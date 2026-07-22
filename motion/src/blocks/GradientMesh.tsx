// GradientMesh — a living mesh gradient: several soft colour blobs orbiting on Lissajous
// paths, screen-blended and heavily blurred into one breathing field. This is the base
// layer that makes a pure-graphics clip feel expensive instead of flat. Pure in t.

import React from 'react';
import { AbsoluteFill } from 'remotion';
import type { GradientMesh, Palette } from '../spec';
import { springStep } from '../lib/spring';

interface Props {
  readonly block: GradientMesh;
  readonly t: number; // absolute seconds
  readonly tIn: number; // scene start
  readonly palette: Palette;
}

/** Append 8-bit alpha to a #rrggbb colour (falls back to the raw string if not hex). */
const withAlpha = (hex: string, a: number): string => {
  const h = hex.trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(h)) return h;
  const v = Math.max(0, Math.min(255, Math.round(a * 255)));
  return h + v.toString(16).padStart(2, '0');
};

export const GradientMeshBlock: React.FC<Props> = ({ block, t, tIn, palette }) => {
  const s = springStep(t - tIn, block.spring); // fade the whole field in
  const cols =
    block.colors.length >= 2 ? block.colors : [palette.accent, palette.fg, palette.muted];
  const sp = block.speed;

  const blobs = cols.map((c, i) => {
    const a = 0.55 - i * 0.05;
    const cx = 50 + 28 * Math.sin(t * sp * (0.17 + i * 0.05) + i * 1.7);
    const cy = 50 + 30 * Math.cos(t * sp * (0.15 + i * 0.04) + i * 2.3);
    const r = 42 + 12 * Math.sin(t * sp * 0.23 + i * 1.1);
    return `radial-gradient(${r.toFixed(1)}% ${r.toFixed(1)}% at ${cx.toFixed(1)}% ${cy.toFixed(
      1,
    )}%, ${withAlpha(c, a)} 0%, transparent 62%)`;
  });

  return (
    <AbsoluteFill
      style={{
        opacity: Math.min(1, s * 1.4) * 0.92,
        backgroundColor: palette.bg,
        backgroundImage: blobs.join(','),
        filter: 'blur(46px) saturate(1.25)',
        transform: `scale(${(1.06 + 0.02 * s).toFixed(4)})`, // avoid blurred edges
        willChange: 'background-image',
      }}
    />
  );
};
