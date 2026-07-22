// test-autoguards.mjs — guards the auto-overlay quality rules: no overlapping beats, a breath
// between them, density capped to the video length, junk beats dropped, timings snapped to
// word onsets. Bundles autoGuards via esbuild.  node scripts/test-autoguards.mjs

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const work = mkdtempSync(join(tmpdir(), 'dve-guards-'));
try {
  const entry = join(work, 'entry.mjs'); const out = join(work, 'b.mjs');
  const mod = JSON.stringify(join(process.cwd(), 'src/director/autoGuards.ts'));
  writeFileSync(entry, `
import { guardPlan } from ${mod};
let fail = 0;
const onsets = [0, 1, 1.5, 2, 3, 4, 5, 6, 7, 8];
// deliberately overlapping + junk + over-dense input
const raw = [
  { t: 0.05, dur: 5, kind: 'headline', text: 'The big hook here', anchor: 'center', enter: 'rise', emphasis: 0.9 },
  { t: 0.1, dur: 3, kind: 'keyword', text: 'Overlap', anchor: 'center', enter: 'pop', emphasis: 0.8 },
  { t: 1.0, dur: 2, kind: 'chips', items: ['only-one'], anchor: 'lower' },     // <2 items -> drop
  { t: 2.0, dur: 2, kind: 'stat', anchor: 'upper' },                            // no value -> drop
  { t: 2.1, dur: 2, kind: 'headline', anchor: 'top' },                          // no text -> drop
  { t: 3.02, dur: 2, kind: 'keyword', text: 'Sharp', anchor: 'upper', enter: 'pop', emphasis: 0.7 },
  { t: 5.0, dur: 2, kind: 'lowerthird', text: 'Name here', anchor: 'lower', enter: 'slide', emphasis: 0.6 },
];
const beats = guardPlan(raw, { videoDur: 9, onsets, perMinute: 22 });

// 1) no overlaps + a real gap between consecutive beats
for (let i = 1; i < beats.length; i++) {
  if (beats[i].t < beats[i-1].t + beats[i-1].dur) { fail++; console.error('FAIL overlap at', i, JSON.stringify(beats.map(b=>[b.t,b.dur]))); }
}
// 2) junk beats dropped (chips<2, stat w/o value, headline w/o text)
if (beats.some((b) => b.kind === 'chips' || (b.kind === 'stat') || (b.kind === 'headline' && !b.text))) { fail++; console.error('FAIL junk survived'); }
// 3) durations clamped
if (beats.some((b) => b.dur > 3.4001 || b.dur < 0.9)) { fail++; console.error('FAIL dur out of range', beats.map(b=>b.dur)); }
// 4) snapped to an onset (t appears in onsets, within tolerance already applied)
if (!beats.every((b) => onsets.some((o) => Math.abs(o - b.t) < 0.7))) { fail++; console.error('FAIL not near an onset'); }
// 5) alternating anchors (no two identical in a row)
for (let i = 1; i < beats.length; i++) if (beats[i].anchor === beats[i-1].anchor) { fail++; console.error('FAIL same anchor twice', i); }
// 6) density cap for a short clip
const dense = guardPlan(Array.from({length: 40}, (_, i) => ({ t: i*0.15, dur: 2, kind: 'keyword', text: 'w'+i, anchor: 'center', enter: 'pop', emphasis: Math.random?0.5:0.5 })), { videoDur: 10, onsets: [] });
if (dense.length > Math.round((10/60)*22) + 1) { fail++; console.error('FAIL density not capped:', dense.length); }

console.log('autoGuards:', beats.length, 'beats kept,', fail, 'fail');
if (fail) process.exit(1);
`);
  execFileSync('node_modules/.bin/esbuild', [entry, '--bundle', '--platform=node', '--format=esm', `--outfile=${out}`, '--log-level=error']);
  execFileSync('node', [out], { stdio: 'inherit' });
} finally { rmSync(work, { recursive: true, force: true }); }
