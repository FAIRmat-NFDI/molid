import pytest
from molid.pipeline import (
    search_identifier,
    search_from_atoms,
    search_from_file,
    search_from_input
)
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


def test_search_identifier(test_config):
    result, source = search_identifier({"SMILES": "c1ccccc1"}, config_path=test_config)
    assert isinstance(result, dict)
    assert isinstance(source, str)


def test_search_from_atoms(test_config):
    atoms = molecule("CH4")
    result, source = search_from_atoms(atoms, config_path=test_config)
    assert isinstance(result, dict)
    assert isinstance(source, str)


def test_search_from_file_xyz(tmp_path, test_config):
    xyz_file = tmp_path / "test.xyz"
    xyz_file.write_text("""5\nMethane\nC 0.000 0.000 0.000\nH 0.629 0.629 0.629\nH -0.629 -0.629 0.629\nH -0.629 0.629 -0.629\nH 0.629 -0.629 -0.629\n""")
    result, source = search_from_file(str(xyz_file), config_path=test_config)
    assert isinstance(result, dict)
    assert isinstance(source, str)


def test_search_from_file_invalid_extension(tmp_path, test_config):
    invalid_file = tmp_path / "test.txt"
    invalid_file.write_text("Some invalid content")
    with pytest.raises(ValueError):
        search_from_file(str(invalid_file), config_path=test_config)


def test_search_from_input_dict(test_config):
    result, source = search_from_input({"SMILES": "C"}, config_path=test_config)
    assert isinstance(result, dict)
    assert isinstance(source, str)


def test_search_from_input_raw_xyz(test_config):
    xyz = """3\nwater\nO      0.00000      0.00000      0.00000\nH      0.75700      0.58600      0.00000\nH     -0.75700      0.58600      0.00000\n"""
    result, source = search_from_input(xyz, config_path=test_config)
    assert isinstance(result, dict)
    assert isinstance(source, str)


def test_search_from_input_invalid_type(test_config):
    with pytest.raises(ValueError):
        search_from_input(12345, config_path=test_config)
