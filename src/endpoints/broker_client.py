"""
broker_client.py – Persistent WebSocket client for Gateway→Broker communication.
Udržuje persistentní WebSocket spojení se standalone brokerem
a poskytuje async publish() metodu pro Gateway endpointy.
"""

import asyncio
import logging
import threading

import msgpack
import websockets

log = logging.getLogger(__name__)


class BrokerClient:
    def __init__(self, broker_uri: str):
        self._uri = broker_uri
        self._ws = None
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self):
        delay = 1
        while True:
            try:
                async with websockets.connect(
                    self._uri,
                    max_size=2**30,
                    max_queue=None,
                    compression=None,
                    ping_interval=None,
                    ping_timeout=None,
                ) as ws:
                    self._ws = ws
                    self._ready.set()
                    log.info("Broker client: připojeno k %s", self._uri)
                    delay = 1
                    async for _ in ws:
                        pass
            except Exception as e:
                log.warning(
                    "Broker client: chyba připojení (%s), zkouším za %ds",
                    e, delay,
                )
            finally:
                self._ws = None
                self._ready.clear()

            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def publish(self, topic: str, payload: dict):
        await asyncio.wait_for(self._ready.wait(), timeout=30.0)
        async with self._lock:
            data = msgpack.packb({
                "action": "publish",
                "topic": topic,
                "payload": payload,
            })
            await self._ws.send(data)


_tls = threading.local()


async def init_broker_client(broker_uri: str):
    client = BrokerClient(broker_uri)
    await client.start()
    _tls.client = client


def get_broker_client() -> BrokerClient:
    client = getattr(_tls, 'client', None)
    assert client is not None, "Broker client not initialized"
    return client
