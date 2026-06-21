// Main screen: orb hero + chat drawer. The orb fades down as the
// drawer expands so the keyboard + history have visual focus.

import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Link } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Orb } from '../components/Orb/Orb';
import { ChatDrawer } from '../components/Chat/ChatDrawer';
import { useApi, useCredentials } from '../lib/credentials';

const DRAWER_COLLAPSED = 84;
const DRAWER_EXPANDED = 0.55; // fraction of screen height

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
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Link href="/settings" asChild>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open settings"
            hitSlop={12}
            style={styles.settingsBtn}
          >
            <Text style={styles.settingsBtnText}>⚙</Text>
          </Pressable>
        </Link>
      </View>

      <Animated.View style={[styles.orbWrap, orbStyle]} pointerEvents="none">
        <Orb size={orbSize} state="idle" />
      </Animated.View>

      {status === 'unconfigured' && !drawerExpanded && (
        <View style={styles.unconfiguredBanner} pointerEvents="none">
          <Text style={styles.unconfiguredText}>
            Tap ⚙ to configure host + API key
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
    backgroundColor: '#000814',
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  settingsBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: 'rgba(120, 200, 255, 0.10)',
  },
  settingsBtnText: { color: '#bfe6ff', fontSize: 18, lineHeight: 22 },
  orbWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  unconfiguredBanner: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 110,
    alignItems: 'center',
  },
  unconfiguredText: {
    color: '#9fc4dc',
    fontSize: 13,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 10,
    backgroundColor: 'rgba(0, 8, 20, 0.6)',
  },
});
