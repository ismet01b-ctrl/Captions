// autoGuards.ts — the deterministic quality guardrails that sit AFTER the AI director. The
// senior-designer brain proposes beats; these rules enforce the non-negotiables so the output
// is never cheap or broken, whatever the model returns (and they fully shape the offline
// heuristic path too). Pure + unit-tested.
//
// Guarantees: on-screen durations in a sane range; beats sorted; NEVER two overlapping beats
// (a busy screen is amateur); a minimum breath between beats; a density cap tied to video
// length (restraint reads as senior); timings snapped to word onsets (motion lands ON the
// word, not near it); emphasis clamped; nothing spilling past the video.

import type { OverlayBeat, OverlayAnchor, OverlayEnter, OverlayKind } from '../spec';

const KINDS: readonly OverlayKind[] = ['headline', 'lowerthird', 'keyword', 'chips', 'stat', 'brand'];
const ANCHORS: readonly OverlayAnchor[] = ['top', 'upper', 'center', 'lower', 'bottom'];
const ENTERS: readonly OverlayEnter[] = ['rise', 'pop', 'slide', 'wipe'];

const clamp = (x: number, lo: number, hi: number): number => (x < lo ? lo : x > hi ? hi : x);
const isKind = (x: unknown): x is OverlayKind => KINDS.includes(x as OverlayKind);

export interface GuardOpts {
  readonly videoDur: number;       // seconds
  readonly onsets?: readonly number[]; // word start times, for snapping
  readonly minDur?: number;        // default 1.2
  readonly maxDur?: number;        // default 3.4
  readonly minGap?: number;        // default 0.45  (breath between beats)
  readonly snapTol?: number;       // default 0.22  (max shift to a word onset)
  readonly perMinute?: number;     // default 22    (density ceiling)
}

/** Snap a time to the nearest word onset within tolerance (motion lands on the word). */
const snap = (t: number, onsets: readonly number[], tol: number): number => {
  let best = t, bestD = tol;
  for (const o of onsets) { const d = Math.abs(o - t); if (d < bestD) { bestD = d; best = o; } }
  return best;
};

/** Normalise + sanity one raw beat (from the model or the heuristic). Returns null if unusable. */
const sanitizeBeat = (b: any, minDur: number, maxDur: number): OverlayBeat | null => {
  if (!b || !isKind(b.kind)) return null;
  const kind = b.kind as OverlayKind;
  const t = Number(b.t);
  if (!Number.isFinite(t) || t < 0) return null;
  const dur = clamp(Number(b.dur) || 2.2, minDur, maxDur);
  const anchor: OverlayAnchor = ANCHORS.includes(b.anchor) ? b.anchor : (kind === 'lowerthird' ? 'lower' : 'center');
  const enter: OverlayEnter = ENTERS.includes(b.enter) ? b.enter : 'rise';
  const emphasis = clamp(Number(b.emphasis) ?? 0.5, 0, 1);
  const text = typeof b.text === 'string' ? b.text.slice(0, 60).trim() : undefined;
  const text2 = typeof b.text2 === 'string' ? b.text2.slice(0, 80).trim() : undefined;
  const label = typeof b.label === 'string' ? b.label.slice(0, 40).trim() : undefined;
  const items = Array.isArray(b.items)
    ? b.items.map((s: any) => String(s).slice(0, 22).trim()).filter(Boolean).slice(0, 5) : undefined;
  const value = Number.isFinite(Number(b.value)) ? Number(b.value) : undefined;
  const prefix = typeof b.prefix === 'string' ? b.prefix.slice(0, 4) : undefined;
  const suffix = typeof b.suffix === 'string' ? b.suffix.slice(0, 4) : undefined;
  // content sanity: every kind needs its payload, else it is cheap filler → drop.
  if ((kind === 'headline' || kind === 'keyword' || kind === 'lowerthird' || kind === 'brand') && !text) return null;
  if (kind === 'chips' && (!items || items.length < 2)) return null;
  if (kind === 'stat' && value == null) return null;
  const beat: any = { t, dur, kind, anchor, enter, emphasis };
  if (text) beat.text = text; if (text2) beat.text2 = text2; if (label) beat.label = label;
  if (items) beat.items = items; if (value != null) beat.value = value;
  if (prefix) beat.prefix = prefix; if (suffix) beat.suffix = suffix;
  return beat as OverlayBeat;
};

/**
 * The full guardrail pass: sanitize → snap → sort → de-overlap (breath) → density cap → clip
 * to the video. Alternates anchors when the model stacks the same spot, so the eye moves.
 */
export function guardPlan(raw: readonly any[], opts: GuardOpts): OverlayBeat[] {
  const videoDur = Math.max(0.5, opts.videoDur);
  const minDur = opts.minDur ?? 1.2, maxDur = opts.maxDur ?? 3.4;
  const minGap = opts.minGap ?? 0.45, snapTol = opts.snapTol ?? 0.22;
  const perMinute = opts.perMinute ?? 22;
  const onsets = opts.onsets ?? [];

  let beats = (raw || []).map((b) => sanitizeBeat(b, minDur, maxDur)).filter(Boolean) as OverlayBeat[];
  // snap starts to word onsets, keep beats that start before the video ends
  beats = beats
    .map((b) => ({ ...b, t: onsets.length ? snap(b.t, onsets, snapTol) : b.t }))
    .filter((b) => b.t < videoDur - 0.3)
    .sort((a, b) => a.t - b.t);

  // de-overlap: each beat must end at least minGap before the next one starts; shrink/drop.
  const kept: OverlayBeat[] = [];
  for (const b of beats) {
    const prev = kept[kept.length - 1];
    let t = b.t;
    if (prev) {
      const earliest = prev.t + prev.dur + minGap;
      if (t < earliest) t = earliest;            // push later
    }
    let dur = Math.min(b.dur, videoDur - 0.15 - t);
    if (dur < minDur * 0.8) continue;            // no room → drop (never crush a beat)
    // never let the same anchor run back-to-back (keep the eye moving)
    let anchor = b.anchor;
    if (prev && prev.anchor === anchor) {
      const alt: OverlayAnchor[] = anchor === 'lower' ? ['upper', 'center'] : ['lower', 'upper'];
      anchor = alt[(kept.length) % alt.length]!;
    }
    kept.push({ ...b, t, dur, anchor });
  }

  // density cap: at most perMinute beats per 60s, evenly — drop the lowest-emphasis extras.
  const cap = Math.max(1, Math.round((videoDur / 60) * perMinute));
  if (kept.length > cap) {
    const ranked = [...kept].sort((a, b) => b.emphasis - a.emphasis).slice(0, cap);
    const keepSet = new Set(ranked);
    return kept.filter((b) => keepSet.has(b));
  }
  return kept;
}
