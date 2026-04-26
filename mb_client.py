import argparse
import asyncio
import json
import sys
from typing import Any

import msgpack
import websockets


def encode(data: dict, use_msgpack: bool) -> bytes | str:
    if use_msgpack:
        result: Any = msgpack.packb(data)
        return bytes(result)
    return json.dumps(data)


def decode(raw: bytes, use_msgpack: bool) -> dict:
    if use_msgpack:
        return msgpack.unpackb(raw, raw=False)
    return json.loads(raw)


async def _send(ws, data: dict, use_msgpack: bool):
    await ws.send(encode(data, use_msgpack))


async def subscriber(uri: str, topic: str, use_msgpack: bool):
    async with websockets.connect(uri) as ws:
        await _send(ws, {"action": "subscribe", "topic": topic}, use_msgpack)

        while True:
            raw = await ws.recv()
            msg = decode(raw if isinstance(raw, bytes) else raw.encode(), use_msgpack)
            action = msg.get("action", "")
            if action == "subscribed":
                print(f"[SUB] Subscribed to '{topic}'")
                continue
            if action == "deliver":
                print(
                    f"[DELIVER] topic={msg['topic']} "
                    f"id={msg['message_id']} "
                    f"payload={msg['payload']}"
                )
                await _send(
                    ws,
                    {"action": "ack", "message_id": msg["message_id"]},
                    use_msgpack,
                )


async def publisher(
    uri: str, topic: str, use_msgpack: bool, payload: dict, count: int, interval: float
):
    async with websockets.connect(uri) as ws:
        for _ in range(count):
            await _send(
                ws,
                {"action": "publish", "topic": topic, "payload": payload},
                use_msgpack,
            )
            if interval > 0:
                await asyncio.sleep(interval)
    print(f"[PUB] Sent {count} messages to '{topic}'")


def _print_help():
    print("Commands:")
    print("  sub <topic>              Subscribe to a topic")
    print("  pub <topic> <json>       Publish a message")
    print("  ack <message_id>         Acknowledge a message")
    print("  help                     Show this help")
    print("  quit / exit              Disconnect and exit")


def _parse_line(line: str) -> tuple[str, dict[str, Any]] | None:
    parts = line.strip().split(None, 1)
    if not parts:
        return None

    cmd = parts[0].lower()

    if cmd in ("quit", "exit"):
        return ("quit", {})
    if cmd == "help":
        return ("help", {})

    if cmd == "sub":
        if len(parts) < 2 or not parts[1].strip():
            print("[ERR] Usage: sub <topic>")
            return None
        topic = parts[1].strip()
        if " " in topic:
            print("[ERR] Topic must not contain spaces")
            return None
        return ("sub", {"topic": topic})

    if cmd == "ack":
        if len(parts) < 2 or not parts[1].strip():
            print("[ERR] Usage: ack <message_id>")
            return None
        try:
            msg_id = int(parts[1].strip())
        except ValueError:
            print("[ERR] message_id must be an integer")
            return None
        return ("ack", {"message_id": msg_id})

    if cmd == "pub":
        if len(parts) < 2:
            print("[ERR] Usage: pub <topic> <json_payload>")
            return None
        rest = parts[1]
        first_space = rest.find(" ")
        if first_space == -1:
            print("[ERR] Usage: pub <topic> <json_payload>")
            return None
        topic = rest[:first_space].strip()
        payload_str = rest[first_space + 1 :].strip()
        if " " in topic:
            print("[ERR] Topic must not contain spaces")
            return None
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            print(f"[ERR] Invalid JSON: {e}")
            return None
        if not isinstance(payload, dict):
            print("[ERR] Payload must be a JSON object")
            return None
        return ("pub", {"topic": topic, "payload": payload})

    print(f"[ERR] Unknown command: {cmd}  (type 'help' for commands)")
    return None


async def interactive(uri: str, use_msgpack: bool):
    print(f"Connecting to {uri} ({'msgpack' if use_msgpack else 'json'})...")
    async with websockets.connect(uri) as ws:
        print("Connected. Type 'help' for commands.\n")

        async def recv_loop():
            try:
                async for raw in ws:
                    msg = decode(
                        raw if isinstance(raw, bytes) else raw.encode(), use_msgpack
                    )
                    action = msg.get("action", "")
                    if action == "subscribed":
                        print(f"\n[SUB] Subscribed to '{msg['topic']}'")
                    elif action == "deliver":
                        print(
                            f"\n[DELIVER] topic={msg['topic']} "
                            f"id={msg['message_id']} "
                            f"payload={msg['payload']}"
                        )
                    else:
                        print(f"\n[MSG] {msg}")
                    print("> ", end="", flush=True)
            except websockets.ConnectionClosed:
                print("\n[DISCONNECTED]")

        recv_task = asyncio.create_task(recv_loop())

        loop = asyncio.get_event_loop()
        try:
            while not recv_task.done():
                line = await loop.run_in_executor(None, lambda: sys.stdin.readline())
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                parsed = _parse_line(line)
                if parsed is None:
                    continue

                cmd, args = parsed
                if cmd == "quit":
                    break
                if cmd == "help":
                    _print_help()
                    continue
                if cmd == "sub":
                    await _send(ws, {"action": "subscribe", "topic": args["topic"]}, use_msgpack)
                elif cmd == "pub":
                    await _send(
                        ws,
                        {"action": "publish", "topic": args["topic"], "payload": args["payload"]},
                        use_msgpack,
                    )
                    print(f"[PUB] Sent to '{args['topic']}'")
                elif cmd == "ack":
                    await _send(ws, {"action": "ack", "message_id": args["message_id"]}, use_msgpack)
                    print(f"[ACK] Acknowledged {args['message_id']}")
        except KeyboardInterrupt:
            pass
        finally:
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

    print("Bye.")


def main():
    parser = argparse.ArgumentParser(description="Message Broker Client")
    parser.add_argument(
        "--mode",
        choices=["pub", "sub", "interactive"],
        default="interactive",
        help="Mode: pub, sub, or interactive (default: interactive)",
    )
    parser.add_argument("--topic", help="Topic name (pub/sub mode)")
    parser.add_argument(
        "--format",
        choices=["json", "msgpack"],
        default="json",
        help="Serialization format",
    )
    parser.add_argument("--uri", default="ws://localhost:8080/broker", help="Broker URI")
    parser.add_argument("--count", type=int, default=1, help="Number of messages (pub)")
    parser.add_argument("--interval", type=float, default=0, help="Delay between messages (pub)")
    parser.add_argument(
        "--payload", default='{"data": "hello"}', help="JSON payload (pub)"
    )

    args = parser.parse_args()
    use_msgpack = args.format == "msgpack"

    if args.mode == "sub":
        if not args.topic:
            parser.error("--topic is required for sub mode")
        asyncio.run(subscriber(args.uri, args.topic, use_msgpack))
    elif args.mode == "pub":
        if not args.topic:
            parser.error("--topic is required for pub mode")
        payload = json.loads(args.payload)
        asyncio.run(
            publisher(args.uri, args.topic, use_msgpack, payload, args.count, args.interval)
        )
    else:
        asyncio.run(interactive(args.uri, use_msgpack))


if __name__ == "__main__":
    main()
