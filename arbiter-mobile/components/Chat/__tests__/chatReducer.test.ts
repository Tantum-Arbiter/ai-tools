import {
  chatReducer,
  INITIAL_STATE,
  HISTORY_CAP,
  canSend,
  toHistoryEntries,
  type ChatState,
  type ChatMessage,
} from '../chatReducer';

const mk = (over: Partial<ChatState> = {}): ChatState => ({ ...INITIAL_STATE, ...over });

describe('chatReducer — input', () => {
  it('updates input text', () => {
    const s = chatReducer(mk(), { type: 'INPUT_CHANGED', value: 'hello' });
    expect(s.input).toBe('hello');
  });

  it('preserves other fields when input changes', () => {
    const s = chatReducer(mk({ expanded: true }), { type: 'INPUT_CHANGED', value: 'x' });
    expect(s.expanded).toBe(true);
  });
});

describe('chatReducer — drawer', () => {
  it('toggles the expanded flag', () => {
    const a = chatReducer(mk(), { type: 'TOGGLE_EXPANDED' });
    expect(a.expanded).toBe(true);
    const b = chatReducer(a, { type: 'TOGGLE_EXPANDED' });
    expect(b.expanded).toBe(false);
  });

  it('sets expanded explicitly', () => {
    const s = chatReducer(mk({ expanded: true }), { type: 'SET_EXPANDED', expanded: false });
    expect(s.expanded).toBe(false);
  });
});

describe('chatReducer — SEND_REQUESTED', () => {
  const send = (s: ChatState) =>
    chatReducer(s, { type: 'SEND_REQUESTED', id: 'u1', assistantId: 'a1', timestamp: 100 });

  it('pushes user message + pending assistant placeholder', () => {
    const s = send(mk({ input: ' hello world ' }));
    expect(s.messages).toHaveLength(2);
    expect(s.messages[0]).toMatchObject({ id: 'u1', role: 'user', text: 'hello world' });
    expect(s.messages[1]).toMatchObject({ id: 'a1', role: 'assistant', text: '', pending: true });
  });

  it('clears input, marks sending, expands the drawer, clears prior error', () => {
    const s = send(mk({ input: 'hi', lastError: 'old' }));
    expect(s.input).toBe('');
    expect(s.sending).toBe(true);
    expect(s.expanded).toBe(true);
    expect(s.lastError).toBeNull();
  });

  it('is a no-op when input is empty or whitespace', () => {
    expect(send(mk({ input: '' }))).toEqual(mk({ input: '' }));
    expect(send(mk({ input: '   ' }))).toEqual(mk({ input: '   ' }));
  });

  it('is a no-op when already sending (prevents double-send)', () => {
    const s = mk({ input: 'hi', sending: true });
    expect(send(s)).toEqual(s);
  });

  it('uses action.text when provided and leaves typed input untouched', () => {
    const s = chatReducer(
      mk({ input: 'typing this' }),
      { type: 'SEND_REQUESTED', id: 'u1', assistantId: 'a1', timestamp: 0, text: 'pick me' },
    );
    expect(s.messages[0]).toMatchObject({ role: 'user', text: 'pick me' });
    expect(s.input).toBe('typing this');
  });

  it('sends with action.text even when state.input is empty', () => {
    const s = chatReducer(
      mk({ input: '' }),
      { type: 'SEND_REQUESTED', id: 'u1', assistantId: 'a1', timestamp: 0, text: 'why?' },
    );
    expect(s.messages).toHaveLength(2);
    expect(s.messages[0]).toMatchObject({ text: 'why?' });
  });
});

describe('chatReducer — FOLLOWUPS_CLEARED', () => {
  const seeded: ChatState = mk({
    messages: [
      {
        id: 'a1',
        role: 'assistant',
        text: 'hi',
        timestamp: 0,
        followups: ['why?', 'how?'],
      },
    ],
  });

  it('drops the followups array from the targeted message', () => {
    const s = chatReducer(seeded, { type: 'FOLLOWUPS_CLEARED', messageId: 'a1' });
    expect(s.messages[0]!.followups).toBeUndefined();
    expect(s.messages[0]!.text).toBe('hi');
  });

  it('is a no-op for an unknown messageId', () => {
    const s = chatReducer(seeded, { type: 'FOLLOWUPS_CLEARED', messageId: 'zzz' });
    expect(s).toEqual(seeded);
  });
});

