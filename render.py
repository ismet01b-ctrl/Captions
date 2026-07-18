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
            'dx': rel * w * 0.028 + (float(rng.random()) - 0.5) * w * 0.008,
            'dy': (float(rng.random()) - 0.25) * h * 0.10,
            'rot': rel * 3.2 + (float(rng.random()) - 0.5) * 1.6,
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
            pad_x, pad_y = int(w * 0.09) + 6, int(h * 0.16) + 6
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
            pad = int(w * 0.25) + 6
            out = np.zeros((h, w + 2 * pad, 4), base.dtype)
            for i in range(n_col):
                x0 = i * cw
                x1 = min(x0 + cw, w)
                if x1 <= x0:
                    continue
                seg = base[:, x0:x1]
                # radial vom Zentrum weg
                cx = (x0 + x1) / 2 - w / 2
                dx_s = int(cx / (w / 2) * (w * 0.22) * spread)
                dst_x = pad + x0 + dx_s
                if 0 <= dst_x <= w + 2 * pad - (x1 - x0):
                    np.maximum(out[:, dst_x:dst_x + (x1 - x0)], seg,
                               out=out[:, dst_x:dst_x + (x1 - x0)])
            arr = out
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

Regeln: Wasser/Boden gross im Bild + grosser Moment -> "liegend". Klare Flaeche im \
Mittelgrund -> "stehend". Sprecher-Nahaufnahme -> "frei". Im Zweifel "frei".
Antworte NUR mit JSON: {"momente": [{"i": <Index>, "szene": "...", "lage": "...", "fx": "<optional>"}]}"""

def ai_scene_direct(words, fx_map, video_path, model='gpt-4o', min_power=2):
    """Regie v4 (Vision): schaut sich pro gewaehltem Moment einen Frame an und
    entscheidet Material ('szene') und Lage ('liegend'/'stehend'/'frei').
    Ergaenzt fx_map in-place. Faellt bei jedem Fehler lautlos auf Text-Regie zurueck.

    v80e: min_power (Default 2) filtert billige power=1-Momente raus. Die kriegen
    keine Vision-Analyse - fuer die reicht Text-Regie. Spart 60% Vision-Kosten."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not fx_map:
        return fx_map
    idx = [i for i in sorted(fx_map)
           if int(fx_map[i].get('power', 2)) >= min_power][:24]
    if not idx:
        return fx_map                          # nur schwache Momente = kein Vision-Call
    content = []
    sent = []
    for i in idx:
        b64 = _frame_b64(video_path, words[i]['start'] + 0.15)
        if not b64:
            continue
        txt = ' '.join(clean(words[j]['word'])
                       for j in range(i, min(i + fx_map[i].get('n', 1), len(words))))
        content.append({'type': 'text',
                        'text': f"MOMENT [{i}] Text: \"{txt}\" geplant: {fx_map[i].get('fx')}"})
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
            json={'model': model, 'temperature': 0.1, 'max_tokens': 1500,
                  'response_format': {'type': 'json_object'},
                  'messages': [{'role': 'system', 'content': SZENE_PROMPT},
                               {'role': 'user', 'content': content}]},
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
    opts = vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=os.path.join(HERE, 'models/face.tflite')),
        min_detection_confidence=0.4)
    detector = vision.FaceDetector.create_from_options(opts)
    raw, hists, face_hists = [], [], []
    last_det = None
    fi_a = 0
    for frame in iter_frames(video_path, work_w, work_h, fps_str):
        tiny = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(tiny, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        hists.append(hist)
        if fi_a % det_step != 0:
            raw.append(list(last_det) if last_det else None)
            face_hists.append(None)
            fi_a += 1
            continue
        fi_a += 1
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img))
        if res.detections:
            d = max(res.detections, key=lambda d: d.categories[0].score)
            bb = d.bounding_box
            last_det = [bb.origin_x + bb.width / 2, bb.origin_y + bb.height / 2, bb.width]
            raw.append(list(last_det))
            x0, y0 = max(bb.origin_x, 0), max(bb.origin_y, 0)
            crop = frame[y0:y0 + max(bb.height, 4), x0:x0 + max(bb.width, 4)]
            if crop.size:
                ch = cv2.calcHist([cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)], [0, 1], None,
                                  [8, 8], [0, 180, 0, 256])
                cv2.normalize(ch, ch)
                face_hists.append(ch)
            else:
                face_hists.append(None)
        else:
            last_det = None
            raw.append(None)
            face_hists.append(None)
    n = len(raw)

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
    valid = [h for h in face_hists if h is not None]
    if len(valid) > 10:
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
        if is_head and ref_w and det_shot:
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
    print(f"  {len(shots)} Szenen, {int(sum(r is not None for r in raw))}/{n} Frames mit Gesicht"
          + (f", {n_broll} Frames als B-Roll eingestuft" if n_broll else ""))
    sc = out_w / float(work_w)
    # v85: interne Schnitt-Frames mitgeben (fuer Caption-Schnitt-Disziplin).
    inner_cuts = [c for c in cuts if 0 < c < n]
    return sm * sc, present, wsm * sc, inner_cuts

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

