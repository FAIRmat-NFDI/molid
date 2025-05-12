from molid.pipeline import (
    search_from_input,
    search_from_atoms,
    search_from_file,
    search_identifier
)

__all__ = [
    "run",
    "search_from_input",
    "search_from_atoms",
    "search_from_file",
    "search_identifier"
]


def run(data, config_path: str = "config.yaml") -> (dict, str):
    """
    Execute a MolID lookup on the given data using the configuration at config_path.

    Parameters
    ----------
    data : ASE Atoms | str | Path
        - ASE Atoms object
        - Path to a .xyz/.extxyz/.sdf file
        - Raw XYZ content as string
    config_path : str
        Path to MolID config.yaml

    Returns
    -------
    result : dict
        Dictionary of molecular properties from PubChem or offline DB.
    source : str
        Indicates where the data came from (e.g. 'offline-basic', 'api', 'user-cache').

    Raises
    ------
    ValueError, FileNotFoundError
    """
    return search_from_input(data, config_path)
