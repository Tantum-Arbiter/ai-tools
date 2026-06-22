// PanelCard — top-level dispatcher for a server-returned Panel. Splits
// sections, renders the parts we have native support for (hero, stats,
// status grid, insights, recommendations, pros/cons, summary, table),
// and falls back to the WebView renderer for sections with chart /
// heatmap / quadrant / calendar_heatmap / comparison_matrix content.

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Panel as PanelChrome } from '../HUD';
import { HUD_COLORS, HUD_FONTS } from '../HUD/tokens';
import type { Panel, PanelSection } from '../../lib/types';
import PanelHero from './PanelHero';
import PanelStats from './PanelStats';
import PanelStatusGrid from './PanelStatusGrid';
import PanelList from './PanelList';
import PanelTable from './PanelTable';
import PanelWebView from './PanelWebView';
import { needsWebView, sectionsFromPanel } from './panelHelpers';

export interface PanelCardProps {
  panel: Panel;
  /** Override the WebView fallback component (used by tests). */
  WebViewComponent?: typeof PanelWebView;
}

export const PanelCard: React.FC<PanelCardProps> = ({ panel, WebViewComponent = PanelWebView }) => {
  if (!panel || typeof panel !== 'object') return null;
  const sections = sectionsFromPanel(panel);
  const title = typeof panel.title === 'string' ? panel.title : 'ANALYSIS';

  return (
    <PanelChrome title={title} style={styles.outer}>
      {typeof panel.summary === 'string' && panel.summary.length > 0 && (
        <Text style={styles.summary}>{panel.summary}</Text>
      )}
      {sections.map((section, i) => (
        <PanelSectionView
          key={`s-${i}`}
          section={section}
          WebViewComponent={WebViewComponent}
        />
      ))}
    </PanelChrome>
  );
};

interface SectionViewProps {
  section: PanelSection;
  WebViewComponent: typeof PanelWebView;
}

export const PanelSectionView: React.FC<SectionViewProps> = ({ section, WebViewComponent }) => {
  if (!section || typeof section !== 'object') return null;
  const blocks: React.ReactNode[] = [];

  if (typeof section.title === 'string' && section.title.length > 0) {
    blocks.push(<Text key="t" style={styles.sectionTitle}>{section.title}</Text>);
  }
  if (section.hero && typeof section.hero === 'object') {
    blocks.push(<PanelHero key="hero" hero={section.hero} />);
  }
  if (
    (Array.isArray(section.stats) && section.stats.length > 0) ||
    (Array.isArray(section.key_metrics) && section.key_metrics.length > 0)
  ) {
    blocks.push(
      <PanelStats
        key="stats"
        {...(Array.isArray(section.stats) ? { stats: section.stats } : {})}
        {...(Array.isArray(section.key_metrics) ? { keyMetrics: section.key_metrics } : {})}
      />,
    );
  }
  if (section.status_grid && typeof section.status_grid === 'object') {
    blocks.push(<PanelStatusGrid key="sg" grid={section.status_grid} />);
  }
  if (Array.isArray(section.insights) && section.insights.length > 0) {
    blocks.push(<PanelList key="ins" caption="Insights" items={section.insights} tone="info" />);
  }
  if (Array.isArray(section.recommendations) && section.recommendations.length > 0) {
    blocks.push(
      <PanelList key="rec" caption="Recommendations" items={section.recommendations} tone="info" />,
    );
  }
  if (section.pros_cons && typeof section.pros_cons === 'object') {
    const pc = section.pros_cons as { pros?: string[]; cons?: string[] };
    if (Array.isArray(pc.pros) && pc.pros.length > 0) {
      blocks.push(<PanelList key="pros" caption="Pros" items={pc.pros} tone="positive" />);
    }
    if (Array.isArray(pc.cons) && pc.cons.length > 0) {
      blocks.push(<PanelList key="cons" caption="Cons" items={pc.cons} tone="negative" />);
    }
  }
  if (section.table && typeof section.table === 'object' && !needsWebView(section)) {
    // Standalone tables render natively; tables inside chart-bearing
    // sections fall through to the WebView so layout stays consistent.
    blocks.push(<PanelTable key="tbl" table={section.table} />);
  }
  if (typeof section.summary === 'string' && section.summary.length > 0) {
    blocks.push(<Text key="sum" style={styles.summary}>{section.summary}</Text>);
  }
  if (needsWebView(section)) {
    blocks.push(<WebViewComponent key="wv" panel={{ sections: [section] }} />);
  }

  if (blocks.length === 0) return null;
  return <View style={styles.section}>{blocks}</View>;
};

const styles = StyleSheet.create({
  outer: { marginTop: 6 },
  section: { gap: 10, paddingTop: 4 },
  sectionTitle: {
    color: HUD_COLORS.cyanSoft,
    fontFamily: HUD_FONTS.mono,
    fontSize: 11,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  summary: { color: HUD_COLORS.textBright, fontSize: 14, lineHeight: 20 },
});

export default PanelCard;
