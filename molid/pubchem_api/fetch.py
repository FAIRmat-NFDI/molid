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
        "cas": "xrefs/rn",
    }.get(t, t)


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
        if isinstance(swm, list) and swm and isinstance(swm[0], dict):
            s = (swm[0].get("String") or "").strip()
            if s:
                return s
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
    return props