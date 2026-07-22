// templates.ts — the UI-mockup template set: iOS-style motion (embossed pills, an app
// card, a search bar, a home screen, chat bubbles, a notification). Each is a deterministic
// (templateId, text, accent) -> SceneSpec carrying a `ui` payload that the MotionApple
// composition renders. No Python, one credit.

import type { SceneSpec, Format, Palette, UiTemplate, SeqSegment, UiSpec, TransId } from '../spec';
import { CANVAS, PALETTES } from './vocabulary';
import { isTransId } from '../lib/transitions';

export type TemplateId = UiTemplate;

/** Seconds of cross-transition overlap between two chained segments. */
export const SEQ_TRANSITION = 0.55;

export const TEMPLATES: readonly { id: TemplateId; label: string; hint: string }[] = [
  { id: 'pills', label: 'Pills', hint: 'Embossed keyword pills that pop in' },
  { id: 'appcard', label: 'App card', hint: 'A store-style download card' },
  { id: 'search', label: 'Search bar', hint: 'A query typing into a search field' },
  { id: 'homescreen', label: 'Home screen', hint: 'An app grid springing in' },
  { id: 'chat', label: 'Chat', hint: 'Message bubbles in a conversation' },
  { id: 'notify', label: 'Notification', hint: 'A banner dropping from the top' },
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
}

const DUR: Record<TemplateId, number> = {
  pills: 4.2, appcard: 5.0, search: 4.6, homescreen: 4.6, chat: 5.6, notify: 4.4,
};

const commaParts = (text: string): string[] =>
  text.split(',').map((s) => s.trim()).filter(Boolean);

/**
 * Per-template text parsing. This is the ONE place input semantics live, so a phrase
 * template (search) is never word-split, comma templates keep multi-word fields intact,
 * and every branch degrades gracefully on odd input. Pure + unit-tested.
 */
export function parseTemplateText(id: TemplateId, raw: string): { title: string; subtitle: string; lines: string[] } {
  const safe = (raw || '').trim() || 'DouchkoVE';
  const cp = commaParts(safe);
  switch (id) {
    case 'pills': {
      // multiple pills: comma-separated (keeps multi-word pills), else one pill per word.
      const items = safe.includes(',') ? cp : safe.split(/\s+/).filter(Boolean);
      return { title: '', subtitle: '', lines: items.slice(0, 5) };
    }
    case 'search':
      // the WHOLE phrase is the query — never word-split.
      return { title: safe, subtitle: '', lines: [] };
    case 'appcard':
      return { title: cp[0] || safe, subtitle: cp[1] || 'Productivity', lines: [] };
    case 'notify':
      return { title: cp[0] || safe, subtitle: cp.slice(1).join(', ') || 'Your clip is ready to share', lines: [] };
    case 'homescreen':
      return { title: cp[0] || '', subtitle: '', lines: [] };
    case 'chat':
    default:
      // "Contact, messages…". With <2 parts, show the input as a single message.
      return cp.length >= 2
        ? { title: cp[0]!, subtitle: '', lines: cp.slice(1, 5) }
        : { title: 'Messages', subtitle: '', lines: cp.slice(0, 4) };
  }
}

export function templateSpec(id: TemplateId, text: string, opts: TemplateOpts = {}): SceneSpec {
  const format = opts.format ?? '9:16';
  const { w, h } = CANVAS[format];
  const seed = strHash(id + '|' + text) % 100000;
  const palKeys = Object.keys(PALETTES);
  const base = PALETTES[palKeys[seed % palKeys.length]!]!;
  const accent = opts.accent || '#3574ff';
  const palette: Palette = { ...base, accent };
  const { title, subtitle, lines } = parseTemplateText(id, text);

  return {
    version: 1,
    seed,
    canvas: { format, w, h },
    fps: 30,
    duration: DUR[id],
    grain: 0,
    palette,
    beat: { bpm: 120, offset: 0, snapTol: 0.09 },
    scenes: [],
    ui: { template: id, title, subtitle, lines, accent },
  };
}

/** Build a chained-sequence spec: several UI mockups played back-to-back as ONE video. */
export function sequenceSpec(
  items: readonly { template: string; text: string; transition?: string }[],
  opts: TemplateOpts = {},
): SceneSpec {
  const format = opts.format ?? '9:16';
  const { w, h } = CANVAS[format];
  const accent = opts.accent || '#3574ff';
  const valid = items.filter((it) => isTemplateId(it.template));
  const src = valid.length ? valid : [{ template: 'pills', text: 'Write, Create, Solve' } as typeof items[number]];
  const segs: SeqSegment[] = src.map((it) => {
    const id = it.template as TemplateId;
    const { title, subtitle, lines } = parseTemplateText(id, it.text);
    const ui: UiSpec = { template: id, title, subtitle, lines, accent };
    const tr = it.transition && isTransId(it.transition) ? (it.transition as TransId) : undefined;
    return tr ? { ui, dur: DUR[id], transition: tr } : { ui, dur: DUR[id] };
  });
  const total = segs.reduce((a, s) => a + s.dur, 0) - SEQ_TRANSITION * (segs.length - 1);
  const seed = strHash(segs.map((s) => s.ui.template + s.ui.title).join('|')) % 100000;
  const base = PALETTES[Object.keys(PALETTES)[seed % Object.keys(PALETTES).length]!]!;
  return {
    version: 1, seed, canvas: { format, w, h }, fps: 30,
    duration: Math.round(total * 100) / 100, grain: 0,
    palette: { ...base, accent }, beat: { bpm: 120, offset: 0, snapTol: 0.09 },
    scenes: [], sequence: segs,
  };
}
