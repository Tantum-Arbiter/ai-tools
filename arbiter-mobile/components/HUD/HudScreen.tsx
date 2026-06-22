// Shared chrome for HUD view screens: back button, mono uppercase title,
// optional refresh affordance, bottom safe-area handling, and the dark
// Tron background. Centralises the boilerplate that business-summary,
// uptime, and orchestration were all copy-pasting. The chrome strip
// sits at the bottom of the screen so the operator's thumb can reach
// back / refresh without crossing the viewport — the title doubles as
// a footer label.

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
  /** Renders directly above the footer chrome (e.g. segmented control). */
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
      {scroll ? (
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + 14, paddingBottom: 24 },
          ]}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.flex, { paddingTop: insets.top + 14 }]}>{children}</View>
      )}
      {headerExtra}
      <View style={[styles.footer, { paddingBottom: insets.bottom + 10 }]}>
        <Pressable
          onPress={onBack}
          hitSlop={12}
          style={styles.iconBtn}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <ArrowLeft size={20} color={HUD_COLORS.textMain} strokeWidth={2} />
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
            <RefreshCw size={20} color={HUD_COLORS.textMain} strokeWidth={2} />
          </Pressable>
        ) : (
          <View style={styles.iconBtnPlaceholder} />
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: HUD_COLORS.bg },
  flex: { flex: 1 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(32, 244, 255, 0.18)',
    backgroundColor: 'rgba(8, 16, 28, 0.92)',
  },
  iconBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(0, 240, 255, 0.18)',
    backgroundColor: 'rgba(0, 240, 255, 0.04)',
  },
  iconBtnPlaceholder: { width: 40, height: 40 },
  title: {
    color: HUD_COLORS.textBright,
    fontSize: 15,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 2.4,
    textTransform: 'uppercase',
  },
  content: { padding: 14, gap: 14 },
});

export default HudScreen;
