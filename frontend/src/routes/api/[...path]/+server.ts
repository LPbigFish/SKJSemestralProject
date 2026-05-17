import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const BACKEND = env.API_URL ?? env.VITE_API_URL ?? 'http://localhost:8080';

export const GET: RequestHandler = async ({ url, request }) => {
	const target = `${BACKEND}${url.pathname.replace(/^\/api/, '')}${url.search}`;
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
	const target = `${BACKEND}${url.pathname.replace(/^\/api/, '')}${url.search}`;
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

export const PUT: RequestHandler = async ({ url, request }) => {
	const target = `${BACKEND}${url.pathname.replace(/^\/api/, '')}${url.search}`;
	const reqBody = await request.arrayBuffer();
	const res = await fetch(target, {
		method: 'PUT',
		headers: forwardHeaders(request),
		body: reqBody
	});
	const body = await res.arrayBuffer();
	return new Response(body, {
		status: res.status,
		headers: forwardResponseHeaders(res)
	});
};

export const DELETE: RequestHandler = async ({ url, request }) => {
	const target = `${BACKEND}${url.pathname.replace(/^\/api/, '')}${url.search}`;
	const res = await fetch(target, {
		method: 'DELETE',
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
	const safelist = ['content-type', 'x-user-id', 'x-internal-source'];
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
