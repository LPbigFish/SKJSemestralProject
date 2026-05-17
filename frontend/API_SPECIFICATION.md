# API Specification

## Architecture Overview

```
Frontend (SvelteKit) ──► S3 Gateway (:8080) ──► Haystack Node (:8081)
                              │                        │
                              ├─ REST API              ├─ Volume storage
                              ├─ WebSocket broker      ├─ Append-only writes
                              └─ SQLite metadata DB    └─ Compaction
```

All frontend requests go through the S3 Gateway via `/api/` proxy.  
The Haystack Node is an internal service — not directly exposed to the frontend.

---

## S3 Gateway — `http://localhost:8080`

Base path for frontend: `/api` (proxied by SvelteKit)

### Buckets

#### `POST /buckets/`
Create a new bucket.

**Request:**
```json
{ "name": "my-bucket" }
```

**Response `201`:**
```json
{
  "id": 1,
  "name": "my-bucket",
  "created_at": "2026-05-17T12:00:00"
}
```

---

#### `GET /buckets/{bucket_id}/objects/`
List all non-deleted files in a bucket.

**Response `200`:**
```json
{
  "bucket_id": 1,
  "files": [
    {
      "id": "abc123",
      "filename": "photo.png",
      "size": 4096,
      "content_type": "image/png",
      "created_at": "2026-05-17T12:00:00"
    }
  ],
  "total": 1
}
```

---

#### `GET /buckets/{bucket_id}/billing/`
Get bandwidth and storage billing for a bucket.

**Response `200`:**
```json
{
  "bucket_id": 1,
  "bucket_name": "my-bucket",
  "bandwidth_bytes": 8192,
  "current_storage_bytes": 4096,
  "ingress_bytes": 4096,
  "egress_bytes": 2048,
  "internal_transfer_bytes": 2048
}
```

---

### Files

#### `GET /files/`
List files for a user. Optional `X-User-Id` header filters by user.

**Headers:** `X-User-Id: <user_id>` (optional)

**Response `200`:**
```json
{
  "files": [
    {
      "id": "abc123",
      "filename": "photo.png",
      "size": 4096,
      "content_type": "image/png",
      "created_at": "2026-05-17T12:00:00"
    }
  ],
  "total": 1
}
```

---

#### `POST /files/upload`
Upload a file. Returns `202 Accepted` — file is persisted asynchronously via the Haystack Node. The file starts with `status="uploading"` and transitions to `"ready"` once the Haystack Node confirms storage.

**Headers:** `X-User-Id: <user_id>` (optional)

**Request:** `multipart/form-data`
- `bucket_id` (int, required)
- `file` (binary, required)

**Response `202`:**
```json
{
  "id": "abc123",
  "filename": "photo.png",
  "size": 4096,
  "content_type": "image/png"
}
```

> **Important:** After upload, the file is in `"uploading"` status. Poll `GET /files/{file_id}` until you get a `200` response (not `202`) before attempting to display or process the file.

---

#### `GET /files/{file_id}`
Download a file by ID.

**Headers:**
- `X-User-Id: <user_id>` (optional)
- `X-Internal-Source: true` (internal use only — marks as internal transfer for billing)

