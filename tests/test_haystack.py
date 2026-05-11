"""
tests/test_haystack.py
======================
Tests for Haystack Storage Node.

Requires: pytest, pytest-asyncio, httpx, msgpack, websockets
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
import msgpack
import pytest
import uvicorn
import websockets

project_root = str(Path(__file__).resolve().parent.parent)
broker_path = str(Path(__file__).resolve().parent.parent / "broker")
src_path = str(Path(__file__).resolve().parent.parent / "src")
for p in [project_root, broker_path, src_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

from broker.db import init_db

HAYSTACK_HOST = "127.0.0.1"
HAYSTACK_PORT = 18770
HAYSTACK_URL = f"http://{HAYSTACK_HOST}:{HAYSTACK_PORT}"

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 18771
BROKER_URI = f"ws://{BROKER_HOST}:{BROKER_PORT}/broker"
GATEWAY_PORT = 18772
GATEWAY_URL = f"http://{BROKER_HOST}:{GATEWAY_PORT}"

WS_OPTS = {
    "max_queue": None,
    "compression": None,
    "ping_interval": None,
    "ping_timeout": None,
}

_TEST_VOLUME_DIR: Path = Path(tempfile.mkdtemp(prefix="haystack_test_"))


def _run_broker():
    from broker.main import app
    init_db()
    uvicorn.run(app, host=BROKER_HOST, port=BROKER_PORT, log_level="error")


def _run_haystack_server():
    haystack_path = str(Path(__file__).resolve().parent.parent / "src" / "haystack")
    if haystack_path not in sys.path:
        sys.path.insert(0, haystack_path)

    import haystack_node as hn  # type: ignore[import-unresolved]

    hn.BROKER_URI = BROKER_URI
    hn.GATEWAY_URL = GATEWAY_URL
    hn.VOLUME_DIR = _TEST_VOLUME_DIR
    hn.MAX_VOLUME_BYTES = 1 * 1024 * 1024

    hn._current_volume_id = 1
    hn._current_file = None

    uvicorn.run(
        hn.app,
        host=HAYSTACK_HOST,
        port=HAYSTACK_PORT,
        log_level="error",
    )


def _run_gateway_server():
    from endpoints import files as files_module
    files_module.BROKER_URI = BROKER_URI
    files_module.HAYSTACK_URL = HAYSTACK_URL

    import broker_client
    broker_client.BROKER_URI = BROKER_URI

    from main import app
    uvicorn.run(
        app,
        host=BROKER_HOST,
        port=GATEWAY_PORT,
        log_level="error",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


@pytest.fixture(scope="module", autouse=True)
def servers():
    broker_thread = threading.Thread(target=_run_broker, daemon=True)
    broker_thread.start()
    time.sleep(0.5)

    gw_thread = threading.Thread(target=_run_gateway_server, daemon=True)
    gw_thread.start()
    time.sleep(1.0)

    hs_thread = threading.Thread(target=_run_haystack_server, daemon=True)
    hs_thread.start()
    time.sleep(1.5)

    yield

    shutil.rmtree(_TEST_VOLUME_DIR, ignore_errors=True)


async def _create_bucket(name: Optional[str] = None) -> int:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/buckets/",
            json={"name": name or f"test-bucket-{int(time.time() * 1000)}"},
        )
        assert resp.status_code == 201
        return resp.json()["id"]


async def _upload_via_gateway(bucket_id: int, data: bytes, filename: str = "test.bin") -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": "testuser"},
            files={"file": (filename, data, "application/octet-stream")},
            data={"bucket_id": str(bucket_id)},
        )
        assert resp.status_code == 202, f"Upload failed: {resp.text}"
        file_id = resp.json()["id"]

    for _ in range(30):
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": "testuser"},
            )
            if resp.status_code == 200:
                return {"id": file_id, "data": resp.content}

    pytest.fail(f"File {file_id} did not reach ready state within 6 seconds")


# -- Unit tests: direct HTTP to Haystack Node --------------------------------

@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "active_volume" in body
    assert "volume_size_bytes" in body


@pytest.mark.asyncio
async def test_write_and_read_single_needle():
    data = b"Hello, Haystack! " * 100

    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        sub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {"action": "subscribe", "topic": "storage.ack"}
        )
        await ws.send(sub_msg)

        raw = await ws.recv()
        msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
        assert msg.get("action") == "subscribed"

        object_id = f"test-needle-{int(time.time() * 1000)}"
        pub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {
                "action": "publish",
                "topic": "storage.write",
                "payload": {
                    "object_id": object_id,
                    "data": data,
                },
            }
        )
        await ws.send(pub_msg)

        ack = None
        for _ in range(20):
            raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
            if msg.get("action") == "deliver" and msg.get("topic") == "storage.ack":
                ack = msg["payload"]
                break

    assert ack is not None, "Haystack did not send ACK"
    assert ack["object_id"] == object_id
    assert ack["size"] == len(data)
    assert ack["offset"] >= 0
    assert ack["volume_id"] >= 1

    volume_id = ack["volume_id"]
    offset = ack["offset"]
    size = ack["size"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volume/{volume_id}/{offset}/{size}")

    assert resp.status_code == 200
    assert resp.content == data


@pytest.mark.asyncio
async def test_read_nonexistent_volume_returns_404():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volume/9999/0/10")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_needles_correct_offsets():
    payloads = [
        b"first-data-" + bytes([i] * 50)
        for i in range(5)
    ]
    acks = []

    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        sub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {"action": "subscribe", "topic": "storage.ack"}
        )
        await ws.send(sub_msg)
        raw = await ws.recv()
        msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
        assert msg.get("action") == "subscribed"

        object_ids = []
        for i, data in enumerate(payloads):
            object_id = f"multi-needle-{i}-{int(time.time() * 1000)}"
            object_ids.append(object_id)
            pub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
                {
                    "action": "publish",
                    "topic": "storage.write",
                    "payload": {"object_id": object_id, "data": data},
                }
            )
            await ws.send(pub_msg)

        payload_map = dict(zip(object_ids, payloads))
        our_ids = set(object_ids)

        for _ in range(len(payloads)):
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
                if (msg.get("action") == "deliver"
                        and msg.get("topic") == "storage.ack"
                        and msg.get("payload", {}).get("object_id") in our_ids):
                    acks.append(msg["payload"])
                    break

    assert len(acks) == len(payloads), f"Expected {len(payloads)} ACKs, got {len(acks)}"

    offsets = [a["offset"] for a in acks]
    assert len(set(offsets)) == len(offsets), f"Duplicate offsets: {offsets}"

    for ack in acks:
        original_data = payload_map[ack["object_id"]]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{HAYSTACK_URL}/volume/{ack['volume_id']}/{ack['offset']}/{ack['size']}"
            )
        assert resp.status_code == 200
        assert resp.content == original_data, (
            f"Data at offset {ack['offset']} mismatch for {ack['object_id']}"
        )


@pytest.mark.asyncio
async def test_volume_rotation():
    async with httpx.AsyncClient() as client:
        health_before = (await client.get(f"{HAYSTACK_URL}/health")).json()
    volume_before = health_before["active_volume"]

    big_data = os.urandom(600 * 1024)
    big_data_2 = os.urandom(600 * 1024)

    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        sub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {"action": "subscribe", "topic": "storage.ack"}
        )
        await ws.send(sub_msg)
        raw = await ws.recv()
        msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
        assert msg.get("action") == "subscribed"

        for i, chunk in enumerate([big_data, big_data_2]):
            pub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
                {
                    "action": "publish",
                    "topic": "storage.write",
                    "payload": {
                        "object_id": f"rotation-test-{i}",
                        "data": chunk,
                    },
                }
            )
            await ws.send(pub_msg)

        received = 0
        for _ in range(40):
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
            if msg.get("action") == "deliver" and msg.get("topic") == "storage.ack":
                received += 1
            if received == 2:
                break

    assert received == 2, "Did not get both ACKs after large write"

    async with httpx.AsyncClient() as client:
        health_after = (await client.get(f"{HAYSTACK_URL}/health")).json()
    volume_after = health_after["active_volume"]

    assert volume_after > volume_before, (
        f"Rotation did not occur: before={volume_before}, after={volume_after}"
    )


@pytest.mark.asyncio
async def test_list_volumes():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volumes")
    assert resp.status_code == 200
    body = resp.json()
    assert "volumes" in body
    assert len(body["volumes"]) >= 1
    for v in body["volumes"]:
        assert "volume_id" in v
        assert "size_bytes" in v


# -- Integration tests: Gateway -> Broker -> Haystack -> ACK ------------------

@pytest.mark.asyncio
async def test_upload_via_gateway_and_download():
    bucket_id = await _create_bucket()
    original_data = os.urandom(4096)

    result = await _upload_via_gateway(bucket_id, original_data, "binary_test.bin")

    assert result["data"] == original_data, "Downloaded data does not match uploaded"


@pytest.mark.asyncio
async def test_upload_status_uploading_then_ready():
    bucket_id = await _create_bucket()
    data = os.urandom(1024)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": "testuser"},
            files={"file": ("status_test.bin", data, "application/octet-stream")},
            data={"bucket_id": str(bucket_id)},
        )
    assert resp.status_code == 202
    file_id = resp.json()["id"]

    ready = False
    for _ in range(30):
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            get_resp = await client.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": "testuser"},
            )
        if get_resp.status_code == 200:
            ready = True
            assert get_resp.content == data
            break

    assert ready, "File did not reach ready state"


@pytest.mark.asyncio
async def test_soft_delete_hides_file():
    bucket_id = await _create_bucket()
    data = b"soft-delete-test-data"

    result = await _upload_via_gateway(bucket_id, data)
    file_id = result["id"]

    async with httpx.AsyncClient() as client:
        del_resp = await client.delete(
            f"{GATEWAY_URL}/files/{file_id}",
            headers={"X-User-Id": "testuser"},
        )
    assert del_resp.status_code == 200

    async with httpx.AsyncClient() as client:
        get_resp = await client.get(
            f"{GATEWAY_URL}/files/{file_id}",
            headers={"X-User-Id": "testuser"},
        )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_files_independent_reads():
    bucket_id = await _create_bucket()

    files = {
        "alpha.bin": os.urandom(512),
        "beta.bin": os.urandom(1024),
        "gamma.bin": os.urandom(256),
    }

    results = {}
    for filename, data in files.items():
        result = await _upload_via_gateway(bucket_id, data, filename)
        results[filename] = (data, result["data"])

    for filename, (original, downloaded) in results.items():
        assert original == downloaded, f"File {filename}: data mismatch"


@pytest.mark.asyncio
async def test_invalid_message_does_not_crash_node():
    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        bad_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {
                "action": "publish",
                "topic": "storage.write",
                "payload": {"data": b"some data"},
            }
        )
        await ws.send(bad_msg)
        await asyncio.sleep(0.5)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
