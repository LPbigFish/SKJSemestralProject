export async function getServiceHealth(baseUrl: string): Promise<boolean> {
	try {
		const res = await fetch(baseUrl);
		return res.ok;
	} catch {
		return false;
	}
}
