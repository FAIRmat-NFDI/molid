from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter, Retry

# ---- Tunables --------------------------------------------------------------

# Use a (connect, read) tuple so slow PubChem responses don’t fail tests.
_TIMEOUT: tuple[float, float] = (10.0, 35.0)

# Conservative retry policy: covers transient network and 5xx/429.
_RETRY = Retry(
    total=4,                # 1 original + 4 retries = up to 5 attempts
    connect=4,
    read=4,
    status=4,
    backoff_factor=0.7,     # ~0.7, 1.4, 2.1, 2.8s
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)

_session: requests.Session | None = None

def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=_RETRY))
        s.mount("http://",  HTTPAdapter(max_retries=_RETRY))
        _session = s
    return _session

# ---- Helpers ---------------------------------------------------------------

def _ns_for_id_type(id_type: str) -> str:
    t = id_type.lower()
    return {
        "cid": "cid",
        "inchikey": "inchikey",
        "inchi": "inchi",
        "smiles": "smiles",
        "name": "name",
        "molecularformula": "formula",
        "cas": "xref/rn",
    }.get(t, t)

def _fetch_cas_rn_by_cid(cid: int) -> list[str]:
    """
    Return CAS RNs for a CID. Network errors are treated as 'no data'
    (we don't want optional enrichment to fail the whole lookup).
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
    s = _get_session()
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

def _is_cas_rn(candidate: str) -> bool:
    import re
    m = re.fullmatch(r"(?P<p1>\d{2,7})-(?P<p2>\d{2})-(?P<check>\d{1})", candidate or "")
    if not m:
        return False
    digits = (m.group('p1') + m.group('p2'))[::-1]
    checksum = sum(int(c) * (i + 1) for i, c in enumerate(digits)) % 10
    return checksum == int(m.group('check'))

def _resolve_to_cids(id_type: str, id_value: str) -> list[int]:
    ns = _ns_for_id_type(id_type)
    safe_value = quote(str(id_value), safe="")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/{ns}/{safe_value}/cids/JSON"
    s = _get_session()
    r = s.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    obj = r.json()
    cids = (
        obj.get("IdentifierList", {}).get("CID")
        or obj.get("InformationList", {}).get("Information", [{}])[0].get("CID")
    )
    if not cids:
        return []
    return [int(c) for c in (cids if isinstance(cids, list) else [cids])]

def _fetch_properties_by_cid(cid: int, properties: tuple[str, ...]) -> list[dict[str, Any]]:
    props_str = ",".join(properties)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/{props_str}/JSON"
    s = _get_session()
    r = s.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json().get("PropertyTable", {}).get("Properties", []) or []

def _fetch_iupac_from_pugview(cid: int) -> str | None:
    s = _get_session()
    # 1) Heading-filtered call (don’t raise on 400/404)
    heading_url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON/?heading=IUPAC%20Name"
    )
    try:
        r = s.get(heading_url, timeout=_TIMEOUT)
        if r.ok:
            data = r.json()
            rec = data.get("Record", {})
            for sec in rec.get("Section", []) or []:
                if sec.get("TOCHeading") == "IUPAC Name":
                    for info in sec.get("Information", []) or []:
                        val = (info.get("Value") or {})
                        swm = val.get("StringWithMarkup") or []
                        if isinstance(swm, list) and swm and isinstance(swm[0], dict):
                            s0 = (swm[0].get("String") or "").strip()
                            if s0:
                                return s0
    except requests.RequestException:
        pass
    # 2) Full record
    r2 = s.get(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON", timeout=_TIMEOUT)
    r2.raise_for_status()
    payload = r2.json()

    targets = {"Preferred IUPAC Name", "IUPAC Name", "Systematic Name"}

    def _from_info(info: dict) -> str | None:
        val = info.get("Value") or {}
        swm = val.get("StringWithMarkup")
        if isinstance(swm, list) and swm and isinstance(swm[0], dict):
            s0 = (swm[0].get("String") or "").strip()
            if s0:
                return s0
        sl = val.get("StringList") or []
        if isinstance(sl, list):
            for item in sl:
                si = (item or "").strip()
                if si:
                    return si
        return None

    def _walk(sections: list[dict]) -> str | None:
        for sec in sections or []:
            if sec.get("TOCHeading") in targets:
                for info in sec.get("Information", []) or []:
                    s1 = _from_info(info)
                    if s1:
                        return s1
            for info in sec.get("Information", []) or []:
                if info.get("Name") in targets:
                    s2 = _from_info(info)
                    if s2:
                        return s2
            child = _walk(sec.get("Section", []) or [])
            if child:
                return child
        return None

    rec = payload.get("Record", {})
    return _walk(rec.get("Section", []) or [])

# Default properties — unchanged
_DEFAULT_PROPERTIES: tuple[str, ...] = (
    "Title",
    "IUPACName",
    "MolecularFormula",
    "InChI",
    "InChIKey",
    "ConnectivitySMILES",
    "SMILES",
    "XLogP",
    "ExactMass",
    "MonoisotopicMass",
    "TPSA",
    "Complexity",
    "Charge",
)

def fetch_molecule_data(
    id_type: str,
    id_value: str,
    properties: tuple[str, ...] = _DEFAULT_PROPERTIES,
) -> list[dict[str, Any]]:
    id_type_lc = id_type.lower()

    if id_type_lc == "cid":
        try:
            cid_int = int(str(id_value).strip())
        except ValueError:
            raise ValueError(f"Invalid CID value: {id_value!r}")
        props = _fetch_properties_by_cid(cid_int, properties)
        if props:
            rec = props[0]
            if not rec.get("IUPACName"):
                iupac = _fetch_iupac_from_pugview(cid_int)
                if iupac:
                    rec["IUPACName"] = iupac
            rns = _fetch_cas_rn_by_cid(cid_int)
            if rns:
                for rn in rns:
                    if _is_cas_rn(rn):
                        rec["CAS"] = rn
                        break
                rec.setdefault("CAS", rns[0])
        return props

    cids = _resolve_to_cids(id_type_lc, id_value)
    if not cids:
        return []

    cid = cids[0]
    props = _fetch_properties_by_cid(cid, properties)
    if props:
        rec = props[0]
        rec.setdefault("CID", cid)
        if not rec.get("IUPACName"):
            iupac = _fetch_iupac_from_pugview(cid)
            if iupac:
                rec["IUPACName"] = iupac
            elif rec.get("Title"):
                rec["IUPACName"] = rec["Title"]
        rns = _fetch_cas_rn_by_cid(cid)
        if rns:
            for rn in rns:
                if _is_cas_rn(rn):
                    rec["CAS"] = rn
                    break
            rec.setdefault("CAS", rns[0])
        if id_type_lc == "cas":
            rec.setdefault("CAS", str(id_value))
    return props
