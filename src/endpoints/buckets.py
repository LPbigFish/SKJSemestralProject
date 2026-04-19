from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from repo.db import get_db
from repo.repo import Bucket, FileRecord
from schemas.bucket import BucketCreate, BucketResponse
from schemas.bucket_object_list import BucketObjectListResponse
from schemas.file_metadata import FileMetadata
from schemas.billing import BillingResponse

buckets_router = APIRouter(prefix="/buckets")


@buckets_router.post("/", response_model=BucketResponse, status_code=201)
def create_bucket(bucket_data: BucketCreate, db: Session = Depends(get_db)):
    existing = db.query(Bucket).filter(Bucket.name == bucket_data.name).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Bucket s tímto názvem již existuje"
        )

    bucket = Bucket(name=bucket_data.name)
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket


@buckets_router.get(
    "/{bucket_id}/objects/", response_model=BucketObjectListResponse, status_code=200
)
def list_bucket_objects(bucket_id: int, db: Session = Depends(get_db)):
    bucket = db.query(Bucket).filter(Bucket.id == bucket_id).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket nenalezen")

    files = (
        db.query(FileRecord)
        .filter(FileRecord.bucket_id == bucket_id, FileRecord.is_deleted == False)
        .all()
    )
    return BucketObjectListResponse(
        bucket_id=bucket_id,
        files=[
            FileMetadata(
                id=f.id,
                filename=f.filename,
                size=f.size,
                content_type=f.content_type,
                created_at=f.created_at,
            )
            for f in files
        ],
        total=len(files),
    )


@buckets_router.get(
    "/{bucket_id}/billing/", response_model=BillingResponse, status_code=200
)
def get_bucket_billing(bucket_id: int, db: Session = Depends(get_db)):
    bucket = db.query(Bucket).filter(Bucket.id == bucket_id).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket nenalezen")

    return BillingResponse(
        bucket_id=bucket.id,
        bucket_name=bucket.name,
        bandwidth_bytes=bucket.bandwidth_bytes,
        current_storage_bytes=bucket.current_storage_bytes,
        ingress_bytes=bucket.ingress_bytes,
        egress_bytes=bucket.egress_bytes,
        internal_transfer_bytes=bucket.internal_transfer_bytes,
    )
