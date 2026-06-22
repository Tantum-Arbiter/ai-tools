// Hook bridging voiceReducer to the native expo-speech-recognition
// module. Owns nothing the reducer can own — just translates events.
//
// Usage:
//   const { state, start, stop } = useVoiceSession({
//     onFinalTranscript: (t) => api.sendChat(t),
//   });
//
// Behaviour:
//   - start() requests permissions (cached after first grant) and kicks
//     off a recognition session with interim results enabled.
//   - The hook listens to start / result / end / error / volumechange
//     and dispatches into the reducer.
//   - When a final result lands, onFinalTranscript is called and the
//     session is closed (ENDED), returning state to idle.
//   - stop() ends the current session early; the next final result (if
//     any) is still emitted before ENDED.

import { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  initialVoiceState,
  voiceReducer,
  type VoiceState,
} from './voiceReducer';

// Lazy, defensive load of the native module. If the dev client binary
// was built without expo-speech-recognition (or the native side failed
// to register for any reason), we fall back to no-op stubs so the rest
// of the app still renders. The mic button will surface a clear
// "voice unavailable" message via the reducer's denied state.
type SpeechModule = typeof import('expo-speech-recognition');
let speech: SpeechModule | null = null;
let speechLoadError: string | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  speech = require('expo-speech-recognition') as SpeechModule;
} catch (e) {
  speechLoadError = e instanceof Error ? e.message : String(e);
}
const noopHook: SpeechModule['useSpeechRecognitionEvent'] = () => {};
const useSpeechRecognitionEvent = speech?.useSpeechRecognitionEvent ?? noopHook;
const ExpoSpeechRecognitionModule = speech?.ExpoSpeechRecognitionModule;

export interface UseVoiceSessionOptions {
  /** Locale to recognise. Defaults to en-GB to match ARBITER's TTS voice. */
  lang?: string;
  /** Called once per session when a final transcript is produced. */
  onFinalTranscript?: (transcript: string) => void;
}

export interface VoiceSessionApi {
  state: VoiceState;
  /** Begin a push-to-talk session. Safe to call multiple times (no-ops while active). */
  start: () => Promise<void>;
  /** End the active session. No-op if idle. */
  stop: () => void;
  /** Hard-abort and reset the reducer. */
  cancel: () => void;
  /**
   * False when the native expo-speech-recognition module failed to load
   * (dev client built without it). The UI can use this to differentiate
   * "missing native module" from "user denied permission".
   */
  available: boolean;
  /** Underlying load error, if any. */
  loadError: string | null;
}

export function useVoiceSession(options: UseVoiceSessionOptions = {}): VoiceSessionApi {
  const { lang = 'en-GB', onFinalTranscript } = options;
  const [state, dispatch] = useReducer(voiceReducer, initialVoiceState);

  // Keep the latest callback in a ref so the effect setup doesn't
  // re-bind native event listeners every render.
  const onFinalRef = useRef(onFinalTranscript);
  useEffect(() => { onFinalRef.current = onFinalTranscript; }, [onFinalTranscript]);

  useSpeechRecognitionEvent('start', () => {
    dispatch({ type: 'STARTED' });
  });

  useSpeechRecognitionEvent('result', (event) => {
    const top = event.results[0];
    if (!top) return;
    if (event.isFinal) {
      const transcript = top.transcript.trim();
      dispatch({ type: 'FINAL', transcript });
      if (transcript) onFinalRef.current?.(transcript);
    } else {
      dispatch({ type: 'INTERIM', transcript: top.transcript });
    }
  });

  useSpeechRecognitionEvent('speechend', () => {
    dispatch({ type: 'SPEECH_END' });
  });

  useSpeechRecognitionEvent('end', () => {
    dispatch({ type: 'ENDED' });
  });

  useSpeechRecognitionEvent('error', (event) => {
    // "no-speech" is benign — user opened the mic and said nothing.
    // Treat it as a quiet cancellation rather than a loud error banner.
    if (event.error === 'no-speech' || event.error === 'aborted') {
      dispatch({ type: 'ENDED' });
      return;
    }
    dispatch({ type: 'ERROR', message: event.message || event.error });
  });

  useSpeechRecognitionEvent('volumechange', (event) => {
    dispatch({ type: 'VOLUME', value: event.value });
  });

  const start = useCallback(async () => {
    dispatch({ type: 'REQUEST' });
    if (!ExpoSpeechRecognitionModule) {
      dispatch({
        type: 'PERMISSION_DENIED',
        message:
          'Voice module unavailable in this build. Rebuild the dev client: npx expo prebuild --clean && npx expo run:ios (or run:android).',
      });
      return;
    }
    try {
      const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!perm.granted) {
        dispatch({
          type: 'PERMISSION_DENIED',
          message: 'Microphone or speech-recognition permission was denied.',
        });
        return;
      }
      ExpoSpeechRecognitionModule.start({
        lang,
        interimResults: true,
        maxAlternatives: 1,
        volumeChangeEventOptions: { enabled: true, intervalMillis: 200 },
      });
    } catch (e) {
      dispatch({
        type: 'ERROR',
        message: e instanceof Error ? e.message : 'Failed to start voice session',
      });
    }
  }, [lang]);

  const stop = useCallback(() => {
    try {
      ExpoSpeechRecognitionModule?.stop();
    } catch {
      // Stop may throw if no session is active; harmless.
    }
  }, []);

  const cancel = useCallback(() => {
    try {
      ExpoSpeechRecognitionModule?.abort();
    } catch {
      // ignore
    }
    dispatch({ type: 'CANCEL' });
  }, []);

  return {
    state,
    start,
    stop,
    cancel,
    available: !!ExpoSpeechRecognitionModule,
    loadError: speechLoadError,
  };
}
