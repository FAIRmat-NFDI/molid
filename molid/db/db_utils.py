from __future__ import annotations

import logging
from typing import Any, Optional

from molid.db.sqlite_manager import DatabaseManager
from molid.db.schema import OFFLINE_SCHEMA, CACHE_SCHEMA

logger = logging.getLogger(__name__)


def insert_dict_records(
    db_file: str,
    table: str,
    records: list[dict[str, Any]],
    ignore_conflicts: bool = True,
) -> None:
    """
    Insert a list of dict records into `table` in the given sqlite file.
    """
    if not records:
        logger.info("No records to insert into table '%s' (db=%s).", table, db_file)
        return
    mgr = DatabaseManager(db_file)
    columns = list(records[0].keys())
    rows = [[rec.get(col) for col in columns] for rec in records]
    mgr.insert_many(
        table=table, columns=columns, rows=rows, ignore_conflicts=ignore_conflicts
    )


def initialize_database(db_file: str, sql_script: str) -> None:
    """Initialize the database schema from a SQL script."""
    DatabaseManager(db_file).initialize(sql_script)


def create_offline_db(db_file: str) -> None:
    """Create or update the full offline PubChem database schema."""
    initialize_database(db_file, OFFLINE_SCHEMA)


def create_cache_db(db_file: str) -> None:
    """Create or update the user-specific API cache database schema."""
    initialize_database(db_file, CACHE_SCHEMA)


def upsert_archive_state(db_file: str, name: str, **fields: Any) -> None:
    """
    Upsert a row in processed_archives. Unknown keys go into a dynamic SET list.
    """
    db = DatabaseManager(db_file)

    # Build dynamic column and placeholder lists
    cols = list(fields.keys())
    insert_cols = ", ".join(["archive_name"] + cols)
    insert_placeholders = ", ".join(["?"] + ["?"] * len(cols))

    # Use excluded.<col> so we don't need extra parameters in the UPDATE
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in cols)

    sql = f"""
    INSERT INTO processed_archives ({insert_cols})
    VALUES ({insert_placeholders})
    ON CONFLICT(archive_name) DO UPDATE SET
      {set_clause},
      updated_at = CURRENT_TIMESTAMP;
    """
    params = [name] + [fields[c] for c in cols]
    db.execute(sql, params)


def get_archive_state(db_file: str, name: str) -> Optional[dict[str, Any]]:
    db = DatabaseManager(db_file)
    return db.query_one(
        "SELECT * FROM processed_archives WHERE archive_name = ?", [name]
    )


def save_to_database(db_file: str, data: list[dict], columns: list[str]) -> None:
    if not data or not columns:
        logger.info("No data to save into '%s'.", db_file)
        return

    db = DatabaseManager(db_file)
    # Build a parameterized UPSERT that updates all non-key columns
    nonkey = [c for c in columns if c != "CID"]
    insert_cols = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in nonkey)

    sql = f"""
    INSERT INTO compound_data ({insert_cols})
    VALUES ({placeholders})
    ON CONFLICT(CID) DO UPDATE SET
      {set_clause};
    """
    params = [[row.get(c) for c in columns] for row in data]
    db.executemany(sql, params)
