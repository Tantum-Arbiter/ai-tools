// Types used by PanelFeed. Kept in a plain .ts file so the helpers and
// tests don't drag the .tsx renderer into compilation paths that can't
// parse JSX (e.g. the project's jest config which is .ts-only).

import type { Panel } from '../../lib/types';

export interface PanelFeedItem {
  id: string;
  panel: Panel;
  /** ms-since-epoch — used to sort newest-first and as a stable secondary key. */
  timestamp: number;
}
