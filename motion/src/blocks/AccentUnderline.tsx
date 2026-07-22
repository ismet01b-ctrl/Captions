// AccentUnderline — a weighted accent bar that wipes in under a headline. Grows from the
// left on the spring, with a soft glow. Deterministic, no keyframes.

import React from 'react';
import { easeOutQuint } from '../lib/easing';
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
  const e = t - tIn;
  const s = springStep(e, block.spring);
  // Draw with a clean eased-out width (bar) but let a bright node lead the wipe.
  const draw = easeOutQuint(Math.max(0, Math.min(1, s)));
  const h = Math.max(3, Math.round(laneH * 0.06));
  const fullPct = block.widthPct * 100;
  const glow = 1 + 0.15 * Math.sin(Math.max(0, e) * 3); // gentle settle pulse

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
      <div style={{ position: 'relative', width: `${fullPct.toFixed(2)}%`, height: h }}>
        {/* faint track the bar draws along */}
        <div style={{ position: 'absolute', inset: 0, borderRadius: h,
          background: accent, opacity: 0.12 }} />
        {/* the drawing bar */}
        <div
          style={{
            position: 'absolute', left: 0, top: 0, height: h,
            width: `${(100 * draw).toFixed(2)}%`,
            borderRadius: h, background: accent,
            boxShadow: `0 0 ${h * 2.4 * glow}px ${accent}`,
            opacity: Math.min(1, s * 2),
          }}
        />
        {/* bright node riding the leading edge */}
        {draw > 0.02 && draw < 0.999 ? (
          <div style={{ position: 'absolute', top: h / 2 - h,
            left: `calc(${(100 * draw).toFixed(2)}% - ${h}px)`,
            width: h * 2, height: h * 2, borderRadius: '50%',
            background: '#fff', boxShadow: `0 0 ${h * 3}px ${accent}`, opacity: 0.9 }} />
        ) : null}
      </div>
    </div>
  );
};
