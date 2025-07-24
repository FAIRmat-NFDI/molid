import pytest
from pathlib import Path
from ase.build import molecule
from molid.db.db_utils import create_cache_db, insert_dict_records
from molid.pipeline import (
    search_identifier,
    search_from_atoms,
    search_from_file,
    search_from_input,
)

# Shared expected results
ADVANCED_RESULT = {
    'CID': 280,
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'InChIKey14': 'CURLTUGMZLYLDI',
    'MolecularFormula': 'CO2',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'TPSA': 34.1,
    'Charge': 0,
    'ConnectivitySMILES': 'C(=O)=O',
    'SMILES': 'C(=O)=O',
    'Title': 'Carbon Dioxide',
    'XLogP': 0.9,
    'ExactMass': '43.989829239',
    'Complexity': 18,
    'MonoisotopicMass': '43.989829239'
}

BASIC_RESULT = {
    'SMILES': 'C(=O)=O',
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'Formula': 'CO2',
    'InChIKey14': 'CURLTUGMZLYLDI'
}

@pytest.fixture(scope="session", autouse=True)
def clear_cache():
    # ensure no leftover cache from previous runs
    cache_path = Path("tests/data/test_cache.db")
    if cache_path.exists():
        cache_path.unlink()

@pytest.fixture
def set_env(request, monkeypatch):
    """
    Configure MOLID_* environment variables for each mode.
    If parametrized, request.param is the mode string.
    """
    mode = getattr(request, 'param', 'online-only')
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      mode)

    # For any mode that needs to read from the cache, seed it with our CO₂ record
    if mode in ("offline-advanced", "online-cached"):
        # ADVANCED_RESULT is defined just below
        create_cache_db("tests/data/test_cache.db")
        insert_dict_records(
            db_file="tests/data/test_cache.db",
            table="cached_molecules",
            records=[ADVANCED_RESULT],
            ignore_conflicts=True
        )
    return mode

@pytest.mark.parametrize(
    "set_env, expected_result",
    [
        ("online-only", ADVANCED_RESULT),
        ("online-cached", ADVANCED_RESULT),
        ("offline-basic", BASIC_RESULT),
        ("offline-advanced", ADVANCED_RESULT),
    ],
    indirect=["set_env"]
)
def test_search_identifier(set_env, expected_result):
    mode = set_env
    seen = []
    sources = []

    for _ in range(2):
        results, source = search_identifier({"SMILES": "C(=O)=O"})
        assert len(results) == 1
        # strip nondeterministic fields
        rec = results[0].copy()
        rec.pop("fetched_at", None)
        rec.pop("id", None)
        seen.append(rec)
        sources.append(source)

    assert seen == [expected_result, expected_result]
    # the library returns the mode string as the source in every call
    assert sources == [mode, mode]
    # import pdb; pdb.set_trace()

def test_search_from_atoms(monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    atoms = molecule("CH4")
    result, source = search_from_atoms(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_search_from_file_xyz(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    xyz_file = tmp_path / "methane.xyz"
    xyz_file.write_text(
        "5\nMethane\n"
        "C 0.000 0.000 0.000\n"
        "H 0.629 0.629 0.629\n"
        "H -0.629 -0.629 0.629\n"
        "H -0.629 0.629 -0.629\n"
        "H 0.629 -0.629 -0.629\n"
    )
    result, source = search_from_file(str(xyz_file))
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_search_from_file_invalid_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    invalid = tmp_path / "not.xyz.txt"
    invalid.write_text("foo")
    with pytest.raises(ValueError):
        search_from_file(str(invalid))

def test_search_from_input_dict(monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    result, source = search_from_input({"SMILES": "C"})
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_search_from_input_raw_xyz(monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    xyz = (
        "3\nwater\n"
        "O      0.00000      0.00000      0.00000\n"
        "H      0.75700      0.58600      0.00000\n"
        "H     -0.75700      0.58600      0.00000\n"
    )
    result, source = search_from_input(xyz)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_search_from_input_invalid_type(monkeypatch):
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

    with pytest.raises(ValueError):
        search_from_input(12345)
