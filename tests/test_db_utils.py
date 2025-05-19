import sqlite3
import pytest
from molid.db import db_utils  # :contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}

def test_create_offline_and_cache_dbs(tmp_path):
    off = tmp_path/"off.db"
    cache = tmp_path/"cache.db"
    db_utils.create_offline_db(str(off))
    db_utils.create_cache_db(str(cache))
    names1 = [r[0] for r in sqlite3.connect(off).execute(
        "SELECT name FROM sqlite_master WHERE type='table';")]
    names2 = [r[0] for r in sqlite3.connect(cache).execute(
        "SELECT name FROM sqlite_master WHERE type='table';")]
    assert "compound_data" in names1 and "processed_folders" in names1
    assert "cached_molecules" in names2

def test_mark_and_check_folder(tmp_path):
    off = tmp_path/"off2.db"
    db_utils.create_offline_db(str(off))
    assert not db_utils.is_folder_processed(str(off), "foo")
    db_utils.mark_folder_as_processed(str(off), "foo")
    assert db_utils.is_folder_processed(str(off), "foo")
