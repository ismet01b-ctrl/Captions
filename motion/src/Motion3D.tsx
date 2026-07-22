// Motion3D — the 3D face of the brief engine. Same SceneSpec drives it (palette, beat,
// seed, duration, format); a living CSS gradient sits behind a transparent Three canvas
// so the lit solids read against real depth, film grain on top. Renders headless on CPU
// via `remotion render … --gl=angle` (proven in the sandbox).

import React from 'react';
import { AbsoluteFill, useVideoConfig } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
// @ts-ignore — postprocessing effect components are runtime JSX, not strictly typed here.
import { EffectComposer, Bloom, DepthOfField, Vignette } from '@react-three/postprocessing';
import type { SceneSpec } from './spec';
import { Scene3D } from './three/Scene3D';
import { Grain } from './blocks/Grain';

export type Motion3DProps = {
  readonly spec: SceneSpec;
};

export const Motion3D: React.FC<Motion3DProps> = ({ spec }) => {
  const { width, height } = useVideoConfig();
  const { palette } = spec;

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg }}>
      {/* Depth wash behind the 3D so the metal catches an environment, not a flat void. */}
      <AbsoluteFill
        style={{
          background:
            `radial-gradient(120% 90% at 32% 26%, ${palette.accent}33 0%, transparent 55%),`
            + `radial-gradient(120% 90% at 78% 82%, ${palette.fg}1f 0%, transparent 55%),`
            + `radial-gradient(120% 80% at 50% 40%, ${palette.bg} 42%, #000 130%)`,
        }}
      />
      <ThreeCanvas
        width={width}
        height={height}
        gl={{ antialias: true, alpha: true }}
        camera={{ position: [0, 0, 6.2], fov: 48 }}
        style={{ position: 'absolute', inset: 0 }}
      >
        <Scene3D spec={spec} />
        {/* REAL GPU-style post stack (via render-targets): physically-based Bloom on the
            emissive screens/glass, a Depth-of-Field bokeh that holds the hero sharp and
            softens the depth, and a vignette. Heavier on software-GL but it renders. */}
        <EffectComposer multisampling={0}>
          <Bloom intensity={0.9} luminanceThreshold={0.62} luminanceSmoothing={0.25} mipmapBlur radius={0.7} />
          <DepthOfField focusDistance={0.012} focalLength={0.05} bokehScale={2.6} height={480} />
          <Vignette eskil={false} offset={0.28} darkness={0.72} />
        </EffectComposer>
      </ThreeCanvas>
      {/* A subtle DOM colour-grade tint over the top, then film grain. */}
      <AbsoluteFill style={{
        background: `linear-gradient(180deg, ${palette.accent}10 0%, transparent 32%, ${palette.fg}0e 100%)`,
        mixBlendMode: 'soft-light', pointerEvents: 'none',
      }} />
      <Grain amount={Math.max(spec.grain, 2)} seed={spec.seed} />
    </AbsoluteFill>
  );
};
