import { COMPASS_RINGS, OrbSimulation, STATE_PALETTE } from '../orbSimulation';
import { frameToDrawables, rgbaString } from '../frameToDrawables';

const step = (sim: OrbSimulation, frames: number) => {
  for (let i = 0; i < frames; i++) sim.step(1 / 60);
};

function snapshotAt(opts: { state?: 'idle' | 'listening' | 'thinking' | 'speaking'; audio?: number; frames?: number } = {}) {
  const sim = new OrbSimulation({ particleCount: 20, bands: 16, rngSeed: 7 });
  if (opts.state) sim.setState(opts.state);
  if (typeof opts.audio === 'number') sim.setAudioLevel(opts.audio);
  step(sim, opts.frames ?? 1);
  return sim.snapshot();
}

describe('frameToDrawables — geometry', () => {
  it('centres around size/2', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    expect(spec.size).toBe(400);
    expect(spec.cx).toBe(200);
    expect(spec.cy).toBe(200);
    expect(spec.halo.cx).toBe(200);
    expect(spec.core.cx).toBe(200);
  });

  it('clamps tiny sizes to a minimum', () => {
    const spec = frameToDrawables(snapshotAt(), 3);
    expect(spec.size).toBeGreaterThanOrEqual(10);
  });

  it('produces one drawable circle per simulation particle', () => {
    const f = snapshotAt();
    const spec = frameToDrawables(f, 200);
    expect(spec.particles).toHaveLength(f.particles.length);
  });

  it('keeps particles within the canvas bounds', () => {
    const spec = frameToDrawables(snapshotAt({ state: 'listening', audio: 1, frames: 60 }), 200);
    for (const p of spec.particles) {
      expect(p.cx).toBeGreaterThanOrEqual(-20);
      expect(p.cx).toBeLessThanOrEqual(220);
      expect(p.cy).toBeGreaterThanOrEqual(-20);
      expect(p.cy).toBeLessThanOrEqual(220);
    }
  });
});

describe('frameToDrawables — colour', () => {
  it('uses the state palette for every layer', () => {
    const spec = frameToDrawables(snapshotAt({ state: 'thinking' }), 200);
    expect(spec.color).toEqual(STATE_PALETTE.thinking);
    expect(spec.halo.color).toEqual(STATE_PALETTE.thinking);
    expect(spec.core.color).toEqual(STATE_PALETTE.thinking);
    expect(spec.outerGlow.color).toEqual(STATE_PALETTE.thinking);
    expect(spec.outerHalo.color).toEqual(STATE_PALETTE.thinking);
    for (const ring of spec.compassRings) {
      expect(ring.color).toEqual(STATE_PALETTE.thinking);
    }
  });
});

describe('frameToDrawables — outer glow', () => {
  it('produces a centred radial spec sized just outside the nebula', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    expect(spec.outerGlow.cx).toBe(200);
    expect(spec.outerGlow.cy).toBe(200);
    // pulse is in [0.92, 1.08]; r ≈ size * 0.36 * 1.2 = 172.8
    expect(spec.outerGlow.r).toBeGreaterThan(150);
    expect(spec.outerGlow.r).toBeLessThan(200);
  });

  it('pulses radius over time (sin(time*1.2))', () => {
    const a = frameToDrawables(snapshotAt({ frames: 1 }), 400);
    const b = frameToDrawables(snapshotAt({ frames: 60 }), 400);
    expect(a.outerGlow.r).not.toBeCloseTo(b.outerGlow.r, 3);
  });
});

describe('frameToDrawables — outer halo (cog ring)', () => {
  it('exposes 120 ticks and 12 cog teeth at the configured radius', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    expect(spec.outerHalo.ticks).toHaveLength(120);
    expect(spec.outerHalo.cogs).toHaveLength(12);
    // r = size * 0.36 * 1.28 ≈ 184.32
    expect(spec.outerHalo.r).toBeGreaterThan(180);
    expect(spec.outerHalo.r).toBeLessThan(190);
    expect(spec.outerHalo.innerR).toBeLessThan(spec.outerHalo.r);
  });

  it('marks every 10th tick as bigger / brighter', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    const big = spec.outerHalo.ticks[0]!;
    const small = spec.outerHalo.ticks[1]!;
    expect(big.opacity).toBeGreaterThan(small.opacity);
    expect(big.strokeWidth).toBeGreaterThan(small.strokeWidth);
  });

  it('rotates over time via frame.ringAngle', () => {
    const a = frameToDrawables(snapshotAt({ frames: 1 }), 400);
    const b = frameToDrawables(snapshotAt({ frames: 60 }), 400);
    expect(b.outerHalo.rotation).toBeGreaterThan(a.outerHalo.rotation);
  });
});

