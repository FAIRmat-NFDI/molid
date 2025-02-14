import gzip
import shutil
from pathlib import Path

def validate_gz_file(gz_file_path):
    """Validate the integrity of a .gz file."""
    try:
        with gzip.open(gz_file_path, "rb") as gz_file:
            while gz_file.read(1024):
                pass
        print(f"[INFO] Validated: {gz_file_path.name}")
        return True
    except Exception as e:
        print(f"[ERROR] Invalid .gz file: {gz_file_path.name} - {e}")
        return False

def unpack_gz_file(gz_file_path, output_folder):
    """Unpack a .gz file into the specified folder."""
    extracted_file_path = Path(output_folder) / gz_file_path.stem
    try:
        with gzip.open(gz_file_path, "rb") as gz_file:
            with open(extracted_file_path, "wb") as output_file:
                shutil.copyfileobj(gz_file, output_file)
        print(f"[INFO] Unpacked: {gz_file_path.name}")
        return extracted_file_path
    except Exception as e:
        print(f"[ERROR] Failed to unpack {gz_file_path.name}: {e}")
        return None

def cleanup_files(*paths):
    """Delete specified files or directories."""
    for path in paths:
        path = Path(path)
        if path.exists():
            if path.is_file():
                path.unlink()
                print(f"[INFO] File deleted: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"[INFO] Directory deleted: {path}")

def move_file(source, destination):
    """Move a file to a new location."""
    source_path = Path(source)
    destination_path = Path(destination)
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        print(f"[INFO] Moved file from {source_path} to {destination_path}")
    except Exception as e:
        print(f"[ERROR] Failed to move {source_path}: {e}")
