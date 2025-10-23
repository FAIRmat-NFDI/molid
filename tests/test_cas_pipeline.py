from molid.pubchemproc.cache import get_cached_or_fetch
from molid.search.db_lookup import advanced_search
from molid.db.sqlite_manager import DatabaseManager

cache_db = "./pubchem_cache.db"
db = DatabaseManager(cache_db)

# --- Query a multi-CID CAS (expands + caches up to limit) ---
records, from_cache = get_cached_or_fetch(cache_db, "cas", "25322-68-3")
print("Returned records:", len(records))
print("Sample fields first hit:", {k: records[0].get(k) for k in ("CID","CAS","MatchedCAS","Title")})

# cas_mapping should have ALL CIDs PubChem returns (could be > limit)
n_map = db.query_all("SELECT COUNT(*) AS n FROM cas_mapping WHERE CAS='25322-68-3'")[0]["n"]
print("cas_mapping rows for 25322-68-3:", n_map)

# cached_molecules should be <= limit (5 per config)
n_cached = db.query_all("SELECT COUNT(*) AS n FROM cached_molecules")[0]["n"]
print("cached_molecules rows (<=5 expected):", n_cached)

# Derived CAS for a CID view (winner from cas_mapping)
cid0 = records[0]["CID"]
cid_view = advanced_search(cache_db, "cid", str(cid0))[0]
print("CID view derived CAS:", cid_view.get("CAS"))

# The CAS search view exposes what you matched on:
print("MatchedCAS in CAS search:", records[0].get("MatchedCAS"))

records, from_cache = get_cached_or_fetch(cache_db, "cas", "7732-18-5")
print("Water hits:", len(records))
print("First water record:", {k: records[0].get(k) for k in ("CID","CAS","MatchedCAS","Title")})

# cas_mapping should have exactly the single mapping for water (plus whatever else you've inserted)
print("Water mappings:", db.query_all("SELECT * FROM cas_mapping WHERE CAS='7732-18-5'"))

# CID lookup returns derived CAS (7732-18-5 expected)
cid = records[0]["CID"]
print("Water CID derived CAS:", advanced_search(cache_db, "cid", str(cid))[0].get("CAS"))

