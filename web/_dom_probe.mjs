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
  // v230b3: ein echtes Element kann Attribute wieder loswerden. Ohne das
  // fiel prShotWeg() mit "removeAttribute is not a function" - der Test
  // waere am Werkzeug gescheitert, nicht am Code.
  removeAttribute(n) { if (n === 'src') this.src = ''; },
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
  // v230b3: pollRender holt jetzt zusaetzlich das Live-Bild. Ohne diese
  // beiden Stummel wirft der Aufruf hier einen ReferenceError - der landet
  // in demselben catch wie ein Netzfehler und zaehlt als Ausfall. Genau so
  // ist der v230e-Test gefallen, obwohl an ihm nichts kaputt war.
  globalThis.prShotLaden = async () => { globalThis._shot = (globalThis._shot || 0) + 1; };
  globalThis.prShotWeg = () => { globalThis._shotWeg = true; };
  globalThis.setPhase = (t) => { $('#progressPhase').textContent = t; };
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

// ---- v230ae: der Ebenen-Render zeigt seinen Fortschritt ----
// Ismets Befund: "ich klicke darauf und da steht rendering, aber es kommt
// nichts". Der Knopf war ein Standbild - er sagte weder, wie weit der Job
// ist, noch wurde er von selbst zum Download. Geprueft wird das VERHALTEN:
// Warteschlange -> Prozente -> fertig, und im Hintergrund keine Anfrage.
{
  globalThis.setTimeout = ECHTER_TIMEOUT;
  const warte = (ms) => new Promise(r => ECHTER_TIMEOUT(r, ms));
  let versteckt = false, gefragt = 0, neuGezeichnet = 0;
  const horcher = [];
  globalThis.document = {
    get hidden() { return versteckt; },
    addEventListener: (n, f) => horcher.push(f),
    removeEventListener: () => {},
    body: { contains: (b) => !b._weg },
  };
  const umschalten = (v) => { versteckt = v; horcher.slice().forEach(f => f()); };
  globalThis.whenVisible = eval('(' + schneide('whenVisible') + ')');
  globalThis.toast = () => {};
  globalThis.refreshBalanceInHeader = () => {};
  globalThis.renderLibrary = () => { neuGezeichnet++; };
  globalThis.ALPHA_WATCH = new Set();     // Modul-Zustand aus index.html
  const alphaWatch = eval('(' + schneide('alphaWatch') + ')');
  globalThis.alphaWatch = alphaWatch;

  const antworten = [
    { status: 'wartet', progress: 0, queue_pos: 2, phase: 'Queued …' },
    { status: 'laeuft', progress: 0.42, phase: 'Compositing …' },
    { status: 'fertig', progress: 1, alpha: true, phase: 'Editor layer ready' },
  ];
  const gesehen = [];
  // Gezaehlt wird NUR die eigene Job-Nummer: aus frueheren Abschnitten
  // laufen noch Poll-Ketten, die dieselbe fetch-Attrappe benutzen - deren
  // Anfragen wuerden sonst die Antwortfolge weiterschalten und der Test
  // misst etwas anderes, als er glaubt (v230ac-Lehre).
  let schritt = 0;
  globalThis.fetch = async (url = '') => {
    if (!String(url).includes('/j1')) {
      if (String(url).includes('/j2')) gefragt++;
      return { json: async () => ({ status: 'laeuft', progress: 0.5, phase: 'x' }) };
    }
    schritt++;
    return { json: async () => antworten[Math.min(schritt - 1, antworten.length - 1)] };
  };
  const knopf = { textContent: 'Layer …', title: '', dataset: {} };
  // Gewartet wird auf den ZUSTAND, nicht auf eine Uhrzeit - sonst haengt der
  // Test an der Taktrate und flattert (v230ac-Lehre).
  const bis = async (pruefen, ms = 8000) => {
    const t0 = Date.now();
    while (!pruefen() && Date.now() - t0 < ms) await warte(50);
    return pruefen();
  };
  const lauf = alphaWatch('j1', knopf);
  await bis(() => /queued/i.test(knopf.textContent));
  gesehen.push(knopf.textContent);                      // Warteschlange
  await bis(() => knopf.textContent.includes('%'));
  gesehen.push(knopf.textContent);                      // Prozente
  await lauf;
  pruef('v230ae: die Warteschlange steht am Knopf',
        /queued/i.test(gesehen[0]) && gesehen[0].includes('2'), gesehen[0]);
  pruef('v230ae: der Fortschritt steht am Knopf',
        gesehen[1].includes('42'), gesehen[1]);
  pruef('v230ae: am Ende wird die Bibliothek neu gezeichnet (Knopf -> Download)',
        neuGezeichnet === 1, neuGezeichnet + 'x');

  // v230e-Lehre: im Hintergrund gar nicht erst fragen.
  gefragt = 0; neuGezeichnet = 0;
  const antw2 = { status: 'laeuft', progress: 0.5, phase: 'Compositing …' };
  globalThis.fetch = async () => { gefragt++; return { json: async () => antw2 }; };
  const k2 = { textContent: '', title: '', dataset: {} };
  const lauf2 = alphaWatch('j2', k2);
  await bis(() => gefragt > 0);
  // Ein zweiter Aufruf fuer denselben Job darf nichts anstossen - sonst
  // fragen nach jedem Neuzeichnen der Kachel mehrere Poller parallel.
  const vorZweit = gefragt;
  await alphaWatch('j2', k2);
  pruef('v230ae: ein zweiter Poller fuer denselben Job startet nicht',
        gefragt === vorZweit, gefragt + ' Anfragen');
  const vorher = gefragt;
  umschalten(true);
  await warte(3000);
  pruef('v230ae: im Hintergrund wird nicht gefragt',
        gefragt === vorher, (gefragt - vorher) + ' Anfragen');
  k2._weg = true;                       // Karte neu gezeichnet -> Poller endet
  umschalten(false);
  await lauf2;
  pruef('v230ae: eine neu gezeichnete Kachel beendet ihren Poller',
        !globalThis.ALPHA_WATCH.has('j2'));
}

