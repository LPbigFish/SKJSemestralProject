# Frontend TODO — Adapt to 4-Service Architecture

Backend now consists of 4 independent services:

| Service       | Port | Role                          |
|---------------|------|-------------------------------|
| S3 Gateway    | 8080 | Main API (files, buckets, jobs)|
| Message Broker| 8082 | Pub/sub via WebSocket         |
| Haystack Node | 8081 | Append-only binary storage    |
| Worker        | 8083 | Image processing              |

---

## Must-Fix (broken right now)

### 1. `VolumeInfo.size` field name mismatch

`src/lib/types.ts:90` defines `size: number` but the Haystack API returns `size_bytes`.
The haystack page (`src/routes/haystack/+page.svelte:199`) renders `vol.size` → shows `undefined`.

**Fix in `src/lib/types.ts`:**
```ts
export interface VolumeInfo {
  volume_id: number;
  size_bytes: number;
  path?: string;
}
```

**Fix in `src/routes/haystack/+page.svelte`:**
```svelte
<!-- line 199: change vol.size → vol.size_bytes -->
{formatSize(vol.size_bytes)}
```

### 2. Worker import breaks when run as script

The backend worker must be started with `python -m worker.worker_app` (not `python src/worker/worker_app.py`).
This is already fixed in `start_all.sh`, but document it in the frontend README too.

---

## Should-Fix (UX gaps)

### 3. No "Create Bucket" UI

`createBucket()` exists in `src/lib/api.ts` but is never called. Users must know a bucket ID to use the app.

**Add a "Create Bucket" form** to `+page.svelte` — a simple input + button that calls `createBucket(name)` and sets the new bucket ID.

### 4. `createBucket()` missing `x-user-id` header

`src/lib/api.ts` — `createBucket()` sends only `Content-Type` but every other user-scoped call sends `x-user-id`. Add the user ID header for consistency.

### 5. No bucket list / switcher

Users type a bucket ID manually. Add a dropdown that calls `GET /files/` with the user ID and extracts distinct `bucket_id` values, or add a backend endpoint `GET /buckets/` that lists the user's buckets.

### 6. Upload status not visible

`ImagePreview` polls for 202→200, but the main file list (`FileBrowser`) doesn't show upload status. Files stuck in "uploading" appear in the list but fail to download with no explanation. Show a spinner/badge for files with status "uploading".

---

## Nice-to-Have (architecture improvements)

### 7. Worker health/status page

Add a page showing Worker health (`GET :8083/health`) and active processing jobs. Would need:
- New proxy: `src/routes/worker/api/[...path]/+server.ts` → `http://localhost:8083`
- New API module: `src/lib/worker-api.ts`

### 8. Broker status page

Add a page showing Broker health (`GET :8082/health`) and topic/queue status. Would need:
- New proxy: `src/routes/broker/api/[...path]/+server.ts` → `http://localhost:8082`

### 9. Real-time updates via WebSocket

Currently everything is HTTP polling:
- `ImagePreview` polls every 2s for upload completion
- `JobStatus` polls every 3s for job status
- Haystack page polls every 10s for health

Could subscribe to broker topics (`storage.ack`, `image.done`) directly from the browser via WebSocket for instant updates.

### 10. File type icons for non-image files

`ImagePreview` only renders image files. Add generic icons for PDFs, text files, etc.

### 11. Pagination

`getFiles()` and `listBucketObjects()` fetch everything at once. Add pagination controls when file counts grow.

### 12. Batch operations

Allow multi-select for batch delete or batch process.
