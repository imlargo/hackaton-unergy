import api from '$lib/shared/api';

export interface DeviceCatalogEntry {
	label: string;
	watts: number;
	icon: string;
}

export interface Device {
	id: number;
	space_name: string;
	name: string;
	device_type: string;
	custom_watts: number | null;
	is_on: boolean;
	turned_on_at: number | null;
	total_kwh: number;
	created_at: number;
	watts: number;
	label: string;
	icon: string;
}

export interface DeviceEvent {
	device_id: number;
	device_name: string;
	space_name: string;
	device_type: string;
	action: 'on' | 'off';
	timestamp: number;
	watts: number;
	message: string;
	duration_seconds?: number;
	kwh_consumed?: number;
	co2_kg?: number;
}

export interface ConsumptionSummary {
	total_kwh: number;
	total_co2_kg: number;
	active_watts: number;
	active_devices: number;
	total_devices: number;
	co2_factor_kg_per_kwh: number;
	devices: Array<{
		id: number;
		name: string;
		space_name: string;
		device_type: string;
		label: string;
		is_on: boolean;
		watts: number;
		total_kwh: number;
		co2_kg: number;
	}>;
	by_space: Record<string, { kwh: number; co2_kg: number }>;
}

export class ConsumptionService {
	async getCatalog(): Promise<{ devices: Record<string, DeviceCatalogEntry> }> {
		return api.get('/consumption/catalog');
	}

	async registerDevice(payload: {
		space_name: string;
		name: string;
		device_type: string;
		custom_watts?: number;
	}): Promise<Device> {
		return api.post('/consumption/devices', payload);
	}

	async listDevices(spaceName?: string): Promise<{ devices: Device[] }> {
		const qs = spaceName ? `?space_name=${encodeURIComponent(spaceName)}` : '';
		return api.get(`/consumption/devices${qs}`);
	}

	async toggleDevice(deviceId: number, action: 'on' | 'off'): Promise<DeviceEvent> {
		return api.post('/consumption/event', { device_id: deviceId, action });
	}

	async getSummary(spaceName?: string): Promise<ConsumptionSummary> {
		const qs = spaceName ? `?space_name=${encodeURIComponent(spaceName)}` : '';
		return api.get(`/consumption/summary${qs}`);
	}

	async getEvents(spaceName?: string, limit = 50): Promise<{ events: DeviceEvent[] }> {
		let qs = `?limit=${limit}`;
		if (spaceName) qs += `&space_name=${encodeURIComponent(spaceName)}`;
		return api.get(`/consumption/events${qs}`);
	}

	async getActive(): Promise<{ active_count: number; total_watts: number; devices: Device[] }> {
		return api.get('/consumption/active');
	}
}

export const consumptionService = new ConsumptionService();
