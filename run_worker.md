# Image Processing Worker

## Prerequisites

Dependencies are included in the Nix flake (run `direnv allow` or `nix develop`).

Without Nix:

```bash
pip install -r worker/requirements.txt
```

## Start the S3 Gateway

The worker requires a running gateway + broker:

```bash
PYTHONPATH=src python main.py
```

## Start the Worker

```bash
python worker/worker.py
```

Default options:

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--broker-uri` | `ws://localhost:8080/broker` | WebSocket broker URI |
| `--gateway-url` | `http://localhost:8080` | S3 Gateway HTTP URL |

Custom:

```bash
python worker/worker.py --broker-uri ws://my-host:8080/broker --gateway-url http://my-host:8080
```

## Submit a Processing Job

```sh
curl -s -X POST http://localhost:8080/buckets/1/objects/<file_id>/process \
  -H 'Content-Type: application/json' \
  -d '{"operation": "grayscale"}'
```

Response (immediate):

```json
{"status": "processing_started"}
```

## Supported Operations

| Operation | JSON Body | Description |
| --------- | --------- | ----------- |
| `invert` | `{"operation": "invert"}` | Color inversion (negative) |
| `flip` | `{"operation": "flip"}` | Horizontal mirror |
| `crop` | `{"operation": "crop", "params": {"top": 10, "left": 10, "bottom": 200, "right": 200}}` | Crop to region (bounds checked) |
| `brightness` | `{"operation": "brightness", "params": {"value": 50}}` | Adjust brightness (+/- value, with saturation) |
| `grayscale` | `{"operation": "grayscale"}` | Weighted grayscale (ITU-R BT.601) |

## Completion Messages

The worker publishes results to `image.done`. Use the broker client to monitor:

```bash
python mb_client.py --mode sub --topic image.done
```

Success:

```json
{
  "status": "completed",
  "original_file_id": "<uuid>",
  "new_file_id": "<uuid>",
  "operation": "grayscale",
  "bucket_id": 1
}
```

Failure (invalid operation, crop out of bounds, etc.):

```json
{
  "status": "failed",
  "original_file_id": "<uuid>",
  "operation": "exploit-op",
  "bucket_id": 1,
  "error": "Unknown operation: exploit-op"
}
```

## Run Tests

```bash
PYTHONPATH=src pytest tests/test_worker.py -v
```

## End-to-End Example

Terminal 1 — gateway:

```bash
PYTHONPATH=src python main.py
```

Terminal 2 — worker:

```bash
python worker/worker.py
```

Terminal 3 — upload + process:

```sh
curl -s -X POST http://localhost:8080/buckets/ -H 'Content-Type: application/json' -d '{"name": "img-bucket"}'
# {"id": 1, ...}

curl -s -X POST http://localhost:8080/files/upload -F "bucket_id=1" -F "file=@photo.png"
# {"id": "abc-123", ...}

curl -s -X POST http://localhost:8080/buckets/1/objects/abc-123/process \
  -H 'Content-Type: application/json' \
  -d '{"operation": "invert"}'
# {"status": "processing_started"}
```

Terminal 4 — monitor completions:

```bash
python mb_client.py --mode sub --topic image.done
# [DELIVER] topic=image.done id=42 payload={'status': 'completed', 'original_file_id': 'abc-123', 'new_file_id': 'def-456', ...}
```
