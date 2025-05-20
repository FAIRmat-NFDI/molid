import io
import os
from pathlib import Path
from ase import Atoms
from ase.io import read

from molid.utils.conversion import atoms_to_inchikey
from molid.search.service import SearchService, SearchConfig
from molid.pubchemproc.pubchem import process_file, FIELDS_TO_EXTRACT
from molid.utils.config_loader import load_config, AppConfig


def _create_search_service(config_path: str = "config.yaml") -> SearchService:
    """
    Instantiate a SearchService based on parameters in config.yaml.
    """
    cfg: AppConfig = load_config(config_path)
    master_db     = cfg.master_db
    cache_db      = cfg.cache_db
    mode          = cfg.mode
    cache_enabled = cfg.cache_enabled

    _sanity_check(master_db, cache_db, mode)
    search_cfg = SearchConfig(mode=mode, cache_enabled=cache_enabled)
    return SearchService(master_db=master_db, cache_db=cache_db, cfg=search_cfg)


def search_identifier(
    input,
    config_path: str = "config.yaml"
) -> (Dict, str):
    """
    Universal search for any identifier type (InChIKey, SMILES, name, etc.)
    using the mode defined in config.yaml. Returns (result Dict, source).
    """
    service = _create_search_service(config_path)
    return service.search(input)

def search_from_atoms(
    atoms: Atoms,
    config_path: str = "config.yaml"
) -> (Dict, str):
    """
    Search using an ASE Atoms object. Computes its InChIKey, then delegates.
    Returns (result Dict, source).
    """
    inchikey = atoms_to_inchikey(atoms)
    input = {"inchikey": inchikey}
    return search_identifier(input, config_path=config_path)


def search_from_file(
    file_path: str,
    config_path: str = "config.yaml"
) -> (Dict, str):
    """
    Detect file extension from path and process accordingly:
    - .xyz, .extxyz: read via ASE, then search
    - .sdf: extract InChIKey via process_file, then search
    Returns (result Dict, source).
    """
    #TODO: Rework function. FIELDS_TO_EXTRACT is strange
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    ext = p.suffix.lower()
    if ext in ['.xyz', '.extxyz']:
        atoms = read(str(p), format='xyz')
        return search_from_atoms(atoms, config_path)
    if ext == '.sdf':
        records = process_file(str(p), FIELDS_TO_EXTRACT)
        if not records or 'InChIKey' not in records[0]:
            raise ValueError(f"No InChIKey found in SDF: {file_path}")
        inchikey = records[0]['InChIKey']
        return search_identifier(inchikey, config_path=config_path)
    raise ValueError(f"Unsupported file extension: {ext}")


def search_from_input(
    data,
    config_path: str = "config.yaml"
) -> (Dict, str):
    """
    Universal entrypoint: accepts one of:
      • ASE Atoms
      • file path (xyz/extxyz/sdf)
      • raw XYZ file content (str)
    Detects type automatically and delegates to the right handler.
    Returns (result Dict, source).
    """
    # Identifier
    if isinstance(data, dict):
        return search_identifier(data, config_path)

    # ASE Atoms
    if isinstance(data, Atoms):
        return search_from_atoms(data, config_path)

    # File path
    if isinstance(data, str) and os.path.isfile(data):
        return search_from_file(data, config_path)

    if isinstance(data, Path) and data.is_file():
        return search_from_file(str(data), config_path)

    # Raw XYZ content
    if isinstance(data, str):
        try:
            atoms = read(io.StringIO(data), format='xyz')
            return search_from_atoms(atoms, config_path)
        except Exception:
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