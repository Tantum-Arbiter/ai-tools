// Pure state machine for the hands-on chat drawer. All side-effects
// (network, storage, animations) live in the host component; the reducer
// only mutates the immutable in-memory model. Designed for unit testing
// in plain Node with no RN dependencies.

import type { Action as ServerAction, HistoryEntry, Panel } from '../../lib/types';

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  /** Set on the assistant message that is still awaiting a reply. */
  pending?: boolean;
  /** Set when the assistant turn errored — text contains the user-facing copy. */
  error?: boolean;
  panel?: Panel;
  actions?: ServerAction[];
  followups?: string[];
  timestamp: number;
}

export interface ChatState {
  messages: ChatMessage[];
  input: string;
  expanded: boolean;
  /** True while an assistant turn is in flight. */
  sending: boolean;
  /** Non-null when last send failed; cleared on next send/dismiss. */
  lastError: string | null;
}

export const INITIAL_STATE: ChatState = {
  messages: [],
  input: '',
  expanded: false,
  sending: false,
  lastError: null,
};

/** Hard cap on retained messages to bound memory and storage. */
export const HISTORY_CAP = 200;

export type ChatAction =
  | { type: 'INPUT_CHANGED'; value: string }
  | { type: 'SET_EXPANDED'; expanded: boolean }
  | { type: 'TOGGLE_EXPANDED' }
  | {
      type: 'SEND_REQUESTED';
      id: string;
      assistantId: string;
      timestamp: number;
      /** When set, this overrides state.input (used by followup-chip taps). */
      text?: string;
    }
  | {
      type: 'SEND_SUCCEEDED';
      assistantId: string;
      reply: string;
      panel?: Panel;
      actions?: ServerAction[];
      followups?: string[];
    }
  /** Append a streaming token to the in-flight assistant bubble. */
  | { type: 'STREAM_DELTA'; assistantId: string; text: string }
  /** Attach a streamed-in panel without finalising the message. */
  | { type: 'STREAM_PANEL'; assistantId: string; panel: Panel }
  | { type: 'SEND_FAILED'; assistantId: string; error: string }
  | { type: 'ERROR_DISMISSED' }
  | { type: 'HISTORY_LOADED'; messages: ChatMessage[] }
  | { type: 'CLEAR_HISTORY' }
  /** Clear followup chips from a message after the user picks one. */
  | { type: 'FOLLOWUPS_CLEARED'; messageId: string };

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'INPUT_CHANGED':
      return { ...state, input: action.value };

    case 'SET_EXPANDED':
      return { ...state, expanded: action.expanded };

    case 'TOGGLE_EXPANDED':
      return { ...state, expanded: !state.expanded };

    case 'SEND_REQUESTED': {
      const source = action.text !== undefined ? action.text : state.input;
      const trimmed = source.trim();
      // Guard against double-send and empty messages — the host should also
      // check canSend(state) before dispatching, but the reducer is the
      // authority.
      if (!trimmed || state.sending) return state;
      const userMsg: ChatMessage = {
        id: action.id,
        role: 'user',
        text: trimmed,
        timestamp: action.timestamp,
      };
      const placeholder: ChatMessage = {
        id: action.assistantId,
        role: 'assistant',
        text: '',
        pending: true,
        timestamp: action.timestamp,
      };
      return {
        ...state,
        // Only clear the typed input when the send was sourced from it;
        // a chip-driven send shouldn't wipe what the operator is typing.
        input: action.text !== undefined ? state.input : '',
        sending: true,
        lastError: null,
        expanded: true,
        messages: capMessages([...state.messages, userMsg, placeholder]),
      };
    }

    case 'FOLLOWUPS_CLEARED': {
      const messages = state.messages.map((m) => {
        if (m.id !== action.messageId || !m.followups) return m;
        const { followups: _f, ...rest } = m;
        return rest;
      });
      return { ...state, messages };
    }

    case 'SEND_SUCCEEDED': {
      const messages = state.messages.map((m) => {
        if (m.id !== action.assistantId) return m;
        const updated: ChatMessage = {
          ...m,
          // Prefer the accumulated streamed text when present so a final
          // reply value of '' from `done` doesn't blank out the bubble.
          text: action.reply || m.text,
          pending: false,
        };
        if (action.panel !== undefined) updated.panel = action.panel;
        if (action.actions !== undefined) updated.actions = action.actions;
        if (action.followups !== undefined) updated.followups = action.followups;
        return updated;
      });
      return { ...state, sending: false, lastError: null, messages };
    }

    case 'STREAM_DELTA': {
      if (!action.text) return state;
      const messages = state.messages.map((m) =>
        m.id === action.assistantId
          ? { ...m, text: m.text + action.text, pending: true }
          : m,
      );
      return { ...state, messages };
    }

    case 'STREAM_PANEL': {
      const messages = state.messages.map((m) =>
        m.id === action.assistantId ? { ...m, panel: action.panel } : m,
      );
      return { ...state, messages };
    }

    case 'SEND_FAILED': {
      const messages = state.messages.map((m) =>
        m.id === action.assistantId
          ? { ...m, text: action.error, pending: false, error: true }
          : m,
      );
      return { ...state, sending: false, lastError: action.error, messages };
    }

    case 'ERROR_DISMISSED':
      return { ...state, lastError: null };

    case 'HISTORY_LOADED':
      return { ...state, messages: capMessages(action.messages) };

    case 'CLEAR_HISTORY':
      return { ...state, messages: [], sending: false, lastError: null };

    default:
      return state;
  }
}

export function canSend(state: ChatState): boolean {
  return !state.sending && state.input.trim().length > 0;
}

/** Map UI messages → wire-shape history for the chat API. */
export function toHistoryEntries(messages: ChatMessage[]): HistoryEntry[] {
  return messages
    .filter((m) => !m.pending && !m.error && m.text.length > 0)
    .map((m) => ({ role: m.role, content: m.text }));
}

function capMessages(msgs: ChatMessage[]): ChatMessage[] {
  return msgs.length <= HISTORY_CAP ? msgs : msgs.slice(msgs.length - HISTORY_CAP);
}
