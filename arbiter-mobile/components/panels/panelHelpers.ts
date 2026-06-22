// Pure helpers for the panel renderers. Kept in a separate .ts file so
// unit tests (jest is .ts-only here) can import them without trying to
// parse the JSX in the renderer components.

import type { Panel, PanelSection } from '../../lib/types';
import type { PanelFeedItem } from './PanelFeedTypes';

const WEBVIEW_FIELDS = [
  'chart',
  'heatmap',
  'quadrant',
  'calendar_heatmap',
  'comparison_matrix',
] as const;

export function sectionsFromPanel(panel: Panel): PanelSection[] {
  if (panel && Array.isArray(panel.sections) && panel.sections.length > 0) {
    return panel.sections as PanelSection[];
  }
  return [panel as PanelSection];
}

export function needsWebView(section: PanelSection): boolean {
  return WEBVIEW_FIELDS.some((f) => section?.[f] != null);
}

/** Return a new array sorted newest-first by `timestamp`; never mutates input. */
export function sortFeedNewestFirst(items: PanelFeedItem[]): PanelFeedItem[] {
  return [...items].sort((a, b) => b.timestamp - a.timestamp);
}
