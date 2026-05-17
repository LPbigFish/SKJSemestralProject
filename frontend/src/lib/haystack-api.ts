import type { VolumeListResponse } from './types';

export async function getHealth(): Promise<boolean> {
	const res = await fetch('/haystack/api/health');
	return res.ok;
}

export async function listVolumes(): Promise<VolumeListResponse> {
	const res = await fetch('/haystack/api/volumes');
	if (!res.ok) throw new Error(`Failed to list volumes: ${res.status}`);
	return res.json();
}

export async function compactVolume(volumeId: number, gatewayUrl?: string): Promise<unknown> {
	const params = gatewayUrl ? `?gateway_url=${encodeURIComponent(gatewayUrl)}` : '';
	const res = await fetch(`/haystack/api/compact/${volumeId}${params}`, {
		method: 'POST'
	});
	if (!res.ok) throw new Error(`Failed to compact volume: ${res.status}`);
	return res.json();
}
