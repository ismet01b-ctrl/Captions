// render-brief.mjs — the one-command bridge the Python server spawns:
//   node scripts/render-brief.mjs "<brief>" /abs/out.mp4 [--browser-executable=PATH] [--codec=prores]
//
// brief -> AI director (validated SceneSpec) -> Remotion render -> MP4/ProRes.
// Self-contained + concurrency-safe (unique temp dir per invocation). No live-deploy
// coupling: the Python side spawns this like it spawns gfx_engine.py, then reads the file.

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, mkdtempSync, rmSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';

// Remotion würde sich sonst zur Laufzeit Chrome Headless Shell von remotion.media
// ziehen — auf einem Server mit Egress-Allowlist (prod, Sandbox) gibt das 403 und
// der Render stirbt. Wir zeigen deshalb auf ein LOKAL installiertes Chromium
// (Docker: apt chromium). Reihenfolge: expliziter Flag > Env > bekannte Pfade.
function findBrowser(args) {
  const flag = args.find((a) => a.startsWith('--browser-executable='));
  if (flag) return null; // schon gesetzt, nichts tun
  const env = process.env.DVE_CHROMIUM || process.env.REMOTION_BROWSER_EXECUTABLE;
  const candidates = [env, '/usr/bin/chromium', '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable'].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
  return null; // nichts gefunden -> Remotion versucht seinen Default (Download)
}

const [, , brief, outArg, ...rest] = process.argv;
if (!brief) {
  process.stderr.write('usage: render-brief.mjs "<brief>" <out.mp4> [--browser-executable=..] [--codec=prores]\n');
  process.exit(2);
}
const out = outArg && !outArg.startsWith('--') ? outArg : 'out/video.mp4';
const passthrough = (outArg && outArg.startsWith('--') ? [outArg] : []).concat(rest);
mkdirSync(dirname(out), { recursive: true });

const work = mkdtempSync(join(tmpdir(), 'dve-motion-'));
try {
  const esbuild = 'node_modules/.bin/esbuild';
  const directorBundle = join(work, 'director.mjs');
  const specPath = join(work, 'spec.json');

  // 1) Bundle the director (TS -> ESM) and produce a validated SceneSpec from the brief.
  execFileSync(esbuild, [
    'src/director/run.ts',
    '--bundle',
    '--platform=node',
    '--format=esm',
    `--outfile=${directorBundle}`,
    '--log-level=error',
  ]);
  const specJson = execFileSync('node', [directorBundle, brief], { maxBuffer: 8 << 20 }).toString();
  writeFileSync(specPath, specJson);

  // 2) Render the spec. Remotion manages its own headless browser in production; in the
  //    sandbox pass --browser-executable=... through the trailing args.
  const codecArg = passthrough.find((a) => a.startsWith('--codec='));
  const codec = codecArg ? codecArg.split('=')[1] : 'h264';
  const browser = findBrowser(passthrough);
  execFileSync(
    'npx',
    [
      'remotion',
      'render',
      'src/index.ts',
      'MotionVideo',
      out,
      `--props=${specPath}`,
      `--codec=${codec}`,
      ...(browser ? [`--browser-executable=${browser}`] : []),
      ...passthrough.filter((a) => !a.startsWith('--codec=')),
    ],
    { stdio: 'inherit' },
  );
  process.stderr.write(`\nOK: ${out}\n`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
