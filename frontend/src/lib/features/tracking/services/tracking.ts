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

export interface CollectionStatus {
	space_name: string;
	status: 'collecting' | 'done' | 'error' | 'unknown';
	samples_requested?: number;
	fingerprints_saved?: number;
	model_trained?: boolean;
	model_accuracy?: number | null;
	error?: string;
}

export interface WifiPosDiagnostics {
	wifipos_available: boolean;
	database_initialized: boolean;
	scanner_initialized: boolean;
	fingerprint_counts?: Record<string, number>;
	model_available?: boolean;
	dependencies?: Record<string, boolean>;
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

	async collectionStatus(spaceName: string): Promise<CollectionStatus> {
		return api.get<CollectionStatus>(`/spaces/collection-status/${encodeURIComponent(spaceName)}`);
	}

	async diagnostics(): Promise<WifiPosDiagnostics> {
		return api.get<WifiPosDiagnostics>('/health/wifipos');
	}
}

export const trackingService = new TrackingService();
