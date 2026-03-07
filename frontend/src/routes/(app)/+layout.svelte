<script lang="ts">
	import type { LayoutProps } from './$types';
	import { Zap, MapPin, LayoutDashboard } from '@lucide/svelte';
	let { data, children }: LayoutProps = $props();
</script>

<!-- Top Navigation -->
<nav class="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl">
	<div class="mx-auto flex h-14 max-w-5xl items-center justify-between px-4 md:px-12 xl:px-24">
		<a href="/" class="flex items-center gap-2.5 transition-opacity hover:opacity-80">
			<div class="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
				<Zap class="size-4" />
			</div>
			<span class="text-lg font-bold tracking-tight">Unergy</span>
		</a>
		<div class="flex items-center gap-1">
			<a href="/" class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
				<LayoutDashboard class="size-3.5" />
				Dashboard
			</a>
			<a href="/" class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
				<MapPin class="size-3.5" />
				Espacios
			</a>
		</div>
	</div>
</nav>

<div class="flex w-full flex-col gap-y-6 px-4 pt-8 pb-24 md:px-12 md:pb-12 xl:px-24">
	{@render children()}
</div>
