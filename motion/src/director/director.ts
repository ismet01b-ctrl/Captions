// director.ts — brief -> validated SceneSpec. Same shape as the Python caption engine's
// ai_direct(): GPT-4o composes from the curated vocabulary, a strict validator repairs
// the output, and a deterministic heuristic is the always-available fallback (and the
// offline test path). The renderer only ever sees a schema-valid spec.

import type { Format, Palette, SceneSpec } from '../spec';
import { parseSpec } from './schema';
import { heuristicSpec } from './heuristic';
import { SYSTEM_PROMPT } from './vocabulary';

export interface Brief {
  readonly text: string;
  readonly format?: Format;
  readonly bpm?: number;
  readonly palette?: Partial<Palette>;
}

/** Compose a spec from a brief. Never throws — always returns a renderable spec. */
export async function directBrief(brief: Brief): Promise<SceneSpec> {
  const key = process.env['OPENAI_API_KEY'];
  if (key) {
    try {
      const spec = await gptDirect(brief, key);
      if (spec) return spec;
    } catch {
      // fall through to the deterministic composer
    }
  }
  return heuristicSpec(brief);
}

async function gptDirect(brief: Brief, key: string): Promise<SceneSpec | null> {
  // Match the Python engine's model handling: default gpt-5 (env-overridable), and the
  // gpt-5 / o-series reject `temperature`, so omit it for those (same as render.py).
  const model = process.env['OPENAI_MODEL'] ?? 'gpt-5';
  const isNew = /^(gpt-5|o1|o3|o4)/.test(model);
  const body: Record<string, unknown> = {
    model,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: briefToPrompt(brief) },
    ],
  };
  if (!isNew) body['temperature'] = 0.6;
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const content = data.choices?.[0]?.message?.content;
  if (!content) return null;
  let raw: unknown;
  try {
    raw = JSON.parse(content);
  } catch {
    return null;
  }
  // The model returns the SceneSpec (optionally wrapped in { spec }). Repair + validate.
  const candidate = (raw as { spec?: unknown }).spec ?? raw;
  return parseSpec(candidate); // null -> caller falls back to heuristic
}

function briefToPrompt(brief: Brief): string {
  const fmt = brief.format ?? '9:16';
  return [
    `Brief: ${brief.text}`,
    `Format: ${fmt}`,
    brief.bpm ? `BPM: ${brief.bpm}` : '',
    `Canvas must match the format. Produce 2-4 scenes, 6-10s total.`,
  ]
    .filter(Boolean)
    .join('\n');
}
