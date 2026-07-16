# -*- coding: utf-8 -*-
"""DouchkoVE Web - vollstaendige Web-Version mit allen Reglern der Desktop-App.

Was fehlt bewusst (server-seitig sinnlos):
- Blender-Wasser (500 MB Install, sehr langsam auf CPU - hart aus).
- Freesound-Key-Verwaltung (Sound-Pack liegt auf dem Server).
- Kundenprofile (Session-basiert - hier nicht relevant).
- Windows-Setup-Sachen.

Was NEU vs. v59:
- Alle v69-v73-Effekte als Regler (Blur, Musik-Beat, Freeze, Trail, Ring,
  Split, Env-Shadow).
- Momente-Editor mit Undo/Redo (v68a).
- Font-Auswahl, Fein-Regler, Momente-Rerender.
- Preset (Look) als Startpunkt, individuelles Feintuning per JSON-Overrides.
"""
import copy
import glob
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
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get('DVE_DATA', os.path.join(HERE, 'data'))
JOBS_DIR = os.path.join(DATA, 'jobs')
CODES_FILE = os.path.join(DATA, 'codes.json')
MAX_MB = int(os.environ.get('DVE_MAX_MB', '300'))
MAX_SECONDS = int(os.environ.get('DVE_MAX_SECONDS', '180'))

os.makedirs(JOBS_DIR, exist_ok=True)

app = FastAPI(title='DouchkoVE')

# Fonts fuer die Font-Kacheln (Preview mit tatsaechlicher Schrift)
_fonts_dir = os.path.join(ROOT, 'fonts')
if os.path.isdir(_fonts_dir):
    app.mount('/fonts', StaticFiles(directory=_fonts_dir), name='fonts')
JOBS = {}
QUEUE = Queue()
LOCK = threading.Lock()

# Presets als Startpunkt. Der Nutzer kann alles individuell nachjustieren.
LOOKS = {
    'tiktok':    {'name': 'TikTok', 'desc': 'Wort für Wort, fett, laut.'},
    'creator':   {'name': 'Creator', 'desc': 'Talking-Head & Business.'},
    'cinematic': {'name': 'Cinematic', 'desc': 'Wenige, große Momente.'},
    'clean':     {'name': 'Clean', 'desc': 'Nur lesbare Untertitel.'},
}

# Font-Kacheln wie in der Desktop-App
FONTS = [
    {'id': 'kino',    'label': 'Kino',      'file': 'fonts/archivo.ttf',
     'script': 'fonts/playfair_i.ttf'},
    {'id': 'tiktok',  'label': 'TikTok',    'file': 'fonts/tiktok_bold.ttf'},
    {'id': 'montse',  'label': 'Creator',   'file': 'fonts/montserrat_xb.ttf'},
    {'id': 'inter',   'label': 'Cinematic', 'file': 'fonts/inter_black.ttf'},
    {'id': 'anton',   'label': 'Impact',    'file': 'fonts/anton.ttf'},
    {'id': 'archivo', 'label': 'Black',     'file': 'fonts/archivo.ttf'},
    {'id': 'bebas',   'label': 'Condensed', 'file': 'fonts/bebas.ttf'},
    {'id': 'poppins', 'label': 'Clean',     'file': 'fonts/poppins_b.ttf'},
    {'id': 'staat',   'label': 'Poster',    'file': 'fonts/staatliches.ttf'},
    {'id': 'alfa',    'label': 'Slab',      'file': 'fonts/alfaslab.ttf'},
    {'id': 'yeseva',  'label': 'Fashion',   'file': 'fonts/yeseva.ttf'},
    {'id': 'bangers', 'label': 'Comic',     'file': 'fonts/bangers.ttf'},
    {'id': 'right',   'label': 'Retro',     'file': 'fonts/righteous.ttf'},
    {'id': 'lobster', 'label': 'Script',    'file': 'fonts/lobster.ttf'},
    {'id': 'marker',  'label': 'Brush',     'file': 'fonts/marker.ttf'},
]

FX_LABELS = [
    ('behind',  'Hinter dir'),
    ('cascade', 'Buchstaben-Aufbau'),
    ('blurin',  'Aus der Unschärfe'),
    ('outline', 'Nur Umriss'),
    ('ground',  'In der Szene'),
]

