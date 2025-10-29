# MolID

**MolID** is a Python toolkit and CLI for **resolving, validating, and enriching chemical identifiers** from PubChem — either online via API, offline via local databases, or through a smart hybrid `AUTO` mode.
It is designed to provide robust compound lookup, CAS mapping, and caching for workflows that integrate chemical metadata into larger material-science or data-infrastructure projects.

---

## Key Features

### Flexible Search Sources
MolID now uses an ordered list of **sources** instead of legacy "modes".
You can flexibly mix offline databases, cache, and API access using configuration options.

| Source | Description |
|---------|-------------|
| `master` | The read-only, static master PubChem database (for NOMAD or labeling). |
| `cache`  | User’s local cache database with previously queried compounds. |
| `api`    | Live PubChem REST API queries (optionally writing to cache). |

This replaces the old AUTO / offline-basic / online-cached modes. You can combine sources, e.g.:
- `["master"]` – strictly offline using master DB only.
- `["cache"]` – strictly offline using the local cache DB.
- `["cache", "api"]` – default hybrid mode (use cache, fall back to PubChem).
- `["master", "cache", "api"]` – prefer offline data, then API as fallback.


### Supported Identifiers
- CID, CAS, InChI, InChIKey, SMILES, MolecularFormula, and Name.
- Auto-normalization of identifiers (e.g. SMILES → InChIKey).
- Isotope-aware InChIKey generation from ASE `Atoms` objects using OpenBabel.

### Databases
- **Offline database:** built from PubChem `.sdf.gz` dumps.
  - Tracks processed archives.
  - Can be updated incrementally.
- **Cache database:** stores API query results for faster future lookups.
  - Includes compound and CAS mapping tables.

### CAS Enrichment
- Map PubChem CIDs to CAS numbers via PubChem xrefs.
- Automatic *generic CAS* detection and confidence downgrading.
- Validation of bidirectional CID↔CAS mappings.
- Supports concurrent enrichment of large datasets.

### Configurable Settings
- Fully managed by `pydantic.BaseSettings` and `.env` file (`~/.molid.env`).
- Includes timeouts, retries, and throttling controls for API calls.
- Easily editable via CLI (`molid config ...`).

### CLI Commands
| Command | Description |
|----------|-------------|
| `molid config` | Manage configuration and modes |
| `molid db create` | Create new offline database |
| `molid db update` | Fetch & process PubChem archives |
| `molid db enrich-cas` | Enrich database with CAS mappings |
| `molid search` | Query molecules from any mode |

---

## Installation

### Requirements
- **Python** ≥ 3.8
- Optional dependency: **OpenBabel** (for `.xyz` / ASE Atoms → InChIKey conversion)
- Optional system libs on Linux:
  ```bash
  sudo apt install libxrender1 libxext6
  ```

### Install from source
```bash
pip install molid
```

### Optional: Enable OpenBabel support
MolID can optionally use **OpenBabel** to convert `.xyz` or ASE `Atoms` structures into InChIKeys.
If you only search by SMILES, InChI, or InChIKey, you can skip this dependency.

To enable OpenBabel support:
```bash
pip install molid[openbabel]
# or, alternatively:
pip install openbabel-wheel
```
If OpenBabel is not installed and you run an `.xyz` or `Atoms` search, MolID will show:
```
ERROR: Missing optional dependency 'openbabel'. Install it to enable XYZ/Atoms → InChIKey conversion.
```
---

## Configuration

MolID reads from environment variables or `~/.molid.env`.
All variables are prefixed `MOLID_`.

| Variable | Default | Description |
|-----------|----------|-------------|
| `MOLID_MASTER_DB` | `pubchem_data_FULL.db` | Path to offline master database |
| `MOLID_CACHE_DB` | `pubchem_cache.db` | Path to API cache database |
| `MOLID_SOURCES` | `cache,api` | Ordered list of data sources (`master`, `cache`, `api`) |
| `MOLID_NETWORK` | `allow` | Whether API/network access is allowed |
| `MOLID_CACHE_WRITES` | `True` | Whether API results are written into the cache database |
| `MOLID_DOWNLOAD_FOLDER` | `~/.cache/molid/downloads` | Folder for PubChem `.sdf.gz` archives |
| `MOLID_PROCESSED_FOLDER` | `~/.local/share/molid/processed` | Folder for unpacked `.sdf` files |
| `MOLID_LOG_FILE` | `~/.local/share/molid/molid.log` | Default log file |
| `MOLID_HTTP_CONNECT_TIMEOUT` | 10 | API connection timeout (s) |
| `MOLID_HTTP_READ_TIMEOUT` | 35 | API read timeout (s) |
| `MOLID_HTTP_RETRIES` | 4 | Retry attempts |
| `MOLID_HTTP_BACKOFF` | 0.7 | Backoff factor between retries |

