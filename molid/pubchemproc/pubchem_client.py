# molid/pubchemproc/pubchem_client.py
from __future__ import annotations

import os
import requests
from typing import Any
from urllib.parse import quote

from requests.adapters import HTTPAdapter, Retry
from molid.db.schema import NUMERIC_FIELDS
from molid.utils.conversion import coerce_numeric_fields

# -------- Tunables (env-overridable, no hard dependency on settings.py) -----
_CONNECT_TIMEOUT = float(os.getenv("MOLID_HTTP_CONNECT_TIMEOUT", "10"))
_READ_TIMEOUT = float(os.getenv("MOLID_HTTP_READ_TIMEOUT", "35"))
_TIMEOUT = (_CONNECT_TIMEOUT, _READ_TIMEOUT)

_RETRIES = int(os.getenv("MOLID_HTTP_RETRIES", "4"))
_BACKOFF = float(os.getenv("MOLID_HTTP_BACKOFF", "0.7"))

_RETRY = Retry(
    total=_RETRIES,
    connect=_RETRIES,
    read=_RETRIES,
    status=_RETRIES,
    backoff_factor=_BACKOFF,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Shared, retried Session for all PubChem calls."""
    global _session
    if _session is None:
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=_RETRY))
        s.mount("http://", HTTPAdapter(max_retries=_RETRY))
        _session = s
    return _session


# ----------------------------- Namespace helpers ----------------------------


def ns_for_id_type(id_type: str) -> str:
    t = id_type.lower()
    return {
        "cid": "cid",
        "inchikey": "inchikey",
        "inchi": "inchi",
        "smiles": "smiles",
        "canonicalsmiles": "smiles",
        "isomericsmiles": "smiles",
        "name": "name",
        "molecularformula": "formula",
        "cas": "xref/rn",
    }.get(t, t)


# ------------------------------- High-level API -----------------------------


def resolve_to_cids(id_type: str, id_value: str) -> list[int]:
    """
    Resolve an identifier to PubChem CIDs.

    Adds a robust fallback path for InChI:
      - try GET with full value
      - try GET without 'InChI=' prefix
      - try POST form 'inchi=<string>'
    """
    key = (id_type or "").strip().lower()
    s = get_session()

    # Fast path for molecular formula (unchanged)
    if key in ("molecularformula", "formula"):
        safe_value = quote(str(id_value).strip(), safe="")
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/fastformula/{safe_value}/cids/JSON"
        r = s.get(url, timeout=_TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        obj = r.json()
        cids = obj.get("IdentifierList", {}).get("CID") or obj.get(
            "InformationList", {}
        ).get("Information", [{}])[0].get("CID")
        if not cids:
            return []
        return [int(c) for c in (cids if isinstance(cids, list) else [cids])]

    # All other ID types → existing namespace
    ns = ns_for_id_type(key)

    def _extract_cids(obj: dict) -> list[int]:
        c = obj.get("IdentifierList", {}).get("CID") or obj.get(
            "InformationList", {}
        ).get("Information", [{}])[0].get("CID")
        if not c:
            return []
        if not isinstance(c, list):
            c = [c]
        return [int(v) for v in c]

    val = str(id_value).strip()

    # InChI: be extra robust
    if key == "inchi":
        # 1) GET with full value
        for candidate in (val, val[6:] if val.startswith("InChI=") else None):
            if not candidate:
                continue
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchi/{quote(candidate, safe='')}/cids/JSON"
            r = s.get(url, timeout=_TIMEOUT)
            if r.status_code == 404:
                # try next variant
                continue
            if r.status_code == 400:
                # try next variant
                continue
            r.raise_for_status()
            cids = _extract_cids(r.json())
            if cids:
                return cids

        # 2) POST body form (most reliable)
        #    Accept both raw and prefix-stripped variants
        for candidate in (val, val[6:] if val.startswith("InChI=") else None):
            if not candidate:
                continue
            url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchi/cids/JSON"
            r = s.post(url, data={"inchi": candidate}, timeout=_TIMEOUT)
            if r.status_code == 404:
                continue
            if r.status_code == 400:
                continue
            r.raise_for_status()
            cids = _extract_cids(r.json())
            if cids:
                return cids

        return []  # nothing worked; let upper layers fall through

    # Default path (inchikey, smiles, name, cas, cid…)
    safe_value = quote(val, safe="")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/{ns}/{safe_value}/cids/JSON"
    r = s.get(url, timeout=_TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return _extract_cids(r.json())


def get_properties(cid: int, properties: tuple[str, ...]) -> list[dict[str, Any]]:
    props_str = ",".join(properties)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/{props_str}/JSON"
    s = get_session()
    r = s.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    record = r.json().get("PropertyTable", {}).get("Properties", []) or []
    cleaned_records = [coerce_numeric_fields(item, NUMERIC_FIELDS) for item in record]
    return cleaned_records


def get_pugview(cid: int, heading: str | None = None) -> dict[str, Any] | None:
    base = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    url = base if not heading else f"{base}/?heading={quote(heading)}"
    s = get_session()
    r = s.get(url, timeout=_TIMEOUT)
    if heading:
        # tolerate 400/404 on heading-optimized calls
        if not r.ok:
            return None
        try:
            return r.json()
        except Exception:
            return None
    r.raise_for_status()
    return r.json()


def get_xrefs_rn(cid: int) -> list[str]:
    """Return CAS RNs; network problems return [] (non-fatal enrichment)."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
    s = get_session()
    try:
        r = s.get(url, timeout=_TIMEOUT)
        if not r.ok:
            return []
        info = r.json().get("InformationList", {}).get("Information", [])
        if not info:
            return []
        rns = info[0].get("RN") or []
        if isinstance(rns, str):
            return [rns]
        return [s for s in rns if isinstance(s, str)]
    except requests.RequestException:
        return []
    except Exception:
        return []


def get_synonyms(cid: int) -> list[str]:
    """Return PubChem synonyms (StringList). Empty on transient/404."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    s = get_session()
    try:
        r = s.get(url, timeout=_TIMEOUT)
        if not r.ok:
            return []
        info = r.json().get("InformationList", {}).get("Information", [])
        if not info:
            return []
        syns = info[0].get("Synonym") or []
        return [s for s in syns if isinstance(s, str)]
    except requests.RequestException:
        return []
    except Exception:
        return []
