import { BACKEND_BASE_URL } from '$lib/config/constants';
import { ApiClient } from './client';

const api = new ApiClient({
	baseUrl: BACKEND_BASE_URL
});

export default api;
