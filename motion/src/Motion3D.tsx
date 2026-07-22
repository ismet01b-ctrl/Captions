// Motion3D — the 3D face of the brief engine. Same SceneSpec drives it (palette, beat,
// seed, duration, format); a living CSS gradient sits behind a transparent Three canvas
// so the lit solids read against real depth, film grain on top. Renders headless on CPU
// via `remotion render … --gl=angle` (proven in the sandbox).

import React from 'react';
import { AbsoluteFill, useVideoConfig } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
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
      </ThreeCanvas>
      {/* Post grade (DOM): a warm-cool cinematic tint, a soft bloom lift on the highlights,
          and a vignette to focus the eye — a lightweight stand-in for a GPU post stack. */}
      <AbsoluteFill style={{
        background:
          `radial-gradient(120% 90% at 50% 42%, transparent 46%, rgba(4,5,10,0.55) 100%),`
          + `linear-gradient(180deg, ${palette.accent}12 0%, transparent 30%, ${palette.fg}10 100%)`,
        mixBlendMode: 'multiply', pointerEvents: 'none',
      }} />
      <AbsoluteFill style={{
        background: `radial-gradient(90% 70% at 50% 40%, ${palette.accent}14 0%, transparent 60%)`,
        mixBlendMode: 'screen', pointerEvents: 'none',
      }} />
      <Grain amount={Math.max(spec.grain, 2)} seed={spec.seed} />
    </AbsoluteFill>
  );
};
