import argparse
import asyncio
import json
import time
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


async def subscriber_task(
    uri: str,
    topic: str,
    use_msgpack: bool,
    expected: int,
    results: dict,
    sub_id: int,
):
    received = 0
    async with websockets.connect(uri, max_size=2**24) as ws:
        sub_msg = encode({"action": "subscribe", "topic": topic}, use_msgpack)
        await ws.send(sub_msg)

        while received < expected:
            raw = await ws.recv()
            msg = decode(raw if isinstance(raw, bytes) else raw.encode(), use_msgpack)
            if msg.get("action") == "subscribed":
                continue
            if msg.get("action") == "deliver":
                received += 1
                ack = encode(
                    {"action": "ack", "message_id": msg["message_id"]},
                    use_msgpack,
                )
                await ws.send(ack)

    results[sub_id] = received


async def publisher_task(
    uri: str,
    topic: str,
    use_msgpack: bool,
    count: int,
    payload: dict,
):
    async with websockets.connect(uri, max_size=2**24) as ws:
        for _ in range(count):
            msg = encode(
                {"action": "publish", "topic": topic, "payload": payload},
                use_msgpack,
            )
            await ws.send(msg)


async def run_benchmark(
    uri: str,
    topic: str,
    use_msgpack: bool,
    num_subs: int,
    num_pubs: int,
    msgs_per_pub: int,
):
    total_msgs = num_pubs * msgs_per_pub
    expected_per_sub = total_msgs
    payload = {"temp": 67, "sensor_id": 1, "status": "ok"}

    sub_results: dict[int, int] = {}

    sub_tasks = [
        subscriber_task(
            uri,
            topic,
            use_msgpack,
            expected_per_sub,
            sub_results,
            i,
        )
        for i in range(num_subs)
    ]

    async def delayed_pubs():
        await asyncio.sleep(0.5)
        pub_coros = [
            publisher_task(uri, topic, use_msgpack, msgs_per_pub, payload)
            for _ in range(num_pubs)
        ]
        await asyncio.gather(*pub_coros)

    start = time.perf_counter()

    await asyncio.gather(*sub_tasks, delayed_pubs())

    elapsed = time.perf_counter() - start
    total_received = sum(sub_results.values())
    throughput = total_received / elapsed if elapsed > 0 else 0

    return total_received, elapsed, throughput


async def main():
    parser = argparse.ArgumentParser(description="Broker Benchmark")
    parser.add_argument("--uri", default="ws://localhost:8080/broker")
    parser.add_argument("--subs", type=int, default=5)
    parser.add_argument("--pubs", type=int, default=5)
    parser.add_argument("--msgs", type=int, default=10000)
    parser.add_argument(
        "--format",
        choices=["json", "msgpack", "both"],
        default="both",
    )
    args = parser.parse_args()

    if args.format in ("json", "both"):
        print("=== JSON Benchmark ===")
        total, elapsed, throughput = await run_benchmark(
            args.uri, "bench_json", False, args.subs, args.pubs, args.msgs
        )
        print(f"Messages received: {total}")
        print(f"Time: {elapsed:.2f}s")
        print(f"Throughput: {throughput:.0f} msg/s")

    if args.format in ("msgpack", "both"):
        print("\n=== MessagePack Benchmark ===")
        total, elapsed, throughput = await run_benchmark(
            args.uri, "bench_msgpack", True, args.subs, args.pubs, args.msgs
        )
        print(f"Messages received: {total}")
        print(f"Time: {elapsed:.2f}s")
        print(f"Throughput: {throughput:.0f} msg/s")


if __name__ == "__main__":
    asyncio.run(main())
