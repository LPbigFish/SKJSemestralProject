import argparse
import asyncio
import json
import time
import uuid
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
    ready_event: asyncio.Event,
    subscriber_count: int,
    ready_lock: asyncio.Lock,
    ready_counter: list[int],
    progress: dict,
):
    received = 0
    async with websockets.connect(
        uri, max_size=2**24, max_queue=None, compression=None,
        ping_interval=None, ping_timeout=None,
    ) as ws:
        sub_msg = encode({"action": "subscribe", "topic": topic}, use_msgpack)
        await ws.send(sub_msg)

        while True:
            raw = await ws.recv()
            msg = decode(raw if isinstance(raw, bytes) else raw.encode(), use_msgpack)
            if msg.get("action") == "subscribed":
                async with ready_lock:
                    ready_counter[0] += 1
                    if ready_counter[0] == subscriber_count:
                        ready_event.set()
                break

        while received < expected:
            raw = await ws.recv()
            msg = decode(raw if isinstance(raw, bytes) else raw.encode(), use_msgpack)
            if msg.get("action") == "deliver":
                received += 1
                progress["sub_recv"][sub_id] = received
                if sub_id == 0:
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
    pub_id: int,
    progress: dict,
):
    sent = 0
    async with websockets.connect(
        uri, max_size=2**24, max_queue=None, compression=None,
        ping_interval=None, ping_timeout=None,
    ) as ws:
        for _ in range(count):
            msg = encode(
                {"action": "publish", "topic": topic, "payload": payload},
                use_msgpack,
            )
            await ws.send(msg)
            sent += 1
            progress["pub_sent"][pub_id] = sent
    progress["pub_done"][pub_id] = True


async def progress_monitor(progress: dict, expected_per_sub: int, num_subs: int, num_pubs: int):
    try:
        while True:
            await asyncio.sleep(2)
            elapsed = time.perf_counter() - progress["start"]
            pub_total = sum(progress["pub_sent"].values())
            pubs_done = sum(progress["pub_done"].values())
            sub_total = sum(progress["sub_recv"].values())
            total_expected = expected_per_sub * num_subs
            pct = (sub_total / total_expected * 100) if total_expected else 0
            sub_details = " ".join(
                f"s{i}={progress['sub_recv'].get(i, 0)}" for i in range(num_subs)
            )
            print(
                f"  [{elapsed:6.1f}s] pubs: {pubs_done}/{num_pubs} done ({pub_total} sent) | "
                f"subs: {sub_total}/{total_expected} ({pct:5.1f}%) [{sub_details}]",
                flush=True,
            )
    except asyncio.CancelledError:
        pass


async def run_benchmark(
    uri: str,
    topic: str,
    use_msgpack: bool,
    num_subs: int,
    num_pubs: int,
    msgs_per_pub: int,
    timeout: float = 300,
) -> tuple[int, float, float] | None:
    total_msgs = num_pubs * msgs_per_pub
    expected_per_sub = total_msgs
    payload = {"temp": 67, "sensor_id": 1, "status": "ok"}

    sub_results: dict[int, int] = {}
    ready_event = asyncio.Event()
    ready_lock = asyncio.Lock()
    ready_counter = [0]

    progress = {
        "start": 0,
        "pub_sent": {},
        "pub_done": {},
        "sub_recv": {},
    }

    sub_tasks = [
        asyncio.create_task(
            subscriber_task(
                uri, topic, use_msgpack, expected_per_sub, sub_results, i,
                ready_event, num_subs, ready_lock, ready_counter, progress,
            )
        )
        for i in range(num_subs)
    ]

    try:
        await asyncio.wait_for(ready_event.wait(), timeout=15)
    except asyncio.TimeoutError:
        print("  TIMEOUT: subscribers failed to connect within 15s", flush=True)
        for t in sub_tasks:
            t.cancel()
        return None

    progress["start"] = time.perf_counter()
    start = progress["start"]

    pub_tasks = [
        asyncio.create_task(
            publisher_task(uri, topic, use_msgpack, msgs_per_pub, payload, i, progress)
        )
        for i in range(num_pubs)
    ]

    monitor = asyncio.create_task(
        progress_monitor(progress, expected_per_sub, num_subs, num_pubs)
    )

    try:
        await asyncio.wait_for(
            asyncio.gather(*pub_tasks, *sub_tasks), timeout=timeout
        )
    except asyncio.TimeoutError:
        print(
            f"  TIMEOUT: benchmark exceeded {timeout}s, cancelling...", flush=True
        )
        for t in pub_tasks:
            t.cancel()
        for t in sub_tasks:
            t.cancel()
        await asyncio.gather(*pub_tasks, *sub_tasks, return_exceptions=True)
        total_received = sum(sub_results.values())
        elapsed = time.perf_counter() - start
        monitor.cancel()
        await monitor
        return total_received, elapsed, total_received / elapsed if elapsed > 0 else 0

    elapsed = time.perf_counter() - start
    total_received = sum(sub_results.values())
    throughput = total_received / elapsed if elapsed > 0 else 0
    monitor.cancel()
    await monitor

    return total_received, elapsed, throughput


async def main():
    parser = argparse.ArgumentParser(description="Broker Benchmark")
    parser.add_argument("--uri", default="ws://localhost:8080/broker")
    parser.add_argument("--subs", type=int, default=5)
    parser.add_argument("--pubs", type=int, default=5)
    parser.add_argument("--msgs", type=int, default=1000)
    parser.add_argument(
        "--format",
        choices=["json", "msgpack", "both"],
        default="both",
    )
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    formats = ["json", "msgpack"] if args.format == "both" else [args.format]

    for fmt in formats:
        use_msgpack = fmt == "msgpack"
        label = "MessagePack" if use_msgpack else "JSON"
        topic = f"bench_{fmt}_{uuid.uuid4().hex[:8]}"

        print(f"=== {label} Benchmark ===", flush=True)
        print(
            f"  subs={args.subs} pubs={args.pubs} msgs/pub={args.msgs} "
            f"total_pub={args.pubs * args.msgs} "
            f"total_delivered={args.pubs * args.msgs * args.subs}",
            flush=True,
        )

        result = await run_benchmark(
            args.uri, topic, use_msgpack, args.subs, args.pubs, args.msgs,
            timeout=args.timeout,
        )
        if result is None:
            print("  Benchmark failed.", flush=True)
            continue

        total_received, elapsed, throughput = result
        expected = args.pubs * args.msgs * args.subs
        print(f"Messages received: {total_received}/{expected}", flush=True)
        print(f"Time: {elapsed:.2f}s", flush=True)
        print(f"Throughput: {throughput:.0f} msg/s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
