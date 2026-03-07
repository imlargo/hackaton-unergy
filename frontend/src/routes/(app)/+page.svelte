<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		Wifi, Plus, MapPin, Radio, Home, Building, ChefHat, Warehouse,
		LayoutDashboard, Navigation, Power, PowerOff, Activity, Target, Clock,
		BarChart3, Eye, Zap, Sparkles, CircleDot, TrendingUp, Loader2,
		Download, Upload, Share2,
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
	import { trackingService, type LocationPrediction, type TrackingStatus, type CollectionStatus, type WifiPosDiagnostics } from '$lib/features/tracking/services/tracking';
	import type { Space, SpaceCreate } from '$lib/domain/models/space';
	import { BACKEND_BASE_URL } from '$lib/config/constants';

	let spaces: Space[] = $state([]);
	let wifiStatus: WifiStatus | null = $state(null);
	let loading = $state(true);
	let creating = $state(false);
	let dialogOpen = $state(false);

	// Tracking state
	let trackingActive = $state(false);
	let trackingStarting = $state(false);
	let trackingStopping = $state(false);
	let predicting = $state(false);
	let locationUpdating = $state(false);
	let currentLocation: LocationPrediction | null = $state(null);
	let locationHistory: LocationPrediction[] = $state([]);
	let pollInterval: ReturnType<typeof setInterval> | null = $state(null);
	let trackingInterval = $state(3);
	let lastUpdated: string | null = $state(null);
	let predictionCount = $state(0);

	// Model / system state
	let modelReady = $state(false);
	let collectingSpaces: Set<string> = $state(new Set());
	let collectionPollInterval: ReturnType<typeof setInterval> | null = $state(null);

	// Export / Import state
	let exporting = $state(false);
	let importing = $state(false);

	const TRACKING_POLL_MS = 3000;
	const COLLECTION_POLL_MS = 3000;
	const LOCATION_UPDATE_FLASH_MS = 500;

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
		if (confidence >= 0.8) return 'text-emerald-500';
		if (confidence >= 0.5) return 'text-amber-500';
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
			const [spacesData, wifi, trackingStatus, diag] = await Promise.all([
				spaceService.list(),
				instructionsService.getWifiStatus(),
				trackingService.status(),
				trackingService.diagnostics().catch(() => null),
			]);
			spaces = spacesData;
			wifiStatus = wifi;

			if (diag) {
				modelReady = !!diag.model_available;
			}

			for (const space of spacesData) {
				if (space.registration_feedback?.collection_status === 'collecting') {
					collectingSpaces.add(space.name);
				}
			}
			if (collectingSpaces.size > 0) {
				startCollectionPolling();
			}

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
		predicting = true;
		currentLocation = null;
		try {
			const prediction = await trackingService.predictOnce();
			currentLocation = prediction;
			lastUpdated = new Date().toISOString();
			predictionCount++;
			addToHistory(prediction);
		} catch (err) {
			console.error('Error predicting location:', err);
			toast.error('Error al predecir ubicación');
		} finally {
			predicting = false;
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
					const locationChanged = currentLocation?.location !== newPrediction.location;
					if (locationChanged && currentLocation) {
						// Location changed: clear → brief skeleton → new value
						locationUpdating = true;
						currentLocation = null;
						await new Promise(r => setTimeout(r, LOCATION_UPDATE_FLASH_MS));
						currentLocation = newPrediction;
						lastUpdated = newPrediction.timestamp ?? new Date().toISOString();
						predictionCount++;
						addToHistory(newPrediction);
						locationUpdating = false;
					} else {
						// Same location, just updated confidence/timestamp — flash transition
						locationUpdating = true;
						currentLocation = newPrediction;
						lastUpdated = newPrediction.timestamp ?? new Date().toISOString();
						predictionCount++;
						addToHistory(newPrediction);
						setTimeout(() => { locationUpdating = false; }, LOCATION_UPDATE_FLASH_MS);
					}
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
		pollInterval = setInterval(pollTrackingStatus, TRACKING_POLL_MS);
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
			const spaceName = newName.trim();
			const space = await spaceService.create({
				name: spaceName,
				space_type: newType,
				samples: newSamples,
			});
			spaces = [...spaces, space];
			const feedback = space.registration_feedback;
			if (feedback) {
				toast.success(
					`Espacio "${space.name}" registrado ✔ ` +
					`Recolectando ${feedback.samples_requested} muestras WiFi — ¡camina por el espacio!`
				);
				collectingSpaces.add(spaceName);
				startCollectionPolling();
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

	// ------------------------------------------------------------------
	// Collection status polling (after registering a space)
	// ------------------------------------------------------------------

	function startCollectionPolling() {
		if (collectionPollInterval) return;
		collectionPollInterval = setInterval(pollCollectionStatus, COLLECTION_POLL_MS);
	}

	function stopCollectionPolling() {
		if (collectionPollInterval) {
			clearInterval(collectionPollInterval);
			collectionPollInterval = null;
		}
	}

	function formatAccuracy(accuracy: number | null | undefined): string {
		if (accuracy == null) return 'OK';
		return `${Math.round(accuracy * 100)}%`;
	}

	async function pollCollectionStatus() {
		const names = [...collectingSpaces];
		if (names.length === 0) {
			stopCollectionPolling();
			return;
		}

		let changed = false;
		for (const name of names) {
			try {
				const cs = await trackingService.collectionStatus(name);
				if (cs.status === 'done') {
					collectingSpaces.delete(name);
					changed = true;

					const updatedSpace = spaces.find(s => s.name === name);
					if (updatedSpace?.registration_feedback) {
						updatedSpace.registration_feedback.collection_status = 'done';
						if (cs.fingerprints_saved !== undefined) {
							updatedSpace.registration_feedback.fingerprints_saved = cs.fingerprints_saved;
						}
						if (cs.model_trained) {
							updatedSpace.registration_feedback.model_trained = true;
							updatedSpace.registration_feedback.model_accuracy = cs.model_accuracy ?? undefined;
						}
						spaces = [...spaces];
					}

					if (cs.model_trained) {
						modelReady = true;
						toast.success(
							`🎯 Modelo entrenado — precisión ${formatAccuracy(cs.model_accuracy)}. ¡Ya puedes hacer tracking!`
						);
					} else {
						toast.success(
							`✅ Muestras de "${name}" recolectadas. Registra más espacios para entrenar el modelo.`
						);
					}
				} else if (cs.status === 'error') {
					collectingSpaces.delete(name);
					changed = true;

					const updatedSpace = spaces.find(s => s.name === name);
					if (updatedSpace?.registration_feedback) {
						updatedSpace.registration_feedback.collection_status = 'error';
						spaces = [...spaces];
					}
					toast.error(`Error recolectando muestras para "${name}"`);
				}
			} catch {
				// Ignore polling errors
			}
		}

		if (changed) {
			collectingSpaces = new Set(collectingSpaces);
		}
		if (collectingSpaces.size === 0) {
			stopCollectionPolling();
		}
	}

	// ── Model export / import ──────────────────────────────────────

	async function exportModel() {
		exporting = true;
		try {
			const resp = await fetch(`${BACKEND_BASE_URL}/model/export`);
			if (!resp.ok) throw new Error('Export failed');
			const bundle = await resp.json();
			const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `unergy-model-${new Date().toISOString().slice(0, 10)}.wifipos`;
			a.click();
			URL.revokeObjectURL(url);
			toast.success(`Modelo exportado — ${bundle.fingerprints?.length ?? 0} huellas`);
		} catch (err) {
			console.error(err);
			toast.error('Error al exportar el modelo');
		} finally {
			exporting = false;
		}
	}

	async function importModel(event: Event) {
		const input = event.target as HTMLInputElement;
		const file = input?.files?.[0];
		if (!file) return;
		importing = true;
		try {
			const formData = new FormData();
			formData.append('file', file);
			const resp = await fetch(`${BACKEND_BASE_URL}/model/import`, {
				method: 'POST',
				body: formData,
			});
			if (!resp.ok) throw new Error('Import failed');
			const result = await resp.json();
			toast.success(
				`Modelo importado — ${result.fingerprints_imported} huellas` +
					(result.model_imported ? ', modelo listo ✓' : '')
			);
			await loadData(); // refresh everything
		} catch (err) {
			console.error(err);
			toast.error('Error al importar — asegúrate de que sea un archivo .wifipos válido');
		} finally {
			importing = false;
			// Reset file input
			if (input) input.value = '';
		}
	}

	onMount(() => {
		loadData();
	});

	onDestroy(() => {
		stopPolling();
		stopCollectionPolling();
	});
</script>

<div class="mx-auto w-full max-w-5xl space-y-8">
	<!-- ═══════════════════ Hero Header ═══════════════════ -->
	<div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary/90 to-purple-700 p-8 text-white shadow-xl shadow-primary/20">
		<!-- Decorative blurs -->
		<div class="pointer-events-none absolute -top-20 -right-20 size-64 rounded-full bg-white/10 blur-3xl"></div>
		<div class="pointer-events-none absolute -bottom-16 -left-16 size-48 rounded-full bg-purple-400/20 blur-3xl"></div>

		<div class="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
			<div class="space-y-2">
				<div class="flex items-center gap-2">
					<Sparkles class="size-5 text-purple-200" />
					<span class="text-sm font-medium text-purple-200">Posicionamiento WiFi inteligente</span>
				</div>
				<h1 class="text-3xl font-bold tracking-tight sm:text-4xl">Panel de control</h1>
				<p class="max-w-md text-purple-100/80">
					Registra espacios, entrena modelos y detecta tu ubicación en tiempo real usando señales WiFi.
				</p>
			</div>
			<Dialog.Root bind:open={dialogOpen}>
				<Dialog.Trigger>
					{#snippet child({ props })}
						<Button {...props} class="gap-2 border-white/20 bg-white/15 text-white shadow-lg backdrop-blur-sm hover:bg-white/25">
							<Plus class="size-4" />
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
								<Loader2 class="mr-2 size-4 animate-spin" />
								Registrando…
							{:else}
								Registrar
							{/if}
						</Button>
					</Dialog.Footer>
				</Dialog.Content>
			</Dialog.Root>
		</div>
	</div>

	<!-- ═══════════════════ Stats Row ═══════════════════ -->
	<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
		{#if loading}
			{#each [1, 2, 3, 4] as _}
				<Card.Root class="group relative overflow-hidden">
					<Card.Header class="pb-2">
						<div class="flex items-center gap-2">
							<div class="size-8 animate-pulse rounded-lg bg-muted"></div>
							<div class="h-4 w-24 animate-pulse rounded-md bg-muted"></div>
						</div>
					</Card.Header>
					<Card.Content>
						<div class="h-7 w-20 animate-pulse rounded-md bg-muted"></div>
					</Card.Content>
				</Card.Root>
			{/each}
		{:else}
		<Card.Root class="group relative overflow-hidden transition-shadow hover:shadow-md">
			<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent"></div>
			<Card.Header class="pb-2">
				<div class="flex items-center gap-2">
					<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
						<Wifi class="size-4 text-primary" />
					</div>
					<Card.Title class="text-sm font-medium text-muted-foreground">Estado WiFi</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				{#if wifiStatus}
					<Badge variant={wifiStatus.wifi_available ? 'default' : 'outline'}>
						{wifiStatus.wifi_available ? '● Disponible' : 'No disponible'}
					</Badge>
				{:else if loading}
					<span class="text-sm text-muted-foreground">Cargando…</span>
				{:else}
					<Badge variant="outline">Sin conexión</Badge>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root class="group relative overflow-hidden transition-shadow hover:shadow-md">
			<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-purple-500/5 to-transparent"></div>
			<Card.Header class="pb-2">
				<div class="flex items-center gap-2">
					<div class="flex size-8 items-center justify-center rounded-lg bg-purple-500/10">
						<Radio class="size-4 text-purple-500" />
					</div>
					<Card.Title class="text-sm font-medium text-muted-foreground">Redes detectadas</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				<p class="text-3xl font-bold tracking-tight">
					{wifiStatus?.networks_detected ?? '—'}
				</p>
			</Card.Content>
		</Card.Root>

		<Card.Root class="group relative overflow-hidden transition-shadow hover:shadow-md">
			<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-violet-500/5 to-transparent"></div>
			<Card.Header class="pb-2">
				<div class="flex items-center gap-2">
					<div class="flex size-8 items-center justify-center rounded-lg bg-violet-500/10">
						<MapPin class="size-4 text-violet-500" />
					</div>
					<Card.Title class="text-sm font-medium text-muted-foreground">Espacios registrados</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				<p class="text-3xl font-bold tracking-tight">
					{spaces.length}
				</p>
			</Card.Content>
		</Card.Root>

		<Card.Root class="group relative overflow-hidden transition-shadow hover:shadow-md">
			<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent"></div>
			<Card.Header class="pb-2">
				<div class="flex items-center gap-2">
					<div class="flex size-8 items-center justify-center rounded-lg bg-emerald-500/10">
						<TrendingUp class="size-4 text-emerald-500" />
					</div>
					<Card.Title class="text-sm font-medium text-muted-foreground">Modelo ML</Card.Title>
				</div>
			</Card.Header>
			<Card.Content>
				{#if modelReady}
					<Badge class="bg-emerald-600 text-white">✓ Listo</Badge>
				{:else if spaces.length >= 2}
					<Badge variant="secondary">Entrenando…</Badge>
				{:else if spaces.length === 1}
					<Badge variant="outline">Falta 1 espacio</Badge>
				{:else}
					<Badge variant="outline">Sin datos</Badge>
				{/if}
			</Card.Content>
		</Card.Root>
		{/if}
	</div>
	<!-- ═══════════════════ Live Tracking ═══════════════════ -->
	<div class="space-y-4">
		<div class="flex items-center gap-2.5">
			<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
				<Navigation class="size-4 text-primary" />
			</div>
			<h2 class="text-xl font-semibold">Ubicación en vivo</h2>
			{#if trackingActive}
				<span class="relative ml-1 flex size-2.5">
					<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
					<span class="relative inline-flex size-2.5 rounded-full bg-emerald-500"></span>
				</span>
				<Badge variant="secondary" class="text-xs font-normal">Activo</Badge>
			{/if}
		</div>

		{#if loading}
			<Card.Root>
				<Card.Content class="p-6">
					<div class="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
						<div class="flex flex-1 items-center gap-4">
							<div class="size-16 animate-pulse rounded-2xl bg-muted"></div>
							<div class="space-y-2">
								<div class="h-4 w-24 animate-pulse rounded-md bg-muted"></div>
								<div class="h-8 w-48 animate-pulse rounded-lg bg-muted"></div>
								<div class="h-4 w-36 animate-pulse rounded-md bg-muted"></div>
							</div>
						</div>
						<div class="flex flex-col items-center gap-3 lg:items-end">
							<div class="h-10 w-40 animate-pulse rounded-lg bg-muted"></div>
							<div class="h-8 w-32 animate-pulse rounded-md bg-muted"></div>
						</div>
					</div>
				</Card.Content>
			</Card.Root>
		{:else}
		<Card.Root class={`relative overflow-hidden transition-all duration-300 ${trackingActive ? 'border-emerald-500/30 shadow-lg shadow-emerald-500/5' : ''}`}>
			{#if trackingActive}
				<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent"></div>
			{/if}
			<Card.Content class="relative p-6">
				<div class="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
					<!-- Current Location Display -->
					<div class="flex-1 space-y-5">
						<div class="flex items-center gap-4">
							<div class={`flex size-16 items-center justify-center rounded-2xl transition-colors duration-300 ${trackingActive ? 'bg-emerald-500/10' : (predicting || locationUpdating) ? 'bg-primary/10' : 'bg-muted'}`}>
								{#if predicting || (locationUpdating && !currentLocation)}
									<Loader2 class="size-8 animate-spin text-primary" />
								{:else if currentLocation && currentLocation.location !== 'unknown'}
									{@const LocIcon = getSpaceIcon(
										spaces.find(s => s.name === currentLocation?.location)?.space_type ?? ''
									)}
									<LocIcon class={`size-8 ${trackingActive ? 'text-emerald-500' : 'text-muted-foreground'}`} />
								{:else}
									<Target class={`size-8 ${trackingActive ? 'text-emerald-500 animate-pulse' : 'text-muted-foreground'}`} />
								{/if}
							</div>
							<div class="min-w-0 flex-1">
								<p class="text-sm text-muted-foreground">
									{(predicting || (locationUpdating && !currentLocation)) ? 'Detectando ubicación…' : trackingActive ? 'Estás en' : 'Última ubicación'}
								</p>
								{#if predicting || (locationUpdating && !currentLocation)}
									<div class="mt-1 space-y-2">
										<div class="h-8 w-48 animate-pulse rounded-lg bg-primary/10"></div>
										<div class="h-4 w-32 animate-pulse rounded-md bg-muted"></div>
									</div>
								{:else}
									<p class={`text-3xl font-bold tracking-tight transition-all duration-500 ${locationUpdating ? 'scale-105 text-primary' : ''}`}>
										{#if currentLocation && currentLocation.location !== 'unknown'}
											{currentLocation.location}
										{:else if trackingActive}
											Detectando…
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
									{:else if !modelReady && spaces.length >= 2}
										<p class="mt-1 text-sm text-amber-600">
											⏳ El modelo se está entrenando con los datos recolectados…
										</p>
									{:else if !modelReady && spaces.length === 1}
										<p class="mt-1 text-sm text-muted-foreground">
											Registra al menos 2 espacios diferentes para activar la detección
										</p>
									{:else if !modelReady && spaces.length === 0}
										<p class="mt-1 text-sm text-muted-foreground">
											Registra espacios en diferentes habitaciones para comenzar
										</p>
									{:else if currentLocation?.location === 'unknown' && modelReady}
										<p class="mt-1 text-sm text-amber-600">
											No se pudo determinar la ubicación — intenta moverte
										</p>
									{/if}
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
							<div class="space-y-3">
								<p class="text-sm font-medium text-muted-foreground">Probabilidades por espacio</p>
								<div class="space-y-2">
									{#each Object.entries(currentLocation.probabilities).sort((a, b) => b[1] - a[1]) as [loc, prob]}
										<div class="flex items-center gap-3">
											<span class="w-24 truncate text-sm">{loc}</span>
											<div class="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
												<div
													class="h-full rounded-full bg-gradient-to-r from-primary/70 to-primary transition-all duration-500"
													style="width: {prob * 100}%"
												></div>
											</div>
											<span class="w-12 text-right text-xs font-medium text-muted-foreground">
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
								class="gap-2 bg-emerald-600 text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-700"
								onclick={startTracking}
								disabled={trackingStarting || spaces.length === 0}
							>
								{#if trackingStarting}
									<Loader2 class="size-5 animate-spin" />
									Iniciando…
								{:else}
									<Power class="size-5" />
									Iniciar tracking
								{/if}
							</Button>
						{:else}
							<Button
								size="lg"
								variant="destructive"
								class="gap-2 shadow-lg"
								onclick={stopTracking}
								disabled={trackingStopping}
							>
								{#if trackingStopping}
									<Loader2 class="size-5 animate-spin" />
									Deteniendo…
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
							disabled={predicting}
						>
							{#if predicting}
								<Loader2 class="size-4 animate-spin" />
								Detectando…
							{:else}
								<Eye class="size-4" />
								Detectar ahora
							{/if}
						</Button>

						<!-- Interval selector -->
						{#if !trackingActive}
							<div class="flex items-center gap-2 text-sm text-muted-foreground">
								<Clock class="size-3.5" />
								<span>Cada</span>
								<select
									bind:value={trackingInterval}
									class="rounded-md border border-input bg-background px-2 py-0.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary/30"
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
									<Zap class="size-3 text-emerald-500" />
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
								Registra al menos 2 espacios para empezar a detectar tu ubicación
							</p>
						{:else if spaces.length === 1 && !modelReady}
							<p class="max-w-48 text-center text-xs text-amber-600">
								Falta 1 espacio más para entrenar el modelo
							</p>
						{:else if collectingSpaces.size > 0}
							<p class="max-w-48 text-center text-xs text-muted-foreground">
								📡 Recolectando muestras… camina por el espacio
							</p>
						{/if}
					</div>
				</div>
			</Card.Content>
		</Card.Root>
		{/if}

		<!-- Location History Timeline -->
		{#if locationHistory.length > 0}
			<Card.Root>
				<Card.Header>
					<div class="flex items-center gap-2">
						<Activity class="size-4 text-muted-foreground" />
						<Card.Title class="text-sm font-medium">Historial reciente</Card.Title>
						<Badge variant="secondary" class="text-xs">{locationHistory.length}</Badge>
					</div>
				</Card.Header>
				<Card.Content>
					<div class="max-h-48 space-y-1 overflow-y-auto">
						{#each locationHistory as entry, i}
							<div class="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors {i === 0 ? 'bg-primary/5' : 'hover:bg-muted/50'}">
								<div class="flex size-6 items-center justify-center rounded-full {i === 0 ? 'bg-primary/15' : 'bg-muted'}">
									<MapPin class="size-3 {i === 0 ? 'text-primary' : 'text-muted-foreground'}" />
								</div>
								<span class="flex-1 text-sm {i === 0 ? 'font-medium' : 'text-muted-foreground'}">
									{entry.location === 'unknown'
										? (modelReady ? 'No determinado' : 'Sin modelo')
										: entry.location}
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

	<!-- ═══════════════════ Spaces List ═══════════════════ -->
	<div id="espacios">
		<div class="mb-4 flex items-center gap-2.5">
			<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
				<LayoutDashboard class="size-4 text-primary" />
			</div>
			<h2 class="text-xl font-semibold">Espacios</h2>
			<Badge variant="secondary" class="text-xs">{spaces.length}</Badge>
		</div>

		{#if loading}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each [1, 2, 3] as _}
					<Card.Root>
						<Card.Header>
							<div class="h-5 w-32 animate-pulse rounded-md bg-muted"></div>
							<div class="h-4 w-20 animate-pulse rounded-md bg-muted"></div>
						</Card.Header>
						<Card.Content>
							<div class="space-y-2">
								<div class="h-4 w-full animate-pulse rounded-md bg-muted"></div>
								<div class="h-4 w-3/4 animate-pulse rounded-md bg-muted"></div>
							</div>
						</Card.Content>
					</Card.Root>
				{/each}
			</div>
		{:else if spaces.length === 0}
			<Card.Root class="border-dashed">
				<Card.Content class="flex flex-col items-center justify-center py-16">
					<div class="mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
						<MapPin class="size-8 text-primary" />
					</div>
					<p class="text-lg font-semibold">No hay espacios registrados</p>
					<p class="mb-6 max-w-sm text-center text-sm text-muted-foreground">
						Registra al menos 2 espacios (ej: cocina y sala) para comenzar
						la detección automática de ubicación por WiFi
					</p>
					<Button onclick={() => (dialogOpen = true)} class="gap-2">
						<Plus class="size-4" />
						Registrar espacio
					</Button>
				</Card.Content>
			</Card.Root>
		{:else}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each spaces as space}
					{@const Icon = getSpaceIcon(space.space_type)}
					{@const isCurrentSpace = trackingActive && currentLocation?.location === space.name}
					<Card.Root class={`group relative overflow-hidden transition-all duration-300 hover:shadow-md ${isCurrentSpace ? 'border-emerald-500/40 shadow-lg shadow-emerald-500/10 ring-1 ring-emerald-500/20' : ''}`}>
						{#if isCurrentSpace}
							<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent"></div>
						{/if}
						<Card.Header class="relative">
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-2.5">
									<div class={`flex size-9 items-center justify-center rounded-lg transition-colors ${isCurrentSpace ? 'bg-emerald-500/15' : 'bg-muted'}`}>
										<Icon class={`size-5 ${isCurrentSpace ? 'text-emerald-500' : 'text-muted-foreground'}`} />
									</div>
									<Card.Title class="text-base">{space.name}</Card.Title>
								</div>
								<div class="flex items-center gap-1.5">
									{#if isCurrentSpace}
										<Badge class="gap-1 bg-emerald-600 text-white">
											<span class="relative flex size-1.5">
												<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75"></span>
												<span class="relative inline-flex size-1.5 rounded-full bg-white"></span>
											</span>
											Aquí
										</Badge>
									{/if}
									<Badge variant="secondary" class="text-xs">{getSpaceLabel(space.space_type)}</Badge>
								</div>
							</div>
						</Card.Header>
						<Card.Content class="relative">
							<div class="space-y-2.5 text-sm text-muted-foreground">
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
											<span class="flex items-center gap-1.5 text-primary">
												<span class="relative flex size-2">
													<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
													<span class="relative inline-flex size-2 rounded-full bg-primary"></span>
												</span>
												Recolectando {space.registration_feedback.samples_requested} muestras… ¡Camina!
											</span>
										{:else if space.registration_feedback.collection_status === 'error'}
											<span class="text-destructive">⚠️ Error en recolección</span>
										{:else if space.registration_feedback.model_trained}
											<span class="text-emerald-600">✓ {space.registration_feedback.fingerprints_saved} muestras · Modelo entrenado ({formatAccuracy(space.registration_feedback.model_accuracy)})</span>
										{:else}
											<span>📡 {space.registration_feedback.fingerprints_saved} muestras recolectadas</span>
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

	<!-- ═══════════════════ Model Sharing ═══════════════════ -->
	<div>
		<div class="mb-4 flex items-center gap-2.5">
			<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
				<Share2 class="size-4 text-primary" />
			</div>
			<h2 class="text-xl font-semibold">Compartir modelo</h2>
		</div>

		<Card.Root>
			<Card.Content class="space-y-4 p-6">
				<p class="text-sm text-muted-foreground">
					Exporta el modelo entrenado y las huellas WiFi para usarlos en otro computador.
					Importa un archivo <code class="rounded bg-muted px-1">.wifipos</code> para cargar datos de otra máquina.
				</p>

				<div class="flex flex-wrap gap-3">
					<Button
						variant="outline"
						class="gap-2"
						onclick={exportModel}
						disabled={exporting || !modelReady}
					>
						{#if exporting}
							<Loader2 class="size-4 animate-spin" />
							Exportando…
						{:else}
							<Download class="size-4" />
							Exportar modelo
						{/if}
					</Button>

					<Button
						variant="outline"
						class="relative gap-2"
						disabled={importing}
					>
						{#if importing}
							<Loader2 class="size-4 animate-spin" />
							Importando…
						{:else}
							<Upload class="size-4" />
							Importar modelo
						{/if}
						<input
							type="file"
							accept=".wifipos,.json"
							class="absolute inset-0 cursor-pointer opacity-0"
							onchange={importModel}
							disabled={importing}
						/>
					</Button>
				</div>

				{#if !modelReady}
					<p class="text-xs text-amber-600">
						⚠️ Registra al menos 2 espacios para entrenar un modelo antes de exportar.
						También puedes <strong>importar</strong> un modelo de otro PC.
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>
</div>
