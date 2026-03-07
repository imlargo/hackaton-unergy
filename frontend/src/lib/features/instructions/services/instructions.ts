import api from '$lib/shared/api';

export interface WifiStatus {
	wifi_available: boolean;
	source: string;
	networks_detected: number;
}

export interface RegisterSpaceInstructions {
	title: string;
	description: string;
	steps: string[];
}

export class InstructionsService {
	async getWifiStatus(): Promise<WifiStatus> {
		return api.get<WifiStatus>('/instructions/wifi-status');
	}

	async getRegisterSpaceInstructions(): Promise<RegisterSpaceInstructions> {
		return api.get<RegisterSpaceInstructions>('/instructions/register-space');
	}
}

export const instructionsService = new InstructionsService();
