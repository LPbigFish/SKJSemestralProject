from pydantic import BaseModel, Field
from typing import List
from .file_metadata import FileMetadata


class FileListResponse(BaseModel):
    files: List[FileMetadata] = Field(..., description="Seznam souborů uživatele")
    total: int = Field(..., description="Celkový počet souborů")
