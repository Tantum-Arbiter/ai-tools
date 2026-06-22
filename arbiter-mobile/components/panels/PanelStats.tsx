// Stats grid panel — small uniform readouts laid out in a wrap row. Used
// for compact key/value summaries returned by analysis prompts.

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Stat } from '../HUD';
import type { StatSpec, KeyMetricSpec } from '../../lib/types';

export interface PanelStatsProps {
  stats?: StatSpec[];
  keyMetrics?: KeyMetricSpec[];
}

export const PanelStats: React.FC<PanelStatsProps> = ({ stats, keyMetrics }) => {
  const items: Array<{
    label: string;
    value: string;
    delta?: string;
    deltaDir?: 'up' | 'down' | 'flat';
  }> = [];

  for (const s of stats ?? []) {
    if (!s || typeof s.label !== 'string') continue;
    const entry: (typeof items)[number] = {
      label: s.label,
      value: String(s.value ?? ''),
    };
    if (s.delta !== undefined) entry.delta = String(s.delta);
    items.push(entry);
  }
  for (const m of keyMetrics ?? []) {
    if (!m || typeof m.label !== 'string') continue;
    const entry: (typeof items)[number] = {
      label: m.label,
      value: String(m.value ?? ''),
    };
    if (m.trend) entry.deltaDir = m.trend;
    items.push(entry);
  }

  if (items.length === 0) return null;

  return (
    <View style={styles.grid}>
      {items.map((it, i) => (
        <View key={`${it.label}-${i}`} style={styles.cell}>
          <Stat
            label={it.label}
            value={it.value}
            tone="cyan"
            align="center"
            {...(it.delta !== undefined ? { delta: it.delta } : {})}
            {...(it.deltaDir ? { deltaDir: it.deltaDir } : {})}
          />
        </View>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, justifyContent: 'space-around' },
  cell: { minWidth: 96, paddingVertical: 4 },
});

export default PanelStats;
