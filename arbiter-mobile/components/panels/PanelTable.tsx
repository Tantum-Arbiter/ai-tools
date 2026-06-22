// Table panel — narrow tabular renderer for chat-returned tables. Caps
// columns to keep things readable on a phone and horizontally scrolls
// when the headers don't fit.

import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { HUD_COLORS, HUD_FONTS } from '../HUD/tokens';
import type { TableSpec } from '../../lib/types';

export interface PanelTableProps {
  table: TableSpec;
  maxRows?: number;
}

const COL_MIN_WIDTH = 96;

export const PanelTable: React.FC<PanelTableProps> = ({ table, maxRows = 12 }) => {
  const columns = Array.isArray(table?.columns) ? table.columns : [];
  const rows = Array.isArray(table?.rows) ? table.rows : [];
  if (columns.length === 0 || rows.length === 0) return null;
  const visibleRows = rows.slice(0, maxRows);

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <View>
        <View style={[styles.row, styles.headerRow]}>
          {columns.map((c, i) => (
            <Text key={`h-${i}`} style={[styles.cell, styles.headerCell]} numberOfLines={1}>
              {String(c)}
            </Text>
          ))}
        </View>
        {visibleRows.map((row, ri) => (
          <View key={`r-${ri}`} style={[styles.row, ri % 2 === 1 && styles.zebraRow]}>
            {columns.map((_, ci) => (
              <Text key={`r-${ri}-c-${ci}`} style={styles.cell} numberOfLines={1}>
                {row?.[ci] == null ? '' : String(row[ci])}
              </Text>
            ))}
          </View>
        ))}
        {rows.length > visibleRows.length && (
          <Text style={styles.more}>
            +{rows.length - visibleRows.length} more rows
          </Text>
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  headerRow: { borderBottomWidth: 1, borderBottomColor: HUD_COLORS.divider, paddingBottom: 4 },
  zebraRow: { backgroundColor: 'rgba(0,240,255,0.03)' },
  cell: {
    minWidth: COL_MIN_WIDTH,
    paddingHorizontal: 8,
    paddingVertical: 6,
    color: HUD_COLORS.textBright,
    fontSize: 13,
    fontFamily: HUD_FONTS.mono,
  },
  headerCell: {
    color: HUD_COLORS.cyan,
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontSize: 11,
  },
  more: { color: HUD_COLORS.textDim, fontSize: 12, paddingTop: 6, paddingHorizontal: 8 },
});

export default PanelTable;
