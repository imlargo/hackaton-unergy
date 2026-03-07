<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { Wifi, Plus, MapPin, Radio, Home, Building, ChefHat, Warehouse, LayoutDashboard } from '@lucide/svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import { spaceService } from '$lib/features/spaces/services/space';
	import { instructionsService, type WifiStatus } from '$lib/features/instructions/services/instructions';
	import type { Space, SpaceCreate } from '$lib/domain/models/space';

	let spaces: Space[] = $state([]);
	let wifiStatus: WifiStatus | null = $state(null);
	let loading = $state(true);
	let creating = $state(false);
	let dialogOpen = $state(false);

	// Form state
	let newName = $state('');
	let newType = $state('room');

	const spaceTypes = [
		{ value: 'room', label: 'Habitación', icon: Home },
		{ value: 'kitchen', label: 'Cocina', icon: ChefHat },
		{ value: 'office', label: 'Oficina', icon: Building },
		{ value: 'living_room', label: 'Sala', icon: Home },
		{ value: 'garage', label: 'Garaje', icon: Warehouse },
	];

	function getSpaceIcon(type: string) {
		return spaceTypes.find(t => t.value === type)?.icon ?? MapPin;
	}

	function getSpaceLabel(type: string) {
		return spaceTypes.find(t => t.value === type)?.label ?? type;
	}

	async function loadData() {
		loading = true;
		try {
			const [spacesData, wifi] = await Promise.all([
				spaceService.list(),
				instructionsService.getWifiStatus()
			]);
			spaces = spacesData;
			wifiStatus = wifi;
		} catch (err) {
			console.error('Error loading data:', err);
			toast.error('Error al cargar datos del servidor');
		} finally {
			loading = false;
		}
	}

	async function createSpace() {
		if (!newName.trim()) {
			toast.error('El nombre del espacio es requerido');
			return;
		}
		creating = true;
		try {
			const space = await spaceService.create({ name: newName.trim(), space_type: newType });
			spaces = [...spaces, space];
			toast.success(`Espacio "${space.name}" registrado exitosamente`);
			newName = '';
			newType = 'room';
			dialogOpen = false;
		} catch (err) {
			console.error('Error creating space:', err);
			toast.error('Error al registrar el espacio');
		} finally {
			creating = false;
		}
	}

	onMount(() => {
		loadData();
	});
</script>

