// render-showcase.mjs — the one-command bridge the Python server spawns to turn a TRANSCRIPT into
// a per-user motion video in the chosen COMPOSITION + STYLE:
//   node scripts/render-showcase.mjs <transcript.json> /abs/out.mp4 \
//        [--composition=showcase|kinetic|prompt] [--style=editorial|bold|soft|mono] \
//        [--brand="Name"] [--format=16:9|9:16|1:1] [--browser-executable=PATH] [--codec=prores]
//
// transcript.json = [{ "word": " Hi", "start": 0.0, "end": 0.25 }, ...] (Whisper words).
// The storyboard is generated deterministically from the words (buildShowcase) — text stays
// verbatim from the transcript (no hallucination). Self-contained + concurrency-safe.

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';

function findBrowser(args) {
  if (args.find((a) => a.startsWith('--browser-executable='))) return null;
  const env = process.env.DVE_CHROMIUM || process.env.REMOTION_BROWSER_EXECUTABLE;
  const cands = [env, '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable'].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return null;
}
const arg = (rest, name, def) => { const f = rest.find((a) => a.startsWith(`--${name}=`)); return f ? f.split('=').slice(1).join('=') : def; };

const [, , transcriptPath, outArg, ...rest] = process.argv;
if (!transcriptPath || !outArg) {
  process.stderr.write('usage: render-showcase.mjs <transcript.json> <out.mp4> [--composition=] [--style=] [--brand=] [--format=] [--browser-executable=]\n');
  process.exit(2);
}
const out = outArg;
const composition = ({ showcase: 'MotionShowcase', kinetic: 'MotionKinetic', prompt: 'MotionPrompt' })[arg(rest, 'composition', 'showcase')] || 'MotionShowcase';
const style = arg(rest, 'style', 'editorial');
const brand = arg(rest, 'brand', 'DouchkoVE');
const format = arg(rest, 'format', '9:16');
const codec = arg(rest, 'codec', 'h264');
const dims = ({ '16:9': [1920, 1080], '9:16': [1080, 1920], '1:1': [1080, 1080] })[format] || [1080, 1920];
mkdirSync(dirname(out), { recursive: true });

const work = mkdtempSync(join(tmpdir(), 'dve-showcase-'));
try {
  const esbuild = 'node_modules/.bin/esbuild';
  const genBundle = join(work, 'gen.mjs');
  const propsPath = join(work, 'props.json');

  // 1) Bundle a tiny generator: transcript words -> storyboard -> props JSON (spec + story + styleId).
  const genEntry = join(work, 'gen-entry.mjs');
  writeFileSync(genEntry, `
import { buildShowcase } from ${JSON.stringify(join(process.cwd(), 'src/director/buildShowcase.ts'))};
import { demoProps } from ${JSON.stringify(join(process.cwd(), 'src/demo-spec.ts'))};
import { readFileSync, writeFileSync } from 'node:fs';
const words = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const story = buildShowcase(Array.isArray(words) ? words : (words.words || []), { brandName: process.argv[5] });
const spec = JSON.parse(JSON.stringify(demoProps.spec));
spec.canvas = { w: Number(process.argv[3]), h: Number(process.argv[4]) };
spec.fps = 30;
const out = { spec, styleId: process.argv[6] };
if (story && story.length) out.story = story;
writeFileSync(process.argv[7], JSON.stringify(out));
process.stderr.write('shots=' + (story ? story.length : 0) + '\\n');
`);
  execFileSync(esbuild, [genEntry, '--bundle', '--platform=node', '--format=esm', `--outfile=${genBundle}`, '--log-level=error']);
  execFileSync('node', [genBundle, transcriptPath, String(dims[0]), String(dims[1]), brand, style, propsPath], { stdio: 'inherit' });

  // 2) Render the chosen composition.
  const browser = findBrowser(rest);
  execFileSync('npx', [
    'remotion', 'render', 'src/index.ts', composition, out,
    `--props=${propsPath}`, `--codec=${codec}`,
    ...(browser ? [`--browser-executable=${browser}`] : []),
    ...rest.filter((a) => a.startsWith('--concurrency=') || a.startsWith('--log=')),
  ], { stdio: 'inherit' });
  process.stderr.write(`\nOK: ${out}\n`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
