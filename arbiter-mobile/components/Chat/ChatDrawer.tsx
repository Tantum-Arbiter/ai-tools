// Hands-on chat drawer. Hosts chatReducer, owns the network round-trip,
// and renders an expandable bottom sheet (input bar collapsed, scrollable
// history when expanded). All visual state mutations go through the
// reducer; this file holds layout + animation + glue only.

import React, { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type ListRenderItem,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import {
  chatReducer,
  INITIAL_STATE,
  canSend,
  toHistoryEntries,
  type ChatMessage,
  type ChatState,
} from './chatReducer';
import type { ArbiterApi } from '../../lib/api';

export interface ChatDrawerProps {
  api: ArbiterApi;
  /** Stable id factory — defaults to time + random. Injected in tests. */
  idFactory?: () => string;
  /** Clock — defaults to Date.now. Injected in tests. */
  now?: () => number;
  /** Height of the input bar when the drawer is collapsed. */
  collapsedHeight?: number;
  /** Max height of the drawer when expanded (fraction of parent). */
  expandedHeight?: number;
  /** Called when the drawer's expansion state changes (lets the host fade out the orb). */
  onExpansionChange?: (expanded: boolean) => void;
}

const defaultIdFactory = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export const ChatDrawer: React.FC<ChatDrawerProps> = ({
  api,
  idFactory = defaultIdFactory,
  now = Date.now,
  collapsedHeight = 72,
  expandedHeight = 480,
  onExpansionChange,
}) => {
  const [state, dispatch] = useReducer(chatReducer, INITIAL_STATE);
  const stateRef = useRef<ChatState>(state);
  stateRef.current = state;

  const height = useSharedValue(collapsedHeight);

  useEffect(() => {
    height.value = withTiming(state.expanded ? expandedHeight : collapsedHeight, {
      duration: 220,
    });
    onExpansionChange?.(state.expanded);
  }, [state.expanded, expandedHeight, collapsedHeight, height, onExpansionChange]);

  const animatedStyle = useAnimatedStyle(() => ({ height: height.value }));

  const send = useCallback(async () => {
    const current = stateRef.current;
    if (!canSend(current)) return;
    const messageText = current.input.trim();
    const historyEntries = toHistoryEntries(current.messages);
    const userId = idFactory();
    const assistantId = idFactory();
    dispatch({ type: 'SEND_REQUESTED', id: userId, assistantId, timestamp: now() });
    try {
      const res = await api.sendChat(messageText, historyEntries);
      dispatch({
        type: 'SEND_SUCCEEDED',
        assistantId,
        reply: res.reply ?? '',
        ...(res.panel !== undefined ? { panel: res.panel } : {}),
        ...(res.actions !== undefined ? { actions: res.actions } : {}),
        ...(res.followups !== undefined ? { followups: res.followups } : {}),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Send failed';
      dispatch({ type: 'SEND_FAILED', assistantId, error: msg });
    }
  }, [api, idFactory, now]);

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}
      pointerEvents="box-none"
    >
      <Animated.View style={[styles.sheet, animatedStyle]}>
        <Pressable
          style={styles.grabber}
          onPress={() => dispatch({ type: 'TOGGLE_EXPANDED' })}
          accessibilityRole="button"
          accessibilityLabel={state.expanded ? 'Collapse chat' : 'Expand chat'}
          testID="chat-drawer-toggle"
        >
          <View style={styles.grabberHandle} />
        </Pressable>

        {state.expanded && (
          <MessageList messages={state.messages} />
        )}

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={state.input}
            onChangeText={(value) => dispatch({ type: 'INPUT_CHANGED', value })}
            placeholder="Ask anything…"
            placeholderTextColor="#5a7a8a"
            multiline
            blurOnSubmit={false}
            editable={!state.sending}
            onFocus={() => dispatch({ type: 'SET_EXPANDED', expanded: true })}
            onSubmitEditing={send}
            returnKeyType="send"
            testID="chat-drawer-input"
          />
          <Pressable
            onPress={send}
            disabled={!canSend(state)}
            style={[styles.sendBtn, !canSend(state) && styles.sendBtnDisabled]}
            accessibilityRole="button"
            accessibilityLabel="Send message"
            testID="chat-drawer-send"
          >
            <Text style={styles.sendBtnText}>{state.sending ? '…' : 'Send'}</Text>
          </Pressable>
        </View>

        {state.lastError && (
          <Text style={styles.errorText} testID="chat-drawer-error">
            {state.lastError}
          </Text>
        )}
      </Animated.View>
    </KeyboardAvoidingView>
  );
};

// ── MessageList ───────────────────────────────────────────────────────

interface MessageListProps {
  messages: ChatMessage[];
}

const renderMessage: ListRenderItem<ChatMessage> = ({ item }) => {
  const isUser = item.role === 'user';
  return (
    <View
      style={[
        styles.bubble,
        isUser ? styles.bubbleUser : styles.bubbleAssistant,
        item.error && styles.bubbleError,
      ]}
      testID={`chat-msg-${item.id}`}
    >
      <Text style={[styles.bubbleText, item.error && styles.bubbleTextError]}>
        {item.pending ? '…' : item.text}
      </Text>
    </View>
  );
};

const keyExtractor = (m: ChatMessage) => m.id;

const MessageList: React.FC<MessageListProps> = ({ messages }) => (
  <FlatList
    style={styles.list}
    contentContainerStyle={styles.listContent}
    data={messages}
    renderItem={renderMessage}
    keyExtractor={keyExtractor}
    keyboardShouldPersistTaps="handled"
    testID="chat-drawer-list"
  />
);

// ── Styles ────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
  },
  sheet: {
    backgroundColor: 'rgba(8, 16, 24, 0.92)',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(120, 200, 255, 0.25)',
    overflow: 'hidden',
  },
  grabber: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  grabberHandle: {
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(120, 200, 255, 0.45)',
  },
  list: { flex: 1 },
  listContent: { padding: 12, gap: 8 },
  bubble: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 14,
    maxWidth: '85%',
  },
  bubbleUser: {
    alignSelf: 'flex-end',
    backgroundColor: 'rgba(80, 160, 220, 0.35)',
  },
  bubbleAssistant: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
  },
  bubbleError: {
    backgroundColor: 'rgba(220, 80, 80, 0.25)',
  },
  bubbleText: { color: '#e8f4ff', fontSize: 15, lineHeight: 20 },
  bubbleTextError: { color: '#ffd5d5' },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    color: '#e8f4ff',
    fontSize: 15,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  sendBtn: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: 'rgba(80, 160, 220, 0.55)',
  },
  sendBtnDisabled: { opacity: 0.4 },
  sendBtnText: { color: '#e8f4ff', fontWeight: '600' },
  errorText: {
    color: '#ffb0b0',
    fontSize: 12,
    paddingHorizontal: 14,
    paddingBottom: 8,
  },
});

export default ChatDrawer;
