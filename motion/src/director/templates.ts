// templates.ts — the UI-mockup template set: iOS-style motion (embossed pills, an app
// card, a search bar, a home screen, chat bubbles, a notification). Each is a deterministic
// (templateId, text, accent) -> SceneSpec carrying a `ui` payload that the MotionApple
// composition renders. No Python, one credit.

import type { SceneSpec, Format, Palette, UiTemplate } from '../spec';
import { CANVAS, PALETTES } from './vocabulary';

export type TemplateId = UiTemplate;

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

const parts = (text: string): string[] =>
  (text.includes(',') ? text.split(',') : text.split(/\s+/))
    .map((s) => s.trim())
    .filter(Boolean);

const DUR: Record<TemplateId, number> = {
  pills: 4.2, appcard: 5.0, search: 4.6, homescreen: 4.6, chat: 5.6, notify: 4.4,
};

export function templateSpec(id: TemplateId, text: string, opts: TemplateOpts = {}): SceneSpec {
  const format = opts.format ?? '9:16';
  const { w, h } = CANVAS[format];
  const seed = strHash(id + '|' + text) % 100000;
  const palKeys = Object.keys(PALETTES);
  const base = PALETTES[palKeys[seed % palKeys.length]!]!;
  const accent = opts.accent || '#3574ff';
  const palette: Palette = { ...base, accent };
  const safe = (text || '').trim() || 'DouchkoVE';
  const p = parts(safe);

  const title = p[0] ?? safe;
  const subtitle = p[1] ?? '';
  const lines =
    id === 'pills' ? p.slice(0, 5)
    : id === 'chat' ? p.slice(1, 5) // p[0] is the contact name (title)
    : id === 'notify' ? [p[0] ?? safe, p.slice(1).join(' ')].filter(Boolean)
    : p;

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
