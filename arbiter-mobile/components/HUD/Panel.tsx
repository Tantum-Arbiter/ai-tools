// HUD Panel — the base container for dashboard content. Matches the
// website's `.dock-panel` art direction: dark glassy background, thin
// cyan border, sharp 4px corners, optional uppercase mono title.

import React from 'react';
import { StyleSheet, Text, View, type ViewStyle, type StyleProp } from 'react-native';
import { HUD_COLORS, HUD_FONTS } from './tokens';

export interface PanelProps {
  title?: string;
  /** Right-aligned text in the header row (e.g. counter or status). */
  rightSlot?: React.ReactNode;
  /** Narrow accent stripe on the left edge; useful for status grouping. */
  accent?: string;
  style?: StyleProp<ViewStyle>;
  bodyStyle?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
}

export const Panel: React.FC<PanelProps> = ({
  title,
  rightSlot,
  accent,
  style,
  bodyStyle,
  children,
}) => (
  <View style={[styles.panel, !!accent && { borderLeftColor: accent, borderLeftWidth: 2 }, style]}>
    {(title || rightSlot) && (
      <View style={styles.header}>
        {title && <Text style={styles.title}>{title}</Text>}
        {rightSlot ? <View style={styles.right}>{rightSlot}</View> : null}
      </View>
    )}
    <View style={[styles.body, bodyStyle]}>{children}</View>
  </View>
);

export interface PanelHeadingProps {
  children: React.ReactNode;
}

export const PanelHeading: React.FC<PanelHeadingProps> = ({ children }) => (
  <Text style={styles.title}>{children}</Text>
);

export const PanelDivider: React.FC = () => <View style={styles.divider} />;

const styles = StyleSheet.create({
  panel: {
    backgroundColor: HUD_COLORS.panelBg,
    borderWidth: 1,
    borderColor: HUD_COLORS.panelBorder,
    borderRadius: 4,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 10,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  title: {
    color: HUD_COLORS.cyan,
    fontFamily: HUD_FONTS.mono,
    fontSize: 11,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  right: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  body: { gap: 8 },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: HUD_COLORS.divider,
    marginVertical: 4,
  },
});

export default Panel;