describe('chatReducer — SEND_SUCCEEDED', () => {
  const sent = chatReducer(
    mk({ input: 'hi' }),
    { type: 'SEND_REQUESTED', id: 'u1', assistantId: 'a1', timestamp: 0 },
  );

  it('fills in the assistant message text + panel + actions + followups', () => {
    const s = chatReducer(sent, {
      type: 'SEND_SUCCEEDED',
      assistantId: 'a1',
      reply: 'pong',
      panel: { title: 'P' },
      actions: [{ action: 'open_url', url: 'https://x' }],
      followups: ['why?'],
    });
    const ass = s.messages.find((m) => m.id === 'a1')!;
    expect(ass.text).toBe('pong');
    expect(ass.pending).toBe(false);
    expect(ass.panel).toEqual({ title: 'P' });
    expect(ass.actions).toHaveLength(1);
    expect(ass.followups).toEqual(['why?']);
    expect(s.sending).toBe(false);
  });

  it('ignores success for an unknown assistantId (leaves state untouched)', () => {
    const s = chatReducer(sent, { type: 'SEND_SUCCEEDED', assistantId: 'zzz', reply: 'x' });
    expect(s.messages).toEqual(sent.messages);
    // sending still flips off — host owns lifecycle
    expect(s.sending).toBe(false);
  });
});

describe('chatReducer — SEND_FAILED', () => {
  const sent = chatReducer(
    mk({ input: 'hi' }),
    { type: 'SEND_REQUESTED', id: 'u1', assistantId: 'a1', timestamp: 0 },
  );

  it('marks the assistant message as errored and records lastError', () => {
    const s = chatReducer(sent, { type: 'SEND_FAILED', assistantId: 'a1', error: 'offline' });
    const ass = s.messages.find((m) => m.id === 'a1')!;
    expect(ass.error).toBe(true);
    expect(ass.text).toBe('offline');
    expect(ass.pending).toBe(false);
    expect(s.sending).toBe(false);
    expect(s.lastError).toBe('offline');
  });

  it('ERROR_DISMISSED clears lastError without touching messages', () => {
    const failed = chatReducer(sent, { type: 'SEND_FAILED', assistantId: 'a1', error: 'x' });
    const s = chatReducer(failed, { type: 'ERROR_DISMISSED' });
    expect(s.lastError).toBeNull();
    expect(s.messages).toEqual(failed.messages);
  });
});

describe('chatReducer — history', () => {
  it('HISTORY_LOADED replaces messages and caps to HISTORY_CAP', () => {
    const big: ChatMessage[] = Array.from({ length: HISTORY_CAP + 50 }, (_, i) => ({
      id: `m${i}`, role: i % 2 === 0 ? 'user' : 'assistant', text: String(i), timestamp: i,
    }));
    const s = chatReducer(mk(), { type: 'HISTORY_LOADED', messages: big });
    expect(s.messages).toHaveLength(HISTORY_CAP);
    expect(s.messages[0]!.id).toBe(`m50`);
  });

  it('CLEAR_HISTORY empties messages and resets sending/error', () => {
    const seed: ChatMessage[] = [{ id: 'a', role: 'user', text: 'x', timestamp: 0 }];
    const s = chatReducer(mk({ messages: seed, sending: true, lastError: 'oops' }), { type: 'CLEAR_HISTORY' });
    expect(s.messages).toEqual([]);
    expect(s.sending).toBe(false);
    expect(s.lastError).toBeNull();
  });

  it('SEND_REQUESTED caps after push beyond limit', () => {
    const big: ChatMessage[] = Array.from({ length: HISTORY_CAP }, (_, i) => ({
      id: `m${i}`, role: 'user', text: String(i), timestamp: i,
    }));
    const s = chatReducer(
      mk({ messages: big, input: 'next' }),
      { type: 'SEND_REQUESTED', id: 'u', assistantId: 'a', timestamp: 1 },
    );
    expect(s.messages).toHaveLength(HISTORY_CAP);
    expect(s.messages[s.messages.length - 1]!.id).toBe('a');
    expect(s.messages[s.messages.length - 2]!.id).toBe('u');
  });
});

describe('canSend', () => {
  it('true only with non-empty trimmed input and not sending', () => {
    expect(canSend(mk({ input: '' }))).toBe(false);
    expect(canSend(mk({ input: '   ' }))).toBe(false);
    expect(canSend(mk({ input: 'hi', sending: true }))).toBe(false);
    expect(canSend(mk({ input: 'hi' }))).toBe(true);
  });
});

describe('toHistoryEntries', () => {
  it('drops pending, errored, and empty messages', () => {
    const msgs: ChatMessage[] = [
      { id: '1', role: 'user', text: 'hi', timestamp: 0 },
      { id: '2', role: 'assistant', text: 'hey', timestamp: 1 },
      { id: '3', role: 'assistant', text: '', pending: true, timestamp: 2 },
      { id: '4', role: 'assistant', text: 'boom', error: true, timestamp: 3 },
      { id: '5', role: 'user', text: '', timestamp: 4 },
    ];
    expect(toHistoryEntries(msgs)).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'hey' },
    ]);
  });
});
