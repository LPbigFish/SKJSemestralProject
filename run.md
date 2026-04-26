# How to Run

## Prerequisites

Install dependencies (Nix or pip):

```bash
# pip
pip install -r requirements.txt

# Nix
direnv allow   # or: nix develop
```

## Database Migration

```bash
bash migrate.sh
```

## Start the Server

```bash
PYTHONPATH=src python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

## Run Tests

```bash
PYTHONPATH=src pytest tests/ -v
```

## Run the Benchmark

```bash
PYTHONPATH=src python benchmark.py --uri ws://localhost:8080/broker --subs 5 --pubs 5 --msgs 10000 --format both
```

# Showcase

## 1. Health Check

```
$ curl http://localhost:8080/
["The API is RUNNING!!!"]
```

## 2. Create a Bucket

```
$ curl -s -X POST http://localhost:8080/buckets/ \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-bucket"}'
{
    "id": 1,
    "name": "my-bucket",
    "created_at": "2026-04-26T08:29:27.729773"
}
```

## 3. Upload a File

```
$ echo "Hello from SKJ!" > testfile.txt
$ curl -s -X POST http://localhost:8080/files/upload \
  -F "bucket_id=1" \
  -F "file=@testfile.txt" \
  -H "X-User-Id: alice"
{
    "id": "cb9511be-8fa2-4c74-bb49-86e2cd5f7d1a",
    "filename": "testfile.txt",
    "size": 16,
    "content_type": "text/plain"
}
```

## 4. List Files

```
$ curl -s http://localhost:8080/files/ -H "X-User-Id: alice"
{
    "files": [
        {
            "id": "cb9511be-8fa2-4c74-bb49-86e2cd5f7d1a",
            "filename": "testfile.txt",
            "size": 16,
            "content_type": "text/plain",
            "created_at": "2026-04-26T08:29:27.765988Z"
        }
    ],
    "total": 1
}
```

## 5. Download a File

```
$ curl http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
Hello from SKJ!
```

## 6. Bucket Billing

Tracks bandwidth, ingress, egress, storage, and internal transfer bytes.

```
$ curl -s http://localhost:8080/buckets/1/billing/
{
    "bucket_id": 1,
    "bucket_name": "my-bucket",
    "bandwidth_bytes": 32,
    "current_storage_bytes": 16,
    "ingress_bytes": 16,
    "egress_bytes": 16,
    "internal_transfer_bytes": 0
}
```

## 7. Delete a File (soft delete)

```
$ curl -s -X DELETE http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
{
    "message": "Soubor úspěšně smazán (soft delete)",
    "id": "cb9511be-8fa2-4c74-bb49-86e2cd5f7d1a"
}
```

## 8. Message Broker -- Interactive Mode

The default mode. Connects to the broker and opens a REPL where you can subscribe, publish, and ack.

```
$ python mb_client.py --format json
Connecting to ws://localhost:8080/broker (json)...
Connected. Type 'help' for commands.

> sub sensors
> [SUB] Subscribed to 'sensors'

> pub sensors {"temperature": 23.5}
[PUB] Sent to 'sensors'

> [DELIVER] topic=sensors id=5015 payload={'temperature': 23.5}

> ack 5015
[ACK] Acknowledged 5015

> help
Commands:
  sub <topic>              Subscribe to a topic
  pub <topic> <json>       Publish a message
  ack <message_id>         Acknowledge a message
  help                     Show this help
  quit / exit              Disconnect and exit

> quit
Bye.
```

Input validation catches common mistakes:

```
> pub missing_json
[ERR] Usage: pub <topic> <json_payload>

> pub mytopic notjson
[ERR] Invalid JSON: Expecting value: line 1 column 1 (char 0)

> ack notanumber
[ERR] message_id must be an integer

> bogus
[ERR] Unknown command: bogus  (type 'help' for commands)
```

Works with msgpack too: `python mb_client.py --format msgpack`

## 9. Message Broker (JSON)

Terminal 1 -- subscriber:

```
$ python mb_client.py --mode sub --topic showcase --format json
[SUB] Subscribed to 'showcase'
[DELIVER] topic=showcase id=5015 payload={'temperature': 23.5}
[DELIVER] topic=showcase id=5016 payload={'temperature': 23.5}
[DELIVER] topic=showcase id=5017 payload={'temperature': 23.5}
```

Terminal 2 -- publisher:

```
$ python mb_client.py --mode pub --topic showcase --format json \
  --payload '{"temperature": 23.5}' --count 3
[PUB] Sent 3 messages to 'showcase'
```

## 10. Message Broker (MessagePack)

```
$ python mb_client.py --mode sub --topic mp_showcase --format msgpack
[SUB] Subscribed to 'mp_showcase'
[DELIVER] topic=mp_showcase id=5018 payload={'sensor': 'CPU', 'value': 72}
[DELIVER] topic=mp_showcase id=5019 payload={'sensor': 'CPU', 'value': 72}
```

```
$ python mb_client.py --mode pub --topic mp_showcase --format msgpack \
  --payload '{"sensor": "CPU", "value": 72}' --count 2
[PUB] Sent 2 messages to 'mp_showcase'
```

## 11. Bucket Objects After Delete

```
$ curl -s http://localhost:8080/buckets/1/objects/
{
    "bucket_id": 1,
    "files": [],
    "total": 0
}
```

# Client Modes

| Mode | Command | Description |
|------|---------|-------------|
| Interactive | `python mb_client.py` | REPL: sub, pub, ack with input validation |
| Subscriber | `python mb_client.py --mode sub --topic <t>` | Auto-subscribes and acks |
| Publisher | `python mb_client.py --mode pub --topic <t> --payload '<json>'` | Sends N messages |

# API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| POST | `/buckets/` | Create bucket |
| GET | `/buckets/{id}/objects/` | List files in bucket |
| GET | `/buckets/{id}/billing/` | Bucket billing stats |
| GET | `/files/` | List files (filter by `X-User-Id`) |
| POST | `/files/upload` | Upload file (form: `bucket_id`, `file`) |
| GET | `/files/{id}` | Download file |
| DELETE | `/files/{id}` | Soft-delete file |
| WS | `/broker` | WebSocket message broker |
