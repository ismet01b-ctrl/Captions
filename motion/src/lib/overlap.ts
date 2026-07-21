// overlap.ts — the continuous-flow overlap manager (component #2).
//
// Given absolute time t it returns which scenes are live and, per scene, an affine
// transform + alpha. An OUTGOING scene eases out (up + shrink + fade) while the INCOMING
// one flies into the same lane — so successive scenes read as one flow, never as a
// stacked collision. Pure function of t -> Remotion-safe, allocation-light.

import { easeOutQuint } from './easing';
import type { Scene, SceneSpec } from '../spec';

export interface Affine {
  readonly tx: number;
  readonly ty: number;
  readonly scale: number;
  readonly alpha: number;
}

export type Phase = 'in' | 'hold' | 'out';

export interface ActiveScene {
  readonly scene: Scene;
  readonly phase: Phase;
  readonly local: number; // 0..1 progress within the current phase
  readonly xf: Affine;
}

const HOLD: Affine = { tx: 0, ty: 0, scale: 1, alpha: 1 };

function enter(kind: Scene['in']['kind'], p: number, riseH: number): Affine {
  switch (kind) {
    case 'rise':
      return { tx: 0, ty: (1 - p) * riseH, scale: 1, alpha: p };
    case 'whip':
      return { tx: (1 - p) * riseH * 1.6, ty: 0, scale: 1, alpha: p };
    case 'scaleIn':
      return { tx: 0, ty: 0, scale: 0.82 + 0.18 * p, alpha: p };
    case 'fade':
    default:
      return { tx: 0, ty: 0, scale: 1, alpha: p };
  }
}

// Outgoing shares the lane with the incoming scene -> push it OUT of the primary slot.
function exit(kind: Scene['out']['kind'], p: number, riseH: number): Affine {
  switch (kind) {
    case 'whip':
      return { tx: -p * riseH * 1.6, ty: 0, scale: 1, alpha: 1 - p };
    case 'scaleIn':
      return { tx: 0, ty: 0, scale: 1 - 0.06 * p, alpha: 1 - p };
    case 'rise':
    case 'fade':
    default:
      return { tx: 0, ty: -p * riseH * 0.5, scale: 1 - 0.06 * p, alpha: 1 - p };
  }
}

/** Envelope for one scene at absolute time t, or null when the scene is not live. */
export function sceneEnvelope(scene: Scene, t: number, riseH: number): ActiveScene | null {
  const inEnd = scene.tStart + scene.in.dur;
  const holdEnd = inEnd + scene.tLen;
  const outEnd = holdEnd + scene.out.dur;
  if (t < scene.tStart || t >= outEnd) return null;
  if (t < inEnd) {
    const p = easeOutQuint((t - scene.tStart) / scene.in.dur);
    return { scene, phase: 'in', local: p, xf: enter(scene.in.kind, p, riseH) };
  }
  if (t < holdEnd) {
    return { scene, phase: 'hold', local: 1, xf: HOLD };
  }
  const p = easeOutQuint((t - holdEnd) / scene.out.dur);
  return { scene, phase: 'out', local: p, xf: exit(scene.out.kind, p, riseH) };
}

/**
 * All live scenes at t, sorted by tStart. Small arrays (rarely >2), so a fresh array
 * per call is fine and keeps the function pure for Remotion's out-of-order rendering.
 */
export function activeScenes(spec: SceneSpec, t: number): ActiveScene[] {
  const riseH = spec.canvas.h * 0.14;
  const out: ActiveScene[] = [];
  for (const scene of spec.scenes) {
    if (scene.tStart > t) break; // scenes are authored in order
    const e = sceneEnvelope(scene, t, riseH);
    if (e) out.push(e);
  }
  return out;
}

/** CSS transform string for an affine (kept here so blocks stay declarative). */
export function affineToCss(xf: Affine): string {
  return `translate3d(${xf.tx.toFixed(3)}px, ${xf.ty.toFixed(3)}px, 0) scale(${xf.scale.toFixed(4)})`;
}
