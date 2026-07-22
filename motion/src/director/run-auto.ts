// run-auto.ts — CLI bridge for the auto-overlay director. Reads an input JSON
// ({words, frames, video, accent, logo?, font?, platform?}) from --input=<path>, runs the
// senior-designer brain (autoDirect: GPT-5 vision when a key is present, heuristic otherwise),
// and writes the validated OverlayPlan JSON to stdout. Bundled to ESM via esbuild.

import { readFileSync } from 'node:fs';
import { autoDirect, type AutoInput } from './autoDirect';

async function main(): Promise<void> {
  const arg = process.argv.find((a) => a.startsWith('--input='));
  if (!arg) { process.stderr.write('usage: run-auto --input=<file.json>\n'); process.exit(2); }
  const input = JSON.parse(readFileSync(arg.split('=').slice(1).join('='), 'utf8')) as AutoInput;
  const plan = await autoDirect(input);
  // The MotionOverlay component takes { plan }, so wrap it (mirrors run.ts emitting { spec }).
  process.stdout.write(JSON.stringify({ plan }));
}

void main();
