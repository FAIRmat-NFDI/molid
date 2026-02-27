from molid.pubchemproc.cache import get_cached_or_fetch
from molid.db.db_utils import create_cache_db, create_offline_db
from molid.db.sqlite_manager import DatabaseManager
import molid.pubchemproc.pubchem_client as pc
from molid.search.db_lookup import master_lookup_by_cas, advanced_search


def test_read_then_write_through(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.db")
    create_cache_db(db)

    # 1) No cache → fetch → store
    def fake_resolve_to_cids(id_type, id_value):
        return [280]

    def fake_get_properties(cid, props):
        return [
            {
                "CID": 280,
                "Title": "Carbon Dioxide",
                "InChIKey": "CURLTUGMZLYLDI-UHFFFAOYSA-N",
                "MolecularFormula": "CO2",
                "CanonicalSMILES": "C(=O)=O",
            }
        ]

    monkeypatch.setattr(
        "molid.pubchemproc.pubchem_client.resolve_to_cids", fake_resolve_to_cids
    )
    monkeypatch.setattr(
        "molid.pubchemproc.pubchem_client.get_properties", fake_get_properties
    )

    recs, from_cache = get_cached_or_fetch(
        db, "inchikey", "CURLTUGMZLYLDI-UHFFFAOYSA-N"
    )
    assert recs and from_cache is False

    # 2) Now present → read-through
    recs2, from_cache2 = get_cached_or_fetch(
        db, "inchikey", "CURLTUGMZLYLDI-UHFFFAOYSA-N"
    )
    assert recs2 and from_cache2 is True


def test_cas_mapping_written_but_not_row_cas(tmp_path, monkeypatch):
    db = str(tmp_path / "cache2.db")
    create_cache_db(db)
    # Full flow: resolve→properties→store (no network)
    monkeypatch.setattr(pc, "resolve_to_cids", lambda id_type, id_value: [50])
    monkeypatch.setattr(
        pc,
        "get_properties",
        lambda cid, props: [
            {
                "CID": 50,
                "Title": "Foo",
                "InChIKey": "AAAAAAAAAAAAAA-UHFFFAOYSA-N",
                "MolecularFormula": "C2H6",
                "CanonicalSMILES": "CC",
            }
        ],
    )
    recs, from_cache = get_cached_or_fetch(db, "cas", "50-00-0")
    assert recs  # regardless of cache hit/miss
    cid = recs[0]["CID"]
    # Mapping exists for the returned CID, and row has no CAS column
    m = DatabaseManager(db)
    rows = m.query_all(
        "SELECT * FROM cas_mapping WHERE CAS=? AND CID=?", ["50-00-0", cid]
    )
    assert rows
    rows2 = m.query_all("SELECT * FROM cached_molecules WHERE CID=?", [cid])
    assert rows2 and "CAS" not in rows2[0]


def _seed_master(db):
    m = DatabaseManager(db)
    # 2 compounds with different IK14 to exercise generic vs specific later if needed
    m.executemany(
        "INSERT OR IGNORE INTO compound_data(CID,Title,IUPACName,MolecularFormula,CanonicalSMILES,InChIKey,InChI) VALUES (?,?,?,?,?,?,?)",
        [
            (
                100,
                "Acetone",
                "propan-2-one",
                "C3H6O",
                "CC(=O)C",
                "CSCPPACGZOOCGX-UHFFFAOYSA-N",
                "InChI=1S/C3H6O/c1-3(2)4/h1-2H3",
            ),
            (
                101,
                "Acetaldehyde",
                "ethanal",
                "C2H4O",
                "CC=O",
                "IKHGUXGNUITLKF-UHFFFAOYSA-N",
                "InChI=1S/C2H4O/c1-2-3/h2H,1H3",
            ),
        ],
    )
    # CAS mapping: same CAS for two to show ordering, synonym should win over xref
    m.executemany(
        "INSERT OR IGNORE INTO cas_mapping(CAS,CID,source,confidence) VALUES (?,?,?,?)",
        [
            ("67-64-1", 100, "synonym", 2),
            ("67-64-1", 101, "xref", 2),
        ],
    )


def _seed_cache(db):
    m = DatabaseManager(db)
    m.executemany(
        "INSERT OR IGNORE INTO cached_molecules(CID,Title,InChIKey,MolecularFormula,CanonicalSMILES) VALUES (?,?,?,?,?)",
        [
            (200, "CO2", "CURLTUGMZLYLDI-UHFFFAOYSA-N", "CO2", "C(=O)=O"),
        ],
    )
    m.executemany(
        "INSERT OR IGNORE INTO cas_mapping(CAS,CID,source,confidence) VALUES (?,?,?,?)",
        [
            ("124-38-9", 200, "xref", 2),
        ],
    )


def test_master_lookup_by_cas_prefers_synonym(tmp_path):
    db = str(tmp_path / "master.db")
    create_offline_db(db)
    _seed_master(db)
    rows = master_lookup_by_cas(db, "67-64-1")
    assert rows and rows[0]["CID"] == 100  # synonym row wins over xref row


def test_cache_advanced_search_cas_join(tmp_path):
    db = str(tmp_path / "cache.db")
    create_cache_db(db)
    _seed_cache(db)
    rows = advanced_search(db, "CAS", "124-38-9")
    assert rows and rows[0]["CID"] == 200
    # Ensure derived CAS is present in projection
    assert rows[0]["CAS"] == "124-38-9"
