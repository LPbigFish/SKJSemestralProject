"""
broker/main.py - Message Broker
===============================
Standalone Pub/Sub message broker service.

Spusteni:
    python -m broker.main
    # nebo
    python broker/main.py --host 0.0.0.0 --port 8082
"""

import argparse
import asyncio
import base64
import json
import logging
from typing import Any

import msgpack
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from broker.connection_manager import ConnectionManager
from broker.db import engine, get_sync_session, init_db
from broker.models import QueuedMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BROKER] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


class BrokerMessage(BaseModel):
    action: str
    topic: str | None = None
    payload: Any = None
    message_id: int | None = None


class DeliverMessage(BaseModel):
    action: str = "deliver"
    topic: str
    message_id: int
    payload: Any


class SubscribedMessage(BaseModel):
    action: str = "subscribed"
    topic: str


manager = ConnectionManager()


def _serialize_payload(payload: Any) -> str:
    """Serialize payload to string, handling bytes values via base64."""
    import msgpack as _mp

    def _convert(obj):
        if isinstance(obj, bytes):
            return {"__bytes_b64__": base64.b64encode(obj).decode("ascii")}
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_convert(v) for v in obj]
        return obj

    return json.dumps(_convert(payload))


def _store_message_sync(topic: str, payload: Any) -> int:
    with get_sync_session() as session:
        msg = QueuedMessage(topic=topic, payload=_serialize_payload(payload))
        session.add(msg)
        session.flush()
        msg_id = msg.id
        session.commit()
        return msg_id


def _ack_message_sync(message_id: int):
    with get_sync_session() as session:
        session.execute(
            update(QueuedMessage)
            .where(QueuedMessage.id == message_id)
            .values(is_delivered=True)
        )
        session.commit()


def _deserialize_payload(payload_str: str) -> Any:
    """Deserialize payload from string, restoring base64-encoded bytes."""
    def _convert(obj):
        if isinstance(obj, dict):
            if "__bytes_b64__" in obj:
                return base64.b64decode(obj["__bytes_b64__"])
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(v) for v in obj]
        return obj

    return _convert(json.loads(payload_str))


def _load_pending_sync(topic: str) -> list[dict]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(QueuedMessage)
            .where(
                QueuedMessage.topic == topic,
                QueuedMessage.is_delivered == False,
            )
            .order_by(QueuedMessage.id)
        ).all()
        return [
            {
                "topic": m.topic,
                "message_id": m.id,
                "payload": _deserialize_payload(m.payload),
            }
            for m in rows
        ]


async def broker_endpoint(websocket: WebSocket):
    await websocket.accept()
    topic: str | None = None
    binary = False

    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break
            if "text" in raw and raw["text"] is not None:
                data = json.loads(raw["text"])
                binary = False
            elif "bytes" in raw and raw["bytes"] is not None:
                data = msgpack.unpackb(raw["bytes"], raw=False)
                binary = True
            else:
                continue

            msg = BrokerMessage(**data)

            if msg.action == "subscribe":
                topic = msg.topic
                if topic is None:
                    continue
                await manager.add(websocket, topic, binary=binary)
                sub_conf = SubscribedMessage(topic=topic)
                await manager.send_message(websocket, sub_conf.model_dump())

                pending = await run_in_threadpool(_load_pending_sync, topic)
                for m in pending:
                    deliver = DeliverMessage(**m)
                    await manager.send_message(websocket, deliver.model_dump())

            elif msg.action == "publish":
                if msg.topic is None:
                    continue
                msg_id = await run_in_threadpool(
                    _store_message_sync, msg.topic, msg.payload
                )
                deliver = DeliverMessage(
                    topic=msg.topic, message_id=msg_id, payload=msg.payload
                )
                await manager.broadcast(deliver.model_dump(), msg.topic)

            elif msg.action == "ack":
                if msg.message_id is not None:
                    await run_in_threadpool(_ack_message_sync, msg.message_id)
    except WebSocketDisconnect:
        pass
    finally:
        if topic:
            await manager.remove(websocket)


app = FastAPI(title="Message Broker")

app.websocket("/broker")(broker_endpoint)


@app.get("/")
def info():
    return {"status": "Message Broker is RUNNING"}


@app.get("/health")
def health():
    return {"status": "ok"}


def main():
    parser = argparse.ArgumentParser(description="Message Broker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8082)
    args = parser.parse_args()

    init_db()
    log.info("Broker database initialized")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
