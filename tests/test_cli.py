import sqlite3
import json
import pytest
from click.testing import CliRunner

from molid.cli import cli
from molid.db.sqlite_manager import DatabaseManager
from molid.db.schema import OFFLINE_SCHEMA


@pytest.fixture
def runner():
    return CliRunner()


def test_db_create_creates_sqlite_file(tmp_path, runner):
    db_file = tmp_path / "test.db"
    result = runner.invoke(cli, ["db", "create", "--db-file", str(db_file)])
    assert result.exit_code == 0, result.output
    assert db_file.exists()
    conn = sqlite3.connect(db_file)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "compound_data" in tables
    assert "processed_archives" in tables
    conn.close()


def test_db_use_success(tmp_path, runner):
    db_file = tmp_path / "use.db"
    db_file.write_bytes(b"")
    result = runner.invoke(cli, ["db", "use", "--db-file", str(db_file)])
    assert result.exit_code == 0, result.output
    assert f"Using master database: {db_file}" in result.output


def test_db_use_failure(tmp_path, runner):
    non_existent = tmp_path / "nope.db"
    result = runner.invoke(cli, ["db", "use", "--db-file", str(non_existent)])
    assert result.exit_code != 0


def test_search_master_smiles_found(tmp_path, runner):
    db_file = tmp_path / "search.db"
    DatabaseManager(str(db_file)).initialize(OFFLINE_SCHEMA)
    conn = sqlite3.connect(db_file)
    data = ("C", "ABCDEF1234567890-UHFFFAOYSA-N", "InChI=1S/C", "C")
    conn.execute(
        "INSERT INTO compound_data (CanonicalSMILES, InChIKey, InChI, MolecularFormula) VALUES (?, ?, ?, ?)",
        data,
    )
    conn.commit()
    conn.close()

    env = {
        "MOLID_MASTER_DB": str(db_file),
        "MOLID_SOURCES": json.dumps(["master"]),
        "MOLID_CACHE_WRITES": "false",
    }
    result = runner.invoke(cli, ["search", "C", "--id-type", "smiles"], env=env)
    assert result.exit_code == 0, result.output
    assert "[Source] master" in result.output


def test_search_master_not_found(tmp_path, runner):
    db_file = tmp_path / "empty.db"
    DatabaseManager(str(db_file)).initialize(OFFLINE_SCHEMA)
    env = {
        "MOLID_MASTER_DB": str(db_file),
        "MOLID_SOURCES": json.dumps(["master"]),
        "MOLID_CACHE_WRITES": "false",
    }
    result = runner.invoke(cli, ["search", "UNKNOWN", "--id-type", "smiles"], env=env)
    assert result.exit_code != 0


def test_config_set_and_show(monkeypatch, tmp_path):
    # Redirect HOME so ~/.molid.env goes under tmp
    monkeypatch.setenv("HOME", str(tmp_path))
    r = CliRunner()

    # set-master / set-cache
    out1 = r.invoke(cli, ["config", "set-master", str(tmp_path / "master.db")])
    assert out1.exit_code == 0
    out2 = r.invoke(cli, ["config", "set-cache", str(tmp_path / "cache.db")])
    assert out2.exit_code == 0

    # set-sources
    out3 = r.invoke(cli, ["config", "set-sources", "cache", "api"])
    assert out3.exit_code == 0

    # set-cache-writes
    out4 = r.invoke(cli, ["config", "set-cache-writes", "true"])
    assert out4.exit_code == 0

    # show
    out5 = r.invoke(cli, ["config", "show"])
    assert out5.exit_code == 0
    s = out5.output
    assert '"master_db"' in s and '"cache_db"' in s
    assert '"sources"' in s and '"cache_writes"' in s
