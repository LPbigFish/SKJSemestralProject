<script lang="ts">
	import { deleteFile, getFileBlob } from '$lib/api';
	import type { FileMetadata } from '$lib/types';
	import ImagePreview from './ImagePreview.svelte';
	import ProcessDialog from './ProcessDialog.svelte';
	import JobStatus from './JobStatus.svelte';
	import { SvelteSet } from 'svelte/reactivity';

	let {
		files,
		userId,
		bucketId,
		onChanged
	}: {
		files: FileMetadata[];
		userId: string;
		bucketId: number;
		onChanged: () => void;
	} = $props();

	let previewFileId = $state<string | null>(null);
	let expandedJobsFor = $state<string | null>(null);
	let deleting = new SvelteSet<string>();

	function isImage(file: FileMetadata): boolean {
		return file.content_type?.startsWith('image/') ?? false;
	}

	function isUploading(file: FileMetadata): boolean {
		return file.status === 'uploading';
	}

	function fileTypeIcon(contentType: string | null): string {
		if (!contentType) return 'file';
		if (contentType.startsWith('image/')) return 'image';
		if (contentType === 'application/pdf') return 'pdf';
		if (contentType.startsWith('text/')) return 'text';
		if (contentType.startsWith('video/')) return 'video';
		if (contentType.startsWith('audio/')) return 'audio';
		if (contentType.includes('zip') || contentType.includes('tar') || contentType.includes('gzip'))
			return 'archive';
		return 'file';
	}

	function fileTypeLabel(icon: string): string {
		const labels: Record<string, string> = {
			pdf: 'PDF',
			text: 'TXT',
			video: 'VID',
			audio: 'AUD',
			archive: 'ZIP',
			image: 'IMG',
			file: 'File'
		};
		return labels[icon] ?? 'File';
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString();
	}

	async function handleDownload(file: FileMetadata) {
		try {
			const { blob } = await getFileBlob(file.id, userId || undefined);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = file.filename;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Download failed');
		}
	}

	async function handleDelete(fileId: string) {
		if (!confirm('Delete this file?')) return;
		deleting.add(fileId);
		try {
			await deleteFile(fileId, userId || undefined);
			onChanged();
		} catch (e) {
			alert(e instanceof Error ? e.message : 'Delete failed');
		} finally {
			deleting.delete(fileId);
		}
	}

	function toggleJobs(fileId: string) {
		expandedJobsFor = expandedJobsFor === fileId ? null : fileId;
	}
</script>

{#if !files.length}
	<p class="py-8 text-center text-gray-500">No files found. Upload some files to get started.</p>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full text-left text-sm">
			<thead>
				<tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
					<th class="px-3 py-2">Preview</th>
					<th class="px-3 py-2">Filename</th>
					<th class="px-3 py-2">Size</th>
					<th class="px-3 py-2">Type</th>
					<th class="px-3 py-2">Created</th>
					<th class="px-3 py-2 text-right">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each files as file (file.id)}
					<tr class="border-b border-gray-100 hover:bg-gray-50">
						<td class="px-3 py-2">
							{#if isUploading(file)}
								<div
									class="flex h-12 w-12 items-center justify-center rounded bg-yellow-50"
									title="Uploading..."
								>
									<svg class="h-6 w-6 animate-spin text-yellow-500" viewBox="0 0 24 24" fill="none">
										<circle
											class="opacity-25"
											cx="12"
											cy="12"
											r="10"
											stroke="currentColor"
											stroke-width="4"
										/>
										<path
											class="opacity-75"
											fill="currentColor"
											d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
										/>
									</svg>
								</div>
							{:else if isImage(file)}
								<button
									onclick={() => (previewFileId = file.id)}
									class="block overflow-hidden rounded"
								>
									<ImagePreview fileId={file.id} {userId} thumbnail={true} />
								</button>
							{:else}
								<div
									class="flex h-12 w-12 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-500"
									title={file.content_type ?? ''}
								>
									{fileTypeLabel(fileTypeIcon(file.content_type))}
								</div>
							{/if}
						</td>
						<td class="max-w-[200px] truncate px-3 py-2 font-medium" title={file.filename}>
							{file.filename}
						</td>
						<td class="px-3 py-2 text-gray-600">{formatSize(file.size)}</td>
						<td class="px-3 py-2 text-gray-600">{file.content_type ?? 'unknown'}</td>
						<td class="px-3 py-2 text-gray-600">{formatDate(file.created_at)}</td>
						<td class="px-3 py-2">
							<div class="flex items-center justify-end gap-1">
								<button
									onclick={() => handleDownload(file)}
									class="rounded px-2 py-1 text-sm text-blue-700 hover:bg-blue-100"
									title="Download"
								>
									<svg class="inline h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
										/>
									</svg>
								</button>
								<button
									onclick={() => handleDelete(file.id)}
									disabled={deleting.has(file.id)}
									class="rounded px-2 py-1 text-sm text-red-700 hover:bg-red-100 disabled:opacity-50"
									title="Delete"
								>
									<svg class="inline h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
										/>
									</svg>
								</button>
								<ProcessDialog
									{bucketId}
									fileId={file.id}
									{userId}
									onProcessed={() => {
										toggleJobs(file.id);
										onChanged();
									}}
								/>
								<button
									onclick={() => toggleJobs(file.id)}
									class="rounded px-2 py-1 text-sm text-gray-600 hover:bg-gray-100"
									title="Job status"
								>
									<svg class="inline h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
										/>
									</svg>
								</button>
							</div>
						</td>
					</tr>
					{#if expandedJobsFor === file.id}
						<tr>
							<td colspan="6" class="px-3 py-2">
								<JobStatus {bucketId} fileId={file.id} {userId} />
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
{/if}

{#if previewFileId}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
		role="dialog"
		tabindex="-1"
		onclick={() => (previewFileId = null)}
		onkeydown={(e) => e.key === 'Escape' && (previewFileId = null)}
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="relative max-h-[90vh] max-w-[90vw]" onclick={(e) => e.stopPropagation()}>
			<button
				onclick={() => (previewFileId = null)}
				class="absolute -top-3 -right-3 rounded-full bg-white p-2 shadow-lg hover:bg-gray-100"
				aria-label="Close preview"
			>
				<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
			<ImagePreview fileId={previewFileId} {userId} />
		</div>
	</div>
{/if}
