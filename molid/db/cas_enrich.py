from __future__ import annotations
import time
import os
from typing import Iterable
from molid.db.sqlite_manager import DatabaseManager
from molid.pubchemproc.pubchem_client import get_session

from requests.adapters import HTTPAdapter, Retry
import requests

_TIMEOUT = float(os.getenv("MOLID_CAS_TIMEOUT", "30"))
_RETRIES = int(os.getenv("MOLID_CAS_RETRIES", "3"))

def _make_session(retries: int) -> requests.Session:
    s = get_session()  # reuse shared session (already retried)
    # Optionally extend with CAS-specific retries if caller asked for more
    if retries > 0:
        s.mount("https://", HTTPAdapter(max_retries=Retry(
            total=retries, connect=retries, read=retries, status=retries,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )))
    return s

def _is_cas_rn(s: str) -> bool:
    import re
    m = re.fullmatch(r"(\d{2,7})-(\d{2})-(\d)", (s or "").strip())
    if not m: return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum(int(c) * (i+1) for i, c in enumerate(digits)) % 10 == int(m.group(3))

def _fetch_cas_by_cid(cid: int, session: requests.Session, timeout: float) -> list[str]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
    try:
        r = session.get(url, timeout=(10, timeout))
        if not r.ok:
            return []
    except requests.RequestException:
        return []
    try:
        info = r.json().get("InformationList", {}).get("Information", [])
        rns = (info[0].get("RN") if info else []) or []
        return [rns] if isinstance(rns, str) else [s for s in rns if isinstance(s, str)]
    except Exception:
        return []

def _fetch_synonyms(cid: int, session: requests.Session, timeout: float) -> list[str]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    try:
        r = session.get(url, timeout=(10, timeout))
        if not r.ok:
            return []
    except requests.RequestException:
        return []
    try:
        info = r.json().get("InformationList", {}).get("Information", [])
        syns = (info[0].get("Synonym") if info else []) or []
        return [s for s in syns if isinstance(s, str)]
    except Exception:
        return []

def enrich_cas_for_cids(
    db_file: str,
    cids: Iterable[int],
    sleep_s: float = 0.2,
    use_synonyms: bool = False,
    timeout_s: float = _TIMEOUT,
    retries: int = _RETRIES,
) -> int:
    """For each CID, fetch CAS RNs and insert into cas_mapping with confidence flags."""
    db = DatabaseManager(db_file)
    session = _make_session(retries=retries)
    upserts = 0
    for cid in cids:
        rns = _fetch_cas_by_cid(cid, session=session, timeout=timeout_s)
        for rn in rns:
            conf = 2 if _is_cas_rn(rn) else 1
            db.execute(
                "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
                [rn, cid, "xref", conf]
            )
            upserts += 1

        if use_synonyms:
            syns = _fetch_synonyms(cid, session=session, timeout=timeout_s)
            for s in syns:
                if _is_cas_rn(s):
                    db.execute(
                        "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
                        [s, cid, "synonym", 2]
                    )
                    upserts += 1
        time.sleep(sleep_s)
    return upserts
