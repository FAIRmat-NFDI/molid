# molid/utils/identifiers.py
from __future__ import annotations
from typing import Any, Literal

from molid.utils.conversion import convert_to_inchikey

_BASIC_ALLOWED   = ("inchikey", "inchi", "smiles")
_ADV_ALLOWED     = ("cid", "name", "smiles", "inchi", "inchikey", "molecularformula", "cas")

def normalize_query(
    query: dict[str, Any],
    mode: Literal["basic","advanced"]
) -> tuple[str, Any]:
    """
    Validate + normalize a one-key query based on mode.
    - Converts SMILES/InChI → InChIKey
    - Maps keys to lowercase
    """
    if not isinstance(query, dict) or len(query) != 1:
        raise ValueError("Expected a dict with exactly one identifier.")
    k, v = next(iter(((k.lower(), val) for k, val in query.items())))
    allowed = _BASIC_ALLOWED if mode == "basic" else _ADV_ALLOWED
    if k not in allowed:
        raise ValueError(f"search mode {mode} only supports {allowed}; received {k!r}.")

    if k in ("smiles", "inchi"):
        return "inchikey", convert_to_inchikey(v, k)
    # normalize alias (leave actual API mapping to HTTP client)
    return k, v
