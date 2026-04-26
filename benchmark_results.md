# Benchmark Results

## Configuration

- **CPU:** Intel Core i5-12600KF
- **RAM:** 32 GB DDR4
- **OS:** NixOS Linux
- **Python:** 3.13.12
- **Broker:** FastAPI
- **Database:** SQLite (WAL mode)
- **Date:** 2026-04-23

## Test Parameters

- 5 concurrent Subscribers
- 5 concurrent Publishers
- 1000 messages per Publisher
- Total messages: 5000 published, 25000 delivered (each sub gets all msgs)
- Payload: `{"temp": 67, "sensor_id": 1, "status": "ok"}`

## Results

| Format     | Messages Received | Time (s)  | Throughput (msg/s)  |
|------------|------------------:|----------:|--------------------:|
| JSON       |             25000 |     16.32 |                1532 |
| MessagePack|             25000 |     15.97 |                1566 |

## Analysis

MessagePack is faster (~2.2%) than JSON in this benchmark.

## How to Run

```bash
# Terminal 1: Start the broker
PYTHONPATH=src uvicorn main:app --host 0.0.0.0 --port 8080

# Terminal 2: Run benchmark
python benchmark.py --subs 5 --pubs 5 --msgs 1000 --format both
```
