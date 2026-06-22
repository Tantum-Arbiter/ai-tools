// Auth-aware HTTP client for the Arbiter Mission Control server.
// Pure dependency-injected factory: pass in `fetch` and a credential getter
// so tests can run in plain Node without RN/Expo runtime.

import { consumeSse, type SseEvent } from './sse';
import {
  Action,
  ApiError,
  AuthCheckResponse,
  ChatRequest,
  ChatResponse,
  HistoryEntry,
  MOBILE_SAFE_ACTIONS,
  Panel,
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

export interface StreamChatHandlers {
  onMeta?: (m: { topic: string | null; error: boolean }) => void;
  onDelta?: (text: string) => void;
  onPanel?: (panel: Panel) => void;
  onActions?: (actions: Action[]) => void;
  onFollowups?: (followups: string[]) => void;
}

export interface ArbiterApi {
  checkAuth(): Promise<AuthCheckResponse>;
  sendChat(message: string, history: HistoryEntry[], signal?: AbortSignal): Promise<ChatResponse>;
  streamChat(
    message: string,
    history: HistoryEntry[],
    handlers: StreamChatHandlers,
    signal?: AbortSignal,
  ): Promise<ChatResponse>;
  sendVision(req: VisionRequest, signal?: AbortSignal): Promise<VisionResponse>;
  getRevenueSummary(signal?: AbortSignal): Promise<unknown>;
  getSystemStatus(signal?: AbortSignal): Promise<unknown>;
  getGcpSummary(signal?: AbortSignal): Promise<unknown>;
  getAgents(signal?: AbortSignal): Promise<unknown>;
  getCeoAgents(signal?: AbortSignal): Promise<unknown>;
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

    async streamChat(message, history, handlers, signal) {
      const creds = await deps.getCredentials();
      if (!creds) {
        throw new ApiError('Not configured — set host URL and API key', 0, 'unauthorized');
      }
      const url = joinUrl(creds.hostUrl, '/api/jarvis/chat/stream');
      const body: ChatRequest = {
        message,
        history: history.slice(-20),
        client: 'mobile',
      };
      const aggregate: ChatResponse = { reply: '', error: false };
      try {
        await consumeSse(
          { fetch: deps.fetch },
          {
            url,
            init: {
              method: 'POST',
              body: JSON.stringify(body),
              headers: {
                ...JSON_HEADERS,
                Authorization: `Bearer ${creds.apiKey}`,
              },
            },
            ...(signal ? { signal } : {}),
            onEvent: (evt) => handleStreamEvent(evt, aggregate, handlers),
          },
        );
      } catch (err) {
        if (err instanceof ApiError) throw err;
        const msg = err instanceof Error ? err.message : 'stream failed';
        if (/401/.test(msg)) {
          throw new ApiError('Unauthorized — API key rejected', 401, 'unauthorized');
        }
        throw new ApiError(`Stream error: ${msg}`, 0, 'network');
      }
      return sanitizeResponse(aggregate);
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

    async getRevenueSummary(signal) {
      const init: RequestInit = { method: 'GET' };
      if (signal) init.signal = signal;
      return authedRequest<unknown>('/api/revenue/summary', init);
    },

    async getSystemStatus(signal) {
      const init: RequestInit = { method: 'GET' };
      if (signal) init.signal = signal;
      return authedRequest<unknown>('/api/status', init);
    },

    async getGcpSummary(signal) {
      const init: RequestInit = { method: 'GET' };
      if (signal) init.signal = signal;
      return authedRequest<unknown>('/api/gcp/summary', init);
    },

    async getAgents(signal) {
      const init: RequestInit = { method: 'GET' };
      if (signal) init.signal = signal;
      return authedRequest<unknown>('/api/agents', init);
    },

    async getCeoAgents(signal) {
      const init: RequestInit = { method: 'GET' };
      if (signal) init.signal = signal;
      return authedRequest<unknown>('/api/ceo/agents', init);
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

export function handleStreamEvent(
  evt: SseEvent,
  aggregate: ChatResponse,
  handlers: StreamChatHandlers,
): void {
  let data: unknown;
  try {
    data = JSON.parse(evt.data);
  } catch {
    return;
  }
  switch (evt.event) {
    case 'meta': {
      const m = data as { topic?: string | null; error?: boolean };
      if (m.error) aggregate.error = true;
      handlers.onMeta?.({ topic: m.topic ?? null, error: !!m.error });
      return;
    }
    case 'delta': {
      const d = data as { text?: string };
      const text = typeof d.text === 'string' ? d.text : '';
      if (!text) return;
      aggregate.reply += text;
      handlers.onDelta?.(text);
      return;
    }
    case 'panel': {
      aggregate.panel = data as Panel;
      handlers.onPanel?.(aggregate.panel);
      return;
    }
    case 'actions': {
      if (Array.isArray(data)) {
        aggregate.actions = data as Action[];
        handlers.onActions?.(aggregate.actions);
      }
      return;
    }
    case 'followups': {
      if (Array.isArray(data)) {
        aggregate.followups = (data as unknown[]).filter(
          (s): s is string => typeof s === 'string',
        );
        handlers.onFollowups?.(aggregate.followups);
      }
      return;
    }
    case 'error': {
      const e = data as { message?: string };
      aggregate.error = true;
      aggregate.reply = aggregate.reply || e.message || 'stream error';
      return;
    }
    case 'done': {
      const d = data as { reply?: string; error?: boolean };
      if (typeof d.reply === 'string' && d.reply && !aggregate.reply) {
        aggregate.reply = d.reply;
      }
      if (d.error) aggregate.error = true;
      return;
    }
    default:
      return;
  }
}
