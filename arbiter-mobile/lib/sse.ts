// Streaming SSE parser used by the mobile chat client.
//
// React Native does not ship a useful EventSource (the polyfills that exist
// either require XMLHttpRequest tricks or break with fetch streams). We sidestep
// the problem by consuming the response body as a ReadableStream of text and
// re-implementing the wire-format parser in line with the spec subset that
// arbiter-mission-control/chat_stream.py produces:
//
//   event: <name>
//   data: <json-or-text>
//   <blank line>
//
// Comment lines (lines starting with ":") are skipped — these are keepalives.

export interface SseEvent {
  event: string;
  data: string;
}

export function parseSseChunkBuffer(buffer: string): {
  events: SseEvent[];
  remainder: string;
} {
  // SSE frames are terminated by a blank line. Split on \n\n (we have already
  // normalised \r\n -> \n upstream). Anything after the last blank line is an
  // incomplete frame and goes back into the buffer.
  const events: SseEvent[] = [];
  let cursor = 0;
  while (true) {
    const nextBlank = buffer.indexOf('\n\n', cursor);
    if (nextBlank === -1) break;
    const frame = buffer.slice(cursor, nextBlank);
    cursor = nextBlank + 2;
    const parsed = parseSseFrame(frame);
    if (parsed) events.push(parsed);
  }
  return { events, remainder: buffer.slice(cursor) };
}

function parseSseFrame(frame: string): SseEvent | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.replace(/\r$/, '');
    if (line.length === 0) continue;
    if (line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const field = line.slice(0, colon);
    const value = line.slice(colon + 1).replace(/^ /, '');
    if (field === 'event') {
      event = value;
    } else if (field === 'data') {
      dataLines.push(value);
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

export interface SseConsumeDeps {
  fetch: typeof fetch;
}

export interface SseConsumeOptions {
  url: string;
  init: RequestInit;
  onEvent: (event: SseEvent) => void;
  signal?: AbortSignal;
}

export async function consumeSse(
  deps: SseConsumeDeps,
  opts: SseConsumeOptions,
): Promise<void> {
  const finalInit: RequestInit = { ...opts.init };
  if (opts.signal) finalInit.signal = opts.signal;
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    ...((finalInit.headers as Record<string, string>) ?? {}),
  };
  finalInit.headers = headers;

  const res = await deps.fetch(opts.url, finalInit);
  if (!res.ok) {
    throw new Error(`SSE request failed: ${res.status}`);
  }
  const body = res.body as ReadableStream<Uint8Array> | null | undefined;
  if (!body || typeof body.getReader !== 'function') {
    const fallback = await res.text();
    drainBuffer(fallback, opts.onEvent);
    return;
  }
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      const { events, remainder } = parseSseChunkBuffer(buffer);
      buffer = remainder;
      for (const evt of events) opts.onEvent(evt);
    }
    buffer += decoder.decode();
    drainBuffer(buffer, opts.onEvent);
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // releaseLock can throw if the reader was already cancelled; harmless.
    }
  }
}

function drainBuffer(buffer: string, onEvent: (e: SseEvent) => void): void {
  const trailing = buffer.endsWith('\n\n') ? buffer : buffer + '\n\n';
  const { events } = parseSseChunkBuffer(trailing);
  for (const evt of events) onEvent(evt);
}
