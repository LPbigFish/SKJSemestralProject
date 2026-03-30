from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Header, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from repo.db import get_db
from repo.repo import FileRecord

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
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id
    files = db.query(FileRecord).filter(FileRecord.user_id == user_id).all() if user_id else db.query(FileRecord).all()
    return FileListResponse(files=[
        FileMetadata(
            id=file.id,
            filename=file.filename,
            size=file.size,
            content_type=file.content_type,
            created_at=file.created_at
        ) for file in files
    ], total=len(files))


@files_router.get("/{file_id}", status_code=200)
def get_specific_file(
    file_id: str,
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Soubor nenalezen")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Přístup odepřen")
    if not file_exists(user_id, file_id):
        raise HTTPException(status_code=404, detail="Soubor chybí na disku")

    return FileResponse(
        path=record.path,
        filename=record.filename,
        media_type=record.content_type or None,
    )

    
@files_router.delete("/{file_id}", response_model=DeleteResponse, status_code=200)
def delete_specific_file(
        file_id: str,
        x_user_id: Optional[str] = Header(default=None),
        db: Session = Depends(get_db)
    ):
        user_id = x_user_id or "default_user"
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not record:
            raise HTTPException(status_code=404, detail="Soubor nenalezen")
        if record.user_id != user_id:
            raise HTTPException(status_code=403, detail="Přístup odepřen")

        delete_file(user_id, file_id)
        db.delete(record)
        db.commit()

        return DeleteResponse(message="Soubor úspěšně smazán", id=file_id)


@files_router.post("/upload", response_model=CreateFile, status_code=201)
def create_file(
    file: UploadFile = File(...),
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    file_id = generate_file_id()

    size = save_file(user_id, file_id, file)

    record = FileRecord(
        file_id=file_id,
        user_id=user_id,
        filename=file.filename or "unknown",
        path=str(get_file_path(user_id, file_id)),
        size=size,
        content_type=file.content_type,
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)

    return CreateFile(
        id=record.id,
        filename=record.filename,
        size=record.size,
        content_type=record.content_type,
    )