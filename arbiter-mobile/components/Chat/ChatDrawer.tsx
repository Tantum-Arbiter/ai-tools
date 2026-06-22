// Hands-on chat drawer. Hosts chatReducer, owns the network round-trip,
// and renders an expandable bottom sheet (input bar collapsed, scrollable
// history when expanded). All visual state mutations go through the
// reducer; this file holds layout + animation + glue only.

import React, { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  FlatList,
  Keyboard,
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
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ChevronDown, ChevronUp, Send, X } from 'lucide-react-native';
import {
  chatReducer,
  INITIAL_STATE,
  canSend,
  toHistoryEntries,
  type ChatMessage,
  type ChatState,
} from './chatReducer';
import type { ArbiterApi } from '../../lib/api';
import { PanelCard } from '../panels';
import type { PanelFeedItem } from '../panels';
import type { Panel } from '../../lib/types';

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
  /** App-level visibility. When false the drawer slides off-screen. Default true. */
  visible?: boolean;
  /**
   * Optional externally-supplied transcript (e.g. from voice). When this
   * value changes to a non-empty string, the drawer expands and sets it
   * as the input so the operator can review/edit before sending.
   */
  pendingInput?: string | null;
  /**
   * Monotonic counter; whenever it increments, the drawer force-expands.
   * Used by the host (e.g. tap on the orb) to open the chat fully without
   * having to thread an `expanded` controlled prop through the reducer.
   */
  expandSignal?: number;
  /** Dismiss the drawer (host flips `visible` to false). */
  onClose?: () => void;
  /**
   * Notified when the in-flight send state changes. Lets the host drive
   * the orb's `thinking` colour while a reply is being generated.
   */
  onSendingChange?: (sending: boolean) => void;
  /**
   * Called whenever the assistant attaches a panel to a message — once
   * during streaming (when the panel event arrives) and once on send
   * success. The host should de-dup by id when feeding a PanelFeed.
   */
  onPanel?: (item: PanelFeedItem) => void;
  /**
   * When false, inline panel rendering inside the chat bubble is
   * skipped — typically because the host is rendering a PanelFeed
   * alongside the drawer (tablet layout).
   */
  renderPanelInline?: boolean;
  /**
   * Optional explicit right-edge offset for the drawer's container.
   * Default 16. Used by the tablet layout to clamp the chat to the
   * left column so it doesn't overlap the PanelFeed rail.
   */
  rightInset?: number;
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
  visible = true,
  pendingInput = null,
  expandSignal = 0,
  onClose,
  onSendingChange,
  onPanel,
  renderPanelInline = true,
  rightInset = 16,
}) => {
  const insets = useSafeAreaInsets();
  const [state, dispatch] = useReducer(chatReducer, INITIAL_STATE);
  const stateRef = useRef<ChatState>(state);
  stateRef.current = state;

  const height = useSharedValue(collapsedHeight);
  const startHeight = useSharedValue(collapsedHeight);
  const translateY = useSharedValue(visible ? 0 : expandedHeight + 200);

  useEffect(() => {
    height.value = withTiming(state.expanded ? expandedHeight : collapsedHeight, {
      duration: 220,
    });
    onExpansionChange?.(state.expanded);
  }, [state.expanded, expandedHeight, collapsedHeight, height, onExpansionChange]);

  useEffect(() => {
    translateY.value = withTiming(visible ? 0 : expandedHeight + 200, { duration: 260 });
  }, [visible, expandedHeight, translateY]);

  // Inbound transcript from the voice session. Populate the input and
  // expand the drawer so the operator can confirm / edit / send.
  useEffect(() => {
    if (!pendingInput) return;
    dispatch({ type: 'INPUT_CHANGED', value: pendingInput });
    dispatch({ type: 'SET_EXPANDED', expanded: true });
  }, [pendingInput]);

  // External expansion trigger (e.g. tap on the orb). The host bumps
  // `expandSignal` to request the drawer be opened fully; we skip the
  // initial 0 value so a freshly mounted drawer doesn't auto-expand.
  const expandSignalSeen = useRef(expandSignal);
  useEffect(() => {
    if (expandSignal === expandSignalSeen.current) return;
    expandSignalSeen.current = expandSignal;
    dispatch({ type: 'SET_EXPANDED', expanded: true });
  }, [expandSignal]);

  // Surface the in-flight send state so the host can flip the orb to
  // its `thinking` colour while a reply is being generated.
  useEffect(() => {
    onSendingChange?.(state.sending);
  }, [state.sending, onSendingChange]);

  const animatedStyle = useAnimatedStyle(() => ({
    height: height.value,
    transform: [{ translateY: translateY.value }],
  }));

  const setExpansion = useCallback((expanded: boolean) => {
    if (stateRef.current.expanded !== expanded) {
      dispatch({ type: 'SET_EXPANDED', expanded });
    }
  }, []);

  const toggleExpansion = useCallback(() => {
    dispatch({ type: 'TOGGLE_EXPANDED' });
  }, []);

  // Drag-to-resize. The pan gesture owns drawer height while active; on
  // release we snap to the nearest end (or fling threshold) and sync
  // state.expanded so the host (orb fade) follows.
  const panGesture = Gesture.Pan()
    .activeOffsetY([-8, 8])
    .onStart(() => {
      startHeight.value = height.value;
    })
    .onUpdate((e) => {
      const next = startHeight.value - e.translationY;
      height.value = Math.max(collapsedHeight, Math.min(expandedHeight, next));
    })
    .onEnd((e) => {
      const mid = (collapsedHeight + expandedHeight) / 2;
      const flingUp = e.velocityY < -500;
      const flingDown = e.velocityY > 500;
      const expanded = flingUp || (!flingDown && height.value > mid);
      const target = expanded ? expandedHeight : collapsedHeight;
      height.value = withTiming(target, { duration: 220 });
      runOnJS(setExpansion)(expanded);
    });

  const tapGesture = Gesture.Tap()
    .maxDistance(8)
    .onEnd((_e, success) => {
      if (success) runOnJS(toggleExpansion)();
    });

  const handleGesture = Gesture.Race(panGesture, tapGesture);

  const sendText = useCallback(
    async (overrideText?: string) => {
      const current = stateRef.current;
      const source = overrideText !== undefined ? overrideText : current.input;
      const messageText = source.trim();
      if (!messageText || current.sending) return;
      // Dismiss the soft keyboard so the orb + "thinking" feedback are
      // visible while the reply is being generated.
      Keyboard.dismiss();
      const historyEntries = toHistoryEntries(current.messages);
      const userId = idFactory();
      const assistantId = idFactory();
      dispatch({
        type: 'SEND_REQUESTED',
        id: userId,
        assistantId,
        timestamp: now(),
        ...(overrideText !== undefined ? { text: overrideText } : {}),
      });
      const emitPanel = (panel: Panel) => {
        onPanel?.({ id: assistantId, panel, timestamp: now() });
      };
      try {
        const res = await api.streamChat(messageText, historyEntries, {
          onDelta: (text) =>
            dispatch({ type: 'STREAM_DELTA', assistantId, text }),
          onPanel: (panel) => {
            dispatch({ type: 'STREAM_PANEL', assistantId, panel });
            emitPanel(panel);
          },
        });
        dispatch({
          type: 'SEND_SUCCEEDED',
          assistantId,
          reply: res.reply ?? '',
          ...(res.panel !== undefined ? { panel: res.panel } : {}),
          ...(res.actions !== undefined ? { actions: res.actions } : {}),
          ...(res.followups !== undefined ? { followups: res.followups } : {}),
        });
        if (res.panel) emitPanel(res.panel);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Send failed';
        dispatch({ type: 'SEND_FAILED', assistantId, error: msg });
      }
    },
    [api, idFactory, now, onPanel],
  );

  const send = useCallback(() => {
    if (!canSend(stateRef.current)) return;
    void sendText();
  }, [sendText]);

  const onFollowupPress = useCallback(
    (messageId: string, text: string) => {
      // Mirror the website's behaviour: clear the chip strip on tap and
      // immediately fire the send so a single tap commits the choice.
      dispatch({ type: 'FOLLOWUPS_CLEARED', messageId });
      void sendText(text);
    },
    [sendText],
  );

  // Tapping the X dismisses the keyboard before handing control back to
  // the host so the parent UI isn't left with a stranded soft keyboard.
  const handleClose = useCallback(() => {
    Keyboard.dismiss();
    onClose?.();
  }, [onClose]);

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={[styles.container, { bottom: insets.bottom + 12, right: rightInset }]}
      pointerEvents="box-none"
    >
      <Animated.View style={[styles.sheet, animatedStyle]}>
        <View style={styles.header}>
          <GestureDetector gesture={handleGesture}>
            <View
              style={styles.grabber}
              accessibilityRole="button"
              accessibilityLabel={state.expanded ? 'Collapse chat' : 'Expand chat'}
              testID="chat-drawer-toggle"
            >
              <View style={styles.grabberHandle} />
              {state.expanded ? (
                <ChevronDown size={14} color="#78a8bc" strokeWidth={2} />
              ) : (
                <ChevronUp size={14} color="#78a8bc" strokeWidth={2} />
              )}
            </View>
          </GestureDetector>
          {onClose && (
            <Pressable
              onPress={handleClose}
              style={styles.headerBtn}
              accessibilityRole="button"
              accessibilityLabel="Close chat"
              testID="chat-drawer-close"
            >
              <X size={14} color="#78a8bc" strokeWidth={2} />
            </Pressable>
          )}
        </View>

        {state.expanded && (
          <MessageList
            messages={state.messages}
            onFollowupPress={onFollowupPress}
            renderPanelInline={renderPanelInline}
          />
        )}

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={state.input}
            onChangeText={(value) => dispatch({ type: 'INPUT_CHANGED', value })}
            placeholder="Type a message…"
            placeholderTextColor="#5a7a8a"
            multiline
            blurOnSubmit={false}
            editable={!state.sending}
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
            <Send size={16} color="#20f4ff" strokeWidth={2} />
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
  onFollowupPress: (messageId: string, text: string) => void;
  renderPanelInline: boolean;
}

