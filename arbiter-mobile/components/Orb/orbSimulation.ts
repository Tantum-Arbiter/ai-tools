// Renderer-agnostic orb simulation, ported from arbiter-mission-control/
// static/jarvis.js (class Orb). Holds state, particles, audio reactivity, and
// per-frame transitions. The Skia view consumes snapshots; tests consume the
// raw module without any RN/Skia runtime.

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface RGB { r: number; g: number; b: number }

export const STATE_PALETTE: Readonly<Record<OrbState, RGB>> = {
  idle:      { r: 0,   g: 200, b: 255 },
  listening: { r: 0,   g: 255, b: 136 },
  thinking:  { r: 255, g: 170, b: 0   },
  speaking:  { r: 100, g: 210, b: 255 },
};

export const STATE_LABEL: Readonly<Record<OrbState, string>> = {
  idle:      'STANDBY',
  listening: 'LISTENING',
  thinking:  'ANALYSING',
  speaking:  'SPEAKING',
};

const SPEED_MULTIPLIER: Readonly<Record<OrbState, number>> = {
  idle: 2.5, listening: 4.5, thinking: 6, speaking: 5.5,
};

// Smoothing constants (per-frame at ~60 fps; matches jarvis.js):
const AUDIO_SMOOTH = 0.15;
const BLEND_ATTACK = 0.06;
const BLEND_DECAY  = 0.025;
const WAVE_SMOOTH  = 0.2;

export interface OrbParticle {
  angle: number;
  baseDist: number;
  dist: number;
  speed: number;
  size: number;
  phase: number;
  twinkleSpeed: number;
  brightness: number;
  ringAngle: number;
  ringBaseDist: number;
}

export interface OrbFrame {
  readonly state: OrbState;
  readonly color: RGB;
  readonly time: number;
  readonly audioLevel: number;
  readonly voiceBlend: number; // 0 = nebula, 1 = ring
  readonly particles: ReadonlyArray<OrbParticle>;
  readonly waveData: ReadonlyArray<number>;
  /** Continuous rotation (rad) of the outer cog halo. */
  readonly ringAngle: number;
  /** Continuous rotation (rad) per compass ring; same length & order as COMPASS_RINGS. */
  readonly compassRingAngles: ReadonlyArray<number>;
}

// Compass rings — matches jarvis.js `this.rings`. Radii are fractions of maxR.
export interface CompassRingConfig {
  readonly r: number;
  readonly ticks: number;
  readonly w: number;
  readonly speed: number;
}
export const COMPASS_RINGS: ReadonlyArray<CompassRingConfig> = [
  { r: 0.62, ticks: 72,  w: 1.0, speed:  0.08 },
  { r: 0.78, ticks: 90,  w: 0.7, speed: -0.05 },
  { r: 0.92, ticks: 120, w: 0.5, speed:  0.03 },
];

// Outer halo rotation speed (rad/s) — matches jarvis._drawHalo: ringAngle += dt * 0.15.
const HALO_ROTATION_SPEED = 0.15;

export interface OrbSimulationOptions {
  particleCount?: number;
  bands?: number;
  rngSeed?: number;
}

