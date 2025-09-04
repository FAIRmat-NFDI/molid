# molid/utils/identifiers.py
from __future__ import annotations
from typing import Any, Literal

from molid.utils.conversion import convert_to_inchikey

class UnsupportedIdentifierForMode(Exception):
    """Raised when a given identifier is not supported by the chosen search mode."""
    pass

_BASIC_ALLOWED   = ("inchikey", "inchi", "smiles")
_ADV_ALLOWED     = ("cid", "name", "smiles", "inchi", "inchikey", "molecularformula", "cas")

def normalize_query(
    query: dict[str, Any],
    mode: Literal["basic","advanced"]
) -> tuple[str, Any]:
    if not isinstance(query, dict) or len(query) != 1:
        raise ValueError("Expected a dict with exactly one identifier.")
    k, v = next(iter(((k.lower(), val) for k, val in query.items())))
    allowed = _BASIC_ALLOWED if mode == "basic" else _ADV_ALLOWED
    if k not in allowed:
        # 👇 key change: raise a soft, *expected* signal for the dispatcher
        raise UnsupportedIdentifierForMode(
            f"Mode {mode} supports {allowed}; received {k!r}."
        )

    if k in ("smiles", "inchi"):
        return "inchikey", convert_to_inchikey(v, k)
    return k, v

