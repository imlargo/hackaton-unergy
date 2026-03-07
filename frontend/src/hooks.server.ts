import type { Handle } from '@sveltejs/kit';

/** No authentication required — all routes are public. */
export const handle: Handle = async ({ event, resolve }) => {
	return resolve(event);
};
