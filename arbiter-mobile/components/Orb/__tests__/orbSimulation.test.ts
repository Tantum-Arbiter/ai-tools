import {
  OrbSimulation,
  STATE_LABEL,
  STATE_PALETTE,
} from '../orbSimulation';

const step60 = (sim: OrbSimulation, frames: number) => {
  for (let i = 0; i < frames; i++) sim.step(1 / 60);
};

describe('STATE_PALETTE / STATE_LABEL', () => {
  it('covers every state', () => {
    const keys = ['idle', 'listening', 'thinking', 'speaking'] as const;
    for (const k of keys) {
      expect(STATE_PALETTE[k]).toBeDefined();
      expect(STATE_LABEL[k]).toMatch(/[A-Z]+/);
    }
  });
});

describe('OrbSimulation construction', () => {
  it('uses requested particle count and band count', () => {
    const sim = new OrbSimulation({ particleCount: 250, bands: 32 });
    expect(sim.particleCount).toBe(250);
    expect(sim.bandCount).toBe(32);
  });

  it('defaults to 1500 particles and 64 bands', () => {
    const sim = new OrbSimulation();
    expect(sim.particleCount).toBe(1500);
    expect(sim.bandCount).toBe(64);
  });

  it('is deterministic given the same seed', () => {
    const a = new OrbSimulation({ particleCount: 10, rngSeed: 42 });
    const b = new OrbSimulation({ particleCount: 10, rngSeed: 42 });
    const pa = a.snapshot().particles[0]!;
    const pb = b.snapshot().particles[0]!;
    expect(pa.angle).toBeCloseTo(pb.angle, 10);
    expect(pa.dist).toBeCloseTo(pb.dist, 10);
  });

  it('produces different layouts for different seeds', () => {
    const a = new OrbSimulation({ particleCount: 10, rngSeed: 1 });
    const b = new OrbSimulation({ particleCount: 10, rngSeed: 2 });
    expect(a.snapshot().particles[0]!.angle)
      .not.toBeCloseTo(b.snapshot().particles[0]!.angle, 5);
  });

  it('starts in idle with zero motion', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    expect(sim.state).toBe('idle');
    expect(sim.time).toBe(0);
    expect(sim.audioLevel).toBe(0);
    expect(sim.voiceBlend).toBe(0);
  });
});

describe('OrbSimulation.setState', () => {
  it('switches state and exposes matching colour via snapshot', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.setState('listening');
    expect(sim.state).toBe('listening');
    expect(sim.snapshot().color).toEqual(STATE_PALETTE.listening);
  });
});

describe('OrbSimulation.setAudioLevel', () => {
  it('clamps to [0, 1]', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.setAudioLevel(-0.5); sim.step(1 / 60);
    expect(sim.audioLevel).toBeGreaterThanOrEqual(0);
    sim.setAudioLevel(5); step60(sim, 200);
    expect(sim.audioLevel).toBeLessThanOrEqual(1);
    expect(sim.audioLevel).toBeGreaterThan(0.99);
  });

  it('ignores NaN/Infinity', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.setAudioLevel(0.5); step60(sim, 200);
    const before = sim.audioLevel;
    sim.setAudioLevel(NaN); sim.step(1 / 60);
    sim.setAudioLevel(Infinity); sim.step(1 / 60);
    expect(Math.abs(sim.audioLevel - before)).toBeLessThan(0.05);
  });

  it('smooths toward target monotonically', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.setAudioLevel(1);
    const samples: number[] = [];
    for (let i = 0; i < 10; i++) { sim.step(1 / 60); samples.push(sim.audioLevel); }
    for (let i = 1; i < samples.length; i++) {
      expect(samples[i]!).toBeGreaterThanOrEqual(samples[i - 1]!);
    }
    expect(samples[9]!).toBeLessThan(1); // not yet fully reached
  });
});

describe('OrbSimulation.voiceBlend', () => {
  it('ramps up in listening/speaking and decays in idle/thinking', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.setState('listening'); step60(sim, 60);
    const peak = sim.voiceBlend;
    expect(peak).toBeGreaterThan(0.9);
    sim.setState('idle'); step60(sim, 60);
    expect(sim.voiceBlend).toBeLessThan(peak);
    sim.setState('thinking'); step60(sim, 300);
    expect(sim.voiceBlend).toBeLessThan(0.1);
  });

  it('attacks faster than it decays', () => {
    // One-step delta from blend=0 toward 1 (attack)
    const attack = new OrbSimulation({ particleCount: 4 });
    attack.setState('listening');
    attack.step(1 / 60);
    const attackDelta = attack.voiceBlend; // 0 → attackDelta

    // One-step delta from blend≈1 toward 0 (decay)
    const decay = new OrbSimulation({ particleCount: 4 });
    decay.setState('listening');
    step60(decay, 200); // saturate to near 1
    const before = decay.voiceBlend;
    decay.setState('idle');
    decay.step(1 / 60);
    const decayDelta = before - decay.voiceBlend;

    expect(attackDelta).toBeGreaterThan(decayDelta);
  });
});

describe('OrbSimulation.step', () => {
  it('ignores negative or non-finite dt', () => {
    const sim = new OrbSimulation({ particleCount: 4 });
    sim.step(-1); sim.step(NaN); sim.step(Infinity);
    expect(sim.time).toBe(0);
  });

  it('updates waveform bands when audio is non-zero', () => {
    const sim = new OrbSimulation({ particleCount: 4, bands: 16 });
    sim.setAudioLevel(0.8); step60(sim, 60);
    const w = sim.snapshot().waveData;
    expect(w).toHaveLength(16);
    expect(w.some((v) => v > 0.01)).toBe(true);
  });

  it('snapshot is a fresh copy of waveData each call', () => {
    const sim = new OrbSimulation({ particleCount: 4, bands: 4 });
    sim.setAudioLevel(0.5); step60(sim, 10);
    const a = sim.snapshot().waveData;
    step60(sim, 10);
    const b = sim.snapshot().waveData;
    expect(a).not.toBe(b);
  });
});
