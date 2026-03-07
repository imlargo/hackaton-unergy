<script lang="ts">
	import LoginForm from '$lib/features/auth/components/login/login-form.svelte';
	import { Zap } from '@lucide/svelte';
</script>

<div class="grid min-h-svh lg:grid-cols-2">
	<div class="flex flex-col gap-4 p-6 md:p-10">
		<div class="flex justify-center gap-2 md:justify-start">
			<a href="/" class="flex items-center gap-2.5 font-medium">
				<div
					class="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm"
				>
					<Zap class="size-4" />
				</div>
				<span class="text-lg font-bold tracking-tight">Unergy</span>
			</a>
		</div>
		<div class="flex flex-1 items-center justify-center">
			<div class="w-full max-w-xs">
				<LoginForm />
			</div>
		</div>
	</div>
	<div class="relative hidden items-center justify-center overflow-hidden bg-gradient-to-br from-primary via-primary/90 to-purple-700 lg:flex">
		<!-- Decorative blurs -->
		<div class="pointer-events-none absolute -top-32 -right-32 size-96 rounded-full bg-white/10 blur-3xl"></div>
		<div class="pointer-events-none absolute -bottom-24 -left-24 size-72 rounded-full bg-purple-400/20 blur-3xl"></div>
		<div class="pointer-events-none absolute top-1/2 left-1/2 size-48 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/5 blur-2xl"></div>
		<div class="relative flex flex-col items-center gap-6 text-white">
			<div class="flex size-20 items-center justify-center rounded-2xl border border-white/20 bg-white/10 backdrop-blur-sm">
				<Zap class="size-10" />
			</div>
			<div class="text-center">
				<h2 class="text-3xl font-bold tracking-tight">Unergy</h2>
				<p class="mt-2 max-w-xs text-purple-100/80">Posicionamiento WiFi inteligente para tu hogar</p>
			</div>
		</div>
	</div>
</div>
