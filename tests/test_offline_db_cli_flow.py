from pathlib import Path

from molid.db import offline_db_cli as odc
from molid.db.db_utils import create_offline_db
from molid.db.sqlite_manager import DatabaseManager


def test_update_database_happy_path(monkeypatch, tmp_path):
    db = str(tmp_path / "master.db")
    downloads = tmp_path / "dl"
    downloads.mkdir()
    processed = tmp_path / "proc"
    processed.mkdir()

    # init schema
    create_offline_db(db)

    # avoid disk space dependency
    monkeypatch.setattr(odc, "check_disk_space", lambda *a, **k: None)

    # plan: one archive (gz + md5)
    plan = [("ftp/path/0001.sdf.gz", "ftp/path/0001.sdf.gz.md5", "full")]
    monkeypatch.setattr(odc, "_build_update_plan", lambda *_: plan)

    # simulate "download" by creating local files and returning their paths
    def fake_download(remote_path, folder):
        p = Path(folder) / Path(remote_path).name
        # write placeholder; content irrelevant for this test
        p.write_text("dummy")
        return p

    monkeypatch.setattr(odc, "download_file_with_resume", fake_download)

    # md5 verification always OK
    monkeypatch.setattr(odc, "verify_md5", lambda gz, md5: True)

    # unpack/process: directly call the callback with tiny record(s)
    def fake_unpack_and_process(
        file_name, download_folder, processed_folder, process_callback
    ):
        # emulate SDF extraction: write a minimal record into DB via callback
        data = [
            {
                "CID": 123,
                "Title": "Foo",
                "IUPACName": "bar",
                "MolecularFormula": "C2H6",
                "CanonicalSMILES": "CC",
                "InChIKey": "OTMSDBZUPAUEDD-UHFFFAOYSA-N",
                "InChI": "InChI=1S/C2H6/c1-2/h1-2H3",
                "ExactMass": 30.04695,
                "MolecularWeight": 30.07,
                "MonoisotopicMass": 30.04695,
                "CAS": None,
            }
        ]
        process_callback(data)
        return True

    monkeypatch.setattr(odc, "unpack_and_process_file", fake_unpack_and_process)

    # run update
    ok, fail = odc.update_database(
        database_file=db,
        max_files=None,
        download_folder=str(downloads),
        processed_folder=str(processed),
    )
    assert ok == 1 and fail == 0

    # processed_archives should be recorded
    m = DatabaseManager(db)
    rows = m.query_all("SELECT * FROM processed_archives", [])
    assert rows and rows[0]["status"] == "ingested"

    # and compound_data contains the inserted record
    cd = m.query_one("SELECT * FROM compound_data WHERE CID=123", [])
    assert cd and cd["InChIKey"] == "OTMSDBZUPAUEDD-UHFFFAOYSA-N"
