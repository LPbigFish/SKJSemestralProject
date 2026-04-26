import json
import logging
import threading
from typing import Any

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from repository.db import engine
from repository.repo import QueuedMessage
from schemas.broker import BrokerMessage, DeliverMessage, SubscribedMessage

logger = logging.getLogger(__name__)

broker_router = APIRouter()

_db_lock = threading.Lock()


def _db_save(topic: str, payload: Any) -> int:
    with _db_lock:
        session = Session(bind=engine.connect())
        try:
            msg = QueuedMessage(topic=topic, payload=json.dumps(payload))
            session.add(msg)
            session.commit()
            session.refresh(msg)
            return msg.id
        finally:
            session.close()


def _db_ack(message_id: int):
    with _db_lock:
        session = Session(bind=engine.connect())
        try:
            session.execute(
                update(QueuedMessage)
                .where(QueuedMessage.id == message_id)
                .values(is_delivered=True)
            )
            session.commit()
        finally:
            session.close()


def _db_get_undelivered(topic: str) -> list[dict]:
    with _db_lock:
        session = Session(bind=engine.connect())
        try:
            rows = (
                session.execute(
                    select(QueuedMessage)
                    .where(
                        QueuedMessage.topic == topic,
                        QueuedMessage.is_delivered == False,
                    )
                    .order_by(QueuedMessage.id)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "topic": m.topic,
                    "message_id": m.id,
                    "payload": json.loads(m.payload),
                }
                for m in rows
            ]
        finally:
            session.close()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.ws_topics: dict[WebSocket, str] = {}
        self.ws_binary: dict[WebSocket, bool] = {}

    def add(self, websocket: WebSocket, topic: str, binary: bool = False):
        self.active_connections.setdefault(topic, set()).add(websocket)
        self.ws_topics[websocket] = topic
        self.ws_binary[websocket] = binary

    def remove(self, websocket: WebSocket):
        topic = self.ws_topics.pop(websocket, None)
        self.ws_binary.pop(websocket, None)
        if topic and topic in self.active_connections:
            self.active_connections[topic].discard(websocket)
            if not self.active_connections[topic]:
                del self.active_connections[topic]

    async def _send(self, ws: WebSocket, data: dict):
        if self.ws_binary.get(ws, False):
            packed = msgpack.packb(data)
            if isinstance(packed, bytes):
                await ws.send_bytes(packed)
        else:
            await ws.send_json(data)

    async def broadcast_to_topic(self, data: dict, topic: str):
        if topic not in self.active_connections:
            return
        dead = []
        for ws in list(self.active_connections[topic]):
            try:
                await self._send(ws, data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(ws)


manager = ConnectionManager()


async def _send_undelivered(websocket: WebSocket, topic: str):
    messages = await run_in_threadpool(_db_get_undelivered, topic)
    for m in messages:
        deliver = DeliverMessage(
            topic=m["topic"], message_id=m["message_id"], payload=m["payload"]
        )
        await manager._send(websocket, deliver.model_dump())


async def _handle_publish(msg: BrokerMessage):
    if msg.topic is None:
        return
    msg_id: int = await run_in_threadpool(_db_save, msg.topic, msg.payload)
    deliver = DeliverMessage(topic=msg.topic, message_id=msg_id, payload=msg.payload)
    await manager.broadcast_to_topic(deliver.model_dump(), msg.topic)


async def _handle_ack(msg: BrokerMessage):
    if msg.message_id is None:
        return
    await run_in_threadpool(_db_ack, msg.message_id)


@broker_router.websocket("/broker")
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
                manager.add(websocket, topic, binary=binary)
                sub_conf = SubscribedMessage(topic=topic)
                await manager._send(websocket, sub_conf.model_dump())
                await _send_undelivered(websocket, topic)

            elif msg.action == "publish":
                await _handle_publish(msg)

            elif msg.action == "ack":
                await _handle_ack(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if topic:
            manager.remove(websocket)
