from pydantic import BaseModel, Field


class DeleteResponse(BaseModel):
    message: str = Field(..., description="Zpráva o výsledku operace")
    id: str = Field(..., description="ID smazaného souboru")
