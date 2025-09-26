from typing import Set

import re
import sqlglot
from sqlglot import expressions as exp


ALLOWED_STATEMENTS: Set[str] = {"SELECT"}


def is_safe_select(sql: str) -> bool:
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return False
    # Only allow SELECT
    return isinstance(parsed, exp.Select) or isinstance(parsed, exp.Union) or isinstance(parsed, exp.With)


def ensure_limit(sql: str, default_limit: int = 200) -> str:
    # If there's already a LIMIT, keep as is
    if re.search(r"\blimit\b", sql, flags=re.IGNORECASE):
        return sql
    # Preserve trailing semicolon if present
    sql_stripped = sql.rstrip()
    has_semicolon = sql_stripped.endswith(";")
    if has_semicolon:
        sql_core = sql_stripped[:-1].rstrip()
    else:
        sql_core = sql_stripped
    return f"{sql_core} LIMIT {default_limit}" + (";" if has_semicolon else "")


def append_company_constraint(sql: str, company_column: str, company_id: int) -> str:
    """If possible, add company constraint to WHERE if query has a FROM clause.
    This is best-effort; if not applicable, return original SQL.
    """
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
        if not isinstance(parsed, exp.Select):
            return sql
        # Only append if there is a FROM clause
        if not parsed.args.get("from"):
            return sql
        where = parsed.args.get("where")
        constraint = exp.EQ(this=exp.to_identifier(company_column), that=exp.Literal.number(company_id))
        if where is None:
            parsed.set("where", exp.Where(this=constraint))
        else:
            new_where = exp.and_(where.this, constraint)
            parsed.set("where", exp.Where(this=new_where))
        return parsed.sql(dialect="postgres")
    except Exception:
        return sql
