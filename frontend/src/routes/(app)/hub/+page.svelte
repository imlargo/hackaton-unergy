<script lang="ts">
import { onMount, onDestroy } from 'svelte';
import { toast } from 'svelte-sonner';
import {
Users, MapPin, Home, Building, ChefHat, Warehouse,
Loader2, Wifi, Radio, User, Edit3, Check, X, Link
} from '@lucide/svelte';
import * as Card from '$lib/components/ui/card/index.js';
import { Button } from '$lib/components/ui/button/index.js';
import { Badge } from '$lib/components/ui/badge/index.js';
import { Separator } from '$lib/components/ui/separator/index.js';
import { spaceService } from '$lib/features/spaces/services/space';
import { trackingService, type LocationPrediction } from '$lib/features/tracking/services/tracking';
import { hubService, type HubUser } from '$lib/features/hub/services/hub';
import type { Space } from '$lib/domain/models/space';

// ── Device identity (UUID persisted in localStorage) ──
let deviceId = $state('');
let displayName = $state('');
let editingName = $state(false);
let nameInput = $state('');

// ── Hub server config ──
let hubUrl = $state('');
let editingUrl = $state(false);
let urlInput = $state('');
let hubConnected = $state(false);

// ── Data ──
let spaces: Space[] = $state([]);
let hubUsers: HubUser[] = $state([]);
let loading = $state(true);
let currentLocation: LocationPrediction | null = $state(null);
let trackingActive = $state(false);

// ── Polling ──
let pollInterval: ReturnType<typeof setInterval> | null = $state(null);
const HUB_POLL_INTERVAL_MS = 2500;

// ── Space types ──
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

// ── Device identity helpers ──
function getDeviceId(): string {
if (typeof window === 'undefined') return '';
let id = localStorage.getItem('unergy_device_id');
if (!id) {
id = crypto.randomUUID();
localStorage.setItem('unergy_device_id', id);
}
return id;
}

function getDisplayName(): string {
if (typeof window === 'undefined') return 'Anónimo';
return localStorage.getItem('unergy_display_name') || 'Anónimo';
}

function saveDisplayName(name: string) {
displayName = name;
if (typeof window !== 'undefined') {
localStorage.setItem('unergy_display_name', name);
}
}

function startEditName() { nameInput = displayName; editingName = true; }
function confirmEditName() {
const trimmed = nameInput.trim();
if (trimmed) saveDisplayName(trimmed);
editingName = false;
}
function cancelEditName() { editingName = false; }

// ── Hub URL helpers ──
function startEditUrl() { urlInput = hubUrl; editingUrl = true; }
function confirmEditUrl() {
const trimmed = urlInput.trim();
if (trimmed) {
hubService.setHubUrl(trimmed);
hubUrl = hubService.hubUrl;
toast.success(`Hub server: ${hubUrl}`);
}
editingUrl = false;
}
function cancelEditUrl() { editingUrl = false; }

// ── Avatar helpers ──
const avatarColors = [
'bg-violet-500', 'bg-blue-500', 'bg-emerald-500', 'bg-amber-500',
'bg-rose-500', 'bg-cyan-500', 'bg-pink-500', 'bg-teal-500',
'bg-indigo-500', 'bg-orange-500',
];

function getAvatarColor(id: string): string {
let hash = 0;
for (let i = 0; i < id.length; i++) {
hash = ((hash << 5) - hash) + id.charCodeAt(i);
hash |= 0;
}
return avatarColors[Math.abs(hash) % avatarColors.length];
}

function getInitials(name: string): string {
return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?';
}

// ── Room building ──
// Merge local spaces + hub users' locations into a unified room list
interface Room {
name: string;
space_type: string;
users: HubUser[];
}

function buildRooms(): Room[] {
const roomMap = new Map<string, Room>();

for (const s of spaces) {
roomMap.set(s.name, { name: s.name, space_type: s.space_type, users: [] });
}

for (const u of hubUsers) {
if (u.location && !roomMap.has(u.location)) {
roomMap.set(u.location, {
name: u.location,
space_type: u.space_type ?? 'room',
users: [],
});
}
}

for (const u of hubUsers) {
if (u.location && roomMap.has(u.location)) {
roomMap.get(u.location)!.users.push(u);
}
}

return [...roomMap.values()];
}

