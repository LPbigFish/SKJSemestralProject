<script lang="ts">
	import { getHealth, listVolumes, compactVolume, compactAll } from '$lib/haystack-api';
	import type { VolumeInfo } from '$lib/types';

	let healthy = $state<boolean | null>(null);
	let volumes = $state.raw<VolumeInfo[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let compactingId = $state<number | null>(null);
	let compactingAll = $state(false);
	let compactResult = $state<{ volumeId: number | string; message: string } | null>(null);
	let gatewayUrl = $state('');
	let healthPolling = false;
	let healthInterval: ReturnType<typeof setInterval> | null = null;

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
		return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
	}

	async function checkHealth() {
		try {
			healthy = await getHealth();
		} catch {
			healthy = false;
		}
	}

	async function refreshVolumes() {
		loading = true;
		error = null;
		try {
			const res = await listVolumes();
			volumes = res.volumes ?? [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fetch volumes';
			volumes = [];
		} finally {
			loading = false;
		}
	}

	async function handleCompact(volumeId: number) {
		compactingId = volumeId;
		compactResult = null;
		try {
			await compactVolume(volumeId, gatewayUrl || undefined);
			compactResult = { volumeId, message: 'Compaction completed successfully' };
			await refreshVolumes();
		} catch (e) {
			compactResult = {
				volumeId,
				message: e instanceof Error ? e.message : 'Compaction failed'
			};
		} finally {
			compactingId = null;
		}
	}

	async function handleCompactAll() {
		compactingAll = true;
		compactResult = null;
		try {
			await compactAll(gatewayUrl || undefined);
			compactResult = { volumeId: 'all', message: 'Global compaction completed successfully' };
			await refreshVolumes();
		} catch (e) {
			compactResult = {
				volumeId: 'all',
				message: e instanceof Error ? e.message : 'Global compaction failed'
			};
		} finally {
			compactingAll = false;
		}
	}

	function startHealthPolling() {
		if (healthPolling) return;
		healthPolling = true;
		checkHealth();
		healthInterval = setInterval(checkHealth, 10000);
	}

	function stopHealthPolling() {
		healthPolling = false;
		if (healthInterval) {
			clearInterval(healthInterval);
			healthInterval = null;
		}
	}

	import { onMount } from 'svelte';

	onMount(() => {
		startHealthPolling();
		refreshVolumes();
		return () => stopHealthPolling();
	});
</script>

<svelte:head>
	<title>Haystack Storage Node</title>
</svelte:head>

<div class="mx-auto max-w-6xl p-6">
	<div class="mb-6 flex items-center justify-between">
		<div class="flex items-center gap-3">
			<h1 class="text-2xl font-bold text-gray-900">Haystack Storage Node</h1>
			{#if healthy === true}
				<span
					class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
					Healthy
				</span>
			{:else if healthy === false}
				<span
					class="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-red-500"></span>
					Unreachable
				</span>
			{:else}
				<span
					class="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-gray-400"></span>
					Checking...
				</span>
			{/if}
		</div>
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href="/" class="text-sm text-blue-600 hover:underline">&larr; Back to File Browser</a>
	</div>

	{#if error}
		<div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
			{error}
		</div>
	{/if}

	{#if compactResult}
		<div
			class="mb-4 rounded-lg border {compactResult.message.includes('failed') ||
			compactResult.message.includes('Failed')
				? 'border-red-200 bg-red-50 text-red-700'
				: 'border-green-200 bg-green-50 text-green-700'} px-4 py-3 text-sm"
		>
			Volume {compactResult.volumeId}: {compactResult.message}
		</div>
	{/if}

	<section class="mb-6">
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-gray-800">
				Volumes
				{#if volumes.length > 0}
					<span class="text-sm font-normal text-gray-500">({volumes.length})</span>
				{/if}
			</h2>
			<div class="flex items-center gap-2">
				<button
					onclick={handleCompactAll}
					disabled={compactingAll || volumes.length <= 1}
					class="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
				>
					{compactingAll ? 'Compacting All...' : 'Compact All'}
				</button>
				<button
					onclick={refreshVolumes}
					disabled={loading}
					class="flex items-center gap-1 rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
				>
					<svg
						class="h-4 w-4 {loading ? 'animate-spin' : ''}"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
						/>
					</svg>
					Refresh
				</button>
			</div>
		</div>

		{#if loading && !volumes.length}
			<div class="mt-4 space-y-2">
				<!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
				{#each Array(3) as _, i (i)}
					<div class="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
						<div class="flex items-center justify-between">
							<div class="h-4 w-32 rounded bg-gray-200"></div>
							<div class="h-4 w-20 rounded bg-gray-200"></div>
						</div>
					</div>
				{/each}
			</div>
		{:else if !volumes.length}
			<div class="mt-4 rounded-lg border border-gray-200 bg-gray-50 px-6 py-12 text-center">
				<p class="text-gray-500">No volumes found on this storage node.</p>
			</div>
		{:else}
			<div class="mt-4 overflow-x-auto">
				<table class="w-full text-left text-sm">
					<thead>
						<tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
							<th class="px-3 py-2">Volume ID</th>
							<th class="px-3 py-2">Size</th>
							<th class="px-3 py-2 text-right">Actions</th>
						</tr>
					</thead>
					<tbody>
						{#each volumes as vol (vol.volume_id)}
							<tr class="border-b border-gray-100 hover:bg-gray-50">
								<td class="px-3 py-2 font-mono font-medium text-gray-900">
									{vol.volume_id}
								</td>
								<td class="px-3 py-2 text-gray-600">{formatSize(vol.size_bytes)}</td>
								<td class="px-3 py-2 text-right">
									<button
										onclick={() => handleCompact(vol.volume_id)}
										disabled={compactingId === vol.volume_id}
										class="rounded bg-amber-600 px-3 py-1 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
									>
										{compactingId === vol.volume_id ? 'Compacting...' : 'Compact'}
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	<section class="rounded-lg border border-gray-200 bg-white p-4">
		<h3 class="mb-3 text-sm font-semibold text-gray-700">Compact with Custom Gateway URL</h3>
		<div class="flex gap-2">
			<input
				type="text"
				bind:value={gatewayUrl}
				placeholder="http://localhost:8080 (optional override)"
				class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
			/>
			<p class="self-center text-xs text-gray-500">
				If set, this URL will override the default gateway URL during compaction.
			</p>
		</div>
	</section>
</div>
