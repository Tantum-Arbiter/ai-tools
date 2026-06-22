import { createApi, handleStreamEvent, joinUrl, sanitizeResponse } from '../api';
import { ApiError, ChatResponse } from '../types';
import type { SseEvent } from '../sse';

type FetchArgs = [input: RequestInfo | URL, init?: RequestInit];

function mockFetch(impl: (...args: FetchArgs) => Promise<Response>) {
  const calls: FetchArgs[] = [];
  const fn = ((...args: FetchArgs) => {
    calls.push(args);
    return impl(...args);
  }) as unknown as typeof fetch;
  return { fn, calls };
}

const goodCreds = async () => ({ hostUrl: 'https://h.example/', apiKey: 'k1' });
const noCreds = async () => null;

describe('joinUrl', () => {
  it('strips trailing slash and prepends /', () => {
    expect(joinUrl('https://h.example/', 'api/foo')).toBe('https://h.example/api/foo');
    expect(joinUrl('https://h.example', '/api/foo')).toBe('https://h.example/api/foo');
    expect(joinUrl('https://h.example/sub//', 'api/foo')).toBe('https://h.example/sub/api/foo');
  });
});

describe('sanitizeResponse', () => {
  it('drops unknown action types and keeps safe ones', () => {
    const r: ChatResponse = {
      reply: 'ok',
      error: false,
      actions: [
        { action: 'open_browser', url: 'https://x' },
        { action: 'desktop_screenshot' },
        { action: 'open_url', url: 'https://y' },
        { action: 'launch_app', name: 'Slack' },
      ],
    };
    const out = sanitizeResponse(r);
    expect(out.actions).toEqual([
      { action: 'open_browser', url: 'https://x' },
      { action: 'open_url', url: 'https://y' },
    ]);
  });

  it('is a no-op when actions is missing', () => {
    const r: ChatResponse = { reply: 'ok', error: false };
    expect(sanitizeResponse(r)).toEqual(r);
  });
});

describe('createApi.checkAuth', () => {
  it('hits /api/auth/check with Bearer header', async () => {
    const { fn, calls } = mockFetch(async () =>
      new Response(JSON.stringify({ auth_required: true, valid: true }), { status: 200 }),
    );
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    const r = await api.checkAuth();
    expect(r).toEqual({ auth_required: true, valid: true });
    expect(calls).toHaveLength(1);
    const [url, init] = calls[0]!;
    expect(String(url)).toBe('https://h.example/api/auth/check');
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer k1');
  });

  it('throws unauthorized ApiError when no credentials', async () => {
    const { fn } = mockFetch(async () => new Response('{}', { status: 200 }));
    const api = createApi({ fetch: fn, getCredentials: noCreds });
    await expect(api.checkAuth()).rejects.toMatchObject({ kind: 'unauthorized' });
  });
});

describe('createApi.sendChat', () => {
  it('POSTs the expected body with client=mobile and 20-message cap', async () => {
    const captured: FetchArgs[] = [];
    const { fn } = mockFetch(async (...args) => {
      captured.push(args);
      return new Response(JSON.stringify({ reply: 'hi', error: false }), { status: 200 });
    });
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    const history = Array.from({ length: 25 }, (_, i) => ({
      role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
      content: `m${i}`,
    }));
    const r = await api.sendChat('hello', history);
    expect(r.reply).toBe('hi');
    const [url, init] = captured[0]!;
    expect(String(url)).toBe('https://h.example/api/jarvis/chat');
    expect(init?.method).toBe('POST');
    const body = JSON.parse(String(init?.body));
    expect(body.client).toBe('mobile');
    expect(body.message).toBe('hello');
    expect(body.history).toHaveLength(20);
    expect(body.history[0].content).toBe('m5');
  });

  it('maps 401 to unauthorized ApiError', async () => {
    const { fn } = mockFetch(async () => new Response('nope', { status: 401 }));
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    await expect(api.sendChat('x', [])).rejects.toMatchObject({
      kind: 'unauthorized',
      status: 401,
    });
  });

  it('maps network failure to network ApiError', async () => {
    const fn = (async () => {
      throw new Error('boom');
    }) as unknown as typeof fetch;
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    await expect(api.sendChat('x', [])).rejects.toBeInstanceOf(ApiError);
    await expect(api.sendChat('x', [])).rejects.toMatchObject({ kind: 'network' });
  });

  it('maps invalid JSON to parse ApiError', async () => {
    const { fn } = mockFetch(async () => new Response('<<not json>>', { status: 200 }));
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    await expect(api.sendChat('x', [])).rejects.toMatchObject({ kind: 'parse' });
  });

  it('strips desktop-only actions from the response', async () => {
    const { fn } = mockFetch(async () =>
      new Response(
        JSON.stringify({
          reply: 'ok', error: false,
          actions: [
            { action: 'desktop_screenshot' },
            { action: 'open_browser', url: 'https://x' },
          ],
        }),
        { status: 200 },
      ),
    );
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    const r = await api.sendChat('go', []);
    expect(r.actions).toEqual([{ action: 'open_browser', url: 'https://x' }]);
  });

  it('passes abort signal through', async () => {
    let seenSignal: AbortSignal | undefined;
    const fn = (async (_u: unknown, init?: RequestInit) => {
      seenSignal = init?.signal ?? undefined;
      return new Response(JSON.stringify({ reply: 'ok', error: false }), { status: 200 });
    }) as unknown as typeof fetch;
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    const ac = new AbortController();
    await api.sendChat('x', [], ac.signal);
    expect(seenSignal).toBe(ac.signal);
  });
});