function getUnlocatedUsers(): HubUser[] {
const roomNames = new Set([
...spaces.map(s => s.name),
...hubUsers.filter(u => u.location).map(u => u.location!),
]);
return hubUsers.filter(u => !u.location || !roomNames.has(u.location));
}

function formatConfidence(c: number): string {
return `${Math.round(c * 100)}%`;
}

// ── Data loading & polling ──
async function loadData() {
loading = true;
try {
const [spacesData, status] = await Promise.all([
spaceService.list(),
trackingService.status(),
]);
spaces = spacesData;
trackingActive = status.active;
if (status.latest_prediction) {
currentLocation = status.latest_prediction;
}
try {
const usersRes = await hubService.getUsers();
hubUsers = usersRes.users;
hubConnected = true;
} catch {
hubConnected = false;
}
} catch (err) {
console.error('Error loading hub data:', err);
toast.error('Error al cargar datos');
} finally {
loading = false;
}
}

async function poll() {
try {
const status = await trackingService.status();
trackingActive = status.active;
if (status.latest_prediction) {
currentLocation = status.latest_prediction;
}

await hubService.heartbeat({
device_id: deviceId,
display_name: displayName,
location: currentLocation?.location ?? null,
confidence: currentLocation?.confidence ?? 0,
space_type: currentLocation?.location
? (spaces.find(s => s.name === currentLocation?.location)?.space_type ?? null)
: null,
}).catch(() => { hubConnected = false; });

try {
const usersRes = await hubService.getUsers();
hubUsers = usersRes.users;
hubConnected = true;
} catch {
hubConnected = false;
}
} catch (err) {
console.error('Hub poll error:', err);
}
}

