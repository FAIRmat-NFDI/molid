from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


# Properties to request from the Property endpoint.
# IMPORTANT: Do NOT include "CID" here. PubChem returns CID automatically.
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

_TIMEOUT = 15

def _ns_for_id_type(id_type: str) -> str:
    """Map our id_type to PubChem's namespace segment."""
    t = id_type.lower()
    return {
        # direct namespaces
        "cid": "cid",
        "inchikey": "inchikey",
        "inchi": "inchi",
        "smiles": "smiles",
        "name": "name",
        "molecularformula": "formula",
        # special cases
        "cas": "xref/rn",
    }.get(t, t)

def _fetch_cas_rn_by_cid(cid: int) -> list[str]:
    """
    Return a list of CAS Registry Numbers (RN) associated with a CID using PUG xrefs.
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
    r = requests.get(url, timeout=_TIMEOUT)
    if not r.ok:
        return []
    try:
        info = r.json().get("InformationList", {}).get("Information", [])
        if not info:
            return []
        rns = info[0].get("RN") or []
        if isinstance(rns, str):
            return [rns]
        return [s for s in rns if isinstance(s, str)]
    except Exception:
        return []

def _is_cas_rn(candidate: str) -> bool:
    """
    Validate CAS RN checksum (NNNNNNN-NN-N). Keeps parity with v2.py logic.
    """
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
    r = requests.get(url, timeout=_TIMEOUT)
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
    r = requests.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json().get("PropertyTable", {}).get("Properties", []) or []

def _fetch_iupac_from_pugview(cid: int) -> str | None:
    """
    Fallback when the Property endpoint omits IUPACName.
    Strategy:
      1) Try heading-filtered PUG-View (?heading=IUPAC Name) without raising on 404/400.
      2) Scan the full PUG-View record recursively for any of:
         - TOCHeading in {"Preferred IUPAC Name","IUPAC Name","Systematic Name"}
         - Information['Name'] exactly one of those targets
         Values may appear under Value.StringWithMarkup, Value.String, or Value.StringList.
    """
    # 1) Narrow "heading" call — tolerate 404s/400s without raising
    heading_url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON/"
        f"?heading=IUPAC%20Name"
    )
    r = requests.get(heading_url, timeout=_TIMEOUT)
    if r.ok:
        try:
            data = r.json()
            rec = data.get("Record", {})
            for sec in rec.get("Section", []) or []:
                if sec.get("TOCHeading") == "IUPAC Name":
                    for info in sec.get("Information", []) or []:
                        val = (info.get("Value") or {})
                        swm = val.get("StringWithMarkup") or []
                        if isinstance(swm, list) and swm and isinstance(swm[0], dict):
                            s = (swm[0].get("String") or "").strip()
                            if s:
                                return s
        except Exception:
            pass
    elif r.status_code not in (400, 404):
        # Other client/server errors should still surface
        r.raise_for_status()

    # 2) Full record fetch  recursive scan
    full_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    r2 = requests.get(full_url, timeout=_TIMEOUT)
    r2.raise_for_status()
    payload = r2.json()

    targets = {"Preferred IUPAC Name", "IUPAC Name", "Systematic Name"}

    def _from_info(info: dict) -> str | None:
        val = info.get("Value") or {}
        swm = val.get("StringWithMarkup")
        s = ""
        if isinstance(swm, list) and swm and isinstance(swm[0], dict):
            s = (swm[0].get("String") or "").strip()
            if s:
                return s

        # StringList (pick first non-empty)
        sl = val.get("StringList") or []
        if isinstance(sl, list):
            for item in sl:
                si = (item or "").strip()
                if si:
                    return si
        return None

    def _walk(sections: list[dict]) -> str | None:
        for sec in sections or []:
            # Match on heading name
            if sec.get("TOCHeading") in targets:
                for info in sec.get("Information", []) or []:
                    s = _from_info(info)
                    if s:
                        return s
            # Match on Information['Name'] (some records name the entry, not the heading)
            for info in sec.get("Information", []) or []:
                if info.get("Name") in targets:
                    s = _from_info(info)
                    if s:
                        return s
            child = _walk(sec.get("Section", []) or [])
            if child:
                return child
        return None

    rec = payload.get("Record", {})
    return _walk(rec.get("Section", []) or [])

def fetch_molecule_data(
    id_type: str,
    id_value: str,
    properties: tuple[str, ...] = _DEFAULT_PROPERTIES,
) -> list[dict[str, Any]]:
    """
    Resolve identifier to CID (if needed), fetch properties, and
    fill in IUPACName from PUG-View if the Property endpoint omits it.
    """
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
            # Enrich with CAS if available
            rns = _fetch_cas_rn_by_cid(cid_int)
            if rns:
                # Prefer a syntactically valid RN; store the first valid one
                for rn in rns:
                    if _is_cas_rn(rn):
                        rec["CAS"] = rn
                        break
                # Fallback to first if none validate strictly
                rec.setdefault("CAS", rns[0])
        return props

    # Resolve -> CID(s)
    cids = _resolve_to_cids(id_type_lc, id_value)
    if not cids:
        return []

    cid = cids[0]
    props = _fetch_properties_by_cid(cid, properties)
    if props:
        rec = props[0]
        # Ensure CID present even though we didn’t request it explicitly
        rec.setdefault("CID", cid)
        if not rec.get("IUPACName"):
            iupac = _fetch_iupac_from_pugview(cid)
            if iupac:
                rec["IUPACName"] = iupac
            elif rec.get("Title"):
                # Final safeguard: prefer a non-empty value instead of None
                rec["IUPACName"] = rec["Title"]
        # Enrich with CAS if possible
        rns = _fetch_cas_rn_by_cid(cid)
        if rns:
            for rn in rns:
                if _is_cas_rn(rn):
                    rec["CAS"] = rn
                    break
            rec.setdefault("CAS", rns[0])
        # If query was by CAS, ensure we preserve it even if xrefs has multiple
        if id_type_lc == "cas":
            rec.setdefault("CAS", str(id_value))
    return props