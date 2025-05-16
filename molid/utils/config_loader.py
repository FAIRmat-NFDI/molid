import yaml
from pathlib import Path


def load_config(path: str = "config.yaml") -> dict:
    """
    Load the configuration from a YAML file.
    Tries:
    1. Direct path.
    2. Package-root relative config.yaml.
    3. Project-root relative config.yaml.
    Raises FileNotFoundError if none found.
    """
    p = Path(path)
    if p.is_file():
        cfg_path = p
    else:
        # Try package-root
        pkg_root = Path(__file__).resolve().parent.parent.parent  # .../MolID/molid/utils/
        alt1 = pkg_root / "config.yaml"
        alt2 = pkg_root.parent / "config.yaml"
        if alt1.is_file():
            cfg_path = alt1
        elif alt2.is_file():
            cfg_path = alt2
        else:
            raise FileNotFoundError(
                f"Config file not found at {p!s}, {alt1}, or {alt2}"
            )
    with open(cfg_path) as f:
        return yaml.safe_load(f)
