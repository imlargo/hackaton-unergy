import api from '$lib/shared/api';
import type { Space, SpaceCreate } from '$lib/domain/models/space';

export class SpaceService {
	async list(): Promise<Space[]> {
		return api.get<Space[]>('/spaces');
	}

	async get(id: number): Promise<Space> {
		return api.get<Space>(`/spaces/${id}`);
	}

	async create(data: SpaceCreate): Promise<Space> {
		return api.post<Space, SpaceCreate>('/spaces', data);
	}
}

export const spaceService = new SpaceService();