// ---- v230b3/v230b4: das Live-Bild waehrend des Renders ----
// Ismets Wunsch "den Fortschritt visuell zeigen", danach "das sieht billig
// aus". Die Buehne blendet ueber ZWEI Ebenen um, damit beim Nachladen nichts
// weiss blitzt - und sie MUSS die alte Objekt-URL freigeben, sonst waechst
// der Speicher bei einem langen Render mit jedem Bild. Beides laesst sich
// nur durch AUSFUEHREN pruefen.
{
  const gemacht = [], frei = [];
  globalThis.URL = { createObjectURL: (b) => { const u = 'blob:' + gemacht.length;
                                               gemacht.push(u); return u; },
                     revokeObjectURL: (u) => frei.push(u) };
  const box = $('#prShotBox'), a = $('#prShot'), c = $('#prShot2'), glow = $('#prGlow');
  // Das Bild meldet sich per onload - im Mini-DOM feuert nichts von selbst,
  // also loest das Setzen von .src den Rueckruf aus.
  for (const el of [a, c]) {
    el.naturalWidth = 1080; el.naturalHeight = 1920;
    Object.defineProperty(el, 'src', {
      configurable: true,
      get() { return this._src || ''; },
      set(v) { this._src = v; if (this.onload) ECHTER_TIMEOUT(this.onload, 0); },
    });
  }
  box.querySelector = () => ({ style: { setProperty() {}, removeProperty() {} } });
  globalThis.State = { jid: 'abc123' };
  globalThis.document = { hidden: false };
  const [laden, weg] = eval('(function(){let PRSHOT_URL=null,PRSHOT_LAYER=0;'
    + schneide('prShotLaden') + schneide('prShotWeg')
    + 'return [prShotLaden, prShotWeg];})()');
  // (1) Noch kein Bild da (404): die Buehne bleibt im Wartezustand.
  globalThis.fetch = async () => ({ ok: false, status: 404 });
  await laden();
  pruef('v230b3: ohne Bild bleibt die Buehne im Wartezustand',
        !box.classList.contains('on') && !a.src);
  // (2) Erstes Bild: Buehne an, eine Ebene sichtbar, nichts freigegeben.
  globalThis.fetch = async () => ({ ok: true, status: 200,
                                    blob: async () => ({ size: 1234 }) });
  await laden();
  pruef('v230b4: das erste Bild macht die Buehne auf',
        box.classList.contains('on') && a.src === 'blob:0'
        && a.classList.contains('on') && frei.length === 0,
        `${a.src}, ${frei.length} freigegeben`);
  pruef('v230b4: der Schein hinter dem Bild bekommt dasselbe Motiv',
        glow.src === 'blob:0', glow.src);
  // (3) Zweites Bild: die ANDERE Ebene traegt es, die alte URL ist frei.
  await laden();
  pruef('v230b4: das zweite Bild blendet auf der anderen Ebene ein',
        c.src === 'blob:1' && c.classList.contains('on')
        && !a.classList.contains('on'),
        `a=${a.src}/${a.classList.contains('on')}, c=${c.src}/${c.classList.contains('on')}`);
  pruef('v230b3: beim Nachladen wird die alte Objekt-URL freigegeben',
        frei.length === 1 && frei[0] === 'blob:0',
        `freigegeben ${JSON.stringify(frei)}`);
  // (4) Im Hintergrund gar nicht erst fragen (v230e).
  let gefragt = 0;
  globalThis.fetch = async () => { gefragt++; return { ok: false, status: 404 }; };
  globalThis.document = { hidden: true };
  await laden();
  pruef('v230b3: im Hintergrund wird nicht nachgeladen', gefragt === 0);
  globalThis.document = { hidden: false };
  // (5) Aufraeumen am Ende: Buehne aus, beide Ebenen leer, letzte URL frei.
  weg();
  pruef('v230b3: am Ende wird aufgeraeumt',
        !box.classList.contains('on') && !a.src && !c.src && frei.length === 2,
        `freigegeben ${JSON.stringify(frei)}`);
}

