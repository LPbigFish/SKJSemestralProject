from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from endpoints.broker import _store_message_sync, manager
from repository.db import get_db
from repository.repo import Bucket, FileRecord, ProcessingJob
from schemas.broker import DeliverMessage

process_router = APIRouter(prefix="/buckets")


class ProcessRequest(BaseModel):
    operation: str
    params: dict[str, Any] | None = None


class OperationParam(BaseModel):
    name: str
    type: str
    required: bool
    default: Any | None = None


class OperationInfo(BaseModel):
    operation: str
    params: list[OperationParam]


class ProcessResponse(BaseModel):
    status: str


OPERATION_PARAMS: dict[str, list[OperationParam]] = {
    "invert": [],
    "flip": [],
    "crop": [
        OperationParam(name="top", type="int", required=False, default=0),
        OperationParam(name="left", type="int", required=False, default=0),
        OperationParam(name="bottom", type="int", required=False),
        OperationParam(name="right", type="int", required=False),
    ],
    "brightness": [
        OperationParam(name="value", type="int", required=False, default=0),
    ],
    "grayscale": [],
}

VALID_OPERATIONS = set(OPERATION_PARAMS.keys())


@process_router.get("/operations", response_model=list[OperationInfo])
def get_operations():
    return [
        OperationInfo(operation=op, params=OPERATION_PARAMS[op])
        for op in sorted(OPERATION_PARAMS)
    ]


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

    job = ProcessingJob(
        original_file_id=file_id,
        bucket_id=bucket_id,
        operation=body.operation,
        status="processing",
    )
    db.add(job)
    db.flush()
    job_id = job.id
    payload["job_id"] = job_id
    db.commit()

    msg_id = await run_in_threadpool(_store_message_sync, "image.jobs", payload)

    deliver = DeliverMessage(
        topic="image.jobs", message_id=msg_id, payload=payload
    )
    await manager.broadcast(deliver.model_dump(), "image.jobs")

    return ProcessResponse(status="processing_started")


class JobUpdateRequest(BaseModel):
    status: str
    result_file_id: Optional[str] = None
    error: Optional[str] = None


class JobResult(BaseModel):
    id: int
    operation: str
    status: str
    result_file_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class JobResultList(BaseModel):
    jobs: list[JobResult]
    total: int


@process_router.put(
    "/internal/jobs/{job_id}",
    status_code=200,
)
def update_job_status(
    job_id: int,
    body: JobUpdateRequest,
    x_internal_source: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_internal_source or x_internal_source.lower() != "true":
        raise HTTPException(status_code=403, detail="Přístup odepřen")

    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job nenalezen")

    job.status = body.status
    job.result_file_id = body.result_file_id
    job.error = body.error
    db.commit()

    return {"status": "updated"}


@process_router.get(
    "/{bucket_id}/objects/{file_id}/results",
    response_model=JobResultList,
    status_code=200,
)
def get_processing_results(
    bucket_id: int,
    file_id: str,
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

    jobs = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.original_file_id == file_id,
            ProcessingJob.bucket_id == bucket_id,
        )
        .order_by(ProcessingJob.id.desc())
        .all()
    )

    return JobResultList(
        jobs=[
            JobResult(
                id=j.id,
                operation=j.operation,
                status=j.status,
                result_file_id=j.result_file_id,
                error=j.error,
                created_at=j.created_at.isoformat() if j.created_at else "",
                updated_at=j.updated_at.isoformat() if j.updated_at else "",
            )
            for j in jobs
        ],
        total=len(jobs),
    )
