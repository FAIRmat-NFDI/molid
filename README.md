# MolID

**MolID** is a versatile Python package and command-line tool for downloading, processing, and querying chemical compound data from PubChem. It supports both:

- A full offline SQLite database built from PubChem SDF dumps.
- On-demand online queries via the PubChem REST API, with optional per-user caching.

---

## Features

- **PubChem SDF Processing**

  - Download `.sdf.gz` archives from NCBI FTP with resume and retry logic.
  - Unpack and extract core properties: SMILES, InChI, InChIKey, molecular formula.

- **Offline Database**

  - Build and maintain a full offline SQLite database (`master_db`) of PubChem compounds.
  - Track processed archives to avoid re-processing.

- **Online API & Caching**

  - Query PubChem REST API on-the-fly (`online-only`).
  - Transparent per-user cache (`cache_db`) for repeated lookups (`online-cached`).

- **Flexible Search Modes**

  - `offline-basic`: lookup by full or 14-character InChIKey prefix.
  - `offline-advanced`: filter by CID, InChIKey, SMILES, name, formula, etc.
  - `online-only` & `online-cached` modes for live API searches.

- **Programmatic API**

  - `run(data)` entry point: accepts ASE `Atoms`, raw XYZ content, file paths, or identifier dict.
  - Helpers: `search_identifier`, `search_from_file`, `search_from_atoms`, `search_from_input`.

- **CLI Interface**

  - `molid config` to set defaults (master DB, mode).
  - `molid db create|update|use` to manage offline database.
  - `molid search <identifier> [--id-type]` to query molecules.

---

## Installation

### Requirements

- Python 3.8+
- `openbabel-wheel` (OpenBabel bindings)
- System libraries for OpenBabel on Linux: `libxrender1`, `libxext6` (e.g., via `apt`, `dnf`, or `pacman`).

### Install via pip

```bash
git clone https://github.com/your_org/MolID.git
cd MolID
pip install -r requirements.txt
```

If OpenBabel fails to install, manually:

```bash
pip install openbabel-wheel
```

Verify OpenBabel:

```bash
obabel -V
```

---

## Configuration

MolID uses Pydantic `BaseSettings` with environment variables (or `~/.molid.env`). All vars are prefixed `MOLID_`:

| Variable                 | Default                  | Description                                                                       |
| ------------------------ | ------------------------ | --------------------------------------------------------------------------------- |
| `MOLID_MASTER_DB`        | `pubchem_data_FULL.db`   | Path to offline master database                                                   |
| `MOLID_CACHE_DB`         | `pubchem_cache.db`       | Path to API cache database                                                        |
| `MOLID_MODE`             | `online-cached`          | Search mode (`offline-basic`, `offline-advanced`, `online-only`, `online-cached`) |
| `MOLID_DOWNLOAD_FOLDER`  | user cache dir/downloads | Temp folder for SDF archives                                                      |
| `MOLID_PROCESSED_FOLDER` | user data dir/processed  | Staging folder for unpacked SDF files                                             |
| `MOLID_MAX_FILES`        | `None`                   | Max number of SDF archives to process                                             |

You can also configure interactively:

```bash
molid config set-db /path/to/master.db
molid config set-mode offline-basic
molid config show
```

---

## Project Structure

```
MolID/                       # Project root
├── molid/                   # Main package
│   ├── __init__.py          # Package init
│   ├── __main__.py          # Module CLI entrypoint
│   ├── cli.py               # CLI subcommands
│   ├── main.py              # `run(data)` universal API
│   ├── pipeline.py          # High-level search orchestration
│   ├── utils/               # Utility modules
│   │   ├── conversion.py    # Format conversions (XYZ, SDF, Atoms)
│   │   ├── disk_utils.py    # Filesystem helpers
│   │   ├── ftp_utils.py     # FTP download logic
│   │   ├── settings.py      # Configuration via Pydantic
│   │   └── __init__.py
│   ├── pubchemproc/         # SDF processing pipeline
│   │   ├── file_handler.py  # Read/write SDF/archives
│   │   ├── pubchem.py       # SDF parsing logic
│   │   └── __init__.py
│   ├── pubchem_api/         # Online REST client & caching
│   │   ├── cache.py         # Local query caching
│   │   ├── fetch.py         # PubChem API requests
│   │   └── __init__.py
│   ├── search/              # Search service and DB lookups
│   │   ├── service.py       # High-level search interface
│   │   ├── db_lookup.py     # SQL queries for identifiers
│   │   └── __init__.py
│   └── db/                  # Offline & cache DB schema/utilities
│       ├── db_utils.py      # DB connection and migrations
│       ├── offline_db_cli.py# CLI for offline DB management
│       ├── schema.py        # Table definitions
│       ├── sqlite_manager.py# Low-level SQLite interactions
│       └── __init__.py
├── requirements.txt         # Python dependencies
├── README.md                # This documentation
└── LICENSE                  # MIT License

tests/                       # Unit and integration tests
```

---

## CLI Usage

### Initialize a new offline DB

```bash
molid db create [--db-file path/to/master.db]
```

### Update the offline DB

```bash
molid db update [--db-file pubchem_data.db] [--max-files N]
```

Downloads, processes, and ingests new PubChem SDF batches.

### Health-check an offline DB

```bash
molid db use [--db-file pubchem_data.db]
```

### Search for a molecule

```bash
molid search <identifier> [--id-type inchikey|smiles|cid|name]
```

Example:

```bash
molid search QWERTYUIOPLKJHG --id-type inchikey
```

Prints JSON properties and the data source mode.

---

## Programmatic API

```python
from molid.main import run

# Search from raw XYZ content:
xyz_str = open("mol.xyz").read()
results, source = run(xyz_str)

# Or search by identifier:
from molid.pipeline import search_identifier
results, source = search_identifier({"smiles": "C1=CC=CC=C1"})
```

Other helpers:

- `search_from_file(path)` for `.xyz`, `.extxyz`, or `.sdf` files.
- `search_from_atoms(atoms: ASE Atoms)` for in-memory structures.

---

## Development & Testing

```bash
# Run tests
pytest tests/

# Lint & format
black .
flake8 .
```

---

## License

MolID is released under the MIT License. See [LICENSE](LICENSE) for details.

