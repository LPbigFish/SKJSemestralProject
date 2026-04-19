from pydantic import BaseModel, Field


class BillingResponse(BaseModel):
    bucket_id: int = Field(..., description="ID bucketu")
    bucket_name: str = Field(..., description="Název bucketu")
    bandwidth_bytes: int = Field(..., description="Celkové přenesené bajty (legacy)")
    current_storage_bytes: int = Field(..., description="Aktuální úložiště v bajtech")
    ingress_bytes: int = Field(..., description="Příchozí přenosy v bajtech")
    egress_bytes: int = Field(..., description="Odchozí přenosy v bajtech")
    internal_transfer_bytes: int = Field(..., description="Interní přenosy v bajtech")
