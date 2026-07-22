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

// 7) TRANSCRIPT PROVENANCE: on-screen text must be spoken (or the brand name); else it degrades
//    to a text-free graphic accent. No invented words ever survive.
const transcript = 'Today we shipped the new dashboard and revenue jumped 42 percent';
const rawProv = [
  { t: 0, dur: 2, kind: 'headline', text: 'Today we shipped', anchor: 'center', enter: 'rise', emphasis: 0.9 }, // grounded -> keep
  { t: 3, dur: 2, kind: 'headline', text: 'Buy now for cheap', anchor: 'center', enter: 'rise', emphasis: 0.9 }, // INVENTED -> degrade
  { t: 5, dur: 2, kind: 'keyword', text: 'dashboard', anchor: 'upper', enter: 'pop', emphasis: 0.7 },            // grounded token -> keep
  { t: 7, dur: 2, kind: 'keyword', text: 'discount', anchor: 'center', enter: 'pop', emphasis: 0.7 },            // INVENTED token -> degrade
  { t: 9, dur: 2, kind: 'stat', value: 42, label: 'revenue', anchor: 'upper', emphasis: 0.8 },                   // spoken number -> keep
  { t: 11, dur: 2, kind: 'stat', value: 999, label: 'sales', anchor: 'center', emphasis: 0.8 },                  // UNSPOKEN number -> degrade
  { t: 13, dur: 2, kind: 'chips', items: ['dashboard', 'revenue', 'unicorn'], anchor: 'lower', emphasis: 0.6 },  // filter to spoken tokens
  { t: 15, dur: 2, kind: 'brand', text: 'Whatever The Model Wrote', anchor: 'center', enter: 'rise', emphasis: 0.8 }, // force brand name
];
const prov = guardPlan(rawProv, { videoDur: 20, onsets: [], transcript, brandName: 'Acme', minGap: 0.2 });
const byTime = (t) => prov.find((b) => Math.abs(b.t - t) < 0.6);
const GRAPHIC = new Set(['burst', 'sweep', 'pulse', 'brackets']);
// grounded headline keeps its text
if (!prov.some((b) => b.kind === 'headline' && b.text === 'Today we shipped')) { fail++; console.error('FAIL grounded headline lost'); }
// invented headline/keyword/stat became text-free graphics (no invented words anywhere)
if (prov.some((b) => (b.text && /Buy now|discount|cheap/i.test(b.text)))) { fail++; console.error('FAIL invented text survived'); }
if (prov.some((b) => b.kind === 'stat' && b.value === 999)) { fail++; console.error('FAIL unspoken number survived'); }
// spoken stat survives
if (!prov.some((b) => b.kind === 'stat' && b.value === 42)) { fail++; console.error('FAIL spoken stat lost'); }
// chips filtered to only spoken tokens (unicorn gone)
const chip = prov.find((b) => b.kind === 'chips');
if (chip && chip.items.includes('unicorn')) { fail++; console.error('FAIL unspoken chip survived'); }
// brand forced to the trusted name, never model text
const brand = prov.find((b) => b.kind === 'brand');
if (!brand || brand.text !== 'Acme') { fail++; console.error('FAIL brand not forced to trusted name'); }
// every surviving text token must exist in the transcript (the whole point)
const tnorm = transcript.toLowerCase();
for (const b of prov) {
  for (const s of [b.text, b.label, ...(b.items || [])].filter(Boolean)) {
    if (b.kind === 'brand') continue;
    const words = String(s).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
    if (!words.every((w) => tnorm.includes(w))) { fail++; console.error('FAIL ungrounded word on screen:', s); }
  }
}

console.log('autoGuards:', beats.length, 'beats kept,', prov.length, 'prov beats,', fail, 'fail');
if (fail) process.exit(1);
`);
  execFileSync('node_modules/.bin/esbuild', [entry, '--bundle', '--platform=node', '--format=esm', `--outfile=${out}`, '--log-level=error']);
  execFileSync('node', [out], { stdio: 'inherit' });
} finally { rmSync(work, { recursive: true, force: true }); }
