from pathlib import Path

import pytest

import molid.search.service as svc_mod
from molid.search.service import SearchConfig, SearchService

# Create empty, readable files so the service doesn't skip for missing files
tmp_master = Path("/tmp/master.db")
tmp_master.touch()
tmp_cache = Path("/tmp/cache.db")
tmp_cache.touch()


def make_service(sources, cache_writes=True):
    cfg = SearchConfig(sources=sources, cache_writes=cache_writes)
    return SearchService(master_db=str(tmp_master), cache_db=str(tmp_cache), cfg=cfg)


def test_order_and_skip(monkeypatch):
    order = []
    # pretend the files are readable so tiers aren’t skipped for IO reasons
    monkeypatch.setattr(svc_mod, "_has_readable_file", lambda p: True)

    def m(self, inp):
        order.append("master")
        return ([{"CID": 10}], "master")

    def c(self, inp):
        order.append("cache")
        return ([], "cache")

    def a(self, inp):
        order.append("api")
        return ([{"CID": 99}], "API")

    monkeypatch.setattr(SearchService, "_search_master", m)
    monkeypatch.setattr(SearchService, "_search_cache", c)
    monkeypatch.setattr(SearchService, "_search_api", a)

    svc = make_service(["cache", "master", "api"])
    recs, src = svc.search({"inchikey": "X" * 27})
    assert order == ["cache", "master"]
    assert src == "master"
    assert recs and recs[0]["CID"] == 10


def test_no_sources_configured_raises(monkeypatch, tmp_path):
    svc = SearchService(
        master_db=str(tmp_path / "m.db"),
        cache_db=str(tmp_path / "c.db"),
        cfg=SearchConfig(sources=[]),
    )
    with pytest.raises(ValueError):
        svc.search({"inchikey": "X" * 27})


def test_query_must_have_single_key(monkeypatch, tmp_path):
    svc = SearchService(
        master_db=str(tmp_path / "m.db"),
        cache_db=str(tmp_path / "c.db"),
        cfg=SearchConfig(sources=["api"]),
    )
    with pytest.raises(ValueError):
        svc.search({"inchikey": "A", "smiles": "C"})


def test_pipeline_raw_xyz_parse_failure(monkeypatch):
    from molid.pipeline import search_from_input

    with pytest.raises(ValueError):
        search_from_input("this is not xyz at all")
