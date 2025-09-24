import pytest
from ase.build import molecule
from molid.main import run
from molid.db.db_utils import create_cache_db, insert_dict_records

CO2_ADVANCED = {
    'CID': 280,
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'MolecularFormula': 'CO2',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'TPSA': 34.1,
    'Charge': 0,
    'CanonicalSMILES': 'C(=O)=O',
    'IsomericSMILES': 'C(=O)=O',
    'Title': 'Carbon Dioxide',
    'IUPACName': 'carbonic acid oxide',
    'XLogP': 0.9,
    'ExactMass': 43.989829239,
    'Complexity': 18,
    'MonoisotopicMass': '43.989829239'
}

@pytest.fixture(autouse=True)
def set_env(monkeypatch, tmp_path_factory):
    """Global env for all `run(...)` tests - use cached mode with seeded CO₂ to avoid network."""
    cache = tmp_path_factory.mktemp("cache") / "test_cache.db"
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  str(cache))
    monkeypatch.setenv("MOLID_MODE",      "online-cached")
    create_cache_db(str(cache))
    insert_dict_records(
        db_file=str(cache),
        table="cached_molecules",
        records=[CO2_ADVANCED],
        ignore_conflicts=True
    )

def test_run_from_atoms():
    atoms = molecule("CO2")
    result, source = run(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_identifier_dict():
    result, source = run({"SMILES": "C(=O)=O"})
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_raw_xyz():
    xyz = ("3\nCO2\n"
           "C 0.000 0.000 0.000\n"
           "O 1.160 0.000 0.000\n"
           "O -1.160 0.000 0.000\n")
    result, source = run(xyz)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_path_xyz(tmp_path):
    xyz_file = tmp_path / "water.xyz"
    xyz_file.write_text(
        "3\nCO2\n"
        "C 0.000 0.000 0.000\n"
        "O 1.160 0.000 0.000\n"
        "O -1.160 0.000 0.000\n"
    )
    result, source = run(str(xyz_file))
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_invalid_input_type():
    with pytest.raises(ValueError):
        run(12345)
