from __future__ import annotations

import requests
from typing import Any
from urllib.parse import quote


def fetch_molecule_data(
    id_type: str,
    id_value: str,
    properties: tuple = (
        "CID", "Title", "IUPACName", "MolecularFormula", "InChI", "InChIKey",
        "ConnectivitySMILES", "SMILES", "XLogP", "ExactMass",
        "MonoisotopicMass", "TPSA", "Complexity", "Charge"
    ),
) -> list[dict[str, Any]]:
    """
    Fetch molecule data from the PubChem API.
    Requests a set of standard properties including:
      cid, name, smiles, inchi, inchikey, formula, sourceid/cas
    """
    ns = {
        "cas": "xrefs/rn"
    }.get(id_type, id_type)

    # Join and URL‐encode the property list
    props_str = ",".join(properties)
    safe_value = quote(str(id_value), safe="")
    url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
        f"{ns}/{safe_value}/property/{props_str}/JSON"
    )

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("PropertyTable", {}).get("Properties", [])
    return data if data else []