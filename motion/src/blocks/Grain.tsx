// Grain — deterministic film grain via SVG turbulence. The seed advances by frame so the
// grain shimmers (static grain reads as dirt on the lens); intensity comes from the spec.

import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';

interface Props {
  readonly amount: number; // spec.grain, 0..10
  readonly seed: number;
}

export const Grain: React.FC<Props> = ({ amount, seed }) => {
  const frame = useCurrentFrame();
  if (amount <= 0.05) return null;
  const turbSeed = (seed + frame) % 997;
  const opacity = Math.min(0.16, amount / 60);

  return (
    <AbsoluteFill style={{ mixBlendMode: 'overlay', opacity, pointerEvents: 'none' }}>
      <svg width="100%" height="100%">
        <filter id={`grain-${turbSeed}`}>
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves={2}
            seed={turbSeed}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter={`url(#grain-${turbSeed})`} />
      </svg>
    </AbsoluteFill>
  );
};
