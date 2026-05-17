export interface FileMetadata {
	id: string;
	filename: string;
	size: number;
	content_type: string | null;
	created_at: string;
	status?: string;
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

export interface BucketListResponse {
	buckets: BucketResponse[];
	total: number;
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

export interface VolumeInfo {
	volume_id: number;
	size_bytes: number;
	path?: string;
}

export interface VolumeListResponse {
	volumes: VolumeInfo[];
}
