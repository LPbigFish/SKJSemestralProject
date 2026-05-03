import asyncio
import io
import json
import threading
import time

import numpy as np
import pytest
import pytest_asyncio
import uvicorn
import websockets
from PIL import Image

HOST = "127.0.0.1"
PORT = 18768
URI = f"ws://{HOST}:{PORT}/broker"
GATEWAY_URL = f"http://{HOST}:{PORT}"
WS_OPTS = {
    "max_queue": None,
    "compression": None,
    "ping_interval": None,
    "ping_timeout": None,
}


def _make_test_image(width=64, height=64) -> bytes:
    arr = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _run_server():
    import sys

    sys.path.insert(0, "src")
    from main import app

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="error",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


@pytest.fixture(scope="module", autouse=True)
def server():
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    time.sleep(1.5)
    yield


async def _create_bucket() -> int:
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{GATEWAY_URL}/buckets/",
            json={"name": f"test-bucket-{int(time.time()*1000)}"},
        ) as resp:
            data = await resp.json()
            return data["id"]


async def _upload_file(bucket_id: int, user_id: str = "testuser") -> str:
    import aiohttp

    image_bytes = _make_test_image()
    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("bucket_id", str(bucket_id))
        form.add_field(
            "file",
            image_bytes,
            filename="test_image.png",
            content_type="image/png",
        )
        async with session.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": user_id},
            data=form,
        ) as resp:
            data = await resp.json()
            return data["id"]


async def _start_worker():
    import sys
    from pathlib import Path

    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from worker.worker import worker_loop

    return asyncio.create_task(worker_loop(URI, GATEWAY_URL))


@pytest.mark.asyncio
async def test_ten_jobs_processed():
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    operations = [
        "invert",
        "flip",
        "grayscale",
        "brightness",
        "invert",
        "flip",
        "crop",
        "grayscale",
        "brightness",
        "invert",
    ]

    async with websockets.connect(URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub_ws:
            for i, op in enumerate(operations):
                payload = {
                    "bucket_id": bucket_id,
                    "file_id": file_id,
                    "user_id": "testuser",
                    "operation": op,
                    "params": (
                        {"value": 30}
                        if op == "brightness"
                        else {"top": 10, "left": 10, "bottom": 54, "right": 54}
                        if op == "crop"
                        else {}
                    ),
                    "filename": "test_image.png",
                }
                await pub_ws.send(
                    json.dumps(
                        {"action": "publish", "topic": "image.jobs", "payload": payload}
                    )
                )

        completed = []
        for _ in range(len(operations)):
            raw = await asyncio.wait_for(done_sub.recv(), timeout=30)
            msg = json.loads(raw)
            if msg.get("action") == "deliver":
                payload = msg["payload"]
                assert payload["status"] in ("completed", "failed"), f"Unexpected: {payload}"
                completed.append(payload)

                if msg.get("message_id"):
                    await done_sub.send(
                        json.dumps(
                            {"action": "ack", "message_id": msg["message_id"]}
                        )
                    )

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    assert len(completed) == 10, f"Expected 10 completions, got {len(completed)}"
    statuses = [c["status"] for c in completed]
    assert all(s == "completed" for s in statuses), f"Some jobs failed: {statuses}"


@pytest.mark.asyncio
async def test_invalid_operation_returns_failure():
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    async with websockets.connect(URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub_ws:
            payload = {
                "bucket_id": bucket_id,
                "file_id": file_id,
                "user_id": "testuser",
                "operation": "exploit-op",
                "params": {},
                "filename": "test_image.png",
            }
            await pub_ws.send(
                json.dumps(
                    {"action": "publish", "topic": "image.jobs", "payload": payload}
                )
            )

        raw = await asyncio.wait_for(done_sub.recv(), timeout=15)
        msg = json.loads(raw)
        assert msg["action"] == "deliver"
        assert msg["payload"]["status"] == "failed"
        assert "Unknown operation" in msg["payload"]["error"]

        if msg.get("message_id"):
            await done_sub.send(
                json.dumps({"action": "ack", "message_id": msg["message_id"]})
            )

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_crop_out_of_bounds_returns_failure():
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    async with websockets.connect(URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub_ws:
            payload = {
                "bucket_id": bucket_id,
                "file_id": file_id,
                "user_id": "testuser",
                "operation": "crop",
                "params": {"top": 0, "left": 0, "bottom": 9999, "right": 9999},
                "filename": "test_image.png",
            }
            await pub_ws.send(
                json.dumps(
                    {"action": "publish", "topic": "image.jobs", "payload": payload}
                )
            )

        raw = await asyncio.wait_for(done_sub.recv(), timeout=15)
        msg = json.loads(raw)
        assert msg["action"] == "deliver"
        assert msg["payload"]["status"] == "failed"
        assert "out of image dimensions" in msg["payload"]["error"]

        if msg.get("message_id"):
            await done_sub.send(
                json.dumps({"action": "ack", "message_id": msg["message_id"]})
            )

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


def _make_test_image_from_array(arr: np.ndarray) -> bytes:
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _upload_file_bytes(bucket_id: int, data: bytes, user_id: str = "testuser") -> str:
    import aiohttp

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("bucket_id", str(bucket_id))
        form.add_field("file", data, filename="test_image.png", content_type="image/png")
        async with session.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": user_id},
            data=form,
        ) as resp:
            return (await resp.json())["id"]


@pytest.mark.asyncio
async def test_invert_produces_correct_result():
    import aiohttp

    bucket_id = await _create_bucket()

    arr = np.full((4, 4, 3), 200, dtype=np.uint8)
    arr[0, 0] = [0, 128, 255]
    original_bytes = _make_test_image_from_array(arr)
    file_id = await _upload_file_bytes(bucket_id, original_bytes)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    new_file_id = None

    async with websockets.connect(URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub_ws:
            payload = {
                "bucket_id": bucket_id,
                "file_id": file_id,
                "user_id": "testuser",
                "operation": "invert",
                "params": {},
                "filename": "test_image.png",
            }
            await pub_ws.send(
                json.dumps(
                    {"action": "publish", "topic": "image.jobs", "payload": payload}
                )
            )

        raw = await asyncio.wait_for(done_sub.recv(), timeout=15)
        msg = json.loads(raw)
        assert msg["action"] == "deliver"
        assert msg["payload"]["status"] == "completed"
        new_file_id = msg["payload"]["new_file_id"]

        if msg.get("message_id"):
            await done_sub.send(
                json.dumps({"action": "ack", "message_id": msg["message_id"]})
            )

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{GATEWAY_URL}/files/{new_file_id}",
            headers={"X-User-Id": "testuser", "X-Internal-Source": "true"},
        ) as resp:
            assert resp.status == 200
            result_bytes = await resp.read()

    result_img = Image.open(io.BytesIO(result_bytes)).convert("RGB")
    result_arr = np.array(result_img)

    expected_pixel = np.array([255, 127, 0], dtype=np.uint8)
    np.testing.assert_array_equal(result_arr[0, 0], expected_pixel)
    np.testing.assert_array_equal(result_arr[1, 1], np.array([55, 55, 55], dtype=np.uint8))

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
