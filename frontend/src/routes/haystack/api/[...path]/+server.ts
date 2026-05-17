import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const HAYSTACK_NODE = env.HAYSTACK_NODE_URL ?? 'http://localhost:8081';

export const GET: RequestHandler = async ({ url, request }) => {
	const target = `${HAYSTACK_NODE}${url.pathname.replace(/^\/haystack\/api/, '')}${url.search}`;
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

export const POST: RequestHandler = async ({ url, request }) => {
	const target = `${HAYSTACK_NODE}${url.pathname.replace(/^\/haystack\/api/, '')}${url.search}`;
	const reqBody = await request.arrayBuffer();
	const res = await fetch(target, {
		method: 'POST',
		headers: forwardHeaders(request),
		body: reqBody
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
