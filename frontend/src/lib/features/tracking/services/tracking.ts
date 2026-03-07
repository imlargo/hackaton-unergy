import api from '$lib/shared/api';

export interface LocationPrediction {
	location: string;
	confidence: number;
	probabilities?: Record<string, number>;
	note?: string;
	timestamp?: string;
}

export interface TrackingStatus {
	active: boolean;
	latest_prediction: LocationPrediction | null;
}

export interface TrackingStartResponse {
	status: 'started' | 'already_running';
	interval: number;
}

export interface TrackingStopResponse {
	status: 'stopped' | 'not_running';
}

export class TrackingService {
	async start(interval: number = 3.0): Promise<TrackingStartResponse> {
		return api.post<TrackingStartResponse>(`/tracking/start?interval=${interval}`);
	}

	async stop(): Promise<TrackingStopResponse> {
		return api.post<TrackingStopResponse>('/tracking/stop');
	}

	async status(): Promise<TrackingStatus> {
		return api.get<TrackingStatus>('/tracking/status');
	}

	async predictOnce(): Promise<LocationPrediction> {
		return api.get<LocationPrediction>('/tracking/predict');
	}
}

export const trackingService = new TrackingService();
