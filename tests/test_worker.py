import asyncio
import io
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import uvicorn
import websockets
from PIL import Image

project_root = str(Path(__file__).resolve().parent.parent)
broker_path = str(Path(__file__).resolve().parent.parent / "broker")
src_path = str(Path(__file__).resolve().parent.parent / "src")
for p in [project_root, broker_path, src_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

from broker.db import init_db

HOST = "127.0.0.1"
BROKER_PORT = 18778
GATEWAY_PORT = 18779
HAYSTACK_PORT = 18780
BROKER_URI = f"ws://{HOST}:{BROKER_PORT}/broker"
GATEWAY_URL = f"http://{HOST}:{GATEWAY_PORT}"
HAYSTACK_URL = f"http://{HOST}:{HAYSTACK_PORT}"
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
    from broker.main import app
    init_db()
    uvicorn.run(app, host=HOST, port=BROKER_PORT, log_level="error")


def _run_gateway():
    from endpoints import files as files_module
    files_module.BROKER_URI = BROKER_URI
    files_module.HAYSTACK_URL = HAYSTACK_URL

    import broker_client
    broker_client.BROKER_URI = BROKER_URI

    from main import app
    uvicorn.run(
        app,
        host=HOST,
        port=GATEWAY_PORT,
        log_level="error",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


def _run_haystack():
    haystack_path = str(Path(__file__).resolve().parent.parent / "src" / "haystack")
    if haystack_path not in sys.path:
        sys.path.insert(0, haystack_path)

    import haystack_node as hn  # type: ignore[import-unresolved]

    hn.BROKER_URI = BROKER_URI
    hn.GATEWAY_URL = GATEWAY_URL
    hn.VOLUME_DIR = Path(tempfile.mkdtemp(prefix="worker_haystack_"))
    hn.MAX_VOLUME_BYTES = 50 * 1024 * 1024
    hn._current_volume_id = 1
    hn._current_file = None

    uvicorn.run(hn.app, host=HOST, port=HAYSTACK_PORT, log_level="error")


@pytest.fixture(scope="module", autouse=True)
def servers():
    broker_thread = threading.Thread(target=_run_broker, daemon=True)
    broker_thread.start()
    time.sleep(0.5)

    gw_thread = threading.Thread(target=_run_gateway, daemon=True)
    gw_thread.start()
    time.sleep(1.0)

    hs_thread = threading.Thread(target=_run_haystack, daemon=True)
    hs_thread.start()
    time.sleep(1.0)
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
    return await _upload_file_bytes(bucket_id, image_bytes, user_id)


async def _upload_file_bytes(bucket_id: int, data: bytes, user_id: str = "testuser") -> str:
    import aiohttp

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("bucket_id", str(bucket_id))
        form.add_field("file", data, filename="test_image.png", content_type="image/png")
        async with session.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": user_id, "X-Internal-Source": "true"},
            data=form,
        ) as resp:
            file_id = (await resp.json())["id"]

    for _ in range(30):
        await asyncio.sleep(0.3)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": user_id, "X-Internal-Source": "true"},
            ) as resp:
                if resp.status == 200:
                    return file_id

    pytest.fail(f"File {file_id} did not reach ready state")


async def _start_worker():
    from worker.worker import worker_loop
    return asyncio.create_task(worker_loop(BROKER_URI, GATEWAY_URL))


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
async def test_invalid_operation_returns_failure():
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
            headers={"X-User-Id": user_id, "X-Internal-Source": "true"},
            data=form,
        ) as resp:
            file_id = (await resp.json())["id"]

    await asyncio.sleep(0.3)

    from repository.db import get_sync_session
    from repository.repo import FileRecord
    from pathlib import Path

    file_path = Path("storage") / user_id / file_id
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(data)

    with get_sync_session() as db:
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if record:
            record.status = "ready"
            record.path = str(file_path)
            db.commit()

    return file_id


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

    await asyncio.sleep(0.5)

    result_bytes = None
    for _ in range(30):
        await asyncio.sleep(0.3)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GATEWAY_URL}/files/{new_file_id}",
                headers={"X-User-Id": "testuser", "X-Internal-Source": "true"},
            ) as resp:
                if resp.status == 200:
                    result_bytes = await resp.read()
                    break

    if result_bytes is None:
        pytest.fail(f"Processed file {new_file_id} did not reach ready state")

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
