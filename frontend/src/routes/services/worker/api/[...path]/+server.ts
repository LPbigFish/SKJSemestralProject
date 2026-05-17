import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const WORKER_URL = env.WORKER_URL ?? 'http://localhost:8083';

export const GET: RequestHandler = async ({ url, request }) => {
	const target = `${WORKER_URL}${url.pathname.replace(/^\/services\/worker\/api/, '')}${url.search}`;
	const res = await fetch(target, {
		method: 'GET',
		headers: forwardHeaders(request)
	});
	const body = await res.arrayBuffer();
	return new Response(body, {
		status: res.status,
		headers: forwardResponseHeaders(res)
	});
};

function forwardHeaders(req: Request): HeadersInit {
	const h = new Headers();
	const safelist = ['content-type'];
	for (const key of safelist) {
		const val = req.headers.get(key);
		if (val) h.set(key, val);
	}
	return h;
}

function forwardResponseHeaders(res: Response): HeadersInit {
	const h = new Headers();
	const contentType = res.headers.get('content-type');
	if (contentType) h.set('content-type', contentType);
	return h;
}
