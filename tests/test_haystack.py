"""
tests/test_haystack.py
======================
Testy pro Haystack Storage Node (haystack_node.py).

Spuštění:
    pytest tests/test_haystack.py -v

Požadavky: pytest, pytest-asyncio, httpx, msgpack, websockets
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

from conftest import wait_for_ready

# ── Konfigurace testovacího serveru ───────────────────────────────────────────

HAYSTACK_HOST = "127.0.0.1"
HAYSTACK_PORT = 18770
HAYSTACK_URL = f"http://{HAYSTACK_HOST}:{HAYSTACK_PORT}"

# Broker – standalone na vlastním portu
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 18772
BROKER_URI = f"ws://{BROKER_HOST}:{BROKER_PORT}/broker"

# Gateway – na vlastním portu
GATEWAY_PORT = 18771
GATEWAY_URL = f"http://{BROKER_HOST}:{GATEWAY_PORT}"

WS_OPTS = {
    "max_queue": None,
    "compression": None,
    "ping_interval": None,
    "ping_timeout": None,
}

_TEST_VOLUME_DIR: Path | None = None


# ── Spuštění serverů v threadech ─────────────────────────────────────────────

def _run_broker():
    sys.path.insert(0, "src")
    from broker.broker_app import app
    uvicorn.run(app, host=BROKER_HOST, port=BROKER_PORT, log_level="error",
                ws_ping_interval=None, ws_ping_timeout=None)


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
    src_path = str(Path(__file__).resolve().parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from endpoints import files as files_module
    files_module.BROKER_URI = BROKER_URI
    files_module.HAYSTACK_URL = HAYSTACK_URL

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
    global _TEST_VOLUME_DIR
    _TEST_VOLUME_DIR = Path(tempfile.mkdtemp(prefix="haystack_test_"))

    t_broker = threading.Thread(target=_run_broker, daemon=True)
    t_broker.start()
    wait_for_ready(f"http://{BROKER_HOST}:{BROKER_PORT}/health")

    gw_thread = threading.Thread(target=_run_gateway_server, daemon=True)
    gw_thread.start()
    wait_for_ready(f"http://{BROKER_HOST}:{GATEWAY_PORT}/")

    hs_thread = threading.Thread(target=_run_haystack_server, daemon=True)
    hs_thread.start()
    wait_for_ready(f"{HAYSTACK_URL}/health")

    yield

    if _TEST_VOLUME_DIR:
        shutil.rmtree(_TEST_VOLUME_DIR, ignore_errors=True)


# ── Pomocné funkce ────────────────────────────────────────────────────────────

async def _create_bucket(name: Optional[str] = None) -> int:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/buckets/",
            json={"name": name or f"test-bucket-{int(time.time() * 1000)}"},
        )
        assert resp.status_code == 201
        return resp.json()["id"]


async def _upload_via_gateway(bucket_id: int, data: bytes, filename: str = "test.bin") -> dict:
    """Nahraje soubor přes S3 Gateway a počká na status ready (ACK od Haystack)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/files/upload",
            headers={"X-User-Id": "testuser"},
            files={"file": (filename, data, "application/octet-stream")},
            data={"bucket_id": str(bucket_id)},
        )
        assert resp.status_code == 202, f"Upload selhal: {resp.text}"
        file_id = resp.json()["id"]

    # Počkáme na ACK (Haystack zapíše a Gateway aktualizuje status na "ready")
    for _ in range(30):
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GATEWAY_URL}/files/{file_id}",
                headers={"X-User-Id": "testuser"},
            )
            if resp.status_code == 200:
                return {"id": file_id, "data": resp.content}
        # 202 = ještě se nahrává, čekáme dál

    pytest.fail(f"Soubor {file_id} nedosáhl stavu ready do 6 sekund")


