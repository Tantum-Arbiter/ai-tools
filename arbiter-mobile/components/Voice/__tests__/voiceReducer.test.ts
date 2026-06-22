import { voiceReducer, initialVoiceState } from '../voiceReducer';

describe('voiceReducer', () => {
  it('REQUEST resets transient fields and moves to requesting', () => {
    const seeded = {
      ...initialVoiceState,
      interim: 'old',
      finalTranscript: 'old',
      errorMessage: 'stale',
      audioLevel: 0.4,
    };
    const next = voiceReducer(seeded, { type: 'REQUEST' });
    expect(next.status).toBe('requesting');
    expect(next.interim).toBe('');
    expect(next.finalTranscript).toBe('');
    expect(next.errorMessage).toBeNull();
    expect(next.audioLevel).toBe(0);
  });

  it('STARTED transitions to listening and clears any error', () => {
    const s = voiceReducer(
      { ...initialVoiceState, status: 'requesting', errorMessage: 'x' },
      { type: 'STARTED' },
    );
    expect(s.status).toBe('listening');
    expect(s.errorMessage).toBeNull();
  });

  it('INTERIM only mutates when listening', () => {
    const listening = voiceReducer(initialVoiceState, { type: 'STARTED' });
    // not listening yet (state was 'idle' before STARTED applied to idle)
    const ignored = voiceReducer(initialVoiceState, { type: 'INTERIM', transcript: 'hi' });
    expect(ignored.interim).toBe('');

    const updated = voiceReducer(
      { ...listening, status: 'listening' },
      { type: 'INTERIM', transcript: 'hello sir' },
    );
    expect(updated.interim).toBe('hello sir');
  });

  it('FINAL commits transcript and moves to finalising', () => {
    const s = voiceReducer(
      { ...initialVoiceState, status: 'listening' },
      { type: 'FINAL', transcript: 'system status' },
    );
    expect(s.status).toBe('finalising');
    expect(s.finalTranscript).toBe('system status');
    expect(s.interim).toBe('system status');
  });

  it('ENDED resets to initial state', () => {
    const dirty = {
      status: 'finalising' as const,
      interim: 'x',
      finalTranscript: 'y',
      errorMessage: null,
      audioLevel: 0.5,
    };
    expect(voiceReducer(dirty, { type: 'ENDED' })).toEqual(initialVoiceState);
  });

  it('PERMISSION_DENIED records the message', () => {
    const s = voiceReducer(initialVoiceState, {
      type: 'PERMISSION_DENIED',
      message: 'mic blocked',
    });
    expect(s.status).toBe('denied');
    expect(s.errorMessage).toBe('mic blocked');
  });

  it('ERROR records the message and zeros audioLevel', () => {
    const s = voiceReducer(
      { ...initialVoiceState, status: 'listening', audioLevel: 0.6 },
      { type: 'ERROR', message: 'no-speech' },
    );
    expect(s.status).toBe('error');
    expect(s.errorMessage).toBe('no-speech');
    expect(s.audioLevel).toBe(0);
  });

  it('VOLUME normalises native -2..10 range to 0..1 while listening', () => {
    const listening = { ...initialVoiceState, status: 'listening' as const };
    expect(voiceReducer(listening, { type: 'VOLUME', value: -1 }).audioLevel).toBe(0);
    expect(voiceReducer(listening, { type: 'VOLUME', value: 0 }).audioLevel).toBe(0);
    expect(voiceReducer(listening, { type: 'VOLUME', value: 3 }).audioLevel).toBeCloseTo(0.5, 5);
    expect(voiceReducer(listening, { type: 'VOLUME', value: 12 }).audioLevel).toBe(1);
  });

  it('VOLUME is a no-op when not listening (prevents flicker on idle/denied)', () => {
    const denied = { ...initialVoiceState, status: 'denied' as const };
    expect(voiceReducer(denied, { type: 'VOLUME', value: 5 })).toBe(denied);
  });

  it('CANCEL hard-resets from any state', () => {
    const dirty = {
      status: 'error' as const,
      interim: 'x',
      finalTranscript: 'y',
      errorMessage: 'boom',
      audioLevel: 0.3,
    };
    expect(voiceReducer(dirty, { type: 'CANCEL' })).toEqual(initialVoiceState);
  });
});
