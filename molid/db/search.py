import sqlite3

def is_folder_processed(database_file, folder_name):
    """Check if a folder has already been processed."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_folders WHERE folder_name = ?", (folder_name,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_folder_as_processed(database_file, folder_name):
    """Mark a folder as processed."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO processed_folders (folder_name) VALUES (?)", (folder_name,))
    conn.commit()
    conn.close()

def query_database(database_file, field, value):
    """Query the SQLite database for a specific field and value."""
    with sqlite3.connect(database_file) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM compound_data WHERE {field} = ?", (value,))
        return cursor.fetchall()
