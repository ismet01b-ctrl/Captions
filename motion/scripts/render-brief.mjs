// render-brief.mjs — the one-command bridge the Python server calls:
//   node scripts/render-brief.mjs "<brief>" out/video.mp4 [--browser-executable=PATH] [--codec=prores]
//
// brief -> AI director (validated SceneSpec) -> Remotion render -> MP4/ProRes.
// Self-contained: no live-deploy coupling. The Python side just spawns this and reads the
// output file, exactly like it spawns render.py / gfx_engine.py today.

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const [, , brief, outArg, ...rest] = process.argv;
if (!brief) {
  process.stderr.write('usage: render-brief.mjs "<brief>" [out.mp4] [--browser-executable=..] [--codec=prores]\n');
  process.exit(2);
}
const out = outArg && !outArg.startsWith('--') ? outArg : 'out/video.mp4';
const passthrough = (outArg && outArg.startsWith('--') ? [outArg] : []).concat(rest);
mkdirSync(dirname(out), { recursive: true });
mkdirSync('out', { recursive: true });

const bin = 'node_modules/.bin/esbuild';

// 1) Bundle the director (TS -> ESM) and produce a validated SceneSpec from the brief.
execFileSync(bin, [
  'src/director/run.ts',
  '--bundle',
  '--platform=node',
  '--format=esm',
  '--outfile=out/_director.mjs',
  '--log-level=error',
]);
const specJson = execFileSync('node', ['out/_director.mjs', brief], { maxBuffer: 8 << 20 }).toString();
writeFileSync('out/_spec.json', specJson);

// 2) Render the spec. Remotion manages its own headless browser in production; in the
//    sandbox pass --browser-executable=... through `rest`.
const codecArg = passthrough.find((a) => a.startsWith('--codec='));
const codec = codecArg ? codecArg.split('=')[1] : 'h264';
execFileSync(
  'npx',
  [
    'remotion',
    'render',
    'src/index.ts',
    'MotionVideo',
    out,
    '--props=out/_spec.json',
    `--codec=${codec}`,
    ...passthrough.filter((a) => !a.startsWith('--codec=')),
  ],
  { stdio: 'inherit' },
);
process.stderr.write(`\nOK: ${out}\n`);
