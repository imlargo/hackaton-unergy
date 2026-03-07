<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		Wifi, Plus, MapPin, Radio, Home, Building, ChefHat, Warehouse,
		LayoutDashboard, Navigation, Power, PowerOff, Activity, Target, Clock,
		BarChart3, Eye, Zap,
	} from '@lucide/svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import { spaceService } from '$lib/features/spaces/services/space';
	import { instructionsService, type WifiStatus } from '$lib/features/instructions/services/instructions';
	import { trackingService, type LocationPrediction, type TrackingStatus } from '$lib/features/tracking/services/tracking';
	import type { Space, SpaceCreate } from '$lib/domain/models/space';

	let spaces: Space[] = $state([]);
	let wifiStatus: WifiStatus | null = $state(null);
	let loading = $state(true);
	let creating = $state(false);
	let dialogOpen = $state(false);

	// Tracking state
	let trackingActive = $state(false);
	let trackingStarting = $state(false);
	let trackingStopping = $state(false);
	let currentLocation: LocationPrediction | null = $state(null);
	let locationHistory: LocationPrediction[] = $state([]);
	let pollInterval: ReturnType<typeof setInterval> | null = $state(null);
	let trackingInterval = $state(3);
	let lastUpdated: string | null = $state(null);
	let predictionCount = $state(0);

	// Form state
	let newName = $state('');
	let newType = $state('room');
	let newSamples = $state(5);

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

	function getConfidenceColor(confidence: number): string {
		if (confidence >= 0.8) return 'text-green-500';
		if (confidence >= 0.5) return 'text-yellow-500';
		return 'text-red-400';
	}

	function getConfidenceBadgeVariant(confidence: number): 'default' | 'secondary' | 'outline' {
		if (confidence >= 0.8) return 'default';
		if (confidence >= 0.5) return 'secondary';
		return 'outline';
	}

	function formatConfidence(confidence: number): string {
		return `${Math.round(confidence * 100)}%`;
	}

	function formatTime(isoString: string): string {
		return new Date(isoString).toLocaleTimeString('es-CO', {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
		});
	}

	async function loadData() {
		loading = true;
		try {
			const [spacesData, wifi, trackingStatus] = await Promise.all([
				spaceService.list(),
				instructionsService.getWifiStatus(),
				trackingService.status(),
			]);
			spaces = spacesData;
			wifiStatus = wifi;

			// Sync tracking state from backend
			if (trackingStatus.active) {
				trackingActive = true;
				if (trackingStatus.latest_prediction) {
					currentLocation = trackingStatus.latest_prediction;
				}
				startPolling();
			}
		} catch (err) {
			console.error('Error loading data:', err);
			toast.error('Error al cargar datos del servidor');
		} finally {
			loading = false;
		}
	}

	async function startTracking() {
		trackingStarting = true;
		try {
			const res = await trackingService.start(trackingInterval);
			trackingActive = true;
			predictionCount = 0;
			locationHistory = [];
			startPolling();
			if (res.status === 'already_running') {
				toast.info('El tracking ya estaba activo');
			} else {
				toast.success('📍 Tracking iniciado — monitoreando tu ubicación');
			}
		} catch (err) {
			console.error('Error starting tracking:', err);
			toast.error('No se pudo iniciar el tracking');
		} finally {
			trackingStarting = false;
		}
	}

	async function stopTracking() {
		trackingStopping = true;
		try {
			await trackingService.stop();
			trackingActive = false;
			stopPolling();
			toast.success('Tracking detenido');
		} catch (err) {
			console.error('Error stopping tracking:', err);
			toast.error('No se pudo detener el tracking');
		} finally {
			trackingStopping = false;
		}
	}

	async function singlePredict() {
		try {
			const prediction = await trackingService.predictOnce();
			currentLocation = prediction;
			lastUpdated = new Date().toISOString();
			predictionCount++;
			addToHistory(prediction);
		} catch (err) {
			console.error('Error predicting location:', err);
			toast.error('Error al predecir ubicación');
		}
	}

	async function pollTrackingStatus() {
		try {
			const status = await trackingService.status();
			if (!status.active) {
				trackingActive = false;
				stopPolling();
				return;
			}
			if (status.latest_prediction) {
				const newPrediction = status.latest_prediction;
				const isNew = !currentLocation ||
					newPrediction.timestamp !== currentLocation.timestamp;
				if (isNew) {
					currentLocation = newPrediction;
					lastUpdated = newPrediction.timestamp ?? new Date().toISOString();
					predictionCount++;
					addToHistory(newPrediction);
				}
			}
		} catch (err) {
			console.error('Error polling tracking status:', err);
		}
	}

	function addToHistory(prediction: LocationPrediction) {
		locationHistory = [
			{ ...prediction, timestamp: prediction.timestamp ?? new Date().toISOString() },
			...locationHistory,
		].slice(0, 20);
	}

	function startPolling() {
		stopPolling();
		pollInterval = setInterval(pollTrackingStatus, 2000);
	}

	function stopPolling() {
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}

	async function createSpace() {
		if (!newName.trim()) {
			toast.error('El nombre del espacio es requerido');
			return;
		}
		creating = true;
		try {
			const space = await spaceService.create({
				name: newName.trim(),
				space_type: newType,
				samples: newSamples,
			});
			spaces = [...spaces, space];
			const feedback = space.registration_feedback;
			if (feedback) {
				toast.success(
					`Espacio "${space.name}" registrado ✔ ` +
					`Recolectando ${feedback.samples_requested} muestras WiFi en segundo plano…`
				);
			} else {
				toast.success(`Espacio "${space.name}" registrado exitosamente`);
			}
			newName = '';
			newType = 'room';
			newSamples = 5;
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

	onDestroy(() => {
		stopPolling();
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
						Las muestras se recolectan en segundo plano — camina por el espacio para mejor precisión.
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
					<div class="grid gap-2">
						<Label for="samples">Muestras WiFi ({newSamples})</Label>
						<Input
							id="samples"
							type="range"
							min="1"
							max="30"
							bind:value={newSamples}
						/>
						<p class="text-xs text-muted-foreground">
							{newSamples} muestras · Se recolectan en segundo plano
						</p>
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

	<!-- ========================== -->
	<!-- LIVE TRACKING SECTION      -->
	<!-- ========================== -->
	<div class="space-y-4">
		<div class="flex items-center gap-2">
			<Navigation class="size-5" />
			<h2 class="text-xl font-semibold">Ubicación en vivo</h2>
			{#if trackingActive}
				<span class="relative ml-2 flex size-3">
					<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"></span>
					<span class="relative inline-flex size-3 rounded-full bg-green-500"></span>
				</span>
			{/if}
		</div>

		<!-- Main Tracking Card -->
		<Card.Root class={trackingActive ? 'border-green-500/30 shadow-lg shadow-green-500/5' : ''}>
			<Card.Content class="p-6">
				<div class="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
					<!-- Current Location Display -->
					<div class="flex-1 space-y-4">
						<!-- Location Badge / Hero -->
						<div class="flex items-center gap-4">
							<div class={`flex size-16 items-center justify-center rounded-2xl ${trackingActive ? 'bg-green-500/10' : 'bg-muted'}`}>
								{#if currentLocation && currentLocation.location !== 'unknown'}
									{@const LocIcon = getSpaceIcon(
										spaces.find(s => s.name === currentLocation?.location)?.space_type ?? ''
									)}
									<LocIcon class={`size-8 ${trackingActive ? 'text-green-500' : 'text-muted-foreground'}`} />
								{:else}
									<Target class={`size-8 ${trackingActive ? 'text-green-500 animate-pulse' : 'text-muted-foreground'}`} />
								{/if}
							</div>
							<div>
								<p class="text-sm text-muted-foreground">
									{trackingActive ? 'Estás en' : 'Última ubicación'}
								</p>
								<p class="text-3xl font-bold tracking-tight">
									{#if currentLocation && currentLocation.location !== 'unknown'}
										{currentLocation.location}
									{:else if trackingActive}
										Detectando...
									{:else}
										—
									{/if}
								</p>
								{#if currentLocation && currentLocation.location !== 'unknown'}
									<div class="mt-1 flex items-center gap-2">
										<span class={`text-sm font-medium ${getConfidenceColor(currentLocation.confidence)}`}>
											{formatConfidence(currentLocation.confidence)} confianza
										</span>
										{#if lastUpdated}
											<span class="text-xs text-muted-foreground">
												· {formatTime(lastUpdated)}
											</span>
										{/if}
									</div>
								{:else if currentLocation?.note}
									<p class="mt-1 text-sm text-muted-foreground">{currentLocation.note}</p>
								{/if}
							</div>
						</div>

						<!-- Confidence Bar -->
						{#if currentLocation && currentLocation.location !== 'unknown'}
							<div class="space-y-2">
								<div class="flex items-center justify-between text-sm">
									<span class="text-muted-foreground">Confianza</span>
									<span class="font-medium">{formatConfidence(currentLocation.confidence)}</span>
								</div>
								<Progress value={currentLocation.confidence * 100} max={100} />
							</div>
						{/if}

						<!-- Location Probabilities -->
						{#if currentLocation?.probabilities && Object.keys(currentLocation.probabilities).length > 0}
							<div class="space-y-2">
								<p class="text-sm font-medium text-muted-foreground">Probabilidades por espacio</p>
								<div class="space-y-1.5">
									{#each Object.entries(currentLocation.probabilities).sort((a, b) => b[1] - a[1]) as [loc, prob]}
										<div class="flex items-center gap-3">
											<span class="w-24 truncate text-sm">{loc}</span>
											<div class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
												<div
													class="h-full rounded-full bg-primary/60 transition-all duration-500"
													style="width: {prob * 100}%"
												></div>
											</div>
											<span class="w-12 text-right text-xs text-muted-foreground">
												{formatConfidence(prob)}
											</span>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>

					<!-- Tracking Controls -->
					<div class="flex flex-col items-center gap-3 lg:items-end">
						{#if !trackingActive}
							<Button
								size="lg"
								class="gap-2 bg-green-600 text-white hover:bg-green-700"
								onclick={startTracking}
								disabled={trackingStarting || spaces.length === 0}
							>
								{#if trackingStarting}
									<Activity class="size-5 animate-spin" />
									Iniciando...
								{:else}
									<Power class="size-5" />
									Iniciar tracking
								{/if}
							</Button>
						{:else}
							<Button
								size="lg"
								variant="destructive"
								class="gap-2"
								onclick={stopTracking}
								disabled={trackingStopping}
							>
								{#if trackingStopping}
									<Activity class="size-5 animate-spin" />
									Deteniendo...
								{:else}
									<PowerOff class="size-5" />
									Detener tracking
								{/if}
							</Button>
						{/if}

						<Button
							variant="outline"
							size="sm"
							class="gap-2"
							onclick={singlePredict}
						>
							<Eye class="size-4" />
							Detectar ahora
						</Button>

						<!-- Interval selector -->
						{#if !trackingActive}
							<div class="flex items-center gap-2 text-sm text-muted-foreground">
								<Clock class="size-3.5" />
								<span>Cada</span>
								<select
									bind:value={trackingInterval}
									class="rounded border border-input bg-background px-2 py-0.5 text-sm"
								>
									<option value={1}>1s</option>
									<option value={2}>2s</option>
									<option value={3}>3s</option>
									<option value={5}>5s</option>
									<option value={10}>10s</option>
								</select>
							</div>
						{/if}

						<!-- Tracking stats -->
						{#if trackingActive}
							<div class="flex items-center gap-3 text-xs text-muted-foreground">
								<div class="flex items-center gap-1">
									<Zap class="size-3" />
									<span>{predictionCount} lecturas</span>
								</div>
								<div class="flex items-center gap-1">
									<BarChart3 class="size-3" />
									<span>~{trackingInterval}s intervalo</span>
								</div>
							</div>
						{/if}

						{#if spaces.length === 0}
							<p class="max-w-48 text-center text-xs text-muted-foreground">
								Registra al menos un espacio para habilitar el tracking
							</p>
						{/if}
					</div>
				</div>
			</Card.Content>
		</Card.Root>

		<!-- Location History Timeline -->
		{#if locationHistory.length > 0}
			<Card.Root>
				<Card.Header>
					<div class="flex items-center gap-2">
						<Activity class="size-4 text-muted-foreground" />
						<Card.Title class="text-sm font-medium">Historial reciente</Card.Title>
						<Badge variant="secondary">{locationHistory.length}</Badge>
					</div>
				</Card.Header>
				<Card.Content>
					<div class="max-h-48 space-y-1 overflow-y-auto">
						{#each locationHistory as entry, i}
							<div class="flex items-center gap-3 rounded-md px-2 py-1.5 {i === 0 ? 'bg-muted/50' : ''}">
								<div class="flex size-6 items-center justify-center rounded-full {i === 0 ? 'bg-green-500/20' : 'bg-muted'}">
									<MapPin class="size-3 {i === 0 ? 'text-green-500' : 'text-muted-foreground'}" />
								</div>
								<span class="flex-1 text-sm {i === 0 ? 'font-medium' : 'text-muted-foreground'}">
									{entry.location === 'unknown' ? 'Desconocido' : entry.location}
								</span>
								<Badge variant={getConfidenceBadgeVariant(entry.confidence)} class="text-xs">
									{formatConfidence(entry.confidence)}
								</Badge>
								{#if entry.timestamp}
									<span class="text-xs text-muted-foreground">{formatTime(entry.timestamp)}</span>
								{/if}
							</div>
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		{/if}
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
					{@const isCurrentSpace = trackingActive && currentLocation?.location === space.name}
					<Card.Root class={isCurrentSpace ? 'border-green-500/50 ring-1 ring-green-500/20' : ''}>
						<Card.Header>
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-2">
									<Icon class="size-5 {isCurrentSpace ? 'text-green-500' : 'text-muted-foreground'}" />
									<Card.Title>{space.name}</Card.Title>
								</div>
								<div class="flex items-center gap-1.5">
									{#if isCurrentSpace}
										<Badge class="gap-1 bg-green-600 text-white">
											<span class="relative flex size-2">
												<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75"></span>
												<span class="relative inline-flex size-2 rounded-full bg-white"></span>
											</span>
											Aquí
										</Badge>
									{/if}
									<Badge variant="secondary">{getSpaceLabel(space.space_type)}</Badge>
								</div>
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
								{#if space.registration_feedback}
									<div class="flex items-center gap-2">
										{#if space.registration_feedback.collection_status === 'collecting'}
											<span>📡 {space.registration_feedback.samples_requested} muestras · Recolectando…</span>
										{:else if space.registration_feedback.collection_status === 'error'}
											<span>⚠️ Error en recolección</span>
										{:else}
											<span>📡 {space.registration_feedback.samples_requested} muestras · Completado</span>
										{/if}
									</div>
								{/if}
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
