"""
worker_app.py – Image Processing Worker (FastAPI)
==================================================
Samostatná FastAPI aplikace pro zpracování obrázků.
Na pozadí běží worker_loop, který naslouchá na image.jobs.

Spouštění:
    PYTHONPATH=src python src/worker/worker_app.py
    PYTHONPATH=src python src/worker/worker_app.py --port 8083
"""

import argparse
import asyncio
import logging

import uvicorn
from fastapi import FastAPI

from worker.worker import worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BROKER_URI: str = "ws://localhost:8082/broker"
GATEWAY_URL: str = "http://localhost:8080"

app = FastAPI(title="Image Processing Worker")


@app.on_event("startup")
async def startup():
    asyncio.create_task(worker_loop(BROKER_URI, GATEWAY_URL))
    log.info("Worker spuštěn: broker=%s gateway=%s", BROKER_URI, GATEWAY_URL)


@app.get("/health")
def health():
    return {"status": "ok"}


def main():
    global BROKER_URI, GATEWAY_URL

    parser = argparse.ArgumentParser(description="Image Processing Worker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--broker-uri", default="ws://localhost:8082/broker")
    parser.add_argument("--gateway-url", default="http://localhost:8080")
    args = parser.parse_args()

    BROKER_URI = args.broker_uri
    GATEWAY_URL = args.gateway_url

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
