from importlib.metadata import PackageNotFoundError, version

from .cli import cli
from .main import run

__all__ = ["run", "cli"]

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # When running from source (not installed), fall back to a default
    __version__ = "0.0.0"
