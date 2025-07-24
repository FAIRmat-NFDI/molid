import io
import os
from pathlib import Path
from ase import Atoms
from ase.io import read

from molid.utils.conversion import atoms_to_inchikey
from molid.search.service import SearchService, SearchConfig
from molid.pubchemproc.pubchem import process_file, FIELDS_TO_EXTRACT
from molid.utils.settings import load_config, AppConfig


def _create_search_service() -> SearchService:
    """
    Instantiate a SearchService from Pydantic settings (env/defaults).
    """
    cfg: AppConfig = load_config()
    master_db     = cfg.master_db
    cache_db      = cfg.cache_db
    mode          = cfg.mode

    _sanity_check(master_db, cache_db, mode)
    search_cfg = SearchConfig(mode=mode)
    return SearchService(master_db=master_db, cache_db=cache_db, cfg=search_cfg)


def search_identifier(input):
    """
    Universal search for any identifier type (InChIKey, SMILES, name, etc.)
    using the configured mode. Returns (list of result dicts, source).
    """
    service = _create_search_service()
    return service.search(input)

def search_from_atoms(atoms: Atoms):
    """
    Search using an ASE Atoms object. Computes its InChIKey, then delegates.
    Returns (list of result dicts, source).
    """
    inchikey = atoms_to_inchikey(atoms)
    input = {"inchikey": inchikey}
    return search_identifier(input)


def search_from_file(file_path: str):
    """
    Detect file extension from path and process accordingly:
    - .xyz, .extxyz: read via ASE, then search
    - .sdf: extract InChIKey via process_file, then search
    Returns (list of result dicts, source).
    """
    #TODO: Rework function. FIELDS_TO_EXTRACT is strange
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    ext = p.suffix.lower()
    if ext in ['.xyz', '.extxyz']:
        atoms = read(str(p), format='xyz')
        return search_from_atoms(atoms)
    if ext == '.sdf':
        records = process_file(str(p), FIELDS_TO_EXTRACT)
        if not records or 'InChIKey' not in records[0]:
            raise ValueError(f"No InChIKey found in SDF: {file_path}")
        inchikey = records[0]['InChIKey']
        return search_identifier({"inchikey": inchikey})
    raise ValueError(f"Unsupported file extension: {ext}")


def search_from_input(data):
    """
    Universal entrypoint: accepts one of:
      • ASE Atoms
      • file path (xyz/extxyz/sdf)
      • raw XYZ file content (str)
    Detects type automatically and delegates to the right handler.
    Returns (list of result dicts, source).
    """
    # Identifier
    if isinstance(data, dict):
        return search_identifier(data)

    # ASE Atoms
    if isinstance(data, Atoms):
        return search_from_atoms(data)

    # File path
    if isinstance(data, str) and os.path.isfile(data):
        return search_from_file(data)

    if isinstance(data, Path) and data.is_file():
        return search_from_file(str(data))

    # Raw XYZ content
    if isinstance(data, str):
        try:
            atoms = read(io.StringIO(data), format='xyz')
            return search_from_atoms(atoms)
        except Exception as e:
            print(e)
            pass

    raise ValueError("Input type not recognized: must be ASE Atoms, file path, dict (of identifiers) or raw XYZ content.")

def _sanity_check(master_db, cache_db, mode):
    if mode not in ("offline-basic", "offline-advanced", "online-only", "online-cached"):
        raise ValueError(f'{mode} is no valid search mode. Select on of "offline-basic", "offline-advanced", "online-only", "online-cached"')
    p_master_db = Path(master_db)
    if mode == "offline-basic" and not p_master_db.exists():
        raise FileNotFoundError(f"File not found: {master_db}. Master DB needed for {mode}")
    p_cache_db = Path(cache_db)
    if mode == "offline-advanced" and not p_cache_db.exists():
        raise FileNotFoundError(f"File not found: {p_cache_db}. Cache DB needed for {mode}")