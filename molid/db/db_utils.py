import sqlite3
import logging
from molid.db.schema import OFFLINE_SCHEMA, CACHE_SCHEMA

logger = logging.getLogger(__name__)


def is_folder_processed(database_file: str, folder_name: str) -> bool:
    """Check if a folder has already been processed."""
    try:
        with sqlite3.connect(database_file) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_folders WHERE folder_name = ?",
                (folder_name,)
            )
            return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error("Error checking processed folder '%s' in %s: %s", folder_name, database_file, e)
        return False


def mark_folder_as_processed(database_file: str, folder_name: str) -> None:
    """Mark a folder as processed."""
    try:
        with sqlite3.connect(database_file) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_folders (folder_name) VALUES (?)",
                (folder_name,)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Error marking folder '%s' as processed in %s: %s", folder_name, database_file, e)


def initialize_database(db_file: str, sql_script: str) -> None:
    """Initialize the database schema from a SQL script."""
    try:
        with sqlite3.connect(db_file) as conn:
            conn.executescript(sql_script)
        logger.info("Database initialized: %s", db_file)
    except sqlite3.Error as e:
        logger.error("Failed to initialize database %s: %s", db_file, e)
        raise


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

    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    insert_query = (
        f"INSERT OR IGNORE INTO compound_data ({column_list}) "
        f"VALUES ({placeholders})"
    )

    try:
        with sqlite3.connect(db_file) as conn:
            records = [tuple(entry.get(col) for col in columns) for entry in data]
            conn.executemany(insert_query, records)
            conn.commit()
        logger.info("Saved %d records into '%s'.", len(records), db_file)
    except sqlite3.Error as e:
        logger.error("Failed to save data into %s: %s", db_file, e)
