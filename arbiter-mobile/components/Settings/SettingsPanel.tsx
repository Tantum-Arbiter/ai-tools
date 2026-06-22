// Settings overlay window. Replaces the previous /settings stack
// route — operator wanted a HUD-style modal centered in the viewport
// that slides in over the current view rather than a full page push.
// Mounted at the root via SettingsOverlayProvider, so any screen can
// open it via the useSettingsOverlay hook without router involvement.
//
// Visual: dimmed backdrop (tap to dismiss) + a centered card that
// slides up from below with a scale/opacity fade. Form logic is
// unchanged from the old route file — verify-before-persist, then
// auto-dismiss on success.

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { X } from 'lucide-react-native';
import { useCredentials } from '../../lib/credentials';
import { createApi } from '../../lib/api';

export interface SettingsPanelProps {
  visible: boolean;
  onClose: () => void;
}

const SLIDE_MS = 240;
// Distance (dp) the card slides up from below its resting position
// during the open animation. Small enough to feel like a window
// settling into place rather than a sheet flying in from off-screen.
const SLIDE_FROM = 32;

const SettingsPanelImpl: React.FC<SettingsPanelProps> = ({ visible, onClose }) => {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const { credentials, setCredentials, clearCredentials } = useCredentials();
  // Card dimensions: capped so it reads as a windowed modal even on
  // tablets. Width tracks the viewport with 24dp margins on each side
  // up to the cap; height stays below the keyboard-safe area.
  const cardWidth = Math.min(width - 32, 440);
  const cardMaxHeight = Math.min(height - insets.top - insets.bottom - 40, 560);

  const [hostUrl, setHostUrl] = useState(credentials?.hostUrl ?? '');
  const [apiKey, setApiKey] = useState(credentials?.apiKey ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-seed fields when the stored credentials change or the panel
  // re-opens, so a freshly-saved value shows up next time round.
  useEffect(() => {
    if (!visible) return;
    setHostUrl(credentials?.hostUrl ?? '');
    setApiKey(credentials?.apiKey ?? '');
    setError(null);
  }, [visible, credentials]);

  // Open: slide from SLIDE_FROM below to 0, scale 0.94 → 1, fade in.
  // Close: reverse. Backdrop opacity tracks in parallel.
  const progress = useSharedValue(0);
  const backdropOpacity = useSharedValue(0);
  useEffect(() => {
    progress.value = withTiming(visible ? 1 : 0, { duration: SLIDE_MS });
    backdropOpacity.value = withTiming(visible ? 1 : 0, { duration: SLIDE_MS });
  }, [visible, progress, backdropOpacity]);

  const cardStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [
      { translateY: (1 - progress.value) * SLIDE_FROM },
      { scale: 0.94 + progress.value * 0.06 },
    ],
  }));
  const backdropStyle = useAnimatedStyle(() => ({
    opacity: backdropOpacity.value,
  }));

  const close = () => {
    Keyboard.dismiss();
    onClose();
  };

  const save = async () => {
    setError(null);
    const host = hostUrl.trim();
    const key = apiKey.trim();
    if (!host || !key) {
      setError('Host URL and API key are required');
      return;
    }
    setBusy(true);
    try {
      const probe = createApi({
        fetch: globalThis.fetch.bind(globalThis),
        getCredentials: async () => ({ hostUrl: host, apiKey: key }),
      });
      const res = await probe.checkAuth();
      if (!res.valid) {
        setError('Server rejected the API key');
        return;
      }
      await setCredentials({ hostUrl: host, apiKey: key });
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify credentials');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setError(null);
    await clearCredentials();
    setHostUrl('');
    setApiKey('');
  };

  // Cheap mount guard: keep the tree unmounted while fully closed so
  // we don't pay layout/render costs in the common case.
  const [mounted, setMounted] = useState(visible);
  useEffect(() => {
    if (visible) {
      setMounted(true);
      return;
    }
    const t = setTimeout(() => setMounted(false), SLIDE_MS + 40);
    return () => clearTimeout(t);
  }, [visible]);
  if (!mounted) return null;

  return (
    <View style={styles.root} pointerEvents={visible ? 'auto' : 'none'}>
      <Animated.View style={[StyleSheet.absoluteFill, backdropStyle]}>
        <Pressable style={styles.backdrop} onPress={close} accessibilityLabel="Close settings" />
      </Animated.View>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.centerer}
        pointerEvents="box-none"
      >
        <Animated.View
          style={[
            styles.card,
            { width: cardWidth, maxHeight: cardMaxHeight },
            cardStyle,
          ]}
        >
          <View style={styles.header}>
            <Text style={styles.title}>SETTINGS</Text>
            <Pressable onPress={close} hitSlop={12} accessibilityRole="button" accessibilityLabel="Close">
              <X size={20} color="#bfe6ff" strokeWidth={2} />
            </Pressable>
          </View>
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.label}>Host URL</Text>
            <TextInput
              style={styles.input}
              value={hostUrl}
              onChangeText={setHostUrl}
              placeholder="https://laptop.tailXXXX.ts.net"
              placeholderTextColor="#5a7a8a"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              testID="settings-host-input"
            />
            <Text style={styles.label}>API Key</Text>
            <TextInput
              style={styles.input}
              value={apiKey}
              onChangeText={setApiKey}
              placeholder="ARBITER_API_KEY"
              placeholderTextColor="#5a7a8a"
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
              testID="settings-key-input"
            />
            {error && <Text style={styles.error}>{error}</Text>}
            <Pressable
              style={[styles.btn, styles.btnPrimary, busy && styles.btnDisabled]}
              onPress={save}
              disabled={busy}
              accessibilityRole="button"
              testID="settings-save"
            >
              {busy ? (
                <ActivityIndicator color="#e8f4ff" />
              ) : (
                <Text style={styles.btnText}>Verify &amp; Save</Text>
              )}
            </Pressable>
            <Pressable
              style={[styles.btn, styles.btnGhost]}
              onPress={clear}
              accessibilityRole="button"
              testID="settings-clear"
            >
              <Text style={[styles.btnText, styles.btnGhostText]}>Clear</Text>
            </Pressable>
            <Text style={styles.hint}>
              Connect over Tailscale or a similar private network. The host URL
              must be reachable from this device.
            </Text>
          </ScrollView>
        </Animated.View>
      </KeyboardAvoidingView>
    </View>
  );
};

