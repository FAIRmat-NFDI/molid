import pytest
from molid import run
from ase.build import molecule

@pytest.fixture
def test_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
    master_db: "tests/data/test_master.db"
    cache_db: "tests/data/test_cache.db"
    mode: "online-only"
    cache_enabled: false
    """)
    return str(cfg)


def test_run_from_atoms(test_config):
    atoms = molecule("H2O")
    result, source = run(atoms, config_path=test_config)
    assert isinstance(result, list)
    assert isinstance(source, str)


def test_run_from_identifier_dict(test_config):
    result, source = run({"SMILES": "c1ccccc1"}, config_path=test_config)
    assert isinstance(result, list)
    assert isinstance(source, str)


def test_run_from_raw_xyz(test_config):
    xyz = """3\nwater\nO      0.00000      0.00000      0.00000\nH      0.75700      0.58600      0.00000\nH     -0.75700      0.58600      0.00000\n"""
    result, source = run(xyz, config_path=test_config)
    assert isinstance(result, list)
    assert isinstance(source, str)


def test_run_from_path_xyz(tmp_path, test_config):
    xyz_file = tmp_path / "molecule.xyz"
    xyz_file.write_text("""3\nwater\nO      0.00000      0.00000      0.00000\nH      0.75700      0.58600      0.00000\nH     -0.75700      0.58600      0.00000\n""")
    result, source = run(str(xyz_file), config_path=test_config)
    assert isinstance(result, list)
    assert isinstance(source, str)


def test_run_invalid_input_type(test_config):
    with pytest.raises(ValueError):
        run(12345, config_path=test_config)