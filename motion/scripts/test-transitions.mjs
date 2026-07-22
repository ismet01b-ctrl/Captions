// test-transitions.mjs — guards the sequencer transition library: (1) every curve settles
// to identity at its resolved end (so the mid-hold is a clean frame, no residual blur/offset),
// (2) auto-picked boundaries never repeat adjacently and stay deterministic, (3) a per-scene
// override wins. Bundles transitions.ts via esbuild.  node scripts/test-transitions.mjs
//   -> exit 0 on pass, 1 on fail

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const work = mkdtempSync(join(tmpdir(), 'dve-trtest-'));
try {
  const entry = join(work, 'entry.mjs');
  const out = join(work, 'b.mjs');
  const modPath = JSON.stringify(join(process.cwd(), 'src/lib/transitions.ts'));
  writeFileSync(entry, `
import { TRANSITIONS, TRANS_IDS, pickTransitions, isTransId, SFX_KEYS } from ${modPath};
let fail = 0;
const near = (a, b) => Math.abs(a - b) < 1e-6;
const isId = (o) => near(o.x,0) && near(o.y,0) && near(o.scale,1) && near(o.rotateY,0)
  && near(o.alpha,1) && near(o.blur,0) && near(o.blurX,0);

// (1) enter(1) and exit(0) MUST be identity for every transition.
for (const id of TRANS_IDS) {
  const d = TRANSITIONS[id];
  if (!isId(d.enter(1, 1080, 1920))) { fail++; console.error('FAIL enter(1) not identity:', id, JSON.stringify(d.enter(1,1080,1920))); }
  if (!isId(d.exit(0, 1080, 1920)))  { fail++; console.error('FAIL exit(0) not identity:', id, JSON.stringify(d.exit(0,1080,1920))); }
  // alpha must stay within [0,1]-ish and blur non-negative across the window.
  for (let e = 0; e <= 1.0001; e += 0.1) {
    for (const a of [d.enter(e,1080,1920), d.exit(e,1080,1920)]) {
      if (a.blur < -1e-6 || a.blurX < -1e-6) { fail++; console.error('FAIL negative blur:', id, e); }
      if (a.scale <= 0) { fail++; console.error('FAIL non-positive scale:', id, e); }
    }
  }
}

// (2) auto variety: no two adjacent boundaries share a transition; deterministic per seed.
for (const seed of [0, 1, 7, 42, 99999]) {
  const p = pickTransitions(5, seed);
  if (p.length !== 5) { fail++; console.error('FAIL length', seed); }
  for (let i = 1; i < p.length; i++) if (p[i] === p[i-1]) { fail++; console.error('FAIL adjacent repeat', seed, p.join(',')); }
  if (!p.every(isTransId)) { fail++; console.error('FAIL invalid id', seed, p.join(',')); }
  const q = pickTransitions(5, seed);
  if (p.join(',') !== q.join(',')) { fail++; console.error('FAIL not deterministic', seed); }
}

// (3) a valid override wins; an invalid one falls back to the auto pick.
const ov = pickTransitions(3, 3, ['iris', 'zzz', undefined]);
if (ov[0] !== 'iris') { fail++; console.error('FAIL override ignored', ov.join(',')); }
if (!isTransId(ov[1]) || ov[1] === 'zzz') { fail++; console.error('FAIL bad override not sanitised', ov.join(',')); }

if (!SFX_KEYS.length) { fail++; console.error('FAIL no sfx keys'); }
console.log('transitions:', TRANS_IDS.length, 'defs,', SFX_KEYS.length, 'sfx keys,', fail, 'fail');
if (fail) process.exit(1);
`);
  execFileSync('node_modules/.bin/esbuild', [entry, '--bundle', '--platform=node', '--format=esm', `--outfile=${out}`, '--log-level=error']);
  execFileSync('node', [out], { stdio: 'inherit' });
} finally {
  rmSync(work, { recursive: true, force: true });
}
