// Skia view layer for the orb. All visual maths lives in
// orbSimulation.ts (state + audio + particles) and frameToDrawables.ts
// (frame → pixel-space draw specs). This component just iterates the
// spec each frame and renders it. Kept dumb on purpose.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Canvas,
  Circle,
  Group,
  Paint,
  BlurMask,
  vec,
  RadialGradient,
} from '@shopify/react-native-skia';
import { OrbSimulation, type OrbState } from './orbSimulation';
import { frameToDrawables, type OrbDrawSpec } from './frameToDrawables';

export interface OrbProps {
  /** Side length in DIPs. Component renders a square. */
  size: number;
  state?: OrbState;
  /** 0–1; clamped & smoothed inside the simulation. */
  audioLevel?: number;
  /** Number of particles. Default 1500 on phone-class hardware can be heavy; tune per device. */
  particleCount?: number;
  /** Stable seed so layout is identical across remounts and tests. */
  rngSeed?: number;
}

/**
 * <Orb /> — animated nebula/voice ring driven by OrbSimulation.
 * The simulation advances on every requestAnimationFrame; the resulting
 * frame is converted into a flat draw spec and rendered with Skia.
 */
export const Orb: React.FC<OrbProps> = ({
  size,
  state = 'idle',
  audioLevel = 0,
  particleCount = 800,
  rngSeed = 0xa1b2c3d4,
}) => {
  const sim = useMemo(
    () => new OrbSimulation({ particleCount, rngSeed }),
    [particleCount, rngSeed],
  );

  // Push prop changes into the simulation imperatively.
  useEffect(() => { sim.setState(state); }, [sim, state]);
  useEffect(() => { sim.setAudioLevel(audioLevel); }, [sim, audioLevel]);

  const [spec, setSpec] = useState<OrbDrawSpec>(() =>
    frameToDrawables(sim.snapshot(), size),
  );

  // RAF loop — replace with useFrameCallback(reanimated) later if needed.
  const lastRef = useRef<number | null>(null);
  useEffect(() => {
    let raf = 0;
    const tick = (t: number) => {
      const last = lastRef.current ?? t;
      const dt = Math.min(0.05, (t - last) / 1000); // clamp huge gaps
      lastRef.current = t;
      sim.step(dt);
      setSpec(frameToDrawables(sim.snapshot(), size));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [sim, size]);

  const colorStr = (a: number) =>
    `rgba(${spec.color.r | 0},${spec.color.g | 0},${spec.color.b | 0},${a})`;

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <Canvas style={{ width: size, height: size }}>
        {/* Halo: soft radial glow */}
        <Group>
          <Circle cx={spec.halo.cx} cy={spec.halo.cy} r={spec.halo.r}>
            <RadialGradient
              c={vec(spec.halo.cx, spec.halo.cy)}
              r={spec.halo.r}
              colors={[colorStr(spec.halo.opacity), colorStr(0)]}
            />
          </Circle>
        </Group>

        {/* Orbital ring outline */}
        <Circle
          cx={spec.orbitalRing.cx}
          cy={spec.orbitalRing.cy}
          r={spec.orbitalRing.r}
          style="stroke"
          strokeWidth={spec.orbitalRing.strokeWidth}
          color={colorStr(spec.orbitalRing.opacity)}
        />

        {/* Particles */}
        <Group>
          {spec.particles.map((p, i) => (
            <Circle
              key={i}
              cx={p.cx}
              cy={p.cy}
              r={p.r}
              color={colorStr(p.opacity)}
            />
          ))}
        </Group>

        {/* Waveform ring (only when voice engaged) */}
        {spec.waveformRing && (
          <Circle
            cx={spec.waveformRing.cx}
            cy={spec.waveformRing.cy}
            r={spec.waveformRing.r}
            style="stroke"
            strokeWidth={spec.waveformRing.strokeWidth}
            color={colorStr(spec.waveformRing.opacity)}
          />
        )}

        {/* Bright core */}
        <Circle
          cx={spec.core.cx}
          cy={spec.core.cy}
          r={spec.core.r}
          color={colorStr(spec.core.opacity)}
        >
          <Paint>
            <BlurMask blur={4} style="solid" />
          </Paint>
        </Circle>
      </Canvas>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default Orb;