// ---- v230b8: Vollbild in der Bibliothek ----
// Ismets Befund: "kann die Videos nicht auf Vollbild machen, dann laeuft das
// Video nicht". Am Desktop war es nicht nachstellbar - am Handy kennt iOS
// Safari `requestFullscreen` auf einem <video> gar nicht und braucht
// `webkitEnterFullscreen`. Beide Wege werden hier AUSGEFUEHRT.
{
  const vollbild = eval('(' + schneide('vollbild') + ')');
  globalThis.document = { fullscreenElement: null, webkitFullscreenElement: null };
  const bau = (welche) => {
    const v = { paused: false, _gespielt: 0,
                play() { this.paused = false; this._gespielt++; return Promise.resolve(); } };
    if (welche === 'standard') v.requestFullscreen = () => { v._voll = true; return Promise.resolve(); };
    if (welche === 'ios') v.webkitEnterFullscreen = () => { v._voll = true; };
    if (welche === 'alt') v.webkitRequestFullscreen = () => { v._voll = true; };
    return v;
  };
  for (const welche of ['standard', 'ios', 'alt']) {
    const v = bau(welche);
    vollbild(v);
    pruef('v230b8: Vollbild geht ueber den Weg "' + welche + '"', !!v._voll);
  }
  // Haelt der Wechsel die Wiedergabe an, wird sie wieder angeworfen - ein
  // Vollbild mit stehendem Bild ist kein Vollbild.
  const v2 = bau('ios');
  vollbild(v2);
  v2.paused = true;                       // der Wechsel hat pausiert
  await new Promise(r => ECHTER_TIMEOUT(r, 800));
  pruef('v230b8: nach dem Wechsel laeuft das Video weiter',
        !v2.paused && v2._gespielt >= 1, `gespielt ${v2._gespielt}`);
  // Ein zweiter Klick geht wieder RAUS, statt nichts zu tun.
  let raus = 0;
  globalThis.document = { fullscreenElement: {}, exitFullscreen: () => { raus++; } };
  vollbild(bau('standard'));
  pruef('v230b8: der zweite Klick beendet das Vollbild', raus === 1);
}

// ---- v230b0: die Navigation des Panels wird AUSGEFUEHRT, nicht gelesen ----
// Beim Zusammenlegen der siebzehn Punkte auf zwoelf darf keine Ansicht
// verschwinden und kein Reiter ins Leere zeigen. Der Selftest prueft das am
// Quelltext; hier laufen die echten Ausdruecke aus admin.html.
{
  const adm = readFileSync(join(HIER, 'admin.html'), 'utf8');
  const stueck = (von, bis) => {
    const i = adm.indexOf(von);
    if (i < 0) throw new Error('nicht gefunden: ' + von);
    const j = adm.indexOf(bis, i);
    return adm.slice(i, j + bis.length);
  };
  const src = stueck('const NAV=[', '\n];')
    + '\n' + stueck('const NAVITEMS=', 'PARENT[k]=id;}')
    + '\n' + stueck('const TABS=NAVITEMS', 'TITEL[id]=t;')
    + '\nreturn {NAV,NAVITEMS,TABSOF,PARENT,TABS,TITEL};';
  const N = new Function(src)();
  const renderBlock = stueck('const RENDER={', '};');
  const rkeys = new Set([...renderBlock.matchAll(/([a-z0-9_]+):/g)].map(m => m[1]));
  const alle = Object.keys(N.TITEL);
  pruef('v230b0: jeder Reiter der Navigation hat eine Ansichts-Funktion',
        alle.every(k => rkeys.has(k)),
        alle.filter(k => !rkeys.has(k)).join(', ') || alle.length + ' Reiter');
  // Ein Sprung direkt auf einen Reiter muss den ELTERN-Punkt liefern.
  pruef('v230b0: ein Reiter zeigt auf seinen Menuepunkt zurueck',
        N.PARENT['credits'] === 'revenue' && N.PARENT['offsite'] === 'system'
        && N.PARENT['events'] === 'logs' && N.PARENT['start'] === 'start',
        JSON.stringify({credits: N.PARENT['credits'], offsite: N.PARENT['offsite']}));
  // Jeder Menuepunkt braucht eine Ueberschrift, sonst steht die Kopfzeile leer.
  pruef('v230b0: jeder Menuepunkt hat einen Titel',
        N.NAVITEMS.every(([id]) => !!N.TITEL[id]),
        N.NAVITEMS.filter(([id]) => !N.TITEL[id]).map(x => x[0]).join(', ') || 'alle');
}

console.log(fails ? `\n${fails} FEHLER` : '\nalle Nachweise gruen');
process.exit(fails ? 1 : 0);
