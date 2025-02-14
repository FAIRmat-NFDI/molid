import os
from ase import Atoms
from ase.io import read
from molid.utils.conversion import convert_xyz_to_inchikey, atoms_to_inchikey
from molid.db.search import query_database


def query_pubchem_database(input_data, database_file):
    """
    Queries a PubChem database using an XYZ molecular structure file.

    Args:
        input_data (str or ase.Atoms): Path to an XYZ file or an ASE Atoms object.
        database_file (str): Path to the SQLite PubChem database file.

    Returns:
        tuple: (InChIKey, results) where:
            - InChIKey (str): The converted InChIKey from the XYZ file.
            - results (list): List of matching records from the database.
    """
    if not os.path.exists(database_file):
        raise FileNotFoundError(f"[ERROR] The specified database file does not exist: {database_file}")
    if isinstance(input_data, str):  # Assume it's an XYZ file
        # Read the XYZ file
        with open(input_data, "r") as file:
            xyz_content = file.read()
        # Convert XYZ to InChIKey
        inchikey = convert_xyz_to_inchikey(xyz_content)
    elif isinstance(input_data, Atoms):
        inchikey = atoms_to_inchikey(input_data)
    else:
        raise TypeError("input_data must be a file path (str) or an ASE Atoms object.")

    # Query the database
    results = query_database(database_file, "InChIKey", inchikey)

    return inchikey, results

def display_results(inchikey, results):
    """
    Displays query results in a readable format.

    Args:
        inchikey (str): The InChIKey corresponding to the queried molecule.
        results (list): List of matching records from the database.
    """
    print(f"\n**InChIKey:** {inchikey}")

    if results:
        print("\n**[RESULTS FOUND]**")
        for row in results:
            print("\n--- **Compound Information** ---")
            print(f"**SMILES:** {row[2] if len(row) > 2 else 'N/A'}")
            print(f"**InChI:** {row[3] if len(row) > 3 else 'N/A'}")
            print(f"**CAS Number:** {row[4] if len(row) > 4 else 'N/A'}")
    else:
        print("\n⚠️ **[WARNING]** No data found for the given InChIKey in the database.")

def main():
    """CLI tool to query a PubChem database using an XYZ molecular structure file."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Query a PubChem database using an XYZ molecular structure file."
    )
    parser.add_argument(
        "xyz_file", type=str,
        help="Path to the XYZ molecular structure file (e.g., example.xyz)."
    )
    parser.add_argument(
        "database_file", type=str,
        help="Path to the SQLite PubChem database file."
    )

    args = parser.parse_args()

    try:
        # Process the XYZ file and query the database
        inchikey, results = query_pubchem_database(args.xyz_file, args.database_file)

        # Display results in a readable format
        display_results(inchikey, results)

    except Exception as e:
        print(f"\n**[ERROR]** {e}")

if __name__ == "__main__":
    main()