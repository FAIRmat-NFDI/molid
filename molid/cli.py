from __future__ import annotations

import os
import click
import json
import logging
from logging import StreamHandler, FileHandler, Formatter

from molid.db.offline_db_cli import update_database, use_database, enrich_cas_database
from molid.db.db_utils import create_offline_db
from molid.search.service import SearchService, SearchConfig
from molid.pipeline import search_from_file
from molid.utils.settings import load_config, save_config

def _setup_logging(level: str, logfile: str | None) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(lvl)
    # Clear default handlers if any
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if logfile:
        fh = FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

@click.group()
@click.option("--log-level", type=click.Choice(["DEBUG","INFO","WARNING","ERROR","CRITICAL"]),
              default="INFO", show_default=True,
              help="Set logging verbosity.")
@click.option("--log-file", type=click.Path(dir_okay=False, writable=True), default=None,
              help="Also write logs to this file.")
def cli(log_level: str, log_file: str | None) -> None:
    """MolID: PubChem data downloader & search tool"""
    _setup_logging(log_level, log_file)

@cli.group()
def config() -> None:
    """Manage MolID configuration"""
    pass

@config.command("set-master")
@click.argument("db_path", type=click.Path())
def set_db(db_path: str) -> None:
    """Set default master database path."""
    save_config(master_db=db_path)
    click.echo(f"Default master_db set to: {db_path}")

@config.command("set-mode")
@click.argument(
    "mode",
    type=click.Choice([
        "offline-basic",
        "offline-advanced",
        "online-only",
        "online-cached",
        "auto"
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
    try:
        payload = cfg.model_dump()  # pydantic v2
    except AttributeError:
        payload = cfg.dict()        # pydantic v1
    click.echo(json.dumps(payload, indent=2))

@config.command("set-cache")
@click.argument("db_path", type=click.Path())
def set_cache(db_path: str) -> None:
    """Set default cache database path."""
    save_config(cache_db=db_path)
    click.echo(f"Default cache_db set to: {db_path}")

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
    final_path = db_path or cfg.master_db or "pubchem_data_FULL.db"
    create_offline_db(final_path)
    click.echo(f"Initialized master DB at {final_path}")

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
        raise click.UsageError("No DB path set; use `molid config set-master` or `--db-file`.")
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
        raise click.UsageError("No DB path set; use `molid config set-master` or `--db-file`.")
    use_database(path)
    click.echo(f"Using master database: {path}")

@db.command("enrich-cas")
@click.option("--db-file", "db_path", default=None, type=str, help="Path to master DB")
@click.option("--from-cid", type=int, default=None, help="Start from this CID (inclusive)")
@click.option("--limit", type=int, default=None, help="Max number of CIDs to enrich")
@click.option("--synonyms/--no-synonyms", default=False, help="Also mine CAS from synonyms (validated)")
@click.option("--sleep", "sleep_s", type=float, default=0.2, help="Delay between API calls (s)")
@click.option("--timeout", "timeout_s", type=float, default=30.0, help="HTTP timeout (s)")
@click.option("--retries", type=int, default=3, help="HTTP retries for transient failures")
def db_enrich_cas(db_path: str | None, from_cid: int | None, limit: int | None, synonyms: bool, sleep_s: float, timeout_s: float, retries: int):
    """Backfill CAS↔CID mapping into the master DB via PubChem xref/RN (and optional synonyms)."""
    cfg = load_config()
    path = db_path or cfg.master_db
    if not path:
        raise click.UsageError("No DB path set; use `molid config set-master` or `--db-file`.")
    enrich_cas_database(
        database_file=path,
        from_cid=from_cid,
        limit=limit,
        use_synonyms=synonyms,
        sleep_s=sleep_s,
        timeout_s=timeout_s,
        retries=retries
    )
    click.echo(f"CAS enrichment completed for {path}")

@cli.command("search")
@click.argument("identifier", type=str)
@click.option(
    "--id-type",
    type=click.Choice([
        "inchikey",
        "smiles",
        "cid",
        "name",
        "molecularformula",
        "cas"
    ]),
    default="inchikey",
)
def do_search(identifier: str, id_type: str) -> None:
    """Search for a molecule by identifier."""
    cfg = load_config()
    if cfg.mode == "offline-basic" and not cfg.master_db:
        raise click.UsageError("No default master DB; use `molid config set-master` first.")
    if cfg.mode == "offline-advanced" and not cfg.cache_db:
        raise click.UsageError("No default cache DB; use `molid config set-cache` first.")
    # If the user passed a readable file path, treat it as file input.
    # This ensures .xyz/.extxyz/.sdf go through the pipeline (and optional OpenBabel path).
    if os.path.isfile(identifier):
        try:
            results, source = search_from_file(identifier)
        except RuntimeError as e:
            # Friendly message when OpenBabel is missing for XYZ/Atoms conversion
            click.echo(f"ERROR: {e}")
            return
    else:
        svc = SearchService(
            master_db=cfg.master_db,
            cache_db=cfg.cache_db,
            cfg=SearchConfig(mode=cfg.mode),
        )
        try:
            results, source = svc.search({id_type: identifier})
        except RuntimeError as e:
            click.echo(f"ERROR: {e}")
            return
    click.echo(f"[Source] {source}\n")
    click.echo(json.dumps(results, indent=2))

@config.command("set-cas-expand")
@click.argument("enabled", type=bool)
def set_cas_expand(enabled: bool) -> None:
    """Enable or disable automatic CAS expansion/caching."""
    save_config(cas_expand_cache=enabled)
    click.echo(f"CAS expand caching set to: {enabled}")

@config.command("set-cas-limit")
@click.argument("limit", type=int)
def set_cas_limit(limit: int) -> None:
    """Set max number of CIDs to cache during CAS expansion."""
    save_config(cas_expand_cache_limit=limit)
    click.echo(f"CAS expand cache limit set to: {limit}")

if __name__ == "__main__":
    cli()
