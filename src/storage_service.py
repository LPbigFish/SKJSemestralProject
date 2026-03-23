"""
Operace se soubory na disku.

Struktura adresáře:
  storage/
    <user_id>/
      <file_id>        ← obsah souboru (bez přípony, název = UUID)
"""

import uuid
from pathlib import Path
from fastapi import UploadFile

STORAGE_ROOT = Path("storage")
CHUNK_SIZE = 1024 * 1024  # 1 MB


def generate_file_id() -> str:
    return str(uuid.uuid4())


def get_file_path(user_id: str, file_id: str) -> Path:
    return STORAGE_ROOT / user_id / file_id


def save_file(user_id: str, file_id: str, upload: UploadFile) -> int:
    """Uloží soubor na disk, vrátí velikost v bajtech."""
    dest = get_file_path(user_id, file_id)
    dest.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with open(dest, "wb") as out:
        while chunk := upload.file.read(CHUNK_SIZE):
            out.write(chunk)
            total += len(chunk)
    return total


def delete_file(user_id: str, file_id: str) -> bool:
    """Smaže soubor, vrátí True pokud existoval."""
    path = get_file_path(user_id, file_id)
    if path.exists():
        path.unlink()
        return True
    return False


def file_exists(user_id: str, file_id: str) -> bool:
    return get_file_path(user_id, file_id).exists()
