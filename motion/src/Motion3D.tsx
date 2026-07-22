// Motion3D — the 3D face of the brief engine. Same SceneSpec drives it (palette, beat,
// seed, duration, format); a living CSS gradient sits behind a transparent Three canvas
// so the lit solids read against real depth, film grain on top. Renders headless on CPU
// via `remotion render … --gl=angle` (proven in the sandbox).

import React from 'react';
import { AbsoluteFill, useVideoConfig } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
// @ts-ignore — postprocessing effect components are runtime JSX, not strictly typed here.
import { EffectComposer, Bloom, DepthOfField, Vignette, ChromaticAberration } from '@react-three/postprocessing';
import { Vector2 } from 'three';
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
    <AbsoluteFill style={{ backgroundColor: '#eef0f4' }}>
      {/* Clean neutral studio backdrop (reference style) — soft grey so the glossy widget
          cards read as premium objects, not floating in a colour wash. */}
      <AbsoluteFill
        style={{ background: 'radial-gradient(120% 100% at 50% 34%, #f6f7fa 0%, #e9ecf1 55%, #dde1e8 100%)' }}
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
          {/* bright scene → bloom only the strongest highlights; heavy DoF for the reference's
              creamy bokeh; a whisper of chromatic aberration on the edges. */}
          <Bloom intensity={0.4} luminanceThreshold={0.9} luminanceSmoothing={0.2} mipmapBlur radius={0.6} />
          <DepthOfField focusDistance={0.012} focalLength={0.045} bokehScale={2.4} height={480} />
          <Vignette eskil={false} offset={0.4} darkness={0.4} />
        </EffectComposer>
      </ThreeCanvas>
      {/* A whisper of warm grade + film grain. */}
      <AbsoluteFill style={{
        background: `radial-gradient(120% 90% at 50% 40%, transparent 55%, ${palette.accent}12 100%)`,
        mixBlendMode: 'soft-light', pointerEvents: 'none',
      }} />
      <Grain amount={Math.max(spec.grain, 2)} seed={spec.seed} />
    </AbsoluteFill>
  );
};
