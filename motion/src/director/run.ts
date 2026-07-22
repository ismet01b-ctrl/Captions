// run.ts — CLI bridge: brief -> validated SceneSpec JSON on stdout. The Python server
// (or a Node service) calls this, then feeds the JSON to `remotion render --props`.
//
//   node out/run.mjs "3.4M views in 24h — made for creators" > out/brief.json
//
// Bundled to ESM via esbuild (no ts-node needed). Also asserts schema<->heuristic parity.

import { directBrief } from './director';
import { parseSpec } from './schema';

async function main(): Promise<void> {
  const text = process.argv[2] ?? 'Unlimited motion for every creator';
  const spec = await directBrief({ text });
  if (!parseSpec(spec)) {
    process.stderr.write('FATAL: director produced a spec the schema rejects\n');
    process.exit(1);
  }
  process.stdout.write(JSON.stringify({ spec }, null, 2));
}

void main();
