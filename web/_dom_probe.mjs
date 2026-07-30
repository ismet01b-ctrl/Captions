// v220 WIRKSAMKEITS-NACHWEIS fuer die SPA-Logik.
// WARUM eine eigene Datei: die Fehlerbehandlung der App ist JavaScript im
// Browser - eine Quelltext-Suche aus dem Python-Selftest beweist NICHTS
// (das ist der v218/v219-Fehler). Diese Sonde schneidet die echten
// Funktionen aus index.html, fuehrt sie gegen ein Mini-DOM AUS und prueft
// das Verhalten. Aufgerufen aus selftest.py, laeuft aber auch allein:
//   node web/_dom_probe.mjs
// v220 WIRKSAMKEITS-NACHWEIS: die echten Funktionen aus web/index.html werden
// AUSGEFUEHRT (Mini-DOM), nicht nur im Quelltext gesucht.
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
const HIER = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(HIER, 'index.html'), 'utf8');

function schneide(name) {
  const i = html.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('nicht gefunden: ' + name);
  let d = 0, j = html.indexOf('{', i);
  for (let k = j; k < html.length; k++) {
    if (html[k] === '{') d++;
    else if (html[k] === '}') { d--; if (!d) return html.slice(i, k + 1); }
  }
  throw new Error('unbalanciert: ' + name);
}

const el = {};
const $ = s => (el[s] = el[s] || {
  _cls: new Set(['hidden']), textContent: '', disabled: false, style: {},
  classList: { add: c => el[s]._cls.add(c), remove: c => el[s]._cls.delete(c),
               contains: c => el[s]._cls.has(c) },
  scrollIntoView() {},
});
const store = {};
const localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
};
const fbInit = () => {};
const State = {};
const toast = () => {};

const showError = eval('(' + schneide('showError') + ')');
const renderSuccess = eval('(' + schneide('renderSuccess') + ')');

let fails = 0;
const pruef = (name, ok, detail) => {
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  (' + detail + ')' : ''));
  if (!ok) fails++;
};

// 1) Echter Render-Fehler: rot, Job wird vergessen, Knopf frei
store['dve_active_job'] = '{"jid":"abc","ts":1}';
showError('Render failed', 'boom');
pruef('echter Fehler: Titel bleibt "Render error"',
      $('#errTitleText').textContent === 'Render error', $('#errTitleText').textContent);
pruef('echter Fehler: Titel ist rot', $('#errTitle').style.color === 'var(--red)');
pruef('echter Fehler: Job wird vergessen', !('dve_active_job' in store));
pruef('echter Fehler: Render-Knopf wieder frei', $('#btnRender').disabled === false);

// 2) Verbindungsabbruch: neutral, Job BLEIBT, Knopf bleibt gesperrt
store['dve_active_job'] = '{"jid":"abc","ts":1}';
showError('Connection lost - your render is still running.', 'egal',
          {weich: true, keepJob: true, titel: 'Connection lost'});
pruef('Funkloch: Titel ist NICHT "Render error"',
      $('#errTitleText').textContent === 'Connection lost', $('#errTitleText').textContent);
pruef('Funkloch: Titel ist nicht rot',
      $('#errTitle').style.color !== 'var(--red)', $('#errTitle').style.color);
pruef('Funkloch: der laufende Job bleibt gespeichert (Neuladen findet ihn)',
      store['dve_active_job'] === '{"jid":"abc","ts":1}');
pruef('Funkloch: Render-Knopf bleibt gesperrt (kein Doppelkauf)',
      $('#btnRender').disabled === true);

// 3) Video fertig -> die Karte muss weg sein
$('#errCard').classList.remove('hidden');
State.jid = 'abc';
// renderSuccess ruft weiter unten Hilfsfunktionen, die hier nicht existieren -
// die geprueffte Zeile (Karte verstecken) ist die ERSTE im Rumpf.
try { renderSuccess(); } catch (e) {}
pruef('fertig: die Connection-lost-Karte ist verschwunden',
      $('#errCard').classList.contains('hidden'));

// 4) v226b Aufklapp-Bereich: KEIN fester Deckel, nichts abgeschnitten.
// Ismets Befund am Handy: "Ich sehe die weiteren Menue Optionen nicht" - der
// offene Bereich war auf 2000 px begrenzt (overflow:hidden), auf dem Handy ist
// er hoeher, der Rest war unerreichbar. Hier wird die ECHTE Funktion aus
// index.html ausgefuehrt und geprueft, dass am Ende KEIN Pixel-Deckel steht.
const accToggle = eval('(' + schneide('accToggle') + ')');
let raf_q = [], to_q = [];
globalThis.requestAnimationFrame = f => raf_q.push(f);
globalThis.setTimeout = (f) => { to_q.push(f); return 0; };
const mkAcc = () => {
  const body = {
    _cls: new Set(), style: {}, scrollHeight: 4200,
    classList: { add: c => body._cls.add(c), remove: c => body._cls.delete(c),
                 contains: c => body._cls.has(c) },
    _lis: [], addEventListener: (_e, f) => body._lis.push(f),
    removeEventListener: (_e, f) => { body._lis = body._lis.filter(x => x !== f); },
  };
  const acc = {
    _cls: new Set(),
    classList: { add: c => acc._cls.add(c), remove: c => acc._cls.delete(c),
                 contains: c => acc._cls.has(c),
                 toggle: c => (acc._cls.has(c) ? acc._cls.delete(c)
                                               : acc._cls.add(c)) },
    querySelector: () => body,
  };
  return { acc, body };
};
const { acc: a4, body: b4 } = mkAcc();
accToggle(a4);                              // aufklappen
pruef('Aufklappen: der Bereich ist offen', a4._cls.has('open'));
raf_q.forEach(f => f()); raf_q = [];
pruef('Aufklappen: die Animation nutzt die GEMESSENE Hoehe, nicht 2000 px',
      b4.style.maxHeight === '4200px', b4.style.maxHeight);
b4._lis.slice().forEach(f => f());          // transitionend
pruef('Aufklappen: danach steht KEIN Deckel mehr (nichts abgeschnitten)',
      b4.style.maxHeight === '' && !b4._cls.has('anim'),
      JSON.stringify({max: b4.style.maxHeight, anim: [...b4._cls]}));
// Auch wenn transitionend NIE kommt (Hintergrund-Tab), muss der Deckel weg.
const { acc: a5, body: b5 } = mkAcc();
accToggle(a5);
raf_q.forEach(f => f()); raf_q = [];
to_q.forEach(f => f()); to_q = [];
pruef('Aufklappen: auch ohne transitionend faellt der Deckel weg',
      b5.style.maxHeight === '', b5.style.maxHeight);
accToggle(a5);                              // zuklappen
raf_q.forEach(f => f()); raf_q = [];
pruef('Zuklappen: der Bereich schliesst wieder',
      !a5._cls.has('open') && b5.style.maxHeight === '0px', b5.style.maxHeight);

console.log(fails ? `\n${fails} FEHLER` : '\nalle Nachweise gruen');
process.exit(fails ? 1 : 0);
