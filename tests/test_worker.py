import asyncio
import io
import json
import sys
import tempfile
import threading
import time

import numpy as np
import pytest
import uvicorn
import websockets
from PIL import Image

from conftest import wait_for_ready

HOST = "127.0.0.1"
BROKER_PORT = 18766
BROKER_URI = f"ws://{HOST}:{BROKER_PORT}/broker"
PORT = 18768
GATEWAY_URL = f"http://{HOST}:{PORT}"
HAYSTACK_PORT = 18769
HAYSTACK_URL = f"http://{HOST}:{HAYSTACK_PORT}"
WORKER_APP_PORT = 18767
WORKER_APP_URL = f"http://{HOST}:{WORKER_APP_PORT}"
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


def _run_broker():
    sys.path.insert(0, "src")
    from broker.broker_app import app
    uvicorn.run(app, host=HOST, port=BROKER_PORT, log_level="error",
                ws_ping_interval=None, ws_ping_timeout=None)


def _run_server():
    sys.path.insert(0, "src")
    from main import app
    import endpoints.files as _f

    _f.HAYSTACK_URL = HAYSTACK_URL
    _f.BROKER_URI = BROKER_URI

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="error",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


def _run_haystack():
    sys.path.insert(0, "src")
    from pathlib import Path
    import haystack.haystack_node as hn

    hn.BROKER_URI = BROKER_URI
    hn.GATEWAY_URL = GATEWAY_URL
    hn.VOLUME_DIR = Path(tempfile.mkdtemp(prefix="haystack_test_"))
    uvicorn.run(
        hn.app,
        host=HOST,
        port=HAYSTACK_PORT,
        log_level="error",
    )


def _run_worker_app():
    sys.path.insert(0, "src")
    import worker.worker_app as wa

    wa.BROKER_URI = BROKER_URI
    wa.GATEWAY_URL = GATEWAY_URL
    uvicorn.run(wa.app, host=HOST, port=WORKER_APP_PORT, log_level="error")


@pytest.fixture(scope="module", autouse=True)
def server():
    t_broker = threading.Thread(target=_run_broker, daemon=True)
    t_broker.start()
    wait_for_ready(f"http://{HOST}:{BROKER_PORT}/health")

    t_gw = threading.Thread(target=_run_server, daemon=True)
    t_gw.start()
    wait_for_ready(f"http://{HOST}:{PORT}/")

    t_hay = threading.Thread(target=_run_haystack, daemon=True)
    t_hay.start()
    wait_for_ready(f"{HAYSTACK_URL}/health")
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
            file_id = (await resp.json())["id"]

        for _ in range(30):
            await asyncio.sleep(0.2)
            async with session.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": user_id},
            ) as resp:
                if resp.status == 200:
                    return file_id

    raise TimeoutError(f"File {file_id} never became ready")


async def _drain_image_done():
    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:
        await ws.send(json.dumps({"action": "subscribe", "topic": "image.done"}))
        await asyncio.wait_for(ws.recv(), timeout=2)
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                msg = json.loads(raw)
                if msg.get("message_id"):
                    await ws.send(json.dumps({"action": "ack", "message_id": msg["message_id"]}))
            except asyncio.TimeoutError:
                break


async def _start_worker():
    from worker.worker import worker_loop

    return asyncio.create_task(worker_loop(BROKER_URI, GATEWAY_URL))


@pytest.mark.asyncio
async def test_worker_health_endpoint():
    t_worker = threading.Thread(target=_run_worker_app, daemon=True)
    t_worker.start()
    wait_for_ready(f"{WORKER_APP_URL}/health")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{WORKER_APP_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ten_jobs_processed():
    await _drain_image_done()
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

    async with websockets.connect(BROKER_URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(BROKER_URI, **WS_OPTS) as pub_ws:
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
async def test_process_endpoint_creates_job():
    import aiohttp

    await _drain_image_done()
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{GATEWAY_URL}/buckets/{bucket_id}/objects/{file_id}/process",
            json={"operation": "invert", "params": {}},
            headers={"X-User-Id": "testuser"},
        ) as resp:
            assert resp.status == 202
            body = await resp.json()
            assert body["status"] == "processing_started"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{GATEWAY_URL}/buckets/{bucket_id}/objects/{file_id}/results",
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["total"] >= 1
            job = body["jobs"][0]
            assert job["operation"] == "invert"
            assert job["status"] in ("processing", "completed", "failed")


@pytest.mark.asyncio
async def test_invalid_operation_returns_failure():
    await _drain_image_done()
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    async with websockets.connect(BROKER_URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(BROKER_URI, **WS_OPTS) as pub_ws:
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
    await _drain_image_done()
    bucket_id = await _create_bucket()
    file_id = await _upload_file(bucket_id)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    async with websockets.connect(BROKER_URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(BROKER_URI, **WS_OPTS) as pub_ws:
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
            file_id = (await resp.json())["id"]

        for _ in range(30):
            await asyncio.sleep(0.2)
            async with session.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": user_id},
            ) as resp:
                if resp.status == 200:
                    return file_id

    raise TimeoutError(f"File {file_id} never became ready")


@pytest.mark.asyncio
async def test_invert_produces_correct_result():
    import aiohttp

    await _drain_image_done()
    bucket_id = await _create_bucket()

    arr = np.full((4, 4, 3), 200, dtype=np.uint8)
    arr[0, 0] = [0, 128, 255]
    original_bytes = _make_test_image_from_array(arr)
    file_id = await _upload_file_bytes(bucket_id, original_bytes)

    worker_task = await _start_worker()
    await asyncio.sleep(0.5)

    new_file_id = None

    async with websockets.connect(BROKER_URI, **WS_OPTS) as done_sub:
        await done_sub.send(
            json.dumps({"action": "subscribe", "topic": "image.done"})
        )
        sub_resp = json.loads(await done_sub.recv())
        assert sub_resp["action"] == "subscribed"

        async with websockets.connect(BROKER_URI, **WS_OPTS) as pub_ws:
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
        result_bytes = None
        for _ in range(30):
            async with session.get(
                f"{GATEWAY_URL}/files/{new_file_id}",
                headers={"X-User-Id": "testuser", "X-Internal-Source": "true"},
            ) as resp:
                if resp.status == 200:
                    result_bytes = await resp.read()
                    break
            await asyncio.sleep(0.2)
        assert result_bytes is not None, f"Result file {new_file_id} never became ready"

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
