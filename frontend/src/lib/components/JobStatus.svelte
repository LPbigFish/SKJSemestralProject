<script lang="ts">
	import { getProcessingResults } from '$lib/api';
	import type { JobResult } from '$lib/types';
	import ImagePreview from './ImagePreview.svelte';

	let {
		bucketId,
		fileId,
		userId,
		initialExpanded = false
	}: {
		bucketId: number;
		fileId: string;
		userId: string;
		initialExpanded?: boolean;
	} = $props();

	let jobs = $state.raw<JobResult[]>([]);
	let loading = $state(false);
	let polling = $state(false);
	let expanded = $state(false);
	let previewFileId = $state<string | null>(null);
	let intervalId: ReturnType<typeof setInterval> | null = null;
	let mounted = $state(false);

	$effect(() => {
		if (!mounted && initialExpanded) {
			expanded = true;
			fetchResults();
		}
		mounted = true;
	});

	let activeJobs = $derived(
		jobs.filter(
			(j) =>
				j.status !== 'done' &&
				j.status !== 'error' &&
				j.status !== 'completed' &&
				j.status !== 'failed'
		)
	);

	let completedJobs = $derived(
		jobs.filter(
			(j) =>
				j.status === 'done' ||
				j.status === 'error' ||
				j.status === 'completed' ||
				j.status === 'failed'
		)
	);

	function statusColor(status: string): string {
		switch (status) {
			case 'done':
			case 'completed':
				return 'bg-green-100 text-green-800';
			case 'error':
			case 'failed':
				return 'bg-red-100 text-red-800';
			case 'processing':
			case 'running':
				return 'bg-blue-100 text-blue-800';
			default:
				return 'bg-yellow-100 text-yellow-800';
		}
	}

	async function fetchResults() {
		loading = true;
		try {
			const res = await getProcessingResults(bucketId, fileId);
			jobs = res.jobs;
		} catch {
			jobs = [];
		} finally {
			loading = false;
		}
	}

	function startPolling() {
		if (polling) return;
		polling = true;
		fetchResults();
		intervalId = setInterval(fetchResults, 3000);
	}

	function stopPolling() {
		polling = false;
		if (intervalId) {
			clearInterval(intervalId);
			intervalId = null;
		}
	}

	function toggle() {
		expanded = !expanded;
		if (expanded) {
			fetchResults();
			if (activeJobs.length > 0) startPolling();
		} else {
			stopPolling();
		}
	}

	$effect(() => {
		if (expanded && activeJobs.length > 0 && !polling) {
			startPolling();
		} else if (expanded && activeJobs.length === 0 && polling) {
			stopPolling();
		}
	});
</script>

<div class="rounded-lg border border-gray-200">
	<button
		onclick={toggle}
		class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-gray-700 hover:bg-gray-50"
	>
		<span>
			Processing Jobs ({jobs.length})
			{#if completedJobs.length > 0}
				<span class="text-gray-400">({completedJobs.length} completed)</span>
			{/if}
		</span>
		<svg
			class="h-4 w-4 transition-transform {expanded ? 'rotate-180' : ''}"
			fill="none"
			viewBox="0 0 24 24"
			stroke="currentColor"
		>
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
		</svg>
	</button>

	{#if expanded}
		<div class="border-t border-gray-200 px-4 py-3">
			{#if loading && !jobs.length}
				<p class="text-sm text-gray-500">Loading jobs...</p>
			{:else if !jobs.length}
				<p class="text-sm text-gray-500">No processing jobs yet.</p>
			{:else}
				<div class="space-y-2">
					{#each activeJobs as job (job.id)}
						<div
							class="flex items-center justify-between rounded border border-blue-100 bg-blue-50/50 px-3 py-2"
						>
							<div class="flex items-center gap-3">
								<span class="font-mono text-xs text-gray-500">#{job.id}</span>
								<span class="text-sm">{job.operation}</span>
								<span
									class="rounded-full px-2 py-0.5 text-xs font-medium {statusColor(job.status)}"
								>
									{job.status}
								</span>
							</div>
							<div class="flex items-center gap-2">
								{#if job.error}
									<span class="text-xs text-red-500">{job.error}</span>
								{/if}
								{#if job.result_file_id}
									<button
										onclick={() => (previewFileId = job.result_file_id)}
										class="text-xs text-blue-600 hover:underline"
									>
										View Result
									</button>
								{/if}
							</div>
						</div>
					{/each}
					{#if completedJobs.length > 0}
						<details class="group">
							<summary class="cursor-pointer text-xs text-gray-400 hover:text-gray-600">
								{completedJobs.length} completed job{completedJobs.length > 1 ? 's' : ''}
							</summary>
							<div class="mt-2 space-y-2">
								{#each completedJobs as job (job.id)}
									<div
										class="flex items-center justify-between rounded border border-gray-100 px-3 py-2 opacity-60"
									>
										<div class="flex items-center gap-3">
											<span class="font-mono text-xs text-gray-500">#{job.id}</span>
											<span class="text-sm">{job.operation}</span>
											<span
												class="rounded-full px-2 py-0.5 text-xs font-medium {statusColor(
													job.status
												)}"
											>
												{job.status}
											</span>
										</div>
										<div class="flex items-center gap-2">
											{#if job.error}
												<span class="text-xs text-red-500">{job.error}</span>
											{/if}
											{#if job.result_file_id}
												<button
													onclick={() => (previewFileId = job.result_file_id)}
													class="text-xs text-blue-600 hover:underline"
												>
													View Result
												</button>
											{/if}
										</div>
									</div>
								{/each}
							</div>
						</details>
					{/if}
				</div>
			{/if}

			<button
				onclick={fetchResults}
				disabled={loading}
				class="mt-2 text-xs text-gray-500 hover:text-gray-700"
			>
				{loading ? 'Refreshing...' : 'Refresh'}
			</button>
		</div>
	{/if}
</div>

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
				class="absolute -top-3 -right-3 rounded-full bg-white p-1 shadow-lg hover:bg-gray-100"
				aria-label="Close preview"
			>
				<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
