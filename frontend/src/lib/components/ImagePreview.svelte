<script lang="ts">
	import { getFileBlob } from '$lib/api';

	let {
		fileId,
		userId,
		thumbnail = false
	}: {
		fileId: string;
		userId: string;
		thumbnail?: boolean;
	} = $props();

	let objectUrl = $state<string | null>(null);
	let loading = $state(true);
	let failed = $state(false);

	let timer: ReturnType<typeof setTimeout> | null = null;
	let attempts = 0;
	const MAX_ATTEMPTS = 15;

	function load() {
		failed = false;

		getFileBlob(fileId, userId || undefined)
			.then(({ blob, status }) => {
				if (status === 202) {
					attempts++;
					if (attempts >= MAX_ATTEMPTS) {
						failed = true;
						loading = false;
						return;
					}
					timer = setTimeout(load, 2000);
					return;
				}
				objectUrl = URL.createObjectURL(blob);
				loading = false;
			})
			.catch(() => {
				failed = true;
				loading = false;
			});
	}

	$effect(() => {
		attempts = 0;
		objectUrl = null;
		loading = true;
		failed = false;
		load();
		return () => {
			if (timer) clearTimeout(timer);
			if (objectUrl) URL.revokeObjectURL(objectUrl);
		};
	});
</script>

{#if loading}
	<div
		class="flex items-center justify-center bg-gray-100 {thumbnail
			? 'h-12 w-12 rounded'
			: 'h-64 w-full rounded-lg'}"
	>
		<svg class="h-5 w-5 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path
				class="opacity-75"
				fill="currentColor"
				d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
			/>
		</svg>
	</div>
{:else if failed}
	<div
		class="flex items-center justify-center bg-red-50 text-red-400 {thumbnail
			? 'h-12 w-12 rounded text-xs'
			: 'h-64 w-full rounded-lg text-sm'}"
	>
		Failed
	</div>
{:else if objectUrl}
	<img
		src={objectUrl}
		alt="Preview"
		class="rounded object-contain {thumbnail ? 'h-12 w-12' : 'max-h-[80vh] max-w-full'}"
	/>
{/if}