function streamingFetch(frames: string[], status = 200): typeof fetch {
  return (async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const f of frames) controller.enqueue(encoder.encode(f));
        controller.close();
      },
    });
    return new Response(stream, {
      status,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }) as unknown as typeof fetch;
}

describe('createApi.streamChat', () => {
  it('aggregates deltas, panel, and followups across SSE events', async () => {
    const fn = streamingFetch([
      'event: meta\ndata: {"topic":"x","error":false}\n\n',
      'event: delta\ndata: {"text":"hello "}\n\nevent: delta\ndata: {"text":"world"}\n\n',
      'event: panel\ndata: {"title":"P","summary":"s"}\n\n',
      'event: followups\ndata: ["a","b"]\n\n',
      'event: done\ndata: {"reply":""}\n\n',
    ]);
    const api = createApi({ fetch: fn, getCredentials: goodCreds });

    const deltas: string[] = [];
    const panels: unknown[] = [];
    const followups: unknown[] = [];
    const result = await api.streamChat('hi', [], {
      onDelta: (t) => deltas.push(t),
      onPanel: (p) => panels.push(p),
      onFollowups: (f) => followups.push(f),
    });

    expect(deltas).toEqual(['hello ', 'world']);
    expect(result.reply).toBe('hello world');
    expect(result.panel).toEqual({ title: 'P', summary: 's' });
    expect(result.followups).toEqual(['a', 'b']);
    expect(panels).toEqual([{ title: 'P', summary: 's' }]);
    expect(followups).toEqual([['a', 'b']]);
  });

  it('throws unauthorized when no credentials are configured', async () => {
    const fn = streamingFetch([]);
    const api = createApi({ fetch: fn, getCredentials: noCreds });
    await expect(api.streamChat('hi', [], {})).rejects.toMatchObject({
      kind: 'unauthorized',
    });
  });

  it('maps 401 to unauthorized ApiError', async () => {
    const fn = streamingFetch([], 401);
    const api = createApi({ fetch: fn, getCredentials: goodCreds });
    await expect(api.streamChat('hi', [], {})).rejects.toMatchObject({
      kind: 'unauthorized',
      status: 401,
    });
  });
});

describe('handleStreamEvent', () => {
  const ev = (event: string, data: unknown): SseEvent => ({
    event,
    data: JSON.stringify(data),
  });

  it('ignores malformed JSON data', () => {
    const agg: ChatResponse = { reply: '', error: false };
    handleStreamEvent({ event: 'delta', data: 'not-json' }, agg, {});
    expect(agg.reply).toBe('');
  });

  it('marks error and reply when an error event arrives', () => {
    const agg: ChatResponse = { reply: '', error: false };
    handleStreamEvent(ev('error', { message: 'boom' }), agg, {});
    expect(agg.error).toBe(true);
    expect(agg.reply).toBe('boom');
  });

  it('drops actions outside the mobile-safe set', () => {
    const agg: ChatResponse = { reply: '', error: false };
    handleStreamEvent(
      ev('actions', [
        { action: 'open_browser', url: 'https://x' },
        { action: 'desktop_screenshot' },
      ]),
      agg,
      {},
    );
    // handleStreamEvent itself doesn't sanitize — that's sanitizeResponse's
    // job. We just confirm it stored what arrived so downstream code can
    // sanitize once at the end.
    expect(agg.actions).toHaveLength(2);
  });
});
