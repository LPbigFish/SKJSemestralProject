from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class FileMetadata(BaseModel):
    id: str = Field(..., description="Unikátní ID souboru")
    filename: str = Field(..., description="Původní název souboru")
    size: int = Field(..., description="Velikost souboru v bytech")
    content_type: Optional[str] = Field(None, description="MIME typ souboru")
    created_at: datetime = Field(..., description="Čas vytvoření souboru")
