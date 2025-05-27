from molid.pipeline import (
    search_from_input
)

__all__ = [
    "run",
    "search_from_input"
]


def run(data, config_path: str = "config.yaml") -> (dict, str):
    """
    Execute a MolID lookup on the given data using the configuration at config_path.

    Parameters
    ----------
    data : ASE Atoms | str | Path | dict
        - ASE Atoms object
        - Path to a .xyz/.extxyz/.sdf file
        - Raw XYZ content as string
        - dict of identifier and identifier type (example {"SMILES": "c1ccccc1"})
    config_path : str
        Path to MolID config.yaml

    Returns
    -------
    result : list of dict
        Dictionary of molecular properties from PubChem or offline DB.
    source : str
        Indicates where the data came from (e.g. 'offline-basic', 'api', 'user-cache').

    Raises
    ------
    ValueError, FileNotFoundError
    """
    return search_from_input(data, config_path)
