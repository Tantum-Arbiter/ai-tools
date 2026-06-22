// PanelFeed — reverse-chronological list of analysis panels surfaced by
// the assistant. Used on tablets where the chat lives in the left rail
// and the panel feed gets a dedicated right column. On phones the
// individual PanelCards are rendered inline under the chat bubble.

import React from 'react';
import { FlatList, StyleSheet, Text, View, type ListRenderItem } from 'react-native';
import { HUD_COLORS, HUD_FONTS } from '../HUD/tokens';
import { PanelCard } from './PanelCard';
import type { PanelFeedItem } from './PanelFeedTypes';
import { sortFeedNewestFirst } from './panelHelpers';

export type { PanelFeedItem } from './PanelFeedTypes';

export interface PanelFeedProps {
  items: PanelFeedItem[];
  /** Optional label shown at the top of the feed. */
  title?: string;
  /** Visible when there are no panels yet. */
  emptyLabel?: string;
}

const keyExtractor = (item: PanelFeedItem) => item.id;

export const PanelFeed: React.FC<PanelFeedProps> = ({
  items,
  title = 'PANEL FEED',
  emptyLabel = 'No analyses yet. Ask Arbiter a question that returns data.',
}) => {
  const sorted = React.useMemo(() => sortFeedNewestFirst(items), [items]);

  const renderItem: ListRenderItem<PanelFeedItem> = ({ item }) => (
    <View style={styles.cardWrap} testID={`panel-feed-item-${item.id}`}>
      <PanelCard panel={item.panel} />
    </View>
  );

  return (
    <View style={styles.wrap} testID="panel-feed">
      <Text style={styles.title}>{title}</Text>
      {sorted.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>{emptyLabel}</Text>
        </View>
      ) : (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.listContent}
          data={sorted}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          showsVerticalScrollIndicator={false}
          testID="panel-feed-list"
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 12,
    gap: 8,
  },
  title: {
    color: HUD_COLORS.cyan,
    fontFamily: HUD_FONTS.mono,
    fontSize: 12,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  list: { flex: 1 },
  listContent: { paddingBottom: 24, gap: 12 },
  cardWrap: { width: '100%' },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  emptyText: {
    color: HUD_COLORS.textDim,
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 18,
  },
});

export default PanelFeed;
