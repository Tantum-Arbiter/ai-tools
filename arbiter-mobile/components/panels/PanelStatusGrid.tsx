// Status grid panel — list of labelled items each with a colored status
// dot. Mirrors the website's `.status-grid` block; used for service /
// region health summaries.

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { StatusRow } from '../HUD';
import type { StatusGridSpec } from '../../lib/types';

export interface PanelStatusGridProps {
  grid: StatusGridSpec;
}

export const PanelStatusGrid: React.FC<PanelStatusGridProps> = ({ grid }) => {
  const items = Array.isArray(grid?.items) ? grid.items : [];
  if (items.length === 0) return null;
  return (
    <View style={styles.wrap}>
      {items.map((it, i) => (
        <StatusRow
          key={`${it.label ?? 'item'}-${i}`}
          status={it.status}
          label={String(it.label ?? '')}
          {...(it.note ? { note: it.note } : {})}
        />
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: { gap: 0 },
});

export default PanelStatusGrid;
