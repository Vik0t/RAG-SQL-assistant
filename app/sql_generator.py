from typing import Optional, Tuple
import os
import re

from .models import GeneratedSQL, Identity
from .retriever import retrieve_snippets
from .safety import ensure_limit, append_company_constraint
from .schema_cache import schema_cache


USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))


RU_MONTHS = {
    # base → month number; match by prefix in text
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,  # май/мая
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


def _first_existing_table() -> Optional[str]:
    if not schema_cache.tables:
        schema_cache.load()
    preferred = ["tasks", "task", "users", "user"]
    for p in preferred:
        if p in schema_cache.tables:
            return p
    if schema_cache.tables:
        return sorted(schema_cache.tables.keys())[0]
    return None


def _table_has_column(table: str, column: str) -> bool:
    ts = schema_cache.tables.get(table)
    if not ts:
        return False
    return any(c.name.lower() == column.lower() for c in ts.columns)


def _parse_month_year(text: str) -> Optional[Tuple[int, int]]:
    tl = text.lower()
    month = None
    for prefix, mnum in RU_MONTHS.items():
        if prefix in tl:
            month = mnum
            break
    if month is None:
        return None
    years = re.findall(r"(20\d{2})", tl)
    if not years:
        return None
    year = int(years[0])
    return (year, month)


def generate_sql(question: str, identity: Identity, limit: int = 200) -> GeneratedSQL:
    # Make sure schema is loaded before any logic
    if not schema_cache.tables:
        try:
            schema_cache.load()
        except Exception:
            pass

    context_snippets = retrieve_snippets(question, k=12)

    sql = ""
    needs = False
    clar = ""

    # Rule-based shortcut for common case: month in text → date range on tasks.created_at
    table = _first_existing_table()
    month_year = _parse_month_year(question)
    if table and month_year and _table_has_column(table, "created_at"):
        year, month = month_year
        # compute next month and year rollover
        next_month = 1 if month == 12 else month + 1
        next_year = year + 1 if month == 12 else year
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE created_at >= '{year:04d}-{month:02d}-01' AND created_at < '{next_year:04d}-{next_month:02d}-01'"
        )
    else:
        if USE_OPENAI:
            try:
                from openai import OpenAI

                client = OpenAI()
                system_prompt = (
                    "Ты генерируешь Postgres SQL только на основе предоставленной схемы и правил. "
                    "Только SELECT, явные JOIN, не выдумывай таблицы/колонки. Ограничь результат."
                )
                prompt = (
                    f"Контекст:\n" + "\n".join(context_snippets) + "\n\n"
                    f"Пользователь: user_id={identity.user_id}, company_id={identity.company_id}, department_id={identity.department_id}, role={identity.role}\n"
                    f"Вопрос: {question}\n"
                    "Ответи в JSON: {\"sql\": \"...\", \"needs_clarification\": false, \"clarification_question\": \"\"}"
                )
                resp = client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                text = resp.choices[0].message.content or ""
                import json

                data = json.loads(text)
                sql = str(data.get("sql", "")).strip()
                needs = bool(data.get("needs_clarification", False))
                clar = str(data.get("clarification_question", ""))
            except Exception:
                sql = ""
                needs = True
                clar = "Не удалось сгенерировать SQL. Уточните запрос."
        else:
            if table:
                sql = f"SELECT * FROM {table}"
            else:
                sql = "SELECT 1 AS ok"
                needs = True
                clar = "Схема базы данных недоступна."

    # Fallback if sql is still empty for any reason
    if not sql.strip():
        table = _first_existing_table()
        if table:
            sql = f"SELECT * FROM {table}"
            needs = False
            clar = ""
        else:
            sql = "SELECT 1 AS ok"
            needs = True
            if not clar:
                clar = "Схема базы данных недоступна."

    if identity.company_id is not None and sql:
        sql = append_company_constraint(sql, "company_id", identity.company_id)
    sql = ensure_limit(sql, default_limit=limit)

    return GeneratedSQL(sql=sql, needs_clarification=needs, clarification_question=clar)
