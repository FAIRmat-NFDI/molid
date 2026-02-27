import re


def _extract_columns(schema: str, table: str) -> tuple[str, ...]:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\)", schema, re.S | re.I)
    cols = []
    for line in (m.group(1) if m else "").splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY")):
            continue
        col = line.split()[0]
        if col != "fetched_at":
            cols.append(col)
    return tuple(cols)


NUMERIC_FIELDS = [
    "XLogP",
    "ExactMass",
    "MonoisotopicMass",
    "MolecularWeight",
    "TPSA",
    "Complexity",
    "Charge",
]

"""
Centralized SQL schema definitions for MolID's SQLite databases.
"""
# ------------------------------------------------------------------
# Offline master db schema
# ------------------------------------------------------------------
OFFLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compound_data (
    CID                 INTEGER PRIMARY KEY,
    Title               TEXT,
    IUPACName           TEXT,
    MolecularFormula    TEXT,
    CanonicalSMILES     TEXT,   -- connectivity/topology only
    InChIKey            TEXT,
    InChI               TEXT,
    ExactMass           REAL,
    MolecularWeight     REAL,
    MonoisotopicMass    REAL,
    CAS                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_inchikey                 ON compound_data(InChIKey);
CREATE INDEX IF NOT EXISTS idx_compound_inchikey14      ON compound_data(substr(InChIKey, 1, 14));
CREATE INDEX IF NOT EXISTS idx_compound_inchi           ON compound_data(InChI);
CREATE INDEX IF NOT EXISTS idx_compound_canonicalsmiles ON compound_data(CanonicalSMILES);

CREATE INDEX IF NOT EXISTS idx_compound_cas             ON compound_data(CAS);
CREATE INDEX IF NOT EXISTS idx_compound_formula         ON compound_data(MolecularFormula);

CREATE TABLE IF NOT EXISTS cas_mapping (
    CAS         TEXT NOT NULL,
    CID         INTEGER NOT NULL,
    source      TEXT,                     -- 'xref' (authoritative) or 'synonym' (heuristic)
    confidence  INTEGER,                  -- 2=checksum-valid RN, 1=weaker
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (CAS, CID),
    FOREIGN KEY (CID) REFERENCES compound_data(CID)
);

CREATE INDEX IF NOT EXISTS idx_cas_mapping_cas ON cas_mapping(CAS);
CREATE INDEX IF NOT EXISTS idx_cas_mapping_cid ON cas_mapping(CID);

CREATE TABLE IF NOT EXISTS processed_archives (
    archive_name   TEXT PRIMARY KEY,
    status         TEXT,
    last_error     TEXT,
    md5            TEXT,
    source         TEXT NOT NULL,          -- 'full' or 'monthly'
    last_ingested  TIMESTAMP,              -- ISO string in UTC
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Columns present in the offline table (compound_data)
OFFLINE_COLUMNS = _extract_columns(OFFLINE_SCHEMA, "compound_data")

# Map DB column → SDF tag to read from PubChem SDF
OFFLINE_SDF_TAGS: dict[str, str] = {
    "CID": "PUBCHEM_COMPOUND_CID",
    "Title": "Title",
    "IUPACName": "PUBCHEM_IUPAC_NAME",
    "MolecularFormula": "PUBCHEM_MOLECULAR_FORMULA",
    "SMILES": "PUBCHEM_SMILES",
    "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
    "InChI": "PUBCHEM_IUPAC_INCHI",
    "ExactMass": "PUBCHEM_EXACT_MASS",
    "MolecularWeight": "PUBCHEM_MOLECULAR_WEIGHT",
    "MonoisotopicMass": "PUBCHEM_MONOISOTOPIC_MASS",
}

DEFAULT_PROPERTIES_MASTER = {
    col: OFFLINE_SDF_TAGS[col] for col in OFFLINE_COLUMNS if col in OFFLINE_SDF_TAGS
}

# ------------------------------------------------------------------
# Cached db schema
# ------------------------------------------------------------------
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_molecules (
    CID                INTEGER PRIMARY KEY,
    Title              TEXT,
    IUPACName          TEXT,
    MolecularFormula   TEXT,
    InChI              TEXT,
    InChIKey           TEXT,
    CanonicalSMILES    TEXT,    -- connectivity/topology only
    IsomericSMILES     TEXT,    -- stereo + isotope
    XLogP              REAL,
    ExactMass          REAL,
    MonoisotopicMass   REAL,
    MolecularWeight    REAL,
    TPSA               REAL,
    Complexity         INTEGER,
    Charge             INTEGER,
    fetched_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey           ON cached_molecules(InChIKey);
CREATE INDEX IF NOT EXISTS idx_cache_inchikey14         ON cached_molecules(substr(InChIKey, 1, 14));
CREATE INDEX IF NOT EXISTS idx_cache_inchi              ON cached_molecules(InChI);
CREATE INDEX IF NOT EXISTS idx_cache_canonicalsmiles    ON cached_molecules(CanonicalSMILES);
CREATE INDEX IF NOT EXISTS idx_cache_isomericsmiles     ON cached_molecules(IsomericSMILES);


CREATE INDEX IF NOT EXISTS idx_cache_formula            ON cached_molecules(MolecularFormula);

CREATE TABLE IF NOT EXISTS cas_mapping (
    CAS         TEXT NOT NULL,
    CID         INTEGER NOT NULL,
    source      TEXT,                     -- 'xref' (authoritative) or 'synonym' (heuristic)
    confidence  INTEGER,                  -- 2=checksum-valid RN, 1=weaker
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (CAS, CID)
);

CREATE INDEX IF NOT EXISTS idx_cas_mapping_cas ON cas_mapping(CAS);
CREATE INDEX IF NOT EXISTS idx_cas_mapping_cid ON cas_mapping(CID);
"""


CACHE_COLUMNS = _extract_columns(CACHE_SCHEMA, "cached_molecules")

# derive API request list from the same source of truth
DEFAULT_PROPERTIES_CACHE = tuple(c for c in CACHE_COLUMNS if c not in {"CID"})
