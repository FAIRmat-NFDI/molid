
import pytest
import json
import textwrap
import importlib.util
from pathlib import Path
from ase.build import molecule
from molid.main import run
from molid.db.db_utils import create_cache_db, insert_dict_records
from molid.utils import settings as _settings
from molid import pipeline
from molid.search.service import SearchService, SearchConfig
from molid.pipeline import (
    search_identifier,
    search_from_atoms,
    search_from_file,
    search_from_input,
)

CO2_ADVANCED = {
    'CID': 280,
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'MolecularFormula': 'CO2',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'TPSA': 34.1,
    'Charge': 0,
    'CanonicalSMILES': 'C(=O)=O',
    'IsomericSMILES': 'C(=O)=O',
    'Title': 'carbonic acid oxide',
    'XLogP': 0.9,
    'ExactMass': 43.989829239,
    'Complexity': 18,
    'MonoisotopicMass': '43.989829239'
}

has_openbabel = importlib.util.find_spec("openbabel") is not None

@pytest.fixture(autouse=True)
def sandbox_env(monkeypatch, tmp_path_factory):
    # isolate from CLI tests by sandboxing HOME and ENV_FILE
    home = tmp_path_factory.mktemp("home")
    cache = tmp_path_factory.mktemp("cache") / "test_cache.db"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(_settings, "ENV_FILE", home / ".molid.env", raising=True)
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  str(cache))
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache","api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    create_cache_db(str(cache))
    insert_dict_records(
        db_file=str(cache),
        table="cached_molecules",
        records=[CO2_ADVANCED],
        ignore_conflicts=True
    )
    # Force the pipeline to construct the service from ENV only (ignore any file config)
    def _factory():
        import os, json
        master = os.environ.get("MOLID_MASTER_DB", "")
        cachep = os.environ.get("MOLID_CACHE_DB", "")
        sources = json.loads(os.environ.get("MOLID_SOURCES", "[]"))
        net = os.environ.get("MOLID_NETWORK", "allow")
        cw = os.environ.get("MOLID_CACHE_WRITES", "true").lower() == "true"
        return SearchService(master, cachep, SearchConfig(sources=sources, network=net, cache_writes=cw))
    monkeypatch.setattr(pipeline, "_create_search_service", _factory, raising=True)


@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; Atoms→InChIKey path uses OpenBabel")
def test_run_from_atoms():
    atoms = molecule("CO2")
    result, source = run(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)

def test_run_from_identifier_dict():
    result, source = run({"SMILES": "C(=O)=O"})
    assert isinstance(result, list)
    assert isinstance(source, str)

@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; raw XYZ path uses Atoms→InChIKey")
def test_run_from_raw_xyz():
    xyz = ("3\nCO2\n"
           "C 0.000 0.000 0.000\n"
           "O 1.160 0.000 0.000\n"
           "O -1.160 0.000 0.000\n")
    result, source = run(xyz)
    assert isinstance(result, list)
    assert isinstance(source, str)

@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; file XYZ path uses Atoms→InChIKey")
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
    'MolecularWeight': 44.009,
    'Complexity': 18,
    'MonoisotopicMass': 43.989829239,
}

BASIC_RESULT = {
    'SMILES': 'C(=O)=O',
    'InChIKey': 'CURLTUGMZLYLDI-UHFFFAOYSA-N',
    'InChI': 'InChI=1S/CO2/c2-1-3',
    'Formula': 'CO2'
}

has_openbabel = importlib.util.find_spec("openbabel") is not None

@pytest.fixture(scope="session", autouse=True)
def clear_cache():
    cache_path = Path("tests/data/test_cache.db")
    if cache_path.exists():
        cache_path.unlink()

@pytest.fixture
def set_env(request, monkeypatch):
    # params: (sources, network, cache_writes, expect_kind, query_dict)
    sources, network, cache_writes, expect_kind, query = getattr(
        request, 'param',
        (["api"], "allow", True, "advanced", {"SMILES": "C(=O)=O"})
    )
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(sources))
    monkeypatch.setenv("MOLID_NETWORK", network)
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true" if cache_writes else "false")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    if "cache" in sources:
        create_cache_db("tests/data/test_cache.db")
        insert_dict_records(
            db_file="tests/data/test_cache.db",
            table="cached_molecules",
            records=[ADVANCED_RESULT],
            ignore_conflicts=True
        )
    return expect_kind, query

@pytest.mark.parametrize(
    "set_env",
    [
        # For API-only: use an API-supported namespace (InChIKey).
        (["api"], "allow", False, "advanced", {"InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N"}),
        # Cache+API: SMILES ok (cache schema supports CanonicalSMILES).
        (["cache","api"], "allow", True, "advanced", {"SMILES": "C(=O)=O"}),
        # Master-only (older sample DB may miss CanonicalSMILES): use InChIKey.
        (["master"], "forbid", False, "basic", {"InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N"}),
        # Cache-only, no network: SMILES ok.
        (["cache"], "forbid", False, "advanced", {"SMILES": "C(=O)=O"}),
    ],
    indirect=True
)
def test_search_identifier(set_env):
    expect_kind, query = set_env
    results, source = search_identifier(query)
    assert isinstance(results, list) and len(results) >= 1
    rec = results[0]
    subset = BASIC_RESULT if expect_kind == "basic" else ADVANCED_RESULT
    for k, v in subset.items():
        assert rec.get(k) == v

@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; Atoms→InChIKey conversion is optional")
def test_search_from_atoms(monkeypatch):
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache","api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    atoms = molecule("CH4")
    result, source = search_from_atoms(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)

@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; XYZ→InChIKey path uses OpenBabel")
def test_search_from_file_xyz(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache","api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

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
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "false")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    invalid = tmp_path / "not.xyz.txt"
    invalid.write_text("foo")
    with pytest.raises(ValueError):
        search_from_file(str(invalid))

def test_search_from_input_dict(monkeypatch):
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "false")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    # Use an identifier that PubChem resolves via API without hitting the
    # canonicalsmiles namespace issue.
    result, source = search_from_input({"InChIKey": "VNWKTOKETHGBQD-UHFFFAOYSA-N"})  # methane
    assert isinstance(result, list)
    assert isinstance(source, str)

@pytest.mark.skipif(not has_openbabel, reason="OpenBabel not installed; raw XYZ path uses Atoms→InChIKey")
def test_search_from_input_raw_xyz(monkeypatch):
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache","api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

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
    import json
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "false")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB",  "tests/data/test_cache.db")

    with pytest.raises(ValueError):
        search_from_input(12345)

def test_sdf_path_calls_search_with_inchikey(tmp_path, monkeypatch):
    # Minimal SDF snippet with InChIKey field
    sdf = textwrap.dedent("""
    RDKit

      0  0  0  0  0  0            999 V2000
    M  END
    > <PUBCHEM_IUPAC_INCHIKEY>
    ABCDEFGHIJKLMN-ABCDEFHIJSA-N

    $$$$
    """).strip()
    f = tmp_path / "one.sdf"; f.write_text(sdf)

    # Make _create_search_service return a stub that records inputs
    called = {}
    class _Stub:
        def search(self, q):
            called["q"] = q
            return ([{"CID": 1}], "api")
    monkeypatch.setattr(pipeline, "_create_search_service", lambda: _Stub())
    res, src = pipeline.search_from_file(str(f))
    assert res and src == "api"
    # Ensure we extracted IK and searched by it
    assert called["q"] == {"inchikey": "ABCDEFGHIJKLMN-ABCDEFHIJSA-N"}
