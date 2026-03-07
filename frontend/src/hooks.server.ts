import type { Handle } from '@sveltejs/kit';
import { authCookiesManager } from '$lib/server/cookies/manager';
import { AuthService } from '$lib/features/auth/services/auth';
import { createAuthHandler } from '$lib/server/hooks/auth';
