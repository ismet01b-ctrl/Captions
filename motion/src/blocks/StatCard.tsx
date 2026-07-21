// StatCard — a number that springs in and counts up. The count is driven by the same
// closed-form spring so it lands exactly on the overshoot beat, never linear.

import React from 'react';
import type { StatCard } from '../spec';
import { springStep } from '../lib/spring';
import { FONT_FAMILY } from '../fonts';

interface Props {
  readonly block: StatCard;
  readonly t: number; // absolute seconds
  readonly tIn: number; // scene start (entrance trigger)
  readonly fg: string;
  readonly accent: string;
  readonly muted: string;
  readonly laneH: number;
}

const fmt = (n: number): string => Math.round(n).toLocaleString('en-US');

export const StatCardBlock: React.FC<Props> = ({
  block,
  t,
  tIn,
  fg,
  accent,
  muted,
  laneH,
}) => {
  const s = springStep(t - tIn, block.spring); // 0 -> ~1.08 -> 1
  const shown = block.countUp ? Math.min(block.value, block.value * s) : block.value;
  const valueSize = Math.round(laneH * 0.5);
  const labelSize = Math.round(laneH * 0.12);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        opacity: Math.min(1, s * 1.6),
        transform: `scale(${(0.9 + 0.1 * s).toFixed(4)})`,
        fontFamily: `'${FONT_FAMILY}', system-ui, sans-serif`,
      }}
    >
      <div
        style={{
          color: fg,
          fontSize: valueSize,
          fontWeight: 800,
          fontVariationSettings: `'wght' 800`,
          letterSpacing: '-0.03em',
          lineHeight: 1,
        }}
      >
        <span style={{ color: accent }}>{block.prefix ?? ''}</span>
        {fmt(shown)}
        <span style={{ color: accent }}>{block.suffix ?? ''}</span>
      </div>
      <div
        style={{
          color: muted,
          fontSize: labelSize,
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginTop: labelSize * 0.6,
        }}
      >
        {block.label}
      </div>
    </div>
  );
};
