# molid/db/cas_enrich.py
from __future__ import annotations

import os
import re
import time
import sqlite3
from typing import Iterable, Dict, List, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm

from molid.db.sqlite_manager import DatabaseManager
from molid.pubchemproc.pubchem_client import get_session

# =========================
# Tunables / Env overrides
# =========================

_TIMEOUT = float(os.getenv("MOLID_CAS_TIMEOUT", "10"))
_RETRIES = int(os.getenv("MOLID_CAS_RETRIES", "4"))
BATCH_SIZE = int(os.getenv("MOLID_CAS_BATCH_SIZE", "300"))  # CIDs per network call
MAX_WORKERS = int(os.getenv("MOLID_CAS_MAX_WORKERS", "6"))  # concurrent batch calls
FLUSH_EVERY = int(os.getenv("MOLID_CAS_FLUSH_EVERY", "50000"))  # rows before DB flush
SLEEP_BETWEEN = float(
    os.getenv("MOLID_CAS_SLEEP", "0.0")
)  # optional pause per finished batch

# =========================
# CAS helpers / validation
# =========================

_CAS_RE = re.compile(r"(\d{2,7})-(\d{2})-(\d)$")


def _is_cas_rn(s: str) -> bool:
    m = _CAS_RE.fullmatch((s or "").strip())
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    checksum = sum(int(c) * (i + 1) for i, c in enumerate(digits)) % 10
    return checksum == int(m.group(3))


# =========================
# Network / Session
# =========================


def _make_session(retries: int) -> requests.Session:
    """
    Reuse the shared session and add compression + extra retries if requested.
    """
    s = get_session()  # already has a Retry adapter mounted
    s.headers.update({"Accept-Encoding": "gzip, deflate"})
    if retries > 0:
        s.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(
                    total=retries,
                    connect=retries,
                    read=retries,
                    status=retries,
                    backoff_factor=0.8,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset(["GET"]),
                    raise_on_status=False,
                )
            ),
        )
    return s


def _fetch_rn_batch(
    session: requests.Session, cids: List[int], timeout: float
) -> Dict[int, List[str]]:
    """
    Fetch CAS RN lists for a batch of CIDs via a single PUG REST call.
    Returns {cid: [RN, ...]}.
    """
    result: Dict[int, List[str]] = {}
    if not cids:
        return result
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{quote(','.join(map(str, cids)), safe=',')}/xrefs/RN/JSON"
    try:
        r = session.get(url, timeout=(10, timeout))
        if not r.ok:
            return result
        obj = r.json()
        info_list = (obj.get("InformationList", {}) or {}).get("Information", []) or []
        for item in info_list:
            cid = item.get("CID")
            rns = item.get("RN") or []
            if isinstance(rns, str):
                rns = [rns]
            if isinstance(cid, int) and rns:
                result[cid] = [s for s in rns if isinstance(s, str)]
    except requests.RequestException:
        return {}
    return result


# =========================
# Data prep / batching
# =========================


def _chunk(iterable: List[int], size: int) -> List[List[int]]:
    return [iterable[i : i + size] for i in range(0, len(iterable), size)]


def _filter_cids_missing_mapping(db: DatabaseManager, cids: List[int]) -> List[int]:
    """
    Return only CIDs that do not yet appear in cas_mapping (any CAS present).
    """
    if not cids:
        return cids
    out: List[int] = []
    CH = 999  # keep well under SQLite param limits
    for i in range(0, len(cids), CH):
        sub = cids[i : i + CH]
        placeholders = ",".join("?" for _ in sub)
        rows = db.query_all(
            f"""
            SELECT cd.CID, COUNT(cm.CAS) AS n
            FROM compound_data cd
            LEFT JOIN cas_mapping cm ON cm.CID = cd.CID
            WHERE cd.CID IN ({placeholders})
            GROUP BY cd.CID
            """,
            sub,
        )
        for r in rows:
            if int(r.get("n") or 0) == 0:
                out.append(int(r["CID"]))
    return out


# =========================
# Bulk DB operations
# =========================


def _bulk_upsert_cas(db_path: str, rows: List[Tuple[str, int, str, int]]) -> int:
    """
    Bulk INSERT OR IGNORE rows into cas_mapping.
    rows are (CAS, CID, source, confidence).
    Returns number of changes (best effort).
    """
    if not rows:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executemany(
            "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
            rows,
        )
        return conn.total_changes


