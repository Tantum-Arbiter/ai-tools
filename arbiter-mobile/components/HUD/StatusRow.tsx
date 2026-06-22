// HUD StatusRow — single-line item with a colored status dot, a label,
// and an optional right-side note. Used inside Panels for service and
// region grids.

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { HUD_COLORS, HUD_FONTS, statusColor } from './tokens';

export interface StatusDotProps {
  status: string | undefined;
  size?: number;
  glow?: boolean;
}

export const StatusDot: React.FC<StatusDotProps> = ({ status, size = 8, glow = true }) => {
  const color = statusColor(status);
  return (
    <View
      style={[
        styles.dot,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: color,
          ...(glow
            ? {
                shadowColor: color,
                shadowOpacity: 0.85,
                shadowRadius: 4,
                shadowOffset: { width: 0, height: 0 },
              }
            : null),
        },
      ]}
    />
  );
};

export interface StatusRowProps {
  status: string | undefined;
  label: string;
  note?: string;
  /** Optional value rendered in mono on the right (instead of `note`). */
  value?: string;
}

export const StatusRow: React.FC<StatusRowProps> = ({ status, label, note, value }) => (
  <View style={styles.row}>
    <StatusDot status={status} />
    <Text style={styles.label} numberOfLines={1}>
      {label}
    </Text>
    {value ? (
      <Text style={styles.value} numberOfLines={1}>
        {value}
      </Text>
    ) : note ? (
      <Text style={styles.note} numberOfLines={1}>
        {note}
      </Text>
    ) : null}
  </View>
);

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 6,
  },
  dot: {},
  label: {
    color: HUD_COLORS.textBright,
    fontSize: 13,
    flexShrink: 1,
    flex: 1,
  },
  note: {
    color: HUD_COLORS.textDim,
    fontSize: 11,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  value: {
    color: HUD_COLORS.cyan,
    fontSize: 12,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 0.5,
  },
});

export default StatusRow;
