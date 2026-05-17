<script lang="ts">
	import { getFiles, listBucketObjects, createBucket } from '$lib/api';
	import type { FileMetadata } from '$lib/types';
	import FileUpload from '$lib/components/FileUpload.svelte';
	import FileBrowser from '$lib/components/FileBrowser.svelte';
	import BillingDashboard from '$lib/components/BillingDashboard.svelte';

	let userId = $state('');
	let bucketId = $state('');
	let files = $state.raw<FileMetadata[]>([]);
	let total = $state(0);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let newBucketName = $state('');
	let creatingBucket = $state(false);

	async function refreshFiles() {
		if (!userId) {
			files = [];
			total = 0;
			return;
		}
		loading = true;
		error = null;
		try {
			if (bucketIdNum > 0) {
				const res = await listBucketObjects(bucketIdNum);
				files = res.files;
				total = res.total;
			} else {
				const res = await getFiles(userId);
				files = res.files;
				total = res.total;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fetch files';
			files = [];
			total = 0;
		} finally {
			loading = false;
		}
	}

	async function handleCreateBucket() {
		if (!newBucketName.trim()) return;
		creatingBucket = true;
		error = null;
		try {
			const bucket = await createBucket({ name: newBucketName.trim() }, userId || undefined);
			bucketId = String(bucket.id);
			newBucketName = '';
			await refreshFiles();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create bucket';
		} finally {
			creatingBucket = false;
		}
	}

	function onUploadDone() {
		refreshFiles();
	}

	let bucketIdNum = $derived(Number(bucketId) || 0);

	$effect(() => {
		if (userId && bucketIdNum) refreshFiles();
	});
</script>

<svelte:head>
	<title>S3 Gateway - File Browser</title>
</svelte:head>

<div class="mx-auto max-w-6xl p-6">
	<h1 class="mb-6 text-2xl font-bold text-gray-900">S3 Gateway File Browser</h1>

	<div class="mb-6 flex flex-wrap items-end gap-4">
		<div class="flex-1" style="min-width: 200px;">
			<label for="user-id" class="mb-1 block text-sm font-medium text-gray-700">User ID</label>
			<div class="flex gap-2">
				<input
					id="user-id"
					type="text"
					bind:value={userId}
					placeholder="Enter user ID"
					class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					onkeydown={(e) => e.key === 'Enter' && refreshFiles()}
				/>
				<button
					onclick={refreshFiles}
					disabled={!userId || loading}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
				>
					{loading ? 'Loading...' : 'Fetch Files'}
				</button>
			</div>
		</div>
		<div style="min-width: 120px;">
			<label for="bucket-id" class="mb-1 block text-sm font-medium text-gray-700">Bucket ID</label>
			<input
				id="bucket-id"
				type="number"
				bind:value={bucketId}
				placeholder="e.g. 1"
				class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
			/>
		</div>
	</div>

	{#if error}
		<div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
			{error}
		</div>
	{/if}

	{#if userId}
		<section class="mb-6 rounded-lg border border-gray-200 bg-white p-4">
			<h2 class="mb-3 text-sm font-semibold text-gray-700">Create New Bucket</h2>
			<div class="flex gap-2">
				<input
					type="text"
					bind:value={newBucketName}
					placeholder="Bucket name"
					class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-green-500 focus:ring-1 focus:ring-green-500"
					onkeydown={(e) => e.key === 'Enter' && handleCreateBucket()}
				/>
				<button
					onclick={handleCreateBucket}
					disabled={!newBucketName.trim() || creatingBucket}
					class="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
				>
					{creatingBucket ? 'Creating...' : 'Create Bucket'}
				</button>
			</div>
		</section>

		{#if bucketIdNum > 0}
			<section class="mb-6">
				<h2 class="mb-3 text-lg font-semibold text-gray-800">Upload Files</h2>
				<FileUpload {userId} bucketId={bucketIdNum} onUploaded={onUploadDone} />
			</section>

			<section class="mb-6">
				<BillingDashboard bucketId={bucketIdNum} />
			</section>
		{:else}
			<div
				class="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-700"
			>
				Enter a Bucket ID or create a new bucket above to enable file uploads and processing.
			</div>
		{/if}

		<section>
			<h2 class="mb-3 text-lg font-semibold text-gray-800">
				Files
				{#if total > 0}
					<span class="text-sm font-normal text-gray-500">({total})</span>
				{/if}
			</h2>
			<FileBrowser {files} {userId} bucketId={bucketIdNum} onChanged={refreshFiles} />
		</section>
	{:else}
		<div class="rounded-lg border border-gray-200 bg-gray-50 px-6 py-12 text-center">
			<svg
				class="mx-auto mb-4 h-12 w-12 text-gray-300"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="1.5"
					d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
				/>
			</svg>
			<p class="text-gray-500">Enter your User ID and click "Fetch Files" to browse your files.</p>
		</div>
	{/if}
</div>
