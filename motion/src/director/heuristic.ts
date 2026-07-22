// heuristic.ts — deterministic brief -> SceneSpec composer. This is the fallback when no
// OPENAI_API_KEY is set (mirrors the Python engine's heuristic path), and it doubles as
// the offline-testable proof that a one-line brief becomes a valid, renderable spec.

import type { Block, KineticHeadline, Scene, SceneSpec } from '../spec';
import { CANVAS, DEFAULT_SPRING, PALETTES } from './vocabulary';
import type { Brief } from './director';

const strHash = (s: string): number => {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
};

const STOP = new Set(['the', 'a', 'an', 'to', 'for', 'of', 'and', 'my', 'your', 'with', 'in', 'on']);

/** Split a brief into short, punchy phrases (<= 3 substance words each). */
function phrases(text: string): string[][] {
  const clauses = text
    .split(/[.,;:!?\n]+/)
    .map((c) => c.trim())
    .filter(Boolean);
  const out: string[][] = [];
  for (const c of clauses) {
    const words = c.split(/\s+/).filter(Boolean);
    for (let i = 0; i < words.length; i += 3) out.push(words.slice(i, i + 3));
  }
  return out.length ? out : [['MOTION']];
}

interface Stat {
  value: number;
  suffix: string;
  label: string;
}

/** Pull the first meaningful number out of the brief, if any. */
function findStat(text: string): Stat | null {
  const m = text.match(/(\d[\d.,]*)\s*(%|x|k|m|bn)?/i);
  if (!m) return null;
  const num = parseFloat(m[1]!.replace(/,/g, ''));
  if (!Number.isFinite(num)) return null;
  const unit = (m[2] ?? '').toLowerCase();
  const mult = unit === 'k' ? 1e3 : unit === 'm' ? 1e6 : unit === 'bn' ? 1e9 : 1;
  const suffix = unit === '%' || unit === 'x' ? unit : '';
  // Label = the words that FOLLOW the number, up to the next punctuation (max 3).
  const after = text.slice((m.index ?? 0) + m[0].length).split(/[.,;:!?]/)[0] ?? '';
  const label =
    after
      .split(/\s+/)
      .filter((w) => w && !STOP.has(w.toLowerCase()))
      .slice(0, 3)
      .join(' ')
      .toUpperCase() || 'RESULT';
  return { value: Math.round(num * mult), suffix, label: label.slice(0, 40) };
}

function kinetic(id: string, words: string[], tIn: number, bpm: number, weight: [number, number]): KineticHeadline {
  const period = 60 / bpm;
  return {
    id,
    kind: 'kineticHeadline',
    slot: 0,
    spring: { ...DEFAULT_SPRING },
    weight,
    beatSync: true,
    words: words.map((w, i) => {
      const start = tIn + 0.45 + i * period * 0.5;
      return { text: w.toUpperCase(), start, end: start + 0.5 };
    }),
  };
}

export function heuristicSpec(brief: Brief): SceneSpec {
  const format = brief.format ?? '9:16';
  const { w, h } = CANVAS[format];
  const bpm = brief.bpm ?? 120;
  const seed = strHash(brief.text) % 100000;
  const palKeys = Object.keys(PALETTES);
  const palette = { ...PALETTES[palKeys[seed % palKeys.length]!]!, ...(brief.palette ?? {}) };

  const ph = phrases(brief.text);
  const stat = findStat(brief.text);
  const scenes: Scene[] = [];
  let t = 0;

  const pushScene = (blocks: Block[], len: number, inKind: Scene['in']['kind'], outKind: Scene['out']['kind']) => {
    const inDur = 0.45;
    const outDur = 0.5;
    scenes.push({
      id: `s${scenes.length + 1}`,
      tStart: t,
      tLen: len,
      in: { kind: inKind, dur: inDur },
      out: { kind: outKind, dur: outDur },
      blocks,
    });
    t += inDur + len - outDur * 0.6; // slight overlap -> continuous flow
  };

  // Scene 1 — hook headline + accent underline.
  const hook = ph[0]!;
  pushScene(
    [
      kinetic('s1-h', hook, 0, bpm, [500, 900]),
      {
        id: 's1-u',
        kind: 'accentUnderline',
        slot: 1,
        spring: { stiffness: 150, damping: 0.7, delay: 0.25 },
        follows: 's1-h',
        widthPct: 0.5,
      },
    ],
    2.0,
    'rise',
    'whip',
  );

  // Scene 2 — a stat if the brief carries a number, else the second phrase.
  if (stat) {
    pushScene(
      [
        {
          id: 's2-stat',
          kind: 'statCard',
          slot: 0,
          spring: { stiffness: 120, damping: 0.66, delay: 0 },
          value: stat.value,
          suffix: stat.suffix,
          label: stat.label,
          countUp: true,
        },
      ],
      2.2,
      'whip',
      'fade',
    );
  } else if (ph[1]) {
    pushScene([kinetic('s2-h', ph[1], scenes[scenes.length - 1]!.tStart, bpm, [420, 840])], 2.0, 'scaleIn', 'fade');
  }

  // Final scene — closing line (last phrase, or a default).
  const closer = ph[ph.length - 1] && ph.length > 1 ? ph[ph.length - 1]! : ['MADE', 'FOR', 'YOU'];
  const sIn = scenes.length ? scenes[scenes.length - 1]!.tStart : 0;
  pushScene(
    [
      kinetic('s3-h', closer, sIn, bpm, [400, 860]),
      {
        id: 's3-u',
        kind: 'accentUnderline',
        slot: 1,
        spring: { stiffness: 150, damping: 0.7, delay: 0.3 },
        follows: 's3-h',
        widthPct: 0.42,
      },
    ],
    2.0,
    'rise',
    'fade',
  );

  const last = scenes[scenes.length - 1]!;
  const duration = last.tStart + last.in.dur + last.tLen + last.out.dur;

  return {
    version: 1,
    seed,
    canvas: { format, w, h },
    fps: 30,
    duration: Math.round(duration * 100) / 100,
    grain: 6,
    palette,
    beat: { bpm, offset: 0, snapTol: 0.09 },
    scenes,
  };
}
