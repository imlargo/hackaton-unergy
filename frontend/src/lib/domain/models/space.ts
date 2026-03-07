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

export interface Space {
	id: number;
	user_id: number;
	name: string;
	space_type: string;
	wifi_metadata: WifiMetadata;
	created_at: string;
}

export interface SpaceCreate {
	name: string;
	space_type: string;
}
