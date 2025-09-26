from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .db import fetch_all


@dataclass
class Column:
    name: str
    data_type: str
    is_nullable: bool


@dataclass
class TableSchema:
    table: str
    columns: List[Column]


@dataclass
class ForeignKey:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


class SchemaCache:
    def __init__(self) -> None:
        self.tables: Dict[str, TableSchema] = {}
        self.foreign_keys: List[ForeignKey] = []

    def load(self) -> None:
        columns = fetch_all(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        tables: Dict[str, List[Column]] = {}
        for row in columns:
            tables.setdefault(row["table_name"], []).append(
                Column(
                    name=row["column_name"],
                    data_type=row["data_type"],
                    is_nullable=(row["is_nullable"] == "YES"),
                )
            )
        self.tables = {
            t: TableSchema(table=t, columns=cols) for t, cols in tables.items()
        }

        fks = fetch_all(
            """
            SELECT tc.table_name AS child_table,
                   kcu.column_name AS child_column,
                   ccu.table_name AS parent_table,
                   ccu.column_name AS parent_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema)
            JOIN information_schema.constraint_column_usage ccu USING (constraint_name, table_schema)
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
            ORDER BY child_table
            """
        )
        self.foreign_keys = [
            ForeignKey(
                child_table=r["child_table"],
                child_column=r["child_column"],
                parent_table=r["parent_table"],
                parent_column=r["parent_column"],
            )
            for r in fks
        ]

    def to_text_snippets(self) -> List[str]:
        snippets: List[str] = []
        for t, schema in sorted(self.tables.items()):
            cols = ", ".join(f"{c.name}:{c.data_type}" for c in schema.columns)
            snippets.append(f"table {t}({cols})")
        for fk in self.foreign_keys:
            snippets.append(
                f"fk {fk.child_table}.{fk.child_column} -> {fk.parent_table}.{fk.parent_column}"
            )
        return snippets


schema_cache = SchemaCache()
