// Shared HUD design tokens. Mirrors the website's CSS custom properties
// (see arbiter-mission-control/static/style.css :root) so panels look
// consistent across the mobile and desktop surfaces.

import { Platform } from 'react-native';

export const HUD_COLORS = {
  bg: '#080f1e',
  panelBg: 'rgba(6, 12, 28, 0.94)',
  panelBgHover: 'rgba(0, 240, 255, 0.06)',
  panelBorder: 'rgba(0, 240, 255, 0.16)',
  panelBorderStrong: 'rgba(32, 244, 255, 0.45)',
  divider: 'rgba(32, 244, 255, 0.12)',
  textBright: '#e8f4ff',
  textMain: '#bfe6ff',
  textDim: '#9fc4dc',
  textMuted: '#5a7a8a',
  cyan: '#20f4ff',
  cyanSoft: '#80dfff',
  green: '#00ff88',
  amber: '#ffb454',
  red: '#ff5454',
  grey: '#5a7a8a',
} as const;

export const HUD_FONTS = {
  mono: Platform.select({ ios: 'Menlo', android: 'monospace' }) ?? 'monospace',
} as const;

export type StatusKind = 'green' | 'amber' | 'red' | 'grey' | 'cyan';

export const STATUS_COLOR: Record<string, string> = {
  green: HUD_COLORS.green,
  ok: HUD_COLORS.green,
  online: HUD_COLORS.green,
  nominal: HUD_COLORS.green,
  amber: HUD_COLORS.amber,
  warning: HUD_COLORS.amber,
  caution: HUD_COLORS.amber,
  red: HUD_COLORS.red,
  error: HUD_COLORS.red,
  alert: HUD_COLORS.red,
  offline: HUD_COLORS.red,
  grey: HUD_COLORS.grey,
  unknown: HUD_COLORS.grey,
  cyan: HUD_COLORS.cyan,
};

export function statusColor(status: string | undefined): string {
  if (!status) return HUD_COLORS.grey;
  return STATUS_COLOR[status.toLowerCase()] ?? HUD_COLORS.grey;
}
