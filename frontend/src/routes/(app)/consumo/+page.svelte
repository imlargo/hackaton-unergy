<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		Zap, Plus, Power, PowerOff, Tv, Lamp, Fan, Monitor, Snowflake,
		Speaker, BatteryCharging, Shirt, CookingPot, Plug, Leaf,
		BarChart3, Activity, Loader2, Trash2, RefrigeratorIcon,
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
	import {
		consumptionService,
		type Device,
		type DeviceEvent,
		type ConsumptionSummary,
		type DeviceCatalogEntry,
	} from '$lib/features/consumption/services/consumption';
	import type { Space } from '$lib/domain/models/space';

	// ── State ──
	let spaces: Space[] = $state([]);
	let devices: Device[] = $state([]);
	let summary: ConsumptionSummary | null = $state(null);
	let events: DeviceEvent[] = $state([]);
	let catalog: Record<string, DeviceCatalogEntry> = $state({});
	let loading = $state(true);
	let dialogOpen = $state(false);
	let togglingDevices: Set<number> = $state(new Set());

	// Form state
	let newDeviceName = $state('');
	let newDeviceType = $state('tv');
	let newDeviceSpace = $state('');

	// Polling
	let pollInterval: ReturnType<typeof setInterval> | null = $state(null);
	const POLL_MS = 3000;

	// Icon map
	const iconMap: Record<string, any> = {
		tv: Tv,
		lamp: Lamp,
		fan: Fan,
		monitor: Monitor,
		snowflake: Snowflake,
		speaker: Speaker,
		'battery-charging': BatteryCharging,
		shirt: Shirt,
		'cooking-pot': CookingPot,
		plug: Plug,
		refrigerator: Plug,
	};

	function getDeviceIcon(iconName: string) {
		return iconMap[iconName] ?? Plug;
	}

	// ── Data loading ──
	async function loadAll() {
		try {
			const [spacesRes, catalogRes] = await Promise.all([
				spaceService.list(),
				consumptionService.getCatalog(),
			]);
			spaces = spacesRes;
			catalog = catalogRes.devices;
			if (spaces.length > 0 && !newDeviceSpace) {
				newDeviceSpace = spaces[0].name;
			}
			await refreshData();
		} catch (err) {
			console.error('Load failed:', err);
		} finally {
			loading = false;
		}
	}

	async function refreshData() {
		try {
			const [devRes, sumRes, evtRes] = await Promise.all([
				consumptionService.listDevices(),
				consumptionService.getSummary(),
				consumptionService.getEvents(undefined, 20),
			]);
			devices = devRes.devices;
			summary = sumRes;
			events = evtRes.events;
		} catch (err) {
			console.error('Refresh failed:', err);
		}
	}

	// ── Actions ──
	async function addDevice() {
		if (!newDeviceName.trim() || !newDeviceSpace) return;
		try {
			const device = await consumptionService.registerDevice({
				space_name: newDeviceSpace,
				name: newDeviceName.trim(),
				device_type: newDeviceType,
			});
			toast.success(`${device.label} registrado en ${device.space_name}`);
			newDeviceName = '';
			dialogOpen = false;
			await refreshData();
		} catch (err) {
			toast.error('Error al registrar dispositivo');
			console.error(err);
		}
	}

	async function toggleDevice(device: Device) {
		const action = device.is_on ? 'off' : 'on';
		togglingDevices = new Set([...togglingDevices, device.id]);
		try {
			const event = await consumptionService.toggleDevice(device.id, action);
			if (action === 'off' && event.kwh_consumed !== undefined) {
				toast.info(event.message);
			} else {
				toast.success(event.message);
			}
			await refreshData();
		} catch (err) {
			toast.error('Error al cambiar estado del dispositivo');
			console.error(err);
		} finally {
			togglingDevices = new Set([...togglingDevices].filter(id => id !== device.id));
		}
	}

	// ── Helpers ──
	function formatKwh(kwh: number): string {
		if (kwh < 0.001) return `${(kwh * 1_000_000).toFixed(1)} µWh`;
		if (kwh < 1) return `${(kwh * 1000).toFixed(2)} Wh`;
		return `${kwh.toFixed(3)} kWh`;
	}

	function formatCo2(kg: number): string {
		if (kg < 0.001) return `${(kg * 1_000_000).toFixed(1)} µg`;
		if (kg < 1) return `${(kg * 1000).toFixed(2)} g`;
		return `${kg.toFixed(3)} kg`;
	}

	function formatWatts(w: number): string {
		if (w >= 1000) return `${(w / 1000).toFixed(1)} kW`;
		return `${w} W`;
	}

	function timeAgo(ts: number): string {
		const seconds = Math.floor(Date.now() / 1000 - ts);
		if (seconds < 60) return `hace ${seconds}s`;
		if (seconds < 3600) return `hace ${Math.floor(seconds / 60)}min`;
		return `hace ${Math.floor(seconds / 3600)}h`;
	}

	// ── Lifecycle ──
	onMount(() => {
		loadAll();
		pollInterval = setInterval(refreshData, POLL_MS);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

<div class="mx-auto w-full max-w-5xl space-y-8">
	<!-- ═══════════════════ Hero Header ═══════════════════ -->
	<div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-green-600 via-emerald-600 to-teal-700 p-6 text-white shadow-lg md:p-8">
		<div class="absolute -top-8 -right-8 size-32 rounded-full bg-white/10 blur-2xl"></div>
		<div class="absolute -bottom-4 -left-4 size-24 rounded-full bg-white/10 blur-xl"></div>
		<div class="relative">
			<div class="mb-2 flex items-center gap-2 text-sm font-medium text-white/80">
				<Leaf class="size-4" />
				Monitoreo de consumo energético
			</div>
			<h1 class="mb-2 text-2xl font-bold md:text-3xl">Consumo y huella de carbono</h1>
			<p class="max-w-xl text-sm text-white/80">
				Asigna dispositivos a tus espacios, controla su encendido/apagado y monitorea
				el consumo energético y la huella de carbono en tiempo real.
			</p>
		</div>
		<Button
			variant="secondary"
			class="mt-4 gap-2"
			onclick={() => (dialogOpen = true)}
		>
			<Plus class="size-4" />
			Agregar dispositivo
		</Button>
	</div>

	<!-- ═══════════════════ Stats Row ═══════════════════ -->
	{#if summary}
		<div class="grid grid-cols-2 gap-4 md:grid-cols-4">
			<Card.Root>
				<Card.Header class="pb-2">
					<div class="flex items-center gap-2">
						<div class="flex size-8 items-center justify-center rounded-lg bg-amber-500/10">
							<Zap class="size-4 text-amber-500" />
						</div>
						<Card.Title class="text-sm font-medium text-muted-foreground">Consumo total</Card.Title>
					</div>
				</Card.Header>
				<Card.Content>
					<p class="text-xl font-bold">{formatKwh(summary.total_kwh)}</p>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header class="pb-2">
					<div class="flex items-center gap-2">
						<div class="flex size-8 items-center justify-center rounded-lg bg-green-500/10">
							<Leaf class="size-4 text-green-500" />
						</div>
						<Card.Title class="text-sm font-medium text-muted-foreground">CO₂ emitido</Card.Title>
					</div>
				</Card.Header>
				<Card.Content>
					<p class="text-xl font-bold">{formatCo2(summary.total_co2_kg)}</p>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header class="pb-2">
					<div class="flex items-center gap-2">
						<div class="flex size-8 items-center justify-center rounded-lg bg-red-500/10">
							<Activity class="size-4 text-red-500" />
						</div>
						<Card.Title class="text-sm font-medium text-muted-foreground">Potencia activa</Card.Title>
					</div>
				</Card.Header>
				<Card.Content>
					<p class="text-xl font-bold">{formatWatts(summary.active_watts)}</p>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header class="pb-2">
					<div class="flex items-center gap-2">
						<div class="flex size-8 items-center justify-center rounded-lg bg-blue-500/10">
							<Power class="size-4 text-blue-500" />
						</div>
						<Card.Title class="text-sm font-medium text-muted-foreground">Dispositivos</Card.Title>
					</div>
				</Card.Header>
				<Card.Content>
					<p class="text-xl font-bold">
						<span class="text-emerald-500">{summary.active_devices}</span>
						<span class="text-sm font-normal text-muted-foreground">/ {summary.total_devices}</span>
					</p>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}

	<!-- ═══════════════════ Devices by Space ═══════════════════ -->
	<div>
		<div class="mb-4 flex items-center gap-2.5">
			<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
				<Plug class="size-4 text-primary" />
			</div>
			<h2 class="text-xl font-semibold">Dispositivos</h2>
			<Badge variant="secondary" class="text-xs">{devices.length}</Badge>
		</div>

		{#if loading}
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each [1, 2, 3] as _}
					<Card.Root>
						<Card.Header>
							<div class="h-5 w-32 animate-pulse rounded-md bg-muted"></div>
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
		{:else if devices.length === 0}
			<Card.Root class="border-dashed">
				<Card.Content class="flex flex-col items-center justify-center py-16">
					<div class="mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
						<Plug class="size-8 text-primary" />
					</div>
					<p class="text-lg font-semibold">No hay dispositivos registrados</p>
					<p class="mb-6 max-w-sm text-center text-sm text-muted-foreground">
						Agrega dispositivos a tus espacios para comenzar a monitorear consumo energético
					</p>
					<Button onclick={() => (dialogOpen = true)} class="gap-2">
						<Plus class="size-4" />
						Agregar dispositivo
					</Button>
				</Card.Content>
			</Card.Root>
		{:else}
			<!-- Group devices by space -->
			{@const spaceGroups = devices.reduce((acc, d) => {
				(acc[d.space_name] = acc[d.space_name] || []).push(d);
				return acc;
			}, {} as Record<string, Device[]>)}

			<div class="space-y-6">
				{#each Object.entries(spaceGroups) as [spaceName, spaceDevices]}
					{@const spaceStats = summary?.by_space[spaceName]}
					<div>
						<div class="mb-3 flex items-center justify-between">
							<div class="flex items-center gap-2">
								<h3 class="text-lg font-semibold">{spaceName}</h3>
								<Badge variant="outline" class="text-xs">
									{spaceDevices.filter(d => d.is_on).length}/{spaceDevices.length} activos
								</Badge>
							</div>
							{#if spaceStats}
								<div class="flex items-center gap-3 text-xs text-muted-foreground">
									<span class="flex items-center gap-1">
										<Zap class="size-3" />
										{formatKwh(spaceStats.kwh)}
									</span>
									<span class="flex items-center gap-1">
										<Leaf class="size-3" />
										{formatCo2(spaceStats.co2_kg)}
									</span>
								</div>
							{/if}
						</div>

						<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
							{#each spaceDevices as device}
								{@const DeviceIcon = getDeviceIcon(device.icon)}
								{@const isToggling = togglingDevices.has(device.id)}
								<Card.Root class={`group relative overflow-hidden transition-all duration-300 ${device.is_on ? 'border-emerald-500/40 shadow-md shadow-emerald-500/10 ring-1 ring-emerald-500/20' : 'hover:shadow-sm'}`}>
									{#if device.is_on}
										<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent"></div>
									{/if}
									<Card.Header class="relative pb-2">
										<div class="flex items-center justify-between">
											<div class="flex items-center gap-2.5">
												<div class={`flex size-9 items-center justify-center rounded-lg ${device.is_on ? 'bg-emerald-500/15' : 'bg-muted'}`}>
													<DeviceIcon class={`size-4 ${device.is_on ? 'text-emerald-500' : 'text-muted-foreground'}`} />
												</div>
												<div>
													<Card.Title class="text-sm font-semibold">{device.name}</Card.Title>
													<p class="text-xs text-muted-foreground">{device.label} · {device.watts}W</p>
												</div>
											</div>
											<Button
												size="sm"
												variant={device.is_on ? 'default' : 'outline'}
												class={`gap-1.5 ${device.is_on ? 'bg-emerald-600 hover:bg-red-600' : 'hover:bg-emerald-50 hover:text-emerald-600 hover:border-emerald-300'}`}
												onclick={() => toggleDevice(device)}
												disabled={isToggling}
											>
												{#if isToggling}
													<Loader2 class="size-3.5 animate-spin" />
												{:else if device.is_on}
													<PowerOff class="size-3.5" />
													Apagar
												{:else}
													<Power class="size-3.5" />
													Encender
												{/if}
											</Button>
										</div>
									</Card.Header>
									<Card.Content class="relative pt-0">
										<div class="flex items-center gap-4 text-xs text-muted-foreground">
											<span class="flex items-center gap-1">
												<Zap class="size-3" />
												{formatKwh(device.total_kwh)}
											</span>
											<span class="flex items-center gap-1">
												<Leaf class="size-3" />
												{formatCo2(device.total_kwh * 0.126)}
											</span>
											{#if device.is_on}
												<Badge variant="default" class="bg-emerald-600 text-[10px]">
													<Activity class="mr-1 size-2.5" /> Activo
												</Badge>
											{/if}
										</div>
									</Card.Content>
								</Card.Root>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- ═══════════════════ Carbon Footprint ═══════════════════ -->
	{#if summary && summary.total_devices > 0}
		<div>
			<div class="mb-4 flex items-center gap-2.5">
				<div class="flex size-8 items-center justify-center rounded-lg bg-green-500/10">
					<Leaf class="size-4 text-green-500" />
				</div>
				<h2 class="text-xl font-semibold">Huella de carbono</h2>
			</div>

			<Card.Root>
				<Card.Content class="p-6">
					<div class="grid gap-6 md:grid-cols-3">
						<div class="space-y-2">
							<p class="text-sm font-medium text-muted-foreground">Energía consumida</p>
							<p class="text-3xl font-bold">{formatKwh(summary.total_kwh)}</p>
							<p class="text-xs text-muted-foreground">Total acumulado de todos los dispositivos</p>
						</div>
						<div class="space-y-2">
							<p class="text-sm font-medium text-muted-foreground">CO₂ equivalente</p>
							<p class="text-3xl font-bold text-green-600">{formatCo2(summary.total_co2_kg)}</p>
							<p class="text-xs text-muted-foreground">
								Factor: {summary.co2_factor_kg_per_kwh} kg CO₂/kWh (Colombia)
							</p>
						</div>
						<div class="space-y-2">
							<p class="text-sm font-medium text-muted-foreground">Equivalencia</p>
							<p class="text-3xl font-bold text-emerald-600">
								{(summary.total_co2_kg / 0.022).toFixed(1)}
							</p>
							<p class="text-xs text-muted-foreground">
								Km equivalentes en auto (0.022 kg CO₂/km promedio)
							</p>
						</div>
					</div>

					{#if Object.keys(summary.by_space).length > 0}
						<Separator class="my-6" />
						<h3 class="mb-3 text-sm font-semibold">Consumo por espacio</h3>
						<div class="space-y-3">
							{#each Object.entries(summary.by_space) as [space, stats]}
								{@const pct = summary.total_kwh > 0 ? (stats.kwh / summary.total_kwh) * 100 : 0}
								<div class="space-y-1">
									<div class="flex items-center justify-between text-sm">
										<span class="font-medium">{space}</span>
										<span class="text-muted-foreground">
											{formatKwh(stats.kwh)} · {formatCo2(stats.co2_kg)} CO₂
										</span>
									</div>
									<Progress value={pct} class="h-2" />
								</div>
							{/each}
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		</div>
	{/if}

	<!-- ═══════════════════ Event Log ═══════════════════ -->
	{#if events.length > 0}
		<div>
			<div class="mb-4 flex items-center gap-2.5">
				<div class="flex size-8 items-center justify-center rounded-lg bg-blue-500/10">
					<BarChart3 class="size-4 text-blue-500" />
				</div>
				<h2 class="text-xl font-semibold">Eventos recientes</h2>
				<Badge variant="secondary" class="text-xs">{events.length}</Badge>
			</div>

			<Card.Root>
				<Card.Content class="p-0">
					<div class="divide-y">
						{#each events as event}
							<div class="flex items-center gap-3 px-4 py-3">
								<div class={`flex size-8 items-center justify-center rounded-full ${event.action === 'on' ? 'bg-emerald-500/10' : 'bg-amber-500/10'}`}>
									{#if event.action === 'on'}
										<Power class="size-3.5 text-emerald-500" />
									{:else}
										<PowerOff class="size-3.5 text-amber-500" />
									{/if}
								</div>
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm font-medium">{event.device_name}</p>
									<p class="text-xs text-muted-foreground">
										{event.space_name} · {event.action === 'on' ? 'Encendido' : 'Apagado'}
										{#if event.kwh_consumed !== undefined}
											· {formatKwh(event.kwh_consumed)}
										{/if}
									</p>
								</div>
								<span class="shrink-0 text-xs text-muted-foreground">
									{timeAgo(event.timestamp)}
								</span>
							</div>
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}
</div>

<!-- ═══════════════════ Add Device Dialog ═══════════════════ -->
<Dialog.Root bind:open={dialogOpen}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Agregar dispositivo</Dialog.Title>
			<Dialog.Description>
				Registra un dispositivo eléctrico en uno de tus espacios para monitorear su consumo.
			</Dialog.Description>
		</Dialog.Header>
		<div class="space-y-4 py-4">
			<div class="space-y-2">
				<Label>Nombre del dispositivo</Label>
				<Input bind:value={newDeviceName} placeholder="Ej: TV de la sala" />
			</div>

			<div class="space-y-2">
				<Label>Tipo de dispositivo</Label>
				<select
					bind:value={newDeviceType}
					class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
				>
					{#each Object.entries(catalog) as [key, info]}
						<option value={key}>{info.label} ({info.watts}W)</option>
					{/each}
				</select>
			</div>

			<div class="space-y-2">
				<Label>Espacio</Label>
				<select
					bind:value={newDeviceSpace}
					class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
				>
					{#each spaces as space}
						<option value={space.name}>{space.name}</option>
					{/each}
				</select>
			</div>
		</div>
		<Dialog.Footer>
			<Button variant="outline" onclick={() => (dialogOpen = false)}>Cancelar</Button>
			<Button onclick={addDevice} disabled={!newDeviceName.trim() || !newDeviceSpace} class="gap-2">
				<Plus class="size-4" />
				Registrar
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
