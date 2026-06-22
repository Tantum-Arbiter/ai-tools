// HUD Stat — large mono numeric readout with an uppercase caption,
// optional delta indicator, and tone-driven colour (nominal/caution/
// alert/accent). Mirrors `.dp-val`/`.dp-lbl` from the website.

import React from 'react';
import { StyleSheet, Text, View, type ViewStyle, type StyleProp } from 'react-native';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react-native';
import { HUD_COLORS, HUD_FONTS } from './tokens';

export type StatTone = 'cyan' | 'nominal' | 'caution' | 'alert' | 'accent' | 'dim';

const TONE: Record<StatTone, string> = {
  cyan: HUD_COLORS.cyan,
  nominal: HUD_COLORS.green,
  caution: HUD_COLORS.amber,
  alert: HUD_COLORS.red,
  accent: HUD_COLORS.cyanSoft,
  dim: HUD_COLORS.textDim,
};

export interface StatProps {
  label: string;
  value: string;
  tone?: StatTone;
  delta?: string;
  deltaDir?: 'up' | 'down' | 'flat';
  style?: StyleProp<ViewStyle>;
  /** Block-style stat with left-aligned label below the value. */
  align?: 'left' | 'center';
}

export const Stat: React.FC<StatProps> = ({
  label,
  value,
  tone = 'cyan',
  delta,
  deltaDir,
  style,
  align = 'center',
}) => {
  const color = TONE[tone];
  const isLeft = align === 'left';
  return (
    <View style={[styles.wrap, isLeft ? styles.left : styles.center, style]}>
      <Text style={[styles.value, { color }]} numberOfLines={1}>
        {value}
      </Text>
      <View style={isLeft ? styles.labelRowLeft : styles.labelRowCenter}>
        <Text style={styles.label}>{label}</Text>
        {delta && (
          <View style={styles.deltaWrap}>
            {deltaDir === 'up' && <ArrowUp size={10} color={HUD_COLORS.green} strokeWidth={2.5} />}
            {deltaDir === 'down' && (
              <ArrowDown size={10} color={HUD_COLORS.red} strokeWidth={2.5} />
            )}
            {deltaDir === 'flat' && (
              <Minus size={10} color={HUD_COLORS.textDim} strokeWidth={2.5} />
            )}
            <Text
              style={[
                styles.delta,
                {
                  color:
                    deltaDir === 'up'
                      ? HUD_COLORS.green
                      : deltaDir === 'down'
                        ? HUD_COLORS.red
                        : HUD_COLORS.textDim,
                },
              ]}
            >
              {delta}
            </Text>
          </View>
        )}
      </View>
    </View>
  );
};

export const StatGrid: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <View style={styles.grid}>{children}</View>
);

const styles = StyleSheet.create({
  wrap: { gap: 2 },
  center: { alignItems: 'center' },
  left: { alignItems: 'flex-start' },
  value: {
    fontFamily: HUD_FONTS.mono,
    fontSize: 24,
    fontWeight: '300',
    letterSpacing: 0.5,
  },
  label: {
    color: HUD_COLORS.textDim,
    fontFamily: HUD_FONTS.mono,
    fontSize: 11,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  labelRowCenter: { flexDirection: 'row', alignItems: 'center', gap: 4, justifyContent: 'center' },
  labelRowLeft: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  deltaWrap: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  delta: { fontFamily: HUD_FONTS.mono, fontSize: 11, letterSpacing: 0.5 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, justifyContent: 'space-around' },
});

export default Stat;
