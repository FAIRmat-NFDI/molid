import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class AppConfig:
    # Core DB settings
    master_db: str
    cache_db:  str
    # Search settings
    mode:            str
    cache_enabled:   bool

def _load_raw(path: str = "config.yaml") -> Dict[str, Any]:
    """
    Loader that returns the raw YAML dict.
    """
    p = Path(path)
    if not p.is_file():
        pkg_root = Path(__file__).resolve().parent.parent.parent  # .../MolID/molid/utils/
        alt1 = pkg_root / "config.yaml"
        alt2 = pkg_root.parent / "config.yaml"
        if alt1.is_file():
            p = alt1
        elif alt2.is_file():
            p = alt2
        else:
            raise FileNotFoundError(
                f"Config file not found at {p!s}, {alt1}, or {alt2}"
            )
    with open(p) as f:
        return yaml.safe_load(f)

def load_config(path: str = "config.yaml") -> AppConfig:
    """
    Load and validate the YAML config, returning a typed AppConfig.
    """
    raw = _load_raw(path)
    return AppConfig(
        master_db    = raw["master_db"],
        cache_db     = raw["cache_db"],
        mode         = raw.get("mode", "offline-basic"),
        cache_enabled= raw.get("cache_enabled", False),
    )