import importlib.util
import textwrap
from pathlib import Path

import pytest
from ase.build import molecule

from molid import pipeline
from molid.db.db_utils import create_cache_db, insert_dict_records
from molid.pipeline import (
    search_from_atoms,
    search_from_file,
    search_from_input,
    search_identifier,
)

ADVANCED_RESULT = {
    "CID": 280,
    "InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N",
    "MolecularFormula": "CO2",
    "InChI": "InChI=1S/CO2/c2-1-3",
    "TPSA": 34.1,
    "Charge": 0,
    "CanonicalSMILES": "C(=O)=O",
    "IsomericSMILES": "C(=O)=O",
    "Title": "Carbon Dioxide",
    "IUPACName": "carbon dioxide",
    "XLogP": 0.9,
    "ExactMass": 43.989829239,
    "MolecularWeight": 44.009,
    "Complexity": 18,
    "MonoisotopicMass": 43.989829239,
}

BASIC_RESULT = {
    "SMILES": "C(=O)=O",
    "InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N",
    "InChI": "InChI=1S/CO2/c2-1-3",
    "Formula": "CO2",
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
        request, "param", (["api"], "allow", True, "advanced", {"SMILES": "C(=O)=O"})
    )
    import json

    monkeypatch.setenv("MOLID_SOURCES", json.dumps(sources))
    monkeypatch.setenv("MOLID_NETWORK", network)
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true" if cache_writes else "false")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

    if "cache" in sources:
        create_cache_db("tests/data/test_cache.db")
        insert_dict_records(
            db_file="tests/data/test_cache.db",
            table="cached_molecules",
            records=[ADVANCED_RESULT],
            ignore_conflicts=True,
        )
    return expect_kind, query


@pytest.mark.parametrize(
    "set_env",
    [
        # For API-only: use an API-supported namespace (InChIKey).
        (
            ["api"],
            "allow",
            False,
            "advanced",
            {"InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N"},
        ),
        # Cache+API: SMILES ok (cache schema supports CanonicalSMILES).
        (["cache", "api"], "allow", True, "advanced", {"SMILES": "C(=O)=O"}),
        # Master-only (older sample DB may miss CanonicalSMILES): use InChIKey.
        (
            ["master"],
            "forbid",
            False,
            "basic",
            {"InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N"},
        ),
        # Cache-only, no network: SMILES ok.
        (["cache"], "forbid", False, "advanced", {"SMILES": "C(=O)=O"}),
    ],
    indirect=True,
)
def test_search_identifier(set_env):
    expect_kind, query = set_env
    results, source = search_identifier(query)
    assert isinstance(results, list) and len(results) >= 1
    rec = results[0]
    subset = BASIC_RESULT if expect_kind == "basic" else ADVANCED_RESULT
    for k, v in subset.items():
        assert rec.get(k) == v


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; Atoms→InChIKey conversion is optional",
)
def test_search_from_atoms(monkeypatch):
    import json

    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache", "api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

    atoms = molecule("CH4")
    result, source = search_from_atoms(atoms)
    assert isinstance(result, list)
    assert isinstance(source, str)


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; XYZ→InChIKey path uses OpenBabel",
)
def test_search_from_file_xyz(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache", "api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

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
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

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
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

    # Use an identifier that PubChem resolves via API without hitting the
    # canonicalsmiles namespace issue.
    result, source = search_from_input(
        {"InChIKey": "VNWKTOKETHGBQD-UHFFFAOYSA-N"}
    )  # methane
    assert isinstance(result, list)
    assert isinstance(source, str)


@pytest.mark.skipif(
    not has_openbabel,
    reason="OpenBabel not installed; raw XYZ path uses Atoms→InChIKey",
)
def test_search_from_input_raw_xyz(monkeypatch):
    import json

    monkeypatch.setenv("MOLID_SOURCES", json.dumps(["cache", "api"]))
    monkeypatch.setenv("MOLID_NETWORK", "allow")
    monkeypatch.setenv("MOLID_CACHE_WRITES", "true")
    monkeypatch.setenv("MOLID_MASTER_DB", "tests/data/test_master.db")
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

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
    monkeypatch.setenv("MOLID_CACHE_DB", "tests/data/test_cache.db")

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
    f = tmp_path / "one.sdf"
    f.write_text(sdf)

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
