// Public surface for HUD primitives. Import from `components/HUD` so
// individual primitive files can move/split without touching callers.

export { Panel, PanelHeading, PanelDivider } from './Panel';
export type { PanelProps, PanelHeadingProps } from './Panel';

export { Stat, StatGrid } from './Stat';
export type { StatProps, StatTone } from './Stat';

export { StatusRow, StatusDot } from './StatusRow';
export type { StatusRowProps, StatusDotProps } from './StatusRow';

export { Sparkline } from './Sparkline';
export type { SparklineProps } from './Sparkline';

export { HudScreen } from './HudScreen';
export type { HudScreenProps } from './HudScreen';

export { HUD_COLORS, HUD_FONTS, STATUS_COLOR, statusColor } from './tokens';
export type { StatusKind } from './tokens';
