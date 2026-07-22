// ChipRow — a row of pill chips that pop in on a staggered spring. Alternating filled /
// outlined so the accent reads as rhythm, not decoration.

import React from 'react';
import type { ChipRow } from '../spec';
import { entrancePose, idleFloat, blurCss } from '../lib/motion';
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
        // Scrambled-but-deterministic stagger so pills don't pop strictly left-to-right.
        const stagger = ((i * 7) % block.items.length) * 0.075;
        const pose = entrancePose(t - tIn, { ...block.spring, delay: block.spring.delay + stagger }, laneH * 0.16);
        const float = idleFloat(t, i * 1.3, laneH * 0.012) * pose.alpha;
        const filled = i % 2 === 0;
        return (
          <span
            key={i}
            style={{
              opacity: pose.alpha,
              transform: `translate3d(0, ${(pose.ty + float).toFixed(1)}px, 0) scale(${pose.scale.toFixed(3)})`,
              filter: blurCss(pose.blur),
              padding: `${fs * 0.34}px ${fs * 0.7}px`,
              borderRadius: 999,
              background: filled ? accent : 'transparent',
              color: filled ? bg : fg,
              border: `2px solid ${accent}`,
              boxShadow: filled ? `0 6px 22px ${accent}44` : 'none',
              fontSize: fs,
              fontWeight: 700,
              fontVariationSettings: `'wght' 700`,
              whiteSpace: 'nowrap',
              willChange: 'transform, opacity, filter',
            }}
          >
            {it}
          </span>
        );
      })}
    </div>
  );
};
