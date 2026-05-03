from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from endpoints.broker import _store_message_sync, manager
from repository.db import get_db
from repository.repo import Bucket, FileRecord
from schemas.broker import DeliverMessage

process_router = APIRouter(prefix="/buckets")


class ProcessRequest(BaseModel):
    operation: str
    params: dict[str, Any] | None = None


class ProcessResponse(BaseModel):
    status: str


VALID_OPERATIONS = {"invert", "flip", "crop", "brightness", "grayscale"}


@process_router.post(
    "/{bucket_id}/objects/{file_id}/process",
    response_model=ProcessResponse,
    status_code=202,
)
async def process_object(
    bucket_id: int,
    file_id: str,
    body: ProcessRequest,
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    bucket = db.query(Bucket).filter(Bucket.id == bucket_id).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket nenalezen")

    record = (
        db.query(FileRecord)
        .filter(
            FileRecord.id == file_id,
            FileRecord.bucket_id == bucket_id,
            FileRecord.is_deleted == False,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Objekt nenalezen")

    user_id = x_user_id or "default_user"

    if body.operation not in VALID_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operation: {body.operation}. "
                   f"Supported: {', '.join(sorted(VALID_OPERATIONS))}",
        )

    payload = {
        "bucket_id": bucket_id,
        "file_id": file_id,
        "user_id": record.user_id,
        "operation": body.operation,
        "params": body.params or {},
        "filename": record.filename,
    }

    msg_id = await run_in_threadpool(_store_message_sync, "image.jobs", payload)

    deliver = DeliverMessage(
        topic="image.jobs", message_id=msg_id, payload=payload
    )
    await manager.broadcast(deliver.model_dump(), "image.jobs")

    return ProcessResponse(status="processing_started")