# ── Unit testy: přímé HTTP volání na Haystack Node ────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint():
    """Haystack Node odpovídá na /health."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "active_volume" in body
    assert "volume_size_bytes" in body


@pytest.mark.asyncio
async def test_write_and_read_single_needle():
    """Přímý zápis přes broker a čtení přes HTTP endpoint."""
    data = b"Hello, Haystack! " * 100  # 1700 bajtů

    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        # Subscribujeme na storage.ack abychom dostali offset/size
        sub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {"action": "subscribe", "topic": "storage.ack"}
        )
        await ws.send(sub_msg)

        raw = await ws.recv()
        msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
        assert msg.get("action") == "subscribed"

        # Publikujeme zápis
        object_id = f"test-needle-{int(time.time() * 1000)}"
        pub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {
                "action": "publish",
                "topic": "storage.write",
                "payload": {
                    "object_id": object_id,
                    "data": list(data),
                },
            }
        )
        await ws.send(pub_msg)

        # Čekáme na ACK od Haystack Node
        ack = None
        for _ in range(20):
            raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
            if msg.get("action") == "deliver" and msg.get("topic") == "storage.ack":
                ack = msg["payload"]
                break

    assert ack is not None, "Haystack neodeslal ACK"
    assert ack["object_id"] == object_id
    assert ack["size"] == len(data)
    assert ack["offset"] >= 0
    assert ack["volume_id"] >= 1

    # Přečteme data přímo z Haystack Node
    volume_id = ack["volume_id"]
    offset = ack["offset"]
    size = ack["size"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volume/{volume_id}/{offset}/{size}")

    assert resp.status_code == 200
    assert resp.content == data


@pytest.mark.asyncio
async def test_read_nonexistent_volume_returns_404():
    """Čtení z neexistujícího svazku vrátí 404."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volume/9999/0/10")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_needles_correct_offsets():
    """Více zápisů za sebou – každý musí mít unikátní a správný offset."""
    payloads = [
        b"prvni-data-" + bytes([i] * 50)
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

        # Mapujeme object_id → původní data, abychom mohli správně párovat ACK
        object_ids = []
        for i, data in enumerate(payloads):
            object_id = f"multi-needle-{i}-{int(time.time() * 1000)}"
            object_ids.append(object_id)
            pub_msg: bytes = msgpack.packb(  # type: ignore[assignment]
                {
                    "action": "publish",
                    "topic": "storage.write",
                    "payload": {"object_id": object_id, "data": list(data)},
                }
            )
            await ws.send(pub_msg)

        payload_map = dict(zip(object_ids, payloads))
        our_ids = set(object_ids)

        # Sesbíráme ACK pouze pro naše object_ids (filtrujeme zprávy z jiných testů)
        for _ in range(len(payloads)):
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
                if (msg.get("action") == "deliver"
                        and msg.get("topic") == "storage.ack"
                        and msg.get("payload", {}).get("object_id") in our_ids):
                    acks.append(msg["payload"])
                    break

    assert len(acks) == len(payloads), f"Očekáváno {len(payloads)} ACK, dostáno {len(acks)}"

    # Ověříme, že každý offset je unikátní
    offsets = [a["offset"] for a in acks]
    assert len(set(offsets)) == len(offsets), f"Duplicitní offsety: {offsets}"

    # Ověříme data podle object_id – správné párování bez závislosti na pořadí
    for ack in acks:
        original_data = payload_map[ack["object_id"]]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{HAYSTACK_URL}/volume/{ack['volume_id']}/{ack['offset']}/{ack['size']}"
            )
        assert resp.status_code == 200
        assert resp.content == original_data, (
            f"Data na offset {ack['offset']} nesedí pro object_id {ack['object_id']}"
        )