<div class="mx-auto w-full max-w-5xl space-y-8">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold tracking-tight">Unergy</h1>
			<p class="text-muted-foreground">Plataforma de contexto energético y posicionamiento espacial</p>
		</div>
		<Dialog.Root bind:open={dialogOpen}>
			<Dialog.Trigger>
				{#snippet child({ props })}
					<Button {...props}>
						<Plus class="mr-2 size-4" />
						Registrar espacio
					</Button>
				{/snippet}
			</Dialog.Trigger>
			<Dialog.Content>
				<Dialog.Header>
					<Dialog.Title>Registrar nuevo espacio</Dialog.Title>
					<Dialog.Description>
						Registra un nuevo espacio usando el entorno WiFi actual para posicionamiento.
					</Dialog.Description>
				</Dialog.Header>
				<div class="grid gap-4 py-4">
					<div class="grid gap-2">
						<Label for="space-name">Nombre del espacio</Label>
						<Input
							id="space-name"
							placeholder="Ej: Cocina principal"
							bind:value={newName}
						/>
					</div>
					<div class="grid gap-2">
						<Label>Tipo de espacio</Label>
						<Select.Root bind:value={newType}>
							<Select.Trigger>
								{getSpaceLabel(newType)}
							</Select.Trigger>
							<Select.Content>
								{#each spaceTypes as st}
									<Select.Item value={st.value}>{st.label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
				</div>
				<Dialog.Footer>
					<Dialog.Close>
						{#snippet child({ props })}
							<Button variant="outline" {...props}>Cancelar</Button>
						{/snippet}
					</Dialog.Close>
					<Button onclick={createSpace} disabled={creating}>
						{#if creating}
							Registrando...
						{:else}
							Registrar
						{/if}
					</Button>
				</Dialog.Footer>
			</Dialog.Content>
		</Dialog.Root>
	</div>

	<Separator />

	<!-- WiFi Status -->
	<div class="grid gap-4 sm:grid-cols-3">
		<Card.Root>
			<Card.Header>
				<div class="flex items-center gap-2">
					<Wifi class="size-4 text-muted-foreground" />
					<Card.Title class="text-sm font-medium">Estado WiFi</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				{#if wifiStatus}
					<Badge variant={wifiStatus.wifi_available ? 'default' : 'outline'}>
						{wifiStatus.wifi_available ? 'Disponible' : 'No disponible'}
					</Badge>
				{:else if loading}
					<span class="text-sm text-muted-foreground">Cargando...</span>
				{:else}
					<Badge variant="outline">Sin conexión</Badge>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<div class="flex items-center gap-2">
					<Radio class="size-4 text-muted-foreground" />
					<Card.Title class="text-sm font-medium">Redes detectadas</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				<p class="text-2xl font-bold">
					{wifiStatus?.networks_detected ?? '—'}
				</p>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<div class="flex items-center gap-2">
					<MapPin class="size-4 text-muted-foreground" />
					<Card.Title class="text-sm font-medium">Espacios registrados</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				<p class="text-2xl font-bold">
					{spaces.length}
				</p>
			</Card.Content>
		</Card.Root>
	</div>

	<!-- Spaces List -->
	<div>
		<div class="mb-4 flex items-center gap-2">
			<LayoutDashboard class="size-5" />
			<h2 class="text-xl font-semibold">Espacios</h2>
		</div>

		{#if loading}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each [1, 2, 3] as _}
					<Card.Root>
						<Card.Header>
							<div class="h-5 w-32 animate-pulse rounded bg-muted"></div>
							<div class="h-4 w-20 animate-pulse rounded bg-muted"></div>
						</Card.Header>
						<Card.Content>
							<div class="h-4 w-full animate-pulse rounded bg-muted"></div>
						</Card.Content>
					</Card.Root>
				{/each}
			</div>
		{:else if spaces.length === 0}
			<Card.Root>
				<Card.Content class="flex flex-col items-center justify-center py-12">
					<MapPin class="mb-4 size-12 text-muted-foreground" />
					<p class="text-lg font-medium">No hay espacios registrados</p>
					<p class="mb-4 text-sm text-muted-foreground">
						Registra tu primer espacio para comenzar el posicionamiento WiFi
					</p>
					<Button onclick={() => (dialogOpen = true)}>
						<Plus class="mr-2 size-4" />
						Registrar espacio
					</Button>
				</Card.Content>
			</Card.Root>
		{:else}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each spaces as space}
					{@const Icon = getSpaceIcon(space.space_type)}
					<Card.Root>
						<Card.Header>
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-2">
									<Icon class="size-5 text-muted-foreground" />
									<Card.Title>{space.name}</Card.Title>
								</div>
								<Badge variant="secondary">{getSpaceLabel(space.space_type)}</Badge>
							</div>
						</Card.Header>
						<Card.Content>
							<div class="space-y-2 text-sm text-muted-foreground">
								<div class="flex items-center gap-2">
									<Wifi class="size-3.5" />
									<span>{space.wifi_metadata.networks_detected} redes detectadas</span>
								</div>
								<div class="flex items-center gap-2">
									<Radio class="size-3.5" />
									<span>Fuente: {space.wifi_metadata.source}</span>
								</div>
								<p class="text-xs">
									Registrado: {new Date(space.created_at).toLocaleDateString('es-CO', { dateStyle: 'medium' })}
								</p>
							</div>
						</Card.Content>
					</Card.Root>
				{/each}
			</div>
		{/if}
	</div>
</div>
