// AccentUnderline — a weighted accent bar that wipes in under a headline. Grows from the
// left on the spring, with a soft glow. Deterministic, no keyframes.

import React from 'react';
import type { AccentUnderline } from '../spec';
import { springStep } from '../lib/spring';

interface Props {
  readonly block: AccentUnderline;
  readonly t: number;
  readonly tIn: number;
  readonly accent: string;
  readonly laneH: number;
}

export const AccentUnderlineBlock: React.FC<Props> = ({ block, t, tIn, accent, laneH }) => {
  const s = springStep(t - tIn, block.spring);
  const h = Math.max(3, Math.round(laneH * 0.06));

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
      }}
    >
      <div
        style={{
          width: `${(block.widthPct * 100 * Math.min(1, s)).toFixed(2)}%`,
          height: h,
          borderRadius: h,
          background: accent,
          boxShadow: `0 0 ${h * 2.4}px ${accent}`,
          opacity: Math.min(1, s * 2),
          transformOrigin: 'left center',
        }}
      />
    </div>
  );
};
