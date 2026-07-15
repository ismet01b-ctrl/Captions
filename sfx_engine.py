# -*- coding: utf-8 -*-
"""DouchkoVE SFX-Engine: erzeugt Cinematic-Sounds prozedural (lizenzfrei).
Die WAVs landen im sfx/-Ordner und koennen dort durch eigene Dateien ersetzt werden."""
import os
import wave
import numpy as np

SR = 44100

def _save(path, sig):
    peak = float(np.abs(sig).max())
    if peak > 0.98:
        sig = sig * (0.95 / peak)      # normalisieren statt clippen (kein Klirren)
    sig = np.clip(sig, -1, 1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())

# Die Slots, die das Video benutzt. Es gibt KEINE synthetischen Sounds mehr -
# jeder Slot wird ausschliesslich aus dem Sound-Pack (sfx/pack/<slot>.wav) geladen.
# Fehlt ein Slot, wird an dieser Stelle einfach kein Sound gesetzt. Lieber Stille
# als ein billiger Ersatzton.
SLOTS = ('impact', 'whoosh', 'whoosh_soft', 'riser', 'tick', 'counter', 'boom',
         'crack', 'fall', 'rise', 'turn', 'press', 'vanish', 'slam')

ANIM_SFX = {
    'bruch':   ('crack',  0.02, 0.95),
    'sturz':   ('fall',  -0.05, 0.85),
    'anstieg': ('rise',  -0.10, 0.80),
    'wende':   ('turn',  -0.04, 0.75),
    'druck':   ('press',  0.00, 0.70),
    'schwund': ('vanish', 0.15, 0.65),
    'knall':   ('slam',   0.00, 1.18),   # Punchline sitzt lauter (Feed-Standard)
}

def pack_folder(here=None):
    here = here or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, 'sfx', 'pack')


def ensure_sfx(folder=None):
    """Frueher wurden hier synthetische Sounds erzeugt. Die sind ersatzlos raus -
    aus Formeln erzeugte Sounds klingen billig, und ein billiger Sound ist
    schlechter als gar keiner. Es gilt nur noch der Sound-Pack."""
    return pack_folder()


def load_bank(folder=None):
    """Laedt die echten Sounds. Rueckgabe: {slot: signal} - nur was da ist."""
    pdir = folder or pack_folder()
    bank = {}
    if not os.path.isdir(pdir):
        return bank
    for slot in SLOTS:
        p = os.path.join(pdir, slot + '.wav')
        if os.path.exists(p):
            try:
                sig = load_wav(p)
                if len(sig) > 64:
                    bank[slot] = sig
            except Exception:
                pass
    return bank


def load_wav(path):
    with wave.open(path, 'rb') as w:
        n = w.getnframes()
        sig = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32767.0
        if w.getnchannels() == 2:
            sig = sig.reshape(-1, 2).mean(axis=1)
        sr = w.getframerate()
    if sr != SR:
        idx = np.linspace(0, len(sig) - 1, int(len(sig) * SR / sr))
        sig = np.interp(idx, np.arange(len(sig)), sig)
    return sig

def _energy(sig, win=882, hop=441):
    """Kurzzeit-RMS-Huellkurve (20ms Fenster, 10ms Schritt)."""
    n = (len(sig) - win) // hop
    if n <= 0:
        return np.zeros(1), hop
    idx = np.arange(n)[:, None] * hop + np.arange(win)[None, :]
    return np.sqrt((sig[idx] ** 2).mean(axis=1)), hop

def clean_word(w):
    return ''.join(ch for ch in w if ch.isalnum())


