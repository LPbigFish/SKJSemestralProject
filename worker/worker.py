import argparse
import asyncio
import io
import json
import logging
import sys
import tempfile
from pathlib import Path

import aiohttp
import numpy as np
import websockets
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from image_ops import apply_operation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


async def download_image(
    session: aiohttp.ClientSession, gateway_url: str, file_id: str, user_id: str
) -> bytes:
    url = f"{gateway_url}/files/{file_id}"
    headers = {"X-User-Id": user_id, "X-Internal-Source": "true"}
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(
                f"Failed to download {file_id}: HTTP {resp.status} {body}"
            )
        return await resp.read()


async def upload_image(
    session: aiohttp.ClientSession,
    gateway_url: str,
    bucket_id: int,
    user_id: str,
    filename: str,
    data: bytes,
) -> dict:
    url = f"{gateway_url}/files/upload"
    headers = {"X-User-Id": user_id, "X-Internal-Source": "true"}
    form = aiohttp.FormData()
    form.add_field("bucket_id", str(bucket_id))
    form.add_field("file", data, filename=filename, content_type="image/png")
    async with session.post(url, headers=headers, data=form) as resp:
        if resp.status != 201:
            body = await resp.text()
            raise RuntimeError(
                f"Failed to upload processed image: HTTP {resp.status} {body}"
            )
        return await resp.json()


def process_image(image_bytes: bytes, operation: str, params: dict | None) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img_array = np.array(img)

    result_array = apply_operation(img_array, operation, params)

    result_img = Image.fromarray(result_array)
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    return buf.getvalue()


async def publish_done(ws, payload: dict):
    await ws.send(json.dumps({"action": "publish", "topic": "image.done", "payload": payload}))
    log.info("Published to image.done: %s", payload.get("status"))


async def handle_job(
    ws,
    session: aiohttp.ClientSession,
    gateway_url: str,
    payload: dict,
    message_id: int,
):
    bucket_id = payload["bucket_id"]
    file_id = payload["file_id"]
    user_id = payload.get("user_id", "default_user")
    operation = payload.get("operation", "")
    params = payload.get("params")

    try:
        log.info(
            "Processing job msg_id=%d op=%s file=%s", message_id, operation, file_id
        )

        image_bytes = await download_image(session, gateway_url, file_id, user_id)

        result_bytes = process_image(image_bytes, operation, params)

        original_name = payload.get("filename", "image.png")
        stem = Path(original_name).stem
        new_name = f"{stem}_{operation}.png"

        upload_result = await upload_image(
            session, gateway_url, bucket_id, user_id, new_name, result_bytes
        )

        await publish_done(
            ws,
            {
                "status": "completed",
                "original_file_id": file_id,
                "new_file_id": upload_result["id"],
                "operation": operation,
                "bucket_id": bucket_id,
            },
        )

        log.info("Job msg_id=%d completed -> new_file_id=%s", message_id, upload_result["id"])

    except Exception as exc:
        log.error("Job msg_id=%d failed: %s", message_id, exc)
        await publish_done(
            ws,
            {
                "status": "failed",
                "original_file_id": file_id,
                "operation": operation,
                "bucket_id": bucket_id,
                "error": str(exc),
            },
        )

    finally:
        await ws.send(json.dumps({"action": "ack", "message_id": message_id}))
        log.info("Acked message_id=%d", message_id)


async def worker_loop(broker_uri: str, gateway_url: str):
    session = aiohttp.ClientSession()
    try:
        async with websockets.connect(
            broker_uri,
            max_queue=None,
            compression=None,
            ping_interval=None,
            ping_timeout=None,
        ) as ws:
            await ws.send(
                json.dumps({"action": "subscribe", "topic": "image.jobs"})
            )
            log.info("Subscribed to image.jobs on %s", broker_uri)

            while True:
                raw = await ws.recv()
                msg = json.loads(raw if isinstance(raw, str) else raw.decode())

                action = msg.get("action", "")
                if action == "subscribed":
                    log.info("Subscription confirmed: %s", msg.get("topic"))
                    continue

                if action == "deliver":
                    payload = msg.get("payload", {})
                    message_id = msg.get("message_id")
                    await handle_job(ws, session, gateway_url, payload, message_id)
    finally:
        await session.close()


def main():
    parser = argparse.ArgumentParser(description="Image Processing Worker")
    parser.add_argument(
        "--broker-uri",
        default="ws://localhost:8080/broker",
        help="WebSocket broker URI",
    )
    parser.add_argument(
        "--gateway-url",
        default="http://localhost:8080",
        help="S3 Gateway HTTP URL",
    )
    args = parser.parse_args()

    log.info("Starting worker: broker=%s gateway=%s", args.broker_uri, args.gateway_url)
    asyncio.run(worker_loop(args.broker_uri, args.gateway_url))


if __name__ == "__main__":
    main()
