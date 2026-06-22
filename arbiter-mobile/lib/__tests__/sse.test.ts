import { consumeSse, parseSseChunkBuffer, type SseEvent } from '../sse';

describe('parseSseChunkBuffer', () => {
  it('returns no events for empty buffer', () => {
    expect(parseSseChunkBuffer('')).toEqual({ events: [], remainder: '' });
  });

  it('parses a single complete frame', () => {
    const buf = 'event: delta\ndata: {"text":"hi"}\n\n';

    const { events, remainder } = parseSseChunkBuffer(buf);

    expect(remainder).toBe('');
    expect(events).toEqual([{ event: 'delta', data: '{"text":"hi"}' }]);
  });

  it('parses multiple frames in one call', () => {
    const buf =
      'event: meta\ndata: {"topic":null}\n\n' +
      'event: delta\ndata: {"text":"a"}\n\n' +
      'event: delta\ndata: {"text":"b"}\n\n';

    const { events, remainder } = parseSseChunkBuffer(buf);

    expect(remainder).toBe('');
    expect(events.map((e) => e.event)).toEqual(['meta', 'delta', 'delta']);
  });

  it('holds back partial frame in remainder', () => {
    const buf = 'event: delta\ndata: {"text":"done"}\n\nevent: panel\ndata: {"x":';

    const { events, remainder } = parseSseChunkBuffer(buf);

    expect(events).toHaveLength(1);
    expect(remainder).toBe('event: panel\ndata: {"x":');
  });

  it('skips comment (keepalive) lines', () => {
    const buf = ': keepalive\n\nevent: ping\ndata: {}\n\n';

    const { events } = parseSseChunkBuffer(buf);

    expect(events).toEqual([{ event: 'ping', data: '{}' }]);
  });

  it('defaults event name to message when omitted', () => {
    const buf = 'data: bare\n\n';

    const { events } = parseSseChunkBuffer(buf);

    expect(events).toEqual([{ event: 'message', data: 'bare' }]);
  });
});

describe('consumeSse', () => {
  // Build a fetch stub whose response.body is a ReadableStream over the
  // supplied byte chunks. Lets us simulate progressive deltas without a real
  // socket.
  function makeStreamingFetch(chunks: string[], status = 200): typeof fetch {
    return (async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
          controller.close();
        },
      });
      return new Response(stream, { status, headers: { 'Content-Type': 'text/event-stream' } });
    }) as unknown as typeof fetch;
  }

  it('emits events progressively across chunk boundaries', async () => {
    const fetchStub = makeStreamingFetch([
      'event: meta\ndata: {"topic":"x"}\n\nevent: del',
      'ta\ndata: {"text":"hello"}\n\n',
      'event: done\ndata: {"reply":"hello"}\n\n',
    ]);
    const events: SseEvent[] = [];

    await consumeSse({ fetch: fetchStub }, {
      url: 'https://example.com/stream',
      init: { method: 'POST' },
      onEvent: (e) => events.push(e),
    });

    expect(events.map((e) => e.event)).toEqual(['meta', 'delta', 'done']);
  });

  it('throws on non-OK status', async () => {
    const fetchStub = makeStreamingFetch([], 401);

    await expect(
      consumeSse({ fetch: fetchStub }, {
        url: 'https://example.com/stream',
        init: { method: 'POST' },
        onEvent: () => undefined,
      }),
    ).rejects.toThrow('SSE request failed: 401');
  });

  it('drains a buffer with no trailing blank line', async () => {
    const fetchStub = makeStreamingFetch([
      'event: meta\ndata: {}\n\nevent: done\ndata: {"reply":""}',
    ]);
    const events: SseEvent[] = [];

    await consumeSse({ fetch: fetchStub }, {
      url: 'https://example.com/stream',
      init: { method: 'POST' },
      onEvent: (e) => events.push(e),
    });

    expect(events.map((e) => e.event)).toEqual(['meta', 'done']);
  });
});