def _flush_if_needed(
    db_path: str, buffer: List[Tuple[str, int, str, int]], threshold: int
) -> int:
    if len(buffer) >= threshold:
        changed = _bulk_upsert_cas(db_path, buffer)
        buffer.clear()
        return changed
    return 0


# =========================
# Post-processing
# =========================


def _detect_main_table(conn) -> str:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0].lower() for r in rows}
    if "compound_data" in names:
        return "compound_data"
    if "cached_molecules" in names:
        return "cached_molecules"
    raise RuntimeError("Neither compound_data nor cached_molecules table found.")


GENERIC_HINTS = re.compile(
    r"(poly|copolymer|oligomer|resin|mixture|blend|grade|uvcb|"
    r"natural\s+oil|extract|essence|unspecified|trade\s+name)",
    re.IGNORECASE,
)


def _downgrade_generic_cas(db: DatabaseManager, cas_values: Iterable[str]) -> None:
    """
    Mark generic CAS (confidence=0) in bulk, using a single connection and set-based SQL.
    Heuristics:
      • Multi-chemistry: >1 distinct InChIKey14 or >1 distinct formula or any missing/empty formula
      • Text hints in Title/IUPACName (poly, mixture, resin, etc.)
    Applies only to the CAS touched in this enrichment run.
    """
    cas_list = list({c for c in cas_values if c})
    if not cas_list:
        return

    CHUNK = 50_000  # avoid oversized temp tables on huge runs
    # Could be added later for mark generic CAS numbers
    # KEYWORD_SQL = (
    #     "%poly% OR %copolymer% OR %oligomer% OR %resin% OR %mixture% OR %blend% OR "
    #     "%grade% OR %uvcb% OR %natural oil% OR %extract% OR %essence% OR %unspecified% OR %trade name%"
    # )

    with sqlite3.connect(db.db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        main = _detect_main_table(conn)  # NEW

        for start in range(0, len(cas_list), CHUNK):
            chunk = cas_list[start : start + CHUNK]
            conn.execute("DROP TABLE IF EXISTS _affected_cas")
            conn.execute("CREATE TEMP TABLE _affected_cas (CAS TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT OR IGNORE INTO _affected_cas(CAS) VALUES (?)",
                ((c,) for c in chunk),
            )

            # 1) multi-chemistry / missing-formula
            conn.execute(f"""
                UPDATE cas_mapping
                SET confidence = 0
                WHERE CAS IN (
                SELECT cm.CAS
                FROM cas_mapping cm
                JOIN {main} cd ON cd.CID = cm.CID
                JOIN _affected_cas ac ON ac.CAS = cm.CAS
                GROUP BY cm.CAS
                HAVING
                    COUNT(DISTINCT substr(cd.InChIKey,1,14)) > 1
                    OR COUNT(DISTINCT cd.MolecularFormula)      > 1
                    OR SUM(CASE
                            WHEN cd.MolecularFormula IS NULL
                                OR TRIM(cd.MolecularFormula) IN ('','N/A','NA','?')
                            THEN 1 ELSE 0 END) > 0
                )
            """)

            # 2) polymer/mixture keyword hints
            conn.execute(f"""
                UPDATE cas_mapping
                SET confidence = 0
                WHERE CAS IN (
                SELECT DISTINCT cm.CAS
                FROM cas_mapping cm
                JOIN {main} cd ON cd.CID = cm.CID
                JOIN _affected_cas ac ON ac.CAS = cm.CAS
                WHERE (cd.Title     LIKE '%poly%' OR cd.IUPACName LIKE '%poly%')
                    OR (cd.Title     LIKE '%copolymer%' OR cd.IUPACName LIKE '%copolymer%')
                    OR (cd.Title     LIKE '%oligomer%' OR cd.IUPACName LIKE '%oligomer%')
                    OR (cd.Title     LIKE '%resin%' OR cd.IUPACName LIKE '%resin%')
                    OR (cd.Title     LIKE '%mixture%' OR cd.IUPACName LIKE '%mixture%')
                    OR (cd.Title     LIKE '%blend%' OR cd.IUPACName LIKE '%blend%')
                    OR (cd.Title     LIKE '%grade%' OR cd.IUPACName LIKE '%grade%')
                    OR (cd.Title     LIKE '%uvcb%' OR cd.IUPACName LIKE '%uvcb%')
                    OR (cd.Title     LIKE '%natural oil%' OR cd.IUPACName LIKE '%natural oil%')
                    OR (cd.Title     LIKE '%extract%' OR cd.IUPACName LIKE '%extract%')
                    OR (cd.Title     LIKE '%essence%' OR cd.IUPACName LIKE '%essence%')
                    OR (cd.Title     LIKE '%unspecified%' OR cd.IUPACName LIKE '%unspecified%')
                    OR (cd.Title     LIKE '%trade name%' OR cd.IUPACName LIKE '%trade name%')
                )
            """)
        conn.commit()


def _update_best_cas_for_cids(db: DatabaseManager, cids: Iterable[int]) -> None:
    cid_list = list({int(c) for c in cids if c is not None})
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # If caller didn't pass any CIDs (or they got filtered away),
        # update for all CIDs that appear in cas_mapping.
        if not cid_list:
            rows = conn.execute("SELECT DISTINCT CID FROM cas_mapping").fetchall()
            cid_list = [int(r[0]) for r in rows]

        if not cid_list:
            return

        conn.execute("CREATE TEMP TABLE _affected (CID INTEGER PRIMARY KEY)")
        conn.executemany(
            "INSERT OR IGNORE INTO _affected(CID) VALUES (?)", ((c,) for c in cid_list)
        )
        conn.execute("""
        UPDATE compound_data
        SET CAS = (
          SELECT cm.CAS
          FROM cas_mapping cm
          WHERE cm.CID = compound_data.CID
            AND cm.confidence > 0
          ORDER BY (cm.source='synonym') DESC,
                   cm.confidence DESC,
                   CAST(substr(cm.CAS, 1, instr(cm.CAS,'-')-1) AS INTEGER) ASC,
                   cm.CAS ASC
          LIMIT 1
        )
        WHERE CID IN (SELECT CID FROM _affected);
        """)
        conn.execute("DROP TABLE _affected")
        conn.commit()


# =========================
# Batch fetching (orchestrated)
# =========================


def _fetch_all_batches(
    session: requests.Session,
    batches: List[List[int]],
    timeout_s: float,
    max_workers: int,
    progress_desc: str = "Fetching CAS",
) -> Tuple[Dict[int, List[str]], int]:
    """
    Run batched fetches concurrently and aggregate to {cid: [rns]}.
    Returns (mapping, completed_batches).
    """
    mapping_all: Dict[int, List[str]] = {}
    completed = 0
    with tqdm(
        total=len(batches), desc=progress_desc, unit="batch", dynamic_ncols=True
    ) as pbar:
        with ThreadPoolExecutor(
            max_workers=max_workers if max_workers > 1 else None
        ) as ex:
            future_map = {
                ex.submit(_fetch_rn_batch, session, b, timeout_s): tuple(b)
                for b in batches
            }
            for fut in as_completed(future_map):
                try:
                    got = fut.result() or {}
                except Exception:
                    got = {}
                for cid, rns in got.items():
                    if rns:
                        mapping_all[cid] = rns
                completed += 1
                pbar.update(1)
                if SLEEP_BETWEEN > 0:
                    time.sleep(SLEEP_BETWEEN)
    return mapping_all, completed


def _prepare_insert_rows(
    cid_to_rns: Dict[int, List[str]],
) -> Tuple[List[Tuple[str, int, str, int]], Set[int], Set[str]]:
    """
    Convert mapping to DB rows and collect affected CIDs/CAS.
    Filters to valid CAS and sets confidence=2 (checksum-valid).
    """
    rows: List[Tuple[str, int, str, int]] = []
    affected_cids: Set[int] = set()
    affected_cas: Set[str] = set()
    for cid, rns in cid_to_rns.items():
        valid = [rn for rn in rns if _is_cas_rn(rn)]
        if not valid:
            continue
        affected_cids.add(cid)
        for rn in valid:
            affected_cas.add(rn)
            rows.append((rn, cid, "xref", 2))
    return rows, affected_cids, affected_cas


# =========================
# Public API
# =========================


def enrich_cas_for_cids(
    db_file: str,
    cids: Iterable[int],
    sleep_s: float = 0.0,  # kept for API compat; not used in batched path
    use_synonyms: bool = False,  # kept for API compat; no-op here
    timeout_s: float = _TIMEOUT,
    retries: int = _RETRIES,
    batch_size: int = BATCH_SIZE,
    max_workers: int = MAX_WORKERS,
    only_missing: bool = True,
) -> int:
    """
    Enrich CAS mapping for the given CIDs, quickly:
      • Filter to missing (optional).
      • Batch + concurrent fetch of /xrefs/RN.
      • Bulk insert (INSERT OR IGNORE) in large WAL transactions.
      • Mark generic CAS (confidence=0).
      • Update best CAS per affected CID.

    Returns the number of inserted (CAS, CID) pairs (approximate; due to IGNORE).
    """
    session = _make_session(retries=retries)
    db = DatabaseManager(db_file)

    all_cids = list(int(c) for c in cids)
    if only_missing:
        all_cids = _filter_cids_missing_mapping(db, all_cids)
    if not all_cids:
        return 0

    batches = _chunk(all_cids, batch_size)
    cid_to_rns, _ = _fetch_all_batches(
        session=session,
        batches=batches,
        timeout_s=timeout_s,
        max_workers=max_workers,
        progress_desc=f"Enriching CAS (batch={batch_size}, workers={max_workers})",
    )

    # Convert to insertable rows and collect which entities we touched
    row_buffer, affected_cids, affected_cas = _prepare_insert_rows(cid_to_rns)
    inserted_total = 0

    # Flush XREF rows first no matter what
    for i in range(0, len(row_buffer), FLUSH_EVERY):
        slice_rows = row_buffer[i : i + FLUSH_EVERY]
        inserted_total += _bulk_upsert_cas(db.db_path, slice_rows)

    if use_synonyms:
        from molid.pubchemproc.pubchem_client import get_synonyms

        # Fetch synonyms for all CIDs you’re enriching (covers xref-miss cases)
        syn_target_cids = all_cids

        syn_rows = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(get_synonyms, cid): cid for cid in syn_target_cids}
            for fut in as_completed(futs):
                cid = futs[fut]
                try:
                    syns = fut.result() or []
                except Exception:
                    syns = []
                for rn in syns:
                    if _is_cas_rn(rn):
                        syn_rows.append((rn, cid, "synonym", 2))
                        affected_cids.add(
                            cid
                        )  # make sure we update winner for synonym-only CIDs
                        affected_cas.add(
                            rn
                        )  # ensure generics downgrade sees synonym RNs
        inserted_total += _bulk_upsert_cas(db.db_path, syn_rows)

    # Post-processing: downgrade generic CAS, then choose best CAS per CID
    _downgrade_generic_cas(db, affected_cas)
    _update_best_cas_for_cids(db, affected_cids)

    # synonyms path intentionally omitted (slow/noisy); preserve parameter for API stability
    return inserted_total


