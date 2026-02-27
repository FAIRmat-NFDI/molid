import pytest
import json
import importlib.util
from ase.build import molecule
from molid.main import run
from molid.db.db_utils import create_cache_db, insert_dict_records
from molid.utils import settings as _settings
from molid import pipeline
from molid.search.service import SearchService, SearchConfig

CO2_ADVANCED = {
    "CID": 280,
    "InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N",
    "MolecularFormula": "CO2",
    "InChI": "InChI=1S/CO2/c2-1-3",
    "TPSA": 34.1,
    "Charge": 0,
    "CanonicalSMILES": "C(=O)=O",
    "IsomericSMILES": "C(=O)=O",
    "Title": "carbonic acid oxide",
    "XLogP": 0.9,
    "ExactMass": 43.989829239,
    "Complexity": 18,
    "MonoisotopicMass": "43.989829239",
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
    monkeypatch.setenv("MOLID_CACHE_DB", str(cache))
    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache", "api"]))
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    create_cache_db(str(cache))
    insert_dict_records(
        db_file=str(cache),
        table="cached_molecules",
        records=[CO2_ADVANCED],
        ignore_conflicts=True,
    )

    # Force the pipeline to construct the service from ENV only (ignore any file config)
    def _factory():
        import os
        import json

        master = os.environ.get("MOLID_MASTER_DB", "")
        cachep = os.environ.get("MOLID_CACHE_DB", "")
        sources = json.loads(os.environ.get("MOLID_SOURCES", "[]"))
        cw = os.environ.get("MOLID_CACHE_WRITES", "true").lower() == "true"
        return SearchService(
            master, cachep, SearchConfig(sources=sources, cache_writes=cw)
        )

    monkeypatch.setattr(pipeline, "_create_search_service", _factory, raising=True)


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; Atoms→InChIKey path uses OpenBabel",
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


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; raw XYZ path uses Atoms→InChIKey",
)
def test_run_from_raw_xyz():
    xyz = "3\nCO2\nC 0.000 0.000 0.000\nO 1.160 0.000 0.000\nO -1.160 0.000 0.000\n"
    result, source = run(xyz)
    assert isinstance(result, list)
    assert isinstance(source, str)


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; file XYZ path uses Atoms→InChIKey",
)
def test_run_from_path_xyz(tmp_path):
    xyz_file = tmp_path / "water.xyz"
    xyz_file.write_text(
        "3\nCO2\nC 0.000 0.000 0.000\nO 1.160 0.000 0.000\nO -1.160 0.000 0.000\n"
    )
    result, source = run(str(xyz_file))
    assert isinstance(result, list)
    assert isinstance(source, str)


def test_run_invalid_input_type():
    with pytest.raises(ValueError):
        run(12345)
