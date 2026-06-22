// Main screen: orb hero + dock of view buttons + (tap-to-reveal) chat
// drawer. The orb is absolutely centred on the full viewport. Tapping it
// opens the chat drawer. The mic toggle starts a push-to-talk voice
// session via expo-speech-recognition; the resulting transcript is
// piped into the chat drawer for review/send. The Tron grid + radial
// illumination mirrors the desktop dashboard (static/style.css
// body::before / body::after).

import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { useIsFocused } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Mic,
  MicOff,
  Network,
  Settings as SettingsIcon,
} from 'lucide-react-native';
import { Orb } from '../components/Orb/Orb';
import { ChatDrawer } from '../components/Chat/ChatDrawer';
import { TronBackground } from '../components/Background/TronBackground';
import { PanelFeed, type PanelFeedItem } from '../components/panels';
import { HUD_FONTS } from '../components/HUD/tokens';
import { useApi, useCredentials } from '../lib/credentials';
import { useSettingsOverlay } from '../lib/settingsOverlay';
import { useVoiceSession } from '../components/Voice/useVoiceSession';

const DRAWER_COLLAPSED = 84;
// Fraction of viewport height the chat occupies when expanded. Operator
// asked for a small, focused panel — kept at 20% so the orb stays the
// dominant element.
const DRAWER_EXPANDED = 0.20;
// Floor on the expanded drawer height so an iPad in Stage Manager
// resized to a short window can't collapse the chat to a sliver.
const DRAWER_EXPANDED_MIN_PX = 220;
// Tablet split-layout breakpoint. iPad mini portrait = 768 — anything
// at or above that gets the right-rail PanelFeed. Computed off the
// live useWindowDimensions value so iPad multitasking (Slide Over /
// Split View / Stage Manager) flips between single-pane and split as
// the window is resized.
const TABLET_BREAKPOINT = 768;
// Cap on retained panel-feed items so the right rail can't grow
// unbounded over a long session.
const PANEL_FEED_CAP = 24;

