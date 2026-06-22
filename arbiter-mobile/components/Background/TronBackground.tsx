// Tron-style grid + radial illumination background, mirroring the
// desktop dashboard's body::before / body::after layers (see
// arbiter-mission-control/static/style.css around line 40-66).
//
// Static — no animation, no per-frame work. Drawn once with SVG so it
// composites cheaply alongside the Skia orb canvas above it. Memoised
// because Home re-renders on every voice interim-transcript / chat
// state tick and re-reconciling 15+ SVG nodes (patterns, masks,
// gradients) is wasted work when nothing visible changes.

import React from 'react';
import { StyleSheet } from 'react-native';
import Svg, {
  Defs,
  Ellipse,
  G,
  Line,
  Mask,
  Pattern,
  RadialGradient,
  Rect,
  Stop,
} from 'react-native-svg';

export interface TronBackgroundProps {
  width: number;
  height: number;
  /**
   * Optional pixel-space centre for the radial fade-mask and the soft
   * blue illumination. Defaults to (width/2, height/2). The home
   * screen overrides this on tablets so the lighting follows the orb
   * into the left column instead of staying glued to the middle of an
   * iPad landscape window. Values are clamped into the visible area.
   */
  centerX?: number;
  centerY?: number;
}

const FINE_STEP = 30;
const MAJOR_STEP = 150;
const FINE_STROKE = 'rgba(0, 240, 255, 0.055)';
const MAJOR_STROKE = 'rgba(0, 240, 255, 0.10)';

const TronBackgroundImpl: React.FC<TronBackgroundProps> = ({
  width,
  height,
  centerX,
  centerY,
}) => {
  const cx = clamp(centerX ?? width * 0.5, 0, width);
  const cy = clamp(centerY ?? height * 0.5, 0, height);
  // Radii scale off the larger axis so an off-centre orb on a wide
  // landscape iPad still throws light across most of the surface, not
  // a small puddle around the column centre.
  const rx = Math.max(width, height) * 0.55;
  const ry = rx;

  return (
    <Svg
      width={width}
      height={height}
      style={StyleSheet.absoluteFill}
      pointerEvents="none"
    >
      <Defs>
        <Pattern id="fine-grid" width={FINE_STEP} height={FINE_STEP} patternUnits="userSpaceOnUse">
          <Line x1="0" y1="0" x2={FINE_STEP} y2="0" stroke={FINE_STROKE} strokeWidth={1} />
          <Line x1="0" y1="0" x2="0" y2={FINE_STEP} stroke={FINE_STROKE} strokeWidth={1} />
        </Pattern>
        <Pattern id="major-grid" width={MAJOR_STEP} height={MAJOR_STEP} patternUnits="userSpaceOnUse">
          <Line x1="0" y1="0" x2={MAJOR_STEP} y2="0" stroke={MAJOR_STROKE} strokeWidth={1} />
          <Line x1="0" y1="0" x2="0" y2={MAJOR_STEP} stroke={MAJOR_STROKE} strokeWidth={1} />
        </Pattern>

        {/* Radial fade — white core, transparent edges. Used as alpha mask
            so the grid feathers out toward the corners. */}
        <RadialGradient
          id="radial-fade"
          cx={cx}
          cy={cy}
          rx={rx}
          ry={ry}
          fx={cx}
          fy={cy}
          gradientUnits="userSpaceOnUse"
        >
          <Stop offset="0" stopColor="#ffffff" stopOpacity={1} />
          <Stop offset="1" stopColor="#ffffff" stopOpacity={0} />
        </RadialGradient>
        <Mask id="fade-mask" maskUnits="userSpaceOnUse" x={0} y={0} width={width} height={height}>
          <Rect x={0} y={0} width={width} height={height} fill="url(#radial-fade)" />
        </Mask>

        {/* Soft blue illumination — matches body::after on the desktop HUD. */}
        <RadialGradient
          id="illumination"
          cx={cx}
          cy={cy}
          rx={rx}
          ry={ry}
          fx={cx}
          fy={cy}
          gradientUnits="userSpaceOnUse"
        >
          <Stop offset="0" stopColor="rgb(0, 180, 255)" stopOpacity={0.24} />
          <Stop offset="0.25" stopColor="rgb(0, 120, 200)" stopOpacity={0.14} />
          <Stop offset="0.5" stopColor="rgb(0, 60, 140)" stopOpacity={0.07} />
          <Stop offset="0.75" stopColor="rgb(0, 10, 30)" stopOpacity={0} />
          <Stop offset="1" stopColor="rgb(0, 10, 30)" stopOpacity={0} />
        </RadialGradient>
      </Defs>

      <G mask="url(#fade-mask)">
        <Rect x={0} y={0} width={width} height={height} fill="url(#fine-grid)" />
        <Rect x={0} y={0} width={width} height={height} fill="url(#major-grid)" />
      </G>

      <Ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="url(#illumination)" />
    </Svg>
  );
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export const TronBackground = React.memo(TronBackgroundImpl);

export default TronBackground;
