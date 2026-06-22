// Pure projection from OrbFrame → typed draw specs in pixel space.
// Keeps the Skia view dumb: it just iterates these arrays.

import { COMPASS_RINGS, type OrbFrame, type RGB } from './orbSimulation';

export interface DrawableCircle {
  cx: number;
  cy: number;
  r: number;
  color: RGB;
  opacity: number;
}

export interface DrawableRing {
  cx: number;
  cy: number;
  r: number;
  strokeWidth: number;
  color: RGB;
  opacity: number;
}

// Radial tick mark in centred polar coordinates (origin = orb centre).
// Rendering layer translates + rotates a Group, then draws each tick as
// a line from cos(angle)*innerR..outerR. Keeping ticks as polar tuples
// lets the simulation's rotation drive the whole array via one rotate.
export interface TickSpec {
  angle: number;
  innerR: number;
  outerR: number;
  opacity: number;
  strokeWidth: number;
}

export interface OuterHaloSpec {
  cx: number;
  cy: number;
  rotation: number;
  r: number;       // outer ring circle radius
  innerR: number;  // inner faint ring circle radius
  color: RGB;
  ringOpacity: number;     // outer ring stroke opacity
  innerRingOpacity: number;
  ticks: TickSpec[];       // 120 tick marks
  cogs: TickSpec[];        // 12 cog teeth (rendered as thick radial bars)
}

export interface CompassRingSpec {
  cx: number;
  cy: number;
  rotation: number;
  r: number;
  strokeWidth: number;
  color: RGB;
  opacity: number;
  ticks: TickSpec[];
}

export interface OrbDrawSpec {
  size: number;
  cx: number;
  cy: number;
  color: RGB;
  outerGlow: DrawableCircle;
  outerHalo: OuterHaloSpec;
  halo: DrawableCircle;
  core: DrawableCircle;
  particles: DrawableCircle[];
  waveformRing: DrawableRing | null;
  compassRings: CompassRingSpec[];
}

const CORE_R_FRAC = 0.06;
const HALO_R_FRAC = 1.6;
const NEBULA_MAX_R_FRAC = 0.36; // matches Orb.maxR (size * 0.36)
const WAVE_BASE_FRAC = 0.28; // matches jarvis.js _drawWaveformRing baseR
const WAVE_AMP_FRAC = 0.35;
const OUTER_HALO_R_FRAC = 1.28;       // jarvis: maxR * 1.28
const OUTER_GLOW_R_FRAC = 1.2;        // jarvis: maxR * 1.2 * pulse
const HALO_TICK_COUNT = 120;
const HALO_BIG_TICK_EVERY = 10;
const HALO_TICK_LEN = 7;
const HALO_COG_COUNT = 12;

