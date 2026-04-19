from pydantic import BaseModel, Field
from typing import List
from .file_metadata import FileMetadata


class BucketObjectListResponse(BaseModel):
    bucket_id: int = Field(..., description="ID bucketu")
    files: List[FileMetadata] = Field(..., description="Seznam objektů v bucketu")
    total: int = Field(..., description="Celkový počet objektů")
