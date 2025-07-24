"""
Centralized SQL schema definitions for MolID's SQLite databases.
"""

OFFLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compound_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    SMILES TEXT,
    InChIKey TEXT UNIQUE,
    InChI TEXT,
    Formula TEXT,
    InChIKey14 TEXT
);
CREATE INDEX IF NOT EXISTS idx_inchikey ON compound_data(InChIKey);
CREATE INDEX IF NOT EXISTS idx_inchikey14 ON compound_data(InChIKey14);

CREATE TABLE IF NOT EXISTS processed_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_name TEXT UNIQUE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_molecules (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    CID                INTEGER,
    InChIKey           TEXT UNIQUE,
    InChIKey14         TEXT,
    MolecularFormula   TEXT,
    InChI              TEXT,
    TPSA               REAL,
    Charge             INTEGER,
    ConnectivitySMILES TEXT,
    Title              TEXT,
    IUPACName          TEXT,
    XLogP              REAL,
    ExactMass          TEXT,
    Complexity         INTEGER,
    MonoisotopicMass   TEXT,
    SMILES     TEXT,
    fetched_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey ON cached_molecules(InChIKey);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey14 ON cached_molecules(InChIKey14);
"""