@pytest.mark.asyncio
async def test_volume_rotation():
    """
    Zápis dat větších než MAX_VOLUME_BYTES (1 MB v testu) způsobí rotaci svazku.
    Po rotaci musí existovat volume_2.dat (nebo vyšší).
    """
    # Zjistíme aktuální aktivní svazek
    async with httpx.AsyncClient() as client:
        health_before = (await client.get(f"{HAYSTACK_URL}/health")).json()
    volume_before = health_before["active_volume"]

    # Zapíšeme data větší než limit (1 MB)
    big_data = os.urandom(600 * 1024)   # 600 KB
    big_data_2 = os.urandom(600 * 1024)  # dalších 600 KB → celkem >1 MB → rotace

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
                        "data": list(chunk),
                    },
                }
            )
            await ws.send(pub_msg)

        # Počkáme na oba ACK
        received = 0
        for _ in range(40):
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg = msgpack.unpackb(raw, raw=False) if isinstance(raw, bytes) else json.loads(raw)
            if msg.get("action") == "deliver" and msg.get("topic") == "storage.ack":
                received += 1
            if received == 2:
                break

    assert received == 2, "Nezískány oba ACK po velkém zápisu"

    # Aktivní svazek se musí zvýšit
    async with httpx.AsyncClient() as client:
        health_after = (await client.get(f"{HAYSTACK_URL}/health")).json()
    volume_after = health_after["active_volume"]

    assert volume_after > volume_before, (
        f"Rotace nenastala: volume_before={volume_before}, volume_after={volume_after}"
    )


@pytest.mark.asyncio
async def test_list_volumes():
    """/volumes vrátí seznam existujících svazků."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/volumes")
    assert resp.status_code == 200
    body = resp.json()
    assert "volumes" in body
    assert len(body["volumes"]) >= 1
    for v in body["volumes"]:
        assert "volume_id" in v
        assert "size_bytes" in v


# ── Integrační testy: celý tok Gateway → Broker → Haystack → ACK ─────────────

@pytest.mark.asyncio
async def test_upload_via_gateway_and_download():
    """
    Celý tok: POST /files/upload → broker → Haystack zápis → ACK → GET /files/{id}.
    """
    bucket_id = await _create_bucket()
    original_data = os.urandom(4096)  # 4 KB náhodných dat

    result = await _upload_via_gateway(bucket_id, original_data, "binary_test.bin")

    assert result["data"] == original_data, "Stažená data se neshodují s nahranými"


@pytest.mark.asyncio
async def test_upload_status_uploading_then_ready():
    """
    Ihned po uploadu je status 'uploading', po ACK přejde na 'ready'.
    Ověříme nepřímo: GET souboru vrátí 202 ihned a pak 200 po ACK.
    """
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

    # Počkáme na ready stav
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

    assert ready, "Soubor nedosáhl stavu ready"


@pytest.mark.asyncio
async def test_soft_delete_hides_file():
    """
    Po soft delete GET vrátí 404, ale data ve volume souboru fyzicky zůstávají.
    """
    bucket_id = await _create_bucket()
    data = b"soft-delete-test-data"

    result = await _upload_via_gateway(bucket_id, data)
    file_id = result["id"]

    # Soft delete
    async with httpx.AsyncClient() as client:
        del_resp = await client.delete(
            f"{GATEWAY_URL}/files/{file_id}",
            headers={"X-User-Id": "testuser"},
        )
    assert del_resp.status_code == 200

    # GET musí vrátit 404
    async with httpx.AsyncClient() as client:
        get_resp = await client.get(
            f"{GATEWAY_URL}/files/{file_id}",
            headers={"X-User-Id": "testuser"},
        )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_files_independent_reads():
    """Nahrání více souborů – každý se musí stáhnout správně nezávisle."""
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
        assert original == downloaded, f"Soubor {filename}: data se neshodují"


@pytest.mark.asyncio
async def test_invalid_message_does_not_crash_node():
    """
    Neplatná zpráva (chybí object_id) nesmí shodit Haystack Node.
    Node musí zůstat funkční pro další požadavky.
    """
    async with websockets.connect(BROKER_URI, **WS_OPTS) as ws:  # type: ignore[call-overload]
        bad_msg: bytes = msgpack.packb(  # type: ignore[assignment]
            {
                "action": "publish",
                "topic": "storage.write",
                "payload": {"data": list(b"some data")},  # chybí object_id
            }
        )
        await ws.send(bad_msg)
        await asyncio.sleep(0.5)

    # Node musí stále odpovídat
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{HAYSTACK_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
