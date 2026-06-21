// Auth-aware HTTP client for the Arbiter Mission Control server.
// Pure dependency-injected factory: pass in `fetch` and a credential getter
// so tests can run in plain Node without RN/Expo runtime.

import {
  ApiError,
  AuthCheckResponse,
  ChatRequest,
  ChatResponse,
  HistoryEntry,
  MOBILE_SAFE_ACTIONS,
  VisionRequest,
  VisionResponse,
} from './types';

export interface Credentials {
  hostUrl: string; // e.g. https://laptop.tailXXXX.ts.net
  apiKey: string;
}

export interface ApiDeps {
  fetch: typeof fetch;
  getCredentials: () => Promise<Credentials | null>;
}

export interface ArbiterApi {
  checkAuth(): Promise<AuthCheckResponse>;
  sendChat(message: string, history: HistoryEntry[], signal?: AbortSignal): Promise<ChatResponse>;
  sendVision(req: VisionRequest, signal?: AbortSignal): Promise<VisionResponse>;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' } as const;

export function createApi(deps: ApiDeps): ArbiterApi {
  async function authedRequest<T>(
    path: string,
    init: RequestInit,
  ): Promise<T> {
    const creds = await deps.getCredentials();
    if (!creds) {
      throw new ApiError('Not configured — set host URL and API key', 0, 'unauthorized');
    }
    const url = joinUrl(creds.hostUrl, path);
    const headers: Record<string, string> = {
      ...JSON_HEADERS,
      Authorization: `Bearer ${creds.apiKey}`,
      ...(init.headers as Record<string, string> | undefined),
    };

    let res: Response;
    try {
      res = await deps.fetch(url, { ...init, headers });
    } catch (err) {
      throw new ApiError(
        `Network error: ${(err as Error).message}`,
        0,
        'network',
      );
    }

    if (res.status === 401) {
      throw new ApiError('Unauthorized — API key rejected', 401, 'unauthorized');
    }
    if (!res.ok) {
      throw new ApiError(`Server error ${res.status}`, res.status, 'server');
    }

    try {
      return (await res.json()) as T;
    } catch {
      throw new ApiError('Invalid JSON in response', res.status, 'parse');
    }
  }

  return {
    async checkAuth() {
      // /api/auth/check is the only API endpoint that bypasses the bearer
      // requirement — but the server still inspects the supplied key to
      // tell us whether it is valid.
      const creds = await deps.getCredentials();
      if (!creds) {
        throw new ApiError('Not configured', 0, 'unauthorized');
      }
      const url = joinUrl(creds.hostUrl, '/api/auth/check');
      const res = await deps.fetch(url, {
        headers: { Authorization: `Bearer ${creds.apiKey}` },
      });
      if (!res.ok) {
        throw new ApiError(`auth/check failed: ${res.status}`, res.status, 'server');
      }
      return (await res.json()) as AuthCheckResponse;
    },

    async sendChat(message, history, signal) {
      const body: ChatRequest = {
        message,
        history: history.slice(-20), // mirror server-side cap
        client: 'mobile',
      };
      const init: RequestInit = {
        method: 'POST',
        body: JSON.stringify(body),
      };
      if (signal) init.signal = signal;
      const raw = await authedRequest<ChatResponse>('/api/jarvis/chat', init);
      return sanitizeResponse(raw);
    },

    async sendVision(req, signal) {
      const init: RequestInit = {
        method: 'POST',
        body: JSON.stringify(req),
      };
      if (signal) init.signal = signal;
      const raw = await authedRequest<VisionResponse>('/api/jarvis/vision', init);
      return sanitizeResponse(raw);
    },
  };
}

// ── Helpers ─────────────────────────────────────────────────────────

export function joinUrl(host: string, path: string): string {
  const h = host.replace(/\/+$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${h}${p}`;
}

// Drop any action types we don't render natively. Belt-and-braces alongside
// the server-side client=="mobile" gate.
export function sanitizeResponse<T extends { actions?: { action: string }[] }>(r: T): T {
  if (!r.actions || !Array.isArray(r.actions)) return r;
  const filtered = r.actions.filter((a) => MOBILE_SAFE_ACTIONS.has(a.action));
  return { ...r, actions: filtered };
}
