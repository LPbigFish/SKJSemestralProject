import asyncio
import json
from typing import Any

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from repository.db import engine
from repository.repo import QueuedMessage
from schemas.broker import BrokerMessage, DeliverMessage, SubscribedMessage

broker_router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.ws_topics: dict[WebSocket, str] = {}
        self.ws_binary: dict[WebSocket, bool] = {}
        self.ws_locks: dict[WebSocket, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    async def add(self, websocket: WebSocket, topic: str, binary: bool = False):
        async with self._lock:
            self.active_connections.setdefault(topic, set()).add(websocket)
            self.ws_topics[websocket] = topic
            self.ws_binary[websocket] = binary
            self.ws_locks[websocket] = asyncio.Lock()

    async def remove(self, websocket: WebSocket):
        async with self._lock:
            topic = self.ws_topics.pop(websocket, None)
            self.ws_binary.pop(websocket, None)
            self.ws_locks.pop(websocket, None)
            if topic and topic in self.active_connections:
                self.active_connections[topic].discard(websocket)
                if not self.active_connections[topic]:
                    del self.active_connections[topic]

    async def send_message(self, ws: WebSocket, data: dict):
        async with self._lock:
            binary = self.ws_binary.get(ws, False)
            lock = self.ws_locks.get(ws)

        if lock is None:
            return

        try:
            async with lock:
                if binary:
                    packed = msgpack.packb(data)
                    if isinstance(packed, bytes):
                        await ws.send_bytes(packed)
                else:
                    await ws.send_json(data)
        except Exception:
            await self.remove(ws)

    async def broadcast(self, data: dict, topic: str):
        async with self._lock:
            targets = list(self.active_connections.get(topic, set()))

        if not targets:
            return

        await asyncio.gather(
            *(self.send_message(ws, data) for ws in targets)
        )


manager = ConnectionManager()


def _store_message_sync(topic: str, payload: Any) -> int:
    with Session(bind=engine.connect()) as session:
        msg = QueuedMessage(topic=topic, payload=json.dumps(payload))
        session.add(msg)
        session.flush()
        msg_id = msg.id
        session.commit()
        return msg_id


def _ack_message_sync(message_id: int):
    with Session(bind=engine.connect()) as session:
        session.execute(
            update(QueuedMessage)
            .where(QueuedMessage.id == message_id)
            .values(is_delivered=True)
        )
        session.commit()


def _load_pending_sync(topic: str) -> list[dict]:
    with Session(bind=engine.connect()) as session:
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
                "payload": json.loads(m.payload),
            }
            for m in rows
        ]


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
