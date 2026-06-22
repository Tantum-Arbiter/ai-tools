import { sortFeedNewestFirst } from '../panelHelpers';
import type { PanelFeedItem } from '../PanelFeedTypes';

const item = (id: string, timestamp: number): PanelFeedItem => ({
  id,
  timestamp,
  panel: { title: id },
});

describe('sortFeedNewestFirst', () => {
  it('returns newest panels first without mutating the input', () => {
    const a = item('a', 1_700_000_000_000);
    const b = item('b', 1_700_000_500_000);
    const c = item('c', 1_700_000_250_000);
    const input = [a, b, c];

    const sorted = sortFeedNewestFirst(input);

    expect(sorted.map((i) => i.id)).toEqual(['b', 'c', 'a']);
    // Original array order is preserved.
    expect(input.map((i) => i.id)).toEqual(['a', 'b', 'c']);
  });

  it('handles empty input', () => {
    expect(sortFeedNewestFirst([])).toEqual([]);
  });

  it('preserves order for equal timestamps (stable enough for chat usage)', () => {
    const a = item('a', 1);
    const b = item('b', 1);
    const c = item('c', 2);

    const sorted = sortFeedNewestFirst([a, b, c]);

    expect(sorted[0]?.id).toBe('c');
    // a and b had identical timestamps so we don't assert their relative order.
    expect(new Set(sorted.slice(1).map((i) => i.id))).toEqual(new Set(['a', 'b']));
  });
});
