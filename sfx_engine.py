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


# v96d: Mikro-Variation. Selbst mit EINER Datei pro Slot soll nicht jeder Klick
# identisch klingen (der "immer gleiche Maus-Klick"). Deterministische Folge aus
# leichten Pitch- und Pegel-Abweichungen pro Platzierung + optionale Varianten-
# Dateien (slot_1.wav ...), die reihum durchgewechselt werden.
_JIT_P = (1.000, 0.955, 1.052, 0.928, 1.081, 0.985, 1.033, 0.910, 1.068, 0.972)
_JIT_G = (1.00, 0.90, 1.09, 0.94, 1.06, 0.88, 1.10, 0.97, 1.04, 0.92)


def _pitch(sig, f):
    """Leichter Pitch-/Zeit-Shift durch Resampling (f>1 = kuerzer+heller)."""
    if sig is None or len(sig) < 8 or abs(f - 1.0) < 1e-3:
        return sig
    idx = np.arange(0, len(sig) - 1, f, dtype=np.float32)
    return np.interp(idx, np.arange(len(sig)), sig).astype(np.float32)


def load_variants(folder=None):
    """Wie load_bank, aber pro Slot ALLE Varianten: slot.wav + slot_1.wav ...
    Rueckgabe: {slot: [signal, ...]} - erste ist die Hauptdatei."""
    pdir = folder or pack_folder()
    out = {}
    if not os.path.isdir(pdir):
        return out
    for slot in SLOTS:
        sigs = []
        names = [slot + '.wav'] + [f'{slot}_{k}.wav' for k in range(1, 6)]
        for name in names:
            p = os.path.join(pdir, name)
            if os.path.exists(p):
                try:
                    s = load_wav(p)
                    if len(s) > 64:
                        sigs.append(s)
                except Exception:
                    pass
        if sigs:
            out[slot] = sigs
    return out


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
    # v96d: Varianten + Mikro-Variation, damit sich wiederkehrende Sounds (v.a.
    # der Tick/Klick) nicht identisch anhoeren. V(slot) wechselt reihum durch
    # die Varianten-Dateien und legt pro Aufruf einen leichten Pitch/Pegel-Jitter
    # drauf - auch bei nur einer Datei klingt jeder Einsatz minimal anders.
    _variants = load_variants(folder if (folder and os.path.isdir(folder)) else None)
    _vc = {}
    _nvar = sum(len(v) for v in _variants.values())
    if _nvar > len(_variants):
        print(f"  SFX-Varianten: {_nvar} Dateien fuer {len(_variants)} Slots "
              f"(mehr Abwechslung)")

    def V(slot):
        """Naechste Variante eines Slots mit Pitch/Pegel-Jitter - oder None."""
        vs = _variants.get(slot)
        if not vs:
            return bank.get(slot)          # kein Varianten-Eintrag -> Original
        c = _vc.get(slot, 0)
        _vc[slot] = c + 1
        sig = vs[c % len(vs)]
        return _pitch(sig, _JIT_P[c % len(_JIT_P)]) * _JIT_G[c % len(_JIT_G)]
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
            place(V('whoosh'), t0 - 0.30, 0.8 * g)
            place(V('impact'), t0 - 0.02, 1.0 * g)
        elif tpl == 'blurin':
            place(V('riser'), t0 - 0.78, 0.9 * g)
            place(V('tick'), t0 + 0.12, 0.5 * g)           # v96g: naeher am Wort
        elif tpl == 'cascade':
            place(V('whoosh_soft'), t0 - 0.05, 0.9 * g)
            for k, dt_l in enumerate((0.04, 0.11, 0.18)):     # Buchstaben-Laeufer, enger am Onset
                place(V('tick'), t0 + dt_l, (0.30 - k * 0.07) * g)
        elif tpl == 'ground':
            place(V('whoosh_soft'), t0 - 0.05, 0.9 * g)
            place(V('impact'), t0 + 0.08, 0.45 * g)        # der Text "steht"
        elif tpl == 'outline':
            place(V('whoosh_soft'), t0 - 0.05, 0.55 * g)
            place(V('tick'), t0 + 0.08, 0.9 * g)           # v96g: sitzt auf dem Wort
        n_placed += 1
        w = words[p['kw_i']]['word'].strip()
        print(f"  SFX '{w}': Onset {off*1000:+.0f} ms, Pegel x{g:.2f}"
              + (' +Boom' if pw >= 3 else ''))
    # Folge-Captions (laufende Wortgruppen): JEDE bekommt einen dezenten
    # Einflug-Sound. Vorher lief nur ein rate-begrenzter Micro-Tick (>=1s
    # Abstand + nahe Keywords unterdrueckt) - Ergebnis: bei drei Captions
    # hintereinander klang nur die erste, danach Stille -> wirkte unfertig.
    # Jetzt fliegt jede Caption hoerbar ein (weicher Whoosh, sonst Tick),
    # nur echtes Uebereinander und der Keyword-Einschlag selbst werden gemieden.
    last_tick = -9.0
    n_ticks = 0
    _acc_i = 0
    _soft_slot = ('whoosh_soft' if 'whoosh_soft' in bank
                  else 'whoosh' if 'whoosh' in bank else 'tick')
    for p in plans:
        if p.get('tpl') != 'stack':
            continue
        ts, _ = snap(p['start'])
        if ts - last_tick < 0.28:
            continue                       # nur echtes Uebereinander vermeiden
        if any(abs(ts - kt) < 0.32 for kt in kw_times):
            continue                       # nicht direkt auf den Keyword-Einschlag
        g_soft = local_gain(ts)
        place(V(_soft_slot), ts - 0.04, 0.42 * g_soft)   # weicher Einflug, variiert
        # v96g: der Klick-Akzent lief bisher auf JEDER Folge-Caption -> im dichten
        # Hook ein monotoner Klick-Teppich. Jetzt im 3er-Zyklus: lauter Tick /
        # leiser Tick / GAR KEINER (Atempause) - dazu variiert V() Pitch/Pegel.
        # Ergebnis: weniger Klicks, mehr Abwechslung, v.a. im Hook. Tick sitzt
        # eng auf dem Wort-Einsatz (+0.02) statt hinterher.
        _acc_i += 1
        _cyc = _acc_i % 3
        if _cyc == 0:
            place(V('tick'), ts + 0.02, 0.24 * g_soft)
        elif _cyc == 1:
            place(V('tick'), ts + 0.02, 0.15 * g_soft)   # leiser, andere Variante
        # _cyc == 2: kein Akzent -> bricht die Monotonie
        last_tick = ts
        n_ticks += 1
    if n_ticks:
        print(f"  SFX: {n_ticks} Einflug-Sounds auf Folge-Captions")
        n_placed += n_ticks
    peak = np.abs(total).max()
    if peak > 1.0:
        total /= peak
    _save(out_path, total)
    return n_placed
