// render-auto.mjs — the one-command bridge for AUTO-OVERLAY. The Python server spawns:
//   node scripts/render-auto.mjs <video.mp4> <out.mp4> --transcript=words.json [--accent=#..]
//        [--frames=dir] [--logo=img] [--font=ttf] [--platform=tiktok] [--browser-executable=..]
//
// video -> ffprobe (w/h/fps/duration) + sample frames -> autoDirect (AI/heuristic) -> plan
// -> Remotion render of MotionOverlay (video composited with the AI-directed beats). The video
// is copied under public/ so staticFile/OffthreadVideo can read it; cleaned up after.

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, mkdtempSync, rmSync, existsSync, copyFileSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, basename } from 'node:path';
import { tmpdir } from 'node:os';

function findBrowser(args) {
  if (args.find((a) => a.startsWith('--browser-executable='))) return null;
  const env = process.env.DVE_CHROMIUM || process.env.REMOTION_BROWSER_EXECUTABLE;
  for (const c of [env, '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'].filter(Boolean)) if (existsSync(c)) return c;
  return null;
}
const arg = (name, rest) => { const a = rest.find((x) => x.startsWith(`--${name}=`)); return a ? a.split('=').slice(1).join('=') : null; };

const [, , video, outArg, ...rest] = process.argv;
if (!video || !existsSync(video)) { process.stderr.write('usage: render-auto.mjs <video> <out> --transcript=..\n'); process.exit(2); }
const out = outArg && !outArg.startsWith('--') ? outArg : 'out/overlay.mp4';
mkdirSync(dirname(out), { recursive: true });

// ffprobe: dimensions, fps, duration
const probe = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries',
  'stream=width,height,r_frame_rate:format=duration', '-of', 'default=noprint_wrappers=1', video]).toString();
const num = (re) => { const m = re.exec(probe); return m ? m[1] : null; };
const w = parseInt(num(/width=(\d+)/), 10) || 1080;
const h = parseInt(num(/height=(\d+)/), 10) || 1920;
const frr = num(/r_frame_rate=(\d+\/\d+)/) || '30/1'; const [fn, fd] = frr.split('/').map(Number); let fps = Math.round((fn / (fd || 1)) || 30);
if (!fps || fps > 60) fps = 30;
const duration = Math.max(0.5, parseFloat(num(/duration=([\d.]+)/)) || 6);

const work = mkdtempSync(join(tmpdir(), 'dve-auto-'));
// copy the video into public/ so OffthreadVideo(staticFile) can read it
const pubName = `auto-${basename(work)}.mp4`;
const pubPath = join('public', pubName);
mkdirSync('public', { recursive: true });
copyFileSync(video, pubPath);
try {
  // transcript words
  const trPath = arg('transcript', rest);
  let words = [];
  if (trPath && existsSync(trPath)) { try { const j = JSON.parse(readFileSync(trPath, 'utf8')); words = Array.isArray(j) ? j : (j.words || []); } catch { words = []; } }
  // sample frames -> data URIs (for GPT-vision; harmless if unused)
  let frames = [];
  const framesDir = arg('frames', rest);
  if (framesDir && existsSync(framesDir)) {
    for (const f of readdirSync(framesDir).filter((x) => /\.(jpe?g|png)$/i.test(x)).slice(0, 6)) {
      const mime = /\.png$/i.test(f) ? 'image/png' : 'image/jpeg';
      frames.push(`data:${mime};base64,` + readFileSync(join(framesDir, f)).toString('base64'));
    }
  }
  const dataUri = (p) => { if (!p || !existsSync(p)) return null; const ext = (p.split('.').pop() || '').toLowerCase(); const m = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', ttf: 'font/ttf', otf: 'font/otf', woff2: 'font/woff2' }[ext]; return m ? `data:${m};base64,` + readFileSync(p).toString('base64') : null; };
  const logo = dataUri(arg('logo', rest));
  const fontUri = dataUri(arg('font', rest));

  const input = {
    words, frames, accent: arg('accent', rest) || '#e0483d',
    video: { src: pubName, w, h, fps, duration },
    ...(logo ? { logo } : {}), ...(fontUri ? { font: { family: 'DVEUserFont', url: fontUri } } : {}),
    ...(arg('platform', rest) ? { platform: arg('platform', rest) } : {}),
  };
  const inputPath = join(work, 'input.json'); writeFileSync(inputPath, JSON.stringify(input));

  // 1) bundle + run the director → plan
  const esbuild = 'node_modules/.bin/esbuild';
  const dirBundle = join(work, 'auto.mjs');
  execFileSync(esbuild, ['src/director/run-auto.ts', '--bundle', '--platform=node', '--format=esm', `--outfile=${dirBundle}`, '--log-level=error']);
  const planJson = execFileSync('node', [dirBundle, `--input=${inputPath}`], { maxBuffer: 16 << 20 }).toString();
  const planPath = join(work, 'plan.json'); writeFileSync(planPath, planJson);

  // 2) render MotionOverlay
  const browser = findBrowser(rest);
  const codecArg = rest.find((a) => a.startsWith('--codec=')); const codec = codecArg ? codecArg.split('=')[1] : 'h264';
  execFileSync('npx', ['remotion', 'render', 'src/index.ts', 'MotionOverlay', out, `--props=${planPath}`, `--codec=${codec}`,
    ...(browser ? [`--browser-executable=${browser}`] : []),
    ...rest.filter((a) => a.startsWith('--concurrency=') || a === '--log=verbose'),
  ], { stdio: 'inherit' });
  process.stderr.write(`\nOK: ${out}\n`);
} finally {
  rmSync(work, { recursive: true, force: true });
  rmSync(pubPath, { force: true });
}
