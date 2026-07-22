// autoDirect.ts — the SENIOR-DESIGNER BRAIN for auto-overlay. Given a video's transcript
// (word timings) + sampled frames + brand, it decides WHAT motion graphic comes in WHEN and
// HOW — the way a senior motion designer would: sparse, meaningful, landing on the word,
// reinforcing the message, never cheap filler. GPT-5 (vision) is the director; a strong
// deterministic heuristic is the always-available fallback (offline/test/no-key). Both outputs
// pass through the same guardrails (autoGuards) so quality is enforced, not hoped for.

import type { OverlayBeat, OverlayPlan, OverlayVideo } from '../spec';
import { guardPlan } from './autoGuards';

export interface Word { readonly word: string; readonly start: number; readonly end: number; }

export interface AutoInput {
  readonly words: readonly Word[];
  readonly frames?: readonly string[]; // data URIs (jpg) for GPT-vision
  readonly video: OverlayVideo;
  readonly accent: string;
  readonly logo?: string;
  readonly font?: { family: string; url: string };
  readonly platform?: 'tiktok' | 'reels' | 'shorts' | 'none';
  readonly brandName?: string;
}

const STOP = new Set([
  'the', 'and', 'for', 'you', 'your', 'that', 'this', 'with', 'from', 'have', 'was', 'are',
  'ich', 'und', 'die', 'der', 'das', 'ein', 'eine', 'wie', 'wir', 'ist', 'auf', 'für', 'dir',
  'mit', 'von', 'den', 'dem', 'des', 'sind', 'heute', 'einen', 'eines', 'wird', 'werden',
]);

const clean = (w: string): string => w.replace(/[^\p{L}\p{N}]/gu, '');

/** Split the word stream into phrases at pauses (>0.4s) or sentence punctuation. */
function phrases(words: readonly Word[]): { text: string; words: Word[]; start: number; end: number }[] {
  const out: { text: string; words: Word[]; start: number; end: number }[] = [];
  let cur: Word[] = [];
  const flush = () => {
    if (!cur.length) return;
    out.push({ text: cur.map((w) => w.word.trim()).join(' ').replace(/\s+/g, ' ').trim(), words: cur, start: cur[0]!.start, end: cur[cur.length - 1]!.end });
    cur = [];
  };
  for (let i = 0; i < words.length; i++) {
    const w = words[i]!; cur.push(w);
    const next = words[i + 1];
    const gap = next ? next.start - w.end : 99;
    if (/[.!?]$/.test(w.word.trim()) || gap > 0.4 || cur.length >= 7) flush();
  }
  flush();
  return out;
}

const strongestWord = (ws: Word[]): string => {
  let best = '', score = 0;
  for (const w of ws) { const c = clean(w.word); if (c.length >= 4 && !STOP.has(c.toLowerCase()) && c.length > score) { score = c.length; best = c; } }
  return best;
};

/** Deterministic heuristic director — a competent, restrained plan from timing alone. */
export function heuristicAuto(input: AutoInput): OverlayBeat[] {
  const ph = phrases(input.words);
  const raw: any[] = [];
  ph.forEach((p, i) => {
    const numTok = p.words.map((w) => clean(w.word)).find((c) => /^\d[\d.,]*$/.test(c));
    const content = p.words.filter((w) => { const c = clean(w.word).toLowerCase(); return c.length >= 5 && !STOP.has(c); });
    if (i === 0) {
      // opening headline — the hook
      raw.push({ t: p.start, dur: Math.min(2.8, Math.max(1.6, p.end - p.start + 0.4)), kind: 'headline', text: p.text, anchor: 'center', enter: 'rise', emphasis: 0.95 });
    } else if (numTok) {
      raw.push({ t: p.words.find((w) => clean(w.word) === numTok)!.start, dur: 2.2, kind: 'stat', value: parseFloat(numTok.replace(',', '.')), label: strongestWord(p.words) || 'total', anchor: 'upper', enter: 'pop', emphasis: 0.85 });
    } else if (content.length >= 3 && i % 3 === 1) {
      raw.push({ t: p.start, dur: 2.2, kind: 'chips', items: content.slice(0, 3).map((w) => clean(w.word)), anchor: 'lower', enter: 'slide', emphasis: 0.6 });
    } else if (p.words.length >= 3 && i % 2 === 0) {
      raw.push({ t: p.start, dur: Math.min(2.6, p.end - p.start + 0.3), kind: 'lowerthird', text: p.text, anchor: 'lower', enter: 'slide', emphasis: 0.55 });
    } else if (p.words.length <= 2) {
      // short punchy line → a pure-graphic IMPACT instead of yet more text.
      raw.push({ t: p.start, dur: 1.1, kind: 'burst', anchor: 'center', enter: 'pop', emphasis: 0.75 });
    } else if (i % 4 === 3) {
      // section change → an accent SWEEP wipe (no text).
      raw.push({ t: p.start, dur: 0.9, kind: 'sweep', anchor: 'center', enter: 'wipe', emphasis: 0.6 });
    } else {
      const kw = strongestWord(p.words);
      if (kw) raw.push({ t: p.words.find((w) => clean(w.word) === kw)!.start, dur: 1.6, kind: 'keyword', text: kw, anchor: i % 2 ? 'upper' : 'center', enter: 'pop', emphasis: 0.7 });
    }
  });
  if (input.brandName || input.logo) {
    const last = ph[ph.length - 1];
    const t = last ? Math.max(0, last.end - 1.4) : Math.max(0, input.video.duration - 2);
    raw.push({ t, dur: 2.2, kind: 'brand', text: input.brandName || 'DouchkoVE', text2: 'made with DouchkoVE', anchor: 'center', enter: 'rise', emphasis: 0.8 });
  }
  const onsets = input.words.map((w) => w.start);
  const transcript = input.words.map((w) => w.word).join(' ');
  const opts: any = { videoDur: input.video.duration, onsets, transcript };
  if (input.brandName) opts.brandName = input.brandName;
  return guardPlan(raw, opts);
}

