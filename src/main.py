"""
main.py - S3 Gateway
====================
Spusteni: python main.py
"""

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from broker_client import start_broker_client, stop_broker_client
from endpoints.files import files_router, storage_ack_listener
from endpoints.buckets import buckets_router
from endpoints.process import process_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_broker_client()
    asyncio.create_task(storage_ack_listener())
    yield
    await stop_broker_client()


app = FastAPI(title="S3 Gateway", lifespan=lifespan)

app.include_router(files_router)
app.include_router(buckets_router)
app.include_router(process_router)


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