function startPolling() {
if (pollInterval) return;
pollInterval = setInterval(poll, HUB_POLL_INTERVAL_MS);
}
function stopPolling() {
if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

onMount(async () => {
deviceId = getDeviceId();
displayName = getDisplayName();
hubUrl = hubService.hubUrl;
await loadData();
await hubService.heartbeat({
device_id: deviceId,
display_name: displayName,
location: currentLocation?.location ?? null,
confidence: currentLocation?.confidence ?? 0,
space_type: null,
}).catch(() => {});
startPolling();
});

onDestroy(() => {
stopPolling();
hubService.leave(deviceId).catch(() => {});
});
</script>

<div class="mx-auto w-full max-w-5xl space-y-8">
<!-- ═══════ Header ═══════ -->
<div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-700 p-8 text-white shadow-xl shadow-purple-500/20">
<div class="pointer-events-none absolute -top-20 -right-20 size-64 rounded-full bg-white/10 blur-3xl"></div>
<div class="pointer-events-none absolute -bottom-16 -left-16 size-48 rounded-full bg-indigo-400/20 blur-3xl"></div>

<div class="relative flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
<div class="space-y-2">
<div class="flex items-center gap-2">
<Users class="size-5 text-purple-200" />
<span class="text-sm font-medium text-purple-200">Hub en tiempo real</span>
</div>
<h1 class="text-3xl font-bold tracking-tight sm:text-4xl">Hub de ubicaciones</h1>
<p class="max-w-md text-purple-100/80">
Visualiza dónde está cada persona. Todos los dispositivos conectados al mismo hub comparten ubicación en tiempo real.
</p>
</div>

<!-- Device identity + Hub config -->
<div class="flex flex-col gap-2">
<!-- Your name -->
<div class="flex items-center gap-3 rounded-xl bg-white/10 p-3 backdrop-blur-sm">
<div class={`flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white ${getAvatarColor(deviceId)}`}>
{getInitials(displayName)}
</div>
<div class="min-w-0">
<p class="text-xs text-purple-200">Tu nombre</p>
{#if editingName}
<div class="flex items-center gap-1">
<input
class="w-28 rounded bg-white/20 px-1.5 py-0.5 text-sm text-white placeholder-white/50 outline-none"
bind:value={nameInput}
onkeydown={(e) => { if (e.key === 'Enter') confirmEditName(); if (e.key === 'Escape') cancelEditName(); }}
/>
<button onclick={confirmEditName} class="rounded p-0.5 hover:bg-white/20"><Check class="size-3.5" /></button>
<button onclick={cancelEditName} class="rounded p-0.5 hover:bg-white/20"><X class="size-3.5" /></button>
</div>
{:else}
<button class="flex items-center gap-1 text-sm font-medium" onclick={startEditName}>
{displayName}
<Edit3 class="size-3 text-purple-200" />
</button>
{/if}
</div>
</div>
<!-- Hub server URL -->
<div class="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 backdrop-blur-sm">
<Link class="size-4 shrink-0 text-purple-200" />
<div class="min-w-0 flex-1">
<p class="text-xs text-purple-200">Hub server</p>
{#if editingUrl}
<div class="flex items-center gap-1">
<input
class="w-44 rounded bg-white/20 px-1.5 py-0.5 text-xs text-white placeholder-white/50 outline-none"
bind:value={urlInput}
placeholder="http://192.168.1.X:8000"
onkeydown={(e) => { if (e.key === 'Enter') confirmEditUrl(); if (e.key === 'Escape') cancelEditUrl(); }}
/>
<button onclick={confirmEditUrl} class="rounded p-0.5 hover:bg-white/20"><Check class="size-3.5" /></button>
<button onclick={cancelEditUrl} class="rounded p-0.5 hover:bg-white/20"><X class="size-3.5" /></button>
</div>
{:else}
<button class="flex items-center gap-1 text-xs font-medium" onclick={startEditUrl}>
<span class="max-w-40 truncate">{hubUrl}</span>
<Edit3 class="size-3 text-purple-200" />
</button>
{/if}
</div>
{#if hubConnected}
<span class="relative flex size-2">
<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
<span class="relative inline-flex size-2 rounded-full bg-emerald-400"></span>
</span>
{:else}
<span class="size-2 rounded-full bg-red-400"></span>
{/if}
</div>
</div>
</div>
</div>

<!-- ═══════ Connected Users Counter ═══════ -->
<div class="flex flex-wrap items-center gap-3">
<div class="flex size-8 items-center justify-center rounded-lg bg-primary/10">
<Users class="size-4 text-primary" />
</div>
<h2 class="text-xl font-semibold">Espacios</h2>
{#if hubConnected}
<Badge variant="secondary" class="text-xs">{hubUsers.length} {hubUsers.length === 1 ? 'usuario' : 'usuarios'}</Badge>
{/if}
{#if trackingActive}
<span class="relative ml-1 flex size-2.5">
<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
<span class="relative inline-flex size-2.5 rounded-full bg-emerald-500"></span>
</span>
<Badge variant="secondary" class="text-xs font-normal">Tracking activo</Badge>
{:else}
<Badge variant="outline" class="text-xs font-normal">Tracking inactivo — inicia en el Dashboard</Badge>
{/if}
{#if !hubConnected && !loading}
<Badge variant="outline" class="gap-1 border-red-300 text-xs text-red-500">
<span class="size-1.5 rounded-full bg-red-400"></span>
Hub desconectado
</Badge>
{/if}
</div>

<!-- ═══════ Spaces Grid ═══════ -->
{#if loading}
<div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
{#each [1, 2, 3] as _}
<Card.Root class="overflow-hidden">
<Card.Header class="pb-3">
<div class="flex items-center gap-3">
<div class="size-10 animate-pulse rounded-xl bg-muted"></div>
<div class="space-y-1.5">
<div class="h-5 w-28 animate-pulse rounded-md bg-muted"></div>
<div class="h-3 w-16 animate-pulse rounded-md bg-muted"></div>
</div>
</div>
</Card.Header>
<Card.Content>
<div class="flex gap-2">
<div class="size-9 animate-pulse rounded-full bg-muted"></div>
<div class="size-9 animate-pulse rounded-full bg-muted"></div>
</div>
</Card.Content>
</Card.Root>
{/each}
</div>
{:else}
{@const rooms = buildRooms()}
{#if rooms.length === 0}
<Card.Root class="border-dashed">
<Card.Content class="flex flex-col items-center justify-center py-16">
<div class="mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
<MapPin class="size-8 text-primary" />
</div>
<p class="text-lg font-semibold">No hay espacios</p>
<p class="mb-4 max-w-sm text-center text-sm text-muted-foreground">
Registra espacios en el Dashboard para verlos aquí. Inicia tracking para que tu ubicación aparezca.
</p>
<Button href="/" class="gap-2">Ir al Dashboard</Button>
</Card.Content>
</Card.Root>
{:else}
<div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
{#each rooms as room}
{@const SpaceIcon = getSpaceIcon(room.space_type)}
{@const isMySpace = currentLocation?.location === room.name}
<Card.Root class={`group relative overflow-hidden transition-all duration-300 hover:shadow-lg ${isMySpace ? 'border-emerald-500/40 shadow-lg shadow-emerald-500/10 ring-1 ring-emerald-500/20' : ''}`}>
{#if isMySpace}
<div class="pointer-events-none absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent"></div>
{/if}

<Card.Header class="relative pb-3">
<div class="flex items-center justify-between">
<div class="flex items-center gap-3">
<div class={`flex size-11 items-center justify-center rounded-xl transition-colors ${isMySpace ? 'bg-emerald-500/15' : 'bg-muted'}`}>
<SpaceIcon class={`size-6 ${isMySpace ? 'text-emerald-500' : 'text-muted-foreground'}`} />
</div>
<div>
<Card.Title class="text-base">{room.name}</Card.Title>
<p class="text-xs text-muted-foreground">{getSpaceLabel(room.space_type)}</p>
</div>
</div>
<div class="flex items-center gap-1.5">
{#if room.users.length > 0}
<Badge variant="secondary" class="text-xs">
<User class="mr-1 size-3" />
{room.users.length}
</Badge>
{/if}
{#if isMySpace}
<Badge class="gap-1 bg-emerald-600 text-white">
<span class="relative flex size-1.5">
<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75"></span>
<span class="relative inline-flex size-1.5 rounded-full bg-white"></span>
</span>
Tú
</Badge>
{/if}
</div>
</div>
</Card.Header>

<Separator />

<Card.Content class="relative pt-4">
{#if room.users.length === 0}
<div class="flex h-16 items-center justify-center">
<p class="text-sm text-muted-foreground/60">Sin personas</p>
</div>
{:else}
<div class="flex flex-wrap gap-3">
{#each room.users as user}
{@const isMe = user.device_id === deviceId}
<div class="flex flex-col items-center gap-1.5" title="{user.display_name} — {formatConfidence(user.confidence)} confianza">
<div class="relative">
<div class={`flex size-11 items-center justify-center rounded-full text-xs font-bold text-white shadow-md ${getAvatarColor(user.device_id)} ${isMe ? 'ring-2 ring-emerald-400 ring-offset-2 ring-offset-background' : ''}`}>
{getInitials(user.display_name)}
</div>
{#if isMe}
<span class="absolute -right-0.5 -bottom-0.5 flex size-3.5 items-center justify-center rounded-full bg-emerald-500 text-[8px] text-white ring-2 ring-background">✓</span>
{/if}
</div>
<span class="max-w-16 truncate text-[11px] text-muted-foreground {isMe ? 'font-medium text-foreground' : ''}">
{isMe ? 'Tú' : user.display_name}
</span>
</div>
{/each}
</div>
{/if}
</Card.Content>
</Card.Root>
{/each}
</div>
{/if}

<!-- Unlocated users -->
{@const unlocated = getUnlocatedUsers()}
{#if unlocated.length > 0}
<Card.Root class="border-dashed">
<Card.Header class="pb-2">
<div class="flex items-center gap-2">
<Radio class="size-4 text-muted-foreground" />
<Card.Title class="text-sm font-medium">Sin ubicación detectada</Card.Title>
<Badge variant="outline" class="text-xs">{unlocated.length}</Badge>
</div>
</Card.Header>
<Card.Content>
<div class="flex flex-wrap gap-3">
{#each unlocated as user}
{@const isMe = user.device_id === deviceId}
<div class="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2">
<div class={`flex size-8 items-center justify-center rounded-full text-xs font-bold text-white ${getAvatarColor(user.device_id)}`}>
{getInitials(user.display_name)}
</div>
<span class="text-sm text-muted-foreground {isMe ? 'font-medium text-foreground' : ''}">
{isMe ? 'Tú' : user.display_name}
</span>
</div>
{/each}
</div>
</Card.Content>
</Card.Root>
{/if}
{/if}
</div>