**Responses:**
- `200` — File binary content (Content-Disposition: attachment)
- `202` — File is still uploading (Haystack Node hasn't confirmed storage yet)
- `403` — Access denied (wrong user)
- `404` — File not found or deleted
- `502` — Haystack Node returned an error
- `503` — Haystack Node unreachable

**Response headers:** `Content-Type`, `Content-Disposition`

---

#### `DELETE /files/{file_id}`
Soft-delete a file.

**Headers:** `X-User-Id: <user_id>` (optional)

**Response `200`:**
```json
{
  "message": "Soubor úspěšně smazán (soft delete)",
  "id": "abc123"
}
```

---

### Image Processing

#### `GET /buckets/operations`
List available image processing operations.

**Response `200`:**
```json
[
  {
    "operation": "brightness",
    "params": [
      { "name": "value", "type": "int", "required": false, "default": 0 }
    ]
  },
  {
    "operation": "crop",
    "params": [
      { "name": "top", "type": "int", "required": false, "default": 0 },
      { "name": "left", "type": "int", "required": false, "default": 0 },
      { "name": "bottom", "type": "int", "required": false },
      { "name": "right", "type": "int", "required": false }
    ]
  },
  { "operation": "flip", "params": [] },
  { "operation": "grayscale", "params": [] },
  { "operation": "invert", "params": [] }
]
```

---

#### `POST /buckets/{bucket_id}/objects/{file_id}/process`
Start an image processing job. Returns `202` — processing is async.

**Headers:** `X-User-Id: <user_id>` (optional)

**Request:**
```json
{
  "operation": "invert",
  "params": {}
}
```

**Response `202`:**
```json
{ "status": "processing_started" }
```

Supported operations: `invert`, `flip`, `grayscale`, `brightness`, `crop`

---

#### `GET /buckets/{bucket_id}/objects/{file_id}/results`
Get processing job results for a file.

**Response `200`:**
```json
{
  "jobs": [
    {
      "id": 42,
      "operation": "invert",
      "status": "completed",
      "result_file_id": "def456",
      "error": null,
      "created_at": "2026-05-17T12:00:00",
      "updated_at": "2026-05-17T12:00:05"
    }
  ],
  "total": 1
}
```

Job statuses: `processing` → `completed` | `failed`

When `status == "completed"`, `result_file_id` is the ID of the processed output file (download via `GET /files/{result_file_id}`).

---

## Haystack Storage Node — `http://localhost:8081`

Internal service — **not proxied to the frontend**. Used by the S3 Gateway.

### Endpoints

#### `GET /health`
Health check.

**Response `200`:**
```json
{
  "status": "ok",
  "active_volume": 1,
  "volume_size_bytes": 524288,
  "max_volume_bytes": 104857600
}
```

---

#### `GET /volumes`
List all storage volumes.

**Response `200`:**
```json
{
  "volumes": [
    { "volume_id": 1, "size_bytes": 524288, "path": "haystack_volumes/volume_1.dat" }
  ]
}
```

---

#### `GET /volume/{volume_id}/{offset}/{size}`
Read raw bytes from a volume file at the given offset and size. Used internally by the S3 Gateway to serve file downloads.

**Response `200`:** Binary `application/octet-stream`

**Error responses:**
- `404` — Volume doesn't exist
- `416` — Requested range doesn't match available data
- `500` — I/O error

---

#### `POST /compact/{volume_id}`
Compact a volume by removing deleted objects and defragmenting.

**Query params:** `gateway_url` (optional — override gateway URL)

**Response `200`:**
```json
{
  "status": "compacted",
  "volume_id": 1,
  "objects_moved": 15
}
```

**Error responses:**
- `404` — Volume doesn't exist
- `409` — Cannot compact the active volume

---

## TypeScript Types

These are already defined in `src/lib/types.ts`:

```typescript
export interface FileMetadata {
  id: string;
  filename: string;
  size: number;
  content_type: string | null;
  created_at: string;
}

export interface FileListResponse {
  files: FileMetadata[];
  total: number;
}

export interface CreateFileResponse {
  id: string;
  filename: string;
  size: number;
  content_type: string | null;
}

export interface DeleteResponse {
  message: string;
  id: string;
}

export interface BucketCreate {
  name: string;
}

export interface BucketResponse {
  id: number;
  name: string;
  created_at: string;
}

export interface BucketObjectListResponse {
  bucket_id: number;
  files: FileMetadata[];
  total: number;
}

export interface BillingResponse {
  bucket_id: number;
  bucket_name: string;
  bandwidth_bytes: number;
  current_storage_bytes: number;
  ingress_bytes: number;
  egress_bytes: number;
  internal_transfer_bytes: number;
}

export interface OperationParam {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
}

export interface OperationInfo {
  operation: string;
  params: OperationParam[];
}

export interface ProcessRequest {
  operation: string;
  params?: Record<string, unknown> | null;
}

export interface ProcessResponse {
  status: string;
}

export interface JobResult {
  id: number;
  operation: string;
  status: string;
  result_file_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobResultList {
  jobs: JobResult[];
  total: number;
}
```

## Key Behavioral Notes for Frontend

1. **Upload flow is async:** `POST /files/upload` returns `202`. The file transitions `uploading → ready` via the Haystack Node. Poll `GET /files/{file_id}` — a `202` response means still uploading, `200` means ready.

2. **Processing flow is async:** `POST /.../process` returns `202`. Poll `GET /.../results` to check job status. When `status === "completed"`, use `result_file_id` to download the output.

3. **Billing:** Egress/ingress is tracked per-bucket. Internal transfers (worker → gateway) are billed separately from user-facing downloads.
