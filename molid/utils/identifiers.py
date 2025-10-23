from __future__ import annotations
from typing import Any, Literal
import logging

from molid.utils.conversion import convert_to_inchikey

logger = logging.getLogger(__name__)

class UnsupportedIdentifierForMode(Exception):
    """Raised when a given identifier is not supported by the chosen search mode."""
    pass

_BASIC_ALLOWED   = ("cid", "title", "iupacname", "molecularformula", "inchi", "inchikey","smiles", "canonicalsmiles", "cas")
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
    if k in ("smiles", "canonicalsmiles", "isomericsmiles"):
        logger.debug('CanonicalSMILES, IsomericSMILES, SMILES and InChi are converted to InChiKey')
        return "inchikey", convert_to_inchikey(v, "smiles")

    if k == "inchi":
        return "inchikey", convert_to_inchikey(v, k)

    if k in ("formula", "molecularformula") and not any(ch.isupper() for ch in v):
        raise ValueError('Given formula has no upper character.')

    if k == "formula":
        return "molecularformula", v

    return k, v

