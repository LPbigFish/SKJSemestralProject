from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from repo.db import get_db
from repo.repo import FileRecord, Bucket

from storage_service import (
    generate_file_id,
    save_file,
    delete_file,
    file_exists,
    get_file_path,
)
from schemas.create_file import CreateFile
from schemas.file_list_response import FileListResponse
from schemas.delete_response import DeleteResponse
from schemas.file_metadata import FileMetadata

files_router = APIRouter(prefix="/files")


@files_router.get("/", response_model=FileListResponse, status_code=200)
def get_files(
    x_user_id: Optional[str] = Header(default=None), db: Session = Depends(get_db)
):
    user_id = x_user_id
    query = db.query(FileRecord).filter(FileRecord.is_deleted == False)
    if user_id:
        query = query.filter(FileRecord.user_id == user_id)
    files = query.all()
    return FileListResponse(
        files=[
            FileMetadata(
                id=file.id,
                filename=file.filename,
                size=file.size,
                content_type=file.content_type,
                created_at=file.created_at,
            )
            for file in files
        ],
        total=len(files),
    )


@files_router.get("/{file_id}", status_code=200)
def get_specific_file(
    file_id: str,
    x_user_id: Optional[str] = Header(default=None),
    x_internal_source: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = x_user_id or "default_user"
    record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Soubor nenalezen")
    if record.is_deleted:
        raise HTTPException(status_code=404, detail="Soubor byl smazán")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Přístup odepřen")
    if not file_exists(user_id, file_id):
        raise HTTPException(status_code=404, detail="Soubor chybí na disku")

    bucket = db.query(Bucket).filter(Bucket.id == record.bucket_id).first()
    if bucket:
        is_internal = x_internal_source and x_internal_source.lower() == "true"
        bucket.bandwidth_bytes += record.size
        if is_internal:
            bucket.internal_transfer_bytes += record.size
        else:
            bucket.egress_bytes += record.size
        db.commit()

    return FileResponse(
        path=record.path,
        filename=record.filename,
        media_type=record.content_type or None,
    )


@files_router.delete("/{file_id}", response_model=DeleteResponse, status_code=200)
def delete_specific_file(
    file_id: str,
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = x_user_id or "default_user"
    record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Soubor nenalezen")
    if record.is_deleted:
        raise HTTPException(status_code=404, detail="Soubor již byl smazán")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Přístup odepřen")

    record.is_deleted = True
    db.commit()

    return DeleteResponse(message="Soubor úspěšně smazán (soft delete)", id=file_id)


@files_router.post("/upload", response_model=CreateFile, status_code=201)
def create_file(
    bucket_id: int = Form(...),
    file: UploadFile = File(...),
    x_user_id: Optional[str] = Header(default=None),
    x_internal_source: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    bucket = db.query(Bucket).filter(Bucket.id == bucket_id).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket nenalezen")

    user_id = x_user_id or "default_user"
    file_id = generate_file_id()

    size = save_file(user_id, file_id, file)

    record = FileRecord(
        id=file_id,
        user_id=user_id,
        filename=file.filename or "unknown",
        path=str(get_file_path(user_id, file_id)),
        size=size,
        content_type=file.content_type,
        bucket_id=bucket_id,
    )

    db.add(record)

    is_internal = x_internal_source and x_internal_source.lower() == "true"
    bucket.bandwidth_bytes += size
    bucket.current_storage_bytes += size
    if is_internal:
        bucket.internal_transfer_bytes += size
    else:
        bucket.ingress_bytes += size

    db.commit()
    db.refresh(record)

    return CreateFile(
        id=record.id,
        filename=record.filename,
        size=record.size,
        content_type=record.content_type,
    )
