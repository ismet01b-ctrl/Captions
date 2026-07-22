// ChipRow — a row of pill chips that pop in on a staggered spring. Alternating filled /
// outlined so the accent reads as rhythm, not decoration.

import React from 'react';
import type { ChipRow } from '../spec';
import { springStep } from '../lib/spring';
import { FONT_FAMILY } from '../fonts';

interface Props {
  readonly block: ChipRow;
  readonly t: number;
  readonly tIn: number;
  readonly fg: string;
  readonly accent: string;
  readonly bg: string;
  readonly laneH: number;
}

export const ChipRowBlock: React.FC<Props> = ({ block, t, tIn, fg, accent, bg, laneH }) => {
  const fs = Math.round(laneH * 0.16);

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: fs * 0.5,
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        fontFamily: `'${FONT_FAMILY}', system-ui, sans-serif`,
      }}
    >
      {block.items.map((it, i) => {
        const s = springStep(t - tIn, { ...block.spring, delay: block.spring.delay + i * 0.08 });
        const filled = i % 2 === 0;
        return (
          <span
            key={i}
            style={{
              opacity: Math.min(1, s * 1.6),
              transform: `translate3d(0, ${((1 - s) * laneH * 0.12).toFixed(1)}px, 0) scale(${(0.8 + 0.2 * s).toFixed(3)})`,
              padding: `${fs * 0.34}px ${fs * 0.7}px`,
              borderRadius: 999,
              background: filled ? accent : 'transparent',
              color: filled ? bg : fg,
              border: `2px solid ${accent}`,
              fontSize: fs,
              fontWeight: 700,
              fontVariationSettings: `'wght' 700`,
              whiteSpace: 'nowrap',
              willChange: 'transform, opacity',
            }}
          >
            {it}
          </span>
        );
      })}
    </div>
  );
};
