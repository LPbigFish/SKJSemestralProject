from typing import Optional

from fastapi import APIRouter, File, HTTPException, Header, UploadFile
from fastapi.responses import FileResponse

import metadata as db

from storage_service import (
    generate_file_id,
    save_file,
    delete_file,
    file_exists,
    get_file_path,
)

files_router = APIRouter(prefix="/files")

@files_router.get("/", status_code=200)
def get_files(x_user_id: Optional[str] = Header(default=None)):
    user_id = x_user_id or "default_user"
    files = db.list_records(user_id)
    return {"files": files, "total": len(files)}


@files_router.get("/{file_id}", status_code=200)
def get_specific_file(
    file_id: str,
    x_user_id: Optional[str] = Header(default=None),
):
    user_id = x_user_id or "default_user"
    record = db.get_record(file_id)

    if not record:
        raise HTTPException(status_code=404, detail="Soubor nenalezen")
    if record["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Přístup odepřen")
    if not file_exists(user_id, file_id):
        raise HTTPException(status_code=404, detail="Soubor chybí na disku")

    return FileResponse(
        path=record["path"],
        filename=record["filename"],
        media_type=record.get("content_type") or "application/octet-stream",
    )

    
@files_router.delete("/{file_id}", status_code=204)
def delete_specific_file(
    file_id: str,
        x_user_id: Optional[str] = Header(default=None),
    ):
        user_id = x_user_id or "default_user"
        record = db.get_record(file_id)

        if not record:
            raise HTTPException(status_code=404, detail="Soubor nenalezen")
        if record["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Přístup odepřen")

        delete_file(user_id, file_id)
        db.delete_record(file_id)

        return {"message": "Soubor byl smazán", "id": file_id}


@files_router.post("/upload", status_code=201)
def create_file(
    file: UploadFile = File(...),
    x_user_id: Optional[str] = Header(default=None),
):
    user_id = x_user_id or "default_user"
    file_id = generate_file_id()

    size = save_file(user_id, file_id, file)

    record = db.save_record(
        file_id=file_id,
        user_id=user_id,
        filename=file.filename or "unknown",
        path=str(get_file_path(user_id, file_id)),
        size=size,
        content_type=file.content_type,
    )

    return {
        "id": record["id"],
        "filename": record["filename"],
        "size": record["size"],
    }