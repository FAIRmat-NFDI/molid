import time
import sqlite3
from simple_progress_bar import update_progress

# Define the input and output file paths
input_files = ["data/test_data.txt"]#, "../data/data_2.txt", "../data/data_3.txt"]  # List of input files
database_file = "data/extracted_data_temp_2.db"

# Fields to extract
fields_to_extract = {
    "SMILES": "PUBCHEM_SMILES",
    "InChIKey": "PUBCHEM_IUPAC_INCHIKEY",
    "InChI": "PUBCHEM_IUPAC_INCHI",
    "CAS": "PUBCHEM_IUPAC_CAS_NAME",
    "Formula": "PUBCHEM_MOLECULAR_FORMULA",
}

def initialize_database(database_file, fields):
    """Initialize the SQLite database and create the table."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    columns = ", ".join([f"{field} TEXT" for field in fields])
    cursor.execute(f"CREATE TABLE IF NOT EXISTS compound_data (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns})")

    conn.commit()
    conn.close()

def save_data_to_db(database_file, extracted_data, fields):
    """Save extracted data to the SQLite database."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    placeholders = ", ".join(["?" for _ in fields])
    insert_query = f"INSERT INTO compound_data ({', '.join(fields)}) VALUES ({placeholders})"
    for data in extracted_data:
        values = [data.get(field, None) for field in fields]
        cursor.execute(insert_query, values)

    conn.commit()
    conn.close()

def process_file(input_file, fields_to_extract):
    """Process a single file and extract data."""
    extracted_data = []

    with open(input_file, "r") as file:
        total_lines = sum(1 for _ in file)

    processed_lines = 0

    with open(input_file, "r") as txt_file:
        compound_data = {}

        for line in txt_file:
            line = line.strip()
            processed_lines += 1

            if line.startswith("> <"):
                property_name = line[3:-1]

                if property_name in fields_to_extract.values():
                    value = txt_file.readline().strip()
                    key = [k for k, v in fields_to_extract.items() if v == property_name][0]
                    compound_data[key] = value

            elif line == "$$$$":
                if compound_data:
                    extracted_data.append(compound_data)
                compound_data = {}

            update_progress(processed_lines / total_lines, barLength=50, digit_to_be_rounded=2)

    return extracted_data

def extract_data_from_files(input_files, database_file, fields_to_extract):
    """Main function to process files and save data to the database."""
    initialize_database(database_file, list(fields_to_extract.keys()))

    all_extracted_data = []
    start_time = time.time()

    for input_file in input_files:
        print(f"Processing file: {input_file}")
        extracted_data = process_file(input_file, fields_to_extract)
        all_extracted_data.extend(extracted_data)

    save_data_to_db(database_file, all_extracted_data, list(fields_to_extract.keys()))

    elapsed_time = time.time() - start_time
    print(f"\nData extraction and saving complete. Data saved to {database_file}")
    print(f"Processing time: {elapsed_time:.2f} seconds")

# Run the extraction function
if __name__ == "__main__":
    extract_data_from_files(input_files, database_file, fields_to_extract)
