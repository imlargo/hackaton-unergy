export interface WifiMetadata {
	networks_detected: number;
	readings: {
		bssid: string;
		ssid: string;
		rssi: number;
		channel: number;
	}[];
	source: string;
}

export interface RegistrationFeedback {
	fingerprints_saved: number;
	samples_requested: number;
	wifi_source: string;
	networks_detected: number;
	collection_status: string;
	model_trained: boolean;
	model_note?: string;
	model_accuracy?: number;
}

export interface Space {
	id: number;
	user_id: number;
	name: string;
	space_type: string;
	wifi_metadata: WifiMetadata;
	created_at: string;
	registration_feedback?: RegistrationFeedback | null;
}

export interface SpaceCreate {
	name: string;
	space_type: string;
	samples?: number;
}
