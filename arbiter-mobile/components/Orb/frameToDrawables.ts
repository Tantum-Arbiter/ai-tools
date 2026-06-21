// Pure projection from OrbFrame → typed draw specs in pixel space.
// Keeps the Skia view dumb: it just iterates these arrays.

import type { OrbFrame, RGB } from './orbSimulation';

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

export interface OrbDrawSpec {
  size: number;
  cx: number;
  cy: number;
  color: RGB;
  halo: DrawableCircle;
  core: DrawableCircle;
  particles: DrawableCircle[];
  waveformRing: DrawableRing | null;
  orbitalRing: DrawableRing;
}

const CORE_R_FRAC = 0.06;
const HALO_R_FRAC = 1.6;
const NEBULA_MAX_R_FRAC = 0.36; // matches Orb.maxR (size * 0.36)
const ORBITAL_R_FRAC = 0.62;
const WAVE_BASE_FRAC = 0.28; // matches jarvis.js _drawWaveformRing baseR
const WAVE_AMP_FRAC = 0.35;

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

  // One subtle orbital ring outline (matches the first web ring at r=0.62).
  const orbitalRing: DrawableRing = {
    cx, cy,
    r: maxR * (ORBITAL_R_FRAC / NEBULA_MAX_R_FRAC) * 0.62, // ≈ size*0.225
    strokeWidth: 1,
    color,
    opacity: 0.18,
  };

  return { size: s, cx, cy, color, halo, core, particles, waveformRing, orbitalRing };
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
