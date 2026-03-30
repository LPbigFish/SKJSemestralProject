from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Popis chyby")
    status_code: int = Field(..., description="HTTP stavový kód")
