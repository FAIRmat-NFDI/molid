# tests/test_auto_mode.py
import os
import stat
import pytest
from pathlib import Path

from molid.db.db_utils import create_offline_db
from molid.pipeline import search_identifier

# Expected subsets (mirror test_pipeline.py style)
ADVANCED_RESULT = {
    'CID': 280,
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'MolecularFormula': 'CO2',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'TPSA': 34.1,
    'Charge': 0,
    'CanonicalSMILES': 'C(=O)=O',
    'IsomericSMILES': 'C(=O)=O',
    'Title': 'Carbon Dioxide',
    'IUPACName': 'carbon dioxide',
    'XLogP': 0.9,
    'ExactMass': 43.989829239,
    'Complexity': 18,
    'MonoisotopicMass': 43.989829239
}

BASIC_RESULT = {
    'SMILES': 'C(=O)=O',
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'Formula': 'CO2'
}

@pytest.fixture(scope="session", autouse=True)
def clear_cache():
    p = Path("tests/data/test_cache.db")
    if p.exists():
        p.unlink()

def _assert_subset(rec: dict, expected_subset: dict):
    for k, v in expected_subset.items():
        assert rec.get(k) == v, f"Mismatch for {k}: got {rec.get(k)!r}, expected {v!r}"

def test_auto_prefers_offline_basic(monkeypatch):
    """
    With a valid master DB present and containing CO2, auto should resolve via offline-basic.
    """
    monkeypatch.setenv("MOLID_MODE", "auto")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    results, source = search_identifier({"SMILES": "C(=O)=O"})
    assert source == "offline-basic"
    assert len(results) == 1
    _assert_subset(results[0], BASIC_RESULT)

def test_auto_falls_back_to_online_cached_on_offline_miss(tmp_path, monkeypatch):
    """
    If offline-basic returns no hit (empty master DB), auto should fall back to online-cached
    and fetch from the live API, then cache it.
    """
    monkeypatch.setenv("MOLID_MODE", "auto")

    # Create an empty master DB (schema only) so offline-basic misses.
    empty_master = tmp_path / "empty_master.db"
    create_offline_db(str(empty_master))
    monkeypatch.setenv("MOLID_MASTER_DB", str(empty_master))

    # Use a writable cache DB location.
    cache_db = tmp_path / "cache.db"
    monkeypatch.setenv("MOLID_CACHE_DB", str(cache_db))

    results, source = search_identifier({"SMILES": "C(=O)=O"})
    assert source == "online-cached"  # fetched (and cached) via API
    assert isinstance(results, list) and len(results) >= 1
    _assert_subset(results[0], ADVANCED_RESULT)

def test_auto_skips_online_cached_when_cache_dir_unwritable_and_uses_online_only(tmp_path, monkeypatch):
    """
    If the cache directory is not writable, auto should skip online-cached and use online-only.
    """
    monkeypatch.setenv("MOLID_MODE", "auto")

    # Force offline-basic to miss as well (empty master)
    empty_master = tmp_path / "empty_master.db"
    create_offline_db(str(empty_master))
    monkeypatch.setenv("MOLID_MASTER_DB", str(empty_master))

    # Create a read-only directory for the cache DB to trigger skip of online-cached
    ro_dir = tmp_path / "ro_dir"
    ro_dir.mkdir()
    # remove write permission for owner/group/others
    ro_dir.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    cache_db = ro_dir / "cache.db"
    monkeypatch.setenv("MOLID_CACHE_DB", str(cache_db))

    try:
        results, source = search_identifier({"SMILES": "C(=O)=O"})
        # Expect auto to bypass online-cached (permission failure) and succeed via online-only
        assert source == "online-only"
        assert isinstance(results, list) and len(results) >= 1
        _assert_subset(results[0], ADVANCED_RESULT)
    finally:
        # restore permissions so tmp cleanup doesn't fail on some platforms
        ro_dir.chmod(stat.S_IWUSR | stat.S_IREAD)
