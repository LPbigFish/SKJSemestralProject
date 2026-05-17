import json
import asyncio
import sys
import threading

import pytest
import uvicorn
import websockets

from conftest import wait_for_ready

HOST = "127.0.0.1"
PORT = 18765
URI = f"ws://{HOST}:{PORT}/broker"
WS_OPTS = {"max_queue": None, "compression": None, "ping_interval": None, "ping_timeout": None}


def _run_server():
    sys.path.insert(0, "src")
    from broker.broker_app import app
    uvicorn.run(app, host=HOST, port=PORT, log_level="error",
                ws_ping_interval=None, ws_ping_timeout=None)


@pytest.fixture(scope="module", autouse=True)
def server():
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    wait_for_ready(f"http://{HOST}:{PORT}/health")
    yield


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    async with websockets.connect(URI, **WS_OPTS) as ws: # type: ignore
        pass


@pytest.mark.asyncio
async def test_message_delivered_to_subscribed_topic():
    async with websockets.connect(URI, **WS_OPTS) as sub: # type: ignore
        await sub.send(json.dumps({"action": "subscribe", "topic": "test_a"}))
        resp = json.loads(await sub.recv())
        assert resp["action"] == "subscribed"

        async with websockets.connect(URI, **WS_OPTS) as pub: # type: ignore
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
    async with websockets.connect(URI, **WS_OPTS) as sub_x: # type: ignore
        await sub_x.send(json.dumps({"action": "subscribe", "topic": "topic_x"}))
        _ = json.loads(await sub_x.recv())

        async with websockets.connect(URI, **WS_OPTS) as pub: # type: ignore
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
    async with websockets.connect(URI, **WS_OPTS) as sub: # type: ignore
        await sub.send(json.dumps({"action": "subscribe", "topic": "ack_test"}))
        _ = json.loads(await sub.recv())

        async with websockets.connect(URI, **WS_OPTS) as pub: # type: ignore
            await pub.send(
                json.dumps(
                    {"action": "publish", "topic": "ack_test", "payload": {"x": 1}}
                )
            )

        resp = json.loads(await sub.recv())
        msg_id = resp["message_id"]

        await sub.send(json.dumps({"action": "ack", "message_id": msg_id}))

    await asyncio.sleep(0.2)

    from repository.db import get_sync_session
    from repository.repo import QueuedMessage
    from sqlalchemy import select

    session = get_sync_session()
    try:
        queued = session.execute(
            select(QueuedMessage).where(QueuedMessage.id == msg_id)
        ).scalar_one()
        assert queued.is_delivered is True
    finally:
        session.close()


@pytest.mark.asyncio
async def test_pending_messages_delivered_on_subscribe():
    async with websockets.connect(URI, **WS_OPTS) as pub: # type: ignore
        await pub.send(
            json.dumps(
                {"action": "publish", "topic": "pending_test", "payload": {"val": 42}}
            )
        )

    await asyncio.sleep(0.2)

    async with websockets.connect(URI, **WS_OPTS) as sub: # type: ignore
        await sub.send(json.dumps({"action": "subscribe", "topic": "pending_test"}))
        resp = json.loads(await sub.recv())
        assert resp["action"] == "subscribed"

        resp = json.loads(await sub.recv())
        assert resp["action"] == "deliver"
        assert resp["topic"] == "pending_test"
        assert resp["payload"] == {"val": 42}
