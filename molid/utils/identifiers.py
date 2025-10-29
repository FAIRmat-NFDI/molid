from __future__ import annotations
from typing import Any, Literal
import logging

logger = logging.getLogger(__name__)

class UnsupportedIdentifierForMode(Exception):
    """Raised when a given identifier is not supported by the chosen search mode."""
    pass

_BASIC_ALLOWED   = ("cid", "title", "iupacname", "molecularformula", "inchi", "inchikey","smiles", "canonicalsmiles", "isomericsmiles", "cas")
_ADV_ALLOWED     = _BASIC_ALLOWED + ("isomericsmiles",)


def normalize_query(
    query: dict[str, Any],
    mode: Literal["basic","advanced"]
) -> tuple[str, Any]:
    if not isinstance(query, dict) or len(query) != 1:
        raise ValueError("Expected a dict with exactly one identifier.")
    k, v = next(iter(((k.lower(), val) for k, val in query.items())))
    allowed = _BASIC_ALLOWED if mode == "basic" else _ADV_ALLOWED
    if k not in allowed:
        # raise a soft, *expected* signal for the dispatcher
        raise UnsupportedIdentifierForMode(
            f"Mode {mode} supports {allowed}; received {k!r}."
        )

    if k == "smiles":
        return "canonicalsmiles", v
    if k == "isomericsmiles":
        # master DB doesn't have IsomericSMILES; map to CanonicalSMILES for basic
        return ("canonicalsmiles" if mode == "basic" else "isomericsmiles"), v

    if k in ("formula", "molecularformula"):
        if k == "formula" and not any(ch.isupper() for ch in v):
            raise ValueError('Given formula has no upper character.')
        return "molecularformula", v

    return k, v

