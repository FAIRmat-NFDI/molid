import os
import sqlite3
import json
import pytest
from click.testing import CliRunner

from molid.cli import cli
from molid.db.sqlite_manager import DatabaseManager
from molid.db.schema import OFFLINE_SCHEMA
from molid.search.service import MoleculeNotFound

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
    assert "processed_folders" in tables
    conn.close()


def test_db_use_success(tmp_path, runner):
    db_file = tmp_path / "use.db"
    # create empty file
    db_file.write_bytes(b"")
    result = runner.invoke(cli, ["db", "use", "--db-file", str(db_file)])
    assert result.exit_code == 0, result.output
    assert f"Using master database: {db_file}" in result.output


def test_db_use_failure(tmp_path, runner):
    non_existent = tmp_path / "nope.db"
    result = runner.invoke(cli, ["db", "use", "--db-file", str(non_existent)])
    # Should exit with error when DB does not exist
    assert result.exit_code != 0


def test_search_offline_basic_found(tmp_path, runner):
    # Setup offline DB with one record
    db_file = tmp_path / "search.db"
    # initialize schema
    DatabaseManager(str(db_file)).initialize(OFFLINE_SCHEMA)
    # insert record
    conn = sqlite3.connect(db_file)
    inchikey = "ABCDEF1234567890"
    data = ("C", inchikey, "InChI=1S/C", "C", inchikey[:14])
    conn.execute(
        "INSERT INTO compound_data (SMILES, InChIKey, InChI, Formula, InChIKey14) VALUES (?, ?, ?, ?, ?)",
        data
    )
    conn.commit()
    conn.close()

    env = {"MOLID_MASTER_DB": str(db_file), "MOLID_MODE": "offline-basic"}
    result = runner.invoke(cli, ["search", inchikey], env=env)
    assert result.exit_code == 0, result.output
    assert "[Source] offline-basic" in result.output
    # Parse JSON output
    output_lines = result.output.splitlines()
    json_text = "\n".join(output_lines[2:])
    results = json.loads(json_text)
    assert isinstance(results, list)
    assert results[0]["InChIKey"] == inchikey


def test_search_offline_basic_not_found(tmp_path, runner):
    db_file = tmp_path / "empty.db"
    DatabaseManager(str(db_file)).initialize(OFFLINE_SCHEMA)
    env = {"MOLID_MASTER_DB": str(db_file), "MOLID_MODE": "offline-basic"}
    result = runner.invoke(cli, ["search", "UNKNOWN"], env=env)
    # Should error when no record is found
    assert result.exit_code != 0
    # It should raise a MoleculeNotFound exception with appropriate message
    assert isinstance(result.exception, MoleculeNotFound)
    assert "not found in master db" in str(result.exception).lower()