describe('frameToDrawables — compass rings', () => {
  it('emits one CompassRingSpec per COMPASS_RINGS entry with matching tick counts', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    expect(spec.compassRings).toHaveLength(COMPASS_RINGS.length);
    spec.compassRings.forEach((ring, i) => {
      expect(ring.ticks).toHaveLength(COMPASS_RINGS[i]!.ticks);
    });
  });

  it('places ring radii at fraction × maxR (maxR = size * 0.36)', () => {
    const spec = frameToDrawables(snapshotAt(), 400);
    const maxR = 400 * 0.36;
    spec.compassRings.forEach((ring, i) => {
      expect(ring.r).toBeCloseTo(COMPASS_RINGS[i]!.r * maxR, 3);
    });
  });

  it('rotates each ring independently at its configured speed', () => {
    const a = frameToDrawables(snapshotAt({ frames: 1 }), 400);
    const b = frameToDrawables(snapshotAt({ frames: 120 }), 400);
    // Ring 0 (+0.08) advances, ring 1 (-0.05) retreats.
    expect(b.compassRings[0]!.rotation).toBeGreaterThan(a.compassRings[0]!.rotation);
    expect(b.compassRings[1]!.rotation).toBeLessThan(a.compassRings[1]!.rotation);
  });
});

describe('frameToDrawables — voice blend / waveform ring', () => {
  it('omits the waveform ring when voiceBlend is near zero (idle)', () => {
    const spec = frameToDrawables(snapshotAt({ state: 'idle' }), 200);
    expect(spec.waveformRing).toBeNull();
  });

  it('includes the waveform ring when voice is active', () => {
    const spec = frameToDrawables(
      snapshotAt({ state: 'listening', audio: 0.7, frames: 60 }),
      200,
    );
    expect(spec.waveformRing).not.toBeNull();
    expect(spec.waveformRing!.opacity).toBeGreaterThan(0);
    expect(spec.waveformRing!.r).toBeGreaterThan(0);
  });
});

describe('frameToDrawables — audio reactivity', () => {
  it('grows core radius with audio level', () => {
    const quiet = frameToDrawables(snapshotAt({ state: 'listening', audio: 0, frames: 60 }), 200);
    const loud  = frameToDrawables(snapshotAt({ state: 'listening', audio: 1, frames: 60 }), 200);
    expect(loud.core.r).toBeGreaterThan(quiet.core.r);
  });

  it('brightens halo opacity with audio level', () => {
    const quiet = frameToDrawables(snapshotAt({ state: 'listening', audio: 0, frames: 60 }), 200);
    const loud  = frameToDrawables(snapshotAt({ state: 'listening', audio: 1, frames: 60 }), 200);
    expect(loud.halo.opacity).toBeGreaterThan(quiet.halo.opacity);
  });
});

describe('frameToDrawables — opacity', () => {
  it('clamps particle opacity to [0, 1]', () => {
    const spec = frameToDrawables(snapshotAt({ state: 'speaking', audio: 1, frames: 30 }), 200);
    for (const p of spec.particles) {
      expect(p.opacity).toBeGreaterThanOrEqual(0);
      expect(p.opacity).toBeLessThanOrEqual(1);
    }
  });
});

describe('rgbaString', () => {
  it('formats integer channels and clamps alpha', () => {
    expect(rgbaString({ r: 1.4, g: 200, b: 255 }, 0.5)).toBe('rgba(1,200,255,0.5)');
    expect(rgbaString({ r: 0, g: 0, b: 0 }, -1)).toBe('rgba(0,0,0,0)');
    expect(rgbaString({ r: 0, g: 0, b: 0 }, 2)).toBe('rgba(0,0,0,1)');
  });
});
