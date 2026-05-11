"""
endpoints/files.py
==================
S3 Gateway - sprava souboru.

  - POST /files/upload         -> Haystack async upload (202 Accepted)
  - GET  /files/{file_id}      -> cteni pres Haystack Node (pokud volume_id je nastaveno)
  - DELETE /files/{file_id}    -> soft delete
  - GET  /files/internal/volume/{volume_id}/objects  -> pro compact.py
  - POST /files/internal/bulk-update-location        -> pro compact.py

Na pozadi bezi storage_ack_listener(), ktery nasloucha na storage.ack
a aktualizuje DB zaznamy.
"""

import asyncio
import json
import logging
import os
from typing import Optional

import httpx
import msgpack
import websockets
from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from broker_client import publish_to_broker
from repository.db import get_db, get_sync_session
from repository.repo import Bucket, FileRecord
from schemas.create_file import CreateFile
from schemas.delete_response import DeleteResponse
from schemas.file_list_response import FileListResponse
from schemas.file_metadata import FileMetadata
from storage_service import generate_file_id

log = logging.getLogger(__name__)

files_router = APIRouter(prefix="/files")

HAYSTACK_URL: str = os.environ.get("HAYSTACK_URL", "http://localhost:8081")
BROKER_URI: str = os.environ.get("BROKER_URI", "ws://localhost:8082/broker")


# -- Pozadi: ACK listener ---------------------------------------------------

