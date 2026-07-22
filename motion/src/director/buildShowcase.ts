// buildShowcase.ts — turns a spoken transcript into a per-user MotionShowcase storyboard. This is
// what makes the piece INDIVIDUAL: two different voiceovers → two different videos, both in the
// same senior style. The hard rules Ismet set are met BY CONSTRUCTION:
//   • No hallucination — every on-screen word is copied VERBATIM from the transcript (we only ever
//     slice phrase text; the generator never authors words). The sign-off uses the brand name.
//   • Runs to the transcript — one shot per spoken phrase, in spoken order, so it tracks a voiceover.
//   • Reality-only — it picks exclusively from the real-UI archetypes (no abstract shapes).
//   • No broken layout — copy is length-capped and the renderer auto-fits, so text never clips.
// The archetype CHOICE is heuristic (a strong deterministic floor, no API key needed); a GPT pass
// can refine the picks later, but it can never introduce new words — provenance stays enforced.

import type { Shot, ShotKind, TransKind } from '../MotionShowcase';

export interface SWord { readonly word: string; readonly start: number; readonly end: number; }
export interface BuildOpts { readonly brandName?: string; readonly maxShots?: number; }

const STOP = new Set([
  'the', 'and', 'for', 'you', 'your', 'that', 'this', 'with', 'from', 'have', 'was', 'are', 'but',
  'not', 'all', 'can', 'will', 'just', 'its', 'our', 'they', 'them', 'then', 'than', 'what', 'when',
  'ich', 'und', 'die', 'der', 'das', 'ein', 'eine', 'wie', 'wir', 'ist', 'auf', 'für', 'mit', 'von',
  'den', 'dem', 'des', 'sind', 'wird', 'werden', 'nicht', 'auch', 'sich', 'nur', 'aber',
]);

const clean = (w: string): string => w.replace(/[^\p{L}\p{N}]/gu, '');
const cap = (s: string, n: number): string => (s.length <= n ? s : s.slice(0, n).replace(/\s+\S*$/, '').trim());

interface Phrase { text: string; words: SWord[]; start: number; end: number; }

/** Split the word stream into phrases at pauses (>0.4s), sentence punctuation, or length. */
function phrases(words: readonly SWord[]): Phrase[] {
  const out: Phrase[] = [];
  let cur: SWord[] = [];
  const flush = (): void => {
    if (!cur.length) return;
    out.push({
      text: cur.map((w) => w.word.trim()).join(' ').replace(/\s+/g, ' ').trim(),
      words: cur, start: cur[0]!.start, end: cur[cur.length - 1]!.end,
    });
    cur = [];
  };
  for (let i = 0; i < words.length; i++) {
    const w = words[i]!; cur.push(w);
    const next = words[i + 1];
    const gap = next ? next.start - w.end : 99;
    if (/[.!?]$/.test(w.word.trim()) || gap > 0.4 || cur.length >= 8) flush();
  }
  flush();
  return out;
}

const keywords = (ws: SWord[]): string[] =>
  ws.map((w) => clean(w.word)).filter((c) => c.length >= 4 && !STOP.has(c.toLowerCase()));

/** Split a phrase into two clauses (for two-part archetypes) at a comma / conjunction / midpoint. */
function twoClauses(p: Phrase): [string, string] | null {
  const t = p.text.replace(/[.!?]+$/, '');
  const m = t.match(/^(.{4,}?)[,;]\s+(.{2,})$/) || t.match(/^(.{4,}?)\s+(?:and|or|but|und|oder|aber)\s+(.{2,})$/i);
  if (m) return [cap(m[1]!.trim(), 26), cap(m[2]!.trim(), 26)];
  if (p.words.length >= 4) {
    const mid = Math.ceil(p.words.length / 2);
    const a = p.words.slice(0, mid).map((w) => w.word.trim()).join(' ');
    const b = p.words.slice(mid).map((w) => w.word.trim()).join(' ');
    return [cap(a, 26), cap(b, 26)];
  }
  return null;
}