def cache_enrich_single_cid(
    db_file: str,
    cid: int,
    synonyms: list[str],
    xrefs_rn: list[str],
) -> None:
    """
    Cache-miss path:
      - First valid CAS from synonyms => confidence=2 (winner)
      - Other valid synonyms + all valid xrefs => confidence=1
      - Then downgrade generics to 0 via existing heuristic
      - Dedup via INSERT OR IGNORE
    """
    db = DatabaseManager(db_file)
    rows = []
    affected: set[str] = set()
    seen = set()

    # Synonyms (ordered): first valid -> 2, rest -> 1
    first_set = False
    for s in synonyms or []:
        if _is_cas_rn(s):
            conf = 2 if not first_set else 1
            first_set = True if not first_set else first_set
            key = (s, cid, "synonym")
            if key not in seen:
                seen.add(key)
                rows.append((s, cid, "synonym", conf))
                affected.add(s)

    # XRefs/RN (unordered): all valid -> 1
    for rn in xrefs_rn or []:
        if _is_cas_rn(rn):
            key = (rn, cid, "xref")
            if key not in seen:
                seen.add(key)
                rows.append((rn, cid, "xref", 1))
                affected.add(rn)

    if rows:
        _bulk_upsert_cas(db.db_path, rows)
        _downgrade_generic_cas(db, affected)
