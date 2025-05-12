import argparse
import yaml
import sys

from molid.db.db_manager import update_database
from molid.search.service import SearchService, SearchConfig


def load_config(path: str = "config.yaml") -> dict:
    """
    Load the YAML configuration file.
    """
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[ERROR] Configuration file not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[ERROR] Failed to parse YAML: {e}")
        sys.exit(1)


def main():
    # Load configuration
    cfg_dict = load_config()
    master_db = cfg_dict.get("master_db")
    cache_db = cfg_dict.get("cache_db")
    mode = cfg_dict.get("mode", "offline-basic")
    cache_enabled = cfg_dict.get("cache_enabled", False)

    # Build SearchConfig
    search_cfg = SearchConfig(mode=mode, cache_enabled=cache_enabled)

    # CLI setup
    parser = argparse.ArgumentParser(description="MolID: update database or search molecules")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 'update' command
    upd = subparsers.add_parser("update", help="Download and process PubChem SDF files into the master DB")
    upd.add_argument(
        "--db-file", default=master_db, help="Path to master database file"
    )
    upd.add_argument(
        "--max-files", type=int, default=None, help="Maximum number of files to process"
    )
    upd.add_argument(
        "--download-folder", default="downloads", help="Directory for raw .gz downloads"
    )
    upd.add_argument(
        "--processed-folder", default="processed", help="Directory for unpacked SDFs"
    )

    # 'search' command
    sch = subparsers.add_parser("search", help="Search for a molecule by identifier")
    sch.add_argument(
        "identifier", help="Molecule identifier (InChIKey, SMILES, etc.)"
    )
    sch.add_argument(
        "--id-type", default="inchikey", help="Identifier type: inchikey, name, smi, etc."
    )

    args = parser.parse_args()

    if args.command == "update":
        update_database(
            database_file=args.db_file,
            max_files=args.max_files,
            download_folder=args.download_folder,
            processed_folder=args.processed_folder,
        )
    elif args.command == "search":
        service = SearchService(
            master_db=master_db,
            cache_db=cache_db,
            cfg=search_cfg,
        )
        try:
            result, source = service.search(args.identifier, args.id_type)
            print(f"[Source] {source}\n")
            # Pretty-print the result dict
            import json
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"[ERROR] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