async def storage_ack_listener():
    """
    Nasloucha na storage.ack a po obdrzeni potvrzeni od Haystack Node:
      1. Aktualizuje volume_id, haystack_offset, haystack_size v DB
      2. Zmeni status na "ready"
      3. Zaucntuje billing (storage bytes)
    Spoustet jako asyncio.create_task() pri startu aplikace.
    """
    import endpoints.files as _self
    reconnect_delay = 2

    while True:
        try:
            current_broker_uri = _self.BROKER_URI
            log.info("ACK listener: pripojuji se k brokeru %s", current_broker_uri)
            async with websockets.connect(
                current_broker_uri,
                max_queue=None,
                compression=None,
                ping_interval=None,
                ping_timeout=None,
            ) as ws:
                sub: bytes = msgpack.packb({"action": "subscribe", "topic": "storage.ack"})  # type: ignore[assignment]
                await ws.send(sub)
                log.info("ACK listener: subscribovan na storage.ack")
                reconnect_delay = 2

                async for raw in ws:
                    try:
                        msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
                    except Exception as e:
                        log.error("ACK listener: chyba dekodovani: %s", e)
                        continue

                    action = msg.get("action", "")
                    if action == "subscribed":
                        continue

                    if action == "deliver":
                        message_id = msg.get("message_id")
                        payload = msg.get("payload", {})
                        await _process_ack(payload)
                        ack_msg: bytes = msgpack.packb({"action": "ack", "message_id": message_id})  # type: ignore[assignment]
                        await ws.send(ack_msg)

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log.warning("ACK listener: broker nedostupny (%s), zkusim za %ds", e, reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


async def _process_ack(payload: dict):
    object_id = payload.get("object_id")
    volume_id = payload.get("volume_id")
    offset = payload.get("offset")
    size = payload.get("size")

    if not all(v is not None for v in [object_id, volume_id, offset, size]):
        log.error("Neuplne ACK: %s", payload)
        return

    assert object_id is not None
    assert volume_id is not None
    assert offset is not None
    assert size is not None

    def _update_db():
        with get_sync_session() as db:
            try:
                record = db.query(FileRecord).filter(FileRecord.id == object_id).first()
                if not record:
                    log.warning("ACK pro neznamy object_id=%s", object_id)
                    return
                if record.status != "uploading":
                    log.warning("ACK pro object_id=%s se statusem %s (ocekavano uploading)", object_id, record.status)
                    return

                record.volume_id = volume_id
                record.haystack_offset = offset
                record.haystack_size = size
                record.status = "ready"

                bucket = db.query(Bucket).filter(Bucket.id == record.bucket_id).first()
                if bucket:
                    bucket.current_storage_bytes += size

                db.commit()
                log.info("ACK zpracovan: object_id=%s -> volume=%d offset=%d size=%d", object_id, volume_id, offset, size)
            except Exception as e:
                db.rollback()
                log.error("Chyba pri zpracovani ACK: %s", e)

    await run_in_threadpool(_update_db)


# -- Verejne endpointy -------------------------------------------------------

@files_router.get("/", response_model=FileListResponse, status_code=200)
def get_files(
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(FileRecord).filter(FileRecord.is_deleted == False)
    if x_user_id:
        query = query.filter(FileRecord.user_id == x_user_id)
    files = query.all()
    return FileListResponse(
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


@files_router.get("/{file_id}", status_code=200)
async def get_specific_file(
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
        raise HTTPException(status_code=404, detail="Soubor byl smazan")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Pristup odepren")
    if record.status == "uploading":
        return Response(
            content='{"detail":"Soubor se jeste nahraje, zkus to za chvili"}',
            status_code=202,
            media_type="application/json",
        )

    is_internal = x_internal_source and x_internal_source.lower() == "true"
    bucket = db.query(Bucket).filter(Bucket.id == record.bucket_id).first()
    if bucket:
        bucket.bandwidth_bytes += record.size
        if is_internal:
            bucket.internal_transfer_bytes += record.size
        else:
            bucket.egress_bytes += record.size
        db.commit()

    if record.volume_id is not None:
        import endpoints.files as _self
        url = f"{_self.HAYSTACK_URL}/volume/{record.volume_id}/{record.haystack_offset}/{record.haystack_size}"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=30.0)
            except httpx.RequestError as e:
                raise HTTPException(status_code=503, detail=f"Haystack Node nedostupny: {e}")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Haystack vratil chybu: {resp.status_code}")

        return Response(
            content=resp.content,
            media_type=record.content_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
        )

    from pathlib import Path
    path = Path(record.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Soubor chybi na disku")

    def _iter_file():
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        _iter_file(),
        media_type=record.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
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
        raise HTTPException(status_code=404, detail="Soubor jiz byl smazan")
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Pristup odepren")

    record.is_deleted = True
    db.commit()

    return DeleteResponse(message="Soubor uspesne smazan (soft delete)", id=file_id)


@files_router.post("/upload", response_model=CreateFile, status_code=202)
async def create_file(
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

    data: bytes = await file.read()
    size = len(data)

    record = FileRecord(
        id=file_id,
        user_id=user_id,
        filename=file.filename or "unknown",
        path="",
        size=size,
        content_type=file.content_type,
        bucket_id=bucket_id,
        status="uploading",
    )
    db.add(record)

    is_internal = x_internal_source and x_internal_source.lower() == "true"
    bucket.bandwidth_bytes += size
    if is_internal:
        bucket.internal_transfer_bytes += size
    else:
        bucket.ingress_bytes += size

    db.commit()
    db.refresh(record)

    payload = {
        "object_id": file_id,
        "data": data,
    }
    await publish_to_broker("storage.write", payload)

    return CreateFile(
        id=record.id,
        filename=record.filename,
        size=record.size,
        content_type=record.content_type,
    )


# -- Interni endpointy pro compact.py ----------------------------------------

@files_router.get("/internal/volume/{volume_id}/objects")
def get_volume_objects(
    volume_id: int,
    x_internal_source: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_internal_source or x_internal_source.lower() != "true":
        raise HTTPException(status_code=403, detail="Pristup odepren")

    records = (
        db.query(FileRecord)
        .filter(
            FileRecord.volume_id == volume_id,
            FileRecord.is_deleted == False,
            FileRecord.status == "ready",
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "haystack_offset": r.haystack_offset,
            "haystack_size": r.haystack_size,
        }
        for r in records
    ]


@files_router.post("/internal/bulk-update-location")
def bulk_update_location(
    body: dict,
    x_internal_source: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_internal_source or x_internal_source.lower() != "true":
        raise HTTPException(status_code=403, detail="Pristup odepren")

    updates = body.get("updates", [])
    for upd in updates:
        record = db.query(FileRecord).filter(FileRecord.id == upd["object_id"]).first()
        if record:
            record.volume_id = upd["volume_id"]
            record.haystack_offset = upd["new_offset"]
            record.haystack_size = upd["new_size"]
    db.commit()
    return {"updated": len(updates)}
