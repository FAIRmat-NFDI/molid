from __future__ import annotations

import logging
from typing import Any

from molid.db.cas_enrich import _downgrade_generic_cas
from molid.db.db_utils import insert_dict_records
from molid.db.schema import CACHE_COLUMNS, DEFAULT_PROPERTIES_CACHE, NUMERIC_FIELDS
from molid.db.sqlite_manager import DatabaseManager
from molid.pubchemproc.fetch import _normalize_keys
from molid.pubchemproc.pubchem_client import get_properties, resolve_to_cids
from molid.search.db_lookup import advanced_search
from molid.utils.conversion import coerce_numeric_fields
from molid.utils.formula import canonicalize_formula
from molid.utils.settings import load_config

logger = logging.getLogger(__name__)

CACHE_TABLE = "cached_molecules"

cfg = load_config()
cache_enabled = bool(cfg.cas_expand_cache)
cache_limit = int(cfg.cas_expand_cache_limit)


def store_cached_data(
    cache_db_file: str, id_type: str, id_value: str, api_data: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Store the API response in the cache database.
    """
    if not isinstance(api_data, list) or not all(
        isinstance(item, dict) for item in api_data
    ):
        logger.error(
            "Unexpected API response format for %s (%s): expected List[dict], got %r",
            id_type,
            id_value,
            type(api_data),
        )
        raise ValueError("Unexpected API response format; expected a list of dicts.")

    cleaned_records = [coerce_numeric_fields(item, NUMERIC_FIELDS) for item in api_data]
    allowed = set(CACHE_COLUMNS)
    filtered_records = [
        {k: v for k, v in rec.items() if k in allowed} for rec in cleaned_records
    ]
    insert_dict_records(
        db_file=cache_db_file,
        table=CACHE_TABLE,
        records=filtered_records,
        ignore_conflicts=True,
    )

    logger.info("Cached %d records for %s (%s)", len(api_data), id_type, id_value)

    # If the user searched by CAS, record the mapping only (don't touch cached_molecules.CAS)
    if id_type.lower() == "cas":
        mgr = DatabaseManager(cache_db_file)
        cids = resolve_to_cids("cas", str(id_value)) or []
        if cids:
            rows = [(str(id_value), int(c), "xref", 1) for c in cids]
            mgr.executemany(
                "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
                rows,
            )

    cached = advanced_search(cache_db_file, id_type, id_value)
    logger.debug("cached results: %s, for %s, %s", cached, id_type, id_value)
    if not cached and id_type.lower() == "molecularformula":
        cached = advanced_search(
            cache_db_file, "molecularformula", canonicalize_formula(str(id_value))
        )

    if not cached:
        logger.warning(
            "Failed to retrieve just-stored cache record for %s (%s)", id_type, id_value
        )
    return cached


def get_cached_or_fetch(
    cache_db_file: str,
    id_type: str,
    id_value: str,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Checks for a cached molecule; if not found, fetches data via the API
    and stores it.
    Returns (record, from_cache).
    """
    if id_type.lower() == "molecularformula":
        canon = canonicalize_formula(str(id_value))
        cached = advanced_search(cache_db_file, id_type, canon)
        if cached:
            return cached, True

    if id_type.lower() == "cas":
        # Resolve authoritative CID list for this CAS
        try:
            resolved_cids = resolve_to_cids("cas", str(id_value)) or []
        except Exception:
            resolved_cids = []

        if resolved_cids:
            mgr = DatabaseManager(cache_db_file)

            # 1) Record all (CAS, CID) mappings — do not touch cached_molecules.CAS
            rows = [(str(id_value), int(cid), "query", 1) for cid in resolved_cids]
            mgr.executemany(
                "INSERT OR IGNORE INTO cas_mapping (CAS, CID, source, confidence) VALUES (?,?,?,?)",
                rows,
            )

            # 2) Optionally cache molecule rows for missing CIDs (bounded)
            if cache_enabled and cache_limit > 0:
                placeholders = ",".join("?" for _ in resolved_cids)
                existing = mgr.query_all(
                    f"SELECT CID FROM {CACHE_TABLE} WHERE CID IN ({placeholders})",
                    resolved_cids,
                )
                have = {int(r["CID"]) for r in (existing or [])}
                missing = [int(c) for c in resolved_cids if int(c) not in have][
                    :cache_limit
                ]

                if missing:
                    fetched: list[dict[str, Any]] = []
                    for cid in missing:
                        props = get_properties(int(cid), DEFAULT_PROPERTIES_CACHE) or []
                        for p in props:
                            rec = _normalize_keys(p)
                            rec["CID"] = int(cid)
                            fetched.append(rec)

                    if fetched:
                        # coerce numerics, then filter to actual cache columns
                        cleaned = [
                            coerce_numeric_fields(r, NUMERIC_FIELDS) for r in fetched
                        ]
                        allowed = set(CACHE_COLUMNS)
                        filtered = [
                            {k: v for k, v in r.items() if k in allowed}
                            for r in cleaned
                        ]
                        insert_dict_records(
                            db_file=cache_db_file,
                            table=CACHE_TABLE,
                            records=filtered,
                            ignore_conflicts=True,
                        )
            try:
                _downgrade_generic_cas(DatabaseManager(cache_db_file), [str(id_value)])
            except Exception:
                logger.debug("Generic CAS downgrade skipped", exc_info=True)

            # 3) Now, read results from cache using your derived-on-read logic
            records = advanced_search(cache_db_file, "cas", id_value)
            if records:
                return records, True

    cached = advanced_search(cache_db_file, id_type, id_value)
    if cached:
        return cached, True

    from molid.pubchemproc.fetch import fetch_molecule_data

    api_data = fetch_molecule_data(id_type, id_value)
    stored = store_cached_data(cache_db_file, id_type, id_value, api_data)

    # NEW: inline CAS mapping enrichment for the just-fetched CID(s)
    try:
        from molid.db.cas_enrich import cache_enrich_single_cid
        from molid.pubchemproc.pubchem_client import get_synonyms, get_xrefs_rn

        # 'stored' comes from advanced_search; every row should carry a CID
        for row in stored or []:
            cid = row.get("CID")
            if cid is None:
                continue
            # Use short timeout for synonyms in the fetch layer already; here we use defaults
            syns = get_synonyms(int(cid)) or []
            rns = get_xrefs_rn(int(cid)) or []
            cache_enrich_single_cid(cache_db_file, int(cid), syns, rns)
    except Exception as e:
        logger.warning(
            "Inline CAS mapping enrichment failed for %s (%s): %s", id_type, id_value, e
        )
    return stored, False