def build_sfx_track(plans, words, duration, folder, out_path, voice_wav=None, powers=None):
    """Setzt die Sounds intelligent: Onset-Snapping auf den echten Sprech-Einsatz,
    Lautstaerke adaptiv zur lokalen Stimm-Energie, Wucht nach KI-Regie-Bewertung."""
    # Es gibt NUR das Sound-Pack. Fehlt ein Sound, wird er nicht gesetzt -
    # ein synthetischer Ersatzton waere schlechter als Stille.
    bank = load_bank(folder if (folder and os.path.isdir(folder)) else None)
    if not bank:
        print("Kein Sound-Pack gefunden - das Video bekommt KEINE Sound-Effekte.")
        print("  Sounds laden: GUI -> Profi -> Sound-Pack -> 'Echte Sounds laden'")
        _save(out_path, np.zeros(int(duration * SR), dtype=np.float32))
        return 0
    fehlt = [s for s in SLOTS if s not in bank]
    print(f"Sound-Pack: {len(bank)}/{len(SLOTS)} echte Sounds geladen"
          + (f" (fehlen: {', '.join(fehlt)})" if fehlt else ""))
    total = np.zeros(int((duration + 1.5) * SR), dtype=np.float32)

    env, hop, ref = None, 441, None
    if voice_wav and os.path.exists(voice_wav):
        voice = load_wav(voice_wav)
        env, hop = _energy(voice)
        speech = env[env > np.percentile(env, 25) * 2]
        ref = float(np.median(speech)) if len(speech) else None

    def snap(t):
        """Zieht t auf den steilsten Energie-Anstieg im Umfeld (echter Wort-Einsatz)."""
        if env is None:
            return t, 0.0
        a = max(int((t - 0.15) * SR / hop), 1)
        b = min(int((t + 0.22) * SR / hop), len(env) - 1)
        if b - a < 3:
            return t, 0.0
        d = np.diff(env[a:b])
        k = int(np.argmax(d))
        t_new = (a + k + 1) * hop / SR
        return t_new, (t_new - t)

    def local_gain(t):
        """Passt die SFX-Lautstaerke an die lokale Stimm-Energie an."""
        if env is None or not ref:
            return 1.0
        a = max(int(t * SR / hop), 0)
        b = min(int((t + 0.5) * SR / hop), len(env))
        if b <= a:
            return 1.0
        rel = float(env[a:b].mean()) / ref
        return float(np.clip(0.6 + 0.55 * rel, 0.6, 1.25))

    POW = {1: 0.6, 2: 0.9, 3: 1.15}

    def place(sig, t, gain=1.0):
        if sig is None or len(sig) < 8:      # Slot nicht im Pack -> kein Sound
            return
        if t < 0:
            sig = sig[int(-t * SR):]
            t = 0.0
        i = int(t * SR)
        j = min(i + len(sig), len(total))
        if j > i:
            total[i:j] += sig[:j - i] * gain

    n_placed = 0
    kw_times = []                          # fuer den Anti-Matsch-Limiter der Stacks
    for p in plans:
        if 'kw_i' not in p:
            continue
        t_raw = p.get('t0', words[p['kw_i']]['start'])   # Sofort-Hook: Sound ab Frame 1
        t0, off = snap(t_raw)
        kw_times.append(t0)
        pw = (powers or {}).get(p['kw_i'], 2)
        if isinstance(pw, dict):
            pw = pw.get('power', 2)
        g = local_gain(t0) * POW.get(pw, 0.9) * (0.55 if pw <= 1 else 1.0)
        tpl = p['tpl']
        # ANIMATIONS-SOUND: was das Wort TUT, hoert man auch. Liegt als eigene
        # Ebene UEBER dem Effekt-Sound - der Effekt sagt "ein Moment kommt",
        # die Animation sagt "und er bricht/faellt/steigt".
        _an = p.get('anim')
        if _an in ANIM_SFX:
            _nm, _off, _gn = ANIM_SFX[_an]
            if _nm in bank:
                place(bank[_nm], t0 + _off, _gn * g)
            print(f"  SFX '{clean_word(words[p['kw_i']]['word'])}': "
                  f"{_an} ({_nm})")
        # Grosse Momente (power 3) bekommen eine eigene Ebene: Riser rein, Boom drunter
        if pw >= 3:
            place(bank.get('riser'), t0 - 0.85, 0.7 * local_gain(t0))
            place(bank.get('boom'), t0 + 0.02, 0.85 * local_gain(t0))
        if p.get('count'):
            # Zaehler-SFX rollt exakt so lange wie die Zahl hochzaehlt
            cdur = 1.0
            if isinstance(p['count'], dict):
                try:
                    cdur = float(p['count'].get('dur', 1.0))
                except Exception:
                    cdur = 1.0
            # Der Zaehler muss exakt so lange rollen wie die Zahl hochzaehlt.
            # Frueher wurde dafuer ein Sound in passender Laenge SYNTHETISIERT.
            # Jetzt wird er aus den echten Ticks des Packs gebaut: Ticks, die
            # ausrollen (immer groessere Abstaende), am Ende ein Einschlag.
            if 'counter' in bank and abs(len(bank['counter']) / SR - cdur) < 0.35:
                place(bank['counter'], t_raw, 1.3 * max(g, 0.75))
            elif 'tick' in bank:
                tp, gapc = 0.0, 0.030
                while tp < max(cdur - 0.10, 0.05):
                    place(bank['tick'], t_raw + tp,
                          (0.85 - 0.35 * (tp / max(cdur, 1e-6))) * max(g, 0.7))
                    gapc *= 1.16                      # rollt aus
                    tp += gapc
                _end = bank.get('impact')
                if _end is None:
                    _end = bank.get('slam')
                place(_end, t_raw + cdur, 0.9 * max(g, 0.75))   # Einschlag auf der Zahl
            else:
                place(bank.get('counter'), t_raw, 1.3 * max(g, 0.75))
            n_placed += 1
            print(f"  SFX '{clean_word(words[p['kw_i']]['word'])}': Hochzaehlen ({cdur:.1f}s)")
            continue
        if tpl == 'behind':
            place(bank.get('whoosh'), t0 - 0.30, 0.8 * g)
            place(bank.get('impact'), t0 - 0.02, 1.0 * g)
        elif tpl == 'blurin':
            place(bank.get('riser'), t0 - 0.78, 0.9 * g)
            place(bank.get('tick'), t0 + 0.30, 0.5 * g)
        elif tpl == 'cascade':
            place(bank.get('whoosh_soft'), t0 - 0.05, 0.9 * g)
            for k, dt_l in enumerate((0.10, 0.19, 0.27)):     # Buchstaben-Laeufer
                place(bank.get('tick'), t0 + dt_l, (0.30 - k * 0.07) * g)
        elif tpl == 'ground':
            place(bank.get('whoosh_soft'), t0 - 0.05, 0.9 * g)
            place(bank.get('impact'), t0 + 0.12, 0.45 * g)        # der Text "steht"
        elif tpl == 'outline':
            place(bank.get('whoosh_soft'), t0 - 0.05, 0.55 * g)
            place(bank.get('tick'), t0 + 0.26, 0.9 * g)
        n_placed += 1
        w = words[p['kw_i']]['word'].strip()
        print(f"  SFX '{w}': Onset {off*1000:+.0f} ms, Pegel x{g:.2f}"
              + (' +Boom' if pw >= 3 else ''))
    # Stacks (laufende Wortgruppen): fuehlbarer Micro-Tick, aber nie im Weg
    last_tick = -9.0
    n_ticks = 0
    for p in plans:
        if p.get('tpl') != 'stack':
            continue
        ts, _ = snap(p['start'])
        if ts - last_tick < 1.0:
            continue                       # Anti-Matsch: Ticks nicht haeufen
        if any(abs(ts - kt) < 0.9 for kt in kw_times):
            continue                       # Keyword-Momente behalten die Buehne
        place(bank.get('tick'), ts, 0.30 * local_gain(ts))
        last_tick = ts
        n_ticks += 1
    if n_ticks:
        print(f"  SFX: {n_ticks} Micro-Ticks auf Wortgruppen")
        n_placed += n_ticks
    peak = np.abs(total).max()
    if peak > 1.0:
        total /= peak
    _save(out_path, total)
    return n_placed
