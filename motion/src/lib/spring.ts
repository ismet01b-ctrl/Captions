// spring.ts — closed-form damped-spring step response + Whisper->spring binding.
//
// Why closed form (not Euler stepping): Remotion renders frames out of order (seeking,
// parallel workers). A stateful integrator would desync. springStep(elapsed) is a pure
// function of elapsed time -> identical value at any frame, zero accumulated state,
// zero per-frame heap. This is the component that makes kinetic type snap to the beat.

import type { BeatGrid, KineticHeadline, Spring, WordToken } from '../spec';

/**
 * Unit step response of a damped spring at `elapsed` seconds after its trigger.
 *  - ζ<1 (underdamped): overshoots past 1.0 then settles = the "pop".
 *  - ζ≥1 (critical):    monotonic, no overshoot.
 * Returns 0 before the trigger (+delay).
 */
export function springStep(elapsed: number, s: Spring): number {
  const e = elapsed - s.delay;
  if (e <= 0) return 0;
  const w0 = Math.sqrt(s.stiffness);
  const z = s.damping;
  if (z < 1) {
    const wd = w0 * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w0 * e) * (Math.cos(wd * e) + ((z * w0) / wd) * Math.sin(wd * e));
  }
  return 1 - Math.exp(-w0 * e) * (1 + w0 * e);
}

/**
 * Decaying pulse in [0,1] that spikes to 1 on each downbeat and eases out before the
 * next — drives beat-reactive graphics (orb breathing, wave amplitude). Pure in t.
 */
export function beatPulse(t: number, grid: BeatGrid): number {
  const period = 60 / grid.bpm;
  const phase = (((t - grid.offset) % period) + period) % period; // 0..period
  return Math.exp((-phase / period) * 4.5); // 1 at the beat, ~0.01 just before the next
}

/** Snap an onset to the nearest beat if within tolerance; else keep it verbatim. */
export function snapToBeat(t: number, grid: BeatGrid): number {
  const period = 60 / grid.bpm;
  const k = Math.round((t - grid.offset) / period);
  const beat = grid.offset + k * period;
  return Math.abs(beat - t) <= grid.snapTol ? beat : t;
}

export interface WordTrigger {
  readonly text: string;
  readonly fire: number; // absolute s, beat-snapped
  readonly spring: Spring;
}

/**
 * One trigger per word with a deterministic, scrambled stagger, so a headline never
 * animates in a mechanical left-to-right sweep. Built ONCE per block (memoise upstream).
 */
export function buildTriggers(block: KineticHeadline, grid: BeatGrid): WordTrigger[] {
  const words: readonly WordToken[] = block.words;
  const out: WordTrigger[] = new Array(words.length);
  for (let i = 0; i < words.length; i++) {
    const w = words[i]!;
    const onset = block.beatSync ? snapToBeat(w.start, grid) : w.start;
    const jitter = ((Math.imul(i + 1, 2654435761) >>> 0) & 0x3ff) / 1023; // 0..1
    out[i] = {
      text: w.text,
      fire: onset,
      spring: { ...block.spring, delay: block.spring.delay + jitter * 0.03 },
    };
  }
  return out;
}

export interface WordPose {
  readonly text: string;
  readonly scale: number;
  readonly alpha: number;
  readonly lift: number; // normalised upward settle (0 at rest)
  readonly wght: number; // resolved variable-font weight
}

/**
 * Pose for one word at absolute time t. Pure -> safe to call per frame per word.
 * `weight` is the block's [rest, peak] axis; the pop briefly drives it to peak.
 */
export function wordPose(
  tr: WordTrigger,
  t: number,
  weight: readonly [number, number],
): WordPose | null {
  const e = t - tr.fire;
  if (e < -0.05) return null; // not on screen yet
  const s = springStep(e, tr.spring); // 0 -> ~1.08 (overshoot) -> 1
  const peakPulse = Math.max(0, 1 - Math.abs(1 - s) * 6); // brief spike around settle
  return {
    text: tr.text,
    scale: 0.86 + 0.14 * s,
    alpha: Math.min(1, s * 1.6),
    lift: (1 - s) * 0.06,
    wght: Math.round(weight[0] + (weight[1] - weight[0]) * peakPulse),
  };
}
