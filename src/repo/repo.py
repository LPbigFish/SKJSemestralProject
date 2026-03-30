import datetime
from typing import Optional

from sqlalchemy import Boolean, create_engine, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

"""
Struktura záznamu v databázi:
  "<file_id>": {
    "id":           "uuid",
    "user_id":      "string",
    "filename":     "original_name.txt",
    "path":         "storage/user_id/uuid",
    "size":         1234,
    "content_type": "text/plain",
    "created_at":   "2025-03-23T10:00:00"
  }
"""
class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=datetime.datetime.now(tz=datetime.timezone.utc).isoformat())