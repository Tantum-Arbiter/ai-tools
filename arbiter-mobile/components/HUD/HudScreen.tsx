// Shared chrome for HUD view screens: back button, mono uppercase title,
// optional refresh affordance, top safe-area handling, and the dark Tron
// background. Centralises the boilerplate that business-summary,
// uptime, and orchestration were all copy-pasting.

import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Stack } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ArrowLeft, RefreshCw } from 'lucide-react-native';
import { HUD_COLORS, HUD_FONTS } from './tokens';

export interface HudScreenProps {
  title: string;
  onBack: () => void;
  onRefresh?: () => void;
  /** Renders below the title in the header strip (e.g. segmented control). */
  headerExtra?: React.ReactNode;
  /** When true, content is rendered without the inner ScrollView so the
   *  caller can compose its own. Defaults to false. */
  scroll?: boolean;
  children?: React.ReactNode;
}

export const HudScreen: React.FC<HudScreenProps> = ({
  title,
  onBack,
  onRefresh,
  headerExtra,
  scroll = true,
  children,
}) => {
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.root}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable
          onPress={onBack}
          hitSlop={12}
          style={styles.iconBtn}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <ArrowLeft size={18} color={HUD_COLORS.textMain} strokeWidth={2} />
        </Pressable>
        <Text style={styles.title}>{title}</Text>
        {onRefresh ? (
          <Pressable
            onPress={onRefresh}
            hitSlop={12}
            style={styles.iconBtn}
            accessibilityRole="button"
            accessibilityLabel="Refresh"
          >
            <RefreshCw size={18} color={HUD_COLORS.textMain} strokeWidth={2} />
          </Pressable>
        ) : (
          <View style={styles.iconBtnPlaceholder} />
        )}
      </View>
      {headerExtra}
      {scroll ? (
        <ScrollView
          contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}
        >
          {children}
        </ScrollView>
      ) : (
        children
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: HUD_COLORS.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(32, 244, 255, 0.18)',
  },
  iconBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.18)',
    backgroundColor: 'rgba(0, 240, 255, 0.04)',
  },
  iconBtnPlaceholder: { width: 36, height: 36 },
  title: {
    color: HUD_COLORS.textBright,
    fontSize: 12,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 2.2,
    textTransform: 'uppercase',
  },
  content: { padding: 14, gap: 14 },
});

export default HudScreen;