export const SettingsPanel = React.memo(SettingsPanelImpl);

const styles = StyleSheet.create({
  root: { ...StyleSheet.absoluteFillObject, zIndex: 100 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0, 8, 20, 0.55)' },
  centerer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  card: {
    backgroundColor: '#080f1e',
    borderRadius: 18,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(32, 244, 255, 0.35)',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.55,
    shadowRadius: 24,
    elevation: 24,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(32, 244, 255, 0.20)',
  },
  title: {
    color: '#e8f4ff',
    fontSize: 14,
    letterSpacing: 2,
    fontWeight: '600',
  },
  scroll: { padding: 16, gap: 12 },
  label: { color: '#9fc4dc', fontSize: 14, marginTop: 8 },
  input: {
    color: '#e8f4ff',
    fontSize: 17,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(120, 200, 255, 0.25)',
  },
  error: { color: '#ffb0b0', fontSize: 14, marginTop: 4 },
  btn: { paddingVertical: 12, borderRadius: 12, alignItems: 'center', marginTop: 8 },
  btnPrimary: { backgroundColor: 'rgba(80, 160, 220, 0.55)' },
  btnGhost: { backgroundColor: 'transparent' },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#e8f4ff', fontWeight: '600', fontSize: 17 },
  btnGhostText: { color: '#9fc4dc' },
  hint: { color: '#5a7a8a', fontSize: 13, marginTop: 16, lineHeight: 20 },
});

export default SettingsPanel;
