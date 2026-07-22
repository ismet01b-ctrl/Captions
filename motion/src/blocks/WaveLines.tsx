// WaveLines — stacked flowing sine lines (equaliser / soundwave). Each line has its own
// phase and frequency; the amplitude swells on every downbeat via beatPulse, so the field
// "pumps" to the track. Colour ramps accent -> fg down the stack.

import React from 'react';
import type { WaveLines, Palette, BeatGrid } from '../spec';
import { springStep, beatPulse } from '../lib/spring';

interface Props {
  readonly block: WaveLines;
  readonly t: number;
  readonly tIn: number;
  readonly w: number;
  readonly h: number;
  readonly palette: Palette;
  readonly beat: BeatGrid;
}

const mixHex = (a: string, b: string, k: number): string => {
  const pa = /^#([0-9a-f]{6})$/i.exec(a);
  const pb = /^#([0-9a-f]{6})$/i.exec(b);
  if (!pa || !pb) return a;
  const ca = parseInt(pa[1]!, 16);
  const cb = parseInt(pb[1]!, 16);
  const ch = (sh: number): number => {
    const x = (ca >> sh) & 255;
    const y = (cb >> sh) & 255;
    return Math.round(x + (y - x) * k) & 255;
  };
  return `#${((1 << 24) | (ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).slice(1)}`;
};

export const WaveLinesBlock: React.FC<Props> = ({ block, t, tIn, w, h, palette, beat }) => {
  const e = t - tIn;
  const s = springStep(e, block.spring);
  const n = Math.max(2, Math.min(12, block.lines | 0));
  const pulse = 0.6 + 0.4 * beatPulse(t, beat);
  const A = h * 0.5 * block.amp * pulse * (0.3 + 0.7 * s);
  const midY = h / 2;
  const steps = 48;

  const lines = Array.from({ length: n }, (_, li) => {
    const spread = (li - (n - 1) / 2) / Math.max(1, n); // -0.5..0.5
    const yBase = midY + spread * h * 0.4;
    const freq = 1.4 + li * 0.35;
    const phase = e * (0.9 + li * 0.12) + li * 0.7;
    const pts: string[] = [];
    for (let k = 0; k <= steps; k++) {
      const x = (k / steps) * w;
      const env = Math.sin((k / steps) * Math.PI); // 0 at edges, 1 centre -> no hard ends
      const y = yBase + Math.sin((k / steps) * Math.PI * 2 * freq + phase) * A * env * (0.5 + 0.5 * (1 - Math.abs(spread) * 1.4));
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    const col = mixHex(palette.accent, palette.fg, Math.abs(spread) * 1.6);
    return (
      <polyline
        key={li}
        points={pts.join(' ')}
        fill="none"
        stroke={col}
        strokeWidth={Math.max(1.5, Math.min(w, h) * 0.004)}
        strokeOpacity={(0.25 + 0.55 * (1 - Math.abs(spread) * 1.2)).toFixed(3)}
        strokeLinecap="round"
      />
    );
  });

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      style={{ position: 'absolute', inset: 0, mixBlendMode: 'screen', opacity: Math.min(1, s * 1.5) }}
    >
      {lines}
    </svg>
  );
};
