# How to Run (Windows PowerShell)

## Prerequisites
Install dependencies using pip:
pip install -r requirements.txt

## Database Migration
Run the migration script (requires a shell like Git Bash or WSL if running .sh directly):
sh migrate.sh

Without git bash or wsl, just run this instead:
$env:PYTHONPATH="src;$env:PYTHONPATH"
alembic upgrade head

## Start the Server
$env:PYTHONPATH="src"
python -m uvicorn main:app --host 0.0.0.0 --port 8080

## Run Tests
$env:PYTHONPATH="src"
pytest tests/ -v

## Run the Benchmark
$env:PYTHONPATH="src"
python benchmark.py --uri ws://localhost:8080/broker --subs 5 --pubs 5 --msgs 10000 --format both

# Showcase

## 1. Health Check
curl.exe http://localhost:8080/

## 2. Create a Bucket
curl.exe -X POST http://localhost:8080/buckets/ -H "Content-Type: application/json" -d '{\"name\": \"my-bucket\"}'

## 3. Upload a File
"Hello from SKJ!" | Out-File -FilePath testfile.txt -Encoding ascii
curl.exe -X POST http://localhost:8080/files/upload -F "bucket_id=1" -F "file=@testfile.txt" -H "X-User-Id: alice"

## 4. List Files
curl.exe http://localhost:8080/files/ -H "X-User-Id: alice"

## 5. Download a File
# Replace <file_id> with your actual ID
curl.exe http://localhost:8080/files/<file_id> -H "X-User-Id: alice"

## 6. Bucket Billing
curl.exe http://localhost:8080/buckets/1/billing/

## 7. Delete a File (soft delete)
curl.exe -X DELETE http://localhost:8080/files/<file_id> -H "X-User-Id: alice"

## 8. Message Broker -- Interactive Mode
python mb_client.py --format json

## 9. Message Broker (JSON)
# Terminal 1 -- subscriber:
python mb_client.py --mode sub --topic showcase --format json

# Terminal 2 -- publisher:
python mb_client.py --mode pub --topic showcase --format json --payload '{\"temperature\": 23.5}' --count 3

## 10. Message Broker (MessagePack)
# Subscriber
python mb_client.py --mode sub --topic mp_showcase --format msgpack

# Publisher
python mb_client.py --mode pub --topic mp_showcase --format msgpack --payload '{\"sensor\": \"CPU\", \"value\": 72}' --count 2

## 11. Bucket Objects After Delete
curl.exe http://localhost:8080/buckets/1/objects/

# Client Modes Summary
| Mode | PowerShell Command | Description |
|------|---------|-------------|
| Interactive | python mb_client.py | REPL: sub, pub, ack |
| Subscriber | python mb_client.py --mode sub --topic <t> | Auto-subscribes and acks |
| Publisher | python mb_client.py --mode pub --topic <t> --payload '{\"k\": \"v\"}' | Sends N messages |

# API Endpoints Summary
| Method | Path | Description |
|--------|------|-------------|
| GET | / | Health check |
| POST | /buckets/ | Create bucket |
| GET | /buckets/{id}/objects/ | List files in bucket |
| GET | /buckets/{id}/billing/ | Bucket billing stats |
| GET | /files/ | List files (filter by X-User-Id) |
| POST | /files/upload | Upload file (form: bucket_id, file) |
| GET | /files/{id} | Download file |
| DELETE | /files/{id} | Soft-delete file |
| WS | /broker | WebSocket message broker |