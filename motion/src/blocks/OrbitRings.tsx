// OrbitRings — concentric thin rings, each carrying one bright travelling arc and a glow
// node, counter-rotating at staggered rates. Rings scale in on the entrance spring so the
// system "assembles" rather than just fading. SVG for crisp strokes at any resolution.

import React from 'react';
import type { OrbitRings, Palette } from '../spec';
import { springStep } from '../lib/spring';
import { hash01 } from '../lib/rng';

interface Props {
  readonly block: OrbitRings;
  readonly t: number;
  readonly tIn: number;
  readonly w: number;
  readonly h: number;
  readonly palette: Palette;
  readonly seed: number;
}

export const OrbitRingsBlock: React.FC<Props> = ({ block, t, tIn, w, h, palette, seed }) => {
  const e = t - tIn;
  const cx = w / 2;
  const cy = h / 2;
  const base = Math.min(w, h) * 0.14;
  const step = Math.min(w, h) * 0.11;
  const n = Math.max(1, Math.min(5, block.rings | 0));
  const acc = palette.accent;

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      style={{ position: 'absolute', inset: 0, mixBlendMode: 'screen' }}
    >
      <defs>
        <filter id={`orbglow-${seed}`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation={Math.max(2, base * 0.04)} result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {Array.from({ length: n }, (_, i) => {
        const r = base + i * step;
        const s = springStep(e, { ...block.spring, delay: block.spring.delay + i * 0.08 });
        const rr = r * (0.4 + 0.6 * s);
        const dir = i % 2 === 0 ? 1 : -1;
        const rate = block.spin * (0.6 + 0.25 * i);
        const rot = e * rate * dir + hash01(i, seed) * 360;
        const circ = 2 * Math.PI * rr;
        const arc = circ * (0.14 + 0.06 * ((i * 37) % 5) / 5);
        const nodeAngle = (rot * Math.PI) / 180;
        const nx = cx + rr * Math.cos(nodeAngle);
        const ny = cy + rr * Math.sin(nodeAngle);
        return (
          <g key={i} opacity={Math.min(1, s * 1.6)} filter={`url(#orbglow-${seed})`}>
            {/* faint full ring */}
            <circle cx={cx} cy={cy} r={rr} fill="none" stroke={acc} strokeOpacity={0.16}
              strokeWidth={Math.max(1, base * 0.012)} />
            {/* bright travelling arc */}
            <circle
              cx={cx}
              cy={cy}
              r={rr}
              fill="none"
              stroke={acc}
              strokeWidth={Math.max(1.5, base * 0.03)}
              strokeLinecap="round"
              strokeDasharray={`${arc} ${circ}`}
              transform={`rotate(${rot} ${cx} ${cy})`}
            />
            {/* glow node riding the ring */}
            <circle cx={nx} cy={ny} r={Math.max(2, base * 0.05)} fill="#ffffff" />
          </g>
        );
      })}
    </svg>
  );
};
