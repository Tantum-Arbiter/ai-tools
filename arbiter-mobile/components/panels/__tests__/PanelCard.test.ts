// Tests for the pure helpers behind PanelCard. The view tree itself is
// covered by the integration test on ChatDrawer; here we focus on the
// dispatcher logic that decides what renders natively vs in the WebView.

import { needsWebView, sectionsFromPanel } from '../panelHelpers';
import type { Panel, PanelSection } from '../../../lib/types';

describe('sectionsFromPanel', () => {
  it('returns the sections array when present and non-empty', () => {
    const sectionA: PanelSection = { title: 'A' };
    const sectionB: PanelSection = { title: 'B' };
    const panel: Panel = { title: 't', sections: [sectionA, sectionB] };

    expect(sectionsFromPanel(panel)).toEqual([sectionA, sectionB]);
  });

  it('falls back to a single root section when sections missing', () => {
    const panel: Panel = { title: 't', summary: 's', stats: [{ label: 'x', value: 1 }] };

    const sections = sectionsFromPanel(panel);

    expect(sections).toHaveLength(1);
    expect(sections[0]).toBe(panel);
  });

  it('falls back to a single root section when sections is empty', () => {
    const panel: Panel = { title: 't', sections: [] };

    expect(sectionsFromPanel(panel)).toEqual([panel]);
  });
});

describe('needsWebView', () => {
  it('returns false for purely native sections', () => {
    const s: PanelSection = {
      hero: { value: 42, label: 'MRR' },
      stats: [{ label: 'subs', value: 12 }],
      insights: ['ok'],
    };

    expect(needsWebView(s)).toBe(false);
  });

  it.each([
    ['chart', { chart: { type: 'line' as const, labels: [], datasets: [] } }],
    ['heatmap', { heatmap: { rows: [] } }],
    ['quadrant', { quadrant: { items: [] } }],
    ['calendar_heatmap', { calendar_heatmap: { values: [] } }],
    ['comparison_matrix', { comparison_matrix: { columns: [], rows: [] } }],
  ])('returns true when section contains %s', (_label, partial) => {
    expect(needsWebView(partial as PanelSection)).toBe(true);
  });

  it('treats empty/undefined fields as not requiring the WebView', () => {
    expect(needsWebView({} as PanelSection)).toBe(false);
    expect(needsWebView({ chart: undefined } as unknown as PanelSection)).toBe(false);
  });
});