Vorgehen:
1. Erfasse die Kernbotschaft des Videos.
2. Waehle die Woerter, die die Geschichte TRAGEN: Zahlen, Namen, Fachbegriffe, emotionale \
Spitzen, Pointen, Kontraste.
3. Verteile ueber das Video: ein starker Moment frueh (Hook), einer am Ende (Abschluss).

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
Beispiel: "unser Umsatz explodiert" -> "anim": "schub". Sonst weglassen.
- Optional "emoji": EIN einzelnes Unicode-Emoji das die Aussage untermalt. \
Nur wenn es wirklich passt - kein Deko-Zwang. Beispiele: \
Geld/Umsatz "💰" · Wachstum "🚀" · Absturz "📉" · Rekord "🏆" · Schock "⚠️" · \
Zeit "⏰" · Herz/Emotion "❤️" · Fakt/Beweis "✅" · Verbot "🚫" · Idee "💡" · \
Sieg "🔥" · Krise "🆘". Kein Emoji bei neutralem Text.
Antworte NUR mit JSON: {"keywords": [{"i": <Startindex>, "n": <1-4>, "fx": "<Effekt>", "power": <1-3>, "anim": "<optional>", "emoji": "<optional>"}]}"""

def parse_regie(text, words, language='de'):
    import json as _json
    non_de = language not in ('de', 'auto', None, '')
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
            json={'model': model, 'temperature': 0.0, 'max_tokens': 800,
                  'response_format': {'type': 'json_object'},
                  'messages': [{'role': 'system', 'content': prompt},
                               {'role': 'user', 'content': json.dumps(
                                   entries, ensure_ascii=False)}]},
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
    chunks = _regie_chunks(words)
    lang_hint = '' if language in ('de', 'auto', None, '') else \
        f"SPRACHE: Das Transkript ist nicht deutsch ({language}). " \
        f"Wende die Regeln sinngemaess auf diese Sprache an.\n\n"
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
            wl_toks.append(f"[{i}]{raw}")
        listing = lang_hint + part_hint + 'TRANSKRIPT:\n' + prose + \
                  '\n\nWORTLISTE (nur waehlbare Substanz-Woerter, ' \
                  'Fuellwoerter wurden entfernt):\n' + ' '.join(wl_toks)
        try:
            r = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}'},
                json={'model': model, 'temperature': 0.2, 'max_tokens': 3000,
                      'response_format': {'type': 'json_object'},
                      'messages': [{'role': 'system', 'content': REGIE_PROMPT},
                                   {'role': 'user', 'content': listing}]},
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
                         'minus', 'talfahrt', 'billiger', 'weniger')),
              ('anstieg', ('steigt', 'steigen', 'anstieg', 'rekord', 'gewinn',
                           'zuwachs', 'kletter', 'teurer', 'hoeher', 'höher',
                           'verdoppelt', 'verdreifacht', 'aufwaerts', 'aufwärts',
                           'zunahme')),
              ('wende', ('kippt', 'wende', 'umkehr', 'gegenteil', 'ploetzlich',
                         'plötzlich', 'umgekehrt', 'kehrtwende', 'umschwung',
                         'dreht', 'wendepunkt', 'stattdessen')),
              ('druck', ('druck', 'last', 'belastung', 'zwang', 'erdrueck',
                         'erdrück', 'schulden', 'buerde', 'bürde', 'kosten',
                         'abgaben', 'steuerlast', 'schwer')),
              ('schwund', ('verschwindet', 'verschwunden', 'verloren',
                           'geloescht', 'gelöscht', 'vorbei', 'verpuff', 'nichts',
                           'aufgeloest', 'aufgelöst', 'schwindet', 'futsch',
                           'dahin')),
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
                        'dash', 'sprint', 'rennen', 'rennt', 'laeuft', 'läuft')),
              # ---- v71
              ('kippen', ('kippt', 'kippen', 'klappt', 'aufklappt', 'oeffnet',
                          'öffnet', 'aufgeschlagen', 'kapitel')),
              ('explosion', ('explodiert', 'explosion', 'sprengt', 'gesprengt',
                             'zerstoert', 'zerreist', 'zerreißt', 'detoniert',
                             'blast')),
              ('magnet', ('zieht', 'anziehung', 'magnet', 'sog', 'sammelt',
                          'buendel', 'bündel', 'fokussiert', 'zieht an',
                          'ballt', 'rein', 'reinkommt', 'reinfliegt',
                          'einsaugt', 'ansaugt', 'zentriert', 'buendeln',
                          'bündeln')),
              ('wackel', ('lustig', 'quatsch', 'unsinn', 'witz', 'komisch',
                          'cartoon', 'kindisch', 'quirlig', 'bounce')),
              ('regen', ('regen', 'faellt', 'tropfen', 'rieselt', 'schuettet',
                         'schüttet', 'niederschlag', 'sturm')),
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
                palette_at=None, cut_times=None):
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
    # Variation: pro Video eigene Mischung (Seed aus der Wortzahl -> reproduzierbar)
    _seed = len(words) * 7919
    rot_cam = Rotator(CAM_FX or ['none'], _seed)
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
            if disp_end > end and not voiceover and not face_ok(end, disp_end):
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
            elif wish in KW_FX:
                fx = wish                     # KI-Regie hat entschieden
            else:
                fx = KW_FX[kwc % len(KW_FX)]; kwc += 1
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
                sz = S.fit(txt, int(H * 0.213) if not portrait else int(H * 0.11), int(W * (0.62 if safe_z else 0.94) if portrait else W * 0.885))
                if S.kinetic and not p.get('count'):
                    arr, tot, lets = S.text(txt, sz, S.accent, glow=True,
                                            per_letter=True, extrude=S.ex)
                    p['arr'] = arr
                    p['letters'] = letter_slices(arr, lets)
                else:
                    p['arr'] = persp_warp(rot_img(S.text(txt, sz, S.accent, glow=True,
                                                         extrude=S.ex)[0],
                                                  p['tilt'] * 0.6), yaw=p['tilt'] * 4.5)
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
                if lage == 'liegend':
                    lying = broll
                elif lage in ('stehend', 'frei'):
                    lying = False
                else:
                    lying = broll and (pw_g >= 3 or szene in ('wasser', 'boden'))
                standing = broll and not lying
                g_pitch = 0.68 if lying else (0.06 if standing else 0.5)
                g_ex = False if lying else S.ex
                sz = S.fit(txt, int(H * 0.20) if not portrait else int(H * 0.10),
                           int(W * 0.72 if not portrait else W * (0.62 if safe_z else 0.9)), font=S.f_serif)
                g_yaw = -6 if (side_toggle % 2 == 0) else 6
                if S.kinetic and not p.get('count') and not lying:
                    flat, tot, lets = S.text(txt, sz, S.white, per_letter=True, extrude=g_ex)
                    p['arr'] = flat
                    p['letters'] = letter_slices(flat, lets)
                else:
                    flat = S.text(txt, sz, S.white, extrude=g_ex, flat_light=lying)[0]
                    p['arr'] = persp_warp(flat, yaw=g_yaw, pitch=g_pitch)
                if lying:
                    p['scene_blend'] = True        # Wellen laufen durch die Buchstaben
                if broll and cfg['effects'].get('track3d', True):
                    p['track3d'] = True            # planares Kamera-Tracking
                if cfg['effects'].get('reflection', True) and not lying:
                    r, rdy, rdx = make_reflection(p['arr'])
                    if r is not None:
                        p['refl'], p['refl_dy'], p['refl_dx'] = r, rdy, rdx
                if not broll:                      # Kontakt-Schatten nur auf festem Boden
                    sh, sdy_, sdx_ = make_contact_shadow(p['arr'])
                    if sh is not None:
                        p['cshadow'], p['csh_dy'], p['csh_dx'] = sh, sdy_, sdx_
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _y=g_yaw, _pt=g_pitch, _ex=g_ex:
                                    persp_warp(S.text(s, _sz, S.white, extrude=_ex)[0],
                                               yaw=_y, pitch=_pt))
                side_toggle += 1
                p['cx'] = W / 2
                if broll and cfg['effects'].get('track3d', True):
                    # weit voraus verankern: der Text kommt auf uns zu und waechst
                    p['cy'] = H * (0.60 if not portrait else 0.58)
                else:
                    p['cy'] = H * (0.80 if not portrait else (0.72 if safe_z else 0.82))
                sy = p['cy'] - H * 0.155
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
            plans.append(p)
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
    hook_len = float(cfg['effects'].get('hook_seconds', 15))
    hook_on = (cfg['effects'].get('intro_hook', True) and hook_len > 0)
    if hook_on and cfg['effects'].get('instant_hook', True):
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


def apply_duplicate_trail(comp, frame, strength, offset_px=14, layers=3):
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
        fg = alpha[..., 0] if alpha.ndim == 3 else alpha
        fg = np.clip(fg.astype(np.float32), 0, 1)
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
        """Tiefen-Okklusion: Maske der Bildteile, die NAEHER sind als der Text.
        d_ref wird beim ersten aktiven Frame am Text-Ort gemessen."""
        if depth_n is None:
            return None
        if 'd_ref' not in p:
            cx_ = int(p.get('cx', W / 2)); cy_ = int(p.get('cy', H * 0.8))
            hw = int(min(p['arr'].shape[1] * 0.40, W * 0.3))
            hh = int(min(p['arr'].shape[0] * 0.28, H * 0.12))
            reg = depth_n[max(cy_ - hh, 0):min(cy_ + hh, H),
                          max(cx_ - hw, 0):min(cx_ + hw, W)]
            p['d_ref'] = float(np.median(reg)) if reg.size else 0.5
        occ = np.clip((depth_n - p['d_ref'] - 0.07) / 0.10, 0, 1)
        occ = cv2.GaussianBlur(occ, (0, 0), 4)
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
            if p.get('broll'):
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
            frame = apply_bg_blur(frame, alpha, depth_n, bg_blur * bstr, W, H)

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
        # Kein Farbsaum: der Caption-Text hinter der Person darf nicht um die
        # Schulter herumleuchten.
        if cfg['effects'].get('matte_spill', True):
            person = kill_spill(person, alpha, frame)
        # KONTAKTSCHATTEN: Die Person wirft einen weichen Schatten auf die
        # Textebene hinter ihr. Ohne ihn ist der Text nur ausgeschnitten - mit
        # ihm sitzt er IM Raum. Genau daran erkennt man 2026 den Unterschied
        # zwischen Vorlagen-Look und Produktion.
        if PERSON_SHADOW > 0 and behind_str > 0.02:
            a0 = alpha[..., 0]
            sig = max(min(W, H) * 0.016, 3.0)
            sh = cv2.GaussianBlur(a0, (0, 0), sig)
            M = np.float32([[1, 0, W * 0.008], [0, 1, H * 0.012]])   # Licht von oben links
            sh = cv2.warpAffine(sh, M, (W, H), borderValue=0.0)
            sh = np.clip(sh - a0, 0, 1)          # nur ausserhalb der Person
            k = 0.55 * PERSON_SHADOW * behind_str
            comp = comp * (1.0 - k * sh[..., None])
        comp = person * alpha + comp * (1 - alpha)

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
        x_dur = 0.20 + 0.12 * min(ah / (H * 0.15), 1.0)
        over = t - p['end']
        if p.get('power', 2) >= 3:
            over -= 0.04
        g_out = exit_env(over, x_dur)
        x_sc, x_dv = exit_pose(over, x_dur)
        tdx, tdy = track_offset(p, face_xy, cfg)
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
            sdx, sdy = scene_shift(p)
            apply_count(p, dt)
            if p.get('cshadow') is not None:
                paste(comp, p['cshadow'], p.get('cx', W / 2) + sdx + p['csh_dx'],
                      p['cy'] + sdy + p['csh_dy'] + p['cshadow'].shape[0] * 0.30,
                      W, H, opacity=min(dt / 0.5, 1.0) * g_out)
            g_broll = p.get('broll')
            occ_g = occ_for(p) if g_broll else None
            cam_blur = min(scene_vel * 0.45, 5.0) if g_broll else 0.0
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
                d_tr = 0.9                       # Grund-Daempfung (AE-Praxis)
                H_rel = d_tr * H_rel + (1 - d_tr) * np.eye(3)
                H_rel /= H_rel[2, 2]
                # Adaptiv: Drift des Text-Zentrums deckeln - der Text bleibt im
                # Bild und lesbar, bewegt sich aber weiter echt mit der Welt
                ctr = H_rel @ np.array([p.get('cx', W / 2), p['cy'], 1.0])
                ctr /= ctr[2]
                drift = float(np.hypot(ctr[0] - p.get('cx', W / 2), ctr[1] - p['cy']))
                lim = H * 0.26
                if drift > lim:
                    d2 = lim / drift
                    H_rel = d2 * H_rel + (1 - d2) * np.eye(3)
                    H_rel /= H_rel[2, 2]
                e = smoothstep(dt / 0.75)
                arr_t3, adx_g, dy_f, asc_g, aop_g = anim_apply(p, p['arr'], aud, dt)
                dy_f -= (arr_t3.shape[0] - p['arr'].shape[0]) / 2
                g_op = (0.74 if p.get('scene_blend')
                        else (1.0 if p.get('glass') else 0.97))
                # "Aus dem Wasser": Glas-Text steigt aus der Flaeche auf -
                # erst tief und verschwommen wie unter der Oberflaeche, dann klar
                if p.get('glass') and p.get('material', 'wasser') == 'wasser':
                    emerge = smoothstep(min(dt / 0.9, 1.0))
                    dy_e = (1 - emerge) * arr_t3.shape[0] * 0.55
                    bl_e = (1 - emerge) * 3.5
                    op_e = 0.35 + 0.65 * emerge
                else:
                    dy_e, bl_e, op_e = (1 - e) * H * 0.03, 0.0, 1.0
                dy_e += dy_f
                paste_tracked(comp, arr_t3, p.get('cx', W / 2) + adx_g, p['cy'],
                              H_rel, W, H,
                              dy_extra=dy_e,
                              opacity=min(dt / 0.4, 1) * g_out * g_op * op_e * aop_g,
                              refract=1.0 if p.get('scene_blend') else 0.0,
                              ripple=0.06 if p.get('glass')
                              else (0.10 if p.get('scene_blend') else 0.12),
                              grain=1.5 if p.get('glass') else 2.2,
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
                                    opacity=min(dl / 0.12, 1) * g_out
                                    * (0.74 if p.get('scene_blend') else 0.97),
                                    refract=1.0 if p.get('scene_blend') else 0.0,
                                    ripple=0.10 if p.get('scene_blend') else 0.12,
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
                    arr_s, adx_s, dy_s, asc_s, aop_s = anim_apply(p, p['arr'], aud, dt)
                    dy_s -= (arr_s.shape[0] - p['arr'].shape[0]) / 2
                    paste_scene(comp, arr_s, p.get('cx', W / 2) + sdx + adx_s,
                                p['cy'] + sdy + dy_s + (1 - e) * H * 0.03,
                                W, H, scale=(0.97 + 0.03 * e) * live * asc_s,
                                opacity=min(dt / 0.4, 1) * g_out * aop_s
                                * (0.74 if p.get('scene_blend')
                                   else (1.0 if p.get('glass') else 0.97)),
                                refract=1.0 if p.get('scene_blend') else 0.0,
                                ripple=0.06 if p.get('glass')
                                else (0.10 if p.get('scene_blend') else 0.12),
                                grain=1.5 if p.get('glass') else 2.2,
                                occ=occ_g,
                                blur=max(cam_blur, (1 - e) * 4.5 if not p.get('scene_blend') else 0.0))
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
    _trail = float(cfg['effects'].get('trail', 0.0) or 0.0)
    if _trail > 0.02:
        comp = apply_duplicate_trail(comp, frame, _trail)
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
    face, has_face, face_w, cut_frames = track_faces(args.input, W, H, fps_str, det_step)
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
            fx_map = parse_regie(open(regie_path, encoding='utf-8').read(), words,
                                 cfg.get('language', 'de'))
        if fx_map is None:
            print("KI-Regie analysiert das Transkript...")
            fx_map = ai_direct(words, cfg.get('language', 'de'),
                               cfg['keywords'].get('ai_model', 'gpt-4o'),
                               voice_wav=voice_wav,
                               validate=cfg['keywords'].get('ai_validate', True))
            if fx_map and cfg['keywords'].get('ai_vision', True):
                fx_map = ai_scene_direct(words, fx_map, args.input,
                                         cfg['keywords'].get('ai_model', 'gpt-4o'),
                                         min_power=int(cfg['keywords'].get('vision_min_power', 2)))
            if fx_map:
                json.dump({'keywords': [{'i': i, 'fx': v['fx'], 'power': v['power'],
                                         'n': v.get('n', 1),
                                         **({'anim': v['anim']} if v.get('anim') else {}),
                                         **({'szene': v['szene']} if v.get('szene') else {}),
                                         **({'lage': v['lage']} if v.get('lage') else {})}
                                        for i, v in sorted(fx_map.items())]},
                          open(regie_path, 'w', encoding='utf-8'))
    if fx_map:
        kw = set(fx_map)
        manual = detect_keywords(words, {**cfg, 'keywords': {**cfg['keywords'], 'auto': False}},
                                 args.keywords)
        kw |= manual
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
        _mom_export.append({'i': i, 'text': txt, 'zeit': round(words[i]['start'], 2),
                            'fx': info.get('fx', 'behind'),
                            'power': int(info.get('power', 2)), 'n': n,
                            'anim': _anim, 'aktiv': True,
                            'szene': info.get('szene') or '',
                            'lage': info.get('lage') or '',
                            'emoji': info.get('emoji') or '',
                            'thumb': thumb_rel})
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
    plans = build_plans(words, kw, cfg, S, W, H, face_ok, fx_map, face_pos,
                        palette_at, cut_times=cut_times)

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
        if p['tpl'] in ('behind', 'blurin'):
            a = max(int((p['start'] - 0.2) * fps), 0)
            b = min(int((p['end'] + 0.6) * fps) + 1, total_est)
            need_alpha[a:b] = True
    print(f"Matting-Fenster: {int(need_alpha.sum())} von ~{total_est} Frames")

    # Tiefen-Fenster: Okklusion nur, wo Szenen-Texte (B-Roll ground) aktiv sind
    need_depth = np.zeros(total_est, dtype=bool)
    dsess = None
    if cfg['effects'].get('occlusion', True):
        for p in plans:
            if p['tpl'] == 'ground' and p.get('broll'):
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
            if p['tpl'] == 'ground' and p.get('broll'):
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
        if cfg['effects'].get('scene_lock', True):
            g = cv2.cvtColor(cv2.resize(frame.astype(np.uint8), (240, 136)),
                             cv2.COLOR_BGR2GRAY).astype(np.float32)
            if prev_gray is not None:
                (sdx, sdy), resp = cv2.phaseCorrelate(prev_gray, g)
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
        if fi < len(need_track) and need_track[fi]:
            tg = cv2.cvtColor(cv2.resize(frame.astype(np.uint8),
                                         (480, int(H * 480 / W))), cv2.COLOR_BGR2GRAY)
            if trk_prev is not None:
                # Schnitt-Erkennung: harter Bildwechsel -> Track neu aufsetzen
                if float(np.abs(tg.astype(np.float32) - trk_prev.astype(np.float32)).mean()) > 42:
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
                        if trk_fail > 8:
                            H_cum = np.eye(3); track_gen += 1; trk_fail = 0
            trk_prev = tg
        else:
            trk_prev = None
            H_cum = np.eye(3)
            track_gen += 1

        # --- Tiefe fuer Okklusion (nur in Szenen-Text-Fenstern)
        depth_n = None
        if dsess is not None and fi < len(need_depth) and need_depth[fi]:
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
                               H_cum=(H_cum if (fi < len(need_track) and need_track[fi])
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
