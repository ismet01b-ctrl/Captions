// test-templates.mjs — guards the template text-parsing logic (the class of bug where a
// multi-word search query got word-split to its first word). Bundles parseTemplateText
// via esbuild and asserts each template handles multi-word / odd input correctly.
//   node scripts/test-templates.mjs   ->  exit 0 on pass, 1 on fail

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const CASES = [
  ['search', 'Ask anything about growth', { title: 'Ask anything about growth', lines: [] }],
  ['search', 'Search', { title: 'Search' }],
  ['appcard', 'My Cool App, Photo editor', { title: 'My Cool App', subtitle: 'Photo editor' }],
  ['appcard', 'Notes', { title: 'Notes', subtitle: 'Productivity' }],
  ['notify', 'DouchkoVE, Your clip is ready to share', { title: 'DouchkoVE', subtitle: 'Your clip is ready to share' }],
  ['chat', 'Alex, Hey there!, New drop is live', { title: 'Alex', lines: ['Hey there!', 'New drop is live'] }],
  ['chat', 'Just one line', { title: 'Messages', lines: ['Just one line'] }],
  ['pills', 'Write, Ship it, Grow fast', { lines: ['Write', 'Ship it', 'Grow fast'] }],
  ['pills', 'Write Create Solve', { lines: ['Write', 'Create', 'Solve'] }],
  ['homescreen', 'My apps', { title: 'My apps' }],
];

const work = mkdtempSync(join(tmpdir(), 'dve-tpltest-'));
try {
  const entry = join(work, 'entry.mjs');
  const out = join(work, 'b.mjs');
  writeFileSync(entry,
    `import { parseTemplateText } from ${JSON.stringify(join(process.cwd(), 'src/director/templates.ts'))};\n`
    + `const C = ${JSON.stringify(CASES)};\n`
    + `let fail = 0;\n`
    + `for (const [id, txt, exp] of C) { const r = parseTemplateText(id, txt);\n`
    + `  for (const k of Object.keys(exp)) { if (JSON.stringify(r[k]) !== JSON.stringify(exp[k])) {\n`
    + `    fail++; console.error('FAIL', id, JSON.stringify(txt), '->', JSON.stringify(r), 'expected', k, JSON.stringify(exp[k])); } } }\n`
    + `console.log('parseTemplateText:', C.length - 0, 'cases,', fail, 'fail'); if (fail) process.exit(1);\n`);
  execFileSync('node_modules/.bin/esbuild', [entry, '--bundle', '--platform=node', '--format=esm', `--outfile=${out}`, '--log-level=error']);
  execFileSync('node', [out], { stdio: 'inherit' });
} finally {
  rmSync(work, { recursive: true, force: true });
}
