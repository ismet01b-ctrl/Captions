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
// Die echte Uhr sichern, BEVOR ein Test sie durch eine Warteschlange ersetzt.
const ECHTER_TIMEOUT = globalThis.setTimeout;
const html = readFileSync(join(HIER, 'index.html'), 'utf8');

function schneide(name) {
  let i = html.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('nicht gefunden: ' + name);
  // v230e: `async` gehoert zur Funktion. Ohne dieses Stueck schneidet die
  // Sonde eine async-Funktion als normale heraus, und ihr erstes `await`
  // ist dann ein Syntaxfehler - der Test faellt aus dem falschen Grund.
  if (html.slice(Math.max(0, i - 6), i) === 'async ') i -= 6;
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

// 5) v229 Aufloesungs-Stufen ausgrauen, die die Quelle nicht hergibt.
// Die Engine skaliert NIE hoch (H = min(Wunsch, Quelle)); bis hier standen
// alle drei Stufen waehlbar da - eine Auswahl, die nichts auswaehlt, und beim
// 4K-Haken der doppelte Preis fuer dieselbe Datei. Geprueft wird durch
// AUSFUEHREN der echten Funktion, nicht per Quelltext-Suche.
const setDeep = eval('(' + schneide('setDeep') + ')');
const updateResChoices = eval('(' + schneide('updateResChoices') + ')');
const mkBtn = (v, an) => ({
  dataset: {val: String(v)}, disabled: false, title: '', textContent: v + 'p',
  _cls: new Set(an ? ['on'] : []),
  classList: {add: c => mkBtnCls(c), remove: c => mkBtnCls(c, true),
              contains: c => false},
});
function segBau(anWert) {
  const btns = [720, 1080, 2160].map(v => {
    const b = {dataset: {val: String(v)}, disabled: false, title: '',
               textContent: v + 'p', _cls: new Set(v === anWert ? ['on'] : [])};
    b.classList = {add: c => b._cls.add(c), remove: c => b._cls.delete(c),
                   contains: c => b._cls.has(c)};
    return b;
  });
  return {
    querySelectorAll: () => btns,
    querySelector: sel => (sel === 'button.on'
      ? btns.find(b => b._cls.has('on')) || null : btns[0]),
    _btns: btns,
  };
}
let SEG = null;
const HINT = {textContent: '', style: {}};
globalThis.document = {
  querySelector: () => SEG,
  getElementById: id => (id === 'resNote' ? HINT : null),
};
globalThis.State = {};
globalThis.setDeep = setDeep;
globalThis.updateRenderCost = () => {};
function lauf(kurz, anWert) {
  SEG = segBau(anWert);
  State.srcShort = kurz;
  State.cfg = {output: {height: anWert}};
  updateResChoices();
  return SEG._btns.map(b => ({v: +b.dataset.val, aus: b.disabled,
                             an: b._cls.has('on')}));
}
const r720 = lauf(720, 1080);
pruef('720p-Quelle: 1080p und 4K sind ausgegraut',
      !r720[0].aus && r720[1].aus && r720[2].aus, JSON.stringify(r720));
pruef('720p-Quelle: die Auswahl wandert auf die hoechste erreichbare Stufe',
      r720[0].an && State.cfg.output.height === 720,
      'gewaehlt ' + State.cfg.output.height);
const r1080 = lauf(1080, 1080);
pruef('1080p-Quelle: nur 4K ist ausgegraut',
      !r1080[0].aus && !r1080[1].aus && r1080[2].aus, JSON.stringify(r1080));
const r4k = lauf(2160, 1080);
pruef('4K-Quelle: nichts ist ausgegraut',
      r4k.every(x => !x.aus), JSON.stringify(r4k));
const runk = lauf(0, 1080);
pruef('unbekannte Quelle: nichts wird verboten',
      runk.every(x => !x.aus), JSON.stringify(runk));
pruef('der Hinweis nennt die Aufloesung der Quelle',
      lauf(720, 1080) && HINT.textContent.includes('720p'), HINT.textContent);

// ---- v230e: ein weggeklickter Tab ist kein Verbindungsabbruch ----
// Ismets Befund: "Jedesmal wenn ich die Seite im Tab minimiere, ist die
// Seite abgestuerzt." Im Hintergrund bricht das Handy die laufenden
// Anfragen ab; die Zaehlung unterschied nicht, WARUM eine Anfrage
// scheiterte, und zeigte nach 10 Fehlversuchen die grosse Karte
// "Connection lost" - waehrend der Render unveraendert weiterlief.
// Gemessen im echten Browser: 14 abgebrochene Anfragen in 20 s
// Hintergrund, Karte nach ~12 s. Hier wird die ECHTE pollRender
// ausgefuehrt, nicht der Quelltext durchsucht.
{
  let versteckt = false;
  let gefragt = 0;
  const hoerer = [];
  globalThis.document = {
    get hidden() { return versteckt; },
    querySelector: (s) => $(s),
    getElementById: () => null,
    addEventListener: (t, h) => { if (t === 'visibilitychange') hoerer.push(h); },
    removeEventListener: (t, h) => {
      const i = hoerer.indexOf(h); if (i >= 0) hoerer.splice(i, 1);
    },
  };
  const umschalten = (v) => { versteckt = v; hoerer.slice().forEach(h => h()); };
  globalThis.State = { jid: 'x', pollErrs: 0 };
  globalThis.fetch = async () => {
    gefragt++;
    // Der Hintergrund bricht ab - genau wie auf dem Handy.
    if (versteckt) throw new TypeError('Failed to fetch');
    return { json: async () => ({ status: 'laeuft', progress: 0.4,
                                  phase: 'Rendering …', eta_sec: 60 }) };
  };
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  globalThis.progAnim = () => {};
  globalThis.fmtDur = () => '0:00';
  globalThis.renderSuccess = () => {};
  globalThis.refreshBalanceInHeader = () => {};
  globalThis.toast = () => {};
  globalThis.showError = (msg, d, o) => { globalThis._karte = msg; };
  globalThis.localStorage = localStorage;
  globalThis.whenVisible = eval('(' + schneide('whenVisible') + ')');
  const pollRender = eval('(' + schneide('pollRender') + ')');
  globalThis.pollRender = pollRender;
  // Ein frueherer Abschnitt hat globalThis.setTimeout durch eine Warteschlange
  // ersetzt (fuer die Fehler-Tests). Hier brauchen wir die ECHTE Uhr, sonst
  // laeuft der 1.2-s-Takt von pollRender nie an und nichts wird gemessen.
  globalThis.setTimeout = ECHTER_TIMEOUT;
  const warte = (ms) => new Promise(r => ECHTER_TIMEOUT(r, ms));

  globalThis._karte = null;
  await pollRender();                      // sichtbar: eine Runde
  const gefragt_sichtbar = gefragt;
  umschalten(true);                        // Tab weggeklickt
  // Die naechste geplante Runde faellt in den Hintergrund (1.2 s Takt).
  // NICHT awaiten: die Runde bleibt absichtlich stehen, bis der Tab
  // zurueckkommt - genau das ist der Fix.
  await warte(2000);
  const gefragt_versteckt = gefragt - gefragt_sichtbar;
  pruef('v230e: im Hintergrund wird gar nicht erst gefragt',
        gefragt_versteckt === 0, gefragt_versteckt + ' Anfragen');
  pruef('v230e: keine Fehlerkarte, waehrend der Tab weg ist',
        globalThis._karte === null, String(globalThis._karte));

  // Zweiter Fall: die Anfrage lief noch, WAEHREND der Tab weggeklickt wurde.
  // Sie wird abgebrochen - das darf den Zaehler nicht erhoehen.
  // Damit die Messung sauber ist, werden die noch laufenden Poll-Ketten aus
  // Teil 1 vorher geparkt: `versteckt` direkt setzen, OHNE das Ereignis -
  // dann bleiben sie in whenVisible stehen und koennen nichts mehr
  // zuruecksetzen, waehrend der naechste Aufruf sie fuer sichtbar haelt.
  await warte(1500);
  versteckt = false;
  State.pollErrs = 9;
  globalThis.fetch = async () => {
    versteckt = true;                      // Tab geht waehrend der Anfrage weg
    throw new TypeError('Failed to fetch');
  };
  await pollRender();
  pruef('v230e: ein Abbruch im Hintergrund erhoeht den Fehlerzaehler nicht',
        State.pollErrs === 9, 'Zaehler ' + State.pollErrs);
  pruef('v230e: und er zeigt keine Fehlerkarte',
        globalThis._karte === null, String(globalThis._karte));
  // Zurueck im Vordergrund: die naechste Runde setzt den Zaehler zurueck.
  versteckt = true;
  const laeuft = pollRender();             // wartet auf die Rueckkehr
  await warte(200);
  umschalten(false);
  globalThis.fetch = async () => ({ json: async () => ({ status: 'laeuft',
    progress: 0.5, phase: 'Rendering …', eta_sec: 30 }) });
  await laeuft;
  pruef('v230e: zurueck im Vordergrund faengt der Zaehler bei null an',
        State.pollErrs === 0, 'Zaehler ' + State.pollErrs);
}

// ---- v230i: Player wirklich freigeben, nicht nur verstecken ----
// Ismets Screenshot: Chrome selbst meldet "Diese Seite kann nicht geoeffnet
// werden", nachdem der Tab im Hintergrund war - das iPhone hat den Inhalt
// weggeraeumt. Jedes angetippte Bibliotheks-Video blieb als eigener
// <video>-Player mit voller Quelle im DOM. Ein verstecktes Element gibt
// nichts frei; die Quelle muss weg und load() laufen.
{
  const videoFreigeben = eval('(' + schneide('videoFreigeben') + ')');
  const gemacht = [];
  const bau = (n) => {
    const kacheln = [];
    for (let k = 0; k < n; k++) {
      const v = {
        tag: 'video', _src: '/api/video/j' + k,
        pause() { gemacht.push('pause'); },
        removeAttribute(a) { if (a === 'src') this._src = null; },
        load() { gemacht.push('load'); },
        remove() { this._weg = true; },
        closest: () => kachel,
      };
      const kachel = {
        _cls: new Set(['lib-thumb', 'playing']), dataset: { thumb: '<img>' },
        innerHTML: '<video>', style: {},
        classList: { remove: c => kachel._cls.delete(c),
                     add: c => kachel._cls.add(c) },
        _v: v,
      };
      v.closest = () => kachel;
      kacheln.push(kachel);
    }
    return {
      querySelectorAll: (sel) => (sel === 'video' ? kacheln.map(k => k._v) : []),
      _k: kacheln,
    };
  };
  const wurzel = bau(6);
  videoFreigeben(wurzel);
  const alle = wurzel._k.map(k => k._v);
  pruef('v230i: jeder Player wird angehalten und entladen',
        gemacht.filter(x => x === 'pause').length === 6
        && gemacht.filter(x => x === 'load').length === 6, gemacht.length + ' Schritte');
  pruef('v230i: die Quelle wird wirklich entfernt',
        alle.every(v => v._src === null));
  pruef('v230i: das Element fliegt aus der Kachel',
        alle.every(v => v._weg === true));
  pruef('v230i: die Kachel wird wieder zum Vorschaubild',
        wurzel._k.every(k => !k._cls.has('playing') && k.innerHTML === '<img>'));
  // Der gerade laufende Player bleibt.
  const w2 = bau(3);
  const behalten = w2._k[1]._v;
  videoFreigeben(w2, behalten);
  pruef('v230i: der gerade laufende Player bleibt stehen',
        behalten._src !== null && behalten._weg !== true);
}

console.log(fails ? `\n${fails} FEHLER` : '\nalle Nachweise gruen');
process.exit(fails ? 1 : 0);
