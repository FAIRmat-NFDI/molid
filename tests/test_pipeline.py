import pytest
from pathlib import Path
from ase.build import molecule
from molid.pipeline import (
    search_identifier,
    search_from_atoms,
    search_from_file,
    search_from_input,
)

# Shared expected results to avoid duplication
ADVANCED_RESULT = {
    'CID': 280,
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'MolecularFormula': 'CO2',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'TPSA': 34.1,
    'Charge': 0,
    'CanonicalSMILES': 'C(=O)=O',
    'Title': 'Carbon Dioxide',
    'XLogP': 0.9,
    'ExactMass': '43.989829239',
    'Complexity': 18,
    'MonoisotopicMass': '43.989829239',
    'IsomericSMILES': 'C(=O)=O'
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
    """
    Ensure any existing test cache is removed before tests run.
    """
    cache_path = Path("tests/data/test_cache.db")
    if cache_path.exists():
        cache_path.unlink()


@pytest.fixture
def test_config(tmp_path, request):
    """
    Write a temporary configuration file for a given search mode.

    If not parametrized, defaults to 'online-only'.
    """
    mode = getattr(request, 'param', 'online-only')
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        f'master_db: "tests/data/test_master.db"\n'
        f'cache_db:  "tests/data/test_cache.db"\n'
        f'mode:      "{mode}"\n'
        f'cache_enabled: true\n'
    )
    return str(cfg_file)


@pytest.mark.parametrize(
    "test_config, expected_result, expected_sources",
    [
        pytest.param(
            "online-only",
            ADVANCED_RESULT,
            ["api", "api"],
            id="online-only"
        ),
        pytest.param(
            "online-cached",
            ADVANCED_RESULT,
            ["api", "user-cache"],
            id="online-cached"
        ),
        pytest.param(
            "offline-basic",
            BASIC_RESULT,
            ["master-cache", "master-cache"],
            id="offline-basic"
        ),
        pytest.param(
            "offline-advanced",
            ADVANCED_RESULT,
            ["user-cache", "user-cache"],
            id="offline-advanced"
        )
    ],
    indirect=["test_config"]
)
def test_search_identifier(test_config, expected_result, expected_sources):
    """
    Validates search_identifier behavior across modes, ensuring caching works as expected.
    """
    results = []
    sources = []
    for _ in range(2):
        result, source = search_identifier({"SMILES": "C(=O)=O"}, config_path=test_config)
        # Remove nondeterministic fields
        result.pop("fetched_at", None)
        result.pop("id", None)
        results.append(result)
        sources.append(source)

    # Each call should return the same result
    assert results == [expected_result, expected_result]
    # Sources sequence should match expected caching behavior
    assert sources == expected_sources


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
