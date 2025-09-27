from typing import Optional, Tuple, List, Dict
import os
import re
import json

from .models import GeneratedSQL, Identity
from .retriever import retrieve_snippets
from .safety import ensure_limit, append_company_constraint
from .schema_cache import schema_cache


USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))


RU_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
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


def _load_few_shots() -> List[Dict[str, str]]:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "corpus", "few_shots.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _render_few_shots(few: List[Dict[str, str]], identity: Identity) -> str:
    def render_sql(tmpl: str) -> str:
        return (
            tmpl.replace("{{company_id}}", str(identity.company_id or 0))
                .replace("{{department_id}}", str(identity.department_id or 0))
                .replace("{{user_id}}", str(identity.user_id))
        )
    lines: List[str] = []
    for ex in few:
        q = ex.get("question", "").strip()
        s = render_sql(ex.get("sql", "").strip())
        if q and s:
            lines.append(f"Q: {q}\nSQL: {s}")
    return "\n\n".join(lines[:10])


def _extract_json_block(text: str) -> Dict[str, str]:
    # Try to locate the first { ... } JSON block in the response
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    # Try code fences
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}


def generate_sql(question: str, identity: Identity, limit: int = 200) -> GeneratedSQL:
    # Ensure schema is loaded
    if not schema_cache.tables:
        try:
            schema_cache.load()
        except Exception:
            pass

    # Retrieve context: schema snippets + few-shots
    schema_snippets = retrieve_snippets(question, k=12)
    few_raw = _load_few_shots()
    few_text = _render_few_shots(few_raw, identity) if few_raw else ""

    sql = ""
    needs = False
    clar = ""

    # Simple month/year rule first (cheap)
    table = _first_existing_table()
    month_year = _parse_month_year(question)
  
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="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",
            )

        system_prompt = (
            "Ты — помощник по аналитическим запросам Postgres. "
            "Пиши только валидный SQL для Postgres. Используй ТОЛЬКО предоставленную схему и правила. "
            "Только SELECT, явные JOIN. Не придумывай таблицы/колонки. Добавляй LIMIT если нет."
        )
        prompt = (
            "Схема/связи (фрагменты):\n" + "\n".join(schema_snippets) + "\n\n"
            + ("Примеры (NL→SQL):\n" + few_text + "\n\n" if few_text else "")
            + f"Контекст пользователя: user_id={identity.user_id}, department_id={identity.department_id}, company_id={identity.company_id}, role={identity.role}\n"
            + f"Вопрос: {question}\n\n"
            + "Ответь строго JSON с полями: {\"sql\": \"...\", \"needs_clarification\": false, \"clarification_question\": \"\"}."
           # "Напиши такой SQL: SELECT * FROM tasks WHERE company_id = 0 AND created_at >= '2025-09-01' AND created_at < '2025-10-01' LIMIT 200"
        )

        resp = client.chat.completions.create(
            model="x-ai/grok-4-fast:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            #temperature=0.1,
        )
        text = resp.choices[0].message.content 
        data = _extract_json_block(text)
        #sql = text
        sql = str(data.get("sql", "")).strip()
        needs = bool(data.get("needs_clarification", False))
        clar = str(data.get("clarification_question", ""))
    except Exception as e:
        sql = str(e)
        needs = True
        clar = "Не удалось сгенерировать SQL. Уточните запрос."

    if identity.company_id is not None and sql:
        sql = append_company_constraint(sql, "company_id", identity.company_id)
    sql = ensure_limit(sql, default_limit=limit)

    return GeneratedSQL(sql=sql, needs_clarification=needs, clarification_question=clar)