const REGIE_AUTO = `You are a SENIOR MOTION DESIGNER directing motion graphics laid over a creator's video.
You are given the spoken transcript (with per-word timings) and sampled frames of the footage.
Decide a SPARSE, high-impact set of motion "beats" that reinforce the message — the way a senior
designer works, never a cheap template dump.

HARD RULES:
- NEVER invent text. Every word you put on screen (text, text2, keyword, chips, stat label)
  MUST be copied VERBATIM from the transcript below — same spelling, no paraphrase, no new words,
  no translation. A "stat" value must be a number actually spoken. If you cannot ground a caption
  in the transcript, use a text-free graphic beat (burst/sweep/pulse/brackets) instead. Ungrounded
  text will be discarded, so grounding it is the only way your beat keeps its words.
- Restraint: far fewer beats than words. Silence between beats is good. Never clutter the frame.
- Land on the word: a beat's "t" must equal the start time of the exact word it reinforces.
- Meaning first: only surface a beat when it ADDS (a hook, a key term, a number, a punchline,
  a brand sign-off). If it does not add, do not place it.
- Variety: alternate placement (top/upper/center/lower) and entrance style; never stack two in a row.
- Match the footage: use what you SEE in the frames (subject, setting, mood) to choose tone.
- No overlaps. Durations 1.2–3.4s.

Beat kinds — TEXT: "headline" (the opening hook, big), "lowerthird" (name/claim, lower band),
"keyword" (one punchy word popping), "chips" (2–5 short tags), "stat" (a number counting up),
"brand" (sign-off with the brand).
Beat kinds — PURE GRAPHIC (NO text, used sparingly as motion accents, not every beat):
"burst" (an impact of shards + ring on a punchline), "sweep" (an accent band wiping across at
a section change / transition), "pulse" (a full-frame accent energy hit on a strong beat),
"brackets" (focus corners snapping in to spotlight the subject). Mix these in for rhythm so
the piece is motion design, not just captions — but keep it restrained.

Return STRICT JSON: {"beats":[{"t":s,"dur":s,"kind":..,"text":..,"text2":..,"items":[..],
"value":n,"label":..,"anchor":"top|upper|center|lower|bottom","enter":"rise|pop|slide|wipe",
"emphasis":0..1}]}. Only include fields a kind needs.`;

async function gptAuto(input: AutoInput, key: string): Promise<OverlayBeat[] | null> {
  const model = process.env['OPENAI_MODEL'] ?? 'gpt-5';
  const isNew = /^(gpt-5|o1|o3|o4)/.test(model);
  const tsv = input.words.map((w) => `${w.start.toFixed(2)} ${w.word.trim()}`).join('\n').slice(0, 12000);
  const content: any[] = [
    { type: 'text', text: `Video ${input.video.duration.toFixed(1)}s, ${input.video.w}x${input.video.h}. Transcript (start word):\n${tsv}\n\nDirect the motion beats now.` },
  ];
  for (const f of (input.frames ?? []).slice(0, 6)) content.push({ type: 'image_url', image_url: { url: f } });
  const body: Record<string, unknown> = {
    model, response_format: { type: 'json_object' },
    messages: [{ role: 'system', content: REGIE_AUTO }, { role: 'user', content }],
  };
  if (!isNew) body['temperature'] = 0.7;
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) return null;
  const j: any = await res.json();
  try {
    const parsed = JSON.parse(j.choices[0].message.content);
    const beats = Array.isArray(parsed) ? parsed : parsed.beats;
    if (!Array.isArray(beats)) return null;
    const gopts: any = {
      videoDur: input.video.duration,
      onsets: input.words.map((w) => w.start),
      transcript: input.words.map((w) => w.word).join(' '),
    };
    if (input.brandName) gopts.brandName = input.brandName;
    return guardPlan(beats, gopts);
  } catch { return null; }
}

/** Compose the full overlay plan. AI (vision) when a key is present, heuristic otherwise.
 *  Never throws — always returns a renderable plan. */
export async function autoDirect(input: AutoInput): Promise<OverlayPlan> {
  let beats: OverlayBeat[] | null = null;
  const key = process.env['OPENAI_API_KEY'];
  if (key) { try { beats = await gptAuto(input, key); } catch { beats = null; } }
  if (!beats || !beats.length) beats = heuristicAuto(input);
  const seed = Math.abs(input.words.reduce((a, w) => a + w.word.length, 0)) % 100000;
  const plan: any = {
    version: 1, seed, video: input.video, accent: input.accent || '#e0483d', beats,
  };
  if (input.logo) plan.logo = input.logo;
  if (input.font) plan.font = input.font;
  if (input.platform && input.platform !== 'none') plan.platform = input.platform;
  return plan as OverlayPlan;
}
