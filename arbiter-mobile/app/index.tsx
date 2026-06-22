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
import {
  Activity,
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
import { useApi, useCredentials } from '../lib/credentials';
import { useSettingsOverlay } from '../lib/settingsOverlay';
import { useVoiceSession } from '../components/Voice/useVoiceSession';

const DRAWER_COLLAPSED = 84;
// Fraction of viewport height the chat occupies when expanded. Operator
// asked for a small, focused panel — kept at 20% so the orb stays the
// dominant element.
const DRAWER_EXPANDED = 0.20;
// Tablet split-layout breakpoint. iPad mini portrait = 768 — anything
// at or above that gets the right-rail PanelFeed.
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

  return (
    <View style={styles.root}>
      <TronBackground width={width} height={height} />

      <View
        style={[styles.orbWrap, { width: chatColumnWidth, height }]}
        pointerEvents="box-none"
      >
        <Pressable
          onPress={onOrbPress}
          accessibilityRole="button"
          accessibilityLabel="Open chat with Arbiter"
          hitSlop={20}
          style={{ width: orbSize, height: orbSize }}
        >
          <Orb size={orbSize} state={orbState} paused={!isFocused} />
        </Pressable>
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
            <Mic size={18} color="#20f4ff" strokeWidth={2} />
          ) : (
            <MicOff size={18} color="#bfe6ff" strokeWidth={2} />
          )}
        </Pressable>
        <Pressable
          onPress={settings.open}
          accessibilityRole="button"
          accessibilityLabel="Open settings"
          hitSlop={12}
          style={styles.iconBtn}
        >
          <SettingsIcon size={18} color="#bfe6ff" strokeWidth={2} />
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
          actively dictating with the chat closed, to keep that surface
          minimal. */}
      {!(voiceActive && !chatVisible) && (
        <View
          style={[
            styles.dock,
            {
              bottom: insets.bottom + 24,
              right: isTablet ? width - chatColumnWidth : 0,
            },
          ]}
          pointerEvents="box-none"
        >
          <DockButton
            label="Business"
            icon={<BarChart3 size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/business-summary')}
          />
          <DockButton
            label="Uptime"
            icon={<Activity size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/uptime')}
          />
          <DockButton
            label="Orchestration"
            icon={<Network size={20} color="#20f4ff" strokeWidth={2} />}
            onPress={() => router.push('/orchestration')}
          />
        </View>
      )}

      {status === 'unconfigured' && !voiceActive && (
        <Pressable
          onPress={settings.open}
          style={[styles.unconfiguredBanner, { top: insets.top + 56 }]}
          accessibilityRole="button"
          accessibilityLabel="Configure host URL and API key"
        >
          <Text style={styles.unconfiguredText}>
            Host URL + API key not configured — tap to set up
          </Text>
        </Pressable>
      )}

      <ChatDrawer
        api={api}
        visible={chatVisible}
        pendingInput={pendingTranscript}
        expandSignal={expandSignal}
        collapsedHeight={DRAWER_COLLAPSED}
        expandedHeight={height * DRAWER_EXPANDED}
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
    paddingHorizontal: 16,
  },
  iconBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.12)',
    backgroundColor: 'rgba(0, 240, 255, 0.04)',
  },
  iconBtnActive: {
    borderColor: 'rgba(32, 244, 255, 0.55)',
    backgroundColor: 'rgba(32, 244, 255, 0.12)',
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
    gap: 12,
    paddingHorizontal: 16,
  },
  dockBtn: {
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 14,
    minWidth: 96,
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
  unconfiguredBanner: {
    position: 'absolute',
    left: 16,
    right: 16,
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(255, 196, 0, 0.55)',
    backgroundColor: 'rgba(40, 24, 4, 0.82)',
  },
  unconfiguredText: {
    color: '#ffd980',
    fontSize: 14,
    letterSpacing: 0.3,
    textAlign: 'center',
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
