"""
broker_client.py - WebSocket client for Gateway to publish to the Message Broker.
==============================================================================

The Gateway no longer embeds the broker. Instead, it connects to the standalone
broker service via WebSocket and publishes messages through this client.
"""

import asyncio
import json
import logging
import os
from typing import Any

import msgpack
import websockets

log = logging.getLogger(__name__)

BROKER_URI: str = os.environ.get("BROKER_URI", "ws://localhost:8082/broker")

_publish_queue: asyncio.Queue | None = None
_publisher_task: asyncio.Task | None = None


async def publish_to_broker(topic: str, payload: Any) -> int:
    """
    Queue a message for publishing to the broker (fire-and-forget).
    Returns 0 as a placeholder (the message_id is generated server-side).
    """
    global _publish_queue

    if _publish_queue is None:
        raise RuntimeError("Broker client not started. Call start_broker_client() first.")

    await _publish_queue.put((topic, payload))
    return 0


async def start_broker_client():
    global _publish_queue, _publisher_task
    _publish_queue = asyncio.Queue()
    _publisher_task = asyncio.create_task(_publisher_loop())


async def stop_broker_client():
    global _publisher_task
    if _publisher_task:
        _publisher_task.cancel()
        try:
            await _publisher_task
        except asyncio.CancelledError:
            pass
        _publisher_task = None


async def _publisher_loop():
    """
    Maintains a persistent WebSocket connection to the broker.
    Drains the publish queue and sends messages.
    Reconnects with exponential backoff on failure.
    """
    import broker_client as _self

    reconnect_delay = 2

    while True:
        try:
            current_uri = _self.BROKER_URI
            log.info("Broker client: connecting to %s", current_uri)

            async with websockets.connect(
                current_uri,
                max_queue=None,
                compression=None,
                ping_interval=None,
                ping_timeout=None,
            ) as ws:
                log.info("Broker client: connected to %s", current_uri)
                reconnect_delay = 2

                while True:
                    topic, payload = await _publish_queue.get()

                    try:
                        pub_msg: bytes = msgpack.packb({  # type: ignore[assignment]
                            "action": "publish",
                            "topic": topic,
                            "payload": payload,
                        })
                        await ws.send(pub_msg)
                    except Exception as e:
                        log.error("Broker client: publish failed: %s", e)
                        raise

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log.warning("Broker client: broker unavailable (%s), retrying in %ds", e, reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)

        except asyncio.CancelledError:
            break

        except Exception as e:
            log.error("Broker client: unexpected error: %s", e)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
