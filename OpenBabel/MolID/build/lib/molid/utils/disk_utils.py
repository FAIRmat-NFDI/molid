import psutil

def check_disk_space(min_required_gb):
    """Check if sufficient disk space is available."""
    free_space_gb = psutil.disk_usage('.').free / (1024 ** 3)
    if free_space_gb < min_required_gb:
        raise RuntimeError(f"Insufficient disk space! {free_space_gb:.2f}GB available, but {min_required_gb}GB required.")
    print(f"[INFO] Disk space check passed: {free_space_gb:.2f}GB available.")

def is_disk_space_sufficient(min_required_gb):
    """Check if there's enough disk space to continue processing."""
    free_space_gb = psutil.disk_usage('.').free / (1024 ** 3)
    return free_space_gb >= min_required_gb
