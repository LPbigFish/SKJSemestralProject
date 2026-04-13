import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, create_engine, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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
""" class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(String, nullable=False, default=datetime.datetime.now(tz=datetime.timezone.utc).isoformat())
 """


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    
    posts: Mapped[list["Post"]] = relationship(back_populates="author")
    
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    author: Mapped["User"] = relationship(back_populates="posts")