// run.ts — CLI bridge: brief -> validated SceneSpec JSON on stdout. The Python server
// (or a Node service) calls this, then feeds the JSON to `remotion render --props`.
//
//   node out/run.mjs "3.4M views in 24h — made for creators" > out/brief.json
//
// Bundled to ESM via esbuild (no ts-node needed). Also asserts schema<->heuristic parity.

import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { directBrief } from './director';
import { parseSpec } from './schema';
import { templateSpec, isTemplateId, sequenceSpec } from './templates';
import { SFX_KEYS } from '../lib/transitions';
import type { Format } from '../spec';

const argVal = (name: string): string | null => {
  const a = process.argv.find((x) => x.startsWith(`--${name}=`));
  return a ? a.split('=').slice(1).join('=') : null;
};

async function main(): Promise<void> {
  const text = process.argv[2] ?? 'Unlimited motion for every creator';
  // A curated template (--template=pills|title|…) builds its spec deterministically;
  // otherwise the AI director composes from the brief.
  const tpl = argVal('template');
  const accent = argVal('accent') ?? undefined;
  const format = (argVal('format') as Format | null) ?? undefined;
  // No-text (pure motion graphics) via `--no-text` or env, plus a light
  // natural-language sniff so a brief that literally says "no text" is honoured too.
  const flag = process.argv.includes('--no-text') || process.env['DVE_NOTEXT'] === '1';
  const sniff = /\b(no text|without text|textless|kein text|ohne text|nur grafik|graphics only|pure motion)\b/i.test(
    text,
  );
  const seqJson = argVal('sequence');
  const isTpl = tpl && isTemplateId(tpl);
  const tplOpts: { accent?: string; format?: Format } = {};
  if (accent) tplOpts.accent = accent;
  if (format) tplOpts.format = format;
  let seqItems: { template: string; text: string; transition?: string }[] | null = null;
  if (seqJson) {
    try {
      const parsed = JSON.parse(seqJson);
      if (Array.isArray(parsed)) {
        seqItems = parsed.map((x) => {
          const it: { template: string; text: string; transition?: string } = {
            template: String(x.template), text: String(x.text ?? ''),
          };
          if (x.transition) it.transition = String(x.transition);
          return it;
        });
      }
    } catch { seqItems = null; }
  }
  let spec = seqItems && seqItems.length
    ? sequenceSpec(seqItems, tplOpts)
    : isTpl
      ? templateSpec(tpl, text, tplOpts)
      : await directBrief({ text, noText: flag || sniff });
  // Sequence SFX: mount only the transition sounds whose CC0 asset is actually present
  // (public/sfx/<key>.wav). No pack -> silent, matching the engine's "silence over a cheap
  // synthetic tone" rule. Probed here (node) so the pure spec builders stay fs-free.
  if (seqItems && seqItems.length) {
    const present = SFX_KEYS.filter((k) => existsSync(join(process.cwd(), 'public', 'sfx', `${k}.wav`)));
    if (present.length) spec = { ...spec, sfx: present };
  }
  // AI output is untrusted -> validate. Template specs are trusted, deterministic code
  // and carry a `ui` payload (scenes:[]) the block schema doesn't cover, so skip it.
  const trusted = isTpl || (seqItems && seqItems.length > 0);
  if (!trusted && !parseSpec(spec)) {
    process.stderr.write('FATAL: director produced a spec the schema rejects\n');
    process.exit(1);
  }
  process.stdout.write(JSON.stringify({ spec }, null, 2));
}

void main();
