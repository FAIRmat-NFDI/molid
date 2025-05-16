import logging
from typing import List, Dict, Any
from molid.db.database_manager import DatabaseManager
from molid.db.schema import OFFLINE_SCHEMA, CACHE_SCHEMA

logger = logging.getLogger(__name__)

def insert_dict_records(
    db_file: str,
    table: str,
    records: List[Dict[str, Any]],
    ignore_conflicts: bool = True,
) -> None:
    """
    Insert a list of dict records into `table` in the given sqlite file.
    """
    if not records:
        logger.info("No records to insert into '%s'.", db_file)
        return
    mgr = DatabaseManager(db_file)
    columns = list(records[0].keys())
    rows = [[rec.get(col) for col in columns] for rec in records]
    mgr.insert_many(table=table, columns=columns, rows=rows, ignore_conflicts=ignore_conflicts)

def is_folder_processed(database_file: str, folder_name: str) -> bool:
    """Check if a folder has already been processed."""
    mgr = DatabaseManager(database_file)
    return mgr.exists(
        table="processed_folders",
        where_clause="folder_name = ?",
        params=[folder_name]
    )

def mark_folder_as_processed(database_file: str, folder_name: str) -> None:
    """Mark a folder as processed."""
    mgr = DatabaseManager(database_file)
    mgr.insert_many(
        table="processed_folders",
        columns=["folder_name"],
        rows=[[folder_name]],
        ignore_conflicts=True
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

def save_to_database(db_file: str, data: list, columns: list) -> None:
    """Save extracted compound data into the offline database."""
    if not data or not columns:
        logger.info("No data to save into '%s'.", db_file)
        return
    records = [{col: entry.get(col) for col in columns} for entry in data]
    insert_dict_records(db_file, table="compound_data", records=records, ignore_conflicts=True)