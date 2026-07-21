// MotionVideo — the composition root. Background depth + scenes + grain. Everything is a
// pure function of the frame and the incoming SceneSpec, so Studio preview and CLI render
// produce identical pixels.

import React from 'react';
import { AbsoluteFill } from 'remotion';
import type { SceneSpec } from './spec';
import { SceneRenderer } from './SceneRenderer';
import { Grain } from './blocks/Grain';
import { ensureFont } from './fonts';

// NB: a `type` alias (not `interface`) so it satisfies Remotion's
// `Record<string, unknown>` props constraint.
export type MotionProps = {
  readonly spec: SceneSpec;
};

export const MotionVideo: React.FC<MotionProps> = ({ spec }) => {
  ensureFont();
  const { palette } = spec;

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg }}>
      {/* Soft vertical depth so flat text never floats on a dead flat field. */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 80% at 50% 32%, ${palette.bg} 40%, #000 130%)`,
        }}
      />
      <SceneRenderer spec={spec} />
      <Grain amount={spec.grain} seed={spec.seed} />
    </AbsoluteFill>
  );
};
