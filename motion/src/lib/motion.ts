// motion.ts — the shared "senior SaaS motion" primitives layered on top of the closed-form
// spring: an entrance that overshoots, slides and resolves out of a soft focus blur, plus a
// tiny idle float so held elements never sit dead-still. All pure in time (Remotion-seekable).

import { springStep } from './spring';
import { clamp01, easeOutQuint } from './easing';
import type { Spring } from '../spec';

export interface Pose {
  readonly alpha: number;
  readonly scale: number;
  readonly ty: number; // px slide, 0 at rest
  readonly blur: number; // px, resolves to 0 as it lands (focus pull)
}

/**
 * Premium entrance for one element: spring overshoot (from the spec's spring), an upward
 * slide of `yPx`, a fade, and a focus-pull blur that clears as the element settles.
 */
export function entrancePose(elapsed: number, spring: Spring, yPx: number): Pose {
  const s = springStep(elapsed, spring); // 0 -> ~1.08 -> 1
  const e = Math.max(0, elapsed - spring.delay);
  const focus = 1 - easeOutQuint(clamp01(e / 0.5)); // 1 -> 0 over ~0.5s
  return {
    alpha: clamp01(s * 1.7),
    scale: 0.9 + 0.1 * s,
    ty: (1 - s) * yPx,
    blur: focus * 7,
  };
}

/** Tiny slow drift so a held element breathes instead of freezing. Deterministic. */
export const idleFloat = (t: number, phase: number, ampPx: number): number =>
  Math.sin(t * 1.05 + phase) * ampPx;

/** CSS filter string for a blur amount, or undefined below a threshold (no wasted filter). */
export const blurCss = (px: number): string | undefined =>
  px > 0.15 ? `blur(${px.toFixed(2)}px)` : undefined;