export function frameToDrawables(frame: OrbFrame, size: number): OrbDrawSpec {
  const s = Math.max(10, size);
  const cx = s / 2;
  const cy = s / 2;
  const maxR = s * NEBULA_MAX_R_FRAC;
  const color = frame.color;
  const vb = clamp01(frame.voiceBlend);

  // Halo: large soft glow behind everything. Opacity strengthens with audio.
  const halo: DrawableCircle = {
    cx, cy,
    r: maxR * HALO_R_FRAC,
    color,
    opacity: 0.08 + frame.audioLevel * 0.08,
  };

  // Core: bright dot at the centre, pulses subtly with audio.
  const core: DrawableCircle = {
    cx, cy,
    r: maxR * CORE_R_FRAC * (1 + frame.audioLevel * 0.4),
    color,
    opacity: 0.85,
  };

  // Particles: blend between nebula (random) and waveform ring (slot-based).
  const ringBaseR = maxR * WAVE_BASE_FRAC;
  const ringMaxAmp = maxR * WAVE_AMP_FRAC;
  const bands = frame.waveData.length;
  const particles: DrawableCircle[] = new Array(frame.particles.length);
  for (let i = 0; i < frame.particles.length; i++) {
    const p = frame.particles[i]!;
    // Nebula position
    const nebR = p.dist * maxR;
    const nebX = cx + Math.cos(p.angle) * nebR;
    const nebY = cy + Math.sin(p.angle) * nebR;
    // Ring slot position — uses precomputed ringAngle and waveData band
    const band = frame.waveData[i % bands] ?? 0;
    const ringR = ringBaseR + band * ringMaxAmp;
    const ringX = cx + Math.cos(p.ringAngle) * ringR;
    const ringY = cy + Math.sin(p.ringAngle) * ringR;
    // Linear blend
    const x = nebX * (1 - vb) + ringX * vb;
    const y = nebY * (1 - vb) + ringY * vb;
    // Twinkle from sin(time)
    const twinkle = 0.5 + 0.5 * Math.sin(frame.time * p.twinkleSpeed + p.phase);
    particles[i] = {
      cx: x,
      cy: y,
      r: p.size,
      color,
      opacity: clamp01(p.brightness * (0.4 + twinkle * 0.6)),
    };
  }

  // Waveform ring outline — only when voice is engaging.
  const waveformRing: DrawableRing | null = vb > 0.01
    ? {
        cx, cy,
        r: ringBaseR,
        strokeWidth: 1.5,
        color,
        opacity: vb * (0.25 + frame.audioLevel * 0.4),
      }
    : null;

  // Ambient pulsing radial glow behind everything (jarvis._drawOuterGlow).
  const glowPulse = 1 + Math.sin(frame.time * 1.2) * 0.08;
  const outerGlow: DrawableCircle = {
    cx, cy,
    r: maxR * OUTER_GLOW_R_FRAC * glowPulse,
    color,
    opacity: 0.18,
  };

  // Rotating outer cog halo (jarvis._drawHalo). Geometry in centred polar
  // coords; renderer applies `rotation` as a Group transform.
  const haloR = maxR * OUTER_HALO_R_FRAC;
  const ticks: TickSpec[] = new Array(HALO_TICK_COUNT);
  for (let i = 0; i < HALO_TICK_COUNT; i++) {
    const isBig = i % HALO_BIG_TICK_EVERY === 0;
    const tl = isBig ? HALO_TICK_LEN + 3 : HALO_TICK_LEN;
    ticks[i] = {
      angle: (i / HALO_TICK_COUNT) * Math.PI * 2,
      innerR: haloR - tl,
      outerR: haloR,
      opacity: isBig ? 0.35 : 0.14,
      strokeWidth: isBig ? 1.5 : 0.7,
    };
  }
  // Cog teeth — 12 thick radial bars sitting just outside the halo ring.
  const cogOuter = Math.min(haloR + 8, s * 0.48);
  const cogs: TickSpec[] = new Array(HALO_COG_COUNT);
  for (let i = 0; i < HALO_COG_COUNT; i++) {
    cogs[i] = {
      angle: (i / HALO_COG_COUNT) * Math.PI * 2,
      innerR: haloR - 1,
      outerR: cogOuter,
      opacity: 0.22,
      strokeWidth: 4,
    };
  }
  const outerHalo: OuterHaloSpec = {
    cx, cy,
    rotation: frame.ringAngle,
    r: haloR,
    innerR: haloR - HALO_TICK_LEN - 2,
    color,
    ringOpacity: 0.16,
    innerRingOpacity: 0.08,
    ticks,
    cogs,
  };

  // Compass rings (jarvis._drawRings) — three concentric rotating rings
  // with tick marks. Speeds and tick counts come from COMPASS_RINGS.
  const compassRings: CompassRingSpec[] = COMPASS_RINGS.map((cfg, i) => {
    const r = maxR * cfg.r;
    const tickLen = 4 + cfg.w * 3;
    const majorEvery = Math.max(1, Math.floor(cfg.ticks / 12));
    const rTicks: TickSpec[] = new Array(cfg.ticks);
    for (let k = 0; k < cfg.ticks; k++) {
      const isMajor = k % majorEvery === 0;
      const len = isMajor ? tickLen * 1.8 : tickLen;
      rTicks[k] = {
        angle: (k / cfg.ticks) * Math.PI * 2,
        innerR: r - len / 2,
        outerR: r + len / 2,
        opacity: isMajor ? 0.35 : 0.12,
        strokeWidth: isMajor ? 1.5 : 0.5,
      };
    }
    return {
      cx, cy,
      rotation: frame.compassRingAngles[i] ?? 0,
      r,
      strokeWidth: cfg.w,
      color,
      opacity: 0.12 * cfg.w,
      ticks: rTicks,
    };
  });

  return {
    size: s, cx, cy, color,
    outerGlow, outerHalo, halo, core, particles, waveformRing, compassRings,
  };
}

function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

export function rgbaString(c: RGB, a: number): string {
  const r = Math.round(c.r);
  const g = Math.round(c.g);
  const b = Math.round(c.b);
  const aa = a < 0 ? 0 : a > 1 ? 1 : a;
  return `rgba(${r},${g},${b},${aa})`;
}