// Deterministic RNG so particle layout is reproducible in tests.
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = t;
    r = Math.imul(r ^ (r >>> 15), r | 1);
    r ^= r + Math.imul(r ^ (r >>> 7), r | 61);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussFrom(rng: () => number): number {
  let u = 0, v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export class OrbSimulation {
  private _state: OrbState = 'idle';
  private _time = 0;
  private _audio = 0;
  private _audioTarget = 0;
  private _blend = 0;
  private _ringAngle = 0;
  private readonly _compassRingAngles: number[];
  private readonly _particles: OrbParticle[];
  private readonly _wave: Float64Array;

  constructor(opts: OrbSimulationOptions = {}) {
    const n = opts.particleCount ?? 1500;
    const bands = opts.bands ?? 64;
    const rng = mulberry32(opts.rngSeed ?? 0xa1b2c3d4);
    this._particles = buildParticles(n, rng);
    this._wave = new Float64Array(bands);
    this._compassRingAngles = COMPASS_RINGS.map(() => 0);
  }

  get state(): OrbState { return this._state; }
  get time(): number { return this._time; }
  get audioLevel(): number { return this._audio; }
  get voiceBlend(): number { return this._blend; }
  get bandCount(): number { return this._wave.length; }
  get particleCount(): number { return this._particles.length; }
  get ringAngle(): number { return this._ringAngle; }
  get compassRingAngles(): ReadonlyArray<number> { return this._compassRingAngles; }

  setState(s: OrbState): void { this._state = s; }

  setAudioLevel(v: number): void {
    if (!Number.isFinite(v)) return;
    this._audioTarget = v < 0 ? 0 : v > 1 ? 1 : v;
  }

  /** Advance the simulation by `dt` seconds. */
  step(dt: number): void {
    if (!Number.isFinite(dt) || dt < 0) return;
    this._time += dt;
    this._audio += (this._audioTarget - this._audio) * AUDIO_SMOOTH;
    const voiceActive = this._state === 'listening' || this._state === 'speaking';
    const target = voiceActive ? 1 : 0;
    const k = target > this._blend ? BLEND_ATTACK : BLEND_DECAY;
    this._blend += (target - this._blend) * k;
    this._ringAngle += dt * HALO_ROTATION_SPEED;
    for (let i = 0; i < this._compassRingAngles.length; i++) {
      this._compassRingAngles[i]! += dt * COMPASS_RINGS[i]!.speed;
    }
    this._updateWaveData();
    this._stepParticles(dt);
  }

  private _stepParticles(dt: number): void {
    // Match web behaviour: angle drift scales with state speed multiplier.
    // Original was 60-fps frame-stepped; we normalise to dt * 60.
    const mult = SPEED_MULTIPLIER[this._state] * dt * 60;
    const TAU = Math.PI * 2;
    for (const p of this._particles) {
      p.angle = (p.angle + p.speed * mult) % TAU;
      if (p.angle < 0) p.angle += TAU;
    }
  }

  /** Immutable frame data for the renderer. */
  snapshot(): OrbFrame {
    return {
      state: this._state,
      color: STATE_PALETTE[this._state],
      time: this._time,
      audioLevel: this._audio,
      voiceBlend: this._blend,
      particles: this._particles,
      waveData: Array.from(this._wave),
      ringAngle: this._ringAngle,
      compassRingAngles: this._compassRingAngles.slice(),
    };
  }

  speedMultiplier(): number { return SPEED_MULTIPLIER[this._state]; }

  private _updateWaveData(): void {
    const level = this._audio;
    for (let i = 0; i < this._wave.length; i++) {
      const freq = 1.5 + i * 0.3;
      const phase = i * 0.7 + this._time * freq;
      const wave = Math.sin(phase) * 0.3 + Math.sin(phase * 1.7) * 0.2 + Math.sin(phase * 0.5) * 0.15;
      const target = Math.abs(wave) * (0.1 + level * 0.9);
      this._wave[i]! += (target - this._wave[i]!) * WAVE_SMOOTH;
    }
  }
}

function buildParticles(n: number, rng: () => number): OrbParticle[] {
  const out: OrbParticle[] = new Array(n);
  for (let i = 0; i < n; i++) {
    const rawDist = Math.abs(gaussFrom(rng)) * 0.35;
    const dist = Math.min(rawDist, 1.0);
    out[i] = {
      angle: rng() * Math.PI * 2,
      baseDist: dist,
      dist,
      speed: (0.0005 + rng() * 0.002) * (rng() < 0.5 ? 1 : -1),
      size: 0.4 + rng() * 1.6,
      phase: rng() * Math.PI * 2,
      twinkleSpeed: 1.5 + rng() * 3,
      brightness: 0.3 + rng() * 0.7,
      ringAngle: (i / n) * Math.PI * 2,
      ringBaseDist: 0.28 + (i % 3) * 0.02,
    };
  }
  return out;
}
