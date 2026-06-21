// Main screen: orb hero + chat drawer. The orb is absolutely centred on
// the full viewport so the chat drawer floats over it without nudging
// its position. The Tron grid + radial illumination matches the desktop
// dashboard (static/style.css body::before / body::after).

import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Link } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Settings as SettingsIcon } from 'lucide-react-native';
import { Orb } from '../components/Orb/Orb';
import { ChatDrawer } from '../components/Chat/ChatDrawer';
import { TronBackground } from '../components/Background/TronBackground';
import { useApi, useCredentials } from '../lib/credentials';

const DRAWER_COLLAPSED = 84;
const DRAWER_EXPANDED = 0.55;

export default function Home() {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const api = useApi();
  const { status } = useCredentials();

  const orbSize = Math.min(width, height) * 0.7;
  const orbOpacity = useSharedValue(1);
  const [drawerExpanded, setDrawerExpanded] = useState(false);

  const orbStyle = useAnimatedStyle(() => ({ opacity: orbOpacity.value }));

  const onExpansionChange = (expanded: boolean) => {
    setDrawerExpanded(expanded);
    orbOpacity.value = withTiming(expanded ? 0.25 : 1, { duration: 220 });
  };

  return (
    <View style={styles.root}>
      <TronBackground width={width} height={height} />

      <Animated.View
        style={[styles.orbWrap, orbStyle, { width, height }]}
        pointerEvents="none"
      >
        <Orb size={orbSize} state="idle" />
      </Animated.View>

      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]} pointerEvents="box-none">
        <Link href="/settings" asChild>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open settings"
            hitSlop={12}
            style={styles.settingsBtn}
          >
            <SettingsIcon size={18} color="#bfe6ff" strokeWidth={2} />
          </Pressable>
        </Link>
      </View>

      {status === 'unconfigured' && !drawerExpanded && (
        <View
          style={[styles.unconfiguredBanner, { bottom: DRAWER_COLLAPSED + insets.bottom + 20 }]}
          pointerEvents="none"
        >
          <Text style={styles.unconfiguredText}>
            Tap the settings icon to configure host + API key
          </Text>
        </View>
      )}

      <ChatDrawer
        api={api}
        collapsedHeight={DRAWER_COLLAPSED + insets.bottom}
        expandedHeight={height * DRAWER_EXPANDED + insets.bottom}
        onExpansionChange={onExpansionChange}
      />
    </View>
  );
}

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
    justifyContent: 'flex-end',
    paddingHorizontal: 16,
  },
  settingsBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.12)',
    backgroundColor: 'rgba(0, 240, 255, 0.04)',
  },
  orbWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  unconfiguredBanner: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  unconfiguredText: {
    color: '#9fc4dc',
    fontSize: 13,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.18)',
    backgroundColor: 'rgba(2, 6, 18, 0.7)',
  },
});
