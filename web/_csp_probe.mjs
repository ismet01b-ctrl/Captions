// v230ah WIRKSAMKEITS-NACHWEIS FUER DIE CSP.
// Eine Quelltext-Suche beweist NICHT, dass die Seiten unter der scharfen
// Regel noch laufen - genau das ist der v218/v219-Fehler. Diese Sonde startet
// gegen einen laufenden Server, laedt Landing, App und Panel in einem echten
// Chromium und zaehlt `securitypolicyviolation`-Ereignisse; dazu klickt sie
// zwei Bedienelemente, die frueher ein onclick= trugen.
// Aufruf (Server muss laufen, DVE_ADMIN=testkey_csp):
//   node web/_csp_probe.mjs
// Nicht Teil des Selftests: der braucht keinen Serverstart. Wer an CSP,
// Handlern oder den Seiten etwas aendert, laesst sie EINMAL von Hand laufen.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const B = 'http://127.0.0.1:8952';
const br = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox'] });
const ctx = await br.newContext();

async function seite(pfad) {
  const p = await ctx.newPage();
  const verstoss = [], fehler = [];
  await p.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation',
      e => window.__csp.push(e.violatedDirective + ' :: ' + (e.blockedURI || '') + ' :: ' + (e.sourceFile || '')));
  });
  p.on('console', m => { if (m.type() === 'error') fehler.push(m.text().slice(0, 160)); });
  p.on('pageerror', e => fehler.push('JS: ' + String(e).slice(0, 160)));
  await p.goto(B + pfad, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1500);
  verstoss.push(...await p.evaluate(() => window.__csp));
  return { p, verstoss, fehler };
}

// ---------- 1) Landing ----------
{
  const { p, verstoss, fehler } = await seite('/');
  const jsLief = await p.evaluate(() => !!document.getElementById('demoWrap')
    && getComputedStyle(document.getElementById('demoWrap')).getPropertyValue('--split') !== '');
  console.log('LANDING  Verstoesse:', verstoss.length, '| JS lief:', jsLief,
    '| Fehler:', fehler.filter(f => !/favicon|net::ERR/.test(f)).slice(0, 3));
  await p.close();
}

// ---------- 2) Kunden-App ----------
{
  const { p, verstoss, fehler } = await seite('/app');
  const mail = 'csp' + Date.now() + '@test.de';
  const reg = await p.evaluate(async (m) => {
    const fd = new FormData(); fd.append('email', m); fd.append('password', 'testpass1234'); fd.append('name', 'CSP Tester');
    const r = await fetch('/api/register', { method: 'POST', body: fd });
    return r.status;
  }, mail);
  await p.evaluate(() => { try { localStorage.removeItem('dve_chosen'); } catch (e) {} });
  await p.reload({ waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1200);
  // Werkzeugwahl: die beiden Kacheln trugen frueher onclick="pickTool(...)"
  const kachel = p.locator('[data-act="pickTool"][data-arg="create"]');
  const sichtbar = await kachel.count() && await kachel.first().isVisible();
  let gewechselt = null;
  if (!sichtbar) {   // Auswahl erscheint nur beim ersten Besuch
    await p.evaluate(() => document.getElementById('toolChooser')?.classList.add('show'));
    await p.waitForTimeout(300);
  }
  if (await kachel.first().isVisible()) {
    await kachel.first().click();
    await p.waitForTimeout(600);
    gewechselt = await p.evaluate(() => ({
      chooserZu: !document.getElementById('toolChooser')?.classList.contains('show'),
      merker: (() => { try { return localStorage.getItem('dve_tool'); } catch (e) { return null; } })(),
    }));
  }
  const v2 = await p.evaluate(() => window.__csp);
  console.log('APP      Register:', reg, '| Kachel sichtbar:', !!sichtbar,
    '| Klick wirkte:', JSON.stringify(gewechselt), '| Verstoesse:', v2.length,
    '| Fehler:', fehler.filter(f => !/favicon|net::ERR/.test(f)).slice(0, 3));
  await p.close();
}

// ---------- 3) Admin-Panel ----------
{
  const { p, verstoss, fehler } = await seite('/admin');
  await p.fill('#keyIn', 'testkey_csp');
  await p.press('#keyIn', 'Enter');            // data-enter statt onkeydown
  await p.waitForTimeout(2000);
  const drin = await p.evaluate(() => !!document.getElementById('app')
    && getComputedStyle(document.getElementById('app')).display !== 'none');
  // Ansicht wechseln (frueher onclick="go('jobs')")
  const nav = p.locator('[data-act="go"][data-arg="jobs"]');
  let ansicht = null;
  if (await nav.count()) {
    await nav.first().click();
    await p.waitForTimeout(1200);
    ansicht = await p.evaluate(() => document.querySelector('[data-t="jobs"]')?.classList.contains('on')
      || location.hash || 'unbekannt');
  }
  const v3 = await p.evaluate(() => window.__csp);
  console.log('ADMIN    Enter-Taste entsperrt:', drin, '| Ansicht nach Klick:', ansicht,
    '| Verstoesse:', v3.length, '| Fehler:',
    fehler.filter(f => !/favicon|net::ERR|401|403/.test(f)).slice(0, 3));
  if (v3.length) console.log('   ', v3.slice(0, 5));
  await p.close();
}
await br.close();
