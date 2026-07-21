"""
Premium Captions - automatische Premium-Untertitel im Editorial-Stil
Pipeline: Whisper API -> RVM Matting (GPU) -> Face Tracking -> Compositing -> Encode

Nutzung:
    python render.py video.mp4
    python render.py video.mp4 --out fertig.mp4 --keywords "Schufa,Score"
    python render.py video.mp4 --transcript video_transcript.json   (API-Aufruf ueberspringen)
"""
import argparse, json, math, os, re, subprocess, sys, tempfile, time
import numpy as np
import blender_engine
import cv2
import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

MODEL_URLS = {
    'models/rvm.onnx': 'https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx',
    'models/face.tflite': 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
    'models/depth.onnx': 'https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx',
}

# ---------------------------------------------------------------- helpers
MODEL_MIN_BYTES = {'models/rvm.onnx': 10_000_000,
                   'models/face.tflite': 100_000,
                   'models/depth.onnx': 80_000_000}


def ensure_models():
    """Laedt die KI-Modelle. Frueher wurde die ganze Datei in einem Rutsch in den
    Speicher gezogen (requests.get + r.content). Reisst die Verbindung mittendrin
    ab - bei der 99-MB-Tiefendatei sehr wahrscheinlich -, bricht alles ab.
    Jetzt: in Haeppchen laden, bei Abbruch DORT WEITERMACHEN wo es aufhoerte
    (Range-Header), mehrere Anlaeufe, und am Ende die Groesse pruefen."""
    import requests
    for rel, url in MODEL_URLS.items():
        path = os.path.join(HERE, rel)
        need = MODEL_MIN_BYTES.get(rel, 1000)
        # Halbe Datei von einem frueheren Abbruch? Die waere unbrauchbar und
        # wuerde spaeter mit einem kryptischen ONNX-Fehler knallen.
        if os.path.exists(path) and os.path.getsize(path) >= need:
            continue
        if os.path.exists(path):
            print(f"  {rel} ist unvollstaendig - wird neu geladen")
            os.remove(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = path + '.part'
        print(f"Lade {rel} herunter...")
        for versuch in range(1, 6):
            have = os.path.getsize(part) if os.path.exists(part) else 0
            try:
                headers = {'Range': f'bytes={have}-'} if have else {}
                r = requests.get(url, timeout=(30, 120), allow_redirects=True,
                                 stream=True, headers=headers)
                if have and r.status_code == 200:
                    have = 0                 # Server kann nicht fortsetzen
                    r.close()
                    r = requests.get(url, timeout=(30, 120), allow_redirects=True,
                                     stream=True)
                r.raise_for_status()
                total = int(r.headers.get('Content-Length') or 0) + have
                with open(part, 'ab' if have else 'wb') as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            fh.write(chunk)
                            have += len(chunk)
                            if total:
                                print(f"\r  {have / 1e6:.0f} / {total / 1e6:.0f} MB",
                                      end='', flush=True)
                print()
                if os.path.getsize(part) < need:
                    raise IOError(f'Datei zu klein ({os.path.getsize(part)} Bytes)')
                os.replace(part, path)
                break
            except Exception as e:
                print(f"\n  Abbruch ({type(e).__name__}) - Versuch {versuch}/5, "
                      f"mache bei {have / 1e6:.0f} MB weiter ...")
                time.sleep(2 * versuch)
        else:
            raise RuntimeError(
                f"Download von {rel} nach 5 Versuchen fehlgeschlagen.\n"
                f"  Datei manuell laden: {url}\n"
                f"  und ablegen unter:   {path}")

def ease_out(x): return 1 - (1 - min(max(x, 0), 1)) ** 3
def ease_expo(x):
    x = min(max(x, 0), 1)
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)
def ease_back(x):
    x = min(max(x, 0), 1)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def smoothstep(x):
    x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def exit_env(over, dur=0.24):
    """Hand-Made-Exit (v82): Deckkraft laesst LOS statt linear zu dimmen.
    Ease-In-Kurve: haelt anfangs fast voll, beschleunigt in den Schnitt -
    so raeumt ein Cutter Text weg (Anticipation auf das Naechste).
    over = Sekunden seit p['end']. Rueckgabe 1 -> 0."""
    if over <= 0: return 1.0
    x = min(over / max(dur, 1e-6), 1.0)
    return 1.0 - x * x * x
def exit_pose(over, dur=0.24, drop=True):
    """Begleit-Bewegung zum Exit: minimaler Scale-Settle + Richtungs-Drift.
    Statischer Fade wirkt billig; 2-3% Bewegung verkauft die Absicht.
    Rueckgabe (scale_mul, dy_pixelanteil 0..1 der Schrifthoehe)."""
    if over <= 0: return 1.0, 0.0
    x = min(over / max(dur, 1e-6), 1.0)
    xe = x * x                                # ease-in: erst ruhig, dann weg
    return 1.0 - 0.030 * xe, (0.10 if drop else -0.10) * xe
def hand_jitter(seed):
    """v82: Hand-Keyframe-Streuung. Ein Cutter setzt nie zwei Keyframes exakt
    gleich - Dauer und Versatz streuen minimal. Deterministischer Pseudo-
    zufall aus dem Wort-Index (jeder Render bleibt identisch reproduzierbar).
    Rueckgabe -1..1."""
    x = math.sin(float(seed) * 12.9898 + 78.233) * 43758.5453
    return (x - math.floor(x)) * 2.0 - 1.0
def spring(x, freq=3.4, damp=5.5):
    """Feder statt Kurve: schiesst leicht ueber das Ziel hinaus und pendelt sich
    ein - genau das Verhalten, das teure Motion-Graphics 2026 von billigen
    Ease-Out-Presets unterscheidet. Gibt 0 -> 1 (mit Ueberschwinger > 1)."""
    x = max(x, 0.0)
    if x >= 1.6:
        return 1.0
    return 1.0 - math.exp(-damp * x) * math.cos(freq * math.pi * x)
def rng(i, salt=0):
    v = math.sin(i * 127.1 + salt * 311.7) * 43758.5453
    return v - math.floor(v)
def clean(w): return w.rstrip('.,!?').strip()

def iter_frames(path, w, h, rate, start=None):
    """Liefert Frames als konstante Framerate ueber eine ffmpeg-Pipe.
    Dupliziert/verwirft Frames nach ihren echten Zeitstempeln - VFR-Videos bleiben synchron.
    start: exakter Seek (Sekunden) fuer Fenster-Renders."""
    cmd = ['ffmpeg', '-nostdin', '-v', 'error'] \
        + (['-ss', f'{start:.6f}'] if start else []) + ['-i', path,
           '-vf', f'scale={w}:{h},fps={rate}',
           '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=w * h * 3 * 4)
    try:
        while True:
            buf = proc.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()

def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=width,height,r_frame_rate', '-show_entries', 'format=duration',
                        '-of', 'json', path], capture_output=True, text=True)
    import json as _json
    d = _json.loads(r.stdout)
    st = d['streams'][0]
    num, den = st['r_frame_rate'].split('/')
    fps = float(num) / float(den)
    return int(st['width']), int(st['height']), fps, st['r_frame_rate'], float(d['format']['duration'])



class Rotator:
    """Variation ohne Chaos: mischt eine Liste durch, spielt sie ab, mischt neu -
    jeder Wert kommt gleich oft vor, aber nie zweimal direkt hintereinander.
    Genau so wirken Videos abwechslungsreich statt zufaellig oder monoton."""
    def __init__(self, items, seed=0):
        self.items = list(items) or [None]
        self.rng = np.random.default_rng(seed)
        self.bag, self.last = [], None

    def next(self):
        if not self.bag:
            self.bag = list(self.items)
            self.rng.shuffle(self.bag)
            if len(self.bag) > 1 and self.bag[0] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop(0)
        return self.last


# ---------------------------------------------------------------- lebendige Typo
# EINE Stelle fuer alle Animationen. Jeder Zeichenpfad ruft anim_apply() auf -
# so kann keine Auswahl mehr still verpuffen (der alte Feuer-/Glitch-Bug).
ANIM_LIST = ('glitch', 'puls', 'welle', 'zittern', 'neon', 'schub', 'bruch',
             'sturz', 'anstieg', 'wende', 'druck', 'schwund', 'knall',
             # --- Stand 2026: das, was High-End-Editing heute von Presets trennt.
             # Zurueckhaltende, physikalisch plausible Bewegung statt Zappeln.
             'gewicht', 'schweben', 'fokus', 'enthuellen', 'spur',
             # --- v71: acht weitere Klassiker, physikalisch plausibel, jede
             # loest ein anderes Ereignis auf: Kippen, Impact, Sog, Cartoon-
             # Puls, Fallen, Punch, Slide, Stempel.
             'kippen', 'explosion', 'magnet', 'wackel', 'regen', 'zoom_punch',
             'rutsche', 'stempel')

# v94: Animationen mit GROSSER, sichtbarer Bewegung. Hinter der Person
# ("behind") gehen sie unter - solche Momente werden nach vorn geholt.
_VISIBLE_ANIM = frozenset((
    'explosion', 'bruch', 'sturz', 'anstieg', 'spur', 'zoom_punch',
    'regen', 'magnet', 'stempel', 'kippen', 'wackel', 'rutsche'))

# Bewegungsunschaerfe global (aus config.yaml gesetzt). Sie ist der groesste
# einzelne Qualitaetsunterschied: ohne sie springt Text von Frame zu Frame und
# wirkt aufgeklebt - mit ihr sitzt er im Bild.
MOTION_BLUR = True
BEAT_SYNC = 0.7      # Staerke der Onset-Kopplung (0 = aus)
PERSON_SHADOW = 0.5  # Schatten der Person auf den Text dahinter


def _motion_blur(arr, vx, vy):
    """Richtungs-Unschaerfe entlang des Bewegungsvektors (Pixel pro Frame).
    Emuliert den 180-Grad-Shutter einer echten Kamera."""
    mag = math.hypot(vx, vy)
    if mag < 1.6 or arr is None:
        return arr
    mag = min(mag, 34.0)
    k = int(mag) | 1
    if k < 3:
        return arr
    ker = np.zeros((k, k), np.float32)
    cx = (k - 1) / 2.0
    ang = math.atan2(vy, vx)
    ca, sa = math.cos(ang), math.sin(ang)
    for t in np.linspace(-0.5, 0.5, k * 3):
        x = int(round(cx + ca * t * (k - 1)))
        y = int(round(cx + sa * t * (k - 1)))
        if 0 <= x < k and 0 <= y < k:
            ker[y, x] += 1.0
    ssum = float(ker.sum())
    if ssum <= 0:
        return arr
    ker /= ssum
    pad = k // 2 + 1
    src = cv2.copyMakeBorder(arr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    # Premultipliziert filtern, sonst blutet Schwarz aus den transparenten Raendern.
    f = src.astype(np.float32)
    a = f[..., 3:4] / 255.0
    pm = np.concatenate([f[..., :3] * a, f[..., 3:4]], axis=2)
    pm = cv2.filter2D(pm, -1, ker, borderType=cv2.BORDER_CONSTANT)
    a2 = np.clip(pm[..., 3:4], 0, 255)
    rgb = np.where(a2 > 1.0, pm[..., :3] / np.maximum(a2 / 255.0, 1e-4), 0.0)
    return np.concatenate([np.clip(rgb, 0, 255), a2], axis=2).astype(arr.dtype)


def _weight_morph(arr, amt):
    """Variable-Font-Look: der Strich wird fetter/duenner, ohne die Groesse zu
    aendern. Genau die Achsen-Animation, die 2026 als Premium-Signatur gilt -
    hier optisch ueber Morphologie, damit kein Font pro Frame neu gerendert wird."""
    if abs(amt) < 0.06 or arr is None:
        return arr
    k = max(int(round(abs(amt) * 4)) | 1, 3)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    out = arr.copy()
    if amt > 0:
        out[..., 3] = cv2.dilate(arr[..., 3], ker)
        out[..., :3] = cv2.dilate(arr[..., :3], ker)
    else:
        out[..., 3] = cv2.erode(arr[..., 3], ker)
    return out


# ---- Variable-Font-Achsen: echte wght-Animation statt Morphologie-Trick.
# 2026-Standard im High-End-Editing: der Strich waechst, die Form bleibt korrekt.
VAR_EQUIV = {
    'archivo.ttf':      'fonts/archivo_var.ttf',
    'inter_black.ttf':  'fonts/inter_var.ttf',
    'montserrat_xb.ttf': 'fonts/montserrat_var.ttf',
}


def var_font_for(path):
    """Variabler Schnitt zur statischen Schrift - oder None."""
    v = VAR_EQUIV.get(os.path.basename(path or ''))
    if not v:
        return None
    full = os.path.join(HERE, v)
    return full if os.path.exists(full) else None


def _pad_to(arr, w, h):
    """Zentriert ein Bild auf eine gemeinsame Leinwand (Gewichts-Leiter)."""
    ph, pw = arr.shape[:2]
    out = np.zeros((h, w, 4), arr.dtype)
    y0, x0 = (h - ph) // 2, (w - pw) // 2
    out[y0:y0 + ph, x0:x0 + pw] = arr
    return out


def build_wladder(wbuild, lo=300, hi=900, steps=7):
    """Rendert das Wort in mehreren Schriftgewichten und legt alle Stufen auf eine
    gemeinsame Leinwand. Im Frame wird nur noch die Stufe gewaehlt - kein Font-
    Rendering pro Frame, aber echte Achsen-Interpolation statt Dick-Rechnen."""
    arrs = []
    for k in range(steps):
        w = lo + (hi - lo) * k / (steps - 1)
        a = wbuild(w)
        if a is None:
            return None
        arrs.append(a)
    W = max(a.shape[1] for a in arrs)
    H = max(a.shape[0] for a in arrs)
    return [_pad_to(a, W, H) for a in arrs]


def _liquid(arr, amt, seed=0):
    """Fluid-Morph: das Wort fliesst aus einer weichen Verzerrung in seine Form.
    amt=1 -> stark verflossen, amt=0 -> Original. Ersetzt den harten Schnitt
    zwischen zwei Chunks durch einen fliessenden Uebergang."""
    if arr is None or amt < 0.02:
        return arr
    h, w = arr.shape[:2]
    r = np.random.default_rng(1234 + int(seed))
    small = r.standard_normal((max(h // 24, 3), max(w // 24, 3), 2)).astype(np.float32)
    fld = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    fld = cv2.GaussianBlur(fld, (0, 0), max(min(w, h) * 0.03, 3.0))
    fld /= max(float(np.abs(fld).max()), 1e-6)
    d = float(amt) * min(w, h) * 0.20
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    out = cv2.remap(arr, gx + fld[..., 0] * d, gy + fld[..., 1] * d,
                    cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(0, 0, 0, 0))
    return out


def _persp3d(arr, ax, ay, pad_f=0.14):
    """Echte perspektivische Kippung um X- und Y-Achse (Bogenmass). Der alte
    Trick (nur horizontal stauchen) sieht flach aus; hier laufen die Kanten
    korrekt zusammen - das Wort steht wirklich im Raum hinter der Person."""
    h, w = arr.shape[:2]
    if abs(ax) < 1e-3 and abs(ay) < 1e-3:
        return arr, 0, 0
    px, py = int(w * pad_f) + 4, int(h * pad_f) + 4
    W2, H2 = w + 2 * px, h + 2 * py
    f = max(w, h) * 1.8                      # Brennweite: dezente Perspektive
    cx, cy = w / 2.0, h / 2.0
    ca, sa = math.cos(ay), math.sin(ay)
    cb, sb = math.cos(ax), math.sin(ax)
    src, dst = [], []
    for (qx, qy) in ((0, 0), (w, 0), (w, h), (0, h)):
        X, Y, Z = qx - cx, qy - cy, 0.0
        X, Z = X * ca + Z * sa, -X * sa + Z * ca      # Drehung um die Hochachse
        Y, Z = Y * cb - Z * sb, Y * sb + Z * cb       # Drehung um die Querachse
        k = f / max(f + Z, f * 0.25)
        src.append((qx, qy))
        dst.append((X * k + cx + px, Y * k + cy + py))
    M = cv2.getPerspectiveTransform(np.float32(src), np.float32(dst))
    out = cv2.warpPerspective(arr, M, (W2, H2), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return out, px, py


def _bruch_shards(base, rng, n=4):
    """Zerlegt das Wort in Scherben: gezackte Bruchkanten von oben nach unten.
    Wird pro Moment einmal gerechnet und dann wiederverwendet (gleicher Bruch
    in jedem Frame - sonst flackert das Wort)."""
    h, w = base.shape[:2]
    ys = np.arange(h, dtype=np.float32)
    seams = [np.zeros(h, np.float32)]
    for k in range(1, n):
        x0 = w * k / n
        # Gezackte, aber DURCHGEHENDE Bruchkante. Rauschen pro Zeile wuerde
        # 1-Pixel-Kaemme erzeugen (fransige, schmutzige Kante) - darum wird der
        # Zufall entlang der Hoehe geglaettet: echte Zacken, saubere Kante.
        noise = rng.random(h).astype(np.float32) - 0.5
        kx = max(int(h * 0.10) | 1, 3)
        noise = cv2.GaussianBlur(noise.reshape(-1, 1), (1, kx), 0).ravel()
        noise /= max(float(np.abs(noise).max()), 1e-6)
        jag = (np.sin(ys / max(h, 1) * (2.2 + float(rng.random()) * 2.0)
                      + float(rng.random()) * 6.0) * (w * 0.030)
               + noise * (w * 0.022))
        seams.append(np.clip(x0 + jag, 0, w))
    seams.append(np.full(h, float(w), np.float32))
    xs = np.arange(w, dtype=np.float32)[None, :]
    shards = []
    for k in range(n):
        m = ((xs >= seams[k][:, None]) & (xs < seams[k + 1][:, None])).astype(np.float32)
        piece = base.copy()
        piece[..., 3] = (piece[..., 3].astype(np.float32) * m).astype(base.dtype)
        # Fluchtrichtung: aussen kippt staerker weg als die Mitte
        rel = (k - (n - 1) / 2.0) / max((n - 1) / 2.0, 1e-6)
        shards.append({
            'arr': piece,
            # v94: kraeftiger - Scherben fliegen weiter auseinander und kippen
            # staerker (vorher kaum sichtbar).
            'dx': rel * w * 0.060 + (float(rng.random()) - 0.5) * w * 0.020,
            'dy': (float(rng.random()) - 0.25) * h * 0.22,
            'rot': rel * 6.5 + (float(rng.random()) - 0.5) * 3.0,
        })
    return shards


def anim_apply(p, base, aud, dt):
    """Zentraler Einstieg fuer alle Animationen. Rechnet die Animation und legt
    danach die Bewegungsunschaerfe darueber: die Geschwindigkeit wird aus dem
    Unterschied zum letzten Frame gewonnen (kein zweiter Durchlauf, keine
    Extrakosten). Rueckgabe: (arr, dx, dy, scale_mul, opacity_mul)."""
    arr, dx, dy, sc, op = _anim_core(p, base, aud, dt)
    # Beat-/Stimm-Sync: Skalierung und Mikro-Hub haengen am Sprech-Onset, nicht
    # an einer festen Kurve. Text und Stimme treffen denselben Akzent - das ist
    # der Grund, warum teure Edits "auf den Punkt" wirken. Laeuft zentral, damit
    # es auf JEDER Animation greift (auch ohne anim).
    if BEAT_SYNC > 0 and base is not None:
        ons = float(aud[2]) if len(aud) > 2 else 0.0
        if ons < 0.15:
            ons = 0.0                         # Deadzone: Mikro-Rauschen bewegt nichts
        st = p.setdefault('_bs', 0.0)
        # Anstieg begrenzt (max +0.5/Frame): ein einzelner Spike kann den Text
        # nicht mehr anreissen, ein echter Akzent ueber 2 Frames schon.
        # v82: zeitbasiert statt frame-basiert - bei 60fps-Material verfiel der
        # Zustand doppelt so schnell, das Gefuehl haengt jetzt an Sekunden.
        pdt = p.get('_bs_t', dt)
        stp = dt - pdt if 0.0 < dt - pdt < 0.2 else (1.0 / 30.0)
        p['_bs_t'] = dt
        st = max(min(ons, st + 0.5 * stp * 30.0), st * (0.72 ** (stp * 30.0)))
        p['_bs'] = st
        sc *= 1.0 + 0.045 * BEAT_SYNC * st
        dy -= base.shape[0] * 0.012 * BEAT_SYNC * st   # weniger Hub -> kein Zucken
    a = p.get('anim')
    if not MOTION_BLUR or not a or base is None or a in _NO_BLUR:
        return arr, dx, dy, sc, op
    # Zustand pro Textbild (Tokens haben eigene Groessen -> eigener Schluessel).
    cache = p.setdefault('_vel', {})
    key = base.shape
    prev = cache.get(key)
    cache[key] = (dt, dx, dy, sc)
    if prev is not None:
        pdt, pdx, pdy, psc = prev
        step = dt - pdt
        if 0.0 < step < 0.2:
            w = base.shape[1]
            vx = dx - pdx
            vy = dy - pdy
            vy += (sc - psc) * base.shape[0] * 0.5      # Zoom zaehlt als Bewegung
            vx += (sc - psc) * w * 0.5
            arr = _motion_blur(arr, vx, vy)
    return arr, dx, dy, sc, op


_NO_BLUR = ('glitch', 'neon', 'schwund', 'enthuellen', 'fokus', 'gewicht')


def _anim_core(p, base, aud, dt):
    """Wendet die gewaehlte Animation auf ein Text-Bild an. Rueckgabe:
    (arr, dx, dy, scale_mul, opacity_mul) - die Zeichenpfade addieren die
    Offsets auf ihre eigenen Werte."""
    a = p.get('anim')
    if not a or base is None:
        return base, 0.0, 0.0, 1.0, 1.0
    a_rms, a_bass, a_onset = aud
    arr, dx, dy, sc, op = base, 0.0, 0.0, 1.0, 1.0
    rng = p.setdefault('_arng', np.random.default_rng(int(p['start'] * 977) & 0xffff))

    if a == 'glitch':                       # digitaler Riss auf harten Beats
        if a_onset > 0.5:
            arr = glitch_arr(base, rng, a_onset)
            dx = (float(rng.random()) - 0.5) * 10 * a_onset
    elif a == 'puls':                       # atmet auf dem Bass
        sc = 1.0 + 0.055 * a_bass
    elif a == 'welle':                      # Woge laeuft durch die Buchstaben
        h, w = base.shape[:2]
        ph = (dt * 2.4) % (2 * math.pi)
        amp = h * 0.05 * (0.45 + 0.55 * a_rms)
        ys = np.arange(h, dtype=np.float32)
        shift = amp * np.sin(ys / max(h, 1) * 6.0 + ph)
        xs = np.arange(w, dtype=np.float32)
        M = np.zeros((h, w, 2), np.float32)
        M[..., 0] = xs[None, :] + shift[:, None]
        M[..., 1] = ys[:, None]
        arr = cv2.remap(base, M, None, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    elif a == 'zittern':                    # nervoese Energie, Shake auf Onsets
        k = 0.35 + 0.65 * a_onset
        dx = (float(rng.random()) - 0.5) * 9 * k
        dy = (float(rng.random()) - 0.5) * 7 * k
    elif a == 'neon':                       # Leuchtreklame: glimmt und flackert
        f = 1.0
        if float(rng.random()) < 0.05:
            f = 0.4 + 0.4 * float(rng.random())
        op = f * (0.88 + 0.12 * a_rms)
        arr = base.copy()
        glow = cv2.GaussianBlur(base[..., :3].astype(np.float32), (0, 0), 6) \
            * (0.5 + 0.45 * a_rms)
        arr[..., :3] = np.clip(base[..., :3].astype(np.float32) * 0.85 + glow,
                               0, 255).astype(base.dtype)
    elif a == 'schub':                      # Druck nach vorn auf jedem Beat
        push = math.exp(-((dt * 6.0) % 4.0) * 1.6) * max(a_bass, 0.25)
        sc = 1.0 + 0.10 * push
        dy = -push * 12
    elif a == 'bruch':                      # das Wort zerbricht: Scherben kippen weg
        # Erst steht das Wort ganz (0.30 s), dann reisst es auf und die Scherben
        # driften minimal auseinander - lesbar bleibt es die ganze Zeit.
        prog = min(max((dt - 0.30) / 0.50, 0.0), 1.0)
        if prog > 0.001:
            h, w = base.shape[:2]
            pad_x, pad_y = int(w * 0.20) + 6, int(h * 0.34) + 6   # v94: mehr Platz fuer weiteren Flug
            key = (base.shape, id(base))
            cache = p.get('_bruch')
            if not cache or cache['shape'] != base.shape:
                cache = {'shape': base.shape,
                         'shards': _bruch_shards(base, rng)}
                p['_bruch'] = cache
            H2, W2 = h + 2 * pad_y, w + 2 * pad_x
            out = np.zeros((H2, W2, 4), base.dtype)
            e = prog * prog                  # beschleunigt: der Bruch gibt nach
            for sh in cache['shards']:
                M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), sh['rot'] * e, 1.0)
                M[0, 2] += pad_x + sh['dx'] * e
                M[1, 2] += pad_y + sh['dy'] * e + (h * 0.05) * e * e   # Schwerkraft
                warped = cv2.warpAffine(sh['arr'], M, (W2, H2),
                                        flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT,
                                        borderValue=(0, 0, 0, 0))
                np.maximum(out, warped, out=out)
            arr = out
    elif a == 'sturz':                      # faellt: Preise, Aktien, Umsatz, Absturz
        e = min(max(dt / 0.55, 0.0), 1.0) ** 2      # Schwerkraft: wird schneller
        h = base.shape[0]
        dy = h * 0.32 * e
        dx = -h * 0.05 * e
        arr = rot_img(base, -4.5 * e)
        op = 1.0 - 0.30 * e                 # sackt weg, bleibt aber lesbar
    elif a == 'anstieg':                    # steigt: Rekord, Gewinn, Zuwachs, Hoch
        e = ease_out(min(dt / 0.70, 1.0))
        dy = -base.shape[0] * 0.20 * e
        sc = 1.0 + 0.06 * e
    elif a == 'wende':                      # kippt um: Wende, Umkehr, Gegenteil
        # Echte 3D-Drehung um die Hochachse mit Fluchtpunkt: die nahe Kante wird
        # groesser, die ferne kleiner. Kommt lesbar zurueck - kein Spiegeltext.
        ang = math.sin(min(dt / 0.75, 1.0) * math.pi) * 1.05     # max ~60 Grad
        arr, _px, _py = _persp3d(base, 0.0, ang, 0.18)
    elif a == 'druck':                       # wird erdrueckt: Last, Zwang, Belastung
        sq = 0.10 * (0.55 + 0.45 * a_rms) * min(dt / 0.40, 1.0)
        h, w = base.shape[:2]
        arr = cv2.resize(base, (int(w * (1 + sq * 0.35)), max(int(h * (1 - sq)), 2)),
                         interpolation=cv2.INTER_LINEAR)
        dy = h * sq * 0.5                    # sinkt unter der Last nach unten
    elif a == 'schwund':                     # loest sich auf: weg, verloren, vorbei
        e = min(max((dt - 0.35) / 0.75, 0.0), 1.0)
        if e > 0.001:
            h, w = base.shape[:2]
            key = p.get('_schwund')
            if key is None or key.shape[:2] != (h, w):
                n = rng.random((h, w)).astype(np.float32)
                key = cv2.GaussianBlur(n, (0, 0), max(min(h, w) * 0.02, 1.0))
                key -= key.min()
                key /= max(float(key.max()), 1e-6)
                p['_schwund'] = key
            arr = base.copy()
            keep = np.clip((key - e * 1.15) * 6.0 + 0.5, 0.0, 1.0)   # loest sich fleckig
            arr[..., 3] = (base[..., 3].astype(np.float32)
                           * (0.42 + 0.58 * keep)).astype(base.dtype)
            dy = -base.shape[0] * 0.06 * e   # steigt leicht auf wie Rauch
    elif a == 'knall':                       # Punchline: knallt hin und federt aus
        # Feder statt Ease-Out: schiesst minimal ueber und pendelt sich ein.
        if dt < 0.75:
            e = spring(dt / 0.42, freq=2.6, damp=6.0)
            sc = 1.42 - 0.42 * e
            op = min(dt / 0.05, 1.0)
            if dt < 0.16:                    # Nachbeben nur im Aufschlag
                k = 1.0 - dt / 0.16
                dx = (float(rng.random()) - 0.5) * 8 * k
                dy = (float(rng.random()) - 0.5) * 6 * k

    # ---------------------------------------------------------------- Stand 2026
    elif a == 'gewicht':                     # Variable-Font-Achse: der Strich atmet
        # Statt das Wort zu skalieren (billig, springt), wird der Strich fetter.
        # Die Groesse bleibt, nur das Gewicht pumpt auf den Bass.
        pump = 0.35 + 0.65 * a_bass
        lad = p.get('_wladder')
        if lad and base is p.get('arr'):
            # Echte Variable-Font-Achse: der Schnitt wird wirklich fetter, die
            # Buchstabenform bleibt korrekt. Das ist der Unterschied zum
            # Dick-Rechnen - und die Signatur teurer Captions 2026.
            k = pump * min(dt / 0.20, 1.0)
            arr = lad[int(round(k * (len(lad) - 1)))]
        else:
            arr = _weight_morph(base, 0.9 * pump * min(dt / 0.20, 1.0))
        sc = 1.0 + 0.012 * pump              # kaum sichtbar, gibt nur Koerper

    elif a == 'schweben':                    # ruhige 3D-Drift: Premium-Grundton
        # Sehr dezent. Das Wort steht im Raum und atmet mit der Kamera mit -
        # das verkauft "hinter dem Objekt" als echte Tiefe statt als Aufkleber.
        ay = math.sin(dt * 0.85) * 0.10 + 0.05
        ax = math.sin(dt * 0.63 + 1.1) * 0.055
        arr, _px, _py = _persp3d(base, ax, ay, 0.10)
        dy = math.sin(dt * 0.72 + 2.0) * base.shape[0] * 0.022
        sc = 1.0 + 0.010 * math.sin(dt * 0.55)

    elif a == 'fokus':                       # Rack Focus: kommt scharf ins Bild
        # Der Klassiker aus dem Kino, in 2026 der Marker fuer teure Captions:
        # kein Zappeln, nur Schaerfe, die sich setzt.
        e = spring(min(dt / 0.38, 1.6), freq=1.8, damp=6.5)
        blur = (1.0 - min(e, 1.0)) * min(base.shape[0], base.shape[1]) * 0.09
        if blur > 0.6:
            arr = cv2.GaussianBlur(base, (0, 0), blur)
        sc = 1.055 - 0.055 * min(e, 1.0)
        op = min(dt / 0.10, 1.0)

    elif a == 'enthuellen':                  # weiche Kante wischt das Wort frei
        e = smoothstep(min(dt / 0.42, 1.0))
        if e < 0.999:
            h, w = base.shape[:2]
            xs = np.arange(w, dtype=np.float32)[None, :]
            edge = e * (w * 1.30) - w * 0.15
            soft = max(w * 0.13, 6.0)
            m = np.clip((edge - xs) / soft + 0.5, 0.0, 1.0)
            arr = base.copy()
            arr[..., 3] = (base[..., 3].astype(np.float32) * m).astype(base.dtype)
            # Heller Lichtsaum genau auf der Wischkante - das macht den Unterschied
            # zwischen "Maske" und "Reveal".
            lip = np.exp(-((xs - edge) / max(soft * 0.9, 1.0)) ** 2) * 0.55
            lit = np.clip(arr[..., :3].astype(np.float32) + 255.0 * lip[..., None], 0, 255)
            arr[..., :3] = lit.astype(base.dtype)
            dx = -(1.0 - e) * base.shape[1] * 0.035

    elif a == 'spur':                        # Nachzieher: Echos laufen hinterher
        # Das Wort schiesst herein, vier abklingende Echos bleiben kurz stehen.
        e = spring(min(dt / 0.50, 1.6), freq=2.2, damp=6.2)
        h, w = base.shape[:2]
        travel = w * 0.42 * (1.0 - min(e, 1.0))
        fade = max(1.0 - dt / 0.55, 0.0)
        if fade > 0.02 and travel > 0.8:
            pad = int(w * 0.55) + 6
            out = np.zeros((h, w + 2 * pad, 4), base.dtype)
            for i in range(4, 0, -1):
                off = min(max(pad + int(travel * i * 0.26), 0), 2 * pad)
                gh = base.copy()
                gh[..., 3] = (base[..., 3].astype(np.float32)
                              * fade * (0.30 - 0.06 * i)).astype(base.dtype)
                np.maximum(out[:, off:off + w], gh, out=out[:, off:off + w])
            np.maximum(out[:, pad:pad + w], base, out=out[:, pad:pad + w])
            arr = out
        dx = travel
        op = min(dt / 0.06, 1.0)

    # ---------------------------------------------------------------- v71
    elif a == 'kippen':                       # Wort kippt nach vorn wie ein Buch das aufklappt
        # Tilt um X-Achse: obere Kante entfernt sich, untere kommt entgegen.
        # Federt aus, bleibt stehen. Kein Wackeln danach.
        e = spring(min(dt / 0.50, 1.4), freq=2.1, damp=6.0)
        tilt = -0.85 * (1.0 - min(e, 1.0))    # startet stark tilted, geht auf 0
        arr, _px, _py = _persp3d(base, 0.0, tilt, 0.14)
        op = min(dt / 0.06, 1.0)

    elif a == 'explosion':                    # radialer Aufschlag: Streifen fliegen weg + zurueck
        # v82: Physik statt Dreieck - Dinge explodieren SCHNELL (ease_out
        # 0.12s), der Rueckzug federt ein und schiesst 6% ueber die Ruhelage
        # (Recoil). Konstante Geschwindigkeit war physikalisch tot.
        if dt < 0.12:
            spread = ease_out(dt / 0.12)
        else:
            spread = max(1.0 - spring(min((dt - 0.12) / 0.43, 1.4),
                                      freq=2.2, damp=5.0), -0.06)
        if abs(spread) > 0.02:
            h, w = base.shape[:2]
            n_col = 8                          # 8 vertikale Streifen
            cw = max(w // n_col, 6)
            # v94: dramatischer - Streifen fliegen deutlich weiter (0.22 -> 0.48)
            # und driften zusaetzlich vertikal auseinander (echter 2D-Aufschlag).
            padx = int(w * 0.50) + 6
            pady = int(h * 0.30) + 6
            out = np.zeros((h + 2 * pady, w + 2 * padx, 4), base.dtype)
            for i in range(n_col):
                x0 = i * cw
                x1 = min(x0 + cw, w)
                if x1 <= x0:
                    continue
                seg = base[:, x0:x1]
                cx = (x0 + x1) / 2 - w / 2
                dx_s = int(cx / (w / 2) * (w * 0.48) * spread)
                # aeussere Streifen fliegen auch nach oben/unten weg
                dy_s = int((abs(cx) / (w / 2)) * (h * 0.22) * spread
                           * (1 if i % 2 else -1))
                dst_x = padx + x0 + dx_s
                dst_y = pady + dy_s
                if 0 <= dst_x <= w + 2 * padx - (x1 - x0) and 0 <= dst_y <= h + 2 * pady - h:
                    np.maximum(out[dst_y:dst_y + h, dst_x:dst_x + (x1 - x0)], seg,
                               out=out[dst_y:dst_y + h, dst_x:dst_x + (x1 - x0)])
            arr = out
        sc = 1.0 + 0.22 * max(spread, 0.0)     # Scale-Pop beim Aufschlag
        op = min(dt / 0.05, 1.0)

    elif a == 'magnet':                       # umgekehrte Explosion: aus Streuung zusammenziehen
        # v82: Magnete ziehen staerker je naeher - die Teile BESCHLEUNIGEN ins
        # Zentrum (1-x^2) statt linear zu schrumpfen, und landen mit einem
        # 1-Frame-Squash wenn alles einrastet.
        xm = min(dt / 0.55, 1.0)
        e = 1.0 - xm * xm
        if 0.55 <= dt < 0.62:
            sc = 1.0 - 0.03 * math.sin((dt - 0.55) / 0.07 * math.pi)
        if e > 0.02:
            h, w = base.shape[:2]
            n_col = 8
            cw = max(w // n_col, 6)
            pad = int(w * 0.30) + 6
            out = np.zeros((h, w + 2 * pad, 4), base.dtype)
            for i in range(n_col):
                x0 = i * cw
                x1 = min(x0 + cw, w)
                seg = base[:, x0:x1]
                cx = (x0 + x1) / 2 - w / 2
                dx_s = int(cx / (w / 2) * (w * 0.28) * e)
                dst_x = pad + x0 + dx_s
                dst_x = max(0, min(dst_x, w + 2 * pad - (x1 - x0)))
                # Opacity waechst waehrend Zusammenzug (aus Nichts kommend)
                alpha_mul = 1.0 - e * 0.7
                gh = seg.copy()
                gh[..., 3] = np.clip(seg[..., 3].astype(np.float32) * alpha_mul,
                                     0, 255).astype(base.dtype)
                np.maximum(out[:, dst_x:dst_x + (x1 - x0)], gh,
                           out=out[:, dst_x:dst_x + (x1 - x0)])
            arr = out
        op = 1.0

    elif a == 'wackel':                       # Cartoon-Wackel: vertikaler Sinus-Loop
        # Loopfaehig, kein Ende. Amplitude wird von der Stimme moduliert.
        # v82: zweiter Sinus (1.7x Frequenz, 30% Amplitude, Wort-eigene Phase)
        # - ein nackter Einzelsinus ist als synthetisch erkennbar.
        amp = base.shape[0] * (0.020 + 0.015 * a_rms)
        ph = math.pi * hand_jitter(p.get('kw_i', 0))
        dy = amp * (math.sin(dt * 12.0) + 0.30 * math.sin(dt * 20.4 + ph))
        sc = 1.0 + 0.015 * math.sin(dt * 12.0 + math.pi / 2)

    elif a == 'regen':                        # Buchstaben-Streifen fallen von oben nacheinander
        h, w = base.shape[:2]
        n_col = max(int(w / 34), 4)
        cw = max(w // n_col, 6)
        pad_y = int(h * 0.55) + 8
        out = np.zeros((h + pad_y, w, 4), base.dtype)
        for i in range(n_col):
            x0 = i * cw
            x1 = min(x0 + cw, w)
            # gestaffelt: linke Streifen zuerst fertig
            offset = 0.05 * i
            e = ease_out(min(max((dt - offset) / 0.55, 0.0), 1.0))
            y_off = int((1.0 - e) * pad_y)
            if e <= 0.001:
                continue
            seg = base[:, x0:x1]
            alpha_mul = e
            gh = seg.copy()
            gh[..., 3] = np.clip(seg[..., 3].astype(np.float32) * alpha_mul,
                                 0, 255).astype(base.dtype)
            np.maximum(out[y_off:y_off + h, x0:x1], gh,
                       out=out[y_off:y_off + h, x0:x1])
        arr = out
        dy = 0.0

    elif a == 'zoom_punch':                   # kurzer harter Skalen-Push mit Nachschwingen
        # Reisst rein bis 1.25, federt auf 1.0. Sehr kurz, sitzt genau auf Onset.
        # Explizite Kurve statt spring: startet bei 1.25, sinkt smooth zu 1.0.
        if dt < 0.55:
            e = min(dt / 0.28, 1.0)
            sc = 1.0 + 0.25 * (1.0 - e) ** 2   # quadratisch: bleibt oben, faellt spaet
            op = min(dt / 0.04, 1.0)
        else:
            sc = 1.0

    elif a == 'rutsche':                      # Streifen rutschen einzeln von rechts rein
        h, w = base.shape[:2]
        n_col = max(int(w / 34), 4)
        cw = max(w // n_col, 6)
        pad_x = int(w * 0.45) + 8
        out = np.zeros((h, w + pad_x, 4), base.dtype)
        for i in range(n_col):
            x0 = i * cw
            x1 = min(x0 + cw, w)
            # gestaffelt: linke zuerst
            offset = 0.06 * i
            e = ease_out(min(max((dt - offset) / 0.45, 0.0), 1.0))
            x_off = int((1.0 - e) * pad_x)
            if e <= 0.001:
                continue
            seg = base[:, x0:x1]
            gh = seg.copy()
            gh[..., 3] = np.clip(seg[..., 3].astype(np.float32) * e,
                                 0, 255).astype(base.dtype)
            dst_x = x0 + x_off
            np.maximum(out[:, dst_x:dst_x + (x1 - x0)], gh,
                       out=out[:, dst_x:dst_x + (x1 - x0)])
        arr = out
        dx = 0.0

    elif a == 'stempel':                       # knallt drauf wie ein Stempel: fetter Rand-Blur am Aufschlag
        # 0..0.18: kommt aus 1.8x rein (Vergroesserung des ganzen Bildes) und
        # verwischt weich (Motion-Streaks). Ab 0.18 steht es scharf.
        if dt < 0.18:
            e = min(dt / 0.18, 1.0)
            sc = 1.8 - 0.8 * e                # von 1.8 auf 1.0
            # Aufprall-Unschaerfe: Gaussian verschmilzt Kanten kurz.
            blur_sig = (1.0 - e) * max(base.shape[0], base.shape[1]) * 0.020
            if blur_sig > 0.6:
                arr = cv2.GaussianBlur(base, (0, 0), blur_sig)
            op = min(dt / 0.03, 1.0)
        elif dt < 0.28:
            # Kurzes Nachbeben - Aufschlag stanzt
            k = 1.0 - (dt - 0.18) / 0.10
            dy = -base.shape[0] * 0.008 * k
            sc = 1.0 + 0.03 * k
    return arr, dx, dy, sc, op


# ---------------------------------------------------------------- transcription
def transcribe(audio_path, language, cfg=None):
    """Transkription ueber OpenAI Whisper API (whisper-1). Beste Qualitaet
    bei Namen/Fachbegriffen, laeuft ueber Ismets lokalen OPENAI_API_KEY.
    Der Signatur-Parameter `cfg` bleibt fuer Kompatibilitaet - wird nicht
    mehr ausgewertet."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        sys.exit("FEHLER: Umgebungsvariable OPENAI_API_KEY ist nicht gesetzt.")
    print("Transkribiere ueber Sprach-KI...")
    try:
        with open(audio_path, 'rb') as f:
            r = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {key}'},
                data={'model': 'whisper-1', 'response_format': 'verbose_json',
                      'timestamp_granularities[]': ['word', 'segment'],
                      **({} if language == 'auto' else {'language': language})},
                files={'file': (os.path.basename(audio_path), f, 'audio/mp4')},
                timeout=600)
    except requests.exceptions.Timeout:
        sys.exit("FEHLER: Sprach-KI antwortet zu langsam. "
                 "Bitte in 2-3 Minuten erneut versuchen.")
    except requests.exceptions.ConnectionError:
        sys.exit("FEHLER: Keine Verbindung zur Sprach-KI. "
                 "Internet pruefen oder in ein paar Minuten erneut versuchen.")
    if r.status_code == 401:
        sys.exit("FEHLER: KI-Zugang ungueltig. Support kontaktieren.")
    if r.status_code == 429:
        sys.exit("FEHLER: KI-Dienst ueberlastet. "
                 "Bitte in 5 Minuten erneut versuchen.")
    if r.status_code == 413:
        sys.exit("FEHLER: Audio-Spur zu gross. Kuerzeres Video versuchen.")
    if 500 <= r.status_code < 600:
        sys.exit(f"FEHLER: KI-Dienst-Problem (HTTP {r.status_code}). "
                 f"Bitte in ein paar Minuten erneut versuchen.")
    r.raise_for_status()
    data = r.json()
    words = [{'word': w['word'].strip(), 'start': round(w['start'], 3), 'end': round(w['end'], 3)}
             for w in data.get('words', [])]
    if not words:
        sys.exit("FEHLER: Keine Woerter in der Transkription. Hat das Video eine Tonspur?")
    return attach_punctuation(words, data.get('segments') or [])


def attach_punctuation(words, segments):
    """Whisper liefert Satzzeichen nur auf Segment-Ebene. Hier werden sie den
    Woertern wieder angeheftet, damit Satzgrenzen fuer die Gruppierung sichtbar sind."""
    def core(s):
        return ''.join(ch for ch in s.lower() if ch.isalnum())
    tokens = []
    for seg in segments:
        tokens.extend(str(seg.get('text', '')).split())
    ti = 0
    for w in words:
        cw = core(w['word'])
        if not cw:
            continue
        for look in range(ti, min(ti + 4, len(tokens))):
            if core(tokens[look]) == cw:
                w['word'] = tokens[look]
                ti = look + 1
                break
    return words

def refine_word_times(words, voice_wav):
    """Zieht jeden Wort-Start auf den echten Sprech-Einsatz im Audio (Onset-Analyse).
    Whisper-Timestamps sind oft 50-150 ms daneben - das hier macht die Captions synchron."""
    try:
        import sfx_engine
        voice = sfx_engine.load_wav(voice_wav)
        env, hop = sfx_engine._energy(voice)
    except Exception:
        return words, 0.0
    SR = 44100
    shifts = []
    prev_start = -1.0
    for w in words:
        t = w['start']
        a = max(int((t - 0.12) * SR / hop), 1)
        b = min(int((t + 0.16) * SR / hop), len(env) - 1)
        if b - a < 4:
            continue
        d = np.diff(env[a:b])
        k = int(np.argmax(d))
        if d[k] < 1e-4:
            continue
        t_new = (a + k + 1) * hop / SR
        t_new = max(t_new, prev_start + 0.02)
        shifts.append(t_new - t)
        dur = w['end'] - w['start']
        w['start'] = round(t_new, 3)
        w['end'] = round(t_new + dur, 3)
        prev_start = t_new
    # Enden duerfen den naechsten Start nicht ueberholen
    for i in range(len(words) - 1):
        words[i]['end'] = min(words[i]['end'], words[i + 1]['start'])
    avg = float(np.mean(np.abs(shifts))) * 1000 if shifts else 0.0
    return words, avg

def scene_palette_sampler(video_path, cut_times=None):
    """Liefert palette_at(t, region): tastet den Frame zum Zeitpunkt t per ffmpeg ab
    (robust bei HEVC/VFR, wo cv2-Seeks scheitern) und leitet Caption-Farben ab,
    die sich der Umgebung anpassen (Referenz-Look): Text = dominanter Szenenton,
    stark entsaettigt und fast auf Weiss gehoben (nie #FFFFFF), Akzent = leuchtende
    Version desselben Tons. region='unten' sampelt den Untergrund (Wasser/Boden),
    auf dem ground-Texte liegen, statt Himmel und Felsen mitzumitteln.

    v86: Farbwelt pro SHOT, nicht pro Sekunde. Vorher war der Cache auf int(t)
    gekeyt - zwei Captions 0.4s auseinander ueber eine Sekundengrenze bekamen aus
    DERSELBEN Einstellung leicht verschiedene Toene (sichtbarer Tint-Sprung, ohne
    dass sich das Bild aenderte). Jetzt teilen sich alle Captions eines Shots
    exakt eine Farbe (Cache-Key = Shot-Index). Sehr lange Shots duerfen alle 6s
    langsam nachziehen, damit Licht-Drift im Dauer-Take nicht einfriert."""
    cache = {}
    bounds = sorted(float(c) for c in (cut_times or []))

    def _shot_bucket(t):
        # Index des Shots, in dem t liegt (Anzahl Schnitte davor) + grober
        # 6s-Unterbucket fuer sehr lange Einstellungen.
        import bisect
        idx = bisect.bisect_right(bounds, t)
        shot_start = bounds[idx - 1] if idx > 0 else 0.0
        return (idx, int((t - shot_start) / 6.0))

    def palette_at(t, region='mitte'):
        key = (_shot_bucket(t), region)
        if key in cache:
            return cache[key]
        try:
            r = subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', str(max(t, 0.0)), '-i', video_path,
                 '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                 '-s', '96x96', '-'],
                capture_output=True, timeout=20)
            if len(r.stdout) < 96 * 96 * 3:
                raise ValueError('kein Frame')
            small = np.frombuffer(r.stdout[:96 * 96 * 3],
                                  dtype=np.uint8).reshape(96, 96, 3)
            if region == 'unten':
                small = small[52:, :]         # Untergrund: Wasser, Boden, Strasse
            else:
                small = small[18:82, :]       # Bildmitte ohne Himmel-/Bodenraender
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
            sel = (hsv[:, 1] > 40) & (hsv[:, 2] > 50)
            src = hsv[sel] if sel.sum() > hsv.shape[0] * 0.08 else hsv
            hue = float(np.median(src[:, 0]))
            sat = float(np.median(src[:, 1])) / 255.0
            t_sat = int(255 * min(0.08 + sat * 0.16, 0.22))
            text = cv2.cvtColor(np.uint8([[[hue, t_sat, 246]]]),
                                cv2.COLOR_HSV2RGB)[0, 0]
            accent = cv2.cvtColor(np.uint8([[[hue, int(255 * 0.55), 255]]]),
                                  cv2.COLOR_HSV2RGB)[0, 0]
            out = (tuple(int(c) for c in text), tuple(int(c) for c in accent))
        except Exception:
            out = None                        # Aufrufer faellt auf Config-Farben zurueck
        cache[key] = out
        return out

    return palette_at

def _frame_b64(video_path, t, width=480, quality=72):
    """Holt einen Frame als Base64-JPEG fuer die Vision-Regie (klein und guenstig)."""
    import base64
    r = subprocess.run(
        ['ffmpeg', '-v', 'error', '-ss', str(max(t, 0.0)), '-i', video_path,
         '-frames:v', '1', '-vf', f'scale={width}:-2',
         '-f', 'image2', '-c:v', 'mjpeg', '-q:v', str(max(2, int(31 - quality / 3.5))), '-'],
        capture_output=True, timeout=20)
    if len(r.stdout) < 500:
        return None
    return base64.b64encode(r.stdout).decode('ascii')

SZENE_PROMPT = """Du bist der visuelle Regisseur fuer Premium-Captions. Du siehst pro \
Moment einen Frame des Videos plus den Text, der dort erscheint. Entscheide fuer jeden \
Moment, wie der Text zur UMGEBUNG gehoert:

- "szene": was dominiert dort, wo der Text hin soll? \
"wasser" | "boden" (Strasse, Sand, Gras, Tisch) | "wand" (Fels, Gebaeude, Flaeche) | \
"himmel" | "person" (Sprecher im Bild) | "unklar"
- "lage": wie soll der Text in der Szene liegen? \
"liegend" = flach AUF der Flaeche (Wasser/Boden), wird Teil des Materials. \
"stehend" = aufrecht IN der Szene mit Spiegelung/Gewicht. \
"frei" = klassisches Overlay (Person im Bild, unruhiger Hintergrund).
- Optional "fx": NUR wenn der Frame einen anderen Effekt verlangt als geplant \
(z.B. geplant "behind", aber keine Person im Bild -> "ground").
- LOHNT SICH "behind" HIER? "behind" legt den Text HINTER die Person und dimmt \
ihn. Das wirkt nur, wenn RUND um die Person genug freie Flaeche ist. Fuellt die \
Person das Bild fast aus (Nahaufnahme, ganz nah an der Kamera - im Text steht \
dann ein hoher Prozentwert "Person ~X% der Breite"), bleibt vom Text hinter ihr \
kaum etwas sichtbar. Entscheide dann bewusst UM auf eine sichtbare Platzierung \
("outline"/"cascade" vorne, oder "ground" als grosses Statement). Ist reichlich \
Hintergrund frei, darf "behind" bleiben. Du entscheidest pro Frame - es ist kein \
Zwang, nur: verschenke keinen Moment hinter einem Gesicht, das alles verdeckt.

Regeln: Wasser/Boden gross im Bild + grosser Moment -> "liegend". Klare Flaeche im \
Mittelgrund -> "stehend". Sprecher-Nahaufnahme -> "frei". Im Zweifel "frei".
Antworte NUR mit JSON: {"momente": [{"i": <Index>, "szene": "...", "lage": "...", "fx": "<optional>"}]}"""

def _oai_json(model, messages, max_toks, temperature, json_mode=True):
    """v94: chat/completions-Body, modell-kompatibel. Neuere Modelle (gpt-5,
    o-Serie) verlangen max_completion_tokens und lehnen ein abweichendes
    temperature ab; gpt-4o akzeptiert beides. Ohne das faellt ein neues Modell
    still auf die Heuristik zurueck.
    v96t: json_mode=False fuer PROSA-Antworten (Stil-Lernen). Mit
    response_format=json_object verlangt OpenAI das Wort "json" im Prompt und
    erzwingt JSON - ein Prosa-Prompt scheitert dann mit 400."""
    new = str(model).startswith(('gpt-5', 'o1', 'o3', 'o4'))
    body = {'model': model, 'messages': messages}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    body['max_completion_tokens' if new else 'max_tokens'] = max_toks
    if not new:
        body['temperature'] = temperature
    return body


def ai_scene_direct(words, fx_map, video_path, model='gpt-4o', min_power=2,
                    face_cover=None):
    """Regie v4 (Vision): schaut sich pro gewaehltem Moment einen Frame an und
    entscheidet Material ('szene') und Lage ('liegend'/'stehend'/'frei').
    Ergaenzt fx_map in-place. Faellt bei jedem Fehler lautlos auf Text-Regie zurueck.

    v80e: min_power (Default 2) filtert billige power=1-Momente raus. Die kriegen
    keine Vision-Analyse - fuer die reicht Text-Regie. Spart 60% Vision-Kosten.
    v95c: face_cover {index: Gesichts-Breitenanteil 0..1} - die KI bekommt pro
    Moment, wie sehr die Person das Bild fuellt, und entscheidet, ob 'behind'
    (hinter der Person) ueberhaupt sichtbar waere. Zusaetzlich ein konservativer
    Backstop bei extremer Nahaufnahme (schuetzt auch den Kein-Vision-Pfad)."""
    import requests
    face_cover = face_cover or {}
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not fx_map:
        return _behind_cover_backstop(fx_map, face_cover)
    idx = [i for i in sorted(fx_map)
           if int(fx_map[i].get('power', 2)) >= min_power][:24]
    if not idx:
        return _behind_cover_backstop(fx_map, face_cover)
    content = []
    sent = []
    for i in idx:
        b64 = _frame_b64(video_path, words[i]['start'] + 0.15)
        if not b64:
            continue
        txt = ' '.join(clean(words[j]['word'])
                       for j in range(i, min(i + fx_map[i].get('n', 1), len(words))))
        cov = face_cover.get(i)
        cov_txt = f" Person ~{int(cov * 100)}% der Breite." if cov else ''
        content.append({'type': 'text',
                        'text': f"MOMENT [{i}] Text: \"{txt}\" "
                                f"geplant: {fx_map[i].get('fx')}.{cov_txt}"})
        content.append({'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b64}',
                                      'detail': 'low'}})
        sent.append(i)
    if not sent:
        return fx_map
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}'},
            json=_oai_json(model,
                           [{'role': 'system', 'content': SZENE_PROMPT},
                            {'role': 'user', 'content': content}],
                           max_toks=1500, temperature=0.1),
            timeout=180)
        r.raise_for_status()
        data = json.loads(r.json()['choices'][0]['message']['content'])
        n_v = 0
        for m in data.get('momente', []):
            i = int(m.get('i', -1))
            if i not in fx_map:
                continue
            sz = str(m.get('szene', '')).strip().lower()
            lg = str(m.get('lage', '')).strip().lower()
            if sz in ('wasser', 'boden', 'wand', 'himmel', 'person', 'unklar'):
                fx_map[i]['szene'] = sz
            if lg in ('liegend', 'stehend', 'frei'):
                fx_map[i]['lage'] = lg
            fxo = str(m.get('fx', '')).strip().lower()
            if fxo in ('behind', 'cascade', 'blurin', 'outline', 'ground'):
                fx_map[i]['fx'] = fxo
            n_v += 1
        print(f"Vision-Regie: {n_v} Momente an die Umgebung angepasst")
    except Exception as e:
        print(f"Vision-Regie nicht verfuegbar ({type(e).__name__}), Text-Regie bleibt.")
    return _behind_cover_backstop(fx_map, face_cover)


def _behind_cover_backstop(fx_map, face_cover, thresh=0.52):
    """v95c: Sicherheitsnetz gegen unsichtbares 'behind'. Fuellt die Person das
    Bild fast aus (Gesichts-Breite >= thresh der Bildbreite = ganz nah an der
    Kamera), sieht man vom gedimmten Text hinter ihr praktisch nichts. Dann auf
    eine sichtbare Platzierung wechseln. Konservativ (nur extreme Nahaufnahmen),
    damit es die feinere KI-Entscheidung nicht ueberstimmt - und es greift auch,
    wenn gar keine Vision-KI lief (kein Key)."""
    if not fx_map or not face_cover:
        return fx_map
    moved = 0
    for i, v in fx_map.items():
        if v.get('fx') != 'behind':
            continue
        if face_cover.get(i, 0.0) >= thresh:
            # Grosses Statement -> ground, sonst klar sichtbares outline.
            v['fx'] = 'ground' if int(v.get('power', 2)) >= 3 else 'outline'
            moved += 1
    if moved:
        print(f"  Sichtbarkeit: {moved} 'behind' bei Nahaufnahme -> nach vorn")
    return fx_map

def persp_warp(arr, yaw=0.0, pitch=0.0):
    """Legt eine leichte 3D-Perspektive auf ein Sprite.
    yaw: Drehung um die Hochachse (Grad, + = rechte Seite kippt nach hinten).
    pitch: 'liegt am Boden'-Look (0..1, staerker = flacher in die Szene gelegt)."""
    if abs(yaw) < 0.1 and pitch <= 0:
        return arr
    h, w = arr.shape[:2]
    m = int(w * 0.12) + 20
    big = cv2.copyMakeBorder(arr, m, m, m, m, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    H2, W2 = big.shape[:2]
    src_q = np.float32([[m, m], [m + w, m], [m + w, m + h], [m, m + h]])
    ky = abs(yaw) / 90.0
    if yaw > 0:
        dst_q = np.float32([[m, m], [m + w * (1 - ky * 0.4), m + h * ky * 0.9],
                            [m + w * (1 - ky * 0.4), m + h * (1 - ky * 0.9)], [m, m + h]])
    elif yaw < 0:
        dst_q = np.float32([[m + w * ky * 0.4, m + h * ky * 0.9], [m + w, m],
                            [m + w, m + h], [m + w * ky * 0.4, m + h * (1 - ky * 0.9)]])
    else:
        dst_q = src_q.copy()
    if pitch > 0:
        sq = pitch * 0.55
        kx = pitch * 0.18
        dst_q[0][0] += w * kx; dst_q[0][1] += h * sq
        dst_q[1][0] -= w * kx; dst_q[1][1] += h * sq
    M = cv2.getPerspectiveTransform(src_q, dst_q)
    return cv2.warpPerspective(big, M, (W2, H2), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

def make_contact_shadow(arr, strength=0.42):
    """Weicher Kontakt-Schatten unter dem Text: verkauft, dass der Text WIRKLICH
    auf dem Untergrund steht. Breite folgt der Alpha-Verteilung der Unterkante."""
    a = arr[..., 3]
    ys, xs = np.where(a > 8)
    if len(ys) < 10:
        return None, 0.0, 0.0
    y1 = int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    w = max(x1 - x0, 8)
    sh_h = max(int(w * 0.055), 10)
    sh = np.zeros((sh_h, int(w * 1.10), 4), dtype=np.float32)
    yy, xx = np.mgrid[0:sh.shape[0], 0:sh.shape[1]]
    cx_, cy_ = sh.shape[1] / 2.0, sh.shape[0] / 2.0
    d2 = ((xx - cx_) / (sh.shape[1] * 0.46)) ** 2 + ((yy - cy_) / (sh.shape[0] * 0.55)) ** 2
    sh[..., 3] = np.clip(1.0 - d2, 0, 1) ** 1.6 * 255 * strength
    sh = cv2.GaussianBlur(sh, (0, 0), sh_h * 0.28)
    dy = float(y1 - arr.shape[0] / 2.0)
    dx = float((x0 + x1) / 2.0 - arr.shape[1] / 2.0)
    return sh, dy, dx

def make_reflection(arr, squash=0.55, strength=0.35):
    """Wasser-/Boden-Spiegelung eines Sprites: eng beschnitten, vertikal gespiegelt
    und gestaucht, weichgezeichnet, nach unten auslaufende Deckkraft.
    Gibt (Sprite, dy, dx) zurueck - Versatz der Textunterkante relativ zum
    Sprite-Zentrum, damit die Spiegelung buendig unter dem Text sitzt."""
    arr = np.asarray(arr)
    a = arr[..., 3]
    ys, xs = np.where(a > 8)
    if len(ys) < 10:
        return None, 0.0, 0.0
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    tight = np.ascontiguousarray(arr[y0:y1, x0:x1])
    ref = cv2.flip(tight, 0)
    hh = max(int(ref.shape[0] * squash), 2)
    ref = cv2.resize(ref, (ref.shape[1], hh), interpolation=cv2.INTER_AREA)
    ref = cv2.GaussianBlur(ref, (0, 0), 2.2).astype(np.float32)
    ramp = np.linspace(strength, 0.0, hh, dtype=np.float32) ** 1.25
    ref[..., 3] = ref[..., 3] * ramp[:, None]
    dy = float(y1 - arr.shape[0] / 2.0)
    dx = float((x0 + x1) / 2.0 - arr.shape[1] / 2.0)
    return ref, dy, dx

# ---------------------------------------------------------------- face tracking
def _faces_tracks(dets_seq, max_d):
    """v96 (Multi-Person): ordnet die Gesichter aufeinanderfolgender Frames zu
    stabilen Personen-Spuren (greedy Nearest-Neighbor ueber den Mittelpunkt) und
    summiert pro Spur die Mund-Bewegung. Rein & deterministisch (testbar).
    dets_seq[i] = Liste von [cx, cy, w, motion] pro Frame.
    Rueckgabe: (track_of, track_motion)
      track_of[i][j]   = Spur-ID des j-ten Gesichts in Frame i
      track_motion[id] = aufsummierte Mund-Bewegung dieser Spur."""
    track_of = []
    track_motion = {}
    prev = []                      # (track_id, cx, cy) der letzten belegten Spuren
    next_id = 0
    for faces in dets_seq:
        row = []
        used_prev = set()
        for f in faces:
            cx, cy = f[0], f[1]
            best, best_d = None, max_d
            for pi, (tid, px, py) in enumerate(prev):
                if pi in used_prev:
                    continue
                d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                if d < best_d:
                    best, best_d, best_pi = tid, d, pi
            if best is None:
                best = next_id
                next_id += 1
            else:
                used_prev.add(best_pi)
            row.append(best)
            track_motion[best] = track_motion.get(best, 0.0) + (f[3] if len(f) > 3 else 0.0)
        track_of.append(row)
        prev = [(row[j], faces[j][0], faces[j][1]) for j in range(len(faces))]
    return track_of, track_motion


def _smooth_tracks(dets_seq, track_of, hold=6, min_len=2):
    """v96c: macht die Gesichts-Spuren robust gegen weggedrehte Koepfe. Ein
    Gesicht, das kurz zur Seite/weg schaut, wird ein paar Frames NICHT erkannt -
    ohne Ausgleich vergisst die Safe-Zone die Person und der Text springt auf
    sie. Hier werden (a) Luecken innerhalb einer Spur interpoliert, (b) die Box
    vor der ersten / nach der letzten Detektion kurz gehalten und (c) Spuren, die
    zu selten auftauchen (Spuk-Fehldetektion durch niedrige Confidence), ganz
    verworfen. Rein & testbar.
    Rueckgabe: (boxes, tids) - je Frame Liste der (cx,cy,w) bzw. Spur-IDs."""
    n = len(dets_seq)
    seen = {}
    for i in range(n):
        for j, f in enumerate(dets_seq[i]):
            seen.setdefault(track_of[i][j], {})[i] = list(f[:3])
    boxes = [[] for _ in range(n)]
    tids = [[] for _ in range(n)]
    for tid, fr in seen.items():
        if len(fr) < min_len:
            continue                         # zu selten -> Fehldetektion, weg
        keys = sorted(fr)
        for i in keys:
            boxes[i].append(fr[i]); tids[i].append(tid)
        for a, b in zip(keys, keys[1:]):     # Luecken interpolieren
            gap = b - a
            if 1 < gap <= 2 * hold + 1:
                for i in range(a + 1, b):
                    t = (i - a) / gap
                    boxes[i].append([fr[a][k] + (fr[b][k] - fr[a][k]) * t
                                     for k in range(3)])
                    tids[i].append(tid)
        first, last = keys[0], keys[-1]      # Raender kurz halten
        for i in range(max(0, first - hold), first):
            boxes[i].append(list(fr[first])); tids[i].append(tid)
        for i in range(last + 1, min(last + 1 + hold, n)):
            boxes[i].append(list(fr[last])); tids[i].append(tid)
    return boxes, tids


def _active_index(faces, tids, track_motion):
    """Waehlt das AKTIVE (sprechende) Gesicht eines Frames: die Spur mit der
    meisten Mund-Bewegung. Ist die Bewegung ueberall ~0 (kein klarer Sprecher),
    faellt es auf das groesste Gesicht zurueck. Rein & testbar.
    faces[j] = [cx, cy, w, ...], tids[j] = Spur-ID von faces[j]."""
    if not faces:
        return -1
    mots = [track_motion.get(tids[j], 0.0) for j in range(len(faces))]
    mx = max(mots)
    if mx > 1.5:                                   # klare Mund-Bewegung vorhanden
        return int(max(range(len(faces)), key=lambda j: mots[j]))
    return int(max(range(len(faces)), key=lambda j: faces[j][2]))   # sonst groesstes


def _free_x_multi(faces, W, sprite_w, toggle):
    """v96: Text-Mittelpunkt im Querformat, der KEIN Gesicht ueberdeckt - auch
    wenn mehrere Personen im Bild sind. Sucht die breiteste freie Luecke (links
    der linkesten Person, zwischen zwei Personen, rechts der rechtesten) und legt
    den Text dorthin, sofern der Sprite hineinpasst. Findet sich keine Luecke,
    kommt der Text auf die Seite mit dem meisten Rand. Rein & testbar.
    faces = Liste (cx, w) in Bild-Pixeln. Rueckgabe: (side -1/1, cx)."""
    m = W * 0.045
    half = sprite_w / 2.0
    if not faces:
        cx = W * 0.224 if toggle % 2 == 0 else W * 0.766
        return (-1 if cx < W / 2 else 1), cx
    # Belegte Intervalle (Person + Sicherheitsabstand), sortiert. Faktor 1.9:
    # der Koerper/die Schultern sind deutlich breiter als die Gesichtsbox - v.a.
    # bei zur Seite gedrehten Personen. Lieber etwas grosszuegig sperren, damit
    # der Text niemanden anschneidet.
    occ = sorted((max(cx - w * 1.9, 0), min(cx + w * 1.9, W)) for cx, w in faces)
    # Freie Luecken zwischen den belegten Intervallen (inkl. Raender)
    gaps = []
    cursor = m
    for a, b in occ:
        if a - cursor > 0:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if W - m - cursor > 0:
        gaps.append((cursor, W - m))
    # Luecken, in die der Text passt - die breiteste gewinnt
    fit = [(a, b) for a, b in gaps if (b - a) >= sprite_w]
    if fit:
        a, b = max(fit, key=lambda g: g[1] - g[0])
        cx = (a + b) / 2.0
    elif gaps:
        a, b = max(gaps, key=lambda g: g[1] - g[0])
        cx = min(max((a + b) / 2.0, m + half), W - m - half)
    else:
        cx = W / 2.0
    return (-1 if cx < W / 2 else 1), cx


_CUT_SESS = None


def _person_cutout_png(frame_path, out_png):
    """v96h: Personen-Freistellung eines EINZELNEN Frames als RGBA-PNG (Person
    deckend, Rest transparent) - fuer die Momente-Editor-Vorschau, damit 'behind'
    dort wirklich HINTER der Person sitzt. Nutzt dieselbe RVM-Matte wie der
    Render, auf ein Bild angewandt (Recurrent-State = 0). Lazy, fehlertolerant:
    fehlt onnxruntime/Modell, gibt es einfach kein Cutout (Vorschau bleibt flach)."""
    global _CUT_SESS
    if _CUT_SESS is False:
        return False
    try:
        if _CUT_SESS is None:
            import onnxruntime as ort
            mp = os.path.join(HERE, 'models/rvm.onnx')
            if not os.path.exists(mp):
                _CUT_SESS = False
                return False
            _CUT_SESS = ort.InferenceSession(mp, providers=['CPUExecutionProvider'])
        img = cv2.imread(frame_path)
        if img is None:
            return False
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        src = rgb.transpose(2, 0, 1)[None]
        z = np.zeros((1, 1, 1, 1), np.float32)
        dsr = np.array([0.4], np.float32)
        out = _CUT_SESS.run(None, {'src': src, 'r1i': z, 'r2i': z, 'r3i': z,
                                   'r4i': z, 'downsample_ratio': dsr})
        pha = out[1]
        a = (np.clip(pha[0, 0], 0.0, 1.0) * 255).astype(np.uint8)
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        bgra[:, :, 3] = a
        cv2.imwrite(out_png, bgra)
        return True
    except Exception as e:
        _CUT_SESS = False
        print(f"  Cutout-Vorschau uebersprungen ({type(e).__name__})")
        return False


def _video_mode(face_frac, multi_person, min_head=0.35):
    """v96b: Automatischer Modus-Schalter. Aus dem Gesichts-Anteil (Anteil der
    Frames mit erkanntem Sprecher-Gesicht) und dem Multi-Person-Flag ergibt sich,
    wie die Captions gesetzt werden:
      'conversation'  = mehrere Personen reden -> Active-Speaker + Multi-Safe-Zone
      'talking_head'  = eine Person meist im Bild -> Face-relative Platzierung
      'narrator'      = kaum/kein Gesicht (Voiceover, Screen-Recording, B-Roll mit
                        Erzaehler) -> zentrierte, editoriale Platzierung, kein
                        'behind' (es ist nichts da, wovor/wohinter der Text koennte)
    Rein & testbar."""
    if multi_person:
        return 'conversation'
    if face_frac >= min_head:
        return 'talking_head'
    return 'narrator'


def track_faces(video_path, out_w, out_h, fps_str='25', det_step=2):
    work_w = 512
    work_h = max(int(512 * out_h / out_w) // 2 * 2, 2)
    """Gesichts-Tracking + Szenen-Analyse.
    Rueckgabe: (positionen, present) - present[frame] = Talking-Head (True) oder B-Roll (False).
    B-Roll wird pro Szene erkannt (Schnitt-Erkennung), nicht pro Frame. Eine Szene gilt nur
    dann als Talking Head, wenn durchgehend ein Gesicht da ist UND es zur typischen
    Gesichtsgroesse des Videos passt (filtert Stock-Footage mit fremden Personen)."""
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    print("Gesichts-Tracking + Szenen-Analyse...")
    # v96c: niedrigere Confidence (0.4->0.25) faengt angewinkelte / halb
    # abgewandte / kleinere Gesichter, die frontal-optimierte Modelle sonst
    # verwerfen. Die dadurch moeglichen Fehldetektionen werden ueber die
    # Spur-Mindestlaenge (_smooth_tracks) wieder ausgesiebt.
    opts = vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=os.path.join(HERE, 'models/face.tflite')),
        min_detection_confidence=0.25)
    detector = vision.FaceDetector.create_from_options(opts)
    # v96c: Gesichter in HOEHERER Aufloesung suchen. BlazeFace erkennt nicht-
    # frontale und kleinere Koepfe deutlich besser, wenn das Bild groesser ist;
    # die gefundenen Boxen werden zurueck in den Arbeits-Raum skaliert.
    det_up = 1.8
    det_w, det_h = int(work_w * det_up), int(work_h * det_up)
    raw, hists, face_hists = [], [], []
    dets_seq = []                  # v96: ALLE Gesichter pro Frame [cx,cy,w,motion]
    last_dets = []
    prev_gray = None
    fi_a = 0
    for frame in iter_frames(video_path, work_w, work_h, fps_str):
        tiny = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(tiny, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        hists.append(hist)
        if fi_a % det_step != 0:
            dets_seq.append([list(d) for d in last_dets])   # halten
            raw.append(list(last_dets[0][:3]) if last_dets else None)
            face_hists.append(None)
            fi_a += 1
            continue
        fi_a += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        big = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(big, cv2.COLOR_BGR2RGB)
        res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img))
        faces = []
        if res.detections:
            for d in res.detections:
                bb = d.bounding_box
                # Box aus dem hochskalierten Bild zurueck in den Arbeits-Raum
                bx = bb.origin_x / det_up
                by = bb.origin_y / det_up
                bw = bb.width / det_up
                bh = bb.height / det_up
                cx = bx + bw / 2.0
                cy = by + bh / 2.0
                # v96: Mund-/Lippen-Bewegung = Frame-Differenz im unteren Drittel
                # der Gesichtsbox. Wer spricht, bewegt dort am meisten -> Basis
                # fuer die Active-Speaker-Wahl.
                mot = 0.0
                if prev_gray is not None:
                    y0m = max(int(by + bh * 0.55), 0)
                    y1m = min(int(by + bh), gray.shape[0])
                    x0m = max(int(bx), 0)
                    x1m = min(int(bx + bw), gray.shape[1])
                    if y1m > y0m and x1m > x0m:
                        cur = gray[y0m:y1m, x0m:x1m].astype(np.float32)
                        pre = prev_gray[y0m:y1m, x0m:x1m].astype(np.float32)
                        if cur.shape == pre.shape and cur.size:
                            mot = float(np.abs(cur - pre).mean())
                faces.append([cx, cy, float(bw), mot,
                              float(bh), float(d.categories[0].score),
                              int(bx), int(by)])
        prev_gray = gray
        # nach Score sortiert (staerkste Detektion zuerst)
        faces.sort(key=lambda f: f[5], reverse=True)
        dets_seq.append([f[:4] for f in faces])
        last_dets = [f[:4] for f in faces]
        if faces:
            d0 = faces[0]
            raw.append([d0[0], d0[1], d0[2]])
            x0, y0 = max(d0[6], 0), max(d0[7], 0)
            crop = frame[y0:y0 + max(int(d0[4]), 4), x0:x0 + max(int(d0[2]), 4)]
            if crop.size:
                ch = cv2.calcHist([cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)], [0, 1], None,
                                  [8, 8], [0, 180, 0, 256])
                cv2.normalize(ch, ch)
                face_hists.append(ch)
            else:
                face_hists.append(None)
        else:
            raw.append(None)
            face_hists.append(None)
    n = len(raw)
    # v96/v96c: Personen-Spuren, geglaettet (Luecken bei weggedrehten Koepfen
    # gefuellt, Fehldetektionen ausgesiebt) + Active-Speaker ueber Mund-Bewegung.
    # Position/Kamera/Effekte folgen dem aktiven Sprecher (Hybrid). Aus den
    # geglaetteten Spuren kommen auch die Multi-Face-Safe-Zone-Boxen.
    smooth_boxes = [[] for _ in range(n)]
    if any(dets_seq):
        track_of, track_motion = _faces_tracks(dets_seq, work_w * 0.14)
        _hold = int(round(6 / max(det_step, 1))) + 2
        smooth_boxes, smooth_tids = _smooth_tracks(dets_seq, track_of,
                                                   hold=_hold, min_len=2)
        for i in range(n):
            fb = smooth_boxes[i]
            if fb:
                aj = _active_index(fb, smooth_tids[i], track_motion)
                raw[i] = [fb[aj][0], fb[aj][1], fb[aj][2]]    # Primaer = Sprecher
            else:
                raw[i] = None                                 # Spuk-Detektion weg
    # Multi-Person aus den GEGLAETTETEN Spuren (haelt eine kurz abgewandte
    # zweite Person - sonst wuerde ein Gespraech faelschlich als Einzelperson
    # eingestuft und die Safe-Zone gegen die zweite Person entfiele).
    multi_person = sum(len(fr) >= 2 for fr in smooth_boxes) > 0.10 * max(n, 1)

    # --- Schnitte finden (Histogramm-Korrelation zwischen Nachbar-Frames)
    cuts = [0]
    for i in range(1, n):
        if cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_CORREL) < 0.55:
            if i - cuts[-1] >= 5:            # Mini-Szenen (Blitze) nicht splitten
                cuts.append(i)
    # Weiche Uebergaenge (Crossfades): Vergleich ueber 12 Frames Abstand
    for i in range(6, n - 6):
        if cv2.compareHist(hists[i - 6], hists[i + 6], cv2.HISTCMP_CORREL) < 0.45:
            if all(abs(i - c) >= 8 for c in cuts):
                cuts.append(i)
    cuts = sorted(set(cuts + [n]))
    shots = list(zip(cuts[:-1], cuts[1:]))

    # --- Referenz: typische Gesichtsgroesse des Sprechers
    widths = [r[2] for r in raw if r]
    ref_w = float(np.median(widths)) if widths else None

    det = [r is not None for r in raw]
    # v96: Der Sprecher-Identitaets-Filter (nur EIN Gesicht gilt als "der
    # Sprecher") wuerde in einem Gespraech die zweite Person als Fremd-Gesicht
    # verwerfen. Bei Multi-Person also AUS - beide reden, beide zaehlen. Bei
    # einer Person filtert er weiter Stock-Footage-Gesichter raus.
    valid = [h for h in face_hists if h is not None]
    if not multi_person and len(valid) > 10:
        avg = sum(valid) / len(valid)
        sims = [cv2.compareHist(h, avg, cv2.HISTCMP_CORREL) if h is not None else -1
                for h in face_hists]
        core = [h for h, s in zip(face_hists, sims) if h is not None and s > np.median(
            [x for x in sims if x >= 0])]
        ref = sum(core) / len(core) if core else avg
        for i, h in enumerate(face_hists):
            if h is not None and cv2.compareHist(h, ref, cv2.HISTCMP_CORREL) < 0.45:
                det[i] = False        # Gesicht erkannt, aber nicht der Sprecher

    # --- Szenen klassifizieren
    present = np.zeros(n, dtype=bool)
    for a, b in shots:
        det_shot = [raw[i] for i in range(a, b) if det[i]]
        ratio = len(det_shot) / max(b - a, 1)
        is_head = ratio > 0.55
        # v96: Die Groessen-Schranke (Gesicht muss zur typischen Sprecher-Groesse
        # passen) filtert Stock-Footage. Bei Multi-Person haben zwei Personen in
        # unterschiedlicher Tiefe legitim verschiedene Groessen - dann NICHT nach
        # Groesse aussortieren, sonst faellt ein echtes Gespraech als B-Roll raus.
        if is_head and ref_w and det_shot and not multi_person:
            mw = float(np.median([r[2] for r in det_shot]))
            if not (0.55 * ref_w <= mw <= 1.9 * ref_w):
                is_head = False              # Gesicht da, aber falsche Groesse -> B-Roll
        present[a:b] = is_head

    # --- Positionen fuellen und glaetten
    last = None
    filled = []
    for r in raw:
        if r is not None: last = r[:2]
        filled.append(list(last) if last else [work_w / 2, work_h * 0.35])
    arr = np.array(filled)
    k = 15
    kernel = np.ones(k) / k
    sm = np.stack([np.convolve(np.pad(arr[:, j], k // 2, mode='edge'), kernel, 'valid')[:len(arr)]
                   for j in range(2)], axis=1)
    raw_present = np.array([any(det[max(0, i - 6):i + 7]) for i in range(n)])
    present = present & raw_present
    # Uebergangs-Sperre: rund um Praesenz-Wechsel keine Texte starten
    flips = np.where(present[1:] != present[:-1])[0]
    for f in flips:
        present[max(f - 8, 0):min(f + 9, n)] = False
    lastw = None
    wfill = []
    for r in raw:
        if r is not None: lastw = r[2]
        wfill.append(lastw if lastw else work_w * 0.09)
    wsm = np.convolve(np.pad(np.array(wfill, dtype=float), k // 2, mode='edge'),
                      kernel, 'valid')[:n]
    n_broll = int((~present).sum())
    _npf = sum(len(f) >= 2 for f in smooth_boxes)
    print(f"  {len(shots)} Szenen, {int(sum(r is not None for r in raw))}/{n} Frames mit Gesicht"
          + (f", {n_broll} Frames als B-Roll eingestuft" if n_broll else "")
          + (f", Multi-Person in {_npf} Frames" if multi_person else ""))
    sc = out_w / float(work_w)
    # v85: interne Schnitt-Frames mitgeben (fuer Caption-Schnitt-Disziplin).
    inner_cuts = [c for c in cuts if 0 < c < n]
    # v96/v96c: ALLE Gesichter pro Frame in Output-Pixeln aus den GEGLAETTETEN
    # Spuren (kurz weggedrehte Koepfe bleiben drin) - fuer die Multi-Face-Safe-
    # Zone, damit der Text KEINES der Gesichter ueberdeckt.
    faces_seq = [[(b[0] * sc, b[1] * sc, b[2] * sc) for b in fr]
                 for fr in smooth_boxes]
    return sm * sc, present, wsm * sc, inner_cuts, faces_seq, multi_person

# ---------------------------------------------------------------- sprites
class Sprites:
    def __init__(self, cfg, W, H):
        style = str(cfg['effects'].get('text_style', 'klassisch')).lower()
        self.ex = '3d' in style
        self.kinetic = 'kinet' in style
        self.cfg, self.W, self.H = cfg, W, H
        f = cfg['fonts']
        self.f_serif = os.path.join(HERE, f['display'])
        self.f_italic = os.path.join(HERE, f['italic'])
        self.f_sans = os.path.join(HERE, f['support'])
        scr = os.path.join(HERE, f.get('script', 'fonts/lobster.ttf'))
        if not os.path.exists(scr):
            scr = os.path.join(HERE, 'fonts', 'lobster.ttf')
        self.f_script = scr if os.path.exists(scr) else self.f_italic
        sb = os.path.join(HERE, 'fonts', 'poppins_b.ttf')
        self.f_sans_b = sb if os.path.exists(sb) else self.f_sans
        self.white = tuple(cfg['colors']['text'])
        self.accent = tuple(cfg['colors']['accent'])
        self._white0, self._accent0 = self.white, self.accent

    def set_base_colors(self, text, accent):
        """Feste Farbwelt (Elegantes Schwarz/Weiss): ueberschreibt auch die
        Rueckfall-Farben, damit set_palette(None) nicht die Config-Toene holt."""
        self.white, self.accent = tuple(text), tuple(accent)
        self._white0, self._accent0 = self.white, self.accent

    def set_palette(self, pal):
        """Adaptive Farben pro Moment: pal=(text, accent) oder None = Config-Farben."""
        if pal:
            self.white, self.accent = tuple(pal[0]), tuple(pal[1])
        else:
            self.white, self.accent = self._white0, self._accent0

    def text(self, txt, size, color, tracking=4, glow=False, outline=False,
             per_letter=False, font=None, extrude=False, flat_light=False,
             wght=None):
        """Rendert in doppelter Aufloesung und rechnet mit INTER_AREA herunter (Supersampling).
        wght setzt - falls ein variabler Schnitt vorliegt - die echte Gewichts-Achse."""
        font = font or self.f_serif
        SS = 2
        size2, tracking2 = size * SS, tracking * SS
        f = ImageFont.truetype(font, size2)
        if wght is not None:
            vf = var_font_for(font)
            if vf:
                try:
                    f = ImageFont.truetype(vf, size2)
                    vals = []
                    for ax in f.get_variation_axes():
                        nm = ax.get('name', b'')
                        nm = nm.decode('utf-8', 'ignore') if isinstance(nm, bytes) else str(nm)
                        if nm.strip().lower() in ('weight', 'wght'):
                            vals.append(float(min(max(wght, ax['minimum']), ax['maximum'])))
                        else:
                            vals.append(float(ax['default']))
                    f.set_variation_by_axes(vals)
                except Exception:
                    f = ImageFont.truetype(font, size2)
        if 'playfair' in os.path.basename(font):
            try:
                f.set_variation_by_axes([600])   # Kursive mit Praesenz
            except Exception:
                pass
        d0 = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        widths = [d0.textbbox((0, 0), ch, font=f)[2] for ch in txt]
        # v85: Kerning. Bisher wurde jeder Buchstabe einzeln gesetzt und um seine
        # eigene Ink-Breite vorgeschoben - PIL wendet Kerning-Paare (VA, To, AV,
        # LT ...) aber nur an, wenn ein String am Stueck gezeichnet wird. Ergebnis
        # waren optisch zu grosse Luecken an genau diesen Paaren, der klassische
        # "burnt-in Auto-Caption"-Tell. Wir behalten das Einzel-Setzen (fuer
        # Schatten/Extrusion/Buchstaben-Boxen), ziehen aber pro Paar die echte
        # Kerning-Korrektur ab: kern = adv(prev+ch) - adv(prev) - adv(ch).
        # Nicht-gekernte Paare bleiben damit exakt wie vorher.
        kerns = [0.0] * len(txt)
        for i in range(1, len(txt)):
            try:
                pv = txt[i - 1]
                kerns[i] = (f.getlength(pv + txt[i]) - f.getlength(pv)
                            - f.getlength(txt[i]))
            except Exception:
                kerns[i] = 0.0
        total = sum(widths) + tracking2 * max(len(txt) - 1, 0) + sum(kerns)
        asc, desc = f.getmetrics()
        pad = (90 if glow else 40) * SS
        img = Image.new('RGBA', (int(math.ceil(total)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        front = Image.new('RGBA', img.size, (0, 0, 0, 0))
        dfr = ImageDraw.Draw(front)
        x = pad
        letters = []
        depth = max(int(size2 * 0.085), 6) if extrude else 0
        for ch, cw, kern in zip(txt, widths, kerns):
            x += kern                         # v85: Paar an prev heranziehen
            if outline:
                d.text((x, pad), ch, font=f, fill=(0, 0, 0, 0), stroke_width=4 * SS,
                       stroke_fill=color + (255,))
            elif extrude:
                for k in range(depth, 0, -2):     # 3D-Extrusion, nach hinten dunkler
                    kk = k / max(depth, 1)
                    dk = tuple(int(c * (0.38 - 0.22 * kk)) for c in color)
                    d.text((x + k * 0.55, pad + k), ch, font=f, fill=dk + (255,))
                dfr.text((x, pad), ch, font=f, fill=color + (255,))
            else:
                d.text((x + 3 * SS, pad + 5 * SS), ch, font=f, fill=(0, 0, 0, 150))
                dfr.text((x, pad), ch, font=f, fill=color + (255,))
            letters.append(((x - 6 * SS) / SS, (x + cw + tracking2 + 6 * SS) / SS))
            x += cw + tracking2
        # Studio-Licht auf der Frontflaeche: vertikaler Verlauf + Glanzband oben.
        # Das nimmt den Buchstaben das Flache - der Unterschied zwischen
        # Systemschrift und Produktion.
        fr = np.array(front).astype(np.float32)
        amask = fr[..., 3] > 0
        if amask.any() and not outline and not flat_light:
            ys = np.where(amask.any(axis=1))[0]
            y0g, y1g = int(ys.min()), int(ys.max())
            tgrad = np.zeros(fr.shape[0], dtype=np.float32)
            span = max(y1g - y0g, 1)
            tgrad[y0g:y1g + 1] = (np.arange(y0g, y1g + 1) - y0g) / span
            fac = 1.14 - 0.30 * tgrad                       # oben hell, unten satt
            fac += 0.24 * np.exp(-((tgrad - 0.20) / 0.11) ** 2)   # Glanzband
            fr[..., :3] = np.clip(fr[..., :3] * fac[:, None, None], 0, 255)
        front = Image.fromarray(fr.astype(np.uint8))
        img = Image.alpha_composite(img, front)
        arr = np.array(img)
        if glow:
            a = cv2.GaussianBlur(arr[..., 3], (0, 0), 16 * SS).astype(np.float32)
            gl = np.zeros_like(arr)
            gl[..., 0], gl[..., 1], gl[..., 2] = color
            gl[..., 3] = np.clip(a * 0.85, 0, 255).astype(np.uint8)
            arr = np.array(Image.alpha_composite(Image.fromarray(gl), Image.fromarray(arr)))
        h2, w2 = arr.shape[:2]
        arr = cv2.resize(arr, (w2 // SS, h2 // SS), interpolation=cv2.INTER_AREA)
        if per_letter:
            return arr, total / SS, letters
        return arr, total / SS

    def fit(self, txt, base, max_w, font=None, tracking=4):
        font = font or self.f_serif
        f = ImageFont.truetype(font, base)
        if 'playfair' in os.path.basename(font):
            try:
                f.set_variation_by_axes([600])   # Kursive mit Praesenz
            except Exception:
                pass
        d0 = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        w = sum(d0.textbbox((0, 0), ch, font=f)[2] for ch in txt) + tracking * (len(txt) - 1)
        if w <= max_w: return base
        return max(int(base * max_w / w), 36)

def rot_img(arr, deg):
    if abs(deg) < 0.2: return arr
    return np.array(Image.fromarray(arr).rotate(deg, expand=True, resample=Image.BICUBIC))

# --- Emoji (v81e): Noto Color Emoji rendert nur in fester Bitmap-Groesse (109),
# wird danach auf Zielhoehe skaliert. Ergebnis wird gecacht (pro Emoji+Hoehe).
_EMOJI_FONT_PATH = None
_EMOJI_CACHE = {}


def _emoji_font():
    global _EMOJI_FONT_PATH
    if _EMOJI_FONT_PATH is None:
        import glob
        c = (glob.glob('/usr/share/fonts/**/NotoColorEmoji*.ttf', recursive=True) or
             glob.glob('/usr/share/fonts/**/*Emoji*.ttf', recursive=True))
        _EMOJI_FONT_PATH = c[0] if c else ''
    return _EMOJI_FONT_PATH or None


def emoji_sprite(emoji, height):
    """BGRA-Array eines Emojis in gewuenschter Pixel-Hoehe, oder None."""
    if not emoji:
        return None
    key = (emoji, int(height))
    if key in _EMOJI_CACHE:
        return _EMOJI_CACHE[key]
    fp = _emoji_font()
    if not fp:
        return None
    try:
        f = ImageFont.truetype(fp, 109)          # Noto: fixe Bitmap-Groesse
        img = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        try:
            d.text((64, 64), emoji, font=f, embedded_color=True, anchor='mm')
        except Exception:
            d.text((8, 8), emoji, font=f, embedded_color=True)
        arr = np.array(img)                       # RGBA
        ys, xs = np.where(arr[:, :, 3] > 8)
        if not len(ys):
            _EMOJI_CACHE[key] = None
            return None
        arr = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h = max(int(height), 8)
        w = max(int(arr.shape[1] * h / arr.shape[0]), 8)
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_AREA)
        bgra = arr[:, :, [2, 1, 0, 3]].copy()     # RGBA -> BGRA (Compositor-Format)
        _EMOJI_CACHE[key] = bgra
        return bgra
    except Exception:
        _EMOJI_CACHE[key] = None
        return None


def bake_emoji(arr, emoji, side='right'):
    """Setzt das Emoji neben ein BGRA-Sprite und liefert ein breiteres Sprite.
    So reist das Emoji durch alle Downstream-Effekte (Anim/Reflexion/Schatten)
    mit, ohne dass die fx-spezifische Logik angefasst werden muss."""
    if arr is None or not emoji:
        return arr
    eh = int(arr.shape[0] * 0.62)
    em = emoji_sprite(emoji, eh)
    if em is None:
        return arr
    gap = int(arr.shape[0] * 0.12)
    new_w = arr.shape[1] + gap + em.shape[1]
    out = np.zeros((arr.shape[0], new_w, 4), dtype=arr.dtype)
    if side == 'left':
        out[:, em.shape[1] + gap:] = arr
        ex = 0
    else:
        out[:, :arr.shape[1]] = arr
        ex = arr.shape[1] + gap
    ey = (arr.shape[0] - em.shape[0]) // 2
    out[ey:ey + em.shape[0], ex:ex + em.shape[1]] = em
    return out

def paste(canvas, rgba, cx, cy, W, H, scale=1.0, opacity=1.0, blur=0.0, crop_w=None):
    if scale <= 0.02 or opacity <= 0.01: return
    if crop_w is not None:
        rgba = rgba[:, :max(int(crop_w), 1)]
    if abs(scale - 1.0) > 0.002:
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        rgba = cv2.resize(rgba, None, fx=scale, fy=scale, interpolation=interp)
    if blur > 0.4:
        rgba = cv2.GaussianBlur(rgba, (0, 0), blur)
    h, w = rgba.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = max(x0, 0), max(y0, 0)
    x2, y2 = min(x0 + w, W), min(y0 + h, H)
    if x2 <= x1 or y2 <= y1: return
    sub = rgba[y1 - y0:y2 - y0, x1 - x0:x2 - x0].astype(np.float32)
    a = sub[..., 3:4] / 255.0 * opacity
    canvas[y1:y2, x1:x2] = sub[..., [2, 1, 0]] * a + canvas[y1:y2, x1:x2] * (1 - a)

def _blend_region(canvas, sub, x1, y1, W, H, opacity=0.74, ripple=0.10,
                  refract=1.0, blur=0.0, occ=None, grain=2.2):
    """Blend-Kern der Szenen-Integration: Refraktion, Farb-Kopplung, Spitzlichter,
    Tiefen-Okklusion und Film-Grain auf einem bereits positionierten RGBA-Ausschnitt."""
    y2, x2 = y1 + sub.shape[0], x1 + sub.shape[1]
    bg = canvas[y1:y2, x1:x2]
    lum = bg.mean(axis=2)
    if refract > 0.05 and min(sub.shape[0], sub.shape[1]) > 12:
        soft = cv2.GaussianBlur(lum, (0, 0), 4.5)
        gx = cv2.Sobel(soft, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(soft, cv2.CV_32F, 0, 1, ksize=5)
        norm = float(np.abs(gx).mean() + np.abs(gy).mean()) / 2.0 + 1e-3
        amp = refract * max(sub.shape[0] * 0.035, 3.0)
        dxm = np.clip(gx / (norm * 3.0), -1, 1) * amp
        dym = np.clip(gy / (norm * 3.0), -1, 1) * amp
        yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]].astype(np.float32)
        sub = cv2.remap(sub, xx + dxm.astype(np.float32), yy + dym.astype(np.float32),
                        cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                        borderValue=(0, 0, 0, 0))
        feather = max(sub.shape[0] * 0.026, 3.0)
        sub[..., 3] = cv2.GaussianBlur(sub[..., 3], (0, 0), feather)
    eff_blur = max(blur, 1.0 if refract > 0.05 else blur)
    if eff_blur > 0.4:
        sub = cv2.GaussianBlur(sub, (0, 0), eff_blur)
    base = cv2.GaussianBlur(bg, (0, 0), 11).astype(np.float32) + 1.0
    mod = np.clip(bg / base, 0.80, 1.20)
    mod = (1.0 - ripple) + ripple * mod
    a = sub[..., 3:4] / 255.0 * opacity
    if refract > 0.05:
        base_l = base.mean(axis=2)
        spec = np.clip((lum - base_l * 1.16) / 55.0, 0, 1)
        spec = cv2.GaussianBlur(spec, (0, 0), 2.0)[..., None]
        a = a * (1.0 - 0.45 * spec)
    if occ is not None:
        a = a * (1.0 - occ[y1:y2, x1:x2, None])
    if grain > 0.1:
        noise = np.random.default_rng().standard_normal(sub.shape[:2])[..., None]
        sub[..., :3] = np.clip(sub[..., :3] + noise * grain, 0, 255)
    canvas[y1:y2, x1:x2] = sub[..., [2, 1, 0]] * mod * a + bg * (1 - a)

def paste_scene(canvas, rgba, cx, cy, W, H, scale=1.0, opacity=0.74, ripple=0.10,
                refract=1.0, blur=0.0, occ=None, grain=2.2):
    """Positioniert ein Sprite und blendet es als Teil der Szene ein (siehe _blend_region)."""
    if scale <= 0.02 or opacity <= 0.01:
        return
    if abs(scale - 1.0) > 0.002:
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        rgba = cv2.resize(rgba, None, fx=scale, fy=scale, interpolation=interp)
    h, w = rgba.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = max(x0, 0), max(y0, 0)
    x2, y2 = min(x0 + w, W), min(y0 + h, H)
    if x2 <= x1 or y2 <= y1:
        return
    sub = np.ascontiguousarray(rgba[y1 - y0:y2 - y0, x1 - x0:x2 - x0]).astype(np.float32)
    _blend_region(canvas, sub, x1, y1, W, H, opacity=opacity, ripple=ripple,
                  refract=refract, blur=blur, occ=occ, grain=grain)

def update_homography(prev_gray, gray, H_cum, mask_lower=0.30):
    """Ein Schritt planares Kamera-Tracking: verfolgt Features der Bodenebene
    (unteres Bilddrittel aufwaerts) und akkumuliert die Homographie.
    Gibt (H_cum_neu, ok) zurueck - genau die Transformation, die ein
    After-Effects-Plane-Track liefert."""
    h, w = gray.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    mask[int(h * mask_lower):, :] = 255
    p0 = cv2.goodFeaturesToTrack(prev_gray, maxCorners=260, qualityLevel=0.01,
                                 minDistance=8, mask=mask)
    if p0 is None or len(p0) < 24:
        return H_cum, False
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None,
                                         winSize=(21, 21), maxLevel=3)
    if p1 is None:
        return H_cum, False
    good = st.reshape(-1) == 1
    if good.sum() < 24:
        return H_cum, False
    Hs, inl = cv2.findHomography(p0[good], p1[good], cv2.RANSAC, 3.0)
    if Hs is None or inl is None or inl.sum() < 20 or not np.isfinite(Hs).all():
        return H_cum, False
    H_new = Hs @ H_cum
    H_new /= H_new[2, 2]
    return H_new, True

def paste_tracked(canvas, rgba, cx, cy, H_rel, W, H, dy_extra=0.0, **blend_kwargs):
    """Setzt ein Sprite mit der getrackten Kamera-Transformation in die Szene:
    das urspruengliche Quad wird pro Frame durch H_rel bewegt - der Text waechst,
    kippt und zieht vorbei wie ein Objekt in der Welt."""
    h, w = rgba.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    base = np.float32([[cx - w / 2, cy - h / 2 + dy_extra],
                       [cx + w / 2, cy - h / 2 + dy_extra],
                       [cx + w / 2, cy + h / 2 + dy_extra],
                       [cx - w / 2, cy + h / 2 + dy_extra]])
    dst = cv2.perspectiveTransform(base[None], H_rel.astype(np.float64))[0].astype(np.float32)
    if not np.isfinite(dst).all():
        return
    area = abs(cv2.contourArea(dst))
    if area < 300 or area > W * H * 6:
        return                                  # degeneriert oder laengst vorbeigezogen
    M = cv2.getPerspectiveTransform(src, dst)
    layer = cv2.warpPerspective(rgba, M, (W, H), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    ys, xs = np.where(layer[..., 3] > 4)
    if len(ys) < 8:
        return
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    sub = np.ascontiguousarray(layer[y1:y2, x1:x2]).astype(np.float32)
    _blend_region(canvas, sub, x1, y1, W, H, **blend_kwargs)


def person_mask(alpha):
    """Bereinigt die RVM-Matte zu einer verlaesslichen PERSONEN-Maske: nur die
    groesste zusammenhaengende Flaeche bleibt. Die rohe Matte markiert gern
    kleine Hintergrund-Blobs (Autos, Pflaster-Flecken) als 'Person' - die
    wuerden Okklusion, Boden-Anker und Bokeh mit Halos zerfressen."""
    a2 = alpha[..., 0] if alpha.ndim == 3 else alpha
    a2 = a2.astype(np.float32)
    bw = (a2 > 0.45).astype(np.uint8)
    # Opening: duenne Bruecken zwischen Person und Fehl-Blobs (Autos,
    # Pflaster) kappen, sonst haengen sie an derselben Komponente.
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    if n <= 1:
        return a2
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[big, cv2.CC_STAT_AREA] < a2.size * 0.02:
        return a2                          # nichts Substanzielles -> roh lassen
    # Dilatieren: weiche Kanten (Haare, Finger) der ECHTEN Person zurueckholen,
    # entfernte Blobs bleiben draussen.
    keep = cv2.dilate((lab == big).astype(np.uint8),
                      np.ones((13, 13), np.uint8))
    return (a2 * keep).astype(np.float32)


def ground_pose(depth_n, cx, cy, bw, bh, W, H):
    """Misst die NEIGUNG der Flaeche am Ankerpunkt aus der Tiefenkarte.
    depth_n ist NAEHE (invers: nah = grosse Werte). Die Richtung fallender
    Naehe = 'von der Kamera weg'; liegender Text richtet seine Oberkante
    dorthin aus (Roll) und uebernimmt die Staerke des Gefaelles als
    Perspektive (Pitch). None = keine klare liegende Flaeche messbar."""
    if depth_n is None:
        return None
    x1 = int(max(cx - bw, 0)); x2 = int(min(cx + bw, W))
    y1 = int(max(cy - bh, 0)); y2 = int(min(cy + bh, H))
    reg = depth_n[y1:y2, x1:x2]
    if reg.size < 400:
        return None
    reg = cv2.GaussianBlur(reg.astype(np.float32), (0, 0), 4)
    gx = cv2.Sobel(reg, cv2.CV_32F, 1, 0, ksize=5)
    gy = cv2.Sobel(reg, cv2.CV_32F, 0, 1, ksize=5)
    mgx = float(np.median(gx)); mgy = float(np.median(gy))
    mag = float(np.hypot(mgx, mgy))
    if mag < 1e-5:
        # Uniforme Tiefe = Kamera schaut SENKRECHT auf die Flaeche
        # (Draufsicht). Kein Roll, kaum Foreshortening.
        return 0.0, 0.55
    ax, ay = -mgx / mag, -mgy / mag         # 'weg'-Richtung (Naehe faellt)
    if ay > 0.25:
        return None                          # flieht nach UNTEN -> kein Boden
    roll = float(np.degrees(np.arctan2(ax, -ay)))
    roll = max(-30.0, min(30.0, roll))
    span = float(np.percentile(reg, 90) - np.percentile(reg, 10))
    pitch = max(0.52, min(0.80, 0.45 + 0.55 * span))
    return roll, pitch


def ground_anchor(alpha, arr, W, H, avoid_x=None, band=(0.60, 1.02),
                  allow_overhang=False, depth_n=None):
    """Sucht auf B-Roll MIT sichtbarer Person eine klare Bodenflaeche fuer
    liegenden Text. Ohne diese Suche landet der Text am Bild-Zentrum - und
    genau dort steht bei einem Selfie-Kameraschwenk-nach-unten die Person
    (Arm/Pulli), sodass der Text auf der Person klebt statt auf der Strasse.

    Idee: die Person (RVM-Matte, alpha>0.35) wird ausgespart, aus den freien
    Boden-Pixeln wird eine Ankerstelle gewaehlt - bevorzugt tief/vorne (die
    Strasse direkt vor der Person) und mit freier Mitte (der Anker selbst
    liegt auf dem Boden). Der Arm/Koerper deckt spaeter nur den oberen Rand
    des Wortes ab - das ist der Look: das Wort liegt hinter der Person auf
    dem Pflaster.

    Gibt (cx, cy) zurueck oder None (kaum Person -> Standard-Anker behalten)."""
    a2 = person_mask(alpha)
    if float(a2.mean()) < 0.06:
        return None                       # kaum Person -> echtes Aerial-B-Roll
    tw, th = arr.shape[1], arr.shape[0]
    mx = tw / 2 + W * 0.03                # das Wort muss ganz im Bild bleiben
    my = th / 2 + H * 0.02
    xs = np.linspace(mx, W - mx, 9)
    # band = vertikaler Suchbereich der Flaeche (Boden: unten, Wand: Mitte).
    # allow_overhang: unten darf das Wort ueber den Rand haengen (Not-Option
    # zum Sprech-Zeitpunkt). Vorher gilt: NUR voll lesbare Plaetze - der
    # Schwenk gibt gleich mehr Flaeche frei, wir warten lieber einen Moment.
    _edge = th * (0.2 if allow_overhang else 0.55)
    ys = np.linspace(max(band[0] * H, my), min(band[1] * H, H - _edge), 12)
    if len(xs) == 0 or len(ys) == 0 or mx > W / 2 or my > H / 2:
        return None                       # Wort passt nicht sauber -> Standard
    best = None
    # Kaskade: erst klar freie Bodenflaeche verlangen, dann schrittweise
    # lockern - besser leicht von der Person angeschnitten (Okklusion macht
    # daraus "liegt hinter ihr") als gar kein Boden-Text.
    fallback = None
    for thr in (0.7, 0.5, 0.35):
        for cy in ys:
            for cx in xs:
                x1 = int(cx - tw / 2); x2 = int(cx + tw / 2)
                y1 = int(cy - th / 2); y2 = int(cy + th / 2)
                box = a2[max(y1, 0):y2, max(x1, 0):x2]
                if box.size == 0:
                    continue
                cover = float((box > 0.35).mean())      # Personanteil in der Box
                # wenig Person + mittig. Tiefen-Bias haengt vom Kontext: im
                # Talking-Head liegt der Boden UNTEN (stark nach vorn ziehen);
                # bei breitem Band (Kamera-auf-die-Flaeche) zaehlt die MITTE
                # der freigeschwenkten Flaeche - dort haelt die Kamera.
                _deep = 0.15 if band[0] < 0.4 else 0.6
                score = (-1.1 * cover + _deep * (cy / H)
                         - 0.25 * abs(cx - W / 2) / W)
                if avoid_x is not None:
                    # Talking-Head: weg von der Person ankern - sie laeuft/
                    # gestikuliert, die Gegenseite bleibt frei sichtbar.
                    score += 0.5 * abs(cx - avoid_x) / W
                if thr == 0.7 and (fallback is None or score > fallback[0]):
                    fallback = (score, cx, cy, cover)   # bester Platz ueberhaupt
                cs = 8
                cb = a2[int(cy) - cs:int(cy) + cs, int(cx) - cs:int(cx) + cs]
                center_free = float((cb < 0.35).mean()) if cb.size else 0.0
                if center_free < thr:                    # Anker muss auf Boden sitzen
                    continue
                if best is None or score > best[0]:
                    best = (score, cx, cy, cover)
        if best is not None:
            break
    # NIE aufgeben: findet die Kaskade nichts Freies, nimm den am wenigsten
    # verdeckten Platz. Die Okklusion macht daraus "liegt hinter der Person" -
    # unsichtbar am Default-Platz mitten auf der Person waere das Schlimmste.
    if best is None:
        best = fallback
    # Teilverdeckung ist erlaubt und ERWUENSCHT: Arm/Schulter VOR dem
    # liegenden Wort ist der Signature-Look (Okklusion macht die Tiefe).
    # Der Tiefen-Check unten verhindert zuverlaessig, dass auf dem Koerper
    # selbst geankert wird - Cover allein muss darum nicht streng sein.
    if best is None or best[3] > 0.70:
        return None
    return (best[1], best[2])


# ---------------------------------------------------------------- keywords + plans
STOPWORDS = {
    'aber', 'also', 'auch', 'bevor', 'beim', 'dabei', 'dann', 'denn', 'dein', 'deine',
    'diese', 'dieser', 'dieses', 'doch', 'eine', 'einem', 'einen', 'einer', 'eines',
    'ende', 'erst', 'euch', 'fast', 'ganz', 'genau', 'gleichzeitig', 'heute', 'hier',
    'hinter', 'immer', 'jetzt', 'kein', 'keine', 'mein', 'meine', 'nach', 'nicht',
    'noch', 'ohne', 'schon', 'sein', 'seine', 'selbst', 'sich', 'total', 'trotzdem',
    'viel', 'viele', 'vielleicht', 'voellig', 'völlig', 'wann', 'warum', 'wenn',
    'wieder', 'wirklich', 'zuerst', 'zwar', 'dinge', 'bleib', 'oder', 'und', 'was',
    'wie', 'wer', 'werden', 'wurde', 'darum', 'deshalb', 'damit', 'dazu',
    'jahr', 'jahre', 'jahren', 'tag', 'tage', 'tagen', 'woche', 'wochen',
    'monat', 'monate', 'monaten', 'mal', 'seit', 'lebe',
    # v80: Hilfsverben + Kopula (der Grund warum "IST" als Caption landete)
    'bin', 'bist', 'ist', 'sind', 'seid', 'war', 'warst', 'waren', 'wart',
    'gewesen', 'hab', 'habe', 'hast', 'hat', 'haben', 'habt', 'hatte',
    'hattest', 'hatten', 'hattet', 'gehabt',
    'kann', 'kannst', 'koennen', 'können', 'könnt', 'koennt', 'konnte',
    'konntest', 'konnten', 'konntet', 'gekonnt',
    'muss', 'musst', 'muessen', 'müssen', 'müsst', 'muesst', 'musste',
    'musstest', 'mussten', 'musstet', 'gemusst',
    'soll', 'sollst', 'sollen', 'sollt', 'sollte', 'solltest', 'sollten', 'solltet',
    'will', 'willst', 'wollen', 'wollt', 'wollte', 'wolltest', 'wollten', 'wolltet', 'gewollt',
    'wird', 'wirst', 'werdet', 'wurdest', 'wurden', 'wurdet', 'worden',
    'gibt', 'geben', 'gab', 'gaben', 'gegeben',
    'tut', 'tue', 'tust', 'tun', 'tat', 'taten', 'getan',
    'mag', 'magst', 'moegen', 'mögen', 'mocht', 'mochte', 'mochten', 'gemocht',
    'darf', 'darfst', 'duerfen', 'dürfen', 'durfte', 'durftest', 'durften',
    'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'sie', 'mir', 'dir', 'ihm', 'ihn',
    'uns', 'ihnen', 'mich', 'dich', 'ihm', 'ihm', 'ihn', 'euch',
    'einfach', 'nur', 'mehr', 'weniger', 'gar', 'zu', 'zum', 'zur', 'am', 'im',
    'in', 'an', 'auf', 'bei', 'mit', 'von', 'aus', 'ueber', 'über', 'unter', 'vor',
    'als', 'aus', 'ohne', 'gegen', 'fuer', 'für', 'ja', 'nein', 'okay', 'so',
    'da', 'dass', 'ob', 'weil', 'obwohl', 'sondern', 'sowie', 'sowohl',
    'jeder', 'jede', 'jedes', 'alle', 'alles', 'aller', 'meiner', 'meinem',
    # v80s: Artikel fehlten komplett - "DAS" konnte als Keyword landen
    'der', 'die', 'das', 'dem', 'den', 'des', 'ein',
    # Englisch (fuer language != de; kollidiert nicht mit deutschen Woertern)
    'the', 'and', 'that', 'this', 'with', 'have', 'from', 'they', 'will',
    'would', 'there', 'their', 'what', 'when', 'your', 'just', 'like',
    'some', 'more', 'very', 'really', 'about', 'because', 'been', 'were',
    'then', 'than', 'them', 'only', 'into', 'over', 'after', 'before',
    'again', 'still', 'even', 'much', 'many', 'most', 'such', 'here',
    'thing', 'things', 'stuff', 'people', 'video', 'going', 'want',
    'know', 'make', 'made', 'well', 'said', 'gonna', 'right', 'okay',
    'has', 'had', 'was', 'are', 'is', 'be', 'am', 'do', 'does', 'did',
    'can', 'could', 'should', 'may', 'might', 'must', 'shall',
    'i', 'you', 'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us',
    'my', 'his', 'our', 'its', 'these', 'those', 'to', 'of', 'for', 'in',
    'on', 'at', 'by', 'as', 'or', 'if', 'so', 'yes', 'no', 'get', 'got',
    'going', 'gotta',
}

REGIE_PROMPT = """Du bist Senior-Editor fuer Premium-Talking-Head-Videos. Du bekommst das \
Transkript zweimal: als Fliesstext (fuer den Sinn) und als indizierte Wortliste [i]Wort (fuer die Auswahl).

Du bist der Regisseur - triff eigene, mutige Entscheidungen. Halte dich nicht \
an ein Schema-F: VARIIERE Effekt-Wahl, Betonung, Rhythmus und Animationen je \
nach Inhalt. Zwei verschiedene Videos duerfen sich NICHT gleich anfuehlen - \
nutze die ganze Bandbreite (nicht immer dieselben zwei Effekte). Was der Inhalt \
verlangt, entscheidest DU, nicht eine feste Regel.

Vorgehen:
1. Erfasse die Kernbotschaft des Videos.
2. Waehle die Woerter, die die Geschichte TRAGEN: Zahlen, Namen, Fachbegriffe, emotionale \
Spitzen, Pointen, Kontraste.
3. Baue eine RETENTION-DRAMATURGIE - Psychologie, die Zuschauer bis zum Ende haelt:
   - HOOK (erste Sekunden): der erste Moment verspricht oder provoziert - man
     muss sofort spueren, dass Bleiben sich lohnt. Frueh und kraeftig.
   - OFFENE SCHLEIFE: wirft das Video frueh eine Frage/These auf, lass sie
     stehen und lege den staerksten Moment (power 3) auf die AUFLOESUNG weiter
     hinten - wer die Antwort will, bleibt dran.
   - MUSTER-BRUCH: nie zweimal hintereinander dasselbe Gefuehl. Wechsle
     Effekt-Typ, Rhythmus und Wucht, bevor Monotonie entsteht.
   - ESKALATION: die Intensitaet steigt zum Ende hin - vorne nicht alles
     verschiessen, der Hoehepunkt kommt spaet.
   - MIKRO-BELOHNUNG: Zahlen, Beweise, Pointen sichtbar auszahlen (Zaehler,
     outline) - kleine Belohnungen ziehen zum Weiterschauen.
   Diese Dramaturgie bestimmt, WO deine Momente liegen und wie stark sie sind -
   in JEDEM Look, vom lauten TikTok bis zum ruhigen Clean, jeweils auf seine Art.

Regeln:
- Etwa 1 Moment pro 6-8 Sekunden Sprechzeit. Lieber weniger als mehr.
- Mehrwort-Highlights sind erwuenscht, wo sie Sinn ergeben: "n" = Anzahl aufeinanderfolgender \
Woerter ab Index i (1-4). Beispiele: Zahl + Einheit ("100 Milliarden Euro"), Eigennamen \
("Schufa Holding AG"), feste Begriffe ("Dynamic Pricing").
- NIE waehlen (harte Sperrliste, absolut ausnahmslos):
  * Hilfsverben: ist, sind, war, waren, bin, bist, hat, habe, haben, hatte, hatten, \
wird, werden, wurde, wurden, kann, koennen, könne, muss, muessen, müssen, soll, sollen, \
will, wollen, mag, moegen, mögen, darf, duerfen, dürfen
  * Konjunktionen/Fuellwoerter: denn, weil, aber, doch, jedoch, also, dann, sondern, \
oder, ob, dass, wenn, obwohl, waehrend, während, damit, als, wie, so, nur, noch, schon, \
eben, halt, mal, ja, nein, quasi, sozusagen
  * Pronomen: ich, du, er, sie, es, wir, ihr, mein, dein, sein, ihr, unser, euer, \
mich, dich, ihn, uns, euch, was, wer, welche
  * Praepositionen: in, an, auf, bei, mit, nach, von, vor, zu, aus, ueber, über, unter, \
gegen, ohne, durch, fuer, für, um, seit, bis
  * Generische Fuellsubstantive: sache, sachen, dinge, ding, thema, video, leute, \
mensch, menschen, art, weise, moment, stelle
  * Grammatik-Grossbuchstaben ohne Bedeutung (Satzanfang mit Fuellwort).
FALSCH-Beispiele die du NIE waehlen darfst:
  "Und das IST der Punkt" -> "IST" ist Hilfsverb, verboten. Waehle "Punkt".
  "DENN was der Staat tut" -> "DENN" ist Konjunktion, verboten. Waehle "Staat".
  "DAS was du siehst" -> "DAS" ist Pronomen, verboten. Waehle das Objekt.
  "HIER kommt der Beweis" -> "HIER" ist Fuellwort, verboten. Waehle "Beweis".
- Phrasen muessen in sich geschlossen sein: Substantivgruppe, Eigenname oder Zahl mit \
Einheit. NIE mit Verb, Adverb oder Kleinwort enden ("Deutschland nimmt" ist FALSCH, \
"Deutschland" ist richtig; "100 Milliarden Euro" ist richtig).
- Highlighte das OBJEKT der Aussage, nicht den Satzanfang. Bei "Eine Zahl, die du dir \
merken musst: Deutschland nimmt 14 Milliarden ein" ist "14 Milliarden" richtig, \
"Deutschland" falsch.
- Effekt passend zum Inhalt:
  behind = dramatischer Hoehepunkt einer Passage
  outline = Zahlen, Fakten, Geldbetraege
  cascade = elegante Begriffe, Namen
  blurin = Themenwechsel, neue Kapitel
  ground = grosse Statements, Schluss-Sätze
- INTERAKTION (WICHTIGSTE Regel - so hebt sich das Video von Konkurrenz ab):
  Die Caption ist kein Aufkleber, sie REAGIERT auf das Gesagte - das Video soll
  LEBEN. Steckt Bewegung, Wucht oder Veraenderung im Satz, gib MUTIG die
  passende Animation; ein reaktives Video ist besser als ein stilles. Die
  Mehrheit der starken Momente darf sich bewegen. Ueberspring den Effekt NUR
  bei klar bildlicher/beilaeufiger Nutzung ("mir explodiert der Kopf vor Ideen"
  = ruhig) oder ganz neutralem Text - dort kein falscher Effekt. Im Zweifel:
  lieber lebendig als steif. Die Regeln gelten in JEDER Sprache: erkenne die
  HANDLUNG, egal ob deutsch oder englisch.
  ORT (fx + szene + lage):
    "hinter mir" / "behind me"        -> fx "behind"
    "auf dem Boden/der Strasse" / "on the ground/floor" -> fx "ground", szene "boden", lage "liegend"
    "ueber mir" / "above me" / "am Himmel" / "in the sky" -> fx "behind", szene "himmel"
    "an der Wand" / "on the wall"      -> fx "ground", szene "wand", lage "stehend"
    "im Wasser" / "in the water"       -> fx "ground", szene "wasser", lage "liegend"
  HANDLUNG (anim) - DE und EN, jedes Aktions-/Wucht-Wort loest den Effekt aus:
    faellt/sinkt/drops/falls/sinks/crashes                 -> "sturz"
    steigt/waechst/rises/grows/soars/climbs/skyrockets     -> "anstieg"
    zerbricht/shatter/breaks/cracks/collapses              -> "bruch"
    explodiert/explodes/bursts/blows up                    -> "explosion"
    knallt/pop/boom/punch/bang/wumms/Pointe                -> "zoom_punch"
    fliegt/schiesst/flies/shoots/races/rushes/instant      -> "spur"
    verschwindet/disappears/gone/vanishes                  -> "schwund"
    Sog/zieht an/pulls/draws/magnet                        -> "magnet"
    regnet/faellt herab/rain/drips/pours                   -> "regen"
    endgueltig/beschlossen/final/official/stamped/proof    -> "stempel"
    Last/Zwang/erdrueckt/pressure/weight/crushing          -> "druck"
    Staerke/Macht/Wucht/power/strength/heavy               -> "gewicht"
  Denk pro Moment mit: Was TUT das Wort? Passt eine Bewegung, dann gib sie -
  das Wort tut im Bild, was es sagt. Diese Reaktionen funktionieren in JEDER
  Einstellung, auch im Talking-Head. Setz sie regelmaessig ein, damit das Video
  atmet - nur nicht auf harmlosen/bildlichen Woertern.
- AKTION-WORT ALS KEYWORD (Ausnahme sticht "keine Verben"): Wenn die HANDLUNG
  selbst der Kern des Satzes ist - imperativ/meta wie "the word flies",
  "broken should shatter", oder ein Aktions-Satz wie "prices crash", "sales
  explode" - DARFST du das Aktion-Wort selbst als Keyword waehlen (n=1, auch ein
  Verb) und ihm die passende Animation geben (flies->spur, explodes->explosion,
  shatter/broken->bruch, crash->sturz). Aber nur wenn die Handlung wirklich
  gemeint ist - nicht bei beilaeufiger oder bildlicher Erwaehnung. Gibt es ein
  klares OBJEKT, das die Handlung erleidet ("die Mieten steigen"), nimm lieber
  das Objekt + Anim.
- SELBSTBEZUG AUF DIE CAPTIONS: Spricht der Sprecher ueber die Captions oder
  Woerter SELBST ("meine Captions explodieren", "watch this word fly", "der
  Text zerbricht gleich"), dann MUSS genau diese Caption die angesagte Handlung
  ausfuehren (explodieren -> "explosion", fliegen -> "spur", zerbrechen ->
  "bruch", verschwinden -> "schwund") - sofern es zum Moment passt. Das ist der
  staerkste Beweis, dass das Video lebt: der Zuschauer sieht sofort, die
  Captions HOEREN zu.
  In diesen Selbstbezug-Saetzen ist die Sperrliste AUSGESETZT: waehle die
  angesagte Handlung oder den angesagten Ort SELBST als Keyword ("behind me",
  "explode"), auch wenn es Verb, Praeposition oder Pronomen ist - der Satz
  handelt von der Caption, also zeigt die Caption genau das. Orts-Ansagen
  ("the captions are behind me" -> Keyword "behind me" mit fx "behind";
  "die Untertitel liegen auf dem Boden" -> fx "ground", szene "boden",
  lage "liegend") bekommen fx/szene/lage nach der ORT-Tabelle oben.
  Ein Selbstbezug-Satz darf NIE ohne Moment bleiben.
- SICHTBARKEIT VOR VERSTECKEN: Ein Wort, dessen ANIMATION der Punkt ist (es
  soll explodieren, zerbrechen, fliegen, stuerzen), darf NICHT fx "behind" sein
  - hinter der Person und gedimmt sieht man den Effekt nicht. Waehle dann eine
  SICHTBARE Platzierung: "ground" (grosses Statement, liegt frei im Bild),
  "outline" oder "cascade" (vorne, klar sichtbar). "behind" nur fuer ruhige,
  dramatische Hoehepunkte OHNE bewegte Animation. Kurz: soll man die Bewegung
  SEHEN, gehoert das Wort nach VORN, nicht hinter die Person.
- AUDIO-DYNAMIK (der Sound entscheidet mit): In der Wortliste ist der ECHTE
  Sprech-Pegel markiert - ein "!" hinter einem Wort heisst, der Sprecher wird
  hier LAUT/betont (Stimmspitze), ein "~" heisst leise/zurueckgenommen. Koppel
  deine Wahl daran: laute Woerter (!) sind starke Moment-Kandidaten - hoehere
  "power", wuchtigere Effekte/Animationen (explosion, zoom_punch, bruch,
  anstieg), sie tragen die Energie. Leise Woerter (~) bekommen ruhige,
  zurueckhaltende Behandlung (cascade, schweben, kleine power) oder gar keinen
  Moment. So sitzt die Wucht der Caption genau dort, wo auch die Stimme sie
  setzt - das Video fuehlt sich echt an. Der Pegel ist ein starker Hinweis,
  kein Zwang: ein inhaltlich schwaches lautes Fuellwort bleibt trotzdem tabu.
- "power": 1 (dezent), 2 (normal), 3 (Hoehepunkt des Videos, maximal ein bis zwei 3er).
- Optional "anim", NUR wenn der Inhalt es verlangt. Verfuegbar:
  "glitch" (Fehler, Hack, Schock) · "puls" (Herz, Beat, Energie) · \
"welle" (Wasser, Fluss, Ruhe) · "zittern" (Angst, Stress, Chaos) · \
"neon" (Nacht, Stadt, Licht) · "schub" (Wachstum, Durchbruch, Power) · \
"bruch" (etwas bricht, zerfaellt, scheitert) · "sturz" (faellt, sinkt, Absturz, \
Verlust, Rezession) · "anstieg" (steigt, Rekord, Gewinn, teurer) · \
"wende" (kippt, Umkehr, Gegenteil, ploetzlich) · "druck" (Last, Zwang, Schulden, \
erdrueckt) · "schwund" (verschwindet, verloren, vorbei) · \
"knall" (Pointe, Fakt, Beweis, endgueltig) · \
"gewicht" (Staerke, Macht, Wucht - der Strich wird fetter) · \
"schweben" (Ruhe, Eleganz, Luxus, Raum - dezente 3D-Drift) · \
"fokus" (Klarheit, Erkenntnis, praezise - kommt scharf ins Bild) · \
"enthuellen" (Geheimnis, Wahrheit, aufgedeckt - wird freigewischt) · \
"spur" (Tempo, rasant, sofort - schiesst herein mit Nachzieher) · \
"kippen" (Buch kippt auf, Kapitel-Beginn, oeffnet sich) · \
"explosion" (explodiert, sprengt, zerreisst - radialer Aufschlag) · \
"magnet" (Sog, Anziehung, sammelt, buendelt - Streifen ziehen zusammen) · \
"wackel" (Cartoon, Witz, lustig, kindisch - Sinus-Wobble) · \
"regen" (regnet, faellt, tropft, rieselt - Streifen fallen von oben) · \
"zoom_punch" (Punchline, achtung, wumms - kurzer harter Push) · \
"rutsche" (rutscht, gleitet, slidet seitlich - Streifen von rechts) · \
"stempel" (endgueltig, offiziell, beschlossen, geprueft - knallt drauf wie Stempel).
WICHTIG: Die Animation richtet sich nach dem, was im SATZ passiert - auch wenn das \
Keyword selbst nur der Handelnde oder das Opfer ist.
Beispiel: "Deutschland bricht seine Versprechen" -> Keyword "Deutschland" bekommt \
"anim": "bruch" (das Wort zerbricht sichtbar).
Beispiel: "die Mieten steigen ins Unermessliche" -> Keyword "Mieten" bekommt "anim": "anstieg".
Beispiel: "unser Umsatz explodiert" (bildlich = starkes Wachstum) -> "anim": "schub"; \
"die Bombe explodiert" (woertlich) -> "anim": "explosion". Waehle nach der \
GEMEINTEN Handlung - und nur wenn sie wirklich der Punkt des Moments ist.
- Optional "emoji": EIN einzelnes Unicode-Emoji das die Aussage untermalt. \
Nur wenn es wirklich passt - kein Deko-Zwang. Beispiele: \
Geld/Umsatz "💰" · Wachstum "🚀" · Absturz "📉" · Rekord "🏆" · Schock "⚠️" · \
Zeit "⏰" · Herz/Emotion "❤️" · Fakt/Beweis "✅" · Verbot "🚫" · Idee "💡" · \
Sieg "🔥" · Krise "🆘". Kein Emoji bei neutralem Text.
- ZAHLEN: nur eine MENGE ist ein Zahl-Moment (Betrag, Anzahl, Prozent, \
"14 Milliarden", "87 Prozent", "850 Euro"). Jahreszahlen, Datum und Uhrzeiten \
sind KEINE Menge und zaehlen NICHT hoch - "2026" ist ein Label. Markiere ein \
Jahr hoechstens als normalen Moment, nie als Zaehler.
- SOUND-ANIMATIONEN (bruch, sturz, anstieg, wende, druck, schwund, knall) loesen \
einen hoerbaren Effekt aus. Vergib sie NUR, wenn die Handlung wirklich im Satz \
steht ("bricht", "faellt", "steigt", ...). Steht sie nicht da: KEINE Animation. \
Lieber kein Effekt als ein falscher Sound auf einem harmlosen Wort.
- AKTUELLER SHORT-FORM-STANDARD (viral, 2026 - so schneidet die Spitze heute):
  * HOOK in Sekunde 0-2: der erste sichtbare Moment ist der staerkste Reiz -
    Zahl, steile These oder Widerspruch. Nie mit Aufwaermen anfangen.
  * 2-3 Wort-Chunks, die 600-900 ms stehen - kein Wort-Ping-Pong (liest sich
    billig), keine ganzen Saetze (liest sich wie Fernsehen).
  * NUR das Schluesselwort betont, nicht der halbe Satz. Ein Highlight sticht
    nur, wenn drumherum Ruhe ist.
  * Bewegung mit Absicht: der Effekt bebildert die AUSSAGE (steigt->anstieg,
    bricht->bruch), er ist keine Deko. Ein ruhiger Moment ist besser als ein
    zappelnder ohne Grund.
  * ESKALATION: die groessten Momente (power 3) sitzen spaet, auf der Pointe/
    Aufloesung - nicht alles vorne verschiessen.
  * KEIN Muster zweimal hintereinander: Effekt-Typ, Wucht und Rhythmus wechseln,
    sonst stumpft das Auge ab (Muster-Bruch = Kern moderner Retention).
  Wenn dir STIL-REFERENZEN mitgegeben werden, richte dich an ihrem Geschmack aus
  (Auswahl, Dichte, Wucht) - kopiere aber nie deren Woerter, nur den Stil.
Antworte NUR mit JSON: {"keywords": [{"i": <Startindex>, "n": <1-4>, "fx": "<Effekt>", "power": <1-3>, "anim": "<optional>", "emoji": "<optional>"}]}"""


STYLE_LEARN_PROMPT = (
    "Du siehst mehrere Frames aus EINEM kurzen Video mit hochwertigen Captions. "
    "Analysiere DETAILLIERT den Caption- und Schnitt-STIL als Vorbild fuer eine "
    "Caption-Regie - KEINE Inhalte, KEINE Woerter abtippen. Gehe auf JEDEN Punkt "
    "kurz ein (je 1 knapper Satz, als Handlungsanweisung 'Startet mit ...', "
    "'Nutzt ...'):\n"
    "1) HOOK: Wie startet das Video in den ersten 1-2 Sekunden?\n"
    "2) CHUNKS: Wie viele Woerter pro Caption, wie lange stehen sie?\n"
    "3) BETONUNG: Welche Art Woerter wird hervorgehoben (Zahlen, Aktionen, "
    "Pointen, Namen)? Wie oft (Dichte)?\n"
    "4) TYPO/PLATZIERUNG: Groesse, Position (mittig/unten/hinter Person), "
    "Farb-Akzente, Umriss/Schatten?\n"
    "5) BEWEGUNG: Welche Art Animation/Effekte (dezent vs. wuchtig, "
    "Kamera-Bewegung, Zoom-Punches)?\n"
    "6) RHYTHMUS/RETENTION: Wie wechselt die Intensitaet, gibt es Muster-Brueche, "
    "eskaliert es zum Ende?\n"
    "Antworte auf Deutsch, nur der Analyse-Text, mit den Nummern."
)


def _ref_audio_summary(video_path):
    """v96v: analysiert die AUDIOSPUR des Referenz-Videos (Vision hoert nichts).
    Rein lokal aus der Wellenform: Schlag-/Betonungs-Dichte, Beat-Regelmaessigkeit,
    Laut-Leise-Dynamik. Gibt einen knappen Prosa-Satz zurueck (oder '')."""
    import wave as _wave
    import tempfile as _tf
    wavp = _tf.NamedTemporaryFile(suffix='.wav', delete=False).name
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', video_path,
                        '-ac', '1', '-ar', '22050', wavp], check=True, timeout=60)
        with _wave.open(wavp, 'rb') as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        sig = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if len(sig) < sr:                       # <1s Audio -> nichts Belastbares
            return ''
        win = max(1, sr // 20)                  # 50ms
        n = len(sig) // win
        rms = np.sqrt(np.array([np.mean(sig[i * win:(i + 1) * win] ** 2)
                                for i in range(n)], dtype=np.float32) + 1e-9)
        d = np.clip(np.diff(rms, prepend=rms[:1]), 0, None)
        pos = d[d > 0]
        thr = float(np.quantile(pos, 0.9)) if pos.size else 0.0
        hits = int((d > thr).sum()) if thr > 0 else 0
        dur = len(sig) / float(sr)
        hpm = hits / max(dur / 60.0, 1e-6)      # Schlaege pro Minute
        dyn = float(rms.max() / (np.median(rms) + 1e-9))
        dens = 'hoch' if hpm > 40 else 'mittel' if hpm > 18 else 'niedrig'
        dynd = 'starke' if dyn > 4 else 'moderate' if dyn > 2 else 'flache'
        return (f"7) AUDIO/SFX (aus der Tonspur gemessen): ~{hpm:.0f} betonte "
                f"Schlaege/Minute (Dichte {dens}), {dynd} Laut-Leise-Dynamik - "
                f"halte die SFX-Dichte/Wucht sinngemaess aehnlich.")
    except Exception:
        return ''
    finally:
        try:
            os.remove(wavp)
        except OSError:
            pass


def analyze_reference_video(video_path, name=None, model='gpt-4o',
                            n_frames=6, save=True):
    """v96n: Lernt aus einem REFERENZ-Video mit High-End-Captions. Sampelt ein
    paar Frames, laesst GPT-4o-Vision den STIL beschreiben (Pacing, Dichte,
    betonte Woerter, Effekt-Wucht, Hook) und legt das als Stil-Referenz in
    regie_reference.json ab. WICHTIG/EHRLICH: die Regie-KI uebernimmt daraus
    EDITORIALE Entscheidungen (wo + wie stark), NICHT den exakten Look - Fonts,
    Animationen und Kamera kommen aus unserer Engine, nicht aus dem Referenz-
    video. Gibt den Eintrag zurueck oder None."""
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not os.path.exists(video_path):
        return None
    import requests
    try:
        dur = float(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', video_path],
            capture_output=True, text=True, timeout=20).stdout.strip() or 0)
    except Exception:
        dur = 0
    frames = []
    for k in range(max(n_frames, 1)):
        t = (dur * (k + 0.5) / n_frames) if dur > 0 else k * 1.0
        b = _frame_b64(video_path, t)
        if b:
            frames.append(b)
    if not frames:
        return None
    content = [{'type': 'text', 'text': STYLE_LEARN_PROMPT}]
    for b in frames:
        content.append({'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b}',
                                      'detail': 'low'}})
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}'},
            json=_oai_json(model, [{'role': 'user', 'content': content}],
                           max_toks=400, temperature=0.3, json_mode=False),
            timeout=120)
        r.raise_for_status()
        desc = r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Stil-Lernen nicht verfuegbar ({type(e).__name__})")
        return None
    if not desc:
        return None
    # v96v: Audio/SFX separat aus der Tonspur analysieren (Vision hoert nichts)
    aud = _ref_audio_summary(video_path)
    if aud:
        desc = desc + "\n" + aud
    entry = {'name': (name or os.path.splitext(os.path.basename(video_path))[0])[:60],
             'beispiel': desc}
    # v96y/z: MESSBARE Parameter aus Beschreibung + FRAMES ziehen (Farbe/Dichte
    # praezise) - die wirken deterministisch auf die Render-Config (sichtbar).
    params = _style_params_from_desc(desc, model, key, frames=frames)
    if params:
        entry['params'] = params
    if save:
        path = _reference_store_path()
        try:
            refs = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
            if not isinstance(refs, list):
                refs = []
        except Exception:
            refs = []
        refs.append(entry)
        try:
            json.dump(refs[-12:], open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)   # max 12 Referenzen halten
        except Exception as e:
            print(f"Referenz nicht gespeichert ({type(e).__name__})")
    print(f"Stil-Referenz gelernt: {entry['name']}")
    return entry


def _reference_store_path():
    """v96w: gelernte Stil-Referenzen liegen im PERSISTENTEN DATA-Ordner
    (DVE_DATA), NICHT im Git-Repo - sonst wuerde jeder Deploy (Docker-Rebuild)
    die Datei mit der Repo-Version ueberschreiben und das Gelernte waere weg.
    Genau das war der Grund, warum die KI das Gelernte nicht anwandte."""
    data = os.environ.get('DVE_DATA')
    if data:
        try:
            os.makedirs(data, exist_ok=True)
        except Exception:
            pass
        return os.path.join(data, 'regie_reference.json')
    return os.path.join(HERE, 'regie_reference.json')


def _load_regie_reference():
    """v96m: STIL-REFERENZEN. Ismet kann Beispiele hinterlegen (Trend-Bezug), an
    denen sich die Regie-KI ausrichtet - Geschmack/Dichte/Wucht, NICHT die
    Woerter. Liest ZUERST die gelernten (persistent, DATA), sonst die im Repo
    mitgelieferten Defaults. Gibt einen fertigen Prompt-Block oder '' zurueck."""
    path = _reference_store_path()
    if not os.path.exists(path):
        path = os.path.join(HERE, 'regie_reference.json')   # mitgelieferte Defaults
    if not os.path.exists(path):
        return ''
    try:
        refs = json.load(open(path, encoding='utf-8'))
    except Exception:
        return ''
    if not isinstance(refs, list) or not refs:
        return ''
    lines = []
    # v96x: die NEUESTEN 6 (der Store haengt neue hinten an und haelt refs[-12:];
    # refs[:6] nahm die aeltesten - ab der 7. Referenz fiel das frisch Gelernte
    # aus dem Prompt).
    for r in refs[-6:]:
        if not isinstance(r, dict):
            continue
        bsp = str(r.get('beispiel', '')).strip()
        if not bsp:
            continue
        nm = str(r.get('name', '')).strip()
        lines.append(f"- {nm + ': ' if nm else ''}{bsp}")
    if not lines:
        return ''
    return ("STIL-REFERENZEN (aktuelle, starke Videos): Diese Referenzen sind "
            "VERBINDLICH fuer Dichte, Chunk-Laenge, Wucht und Hook-Verhalten - "
            "richte deine Auswahl messbar daran aus und weiche nur ab, wo harte "
            "Regeln (Sperrliste, Sichtbarkeit) es verlangen. Kopiere NIE deren "
            "Woerter, nur den Stil:\n"
            + '\n'.join(lines) + "\n\n")


def _style_params_from_desc(desc, model='gpt-4o', key=None, frames=None):
    """v96y/z: extrahiert MESSBARE Stil-Parameter - mit den Original-FRAMES
    (Vision, praezise Farben/Groessen), sonst nur aus der Prosa. Die Parameter
    wirken deterministisch auf die Render-Config - so wird der Referenz-Stil
    KOPIERT, nicht nur als weicher Prompt-Hinweis gereicht. {} bei Problemen."""
    key = key or os.environ.get('OPENAI_API_KEY')
    if not key or not desc:
        return {}
    import requests
    ask = ("Du siehst Frames eines Videos mit Premium-Captions plus eine "
           "Stilbeschreibung. Extrahiere die Parameter als json: "
           "{\"words_per_group\": <1-5, Woerter pro Caption>, "
           "\"min_gap_seconds\": <3-15, Sekunden zwischen Highlights - hohe "
           "Dichte = kleiner Wert>, \"hook_strength\": <0.0-1.0, wie aggressiv "
           "der Anfang ist>, \"wucht\": \"ruhig\"|\"normal\"|\"wuchtig\", "
           "\"accent_hex\": <\"#RRGGBB\" der dominanten Highlight-Farbe der "
           "Captions, oder null wenn keine klare Akzentfarbe>, "
           "\"density\": \"akzente\"|\"durchgehend\" (stehen nur einzelne "
           "Highlights oder laufen Captions durchgehend)}. Nur das JSON.\n\n"
           "BESCHREIBUNG:\n" + desc)
    content = [{'type': 'text', 'text': ask}]
    for b in (frames or [])[:4]:
        content.append({'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b}',
                                      'detail': 'low'}})
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}'},
            json=_oai_json(model, [{'role': 'user', 'content': content}],
                           max_toks=200, temperature=0.0),
            timeout=90)
        r.raise_for_status()
        data = json.loads(r.json()['choices'][0]['message']['content'])
        out = {}
        try:
            out['words_per_group'] = min(max(int(data.get('words_per_group')), 1), 5)
        except Exception:
            pass
        try:
            out['min_gap_seconds'] = min(max(float(data.get('min_gap_seconds')), 3.0), 15.0)
        except Exception:
            pass
        try:
            out['hook_strength'] = min(max(float(data.get('hook_strength')), 0.0), 1.0)
        except Exception:
            pass
        if str(data.get('wucht', '')).lower() in ('ruhig', 'normal', 'wuchtig'):
            out['wucht'] = str(data['wucht']).lower()
        hx = str(data.get('accent_hex') or '').strip()
        if re.fullmatch(r'#?[0-9a-fA-F]{6}', hx):
            out['accent_hex'] = '#' + hx.lstrip('#').lower()
        if str(data.get('density', '')).lower() in ('akzente', 'durchgehend'):
            out['density'] = str(data['density']).lower()
        return out
    except Exception as e:
        print(f"  Stil-Parameter uebersprungen ({type(e).__name__})")
        return {}


def _reference_params():
    """v96y: gemittelte Stil-Parameter der neuesten Referenzen (die 'params'
    tragen). {} wenn keine vorhanden - dann bleibt die Config unangetastet."""
    path = _reference_store_path()
    if not os.path.exists(path):
        path = os.path.join(HERE, 'regie_reference.json')
    try:
        refs = json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}
    if not isinstance(refs, list):
        return {}
    ps = [r.get('params') for r in refs[-6:]
          if isinstance(r, dict) and isinstance(r.get('params'), dict)]
    if not ps:
        return {}
    out = {}
    for k in ('words_per_group', 'min_gap_seconds', 'hook_strength'):
        vals = [p[k] for p in ps if isinstance(p.get(k), (int, float))]
        if vals:
            out[k] = sum(vals) / len(vals)
    wu = [p.get('wucht') for p in ps if p.get('wucht')]
    if wu:
        out['wucht'] = max(set(wu), key=wu.count)
    # v96z: Look-Merkmale - Akzentfarbe (RGB gemittelt) + Caption-Dichte
    cols = []
    for p in ps:
        hx = str(p.get('accent_hex') or '').lstrip('#')
        if re.fullmatch(r'[0-9a-fA-F]{6}', hx):
            cols.append(tuple(int(hx[k:k + 2], 16) for k in (0, 2, 4)))
    if cols:
        out['accent'] = [int(sum(c[k] for c in cols) / len(cols))
                         for k in range(3)]
    de = [p.get('density') for p in ps if p.get('density')]
    if de:
        out['density'] = max(set(de), key=de.count)
    return out


def _apply_reference_params(cfg):
    """v96y: wendet die Referenz-Parameter DETERMINISTISCH auf die Config an -
    Chunk-Laenge, Highlight-Dichte, Hook-Aggressivitaet, Wucht. Der Effekt ist
    damit sichtbar/messbar, unabhaengig davon wie stark GPT den Prompt-Hinweis
    gewichtet. Gibt eine Log-Zeile zurueck (oder '')."""
    p = _reference_params()
    if not p:
        return ''
    parts = []
    if 'words_per_group' in p:
        v = int(round(p['words_per_group']))
        cfg['effects']['words_per_group'] = v
        cfg['effects']['words_per_group_max'] = max(v + 2, 3)
        parts.append(f"chunks={v}")
    if 'min_gap_seconds' in p:
        v = round(float(p['min_gap_seconds']), 1)
        cfg['keywords']['min_gap_seconds'] = v
        parts.append(f"gap={v}s")
    if 'hook_strength' in p:
        v = round(float(p['hook_strength']), 2)
        cfg['effects']['hook_strength'] = v
        parts.append(f"hook={v}")
    if p.get('wucht'):
        w = p['wucht']
        # Wucht wirkt auf Kamera-Staerke + SFX-Pegel (gedeckelt, kein Extrem)
        if w == 'wuchtig':
            cfg['camera']['strength'] = min(float(cfg['camera'].get('strength', 0.7)) + 0.15, 1.0)
            cfg['effects']['sfx_volume'] = min(float(cfg['effects'].get('sfx_volume', 0.6)) + 0.1, 1.0)
        elif w == 'ruhig':
            cfg['camera']['strength'] = max(float(cfg['camera'].get('strength', 0.7)) - 0.2, 0.2)
            cfg['effects']['sfx_volume'] = max(float(cfg['effects'].get('sfx_volume', 0.6)) - 0.15, 0.2)
        parts.append(f"wucht={w}")
    # v96z: LOOK kopieren - Akzentfarbe der Referenz wird zur Caption-
    # Akzentfarbe (feste Farbe schlaegt adaptive Szenen-Toene), Dichte
    # (akzente vs durchgehend) wird uebernommen.
    if p.get('accent'):
        cfg.setdefault('colors', {})['accent'] = list(p['accent'])
        cfg['colors']['adaptive'] = False
        parts.append('farbe=#%02x%02x%02x' % tuple(p['accent']))
    if p.get('density'):
        cfg['effects']['density'] = p['density']
        parts.append(f"dichte={p['density']}")
    return 'Stil-Anker: ' + ', '.join(parts) if parts else ''


def _ref_fingerprint():
    """v96x/y: Fingerprint der EFFEKTIVEN Referenz-Datei (Block + Parameter).
    Steht im Regie-Cache (_regie3.json) - aendert sich irgendwas am Gelernten,
    ist der Cache ungueltig und die KI plant neu mit den aktuellen Referenzen."""
    import hashlib
    path = _reference_store_path()
    if not os.path.exists(path):
        path = os.path.join(HERE, 'regie_reference.json')
    try:
        raw = open(path, 'rb').read()
    except Exception:
        raw = b''
    return hashlib.md5(raw).hexdigest()


def parse_regie(text, words, language='de'):
    import json as _json
    if language in (None, '', 'auto'):          # v94: 'auto' aus Inhalt aufloesen
        language = 'de' if _looks_german(words) else 'en'
    non_de = language != 'de'
    try:
        data = _json.loads(text)
        out = {}
        for item in data.get('keywords', []):
            i = int(item.get('i', -1))
            fx = str(item.get('fx', '')).strip().lower()
            try:
                power = min(max(int(item.get('power', 2)), 1), 3)
            except Exception:
                power = 2
            try:
                n = min(max(int(item.get('n', 1)), 1), 4)
            except Exception:
                n = 1
            if 0 <= i < len(words) and fx in ('behind', 'cascade', 'blurin', 'outline', 'ground'):
                n = min(n, len(words) - i)
                UNITS = {'euro', 'dollar', 'cent', 'prozent', 'milliarden', 'millionen',
                         'tausend', 'billionen', 'jahre', 'jahren', 'kilo', 'gramm',
                         'meter', 'kilometer', 'stunden', 'minuten', 'sekunden', 'tonnen'}
                def phrase_ok(w):
                    raw = clean(w).strip()
                    if not raw:
                        return False
                    if raw[0].isupper() or raw[0].isdigit() or raw.lower() in UNITS:
                        return True
                    # Sprachen ohne Substantiv-Grossschreibung: Inhaltswoerter
                    # duerfen klein sein ("dynamic pricing"), Kleinwoerter nicht
                    return non_de and raw.isalpha() and len(raw) > 3
                CONNECTORS = {'im', 'in', 'am', 'an', 'auf', 'der', 'die', 'das',
                              'dem', 'den', 'des', 'mit', 'von', 'vom', 'zum', 'zur',
                              'zu', 'fuer', 'für', 'und', 'of', 'to', 'the', 'at',
                              'on', 'for', 'and'}
                m = 1
                while m < n:
                    raw = clean(words[i + m]['word'])
                    if phrase_ok(raw) or raw.lower() in CONNECTORS:
                        m += 1                 # Bindewoerter ("im", "to") sind ok
                    else:
                        break                  # Verben brechen ab: "Deutschland nimmt" -> n=1
                n = m
                while n > 1 and not phrase_ok(clean(words[i + n - 1]['word'])):
                    n -= 1                     # Phrase endet nie auf einem Bindewort
                toks = [clean(words[j]['word']).lower() for j in range(i, i + n)]
                if any(t and t not in STOPWORDS for t in toks):
                    entry = {'fx': fx, 'power': power, 'n': n}
                    sz = str(item.get('szene', '')).strip().lower()
                    if sz in ('wasser', 'boden', 'wand', 'himmel', 'person', 'unklar'):
                        entry['szene'] = sz
                    lg = str(item.get('lage', '')).strip().lower()
                    if lg in ('liegend', 'stehend', 'frei'):
                        entry['lage'] = lg
                    anim = str(item.get('anim', '')).strip().lower()
                    if anim in ANIM_LIST:
                        entry['anim'] = anim
                        # v94: Sichtbarkeit erzwingen (kein Anim-Zwang, nur
                        # Platzierung). Eine bewegte Aktion hinter der Person
                        # ("behind") sieht man nicht -> nach vorn holen.
                        if anim in _VISIBLE_ANIM and entry['fx'] == 'behind':
                            entry['fx'] = 'outline'
                    emo = str(item.get('emoji', '')).strip()
                    # nur echte Emoji-Bereiche zulassen, kein Text/HTML
                    if emo and 1 <= len(emo) <= 4 and any(
                            0x1F000 <= ord(c) <= 0x1FFFF or 0x2600 <= ord(c) <= 0x27BF
                            for c in emo):
                        entry['emoji'] = emo
                    out[i] = entry
        return out or None
    except Exception:
        return None

def _regie_chunks(words, max_words=400, overlap=30):
    """Teilt lange Transkripte in Regie-Haeppchen an Satzgrenzen.
    Globale Wort-Indizes bleiben erhalten; kurze Videos = genau ein Chunk.

    Overlap (v80d): jeder Nicht-Anfangs-Chunk beginnt 30 Woerter frueher als
    das eigentliche Fenster. So sieht die KI Kontext links vom Satz - Momente
    an Chunk-Grenzen werden nicht mehr verschluckt. Bei doppelter Erwaehnung
    gewinnt in der merge-Schleife der letzte Chunk."""
    if len(words) <= max_words:
        return [(0, len(words), 0)]
    chunks, start = [], 0
    while start < len(words):
        end = min(start + max_words, len(words))
        if end < len(words):
            for j in range(end - 1, max(end - 80, start), -1):
                if words[j]['word'].rstrip().endswith(('.', '!', '?')):
                    end = j + 1
                    break
        ctx_start = max(0, start - overlap) if chunks else start
        chunks.append((ctx_start, end, start))     # (Kontext-Start, Ende, Auswahl-Start)
        start = end
    return chunks


def _regie_validate(fx_map, words, model, key):
    """Zwei-Pass-Validator: gpt-4o kriegt seine eigenen Vorschlaege zurueck und
    prueft, ob wirklich Substanz-Woerter markiert wurden. Streicht Hilfsverben,
    Fuellwoerter und generische Phrasen die durch die erste Runde geschluepft
    sind. Kostet einen zweiten Call, faengt aber die "IST/DENN"-Klasse
    strukturell ab. Bei Netzfehler bleibt fx_map unveraendert."""
    import requests
    if not fx_map:
        return fx_map
    entries = []
    for i in sorted(fx_map):
        v = fx_map[i]
        n = int(v.get('n', 1))
        txt = ' '.join(clean(words[j]['word'])
                       for j in range(i, min(i + n, len(words))))
        ctx_a = max(0, i - 4); ctx_b = min(len(words), i + n + 4)
        ctx = ' '.join(clean(words[j]['word']) for j in range(ctx_a, ctx_b))
        entries.append({'i': i, 'text': txt, 'im_satz': ctx})
    prompt = (
        "Du bist Qualitaets-Pruefer fuer Video-Captions. Du bekommst eine Liste "
        "vorgeschlagener Highlights. Pruefe JEDES einzeln:\n"
        "STREICHE es (in 'entfernen': [i, ...]) wenn es ist:\n"
        "  - ein Hilfsverb (ist, hat, wird, kann, ...),\n"
        "  - eine Konjunktion (denn, weil, aber, dann, ...),\n"
        "  - ein Pronomen (ich, du, das, was, ...),\n"
        "  - eine Praeposition (in, an, auf, mit, ...),\n"
        "  - ein generisches Fuellwort (sache, thema, dinge, hier),\n"
        "  - eine Phrase die auf Fuellwort endet (z.B. 'Deutschland nimmt').\n"
        "BEHALTE alles was Substanz traegt (Zahlen, Namen, Fakten, Objekte, "
        "emotionale Spitzen).\n"
        "Antworte NUR mit JSON: {\"entfernen\": [<Index>, ...]}"
    )
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}'},
            json=_oai_json(model,
                           [{'role': 'system', 'content': prompt},
                            {'role': 'user', 'content': json.dumps(
                                entries, ensure_ascii=False)}],
                           max_toks=800, temperature=0.0),
            timeout=90)
        r.raise_for_status()
        data = json.loads(r.json()['choices'][0]['message']['content'])
        drop = {int(i) for i in data.get('entfernen', []) if i in fx_map}
        if drop:
            for i in drop:
                fx_map.pop(i, None)
            print(f"  Validator: {len(drop)} Fehl-Highlights gestrichen")
        else:
            print(f"  Validator: alle {len(entries)} Highlights bestaetigt")
    except Exception as e:
        print(f"  Validator uebersprungen ({type(e).__name__})")
    return fx_map


def _word_loudness(words, voice_wav_path):
    """v95: Sprech-Pegel PRO WORT fuer die KI-Regie. Markiert die lautesten
    Substanz-Woerter (!) und die leisesten (~), damit GPT Effekt/Motion/Wucht
    an die ECHTE Stimme koppeln kann - nicht nur an den Text. Reiner RMS aus
    der vorhandenen wav (50ms-Fenster), keine Extra-Modelle. Gibt
    {wort_index: '!'|'~'} nur fuer auffaellige waehlbare Woerter zurueck; bei
    fehlender/kaputter wav ein leeres dict (dann laeuft die Regie wie bisher)."""
    out = {}
    if not words or not voice_wav_path or not os.path.exists(voice_wav_path):
        return out
    try:
        import wave
        with wave.open(voice_wav_path, 'rb') as wf:
            sr = wf.getframerate()
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if sw != 2:
            return out
        samp = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if nch > 1:
            samp = samp.reshape(-1, nch).mean(axis=1)
        win = max(1, sr // 20)               # 50ms-Fenster (feiner als _audio_boost)
        n_win = len(samp) // win
        if n_win < 4:
            return out
        rms = np.sqrt(np.array([np.mean(samp[i * win:(i + 1) * win] ** 2)
                                for i in range(n_win)], dtype=np.float32) + 1e-9)
        vals = {}
        for i, w in enumerate(words):
            raw_w = clean(w['word'])
            if raw_w.lower() in STOPWORDS or not raw_w.strip():
                continue                     # nur waehlbare Substanz-Woerter
            s = float(w.get('start', 0.0))
            e = float(w.get('end', s + 0.3))
            k0 = max(0, int(s * 20) - 1)
            k1 = min(n_win, int(e * 20) + 3)  # bis +150ms Nachhall
            band = rms[k0:k1]
            if band.size:
                vals[i] = float(band.max())
        if len(vals) < 4:
            return out
        arr = np.array(list(vals.values()), dtype=np.float32)
        hi = float(np.quantile(arr, 0.80))    # top 20% = laut
        lo = float(np.quantile(arr, 0.30))    # untere 30% = leise
        for i, v in vals.items():
            if v >= hi:
                out[i] = '!'
            elif v <= lo:
                out[i] = '~'
    except Exception as e:
        print(f"  Wort-Lautstaerke uebersprungen ({type(e).__name__})")
    return out


def _audio_boost(fx_map, words, voice_wav_path):
    """Audio-Emotion (v80d): wo der Sprecher laut/betont wird, bekommt der
    nahe Moment einen Power-Bump. Nutzt nur die vorhandene wav - keine extra
    Modelle. Konservativ: bumpt nur um 1 Stufe, nie ueber 3."""
    if not fx_map or not voice_wav_path or not os.path.exists(voice_wav_path):
        return fx_map
    try:
        import wave
        with wave.open(voice_wav_path, 'rb') as wf:
            sr = wf.getframerate()
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if sw == 2:
            samp = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            return fx_map
        if nch > 1:
            samp = samp.reshape(-1, nch).mean(axis=1)
        # RMS pro 100ms-Fenster
        win = max(1, sr // 10)
        n_win = len(samp) // win
        if n_win < 2:
            return fx_map
        rms = np.array([np.sqrt(np.mean(samp[i * win:(i + 1) * win] ** 2))
                        for i in range(n_win)], dtype=np.float32)
        thr = float(np.quantile(rms, 0.85))    # top 15% = "laut"
        bumped = 0
        for i in list(fx_map):
            t = words[i].get('start', 0)
            k = int(t * 10)                    # 100ms-Bins
            band = rms[max(0, k - 2):min(n_win, k + 6)]  # -200ms .. +500ms
            if band.size and float(band.max()) >= thr:
                cur = int(fx_map[i].get('power', 2))
                if cur < 3:
                    fx_map[i]['power'] = cur + 1
                    bumped += 1
        if bumped:
            print(f"  Audio-Emotion: {bumped} Momente lauter -> Power hoch")
    except Exception as e:
        print(f"  Audio-Emotion uebersprungen ({type(e).__name__})")
    return fx_map

def _cap_power3(fx_map, keep=2):
    """Video-weite Regel auch bei Chunk-Analyse: maximal zwei power-3-Momente
    (der frueheste als Hook und der spaeteste als Abschluss bleiben)."""
    threes = sorted(i for i, v in fx_map.items() if v.get('power') == 3)
    if len(threes) > keep:
        keepers = {threes[0], threes[-1]}
        for i in threes:
            if i not in keepers:
                fx_map[i]['power'] = 2
    return fx_map


# Animationen mit EIGENEM Effekt-Sound (siehe sfx_engine.ANIM_SFX). Genau die
# duerfen nicht geraten werden: sitzt ein 'bruch' auf einem Wort, das nichts
# zerbricht, knallt ein Schwert/Glas-Sound daneben.
_SFX_ANIMS = ('bruch', 'sturz', 'anstieg', 'wende', 'druck', 'schwund', 'knall')

def _regie_sanity(fx_map, words):
    """Deterministische Leitplanke NACH der KI-Regie (kein GPT noetig).
    Sound-Animationen bleiben nur stehen, wenn ihr Ausloeser wirklich im
    Keyword ODER im Satz-Kontext vorkommt (gleiche Vokabel wie anim_for).
    Sonst wird die Animation entfernt - der Moment bleibt, nur der falsche
    Sound faellt weg. So verstehen wir den Satz wenigstens strukturell."""
    if not fx_map:
        return fx_map
    hints = dict(ANIM_HINTS)
    dropped = 0
    for i in list(fx_map):
        anim = fx_map[i].get('anim')
        if anim in _SFX_ANIMS:
            n = int(fx_map[i].get('n', 1))
            a = max(0, i - 4); b = min(len(words), i + n + 5)
            ctx = ' '.join(clean(words[j].get('word', '')) for j in range(a, b))
            if not any(_anim_hit(ctx, k) for k in hints.get(anim, ())):
                fx_map[i].pop('anim', None)
                dropped += 1
    if dropped:
        print(f"  Regie-Check: {dropped} unpassende Sound-Animation(en) entfernt")
    return fx_map


# Selbst-referenzielle Orts-/Lage-Ansagen im Gesprochenen. Sagt der Sprecher,
# WO das Wort hin soll, MUSS die Caption das abbilden - genau das ist "der Text
# interagiert mit dem Satz", nicht billig draufgeklatscht. (fx, szene, lage,
# Trigger-Phrasen - Mehrwort, als Teilstring im Kontext gesucht.)
_INTENT_SPATIAL = (
    ('behind', '',       '',        ('hinter mir', 'hinter uns', 'hinter dir',
                                     'hinter mich', 'behind me', 'behind us',
                                     'behind you')),
    ('ground', 'himmel', '',        ('ueber mir', 'ueber uns', 'ueberm kopf',
                                     'über mir', 'über uns', 'überm kopf',
                                     'am himmel', 'in den himmel', 'in the sky',
                                     'above me', 'above us', 'up above',
                                     'over my head')),
    ('ground', 'boden',  'liegend', ('auf dem boden', 'am boden', 'auf der strasse',
                                     'auf der straße', 'auf die strasse',
                                     'auf der strase', 'auf den boden', 'am boden liegt',
                                     'on the ground', 'on the floor', 'on the street',
                                     'on the pavement', 'on the road')),
    ('ground', 'wasser', 'liegend', ('im wasser', 'auf dem wasser', 'in the water',
                                     'on the water', 'unter wasser')),
    ('ground', 'wand',   'stehend', ('an der wand', 'an die wand', 'on the wall',
                                     'against the wall')),
)

def _speech_intent(fx_map, words):
    """Wenn der Sprecher die Position des Wortes beschreibt ('hinter mir',
    'auf dem Boden', 'ueber mir/am Himmel'), setzt die Caption GENAU das um -
    egal was die generische Effekt-Wahl vorschlug. So folgt der Text dem, was
    gesagt wird. Deterministisch; ueberstimmt nur bei eindeutiger Ansage.
    Hinweis 'himmel' nutzt fx 'behind' + szene 'himmel' (steigt ueber den Kopf)."""
    if not fx_map:
        return fx_map
    n_w = len(words)

    def _tok(j):
        return clean(words[j].get('word', '')).lower()

    def _satzende(j):
        return str(words[j].get('word', '')).rstrip().endswith(('.', '!', '?'))

    hat_punkt = any(_satzende(j) for j in range(n_w))
    hits = 0
    for i in list(fx_map):
        n = int(fx_map[i].get('n', 1))
        # Die Ansage gilt nur im SELBEN Satz wie das Keyword. Sonst zieht
        # "hinter mir." aus dem Vorsatz das naechste Wort mit um ("STREET"
        # direkt nach "behind me." wuerde faelschlich hinter die Person gehen).
        if hat_punkt:
            a = i
            while a > 0 and not _satzende(a - 1):
                a -= 1
            b = min(i + n - 1, n_w - 1)
            while b < n_w - 1 and not _satzende(b):
                b += 1
            b += 1
        else:
            a = max(0, i - 3); b = min(n_w, i + n + 4)
        toks = [_tok(j) for j in range(a, b)]
        # Bei mehreren Ansagen im Satz gewinnt die naechste am Keyword.
        best = None
        for fx, szene, lage, triggers in _INTENT_SPATIAL:
            for trig in triggers:
                tt = trig.split()
                L = len(tt)
                for k in range(0, len(toks) - L + 1):
                    if toks[k:k + L] == tt:
                        dist = min(abs((a + k) - i),
                                   abs((a + k + L - 1) - (i + n - 1)))
                        if best is None or dist < best[0]:
                            best = (dist, fx, szene, lage)
        if best is None:
            continue
        _, fx, szene, lage = best
        # 'himmel' lebt hinter der Person und steigt ueber den Kopf
        fx_map[i]['fx'] = 'behind' if szene == 'himmel' else fx
        if szene:
            fx_map[i]['szene'] = szene
        if lage:
            fx_map[i]['lage'] = lage
        hits += 1
    if hits:
        print(f"  Sprach-Intent: {hits} Caption(s) folgen der Ansage "
              f"(hinter/Boden/Himmel/Wasser/Wand)")
    return fx_map


# v99 Selbstbezug: Woran wir erkennen, dass ueber die CAPTIONS SELBST
# gesprochen wird. Eindeutige Woerter zaehlen immer; mehrdeutige (Wort/Text)
# nur mit Artikel davor ('this word', 'der Text') - 'ich gebe dir mein Wort'
# ist ein Versprechen, kein Selbstbezug.
_SELF_NOUN_ONE = {'caption', 'captions', 'untertitel', 'subtitle', 'subtitles'}
_SELF_NOUN_PAIR = {'wort', 'worte', 'woerter', 'wörter', 'word', 'words',
                   'text', 'texte'}
_SELF_DET = {'the', 'this', 'these', 'der', 'die', 'das', 'den',
             'dieses', 'diese', 'dieser'}
# Animationen, die eine angesagte HANDLUNG sichtbar ausfuehren koennen
_SELF_ACTION_ANIMS = ('explosion', 'bruch', 'spur', 'schwund', 'sturz',
                      'anstieg', 'regen', 'magnet', 'zittern', 'kippen',
                      'rutsche')


def _self_ref_intent(fx_map, words):
    """v99: 'The captions are behind me' / 'meine Untertitel explodieren' -
    spricht der Sprecher ueber die Captions SELBST und sagt, wo sie sind oder
    was sie tun, bekommt GENAU dieser Satz seinen Moment. Die KI-Sperrliste
    laesst in solchen Saetzen oft kein Keyword zu (behind/me/are sind alle
    verboten), und ohne API-Key gibt es gar keine KI-Wahl - darum erzeugt
    dieser deterministische Backstop den Moment notfalls selbst. Orts-Ansagen
    nutzen dieselbe Tabelle wie _speech_intent, Handlungen dieselben Vokabeln
    wie anim_for. Laeuft in ALLEN Pfaden (KI, Regie-Cache, Heuristik)."""
    if not words:
        return fx_map
    out = dict(fx_map) if fx_map else {}
    n_w = len(words)

    def _tok(j):
        return clean(words[j].get('word', '')).lower()

    def _ende(j):
        return str(words[j].get('word', '')).rstrip().endswith(('.', '!', '?'))

    saetze, a = [], 0
    for j in range(n_w):
        if _ende(j) or j == n_w - 1:
            saetze.append((a, j))
            a = j + 1
    hints = dict(ANIM_HINTS)
    neu = 0
    for (a, b) in saetze:
        toks = [_tok(j) for j in range(a, b + 1)]
        ref_at = None
        for k, t in enumerate(toks):
            if t in _SELF_NOUN_ONE or (t in _SELF_NOUN_PAIR and k > 0
                                       and toks[k - 1] in _SELF_DET):
                ref_at = k
                break
        if ref_at is None:
            continue
        # 1) Orts-Ansage im Satz (nahe am Selbstbezug)?
        tgt = None
        for fx, szene, lage, triggers in _INTENT_SPATIAL:
            for trig in triggers:
                tt = trig.split()
                L = len(tt)
                for k in range(0, len(toks) - L + 1):
                    if toks[k:k + L] == tt and abs(k - ref_at) <= 8:
                        tgt = ('ort', k, L, fx, szene, lage)
                        break
                if tgt:
                    break
            if tgt:
                break
        # 2) sonst: angesagte Handlung (gleiches Vokabular wie anim_for)
        if tgt is None:
            for k, t in enumerate(toks):
                if not t or abs(k - ref_at) > 8:
                    continue
                for anim in _SELF_ACTION_ANIMS:
                    if any(_anim_hit(t, key) for key in hints.get(anim, ())):
                        tgt = ('tat', k, 1, anim, '', '')
                        break
                if tgt:
                    break
        if tgt is None:
            continue
        kind, k, L, val, szene, lage = tgt
        vorhandene = [i for i in out if a <= i <= b]
        if vorhandene:
            # Es gibt schon einen Moment im Satz: nur die Handlung ergaenzen
            # (Orts-Ansagen hat _speech_intent dort bereits umgesetzt).
            i0 = min(vorhandene, key=lambda i: abs(i - (a + k)))
            if kind == 'tat' and not out[i0].get('anim'):
                out[i0]['anim'] = val
                if out[i0].get('fx') == 'behind' and val in _VISIBLE_ANIM:
                    out[i0]['fx'] = 'outline'   # Bewegung muss man SEHEN
                neu += 1
            continue
        i = a + k
        if kind == 'ort':
            ent = {'fx': 'behind' if szene == 'himmel' else val,
                   'power': 2, 'n': max(1, min(L, 4))}
            if szene:
                ent['szene'] = szene
            if lage:
                ent['lage'] = lage
        else:
            # Sichtbar vorn (nie behind) - die Bewegung IST der Punkt.
            ent = {'fx': 'outline', 'power': 2, 'n': 1, 'anim': val}
        out[i] = ent
        neu += 1
    if neu:
        print(f"  Selbstbezug: {neu} Caption(s) tun, was der Sprecher ansagt")
        return out
    return fx_map


def _corrections_path():
    return os.path.join(os.environ.get('DVE_DATA') or os.path.join(HERE, 'data'),
                        'corrections.json')

def _load_corrections(path=None):
    """Global gelernte Korrekturen (aus frueheren Momente-Editor-Edits)."""
    try:
        data = json.load(open(path or _corrections_path(), encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _norm_phrase(s):
    return ' '.join(clean(w).lower() for w in str(s or '').split() if clean(w))

def _apply_corrections(fx_map, words, corrections):
    """Phase 2 'aus Fehlern lernen' (global, deterministisch): wo der Nutzer
    dieselbe Phrase schon einmal anders wollte - anderer Effekt, Animation
    entfernt/gesetzt, oder Moment ganz deaktiviert - zieht die KI-Wahl jetzt
    automatisch dorthin nach. Braucht kein GPT. Die juengste Korrektur pro
    Phrase gewinnt."""
    if not fx_map or not corrections:
        return fx_map
    by_phrase = {}
    for c in corrections:
        p = _norm_phrase(c.get('phrase', ''))
        if p:
            by_phrase[p] = c                    # spaetere ueberschreiben fruehere
    applied = 0
    for i in list(fx_map):
        n = int(fx_map[i].get('n', 1))
        phrase = _norm_phrase(' '.join(clean(words[j].get('word', ''))
                              for j in range(i, min(i + n, len(words)))))
        c = by_phrase.get(phrase)
        if not c:
            continue
        if c.get('user_aktiv') is False:        # Nutzer hatte den Moment geloescht
            fx_map.pop(i, None); applied += 1; continue
        if c.get('user_fx') and c['user_fx'] != fx_map[i].get('fx'):
            fx_map[i]['fx'] = c['user_fx']; applied += 1
        if 'user_anim' in c:
            if c['user_anim']:
                fx_map[i]['anim'] = c['user_anim']
            else:
                fx_map[i].pop('anim', None)
            applied += 1
    if applied:
        print(f"  Gelernt: {applied} Korrektur(en) aus frueheren Edits angewandt")
    return fx_map

def _looks_german(words):
    """v94: Rate die Sprache aus dem Transkript. Bei language='auto' wurde alles
    als Deutsch behandelt (non_de=False) - dann verwarf der Phrasen-Filter
    englische Kleinbuchstaben-Woerter ('flies', 'shatter') und die Deutsch-
    Regeln passten nicht. Diese Heuristik laeuft auch auf gecachten Transkripten
    (kein Whisper-Aufruf noetig)."""
    txt = ' ' + ' '.join(w.get('word', '') for w in words).lower() + ' '
    if any(c in txt for c in 'äöüß'):
        return True
    de = (' der ', ' die ', ' das ', ' und ', ' ist ', ' nicht ', ' ein ',
          ' den ', ' dem ', ' mit ', ' auf ', ' fuer ', ' wir ', ' ich ',
          ' sich ', ' auch ', ' eine ', ' werden ', ' haben ')
    return sum(txt.count(m) for m in de) >= 3


def ai_direct(words, language, model='gpt-4o', voice_wav=None, validate=True):
    """LLM waehlt Keywords, Phrasen, Effekte und Wucht. Gibt {index: info} zurueck oder None.
    Lange Videos werden in Etappen analysiert, damit die JSON-Antwort nie abgeschnitten wird.

    v80d: WORTLISTE ohne STOPWORDS an gpt-4o - die KI KANN Hilfsverben gar
    nicht mehr waehlen. Chunks mit 30-Wort-Overlap. Zwei-Pass-Validator und
    Audio-Emotion optional (validate=True, voice_wav gesetzt)."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return None
    # v94: 'auto' aus dem Inhalt aufloesen, damit Nicht-Deutsch (z.B. Englisch)
    # die richtigen Regeln bekommt (Kleinbuchstaben-Keywords erlaubt).
    if language in (None, '', 'auto'):
        language = 'de' if _looks_german(words) else 'en'
    chunks = _regie_chunks(words)
    lang_hint = '' if language in ('de', 'auto', None, '') else \
        f"SPRACHE: Das Transkript ist nicht deutsch ({language}). " \
        f"Wende die Regeln sinngemaess auf diese Sprache an.\n\n"
    # v95: echten Sprech-Pegel pro Wort holen, damit die KI Effekt/Wucht am
    # Sound koppelt (! = laut/betont, ~ = leise). Fehlt die wav, bleibt es leer.
    loud = _word_loudness(words, voice_wav) if voice_wav else {}
    ref_block = _load_regie_reference()      # v96m: Stil-Referenzen (Trend-Bezug)
    # v96x: BEWEIS im Job-Log, ob Referenzen wirklich in den Prompt fliessen -
    # vorher war ein leerer/verlorener Block unsichtbar ("KI wendet nichts an").
    if ref_block:
        _n_refs = sum(1 for l in ref_block.splitlines() if l.startswith('- '))
        print(f"Stil-Referenzen: {_n_refs} aktiv - fliessen in die KI-Regie ein")
    else:
        print("Stil-Referenzen: keine gefunden (Regie laeuft ohne Stil-Anker)")
    merged = {}
    for ci, (a, b, sel) in enumerate(chunks):
        part = words[a:b]
        prose = ' '.join(w['word'].strip() for w in part)
        part_hint = '' if len(chunks) == 1 else \
            f"HINWEIS: Dies ist Teil {ci + 1} von {len(chunks)} eines laengeren Videos. " \
            f"Die Wort-Indizes sind global und gelten wie angegeben. " \
            f"Waehle nur Momente ab Index {sel} (davor ist nur Kontext)." \
            + (" Der Hook liegt in diesem Teil." if ci == 0 else "") \
            + (" Der Abschluss liegt in diesem Teil." if ci == len(chunks) - 1 else "") + "\n\n"
        # Wortliste-Filter: Fuellwoerter werden nicht mehr angeboten, damit die
        # KI sie nicht waehlen kann. Original-Indizes bleiben erhalten.
        wl_toks = []
        for i, w in enumerate(part, start=a):
            raw = clean(w['word'])
            if raw.lower() in STOPWORDS or not raw.strip():
                continue
            wl_toks.append(f"[{i}]{raw}{loud.get(i, '')}")   # v95: Pegel-Marke
        pegel_hint = ('\n\nPEGEL: "!" = hier wird der Sprecher LAUT/betont '
                      '(Stimmspitze), "~" = leise/zurueckgenommen. Koppel '
                      'Effekt und Wucht daran (siehe AUDIO-DYNAMIK).'
                      if loud else '')
        listing = ref_block + lang_hint + part_hint + 'TRANSKRIPT:\n' + prose + \
                  '\n\nWORTLISTE (nur waehlbare Substanz-Woerter, ' \
                  'Fuellwoerter wurden entfernt):\n' + ' '.join(wl_toks) + pegel_hint
        try:
            r = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}'},
                json=_oai_json(model,
                               [{'role': 'system', 'content': REGIE_PROMPT},
                                {'role': 'user', 'content': listing}],
                               max_toks=3000, temperature=0.2),
                timeout=120)
            r.raise_for_status()
            res = parse_regie(r.json()['choices'][0]['message']['content'], words, language)
            if res:
                # Overlap-Bereich: Momente aus dem Kontext-Vorlauf verwerfen,
                # der vorherige Chunk hat sie bereits (oder bewusst uebergangen).
                if ci > 0:
                    res = {i: v for i, v in res.items() if i >= sel}
                merged.update(res)
            if len(chunks) > 1:
                print(f"  KI-Regie Etappe {ci + 1}/{len(chunks)}: "
                      f"{len(res) if res else 0} Momente")
        except Exception as e:
            print(f"KI-Regie Etappe {ci + 1}/{len(chunks)} nicht verfuegbar "
                  f"({type(e).__name__})" if len(chunks) > 1 else
                  f"KI-Regie nicht verfuegbar ({type(e).__name__}), nutze Automatik.")
    if not merged:
        return None
    if validate:
        merged = _regie_validate(merged, words, model, key)
    if voice_wav:
        merged = _audio_boost(merged, words, voice_wav)
    merged = _regie_sanity(merged, words)
    merged = _speech_intent(merged, words)          # Text folgt der Ansage
    merged = _apply_corrections(merged, words, _load_corrections())  # Nutzer gewinnt zuletzt
    return _cap_power3(merged) if merged else None

# ---- Zahlen: nicht jede Zahl ist eine Aussage.
# "zwei Sachen", "erstens", "um drei Uhr" -> Fuellwort.
# "3 Millionen Umsatz", "87 Prozent", "10x" -> DAS ist der Moment.
ZAHLWORT = {
    'null': 0, 'eins': 1, 'eine': 1, 'einen': 1, 'zwei': 2, 'drei': 3, 'vier': 4,
    'fuenf': 5, 'fünf': 5, 'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9,
    'zehn': 10, 'elf': 11, 'zwoelf': 12, 'zwölf': 12, 'zwanzig': 20,
    'dreissig': 30, 'dreißig': 30, 'vierzig': 40, 'fuenfzig': 50, 'fünfzig': 50,
    'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90, 'hundert': 100,
    'tausend': 1000, 'million': 1e6, 'millionen': 1e6, 'milliarde': 1e9,
    'milliarden': 1e9,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
    'eight': 8, 'nine': 9, 'ten': 10, 'twenty': 20, 'fifty': 50,
    'hundred': 100, 'thousand': 1000, 'million': 1e6, 'billion': 1e9,
}
# Einheiten direkt an der Zahl: machen sie sofort zur Aussage.
ZAHL_EINHEIT = {'prozent', '%', 'euro', 'eur', '€', 'dollar', 'usd', '$', 'grad',
                'million', 'millionen', 'milliarde', 'milliarden', 'tausend',
                'mio', 'mrd', 'percent', 'k', 'x', 'mal', 'fach', 'stunden',
                'jahre', 'jahren', 'tage', 'tagen', 'monate', 'monaten',
                'sekunden', 'minuten', 'kilo', 'kg', 'meter', 'km'}
# Wertwoerter im Umfeld: eine Zahl daneben traegt Gewicht.
ZAHL_KONTEXT = {'umsatz', 'gewinn', 'verlust', 'wachstum', 'kosten', 'preis',
                'rekord', 'kunden', 'follower', 'abonnenten', 'views', 'klicks',
                'marge', 'rendite', 'invest', 'investment', 'budget', 'bewertung',
                'gehalt', 'einkommen', 'schulden', 'markt', 'anteil', 'quote',
                'steigerung', 'zuwachs', 'rueckgang', 'rückgang', 'absturz',
                'verdoppelt', 'verdreifacht', 'gespart', 'verdient', 'verloren',
                'revenue', 'profit', 'growth', 'sales', 'users', 'subscribers'}
# Aufzaehlung/Uhrzeit: nie ein Moment.
ZAHL_TABU = {'erstens', 'zweitens', 'drittens', 'uhr', 'punkt', 'first', 'second',
             'third', 'nummer', 'schritt', 'teil', 'kapitel'}


def _zahl_wert(t):
    """Numerischer Wert eines Wortes - als Ziffer oder ausgeschrieben. None = keine Zahl."""
    s = t.lower().strip().replace('.', '').replace(',', '.')
    s2 = ''.join(c for c in s if c.isdigit() or c == '.')
    if s2 and any(c.isdigit() for c in t):
        try:
            return float(s2)
        except ValueError:
            return None
    return ZAHLWORT.get(t.lower().strip())


def zahl_relevanz(words, i):
    """Wie sehr traegt diese Zahl die Aussage? 0 = keine Caption.

    Bewusst streng: eine Caption bei JEDER Zahl waere Laerm. Ausgeloest wird nur
    bei Substanz - grosse/gerundete Zahlen, Prozent, Waehrung, Faktor, Jahreszahl
    mit Aussage, oder eine Zahl direkt neben einem Wertwort."""
    t = clean(words[i]['word'])
    wert = _zahl_wert(t)
    if wert is None:
        return 0.0
    low = t.lower()
    if low in ZAHL_TABU:
        return 0.0
    umfeld = []
    for j in range(max(i - 3, 0), min(i + 4, len(words))):   # Wertwort steht oft 3 Woerter weiter
        if j == i:
            continue
        umfeld.append(clean(words[j]['word']).lower().strip('.,!?%'))
    if any(u in ZAHL_TABU for u in umfeld[:2]):
        return 0.0                       # "Schritt 3", "um 8 Uhr"
    direkt = set(umfeld)
    einheit = (any(z in low for z in ('%', '€', '$'))
               or any(u in ZAHL_EINHEIT for u in direkt))
    kontext = any(u in ZAHL_KONTEXT for u in direkt)
    # Jahreszahl ohne Einheit: nur mit Wertwort im Umfeld ein Moment. "das war
    # 2019 damals so" ist Beiwerk - "2019 lag der Umsatz hoeher" ist die Aussage.
    if 1900 <= wert <= 2100 and float(wert).is_integer() and not einheit:
        return 1.3 if kontext else 0.0
    r = 0.0
    if einheit:
        r += 1.0
    if wert >= 1000:            # grosse Zahl traegt fast immer
        r += 1.0
    elif wert >= 100:
        r += 0.5
    if kontext:
        r += 0.9
    # Kleine, nackte Zahl ohne alles: Fuellwort ("zwei Sachen", "drei Punkte")
    if wert < 100 and r < 0.5:
        return 0.0
    return min(r, 2.5)


def detect_keywords(words, cfg, cli_keywords):
    manual = set()
    if cli_keywords:
        manual = {k.strip().lower() for k in cli_keywords.split(',') if k.strip()}
    include = {k.lower() for k in cfg['keywords'].get('include', []) or []} | manual
    exclude = {k.lower() for k in cfg['keywords'].get('exclude', []) or []}
    kw = set()
    for i, w in enumerate(words):
        t = clean(w['word'])
        low = t.lower()
        if low in exclude or low in STOPWORDS: continue
        if low in include:
            kw.add(i); continue
        if not cfg['keywords'].get('auto', True): continue
        sent_start = i == 0 or words[i - 1]['word'].rstrip().endswith(('.', '!', '?'))
        if _zahl_wert(t) is not None:
            # Frueher wurde JEDE Ziffer zum Keyword - das erzeugt Laerm und
            # verdraengt die Zahl, auf die es ankommt. Jetzt zaehlt die Substanz;
            # ausgeschriebene Zahlen ("drei Millionen") werden mitgenommen.
            if zahl_relevanz(words, i) > 0:
                kw.add(i)
            continue
        if t and t[0].isupper() and (not sent_start and len(t) > 3 or sent_start and len(t) > 7):
            kw.add(i)
    if cfg['keywords'].get('emphasize_last', True) and len(words) > 1:
        t_last = clean(words[len(words) - 2]['word']).lower()
        if t_last not in STOPWORDS and t_last not in exclude:
            kw.add(len(words) - 2)
    return kw

def build_groups(words, max_words=3, min_hold=0.0, hard_max=5):
    """Wortgruppen wie ein Cutter: nie ueber Satzgrenzen hinweg. Whisper liefert
    auf Wort-Ebene keine Satzzeichen, also zaehlen Sprechpausen als Grenze."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        pause = (i + 1 < len(words)
                 and words[i + 1]['start'] - w['end'] > 0.35)
        if (len(cur) == max_words or pause
                or w['word'].rstrip().endswith(('.', ',', '?', '!'))):
            groups.append(cur); cur = []
    if cur: groups.append(cur)
    # Premium-Pacing 2026: zu kurze Chunks (Wort-Ping-Pong) lesen sich billig.
    # 2-4 Woerter, die 600-900 ms stehen bleiben, sind der aktuelle Standard -
    # das Auge kommt mit, die Aussage bleibt haengen.
    if min_hold > 0 and words:
        merged = []
        for g in groups:
            if merged:
                prev = merged[-1]
                pw = words[prev[-1]]
                dauer = pw['end'] - words[prev[0]]['start']
                luecke = words[g[0]]['start'] - pw['end']
                satzende = pw['word'].rstrip().endswith(('.', '!', '?'))
                if (dauer < min_hold and not satzende and luecke <= 0.35
                        and len(prev) + len(g) <= hard_max):
                    merged[-1] = prev + g
                    continue
            merged.append(list(g))
        groups = merged
    return groups

def music_beats(voice_wav, n_frames, fps):
    """Musik-Beat-Erkennung (Kick + Snare). Rueckgabe: (beat_env, bpm, conf).

    beat_env: 0..1 pro Videoframe, spike auf jedem Beat, weicher Ausklang.
    bpm:      geschaetztes Tempo (int) oder 0.
    conf:     0..1 wie sicher ein Beat vorliegt. Bei purem Talking-Head ohne
              Musik ist conf klein -> die Kopplung wirkt nicht (Selbstschutz).

    Algorithmus ohne librosa: (1) Sub-Bass-Onset (Amplitude-Delta auf
    Tiefpass < 200 Hz) fuer Kick, (2) Auto-Korrelation der Onset-Reihe im
    Tempo-Bereich 60-180 BPM fuer den Grundschlag, (3) Confidence aus dem
    Auto-Korrelations-Peak vs. Rauschboden.
    """
    try:
        import wave
        wf = wave.open(voice_wav, 'rb')
        sr = wf.getframerate()
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        wf.close()
        x = raw.astype(np.float32) / 32768.0
        # Tiefpass ~200 Hz: einfache gleitende Mittelung, greift Kick + Sub.
        k = max(int(sr / 200), 8)
        low = np.convolve(x, np.ones(k, np.float32) / k, mode='same')
        hop = max(int(sr / fps), 1)
        n = min(n_frames, len(low) // hop)
        rms_lo = np.zeros(n_frames, np.float32)
        for i in range(n):
            seg = low[i * hop:(i + 1) * hop]
            rms_lo[i] = np.sqrt(np.mean(seg * seg) + 1e-9)
        # Stille: das eps in sqrt() haelt rms_lo.max() bei ~3e-5 (nicht 0),
        # deshalb auf dem echten Signal pruefen.
        if float(np.abs(x).max()) < 1e-4:
            z = np.zeros(n_frames, np.float32)
            return z, 0, 0.0
        # Onset = positive Amplitude-Steigerung im Sub-Bass
        d = np.diff(rms_lo, prepend=rms_lo[:1])
        onset = np.clip(d, 0, None)
        hi = max(np.percentile(onset[onset > 0], 95) if (onset > 0).any() else 1e-6, 1e-6)
        onset = np.clip(onset / hi, 0, 1)
        # Schwellwert: nur echte Peaks in die Auto-Korrelation. Bei Rauschen bleibt
        # das Signal fast leer -> flache AC -> niedrige Confidence.
        onset_sharp = np.where(onset > 0.4, onset, 0.0).astype(np.float32)
        # Auto-Korrelation im Bereich 60-180 BPM
        min_bpm, max_bpm = 60, 180
        lag_min = max(int(60.0 / max_bpm * fps), 4)          # 20 Frames bei 30 fps, 180 BPM
        lag_max = min(int(60.0 / min_bpm * fps), n_frames // 3)  # 30 Frames bei 30 fps, 60 BPM
        if lag_max <= lag_min + 1:
            return onset, 0, 0.0
        # Zentrierte AC auf dem geschaerften Signal - Harmonische bleiben, aber
        # der Peak sticht deutlicher hervor.
        y = onset_sharp - onset_sharp.mean()
        norm = float(np.dot(y, y)) + 1e-9
        ac = np.zeros(lag_max - lag_min + 1, np.float32)
        for j, lag in enumerate(range(lag_min, lag_max + 1)):
            ac[j] = float(np.dot(y[:-lag], y[lag:])) / norm
        peak_idx = int(np.argmax(ac))
        peak_val = float(ac[peak_idx])
        best_lag = peak_idx + lag_min
        bpm = int(round(60.0 * fps / best_lag)) if best_lag > 0 else 0
        # Confidence: Peak muss aus dem Median-Rauschen herausragen. Kombiniert
        # mit z-score gegen zufaellige Muster (Gauss-Rauschen).
        med_ac = float(np.median(ac))
        std_ac = float(ac.std()) + 1e-9
        pom = (peak_val - med_ac) / max(peak_val, 0.05)      # 0..1, robust vs Harmonics
        z_score = (peak_val - float(ac.mean())) / std_ac      # gegen Rauschen
        conf = max(0.0, min(1.0, pom * min(1.0, (z_score - 1.5) / 3.0)))
        # Beat-Envelope aus den Onset-Peaks: max +0.5/Frame hoch, 0.72 Abklingfaktor.
        env = np.zeros(n_frames, np.float32)
        acc = 0.0
        for i in range(n_frames):
            v = onset[i] if i < len(onset) else 0.0
            acc = max(min(v, acc + 0.5), acc * 0.72)
            env[i] = acc
        return env, bpm, conf
    except Exception:
        z = np.zeros(n_frames, np.float32)
        return z, 0, 0.0


def audio_envelopes(voice_wav, n_frames, fps):
    """Lautstaerke-, Bass- und Onset-Huellkurve pro Videoframe, normalisiert 0..1.
    Damit koennen Texte auf Musik und Stimme reagieren."""
    try:
        import wave
        wf = wave.open(voice_wav, 'rb')
        sr = wf.getframerate()
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        wf.close()
        if wf.getnchannels() if False else False:
            pass
        x = raw.astype(np.float32) / 32768.0
        hop = max(int(sr / fps), 1)
        n = min(n_frames, len(x) // hop)
        rms = np.zeros(n_frames, np.float32)
        bass = np.zeros(n_frames, np.float32)
        # Bass: einfacher Tiefpass (gleitendes Mittel ueber ~5 ms)
        k = max(int(sr * 0.005), 8)
        low = np.convolve(x, np.ones(k, np.float32) / k, mode='same')
        for i in range(n):
            seg = x[i * hop:(i + 1) * hop]
            rms[i] = np.sqrt(np.mean(seg * seg) + 1e-9)
            lseg = low[i * hop:(i + 1) * hop]
            bass[i] = np.sqrt(np.mean(lseg * lseg) + 1e-9)
        def norm(v):
            hi = np.percentile(v[v > 0], 96) if (v > 0).any() else 1.0
            return np.clip(v / max(hi, 1e-6), 0, 1)
        rms, bass = norm(rms), norm(bass)
        d = np.diff(rms, prepend=rms[:1])
        onset = np.clip(d / max(np.percentile(np.abs(d), 97), 1e-6), 0, 1)
        # Onset war roh: Frame-zu-Frame-Sprung der Lautstaerke. Einzelne Spikes
        # (Konsonanten, Plosive) liessen den Text zucken, seit Beat-Sync auf jedem
        # Keyword laeuft. Huellkurve mit schnellem Anstieg / weichem Ausklang:
        # ein echter Akzent kommt durch, ein Ein-Frame-Ausreisser nicht mehr.
        env = np.zeros_like(onset)
        acc = 0.0
        for i in range(len(onset)):
            acc = max(min(onset[i], acc + 0.5), acc * 0.7)   # max +0.5/Frame hoch
            env[i] = acc
        onset = env
        # Glaettung fuer geschmeidiges Pulsieren
        kk = np.ones(3, np.float32) / 3
        bass = np.convolve(bass, kk, mode='same')
        return rms, bass, onset
    except Exception:
        z = np.zeros(n_frames, np.float32)
        return z, z, z


FIRE_PAL = None

def fire_palette():
    global FIRE_PAL
    if FIRE_PAL is None:
        stops = [(0.00, (0, 0, 0)), (0.30, (165, 8, 0)), (0.55, (255, 72, 0)),
                 (0.75, (255, 168, 0)), (0.90, (255, 235, 90)), (1.00, (255, 255, 255))]
        pal = np.zeros((256, 3), np.float32)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            a, b = int(p0 * 255), int(p1 * 255)
            for ch in range(3):
                pal[a:b + 1, ch] = np.linspace(c0[ch], c1[ch], b - a + 1)
        FIRE_PAL = pal
    return FIRE_PAL


def glitch_arr(arr, rng, strength):
    """Digitaler Glitch: verschobene Zeilen-Slices + Farbkanal-Versatz."""
    out = arr.copy()
    h = arr.shape[0]
    for _ in range(int(2 + 5 * strength)):
        y = rng.integers(0, max(h - 14, 1))
        sh = int(rng.integers(4, 15))
        dx = int(rng.integers(6, 26) * strength) * (1 if rng.random() < 0.5 else -1)
        out[y:y + sh] = np.roll(out[y:y + sh], dx, axis=1)
    out[..., 2] = np.roll(out[..., 2], int(3 + 4 * strength), axis=1)
    return out


def compose_phrase(phrase, words, S, W, H, portrait=False, safe=False):
    """Setzt eine Phrase wie ein Magazin-Layout, nach dem Muster hochwertiger
    Social-Edits: Bindewoerter als kleine Akzent-Zeile darueber, der Kern riesig
    in Weiss, ein kleines Abschlusswort kursiv schraeg ueberlappend.
    Jedes Wort erscheint zu seinem eigenen Sprech-Zeitpunkt."""
    CONNECTORS = {'im', 'in', 'am', 'an', 'auf', 'der', 'die', 'das', 'dem', 'den',
                  'des', 'mit', 'von', 'vom', 'zum', 'zur', 'zu', 'fuer', 'für',
                  'und', 'of', 'to', 'the', 'at', 'on', 'for', 'and'}
    toks = []
    for j in phrase:
        raw = clean(words[j]['word'])
        toks.append({'raw': raw, 'up': raw.upper(),
                     'conn': raw.lower() in CONNECTORS, 't': words[j]['start']})

    # Split am letzten Bindewort: davor = Akzent-Zeile, danach = Kern-Lauf
    last_conn = max((k for k, t in enumerate(toks) if t['conn']), default=-1)
    pre, run = toks[:last_conn + 1], toks[last_conn + 1:]
    script = None
    if len(run) >= 2:
        last = run[-1]['raw']
        has_digit_before = any(any(c.isdigit() for c in t['raw']) for t in run[:-1])
        if last[:1].islower() or (has_digit_before and not any(c.isdigit() for c in last)):
            script = run[-1]               # "west" / "1957 West" -> Schreibschrift
            run = run[:-1]
    if not pre and len(run) >= 2 and run[0]['raw'][:1].islower():
        pre, run = [run[0]], run[1:]       # "drei Themen" -> DREI klein, THEMEN gross

    base = int(H * (0.16 if not portrait else 0.085))
    max_w = int(W * (0.86 if not portrait else (0.62 if safe else 0.92)))
    out = []
    core_txt = ' '.join(t['up'] for t in run)
    core_sz = S.fit(core_txt, base, max_w)
    core_arr = S.text(core_txt, core_sz, S.white)[0]          # crisp: kein Glow
    core_h, core_w = core_arr.shape[0], core_arr.shape[1]
    if pre:
        line = ' '.join(t['up'] for t in pre)
        sz = S.fit(line, int(base * 0.34), int(max_w * 0.8))
        arr = S.text(line, sz, S.accent, tracking=2, font=S.f_sans_b)[0]
        out.append({'arr': arr, 'ox': -core_w / 2 + arr.shape[1] / 2 + core_w * 0.02,
                    'oy': -core_h * 0.58, 't': pre[0]['t'], 'role': 'pre'})
    out.append({'arr': core_arr, 'ox': 0.0, 'oy': 0.0,
                't': run[0]['t'], 'role': 'core', 'txt': core_txt, 'sz': core_sz})
    if script:
        sz = S.fit(script['up'].lower().capitalize(), int(base * 0.55), int(max_w * 0.55))
        arr = S.text(script['raw'].capitalize(), sz, S.accent, font=S.f_script)[0]
        out.append({'arr': rot_img(arr, -8), 'ox': W * 0.16,
                    'oy': core_h * 0.40, 't': script['t'], 'role': 'script'})
    return out


_FLOW_CONN = {'im', 'in', 'am', 'an', 'auf', 'aus', 'bei', 'der', 'die', 'das',
              'dem', 'den', 'des', 'ein', 'eine', 'mit', 'von', 'vom', 'zum',
              'zur', 'zu', 'fuer', 'für', 'und', 'ist', 'es', 'so', 'wie', 'was',
              'wir', 'ich', 'du', 'er', 'sie', 'als', 'wenn', 'doch', 'nur',
              'of', 'to', 'the', 'a', 'an', 'at', 'on', 'in', 'for', 'and',
              'is', 'it', 'its', "it's", 'so', 'as', 'do', 'i', 'you', 'we',
              'why', 'how', 'that', 'this', 'not', 'but', 'just', 'my', 'your'}


def compose_flow(g, words, S, W, H, portrait=False, flow_sel=None):
    """v97: Flow-Caption nach den Referenz-Videos (@migs.visuals). Der ganze
    Chunk baut sich INLINE auf (Wort fuer Wort, stehend), mit Hierarchie:
      - Verbinder = Support-Font, normal, weiss (Kleinschreibung wie gesprochen)
      - EIN Anker-Wort (laengstes Inhaltswort) = Display-schwer, GROSS, Glow,
        wird per Schreibmaschine enthuellt (letters mitgegeben)
      - optionales Abschlusswort kleingeschrieben = kursive Serif in Akzentfarbe
    Nutzt die LOOK-Fonts + Akzentfarbe (Hybrid: Filler fliesst, Dramatik bleibt).
    Rueckgabe: (items, total_h, anchor_index_or_None). items tragen absolute
    cx/cy relativ zu einem Block-Ursprung y=0 (Aufrufer verschiebt vertikal)."""
    idxs = list(g)
    cont = [i for i in idxs
            if clean(words[i]['word']).lower().strip(".,!?;:") not in _FLOW_CONN
            and len(clean(words[i]['word'])) >= 2]
    # v97f: KI-Wahl zuerst (GPT waehlt Anker/Akzent inhaltlich, wie ein Editor).
    # Die Laengen-Heuristik bleibt Fallback (kein Key / KI ohne Meinung).
    sel = flow_sel or {}
    anchor = None
    _ka = sel.get('kw')
    if _ka in idxs and len(clean(words[_ka]['word'])) >= 3 \
            and clean(words[_ka]['word']).lower() not in _FLOW_CONN:
        anchor = _ka
    if anchor is None and len(idxs) >= 3 and cont:
        cand = cont[int(np.argmax([len(clean(words[i]['word'])) for i in cont]))]
        if len(clean(words[cand]['word'])) >= 5:
            anchor = cand
    accent = None
    _acc = sel.get('accent')
    if _acc in idxs and _acc != anchor and len(clean(words[_acc]['word'])) >= 3:
        accent = _acc
    if accent is None and 'accent' not in sel and len(idxs) >= 4 and cont:
        last = cont[-1]
        raw_last = clean(words[last]['word'])
        if last != anchor and raw_last[:1].islower() and len(raw_last) >= 3:
            accent = last
    pf = 0.62 if not portrait else 1.0
    sz_n = int(H * 0.050 * pf)
    sz_k = int(H * 0.074 * pf)
    sz_a = int(H * 0.056 * pf)
    items = []
    for i in idxs:
        raw = clean(words[i]['word'])
        if i == anchor:
            up = raw.upper()
            sz = S.fit(up, sz_k, int(W * 0.86), font=S.f_sans_b)
            arr, tw, lets = S.text(up, sz, S.white, font=S.f_sans_b,
                                   glow=True, per_letter=True, tracking=2)
            items.append({'i': i, 'arr': arr, 'w': tw, 'role': 'key',
                          'letters': lets, 't': words[i]['start']})
        elif i == accent:
            cap = raw.lower().capitalize()
            sz = S.fit(cap, sz_a, int(W * 0.5), font=S.f_script)
            arr, tw = S.text(cap, sz, S.accent, font=S.f_script)   # Kursive gibt
            items.append({'i': i, 'arr': arr, 'w': tw, 'role': 'accent',  # den Slant
                          't': words[i]['start']})
        else:
            arr, tw = S.text(raw, sz_n, S.white, tracking=6, font=S.f_sans)
            items.append({'i': i, 'arr': arr, 'w': tw, 'role': 'norm',
                          't': words[i]['start']})
    # Inline-Fluss mit Umbruch, Zeilen unten ausgerichtet (gemeinsame Grundlinie)
    max_w = int(W * 0.86)
    x0 = int(W * 0.07)
    space = int(W * 0.032)
    # STRUKTUR wie in der Referenz: klare Zeilen nach ROLLE statt wildem
    # Breiten-Umbruch. Verbinder-vor-Keyword = Zeile 1, das KEYWORD = eigene
    # Zeile, Rest (inkl. Kursiv-Akzent) = Zeile darunter. Alles LINKS buendig,
    # konstante Zeilenhoehe nach dem groessten Font der Zeile. Vorschub nach
    # echter Textbreite; zentriert wird das symmetrisch gepolsterte Sprite.
    for it in items:
        it['adv'] = it['w']
    rows = []
    if anchor is not None:
        pos = idxs.index(anchor)
        pre = items[:pos]
        key = [items[pos]]
        post = items[pos + 1:]
        if pre:
            rows.append(pre)
        rows.append(key)
        if post:
            rows.append(post)
    else:
        cur = []
        cur_w = 0
        for it in items:
            aw = it['adv']
            if cur and cur_w + space + aw > max_w:
                rows.append(cur)
                cur = []
                cur_w = 0
            cur.append(it)
            cur_w += (space if len(cur) > 1 else 0) + aw
        if cur:
            rows.append(cur)

    def _rsz(it):
        return sz_k if it['role'] == 'key' else (sz_a if it['role'] == 'accent' else sz_n)
    y = 0
    for row in rows:
        line_h = int(max(_rsz(it) for it in row) * 1.20)
        x = x0
        for it in row:
            it['cx'] = x + it['adv'] / 2.0
            it['cy'] = y + line_h / 2.0           # in der Zeilen-Mitte
            x += it['adv'] + space
        y += line_h
    total_h = max(y, 1)
    return items, total_h, anchor


def _parse_flow_sel(data, groups, words):
    """v97f: Validiert die KI-Flow-Wahl. Rueckgabe {g_first_index: {'kw': i,
    'accent': i|None}} - nur Eintraege, deren Indizes wirklich im Chunk liegen
    und Substanz haben. Ungueltiges wird verworfen (Fallback: Heuristik)."""
    out = {}
    if not isinstance(data, dict):
        return out
    by_first = {g[0]: list(g) for g in groups}
    for ch in data.get('chunks', []) or []:
        if not isinstance(ch, dict):
            continue
        try:
            g0 = int(ch.get('g'))
            kw = int(ch.get('kw'))
        except (TypeError, ValueError):
            continue
        g = by_first.get(g0)
        if not g or kw not in g:
            continue
        t = clean(words[kw]['word'])
        if len(t) < 3 or t.lower() in _FLOW_CONN:
            continue
        entry = {'kw': kw, 'accent': None}
        acc = ch.get('accent')
        if acc is not None:
            try:
                acc = int(acc)
            except (TypeError, ValueError):
                acc = None
            if acc is not None and acc in g and acc != kw \
                    and len(clean(words[acc]['word'])) >= 3:
                entry['accent'] = acc
            else:
                acc = None
        out[g0] = entry
    return out


def ai_flow_direct(words, groups, language='de', model='gpt-4o'):
    """v97f: GPT waehlt pro Filler-Chunk das ANKER-Wort (wird gross+getippt)
    und optional ein Akzent-Wort (kursiv, warm) - inhaltlich, wie ein Editor,
    statt Laengen-Heuristik. EIN Call pro Video. None bei fehlendem Key/Fehler."""
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key or not groups:
        return None
    lines = []
    for g in groups:
        toks = ' '.join(f"{j}:{clean(words[j]['word'])}" for j in g)
        lines.append(f"g={g[0]} | {toks}")
    lang_hint = {'de': 'Deutsch', 'en': 'Englisch'}.get(language, language or 'de')
    sysm = ("Du bist Cutter fuer Premium-Social-Edits (Sprache: " + lang_hint + "). "
            "Pro Text-Chunk waehlst du GENAU EIN Anker-Wort 'kw': das "
            "bedeutungstragende Wort, das ein Editor gross setzen wuerde "
            "(Substantiv/Verb/Zahl/Name - traegt die Aussage, NIE Fuellwort). "
            "Optional 'accent': ein weiches emotionales Schlusswort "
            "(Adjektiv/Adverb), sonst null. Nutze die mitgegebenen Indizes. "
            'Antworte NUR mit JSON: {"chunks": [{"g": <g>, "kw": <index>, '
            '"accent": <index|null>}]}')
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}'},
            json=_oai_json(model, [{'role': 'system', 'content': sysm},
                                   {'role': 'user', 'content': '\n'.join(lines)}],
                           max_toks=min(120 + 30 * len(groups), 4000),
                           temperature=0.0),
            timeout=120)
        r.raise_for_status()
        data = json.loads(r.json()['choices'][0]['message']['content'])
    except Exception as e:
        print(f"KI-Flow nicht verfuegbar ({type(e).__name__}), nutze Heuristik.")
        return None
    return _parse_flow_sel(data, groups, words)


def letter_slices(arr, letters):
    """Zerlegt ein Wort-Sprite in Buchstaben-Streifen fuer kinetische Animation."""
    w = arr.shape[1]
    out = []
    for a, b in letters:
        a2, b2 = max(int(a), 0), min(int(b), w)
        if b2 - a2 < 3:
            continue
        sl = arr[:, a2:b2].copy()
        if sl[..., 3].max() < 8:
            continue
        out.append((sl, (a2 + b2) / 2 - w / 2))
    return out

ANIM_HINTS = (('glitch', ('glitch', 'hack', 'fehler', 'error', 'schock', 'crash',
                          'digital', 'bug', 'virus', 'stoerung', 'störung',
                          'ausfall', 'panne', 'gehackt', 'geknackt', 'malware',
                          'cyber', 'system', 'daten', 'leck')),
              ('puls', ('herz', 'beat', 'puls', 'bass', 'energie', 'musik',
                        'rhythmus', 'trommel', 'takt', 'lebendig',
                        'schlaegt', 'schlägt', 'klopft', 'pumpt')),
              ('welle', ('welle', 'wasser', 'meer', 'fluss', 'flow', 'ozean',
                         'stroemung', 'strömung', 'see', 'ufer', 'kueste',
                         'küste', 'nass', 'flut', 'ebbe', 'sturm', 'brandung')),
              ('zittern', ('angst', 'panik', 'nervoes', 'beben', 'stress', 'chaos',
                           'shake', 'shakes', 'shaking', 'tremble',
                           'furcht', 'schreck', 'terror', 'zittert', 'schaudert',
                           'unruhe', 'aufregung', 'hektik', 'druck', 'krise')),
              ('neon', ('neon', 'nacht', 'club', 'leucht', 'glow', 'licht', 'city',
                        'stadt', 'metropole', 'downtown', 'bar', 'party',
                        'strahl', 'grell', 'blitz')),
              ('schub', ('boom', 'schub', 'power', 'wachstum',
                         'durchbruch', 'skalier', 'raketen',
                         'wachsen', 'wächst', 'waechst', 'expandiert',
                         'stark', 'kraftvoll', 'antrieb', 'motor',
                         'beschleunigt', 'zoomt', 'shootet')),
              ('bruch', ('bricht', 'brechen', 'gebrochen', 'zerbricht', 'zerbrochen',
                         'bruch', 'zerfaellt', 'zerfällt', 'kaputt', 'ruin',
                         'kollaps', 'zusammenbruch', 'scheitert', 'gescheitert',
                         'versagt', 'zerstoert', 'zerstört', 'riss', 'scherben',
                         'break', 'broken', 'shatter', 'collapse')),
              ('sturz', ('stuerz', 'stürz', 'sturz', 'absturz', 'faellt', 'fällt',
                         'fallen', 'sinkt', 'sinken', 'einbruch', 'rezession',
                         'pleite', 'verlust', 'abwaerts', 'abwärts',
                         'minus', 'talfahrt', 'billiger', 'weniger',
                         'fall', 'drop', 'crash', 'plunge', 'sink')),
              ('anstieg', ('steigt', 'steigen', 'anstieg', 'rekord', 'gewinn',
                           'zuwachs', 'kletter', 'teurer', 'hoeher', 'höher',
                           'verdoppelt', 'verdreifacht', 'aufwaerts', 'aufwärts',
                           'zunahme', 'rise', 'rises', 'rising', 'grow', 'soar',
                           'climb', 'skyrocket')),
              ('wende', ('kippt', 'wende', 'umkehr', 'gegenteil', 'ploetzlich',
                         'plötzlich', 'umgekehrt', 'kehrtwende', 'umschwung',
                         'dreht', 'wendepunkt', 'stattdessen')),
              ('druck', ('druck', 'last', 'belastung', 'zwang', 'erdrueck',
                         'erdrück', 'schulden', 'buerde', 'bürde', 'kosten',
                         'abgaben', 'steuerlast', 'schwer')),
              ('schwund', ('verschwindet', 'verschwunden', 'verloren',
                           'geloescht', 'gelöscht', 'vorbei', 'verpuff', 'nichts',
                           'aufgeloest', 'aufgelöst', 'schwindet', 'futsch',
                           'dahin', 'disappear', 'vanish', 'gone')),
              ('knall', ('punkt', 'fakt', 'fakten', 'schluss',
                         'basta', 'beweis', 'bewiesen', 'definitiv',
                         'garantiert')),
              ('gewicht', ('stark', 'staerke', 'stärke', 'macht', 'gewicht',
                           'massiv', 'wucht', 'kraft', 'dominanz', 'schwergewicht',
                           'gross', 'groß', 'grosser', 'größer', 'gigant',
                           'riesig', 'riese', 'kolossal', 'enorm', 'gewaltig',
                           'brutal', 'hart', 'monster', 'immens', 'giga')),
              ('schweben', ('ruhe', 'ruhig', 'leicht', 'schwebt', 'frei', 'raum',
                            'traum', 'stille', 'gelassen', 'luxus', 'eleganz')),
              ('fokus', ('fokus', 'klar', 'klarheit', 'scharf', 'erkennt',
                         'begreift', 'versteht', 'sichtbar', 'praezise', 'präzise')),
              ('enthuellen', ('enthuellt', 'enthüllt', 'geheim', 'geheimnis',
                              'wahrheit', 'aufgedeckt', 'zeigt', 'verraten',
                              'offenbart', 'luegt', 'lügt')),
              ('spur', ('schnell', 'tempo', 'rasant', 'sofort', 'blitz', 'rast',
                        'jagt', 'speed', 'eilt', 'sekunden', 'fliegt', 'fliegen',
                        'sausen', 'saust', 'huscht', 'schiesst', 'schießt',
                        'flitz', 'zischt', 'segelt', 'schwebt vorbei',
                        'dash', 'sprint', 'rennen', 'rennt', 'laeuft', 'läuft',
                        'fly', 'flies', 'flying', 'shoot', 'race', 'rush')),
              # ---- v71
              ('kippen', ('kippt', 'kippen', 'klappt', 'aufklappt', 'oeffnet',
                          'öffnet', 'aufgeschlagen', 'kapitel', 'flip', 'tilt',
                          'fold')),
              ('explosion', ('explodiert', 'explosion', 'sprengt', 'gesprengt',
                             'zerstoert', 'zerreist', 'zerreißt', 'detoniert',
                             'blast', 'explod', 'burst', 'detonat')),
              ('magnet', ('zieht', 'anziehung', 'magnet', 'sog', 'sammelt',
                          'buendel', 'bündel', 'fokussiert', 'zieht an',
                          'ballt', 'rein', 'reinkommt', 'reinfliegt',
                          'einsaugt', 'ansaugt', 'zentriert', 'buendeln',
                          'bündeln')),
              ('wackel', ('lustig', 'quatsch', 'unsinn', 'witz', 'komisch',
                          'cartoon', 'kindisch', 'quirlig', 'bounce')),
              ('regen', ('regen', 'faellt', 'tropfen', 'rieselt', 'schuettet',
                         'schüttet', 'niederschlag', 'sturm', 'rain', 'pour',
                         'drip')),
              ('zoom_punch', ('achtung', 'punchline', 'boom', 'wumms', 'plopp',
                              'hier', 'schau', 'guck', 'siehst', 'sehen')),
              ('rutsche', ('rutscht', 'schlittert', 'gleitet', 'slide', 'slidet',
                           'schiebt', 'seitwaerts', 'seitwärts')),
              ('stempel', ('endgueltig', 'endgültig', 'fest', 'siegel',
                           'beschlossen', 'unterschrieben', 'genehmigt', 'stempel',
                           'zertifiziert', 'offiziell', 'approved', 'verified',
                           'geprueft', 'geprüft')))


def _anim_hit(text, key):
    """Wortgenauer Treffer statt blinder Teilstring-Suche.
    'fällt' darf NICHT in 'gefällt' anschlagen ('das gefaellt mir' ist kein Sturz).
    Darum muss der Wortanfang passen. Nur richtig lange Stichwoerter (>=7 Zeichen)
    duerfen auch mitten in Komposita stecken ('Staatsschulden' -> schulden);
    bei kurzen waere genau das die Falle."""
    for tok in re.split(r"[^0-9A-Za-zÄÖÜäöüß]+", text.lower()):
        if not tok:
            continue
        if tok.startswith(key) or (len(key) >= 7 and key in tok):
            return True
    return False


def anim_for(txt, context=None):
    """Waehlt die Animation. Das Keyword allein reicht nicht: bei
    'Deutschland bricht seine Versprechen' steht das Keyword DEUTSCHLAND, aber
    was passiert (brechen), steht drumherum. Darum zaehlt der Satz mit -
    das Keyword hat Vorrang, der Kontext entscheidet, wenn das Wort nichts sagt."""
    for src in (txt, context):
        if not src:
            continue
        for name, keys in ANIM_HINTS:
            if any(_anim_hit(src, k) for k in keys):
                return name
    return None

NUM_RE = re.compile(r"\d[\d.,]*\d|\d")

def make_counter(txt):
    """Erkennt eine Zahl im Text und liefert (fmt(dt)->String, Dauer) oder None.
    "14 MILLIARDEN" zaehlt 0->14, "2,5 PROZENT" zaehlt mit einer Dezimalstelle."""
    m = NUM_RE.search(txt)
    if not m:
        return None
    raw = m.group(0)
    dec_sep = None
    if raw.count(',') == 1 and len(raw.split(',')[1]) <= 2:
        dec_sep = ','
    elif raw.count('.') == 1 and len(raw.split('.')[1]) <= 2:
        dec_sep = '.'
    grp_sep = None
    if dec_sep is None and (raw.count('.') >= 1 or raw.count(',') >= 1):
        grp_sep = '.' if '.' in raw else ','
    try:
        target = float(raw.replace('.', '').replace(',', '.')) if dec_sep == ',' else \
                 float(raw.replace(',', '')) if dec_sep == '.' else \
                 float(raw.replace('.', '').replace(',', ''))
    except ValueError:
        return None
    if target <= 1:
        return None
    # Jahreszahlen sind KEINE Menge - ein Jahr zaehlt nicht von 0 hoch.
    # "im Jahr 2026" soll einfach "2026" zeigen, nicht von 0 auf 2026 rollen
    # (und dabei vorbei sein, bevor die 2026 ueberhaupt steht). 4-stellige
    # Ganzzahl im Jahres-Bereich -> nur anzeigen, nicht zaehlen.
    if dec_sep is None and grp_sep is None and raw.isdigit() and len(raw) == 4 \
            and 1500 <= int(raw) <= 2100:
        return None
    dur = 0.9 if target < 1000 else 1.15

    def fmt(dt):
        e = 1 - (1 - min(dt / dur, 1.0)) ** 3          # ease-out: rollt aus
        v = target * e
        if dec_sep:
            s = f"{v:.1f}".replace('.', dec_sep)
        elif grp_sep:
            s = f"{int(round(v)):,}".replace(',', grp_sep)
        else:
            s = str(int(round(v)))
        return txt[:m.start()] + s + txt[m.end():]
    return fmt, dur


def resolve_overlaps(plans, W, H, exit_lead=0.34):
    """v88: Verhindert, dass zwei Text-Momente gleichzeitig an fast derselben
    Stelle stehen (der SHIBUYA/RIGHT-Doppelbild-Fehler). Ueberlappen sich zwei
    Momente zeitlich - inkl. Abgang (exit_lead) - UND liegen ihre Anker nah
    beieinander (< H*0.16 vertikal, < W*0.42 horizontal), wird das Ende des
    FRUEHEREN so weit vorgezogen, dass er raeumt, bevor der spaetere steht.
    Anker-Naehe schuetzt echte Neben-Platzierungen (links/rechts, oben/unten).
    Wirkt auf Plaene mit 'target'=(x, y); Kamera-Impulse (ohne target) bleiben
    unberuehrt. Rueckgabe: Anzahl vorgezogener Momente."""
    txt = sorted([p for p in plans if 'target' in p],
                 key=lambda p: p.get('t0', p['start']))
    n = 0
    for i in range(len(txt)):
        a = txt[i]
        a_t0 = a.get('t0', a['start'])
        a_end0 = a['end']
        new_end = a_end0
        for b in txt[i + 1:]:
            b_t0 = b.get('t0', b['start'])
            if b_t0 >= a_end0 + exit_lead:
                break                       # sortiert -> ab hier keiner mehr nah
            if b_t0 <= a_t0 + 0.05:
                continue                    # praktisch gleichzeitig gestartet
            if (abs(a['target'][1] - b['target'][1]) < H * 0.16
                    and abs(a['target'][0] - b['target'][0]) < W * 0.42):
                new_end = min(new_end, max(a_t0 + 0.3, b_t0 - 0.12))
        if new_end < a_end0 - 1e-3:
            a['end'] = new_end
            n += 1
    return n


def build_plans(words, kw, cfg, S, W, H, face_ok, fx_map=None, face_pos=None,
                palette_at=None, cut_times=None, faces_at=None, flow_map=None):
    KW_FX = cfg['effects']['keyword_rotation']
    CAM_FX = [m for m in (cfg['camera'].get('keyword_rotation') or []) if m and m != 'none']
    SIDE_MODES = [m for m in (cfg['camera'].get('side_rotation') or []) if m and m != 'none']
    side_every = int(cfg['camera'].get('side_every', 3))
    min_gap = cfg['keywords'].get('min_gap_seconds', 6.0)
    breathing = cfg['effects'].get('breathing', True)
    left_x, right_x = int(W * 0.224), int(W * 0.766)

    def pick_side(start, end, toggle):
        """Waehlt die freie Seite neben der Person und die Text-Position dort.
        Rueckgabe: (side -1/1, cx) - side -1 = links, 1 = rechts. Hochformat: zentriert."""
        if portrait:
            return 0, W / 2
        if face_pos is None:
            cx = left_x if toggle % 2 == 0 else right_x
            return (-1 if cx < W / 2 else 1), cx
        # v96: Sind MEHRERE Gesichter im Bild, den Text in die breiteste Luecke
        # legen, die KEINES der Gesichter ueberdeckt (Multi-Face-Safe-Zone).
        if faces_at is not None:
            _fs = faces_at(start, end)
            if len(_fs) >= 2:
                return _free_x_multi(_fs, W, W * 0.42, toggle)
        fx_x, _, fw = face_pos(start, end)
        person_half = max(fw * 2.1, W * 0.10)
        if abs(fx_x - W / 2) < W * 0.09:
            side = -1 if toggle % 2 == 0 else 1      # Person mittig: abwechseln
        else:
            side = 1 if fx_x < W / 2 else -1          # sonst: immer die freie Seite
        if side < 0:
            edge_in = fx_x - person_half
            cx = max(edge_in / 2, W * 0.13)
        else:
            edge_in = fx_x + person_half
            cx = min((edge_in + W) / 2, W * 0.87)
        return side, cx

    portrait = W / H < 0.8    # 9:16 und aehnliche Hochformate
    # v86: Baseline-Zonen fuer Querformat. Vorher sassen cascade (0.39),
    # outline (0.398) und stack (0.435) auf drei knapp verschiedenen Hoehen -
    # aufeinanderfolgende Momente unterschiedlichen Typs huepften minimal. Jetzt
    # teilen sie sich EINEN Unteres-Drittel-Anker. 'behind' bleibt oben (naeher
    # am Kopf), 'ground' bleibt die Bodenebene fuer B-Roll.
    Z_MAIN = H * 0.40         # gemeinsamer Anker: cascade / outline / stack
    Z_BEHIND = H * 0.34       # Text hinter der Person, sitzt hoeher
    safe_z = portrait and cfg['effects'].get('safe_zone', True)
    if safe_z:
        print("Safe-Zone 9:16 aktiv: Buttons rechts und Beschreibung unten bleiben frei")

    # v86: Baseline-Grid. Aufeinanderfolgende Captions sollen auf EINER Linie
    # sitzen statt bei jedem Moment ein paar Prozent zu huepfen. Zwei Massnahmen:
    # (a) Hysterese bei der Band-Wahl (oben ueber dem Kopf / unteres Drittel) -
    #     die Grenze muss um H*0.34 herum deutlich ueberschritten werden, bevor
    #     umgeschaltet wird, sonst wackelt der Text bei Mini-Kopfbewegungen.
    # (b) Die Ziel-Hoehe wird auf ein Raster (H*0.025) gerundet, damit Gesichts-
    #     Jitter den Text nicht kontinuierlich verschiebt.
    VZ_GRID = H * 0.025
    vz_state = {'band': None}

    def v_zone(start, end):
        """Vertikale Text-Zone im Hochformat: ueber dem Kopf wenn Platz, sonst
        unteres Drittel - mit Hysterese und auf ein Baseline-Raster gerastet."""
        if face_pos is None:
            return H * 0.70
        _, fy, fw = face_pos(start, end)
        head_top = fy - fw * 1.15
        floor_top = H * (0.12 if safe_z else 0.10)
        cap_bot = H * (0.64 if safe_z else 0.74)
        # Band mit Hysterese: rein in 'oben' erst ab 0.39, rein in 'unten' erst
        # ab 0.29; dazwischen bleibt das zuletzt gewaehlte Band stehen.
        prev = vz_state['band']
        if head_top > H * 0.39:
            band = 'oben'
        elif head_top < H * 0.29:
            band = 'unten'
        else:
            band = prev or ('oben' if head_top > H * 0.34 else 'unten')
        vz_state['band'] = band
        y = (max(head_top * 0.52, floor_top) if band == 'oben'
             else min(cap_bot, fy + fw * 2.4))
        return round(y / VZ_GRID) * VZ_GRID          # aufs Raster einrasten

    def clamp_cx(cx, sprite_w):
        m = W * 0.045 + 30            # Rand + Reserve fuer Kamera und Tracking
        half = sprite_w / 2
        if half + m >= W - half - m:  # Sprite breiter als der sichere Bereich: zentrieren
            return W / 2
        return min(max(cx, half + m), W - half - m)

    side_state = {'seen': 0, 'rot': 0}
    def next_side_cam():
        side_state['seen'] += 1
        if not SIDE_MODES or side_every <= 0 or (side_state['seen'] - 1) % side_every != 0:
            return 'none'
        m = SIDE_MODES[side_state['rot'] % len(SIDE_MODES)]
        side_state['rot'] += 1
        return m

    # Worthaeufigkeit fuer das Scoring (seltener = wichtiger)
    freq = {}
    for w in words:
        t = clean(w['word']).lower()
        freq[t] = freq.get(t, 0) + 1

    _zrel_cache = {}

    def zrel(i):
        if i not in _zrel_cache:
            _zrel_cache[i] = zahl_relevanz(words, i)
        return _zrel_cache[i]

    def score(i):
        t = clean(words[i]['word'])
        # Relevante Zahl schlaegt das Nachbarwort: sie IST die Aussage. Damit
        # gewinnt pro Gruppe immer die staerkste Zahl - und nicht das Substantiv
        # daneben, das den Moment vorher weggeschnappt hat.
        return (len(t) + (6 if freq[t.lower()] == 1 else 0) - freq[t.lower()]
                + 9.0 * zrel(i))

    plans, side_toggle, kwc, camc, scamc = [], 0, 0, 0, 0
    # v96e: Variation PRO VIDEO. Frueher war der Seed nur die Wortzahl - zwei
    # verschiedene Videos mit gleich vielen Woertern bekamen dieselbe Mischung,
    # und der Keyword-Effekt lief stur ab Index 0 (jedes Video: behind, cascade,
    # ...). Jetzt kommt der Seed aus dem INHALT (Transkript-Text) - jedes andere
    # Video bekommt eine andere, aber reproduzierbare Reihenfolge. Gleiches Video
    # -> gleiches Ergebnis (Cache/Re-Render stabil), verschiedene Videos ->
    # sichtbar andere Effekt-Mischung, Platzierung, Kamera.
    import zlib as _zlib
    _txt = ' '.join(w.get('word', '') for w in words).encode('utf-8', 'ignore')
    _seed = (_zlib.crc32(_txt) ^ (len(words) * 2654435761)) & 0xffffffff
    rot_cam = Rotator(CAM_FX or ['none'], _seed)
    rot_kw = Rotator(KW_FX or ['cascade'], _seed + 4)   # Keyword-Effekt-Mischung
    side_toggle = _seed % 2                              # mal links, mal rechts zuerst
    big_used = set()      # v96i: (fx, anim) bereits benutzter GROSSER Momente -
                          #       kein Hoehepunkt darf visuell exakt gleich sein
    rot_entr = Rotator(('edge_l', 'edge_r', 'rise', 'drop', 'zoom', 'swing', 'flip', 'morph',
                        'emerge'),
                       _seed + 1)
    rot_entr_safe = Rotator(('edge_l', 'rise', 'drop', 'zoom', 'swing', 'morph', 'emerge'),
                            _seed + 2)
    rot_entr_no_em = Rotator(('edge_l', 'edge_r', 'rise', 'drop', 'zoom', 'swing', 'morph'),
                             _seed + 9)
    rot_fill = Rotator(('cascade', 'outline', 'blurin'), _seed + 3)   # Lueckenfueller
    last_kw_end = -999.0
    last_num_end = -999.0
    prev_was_keyword_sentence = False   # letzter Moment liess seinen Satz offen
    forts_count = 0                     # wie viele Fortsetzungsgruppen schon gezeigt
    # Nur sinnvoll, wenn das Transkript ueberhaupt Satzzeichen hat. Ohne
    # Interpunktion (manche Whisper-Laeufe) gaebe es kein Satzende - die
    # Fortsetzung liefe endlos. Dann bleibt das Verhalten wie bisher.
    hat_interpunktion = any(
        w['word'].rstrip().endswith(('.', '!', '?')) for w in words)
    # Bremse: hoechstens eine Zahl-Caption pro zahl_gap Sekunden. Sonst knallt es
    # bei jeder Zahl - und genau das soll es NICHT.
    zahl_gap = float(cfg['effects'].get('zahl_gap', 15))
    prev_was_keyword = False
    groups = list(build_groups(words, cfg['effects'].get('words_per_group', 3),
                               min_hold=float(cfg['effects'].get('chunk_hold_min', 0.65)),
                               hard_max=int(cfg['effects'].get('words_per_group_max', 5))))
    g_starts = [words[g[0]]['start'] for g in groups]
    # Randfall: nirgends ein Sprecher-Gesicht (Voiceover, Screen-Recording).
    # Dann duerfen die Captions nicht komplett wegfallen -> szenen-verankert zeigen.
    voiceover = bool(groups) and not any(
        face_ok(words[g[0]]['start'], words[g[-1]]['end']) for g in groups)
    if voiceover and not cfg['effects'].get('broll_captions', False):
        print("Kein Sprecher-Gesicht im Video: Captions werden szenen-verankert gesetzt.")
    used = set()                            # von Phrasen verbrauchte Woerter
    kw_count = 0
    for gi, g in enumerate(groups):
        g = [i for i in g if i not in used]
        if not g:
            continue
        start, end = words[g[0]]['start'], words[g[-1]]['end']
        next_start = g_starts[gi + 1] if gi + 1 < len(groups) else 1e9
        broll = not face_ok(start, end)
        # Adaptive Farben: Caption-Toene greifen die Szene dieses Moments auf
        S.set_palette(palette_at(start + 0.2) if palette_at else None)
        if broll and not voiceover and not cfg['effects'].get('broll_captions', False):
            prev_was_keyword = False
            continue                       # Szenen ohne Sprecher bleiben textfrei
        # Hook: Laenge frei einstellbar (0 = aus), Staerke steuert die Dichte.
        # In den ersten Sekunden entscheidet sich, ob jemand dranbleibt.
        hook_len = float(cfg['effects'].get('hook_seconds', 15))
        hook_pow = float(cfg['effects'].get('hook_strength', 0.5))   # 0..1
        in_intro = (cfg['effects'].get('intro_hook', True) and hook_len > 0
                    and cfg['effects'].get('density', 'akzente') != 'durchgehend'
                    and start < hook_len)
        g_kw = sorted([i for i in g if i in kw], key=score, reverse=True)
        # Zahl-Bremse: liegt die letzte Zahl-Caption noch keine zahl_gap Sekunden
        # zurueck, faellt die Zahl aus dem Rennen - der Moment geht dann an das
        # naechstbeste Wort, nicht an noch eine Zahl.
        if (zahl_gap > 0 and g_kw and zrel(g_kw[0]) > 0
                and start - last_num_end < zahl_gap):
            g_kw = [i for i in g_kw if zrel(i) <= 0]

        # Rhythmus: direkt nach einem Keyword-Moment eine Atempause ohne Text
        if breathing and prev_was_keyword and not g_kw:
            prev_was_keyword = False
            continue

        # Dichte-Limit: zu dichte Keyword-Momente werden zu normalen Gruppen
        # Im Hook duerfen Momente enger stehen - hook_strength regelt wie eng
        # (0 = wie normal, 1 = dreifache Dichte)
        gap_eff = min_gap * ((1.0 - 0.66 * hook_pow) if in_intro else 1.0)
        is_kw_group = bool(g_kw) and (start - last_kw_end >= gap_eff)
        prev_budget = last_kw_end
        if is_kw_group:
            last_kw_end = end
        prev_was_keyword = is_kw_group

        # WATCHTIME: Lueckenfueller. Lange Strecken ohne visuelles Ereignis sind
        # die klassischen Absprungstellen. Reisst die Lueche zu weit auf, wird die
        # beste Gruppe im Fenster zum Moment erhoben - auch ohne echtes Keyword.
        ret_gap = float(cfg['effects'].get('retention_gap', 0))
        if (ret_gap > 0 and not is_kw_group and not in_intro
                and start - last_kw_end > ret_gap and g):
            # v80: Stopwords (denn/aber/also/ist/...) sind ausdruecklich KEINE
            # gueltigen Watchtime-Momente - sonst kommt "DENN" gross ins Bild.
            g_kw_cand = [j for j in g
                         if clean(words[j].get('word', '')).lower() not in STOPWORDS]
            if not g_kw_cand:
                g_kw_cand = g       # nur wenn ALLES Fuellwoerter sind, doch nehmen
            g_kw = sorted(g_kw_cand, key=score, reverse=True)[:1]
            i_f = g_kw[0]
            _tf = clean(words[i_f].get('word', '')).lower()
            if (len(_tf) >= 3 and _tf not in STOPWORDS):       # kein "der"/"und"/"denn"
                is_kw_group = True
                kw = set(kw) | {i_f}
                fx_map.setdefault(i_f, {}).setdefault('fx', rot_fill.next())
                fx_map[i_f].setdefault('power', 1)             # dezent, nicht laut
                last_kw_end = end
                prev_was_keyword = True
                print(f"  Watchtime-Moment (Luecke {start - prev_budget:.0f}s): "
                      f"{words[i_f].get('word', '')}")

        # SATZ ZU ENDE FUEHREN: Ein grosser Keyword-Moment ("BLEIB dran denn am
        # Ende ...") deckt nur seine eigene Wortgruppe ab. Der Rest des Satzes
        # ("... wirst du das alles anders sehen") bildet Folgegruppen ohne eigenes
        # Keyword und fiele bei Dichte "akzente" weg - der Satz wirkt dann
        # abgeschnitten, als haette man vergessen weiterzumachen. Solche
        # Fortsetzungen laufen darum als ruhige Caption weiter, bis der Satz
        # (Punkt/Frage/Ausruf) abgeschlossen ist.
        satz_offen = (prev_was_keyword_sentence
                      and hat_interpunktion
                      and not is_kw_group
                      and not in_intro
                      and not broll
                      and forts_count < 2
                      and start - last_kw_end < 4.0)
        if satz_offen:
            # kein neuer Moment - nur weiterlesen lassen
            fx_map.pop(g[0], None)
            forts_count += 1

        # Plattform-Dichte: YouTube/Ausgewogen zeigen nur Akzent-Momente.
        # Im Hook-Intro laufen die Captions durchgehend fuer die Watchtime.
        if (cfg['effects'].get('density', 'akzente') != 'durchgehend'
                and not is_kw_group and not in_intro and not satz_offen):
            continue

        if is_kw_group:
            i = g_kw[0]                       # bestes Keyword der Gruppe (Score)
            if zrel(i) > 0:
                last_num_end = end
                print(f"  Zahl-Moment ({zrel(i):.1f}): {clean(words[i]['word'])}")
            # Mindest-Anzeigedauer: das grosse Wort braucht mindestens 1 s Buehne.
            # Wenn Platz ist, wird die Anzeige in die folgende Pause verlaengert;
            # wenn nicht (naechste Gruppe zu nah, Szenenwechsel), faellt der
            # Moment komplett weg statt kurz aufzublitzen.
            kw_t0 = words[i]['start']
            disp_end = min(max(end, kw_t0 + 1.2), end + 1.5)
            # Szenen-verankerter Text (broll: liegt am Boden / in der Szene)
            # braucht die Person nicht - er darf ueber das gesprochene Wort
            # hinaus stehen bleiben, auch wenn danach kein Gesicht kommt. Nur
            # personen-gebundener Text (behind/blurin) wuerde ins Leere laufen.
            if (disp_end > end and not voiceover and not broll
                    and not face_ok(end, disp_end)):
                disp_end = end             # Verlaengerung wuerde in B-Roll laufen
            if disp_end - kw_t0 < 1.0:
                prev_was_keyword = False
                last_kw_end = prev_budget  # Moment entfaellt, Budget zurueckgeben
                continue
            end = disp_end
            info = (fx_map or {}).get(i)
            if isinstance(info, dict):
                wish, n_ph = info.get('fx'), int(info.get('n', 1))
            else:
                wish, n_ph = info, 1
            phrase = [i]
            for j in range(i + 1, min(i + n_ph, len(words))):
                gap = words[j]['start'] - words[j - 1]['end']
                if j in g or gap <= 0.35:   # zusammenhaengend gesprochen
                    phrase.append(j)
                else:
                    break
            used.update(phrase)
            end = max(end, words[phrase[-1]]['end'])
            # Laesst dieser Moment seinen Satz offen? Dann muss die Fortsetzung
            # danach sichtbar bleiben, sonst wirkt der Satz abgeschnitten.
            _last_w = words[phrase[-1]]['word'].rstrip()
            prev_was_keyword_sentence = not _last_w.endswith(('.', '!', '?'))
            forts_count = 0
            if broll:
                # Auf B-Roll steht der Text in der Szene: ground ist erlaubt
                # (grosse Momente), behind/blurin brauchen die Person -> mappen
                if wish in ('cascade', 'outline', 'ground'):
                    fx = wish
                elif wish == 'behind':
                    fx = 'ground'
                else:
                    fx = 'cascade'
            elif wish in KW_FX or wish == 'ground':
                # 'ground' ist eine PLATZIERUNGS-Ansage (Boden/Wasser/Wand),
                # kein blosser Stil - sie muss honoriert werden, auch wenn sie
                # nicht in der Look-Rotation steht. Sonst landet "liegt auf dem
                # Boden" im Talking-Head nie auf dem Boden, sondern wird zu
                # behind/cascade wegge-mappt.
                fx = wish                     # KI-Regie / Sprach-Intent hat entschieden
            else:
                fx = rot_kw.next(); kwc += 1     # v96e: seed-gemischt statt stur
            txt = ' '.join(clean(words[j]['word']).upper() for j in phrase)
            _ov = info.get('txt') if isinstance(info, dict) else None
            words_c = words
            if _ov and _ov.strip():
                txt = ' '.join(clean(w).upper() for w in _ov.split() if clean(w))
                ov_toks = _ov.split()
                if len(ov_toks) == len(phrase):   # Wort fuer Wort in die Komposition
                    words_c = list(words)
                    for j, tok in zip(phrase, ov_toks):
                        words_c[j] = dict(words[j], word=tok)
                elif len(phrase) >= 2:            # Wortzahl geaendert: als Block setzen
                    phrase = phrase[:1]
            _cnt = make_counter(txt)
            if _cnt:
                # Der Zaehler muss KOMPLETT hochlaufen UND das Ziel danach lesbar
                # stehen bleiben. Sonst ist der Moment vorbei, bevor die Zahl oben
                # ankommt (Bug: "2026" verschwindet, bevor die Zahl steht). Die
                # Zahl darf ruhig ueber die naechste Wortgruppe hinaus stehen.
                _need = kw_t0 + _cnt[1] + 0.45
                if _need > end:
                    end = min(_need, end + 1.5)
            if _cnt and fx == 'cascade':
                fx = 'outline'          # Zahlen zaehlen immer hoch: Cascade kann das
                                        # nicht tragen -> Zahlen-Buehne ist outline
            small = []
            for i2 in ([] if (cfg['effects'].get('density', 'akzente') == 'akzente'
                              and not in_intro)
                       else [x for x in g if x not in phrase]):
                a2, tw = S.text(clean(words[i2]['word']).upper(), int(H * 0.043), S.white,
                                tracking=14, font=S.f_sans)
                small.append({'i': i2, 'arr': a2, 'w': tw})
            p = {'tpl': fx, 'kw_i': i, 'kw_txt': txt, 'small': small, 'start': start, 'end': end,
                 'tilt': rng(i, 4) * 3 - 1.5, 'side': 0, 'broll': broll}
            # Einflug variiert gemischt statt stur reihum - nie zweimal derselbe
            p['entr'] = (rot_entr_safe if safe_z else rot_entr).next()
            # HERAUSSCHIEBEN steuerbar: 'auto' = nur ab und zu (Abwechslung),
            # 'immer' = jedes Wort hinter der Person wird hervorgeschoben (das ist
            # der Signature-Look), 'aus' = nie.
            _em_mode = str(cfg['effects'].get('emerge', 'auto')).lower()
            _em_moeglich = (fx == 'behind' and not broll and face_pos is not None)
            if _em_mode == 'immer' and _em_moeglich:
                p['entr'] = 'emerge'
            elif _em_mode == 'aus' and p['entr'] == 'emerge':
                p['entr'] = rot_entr_no_em.next()
            # Ohne Person und ohne Freistellung (nur 'behind' wird von der Maske
            # verdeckt) gaebe es nichts, wovon das Wort hervorkommen koennte.
            if p['entr'] == 'emerge' and not _em_moeglich:
                p['entr'] = rot_entr_no_em.next()
            kw_count += 1
            # v80f: Emoji durchreichen (kommt aus KI-Regie oder Editor-Overrides)
            if isinstance(info, dict) and info.get('emoji'):
                p['emoji'] = info['emoji']
            if cfg['effects'].get('anim', True):
                _auto_anim = (info.get('anim') if isinstance(info, dict) else None)
                if not _auto_anim:
                    _auto_anim = anim_for(txt, ' '.join(
                        clean(words[j]['word'])
                        for j in range(max(i - 4, 0),
                                       min(i + 8, len(words)))))
                p['anim'] = _auto_anim
                # Auto-Wahl zurueck in fx_map schreiben, damit der Momente-Editor
                # sie anzeigt (sonst steht dort "keine", obwohl das Video animiert).
                if _auto_anim and isinstance(fx_map, dict):
                    if i not in fx_map or not isinstance(fx_map[i], dict):
                        fx_map[i] = fx_map.get(i) if isinstance(fx_map.get(i), dict) else {}
                    if isinstance(fx_map.get(i), dict):
                        fx_map[i].setdefault('anim', _auto_anim)
                if p.get('anim'):
                    print(f"  Lebendige Typo: {p['anim']} auf '{txt}'")
            if _cnt:
                p['count'] = {'fmt': _cnt[0], 'dur': _cnt[1]}
                print(f"  Zaehler-Moment: {txt}")

            _pw_here = int(info.get('power', 2)) if isinstance(info, dict) else 2

            if broll:
                p['ccam'] = 'none'
            elif fx in ('behind', 'blurin', 'ground'):
                if CAM_FX:
                    p['cam'] = rot_cam.next(); camc += 1
            else:
                p['ccam'] = next_side_cam()
            if len(phrase) >= 2:
                p['tokens'] = compose_phrase(phrase, words_c, S, W, H, portrait, safe_z)
                print(f"  Editorial-Komposition: {txt}")
                core_tok = next((tk for tk in p['tokens'] if tk.get('role') == 'core'), None)
                if core_tok is not None and p.get('count'):
                    c2 = make_counter(core_tok.get('txt', ''))
                    if c2:
                        core_tok['count'] = {'fmt': c2[0], 'dur': c2[1]}
                        core_tok['builder'] = (lambda s, _sz=core_tok.get('sz'):
                                               S.text(s, _sz, S.white)[0])
                p['tpl'] = 'behind'            # Komposition lebt hinter der Person
                p['by'] = Z_BEHIND if not portrait else v_zone(start, end)
                sy = p['by'] + (H * 0.24 if not portrait else H * 0.15)
            elif fx == 'behind':
                # v90: 'himmel' = das Wort steigt HINTER dem Kopf hervor und endet
                # KOMPLETT UEBER dem Kopf, voll lesbar (Schluss-Signatur, z.B. der
                # Markenname). Kein emerge (das haelt es hinter der Person), sondern
                # hoch platziert + Aufwaerts-Einflug.
                if isinstance(info, dict) and info.get('szene') == 'himmel' \
                        and face_pos is not None:
                    _fp = face_pos(start, end)
                    if _fp:
                        p['entr'] = 'rise'
                        p['by'] = max(float(_fp[1]) - H * 0.25, H * 0.06)
                # HERAUSSCHIEBEN braucht Ueberlappung: liegt das Wort ueber dem
                # Kopf, verdeckt die Person nichts und der Effekt ist unsichtbar.
                # Darum wird es auf Kopf-/Schulterhoehe gelegt.
                elif p.get('entr') == 'emerge' and face_pos is not None:
                    _fp = face_pos(start, end)
                    if _fp:
                        p['by'] = max(min(float(_fp[1]) - H * 0.055, H * 0.62),
                                      H * 0.10)
                _bh_limit = int(W * (0.62 if safe_z else 0.94) if portrait else W * 0.885)
                sz = S.fit(txt, int(H * 0.213) if not portrait else int(H * 0.11), _bh_limit)

                def _build_behind(_s):
                    if S.kinetic and not p.get('count'):
                        arr, tot, lets = S.text(txt, _s, S.accent, glow=True,
                                                per_letter=True, extrude=S.ex)
                        p['arr'] = arr
                        p['letters'] = letter_slices(arr, lets)
                    else:
                        p['arr'] = persp_warp(rot_img(S.text(txt, _s, S.accent, glow=True,
                                                             extrude=S.ex)[0],
                                                      p['tilt'] * 0.6), yaw=p['tilt'] * 4.5)
                _build_behind(sz)
                # v96z LESBARKEIT: Ist das Wort schmaler als der Kopf (inkl.
                # Haare ~1.7x Gesichtsbox), verschwindet es hinter der Person -
                # nur Anfangs-/Endbuchstabe ragen heraus (unlesbar). Dann:
                # (1) Schrift vergroessern, bis das Wort DEUTLICH breiter ist
                # als der Kopf; reicht das nicht (Randlimit), (2) das Wort
                # UEBER den Kopf legen - lieber sichtbar als versteckt.
                if face_pos is not None and not broll:
                    _fpv = face_pos(start, end)
                    _kopf = float(_fpv[2]) * 1.7 if _fpv else 0.0
                    if _kopf > 0:
                        def _vis_w():
                            _ax = np.where(p['arr'][..., 3] > 8)[1]
                            return (int(_ax.max() - _ax.min()) if _ax.size
                                    else p['arr'].shape[1])
                        _tw = _vis_w()
                        if _tw < _kopf * 1.25:
                            _gr = min(_kopf * 1.35 / max(_tw, 1),
                                      _bh_limit / max(_tw, 1))
                            if _gr > 1.02:
                                sz = int(sz * _gr)
                                _build_behind(sz)
                                _tw = _vis_w()
                            if _tw < _kopf * 1.10:
                                p['by'] = max(float(_fpv[1]) - _kopf * 0.85,
                                              H * 0.07)
                                if p.get('entr') == 'emerge':
                                    p['entr'] = 'rise'
                                print(f"  Lesbarkeit: '{txt}' schmaler als der "
                                      f"Kopf -> ueber den Kopf gelegt")
                            else:
                                print(f"  Lesbarkeit: '{txt}' vergroessert "
                                      f"(ragt beidseitig heraus)")
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _tl=p['tilt']:
                                    persp_warp(rot_img(S.text(s, _sz, S.accent, glow=True,
                                                              extrude=S.ex)[0], _tl * 0.6),
                                               yaw=_tl * 4.5))
                # Echte Variable-Font-Achse statt Dick-Rechnen: die Gewichts-Stufen
                # werden einmal gerendert, im Frame wird nur noch gewaehlt.
                if (p.get('anim') == 'gewicht' and not p.get('count')
                        and not S.kinetic and var_font_for(S.f_serif)):
                    _wb = (lambda w, _t=txt, _sz=sz, _tl=p['tilt']:
                           persp_warp(rot_img(S.text(_t, _sz, S.accent, glow=True,
                                                     extrude=S.ex, wght=w)[0], _tl * 0.6),
                                      yaw=_tl * 4.5))
                    try:
                        p['_wladder'] = build_wladder(_wb)
                        print(f"  Variable-Achse: echte Gewichts-Leiter auf '{txt}'")
                    except Exception:
                        p['_wladder'] = None
                sy = H * (0.74 if safe_z else 0.80)
            elif fx == 'cascade':
                max_w = int(W * (0.60 if safe_z else 0.82)) if portrait else int(W * 0.396)
                sz = S.fit(txt, int(H * 0.139) if not portrait else int(H * 0.085), max_w, font=S.f_italic)
                arr, tw, letters = S.text(txt, sz, S.white, per_letter=True, font=S.f_italic)
                p['arr'], p['letters'] = arr, letters
                p['side'], p['cx'] = pick_side(start, end, side_toggle)
                p['cx'] = clamp_cx(p['cx'], p['arr'].shape[1])
                side_toggle += 1
                p['cy'] = v_zone(start, end) if portrait else Z_MAIN
                sy = p['cy'] + (H * 0.128 if portrait else H * 0.139)
            elif fx == 'blurin':
                sz = S.fit(txt, int(H * 0.199) if not portrait else int(H * 0.10), int(W * (0.62 if safe_z else 0.86) if portrait else W * 0.78), tracking=6)
                p['arr'] = rot_img(S.text(txt, sz, S.white, tracking=6, extrude=S.ex)[0], p['tilt'] * 0.5)
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _tl=p['tilt']:
                                    rot_img(S.text(s, _sz, S.white, tracking=6,
                                                   extrude=S.ex)[0], _tl * 0.5))
                sy = H * (0.74 if safe_z else 0.80)
            elif fx == 'outline':
                max_w = int(W * (0.60 if safe_z else 0.82)) if portrait else int(W * 0.396)
                sz = S.fit(txt, int(H * 0.148) if not portrait else int(H * 0.09), max_w)
                p['o_arr'] = rot_img(S.text(txt, sz, S.accent, outline=True)[0], p['tilt'])
                p['f_arr'] = rot_img(S.text(txt, sz, S.accent)[0], p['tilt'])
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _tl=p['tilt']:
                                    (rot_img(S.text(s, _sz, S.accent, outline=True)[0], _tl),
                                     rot_img(S.text(s, _sz, S.accent)[0], _tl)))
                p['side'], p['cx'] = pick_side(start, end, side_toggle)
                p['cx'] = clamp_cx(p['cx'], p['o_arr'].shape[1])
                side_toggle += 1
                p['cy'] = v_zone(start, end) if portrait else Z_MAIN
                sy = p['cy'] + (H * 0.09 if portrait else H * 0.13)
            elif fx == 'ground':
                # Untergrund-Palette: der Text liegt auf Wasser/Boden -> genau dort sampeln
                if palette_at:
                    S.set_palette(palette_at(kw_t0 + 0.2, 'unten')
                                  or palette_at(kw_t0 + 0.2))
                pw_g = int(info.get('power', 2)) if isinstance(info, dict) else 2
                lage = info.get('lage') if isinstance(info, dict) else None
                szene = info.get('szene') if isinstance(info, dict) else None
                # Vision-Regie hat Vorrang: sie hat den Frame gesehen.
                # Fallback ohne Vision: power entscheidet.
                p['szene'] = szene
                # WICHTIG: "liegt auf dem Boden/im Wasser" MUSS liegen - auch
                # wenn eine Person im Bild ist. Frueher lag der Text nur auf
                # B-Roll (ohne Gesicht); im Talking-Head wurde daraus ein
                # stehendes Billboard mit Spiegelung -> wirkte draufgeklatscht.
                if lage == 'liegend':
                    lying = True
                elif lage in ('stehend', 'frei'):
                    lying = False
                else:
                    lying = (szene in ('wasser', 'boden')) or (broll and pw_g >= 3)
                on_wall = (szene == 'wand') and not lying
                # scene_ground: der Text lebt IN einer Flaeche der Szene
                # (Boden/Wasser/Wand) - perspektivisch, von der Person verdeckt,
                # kamera-getrackt. Das ist der Premium-Pfad, unabhaengig davon,
                # ob gerade ein Gesicht im Bild ist.
                scene_ground = lying or on_wall
                standing_br = broll and not lying
                g_pitch = 0.68 if lying else (0.12 if on_wall
                                              else (0.06 if standing_br else 0.5))
                g_ex = False if lying else S.ex
                # Liegender Boden-Text schmaler fassen: nach der Perspektive
                # (persp_warp) wird er breiter - sonst laeuft "STREET" aus dem
                # Bild. Im Talking-Head noch schmaler: er liegt auf der freien
                # Bodenflaeche VOR der Person, nicht als Riesen-Sticker
                # ueber der Szene. Stehender Text darf breiter sein.
                if lying:
                    _gw = (0.58 if broll else 0.48) if not portrait \
                        else (0.52 if broll else 0.42)
                else:
                    _gw = 0.72 if not portrait else (0.62 if safe_z else 0.9)
                sz = S.fit(txt, int(H * 0.20) if not portrait else int(H * 0.10),
                           int(W * _gw), font=S.f_serif)
                g_yaw = -6 if (side_toggle % 2 == 0) else 6
                if S.kinetic and not p.get('count') and not lying:
                    flat, tot, lets = S.text(txt, sz, S.white, per_letter=True, extrude=g_ex)
                    p['arr'] = flat
                    p['letters'] = letter_slices(flat, lets)
                else:
                    flat = S.text(txt, sz, S.white, extrude=g_ex, flat_light=lying)[0]
                    p['arr'] = persp_warp(flat, yaw=g_yaw, pitch=g_pitch)
                    if lying:
                        # Roh-Sprite aufheben: beim Ankern wird die Neigung der
                        # ECHTEN Flaeche gemessen und der Text neu gewarpt.
                        p['flat_arr'] = flat
                p['lying'] = lying
                if scene_ground:
                    p['scene_ground'] = True
                if lying:
                    if szene == 'wasser':
                        p['scene_blend'] = True     # Wasser: Wellen laufen durch die Buchstaben
                    else:
                        p['ground_paint'] = True    # fester Boden: flach aufgemalt, nicht fluessig
                if (scene_ground or broll) and cfg['effects'].get('track3d', True):
                    p['track3d'] = True            # planares Kamera-Tracking (Flaeche)
                # Spiegelung nur beim klassischen stehenden Billboard - Szenen-
                # Text (liegend/Wand) spiegelt nicht, das saehe geklebt aus.
                if cfg['effects'].get('reflection', True) and not lying \
                        and not scene_ground:
                    r, rdy, rdx = make_reflection(p['arr'])
                    if r is not None:
                        p['refl'], p['refl_dy'], p['refl_dx'] = r, rdy, rdx
                # Kontakt-Schatten nur fuer das stehende Billboard im Talking-
                # Head. Auf die Flaeche GEMALTER Text (liegend) wirft keinen
                # Schatten - Farbe hat keine Hoehe.
                if not broll and not scene_ground:
                    sh, sdy_, sdx_ = make_contact_shadow(p['arr'])
                    if sh is not None:
                        p['cshadow'], p['csh_dy'], p['csh_dx'] = sh, sdy_, sdx_
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _y=g_yaw, _pt=g_pitch, _ex=g_ex:
                                    persp_warp(S.text(s, _sz, S.white, extrude=_ex)[0],
                                               yaw=_y, pitch=_pt))
                side_toggle += 1
                p['cx'] = W / 2
                if (scene_ground or broll) and cfg['effects'].get('track3d', True):
                    if lying and not broll:
                        # Talking-Head: tief unter dem Sprecher - dort liegt der
                        # Boden, die Person verdeckt hoechstens die Wort-Mitte.
                        # ground_anchor verschiebt beim ersten Frame auf die
                        # freie Flaeche, wenn die Matte eine hergibt.
                        p['cy'] = H * (0.78 if not portrait else 0.86)
                    elif on_wall and not broll:
                        p['cy'] = H * (0.45 if not portrait else 0.42)
                    else:
                        # B-Roll: weit voraus verankern - kommt auf uns zu
                        p['cy'] = H * (0.60 if not portrait else 0.58)
                else:
                    p['cy'] = H * (0.80 if not portrait else (0.72 if safe_z else 0.82))
                sy = p['cy'] - H * 0.155
                # "LIEGT SCHON DA": Szenen-Text beginnt VOR dem gesprochenen
                # Wort - die Kamera schwenkt auf ein Wort, das bereits in der
                # Welt liegt. Gezeichnet wird erst, wenn der Anker die Flaeche
                # wirklich sieht; t_word haelt den Sprech-Zeitpunkt fuer den
                # Talking-Head-Fallback fest.
                if (scene_ground or broll) and cfg['effects'].get('track3d', True):
                    p['t_word'] = kw_t0
                    p['start'] = max(p['start'] - 1.5, 0.0)
            # v81e: Emoji ins Sprite backen. Nur einfache Ein-Array-Effekte
            # (behind/cascade/blurin/ground). 'outline' hat zwei Layer + Zaehler
            # bauen live -> dort bewusst kein Emoji, um Regression zu vermeiden.
            if p.get('emoji') and 'arr' in p and not p.get('count') \
                    and not p.get('letters') and not p.get('tokens'):
                try:
                    p['arr'] = bake_emoji(p['arr'], p['emoji'])
                except Exception as _e:
                    print(f"  Emoji uebersprungen ({type(_e).__name__})")
            p['target'] = (p.get('cx', W / 2), p.get('cy', p.get('by', H * 0.398)))
            gap = 28
            total = sum(it['w'] for it in small) + gap * max(len(small) - 1, 0)
            x0 = p.get('cx', W / 2) - total / 2
            for it in small:
                it['cx'], it['cy'] = x0 + it['w'] / 2, sy
                x0 += it['w'] + gap
            if face_pos is not None and not broll:
                ax, ay, _ = face_pos(start, end)
                p['anchor'] = (ax, ay)
            # v96k: GROSSE Momente duerfen sich VISUELL nicht wiederholen. Jetzt -
            # nachdem ALLE sichtbaren Attribute stehen (Effekt-Ebene, Animation,
            # Einflug, Kamera) - die volle Kombi pruefen. Denn Mehrwort-Hoehepunkte
            # werden immer zur 'behind'-Komposition, ein blosser fx-Wechsel vorher
            # verpufft. Taucht die Kombi bei einem frueheren Hoehepunkt schon auf,
            # wird die MOTION aufgebrochen: anderer Einflug + andere Kamera, und nur
            # wenn's dann noch gleich ist, eine andere (Impact-)Animation.
            if _pw_here >= 3 and not broll:
                _cam = p.get('cam') or p.get('ccam') or 'none'
                _sig = (p.get('tpl'), p.get('anim') or '', p.get('entr'), _cam)
                if _sig in big_used:
                    for _ in range(9):
                        _e = (rot_entr_safe if safe_z else rot_entr).next()
                        if _e != p.get('entr') and (_em_moeglich or _e != 'emerge'):
                            p['entr'] = _e
                            break
                    if CAM_FX and p.get('cam') is not None:
                        for _ in range(len(CAM_FX)):
                            _c = rot_cam.next()
                            if _c != _cam:
                                p['cam'] = _c
                                break
                    _cam = p.get('cam') or p.get('ccam') or 'none'
                    _sig = (p.get('tpl'), p.get('anim') or '', p.get('entr'), _cam)
                    if _sig in big_used and p.get('anim'):
                        for _a in ('explosion', 'zoom_punch', 'bruch', 'sturz',
                                   'anstieg', 'stempel', 'kippen'):
                            _s2 = (p.get('tpl'), _a, p.get('entr'), _cam)
                            if _s2 not in big_used:
                                p['anim'] = _a
                                _sig = _s2
                                break
                    print("  Hoehepunkt-Variation: Motion aufgebrochen")
                big_used.add(_sig)
            plans.append(p)
        elif cfg['effects'].get('caption_flow', True):
            # v97 Flow-Caption (Referenz-Look): Chunk baut sich INLINE auf,
            # Anker-Wort gross+getippt+Glow, Abschlusswort kursiv-Akzent.
            items, tot_h, anchor_i = compose_flow(g, words, S, W, H, portrait,
                                                  flow_sel=(flow_map or {}).get(g[0]))
            # Referenz-Look: Block im OBEREN Drittel (nicht mittig ueber dem
            # Gesicht). Bei Hochformat oben verankert, sonst zentriert.
            zc = v_zone(start, end) if portrait else Z_MAIN
            y0 = int(H * 0.13) if portrait else (zc - tot_h / 2.0)
            for it in items:
                it['cy'] += y0
            # v97d: KEINE Seiten-/Cap-Zoom-Fahrt auf Filler-Flow. Die zog frueher
            # zur alten Stack-Seite bzw. zum Ziel (W*0.07, zc) = leerer linker
            # Rand auf halber Hoehe -> "Zoom ins Leere", entkoppelt von der oben
            # verankerten Caption. Filler bleibt ruhig (wie die Referenz); die
            # dramatischen Keyword-Momente behalten ihre Kamera.
            sp = {'tpl': 'flow', 'front': items, 'start': start, 'end': end,
                  'side': 0, 'ccam': 'none',
                  'target': (int(W * 0.07), int(y0 + tot_h / 2.0)),
                  'broll': broll}
            if anchor_i is not None:                 # leiser Tick auf den Anker
                sp['flow'] = True
                sp['flow_anchor'] = anchor_i
                sp['flow_t'] = words[anchor_i]['start']
            if face_pos is not None and not broll:
                ax, ay, _ = face_pos(start, end)
                sp['anchor'] = (ax, ay)
            plans.append(sp)
            if satz_offen and words[g[-1]]['word'].rstrip().endswith(('.', '!', '?')):
                prev_was_keyword_sentence = False
            elif not satz_offen:
                prev_was_keyword_sentence = False
            continue
        else:
            side, sx = pick_side(start, end, side_toggle)
            sx = int(sx)
            side_toggle += 1
            items = []
            big = g[int(np.argmax([len(clean(words[i2]['word'])) for i2 in g]))]
            for i2 in g:
                tt = clean(words[i2]['word']).upper()
                if i2 == big:
                    b_max = int(W * 0.80) if portrait else int(W * 0.365)
                    a2, tw = S.text(tt, S.fit(tt, int(H * 0.104) if not portrait else int(H * 0.062), b_max), S.white, extrude=S.ex)
                else:
                    a2, tw = S.text(tt, int(H * 0.048), S.white, tracking=14, font=S.f_sans)
                items.append({'i': i2, 'arr': rot_img(a2, rng(i2, 4) * 2.0 - 1.0), 'w': tw})
            sx = int(clamp_cx(sx, max(it['arr'].shape[1] for it in items)))
            zc = v_zone(start, end) if portrait else Z_MAIN
            step = H * 0.062 if portrait else H * 0.096
            y0 = zc - (len(items) - 1) * step / 2
            for r, it in enumerate(items):
                it['cx'], it['cy'] = sx, y0 + r * step
            ccam = 'none' if broll else next_side_cam()
            sp = {'tpl': 'stack', 'front': items, 'start': start, 'end': end,
                  'side': side, 'ccam': ccam, 'target': (sx, zc), 'broll': broll}
            if face_pos is not None and not broll:
                ax, ay, _ = face_pos(start, end)
                sp['anchor'] = (ax, ay)
            plans.append(sp)
            # War das eine Satz-Fortsetzung? Sobald sie den Satz abschliesst, ist
            # er nicht mehr offen - die naechste Gruppe darf wieder wegfallen.
            if satz_offen and words[g[-1]]['word'].rstrip().endswith(('.', '!', '?')):
                prev_was_keyword_sentence = False
            elif not satz_offen:
                prev_was_keyword_sentence = False

    # HOOK v48: Sofort-Hook. 65-71% entscheiden in den ersten 3 Sekunden, ob sie
    # bleiben. Das staerkste fruehe Statement wird zur Hook-Karte: sie steht ab
    # Frame 1 und bleibt, bis das Statement gesprochen ist - kein leerer Anfang.
    # v97e: NICHT bei aktivem Flow. Flow baut ab dem ersten Wort durchgehend
    # Captions auf (kein leerer Anfang mehr) - eine zusaetzlich fest oben
    # geparkte Keyword-Karte wirkt wie ein zufaelliger Titel und kollidiert mit
    # dem Flow-Text, der drueber laeuft. Das Keyword spielt normal zur Sprechzeit.
    hook_len = float(cfg['effects'].get('hook_seconds', 15))
    hook_on = (cfg['effects'].get('intro_hook', True) and hook_len > 0)
    _flow_on = cfg['effects'].get('caption_flow', True)
    if hook_on and cfg['effects'].get('instant_hook', True) and not _flow_on:
        early = min(hook_len, 8.0)
        cands = [p for p in plans if 'kw_i' in p and not p.get('broll')
                 and not p.get('tokens')          # Kompositionen takten wortweise
                 and words[p['kw_i']]['start'] < early]
        if cands:
            def _hook_rank(p):
                info = (fx_map or {}).get(p['kw_i'])
                pw = int(info.get('power', 2)) if isinstance(info, dict) else 2
                return (pw, len(p.get('kw_txt', '')), -words[p['kw_i']]['start'])
            best = max(cands, key=_hook_rank)
            t_spoken = words[best['kw_i']]['start']
            if t_spoken > 0.35:
                best['t0'] = 0.0
                best['start'] = 0.0
                print(f"  Sofort-Hook: '{best['kw_txt']}' steht ab Frame 1 "
                      f"(gesprochen bei {t_spoken:.1f}s)")

    # WATCHTIME: Pattern-Interrupt. Wo laenger nichts passiert, bekommt die
    # Kamera einen Impuls (Push/Punch) - das Auge bekommt ein Ereignis, auch
    # ohne Text. Klassischer Retention-Trick aus dem Schnitt.
    # HOOK v48: im Hook-Fenster verdichtet auf 3-5-Sekunden-Takt - genau dort
    # faellt die Bleiben-oder-Wischen-Entscheidung.
    pi_gap = float(cfg['effects'].get('pattern_interrupt', 0))
    hook_pi = hook_len if (hook_on and pi_gap > 0) else 0.0

    def _pi_step(tp):
        if tp < hook_pi:
            return (3.0, 4.0, 5.0)[int(tp * 7919) % 3]   # 3-5s, deterministisch variiert
        return pi_gap
    if pi_gap > 0 and plans:
        evts = sorted(p['start'] for p in plans)
        rot_pi = Rotator(('punch', 'push', 'pan'), _seed + 4)
        t_last, extra, skipped = evts[0], [], 0
        for t_e in evts[1:] + [words[-1]['end'] if words else evts[-1]]:
            while t_e - t_last > _pi_step(t_last):
                t_last += _pi_step(t_last)
                # B-Roll wird ignoriert: die Kamera darf fremdes Material
                # (Drohne, Schnittbilder) nicht nachtraeglich zoomen oder
                # schwenken - das zerstoert die Bildkomposition des Footage.
                if not face_ok(t_last, t_last + 0.9):
                    skipped += 1
                    continue
                extra.append({'tpl': 'camonly', 'start': t_last, 'end': t_last + 0.9,
                              'cam': rot_pi.next(), 'small': [], 'broll': False,
                              'ccam': 'none', 'arr': None})
            t_last = t_e
        if skipped:
            print(f"  Watchtime: {skipped} Kamera-Impuls(e) auf B-Roll uebersprungen")
        if extra:
            n_h = sum(1 for x in extra if x['start'] < hook_pi)
            print(f"  Watchtime: {len(extra)} Kamera-Impuls(e) in ruhigen Passagen"
                  + (f", davon {n_h} im Hook-Takt" if n_h else ""))
            plans.extend(extra)

    # ------------------------------------------------------------- Crash & Whip
    # Beide sind bewusst selten: der Crash-Zoom trifft NUR den einen staerksten
    # Moment (sonst wird der Effekt billig), der Whip-Pan nur echte Abschnitt-
    # grenzen. Auf 'Ruhig' (Clean/Cinematic) sind beide aus.
    crash_amt = float(cfg['camera'].get('crash', 0.0))
    if crash_amt > 0:
        # staerkster Keyword-Moment: hoechste power, bei Gleichstand laengstes Wort
        cand = [p for p in plans if 'cam' in p and 'kw_i' in p and not p.get('broll')]
        if cand:
            def _wucht(p):
                info = (fx_map or {}).get(p['kw_i'])
                pw = info.get('power', 1) if isinstance(info, dict) else 1
                return (pw, len(clean(words[p['kw_i']].get('word', ''))))
            top = max(cand, key=_wucht)
            top['cam'] = 'crash'
            top['crash_amt'] = crash_amt
            print(f"  Crash-Zoom auf staerksten Moment: "
                  f"{clean(words[top['kw_i']].get('word', ''))}")

    if cfg['camera'].get('whip', False):
        # Abschnittsgrenze = grosse Sprechpause zwischen zwei Keyword-Momenten.
        kwm = sorted([p for p in plans if 'kw_i' in p and not p.get('broll')],
                     key=lambda p: p['start'])
        n_whip = 0
        for a, b in zip(kwm, kwm[1:]):
            if b['start'] - a['end'] >= 1.4:        # klare Zaesur
                b['whip_at'] = b['start'] - 0.18
                b['whip_dir'] = 1 if n_whip % 2 == 0 else -1
                n_whip += 1
        if n_whip:
            print(f"  Whip-Pan an {n_whip} Abschnittsgrenze(n)")

    # v88: Kein Doppelbild - generalisiert ueber ALLE Text-Momente (siehe
    # resolve_overlaps). Laeuft NACH dem Hook (der t0 auf 0 zieht), damit die
    # Hook-Karte in der Ueberlappungs-Pruefung mitgezaehlt wird.
    _n_ovl = resolve_overlaps(plans, W, H)
    if _n_ovl:
        print(f"  Ueberlappungs-Schutz: {_n_ovl} Moment(e) vorgezogen")

    # v85: SCHNITT-DISZIPLIN (Broadcast-Regel, BBC/Netflix). Ein Untertitel darf
    # nicht ueber einen harten Schnitt hinweg stehen bleiben - das ist der
    # deutlichste "unbeaufsichtigte Auto-Pipeline"-Tell. Schnitte kennen wir aus
    # der Szenen-Analyse (cut_times). Ragt das Ende eines Moments in den naechsten
    # Shot, ziehen wir es so weit vor, dass der Abgang (exit_env, bis ~0.32s)
    # noch VOR dem Schnitt fertig ist. Zu nah am Start liegende Schnitte lassen
    # wir in Ruhe - dort lieber den kurzen Moment als einen Null-Frame-Blitz.
    if cut_times and cfg['effects'].get('cut_snap', True):
        cts = sorted(float(c) for c in cut_times)
        EXIT_LEAD = 0.34          # Abgangsdauer + 1 Frame Puffer
        MIN_SHOWN = 0.40          # so lange muss ein Moment mindestens stehen
        n_clamp = 0
        for p in plans:
            st = p.get('start')
            en = p.get('end')
            if st is None or en is None:
                continue
            nxt = next((c for c in cts if c > st + MIN_SHOWN), None)
            if nxt is None:
                continue
            limit = nxt - EXIT_LEAD
            if en > limit and limit >= st + MIN_SHOWN:
                p['end'] = limit
                n_clamp += 1
        if n_clamp:
            print(f"  Schnitt-Disziplin: {n_clamp} Moment(e) enden vor dem Schnitt")

    plans.sort(key=lambda p: p['start'])
    return plans

# ---------------------------------------------------------------- camera
def envelope(t, start, end, attack=0.35, release=0.40):
    if t < start: return 0.0
    if t < start + attack: return smoothstep((t - start) / attack)
    if t < end: return 1.0
    return 1.0 - smoothstep((t - end) / release) if t < end + release else 0.0

def camera_at(t, plans, words, cfg, W, H):
    """Eine Bewegung zur Zeit: die staerkste aktive Kamera gewinnt, nichts addiert sich."""
    strength = cfg['camera'].get('strength', 1.0)
    if strength <= 0:
        return 1.0, 0.0, 0.0, 0.0
    # v82: zwei inkommensurable Frequenzen (16s + 7.3s) - ein Einzelsinus
    # liest sich nach ~30s Material als mechanisch, die Ueberlagerung atmet
    # wie eine gehaltene Kamera.
    breathe = 1.0 + 0.016 * strength * (0.5 - 0.5 * math.cos(2 * math.pi * t / 16.0)) \
        + 0.005 * strength * math.sin(2 * math.pi * t / 7.3 + 1.7)
    C = (W / 2, H / 2)
    best = (0.0, 1.0, 0.0, 0.0, 0.0)   # (Gewicht, z, px, py, rd)

    def consider(w, z, px, py, rd):
        nonlocal best
        if w > best[0]:
            best = (w, z, px, py, rd)

    for p in plans:
        # WHIP-PAN: schneller, verwischter Seitwaerts-Schwenk als Uebergang an
        # einer Abschnittsgrenze. Sehr energisch - nur wenn ausdruecklich an.
        # Der Blur entsteht im Compositor aus der hohen px-Geschwindigkeit.
        if p.get('whip_at') is not None:
            wt = t - p['whip_at']
            if -0.02 <= wt < 0.24:
                e = wt / 0.24
                # Sweep laeuft von der Seite herein und stoppt. v82: asymmetrisch
                # (30% rein, 70% settle) - ein echter Whip beschleunigt hart und
                # laeuft weich aus, der symmetrische sin-Bogen wirkte mechanisch.
                sw_env = (math.sin(min(e / 0.3, 1.0) * math.pi / 2) if e < 0.3
                          else 1.0 - smoothstep((e - 0.3) / 0.7))
                sweep = sw_env * W * 0.075 * p.get('whip_dir', 1)
                consider(1.6, 1.0 + 0.02 * (1 - e), sweep * strength, 0.0, 0.0)
        mode = p.get('ccam')
        if mode in ('drift', 'capzoom'):
            env = envelope(t, p['start'], p['end']) * strength
            if env > 0.01:
                if mode == 'drift' and p['side'] != 0:
                    consider(env * 0.7, 1.0 + 0.052 * env, p['side'] * W * 0.022 * env, 0.0, 0.0)
                elif mode == 'capzoom':
                    tx, ty = p['target']
                    consider(env, 1.0 + 0.16 * env,
                             (tx - C[0]) * 0.22 * env, (ty - C[1]) * 0.22 * env, 0.0)
        if 'cam' not in p:
            continue
        # Watchtime-Impulse haben kein Keyword - sie starten an ihrer eigenen Zeit
        t0 = p.get('t0', words[p['kw_i']]['start'] if 'kw_i' in p else p['start'])
        dur = max(p['end'] - t0, 0.9)
        dt = t - t0
        if dt < -0.1 or dt > dur + 0.6:
            continue
        cam = p['cam']
        z, px, py, rd = 1.0, 0.0, 0.0, 0.0
        if cam == 'punch':                     # weicher Push statt Schlag
            if 0 <= dt < 0.55: z = 1.0 + 0.055 * smoothstep(dt / 0.55) * strength
            elif dt < dur: z = 1.0 + 0.055 * strength
            elif dt < dur + 0.7: z = 1.0 + 0.055 * (1 - smoothstep((dt - dur) / 0.7)) * strength
        elif cam == 'push':
            if 0 <= dt < dur: z = 1.0 + 0.06 * smoothstep(dt / dur) * strength
            elif dt < dur + 0.7: z = 1.0 + (0.06 - 0.06 * smoothstep((dt - dur) / 0.7)) * strength
        elif cam == 'crash':
            # CRASH-ZOOM: schneller, aggressiver Zoom in unter 0.4 s mit hartem,
            # entschiedenem Stopp - der 2026-Signature-Move fuer den einen
            # staerksten Moment. Anders als 'punch' (weich) schnappt er rein und
            # steht dann. Der harte Stopp entsteht durch den kurzen Attack + Halt;
            # die Kamera-EMA laesst ihn danach ruhig stehen statt nachzuwippen.
            amt = 0.10 * p.get('crash_amt', 1.0)
            if 0 <= dt < 0.32:
                z = 1.0 + amt * smoothstep(dt / 0.32) * strength
            elif dt < dur:
                z = 1.0 + amt * strength                 # steht - harter Stopp
            elif dt < dur + 0.5:
                z = 1.0 + amt * (1 - smoothstep((dt - dur) / 0.5)) * strength
        elif cam == 'pan':                     # Kameraschwenk quer durchs Bild
            if 0 <= dt < dur + 0.5:
                e = smoothstep(min(dt / max(dur, 1.0), 1.0))
                px = W * 0.020 * (2 * e - 1) * strength
                z = 1.0 + 0.035 * math.sin(math.pi * min(dt / max(dur, 1.0), 1.0)) * strength
                if dt > dur:
                    fade = 1 - smoothstep((dt - dur) / 0.5)
                    px *= fade
                    z = 1.0 + (z - 1.0) * fade
        elif cam == 'caption':                 # Close-up auf die Caption, folgt ihr
            if 0 <= dt < dur + 0.7:
                e = smoothstep(min(dt / 0.9, 1.0))
                if dt > dur:
                    e *= 1 - smoothstep((dt - dur) / 0.7)
                ty = p.get('by', H * 0.30)
                z = 1.0 + 0.10 * e * strength
                px = 0.0
                py = (ty - C[1]) * 0.30 * e
        elif cam == 'pullback':
            if 0 <= dt < 0.35: z = 1.0 + 0.075 * smoothstep(dt / 0.35) * strength
            elif dt < dur: z = 1.0 + (0.075 - 0.075 * smoothstep((dt - 0.35) / max(dur - 0.35, 0.3))) * strength
        act = max((z - 1.0) / 0.06, abs(px) / (W * 0.03), abs(py) / (H * 0.03), abs(rd) / 0.9)
        if act > 0.01:
            consider(1.25 * min(act, 1.0), z, px, py, rd)
    return best[1] * breathe, best[2], best[3], best[4]

# ---------------------------------------------------------------- compositor
def track_offset(p, face_xy, cfg):
    """Subtile Mitbewegung der Captions mit der Person (Caption-Tracking)."""
    if not cfg['effects'].get('tracking', True) or p.get('broll') or 'anchor' not in p:
        return 0.0, 0.0
    def soft(v, dead):
        return 0.0 if abs(v) < dead else (v - dead if v > 0 else v + dead)
    dx = soft(face_xy[0] - p['anchor'][0], 7.0) * 0.20
    dy = soft(face_xy[1] - p['anchor'][1], 7.0) * 0.14
    return max(-30, min(dx, 30)), max(-20, min(dy, 20))

def reveal_from(arr, x_local, halb, weich=26.0):
    """Deckt das Wort aus einem Punkt heraus auf - nach links und rechts wachsend.

    Genau das braucht der Herausschiebe-Effekt: Das Wort steckt hinter der Person
    und wird von ihr hervorgeschoben. Wuerde man es nur seitlich verschieben, waere
    es sofort komplett sichtbar - eine Person ist schmal, ein langes Wort nicht.
    Darum wird es aus der Position der Person heraus aufgedeckt: erst der Teil
    direkt an ihr, dann immer weiter nach aussen. Das liest sich, als schoebe sie
    es hinter sich hervor."""
    h, w = arr.shape[:2]
    if halb >= w:
        return arr
    x = np.arange(w, dtype=np.float32)
    m = np.clip((halb - np.abs(x - x_local)) / max(weich, 1.0), 0.0, 1.0)
    out = arr.copy()
    out[..., 3] = (out[..., 3].astype(np.float32) * m[None, :]).astype(arr.dtype)
    return out


def refine_alpha(alpha, frame, staerke=1.0):
    """Maske an die echten Bildkanten schnappen.

    Das Matting-Netz rechnet intern verkleinert - die Maske ist dadurch weich und
    sitzt an Haaren, Schultern und Fingern ein paar Pixel daneben. Der Guided
    Filter nimmt das ECHTE Bild als Vorlage und zieht die Maskenkante dorthin, wo
    im Bild tatsaechlich eine Kante ist. Das ist der Unterschied zwischen
    'ausgeschnitten' und 'freigestellt'."""
    if alpha is None or staerke <= 0:
        return alpha
    a = np.ascontiguousarray(alpha[..., 0].astype(np.float32))
    guide = cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_BGR2RGB)
    r = max(int(min(frame.shape[:2]) * 0.006), 4)     # Radius skaliert mit Aufloesung
    try:
        a2 = cv2.ximgproc.guidedFilter(guide, a, r, 1e-4)
        if staerke > 1.15:
            # Zweiter Durchgang mit kleinem Radius: holt feine Struktur zurueck
            # (einzelne Haarstraehnen, Brillenbuegel, Finger), die der erste,
            # groebere Durchgang glatt buegelt.
            a2 = cv2.ximgproc.guidedFilter(guide, a2, max(r // 3, 2), 1e-5)
    except Exception:
        return alpha
    # Kontrast an der Kante anziehen: halbdurchsichtiger Matsch wird zu einer Kante.
    a2 = np.clip((a2 - 0.5) * (1.0 + 0.9 * staerke) + 0.5, 0.0, 1.0)
    mix = min(staerke, 1.0)
    out = a[..., None] * (1 - mix) + a2[..., None] * mix
    return out.astype(np.float32)


def kill_spill(person, alpha, frame):
    """Farbsaum weg. An der Silhouette mischt sich der Hintergrund in die Person -
    steht dahinter ein knallbunter Caption-Text, leuchtet sein Farbstich um die
    Schulter herum. Der Randbereich wird darum leicht entsaettigt und abgedunkelt."""
    if alpha is None:
        return person
    a = alpha[..., 0]
    kante = cv2.GaussianBlur((a > 0.05).astype(np.float32) - (a > 0.95).astype(np.float32),
                             (0, 0), 2.0)
    kante = np.clip(kante, 0, 1)[..., None]
    grau = person.mean(axis=2, keepdims=True)
    return person * (1 - 0.35 * kante) + grau * (0.35 * kante)


def apply_duplicate_trail(comp, frame, strength, alpha=None, offset_px=14, layers=3):
    """Post-Effekt: der Text hinterlaesst versetzte Kopien fuer Speed-Gefuehl.

    Extrahiert die Text-Region ueber ein Diff comp vs. frame (die Stellen, wo
    der Compositor etwas gezeichnet hat), kopiert sie versetzt mit fallender
    Deckkraft nach links. Wirkt nur, wenn UEBERHAUPT Text gemalt wurde -
    keine Trails auf leerem Frame.
    """
    if strength <= 0.02:
        return comp
    diff = np.abs(comp.astype(np.int16) - frame.astype(np.int16)).max(axis=-1)
    text_mask = (diff > 18).astype(np.float32)
    if float(text_mask.sum()) < 500:                # zu wenig Text -> nichts zu duplizieren
        return comp
    # v88b: Ganzbild-Schmier-Schutz. Der Diff comp-vs-frame findet nicht nur
    # Text: Hintergrund-Blur, Farb-Grading, Kamera-Warp und Szenen-Blending
    # veraendern das Bild UEBERALL. Auf Nacht-B-Roll (Shibuya) deckte die
    # "Text"-Maske so fast das ganze Bild ab -> der Trail duplizierte den
    # kompletten Frame und alles wurde matschig. Deckt die Maske mehr als 6 %
    # der Flaeche ab, ist es kein isolierter Text mehr -> kein Trail.
    if float(text_mask.mean()) > 0.06:
        return comp
    # v93b: Die Person NIE mittrailen. Kamera-Schwenk/Grade verschieben die
    # Personenkante gegenueber `frame` -> der Diff haelt sie faelschlich fuer
    # Text und der Versatz erzeugt einen halbtransparenten Doppelgaenger der
    # Person (senkrechte Kamm-Streifen am Kiefer/Hals). Personen-Matte hart aus
    # der Text-Maske schneiden (leicht geweitet, damit auch die Kante raus ist).
    if alpha is not None:
        pm = person_mask(alpha)
        pm = cv2.dilate((pm > 0.15).astype(np.uint8), np.ones((9, 9), np.uint8))
        text_mask *= (1.0 - pm.astype(np.float32))
        if float(text_mask.sum()) < 500:
            return comp
    text_mask = cv2.GaussianBlur(text_mask, (0, 0), 1.6)
    out = comp.astype(np.float32).copy()
    for k in range(1, layers + 1):
        off = int(offset_px * k)
        if off <= 0:
            continue
        shifted = np.zeros_like(out)
        shifted[:, :-off] = comp[:, off:]           # nach links versetzt
        mshift = np.zeros_like(text_mask)
        mshift[:, :-off] = text_mask[:, off:]
        alpha = strength * (1.0 - k / (layers + 1)) * 0.55
        m = (mshift * alpha)[..., None]
        out = out * (1 - m) + shifted * m
    return np.clip(out, 0, 255).astype(comp.dtype)


def apply_counter_ring(comp, active, t, W, H, strength):
    """Kreisrunder Fortschrittsbogen um Zahl-Momente. Waechst mit dem Zaehler.

    Zeichnet nur bei Momenten mit `count`-Metadaten - laeuft synchron zur
    Zahl, die von 0 auf den Zielwert hochzaehlt. Ring liegt hinter dem
    Text, wirkt wie ein Timer-/Score-Ring in Sport-Grafiken.
    """
    if strength <= 0.02 or not active:
        return comp
    out = comp.copy()
    for p in active:
        c = p.get('count')
        if not c:
            continue
        t0p = p.get('t0', p.get('start', 0.0))
        dt = t - t0p
        if dt < 0:
            continue
        prog = min(max(dt / max(float(c.get('dur', 1.0)), 0.1), 0.0), 1.0)
        cx = int(p.get('cx', W / 2))
        cy = int(p.get('cy', H * 0.5))
        radius = int(min(W, H) * 0.10)
        thick = max(int(radius * 0.10), 3)
        # Hintergrund-Ring (dezent)
        cv2.circle(out, (cx, cy), radius, (60, 60, 60), thick, cv2.LINE_AA)
        # Fortschritts-Bogen (hell, Akzentfarbe)
        col = (255, 240, 200)
        end_angle = -90 + int(prog * 360)
        # ellipse mit angle steps - cv2.ellipse zeichnet Bogen
        cv2.ellipse(out, (cx, cy), (radius, radius), 0, -90, end_angle,
                    col, thick, cv2.LINE_AA)
    if strength >= 0.99:
        return out
    return (comp.astype(np.float32) * (1 - strength)
            + out.astype(np.float32) * strength).astype(comp.dtype)


def apply_split_screen(comp, frame, active, t, W, H, strength):
    """Split-Screen: der Frame wird horizontal geteilt, die Haelften driften
    an einer Luecke auseinander. Wirkt bei power=3-Momenten ohne B-Roll
    (die grossen Punkt-Aussagen). Fade rein/raus mit Moment-Kurve.
    """
    if strength <= 0.02:
        return comp
    hit = 0.0
    for p in active:
        if p.get('power', 2) < 3 or p.get('broll'):
            continue
        t0p = p.get('t0', p.get('start', 0.0))
        dur = max(p['end'] - t0p, 0.6)
        dt = t - t0p
        if dt < 0:
            continue
        if dt < 0.20:
            s = dt / 0.20
        elif dt > dur:
            s = max(0.0, 1 - (dt - dur) / 0.35)
        else:
            s = 1.0
        hit = max(hit, s)
    if hit < 0.02:
        return comp
    gap = int(H * 0.05 * hit * strength)             # bis 5 % Bildhoehe
    if gap < 2:
        return comp
    top = comp[:H // 2]
    bot = comp[H // 2:]
    out = np.zeros_like(comp)
    # Fond fuer Luecke: aus Original-Frame leicht abgedunkelt
    fond = (frame.astype(np.float32) * 0.20).astype(comp.dtype)
    out[:] = fond
    # Ober- und Unterhaelfte an die Luecke wegschieben
    top_y = 0
    bot_y = H // 2 + gap
    out[top_y:top_y + top.shape[0] - gap] = top[:top.shape[0] - gap]
    end = bot_y + bot.shape[0] - gap
    if end > H:
        end = H
    out[bot_y:end] = bot[:end - bot_y]
    return out


def apply_env_shadow(comp, frame, active, t, W, H, strength):
    """Environment-Text: ground-Momente bekommen einen weichen Kontakt-
    Schatten auf dem Untergrund, damit sie wie ein Objekt im Raum wirken
    (nicht wie Aufkleber). Analog Trail extrahieren wir die Text-Region
    aus dem Diff comp vs. frame, verschieben nach unten/rechts, verwischen
    weich und dunkeln nur AUSSERHALB des Textes ab.
    """
    if strength <= 0.02 or not active:
        return comp
    env_hit = 0.0
    for p in active:
        if p.get('tpl') != 'ground':
            continue
        # GEMALTER Text (liegend) wirft keinen Schatten - Farbe hat keine
        # Hoehe. Und vor dem Ankern liegt noch gar kein Wort da.
        if p.get('lying') or p.get('front_layer'):
            continue
        if p.get('t_word') is not None and not p.get('_gnd_cal'):
            continue
        t0p = p.get('t0', p.get('start', 0.0))
        dur = max(p['end'] - t0p, 0.6)
        dt = t - t0p
        if dt < 0:
            continue
        if dt < 0.30:
            s = dt / 0.30
        elif dt > dur:
            s = max(0.0, 1 - (dt - dur) / 0.40)
        else:
            s = 1.0
        env_hit = max(env_hit, s)
    if env_hit < 0.02:
        return comp
    diff = np.abs(comp.astype(np.int16) - frame.astype(np.int16)).max(axis=-1)
    text_mask = (diff > 15).astype(np.float32)
    if float(text_mask.sum()) < 500:
        return comp
    off_y = max(int(H * 0.014), 4)                 # Schatten nach unten
    off_x = max(int(W * 0.006), 2)                 # leicht nach rechts (Licht von links)
    shifted = np.zeros_like(text_mask)
    shifted[off_y:, off_x:] = text_mask[:-off_y, :-off_x]
    shadow = cv2.GaussianBlur(shifted, (0, 0), max(H * 0.010, 3.0))
    # Nur AUSSERHALB der Text-Pixel abdunkeln (sonst kaeme der Schatten
    # ueber den Text und dunkelt ihn selbst ab).
    shadow *= 1.0 - np.clip(text_mask, 0, 1)
    darken = strength * env_hit * 0.55 * shadow[..., None]
    return np.clip(comp.astype(np.float32) * (1 - darken), 0, 255).astype(comp.dtype)


def apply_bg_blur(frame, alpha, depth_n, strength, W, H):
    """Hintergrund-Blur (Bokeh-artig) waehrend eines Moments.

    Der Vordergrund (Person, Text) bleibt scharf, dahinter wird das Bild
    weichgezeichnet - lenkt den Blick auf den Text, wie in Kino/Interviews.

    strength: 0 = aus, 1 = maximum (Sigma ~4 % der Bildbreite).
    Maskenlogik:
      - alpha da:    Person = scharf, Rest = blur
      - alpha + depth: zusaetzliche Verlaufskante (weit weg = mehr blur)
      - nur depth:   ohne Person alpha; Fern-Ebenen blur
      - nix:         kein Effekt (kein Blindwurf)
    """
    if strength <= 0.02 or (alpha is None and depth_n is None):
        return frame
    # Blur einmalig auf verkleinertem Bild (schnell, Bokeh-freundlich).
    scale = 4
    small = cv2.resize(frame, (W // scale, H // scale))
    sigma = max(1.5, strength * (W / scale) * 0.04)
    blurred_small = cv2.GaussianBlur(small, (0, 0), sigma)
    blurred = cv2.resize(blurred_small, (W, H))
    # Vordergrund-Maske (was scharf bleibt): 1.0 = scharf, 0.0 = voll blur.
    if alpha is not None:
        # Bereinigte Personen-Maske: Hintergrund-Blobs der rohen Matte wuerden
        # als scharfe Inseln im Bokeh stehen (Halos um Autos/Pflaster).
        fg = np.clip(person_mask(alpha), 0, 1)
        # Etwas ausdehnen, damit die Text-Zone um die Person auch scharf bleibt
        # und der Uebergang natuerlich weich verlaeuft (Bokeh-Rand).
        fg = cv2.GaussianBlur(fg, (0, 0), max(H * 0.008, 2.0))
    else:
        fg = np.zeros((H, W), dtype=np.float32)
    if depth_n is not None and depth_n.shape[:2] == (H, W):
        # Tiefe weit weg (hohe Werte) -> mehr blur.
        far = np.clip(depth_n.astype(np.float32), 0, 1)
        # Fern-Ebene bekommt zusaetzlich blur, Nah-Bereich schuetzt sich.
        fg = np.clip(fg + (1 - far) * 0.5, 0, 1)
    blur_mask = (1 - fg) * strength
    m = blur_mask[..., None]
    return (frame.astype(np.float32) * (1 - m)
            + blurred.astype(np.float32) * m).astype(frame.dtype)


def composite_frame(frame, alpha, t, plans, words, face_xy, cfg, S, W, H, cam_state=None,
                    scene_off=(0.0, 0.0), aud=(0.0, 0.0, 0.0), depth_n=None,
                    scene_vel=0.0, H_cum=None, track_gen=0):
    a_rms, a_bass, a_onset = aud

    def occ_for(p):
        """Okklusion: Maske der Bildteile, die VOR dem Text liegen.
        Zwei Quellen, vereinigt: (1) Tiefen-Fenster (Objekte naeher als der
        Text), (2) die Person-Matte selbst. Gerade auf B-Roll mit sichtbarer
        Person ist die Matte die verlaessliche Quelle - so laeuft die Person
        sauber VOR dem liegenden Boden-Text, statt dass der Text auf ihr klebt.
        d_ref wird beim ersten aktiven Frame am (kalibrierten) Text-Ort gemessen."""
        occ_d = None
        if depth_n is not None:
            if 'd_ref' not in p:
                cx_ = int(p.get('cx', W / 2)); cy_ = int(p.get('cy', H * 0.8))
                hw = int(min(p['arr'].shape[1] * 0.40, W * 0.3))
                hh = int(min(p['arr'].shape[0] * 0.28, H * 0.12))
                reg = depth_n[max(cy_ - hh, 0):min(cy_ + hh, H),
                              max(cx_ - hw, 0):min(cx_ + hw, W)]
                p['d_ref'] = float(np.median(reg)) if reg.size else 0.5
            occ_d = np.clip((depth_n - p['d_ref'] - 0.07) / 0.10, 0, 1)
            occ_d = cv2.GaussianBlur(occ_d, (0, 0), 4)
        occ_a = None
        if (p.get('scene_ground') or p.get('broll')) and alpha is not None:
            occ_a = person_mask(alpha)     # nur die echte Person, keine Blobs
        if occ_d is None and occ_a is None:
            return None
        # Ist die saubere Person-Matte da, occludiert NUR sie den Szenen-Text
        # (die Person steht davor, das Wort liegt dahinter in der Szene). Die
        # grobe Tiefenkarte wuerde den Text an jeder Hintergrund-Kante (Autos,
        # Bordstein) zerschneiden -> haessliche Umrisse. Tiefe nur ohne Matte
        # (echtes Aerial-B-Roll ohne Person).
        occ = occ_a if occ_a is not None else occ_d
        prev = p.get('_occ_prev')
        if prev is not None and prev.shape == occ.shape:
            occ = 0.6 * occ + 0.4 * prev
        p['_occ_prev'] = occ
        return occ
    glitch_rng = np.random.default_rng(int(t * 1000) % 99991)

    def apply_count(obj, dt):
        c = obj.get('count')
        if not c or dt < 0 or 'builder' not in obj:
            return
        s = c['fmt'](min(dt, c['dur']))
        if s == obj.get('_ctxt'):
            return
        obj['_ctxt'] = s
        res = obj['builder'](s)
        if isinstance(res, tuple):
            obj['o_arr'], obj['f_arr'] = res
        else:
            obj['arr'] = res
    active = [p for p in plans if p['start'] <= t < p['end'] + 0.40]   # v82: Exit-Fenster

    # Hintergrund-Blur (v69): waehrend eines aktiven Moments den Hintergrund
    # weichzeichnen. Staerke folgt der max. Moment-Fade-Kurve, damit der
    # Blur mit dem Text ein/ausblendet. Auf B-Roll aus - dort ist der
    # Hintergrund das Motiv, nicht die Person.
    bg_blur = float(cfg['effects'].get('bg_blur', 0.0) or 0.0)
    if bg_blur > 0.02 and active and (alpha is not None or depth_n is not None):
        bstr = 0.0
        for p in active:
            # Szenen-Text (Boden/Wand/Wasser): die Szene ist der Star - kein
            # Bokeh drueber. Verhindert ausserdem Matte-Halos im Hintergrund.
            # Und Bokeh nur fuer echte Keyword-Momente - laufende Wortgruppen
            # (Stacks) rechtfertigen keinen Tiefenschaerfe-Eingriff.
            if p.get('broll') or p.get('scene_ground') or 'kw_i' not in p:
                continue
            dur = max(p['end'] - p.get('t0', p['start']), 0.9)
            dtp = t - p.get('t0', p['start'])
            if dtp < 0:
                s = 0.0
            elif dtp < 0.20:
                s = dtp / 0.20                      # rein
            elif dtp > dur:
                s = max(0.0, 1 - (dtp - dur) / 0.35)  # raus
            else:
                s = 1.0
            # Power-3-Momente kriegen mehr Blur (bewusster Fokus).
            s *= 0.75 + 0.25 * (float(p.get('power', 2)) - 1) / 2.0
            bstr = max(bstr, s)
        if bstr > 0.02:
            # NUR die Person-Matte fuer die Tiefenschaerfe nutzen, NICHT die
            # grobe Tiefenkarte: seit Szenen-Text auch mit Gesicht Tiefe rechnet,
            # wuerde depth_n hier sichtbare Kanten-Halos im Hintergrund ziehen.
            frame = apply_bg_blur(frame, alpha, None, bg_blur * bstr, W, H)

    comp = frame.copy()
    person = frame if alpha is not None else None
    lock = cfg['effects'].get('scene_lock', True)

    def scene_shift(p):
        """Verankert Hintergrund-Texte in der Szene: sie wandern mit Kameraschwenks mit.
        Auf B-Roll (Drohne, FPV) darf der Text weiter wandern - er gehoert zur Welt."""
        if not lock:
            return 0.0, 0.0
        if 's0' not in p:
            p['s0'] = scene_off
        dx = scene_off[0] - p['s0'][0]
        dy = scene_off[1] - p['s0'][1]
        lim = W * (0.30 if p.get('broll') else 0.12)
        return max(-lim, min(dx, lim)), max(-lim * 0.6, min(dy, lim * 0.6))
    behind_str = 0.0          # staerkster aktiver Hintergrund-Text (fuer Kontaktschatten)

    for p in active:
        if p['tpl'] not in ('behind', 'blurin'): continue
        wd = words[p['kw_i']]
        t0p = p.get('t0', wd['start'])     # Sofort-Hook: Karte laeuft ab Frame 1
        dur = max(p['end'] - t0p, 0.9)
        dt = t - t0p
        if dt < 0: continue
        if dt < 0.14: strength = dt / 0.14
        elif dt > dur: strength = exit_env(dt - dur, 0.30)   # v82: haelt, dann los
        else: strength = 1.0
        behind_str = max(behind_str, strength)
        dim = (cfg['effects']['dim_behind'] if p['tpl'] == 'behind'
               else cfg['effects']['dim_blurin']) * strength
        if p.get('tokens'):
            dim = 0.0                        # Kompositionen: Szene bleibt hell
        if dim > 0.005:
            cy0 = p.get('by', H * 0.32)
            yy = (np.arange(H, dtype=np.float32) - cy0) / (H * 0.9)
            xx = (np.arange(W, dtype=np.float32) - W / 2) / (W * 0.75)
            rad = np.clip(np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2), 0, 1)
            comp *= (1 - dim * (0.55 + 0.45 * rad))[..., None]
        if p['tpl'] == 'behind' and strength > 0.05 and not p.get('tokens'):  # leichte Tiefen-Unschaerfe
            small = cv2.resize(comp, (W // 3, H // 3))
            soft = cv2.resize(cv2.GaussianBlur(small, (0, 0), 2.2), (W, H))
            comp = comp * (1 - 0.45 * strength) + soft * (0.45 * strength)
        if p['tpl'] == 'behind':
            sdx, sdy = scene_shift(p)
            by = p.get('by', H * 0.292)
            fade = (strength if dt > dur else 1)
            apply_count(p, dt)
            if p.get('tokens'):
                out_env = exit_env(dt - dur, 0.20)   # v82: Cutter-Exit
                for tok in p['tokens']:
                    dtt = t - tok['t'] + 0.07   # v82: Lese-Vorlauf
                    if dtt < 0 or out_env <= 0:
                        continue
                    apply_count(tok, t - tok['t'])
                    arr_t = tok['arr']
                    oy_t = tok['oy']
                    zz, adx_t, aop_t = 1.0, 0.0, 1.0
                    if tok.get('role') == 'core':
                        arr_t, adx_t, ady_t, zz, aop_t = anim_apply(p, arr_t, aud, dtt)
                        oy_t = tok['oy'] + ady_t - (arr_t.shape[0]
                                                    - tok['arr'].shape[0]) / 2
                    role = tok.get('role')
                    if role == 'pre':
                        e = ease_expo(dtt / 0.5)
                        px_off, py_off = -(1 - e) * W * 0.07, 0.0
                        sc = 1.0
                    elif role == 'script':
                        e = ease_back(min(dtt / 0.30, 1))
                        px_off, py_off = 0.0, 0.0
                        sc = 0.80 + 0.20 * e
                    else:
                        e = ease_expo(dtt / (0.5 * (1 + 0.10 * hand_jitter(tok['t'] * 37))))
                        entr = p.get('entr', 'rise')
                        px_off, py_off = 0.0, 0.0
                        sc = 0.965 + 0.035 * e
                        if entr == 'edge_l':
                            px_off = -(W * 0.55 + arr_t.shape[1] / 2) * (1 - e)
                        elif entr == 'edge_r':
                            px_off = (W * 0.55 + arr_t.shape[1] / 2) * (1 - e)
                        elif entr == 'drop':
                            py_off = -H * 0.24 * (1 - e)
                        elif entr == 'zoom':
                            sc = 1.5 - 0.5 * e
                        elif entr == 'swing':      # schwingt von der Seite herein
                            eb = ease_back(min(dtt / 0.55, 1))
                            px_off = -(W * 0.30) * (1 - eb)
                            sc = 0.92 + 0.08 * eb
                        elif entr == 'flip':       # kippt aus der Tiefe nach vorn
                            sc = 0.55 + 0.45 * e
                            py_off = -H * 0.06 * (1 - e)
                        elif entr == 'morph':      # Fluid-Morph: fliesst in die Form
                            arr_t = _liquid(arr_t, (1 - e) ** 1.5, seed=int(tok['t'] * 37))
                            sc = 0.97 + 0.03 * e
                        elif entr == 'emerge':
                            # Wort fuer Wort hinter der Person hervorgeschoben:
                            # jedes Wort wird aus ihrer Position heraus aufgedeckt,
                            # sobald es gesprochen wird.
                            ee = smoothstep(min(dtt / 1.10, 1))
                            sc = 0.94 + 0.06 * ee
                            px = float(face_xy[0]) if face_xy is not None else W / 2
                            ziel_x = W / 2 + tok['ox'] + sdx
                            lok = (px - ziel_x) / max(sc, 0.01) + arr_t.shape[1] / 2
                            p_halb = (float(face_xy[2]) if (face_xy is not None
                                                            and len(face_xy) > 2)
                                      else W * 0.055) / max(sc, 0.01)
                            halb = p_halb + ee * arr_t.shape[1] * 0.55
                            arr_t = reveal_from(arr_t, lok, halb, weich=30.0)
                            px_off = (px - ziel_x) * 0.14 * (1 - ee)
                            py_off = 0.0
                        else:
                            py_off = (1 - e) * H * 0.05
                    paste(comp, arr_t, W / 2 + tok['ox'] + sdx + px_off + adx_t,
                          by + oy_t + sdy + py_off,
                          W, H, scale=sc * (0.985 + 0.015 * out_env) * zz,
                          opacity=min(dtt / 0.12, 1) * out_env * aop_t)
            elif p.get('letters'):
                for li, (sl, off) in enumerate(p['letters']):
                    # v82: Stagger streut +-0.5 Frames - mechanisch gleiche
                    # Abstaende sind der Vorlagen-Tell schlechthin.
                    dl = dt - li * 0.05 + 0.015 * hand_jitter(p['kw_i'] * 31 + li)
                    if dl < 0:
                        continue
                    e = ease_back(dl / (0.32 * (1 + 0.08 * hand_jitter(p['kw_i'] * 7 + li))))
                    paste(comp, sl, W / 2 + sdx + off, by + sdy + (1 - e) * H * 0.055,
                          W, H, scale=0.9 + 0.1 * e, opacity=min(dl / 0.12, 1) * fade)
            else:
                e = smoothstep(dt / 0.8)
                live = 1.0 + 0.018 * min(dt / max(dur, 1.0), 1.0)   # Micro-Drift: lebt weiter
                arr_b, adx_b, ady_b, asc_b, aop_b = anim_apply(p, p['arr'], aud, dt)
                oy_b = ady_b - (arr_b.shape[0] - p['arr'].shape[0]) / 2
                live *= asc_b
                # v82: Entrance-Dauer streut +-10% pro Wort (Hand-Keyframe)
                ex = ease_expo(dt / (0.60 * (1 + 0.10 * hand_jitter(p['kw_i']))))
                dx0 = dy0 = 0.0
                sc = 1.04 - 0.04 * e
                op = smoothstep(dt / 0.30)   # v82: Alpha folgt der Bewegung
                entr = p.get('entr', 'rise')
                if entr == 'edge_l':
                    dx0 = -(W * 0.55 + arr_b.shape[1] / 2) * (1 - ex)
                    op = min(dt / 0.10, 1)
                elif entr == 'edge_r':
                    dx0 = (W * 0.55 + arr_b.shape[1] / 2) * (1 - ex)
                    op = min(dt / 0.10, 1)
                elif entr == 'drop':
                    dy0 = -H * 0.28 * (1 - ex)
                    op = min(dt / 0.15, 1)
                elif entr == 'zoom':
                    sc = (1.55 - 0.55 * ex) * (1.0 - 0.04 * e)
                    op = min(dt / 0.20, 1)
                elif entr == 'swing':          # schwingt seitlich herein, federt aus
                    eb = ease_back(min(dt / 0.6, 1))
                    dx0 = -(W * 0.34) * (1 - eb)
                    sc = (0.90 + 0.10 * eb) * (1.0 - 0.04 * e)
                    op = min(dt / 0.12, 1)
                elif entr == 'flip':           # klappt aus der Tiefe nach vorn
                    sc = (0.5 + 0.5 * ex) * (1.0 - 0.04 * e)
                    dy0 = -H * 0.05 * (1 - ex)
                    op = min(dt / 0.18, 1)
                elif entr == 'morph':          # FLUID-MORPH: das Wort fliesst aus
                    # einer weichen Verzerrung in seine Form - kein harter Schnitt
                    # zwischen zwei Chunks, sondern ein Uebergang. High-End-Signatur.
                    arr_b = _liquid(arr_b, (1 - ex) ** 1.5, seed=p['kw_i'])
                    sc = (1.02 - 0.02 * e)
                    op = min(dt / 0.22, 1)
                elif entr == 'emerge':
                    # HERAUSGESCHOBEN: Das Wort wird aus der Person heraus
                    # aufgedeckt - erst der Teil direkt hinter ihr, dann waechst es
                    # gemaechlich nach beiden Seiten heraus. Zusammen mit der
                    # Freistellung (die Person bleibt davor) liest sich das, als
                    # schoebe sie das Wort hinter sich hervor.
                    # smoothstep statt ease_out: laeuft sanft an und sanft aus -
                    # ease_out schiesst am Anfang los, das wirkt gehetzt.
                    ee = smoothstep(min(dt / 1.10, 1))
                    sc = (0.94 + 0.06 * ee) * (1.0 - 0.04 * e)
                    op = 1.0
                    px = float(face_xy[0]) if face_xy is not None else W / 2
                    lok = (px - (W / 2 + sdx)) / max(sc, 0.01) + arr_b.shape[1] / 2
                    # Startfenster = ungefaehr die Breite der Person. Groesser waere
                    # sinnlos: das Wort waere sofort halb sichtbar, statt HINTER ihr
                    # zu stecken.
                    p_halb = (float(face_xy[2]) if (face_xy is not None
                                                    and len(face_xy) > 2)
                              else W * 0.055) / max(sc, 0.01)
                    halb = p_halb + ee * arr_b.shape[1] * 0.55   # voll erst gegen Ende
                    arr_b = reveal_from(arr_b, lok, halb, weich=34.0)
                    dx0 = (px - (W / 2 + sdx)) * 0.14 * (1 - ee)   # leichter Schub
                    dy0 = 0.0
                else:
                    dy0 = H * 0.10 * (1 - ex)
                # Motion Blur waehrend des Einflugs: verkauft die Geschwindigkeit
                mb_amt = min((abs(dx0) + abs(dy0)) / (W * 0.02), 1.0) * 6.0
                if entr == 'zoom':
                    mb_amt = (1 - ex) * 4.0
                # v82: Abgang mit Absicht - der Exit SPIEGELT den Entrance.
                # edge-Woerter gehen seitlich raus, zoom waechst nach vorn weg,
                # der Rest weicht leicht nach oben zurueck (recede). Ein
                # uniformer Exit fuer 9 Entrances war der letzte Preset-Tell.
                x_sc, x_dv = exit_pose(dt - dur, 0.30, drop=False)
                xo = min(max((dt - dur) / 0.30, 0.0), 1.0) ** 2
                if xo > 0 and entr in ('edge_l', 'edge_r'):
                    dx0 += (-1 if entr == 'edge_l' else 1) * W * 0.03 * xo
                    x_dv = 0.0
                elif xo > 0 and entr == 'zoom':
                    x_sc = 2.0 - x_sc            # raus wie rein: nach vorn
                    x_dv = 0.0
                paste(comp, arr_b, W / 2 + sdx + dx0 + adx_b,
                      by + oy_b + sdy + dy0 + x_dv * arr_b.shape[0],
                      W, H, scale=sc * live * x_sc, opacity=op * fade * aop_b, blur=mb_amt)
        else:
            e = ease_out(min(dt / 0.34, 1))
            sdx, sdy = scene_shift(p)
            arr_bl, adx, ady, asc, aop = anim_apply(p, p['arr'], aud, dt)
            ady -= (arr_bl.shape[0] - p['arr'].shape[0]) / 2
            paste(comp, arr_bl, W / 2 + sdx + adx, p.get('by', H * 0.333) + sdy + ady,
                  W, H, scale=(1.16 - 0.16 * e) * asc,
                  opacity=smoothstep(dt / 0.20) * (strength if dt > dur else 1) * aop,
                  blur=(1 - e) * 11)

    if alpha is not None:
        # Bereinigte Personen-Maske fuer ALLES, was die Person zurueck ueber
        # den Text legt: die rohe Matte markiert Hintergrund-Blobs (Autos,
        # Pflaster) als 'Person' - kill_spill/Schatten/Repaste zeichnen dann
        # sichtbare Umrisse um diese Blobs (Halos im ganzen Bild).
        alpha_p = person_mask(alpha)[..., None]
        # Kein Farbsaum: der Caption-Text hinter der Person darf nicht um die
        # Schulter herumleuchten.
        if cfg['effects'].get('matte_spill', True):
            person = kill_spill(person, alpha_p, frame)
        # KONTAKTSCHATTEN: Die Person wirft einen weichen Schatten auf die
        # Textebene hinter ihr. Ohne ihn ist der Text nur ausgeschnitten - mit
        # ihm sitzt er IM Raum. Genau daran erkennt man 2026 den Unterschied
        # zwischen Vorlagen-Look und Produktion.
        if PERSON_SHADOW > 0 and behind_str > 0.02:
            a0 = alpha_p[..., 0]
            sig = max(min(W, H) * 0.016, 3.0)
            sh = cv2.GaussianBlur(a0, (0, 0), sig)
            M = np.float32([[1, 0, W * 0.008], [0, 1, H * 0.012]])   # Licht von oben links
            sh = cv2.warpAffine(sh, M, (W, H), borderValue=0.0)
            sh = np.clip(sh - a0, 0, 1)          # nur ausserhalb der Person
            k = 0.55 * PERSON_SHADOW * behind_str
            comp = comp * (1.0 - k * sh[..., None])
        comp = person * alpha_p + comp * (1 - alpha_p)

    def draw_small(p, g_out, tdx=0.0, tdy=0.0, x_sc=1.0, x_dv=0.0):
        for it in p['small']:
            wd = words[it['i']]
            # v82: 70ms Vorlauf - Lesen ist schneller als Hoeren, das Wort
            # steht beim Einsatz schon (Broadcast-Praxis: 50-100ms Lead).
            dt = t - wd['start'] + 0.07
            if dt < 0: continue
            e = ease_back(dt / (0.26 * (1 + 0.08 * hand_jitter(it['i'] * 13))))  # v82
            paste(comp, it['arr'], it['cx'] + tdx,
                  it['cy'] + tdy + (1 - e) * H * 0.024 + x_dv * it['arr'].shape[0],
                  W, H, scale=(0.88 + 0.12 * e) * x_sc,
                  opacity=min(dt / 0.10, 1) * g_out)

    for p in active:
        # v82: Cutter-Exit statt linearem Fade - Deckkraft haelt und laesst
        # dann los, dazu minimaler Scale-Settle + Drift (exit_pose).
        # Exit-Dauer skaliert mit der Schriftgroesse: grosse Display-Type
        # braucht laengeren Abgang als ein 46px-Label (Netzhaut-Footprint).
        # Power-3-Momente halten 40ms extra, bevor sie loslassen.
        _a = p.get('arr') if 'arr' in p else p.get('f_arr')
        ah = _a.shape[0] if _a is not None else H * 0.06
        # v97: Flow-Caption raeumt knackig, damit ein Satz weg ist, bevor der
        # naechste an derselben Stelle steht (kein Doppel-Stack im Fluss).
        x_dur = 0.15 if p['tpl'] == 'flow' else 0.20 + 0.12 * min(ah / (H * 0.15), 1.0)
        over = t - p['end']
        if p.get('power', 2) >= 3:
            over -= 0.04
        g_out = exit_env(over, x_dur)
        x_sc, x_dv = exit_pose(over, x_dur)
        tdx, tdy = track_offset(p, face_xy, cfg)
        if p.get('front_layer') and p['tpl'] == 'ground':
            # Boden-Text VOR der Person (kein freier Boden im Bild): liegt
            # perspektivisch flach ueber allem - lesbar statt unsichtbar.
            # Basis ist der SPRECH-Zeitpunkt, nicht der vorgezogene Start.
            _dtf = t - p.get('t_word', p.get('t0', p['start']))
            if _dtf >= 0:
                _sdx, _sdy = scene_shift(p)
                _e = smoothstep(_dtf / 0.75)
                arr_fl, adx_fl, dy_fl, asc_fl, aop_fl = anim_apply(p, p['arr'], aud, _dtf)
                dy_fl -= (arr_fl.shape[0] - p['arr'].shape[0]) / 2
                paste_scene(comp, arr_fl, p.get('cx', W / 2) + _sdx + adx_fl,
                            p['cy'] + _sdy + dy_fl + (1 - _e) * H * 0.03,
                            W, H, scale=(0.97 + 0.03 * _e) * asc_fl,
                            opacity=min(_dtf / 0.4, 1) * g_out * aop_fl * 0.92,
                            refract=0.0, ripple=0.05, grain=1.6,
                            occ=None, blur=0.0)
            continue
        if p['tpl'] == 'flow':
            # v97c Flow-Caption: STRUKTUR bleibt (feste Rollen-Zeilen, links).
            # Der Block ist verankert, folgt der Person aber SANFT - stark
            # gedaempft (0.10) und eng begrenzt (W*0.045): fuehlt sich verbunden
            # an, wandert nicht (der fruehere 0.22/0.09-Follow brach die Struktur).
            # Schaltbar per effects.caption_follow. Dazu ein dezenter Settle auf
            # dem Keyword ("passend bewegen").
            fdx = fdy = 0.0
            if cfg['effects'].get('caption_follow', True) and not p.get('broll') \
                    and 'anchor' in p:
                tgt = (face_xy[0] - p['anchor'][0], face_xy[1] - p['anchor'][1])
                fp = p.setdefault('fpos', [0.0, 0.0])
                fp[0] += 0.10 * (tgt[0] - fp[0])
                fp[1] += 0.10 * (tgt[1] - fp[1])
                lim = W * 0.045
                fdx = max(-lim, min(fp[0] * 0.6, lim))
                fdy = max(-lim * 0.5, min(fp[1] * 0.5, lim * 0.5))
            for it in p['front']:
                wd = words[it['i']]
                dt = t - wd['start'] + 0.07          # Lese-Vorlauf
                if dt < 0:
                    continue
                if it.get('role') == 'key' and it.get('letters'):
                    n = len(it['letters'])
                    reveal = ease_out(dt / (0.17 * (1 + 0.08 * hand_jitter(it['i']))))
                    vis_px = None
                    k_full = int(min(reveal * n, n))
                    if k_full < n:
                        frac = reveal * n - k_full
                        l0, l1 = it['letters'][k_full]
                        vis_px = (l0 + (l1 - l0) * frac) + 40
                    # dezenter Settle: Keyword landet minimal groesser und
                    # setzt sich weich auf 1.0 (gezielte, ruhige Bewegung)
                    k_settle = 1.0 + 0.05 * (1 - smoothstep(min(dt / 0.42, 1.0)))
                    paste(comp, it['arr'],
                          it['cx'] + fdx - (0 if vis_px is None
                                            else (it['arr'].shape[1] - vis_px) / 2),
                          it['cy'] + fdy + x_dv * it['arr'].shape[0],
                          W, H, scale=x_sc * k_settle,
                          opacity=g_out, crop_w=vis_px)
                else:
                    e = ease_back(dt / (0.24 * (1 + 0.08 * hand_jitter(it['i']))))
                    paste(comp, it['arr'],
                          it['cx'] + fdx,
                          it['cy'] + fdy + (1 - e) * H * 0.020 + x_dv * it['arr'].shape[0],
                          W, H, scale=(0.86 + 0.14 * e) * x_sc,
                          opacity=min(dt / 0.10, 1) * g_out)
            continue
        if p['tpl'] == 'stack':
            # Personen-Tracking: die Gruppe haengt an der Person und geht mit,
            # wenn das gerade passt (Gesicht da, keine B-Roll). Sanft per EMA.
            fdx = fdy = 0.0
            if cfg['effects'].get('tracking', True) and not p.get('broll') \
                    and 'anchor' in p:
                tgt = (face_xy[0] - p['anchor'][0], face_xy[1] - p['anchor'][1])
                fp = p.setdefault('fpos', [0.0, 0.0])
                fp[0] += 0.22 * (tgt[0] - fp[0])
                fp[1] += 0.22 * (tgt[1] - fp[1])
                lim = W * 0.09
                fdx = max(-lim, min(fp[0] * 0.85, lim))
                fdy = max(-lim * 0.6, min(fp[1] * 0.6, lim * 0.6))
            slide_dir = -1 if p.get('side', 0) == 0 else 1
            for it in p['front']:
                wd = words[it['i']]
                dt = t - wd['start'] + 0.07     # v82: Lese-Vorlauf
                if dt < 0: continue
                e = ease_expo(dt / (0.38 * (1 + 0.08 * hand_jitter(it['i']))))  # v82
                paste(comp, it['arr'],
                      it['cx'] + fdx + slide_dir * (1 - e) * W * 0.045,
                      it['cy'] + fdy + (1 - e) * H * 0.009 + x_dv * it['arr'].shape[0],
                      W, H, scale=(0.97 + 0.03 * e) * x_sc,
                      opacity=min(dt / 0.09, 1) * g_out)
            continue
        if 'kw_i' not in p:
            continue                       # Kamera-Impulse: kein Text zu zeichnen
        wd = words[p['kw_i']]
        dt = t - p.get('t0', wd['start'])  # Sofort-Hook: Karte laeuft ab Frame 1
        if p['tpl'] == 'cascade' and dt >= 0:
            n = len(p['letters'])
            # v82: Wipe mit ease_out - startet schnell, landet weich. Ein
            # linearer Crop mit konstanter Geschwindigkeit las sich wie ein
            # Ladebalken, nicht wie kinetische Typo.
            reveal = ease_out(dt / (0.32 * (1 + 0.10 * hand_jitter(p['kw_i']))))
            vis_px = None
            k_full = int(min(reveal * n, n))
            if k_full < n:
                frac = reveal * n - k_full
                l0, l1 = p['letters'][k_full]
                vis_px = (l0 + (l1 - l0) * frac) + 40
            arr_c, adx, ady, asc, aop = anim_apply(p, p['arr'], aud, dt)
            ady -= (arr_c.shape[0] - p['arr'].shape[0]) / 2
            paste(comp, arr_c,
                  p['cx'] + tdx + adx - (0 if vis_px is None
                                         else (p['arr'].shape[1] - vis_px) / 2),
                  p['cy'] + tdy + ady + x_dv * p['arr'].shape[0],
                  W, H, scale=asc * x_sc,
                  opacity=g_out * aop, crop_w=vis_px)
            draw_small(p, g_out, tdx, tdy, x_sc, x_dv)
        elif p['tpl'] == 'ground' and dt >= 0:
            # v91: liegender Boden-Text auf B-Roll MIT Person -> Anker einmalig
            # auf die klare Strasse verschieben (weg vom Bild-Zentrum, wo bei
            # Kameraschwenk-nach-unten Arm/Pulli stehen). Danach traegt die
            # Person-Matte die Okklusion: das Wort liegt hinter ihr auf dem Boden.
            _scene_cal = ((p.get('scene_ground') or p.get('broll'))
                          and (p.get('lying') or p.get('szene') == 'wand')
                          and alpha is not None)
            # Schnitt waehrend der Anzeige: neue Szene -> neu ankern. Das Wort
            # gehoert zur Flaeche der NEUEN Einstellung, nicht zur alten.
            if (_scene_cal and p.get('_gnd_cal') and not p.get('front_layer')
                    and p.get('_gnd_gen') is not None
                    and p['_gnd_gen'] != track_gen):
                p['_gnd_cal'] = False
                p.pop('t_anchor', None)
            if _scene_cal and not p.get('_gnd_cal'):
                # Rollende Union der Personen-Maske (mit Decay): eine einzelne
                # Frame-Maske ist bei Bewegung fragmentiert; eine ewige Union
                # hielte jeden je besetzten Fleck fuer belegt. Der Anker wird
                # JEDEN Frame versucht - sobald die Kamera die Flaeche
                # freigibt, liegt das Wort dort. Vorher wird nichts gezeichnet:
                # die Kamera findet ein Wort, das schon da ist.
                _am = person_mask(alpha)
                _acc = p.get('_gnd_acc')
                # Decay 0.6: schnell genug, dass der "Geist" der Person das
                # frisch freigeschwenkte Pflaster nicht blockiert (2-3 Frames),
                # aber traege genug gegen Einzel-Frame-Fragmente der Matte.
                p['_gnd_acc'] = _am if _acc is None else np.maximum(_acc * 0.6, _am)
                p['_gnd_n'] = p.get('_gnd_n', 0) + 1
                _t_word = p.get('t_word', p['start'])
                if p.get('broll') and float(_am.mean()) < 0.05:
                    # Aerial ohne Person: Standard-Anker gilt sofort
                    p['t_anchor'] = t
                    p['_gnd_gen'] = track_gen
                    p['_gnd_cal'] = True
                    p.pop('_gnd_acc', None)
                else:
                    _ga = None
                    # Anker-Fenster: fruehestens 0.6s vor dem Wort. Der
                    # Regisseur timt den Schwenk auf das Wort - frueher ankern
                    # hiesse: Track-Referenz in der Sprecher-Phase (Muell) und
                    # eine Flaeche, die der Schwenk gleich wieder wegschiebt.
                    if p['_gnd_n'] >= 2 and t >= _t_word - 0.6:
                        _avx = p.get('anchor', (None, None))[0]   # Personen-x
                        # Wo ist die Flaeche? Talking-Head: der Boden liegt
                        # UNTER dem Sprecher (Band unten). B-Roll/Kamera nach
                        # unten: praktisch das ganze Bild IST die Flaeche.
                        if not p.get('lying') and p.get('szene') == 'wand':
                            _band = (0.28, 0.72)
                        elif p.get('broll'):
                            _band = (0.22, 1.02)
                        else:
                            _band = (0.60, 1.02)
                        # Overhang erlaubt: das Wort darf am unteren Rand
                        # anliegen - der laufende Schwenk schiebt es voll ins
                        # Bild (Welt-Verankerung). So liegt es schon da, wenn
                        # die Kamera ankommt. Der Tiefen-Check (depth_n) stellt
                        # sicher, dass dort wirklich eine Flaeche liegt.
                        # Immer voll im Bild ankern: ab t_word-0.6 zeigt die
                        # Kamera die Flaeche bereits gross genug.
                        _ga = ground_anchor(p['_gnd_acc'], p['arr'], W, H,
                                            avoid_x=_avx, band=_band)
                    if _ga:
                        p['cx'], p['cy'] = _ga
                        p.pop('d_ref', None)  # Tiefe neu am Boden messen
                        p.pop('H_ref', None)  # Track-Referenz am neuen Anker
                        p['t_anchor'] = t
                        p['_gnd_gen'] = track_gen
                        p['_gnd_cal'] = True
                        p.pop('_gnd_acc', None)
                    elif t >= _t_word and not p.get('broll'):
                        # Bis zum gesprochenen Wort keine freie Flaeche (der
                        # Sprecher fuellt das Bild): Wort liegt VOR der Person -
                        # gezeichnet NACH dem Personen-Repaste, sonst unsichtbar.
                        p['front_layer'] = True
                        p['_gnd_cal'] = True
                        p.pop('_gnd_acc', None)
                    else:
                        continue           # liegt erst, wenn die Kamera die
                                           # Flaeche freigibt
            if p.get('front_layer'):
                continue                   # wird NACH dem Personen-Repaste gezeichnet
            sdx, sdy = scene_shift(p)
            apply_count(p, dt)
            if p.get('cshadow') is not None:
                paste(comp, p['cshadow'], p.get('cx', W / 2) + sdx + p['csh_dx'],
                      p['cy'] + sdy + p['csh_dy'] + p['cshadow'].shape[0] * 0.30,
                      W, H, opacity=min(dt / 0.5, 1.0) * g_out)
            # Szenen-Text (Boden/Wasser/Wand) laeuft ueber denselben Premium-
            # Pfad wie B-Roll: perspektivisch in der Flaeche, von der Person
            # verdeckt, kamera-getrackt - auch wenn ein Gesicht im Bild ist.
            g_broll = p.get('scene_ground') or p.get('broll')
            occ_g = occ_for(p) if g_broll else None
            cam_blur = min(scene_vel * 0.45, 5.0) if g_broll else 0.0
            # Blend-Charakter: Wasser wellt/bricht (refract, ripple), fester
            # Boden ist flach aufgemalt (kein Refract, wenig Ripple, leicht
            # transparent, damit die Pflaster-Textur durchscheint).
            gp = p.get('ground_paint')
            g_refract = 1.0 if p.get('scene_blend') else 0.0
            g_ripple = (0.06 if p.get('glass')
                        else 0.05 if gp
                        else (0.10 if p.get('scene_blend') else 0.12))
            g_grain = 1.5 if p.get('glass') else (1.6 if gp else 2.2)
            g_opac = (0.90 if gp else 0.74 if p.get('scene_blend')
                      else (1.0 if p.get('glass') else 0.97))
            tracked = (g_broll and p.get('track3d') and H_cum is not None)
            if tracked:
                # Planares Kamera-Tracking: Referenz beim ersten aktiven Frame,
                # danach bewegt die akkumulierte Homographie den Text wie ein
                # Objekt in der Welt (waechst, kippt, zieht vorbei).
                if 'H_ref' not in p or p.get('H_gen') != track_gen:
                    p['H_ref'] = np.linalg.inv(H_cum)
                    p['H_gen'] = track_gen
                H_rel = H_cum @ p['H_ref']
                if p.get('glass_frames'):
                    gf = p['glass_frames']
                    p['arr'] = gf[blender_engine.anim_loop_idx(dt, len(gf))]
                # GEMALT = starr: liegender Szenen-Text ist Teil der Welt.
                # Keine Daempfung, kein Drift-Deckel - er klebt exakt auf der
                # Flaeche und verlaesst das Bild mit dem Schwenk wie ein
                # echtes Objekt. Nur stehende B-Roll-Texte behalten die
                # weiche AE-Daempfung (Lesbarkeit).
                rigid = bool(p.get('lying')) and not p.get('glass')
                if not rigid:
                    d_tr = 0.9                   # Grund-Daempfung (AE-Praxis)
                    H_rel = d_tr * H_rel + (1 - d_tr) * np.eye(3)
                    H_rel /= H_rel[2, 2]
                    # Adaptiv: Drift des Text-Zentrums deckeln - der Text bleibt
                    # im Bild und lesbar, bewegt sich aber weiter echt mit
                    ctr = H_rel @ np.array([p.get('cx', W / 2), p['cy'], 1.0])
                    ctr /= ctr[2]
                    drift = float(np.hypot(ctr[0] - p.get('cx', W / 2), ctr[1] - p['cy']))
                    lim = H * 0.26
                    if drift > lim:
                        d2 = lim / drift
                        H_rel = d2 * H_rel + (1 - d2) * np.eye(3)
                        H_rel /= H_rel[2, 2]
                # VOR dem gesprochenen Wort gilt: ist das verankerte Wort vom
                # Schwenk komplett aus dem Bild geschoben worden (der Zuschauer
                # hat es nie gesehen), wird still NEU geankert - auf der
                # Flaeche, die JETZT sichtbar ist. So liegt das Wort genau da,
                # wo die Kamera zum Sprech-Zeitpunkt ankommt.
                if rigid and t < p.get('t_word', p['start']):
                    _c2 = H_rel @ np.array([p.get('cx', W / 2), p['cy'], 1.0])
                    _c2 /= _c2[2]
                    _hw2 = p['arr'].shape[1] * 0.6
                    _hh2 = p['arr'].shape[0] * 0.6
                    if (_c2[0] < -_hw2 or _c2[0] > W + _hw2
                            or _c2[1] < -_hh2 or _c2[1] > H + _hh2):
                        p['_gnd_cal'] = False
                        p.pop('t_anchor', None)
                        p.pop('_pose_done', None)
                        continue
                # NEIGUNG lazy messen: sobald der Schwenk das Wort ins Bild
                # geschoben hat, uebernimmt es die GEMESSENE Bodenebene -
                # beim Ankern am Rand war die Flaeche noch nicht sichtbar.
                if (rigid and not p.get('_pose_done')
                        and p.get('flat_arr') is not None):
                    _ctr = H_rel @ np.array([p.get('cx', W / 2), p['cy'], 1.0])
                    _ctr /= _ctr[2]
                    if 0.15 * H < _ctr[1] < 0.85 * H:
                        _pose = ground_pose(depth_n, _ctr[0], _ctr[1],
                                            p['flat_arr'].shape[1] * 0.7,
                                            p['flat_arr'].shape[0] * 2.2, W, H)
                        if _pose is not None:
                            p['arr'] = rot_img(persp_warp(p['flat_arr'], yaw=0.0,
                                                          pitch=_pose[1]),
                                               _pose[0])
                        p['_pose_done'] = True
                e = smoothstep(dt / 0.75)
                if rigid:
                    # Keine Eigenbewegung: kein Einflug, keine Animation,
                    # kein Atmen. Nur schneller Fade ab dem Anker-Moment.
                    arr_t3, adx_g, dy_f, aop_g = p['arr'], 0.0, 0.0, 1.0
                else:
                    arr_t3, adx_g, dy_f, asc_g, aop_g = anim_apply(p, p['arr'], aud, dt)
                    dy_f -= (arr_t3.shape[0] - p['arr'].shape[0]) / 2
                g_op = g_opac
                # "Aus dem Wasser": Glas-Text steigt aus der Flaeche auf -
                # erst tief und verschwommen wie unter der Oberflaeche, dann klar
                if p.get('glass') and p.get('material', 'wasser') == 'wasser':
                    emerge = smoothstep(min(dt / 0.9, 1.0))
                    dy_e = (1 - emerge) * arr_t3.shape[0] * 0.55
                    bl_e = (1 - emerge) * 3.5
                    op_e = 0.35 + 0.65 * emerge
                else:
                    dy_e = 0.0 if rigid else (1 - e) * H * 0.03
                    bl_e, op_e = 0.0, 1.0
                dy_e += dy_f
                _tv = t - p.get('t_anchor', p.get('t0', p['start']))
                _fade = min(_tv / 0.12, 1) if rigid else min(dt / 0.4, 1)
                paste_tracked(comp, arr_t3, p.get('cx', W / 2) + adx_g, p['cy'],
                              H_rel, W, H,
                              dy_extra=dy_e,
                              opacity=_fade * g_out * g_op * op_e * aop_g,
                              refract=g_refract, ripple=g_ripple, grain=g_grain,
                              occ=occ_g, blur=cam_blur + bl_e)
                draw_small(p, g_out, 0.0, 0.0, x_sc, x_dv)
                continue
            if p.get('letters'):
                for li, (sl, off) in enumerate(p['letters']):
                    # v82: Hand-Keyframe-Streuung (siehe behind-Pfad)
                    dl = dt - li * 0.05 + 0.015 * hand_jitter(p['kw_i'] * 31 + li)
                    if dl < 0:
                        continue
                    e = ease_back(dl / (0.32 * (1 + 0.08 * hand_jitter(p['kw_i'] * 7 + li))))
                    if g_broll:
                        paste_scene(comp, sl, p.get('cx', W / 2) + sdx + off,
                                    p['cy'] + sdy + (1 - e) * H * 0.055,
                                    W, H, scale=0.9 + 0.1 * e,
                                    opacity=min(dl / 0.12, 1) * g_out * g_opac,
                                    refract=g_refract, ripple=g_ripple,
                                    occ=occ_g, blur=cam_blur)
                    else:
                        paste(comp, sl, p.get('cx', W / 2) + sdx + off,
                              p['cy'] + sdy + (1 - e) * H * 0.055 + x_dv * sl.shape[0],
                              W, H, scale=(0.9 + 0.1 * e) * x_sc,
                              opacity=min(dl / 0.12, 1) * g_out)
            else:
                e = smoothstep(dt / 0.75)
                live = 1.0 + 0.015 * min(dt / 2.5, 1.0)
                if g_broll:
                    if p.get('glass_frames'):
                        gf = p['glass_frames']
                        p['arr'] = gf[blender_engine.anim_loop_idx(dt, len(gf))]
                    if p.get('lying') and not p.get('glass'):
                        # GEMALT = starr, auch ohne Kamera-Track: kein Einflug,
                        # kein Atmen - nur schneller Fade ab dem Anker-Moment.
                        if (not p.get('_pose_done')
                                and p.get('flat_arr') is not None):
                            _pose = ground_pose(depth_n, p.get('cx', W / 2),
                                                p['cy'],
                                                p['flat_arr'].shape[1] * 0.7,
                                                p['flat_arr'].shape[0] * 2.2,
                                                W, H)
                            if _pose is not None:
                                p['arr'] = rot_img(
                                    persp_warp(p['flat_arr'], yaw=0.0,
                                               pitch=_pose[1]), _pose[0])
                            p['_pose_done'] = True
                        _tvs = t - p.get('t_anchor', p.get('t0', p['start']))
                        paste_scene(comp, p['arr'], p.get('cx', W / 2) + sdx,
                                    p['cy'] + sdy,
                                    W, H, scale=1.0,
                                    opacity=min(_tvs / 0.12, 1) * g_out * g_opac,
                                    refract=g_refract, ripple=g_ripple,
                                    grain=g_grain, occ=occ_g, blur=cam_blur)
                    else:
                        arr_s, adx_s, dy_s, asc_s, aop_s = anim_apply(p, p['arr'], aud, dt)
                        dy_s -= (arr_s.shape[0] - p['arr'].shape[0]) / 2
                        paste_scene(comp, arr_s, p.get('cx', W / 2) + sdx + adx_s,
                                    p['cy'] + sdy + dy_s + (1 - e) * H * 0.03,
                                    W, H, scale=(0.97 + 0.03 * e) * live * asc_s,
                                    opacity=min(dt / 0.4, 1) * g_out * aop_s * g_opac,
                                    refract=g_refract, ripple=g_ripple, grain=g_grain,
                                    occ=occ_g,
                                    blur=max(cam_blur, (1 - e) * 4.5 if not (p.get('scene_blend') or gp) else 0.0))
                else:
                    paste(comp, p['arr'], p.get('cx', W / 2) + sdx,
                          p['cy'] + sdy + (1 - e) * H * 0.03 + x_dv * p['arr'].shape[0],
                          W, H, scale=(0.97 + 0.03 * e) * live * x_sc,
                          opacity=smoothstep(dt / 0.35) * g_out, blur=(1 - e) * 4.5)
            if p.get('refl') is not None and cfg['effects'].get('reflection', True):
                r = p['refl']
                if occ_g is not None:
                    paste_scene(comp, r, p.get('cx', W / 2) + sdx + p['refl_dx'],
                                p['cy'] + sdy + p['refl_dy'] + r.shape[0] / 2 + 3,
                                W, H, opacity=min(max(dt - 0.2, 0.0) / 0.5, 1.0) * g_out,
                                refract=0.0, ripple=0.0, occ=occ_g, grain=0.0)
                else:
                    paste(comp, r, p.get('cx', W / 2) + sdx + p['refl_dx'],
                          p['cy'] + sdy + p['refl_dy'] + r.shape[0] / 2 + 3,
                          W, H, opacity=min(max(dt - 0.2, 0.0) / 0.5, 1.0) * g_out)
            draw_small(p, g_out, sdx, sdy, x_sc, x_dv)
        elif p['tpl'] == 'blurin' and dt >= 0:
            apply_count(p, dt)
            draw_small(p, g_out, 0.0, 0.0, x_sc, x_dv)  # blurin: small bleibt ruhig
        elif p['tpl'] == 'outline' and dt >= 0:
            apply_count(p, dt)
            e = ease_out(min(dt / 0.20, 1))
            fill_t = min(max((dt - 0.26) / 0.10, 0), 1)
            if fill_t < 1:
                paste(comp, p['o_arr'], p['cx'] + tdx,
                      p['cy'] + tdy + (1 - e) * H * 0.028, W, H,
                      scale=0.94 + 0.06 * e, opacity=min(dt / 0.08, 1) * (1 - fill_t) * g_out)
            if fill_t > 0:
                pop = 1.0 + 0.05 * math.sin(min(fill_t, 1) * math.pi)
                arr_o, adx, ady, asc, aop = anim_apply(p, p['f_arr'], aud, dt)
                ady -= (arr_o.shape[0] - p['f_arr'].shape[0]) / 2
                paste(comp, arr_o, p['cx'] + tdx + adx,
                      p['cy'] + tdy + ady + x_dv * p['f_arr'].shape[0], W, H,
                      scale=pop * asc * x_sc, opacity=fill_t * g_out * aop)
            draw_small(p, g_out, tdx, tdy, x_sc, x_dv)
        elif p['tpl'] == 'behind':
            draw_small(p, g_out, 0.0, 0.0, x_sc, x_dv)

    z, px, py, rd = camera_at(t, plans, words, cfg, W, H)
    if cam_state is not None:
        a = 0.32   # EMA: glaettet Knicke und Mikro-Zittern der Kamera
        cam_state[0] += a * (z - cam_state[0])
        cam_state[1] += a * (px - cam_state[1])
        cam_state[2] += a * (py - cam_state[2])
        cam_state[3] += a * (rd - cam_state[3])
        z, px, py, rd = cam_state[0], cam_state[1], cam_state[2], cam_state[3]
    if z > 1.0005 or abs(px) > 0.3 or abs(py) > 0.3 or abs(rd) > 0.05:
        M = cv2.getRotationMatrix2D((face_xy[0], face_xy[1]), rd, z)
        M[0, 2] -= px
        M[1, 2] -= py
        comp = cv2.warpAffine(comp, M, (W, H), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
    # Whip-Blur: bewegt sich die Kamera seitlich sehr schnell (px-Sprung zum
    # letzten Frame), wird der Frame horizontal verwischt. Ohne diesen Blur waere
    # ein Whip-Pan nur ein schnelles Rutschen - erst der Verwisch macht ihn zum
    # Whip. Nur bei echtem Tempo, damit ruhige Schwenke scharf bleiben.
    if cam_state is not None:
        pv = cam_state[4] if len(cam_state) > 4 else px
        vx = abs(px - pv)
        if len(cam_state) > 4:
            cam_state[4] = px
        if vx > W * 0.010:
            k = int(min(vx / (W * 0.010) * 4, 41))
            if k >= 3:
                if k % 2 == 0:
                    k += 1
                ker = np.zeros((k, k), np.float32)
                ker[k // 2, :] = 1.0 / k          # rein horizontaler Kernel
                comp = cv2.filter2D(comp, -1, ker)
    # ---------- v73: 4 neue Post-Effekte (Split-Screen macht Etappe 2) ----------
    _env = float(cfg['effects'].get('env_shadow', 0.0) or 0.0)
    if _env > 0.02:
        comp = apply_env_shadow(comp, frame, active, t, W, H, _env)
    _ring = float(cfg['effects'].get('counter_ring', 0.0) or 0.0)
    if _ring > 0.02:
        comp = apply_counter_ring(comp, active, t, W, H, _ring)
    # Trail ist ein TEXT-Effekt (versetzte Text-Kopien). Er darf NUR laufen,
    # wenn wirklich eine Caption auf dem Bild ist. Sonst erkennt der Diff
    # comp-vs-frame die durch Kamera-Zoom/-Schwenk/Grade verschobenen
    # Personen-Kanten als "Text" und dupliziert die Person -> sie wirkt doppelt,
    # gerade in Passagen OHNE Caption. Kein aktiver Text -> kein Trail.
    _trail = float(cfg['effects'].get('trail', 0.0) or 0.0)
    if _trail > 0.02 and active:
        comp = apply_duplicate_trail(comp, frame, _trail, alpha)
    _split = float(cfg['effects'].get('split_screen', 0.0) or 0.0)
    if _split > 0.02:
        comp = apply_split_screen(comp, frame, active, t, W, H, _split)
    return comp

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--out', default=None)
    ap.add_argument('--config', default=os.path.join(HERE, 'config.yaml'))
    ap.add_argument('--keywords', default=None, help='Kommagetrennte Zusatz-Keywords')
    ap.add_argument('--transcript', default=None, help='Vorhandenes Transkript-JSON nutzen')
    ap.add_argument('--duration', type=float, default=None, help='Nur die ersten N Sekunden rendern (Vorschau)')
    ap.add_argument('--preview', action='store_true',
                    help='Schnelle 540p-Vorschau: grober Encode, kein Master')
    ap.add_argument('--window', nargs=2, type=float, default=None,
                    metavar=('T0', 'T1'),
                    help='Nur dieses Zeitfenster rendern (Sekunden, Video-only)')
    ap.add_argument('--splice-into', default=None,
                    help='Fertiges Video, in das das Fenster-Segment eingesetzt wird')
    ap.add_argument('--transcribe-only', action='store_true',
                    help='Nur transkribieren und speichern, dann beenden')
    ap.add_argument('--plan-only', action='store_true',
                    help='Nur analysieren: Momente als JSON schreiben, nicht rendern')
    ap.add_argument('--watermark', action='store_true',
                    help='Dezentes DouchkoVE-Wasserzeichen einblenden (Free-Tier)')
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding='utf-8'))
    # v96y: gelernte Stil-Referenzen wirken DETERMINISTISCH auf die Config
    # (Chunk-Laenge, Highlight-Dichte, Hook, Wucht) - zusaetzlich zum Prompt.
    # So ist der Referenz-Einfluss sichtbar, egal wie GPT den Hinweis gewichtet.
    if not args.transcribe_only:
        _anker = _apply_reference_params(cfg)
        if _anker:
            print(_anker)
    global MOTION_BLUR, BEAT_SYNC, PERSON_SHADOW
    MOTION_BLUR = bool(cfg.get('effects', {}).get('motion_blur', True))
    BEAT_SYNC = float(cfg.get('effects', {}).get('beat_sync', 0.7))
    PERSON_SHADOW = float(cfg.get('effects', {}).get('person_shadow', 0.5))
    out_path = args.out or os.path.splitext(args.input)[0] + '_captions.mp4'
    if not args.transcribe_only:
        ensure_models()          # Transkript-Kontrolle braucht keine KI-Modelle

    src_w, src_h, fps, fps_str, src_dur = probe(args.input)
    n_frames = int(src_dur * fps)
    H = cfg['output'].get('height', 1080)
    if args.preview:
        H = 540
        cfg['output']['master'] = False
        cfg['output']['crf'] = 30
        cfg['output']['speed'] = 'schnell'
        print("VORSCHAU-MODUS: 540p, schneller Encode")
    W = int(round(src_w * H / src_h / 2) * 2)

    # v80f: Aspect-Ratio Auto-Detect. Der Renderer ist auf 9:16 optimiert
    # (Safe-Zone, v_zone, Textgroessen). Bei Landscape-Eingaben (>1.3) kippen
    # sicherheitshalber alle Portrait-Assumptions. Wir warnen laut und
    # deaktivieren safe_zone/portrait-Layout automatisch.
    _ar = src_w / max(src_h, 1)
    _mode = str(cfg.get('output', {}).get('orientation', 'auto')).lower()
    if _mode == 'auto':
        if _ar > 1.3:
            _mode = 'landscape'
        elif _ar > 0.85:
            _mode = 'square'
        else:
            _mode = 'portrait'
    if _mode != 'portrait':
        cfg['effects']['safe_zone'] = False
        print(f"Eingabe erkannt als {_mode.upper()} ({src_w}x{src_h}, "
              f"AR {_ar:.2f}). Portrait-Optimierungen deaktiviert.")
    print(f"Eingabe: {src_w}x{src_h} @ {fps:.3g}fps, {n_frames} Frames -> Ausgabe {W}x{H}")

    # --- Transkription
    # Transkript-Cache neben dem Video automatisch nutzen (kein API-Aufruf)
    if not args.transcript:
        auto_t = os.path.splitext(args.input)[0] + '_transcript2.json'
        if os.path.exists(auto_t):
            args.transcript = auto_t
    if args.transcript and os.path.exists(args.transcript):
        words = json.load(open(args.transcript, encoding='utf-8'))
        print(f"Transkript geladen: {len(words)} Woerter")
    else:
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, 'audio.m4a')
            # Whisper-API-Limit: 25 MB. Bitrate so waehlen, dass auch sehr
            # lange Videos (60min+) unter der Grenze bleiben.
            br_kbps = max(24, min(64, int(24 * 8192 / max(src_dur, 1.0))))
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.input,
                            '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'aac',
                            '-b:a', f'{br_kbps}k', wav], check=True)
            # v80e: Sicherheitsnetz. Falls Duration-Schaetzung daneben lag und
            # die Datei > 25 MB ist, kompressiere nochmal mit halber Bitrate.
            _sz_mb = os.path.getsize(wav) / 1e6 if os.path.exists(wav) else 0
            if _sz_mb > 24.5:
                br_kbps = max(16, br_kbps // 2)
                print(f"Audio {_sz_mb:.1f} MB > Whisper-Limit, "
                      f"neu enkodiert mit {br_kbps} kbps")
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.input,
                                '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'aac',
                                '-b:a', f'{br_kbps}k', wav], check=True)
            words = transcribe(wav, cfg.get('language', 'de'), cfg)
        tpath = os.path.splitext(args.input)[0] + '_transcript2.json'
        json.dump(words, open(tpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"{len(words)} Woerter, Transkript gespeichert: {tpath}")

    if args.transcribe_only:
        print('Transkript bereit - Kontrolle kann starten.')
        sys.exit(0)

    # --- Wort-Timing am echten Audio nachjustieren
    voice_wav = os.path.join(tempfile.gettempdir(), 'dve_voice.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.input, '-vn',
                    '-ac', '1', '-ar', '44100', voice_wav], check=False)
    if os.path.exists(voice_wav):
        words, avg_shift = refine_word_times(words, voice_wav)
        print(f"Wort-Timing nachjustiert (mittlere Korrektur {avg_shift:.0f} ms)")
    else:
        voice_wav = None

    # --- Tracking + Plaene
    speed = str(cfg['output'].get('speed', 'standard')).lower()
    det_step, md_mult, x264_preset = {
        'schnell':  (3, 0.7, 'veryfast'),
        'standard': (2, 1.0, cfg['output'].get('preset', 'medium')),
        'maximal':  (1, 1.2, 'slow')}.get(speed, (2, 1.0, 'medium'))
    face, has_face, face_w, cut_frames, faces_seq, multi_person = track_faces(
        args.input, W, H, fps_str, det_step)
    # v96b: Automatischer Modus-Schalter. Kaum Gesicht = Erzaehler/Voiceover ->
    # zentrierte editoriale Captions; ein Gesicht = Talking-Head; mehrere =
    # Gespraech. Ismet muss nichts umstellen, der Render erkennt es selbst.
    face_frac = float(has_face.mean()) if len(has_face) else 0.0
    video_mode = _video_mode(face_frac, multi_person)
    print(f"Modus automatisch: {video_mode} "
          f"(Gesicht in {face_frac*100:.0f}% der Frames"
          + (", mehrere Personen" if multi_person else "") + ")")
    k2 = 41
    kern2 = np.ones(k2) / k2
    face_stable = np.stack([np.convolve(np.pad(face[:, j], k2 // 2, mode='edge'),
                                        kern2, 'valid')[:len(face)] for j in range(2)], axis=1)
    fps_i = fps
    def face_ok(start, end):
        a, b = int(start * fps_i), min(int(end * fps_i) + 1, len(has_face))
        if b <= a: return True
        return has_face[a:b].mean() > 0.62
    def face_pos(start, end):
        a, b = int(start * fps_i), min(int(end * fps_i) + 1, len(face))
        if b <= a: a, b = max(len(face) - 2, 0), len(face)
        return (float(face[a:b, 0].mean()), float(face[a:b, 1].mean()),
                float(face_w[a:b].mean()))
    def faces_at(start, end):
        """v96: ALLE Gesichter (x, w) im Zeitfenster - fuer die Multi-Face-Safe-
        Zone. Nimmt aus dem Fenster den Frame mit den MEISTEN Gesichtern (so
        wird keine kurz verdeckte zweite Person uebersehen) und mittelt je Spur
        grob ueber die x-Position. Leere Liste = keine Gesichter."""
        a, b = int(start * fps_i), min(int(end * fps_i) + 1, len(faces_seq))
        if b <= a:
            return []
        best = []
        for i in range(a, b):
            if len(faces_seq[i]) > len(best):
                best = faces_seq[i]
        return [(fx, fw) for (fx, fy, fw) in best]
    S = Sprites(cfg, W, H)
    n_est = (max(int(args.duration * fps), 1) if args.duration else n_frames) + 8
    if voice_wav and os.path.exists(voice_wav) and cfg['effects'].get('anim', True):
        aud_rms, aud_bass, aud_onset = audio_envelopes(voice_wav, n_est, fps)
        # Musik-Beat: eigener Onset aus Sub-Bass + Auto-Korrelation. Wird mit
        # dem Sprech-Onset kombiniert (max), damit Text sowohl auf Stimme als
        # auch auf Musik reagiert. Gewicht = effects.music_beat * conf; ohne
        # Musik im Clip ist conf klein -> reine Talking-Heads werden nicht
        # angefasst.
        _mb_w = float(cfg['effects'].get('music_beat', 0.6) or 0.0)
        if _mb_w > 0.01:
            beat_env, bpm, conf = music_beats(voice_wav, n_est, fps)
            if conf > 0.10:
                gain = _mb_w * conf
                aud_onset = np.maximum(aud_onset, beat_env * gain).astype(np.float32)
                print(f"Musik-Beat: ~{bpm} BPM (Confidence {conf:.2f}, "
                      f"Gewicht {gain:.2f})")
            else:
                print("Musik-Beat: kein klares Tempo (Confidence zu niedrig) - "
                      "nur Sprech-Onset")
    else:
        aud_rms = aud_bass = aud_onset = np.zeros(n_est, np.float32)
    fx_map = None
    if cfg['keywords'].get('ai', True):
        regie_path = os.path.splitext(args.input)[0] + '_regie3.json'
        if os.path.exists(regie_path):
            # v96x: Regie-Cache ist nur gueltig, wenn die Stil-Referenzen seit
            # seinem Entstehen UNVERAENDERT sind. Sonst (User hat inzwischen
            # einen Stil gelernt/geloescht) wird der Cache verworfen und die
            # KI plant neu MIT den aktuellen Referenzen - vorher wirkte ein
            # frisch gelernter Stil auf Analyze-/Re-Render-Jobs nie.
            _rtxt = open(regie_path, encoding='utf-8').read()
            try:
                _rfp = json.loads(_rtxt).get('ref_fp')
            except Exception:
                _rfp = None
            if _rfp == _ref_fingerprint():
                fx_map = parse_regie(_rtxt, words, cfg.get('language', 'de'))
            else:
                print("Stil-Referenzen geaendert - alte Regie verworfen, KI plant neu")
        if fx_map is None:
            print("KI-Regie analysiert das Transkript...")
            fx_map = ai_direct(words, cfg.get('language', 'de'),
                               cfg['keywords'].get('ai_model', 'gpt-4o'),
                               voice_wav=voice_wav,
                               validate=cfg['keywords'].get('ai_validate', True))
            if fx_map:
                # v95c: Gesichts-Breitenanteil pro Moment (0..1) - wie sehr
                # fuellt die Person das Bild. Speist die 'behind'-Entscheidung
                # (KI + Backstop): hinter einem bildfuellenden Gesicht sieht man
                # den Text nicht.
                face_cover = {i: min(max(face_pos(words[i].get('start', 0),
                                                  words[i].get('end', 0))[2] / max(W, 1),
                                         0.0), 1.0)
                              for i in list(fx_map)}
            if fx_map and cfg['keywords'].get('ai_vision', True):
                fx_map = ai_scene_direct(words, fx_map, args.input,
                                         cfg['keywords'].get('ai_model', 'gpt-4o'),
                                         min_power=int(cfg['keywords'].get('vision_min_power', 2)),
                                         face_cover=face_cover)
            elif fx_map:
                # Vision aus, aber der Backstop soll trotzdem greifen.
                fx_map = _behind_cover_backstop(fx_map, face_cover)
            if fx_map:
                json.dump({'ref_fp': _ref_fingerprint(),   # v96x: Cache-Gueltigkeit
                           'keywords': [{'i': i, 'fx': v['fx'], 'power': v['power'],
                                         'n': v.get('n', 1),
                                         **({'anim': v['anim']} if v.get('anim') else {}),
                                         **({'szene': v['szene']} if v.get('szene') else {}),
                                         **({'lage': v['lage']} if v.get('lage') else {})}
                                        for i, v in sorted(fx_map.items())]},
                          open(regie_path, 'w', encoding='utf-8'))
    # v99 Selbstbezug-Backstop: "The captions are behind me" besteht komplett
    # aus Sperrlisten-Woertern - die KI kann dort oft kein Keyword setzen, und
    # ohne API-Key gibt es gar keine Regie. Der deterministische Backstop
    # erzeugt den Moment dann selbst (gleiches Verhalten in KI-, Cache- und
    # Heuristik-Pfad). _had_regie merkt sich, ob die KEYWORD-Wahl von der KI
    # kam - nur dann bleibt die Auto-Heuristik aus.
    _had_regie = bool(fx_map)
    fx_map = _self_ref_intent(fx_map, words)
    if fx_map:
        kw = set(fx_map)
        if _had_regie:
            manual = detect_keywords(words, {**cfg, 'keywords': {**cfg['keywords'], 'auto': False}},
                                     args.keywords)
            kw |= manual
        else:
            # Nur Selbstbezug-Momente, keine KI-Wahl: volle Heuristik bleibt an.
            kw |= detect_keywords(words, cfg, args.keywords)
        exclude = {k.lower() for k in (cfg['keywords'].get('exclude') or [])}
        kw = {i for i in kw if clean(words[i]['word']).lower() not in exclude}
        print(f"KI-Regie: {len(kw)} Keywords gewaehlt")
    else:
        kw = detect_keywords(words, cfg, args.keywords)

    # v80f: Chapter-Detection aus Sprech-Pausen. Lange Videos brauchen
    # Struktur - eine >1.2s-Pause markiert idR einen Themen- oder Kapitel-
    # Wechsel. Wenn dort noch kein Highlight sitzt, setzen wir einen dezenten
    # blurin-Moment auf das erste Substanz-Wort nach der Pause. Nur bei
    # Videos >= 60s, sonst waere jedes Atmen ein Kapitel.
    if cfg.get('effects', {}).get('chapters', True) and words and \
            words[-1].get('end', 0) - words[0].get('start', 0) >= 60:
        n_chap = 0
        for i in range(1, len(words)):
            gap = words[i].get('start', 0) - words[i - 1].get('end', 0)
            if gap < 1.2:
                continue
            # Erstes Substanz-Wort nach der Pause finden
            for j in range(i, min(i + 6, len(words))):
                t = clean(words[j]['word']).lower()
                if not t or t in STOPWORDS:
                    continue
                # Nur wenn dort und drumherum noch kein Highlight sitzt
                if any(abs(j - k) <= 3 for k in kw):
                    break
                kw.add(j)
                fx_map = fx_map or {}
                if j not in fx_map:
                    fx_map[j] = {'fx': 'blurin', 'power': 1, 'n': 1}
                n_chap += 1
                break
        if n_chap:
            print(f"Kapitel-Struktur: {n_chap} Themenwechsel markiert")

    print("Keywords:", [clean(words[i]['word']) for i in sorted(kw)])

    # --- Moment-Editor: Analyse exportieren / Overrides anwenden
    # IMMER schreiben (nicht nur bei --plan-only), damit die Web-UI nach
    # dem Voll-Render einen Momente-Editor fuer Re-Rendering oeffnen kann.
    mom_path = os.path.splitext(args.input)[0] + '_momente.json'
    # v80e: Thumb-Ordner - pro Moment ein 320x180 JPEG. Die Web-UI zeigt sie
    # als Preview-Hintergrund, damit man beim Editieren sieht was zum Zeitpunkt
    # wirklich im Bild ist.
    thumb_dir = os.path.splitext(args.input)[0] + '_thumbs'
    try:
        os.makedirs(thumb_dir, exist_ok=True)
    except Exception:
        thumb_dir = None
    _cut_ok = [None]        # RVM-Session fuer Personen-Freistellung (lazy)
    prev = {}
    if os.path.exists(mom_path):
        try:
            prev = {m['i']: m for m in json.load(open(mom_path, encoding='utf-8'))}
        except Exception:
            prev = {}
    _mom_export = []
    for i in sorted(kw):
        info = (fx_map or {}).get(i, {}) if isinstance((fx_map or {}).get(i), dict) else {}
        n = int(info.get('n', 1))
        txt = ' '.join(clean(words[j]['word'])
                       for j in range(i, min(i + n, len(words))))
        # Wenn KI keine Animation vorgibt, spiegele die Auto-Wahl aus
        # build_plans (anim_for) hier vor - sonst zeigt der Momente-Editor
        # "keine", obwohl das Video mit Animation gerendert wird.
        _anim = info.get('anim') or ''
        if not _anim and cfg.get('effects', {}).get('anim', True):
            _anim = anim_for(txt, ' '.join(
                clean(words[j]['word'])
                for j in range(max(i - 4, 0),
                               min(i + 8, len(words))))) or ''
        thumb_rel = ''
        if thumb_dir:
            thumb_rel = f'{i:06d}.jpg'
            thumb_path = os.path.join(thumb_dir, thumb_rel)
            if not os.path.exists(thumb_path):
                _t = max(0.0, float(words[i].get('start', 0)) + 0.15)
                try:
                    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{_t:.2f}',
                                    '-i', args.input, '-frames:v', '1',
                                    '-vf', 'scale=320:-2', '-q:v', '5', thumb_path],
                                   check=False, timeout=15)
                except Exception:
                    pass
                if not os.path.exists(thumb_path):
                    thumb_rel = ''
        # v96h: Personen-Cutout fuer die Vorschau, damit 'behind' im Editor
        # wirklich hinter der Person sitzt. Nur wenn ein Thumb da ist.
        cut_rel = ''
        if thumb_dir and thumb_rel:
            _cut = f'{i:06d}_cut.png'
            _cutp = os.path.join(thumb_dir, _cut)
            if os.path.exists(_cutp) or _person_cutout_png(thumb_path, _cutp):
                cut_rel = _cut
        _mom_export.append({'i': i, 'text': txt, 'zeit': round(words[i]['start'], 2),
                            'fx': info.get('fx', 'behind'),
                            'power': int(info.get('power', 2)), 'n': n,
                            'anim': _anim, 'aktiv': True,
                            'szene': info.get('szene') or '',
                            'lage': info.get('lage') or '',
                            'emoji': info.get('emoji') or '',
                            'thumb': thumb_rel, 'cut': cut_rel})
        if i in prev:                       # fruehere Korrekturen behalten
            for k in ('aktiv', 'fx', 'power', 'anim', 'text', 'szene', 'lage', 'emoji'):
                if k in prev[i]:
                    _mom_export[-1][k] = prev[i][k]
    json.dump(_mom_export, open(mom_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    if args.plan_only:
        print(f"Momente exportiert: {mom_path}")
        sys.exit(0)
    if os.path.exists(mom_path):
        try:
            edits = {m['i']: m for m in json.load(open(mom_path, encoding='utf-8'))}
            kw = {i for i in kw if edits.get(i, {}).get('aktiv', True)}
            fx_map = fx_map or {}
            for i, m in edits.items():
                if i in kw:
                    e = fx_map.get(i) if isinstance(fx_map.get(i), dict) else {}
                    fx_map[i] = {'fx': m.get('fx', e.get('fx', 'behind')),
                                 'power': int(m.get('power', e.get('power', 2))),
                                 'n': int(m.get('n', e.get('n', 1)))}
                    for k_v in ('szene', 'lage'):
                        if isinstance(e, dict) and e.get(k_v):
                            fx_map[i][k_v] = e[k_v]     # Vision-Regie ueberlebt Edits
                    if str(m.get('szene', '')).lower() in ('wasser', 'boden', 'wand',
                                                           'himmel', 'person', 'unklar'):
                        fx_map[i]['szene'] = str(m['szene']).lower()
                    if str(m.get('lage', '')).lower() in ('liegend', 'stehend', 'frei'):
                        fx_map[i]['lage'] = str(m['lage']).lower()
                    if m.get('anim'):
                        fx_map[i]['anim'] = m['anim']
                    if m.get('text'):
                        fx_map[i]['txt'] = m['text']
                    if m.get('emoji'):
                        fx_map[i]['emoji'] = m['emoji']
            print(f"Moment-Editor: {len(kw)} aktive Momente uebernommen")
        except Exception as e:
            print(f"Momente-Datei ignoriert ({type(e).__name__})")
    palette_at = None
    # Farbwelt: 'auto' = adaptiv aus der Szene. 'schwarz'/'weiss' = feste
    # High-End-Palette; die Szenen-Toene werden dann bewusst NICHT aufgegriffen,
    # sonst waere die Farbwahl wirkungslos.
    cut_times = [c / float(fps_i) for c in cut_frames] if fps_i else []
    c_style = str(cfg.get('colors', {}).get('style', 'auto')).lower()
    if c_style == 'schwarz':
        S.set_base_colors((20, 20, 22), (58, 58, 64))
        print("Farbwelt: Elegantes Schwarz (Tiefschwarz + Graphit-Akzent)")
    elif c_style == 'weiss':
        S.set_base_colors((250, 249, 246), (208, 204, 196))
        print("Farbwelt: Elegantes Weiss (Softweiss + warmer Grau-Akzent)")
    elif cfg.get('colors', {}).get('adaptive', True):
        palette_at = scene_palette_sampler(args.input, cut_times)
        print("Adaptive Farben: Captions greifen die Szenen-Toene auf (pro Shot)")
    # v96b: Erzaehler-/Voiceover-Modus. Kaum Gesicht im Bild -> Captions NICHT
    # an einer (kaum vorhandenen) Person ausrichten, sondern zentriert-editorial
    # setzen (face_pos/faces_at = None laesst build_plans das freie, mittige
    # Layout waehlen). 'behind' ergibt ohne Person keinen Sinn -> auf sichtbares
    # 'outline' umlegen.
    # v97f: KI-Flow - GPT waehlt pro Filler-Chunk das Anker-/Akzent-Wort
    # (inhaltlich, wie ein Editor) statt der Laengen-Heuristik. EIN Call pro
    # Video, gecacht neben dem Input (_flow3.json). Fallback: Heuristik.
    flow_map = None
    if cfg['effects'].get('caption_flow', True) and cfg['keywords'].get('ai', True):
        _fgroups = list(build_groups(words, cfg['effects'].get('words_per_group', 3),
                                     min_hold=float(cfg['effects'].get('chunk_hold_min', 0.65)),
                                     hard_max=int(cfg['effects'].get('words_per_group_max', 5))))
        flow_path = os.path.splitext(args.input)[0] + '_flow3.json'
        if os.path.exists(flow_path):
            try:
                _raw = json.load(open(flow_path, encoding='utf-8'))
                flow_map = _parse_flow_sel(_raw, _fgroups, words)
            except Exception:
                flow_map = None
        if flow_map is None:
            _sel = ai_flow_direct(words, _fgroups, cfg.get('language', 'de'),
                                  cfg['keywords'].get('ai_model', 'gpt-4o'))
            if _sel:
                flow_map = _sel
                try:
                    json.dump({'chunks': [{'g': k, 'kw': v['kw'],
                                           'accent': v.get('accent')}
                                          for k, v in sorted(flow_map.items())]},
                              open(flow_path, 'w', encoding='utf-8'))
                except OSError:
                    pass
        if flow_map:
            print(f"KI-Flow: {len(flow_map)} Anker gewaehlt")

    if video_mode == 'narrator':
        if fx_map:
            for _v in fx_map.values():
                if _v.get('fx') == 'behind':
                    _v['fx'] = 'outline'
        plans = build_plans(words, kw, cfg, S, W, H, face_ok, fx_map,
                            face_pos=None, palette_at=palette_at,
                            cut_times=cut_times, faces_at=None,
                            flow_map=flow_map)
    else:
        plans = build_plans(words, kw, cfg, S, W, H, face_ok, fx_map, face_pos,
                            palette_at, cut_times=cut_times, faces_at=faces_at,
                            flow_map=flow_map)

    # --- Blender-Wasser-Text: stehende Szenen-Texte werden echtes 3D-Wasser-Glas.
    # Ein Render pro Moment (gecacht); Bewegung/Okklusion macht weiter die Pipeline.
    if cfg['effects'].get('blender_water', True):
        bl_exe = blender_engine.find_blender(cfg.get('render', {}).get('blender_path'))
        bl_targets = [p for p in plans if p['tpl'] == 'ground' and p.get('broll')
                      and not p.get('scene_blend') and not p.get('count')
                      and (not args.window or (p['start'] < args.window[1]
                                               and p['end'] > args.window[0]))]
        if bl_targets and not bl_exe:
            print("Blender nicht gefunden - stehende Szenen-Texte nutzen den 2D-Look."
                  " (Blender installieren oder render.blender_path in config.yaml setzen)")
        elif bl_targets:
            print(f"Blender-Wasser-Text: {len(bl_targets)} Moment(e) ({bl_exe})")
            import tempfile as _tf
            for p in bl_targets:
                bg_png = os.path.join(_tf.gettempdir(),
                                      f"douchko_bg_{int(p['start']*1000)}.png")
                subprocess.run(['ffmpeg', '-y', '-v', 'error',
                                '-ss', str(max(p['start'] + 0.15, 0.0)),
                                '-i', args.input, '-frames:v', '1', bg_png],
                               capture_output=True, timeout=30)
                tint = (0.55, 0.9, 0.86)
                if palette_at:
                    pal = palette_at(p['start'] + 0.2, 'unten')
                    if pal:
                        a = pal[1]
                        tint = tuple(min(c / 255.0 * 1.15 + 0.15, 1.0) for c in a)
                # Material folgt der Vision-Regie: Wasser -> fluessiges Glas,
                # Boden/Wand -> massives, mattes 3D (Glas auf Asphalt wirkt falsch)
                material = ('wasser' if p.get('szene') in (None, '', 'unklar', 'wasser')
                            else 'solid')
                n_anim = max(int(cfg['effects'].get('blender_anim_frames', 12)), 1)
                if material != 'wasser':
                    n_anim = 1                     # Wellen laufen nur auf Wasser
                spr = blender_engine.render_water_text(
                    p.get('txt_str') or p.get('kw_txt', ''), bg_png, S.f_serif,
                    tint=tint, blender_path=bl_exe, material=material,
                    samples=int(cfg['effects'].get('blender_samples', 128)),
                    width=int(cfg['effects'].get('blender_width', 1600)),
                    frames=n_anim)
                if spr is None:
                    continue
                seq = spr if isinstance(spr, list) else [spr]
                # auf Zielbreite des bisherigen Sprites skalieren
                tw = p['arr'].shape[1]
                sc = tw / seq[0].shape[1]
                seq = [cv2.resize(f, None, fx=sc, fy=sc,
                                  interpolation=cv2.INTER_AREA) for f in seq]
                p['arr'] = seq[0]
                if len(seq) > 1:
                    p['glass_frames'] = seq        # lebendiges Wasser (Loop)
                p['glass'] = True
                p['material'] = material
                p.pop('letters', None)
                if cfg['effects'].get('reflection', True):
                    r, rdy, rdx = make_reflection(p['arr'])
                    if r is not None:
                        p['refl'], p['refl_dy'], p['refl_dx'] = r, rdy, rdx
    n_kw = sum(1 for p in plans if 'kw_i' in p)
    n_broll = sum(1 for p in plans if p.get('broll'))
    print(f"Kompositionen: {len(plans)} ({n_kw} Keyword-Momente, {n_broll} ueber B-Roll)")

    # --- Matting-Session: probiert CUDA, dann DirectML, dann CPU
    import onnxruntime as ort
    try:
        ort.preload_dlls()   # laedt pip-installierte NVIDIA-Bibliotheken (Windows)
    except Exception:
        pass
    dsr = np.array([0.25], dtype=np.float32)   # nur fuer den Warmup-Test
    available = set(ort.get_available_providers())
    chain = [p for p in ('CUDAExecutionProvider', 'DmlExecutionProvider',
                         'CPUExecutionProvider') if p in available]
    sess = None
    model_path = os.path.join(HERE, 'models/rvm.onnx')
    for prov in chain:
        try:
            cand = ort.InferenceSession(model_path, providers=[prov])
            if cand.get_providers()[0] != prov:
                continue
            z = [np.zeros([1, 1, 1, 1], dtype=np.float32)] * 4
            test = np.zeros([1, 3, H, W], dtype=np.float32)
            cand.run(None, {'src': test, 'r1i': z[0], 'r2i': z[1],
                            'r3i': z[2], 'r4i': z[3], 'downsample_ratio': dsr})
            sess = cand
            break
        except Exception:
            print(f"{prov} nicht nutzbar, probiere naechsten...")
    if sess is None:
        sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    rec = [np.zeros([1, 1, 1, 1], dtype=np.float32)] * 4
    active_prov = sess.get_providers()[0]
    # MASKENQUALITAET. Das Netz rechnet die Maske intern VERKLEINERT - genau daran
    # haengt, ob Haare, Schultern und Finger sauber freigestellt sind oder ob die
    # Kante matscht. 0.25 (bisher) ist schnell, aber grob. Hoehere Stufen kosten
    # Rechenzeit, bringen aber echte Kanten.
    QUAL = {'standard': (1.0, 1.0), 'hoch': (1.6, 1.3), 'maximum': (2.2, 1.6)}
    q_name = str(cfg.get('matting_quality', 'standard')).lower()
    q_mult, q_refine = QUAL.get(q_name, QUAL['standard'])
    md = cfg.get('matting_downsample', 'auto')
    if md in (None, 'auto'):
        base = 0.375 if active_prov != 'CPUExecutionProvider' else 0.25
        md_val = min(max(base * min(1080.0 / H, 1.0) * md_mult * q_mult,
                         0.125), 0.8)
    else:
        md_val = float(md)
    dsr = np.array([md_val], dtype=np.float32)
    refine_str = float(cfg['effects'].get('refine', 1.0)) * q_refine
    print(f"Matting: {active_prov}, Qualitaet '{q_name}' "
          f"(Detailstufe {md_val:.3g}, Kantenschaerfe {refine_str:.2g})")

    # --- SFX-Spur. Es gibt NUR echte Sounds aus dem Sound-Pack (sfx/pack/).
    # Synthetische Ersatztoene wurden ersatzlos entfernt - ein billiger Sound ist
    # schlechter als gar keiner. Ohne Pack laeuft das Video ohne Sound-Effekte.
    sfx_path = None
    if cfg['effects'].get('sfx', True) and not args.window:
        try:
            import sfx_engine
            folder = sfx_engine.pack_folder(HERE)
            if not sfx_engine.load_bank(folder):
                print("HINWEIS: Kein Sound-Pack -> das Video bekommt keine "
                      "Sound-Effekte.")
                print("  Laden: GUI -> Profi -> Sound-Pack -> 'Echte Sounds laden'")
            else:
                sfx_path = os.path.join(tempfile.gettempdir(), 'dve_sfx_track.wav')
                powers = {i: v.get('power', 2) for i, v in (fx_map or {}).items()
                          if isinstance(v, dict)}
                dur_total = (args.duration if args.duration else n_frames / fps)
                print("SFX werden intelligent gesetzt (Onset-Analyse)...")
                n_sfx = sfx_engine.build_sfx_track(plans, words, dur_total, folder,
                                                   sfx_path, voice_wav=voice_wav,
                                                   powers=powers)
                print(f"SFX: {n_sfx} Sound-Momente gesetzt")
                if not n_sfx:
                    sfx_path = None
        except Exception as e:
            print(f"SFX uebersprungen ({type(e).__name__})")
            sfx_path = None

    # --- Wasserzeichen-Sprite (v80y, Free-Tier): einmal gebaut, pro Frame
    # alpha-geblendet. Dezent: 38% Deckkraft, unten rechts.
    wm = None
    if args.watermark:
        _wm_f = ImageFont.truetype(os.path.join(HERE, 'fonts', 'poppins_b.ttf'),
                                   max(int(H * 0.030), 22))
        _d = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
        _bb = _d.textbbox((0, 0), 'DouchkoVE', font=_wm_f)
        _tw, _th = _bb[2], _bb[3]
        # v88b: Logo-Monogramm links neben den Schriftzug. Weiss, gleiche
        # dezente Deckkraft wie der Text (~38%).
        _logo_arr = None
        _lp = os.path.join(HERE, 'web', 'logo_white.png')
        if os.path.exists(_lp):
            try:
                _lh = int(_th * 1.15)
                _lg = Image.open(_lp).convert('RGBA')
                _lg = _lg.resize((max(int(_lg.width * _lh / _lg.height), 1), _lh),
                                 Image.LANCZOS)
                _la = np.array(_lg).astype(np.float32)
                _la[..., 3] *= 97 / 255.0            # gleiche Transluzenz wie Text
                _logo_arr = _la.astype(np.uint8)
            except Exception:
                _logo_arr = None
        _lw = (_logo_arr.shape[1] + int(H * 0.010)) if _logo_arr is not None else 0
        _wm_img = Image.new('RGBA', (_lw + _tw + 12, max(_th, _logo_arr.shape[0]
                            if _logo_arr is not None else _th) + 14), (0, 0, 0, 0))
        _cy = _wm_img.height // 2
        if _logo_arr is not None:
            _li = Image.fromarray(_logo_arr)
            _wm_img.alpha_composite(_li, (6, _cy - _li.height // 2))
        ImageDraw.Draw(_wm_img).text((_lw + 6, _cy - _th // 2 - _bb[1]), 'DouchkoVE',
                                     font=_wm_f, fill=(255, 255, 255, 97),
                                     stroke_width=2, stroke_fill=(0, 0, 0, 60))
        _wm_arr = np.array(_wm_img)
        _wx = W - _wm_arr.shape[1] - int(W * 0.03)
        _wy = H - _wm_arr.shape[0] - int(H * 0.025)
        wm = (_wm_arr, _wx, _wy)
        print("Wasserzeichen: aktiv (Free-Tier, mit Logo)")

    # --- Encoder (v80p): ZWEI Stufen statt einer Pipe-Mux-Kombi.
    # Stufe 1: NUR Video aus der Pipe in eine Temp-Datei. Kein zweiter Input,
    #   kein -shortest. Hintergrund: ffmpeg hat einen Interleave-Mechanismus
    #   (max_interleave_delta, 10s), der bei langsamer Pipe-Zufuhr (CPU-Render
    #   ist langsamer als Echtzeit) die komplett eingelesene Audio-Spur
    #   vorzeitig ausschreibt - danach beendet -shortest den Prozess REGULAER
    #   mitten im Render. Symptom: BrokenPipeError ohne ffmpeg-Fehlertext.
    # Stufe 2 (nach dem Render): Audio/SFX per Stream-Copy dazu muxen -
    #   alle Inputs sind dann Dateien, dauert nur Sekunden, kein Pipe-Risiko.
    if cfg['output'].get('master', False):
        if not out_path.lower().endswith('.mov'):
            out_path = os.path.splitext(out_path)[0] + '.mov'
        vcodec = ['-c:v', 'prores_ks', '-profile:v', '3', '-pix_fmt', 'yuv422p10le']
        acodec = ['-c:a', 'pcm_s16le']
        video_tmp = os.path.splitext(out_path)[0] + '.videoonly.mov'
        print("Ausgabe: ProRes-Master (.mov) fuer Premiere")
    else:
        vcodec = ['-c:v', 'libx264', '-preset', x264_preset,
                  '-crf', str(cfg['output'].get('crf', 18)), '-pix_fmt', 'yuv420p']
        acodec = ['-c:a', 'aac']
        video_tmp = os.path.splitext(out_path)[0] + '.videoonly.mp4'
    vol = float(cfg['effects'].get('sfx_volume', 0.35))
    has_audio = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries',
         'stream=codec_type', '-of', 'csv=p=0', args.input],
        capture_output=True, text=True).stdout.strip() != ''
    if args.window:
        # Fenster-Render: reines Video-Segment direkt ans Ziel - die Tonspur
        # des fertigen Videos bleibt beim Einsetzen unveraendert
        video_tmp = None
        cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
               '-s', f'{W}x{H}', '-r', fps_str, '-i', 'pipe:0',
               '-c:v', 'libx264', '-preset', x264_preset,
               '-crf', str(cfg['output'].get('crf', 18)), '-pix_fmt', 'yuv420p',
               out_path]
    else:
        cmd = ['ffmpeg', '-y', '-v', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
               '-r', fps_str, '-i', 'pipe:0'] + vcodec + [video_tmp]
    # stderr capturen, damit wir bei BrokenPipeError die echte Ursache sehen
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # Matting nur dort rechnen, wo es gebraucht wird (behind/blurin-Momente)
    total_est = (max(int(args.duration * fps), 1) if args.duration else n_frames) + 8
    need_alpha = np.zeros(total_est, dtype=bool)
    for p in plans:
        # v91: ground-B-Roll braucht die Person-Matte, damit liegender Text
        # auf klarem Boden verankert wird UND die Person davor laeuft
        # (Text liegt hinter ihr auf der Strasse, nicht auf ihrem Pulli).
        if p['tpl'] in ('behind', 'blurin') or (p['tpl'] == 'ground'
                and (p.get('scene_ground') or p.get('broll'))):
            a = max(int((p['start'] - 0.2) * fps), 0)
            b = min(int((p['end'] + 0.6) * fps) + 1, total_est)
            need_alpha[a:b] = True
    print(f"Matting-Fenster: {int(need_alpha.sum())} von ~{total_est} Frames")

    # Tiefen-Fenster: Okklusion nur, wo Szenen-Texte (B-Roll ground) aktiv sind
    need_depth = np.zeros(total_est, dtype=bool)
    dsess = None
    if cfg['effects'].get('occlusion', True):
        for p in plans:
            if p['tpl'] == 'ground' and (p.get('scene_ground') or p.get('broll')):
                a = max(int((p['start'] - 0.2) * fps), 0)
                b = min(int((p['end'] + 0.6) * fps) + 1, total_est)
                need_depth[a:b] = True
        if need_depth.any():
            depth_path = os.path.join(HERE, 'models/depth.onnx')
            if os.path.exists(depth_path):
                for prov in chain + ['CPUExecutionProvider']:
                    try:
                        dsess = ort.InferenceSession(depth_path, providers=[prov])
                        break
                    except Exception:
                        continue
                print(f"Tiefen-Okklusion: {int(need_depth.sum())} Frames "
                      f"({dsess.get_providers()[0] if dsess else 'kein Modell'})")
            else:
                print("Tiefen-Okklusion uebersprungen (models/depth.onnx fehlt - setup.bat laedt es)")
    # Tracking-Fenster (planarer Kamera-Track) = Szenen-Text-Fenster
    need_track = np.zeros(total_est, dtype=bool)
    if cfg['effects'].get('track3d', True):
        for p in plans:
            if p['tpl'] == 'ground' and (p.get('scene_ground') or p.get('broll')):
                a = max(int((p['start'] - 0.35) * fps), 0)
                b = min(int((p['end'] + 0.6) * fps) + 1, total_est)
                need_track[a:b] = True
        if need_track.any():
            print(f"Kamera-Track (planar): {int(need_track.sum())} Frames")
    if W >= H:
        d_w = 252; d_h = max(int(round(H / W * 252 / 14)) * 14, 56)
    else:
        d_h = 252; d_w = max(int(round(W / H * 252 / 14)) * 14, 56)
    D_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
    D_STD = np.array([0.229, 0.224, 0.225], np.float32)
    d_in_name = dsess.get_inputs()[0].name if dsess else None

    fi = 0
    prev_alpha = None
    prev_needed = False
    cam_state = [1.0, 0.0, 0.0, 0.0, 0.0]   # [z, px, py, rd, px_prev fuer Whip-Blur]
    prev_gray = None
    scene_cum = [0.0, 0.0]
    scene_gate = [0.0, 0.0]
    scene_smooth = [0.0, 0.0]
    prev_scene = [0.0, 0.0]
    trk_prev = None
    H_cum = np.eye(3)
    track_gen = 0
    trk_fail = 0
    sx_up, sy_up = W / 480.0, H / float(int(H * 480 / W))
    S_up = np.diag([sx_up, sy_up, 1.0])
    S_dn = np.linalg.inv(S_up)
    import time as _time
    t_start = _time.time()
    max_frames = int(args.duration * fps) if args.duration else None
    if max_frames:
        print(f'Vorschau-Modus: nur die ersten {args.duration:.0f} Sekunden')
    win = args.window
    preroll = 1.2
    seek = max(win[0] - preroll, 0.0) if win else 0.0
    off_frames = int(round(seek * fps))
    first_abs = last_abs = None                 # exakt geschriebene Frame-Grenzen
    if win:
        print(f'Fenster-Render: {win[0]:.2f}s - {win[1]:.2f}s '
              f'(Vorlauf {win[0] - seek:.2f}s fuer Tracking/Matting)')
    # ---- v73: Freeze-Frame vorberechnen. Auf dem staerksten power=3-Moment
    # wird das Video-Frame fuer `freeze_frame` Sekunden gehalten (Regie-Trick,
    # der die Aufmerksamkeit auf die Punchline zwingt). Caption laeuft weiter.
    freeze_dur = float(cfg['effects'].get('freeze_frame', 0.0) or 0.0)
    freeze_windows = []
    if freeze_dur > 0.02:
        p3 = [p for p in plans if p.get('power', 2) == 3
              and 'kw_i' in p and not p.get('broll')]
        if p3:
            p3.sort(key=lambda p: (-float(p.get('power', 2)),
                                   -(p.get('end', 0) - p.get('start', 0))))
            fp = p3[0]
            fz_start = float(fp.get('t0', fp['start']))
            freeze_windows.append((fz_start, fz_start + freeze_dur))
            print(f'Freeze-Frame: {fz_start:.2f}s fuer {freeze_dur:.2f}s '
                  f'(Moment "{fp.get("text", "?")}")')
    frozen_frame = None
    for frame in iter_frames(args.input, W, H, fps_str,
                             start=seek if win else None):
        if max_frames and fi >= max_frames: break
        t = (fi + off_frames) / fps
        if win and t > win[1] + 1.0 / fps: break
        frame = frame.astype(np.float32)
        # Freeze anwenden: wenn t in einem Fenster, dann Frame durch
        # den ersten Frame ab Fensterstart ersetzen.
        for fz_s, fz_e in freeze_windows:
            if fz_s <= t < fz_e:
                if frozen_frame is None:
                    frozen_frame = frame.copy()
                frame = frozen_frame.copy()
                break
            elif t >= fz_e:
                frozen_frame = None

        # --- Freistellen nur in den benoetigten Fenstern
        fa = fi + off_frames
        if fa < len(need_alpha) and need_alpha[fa]:
            if not prev_needed:
                rec = [np.zeros([1, 1, 1, 1], dtype=np.float32)] * 4
                prev_alpha = None
            src_t = np.transpose(cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_BGR2RGB)
                                 .astype(np.float32) / 255.0, (2, 0, 1))[None]
            _, pha, *rec = sess.run(None, {'src': src_t, 'r1i': rec[0], 'r2i': rec[1],
                                           'r3i': rec[2], 'r4i': rec[3],
                                           'downsample_ratio': dsr})
            alpha = pha[0, 0][..., None]
            # Kante an das echte Bild schnappen (Haare, Schultern, Finger)
            alpha = refine_alpha(alpha, frame,
                                 float(cfg['effects'].get('matte_refine', 1.0))
                                 * q_refine)
            # Zeitliche Glaettung gegen Flackern - aber NUR wenn sich wenig bewegt.
            # Bei schneller Bewegung wuerde das Mitteln einen Geisterschatten
            # hinter der Person ziehen. Darum bewegungsabhaengig.
            if prev_alpha is not None:
                bewegung = float(np.abs(alpha - prev_alpha).mean())
                if bewegung < 0.15:
                    mix = 0.65 + 0.20 * min(bewegung / 0.15, 1.0)   # ruhig: staerker glaetten
                    alpha = mix * alpha + (1 - mix) * prev_alpha
            prev_alpha = alpha
            prev_needed = True
        else:
            alpha = None
            prev_needed = False

        # --- Globale Kamerabewegung fuer die Szenen-Verankerung
        coh_resp = None                    # Phasen-Korrelation dieses Frames
        if cfg['effects'].get('scene_lock', True):
            g = cv2.cvtColor(cv2.resize(frame.astype(np.uint8), (240, 136)),
                             cv2.COLOR_BGR2GRAY).astype(np.float32)
            if prev_gray is not None:
                (sdx, sdy), resp = cv2.phaseCorrelate(prev_gray, g)
                coh_resp = float(resp)
                if resp > 0.12 and abs(sdx) < 40 and abs(sdy) < 40:
                    fx_full, fy_full = sdx * (W / 240.0), sdy * (W / 240.0)
                    ga = 0.30                      # geglaettetes Bewegungssignal
                    scene_gate[0] += ga * (fx_full - scene_gate[0])
                    scene_gate[1] += ga * (fy_full - scene_gate[1])
                    # Schwenk = anhaltend gleiche Richtung; Gesten mitteln sich zu ~0
                    if abs(scene_gate[0]) > 1.1:
                        scene_cum[0] += fx_full
                    if abs(scene_gate[1]) > 1.1:
                        scene_cum[1] += fy_full
                    if abs(scene_gate[0]) <= 1.1 and abs(scene_gate[1]) <= 1.1:
                        scene_cum[0] *= 0.97       # ohne echte Bewegung sanft zurueck
                        scene_cum[1] *= 0.97
            prev_gray = g
            a = 0.35
            scene_smooth[0] += a * (scene_cum[0] - scene_smooth[0])
            scene_smooth[1] += a * (scene_cum[1] - scene_smooth[1])

        # --- Planarer Kamera-Track (nur in Szenen-Text-Fenstern)
        # fa = absolute Frame-Nummer: bei Fenster-Renders (--window) zaehlt fi
        # ab Fensterstart - need_track/need_depth sind aber absolut indiziert.
        # Mit fi waren Tracking + Tiefe im Fenster-Render schlicht nie aktiv.
        if fa < len(need_track) and need_track[fa]:
            tg = cv2.cvtColor(cv2.resize(frame.astype(np.uint8),
                                         (480, int(H * 480 / W))), cv2.COLOR_BGR2GRAY)
            if trk_prev is not None:
                # Schnitt-Erkennung: harter Bildwechsel -> Track neu aufsetzen.
                # WICHTIG: ein schneller Schwenk sieht im Pixel-Diff auch
                # "hart" aus, hat aber KOHAERENTE Bewegung (Phasen-Korrelation
                # schlaegt an). Nur wenn beides fehlt, ist es ein Schnitt -
                # sonst wuerde der Welt-Anker mitten im Schwenk zurueckgesetzt
                # und das liegende Wort spraenge neu an.
                _hard = float(np.abs(tg.astype(np.float32)
                                     - trk_prev.astype(np.float32)).mean()) > 42
                if _hard and (coh_resp is None or coh_resp < 0.25):
                    H_cum = np.eye(3); track_gen += 1; trk_fail = 0
                else:
                    Hs_small, ok_t = update_homography(trk_prev, tg, np.eye(3))
                    if ok_t:
                        H_step = S_up @ Hs_small @ S_dn
                        H_cum = H_step @ H_cum
                        H_cum /= H_cum[2, 2]
                        trk_fail = 0
                    else:
                        trk_fail += 1
                        if trk_fail > 12:
                            H_cum = np.eye(3); track_gen += 1; trk_fail = 0
            trk_prev = tg
        else:
            trk_prev = None
            H_cum = np.eye(3)
            track_gen += 1

        # --- Tiefe fuer Okklusion (nur in Szenen-Text-Fenstern)
        depth_n = None
        if dsess is not None and fa < len(need_depth) and need_depth[fa]:
            small_d = cv2.resize(frame.astype(np.uint8), (d_w, d_h))
            rgbn = (small_d[..., ::-1].astype(np.float32) / 255.0 - D_MEAN) / D_STD
            pred = dsess.run(None, {d_in_name: rgbn.transpose(2, 0, 1)[None]})[0][0]
            p5, p95 = np.percentile(pred, 5), np.percentile(pred, 95)
            dn = np.clip((pred - p5) / max(p95 - p5, 1e-4), 0, 1)
            depth_n = cv2.resize(dn.astype(np.float32), (W, H))
        scene_vel = float(np.hypot(scene_smooth[0] - prev_scene[0],
                                   scene_smooth[1] - prev_scene[1]))
        prev_scene = list(scene_smooth)
        fidx = min(fi, len(face_stable) - 1)
        ai = min(fi, len(aud_rms) - 1)
        comp = composite_frame(frame, alpha, t, plans, words, face_stable[fidx],
                               cfg, S, W, H, cam_state, tuple(scene_smooth),
                               aud=(float(aud_rms[ai]), float(aud_bass[ai]),
                                    float(aud_onset[ai])),
                               depth_n=depth_n, scene_vel=scene_vel,
                               H_cum=(H_cum if (fa < len(need_track) and need_track[fa])
                                      else None),
                               track_gen=track_gen)
        if not win or t >= win[0] - 1e-6:
            if first_abs is None:
                first_abs = fi + off_frames
            last_abs = fi + off_frames
            if wm is not None:
                _a, _x, _y = wm
                _h, _w = _a.shape[:2]
                _roi = comp[_y:_y + _h, _x:_x + _w]
                _al = (_a[:, :, 3:4].astype(np.float32) / 255.0)
                _roi[:] = _roi * (1 - _al) + _a[:, :, 2::-1].astype(np.float32) * _al
            try:
                enc.stdin.write(np.clip(comp, 0, 255).astype(np.uint8).tobytes())
            except BrokenPipeError:
                # v80n: ffmpeg ist gestorben - Ursache so genau wie moeglich melden
                err = ''
                try:
                    if enc.stderr:
                        err = enc.stderr.read().decode('utf-8', 'ignore')[-800:]
                except Exception:
                    pass
                rc = enc.poll()
                if not err.strip() and rc in (-9, 137):
                    grund = ('Der Videoschreiber wurde vom System beendet '
                             '(Out-of-Memory-Killer). Der Server hatte zu wenig '
                             'freien Arbeitsspeicher fuer diese Aufloesung.')
                elif not err.strip():
                    grund = (f'Der Videoschreiber wurde beendet (Exit-Code {rc}) '
                             f'ohne Fehlermeldung - typisch fuer volle Festplatte '
                             f'oder System-Kill.')
                else:
                    grund = f'ffmpeg-Fehler: {err.strip()}'
                sys.exit(f"FEHLER: Video-Encoding abgebrochen. {grund}")
        fi += 1
        if fi % 100 == 0:
            el = _time.time() - t_start
            rate = fi / max(el, 0.01)
            rest = int(((max_frames or n_frames) - fi) / max(rate, 0.01))
            print(f"  Frame {fi}/{max_frames or n_frames} | {rate:.1f} f/s | "
                  f"noch ~{rest // 60}:{rest % 60:02d}", flush=True)
    enc.stdin.close()
    enc_err = b''
    try:
        enc_err = enc.stderr.read() if enc.stderr else b''
    except Exception:
        pass
    enc.wait()
    if fi == 0:
        sys.exit("FEHLER: Es konnten keine Frames gelesen werden. Ist die Videodatei intakt?")
    if enc.returncode != 0:
        sys.exit(f"FEHLER: Video-Encoding fehlgeschlagen (ffmpeg Exit "
                 f"{enc.returncode}). "
                 f"{enc_err.decode('utf-8', 'ignore')[-600:].strip() or '(keine Ausgabe)'}")

    # --- Stufe 2 (v80p): Audio + SFX dazu muxen. Video wird nur kopiert.
    if video_tmp:
        # WICHTIG: nur die ERSTE Tonspur (1:a:0). iPhone-Videos tragen oft
        # zusaetzliche Metadaten-Streams, die als 'Audio mit Codec none'
        # auftauchen - '1:a' wuerde die mit mappen und ffmpeg abbrechen lassen.
        mux = ['ffmpeg', '-y', '-v', 'error', '-i', video_tmp, '-i', args.input]
        if sfx_path and has_audio:
            mux += ['-i', sfx_path, '-filter_complex',
                    f'[2:a:0]volume={vol}[sfx];'
                    f'[1:a:0][sfx]amix=inputs=2:duration=first:normalize=0[aout]',
                    '-map', '0:v', '-map', '[aout]']
        elif sfx_path:
            mux += ['-i', sfx_path, '-filter_complex', f'[2:a:0]volume={vol}[aout]',
                    '-map', '0:v', '-map', '[aout]']
        else:
            mux += ['-map', '0:v', '-map', '1:a:0?']
        mux += ['-c:v', 'copy'] + acodec + ['-shortest', out_path]
        print("Tonspur wird angelegt...")
        r_mux = subprocess.run(mux, capture_output=True, text=True)
        if r_mux.returncode != 0 or not os.path.exists(out_path):
            sys.exit(f"FEHLER: Ton-Muxing fehlgeschlagen: "
                     f"{(r_mux.stderr or '')[-600:].strip() or '(keine Ausgabe)'}")
        try:
            os.remove(video_tmp)
        except OSError:
            pass
    print(f"Fertig: {out_path}")

    # --- Fenster-Segment frame-exakt ins fertige Video einsetzen
    if args.window and args.splice_into:
        if first_abs is None:
            sys.exit("FEHLER: Fenster hat keine Frames erzeugt.")
        if not os.path.exists(args.splice_into):
            sys.exit(f"FEHLER: Zielvideo nicht gefunden: {args.splice_into}")
        t0x = first_abs / fps                    # exakte Grenzen auf dem Frame-Raster
        t1x = (last_abs + 1) / fps
        tmp = args.splice_into + '.splice.tmp.mp4'
        parts, n_in = [], 0
        fc = []
        if t0x > 1e-6:
            fc.append(f"[0:v]trim=end={t0x:.6f},setpts=PTS-STARTPTS[p{n_in}]")
            parts.append(f"[p{n_in}]"); n_in += 1
        fc.append(f"[1:v]setpts=PTS-STARTPTS[p{n_in}]")
        parts.append(f"[p{n_in}]"); n_in += 1
        fc.append(f"[0:v]trim=start={t1x:.6f},setpts=PTS-STARTPTS[p{n_in}]")
        parts.append(f"[p{n_in}]"); n_in += 1
        fc.append(''.join(parts) + f"concat=n={n_in}:v=1:a=0[v]")
        r = subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.splice_into,
                            '-i', out_path, '-filter_complex', ';'.join(fc),
                            '-map', '[v]', '-map', '0:a?', '-c:a', 'copy',
                            '-c:v', 'libx264', '-preset', 'fast',
                            '-crf', str(cfg['output'].get('crf', 18)),
                            '-pix_fmt', 'yuv420p', tmp], capture_output=True)
        if r.returncode != 0 or not os.path.exists(tmp):
            sys.exit("FEHLER beim Einsetzen: " + r.stderr.decode('utf-8', 'ignore')[-300:])
        os.replace(tmp, args.splice_into)
        print(f"Segment eingesetzt: {args.splice_into} "
              f"({t0x:.2f}s - {t1x:.2f}s ersetzt)")

if __name__ == '__main__':
    main()
