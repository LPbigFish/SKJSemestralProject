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
from endpoints.process import process_router
from endpoints.broker_client import init_broker_client
import endpoints.files as _files

app = FastAPI(title="S3 Gateway")

app.include_router(files_router)
app.include_router(buckets_router)
app.include_router(process_router)


@app.on_event("startup")
async def startup():
    await init_broker_client(_files.BROKER_URI)
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