/** Pick the archetype that best fits a phrase's content (deterministic). Returns null to skip. */
function pickKind(p: Phrase, i: number, n: number): ShotKind {
  const low = ` ${p.text.toLowerCase()} `;
  const wc = p.words.length;
  if (i === 0) return 'ktypo';                                            // the hook
  if (/\b(search|find|look up|google|type|discover|suchen|finden)\b/.test(low)) return 'searchbar';
  if (/\b(time|timing|second|seconds|frame|frames|fps|sync|voice|timed|zeit|sekunde)\b/.test(low)) return 'timeline';
  if (/\b(render|progress|build|process|frame by frame|rendern)\b/.test(low)) return 'timer';
  if (/[,;]| and | or | und | oder /.test(` ${p.text} `)) return 'imessage';   // a list / two-part line
  if (wc <= 3) return 'pill';                                             // a short punchy claim
  if (wc >= 6) return 'notes';                                            // a longer statement reads as a note
  return 'widgets';                                                       // otherwise a real-UI beat
}

const clampDur = (wc: number): number => Math.min(3.4, Math.max(2.4, 1.9 + wc * 0.22));

/**
 * Build the storyboard. Returns null if there's not enough transcript to work with (the caller
 * then falls back to the built-in demo). Never throws.
 */
export function buildShowcase(words: readonly SWord[], opts: BuildOpts = {}): Shot[] | null {
  const ph = phrases(words);
  if (ph.length < 2) return null;
  const brand = (opts.brandName || 'DouchkoVE').slice(0, 24);
  const maxContent = Math.max(3, (opts.maxShots ?? 10) - 1); // leave room for the sign-off
  const use = ph.slice(0, maxContent);

  const shots: Shot[] = [];
  const TRANS_CYCLE: TransKind[] = ['slideL', 'push', 'slideUp', 'morph'];
  let ti = 0;
  const nextTrans = (): TransKind => TRANS_CYCLE[(ti++) % TRANS_CYCLE.length]!;

  use.forEach((p, i) => {
    let kind = pickKind(p, i, use.length);
    const dur = clampDur(p.words.length);
    const into = i === 0 ? 'slideL' : nextTrans();
    const kw = keywords(p.words);

    // Build the shot, always with verbatim copy. If a two-part archetype can't be split, fall back.
    if (kind === 'imessage') {
      const cl = twoClauses(p);
      if (cl) { shots.push({ kind, dur, into, a: cl[0], b: cl[1] }); return; }
      kind = 'ktypo';
    }
    if (kind === 'searchbar') {
      if (kw.length >= 2) { shots.push({ kind, dur, into, dark: true, accentText: cap(kw[0]!, 22), b: cap(kw[1]!, 22) }); return; }
      kind = 'notes';
    }
    if (kind === 'notes') {
      const cl = twoClauses(p);
      shots.push({ kind, dur, into, dark: true, accentText: cap(cl ? cl[0] : p.text, 30), b: cl ? cl[1] : '' });
      return;
    }
    if (kind === 'timer') { shots.push({ kind, dur, into, accentText: cap(p.text, 22) }); return; }
    if (kind === 'timeline') { shots.push({ kind, dur, into, accentText: cap(p.text, 34) }); return; }
    if (kind === 'pill') { shots.push({ kind, dur, into, accentText: cap(p.text, 22) }); return; }
    if (kind === 'widgets') { shots.push({ kind, dur, into, accentText: cap(kw[0] || p.text, 20) }); return; }
    // ktypo (default / hook)
    const kt: Shot = { kind: 'ktypo', dur: i === 0 ? 3.0 : dur, into, accentText: cap(p.text, 34) };
    shots.push(i % 4 === 3 ? { ...kt, c: 'warm' } : kt);
  });

  // sign-off always closes on the brand (the one non-transcript, trusted string).
  shots.push({ kind: 'signoff', dur: 2.8, into: 'morph', accentText: `made with ${brand}` });

  return shots.length >= 3 ? shots : null;
}