interface MessageRowProps {
  message: ChatMessage;
  onFollowupPress: (messageId: string, text: string) => void;
  renderPanelInline: boolean;
}

const MessageRow: React.FC<MessageRowProps> = ({
  message,
  onFollowupPress,
  renderPanelInline,
}) => {
  const isUser = message.role === 'user';
  return (
    <View style={styles.messageRow}>
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAssistant,
          message.error && styles.bubbleError,
        ]}
        testID={`chat-msg-${message.id}`}
      >
        <Text style={[styles.bubbleText, message.error && styles.bubbleTextError]}>
          {message.pending && message.text.length === 0 ? '…' : message.text}
        </Text>
      </View>
      {!isUser && renderPanelInline && message.panel && (
        <PanelCard panel={message.panel} />
      )}
      {!isUser && !message.pending && message.followups && message.followups.length > 0 && (
        <View style={styles.followupWrap} testID={`chat-followups-${message.id}`}>
          {message.followups.map((fu, i) => (
            <Pressable
              key={`${message.id}-fu-${i}`}
              onPress={() => onFollowupPress(message.id, fu)}
              style={({ pressed }) => [
                styles.followupBtn,
                pressed && styles.followupBtnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={`Suggested reply: ${fu}`}
              testID={`chat-followup-${message.id}-${i}`}
            >
              <Text style={styles.followupBtnText}>{fu}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
};

const keyExtractor = (m: ChatMessage) => m.id;

const MessageList: React.FC<MessageListProps> = ({
  messages,
  onFollowupPress,
  renderPanelInline,
}) => {
  const renderItem: ListRenderItem<ChatMessage> = ({ item }) => (
    <MessageRow
      message={item}
      onFollowupPress={onFollowupPress}
      renderPanelInline={renderPanelInline}
    />
  );
  return (
    <FlatList
      style={styles.list}
      contentContainerStyle={styles.listContent}
      data={messages}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      keyboardShouldPersistTaps="handled"
      testID="chat-drawer-list"
    />
  );
};

// ── Styles ────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 16,
    right: 16,
    bottom: 0,
    alignItems: 'center',
  },
  sheet: {
    width: '100%',
    maxWidth: 520,
    backgroundColor: 'rgba(8, 16, 24, 0.92)',
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(120, 200, 255, 0.25)',
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 8,
  },
  grabber: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 8,
  },
  grabberHandle: {
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(120, 200, 255, 0.45)',
  },
  headerBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 200, 255, 0.08)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(120, 200, 255, 0.25)',
  },
  list: { flex: 1 },
  listContent: { padding: 12, gap: 10 },
  messageRow: { gap: 6 },
  followupWrap: {
    alignSelf: 'flex-start',
    maxWidth: '92%',
    flexDirection: 'column',
    gap: 4,
    paddingTop: 2,
  },
  followupBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 200, 255, 0.22)',
    backgroundColor: 'rgba(0, 200, 255, 0.06)',
  },
  followupBtnPressed: {
    borderColor: 'rgba(32, 244, 255, 0.85)',
    backgroundColor: 'rgba(0, 200, 255, 0.16)',
  },
  followupBtnText: {
    color: '#bfe6ff',
    fontSize: 13,
    letterSpacing: 0.4,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
  },
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
  bubbleText: { color: '#e8f4ff', fontSize: 17, lineHeight: 22 },
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
    fontSize: 17,
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
    fontSize: 13,
    paddingHorizontal: 14,
    paddingBottom: 8,
  },
});

export default ChatDrawer;
