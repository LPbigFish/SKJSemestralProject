"""
main.py – S3 Gateway
====================
Spouštění: python main.py
"""

import asyncio
import uvicorn
from fastapi import FastAPI

from endpoints.files import files_router, storage_ack_listener
from endpoints.buckets import buckets_router
from endpoints.broker import broker_router
from endpoints.process import process_router

app = FastAPI(title="S3 Gateway")

app.include_router(files_router)
app.include_router(buckets_router)
app.include_router(broker_router)
app.include_router(process_router)


@app.on_event("startup")
async def startup():
    """Spustí ACK listener jako asyncio task na pozadí."""
    asyncio.create_task(storage_ack_listener())


@app.get("/")
def info():
    return {"status": "S3 Gateway is RUNNING"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )