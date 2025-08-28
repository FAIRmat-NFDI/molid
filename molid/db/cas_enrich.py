from __future__ import annotations
import time
from typing import Iterable
import requests
from requests.adapters import HTTPAdapter, Retry
from molid.db.sqlite_manager import DatabaseManager

_TIMEOUT = 30

def _make_session(retries: int) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
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
        r = session.get(url, timeout=timeout)
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
        r = session.get(url, timeout=timeout)
        if not r.ok:
            return []
    except requests.RequestException:
        return []
    try:
        info = r.json().get("InformationList", {}).get("Information", [])
        syns = (info[0].get("Synonym") if info else []) or []
        # Flatten and filter to strings
        return [s for s in syns if isinstance(s, str)]
    except Exception:
        return []

def enrich_cas_for_cids(
    db_file: str,
    cids: Iterable[int],
    sleep_s: float = 0.2,
    use_synonyms: bool = False,
    timeout_s: float = _TIMEOUT,
    retries: int = 3,
) -> int:
    """
    For each CID, fetch CAS RNs and insert into cas_mapping with confidence flags.
    Returns count of (CAS,CID) rows upserted.
    """
    db = DatabaseManager(db_file)
    session = _make_session(retries=retries)
    upserts = 0
    for cid in cids:
        # 1) Authoritative xref/RN
        rns = _fetch_cas_by_cid(cid, session=session, timeout=timeout_s)
        for rn in rns:
            conf = 2 if _is_cas_rn(rn) else 1
            db.execute(
                "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
                [rn, cid, "xref", conf]
            )
            upserts += 1
        # 2) Optional heuristic from synonyms (validated by checksum)
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
