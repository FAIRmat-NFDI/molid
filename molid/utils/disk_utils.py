import psutil
import logging

logger = logging.getLogger(__name__)


def check_disk_space(min_required_gb: float) -> None:
    """Check if sufficient disk space is available."""
    free_space_gb = psutil.disk_usage(".").free / (1024**3)
    if free_space_gb < min_required_gb:
        raise RuntimeError(
            f"Insufficient disk space! {free_space_gb:.2f}GB available, "
            f"but {min_required_gb}GB required."
        )
    logger.info("Disk space check passed: %.2fGB available.", free_space_gb)


def is_disk_space_sufficient(min_required_gb: float) -> bool:
    """Check if there's enough disk space to continue processing."""
    free_space_gb = psutil.disk_usage(".").free / (1024**3)
    return free_space_gb >= min_required_gb
