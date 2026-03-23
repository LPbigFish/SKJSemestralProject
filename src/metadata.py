"""
Metadata store – ukládá záznamy o souborech jako JSON.

Struktura souboru metadata.json:
{
  "<file_id>": {
    "id":           "uuid",
    "user_id":      "string",
    "filename":     "original_name.txt",
    "path":         "storage/user_id/uuid",
    "size":         1234,
    "content_type": "text/plain",
    "created_at":   "2025-03-23T10:00:00"
  },
  ...
}
"""

import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

METADATA_FILE = Path("metadata.json")

# Zámek pro thread-safe čtení/zápis
_lock = threading.Lock()


def _load() -> dict:
    if not METADATA_FILE.exists():
        return {}
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_record(
    file_id: str,
    user_id: str,
    filename: str,
    path: str,
    size: int,
    content_type: Optional[str],
) -> dict:
    record = {
        "id": file_id,
        "user_id": user_id,
        "filename": filename,
        "path": path,
        "size": size,
        "content_type": content_type,
        "created_at": datetime.utcnow().isoformat(),
    }
    with _lock:
        data = _load()
        data[file_id] = record
        _save(data)
    return record


def get_record(file_id: str) -> Optional[dict]:
    with _lock:
        return _load().get(file_id)


def list_records(user_id: str) -> list[dict]:
    with _lock:
        data = _load()
    return [r for r in data.values() if r["user_id"] == user_id]


def delete_record(file_id: str) -> bool:
    with _lock:
        data = _load()
        if file_id not in data:
            return False
        del data[file_id]
        _save(data)
    return True
