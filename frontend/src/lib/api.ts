import type {
	BillingResponse,
	BucketCreate,
	BucketObjectListResponse,
	BucketResponse,
	CreateFileResponse,
	DeleteResponse,
	FileListResponse,
	JobResultList,
	OperationInfo,
	ProcessRequest,
	ProcessResponse
} from './types';

function headers(userId?: string): HeadersInit {
	const h: Record<string, string> = {};
	if (userId) h['x-user-id'] = userId;
	return h;
}

export async function getFiles(userId?: string): Promise<FileListResponse> {
	const res = await fetch('/api/files/', { headers: headers(userId) });
	if (!res.ok) throw new Error(`Failed to fetch files: ${res.status}`);
	return res.json();
}

export async function getFileBlob(
	fileId: string,
	userId?: string
): Promise<{ blob: Blob; contentType: string | null; status: number }> {
	const res = await fetch(`/api/files/${encodeURIComponent(fileId)}`, {
		headers: headers(userId)
	});
	if (res.status === 202) return { blob: new Blob(), contentType: null, status: 202 };
	if (!res.ok) throw new Error(`Failed to fetch file: ${res.status}`);
	const blob = await res.blob();
	return { blob, contentType: res.headers.get('content-type'), status: res.status };
}

export async function deleteFile(fileId: string, userId?: string): Promise<DeleteResponse> {
	const res = await fetch(`/api/files/${encodeURIComponent(fileId)}`, {
		method: 'DELETE',
		headers: headers(userId)
	});
	if (!res.ok) throw new Error(`Failed to delete file: ${res.status}`);
	return res.json();
}

export async function uploadFile(
	bucketId: number,
	file: File,
	userId?: string
): Promise<CreateFileResponse> {
	const form = new FormData();
	form.append('bucket_id', String(bucketId));
	form.append('file', file);
	const res = await fetch('/api/files/upload', {
		method: 'POST',
		headers: headers(userId),
		body: form
	});
	if (!res.ok) throw new Error(`Failed to upload file: ${res.status}`);
	return res.json();
}

export async function createBucket(data: BucketCreate, userId?: string): Promise<BucketResponse> {
	const res = await fetch('/api/buckets/', {
		method: 'POST',
		headers: { ...headers(userId), 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	});
	if (!res.ok) throw new Error(`Failed to create bucket: ${res.status}`);
	return res.json();
}

export async function listBucketObjects(bucketId: number): Promise<BucketObjectListResponse> {
	const res = await fetch(`/api/buckets/${bucketId}/objects/`);
	if (!res.ok) throw new Error(`Failed to list bucket objects: ${res.status}`);
	return res.json();
}

export async function getBucketBilling(bucketId: number): Promise<BillingResponse> {
	const res = await fetch(`/api/buckets/${bucketId}/billing/`);
	if (!res.ok) throw new Error(`Failed to get billing: ${res.status}`);
	return res.json();
}

export async function getOperations(): Promise<OperationInfo[]> {
	const res = await fetch('/api/buckets/operations');
	if (!res.ok) throw new Error(`Failed to fetch operations: ${res.status}`);
	return res.json();
}

export async function processObject(
	bucketId: number,
	fileId: string,
	body: ProcessRequest,
	userId?: string
): Promise<ProcessResponse> {
	const res = await fetch(
		`/api/buckets/${bucketId}/objects/${encodeURIComponent(fileId)}/process`,
		{
			method: 'POST',
			headers: { ...headers(userId), 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		}
	);
	if (!res.ok) throw new Error(`Failed to process object: ${res.status}`);
	return res.json();
}

export async function getProcessingResults(
	bucketId: number,
	fileId: string
): Promise<JobResultList> {
	const res = await fetch(`/api/buckets/${bucketId}/objects/${encodeURIComponent(fileId)}/results`);
	if (!res.ok) throw new Error(`Failed to get processing results: ${res.status}`);
	return res.json();
}
