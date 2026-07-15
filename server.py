# -*- coding: utf-8 -*-
"""DouchkoVE Web - kein Download, kein Setup.

Der Nutzer oeffnet einen Link, laedt sein Video hoch, waehlt einen Look und
bekommt das fertige Video zurueck. Auf seinem Rechner wird NICHTS installiert.

Warum das so gebaut ist:
- Der OpenAI-Key liegt AUF DEM SERVER (Umgebungsvariable). Kein Nutzer sieht ihn
  je. In eine ausgelieferte .exe gepackt waere er in zwei Minuten ausgelesen - und
  ein OpenAI-Key hat kein Limit pro Nutzer, das Konto waere offen wie ein Scheunentor.
- Zugang nur mit CODE. Jeder Tester bekommt seinen eigenen. Verbrauch wird
  mitgezaehlt, Limit pro Code, jederzeit sperrbar. Das ist zugleich die Grundlage
  fuer die spaetere Paywall - dann wird aus dem Code ein Abo.
- Rendern laeuft in einer WARTESCHLANGE, ein Job nach dem anderen. Sonst reissen
  sich zwei Videos um denselben Prozessor und beide dauern doppelt so lang.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from queue import Queue

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get('DVE_DATA', os.path.join(HERE, 'data'))
JOBS_DIR = os.path.join(DATA, 'jobs')
CODES_FILE = os.path.join(DATA, 'codes.json')
MAX_MB = int(os.environ.get('DVE_MAX_MB', '300'))
MAX_SECONDS = int(os.environ.get('DVE_MAX_SECONDS', '180'))

os.makedirs(JOBS_DIR, exist_ok=True)

app = FastAPI(title='DouchkoVE')
JOBS = {}
QUEUE = Queue()
LOCK = threading.Lock()

# Die Looks, die der Nutzer waehlen kann. Bewusst wenige: im Browser will niemand
# 40 Regler sehen - das ist der Unterschied zum Profi-Programm.
LOOKS = {
    'tiktok':    {'name': 'TikTok', 'desc': 'Wort für Wort, fett, laut.'},
    'creator':   {'name': 'Creator', 'desc': 'Talking-Head & Business.'},
    'cinematic': {'name': 'Cinematic', 'desc': 'Wenige, große Momente.'},
    'clean':     {'name': 'Clean', 'desc': 'Nur lesbare Untertitel.'},
}


# ---------------------------------------------------------------- Zugangscodes
def load_codes():
    if os.path.exists(CODES_FILE):
        try:
            return json.load(open(CODES_FILE, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_codes(c):
    tmp = CODES_FILE + '.tmp'
    json.dump(c, open(tmp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    os.replace(tmp, CODES_FILE)


def check_code(code):
    """Prueft den Zugangscode. Gibt (ok, meldung) zurueck. Das Limit schuetzt dich
    davor, dass ein einzelner Tester (oder ein weitergegebener Code) dein
    OpenAI-Guthaben leerlaeuft."""
    codes = load_codes()
    c = codes.get((code or '').strip())
    if not c:
        return False, 'Zugangscode ungültig.'
    if not c.get('aktiv', True):
        return False, 'Dieser Zugangscode wurde deaktiviert.'
    if c.get('limit') and c.get('genutzt', 0) >= c['limit']:
        return False, (f"Kontingent aufgebraucht ({c['genutzt']}/{c['limit']} Videos). "
                       'Melde dich bei Ismet.')
    return True, ''


def count_use(code):
    with LOCK:
        codes = load_codes()
        if code in codes:
            codes[code]['genutzt'] = codes[code].get('genutzt', 0) + 1
            codes[code]['zuletzt'] = time.strftime('%Y-%m-%d %H:%M')
            save_codes(codes)


# ---------------------------------------------------------------- Render-Worker
def job_dir(jid):
    return os.path.join(JOBS_DIR, jid)


def set_state(jid, **kw):
    j = JOBS.setdefault(jid, {})
    j.update(kw)
    try:
        json.dump(j, open(os.path.join(job_dir(jid), 'state.json'), 'w',
                          encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def build_config(look):
    """Baut die config.yaml fuer diesen Job aus dem gewaehlten Look."""
    cfg = yaml.safe_load(open(os.path.join(ROOT, 'config.yaml'), encoding='utf-8'))
    # Blender-Wasser ist serverseitig aus: 500 MB Installation und sehr langsam.
    cfg['effects']['blender_water'] = False
    presets = {
        'tiktok':    dict(density='wortweise', text_style='3d kinetisch',
                          hook_seconds=8, hook_strength=0.85),
        'creator':   dict(density='akzente', text_style='3d',
                          hook_seconds=15, hook_strength=0.5),
        'cinematic': dict(density='sparsam', text_style='klassisch',
                          hook_seconds=30, hook_strength=0.3),
        'clean':     dict(density='sparsam', text_style='klassisch',
                          hook_seconds=0, hook_strength=0.0),
    }
    cfg['effects'].update(presets.get(look, presets['creator']))
    if look == 'clean':
        cfg['effects']['keyword_rotation'] = ['outline']
    return cfg


def worker():
    while True:
        jid = QUEUE.get()
        try:
            run_job(jid)
        except Exception as e:
            set_state(jid, status='fehler',
                      msg=f'Unerwarteter Fehler: {type(e).__name__}')
        finally:
            QUEUE.task_done()


def run_job(jid):
    j = JOBS[jid]
    d = job_dir(jid)
    src = j['input']
    out = os.path.join(d, 'fertig.mp4')
    cfg = build_config(j['look'])
    cfg_path = os.path.join(d, 'config.yaml')
    yaml.safe_dump(cfg, open(cfg_path, 'w', encoding='utf-8'))

    set_state(jid, status='laeuft', phase='Transkription …', progress=0.05)
    cmd = [sys.executable, os.path.join(ROOT, 'render.py'), src,
           '--config', cfg_path, '--out', out]
    # Testbetrieb ohne OpenAI-Key: fertiges Transkript verwenden.
    if os.environ.get('DVE_TEST_TRANSCRIPT'):
        cmd += ['--transcript', os.environ['DVE_TEST_TRANSCRIPT']]
    env = dict(os.environ)          # OPENAI_API_KEY kommt vom Server, nicht vom Nutzer
    p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    log = []
    for line in p.stdout:
        log.append(line.rstrip())
        ln = line.strip()
        if 'Gesichts-Tracking' in ln:
            set_state(jid, phase='Szenen-Analyse …', progress=0.20)
        elif ln.startswith('Keywords') or 'KI-Regie' in ln:
            set_state(jid, phase='Die KI wählt die Momente …', progress=0.35)
        elif 'Frame' in ln and '/' in ln:
            try:
                cur, tot = ln.split('Frame')[1].split('|')[0].strip().split('/')
                frac = 0.45 + 0.5 * (int(cur) / max(int(tot), 1))
                set_state(jid, phase='Video wird gebaut …',
                          progress=round(min(frac, 0.95), 3))
            except Exception:
                pass
        elif ln.startswith('Fertig'):
            set_state(jid, phase='Fast fertig …', progress=0.97)
    p.wait()
    open(os.path.join(d, 'log.txt'), 'w', encoding='utf-8').write('\n'.join(log))

    if 'OPENAI_API_KEY ist nicht gesetzt' in '\n'.join(log):
        set_state(jid, status='fehler', progress=0,
                  msg='Der Server ist noch nicht fertig eingerichtet '
                      '(kein OpenAI-Schlüssel). Sag Ismet Bescheid.')
        return
    if p.returncode == 0 and os.path.exists(out):
        count_use(j['code'])
        set_state(jid, status='fertig', progress=1.0, phase='Fertig',
                  out='fertig.mp4')
    else:
        letzte = [x for x in log[-12:] if x.strip()]
        set_state(jid, status='fehler', progress=0,
                  msg='Der Render ist fehlgeschlagen.',
                  detail='\n'.join(letzte))
    try:
        os.remove(src)              # Quellvideo loeschen: kein Datenfriedhof
    except Exception:
        pass


for _ in range(int(os.environ.get('DVE_WORKERS', '1'))):
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------- Endpunkte
@app.get('/', response_class=HTMLResponse)
def index():
    return open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()


@app.post('/api/pruefe-code')
def pruefe(code: str = Form(...)):
    ok, msg = check_code(code)
    if not ok:
        return JSONResponse({'ok': False, 'msg': msg}, status_code=403)
    c = load_codes()[code.strip()]
    rest = (c['limit'] - c.get('genutzt', 0)) if c.get('limit') else None
    return {'ok': True, 'name': c.get('name', ''), 'rest': rest}


@app.post('/api/upload')
async def upload(datei: UploadFile = File(...), look: str = Form('creator'),
                 code: str = Form(...)):
    ok, msg = check_code(code)
    if not ok:
        raise HTTPException(403, msg)
    if look not in LOOKS:
        look = 'creator'
    jid = uuid.uuid4().hex[:12]
    d = job_dir(jid)
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv'):
        raise HTTPException(400, 'Nur Videodateien (mp4, mov, webm, mkv).')
    src = os.path.join(d, 'quelle' + ext)
    groesse = 0
    with open(src, 'wb') as f:
        while True:
            chunk = await datei.read(1 << 20)
            if not chunk:
                break
            groesse += len(chunk)
            if groesse > MAX_MB * 1024 * 1024:
                f.close()
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, f'Video zu groß (max. {MAX_MB} MB).')
            f.write(chunk)

    # Laenge pruefen: ein 30-Minuten-Video blockiert die Warteschlange stundenlang.
    try:
        dur = float(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', src],
            capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        dur = 0
    if dur > MAX_SECONDS:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(413, f'Video zu lang ({dur:.0f}s). '
                                 f'Maximal {MAX_SECONDS} Sekunden.')

    JOBS[jid] = {'id': jid, 'input': src, 'look': look, 'code': code.strip(),
                 'status': 'wartet', 'progress': 0.0,
                 'phase': 'In der Warteschlange …',
                 'dauer': round(dur, 1), 'name': datei.filename}
    set_state(jid, **JOBS[jid])
    QUEUE.put(jid)
    return {'job': jid, 'position': QUEUE.qsize()}


@app.get('/api/status/{jid}')
def status(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Job unbekannt.')
    out = {k: v for k, v in j.items() if k not in ('input', 'code')}
    if j.get('status') == 'wartet':
        out['phase'] = f'In der Warteschlange (Platz {QUEUE.qsize()}) …'
    return out


@app.get('/api/video/{jid}')
def video(jid: str):
    p = os.path.join(job_dir(jid), 'fertig.mp4')
    if not os.path.exists(p):
        raise HTTPException(404, 'Noch nicht fertig.')
    return FileResponse(p, media_type='video/mp4',
                        filename='DouchkoVE_Captions.mp4')


@app.get('/api/looks')
def looks():
    return LOOKS


@app.get('/admin/codes')
def admin_codes(schluessel: str = ''):
    """Uebersicht fuer dich: wer hat wie viel verbraucht."""
    if schluessel != os.environ.get('DVE_ADMIN', 'admin'):
        raise HTTPException(403, 'Kein Zugriff.')
    return load_codes()
