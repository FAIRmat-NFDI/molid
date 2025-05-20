from molid.db.sqlite_manager import DatabaseManager

def test_initialize_and_query(tmp_path):
    db_file = tmp_path / "db.sqlite"
    mgr = DatabaseManager(str(db_file))
    # schema: single table
    mgr.initialize("CREATE TABLE t(x INTEGER PRIMARY KEY, y TEXT);")
    assert db_file.exists()
    mgr.insert_many("t", ["x","y"], [[1,"a"],[2,"b"]], ignore_conflicts=False)
    assert mgr.exists("t", "x = ?", [1])
    row = mgr.query_one("SELECT y FROM t WHERE x = ?", [2])
    assert row["y"] == "b"
    rows = mgr.query_all("SELECT * FROM t")
    assert len(rows) == 2

def test_insert_many_no_rows(tmp_path, caplog):
    mgr = DatabaseManager(str(tmp_path/"x.db"))
    # Should do nothing and not error
    mgr.insert_many("nonexistent", ["a"], [], ignore_conflicts=True)
