from typing import Optional, Tuple, List, Dict, Any
from typing import Optional, Tuple, List, Dict, Any
import os
import re
import json
from groq import Groq

from .models import GeneratedSQL, Identity
from .safety import ensure_limit, append_company_constraint
from .schema_cache import schema_cache, ForeignKey

USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

RU_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


class SQLGenerator:
    def __init__(self):
        self.client = Groq(api_key="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")
        self.schema_graph = self._build_schema_graph()

    def _build_schema_graph(self) -> Dict[str, Any]:
        """Строит граф связей между таблицами"""
        if not schema_cache.tables:
            schema_cache.load()

        graph = {
            "tables": {},
            "relationships": []
        }

        for table_name, table_info in schema_cache.tables.items():
            graph["tables"][table_name] = {
                "columns": [col.name for col in table_info.columns],
                "primary_key": self._get_primary_key(table_name),
                "foreign_keys": self._get_table_foreign_keys(table_name)
            }

            # Добавляем связи по внешним ключам
            for fk in schema_cache.foreign_keys:
                if fk.child_table == table_name:
                    graph["relationships"].append({
                        "from_table": fk.child_table,
                        "from_column": fk.child_column,
                        "to_table": fk.parent_table,
                        "to_column": fk.parent_column,
                        "relationship_type": "foreign_key"
                    })
        print('граф построился')

        return graph

    def _get_primary_key(self, table_name: str) -> Optional[str]:
        """Получает имя первичного ключа для таблицы"""
        # Попытка определить первичный ключ на основе названия колонки
        table_info = schema_cache.tables.get(table_name)
        if table_info:
            for col in table_info.columns:
                if col.name.lower() in ['id', f'{table_name.lower()}_id']:
                    return col.name
        return None

    def _get_table_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        """Получает внешние ключи для конкретной таблицы в нужном формате"""
        table_fks = []
        for fk in schema_cache.foreign_keys:
            if fk.child_table == table_name:
                table_fks.append({
                    "column_name": fk.child_column,
                    "foreign_table_name": fk.parent_table,
                    "foreign_column_name": fk.parent_column
                })
        return table_fks

    def _generate_schema_description(self) -> str:
        """Генерирует текстовое описание схемы для модели"""
        description = "SCHEMA DESCRIPTION:\n\n"

        for table_name, table_info in self.schema_graph["tables"].items():
            description += f"TABLE: {table_name}\n"

            # Добавляем колонки
            description += "Columns:\n"
            for col in schema_cache.tables[table_name].columns:
                nullable_str = "NULL" if col.is_nullable else "NOT NULL"
                description += f"  - {col.name}: {col.data_type} {nullable_str}\n"

            if table_info['primary_key']:
                description += f"Primary Key: {table_info['primary_key']}\n"

            # Добавляем связи
            table_relations = [
                rel for rel in self.schema_graph["relationships"]
                if rel["from_table"] == table_name or rel["to_table"] == table_name
            ]

            if table_relations:
                description += "Relationships:\n"
                for rel in table_relations:
                    if rel["from_table"] == table_name:
                        description += f"  - {table_name}.{rel['from_column']} → {rel['to_table']}.{rel['to_column']}\n"
                    else:
                        description += f"  - {table_name} ← {rel['from_table']}.{rel['from_column']}\n"

            description += "\n"

        return description

    def identify_relevant_tables(self, question: str, identity: Identity) -> List[str]:
        """Этап 1: Определение релевантных таблиц"""

        schema_desc = self._generate_schema_description()

        prompt = f"""{schema_desc}

USER QUESTION: {question}
USER CONTEXT: user_id={identity.user_id}, department_id={identity.department_id}, company_id={identity.company_id}

INSTRUCTIONS:
Analyze the question and identify which tables are relevant. Consider:
1. Which entities are mentioned (tasks, users, departments, etc.)
2. What relationships might be needed
3. What filtering conditions apply

Respond with JSON format:
{{
    "relevant_tables": ["table1", "table2", ...],
    "reasoning": "brief explanation of why these tables are needed",
    "join_paths": [
        {{
            "from_table": "table1", 
            "to_table": "table2",
            "on_condition": "table1.col = table2.col"
        }}
    ]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",  # Изменяем модель на доступную для Groq
                messages=[
                    {"role": "system",
                     "content": "You are a database schema analyzer. Identify relevant tables for SQL queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )

            result = _extract_json_block(response.choices[0].message.content)
            return result.get("relevant_tables", [])

        except Exception as e:
            print(f"Error identifying tables: {e}")
            return []

    def generate_sql_with_context(self, question: str, relevant_tables: List[str], identity: Identity) -> GeneratedSQL:
        """Этап 2: Генерация SQL с учетом выбранных таблиц"""

        # Фильтруем описание схемы только для релевантных таблиц
        relevant_schema = self._get_relevant_schema_description(relevant_tables)

        few_shots = self._load_and_render_few_shots(identity)

        prompt = f"""RELEVANT SCHEMA TABLES:
{relevant_schema}

