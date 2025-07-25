from __future__ import annotations

import click
import json

from molid.db.offline_db_cli import create_offline_db, update_database, use_database
from molid.search.service import SearchService, SearchConfig
from molid.utils.settings import load_config, save_config

@click.group()
def cli() -> None:
    """MolID: PubChem data downloader & search tool"""
    pass

@cli.group()
def config() -> None:
    """Manage MolID configuration"""
    pass

@config.command("set-db")
@click.argument("db_path", type=click.Path())
def set_db(db_path: str) -> None:
    """Set default master database path."""
    save_config(master_db=db_path)
    click.echo(f"✔ Default master_db set to: {db_path}")

@config.command("set-mode")
@click.argument(
    "mode",
    type=click.Choice([
        "offline-basic",
        "offline-advanced",
        "online-only",
        "online-cached"
    ])
)
def set_mode(mode: str) -> None:
    """Set default search mode."""
    save_config(mode=mode)
    click.echo(f"✔ Default mode set to: {mode}")

@config.command("show")
def show_cfg() -> None:
    """Show current MolID configuration."""
    cfg = load_config()
    click.echo(json.dumps(cfg.dict(), indent=2))

@cli.group()
def db() -> None:
    """Manage your offline PubChem database"""
    pass

@db.command("create")
@click.option(
    "--db-file",
    "db_path",
    default=None,
    help="Path to new DB"
)
def db_create(db_path: str | None) -> None:
    """Initialize a new offline DB."""
    cfg = load_config()
    path = db_path or cfg.master_db or "pubchem_data_FULL.db"
    create_offline_db(path)
    click.echo(f"Initialized master DB at {path}")

@db.command("update")
@click.option(
    "--db-file",
    "db_path",
    default=None,
    help="Path to existing DB",
    type=str,
)
@click.option("--max-files", type=int, default=None)
@click.option("--download-folder", type=str, default=None)
@click.option("--processed-folder", type=str, default=None)
def db_update(
    db_path: str | None,
    max_files: int | None,
    download_folder: str | None,
    processed_folder: str | None,
) -> None:
    """Fetch & process new batches into an existing DB."""
    cfg = load_config()
    path = db_path or cfg.master_db
    if not path:
        raise click.UsageError("No DB path set; use `molid config set-db` or `--db-file`.")
    update_database(
        database_file=path,
        max_files=max_files or cfg.max_files,
        download_folder=download_folder or cfg.download_folder,
        processed_folder=processed_folder or cfg.processed_folder,
    )
    click.echo(f"Updated database at {path}")

@db.command("use")
@click.option(
    "--db-file",
    "db_path",
    default=None,
    help="Path to existing DB",
    type=str
)
def db_use(db_path: str | None) -> None:
    """Health check connection to the database."""
    cfg = load_config()
    path = db_path or cfg.master_db
    if not path:
        raise click.UsageError("No DB path set; use `molid config set-db` or `--db-file`.")
    use_database(path)
    click.echo(f"Using master database: {path}")

@cli.command("search")
@click.argument("identifier", type=str)
@click.option(
    "--id-type",
    type=click.Choice([
        "inchikey",
        "smiles",
        "cid",
        "name"
    ]),
    default="inchikey",
)
def do_search(identifier: str, id_type: str) -> None:
    """Search for a molecule by identifier."""
    cfg = load_config()
    if not cfg.master_db:
        raise click.UsageError("No default DB set; use `molid config set-db` first.")
    svc = SearchService(
        master_db=cfg.master_db,
        cache_db=cfg.cache_db,
        cfg=SearchConfig(mode=cfg.mode),
    )
    results, source = svc.search({id_type: identifier})
    click.echo(f"[Source] {source}\n")
    click.echo(json.dumps(results, indent=2))

if __name__ == "__main__":
    cli()
