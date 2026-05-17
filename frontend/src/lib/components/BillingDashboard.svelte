<script lang="ts">
	import { getBucketBilling } from '$lib/api';
	import type { BillingResponse } from '$lib/types';

	let {
		bucketId
	}: {
		bucketId: number;
	} = $props();

	let billing = $state.raw<BillingResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	function formatBytes(bytes: number): string {
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		const value = bytes / Math.pow(1024, i);
		return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	async function refresh() {
		loading = true;
		error = null;
		try {
			billing = await getBucketBilling(bucketId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load billing';
			billing = null;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (bucketId > 0) refresh();
	});

	let ingressPercent = $derived(
		billing ? Math.round((billing.ingress_bytes / billing.bandwidth_bytes) * 100) || 0 : 0
	);
	let egressPercent = $derived(
		billing ? Math.round((billing.egress_bytes / billing.bandwidth_bytes) * 100) || 0 : 0
	);
	let internalPercent = $derived(
		billing ? Math.round((billing.internal_transfer_bytes / billing.bandwidth_bytes) * 100) || 0 : 0
	);
</script>

<div class="space-y-4">
	<div class="flex items-center justify-between">
		<h2 class="text-lg font-semibold text-gray-800">Billing Dashboard</h2>
		<button
			onclick={refresh}
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

	{#if error}
		<div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
			{error}
		</div>
	{/if}

	{#if loading && !billing}
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
			<div class="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
				<div class="mb-2 h-3 w-20 rounded bg-gray-200"></div>
				<div class="h-6 w-24 rounded bg-gray-200"></div>
			</div>
			<div class="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
				<div class="mb-2 h-3 w-20 rounded bg-gray-200"></div>
				<div class="h-6 w-24 rounded bg-gray-200"></div>
			</div>
			<div class="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
				<div class="mb-2 h-3 w-20 rounded bg-gray-200"></div>
				<div class="h-6 w-24 rounded bg-gray-200"></div>
			</div>
			<div class="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
				<div class="mb-2 h-3 w-20 rounded bg-gray-200"></div>
				<div class="h-6 w-24 rounded bg-gray-200"></div>
			</div>
		</div>
	{:else if billing}
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
			<div class="rounded-lg border border-blue-200 bg-blue-50 p-4">
				<div class="mb-1 flex items-center gap-2 text-xs font-medium text-blue-600 uppercase">
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
						/>
					</svg>
					Storage
				</div>
				<p class="text-xl font-bold text-blue-900">{formatBytes(billing.current_storage_bytes)}</p>
				<p class="mt-1 text-xs text-blue-500">
					{formatNumber(billing.current_storage_bytes)} bytes
				</p>
			</div>

			<div class="rounded-lg border border-green-200 bg-green-50 p-4">
				<div class="mb-1 flex items-center gap-2 text-xs font-medium text-green-600 uppercase">
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
						/>
					</svg>
					Ingress
				</div>
				<p class="text-xl font-bold text-green-900">{formatBytes(billing.ingress_bytes)}</p>
				<p class="mt-1 text-xs text-green-500">{formatNumber(billing.ingress_bytes)} bytes</p>
			</div>

			<div class="rounded-lg border border-orange-200 bg-orange-50 p-4">
				<div class="mb-1 flex items-center gap-2 text-xs font-medium text-orange-600 uppercase">
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
						/>
					</svg>
					Egress
				</div>
				<p class="text-xl font-bold text-orange-900">{formatBytes(billing.egress_bytes)}</p>
				<p class="mt-1 text-xs text-orange-500">{formatNumber(billing.egress_bytes)} bytes</p>
			</div>

			<div class="rounded-lg border border-purple-200 bg-purple-50 p-4">
				<div class="mb-1 flex items-center gap-2 text-xs font-medium text-purple-600 uppercase">
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
						/>
					</svg>
					Bandwidth
				</div>
				<p class="text-xl font-bold text-purple-900">{formatBytes(billing.bandwidth_bytes)}</p>
				<p class="mt-1 text-xs text-purple-500">
					{formatNumber(billing.bandwidth_bytes)} bytes total
				</p>
			</div>
		</div>

		<div class="rounded-lg border border-gray-200 bg-white p-4">
			<h3 class="mb-3 text-sm font-semibold text-gray-700">Transfer Breakdown</h3>

			<div class="space-y-3">
				<div>
					<div class="mb-1 flex items-center justify-between text-sm">
						<span class="text-gray-600">Ingress</span>
						<span class="font-medium text-green-700">{formatBytes(billing.ingress_bytes)}</span>
					</div>
					<div class="h-2 w-full rounded-full bg-gray-100">
						<div
							class="h-2 rounded-full bg-green-500 transition-all"
							style="width: {ingressPercent}%"
						></div>
					</div>
				</div>

				<div>
					<div class="mb-1 flex items-center justify-between text-sm">
						<span class="text-gray-600">Egress</span>
						<span class="font-medium text-orange-700">{formatBytes(billing.egress_bytes)}</span>
					</div>
					<div class="h-2 w-full rounded-full bg-gray-100">
						<div
							class="h-2 rounded-full bg-orange-500 transition-all"
							style="width: {egressPercent}%"
						></div>
					</div>
				</div>

				<div>
					<div class="mb-1 flex items-center justify-between text-sm">
						<span class="text-gray-600">Internal Transfer</span>
						<span class="font-medium text-gray-700"
							>{formatBytes(billing.internal_transfer_bytes)}</span
						>
					</div>
					<div class="h-2 w-full rounded-full bg-gray-100">
						<div
							class="h-2 rounded-full bg-gray-500 transition-all"
							style="width: {internalPercent}%"
						></div>
					</div>
				</div>
			</div>

			{#if billing.internal_transfer_bytes > 0}
				<div class="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
					Internal transfers: {formatBytes(billing.internal_transfer_bytes)}
				</div>
			{/if}
		</div>

		<div class="rounded-lg border border-gray-200 bg-white p-4">
			<h3 class="mb-2 text-sm font-semibold text-gray-700">Bucket Info</h3>
			<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
				<dt class="text-gray-500">Bucket ID</dt>
				<dd class="font-medium text-gray-900">{billing.bucket_id}</dd>
				<dt class="text-gray-500">Bucket Name</dt>
				<dd class="font-medium text-gray-900">{billing.bucket_name}</dd>
			</dl>
		</div>
	{/if}
</div>
