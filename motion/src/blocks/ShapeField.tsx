// ShapeField — a scatter of small geometric marks (dots, rings, triangles, plus, squares)
// that spring in on a scrambled per-index stagger, then drift and rotate slowly with a
// parallax depth cue. Deterministic scatter from the spec seed + block id.

import React from 'react';
import type { ShapeField, Palette } from '../spec';
import { springStep } from '../lib/spring';
import { mulberry32, hash01 } from '../lib/rng';

interface Props {
  readonly block: ShapeField;
  readonly t: number;
  readonly tIn: number;
  readonly w: number;
  readonly h: number;
  readonly palette: Palette;
  readonly seed: number;
}

const strHash = (s: string): number => {
  let x = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    x ^= s.charCodeAt(i);
    x = Math.imul(x, 16777619) >>> 0;
  }
  return x >>> 0;
};

type Kind = 'dot' | 'ring' | 'triangle' | 'plus' | 'square';
const KINDS: Kind[] = ['dot', 'ring', 'triangle', 'plus', 'square'];

function shapeNode(kind: Kind, size: number, color: string, key: number): React.ReactNode {
  const sw = Math.max(1.2, size * 0.12);
  switch (kind) {
    case 'dot':
      return <circle key={key} r={size * 0.5} fill={color} />;
    case 'ring':
      return <circle key={key} r={size * 0.5} fill="none" stroke={color} strokeWidth={sw} />;
    case 'square':
      return (
        <rect key={key} x={-size / 2} y={-size / 2} width={size} height={size} fill="none"
          stroke={color} strokeWidth={sw} />
      );
    case 'plus':
      return (
        <g key={key} stroke={color} strokeWidth={sw} strokeLinecap="round">
          <line x1={-size / 2} y1={0} x2={size / 2} y2={0} />
          <line x1={0} y1={-size / 2} x2={0} y2={size / 2} />
        </g>
      );
    case 'triangle': {
      const p = `0,${-size * 0.55} ${size * 0.5},${size * 0.4} ${-size * 0.5},${size * 0.4}`;
      return <polygon key={key} points={p} fill="none" stroke={color} strokeWidth={sw} />;
    }
  }
}

export const ShapeFieldBlock: React.FC<Props> = ({ block, t, tIn, w, h, palette, seed }) => {
  const e = t - tIn;
  const n = Math.max(4, Math.min(40, block.count | 0));
  const rnd = mulberry32(seed ^ strHash(block.id));
  const cols = [palette.accent, palette.fg, palette.muted];

  const items = Array.from({ length: n }, (_, i) => {
    const x0 = rnd() * 100;
    const y0 = rnd() * 100;
    const depth = 0.35 + rnd() * 0.65; // near shapes bigger + more opaque + drift more
    const size = Math.min(w, h) * (0.012 + 0.05 * depth);
    const kind: Kind =
      block.shape === 'mixed' ? KINDS[Math.floor(rnd() * KINDS.length)]! : block.shape;
    const col = cols[Math.floor(rnd() * cols.length)]!;
    const fire = e - hash01(i, seed) * 0.9; // scrambled stagger
    const s = springStep(fire, block.spring);
    const drift = block.drift * depth;
    const dx = 4 * drift * Math.sin(e * 0.4 + i);
    const dy = 4 * drift * Math.cos(e * 0.33 + i * 1.3) - e * drift * 1.2; // gentle upward float
    const rot = (hash01(i, seed + 7) - 0.5) * 90 + e * 12 * drift * (i % 2 ? 1 : -1);
    const px = ((x0 + dx) / 100) * w;
    const py = ((y0 + dy) / 100) * h;
    return (
      <g
        key={i}
        transform={`translate(${px.toFixed(1)} ${py.toFixed(1)}) rotate(${rot.toFixed(1)}) scale(${(
          0.4 +
          0.6 * s
        ).toFixed(3)})`}
        opacity={(Math.min(1, s * 1.6) * (0.35 + 0.5 * depth)).toFixed(3)}
      >
        {shapeNode(kind, size, col, i)}
      </g>
    );
  });

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      style={{ position: 'absolute', inset: 0 }}
    >
      {items}
    </svg>
  );
};
