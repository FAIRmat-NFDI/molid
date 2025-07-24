import pytest
from ase.build import molecule
from molid import run

@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    """
    Global env for all `run(...)` tests
    """
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")
    monkeypatch.setenv("MOLID_MODE",      "online-only")

def test_run_from_atoms():
    atoms = molecule("H2O")
    result, source = run(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_identifier_dict():
    result, source = run({"SMILES": "c1ccccc1"})
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_raw_xyz():
    xyz = (
        "3\nwater\n"
        "O      0.00000      0.00000      0.00000\n"
        "H      0.75700      0.58600      0.00000\n"
        "H     -0.75700      0.58600      0.00000\n"
    )
    result, source = run(xyz)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_path_xyz(tmp_path):
    xyz_file = tmp_path / "water.xyz"
    xyz_file.write_text(
        "3\nwater\n"
        "O      0.00000      0.00000      0.00000\n"
        "H      0.75700      0.58600      0.00000\n"
        "H     -0.75700      0.58600      0.00000\n"
    )
    result, source = run(str(xyz_file))
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_invalid_input_type():
    with pytest.raises(ValueError):
        run(12345)
