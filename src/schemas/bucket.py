from pydantic import BaseModel, Field
from datetime import datetime


class BucketCreate(BaseModel):
    name: str = Field(..., description="Název bucketu")


class BucketResponse(BaseModel):
    id: int = Field(..., description="ID bucketu")
    name: str = Field(..., description="Název bucketu")
    created_at: datetime = Field(..., description="Čas vytvoření bucketu")

    model_config = {"from_attributes": True}


class BucketListResponse(BaseModel):
    buckets: list[BucketResponse]
    total: int
