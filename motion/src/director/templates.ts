// templates.ts — curated Remotion templates that REPLACE the old Python gfx_engine
// templates. Each one is a deterministic (templateId, text, style) -> SceneSpec built
// from the existing vetted blocks, so it renders through the very same Remotion pipeline
// as the AI brief (MotionVideo / Motion3D). No Python, one credit, MP4 or ProRes-alpha.

import type { Block, Scene, SceneSpec, Format, Palette } from '../spec';
import { CANVAS, DEFAULT_SPRING, PALETTES } from './vocabulary';

export type TemplateId = 'pills' | 'title' | 'lowerthird' | 'stat' | 'quote';

export const TEMPLATES: readonly { id: TemplateId; label: string; hint: string }[] = [
  { id: 'pills', label: 'Pills', hint: 'Up to 5 keyword pills that pop in' },
  { id: 'title', label: 'Title', hint: 'One bold kinetic headline' },
  { id: 'lowerthird', label: 'Lower third', hint: 'Name + role with an accent bar' },
  { id: 'stat', label: 'Big stat', hint: 'A number that counts up' },
  { id: 'quote', label: 'Quote', hint: 'An oversized pull-quote' },
];

const TEMPLATE_IDS = new Set<TemplateId>(TEMPLATES.map((t) => t.id));
export const isTemplateId = (x: string): x is TemplateId => TEMPLATE_IDS.has(x as TemplateId);

const strHash = (s: string): number => {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
};

export interface TemplateOpts {
  readonly format?: Format;
  readonly accent?: string;
  readonly bpm?: number;
}

/** Split a brief/word string into short items (by comma, else by word). */
function items(text: string, max: number): string[] {
  const raw = text.includes(',')
    ? text.split(',')
    : text.split(/\s+/);
  return raw.map((s) => s.trim()).filter(Boolean).slice(0, max);
}

function headlineWords(text: string, tIn: number, bpm: number): { text: string; start: number; end: number }[] {
  const period = 60 / bpm;
  return items(text, 6).map((w, i) => {
    const start = tIn + 0.4 + i * period * 0.5;
    return { text: w.toUpperCase(), start, end: start + 0.5 };
  });
}

/** Pull the first meaningful number for the stat template. */
function firstStat(text: string): { value: number; suffix: string; label: string } {
  const m = text.match(/(\d[\d.,]*)\s*(%|x|k|m|bn)?/i);
  if (!m) return { value: 100, suffix: '%', label: items(text, 3).join(' ').toUpperCase() || 'RESULT' };
  const num = parseFloat(m[1]!.replace(/,/g, ''));
  const unit = (m[2] ?? '').toLowerCase();
  const mult = unit === 'k' ? 1e3 : unit === 'm' ? 1e6 : unit === 'bn' ? 1e9 : 1;
  const suffix = unit === '%' || unit === 'x' ? unit : '';
  const after = text.slice((m.index ?? 0) + m[0].length).trim();
  const label = (after.split(/[.,;:!?]/)[0] ?? '').split(/\s+/).filter(Boolean).slice(0, 3).join(' ').toUpperCase();
  return { value: Math.round(num * mult), suffix, label: label || 'RESULT' };
}

export function templateSpec(id: TemplateId, text: string, opts: TemplateOpts = {}): SceneSpec {
  const format = opts.format ?? '9:16';
  const { w, h } = CANVAS[format];
  const bpm = opts.bpm ?? 120;
  const seed = strHash(id + '|' + text) % 100000;
  const palKeys = Object.keys(PALETTES);
  const base = PALETTES[palKeys[seed % palKeys.length]!]!;
  const palette: Palette = { ...base, ...(opts.accent ? { accent: opts.accent } : {}) };
  const safe = (text || '').trim() || 'DouchkoVE';

  const blocks: Block[] = [];
  let len = 3.4;

  switch (id) {
    case 'pills': {
      blocks.push({
        id: 't-pills', kind: 'chipRow', slot: 0, spring: { ...DEFAULT_SPRING },
        items: items(safe, 5).map((s) => s) as readonly string[],
      });
      len = 3.6;
      break;
    }
    case 'title': {
      blocks.push({
        id: 't-h', kind: 'kineticHeadline', slot: 0, spring: { ...DEFAULT_SPRING },
        words: headlineWords(safe, 0, bpm), weight: [500, 900], beatSync: true,
      });
      len = 3.4;
      break;
    }
    case 'lowerthird': {
      const parts = safe.split(',');
      const line = (parts[0] ?? safe).trim();
      blocks.push({
        id: 'lt-h', kind: 'kineticHeadline', slot: 0, spring: { ...DEFAULT_SPRING },
        words: headlineWords(line, 0, bpm), weight: [500, 850], beatSync: true,
      });
      blocks.push({
        id: 'lt-u', kind: 'accentUnderline', slot: 1,
        spring: { stiffness: 150, damping: 0.7, delay: 0.3 }, follows: 'lt-h', widthPct: 0.5,
      });
      len = 3.6;
      break;
    }
    case 'stat': {
      const s = firstStat(safe);
      blocks.push({
        id: 't-stat', kind: 'statCard', slot: 0,
        spring: { stiffness: 120, damping: 0.66, delay: 0 },
        value: s.value, suffix: s.suffix, label: s.label, countUp: true,
      });
      len = 3.8;
      break;
    }
    case 'quote': {
      const [q, author] = safe.split('—').map((s) => s.trim());
      blocks.push({
        id: 't-q', kind: 'bigQuote', slot: 0, spring: { ...DEFAULT_SPRING },
        text: (q || safe).slice(0, 140), ...(author ? { author: author.slice(0, 40) } : {}),
      });
      len = 4.0;
      break;
    }
  }

  const inDur = 0.45;
  const outDur = 0.5;
  const scene: Scene = {
    id: 's1', tStart: 0, tLen: len,
    in: { kind: 'rise', dur: inDur }, out: { kind: 'fade', dur: outDur }, blocks,
  };
  const duration = Math.round((inDur + len + outDur) * 100) / 100;

  return {
    version: 1, seed, canvas: { format, w, h }, fps: 30, duration, grain: 5,
    palette, beat: { bpm, offset: 0, snapTol: 0.09 }, scenes: [scene],
  };
}
