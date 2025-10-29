from molid.pubchemproc import pubchem_client as pc
from molid.pubchemproc.fetch import fetch_molecule_data

class _Resp:
    def __init__(self, ok=True, status=200, payload=None, url="http://x", reason="OK"):
        self.ok = ok; self.status_code = status; self._payload = payload or {}
        self.url = url; self.reason = reason
    def json(self): return self._payload
    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            from requests import HTTPError; raise HTTPError(f"{self.status_code} {self.reason}", response=self)

def _mk_session(queue):
    # queue is list of _Resp that will be returned on successive .get calls
    class _S:
        def get(self, *a, **k):
            return queue.pop(0)
    return _S()

def test_fetch_prefers_synonym_cas(monkeypatch):
    # 1) resolve_to_cids → CID 280
    r1 = _Resp(payload={"IdentifierList": {"CID": [280]}})
    # 2) get_properties → no IUPAC yet
    r2 = _Resp(payload={"PropertyTable": {"Properties": [{"CID": 280, "Title": "CO2"}]}})
    # 3) get_pugview (IUPAC fallback)
    r3 = _Resp(payload={"Record": {"Section":[{"TOCHeading":"IUPAC Name","Information":[{"Value":{"StringWithMarkup":[{"String":"carbon dioxide"}]}}]}]}})
    # 4) get_synonyms → contains valid CAS
    r4 = _Resp(payload={"InformationList":{"Information":[{"Synonym":["124-38-9","foo"]}]}})
    # 5) get_xrefs_rn (won’t be used since synonym provided CAS)
    r5 = _Resp(payload={"InformationList":{"Information":[{"RN":["124-38-9"]}]}})
    sess = _mk_session([r1,r2,r3,r4,r5])
    monkeypatch.setattr(pc, "get_session", lambda: sess)

    recs = fetch_molecule_data("inchikey", "CURLTUGMZLYLDI-UHFFFAOYSA-N")
    assert recs and recs[0]["CID"] == 280
    assert recs[0]["IUPACName"] == "carbon dioxide"
    assert recs[0]["CAS"] == "124-38-9"

def test_resolve_404_soft_miss(monkeypatch):
    r1 = _Resp(ok=False, status=404, reason="NotFound")
    sess = _mk_session([r1])
    monkeypatch.setattr(pc, "get_session", lambda: sess)
    recs = fetch_molecule_data("name", "this-does-not-exist")
    assert recs == []
