// transitions.ts — the sequencer's transition library. Each transition defines how the
// OUTgoing segment leaves and how the INcoming segment arrives across a shared 0..1 window.
// Everything is a pure function of progress `e` and the canvas size, so the whole sequence
// stays frame-exact and seekable. This is the "many different, elaborate transitions" layer:
// clean pushes, whip pans with real directional motion blur, glass card slides with an
// elastic land, iris app-opens, subtle 3D swooshes — chosen so no two adjacent boundaries
// repeat. A matching SFX key rides on each (mounted only when the CC0 asset exists).

import type { TransId } from '../spec';
import {
  clamp01, easeOutQuint, easeInQuint, easeInOutCubic, easeInOutQuint, easeOutBack,
} from './easing';

/** A per-frame transform state for one segment layer. Composable (see composeAffine). */
export interface Affine {
  readonly x: number; // px translate
  readonly y: number; // px translate
  readonly scale: number;
  readonly rotateY: number; // deg (3D swoosh)
  readonly alpha: number; // 0..1
  readonly blur: number; // isotropic px
  readonly blurX: number; // horizontal (directional) motion-blur px
  readonly persp: number; // perspective px (0 = none)
}

const A = (p: Partial<Affine>): Affine => ({
  x: 0, y: 0, scale: 1, rotateY: 0, alpha: 1, blur: 0, blurX: 0, persp: 0, ...p,
});

/** Identity at the settled end of every curve, so mid-hold is a perfectly clean frame. */
export const IDENTITY = A({});

export interface TransDef {
  readonly id: TransId;
  readonly label: string;
  readonly sound: string; // SFX key -> public/sfx/<key>.wav
  // incoming: e=0 fully off / unresolved  ->  e=1 settled (MUST return identity at e=1).
  enter(e: number, w: number, h: number): Affine;
  // outgoing: e=0 settled (MUST return identity at e=0)  ->  e=1 fully gone.
  exit(e: number, w: number, h: number): Affine;
}

// Bell curve (0 at the ends, 1 in the middle) — drives motion blur that peaks mid-swipe.
const bell = (e: number): number => Math.sin(Math.PI * clamp01(e));

export const TRANSITIONS: Record<TransId, TransDef> = {
  // Airy defocus zoom — the calm, premium default (resolve out of a blur / grow away).
  blurzoom: {
    id: 'blurzoom', label: 'Blur zoom', sound: 'airy',
    enter(e) {
      const o = easeOutQuint(e);
      return A({ scale: 1.08 - 0.08 * o, blur: 16 * (1 - o), alpha: clamp01(e * 1.3) });
    },
    exit(e) {
      const i = easeInOutCubic(e);
      return A({ scale: 1 + 0.1 * i, blur: 16 * i, alpha: 1 - i });
    },
  },
  // Clean nav-style push — both cards slide, crisp, no blur. iOS-grade.
  push: {
    id: 'push', label: 'Push', sound: 'click',
    enter(e, w) {
      const o = easeInOutQuint(e);
      return A({ x: w * (1 - o), scale: 0.985 + 0.015 * o });
    },
    exit(e, w) {
      const o = easeInOutQuint(e);
      return A({ x: -w * o, scale: 1 - 0.02 * o });
    },
  },
  // Whip pan — fast horizontal fling with REAL directional blur peaking mid-swipe.
  whip: {
    id: 'whip', label: 'Whip pan', sound: 'whoosh',
    enter(e, w) {
      const o = easeOutQuint(e);
      return A({ x: w * 0.6 * (1 - o), blurX: 52 * bell(e), alpha: clamp01(e * 2.2) });
    },
    exit(e, w) {
      const i = easeInQuint(e);
      return A({ x: -w * 0.6 * i, blurX: 52 * bell(e), alpha: 1 - clamp01(e * 1.6) });
    },
  },
  // Glass card slide — rises from below with an elastic overshoot + soft focus pull.
  glass: {
    id: 'glass', label: 'Glass slide', sound: 'swish',
    enter(e, _w, h) {
      const b = easeOutBack(e); // may exceed 1 -> a little bounce past the resting line
      return A({ y: h * 0.16 * (1 - b), scale: 0.965 + 0.035 * clamp01(b), blur: 9 * (1 - easeOutQuint(e)), alpha: clamp01(e * 1.4) });
    },
    exit(e, _w, h) {
      const i = easeInOutCubic(e);
      return A({ y: -h * 0.14 * i, scale: 1 - 0.06 * i, blur: 6 * i, alpha: 1 - i });
    },
  },
  // Iris / app-open — incoming zooms up from a small centred tile; outgoing punches out.
  iris: {
    id: 'iris', label: 'App open', sound: 'pop',
    enter(e) {
      const o = easeOutQuint(e);
      return A({ scale: 0.62 + 0.38 * o, blur: 14 * (1 - o), alpha: clamp01(e * 1.7) });
    },
    exit(e) {
      const i = easeInQuint(e);
      return A({ scale: 1 + 0.42 * i, blur: 12 * i, alpha: 1 - i });
    },
  },
  // Subtle 3D swoosh — a shallow rotateY hand-off with perspective. Understated, expensive.
  swoosh: {
    id: 'swoosh', label: '3D swoosh', sound: 'whoosh2',
    enter(e, w) {
      const o = easeOutQuint(e);
      return A({ rotateY: -22 * (1 - o), x: w * 0.18 * (1 - o), alpha: clamp01(e * 1.6), persp: 1500 });
    },
    exit(e, w) {
      const i = easeInOutCubic(e);
      return A({ rotateY: 20 * i, x: -w * 0.16 * i, alpha: 1 - i, persp: 1500 });
    },
  },
};

export const TRANS_IDS: readonly TransId[] = ['blurzoom', 'push', 'whip', 'glass', 'iris', 'swoosh'];
export const isTransId = (x: string): x is TransId => (TRANS_IDS as readonly string[]).includes(x);

/** Every distinct SFX key the library can ask for (used to fs-probe the asset folder). */
export const SFX_KEYS: readonly string[] = Array.from(new Set(TRANS_IDS.map((id) => TRANSITIONS[id].sound)));

// Curated variety order. Walking it with a seed-offset + stride coprime to the length
// guarantees a full non-repeating cycle: adjacent boundaries never share a transition.
const ORDER: readonly TransId[] = ['whip', 'glass', 'iris', 'push', 'swoosh', 'blurzoom'];

/**
 * Pick a transition per boundary. `overrides[b]` (a per-scene choice) wins when valid;
 * otherwise the boundary gets the next entry in the varied order. Deterministic in `seed`.
 */
export function pickTransitions(
  nBoundaries: number,
  seed: number,
  overrides: readonly (TransId | undefined)[] = [],
): TransId[] {
  const start = ((seed % ORDER.length) + ORDER.length) % ORDER.length;
  const out: TransId[] = [];
  for (let b = 0; b < nBoundaries; b++) {
    const ov = overrides[b];
    out.push(ov && isTransId(ov) ? ov : ORDER[(start + b * 5) % ORDER.length]!);
  }
  return out;
}

/** Stack two affines (enter over the hold, exit at the tail — they never overlap in time). */
export function composeAffine(a: Affine, b: Affine): Affine {
  return {
    x: a.x + b.x,
    y: a.y + b.y,
    scale: a.scale * b.scale,
    rotateY: a.rotateY + b.rotateY,
    alpha: a.alpha * b.alpha,
    blur: a.blur + b.blur,
    blurX: a.blurX + b.blurX,
    persp: a.persp || b.persp,
  };
}