### Example CLI setup
```bash
molid config set-master /data/molid/pubchem_master.db
molid config set-cache ~/.cache/molid/pubchem_cache.db
molid config set-sources cache api
molid config set-network allow
molid config set-cache-writes true
molid config show
```

---

## Usage

### Create and Update Database
```bash
# Create empty offline DB
molid db create --db-file pubchem_data.db

# Download and ingest new PubChem SDF batches
molid db update --max-files 10
```

### Enrich CAS mappings
```bash
molid db enrich-cas --limit 100000
```

### Search Examples
```bash
# Search by InChIKey
molid search QGZKDVFQNNGYKY-UHFFFAOYSA-N --id-type inchikey

# Search by formula
molid search H2O --id-type molecularformula

# Auto-detect identifier type
molid search 25322-68-3
```

Outputs a JSON block including compound properties and data source.

---

## Python API

```python
from molid.main import run
from molid.pipeline import search_identifier

# From an ASE Atoms object
results, source = run(atoms)

# From a SMILES string
results, source = search_identifier({"smiles": "C1=CC=CC=C1"})
```

Additional helpers:
- `search_from_file(path)` → handles `.xyz`, `.extxyz`, `.sdf`
- `search_from_atoms(atoms)` → handles ASE `Atoms`
- `search_from_input(data)` → infers type automatically

---

## Architecture Overview

```
molid/
├── init.py
├── main.py                   # Enables python -m molid CLI execution
├── main.py                   # High-level programmatic entrypoint (API wrapper)
├── cli.py                    # Command-line interface: config, DB ops, search
├── pipeline.py               # Unified search orchestration (Atoms, file, identifier)
│
├── search/
│   ├── init.py
│   ├── service.py            # Central search engine with offline/online/auto modes
│   └── db_lookup.py          # SQLite lookup logic for offline and cache DBs
│
├── db/
│   ├── init.py
│   ├── schema.py             # Centralized SQLite schema & property definitions
│   ├── db_utils.py           # Database creation, initialization, UPSERT helpers
│   ├── sqlite_manager.py     # Generic SQLite wrapper (queries, inserts, schema setup)
│   ├── offline_db_cli.py     # CLI for managing PubChem offline archives (download, ingest, enrich)
│   ├── cas_enrich.py         # Parallel CAS↔CID enrichment, confidence scoring, and generic-CAS detection
│   └── cas_enrich.py
│
├── pubchemproc/
│   ├── init.py
│   ├── pubchem.py            # SDF file parsing and extraction of compound records
│   ├── fetch.py              # High-level data retrieval and enrichment via PubChem REST API
│   ├── pubchem_client.py     # Session management, retry policies, and endpoint resolution
│   ├── cache.py              # Cache database management and store/fetch synchronization
│   └── file_handler.py       # File utilities for .gz, .sdf, and MD5 validation
│
├── utils/
│   ├── init.py
│   ├── formula.py            # Formula parsing and Hill-system canonicalization
│   ├── conversion.py         # SMILES/InChI/XYZ conversion and isotope tagging via OpenBabel
│   ├── identifiers.py        # Identifier normalization and type coercion
│   ├── ftp_utils.py          # FTP/HTTP logic for downloading PubChem archives
│   ├── disk_utils.py         # Disk space validation utilities
│   └── settings.py           # Pydantic-based configuration loader & persistence

```

---

## Development & Testing

```bash
pytest -v
black .
flake8 .
```

Optional integration test:
```bash
molid search --id-type smiles C
```

---

## License

MolID is released under the **Apache License 2.0**.
See the [LICENSE](LICENSE) file for full details.
