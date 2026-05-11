import asyncio

import msgpack
from fastapi import WebSocket


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
