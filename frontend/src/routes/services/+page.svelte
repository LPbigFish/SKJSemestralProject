<script lang="ts">
	import { onMount } from 'svelte';

	interface ServiceStatus {
		name: string;
		port: number;
		proxyPath: string;
		healthy: boolean | null;
		info: Record<string, unknown> | null;
	}

	let services = $state.raw<ServiceStatus[]>([
		{ name: 'S3 Gateway', port: 8080, proxyPath: '/api', healthy: null, info: null },
		{
			name: 'Haystack Node',
			port: 8081,
			proxyPath: '/haystack/api',
			healthy: null,
			info: null
		},
		{
			name: 'Message Broker',
			port: 8082,
			proxyPath: '/services/broker/api',
			healthy: null,
			info: null
		},
		{
			name: 'Worker',
			port: 8083,
			proxyPath: '/services/worker/api',
			healthy: null,
			info: null
		}
	]);

	let loading = $state(false);
	let pollingInterval: ReturnType<typeof setInterval> | null = null;

	async function checkServices() {
		loading = true;
		const updated = [...services];
		for (let i = 0; i < updated.length; i++) {
			try {
				const res = await fetch(`${updated[i].proxyPath}/health`);
				updated[i] = {
					...updated[i],
					healthy: res.ok,
					info: res.ok ? await res.json() : null
				};
			} catch {
				updated[i] = { ...updated[i], healthy: false, info: null };
			}
		}
		services = updated;
		loading = false;
	}

	onMount(() => {
		checkServices();
		pollingInterval = setInterval(checkServices, 15000);
		return () => {
			if (pollingInterval) clearInterval(pollingInterval);
		};
	});

	let healthyCount = $derived(services.filter((s) => s.healthy === true).length);
	let totalCount = $derived(services.length);
</script>

<svelte:head>
	<title>Services Status</title>
</svelte:head>

<div class="mx-auto max-w-6xl p-6">
	<div class="mb-6 flex items-center justify-between">
		<div class="flex items-center gap-3">
			<h1 class="text-2xl font-bold text-gray-900">Services Status</h1>
			<span class="text-sm text-gray-500">
				{healthyCount}/{totalCount} healthy
			</span>
		</div>
		<button
			onclick={checkServices}
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

	<p class="mb-6 text-sm text-gray-500">
		Auto-refreshes every 15 seconds. All services are checked via their <code>/health</code> endpoint.
	</p>

	<div class="grid gap-4 sm:grid-cols-2">
		{#each services as svc (svc.name)}
			<div
				class="rounded-lg border {svc.healthy === true
					? 'border-green-200 bg-green-50'
					: svc.healthy === false
						? 'border-red-200 bg-red-50'
						: 'border-gray-200 bg-gray-50'} p-4"
			>
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						{#if svc.healthy === true}
							<span class="h-2.5 w-2.5 rounded-full bg-green-500"></span>
						{:else if svc.healthy === false}
							<span class="h-2.5 w-2.5 rounded-full bg-red-500"></span>
						{:else}
							<span class="h-2.5 w-2.5 rounded-full bg-gray-400"></span>
						{/if}
						<h2 class="font-semibold text-gray-900">{svc.name}</h2>
					</div>
					<span class="font-mono text-xs text-gray-500">:{svc.port}</span>
				</div>

				<div class="mt-2">
					{#if svc.healthy === true}
						<span
							class="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800"
						>
							Healthy
						</span>
					{:else if svc.healthy === false}
						<span
							class="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800"
						>
							Unreachable
						</span>
					{:else}
						<span
							class="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600"
						>
							Checking...
						</span>
					{/if}
				</div>

				{#if svc.info}
					<div class="mt-3 rounded bg-white/60 px-3 py-2">
						<pre class="overflow-x-auto text-xs text-gray-600">{JSON.stringify(
								svc.info,
								null,
								2
							)}</pre>
					</div>
				{/if}
			</div>
		{/each}
	</div>
</div>
