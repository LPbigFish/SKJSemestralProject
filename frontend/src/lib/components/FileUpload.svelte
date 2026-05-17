<script lang="ts">
	import { uploadFile } from '$lib/api';

	let {
		userId,
		bucketId,
		onUploaded
	}: {
		userId: string;
		bucketId: number;
		onUploaded: () => void;
	} = $props();

	let dragging = $state(false);
	let uploading = $state(false);
	let error = $state<string | null>(null);

	async function handleFiles(fileList: FileList) {
		if (!fileList.length) return;
		uploading = true;
		error = null;
		try {
			for (const file of Array.from(fileList)) {
				await uploadFile(bucketId, file, userId || undefined);
			}
			onUploaded();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Upload failed';
		} finally {
			uploading = false;
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragging = false;
		if (e.dataTransfer?.files.length) {
			handleFiles(e.dataTransfer.files);
		}
	}

	function onDragOver(e: DragEvent) {
		e.preventDefault();
		dragging = true;
	}

	function onDragLeave() {
		dragging = false;
	}

	function onInput(e: Event) {
		const target = e.target as HTMLInputElement;
		if (target.files?.length) {
			handleFiles(target.files);
			target.value = '';
		}
	}
</script>

<div
	role="button"
	tabindex="0"
	ondragover={onDragOver}
	ondragleave={onDragLeave}
	ondrop={onDrop}
	class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors {dragging
		? 'border-blue-500 bg-blue-50'
		: 'border-gray-300 bg-gray-50 hover:border-gray-400'}"
	onclick={() => document.getElementById('file-upload-input')?.click()}
	onkeydown={(e) => e.key === 'Enter' && document.getElementById('file-upload-input')?.click()}
>
	<input
		id="file-upload-input"
		type="file"
		class="hidden"
		multiple
		onchange={onInput}
		disabled={uploading}
	/>

	{#if uploading}
		<div class="flex items-center gap-2 text-blue-600">
			<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
				/>
			</svg>
			<span>Uploading...</span>
		</div>
	{:else}
		<svg class="mb-2 h-10 w-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
			/>
		</svg>
		<p class="text-sm text-gray-600">Drop files here or click to upload</p>
	{/if}
</div>

{#if error}
	<p class="mt-2 text-sm text-red-600">{error}</p>
{/if}
