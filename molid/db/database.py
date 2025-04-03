import sqlite3

def initialize_database(database_file, fields):
    """Initialize the main database and create tables."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    # Create compound data table
    columns = ", ".join([
    f"{field} TEXT" for field in fields if fields[field] is not None
    ] + ["InChIKey14 TEXT"])
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS compound_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {columns}
        )
    """)
    # Add index for InChIKey
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inchikey ON compound_data(InChIKey);")
    # Create processed folders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT UNIQUE NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_to_database(database_file, data, fields):
    """Save extracted data into the database."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    placeholders = ", ".join(["?" for _ in fields])
    insert_query = f"INSERT INTO compound_data ({', '.join(fields)}) VALUES ({placeholders})"
    cursor.executemany(insert_query, [[entry.get(field) for field in fields] for entry in data])
    conn.commit()
    conn.close()
