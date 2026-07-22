// run.ts — CLI bridge: brief -> validated SceneSpec JSON on stdout. The Python server
// (or a Node service) calls this, then feeds the JSON to `remotion render --props`.
//
//   node out/run.mjs "3.4M views in 24h — made for creators" > out/brief.json
//
// Bundled to ESM via esbuild (no ts-node needed). Also asserts schema<->heuristic parity.

import { directBrief } from './director';
import { parseSpec } from './schema';
import { templateSpec, isTemplateId } from './templates';
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
  const tplOpts: { accent?: string; format?: Format } = {};
  if (accent) tplOpts.accent = accent;
  if (format) tplOpts.format = format;
  const spec = tpl && isTemplateId(tpl)
    ? templateSpec(tpl, text, tplOpts)
    : await directBrief({ text, noText: flag || sniff });
  if (!parseSpec(spec)) {
    process.stderr.write('FATAL: director produced a spec the schema rejects\n');
    process.exit(1);
  }
  process.stdout.write(JSON.stringify({ spec }, null, 2));
}

void main();
