from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, Union


class FileMetadata(BaseModel):
    id: str = Field(..., description="Unikátní ID souboru")
    filename: str = Field(..., description="Původní název souboru")
    size: int = Field(..., description="Velikost souboru v bytech")
    content_type: Optional[str] = Field(None, description="MIME typ souboru")
    created_at: Union[datetime, str] = Field(..., description="Čas vytvoření souboru")

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_created_at(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
