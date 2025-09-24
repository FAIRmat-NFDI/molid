from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Generic SQLite helper for schema initialization,
    simple inserts, and custom queries.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        # ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize(self, sql_script: str) -> None:
        """Create or migrate the database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                try:
                    conn.executescript(sql_script)
                except:
                    import pdb; pdb.set_trace()
            logger.info("Initialized database schema at %s", self.db_path)
        except sqlite3.Error as e:
            logger.error("Failed to initialize %s: %s", self.db_path, e)
            raise

    def insert_many(
        self,
        table: str,
        columns: list[str],
        rows: list[list[Any]],
        ignore_conflicts: bool = True
    ) -> None:
        """
        Insert multiple rows into `table` for the given `columns`.
        If ignore_conflicts, will do INSERT OR IGNORE; otherwise plain INSERT.
        """
        if not rows:
            logger.debug("No rows to insert into %s", table)
            return

        cols = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        verb = "INSERT OR IGNORE" if ignore_conflicts else "INSERT"
        sql = f"{verb} INTO {table} ({cols}) VALUES ({placeholders})"

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(sql, rows)
                conn.commit()
            logger.info("Inserted %d rows into %s", len(rows), table)
        except sqlite3.Error as e:
            logger.error("Failed to insert rows into %s: %s", table, e)
            raise

    def exists(
        self,
        table: str,
        where_clause: str,
        params: list[Any]
    ) -> bool:
        """Return True if a row exists matching the given WHERE clause."""
        sql = f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1"
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(sql, params)
                return cur.fetchone() is not None
        except sqlite3.Error as e:
            logger.error("Existence check failed on %s: %s", self.db_path, e)
            return False

    def query_one(
        self,
        sql: str,
        params: list[Any] = None
    ) -> dict[str, Any] | None:
        """Return a single row as a dict, or None if not found."""
        params = params or []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def query_all(
        self,
        sql: str,
        params: list[Any] = None
    ) -> list[dict[str, Any]]:
        """Return all matching rows as a list of dicts."""
        params = params or []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, params or [])
            conn.commit()

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.executemany(sql, seq_of_params)
            except:
                import pdb; pdb.set_trace()
            conn.commit()

