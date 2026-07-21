// layout.ts — the collision-free lane solver. Blocks are placed into vertical bands
// inside a platform safe zone (same idea as the Python engine's Safe-Zone-Regie: keep
// the feed's UI chrome clear). Bands never overlap, so two blocks in one scene can't collide.

import type { Format } from '../spec';

export interface LaneRect {
  readonly leftPct: number;
  readonly widthPct: number;
  readonly top: number; // px
  readonly height: number; // px
}

// Fraction of the frame reserved for platform UI (right rail / caption bar / tabs).
const SAFE: Record<Format, { top: number; bottom: number; sideR: number }> = {
  '9:16': { top: 0.12, bottom: 0.2, sideR: 0.14 },
  '1:1': { top: 0.1, bottom: 0.12, sideR: 0.06 },
  '16:9': { top: 0.08, bottom: 0.1, sideR: 0.04 },
};

export function laneRect(slot: number, format: Format, w: number, h: number): LaneRect {
  const s = SAFE[format];
  const safeTop = h * s.top;
  const safeBot = h * (1 - s.bottom);
  const usable = safeBot - safeTop;
  const bandH = usable / 3.2; // up to ~3 stacked lanes
  const top = safeTop + slot * bandH * 1.08;
  const rightInset = s.sideR * 100;
  return {
    leftPct: 6,
    widthPct: 100 - 6 - rightInset,
    top,
    height: bandH,
  };
}
