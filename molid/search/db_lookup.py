
from molid.pubchem_api.offline import basic_offline_search


def query_validation_db(
    db_file: str,
    identifier: str
) -> (dict, bool):
    """
    Query the master PubChem dump for a full InChIKey or its 14-char skeleton.
    Returns a tuple (record_dict, matched_full).
    """
    rec = basic_offline_search(db_file, identifier)
    if not rec:
        return None, False
    full = rec.get("InChIKey") == identifier
    return rec, full