<script lang="ts">
	import { getOperations, processObject } from '$lib/api';
	import type { OperationInfo, OperationParam } from '$lib/types';

	let {
		bucketId,
		fileId,
		userId,
		onProcessed
	}: {
		bucketId: number;
		fileId: string;
		userId: string;
		onProcessed: () => void;
	} = $props();

	let open = $state(false);
	let operations = $state.raw<OperationInfo[]>([]);
	let selectedOp = $state('');
	let paramValues = $state<Record<string, string>>({});
	let loading = $state(false);
	let error = $state<string | null>(null);

	let selectedOpDetails: OperationInfo | null = $derived(
		operations.find((o) => o.operation === selectedOp) ?? null
	);

	async function openDialog() {
		open = true;
		error = null;
		selectedOp = '';
		paramValues = {};
		try {
			operations = await getOperations();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load operations';
		}
	}

	function coerceParam(param: OperationParam, value: string): unknown {
		if (param.type === 'integer' || param.type === 'number') {
			return Number(value);
		}
		if (param.type === 'boolean') {
			return value === 'true';
		}
		return value;
	}

	async function submit() {
		if (!selectedOpDetails) return;
		loading = true;
		error = null;
		try {
			const params: Record<string, unknown> = {};
			for (const p of selectedOpDetails.params) {
				if (paramValues[p.name] !== undefined && paramValues[p.name] !== '') {
					params[p.name] = coerceParam(p, paramValues[p.name]);
				}
			}
			await processObject(bucketId, fileId, { operation: selectedOp, params }, userId || undefined);
			open = false;
			onProcessed();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Processing failed';
		} finally {
			loading = false;
		}
	}
</script>

<button
	onclick={openDialog}
	class="rounded px-2 py-1 text-sm text-purple-700 hover:bg-purple-100"
	title="Process file"
>
	<svg class="inline h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			stroke-width="2"
			d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
		/>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			stroke-width="2"
			d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
		/>
	</svg>
	Process
</button>

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog">
		<div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
			<h2 class="mb-4 text-lg font-semibold">Process File</h2>

			{#if error}
				<p class="mb-3 text-sm text-red-600">{error}</p>
			{/if}

			<div class="mb-4">
				<label for="operation-select" class="mb-1 block text-sm font-medium text-gray-700"
					>Operation</label
				>
				<select
					id="operation-select"
					class="w-full rounded border border-gray-300 px-3 py-2 text-sm"
					bind:value={selectedOp}
				>
					<option value="">Select an operation...</option>
					{#each operations as op (op.operation)}
						<option value={op.operation}>{op.operation}</option>
					{/each}
				</select>
			</div>

			{#if selectedOpDetails?.params.length}
				<div class="mb-4 space-y-3">
					{#each selectedOpDetails.params as param (param.name)}
						<div>
							<label for="param-{param.name}" class="mb-1 block text-sm font-medium text-gray-700">
								{param.name}
								{#if param.required}<span class="text-red-500">*</span>{/if}
								{#if param.default !== undefined && param.default !== null}
									<span class="text-gray-400">(default: {param.default})</span>
								{/if}
							</label>
							<input
								id="param-{param.name}"
								type={param.type === 'integer' || param.type === 'number' ? 'number' : 'text'}
								class="w-full rounded border border-gray-300 px-3 py-2 text-sm"
								bind:value={paramValues[param.name]}
								placeholder={param.type}
							/>
						</div>
					{/each}
				</div>
			{/if}

			<div class="flex justify-end gap-2">
				<button
					onclick={() => (open = false)}
					class="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={submit}
					disabled={!selectedOp || loading}
					class="rounded bg-purple-600 px-4 py-2 text-sm text-white hover:bg-purple-700 disabled:opacity-50"
				>
					{loading ? 'Processing...' : 'Process'}
				</button>
			</div>
		</div>
	</div>
{/if}
