import { ApiClient } from '$lib/shared/api/client';
import { BACKEND_BASE_URL } from '$lib/config/constants';

export interface HubUser {
	device_id: string;
	display_name: string;
	location: string | null;
	confidence: number;
	space_type: string | null;
	last_seen: number;
}

export interface HubUsersResponse {
	users: HubUser[];
}

/**
 * Hub service with configurable server URL.
 *
 * For cross-machine POC: each device tracks via its own local-server
 * but all devices send/read hub data from the same "hub server".
 * One machine acts as the hub — the other connects to its IP.
 */
export class HubService {
	private client: ApiClient;
	private _hubUrl: string;

	constructor() {
		this._hubUrl = this.loadHubUrl();
		this.client = new ApiClient({ baseUrl: this._hubUrl });
	}

	get hubUrl(): string {
		return this._hubUrl;
	}

	/** Change hub server URL at runtime (persisted in localStorage). */
	setHubUrl(url: string) {
		const cleaned = url.replace(/\/+$/, '');
		this._hubUrl = cleaned;
		this.client = new ApiClient({ baseUrl: cleaned });
		if (typeof window !== 'undefined') {
			localStorage.setItem('unergy_hub_url', cleaned);
		}
	}

	private loadHubUrl(): string {
		if (typeof window !== 'undefined') {
			return localStorage.getItem('unergy_hub_url') || BACKEND_BASE_URL;
		}
		return BACKEND_BASE_URL;
	}

	async heartbeat(payload: {
		device_id: string;
		display_name: string;
		location: string | null;
		confidence: number;
		space_type: string | null;
	}): Promise<{ status: string }> {
		return this.client.post('/hub/heartbeat', payload);
	}

	async getUsers(): Promise<HubUsersResponse> {
		return this.client.get<HubUsersResponse>('/hub/users');
	}

	async leave(deviceId: string): Promise<{ status: string }> {
		return this.client.delete(`/hub/leave?device_id=${encodeURIComponent(deviceId)}`);
	}
}

export const hubService = new HubService();
