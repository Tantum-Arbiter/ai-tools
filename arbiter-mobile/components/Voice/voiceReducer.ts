// Pure state machine for the push-to-talk voice session. Native
// recognition events (from expo-speech-recognition) are translated into
// VoiceAction by the useVoiceSession hook; the reducer itself is JS-only
// so it can be exhaustively unit-tested without a device.
//
// Lifecycle:
//   idle -> requesting (mic tap)
//   requesting -> listening (permission granted + native `start` event)
//   requesting -> denied (permission rejected)
//   listening -> listening (interim result updates)
//   listening -> finalising (native `speechend`)
//   finalising -> idle (final result dispatched to caller) | error
//   <any> -> idle (cancel / stop)

export type VoiceStatus =
  | 'idle'
  | 'requesting'
  | 'listening'
  | 'finalising'
  | 'denied'
  | 'error';

export interface VoiceState {
  status: VoiceStatus;
  /** Live partial transcript shown while listening. */
  interim: string;
  /** Last committed transcript (set on final result, cleared on next start). */
  finalTranscript: string;
  /** Most recent error code/message; cleared on next start. */
  errorMessage: string | null;
  /** 0–1 normalised audio level for the orb to react to. */
  audioLevel: number;
}

export const initialVoiceState: VoiceState = {
  status: 'idle',
  interim: '',
  finalTranscript: '',
  errorMessage: null,
  audioLevel: 0,
};

export type VoiceAction =
  | { type: 'REQUEST' }
  | { type: 'PERMISSION_GRANTED' }
  | { type: 'PERMISSION_DENIED'; message?: string }
  | { type: 'STARTED' }
  | { type: 'INTERIM'; transcript: string }
  | { type: 'FINAL'; transcript: string }
  | { type: 'SPEECH_END' }
  | { type: 'ENDED' }
  | { type: 'ERROR'; message: string }
  | { type: 'VOLUME'; value: number }
  | { type: 'CANCEL' };

// Map the native `volumechange` range (-2..10) to a 0..1 audio level
// usable by the orb simulation. Anything below 0 reads as silence.
const normaliseVolume = (raw: number): number => {
  if (raw <= 0) return 0;
  return Math.min(1, raw / 6);
};

export function voiceReducer(state: VoiceState, action: VoiceAction): VoiceState {
  switch (action.type) {
    case 'REQUEST':
      return {
        ...state,
        status: 'requesting',
        interim: '',
        finalTranscript: '',
        errorMessage: null,
        audioLevel: 0,
      };
    case 'PERMISSION_GRANTED':
      // Stay in requesting until the native `start` event fires; this
      // avoids flicker if the OS prompt was already accepted.
      return state.status === 'requesting' ? state : { ...state, status: 'requesting' };
    case 'PERMISSION_DENIED':
      return {
        ...state,
        status: 'denied',
        errorMessage: action.message ?? 'Microphone permission denied',
        audioLevel: 0,
      };
    case 'STARTED':
      return { ...state, status: 'listening', errorMessage: null };
    case 'INTERIM':
      if (state.status !== 'listening') return state;
      return { ...state, interim: action.transcript };
    case 'FINAL':
      // We treat FINAL as a terminal handoff: the hook will dispatch
      // the transcript outward and then send 'ENDED' to return to idle.
      return {
        ...state,
        status: 'finalising',
        finalTranscript: action.transcript,
        interim: action.transcript,
      };
    case 'SPEECH_END':
      if (state.status !== 'listening') return state;
      return { ...state, status: 'finalising' };
    case 'ENDED':
      return { ...initialVoiceState };
    case 'ERROR':
      return {
        ...state,
        status: 'error',
        errorMessage: action.message,
        audioLevel: 0,
      };
    case 'VOLUME':
      if (state.status !== 'listening') return state;
      return { ...state, audioLevel: normaliseVolume(action.value) };
    case 'CANCEL':
      return { ...initialVoiceState };
    default: {
      // Exhaustiveness guard: any new action type must be handled.
      const _exhaustive: never = action;
      void _exhaustive;
      return state;
    }
  }
}
