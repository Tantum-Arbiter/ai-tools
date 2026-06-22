// Skia view layer for the orb. All visual maths lives in
// orbSimulation.ts (state + audio + particles) and frameToDrawables.ts
// (frame → pixel-space draw specs). This component just iterates the
// spec each frame and renders it. Kept dumb on purpose.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Canvas,
  Circle,
  Group,
  Line,
  vec,
  RadialGradient,
} from '@shopify/react-native-skia';
import {
  runOnJS,
  useFrameCallback,
  useSharedValue,
} from 'react-native-reanimated';
import { OrbSimulation, type OrbState } from './orbSimulation';
import { frameToDrawables, type OrbDrawSpec } from './frameToDrawables';

// Target ~24fps. Anything higher fries phone GPUs running Skia + 100+
// circles + a radial gradient + a blur mask. Tunable per device class
// later (e.g. promote to 30fps on tablets) but 24fps is plenty for the
// nebula/halo look — the human eye reads it as smooth.
const TARGET_FRAME_MS = 1000 / 24;

export interface OrbProps {
  /** Side length in DIPs. Component renders a square. */
  size: number;
  state?: OrbState;
  /** 0–1; clamped & smoothed inside the simulation. */
  audioLevel?: number;
  /** Number of particles. Defaults tuned for mobile thermals (120). */
  particleCount?: number;
  /** Stable seed so layout is identical across remounts and tests. */
  rngSeed?: number;
  /**
   * When true, the simulation loop and Skia re-renders stop entirely.
   * Used to drop GPU/CPU load when the orb is faded out behind the chat
   * drawer or when the screen is off-route.
   */
  paused?: boolean;
}

/**
 * <Orb /> — animated nebula/voice ring driven by OrbSimulation.
 * Throttled to ~24fps via Reanimated's useFrameCallback (UI-thread
 * scheduled, not RAF) to keep mobile thermals under control.
 */
