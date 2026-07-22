// transitions.ts — the sequencer's transition library. These are INTERACTIVE, camera-style
// hand-offs: one scene is fully shown, then the next is physically pushed in while a virtual
// camera pans / swings / dollies between them. BOTH scenes stay razor-sharp — there is no
// defocus/blur-out (a scene never dissolves into mush). Everything is a pure function of
// progress `e` and the canvas size, so the whole sequence is frame-exact and seekable.
//
// A matching SFX key rides on each (mounted only when its designed asset exists).

import type { TransId } from '../spec';
import { clamp01, easeInOutQuint, easeInOutCubic, easeOutBack } from './easing';

/** A per-frame transform state for one segment layer. Composable (see composeAffine). */
export interface Affine {
  readonly x: number; // px translate
  readonly y: number; // px translate
  readonly scale: number;
  readonly rotateX: number; // deg (vertical camera swing / flip)
  readonly rotateY: number; // deg (horizontal camera swing)
  readonly alpha: number; // 0..1
  readonly persp: number; // perspective px (0 = none)
}

const A = (p: Partial<Affine>): Affine => ({
  x: 0, y: 0, scale: 1, rotateX: 0, rotateY: 0, alpha: 1, persp: 0, ...p,
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

export const TRANSITIONS: Record<TransId, TransDef> = {
  // Horizontal camera pan — the two scenes sit edge-to-edge and the camera slides right
  // across both. Fully opaque, no fade: a physical push. The clean SaaS default.
  push: {
    id: 'push', label: 'Camera pan', sound: 'whoosh',
    enter(e, w) {
      const o = easeInOutQuint(e);
      return A({ x: w * (1 - o) });
    },
    exit(e, w) {
      const o = easeInOutQuint(e);
      return A({ x: -w * o, scale: 1 - 0.04 * o }); // slight dolly-back = depth parallax
    },
  },
  // Vertical camera pan — the next scene rises up from below and pushes the current one up.
  panv: {
    id: 'panv', label: 'Camera tilt', sound: 'swish',
    enter(e, _w, h) {
      const o = easeInOutQuint(e);
      return A({ y: h * (1 - o) });
    },
    exit(e, _w, h) {
      const o = easeInOutQuint(e);
      return A({ y: -h * o, scale: 1 - 0.04 * o });
    },
  },
  // Cover — the outgoing scene HOLDS in place (sinks a touch for depth) while the incoming
  // slides in over the top with an elastic land. "One is shown, the other is pushed in."
  cover: {
    id: 'cover', label: 'Slide over', sound: 'click',
    enter(e, w) {
      const b = easeOutBack(e);
      return A({ x: w * (1 - clamp01(b)) + w * 0.001 * (1 - b) }); // overshoot settle
    },
    exit(e) {
      const o = easeInOutCubic(e);
      return A({ scale: 1 - 0.08 * o, y: -8 * o }); // recedes slightly under the incoming
    },
  },
  // Dolly — a camera push-through: the outgoing scales up and clears while the incoming
  // rises from a smaller frame into place. Sharp throughout (no blur), reads as depth.
  dolly: {
    id: 'dolly', label: 'Dolly in', sound: 'whoosh2',
    enter(e) {
      const o = easeInOutCubic(e);
      return A({ scale: 0.86 + 0.14 * o, alpha: clamp01(e * 2) });
    },
    exit(e) {
      const o = easeInOutQuint(e);
      return A({ scale: 1 + 0.5 * o, alpha: 1 - clamp01((e - 0.55) / 0.45) });
    },
  },
  // 3D swoosh — a horizontal camera swing (cube-like). The outgoing turns away, the incoming
  // turns in, with real perspective. Both faces stay sharp.
  swoosh: {
    id: 'swoosh', label: '3D swing', sound: 'pop',
    enter(e, w) {
      const o = easeInOutCubic(e);
      return A({ rotateY: -32 * (1 - o), x: w * 0.42 * (1 - o), alpha: clamp01(e * 2.2), persp: 1600 });
    },
    exit(e, w) {
      const o = easeInOutCubic(e);
      return A({ rotateY: 34 * o, x: -w * 0.4 * o, alpha: 1 - clamp01((e - 0.6) / 0.4), persp: 1600 });
    },
  },
  // Tilt — a vertical camera swing (flip up). The outgoing lifts and turns; the incoming
  // swings up from below. Perspective depth, sharp.
  tilt: {
    id: 'tilt', label: '3D flip', sound: 'airy',
    enter(e, _w, h) {
      const o = easeInOutCubic(e);
      return A({ rotateX: 30 * (1 - o), y: h * 0.32 * (1 - o), alpha: clamp01(e * 2.2), persp: 1600 });
    },
    exit(e, _w, h) {
      const o = easeInOutCubic(e);
      return A({ rotateX: -28 * o, y: -h * 0.3 * o, alpha: 1 - clamp01((e - 0.6) / 0.4), persp: 1600 });
    },
  },
};

export const TRANS_IDS: readonly TransId[] = ['push', 'panv', 'cover', 'dolly', 'swoosh', 'tilt'];
export const isTransId = (x: string): x is TransId => (TRANS_IDS as readonly string[]).includes(x);

/** Every distinct SFX key the library can ask for (used to fs-probe the asset folder). */
export const SFX_KEYS: readonly string[] = Array.from(new Set(TRANS_IDS.map((id) => TRANSITIONS[id].sound)));

// Curated variety order. Walking it with a seed-offset + stride coprime to the length
// guarantees a full non-repeating cycle: adjacent boundaries never share a transition.
const ORDER: readonly TransId[] = ['push', 'swoosh', 'panv', 'dolly', 'cover', 'tilt'];

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
    rotateX: a.rotateX + b.rotateX,
    rotateY: a.rotateY + b.rotateY,
    alpha: a.alpha * b.alpha,
    persp: a.persp || b.persp,
  };
}