export default function Home() {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const api = useApi();
  const { status } = useCredentials();
  const router = useRouter();
  const settings = useSettingsOverlay();
  // Pause the Skia orb whenever the home screen is not the focused
  // route in the stack. Cuts CPU/GPU to ~0 while the operator is on
  // Uptime/Business/Orchestration — single biggest thermal win.
  const isFocused = useIsFocused();

  const isTablet = width >= TABLET_BREAKPOINT;
  // On tablets the chat lives in the left rail and the orb shrinks so
  // both columns fit; on phones the orb stays at its 62% hero size.
  const chatColumnWidth = isTablet ? Math.min(width * 0.42, 480) : width;
  const orbSize = Math.min(chatColumnWidth, height) * (isTablet ? 0.55 : 0.62);
  const [drawerExpanded, setDrawerExpanded] = useState(false);
  const [chatVisible, setChatVisible] = useState(false);
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null);
  const [expandSignal, setExpandSignal] = useState(0);
  const [panelFeed, setPanelFeed] = useState<PanelFeedItem[]>([]);
  // Local "tap-confirmed listening" flag so the orb flips green
  // instantly when the operator hits the mic, even if the native
  // voice module is still negotiating permissions. Cleared when the
  // session ends naturally or another mic tap stops it.
  const [listeningOverride, setListeningOverride] = useState(false);
  // Set by the ChatDrawer while an API round-trip is in-flight so the
  // orb flips to its `thinking` colour while a reply is generated.
  const [chatSending, setChatSending] = useState(false);

  // Capture each assistant-attached panel into the feed. Replaces by id
  // so streaming updates from /stream don't pile up duplicates.
  const onPanel = useCallback((item: PanelFeedItem) => {
    setPanelFeed((prev) => {
      const filtered = prev.filter((p) => p.id !== item.id);
      const next = [item, ...filtered];
      return next.length > PANEL_FEED_CAP ? next.slice(0, PANEL_FEED_CAP) : next;
    });
  }, []);

  const onFinalTranscript = useCallback((transcript: string) => {
    // Open chat with the transcript pre-filled so the user can edit /
    // confirm. Reset to null on next tick so re-recording the same
    // phrase still triggers the effect downstream.
    setChatVisible(true);
    setPendingTranscript(transcript);
    setListeningOverride(false);
  }, []);

  const voice = useVoiceSession({ onFinalTranscript });
  const voiceActive = voice.state.status === 'listening' || voice.state.status === 'requesting';

  // Clear pendingTranscript after the drawer has had a tick to consume it.
  useEffect(() => {
    if (pendingTranscript === null) return;
    const t = setTimeout(() => setPendingTranscript(null), 0);
    return () => clearTimeout(t);
  }, [pendingTranscript]);

  // Focus mode: when a shared-content panel (currently just the
  // settings overlay) is up on a phone, the orb shrinks and tucks into
  // the bottom-right corner so the panel reads as the primary surface
  // and the dock hides. Tablets keep the split layout — the orb is
  // already in its own column, no transition needed.
  const focusActive = settings.isOpen && !isTablet;
  const focusProgress = useSharedValue(0);
  useEffect(() => {
    focusProgress.value = withTiming(focusActive ? 1 : 0, {
      duration: 320,
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    });
  }, [focusActive, focusProgress]);

  // Target geometry for the focused orb. Scale is applied via
  // transform (Skia canvas internal size unchanged so the animation
  // stays on the UI thread) and translation moves the centre of the
  // orb wrapper from its resting point to the bottom-right corner.
  const FOCUS_SCALE = 0.34;
  const FOCUS_MARGIN_RIGHT = 20;
  const FOCUS_MARGIN_BOTTOM = 24;
  const focusedSize = orbSize * FOCUS_SCALE;
  const restingCenterX = chatColumnWidth / 2;
  const restingCenterY = height / 2;
  const targetCenterX = width - FOCUS_MARGIN_RIGHT - focusedSize / 2;
  const targetCenterY = height - insets.bottom - FOCUS_MARGIN_BOTTOM - focusedSize / 2;
  const focusDx = targetCenterX - restingCenterX;
  const focusDy = targetCenterY - restingCenterY;

  const orbAnimStyle = useAnimatedStyle(() => {
    const p = focusProgress.value;
    return {
      transform: [
        { translateX: focusDx * p },
        { translateY: focusDy * p },
        { scale: 1 - (1 - FOCUS_SCALE) * p },
      ],
    };
  });

  const dockAnimStyle = useAnimatedStyle(() => {
    const p = focusProgress.value;
    return {
      opacity: 1 - p,
      transform: [{ translateY: 40 * p }],
    };
  });

  // The chat is a small (~20%) floating card so the orb stays the
  // dominant visual. We only track expansion to keep state in sync; we
  // deliberately do NOT pause or fade the orb here — doing so used to
  // freeze the simulation the moment the chat opened.
  const onExpansionChange = (expanded: boolean) => {
    setDrawerExpanded(expanded);
  };

  // Orb tap is the primary voice affordance. Blue → green: opens the
  // chat and starts dictation. Green → blue: stops dictation AND
  // closes the chat entirely so the orb returns to a clean idle
  // surface (operator request). The text input never triggers voice
  // (that was the earlier bug — focusing the field auto-started
  // dictation); the mic now only fires from an explicit mic gesture
  // (orb tap or topbar mic).
  const onOrbPress = () => {
    if (voiceActive || listeningOverride) {
      voice.stop();
      setListeningOverride(false);
      setChatVisible(false);
      return;
    }
    setChatVisible(true);
    setExpandSignal((n) => n + 1);
    setListeningOverride(true);
    void voice.start();
  };

  const onChatClose = () => {
    setChatVisible(false);
  };

  // Mic toggle — used by the topbar mic. Does NOT touch chat
  // visibility (the topbar mic is a heads-up dictation affordance, not
  // a chat opener); use the orb tap if you want chat + voice together.
  const onMicToggle = () => {
    if (voiceActive || listeningOverride) {
      voice.stop();
      setListeningOverride(false);
      return;
    }
    setListeningOverride(true);
    void voice.start();
  };

  // Priority: a live voice session always wins (operator is talking),
  // then an in-flight chat send (orb thinks), then idle.
  const orbState =
    voiceActive || listeningOverride
      ? 'listening'
      : chatSending
        ? 'thinking'
        : 'idle';

  // Anchor the radial lighting to the orb on tablets so it tracks the
  // orb into the left column instead of staying glued to viewport
  // centre during iPad landscape / Stage Manager. On phones the orb
  // sits dead-centre so the default centre is correct.
  const lightingCenterX = isTablet ? chatColumnWidth / 2 : width / 2;
  const lightingCenterY = height / 2;

  return (
    <View style={styles.root}>
      <TronBackground
        width={width}
        height={height}
        centerX={lightingCenterX}
        centerY={lightingCenterY}
      />

      <View
        style={[styles.orbWrap, { width: chatColumnWidth, height }]}
        pointerEvents="box-none"
      >
        <Animated.View style={orbAnimStyle}>
          <Pressable
            onPress={onOrbPress}
            accessibilityRole="button"
            accessibilityLabel="Open chat with Arbiter"
            hitSlop={20}
            style={{ width: orbSize, height: orbSize }}
          >
            <Orb size={orbSize} state={orbState} paused={!isFocused} />
          </Pressable>
        </Animated.View>
      </View>

      {isTablet && (
        <View
          style={[
            styles.panelRail,
            {
              left: chatColumnWidth,
              width: width - chatColumnWidth,
              paddingTop: insets.top + 56,
              paddingBottom: insets.bottom + 24,
            },
          ]}
          pointerEvents="box-none"
        >
          <PanelFeed items={panelFeed} />
        </View>
      )}

      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]} pointerEvents="box-none">
        <Pressable
          onPress={onMicToggle}
          accessibilityRole="button"
          accessibilityLabel={voiceActive ? 'Stop listening' : 'Start voice input'}
          hitSlop={12}
          style={[styles.iconBtn, voiceActive && styles.iconBtnActive]}
        >
          {voiceActive ? (
            <Mic size={22} color="#20f4ff" strokeWidth={2} />
          ) : (
            <MicOff size={22} color="#bfe6ff" strokeWidth={2} />
          )}
        </Pressable>
        <View style={styles.brand} pointerEvents="none">
          <View style={styles.haloOuter}>
            <View style={styles.haloRing} />
          </View>
          <View style={styles.brandText}>
            <Text style={styles.brandTitle}>ARBITER</Text>
            <Text style={styles.brandSub}>MISSION CONTROL</Text>
          </View>
        </View>
        <Pressable
          onPress={settings.open}
          accessibilityRole="button"
          accessibilityLabel="Open settings"
          hitSlop={12}
          style={styles.iconBtn}
        >
          <SettingsIcon size={22} color="#bfe6ff" strokeWidth={2} />
        </Pressable>
      </View>

      {voiceActive && (
        <View
          style={[styles.voiceBanner, { top: insets.top + 56 }]}
          pointerEvents="none"
        >
          <Text style={styles.voiceBannerText}>
            {voice.state.status === 'requesting'
              ? 'Listening…'
              : voice.state.interim || 'Listening…'}
          </Text>
        </View>
      )}

      {(voice.state.status === 'denied' || voice.state.status === 'error') && (
        <View
          style={[styles.voiceBanner, styles.voiceBannerError, { top: insets.top + 56 }]}
          pointerEvents="none"
        >
          <Text style={styles.voiceBannerText}>
            {!voice.available
              ? 'Voice module not in this build. Run: npx expo prebuild --clean && npx expo run:ios'
              : voice.state.errorMessage ||
                'Microphone permission denied. Enable it in Settings to use voice.'}
          </Text>
        </View>
      )}

      {/* Dock stays mounted whether the chat is open or not — the chat
          panel is a small floating card so the dock remains visible and
          tappable underneath it. Only hidden while the operator is
          actively dictating with the chat closed, OR while a focused
          shared-content panel (settings overlay on phones) is up. */}
      {!(voiceActive && !chatVisible) && (
        <Animated.View
          style={[
            styles.dock,
            {
              bottom: insets.bottom + 24,
              right: isTablet ? width - chatColumnWidth : 0,
            },
            dockAnimStyle,
          ]}
          pointerEvents={focusActive ? 'none' : 'box-none'}
        >
          <DockButton
            label="Business"
            icon={<BarChart3 size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/business-summary')}
          />
          <DockButton
            label="Orchestration"
            icon={<Network size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/orchestration')}
          />
          <DockButton
            label="Uptime"
            icon={<Activity size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/uptime')}
          />
        </Animated.View>
      )}

      {/* Notification-shaped card pinned to the right rail. Sits well
          below the top bar so a tap doesn't fight the buttons.
          Mirrors the website's .notif-banner.warning (style.css ~2372)
          — 3px amber left border, tinted background, source label +
          message stack. Tap opens settings (and, on phones, kicks the
          orb into the bottom-right focus state). */}
      {status === 'unconfigured' && !voiceActive && (
        <Pressable
          onPress={settings.open}
          style={[styles.notifBanner, { top: insets.top + 120 }]}
          accessibilityRole="button"
          accessibilityLabel="Configure host URL and API key"
        >
          <AlertTriangle size={18} color="#ffb454" strokeWidth={2} />
          <View style={styles.notifBody}>
            <Text style={styles.notifSource}>CONFIGURATION</Text>
            <Text style={styles.notifMessage}>
              Host URL + API key not set — tap to configure
            </Text>
          </View>
        </Pressable>
      )}

      <ChatDrawer
        api={api}
        visible={chatVisible}
        pendingInput={pendingTranscript}
        expandSignal={expandSignal}
        collapsedHeight={DRAWER_COLLAPSED}
        expandedHeight={Math.max(DRAWER_EXPANDED_MIN_PX, height * DRAWER_EXPANDED)}
        onExpansionChange={onExpansionChange}
        onClose={onChatClose}
        onSendingChange={setChatSending}
        onPanel={onPanel}
        renderPanelInline={!isTablet}
        rightInset={isTablet ? width - chatColumnWidth + 16 : 16}
      />
    </View>
  );
}

interface DockButtonProps {
  label: string;
  icon: React.ReactNode;
  onPress: () => void;
}

const DockButton: React.FC<DockButtonProps> = ({ label, icon, onPress }) => (
  <Pressable
    onPress={onPress}
    accessibilityRole="button"
    accessibilityLabel={label}
    style={({ pressed }) => [styles.dockBtn, pressed && styles.dockBtnPressed]}
  >
    {icon}
    <Text style={styles.dockBtnLabel}>{label}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#080f1e',
  },
  topBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  iconBtn: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.12)',
    backgroundColor: 'rgba(0, 240, 255, 0.04)',
  },
  iconBtnActive: {
    borderColor: 'rgba(32, 244, 255, 0.55)',
    backgroundColor: 'rgba(32, 244, 255, 0.12)',
  },
  // Centered "logo" — mirrors the website's .mc-brand strip
  // (.arc-reactor halo + h1 ARBITER + .brand-sub MISSION CONTROL).
  brand: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  brandText: {
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  // Arc-reactor halo. Outer disc is a soft cyan wash that doubles as
  // the iOS shadow source; inner ring is the crisp 2px cyan border.
  haloOuter: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 240, 255, 0.10)',
    shadowColor: '#20f4ff',
    shadowOpacity: 0.7,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 0 },
  },
  haloRing: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: '#20f4ff',
    backgroundColor: 'rgba(0, 240, 255, 0.05)',
  },
  brandTitle: {
    color: '#20f4ff',
    fontSize: 15,
    fontWeight: '200',
    letterSpacing: 5,
    textShadowColor: 'rgba(0, 240, 255, 0.45)',
    textShadowRadius: 8,
    textShadowOffset: { width: 0, height: 0 },
  },
  brandSub: {
    color: '#9fc4dc',
    fontFamily: HUD_FONTS.mono,
    fontSize: 8,
    letterSpacing: 2.4,
  },
  orbWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  panelRail: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    borderLeftWidth: 1,
    borderLeftColor: 'rgba(0, 240, 255, 0.16)',
    backgroundColor: 'rgba(6, 12, 28, 0.55)',
  },
  dock: {
    position: 'absolute',
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    // Gap + paddings tuned so 3 buttons fit a 320pt iPad Slide Over
    // window (84*3 + 10*2 + 12*2 = 296 ≤ 320) without altering the
    // iPhone cluster width.
    gap: 10,
    paddingHorizontal: 12,
  },
  dockBtn: {
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 12,
    minWidth: 84,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(32, 244, 255, 0.22)',
    backgroundColor: 'rgba(8, 24, 40, 0.72)',
  },
  dockBtnPressed: {
    borderColor: 'rgba(32, 244, 255, 0.55)',
    backgroundColor: 'rgba(32, 244, 255, 0.10)',
  },
  dockBtnLabel: {
    color: '#bfe6ff',
    fontSize: 13,
    letterSpacing: 0.5,
  },
  // Notification-shaped card. Right-pinned, max ~320 wide, sits just
  // below the top bar. Severity styling follows the website's
  // .notif-banner.warning (3px amber left border, tinted background).
  notifBanner: {
    position: 'absolute',
    right: 16,
    maxWidth: 320,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    paddingLeft: 12,
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#ffb454',
    backgroundColor: 'rgba(40, 24, 4, 0.88)',
    shadowColor: '#ffb454',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 2 },
  },
  notifBody: {
    flex: 1,
    minWidth: 0,
  },
  notifSource: {
    color: '#ffd980',
    fontFamily: HUD_FONTS.mono,
    fontSize: 10,
    letterSpacing: 1.5,
    opacity: 0.75,
    marginBottom: 3,
  },
  notifMessage: {
    color: '#e8f4ff',
    fontFamily: HUD_FONTS.mono,
    fontSize: 12,
    lineHeight: 16,
  },
  voiceBanner: {
    position: 'absolute',
    left: 16,
    right: 16,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(32, 244, 255, 0.45)',
    backgroundColor: 'rgba(8, 24, 40, 0.82)',
    alignItems: 'center',
  },
  voiceBannerError: {
    borderColor: 'rgba(220, 80, 80, 0.55)',
    backgroundColor: 'rgba(60, 8, 12, 0.78)',
  },
  voiceBannerText: {
    color: '#e8f4ff',
    fontSize: 14,
    letterSpacing: 0.3,
    textAlign: 'center',
  },
});
