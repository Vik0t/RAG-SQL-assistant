import contextlib
from typing import Iterator, List, Dict, Any, Optional

import psycopg
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/task_db"
    readonly_role: Optional[str] = None


settings = Settings()


@contextlib.contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(settings.postgres_dsn, autocommit=True)
    try:
        # Ensure UTF-8 client encoding for proper Cyrillic handling
        with conn.cursor() as cur:
            cur.execute("SET client_encoding TO 'UTF8'")
        if settings.readonly_role:
            with conn.cursor() as cur:
                cur.execute(f"SET ROLE {settings.readonly_role}")
        yield conn
    finally:
        conn.close()


def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()


def fetch_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params or {})
            return cur.fetchone()
