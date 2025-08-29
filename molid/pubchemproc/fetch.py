# molid/pubchemproc/fetch.py
from __future__ import annotations
from typing import Any

from molid.pubchemproc.pubchem_client import (
    resolve_to_cids,
    get_properties,
    get_pugview,
    get_xrefs_rn,
)

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

def _is_cas_rn(candidate: str) -> bool:
    import re
    m = re.fullmatch(r"(?P<p1>\d{2,7})-(?P<p2>\d{2})-(?P<check>\d{1})", candidate or "")
    if not m:
        return False
    digits = (m.group('p1') + m.group('p2'))[::-1]
    checksum = sum(int(c) * (i + 1) for i, c in enumerate(digits)) % 10
    return checksum == int(m.group('check'))

def _fetch_iupac_from_pugview(cid: int) -> str | None:
    # 1) try heading-filtered
    data = get_pugview(cid, heading="IUPAC Name")
    try:
        if data:
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
    # 2) full record
    payload = get_pugview(cid)
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

    rec = (payload or {}).get("Record", {})
    return _walk(rec.get("Section", []) or [])

def fetch_molecule_data(
    id_type: str,
    id_value: str,
    properties: tuple[str, ...] = _DEFAULT_PROPERTIES,
) -> list[dict[str, Any]]:
    """
    Resolve identifier to CID (if needed), fetch properties,
    fill IUPAC via PUG-View if missing, and enrich with CAS if available.
    """
    if id_type.lower() == "cid":
        try:
            cid_int = int(str(id_value).strip())
        except ValueError:
            raise ValueError(f"Invalid CID value: {id_value!r}")
        props = get_properties(cid_int, properties)
        if props:
            rec = props[0]
            if not rec.get("IUPACName"):
                iupac = _fetch_iupac_from_pugview(cid_int)
                if iupac:
                    rec["IUPACName"] = iupac
            rns = get_xrefs_rn(cid_int)
            if rns:
                for rn in rns:
                    if _is_cas_rn(rn):
                        rec["CAS"] = rn
                        break
                rec.setdefault("CAS", rns[0])
        return props

    cids = resolve_to_cids(id_type, id_value)
    if not cids:
        return []

    cid = cids[0]
    props = get_properties(cid, properties)
    if props:
        rec = props[0]
        rec.setdefault("CID", cid)
        if not rec.get("IUPACName"):
            iupac = _fetch_iupac_from_pugview(cid)
            if iupac:
                rec["IUPACName"] = iupac
            elif rec.get("Title"):
                rec["IUPACName"] = rec["Title"]
        rns = get_xrefs_rn(cid)
        if rns:
            for rn in rns:
                if _is_cas_rn(rn):
                    rec["CAS"] = rn
                    break
            rec.setdefault("CAS", rns[0])
        if id_type.lower() == "cas":
            rec.setdefault("CAS", str(id_value))
    return props
