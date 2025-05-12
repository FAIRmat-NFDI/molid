import requests


def fetch_molecule_data(
    molecule_identifier: str,
    identifier_type: str = "name"
) -> dict:
    """
    Fetch molecule data from the PubChem API.
    Requests a set of standard properties including:
      Title, IUPACName, MolecularFormula, InChI, InChIKey,
      CanonicalSMILES, IsomericSMILES, PUBCHEM_COMPOUND_CID,
      PUBCHEM_EXACT_MASS, PUBCHEM_MOLECULAR_WEIGHT,
      PUBCHEM_SMILES, MonoisotopicMass.
    """
    base_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
    properties = (
        "Title,IUPACName,MolecularFormula,InChI,InChIKey,CanonicalSMILES,"
        "IsomericSMILES,PUBCHEM_COMPOUND_CID,PUBCHEM_EXACT_MASS,"
        "PUBCHEM_MOLECULAR_WEIGHT,PUBCHEM_SMILES,MonoisotopicMass"
    )
    it = identifier_type.lower()
    url = f"{base_url}/{it}/{molecule_identifier}/property/{properties}/JSON"

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()