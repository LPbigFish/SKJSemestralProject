from typing import Optional

from pydantic import BaseModel, Field


class CreateFile(BaseModel):
    id: str = Field(..., description="Unikátní ID souboru")
    filename: str = Field(..., description="Původní název souboru")
    size: int = Field(..., description="Velikost souboru v bytech")
    content_type: Optional[str] = Field(None, description="MIME typ souboru")
