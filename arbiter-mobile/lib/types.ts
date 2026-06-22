// On-wire types that mirror arbiter-mission-control/server.py.
// Kept intentionally permissive for less-used panel section shapes so the
// renderer can fall back to the WebView host without breaking type safety.

export type ChatRole = 'user' | 'assistant';

export interface HistoryEntry {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  message: string;
  history: HistoryEntry[];
  // Server gate so it can strip desktop-only actions (e.g. desktop_*) and
  // skip TTS-only formatting when responding to the phone.
  client: 'mobile';
}

export interface ChatResponse {
  reply: string;
  error: boolean;
  panel?: Panel;
  actions?: Action[];
  followups?: string[];
}

export interface VisionRequest {
  query: string;
  image: string; // base64, no data: prefix
}

export type VisionResponse = ChatResponse;

// ── Auth ────────────────────────────────────────────────────────────
export interface AuthCheckResponse {
  auth_required: boolean;
  valid: boolean;
}

// ── Actions ─────────────────────────────────────────────────────────
// The web client supports a wide set (open_browser, launch_app, etc.).
// Mobile renders a safe subset; unknown action types are dropped.
export type Action =
  | { action: 'open_browser'; url: string }
  | { action: 'open_url'; url: string }
  | { action: string; [key: string]: unknown };

export const MOBILE_SAFE_ACTIONS: ReadonlySet<string> = new Set([
  'open_browser',
  'open_url',
]);

// ── Panels ──────────────────────────────────────────────────────────
// A panel may have a flat shape or be split into multiple sections.
export interface Panel {
  title?: string;
  summary?: string;
  sections?: PanelSection[];
  // Section fields may also live at the panel root for single-section panels.
  [k: string]: unknown;
}

export interface PanelSection {
  title?: string;
  // Left-side visuals
  chart?: ChartSpec;
  table?: TableSpec;
  image_url?: string;
  comparison_matrix?: unknown;
  heatmap?: unknown;
  quadrant?: unknown;
  calendar_heatmap?: unknown;
  // Right-side cards
  hero?: HeroSpec;
  status_grid?: StatusGridSpec;
  stats?: StatSpec[];
  key_metrics?: KeyMetricSpec[];
  trend_indicators?: unknown;
  gauges?: unknown;
  scorecard?: unknown;
  funnel?: unknown;
  insights?: string[];
  recommendations?: string[];
  pros_cons?: { pros?: string[]; cons?: string[] };
  swot?: unknown;
  risk_matrix?: unknown;
  timeline?: unknown;
  summary?: string;
  [k: string]: unknown;
}

export type ChartType =
  | 'bar' | 'hbar' | 'line' | 'area' | 'doughnut' | 'pie'
  | 'radar' | 'polarArea' | 'scatter' | 'bubble' | 'stacked'
  | 'candlestick' | 'waterfall';

export interface ChartSpec {
  type: ChartType;
  labels?: string[];
  datasets?: Array<{ label?: string; data: number[]; color?: string }>;
  // candlestick uses ohlc
  ohlc?: Array<{ t: string | number; o: number; h: number; l: number; c: number }>;
  [k: string]: unknown;
}

export interface TableSpec {
  columns: string[];
  rows: Array<Array<string | number | null>>;
}

export interface HeroSpec {
  value: string | number;
  label?: string;
  delta?: string | number;
  delta_dir?: 'up' | 'down' | 'flat';
}

export interface StatSpec {
  label: string;
  value: string | number;
  delta?: string | number;
}

export interface KeyMetricSpec {
  label: string;
  value: string | number;
  trend?: 'up' | 'down' | 'flat';
}

export interface StatusGridSpec {
  items: Array<{ label: string; status: 'green' | 'amber' | 'red' | 'grey'; note?: string }>;
}

// ── Errors ──────────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly kind: 'network' | 'unauthorized' | 'server' | 'parse',
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
