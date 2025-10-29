from molid.db.db_utils import create_offline_db
from molid.db.sqlite_manager import DatabaseManager
from molid.db.cas_enrich import enrich_cas_for_cids
from molid.db import cas_enrich as ce

def _seed_compounds(db_path):
    m = DatabaseManager(db_path)
    # Two distinct chemistries (different IK14/formula) → same CAS later → generic
    m.executemany("INSERT OR IGNORE INTO compound_data(CID,Title,IUPACName,MolecularFormula,CanonicalSMILES,InChIKey,InChI) VALUES (?,?,?,?,?,?,?)", [
        (1, "poly something", "poly-foo", "C3H6O", "CC(=O)C", "CSCPPACGZOOCGX-UHFFFAOYSA-N", "InChI=1S/C3H6O/c1-3(2)4/h1-2H3"),
        (2, "mixture blend", "bar",      "C2H4O", "CC=O",    "IKHGUXGNUITLKF-UHFFFAOYSA-N", "InChI=1S/C2H4O/c1-2-3/h2H,1H3"),
        (3, "specific",       "baz",      "CO2",   "O=C=O",  "CURLTUGMZLYLDI-UHFFFAOYSA-N", "InChI=1S/CO2/c2-1-3"),
    ])

def test_enrich_generic_downgrade_and_best_cas(tmp_path, monkeypatch):
    db = str(tmp_path / "master.db"); create_offline_db(db); _seed_compounds(db)

    # Monkeypatch the batch fetcher to return:
    #  - RN "999-99-9" for both CIDs 1 & 2 (generic due to multi-chemistry + keywords)
    #  - RN "124-38-9" for CID 3 only (specific)
    def fake_fetch_all_batches(session, batches, timeout_s, max_workers, progress_desc="x"):
        mapping = {1: ["999-99-9"], 2: ["999-99-9"], 3: ["124-38-9"]}
        return mapping, len(batches)
    monkeypatch.setattr(ce, "_fetch_all_batches", fake_fetch_all_batches)

    # Run enrichment on all CIDs; avoid filtering by "missing" to keep it simple
    added = enrich_cas_for_cids(
        db_file=db,
        cids=[1, 2, 3],
        sleep_s=0.0,
        use_synonyms=False,
        timeout_s=1.0,
        retries=0,
        batch_size=100,
        max_workers=1,
        only_missing=False,
    )
    # We care about persisted effects; count can vary with batched WAL/flush
    assert added >= 1

    m = DatabaseManager(db)
    rows_all = m.query_all("SELECT * FROM cas_mapping", [])
    got = { (r["CAS"], r["CID"]) for r in rows_all }
    assert ("124-38-9", 3) in got  # specific RN present

    # After downgrade: generic RN "999-99-9" should have confidence 0
    bad = m.query_all("SELECT confidence FROM cas_mapping WHERE CAS='999-99-9'", [])
    # If present, generic RN must be downgraded to confidence 0
    assert all(int(r["confidence"] or 0) == 0 for r in bad)

    # Best CAS per CID: CIDs 1 and 2 should NOT get a CAS (all 0-confidence)
    cd1 = m.query_one("SELECT CAS FROM compound_data WHERE CID=1", [])
    cd2 = m.query_one("SELECT CAS FROM compound_data WHERE CID=2", [])
    assert cd1["CAS"] in (None, "") and cd2["CAS"] in (None, "")

    # CID 3 should have the specific CAS set
    cd3 = m.query_one("SELECT CAS FROM compound_data WHERE CID=3", [])
    assert cd3["CAS"] == "124-38-9"
