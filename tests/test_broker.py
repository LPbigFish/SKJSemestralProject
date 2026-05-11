import json
import asyncio
import threading
import time
import sys
from pathlib import Path

import pytest
import uvicorn
import websockets

project_root = str(Path(__file__).resolve().parent.parent)
broker_path = str(Path(__file__).resolve().parent.parent / "broker")
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if broker_path not in sys.path:
    sys.path.insert(0, broker_path)

from broker.db import get_sync_session, init_db, engine
from broker.models import QueuedMessage
from sqlalchemy import select

HOST = "127.0.0.1"
PORT = 18765
URI = f"ws://{HOST}:{PORT}/broker"
WS_OPTS = {"max_queue": None, "compression": None, "ping_interval": None, "ping_timeout": None}


def _run_broker():
    from broker.main import app
    init_db()
    uvicorn.run(app, host=HOST, port=PORT, log_level="error")


@pytest.fixture(scope="module", autouse=True)
def server():
    t = threading.Thread(target=_run_broker, daemon=True)
    t.start()
    time.sleep(1.0)
    yield


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    async with websockets.connect(URI, **WS_OPTS) as ws:  # type: ignore
        pass


@pytest.mark.asyncio
async def test_message_delivered_to_subscribed_topic():
    async with websockets.connect(URI, **WS_OPTS) as sub:  # type: ignore
        await sub.send(json.dumps({"action": "subscribe", "topic": "test_a"}))
        resp = json.loads(await sub.recv())
        assert resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub:  # type: ignore
            await pub.send(
                json.dumps(
                    {"action": "publish", "topic": "test_a", "payload": {"val": 1}}
                )
            )

        resp = json.loads(await sub.recv())
        assert resp["action"] == "deliver"
        assert resp["topic"] == "test_a"
        assert resp["payload"] == {"val": 1}


@pytest.mark.asyncio
async def test_message_not_delivered_to_other_topic():
    async with websockets.connect(URI, **WS_OPTS) as sub_x:  # type: ignore
        await sub_x.send(json.dumps({"action": "subscribe", "topic": "topic_x"}))
        _ = json.loads(await sub_x.recv())

        async with websockets.connect(URI, **WS_OPTS) as pub:  # type: ignore
            await pub.send(
                json.dumps(
                    {"action": "publish", "topic": "topic_y", "payload": {"val": 99}}
                )
            )

        try:
            raw = await asyncio.wait_for(sub_x.recv(), timeout=0.5)
            msg = json.loads(raw)
            assert msg.get("topic") != "topic_y", "Should not receive from topic_y"
        except asyncio.TimeoutError:
            pass


@pytest.mark.asyncio
async def test_ack_marks_delivered():
    async with websockets.connect(URI, **WS_OPTS) as sub:  # type: ignore
        await sub.send(json.dumps({"action": "subscribe", "topic": "ack_test"}))
        _ = json.loads(await sub.recv())

        async with websockets.connect(URI, **WS_OPTS) as pub:  # type: ignore
            await pub.send(
                json.dumps(
                    {"action": "publish", "topic": "ack_test", "payload": {"x": 1}}
                )
            )

        resp = json.loads(await sub.recv())
        msg_id = resp["message_id"]

        await sub.send(json.dumps({"action": "ack", "message_id": msg_id}))

    await asyncio.sleep(0.2)

    with get_sync_session() as session:
        queued = session.execute(
            select(QueuedMessage).where(QueuedMessage.id == msg_id)
        ).scalar_one()
        assert queued.is_delivered is True