export const Orb: React.FC<OrbProps> = ({
  size,
  state = 'idle',
  audioLevel = 0,
  particleCount = 120,
  rngSeed = 0xa1b2c3d4,
  paused = false,
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

  // Frame scheduling via Reanimated's UI-thread frame callback. Steps
  // the sim on JS (the sim holds class state — not worklet-portable).
  // Throttled to TARGET_FRAME_MS by accumulating dt on a sharedValue
  // and only crossing the bridge once per ~42ms window.
  const accumulator = useSharedValue(0);
  const stepAndRender = useCallback(
    (dt: number) => {
      sim.step(dt);
      setSpec(frameToDrawables(sim.snapshot(), size));
    },
    [sim, size],
  );
  const frameCallback = useFrameCallback((info) => {
    'worklet';
    const dtMs = info.timeSincePreviousFrame ?? 16;
    if (dtMs <= 0) return;
    accumulator.value += dtMs;
    if (accumulator.value < TARGET_FRAME_MS) return;
    const stepMs = accumulator.value;
    accumulator.value = 0;
    runOnJS(stepAndRender)(Math.min(0.1, stepMs / 1000));
  }, false);

  // Drive activation off the `paused` prop. autostart=false on the hook
  // call avoids a double-toggle race on mount.
  useEffect(() => {
    frameCallback.setActive(!paused);
  }, [paused, frameCallback]);

  const colorStr = (a: number) =>
    `rgba(${spec.color.r | 0},${spec.color.g | 0},${spec.color.b | 0},${a})`;

  // The halo extends to ~size*0.576 from centre but the Canvas would clip
  // it at size/2 — i.e. the soft glow ends in a hard square at the corners.
  // Expand the Canvas by HALO_PAD on each side and translate the drawing
  // back into the middle. The outer wrap stays at the visual orb size so
  // the parent's tap target / layout maths don't shift.
  const HALO_PAD = Math.ceil(size * 0.18);
  const canvasSize = size + HALO_PAD * 2;

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <Canvas
        pointerEvents="none"
        style={{
          position: 'absolute',
          top: -HALO_PAD,
          left: -HALO_PAD,
          width: canvasSize,
          height: canvasSize,
        }}
      >
       <Group transform={[{ translateX: HALO_PAD }, { translateY: HALO_PAD }]}>
        {/* Outer cog halo — rotating ring with 120 ticks + 12 cog teeth.
            Drawn first so everything else sits on top of it. */}
        <Group
          origin={vec(spec.outerHalo.cx, spec.outerHalo.cy)}
          transform={[{ rotate: spec.outerHalo.rotation }]}
        >
          <Circle
            cx={spec.outerHalo.cx}
            cy={spec.outerHalo.cy}
            r={spec.outerHalo.r}
            style="stroke"
            strokeWidth={1.2}
            color={colorStr(spec.outerHalo.ringOpacity)}
          />
          <Circle
            cx={spec.outerHalo.cx}
            cy={spec.outerHalo.cy}
            r={spec.outerHalo.innerR}
            style="stroke"
            strokeWidth={0.6}
            color={colorStr(spec.outerHalo.innerRingOpacity)}
          />
          {spec.outerHalo.ticks.map((t, i) => (
            <Line
              key={`ht-${i}`}
              p1={vec(spec.outerHalo.cx + Math.cos(t.angle) * t.innerR, spec.outerHalo.cy + Math.sin(t.angle) * t.innerR)}
              p2={vec(spec.outerHalo.cx + Math.cos(t.angle) * t.outerR, spec.outerHalo.cy + Math.sin(t.angle) * t.outerR)}
              strokeWidth={t.strokeWidth}
              color={colorStr(t.opacity)}
            />
          ))}
          {spec.outerHalo.cogs.map((t, i) => (
            <Line
              key={`hc-${i}`}
              p1={vec(spec.outerHalo.cx + Math.cos(t.angle) * t.innerR, spec.outerHalo.cy + Math.sin(t.angle) * t.innerR)}
              p2={vec(spec.outerHalo.cx + Math.cos(t.angle) * t.outerR, spec.outerHalo.cy + Math.sin(t.angle) * t.outerR)}
              strokeWidth={t.strokeWidth}
              color={colorStr(t.opacity)}
            />
          ))}
        </Group>

        {/* Ambient outer glow — pulsing radial wash behind the orb. */}
        <Circle cx={spec.outerGlow.cx} cy={spec.outerGlow.cy} r={spec.outerGlow.r}>
          <RadialGradient
            c={vec(spec.outerGlow.cx, spec.outerGlow.cy)}
            r={spec.outerGlow.r}
            colors={[
              colorStr(spec.outerGlow.opacity),
              colorStr(spec.outerGlow.opacity * 0.44),
              colorStr(spec.outerGlow.opacity * 0.17),
              colorStr(0),
            ]}
            positions={[0, 0.3, 0.6, 1]}
          />
        </Circle>

        {/* Halo: soft glow whose brightness peaks at the particle
            perimeter. Sits between the outer glow and the particle cloud. */}
        <Circle cx={spec.halo.cx} cy={spec.halo.cy} r={spec.halo.r}>
          <RadialGradient
            c={vec(spec.halo.cx, spec.halo.cy)}
            r={spec.halo.r}
            colors={[
              colorStr(spec.halo.opacity * 0.3),
              colorStr(spec.halo.opacity * 0.8),
              colorStr(spec.halo.opacity * 3.0),
              colorStr(spec.halo.opacity * 1.2),
              colorStr(0),
            ]}
            positions={[0, 0.4, 0.62, 0.8, 1]}
          />
        </Circle>

        {/* Perimeter rim — bright stroked circle at the particle edge,
            doubled with a wider, softer stroke for a glow effect. */}
        <Circle
          cx={spec.halo.cx}
          cy={spec.halo.cy}
          r={spec.halo.r * 0.62}
          style="stroke"
          strokeWidth={3}
          color={colorStr(0.18 + spec.halo.opacity * 1.5)}
        />
        <Circle
          cx={spec.halo.cx}
          cy={spec.halo.cy}
          r={spec.halo.r * 0.62}
          style="stroke"
          strokeWidth={1}
          color={colorStr(0.55)}
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

        {/* Bright core + close-in glow. BlurMask was a noticeable GPU
            hog every frame; a wider gradient approximates the diffuse
            edge without the blur shader. */}
        <Circle cx={spec.core.cx} cy={spec.core.cy} r={spec.core.r * 3.2}>
          <RadialGradient
            c={vec(spec.core.cx, spec.core.cy)}
            r={spec.core.r * 3.2}
            colors={[colorStr(spec.core.opacity * 0.55), colorStr(0)]}
          />
        </Circle>
        <Circle
          cx={spec.core.cx}
          cy={spec.core.cy}
          r={spec.core.r}
          color={colorStr(spec.core.opacity)}
        />

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

        {/* Compass rings — three rotating concentric rings with tick
            marks, drawn last so they sit crisply over the nebula. */}
        {spec.compassRings.map((ring, ri) => (
          <Group
            key={`cr-${ri}`}
            origin={vec(ring.cx, ring.cy)}
            transform={[{ rotate: ring.rotation }]}
          >
            <Circle
              cx={ring.cx}
              cy={ring.cy}
              r={ring.r}
              style="stroke"
              strokeWidth={ring.strokeWidth}
              color={colorStr(ring.opacity)}
            />
            {ring.ticks.map((t, ti) => (
              <Line
                key={`cr-${ri}-${ti}`}
                p1={vec(ring.cx + Math.cos(t.angle) * t.innerR, ring.cy + Math.sin(t.angle) * t.innerR)}
                p2={vec(ring.cx + Math.cos(t.angle) * t.outerR, ring.cy + Math.sin(t.angle) * t.outerR)}
                strokeWidth={t.strokeWidth}
                color={colorStr(t.opacity)}
              />
            ))}
          </Group>
        ))}
       </Group>
      </Canvas>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
    // Halo overflows by HALO_PAD on each side; allow it to draw outside
    // this View's bounds without being clipped.
    overflow: 'visible',
  },
});

export default Orb;
