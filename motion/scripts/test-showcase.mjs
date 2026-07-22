// test-showcase.mjs — guards the transcript→storyboard generator: two different transcripts
// produce different storyboards (individuality), and EVERY on-screen word is grounded verbatim in
// its own transcript (no hallucination) — except the brand sign-off. Bundles via esbuild.
//   node scripts/test-showcase.mjs

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const work = mkdtempSync(join(tmpdir(), 'dve-showcase-'));
try {
  const entry = join(work, 'entry.mjs'); const out = join(work, 'b.mjs');
  const mod = JSON.stringify(join(process.cwd(), 'src/director/buildShowcase.ts'));
  writeFileSync(entry, `
import { buildShowcase } from ${mod};
let fail = 0;
const mkWords = (phrases) => { const o=[]; let t=0; for(const ph of phrases){ for(const w of ph.split(' ')){ o.push({word:' '+w,start:t,end:t+0.3}); t+=0.32; } t+=0.5; } return o; };
const A = ['This changes how you train','Track every rep, every set','Your progress, in real time','No excuses, just results'];
const B = ['Meet your morning ritual','Single origin, roasted fresh','Ground to order in seconds','Taste the difference'];
const sA = buildShowcase(mkWords(A), { brandName: 'RepLog' });
const sB = buildShowcase(mkWords(B), { brandName: 'Bean&Co' });

// 1) both produce a usable storyboard
if (!sA || sA.length < 3 || !sB || sB.length < 3) { fail++; console.error('FAIL empty storyboard'); }
// 2) individuality: the two storyboards differ (kinds or text)
const sig = (s) => s.map((x) => x.kind + ':' + (x.accentText||x.a||'') ).join('|');
if (sig(sA) === sig(sB)) { fail++; console.error('FAIL identical storyboards'); }
// 3) provenance: every on-screen word is verbatim in the transcript (brand sign-off excepted)
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9\\s]/g,' ').split(/\\s+/).filter(Boolean);
function check(story, phrases, label) {
  const tn = ' ' + norm(phrases.join(' ')).join(' ') + ' ';
  for (const sh of story) {
    if (sh.kind === 'signoff') continue;
    for (const s of [sh.accentText, sh.a, sh.b].filter(Boolean)) {
      for (const w of norm(s)) if (!tn.includes(' '+w+' ')) { fail++; console.error('FAIL ungrounded ['+label+']:', w, 'in', JSON.stringify(s)); }
    }
  }
}
check(sA, A, 'A'); check(sB, B, 'B');
// 4) sign-off carries the brand, verbatim
if (!sA.some((x) => x.kind==='signoff' && x.accentText.includes('RepLog'))) { fail++; console.error('FAIL brand A missing'); }
if (!sB.some((x) => x.kind==='signoff' && x.accentText.includes('Bean&Co'))) { fail++; console.error('FAIL brand B missing'); }
// 5) reality-only: no abstract kinds; only the known real-UI archetypes
const OK = new Set(['ktypo','timer','notes','searchbar','imessage','widgets','pill','timeline','signoff']);
if (![...sA,...sB].every((x) => OK.has(x.kind))) { fail++; console.error('FAIL unknown archetype'); }

console.log('buildShowcase:', sA.length, '+', sB.length, 'shots,', fail, 'fail');
if (fail) process.exit(1);
`);
  execFileSync('node_modules/.bin/esbuild', [entry, '--bundle', '--platform=node', '--format=esm', `--outfile=${out}`, '--log-level=error']);
  execFileSync('node', [out], { stdio: 'inherit' });
} finally { rmSync(work, { recursive: true, force: true }); }
