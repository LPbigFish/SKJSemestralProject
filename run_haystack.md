# Haystack Photo Storage - Run & Test Guide

## Architecture

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Client     │─HTTP─>│  S3 Gateway  │─WS───>│   Broker     │
│  (curl/HTTP) │       │  :8080       │       │  :8082       │
└──────────────┘       └──────┬───────┘       └──────┬───────┘
                              │                      │
                      HTTP    │                      │ WS
                              v                      v
                       ┌──────────────┐       ┌──────────────┐
                       │Haystack Node │       │   Worker     │
                       │  :8081       │       │  (image proc)│
                       └──────────────┘       └──────────────┘
```

**4 services** that must run in separate terminals:
| Service | Port | Description |
|---------|------|-------------|
| Message Broker | 8082 | WebSocket pub/sub with SQLite persistence |
| Haystack Node | 8081 | Append-only storage engine |
| S3 Gateway | 8080 | HTTP API, orchestrates uploads/downloads |
| Worker | - | Subscribes to `image.jobs`, processes images |

## Quick Start

### 1. Install dependencies

```bash
# Using nix (recommended)
nix develop

# Or using pip
pip install -r requirements.txt
```

### 2. Initialize database

```bash
# From project root - creates repo.db and runs migrations
alembic upgrade head
```

### 3. Start all services (4 terminals)

**Terminal 1 - Message Broker:**
```bash
python -m broker.main
# Starts on ws://0.0.0.0:8082/broker
```

**Terminal 2 - Haystack Node:**
```bash
python src/haystack/haystack_node.py
# Starts on http://0.0.0.0:8081
# Connects to broker at ws://localhost:8082/broker
```

**Terminal 3 - S3 Gateway:**
```bash
python src/main.py
# Starts on http://0.0.0.0:8080
# Connects to broker at ws://localhost:8082/broker
```

**Terminal 4 - Worker:**
```bash
python worker/worker.py
# Connects to broker at ws://localhost:8082/broker
```

## Testing the API

### Health checks

```bash
curl http://localhost:8080/          # S3 Gateway status
curl http://localhost:8080/health    # Health check
curl http://localhost:8081/          # Haystack Node status
curl http://localhost:8082/          # Broker status
curl http://localhost:8082/health    # Broker health
```

### Create a bucket

```bash
curl -X POST http://localhost:8080/buckets/ \
  -H "Content-Type: application/json" \
  -d '{"name": "my-photos"}'
```

Response:
```json
{"name":"my-photos","id":1}
```

### Upload a photo

```bash
curl -X POST http://localhost:8080/files/upload \
  -F "bucket_id=1" \
  -F "file=@photo.jpg" \
  -H "X-User-Id: alice"
```

Response (202 Accepted):
```json
{"id":"<file_id>","filename":"photo.jpg","size":12345,"content_type":"image/jpeg"}
```

The file is sent asynchronously to the Haystack Node. The gateway ACK listener will update the DB when the write is confirmed.

### List all files

```bash
curl http://localhost:8080/files/ -H "X-User-Id: alice"
```

### List files in a bucket

```bash
curl http://localhost:8080/buckets/1/objects/
```

### Download a file

```bash
curl -OJ http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```

If the file is still uploading (status=uploading), returns 202 with a message to retry.

### Delete a file (soft delete)

```bash
curl -X DELETE http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```

### Check bucket billing

```bash
curl http://localhost:8080/buckets/1/billing/
```

Response includes `bandwidth_bytes`, `current_storage_bytes`, `ingress_bytes`, `egress_bytes`, `internal_transfer_bytes`.

## Image Processing (Worker)

### List available operations

```bash
curl http://localhost:8080/buckets/operations
```

Returns: `invert`, `flip`, `grayscale`, `brightness`, `crop`

### Process an image

```bash
# Invert colors
curl -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "invert"}'

# Flip image
curl -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "flip"}'

# Adjust brightness
curl -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "brightness", "params": {"value": 50}}'

# Convert to grayscale
curl -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "grayscale"}'

# Crop
curl -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "crop", "params": {"top": 10, "left": 10, "bottom": 200, "right": 200}}'
```

Response (202 Accepted):
```json
{"status": "processing_started"}
```

The worker downloads the image from the gateway, applies the operation, and uploads the result back.

### Check processing results

```bash
curl http://localhost:8080/buckets/1/objects/<file_id>/results
```

```json
{
  "jobs": [
    {
      "id": 1,
      "operation": "invert",
      "status": "completed",
      "result_file_id": "<new_file_id>",
      "error": null,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

Download the processed result using the `result_file_id`:
```bash
curl -OJ http://localhost:8080/files/<result_file_id> -H "X-User-Id: alice"
```

## Volume Compaction

Compaction removes soft-deleted objects and reclaims space in a volume.

```bash
# Compact a specific volume
python compact.py --volume-id 1

# Compact all non-active volumes
python compact.py --all
```

## Running Tests

```bash
# Run all tests (19 total)
pytest tests/ -v

# Run specific test suites
pytest tests/test_broker.py -v      # 4 broker tests
pytest tests/test_worker.py -v      # 4 worker tests (needs broker+gateway+haystack)
pytest tests/test_haystack.py -v    # 11 haystack tests (needs broker+gateway+haystack)
```

Tests start their own service instances on high ports to avoid conflicts.

## Full Demo Script

```bash
# 1. Create bucket
BUCKET=$(curl -s -X POST http://localhost:8080/buckets/ \
  -H "Content-Type: application/json" \
  -d '{"name": "demo"}')
echo "Bucket: $BUCKET"
BUCKET_ID=$(echo $BUCKET | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. Upload an image
RESULT=$(curl -s -X POST http://localhost:8080/files/upload \
  -F "bucket_id=$BUCKET_ID" \
  -F "file=@test_image.png" \
  -H "X-User-Id: alice")
echo "Upload: $RESULT"
FILE_ID=$(echo $RESULT | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 3. Wait for ACK (file to be stored in Haystack)
sleep 2

# 4. Download the file
curl -sOJ http://localhost:8080/files/$FILE_ID -H "X-User-Id: alice"
echo "Downloaded: $FILE_ID"

# 5. Process the image (invert)
curl -s -X POST http://localhost:8080/buckets/$BUCKET_ID/objects/$FILE_ID/process \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"operation": "invert"}'
echo "Processing started..."

# 6. Wait for processing
sleep 3

# 7. Get processing results
RESULTS=$(curl -s http://localhost:8080/buckets/$BUCKET_ID/objects/$FILE_ID/results)
echo "Results: $RESULTS"
NEW_ID=$(echo $RESULTS | python -c "import sys,json; print(json.load(sys.stdin)['jobs'][0]['result_file_id'])")

# 8. Download processed image
curl -sOJ http://localhost:8080/files/$NEW_ID -H "X-User-Id: alice"
echo "Processed image downloaded: $NEW_ID"

# 9. Check billing
curl -s http://localhost:8080/buckets/$BUCKET_ID/billing/ | python -m json.tool

# 10. Soft delete original
curl -s -X DELETE http://localhost:8080/files/$FILE_ID -H "X-User-Id: alice"

# 11. Compact volumes
python compact.py --all
```
