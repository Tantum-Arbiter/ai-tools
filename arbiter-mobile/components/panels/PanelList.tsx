// Bulleted list panel — used for insights/recommendations sections.
// Renders a vertical column of leader-dotted text rows with a section
// caption.

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { HUD_COLORS, HUD_FONTS } from '../HUD/tokens';

export interface PanelListProps {
  caption: string;
  items: string[];
  tone?: 'info' | 'positive' | 'negative';
}

const CAPTION_COLOR: Record<NonNullable<PanelListProps['tone']>, string> = {
  info: HUD_COLORS.cyan,
  positive: HUD_COLORS.green,
  negative: HUD_COLORS.red,
};

const BULLET_COLOR: Record<NonNullable<PanelListProps['tone']>, string> = {
  info: HUD_COLORS.cyanSoft,
  positive: HUD_COLORS.green,
  negative: HUD_COLORS.red,
};

export const PanelList: React.FC<PanelListProps> = ({ caption, items, tone = 'info' }) => {
  const cleaned = (items ?? []).filter((s): s is string => typeof s === 'string' && s.length > 0);
  if (cleaned.length === 0) return null;
  return (
    <View style={styles.wrap}>
      <Text style={[styles.caption, { color: CAPTION_COLOR[tone] }]}>{caption}</Text>
      {cleaned.map((line, i) => (
        <View key={`${caption}-${i}`} style={styles.row}>
          <Text style={[styles.bullet, { color: BULLET_COLOR[tone] }]}>›</Text>
          <Text style={styles.text}>{line}</Text>
        </View>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: { gap: 4 },
  caption: {
    fontFamily: HUD_FONTS.mono,
    fontSize: 11,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  row: { flexDirection: 'row', gap: 8, paddingVertical: 2 },
  bullet: { fontFamily: HUD_FONTS.mono, fontSize: 14, lineHeight: 19 },
  text: { color: HUD_COLORS.textBright, fontSize: 14, lineHeight: 19, flex: 1 },
});

export default PanelList;
