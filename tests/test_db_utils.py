import sqlite3
from molid.db import db_utils

def test_create_offline_and_cache_dbs(tmp_path):
    off = tmp_path/"off.db"
    cache = tmp_path/"cache.db"
    db_utils.create_offline_db(str(off))
    db_utils.create_cache_db(str(cache))
    names1 = [r[0] for r in sqlite3.connect(off).execute(
        "SELECT name FROM sqlite_master WHERE type='table';")]
    names2 = [r[0] for r in sqlite3.connect(cache).execute(
        "SELECT name FROM sqlite_master WHERE type='table';")]
    assert "compound_data" in names1 and "processed_archives" in names1
    assert "cached_molecules" in names2

def test_upsert_and_get_archive_state(tmp_path):
    off = tmp_path/"off2.db"
    db_utils.create_offline_db(str(off))
    # Initially not present
    state = db_utils.get_archive_state(str(off), "2025-07-01.sdf.gz")
    assert state is None
    # Upsert an ingested archive record
    db_utils.upsert_archive_state(
        str(off),
        "2025-07-01.sdf.gz",
        status="ingested",
        source="monthly",
        md5="abc123",
        last_ingested="2025-07-31T12:34:56"
    )
    state = db_utils.get_archive_state(str(off), "2025-07-01.sdf.gz")
    assert state is not None
    assert state["status"] == "ingested"
    assert state["md5"] == "abc123"
