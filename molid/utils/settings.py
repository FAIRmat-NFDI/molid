from __future__ import annotations

from appdirs import user_cache_dir, user_data_dir
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from appdirs import user_cache_dir, user_data_dir

# Persisted env-file in the user's home directory
ENV_FILE = Path.home() / ".molid.env"

class AppConfig(BaseSettings):
    """
    Application configuration for MolID, loaded via Pydantic BaseSettings.
    Persists overrides in ~/.molid.env
    """
    master_db: str = Field(
        str(Path(user_data_dir("molid")) / "master" / "pubchem_master.db"),
        description="Path to the master PubChem database"
        )
    cache_db: str = Field(
        str(Path(user_data_dir("molid")) / "cache" / "pubchem_cache.db"),
        description="Path to the PubChem cache database"
        )
    mode: Literal[
        "offline-basic",
        "offline-advanced",
        "online-only",
        "online-cached",
        "auto"
        ] = Field(
            "online-cached",
            description="Search mode"
            )
    auto_priority: list[str] = Field(
        default_factory=lambda: ["offline-basic", "online-cached", "online-only"],
        description="Fallback order when mode=='auto'"
    )
    download_folder: str = Field(
        str(Path(user_cache_dir("molid")) / "downloads"),
        description="Where to cache PubChem SDF archives"
        )
    processed_folder: str = Field(
        str(Path(user_data_dir("molid")) / "processed"),
        description="Where to unpack and stage SDF files"
        )
    max_files: int | None = Field(
        None,
        description="Default maximum number of SDF files to process (None = all)"
    )
    model_config = SettingsConfigDict(
        env_prefix="MOLID_",
        env_file=str(ENV_FILE),
    )

def load_config() -> AppConfig:
    """Load application configuration from environment and ~/.molid.env"""
    return AppConfig()

def save_config(**kwargs) -> None:
    """
    Persist the given settings into ~/.molid.env so that Pydantic will load them next time.
    Usage: save_config(master_db="/path/to/db", mode="offline-basic")
    """
    lines: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            if raw.strip() and not raw.startswith("#") and "=" in raw:
                k, v = raw.split("=", 1)
                lines[k] = v

    for key, val in kwargs.items():
        env_key = f"MOLID_{key.upper()}"
        lines[env_key] = str(val)

    ENV_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in lines.items())
    )
