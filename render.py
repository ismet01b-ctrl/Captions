"""
Premium Captions - automatische Premium-Untertitel im Editorial-Stil
Pipeline: Whisper API -> RVM Matting (GPU) -> Face Tracking -> Compositing -> Encode

Nutzung:
    python render.py video.mp4
    python render.py video.mp4 --out fertig.mp4 --keywords "Schufa,Score"
    python render.py video.mp4 --transcript video_transcript.json   (API-Aufruf ueberspringen)
"""
import argparse, copy, json, math, os, re, shutil, subprocess, sys, tempfile, time
import warnings as _warnings
# v230ay: Der Job-Log geht an den Kunden. protobuf meldet bei JEDEM
# MediaPipe-Aufruf dieselbe Veraltet-Warnung - in Ismets Log stand sie zehnmal
# und sieht aus wie ein Fehler. Sie kommt aus einer Fremdbibliothek, wir
# koennen daran nichts aendern, und sie sagt weder ihm noch mir etwas.
# BEWUSST eng gefasst: genau diese eine Meldung, keine Sammelabschaltung -
# ein stiller Filter ueber alle Warnungen wuerde die naechste echte
# verschlucken.
_warnings.filterwarnings(
    'ignore', message=r'SymbolDatabase\.GetPrototype\(\) is deprecated')
import numpy as np
import blender_engine
import cv2
import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# v227 WO GEHT DIE ZEIT HIN? Ismets Befund: knapp 3 Minuten fuer 15 Sekunden
# Video. Bis hier gab es KEINE Messung - nur eine Bilder-pro-Sekunde-Zeile im
# Log, die nicht sagt, WELCHER Schritt sie kostet. Optimieren ohne Messung
# waere Raten, und Raten heisst hier: Qualitaet abschalten, die niemand
# vermisst haette. Deshalb erst der Messschritt. Kostet nichts (ein
# Zeitstempel je Block) und steht am Ende als eine Zeile im Job-Log.
_ZEIT = {}


def zt(name, t0):
    """Dauer eines Blocks aufaddieren. Rueckgabe = jetzt, damit man Bloecke
    hintereinander messen kann: t = zt('a', t); t = zt('b', t)."""
    _n = time.time()
    _ZEIT[name] = _ZEIT.get(name, 0.0) + (_n - t0)
    return _n


# v228c Verschachtelte Bloecke duerfen nicht DOPPELT zaehlen. 'regie+plaene'
# umschliesst die KI-Aufrufe und die Bild-Analysen; in Ismets Zeile standen
# deshalb 133.2s neben 39.5+37.7+26.1+25.3s, und die Summe ergab 190 % - die
# Zahlen stimmten einzeln, die Zeile log trotzdem. Der Elternblock zeigt jetzt
# nur noch, was NACH Abzug seiner Kinder uebrig bleibt.
_ZEIT_KIND = {'regie+plaene': ('ki-textregie', 'ki-bildregie+anker',
                               'ki-textfluss', 'raumkarte', 'zeige-regie')}


def _mem_limit_gb():
    """Speicher-Deckel dieses Containers in GB, oder None (kein Deckel).
    cgroup v2 zuerst, v1 als Rueckfall - beides gibt es in freier Wildbahn."""
    for pfad in ('/sys/fs/cgroup/memory.max',
                 '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
        try:
            roh = open(pfad).read().strip()
        except OSError:
            continue
        if roh in ('max', ''):
            return None
        try:
            n = int(roh)
        except ValueError:
            continue
        if n > 0 and n < (1 << 62):       # v1 schreibt bei "kein Limit" Unsinn
            return n / (1024 ** 3)
    return None


def mem_peak_gb():
    """Hoechster Speicherverbrauch DIESES Prozesses bisher, in GB."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2)
    except Exception:
        return 0.0


def mem_zeile():
    """v230aj: 'Memory: 3.4 GB peak of 6.0 GB limit'. Ohne diese Zeile sieht
    man einem abgeschossenen Render nicht an, WARUM er starb: der Prozess ist
    einfach weg, im Log stehen nur die ffmpeg-Meldungen des Zulieferers
    ('Broken pipe'). Genau so ist Ismets 4K-Job bei Bild 100 von 293
    gestorben - und niemand konnte sagen, ob Speicher, Absturz oder Timeout."""
    peak = mem_peak_gb()
    deckel = _mem_limit_gb()
    if deckel:
        anteil = peak / deckel * 100
        return (f"Memory: {peak:.2f} GB peak of {deckel:.1f} GB limit "
                f"({anteil:.0f}%)")
    return f"Memory: {peak:.2f} GB peak (no container limit)"


_MEM_DECKEL = None            # GB, einmal beim Start ermittelt
_MEM_GEWARNT = False


def rss_gb():
    """Aktueller Speicherverbrauch dieses Prozesses in GB - billig genug, um
    ihn JEDES Bild zu lesen (/proc, kein Fremdpaket)."""
    try:
        with open('/proc/self/statm') as f:
            seiten = int(f.read().split()[1])
        return seiten * os.sysconf('SC_PAGE_SIZE') / (1024 ** 3)
    except Exception:
        return 0.0


def mem_wache(fi, gesamt_frames):
    """v230ak: NIE WIEDER STILL STERBEN. Reisst der Prozess den Speicherdeckel,
    schiesst ihn das Betriebssystem ohne Vorwarnung ab - im Log steht dann nur
    ffmpegs 'Broken pipe', der Kunde sieht 'Render failed', und niemand weiss
    warum (Ismets 4K-Job, Bild 100 von 293).
    Diese Wache liest den Verbrauch mit und greift VOR dem Kill ein:
      ab 80 % - aufraeumen, was aufraeumbar ist, und einmal warnen
      ab 93 % - sauber abbrechen MIT Grund; der Server erstattet automatisch
    Ein sauberer Abbruch ist kein schoenes Ergebnis, aber ein ehrliches: der
    Kunde erfaehrt, was los war, und behaelt sein Guthaben."""
    global _MEM_GEWARNT
    if not _MEM_DECKEL:
        return
    jetzt = rss_gb()
    anteil = jetzt / _MEM_DECKEL
    if anteil >= 0.93:
        print(f"ERROR: not enough memory - stopping at frame {fi}/{gesamt_frames}. "
              f"Used {jetzt:.2f} GB of the {_MEM_DECKEL:.1f} GB limit. "
              f"A 4K render needs more headroom than this server currently "
              f"allows; 1080p works, or raise DVE_MEM_LIMIT.", flush=True)
        sys.exit(3)
    if anteil >= 0.80 and not _MEM_GEWARNT:
        _MEM_GEWARNT = True
        import gc
        gc.collect()
        print(f"WARNING: memory at {anteil * 100:.0f}% "
              f"({jetzt:.2f} of {_MEM_DECKEL:.1f} GB) - freeing caches.",
              flush=True)


# v230d WAS KOSTET EIN RENDER? Bis hierher stand im Panel nur, was der KUNDE
# zahlt (`cost_sec`). Was der Render UNS kostet, wusste niemand - dabei liefert
# jede OpenAI-Antwort einen `usage`-Block mit, und wir haben ihn weggeworfen.
# Ohne diese Zahl ist jede Preisentscheidung geraten.
# Gezaehlt werden ALLE Aufrufe, auch der Wiederholversuch nach einer leeren
# Antwort - der kostet echtes Geld und ist genau die Verschwendung, die man
# sehen will (v230ay: ein ganzer Aufruf umsonst, weil das Budget zu klein war).
AI_VERBRAUCH = {'calls': 0, 'in': 0, 'out': 0, 'denken': 0, 'audio_s': 0.0,
                'modelle': {}}


def ai_verbrauch_zaehlen(model, usage):
    """Tokens einer Antwort aufaddieren. Scheitert IMMER leise - eine
    Buchhaltung darf nie einen Render reissen."""
    try:
        u = usage or {}
        det = u.get('completion_tokens_details') or {}
        AI_VERBRAUCH['calls'] += 1
        AI_VERBRAUCH['in'] += int(u.get('prompt_tokens') or 0)
        AI_VERBRAUCH['out'] += int(u.get('completion_tokens') or 0)
        AI_VERBRAUCH['denken'] += int(det.get('reasoning_tokens') or 0)
        m = str(model or '?')[:40]
        AI_VERBRAUCH['modelle'][m] = AI_VERBRAUCH['modelle'].get(m, 0) + 1
    except Exception:
        pass


def ai_verbrauch_zeile():
    """Eine Zeile fuer den Job-Log. ENGLISCH, sie landet beim Kunden (v148).
    Bewusst nur TOKENS und Minuten - was das in Euro ist, haengt an Preisen,
    die sich aendern, und die gehoeren an EINE Stelle (Server/Panel), nicht
    in jeden Render."""
    a = AI_VERBRAUCH
    if not a['calls'] and a['audio_s'] <= 0:
        return ''
    t = []
    if a['calls']:
        t.append(f"{a['calls']} calls, {a['in']} in + {a['out']} out tokens"
                 + (f" (thereof {a['denken']} thinking)" if a['denken'] else ''))
    if a['audio_s'] > 0:
        t.append(f"{a['audio_s'] / 60.0:.2f} min transcription")
    if a['modelle']:
        t.append('model ' + ', '.join(sorted(a['modelle'])))
    return 'AI usage: ' + ' | '.join(t)


def zeit_report(gesamt):
    """Eine Zeile, absteigend nach Kosten. 'rest' ist alles Ungemessene -
    ist der gross, ist die Messung selbst unvollstaendig und sagt das."""
    if not _ZEIT:
        return ''
    _w = dict(_ZEIT)
    for _p, _kinder in _ZEIT_KIND.items():
        if _p in _w:
            _w[_p] = max(_w[_p] - sum(_w.get(_k, 0.0) for _k in _kinder), 0.0)
    _s = sorted(_w.items(), key=lambda kv: -kv[1])
    _rest = max(gesamt - sum(v for _, v in _s), 0.0)
    _teile = [f"{k} {v:.1f}s ({v / max(gesamt, 1e-6) * 100:.0f}%)"
              for k, v in _s if v >= 0.05]
    _teile.append(f"other {_rest:.1f}s ({_rest / max(gesamt, 1e-6) * 100:.0f}%)")
    return f"Timing (total {gesamt:.1f}s): " + ' | '.join(_teile)


MODEL_URLS = {
    'models/rvm.onnx': 'https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx',
    'models/face.tflite': 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
    'models/depth.onnx': 'https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx',
    # v101j Hand-Kontakt: Fingerspitzen-Erkennung (Impulse + Occlusion)
    'models/hand.task': 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
}

# ---------------------------------------------------------------- helpers
MODEL_MIN_BYTES = {'models/rvm.onnx': 10_000_000,
                   'models/face.tflite': 100_000,
                   'models/depth.onnx': 80_000_000,
                   'models/hand.task': 5_000_000}

# v230ax: Fingerabdruck jeder Modelldatei. Eine Groessenpruefung faengt nur
# den abgebrochenen Download; sie sagt NICHTS darueber, ob die Datei noch
# dieselbe ist. Die Werte sind nachgemessen: am 05.08.2026 frisch von der
# Quelle geladen und mit der Datei im Repo verglichen, beide identisch.
MODEL_SHA256 = {
    'models/rvm.onnx':
        '88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828',
    'models/face.tflite':
        'b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f',
    'models/hand.task':
        'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1',
}

# Was NICHT geprueft wird, und warum - ein leerer Eintrag waere derselbe
# stille Wegfall wie v230f. Wer ein Modell ergaenzt, traegt es entweder oben
# mit Fingerabdruck ein oder hier mit Begruendung; der Selftest faellt sonst.
MODEL_UNPINNED = {
    'models/depth.onnx':
        'Die Adresse zeigt auf resolve/main, also auf einen beweglichen '
        'Stand - ein Fingerabdruck von heute wuerde beim naechsten Upload '
        'der Gegenseite den Build blockieren. Ausserdem war die Quelle von '
        'der Testumgebung aus nicht erreichbar (403 ueber den Proxy), der '
        'Wert liesse sich hier gar nicht ehrlich messen.',
}


def _modell_pruefen(rel, path, loeschen=True):
    """Stimmt der Fingerabdruck? Bei Abweichung fliegt die frisch geladene
    Datei weg und der Lauf bricht ab - eine unbekannte Modelldatei
    weiterzubenutzen waere das Gegenteil von dem, wofuer die Pruefung da ist.
    `loeschen=False` fuer eine Datei, die schon lag: dort ist die Abweichung
    eine Meldung, kein Grund, den Betrieb anzuhalten."""
    soll = MODEL_SHA256.get(rel)
    if not soll:
        return
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for stueck in iter(lambda: fh.read(1 << 20), b''):
            h.update(stueck)
    ist = h.hexdigest()
    if ist != soll:
        if loeschen:
            try:
                os.remove(path)
            except OSError:
                pass
        raise RuntimeError(
            f'ERROR: checksum mismatch for {rel}.\n'
            f'  expected {soll}\n'
            f'  got      {ist}\n'
            f'  The downloaded model file is not the one this build was '
            f'tested with. It has been deleted. Do not re-run blindly: '
            f'check MODEL_URLS and MODEL_SHA256 in render.py.')


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
            # v230ax: Eine Datei, die schon da ist, wird geprueft aber nicht
            # zum Abbruch gemacht. Der Angriff, gegen den der Fingerabdruck
            # gebaut ist, passiert beim LADEN; wer schon auf die Platte des
            # Containers schreiben kann, hat ohnehin gewonnen. Haerter zu
            # sein hiesse: ein zu alter Pin legt den Betrieb still.
            try:
                _modell_pruefen(rel, path, loeschen=False)
            except RuntimeError as e:
                print(f'WARNING: {rel} does not match its pinned checksum - '
                      f'keeping it, but this needs a look.\n{e}')
            continue
        if os.path.exists(path):
            print(f"  {rel} is incomplete - downloading again")
            os.remove(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = path + '.part'
        print(f"Downloading {rel} ...")
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
                # v230ax: Die Groesse sagt nur, dass etwas ankam. Erst der
                # Fingerabdruck sagt, dass es DIESE Datei ist. Ein Fehler
                # hier ist KEIN Netzproblem und darf nicht in die
                # Wiederholschleife - sonst laedt sie fuenfmal dasselbe.
                _modell_pruefen(rel, path)
                break
            except RuntimeError:
                raise
            except Exception as e:
                print(f"\n  Aborted ({type(e).__name__}) - attempt {versuch}/5, "
                      f"mache bei {have / 1e6:.0f} MB ...")
                time.sleep(2 * versuch)
        else:
            raise RuntimeError(
                f"Download von {rel} nach 5 Versuchen fehlgeschlagen.\n"
                f"  Datei manuell laden: {url}\n"
                f"  und ablegen unter:   {path}")

def vorschau_schreiben(comp, pfad, breite=360):
    """v230b3: legt das GERADE FERTIGE Bild klein neben das Ergebnis, damit
    der Kunde beim Rendern sieht, was entsteht - eine Prozentzahl ist bei
    einem Vorgang von Minuten wenig.

    Zwei Dinge, die man hier falsch machen kann:
      * Direkt auf die Zieldatei schreiben. Die App liest sie im Sekundentakt
        und bekaeme irgendwann ein halbes JPEG. Also Zwischendatei plus
        `os.replace` - und der Name traegt die Prozessnummer, sonst
        loeschen sich zwei Laeufe gegenseitig die halbfertige Datei
        (derselbe Wettlauf wie v230w bei der Sicherung).
      * Den Render kippen lassen. Ein Vorschaubild ist Beiwerk; scheitert
        es, laeuft der Render weiter und der Kunde sieht eben kein Bild.
    Rueckgabe: True, wenn ein Bild liegt."""
    try:
        b = np.clip(comp, 0, 255).astype(np.uint8)
        h, w = b.shape[:2]
        s = float(breite) / max(w, 1)
        if s < 1.0:
            b = cv2.resize(b, (int(breite), max(1, int(h * s))),
                           interpolation=cv2.INTER_AREA)
        # Die Endung MUSS .jpg bleiben: cv2.imwrite waehlt den Codec ueber
        # die Dateiendung und bricht bei '.tmp' mit "could not find a writer"
        # ab (beim ersten echten Aufruf sofort aufgefallen - der Grund, warum
        # diese Zeilen jetzt eine eigene, testbare Funktion sind).
        tmp = f'{pfad}.{os.getpid()}.tmp.jpg'
        if cv2.imwrite(tmp, b, [int(cv2.IMWRITE_JPEG_QUALITY), 72]):
            os.replace(tmp, pfad)
            return True
    except Exception:
        pass
    return False


def ensure_models_cli():
    """Fuer den Image-Bau. Der Aufruf dort ist absichtlich fehlertolerant -
    ein Netzhaenger beim Bauen soll den Deploy nicht kippen, die Modelle
    kommen dann zur Laufzeit. Ein FALSCHER FINGERABDRUCK ist aber kein
    Netzhaenger: der muss den Bau anhalten, sonst wird genau die Meldung
    verschluckt, wegen der es die Pruefung gibt. Darum zwei Ausgaenge -
    9 = Fingerabdruck stimmt nicht, 0 = alles andere."""
    import sys as _s
    try:
        ensure_models()
    except Exception as e:
        if 'checksum mismatch' in str(e):
            print(str(e))
            _s.exit(9)
        print(f'WARNING: models not fetched at build time ({e}) - '
              f'they will be downloaded on first use.')
    _s.exit(0)


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


def _norm_txt(s):
    """Vergleichsform fuer Blocktexte (v230g): Gross-/Kleinschreibung,
    Mehrfach-Leerzeichen und Satzzeichen sind kein 'der Nutzer hat den Text
    geaendert'. Nur ein echter Wortlaut-Unterschied zaehlt."""
    import re as _re
    return _re.sub(r'[^a-z0-9äöüß]+', ' ', str(s or '').lower()).strip()

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

# v230ay: Anzeigenamen fuer den Job-Log. Die Kennungen oben sind Code und
# bleiben deutsch (sie stehen in Config, Cache und Sidecar-Dateien); der Log
# landet beim Kunden und muss englisch sein (v148). Wer eine Animation
# ergaenzt, traegt sie hier ein - der Selftest faellt sonst.
ANIM_EN = {
    'glitch': 'glitch', 'puls': 'pulse', 'welle': 'wave', 'zittern': 'jitter',
    'neon': 'neon', 'schub': 'thrust', 'bruch': 'shatter', 'sturz': 'drop',
    'anstieg': 'rise', 'wende': 'flip', 'druck': 'squash', 'schwund': 'fade',
    'knall': 'bang', 'gewicht': 'weight', 'schweben': 'float',
    'fokus': 'focus', 'enthuellen': 'reveal', 'spur': 'trail',
    'kippen': 'tilt', 'explosion': 'explode', 'magnet': 'magnet',
    'wackel': 'wobble', 'regen': 'rain', 'zoom_punch': 'zoom punch',
    'rutsche': 'slide', 'stempel': 'stamp',
}


def anim_en(name):
    """Anzeigename einer Animation. Unbekanntes wird durchgereicht, nicht
    verschluckt - ein leeres Feld im Log waere schlimmer als ein deutsches
    Wort (v230f)."""
    return ANIM_EN.get(name, name)

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
    # v194 STUFENLOS. Bis v193 war der Kernel eine ungerade GANZE Zahl:
    #   k = max(int(round(abs(amt) * 4)) | 1, 3)
    # Damit lieferte die ganze Spanne amt = 0.06 bis 0.87 denselben Kernel 3,
    # und der "atmende" Strich war in Wahrheit eine STATISCHE Verdickung.
    # Gemessen am Sprite: Strichbreite 1.177x fuer Bass 0.0 bis 0.8, erst bei
    # Bass 1.0 sprang sie auf 1.257x. Ein Regler, der ueber 80 % seines
    # Bereichs nichts tut, ist kein Regler.
    # Jetzt wird zwischen den beiden benachbarten Kernelgroessen GEMISCHT -
    # dazwischen liegende Werte ergeben eine echte Zwischenstufe.
    roh = max(abs(amt) * 4.0, 1.0)
    # k_lo muss die groesste UNGERADE Zahl <= roh sein. 'floor(roh) | 1'
    # rundet bei geraden Werten nach OBEN (2 -> 3) und liegt dann ueber roh -
    # die Mischung wird negativ und wieder auf 0 geklemmt, also blieb eine
    # Stufe stehen (gemessen: Bass 0.4 bis 0.8 wieder identisch).
    k_lo = int(math.floor(roh))
    if k_lo % 2 == 0:
        k_lo -= 1
    k_lo = max(k_lo, 1)
    k_hi = k_lo + 2
    misch = max(0.0, min(1.0, (roh - k_lo) / 2.0))
    out = arr.copy()

    def _morph(kanal, k):
        if k <= 1:
            return kanal
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        return (cv2.dilate(kanal, ker) if amt > 0 else cv2.erode(kanal, ker))

    a_lo = _morph(arr[..., 3], k_lo).astype(np.float32)
    a_hi = _morph(arr[..., 3], k_hi).astype(np.float32)
    out[..., 3] = np.clip(a_lo * (1.0 - misch) + a_hi * misch,
                          0, 255).astype(arr.dtype)
    if amt > 0:
        c_lo = _morph(arr[..., :3], k_lo).astype(np.float32)
        c_hi = _morph(arr[..., :3], k_hi).astype(np.float32)
        out[..., :3] = np.clip(c_lo * (1.0 - misch) + c_hi * misch,
                               0, 255).astype(arr.dtype)
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


# v230ag SCHRIFT-RUECKFALL FUER FREMDE SCHRIFTSYSTEME.
# Die Landing Page versprach "50+ languages" - gemessen konnte KEINE der
# Hausschriften Chinesisch, Japanisch, Koreanisch, Kyrillisch oder Griechisch
# darstellen: Whisper haette sauber transkribiert, im Bild waeren leere
# Kaesten gestanden. Jetzt liegt fuer jedes unterstuetzte Schriftsystem eine
# Noto-Schrift bei (OFL, siehe fonts/noto/LIZENZ.txt); fehlt ein Zeichen in
# der gewaehlten Schrift, uebernimmt sie den ganzen Textblock - eine Zeile in
# zwei Schriften saehe schlimmer aus als ein neutraler Schnitt.
# BEWUSSTE GRENZE: Arabisch, Hebraeisch, Devanagari und Thai sind NICHT
# dabei. Der Zeichenpfad setzt jeden Buchstaben EINZELN (fuer Schatten,
# Extrusion und Buchstaben-Boxen); verbundene Schriften und Rechts-nach-links
# brauchen aber den ganzen String am Stueck. Die Schrift mitzuliefern wuerde
# nur Buchstaben zeigen, die in falscher Form und Reihenfolge dastehen - das
# waere schlimmer als eine ehrliche Absage.
_NOTO_DIR = os.path.join(HERE, 'fonts', 'noto')
_NOTO_FUER = (                       # (Pruefzeichen, Datei) - Reihenfolge zaehlt
    ('kana', 'あア', 'noto_jp.ttf'),      # Hiragana/Katakana -> Japanisch
    ('hangul', '가한', 'noto_kr.ttf'),    # Hangul -> Koreanisch
    ('han', '中文', 'noto_sc.ttf'),       # Han -> Chinesisch (verein.)
    ('kyrillisch', 'Ая', 'noto_sans.ttf'),
    ('griechisch', 'Αω', 'noto_sans.ttf'),
    # Vietnamesisch: Doppel-Diakritika (Ạ, ế, ữ) liegen in "Latein
    # erweitert zusaetzlich" und fehlen JEDER Hausschrift. Als Block
    # gefuehrt, damit es auch ohne fontTools erkannt wird.
    ('vietnamesisch', 'ạ', 'noto_sans.ttf'),
)
_NOTO_NICHT = (                      # erkannt, aber bewusst nicht unterstuetzt
    ('Arabisch', '؀', 'ۿ'), ('Hebraeisch', '֐', '׿'),
    ('Devanagari', 'ऀ', 'ॿ'), ('Thai', '฀', '๿'),
)
_CMAP_CACHE = {}
_SCRIPT_GEMELDET = set()


def _font_kann(pfad, txt):
    """Deckt die Schrift JEDES Zeichen ab? Leerzeichen zaehlen nicht."""
    cm = _CMAP_CACHE.get(pfad)
    if cm is None:
        try:
            from fontTools.ttLib import TTFont
            tt = TTFont(pfad, fontNumber=0, lazy=True)
            cm = set()
            for t in tt['cmap'].tables:
                cm |= set(t.cmap.keys())
            tt.close()
        except Exception:
            cm = set()
        _CMAP_CACHE[pfad] = cm
    if not cm:
        return True                  # unlesbare Schrift: nicht auch noch tauschen
    return all(ord(c) in cm for c in txt if not c.isspace())


def script_font(txt, font):
    """Schrift fuer diesen Text. Deckt die gewuenschte Schrift alles ab, bleibt
    sie stehen (der Look eines lateinischen Videos aendert sich NIE). Sonst die
    passende Noto-Schrift; gibt es keine, bleibt es beim Original und der
    Job-Log nennt das Schriftsystem beim Namen - stumme Kaesten sind der
    schlimmste Ausgang."""
    if not txt or not font:
        return font
    # Zuerst die BLOECKE, dann die Zeichentabelle. Die Blockfrage braucht kein
    # zusaetzliches Paket: faellt fontTools aus, wuerde `_font_kann` alles
    # durchwinken und wir stuenden wieder bei leeren Kaesten - ein stiller
    # Rueckfall, der ein Feature abschaltet (v210-Falle). Chinesisch,
    # Japanisch, Koreanisch, Kyrillisch und Griechisch sind an ihren Bloecken
    # eindeutig zu erkennen, dafuer ist keine Messung noetig.
    _fremd = any(_zeichen_in(txt, p) for _n, proben, _d in _NOTO_FUER
                 for p in proben)
    if not _fremd:
        try:
            if _font_kann(font, txt):
                return font
        except Exception:
            return font
    for name, proben, datei in _NOTO_FUER:
        if not any(_zeichen_in(txt, p) for p in proben):
            continue
        pfad = os.path.join(_NOTO_DIR, datei)
        if not os.path.exists(pfad):
            break
        if not _font_kann(pfad, txt) and datei == 'noto_sc.ttf':
            alt = os.path.join(_NOTO_DIR, 'noto_tc.ttf')   # traditionelle Zeichen
            if os.path.exists(alt) and _font_kann(alt, txt):
                pfad = alt
        if name not in _SCRIPT_GEMELDET:
            _SCRIPT_GEMELDET.add(name)
            print(f'Font: {name} detected - using {os.path.basename(pfad)}')
        return pfad
    for name, a, b in _NOTO_NICHT:
        if any(a <= c <= b for c in txt):
            if name not in _SCRIPT_GEMELDET:
                _SCRIPT_GEMELDET.add(name)
                print(f'WARNING: {name} script is not supported yet - '
                      f'captions may be unreadable.')
            break
    else:
        # Auch LATEINISCH kann fehlen: die Hausschriften kennen die
        # vietnamesischen Doppel-Diakritika (Ạ, ế, ữ) nicht, und ein
        # fehlendes Zeichen ist ein leerer Kasten mitten im Wort - der Test
        # hat genau das gefangen. Noto Sans deckt Latein erweitert ab.
        breit = os.path.join(_NOTO_DIR, 'noto_sans.ttf')
        if os.path.exists(breit) and _font_kann(breit, txt):
            if 'latein_plus' not in _SCRIPT_GEMELDET:
                _SCRIPT_GEMELDET.add('latein_plus')
                print('Font: characters missing in the look font - '
                      'using noto_sans.ttf')
            return breit
    return font


def schrift_unsupported(txt, anteil=0.40):
    """Name des Schriftsystems, wenn der Text ueberwiegend eines benutzt, das
    wir NICHT setzen koennen - sonst None. Ein einzelnes fremdes Zeichen (ein
    Name, ein Zitat) bricht nichts ab; erst ab `anteil` der Buchstaben ist es
    die Sprache des Videos."""
    zeichen = [c for c in (txt or '') if not c.isspace()]
    if not zeichen:
        return None
    for name, a, b in _NOTO_NICHT:
        n = sum(1 for c in zeichen if a <= c <= b)
        if n and n / len(zeichen) >= anteil:
            return name
    return None


def _zeichen_in(txt, probe):
    """Kommt ein Zeichen aus demselben Block wie `probe` im Text vor?"""
    lo, hi = _BLOCK.get(probe, (probe, probe))
    return any(lo <= c <= hi for c in txt)


_BLOCK = {                            # Pruefzeichen -> Unicode-Block
    'あ': ('぀', 'ゟ'), 'ア': ('゠', 'ヿ'),
    '가': ('가', '힯'), '한': ('ᄀ', 'ᇿ'),
    '中': ('一', '鿿'), '文': ('㐀', '䶿'),
    'А': ('Ѐ', 'ӿ'), 'я': ('Ԁ', 'ԯ'),
    'Α': ('Ͱ', 'Ͽ'), 'ω': ('ἀ', '῿'),
    'ạ': ('Ḁ', 'ỿ'),                    # Latein erweitert zusaetzlich
}


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
        # v100: Ein Glitch dauert 2-4 Frames und klingt AB, dazu RGB-Split -
        # der 1-Frame-Zufallsversatz wirkte wie ein Bug, nicht wie Absicht.
        g = p.setdefault('_gl', 0.0)
        _pt = p.get('_gl_t', dt)
        _st = dt - _pt if 0.0 < dt - _pt < 0.2 else (1.0 / 30.0)
        p['_gl_t'] = dt
        g = max(a_onset if a_onset > 0.5 else 0.0, g * (0.55 ** (_st * 30.0)))
        p['_gl'] = g
        if g > 0.08:
            arr = glitch_arr(base, rng, g)
            off = max(int(round(3 * g)), 1)
            spl = arr.copy()
            spl[..., 0] = np.roll(arr[..., 0], off, axis=1)
            spl[..., 2] = np.roll(arr[..., 2], -off, axis=1)
            arr = spl
            dx = (float(rng.random()) - 0.5) * 8 * g
    elif a == 'puls':                       # atmet auf dem Bass
        # v100: Envelope-Follower (schneller Attack, traeger Release) statt
        # rohem Bass-Wert - das rohe Mapping zappelte mit jedem Frame.
        # Ein Puls ATMET: zieht schnell an, laesst weich los.
        env = p.setdefault('_puls', 0.0)
        _pt = p.get('_puls_t', dt)
        _st = dt - _pt if 0.0 < dt - _pt < 0.2 else (1.0 / 30.0)
        p['_puls_t'] = dt
        if a_bass > env:
            env = min(env + (a_bass - env) * min(_st * 18.0, 1.0), 1.0)
        else:
            env *= 0.82 ** (_st * 30.0)
        p['_puls'] = env
        e = env * env * (3 - 2 * env)
        sc = 1.0 + 0.065 * e
        dy = -base.shape[0] * 0.012 * e     # hebt minimal mit: atmen, nicht springen
    elif a == 'welle':                      # Woge laeuft durch die Buchstaben
        # v100: Die Woge SETZT sich (volle Amplitude nur ~1.2s, dann 36%
        # Restschwingen) und traegt eine Oberwelle (2.7x, 30%) - der nackte
        # Endlos-Sinus war als Loop erkennbar.
        h, w = base.shape[:2]
        ph = dt * 2.6
        settle = 0.36 + 0.64 * math.exp(-max(dt - 0.15, 0.0) * 1.6)
        amp = h * 0.055 * (0.45 + 0.55 * a_rms) * settle
        ys = np.arange(h, dtype=np.float32)
        shift = (amp * np.sin(ys / max(h, 1) * 5.0 + ph)
                 + amp * 0.30 * np.sin(ys / max(h, 1) * 13.5 - ph * 1.7))
        xs = np.arange(w, dtype=np.float32)
        M = np.zeros((h, w, 2), np.float32)
        M[..., 0] = xs[None, :] + shift[:, None]
        M[..., 1] = ys[:, None]
        arr = cv2.remap(base, M, None, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    elif a == 'zittern':                    # nervoese Energie, Shake auf Onsets
        # v100: Tremor statt Weissrauschen. Jeder Frame neuer Zufall liest
        # sich als Renderfehler; echtes Zittern sind zwei ueberlagerte
        # Frequenzen mit Wort-eigener Phase, ein Onset-Kick der AUSKLINGT
        # und 0.8 Grad Mikro-Rotation.
        ph = hand_jitter(p.get('kw_i', 0)) * 10.0
        kick = p.setdefault('_zit', 0.0)
        _pt = p.get('_zit_t', dt)
        _st = dt - _pt if 0.0 < dt - _pt < 0.2 else (1.0 / 30.0)
        p['_zit_t'] = dt
        kick = max(a_onset, kick * (0.78 ** (_st * 30.0)))
        p['_zit'] = kick
        k = 0.45 + 0.9 * kick
        dx = (math.sin(dt * 39.0 + ph) + 0.5 * math.sin(dt * 61.0 + ph * 1.7)) * 3.2 * k
        dy = (math.cos(dt * 47.0 + ph * 0.6) + 0.5 * math.sin(dt * 71.0 + ph)) * 2.6 * k
        arr = rot_img(base, 0.8 * math.sin(dt * 33.0 + ph) * k)
    elif a == 'neon':                       # Leuchtreklame: glimmt und flackert
        # v100: Echte Roehre - sie ZUENDET (drei kurze Stotter, dann an),
        # flackert danach selten und nur auf 0.78 (kein Vollbild-Strobo mit
        # Zufalls-Tiefe), und der Glow atmet mit der Stimme und dem Zuend-
        # Zustand mit.
        ph = hand_jitter(p.get('kw_i', 0))
        f = 1.0
        if dt < 0.34:
            f = 0.28
            for i0, z in enumerate((0.05, 0.16, 0.26)):
                if z <= dt < z + 0.045 + 0.02 * i0:
                    f = 0.85 + 0.15 * (i0 / 2.0)
            if dt >= 0.30:
                f = 1.0
        elif math.sin(dt * 7.3 + ph * 9.0) > 0.997:
            f = 0.78
        op = f * (0.90 + 0.10 * a_rms)
        arr = base.copy()
        glow = cv2.GaussianBlur(base[..., :3].astype(np.float32), (0, 0), 7) \
            * (0.42 + 0.5 * a_rms) * (0.55 + 0.45 * f)
        arr[..., :3] = np.clip(base[..., :3].astype(np.float32) * 0.85 + glow,
                               0, 255).astype(base.dtype)
    elif a == 'schub':                      # Druck nach vorn auf jedem Beat
        # v100: sitzt auf ECHTEN Akzenten (Onset/Bass-Follower) statt auf
        # einem festen 0.66s-Metronom - mechanische Perioden ohne Bezug zur
        # Stimme sind sofort als billig erkennbar.
        env = p.setdefault('_schub', 0.0)
        _pt = p.get('_schub_t', dt)
        _st = dt - _pt if 0.0 < dt - _pt < 0.2 else (1.0 / 30.0)
        p['_schub_t'] = dt
        env = max(max(a_onset, a_bass * 0.55), env * (0.80 ** (_st * 30.0)))
        p['_schub'] = env
        e = env * env
        sc = 1.0 + 0.085 * e
        dy = -base.shape[0] * 0.05 * e
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
        # v100: Physik in drei Akten - Anticipation (kurz Luft holen), dann
        # beschleunigter Fall mit Rotation, dann AUFPRALL: Squash, kurzes
        # Nachfedern, steht. Vorher fiel das Wort ins Nichts und blieb 70%
        # transparent in der Luft haengen - kein Ende, kein Gewicht.
        h = base.shape[0]
        drop = h * 0.30
        rot = 0.0
        if dt < 0.10:
            dy = -h * 0.035 * smoothstep(dt / 0.10)
        elif dt < 0.42:
            f = (dt - 0.10) / 0.32
            dy = -h * 0.035 + (drop + h * 0.035) * f * f
            dx = -h * 0.04 * f
            rot = -5.0 * f
        else:
            k = min((dt - 0.42) / 0.30, 1.0)
            rb = math.exp(-k * 6.0) * math.cos(k * 18.0)
            dy = drop - h * 0.04 * max(rb, 0.0)
            dx = -h * 0.04
            rot = -5.0 * math.exp(-k * 5.0)
            sq = math.exp(-k * 9.0) * 0.10
            if sq > 0.01:
                arr = cv2.resize(base, (int(base.shape[1] * (1 + sq * 0.5)),
                                        max(int(h * (1.0 - sq)), 2)),
                                 interpolation=cv2.INTER_LINEAR)
        if abs(rot) > 0.05:
            arr = rot_img(arr if arr is not base else base, rot)
    elif a == 'anstieg':                    # steigt: Rekord, Gewinn, Zuwachs, Hoch
        # v100: Feder statt ease_out - steigt zuegig, schiesst ueber und
        # setzt sich; waehrend der Bewegung leicht vertikal gestreckt
        # (Squash & Stretch), im Stand exakt 1.0. Das flache Gleiten ohne
        # Overshoot war leblos.
        e = spring(min(dt / 0.55, 1.6), freq=2.3, damp=5.6)
        dy = -base.shape[0] * 0.24 * e
        vel = abs(e - p.get('_anst', e))
        p['_anst'] = e
        stretch = min(vel * 6.0, 0.10)
        if stretch > 0.01:
            h, w = base.shape[:2]
            arr = cv2.resize(base, (max(int(w * (1 - stretch * 0.4)), 2),
                                    max(int(h * (1 + stretch)), 2)),
                             interpolation=cv2.INTER_LINEAR)
        sc = 1.0 + 0.05 * min(e, 1.0)
    elif a == 'wende':                      # kippt um: Wende, Umkehr, Gegenteil
        # v100: Asymmetrisch wie eine Entscheidung - reisst schnell auf
        # (quint), federt mit ~8 Grad Overshoot zurueck; am Steilpunkt dimmt
        # das Licht und das Wort weicht minimal zurueck (Tiefe). Der
        # symmetrische Sinus war eine Fahne im Wind.
        if dt < 0.22:
            ang = 1.05 * (1.0 - (1.0 - dt / 0.22) ** 5)
        else:
            ang = 1.05 * (1.0 - spring(min((dt - 0.22) / 0.55, 1.4),
                                       freq=2.4, damp=5.2))
        arr, _px, _py = _persp3d(base, 0.0, ang, 0.18)
        k_edge = min(abs(ang) / 1.05, 1.0)
        op = 1.0 - 0.10 * k_edge
        sc = 1.0 - 0.05 * k_edge
    elif a == 'druck':                       # wird erdrueckt: Last, Zwang, Belastung
        # v100: Last hat GEWICHT - sie faellt drauf (ease-in), staucht ueber
        # das Ziel hinaus und federt gedaempft zurueck. Der lineare
        # Dauer-Squash sah aus wie ein Skalierungs-Regler, nicht wie Druck.
        target = 0.16 * (0.6 + 0.4 * a_rms)
        if dt < 0.22:
            sq = target * (dt / 0.22) ** 3
        else:
            k = min((dt - 0.22) / 0.45, 1.0)
            sq = target * (1.0 + 0.35 * math.exp(-k * 5.0) * math.cos(k * 14.0))
        sq = max(sq, 0.0)
        h, w = base.shape[:2]
        arr = cv2.resize(base, (int(w * (1 + sq * 0.45)), max(int(h * (1 - sq)), 2)),
                         interpolation=cv2.INTER_LINEAR)
        dy = h * sq * 0.55
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
            # v194: DER BODEN MUSSTE WEG. Bis v193 stand hier
            #   alpha = base_alpha * (0.42 + 0.58 * keep)
            # und damit fror das Wort bei 42 % Deckkraft ein - fuer immer.
            # Gemessen: 41.8 % Restdeckkraft noch bei t = 6 s. Eine Animation,
            # die "Fade (dissolves)" heisst und das Wort dauerhaft halb
            # sichtbar stehen laesst, loest sich nicht auf, sie wird blass.
            # Die Regie waehlt sie fuer Woerter wie weg/verloren/vorbei -
            # dort ist Verschwinden die ganze Aussage.
            arr[..., 3] = (base[..., 3].astype(np.float32)
                           * keep).astype(base.dtype)
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
        # v194: Der Scharfzug war nach 0.10 s vorbei - bei 30 fps drei Bilder,
        # und die beiden unschaerfsten davon standen bei 20 % bzw. 50 %
        # Deckkraft, waren also praktisch nicht im Bild. Gemessen sprang die
        # Kantenschaerfe zwischen t = 0.05 und t = 0.10 von 1.8 auf 1075.
        # Ursache war spring(): mit freq 1.8 erreicht die Feder ihr Ziel beim
        # ersten Kosinus-Nulldurchgang, also schon bei x = 0.28 -> dt = 0.10 s.
        # Fuer einen Rack Focus ist eine Feder ohnehin falsch, die Schaerfe
        # soll sich SETZEN, nicht ueberschwingen. Jetzt monoton ueber 0.42 s,
        # und die Blende ist vorher fertig (0.06 s), damit die unscharfe
        # Phase wirklich zu sehen ist.
        e = smoothstep(min(dt / 0.42, 1.0))
        blur = (1.0 - e) * min(base.shape[0], base.shape[1]) * 0.09
        if blur > 0.6:
            arr = cv2.GaussianBlur(base, (0, 0), blur)
        sc = 1.055 - 0.055 * e
        op = min(dt / 0.06, 1.0)

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
        # v194: Die Kippung war nach 0.10 s vorbei - bei 30 fps sind das DREI
        # Bilder, das liest niemand als "klappt nach vorn". Ursache war nicht
        # die Daempfung, sondern die FREQUENZ: spring() erreicht 1.0 beim
        # ersten Nulldurchgang des Kosinus, also bei x = 1/(2*freq) = 0.238.
        # Mit der alten Zeitbasis 0.50 s lag der genau bei dt = 0.12 s.
        # Zeitbasis 1.40 s schiebt ihn auf dt = 0.33 s - dieselbe Groessen-
        # ordnung wie 'wende' (0.40 s), das man klar als Drehung liest.
        e = spring(min(dt / 1.40, 1.4), freq=2.1, damp=4.0)
        tilt = -0.85 * (1.0 - min(e, 1.0))    # startet stark tilted, geht auf 0
        # v194: DIE ACHSEN WAREN VERTAUSCHT. _persp3d(arr, ax, ay) dreht mit
        # ax um die QUERachse (nach vorn kippen) und mit ay um die HOCHachse
        # (umblaettern). Uebergeben wurde tilt als ay - also drehte 'kippen'
        # um die Hochachse und war damit dieselbe Bewegung wie 'wende'.
        # Der eigene Kommentar direkt darueber sagt seit je "Tilt um X-Achse:
        # obere Kante entfernt sich, untere kommt entgegen" - die Absicht war
        # klar, nur das Argument sass an der falschen Stelle.
        arr, _px, _py = _persp3d(base, tilt, 0.0, 0.14)
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
                # v100: Streu-Richtung deterministisch verwuerfelt statt
                # strengem Auf/Ab im Spalten-Takt (das Parity-Zickzack war
                # als Muster lesbar - Explosionen sind Chaos).
                jit = ((((i + 1) * 2654435761) >> 3) & 1023) / 1023.0 - 0.5
                dx_s = int(cx / (w / 2) * (w * 0.48) * spread
                           * (1.0 + 0.25 * jit))
                dy_s = int((abs(cx) / (w / 2)) * (h * 0.26) * spread
                           * (jit * 2.0))
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
        wl = math.sin(dt * 12.0)
        dy = amp * (wl + 0.30 * math.sin(dt * 20.4 + ph))
        # v194 SQUASH & STRETCH. Bis v193 stand hier nur ein GLEICHFOERMIGER
        # Skalen-Puls von 1.5 % - das ist ein Groessen-Zappeln, kein Cartoon.
        # Squash und Stretch sind die erste der 12 Disney-Regeln und genau
        # das, was "Wobble (cartoon bounce)" verspricht: unten breit und
        # flach (Aufprall), in der Bewegung schmal und hoch (Streckung).
        # Deshalb GEGENLAEUFIG auf beiden Achsen und an den Umkehrpunkt der
        # Bewegung gekoppelt (wl, nicht 90 Grad daneben), und volumen-
        # erhaltend: was in der Breite dazukommt, geht in der Hoehe ab.
        q = 0.055 * wl
        arr = cv2.resize(base,
                         (max(int(base.shape[1] * (1.0 + q)), 2),
                          max(int(base.shape[0] * (1.0 - q)), 2)),
                         interpolation=cv2.INTER_LINEAR)

    elif a == 'regen':                        # Buchstaben-Streifen fallen von oben nacheinander
        h, w = base.shape[:2]
        n_col = max(int(w / 34), 4)
        cw = max(w // n_col, 6)
        # v194: SYMMETRISCH polstern. Bis v193 wuchs die Leinwand nur UNTEN
        # (h + pad_y). Das Wort landete am Ende bei y_off = 0, also am OBEREN
        # Rand der Leinwand - und weil der Zeichenpfad das Sprite mittig
        # setzt, sass der fertige Text danach dauerhaft pad_y/2 zu hoch.
        # Gemessen: 53 px bei einem 178 px hohen Wort, also 30 % seiner Hoehe.
        # Die Platzierungs-Regie hatte die Stelle vorher genau berechnet
        # (Gesichtsbox, Title-Safe, Plattform-Maske) - diese Verschiebung
        # hebelte das aus. explosion/magnet polstern seit je symmetrisch,
        # deshalb sitzen sie richtig; das hier ist dieselbe Bauweise.
        pad_y = int(h * 0.55) + 8
        out = np.zeros((h + 2 * pad_y, w, 4), base.dtype)
        for i in range(n_col):
            x0 = i * cw
            x1 = min(x0 + cw, w)
            # v100: Staffelung deterministisch VERWUERFELT (lineares
            # links-nach-rechts war ein sichtbares Muster), Fall mit echter
            # Gravitation (x^2 statt ease_out = weiche Landung) und einem
            # kleinen Bounce beim Aufschlag - Regen SCHLAEGT auf.
            jit = ((i * 2654435761) & 1023) / 1023.0
            offset = 0.17 * (i / max(n_col - 1, 1)) + 0.13 * jit
            x = min(max((dt - offset) / 0.5, 0.0), 1.5)
            if x <= 0.0:
                continue
            fall = min(x, 1.0) ** 2
            bounce = 0.0
            if x > 1.0:
                bounce = math.exp(-(x - 1.0) * 6.0) * math.sin((x - 1.0) * 22.0) * 0.05
            # v194: Die Ruhelage ist jetzt y_off = pad_y (Mitte der Leinwand),
            # der Start liegt DARUEBER bei y_off = 0. Damit faellt der Streifen
            # wirklich von oben herab, statt wie bis v193 von unten
            # heraufzusteigen - gemessen war die Bewegung genau andersherum
            # als das Label "Rain (falls from above)" verspricht.
            y_off = int(max(fall * pad_y + bounce * h, 0))
            seg = base[:, x0:x1]
            gh = seg.copy()
            gh[..., 3] = np.clip(seg[..., 3].astype(np.float32) * min(x * 2.2, 1.0),
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
        # v194: SYMMETRISCH polstern, gleicher Fehler wie bei 'regen'. Bis
        # v193 wuchs die Leinwand nur RECHTS; der Streifen landete bei
        # x_off = 0, also am linken Rand, und der fertige Text sass danach
        # dauerhaft pad_x/2 zu weit links. Gemessen: 92 px bei 397 px
        # Wortbreite, also 23 % - genug, um die berechnete Bildseite
        # (v168) und den Plattform-Korridor (v187) zu verfehlen.
        pad_x = int(w * 0.45) + 8
        out = np.zeros((h, w + 2 * pad_x, 4), base.dtype)
        for i in range(n_col):
            x0 = i * cw
            x1 = min(x0 + cw, w)
            # v100: Staffelung verwuerfelt + Feder mit kleinem Overshoot -
            # jeder Streifen rutscht 2-3% ueber sein Ziel hinaus und setzt
            # sich. Lineares ease_out im Gleichschritt war Praesentations-
            # Software, kein Motion Design.
            jit = (((i + 3) * 2654435761) & 1023) / 1023.0
            offset = 0.14 * (i / max(n_col - 1, 1)) + 0.10 * jit
            x = min(max((dt - offset) / 0.42, 0.0), 1.5)
            if x <= 0.0:
                continue
            e = spring(min(x, 1.4), freq=2.5, damp=5.6)
            # Ruhelage = pad_x (Mitte), Start = 2*pad_x (rechts davon).
            # Damit kommt der Streifen wirklich VON RECHTS, so wie das Label
            # sagt, und steht am Ende an der berechneten Stelle.
            x_off = int(pad_x + (1.0 - e) * pad_x)
            seg = base[:, x0:x1]
            gh = seg.copy()
            gh[..., 3] = np.clip(seg[..., 3].astype(np.float32) * min(x * 2.5, 1.0),
                                 0, 255).astype(base.dtype)
            dst_x = max(0, min(x0 + x_off, out.shape[1] - (x1 - x0)))
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
        sys.exit("ERROR: environment variable OPENAI_API_KEY is not set.")
    print("Transcribing speech ...")
    # v146: WIEDERHOLEN statt aufgeben. Ein einzelner HTTP 500 von OpenAI hat
    # bis v145 den ganzen Render abgebrochen - der Kunde sah 'KI-Dienst-Problem'
    # und musste von vorn anfangen (Ismets Befund live auf douchko.eu, 4K-Clip).
    # 5xx, 429 und Netzabbrueche sind aber voruebergehend; genau dafuer ist
    # exponentielles Backoff da. Die Datei wird je Versuch NEU geoeffnet, ein
    # bereits gelesener Datei-Zeiger wuerde sonst einen leeren Upload schicken.
    # Abgebrochen wird erst, wenn alle Versuche scheitern - dann ist es echt.
    _versuche = 4
    _warte = (2.0, 6.0, 14.0)
    r = None
    for _v in range(_versuche):
        _grund = None
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
            _grund, r = 'timed out', None
        except requests.exceptions.ConnectionError:
            _grund, r = 'connection lost', None
        if r is not None:
            # Endgueltig: daran aendert kein weiterer Versuch etwas.
            if r.status_code == 401:
                sys.exit("ERROR: AI access is invalid. Please contact support.")
            if r.status_code == 413:
                sys.exit("ERROR: audio track too large. Try a shorter video.")
            if r.status_code == 429:
                _grund = 'overloaded (429)'
            elif 500 <= r.status_code < 600:
                _grund = f'service problem (HTTP {r.status_code})'
            else:
                break
        if _v >= _versuche - 1:
            break
        _s = _warte[min(_v, len(_warte) - 1)]
        print(f"Speech AI {_grund} - attempt {_v + 2} of {_versuche} "
              f"in {_s:.0f}s...")
        time.sleep(_s)
    if r is None:
        sys.exit("ERROR: no connection to the speech AI. "
                 "Check the connection or try again in a few minutes.")
    if r.status_code == 429:
        sys.exit("ERROR: the AI service is overloaded. "
                 "Please try again in 5 minutes.")
    if 500 <= r.status_code < 600:
        sys.exit(f"ERROR: AI service problem (HTTP {r.status_code}). "
                 f"Please try again in a few minutes.")
    r.raise_for_status()
    data = r.json()
    # v230d: Whisper wird nach MINUTEN abgerechnet, nicht nach Tokens - die
    # Dauer ist die Kostengroesse und steht in der Antwort.
    try:
        AI_VERBRAUCH['audio_s'] += float(data.get('duration') or 0)
    except Exception:
        pass
    words = [{'word': w['word'].strip(), 'start': round(w['start'], 3), 'end': round(w['end'], 3)}
             for w in data.get('words', [])]
    if not words:
        sys.exit("ERROR: no words in the transcript. Does the video have an audio track?")
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

def _rel_lum(rgb):
    """WCAG-Relativluminanz (0..1) eines sRGB-Tripels."""
    c = np.asarray(rgb, dtype=np.float32) / 255.0
    lin = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def contrast_ratio(rgb, lum_bg):
    """WCAG-Kontrastverhaeltnis zwischen einer Farbe und einer Untergrund-
    Luminanz. 1.0 = identisch, 21.0 = Schwarz auf Weiss."""
    la = _rel_lum(rgb)
    hi, lo = max(la, lum_bg), min(la, lum_bg)
    return (hi + 0.05) / (lo + 0.05)


# v140: Reihenfolge der Helligkeits-Kandidaten. Erst die hellen Werte (der
# Standard-Look bleibt, wo er lesbar ist), dann die dunklen. Mittelwerte sind
# bewusst hinten - gegen einen hellen Untergrund helfen sie physikalisch nicht.
_CAP_VALUES = (246, 232, 214, 34, 22, 52, 84, 120, 160)


def fit_caption_color(hue, sat, bg_lum, min_ratio=2.2, kontur=False):
    """Waehlt die Helligkeit des Caption-Tons so, dass gegen den gemessenen
    Untergrund mindestens min_ratio Kontrast steht. Farbton und Saettigung
    bleiben unangetastet, damit die Handschrift erhalten bleibt: auf dunklem
    Grund heller Text wie bisher, auf hellem Grund (Fenster, weisse Wand,
    Himmel, Schnee) derselbe Ton in dunkel. Schafft kein Kandidat die Schwelle
    (mittelgrauer Untergrund), gewinnt der kontraststaerkste - nie schlechter
    als vorher."""
    # v181: MIT KONTUR bleibt der Text HELL, solange der Untergrund nicht
    # wirklich hell ist. Die dunkle Kontur traegt den Kontrast; nach Dunkel
    # zu kippen waere auf mittelgrauem Grund zwar lesbar, saehe aber aus wie
    # ein anderer Look (am Testrender belegt: schwarze Buchstaben auf grauer
    # Wand). Erst ab einem wirklich hellen Untergrund - Fenster, Himmel,
    # Schnee - gewinnt Dunkel; dort waere Weiss auf Weiss der Amateur-Marker.
    _werte = _CAP_VALUES
    if kontur and bg_lum < 0.45:
        _werte = tuple(v for v in _CAP_VALUES if v >= 200)
    best, best_r = None, -1.0
    for v in _werte:
        rgb = cv2.cvtColor(np.uint8([[[int(hue), int(sat), int(v)]]]),
                           cv2.COLOR_HSV2RGB)[0, 0]
        rgb = tuple(int(c) for c in rgb)
        r = contrast_ratio(rgb, bg_lum)
        if r >= min_ratio:
            return rgb
        if r > best_r:
            best, best_r = rgb, r
    # v181 LESBARKEIT SCHLAEGT HANDSCHRIFT. Bis hier variierte nur die
    # HELLIGKEIT, Farbton und Saettigung blieben stehen - auf mittelgrauem
    # Untergrund (Betonwand, grauer Pullover) erreicht damit KEIN getoenter
    # Wert die Schwelle, und der Text blieb bei gemessenen 1.5-2.5:1 haengen.
    # Ein Szenen-Ton, den man nicht lesen kann, ist keine Handschrift,
    # sondern ein Fehler. Reicht die Toenung nicht, faellt sie weg: reines
    # Weiss oder tiefes Schwarz, was auch immer den Untergrund schlaegt.
    _kand = (((255, 255, 255),) if (kontur and bg_lum < 0.45)
             else ((255, 255, 255), (16, 16, 16)))
    for _rein in _kand:
        _r = contrast_ratio(_rein, bg_lum)
        if _r > best_r:
            best, best_r = _rein, _r
    return best


def region_luminance(bgr_region):
    """Konservative Untergrund-Luminanz einer Bildregion: das 65. Perzentil,
    also die hellere Haelfte. Ein grosses helles Fenster hinter dem Sprecher
    darf nicht vom dunklen Rest weggemittelt werden."""
    rgb = bgr_region[:, :, ::-1].reshape(-1, 3).astype(np.float32) / 255.0
    lin = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = 0.2126 * lin[:, 0] + 0.7152 * lin[:, 1] + 0.0722 * lin[:, 2]
    return float(np.percentile(lum, 65))


def scene_space_sampler(video_path, cut_times=None, gx=12, gy=16):
    """v143 RAUM-KARTE: liefert space_at(t) -> Kostenraster (gy x gx, 0..1),
    das sagt, wie BESETZT eine Bildregion ist. 0 = ruhige Flaeche, dort darf
    Text stehen. 1 = viel Struktur (Motiv, Kanten, Muster), dort stoert er.

    Warum ueberhaupt: bis v142 kannte die Platzierung nur die Gesichtsbox.
    Ein Textblock landete deshalb genauso auf einem vollen Buecherregal wie
    auf einer leeren Wand. Die echte Personen-Maske (RVM) steht erst NACH der
    Planung zur Verfuegung, deshalb hier ein billiger, aber ehrlicher Ersatz:
    lokale Kantenenergie plus lokale Helligkeitsstreuung, pro Shot einmal
    abgetastet (gleicher ffmpeg-Weg und dieselbe Shot-Cache-Logik wie
    scene_palette_sampler, also kein zusaetzlicher Suchaufwand).

    Ausdruecklich KEINE Segmentierung und keine Objekterkennung - das Raster
    sagt nur 'hier ist viel los', nicht 'hier ist ein Mensch'. Das Gesicht
    bleibt eine harte, separate Sperre."""
    cache = {}
    bounds = sorted(float(c) for c in (cut_times or []))
    leer = np.zeros((gy, gx), dtype=np.float32)

    def _shot(t):
        import bisect
        idx = bisect.bisect_right(bounds, t)
        start = bounds[idx - 1] if idx > 0 else 0.0
        return (idx, int((t - start) / 6.0))

    def space_at(t):
        key = _shot(t)
        if key in cache:
            return cache[key]
        karte = leer
        try:
            r = subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', str(max(float(t), 0.0)),
                 '-i', video_path, '-frames:v', '1', '-f', 'rawvideo',
                 '-pix_fmt', 'gray', '-s', '192x192', '-'],
                capture_output=True, timeout=20)
            if len(r.stdout) >= 192 * 192:
                g = np.frombuffer(r.stdout[:192 * 192],
                                  dtype=np.uint8).reshape(192, 192).astype(np.float32)
                # Kantenenergie (Sobel) = Struktur; Streuung = Kontrastunruhe.
                kx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
                ky = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
                kant = np.hypot(kx, ky)
                zell_y, zell_x = 192 // gy, 192 // gx
                k = kant[:zell_y * gy, :zell_x * gx].reshape(gy, zell_y, gx, zell_x)
                s = g[:zell_y * gy, :zell_x * gx].reshape(gy, zell_y, gx, zell_x)
                e = k.mean(axis=(1, 3))
                v = s.std(axis=(1, 3))
                # Beide Anteile robust auf 0..1 normieren (95. Perzentil, damit
                # ein einzelner Glanzpunkt nicht die ganze Karte flach macht).
                def norm(a):
                    p = float(np.percentile(a, 95)) or 1.0
                    return np.clip(a / p, 0.0, 1.0)
                karte = (0.65 * norm(e) + 0.35 * norm(v)).astype(np.float32)
        except Exception:
            karte = leer
        cache[key] = karte
        return karte

    return space_at


def scene_palette_sampler(video_path, cut_times=None, min_contrast=2.2,
                          kontur=True):
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
    _hat_kontur = bool(kontur)
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
            # v140 KONTRAST-GARANTIE: Der Farbton folgt weiter der Szene, die
            # HELLIGKEIT wird jetzt gegen den gemessenen Untergrund geprueft.
            # Vorher stand der Text IMMER auf V=246 (fast weiss) - auf hellem
            # Grund war das Weiss auf Weiss, der deutlichste Amateur-Marker.
            if min_contrast and min_contrast > 1.0:
                bg_lum = region_luminance(small)
                text = fit_caption_color(hue, t_sat, bg_lum, min_contrast,
                                         kontur=_hat_kontur)
                accent = fit_caption_color(hue, int(255 * 0.55), bg_lum,
                                           min_contrast, kontur=_hat_kontur)
            else:
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

# v227a Derselbe Frame wurde MEHRFACH aus dem Video geholt. Bild-Regie
# (bis 24 Momente) und Objekt-Anker (bis 16) fragen exakt dieselbe Stelle
# (`words[i]['start'] + 0.15`) - jeder Aufruf startet ein eigenes ffmpeg.
# Am Kundenrender waren das rund 40 Prozessstarts, gut die Haelfte davon
# fuer ein Bild, das schon im Speicher lag. Ein Zwischenspeicher liefert
# BITGLEICH dasselbe Base64 (gleiche Datei, gleiche Zeit, gleiche
# ffmpeg-Argumente sind deterministisch) - hier wird nichts vereinfacht,
# nur nicht zweimal gemacht. Rund 40 KB je Bild, das ist nichts.
_FRAME_B64_CACHE = {}


def _frame_b64(video_path, t, width=480, quality=72):
    """Holt einen Frame als Base64-JPEG fuer die Vision-Regie (klein und guenstig)."""
    import base64
    _k = (video_path, round(float(max(t, 0.0)), 3), width, quality)
    if _k in _FRAME_B64_CACHE:
        return _FRAME_B64_CACHE[_k]
    _t0 = time.time()
    r = subprocess.run(
        ['ffmpeg', '-v', 'error', '-ss', str(max(t, 0.0)), '-i', video_path,
         '-frames:v', '1', '-vf', f'scale={width}:-2',
         '-f', 'image2', '-c:v', 'mjpeg', '-q:v', str(max(2, int(31 - quality / 3.5))), '-'],
        capture_output=True, timeout=20)
    zt('vision-frames', _t0)
    if len(r.stdout) < 500:
        _FRAME_B64_CACHE[_k] = None
        return None
    _b = base64.b64encode(r.stdout).decode('ascii')
    _FRAME_B64_CACHE[_k] = _b
    return _b


def _frame_b64_vorab(video_path, ts, width=480, quality=72):
    """v227a Die Vision-Bilder GLEICHZEITIG holen. Bild-Regie und Objekt-Anker
    ziehen bis zu 24 bzw. 16 Standbilder, bisher streng hintereinander - das
    ist Wartezeit, nicht Rechenzeit. Gleiche Argumente, gleiches Ergebnis."""
    _offen = [t for t in ts
              if (video_path, round(float(max(t, 0.0)), 3), width, quality)
              not in _FRAME_B64_CACHE]
    if len(_offen) < 2:
        return
    try:
        from concurrent.futures import ThreadPoolExecutor
        _n = max(2, min(6, (os.cpu_count() or 2)))
        with ThreadPoolExecutor(max_workers=_n) as _ex:
            list(_ex.map(lambda _t: _frame_b64(video_path, _t, width, quality),
                         _offen))
    except Exception:
        pass

SILENT_PROMPT = """Du bist Retention-Analyst fuer Short-Form-Video. Du siehst Standbilder
eines FERTIG gerenderten Videos mit eingebrannten Captions - so wie es ~74% der
Zuschauer sehen werden: STUMM, beim Scrollen, 1-2 Sekunden Aufmerksamkeit.
Bewerte NUR die stumme Wirkung:
- Liest man in 1 Sekunde, worum es geht? (Lesbarkeit, Groesse, Kontrast)
- Sitzt die Betonung auf den richtigen Woertern (Emphase erkennbar ohne Ton)?
- Kommt der Spannungsbogen visuell an (Hook -> Eskalation -> Aufloesung)?
- Stoert etwas (Text ueber Gesicht, unleserlich, zu voll, zu leer)?
Antworte NUR mit JSON:
{"score": <0-100>, "hinweise": [{"i": <Moment-Index aus dem Text>, "tipp": "<max 12 Woerter, konkret>"}]}
Maximal 3 Hinweise, nur echte Probleme - kein Lob, keine Fuellhinweise."""


def silent_score(out_video, words, fx_map, model='gpt-5'):
    """v101: Zweiter Score neben dem Hook-Score - bewertet das FERTIGE Video
    STUMM (so laeuft die Mehrheit der Views). Ein Vision-Call, max. 6 Frames
    (detail low). Ohne Key/Fehler: None, der Render bleibt unberuehrt."""
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not fx_map:
        return None
    try:
        mom = sorted(fx_map.items(),
                     key=lambda kv: -int(kv[1].get('power', 2)))[:6]
        mom = sorted(mom, key=lambda kv: kv[0])
        content = []
        for i, info in mom:
            if not (0 <= i < len(words)):
                continue
            t = float(words[i].get('start', 0)) + 0.35
            b64 = _frame_b64(out_video, t)
            if not b64:
                continue
            n = int(info.get('n', 1))
            txt = ' '.join(clean(words[j]['word'])
                           for j in range(i, min(i + n, len(words))))
            content.append({'type': 'text',
                            'text': f'MOMENT [{i}] Caption: "{txt}"'})
            content.append({'type': 'image_url',
                            'image_url': {'url': f'data:image/jpeg;base64,{b64}',
                                          'detail': 'low'}})
        if not content:
            return None
        import requests as _rq
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': SILENT_PROMPT},
                    {'role': 'user', 'content': content}],
            max_toks=500, temperature=0.1), timeout=90)
        data = json.loads(_txt)
        score = min(max(int(data.get('score', -1)), 0), 100)
        hints = []
        for h in (data.get('hinweise') or [])[:3]:
            try:
                hints.append({'i': int(h.get('i', -1)),
                              'tipp': str(h.get('tipp', ''))[:120]})
            except Exception:
                continue
        return {'score': score, 'hinweise': hints}
    except Exception as e:
        print(f"Silent score unavailable ({type(e).__name__})")
        return None


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

# v228d Wieviel darf die KI nachdenken? Wird in main() aus der config gesetzt.
AI_DENKEN = 'aus'   # v228e: zurueckgestellt, siehe config.yaml

# v230c2 DENK-AUFWAND PRO FRAGE.
# v228d war ein EINZIGER Schalter fuer alle KI-Fragen, auf 'low' - und Ismets
# Urteil war "Qualitaet ist sehr schlecht geworden". Der Fehler war nicht der
# Regler, sondern seine Grobheit: die Fragen sind nicht gleich schwer.
# An Ismets Job-Log vom 07.08.2026 gemessen (204 s gesamt, davon 170 s reines
# Warten auf OpenAI): allein die Schluesselwort-Frage stand mit 100.7 s da -
# und das sind ZWEI Aufrufe. Der zweite ist `_regie_validate`, ein Pruefer mit
# Checkliste ("ist das ein Hilfsverb, eine Konjunktion, ein Pronomen?"), der in
# diesem Job ueber ganze 2 Highlights zu urteilen hatte. Der lief mit derselben
# Denkstufe wie die kreative Regie.
# Also: die WAHL der Schluesselwoerter und die BILD-Regie bleiben unangetastet
# (das ist die Qualitaet, die Ismet abgenommen hat), die drei mechanischen
# Fragen denken weniger.
# Rangfolge, bewusst so herum:
#   1. `keywords.ai_denken_frage: {<frage>: <stufe>}` - Einzelfall gewinnt.
#   2. `keywords.ai_denken` auf einer STUFE - eine ausdrueckliche Ansage fuer
#      alles gewinnt gegen die Standards hier (sonst waere der bestehende
#      Schalter fuer die Haelfte der Fragen wirkungslos geworden).
#   3. `keywords.ai_denken: aus` (Standard) - die Tabelle unten.
# Unbekannte Stufen werden IGNORIERT, nicht durchgereicht: die API lehnt einen
# falschen Wert mit 400 ab, und ein Tippfehler in der Config darf nicht die
# ganze Regie abschiessen (v230f: klemmen statt kaputtmachen).
AI_DENKEN_FRAGE = {}
_DENK_STUFEN = ('minimal', 'low', 'medium', 'high')
# Frage -> Stufe, wenn nichts anderes gesetzt ist. Wer hier eine Frage
# ergaenzt, beantwortet zuerst: ist das eine ENTSCHEIDUNG (dann volle
# Gruendlichkeit) oder eine PRUEFUNG/AUSWAHL nach festen Regeln?
_DENK_STD = {
    'pruefer': 'low',   # Checkliste ueber die eigenen Vorschlaege
    'fluss':   'low',   # je Textblock das Ankerwort auswaehlen
    'anker':   'low',   # den genannten Gegenstand im Standbild benennen
}


def _denk_fuer(frage=None):
    """v230c2: welcher Denk-Aufwand gilt fuer diese Frage? '' = Parameter gar
    nicht schicken (Verhalten wie vor v228d)."""
    einzeln = str((AI_DENKEN_FRAGE or {}).get(frage, '')).strip().lower()
    if einzeln in _DENK_STUFEN:
        return einzeln
    if AI_DENKEN in _DENK_STUFEN:
        return AI_DENKEN
    if einzeln == 'aus':
        return ''
    std = _DENK_STD.get(frage, '')
    return std if std in _DENK_STUFEN else ''


# Frage -> Name im Job-Log. Der Kunde liest das Log, also englisch (v148).
_DENK_NAMEN = (('regie', 'keywords'), ('pruefer', 'checker'),
               ('bild', 'picture'), ('anker', 'anchor'), ('fluss', 'flow'))


def _denk_log_zeile():
    """v230c2: eine eigene Funktion, damit der Selftest die Zeile durch
    AUFRUFEN pruefen kann. Eine zusammengebaute Log-Zeile, die nur als
    Quelltext geprueft wird, stand in Ismets Job-Log schon einmal falsch da
    (v230ay, die Stil-Anker-Zeile war noch komplett deutsch)."""
    return 'AI thinking: ' + ', '.join(
        f"{name}={_denk_fuer(frage) or 'full'}" for frage, name in _DENK_NAMEN)


def _oai_json(model, messages, max_toks, temperature, json_mode=True,
              frage=None):
    """v94: chat/completions-Body, modell-kompatibel. Neuere Modelle (gpt-5,
    o-Serie) verlangen max_completion_tokens und lehnen ein abweichendes
    temperature ab; aeltere Chat-Modelle akzeptieren beides. Ohne das faellt
    ein neues Modell still auf die Heuristik zurueck.
    v96t: json_mode=False fuer PROSA-Antworten (Stil-Lernen). Mit
    response_format=json_object verlangt OpenAI das Wort "json" im Prompt und
    erzwingt JSON - ein Prosa-Prompt scheitert dann mit 400."""
    new = str(model).startswith(('gpt-5', 'o1', 'o3', 'o4'))
    body = {'model': model, 'messages': messages}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    # v210 DENKBUDGET. Bei den neuen Modellen zaehlen die internen
    # Denk-Tokens MIT in max_completion_tokens. Ein knappes Budget wird
    # komplett vom Denken aufgebraucht, die Antwort kommt LEER zurueck - und
    # json.loads('') meldet einen JSONDecodeError. Genau so sind in Ismets
    # Job-Log die Bild-Regie, der Objekt-Anker und der Stille-Score
    # ausgefallen: nicht die API war kaputt, das Budget war zu klein.
    # Untergrenze war 2500 - und die hat NICHT gereicht (v230ay). In Ismets
    # 4K-Job vom 05.08.2026 steht es schwarz auf weiss: "empty answer
    # (finish_reason=length, budget=2500, used=2500, thereof reasoning=2500)",
    # der Wiederholversuch mit 5000 lief dann durch. Ein ganzer Aufruf war
    # umsonst, und beim Text-Fluss ist das der teuerste Posten im ganzen
    # Render (85 s von 245 s). Jetzt 6000.
    # WICHTIG: das ist eine OBERGRENZE, keine Bestellung - bezahlt werden die
    # tatsaechlich verbrauchten Tokens. Sie anzuheben kostet nichts, solange
    # das Modell sie nicht braucht, und spart genau dann einen kompletten
    # zweiten Aufruf, wenn es sie braucht.
    body['max_completion_tokens' if new else 'max_tokens'] = (
        max(int(max_toks), 6000) if new else max_toks)
    if not new:
        body['temperature'] = temperature
    # v228d DENK-AUFWAND. An Ismets Job-Log gemessen sind 129 von 191 s reines
    # Warten auf die KI - und bei den neuen Modellen geht der Loewenanteil
    # nicht in die Antwort, sondern ins interne Nachdenken. `reasoning_effort`
    # steuert genau das. 'low' ist der Standard (Ismets Entscheidung, Juli
    # 2026); wer die alte Gruendlichkeit will, setzt `keywords.ai_denken` in
    # der config.yaml auf 'medium' oder 'high' - oder auf 'aus', dann wird der
    # Parameter gar nicht geschickt (Verhalten wie vor v228d).
    # WICHTIG: das Denkbudget oben bleibt bei mindestens 6000. Weniger denken
    # heisst MEHR Platz fuer die Antwort, nie weniger - die v210-Falle
    # (leere Antwort) wird dadurch unwahrscheinlicher, nicht wahrscheinlicher.
    # v230c2: der Aufwand haengt jetzt an der FRAGE, nicht mehr am ganzen
    # Render. Weniger denken heisst wie gehabt MEHR Platz fuer die Antwort,
    # nie weniger - die v210-Falle (leere Antwort) wird dadurch
    # unwahrscheinlicher.
    _denk = _denk_fuer(frage)
    if new and _denk:
        body['reasoning_effort'] = _denk
    return body


def _oai_text(key, body, timeout=120):
    """v230p EINE STELLE FUER DEN AUFRUF - UND EINE EHRLICHE FEHLERMELDUNG.

    Bis v230o las jeder Aufrufer selbst
    `r.json()['choices'][0]['message']['content']`. Ist die Antwort LEER,
    meldet `json.loads('')` einen JSONDecodeError - und genau das stand in
    Ismets Job-Log bei der Bild-Regie und beim Text-Fluss. Die Meldung nennt
    aber nicht die Ursache: die Antwort war nicht kaputt, sie war NICHT DA.
    Bei den Denk-Modellen zaehlen die internen Denk-Tokens in dasselbe
    Budget wie die Antwort (v210); reicht es nicht, kommt
    `finish_reason='length'` mit leerem Inhalt zurueck.

    Deshalb hier: EIN Wiederholversuch mit doppeltem Budget (die Regie ist
    das Herz des Produkts - ein stiller Rueckfall auf die Heuristik kostet
    mehr als ein zweiter Aufruf), und wenn es dann immer noch leer ist, eine
    Meldung, die den Grund NENNT (finish_reason plus Denk-Tokens) statt
    eines nichtssagenden JSONDecodeError.
    """
    import requests
    url = 'https://api.openai.com/v1/chat/completions'
    kopf = {'Authorization': f'Bearer {key}'}
    _tk = 'max_completion_tokens' if 'max_completion_tokens' in body \
        else 'max_tokens'
    letzte = ''
    for versuch in (0, 1):
        r = requests.post(url, headers=kopf, json=body, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        # v230d: JEDER Aufruf wird gezaehlt, auch der gleich folgende
        # Wiederholversuch - der kostet echtes Geld.
        ai_verbrauch_zaehlen(body.get('model'), d.get('usage'))
        ch = (d.get('choices') or [{}])[0]
        txt = ((ch.get('message') or {}).get('content') or '').strip()
        if txt:
            return txt
        u = d.get('usage') or {}
        det = u.get('completion_tokens_details') or {}
        letzte = (f"empty answer (finish_reason={ch.get('finish_reason')}, "
                  f"budget={body.get(_tk)}, used={u.get('completion_tokens')}, "
                  f"thereof reasoning={det.get('reasoning_tokens')})")
        if versuch == 0 and ch.get('finish_reason') == 'length' \
                and body.get(_tk):
            body = dict(body)
            body[_tk] = int(body[_tk]) * 2
            print(f"  AI: {letzte} - retrying with {body[_tk]} tokens")
            continue
        break
    raise ValueError(letzte + ' - token budget too small')


def ai_scene_direct(words, fx_map, video_path, model='gpt-5', min_power=2,
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
    _frame_b64_vorab(video_path, [words[i]['start'] + 0.15 for i in idx])
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
        # v230p: das Budget waechst mit der Zahl der BILDER. Ein Denk-Modell
        # denkt pro Bild nach, und die Denk-Tokens gehen vom selben Budget ab -
        # mit festen 1500 (Untergrenze 2500) war die Antwort bei 24 Bildern
        # leer, bevor sie anfing (Ismets Job-Log).
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': SZENE_PROMPT},
                    {'role': 'user', 'content': content}],
            max_toks=1500 + 260 * len(sent), temperature=0.1), timeout=180)
        data = json.loads(_txt)
        n_v = 0
        for m in data.get('momente', []):
            i = int(m.get('i', -1))
            if i not in fx_map:
                continue
            # v99a: Ansage des Sprechers ist Gesetz. Hat _speech_intent/
            # _self_ref_intent den Moment explizit platziert ("the captions
            # are behind me"), darf die Vision-Regie ihn NICHT umziehen -
            # sonst macht das Video nicht, was der Sprecher sagt.
            if fx_map[i].get('intent'):
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
        print(f"Vision director: {n_v} moments matched to the scene")
    except Exception as e:
        print(f"Vision director unavailable ({type(e).__name__}), text direction stays.")
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
        # v99a: explizite Sprecher-Ansage ("behind me") bleibt 'behind'.
        # v141 (Ismets Befund): frueher wurde bei bildfuellender Nahaufnahme
        # szene='himmel' erzwungen - das Wort landete dann ganz oben am
        # Bildrand, wo die Person gar nicht ist. "behind you" ueber leerem
        # Himmel ergibt keinen Sinn. Stattdessen wird der Moment nur als
        # Nahaufnahme markiert: die Platzierung bleibt auf Kopf-/Schulterhoehe
        # (die Aussage stimmt), und die Lesbarkeits-Logik weiter unten
        # vergroessert das Wort, bis es beidseitig am Kopf vorbeiragt. Erst
        # wenn selbst das nicht reicht, wandert es als letzte Rettung ueber
        # den Kopf. Echte Himmel-Ansagen ("ueber mir") setzen szene selbst und
        # bleiben davon unberuehrt.
        if v.get('intent'):
            if face_cover.get(i, 0.0) >= thresh and not v.get('szene'):
                v['nah'] = True
            continue
        if face_cover.get(i, 0.0) >= thresh:
            # Grosses Statement -> ground, sonst klar sichtbares outline.
            v['fx'] = 'ground' if int(v.get('power', 2)) >= 3 else 'outline'
            moved += 1
    if moved:
        print(f"  Visibility: {moved} 'behind' in a close-up -> moved to the front")
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

def estimate_light_dir(frame_bgr):
    """v101f LICHT-WAHRHEIT: schaetzt die dominante Lichtrichtung aus einem
    Frame. Rueckgabe: (lx, hard) - lx in [-1,1] (positiv = heller rechts, Licht
    kommt von rechts), hard in [0,1] (starkes Helligkeitsgefaelle = hartes,
    gerichtetes Licht -> langer klarer Schatten; flach = weiches Umgebungslicht
    -> runder, kurzer Schatten). Rein aus der Luminanz, kein ML noetig."""
    try:
        f = np.asarray(frame_bgr, np.float32)
        if f.ndim == 3:
            lum = 0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]
        else:
            lum = f
        h, w = lum.shape[:2]
        left = float(lum[:, :w // 2].mean())
        right = float(lum[:, w // 2:].mean())
        span = max(float(lum.mean()), 1.0)
        lx = max(-1.0, min(1.0, (right - left) / span))
        hard = max(0.0, min(1.0, abs(right - left) / (span * 0.6)))
        return (lx, hard)
    except Exception:
        return (0.0, 0.0)


def make_contact_shadow(arr, strength=0.42, light=None):
    """Weicher Kontakt-Schatten unter dem Text: verkauft, dass der Text WIRKLICH
    auf dem Untergrund steht. Breite folgt der Alpha-Verteilung der Unterkante.

    v101f: mit light=(lx, hard) faellt der Schatten licht-wahr zur Seite - weg
    vom Licht (Licht rechts -> Schatten nach links versetzt und in diese
    Richtung gestreckt), und hartes Licht macht ihn kraeftiger. Ohne light
    bleibt es der symmetrische Blob wie bisher (Rueckwaerts-Kompatibilitaet)."""
    a = arr[..., 3]
    ys, xs = np.where(a > 8)
    if len(ys) < 10:
        return None, 0.0, 0.0
    y1 = int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    w = max(x1 - x0, 8)
    lx = hard = 0.0
    if light is not None:
        lx, hard = float(light[0]), float(light[1])
    strength = strength * (1.0 + 0.35 * hard)          # hartes Licht: kraeftiger
    sh_h = max(int(w * 0.055), 10)
    # Schatten faellt weg vom Licht: Breite waechst zur Schattenseite.
    grow = 1.10 + 0.35 * abs(lx) * hard
    sh = np.zeros((sh_h, int(w * grow), 4), dtype=np.float32)
    yy, xx = np.mgrid[0:sh.shape[0], 0:sh.shape[1]]
    cx_, cy_ = sh.shape[1] / 2.0, sh.shape[0] / 2.0
    d2 = ((xx - cx_) / (sh.shape[1] * 0.46)) ** 2 + ((yy - cy_) / (sh.shape[0] * 0.55)) ** 2
    sh[..., 3] = np.clip(1.0 - d2, 0, 1) ** 1.6 * 255 * strength
    sh = cv2.GaussianBlur(sh, (0, 0), sh_h * 0.28)
    dy = float(y1 - arr.shape[0] / 2.0)
    dx = float((x0 + x1) / 2.0 - arr.shape[1] / 2.0)
    # Versatz gegen das Licht (Licht rechts, lx>0 -> Schatten nach links).
    dx -= lx * hard * w * 0.16
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


def _free_x_multi(faces, W, sprite_w, toggle, ziel_x=None):
    """v96: Text-Mittelpunkt im Querformat, der KEIN Gesicht ueberdeckt - auch
    wenn mehrere Personen im Bild sind. Sucht die breiteste freie Luecke (links
    der linkesten Person, zwischen zwei Personen, rechts der rechtesten) und legt
    den Text dorthin, sofern der Sprite hineinpasst. Findet sich keine Luecke,
    kommt der Text auf die Seite mit dem meisten Rand. Rein & testbar.
    faces = Liste (cx, w) in Bild-Pixeln. Rueckgabe: (side -1/1, cx).

    v162: ziel_x = x-Position des AKTIVEN Sprechers. Ist sie gesetzt, gewinnt
    nicht mehr die BREITESTE passende Luecke, sondern die NAECHSTE an ihm.
    Bei zwei Personen ist die breiteste Luecke fast immer dieselbe, egal wer
    gerade redet - der Text blieb dadurch stur auf einer Seite kleben. Ist
    keine Luecke breit genug, bleibt die alte Regel (breiteste), denn eine
    zu enge Luecke neben dem Sprecher schneidet ihn an."""
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
    if fit and ziel_x is not None:
        # Naechste passende Luecke am Sprecher. Der Mittelpunkt wird in die
        # Luecke hinein zum Sprecher gezogen, damit der Text auch WIRKLICH
        # neben ihm sitzt und nicht in der Luecken-Mitte weit weg.
        a, b = min(fit, key=lambda g: abs((g[0] + g[1]) / 2.0 - ziel_x))
        cx = min(max(float(ziel_x), a + half), b - half)
    elif fit:
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
        print(f"  Cutout preview skipped ({type(e).__name__})")
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
    print("Face tracking + scene analysis ...")
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
    # v230m: zusaetzlich ein winziges GRAUSTUFEN-Bild je Frame. Das
    # Farb-Histogramm ist auf einem Studio-Set blind - alles ist grau, und
    # ein Schnitt von der Totale in die Nahaufnahme aendert die Farbverteilung
    # kaum (an Ismets Werbespot gemessen: staerkstes Signal 0.935 bei einer
    # Schwelle von 0.55, also KEIN einziger Schnitt gefunden, obwohl das Video
    # vier hat). Der Bildaufbau aendert sich dagegen massiv.
    thumbs = []
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
        thumbs.append(cv2.resize(cv2.cvtColor(tiny, cv2.COLOR_BGR2GRAY),
                                 (32, 32)).astype(np.float32))
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
    # v230m ZWEITES SIGNAL: der BILDAUFBAU. Auf einem Studio-Set (grauer
    # Hintergrund, dunkle Kleidung) traegt die Farbe keine Information - in
    # Ismets Werbespot fand das Histogramm KEINEN der vier Schnitte (bestes
    # Signal 0.935 gegen die Schwelle 0.55). Die mittlere Helligkeits-
    # Abweichung eines 32x32-Miniaturbildes trennt dort sauber: Median 2.2,
    # 95. Perzentil 5.8, an den drei Schnitten 34 / 67 / 56.
    # Die Schwelle haengt am MATERIAL (Vielfaches des Medians), nicht an einer
    # festen Zahl - ein wackliges Handyvideo hat durchgehend hohe Werte, ein
    # Stativ-Interview durchgehend niedrige.
    _mad = [float(np.abs(thumbs[i] - thumbs[i - 1]).mean())
            for i in range(1, n)] if len(thumbs) == n and n > 1 else []
    _mad_gr = (max(12.0, 6.0 * float(np.median(_mad))) if _mad else 1e9)
    cuts = [0]
    for i in range(1, n):
        _harter_schnitt = (
            cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_CORREL) < 0.55
            or (_mad and _mad[i - 1] >= _mad_gr))
        if _harter_schnitt:
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
    print(f"  {len(shots)} shots, {int(sum(r is not None for r in raw))}/{n} frames with a face"
          + (f", {n_broll} frames classified as B-roll" if n_broll else "")
          + (f", multiple people in {_npf} frames" if multi_person else ""))
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
        # v143: das SCHLUESSELWORT der Flow-Caption lief bisher in JEDEM Look
        # hart auf poppins_b. Damit sah der Fliesstext in allen acht Presets
        # gleich aus, nur die Akzentfarbe unterschied sich - der teuerste Teil
        # des Bildes war look-blind. Die Referenz benutzt EINE Familie in zwei
        # Groessen; entsprechend nimmt das Schluesselwort jetzt die Display-
        # Schrift des Looks. 'strong' kann das gezielt uebersteuern.
        sb = os.path.join(HERE, f.get('strong') or f['display'])
        if not os.path.exists(sb):
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
             wght=None, kontur=None):
        """Rendert in doppelter Aufloesung und rechnet mit INTER_AREA herunter (Supersampling).
        wght setzt - falls ein variabler Schnitt vorliegt - die echte Gewichts-Achse."""
        font = font or self.f_serif
        # v230ag: fremdes Schriftsystem -> passende Noto-Schrift. Der Riegel
        # sitzt HIER, in der Funktion, die jeder Textweg benutzt - nicht an
        # einem einzelnen Aufrufer (v159-Lehre).
        font = script_font(txt, font)
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
        # v181: Konturstaerke waechst mit der Schrift. 0.07 der Schriftgroesse
        # entspricht bei Hausmass-Captions rund 2-4 px im fertigen Bild - der
        # Bereich, den die Praxis als lesbar UND unaufdringlich fuehrt.
        # Ueber effects.caption_kontur abschaltbar (0) oder skalierbar.
        # v189: kontur=False schaltet den Saum fuer diesen Aufruf ab. Grosse
        # Woerter tragen ihren Kontrast ueber die Flaeche; ein Umriss macht
        # sie plakativ statt gesetzt (Ismets Ansage: "bei den grossen
        # Woertern den Umriss weg"). Fliesstext behaelt ihn - dort ist er
        # der Lesbarkeits-Garant aus v181.
        _kf = (0.0 if kontur is False
               else (self.cfg.get('effects', {}) or {}).get('caption_kontur', 1.0))
        try:
            _kf = float(_kf)
        except (TypeError, ValueError):
            _kf = 1.0
        # v181: 0.055 statt 0.07. Die Kontur waechst das Sprite mit; bei 0.07
        # wurde der Block so viel hoeher, dass er im Nahaufnahme-Fall nicht
        # mehr in die schmale Spalte neben den Kopf passte und nach unten
        # auswich (v143-Regression, vom Selftest gefangen). 0.055 liegt
        # weiter im Praxisfenster von 2-4 px bei Hausmass-Captions.
        _kontur = (0 if _kf <= 0.01
                   else max(2 * SS, int(size2 * 0.055 * min(_kf, 2.5))))
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
                # v181 LESBARKEIT IST NICHT VERHANDELBAR. Bis hierher trug der
                # Text nur einen weichen, VERSETZTEN Schlagschatten - auf
                # einem grauen Pullover oder einer Betonwand ist der
                # wirkungslos. Am Render gemessen: 1.52 bis 3.10:1 Kontrast,
                # die Norm (WCAG AA) verlangt 4.5:1. Eine dunkle KONTUR
                # direkt am Glyphenrand loest das unabhaengig vom
                # Untergrund - genau der Grund, warum sie in der Branche
                # der Standard fuer eingebrannten Text ist.
                # Sie liegt auf der HINTEREN Ebene, damit das Studio-Licht
                # der Frontflaeche sie nicht aufhellt.
                if _kontur:
                    # v187: die Kontur richtet sich nach der TEXTFARBE. Hart
                    # schwarz war ein dunkler Saum um dunklen Text - genau
                    # der Fall im Look 'clean', der als einziger eine feste
                    # dunkle Palette faehrt (gemessen 1.37:1 auf dunklem
                    # Material). Ein heller Text behaelt den schwarzen Saum,
                    # ein dunkler bekommt einen hellen.
                    _kfill = ((0, 0, 0, 238) if max(color[:3]) >= 128
                              else (255, 255, 255, 238))
                    d.text((x, pad), ch, font=f, fill=(0, 0, 0, 0),
                           stroke_width=_kontur, stroke_fill=_kfill)
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
        font = script_font(txt, font)     # v230ag: gleiche Schrift wie beim Setzen
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


def occlude_sprite(arr, cx, cy, W, H, scale, alpha_p):
    """v184: stanzt die Personen-Silhouette aus einem Text-Sprite aus, damit
    ein Flow-Schlusswort HINTER der Person stehen kann (Referenz-Grammatik:
    die Punchline laeuft durch die Person, Ref C 'this'). Die Maske wird an
    der Zielposition des Sprites abgetastet - die Zeichenreihenfolge des
    Frames bleibt unangetastet, nur die Sprite-Alpha wird beschnitten."""
    h, w = arr.shape[:2]
    tw, th = max(int(w * scale), 2), max(int(h * scale), 2)
    x0i, y0i = int(cx - tw / 2.0), int(cy - th / 2.0)
    xa, ya = max(0, x0i), max(0, y0i)
    xb, yb = min(W, x0i + tw), min(H, y0i + th)
    if xb <= xa or yb <= ya:
        return arr
    m = np.zeros((th, tw), np.float32)
    m[ya - y0i:yb - y0i, xa - x0i:xb - x0i] = alpha_p[ya:yb, xa:xb, 0]
    if m.max() < 0.02:
        return arr
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    out = arr.copy()
    out[..., 3] = (out[..., 3].astype(np.float32) * (1.0 - m)).astype(np.uint8)
    return out


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
                  refract=1.0, blur=0.0, occ=None, grain=2.2, grain_seed=None):
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
        # v101h: seedbar, damit der Alpha-Export-Doppelpass (schwarz/weiss)
        # bitidentisches Grain sieht. None = frei (Verhalten wie bisher).
        noise = np.random.default_rng(grain_seed).standard_normal(sub.shape[:2])[..., None]
        sub[..., :3] = np.clip(sub[..., :3] + noise * grain, 0, 255)
    canvas[y1:y2, x1:x2] = sub[..., [2, 1, 0]] * mod * a + bg * (1 - a)

def paste_scene(canvas, rgba, cx, cy, W, H, scale=1.0, opacity=0.74, ripple=0.10,
                refract=1.0, blur=0.0, occ=None, grain=2.2, grain_seed=None):
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
                  refract=refract, blur=blur, occ=occ, grain=grain,
                  grain_seed=grain_seed)

# ---------------------------------------------------------------------------
# v161 OBJEKT-ANKER
# Sagt jemand "dieses Glas hier" oder "schau dir das an", dockt die Caption
# AM OBJEKT an und bleibt daran kleben, auch wenn die Kamera schwenkt.
#
# Zwei Stufen, bewusst getrennt:
#   1. WO ist das Objekt? -> GPT-5-Vision, EINMAL pro Moment. Ein
#      Sprachmodell kann sagen "das Glas steht links unten"; eine exakte Box
#      liefert es nicht zuverlaessig, deshalb wird nur ein grober Mittelpunkt
#      plus Groesse verlangt.
#   2. WOHIN wandert es? -> reiner Optical Flow, jeden Frame, lokal. Das ist
#      praezise, deterministisch und kostet keinen einzigen Token. Die KI
#      sagt, WAS gemeint ist; die Messung sagt, WO es gerade ist.
# Ein Vision-Aufruf pro Frame waere weder bezahlbar noch stabil - er wuerde
# bei jedem Frame ein paar Pixel anders raten und der Text wuerde zittern.
# ---------------------------------------------------------------------------

class ObjektAnker:
    """Verfolgt EIN Bildgebiet ueber sparse Optical Flow (Lucas-Kanade).
    Rueckgabe ist die aufsummierte Verschiebung seit dem Start in Pixeln des
    VOLLBILDES. ok=False heisst: die Spur ist verloren (Schnitt, Verdeckung,
    zu wenig Struktur) - dann bleibt der Text stehen, wo er war, statt
    irgendwohin zu springen."""

    def __init__(self, gray, cx, cy, r, W, H):
        self.W, self.H = float(W), float(H)
        self.sk = gray.shape[1] / max(float(W), 1.0)   # Arbeits- zu Vollbild
        self.dx = self.dy = 0.0
        self.ok = False
        self.prev = None
        self.pts = None
        self._seed(gray, cx * self.sk, cy * self.sk, max(r * self.sk, 6.0))

    def _seed(self, gray, x, y, r):
        h, w = gray.shape[:2]
        maske = np.zeros((h, w), np.uint8)
        x0, y0 = int(max(x - r, 0)), int(max(y - r, 0))
        x1, y1 = int(min(x + r, w)), int(min(y + r, h))
        if x1 - x0 < 6 or y1 - y0 < 6:
            return
        maske[y0:y1, x0:x1] = 255
        pts = cv2.goodFeaturesToTrack(gray, maxCorners=90, qualityLevel=0.01,
                                      minDistance=4, mask=maske)
        # Unter 8 Punkten ist der Median kein Median mehr, sondern Rauschen.
        if pts is None or len(pts) < 8:
            return
        self.pts = pts.astype(np.float32)
        self.prev = gray
        self.ok = True

    def step(self, gray):
        """Ein Frame weiter. Rueckgabe (dx, dy) im Vollbild-Massstab."""
        if not self.ok or self.prev is None or self.pts is None:
            return self.dx, self.dy
        nx, st, _ = cv2.calcOpticalFlowPyrLK(self.prev, gray, self.pts, None,
                                             winSize=(17, 17), maxLevel=3)
        if nx is None or st is None:
            self.ok = False
            return self.dx, self.dy
        # VORWAERTS-RUECKWAERTS-PROBE. Ohne sie ist der Status von LK
        # wertlos: bei einem Schnitt oder einem Sprung meldet LK nicht etwa
        # Misserfolg, sondern rastet auf einer aehnlich aussehenden Stelle
        # ein und liefert eine kleine, voellig plausible Verschiebung
        # (im Test: -3.6 px, waehrend das Objekt 200 px gesprungen war).
        # Ein Punkt zaehlt erst, wenn er auch RUECKWAERTS wieder dort landet,
        # wo er herkam. Das ist der Median-Flow-Standard.
        bk, st2, _ = cv2.calcOpticalFlowPyrLK(gray, self.prev, nx, None,
                                              winSize=(17, 17), maxLevel=3)
        gut = st.reshape(-1) == 1
        if bk is not None and st2 is not None:
            fb = np.abs(self.pts.reshape(-1, 2)
                        - bk.reshape(-1, 2)).max(axis=1)
            gut = gut & (st2.reshape(-1) == 1) & (fb < 1.0)
        else:
            gut = np.zeros_like(gut)
        if int(gut.sum()) < 6:
            self.ok = False
            return self.dx, self.dy
        alt = self.pts.reshape(-1, 2)[gut]
        neu = nx.reshape(-1, 2)[gut]
        vx = float(np.median(neu[:, 0] - alt[:, 0]))
        vy = float(np.median(neu[:, 1] - alt[:, 1]))
        # Ausreisser raus: was sich voellig anders bewegt als die Mehrheit,
        # gehoert nicht mehr zum Objekt (Verdeckung, vorbeilaufende Hand).
        rest = np.abs(neu - alt - np.array([vx, vy], np.float32)).max(axis=1)
        behalten = rest < max(2.5, abs(vx) * 0.5 + abs(vy) * 0.5 + 2.0)
        if int(behalten.sum()) >= 6:
            neu = neu[behalten]
            alt = alt[behalten]
            vx = float(np.median(neu[:, 0] - alt[:, 0]))
            vy = float(np.median(neu[:, 1] - alt[:, 1]))
        # Ein Sprung ueber ein Viertel der Bildbreite ist kein Objekt, das
        # wandert - das ist ein Schnitt. Spur beenden statt mitspringen.
        if math.hypot(vx, vy) > gray.shape[1] * 0.25:
            self.ok = False
            return self.dx, self.dy
        self.dx += vx / max(self.sk, 1e-6)
        self.dy += vy / max(self.sk, 1e-6)
        self.pts = neu.reshape(-1, 1, 2).astype(np.float32)
        self.prev = gray
        if len(self.pts) < 10:                # Spur duennt aus -> nachsaeen
            self._seed(gray, alt[:, 0].mean() + vx, alt[:, 1].mean() + vy,
                       max(gray.shape[1] * 0.06, 8.0))
        return self.dx, self.dy


OBJEKT_PROMPT = """Du bist Bildregisseur. Du bekommst pro MOMENT ein Standbild und den
gesprochenen Satz. Frage: zeigt der Satz auf ein KONKRETES, im Bild SICHTBARES Objekt?

JA nur bei einem echten Bezug auf etwas Sichtbares:
"dieses Glas hier", "schau dir das an", "this thing right here", "der Knopf da".
NEIN bei allem anderen - abstrakte Aussagen, Zahlen, Meinungen, allgemeine Saetze,
oder wenn das gemeinte Objekt im Bild gar nicht zu sehen ist. Im Zweifel NEIN.
Die Person selbst ist KEIN Objekt.

Antworte NUR mit JSON:
{"momente": [{"i": <Moment-Index>, "objekt": "<ein Wort>", "cx": <0..1>, "cy": <0..1>, "groesse": <0..1>}]}
cx/cy = Mittelpunkt des Objekts im Bild (0 = links/oben, 1 = rechts/unten).
groesse = Breite des Objekts als Anteil der Bildbreite.
Momente ohne sichtbares Bezugsobjekt laesst du WEG."""


def ai_objekt_anker(words, fx_map, video_path, model='gpt-5', min_power=2):
    """v161: fragt GPT-5-Vision pro Moment nach einem sichtbaren Bezugsobjekt
    und schreibt es als fx_map[i]['anker'] = {'objekt', 'cx', 'cy', 'groesse'}.
    Ohne Key oder bei jedem Fehler passiert nichts - der Anker ist ein Extra,
    kein Fundament."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key or not fx_map:
        return fx_map
    idx = [i for i in sorted(fx_map)
           if int(fx_map[i].get('power', 2)) >= min_power][:16]
    content, sent = [], []
    _frame_b64_vorab(video_path, [words[i]['start'] + 0.15 for i in idx])
    for i in idx:
        b64 = _frame_b64(video_path, words[i]['start'] + 0.15)
        if not b64:
            continue
        txt = ' '.join(clean(words[j]['word'])
                       for j in range(max(i - 4, 0),
                                      min(i + int(fx_map[i].get('n', 1)) + 4,
                                          len(words))))
        content.append({'type': 'text', 'text': f'MOMENT [{i}] Satz: "{txt}"'})
        content.append({'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b64}',
                                      'detail': 'low'}})
        sent.append(i)
    if not sent:
        return fx_map
    try:
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': OBJEKT_PROMPT},
                    {'role': 'user', 'content': content}],
            max_toks=900 + 200 * len(sent), temperature=0.1,
            frage='anker'), timeout=180)
        data = json.loads(_txt)
    except Exception as e:
        print(f"Object anchor: vision skipped ({type(e).__name__})")
        return fx_map
    n = 0
    for m in (data.get('momente') or []):
        try:
            i = int(m.get('i', -1))
            cx = float(m.get('cx'))
            cy = float(m.get('cy'))
            gr = float(m.get('groesse', 0.15))
        except (TypeError, ValueError):
            continue
        if i not in fx_map:
            continue
        # Ausserhalb des Bildes oder absurd gross: das ist kein Objekt mehr,
        # sondern eine Halluzination. Lieber keinen Anker als einen falschen.
        if not (0.02 <= cx <= 0.98 and 0.02 <= cy <= 0.98):
            continue
        if not (0.02 <= gr <= 0.60):
            continue
        fx_map[i]['anker'] = {'objekt': str(m.get('objekt', ''))[:24],
                              'cx': cx, 'cy': cy, 'groesse': gr}
        n += 1
    if n:
        print(f"Object anchor: {n} moments dock onto a visible object")
    return fx_map


def update_homography(prev_gray, gray, H_cum, mask_lower=0.30, region='boden',
                      exclude=None):
    """Ein Schritt planares Kamera-Tracking: verfolgt Features der Bodenebene
    (unteres Bilddrittel aufwaerts) und akkumuliert die Homographie.
    Gibt (H_cum_neu, ok) zurueck - genau die Transformation, die ein
    After-Effects-Plane-Track liefert.

    v101i: region='wand' trackt stattdessen die obere Bildhaelfte (die
    Wand-Ebene hat eine andere Parallaxe als der Boden); exclude = optionale
    Personen-Maske (H,W float 0..1), deren Pixel nie Features liefern."""
    h, w = gray.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    if region == 'wand':
        # v101i WORLD-LOCK WAND: die Wand-Ebene lebt in der OBEREN Bildhaelfte
        # (+Mitte). Boden-Features haben bei Kamerabewegung eine andere
        # Parallaxe - ein Wand-Text, der am Boden-Track haengt, rutscht.
        mask[:int(h * 0.62), :] = 255
    else:
        mask[int(h * mask_lower):, :] = 255
    if exclude is not None:
        # v101i: Personen-Pixel raus - eine bewegte Person zieht sonst die
        # Homographie mit (der "Welt-Anker" klebte an der Schulter).
        _ex = cv2.resize(exclude.astype(np.float32), (w, h))
        mask[_ex > 0.35] = 0
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


# v101k DEPTH-BULLET-TIME: die Sprech-Pause VOR der Punchline (>=0.8s vor
# einem power-3-Moment) wird zum Bullet-Time-Moment - das Bild friert ein und
# eine virtuelle Kamera faehrt per 2.5D-Tiefen-Reprojektion seitlich hinein
# und wieder zurueck (sin-Bogen: endet exakt auf 0, der Schnitt zurueck ins
# Live-Bild ist nahtlos). Dauer bleibt UNVERAENDERT (die Pause war eh still).
# Maximal 1x pro Video, Quality-Gate auf der Tiefenkarte.
def bullet_window(words, plans, min_gap=0.8):
    """Findet DIE Bullet-Time-Stelle: laengste Sprech-Pause >= min_gap direkt
    vor einem power-3-Moment. Rueckgabe (t0, t1, kw_i) oder None."""
    best = None
    for p in plans:
        if p.get('power', 2) < 3 or 'kw_i' not in p or p.get('broll'):
            continue
        i = p['kw_i']
        if i <= 0 or i >= len(words):
            continue
        gap = float(words[i].get('start', 0)) - float(words[i - 1].get('end', 0))
        if gap < min_gap:
            continue
        t0 = float(words[i - 1].get('end', 0)) + 0.06
        t1 = float(words[i].get('start', 0)) - 0.02
        if t1 - t0 < min_gap * 0.6:
            continue
        if best is None or (t1 - t0) > (best[1] - best[0]):
            best = (t0, t1, i)
    return best


def depth_quality_ok(depth_n, min_spread=0.25):
    """v101k Quality-Gate: eine flache Tiefenkarte (kaum Vorder-/Hintergrund-
    Trennung) ergibt keinen 3D-Eindruck, nur Wobbeln -> dann lieber gar kein
    Effekt als ein billiger."""
    if depth_n is None:
        return False
    d = np.asarray(depth_n, np.float32)
    return float(np.percentile(d, 90) - np.percentile(d, 10)) >= min_spread


def depth_dolly(freeze, depth_n, u, W, H, strength=1.0):
    """v101k: reprojiziert das eingefrorene Frame fuer Fortschritt u (0..1).
    Naehere Pixel verschieben sich staerker (Parallaxe), dazu ein leichter
    Push-in. s(u)=sin(pi*u): faehrt hinein und exakt auf 0 zurueck."""
    s = math.sin(math.pi * float(u))
    if s < 1e-4:
        return freeze
    d = cv2.GaussianBlur(np.asarray(depth_n, np.float32), (0, 0), 9.0)
    d = d - float(np.median(d))
    lat = W * 0.030 * s * strength           # seitlicher Dolly
    zoom = 1.0 + 0.028 * s * strength        # leichter Push-in
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx_, cy_ = W / 2.0, H / 2.0
    map_x = (xx - cx_) / zoom + cx_ - d * lat
    map_y = (yy - cy_) / zoom + cy_ - d * lat * 0.22
    return cv2.remap(freeze, map_x, map_y, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


# v101j HAND-KONTAKT: beruehrt eine Fingerspitze den Text, reagiert er
# physisch (Feder-Impuls in Bewegungsrichtung) und die Hand verdeckt ihn
# lokal. Detection nur in Moment-Fenstern (gated), alle 2 Frames.
HAND_TIPS = (4, 8, 12, 16, 20)      # Daumen-, Zeige-, Mittel-, Ring-, kleine Spitze


# ---------------------------------------------------------------------------
# v160 ZEIGE-REGIE
# Zeigt oder schaut der Sprecher irgendwohin, landet die Caption GENAU DORT.
# Das Material dafuer liegt seit v101j im Haus (Hand-Landmarker) bzw. seit
# v96 (Gesichts-Keypoints), wurde aber nur fuer Occlusion und Kamera benutzt.
# Die Regie las es nie.
#
# Zwei Quellen, in dieser Rangfolge:
#   1. ZEIGEN. Der Zeigefinger ist gestreckt, die anderen sind eingerollt.
#      Die Fingerachse (Grundgelenk -> Spitze) ist der Strahl, das Ziel liegt
#      auf halbem Weg zum Bildrand.
#   2. BLICK. Ist kein Zeigen da, verraet die Kopfdrehung die Richtung. Die
#      Nasenspitze wandert relativ zur Augenmitte in die Blickrichtung.
#      Nur bei DEUTLICHER Drehung - wer in die Kamera spricht, meint niemanden.
# Beides ist eine reine Bildmessung, kein API-Aufruf, kein Modell-Rat.
# ---------------------------------------------------------------------------

# Landmark-Indizes des MediaPipe-Handmodells.
_HAND_WRIST = 0
_HAND_FINGER = ((8, 6), (12, 10), (16, 14), (20, 18))   # (Spitze, Mittelgelenk)


_FRAME_BGR_CACHE = {}


def _frame_bgr(video_path, t, w=384):
    """Einzelner Frame als BGR-Array. None, wenn ffmpeg nichts Brauchbares
    liefert (Ende des Videos, kaputte Stelle)."""
    _k = (video_path, round(float(max(t, 0.0)), 3), int(w))
    if _k in _FRAME_BGR_CACHE:
        return _FRAME_BGR_CACHE[_k]
    _t0 = time.time()
    try:
        r = subprocess.run(
            ['ffmpeg', '-v', 'error', '-ss', str(max(float(t), 0.0)),
             '-i', video_path, '-frames:v', '1', '-vf', f'scale={int(w)}:-2',
             '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
            capture_output=True, timeout=25)
    except Exception:
        zt('einzelframes', _t0)
        return None
    zt('einzelframes', _t0)
    buf = r.stdout
    zeile = int(w) * 3
    if len(buf) < zeile * 16 or len(buf) % zeile:
        _FRAME_BGR_CACHE[_k] = None
        return None
    _a = np.frombuffer(buf, dtype=np.uint8).reshape(-1, int(w), 3).copy()
    if len(_FRAME_BGR_CACHE) < 400:          # ~250 KB je Bild, Deckel ~100 MB
        _FRAME_BGR_CACHE[_k] = _a
    return _a


def _frame_bgr_vorab(video_path, ts, w=384):
    """v227a Viele Einzelbilder GLEICHZEITIG holen statt eins nach dem anderen.

    Die Zeige-Regie prueft bis zu 40 Momente, die Hand-Regie bis zu 12 - jede
    Probe war ein eigener ffmpeg-Start, streng hintereinander. Das ist reine
    Wartezeit: jeder Start liest die Datei unabhaengig, sie blockieren sich
    nicht. Die Argumente sind identisch, also ist das Ergebnis BITGLEICH -
    hier wird nichts anders gemessen, nur nicht mehr nacheinander gewartet.
    Scheitert der Pool, laeuft der alte Weg (jeder Aufruf holt selbst)."""
    _offen = [t for t in ts
              if (video_path, round(float(max(t, 0.0)), 3), int(w))
              not in _FRAME_BGR_CACHE]
    if len(_offen) < 2:
        return
    try:
        from concurrent.futures import ThreadPoolExecutor
        _n = max(2, min(6, (os.cpu_count() or 2)))
        with ThreadPoolExecutor(max_workers=_n) as _ex:
            list(_ex.map(lambda _t: _frame_bgr(video_path, _t, w), _offen))
    except Exception:
        pass


def _rand_ziel(ox, oy, dx, dy, W, H, anteil=0.55):
    """Strahl (ox, oy) + s*(dx, dy) bis zum Bildrand verfolgen und einen Punkt
    auf dem Weg dorthin zurueckgeben. Nicht den Rand selbst: dort waere kein
    Platz fuer den Block, und gemeint ist die Richtung, nicht die Kante."""
    s = None
    for (komp, o, lo, hi) in ((dx, ox, 0.0, float(W)), (dy, oy, 0.0, float(H))):
        if abs(komp) < 1e-9:
            continue
        for grenze in (lo, hi):
            k = (grenze - o) / komp
            if k > 1e-6 and (s is None or k < s):
                s = k
    if s is None:
        return None
    return (ox + dx * s * anteil, oy + dy * s * anteil)


def _zeige_strahl(hand, W, H):
    """Zeigt diese Hand? hand = Landmark-Liste des MediaPipe-Modells
    (normierte Koordinaten). Rueckgabe (tx, ty) in Pixeln oder None.

    Gestreckt/eingerollt wird ueber die Distanz zum HANDGELENK gemessen: eine
    gestreckte Fingerspitze ist weiter vom Gelenk weg als ihr eigenes
    Mittelgelenk, eine eingerollte naeher. Das ist unabhaengig davon, wie die
    Hand im Bild gedreht liegt - ein Vergleich gegen die Senkrechte waere es
    nicht."""
    def d(a, b):
        return math.hypot((a.x - b.x) * W, (a.y - b.y) * H)

    wr = hand[_HAND_WRIST]
    spanne = max(d(wr, hand[9]), 1e-6)          # Handflaeche als Massstab
    gestreckt = [d(hand[tip], wr) > d(hand[pip], wr) * 1.12
                 for (tip, pip) in _HAND_FINGER]
    # Zeigefinger raus, hoechstens EIN weiterer daneben (der Zwei-Finger-Zeig
    # ist genauso eindeutig). Eine offene Hand ist eine Geste, kein Zeigen.
    if not gestreckt[0] or sum(1 for g in gestreckt[1:] if g) > 1:
        return None
    mcp, tip = hand[5], hand[8]
    dx = (tip.x - mcp.x) * W
    dy = (tip.y - mcp.y) * H
    laenge = math.hypot(dx, dy)
    # Zeigt der Finger in die Kamera, ist seine Projektion kurz - dann gibt es
    # im Bild kein Ziel und Raten waere schlimmer als nichts.
    if laenge < spanne * 0.45:
        return None
    return _rand_ziel(tip.x * W, tip.y * H, dx / laenge, dy / laenge, W, H)


def _blick_strahl(kp, W, H):
    """Kopfdrehung aus den sechs Gesichts-Keypoints des Detektors
    (rechtes Auge, linkes Auge, Nase, Mund, zwei Ohren). Rueckgabe (tx, ty)
    oder None.

    Die Nasenspitze wandert bei einer Drehung relativ zur Augenmitte in die
    Blickrichtung. Der Augenabstand ist dabei der Massstab, sonst haengt die
    Schwelle an der Kopfgroesse im Bild."""
    if len(kp) < 3:
        return None
    a_x = (kp[0].x + kp[1].x) / 2.0
    a_y = (kp[0].y + kp[1].y) / 2.0
    augen = abs(kp[0].x - kp[1].x)
    if augen < 1e-4:
        return None
    yaw = (kp[2].x - a_x) / augen
    # 0.35 Augenabstaende: darunter ist es Kopfhaltung, kein Hinsehen. Wer in
    # die Kamera spricht, meint keinen Ort im Bild - dann lieber kein Ziel.
    if abs(yaw) < 0.35:
        return None
    ri = 1.0 if yaw > 0 else -1.0
    return _rand_ziel(kp[2].x * W, a_y * H, ri, 0.0, W, H, anteil=0.60)


def _blick_yaw(kp):
    """Rohwert der Kopfdrehung: Nasenversatz zur Augenmitte in
    Augenabstaenden, plus Nasen-/Augenposition (normiert) fuer den Strahl.
    Rueckgabe (yaw, nase_x, augen_y) oder None."""
    if len(kp) < 3:
        return None
    a_x = (kp[0].x + kp[1].x) / 2.0
    a_y = (kp[0].y + kp[1].y) / 2.0
    augen = abs(kp[0].x - kp[1].x)
    if augen < 1e-4:
        return None
    return ((kp[2].x - a_x) / augen, kp[2].x, a_y)


def _blick_targets(cands, W, H):
    """v166: macht aus rohen Kopfdrehungen Blick-Ziele - RELATIV zur
    Grundhaltung des Sprechers, nicht absolut.

    Der v160-Fehler (Ismets Befund: "es ist immer noch links"): die absolute
    Schwelle 0.35 haelt nur Frontal-Sprecher auf. Wer sein Video mit leicht
    seitlich stehender Kamera aufnimmt, liegt in JEDEM Moment darueber -
    jeder Moment bekam dasselbe Blick-Ziel, das Ziel ueberstimmt die
    Seiten-Abwechslung, und ALLE Captions klebten auf einer Seite.
    Eine Haltung ist keine Regie. Regie ist die ABWEICHUNG davon:
    der Median der gemessenen Drehungen ist die Grundhaltung, nur wer
    deutlich darueber hinaus dreht (und zwar in die Richtung, in die er
    schaut), meint wirklich einen Ort im Bild.

    cands = [(t, yaw, nase_x, augen_y)] (normierte Koordinaten)."""
    if not cands:
        return []
    yaws = [c[1] for c in cands]
    stabil = len(yaws) >= 3
    med = float(np.median(yaws)) if stabil else 0.0
    out = []
    for (t, yaw, nx, ay) in cands:
        if abs(yaw) < 0.35:
            continue                     # praktisch frontal: niemand gemeint
        if stabil:
            dev = yaw - med
            # Abweichung von der eigenen Grundhaltung, nicht vom Nullpunkt.
            # Sitzt der Kopf IMMER bei +0.5, ist med +0.5 und dev ~0 - alle
            # diese "Ziele" fallen weg. Genau das ist der Zweck.
            if abs(dev) < 0.25:
                continue
            # Die Abweichung muss in die BLICKrichtung gehen. Wer aus einer
            # Rechts-Haltung zurueck zur Kamera dreht, schaut nirgendwohin.
            if (dev > 0) != (yaw > 0):
                continue
        elif abs(yaw) < 0.55:
            # Unter 3 Messungen gibt es keinen brauchbaren Median - dann
            # zaehlt nur eine wirklich deutliche Drehung.
            continue
        ri = 1.0 if yaw > 0 else -1.0
        z = _rand_ziel(nx * W, ay * H, ri, 0.0, W, H, anteil=0.60)
        if z is not None:
            out.append((float(t), float(z[0]), float(z[1]), 'blick'))
    return out


def _ziel_dedupe(ziele, W, halten=2):
    """v167: eine GEHALTENE Geste ist EINE Ansage, nicht viele.

    Ismets Befund (am Bild belegt): der Sprecher haelt den Arm ueber viele
    Momente in dieselbe Richtung - jeder Moment bekam dasselbe Ziel, und weil
    ein Ziel absichtlich Wunschzone und Seiten-Abwechslung ueberstimmt,
    klebten ALLE Captions auf dieser Seite. Die Ansage ist nach dem ersten
    Block laengst erfuellt; ab dann ist die gehaltene Pose Koerperhaltung,
    keine Regie mehr.

    Aufeinanderfolgende Ziele am praktisch selben Ort (x-Abstand unter
    0.12 W) bilden eine Gruppe; von jeder Gruppe bleiben die ersten `halten`
    Momente. Ein NEUES Ziel woanders beginnt eine neue Gruppe und zaehlt
    wieder voll - wer erst links und dann rechts hinzeigt, bekommt beides."""
    out = []
    g_x = None
    g_n = 0
    for z in sorted(ziele, key=lambda q: q[0]):
        if g_x is not None and abs(z[1] - g_x) < W * 0.12:
            g_n += 1
        else:
            g_x, g_n = z[1], 1
        if g_n <= halten:
            out.append(z)
    return out


# v174: Woerter, mit denen der Sprecher die Captions ANFASST. Sagt er sie,
# gehoert der Text in Reichweite der Hand - sonst laeuft die Geste ins
# Leere (Ismets Befund: "die hand erkennung und captions agieren nicht
# zusammen" - der Schub kam, der Text stand am anderen Bildrand).
_HAND_AKTION = ('push', 'pushes', 'pushed', 'shove', 'shoves', 'swipe',
                'swipes', 'schiebt', 'schieben', 'wegschieben', 'wischt',
                'wischen', 'anfasst', 'anfassen', 'beruehrt', 'beruehren')


def _hand_aktion_hit(text):
    """Beschreibt der Text eine Hand-Aktion an den Captions?"""
    return any(_anim_hit(text, k) for k in _HAND_AKTION)


def hand_ziele(video_path, times, W, H, proben=(0.05, 0.25, 0.45)):
    """v174: Position der HAND an den uebergebenen Zeitpunkten - fuer
    Momente, in denen der Sprecher die Captions anfasst ("push them away").
    Anders als beim Zeigen zaehlt hier JEDE erkannte Hand, nicht nur der
    gestreckte Finger: wer schiebt, hat die Hand offen.
    Rueckgabe [(t, x, y, 'zeigen')] - als Zeige-Ziel, damit Platzierung,
    Dedupe und Hysterese denselben Weg nehmen wie in v160/v167."""
    ziele = []
    if not times:
        return ziele
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
    except Exception:
        return ziele
    hpath = os.path.join(HERE, 'models/hand.task')
    if not os.path.exists(hpath):
        return ziele
    try:
        lm = mp_vision.HandLandmarker.create_from_options(
            mp_vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=hpath),
                num_hands=2, min_hand_detection_confidence=0.4))
    except Exception:
        return ziele
    if proben:                       # v227a: erste Probe fuer alle Zeiten parallel
        _frame_bgr_vorab(video_path, [float(t) + proben[0] for t in times])
    for t in times:
        pos = None
        for dt in proben:
            fr = _frame_bgr(video_path, float(t) + dt)
            if fr is None:
                continue
            try:
                img = mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(fr[..., ::-1]))
                res = lm.detect(img)
            except Exception:
                continue
            for hand in ((res.hand_landmarks if res else None) or []):
                # Handflaechen-Mitte (Mittelfinger-Grundgelenk) statt einer
                # Fingerspitze: die Spitze zittert, das Gelenk steht.
                pos = (hand[9].x * W, hand[9].y * H)
                break
            if pos is not None:
                break
        if pos is not None:
            ziele.append((float(t), float(pos[0]), float(pos[1]), 'zeigen'))
    try:
        lm.close()
    except Exception:
        pass
    if ziele:
        print(f"Hand action: {len(ziele)} caption(s) placed within reach "
              f"of the hand")
    return ziele


def zeige_ziele(video_path, times, W, H, proben=(0.10, 0.30, 0.55)):
    """v160: misst zu jedem Moment-Zeitpunkt, wohin der Sprecher zeigt oder
    schaut. Rueckgabe [(t, tx, ty, art)] mit art 'zeigen' | 'blick'.

    Laeuft NUR auf den uebergebenen Zeitpunkten, nicht ueber das ganze Video -
    drei kleine Frames je Moment. Ohne mediapipe oder ohne models/hand.task
    bleibt die Liste leer und das Feature ist still aus."""
    ziele = []
    if not times:
        return ziele
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
    except Exception:
        return ziele
    hpath = os.path.join(HERE, 'models/hand.task')
    fpath = os.path.join(HERE, 'models/face.tflite')
    lm = det = None
    try:
        if os.path.exists(hpath):
            lm = mp_vision.HandLandmarker.create_from_options(
                mp_vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=hpath),
                    num_hands=2, min_hand_detection_confidence=0.4))
        if os.path.exists(fpath):
            det = mp_vision.FaceDetector.create_from_options(
                mp_vision.FaceDetectorOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=fpath),
                    min_detection_confidence=0.4))
    except Exception:
        lm = det = None
    if lm is None and det is None:
        return ziele
    n_z = 0
    blick_cands = []
    # v227a: die erste Probe fuer ALLE Momente parallel holen. Dort faellt fast
    # die ganze Arbeit an (die meisten Momente sind mit dem ersten Bild
    # entschieden); die restlichen Proben holt die Schleife wie bisher selbst.
    if proben:
        _frame_bgr_vorab(video_path, [float(t) + proben[0] for t in times])
    for t in times:
        treffer = None
        blick = None
        for dt in proben:
            fr = _frame_bgr(video_path, float(t) + dt)
            if fr is None:
                continue
            fh, fw = fr.shape[:2]
            try:
                img = mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(fr[..., ::-1]))
            except Exception:
                continue
            if lm is not None and treffer is None:
                try:
                    res = lm.detect(img)
                except Exception:
                    res = None
                for hand in ((res.hand_landmarks if res else None) or []):
                    z = _zeige_strahl(hand, W, H)
                    if z is not None:
                        treffer = ('zeigen', z)
                        break
            if treffer is not None:
                break
            if det is not None and blick is None:
                try:
                    dres = det.detect(img)
                except Exception:
                    dres = None
                for dd in ((dres.detections if dres else None) or []):
                    y = _blick_yaw(list(getattr(dd, 'keypoints', []) or []))
                    if y is not None:
                        blick = y
                        break
        # Zeigen schlaegt Blick: eine Hand ist eine Ansage, ein Kopf eine
        # Tendenz. Zeige-Ziele stehen sofort fest; Blicke werden erst
        # GESAMMELT und nach dem Durchlauf gegen die Grundhaltung des
        # Sprechers gefiltert (_blick_targets, v166) - sonst wird eine
        # seitlich stehende Kamera zum Dauer-Ziel und alle Captions kleben
        # auf einer Seite.
        if treffer is not None:
            _, (tx, ty) = treffer
            ziele.append((float(t), float(tx), float(ty), 'zeigen'))
            n_z += 1
        elif blick is not None:
            blick_cands.append((float(t), blick[0], blick[1], blick[2]))
    blick_ziele = _blick_targets(blick_cands, W, H)
    ziele.extend(blick_ziele)
    ziele = _ziel_dedupe(ziele, W)
    n_z = sum(1 for z in ziele if z[3] == 'zeigen')
    n_b = len(ziele) - n_z
    for obj in (lm, det):
        try:
            if obj is not None:
                obj.close()
        except Exception:
            pass
    if ziele:
        print(f"Pointing direction: {n_z} pointing, {n_b} gaze targets "
              f"out of {len(times)} moments")
    return ziele


class HandTracker:
    """MediaPipe-HandLandmarker, lazy + fehlertolerant. detect() liefert
    Fingerspitzen [(x, y, vx, vy)] in Voll-Pixeln; v in px/s aus dem letzten
    Aufruf (Nearest-Match). Ohne Modell/mediapipe bleibt ok=False - das
    Feature ist dann still aus (kein Crash, kein Fallback-Fake)."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.ok = False
        self.prev = []
        self.prev_t = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            mpath = os.path.join(HERE, 'models/hand.task')
            if not os.path.exists(mpath):
                return
            self.mp = mp
            self.lm = mp_vision.HandLandmarker.create_from_options(
                mp_vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=mpath),
                    num_hands=2, min_hand_detection_confidence=0.4))
            self.ok = True
        except Exception:
            self.ok = False

    def detect(self, frame_u8, t):
        if not self.ok:
            return []
        try:
            sw = 320
            sh = max(int(self.H * sw / self.W), 32)
            small = cv2.resize(frame_u8, (sw, sh))
            img = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                                data=np.ascontiguousarray(small[..., ::-1]))
            res = self.lm.detect(img)
        except Exception:
            return []
        tips = []
        for hand in (res.hand_landmarks or []):
            for i in HAND_TIPS:
                tips.append([hand[i].x * self.W, hand[i].y * self.H, 0.0, 0.0])
        # Geschwindigkeit: Nearest-Match gegen den letzten Aufruf
        if self.prev and self.prev_t is not None and t > self.prev_t:
            dt = t - self.prev_t
            r_max = self.W * 0.12
            for tp in tips:
                best = min(self.prev,
                           key=lambda q: (q[0] - tp[0]) ** 2 + (q[1] - tp[1]) ** 2)
                d = math.hypot(best[0] - tp[0], best[1] - tp[1])
                if d < r_max:
                    tp[2] = (tp[0] - best[0]) / dt
                    tp[3] = (tp[1] - best[1]) / dt
        self.prev = [list(tp) for tp in tips]
        self.prev_t = t
        return [tuple(tp) for tp in tips]


def hand_contacts(plans, tips, t, W, H):
    """v101j: prueft aktive Momente gegen die Fingerspitzen. Trifft eine
    bewegte Spitze die Text-Box, bekommt der Plan EINEN Impuls (_hand_hit,
    px/s) - mit Cooldown, damit ein liegender Finger nicht dauerfeuert.
    Rueckgabe: Anzahl neuer Kontakte."""
    n = 0
    for p in plans:
        if not (p['start'] - 0.05 <= t <= p['end'] + 0.3):
            continue
        if p.get('arr') is not None and 'kw_i' in p:
            cx = p.get('cx')
            cy = p.get('cy', p.get('by'))
            if cx is None or cy is None:
                continue
            w = p['arr'].shape[1] * 0.55 + 20
            h = p['arr'].shape[0] * 0.55 + 20
        elif p.get('front'):
            # v176: Flow-Chunk. Er hat kein einzelnes 'arr', sondern viele
            # Wort-Sprites - die Box kommt aus deren Huelle. Ohne diesen
            # Zweig konnte ein Fuellwort-Block nie beruehrt werden, und
            # genau dort sass Ismets "push them away".
            _its = [it for it in p['front'] if it.get('arr') is not None]
            if not _its:
                continue
            _x0 = min(it['cx'] - it['arr'].shape[1] / 2.0 for it in _its)
            _x1 = max(it['cx'] + it['arr'].shape[1] / 2.0 for it in _its)
            _y0 = min(it['cy'] - it['arr'].shape[0] / 2.0 for it in _its)
            _y1 = max(it['cy'] + it['arr'].shape[0] / 2.0 for it in _its)
            cx, cy = (_x0 + _x1) / 2.0, (_y0 + _y1) / 2.0
            w = (_x1 - _x0) * 0.55 + 20
            h = (_y1 - _y0) * 0.55 + 20
        else:
            continue
        # v177 ANGESAGTER WISCH. Am echten Render gemessen (Job d70adb09):
        # der Sprecher wischt bei 861 px/s quer durchs Bild, aber SEIN
        # KOERPER steht dort, wo die Hand entlangfaehrt - die Caption kann
        # dort gar nicht liegen (Gesichtssperre 2.5 schlaegt das
        # Hand-Ziel 2.2, und das ist richtig so). Auf Pixel-Beruehrung zu
        # warten heisst deshalb: die Geste bleibt fuer immer folgenlos.
        # Sagt der Satz die Handlung ("I can just push them away") UND ist
        # ein schneller Wisch messbar, bekommt der Block den Impuls in
        # Wisch-Richtung - Ansage plus Messung, nichts geraten.
        if p.get('_hand_geste') and t - p.get('_hand_cool', -9.0) > 0.35:
            _bv = max(tips, key=lambda q: math.hypot(q[2], q[3]))
            _bs = math.hypot(_bv[2], _bv[3])
            if _bs > W * 0.50:
                # v178 WUCHT NACH ANSAGE. Der Deckel W*1.2 stammt aus
                # v101j und ist fuer den ZUFAELLIGEN Kontakt gebaut: ein
                # Handzucken darf das Layout nicht zerlegen. Am Render
                # gemessen ergab er 27 px Ausschlag - ein Stups, kein
                # "push them AWAY". Wer die Handlung ansagt, hat sie
                # bestellt: eigener Deckel W*3.6 (dreifach).
                _s = min(_bs, W * 3.6) / max(_bs, 1e-6)
                p['_hand_hit'] = (_bv[2] * _s, _bv[3] * _s)
                p['_hand_stark'] = True
                p['_hand_cool'] = t
                p['_hand_touch_t'] = t
                n += 1
                continue
        # v179 NUR ECHTE BERUEHRUNG. Der Naeherungs-Treffer aus v174
        # (Reichweite 0.075 W) war ein Notbehelf: damals passierte gar
        # kein Kontakt, weil die Caption nie unter der Hand lag. Seit
        # v176 pruefen wir aber ALLE Flow-Chunks, und wer beim Sprechen
        # gestikuliert - also fast jeder - liess damit JEDE Caption im
        # Video zucken (Ismets Befund: "alle captions sind jetzt etwas
        # davon betroffen"). Der angesagte Schub braucht die Naeherung
        # seit v177/v178 nicht mehr; er laeuft oben ueber die Ansage.
        # Also gilt wieder die klare v101j-Regel: es zaehlt, was die Hand
        # WIRKLICH beruehrt.
        for (x, y, vx, vy) in tips:
            if not (abs(x - cx) < w and abs(y - cy) < h):
                continue
            speed = math.hypot(vx, vy)
            if speed > W * 0.10 and t - p.get('_hand_cool', -9.0) > 0.35:
                # Impuls gedeckelt: auch ein Wisch bleibt ein Stups
                _s = min(speed, W * 1.2) / max(speed, 1e-6)
                p['_hand_hit'] = (vx * _s, vy * _s)
                p['_hand_cool'] = t
                p['_hand_touch_t'] = t
                n += 1
            break
    return n


def hand_spring(p, t):
    """v101j: unterdaempfte Feder fuer den Beruehrungs-Impuls (Overshoot +
    Ausschwingen statt linearem Zurueckrutschen, v100-Massstab). Zustand in
    '_'-Keys (Alpha-Export-Snapshot-kompatibel). Rueckgabe (dx, dy)."""
    hit = p.pop('_hand_hit', None)
    hx = p.get('_hand_dx', 0.0)
    hy = p.get('_hand_dy', 0.0)
    hvx = p.get('_hand_vx', 0.0)
    hvy = p.get('_hand_vy', 0.0)
    _stark = bool(p.pop('_hand_stark', False)) or p.get('_hand_kraft')
    if hit is not None:
        # v178: ein ANGESAGTER Wisch traegt weiter als ein Streifschuss.
        _g = 2.2 if _stark else 0.9
        hvx += hit[0] * _g
        hvy += hit[1] * _g
        if _stark:
            p['_hand_kraft'] = True
    if not (hx or hy or hvx or hvy):
        p['_hand_t'] = t
        return 0.0, 0.0
    dt = min(max(t - p.get('_hand_t', t), 0.0), 0.08)
    # v178: nach einer Ansage weichere Feder + weniger Daempfung -> der
    # Block fliegt weiter weg und schwingt sichtbar zurueck, statt sofort
    # einzurasten. Ohne Ansage bleibt es exakt bei den v101j-Werten.
    K, C = ((52.0, 5.2) if p.get('_hand_kraft')
            else (120.0, 9.0))               # unterdaempft -> sichtbarer Overshoot
    hvx += (-K * hx - C * hvx) * dt
    hvy += (-K * hy - C * hvy) * dt
    hx += hvx * dt
    hy += hvy * dt
    if abs(hx) < 0.15 and abs(hy) < 0.15 and abs(hvx) < 2 and abs(hvy) < 2:
        hx = hy = hvx = hvy = 0.0
        p.pop('_hand_kraft', None)           # v178: Ruhelage -> Kraft-Modus aus
    p['_hand_dx'], p['_hand_dy'] = hx, hy
    p['_hand_vx'], p['_hand_vy'] = hvx, hvy
    p['_hand_t'] = t
    return hx, hy


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


_ANKER_FUELL = {'me', 'us', 'you', 'my', 'the', 'a', 'an', 'on', 'in', 'at',
                'to', 'of', 'this', 'that', 'it', 'here', 'there', 'right',
                'now', 'mir', 'uns', 'dir', 'mich', 'dem', 'der', 'die', 'das',
                'den', 'ein', 'eine', 'im', 'am', 'an', 'auf', 'unter', 'ueber',
                'über', 'kopf', 'hier', 'da', 'jetzt'}


def anker_wort(txt):
    """v221 DAS ORTSWORT EINER ANSAGE.

    Ismets Idee: "es waere ja auch eine Option, dass es schon da darauf steht.
    Beispielsweise das Wort Wall. Und das andere baut sich drum herum auf."
    Genau dafuer braucht die Ansage ein Ankerwort: aus 'ON THE WALL' wird
    'WALL', aus 'BEHIND ME' 'BEHIND', aus 'ABOVE ME' 'ABOVE'. Genommen wird
    das LETZTE inhaltstragende Wort - es benennt den Ort ('wall', 'ground',
    'water'); Praepositionen und Selbstbezuege tragen ihn nicht.
    Rueckgabe: das Wort in der Schreibung des Kartentexts, oder None."""
    teile = [w for w in str(txt or '').split() if w.strip()]
    if len(teile) < 2:
        return None                       # ein Wort ist schon sein eigener Anker
    for w in reversed(teile):
        if clean(w).lower().strip('.,!?;:') not in _ANKER_FUELL:
            return w
    return None


def wall_pose(depth_n, cx, cy, bw, bh, W, H):
    """v218 DIE WAND WIRD GEMESSEN, NICHT GERATEN.

    Ismets Befund am Render: "es sitzt nicht richtig an der Wand". Genau so
    war es gebaut - fuer LIEGENDEN Text misst `ground_pose` die echte Neigung
    der Flaeche aus der Tiefenkarte, fuer WAND-Text gab es das nicht: dort
    stand ein fester Winkel (`g_yaw = -6 oder +6`, im Wechsel je Moment) und
    ein fester Pitch. Sechs Grad in zufaelliger Richtung haben mit der Wand
    im Bild nichts zu tun - der Text lag davor statt darauf.

    Gemessen wird die WAAGERECHTE Fluchtrichtung: depth_n ist NAEHE, eine
    Wand, die nach links wegflieht, hat dort kleinere Werte. Daraus wird der
    Yaw (Drehung um die Hochachse), mit dem persp_warp den Text in die
    Wandebene legt. Rueckgabe: yaw in Grad, oder None, wenn keine klare
    seitliche Flucht messbar ist (dann bleibt der bisherige Wert)."""
    if depth_n is None:
        return None
    x1 = int(max(cx - bw, 0)); x2 = int(min(cx + bw, W))
    y1 = int(max(cy - bh, 0)); y2 = int(min(cy + bh, H))
    reg = depth_n[y1:y2, x1:x2]
    if reg.size < 400:
        return None
    reg = cv2.GaussianBlur(reg.astype(np.float32), (0, 0), 4)
    gx = float(np.median(cv2.Sobel(reg, cv2.CV_32F, 1, 0, ksize=5)))
    gy = float(np.median(cv2.Sobel(reg, cv2.CV_32F, 0, 1, ksize=5)))
    # Eine WAND flieht seitlich. Ueberwiegt das senkrechte Gefaelle, schauen
    # wir auf Boden oder Decke - dafuer ist ground_pose zustaendig.
    if abs(gx) < abs(gy) * 1.2 or abs(gx) < 1e-5:
        return None
    # Wie stark verkuerzt sich die Flaeche? Die Spannweite der Naehe ueber
    # die Breite ist ein direktes Mass fuer den Blickwinkel.
    span = float(np.percentile(reg, 90) - np.percentile(reg, 10))
    stark = max(0.0, min(1.0, span * 2.2))
    # gx < 0: Naehe faellt nach rechts -> die rechte Seite ist weiter weg
    # und muss nach hinten kippen (persp_warp: yaw > 0).
    # v224b DER WINKEL IST GEDECKELT, WEIL SCHRIFT KEINE TEXTUR IST.
    # v218 liess bis 46 Grad zu. Am Beweisbild gemessen zerfallen die
    # Buchstaben dort: bei -33 Grad wurde aus 'WALL' ein 'WAI I', weil
    # persp_warp die abgewandte Seite auf einen Bruchteil staucht und das
    # Antialiasing die Strichenden auffrisst. Eine Wand darf man perspektivisch
    # andeuten - lesbar bleiben muss der Text trotzdem, sonst ist der Effekt
    # gegen sich selbst gerichtet. 20 Grad sind deutlich sichtbar und noch
    # sauber (am Sprite gemessen: Strichenden bleiben geschlossen).
    yaw = (1.0 if gx < 0 else -1.0) * (7.0 + 13.0 * stark)
    return max(-20.0, min(20.0, yaw))


def wall_typo(S, txt, flw, flh, W, H, extrude=False):
    """v224 EIN WANDSCHRIFTZUG WIRD GESETZT, NICHT GESCHRUMPFT.

    Ismets Befund am v223-Render: "sitzt auf der Wand, sieht aber echt
    unstrukturiert aus, muss eventuell etwas kleiner". Beides kam aus
    derselben Ursache: v223 nahm die FERTIGE, fast bildbreite Zeile und
    stauchte sie auf die Flaeche (bis 45 %). Das ergibt eine winzige,
    randfuellende Zeile ohne Luft - typografisch nichts, nur klein.

    Ein Schriftzug AN einer Wand ist mehrzeilig: die Fläche gibt die Breite
    vor, der Text bricht um, die Schrift bleibt gross. Gesetzt wird auf 72 %
    der Flaechenbreite, damit ein sichtbarer Rand bleibt - der Rand ist es,
    der 'strukturiert' aussieht.
    Rueckgabe: Sprite (RGBA) oder None."""
    worte = [w for w in str(txt or '').split() if w.strip()]
    if not worte or flw < W * 0.10:
        return None
    ziel = flw * 0.72
    # Zeilenzahl: so viele, dass die Schrift moeglichst gross bleibt, aber
    # hoechstens drei - mehr liest sich an einer Wand wie ein Absatz.
    beste = None
    for nz in (1, 2, 3):
        if nz > len(worte):
            break
        # Woerter moeglichst gleichmaessig auf nz Zeilen verteilen
        pro = math.ceil(len(worte) / nz)
        zeilen, i = [], 0
        while i < len(worte):
            zeilen.append(' '.join(worte[i:i + pro]))
            i += pro
        if len(zeilen) > nz:
            continue
        # Schriftgroesse, bei der die BREITESTE Zeile die Zielbreite trifft
        gr = min(S.fit(z, int(H * 0.16), int(ziel)) for z in zeilen)
        hoehe = gr * 1.12 * len(zeilen)
        if hoehe > flh * 0.62:
            continue                       # passt nicht in die Flaechenhoehe
        if beste is None or gr > beste[0]:
            beste = (gr, zeilen)
    if beste is None:
        return None
    gr, zeilen = beste
    teile = [S.text(z, gr, S.white, extrude=extrude)[0] for z in zeilen]
    wall_typo.zeilen = len(teile)          # der Aufrufer deckelt den Winkel danach
    # v224c MONTIERT WIRD AN DER TINTE, NICHT AN DER SCHRIFTGROESSE.
    # Ein Text-Sprite ist deutlich hoeher als seine Schriftgroesse (Glow- und
    # Schatten-Polster). Mit einem Zeilenabstand von gr*1.12 wurde jede Zeile
    # oben abgeschnitten - am Beweisbild zu sehen: von 'ON' und 'THE' stand nur
    # die untere Haelfte da. Gemessen wird deshalb die TINTE jeder Zeile, und
    # ueberlagert wird per Maximum, damit nichts wegfaellt.
    _ink = []
    for a in teile:
        _nz = np.where(a[..., 3] > 40)
        _ink.append((int(_nz[0].min()), int(_nz[0].max()), int(_nz[1].min()))
                    if len(_nz[0]) else (0, a.shape[0] - 1, 0))
    _ih = max(b - a0 + 1 for a0, b, _ in _ink)
    _step = int(_ih * 1.30)                # Zeilenfall am Schriftbild, nicht am em
    _res = max(a.shape[0] for a in teile)  # Reserve fuer das Polster
    hoehe = _step * (len(teile) - 1) + _res
    breite = max(a.shape[1] for a in teile) + max(x for _, _, x in _ink)
    out = np.zeros((hoehe, breite, 4), teile[0].dtype)
    for k, a in enumerate(teile):
        # linksbuendig auf einer gemeinsamen Achse: ein Wandschriftzug hat
        # eine Kante, an der er ausgerichtet ist - mittig gesetzte Zeilen
        # wirken wie ein Zitat, nicht wie Farbe an einer Wand. Ausgerichtet
        # wird die TINTE, nicht der Sprite-Rand.
        _y = k * _step - _ink[k][0]
        _x = -_ink[k][2] + max(x for _, _, x in _ink)
        _y0, _x0 = max(_y, 0), max(_x, 0)
        _sy, _sx = _y0 - _y, _x0 - _x
        _y1 = min(_y0 + a.shape[0] - _sy, hoehe)
        _x1 = min(_x0 + a.shape[1] - _sx, breite)
        if _y1 <= _y0 or _x1 <= _x0:
            continue
        _cut = a[_sy:_sy + (_y1 - _y0), _sx:_sx + (_x1 - _x0)]
        np.maximum(out[_y0:_y1, _x0:_x1], _cut, out=out[_y0:_y1, _x0:_x1])
    # v224c SYMMETRISCH POLSTERN. persp_warp polstert nach der BREITE
    # (w*0.12+20) - bei einem hohen, mehrzeiligen Block reicht das oben und
    # unten nicht, und die erste Zeile wurde abgeschnitten (am Beweisbild zu
    # sehen: von 'ON' blieb die untere Haelfte). Einseitig zu polstern waere
    # ausserdem ein Positionsfehler (v194): der Zeichenpfad setzt das Sprite
    # mittig, jedes ungleiche Polster verschiebt es.
    _pad = int(hoehe * 0.22) + 8
    return cv2.copyMakeBorder(out, _pad, _pad, _pad, _pad,
                              cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))


def wall_quad(depth_n, alpha, W, H):
    """v225 DAS WAND-VIERECK. Ismets Befund am v224-Bild: "es ist jetzt auf der
    Wand, aber es hat die falschen Winkel".

    Er hat recht, und ein einzelner Winkel konnte das nie leisten: eine Wand
    im Bild ist ein TRAPEZ mit Fluchtlinien - die Oberkante faellt, die
    Unterkante steigt, beide laufen auf einen Fluchtpunkt zu. `persp_warp(yaw)`
    verkuerzt nur eine Seite und laesst die Zeilen waagerecht; genau deshalb
    sah der Schriftzug aufgeklebt aus statt an der Wand.
    Gemessen wird deshalb die FLAECHE als Viereck. Rueckgabe: 4x2-Array
    (oben-links, oben-rechts, unten-rechts, unten-links) oder None."""
    if depth_n is None:
        return None
    d = cv2.resize(depth_n.astype(np.float32), (96, 128))
    d = cv2.GaussianBlur(d, (0, 0), 2.0)
    gx = np.abs(cv2.Sobel(d, cv2.CV_32F, 1, 0, ksize=5))
    gy = np.abs(cv2.Sobel(d, cv2.CV_32F, 0, 1, ksize=5))
    stark = float(np.percentile(gx, 80))
    if stark < 1e-4:
        return None
    m = ((gx > stark * 0.45) & (gx > gy * 1.2)).astype(np.uint8)
    if alpha is not None:
        pm = cv2.resize(person_mask(alpha).astype(np.float32), (96, 128))
        m[pm > 0.30] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    if cv2.contourArea(c) < 96 * 128 * 0.04:
        return None
    # v225a DAS TRAPEZ WIRD AUS DEN SPALTENHOEHEN KONSTRUIERT.
    # Ismets Befund: "die Schrift muss genau in die andere Richtung mit dem
    # Winkel". Die Richtung kam bis hier aus dem VORZEICHEN eines
    # Sobel-Medians - und die Orientierung davon hatte ich verwechselt; ein
    # Vorzeichen ist auch kein Beleg, sondern eine Behauptung. Ausserdem waren
    # die Ecken aus den Kontur-Extremwerten zu rechteckig (gemessen 180->190
    # statt 120->200), weil die Maske an den Raendern beschnitten wird.
    # Beides loest dieselbe Konstruktion: fuer die linke und die rechte Spalte
    # der Flaeche wird gemessen, WIE HOCH sie im Bild ist und WO ihre Mitte
    # liegt. Die im Bild kuerzere Seite ist die weiter entfernte - daraus
    # ergeben sich Fluchtlinien UND Richtung zwingend aus der Geometrie,
    # ohne Vorzeichen-Raterei.
    _msk = np.zeros((128, 96), np.uint8)
    cv2.drawContours(_msk, [c], -1, 1, thickness=-1)
    _sp = np.where(_msk.any(axis=0))[0]
    if len(_sp) < 6:
        return None
    _x0, _x1 = int(_sp.min()), int(_sp.max())

    def _spalte(x):
        _ys = np.where(_msk[:, x])[0]
        if not len(_ys):
            return None
        return float(_ys.min()), float(_ys.max())
    # v225b DIE VERKUERZUNG KOMMT AUS DER NAEHE, NICHT AUS DER MASKENHOEHE.
    # Die Maske stammt aus dem Gradienten und hoert VOR der echten Wandkante
    # auf - oben und unten gleich weit, wodurch das Trapez zum Rechteck wird
    # (gemessen: Oberkante 179->190 statt 120->200). Die Tiefe dagegen sagt
    # eindeutig, welche Seite weiter weg ist, und Perspektive heisst: die
    # entferntere Seite ist im Bild KUERZER. Damit ist die Richtung
    # geometrisch begruendet statt aus einem Vorzeichen geraten - genau der
    # Punkt in Ismets Befund "die Schrift muss genau in die andere Richtung".
    _dk = cv2.resize(depth_n.astype(np.float32), (96, 128))
    # Gemessen wird ueber SPALTEN-MEDIANE der linken und rechten Haelfte, nicht
    # an den Randspalten. Die Maske reicht ueber die Wandkante hinaus (dort ist
    # der Gradient am groessten) - genau dort ist die Tiefe 0, und ein
    # Mittelwert an der Aussenspalte kam deshalb als 0.0 zurueck und liess die
    # Messung durchfallen. Nullwerte sind keine Flaeche und fliegen raus.
    _prof = []
    for _x in range(_x0, _x1 + 1):
        _v = _dk[:, _x][(_msk[:, _x] > 0) & (_dk[:, _x] > 0.02)]
        if len(_v) >= 3:
            _prof.append((_x, float(np.median(_v))))
    if len(_prof) < 6:
        return None
    _h = len(_prof) // 2
    _n0 = float(np.median([v for _, v in _prof[:_h]]))
    _n1 = float(np.median([v for _, v in _prof[_h:]]))
    _x0, _x1 = _prof[0][0], _prof[-1][0]
    _ca, _cb = _spalte(_x0), _spalte(_x1)
    if _ca is None or _cb is None or _n0 <= 1e-6 or _n1 <= 1e-6:
        return None
    # Naehe ist invers zur Entfernung: die Seite mit der KLEINEREN Naehe ist
    # weiter weg und wird kuerzer. Deckel 0.55, damit die Schrift lesbar bleibt.
    _k = max(0.55, min(_n1 / _n0, 1.0 / max(_n1 / _n0, 1e-6)))
    _mitte = ((_ca[0] + _ca[1]) / 2.0 + (_cb[0] + _cb[1]) / 2.0) / 2.0
    _hoehe = max((_ca[1] - _ca[0]), (_cb[1] - _cb[0]))
    if _n1 < _n0:                          # rechts weiter weg -> rechts kuerzer
        _h0, _h1 = _hoehe, _hoehe * _k
    else:                                  # links weiter weg -> links kuerzer
        _h0, _h1 = _hoehe * _k, _hoehe
    quad = np.array([[_x0, _mitte - _h0 / 2.0], [_x1, _mitte - _h1 / 2.0],
                     [_x1, _mitte + _h1 / 2.0], [_x0, _mitte + _h0 / 2.0]],
                    dtype=np.float32)
    quad[:, 0] *= W / 96.0
    quad[:, 1] *= H / 128.0
    # Entartete Vierecke (Strich, Dreieck) sind keine Flaeche.
    if (np.linalg.norm(quad[0] - quad[1]) < W * 0.06
            or np.linalg.norm(quad[0] - quad[3]) < H * 0.06):
        return None
    return quad


def wall_project(arr, quad, W, H, rand=0.12, oben=0.20, hoch=0.34):
    """v225 Legt ein Text-Sprite IN das Wand-Viereck - eine echte projektive
    Abbildung, also mit Fluchtlinien, Neigung und Verkuerzung in einem.
    `rand` laesst links/rechts Luft, `oben`/`hoch` waehlen das Band auf der
    Flaeche (Standard: oberes Drittel, Augenhoehe). Rueckgabe: bildgrosses
    RGBA-Sprite (Position steckt darin, also cx=W/2, cy=H/2)."""
    def _misch(a, b, f):
        return a + (b - a) * f

    ol, orr, ur, ul = quad
    def _pkt(fx, fy):
        # bilinear im Viereck: erst auf Ober- und Unterkante, dann dazwischen
        return _misch(_misch(ol, orr, fx), _misch(ul, ur, fx), fy)
    ziel = np.array([_pkt(rand, oben), _pkt(1.0 - rand, oben),
                     _pkt(1.0 - rand, oben + hoch), _pkt(rand, oben + hoch)],
                    dtype=np.float32)
    h, w = arr.shape[:2]
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, ziel)
    return cv2.warpPerspective(arr, M, (W, H), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=(0, 0, 0, 0))


def wall_area(depth_n, alpha, W, H):
    """v223 WO IST DIE WAND? Ismets Befund am v222-Render: "der wird gar nicht
    richtig auf der Wand platziert". Die NEIGUNG stimmte da schon (v219), die
    STELLE nicht - der Text landete halb ausserhalb am linken Bildrand, weil
    ihn die normale Platzierungs-Regie setzt: die kennt Gesichter und
    Bildunruhe, aber keine Wandflaeche.

    Gemessen wird die zusammenhaengende Flaeche, deren Tiefe sich WAAGERECHT
    aendert (eine Wand flieht seitlich) und auf der keine Person steht.
    Rueckgabe: (cx, cy, breite, hoehe) der Flaeche in Pixeln, oder None."""
    if depth_n is None:
        return None
    d = cv2.resize(depth_n.astype(np.float32), (96, 128))
    d = cv2.GaussianBlur(d, (0, 0), 2.0)
    gx = np.abs(cv2.Sobel(d, cv2.CV_32F, 1, 0, ksize=5))
    gy = np.abs(cv2.Sobel(d, cv2.CV_32F, 0, 1, ksize=5))
    # Wand = seitliches Gefaelle ueberwiegt deutlich, und es gibt ueberhaupt
    # ein Gefaelle (eine frontale Flaeche hat keine Ebene, in die man legen
    # koennte - dort ist die normale Platzierung richtig).
    stark = float(np.percentile(gx, 80))
    if stark < 1e-4:
        return None
    m = ((gx > stark * 0.45) & (gx > gy * 1.2)).astype(np.uint8)
    if alpha is not None:
        pm = cv2.resize(person_mask(alpha).astype(np.float32), (96, 128))
        m[pm > 0.30] = 0                  # die Person ist keine Wand
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[k, cv2.CC_STAT_AREA] < 96 * 128 * 0.04:
        return None                       # zu kleiner Fleck, nicht verlaesslich
    sx, sy = W / 96.0, H / 128.0
    return (float(cent[k][0]) * sx, float(cent[k][1]) * sy,
            float(stats[k, cv2.CC_STAT_WIDTH]) * sx,
            float(stats[k, cv2.CC_STAT_HEIGHT]) * sy)


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
4. CHOREOGRAPHIE (Pacing 2026 - so unterscheidet sich teuer von billig):
   - BUENDELN statt Geballer: lieber EINE Phrase (n 2-4), die eine Aussage
     traegt, als drei Einzelwoerter kurz hintereinander. Wort-fuer-Wort-
     Dauerfeuer (200+ wpm Highlights) ist der Billig-Marker 2026.
   - PAUSEN HALTEN: nach einem power-3-Moment mindestens einen Satz lang
     NICHTS Grosses setzen - die Stille verkauft den Moment davor.
   - POPS NUR AUF SCHLUESSELWOERTER: zoom_punch/knall/explosion maximal auf
     die 2-3 Woerter, die das Video tragen. Alles andere ruhig oder gar nicht.
   - EIN Farb-/Stil-Wechsel sitzt auf dem WENDEPUNKT der Geschichte (Twist/
     Aufloesung), nicht zufaellig verteilt.
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


def _gross_klasse(werte):
    """v230c5: Median der GROSSEN Textteile einer Referenz-Messung.

    Rueckgabe: die TYPISCHE Schluesselwort-Groesse, oder None wenn sich keine
    grosse Gruppe abhebt (dann gilt der alte Weg).

    Warum nicht das 96. Perzentil: das ist die PUNCHLINE, die eine groesste
    Stelle im ganzen Vorbild. Als Grundmass angewandt blaest es JEDES grosse
    Wort auf Punchline-Groesse auf - genau das war Ismets 'STECKT'.

    Warum nicht Otsu (die Schwelle mit der groessten Trennung): nachgerechnet
    an einer realistischen Verteilung (70 Teile Fliesstext 0.020 H, 25
    Schluesselwoerter 0.060 H, 3 Punchlines 0.185 H) faellt die beste
    Zwei-Klassen-Trennung zwischen Schluesselwort und PUNCHLINE (Varianz 6.80
    gegen 5.59) - Otsu haette also genau den Wert geliefert, den wir loswerden
    wollen. Die Verteilung hat drei Moden, nicht zwei.

    Deshalb von UNTEN her: der Fliesstext ist die dichteste Gruppe, alles
    deutlich darueber ist 'gross'. Die Schwelle 1.8x sitzt sicher zwischen
    beiden - in den gemessenen Vorbildern ist das Verhaeltnis Schluesselwort
    zu Fliesstext 2.2 bis 4.6 (v143/v184). Der MEDIAN der grossen Gruppe ist
    dann gegen einzelne Riesen unempfindlich, und genau darum geht es."""
    x = np.asarray(werte, dtype=np.float64).ravel()
    if x.size < 10:
        return None
    klein = float(np.percentile(x, 35))
    if klein <= 0:
        return None
    oben = x[x >= klein * 1.8]
    if oben.size < 3:
        return None
    return float(np.median(oben))


def measure_reference_video(video_path, max_frames=160):
    """v144: MISST den Stil eines Referenzvideos aus den Pixeln - deterministisch,
    ohne KI, ohne API-Key.

    Warum das die KI ersetzt und nicht ergaenzt: bis v143 lief das Stil-Lernen
    ueber eine Prosa-Beschreibung von GPT-5 Vision, aus der eine zweite Anfrage
    sechs Zahlen SCHAETZTE. Groesse, Position, Hierarchie, Schrift, Glow und
    Timing kamen darin gar nicht vor - und geschaetzte Zahlen aus 6 Frames mit
    'detail: low' sind ohnehin keine Messung. Alles Folgende ist dagegen direkt
    aus dem Bild gerechnet und reproduzierbar.

    Rueckgabe: dict mit Messwerten (Anteile von Breite/Hoehe, damit sie auf
    jedes Zielformat uebertragbar sind) oder {} wenn nichts messbar war.
    """
    if not os.path.exists(video_path):
        return {}
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {}
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    while len(frames) < max_frames:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if len(frames) < 8 or W < 16 or H < 16:
        return {}

    # DAUER-ELEMENTE (Plattform-Wasserzeichen, Sender-Logo) zeitlich finden
    # statt an einer geratenen Stelle auszuschneiden: was in fast JEDEM Frame
    # an derselben Stelle hell ist, ist kein Caption-Text. Funktioniert damit
    # fuer TikTok, Reels, Shorts und jedes Kanal-Logo gleichermassen.
    _sum = np.zeros((H, W), dtype=np.float32)
    for f in frames[::max(1, len(frames) // 40)]:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        _sum += (((hsv[..., 2] >= 244) & (hsv[..., 1] <= 26))
                 | ((hsv[..., 2] >= 195) & (hsv[..., 1] >= 140))).astype(np.float32)
    _n = max(1, len(frames[::max(1, len(frames) // 40)]))
    dauerhaft = (_sum / _n > 0.85).astype(np.uint8)
    if dauerhaft.sum() > W * H * 0.06:        # zu viel -> unbrauchbar, verwerfen
        dauerhaft = None

    def maske(f):
        """Textpixel: sehr helles Weiss ODER kraeftig gesaettigter Akzent.
        Beides mit hoher Schwelle, damit heller Hintergrund nicht mitkommt."""
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        v = hsv[..., 2].astype(np.int16)
        s = hsv[..., 1].astype(np.int16)
        weiss = (v >= 244) & (s <= 26)
        bunt = (v >= 195) & (s >= 140)
        m = (weiss | bunt).astype(np.uint8)
        if dauerhaft is not None:
            m = m & (1 - dauerhaft)       # Wasserzeichen/Logo raus
        return m, bunt.astype(np.uint8)

    def _strich(bild, x, y, bw, bh):
        """Mediane Strichbreite im Teil, als Anteil seiner Hoehe. Buchstaben
        haben duenne, gleichmaessige Striche; eine helle Wand ist massiv."""
        aus = bild[y:y + bh, x:x + bw]
        laeufe = []
        for zy in range(0, bh, max(1, bh // 6)):
            run = 0
            for v in aus[min(zy, bh - 1)]:
                if v: run += 1
                elif run: laeufe.append(run); run = 0
            if run: laeufe.append(run)
        return (float(np.median(laeufe)) / float(bh)) if laeufe else 9.9

    def teile(m, min_flaeche=30):
        """Echte TEXTteile. Eine reine Helligkeitsschwelle reicht nicht: in
        einem warm ausgeleuchteten Raum sind Lampe und helle Wand ebenfalls
        hell und wenig gesaettigt. Gemessen am Referenzvideo lieferte die
        nackte Schwelle eine Zone bis 0.857 H und ein Groessenverhaeltnis von
        4.66 statt 2.4 - also unbrauchbar.
        Zwei zusaetzliche Merkmale trennen Schrift von Flaeche:
          FUELLGRAD  - Buchstaben fuellen ihr Rechteck nur zu 20-72 %,
                       eine Wand zu ueber 90 %.
          STRICHBREITE - Buchstabenstriche sind duenn und gleichmaessig
                       (6-40 % der Zeichenhoehe), eine Flaeche ist massiv.
        Das ist der Kern der Stroke-Width-Idee, auf das noetige reduziert."""
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 7), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        out = []
        for i in range(1, n):
            x, y, bw, bh, a = st[i]
            if a < min_flaeche or bh < H * 0.010 or bh > H * 0.20:
                continue
            if bw > W * 0.98 or bw < 3:
                continue
            fuell = a / float(max(bw * bh, 1))
            if not (0.14 <= fuell <= 0.74):
                continue
            if not (0.06 <= _strich(m, x, y, bw, bh) <= 0.40):
                continue
            out.append((x, y, bw, bh, a))
        # ZEILEN-BINDUNG. Schrift steht in Zeilen: jeder Buchstabe hat einen
        # Nachbarn auf derselben Grundlinie und in aehnlicher Groesse. Ein
        # Glanzpunkt auf der Wange, ein Lampenreflex oder eine Hemdfalte steht
        # allein. Am Referenzvideo waren genau das die Fehltreffer, die die
        # Zone bis 0.857 H zogen. Isolierte Teile fliegen deshalb raus.
        fest = []
        for i, (x, y, bw, bh, a) in enumerate(out):
            mi = y + bh / 2.0
            nachbar = False
            for j, (x2, y2, bw2, bh2, a2) in enumerate(out):
                if i == j:
                    continue
                if abs((y2 + bh2 / 2.0) - mi) > max(bh, bh2) * 0.55:
                    continue
                if not (0.45 <= bh2 / float(max(bh, 1)) <= 2.2):
                    continue
                luecke = max(x, x2) - min(x + bw, x2 + bw2)
                if luecke <= max(bh, bh2) * 1.6:
                    nachbar = True
                    break
            # Ein BREITES Teil ist auch ohne Nachbarn Schrift: ein ganzes Wort
            # oder eine Zeile verschmilzt beim Schliessen zu einem Block.
            # Reflexe sind dagegen rundlich. Ohne diese Ausnahme verwarf die
            # Zeilen-Bindung ganze Caption-Zeilen.
            if nachbar or bw >= bh * 2.5:
                fest.append((x, y, bw, bh, a))
        return fest

    # ZWEI DURCHGAENGE. Erst alle Kandidaten sammeln, dann das BAND finden,
    # in dem die Textmasse wirklich liegt, und nur darin messen.
    # Grund: einzelne Reflexe auf Gesicht und Lampe ueberstehen jeden lokalen
    # Filter, weil sie lokal wie Schrift aussehen. Sie streuen aber ueber das
    # ganze Bild, waehrend Captions in einem schmalen Band sitzen. Am
    # Referenzvideo zog genau das die gemessene Zone von 0.36 auf 0.59 H.
    _kand = []
    _zeilen = []
    for f in frames:
        m, _b = maske(f)
        ts = teile(m)
        for (x, y, bw, bh, a) in ts:
            _kand.append((y + bh / 2.0, a, bh))
        # ZEILEN je Frame gruppieren: Teile auf gemeinsamer Grundlinie. Eine
        # Zeile mit mindestens zwei Teilen ist sicher Schrift - ein einzelner
        # Glanzpunkt bildet nie eine Zeile. Das ist der Anker fuers Wachsen.
        for (x, y, bw, bh, a) in ts:
            mi = y + bh / 2.0
            gefaehrten = [t for t in ts
                          if abs((t[1] + t[3] / 2.0) - mi) <= max(bh, t[3]) * 0.55]
            if len(gefaehrten) >= 2:
                _zeilen.append((float(np.mean([t[1] + t[3] / 2.0 for t in gefaehrten])),
                                float(np.median([t[3] for t in gefaehrten]))))
    band = None
    if len(_kand) >= 20:
        ys = np.array([k[0] for k in _kand], dtype=np.float32)
        ws = np.array([k[1] for k in _kand], dtype=np.float32)
        ordn = np.argsort(ys)
        ys, ws = ys[ordn], ws[ordn]
        ges = float(ws.sum())
        kum = np.cumsum(ws)
        best, bl, br = None, 0.0, float(H)
        j = 0
        for i in range(len(ys)):
            while j < len(ys) and (kum[j] - (kum[i - 1] if i else 0.0)) < ges * 0.70:
                j += 1
            if j >= len(ys):
                break
            spanne = ys[j] - ys[i]
            if best is None or spanne < best:
                best, bl, br = spanne, float(ys[i]), float(ys[j])
        if best is not None:
            luft = max(H * 0.03, best * 0.25)
            bl, br = bl - luft, br + luft
            # BAND WACHSEN LASSEN. Das 70-Prozent-Fenster findet die
            # SCHWERSTE Stelle, nicht den ganzen Block: ein fettes
            # Schluesselwort traegt so viel Masse, dass die duenne
            # Fliesstext-Zeile darueber aus dem Band faellt - dann misst die
            # Funktion Schluessel gegen Schluessel und das Groessenverhaeltnis
            # wird 1.0. Deshalb zieht das Band anschliessend jede echte ZEILE
            # nach, die hoechstens 1.6 Zeilenhoehen entfernt steht.
            # Nur Zeilen (>= 2 Teile auf einer Grundlinie) duerfen ziehen -
            # ein einzelner Reflex auf Wange oder Lampe kann das Band damit
            # nicht aufziehen. Zusaetzlich harte Deckelung auf 0.40 H.
            if _zeilen:
                for _ in range(6):
                    drin = [z for z in _zeilen if bl <= z[0] <= br]
                    mh = float(np.median([z[1] for z in drin])) if drin else float(best or H * 0.05)
                    schritt = max(mh, H * 0.02) * 1.6
                    nah = [z for z in _zeilen
                           if bl - schritt <= z[0] <= br + schritt]
                    if not nah:
                        break
                    nl = min(bl, min(z[0] - z[1] / 2.0 for z in nah))
                    nr = max(br, max(z[0] + z[1] / 2.0 for z in nah))
                    if nr - nl > H * 0.40:
                        break
                    if nl >= bl - 1.0 and nr <= br + 1.0:
                        break
                    bl, br = nl, nr
            band = (bl, br)

    hoehen, zone_y, zone_x, flaechen = [], [], [], []
    akz_px, akz_anteil = [], []
    for f in frames:
        m, bunt = maske(f)
        ts = teile(m)
        if band is not None:
            ts = [t for t in ts if band[0] <= t[1] + t[3] / 2.0 <= band[1]]
        if not ts:
            flaechen.append(0)
            continue
        # NUR die akzeptierten Teile zaehlen - sonst faerbt der Hintergrund
        # jede Folgemessung ein (Zone, Groesse, Farbe, Takt).
        nur = np.zeros_like(m)
        for (x, y, bw, bh, a) in ts:
            nur[y:y + bh, x:x + bw] |= m[y:y + bh, x:x + bw]
            # KERN statt Kasten. Der Aussenschein macht ein Teil messbar
            # groesser: gemessen wuchs die Versalhoehe des Referenzvideos
            # dadurch von 0.085 auf 0.130 H. Fuer die Groesse zaehlt deshalb
            # nur der harte Buchstabenkern (hoehere Schwelle im Kasten).
            _k = _kern_hoehe(f, x, y, bw, bh)
            hoehen.append((_k if _k else bh) / float(H))
        flaechen.append(int(nur.sum()))
        zone_y.append((min(t[1] for t in ts) / H,
                       max(t[1] + t[3] for t in ts) / H))
        zone_x.append((min(t[0] for t in ts) / W,
                       max(t[0] + t[2] for t in ts) / W))
        b_nur = (bunt.astype(bool)) & (nur.astype(bool))
        if nur.sum() > 0:
            akz_anteil.append(float(b_nur.sum()) / float(nur.sum()))
        px = f[b_nur]
        if len(px) > 60:
            akz_px.append(np.percentile(px, 75, axis=0))
    if len(hoehen) < 12 or not zone_y:
        return {}

    res = {'quelle': os.path.basename(video_path),
           'format': round(W / float(H), 3)}
    # --- Groessen. Das groesste Textteil ist das Schluesselwort, das Feld der
    # kleinen Teile der Fliesstext. Perzentile statt max/min: ein einzelner
    # Ausreisser (Glanzpunkt, Logo-Rest) soll die Skala nicht bestimmen.
    hh = np.array(hoehen, dtype=np.float32)
    # v230c5: das 96. Perzentil ist NICHT die typische Schluesselwort-Groesse,
    # es ist die PUNCHLINE - die eine groesste Stelle im ganzen Vorbild. Genau
    # dieser Wert wurde zur Grundgroesse fuer JEDES grosse Wort. In Ismets Job
    # ergab das size=0.184H -> caption_scale 2.60, im Querformat nochmal x1.35,
    # und dann stand ein Fuellwort ('STECKT') so gross im Bild wie eine
    # Punchline. Derselbe Fehler wie v154, nur eine Zeile hoeher: dort traf es
    # den Fliesstext, hier das Schluesselwort.
    # Jetzt: die Hoehen in zwei Gruppen trennen (klein/gross) und den MEDIAN
    # der grossen Gruppe nehmen - das ist die typische Schluesselwort-Groesse.
    # Faellt die Trennung aus (zu wenige Werte, keine echte Struktur), gilt
    # der alte Weg. Ein Messwert, der nicht bestimmbar ist, wird geklemmt oder
    # faellt zurueck, nie verworfen (v151).
    _gr = _gross_klasse(hh)
    res['key_hoehe'] = round(float(_gr if _gr else np.percentile(hh, 96)), 4)
    res['klein_hoehe'] = round(float(np.percentile(hh, 35)), 4)
    if res['klein_hoehe'] > 0.002:
        res['verhaeltnis'] = round(res['key_hoehe'] / res['klein_hoehe'], 2)
    # --- Zone: wo im Bild steht der Text ueberhaupt
    zy = np.array(zone_y, dtype=np.float32)
    zx = np.array(zone_x, dtype=np.float32)
    res['zone_y'] = [round(float(np.percentile(zy[:, 0], 10)), 3),
                     round(float(np.percentile(zy[:, 1], 90)), 3)]
    res['zone_x'] = [round(float(np.percentile(zx[:, 0], 10)), 3),
                     round(float(np.percentile(zx[:, 1], 90)), 3)]
    res['zone_mitte_y'] = round(float(np.mean(res['zone_y'])), 3)
    # --- Ausrichtung: streuen die LINKEN Kanten weniger als die Mitten?
    l_streu = float(np.std(zx[:, 0]))
    m_streu = float(np.std((zx[:, 0] + zx[:, 1]) / 2.0))
    # VERHAELTNIS statt fester Differenz. Die alte Schwelle von 0.01 W war an
    # der Streuung EINES Videos geeicht: bei einem Block, der seine Breite nur
    # wenig aendert, liegen beide Streuungen unter 0.01 und die Ausrichtung
    # fiel auf 'frei' zurueck, obwohl die linken Kanten exakt buendig standen.
    # Der Quotient ist massstabsfrei; der Boden verhindert nur, dass reines
    # Messrauschen eine Aussage erzwingt.
    if max(l_streu, m_streu) < 0.004:
        res['ausrichtung'] = 'frei'
    elif l_streu < m_streu * 0.65:
        res['ausrichtung'] = 'links'
    elif m_streu < l_streu * 0.65:
        res['ausrichtung'] = 'mitte'
    else:
        res['ausrichtung'] = 'frei'
    # --- Akzentfarbe
    if akz_px:
        b, g, r = np.mean(np.array(akz_px), axis=0)
        res['akzent_hex'] = '#%02x%02x%02x' % (int(r), int(g), int(b))
        res['akzent_anteil'] = round(float(np.mean(akz_anteil)), 3)
    # --- Wort-Takt: wann waechst die Textflaeche sprunghaft?
    fl = np.array(flaechen, dtype=np.float32)
    ein = []
    for i in range(1, len(fl)):
        if fl[i - 1] > 40 and fl[i] > fl[i - 1] * 1.16 and fl[i] - fl[i - 1] > 220:
            ein.append(i / fps)
    if len(ein) >= 3:
        d = np.diff(np.array(ein))
        # Buchstaben-Reveal sauber abtrennen: die Referenz deckt mit rund
        # 80 ms je Buchstabe auf, Woerter folgen mit 160-360 ms. Die alte
        # Grenze von 40 ms liess die Buchstaben durch und zog den Wort-Takt
        # auf 0.081 s herunter.
        # Nur echte Wortabstaende: unter 0.12 s sind es Buchstaben, ueber
        # 0.9 s ist es der Sprung zum naechsten Block oder Schnitt.
        d = d[(d > 0.12) & (d < 0.9)]
        if len(d):
            res['wort_takt'] = round(float(np.median(d)), 3)
        fein = np.diff(np.array(ein))
        fein = fein[fein <= 0.12]
        if len(fein) >= 2:
            res['buchstaben_takt'] = round(float(np.median(fein)), 3)
    # --- Glow: Helligkeitsabfall um den Text herum
    res.update(_ref_glow(frames, W, H, maske, teile))
    # --- Strichstaerke der Referenzschrift (fuer die Font-Wahl)
    st = _ref_strichstaerke(frames, maske, H, teile)
    if st:
        res['stamm_versal'] = st
    # v230c8: Schrift-Kennzahlen GETRENNT nach grossem und kleinem Text.
    # Ismets Befund: "bei dynamischen Caption-Videos sind auch verschiedene
    # Schriften drin, die muessen ja auch nachgemacht werden." Stimmt - das
    # Schluesselwort ist fast immer ein anderer Schnitt als der Fliesstext.
    # Die Grenze ist dieselbe wie bei der Groessenmessung (v230c5): alles ab
    # dem 1.8-fachen des Fliesstext-Masses gilt als gross.
    _fk = _ref_font_klassen(frames, maske, H, teile,
                            grenze=res.get('klein_hoehe'))
    for _rolle in ('gross', 'klein'):
        if _fk.get(_rolle):
            res[f'font_mass_{_rolle}'] = list(_fk[_rolle])
    # --- SCHNITT + KAMERA (fehlte der Stil-Analyse bis v143 komplett)
    kam = _ref_kamera(frames, fps)
    res.update(kam)
    # --- TON (bis v143 nur ein Prosa-Satz)
    res.update(_ref_ton(video_path))
    if kam.get('schnitte_pro_s'):
        _n = int(round(kam['schnitte_pro_s'] * (len(frames) / float(fps))))
        _cz = [(_i + 1) / float(fps) for _i in range(len(frames) - 1)]
        # Schnittzeiten aus derselben Differenzreihe wie _ref_kamera holen
        _kl = [cv2.cvtColor(cv2.resize(f, (f.shape[1] // 3 or 1, f.shape[0] // 3 or 1)),
                            cv2.COLOR_BGR2GRAY) for f in frames]
        _d = np.array([float(np.mean(np.abs(_kl[i].astype(np.float32)
                                            - _kl[i - 1].astype(np.float32))))
                       for i in range(1, len(_kl))], dtype=np.float32)
        _thr = max(float(np.median(_d) + 4.0 * np.std(_d)), 18.0)
        _cuts = [(i + 1) / float(fps) for i in range(1, len(_d)) if _d[i] > _thr]
        res.update(_ref_schnitt_ton(video_path, _cuts))
    return res


def _ref_kamera(frames, fps):
    """v144: misst SCHNITT und KAMERA eines Referenzvideos.

    Beides fehlte der Stil-Analyse komplett - sie fragte GPT-5 nach Prosa und
    leitete daraus 'ruhig/normal/wuchtig' ab, was dann pauschal die
    Kamerastaerke verstellte. Am Referenzvideo waere das falsch gewesen:
    gemessen ist die Kamera dort RUHIG (Zoom 0.994 je Sekunde, Pan-Streuung
    0.83 %), die Energie kommt aus dem SCHNITT (0.54 Schnitte je Sekunde,
    mittlere Einstellung 1.38 s). Wer daraus 'wuchtig' liest und die Kamera
    aufdreht, trifft genau das Gegenteil des Vorbilds."""
    if len(frames) < 8 or fps <= 0:
        return {}
    klein = [cv2.cvtColor(cv2.resize(f, (f.shape[1] // 3 or 1, f.shape[0] // 3 or 1)),
                          cv2.COLOR_BGR2GRAY) for f in frames]
    d = np.array([float(np.mean(np.abs(klein[i].astype(np.float32)
                                       - klein[i - 1].astype(np.float32))))
                  for i in range(1, len(klein))], dtype=np.float32)
    if not len(d):
        return {}
    schwelle = max(float(np.median(d) + 4.0 * np.std(d)), 18.0)
    cuts = [i for i in range(1, len(d)) if d[i] > schwelle]
    # Frames rund um einen Schnitt sperren - der Sprung wuerde sonst als
    # gigantische Kamerafahrt durchgehen (gemessen 171 % Pan an einem Schnitt).
    sperr = set()
    for c in cuts:
        sperr.update(range(c - 3, c + 4))
    zoom, pan = [], []
    for i in range(1, len(klein)):
        if i in sperr:
            continue
        p0 = cv2.goodFeaturesToTrack(klein[i - 1], 250, 0.01, 7)
        if p0 is None:
            continue
        p1, st, _ = cv2.calcOpticalFlowPyrLK(klein[i - 1], klein[i], p0, None)
        if p1 is None:
            continue
        ok = st.ravel() == 1
        if ok.sum() < 15:
            continue
        M, _ = cv2.estimateAffinePartial2D(p0[ok].reshape(-1, 2),
                                           p1[ok].reshape(-1, 2))
        if M is None:
            continue
        zoom.append(float(np.sqrt(M[0, 0] ** 2 + M[0, 1] ** 2)))
        pan.append(float(np.hypot(M[0, 2], M[1, 2])) / max(klein[0].shape[1], 1))
    sek = len(frames) / float(fps)
    res = {'schnitte_pro_s': round(len(cuts) / max(sek, 0.1), 3),
           'einstellung_s': round(sek / (len(cuts) + 1), 2)}
    if zoom:
        res['zoom_pro_s'] = round(float(np.median(zoom)) ** fps, 4)
        res['pan_pro_s'] = round(float(np.median(pan)) * fps, 4)
        res['unruhe'] = round(float(np.std(pan)), 4)
        res['kamera'] = ('ruhig' if res['unruhe'] < 0.012
                         and abs(res['zoom_pro_s'] - 1.0) < 0.02
                         else ('bewegt' if res['unruhe'] < 0.030 else 'wild'))
    return res


def _ref_ton(video_path):
    """v144: misst das SOUNDDESIGN. Bis v143 gab es dazu nur einen Prosa-Satz
    ueber 'Schlagdichte und Dynamik'. Gemessen wird jetzt, was man nachbauen
    kann: liegt Musik drunter, sitzen Toene auf den Schnitten, laeuft der Ton
    dem Bild voraus, wie laut ist gemischt."""
    import wave as _wave
    import tempfile as _tf
    wavp = _tf.NamedTemporaryFile(suffix='.wav', delete=False).name
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', video_path,
                        '-ac', '2', '-ar', '44100', wavp], check=True, timeout=90,
                       capture_output=True)
        with _wave.open(wavp, 'rb') as wf:
            sr, n, ch = wf.getframerate(), wf.getnframes(), wf.getnchannels()
            raw = wf.readframes(n)
    except Exception:
        return {}
    finally:
        try: os.remove(wavp)
        except OSError: pass
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch >= 2:
        x = x.reshape(-1, 2)
        M, S = (x[:, 0] + x[:, 1]) / 2.0, (x[:, 0] - x[:, 1]) / 2.0
    else:
        M, S = x, np.zeros_like(x)
    if len(M) < sr:
        return {}
    res = {}
    def db(v):
        return 20.0 * math.log10(float(np.sqrt(np.mean(v ** 2))) + 1e-12)
    res['pegel_db'] = round(db(M), 1)
    res['breite_db'] = round(db(M) - db(S), 1)
    # MUSIK: eine Musikspur haelt Stereo-Energie AUCH in Mitten und Hoehen.
    # Reine Sprache plus Effekte hat Breite fast nur im Tiefton.
    N = 2048
    f = np.fft.rfftfreq(N, 1.0 / sr)
    def spek(v):
        return np.array([np.abs(np.fft.rfft(v[i:i + N] * np.hanning(N)))
                         for i in range(0, len(v) - N, N)])
    sS = spek(S)
    if len(sS):
        tief = (f >= 20) & (f < 250)
        mitt = (f >= 800) & (f < 6000)
        d_tief = 20.0 * math.log10(float(sS[:, tief].mean()) + 1e-12)
        d_mitt = 20.0 * math.log10(float(sS[:, mitt].mean()) + 1e-12)
        res['musik'] = bool(d_mitt > d_tief - 12.0 and d_mitt > -30.0)
    # Stille-Anteil und Dynamik
    hop = int(sr * 0.05)
    rms = np.array([np.sqrt(np.mean(M[i:i + hop] ** 2) + 1e-12)
                    for i in range(0, len(M) - hop, hop)])
    ddb = 20.0 * np.log10(rms + 1e-12)
    res['stille_anteil'] = round(float(np.mean(ddb < -45.0)), 3)
    res['dynamik_db'] = round(float(np.percentile(ddb, 90) - np.percentile(ddb, 10)), 1)
    return res


def _ref_schnitt_ton(video_path, cut_zeiten):
    """v144: sitzt auf den Schnitten wirklich ein Ton, und laeuft er dem Bild
    voraus? Am Referenzvideo gemessen: Hochton steigt 115 ms vor dem Schnitt
    um 28 dB, der Tiefton-Impuls liegt 30 ms davor. Genau das unterscheidet
    gestalteten Schnitt-Ton von einer Tonspur, die einfach mitlaeuft."""
    if not cut_zeiten:
        return {}
    import wave as _wave
    import tempfile as _tf
    wavp = _tf.NamedTemporaryFile(suffix='.wav', delete=False).name
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', video_path,
                        '-ac', '1', '-ar', '44100', wavp], check=True, timeout=90,
                       capture_output=True)
        with _wave.open(wavp, 'rb') as wf:
            sr, n = wf.getframerate(), wf.getnframes()
            raw = wf.readframes(n)
    except Exception:
        return {}
    finally:
        try: os.remove(wavp)
        except OSError: pass
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    N, hop = 1024, 256
    f = np.fft.rfftfreq(N, 1.0 / sr)
    sp = np.array([np.abs(np.fft.rfft(x[i:i + N] * np.hanning(N)))
                   for i in range(0, len(x) - N, hop)])
    if not len(sp):
        return {}
    t = np.arange(len(sp)) * hop / float(sr)
    hoch = sp[:, (f >= 4000) & (f < 14000)].mean(axis=1)
    tief = sp[:, (f >= 20) & (f < 150)].mean(axis=1)
    treffer, vorlauf = 0, []
    for c in cut_zeiten:
        a, b = np.searchsorted(t, c - 0.35), np.searchsorted(t, c + 0.10)
        ruhe = np.searchsorted(t, max(0.0, c - 0.9)), a
        if b - a < 4 or ruhe[1] - ruhe[0] < 4:
            continue
        basis = float(np.median(hoch[ruhe[0]:ruhe[1]]) + 1e-9)
        spitze = float(np.max(hoch[a:b]))
        anstieg = 20.0 * math.log10(spitze / basis) if basis > 0 else 0.0
        b_basis = float(np.median(tief[ruhe[0]:ruhe[1]]) + 1e-9)
        b_spitze = float(np.max(tief[a:b]))
        b_anstieg = 20.0 * math.log10(b_spitze / b_basis) if b_basis > 0 else 0.0
        if anstieg > 9.0 or b_anstieg > 9.0:
            treffer += 1
            reihe = hoch if anstieg >= b_anstieg else tief
            vorlauf.append(float(c - t[a + int(np.argmax(reihe[a:b]))]))
    if not treffer:
        return {'schnitt_ton': False}
    return {'schnitt_ton': True,
            'schnitt_ton_anteil': round(treffer / float(len(cut_zeiten)), 2),
            'ton_vorlauf_ms': round(float(np.median(vorlauf)) * 1000.0, 1)}


def _kern_hoehe(f, x, y, bw, bh):
    """Hoehe des harten Buchstabenkerns in einem Textkasten - ohne Glow.
    Rueckgabe in Pixeln oder None."""
    aus = f[y:y + bh, x:x + bw]
    if aus.size == 0:
        return None
    hsv = cv2.cvtColor(aus, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.int16)
    s = hsv[..., 1].astype(np.int16)
    kern = ((v >= 250) & (s <= 18)) | ((v >= 215) & (s >= 165))
    aktiv = kern.sum(axis=1) > max(1, bw * 0.04)
    if aktiv.sum() < 2:
        return None
    # LAENGSTER ZUSAMMENHAENGENDER Lauf, nicht die Gesamtausdehnung. Die
    # Referenz setzt sehr eng (Zeilenabstand 0.83 em); mit Glow verschmelzen
    # zwei Zeilen zu EINER Komponente, und min-bis-max haette dann beide
    # gemessen - gemessen 0.122 H statt der echten 0.085 H Versalhoehe.
    best, lauf = 0, 0
    for a_ in aktiv:
        if a_:
            lauf += 1
            best = max(best, lauf)
        else:
            lauf = 0
    return int(best) if best >= 2 else None


def _ref_glow(frames, W, H, maske, teile=None):
    """Misst den Aussenschein: mittlere Helligkeitsanhebung in 2-12 px Abstand
    vom Text gegenueber dem Bildhintergrund. Trennt Glow (positiv, richtungslos)
    von Schatten/Kontur (negativ)."""
    werte = []
    for f in frames[::max(1, len(frames) // 12)]:
        m, _ = maske(f)
        if teile is not None:
            ts = teile(m)
            nur = np.zeros_like(m)
            for (x, y, bw, bh, a) in ts:
                nur[y:y + bh, x:x + bw] |= m[y:y + bh, x:x + bw]
            m = nur
        if m.sum() < 150:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        nah = cv2.dilate(m, np.ones((9, 9), np.uint8)) - cv2.dilate(m, np.ones((3, 3), np.uint8))
        fern = cv2.dilate(m, np.ones((41, 41), np.uint8)) - cv2.dilate(m, np.ones((25, 25), np.uint8))
        if nah.sum() < 60 or fern.sum() < 60:
            continue
        werte.append(float(g[nah > 0].mean() - g[fern > 0].mean()))
    if not werte:
        return {}
    d = float(np.median(werte))
    return {'glow_db': round(d, 1),
            'glow': bool(d > 6.0),
            'kontur': bool(d < -6.0)}


def _ref_strichstaerke(frames, maske, H, teile=None):
    """Stammbreite geteilt durch Zeichenhoehe des GROESSTEN Textteils - das ist
    der Wert, an dem sich unsere Schriftwahl orientiert. Gemessen auf 20 % der
    Zeichenhoehe, also oberhalb von Querbalken."""
    q = []
    for f in frames[::max(1, len(frames) // 20)]:
        m, _ = maske(f)
        best = None
        for (x, y, bw, bh, a) in (teile(m) if teile is not None else []):
            if bh < H * 0.02 or a < 120:
                continue
            if best is None or bh > best[3]:
                best = (x, y, bw, bh)
        if best is None:
            continue
        x, y, bw, bh = best
        zeile = m[int(y + bh * 0.20), x:x + bw]
        laeufe, run = [], 0
        for v in zeile:
            if v: run += 1
            elif run: laeufe.append(run); run = 0
        if run: laeufe.append(run)
        if laeufe:
            q.append(float(np.median(laeufe)) / float(bh))
    return round(float(np.median(q)), 3) if len(q) >= 3 else None


# ---------------------------------------------------------- v230c7 SCHRIFTWAHL
# Ismets Frage: "waere es nicht besser, wenn die KI auch die Schriftart
# erkennen wuerde?" Ja. Der Weg dorthin war aber nicht der, den ich zuerst
# gebaut habe, und die Sackgasse gehoert hierhin, damit sie niemand nochmal
# laeuft:
#   Erster Versuch: drei gemessene Kennzahlen (Strichstaerke, Serifen-
#   Kontrast, Breite der Innenraeume) und die aehnlichste Hausschrift dazu.
#   Auf sauber gezeichnetem Text trennt das gut. Durch die ECHTE Messkette
#   (Videobild -> Schwelle v>=244 -> groesster Textteil) ueberlebt davon
#   genau EINE Zahl. Nachgemessen an vier Testvideos: Innenraum bei Anton
#   0.086 sauber gegen 0.006 aus dem Video, und das Wort 'STECKT' hat gar
#   keine geschlossenen Innenraeume - ein Merkmal, das am Wortlaut haengt,
#   ist keins. Der Kontrast schwankte je nach Weichzeichnung zwischen 1.93
#   und 2.82 fuer dieselbe Schrift.
#   Die Strichstaerke dagegen kam sauber durch (Montserrat 0.105 gegen
#   0.105, Playfair 0.039 gegen 0.039).
# Also: die MESSUNG grenzt ein (Gewicht), das BILDMODELL entscheidet die
# Form. Beides einmal beim Lernen, nie beim Rendern - die Ausgabe bleibt
# reproduzierbar. Ohne Schluessel bleibt die Schrift des Looks stehen; eine
# falsch geratene Schrift ist schlimmer als keine.
_FONT_KANDIDATEN = (
    'anton', 'bebas', 'staatliches', 'montserrat_xb', 'poppins_b', 'archivo',
    'inter_black', 'righteous', 'tiktok_bold', 'sans_l', 'serif', 'serif_i',
    'playfair_i', 'abril', 'yeseva', 'alfaslab', 'lobster', 'marker',
    # v230c8: die verstellbaren Schnitte. Sie decken einen ganzen BEREICH ab
    # und sind deshalb der eigentliche Weg zum "Nachstellen".
    'archivo_var', 'inter_var', 'montserrat_var',
)
# Kurzbeschreibung je Hausschrift - nur fuer die Vision-Rueckfrage. Sie muss
# das BILD einer Schrift treffen, nicht ihren Markennamen.
_FONT_BESCHREIBUNG = {
    'anton': 'very condensed heavy poster sans, tall narrow caps',
    'bebas': 'condensed all-caps sans, medium weight, tall and narrow',
    'staatliches': 'condensed display sans, slightly rounded, poster style',
    'montserrat_xb': 'geometric sans, extra bold, wide round shapes',
    'poppins_b': 'geometric sans, bold, perfectly circular O',
    'archivo': 'grotesque sans, bold, slightly squarish, wide',
    'inter_black': 'neutral UI grotesque, very heavy',
    'righteous': 'retro geometric display sans, rounded, slightly quirky',
    'tiktok_bold': 'modern rounded sans, bold, friendly',
    'sans_l': 'light neutral sans, thin even strokes',
    'serif': 'classic book serif, moderate contrast',
    'serif_i': 'classic serif italic',
    'playfair_i': 'high contrast display serif italic, elegant, thin hairlines',
    'abril': 'high contrast display serif, editorial magazine look',
    'yeseva': 'decorative display serif, flared strokes',
    'alfaslab': 'heavy slab serif, thick rectangular serifs',
    'lobster': 'connected script, brush-like, casual',
    'marker': 'handwritten marker pen, uneven strokes',
    'archivo_var': 'grotesque sans, adjustable from thin to black and from '
                   'condensed to wide, slightly squarish',
    'inter_var': 'neutral UI grotesque, adjustable from thin to black',
    'montserrat_var': 'geometric sans with round shapes, adjustable from '
                      'thin to black',
}
# Variable Schnitte: sie decken einen BEREICH ab statt eines Punktes. Damit
# laesst sich eine gemessene Schrift wirklich nachstellen, statt nur die
# aehnlichste aus einer festen Liste zu nehmen (Ismets Frage: "gibt es keine
# Moeglichkeit die Schrift nachzukreieren?"). Exakt nachbauen geht nicht - ein
# Video zeigt rund 20 Buchstaben, ohne Umlaute, Zahlen und Satzzeichen, dazu
# durch Kompression verwaschen; und fremde Schriften sind in Deutschland
# geschuetzt. Was geht: unsere EIGENEN Schriften auf die gemessenen Werte
# stellen.
_FONT_ACHSEN = {
    'archivo_var': {'wght': (100, 900), 'wdth': (62, 125)},
    'inter_var': {'wght': (100, 900)},
    'montserrat_var': {'wght': (100, 900)},
}
_FONT_STECK = {}       # name -> [(strich, breite, achsen|None), ...]


def _font_probe(fontobj):
    """Strichstaerke UND Zeichenbreite einer Schriftinstanz, gemessen mit
    GENAU DEM REZEPT, mit dem das Vorbild gemessen wird."""
    from PIL import Image, ImageDraw
    bild = Image.fromarray(np.full((900, 2600, 3), 40, np.uint8))
    ImageDraw.Draw(bild).text((60, 300), 'HAMBURG', (245, 245, 240), font=fontobj)
    bgr = cv2.GaussianBlur(cv2.cvtColor(np.array(bild), cv2.COLOR_RGB2BGR),
                           (0, 0), 1.0)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] >= 244) & (hsv[..., 1] <= 26)).astype(np.uint8)
    return _font_masse(m)


def _font_masse(m, cap=None):
    """(strich, breite) aus einer Textmaske, beides als Anteil der
    Zeichenhoehe.

    strich  mediane Lauflaenge auf 20 % Hoehe - dasselbe Rezept wie
            `_ref_strichstaerke` seit v144.
    breite  MEDIANE BREITE EINES ZEICHENS, ueber die Zusammenhangs-
            komponenten. Der naheliegende Weg (Teilbreite geteilt durch die
            Zeichenzahl) scheitert daran, dass wir die Zeichenzahl nicht
            kennen und Leerzeichen mitzaehlen wuerden - an vier Testsaetzen
            schwankte er um ueber 30 %, dieser hier bei Anton 0.463 / 0.463 /
            0.463 / 0.463."""
    ys, xs = np.where(m > 0)
    if ys.size < 50:
        return (None, None)
    cap = float(cap or (ys.max() - ys.min() + 1))
    if cap < 8:
        return (None, None)
    zeile = m[ys.min() + int(cap * 0.20), xs.min():xs.max() + 1]
    laeufe, run = [], 0
    for v in zeile:
        if v:
            run += 1
        elif run:
            laeufe.append(run)
            run = 0
    if run:
        laeufe.append(run)
    strich = round(float(np.median(laeufe)) / cap, 4) if laeufe else None
    n, _lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    # Nur Teile, die wie ein einzelnes Zeichen aussehen: fast volle Hoehe und
    # nicht breiter als hoch mal 1.2 (sonst sind zwei Buchstaben verschmolzen).
    br = [st[i, cv2.CC_STAT_WIDTH] / cap for i in range(1, n)
          if st[i, cv2.CC_STAT_HEIGHT] > cap * 0.55
          and st[i, cv2.CC_STAT_WIDTH] < cap * 1.2]
    breite = round(float(np.median(br)), 4) if len(br) >= 3 else None
    return (strich, breite)


def _font_steckbriefe():
    """Kennzahlen unserer Schriften. Statische Schnitte ergeben EINEN Punkt,
    variable ein Raster ueber ihre Achsen - das ist der Vorrat, aus dem
    nachgestellt wird. Einmal je Prozesslauf; haengt nur an den Dateien."""
    if _FONT_STECK:
        return _FONT_STECK
    from PIL import ImageFont
    for name in _FONT_KANDIDATEN:
        pfad = os.path.join(HERE, 'fonts', f'{name}.ttf')
        if not os.path.exists(pfad):
            continue
        try:
            achsen = _FONT_ACHSEN.get(name)
            punkte = []
            if achsen:
                wg = achsen['wght']
                wd = achsen.get('wdth')
                for w in range(int(wg[0]), int(wg[1]) + 1, 100):
                    for d in ([wd[0], (wd[0] + wd[1]) / 2, wd[1],
                               wd[0] + (wd[1] - wd[0]) * 0.25,
                               wd[0] + (wd[1] - wd[0]) * 0.75]
                              if wd else [None]):
                        f = ImageFont.truetype(pfad, 190)
                        f.set_variation_by_axes(
                            [float(w)] + ([float(d)] if d is not None else []))
                        s, b = _font_probe(f)
                        if s and b:
                            ax = {'wght': float(w)}
                            if d is not None:
                                ax['wdth'] = round(float(d), 1)
                            punkte.append((s, b, ax))
            else:
                s, b = _font_probe(ImageFont.truetype(pfad, 190))
                if s and b:
                    punkte.append((s, b, None))
            if punkte:
                _FONT_STECK[name] = punkte
        except Exception:
            continue
    return _FONT_STECK


# Spannen grob nach der Streuung unserer eigenen Schriften; die Breite traegt
# schwerer, weil sie schmal von breit trennt und das im Bild am meisten
# ausmacht.
_FONT_SPANNE = {'strich': 0.10, 'breite': 0.20}
_FONT_GEWICHT = {'strich': 1.0, 'breite': 1.3}


def _font_abstand(mess, punkt):
    return math.sqrt(
        _FONT_GEWICHT['strich'] * ((mess[0] - punkt[0]) / _FONT_SPANNE['strich']) ** 2
        + _FONT_GEWICHT['breite'] * ((mess[1] - punkt[1]) / _FONT_SPANNE['breite']) ** 2)


def _font_shortlist(mess, n=6):
    """v230c7/c8: die plausibelsten Schrift-FAMILIEN zu einer Messung
    (Strichstaerke, Zeichenbreite). Bei variablen Schnitten zaehlt der beste
    Punkt ihres Rasters - sie kommen also fast immer in Frage, und genau das
    ist gewollt: sie lassen sich nachstellen."""
    steck = _font_steckbriefe()
    if not mess or mess[0] is None or mess[1] is None or not steck:
        return []
    rang = sorted((min(_font_abstand(mess, p) for p in punkte), k)
                  for k, punkte in steck.items())
    return [k for _, k in rang[:n]]


def font_nachstellen(name, mess):
    """v230c8: welche Achsen-Einstellung dieser Familie trifft die Messung am
    besten? Rueckgabe (achsen|None, abstand). Bei statischen Schnitten gibt es
    nichts zu stellen - dann ist der Abstand die Wahrheit ueber den Rest."""
    punkte = _font_steckbriefe().get(name) or []
    if not punkte or not mess or mess[0] is None or mess[1] is None:
        return (None, 1e9)
    d, p = min((_font_abstand(mess, p), p) for p in punkte)
    return (p[2], d)


def _font_instanz(name, achsen):
    """v230c8: erzeugt aus einem variablen Schnitt eine feste Schriftdatei mit
    den gewaehlten Achsen und gibt ihren Pfad zurueck.

    Erzeugt wird beim RENDERN, nicht beim Lernen: so haengt nichts an einer
    Datei, die spaeter fehlen koennte, und die Referenz speichert nur Name und
    Achsen. Das Ergebnis wird ueber den Dateinamen gecacht, ein zweiter Render
    kostet nichts."""
    if not achsen:
        return None
    quelle = os.path.join(HERE, 'fonts', f'{name}.ttf')
    if not os.path.exists(quelle):
        return None
    kurz = '_'.join(f'{k}{int(round(v))}' for k, v in sorted(achsen.items()))
    import tempfile as _tf
    ziel_dir = os.environ.get('DVE_FONT_CACHE') or os.path.join(
        os.environ.get('DVE_DATA') or _tf.gettempdir(), 'dve_fonts')
    ziel = os.path.join(ziel_dir, f'{name}_{kurz}.ttf')
    if os.path.exists(ziel):
        return ziel
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        os.makedirs(ziel_dir, exist_ok=True)
        f = TTFont(quelle)
        instancer.instantiateVariableFont(f, dict(achsen), inplace=True)
        tmp = f'{ziel}.{os.getpid()}.tmp'     # v230w: kein gemeinsamer .tmp
        f.save(tmp)
        os.replace(tmp, ziel)
        return ziel
    except Exception as e:
        print(f"Font instance skipped ({type(e).__name__}: {e})")
        return None


def _ref_font_klassen(frames, maske, H, teile=None, grenze=None):
    """v230c8: Strichstaerke und Zeichenbreite GETRENNT fuer grossen und
    kleinen Text. Ein Caption-Video hat fast immer zwei Schnitte - das
    Schluesselwort und den Fliesstext daneben.

    `grenze` ist die gemessene Fliesstext-Hoehe; alles ab dem 1.8-fachen gilt
    als gross (dieselbe Trennung wie bei den Groessen, v230c5)."""
    aus = {'gross': [], 'klein': []}
    if teile is None:
        return {}
    schwelle = float(grenze) * 1.8 * H if grenze else None
    for f in frames[::max(1, len(frames) // 24)]:
        m, _ = maske(f)
        parts = [p for p in teile(m) if p[3] >= H * 0.012 and p[4] >= 120]
        if not parts:
            continue
        if schwelle is None:
            # Ohne Referenzhoehe: der groesste Teil ist 'gross', der Rest klein.
            hh = max(p[3] for p in parts)
            schwelle_f = hh * 0.55
        else:
            schwelle_f = schwelle
        for (x, y, bw, bh, _a) in parts:
            s, b = _font_masse(m[y:y + bh, x:x + bw], bh)
            if s is None or b is None:
                continue
            aus['gross' if bh >= schwelle_f else 'klein'].append((s, b))
    erg = {}
    for k, v in aus.items():
        if len(v) >= 3:
            a = np.array(v, dtype=np.float64)
            erg[k] = (round(float(np.median(a[:, 0])), 4),
                      round(float(np.median(a[:, 1])), 4))
    return erg


def _ai_font_pick(key, model, frames, kandidaten, rolle='gross'):
    """v230c7: Vision waehlt AUS DER SHORTLIST die passendste Schrift.

    Warum ueberhaupt Vision: aus dem Videobild ueberlebt zuverlaessig nur die
    Strichstaerke, und die trennt Gewicht, nicht Form. Ob eine fette Grotesk
    rund (Poppins), eckig (Archivo) oder schmal (Anton) ist, sieht ein
    Bildmodell besser als eine Zahl.
    Warum trotzdem die Messung davor: sie haelt die Auswahl im richtigen
    Gewicht. Und der Aufruf passiert EINMAL beim Lernen, nie beim Rendern."""
    if not key or not frames or not kandidaten:
        return None
    import requests            # v210: in dieser Datei lokal, sonst NameError
    liste = '\n'.join(f'- {k}: {_FONT_BESCHREIBUNG.get(k, k)}' for k in kandidaten)
    was = ('the BIG highlighted words' if rolle == 'gross'
           else 'the SMALLER running text')
    prompt = ('You see frames from a video with burned-in captions. Look ONLY '
              f'at the SHAPE of the lettering used for {was} (weight, width, '
              'serifs, roundness) - ignore colour, size and the words. Which '
              'of these typefaces is the closest match?\n' + liste +
              '\nIf none is close, answer null. Answer only with JSON: '
              '{"font": "<name from the list>"|null}')
    content = [{'type': 'text', 'text': prompt}]
    for b in frames[:4]:
        content.append({'type': 'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b}',
                                      'detail': 'high'}})
    try:
        txt = _oai_text(key, _oai_json(
            model, [{'role': 'user', 'content': content}],
            max_toks=300, temperature=0.0, frage='schrift'), timeout=120)
        wahl = str((json.loads(txt) or {}).get('font') or '').strip().lower()
        return wahl if wahl in kandidaten else None
    except Exception as e:
        print(f"Font match: vision skipped ({type(e).__name__})")
        return None


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


def analyze_reference_video(video_path, name=None, model='gpt-5',
                            n_frames=6, save=True, store_path=None):
    """v96n: Lernt aus einem REFERENZ-Video mit High-End-Captions. Sampelt ein
    paar Frames, laesst GPT-5 (Vision) den STIL beschreiben (Pacing, Dichte,
    betonte Woerter, Effekt-Wucht, Hook) und legt das als Stil-Referenz in
    regie_reference.json ab. WICHTIG/EHRLICH: die Regie-KI uebernimmt daraus
    EDITORIALE Entscheidungen (wo + wie stark), NICHT den exakten Look - Fonts,
    Animationen und Kamera kommen aus unserer Engine, nicht aus dem Referenz-
    video. Gibt den Eintrag zurueck oder None.
    v126: store_path speichert in eine EXPLIZITE Datei (persoenliche Kunden-
    Referenzen) statt in den globalen Store - der Server ruft das in-process
    auf, ein Env-Override waere dort nicht threadsicher."""
    key = os.environ.get('OPENAI_API_KEY')
    if not os.path.exists(video_path):
        return None
    # v144: die MESSUNG zuerst, und zwar unabhaengig von OpenAI. Sie ist
    # inzwischen die Substanz dieser Funktion - Groesse, Hierarchie, Zone,
    # Satz, Farbe, Kamera, Schnitt und Sounddesign kommen aus den Pixeln und
    # der Tonspur. Bis v143 stand ganz oben ein 'kein Key -> None': ein
    # API-Ausfall liess damit das ganze Stil-Lernen ausfallen, obwohl kein
    # einziger Messwert davon abhaengt.
    try:
        mess = measure_reference_video(video_path)
    except Exception as e:
        print(f"Style measurement skipped ({type(e).__name__})")
        mess = {}
    if not key:
        if not mess:
            return None
        return _reference_entry(video_path, name, '', None, mess, save,
                                store_path)
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
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'user', 'content': content}],
            max_toks=400, temperature=0.3, json_mode=False), timeout=120)
        desc = _txt
    except Exception as e:
        print(f"Style learning unavailable ({type(e).__name__})")
        desc = ''
    if not desc:
        # Prosa fehlt (Ausfall, Rate-Limit, leere Antwort). Die Messung
        # traegt den Eintrag trotzdem - sie ist der Teil, der wirkt.
        if not mess:
            return None
        return _reference_entry(video_path, name, '', None, mess, save,
                                store_path)
    # v230c7: die Schrift. Die Messung hat oben schon eine Shortlist erzeugt
    # und - nur bei klarem Abstand - selbst entschieden. Mit Schluessel darf
    # Vision INNERHALB dieser Shortlist genauer hinsehen; ohne Schluessel
    # bleibt es bei der Messung. Ein Aufruf beim LERNEN, nie beim Rendern.
    # v230c8: fuer BEIDE Rollen eine Schrift - grosses Wort und Fliesstext
    # sind in einem Caption-Video fast nie derselbe Schnitt.
    for _rolle, _ziel in (('gross', 'font'), ('klein', 'font_klein')):
        _mass = mess.get(f'font_mass_{_rolle}')
        if not _mass:
            continue
        _mass = tuple(_mass)
        _kand = _font_shortlist(_mass)
        _pick = _ai_font_pick(key, model, frames, _kand, rolle=_rolle)
        if not _pick and _kand:
            # Ohne Schluessel oder ohne Antwort: die Messung entscheidet, aber
            # nur bei klarem Abstand zum zweiten Platz. Falsch raten ist
            # schlimmer als beim Look zu bleiben.
            _r = sorted((font_nachstellen(k, _mass)[1], k) for k in _kand)
            if len(_r) > 1 and (_r[1][0] - _r[0][0]) >= 0.25:
                _pick = _r[0][1]
        if _pick:
            _ach, _d = font_nachstellen(_pick, _mass)
            mess[_ziel] = _pick
            if _ach:
                mess[f'{_ziel}_achsen'] = _ach
            print(f"Style reference: {_rolle} text -> {_pick}"
                  + (f" ({', '.join(f'{k} {v:.0f}' for k, v in _ach.items())})"
                     if _ach else ''))
    # v96v: Audio/SFX separat aus der Tonspur analysieren (Vision hoert nichts)
    aud = _ref_audio_summary(video_path)
    if aud:
        desc = desc + "\n" + aud
    # v96y/z: MESSBARE Parameter aus Beschreibung + FRAMES ziehen (Farbe/Dichte
    # praezise) - die wirken deterministisch auf die Render-Config (sichtbar).
    params = _style_params_from_desc(desc, model, key, frames=frames)
    # v144: GEMESSENE Werte schlagen geschaetzte. Bis v143 kamen alle
    # Parameter aus einer zweiten GPT-Anfrage auf eine Prosa-Beschreibung -
    # Kamera, Schnitt, Sounddesign und Caption-Geometrie kamen darin gar nicht
    # vor. measure_reference_video() rechnet sie direkt aus Bild und Ton.
    return _reference_entry(video_path, name, desc, params, mess, save,
                            store_path)


def _messung_klartext(mess):
    """v144: die Messwerte als lesbare Zeile. Der Kunde soll SEHEN, was von
    seinem Vorbild uebernommen wurde - sonst bleibt 'Stil gelernt' eine
    Behauptung. Bewusst nur gemessene Groessen, keine Werbeworte."""
    if not mess:
        return ''
    # ENGLISCH, weil dieser Text im Web-Produkt direkt beim Kunden landet.
    t = []
    if mess.get('key_hoehe'):
        t.append(f"key word {mess['key_hoehe'] * 100:.1f}% of frame height")
    if mess.get('verhaeltnis'):
        t.append(f"size contrast {mess['verhaeltnis']:.1f}x")
    z = mess.get('zone_y')
    if isinstance(z, (list, tuple)) and len(z) == 2:
        t.append(f"text zone {z[0] * 100:.0f}-{z[1] * 100:.0f}% height")
    if mess.get('ausrichtung') in ('links', 'mitte'):
        t.append('left aligned' if mess['ausrichtung'] == 'links' else 'centred')
    if mess.get('akzent_hex'):
        t.append(f"accent {mess['akzent_hex']}")
    # v230c7: die Schrift gehoert in diese Zeile - sie ist das Erste, was ein
    # Kunde an einem Vorbild sieht. Ehrlich formuliert: es ist die AEHNLICHSTE
    # aus unserem Haus, nicht dieselbe.
    if mess.get('font'):
        _ax = mess.get('font_achsen') or {}
        t.append('typeface matched to ' + str(mess['font']).replace('_var', '')
                 + (' (' + ', '.join(f'{k} {v:.0f}' for k, v in sorted(_ax.items()))
                    + ')' if _ax else ''))
    if mess.get('font_klein') and mess.get('font_klein') != mess.get('font'):
        t.append('body text ' + str(mess['font_klein']).replace('_var', ''))
    if mess.get('kamera'):
        t.append({'ruhig': 'calm camera', 'bewegt': 'moving camera',
                  'wild': 'restless camera'}.get(mess['kamera'], 'camera'))
    if mess.get('einstellung_s'):
        t.append(f"{mess['einstellung_s']:.2f}s average shot")
    if 'musik' in mess:
        t.append('music bed' if mess['musik'] else 'no music bed')
    if mess.get('schnitt_ton'):
        v = mess.get('ton_vorlauf_ms')
        t.append('sound on the cut'
                 + (f" ({v:.0f} ms early)" if isinstance(v, (int, float)) else ''))
    return 'Measured: ' + ', '.join(t) if t else ''


def _reference_entry(video_path, name, desc, params, mess, save, store_path):
    """v144: baut den Referenz-Eintrag und legt ihn ab. Ausgelagert, weil er
    jetzt aus DREI Wegen erreichbar ist: mit Prosa + Messung, ohne Key nur
    Messung, und bei API-Ausfall ebenfalls nur Messung."""
    entry = {'name': (name or os.path.splitext(os.path.basename(video_path))[0])[:60],
             'beispiel': desc or ''}
    if mess:
        params = dict(params or {})
        params.update({k: v for k, v in mess.items() if v is not None})
        entry['messung'] = mess
        klar = _messung_klartext(mess)
        entry['gemessen'] = klar
        if not entry['beispiel']:
            entry['beispiel'] = klar
        print(f"Style measured: shot {mess.get('einstellung_s', '?')}s, "
              f"camera {mess.get('kamera', '?')}, "
              f"music {'yes' if mess.get('musik') else 'no'}, "
              f"zone {mess.get('zone_y', '?')}")
    if params:
        entry['params'] = params
    if save:
        path = store_path or _reference_store_path()
        try:
            refs = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
            if not isinstance(refs, list):
                refs = []
        except Exception:
            refs = []
        refs.append(entry)
        try:
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            json.dump(refs[-12:], open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)   # max 12 Referenzen halten
        except Exception as e:
            print(f"Reference not saved ({type(e).__name__})")
    print(f"Style reference learned: {entry['name']}")
    return entry


def _reference_store_path():
    """v96w: gelernte Stil-Referenzen liegen im PERSISTENTEN DATA-Ordner
    (DVE_DATA), NICHT im Git-Repo - sonst wuerde jeder Deploy (Docker-Rebuild)
    die Datei mit der Repo-Version ueberschreiben und das Gelernte waere weg.
    Genau das war der Grund, warum die KI das Gelernte nicht anwandte.
    v126: DVE_REFS_FILE uebersteuert den Pfad. Der Server setzt die Variable
    pro Render-Subprozess auf die PERSOENLICHE Referenz-Datei des Kunden -
    damit werden Prompt-Block UND Mess-Parameter pro Konto, ohne dass die
    Regie selbst etwas davon wissen muss. Ohne eigene Referenzen bleibt der
    globale Haus-Stil aktiv."""
    override = os.environ.get('DVE_REFS_FILE')
    if override:
        return override
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


def _style_params_from_desc(desc, model='gpt-5', key=None, frames=None):
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
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'user', 'content': content}],
            max_toks=200, temperature=0.0), timeout=90)
        data = json.loads(_txt)
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
        print(f"  Style parameters skipped ({type(e).__name__})")
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
    # v144: die GEMESSENEN Merkmale durchreichen. Die Liste oben war eine
    # feste Auswahl aus v96 - Kamera, Schnitt, Ton und Caption-Geometrie
    # waeren sonst gemessen worden und dann im Filter haengengeblieben.
    for k in ('schnitte_pro_s', 'einstellung_s', 'zoom_pro_s', 'unruhe',
              'wort_takt', 'buchstaben_takt', 'key_hoehe', 'klein_hoehe',
              'verhaeltnis', 'stamm_versal', 'ton_vorlauf_ms'):
        vals = [p[k] for p in ps if isinstance(p.get(k), (int, float))]
        if vals:
            out[k] = sum(vals) / len(vals)
    for k in ('kamera', 'ausrichtung', 'font', 'font_klein'):
        vs = [p.get(k) for p in ps if p.get(k)]
        if vs:
            out[k] = max(set(vs), key=vs.count)
    # v230c8: die Achsen-Einstellungen sind dicts - sie gehoeren zur zuletzt
    # gewaehlten Schrift und werden nicht gemittelt.
    for k in ('font_achsen', 'font_klein_achsen'):
        vs = [p.get(k) for p in ps if isinstance(p.get(k), dict)]
        if vs:
            out[k] = vs[-1]
    for k in ('musik', 'schnitt_ton', 'glow', 'kontur'):
        vs = [p[k] for p in ps if isinstance(p.get(k), bool)]
        if vs:
            out[k] = sum(vs) > len(vs) / 2.0
    zs = [p['zone_y'] for p in ps
          if isinstance(p.get('zone_y'), (list, tuple)) and len(p['zone_y']) == 2]
    if zs:
        out['zone_y'] = [sum(z[0] for z in zs) / len(zs),
                         sum(z[1] for z in zs) / len(zs)]
    # v144: gemessene Akzentfarbe schlaegt die geschaetzte
    hx = [str(p.get('akzent_hex') or '').lstrip('#') for p in ps]
    hx = [h for h in hx if re.fullmatch(r'[0-9a-fA-F]{6}', h)]
    if hx:
        cs = [tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)) for h in hx]
        out['accent'] = [int(sum(c[k] for c in cs) / len(cs)) for k in range(3)]
    return out


# v230ay: Anzeigenamen fuer die Stil-Anker-Zeile. Die Werte links sind
# Config-Schluessel und bleiben deutsch (sie stehen in config.yaml und in den
# gespeicherten Setups); der Job-Log geht an den Kunden und ist englisch
# (v148). Unbekanntes wird durchgereicht statt verschluckt.
_REF_EN = {'wuchtig': 'strong', 'ruhig': 'calm', 'bewegt': 'moving',
           'wild': 'wild', 'sparsam': 'sparse', 'akzente': 'accents',
           'durchgehend': 'continuous', 'links': 'left', 'mitte': 'centre'}


_REF_FEHLT = object()


def _ref_pfad(cfg, pfad, default=None):
    cur = cfg
    for teil in str(pfad).split('.'):
        if not isinstance(cur, dict) or teil not in cur:
            return default
        cur = cur[teil]
    return cur


def _ref_setzen(cfg, pfad, wert):
    teile = str(pfad).split('.')
    cur = cfg
    for teil in teile[:-1]:
        if not isinstance(cur.get(teil), dict):
            cur[teil] = {}
        cur = cur[teil]
    if wert is _REF_FEHLT:
        cur.pop(teile[-1], None)
    else:
        cur[teile[-1]] = wert


def _apply_reference_params(cfg):
    """v230c6: eine gelernte Referenz ist KEIN Preset.

    Sie setzt 21 Werte quer durch Typografie, Dichte, Kamera und Ton - und lief
    bis v230c5 NACH der ganzen Config-Kaskade. Damit hat sie die Regler des
    Kunden ueberstimmt, ohne ein Wort zu sagen (Ismet: "wofuer habe ich denn
    die ganzen Einstellungen, wenn die nicht wirklich greifen?").

    Reihenfolge jetzt: config.yaml -> Look-Preset -> REFERENZ -> eigene
    Einstellung. Umgesetzt, indem die Referenz wie bisher alles setzen darf und
    die ausdruecklich gewaehlten Werte danach zurueckgeschrieben werden. Das ist
    bewusst so herum: ein Riegel an 21 einzelnen Zuweisungen wuerde beim naechsten
    neuen Messwert vergessen (v159/v230f), das Zurueckschreiben kann nichts
    uebersehen.

    `cfg['ref_schutz']` ist die Liste der eigenen Pfade; sie kommt vom Server
    (build_config). Fehlt sie - Desktop-App, Handbetrieb -, aendert sich nichts
    gegenueber vorher."""
    schutz = [str(k) for k in (cfg.get('ref_schutz') or [])
              if isinstance(k, str) or isinstance(k, (int, float))]
    vorher = {k: _ref_pfad(cfg, k, _REF_FEHLT) for k in schutz}
    zeile = _apply_reference_params_roh(cfg)
    behalten = []
    for k, v in vorher.items():
        if _ref_pfad(cfg, k, _REF_FEHLT) is not v and _ref_pfad(cfg, k, _REF_FEHLT) != v:
            behalten.append(k.split('.')[-1])
        _ref_setzen(cfg, k, v)
    if zeile and behalten:
        # Sichtbar machen, WAS die Referenz nicht durfte - sonst sucht beim
        # naechsten Befund wieder jemand im Code statt im Log.
        zeile += (' | your own settings kept: '
                  + ', '.join(sorted(set(behalten))[:8])
                  + (' ...' if len(set(behalten)) > 8 else ''))
    return zeile


def _apply_reference_params_roh(cfg):
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
        parts.append(f"punch={_REF_EN.get(w, w)}")
    # v96z: LOOK kopieren - Akzentfarbe der Referenz wird zur Caption-
    # Akzentfarbe (feste Farbe schlaegt adaptive Szenen-Toene), Dichte
    # (akzente vs durchgehend) wird uebernommen.
    if p.get('accent'):
        cfg.setdefault('colors', {})['accent'] = list(p['accent'])
        cfg['colors']['adaptive'] = False
        parts.append('colour=#%02x%02x%02x' % tuple(p['accent']))
    if p.get('density'):
        cfg['effects']['density'] = p['density']
        parts.append(f"density={_REF_EN.get(p['density'], p['density'])}")

    # ---------------- v144: GEMESSENE Merkmale anwenden ----------------
    # KAMERA. Vorher wurde die Kamerastaerke aus dem Prosa-Wort 'wucht'
    # abgeleitet. Am Referenzvideo waere das falsch herum gewesen: dort ist
    # die Kamera RUHIG (Zoom 0.994/s, Pan-Streuung 0.83 %), die Energie kommt
    # aus dem Schnitt. Jetzt entscheidet die Messung.
    if p.get('kamera'):
        _k = str(p['kamera'])
        if _k == 'ruhig':
            cfg['camera']['strength'] = min(float(cfg['camera'].get('strength', 0.7)), 0.35)
            cfg['camera']['whip'] = False
            cfg['camera']['crash'] = min(float(cfg['camera'].get('crash', 0.0)), 0.20)
        elif _k == 'bewegt':
            # v151: 'bewegt' war ein LEERLAUF - nur 'ruhig' und 'wild' taten
            # etwas. Ein Vorbild mit bewegter Kamera aenderte an unserer
            # Kamera damit nichts, obwohl genau das gemessen wurde.
            cfg['camera']['strength'] = max(
                0.60, min(0.80, float(cfg['camera'].get('strength', 0.7))))
            cfg['camera']['whip'] = True
        elif _k == 'wild':
            cfg['camera']['strength'] = max(float(cfg['camera'].get('strength', 0.7)), 0.85)
            cfg['camera']['whip'] = True
        parts.append(f"camera={_REF_EN.get(_k, _k)}")
    # SCHNITT-TEMPO steuert, wie lange ein Chunk stehen bleibt. Schnelle
    # Einstellungen vertragen keine langen Standzeiten.
    if p.get('einstellung_s'):
        _e = float(p['einstellung_s'])
        cfg['effects']['chunk_hold_min'] = round(max(0.55, min(1.30, _e * 0.55)), 2)
        parts.append(f"cut={_e}s")
    # SOUND. Kein Musikbett + Toene auf den Schnitten = Sounddesign traegt das
    # Video. Dann darf unser SFX-Pegel hoch, sonst bleibt er zurueckhaltend.
    if 'musik' in p:
        if p.get('musik'):
            cfg['effects']['sfx_volume'] = min(float(cfg['effects'].get('sfx_volume', 0.6)), 0.45)
            parts.append('music bed')
        elif p.get('schnitt_ton'):
            cfg['effects']['sfx_volume'] = max(float(cfg['effects'].get('sfx_volume', 0.6)), 0.75)
            cfg['effects']['sfx'] = True
            parts.append('cut sound')
    # TYPO-ZONE: oben, mittig oder unten - als Wunschzone der Platzierungsregie.
    _z = p.get('zone_y')
    if isinstance(_z, (list, tuple)) and len(_z) == 2:
        _mitte = (float(_z[0]) + float(_z[1])) / 2.0
        cfg['effects']['caption_zone'] = round(_mitte, 3)
        parts.append(f"zone={_mitte:.2f}H")
    # SCHRIFTGROESSE + HIERARCHIE. Das ist der Punkt, an dem man die
    # Aehnlichkeit zuerst sieht: wie gross das Schluesselwort steht und wie
    # weit es sich vom Fliesstext abhebt. Uebertragen wird der Anteil der
    # BILDHOEHE, damit es zwischen 9:16 und 16:9 uebertragbar bleibt.
    # Bezugsgroesse ist unsere eigene Hausgroesse: Schriftgrad 0.098 H mal
    # cap/em 0.70 = 0.0686 H Versalhoehe.
    # v151: GRENZEN KLEMMEN, NICHT VERWERFEN. Bis v150 fiel ein Messwert
    # ausserhalb des Fensters einfach durch - und damit passierte GAR NICHTS.
    # Genau das traf die auffaelligsten Vorbilder: das zweite Referenzvideo
    # misst Versalhoehe 0.1836 H und Verhaeltnis 4.59, beides oberhalb der an
    # v144 geeichten Fenster (0.140 / 4.0). Der Kunde lud eine Referenz hoch
    # und sah nichts - obwohl die Messung stimmte. Das Fenster prueft jetzt
    # nur noch auf groben Unsinn, der Rest wird an den Rand geklemmt.
    if p.get('key_hoehe'):
        _kh = float(p['key_hoehe'])
        if 0.015 <= _kh <= 0.40:
            # Deckel bis 2.6: das Vorbild ist 2.68x groesser als unser
            # Hausmass. Mit dem alten Deckel 1.35 kam nicht einmal die
            # Haelfte des Unterschieds an. S.fit deckelt weiterhin auf die
            # Spaltenbreite, ein langes Wort schrumpft also von selbst.
            _sk = round(max(0.70, min(2.60, _kh / 0.0686)), 3)
            cfg['effects']['caption_scale'] = _sk
            parts.append(f"size={_kh:.3f}H")
    # v154: der KLEINTEXT bekommt seinen eigenen gemessenen Wert. Vorher lief
    # er ueber key_hoehe mal Hierarchie mit - eine Referenz mit grosser
    # Punchline blies damit den ganzen Satz auf.
    if p.get('klein_hoehe'):
        _kl = float(p['klein_hoehe'])
        if 0.008 <= _kl <= 0.20:
            # x-Hoehe/em 0.52, Hausmass 0.034 em -> 0.0177 H
            cfg['effects']['caption_scale_klein'] = round(
                max(0.70, min(1.30, _kl / 0.0177)), 3)
    if p.get('verhaeltnis'):
        _vh = float(p['verhaeltnis'])
        if 1.1 <= _vh <= 8.0:
            cfg['effects']['caption_hierarchie'] = round(max(1.5, min(4.6, _vh)), 2)
            parts.append(f"hierarchy={_vh:.1f}")
    # v151: REVEAL-TEMPO aus dem Vorbild. Gemessen wird, in welchem Abstand
    # neue Textflaeche dazukommt: der Buchstaben-Takt ist die Zeit je
    # aufgedecktem Zeichen (Vorbild 0.087 s), der Wort-Takt der Abstand
    # zwischen zwei Woertern. Bis v150 wurde beides gemessen und dann
    # weggeworfen - dabei ist das Aufdeck-Tempo eines der ersten Dinge, die
    # man beim Vergleich mit einem Vorbild sieht.
    if p.get('buchstaben_takt'):
        _bt = float(p['buchstaben_takt'])
        if 0.02 <= _bt <= 0.30:
            cfg['effects']['reveal_letter_s'] = round(_bt, 3)
            parts.append(f"reveal={_bt:.3f}s")
    # STRICHSTAERKE: wie fett die Referenz-Schrift steht (Stammbreite je
    # Versalhoehe). Sie waehlt das Gewicht der Stuetzschrift.
    if p.get('stamm_versal'):
        _sv = float(p['stamm_versal'])
        if 0.05 <= _sv <= 0.60:
            cfg['effects']['caption_weight'] = int(
                max(300, min(900, round(300 + (_sv - 0.10) * 2000, -1))))
            parts.append(f"stroke={_sv:.2f}")
    # GLOW / KONTUR direkt aus dem Vorbild
    if 'glow' in p:
        cfg['effects']['caption_glow'] = bool(p['glow'])
    if p.get('kontur'):
        cfg['effects']['caption_outline'] = True
    # AUSRICHTUNG
    if p.get('ausrichtung') in ('links', 'mitte'):
        cfg['effects']['caption_align'] = p['ausrichtung']
        parts.append(f"align={_REF_EN.get(p['ausrichtung'], p['ausrichtung'])}")
    # v230c7 SCHRIFT. Bis hierher konnte eine Referenz alles ausser dem
    # Auffaelligsten uebertragen: die Schrift kam weiter vom Look. Jetzt
    # bringt sie die aehnlichste Hausschrift mit.
    # Gesetzt werden display/strong/italic, also die GROSSEN Woerter - dort
    # wurde gemessen (groesster Textteil je Frame). Die Stuetzschrift
    # (support) und die Schreibschrift bleiben beim Look: was der Fliesstext
    # im Vorbild fuer eine Schrift hat, wissen wir nicht, und zwei Familien
    # in einem Block sind der Normalfall (jedes Preset macht das so).
    # v189 gilt hier NICHT: dort ging es um die ausdrueckliche Wahl des
    # Kunden, die den ganzen Satz meint - eine Referenz ist ein Vorbild,
    # kein Befehl, und sie verliert seit v230c6 ohnehin gegen eine eigene
    # Wahl.
    # v230c8: zwei Rollen. Das grosse Wort und der Fliesstext sind in einem
    # Caption-Video fast nie derselbe Schnitt - beide werden nachgestellt.
    # Ist die gewaehlte Familie ein VERSTELLBARER Schnitt, wird daraus eine
    # feste Schriftdatei mit den gemessenen Achsen erzeugt: das ist so nah am
    # "Nachbauen", wie es sauber geht.
    def _schrift(feld):
        _n = str(p.get(feld) or '').strip()
        if not _n or not re.fullmatch(r'[a-z0-9_]{2,32}', _n):
            return None
        if not os.path.exists(os.path.join(HERE, 'fonts', f'{_n}.ttf')):
            return None
        _ax = p.get(f'{feld}_achsen')
        if isinstance(_ax, dict) and _ax:
            _ax = {str(k)[:4]: float(v) for k, v in _ax.items()
                   if str(k)[:4] in ('wght', 'wdth', 'opsz', 'slnt')
                   and isinstance(v, (int, float))}
            _inst = _font_instanz(_n, _ax) if _ax else None
            if _inst:
                return (_inst, _n + '/' + ','.join(
                    f'{k}{v:.0f}' for k, v in sorted(_ax.items())))
        return (f'fonts/{_n}.ttf', _n)
    cfg.setdefault('fonts', {})
    _gr = _schrift('font')
    if _gr:
        cfg['fonts']['display'] = _gr[0]
        cfg['fonts']['strong'] = _gr[0]
        cfg['fonts']['italic'] = _gr[0]
        parts.append(f"font={_gr[1]}")
    _kl = _schrift('font_klein')
    if _kl:
        cfg['fonts']['support'] = _kl[0]
        parts.append(f"body font={_kl[1]}")
    return 'Style anchor: ' + ', '.join(parts) if parts else ''


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
                        if anim in _VISIBLE_ANIM and entry['fx'] in (
                                'behind', 'blurin'):
                            entry['fx'] = 'outline'
                    emo = str(item.get('emoji', '')).strip()
                    # nur echte Emoji-Bereiche zulassen, kein Text/HTML
                    if emo and 1 <= len(emo) <= 4 and any(
                            0x1F000 <= ord(c) <= 0x1FFFF or 0x2600 <= ord(c) <= 0x27BF
                            for c in emo):
                        entry['emoji'] = emo
                    if item.get('intent'):
                        entry['intent'] = True   # v99a: Ansage ueberlebt den Cache
                    # v161: der Objekt-Anker ueberlebt den Cache genauso. Ohne
                    # das waere er beim ZWEITEN Render desselben Videos weg -
                    # und der Cache ist dort der Normalfall (siehe v159).
                    _ak = item.get('anker')
                    if isinstance(_ak, dict):
                        try:
                            _acx, _acy = float(_ak['cx']), float(_ak['cy'])
                            _agr = float(_ak.get('groesse', 0.15))
                        except (KeyError, TypeError, ValueError):
                            _acx = None
                        if _acx is not None and 0.02 <= _acx <= 0.98 \
                                and 0.02 <= _acy <= 0.98 and 0.02 <= _agr <= 0.60:
                            entry['anker'] = {'objekt': str(_ak.get('objekt', ''))[:24],
                                              'cx': _acx, 'cy': _acy, 'groesse': _agr}
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
    """Zwei-Pass-Validator: die Regie-KI kriegt ihre eigenen Vorschlaege zurueck und
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
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': json.dumps(
                        entries, ensure_ascii=False)}],
            max_toks=800, temperature=0.0, frage='pruefer'), timeout=90)
        data = json.loads(_txt)
        drop = {int(i) for i in data.get('entfernen', []) if i in fx_map}
        if drop:
            for i in drop:
                fx_map.pop(i, None)
            print(f"  Validator: {len(drop)} wrong highlights dropped")
        else:
            print(f"  Validator: all {len(entries)} highlights confirmed")
    except Exception as e:
        print(f"  Validator skipped ({type(e).__name__})")
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
        print(f"  Word loudness skipped ({type(e).__name__})")
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
            print(f"  Audio emotion: {bumped} moments louder -> power up")
    except Exception as e:
        print(f"  Audio emotion skipped ({type(e).__name__})")
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
        print(f"  Direction check: {dropped} mismatched sound animation(s) removed")
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
        # v159: schon gesetzte Ansagen bleiben, wie sie sind. Die Funktion
        # laeuft jetzt in ALLEN Pfaden und damit im KI-Pfad zweimal - ohne
        # diesen Riegel meldete das Log denselben Treffer doppelt.
        if fx_map[i].get('intent'):
            continue
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
        fx_map[i]['intent'] = True   # v99a: Ansage ist Gesetz (Vision/Backstop tabu)
        hits += 1
    if hits:
        print(f"  Spoken intent: {hits} caption(s) follow what was said "
              f"(hinter/Boden/Himmel/Wasser/Wand)")
    return fx_map


# v99 Selbstbezug: Woran wir erkennen, dass ueber die CAPTIONS SELBST
# gesprochen wird. Eindeutige Woerter zaehlen immer; mehrdeutige (Wort/Text)
# nur mit Artikel davor ('this word', 'der Text') - 'ich gebe dir mein Wort'
# ist ein Versprechen, kein Selbstbezug.
_SELF_NOUN_ONE = {'caption', 'captions', 'untertitel', 'subtitle', 'subtitles'}
# v209: 'line' und 'one' fehlten - und genau so redet ein Mensch ueber seine
# Captions ("this next LINE goes behind me", "this ONE sticks on the wall").
# In Ismets Werbe-Video wurde deshalb KEINE der drei Ansagen erkannt: der
# Text stand vor der Person, nicht hinter ihr, nicht an der Wand, nicht ueber
# ihm. Ein Wortschatz, der die haeufigste Formulierung nicht kennt, ist der
# gleiche Fehler wie ein Riegel am falschen Gate.
_SELF_NOUN_PAIR = {'wort', 'worte', 'woerter', 'wörter', 'word', 'words',
                   'text', 'texte', 'line', 'lines', 'zeile', 'zeilen',
                   'satz', 'saetze', 'sätze', 'one', 'ones'}
_SELF_DET = {'the', 'this', 'these', 'that', 'those', 'my', 'der', 'die',
             'das', 'den', 'dieses', 'diese', 'dieser', 'jene', 'jener',
             'mein', 'meine', 'meinen'}
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
            # v209: Das Bestimmungswort steht nicht immer direkt davor -
            # "this NEXT line" hat ein Adjektiv dazwischen, und genau diese
            # Formulierung stand in Ismets Werbe-Video. Zwei Woerter
            # zurueckschauen; mehr waere geraten.
            _det = any(toks[k - d] in _SELF_DET for d in (1, 2) if k - d >= 0)
            if t in _SELF_NOUN_ONE or (t in _SELF_NOUN_PAIR and _det):
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
                   'power': 2, 'n': max(1, min(L, 4)), 'intent': True}
            if szene:
                ent['szene'] = szene
            if lage:
                ent['lage'] = lage
        else:
            # Sichtbar vorn (nie behind) - die Bewegung IST der Punkt.
            ent = {'fx': 'outline', 'power': 2, 'n': 1, 'anim': val,
                   'intent': True}
        out[i] = ent
        neu += 1
    if neu:
        print(f"  Self reference: {neu} caption(s) do what the speaker announces")
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
        print(f"  Learned: {applied} correction(s) from earlier edits applied")
    return fx_map


def correction_profile(corrections, min_count=2, max_rules=6):
    """v101e KORREKTUR-GEDAECHTNIS: verdichtet die frueheren Editor-Korrekturen
    dieses Kontos zu einem kurzen Vorlieben-Profil. Waehrend _apply_corrections
    nur EXAKT dieselbe Phrase nachzieht, generalisiert das Profil die TENDENZ
    (welcher Effekt wird bevorzugt getauscht, wird Wucht gesenkt, Anim entfernt)
    und fliesst als Kontext in den KI-Regie-Prompt - so lernt die KI auch fuer
    NEUE Phrasen aus alten Korrekturen. Rueckgabe: Prompt-Textblock oder ''.
    Nur Muster ab min_count Vorkommen (Einzelfaelle sind Rauschen, kein Stil)."""
    if not corrections:
        return ''
    swaps = {}          # (orig_fx -> user_fx): Anzahl
    anim_off = anim_on = deact = 0
    pow_lower = pow_raise = 0
    for c in corrections:
        of, uf = str(c.get('orig_fx', '')), str(c.get('user_fx', ''))
        if uf and of and of != uf:
            swaps[(of, uf)] = swaps.get((of, uf), 0) + 1
        if 'user_anim' in c:
            if str(c.get('user_anim', '')):
                anim_on += 1
            else:
                anim_off += 1
        if c.get('user_aktiv') is False:
            deact += 1
        op, up = c.get('orig_power'), c.get('user_power')
        if isinstance(op, (int, float)) and isinstance(up, (int, float)):
            if up < op:
                pow_lower += 1
            elif up > op:
                pow_raise += 1
    rules = []
    for (of, uf), n in sorted(swaps.items(), key=lambda kv: -kv[1]):
        if n >= min_count:
            rules.append((n, f"Effekt '{of}' wird bevorzugt zu '{uf}' geaendert "
                             f"({n}x) - waehle hier eher '{uf}'."))
    if anim_off >= min_count and anim_off > anim_on:
        rules.append((anim_off, f"Animationen werden oft entfernt ({anim_off}x) - "
                                f"setze Animationen sparsamer."))
    if deact >= min_count:
        rules.append((deact, f"Momente werden gelegentlich ganz deaktiviert "
                             f"({deact}x) - waehle zurueckhaltender, nur klare Hoehepunkte."))
    if pow_lower >= min_count and pow_lower > pow_raise:
        rules.append((pow_lower, f"Wucht wird oft gesenkt ({pow_lower}x) - "
                                 f"dosiere power zurueckhaltender."))
    elif pow_raise >= min_count and pow_raise > pow_lower:
        rules.append((pow_raise, f"Wucht wird oft erhoeht ({pow_raise}x) - "
                                 f"traue dich zu mehr power bei klaren Spitzen."))
    if not rules:
        return ''
    rules.sort(key=lambda r: -r[0])
    lines = '\n'.join('- ' + t for _, t in rules[:max_rules])
    return ("GELERNTE VORLIEBEN (aus frueheren Korrekturen dieses Kontos - "
            "generalisiere sie auf neue, aehnliche Stellen):\n" + lines + "\n\n")


# ---- v101s AUTO-AKZENTE ----------------------------------------------------------
# Dezente Motion-Graphics-Akzente auf dem Transkript (NICHT B-Roll): ein Counter auf
# einer echten Zahl, ein Chip auf einem markanten Begriff, ein kurzer Betonungs-Pop.
# Regel bleibt Finishing-Look: WENIGE Akzente, safe-zone-fromm, vom persoenlichen
# Stil-Profil dosiert, im Momente-Editor editierbar. KI schlaegt vor (ai_accents),
# ohne Key greift der deterministische heuristic_accents-Pfad. Beide Ausgaben laufen
# durch sanitize_accents (Dichte-Cap, gueltige Arten/Lanes) - Ansage ist Gesetz.
ACCENT_ARTS = ('counter', 'chip', 'badge', 'pop')
ACCENT_LANES = ('tl', 'tr', 'bl', 'br')

_ACC_STOP = set(
    'the a an to for of and or but my your our their with in on at is are was were be '
    'been being this that these those it its as by from we you they he she so if then '
    'than just really very can will would should der die das und oder aber mit von zu '
    'im in am ist sind war ich du wir ihr sie es ein eine einen dem den man auch noch '
    'nur schon sehr '
    # lange Binde-/Fuellwoerter, die sonst die Laenge-Heuristik (>=7) faelschlich faengt
    'because however therefore although between without another through people really '
    'actually basically literally something everything trotzdem trotz waehrend zwischen '
    'ohne durch wieder immer eigentlich einfach natuerlich'.split())


def _accent_number(tok):
    """Zahl im Wort -> (wert, suffix) oder None. '3x'/'50%'/'1.2k'/'87'."""
    m = re.match(r'^[^\d]*(\d[\d.,]*)\s*(%|x|k|m|bn|€|\$)?', tok or '')
    if not m:
        return None
    try:
        val = float(m.group(1).replace(',', ''))
    except ValueError:
        return None
    unit = (m.group(2) or '').lower()
    mult = {'k': 1e3, 'm': 1e6, 'bn': 1e9}.get(unit, 1)
    suf = unit if unit in ('%', 'x', '€', '$') else ''
    return (val * mult, suf)


def accent_style(profile):
    """Persoenliches Stil-Profil -> {'accent','intensity'(0..2),'vibe'}. Fehlt es,
    neutrale Defaults. intensity dosiert die Dichte (mehr = mehr Akzente)."""
    p = profile if isinstance(profile, dict) else {}
    acc = str(p.get('accent') or '#ff7a1a')
    try:
        inten = max(0.0, min(2.0, float(p.get('intensity', 1.0))))
    except (TypeError, ValueError):
        inten = 1.0
    return {'accent': acc, 'intensity': inten, 'vibe': str(p.get('vibe') or 'clean')}


def _accent_cap(words, intensity):
    """Wie viele Akzente maximal - dezent, laenge-skaliert x Intensitaet."""
    if not words:
        return 0
    dur = float(words[-1].get('end', 0)) - float(words[0].get('start', 0))
    base = max(1, int(dur / 8.0))              # ~1 Akzent je 8s
    return max(0, min(8, int(round(base * (0.5 + 0.75 * intensity)))))


def sanitize_accents(raw, words, profile=None, kw=None):
    """Beliebige (KI- oder Heuristik-)Akzentliste -> gueltige, dichte-begrenzte,
    zeitsortierte Liste mit Mindestabstand + Lane-Rotation. Verwirft Unfug still.
    DAS ist die Leitplanke: egal was die KI liefert, hier wird es dezent."""
    words = words or []
    st = accent_style(profile)
    cap = _accent_cap(words, st['intensity'])
    # v187: ein Akzent, der WOERTLICH das Schluesselwort wiederholt, ist
    # keine Ergaenzung - er steht doppelt im Bild und bleibt danach mit
    # veraltetem Inhalt stehen. Heuristik und Keyword-Picker benutzen
    # dieselben Kriterien, deshalb passierte das regelmaessig.
    _kwset = set(kw or ())
    _kwtxt = {clean(words[i].get('word', '')).strip('.,!?;:').upper()
              for i in _kwset if 0 <= i < len(words)}
    dur_v = float(words[-1].get('end', 0)) if words else 0.0
    seen, tmp = [], []
    for a in (raw or []):
        if not isinstance(a, dict):
            continue
        art = str(a.get('art', '')).lower()
        if art not in ACCENT_ARTS:
            continue
        try:
            t = round(float(a.get('zeit', 0)), 2)
        except (TypeError, ValueError):
            continue
        if t < 0 or (dur_v and t > dur_v):
            continue
        text = str(a.get('text', '')).strip()[:24]
        if art != 'counter' and not text:
            continue
        wert = a.get('wert')
        try:
            wert = float(wert) if wert is not None else None
        except (TypeError, ValueError):
            wert = None
        _ln = str(a.get('lane', '')).lower()
        tmp.append({'zeit': t, 'art': art, 'text': text, 'wert': wert,
                    'anker': int(a.get('anker', a.get('id', 0)) or 0),
                    'aktiv': a.get('aktiv', True) is not False,
                    'lane': _ln if _ln in ACCENT_LANES else None,
                    'quelle': str(a.get('quelle', 'ki'))})
    tmp.sort(key=lambda x: x['zeit'])
    out, last_t = [], -1e9
    for a in tmp:
        if a.get('anker') in _kwset or (a.get('text') or '').upper() in _kwtxt:
            continue
        if len([o for o in out if o['aktiv']]) >= cap and a['aktiv']:
            continue
        if a['zeit'] - last_t < 3.5:           # Mindestabstand -> dezent
            continue
        a['id'] = len(out)
        # v187: die Standzeit haengt am Anker-Wort statt bei 1.6 s fest zu
        # stehen. Ein Akzent, der eine Sekunde laenger steht als das Wort,
        # auf das er sich bezieht, liest sich als vergessene Grafik.
        _an = a.get('anker')
        if isinstance(_an, int) and 0 <= _an < len(words):
            _wd = float(words[_an].get('end', 0)) - float(words[_an].get('start', 0))
            a['dauer'] = round(max(0.9, min(1.6, _wd + 0.8)), 2)
        else:
            a['dauer'] = 1.6
        # Nutzer-Lane gewinnt (Editor); sonst rotieren, damit nichts stapelt.
        if not a.get('lane'):
            a['lane'] = ACCENT_LANES[len(out) % len(ACCENT_LANES)]
        out.append(a)
        last_t = a['zeit']
    return out


def heuristic_accents(words, cfg=None, profile=None, kw=None):
    """Deterministischer Akzent-Vorschlag OHNE KI (Notnagel ohne OpenAI-Key und der
    offline testbare Beweis): echte Zahlen -> counter, markante Begriffe -> chip.
    Dichte + Abstand macht sanitize_accents. Rueckgabe: Liste von Akzent-Dicts."""
    words = words or []
    if len(words) < 3:
        return []
    raw = []
    for i, w in enumerate(words):
        word = w.get('word', '')
        t = float(w.get('start', 0))
        num = _accent_number(word)
        if num is not None:
            lab = ''
            for j in range(i + 1, min(i + 3, len(words))):
                nx = clean(words[j].get('word', '')).strip('.,!?:;')
                if nx and nx.lower() not in _ACC_STOP:
                    lab = nx
                    break
            head = (str(int(num[0])) + num[1]) if num[1] else str(int(num[0]))
            raw.append({'zeit': t, 'art': 'counter', 'wert': num[0], 'anker': i,
                        'text': (head + (' ' + lab.upper() if lab else ''))[:24],
                        'quelle': 'heuristik'})
            continue
        core = clean(word).strip('.,!?:;')
        salient = core.isalpha() and core.lower() not in _ACC_STOP and (
            (core[:1].isupper() and i > 0) or len(core) >= 7)
        if salient:
            raw.append({'zeit': t, 'art': 'chip', 'text': core.upper()[:24],
                        'anker': i, 'quelle': 'heuristik'})
    return sanitize_accents(raw, words, profile, kw)


def ai_accents(words, language='auto', model='gpt-5', profile=None, cfg=None,
               kw=None):
    """KI-Akzent-Regie (Spiegel von ai_direct): GPT-5 waehlt WENIGE Stellen, die
    einen dezenten Motion-Graphics-Akzent verdienen, und die Art. Faellt bei jedem
    Fehler / fehlendem Key lautlos auf heuristic_accents zurueck. Immer durch
    sanitize_accents gefiltert (die KI kann nie zu dicht/zu wild werden)."""
    key = os.environ.get('OPENAI_API_KEY')
    words = words or []
    if not key or len(words) < 3:
        return heuristic_accents(words, cfg, profile, kw)
    st = accent_style(profile)
    cap = _accent_cap(words, st['intensity'])
    if cap <= 0:
        return []
    wl = ' '.join(f"[{i}]{clean(w.get('word',''))}" for i, w in enumerate(words)
                  if clean(w.get('word', '')).strip())[:6000]
    sys_p = (
        "Du bist Senior Motion-Graphics-Designer (2026). Du setzt DEZENTE Akzente auf "
        "ein gesprochenes Transkript - KEIN B-Roll, kein Deko-Feuerwerk. Ein Akzent nur, "
        "wo er dem Gesagten dient: eine echte ZAHL -> 'counter'; ein zentraler BEGRIFF/"
        "Marke -> 'chip'; ein Guetesiegel/Status -> 'badge'; eine kurze Betonung -> 'pop'. "
        f"Waehle HOECHSTENS {cap} Stellen, gut verteilt (>=4s Abstand). Passe Text + Art "
        "an Thema und Aussage an. Antworte NUR JSON: "
        '{"akzente":[{"anker":<wortindex>,"zeit":<sekunden>,"art":"counter|chip|badge|pop",'
        '"text":"<max 3 Woerter, GROSS>","wert":<zahl oder null>}]}')
    usr = (f"Sprache: {language}\nWORTLISTE (Index in eckigen Klammern):\n{wl}\n\n"
           "Gib die dezenten Akzente als JSON zurueck.")
    try:
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': sys_p},
                    {'role': 'user', 'content': usr}],
            max_toks=1200, temperature=0.3), timeout=90)
        data = json.loads(_txt)
        arr = data.get('akzente') if isinstance(data, dict) else data
        san = sanitize_accents(arr, words, profile, kw)
        for a in san:
            a['quelle'] = 'ki'
        return san if san else heuristic_accents(words, cfg, profile, kw)
    except Exception as e:
        print(f"AI accents unavailable ({type(e).__name__}), falling back to the heuristic.")
        return heuristic_accents(words, cfg, profile, kw)


# ---- v101t Akzent-Compositing: der dezente Akzent wird zum kleinen Alpha-Sprite -----

def _hex_rgb(h):
    """'#rrggbb' -> (r,g,b). Fehlerhaft -> DouchkoVE-Orange."""
    h = str(h or '').lstrip('#')
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return (255, 122, 26)


def _accent_ease(x):
    """Overshoot-Pop (Feder), 0->~1.06->1. Kein linearer Tell."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1 - math.pow(1 - x, 3) * math.cos(x * 3.4)


def _accent_sprite(art, text, wert, count_prog, ent, style, W):
    """Ein Akzent -> RGBA-Sprite (numpy uint8), Senior-Motion-Designer-Niveau:
    weicher Schlagschatten (Lesbarkeit auf JEDEM Footage) + Akzent-Aussenglow +
    Glas-Pille mit Vertikal-Gradient + Top-Highlight + Akzent-Rand. counter zaehlt
    hoch mit einer Fortschritts-Fuellung, badge = Vektor-Haken im Akzent-Chip,
    pop = betonter Text ohne Pille + Unterstrich-Wisch. Alles relativ zu W."""
    from PIL import ImageFilter
    u = W / 1080.0
    rgb = _hex_rgb(style.get('accent'))
    fs = max(int(round(40 * u)), 12)
    try:
        font = ImageFont.truetype(os.path.join(HERE, 'fonts', 'poppins_b.ttf'), fs)
    except Exception:
        font = ImageFont.load_default()

    disp = text
    if art == 'counter' and wert is not None:
        m = re.match(r'^\s*(\d[\d.,]*)(.*)$', str(text))
        if m:
            disp = str(int(round(wert * count_prog))) + m.group(2)
    label = (disp or '').strip() or ' '

    tmp = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    bb = tmp.textbbox((0, 0), label, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    P = int(round(20 * u))                    # Rand fuer Schatten + Glow

    if art == 'pop':
        m2 = int(round(16 * u))
        pw, ph = tw + m2 * 2, th + m2 * 2 + int(round(12 * u))
        img = Image.new('RGBA', (pw + 2 * P, ph + 2 * P), (0, 0, 0, 0))
        tx, ty = P + m2 - bb[0], P + m2 - bb[1]
        # weicher Textschatten fuer Lesbarkeit
        sh = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((tx, ty + int(3 * u)), label, font=font, fill=(0, 0, 0, 200))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4 * u)))
        d = ImageDraw.Draw(img)
        d.text((tx, ty), label, font=font, fill=(255, 255, 255, 255))
        uw = int(tw * max(0.0, min(1.0, ent)))
        uy = ty + th + int(round(9 * u))
        if uw > 1:
            d.rounded_rectangle([tx, uy, tx + uw, uy + int(round(6 * u))],
                                radius=int(round(3 * u)), fill=(*rgb, 255))
        return np.array(img)

    mark = 'dot' if art in ('chip', 'counter') else ('check' if art == 'badge' else '')
    dot_r = int(round(7 * u)) if mark else 0
    pad_x = int(round(30 * u))
    pad_y = int(round(18 * u))
    dot_gap = (dot_r * 2 + int(round(13 * u))) if dot_r else 0
    pw = tw + pad_x * 2 + dot_gap
    ph = th + pad_y * 2
    rad = ph // 2
    W_, H_ = pw + 2 * P, ph + 2 * P
    img = Image.new('RGBA', (W_, H_), (0, 0, 0, 0))
    box = [P, P, P + pw - 1, P + ph - 1]

    # 1) Schlagschatten: Pillen-Silhouette, dunkel, versetzt, weich.
    sh = Image.new('RGBA', (W_, H_), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [box[0], box[1] + int(6 * u), box[2], box[3] + int(6 * u)],
        radius=rad, fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9 * u)))
    # 2) Akzent-Aussenglow: gleiche Form, Akzentfarbe, stark verwischt.
    gl = Image.new('RGBA', (W_, H_), (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle(box, radius=rad, fill=(*rgb, 90))
    img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(11 * u)))
    # 3) Glas-Koerper: Vertikal-Gradient (oben heller) durch Rundeck-Maske.
    grad = np.empty((ph, pw, 4), np.uint8)
    top, bot = np.array((34, 34, 42)), np.array((12, 12, 17))
    ramp = np.linspace(0, 1, ph)[:, None]
    grad[..., :3] = (top * (1 - ramp) + bot * ramp)[:, None, :].astype(np.uint8)
    grad[..., 3] = 224
    mask = Image.new('L', (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=rad, fill=255)
    body = Image.fromarray(grad)
    body.putalpha(Image.composite(mask, Image.new('L', (pw, ph), 0), mask))
    img.alpha_composite(body, (P, P))
    d = ImageDraw.Draw(img)
    # 4) Akzent-Rand (der Gradient gibt schon Tiefe - kein Glanz-Bogen noetig).
    d.rounded_rectangle(box, radius=rad, outline=(*rgb, 240),
                        width=max(int(round(2.5 * u)), 2))
    # 5) Marke (Punkt / Vektor-Haken).
    cyd = H_ // 2
    cxd = P + pad_x - int(round(2 * u))
    if mark == 'dot':
        gd = Image.new('RGBA', (W_, H_), (0, 0, 0, 0))
        ImageDraw.Draw(gd).ellipse([cxd - dot_r, cyd - dot_r, cxd + dot_r, cyd + dot_r],
                                   fill=(*rgb, 255))
        img.alpha_composite(gd.filter(ImageFilter.GaussianBlur(3 * u)))
        d.ellipse([cxd - dot_r, cyd - dot_r, cxd + dot_r, cyd + dot_r], fill=(*rgb, 255))
    elif mark == 'check':
        lw = max(int(round(3.5 * u)), 2)
        d.line([(cxd - dot_r, cyd), (cxd - dot_r * 0.2, cyd + dot_r),
                (cxd + dot_r, cyd - dot_r)], fill=(*rgb, 255), width=lw, joint='curve')
    # 6) Text.
    tx = P + pad_x + dot_gap - bb[0]
    d.text((tx, P + pad_y - bb[1]), label, font=font, fill=(245, 245, 248, 255))
    # 7) counter: duenne Fortschritts-Fuellung unter der Zahl (zaehlt mit hoch).
    if art == 'counter':
        uy = P + ph - int(round(7 * u))
        fw = int((pw - pad_x - dot_gap) * max(0.0, min(1.0, count_prog)))
        if fw > 1:
            d.rounded_rectangle([tx, uy, tx + fw, uy + int(round(4 * u))],
                                radius=int(round(2 * u)), fill=(*rgb, 255))
    return np.array(img)


def _accent_place(lane, w, h, W, H, pz):
    """Lane -> Bildposition (cx,cy), safe-zone-fromm. Akzente sitzen im OBEREN Band
    (Captions liegen unten/mittig) - bl/br also nur bis Bildmitte."""
    mL = int(W * 0.055)
    mR = int(W * 0.055)
    if pz:
        mL = max(mL, int(pz.get('left', 0)))
        rr = pz.get('right_rail')
        if rr:
            mR = max(mR, W - int(rr) + int(W * 0.01))
    top = int(H * (0.14 if not pz else max(0.14, pz.get('top', 0) / H + 0.04)))
    left_x = mL + w // 2
    right_x = W - mR - w // 2
    y_top = top + h // 2
    y_mid = int(H * 0.40) + h // 2
    return {
        'tl': (left_x, y_top), 'tr': (right_x, y_top),
        'bl': (left_x, y_mid), 'br': (right_x, y_mid),
    }.get(lane, (left_x, y_top))


def _caption_boxes(plans, t0, t1, W, H):
    """Bounding-Boxen der Caption-Plaene, die im Fenster [t0,t1] sichtbar sind."""
    out = []
    for p in (plans or []):
        if p.get('end', 0) < t0 or p.get('start', 1e9) > t1:
            continue
        # v187: die ECHTE Lage eines Textblocks steht in seinen Items -
        # jedes traegt absolute cx/cy und sein Sprite. Bis dahin fiel jeder
        # Flow-/Stack-Plan auf eine Ersatzbox aus der Zeit VOR v143 zurueck
        # (mittig, 0.31 bis 0.48 H). Der Akzent fand deshalb nie eine
        # Kollision und wurde ueber die Caption gezeichnet.
        _its = [it for it in (p.get('front') or [])
                if it.get('arr') is not None and it.get('cx') is not None]
        if _its:
            x0 = min(it['cx'] - it['arr'].shape[1] / 2.0 for it in _its)
            x1 = max(it['cx'] + it['arr'].shape[1] / 2.0 for it in _its)
            y0 = min(it['cy'] - it['arr'].shape[0] / 2.0 for it in _its)
            y1 = max(it['cy'] + it['arr'].shape[0] / 2.0 for it in _its)
            out.append((x0, y0, x1, y1))
            continue
        arr = p.get('arr')
        if arr is None or not hasattr(arr, 'shape'):
            continue          # kein Text (z. B. reiner Kamera-Impuls)
        cx = p.get('cx', W / 2)
        cy = p.get('cy', p.get('by', H * 0.398))
        cw, ch = arr.shape[1], arr.shape[0]
        out.append((cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))
    return out


def resolve_accent_positions(accents, plans, W, H, pz=None):
    """v101u: Akzent-Position EINMAL vor dem Rendern festlegen, so dass sie die im
    Zeitfenster aktiven Captions NICHT ueberdeckt. Bevorzugt die Lane; kollidiert
    sie, wird der Akzent knapp UEBER die oberste Caption gehoben. Danach stabil
    (kein Per-Frame-Springen). Setzt a['cx'], a['cy']."""
    for a in (accents or []):
        t0 = float(a.get('zeit', 0))
        t1 = t0 + float(a.get('dauer', 1.6))
        try:
            spr = _accent_sprite(a.get('art', 'chip'), a.get('text', ''),
                                 a.get('wert'), 1.0, 1.0, {'accent': '#ffffff'}, W)
            h, w = spr.shape[:2]
        except Exception:
            w, h = int(W * 0.3), int(H * 0.06)
        cx, cy = _accent_place(a.get('lane', 'tl'), w, h, W, H, pz)
        boxes = _caption_boxes(plans, t0, t1, W, H)
        ax0, ay0, ax1, ay1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        hit = [b for b in boxes
               if not (ax1 < b[0] or ax0 > b[2] or ay1 < b[1] or ay0 > b[3])]
        if hit:
            cap_top = min(b[1] for b in hit)
            cy = max(int(H * 0.04) + h / 2, cap_top - int(H * 0.02) - h / 2)
        a['cx'], a['cy'] = int(cx), int(cy)
    return accents


def draw_accents(comp, t, accents, style, W, H, pz=None):
    """Zeichnet die aktiven Akzente OBEN auf das fertige Frame (nach den Captions).
    Feder-Einflug, Halt, weicher Abgang; Counter zaehlt hoch. Reine paste()-Blits.
    Position kommt (falls vorher aufgeloest) aus a['cx']/a['cy'], sonst aus der Lane."""
    for a in accents:
        if not a.get('aktiv', True):
            continue
        t0 = float(a.get('zeit', 0))
        dur = float(a.get('dauer', 1.6))
        local = t - t0
        fade_out = 0.4
        if local < -0.03 or local > dur + fade_out:
            continue
        ent = _accent_ease(min(1.0, max(0.0, local) / 0.42))
        if local <= dur:
            alpha = min(1.0, local / 0.22) if local < 0.22 else 1.0
        else:
            alpha = max(0.0, 1 - (local - dur) / fade_out)
        scale = 0.86 + 0.14 * ent
        count_prog = _accent_ease(min(1.0, max(0.0, local) / 0.6))
        try:
            spr = _accent_sprite(a.get('art', 'chip'), a.get('text', ''),
                                 a.get('wert'), count_prog, ent, style, W)
        except Exception:
            continue
        sh, sw = spr.shape[:2]
        if 'cx' in a and 'cy' in a:
            cx, cy = int(a['cx']), int(a['cy'])
        else:
            cx, cy = _accent_place(a.get('lane', 'tl'),
                                   int(sw * scale), int(sh * scale), W, H, pz)
        paste(comp, spr, cx, cy, W, H, scale=scale, opacity=alpha)
    return comp


def apply_keyword_marks(kw, fx_map, words, marks, cfg):
    """v101m: Keyword-Markierungen aus dem Text-Editor uebersteuern die KI-Wahl.
    marks[i] = 1 (Wort ERZWINGEN als Highlight) / -1 (Wort NIE highlighten).
    Die KI-Regie laeuft normal - hier wird danach nachjustiert. Erzwungene
    Momente tragen user_pick=True und ueberleben so Dichte- und B-Roll-Gate
    (wie intent, aber ohne dessen semantische Platzierung).
    Rueckgabe: (kw, fx_map)."""
    if not marks:
        return kw, fx_map
    kw = set(kw)
    fx_map = dict(fx_map or {})
    rot = [m for m in (cfg.get('effects', {}).get('keyword_rotation')
                       or ['behind', 'outline', 'cascade', 'ground'])
           if m and m != 'none'] or ['outline']
    added = removed = 0
    on = sorted(i for i, v in marks.items() if v == 1 and 0 <= i < len(words))
    for pos, i in enumerate(on):
        if i not in kw:
            kw.add(i)
            added += 1
        info = dict(fx_map.get(i)) if isinstance(fx_map.get(i), dict) else {}
        info.setdefault('fx', rot[pos % len(rot)])
        info.setdefault('power', 2)
        info.setdefault('n', 1)
        info['user_pick'] = True
        fx_map[i] = info
    for i, v in marks.items():
        if v == -1 and i in kw:
            kw.discard(i)
            fx_map.pop(i, None)
            removed += 1
    if added or removed:
        print(f"Text markers: {added} forced, {removed} removed")
    return kw, fx_map


def split_forced_groups(groups, fx_map):
    """v101n: Liegen MEHRERE erzwungene Woerter (user_pick) in derselben
    Phrasen-Gruppe, wuerde nur EINES ein Highlight - eine Phrase = ein Moment.
    Deshalb die Gruppe an den erzwungenen Woertern auftrennen: jedes markierte
    Wort beginnt eine eigene Untergruppe (=eigenes Highlight). Betrifft NUR
    Gruppen mit >=2 Marken; alles andere bleibt exakt wie es war."""
    if not fx_map:
        return groups
    def _forced(j):
        info = fx_map.get(j)
        return isinstance(info, dict) and info.get('user_pick')
    out = []
    for g in groups:
        pos = [k for k, j in enumerate(g) if _forced(j)]
        if len(pos) < 2:
            out.append(g)
            continue
        start = 0
        for k in pos:
            if k == 0:
                continue                  # erstes Wort beginnt ohnehin die Gruppe
            out.append(g[start:k])
            start = k
        out.append(g[start:])
    return [s for s in out if s]


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


def ai_direct(words, language, model='gpt-5', voice_wav=None, validate=True):
    """LLM waehlt Keywords, Phrasen, Effekte und Wucht. Gibt {index: info} zurueck oder None.
    Lange Videos werden in Etappen analysiert, damit die JSON-Antwort nie abgeschnitten wird.

    v80d: WORTLISTE ohne STOPWORDS an die Regie-KI - sie KANN Hilfsverben gar
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
    # v101e: Korrektur-Gedaechtnis - Vorlieben aus frueheren Edits verdichten
    # und der KI als Kontext geben (generalisiert ueber exakte Phrasen hinaus).
    _corr = _load_corrections()
    prof_block = correction_profile(_corr)
    if prof_block:
        _n_rules = sum(1 for l in prof_block.splitlines() if l.startswith('- '))
        print(f"Correction memory: {_n_rules} preferences feed into the direction")
    # v96x: BEWEIS im Job-Log, ob Referenzen wirklich in den Prompt fliessen -
    # vorher war ein leerer/verlorener Block unsichtbar ("KI wendet nichts an").
    if ref_block:
        _n_refs = sum(1 for l in ref_block.splitlines() if l.startswith('- '))
        # v141: Quelle mitschreiben. Ohne sie konnte die UI nicht unterscheiden,
        # ob der Kunde WIRKLICH etwas gelernt hat oder ob nur der Haus-Stil
        # wirkt - genau daraus wurde die falsche Meldung "N learned references".
        _src = (os.environ.get('DVE_REFS_SOURCE') or '').strip().lower()
        _lbl = {'eigene': 'own', 'haus': 'house style'}.get(_src, 'unknown')
        print(f"Style references: {_n_refs} active ({_lbl}) - feeding into the AI direction")
    else:
        print("Style references: none found (direction runs without a style anchor)")
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
        listing = prof_block + ref_block + lang_hint + part_hint + 'TRANSKRIPT:\n' + prose + \
                  '\n\nWORTLISTE (nur waehlbare Substanz-Woerter, ' \
                  'Fuellwoerter wurden entfernt):\n' + ' '.join(wl_toks) + pegel_hint
        try:
            _txt = _oai_text(key, _oai_json(
                model, [{'role': 'system', 'content': REGIE_PROMPT},
                        {'role': 'user', 'content': listing}],
                max_toks=3000, temperature=0.2), timeout=180)
            res = parse_regie(_txt, words, language)
            if res:
                # Overlap-Bereich: Momente aus dem Kontext-Vorlauf verwerfen,
                # der vorherige Chunk hat sie bereits (oder bewusst uebergangen).
                if ci > 0:
                    res = {i: v for i, v in res.items() if i >= sel}
                merged.update(res)
            if len(chunks) > 1:
                print(f"  AI director stage {ci + 1}/{len(chunks)}: "
                      f"{len(res) if res else 0} moments")
        except Exception as e:
            print(f"AI director stage {ci + 1}/{len(chunks)} unavailable "
                  f"({type(e).__name__})" if len(chunks) > 1 else
                  f"AI director unavailable ({type(e).__name__}), falling back to automatic.")
    if not merged:
        return None
    if validate:
        merged = _regie_validate(merged, words, model, key)
    if voice_wav:
        merged = _audio_boost(merged, words, voice_wav)
    merged = _regie_sanity(merged, words)
    merged = _speech_intent(merged, words)          # Text folgt der Ansage
    merged = _apply_corrections(merged, words, _corr)  # Nutzer gewinnt zuletzt (exakte Phrase)
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

def speech_rate_at(words, i, win=5):
    """Sprechtempo (Woerter/Sekunde) im Fenster um Wort i. 0.0 = unbrauchbar."""
    if not words:
        return 0.0
    a = max(0, i - win // 2)
    b = min(len(words), a + win)
    a = max(0, b - win)
    try:
        span = float(words[b - 1]['end']) - float(words[a]['start'])
    except (KeyError, TypeError, ValueError):
        return 0.0
    if span <= 0.05:
        return 0.0
    return (b - a) / span


def build_groups(words, max_words=3, min_hold=0.0, hard_max=5,
                 adaptive=False, power_at=None):
    """Wortgruppen wie ein Cutter: nie ueber Satzgrenzen hinweg. Whisper liefert
    auf Wort-Ebene keine Satzzeichen, also zaehlen Sprechpausen als Grenze.

    v140 TEMPO-KURVE (adaptive=True): Ein Cutter haelt das Tempo nicht konstant,
    er formt eine Kurve. Zwei Kopplungen bilden das ab:
      (a) Sprechtempo: schnell gesprochene Passagen bekommen groessere Bloecke
          (sonst flackert der Text), langsam-betonte kleinere (mehr Gewicht).
      (b) Pointe: ein power-3-Wort steht ALLEIN. Kein Mitlaeufer davor, keiner
          dahinter - genau so setzt ein Editor die Schlusspointe.
    power_at = {wort_index: power}. Ohne die Flags bleibt das Verhalten exakt
    wie vorher (Rueckwaertskompatibilitaet fuer Tests und Alt-Aufrufer)."""
    groups, cur = [], []
    punch_groups = set()

    def _is_punch(idx):
        if not power_at:
            return False
        try:
            return int(power_at.get(idx, 2) or 2) >= 3
        except (TypeError, ValueError):
            return False

    for i, w in enumerate(words):
        lim = max_words
        if adaptive:
            # Schwellen bewusst konservativ: normale Konversation (rund 2.3
            # bis 2.9 Woerter/s) bleibt beim Standard-Tempo. Nur wirklich
            # schnelle (ab 180 wpm) bzw. betont langsame Passagen verschieben
            # die Blockgroesse, sonst waere es kein Akzent, sondern ein neuer
            # Default.
            # Bewusst nur EIN Wort Abweichung nach oben oder unten. Groessere
            # Bloecke ueberspannen sonst haeufiger eine B-Roll-Grenze und
            # fallen dann komplett weg - die Kurve darf die Abdeckung nicht
            # kosten. Ein Wort reicht, damit der Unterschied traegt.
            wps = speech_rate_at(words, i)
            if wps >= 3.2:
                lim = min(hard_max, max_words + 1)
            elif 0.0 < wps <= 1.8:
                lim = max(1, max_words - 1)
        # Pointe isolieren: laufende Gruppe VOR dem Einschlag schliessen.
        if adaptive and _is_punch(i) and cur:
            groups.append(cur); cur = []
        cur.append(i)
        if adaptive and _is_punch(i):
            punch_groups.add(len(groups))
            groups.append(cur); cur = []
            continue
        pause = (i + 1 < len(words)
                 and words[i + 1]['start'] - w['end'] > 0.35)
        if (len(cur) >= lim or pause
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
                # v140: Die Pointe bleibt allein - sie darf weder einen Vorlaeufer
                # anziehen noch selbst angehaengt werden.
                punch_here = (adaptive
                              and (any(_is_punch(x) for x in prev)
                                   or any(_is_punch(x) for x in g)))
                # v140: Bei langsamer, betonter Rede laenger stehen lassen
                # (weniger Merges), bei schnellem Sprechen frueher zusammen-
                # ziehen - das ist die zweite Haelfte der Tempo-Kurve.
                hold = min_hold
                if adaptive:
                    wps = speech_rate_at(words, prev[0])
                    if 0.0 < wps <= 1.8:
                        hold = min_hold * 1.25
                    elif wps >= 3.6:
                        hold = min_hold * 0.8
                if (dauer < hold and not satzende and not punch_here
                        and luecke <= 0.35
                        and len(prev) + len(g) <= hard_max):
                    merged[-1] = prev + g
                    continue
            merged.append(list(g))
        groups = merged
    return groups

def pace_power_map(fx_map):
    """{wort_index: power} fuer die Tempo-Kurve, aus der Regie-Map."""
    out = {}
    for i, v in (fx_map or {}).items():
        if not isinstance(v, dict):
            continue
        try:
            out[int(i)] = int(v.get('power', 2) or 2)
        except (TypeError, ValueError):
            continue
    return out


# --- v193 BLOCK-EDITOR ------------------------------------------------------
# Ein Block ist das, was gleichzeitig im Bild steht. Bis v192 entstand er bei
# JEDEM Render neu aus Pausen, Satzzeichen, Sprechtempo und der KI-Wucht
# (build_groups) - er hatte keine Identitaet, die ein Nutzer haette anfassen
# koennen. Der Blockplan dreht das um: liegt eine Nutzer-Aufteilung vor, IST
# sie die Aufteilung. Nicht ein Nachschlagen obendrauf, sondern die Quelle.
#
# Warum ein eigenes Sidecar und nicht ein Feld in _momente.json:
#   * _momente.json ist ueber Keyword-Wortindizes verschluesselt und wird bei
#     jedem Lauf aus 'for i in sorted(kw)' neu gebaut. Ein Fliess-Block hat
#     dort keinen Platz, und faellt ein Index aus kw, waeren die Nutzerdaten
#     still weg.
#   * Der Regie-Cache kennt nur acht Keyword-Schluessel. Alles andere ist beim
#     zweiten Render verschwunden (v159-Fehlertyp).
# Der Blockplan haengt deshalb an KEINER Regie-Struktur, sondern nur am
# Wortstrom, und wird an der immer laufenden Stelle geladen.
BLOCK_KEYS = ('i0', 'i1', 'aktiv', 'text', 'anim', 'fx', 'power',
              'groesse', 'start', 'end')


class _SchattenWorte:
    """Wortliste mit ueberschriebenem TEXT bei unveraenderten ZEITEN.

    Der Block-Editor laesst den Nutzer den Text einer Zeile umschreiben.
    Die Zeiten duerfen dabei nicht wandern - an ihnen haengen Karaoke-Emphase,
    SFX-Onsets, Beat-Grid und der Solo-Riegel. Eine echte Kopie der ganzen
    Wortliste je Block waere bei 500 Woertern und 150 Bloecken 75000
    Dict-Kopien; dieser Zugriffs-Wrapper kostet nichts und aendert nur das,
    was wirklich anders ist."""

    __slots__ = ('_w', '_t')

    def __init__(self, words, texte):
        self._w = words
        self._t = texte or {}

    def __len__(self):
        return len(self._w)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self._w)))]
        w = self._w[i]
        neu = self._t.get(i if i >= 0 else len(self._w) + i)
        if neu is None:
            return w
        d = dict(w)
        d['word'] = neu
        return d

    def __iter__(self):
        for i in range(len(self._w)):
            yield self[i]


def block_texte(blk, g, words):
    """Nutzer-Text eines Blocks auf seine Wortindizes verteilen.

    Der Nutzer tippt eine ZEILE, die Engine denkt in Woertern. Stimmen die
    Anzahlen nicht ueberein, wird verteilt statt abgelehnt:
      * mehr getippte Woerter als Indizes -> der Rest haengt am letzten Index
        (die Woerter erscheinen dann gemeinsam, so wie sie gesprochen werden).
      * weniger -> die uebrigen Indizes bekommen leeren Text und fallen aus
        dem Satz. Ein Wort loeschen muss moeglich sein.
    Rueckgabe: ({index: text}, [sichtbare indizes])."""
    roh = str((blk or {}).get('text') or '').strip()
    if not roh or not g:
        return {}, list(g)
    tok = [t for t in roh.split() if t]
    if not tok:
        return {}, list(g)
    if len(tok) > len(g):
        tok = tok[:len(g) - 1] + [' '.join(tok[len(g) - 1:])] if len(g) > 1 \
            else [' '.join(tok)]
    aus, sicht = {}, []
    for n, i in enumerate(g):
        if n < len(tok):
            aus[i] = tok[n]
            sicht.append(i)
        else:
            aus[i] = ''
    return aus, sicht


def _block_norm(roh, n_words):
    """Blockplan pruefen und in eine lueckenlose, sortierte Liste bringen.

    Ein kaputter Eintrag darf nie den ganzen Plan kippen (das ist heute der
    Fehler bei _momente.json: EIN falscher Wert verwirft still alle
    Nutzer-Einstellungen des Videos). Deshalb faengt die Pruefung pro Eintrag,
    nicht global.
    Rueckgabe: (bloecke, meldungen)."""
    if not isinstance(roh, list) or not n_words:
        return [], []
    out, warn = [], []
    for nr, b in enumerate(roh):
        if not isinstance(b, dict):
            warn.append(f'block {nr}: not an object')
            continue
        try:
            i0 = int(b.get('i0'))
            i1 = int(b.get('i1'))
        except (TypeError, ValueError):
            warn.append(f'block {nr}: word range missing')
            continue
        i0 = max(0, min(i0, n_words))
        i1 = max(0, min(i1, n_words))
        if i1 <= i0:
            warn.append(f'block {nr}: empty word range')
            continue
        e = {'i0': i0, 'i1': i1, 'aktiv': b.get('aktiv', True) is not False}
        # Jedes Feld einzeln - ein unbrauchbarer Wert kostet nur dieses Feld.
        t = b.get('text')
        if isinstance(t, str) and t.strip():
            e['text'] = t.strip()[:200]
        a = str(b.get('anim') or '').strip().lower()
        if a in ANIM_LIST:
            e['anim'] = a
        elif a and a not in ('', 'auto'):
            warn.append(f'block {nr}: unknown animation {a!r}')
        f = str(b.get('fx') or '').strip().lower()
        if f in ('behind', 'cascade', 'blurin', 'outline', 'ground'):
            e['fx'] = f
        elif f and f != 'auto':
            warn.append(f'block {nr}: unknown effect {f!r}')
        try:
            p = int(b.get('power') or 0)
            if p in (1, 2, 3):
                e['power'] = p
        except (TypeError, ValueError):
            warn.append(f'block {nr}: power not a number')
        try:
            gr = float(b.get('groesse') or 0)
            if gr > 0:
                e['groesse'] = max(0.5, min(2.0, gr))
        except (TypeError, ValueError):
            warn.append(f'block {nr}: size not a number')
        for k in ('start', 'end'):
            v = b.get(k)
            if v is None or v == '':
                continue
            try:
                e[k] = max(0.0, float(v))
            except (TypeError, ValueError):
                warn.append(f'block {nr}: {k} not a number')
        if 'start' in e and 'end' in e and e['end'] <= e['start']:
            # Unbrauchbares Zeitpaar: lieber die Wortzeiten nehmen als einen
            # Block zu zeigen, der nie endet.
            e.pop('start'); e.pop('end')
            warn.append(f'block {nr}: end before start, using word timing')
        out.append(e)
    out.sort(key=lambda x: (x['i0'], x['i1']))
    # Ueberlappungen aufloesen: ein Wort gehoert genau einem Block. Sonst
    # stuenden zwei Bloecke gleichzeitig mit demselben Wort im Bild.
    sauber, letzte = [], -1
    for e in out:
        if e['i0'] < letzte:
            e['i0'] = letzte
            if e['i1'] <= e['i0']:
                warn.append('overlapping block dropped')
                continue
        letzte = e['i1']
        sauber.append(e)
    return sauber, warn


def load_bloecke(pfad, n_words):
    """Blockplan von der Platte holen. Fehlt er oder ist er unbrauchbar,
    gilt die Engine-Aufteilung - der Nutzer verliert nie mehr als seine
    eigene Aenderung."""
    if not pfad or not os.path.exists(pfad):
        return []
    try:
        roh = json.load(open(pfad, encoding='utf-8'))
    except Exception as e:
        print(f"Block plan ignored ({type(e).__name__})")
        return []
    bl, warn = _block_norm(roh, n_words)
    for w in warn[:6]:
        print(f"Block plan: {w}")
    if warn and len(warn) > 6:
        print(f"Block plan: {len(warn) - 6} more notes")
    return bl


def bloecke_groups(bloecke, n_words):
    """Nutzer-Bloecke -> Wortgruppen, genau wie build_groups sie liefert.
    Abgeschaltete Bloecke fallen raus; Woerter, die in KEINEM Block liegen
    (z.B. weil der Nutzer einen Block geloescht hat), bleiben ebenfalls weg -
    das ist die Ansage 'hier soll kein Text stehen'."""
    out = []
    for b in bloecke:
        if not b.get('aktiv', True):
            continue
        g = [i for i in range(b['i0'], min(b['i1'], n_words))]
        if g:
            out.append(g)
    return out


def groups_for(words, cfg, fx_map=None, bloecke=None):
    """EINE Quelle fuer die Chunk-Bildung. build_plans und der Flow-Cache
    muessen exakt dieselben Gruppen sehen, sonst zeigen die Flow-Indizes auf
    den falschen Chunk.

    v193: liegt ein Nutzer-Blockplan vor, gewinnt er vollstaendig. Bewusst
    OHNE Nachbearbeitung durch build_groups - eine Nutzer-Aufteilung, die
    danach noch vom Merge-Pass zusammengelegt wird, ist keine."""
    if bloecke:
        return bloecke_groups(bloecke, len(words))
    eff = (cfg or {}).get('effects', {})
    return list(build_groups(
        words, eff.get('words_per_group', 3),
        min_hold=float(eff.get('chunk_hold_min', 0.65)),
        hard_max=int(eff.get('words_per_group_max', 5)),
        adaptive=bool(eff.get('pace_adaptive', True)),
        power_at=pace_power_map(fx_map)))


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


def beat_grid_times(beat_env, fps, conf, bpm, min_conf=0.30):
    """v101c Beat-Grid: extrahiert die Beat-Zeitpunkte (Sekunden) aus der
    Beat-Envelope. Rueckgabe: sortierte Liste oder None.

    None wenn kein verlaesslicher Takt vorliegt (conf < min_conf) - dann
    bleibt das Timing rein sprachgetrieben. Ein Beat ist ein lokales Maximum
    der Envelope ueber 0.55; unter 4 Beats gilt der Takt als Zufall."""
    if conf < min_conf or bpm <= 0 or beat_env is None:
        return None
    env = np.asarray(beat_env, np.float32)
    times = []
    for i in range(1, len(env) - 1):
        if env[i] > 0.55 and env[i] >= env[i - 1] and env[i] > env[i + 1]:
            times.append(i / float(fps))
    if len(times) < 4:
        return None
    return times


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


def compose_phrase(phrase, words, S, W, H, portrait=False, safe=False,
                   loud=None):
    """Setzt eine Phrase wie ein Magazin-Layout, nach dem Muster hochwertiger
    Social-Edits: Bindewoerter als kleine Akzent-Zeile darueber, der Kern riesig
    in Weiss, ein kleines Abschlusswort kursiv schraeg ueberlappend.
    Jedes Wort erscheint zu seinem eigenen Sprech-Zeitpunkt.
    v101 Betonungs-Typografie: 'loud' ({wort_index: '!'|'~'} aus
    _word_loudness) setzt laut gesprochene Woerter SCHWERER (echte
    Variable-Font-Achse) und leise leichter - die Zeile sieht aus, wie die
    Stimme klingt. Ohne Marken identisches Verhalten wie vorher."""
    CONNECTORS = {'im', 'in', 'am', 'an', 'auf', 'der', 'die', 'das', 'dem', 'den',
                  'des', 'mit', 'von', 'vom', 'zum', 'zur', 'zu', 'fuer', 'für',
                  'und', 'of', 'to', 'the', 'at', 'on', 'for', 'and'}
    loud = loud or {}
    toks = []
    for j in phrase:
        raw = clean(words[j]['word'])
        toks.append({'raw': raw, 'up': raw.upper(), 'j': j,
                     'mark': loud.get(j),
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
    if any(t.get('mark') for t in run) and len(run) >= 2:
        # Betonungs-Kern: pro Wort eigener Schnitt. '!' = schwer (+Groesse),
        # '~' = leicht. Grundlinie = Unterkante (Kern ist CAPS, keine
        # Unterlaengen). Passt die Groesse an, bis die Zeile in max_w passt.
        def _bau(sz):
            parts = []
            for t in run:
                m = t.get('mark')
                w_sz = int(sz * (1.06 if m == '!' else (0.94 if m == '~' else 1.0)))
                # Normalstufe 760 entspricht dem statischen Schnitt - nur die
                # markierten Woerter weichen ab (laut 900, leise 500)
                wg = 900 if m == '!' else (500 if m == '~' else 760)
                parts.append(S.text(t['up'], max(w_sz, 8), S.white, wght=wg)[0])
            gap = max(int(sz * 0.24), 4)
            tw = sum(a.shape[1] for a in parts) + gap * (len(parts) - 1)
            th = max(a.shape[0] for a in parts)
            out_a = np.zeros((th, tw, 4), parts[0].dtype)
            x = 0
            for a in parts:
                out_a[th - a.shape[0]:, x:x + a.shape[1]] = a
                x += a.shape[1] + gap
            return out_a
        core_arr = _bau(core_sz)
        if core_arr.shape[1] > max_w:
            core_arr = _bau(max(int(core_sz * max_w / core_arr.shape[1]), 8))
    else:
        core_arr = S.text(core_txt, core_sz, S.white)[0]      # crisp: kein Glow
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
              'why', 'how', 'that', 'this', 'not', 'but', 'just', 'my', 'your',
              # v187: HILFSVERBEN IN ALLEN FORMEN. Die Liste kannte 'ist' und
              # 'is', aber keine andere Form - 'sind' galt dadurch als
              # Inhaltswort und bekam in der Collage den Gross-Faktor. Die
              # Betonung lag auf der Kopula statt auf der Aussage. Derselbe
              # Fehlertyp, den v159 fuer ANIM_HINTS ueber Stammformen loeste.
              'bin', 'bist', 'sind', 'seid', 'war', 'warst', 'waren', 'wart',
              'sei', 'seien', 'gewesen',
              'hab', 'habe', 'hast', 'hat', 'habt', 'haben', 'hatte',
              'hattest', 'hatten', 'gehabt',
              'werde', 'wirst', 'wird', 'werdet', 'werden', 'wurde',
              'wurdest', 'wurden', 'worden',
              'kann', 'kannst', 'koennen', 'können', 'konnte', 'konnten',
              'muss', 'musst', 'muessen', 'müssen', 'will', 'willst',
              'wollen', 'soll', 'sollst', 'sollen', 'darf', 'duerfen',
              'am', 'are', 'was', 'were', 'be', 'been', 'being',
              'have', 'has', 'had', 'having',
              'will', 'would', 'shall', 'should', 'can', 'could',
              'may', 'might', 'must', 'does', 'did', 'done'}


def _mix01(n):
    """Deterministische 0..1-Streuung aus einer ganzen Zahl.
    Gleiche Eingabe -> gleiche Ausgabe, also reproduzierbar ueber Re-Renders,
    aber ohne sichtbares Muster.
    v153: die alte Fassung nahm nur die unteren 10 Bit einer einzelnen
    Knuth-Multiplikation. Fuer kleine Vielfache lief sie dadurch FAST LINEAR:
    gemessen ergab n*11 fuer 0,3,6,9,12,15 die Folge 0.27, 0.22, 0.18, 0.13,
    0.09, 0.04 - eine fallende Rampe, kein Zufall. Der Seitenwechsel fiel
    deshalb IMMER auf dieselbe Seite. Jetzt der uebliche 32-Bit-Finalizer
    (drei Shift-Multiply-Runden), der die hohen Bits nach unten mischt."""
    x = (int(n) * 2654435761) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 2246822519) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 3266489917) & 0xFFFFFFFF
    x ^= x >> 16
    return (x & 0xFFFF) / 65535.0


def compose_flow(g, words, S, W, H, portrait=False, flow_sel=None, loud=None,
                 colw=None, layout='flow', punch=False, seite='links',
                 maxw=None, groesse=None, texte=None):
    """v97: Flow-Caption nach den Referenz-Videos (@migs.visuals). Der ganze
    Chunk baut sich INLINE auf (Wort fuer Wort, stehend), mit Hierarchie:
      - Verbinder = Support-Font, normal, weiss (Kleinschreibung wie gesprochen)
      - EIN Anker-Wort (laengstes Inhaltswort) = Display-schwer, GROSS, Glow,
        wird per Schreibmaschine enthuellt (letters mitgegeben)
      - optionales Abschlusswort kleingeschrieben = kursive Serif in Akzentfarbe
    Nutzt die LOOK-Fonts + Akzentfarbe (Hybrid: Filler fliesst, Dramatik bleibt).
    Rueckgabe: (items, total_h, anchor_index_or_None). items tragen absolute
    cx/cy relativ zu einem Block-Ursprung y=0 (Aufrufer verschiebt vertikal)."""
    # v193: Nutzer-Text aus dem Block-Editor. Nur der TEXT wird getauscht,
    # die Zeiten bleiben die gemessenen - an ihnen haengen Karaoke, SFX,
    # Beat-Grid und Solo-Riegel.
    if texte:
        words = _SchattenWorte(words, texte)
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
    # v143 GROESSENHIERARCHIE + QUERFORMAT.
    # (a) pf war im Querformat 0.62, also eine VERKLEINERUNG. Im 16:9 ist H
    #     ohnehin die kurze Kante, die H-Bruchteile schrumpfen dadurch schon
    #     von allein. compose_flow war damit der einzige Composer, der den
    #     Effekt verstaerkt statt ausgleicht - alle Nachbarn kompensieren:
    #     compose_phrase 0.16/0.085, behind 0.213/0.11, blurin 0.199/0.10,
    #     ground 0.20/0.10, stack 0.104/0.062 (Faktor 1.68 bis 2.00).
    #     Flow ist Fliesstext, darf also etwas darunter bleiben: 1.50.
    # (b) sz_k von 0.074 auf 0.120. WICHTIG, weil es kontraintuitiv ist:
    #     die Referenz FUELLT die Spalte nicht. Gemessen spannt 'CREATORS'
    #     (8 Zeichen) 0.828 W bei Versalhoehe 0.051 H, "DON'T" (5) nur
    #     0.638 W bei 0.085 H, 'no' (2) sogar nur 0.124 W bei 0.082 H
    #     Versal-Aequivalent. Der Grad ist also NICHT breitengetrieben - es
    #     wird gross angesetzt und nur das LANGE Wort schrumpft in die Zeile.
    #     Genau das macht S.fit von sich aus, es fehlte nur der grosse
    #     Startwert. 0.120 em ergibt bei cap/em 0.707 eine Versalhoehe von
    #     0.085 H = Oberkante des Referenzbands, lange Woerter landen nach
    #     dem Schrumpfen bei rund 0.066 H.
    # (c) v143b: der ganze Block eine Stufe kleiner (Ismets Befund am echten
    #     Streifen). sz_n MUSS mitgehen - schrumpft nur das Schluesselwort,
    #     flacht die Hierarchie wieder auf das ab, was v143 gerade behoben
    #     hat. Beide um denselben Faktor: x-Hoehe 0.030 H bleibt im
    #     Referenzband 0.023-0.033, Verhaeltnis bleibt bei 2.2.
    # (d) v144: GEMESSENE Referenz uebersteuert die Hausgroesse. Die Messung
    #     liefert Versalhoehe und Hierarchie als Anteil der Bildhoehe; genau
    #     diese beiden Zahlen sind es, die man beim Vergleich mit dem Vorbild
    #     als erstes sieht. Uebertragen wird als H-ANTEIL, nicht in Pixeln -
    #     der Formatausgleich pf bleibt davor, sonst schrumpfte der Satz im
    #     Querformat wieder zusammen (v143 gemessen).
    #     Umrechnung Versalhoehe -> Schriftgrad ueber cap/em 0.70 bei der
    #     Display-Schrift, x-Hoehe/em 0.52 bei der Stuetzschrift. Deckel, weil
    #     eine Fehlmessung sonst den ganzen Satz sprengt.
    _ef = S.cfg.get('effects', {}) or {}
    # v151: DER DECKEL SASS ZWEIMAL. _apply_reference_params klemmte den
    # gemessenen Wert bereits auf einen sinnvollen Bereich - hier wurde er
    # ein zweites Mal auf 1.35 gestutzt. Ergebnis: ein Vorbild mit 2.68x
    # Hausmass kam mit 1.35 an, also gerade der halbe Unterschied, und der
    # Kunde sah "es aendert sich kaum was". Hier nur noch die harte
    # Sicherung gegen Unsinn, die Regie entscheidet davor.
    # v154: DER FLIESSTEXT HAT EINEN EIGENEN FAKTOR. Bis v153 skalierte
    # caption_scale nur sz_k, und sz_n wurde daraus ueber die Hierarchie
    # abgeleitet - eine gemessene Referenz zog damit den GANZEN Satz mit.
    # Gemessen wird aber die PUNCHLINE des Vorbilds (96. Perzentil, im
    # zweiten Referenzvideo das riesige Schlusswort); dieser Wert auf den
    # Fliesstext angewandt machte ihn 68 % groesser: 76 -> 128 px.
    # Genau das war Ismets "Schriften zu gross".
    _skal = float(_ef.get('caption_scale') or 1.0)
    _skal = max(0.60, min(2.80, _skal))
    _skn = float(_ef.get('caption_scale_klein') or 0) or None
    _skn = max(0.60, min(1.30, _skn)) if _skn else _skal
    _hier = float(_ef.get('caption_hierarchie') or 0) or None
    # v183 VIRAL-LOOK. Der Markt-Standard 2026 (Submagic/Hormozi-Schule):
    # ALLE Woerter gross, fett, versal, eng gebuendelt - gemessen 0.10-0.15 H
    # Versalhoehe gegen unsere 0.078-0.096 H (Ismets Render) und 0.014 H
    # Fliesstext-Minimum. Der Viral-Modus ist ein MULTIPLIKATOR auf die
    # Hausgroesse, kein Ersatz: eine gelernte Referenz (caption_scale)
    # skaliert weiter relativ dazu, die v151-Kaskade bleibt intakt.
    # v189: Umriss am Schluesselwort/Knall. Standard aus - grosse Woerter
    # brauchen ihn nicht und wirken damit plakativ. Ueber
    # effects.caption_kontur_key wieder zuschaltbar.
    _kontur_key = None if _ef.get('caption_kontur_key') else False
    # v153: eine Stufe kleiner (Ismets Befund am fertigen Video). 0.098 ->
    # 0.088 em ergibt bei cap/em 0.70 eine Versalhoehe von 0.062 H statt
    # 0.069 H. sz_n geht ueber die Hierarchie automatisch mit - wuerde nur
    # das Schluesselwort schrumpfen, flachte der Kontrast wieder ab (der
    # Fehler aus v143b).
    # v154: noch eine Stufe kleiner (Ismets dritter Befund, "immer noch zu
    # gross"). 0.088 -> 0.076 em ergibt bei cap/em 0.70 eine Versalhoehe von
    # 0.053 H. Der Fliesstext geht mit (0.040 -> 0.034 em, x-Hoehe 0.018 H).
    pf = 1.35 if not portrait else 1.0
    # v184 REFERENZ-GROESSEN. An Ismets drei High-End-Vorbildern gemessen
    # (measure_reference_video): Schluesselwort-Band 0.074 H (B) bis 0.184 H
    # (C-Punchline), Fliesstext-Band 0.040 H in BEIDEN - unsere 0.034 em
    # (x-Hoehe 0.018 H) waren die Haelfte davon. Neu: key 0.105 em (Versal
    # ~0.074 H), Fliesstext 0.050 em (Band ~0.040 H). Der Punch-Faktor 2.25
    # ergibt 0.236 em = Versal ~0.165 H und trifft die C-Punchline (0.184
    # Band inkl. Saum). Die v154-Verkleinerungen galten der ALTEN Anordnung;
    # massgeblich sind jetzt die gemessenen Referenzen.
    # v192: eine Stufe kleiner auf Ismets Ansage ("mach es ruhig etwas
    # kleiner"). Faktor 0.85 auf die v184-Referenzmasse: Schluesselwort
    # 0.105 -> 0.089 em (Versalhoehe 0.062 H), Fliesstext 0.050 -> 0.043 em.
    # Damit liegt das Schluesselwort knapp UNTER dem gemessenen Referenzband
    # (0.074 bis 0.165 H) - bewusste Nutzer-Entscheidung, kein Messfehler.
    sz_k = int(H * 0.089 * pf * _skal)
    if _hier and not _ef.get('caption_scale_klein'):
        _hier = max(1.4, min(5.0, _hier))
        sz_n = int(sz_k * 0.70 / (0.52 * _hier))
    else:
        sz_n = int(H * 0.043 * pf * _skn)
    # v193 GROESSE PRO BLOCK. Bis v192 gab es nur die globalen Regler
    # caption_scale / caption_scale_klein - ein einzelner Block liess sich
    # gar nicht groesser machen. Der Faktor sitzt bewusst NACH allen anderen
    # Faktoren und ist auf 0.5 bis 2.0 geklemmt (in _block_norm), damit die
    # Nutzerwahl relativ zum Look bleibt und die v151-Kaskade intakt haelt.
    # WICHTIG: das ist NICHT 'power'. Power ist die dramaturgische Wucht
    # (Kamera, SFX, Tempo-Kurve); Groesse ist der Schriftgrad. Beides in
    # einen Regler zu legen war der v155/v156-Fehler.
    if groesse:
        _gf = max(0.5, min(2.0, float(groesse)))
        sz_k = max(8, int(sz_k * _gf))
        sz_n = max(6, int(sz_n * _gf))
    # v230c5 HIER KEIN ZWEITER DECKEL. Naheliegend waere gewesen, die Hoehe
    # des Ankerworts hier zu begrenzen - Ismets Befund war ja "viel zu gross".
    # Genau das verbietet v151: der Deckel gehoert an EINE Stelle
    # (_apply_reference_params), sonst kommt eine gelernte Referenz nur noch
    # zur Haelfte an ("Referenz hochgeladen, es aendert sich kaum was").
    # Ausprobiert und am Test belegt: mit einem Deckel von 0.105 H schrumpfte
    # die Wirkung der Referenz von 1.4x auf 1.02x, der v151-Test fiel sofort.
    # Die Groesse wird deshalb dort korrigiert, wo sie ENTSTEHT: die Messung
    # nimmt seit v230c5 die typische Schluesselwort-Groesse des Vorbilds
    # statt seiner groessten Stelle (_gross_klasse).
    sz_a = int(sz_n * 1.244)
    # Satzspiegel: hoch wie bisher die fast volle Breite, quer eine Spalte -
    # eine Zeile ueber 1920 px waere kein Satz mehr, sondern eine Laufschrift.
    # v143: die Spaltenbreite ist verhandelbar. Fuellt eine Person das Bild,
    # bekommt der Block eine schmale Spalte und passt NEBEN den Kopf, statt
    # unter ihn ausweichen zu muessen - genau das macht die Referenz in ihren
    # Nahaufnahmen. Untergrenze 0.34 W, darunter wird der Satz zum Wortsalat.
    _colw = int(W * (0.86 if portrait else 0.55))
    # v187: maxw ist der PLATTFORM-KORRIDOR (Button-Spalte, Title-Safe, Zoom).
    # Er deckelt immer, ist aber KEINE Motiv-Verengung: 'colw' bleibt die
    # Nahaufnahme-Sperre, an der Randabfall und Punch-Deckel haengen.
    if maxw:
        _colw = int(max(W * 0.34, min(_colw, float(maxw))))
    if colw:
        _colw = int(max(W * 0.34, min(_colw, float(colw))))
    # Tracking relativ zum Grad statt absolut: 6 px waren bei 96 px Hochformat
    # 6.25 % em, dieselben 6 px bei geschrumpfter Querformat-Schrift ueber 25 %
    # em - der Satz fiel dort in Einzelbuchstaben auseinander.
    # v187: die Laufweite skaliert in BEIDEN Orientierungen mit dem Grad.
    # Fest 6 px im Hochformat waren bei 1080 W zwar 2.3 % em (richtig), bei
    # kleiner Bildbreite aber 22 % em - dort fiel der Wortabstand auf das
    # Niveau des Buchstabenabstands und Woerter verschmolzen. Bei 1080x1920
    # ergibt die Formel exakt dieselben 6 px, der Kundenpfad bleibt gleich.
    _trk_n = max(2, int(sz_n * 0.0625))
    # v144: Glow kann aus der gemessenen Referenz kommen (Standard: an).
    _glow_k = bool((S.cfg.get('effects', {}) or {}).get('caption_glow', True))
    # v150 COLLAGE-VORAUSWAHL. Zwei Entscheidungen fallen VOR dem Setzen,
    # weil sie die Groessen bestimmen:
    # (1) Wie viele Woerter duerfen gross stehen. Im Vorbild sind es drei
    #     ('have been asking') neben zwei kleinen. Duerften alle
    #     Inhaltswoerter gross, waere der Block bei zehn Woertern 0.44 H
    #     hoch - er passt dann neben keinem Kopf mehr vorbei, und die
    #     Platzierungs-Regie muesste ihn in den Bildrand druecken.
    # (2) Welche Woerter in die Schreibschrift gehen. Das Vorbild setzt eine
    #     zusammenhaengende Verbinder-Kette ('how do I do') kursiv - ein
    #     zweiter Schriftschnitt im selben Satz, und genau der macht den
    #     Unterschied zwischen 'Untertitel' und 'gesetzt'.
    _gross_ok, _skript_grp = set(), set()
    if layout == 'collage':
        _kand = [i for i in cont if i != accent and i != anchor]
        _kand.sort(key=lambda i: -len(clean(words[i]['word'])))
        _gross_ok = set(_kand[:4])
        _kette, _best = [], []
        for i in idxs:
            if i in cont or i == anchor:
                if len(_kette) > len(_best):
                    _best = _kette
                _kette = []
            else:
                _kette.append(i)
        if len(_kette) > len(_best):
            _best = _kette
        if len(_best) >= 2:
            _skript_grp = set(_best[:4])
    items = []
    for i in idxs:
        raw = clean(words[i]['word'])
        if i == anchor:
            up = raw.upper()
            # v143: gross ansetzen, nur lange Woerter schrumpfen lassen -
            # die Zeilenbreite der Referenz (0.83 W) ist das Ergebnis, nicht
            # das Ziel. Deckel 0.83 W hoch / Spaltenbreite quer.
            # Die Referenz-Deckelung 0.83 W gilt nur, solange die Spalte
            # voll ist. Wurde sie wegen eines Motivs verengt, gewinnt die
            # Spalte - sonst spraengte das Schluesselwort den Block wieder
            # auf volle Breite und die Verengung waere wirkungslos.
            # v150 (C) SCHLUSSWORT-KNALL. Im Vorbild ist die Punchline
            # gemessen 0.18 H hoch, das Groessenverhaeltnis zum Fliesstext
            # 4.59 - bei uns lag es bei 2.2 bis 2.9. Ein Satzende darf
            # deshalb deutlich groesser ansetzen; die Spaltenbreite deckelt
            # es weiterhin, ein langes Wort schrumpft also von selbst
            # zurueck. Nur am SATZENDE, sonst waere jedes Video wieder
            # gleichfoermig - nur eben laut.
            # v153: Punch-Faktor von 1.60 auf 1.95. Die Grundschrift ist eine
            # Stufe kleiner geworden (0.098 -> 0.088 em); mit dem alten Faktor
            # erreichte das Schlusswort die Bildbreite nicht mehr und der
            # Randabfall lief ins Leere (gemessen 0.96 W statt 1.07 W).
            # v154: 2.25. Die Grundschrift ist erneut kleiner geworden
            # (0.088 -> 0.076 em); mit 1.95 rutschte der Knall auf 1.01 W und
            # der Abstand zum normalen Schluesselwort schrumpfte auf 1.14x -
            # der Effekt waere kaum noch zu sehen gewesen.
            _kf = 2.25 if punch else 1.0
            # Beim Knall darf die Zeile ueber den normalen Satzspiegel
            # hinaus - im Vorbild laeuft das Schlusswort ueber die volle
            # Breite. 0.89 W und nicht mehr: der Block SETZT bei x0 = 0.07 W
            # an, mit 0.96 ragte die rechte Kante gemessen bis 1.033 W.
            # Breite. ABER nur, wenn der Aufrufer die Spalte nicht wegen
            # eines Motivs verengt hat: die Verengung ist eine Sperre, kein
            # Vorschlag. Ohne diese Unterscheidung deckelte der normale
            # Satzspiegel den Knall auf 156 statt 162 px weg - der Effekt
            # waere unsichtbar geblieben.
            # v152 RANDABFALL. Das Vorbild laesst sein Schlusswort links und
            # rechts aus dem Bild laufen - nur deshalb kann es 0.18 H hoch
            # stehen. Bei fuenf Zeichen braeuchte diese Versalhoehe rund
            # 1480 px Breite, das Bild hat 1080; ohne Anschnitt schrumpft
            # S.fit es zwangslaeufig auf die Spalte. Der Anschnitt gilt NUR
            # am Satzende und nur, wenn die Spalte nicht wegen eines Motivs
            # verengt wurde. Erste und letzte Glyphe duerfen angeschnitten
            # werden, das Wort bleibt lesbar.
            # NUR KURZE WOERTER. Am gerenderten Streifen gemessen: bei
            # 'GEHOERT' (7 Zeichen) frisst der Anschnitt links das G und
            # rechts das T - das Wort ist dann nicht mehr zu lesen. Das
            # Vorbild schneidet 'this' an, also vier Zeichen; dort verliert
            # man nur Teile der Randglyphen. Ab sechs Zeichen bleibt es beim
            # Satzspiegel.
            # v187: bei aktiver Plattform-Maske ist der Randabfall AUS. Er
            # laesst das Wort bewusst am Bildrand anschneiden - genau dort
            # sitzen bei TikTok/Reels die Buttons. Ein Stilmittel fuer
            # Material ohne UI-Overlay, keine Regel fuer jedes Format.
            _maske = bool(maxw and maxw < W * 0.80)
            _bleed = bool(punch and not colw and not _maske and len(up) <= 5
                          and (S.cfg.get('effects', {}) or {}).get(
                              'caption_bleed', True))
            # v183 ZOOM-SICHERER DECKEL. 0.89 W galt fuer ein ruhendes Bild -
            # der Crash-Zoom sitzt aber GENAU auf solchen Punch-Momenten und
            # schiebt die Kante ueber den Rand (MOMENTE-Anschnitt, am Render
            # belegt: Kante bei 0.999 W trotz zentrierter Zeile). Der Deckel
            # zieht deshalb den konfigurierten Zoom ab: crash 0 -> 0.89 W
            # (Alt-Verhalten), crash 1.0 -> 0.78 W. Der gewollte Randabfall
            # (_bleed) bleibt bei 1.14 W - dort IST der Anschnitt das Bild.
            _crash = float((S.cfg.get('camera', {}) or {}).get('crash') or 0)
            _pd = 0.89 - 0.11 * max(0.0, min(1.0, _crash))
            # v187: der Knall-Deckel kennt den Plattform-Korridor. Bis
            # dahin galt bei punch immer 0.89 W, egal welche Maske aktiv war -
            # gemessen lief der Block dadurch bis 0.954 W, also unter die
            # Button-Spalte (rail 0.840 W). Ohne Maske bleibt alles wie v183.
            _deckel = ((_colw if _maske else int(W * (1.14 if _bleed else _pd)))
                       if not colw else _colw) if punch else (
                min(int(W * 0.83), _colw) if portrait else _colw)
            sz = S.fit(up, int(sz_k * _kf), _deckel, font=S.f_sans_b, tracking=2)
            # v187 DER KNALL WAR NUR UEBER DIE BREITE GEDECKELT. Nachgerechnet:
            # im Hochformat band der Breiten-Deckel IMMER und frass den Faktor
            # 2.25 komplett auf - das Schlusswort wurde kleiner als ein
            # normales Schluesselwort (punch/key 0.86 bis 1.02). Im Querformat
            # band er nie und das Wort lief auf 0.22 bis 0.28 H, also weit
            # ueber die Referenz-Obergrenze 0.165 H.
            # Zwei Gegenmassnahmen, je Format eine:
            #  quer: harter HOEHEN-Deckel auf die Referenz-Obergrenze.
            #  hoch: statt weiter zu schrumpfen darf der Knall anschneiden -
            #        genau dafuer ist der Randabfall da (v152). Die Grenze
            #        von 5 auf 8 Zeichen: laenger wird unlesbar.
            if punch:
                _hmax = int(H * 0.165 / 0.70)
                if sz > _hmax:
                    sz = _hmax
                # EHRLICHE GRENZE, NICHT GEFIXT: im Hochformat erreicht ein
                # langes Schlusswort den Faktor 2.25 nicht - bei 1080 W
                # braeuchte ein 8-Zeichen-Wort ueber 1500 px. Erzwingen
                # liesse es sich nur mit Anschnitt (v152 verbietet ihn ab
                # 6 Zeichen, weil die Randglyphen wegfallen) oder mit einem
                # Zeilenumbruch des Knalls. Beides waere schlechter als ein
                # etwas kleineres Wort. Kurze Schlussworte bekommen ihren
                # vollen Knall, lange nicht - das ist Physik, kein Bug.
            # v189: das grosse Wort ohne Umriss (Ismets Ansage). Der Glow
            # und die Flaeche tragen dort den Kontrast; der Saum liess es
            # plakativ wirken. Der Fliesstext behaelt ihn.
            arr, tw, lets = S.text(up, sz, S.white, font=S.f_sans_b,
                                   glow=_glow_k, per_letter=True, tracking=2,
                                   kontur=_kontur_key)
            items.append({'i': i, 'arr': arr, 'w': tw,
                          'role': 'punch' if punch else 'key', 'sz': sz,
                          'bleed': bool(_bleed and tw > W * 0.90),
                          'letters': lets, 't': words[i]['start']})
        elif i == accent:
            cap = raw.lower().capitalize()
            sz = S.fit(cap, sz_a, int(W * 0.5) if portrait else int(_colw * 0.58),
                       font=S.f_script)
            arr, tw = S.text(cap, sz, S.accent, font=S.f_script)   # Kursive gibt
            items.append({'i': i, 'arr': arr, 'w': tw, 'role': 'accent',  # den Slant
                          't': words[i]['start']})
        else:
            # v101 Betonungs-Typografie: laute Woerter schwerer+groesser,
            # leise leichter+kleiner (Variable-Font-Achse; ohne var-Schnitt
            # greift nur die Groesse - immer noch stimmig).
            _m = (loud or {}).get(i)
            _sz = int(sz_n * (1.12 if _m == '!' else (0.92 if _m == '~' else 1.0)))
            # v151: Grundgewicht kann aus der gemessenen Referenz kommen
            # (Stammbreite je Versalhoehe). Betonung bleibt relativ dazu.
            _wb = int((S.cfg.get('effects', {}) or {}).get('caption_weight') or 0)
            if _wb:
                _wg = max(200, min(900, _wb + (140 if _m == '!' else
                                               (-140 if _m == '~' else 0))))
            else:
                _wg = 800 if _m == '!' else (460 if _m == '~' else None)
            # v150 (B) VARIATION: in der Collage sind die Fuellwoerter NICHT
            # alle gleich gross. Im Vorbild traegt jedes Wort seine eigene
            # Groesse - genau das nimmt dem Video die Gleichfoermigkeit.
            # Inhaltswoerter stehen gross und rechts versetzt, echte
            # Verbinder klein links. Die Stufe kommt deterministisch aus dem
            # Wort-Index, damit ein Re-Render dasselbe Bild ergibt.
            _gross = False
            if layout == 'collage' and i in _skript_grp:
                # Schreibschrift-Kette: klein, in Akzentfarbe, leicht schraeg.
                _sz = int(sz_n * 1.15)
                arr, tw = S.text(raw.lower(), _sz, S.accent, font=S.f_script)
                items.append({'i': i, 'arr': rot_img(arr, -6), 'w': tw,
                              'role': 'norm', 'gross': False, 'skript': True,
                              'sz': _sz, 't': words[i]['start']})
                continue
            if layout == 'collage':
                _gross = i in _gross_ok
                if _gross:
                    _sz = int(_sz * (1.75 + 0.35 * _mix01(i)))
                else:
                    _sz = int(_sz * (0.92 + 0.16 * _mix01(i * 7)))
            _trk_v = _trk_n
            # v185 EIN WORT DARF NIE BREITER ALS DIE SPALTE SEIN. Bis v184
            # bekam nur das Schluesselwort ein S.fit; normale Woerter wurden
            # in der Sollgroesse gesetzt und ragten bei langen Woertern aus
            # dem Bild (am Testrender gemessen: 'Momente' von 0.12 bis
            # 1.14 W). Genau das meint die Referenz mit "gross ansetzen, nur
            # das LANGE Wort schrumpft in die Zeile".
            _sz = S.fit(raw, _sz, _colw, font=S.f_sans, tracking=_trk_v)
            arr, tw = S.text(raw, _sz, S.white, tracking=_trk_v,
                             font=S.f_sans, wght=_wg)
            items.append({'i': i, 'arr': arr, 'w': tw, 'role': 'norm',
                          'gross': _gross, 'sz': _sz,
                          't': words[i]['start']})
    # Inline-Fluss mit Umbruch, Zeilen unten ausgerichtet (gemeinsame Grundlinie)
    max_w = _colw
    x0 = int(W * 0.07)
    # v185 WORTABSTAND HAENGT AM GRAD, nicht nur an der Bildbreite. Fest
    # 0.032 W waren bei Hausgroesse in Ordnung; mit den Referenz-Groessen
    # (v184) und erst recht im Viral-Look (doppelter Fliesstext) sank der
    # Abstand auf unter 0.17 em und die Woerter klebten aneinander
    # ("SINDDIE", "AUFEIN" - am Testrender gemessen). Satztechnisches Mass
    # fuer eine Wortluecke ist rund ein Drittel Geviert.
    space = int(max(W * (0.032 if portrait else 0.020), sz_n * 0.30))
    # STRUKTUR wie in der Referenz: klare Zeilen nach ROLLE statt wildem
    # Breiten-Umbruch. Verbinder-vor-Keyword = Zeile 1, das KEYWORD = eigene
    # Zeile, Rest (inkl. Kursiv-Akzent) = Zeile darunter. Alles LINKS buendig,
    # konstante Zeilenhoehe nach dem groessten Font der Zeile. Vorschub nach
    # echter Textbreite; zentriert wird das symmetrisch gepolsterte Sprite.
    for it in items:
        it['adv'] = it['w']
    def _umbruch(seq):
        """Bricht eine Wortfolge am Satzspiegel um. v185: das galt bisher NUR
        fuer den Fall ohne Schluesselwort. Mit Anker liefen Vor- und Nachlauf
        als EINE Zeile durch, egal wie breit - am Testrender gemessen stand
        'Level' bei 1.15 W und 'deines' bei 1.57 W, also weit ausserhalb des
        Bildes. Mit den Referenz-Groessen (v184) und im Viral-Look passiert
        das bei jedem dritten Chunk."""
        out, cur, cur_w = [], [], 0
        for it in seq:
            aw = it['adv']
            if cur and cur_w + space + aw > max_w:
                out.append(cur)
                cur, cur_w = [], 0
            cur.append(it)
            cur_w += (space if len(cur) > 1 else 0) + aw
        if cur:
            out.append(cur)
        return out

    rows = []
    if anchor is not None:
        pos = idxs.index(anchor)
        rows += _umbruch(items[:pos])
        rows.append([items[pos]])
        rows += _umbruch(items[pos + 1:])
    else:
        rows = _umbruch(items)

    def _rsz(it):
        # v187: gerechnet wird mit der WIRKLICH gesetzten Groesse, auch im
        # Zeilensatz. Vorher galt dort die Sollgroesse - beim Knall klafften
        # beide um den Faktor 2.25 auseinander (Soll 153 px, gesetzt 344 px),
        # die Zeilenhoehe blieb bei 184 px und die Glyphe ragte je 80 px in
        # die Nachbarzeilen. Das war echte Tinte auf Tinte, kein Ausklingen:
        # 'ein neues Level' fiel im Render von 603 auf 16 Textpixel, sobald
        # das Schlusswort stand.
        if it.get('sz'):
            return it['sz']
        return sz_k if it['role'] in ('key', 'punch') else (
            sz_a if it['role'] == 'accent' else sz_n)

    if layout == 'collage':
        # v184 CLUSTER-LESEPFAD (an Ismets drei High-End-Referenzen gelesen,
        # ersetzt die v150-Spalten-Anordnung). Die Vorbilder setzen den Satz
        # als EINEN Pfad: jedes Wort schliesst raeumlich an das vorige an,
        # kurze Zeilen (1-3 Woerter) mit eigenem Treppen-Einzug, enger
        # Zeilenfall, gemeinsame Grundlinie je Zeile, jedes Wort in eigener
        # Groesse, Verbinder-Ketten in Schreibschrift INLINE im Pfad, das
        # Schluesselwort IM Pfad (mit hoechstens einem kleinen Wort davor,
        # wie 'add CREATORS' im Vorbild), die Punchline am Ende.
        # Die v150-Anordnung stellte Verbinder in eine EIGENE Spalte neben
        # die Treppe - Lesereihenfolge und Raumfolge fielen auseinander
        # ('that/to/one'-Saeule neben STICKS, Ismets Befund: "keine high
        # level Typografie"). Raumfolge = Lesereihenfolge ist die Regel,
        # an der dieser Block haengt. Wer hier umbaut, muss sie halten.
        _re = (seite == 'rechts')
        _sp = max(2, int(space * 0.60))        # Vorbilder setzen eng
        _cap = max_w * 0.62
        _zeilen, _cur, _cw = [], [], 0.0
        for it in items:
            aw = it['adv']
            _breit = it['role'] in ('key', 'punch')
            _passt = (not _cur) or (_cw + _sp + aw <= _cap and len(_cur) < 3)
            if not _passt or (_breit and len(_cur) > 1):
                _zeilen.append(_cur)
                _cur, _cw = [], 0.0
            _cur.append(it)
            _cw += (_sp if len(_cur) > 1 else 0) + aw
            if _breit:
                _zeilen.append(_cur)
                _cur, _cw = [], 0.0
        if _cur:
            _zeilen.append(_cur)
        y = 0.0
        for _ln, _row in enumerate(_zeilen):
            _rh = max(int(_rsz(it) * 1.06) for it in _row)   # enger Fall
            _rw = sum(it['adv'] for it in _row) + _sp * (len(_row) - 1)
            # Treppen-Einzug: deterministisch je Zeile, nie zufaellig.
            _ind = max_w * (0.03 + 0.16 * _mix01(idxs[0] * 17 + _ln * 5))
            _ind = max(0.0, min(_ind, max_w - _rw))
            if _rw >= max_w:
                x = max(W * 0.035, x0 + (max_w - _rw) / 2.0)
            elif _re:
                x = x0 + max_w - _ind - _rw
            else:
                x = x0 + _ind
            for it in _row:
                it['cx'] = x + it['adv'] / 2.0
                # gemeinsame GRUNDLINIE statt Zeilenmitte: grosse und kleine
                # Woerter einer Zeile stehen auf demselben Fuss (Vorbild
                # 'add CREATORS'), sonst schwimmt die Zeile.
                it['cy'] = y + _rh - _rsz(it) * 0.53
                x += it['adv'] + _sp
            y += _rh
        total_h = max(int(y), 1)
        return items, total_h, anchor

    y = 0
    for row in rows:
        line_h = int(max(_rsz(it) for it in row) * 1.20)
        # v153: Zeilen koennen an der RECHTEN Kante ausgerichtet werden.
        # Der Satzspiegel bleibt derselbe, nur die buendige Kante wechselt.
        _rw = sum(it['adv'] for it in row) + space * (len(row) - 1)
        # v183 SYMMETRIE. Zwei Faelle zentrieren die Zeile im Satzspiegel:
        # (a) seite 'mitte' - zentrierte Zeilen sind die Konvention fuer
        #     mittigen Sprechtext (Netflix TTSG); linksbuendige Zeilen in
        #     einem mittig gesetzten Block sahen nach Fehler aus.
        # (b) die Zeile ist BREITER als der Satzspiegel (Punch-Deckel 0.89 W
        #     gegen 0.86/0.55 W Spiegel): buendig bei x0 lag die rechte
        #     Kante bei 0.96 W, und der Crash-Zoom - der genau auf solchen
        #     Momenten sitzt - schob sie aus dem Bild (MOMENTE-Anschnitt,
        #     am Testrender belegt). Symmetrische Raender halten auch da.
        if seite == 'mitte' or _rw > max_w:
            x = max(W * 0.035, x0 + (max_w - _rw) / 2.0)
        elif seite == 'rechts':
            x = x0 + max_w - _rw
        else:
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


def ai_flow_direct(words, groups, language='de', model='gpt-5'):
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
    # v210: 'requests' wird in dieser Datei in JEDER Funktion lokal
    # importiert - hier fehlte der Import. Die KI-Textaufteilung ist deshalb
    # bei JEDEM Kunden-Render mit einem NameError gestorben und still auf die
    # Heuristik zurueckgefallen (in Ismets Job-Log belegt). Ein Fallback, der
    # jeden Fehler schluckt, macht aus einem Programmierfehler ein Feature,
    # das niemand vermisst - deshalb prueft der Selftest jetzt, dass die
    # Funktion ohne echten Schluessel NICHT mit NameError endet.
    import requests
    try:
        # v230p: das Budget waechst mit der Zahl der Bloecke. 120 + 30 je
        # Block ergab bei 14 Bloecken 540 Tokens - nach der Untergrenze 2500,
        # und davon ging bei einem Denk-Modell alles ins Nachdenken. Die
        # Antwort kam leer (Ismets Job-Log: "AI flow unavailable").
        _txt = _oai_text(key, _oai_json(
            model, [{'role': 'system', 'content': sysm},
                    {'role': 'user', 'content': '\n'.join(lines)}],
            max_toks=min(600 + 90 * len(groups), 12000),
            temperature=0.0, frage='fluss'), timeout=180)
        data = json.loads(_txt)
    except Exception as e:
        print(f"AI flow unavailable ({type(e).__name__}), falling back to the heuristic.")
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


# v159: deutsche Verbendungen. Die Vokabelliste ANIM_HINTS ist in der
# 3. Person Singular geschrieben ('scheitert', 'zittert'). Ein Transkript
# sagt aber genauso oft 'scheitern', 'zitterten', 'zittere'. Gemessen im
# Audit: 39 von 52 geprueften Verbpaaren verloren ihre Animation, sobald
# die -en-Form kam. Beide Seiten werden deshalb auf den Stamm gekuerzt.
_VERB_END = ('endsten', 'endste', 'enden', 'ende', 'etest', 'etet', 'eten',
             'ete', 'test', 'tet', 'ten', 'est', 'end', 'en', 'et', 'st',
             'te', 'e', 't', 'n')


def _anim_stamm(w):
    """Wortstamm fuer den Vergleich: eine deutsche Verbendung abschneiden,
    aber nur solange mindestens vier Zeichen stehen bleiben. Kuerzere Staemme
    kollidieren ('fall' und 'falle' waeren noch tragbar, 'fa' nicht mehr)."""
    for e in _VERB_END:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[:-len(e)]
    return w


def _anim_hit(text, key):
    """Wortgenauer Treffer statt blinder Teilstring-Suche.
    'fällt' darf NICHT in 'gefällt' anschlagen ('das gefaellt mir' ist kein Sturz).
    Darum muss der Wortanfang passen. Nur richtig lange Stichwoerter (>=7 Zeichen)
    duerfen auch mitten in Komposita stecken ('Staatsschulden' -> schulden);
    bei kurzen waere genau das die Falle.
    v159: zusaetzlich Stamm-Vergleich, damit Plural und Infinitiv treffen.
    Das reine startswith bleibt fuer Stichwoerter ab 6 Zeichen erhalten -
    bei kuerzeren war es die Quelle von Fehlalarmen: 'fall' schlug in 'FALLS'
    an und liess den Block samt Sturz-Sound kippen, obwohl im Satz nichts
    faellt (im Audit gemessen)."""
    ks = _anim_stamm(key)
    for tok in re.split(r"[^0-9A-Za-zÄÖÜäöüß]+", text.lower()):
        if not tok:
            continue
        if len(key) >= 7 and key in tok:
            return True
        if len(key) >= 6 and tok.startswith(key):
            return True
        if tok == key or _anim_stamm(tok) == ks:
            return True
    return False


def anim_ctx(words, i, n=1):
    """v99a: Kontextfenster fuer die Auto-Animation, an SATZGRENZEN gekappt.
    Vorher lief das Fenster i-4..i+8 ueber den Punkt hinaus - ein 'explode'
    aus dem NAECHSTEN Satz faerbte die Animation dieses Moments (gemessen:
    'ON THE GROUND' explodierte, weil der Folgesatz von Explosionen sprach)."""
    a0, b0 = max(i - 4, 0), min(i + max(n, 1) + 5, len(words))
    for j in range(i, b0):
        if str(words[j].get('word', '')).rstrip().endswith(('.', '!', '?')):
            b0 = j + 1
            break
    for j in range(i - 1, a0 - 1, -1):
        if str(words[j].get('word', '')).rstrip().endswith(('.', '!', '?')):
            a0 = j + 1
            break
    return ' '.join(clean(words[j].get('word', '')) for j in range(a0, b0))


# v159: NEGATION. "Die Mieten steigen NICHT" bekam dieselbe
# Aufwaerts-Animation wie "Die Mieten steigen" - samt Aufwaerts-Sound. Das
# Video sagt dann das Gegenteil des Satzes. Steht eine Verneinung im
# Umfeld des Treffers, wird die Animation verworfen: lieber keine als eine
# falsche.
_NEGATION = {'nicht', 'nie', 'niemals', 'kein', 'keine', 'keinen', 'keiner',
             'keines', 'keinem', 'nichts', 'ohne', 'weder', 'kaum',
             'no', 'not', "n't", 'never', 'none', 'without', 'neither',
             'hardly', 'barely'}


def _hat_negation(text):
    """Verneint der Satz? Reine Wortliste, deutsch und englisch."""
    for tok in re.split(r"[^0-9A-Za-zÄÖÜäöüß\']+", (text or '').lower()):
        if tok in _NEGATION:
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
        # v159: in einem verneinten Satz ist die Handlung nicht passiert.
        # Eine Animation, die sie trotzdem ausfuehrt, widerspricht dem
        # Gesagten - und ihr Sound tut es hoerbar.
        if _hat_negation(src):
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
    unberuehrt. Rueckgabe: Anzahl vorgezogener Momente.

    v141 (Ismets Doppelbild-Screenshot): verglichen wird jetzt 'vpos' - die
    Stelle, an der der Text WIRKLICH steht. 'target' ist bei der Flow-Caption
    das KAMERA-Ziel (x = W*0.07, linker Rand), nicht der Textblock (Mitte).
    Damit lag der horizontale Abstand zu einem Keyword-Moment bei 0.43*W und
    riss die 0.42*W-Schranke - der Schutz griff bei Flow-Captions nie, obwohl
    beide Texte uebereinander standen. Plaene ohne 'vpos' nutzen 'target'."""
    def _vp(p):
        return p.get('vpos') or p['target']

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
            if (abs(_vp(a)[1] - _vp(b)[1]) < H * 0.16
                    and abs(_vp(a)[0] - _vp(b)[0]) < W * 0.42):
                new_end = min(new_end, max(a_t0 + 0.3, b_t0 - 0.12))
        if new_end < a_end0 - 1e-3:
            a['end'] = new_end
            n += 1
    return n


def ink_box(p, W, H):
    """v216: die TINTE eines Textmoments in Bildkoordinaten - egal in welcher
    Form er vorliegt. Es gibt drei, und jede Pruefung, die nur eine davon
    kennt, ist blind fuer die anderen (derselbe Fehlertyp wie v187 beim
    Safe-Zone-Report):
      * Karte          -> 'arr' (der Look 'outline' legt sein Bild in 'o_arr')
      * Komposition    -> 'tokens' (jedes Wort mit eigenem Versatz 'ox'/'oy')
      * Fliesstext     -> 'front' (Items mit eigenen absoluten Koordinaten)
      * Stuetzzeile    -> 'small' (v230n, ebenfalls absolute Koordinaten)
    Gemessen wird der deckende Glyphenkoerper, NICHT das Sprite-Rechteck: ein
    Text-Sprite traegt bis zu 180 px durchsichtigen Rand (Glow-Polster). Mit
    dem Rechteck gerechnet meldet jede Pruefung Verstoesse, wo im Bild nichts
    steht. Rueckgabe: (x0, x1, y0, y1) oder None."""
    def _nz(a):
        if a is None or a.size == 0:
            return None
        m = np.where(a[..., 3] > 80)
        return None if not len(m[0]) else (float(m[1].min()), float(m[1].max()),
                                           float(m[0].min()), float(m[0].max()))
    xs, ys = [], []
    _a = p.get('arr')
    if _a is None:
        _a = p.get('o_arr')
    if _a is not None:
        _m = _nz(_a)
        if _m:
            _cx = float(p.get('cx', W / 2.0))
            _cy = float(p.get('cy', p.get('by', H * 0.398)))
            xs += [_cx - _a.shape[1] / 2.0 + _m[0], _cx - _a.shape[1] / 2.0 + _m[1]]
            ys += [_cy - _a.shape[0] / 2.0 + _m[2], _cy - _a.shape[0] / 2.0 + _m[3]]
    for _t in (p.get('tokens') or []):
        _m = _nz(_t.get('arr'))
        if not _m:
            continue
        _tx = W / 2.0 + float(_t.get('ox', 0.0))
        _ty = float(p.get('by', H * 0.398)) + float(_t.get('oy', 0.0))
        xs += [_tx - _t['arr'].shape[1] / 2.0 + _m[0],
               _tx - _t['arr'].shape[1] / 2.0 + _m[1]]
        ys += [_ty - _t['arr'].shape[0] / 2.0 + _m[2],
               _ty - _t['arr'].shape[0] / 2.0 + _m[3]]
    # v230n DIE STUETZZEILE WAR HIER NICHT DABEI - und lief deshalb aus dem
    # Bild ('THIS ONE STICKS' begann bei -0.03 W, das T fehlte). Genau der
    # Fehler, vor dem der Docstring oben warnt: eine Pruefung, die nur eine
    # der Formen kennt, ist blind fuer die anderen.
    for _it in (p.get('small') or []) + (p.get('front') or []):
        if _it.get('cx') is None or _it.get('_bleed_aus'):
            continue                       # v152: gewollter Randabfall
        _m = _nz(_it.get('arr'))
        if not _m:
            _h = float(_it.get('adv', _it.get('w', 0))) / 2.0
            xs += [_it['cx'] - _h, _it['cx'] + _h]
            continue
        xs += [_it['cx'] - _it['arr'].shape[1] / 2.0 + _m[0],
               _it['cx'] - _it['arr'].shape[1] / 2.0 + _m[1]]
        ys += [_it['cy'] - _it['arr'].shape[0] / 2.0 + _m[2],
               _it['cy'] - _it['arr'].shape[0] / 2.0 + _m[3]]
    if not xs:
        return None
    return (min(xs), max(xs), min(ys) if ys else 0.0, max(ys) if ys else 0.0)


def _skaliere_sprite(a, s):
    """Sprite um Faktor s verkleinern, Seitenverhaeltnis bleibt."""
    h, w = a.shape[:2]
    nh, nw = max(int(round(h * s)), 2), max(int(round(w * s)), 2)
    return cv2.resize(a, (nw, nh), interpolation=cv2.INTER_AREA)


# v230h: so weit darf das Schlusswort (v152 'bleed') hoechstens hinauslaufen -
# und nur auf EINER Seite. Mehr ist kein Stilmittel mehr, sondern ein Fehler.
_BLEED_MAX_REL = 0.10


def fit_into_frame(plans, W, H, rand=0.012):
    """v216 KEIN TEXT WIRD VOM BILDRAND ANGESCHNITTEN.

    Ismets Render (15 s, 720x1280): 'CAPTIONS LOOK THE' lief links UND rechts
    aus dem Bild - vorne fehlte das C, hinten das E. 'THIS ONE FLOATS' klebte
    mit beiden Aussenkanten am Bildrand, 'BEHIND ME' und 'ON THE WALL' waren
    links angeschnitten. Ein halb abgeschnittenes Wort ist nicht Stil, es ist
    unlesbar - und es ist der deutlichste Amateur-Tell im ganzen Bild.

    Die Breite entsteht auf mehreren Wegen (Karte, Editorial-Komposition,
    Fliesstext, Referenz-Skalierung, Perspektiv-Verzerrung, Betonungs-
    Typografie), und jeder hat seine eigene Begrenzung. Genau daran ist es
    vorbeigelaufen: `S.fit` schaetzt die Breite aus Einzelzeichen-Kaesten
    (Leerzeichen zaehlen dabei fast nichts) und hat eine harte Untergrenze -
    passt es danach immer noch nicht, prueft es niemand nach. Statt fuenf
    Schaetzungen zu flicken, wird am Ende EINMAL das fertige Bild gemessen
    und notfalls verkleinert. Dieselbe Bauweise wie `intent_time_floor`.

    Der GEWOLLTE Randabfall (v152, Items mit 'bleed') bleibt unangetastet -
    er ist Absicht und auf 8 Zeichen begrenzt. Rueckgabe: Anzahl korrigierter
    Momente."""
    links, rechts = -W * rand, W * (1.0 + rand)
    _BLEED_MAX = W * _BLEED_MAX_REL
    n = 0
    for p in plans:
        if 'target' not in p:
            continue                       # Kamera-Impulse tragen keinen Text
        _bl = [it for it in (p.get('front') or []) if it.get('bleed')]
        for it in _bl:
            it['_bleed_aus'] = True        # v152: gewollter Anschnitt, nicht messen
        try:
            box = ink_box(p, W, H)
        finally:
            for it in _bl:
                it.pop('_bleed_aus', None)
        if box is None:
            continue
        x0, x1 = box[0], box[1]
        # v230h: die endgueltige Tinten-Box am Plan merken. Der Riegel hier
        # misst die RUHELAGE - beim Zeichnen kommen aber noch Gesichts-
        # Tracking (bis +-30 px), Hand-Impuls und Objekt-Anker dazu, und
        # genau die haben Ismets 'CAPTIONS LOOK THE' aus dem Bild geschoben
        # (gemessen: Text an der Bildkante in 35 Frames). composite_frame
        # klemmt den Versatz jetzt gegen diese Box.
        p['_ink'] = (x0, x1)
        if x0 >= links and x1 <= rechts:
            continue
        breite = x1 - x0
        # v230g TOLERANZ IST NICHT ZIELBREITE. `nutzbar` stand auf
        # W * (1 + 2*rand) = 1.024 W - also auf einer Breite, die GROESSER ist
        # als das Bild. Jeder korrigierte Block landete danach exakt bei
        # -0.012..1.012 W, es wurde also auf JEDER Seite 1.2 % der Bildbreite
        # abgeschnitten (bei 1080 px gemessen: 26 px Tinte ausserhalb). Der
        # Riegel gegen den Anschnitt hat selbst angeschnitten.
        # `rand` bleibt die AUSLOESE-Schwelle (nicht wegen 3 px eingreifen),
        # die Zielbreite ist jetzt das Bild abzueglich derselben Toleranz.
        nutzbar = W * (1.0 - 2 * rand)
        s = min(1.0, nutzbar / breite) if breite > 1 else 1.0
        if s < 0.999:
            _skaliere_plan(p, s, W, H)
            box = ink_box(p, W, H)
            if box is None:
                continue
            x0, x1 = box[0], box[1]
        # Nach dem Verkleinern kann der Block noch aussermittig stehen
        # (die Tinte sitzt nicht zwangslaeufig mittig im Sprite).
        # v230g: verschoben wird auf die INNEN-Kante, nicht auf die
        # Ausloese-Schwelle - sonst bleibt der Block per Konstruktion mit
        # `rand` der Bildbreite draussen.
        ziel_l, ziel_r = W * rand, W * (1.0 - rand)
        dx = 0.0
        if x0 < ziel_l:
            dx = ziel_l - x0
        elif x1 > ziel_r:
            dx = ziel_r - x1
        if abs(dx) > 0.5:
            _verschiebe_plan(p, dx)
            x0, x1 = x0 + dx, x1 + dx
        p['_ink'] = (x0, x1)
        n += 1
    # v230h DER GEWOLLTE RANDABFALL DARF NUR EIN WORT KOSTEN, NICHT DEN BLOCK.
    # v152 laesst das Schlusswort bewusst am Bildrand auslaufen - und genau
    # dafuer nimmt die Messung oben die 'bleed'-Items heraus. Nur: geschoben
    # und skaliert wird danach der GANZE Plan. Ein breites Schlusswort zieht
    # den Rest damit auf der ANDEREN Seite hinaus. An Ismets Render zu sehen
    # ('CAPTIONS' links ohne C, 'LOOK THE' rechts heraus) und hier
    # nachgestellt: ohne bleed 0.012..0.988 W, mit bleed auf dem letzten Wort
    # -0.284..0.988 W - 28 % der Bildbreite links abgeschnitten.
    # Zweiter Durchgang deshalb MIT allen Items: der Ueberstand ist auf EINE
    # Seite und auf _BLEED_MAX begrenzt.
    for p in plans:
        if 'target' not in p or not any(it.get('bleed')
                                        for it in (p.get('front') or [])):
            continue
        box = ink_box(p, W, H)
        if box is None:
            continue
        x0, x1 = box[0], box[1]
        ueb_l, ueb_r = max(-x0, 0.0), max(x1 - W, 0.0)
        # Ein paar Pixel Ueberstand sind kein Anschnitt, sondern eine Glyphe,
        # die die Kante beruehrt - dieselbe Toleranz wie oben.
        _tol = W * rand
        if ueb_l <= _BLEED_MAX and ueb_r <= _BLEED_MAX \
                and (ueb_l <= _tol or ueb_r <= _tol):
            p['_ink'] = (x0, x1)
            continue                     # ein Wort laeuft aus - so gewollt
        breite = x1 - x0
        ziel = W + _BLEED_MAX            # ein Rand darf ueberstehen, nicht zwei
        s = min(1.0, ziel / breite) if breite > 1 else 1.0
        if s < 0.999:
            _skaliere_plan(p, s, W, H)
            box = ink_box(p, W, H)
            if box is None:
                continue
            x0, x1 = box[0], box[1]
        # Der Ueberstand gehoert auf die Seite, auf der er groesser ist -
        # dort steht das Schlusswort.
        if max(-x0, 0.0) >= max(x1 - W, 0.0):
            dx = -_BLEED_MAX - x0        # links auslaufen lassen
        else:
            dx = (W + _BLEED_MAX) - x1   # rechts auslaufen lassen
        if abs(dx) > 0.5:
            _verschiebe_plan(p, dx)
            x0, x1 = x0 + dx, x1 + dx
        p['_ink'] = (x0, x1)
        n += 1
    return n


def _skaliere_plan(p, s, W, H):
    """Alle Bildteile eines Textmoments um s verkleinern - Karte, Komposition
    und Fliesstext. Die Versaetze schrumpfen mit, sonst faellt das Layout
    auseinander (Treppen-Einzug, Stuetzzeile, Schreibschrift-Akzent)."""
    for k in ('arr', 'o_arr', 'flat_arr'):
        if p.get(k) is not None:
            p[k] = _skaliere_sprite(p[k], s)
    # v230b6 ZWEI FORMEN VON 'letters' - UND EINE DAVON HAT DEN RENDER
    # GEKIPPT. `letter_slices()` liefert (Sprite, Versatz); `S.text(...,
    # per_letter=True)` liefert (x_von, x_bis) als ZAHLEN, und genau das
    # steht bei 'cascade' im Plan. Der Skalierer kannte nur die erste Form
    # und rief `.shape` auf einer Zahl auf -> AttributeError, Render tot.
    # Gefunden beim Durchmessen der Einstellungen (Ismets Auftrag): sobald
    # ein cascade-Wort zu breit wurde und `fit_into_frame` es verkleinern
    # wollte, starb der Job. Derselbe Fehlertyp wie bei `ink_box` (v230n):
    # eine Funktion, die nur EINE Form kennt, ist blind fuer die andere.
    if p.get('letters'):
        _neu = []
        for _e in p['letters']:
            _a, _b = _e
            if hasattr(_a, 'shape'):          # (Sprite, Versatz)
                _neu.append((_skaliere_sprite(_a, s), _b * s))
            else:                              # (x_von, x_bis) in Pixeln
                _neu.append((float(_a) * s, float(_b) * s))
        p['letters'] = _neu
    for t in (p.get('tokens') or []):
        if t.get('arr') is not None:
            t['arr'] = _skaliere_sprite(t['arr'], s)
        t['ox'] = float(t.get('ox', 0.0)) * s
        t['oy'] = float(t.get('oy', 0.0)) * s
        if t.get('sz'):
            t['sz'] = max(int(t['sz'] * s), 8)
    # v230n: die Stuetzzeile schrumpft um die KARTENMITTE mit. Sie gehoert
    # zur selben Karte; um ihre eigene Mitte geschrumpft wandert sie relativ
    # zur Karte und der Satz faellt auseinander.
    _sm = [it for it in (p.get('small') or []) if it.get('cx') is not None]
    if _sm:
        _kx = float(p.get('cx', W / 2.0))
        _ky = float(p.get('cy', p.get('by', H * 0.398)))
        for it in _sm:
            if it.get('arr') is not None:
                it['arr'] = _skaliere_sprite(it['arr'], s)
            it['cx'] = _kx + (float(it['cx']) - _kx) * s
            it['cy'] = _ky + (float(it['cy']) - _ky) * s
            for k in ('w', 'adv', 'sz'):
                if it.get(k):
                    it[k] = it[k] * s
    fr = p.get('front') or []
    if fr:
        # Fliesstext-Items tragen absolute Koordinaten: um die Blockmitte
        # schrumpfen, damit der Satzspiegel als Ganzes kleiner wird.
        mx = sum(float(it['cx']) for it in fr) / len(fr)
        my = sum(float(it['cy']) for it in fr) / len(fr)
        for it in fr:
            if it.get('arr') is not None:
                it['arr'] = _skaliere_sprite(it['arr'], s)
            it['cx'] = mx + (float(it['cx']) - mx) * s
            it['cy'] = my + (float(it['cy']) - my) * s
            for k in ('w', 'adv', 'sz'):
                if it.get(k):
                    it[k] = it[k] * s


def _verschiebe_plan(p, dx):
    """Textmoment waagerecht verschieben, ohne seine Form anzufassen."""
    if p.get('cx') is not None:
        p['cx'] = float(p['cx']) + dx
    for t in (p.get('tokens') or []):
        t['ox'] = float(t.get('ox', 0.0)) + dx
    # v230n: die Stuetzzeile wird MITGEZOGEN. Sie zaehlt jetzt zur gemessenen
    # Tinte (ink_box) - haenge sie hier nicht mit ein, verschiebt der Riegel
    # die Karte und laesst die Zeile stehen.
    for it in (p.get('small') or []) + (p.get('front') or []):
        if it.get('cx') is not None:
            it['cx'] = float(it['cx']) + dx
    if p.get('target') is not None:
        p['target'] = (p['target'][0] + dx, p['target'][1])
    if p.get('vpos') is not None:
        p['vpos'] = (p['vpos'][0] + dx, p['vpos'][1])


def plan_text(p, words):
    """Der Wortlaut eines Textmoments - fuer das Job-Log. Ein Fliesstext-Block
    traegt seinen Text NICHT im Item (dort steht nur der Wortindex 'i'), er
    muss aus dem Transkript geholt werden. Bis v215 schrieb der Block-Log
    darum eine Reihe Leerzeichen, und die Zeile, die den Anschnitt haette
    zeigen sollen, zeigte gar nichts."""
    if p.get('kw_txt'):
        return str(p['kw_txt'])
    out = []
    for _it in (p.get('front') or []):
        _i = _it.get('i')
        if isinstance(_i, int) and 0 <= _i < len(words):
            out.append(clean(words[_i].get('word', '')))
        elif _it.get('txt'):
            out.append(str(_it['txt']))
    return ' '.join(x for x in out if x)


def card_t0(p, words):
    """Der Zeitpunkt, an dem eine Keyword-Karte WIRKLICH im Bild erscheint.
    Alle Zeichen-Zweige rechnen mit `t - p.get('t0', words[kw_i]['start'])`
    und ueberspringen negative Werte - sichtbar wird die Karte also genau
    dann, wenn diese Uhr bei 0 steht, nicht bei p['start'] (das ist der
    Gruppen-Anfang und traegt nur die kleinen Nebenwoerter)."""
    i = p.get('kw_i')
    if not isinstance(i, int) or not (0 <= i < len(words)):
        return p.get('t0', p.get('start', 0.0))
    return float(p.get('t0', words[i].get('start', 0.0)))


def intent_time_floor(plans, words, min_stage=0.50):
    """v214 EINE ANSAGE STEHT NIE VOR IHREM WORT.

    Ismets Werbespot, an seinem Job-Log belegt: die Karte 'ON THE WALL' stand
    ab 8.18 s, gesprochen wird der Satz erst ab 9.08 s. Sagt er "sticks on the
    wall", ist die Karte schon wieder weg - im Bild sieht es aus, als fehle
    sie ganz. Ursache war der 1.5-s-Vorlauf des Szenen-Texts ("liegt schon
    da"), den anschliessend der Solo-Riegel als t0 festschrieb.

    Das ist zum VIERTEN Mal derselbe Fehlertyp: eine Zeit-Regel, die den
    Sonderfall 'Ansage' nicht kennt. Die Ursachen sind an ihrer Stelle
    behoben; dieser Riegel ist der zentrale Rueckfall-Schutz fuer JEDE
    kuenftige Regel. Wer eine neue Zeit-Regel baut, muss sie nicht kennen -
    ihr Ergebnis laeuft hier durch.

    Verschoben wird nur nach HINTEN (spaeter ist erlaubt, frueher nie), und
    eine so verschobene Karte behaelt mindestens `min_stage` Sekunden Buehne.
    Rueckgabe: Anzahl korrigierter Ansagen."""
    n = 0
    for p in plans:
        if not p.get('intent') or p.get('_user_t'):
            continue                      # Nutzer-Zeit bleibt Nutzer-Zeit
        i = p.get('kw_i')
        if not isinstance(i, int) or not (0 <= i < len(words)):
            continue
        w0 = float(words[i].get('start', 0.0))
        if card_t0(p, words) >= w0 - 1e-6:
            continue
        p['t0'] = w0
        if p.get('end') is not None and float(p['end']) < w0 + min_stage:
            p['end'] = w0 + min_stage
        n += 1
    return n


def build_watermark(W, H):
    """v101: Free-Tier-Wasserzeichen als Sprite (Text + Logo, ~38%
    Deckkraft, unten rechts). Ausgelagert, damit der Watermark-Split
    (sauberer Master + identisch gewassermarkte Kopie) EXAKT dasselbe
    Bild nutzt wie der eingebrannte Pfad. Rueckgabe: (arr, x, y)."""
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
    return (_wm_arr, _wx, _wy)


# v101d SAFE-ZONE-REGIE: Jede Plattform legt ihre Bedienelemente woanders hin.
# Text, der unter der Like/Share-Leiste oder hinter der Untertitel-/Ton-Zeile
# verschwindet, ist verlorener Platz - der teuerste Fehler im Hochformat. Statt
# eines pauschalen "Safe-Zone an/aus" kennen wir die echten UI-Rechtecke der
# drei grossen Feeds (Stand 2026) und leiten daraus die nutzbare Text-Flaeche
# ab. Werte sind Anteile 0..1, konservativ (lieber 2% Reserve zu viel).
PLATFORM_UI = {
    # right = Button-Spalte rechts (Like/Kommentar/Teilen/Profil)
    # bottom = Caption-/Ton-/Beschreibungs-Zeile unten
    # top = Reiter/Progress oben
    'tiktok':  {'right': 0.155, 'bottom': 0.20, 'top': 0.09, 'label': 'TikTok'},
    'reels':   {'right': 0.150, 'bottom': 0.24, 'top': 0.10, 'label': 'Instagram Reels'},
    'shorts':  {'right': 0.150, 'bottom': 0.20, 'top': 0.12, 'label': 'YouTube Shorts'},
    # generic = alle Plattformen gleichzeitig sicher (Schnittmenge der Zonen)
    'generic': {'right': 0.160, 'bottom': 0.24, 'top': 0.12, 'label': 'alle Feeds'},
}


def platform_safe_zones(platform, W, H):
    """Nutzbare Text-Flaeche fuer eine Plattform. Rueckgabe: dict mit
    Pixel-Grenzen left/right/top/bottom (das Rechteck, IN dem Text sicher liegt)
    plus der Button-Spalten-Grenze right_rail und dem Label. Unbekannte
    Plattform -> 'generic' (Schnittmenge, nirgends verdeckt)."""
    z = PLATFORM_UI.get(str(platform or 'generic').lower(), PLATFORM_UI['generic'])
    return {
        'left':   int(W * 0.05),
        'right':  int(W * (1.0 - z['right'])),   # Button-Spalte bleibt frei
        'right_rail': int(W * (1.0 - z['right'])),
        'top':    int(H * z['top']),
        'bottom': int(H * (1.0 - z['bottom'])),  # Caption-Zeile bleibt frei
        'label':  z['label'],
    }


def contact_sheet(tiles, labels, cols=3, tile_w=360):
    """v101g REGIE-KONTAKTBOGEN: baut aus den echten Moment-Frames ein Grid-Bild
    (BGR). tiles = Liste BGR-Frames (beliebige Groessen, werden auf tile_w
    skaliert), labels = Text pro Tile ('WORT @ 12.3s'). Unter jedem Tile eine
    Beschriftungszeile. Rueckgabe None bei leerer Liste."""
    if not tiles:
        return None
    cols = max(1, min(cols, len(tiles)))
    cap_h = 26
    cells = []
    for img in tiles:
        h, w = img.shape[:2]
        th = max(int(h * tile_w / max(w, 1)), 8)
        cells.append(cv2.resize(np.asarray(img, np.uint8), (tile_w, th)))
    cell_h = max(c.shape[0] for c in cells) + cap_h
    rows = (len(cells) + cols - 1) // cols
    sheet = np.full((rows * cell_h, cols * tile_w, 3), 16, np.uint8)
    for i, c in enumerate(cells):
        r, k = divmod(i, cols)
        y0, x0 = r * cell_h, k * tile_w
        sheet[y0:y0 + c.shape[0], x0:x0 + tile_w] = c
        lab = str(labels[i] if i < len(labels) else '')[:36]
        cv2.putText(sheet, lab, (x0 + 6, y0 + cell_h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1, cv2.LINE_AA)
    return sheet


def safe_zone_report(plans, pz, W, H):
    """v101d: prueft die fertig platzierten Momente gegen die Plattform-Maske
    und meldet, welche in die Button-Spalte oder Caption-Zeile ragen. Nur
    Momente mit bekanntem Sprite ('arr') und Zentrum ('cx') werden geprueft -
    der Rest ist ohnehin mittig und durch die Constraints gedeckt.
    v187: das galt bis dahin NUR fuer Keyword-Karten - Flow- und Stack-
    Bloecke tragen ihren Text in 'front' (Items mit eigenen absoluten
    Koordinaten) und wurden komplett uebersprungen. Der Log sagte deshalb
    unwidersprochen "Button-Spalte bleibt frei", waehrend dort Text stand.
    Riegel am falschen Gate, derselbe Fehlertyp wie v159/v170/v176.
    Rueckgabe: Liste (kw_txt, grund). Rein beratend, aendert nichts."""
    if not pz:
        return []

    def _box(p):
        """(cx, cy, w, h) eines Plans - Karte ODER Textblock."""
        arr = p.get('arr')
        if arr is not None and p.get('cx') is not None:
            return (p['cx'], p.get('cy', p.get('by')),
                    arr.shape[1], arr.shape[0])
        its = [it for it in (p.get('front') or [])
               if it.get('arr') is not None and it.get('cx') is not None]
        if not its:
            return None
        # Gemessen wird die TINTE, nicht das Sprite-Rechteck: ein Text-Sprite
        # traegt bis zu 180 px transparenten Rand (Glow-Polster). Mit dem
        # Rechteck gerechnet meldete der Report Verstoesse, wo im Bild
        # nichts steht - dieselbe Unterscheidung wie _ink_x in build_plans.
        xs, ys = [], []
        for it in its:
            _a = it['arr']
            _nz = np.where(_a[..., 3] > 80)
            if not len(_nz[0]):
                continue
            xs += [it['cx'] - _a.shape[1] / 2.0 + float(_nz[1].min()),
                   it['cx'] - _a.shape[1] / 2.0 + float(_nz[1].max())]
            ys += [it['cy'] - _a.shape[0] / 2.0 + float(_nz[0].min()),
                   it['cy'] - _a.shape[0] / 2.0 + float(_nz[0].max())]
        if not xs:
            return None
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0, x1 - x0, y1 - y0)

    warn = []
    for p in plans:
        _b = _box(p)
        if _b is None:
            continue
        cx, cy, w, h = _b
        _nm = p.get('kw_txt') or ('%s @%.1fs' % (p.get('tpl', '?'),
                                                 float(p.get('start', 0))))
        if cx + w / 2 > pz['right_rail'] + 2:
            warn.append((_nm, 'right button column'))
        elif cy is not None and cy + h / 2 > pz['bottom'] + 2:
            warn.append((_nm, 'bottom caption row'))
        elif cy is not None and cy - h / 2 < pz['top'] - 2:
            warn.append((_nm, 'top tab bar'))
    return warn


def build_plans(words, kw, cfg, S, W, H, face_ok, fx_map=None, face_pos=None,
                palette_at=None, cut_times=None, faces_at=None, flow_map=None,
                loud=None, beat_times=None, light_dir=None, space_at=None,
                zeigen=None, bloecke=None):
    KW_FX = cfg['effects']['keyword_rotation']
    # v160: gemessene Zeige-/Blick-Ziele [(t, tx, ty, art)]. Ein Ziel gilt fuer
    # das Zeitfenster, in dem gezeigt wurde, plus einen kurzen Nachlauf - eine
    # Zeigegeste haelt laenger an als der Moment, an dem sie gemessen wurde.
    _zeig = sorted(zeigen or [], key=lambda z: z[0])

    def ziel_at(start, end, vor=0.35, nach=1.20):
        """Zeige-Ziel fuer ein Zeitfenster. Rueckgabe (tx, ty, art) oder None."""
        if not _zeig:
            return None
        best = None
        for (t, tx, ty, art) in _zeig:
            if t - vor <= end and t + nach >= start:
                # Naechstliegendes Ziel gewinnt, Zeigen schlaegt Blick.
                rang = (0 if art == 'zeigen' else 1, abs(t - start))
                if best is None or rang < best[0]:
                    best = (rang, (tx, ty, art))
        return best[1] if best else None
    CAM_FX = [m for m in (cfg['camera'].get('keyword_rotation') or []) if m and m != 'none']
    SIDE_MODES = [m for m in (cfg['camera'].get('side_rotation') or []) if m and m != 'none']
    side_every = int(cfg['camera'].get('side_every', 3))
    min_gap = cfg['keywords'].get('min_gap_seconds', 6.0)
    breathing = cfg['effects'].get('breathing', True)
    left_x, right_x = int(W * 0.224), int(W * 0.766)

    # v162 ZWEI-SPRECHER-REGIE
    # face_pos liefert bereits die Position des AKTIVEN Sprechers (track_faces
    # waehlt sie ueber die Mundbewegung, _active_index). Genutzt hat das
    # bisher nur die Kamera - die Captions sassen unabhaengig davon in der
    # breitesten Luecke. In einem Interview sah man dem Bild damit nie an,
    # wem der Satz gehoert.
    _spr_state = {}

    def sprecher_at(start, end):
        """x-Position des gerade sprechenden Gesichts, oder None.

        Nur bei MEHREREN Personen im Bild: bei einer Person ist "der
        Sprecher" keine Information, und die vorhandene Ausweich-Logik ist
        die bessere Wahl."""
        if not cfg['effects'].get('caption_sprecher', True):
            return None
        if face_pos is None or faces_at is None:
            return None
        fs = faces_at(start, end)
        if len(fs) < 2:
            _spr_state.pop('x', None)
            return None
        roh = float(face_pos(start, end)[0])
        # Auf das naechstgelegene ERKANNTE Gesicht einrasten. face_pos ist
        # ueber 41 Frames geglaettet und liegt beim Sprecherwechsel eine
        # Weile ZWISCHEN beiden Personen - ohne das Einrasten landet der
        # Text dort, also genau in der Mitte, wo niemand sitzt.
        ziel = min(fs, key=lambda f: abs(f[0] - roh))[0]
        alt = _spr_state.get('x')
        # Hysterese: erst wechseln, wenn das neue Gesicht deutlich naeher
        # dran ist. Sonst flackert der Text bei jedem Erkennungs-Zittern
        # zwischen zwei Personen hin und her.
        if alt is not None and abs(ziel - alt) > W * 0.02:
            if abs(roh - alt) <= abs(roh - ziel) + W * 0.04:
                ziel = alt
        _spr_state['x'] = float(ziel)
        return float(ziel)

    def pick_side(start, end, toggle):
        """Waehlt die freie Seite neben der Person und die Text-Position dort.
        Rueckgabe: (side -1/1, cx) - side -1 = links, 1 = rechts. Hochformat: zentriert."""
        # v160: hat der Sprecher gezeigt, entscheidet nicht mehr die freie
        # Seite, sondern die Zeigerichtung. Auch im Hochformat - dort war die
        # Position bisher fest die Bildmitte, und ein Zeigefinger nach links
        # blieb folgenlos. clamp_cx haelt den Block danach im sicheren Bereich.
        _zl = ziel_at(start, end)
        if _zl is not None:
            _zx = min(max(float(_zl[0]), W * 0.15), W * 0.85)
            return (-1 if _zx < W / 2 else 1), _zx
        # v162 ZWEI-SPRECHER-REGIE. Sind mehrere Personen im Bild, springt
        # der Text auf die Seite dessen, der GERADE REDET. Auch im
        # Hochformat - dort stand er bisher immer mittig, und in einem
        # Interview sah man dem Bild nie an, wem der Satz gehoert.
        _sp = sprecher_at(start, end)
        if _sp is not None and portrait:
            return (-1 if _sp < W / 2 else 1), _sp
        if portrait:
            return 0, W / 2
        if face_pos is None:
            cx = left_x if toggle % 2 == 0 else right_x
            return (-1 if cx < W / 2 else 1), cx
        # v96: Sind MEHRERE Gesichter im Bild, den Text in die freie Luecke
        # legen, die KEINES der Gesichter ueberdeckt (Multi-Face-Safe-Zone).
        # v162: bei bekanntem Sprecher die Luecke NEBEN IHM statt der
        # breitesten - die breiteste ist bei zwei Personen fast immer
        # dieselbe, egal wer redet.
        if faces_at is not None:
            _fs = faces_at(start, end)
            if len(_fs) >= 2:
                return _free_x_multi(_fs, W, W * 0.42, toggle, ziel_x=_sp)
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

    # v187 DICHTE-NORMALISIERUNG. Der TikTok-Preset schickte seit jeher
    # 'wortweise' - einen Wert, den die Engine an keinem ihrer fuenf
    # Verhaltens-Gates kennt. Er fiel damit in den sparsamen Pfad: der Look,
    # den die UI als "word by word" verkauft, zeigte die Haelfte der Woerter,
    # und die v185-Zusagen (keine Atempause, Luecken-Netz) liefen nie.
    # Hier normalisiert, damit auch gespeicherte Kunden-Konfigs greifen.
    _d187 = str(cfg['effects'].get('density', '')).lower()
    if _d187 in ('wortweise', 'word', 'wordwise'):
        cfg['effects']['density'] = 'durchgehend'
    portrait = W / H < 0.8    # 9:16 und aehnliche Hochformate
    # v139: FORMATGERECHTE Anker (Senior-Editor-Standard). Vorher sassen ALLE
    # Nicht-Hochformate auf einem festen 0.40H-Anker = obere Bildhaelfte,
    # mitten im Gesicht. Jetzt:
    #  - 16:9 und breiter: klassisches Lower Third im Title-Safe (SMPTE/
    #    Netflix: Text innerhalb des 90%-Rahmens; Block-MITTE ~0.78 haelt auch
    #    3-zeilige Stacks ueber der 0.90-Kante).
    #  - 4:3 / leicht quer: ~0.75.
    #  - 1:1 / 4:5 Feed: ~0.72 (Feed-UI unten, Text bleibt frei).
    #  - Hochformat behaelt die gesichtsbewusste v_zone (TikTok/Reels: untere
    #    Mittel-Zone, ueber der Bottom-UI der Plattform-Maske).
    # 'behind' bleibt oben (naeher am Kopf), 'ground' bleibt die Bodenebene.
    _ar = W / max(1.0, float(H))
    if _ar >= 1.45:
        Z_MAIN = H * 0.78     # 16:9+: Lower Third
    elif _ar >= 1.05:
        Z_MAIN = H * 0.75     # 4:3 / leicht quer
    else:
        Z_MAIN = H * 0.72     # 1:1 / 4:5
    Z_BEHIND = H * 0.34       # Text hinter der Person, sitzt hoeher
    safe_z = portrait and cfg['effects'].get('safe_zone', True)
    # v101d: plattform-genaue UI-Maske. Jeder Feed legt Button-Spalte und
    # Caption-Zeile woanders hin; die Zonen speisen die vertikalen Text-Grenzen
    # (v_zone) und den rechten Rand (clamp_cx), statt einer pauschalen Reserve.
    _plat = str(cfg.get('output', {}).get('platform', 'generic')).lower()
    _pz = platform_safe_zones(_plat, W, H) if safe_z else None
    if safe_z:
        print(f"Safe zone 9:16 active ({_pz['label']}): the right button "
              f"column and the caption row at the bottom stay clear")

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
        if _pz is not None:
            # v101d: Grenzen aus der Plattform-Maske. cap_bot laesst H*0.10
            # Text-Hoehe unter dem Anker frei, damit nichts in die Caption-Zeile
            # ragt; Reels (mehr Chrome unten) sitzt so hoeher als TikTok.
            floor_top = _pz['top']
            cap_bot = _pz['bottom'] - H * 0.10
        else:
            floor_top = H * 0.10
            cap_bot = H * 0.74
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

    # ================================================================
    # v143 PLATZIERUNGS-REGIE. Bis v142 stand der Fliesstext IMMER an
    # derselben Stelle: gemessen mit der Person links, rechts, hoch, tief und
    # in Nahaufnahme kam fuenfmal exakt x=0.164 y=0.234 (hoch) bzw.
    # x=0.090 y=0.780 (quer) heraus. Die Bausteine dafuer gab es laengst,
    # sie waren nur nicht verdrahtet: v_zone wurde im Hochformat sogar
    # AUFGERUFEN und ihr Ergebnis danach durch die feste H*0.13 ersetzt.
    #
    # spot() ist die eine Stelle, die das jetzt entscheidet. Sie bekommt die
    # Blockgroesse und liefert die linke obere Ecke. Reihenfolge der Regeln:
    #   1. HARTE Sperren: Title-Safe-Rand und Plattform-UI-Maske.
    #   2. HARTE Sperre: Gesichtsbox mit Rand - Text darf nie ins Gesicht.
    #   3. WEICHE Kosten: Motiv-Unruhe aus der Raum-Karte (space_at) und
    #      Abstand zur Wunschzone des Templates.
    #   4. HYSTERESE: die zuletzt gewaehlte Stelle gewinnt, solange sie nicht
    #      deutlich schlechter ist. Ohne das springt der Block bei jedem
    #      Zittern der Gesichtserkennung quer durchs Bild - genau daran ist
    #      der erste Entwurf im Audit gescheitert (10 px Gesichtsbreite
    #      kippten den Block um 0.19 W).
    #   5. RASTER: Ergebnis rastet auf VZ_GRID ein, damit Rundungsrauschen
    #      keine Ein-Pixel-Wanderung erzeugt.
    # ================================================================
    spot_state = {'xy': None, 'letzte_zeit': -1e9, 'seite': None}
    _cuts_sorted = sorted(float(c) for c in (cut_times or []))

    def _shot_neu(t):
        """Liegt zwischen der letzten Caption und dieser ein Schnitt? Dann
        darf (und soll) der Block frei neu platziert werden - die Hysterese
        wuerde ihn sonst aus der alten Einstellung mitschleppen."""
        import bisect
        vor = spot_state['letzte_zeit']
        spot_state['letzte_zeit'] = t
        if vor < -1e8:
            return True
        return bisect.bisect_right(_cuts_sorted, t) != bisect.bisect_right(_cuts_sorted, vor)

    def _freie_breite(start, end):
        """v143: breitester horizontaler Streifen, den KEIN Gesicht belegt.
        Rueckgabe in Pixeln oder None (dann bleibt die Standardspalte).
        Ohne das musste ein bildfuellender Kopf den Textblock nach unten
        draengen, weil der Block immer 0.86 W breit war und nirgends
        danebenpasste."""
        if face_pos is None and faces_at is None:
            return None
        boxen = []
        if faces_at is not None:
            for _f in (faces_at(start, end) or []):
                try:
                    boxen.append((float(_f[0]), float(_f[2])))
                except (TypeError, IndexError, ValueError):
                    pass
        if not boxen and face_pos is not None:
            _fx, _, _fw = face_pos(start, end)
            boxen.append((float(_fx), float(_fw)))
        if not boxen:
            return None
        rand = W * 0.05 + 8
        belegt = []
        for _fx, _fw in boxen:
            hw = _fw * 0.80 + W * 0.02
            belegt.append((_fx - hw, _fx + hw))
        belegt.sort()
        # Luecken links, zwischen und rechts der Koepfe messen
        luecken, cur = [], rand
        for a, b in belegt:
            if a > cur:
                luecken.append(a - cur)
            cur = max(cur, b)
        if (W - rand) > cur:
            luecken.append((W - rand) - cur)
        breit = max(luecken) if luecken else 0.0
        # Nur bei einer echten Nahaufnahme verengen. Gemessen am Anteil der
        # Breite, den die Koepfe wirklich belegen - NICHT an der groessten
        # Luecke: bei einem normal grossen Kopf in der Bildmitte ist die
        # groesste Luecke immer knapp unter der halben Breite, die Spalte
        # waere dann permanent schmal und der Block koennte vertikal gar
        # nicht mehr ausweichen.
        voll = W - 2 * rand
        belegt_w = 0.0
        cur = rand
        for a, b in belegt:
            belegt_w += max(0.0, min(b, W - rand) - max(a, cur))
            cur = max(cur, b)
        if belegt_w < voll * 0.40:
            return None
        return breit

    def _safe_rand():
        return W * 0.05 + 8                   # 5 % Title-Safe (SMPTE/EBU)

    def _zoom_stauchung():
        """Die Kamera skaliert den FERTIGEN Frame, Captions eingeschlossen.
        Referenz ist der anhaltende Zoom, nicht die Crash-Spitze."""
        return 1.0 + 0.10 * min(1.0, float(cfg['camera'].get('strength', 0.7))
                                + float(cfg['camera'].get('crash', 0.0)))

    def _korridor():
        """v187 NUTZBARE SATZBREITE. Der Flow-Satzspiegel war eine Konstante
        (0.86 W ab 0.07 W) und kannte die Plattform-Maske nicht. Gemessen war
        der Block damit breiter als der sichere Korridor (0.788 W bei
        TikTok); spot() konnte ihn nicht mehr klemmen, weil untere und obere
        Grenze zusammenfielen, und die Zoom-Stauchung schob ihn danach
        zusaetzlich nach rechts. Das war die gemeinsame Ursache fuer BEIDES:
        Text unter der Button-Spalte und abgeschnittene Buchstaben am
        Bildrand. Rueckgabe (x0, breite) - beides schon zoom-bereinigt."""
        _r = _safe_rand()
        _rechts = (_pz['right_rail'] if _pz is not None else W - _r)
        _z = _zoom_stauchung()
        _mx = W / 2.0
        _lo = max(_r, _mx - (_mx - _r) / _z)
        _hi = min(_rechts, _mx + (_rechts - _mx) / _z)
        return (_lo, max(W * 0.34, _hi - _lo))

    def spot(start, end, bw, bh, wunsch_y=None, kalt=False, wunsch_x=None,
             ziel=None, sprecher=None):
        """Freie Stelle fuer einen Textblock (bw x bh). Rueckgabe (x0, y0)."""
        rand_x = _safe_rand()                 # 5 % Title-Safe (SMPTE/EBU)
        oben = (_pz['top'] if _pz is not None else H * 0.05)
        unten = (_pz['bottom'] if _pz is not None else H * 0.95)
        rechts = (_pz['right_rail'] if _pz is not None else W - rand_x)
        x_lo, x_hi = rand_x, max(rand_x, rechts - bw)
        y_lo, y_hi = oben, max(oben, unten - bh)
        # v143: die Kamera skaliert den FERTIGEN Frame, Captions eingeschlossen.
        # Eine reine Planungs-Grenze greift dort nicht: gemessen lag der Block
        # planerisch bei 0.921 W und im Render trotzdem bei 0.961 W. Der
        # nutzbare Bereich wird deshalb um den Zoom zur Bildmitte gestaucht -
        # ein Punkt bei Abstand d von der Mitte landet nach dem Zoom bei d*z.
        # Referenz ist der ANHALTENDE Zoom (~1.10), nicht die Crash-Spitze
        # (1.42): die dauert wenige Frames und ist ein gewollter Schlag.
        _cz = _zoom_stauchung()
        if _cz > 1.001:
            _mx, _my = W / 2.0, H / 2.0
            x_lo = max(x_lo, _mx - (_mx - rand_x) / _cz)
            x_hi = min(x_hi, _mx + (rechts - _mx) / _cz - bw)
            y_lo = max(y_lo, _my - (_my - oben) / _cz)
            y_hi = min(y_hi, _my + (unten - _my) / _cz - bh)
            x_hi = max(x_lo, x_hi)
            y_hi = max(y_lo, y_hi)
        if x_hi < x_lo or y_hi < y_lo:        # Block groesser als die Flaeche
            return (max(x_lo, (W - bw) / 2.0), max(y_lo, (H - bh) / 2.0))

        # Gesichter als harte Sperrflaechen (mit Sicherheitsrand).
        sperren = []
        if faces_at is not None:
            for _f in (faces_at(start, end) or []):
                try:
                    _fx, _fy, _fw = float(_f[0]), float(_f[1]), float(_f[2])
                except (TypeError, IndexError, ValueError):
                    continue
                sperren.append((_fx, _fy, _fw))
        if not sperren and face_pos is not None:
            _fx, _fy, _fw = face_pos(start, end)
            sperren.append((float(_fx), float(_fy), float(_fw)))
        kaesten = []
        for _fx, _fy, _fw in sperren:
            hw = _fw * 0.80 + W * 0.02        # Kopf inkl. Haar + Rand
            hh = _fw * 1.25 + H * 0.015
            kaesten.append((_fx - hw, _fy - hh, _fx + hw, _fy + hh))

        karte = space_at(start + 0.15) if space_at is not None else None
        gy, gx = (karte.shape if karte is not None else (0, 0))

        def kosten(x, y):
            """Rueckgabe (gesamt, motiv). motiv = nur Gesicht + Atemluft -
            der Anteil, der eine Seiten-Entscheidung stoppen darf."""
            k = 0.0
            _motiv = 0.0                      # nur Gesicht/Atemluft, ohne Wuensche
            for (a, b, c, d) in kaesten:      # Ueberlappung mit einem Gesicht
                ux = max(0.0, min(x + bw, c) - max(x, a))
                uy = max(0.0, min(y + bh, d) - max(y, b))
                if ux > 0 and uy > 0:
                    # v143b: Grundstrafe fuer JEDE Beruehrung. Die reine
                    # Flaechen-Normierung machte einen schmalen Anschnitt fast
                    # gratis (gemessen 0.0125 Kosten bei 13 px Ueberlappung) -
                    # der Block blieb dadurch am Gesicht kleben, statt
                    # auszuweichen.
                    k += 2.5 + 8.0 * (ux * uy) / max(bw * bh, 1.0)
                    _motiv += 2.5 + 8.0 * (ux * uy) / max(bw * bh, 1.0)
                elif uy > 0:
                    # v143b: ATEMLUFT. Nicht-Ueberlappen reicht nicht - ein
                    # Cutter laesst Abstand. Ohne diesen Term blieb ein klein
                    # gesetzter Block an derselben Stelle stehen, egal ob die
                    # Person links oder rechts stand: er passte ja beide Male
                    # knapp vorbei. Kosten fallen linear ueber 0.06 W ab.
                    _luft = min(abs(x - c), abs(a - (x + bw)))
                    _soll = W * 0.06
                    if _luft < _soll:
                        k += 1.2 * (1.0 - _luft / _soll)
                        _motiv += 1.2 * (1.0 - _luft / _soll)
            if karte is not None and gy and gx:
                i0 = int(max(0, min(gy - 1, y / H * gy)))
                i1 = int(max(i0 + 1, min(gy, (y + bh) / H * gy)))
                j0 = int(max(0, min(gx - 1, x / W * gx)))
                j1 = int(max(j0 + 1, min(gx, (x + bw) / W * gx)))
                k += 1.6 * float(karte[i0:i1, j0:j1].mean())
            # v160 ZEIGE-ZIEL. Anders als die Wunschseite ist das KEIN
            # Tiebreaker: der Sprecher hat auf eine Stelle gezeigt, also
            # gehoert der Text dorthin. Der Term wirkt auf BEIDE Achsen und
            # wiegt schwerer als Wunschzone und Unruhe-Karte zusammen.
            # Er ueberrennt trotzdem kein Gesicht: eine Beruehrung kostet ab
            # 2.5 aufwaerts, das volle Zeige-Gewicht erreicht 2.2. Genau so
            # soll es sein - Text quer ueber dem Kopf des Sprechers waere
            # kein erfuellter Zeigefinger, sondern ein Fehler.
            if ziel is not None:
                k += 2.2 * (abs((x + bw / 2.0) - ziel[0]) / max(W, 1)
                            + abs((y + bh / 2.0) - ziel[1]) / max(H, 1))
            # v162 SPRECHER-NAEHE. Bewusst KEIN Tiebreaker: die Wunschseite
            # (wunsch_x) wirkt nur an Stellen ohne Motiv-Beruehrung, und
            # neben zwei Personen ist praktisch jede Stelle beruehrt - der
            # Sprecherwechsel waere damit folgenlos geblieben (derselbe
            # Fehler wie in v153). Das Gewicht liegt unter der
            # Gesichtssperre (ab 2.5), der Text landet also NEBEN dem
            # Sprecher, nie auf ihm.
            if sprecher is not None:
                k += 1.3 * abs((x + bw / 2.0) - sprecher) / max(W, 1)
            if ziel is not None:
                # Wunschzone und Wunschseite sind Vorgaben fuer den Normalfall.
                # Liegt eine gemessene Zeige-Geste vor, wuerden sie nur gegen
                # sie ziehen - der Rest der Kosten (Gesicht, Atemluft, Unruhe)
                # bleibt in Kraft.
                return k, _motiv
            if wunsch_y is not None:          # Template-Wunschzone, weich
                k += 1.1 * abs((y + bh / 2.0) - wunsch_y) / max(H, 1)
            # Wunsch-SEITE, nur als TIEBREAKER. Sie darf ausschliesslich
            # zwischen Stellen entscheiden, die das MOTIV ohnehin freilaesst.
            # Ein blosser Kosten-Term reicht nicht: mit Gewicht 1.3 und selbst
            # mit 0.55 blieb der Block im Querformat links stehen, egal ob die
            # Person links oder rechts stand (v153, beide Male x = 0.155 W).
            # v155: _motiv zaehlt NUR Gesichts-Beruehrungen. Vorher stand
            # dort die Zwischensumme inklusive Unruhe-Karte - die liefert an
            # JEDER Stelle einen Beitrag, die Bedingung war also praktisch nie
            # erfuellt und die Wunschseite lief leer (gemessen streuten die
            # Blockmitten nur ueber 0.26 W statt 0.48 W).
            if wunsch_x is not None and _motiv <= 0.0:
                k += 0.55 * abs((x + bw / 2.0) - wunsch_x) / max(W, 1)
            else:
                k += 0.35 * abs((x + bw / 2.0) - W / 2.0) / max(W, 1)
            return k, _motiv

        schritte_x = 9 if not portrait else 7
        kx = [x_lo + (x_hi - x_lo) * i / (schritte_x - 1.0)
              for i in range(schritte_x)] if x_hi > x_lo else [x_lo]
        ky = [y_lo + (y_hi - y_lo) * i / 8.0 for i in range(9)] \
            if y_hi > y_lo else [y_lo]
        best, best_k, best_m = (kx[0], ky[0]), 1e9, 1e9
        for x in kx:
            for y in ky:
                k, m = kosten(x, y)
                if k < best_k:
                    best, best_k, best_m = (x, y), k, m
        # v168: die SEITE ist eine Regie-Entscheidung, kein Kostengewicht.
        # Als Tiebreaker (0.55) verlor sie gegen die Unruhe-Karte (1.6):
        # steht der Sprecher rechts der Mitte und ist die Wand links ruhig,
        # ist die ruhigste Stelle IMMER links - jeder Block landete dort,
        # egal welche Seite die Regie wollte (am eigenen Render gemessen:
        # wx=0.7 W, Ergebnis 0.098 W; Ismets Befund "immer links").
        # Ein einzelner Toleranzwert kann das nicht trennen: Unruhe (bis
        # ~1.4) darf die Regie NICHT stoppen, Atemluft/Gesicht (ab ~1.1)
        # SCHON - die Bereiche ueberlappen. Deshalb entscheidet der
        # MOTIV-Anteil allein: die Wunschseite gilt, wenn ihre beste Stelle
        # genauso gesichtsfrei ist wie die beste Stelle insgesamt. Die
        # Unruhe-Karte waehlt nur noch die Position INNERHALB der Seite.
        # Steht die Person auf der Wunschseite, ist deren Motiv-Anteil
        # hoeher und die Seite faellt zurueck - das Ausweichen (v143)
        # bleibt unangetastet.
        if wunsch_x is not None and ziel is None and sprecher is None:
            kx_s = [x for x in kx
                    if abs((x + bw / 2.0) - wunsch_x) <= W * 0.22]
            # Die Seiten-Suche bleibt in der WUNSCHZONE (Hoehe). Ohne diese
            # Grenze wich sie auf eine Zeile UEBER dem Kopf aus - motivfrei,
            # aber ein Lower-Third-Block stand ploetzlich am oberen Rand,
            # nur um die Seite zu behaupten (gemessen: sm=0.00 direkt neben
            # einem Gesicht, weil y einfach darueber lag).
            ky_s = ([y for y in ky
                     if abs((y + bh / 2.0) - wunsch_y) <= H * 0.18]
                    if wunsch_y is not None else list(ky)) or list(ky)
            if kx_s:
                # Rangfolge innerhalb der Seite: (1) Motiv-Freiheit,
                # (2) Naehe zur Wunschmitte in 4 %-Schritten, (3) Kosten
                # (Wunschzone, Unruhe). Sonst schiebt die Unruhe-Karte den
                # Block wieder an die ruhige Fensterkante zur Bildmitte und
                # die "rechte" Seite sitzt bei 0.505 W - sah aus wie mittig.
                best_s, best_sk, best_sm, best_sd = None, 1e9, 1e9, 1e9
                for x in kx_s:
                    for y in ky_s:
                        k, m = kosten(x, y)
                        d = round(abs((x + bw / 2.0) - wunsch_x)
                                  / max(W * 0.04, 1.0))
                        if (round(m, 2), d, k) \
                                < (round(best_sm, 2), best_sd, best_sk):
                            best_s, best_sk = (x, y), k
                            best_sm, best_sd = m, d
                if best_s is not None and best_sm <= best_m + 0.05:
                    best, best_k = best_s, best_sk

        # Hysterese: alte Stelle behalten, solange sie nicht klar schlechter ist.
        alt = spot_state['xy']
        if alt is not None and not kalt:
            ax = min(max(alt[0], x_lo), x_hi)
            ay = min(max(alt[1], y_lo), y_hi)
            if kosten(ax, ay)[0] <= best_k + 0.16:
                best = (ax, ay)
        gr = max(VZ_GRID, 1.0)
        best = (round(best[0] / gr) * gr, round(best[1] / gr) * gr)
        spot_state['xy'] = best
        return best

    def clamp_cx(cx, sprite_w):
        m = W * 0.045 + 30            # Rand + Reserve fuer Kamera und Tracking
        half = sprite_w / 2
        lo, hi = half + m, W - half - m
        if _pz is not None:
            # v101d: rechter Rand endet an der Button-Spalte, nicht am Bildrand.
            hi = min(hi, _pz['right_rail'] - half)
            lo = max(lo, _pz['left'] + half)
        if lo >= hi:                  # Sprite breiter als der sichere Bereich: zentrieren
            return W / 2 if _pz is None else (lo + hi) / 2
        return min(max(cx, lo), hi)

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
    # v154: FALLBACK-ANIMATIONEN. anim_for() findet nur etwas, wenn das Wort
    # (oder sein Satz) einen Hinweis traegt - "fliegt", "faellt", "explodiert".
    # Bei normalen Keywords traf gemessen KEIN Hinweis, p['anim'] blieb None
    # und der Moment stand still. Ueber ein ganzes Video sahen die grossen
    # Momente dadurch alle gleich aus (Ismets Befund). Bewusst nur
    # BEDEUTUNGSNEUTRALE Animationen in der Rotation: 'sturz' oder 'knall'
    # muessen zum Wortsinn passen, 'puls' oder 'gewicht' passen immer.
    rot_anim = Rotator(('gewicht', 'puls', 'schweben', 'fokus', 'welle',
                        'enthuellen', 'schub', 'neon'), _seed + 17)
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
    # v193: Nutzer-Blockplan schlaegt die Engine-Aufteilung. Er kommt als
    # Parameter herein (nicht ueber cfg), damit build_plans testbar bleibt.
    _bl = list(bloecke or [])
    _bl_akt = [b for b in _bl if b.get('aktiv', True)]
    groups = groups_for(words, cfg, fx_map, bloecke=_bl)
    if _bl_akt:
        # Die Nutzer-Aufteilung ist Gesetz: kein nachtraegliches Auftrennen.
        # split_forced_groups wuerde eine bewusst gesetzte Blockgrenze wieder
        # verschieben, und danach zeigt jeder Block-Schluessel daneben.
        _blk_at = {b['i0']: b for b in _bl_akt}
    else:
        # v101n: mehrere erzwungene Woerter in EINER Phrase -> Phrase
        # auftrennen, damit jedes markierte Wort ein eigenes Highlight bekommt.
        groups = split_forced_groups(groups, fx_map)
        _blk_at = {}
    g_starts = [words[g[0]]['start'] for g in groups]
    # Randfall: nirgends ein Sprecher-Gesicht (Voiceover, Screen-Recording).
    # Dann duerfen die Captions nicht komplett wegfallen -> szenen-verankert zeigen.
    voiceover = bool(groups) and not any(
        face_ok(words[g[0]]['start'], words[g[-1]]['end']) for g in groups)
    if voiceover and not cfg['effects'].get('broll_captions', False):
        print("No speaker face in the video: captions are anchored to the scene.")
    used = set()                            # von Phrasen verbrauchte Woerter
    kw_count = 0
    for gi, g in enumerate(groups):
        g = [i for i in g if i not in used]
        if not g:
            continue
        start, end = words[g[0]]['start'], words[g[-1]]['end']
        # v193: der Block, den der Nutzer angelegt hat. Er ist ueber den
        # ERSTEN Wortindex adressiert, und weil die Nutzer-Aufteilung selbst
        # die Gruppen bildet, kann dieser Schluessel nicht danebenzeigen -
        # anders als flow_map, das auf g[0] einer frisch berechneten
        # Aufteilung sitzt und bei jeder Grenzverschiebung still verfaellt.
        _ublk = _blk_at.get(g[0]) if _blk_at else None
        if _ublk:
            # Nutzer-Zeiten gewinnen ueber die Wortzeiten.
            if _ublk.get('start') is not None:
                start = float(_ublk['start'])
            if _ublk.get('end') is not None:
                end = max(float(_ublk['end']), start + 0.10)
        next_start = g_starts[gi + 1] if gi + 1 < len(groups) else 1e9
        broll = not face_ok(start, end)
        # Adaptive Farben: Caption-Toene greifen die Szene dieses Moments auf
        S.set_palette(palette_at(start + 0.2) if palette_at else None)
        if broll and not voiceover and not cfg['effects'].get('broll_captions', False):
            # v99a: explizit angesagte Momente (intent) ueberleben auch das
            # B-Roll-Gate. "The captions are on the ground", waehrend die
            # Kamera auf den Boden schwenkt: kein Gesicht im Bild, aber GENAU
            # dort gehoert der Text hin. Der Szenen-Text braucht die Person
            # nicht (ground/liegend ist fuer B-Roll gebaut).
            # v193: ein vom Nutzer angelegter Block ueberlebt das Gate genauso.
            # Er hat den Block bewusst dort hingesetzt und sieht im Editor die
            # Vorschau des Bildes - wenn er dort Text will, bekommt er Text.
            if not _ublk and not any(
                    isinstance((fx_map or {}).get(i), dict)
                    and (fx_map[i].get('intent') or fx_map[i].get('user_pick'))
                    for i in g):
                prev_was_keyword = False
                continue                   # Szenen ohne Sprecher bleiben textfrei
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
        # v185: NICHT bei Dichte 'durchgehend'. Dort heisst die Ansage
        # "jedes Wort steht auf dem Schirm" - die Atempause loeschte die
        # ganze Folgegruppe und riss zusammen mit dem Keyword-Moment (der nur
        # EIN Wort zeigt) mehrsekundige Loecher. An Ismets Render gemessen:
        # 4.0 s von 15 s ohne jeden Text, dazu 4 von 30 Woertern nie sichtbar.
        # v193: ein Nutzer-Block ist kein Rhythmus-Vorschlag, sondern eine
        # Ansage. Die Atempause darf ihn nicht wegraeumen.
        # v221: auch 'akzente' verspricht jetzt jedes Wort im Bild (Ismets
        # Ansage). Die Atempause bleibt nur, wo die Pause der Stil IST.
        if (breathing and prev_was_keyword and not g_kw and not _ublk
                and str(cfg['effects'].get('density', 'akzente'))
                not in ('durchgehend', 'akzente')):
            prev_was_keyword = False
            continue

        # Dichte-Limit: zu dichte Keyword-Momente werden zu normalen Gruppen
        # Im Hook duerfen Momente enger stehen - hook_strength regelt wie eng
        # (0 = wie normal, 1 = dreifache Dichte)
        # v99a: EXPLIZIT ANGESAGTE Momente (intent - "the captions are on the
        # ground") duerfen von der Dichte-Regel NICHT degradiert werden. Der
        # Sprecher hat sie woertlich bestellt; faellt der Moment weg, "macht
        # das Video nicht, was er sagt". Intent gewinnt auch die Wort-Wahl
        # innerhalb der Gruppe.
        # v101m: Nutzer-Markierungen (user_pick) sind wie intent gegen die
        # Dichte-Regel geschuetzt - der Nutzer hat das Wort bewusst bestellt.
        # (Die SEMANTISCHE Platzierung bleibt intent-only, siehe unten.)
        _g_int = [i for i in g_kw
                  if isinstance((fx_map or {}).get(i), dict)
                  and (fx_map[i].get('intent') or fx_map[i].get('user_pick'))]
        if _g_int:
            g_kw = _g_int + [i for i in g_kw if i not in _g_int]
        gap_eff = min_gap * ((1.0 - 0.66 * hook_pow) if in_intro else 1.0)
        is_kw_group = bool(g_kw) and (bool(_g_int)
                                      or start - last_kw_end >= gap_eff)
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
                print(f"  Watchtime moment (gap {start - prev_budget:.0f}s): "
                      f"{words[i_f].get('word', '')}")

        # SATZ ZU ENDE FUEHREN: Ein grosser Keyword-Moment ("BLEIB dran denn am
        # Ende ...") deckt nur seine eigene Wortgruppe ab. Der Rest des Satzes
        # ("... wirst du das alles anders sehen") bildet Folgegruppen ohne eigenes
        # Keyword und fiele bei Dichte "akzente" weg - der Satz wirkt dann
        # abgeschnitten, als haette man vergessen weiterzumachen. Solche
        # Fortsetzungen laufen darum als ruhige Caption weiter, bis der Satz
        # (Punkt/Frage/Ausruf) abgeschlossen ist.
        # v169: eine echte SPRECHPAUSE beendet den sichtbaren Satz. Ohne
        # diese Grenze hielt die Fortsetzung ein einzelnes "is" am Leben,
        # das 3.5 s nach dem Keyword-Moment allein unten im Bild stand wie
        # ein Rest (Ismets Video, 14s). Und ein Ein-Wort-Haeppchen traegt
        # als eigener Moment ohnehin nichts - Stille ist besser.
        _pause_davor = (words[g[0]]['start'] - words[g[0] - 1]['end']
                        if g[0] > 0 else 0.0)
        _winzig = (len(g) == 1
                   and len(clean(words[g[0]].get('word', ''))) <= 4)
        # v170: der Ein-Wort-Rest fiel nur im Akzente-Pfad weg. Ismets Job
        # lief mit Dichte 'durchgehend' - dort (und im Hook-Intro) rendert
        # JEDE Gruppe, und das einsame "is" stand wieder im Bild. Der Riegel
        # gehoert VOR die Pfad-Weichen, nicht in eine davon (v159-Lehre).
        # Ausdrueckliche Momente (intent/user_pick) bleiben unantastbar.
        # v193: hat der Nutzer diesen Ein-Wort-Block selbst angelegt, ist er
        # gewollt. Der Riegel ist gegen ZUFAELLIGE Reste gebaut, nicht gegen
        # eine Entscheidung.
        if (_winzig and _pause_davor >= 1.2 and not is_kw_group and not _ublk
                and not any(isinstance((fx_map or {}).get(i), dict)
                            and (fx_map[i].get('intent')
                                 or fx_map[i].get('user_pick'))
                            for i in g)):
            print(f"  Orphan word after a pause skipped: "
                  f"'{clean(words[g[0]].get('word', ''))}'")
            continue
        satz_offen = (prev_was_keyword_sentence
                      and hat_interpunktion
                      and not is_kw_group
                      and not in_intro
                      and not broll
                      and forts_count < 2
                      and start - last_kw_end < 4.0
                      and _pause_davor < 1.2
                      and not _winzig)
        if satz_offen:
            # kein neuer Moment - nur weiterlesen lassen
            fx_map.pop(g[0], None)
            forts_count += 1

        # Plattform-Dichte: YouTube/Ausgewogen zeigen nur Akzent-Momente.
        # Im Hook-Intro laufen die Captions durchgehend fuer die Watchtime.
        # v193: DAS ist das Gate, an dem eine Nutzer-Aufteilung ohne Schutz
        # zerbrechen wuerde. Wer im Editor einen Block anlegt, hat 'akzente'
        # meist gar nicht bewusst gewaehlt - der Block waere trotzdem still
        # verschwunden, und die Dichte-Einstellung haette die sichtbare
        # Nutzer-Entscheidung ueberstimmt. Der Nutzer steht ueber dem Preset.
        if (cfg['effects'].get('density', 'akzente') != 'durchgehend'
                and not is_kw_group and not in_intro and not satz_offen
                and not _ublk):
            continue

        # v193: Vorpruefung der Mindest-Buehnenzeit BEI NUTZER-BLOECKEN.
        # Der Riegel weiter unten laesst den ganzen Chunk fallen, wenn die
        # Keyword-Karte keine Sekunde bekommt. Bei einem selbst angelegten
        # Block waere das der schlimmste Fall fuer einen Editor: der Nutzer
        # legt einen Block an, und im Video steht dort nichts. Also faellt
        # hier nur die KARTE weg - der Block laeuft als Fliesstext weiter.
        if _ublk and is_kw_group and g_kw:
            _kt0 = words[g_kw[0]]['start']
            _de = min(max(end, _kt0 + 1.2), end + 1.5)
            if (_de > end and not voiceover and not broll
                    and not face_ok(end, _de)):
                _de = end
            if _de - _kt0 < 1.0:
                print(f"  Block {g[0]}: no stage time for the keyword card, "
                      f"showing it as running text")
                is_kw_group = False
                prev_was_keyword = False
                last_kw_end = prev_budget
                g_kw = []
        if is_kw_group:
            i = g_kw[0]                       # bestes Keyword der Gruppe (Score)
            if zrel(i) > 0:
                last_num_end = end
                print(f"  Number moment ({zrel(i):.1f}): {clean(words[i]['word'])}")
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
                # v193: eine Phrase darf ueber eine ENGINE-Chunkgrenze
                # greifen, aber niemals ueber eine vom Nutzer gezogene. Sonst
                # frisst der Keyword-Moment Woerter aus dem naechsten Block,
                # und der Block, den der Nutzer angelegt hat, ist im Video
                # kuerzer als im Editor.
                if _ublk and j >= _ublk['i1']:
                    break
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
                # v230l DIE KARTE MUSS BESITZEN, WAS SIE ZEIGT. Ein
                # Kartentext mit MEHR Woertern als die Phrase liess die
                # ueberzaehligen Woerter frei - sie standen danach ein
                # zweites Mal als Fliesstext im Bild (Ismets Befund: "das
                # Gesagte wird zweimal eingeblendet"). Deckt sich der Text
                # mit den GESPROCHENEN Woertern ab i, waechst die Phrase
                # mit; die Woerter gehoeren dann der Karte und werden nicht
                # noch einmal gesetzt. Frei erfundener Text bleibt davon
                # unberuehrt, dort gibt es nichts zuzuordnen.
                if len(ov_toks) > len(phrase):
                    _ph2 = list(phrase)
                    for _k in range(len(phrase), len(ov_toks)):
                        _j = phrase[0] + _k
                        if _j >= len(words) or _j in used:
                            break
                        if _ublk and _j >= _ublk['i1']:
                            break
                        if _norm_txt(words[_j]['word']) != _norm_txt(ov_toks[_k]):
                            break
                        _ph2.append(_j)
                    if len(_ph2) > len(phrase):
                        phrase = _ph2
                        used.update(phrase)
                        end = max(end, words[phrase[-1]]['end'])
                if len(ov_toks) == len(phrase):   # Wort fuer Wort in die Komposition
                    words_c = list(words)
                    for j, tok in zip(phrase, ov_toks):
                        words_c[j] = dict(words[j], word=tok)
                elif len(ov_toks) < len(phrase) and len(phrase) >= 2:
                    # Text KUERZER als die Phrase: die uebrigen gesprochenen
                    # Woerter bekommen wieder eigene Captions.
                    # v230l: bei einem LAENGEREN Text darf hier nicht gekuerzt
                    # werden - die Karte zeigt diese Woerter ja, und freigeben
                    # hiesse sie ein zweites Mal ins Bild zu setzen.
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
            # v185 STUETZZEILE IM HAUSMASS. Bis v184 lief sie hart auf
            # 0.043 H mit Tracking 14 - gesperrte Mikroversalien, die zu
            # keinem Look gehoerten (Ismets Befund am Render: "THESE FORM"
            # sieht aus wie aus einem anderen Produkt). Sie nimmt jetzt
            # dieselbe Groesse und dieselbe Laufweite wie der Fliesstext der
            # Flow-Caption, inklusive Referenz-Skalierung und Viral-Faktor.
            _pf5 = 1.35 if not portrait else 1.0
            _sk5 = float(cfg['effects'].get('caption_scale') or 1.0)
            _sk5 = max(0.60, min(2.80, _sk5))
            _skn5 = float(cfg['effects'].get('caption_scale_klein') or 0) or None
            _skn5 = max(0.60, min(1.30, _skn5)) if _skn5 else _sk5
            _sz5 = int(H * 0.050 * _pf5 * _skn5)
            _trk5 = 6 if portrait else max(2, int(_sz5 * 0.0625))
            small = []
            for i2 in ([] if (cfg['effects'].get('density', 'akzente') == 'akzente'
                              and not in_intro)
                       else [x for x in g if x not in phrase]):
                a2, tw = S.text(clean(words[i2]['word']).upper(), _sz5, S.white,
                                tracking=_trk5, font=S.f_sans)
                small.append({'i': i2, 'arr': a2, 'w': tw})
            p = {'tpl': fx, 'kw_i': i, 'kw_txt': txt, 'small': small, 'start': start, 'end': end,
                 'tilt': rng(i, 4) * 3 - 1.5, 'side': 0, 'broll': broll}
            # v193 WUCHT AN DEN PLAN. Bis v192 stand 'power' ausschliesslich in
            # fx_map - SIEBEN Leser im Zeichner lasen p.get('power', 2) und
            # bekamen darum immer 2. Dadurch liefen Depth-Bullet-Time, die
            # Stille vor dem Einschlag, der Split-Screen, der Freeze-Frame und
            # zwei Timing-Regeln nie an. Ohne das Feld am Plan koennte auch die
            # Wucht aus dem Block-Editor nichts bewirken.
            p['power'] = int((fx_map or {}).get(i, {}).get('power', 2)
                             if isinstance((fx_map or {}).get(i), dict) else 2)
            # v214 ANSAGE AN DEN PLAN. 'intent' stand bisher nur in fx_map -
            # jede Zeit-Regel weiter unten arbeitet aber auf Plaenen und
            # konnte deshalb nicht wissen, dass dieser Moment eine ANSAGE
            # ist. Genau daran ist die Wand-Ansage vor ihr Wort gerutscht.
            if isinstance((fx_map or {}).get(i), dict) and fx_map[i].get('intent'):
                p['intent'] = True
            if _ublk:
                p['_user'] = True
                if _ublk.get('power'):
                    p['power'] = int(_ublk['power'])
                if _ublk.get('start') is not None:
                    p['_user_t'] = True
            # v193 Groesse pro Block, auch auf der Keyword-Karte. Der Faktor
            # geht in die ZIELgroesse von S.fit, nicht auf das Ergebnis -
            # sonst waere die Breiten-Klemmung von fit ausgehebelt und ein
            # langes Wort liefe wieder aus dem Bild (v152).
            _ugrf = float((_ublk or {}).get('groesse') or 1.0)
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
            # v172 SICHTBARKEIT HAENGT AM WORT, nicht an der Anim-Wahl.
            # Der v169/v170-Riegel prueft die GEWAEHLTE Animation - waehlt
            # die KI-Regie fuer "EXPLODE" ein anderes Anim (oder keins,
            # oder sind Animationen im Job aus), feuert er nie, und die
            # Punchline steht weiter hinter der Person (Ismets Render,
            # dritter Beweis am gestempelten Job). Ob ein Wort eine
            # sichtbare Handlung IST, sagt das Wort selbst (anim_for) -
            # unabhaengig davon, was die Regie daraus macht.
            # Eine ORTS-Ansage ("behind me") hat kein Aktionsverb und
            # bleibt dadurch automatisch Gesetz; sagt der Satz die Handlung
            # ("boom they explode"), gewinnt die Handlung auch gegen
            # intent - exakt die dokumentierte v99-Regel: sichtbar vorn,
            # nie behind.
            _wort_anim = anim_for(txt, anim_ctx(words, i, len(phrase)))
            # v173: 'blurin' gehoert dazu. Sein grosses Wort wird VOR dem
            # Person-Overlay gezeichnet (Zeile 'comp = person * alpha_p
            # + ...') und steht damit genauso hinter der Person wie behind
            # und ground. Genau diesen fx hatte die Regie fuer Ismets
            # "EXPLODE" gewaehlt - pixel-identisch in zwei Jobs, und alle
            # bisherigen Riegel prueften nur behind/ground.
            if (_wort_anim in _VISIBLE_ANIM and not broll
                    and fx in ('behind', 'ground', 'blurin')):
                fx = 'outline'
                p['tpl'] = 'outline'
                print(f"  Visibility: '{txt}' is an action ({_wort_anim}) "
                      f"-> in front, not behind the person")
            # v161 OBJEKT-ANKER durchreichen. Auf B-Roll nicht: dort gehoert
            # der Text zur Szene, nicht zu einem Gegenstand darin.
            _ak = info.get('anker') if isinstance(info, dict) else None
            if _ak and cfg['effects'].get('caption_objekt', True) and not broll:
                p['_ank0'] = (float(_ak['cx']) * W, float(_ak['cy']) * H,
                              max(float(_ak.get('groesse', 0.15)) * W * 0.5,
                                  W * 0.03))
                p['_ank_obj'] = str(_ak.get('objekt', ''))
            if cfg['effects'].get('anim', True):
                _auto_anim = (info.get('anim') if isinstance(info, dict) else None)
                if not _auto_anim:
                    _auto_anim = anim_for(txt, anim_ctx(words, i, len(phrase)))
                if not _auto_anim:
                    # Kein semantischer Treffer: eine neutrale Animation aus
                    # der Rotation, statt den Moment still stehen zu lassen.
                    _auto_anim = rot_anim.next()
                p['anim'] = _auto_anim
                # v169: BEWEGUNG MUSS MAN SEHEN - in ALLEN Pfaden. Der
                # Riegel existierte im Cache- und im Ansage-Pfad; kam die
                # Animation aber aus der Auto-Wahl hier (oder aus der
                # KI-Frischwahl), stand ein "EXPLODE" hinter der Person und
                # der Koerper verdeckte die Punchline (Ismets Video, 4s).
                # Eine ausdrueckliche Ansage ("behind me") bleibt Gesetz.
                # v170: auch 'ground' verdeckt - Szenen-Text steht HINTER
                # der Person (Ismets "EXPLODE" kam als Wand-Text aus der
                # Vision-Regie und der Koerper verdeckte die Punchline;
                # der v169-Riegel prueft nur 'behind'). Auf B-Roll bleibt
                # ground: dort gibt es keine Person, die verdeckt.
                if (_auto_anim in _VISIBLE_ANIM and not broll
                        and fx in ('behind', 'ground', 'blurin')
                        and not (isinstance(info, dict) and info.get('intent'))):
                    fx = 'outline'
                    p['tpl'] = 'outline'
                    print(f"  Visibility: '{txt}' moves ({_auto_anim}) "
                          f"-> in front, not behind the person")
                # Auto-Wahl zurueck in fx_map schreiben, damit der Momente-Editor
                # sie anzeigt (sonst steht dort "keine", obwohl das Video animiert).
                if _auto_anim and isinstance(fx_map, dict):
                    if i not in fx_map or not isinstance(fx_map[i], dict):
                        fx_map[i] = fx_map.get(i) if isinstance(fx_map.get(i), dict) else {}
                    if isinstance(fx_map.get(i), dict):
                        fx_map[i].setdefault('anim', _auto_anim)
                if p.get('anim'):
                    print(f"  Living typography: {anim_en(p['anim'])} on '{txt}'")
            if _cnt:
                p['count'] = {'fmt': _cnt[0], 'dur': _cnt[1]}
                print(f"  Counter moment: {txt}")

            _pw_here = int(info.get('power', 2)) if isinstance(info, dict) else 2

            if broll:
                p['ccam'] = 'none'
            elif fx in ('behind', 'blurin', 'ground'):
                if CAM_FX:
                    p['cam'] = rot_cam.next(); camc += 1
                    # v226 DIE KAMERA DARF DIE ANSAGE NICHT WIDERLEGEN.
                    # Ismets Befund am gestempelten Render (v225b): "das
                    # 'above me' zuckt etwas zu viel und geht runter". Am Bild
                    # gemessen wanderte die Karte in 0.29 s um 109 px NACH
                    # UNTEN - bei einer Ansage, die "ueber mir" bedeutet.
                    # Ursache ist der Kameramodus 'caption': er schiebt das
                    # Bild um (by - H/2) * 0.30 auf die Karte zu, bei by =
                    # 0.22 H also 108 px nach unten - genau der Messwert.
                    # Und er kann sein Versprechen ("Close-up auf die
                    # Caption") gar nicht halten: die Caption wird VOR dem
                    # Warp ins Bild gezeichnet, wandert also mit. Der Abstand
                    # zwischen Kamera und Karte bleibt gleich, es rutscht nur
                    # alles zusammen - ein Name, der eine Zusage macht, die
                    # der Code nicht einloest (v194-Lehre).
                    # Bei einer ORTS-Ansage ist das nicht nur wirkungslos,
                    # sondern falsch: die Karte verlaesst den angesagten Ort.
                    # Sie bekommt deshalb den reinen Zoom ('punch') - Wucht
                    # ohne Versatz.
                    # Die Ansage muss AM PLAN stehen, nicht nur in `info`:
                    # `fx` fuehrt eine Himmel-Ansage je nach Fall durch den
                    # ground- ODER den behind-Zweig, und nur der ground-Zweig
                    # schreibt `p['szene']`. Ein Riegel, der davon abhaengt,
                    # greift dann in der Haelfte der Faelle nicht (v159-Lehre:
                    # der Riegel gehoert an die immer laufende Stelle).
                    if (isinstance(info, dict) and info.get('intent')
                            and info.get('szene')):
                        p['ort_ansage'] = str(info['szene'])
                    if p['cam'] == 'caption' and p.get('ort_ansage'):
                        p['cam'] = 'punch'
                        print(f"  Camera: '{txt}' is a place announcement "
                              f"({info.get('szene')}) -> zoom without vertical "
                              f"drift")
            else:
                p['ccam'] = next_side_cam()
            # v99a: Eine PLATZIERUNGS-Ansage schlaegt die Komposition. "ON THE
            # GROUND" (Mehrwort, fx ground) muss auf dem Boden liegen - die
            # Editorial-Komposition wuerde es als 'behind' hinter die Person
            # legen. Ebenso 'himmel' (steigt ueber den Kopf): einzelner Sprite.
            _platzierung = (fx == 'ground'
                            or (fx == 'behind' and isinstance(info, dict)
                                and info.get('szene') == 'himmel'))
            if len(phrase) >= 2 and not _platzierung:
                p['tokens'] = compose_phrase(phrase, words_c, S, W, H, portrait, safe_z,
                                             loud=loud)
                print(f"  Editorial composition: {txt}")
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
                # v228a DIE PERSON GEHOERT IN DIE WORTMITTE, NICHT AN SEIN ENDE.
                # Ismets Befund am gestempelten v227a-Render ("das Maskieren
                # hat hier nicht gut geklappt"): von "BEHIND ME" war nur "BEHI"
                # lesbar. Am Bild gemessen steht der Sprecher bei 0.66 W, der
                # Satz wurde aber IMMER auf die Bildmitte gesetzt (fest W/2 im
                # Zeichenpfad) - seine Silhouette lag damit auf dem rechten
                # Wortende und frass es am Stueck. Der Referenz-Look ist
                # ohnehin "die Person steht MITTEN im Wort".
                # WICHTIG: dieser Zweig (Mehrwort-Komposition) ist der
                # haeufigste - "BEHIND ME" sind zwei Woerter. Die
                # Lesbarkeits-Stufen weiter unten haengen an p['arr'] und
                # laufen hier gar nicht; ein Riegel nur dort waere wirkungslos
                # gewesen (v219-Lehre: prueft, ob die Zeile erreicht wird).
                if face_pos is not None and not broll and p.get('tokens'):
                    _fpc = face_pos(start, end)
                    if _fpc:
                        _hb = max((abs(tk['ox']) + tk['arr'].shape[1] / 2.0
                                   for tk in p['tokens'] if tk.get('arr') is not None),
                                  default=0.0) + W * 0.02
                        if _hb < W / 2:
                            p['bx'] = min(max(float(_fpc[0]), _hb), W - _hb)
                            if abs(p['bx'] - W / 2) > W * 0.02:
                                print(f"  Legibility: '{txt}' centred on the "
                                      f"speaker ({p['bx'] / W:.2f} W) so the "
                                      f"body cannot eat one end")
                            # Steht die Person am Bildrand, reicht Verschieben
                            # nicht: der Block laesst sich nicht weiter
                            # mittig auf sie legen, ohne aus dem Bild zu
                            # laufen. Dann gilt die v191-Stufe 2 - auf
                            # KOPFHOEHE ist die Silhouette nur die Kopfbreite
                            # statt der Schultern, und beide Wortenden bleiben
                            # stehen. Gemessen wird der schwaechere Rand.
                            _sch = float(_fpc[2]) * 2.6
                            _li = max(0.0, (float(_fpc[0]) - _sch / 2)
                                      - (p['bx'] - _hb))
                            _re = max(0.0, (p['bx'] + _hb)
                                      - (float(_fpc[0]) + _sch / 2))
                            # Schwelle in BUCHSTABEN, nicht in Prozent: was
                            # herausragt, muss LESBAR sein. Ein Versal ist
                            # rund 0.6 der Schriftgroesse breit, also braucht
                            # es gut zwei davon.
                            _szc = next((float(tk.get('sz') or 0)
                                         for tk in p['tokens']
                                         if tk.get('role') == 'core'), 0.0)
                            _min_rand = (_szc * 1.2 if _szc > 0
                                         else 0.15 * 2 * _hb)
                            if min(_li, _re) < _min_rand:
                                p['by'] = max(float(_fpc[1])
                                              - float(_fpc[2]) * 1.7 * 0.15,
                                              H * 0.07)
                                if p.get('entr') == 'emerge':
                                    p['entr'] = 'rise'
                                print(f"  Legibility: '{txt}' raised to head "
                                      f"height - the speaker stands at the "
                                      f"edge, shifting alone would still eat "
                                      f"one end")
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
                elif face_pos is not None and (
                        p.get('entr') == 'emerge'
                        or (isinstance(info, dict) and info.get('nah'))):
                    # v141: auch die angesagte Nahaufnahme ("behind you") wird
                    # hier gehalten - am Kopf, nicht am oberen Bildrand.
                    _fp = face_pos(start, end)
                    if _fp:
                        p['by'] = max(min(float(_fp[1]) - H * 0.055, H * 0.62),
                                      H * 0.10)
                _bh_limit = int(W * (0.62 if safe_z else 0.94) if portrait else W * 0.885)
                sz = S.fit(txt, int((H * 0.213 if not portrait else H * 0.11) * _ugrf), _bh_limit)

                def _build_behind(_s):
                    # v230g EINE GEWAEHLTE ANIMATION MUSS LAUFEN.
                    # Der buchstabenweise Aufbau (S.kinetic, z.B. Look
                    # 'TikTok') legt p['letters'] an - und der Zeichenzweig
                    # dafuer ruft anim_apply GAR NICHT auf. Gemessen: bei
                    # text_style '3d' 1 Aufruf je Bild und sichtbare
                    # Bewegung, bei '3d kinetisch' 0 Aufrufe und ein
                    # stehendes Wort. Die Animation fiel also ersatzlos weg,
                    # sobald der Look kinetisch war. Beides gleichzeitig geht
                    # nicht (der Aufbau schneidet das Wort in Slices), also
                    # gewinnt die ANIMATION - sie ist die ausdrueckliche
                    # Wahl der Regie bzw. des Nutzers.
                    if S.kinetic and not p.get('count') and not p.get('anim'):
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
                        # v191 VERDECKT WIRD VON DER PERSON, NICHT VOM KOPF.
                        # Der Riegel verglich die Wortbreite mit der Kopfbreite
                        # (1.7x Gesichtsbox) - ausgestanzt wird aber die ganze
                        # Silhouette inklusive SCHULTERN, und die sind rund
                        # 2.6x Gesichtsbox breit. An Ismets Render gemessen:
                        # 'ZIGARETTEN' war mit 0.52 W klar breiter als der
                        # Kopf, der Riegel griff nicht, und die Person frass
                        # trotzdem 28 % des Wortes AM STUECK - lesbar blieb
                        # "ZIGA...TTEN".
                        _schulter = float(_fpv[2]) * 2.6
                        # (1) So gross, dass beidseits der Schultern etwas
                        #     Substanzielles stehen bleibt.
                        if _tw < _schulter * 1.55:
                            _gr = min(_schulter * 1.60 / max(_tw, 1),
                                      _bh_limit / max(_tw, 1))
                            if _gr > 1.02:
                                sz = int(sz * _gr)
                                _build_behind(sz)
                                _tw = _vis_w()
                        # (2) Reicht die Breite nicht, gehoert das Wort auf
                        #     KOPFHOEHE. Dort ist die Silhouette nur die
                        #     Gesichtsbox breit statt der Schultern - genau
                        #     das beschreibt die v99-Regel fuer Nahaufnahmen
                        #     ("ragt beidseitig am Kopf vorbei").
                        # v210: NICHT bei einer HIMMEL-Ansage. "above me"
                        # heisst UEBER dem Kopf; die Lesbarkeits-Stufe zog das
                        # Wort auf KOPFHOEHE herunter - gut gemeint und genau
                        # das Gegenteil der Ansage (in Ismets Job-Log belegt:
                        # "Legibility: 'ABOVE ME' raised to head height").
                        # Eine Ansage ist Gesetz; die Schutzliste des
                        # intent-Flags kannte diesen Riegel bisher nicht.
                        _himmel = (isinstance(info, dict)
                                   and info.get('szene') == 'himmel')
                        if _tw < _schulter * 1.35 and not _himmel:
                            p['by'] = max(float(_fpv[1]) - _kopf * 0.15,
                                          H * 0.07)
                            if p.get('entr') == 'emerge':
                                p['entr'] = 'rise'
                        # (3) Selbst am Kopf zu schmal: ueber den Kopf legen.
                        if _tw < _kopf * 1.10 or _himmel:
                            p['by'] = max(float(_fpv[1]) - _kopf * 0.85,
                                          H * 0.07)
                            print(f"  Legibility: '{txt}' narrower than the "
                                  f"head -> placed above the head")
                        elif _tw < _schulter * 1.35:
                            print(f"  Legibility: '{txt}' raised to head "
                                  f"height so the body cannot cut it")
                        else:
                            print(f"  Legibility: '{txt}' enlarged so it "
                                  f"clears the shoulders on both sides")
                        # v228a DIE PERSON GEHOERT IN DIE WORTMITTE, NICHT AN
                        # SEIN ENDE. Ismets Befund am gestempelten v227a-Render
                        # ("das Maskieren hat hier nicht gut geklappt"): von
                        # "BEHIND ME" war nur "BEHI" lesbar. Am Bild gemessen
                        # steht der Sprecher bei 0.66 W, der Block wurde aber
                        # IMMER auf die Bildmitte gesetzt (fest W/2 im
                        # Zeichenpfad) - seine Silhouette lag damit auf dem
                        # rechten Wortende und frass es am Stueck.
                        # Die Stufen (1)-(3) darueber vergleichen nur BREITEN
                        # und sind deshalb blind dafuer: das Wort war mit
                        # 2.4 x Schulterbreite klar breit genug, nur eben an
                        # der falschen Stelle. Der Referenz-Look ist ohnehin
                        # "die Person steht MITTEN im Wort" - dann bleibt
                        # links und rechts etwas stehen.
                        _bx = float(_fpv[0])
                        _halb = _tw / 2.0 + W * 0.02
                        p['bx'] = min(max(_bx, _halb), W - _halb) \
                            if _halb < W / 2 else W / 2
                        if abs(p['bx'] - W / 2) > W * 0.02:
                            print(f"  Legibility: '{txt}' centred on the "
                                  f"speaker ({p['bx'] / W:.2f} W) so the body "
                                  f"cannot eat one end")
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
                        print(f"  Variable axis: real weight ladder on '{txt}'")
                    except Exception:
                        p['_wladder'] = None
                # v143 FIX: safe_z ist nur im Hochformat wahr - im Querformat
                # stand die Nebenwort-Zeile deshalb IMMER bei 0.80 H, waehrend
                # ihr eigenes Keyword bei Z_BEHIND = 0.34 H sass. Das sind
                # 0.46 H Abstand, bei 1080p fast 500 px quer durchs Bild, und
                # der Ueberlappungs-Schutz sah es nicht (der Plan traegt als
                # vpos die Keyword-Hoehe). Jetzt haengt die Zeile an ihrem
                # Keyword, gedeckelt auf die alte Untergrenze.
                sy = (H * 0.74 if safe_z
                      else min(H * 0.80, p.get('by', Z_BEHIND) + H * 0.26))
            elif fx == 'cascade':
                max_w = int(W * (0.60 if safe_z else 0.82)) if portrait else int(W * 0.396)
                sz = S.fit(txt, int((H * 0.139 if not portrait else H * 0.085) * _ugrf), max_w, font=S.f_italic)
                arr, tw, letters = S.text(txt, sz, S.white, per_letter=True, font=S.f_italic)
                p['arr'], p['letters'] = arr, letters
                p['side'], p['cx'] = pick_side(start, end, side_toggle)
                p['cx'] = clamp_cx(p['cx'], p['arr'].shape[1])
                side_toggle += 1
                p['cy'] = v_zone(start, end) if portrait else Z_MAIN
                sy = p['cy'] + (H * 0.128 if portrait else H * 0.139)
            elif fx == 'blurin':
                sz = S.fit(txt, int((H * 0.199 if not portrait else H * 0.10) * _ugrf), int(W * (0.62 if safe_z else 0.86) if portrait else W * 0.78), tracking=6)
                p['arr'] = rot_img(S.text(txt, sz, S.white, tracking=6, extrude=S.ex)[0], p['tilt'] * 0.5)
                if p.get('count'):
                    p['builder'] = (lambda s, _sz=sz, _tl=p['tilt']:
                                    rot_img(S.text(s, _sz, S.white, tracking=6,
                                                   extrude=S.ex)[0], _tl * 0.5))
                # v143 FIX: safe_z ist nur im Hochformat wahr - im Querformat
                # stand die Nebenwort-Zeile deshalb IMMER bei 0.80 H, waehrend
                # ihr eigenes Keyword bei Z_BEHIND = 0.34 H sass. Das sind
                # 0.46 H Abstand, bei 1080p fast 500 px quer durchs Bild, und
                # der Ueberlappungs-Schutz sah es nicht (der Plan traegt als
                # vpos die Keyword-Hoehe). Jetzt haengt die Zeile an ihrem
                # Keyword, gedeckelt auf die alte Untergrenze.
                sy = (H * 0.74 if safe_z
                      else min(H * 0.80, p.get('by', Z_BEHIND) + H * 0.26))
            elif fx == 'outline':
                # v187: der Portrait-em-Deckel lag bei 0.09 H, also einer
                # Versalhoehe von 0.063 H - konstruktiv UNTER dem
                # Referenzboden 0.074 H, egal wie kurz das Wort ist.
                # Und die Safe-Zone-Breite war eine Konstante (0.60 W)
                # statt des echten Korridors. Beides gehoben; die Karte
                # laeuft ohnehin durch clamp_cx und bleibt rail-treu.
                _kx8, _kw8 = _korridor()
                max_w = (int(min(W * 0.82, _kw8)) if portrait
                         else int(W * 0.396))
                sz = S.fit(txt, int(H * 0.148) if not portrait else int(H * 0.115), max_w)
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
                # v230g: siehe _build_behind - eine gewaehlte Animation
                # schlaegt den buchstabenweisen Aufbau, sonst laeuft sie nie.
                if S.kinetic and not p.get('count') and not lying \
                        and not p.get('anim'):
                    flat, tot, lets = S.text(txt, sz, S.white, per_letter=True, extrude=g_ex)
                    p['arr'] = flat
                    p['letters'] = letter_slices(flat, lets)
                else:
                    flat = S.text(txt, sz, S.white, extrude=g_ex, flat_light=lying)[0]
                    p['arr'] = persp_warp(flat, yaw=g_yaw, pitch=g_pitch)
                    if lying or on_wall:
                        # Roh-Sprite aufheben: beim Ankern wird die Neigung der
                        # ECHTEN Flaeche gemessen und der Text neu gewarpt.
                        # v218: gilt jetzt auch fuer die WAND. Bis dahin stand
                        # dort ein fester Winkel im Wechsel (-6/+6 Grad) - mit
                        # der Wand im Bild hatte der nichts zu tun, und der
                        # Text lag davor statt darauf ("es sitzt nicht richtig
                        # an der Wand", Ismets Befund am Render).
                        p['flat_arr'] = flat
                # v221 DAS ORTSWORT LIEGT SCHON DA (Ismets Idee).
                # "Es waere ja auch eine Option, dass es schon da darauf steht.
                # Beispielsweise das Wort Wall. Und das andere baut sich drum
                # herum auf." Genau das: ab dem Anfang der Wortgruppe liegt nur
                # das ORTSWORT ('WALL') auf der Flaeche; wenn der Sprecher es
                # ausspricht, steht der ganze Satz da ('ON THE WALL').
                # Das widerspricht v214 NICHT: die KARTE erscheint weiter erst
                # zu ihrem Wort. Frueher da ist nur das Ankerwort - und es
                # verschwindet nicht vorher, genau das war der v214-Fehler.
                _aw = anker_wort(txt) if (scene_ground and not p.get('count')
                                          and not p.get('letters')) else None
                if _aw and isinstance(info, dict) and info.get('intent'):
                    _afl = S.text(_aw, sz, S.white, extrude=g_ex,
                                  flat_light=lying)[0]
                    p['anker_flat'] = _afl
                    p['anker_arr'] = persp_warp(_afl, yaw=g_yaw, pitch=g_pitch)
                    p['anker_txt'] = _aw
                    # Sichtbar ab dem SATZANFANG - dort setzt der Sprecher an
                    # ("this one sticks on the wall"), und genau dann soll das
                    # Wort schon an der Flaeche liegen. Der Gruppenanfang
                    # reicht nicht: er faellt oft mit dem Keyword zusammen,
                    # dann gaebe es gar keinen Vorlauf (am Testmaterial
                    # gemessen: anker_t0 == card_t0). Deckel 2.0 s - mehr
                    # waere ein Titel, kein Anker.
                    _satz = i
                    while (_satz > 0 and _satz > i - 12
                           and not str(words[_satz - 1].get('word', '')).rstrip()
                                   .endswith(('.', '!', '?'))):
                        _satz -= 1
                    _at = float(words[_satz].get('start', p['start']))
                    p['anker_t0'] = max(0.0, min(_at, kw_t0 - 0.25),
                                        kw_t0 - 2.0) if kw_t0 > 0.25 else 0.0
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
                    sh, sdy_, sdx_ = make_contact_shadow(p['arr'], light=light_dir)
                    if sh is not None:
                        p['cshadow'], p['csh_dy'], p['csh_dx'] = sh, sdy_, sdx_
                elif on_wall and not broll:
                    # v101i: STEHENDER Wand-Text ist ein Objekt VOR der Wand -
                    # der wirft einen weichen Kontakt-Schatten auf sie (sonst
                    # schwebt er). Dezenter als am Boden, licht-wahr versetzt.
                    sh, sdy_, sdx_ = make_contact_shadow(p['arr'], strength=0.30,
                                                         light=light_dir)
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
                    # v214: NICHT bei einer ANSAGE. "Liegt schon da" ist ein
                    # Regie-Effekt fuer Szenen-Text, den niemand angekuendigt
                    # hat - die Kamera schwenkt auf ein Wort, das in der Welt
                    # liegt. Sagt der Sprecher die Platzierung aber ANSAGT
                    # ("this one sticks on the wall"), dann ist die Karte 1.5 s
                    # vor seinem Satz schlicht falsch: er zeigt auf etwas, das
                    # laengst steht, und wenn er es ausspricht, ist es weg.
                    # Genau das stand in Ismets Job-Log (Karte 8.18 s, Satz
                    # ab 9.08 s).
                    if not p.get('intent'):
                        p['start'] = max(p['start'] - 1.5, 0.0)
            # v81e: Emoji ins Sprite backen. Nur einfache Ein-Array-Effekte
            # (behind/cascade/blurin/ground). 'outline' hat zwei Layer + Zaehler
            # bauen live -> dort bewusst kein Emoji, um Regression zu vermeiden.
            if p.get('emoji') and 'arr' in p and not p.get('count') \
                    and not p.get('letters') and not p.get('tokens'):
                try:
                    p['arr'] = bake_emoji(p['arr'], p['emoji'])
                except Exception as _e:
                    print(f"  Emoji skipped ({type(_e).__name__})")
            p['target'] = (p.get('cx', W / 2), p.get('cy', p.get('by', H * 0.398)))
            # v143: vpos deckt Keyword UND Nebenwort-Zeile ab. Vorher trug der
            # Plan nur die Keyword-Hoehe; eine Nebenwort-Zeile weit darunter
            # war fuer resolve_overlaps unsichtbar und konnte ungestraft mit
            # einer Flow-Caption kollidieren.
            _vy = p.get('cy', p.get('by', H * 0.398))
            if small:
                _vy = (_vy + sy) / 2.0
            p['vpos'] = (p.get('cx', W / 2), _vy)
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
                    print("  Climax variation: motion broken up")
                big_used.add(_sig)
            plans.append(p)
        elif cfg['effects'].get('caption_flow', True):
            # v97 Flow-Caption (Referenz-Look): Chunk baut sich INLINE auf,
            # Anker-Wort gross+getippt+Glow, Abschlusswort kursiv-Akzent.
            # v143: freie Breite VOR dem Setzen bestimmen. Steht die Person
            # seitlich oder fuellt sie das Bild, liefert _freie_breite eine
            # schmalere Spalte; der Block wird dann hoeher und schmaler und
            # findet neben dem Kopf Platz.
            # v150 ABWECHSLUNG (Ismets Befund: 'zu monoton'). Bis v149 bekam
            # JEDER Filler-Chunk dasselbe linksbuendige Zeilenraster - drei
            # Zeilen, gleiche Kante, gleiche Groessen. Ueber ein ganzes Video
            # sah damit jeder Moment gleich aus.
            # Jetzt wechseln sich zwei Anordnungen ab: das gewohnte Zeilen-
            # Layout und die COLLAGE (Woerter in eigener Groesse ueber die
            # Flaeche verteilt). Der Wechsel ist deterministisch aus dem
            # ersten Wort-Index - reproduzierbar ueber Re-Renders, aber ohne
            # sichtbares Muster - und die Collage braucht genug Woerter,
            # sonst hat sie nichts zu verteilen. 'clean' bleibt aussen vor,
            # dort ist Schlichtheit das gewollte Ergebnis.
            # v153: der Nutzer kann die Anordnung festlegen. 'auto' laesst
            # die Regie wechseln (Standard), 'rows'/'collage' erzwingen eine.
            _lm = str(cfg['effects'].get('caption_layout') or 'auto').lower()
            # v183 RIEGEL an der immer laufenden Stelle (v159-Lehre): der
            _lay = 'flow'
            # v187: die Spalte wird am Plattform-Korridor gedeckelt, nicht
            # mehr nur bei einer Nahaufnahme verengt. Ohne das erreichte die
            # Maske compose_flow nie (auf B-Roll gibt _freie_breite None).
            _kx0, _kbw = _korridor()
            _cw150 = _freie_breite(start, end)
            # Bei verengter Spalte (Nahaufnahme, Person fuellt das Bild)
            # bleibt es beim Zeilensatz. Die Collage staffelt nach RECHTS -
            # in einer schmalen Spalte hat sie dafuer keinen Platz und
            # draengte den Block unter den Kopf, statt neben ihn.
            # Drei Woerter reichen: die Chunk-Bildung liefert im Regelfall
            # 2 bis 4 (words_per_group). Mit der Schwelle 4 lief die Collage
            # im echten Render gemessen KEIN EINZIGES Mal an - der Beweis-
            # Streifen zeigte acht Mal dasselbe Zeilenraster.
            if _lm != 'rows' and len(g) >= 3 \
                    and str(cfg.get('look', '')).lower() != 'clean' \
                    and cfg['effects'].get('caption_collage', True) \
                    and not _cw150 \
                    and (_lm == 'collage' or _mix01(g[0] * 3) >= 0.42):
                _lay = 'collage'
            # v152 SATZWEISE COLLAGE. Im Vorbild bleibt der GANZE SATZ stehen
            # und waechst ueber rund zwei Sekunden zu einem Bild; bei uns
            # wurde er chunkweise ausgetauscht. Die Collage zieht deshalb die
            # folgenden Gruppen desselben Satzes mit herein.
            # Die Chunk-Bildung selbst bleibt unangetastet - sie steuert
            # Dichte, Tempo-Kurve und Pointen-Isolierung, und daran zu drehen
            # haette Nebenwirkungen bis in die Kamera. Geschluckte Woerter
            # laufen ueber 'used', denselben Weg, den Phrasen schon nutzen.
            # v153 SEITENWECHSEL. Ismets Befund: "Captions sind immer auf
            # einer Seite." Das stimmte - x0 war fest W*0.07, jede Caption
            # klebte an der linken Kante. Die Seite wechselt jetzt
            # deterministisch aus dem ersten Wort-Index; hat der Nutzer (oder
            # eine gemessene Referenz) eine Ausrichtung vorgegeben, gilt die.
            # v155 ZWEI VERSCHIEDENE DINGE, die v153 in einen Schalter warf:
            #  BUENDIGKEIT - stehen die Zeilen linksbuendig zueinander? Das
            #    misst die Referenz ('ausrichtung'), und das gehoert zum Stil.
            #  BILDSEITE   - sitzt der Block links oder rechts im Frame? Das
            #    soll variieren, sonst klebt alles an einer Kante.
            # Bis v154 setzte eine Referenz mit 'links' beides - Ismets
            # Konto hatte genau so eine gelernt, und deshalb sass bei ihm
            # weiterhin JEDE Caption links, obwohl die Variation im Code
            # laengst lief. Die Bildseite hoert jetzt nur noch auf die
            # ausdrueckliche Nutzerwahl (caption_seite), nie auf die Messung.
            _bd = str(cfg['effects'].get('caption_align') or 'auto').lower()
            _buendig = ('links' if _bd in ('links', 'left')
                        else ('rechts' if _bd in ('rechts', 'right')
                              else ('mitte' if _bd in ('mitte', 'center',
                                                       'centre') else None)))
            _sw = str(cfg['effects'].get('caption_seite') or 'auto').lower()
            if _sw in ('links', 'left'):
                _seite = 'links'
            elif _sw in ('rechts', 'right'):
                _seite = 'rechts'
            elif _sw in ('mitte', 'center', 'centre'):
                _seite = 'mitte'
            elif not portrait:
                # v180 QUERFORMAT STEHT MITTIG. Die Seiten-Abwechslung aus
                # v168 war gegen "immer links" im HOCHFORMAT gebaut und lief
                # als Nebeneffekt auch bei 16:9 - dort ist sie falsch:
                #  - Konvention fuer eingebrannten Text im Querformat ist
                #    unten MITTIG (Netflix TTSG, BBC-Subtitle-Guidelines,
                #    SMPTE Title-Safe). Links/rechts geparkt ist die Sprache
                #    von Lower-Third-Namensgrafiken, nicht von Sprechtext.
                #  - 16:9 hat wenig Hoehe, die Person sitzt fast immer
                #    mittig - seitlicher Text rutscht an den unruhigen Rand.
                #  - Im Querformat ruht der Blick mittig; wechselnde Seiten
                #    zwingen den Zuschauer, den Text zu suchen.
                # Ausweichen bleibt trotzdem moeglich: spot() darf den Block
                # weiterhin zur Seite schieben, wenn dort das MOTIV steht -
                # 'mitte' ist der Wunsch, keine Fessel. Zeige-Ziel,
                # Hand-Geste und Sprecherwechsel ueberstimmen ihn ohnehin.
                _seite = 'mitte'
            else:
                # v168 ECHTER WECHSEL statt Wuerfeln (Ismets Befund, dritter
                # Anlauf: "die captions sind immer auf der linken seite,
                # egal was passiert"). Der alte Wurf _mix01(g0*11) >= 0.55
                # war pro Chunk unabhaengig: nur ~40-45 % rechts, der erste
                # Chunk IMMER links (_mix01(0) = 0.0), und auf typischen
                # Chunk-Ketten gemessen 3 von 12 rechts - lange Links-Ketten
                # waren der Normalfall, keine Ausnahme. Ein Wuerfel pro
                # Block garantiert keine Abwechslung.
                # Jetzt traegt spot_state die Seite: jeder neue Block
                # WECHSELT, rund jeder vierte bleibt deterministisch stehen
                # (Naturlichkeit, kein Pingpong-Metronom). Startseite haengt
                # am Video-Seed, nicht fest an links. Re-Render ergibt
                # dasselbe Bild.
                _lauf = spot_state.get('seite_lauf')
                if _lauf is None:
                    _lauf = 'rechts' if _mix01(_seed ^ 0x9E37) >= 0.5 else 'links'
                elif _mix01(g[0] * 11 + 7) >= 0.28:
                    _lauf = 'links' if _lauf == 'rechts' else 'rechts'
                spot_state['seite_lauf'] = _lauf
                _seite = _lauf
            # Die gemessene Buendigkeit gilt fuer den SATZ, nicht fuer die
            # Bildseite. 'mitte' ist die einzige, die beides festlegt - ein
            # zentrierter Satz an der Bildkante saehe nach Fehler aus.
            #
            # v156: und sie gilt als TENDENZ, nicht als Zwang. Ismets Einwand:
            # "Das Video war aber auch nicht so, dass da staendig die Captions
            # auf der linken Seite waren." Stimmt - auch ein Vorbild, dessen
            # linke Kanten im Schnitt weniger streuen, setzt einzelne Bloecke
            # anders. Ein gemessenes 'links' auf ALLE Chunks anzuwenden macht
            # Rund die HAELFTE folgt deshalb der Bildseite statt der Messung;
            # welche, ist deterministisch. Mit einem Drittel (Schwelle 0.66)
            # wechselte im echten Render nur EIN Block von sechs.
            # Nutzerwahl und 'mitte' bleiben absolut - wer im Regler links
            # sagt, meint links.
            if _buendig in ('links', 'rechts') and _sw == 'auto' \
                    and _mix01(g[0] * 23) >= 0.50:
                _buendig = None
            _bnd = _buendig or _seite
            if _buendig == 'mitte':
                _seite = 'mitte'
            _g_vor, _g_kurz = list(g), None
            # v193: die satzweise Collage legt zwei Chunks zu EINEM Block
            # zusammen. Bei einer Nutzer-Aufteilung ist genau das verboten -
            # der Editor zeigt zwei Zeilen, das Video zeigte sonst eine.
            # Wer zusammenlegen will, tut das im Editor.
            if _lay == 'collage' and not _ublk \
                    and cfg['effects'].get('caption_satz_collage', True) \
                    and hat_interpunktion:
                _erw, _gj = list(g), gi + 1
                while (_gj < len(groups) and len(_erw) < 8
                       and not str(words[_erw[-1]]['word']).rstrip().endswith(
                           ('.', '!', '?'))):
                    _nx = [i for i in groups[_gj] if i not in used]
                    if not _nx:
                        break
                    # Nur direkt anschliessend, nur im selben Bildzustand, und
                    # NIE ueber ein Keyword hinweg: der grosse Moment gehoert
                    # ihm allein, er darf nicht in einer Collage verschwinden.
                    if words[_nx[0]]['start'] - words[_erw[-1]]['end'] > 0.60:
                        break
                    if any(i in kw for i in _nx):
                        break
                    if (not face_ok(words[_nx[0]]['start'],
                                    words[_nx[-1]]['end'])) != broll:
                        break
                    _erw += _nx
                    _gj += 1
                if len(_erw) > len(g):
                    for _i in _erw[len(g):]:
                        used.add(_i)
                    g = _erw
                    end = words[g[-1]]['end']
                    next_start = (g_starts[_gj] if _gj < len(groups) else 1e9)
                    _g_kurz = list(_g_vor)
            # SATZENDE: nur dort darf das Schluesselwort auf Knall-Groesse.
            _punch = bool(str(words[g[-1]]['word']).rstrip().endswith(('.', '!', '?')))
            # v193: Nutzer-Groesse und Nutzer-Text dieses Blocks. Beides muss
            # an ALLE vier compose_flow-Aufrufe - der Rueckfall auf Zeilensatz
            # und das Luecken-Netz bauen den Block sonst ohne die Einstellung
            # neu, und die Nutzerwahl waere je nach Layout mal da, mal weg.
            _ugr = (_ublk or {}).get('groesse')
            _utx, _usicht = block_texte(_ublk, g, words)
            if _utx and _usicht and len(_usicht) < len(g):
                g = _usicht
                end = words[g[-1]]['end']
            items, tot_h, anchor_i = compose_flow(g, words, S, W, H, portrait, loud=loud,
                                                  flow_sel=(flow_map or {}).get(g[0]),
                                                  colw=_cw150, maxw=_kbw,
                                                  layout=_lay, punch=_punch,
                                                  seite=_bnd,
                                                  groesse=_ugr, texte=_utx)
            # Die Collage baut in die HOEHE. Wird sie zu hoch, passt sie an
            # keinem Kopf mehr vorbei und die Platzierungs-Regie muesste sie
            # in den Bildrand druecken - dann ist das gewohnte Zeilenraster
            # die bessere Wahl. Gemessen: ein 10-Wort-Chunk ergibt 0.47 H,
            # ein normaler 4-Wort-Chunk bleibt klar darunter.
            if _lay == 'collage' and tot_h > H * 0.40 and _g_kurz:
                # Der ganze Satz passt nicht: erst die Erweiterung
                # zurueckdrehen, nicht gleich das Layout. Ein 8-Wort-Chunk im
                # Zeilensatz waere schlechter als eine kurze Collage.
                for _i in g[len(_g_kurz):]:
                    used.discard(_i)
                g = _g_kurz
                end = words[g[-1]]['end']
                next_start = (g_starts[gi + 1] if gi + 1 < len(groups) else 1e9)
                _punch = bool(str(words[g[-1]]['word']).rstrip()
                              .endswith(('.', '!', '?')))
                items, tot_h, anchor_i = compose_flow(
                    g, words, S, W, H, portrait, loud=loud,
                    flow_sel=(flow_map or {}).get(g[0]),
                    colw=_cw150, maxw=_kbw, layout='collage', punch=_punch,
                    seite=_bnd, groesse=_ugr, texte=_utx)
            if _lay == 'collage' and tot_h > H * 0.40:
                _lay = 'flow'
                items, tot_h, anchor_i = compose_flow(
                    g, words, S, W, H, portrait, loud=loud,
                    flow_sel=(flow_map or {}).get(g[0]),
                    colw=_cw150, maxw=_kbw, layout='flow', punch=_punch,
                    seite=_bnd, groesse=_ugr, texte=_utx)
            # v143: Position kommt aus der Platzierungs-Regie statt aus einer
            # Konstanten. Wunschzone = wo der Block AM LIEBSTEN sitzt; spot()
            # weicht davon ab, wenn dort ein Gesicht oder ein unruhiger
            # Bildbereich liegt. Hochformat 0.25 H entspricht der gemessenen
            # Referenzzone (Block 0.14-0.36 H, ueber dem Kopf); Querformat
            # bleibt beim Lower Third, weil 16:9 auf breiten Schirmen laeuft.
            # Vorher: y0 fest H*0.13 bzw. Z_MAIN, x fest W*0.07 - der Block
            # stand bei JEDER Kadrierung an derselben Stelle.
            # v143: SICHTBARE Ausdehnung messen, nicht die Vorschubweite.
            # Gezeichnet wird das Sprite inklusive Leuchten; mit adv gerechnet
            # ragte der Block gemessen bis 0.963 W und riss den Title-Safe-Rand.
            def _ink_x(_it):
                _a = _it.get('arr')
                if _a is None:
                    _h = _it.get('adv', _it.get('w', 0)) / 2.0
                    return (_it['cx'] - _h, _it['cx'] + _h)
                # v181: die KONTUR ist ein Rand-Bleed, keine Layout-Breite.
                # Gemessen wird der GLYPHENKOERPER (deckend UND hell), damit
                # der dunkle Saum die Blockbreite nicht aufblaeht. Ein
                # dunkler Caption-Ton (heller Untergrund) traegt keine
                # Kontur - dort greift die Alpha-Schwelle wie bisher.
                # EHRLICHE GRENZE: das entfernt den Saum nicht restlos, die
                # Antialiasing-Kante zwischen Glyphe und Kontur bleibt.
                # Rest-Unterschied gemessen: 0.003 W.
                _al = _a[..., 3] > 80
                _hell = _al & (_a[..., :3].max(axis=2) > 150)
                _c = np.where(_hell if _hell.any() else _al)[1]
                if not len(_c):
                    return (_it['cx'], _it['cx'])
                _o = _it['cx'] - _a.shape[1] / 2.0
                return (_o + float(_c.min()), _o + float(_c.max()))
            # v152: ein randabfallendes Schlusswort darf die Blockbreite
            # NICHT bestimmen. Sonst meldet der Block 1.22 W, die
            # Platzierungs-Regie findet dafuer nirgends Platz und schiebt
            # den ganzen Satz aus dem Bild.
            _spans = [_ink_x(it) for it in items if not it.get('bleed')]
            if not _spans:
                _spans = [_ink_x(it) for it in items]
            _bl = min(sp[0] for sp in _spans)
            _br = max(sp[1] for sp in _spans)
            # v144: die Wunschzone kann aus einer gemessenen Referenz kommen.
            # 0.25 hoch / 0.72 quer sind die Standardwerte; hat der Kunde ein
            # Referenzvideo angelernt, sitzt sie dort, wo das Vorbild sie hat.
            _cz = cfg['effects'].get('caption_zone')
            _wunsch = (H * float(_cz) if _cz
                       else H * (0.25 if portrait else 0.72))
            # Wunsch-x aus der gewaehlten Seite. 'mitte' bleibt mittig,
            # links/rechts ziehen den Block an die jeweilige Kante - die
            # Gesichts- und Unruhe-Kosten koennen ihn davon abbringen.
            _wx = None
            if _seite == 'links':
                _wx = W * 0.30
            elif _seite == 'rechts':
                _wx = W * 0.70
            elif _seite == 'mitte':
                _wx = W * 0.50
            # Ein SEITENWECHSEL muss die Hysterese durchbrechen. Sie ist
            # dafuer da, Zittern durch schwankende Gesichtserkennung zu
            # verhindern (v143) - ein bewusster Wechsel der Seite ist aber
            # kein Zittern, sondern die Regie. Ohne dieses 'kalt' blieb der
            # Block gemessen bei JEDEM Chunk links, obwohl die Seite wechselte.
            # v160: ein Zeige-Ziel ist ebenfalls ein bewusster Wechsel, kein
            # Zittern. Ohne 'kalt' haette die Hysterese den Block an der alten
            # Stelle festgehalten und die Geste waere folgenlos geblieben.
            _zl = ziel_at(start, end)
            # v162: bei mehreren Personen zieht die Wunschseite zum aktiven
            # Sprecher statt zur deterministischen Wechsel-Seite. Ein
            # SPRECHERWECHSEL muss die Hysterese brechen - genau wie ein
            # Seitenwechsel, aus demselben Grund: er ist Regie, kein Zittern.
            _spx = sprecher_at(start, end)
            _kalt = (_shot_neu(start) or (spot_state.get('seite') != _seite)
                     or (_zl is not None) != bool(spot_state.get('zeig'))
                     or (_spx is not None
                         and abs(_spx - (spot_state.get('spr') or _spx)) > W * 0.02))
            spot_state['seite'] = _seite
            spot_state['zeig'] = _zl is not None
            spot_state['spr'] = _spx
            _sx, _sy = spot(start, end, _br - _bl, tot_h,
                            wunsch_y=_wunsch, kalt=_kalt,
                            wunsch_x=_wx,
                            ziel=(_zl[:2] if _zl is not None else None),
                            sprecher=(_spx if _zl is None else None))
            if os.environ.get('DVE_DBG_SPOT'):
                print('DBGSPOT t=%.2f g0=%s side=%s wx=%s cold=%s bl=%.3f br=%.3f -> sx=%.3f'
                      % (start, g[0] if g else -1, _seite, _wx, _kalt,
                         _bl / W, _br / W, _sx / W))
            _dx = _sx - _bl
            for it in items:
                it['cx'] += _dx
                it['cy'] += _sy
            # Das randabfallende Wort wird auf die BILDMITTE zentriert -
            # der Anschnitt soll links und rechts gleich viel wegnehmen.
            for it in items:
                if it.get('bleed'):
                    it['cx'] = W / 2.0
            y0 = _sy
            # v143: der Kamera-Follow schiebt den Block zur Laufzeit. Die
            # Planung war korrekt und das FERTIGE Bild trotzdem bei 0.961 W -
            # gemessen im echten Render. Statt die Platzierungsflaeche zu
            # verkleinern (das schoebe den Block nur nach rechts), bekommt der
            # Follow hier seinen tatsaechlich vorhandenen Spielraum mit.
            _rnd = W * 0.05 + 8
            _fol_lim = max(0.0, min(W * 0.045,
                                    _sx - _rnd,
                                    (W - _rnd) - (_sx + (_br - _bl))))
            # v97d: KEINE Seiten-/Cap-Zoom-Fahrt auf Filler-Flow. Die zog frueher
            # zur alten Stack-Seite bzw. zum Ziel (W*0.07, zc) = leerer linker
            # Rand auf halber Hoehe -> "Zoom ins Leere", entkoppelt von der oben
            # verankerten Caption. Filler bleibt ruhig (wie die Referenz); die
            # dramatischen Keyword-Momente behalten ihre Kamera.
            sp = {'tpl': 'flow', 'front': items, 'start': start, 'end': end,
                  'layout': _lay, 'punch': _punch,
                  'side': 0, 'ccam': 'none',
                  'target': (int(_sx), int(y0 + tot_h / 2.0)),
                  'fol_lim': _fol_lim,
                  'broll': broll,
                  # v184: die Punchline darf HINTER der Person stehen
                  # (Referenz-Grammatik, Ref C 'this'). Nur am Satzende,
                  # nie auf B-Roll, nie bei angesagtem Hand-Schub - und
                  # sichtbar wird es ohnehin nur, wo die Person das Wort
                  # wirklich ueberlappt (occlude_sprite tastet die Maske ab).
                  'hinter_ok': bool(_punch and not broll),
                  # v177: Sagt der Satz, dass die Hand die Captions schiebt?
                  # Dann darf eine gemessene Wisch-Bewegung den Block auch
                  # OHNE Pixel-Beruehrung stossen - siehe hand_contacts.
                  '_hand_geste': any(_hand_aktion_hit(clean(words[j]['word']))
                                     for j in g)}
            if sp.get('_hand_geste'):
                sp['hinter_ok'] = False
            # v193: Nutzer-Block. Das Flag schuetzt den Block in der
            # Nachbearbeitung (Solo-Riegel, Schnitt-Disziplin, Zeiten) und
            # traegt die Animation, die es bis v192 fuer Fliess-Bloecke gar
            # nicht gab.
            if _ublk:
                sp['_user'] = True
                if _ublk.get('anim'):
                    sp['anim'] = _ublk['anim']
                if _ublk.get('power'):
                    sp['power'] = int(_ublk['power'])
                if _ublk.get('start') is not None:
                    sp['_user_t'] = True
            # v141: echte Textposition fuer den Ueberlappungs-Schutz. 'target'
            # bleibt das Kamera-Ziel - die beiden duerfen nicht verwechselt
            # werden, sonst zieht die Kamera wieder in die Bildmitte.
            _fcx = [it.get('cx') for it in items if it.get('cx') is not None]
            sp['vpos'] = (sum(_fcx) / len(_fcx) if _fcx else W / 2.0,
                          y0 + tot_h / 2.0)
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

    # ---------------------------------------------------------- v185 LUECKEN
    # SICHERHEITSNETZ bei Dichte 'durchgehend': dort ist "jedes gesprochene
    # Wort steht irgendwann auf dem Schirm" eine Zusage, kein Stil. Mehrere
    # Wege koennen Woerter verschlucken (Keyword-Moment zeigt nur EIN Wort
    # seiner Gruppe, B-Roll-Gate, Zahl-Bremse, Ein-Wort-Rest). Statt jeden
    # einzelnen Weg zu flicken, wird am Ende geprueft, WAS fehlt, und der
    # Rest bekommt eine schlichte Flow-Caption.
    # v221 GILT JETZT AUCH FUER 'akzente' (Ismets Ansage, am Render gemessen).
    # Bis v220 lief das Netz nur bei 'durchgehend', weil Textpausen in
    # 'akzente' als gewollte Handschrift galten. Am 15-Sekunden-Werbespot
    # gemessen war das keine Handschrift, sondern ein Loch: 45 % der Laufzeit
    # OHNE jeden Text, einzelne Pausen bis 1.17 s, waehrend durchgehend
    # gesprochen wird. Ismets Urteil: "fuehlt sich 0 fluessig an" - und er
    # hat recht, ein Untertitel, der jede Sekunde verschwindet und wiederkommt,
    # stockt. 'sparsam' bleibt bewusst ruhig; DORT ist die Pause der Stil.
    # v193: Bei einer Nutzer-Aufteilung ist das Netz aus. Wer einen Block
    # abschaltet oder ein Wort aus einer Zeile loescht, sagt "hier soll nichts
    # stehen" - das Netz wuerde es kommentarlos wieder hinstellen und die
    # Loeschung waere wirkungslos. Die Zusage 'jedes Wort' gilt fuer die
    # AUTOMATIK, nicht gegen eine Entscheidung.
    if str(cfg['effects'].get('density', 'akzente')) in ('durchgehend', 'akzente') \
            and words and not _bl_akt:
        _gezeigt = set()
        for _p in plans:
            for _k in ('front', 'small'):
                for _it in (_p.get(_k) or []):
                    if isinstance(_it, dict) and _it.get('i') is not None:
                        _gezeigt.add(_it['i'])
            if _p.get('kw_i') is not None:
                _gezeigt.add(_p['kw_i'])
        _fehlt = [i for i in range(len(words)) if i not in _gezeigt
                  and clean(words[i]['word']).strip()]
        # Zu Laeufen buendeln: nur zusammenhaengende Woerter ohne grosse
        # Sprechpause dazwischen ergeben einen lesbaren Block.
        _laeufe, _cur = [], []
        for i in _fehlt:
            if _cur and (i != _cur[-1] + 1
                         or words[i]['start'] - words[_cur[-1]]['end'] > 0.7):
                _laeufe.append(_cur)
                _cur = []
            _cur.append(i)
        if _cur:
            _laeufe.append(_cur)
        _nach = 0
        for _lauf in _laeufe:
            _s0 = words[_lauf[0]]['start']
            _e0 = words[_lauf[-1]]['end']
            # v170 BLEIBT GUELTIG: ein einzelnes kurzes Wort nach langer
            # Pause ist ein Rest, kein Moment (Ismets "is" am Videoende).
            # Das Netz darf ihn nicht durch die Hintertuer zurueckholen.
            _i0 = _lauf[0]
            _pv = (_s0 - words[_i0 - 1]['end']) if _i0 > 0 else 9.0
            if (len(_lauf) == 1 and len(clean(words[_i0]['word'])) <= 4
                    and _pv >= 1.2):
                continue
            if not face_ok(_s0, _e0) and not cfg['effects'].get('broll_captions', False):
                continue                     # B-Roll bleibt textfrei
            # v221b DAS NETZ FUELLT NUR LEERE ZEIT, KEINE KARTEN-FENSTER.
            # Ohne diesen Riegel war die Umstellung auf 'akzente' ein
            # Rueckschritt: das Netz legte Bloecke IN die Standzeit einer
            # Keyword-Karte, der Solo-Riegel raeumte daraufhin die Karte weg,
            # und die Ansagen standen nur noch 0.2 s im Bild - genau Ismets
            # Befund "eine Millisekunde da", nur schlimmer. Waehrend einer
            # Karte ist das Bild NICHT leer; dort fehlt kein Text.
            _kwf = [(card_t0(_q, words), _q['end'] + 0.40) for _q in plans
                    if _q.get('kw_i') is not None and 'target' in _q]
            if any(_s0 < _kb and _e0 > _ka for _ka, _kb in _kwf):
                continue
            S.set_palette(palette_at(_s0 + 0.2) if palette_at else None)
            _it2, _th2, _an2 = compose_flow(_lauf, words, S, W, H, portrait,
                                            layout='flow', punch=False,
                                            seite='mitte')
            _cz2 = cfg['effects'].get('caption_zone')
            _wy2 = (H * float(_cz2) if _cz2 else H * (0.25 if portrait else 0.72))
            _bl2 = min(i2['cx'] - i2['w'] / 2.0 for i2 in _it2)
            _br2 = max(i2['cx'] + i2['w'] / 2.0 for i2 in _it2)
            _sx2, _sy2 = spot(_s0, _e0, _br2 - _bl2, _th2, wunsch_y=_wy2,
                              kalt=True, wunsch_x=W * 0.5)
            for i2 in _it2:
                i2['cx'] += _sx2 - _bl2
                i2['cy'] += _sy2
            plans.append({'tpl': 'flow', 'front': _it2, 'start': _s0,
                          'end': _e0, 'layout': 'flow', 'punch': False,
                          'side': 0, 'ccam': 'none', 'broll': False,
                          'target': (int(_sx2), int(_sy2 + _th2 / 2.0)),
                          'fol_lim': 0.0,
                          'hinter_ok': False,
                          'vpos': (_sx2 + (_br2 - _bl2) / 2.0, _sy2 + _th2 / 2.0)})
            _nach += len(_lauf)
        if _nach:
            print(f"  Gap guard: {_nach} spoken word(s) had no caption, added")

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
                 and not p.get('intent')          # v214: Ansage bleibt an ihrem Wort
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
                print(f"  Instant hook: '{best['kw_txt']}' steht ab Frame 1 "
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
            print(f"  Watchtime: {skipped} camera impulse(s) on B-roll skipped")
        if extra:
            n_h = sum(1 for x in extra if x['start'] < hook_pi)
            print(f"  Watchtime: {len(extra)} camera impulse(s) in quiet passages"
                  + (f", of those {n_h} on the hook beat" if n_h else ""))
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
            print(f"  Crash zoom on the strongest moment: "
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
            print(f"  Whip pan at {n_whip} section boundary/boundaries")

    # v88: Kein Doppelbild - generalisiert ueber ALLE Text-Momente (siehe
    # resolve_overlaps). Laeuft NACH dem Hook (der t0 auf 0 zieht), damit die
    # Hook-Karte in der Ueberlappungs-Pruefung mitgezaehlt wird.
    _n_ovl = resolve_overlaps(plans, W, H)
    if _n_ovl:
        print(f"  Overlap guard: {_n_ovl} moment(s) pulled forward")

    # v185 EIN MOMENT, EIN BILD. resolve_overlaps raeumt nur auf, wenn zwei
    # Texte AN DERSELBEN STELLE stehen - eine Keyword-Karte oben und ein
    # Flow-Block unten galten als saubere Neben-Platzierung. Am echten Render
    # sah das so aus: BEHIND, Me, RIGHT, WORDS und THESE FORM gleichzeitig,
    # in vier verschiedenen Schriftschnitten. Fuenf Elemente sind kein Layout,
    # das ist ein Stapel. In ALLEN Referenzen (Ismets drei TikToks und das
    # lolo-Video) traegt ein grosser Moment das Bild ALLEIN.
    # Regel: solange eine Keyword-Karte steht, raeumt jeder andere Textplan.
    # Der frueher gestartete wird beendet, der spaeter startende faengt erst
    # nach der Karte an. Kein Plan wird geloescht - Woerter gehen nicht
    # verloren, das Luecken-Netz oben bleibt gueltig.
    # v215 GERECHNET WIRD AB DEM ERSCHEINEN DER KARTE, NICHT AB p['start'].
    # p['start'] ist der Anfang der WORTGRUPPE - dort setzen nur die kleinen
    # Nebenwoerter ein; die grosse Karte kommt erst mit ihrem eigenen Wort
    # (jeder Zeichen-Zweig rechnet mit `t - p.get('t0', words[kw_i]['start'])`
    # und ueberspringt negative Werte). Der Riegel glaubte einer Karte deshalb
    # eine Lesezeit, die sie gar nicht hatte: am Testmaterial stand 'CAPTIONS'
    # auf dem Papier 1.06-1.86, im Bild 1.59-1.86 - 0.27 s statt der hier
    # garantierten 0.80 s, also genau das Blinzeln, das _KW_MIN verhindern
    # soll. Dieselbe Verwechslung wie bei der Ansage (v214).
    if cfg['effects'].get('caption_solo', True):
        def _ct0(p):
            return card_t0(p, words)
        _kwp = sorted([p for p in plans if p.get('kw_i') is not None
                       and 'target' in p], key=_ct0)
        _txt = sorted([p for p in plans if 'target' in p and p.get('front')],
                      key=_ct0)
        _n_solo = 0
        # Die KARTE hat Vorrang, nicht der Fliesstext: sie ist der dramatische
        # Moment und braucht Lesezeit. Unter 0.8 s ist ein grosses Wort nicht
        # gelesen, sondern geblinzelt - deshalb weicht der Flow, nicht sie.
        # Erst wenn die Karte ihre Mindestzeit hat, darf sie selbst kuerzen.
        # v185b GERECHNET WIRD MIT DEM AUSKLINGEN, NICHT MIT DEM ENDE. Ein
        # Plan bleibt nach 'end' noch 0.40 s im Bild (Exit-Fenster, siehe
        # 'active' in der Zeichenschleife). Mit dem blossen Ende gerechnet
        # sagten die Zahlen "keine Ueberschneidung", waehrend das Bild eine
        # zeigte: die ZEIG-Karte stand bis 1.2 s, der Block wuchs ab 0.81 s
        # darueber, 'WIR' lag auf 'ZEIG' (am Render Frame fuer Frame belegt).
        _AUS = 0.40
        _KW_MIN = 0.80
        # v215: so lange muss ein wartender Fliesstext-Block danach noch
        # stehen, sonst gibt die Karte nach. Knapp unter der Lesezeit einer
        # Karte: der Block traegt mehr Woerter, aber in kleinerer Schrift -
        # und er ist der Text, den der Sprecher gerade sagt.
        _FLOW_MIN = 0.55
        for _k in _kwp:
            _ks = _ct0(_k)
            for _b in _txt:
                _bs = _ct0(_b)
                _ke = _k['end']
                if _bs >= _ke + _AUS or _b['end'] + _AUS <= _ks:
                    continue                     # wirklich keine Ueberschneidung
                if _bs <= _ks:
                    # Der Block laeuft schon: er raeumt VOR der Karte, sein
                    # Ausklingen muss dafuer ebenfalls fertig sein.
                    _neu = max(_bs + 0.25, _ks - _AUS)
                    # v187: aber NICHT, bevor sein eigenes letztes Wort
                    # ueberhaupt eingesetzt hat. Vorher wurde nur mit den
                    # Startzeiten gerechnet; gemessen erschien 'heute'
                    # (Wortzeit 0.80) erst waehrend der Ausblende eines auf
                    # 0.68 gekuerzten Blocks - nie voll deckend. Die Karte
                    # hat Vorrang bei der Lesezeit, aber nicht das Recht,
                    # das Schlusswort des Vorgaengers zu verschlucken.
                    _letzt = max((it.get('t', _bs)
                                  for it in (_b.get('front') or [])),
                                 default=_bs)
                    if _neu < _letzt + 0.25:
                        _spaet = max(_ks, _letzt + 0.25)
                        if _spaet > _ks + 1e-3 and _spaet < _k['end'] - 0.30:
                            _k['t0'] = _k['start'] = _ks = _spaet
                            _n_solo += 1
                        _neu = max(_neu, min(_letzt + 0.25, _ks - 0.05))
                    if _neu < _b['end'] - 1e-3:
                        _b['end'] = _neu
                        _n_solo += 1
                    continue
                # Der Block will waehrend der Karte starten. Die Karte hat
                # Vorrang bis zu ihrer Mindestlesezeit; darueber hinaus
                # raeumt sie. Reicht das nicht, wartet der Block.
                _ke_soll = max(_ks + _KW_MIN, min(_ke, _bs - _AUS))
                if _ke_soll < _ke - 1e-3:
                    _k['end'] = _ke = _ke_soll
                    _n_solo += 1
                if _bs < _ke + _AUS:
                    _spaet = _ke + _AUS
                    # v215 WARTEN DARF DEN BLOCK NICHT SELBST ZUM BLINZELN
                    # MACHEN. Die Schranke stand auf 0.20 s - das ist kein
                    # Lesen, das ist ein Aufblitzen, und ein Fliesstext-Block
                    # traegt die GESPROCHENEN Woerter. Mit der korrigierten
                    # Messung oben wurde genau das messbar: die Karte bekam
                    # ihre 0.80 s, der folgende Block sank auf 0.27 s - ein
                    # Blinzeln gegen ein anderes getauscht. Ab _FLOW_MIN
                    # raeumt die Karte, statt den Block kaputtzuschieben.
                    # Der Block wird dabei NIE beschnitten: seine Woerter
                    # gehen nicht verloren, nur die Karte gibt nach.
                    # v221b: bei einer ANSAGE gibt die Karte NICHT nach. Sie
                    # ist woertlich bestellt ("this one sticks on the wall") -
                    # dass sie ihre Lesezeit behaelt, ist die ganze Zusage des
                    # intent-Flags. Der Fliesstext wartet dann eben laenger.
                    # v230g EIN BLOCK DARF NIE HINTER SEIN EIGENES ENDE.
                    # Der intent-Zweig umging die _FLOW_MIN-Pruefung KOMPLETT
                    # und setzte den Start ohne jede Obergrenze. War das Ende
                    # des Blocks vorher schon gekuerzt worden (frueherer
                    # Riegel oder resolve_overlaps), landete der Start HINTER
                    # dem Ende - das Anzeigefenster ist dann leer und der
                    # Block kommt in KEINEM Bild vor. Gemessen: `start=2.82,
                    # end=2.00`, seine Woerter fehlen im Video komplett, und
                    # das Luecken-Netz laeuft vorher, haelt sie also fuer
                    # gezeigt. Die Ansage behaelt ihren Vorrang - aber nur,
                    # solange danach ueberhaupt noch etwas vom Block steht.
                    if _b['end'] - _spaet >= _FLOW_MIN or (
                            _k.get('intent') and _spaet < _b['end'] - 0.12):
                        _b['t0'] = _b['start'] = _spaet
                        _n_solo += 1
                    else:
                        # Der Block ist zu kurz zum Warten. Dann raeumt die
                        # Karte, notfalls unter ihrer Mindestlesezeit - und
                        # sie bekommt ein KURZES Ausklingen mit, sonst fadet
                        # sie 0.40 s lang in den Block hinein (genau die
                        # Kollision, die im Bild zu sehen war).
                        _k['end'] = _ke = max(_ks + 0.20, _bs - 0.16)
                        _k['aus'] = 0.12
                        _n_solo += 1
        # v209a KARTE GEGEN KARTE. Der Riegel darueber vergleicht nur Karte
        # gegen Fliesstext - zwei KARTEN konnten sich beliebig ueberlagern,
        # und niemand hat es gemerkt, weil zwei Karten dicht beieinander
        # selten sind. Bei Orts-Ansagen sind sie der NORMALFALL: drei Saetze
        # hintereinander ("behind me", "on the wall", "above me") ergeben
        # drei Karten, und eine Karte haelt ihre Mindestlesezeit weit ueber
        # das gesprochene Wort hinaus. Gemessen an Ismets Werbespot:
        # 'ON THE WALL' lief 7.20-10.25, 'BEHIND ME' 7.25-8.75 - anderthalb
        # Sekunden zwei Karten uebereinander. Derselbe Fehlertyp wie
        # v159/v170/v176: ein Riegel am falschen Gate.
        _kws = sorted(_kwp, key=_ct0)
        for _a, _n in zip(_kws, _kws[1:]):
            _ns = _ct0(_n)
            if _a['end'] + _a.get('aus', _AUS) <= _ns + 1e-3:
                continue                         # sauber nacheinander
            _as = _ct0(_a)
            # (1) Die erste Karte kuerzt - aber NIE unter ihre Lesezeit. Eine
            # auf 0.2 s zusammengestauchte Karte ist schlimmer als die
            # Ueberschneidung: man sieht sie aufblitzen und kann sie nicht lesen.
            _soll = max(_as + _KW_MIN, _ns - _AUS)
            if _soll < _a['end'] - 1e-3:
                _a['end'] = _soll
                _n_solo += 1
            # (2) Reicht das nicht, WARTET die zweite Karte, statt dass die
            # erste sich kaputtkuerzt. Sie muss danach noch lesbar sein.
            if _a['end'] + _AUS > _ns + 1e-3:
                _spaet = _a['end'] + _AUS
                # v213: EINE ANSAGE VERSCHWINDET NIE. Bis v212 durfte die
                # zweite Karte beliebig weit nach hinten wandern - bei drei
                # Ansagen in vier Sekunden schob sie sich damit in die
                # naechste hinein und fiel am Ende ganz raus. In Ismets
                # Werbespot fehlte 'ON THE WALL' komplett, obwohl er es sagt.
                # Eine Ueberlappung zu beseitigen, indem man eine Aussage
                # loescht, ist keine Loesung. Deshalb: hoechstens 0.60 s
                # warten; reicht das nicht, kuerzt die ERSTE Karte weiter
                # (bis auf 0.50 s), statt die zweite weiter zu schieben.
                _max_push = _ns + 0.60
                if _spaet > _max_push:
                    _a['end'] = max(_as + 0.50, _max_push - _AUS)
                    _spaet = max(_ns, min(_spaet, _max_push), _a['end'] + 0.06)
                    # Das Ausklingen darf nicht in die naechste Karte fallen.
                    _a['aus'] = max(0.06, min(_AUS, _spaet - _a['end']))
                _n['t0'] = _n['start'] = _spaet
                # Sie darf dabei laenger stehen bleiben: die Standzeit einer
                # Karte haengt an der Lesbarkeit, nicht am gesprochenen Wort.
                # Ohne das waere die zweite Karte nach dem Warten zu kurz -
                # und genau dann blitzt sie nur auf.
                _n['end'] = max(_n['end'], _spaet + _KW_MIN)
                _n_solo += 1
        # v217: HIER STAND EIN FLIESSTEXT-GEGEN-FLIESSTEXT-RIEGEL (v216).
        # Er ist RAUS und kommt so nicht wieder. Er hat den Fall nicht
        # geloest, sondern verschlimmert: bei Gedraenge VERLAENGERTE er den
        # wartenden Block (er schob dessen Ende nach hinten), und damit
        # stand derselbe Satz zweimal gleichzeitig im Bild - einmal hinter
        # der Person, einmal unten (Ismets Screenshot, 'EVERYONE'S ... LOOK
        # THE' und 'CAPTIONS LOOK THE'). In keinem Zeit-Test faellt das auf,
        # weil sich die ZAHLEN sauber nicht ueberschneiden; doppelt war der
        # INHALT. Lehre: eine Regel gegen Doppelbilder darf Zeiten nur
        # KUERZEN, nie verlaengern - und wer sie neu baut, muss den Wortlaut
        # vergleichen, nicht nur die Zeitfenster.
        if _n_solo:
            print(f"  Solo guard: {_n_solo} moment(s) trimmed so the "
                  f"keyword card stands alone")

    # v230m HOECHSTENS ZWEI TEXTE, NIE DREI (Ismets Ansage, 01.08.2026).
    # An der Wand standen drei Sachen gleichzeitig: die Karte 'BEHIND ME'
    # klang noch aus, das Ankerwort 'WALL' lag schon an der Wand, und die
    # Stuetzzeile 'THIS ONE STICKS' lief darueber. Karte plus eigene
    # Stuetzzeile sind in Ordnung - die ALTE Karte muss weg sein, bevor die
    # naechste ihr erstes Element zeigt.
    # Gekuerzt wird nur das AUSKLINGEN der vorherigen Karte (v217: eine Regel
    # gegen Doppelbilder darf nie verlaengern). Ihr `end` liegt davor, die
    # gesprochenen Woerter bleiben unangetastet.
    _kt = sorted([p for p in plans if p.get('kw_i') is not None
                  and p.get('kw_txt')],
                 key=lambda p: float(p.get('start', 0.0)))
    _n_zwei = 0
    for _a, _b in zip(_kt, _kt[1:]):
        _ae = float(_a['end'])
        _bs = float(_b.get('start', _b.get('t0', 0.0)))
        _aus_ist = _a.get('aus')
        _aus_ist = 0.40 if _aus_ist is None else float(_aus_ist)
        _aus_soll = max(min(_aus_ist, _bs - _ae - 0.02), 0.10)
        if _aus_soll < _aus_ist - 1e-3:
            _a['aus'] = round(_aus_soll, 3)
            _n_zwei += 1
    if _n_zwei:
        print(f"  Card solo: {_n_zwei} card(s) fade out before the next one "
              f"starts")

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
            # v193: hat der Nutzer die Zeiten dieses Blocks selbst gesetzt,
            # bleiben sie stehen. Die Schnitt-Disziplin ist eine Regel gegen
            # ueber den Schnitt haengende Automatik-Captions, kein Veto gegen
            # eine eingetippte Endzeit.
            if p.get('_user_t'):
                continue
            nxt = next((c for c in cts if c > st + MIN_SHOWN), None)
            if nxt is None:
                continue
            limit = nxt - EXIT_LEAD
            if en > limit and limit >= st + MIN_SHOWN:
                p['end'] = limit
                n_clamp += 1
        if n_clamp:
            print(f"  Cut discipline: {n_clamp} moment(s) end before the cut")

    # v101c BEAT-GRID: Liegt Musik mit klarem Takt unter dem Clip, rasten
    # Keyword-Momente auf den naechsten Beat ein (Editor-Handwerk: "cut on the
    # beat"). Nur der EINSTIEG wird verschoben, max. 0.12s (unter der Wort-
    # Sync-Wahrnehmungsschwelle), und nie so, dass der Moment unter 0.6s
    # Standzeit faellt. SFX bleiben bewusst auf den Sprech-Onsets - der Ton
    # gehoert zum Wort, das Bild darf zum Takt atmen.
    if beat_times and cfg['effects'].get('beat_grid', True):
        bts = sorted(float(b) for b in beat_times)
        n_snap = 0
        for p in plans:
            if 'kw_i' not in p or p.get('broll') or p.get('_user_t'):
                continue                    # v193: Nutzer-Zeit bleibt Nutzer-Zeit
            st, en = p.get('start'), p.get('end')
            if st is None or en is None:
                continue
            nb = min(bts, key=lambda b: abs(b - st))
            # v214: eine Ansage rastet nur NACH hinten auf den Takt. Der Takt
            # darf einen Moment atmen lassen, aber nicht vor den Satz ziehen,
            # der ihn ankuendigt.
            if p.get('intent') and nb < float(words[p['kw_i']]['start']) - 1e-6:
                continue
            if 0.005 < abs(nb - st) <= 0.12 and en - nb >= 0.6:
                p['start'] = nb
                n_snap += 1
        if n_snap:
            print(f"  Beat grid: {n_snap} moment(s) snap to the beat")

    # v140 STILLE VOR DEM EINSCHLAG. Die teuerste Sekunde im professionellen
    # Schnitt ist die leere: kurz vor der Pointe verschwindet der Text, das
    # Bild atmet, dann schlaegt das Wort ein. Wirkt hochwertiger als jede
    # zusaetzliche Animation und ist der klarste Senior-Editor-Marker.
    # Laeuft NACH Schnitt-Disziplin und Beat-Grid, damit der endgueltige
    # Einsatz der Pointe feststeht. Der Vorlaeufer wird nur gekuerzt, wenn er
    # danach noch MIN_SHOWN_SIL steht - lieber keine Stille als ein Blitz.
    _sil = float(cfg['effects'].get('punch_silence', 0.34))
    if _sil > 0:
        MIN_SHOWN_SIL = 0.34      # so lange muss der Vorlaeufer noch stehen
        MIN_GAP_SIL = 0.15        # so viel Luft muss der Sprecher lassen
        n_sil = 0
        for p in plans:
            if (int(p.get('power', 2)) < 3 or 'kw_i' not in p
                    or p.get('broll') or p.get('start') is None):
                continue
            i = p.get('kw_i')
            pst = p['start']
            if not isinstance(i, int) or i <= 0 or i >= len(words):
                continue
            # NUR wo der Sprecher wirklich Luft laesst. Text mitten im Satz
            # wegzunehmen saehe nach Fehler aus, nicht nach Regie - die Leere
            # faellt genau in die Sprechpause vor der Pointe.
            gap = float(words[i].get('start', 0)) - float(words[i - 1].get('end', 0))
            if gap < MIN_GAP_SIL:
                continue
            lead = min(_sil, gap)
            for q in plans:
                qs, qe = q.get('start'), q.get('end')
                if qs is None or qe is None or qs >= pst:
                    continue
                if qe > pst - lead:
                    neu = pst - lead
                    if neu >= qs + MIN_SHOWN_SIL:
                        q['end'] = neu
                        n_sil += 1
        if n_sil:
            print(f"  Silence before the impact: {n_sil} moment(s) end earlier")

    # v214 ZENTRALER RIEGEL, GANZ AM ENDE: keine Ansage steht vor ihrem Wort.
    # Hier laufen ALLE Zeit-Regeln zusammen (Hook, Ueberlappung, Solo, Schnitt,
    # Beat, Stille). Schlaegt er an, hat eine davon eine Ansage nach vorn
    # gezogen - dann ist die Meldung der Hinweis, WO nachzusehen ist.
    _n_int = intent_time_floor(plans, words)
    if _n_int:
        print(f"  Announcement guard: {_n_int} announced moment(s) moved back "
              f"to their spoken word")

    # v101d: Safe-Zone-Kontrolle. Die Constraints (v_zone/clamp_cx) halten Text
    # schon in der Flaeche; hier melden wir nur die Faelle, wo ein Sprite dafuer
    # zu gross ist und trotzdem ins Chrome ragt - damit der Kunde es sieht.
    _sz_warn = safe_zone_report(plans, _pz, W, H)
    if _sz_warn:
        _lst = ', '.join(f"'{t}' ({g})" for t, g in _sz_warn[:3])
        print(f"  Safe zone warning ({_pz['label']}): {len(_sz_warn)} "
              f"moment(s) reach into the platform UI - {_lst}")

    # v161 OBJEKT-ANKER: den Text an sein Objekt setzen. NEBEN das Objekt,
    # nicht darauf - eine Caption quer ueber dem Gegenstand, den sie meint,
    # verdeckt genau das, worum es geht. Bevorzugt darunter (Bildunterschrift-
    # Logik), sonst darueber. Die Seite bleibt die des Objekts.
    _n_ank = 0
    for p in plans:
        _a0 = p.get('_ank0')
        # Nicht jeder Look legt sein Bild in 'arr' - 'outline' benutzt
        # 'o_arr'. Nur auf 'arr' zu pruefen hiess: der Anker wurde gesetzt,
        # aber nie angewandt, und der Text blieb in der Bildmitte stehen.
        _abild = p.get('arr')
        if _abild is None:
            _abild = p.get('o_arr')
        if not _a0 or _abild is None:
            continue
        _ox, _oy, _or = _a0
        _ah = float(_abild.shape[0])
        _aw = float(_abild.shape[1])
        _unten = _oy + _or + _ah * 0.62
        _oben = _oy - _or - _ah * 0.62
        _rand_u = (_pz['bottom'] if _pz is not None else H * 0.95)
        _rand_o = (_pz['top'] if _pz is not None else H * 0.05)
        if _unten + _ah * 0.5 <= _rand_u:
            _ny = _unten
        elif _oben - _ah * 0.5 >= _rand_o:
            _ny = _oben
        else:
            continue                      # kein Platz neben dem Objekt
        p['cx'] = clamp_cx(_ox, int(_aw))
        if 'by' in p:
            p['by'] = _ny
        p['cy'] = _ny
        _n_ank += 1
    if _n_ank:
        print(f"  Object anchor: {_n_ank} moment(s) placed next to their object")

    # v230k ist ZURUECKGENOMMEN (Ismets Ansage, 31.07.2026): zwei
    # Fliesstext-Bloecke duerfen gleichzeitig im Bild stehen. Der
    # Riegel kuerzte das Ausklingen des vorherigen Blocks - das war
    # eine ungefragte Verhaltensaenderung an einem gewollten Zustand.

    # v230l DOPPELTEXT-WACHE. Ein Wort, das gesprochen wurde, gehoert genau
    # EINEM Bild. Steht es in zwei Plaenen, die gleichzeitig oder direkt
    # hintereinander laufen, sieht der Zuschauer dasselbe zweimal - Ismets
    # Befund. Die Ursachen sind gefunden und behoben; diese Zeile ist der
    # Melder fuer den naechsten Weg dorthin. Sie AENDERT nichts (ein Schutz,
    # der Woerter wegwirft, waere die v230f-Falle), sie steht im Job-Log.
    def _plan_worte(p):
        _o = set()
        for _t in str(p.get('kw_txt') or '').split():
            _n = _norm_txt(_t)
            if _n:
                _o.add(_n)
        for _sl in ('small', 'front', 'tokens'):
            for _it in (p.get(_sl) or []):
                if isinstance(_it, dict) and isinstance(_it.get('i'), int) \
                        and 0 <= _it['i'] < len(words):
                    _n = _norm_txt(words[_it['i']].get('word', ''))
                    if _n:
                        _o.add(_n)
        return _o

    def _plan_fenster(p):
        _a = p.get('aus')
        if _a is None:
            _a = 0.15 if p.get('tpl') == 'flow' else 0.40
        return (float(p.get('t0', p.get('start', 0.0))),
                float(p.get('end', 0.0)) + float(_a))

    _dtxt = [(p, _plan_worte(p), _plan_fenster(p)) for p in plans]
    _dtxt = sorted([x for x in _dtxt if x[1]], key=lambda x: x[2][0])
    _dopp = []
    for _x in range(len(_dtxt)):
        for _y in range(_x + 1, len(_dtxt)):
            _pa, _wa, _fa = _dtxt[_x]
            _pb, _wb, _fb = _dtxt[_y]
            if _fb[0] > _fa[1] + 1.0:
                break                       # sortiert: danach kommt nichts mehr
            _gem = _wa & _wb
            if _gem:
                _dopp.append((_fb[0], sorted(_gem)))
    if _dopp:
        print(f"  Duplicate text warning: {len(_dopp)} case(s) show the same "
              f"spoken word twice within 1s")
        for _t, _g in _dopp[:4]:
            print(f"    at {_t:.2f}s: {' '.join(_g)}")

    # v216 GANZ ZUM SCHLUSS: nichts wird vom Bildrand angeschnitten. Hier
    # steht die endgueltige Groesse UND Position jedes Moments fest - davor
    # koennten Objekt-Anker, Platzierungs-Regie oder Referenz-Skalierung noch
    # dazwischenfunken. Wer eine neue Groessen- oder Platzierungsregel baut,
    # muss diesen Riegel nicht kennen; ihr Ergebnis laeuft hier durch.
    _n_fit = fit_into_frame(plans, W, H)
    if _n_fit:
        print(f"  Frame guard: {_n_fit} moment(s) scaled/moved back into frame")

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
    # v161: haengt der Text an einem OBJEKT, darf er nicht gleichzeitig dem
    # Gesicht folgen. Zwei Ziele ergeben keine Bewegung, sondern Zittern.
    if p.get('_ank0'):
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
    # v227 NUR DORT RECHNEN, WO EINE MASKE IST. Ismets Befund: knapp 3 Minuten
    # fuer 15 Sekunden. Gemessen (1080x1920, CPU) kostete DIESE Funktion
    # 151-279 ms je Bild - MEHR als das Matting-Netz selbst (216 ms). Der
    # Guided Filter lief ueber das GANZE Bild, obwohl die Maske typisch ein
    # Drittel davon ausmacht; im leeren Rest rechnet er nachweislich Nullen.
    # Das ist keine Qualitaets-Abwaegung, sondern weggelassene Leerarbeit:
    # der Zuschnitt ist um 4 Radien groesser als die Maske, weiter reicht der
    # Filter nicht, und das Ergebnis ist PIXELGLEICH (gemessen: max. 0.000/255
    # Abweichung ueber mehrere Formen, auch randberuehrend).
    _hh, _ww = a.shape[:2]
    _x0, _y0, _x1, _y1 = 0, 0, _ww, _hh
    _bx = cv2.boundingRect((a > 0.002).astype(np.uint8))
    if _bx[2] == 0 or _bx[3] == 0:
        return alpha                  # leere Maske: es gibt nichts zu schaerfen
    _pd = 4 * r
    _x0, _y0 = max(_bx[0] - _pd, 0), max(_bx[1] - _pd, 0)
    _x1 = min(_bx[0] + _bx[2] + _pd, _ww)
    _y1 = min(_bx[1] + _bx[3] + _pd, _hh)
    try:
        _g = np.ascontiguousarray(guide[_y0:_y1, _x0:_x1])
        _p = np.ascontiguousarray(a[_y0:_y1, _x0:_x1])
        _q = cv2.ximgproc.guidedFilter(_g, _p, r, 1e-4)
        if staerke > 1.15:
            # Zweiter Durchgang mit kleinem Radius: holt feine Struktur zurueck
            # (einzelne Haarstraehnen, Brillenbuegel, Finger), die der erste,
            # groebere Durchgang glatt buegelt.
            _q = cv2.ximgproc.guidedFilter(_g, _q, max(r // 3, 2), 1e-5)
        a2 = np.zeros_like(a)
        a2[_y0:_y1, _x0:_x1] = _q
    except Exception:
        return alpha
    # Kontrast an der Kante anziehen: halbdurchsichtiger Matsch wird zu einer Kante.
    a2 = np.clip((a2 - 0.5) * (1.0 + 0.9 * staerke) + 0.5, 0.0, 1.0)
    mix = min(staerke, 1.0)
    out = a[..., None] * (1 - mix) + a2[..., None] * mix
    return out.astype(np.float32)


def merge_anker(szene_map, anker_map):
    """v228c Ergebnis der Objekt-Anker-Regie in die Bild-Regie einhaengen.

    Beide laufen gleichzeitig auf je einer KOPIE der fx_map (sonst schreiben
    zwei Threads in dieselben dicts). Zusammengefuehrt wird deterministisch:
    die Bild-Regie ist die Grundlage, der Anker steuert NUR sein eigenes Feld
    bei. Damit haengt das Ergebnis nicht daran, wer zuerst fertig wird."""
    if not isinstance(szene_map, dict) or not isinstance(anker_map, dict):
        return szene_map
    for _i, _v in anker_map.items():
        if isinstance(_v, dict) and _v.get('anker') \
                and isinstance(szene_map.get(_i), dict):
            szene_map[_i]['anker'] = _v['anker']
    return szene_map


def matte_loecher_fuellen(alpha, radius=14):
    """v230a LOECHER IM INNEREN EINER PERSON SIND IMMER EIN FEHLER.

    Die Nachschaerfung laesst je nach Staerke Krater in der Maske stehen: an
    Ismets Bild gemessen 15 Pixel bei Staerke 1.3, aber 2981 bei 0.39 (dem
    Wert, den die v228b-Gegenprobe waehlt). Wo die Maske innen nicht ganz
    dicht ist, scheint der Text HINTER der Person durch sie hindurch - als
    Schleier oder feine Linie mitten im Gesicht.
    Gefuellt wird nur der KERN (die um `radius` geschrumpfte Silhouette).
    Der Radius ist bewusst grosszuegig (14 px): bei einer sehr weichen Matte
    reicht der Uebergang 10 px und mehr nach innen, und der wird nicht
    angetastet - sonst sieht die Person ausgeschnitten aus (v181).
    Damit bleiben zwei Dinge unangetastet: die weiche Aussenkante (Haare,
    Finger) und echte Durchblicke - eine Luecke zwischen Arm und Koerper ist
    breiter als der Radius und ueberlebt das Schrumpfen, ein Krater von
    wenigen Pixeln nicht."""
    if alpha is None:
        return alpha
    a = alpha[..., 0] if alpha.ndim == 3 else alpha
    fg = (a > 0.5).astype(np.uint8)
    if fg.sum() < 100:
        return alpha
    k = max(int(radius), 3)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k * 2 + 1, k * 2 + 1))
    kernbereich = cv2.erode(fg, kern)
    if not kernbereich.any():
        return alpha
    out = a.copy()
    out[kernbereich > 0] = 1.0
    # Und die echten KRATER: kleine Loecher (a <= 0.5), die vollstaendig von
    # Person umgeben sind. Ein Durchblick zwischen Arm und Koerper beruehrt
    # entweder den Bildrand oder ist gross - beides bleibt offen.
    loch = (a <= 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(loch, 8)
    if n > 1:
        gross = float(fg.sum()) * 0.0006          # 0.06 % der Personenflaeche
        h, w = a.shape[:2]
        for i in range(1, n):
            # Untergrenze 200 px (rund 14x14): so klein ist kein gewollter
            # Durchblick, aber genau so gross sind die Krater der Maske.
            if st[i, cv2.CC_STAT_AREA] > max(gross, 200):
                continue
            x, y = st[i, cv2.CC_STAT_LEFT], st[i, cv2.CC_STAT_TOP]
            bw_, bh_ = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]
            if x == 0 or y == 0 or x + bw_ >= w or y + bh_ >= h:
                continue                          # beruehrt den Bildrand
            # Ist das Loch RINGSUM von Person umgeben? Der Rahmen um seine
            # Box muss fast vollstaendig Person sein - sonst ist es ein
            # Durchblick nach draussen, kein Krater.
            x0, y0 = max(x - 3, 0), max(y - 3, 0)
            x1, y1 = min(x + bw_ + 3, w), min(y + bh_ + 3, h)
            ring = fg[y0:y1, x0:x1].copy()
            ring[3:-3, 3:-3] = 1 if ring.shape[0] > 6 and ring.shape[1] > 6 else ring[3:-3, 3:-3]
            if float(ring.mean()) < 0.92:
                continue                          # nicht ringsum umschlossen
            out[lab == i] = 1.0
    return out[..., None] if alpha.ndim == 3 else out


def matte_muell(a):
    """v228b Wieviel MUELL hat die Maske? Gezaehlt werden lose Kruemel (kleine
    Flecken neben der Person) und Loecher (kleine Aussparungen in ihr) - genau
    das, was eine zerfetzte Silhouette ausmacht. Echte Haarstraehnen zaehlen
    NICHT mit: sie haengen am Koerper und sind damit dieselbe Flaeche."""
    m = (a > 0.5).astype(np.uint8)
    fl = float(m.sum())
    if fl < 100:
        return 0
    n, _l, st, _c = cv2.connectedComponentsWithStats(m, 8)
    kr = sum(1 for i in range(1, n) if st[i, cv2.CC_STAT_AREA] < fl * 0.002)
    n2, _l2, st2, _c2 = cv2.connectedComponentsWithStats(
        (a <= 0.5).astype(np.uint8), 8)
    lo = sum(1 for i in range(1, n2) if st2[i, cv2.CC_STAT_AREA] < fl * 0.002)
    return kr + lo


def _refine_wahl(sess, dsr, video_path, W, H, wunsch, zeiten):
    """v230h DIE KANTEN-SCHAERFUNG WIRD NICHT MEHR AN EINEM BILD ENTSCHIEDEN.

    v228b prueft die Staerke am ERSTEN Bild und benutzt das Ergebnis fuer den
    ganzen Render. An Ismets Video gemessen ist diese Einzelmessung aber ein
    MUENZWURF: 0.1s->1.0, 1.0s->0.3, 3.0s->1.0, 6.0s->0.3, 8.0s->1.0,
    10.0s->0.3, 13.0s->1.0. Sein Render erwischte am ersten Bild die 1.0 -
    und lief 15 Sekunden lang mit voller Schaerfung, obwohl die Pruefung
    genau in den Einstellungen, wo es sichtbar wird, selbst 0.3 verlangt.
    Ergebnis im Bild: die Kontur des ausgestreckten Arms wird wellig und
    blasig, wie ein zweiter Rand (Ismets "sein Arm wird doppelt").
    Gemessen an derselben Stelle: Kantenrauigkeit 1.49 px roh, 1.51 bei
    Staerke 0.3, 2.42 bei 1.0 - und 1 Kruemel gegen 104.

    Jetzt: mehrere Stellen ueber das Video pruefen und die NIEDRIGSTE
    Staerke nehmen, die irgendeine davon verlangt. Eine zu schwache
    Schaerfung kostet etwas Feinheit an den Haaren; eine zu starke zerfetzt
    die Silhouette - und das sieht jeder. Kostet einmal je Render ein paar
    Sekunden, nicht je Bild."""
    if not zeiten:
        return wunsch
    beste = wunsch
    _z = [t for t in zeiten if t is not None]
    _frame_bgr_vorab(video_path, _z, w=W)          # parallel vorladen (v227a)
    _rec = [np.zeros([1, 1, 1, 1], dtype=np.float32)] * 4
    for _t in _z:
        try:
            _f = _frame_bgr(video_path, _t, w=W)
            if _f is None:
                continue
            if _f.shape[0] != H or _f.shape[1] != W:
                _f = cv2.resize(_f, (W, H))
            _src = np.transpose(cv2.cvtColor(_f, cv2.COLOR_BGR2RGB)
                                .astype(np.float32) / 255.0, (2, 0, 1))[None]
            _, _pha, *_ = sess.run(None, {'src': _src, 'r1i': _rec[0],
                                          'r2i': _rec[1], 'r3i': _rec[2],
                                          'r4i': _rec[3], 'downsample_ratio': dsr})
            _a = _pha[0].transpose(1, 2, 0).astype(np.float32)
            beste = min(beste, _refine_pruefen(_a, _f.astype(np.float32),
                                               wunsch, still=True))
        except Exception:
            continue
    if beste < wunsch - 1e-6:
        print(f"  Matte check: edge sharpening set to {beste:.2f} "
              f"(checked {len(_z)} shots, the strictest one wins - full "
              f"strength was shredding the silhouette)")
    return beste


def _refine_pruefen(alpha, frame, wunsch, still=False):
    """v228b Die Nachschaerfung gegenpruefen und notfalls zuruecknehmen.

    Der Guided Filter zieht die Maskenkante an die Bildkante - auf echtem
    Kameramaterial holt das Haare und Finger zurueck. Auf weichem, rauschfreiem
    Material findet er keine echte Kante mehr und macht aus Stoff-Rauschen
    Silhouette: an Ismets Render gemessen 9 Kruemel/Loecher roh gegen 285 nach
    der Nachschaerfung. Deshalb wird die Staerke am ersten Bild geprueft und
    heruntergedreht, wenn sie die Maske SCHMUTZIGER macht. Qualitaet
    entscheidet, nicht ein fester Wert - und die Pruefung kostet einmal je
    Render, nicht je Bild."""
    if alpha is None or wunsch <= 0:
        return wunsch
    try:
        roh = matte_muell(alpha[..., 0])
        for _st in (wunsch, wunsch * 0.6, wunsch * 0.3):
            _m = matte_muell(refine_alpha(alpha, frame, _st)[..., 0])
            if _m <= roh * 4 + 20:
                if _st < wunsch - 1e-6 and not still:
                    print(f"  Matte check: edge sharpening turned down to "
                          f"{_st:.2f} ({_m} specks vs {roh} raw) - it was "
                          f"shredding the silhouette")
                return _st
        if not still:
            print(f"  Matte check: edge sharpening OFF - it shredded the "
                  f"silhouette on this footage ({roh} specks raw)")
        return 0.0
    except Exception:
        return wunsch


def kill_spill(person, alpha, frame):
    """Farbsaum weg. An der Silhouette mischt sich der Hintergrund in die Person -
    steht dahinter ein knallbunter Caption-Text, leuchtet sein Farbstich um die
    Schulter herum. Der Randbereich wird darum leicht entsaettigt und abgedunkelt."""
    if alpha is None:
        return person
    a = alpha[..., 0]
    # v228f NUR AM SAUM RECHNEN. Gemessen (720x1280, dichte Captions) war das
    # hier der teuerste Einzelposten beim Captions-Setzen: 36 ms je Bild, mehr
    # als alles andere im Compositor. Der Saum ist ein schmales Band um die
    # Silhouette - ausserhalb ist `kante` exakt 0, und die Formel liefert dort
    # `person * 1 + grau * 0`, also das Bild unveraendert. Trotzdem liefen
    # Weichzeichner, Graustufen-Mittel und Mischung ueber das GANZE Bild.
    # Der Zuschnitt ist deshalb keine Qualitaets-Abwaegung, sondern
    # weggelassene Leerarbeit - das Ergebnis ist PIXELGLEICH (geprueft).
    _band = (a > 0.05)
    _bx = cv2.boundingRect(_band.astype(np.uint8))
    if _bx[2] == 0 or _bx[3] == 0:
        return person
    # 10 Sigma Rand: der Weichzeichner ist dort rechnerisch aus. Mit 4 Sigma
    # blieb an einer randberuehrenden Silhouette EIN Wert um 1/255 daneben
    # (Spiegel-Rand des Filters) - messbar, also weg damit.
    _pd = 20
    _h, _w = a.shape[:2]
    _x0, _y0 = max(_bx[0] - _pd, 0), max(_bx[1] - _pd, 0)
    _x1, _y1 = min(_bx[0] + _bx[2] + _pd, _w), min(_bx[1] + _bx[3] + _pd, _h)
    _ac = a[_y0:_y1, _x0:_x1]
    kante = cv2.GaussianBlur((_ac > 0.05).astype(np.float32)
                             - (_ac > 0.95).astype(np.float32), (0, 0), 2.0)
    kante = np.clip(kante, 0, 1)[..., None]
    out = person.copy()
    _pc = out[_y0:_y1, _x0:_x1]
    grau = _pc.mean(axis=2, keepdims=True)
    out[_y0:_y1, _x0:_x1] = _pc * (1 - 0.35 * kante) + grau * (0.35 * kante)
    return out


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
    # Bereinigte Personen-Maske: Hintergrund-Blobs der rohen Matte wuerden
    # als scharfe Inseln im Bokeh stehen (Halos um Autos/Pflaster).
    a_c = np.clip(person_mask(alpha), 0, 1) if alpha is not None else None
    if a_c is not None:
        # v230b MATTE-BLEED. Der Weichzeichner lief ueber das GANZE Bild, also
        # auch ueber die Person: an der Silhouette mischte er dunkles Haar mit
        # heller Wand. Weil die Vordergrund-Maske weichgezeichnet ist, reicht
        # sie ~20 px IN die Person hinein - dort wurde dieser Mischwert wieder
        # aufs Haar gelegt. Ergebnis: ein heller, flimmernder Saum an Haar und
        # Schultern, der nur waehrend eines Moments auftaucht (Ismets Befund
        # "das Auge glitcht"). Jetzt wird der Hintergrund ALPHA-GEWICHTET
        # weichgezeichnet: Personen-Pixel gehen gar nicht erst ein.
        a_s = cv2.resize(a_c, (W // scale, H // scale),
                         interpolation=cv2.INTER_AREA)
        wgt = (1.0 - a_s).astype(np.float32)
        num = cv2.GaussianBlur(small.astype(np.float32) * wgt[..., None],
                               (0, 0), sigma)
        den = cv2.GaussianBlur(wgt, (0, 0), sigma)
        blurred_small = num / np.maximum(den, 1e-3)[..., None]
        # Tief in der Person ist KEIN Hintergrund in Reichweite - dort bleibt
        # das Originalbild stehen (dort mischt die Maske ohnehin nichts).
        leer = den < 1e-3
        blurred_small[leer] = small.astype(np.float32)[leer]
        blurred = cv2.resize(blurred_small, (W, H))
    else:
        blurred = cv2.resize(cv2.GaussianBlur(small, (0, 0), sigma),
                             (W, H)).astype(np.float32)
    # Vordergrund-Maske (was scharf bleibt): 1.0 = scharf, 0.0 = voll blur.
    if a_c is not None:
        # Etwas ausdehnen, damit die Text-Zone um die Person auch scharf bleibt
        # und der Uebergang natuerlich weich verlaeuft (Bokeh-Rand).
        fg = cv2.GaussianBlur(a_c, (0, 0), max(H * 0.008, 2.0))
        # v230b: Die Person selbst bleibt VOLL scharf. Der Weichzeichner der
        # Maske darf nur nach AUSSEN wirken, nie in die Silhouette hinein.
        fg = np.maximum(fg, a_c)
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


# v101h CAPTION-ALPHA-EXPORT: Difference-Matting-Doppelpass. Die Caption-Ebene
# wird zweimal komponiert - einmal ueber Schwarz, einmal ueber Weiss. Aus den
# beiden Ergebnissen laesst sich Alpha EXAKT loesen (fuer alle linearen
# Overlay-Operationen): alpha = 1 - (comp_weiss - comp_schwarz)/255. Person-
# Occlusion (behind) wird dabei automatisch zum LOCH im Alpha - genau das,
# was der Schnittplatz braucht. Voraussetzung: beide Paesse bitidentische
# Geometrie -> Anim-/Kamera-State wird zwischen den Paessen zurueckgesetzt.
def _alpha_state_snapshot(plans, cam_state):
    """Sichert allen veraenderlichen Zustand, den composite_frame anfasst:
    die '_'-Statekeys der Plaene (Anim-Feder, RNGs, Anker-Flags) + cam_state."""
    import copy as _cp
    saved = []
    for p in plans:
        keys = {}
        for k in list(p):
            if isinstance(k, str) and k.startswith('_'):
                keys[k] = _cp.deepcopy(p[k])
        saved.append(keys)
    return (saved, list(cam_state) if cam_state is not None else None)


def _alpha_state_restore(plans, cam_state, snap):
    saved, cam = snap
    for p, keys in zip(plans, saved):
        for k in [k for k in list(p) if isinstance(k, str) and k.startswith('_')]:
            if k not in keys:
                p.pop(k, None)
        p.update(keys)
    if cam is not None and cam_state is not None:
        cam_state[:] = cam


def alpha_from_pair(comp_black, comp_white):
    """Loest die Caption-Ebene aus dem Doppelpass: Rueckgabe BGRA uint8
    (straight alpha, wie prores_ks/yuva444p10le es erwartet). Wo alpha ~0 ist,
    wird die Farbe genullt (kein Entpremultiply-Rauschen)."""
    cb = np.asarray(comp_black, np.float32)
    cw = np.asarray(comp_white, np.float32)
    a = 1.0 - np.clip((cw - cb).mean(axis=2) / 255.0, 0.0, 1.0)
    an = a[..., None]
    straight = np.where(an > 1.0 / 255.0, cb / np.maximum(an, 1e-4), 0.0)
    return np.dstack([np.clip(straight, 0, 255),
                      np.clip(a * 255.0, 0, 255)]).astype(np.uint8)


def composite_frame(frame, alpha, t, plans, words, face_xy, cfg, S, W, H, cam_state=None,
                    scene_off=(0.0, 0.0), aud=(0.0, 0.0, 0.0), depth_n=None,
                    scene_vel=0.0, H_cum=None, track_gen=0,
                    H_cum_wall=None, wall_gen=0, hand_tips=None):
    a_rms, a_bass, a_onset = aud
    # v101h: Grain-Seed pro Frame (aus t) - der Alpha-Export-Doppelpass braucht
    # bitidentisches Grain in beiden Paessen, sonst rauscht das Alpha.
    _gs = int(t * 1000.0) & 0x7fffffff

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
    # v185: das Exit-Fenster ist plan-eigen. Eine gedraengte Keyword-Karte
    # bekommt vom Solo-Riegel ein kuerzeres 'aus' und raeumt dadurch
    # wirklich, statt 0.40 s lang in den naechsten Block hineinzufaden.
    active = [p for p in plans if p['start'] <= t < p['end'] + p.get('aus', 0.40)]
    # v101j: Beruehrungs-Feder pro aktivem Moment einmal pro Frame ticken.
    for _hp in active:
        if '_hand_hit' in _hp or _hp.get('_hand_dx') or _hp.get('_hand_vx') \
                or _hp.get('_hand_dy') or _hp.get('_hand_vy'):
            hand_spring(_hp, t)

    # Hintergrund-Blur (v69): waehrend eines aktiven Moments den Hintergrund
    # weichzeichnen. Staerke folgt der max. Moment-Fade-Kurve, damit der
    # Blur mit dem Text ein/ausblendet. Auf B-Roll aus - dort ist der
    # Hintergrund das Motiv, nicht die Person.
    # v230c-sec: 0..1 ist der Bereich, den der Regler kennt. Der Gauss-Radius
    # haengt linear daran (sigma = staerke * W/4 * 0.04); bei 100 sind das
    # gemessen ~12 s je EINZELBILD statt 0.25 s. Geklemmt wird auf beiden
    # Seiten - die Desktop-App schreibt dieselbe Config-Datei.
    bg_blur = min(max(float(cfg['effects'].get('bg_blur', 0.0) or 0.0), 0.0), 1.0)
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
    # v230b: bereinigte Personen-Maske EINMAL. Sie wird von der Tiefen-
    # Unschaerfe (unten) und beim Zurueckpasten der Person gebraucht -
    # person_mask ist nicht billig, zweimal rechnen waere Leerarbeit.
    alpha_p = person_mask(alpha)[..., None] if alpha is not None else None
    lock = cfg['effects'].get('scene_lock', True)

    def scene_shift(p):
        """Verankert Hintergrund-Texte in der Szene: sie wandern mit Kameraschwenks mit.
        Auf B-Roll (Drohne, FPV) darf der Text weiter wandern - er gehoert zur Welt.
        v101j: der Beruehrungs-Impuls (Hand-Kontakt) federt oben drauf."""
        _hx = p.get('_hand_dx', 0.0) + p.get('_ank_dx', 0.0)
        _hy = p.get('_hand_dy', 0.0) + p.get('_ank_dy', 0.0)
        if not lock or p.get('_ank0'):
            # v161: die Objekt-Spur enthaelt die Kamerabewegung bereits. Die
            # Szenen-Verankerung obendrauf wuerde jeden Schwenk DOPPELT
            # anwenden und den Text aus dem Bild schieben.
            return _hx, _hy
        if 's0' not in p:
            p['s0'] = scene_off
        dx = scene_off[0] - p['s0'][0]
        dy = scene_off[1] - p['s0'][1]
        lim = W * (0.30 if p.get('broll') else 0.12)
        if p.get('ort_ansage') == 'himmel':
            # v226 DER HIMMEL IST DIE FERNE EBENE. Ein Nahbereich-Schwenk
            # verschiebt ihn fast nicht (Parallaxe geht mit der Entfernung
            # gegen null) - ihn 1:1 mitzuziehen war physikalisch falsch UND
            # liess die Karte absinken, bis zum Deckel 0.072 H. Eine
            # "ueber mir"-Ansage darf nicht nach unten wandern; senkrecht
            # bleibt sie deshalb stehen, waagerecht folgt sie gedaempft.
            return (max(-lim, min(dx * 0.35, lim)) + _hx, _hy)
        return (max(-lim, min(dx, lim)) + _hx,
                max(-lim * 0.6, min(dy, lim * 0.6)) + _hy)
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
            if alpha_p is not None:
                # v230b MATTE-BLEED, zweiter Fundort. Der Weichzeichner lief
                # ueber das GANZE Bild, also auch ueber die Person: an der
                # Silhouette mischte er dunkles Haar mit heller Wand. Danach
                # wird die Person mit WEICHER Matte zurueckgepastet - an jeder
                # Haarspitze blieb dadurch ein heller Funkel stehen (Ismets
                # Befund "das Auge glitcht"). Der Hintergrund wird jetzt
                # ALPHA-GEWICHTET weichgezeichnet: Personen-Pixel gehen gar
                # nicht erst in den Mittelwert ein.
                _as = cv2.resize(alpha_p[..., 0], (W // 3, H // 3),
                                 interpolation=cv2.INTER_AREA)
                _w = np.clip(1.0 - _as, 0, 1).astype(np.float32)
                _num = cv2.GaussianBlur(small * _w[..., None], (0, 0), 2.2)
                _den = cv2.GaussianBlur(_w, (0, 0), 2.2)
                _sm = _num / np.maximum(_den, 1e-3)[..., None]
                _leer = _den < 1e-3          # tief in der Person: nichts zu mischen
                _sm[_leer] = small[_leer]
                soft = cv2.resize(_sm, (W, H))
            else:
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
                        # v230g: kein Abzug der halben Hoehenzunahme mehr.
                        # Am Tinten-Schwerpunkt gemessen: KEINE Animation
                        # profitiert davon, fuenf werden dadurch dauerhaft
                        # nach oben verschoben (regen 126 px, bruch 69 px,
                        # druck 30 px, schweben 24 px, wackel 7 px). Der
                        # Abzug verankert die UNTERKANTE der Leinwand - das
                        # waere nur bei Stauch-Animationen richtig, und seit
                        # v194 polstern alle betroffenen symmetrisch.
                        oy_t = tok['oy'] + ady_t
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
                            ziel_x = p.get('bx', W / 2) + tok['ox'] + sdx
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
                    # v228a: Mitte des Blocks, nicht Mitte des Bildes.
                    paste(comp, arr_t,
                          p.get('bx', W / 2) + tok['ox'] + sdx + px_off + adx_t,
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
                    paste(comp, sl, p.get('bx', W / 2) + sdx + off,
                          by + sdy + (1 - e) * H * 0.055,
                          W, H, scale=0.9 + 0.1 * e, opacity=min(dl / 0.12, 1) * fade)
            else:
                e = smoothstep(dt / 0.8)
                live = 1.0 + 0.018 * min(dt / max(dur, 1.0), 1.0)   # Micro-Drift: lebt weiter
                arr_b, adx_b, ady_b, asc_b, aop_b = anim_apply(p, p['arr'], aud, dt)
                oy_b = ady_b            # v230g: siehe oben, kein Abzug
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
                    lok = (px - (p.get('bx', W / 2) + sdx)) / max(sc, 0.01) \
                        + arr_b.shape[1] / 2
                    # Startfenster = ungefaehr die Breite der Person. Groesser waere
                    # sinnlos: das Wort waere sofort halb sichtbar, statt HINTER ihr
                    # zu stecken.
                    p_halb = (float(face_xy[2]) if (face_xy is not None
                                                    and len(face_xy) > 2)
                              else W * 0.055) / max(sc, 0.01)
                    halb = p_halb + ee * arr_b.shape[1] * 0.55   # voll erst gegen Ende
                    arr_b = reveal_from(arr_b, lok, halb, weich=34.0)
                    dx0 = (px - (p.get('bx', W / 2) + sdx)) * 0.14 * (1 - ee)
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
                # v228a: der Block steht auf SEINER Mitte, nicht auf der
                # Bildmitte - sonst frisst eine Person, die seitlich steht,
                # ein ganzes Wortende (siehe _bx-Kommentar in build_plans).
                paste(comp, arr_b, p.get('bx', W / 2) + sdx + dx0 + adx_b,
                      by + oy_b + sdy + dy0 + x_dv * arr_b.shape[0],
                      W, H, scale=sc * live * x_sc, opacity=op * fade * aop_b, blur=mb_amt)
        else:
            e = ease_out(min(dt / 0.34, 1))
            sdx, sdy = scene_shift(p)
            arr_bl, adx, ady, asc, aop = anim_apply(p, p['arr'], aud, dt)
            # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
            paste(comp, arr_bl, W / 2 + sdx + adx, p.get('by', H * 0.333) + sdy + ady,
                  W, H, scale=(1.16 - 0.16 * e) * asc,
                  opacity=smoothstep(dt / 0.20) * (strength if dt > dur else 1) * aop,
                  blur=(1 - e) * 11)

    if alpha is not None:
        # Bereinigte Personen-Maske fuer ALLES, was die Person zurueck ueber
        # den Text legt: die rohe Matte markiert Hintergrund-Blobs (Autos,
        # Pflaster) als 'Person' - kill_spill/Schatten/Repaste zeichnen dann
        # sichtbare Umrisse um diese Blobs (Halos im ganzen Bild).
        # (alpha_p steht seit v230b schon oben - auch die Tiefen-Unschaerfe
        #  braucht sie.)
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

    # v221 DAS ORTSWORT LIEGT SCHON DA. Vor der eigentlichen Karte (deren Uhr
    # erst mit dem gesprochenen Wort bei 0 steht, v214/v215) liegt nur das
    # Ankerwort auf der Flaeche. Eigener Durchgang VOR der Hauptschleife: die
    # Zeichenzweige dort steigen bei dt < 0 alle aus, ein Ankerwort waere
    # dort nie zu sehen (v219-Lehre: die Korrektur muss an der Stelle stehen,
    # die auch laeuft).
    # Bewusst ueber ALLE plans, nicht ueber 'active': das Ankerwort liegt VOR
    # dem Anzeigefenster der Karte. Wuerde man dafuer p['start'] vorziehen,
    # haetten Ueberlappungs- und Solo-Riegel eine falsche Startzeit - genau
    # die Verwechslung, die v214/v215 gekostet hat.
    def _wand_aufbereiten(p):
        """v224d Wandmessung + Typografie an EINER Stelle.

        Vorher stand das nur im ground-Zweig - der laeuft aber erst,
        wenn die Karte im Anzeigefenster ist. Das ANKERWORT liegt davor
        (v221) und wurde deshalb noch mit der alten, bildbreiten Fassung
        und der alten Position gezeichnet: es sass neben der Wand statt
        darauf (am Beweisbild belegt). Jetzt rufen BEIDE Wege dieselbe
        Aufbereitung; `_pose_done` macht sie idempotent."""
        # v219 DIE WANDMESSUNG STEHT HIER OBEN, VOR ALLEN ZWEIGEN.
        # v218 hat sie in den NICHT-getrackten Zweig gelegt - und bei einem
        # Wand-Plan ist `tracked` IMMER wahr (need_track deckt das ganze
        # Anzeigefenster ab, und der Rueckfall auf den Boden-Track ist
        # ebenfalls nie None). Der Block war damit toter Code: gezeichnet
        # wurde weiter mit dem gebackenen Wechselwinkel (+-6 Grad), also
        # genau der Zustand, den v218 ersetzen sollte. Im Talking-Head
        # kommt ein zweiter Bypass dazu (`front_layer`, wenn keine freie
        # Wandflaeche gefunden wird) - der zeichnet noch weiter oben.
        # Es gibt in diesem Zweig DREI Zeichenwege; eine Korrektur am
        # Sprite gehoert deshalb VOR die Weiche, nicht in einen Ast.
        # (Derselbe Fehlertyp wie v159/v170/v176: Riegel am falschen Gate.)
        # v223a: die MELDUNG steht ausserhalb der Tiefen-Bedingung. Sie
        # innerhalb zu haben war derselbe Fehler in Kleinformat: der
        # kritische Fall - KEINE Tiefenkarte, also kein Wand-Effekt -
        # haette sich als einziger nicht gemeldet.
        if (p.get('szene') == 'wand' and not p.get('lying')
                and not p.get('glass') and depth_n is None
                and not p.get('_wall_log')):
            p['_wall_log'] = True
            print(f"  Wall text '{p.get('kw_txt', '')}': no depth map - "
                  f"keeping default angle and position "
                  f"(models/depth.onnx missing?)")
        if (p.get('szene') == 'wand' and not p.get('lying')
                and not p.get('glass') and not p.get('_pose_done')
                and p.get('flat_arr') is not None and depth_n is not None):
            # v223 ZUERST DIE FLAECHE FINDEN, DANN DORT MESSEN. Erst
            # gemessen und dann verschoben zu haben war ein Reihenfolge-
            # Fehler: gemessen wurde an der ALTEN Stelle (Bildmitte), wo
            # die Flaeche frontal ist - `wall_pose` gab dort None zurueck
            # und der Text behielt den gebackenen Winkel, obwohl die Wand
            # links klar schraeg steht (am Testfall belegt: yaw None statt
            # der erwarteten Neigung).
            _wa = wall_area(depth_n, alpha, W, H)
            _mx = _wa[0] if _wa else p.get('cx', W / 2)
            _my = _wa[1] if _wa else p.get('cy', H * 0.45)
            _yaw_w = wall_pose(depth_n, _mx, _my,
                               p['flat_arr'].shape[1] * 0.7,
                               p['flat_arr'].shape[0] * 2.2, W, H)
            if _yaw_w is not None:
                p['arr'] = persp_warp(p['flat_arr'], yaw=_yaw_w, pitch=0.0)
                p['_wall_yaw'] = _yaw_w
                # v221: das Ankerwort liegt auf DERSELBEN Flaeche - sonst
                # kippt es beim Uebergang zum vollen Satz sichtbar um.
                if p.get('anker_flat') is not None:
                    p['anker_arr'] = persp_warp(p['anker_flat'],
                                                yaw=_yaw_w, pitch=0.0)
            # v223 AUF DIE WANDFLAECHE, NICHT DANEBEN. Ismets Befund am
            # v222-Render: die Neigung stimmte, die STELLE nicht - der Text
            # lag halb ausserhalb am linken Bildrand, weil ihn die normale
            # Platzierungs-Regie gesetzt hat (die kennt Gesichter und
            # Bildunruhe, aber keine Wandflaeche). Jetzt wird die Flaeche
            # gemessen und der Text in ihre Mitte gelegt.
            if _wa is not None:
                _wcx, _wcy, _wbw, _wbh = _wa
                # v223 AUF DIE FLAECHE PASSEN, NICHT NUR DARUEBER LIEGEN.
                # Am v222-Render gemessen ist die Wand im Bild nur rund
                # 40 % breit (sie steht links, die Person davor), das
                # Wand-Sprite dagegen fast bildbreit (688-715 px bei
                # 720 px). Der Text konnte dort nie "auf" der Wand sein -
                # er lag zwangslaeufig halb daneben und halb ausserhalb.
                # "An der Wand" heisst: er passt auf die Flaeche.
                # v225 IN DIE WANDEBENE PROJIZIEREN, NICHT NUR KIPPEN.
                # Ismets Befund am v224-Bild: "es ist jetzt auf der Wand, aber
                # es hat die falschen Winkel". Er hat recht, und ein einzelner
                # Winkel konnte das nie leisten: eine Wand im Bild ist ein
                # TRAPEZ mit Fluchtlinien - Oberkante faellt, Unterkante steigt.
                # persp_warp(yaw) verkuerzt nur eine Seite und laesst die
                # Zeilen WAAGERECHT; genau deshalb sah der Schriftzug
                # aufgeklebt aus. Jetzt wird das gemessene Wand-Viereck als
                # Zielflaeche genommen und der Satz per Homographie
                # hineingelegt - Fluchtlinien, Neigung und Verkuerzung in
                # einem Schritt, ohne Winkel-Basteln.
                _quad = wall_quad(depth_n, alpha, W, H)
                _wt = wall_typo(S, p.get('kw_txt', ''), _wbw, _wbh, W, H,
                                extrude=False)
                if _quad is not None and _wt is not None:
                    p['flat_arr'] = _wt
                    p['arr'] = wall_project(_wt, _quad, W, H)
                    p['_wall_quad'] = [[round(float(v), 1) for v in q]
                                       for q in _quad]
                    p['_wall_yaw'] = _yaw_w
                    if p.get('anker_txt'):
                        _wat = wall_typo(S, p['anker_txt'], _wbw, _wbh,
                                         W, H, extrude=False)
                        if _wat is not None:
                            p['anker_flat'] = _wat
                            p['anker_arr'] = wall_project(_wat, _quad, W, H)
                    # Das Sprite liegt jetzt in BILDkoordinaten - die Position
                    # steckt in der Projektion. Ein zusaetzliches cx/cy waere
                    # eine zweite Verschiebung.
                    p['cx'], p['cy'] = W / 2.0, H / 2.0
                    p['_wall_proj'] = True
                elif _wt is not None:
                    # Kein verlaessliches Viereck (frontale Wand, unruhige
                    # Tiefenkarte): sauber gesetzter Satz ohne Projektion.
                    p['flat_arr'] = _wt
                    p['arr'] = _wt
                    p['_wall_yaw'] = None
                    if p.get('anker_txt'):
                        _wat = wall_typo(S, p['anker_txt'], _wbw, _wbh,
                                         W, H, extrude=False)
                        if _wat is not None:
                            p['anker_flat'] = _wat
                            p['anker_arr'] = _wat
                else:
                    # Rueckfall: passt kein Satz auf die Flaeche, wird wie
                    # in v223 gestaucht - lieber klein als daneben.
                    _ziel = _wbw * 0.92
                    for _sn in ('arr', 'anker_arr'):
                        _sa = p.get(_sn)
                        if _sa is None:
                            continue
                        _nz = np.where(_sa[..., 3] > 80)
                        if not len(_nz[0]):
                            continue
                        _tw = float(_nz[1].max() - _nz[1].min() + 1)
                        if _tw > _ziel:
                            p[_sn] = _skaliere_sprite(_sa,
                                                      max(_ziel / _tw, 0.45))
                # v225: NICHT bei projizierten Sprites. Dort steckt die
                # Position schon in der Homographie (das Sprite liegt in
                # Bildkoordinaten) - ein zusaetzliches cx/cy waere eine
                # zweite Verschiebung und schoebe den Schriftzug von der
                # Wand weg.
                if not p.get('_wall_proj'):
                    p['cx'] = _wcx
                    # v224: nicht auf den Schwerpunkt, sondern ins obere
                    # Drittel der Flaeche. Der Schwerpunkt einer bildhohen
                    # Wand ist die Bildmitte - dort schwebt der Text ohne
                    # Bezug. Auf Augenhoehe sitzt ein Wandschriftzug.
                    p['cy'] = _wcy - _wbh * 0.16
                    p['_wall_area'] = (round(_wcx, 1), round(p['cy'], 1),
                                       round(_wbw, 1))
            # v223: ins Log, WAS gemessen wurde. Drei Runden gingen mit
            # der Frage verloren, ob der Wand-Code ueberhaupt greift -
            # ohne Tiefenkarte tut er es nicht, und das war nirgends zu
            # sehen. Eine Zeile je Wand-Moment, nicht je Frame.
            if not p.get('_wall_log'):
                p['_wall_log'] = True
                print(f"  Wall text '{p.get('kw_txt', '')}': "
                      + (f"plane {_yaw_w:+.0f} deg" if _yaw_w is not None
                         else "no clear plane")
                      + (f", placed on wall area at x={_wa[0] / W:.2f} W"
                         if _wa is not None else ", no wall area found"))
            # v223 UND DANN INS BILD. Der Anschnitt-Riegel (v217) laeuft in
            # build_plans - also VOR dieser Neuverzerrung. Nach dem Warp
            # ist das Sprite breiter und die Tinte sitzt anders; ohne
            # zweite Pruefung laeuft genau das wieder aus dem Bild, was
            # v217 abgeriegelt hat (im v222-Render zu sehen: nur 'ON' und
            # 'WAL' standen drin).
            for _sn in ('arr', 'anker_arr'):
                _sa = p.get(_sn)
                if _sa is None:
                    continue
                _nz = np.where(_sa[..., 3] > 80)
                if not len(_nz[0]):
                    continue
                _cxn = float(p.get('cx', W / 2))
                _x0 = _cxn - _sa.shape[1] / 2.0 + float(_nz[1].min())
                _x1 = _cxn - _sa.shape[1] / 2.0 + float(_nz[1].max())
                if _x1 - _x0 > W * 0.98:
                    _s = (W * 0.96) / (_x1 - _x0)
                    p[_sn] = _sa = _skaliere_sprite(_sa, _s)
                    _nz = np.where(_sa[..., 3] > 80)
                    _x0 = _cxn - _sa.shape[1] / 2.0 + float(_nz[1].min())
                    _x1 = _cxn - _sa.shape[1] / 2.0 + float(_nz[1].max())
                if _x0 < W * 0.02:
                    p['cx'] = _cxn + (W * 0.02 - _x0)
                elif _x1 > W * 0.98:
                    p['cx'] = _cxn - (_x1 - W * 0.98)
            p['_pose_done'] = True

    for p in plans:
        if p.get('anker_arr') is None or 'kw_i' not in p:
            continue
        _at0 = float(p.get('anker_t0', p.get('start', 0.0)))
        _kt0 = card_t0(p, words)
        if t < _at0 or t >= _kt0:
            continue                       # davor nichts, danach der ganze Satz
        # v224e EIN MOMENT, EIN BILD - auch fuer das Ankerwort. Es liegt in der
        # Welt und wartet; es ist kein zweiter Untertitel. Steht gerade ein
        # Fliesstext-Block, weicht der Anker (am Beweisbild gesehen: 'WALL' lag
        # auf 'this one'). Damit fuellt er genau die Pausen, in denen sonst
        # nichts im Bild ist - und tritt nie in Konkurrenz.
        # v230m: das gilt auch gegen eine andere KARTE. Bis hierher wich der
        # Anker nur einem Fliesstext-Block; die ausklingende Karte 'BEHIND ME'
        # war kein Hinderungsgrund, und mit der eigenen Stuetzzeile standen
        # drei Texte gleichzeitig im Bild (Ismets Befund an der Wand).
        if any(q is not p and (q.get('front') or q.get('kw_txt'))
               and q.get('start', 0.0) <= t
               < q.get('end', 0.0) + float(q.get('aus') if q.get('aus')
                                           is not None else
                                           (0.15 if q.get('tpl') == 'flow'
                                            else 0.40))
               for q in plans):
            continue
        # v230n: und es weicht der EIGENEN Stuetzzeile. Der bisherige Riegel
        # verglich nur mit ANDEREN Plaenen (`q is not p`) - die Stuetzzeile
        # gehoert aber zur selben Karte, und genau sie lag auf dem Ankerwort
        # ('THIS ONE STICKS' quer ueber 'WALL', Ismets Screenshot).
        # Es weicht nur, wo sie es WIRKLICH ueberdeckt: die Stuetzzeile steht
        # oft ganz woanders im Bild, und dort ist das Ankerwort richtig
        # (v221 - das Ortswort liegt vor dem Satz schon da).
        _ank = p.get('anker_arr')
        if _ank is not None:
            _ax0 = float(p.get('cx', W / 2)) - _ank.shape[1] / 2.0
            _ax1 = _ax0 + _ank.shape[1]
            _ay0 = float(p.get('cy', H * 0.45)) - _ank.shape[0] / 2.0
            _ay1 = _ay0 + _ank.shape[0]
            _deckt = False
            for _it in (p.get('small') or []):
                _sa = _it.get('arr')
                if _sa is None or _it.get('cx') is None:
                    continue
                if not (isinstance(_it.get('i'), int)
                        and 0 <= _it['i'] < len(words)):
                    continue
                if t < float(words[_it['i']]['start']) - 0.07:
                    continue               # dieses Wort steht noch nicht
                _sx0 = float(_it['cx']) - _sa.shape[1] / 2.0
                _sy0 = float(_it['cy']) - _sa.shape[0] / 2.0
                if (min(_ax1, _sx0 + _sa.shape[1]) - max(_ax0, _sx0) > 8
                        and min(_ay1, _sy0 + _sa.shape[0])
                        - max(_ay0, _sy0) > 8):
                    _deckt = True
                    break
            if _deckt:
                continue
        _adt = t - _at0
        # v224d: die Wandmessung MUSS hier auch laufen. Sie stand nur im
        # ground-Zweig, und der greift erst, wenn die Karte im Anzeigefenster
        # ist - das Ankerwort liegt davor. Ergebnis war ein Ankerwort in der
        # alten, bildbreiten Fassung an der alten Stelle: neben der Wand statt
        # darauf (am Beweisbild belegt). Idempotent ueber `_pose_done`.
        if (p.get('szene') == 'wand' and not p.get('lying')
                and not p.get('glass') and not p.get('_pose_done')
                and p.get('flat_arr') is not None and depth_n is not None):
            _wand_aufbereiten(p)
        _asd = scene_shift(p)
        _aop = min(_adt / 0.35, 1.0)       # ruhig einblenden, es LIEGT ja da
        if p.get('scene_ground') or p.get('broll'):
            paste_scene(comp, p['anker_arr'],
                        p.get('cx', W / 2) + _asd[0],
                        p.get('cy', H * 0.45) + _asd[1], W, H, scale=1.0,
                        opacity=_aop * 0.97, refract=0.0, ripple=0.12,
                        grain=2.2, occ=occ_for(p), grain_seed=_gs)
        else:
            paste(comp, p['anker_arr'], p.get('cx', W / 2) + _asd[0],
                  p.get('cy', H * 0.45) + _asd[1], W, H, opacity=_aop)

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
        x_dur = (p.get('aus') if p.get('aus') is not None else
                 (0.15 if p['tpl'] == 'flow' else
                  0.20 + 0.12 * min(ah / (H * 0.15), 1.0)))
        over = t - p['end']
        if p.get('power', 2) >= 3:
            over -= 0.04
        g_out = exit_env(over, x_dur)
        x_sc, x_dv = exit_pose(over, x_dur)
        tdx, tdy = track_offset(p, face_xy, cfg)
        # v101j: Beruehrungs-Impuls verschiebt den Text federnd
        tdx += p.get('_hand_dx', 0.0)
        tdy += p.get('_hand_dy', 0.0)
        # v161: der Objekt-Anker zieht den Text mit seinem Gegenstand mit
        tdx += p.get('_ank_dx', 0.0)
        tdy += p.get('_ank_dy', 0.0)
        # v230h KEIN VERSATZ SCHIEBT TEXT AUS DEM BILD.
        # fit_into_frame misst die RUHELAGE eines Moments; hier oben kommen
        # danach Gesichts-Tracking (bis +-30 px), Hand-Impuls und
        # Objekt-Anker dazu. In Ismets Render lag 'CAPTIONS LOOK THE' nach
        # dem Riegel bei 0.988 W - und wurde vom Tracking ueber die Kante
        # geschoben (gemessen: Text an der Bildkante in 35 von 361 Bildern).
        # Der Riegel gehoert deshalb auch HIER hin, wo der Versatz feststeht.
        # Die Bewegung bleibt sichtbar, sie endet nur an der Bildkante.
        _ib = p.get('_ink')
        if _ib and (_ib[1] - _ib[0]) < W - 4:
            tdx = min(max(tdx, 2.0 - _ib[0]), (W - 2.0) - _ib[1])
        if p.get('front_layer') and p['tpl'] == 'ground':
            # Boden-Text VOR der Person (kein freier Boden im Bild): liegt
            # perspektivisch flach ueber allem - lesbar statt unsichtbar.
            # Basis ist der SPRECH-Zeitpunkt, nicht der vorgezogene Start.
            _dtf = t - p.get('t_word', p.get('t0', p['start']))
            if _dtf >= 0:
                _sdx, _sdy = scene_shift(p)
                _e = smoothstep(_dtf / 0.75)
                arr_fl, adx_fl, dy_fl, asc_fl, aop_fl = anim_apply(p, p['arr'], aud, _dtf)
                # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
                paste_scene(comp, arr_fl, p.get('cx', W / 2) + _sdx + adx_fl,
                            p['cy'] + _sdy + dy_fl + (1 - _e) * H * 0.03,
                            W, H, scale=(0.97 + 0.03 * _e) * asc_fl,
                            opacity=min(_dtf / 0.4, 1) * g_out * aop_fl * 0.92,
                            refract=0.0, ripple=0.05, grain=1.6,
                            occ=None, blur=0.0, grain_seed=_gs)
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
                # v143: plan-eigener Spielraum, falls gesetzt - sonst wie bisher.
                lim = float(p.get('fol_lim', W * 0.045))
                fdx = max(-lim, min(fp[0] * 0.6, lim))
                fdy = max(-lim * 0.5, min(fp[1] * 0.5, lim * 0.5))
            # v176: Beruehrungs-Feder auf den Flow-Block. Der Impuls wurde
            # bisher NUR auf Keyword-Sprites addiert (track_offset /
            # scene_shift) - ein Flow-Chunk konnte gestossen werden und
            # blieb trotzdem stehen.
            fdx += p.get('_hand_dx', 0.0)
            fdy += p.get('_hand_dy', 0.0)
            # v182 AKTIVES WORT (Karaoke-Emphase). Der dominante Caption-Stil
            # 2026: das GERADE gesprochene Wort steht vorn - leicht groesser
            # und in voller Deckkraft - waehrend die schon gesprochenen
            # abdimmen. Das bindet den Blick ans Wort statt an den Block und
            # ist der Unterschied zwischen "Text steht da" und "Text spricht
            # mit". Bewusst OHNE Farbwechsel: der Akzentton gehoert im
            # Hausstil dem Schlusswort, zwei Akzente nebeneinander wuerden
            # sich gegenseitig entwerten.
            _akt_i = None
            if cfg['effects'].get('caption_aktivwort', True):
                _kand = [it for it in p['front']
                         if words[it['i']]['start'] <= t + 0.07]
                if _kand:
                    _akt_i = max(_kand,
                                 key=lambda q: words[q['i']]['start'])['i']
            # v185 KEINE FARB-KARAOKE MEHR. Bis v184 faerbte der Viral-Look
            # das gesprochene Wort in einen festen Gelb-Ton. Ismets Urteil am
            # Ergebnis: "Gelbakzent, die sind ausgelutscht." Stimmt - das ist
            # der Marker jedes CapCut/Opus-Templates, und der Akzent landete
            # ausserdem auf Fuellwoertern (AND, THAT, TO, IS), wo er nichts
            # betont. Die Emphase traegt jetzt in ALLEN Looks das Paar
            # Groessen-Pop (aktiv) und Dimmen auf 70 % (vergangen), ohne
            # Farbwechsel.
            _ruhig = bool(cfg['effects'].get('caption_ruhig', True))
            # v193 ANIMATION AUF DEM FLIESS-BLOCK. Bis v192 lief anim_apply
            # ausschliesslich auf Keyword-Karten (p['arr'] / p['f_arr']) - ein
            # Fliess-Block KONNTE gar keine Animation tragen, egal was
            # eingestellt war. Genau das war die Luecke, die den Block-Editor
            # bis hierher unmoeglich machte.
            # Umsetzung: jedes Wort bekommt einen eigenen Zustandstraeger UND
            # seine EIGENE Zeitbasis - gerechnet ab dem Moment, in dem es
            # erscheint.
            # v194a: das war in v193 falsch. Dort liefen alle Woerter gegen die
            # BLOCK-Zeit, damit sich der Block "als Einheit" bewegt. Ein Block
            # baut sich hier aber Wort fuer Wort auf (Karaoke-Aufbau, v182).
            # Wenn das dritte Wort 0.6 s nach Blockbeginn erscheint, ist eine
            # Animation, die 0.22 s dauert, laengst vorbei - sie lief nur auf
            # dem ERSTEN Wort und dort nur drei Bilder lang.
            # Am Render gemessen (Block 3.24-4.30 s, anim 'explosion'):
            # Unterschied zum Render ohne Animation 4.2 bei 3.28 s, 2.9 bei
            # 3.32 s und ab 3.38 s nur noch 0.3 - also praktisch nichts.
            # Genau das ist Ismets Befund "ist immer noch dasselbe".
            # v194a, zweiter Anlauf: die Zeitbasis allein reichte nicht. Der
            # eigentliche Grund ist der WORT-FUER-WORT-AUFBAU. Ein Block, dessen
            # Woerter nacheinander erscheinen, kann nicht "explodieren" - egal
            # wann die Kurve laeuft, es ist immer nur ein Wort in Bewegung.
            # Wer im Editor eine Animation auf einen BLOCK legt, meint den
            # Block. Also steht bei gesetzter Animation der ganze Block ab
            # seinem Beginn im Bild und bewegt sich als Einheit.
            # Der Karaoke-Aufbau bleibt fuer alle anderen Bloecke unveraendert -
            # er ist die Handschrift des Produkts, nur eben nicht vereinbar mit
            # einer Block-Animation.
            _banim = p.get('anim') if p.get('_user') else None
            _bdt = t - float(p.get('start', 0.0))
            for it in p['front']:
                wd = words[it['i']]
                # Mit Block-Animation zaehlt die BLOCKzeit fuer alle Woerter:
                # sie erscheinen gemeinsam und bewegen sich gemeinsam.
                dt = ((_bdt + 0.07) if _banim else (t - wd['start'] + 0.07))
                if dt < 0:
                    continue
                # Nur die VERGANGENEN Woerter dimmen; das aktive bleibt voll
                # und bekommt einen kleinen Groessen-Pop, der ueber 0.22 s
                # abklingt (kein Dauerzustand, sonst zappelt der Satz).
                _ist_akt = (it['i'] == _akt_i)
                _dim = 1.0
                _pop = 1.0
                if _akt_i is not None:
                    if _ist_akt:
                        _pop = 1.0 + (0.055 * (0.45 if _ruhig else 1.0)) \
                            * (1 - smoothstep(min(dt / 0.22, 1.0)))
                    elif it.get('role') not in ('key', 'punch'):
                        # v190: das Abdimmen laeuft ueber 0.25 s statt als
                        # Helligkeitssprung. Bei drei Woertern je Sekunde
                        # sprang bis v189 mit JEDEM Wort ein Nachbar von
                        # 100 auf 70 % - ein Teil des Flimmerns kam daher.
                        _dtd = t - (words[_akt_i]['start'] if _akt_i is not None
                                    else wd['start'])
                        _dim = (1.0 - 0.30 * smoothstep(min(max(_dtd, 0) / 0.25, 1.0))
                                if _ruhig else 0.70)
                _arr = it['arr']
                if it.get('role') in ('key', 'punch') and it.get('letters'):
                    n = len(it['letters'])
                    # v151: Aufdeck-Tempo kann aus der gemessenen Referenz
                    # kommen. 0.17 s je Wort ist unser Hausmass; das zweite
                    # Vorbild deckt mit 0.087 s je ZEICHEN auf, also rund
                    # doppelt so schnell bei einem 8-Zeichen-Wort.
                    _rv = float((cfg.get('effects', {}) or {}).get(
                        'reveal_letter_s') or 0)
                    _rvd = max(0.06, min(0.40, _rv * n)) if _rv else 0.17
                    reveal = ease_out(dt / (_rvd * (1 + 0.08 * hand_jitter(it['i']))))
                    vis_px = None
                    k_full = int(min(reveal * n, n))
                    if k_full < n:
                        frac = reveal * n - k_full
                        l0, l1 = it['letters'][k_full]
                        vis_px = (l0 + (l1 - l0) * frac) + 40
                    # dezenter Settle: Keyword landet minimal groesser und
                    # setzt sich weich auf 1.0 (gezielte, ruhige Bewegung)
                    k_settle = 1.0 + (0.02 if _ruhig else 0.05) \
                        * (1 - smoothstep(min(dt / 0.42, 1.0)))
                    _pcx = it['cx'] + fdx - (0 if vis_px is None
                                             else (_arr.shape[1] - vis_px) / 2)
                    _pcy = it['cy'] + fdy + x_dv * _arr.shape[0]
                    _psc = x_sc * k_settle * _pop
                    # v184: die Punchline steht HINTER der Person (Ref C).
                    # Die Silhouette wird pro Frame an der Zielposition aus
                    # der Sprite-Alpha gestanzt - Person bewegt sich, die
                    # Ueberdeckung folgt ihr.
                    _kop = 1.0
                    if _banim:
                        # v193: auch das Anker-/Schlusswort des Blocks folgt
                        # der gewaehlten Animation. Sonst animierte der Block
                        # um sein wichtigstes Wort herum.
                        _ap = it.get('_a')
                        if _ap is None:
                            _ap = {'anim': _banim,
                                   'start': float(p['start']),
                                   'kw_i': int(it['i'])}
                            it['_a'] = _ap
                        _arr, _kdx, _kdy, _ksc, _kop = anim_apply(
                            _ap, _arr, aud, _bdt)
                        _pcx += _kdx
                        _pcy += _kdy
                        _psc *= _ksc
                    if (p.get('hinter_ok') and it.get('role') == 'punch'
                            and alpha is not None
                            and cfg['effects'].get('caption_hinter', True)):
                        _arr = occlude_sprite(_arr, _pcx, _pcy, W, H,
                                              _psc, alpha_p)
                    paste(comp, _arr, _pcx, _pcy,
                          W, H, scale=_psc,
                          opacity=g_out * _dim * _kop, crop_w=vis_px)
                else:
                    # v190 RUHE. Bis v189 flog JEDES Wort ein: 2 % Bildhoehe
                    # von unten, von 86 % hochskaliert, mit ease_back-
                    # Overshoot und gestreutem Timing. Bei drei Woertern je
                    # Sekunde ist das Dauerbewegung - Ismets "alles zu sehr
                    # am Zucken". Gemessen war der Effekt-Anteil daran null:
                    # mit Beat, Kamera, Pop und Motion-Blur AUS blieb die
                    # Unruhe unveraendert (3.09 statt 2.84 Promille je
                    # Frame). Es war der Wort-Einflug selbst.
                    # Ruhig heisst: kein Positionssprung, kein Ueberschwingen,
                    # nur ein knapper Scale-Ansatz und die Blende.
                    if _ruhig:
                        e = ease_out(min(dt / 0.16, 1.0))
                        _dy_in, _sc_in = 0.0, 0.97 + 0.03 * e
                    else:
                        e = ease_back(dt / (0.24 * (1 + 0.08 * hand_jitter(it['i']))))
                        _dy_in, _sc_in = (1 - e) * H * 0.020, 0.86 + 0.14 * e
                    _adx = _ady = 0.0
                    _asc = _aop = 1.0
                    if _banim:
                        _ap = it.get('_a')
                        if _ap is None:
                            _ap = {'anim': _banim,
                                   'start': float(p['start']),
                                   'kw_i': int(it['i'])}
                            it['_a'] = _ap
                        _arr, _adx, _ady, _asc, _aop = anim_apply(
                            _ap, _arr, aud, _bdt)
                    paste(comp, _arr,
                          it['cx'] + fdx + _adx,
                          it['cy'] + fdy + _dy_in + _ady + x_dv * _arr.shape[0],
                          W, H, scale=_sc_in * x_sc * _pop * _asc,
                          opacity=min(dt / (0.16 if _ruhig else 0.10), 1)
                          * g_out * _dim * _aop)
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
        # v230g DIE STUETZZEILE HAENGT AM WORT, NICHT AN DER KARTE.
        # Die uebrigen Woerter der Gruppe (p['small']) sind wortgetaktet
        # gebaut (eigenes dt je Wort, v82-Lesevorlauf). Gezeichnet wurden sie
        # aber nur INNERHALB der Zeichenzweige, und die sind gegen die
        # KARTEN-Uhr verriegelt (`dt >= 0`). Liegt das Schluesselwort nicht am
        # Gruppenanfang, ist zwischen dem ersten gesprochenen Wort und dem
        # Erscheinen der Karte GAR NICHTS im Bild - gemessen bis 0.84 s
        # voellig leer, waehrend drei Woerter gesprochen werden, und das
        # betrifft typisch den Videoanfang (im Hook-Fenster ist `small` auch
        # bei Dichte 'akzente' gefuellt). Nur `behind` machte es richtig.
        # Deshalb hier, VOR der Weiche: solange die Karte noch nicht laeuft,
        # traegt die Stuetzzeile das Bild allein. Ab dt >= 0 bleibt alles wie
        # gehabt - die Zweige zeichnen sie mit ihren eigenen Versaetzen.
        # v230m: der `behind`-Zweig hat als EINZIGER kein `dt >= 0` und
        # zeichnet die Stuetzzeile schon vorher - genau deshalb war er in
        # v230g der Massstab. Der Vorlauf hier oben kam bei ihm also OBENDRAUF,
        # mit dem Gesichts-Versatz statt ohne: dieselbe Zeile stand zweimal im
        # Bild, um genau (tdx, tdy) verschoben (an Ismets Render gemessen:
        # 'THIS ONE FLOATS' zweimal, 58 px rechts und 75 px tiefer).
        if dt < 0 and p.get('small') and p['tpl'] != 'behind':
            draw_small(p, g_out, tdx, tdy, x_sc, x_dv)
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
            # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
            paste(comp, arr_c,
                  p['cx'] + tdx + adx - (0 if vis_px is None
                                         else (p['arr'].shape[1] - vis_px) / 2),
                  p['cy'] + tdy + ady + x_dv * p['arr'].shape[0],
                  W, H, scale=asc * x_sc,
                  opacity=g_out * aop, crop_w=vis_px)
            draw_small(p, g_out, tdx, tdy, x_sc, x_dv)
        elif p['tpl'] == 'ground' and dt >= 0:
            _wand_aufbereiten(p)
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
            # v101i: Wand-Texte haengen am WAND-Track (obere Bildhaelfte,
            # Person ausgeschlossen) - der Boden-Track hat andere Parallaxe.
            _is_wall = (p.get('szene') == 'wand' and not p.get('lying'))
            _hc = H_cum_wall if (_is_wall and H_cum_wall is not None) else H_cum
            _tg = wall_gen if (_is_wall and H_cum_wall is not None) else track_gen
            tracked = (g_broll and p.get('track3d') and _hc is not None)
            if tracked:
                # Planares Kamera-Tracking: Referenz beim ersten aktiven Frame,
                # danach bewegt die akkumulierte Homographie den Text wie ein
                # Objekt in der Welt (waechst, kippt, zieht vorbei).
                if 'H_ref' not in p or p.get('H_gen') != _tg:
                    p['H_ref'] = np.linalg.inv(_hc)
                    p['H_gen'] = _tg
                H_rel = _hc @ p['H_ref']
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
                    # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
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
                                    occ=occ_g, blur=cam_blur, grain_seed=_gs)
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
                    # v219: die Wandmessung steht jetzt GANZ OBEN im
                    # ground-Zweig (vor allen drei Zeichenwegen). Hier bleibt
                    # nur der Boden: liegender Text richtet sich nach der
                    # gemessenen Bodenneigung.
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
                                    grain=g_grain, occ=occ_g, blur=cam_blur,
                                    grain_seed=_gs)
                    else:
                        arr_s, adx_s, dy_s, asc_s, aop_s = anim_apply(p, p['arr'], aud, dt)
                        # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
                        paste_scene(comp, arr_s, p.get('cx', W / 2) + sdx + adx_s,
                                    p['cy'] + sdy + dy_s + (1 - e) * H * 0.03,
                                    W, H, scale=(0.97 + 0.03 * e) * live * asc_s,
                                    opacity=min(dt / 0.4, 1) * g_out * aop_s * g_opac,
                                    refract=g_refract, ripple=g_ripple, grain=g_grain,
                                    occ=occ_g, grain_seed=_gs,
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
                # v230g: kein Abzug der halben Hoehenzunahme (gemessen)
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
    # v101j HAND-OCCLUSION: bei frischem Kontakt (letzte 0.5s) liegt die Hand
    # VOR dem Text - lokal um die Fingerspitzen wird die Person (Matte) wieder
    # ueber den Text gelegt. Der Impuls + die verdeckende Hand zusammen
    # verkaufen die Beruehrung als echt.
    if hand_tips and alpha is not None \
            and any(t - p.get('_hand_touch_t', -9.0) < 0.5 for p in active):
        _pm_h = person_mask(alpha)
        for (_hx0, _hy0, _, _) in hand_tips:
            _r = int(H * 0.085)
            _x1 = max(int(_hx0) - _r, 0); _x2 = min(int(_hx0) + _r, W)
            _y1 = max(int(_hy0) - _r, 0); _y2 = min(int(_hy0) + _r, H)
            if _x2 <= _x1 or _y2 <= _y1:
                continue
            _m = _pm_h[_y1:_y2, _x1:_x2].astype(np.float32)
            if _m.max() < 0.2:
                continue
            _m = cv2.GaussianBlur(_m, (0, 0), 2.0)[..., None]
            comp[_y1:_y2, _x1:_x2] = (frame[_y1:_y2, _x1:_x2] * _m
                                      + comp[_y1:_y2, _x1:_x2] * (1 - _m))
    return comp

# ---------------------------------------------------------------- main
def main():
    _zt_main = time.time()          # v227: Gesamtzeit fuer den Zeit-Report
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
    ap.add_argument('--watermark-split', action='store_true',
                    help='Free-Tier: sauber rendern, Master behalten und die '
                         'Ausgabe per identischem Overlay wassermarkieren '
                         '(Kauf schaltet ohne Neu-Render frei)')
    ap.add_argument('--watermark', action='store_true',
                    help='Dezentes DouchkoVE-Wasserzeichen einblenden (Free-Tier)')
    ap.add_argument('--alpha-export', action='store_true',
                    help='Nur die Caption-Ebene rendern: ProRes-4444-MOV mit '
                         'echtem Alpha (inkl. Behind-Loechern) fuer den '
                         'Schnittplatz. SFX kommen als eigene Tonspur mit.')
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding='utf-8'))
    # v101h Alpha-Export: alles, was NUR auf dem Hintergrundbild funktioniert
    # (Kamera-Moves, Freeze, Split-Screen, BG-Blur), ist auf einer Overlay-
    # Ebene nicht transportierbar - die Ebene muss deckungsgleich ueber dem
    # Original des Kunden liegen. Deshalb hart aus, klar geloggt. dim/Schatten/
    # Occlusion bleiben: die werden korrekt zu (teil-)transparenten Pixeln.
    if args.alpha_export:
        if args.window:
            sys.exit('ERROR: --alpha-export is only for the full render.')
        cfg.setdefault('camera', {})
        cfg['camera'].update({'strength': 0.0, 'crash': 0.0, 'whip': False,
                              'keyword_rotation': [], 'side_rotation': []})
        cfg.setdefault('effects', {})
        cfg['effects'].update({'freeze_frame': 0.0, 'split_screen': 0.0,
                               'bg_blur': 0.0, 'contact_sheet': False})
        cfg.setdefault('keywords', {})['silent_score'] = False
        cfg.setdefault('output', {})['master'] = False
        args.watermark = False
        args.watermark_split = False
        print('Alpha export: caption layer (ProRes 4444) - camera/freeze/'
              'split/background blur off, the layer stays aligned with the original')
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
    # v230b3: Das Live-Bild liegt NEBEN dem Ergebnis, im selben Job-Ordner.
    # Kein eigener Schalter und kein Pfad-Parameter: was der Server ausliefert,
    # soll nicht davon abhaengen, dass jemand ein Flag setzt.
    _vorschau_pfad = os.path.join(os.path.dirname(os.path.abspath(out_path))
                                  or '.', 'vorschau.jpg')
    # Ein Bild vom VORIGEN Lauf desselben Jobs (Re-Render, Momente-Editor)
    # waere schlimmer als keines: der Kunde saehe minutenlang ein Standbild,
    # das nichts mit dem laufenden Render zu tun hat.
    try:
        os.remove(_vorschau_pfad)
    except OSError:
        pass
    if not args.transcribe_only:
        ensure_models()          # Transkript-Kontrolle braucht keine KI-Modelle

    src_w, src_h, fps, fps_str, src_dur = probe(args.input)
    n_frames = int(src_dur * fps)
    # v149: 'height' ist das Zielmass der KURZEN Kante, nicht der Bildhoehe.
    # Vorher wurde es stur als Hoehe genommen: eine 1080x1920-Aufnahme kam als
    # 607x1080 heraus, also SCHMALER als die Quelle - im Hochformat hat die
    # Engine damit jedes Video kleingerechnet. Quer war es zufaellig richtig,
    # deshalb ist es nie aufgefallen. 'quality: 4k' hebt das Ziel auf 2160.
    _kurz = int(cfg['output'].get('height', 1080))
    if str(cfg['output'].get('quality', '')).lower() in ('4k', 'uhd'):
        _kurz = max(_kurz, 2160)
    H = _kurz if src_w >= src_h else int(round(_kurz * src_h / max(src_w, 1)))
    # NIE hochskalieren. Aus 1080p wird kein 4K, es wird nur ein grosses,
    # weiches 1080p - teurer zu rechnen und schlechter anzusehen.
    H = min(H, src_h)
    H = int(round(H / 2) * 2)
    if args.preview:
        # v187: auch die Vorschau rechnet 540 als KURZE KANTE (v149-Regel).
        # Als Bildhoehe genommen ergab ein 540x960-Hochformat nur 304 px
        # Breite - ein Fuenftel der Flaeche des Endergebnisses, und genau an
        # diesem Bild beurteilt die Desktop-GUI die Looks.
        H = 540 if src_w >= src_h else int(round(540 * src_h / max(src_w, 1)))
        H = int(round(min(H, src_h) / 2) * 2)
        cfg['output']['master'] = False
        cfg['output']['crf'] = 30
        cfg['output']['speed'] = 'schnell'
        print("PREVIEW MODE: 540p, fast encode")
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
        print(f"Input detected as {_mode.upper()} ({src_w}x{src_h}, "
              f"AR {_ar:.2f}). Portrait optimisations disabled.")
    print(f"Input: {src_w}x{src_h} @ {fps:.3g}fps, {n_frames} frames -> output {W}x{H}")

    # --- Transkription
    # Transkript-Cache neben dem Video automatisch nutzen (kein API-Aufruf)
    if not args.transcript:
        auto_t = os.path.splitext(args.input)[0] + '_transcript2.json'
        if os.path.exists(auto_t):
            args.transcript = auto_t
    # v228d: Denk-Aufwand der KI aus der Config uebernehmen (Standard 'low').
    global AI_DENKEN, AI_DENKEN_FRAGE
    AI_DENKEN = str(cfg['keywords'].get('ai_denken', 'aus')).strip().lower()
    # v230c2: dazu die Feineinstellung je Frage. Sie steht im LOG, damit die
    # naechste Zeitmessung beantwortbar ist, ohne die Config zu kennen - genau
    # daran ist v228d/v228e zweimal vorbeigelaufen.
    _df = cfg['keywords'].get('ai_denken_frage') or {}
    AI_DENKEN_FRAGE = {str(k).strip().lower(): str(v).strip().lower()
                       for k, v in _df.items()} if isinstance(_df, dict) else {}
    print(_denk_log_zeile())
    _zt_tr = time.time()
    if args.transcript and os.path.exists(args.transcript):
        words = json.load(open(args.transcript, encoding='utf-8'))
        print(f"Transcript loaded: {len(words)} words")
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
                      f"re-encoded at {br_kbps} kbps")
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.input,
                                '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'aac',
                                '-b:a', f'{br_kbps}k', wav], check=True)
            words = transcribe(wav, cfg.get('language', 'de'), cfg)
        tpath = os.path.splitext(args.input)[0] + '_transcript2.json'
        json.dump(words, open(tpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"{len(words)} words, transcript saved: {tpath}")

    if args.transcribe_only:
        print('Transcript ready - you can review it now.')
        sys.exit(0)

    # v230ag: Schriftsystem PRUEFEN, bevor gerechnet wird. Arabisch, Hebraeisch,
    # Devanagari und Thai kann der Zeichenpfad nicht setzen (er zeichnet
    # Buchstabe fuer Buchstabe, diese Schriften brauchen den ganzen String am
    # Stueck). Ohne diese Pruefung liefe ein voller Render durch und der Kunde
    # bekaeme leere Kaesten - fuer sein Guthaben. Hier abbrechen heisst:
    # Meldung im Klartext, und der Server erstattet automatisch.
    # v230ak: den Speicherdeckel EINMAL ermitteln - die Wache im Bildlauf
    # braucht ihn, und im Log soll von Anfang an stehen, womit gerechnet wird.
    global _MEM_DECKEL
    _MEM_DECKEL = _mem_limit_gb()
    print(f"Memory limit: "
          + (f"{_MEM_DECKEL:.1f} GB (container)" if _MEM_DECKEL
             else "none (host memory)"))

    _fehl = schrift_unsupported(' '.join(str(w.get('word', '')) for w in words))
    if _fehl:
        sys.exit(f'ERROR: {_fehl} captions are not supported yet. Your credits '
                 f'were not used. Latin, Cyrillic, Greek, Chinese, Japanese '
                 f'and Korean all work.')

    # --- Wort-Timing am echten Audio nachjustieren
    voice_wav = os.path.join(tempfile.gettempdir(), 'dve_voice.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', args.input, '-vn',
                    '-ac', '1', '-ar', '44100', voice_wav], check=False)
    if os.path.exists(voice_wav):
        words, avg_shift = refine_word_times(words, voice_wav)
        print(f"Word timing adjusted (average correction {avg_shift:.0f} ms)")
    else:
        voice_wav = None
    # v101 Betonungs-Typografie: Sprech-Pegel pro Wort einmal messen -
    # compose_phrase/compose_flow setzen laute Woerter typografisch schwerer.
    _zt_x = zt('transkript+audio', _zt_tr)
    loud_map = _word_loudness(words, voice_wav) if voice_wav else {}
    if loud_map:
        _nl = sum(1 for v in loud_map.values() if v == '!')
        print(f"Emphasis: {_nl} loud / {len(loud_map) - _nl} quiet words "
              f"set typographically")

    # --- Tracking + Plaene
    speed = str(cfg['output'].get('speed', 'standard')).lower()
    det_step, md_mult, x264_preset = {
        'schnell':  (3, 0.7, 'veryfast'),
        'standard': (2, 1.0, cfg['output'].get('preset', 'medium')),
        'maximal':  (1, 1.2, 'slow')}.get(speed, (2, 1.0, 'medium'))
    _zt_x = zt('lautheit', _zt_x)
    face, has_face, face_w, cut_frames, faces_seq, multi_person = track_faces(
        args.input, W, H, fps_str, det_step)
    _zt_x = zt('gesichter-durchgang', _zt_x)
    # v96b: Automatischer Modus-Schalter. Kaum Gesicht = Erzaehler/Voiceover ->
    # zentrierte editoriale Captions; ein Gesicht = Talking-Head; mehrere =
    # Gespraech. Ismet muss nichts umstellen, der Render erkennt es selbst.
    face_frac = float(has_face.mean()) if len(has_face) else 0.0
    video_mode = _video_mode(face_frac, multi_person)
    print(f"Mode detected: {video_mode} "
          f"(face in {face_frac*100:.0f}% of frames"
          + (", multiple people" if multi_person else "") + ")")
    k2 = 41
    kern2 = np.ones(k2) / k2
    face_stable = np.stack([np.convolve(np.pad(face[:, j], k2 // 2, mode='edge'),
                                        kern2, 'valid')[:len(face)] for j in range(2)], axis=1)
    fps_i = fps
    # v230c1 DIE SCHLUESSELWORT-FRAGE DAUERT AM LAENGSTEN - ALSO WIRD AUCH
    # IHRE WARTEZEIT GENUTZT.
    # v230c0 hat die TEXTFLUSS-Frage vorgezogen; die Schluesselwort-Frage
    # (ai_direct, in Ismets Log 55 s) liegt aber davor, und waehrend sie
    # laeuft passiert weiterhin nichts. Zwei Analysen brauchen von ihr GAR
    # NICHTS - sie brauchen nur das Video und die Schnittzeiten, und beides
    # steht hier schon fest:
    #   * die Farbwelt-Abtastung (welche Toene hat die Szene je Shot)
    #   * die Raum-Karte (wo ist das Bild besetzt)
    # Sie laufen deshalb ab hier im Hintergrund und werden unten abgeholt.
    # Die Frage selbst wird dadurch NICHT schneller und auch nicht anders
    # gestellt - es wartet nur niemand mehr untaetig. (Schneller antworten
    # wuerde weniger Nachdenken heissen, und das war v228d: Ismets Urteil
    # danach war "Qualitaet ist sehr schlecht geworden".)
    cut_times = [c / float(fps_i) for c in cut_frames] if fps_i else []
    _bild_erg = {}
    _bild_thread = None
    _c_style_frueh = str(cfg.get('colors', {}).get('style', 'auto')).lower()
    _will_palette = (_c_style_frueh not in ('schwarz', 'weiss')
                     and bool(cfg.get('colors', {}).get('adaptive', True)))
    _will_raum = bool(cfg['effects'].get('adaptive_place', True))
    if _will_palette or _will_raum:
        try:
            import threading as _th_b

            def _bild_lauf():
                if _will_palette:
                    try:
                        _bild_erg['palette'] = scene_palette_sampler(
                            args.input, cut_times,
                            min_contrast=float(cfg['effects'].get(
                                'caption_contrast', 4.5)),
                            kontur=float(cfg['effects'].get(
                                'caption_kontur', 1.0) or 0) > 0.01)
                    except Exception as _e3:
                        _bild_erg['palette_fehler'] = _e3
                if _will_raum:
                    try:
                        _bild_erg['raum'] = scene_space_sampler(args.input,
                                                                cut_times)
                    except Exception as _e4:
                        _bild_erg['raum_fehler'] = _e4
            # Daemon, aus demselben Grund wie v230c0: ein Absturz darf nicht
            # warten muessen, bis ffmpeg fertig ist.
            _bild_thread = _th_b.Thread(target=_bild_lauf, daemon=True)
            _bild_thread.start()
        except Exception as _e:
            print(f"Picture analysis: could not start early "
                  f"({type(_e).__name__}), running it in order.")
            _bild_thread = None

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
    _beat_ts = None            # v101c: Beat-Zeitpunkte fuers Beat-Grid
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
                print(f"Music beat: ~{bpm} BPM (confidence {conf:.2f}, "
                      f"weight {gain:.2f})")
            else:
                print("Music beat: no clear tempo (confidence too low) - "
                      "nur Sprech-Onset")
            _beat_ts = beat_grid_times(beat_env, fps, conf, bpm)
    else:
        aud_rms = aud_bass = aud_onset = np.zeros(n_est, np.float32)
    fx_map = None
    _regie_wahl = False        # v99a: kam die Keyword-WAHL wirklich von der KI?
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
                _regie_wahl = bool(fx_map)
            else:
                print("Style references changed - old direction discarded, the AI plans again")
        if fx_map is None:
            print("AI director is analysing the transcript ...")
            _zt_ki = time.time()
            fx_map = ai_direct(words, cfg.get('language', 'de'),
                               cfg['keywords'].get('ai_model', 'gpt-5'),
                               voice_wav=voice_wav,
                               validate=cfg['keywords'].get('ai_validate', True))
            zt('ki-textregie', _zt_ki)
            _regie_wahl = bool(fx_map)
            # v99a: Selbstbezug VOR face_cover/Vision einhaengen, damit
            # erzeugte Momente den Nahaufnahme-Check (behind unsichtbar?)
            # mitbekommen. Der Aufruf weiter unten bleibt (Cache/Heuristik)
            # und ist idempotent.
            fx_map = _self_ref_intent(fx_map, words)
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
                # v228c BILD-REGIE UND OBJEKT-ANKER LAUFEN GLEICHZEITIG.
                # An Ismets Job-Log gemessen: 39.5 s + 25.3 s, streng
                # hintereinander - und beide warten nur auf dieselbe
                # OpenAI-Schnittstelle. Sie sind voneinander unabhaengig: die
                # eine schreibt 'szene'/'lage'/'nah', die andere 'anker'.
                # Damit sich die beiden Threads nicht in derselben fx_map ins
                # Gehege kommen, bekommt jeder eine KOPIE; danach werden die
                # Felder deterministisch zusammengefuehrt. Das Ergebnis haengt
                # damit NICHT davon ab, wer zuerst fertig wird.
                _mit_anker = bool(cfg['effects'].get('caption_objekt', True))
                _zt_ki = time.time()
                _erg = {}

                def _lauf_szene():
                    return ai_scene_direct(
                        words, copy.deepcopy(fx_map), args.input,
                        cfg['keywords'].get('ai_model', 'gpt-5'),
                        min_power=int(cfg['keywords'].get('vision_min_power', 2)),
                        face_cover=face_cover)

                def _lauf_anker():
                    return ai_objekt_anker(
                        words, copy.deepcopy(fx_map), args.input,
                        cfg['keywords'].get('ai_model', 'gpt-5'),
                        min_power=int(cfg['keywords'].get('vision_min_power', 2)))
                if _mit_anker:
                    try:
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=2) as _ex:
                            _f1 = _ex.submit(_lauf_szene)
                            _f2 = _ex.submit(_lauf_anker)
                            _erg['szene'], _erg['anker'] = _f1.result(), _f2.result()
                    except Exception as _e:
                        print(f"  Vision director: parallel run failed "
                              f"({type(_e).__name__}), running one after another")
                        _erg['szene'] = _lauf_szene()
                        _erg['anker'] = _lauf_anker()
                else:
                    _erg['szene'] = _lauf_szene()
                zt('ki-bildregie+anker', _zt_ki)
                # Zusammenfuehren: die Bild-Regie ist die Grundlage, der Anker
                # steuert nur sein eigenes Feld bei.
                fx_map = merge_anker(_erg.get('szene') or fx_map,
                                     _erg.get('anker'))
            elif fx_map:
                # Vision aus, aber der Backstop soll trotzdem greifen.
                fx_map = _behind_cover_backstop(fx_map, face_cover)
            if fx_map and _regie_wahl:    # v99a: Cache nur fuer echte KI-Wahl
                json.dump({'ref_fp': _ref_fingerprint(),   # v96x: Cache-Gueltigkeit
                           'keywords': [{'i': i, 'fx': v['fx'], 'power': v['power'],
                                         'n': v.get('n', 1),
                                         **({'anim': v['anim']} if v.get('anim') else {}),
                                         **({'szene': v['szene']} if v.get('szene') else {}),
                                         **({'lage': v['lage']} if v.get('lage') else {}),
                                         **({'intent': True} if v.get('intent') else {}),
                                         **({'anker': v['anker']} if v.get('anker') else {})}
                                        for i, v in sorted(fx_map.items())]},
                          open(regie_path, 'w', encoding='utf-8'))
    # v99 Selbstbezug-Backstop: "The captions are behind me" besteht komplett
    # aus Sperrlisten-Woertern - die KI kann dort oft kein Keyword setzen, und
    # ohne API-Key gibt es gar keine Regie. Der deterministische Backstop
    # erzeugt den Moment dann selbst (gleiches Verhalten in KI-, Cache- und
    # Heuristik-Pfad). _had_regie merkt sich, ob die KEYWORD-Wahl von der KI
    # kam - nur dann bleibt die Auto-Heuristik aus.
    # v99a: _regie_wahl statt bool(fx_map) - besteht fx_map NUR aus
    # Selbstbezug-Momenten (KI aus/leer), muss die Auto-Heuristik anbleiben.
    _had_regie = _regie_wahl
    # v159 ORTSANSAGE IN ALLEN PFADEN. Bis v158 hatte _speech_intent
    # GENAU EINE Aufrufstelle - innerhalb ai_direct. ai_direct laeuft
    # aber nicht, wenn (a) kein OPENAI_API_KEY gesetzt ist, (b) die API
    # ausfaellt, oder (c) ein Regie-Cache greift - und (c) ist der
    # Normalfall beim zweiten Render desselben Videos. In all diesen
    # Faellen wurde "der Beweis steht HINTER MIR" komplett ignoriert,
    # obwohl CLAUDE.md die Ansage als Gesetz fuehrt. _self_ref_intent
    # stand aus genau diesem Grund schon hier; _speech_intent gehoert
    # daneben.
    fx_map = _speech_intent(fx_map, words)
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
        print(f"AI director: {len(kw)} keywords chosen")
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
            print(f"Chapter structure: {n_chap} topic changes marked")

    # v101m: Keyword-Markierungen aus dem Text-Editor (Sidecar neben dem Input).
    # Laeuft NACH KI-Regie + Heuristik + Kapiteln -> ist die letzte Instanz.
    _km_path = os.path.splitext(args.input)[0] + '_kwmarks.json'
    if os.path.exists(_km_path):
        try:
            _kmr = json.load(open(_km_path, encoding='utf-8'))
            _kmr = {int(k): int(v) for k, v in _kmr.items() if int(v) in (1, -1)}
            kw, fx_map = apply_keyword_marks(kw, fx_map, words, _kmr, cfg)
        except Exception as _kme:
            print(f"Text markers ignored ({type(_kme).__name__})")

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
            _anim = anim_for(txt, anim_ctx(words, i, n)) or ''
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
    # v101t: Akzent-Plan ZUSAMMEN mit den Momenten ausgeben, damit der Momente-
    # Editor die Akzente zeigen + editieren kann. Editierte Datei behaelt ihre
    # Werte (wie die Momente); sonst schlaegt KI/Heuristik vor. Der Voll-Render
    # laedt danach nur noch (editierte Datei gewinnt).
    if (cfg.get('accents') or {}).get('auto', False):
        _acc_path0 = os.path.splitext(args.input)[0] + '_accents.json'
        _acc_prof0 = (cfg.get('accents') or {}).get('profile')
        if os.path.exists(_acc_path0):
            try:
                _acc_list0 = sanitize_accents(
                    json.load(open(_acc_path0, encoding='utf-8')), words,
                    _acc_prof0, kw)
            except Exception:
                _acc_list0 = []
        else:
            _acc_list0 = ai_accents(
                words, cfg.get('language', 'auto'),
                str((cfg.get('accents') or {}).get('ai_model', 'gpt-5')),
                _acc_prof0, cfg, kw)
        try:
            json.dump(_acc_list0, open(_acc_path0, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
    # --- v193 BLOCK-EDITOR: Bloecke exportieren und Nutzer-Plan anwenden -----
    # Der Analyse-Lauf (--plan-only) endete bis v192, BEVOR groups_for je lief.
    # Der Editor konnte darum nur Keyword-Momente zeigen; Bloecke gab es in
    # der Ausgabe schlicht nicht. Der Export steht deshalb VOR dem Ausstieg -
    # und er benutzt dieselbe groups_for-Konfiguration wie der spaetere
    # Voll-Render, sonst zeigt der Editor eine andere Aufteilung als das Video.
    blk_path = os.path.splitext(args.input)[0] + '_bloecke.json'
    _bloecke = load_bloecke(blk_path, len(words))
    _b_groups = groups_for(words, cfg, fx_map, bloecke=_bloecke)
    _b_alt = {b['i0']: b for b in _bloecke}
    _b_export = []
    for _g in _b_groups:
        if not _g:
            continue
        _e = {'i0': _g[0], 'i1': _g[-1] + 1, 'aktiv': True,
              'text': ' '.join(clean(words[j]['word']) for j in _g),
              'start': round(float(words[_g[0]]['start']), 2),
              'end': round(float(words[_g[-1]]['end']), 2),
              'anim': '', 'fx': '', 'power': 0, 'groesse': 0,
              # Zur Anzeige: hat dieser Block ein Keyword? Dann zeigt der
              # Editor die Moment-Bedienfelder an dieser Zeile.
              'kw': next((j for j in _g if j in kw), None)}
        _vor = _b_alt.get(_g[0])
        if _vor:
            for _k in ('aktiv', 'text', 'anim', 'fx', 'power', 'groesse',
                       'start', 'end'):
                if _k in _vor:
                    _e[_k] = _vor[_k]
        _b_export.append(_e)
    # Abgeschaltete Bloecke stehen NICHT in _b_groups (sie bilden ja keine
    # Gruppe). Sie muessen trotzdem in den Export, sonst waeren sie beim
    # naechsten Oeffnen des Editors verschwunden statt nur ausgeschaltet.
    for _i0, _vor in _b_alt.items():
        if _vor.get('aktiv', True):
            continue
        _g = list(range(_vor['i0'], min(_vor['i1'], len(words))))
        if not _g:
            continue
        _e = dict(_vor)
        _e.setdefault('text', ' '.join(clean(words[j]['word']) for j in _g))
        _e['kw'] = next((j for j in _g if j in kw), None)
        _b_export.append(_e)
    _b_export.sort(key=lambda x: x['i0'])
    try:
        json.dump(_b_export, open(blk_path, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    except Exception as _be:
        print(f"Block export failed ({type(_be).__name__})")
    if args.plan_only:
        print(f"Moments exported: {mom_path}")
        print(f"Blocks exported: {len(_b_export)}")
        sys.exit(0)
    if os.path.exists(mom_path):
        try:
            edits = {m['i']: m for m in json.load(open(mom_path, encoding='utf-8'))}
            kw = {i for i in kw if edits.get(i, {}).get('aktiv', True)}
            fx_map = fx_map or {}
            for i, m in edits.items():
                if i in kw:
                    e = fx_map.get(i) if isinstance(fx_map.get(i), dict) else {}
                    # v203-sec: power und n HART klemmen. Sie kommen aus
                    # _momente.json, und die schreibt nicht nur der Server -
                    # auch die Desktop-App und jeder, der die Datei von Hand
                    # anfasst. 'power' geht linear in den Radius des
                    # Hintergrund-Blurs; ein grosser Wert ergibt einen
                    # Gauss-Kernel, dessen Berechnung pro BILD Minuten dauert.
                    # Die Engine darf sich auf keine vorgelagerte Pruefung
                    # verlassen - gueltig ist 1..3 (POW-Tabelle) und 1..8.
                    fx_map[i] = {'fx': m.get('fx', e.get('fx', 'behind')),
                                 'power': max(1, min(3, int(
                                     m.get('power', e.get('power', 2)) or 2))),
                                 'n': max(1, min(8, int(
                                     m.get('n', e.get('n', 1)) or 1)))}
                    # v141: 'nah' (angesagte Nahaufnahme) gehoert dazu - ohne
                    # das Flag rutschte der Text nach einem Editor-Roundtrip
                    # wieder weg vom Kopf.
                    # v193: 'anker' und 'user_pick' KAMEN NIE MIT. Der
                    # Roundtrip baute fx_map[i] als frisches dict und kopierte
                    # nur drei Felder zurueck. Folge, an dieser Datei belegt:
                    # der Objekt-Anker (v161) erreichte build_plans bei JEDEM
                    # Render nicht, und eine erzwungene Nutzer-Markierung
                    # (user_pick) verlor nach dem ersten Speichern ihren
                    # Schutz gegen Dichte- und B-Roll-Gate. Beides ist genau
                    # der Fehlertyp, gegen den der Block-Editor gebaut ist -
                    # deshalb hier mitgezogen.
                    for k_v in ('szene', 'lage', 'nah', 'anker', 'user_pick'):
                        if isinstance(e, dict) and e.get(k_v):
                            fx_map[i][k_v] = e[k_v]     # Vision-Regie ueberlebt Edits
                    # v99a: Sprecher-Ansage ueberlebt den Editor-Roundtrip -
                    # OHNE das Flag degradierte die Dichte-Regel den Moment
                    # direkt nach dem Export wieder. Aendert der Nutzer den
                    # Effekt im Editor bewusst, erlischt die Ansage (User
                    # gewinnt zuletzt).
                    if (isinstance(e, dict) and e.get('intent')
                            and m.get('fx', e.get('fx')) == e.get('fx')):
                        fx_map[i]['intent'] = True
                    if str(m.get('szene', '')).lower() in ('wasser', 'boden', 'wand',
                                                           'himmel', 'person', 'unklar'):
                        fx_map[i]['szene'] = str(m['szene']).lower()
                    if str(m.get('lage', '')).lower() in ('liegend', 'stehend', 'frei'):
                        fx_map[i]['lage'] = str(m['lage']).lower()
                    if m.get('anim'):
                        fx_map[i]['anim'] = m['anim']
                    # v230l DERSELBE FEHLER WIE v230g, EINE DATEI WEITER.
                    # Der Export schreibt in JEDEN Moment das Feld 'text' -
                    # den AUTOMATISCHEN Wortlaut (words[i .. i+n]). Beim
                    # zweiten Render wurde er als NUTZER-UEBERSCHREIBUNG
                    # gelesen, obwohl niemand etwas geaendert hat. Steht dann
                    # eine Sprechpause in der Phrase, bricht `phrase` frueher
                    # ab als `n` - der Kartentext hat mehr Woerter als die
                    # Karte besitzt, `phrase = phrase[:1]` gibt den Rest frei,
                    # und dieselben Woerter stehen ein zweites Mal als
                    # Fliesstext im Bild. Uebernommen wird nur, was sich vom
                    # Automatik-Wortlaut UNTERSCHEIDET.
                    if m.get('text') and str(m['text']).strip():
                        _mn = int(fx_map[i].get('n', 1) or 1)
                        _mauto = ' '.join(clean(words[j].get('word', ''))
                                          for j in range(i, min(i + _mn,
                                                                len(words))))
                        if _norm_txt(str(m['text'])) != _norm_txt(_mauto):
                            fx_map[i]['txt'] = m['text']
                    if m.get('emoji'):
                        fx_map[i]['emoji'] = m['emoji']
            print(f"Moment editor: {len(kw)} active moments applied")
        except Exception as e:
            print(f"Moments file ignored ({type(e).__name__})")

    # --- v193: Block-Einstellungen in die Regie spiegeln ---------------------
    # Reihenfolge ist Absicht: der Blockplan laeuft NACH dem Momente-Editor.
    # Wer eine Zeile im Block-Editor anfasst, hat zuletzt entschieden.
    # Ein Block mit Effekt oder Wucht wird zum Moment - hat er noch kein
    # Keyword, wird eines bestimmt. Damit braucht der Nutzer nicht zu wissen,
    # was intern eine 'Karte' und was 'Fliesstext' ist: er stellt etwas ein,
    # und es passiert.
    if _bloecke:
        fx_map = fx_map or {}
        _b_moment = 0
        for _b in _bloecke:
            if not _b.get('aktiv', True):
                continue
            _g = list(range(_b['i0'], min(_b['i1'], len(words))))
            if not _g:
                continue
            _will = bool(_b.get('fx')) or int(_b.get('power') or 0) >= 3
            _ki = next((j for j in _g if j in kw), None)
            if _ki is None and _will:
                # Bestes Wort des Blocks: kein Fuellwort, moeglichst lang.
                _kand = [j for j in _g
                         if clean(words[j].get('word', '')).lower() not in STOPWORDS
                         and len(clean(words[j].get('word', ''))) >= 3]
                _ki = max(_kand or _g,
                          key=lambda j: len(clean(words[j].get('word', ''))))
                kw = set(kw) | {_ki}
                _b_moment += 1
            if _ki is None:
                continue
            _e = fx_map.get(_ki) if isinstance(fx_map.get(_ki), dict) else {}
            _e = dict(_e)
            if _b.get('fx'):
                _e['fx'] = _b['fx']
                # Eine bewusste Nutzerwahl braucht denselben Schutz wie eine
                # gesprochene Ansage - sonst setzen die Sichtbarkeits-Riegel
                # sie still auf 'outline' zurueck (am Code belegt).
                _e['user_pick'] = True
            if _b.get('power'):
                _e['power'] = int(_b['power'])
                _e['user_pick'] = True
            if _b.get('anim'):
                _e['anim'] = _b['anim']
            # v230g DAS WAR DIE URSACHE DES ANGESCHNITTENEN TEXTS.
            # Der Export schreibt in JEDEN Block das Feld 'text' - den
            # automatisch erzeugten Blockwortlaut, damit der Editor etwas
            # anzeigen kann. Hier wurde er als NUTZER-TEXTUEBERSCHREIBUNG
            # gelesen, obwohl niemand etwas geaendert hatte: aus dem EINEN
            # Schluesselwort wurde die ganze Zeile, und die passt naturgemaess
            # nicht in die Kartenbreite. Am Bild gemessen (540 px breit):
            # Karte 'CAPTIONS' 0.110..0.829 W wird nach EINEM Analyse-Lauf zu
            # 'WIE WIR CAPTIONS AUF' bei -0.052..0.987 W, also beidseitig
            # angeschnitten. Genau deshalb liess sich der Anschnitt mit einem
            # nachgebauten Transkript NIE ausloesen: er braucht die
            # Sidecar-Datei, die erst der erste Lauf schreibt.
            # Uebernommen wird der Text nur noch, wenn er sich vom
            # Automatik-Wortlaut UNTERSCHEIDET - dann hat ihn wirklich jemand
            # geaendert.
            _btxt = _b.get('text')
            if _btxt and _btxt.strip():
                _auto = ' '.join(clean(words[j].get('word', '')) for j in _g)
                if _norm_txt(_btxt) != _norm_txt(_auto):
                    _e['txt'] = _btxt
            fx_map[_ki] = _e
        if _b_moment:
            print(f"Block editor: {_b_moment} block(s) promoted to a moment")
        print(f"Block editor: {len(_bloecke)} user block(s) applied")
    # v230c0 DIE KI DENKT, DER SERVER LIEGT BRACH.
    # An Ismets Job-Log gemessen: von 245 s waren 140 s reines Warten auf
    # OpenAI (Textregie 55 s, Textfluss 85 s). In dieser Zeit stand die
    # Maschine still, obwohl gleich danach mehrere Minuten CPU- und
    # ffmpeg-Arbeit anstehen, die mit dem Textfluss NICHTS zu tun haben:
    # Farbwelt-Abtastung, Raum-Karte und Zeige-Regie brauchen nur das Video
    # und die Schnittzeiten.
    # Also wird der Textfluss JETZT losgeschickt und erst dort abgeholt, wo
    # sein Ergebnis wirklich gebraucht wird. Die Anfrage ist Byte fuer Byte
    # dieselbe - es aendert sich nur, wann gewartet wird. Kein Tausch gegen
    # Qualitaet (Regel 1), nur Leerarbeit weg.
    # Die Eingaben stehen hier alle fest: `fx_map` ist fertig (Bild-Regie und
    # Block-Editor sind durch), und nichts zwischen hier und der Abholstelle
    # fasst sie noch an.
    _flow_future = None
    _flow_groups = None
    _flow_path = os.path.splitext(args.input)[0] + '_flow3.json'
    if (cfg['effects'].get('caption_flow', True)
            and cfg['keywords'].get('ai', True)
            and not os.path.exists(_flow_path)):
        try:
            _flow_groups = groups_for(words, cfg, fx_map, bloecke=_bloecke)
            import threading as _th
            # BEWUSST ein Daemon-Thread und KEIN ThreadPoolExecutor: dessen
            # Threads sind nicht-Daemon, und Python wartet beim Beenden auf
            # sie. Stirbt der Render vorher an einem Fehler, haenge der
            # Prozess sonst bis zum API-Timeout (180 s) - ein Absturz, der
            # drei Minuten braucht, ist schlimmer als der Absturz.
            _flow_erg = {}

            def _flow_lauf():
                try:
                    _flow_erg['sel'] = ai_flow_direct(
                        words, _flow_groups, cfg.get('language', 'de'),
                        cfg['keywords'].get('ai_model', 'gpt-5'))
                except Exception as _e2:
                    _flow_erg['fehler'] = _e2
            _zt_flow_start = time.time()
            _flow_future = _th.Thread(target=_flow_lauf, daemon=True)
            _flow_future.start()
        except Exception as _e:
            print(f"AI flow: could not start early ({type(_e).__name__}), "
                  f"running it in order.")
            _flow_future = None

    palette_at = None
    # Farbwelt: 'auto' = adaptiv aus der Szene. 'schwarz'/'weiss' = feste
    # High-End-Palette; die Szenen-Toene werden dann bewusst NICHT aufgegriffen,
    # sonst waere die Farbwahl wirkungslos.
    # v230c1: hier wird nur noch ABGEHOLT, was oben gestartet wurde. Die
    # Meldungen bleiben an dieser Stelle stehen - der Server liest sie als
    # Fortschritts-Marken (Adaptive colours = 43 %), und eine Meldung, die
    # ploetzlich zwei Minuten frueher kommt, waere ein falscher Fortschritt.
    _zt_warte = time.time()
    if _bild_thread is not None:
        _bild_thread.join()
    _warte_bild = time.time() - _zt_warte
    c_style = _c_style_frueh
    if c_style == 'schwarz':
        S.set_base_colors((20, 20, 22), (58, 58, 64))
        print("Colour world: elegant black (deep black + graphite accent)")
    elif c_style == 'weiss':
        S.set_base_colors((250, 249, 246), (208, 204, 196))
        print("Colour world: elegant white (soft white + warm grey accent)")
    elif cfg.get('colors', {}).get('adaptive', True):
        if _bild_erg.get('palette_fehler') is not None:
            print(f"Adaptive colours: skipped "
                  f"({type(_bild_erg['palette_fehler']).__name__})")
        else:
            palette_at = _bild_erg.get('palette')
            print("Adaptive colours: captions pick up the scene tones (per shot)")
    # v143: Raum-Karte fuer die Platzierungs-Regie. Ein Abtastframe je Shot,
    # daraus ein Kostenraster 'wie besetzt ist diese Bildregion'. Abschaltbar
    # ueber effects.adaptive_place - dann faellt spot() auf Gesicht + Wunschzone
    # zurueck und verhaelt sich wie eine reine Motiv-Ausweichung.
    space_at = None
    _zt_rk = time.time()
    if _will_raum:
        if _bild_erg.get('raum_fehler') is not None:
            print(f"Placement director: space map skipped "
                  f"({type(_bild_erg['raum_fehler']).__name__})")
        else:
            space_at = _bild_erg.get('raum')
            print("Placement director: captions dodge the subject and busy areas "
                  "(space map per shot)")
    zt('raumkarte', _zt_rk)
    if _bild_thread is not None:
        print(f"Picture analysis: waited {_warte_bild:.1f}s "
              f"(ran in parallel with the AI questions)")
    # v160 ZEIGE-REGIE. Wohin zeigt oder schaut der Sprecher an den gewaehlten
    # Momenten? Die Messung laeuft NUR auf diesen Zeitpunkten (drei kleine
    # Frames je Moment), nicht ueber das ganze Video. Ohne models/hand.task
    # bleibt sie leer und die Platzierung verhaelt sich wie bisher.
    _zeigen = []
    _zt_zg = time.time()
    if cfg['effects'].get('caption_zeige', True):
        try:
            _zt = sorted({round(float(words[i]['start']), 2)
                          for i in (fx_map or {}) if i < len(words)})[:40]
            _zeigen = zeige_ziele(args.input, _zt, W, H)
            # v174: Hand-Aktions-Woerter ("push them away") ziehen die
            # Caption in Reichweite der Hand - erst dadurch kann der
            # Beruehrungs-Impuls (v101j) ueberhaupt treffen. Laeuft ueber
            # ALLE Woerter, nicht nur Keywords: der Schub-Satz war bei
            # Ismet ein Fuellwort-Chunk.
            _ht = sorted({round(float(w_['start']), 2) for w_ in words
                          if _hand_aktion_hit(clean(w_.get('word', '')))})[:12]
            if _ht:
                _zeigen = _ziel_dedupe(
                    sorted(_zeigen + hand_ziele(args.input, _ht, W, H),
                           key=lambda z: z[0]), W)
        except Exception as _e:
            print(f"Pointing direction: skipped ({type(_e).__name__})")
            _zeigen = []
    zt('zeige-regie', _zt_zg)
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
        # v193: der Flow-Cache MUSS denselben Blockplan sehen wie
        # build_plans - sonst sind die Anker-Schluessel (g[0]) einer
        # anderen Aufteilung und verfallen still (v161-Fehlertyp).
        # v230c0: dieselbe Aufteilung wie oben beim Vorabstart - nicht neu
        # rechnen, sonst koennten die Anker-Schluessel auseinanderlaufen
        # (v161/v193-Fehlertyp).
        _fgroups = _flow_groups if _flow_groups is not None \
            else groups_for(words, cfg, fx_map, bloecke=_bloecke)
        flow_path = _flow_path
        if os.path.exists(flow_path):
            try:
                _raw = json.load(open(flow_path, encoding='utf-8'))
                flow_map = _parse_flow_sel(_raw, _fgroups, words)
            except Exception:
                flow_map = None
        if flow_map is None:
            _zt_ki = time.time()
            if _flow_future is not None:
                # Schon unterwegs: hier wird nur noch der REST gewartet. Die
                # Zeile im Timing zeigt genau das - lief die Analyse lange
                # genug, steht hier fast null.
                _flow_future.join()
                if _flow_erg.get('fehler') is not None:
                    print(f"AI flow unavailable "
                          f"({type(_flow_erg['fehler']).__name__}), "
                          f"falling back to the heuristic.")
                    _sel = None
                else:
                    _sel = _flow_erg.get('sel')
                _flow_future = None
                print(f"AI flow: waited {time.time() - _zt_ki:.1f}s "
                      f"(started {time.time() - _zt_flow_start:.1f}s earlier, "
                      f"in parallel with the picture analysis)")
            else:
                _sel = ai_flow_direct(words, _fgroups, cfg.get('language', 'de'),
                                      cfg['keywords'].get('ai_model', 'gpt-5'))
            zt('ki-textfluss', _zt_ki)
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
            print(f"AI flow: {len(flow_map)} anchors chosen")

    # v101f LICHT-WAHRHEIT: dominante Lichtrichtung einmal aus einem Mittel-Frame
    # schaetzen, damit der Kontakt-Schatten des stehenden Textes licht-wahr zur
    # Seite faellt (weg vom Licht), statt symmetrisch. Gilt pro Clip (Licht ist
    # meist konstant); abschaltbar via effects.light_shadow.
    _light = None
    if cfg['effects'].get('light_shadow', True):
        try:
            _lt = (words[-1].get('end', 0.0) + words[0].get('start', 0.0)) / 2.0 \
                if words else 0.0
            _lr = subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', str(max(_lt, 0.0)), '-i', args.input,
                 '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                 '-s', '96x96', '-'], capture_output=True, timeout=20)
            if len(_lr.stdout) >= 96 * 96 * 3:
                _lf = np.frombuffer(_lr.stdout[:96 * 96 * 3],
                                    dtype=np.uint8).reshape(96, 96, 3)
                _light = estimate_light_dir(_lf)
                print(f"Light truth: light direction lx={_light[0]:+.2f} "
                      f"hardness={_light[1]:.2f} (the shadow falls with the light)")
        except Exception as _e:
            print(f"Light truth: estimate skipped ({type(_e).__name__})")

    if video_mode == 'narrator':
        if fx_map:
            for _v in fx_map.values():
                if _v.get('fx') == 'behind':
                    _v['fx'] = 'outline'
        plans = build_plans(words, kw, cfg, S, W, H, face_ok, fx_map,
                            face_pos=None, palette_at=palette_at,
                            cut_times=cut_times, faces_at=None,
                            flow_map=flow_map, loud=loud_map,
                            beat_times=_beat_ts, light_dir=_light,
                            space_at=space_at, zeigen=_zeigen,
                            bloecke=_bloecke)
    else:
        plans = build_plans(words, kw, cfg, S, W, H, face_ok, fx_map, face_pos,
                            palette_at, cut_times=cut_times, faces_at=faces_at,
                            flow_map=flow_map, loud=loud_map,
                            beat_times=_beat_ts, light_dir=_light,
                            space_at=space_at, zeigen=_zeigen,
                            bloecke=_bloecke)

    # --- v101t Auto-Akzente: dezente Motion-Graphics-Akzente aufs Transkript.
    # Der Akzent-Plan wird bei der Momente-Ausgabe geschrieben (compute_accents,
    # oben) und im Editor editiert; hier nur noch LADEN (editierte Datei gewinnt).
    accents_render = []
    acc_style = accent_style((cfg.get('accents') or {}).get('profile'))
    _pz_for_accents = None
    # v139: Rendern haengt NUR noch an der Datei (= bewusst im Editor gesetzt
    # oder von der Auto-Regie erzeugt, falls accents.auto an ist). Vorher hing
    # auch das Rendern am auto-Flag - Editor-Akzente waeren bei auto:false
    # stumm verpufft.
    _acc_path = os.path.splitext(args.input)[0] + '_accents.json'
    if os.path.exists(_acc_path):
        try:
            accents_render = sanitize_accents(
                json.load(open(_acc_path, encoding='utf-8')), words,
                (cfg.get('accents') or {}).get('profile'), kw)
        except Exception:
            accents_render = []
        _plat_a = str(cfg.get('output', {}).get('platform', 'generic')).lower()
        try:
            _pz_for_accents = platform_safe_zones(_plat_a, W, H)
        except Exception:
            _pz_for_accents = None
        if accents_render:
            # v101u: Position gegen die echten Caption-Boxen aufloesen -> Akzent
            # und Caption ueberschneiden sich nie (Akzent weicht nach oben aus).
            resolve_accent_positions(accents_render, plans, W, H, _pz_for_accents)
            print(f"Auto accents: {len(accents_render)} subtle motion graphics")

    # --- Blender-Wasser-Text: stehende Szenen-Texte werden echtes 3D-Wasser-Glas.
    # Ein Render pro Moment (gecacht); Bewegung/Okklusion macht weiter die Pipeline.
    if cfg['effects'].get('blender_water', True):
        bl_exe = blender_engine.find_blender(cfg.get('render', {}).get('blender_path'))
        bl_targets = [p for p in plans if p['tpl'] == 'ground' and p.get('broll')
                      and not p.get('scene_blend') and not p.get('count')
                      and (not args.window or (p['start'] < args.window[1]
                                               and p['end'] > args.window[0]))]
        if bl_targets and not bl_exe:
            print("Blender not found - standing scene text falls back to the 2D look."
                  " (install Blender or set render.blender_path in config.yaml setzen)")
        elif bl_targets:
            print(f"Blender water text: {len(bl_targets)} moment(s) ({bl_exe})")
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
    _zt_x = zt('regie+plaene', _zt_x)
    n_kw = sum(1 for p in plans if 'kw_i' in p)
    n_broll = sum(1 for p in plans if p.get('broll'))
    print(f"Compositions: {len(plans)} ({n_kw} keyword moments, {n_broll} over B-roll)")
    # v211 BLOCK-MASSE INS LOG. Fuenf Theorien zum angeschnittenen Text, fuenf
    # widerlegt - weil die gemessene Breite nur im Bild stand, nicht im Log.
    # Eine Zeile je Textblock: Zeit, linke und rechte Kante als Anteil der
    # Bildbreite. Wer sie ausserhalb 0..1 sieht, weiss sofort WELCHER Block
    # herauslaeuft, statt es rueckwaerts aus dem Video zu schaetzen.
    # v216: gemessen wird die TINTE ueber ink_box - damit erscheinen endlich
    # auch KARTEN und KOMPOSITIONEN in dieser Liste. Bis v215 las die Zeile
    # 'bx'/'bw', und die setzt kein Keyword-Plan: jede Karte stand mit
    # '0.000..0.000 W' im Log. Genau die Momente, die im Bild angeschnitten
    # waren, waren im Log unsichtbar - ein Messwerkzeug, das den gesuchten
    # Fall nicht misst.
    try:
        for _p in sorted(plans, key=lambda q: q.get('start', 0)):
            _bx = ink_box(_p, W, H)
            if _bx is None:
                continue
            _lo, _hi = _bx[0], _bx[1]
            _txt = plan_text(_p, words)[:34]
            _warn = ' <-- RAGT AUS DEM BILD' if (_lo < -1 or _hi > W + 1) else ''
            # v216: mit dem SICHTBAREN Zeitfenster. Ohne das Ende liess sich
            # aus dem Log nicht ablesen, ob zwei Texte gleichzeitig stehen -
            # genau der Befund, den Ismet am fertigen Bild gemeldet hat.
            _t0 = card_t0(_p, words)
            _t1 = float(_p.get('end', _t0)) + float(
                _p.get('aus', 0.15 if _p.get('tpl') == 'flow' else 0.40))
            print(f"  Block {_t0:5.2f}-{_t1:5.2f}s x {_lo / W:.3f}..{_hi / W:.3f} W"
                  f" | {_txt}{_warn}")
    except Exception as _e:
        print(f"  Block measurements unavailable: {type(_e).__name__}")

    _zt_x = time.time()
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
            print(f"{prov} not usable, trying the next one ...")
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
        # v230c-sec: derselbe Deckel wie im Auto-Pfad. Ueber 0.8 rechnet das
        # Netz das Bild GROESSER als das Original - gemessen Faktor 50-90 an
        # Zeit und bis 5 GB Speicher, ohne jeden Qualitaetsgewinn. Der Wert
        # kommt aus einer Config-Datei, die auch der Web-Kunde beeinflusst;
        # geklemmt wird auf BEIDEN Seiten (Server + Engine), weil die
        # Desktop-App dieselbe Datei schreibt.
        try:
            md_val = min(max(float(md), 0.125), 0.8)
        except (TypeError, ValueError):
            md_val = 0.25
    dsr = np.array([md_val], dtype=np.float32)
    refine_str = float(cfg['effects'].get('refine', 1.0)) * q_refine
    # v230ay: der Wert ist ein Config-Schluessel und bleibt deutsch; im Log
    # steht der englische Name (der Kunde liest ihn).
    _q_en = {'standard': 'standard', 'hoch': 'high', 'maximum': 'maximum'}
    print(f"Matting: {active_prov}, quality '{_q_en.get(q_name, q_name)}' "
          f"(detail level {md_val:.3g}, edge sharpness {refine_str:.2g})")
    _zt_x = zt('modelle-laden', _zt_x)

    # --- SFX-Spur. Es gibt NUR echte Sounds aus dem Sound-Pack (sfx/pack/).
    # Synthetische Ersatztoene wurden ersatzlos entfernt - ein billiger Sound ist
    # schlechter als gar keiner. Ohne Pack laeuft das Video ohne Sound-Effekte.
    sfx_path = None
    if cfg['effects'].get('sfx', True) and not args.window:
        try:
            import sfx_engine
            folder = sfx_engine.pack_folder(HERE)
            if not sfx_engine.load_bank(folder):
                print("NOTE: no sound pack -> the video gets no "
                      "Sound-Effekte.")
                print("  Load it: GUI -> Pro -> Sound pack -> 'Load real sounds'")
            else:
                sfx_path = os.path.join(tempfile.gettempdir(), 'dve_sfx_track.wav')
                powers = {i: v.get('power', 2) for i, v in (fx_map or {}).items()
                          if isinstance(v, dict)}
                dur_total = (args.duration if args.duration else n_frames / fps)
                print("Placing SFX on the word onsets ...")
                _zt_sfx = time.time()
                n_sfx = sfx_engine.build_sfx_track(
                    plans, words, dur_total, folder, sfx_path,
                    voice_wav=voice_wav, powers=powers, cut_times=cut_times,
                    # v230: wieviel Ton das Video bekommt (sparsam/normal/dicht)
                    dichte=str(cfg['effects'].get('sfx_dichte', 'normal')),
                    # v230b5: Schreibmaschine unter dem wortweisen Aufbau.
                    typing=bool(cfg['effects'].get('sfx_typing', True)))
                zt('sfx-bauen', _zt_sfx)
                print(f"SFX: {n_sfx} sound moments placed "
                      f"({n_sfx / max(dur_total, 1e-6) * 60:.0f} per minute, "
                      f"density '{cfg['effects'].get('sfx_dichte', 'normal')}')")
                if not n_sfx:
                    sfx_path = None
        except Exception as e:
            print(f"SFX skipped ({type(e).__name__})")
            sfx_path = None

    # --- Wasserzeichen-Sprite (v80y, Free-Tier): einmal gebaut, pro Frame
    # alpha-geblendet. Dezent: 38% Deckkraft, unten rechts.
    wm = None
    if args.watermark:
        wm = build_watermark(W, H)
        print("Watermark: on (free tier, with logo)")

    # --- Encoder (v80p): ZWEI Stufen statt einer Pipe-Mux-Kombi.
    # Stufe 1: NUR Video aus der Pipe in eine Temp-Datei. Kein zweiter Input,
    #   kein -shortest. Hintergrund: ffmpeg hat einen Interleave-Mechanismus
    #   (max_interleave_delta, 10s), der bei langsamer Pipe-Zufuhr (CPU-Render
    #   ist langsamer als Echtzeit) die komplett eingelesene Audio-Spur
    #   vorzeitig ausschreibt - danach beendet -shortest den Prozess REGULAER
    #   mitten im Render. Symptom: BrokenPipeError ohne ffmpeg-Fehlertext.
    # Stufe 2 (nach dem Render): Audio/SFX per Stream-Copy dazu muxen -
    #   alle Inputs sind dann Dateien, dauert nur Sekunden, kein Pipe-Risiko.
    if args.alpha_export:
        # v101h: transparente Caption-Ebene. Pipe-Format BGRA, ProRes 4444.
        if not out_path.lower().endswith('.mov'):
            out_path = os.path.splitext(out_path)[0] + '.mov'
        vcodec = ['-c:v', 'prores_ks', '-profile:v', '4444',
                  '-pix_fmt', 'yuva444p10le']
        acodec = ['-c:a', 'pcm_s16le']
        video_tmp = os.path.splitext(out_path)[0] + '.videoonly.mov'
        print("Output: caption layer with alpha (ProRes 4444 .mov)")
    elif cfg['output'].get('master', False):
        if not out_path.lower().endswith('.mov'):
            out_path = os.path.splitext(out_path)[0] + '.mov'
        vcodec = ['-c:v', 'prores_ks', '-profile:v', '3', '-pix_fmt', 'yuv422p10le']
        acodec = ['-c:a', 'pcm_s16le']
        video_tmp = os.path.splitext(out_path)[0] + '.videoonly.mov'
        print("Output: ProRes master (.mov) for Premiere")
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
        _pipe_fmt = 'bgra' if args.alpha_export else 'bgr24'
        cmd = ['ffmpeg', '-y', '-v', 'error',
               '-f', 'rawvideo', '-pix_fmt', _pipe_fmt, '-s', f'{W}x{H}',
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
    print(f"Matting window: {int(need_alpha.sum())} of ~{total_est} frames")

    # v101g Kontaktbogen: pro Keyword-Moment den Frame auf dem Hoehepunkt
    # einsammeln (echtes Compositing, kein Editor-Fake). Nur Voll-Render.
    _kb_frames = {}
    if not args.window and cfg['effects'].get('contact_sheet', True):
        for p in plans:
            if 'kw_i' not in p:
                continue
            _pk = p['start'] + min(0.45, 0.4 * max(p['end'] - p['start'], 0.1))
            _fi = int(_pk * fps)
            _kb_frames.setdefault(_fi, (str(p.get('kw_txt', '?')), p['start']))
    _kb_tiles, _kb_labels = [], []

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
                print(f"Depth occlusion: {int(need_depth.sum())} frames "
                      f"({dsess.get_providers()[0] if dsess else 'no model'})")
            else:
                print("Depth occlusion skipped (models/depth.onnx is missing - setup.bat downloads it)")
    # v101k Bullet-Time: Kandidat suchen (laengste Sprech-Pause >=0.8s vor
    # einem power-3-Moment). Braucht das Tiefen-Modell - notfalls hier laden.
    bt_win = None
    bt_freeze = bt_depth = None
    if cfg['effects'].get('bullet_time', True) and not args.alpha_export:
        bt_win = bullet_window(words, plans)
        if bt_win is not None and dsess is None:
            _bt_dp = os.path.join(HERE, 'models/depth.onnx')
            if os.path.exists(_bt_dp):
                for prov in chain + ['CPUExecutionProvider']:
                    try:
                        dsess = ort.InferenceSession(_bt_dp, providers=[prov])
                        break
                    except Exception:
                        continue
            if dsess is None:
                print("Bullet time skipped (no depth model)")
                bt_win = None
        if bt_win is not None:
            print(f"Bullet time candidate: pause {bt_win[0]:.2f}s-{bt_win[1]:.2f}s "
                  f"vor Moment '{clean(words[bt_win[2]].get('word', '?'))}'")
    # Tracking-Fenster (planarer Kamera-Track) = Szenen-Text-Fenster
    need_track = np.zeros(total_est, dtype=bool)
    # v101i: Wand-Momente bekommen einen EIGENEN Track auf der Wand-Ebene
    # (obere Bildhaelfte, Person ausgeschlossen) - der Boden-Track hat eine
    # andere Parallaxe, ein daran haengender Wand-Text rutscht.
    need_track_wall = np.zeros(total_est, dtype=bool)
    if cfg['effects'].get('track3d', True):
        for p in plans:
            if p['tpl'] == 'ground' and (p.get('scene_ground') or p.get('broll')):
                a = max(int((p['start'] - 0.35) * fps), 0)
                b = min(int((p['end'] + 0.6) * fps) + 1, total_est)
                need_track[a:b] = True
                if p.get('szene') == 'wand' and not p.get('lying'):
                    need_track_wall[a:b] = True
        if need_track.any():
            print(f"Camera track (planar): {int(need_track.sum())} frames"
                  + (f", of those wall plane: {int(need_track_wall.sum())}"
                     if need_track_wall.any() else ""))
    # v101j Hand-Kontakt: Fingerspitzen nur in Moment-Fenstern suchen (gated).
    need_hands = np.zeros(total_est, dtype=bool)
    hand_tracker = None
    if cfg['effects'].get('hand_contact', True):
        for p in plans:
            # v176: FLOW-CHUNKS ZAEHLEN MIT. Bis v174 lief die
            # Hand-Erkennung nur in Keyword-Fenstern - Ismets Schub-Satz
            # ("and i just can push them away") ist aber ein reiner
            # Fuellwort-Chunk ohne kw_i. Dort war der Tracker gar nicht an,
            # und der v174-Naeherungstreffer lief in einer Funktion, die
            # diesen Plan nie zu sehen bekam. Am echten Render gemessen:
            # die Hand kreuzt x = 0.58 -> 0.19 W, der Text steht bei
            # 0.47 W - der Kontakt WAERE da gewesen.
            if 'kw_i' in p or p.get('front'):
                a = max(int((p['start'] - 0.2) * fps), 0)
                b = min(int((p['end'] + 0.4) * fps) + 1, total_est)
                need_hands[a:b] = True
        if need_hands.any():
            hand_tracker = HandTracker(W, H)
            if hand_tracker.ok:
                print(f"Hand contact: {int(need_hands.sum())} frames are "
                      f"checked for contact")
            else:
                hand_tracker = None
                print("Hand contact skipped (models/hand.task is missing "
                      "or mediapipe without HandLandmarker)")
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
    H_cum_wall = np.eye(3)     # v101i: eigener Track fuer die Wand-Ebene
    wall_gen = 0
    trk_fail_w = 0
    _hand_tips = []            # v101j: letzte Fingerspitzen-Erkennung
    sx_up, sy_up = W / 480.0, H / float(int(H * 480 / W))
    S_up = np.diag([sx_up, sy_up, 1.0])
    S_dn = np.linalg.inv(S_up)
    import time as _time
    t_start = _time.time()
    _zt_ende = None                 # v227: Marke fuer die Dekodierzeit je Frame
    # v230h: Kanten-Schaerfung EINMAL fuer den ganzen Render bestimmen - aber
    # aus MEHREREN Einstellungen, nicht aus dem ersten Bild (siehe
    # _refine_wahl). Geprueft werden die Schnitte plus gleichmaessig verteilte
    # Stellen; die strengste Antwort gewinnt.
    _refine_wunsch = float(cfg['effects'].get('matte_refine', 1.0)) * q_refine
    _rz = sorted({round(max(float(c) + 0.20, 0.0), 2) for c in (cut_times or [])}
                 | {round(src_dur * f, 2)
                    for f in (0.05, 0.25, 0.45, 0.65, 0.85)})
    _rz = [t for t in _rz if 0.0 <= t < max(src_dur - 0.1, 0.1)][:10]
    _refine_auto = None if not _rz else _refine_wahl(
        sess, dsr, args.input, W, H, _refine_wunsch, _rz)
    _zt_x = zt('matte-check', _zt_x)
    max_frames = int(args.duration * fps) if args.duration else None
    if max_frames:
        print(f'Preview mode: only the first {args.duration:.0f} seconds')
    win = args.window
    preroll = 1.2
    seek = max(win[0] - preroll, 0.0) if win else 0.0
    off_frames = int(round(seek * fps))
    first_abs = last_abs = None                 # exakt geschriebene Frame-Grenzen
    if win:
        print(f'Window render: {win[0]:.2f}s - {win[1]:.2f}s '
              f'(Vorlauf {win[0] - seek:.2f}s for tracking/matting)')
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
            print(f'Freeze frame: {fz_start:.2f}s for {freeze_dur:.2f}s '
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

        # v101k Bullet-Time: in der Pause vor der Punchline friert das Bild
        # ein und die virtuelle Kamera faehrt per Tiefen-Reprojektion hinein
        # und zurueck (endet auf 0 - nahtloser Wiedereinstieg ins Live-Bild).
        if bt_win is not None and dsess is not None \
                and bt_win[0] <= t < bt_win[1]:
            if bt_freeze is None:
                bt_freeze = frame.copy()
                _bs = cv2.resize(bt_freeze.astype(np.uint8), (d_w, d_h))
                _bn = (_bs[..., ::-1].astype(np.float32) / 255.0 - D_MEAN) / D_STD
                _bp = dsess.run(None, {d_in_name: _bn.transpose(2, 0, 1)[None]})[0][0]
                _b5, _b95 = np.percentile(_bp, 5), np.percentile(_bp, 95)
                _bd = np.clip((_bp - _b5) / max(_b95 - _b5, 1e-4), 0, 1)
                bt_depth = cv2.resize(_bd.astype(np.float32), (W, H))
                if depth_quality_ok(bt_depth):
                    print(f"Bullet time: active {bt_win[0]:.2f}s-{bt_win[1]:.2f}s "
                          f"(2.5D dolly, duration unchanged)")
                else:
                    print("Bullet time skipped (depth map too flat - "
                          "no effect beats a cheap one)")
                    bt_win = None
                    bt_freeze = bt_depth = None
            if bt_win is not None:
                _bu = (t - bt_win[0]) / max(bt_win[1] - bt_win[0], 1e-6)
                frame = depth_dolly(bt_freeze, bt_depth, _bu, W, H)
        elif bt_freeze is not None:
            bt_freeze = bt_depth = None

        # v227: die Zeit VOR diesem Punkt ist Dekodieren + Freeze/Bullet-Time.
        # Der Generator liefert den naechsten Frame erst am Schleifenkopf, also
        # zaehlt hier die Wartezeit auf ffmpeg mit - genau das will man wissen.
        _zt_frame = zt('decode', _zt_ende) if _zt_ende else time.time()

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
            # v228b DIE NACHSCHAERFUNG WIRD EINMAL GEGENGEPRUEFT.
            # Ismets Befund ("das Maskieren hat hier nicht gut geklappt") war
            # am ersten Bild seines Renders messbar: die ROHE Netz-Maske ist
            # sauber (9 Kruemel/Loecher), nach der Nachschaerfung mit Staerke
            # 1.3 waren es 285 - die Kante war zerfetzt, und genau diese Kante
            # schneidet den Text aus. Auf weichem, rauschfreiem Material
            # (KI-Footage) findet der Guided Filter keine echte Kante mehr und
            # rechnet Fabrik-Rauschen zu Silhouette um.
            # Die Detailstufe des Netzes ist NICHT die Ursache: 0.337 gegen
            # 0.506 gemessen - gleiche Kante, aber 59 -> 108 ms je Bild.
            # Deshalb kein fester Wert, sondern eine Gegenprobe am ERSTEN
            # Bild: macht die Nachschaerfung die Maske schmutziger, wird sie
            # heruntergedreht. Kostet einmal je Render, nicht je Bild.
            if _refine_auto is None:
                _refine_auto = _refine_pruefen(
                    alpha, frame,
                    float(cfg['effects'].get('matte_refine', 1.0)) * q_refine)
            alpha = refine_alpha(alpha, frame, _refine_auto)
            # v230a: Krater im Inneren schliessen - dort darf nichts
            # durchscheinen (die Aussenkante bleibt unangetastet).
            alpha = matte_loecher_fuellen(alpha)
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

        _zt_frame = zt('matting', _zt_frame)

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

        _zt_frame = zt('scene-lock', _zt_frame)

        # --- v161 OBJEKT-ANKER: aktive Anker Frame fuer Frame nachfuehren.
        # Der Vision-Aufruf sagt EINMAL, wo das Objekt steht; wohin es
        # wandert, misst Optical Flow - jeden Frame, lokal, ohne Token.
        _ank_aktiv = [_p for _p in plans
                      if _p.get('_ank0')
                      and _p['start'] - 0.35 <= t <= _p['end'] + 0.40]
        if _ank_aktiv:
            _ag = cv2.cvtColor(
                cv2.resize(frame.astype(np.uint8),
                           (480, max(int(H * 480 / max(W, 1)) // 2 * 2, 2))),
                cv2.COLOR_BGR2GRAY)
            for _p in _ank_aktiv:
                _trk = _p.get('_ank_trk')
                if _trk is None:
                    _ox, _oy, _orad = _p['_ank0']
                    _trk = ObjektAnker(_ag, _ox, _oy, _orad, W, H)
                    _p['_ank_trk'] = _trk
                else:
                    _trk.step(_ag)
                # Verlorene Spur friert den Stand ein, sie springt nicht
                # zurueck auf null - ein Text, der bei jeder Verdeckung an
                # seine Startstelle huepft, ist schlimmer als einer, der
                # kurz stehen bleibt.
                _p['_ank_dx'], _p['_ank_dy'] = _trk.dx, _trk.dy

        _zt_frame = zt('objekt-anker', _zt_frame)

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
                    H_cum_wall = np.eye(3); wall_gen += 1; trk_fail_w = 0
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
                    # v101i: Wand-Ebene separat tracken (obere Haelfte,
                    # Person raus) - nur in Fenstern mit aktivem Wand-Text.
                    if fa < len(need_track_wall) and need_track_wall[fa]:
                        _pm_w = person_mask(alpha) if alpha is not None else None
                        Hw_small, ok_w = update_homography(
                            trk_prev, tg, np.eye(3), region='wand',
                            exclude=_pm_w)
                        if ok_w:
                            Hw_step = S_up @ Hw_small @ S_dn
                            H_cum_wall = Hw_step @ H_cum_wall
                            H_cum_wall /= H_cum_wall[2, 2]
                            trk_fail_w = 0
                        else:
                            trk_fail_w += 1
                            if trk_fail_w > 12:
                                H_cum_wall = np.eye(3); wall_gen += 1
                                trk_fail_w = 0
            trk_prev = tg
        else:
            trk_prev = None
            H_cum = np.eye(3)
            track_gen += 1
            H_cum_wall = np.eye(3)
            wall_gen += 1

        _zt_frame = zt('planar-track', _zt_frame)

        # --- Tiefe fuer Okklusion (nur in Szenen-Text-Fenstern)
        depth_n = None
        if dsess is not None and fa < len(need_depth) and need_depth[fa]:
            small_d = cv2.resize(frame.astype(np.uint8), (d_w, d_h))
            rgbn = (small_d[..., ::-1].astype(np.float32) / 255.0 - D_MEAN) / D_STD
            pred = dsess.run(None, {d_in_name: rgbn.transpose(2, 0, 1)[None]})[0][0]
            p5, p95 = np.percentile(pred, 5), np.percentile(pred, 95)
            dn = np.clip((pred - p5) / max(p95 - p5, 1e-4), 0, 1)
            depth_n = cv2.resize(dn.astype(np.float32), (W, H))
        _zt_frame = zt('tiefe', _zt_frame)
        scene_vel = float(np.hypot(scene_smooth[0] - prev_scene[0],
                                   scene_smooth[1] - prev_scene[1]))
        prev_scene = list(scene_smooth)
        fidx = min(fi, len(face_stable) - 1)
        ai = min(fi, len(aud_rms) - 1)
        # v101j: Fingerspitzen in Moment-Fenstern (jedes 2. Frame, Rest haelt
        # die letzte Erkennung) -> Kontakt-Impulse auf beruehrte Momente.
        if hand_tracker is not None and fa < len(need_hands) and need_hands[fa]:
            if fi % 2 == 0:
                _hand_tips = hand_tracker.detect(frame.astype(np.uint8), t)
            if _hand_tips:
                hand_contacts(plans, _hand_tips, t, W, H)
        else:
            _hand_tips = []
        _zt_frame = zt('haende', _zt_frame)
        _cf_kw = dict(aud=(float(aud_rms[ai]), float(aud_bass[ai]),
                           float(aud_onset[ai])),
                      depth_n=depth_n, scene_vel=scene_vel,
                      H_cum=(H_cum if (fa < len(need_track) and need_track[fa])
                             else None),
                      track_gen=track_gen,
                      H_cum_wall=(H_cum_wall
                                  if (fa < len(need_track_wall)
                                      and need_track_wall[fa]) else None),
                      wall_gen=wall_gen,
                      hand_tips=_hand_tips)
        if args.alpha_export:
            # v101h Doppelpass: identische Geometrie ueber Schwarz und Weiss,
            # dazwischen den Anim-/Kamera-State zuruecksetzen.
            _snap = _alpha_state_snapshot(plans, cam_state)
            _cb = composite_frame(np.zeros_like(frame), alpha, t, plans, words,
                                  face_stable[fidx], cfg, S, W, H, cam_state,
                                  tuple(scene_smooth), **_cf_kw)
            _alpha_state_restore(plans, cam_state, _snap)
            _cw = composite_frame(np.full_like(frame, 255), alpha, t, plans,
                                  words, face_stable[fidx], cfg, S, W, H,
                                  cam_state, tuple(scene_smooth), **_cf_kw)
            comp = None
        else:
            comp = composite_frame(frame, alpha, t, plans, words, face_stable[fidx],
                                   cfg, S, W, H, cam_state, tuple(scene_smooth),
                                   **_cf_kw)
            if accents_render:            # v101t: dezente Akzente OBEN drauf
                comp = draw_accents(comp, t, accents_render, acc_style, W, H,
                                    _pz_for_accents)
        _zt_frame = zt('compositing', _zt_frame)
        if not win or t >= win[0] - 1e-6:
            if first_abs is None:
                first_abs = fi + off_frames
            last_abs = fi + off_frames
            if args.alpha_export:
                try:
                    enc.stdin.write(alpha_from_pair(_cb, _cw).tobytes())
                except BrokenPipeError:
                    err = enc.stderr.read().decode('utf-8', 'ignore')[-800:] \
                        if enc.stderr else ''
                    sys.exit(f"ERROR: alpha encoder aborted. {err.strip()}")
            if not args.alpha_export and wm is not None:
                _a, _x, _y = wm
                _h, _w = _a.shape[:2]
                _roi = comp[_y:_y + _h, _x:_x + _w]
                _al = (_a[:, :, 3:4].astype(np.float32) / 255.0)
                _roi[:] = _roi * (1 - _al) + _a[:, :, 2::-1].astype(np.float32) * _al
            if not args.alpha_export and fi in _kb_frames:   # v101g: Beweisbild
                _kt, _ks = _kb_frames.pop(fi)
                _kb_tiles.append(np.clip(comp, 0, 255).astype(np.uint8).copy())
                _kb_labels.append(f"{_kt} @ {_ks:.1f}s")
            try:
                if not args.alpha_export:
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
                sys.exit(f"ERROR: video encoding aborted. {grund}")
        _zt_ende = zt('encode-write', _zt_frame)
        fi += 1
        mem_wache(fi, max_frames or n_frames)   # v230ak: vor dem Kill eingreifen
        # v230b3 LIVE-BILD FUER DEN KUNDEN. Bis hierher sah er beim Rendern
        # nur eine Prozentzahl - bei einem Vorgang, der Minuten dauert, ist
        # das wenig. Alle 25 Bilder (rund eine Sekunde Video) wird das GERADE
        # FERTIGE Bild klein daneben gelegt; die App zeigt es an. Kosten:
        # ein Resize auf 360 px plus ein JPEG, gemessen unter 10 ms - gegen
        # ~250 ms je Bild im Compositing faellt das nicht ins Gewicht.
        # Geschrieben wird ueber eine Zwischendatei mit os.replace, sonst
        # liest die App irgendwann ein halbes JPEG (v230w-Lehre).
        # Beim Alpha-Export gibt es kein sinnvolles Vorschaubild.
        if (not args.alpha_export) and fi % 25 == 0 and _vorschau_pfad:
            vorschau_schreiben(comp, _vorschau_pfad)
        if fi % 100 == 0:
            el = _time.time() - t_start
            rate = fi / max(el, 0.01)
            rest = int(((max_frames or n_frames) - fi) / max(rate, 0.01))
            # v230aj: der Speicherstand gehoert MIT in die Fortschrittszeile.
            # Steigt er Bild fuer Bild, sieht man das Ende kommen, bevor der
            # Prozess abgeschossen wird - danach ist es zu spaet, dann steht
            # im Log nur noch "Broken pipe".
            print(f"  Frame {fi}/{max_frames or n_frames} | {rate:.1f} f/s | "
                  f"~{rest // 60}:{rest % 60:02d} left | {mem_zeile()}",
                  flush=True)
    enc.stdin.close()
    enc_err = b''
    try:
        enc_err = enc.stderr.read() if enc.stderr else b''
    except Exception:
        pass
    enc.wait()
    if fi == 0:
        sys.exit("ERROR: no frames could be read. Is the video file intact?")
    if enc.returncode != 0:
        sys.exit(f"ERROR: video encoding failed (ffmpeg exit "
                 f"{enc.returncode}). "
                 f"{enc_err.decode('utf-8', 'ignore')[-600:].strip() or '(no output)'}")

    # --- Stufe 2 (v80p): Audio + SFX dazu muxen. Video wird nur kopiert.
    if video_tmp and args.alpha_export:
        # v101h: Caption-Ebene - NUR die SFX als eigene Tonspur (der Kunde hat
        # sein Original-Audio selbst). Ohne SFX bleibt die Ebene stumm.
        if sfx_path:
            mux = ['ffmpeg', '-y', '-v', 'error', '-i', video_tmp,
                   '-i', sfx_path, '-filter_complex', f'[1:a:0]volume={vol}[aout]',
                   '-map', '0:v', '-map', '[aout]', '-c:v', 'copy'] + acodec + \
                  ['-shortest', out_path]
            print("Building the audio track (SFX only) ...")
            r_mux = subprocess.run(mux, capture_output=True, text=True)
            if r_mux.returncode != 0 or not os.path.exists(out_path):
                sys.exit(f"ERROR: audio muxing failed: "
                         f"{(r_mux.stderr or '')[-600:].strip() or '(no output)'}")
            try:
                os.remove(video_tmp)
            except OSError:
                pass
        else:
            os.replace(video_tmp, out_path)
        video_tmp = None
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
        mux += ['-c:v', 'copy'] + acodec + ['-shortest']
        # v171 HERKUNFT IN DIE DATEI. Vier byte-identische "neue" Renders
        # in Folge, und niemand konnte sehen, WELCHER Job eine Datei erzeugt
        # hat - der Download hiess immer gleich. Der Job-Stempel (Build +
        # Job-ID, vom Server per Env gesetzt) wandert in die MP4-Metadaten:
        # ffprobe zeigt sofort, aus welchem Render eine Datei stammt.
        _tag = os.environ.get('DVE_JOB_TAG', '').strip()
        if _tag:
            mux += ['-metadata', f'comment={_tag[:120]}']
        mux += [out_path]
        print("Building the audio track ...")
        _zt_mux = time.time()
        r_mux = subprocess.run(mux, capture_output=True, text=True)
        zt('audio-mux', _zt_mux)
        if r_mux.returncode != 0 or not os.path.exists(out_path):
            sys.exit(f"ERROR: audio muxing failed: "
                     f"{(r_mux.stderr or '')[-600:].strip() or '(no output)'}")
        try:
            os.remove(video_tmp)
        except OSError:
            pass
    # v101 Watermark-Split (Free-Tier): sauberen Master behalten und die
    # ausgelieferte Datei mit EXAKT demselben Sprite wassermarkieren wie der
    # eingebrannte Pfad - der erste Kauf schaltet genau dieses Video ohne
    # Neu-Render frei (kein Ergebnis-Risiko, keine Renderkosten).
    if getattr(args, 'watermark_split', False) and out_path.lower().endswith('.mp4'):
        try:
            _mc = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                               'master_clean.mp4')
            shutil.copyfile(out_path, _mc)
            _warr, _wwx, _wwy = build_watermark(W, H)
            _wpng = os.path.join(os.path.dirname(_mc), 'wm.png')
            Image.fromarray(_warr).save(_wpng)
            _wtmp = out_path + '.wm.mp4'
            _wr = subprocess.run(
                ['ffmpeg', '-y', '-v', 'error', '-i', _mc, '-i', _wpng,
                 '-filter_complex', f'[0:v][1:v]overlay={_wwx}:{_wwy}',
                 '-c:v', 'libx264', '-crf', '17', '-pix_fmt', 'yuv420p',
                 '-c:a', 'copy', _wtmp], capture_output=True, text=True)
            if _wr.returncode == 0 and os.path.exists(_wtmp):
                os.replace(_wtmp, out_path)
                print("Watermark: split active (clean master cached)")
            else:
                try:
                    os.remove(_mc)
                except OSError:
                    pass
                print("WARNING: watermark split failed - delivered without a "
                      "watermark")
        except Exception as _we:
            print(f"WARNING: watermark split skipped ({type(_we).__name__})")

    # v101g Kontaktbogen speichern: ein Blick = alle Momente, echtes Compositing.
    if _kb_tiles:
        try:
            _kb = contact_sheet(_kb_tiles, _kb_labels)
            if _kb is not None:
                _kb_path = os.path.splitext(out_path)[0] + '_kontakt.jpg'
                cv2.imwrite(_kb_path, _kb, [cv2.IMWRITE_JPEG_QUALITY, 88])
                print(f"Contact sheet: {len(_kb_tiles)} moment(s) -> {_kb_path}")
        except Exception as _ke:
            print(f"WARNING: contact sheet skipped ({type(_ke).__name__})")

    # v227: WO GEHT DIE ZEIT HIN. Eine Zeile, absteigend nach Kosten - damit
    # die naechste Optimierung an einer MESSUNG haengt und nicht an einem
    # Verdacht. 'other' ist alles Ungemessene; ist es gross, luegt die
    # Messung nicht, sie ist nur unvollstaendig.
    _rep = zeit_report(time.time() - _zt_main)
    if _rep:
        print(_rep)
    print(mem_zeile())
    print(f"Done: {out_path}")

    # v101 Silent-Score: das fertige Video stumm bewerten (74% der Views
    # laufen ohne Ton). Ein guenstiger Vision-Call; ohne Key passiert nichts.
    if cfg['keywords'].get('silent_score', True) and fx_map:
        _sil = silent_score(out_path, words, fx_map,
                            cfg['keywords'].get('ai_model', 'gpt-5'))
        if _sil:
            _sp = os.path.splitext(args.input)[0] + '_silent.json'
            json.dump(_sil, open(_sp, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f"Silent score: {_sil['score']}/100 (impact without sound)")

    # v230d: was dieser Render an KI verbraucht hat. Bewusst GANZ am Ende -
    # der Silent-Score ist auch ein bezahlter Aufruf, und eine Buchhaltung,
    # die den letzten Posten nicht kennt, ist keine. Der Server rechnet
    # daraus Euro; die Preise stehen an EINER Stelle, nicht in jedem Render.
    _aiz = ai_verbrauch_zeile()
    if _aiz:
        print(_aiz)

    # --- Fenster-Segment frame-exakt ins fertige Video einsetzen
    if args.window and args.splice_into:
        if first_abs is None:
            sys.exit("ERROR: the window produced no frames.")
        if not os.path.exists(args.splice_into):
            sys.exit(f"ERROR: target video not found: {args.splice_into}")
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
            sys.exit("ERROR while inserting: " + r.stderr.decode('utf-8', 'ignore')[-300:])
        os.replace(tmp, args.splice_into)
        print(f"Segment inserted: {args.splice_into} "
              f"({t0x:.2f}s - {t1x:.2f}s replaced)")

if __name__ == '__main__':
    main()