USER CONTEXT: user_id={identity.user_id}, department_id={identity.department_id}, company_id={identity.company_id}, role={identity.role}

EXAMPLES:
{few_shots}

QUESTION: {question}

Generate a PostgreSQL SQL query following these rules:
1. Use only the tables and columns mentioned above
2. Use explicit JOIN syntax
3. Include proper WHERE conditions for user context
4. Add appropriate ORDER BY if sorting is implied
5. Include LIMIT if not specified

Respond with JSON:
{{
    "sql": "generated SQL query",
}}
"""

        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",  # Изменяем модель на доступную для Groq
                messages=[
                    {"role": "system",
                     "content": "You are a PostgreSQL expert. Generate valid, efficient SQL queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )

            result = _extract_json_block(response.choices[0].message.content)
            sql = result.get("sql", "").strip()

            # Валидация и пост-обработка
            if sql:
                sql = self._post_process_sql(sql, identity)

            return GeneratedSQL(
                sql=sql
            )

        except Exception as e:
            return GeneratedSQL(
                sql="SELECT tablename FROM pg_tables"
            )

    def _get_relevant_schema_description(self, tables: List[str]) -> str:
        """Возвращает описание схемы только для релевантных таблиц"""
        description = "RELEVANT TABLES SCHEMA:\n\n"

        for table in tables:
            if table in self.schema_graph["tables"]:
                table_info = self.schema_graph["tables"][table]
                description += f"TABLE: {table}\n"

                # Добавляем колонки
                description += "Columns:\n"
                table_schema = schema_cache.tables[table]
                for col in table_schema.columns:
                    nullable_str = "NULL" if col.is_nullable else "NOT NULL"
                    description += f"  - {col.name}: {col.data_type} {nullable_str}\n"

                # Добавляем только релевантные связи
                relevant_relations = [
                    rel for rel in self.schema_graph["relationships"]
                    if (rel["from_table"] in tables and rel["to_table"] in tables) and
                       (rel["from_table"] == table or rel["to_table"] == table)
                ]

                if relevant_relations:
                    description += "Relevant Relationships:\n"
                    for rel in relevant_relations:
                        if rel["from_table"] == table:
                            description += f"  - {rel['from_table']}.{rel['from_column']} → {rel['to_table']}.{rel['to_column']}\n"
                        elif rel["to_table"] == table:
                            description += f"  - {rel['to_table']} ← {rel['from_table']}.{rel['from_column']}\n"

                description += "\n"

        return description

    def _post_process_sql(self, sql: str, identity: Identity) -> str:
        """Пост-обработка SQL для безопасности и корректности"""
        # Добавляем ограничение по компании если нужно
        if identity.company_id is not None:
            sql = append_company_constraint(sql, "company_id", identity.company_id)

        # Обеспечиваем наличие LIMIT
        sql = ensure_limit(sql, default_limit=200)

        return sql

    def _load_and_render_few_shots(self, identity: Identity) -> str:
        """Загружает и рендерит few-shot примеры"""
        few_raw = _load_few_shots()
        return _render_few_shots(few_raw, identity) if few_raw else ""


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
        snippet = text[start:end + 1]
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
    generator = SQLGenerator()

    # Этап 1: Идентификация релевантных таблиц
    relevant_tables = generator.identify_relevant_tables(question, identity)
    print('Ищем в таблицах\n', relevant_tables)

    if not relevant_tables:
        return GeneratedSQL(
            sql="SELECT * FROM tasks WHERE company_id = {{company_id}} LIMIT 200",
        )

    # Этап 2: Генерация SQL с контекстом
    return generator.generate_sql_with_context(question, relevant_tables, identity)