ANIM_LABELS = {
    '': 'keine', 'glitch': 'Glitch', 'puls': 'Puls', 'welle': 'Welle',
    'zittern': 'Zittern', 'neon': 'Neon', 'schub': 'Schub',
    'bruch': 'Bruch (zerbricht)', 'sturz': 'Sturz (fällt)',
    'anstieg': 'Anstieg (steigt)', 'wende': 'Wende (kippt um)',
    'druck': 'Druck (erdrückt)', 'schwund': 'Schwund (löst sich auf)',
    'knall': 'Knall (Pointe)', 'gewicht': 'Gewicht (Strich fetter)',
    'schweben': 'Schweben (3D-Drift)', 'fokus': 'Fokus (kommt scharf)',
    'enthuellen': 'Enthüllen (freigewischt)', 'spur': 'Spur (Nachzieher)',
    'kippen': 'Kippen (klappt nach vorn)',
    'explosion': 'Explosion (fliegt weg + zurück)',
    'magnet': 'Magnet (zieht zusammen)',
    'wackel': 'Wackel (Cartoon-Bounce)',
    'regen': 'Regen (fällt von oben)',
    'zoom_punch': 'Zoom-Punch (harter Push)',
    'rutsche': 'Rutsche (von rechts)',
    'stempel': 'Stempel (knallt drauf)',
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


# ---------------------------------------------------------------- Config-Merge
def deep_merge(base, override):
    """Rekursives Merge: override ueberschreibt base an Blaettern.
    Nur Dicts werden merged, alles andere ersetzt."""
    if not isinstance(override, dict):
        return override
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def build_config(look, overrides=None):
    """Config-Kaskade: config.yaml -> Preset -> User-Overrides.
    Serverseitige Zwaenge werden am Ende hart ueberschrieben (Blender aus).

    Presets sind Stand 2026 - jeder ist eine vollstaendige High-End-Konfig
    quer durch alle Effekte, Kamera, Farben und Schrift. Nutzer kann alles
    einzeln nachtunen; die Defaults sind aber schon deploybar."""
    cfg = yaml.safe_load(open(os.path.join(ROOT, 'config.yaml'), encoding='utf-8'))

    # --- 2026er High-End-Presets (voll ausgereizt, produktionsreif)
    PRESETS = {
        'tiktok': {
            'effects': {
                # Wortweise, dicht, energisch - Reels/Shorts-Kern-Modus 2026
                'density': 'wortweise', 'text_style': '3d kinetisch',
                'hook_seconds': 8, 'hook_strength': 0.85, 'instant_hook': True,
                'pattern_interrupt': 6, 'retention_gap': 8,
                'words_per_group': 2, 'words_per_group_max': 4,
                'chunk_hold_min': 0.55,
                'dim_behind': 0.42, 'dim_blurin': 0.34,
                'beat_sync': 0.90, 'music_beat': 0.85, 'person_shadow': 0.60,
                'zahl_gap': 10,
                'bg_blur': 0.60, 'freeze_frame': 0.50, 'trail': 0.45,
                'counter_ring': 0.55, 'split_screen': 0.30, 'env_shadow': 0.15,
                'emerge': 'immer', 'anim': True,
                'keyword_rotation': ['behind', 'outline', 'ground'],
                'sfx_volume': 0.55, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.90, 'crash': 1.00, 'whip': True, 'side_every': 2,
                'keyword_rotation': ['punch', 'push', 'caption'],
                'side_rotation': ['capzoom', 'drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/tiktok_bold.ttf',
                'italic': 'fonts/tiktok_bold.ttf',
                'script': 'fonts/tiktok_bold.ttf',
            },
            'matting_quality': 'hoch',
        },
        'creator': {
            'effects': {
                # Talking-Head + Business - klar, ruhig-dynamisch, professionell
                'density': 'akzente', 'text_style': '3d',
                'hook_seconds': 15, 'hook_strength': 0.55, 'instant_hook': True,
                'pattern_interrupt': 9, 'retention_gap': 12,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.75,
                'dim_behind': 0.38, 'dim_blurin': 0.30,
                'beat_sync': 0.75, 'music_beat': 0.45, 'person_shadow': 0.55,
                'zahl_gap': 15,
                'bg_blur': 0.55, 'freeze_frame': 0.30, 'trail': 0.0,
                'counter_ring': 0.40, 'split_screen': 0.0, 'env_shadow': 0.45,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['behind', 'cascade', 'blurin', 'outline'],
                'sfx_volume': 0.40, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.70, 'crash': 0.55, 'whip': False, 'side_every': 3,
                'keyword_rotation': ['caption', 'punch', 'pan', 'push'],
                'side_rotation': ['capzoom', 'drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/montserrat_xb.ttf',
                'italic': 'fonts/montserrat_xb.ttf',
                'script': 'fonts/playfair_i.ttf',
            },
            'matting_quality': 'hoch',
        },
        'cinematic': {
            'effects': {
                # Wenige, grosse Momente. Kino-Bokeh, Freeze-Signature.
                'density': 'sparsam', 'text_style': 'klassisch',
                'hook_seconds': 30, 'hook_strength': 0.35, 'instant_hook': False,
                'pattern_interrupt': 14, 'retention_gap': 18,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.95,
                'dim_behind': 0.34, 'dim_blurin': 0.28,
                'beat_sync': 0.55, 'music_beat': 0.30, 'person_shadow': 0.65,
                'zahl_gap': 20,
                'bg_blur': 0.70, 'freeze_frame': 1.00, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.20, 'env_shadow': 0.65,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['blurin', 'ground', 'outline'],
                'sfx_volume': 0.28, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.55, 'crash': 0.40, 'whip': False, 'side_every': 4,
                'keyword_rotation': ['pan', 'pullback', 'caption'],
                'side_rotation': ['drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/inter_black.ttf',
                'italic': 'fonts/serif_i.ttf',
                'script': 'fonts/playfair_i.ttf',
            },
            'matting_quality': 'maximum',
        },
        'clean': {
            'effects': {
                # Nur lesbare Untertitel, keinerlei Deko. Minimalismus 2026.
                'density': 'sparsam', 'text_style': 'klassisch',
                'hook_seconds': 0, 'hook_strength': 0.0, 'instant_hook': False,
                'pattern_interrupt': 0, 'retention_gap': 0,
                'words_per_group': 3, 'words_per_group_max': 4,
                'chunk_hold_min': 0.80,
                'dim_behind': 0.0, 'dim_blurin': 0.0,
                'beat_sync': 0.0, 'music_beat': 0.0, 'person_shadow': 0.0,
                'zahl_gap': 0,
                'bg_blur': 0.0, 'freeze_frame': 0.0, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.0, 'env_shadow': 0.0,
                'emerge': 'aus', 'anim': False,
                'keyword_rotation': ['outline'],
                'sfx_volume': 0.0, 'sfx': False,
                'reflection': False, 'occlusion': False, 'track3d': False,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.0, 'crash': 0.0, 'whip': False, 'side_every': 10,
                'keyword_rotation': [], 'side_rotation': [],
            },
            'colors': {'style': 'schwarz', 'adaptive': False},
            'fonts': {
                'display': 'fonts/poppins_b.ttf',
                'italic': 'fonts/poppins_b.ttf',
                'script': 'fonts/poppins_b.ttf',
            },
            'matting_quality': 'standard',
        },
    }
    preset = PRESETS.get(look, PRESETS['creator'])
    cfg = deep_merge(cfg, preset)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    # Serverseitige Zwaenge - unabhaengig vom User-Wunsch
    cfg['effects']['blender_water'] = False
    return cfg


# ---------------------------------------------------------------- Render-Worker
def job_dir(jid):
    return os.path.join(JOBS_DIR, jid)


def set_state(jid, **kw):
    j = JOBS.setdefault(jid, {})
    j.update(kw)
    try:
        json.dump({k: v for k, v in j.items() if k not in ('input', 'code')},
                  open(os.path.join(job_dir(jid), 'state.json'), 'w',
                       encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def _run_render(jid, extra_args=None, out_name='fertig.mp4', progress_start=0.05):
    """Ruft render.py als Subprocess und streamt Log + Fortschritt in state."""
    j = JOBS[jid]
    d = job_dir(jid)
    src = j['input']
    out = os.path.join(d, out_name)
    cfg = build_config(j.get('look', 'creator'), j.get('cfg_overrides'))
    cfg_path = os.path.join(d, 'config.yaml')
    yaml.safe_dump(cfg, open(cfg_path, 'w', encoding='utf-8'), allow_unicode=True)

    cmd = [sys.executable, os.path.join(ROOT, 'render.py'), src,
           '--config', cfg_path, '--out', out] + (extra_args or [])
    env = dict(os.environ)
    set_state(jid, status='laeuft', phase='Transkription …',
              progress=progress_start)
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
    open(os.path.join(d, 'log.txt'), 'a', encoding='utf-8').write('\n'.join(log) + '\n')
    return p.returncode, log, out


def worker():
    while True:
        jid = QUEUE.get()
        try:
            run_job(jid)
        except Exception as e:
            set_state(jid, status='fehler',
                      msg=f'Unerwarteter Fehler: {type(e).__name__}: {e}')
        finally:
            QUEUE.task_done()


def run_job(jid):
    """Voller Render: Analyse -> Momente -> Video-Bau."""
    j = JOBS[jid]
    d = job_dir(jid)
    mode = j.get('mode', 'full')
    if mode == 'analyze':
        rc, log, out = _run_render(jid, extra_args=['--plan-only'],
                                   out_name='plan.mp4', progress_start=0.10)
        if rc == 0:
            # Momente-Datei liegt neben dem Quellvideo
            base = os.path.splitext(j['input'])[0]
            mom_path = base + '_momente.json'
            if os.path.exists(mom_path):
                set_state(jid, status='analysiert', progress=1.0,
                          phase='Momente bereit',
                          moments_url=f'/api/moments/{jid}')
                return
        set_state(jid, status='fehler', progress=0,
                  msg='Analyse fehlgeschlagen.',
                  detail='\n'.join([x for x in log[-15:] if x.strip()]))
        return

    rc, log, out = _run_render(jid)
    if 'OPENAI_API_KEY ist nicht gesetzt' in '\n'.join(log):
        set_state(jid, status='fehler', progress=0,
                  msg='Der Server ist nicht fertig eingerichtet '
                      '(kein OpenAI-Schlüssel). Sag Ismet Bescheid.')
        return
    if rc == 0 and os.path.exists(out):
        count_use(j['code'])
        set_state(jid, status='fertig', progress=1.0, phase='Fertig',
                  out='fertig.mp4')
    else:
        letzte = [x for x in log[-15:] if x.strip()]
        set_state(jid, status='fehler', progress=0,
                  msg='Der Render ist fehlgeschlagen.',
                  detail='\n'.join(letzte))
    # Quellvideo aufheben, damit "Momente-Editor" nach Analyse den Re-Render kann.
    # Erst beim Job-Cleanup loeschen.


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


@app.get('/api/looks')
def looks():
    return LOOKS


@app.get('/api/fonts')
def fonts():
    return FONTS


@app.get('/api/fx_labels')
def fx_labels():
    return FX_LABELS


@app.get('/api/anim_labels')
def anim_labels():
    return ANIM_LABELS


@app.get('/api/default_config')
def default_config(look: str = 'creator'):
    """Voreinstellungen fuer die UI. Der Client kann alles ueberschreiben."""
    return build_config(look)


@app.post('/api/upload')
async def upload(datei: UploadFile = File(...), look: str = Form('creator'),
                 code: str = Form(...), mode: str = Form('full'),
                 cfg_overrides: str = Form('{}')):
    ok, msg = check_code(code)
    if not ok:
        raise HTTPException(403, msg)
    if look not in LOOKS:
        look = 'creator'
    try:
        overrides = json.loads(cfg_overrides) if cfg_overrides else {}
    except Exception:
        overrides = {}
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
                 'mode': mode, 'cfg_overrides': overrides,
                 'status': 'wartet', 'progress': 0.0,
                 'phase': 'In der Warteschlange …',
                 'dauer': round(dur, 1), 'name': datei.filename}
    set_state(jid, **{k: v for k, v in JOBS[jid].items()
                      if k not in ('input', 'code')})
    QUEUE.put(jid)
    return {'job': jid, 'position': QUEUE.qsize()}


@app.get('/api/status/{jid}')
def status(jid: str):
    j = JOBS.get(jid)
    if not j:
        # State evtl. auf Platte
        sp = os.path.join(job_dir(jid), 'state.json')
        if os.path.exists(sp):
            return json.load(open(sp, encoding='utf-8'))
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


@app.get('/api/moments/{jid}')
def get_moments(jid: str):
    """Momente-Datei aus der Analyse laden."""
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Job unbekannt.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
    if not os.path.exists(mom_path):
        raise HTTPException(404, 'Momente noch nicht analysiert.')
    return json.load(open(mom_path, encoding='utf-8'))


@app.post('/api/moments/{jid}')
async def save_and_render(jid: str, moments: str = Form(...),
                          code: str = Form(...)):
    """Momente speichern und Voll-Render starten."""
    ok, msg = check_code(code)
    if not ok:
        raise HTTPException(403, msg)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Job unbekannt.')
    try:
        mom = json.loads(moments)
    except Exception:
        raise HTTPException(400, 'Momente-JSON ungueltig.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
    json.dump(mom, open(mom_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    # Voll-Render mit den neuen Momenten
    j['mode'] = 'full'
    j['status'] = 'wartet'
    j['progress'] = 0.0
    j['phase'] = 'In der Warteschlange (Re-Render) …'
    set_state(jid, **{k: v for k, v in j.items()
                      if k not in ('input', 'code')})
    QUEUE.put(jid)
    return {'ok': True, 'job': jid, 'position': QUEUE.qsize()}


@app.get('/admin/codes')
def admin_codes(schluessel: str = ''):
    if schluessel != os.environ.get('DVE_ADMIN', 'admin'):
        raise HTTPException(403, 'Kein Zugriff.')
    return load_codes()
