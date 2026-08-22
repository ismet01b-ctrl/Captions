# -*- coding: utf-8 -*-
"""Sound-Pack: echte, aufgenommene Sound-Effekte statt synthetischer.

Warum es das gibt: Die eingebauten Sounds sind aus Formeln erzeugt (Sinus +
Rauschen). Das klingt zwangslaeufig billig - eine echte Studio-Aufnahme holt man
mit Mathematik nicht ein.

Wie es funktioniert: Das Programm laedt CC0-Sounds von Freesound. CC0 heisst
Public Domain - kommerziell frei nutzbar, keine Namensnennung noetig, keine
Weitergabe-Probleme. Andere Lizenzen (CC-BY, CC-BY-NC) werden bewusst NICHT
angefasst, damit hier nie eine Lizenzfalle entsteht.

Eigene Dateien (z.B. aus einem Epidemic-Sound-Abo) gewinnen immer: liegt in
sfx/pack/ eine Datei <slot>.wav, wird die genommen - egal was heruntergeladen
wurde. Die bleibt dann bei dir und steckt nicht in der Software.

Aufruf:
    python sfx_pack.py --key <FREESOUND_KEY> --fetch          # Pack laden
    python sfx_pack.py --key <KEY> --candidates impact        # Auswahl anhoeren
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

API = 'https://freesound.org/apiv2'
CC0 = 'Creative Commons 0'

# Jeder Slot: Suchbegriffe, gewuenschte Laenge, und wofuer er im Video steht.
# Die Begriffe sind bewusst eng - "impact" allein liefert Muell, "impact hit
# cinematic short" trifft das, was gemeint ist.
# Jeder Slot hat eine SUCHKASKADE: von eng nach breit. Der erste Versuch ist
# praezise, die spaeteren immer allgemeiner. Vorher stand hier nur EINE Anfrage mit
# vier Woertern - fand die nichts, blieb der Slot leer. Genau so sind neun Slots
# leer geblieben. Jetzt wird weitergesucht, bis etwas kommt, und zur Not faellt
# auch der Laengenfilter weg.
SLOTS = {
    'impact':      dict(q=['impact hit', 'impact', 'hit punch', 'boom hit'],
                        lo=0.05, hi=3.0, ziel=0.6,
                        # Der meistgeladene "impact" auf Freesound ist oft ein
                        # Glas-Crash oder eine Explosion. Der knallt dann bei JEDEM
                        # grossen Wort - darum werden diese Begriffe abgewertet.
                        meiden=['glass', 'crash', 'shatter', 'break', 'explosion',
                                'gun', 'shot', 'scream', 'car', 'metal pipe'],
                        use='Der Haupt-Einschlag: grosses Wort erscheint'),
    'whoosh':      dict(q=['whoosh', 'swoosh', 'transition whoosh', 'swish'],
                        lo=0.05, hi=3.0,
                        ziel=0.5,
                        meiden=['crash', 'glass', 'explosion', 'scream', 'gun', 'car'],
                        use='Einflug eines Wortes'),
    'whoosh_soft': dict(q=['soft whoosh', 'air whoosh', 'whoosh light', 'whoosh'],
                        lo=0.05, hi=2.5,
                        ziel=0.4,
                        meiden=['crash', 'glass', 'explosion', 'gun', 'scream'],
                        use='dezenter Einflug'),
    'riser':       dict(q=['riser', 'build up', 'rise tension', 'sweep up'],
                        lo=0.2, hi=4.0,
                        ziel=1.2,
                        meiden=['crash', 'glass', 'explosion', 'scream', 'alarm'],
                        use='laeuft auf einen grossen Moment zu'),
    'tick':        dict(q=['click', 'ui click', 'button click', 'tick'],
                        lo=0.005, hi=1.0,
                        ziel=0.1,
                        meiden=['crash', 'glass', 'explosion', 'music', 'song'],
                        use='kleine Wortgruppen, Zaehler-Ticks'),
    'counter':     dict(q=['ticks rolling', 'counter', 'ticking', 'clicks fast'],
                        lo=0.2, hi=4.0,
                        ziel=1.2,
                        meiden=['crash', 'glass', 'explosion', 'music', 'song'],
                        use='Zahl zaehlt hoch'),
    'boom':        dict(q=['cinematic boom', 'boom', 'sub drop', 'deep boom'],
                        lo=0.2, hi=4.0,
                        ziel=1.2,
                        meiden=['glass', 'shatter', 'scream', 'gun', 'shot', 'alarm'],
                        use='der ganz grosse Moment'),
    'crack':       dict(q=['glass break', 'shatter', 'break crack', 'glass smash'],
                        lo=0.05, hi=3.0,
                        ziel=0.7,
                        meiden=['music', 'song', 'voice', 'speech'],
                        use='BRUCH: das Wort zerbricht'),
    'fall':        dict(q=['falling whistle', 'descending', 'fall down', 'downward sweep'],
                        lo=0.1, hi=3.0,
                        ziel=0.8,
                        meiden=['crash', 'glass', 'explosion', 'music', 'voice'],
                        use='STURZ: das Wort faellt'),
    'rise':        dict(q=['rising', 'ascending', 'upward sweep', 'rise up'],
                        lo=0.1, hi=3.0,
                        ziel=0.8,
                        meiden=['crash', 'glass', 'explosion', 'music', 'voice'],
                        use='ANSTIEG: das Wort steigt'),
    'turn':        dict(q=['reverse whoosh', 'spin', 'turn swoosh', 'reverse'],
                        lo=0.05, hi=2.5,
                        ziel=0.5,
                        meiden=['crash', 'glass', 'explosion', 'music', 'voice'],
                        use='WENDE: das Wort kippt um'),
    'press':       dict(q=['creak', 'groan wood', 'pressure', 'stress creak'],
                        lo=0.1, hi=3.5,
                        ziel=0.9,
                        meiden=['crash', 'glass', 'explosion', 'music', 'voice'],
                        use='DRUCK: das Wort wird erdrueckt'),
    'vanish':      dict(q=['magic disappear', 'dissolve', 'sparkle', 'shimmer'],
                        lo=0.1, hi=3.5,
                        ziel=0.9,
                        meiden=['crash', 'glass', 'explosion', 'music', 'voice'],
                        use='SCHWUND: das Wort loest sich auf'),
    'slam':        dict(q=['slam', 'stab hit', 'hard hit', 'punch impact'],
                        lo=0.05, hi=2.5,
                        ziel=0.5,
                        meiden=['glass', 'shatter', 'scream', 'gun', 'shot', 'music'],
                        use='KNALL: die Pointe'),
}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': 'DouchkoVE/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _query(term, key, lo=None, hi=None, n=6):
    flt = f'license:"{CC0}"'
    if lo is not None:
        flt += f' duration:[{lo} TO {hi}]'
    url = (f'{API}/search/text/?query={urllib.parse.quote(term)}'
           f'&filter={urllib.parse.quote(flt)}'
           f'&fields=id,name,tags,duration,license,previews,avg_rating,num_downloads'
           f'&sort=downloads_desc&page_size={n}&token={key}')
    res = _get(url)
    out = []
    for it in res.get('results', []):
        prev = (it.get('previews') or {}).get('preview-hq-mp3')
        if not prev:
            continue
        lic = str(it.get('license', '')).lower()
        # Doppelt gesichert: nur CC0. Alles andere waere ein Rechteproblem.
        if 'publicdomain/zero' not in lic and CC0.lower() not in lic:
            continue
        out.append({'id': it['id'], 'name': it.get('name', '?'),
                    'tags': [str(t).lower() for t in (it.get('tags') or [])],
                    'duration': round(float(it.get('duration', 0)), 2),
                    'downloads': it.get('num_downloads', 0),
                    'rating': float(it.get('avg_rating') or 0),
                    'license': it.get('license', ''), 'preview': prev,
                    'suche': term})
    return out


def score(cand, slot):
    """Bewertet einen Kandidaten. Vorher wurde stur der meistgeladene genommen -
    und der meistgeladene "impact" auf Freesound ist ein Glas-Crash. Der knallte
    dann bei jedem grossen Wort. Jetzt zaehlt auch, ob der Sound zum Slot PASST."""
    s = SLOTS[slot]
    txt = (cand['name'] + ' ' + ' '.join(cand.get('tags', []))).lower()
    sc = 0.0
    # 1) Passt der Klang ueberhaupt? Fremdes Material fliegt hart raus.
    for bad in s.get('meiden', []):
        if bad in txt:
            sc -= 8.0
    # 2) Trifft der Sound den gesuchten Begriff?
    for w in s['q'][0].split():
        if w in txt:
            sc += 2.5
    # 3) Laenge nahe am Zielmass (ein 3-s-Impact taugt nichts)
    ziel = s.get('ziel')
    if ziel:
        sc -= min(abs(cand['duration'] - ziel) / max(ziel, 0.2), 3.0) * 1.6
    # 4) Qualitaet: Bewertung zaehlt mehr als reine Download-Zahl
    sc += min(cand.get('rating', 0), 5.0) * 0.7
    sc += min(cand['downloads'], 5000) / 5000.0 * 1.2
    return sc


def search(slot, key, n=6, log=None):
    """Sucht Kandidaten. Kaskade: erst eng, dann breiter, zuletzt ohne
    Laengenfilter. Ein Slot bleibt nur leer, wenn wirklich NICHTS existiert."""
    s = SLOTS[slot]
    seen, out = set(), []
    for term in s['q']:
        for lo, hi in ((s['lo'], s['hi']), (None, None)):
            try:
                for c in _query(term, key, lo, hi, n):
                    if c['id'] not in seen:
                        seen.add(c['id'])
                        out.append(c)
            except Exception as e:
                if log:
                    log(f"    Suche '{term}' fehlgeschlagen: {type(e).__name__}")
            if len(out) >= n * 2:
                out.sort(key=lambda c: score(c, slot), reverse=True)
                return out[:n]
        if out:                       # bei diesem Begriff was gefunden - reicht
            break
    out.sort(key=lambda c: score(c, slot), reverse=True)
    return out[:n]


def fetch_one(cand, dest_wav):
    """Laedt eine Vorschau (mp3), wandelt sie in WAV, normalisiert und schneidet
    die Stille ab - damit das Timing im Video exakt sitzt."""
    tmp = dest_wav + '.mp3'
    req = urllib.request.Request(cand['preview'],
                                 headers={'User-Agent': 'DouchkoVE/1.0'})
    with urllib.request.urlopen(req, timeout=40) as r, open(tmp, 'wb') as f:
        f.write(r.read())
    # 44.1 kHz mono, Stille vorne weg, Pegel normalisiert
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', tmp,
           '-af', 'silenceremove=start_periods=1:start_threshold=-50dB:'
                  'start_silence=0.01,loudnorm=I=-16:TP=-1.5:LRA=11',
           '-ar', '44100', '-ac', '1', dest_wav]
    subprocess.run(cmd, check=True)
    os.remove(tmp)
    return dest_wav


def pack_dir(here=None):
    here = here or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, 'sfx', 'pack')


def load_manifest(pdir):
    p = os.path.join(pdir, 'pack.json')
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_manifest(pdir, man):
    os.makedirs(pdir, exist_ok=True)
    json.dump(man, open(os.path.join(pdir, 'pack.json'), 'w', encoding='utf-8'),
              indent=1, ensure_ascii=False)


def fetch_pack(key, pdir=None, slots=None, progress=print, pick=0):
    """Laedt fuer jeden Slot den meistgeladenen CC0-Sound. Vorhandene eigene
    Dateien werden NICHT ueberschrieben (Epidemic-Dateien gewinnen)."""
    pdir = pdir or pack_dir()
    os.makedirs(pdir, exist_ok=True)
    man = load_manifest(pdir)
    ok, fail = 0, []
    for slot in (slots or SLOTS):
        dest = os.path.join(pdir, slot + '.wav')
        if man.get(slot, {}).get('eigen'):
            progress(f'  {slot}: eigene Datei - bleibt unangetastet')
            ok += 1
            continue
        try:
            cands = search(slot, key)
            if not cands:
                fail.append(slot)
                progress(f'  {slot}: kein CC0-Treffer')
                continue
            c = cands[min(pick, len(cands) - 1)]
            fetch_one(c, dest)
            man[slot] = {'id': c['id'], 'name': c['name'], 'license': 'CC0',
                         'quelle': f"https://freesound.org/s/{c['id']}/",
                         'dauer': c['duration']}
            # v96d: bis zu 2 weitere CC0-Treffer als Varianten (slot_1/2.wav) -
            # mehr Abwechslung, damit nicht jeder Klick gleich klingt.
            vn = 0
            for extra in cands[min(pick, len(cands) - 1) + 1:]:
                if vn >= 2:
                    break
                try:
                    fetch_one(extra, os.path.join(pdir, f'{slot}_{vn + 1}.wav'))
                    man[f'{slot}_{vn + 1}'] = {
                        'id': extra['id'], 'name': extra['name'], 'license': 'CC0',
                        'quelle': f"https://freesound.org/s/{extra['id']}/",
                        'dauer': extra['duration'], 'variante': slot}
                    vn += 1
                except Exception:
                    pass
            ok += 1
            progress(f"  {slot}: {c['name'][:40]} ({c['duration']}s)"
                     + (f" +{vn} Varianten" if vn else ""))
        except Exception as e:
            fail.append(slot)
            progress(f'  {slot}: Fehler - {type(e).__name__}')
    save_manifest(pdir, man)
    progress(f'Sound-Pack: {ok}/{len(slots or SLOTS)} Slots belegt')
    return ok, fail


def scan_eigene(pdir=None):
    """Erkennt eigene Dateien im Pack-Ordner (z.B. aus Epidemic Sound) und
    markiert sie, damit ein spaeterer Download sie nicht ueberschreibt."""
    pdir = pdir or pack_dir()
    if not os.path.isdir(pdir):
        return 0
    man = load_manifest(pdir)
    n = 0
    for slot in SLOTS:
        f = os.path.join(pdir, slot + '.wav')
        if os.path.exists(f) and slot not in man:
            man[slot] = {'eigen': True, 'license': 'eigene Lizenz',
                         'name': slot + '.wav'}
            n += 1
    if n:
        save_manifest(pdir, man)
    return n


def pack_status(pdir=None):
    pdir = pdir or pack_dir()
    man = load_manifest(pdir)
    have = [s for s in SLOTS
            if os.path.exists(os.path.join(pdir, s + '.wav'))]
    return {'ordner': pdir, 'belegt': len(have), 'gesamt': len(SLOTS),
            'slots': have, 'manifest': man}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', required=True)
    ap.add_argument('--fetch', action='store_true')
    ap.add_argument('--candidates')
    ap.add_argument('--slot')
    ap.add_argument('--pick', type=int, default=0)
    a = ap.parse_args()
    if a.candidates:
        for i, c in enumerate(search(a.candidates, a.key)):
            print(f"[{i}] {c['name'][:50]:52} {c['duration']:5.2f}s  "
                  f"{c['downloads']:>7} Downloads  {c['preview']}")
    elif a.fetch:
        scan_eigene()
        fetch_pack(a.key, slots=[a.slot] if a.slot else None, pick=a.pick)
    print(json.dumps(pack_status(), indent=1, ensure_ascii=False))
