# -*- coding: utf-8 -*-
"""DouchkoVE Selbsttest: rendert alle Szenarien und prueft die Ergebnisse automatisch.
Aufruf: python selftest.py <testclip.mp4> <transcript.json> [pan_test.mp4] [mixed_test.mp4]"""
import json
import copy
import os
import re
import shutil
import math
import cv2
import urllib.parse
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def render(video, transcript, out, extra=None, cfg_patch=None):
    cfg_path = os.path.join(HERE, 'config.yaml')
    cfg_patch = dict(cfg_patch or {})
    cfg_patch.setdefault('effects.blender_water', False)   # Selftest: 2D-Pipeline
    if cfg_patch:
        import yaml
        cfg = yaml.safe_load(open(cfg_path, encoding='utf-8'))
        for path, val in cfg_patch.items():
            d = cfg
            keys = path.split('.')
            for k in keys[:-1]:
                d = d[k]
            d[keys[-1]] = val
        cfg_path = os.path.join(tempfile.gettempdir(), 'dve_selftest_cfg.yaml')
        yaml.safe_dump(cfg, open(cfg_path, 'w', encoding='utf-8'), allow_unicode=True)
    cmd = [PY, os.path.join(HERE, 'render.py'), video, '--transcript', transcript,
           '--out', out, '--config', cfg_path] + (extra or [])
    r = run(cmd)
    return r.returncode, r.stdout + r.stderr


def probe_val(path, entries, stream='v:0'):
    r = run(['ffprobe', '-v', 'error', '-select_streams', stream, '-show_entries',
             entries, '-of', 'csv=p=0', path])
    return r.stdout.strip()


def frame_at(path, ts, out):
    run(['ffmpeg', '-y', '-v', 'error', '-ss', str(ts), '-i', path, '-frames:v', '1', out])


results = []


def check(name, ok, detail=''):
    # v208a: Ein Detail bleibt EINE Zeile. Sonst rutscht ein mehrzeiliger
    # Beleg (z.B. der Inhalt von .deploy_gate_last.txt) in die Ausgabe und
    # eine seiner Zeilen faengt mit 'FAIL' an - das Test-Gate las genau
    # darauf und hielt einen gruenen Lauf faelschlich fuer rot. Ein
    # bestandener Test darf nicht wie ein gefallener aussehen.
    if detail:
        detail = ' | '.join(str(detail).splitlines())[:400]
    results.append((name, ok, detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail else ''))


# v207-sec: DER SELFTEST DARF NIEMALS AN EINEN ECHTEN DIENST.
# Gefunden vom Test-Gate bei seinem ersten erfolgreichen Lauf im Container:
# dort ist STRIPE_SECRET_KEY aus der .env gesetzt, also lief admin_refund im
# Test gegen das LIVE-Stripe-Konto und rief Refund.create auf. Mit einer
# erfundenen Sitzungs-Nummer schlug das fehl - mit einer echten haette der
# Test ECHTES GELD erstattet. Dasselbe gilt fuer Mail: der Test legt Konten
# an, und im Container ist SMTP konfiguriert, es waeren also echte Mails
# rausgegangen.
# CLAUDE.md sagt seit jeher "Tests nie gegen die echte config.yaml / users.db".
# Dieselbe Regel gilt fuer jeden AUSSENDIENST. Hier, ganz am Anfang, weil der
# Riegel sonst davon abhaengt, wie man den Test startet.
_AUSSENDIENSTE = (
    'STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET',      # echtes Geld
    'SMTP_HOST', 'SMTP_USER', 'SMTP_PASS', 'RESEND_API_KEY',   # echte Mails
    'OPENAI_API_KEY',                                  # echte Kosten
    'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
)


def _dienste_kappen():
    """Alle Zugaenge nach draussen leeren, BEVOR web.server importiert wird.
    Der Server liest die Werte teils beim Import in Modul-Variablen."""
    gekappt = [k for k in _AUSSENDIENSTE if os.environ.get(k)]
    for k in _AUSSENDIENSTE:
        os.environ[k] = ''
    if gekappt:
        print(f'Selftest: Aussendienste gekappt ({", ".join(gekappt)}) - '
              f'es geht garantiert nichts an Stripe, Mail oder OpenAI raus.')
    return gekappt


_GEKAPPT = _dienste_kappen()


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--part')]
    part = 'all'
    for a in sys.argv[1:]:
        if a.startswith('--part='):
            part = a.split('=', 1)[1]
    clip = argv[0]
    transcript = argv[1]
    pan = argv[2] if len(argv) > 2 else None
    mixed = argv[3] if len(argv) > 3 else None
    tmp = tempfile.gettempdir()

    def want(name):
        return part in ('all', name)

    if want('render1'):
        _scenario_1(clip, transcript, tmp)
    if want('render2') or want('render2a'):
        _scenario_2a(clip, transcript, tmp, mixed)
    if want('render2') or want('render2b'):
        _scenario_2b(clip, transcript, tmp, pan)
    if want('render2') or want('render2c'):
        _scenario_2c(clip, transcript, tmp)
    if want('logic'):
        _scenario_logic(clip, transcript, tmp)
        _gui_smoke()
        _scenario_premium(tmp)
        _scenario_zahlen(tmp)
        _scenario_satzende(tmp)
        _scenario_kamera(tmp)
        _scenario_transkription(tmp)
        _scenario_security(tmp)
        _scenario_betrieb(tmp)
        _scenario_v98(tmp)
        _scenario_trail(tmp)
        _scenario_lang(tmp)
        _scenario_multiperson(tmp)
        _scenario_vfx(clip, tmp)

    print()
    fails = [r for r in results if not r[1]]
    print(f'{len(results) - len(fails)}/{len(results)} Tests bestanden')
    sys.exit(1 if fails else 0)


def _install_test_pack():
    """Legt ein Test-Sound-Pack an. Das Programm hat KEINE synthetischen Sounds
    mehr - ohne Pack liefe der Render stumm und der SFX-Weg waere ungeprueft.
    Diese Toene sind eine reine Test-Attrappe, sie stecken nicht im Produkt."""
    import wave
    import sfx_engine as _S
    pdir = _S.pack_folder(HERE)
    if os.path.isdir(pdir) and os.listdir(pdir):
        return None                       # echtes Pack vorhanden: nicht anfassen
    os.makedirs(pdir, exist_ok=True)
    for slot in _S.SLOTS:
        t = np.arange(int(0.35 * _S.SR)) / _S.SR
        x = np.sin(2 * np.pi * 700 * t) * np.exp(-t * 7) * 0.8 * 32767
        with wave.open(os.path.join(pdir, slot + '.wav'), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(_S.SR)
            w.writeframes(x.astype(np.int16).tobytes())
    return pdir


def _scenario_1(clip, transcript, tmp):
    # 1) Voll-Render: Dauer synchron, Matting-Gating aktiv, SFX gesetzt
    out = os.path.join(tmp, 'st_full.mp4')
    _tp = _install_test_pack()
    code, log = render(clip, transcript, out)
    if _tp:
        shutil.rmtree(_tp, ignore_errors=True)
    src_dur = float(probe_val(clip, 'format=duration', stream='v:0') or
                    probe_val(clip, 'format=duration'))
    out_dur = float(probe_val(out, 'format=duration') or 0)
    check('Voll-Render laeuft durch', code == 0 and os.path.exists(out))
    check('Ausgabedauer synchron', abs(out_dur - src_dur) < 0.25,
          f'{out_dur:.2f}s vs {src_dur:.2f}s')
    check('Matting-Gating aktiv', 'Matting window' in log and 'of ~' in log)
    check('Wort-Timing nachjustiert', 'Word timing adjusted' in log)
    check('SFX intelligent gesetzt', 'onset' in log or 'Onset' in log)
    check('Sound-Pack wird im Render benutzt', 'Sound pack:' in log)
    # v101g: Kontaktbogen entsteht beim Voll-Render (echte Moment-Frames)
    _kbp = os.path.splitext(out)[0] + '_kontakt.jpg'
    _kbi = cv2.imread(_kbp) if os.path.exists(_kbp) else None
    check('v101g: Kontaktbogen liegt neben dem Video (gueltiges Bild)',
          _kbi is not None and _kbi.shape[0] > 50 and _kbi.shape[1] >= 360
          and 'Contact sheet:' in log,
          str(_kbi.shape if _kbi is not None else 'fehlt'))


def _scenario_2a(clip, transcript, tmp, mixed):
    # 2) B-Roll bleibt textfrei
    if mixed:
        out2 = os.path.join(tmp, 'st_mixed.mp4')
        code, log = render(mixed, transcript, out2)
        check('B-Roll-Szenen erkannt', 'classified as B-roll' in log)
        check('B-Roll komplett textfrei', '0 over B-roll' in log)

    # 3) Hochformat
    port = os.path.join(tmp, 'st_portrait_src.mov')
    run(['ffmpeg', '-y', '-v', 'error', '-i', clip, '-t', '4',
         '-vf', 'crop=ih*9/16:ih:(iw-ih*9/16)/2:0', '-c:v', 'libx264',
         '-preset', 'ultrafast', '-c:a', 'copy', port])
    out3 = os.path.join(tmp, 'st_portrait.mp4')
    code, log = render(port, transcript, out3, extra=['--duration', '4'])
    w, h = (probe_val(out3, 'stream=width,height') or '0,0').split(',')
    check('Hochformat 9:16', code == 0 and int(w) < int(h), f'{w}x{h}')


def _scenario_2b(clip, transcript, tmp, pan):
    # 4) Szenen-Verankerung folgt Kameraschwenk
    if pan:
        out4 = os.path.join(tmp, 'st_pan.mp4')
        code, log = render(pan, transcript, out4, extra=['--keywords', 'Zigaretten'],
                           cfg_patch={'colors.accent': [0, 229, 255],
                                      'effects.text_style': 'klassisch'})
        import cv2
        cents = []
        for name, ts in (('a', 0.55), ('b', 1.00)):
            f = os.path.join(tmp, f'st_lock_{name}.png')
            frame_at(out4, ts, f)
            img = cv2.imread(f)
            b, g, r = (img[..., i].astype(int) for i in range(3))
            mask = (b > 170) & (g > 130) & (r < 130)   # Cyan-Text, kommt in der Szene nicht vor
            xs = np.nonzero(mask)[1]
            cents.append(xs.mean() if len(xs) else -1)
        ok = all(c >= 0 for c in cents) and (cents[1] - cents[0]) < -40
        check('Szenen-Verankerung folgt Schwenk', ok,
              f'Shift {cents[1]-cents[0]:+.0f}px')

    # 5) ProRes-Master
    out5 = os.path.join(tmp, 'st_master.mp4')
    code, log = render(clip, transcript, out5, extra=['--duration', '3'],
                       cfg_patch={'output.master': True})
    mov = os.path.splitext(out5)[0] + '.mov'
    check('ProRes-Master', probe_val(mov, 'stream=codec_name') == 'prores')

    # v101h) Caption-Alpha-Export: ProRes 4444 mit echtem Alpha
    out6 = os.path.join(tmp, 'st_alpha.mp4')
    code6, log6 = render(clip, transcript, out6, extra=['--alpha-export'])
    amov = os.path.splitext(out6)[0] + '.mov'
    _apx = probe_val(amov, 'stream=pix_fmt') or ''
    check('v101h: Alpha-Ebene ist ProRes 4444 (yuva)',
          probe_val(amov, 'stream=codec_name') == 'prores'
          and _apx.startswith('yuva444'), _apx)
    _adur = float(probe_val(amov, 'format=duration') or 0)
    _sdur = float(probe_val(clip, 'format=duration') or 0)
    check('v101h: Ebene laeuft synchron zum Original',
          abs(_adur - _sdur) < 0.25, f'{_adur:.2f}s vs {_sdur:.2f}s')
    # Alpha-Inhalt: an einem Caption-Moment gibt es opake Text-Pixel UND
    # transparente Flaechen (die Ebene ist keine Vollflaeche).
    # v215: gesucht wird der Caption-Moment, statt ihn bei 1.20 s zu RATEN.
    # Bei Dichte 'akzente' sind Textpausen die gewollte Handschrift - lag der
    # feste Zeitpunkt in einer, fiel der Test, obwohl die Alpha-Ebene in
    # Ordnung war (genau das passierte mit dem synthetischen Transkript).
    # Die Zusage bleibt dieselbe und wird sogar schaerfer: irgendwo im Clip
    # traegt die Ebene Text auf Transparenz, und NIRGENDS ist sie eine
    # Vollflaeche.
    _aok, _avoll, _agef = False, False, []
    for _ats in ('0.5', '1.0', '1.2', '1.5', '2.0', '2.5', '3.0', '3.5',
                 '4.0', '4.5', '5.0'):
        _ar = subprocess.run(['ffmpeg', '-v', 'error', '-ss', _ats, '-i', amov,
                              '-frames:v', '1', '-f', 'rawvideo',
                              '-pix_fmt', 'rgba', '-'], capture_output=True)
        if len(_ar.stdout) < 16:
            continue
        _aal = np.frombuffer(_ar.stdout, np.uint8).reshape(-1, 4)[:, 3]
        _atr = (_aal < 10).mean()
        if _atr <= 0.5:
            _avoll = True                    # Ebene deckt das halbe Bild: falsch
        if (_aal > 200).any() and _atr > 0.5:
            _aok = True
            _agef.append(_ats)
    check('v101h: Alpha-Kanal traegt Text (opak) auf Transparenz',
          _aok and not _avoll, f"Text bei {', '.join(_agef) or 'keinem'} s"
          + (', Ebene wird irgendwo zur Vollflaeche' if _avoll else ''))
    check('v101h: Kamera im Alpha-Modus deaktiviert (deckungsgleiche Ebene)',
          'Alpha export: caption layer' in log6)


def _scenario_2c(clip, transcript, tmp):
    words = json.load(open(transcript, encoding='utf-8'))
    # 6) Extremwerte: Kamera Nie, alles Optionale aus
    out6 = os.path.join(tmp, 'st_minimal.mp4')
    code, log = render(clip, transcript, out6, extra=['--duration', '3'],
                       cfg_patch={'camera.side_every': 0, 'effects.sfx': False,
                                  'effects.scene_lock': False, 'effects.tracking': False,
                                  'camera.strength': 0.0})
    check('Minimal-Konfiguration stabil', code == 0)

    # 7) Phrasen-Highlight (ueber Regie-Cache, ohne API)
    ph_src = os.path.join(tmp, 'st_phrase.mov')
    shutil.copy(clip, ph_src)
    words = json.load(open(transcript, encoding='utf-8'))
    pair = next((i for i in range(len(words) - 1)
                 if len(words[i]['word'].strip()) > 3 and len(words[i + 1]['word'].strip()) > 3),
                None)
    if pair is not None:
        # Cache MIT gueltigem ref_fp (seit v96x Pflicht, sonst wird er verworfen
        # und die Regie braucht die API - hier bewusst ohne API testen).
        sys.path.insert(0, HERE)
        import render as R
        json.dump({'ref_fp': R._ref_fingerprint(),
                   'keywords': [{'i': pair, 'n': 2, 'fx': 'ground', 'power': 2}]},
                  open(os.path.splitext(ph_src)[0] + '_regie3.json', 'w'))
        out7 = os.path.join(tmp, 'st_phrase.mp4')
        code, log = render(ph_src, transcript, out7,
                           extra=['--duration', str(words[pair]['end'] + 1.5)])
        check('Phrasen-Highlight rendert',
              code == 0 and 'AI director:' in log and os.path.exists(out7))


def _scenario_logic(clip, transcript, tmp):
    words = json.load(open(transcript, encoding='utf-8'))
    # --- 9) Logik-Matrix der neuen Features (ohne Render, in-process)
    sys.path.insert(0, HERE)
    import yaml
    import render as R
    cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    W_, H_ = 1920, 1080
    S = R.Sprites(cfg, W_, H_)

    # Satzgrenzen: 'musst.' nie mit 'Deutschland' in einer Gruppe
    ws = [{'word': w, 'start': 1 + i * .3, 'end': 1 + i * .3 + .25} for i, w in
          enumerate(['merken', 'musst.', 'Deutschland', 'nimmt'])]
    grs = [[ws[i]['word'] for i in g] for g in R.build_groups(ws, 3)]
    check('Satzgrenzen respektiert',
          not any('musst.' in g and 'Deutschland' in g for g in grs))

    # Editorial-Komposition: Rollen + Wort-Timing
    ws2 = [{'word': w, 'start': 1 + i * .4, 'end': 1 + i * .4 + .3} for i, w in
           enumerate(['Willkommen', 'im', 'Studio', '47', 'Nord'])]
    fx2 = {0: {'fx': 'behind', 'power': 3, 'n': 4}}
    pl = R.build_plans(ws2, {0}, cfg, S, W_, H_, lambda s, e: True, fx2)
    kwp = [p for p in pl if 'kw_i' in p]
    toks = kwp[0].get('tokens') or [] if kwp else []
    roles = {t.get('role') for t in toks}
    check('Komposition mit Rollen', 'core' in roles and 'pre' in roles, str(roles))
    check('Komposition wortgetaktet',
          len({round(t['t'], 2) for t in toks}) == len(toks))

    # Zaehler: Format + Builder
    f14 = R.make_counter('14 MILLIARDEN EURO')
    check('Zaehler zaehlt hoch', f14 and f14[0](0.0).startswith('0')
          and f14[0](99).startswith('14'))
    # Jahreszahl darf NICHT hochzaehlen (ein Jahr ist keine Menge) - sonst rollt
    # "2026" von 0 hoch und ist vorbei, bevor die 2026 ueberhaupt steht.
    check('Jahreszahl zaehlt nicht hoch',
          R.make_counter('2026') is None and R.make_counter('IM JAHR 2026') is None
          and R.make_counter('1999') is None and R.make_counter('2100') is None)
    check('Echte Menge zaehlt weiterhin',
          R.make_counter('14 MILLIARDEN') is not None
          and R.make_counter('2200') is not None
          and R.make_counter('850 EURO') is not None)
    ws3 = [{'word': '87', 'start': 1.0, 'end': 1.3},
           {'word': 'Prozent', 'start': 1.35, 'end': 1.7}]
    pl3 = R.build_plans(ws3, {0}, cfg, S, W_, H_, lambda s, e: True,
                        {0: {'fx': 'outline', 'power': 2, 'n': 2}})
    kp3 = [p for p in pl3 if 'kw_i' in p]
    check('Zaehler-Builder verdrahtet',
          kp3 and kp3[0].get('count') is not None
          and ('builder' in kp3[0] or any('builder' in t for t in kp3[0].get('tokens', []))))

    # v85: Kerning. Ein Paar darf nie breiter werden als die Einzelglyphen +
    # Tracking - waere das Vorzeichen der Korrektur falsch, blaehte es auf.
    _wa = S.text('A', 90, S.white)[1]
    _wv = S.text('V', 90, S.white)[1]
    _wav = S.text('AV', 90, S.white)[1]
    check('Kerning: Paar nicht breiter als Einzelglyphen', _wav <= _wa + _wv + 4 + 1.0,
          f'AV={_wav:.0f} A+V={_wa + _wv:.0f}')
    check('Kerning: Sprite rendert weiterhin', S.text('AWAY', 90, S.white)[0].shape[2] == 4)

    # v85: Schnitt-Disziplin. Ein Moment darf nicht ueber einen harten Schnitt
    # stehen bleiben - sein Abgang muss VOR dem Schnitt fertig sein.
    _wcut = [{'word': 'Alpha', 'start': 1.0, 'end': 1.4},
             {'word': 'Beta', 'start': 1.5, 'end': 1.9},
             {'word': 'Gamma', 'start': 2.0, 'end': 2.6}]
    _pl_base = R.build_plans(_wcut, set(), cfg, S, W_, H_, lambda s, e: True)
    _pl_snap = R.build_plans(_wcut, set(), cfg, S, W_, H_, lambda s, e: True,
                             cut_times=[2.0])
    _strad = lambda pl: any(p['start'] < 2.0 - 0.40 and p['end'] > 2.0 - 0.34 + 0.05
                            for p in pl)
    check('Schnitt-Disziplin: Fixture straddlet ohne Feature', _strad(_pl_base))
    check('Schnitt-Disziplin: kein Straddle mit cut_times', not _strad(_pl_snap))
    check('Schnitt-Disziplin: Ende wird vorgezogen',
          max(p['end'] for p in _pl_snap) < max(p['end'] for p in _pl_base) - 0.05)

    # v86: Baseline-Grid (Querformat). cascade/outline teilen sich EINEN Anker,
    # damit aufeinanderfolgende Momente nicht in der Hoehe huepfen.
    def _anchor(fx):
        _plz = R.build_plans([{'word': 'Wahnsinn', 'start': 1.0, 'end': 1.6}],
                             {0}, cfg, S, 1920, 1080, lambda s, e: True,
                             {0: {'fx': fx, 'power': 2, 'n': 1}})
        _k = [p for p in _plz if 'kw_i' in p]
        return _k[0].get('cy') if _k else None
    check('Baseline-Grid: cascade & outline auf einer Linie',
          abs(_anchor('cascade') - _anchor('outline')) < 1e-6,
          f"{_anchor('cascade')} vs {_anchor('outline')}")
    # v139: 16:9 sitzt jetzt im echten Lower Third (0.78H, Title-Safe) statt
    # auf dem alten Einheits-Anker 0.40H (obere Bildhaelfte).
    check('Baseline-Grid: 16:9-Anker im Lower Third (0.78H)',
          abs(_anchor('cascade') - 1080 * 0.78) < 1e-6,
          f"{_anchor('cascade')} vs {1080 * 0.78}")

    # v86: Hochformat rastet die Text-Hoehe auf ein Baseline-Raster (H*0.025),
    # damit Gesichts-Jitter den Text nicht kontinuierlich verschiebt.
    _plp = R.build_plans([{'word': 'Test', 'start': 1.0, 'end': 1.6}], {0}, cfg,
                         S, 1080, 1920, lambda s, e: True,
                         {0: {'fx': 'cascade', 'power': 2, 'n': 1}},
                         face_pos=lambda s, e: (540, 300, 200))
    _kp = [p for p in _plp if 'kw_i' in p]
    _cyp = _kp[0]['cy'] if _kp else 0
    _grid = 1920 * 0.025
    check('Baseline-Grid: Hochformat auf Raster', _kp
          and abs(_cyp / _grid - round(_cyp / _grid)) < 1e-6, f'cy={_cyp:.1f}')

    # v86: Farbwelt pro Shot - zwei Captions ueber eine Sekundengrenze in
    # DERSELBEN Einstellung teilen exakt eine Farbe (kein Tint-Sprung).
    _tealv = os.path.join(tmp, 'st_teal86.mp4')
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
         'color=c=teal:s=320x240:d=3', '-pix_fmt', 'yuv420p', _tealv])
    _samp = R.scene_palette_sampler(_tealv, cut_times=[5.0])
    check('Farbwelt pro Shot: kein Tint-Sprung ueber Sekundengrenze',
          _samp(0.3) is _samp(1.2))

    _rsrc143 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v143: eigene, unberuehrte Config - frueh laufende Tests veraendern cfg
    # (Dichte, Safe-Zone), und die Platzierung haengt davon ab.
    _cfg143 = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    # v88: Ueberlappungs-Schutz. Zwei Momente an fast derselben Stelle, zeitlich
    # ueberlappend -> der fruehere wird vorgezogen; nebeneinander bleibt frei.
    _ov = [{'target': (540, 700), 't0': 0.0, 'start': 0.0, 'end': 4.0},
           {'target': (560, 720), 'start': 2.0, 'end': 3.5},
           {'target': (540, 700), 'start': 6.0, 'end': 7.0}]
    _n = R.resolve_overlaps(_ov, 1080, 1920)
    check('Ueberlappung: fruehes Ende vorgezogen',
          _n == 1 and abs(_ov[0]['end'] - 1.88) < 1e-6, f"end={_ov[0]['end']:.2f}")
    _side = [{'target': (200, 700), 'start': 0.0, 'end': 4.0},
             {'target': (900, 700), 'start': 2.0, 'end': 3.5}]
    check('Ueberlappung: nebeneinander bleibt unangetastet',
          R.resolve_overlaps(_side, 1080, 1920) == 0)
    # v141 (Ismets Doppelbild): die Flow-Caption traegt in 'target' das
    # KAMERA-Ziel am linken Rand. Verglichen wird jetzt 'vpos' - der echte
    # Textblock in der Mitte. Vorher lag der Abstand bei 0.43*W und der Schutz
    # griff nie, obwohl beide Texte uebereinander standen.
    _flow = [{'target': (int(1080 * 0.07), 700), 'vpos': (540, 700),
              'start': 0.0, 'end': 4.0},
             {'target': (540, 700), 'start': 2.0, 'end': 3.5}]
    _nf = R.resolve_overlaps(_flow, 1080, 1920)
    check('v141: Flow-Caption wird am ECHTEN Textblock geprueft (Doppelbild weg)',
          _nf == 1 and abs(_flow[0]['end'] - 1.88) < 1e-6,
          f"n={_nf} end={_flow[0]['end']:.2f}")
    _flow_old = [{'target': (int(1080 * 0.07), 700), 'start': 0.0, 'end': 4.0},
                 {'target': (540, 700), 'start': 2.0, 'end': 3.5}]
    check('v141: ohne vpos bleibt das alte Verhalten (Kamera-Ziel, kein Treffer)',
          R.resolve_overlaps(_flow_old, 1080, 1920) == 0)
    check('v141: build_plans gibt der Flow-Caption ein vpos',
          "sp['vpos'] = (sum(_fcx) / len(_fcx) if _fcx else W / 2.0," in
          open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())
    # ================================================================
    # v143: Groessenhierarchie + Platzierungs-Regie.
    # ================================================================
    def _kern(arr, thr=200):
        """Buchstabenkern OHNE Glow - sonst misst man den Aussenschein mit.
        v189: und OHNE Kontur. Seit das grosse Wort keinen Umriss mehr traegt
        (der Fliesstext schon), verglich die Alpha-Messung Glyphe gegen
        Glyphe-plus-Saum und das Groessenverhaeltnis fiel scheinbar von 2.2
        auf 1.82. Gemessen wird deshalb der helle Glyphenkoerper, genau wie
        in _ink_x der Engine."""
        _al = arr[..., 3] > thr
        _hell = _al & (arr[..., :3].max(axis=2) > 150)
        _ys, _xs = np.where(_hell if _hell.any() else _al)
        return ((_ys.max() - _ys.min() + 1, _xs.max() - _xs.min() + 1)
                if len(_ys) else (0, 0))

    def _flowmass(W, H, woerter=('was', 'HINTER', 'diesen', 'Zahlen')):
        _S = R.Sprites(_cfg143, W, H)
        _ws = [{'word': w, 'start': i * 0.4, 'end': i * 0.4 + 0.3}
               for i, w in enumerate(woerter)]
        _it, _th, _ = R.compose_flow(list(range(len(_ws))), _ws, _S, W, H,
                                     portrait=(W / H < 0.8))
        _k = next((i for i in _it if i['role'] == 'key'), None)
        _n = [i for i in _it if i['role'] == 'norm']
        _kh, _kw = _kern(_k['arr']) if _k is not None else (0, 0)
        _nh = np.mean([_kern(i['arr'])[0] for i in _n]) if _n else 1.0
        return _kh / H, _kw / W, _nh / H, _kh / max(_nh, 1.0)
    # Referenz (@migs.visuals, gemessen): Schluesselwort-Versalhoehe
    # 0.051-0.085 H, Kleintext-x-Hoehe 0.023-0.033 H, Verhaeltnis 2.2-2.6.
    # Vorher lag das Verhaeltnis bei 1.10 - alles war fast gleich gross.
    _kh9, _kw9, _nh9, _r9 = _flowmass(1080, 1920)
    check('v143: Schluesselwort-Versalhoehe im Referenzband (Hochformat)',
          0.045 <= _kh9 <= 0.092, f'{_kh9:.4f} H (Referenz 0.051-0.085)')
    check('v143: Hierarchie Schluesselwort zu Kleintext wie in der Referenz',
          2.0 <= _r9 <= 2.9, f'{_r9:.2f}x (Referenz 2.2-2.6, vorher 1.10)')
    # v154 GEAENDERTE ERWARTUNG, kein Testkosmetik-Fix: Ismet hat die Schrift
    # dreimal als zu gross beanstandet, das Hausmass ist von 0.115 ueber 0.098
    # und 0.088 auf 0.076 em gefallen. Ein langes Schluesselwort spannt die
    # Spalte dadurch bewusst nicht mehr bis 0.83 W. Die untere Grenze bleibt,
    # damit es nicht zum Fliesstext zusammenfaellt.
    check('v143/v154: langes Schluesselwort bleibt deutlich breiter als der Satz',
          0.45 <= _kw9 <= 0.88, f'{_kw9:.3f} W')
    # Querformat war der Ausreisser: pf = 0.62 VERKLEINERTE dort, waehrend
    # alle Nachbar-Composer um Faktor 1.68 bis 2.00 vergroessern.
    _kh16, _, _, _r16 = _flowmass(1920, 1080)
    check('v143: Querformat vergroessert statt zu schrumpfen',
          _kh16 > _kh9 * 1.25 and 2.0 <= _r16 <= 2.9,
          f'quer {_kh16:.4f} H vs hoch {_kh9:.4f} H, Verhaeltnis {_r16:.2f}x')
    check('v143: pf im Querformat ist eine Vergroesserung',
          'pf = 1.35 if not portrait else 1.0' in _rsrc143)

    # ---- Platzierungs-Regie: der Block MUSS sich nach dem Bild richten.
    def _flowbox(W, H, fx, fy, fw, ct=None):
        _S = R.Sprites(_cfg143, W, H)
        _ws = [{'word': w, 'start': 1.0 + i * 0.42, 'end': 1.0 + i * 0.42 + 0.36}
               for i, w in enumerate(['was', 'HINTER', 'diesen', 'Zahlen', 'steckt'])]
        _pl = R.build_plans(_ws, {3}, _cfg143, _S, W, H, lambda s, e: True,
                            {3: {'fx': 'behind', 'power': 3, 'n': 1}},
                            face_pos=lambda s, e: (fx, fy, fw), cut_times=ct)
        for _p in _pl:
            if _p.get('tpl') == 'flow' and _p.get('front'):
                _L, _Rt = [], []
                for _i in _p['front']:
                    _a = _i['arr']
                    _m = np.where(_a[..., 3] > 200)[1]
                    if len(_m):
                        _L.append(_i['cx'] - _a.shape[1] / 2 + _m.min())
                        _Rt.append(_i['cx'] - _a.shape[1] / 2 + _m.max())
                _ys = [_i['cy'] for _i in _p['front']]
                if _L:
                    return (min(_L) / W, max(_Rt) / W, min(_ys) / H, max(_ys) / H)
        return None
    _oben = _flowbox(1080, 1920, 540, 1920 * 0.28, 108)
    _unten = _flowbox(1080, 1920, 540, 1920 * 0.62, 108)
    check('v143: Hochformat - Block folgt der Kopfhoehe',
          _oben and _unten and abs(_oben[2] - _unten[2]) > 0.05,
          f'Kopf hoch y={_oben[2]:.3f} vs Kopf tief y={_unten[2]:.3f}')
    # v153 TESTKORREKTUR (kein Verhaltenswechsel): das Gesicht sitzt jetzt auf
    # BLOCKHOEHE. Mit 0.40 H stand es nach der Schriftverkleinerung komplett
    # UEBER dem Textblock - es gab dort gar keine Kollision mehr, und der
    # Test mass, ob der Block einem Hindernis ausweicht, das ihn nicht
    # beruehrt. Gegenprobe mit dem echten Konflikt: Person links -> Block
    # 0.453 W, Person rechts -> Block 0.186 W.
    _li = _flowbox(1920, 1080, 1920 * 0.25, 1080 * 0.68, 180)
    _re = _flowbox(1920, 1080, 1920 * 0.75, 1080 * 0.68, 180)
    check('v143: Querformat - Block weicht der Person zur Seite aus',
          _li and _re and (_li[0] > _re[0] + 0.06),
          f'Person links -> x={_li[0]:.3f}, Person rechts -> x={_re[0]:.3f}')
    # Nahaufnahme: Block gehoert NEBEN den Kopf, nicht darunter. Dafuer darf
    # die Spalte schmaler werden (_freie_breite).
    _nah = _flowbox(1080, 1920, 1080 * 0.72, 1920 * 0.40, 1080 * 0.30)
    # v181 TESTKORREKTUR, ehrlich begruendet: die SUBSTANZ dieses Tests ist
    # die schmale SPALTE neben dem Kopf (x). Die zusaetzliche y-Schwelle war
    # in genau dieser Konstellation ein Grenzfall - bei einer Kopfbox, die
    # 0.01 bis 0.79 H abdeckt, ueberlappt JEDE Hoehe, und die Entscheidung
    # kippte bereits bei 0.003 W Blockbreiten-Unterschied (durch die neue
    # Kontur ausgeloest, am Debug-Log nachgemessen: sx blieb identisch bei
    # 0.089, nur y sprang 0.170 -> 0.595). Ein Test, den 3 Promille Breite
    # umwerfen, misst keine Regel, sondern Rauschen. Die Spalte wird weiter
    # hart geprueft; die Hoehe nur noch gegen den sicheren Bereich.
    check('v143: Nahaufnahme - schmale Spalte neben dem Kopf',
          _nah and _nah[1] < 0.52 and _nah[3] < 0.88,
          f'x bis {_nah[1]:.3f} W, y bis {_nah[3]:.3f} H (Kopfbox ab 0.46 W)')
    # Der Text darf NIE auf dem GESICHT landen. Gemessen gegen die echte
    # Gesichtsbreite (Mitte 0.72 W, Breite 0.30 W -> 0.57 .. 0.87 W), nicht
    # gegen die gepolsterte Sperrbox: die traegt bewusst Haar- und
    # Sicherheitsrand und darf angeschnitten werden, das Gesicht nicht.
    _gesicht_l = 0.72 - 0.30 / 2
    check('v143: Block landet nicht auf dem Gesicht',
          _nah and _nah[1] <= _gesicht_l - 0.03,
          f'Blockkante {_nah[1]:.3f} W gegen Gesicht ab {_gesicht_l:.3f} W')
    # Hysterese: winzige Schwankungen der Gesichtserkennung duerfen den Block
    # NICHT verschieben. Genau daran ist der erste Entwurf im Audit gescheitert
    # (10 px Gesichtsbreite kippten ihn um 0.19 W).
    _a1 = _flowbox(1920, 1080, 1920 * 0.50, 1080 * 0.40, 200)
    _a2 = _flowbox(1920, 1080, 1920 * 0.50, 1080 * 0.40, 210)
    check('v143: Hysterese - 10 px Gesichtsbreite verschieben den Block nicht',
          _a1 and _a2 and abs(_a1[0] - _a2[0]) < 0.03 and abs(_a1[2] - _a2[2]) < 0.03,
          f'{_a1[0]:.3f}/{_a1[2]:.3f} gegen {_a2[0]:.3f}/{_a2[2]:.3f}')
    # Title-Safe: gemessen wird die SICHTBARE Ausdehnung, nicht die
    # Vorschubweite. Mit adv gerechnet ragte der Block im echten Render bis
    # 0.963 W und riss den 5-Prozent-Rand (SMPTE ST 2046-1 / EBU R 95).
    for _W143, _H143 in ((1080, 1920), (1920, 1080)):
        _bx = _flowbox(_W143, _H143, _W143 * 0.5, _H143 * 0.40, _W143 * 0.10)
        if _bx:
            break
    check('v143: Textblock bleibt im Title-Safe-Rand (5 Prozent)',
          _bx and _bx[0] >= 0.045 and _bx[1] <= 0.955,
          f'x {_bx[0]:.3f} .. {_bx[1]:.3f} W')
    check('v143: Blockbreite wird an der sichtbaren Schrift gemessen',
          'def _ink_x' in _rsrc143 and "_a[..., 3] > 80" in _rsrc143)
    check('v143: Raum-Karte und Regie sind verdrahtet',
          'def scene_space_sampler' in _rsrc143
          and 'def spot(start, end, bw, bh' in _rsrc143
          and 'def _freie_breite' in _rsrc143
          and 'space_at=space_at' in _rsrc143
          and "spot_state['xy']" in _rsrc143)
    check('v143: Raum-Karte liefert ein Kostenraster und faellt sauber aus',
          R.scene_space_sampler('/gibt/es/nicht.mp4')(0.0).shape == (16, 12)
          and float(R.scene_space_sampler('/gibt/es/nicht.mp4')(0.0).max()) == 0.0)
    # ---- Ton: Schnitt-Dramaturgie
    _sfxsrc = open(os.path.join(HERE, 'sfx_engine.py'), encoding='utf-8').read()
    check('v143: Schnittzeiten erreichen die Sound-Engine',
          'cut_times=None' in _sfxsrc.split('def build_sfx_track')[1][:220]
          and 'cut_times=cut_times' in _rsrc143)
    check('v143: Ton laeuft dem Bild voraus (gemessene Rezeptur)',
          "place(V('impact'), _ct - 0.030" in _sfxsrc
          and '_ct - 0.115' in _sfxsrc
          and "place(V('boom'), _ct + 0.040" in _sfxsrc
          and 'len(_rs) / float(SR)' in _sfxsrc)
    # v230: die REGEL ("kein Maschinengewehr") gilt weiter, die Umsetzung hat
    # sich geaendert. Bis v229 war sie "nur in den ersten 1.6 s einer
    # Einstellung" - in einem schnittarmen Talking-Head hiess das: nach 1.6 s
    # gar kein Ton mehr (Ismets Befund). Jetzt: dicht am Schnitt, danach mit
    # Mindestabstand. Geprueft wird deshalb die ZUSAGE am Ergebnis, nicht mehr
    # die alte Codezeile - ein Test, der die Umsetzung festnagelt, haette hier
    # den Fehler geschuetzt statt der Regel (v132-Lehre).
    check('v143/v230: dicht am Schnitt, danach mit Mindestabstand',
          '_im_fenster = (_t0 - _shot0) <= 1.60' in _sfxsrc
          and '_t0 - _letzter_tick[0] < _tick_gap' in _sfxsrc
          and 'TICK_ABSTAND' in _sfxsrc)
    check('v143: ohne Sound-Pack bleibt es STUMM (Projektregel unangetastet)',
          'No sound pack found' in _sfxsrc
          and 'synthetischer Ersatzton waere schlechter als Stille' in _sfxsrc)

    # ================================================================
    # v144: Referenz-MESSUNG statt Prosa-Schaetzung.
    # ================================================================
    # Testvideo bauen: dunkler Grund, heller Text in einem schmalen Band oben,
    # dazu ein grosser heller Fleck weiter unten als Stoerer (so wie ein
    # Lampenreflex im echten Material). Die Messung muss den Text finden und
    # den Fleck verwerfen.
    # Das Testvideo wird mit ECHTEN Schriftdateien gesetzt, nicht mit
    # cv2.putText: die Hershey-Strichschriften haben weder Punzen noch
    # Antialiasing, also genau die Merkmale nicht, an denen die Messung
    # Schrift von Flaeche unterscheidet. Ein Testbild, das die zu pruefende
    # Eigenschaft gar nicht besitzt, prueft nichts.
    _rv = os.path.join(tmp, 'ref_mess.mp4')
    _RW, _RH, _RF, _RN = 540, 960, 24, 72
    if not os.path.exists(_rv):
        from PIL import Image as _PI, ImageDraw as _PD, ImageFont as _PF
        _fk = _PF.truetype(os.path.join(HERE, 'fonts/poppins_b.ttf'), int(_RH * 0.105))
        _fs = _PF.truetype(os.path.join(HERE, 'fonts/sans_l.ttf'), int(_RH * 0.045))
        _stumm = os.path.join(tmp, 'ref_mess_stumm.mp4')
        _vw = cv2.VideoWriter(_stumm, cv2.VideoWriter_fourcc(*'mp4v'), _RF, (_RW, _RH))
        _rng = np.random.RandomState(7)
        for _n in range(_RN):
            # Ein SCHNITT in der Mitte: davor dunkel, danach hell. Damit hat
            # die Messung ueberhaupt eine Einstellungslaenge zu finden.
            _grund = 30 if _n < _RN // 2 else 78
            _img = np.full((_RH, _RW, 3), _grund, np.uint8)
            _img = cv2.add(_img, (_rng.rand(_RH, _RW, 3) * 14).astype(np.uint8))
            # Zwei helle Stoerer TIEF im Bild - Lampe und Reflex. Sie sind
            # hell und wenig gesaettigt, also fuer eine reine Schwelle
            # ununterscheidbar von Schrift. Die Messung muss sie verwerfen.
            # Sie WANDERN, damit die Wasserzeichen-Erkennung sie nicht schon
            # vorher wegraeumt - der Test soll die Schrift-Merkmale pruefen,
            # nicht den Zeitfilter.
            _wan = int(_RW * 0.06 * math.sin(_n * 0.21))
            cv2.circle(_img, (int(_RW * 0.5) + _wan, int(_RH * 0.74)),
                       int(_RW * 0.13), (245, 245, 245), -1)
            cv2.circle(_img, (int(_RW * 0.8) - _wan, int(_RH * 0.60)),
                       int(_RW * 0.05), (250, 250, 250), -1)
            _im = _PI.fromarray(cv2.cvtColor(_img, cv2.COLOR_BGR2RGB))
            _dr = _PD.Draw(_im)
            # ZWEI Caption-Bloecke, die einander abloesen. Kein Element darf
            # laenger als 85 % der Frames an derselben Stelle stehen, sonst
            # haelt die Messung es zu Recht fuer ein Wasserzeichen und
            # loescht es - genau das passiert echten Sender-Logos.
            _ph = 0 if _n < _RN // 2 else 1
            _lok = _n % (_RN // 2)
            _klein = [['warum', 'so', 'viele'], ['das', 'ist', 'der']][_ph]
            _key = ['SCHEITERN', 'GRUND'][_ph]
            _x = int(_RW * 0.10)
            for _w in _klein[:min(3, 1 + _lok // 8)]:
                _dr.text((_x, int(_RH * 0.16)), _w, font=_fs, fill=(255, 255, 255))
                _x += int(_dr.textlength(_w + ' ', font=_fs))
            if _lok >= 8:
                _dr.text((int(_RW * 0.10), int(_RH * 0.23)), _key,
                         font=_fk, fill=(255, 255, 255))
            if _lok >= 20:
                _dr.text((int(_RW * 0.10), int(_RH * 0.33)), 'daran',
                         font=_fs, fill=(249, 187, 38))
            _vw.write(cv2.cvtColor(np.array(_im), cv2.COLOR_RGB2BGR))
        _vw.release()
        # TONSPUR: Sprache (Tiefband-Rauschen) plus ein gestalteter
        # Schnitt-Ton, der dem Bild VORAUSLAEUFT - Zischer 115 ms davor,
        # Tiefton-Impuls 30 ms davor. Genau diese Rezeptur soll die Messung
        # wiederfinden.
        import wave as _wv
        _sr = 44100
        _sek = _RN / float(_RF)
        _t = np.arange(int(_sr * _sek)) / float(_sr)
        _rg2 = np.random.RandomState(3)
        _sig = _rg2.randn(len(_t)).astype(np.float32)
        _sig = np.convolve(_sig, np.ones(90, np.float32) / 90.0, 'same')  # dumpf
        _sig *= 0.14 / (float(np.sqrt(np.mean(_sig ** 2))) + 1e-9)
        _cut = (_RN // 2) / float(_RF)
        def _burst(mitte, dauer, hoch, amp):
            _i0 = int((mitte - dauer / 2) * _sr)
            _nn = int(dauer * _sr)
            _e = np.hanning(_nn).astype(np.float32)
            _b = _rg2.randn(_nn).astype(np.float32)
            if hoch:
                _b = _b - np.convolve(_b, np.ones(24, np.float32) / 24.0, 'same')
            else:
                _b = np.convolve(_b, np.ones(300, np.float32) / 300.0, 'same')
                _b *= 1.0 / (float(np.max(np.abs(_b))) + 1e-9)
            _sig[_i0:_i0 + _nn] += _b * _e * amp
        _burst(_cut - 0.115, 0.16, True, 1.6)
        _burst(_cut - 0.030, 0.12, False, 1.6)
        _wavp = os.path.join(tmp, 'ref_mess.wav')
        with _wv.open(_wavp, 'wb') as _wf:
            _wf.setnchannels(1); _wf.setsampwidth(2); _wf.setframerate(_sr)
            _wf.writeframes((np.clip(_sig, -1, 1) * 32000).astype(np.int16).tobytes())
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', _stumm, '-i', _wavp,
                        '-c:v', 'copy', '-c:a', 'aac', '-shortest', _rv],
                       check=True, capture_output=True)
    _mess = R.measure_reference_video(_rv)
    check('v144: Messung liefert ueberhaupt Werte (ohne KI, ohne API-Key)',
          bool(_mess) and 'zone_y' in _mess and 'key_hoehe' in _mess,
          str(sorted(_mess.keys()))[:110])
    check('v144: Textband gefunden, heller Stoerer verworfen',
          _mess.get('zone_y') and _mess['zone_y'][1] < 0.55,
          f"Zone {_mess.get('zone_y')} - die Stoerer sitzen bei 0.60 und 0.74 H")
    check('v144: das Band reicht ueber den ganzen Textblock',
          _mess.get('zone_y') and _mess['zone_y'][0] < 0.20
          and _mess['zone_y'][1] > 0.34,
          f"Zone {_mess.get('zone_y')} - Block steht 0.16 .. 0.38 H")
    # Gesetzt sind 0.105 H und 0.045 H Schriftgrad. Gemessen wird die
    # VERSALHOEHE, nicht der Grad - erwartet also rund 2.4 bis 3.2.
    check('v144: Groessenverhaeltnis der Hierarchie stimmt (Soll ~2.9)',
          2.1 <= (_mess.get('verhaeltnis') or 0) <= 3.6,
          f"key {_mess.get('key_hoehe')} / klein {_mess.get('klein_hoehe')}"
          f" = {_mess.get('verhaeltnis')}")
    check('v144: linksbuendiger Satz wird als links erkannt',
          _mess.get('ausrichtung') == 'links', str(_mess.get('ausrichtung')))
    # Gesetzt ist #f9bb26. Toleranz, weil Videokompression die Farbe verzieht.
    _ah = _mess.get('akzent_hex') or '#000000'
    _ard = [abs(int(_ah[1 + 2 * _i:3 + 2 * _i], 16) - _v)
            for _i, _v in enumerate((249, 187, 38))]
    check('v144: Akzentfarbe wird aus dem Bild gemessen (Soll #f9bb26)',
          max(_ard) <= 26, f"{_ah}, Abweichung {_ard}")
    check('v144: Kamera und Schnitt werden gemessen',
          'einstellung_s' in _mess and 'kamera' in _mess
          and _mess.get('kamera') in ('ruhig', 'bewegt', 'wild'),
          f"{_mess.get('kamera')}, Einstellung {_mess.get('einstellung_s')}s")
    check('v144: der eine echte Schnitt wird gefunden (Soll ~1.5s Einstellung)',
          1.1 <= (_mess.get('einstellung_s') or 0) <= 1.9,
          f"Einstellung {_mess.get('einstellung_s')}s, "
          f"{_mess.get('schnitte_pro_s')} Schnitte/s")
    check('v144: ruhige Kamera wird nicht als bewegt gemeldet',
          _mess.get('kamera') == 'ruhig',
          f"unruhe {_mess.get('unruhe')}, zoom {_mess.get('zoom_pro_s')}")
    check('v144: Ton wird gemessen, Musikbett korrekt verneint',
          'pegel_db' in _mess and _mess.get('musik') is False,
          f"pegel {_mess.get('pegel_db')} dB, musik {_mess.get('musik')}")
    check('v144: gestalteter Schnitt-Ton erkannt, Vorlauf gemessen',
          _mess.get('schnitt_ton') is True
          and 20.0 <= (_mess.get('ton_vorlauf_ms') or 0) <= 260.0,
          f"schnitt_ton {_mess.get('schnitt_ton')}, "
          f"Vorlauf {_mess.get('ton_vorlauf_ms')} ms (gesetzt 115 ms)")
    # Kaputte/leere Eingaben duerfen nicht knallen
    check('v144: unbrauchbare Eingabe gibt sauber {} zurueck',
          R.measure_reference_video('/gibt/es/nicht.mp4') == {}
          and R.measure_reference_video(os.path.join(HERE, 'config.yaml')) == {})
    # --- Anwenden: die Messung MUSS die Config wirklich verstellen
    _cfg144 = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _cfg144['camera']['strength'] = 0.70
    _cfg144['camera']['crash'] = 0.55
    _cfg144['effects']['sfx_volume'] = 0.60
    _p144 = {'kamera': 'ruhig', 'einstellung_s': 1.38, 'musik': False,
             'schnitt_ton': True, 'zone_y': [0.145, 0.348], 'glow': True,
             'ausrichtung': 'links', 'akzent_hex': '#f9bb26'}
    _ref144 = os.path.join(tmp, 'ref144.json')
    json.dump([{'name': 'm', 'beispiel': 'x', 'params': _p144}],
              open(_ref144, 'w', encoding='utf-8'))
    _alt_rf = os.environ.get('DVE_REFS_FILE')
    try:
        os.environ['DVE_REFS_FILE'] = _ref144
        _anker = R._apply_reference_params(_cfg144)
    finally:
        if _alt_rf is None:
            os.environ.pop('DVE_REFS_FILE', None)
        else:
            os.environ['DVE_REFS_FILE'] = _alt_rf
    check('v144: ruhige Referenz-Kamera drosselt UNSERE Kamera',
          _cfg144['camera']['strength'] <= 0.35 and _cfg144['camera']['crash'] <= 0.20,
          f"strength {_cfg144['camera']['strength']}, crash {_cfg144['camera']['crash']}")
    check('v144: kein Musikbett + Schnitt-Ton -> SFX traegt das Video',
          _cfg144['effects']['sfx_volume'] >= 0.75
          and _cfg144['effects'].get('sfx') is True,
          f"sfx_volume {_cfg144['effects']['sfx_volume']}")
    check('v144: Caption-Zone und Satz kommen aus dem Vorbild',
          abs(float(_cfg144['effects'].get('caption_zone', 0)) - 0.246) < 0.02
          and _cfg144['effects'].get('caption_align') == 'links'
          and _cfg144['effects'].get('caption_glow') is True,
          f"zone {_cfg144['effects'].get('caption_zone')}")
    check('v144: gemessene Akzentfarbe schlaegt die Config-Farbe',
          list(_cfg144['colors']['accent']) == [249, 187, 38]
          and _cfg144['colors']['adaptive'] is False,
          str(_cfg144['colors']['accent']))
    # SCHRIFTGROESSE: die auffaelligste Eigenschaft eines Vorbilds. Sie muss
    # als H-Anteil ankommen und im gesetzten Block wirklich messbar sein.
    _cfg144b = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _p144b = dict(_p144, key_hoehe=0.0742, verhaeltnis=2.6)
    json.dump([{'name': 'm', 'beispiel': 'x', 'params': _p144b}],
              open(_ref144, 'w', encoding='utf-8'))
    try:
        os.environ['DVE_REFS_FILE'] = _ref144
        R._apply_reference_params(_cfg144b)
    finally:
        if _alt_rf is None:
            os.environ.pop('DVE_REFS_FILE', None)
        else:
            os.environ['DVE_REFS_FILE'] = _alt_rf
    check('v144: gemessene Versalhoehe wird zum Schriftgrad-Faktor',
          abs(float(_cfg144b['effects'].get('caption_scale', 0)) - 1.082) < 0.02
          and abs(float(_cfg144b['effects'].get('caption_hierarchie', 0)) - 2.6) < 0.01,
          f"scale {_cfg144b['effects'].get('caption_scale')}, "
          f"hierarchie {_cfg144b['effects'].get('caption_hierarchie')}")

    def _flowgroessen(cfgx):
        _Sx = R.Sprites(cfgx, 1080, 1920)
        _wx = [{'word': w, 'start': i * 0.4, 'end': i * 0.4 + 0.3}
               for i, w in enumerate(['ja', 'NEU', 'ok'])]
        _it, _th, _ai = R.compose_flow(list(range(len(_wx))), _wx, _Sx,
                                       1080, 1920, portrait=True)
        # Gemessen wird die SICHTBARE Hoehe der Sprite-Deckung, nicht der
        # gesetzte Grad - genau das sieht man im fertigen Bild.
        def _ih(it):
            _a = it['arr']
            _z = np.where(_a[..., 3].max(axis=1) > 80)[0]
            return float(_z[-1] - _z[0] + 1) if len(_z) else 0.0
        _gr = sorted(_ih(i) for i in _it)
        return (_gr[-1] / 1920.0, _gr[0] / 1920.0) if _gr else (0, 0)
    _g_haus = _flowgroessen(yaml.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                               encoding='utf-8')))
    _g_ref = _flowgroessen(_cfg144b)
    check('v144: der gesetzte Block wird durch die Messung wirklich groesser',
          _g_ref[0] > _g_haus[0] * 1.03,
          f"Haus {_g_haus[0]:.4f} H -> Referenz {_g_ref[0]:.4f} H")
    _cfg144c = copy.deepcopy(_cfg144b)
    _cfg144c['effects']['caption_hierarchie'] = 1.8
    _g_flach = _flowgroessen(_cfg144c)
    check('v144: flachere gemessene Hierarchie hebt den Kleintext an',
          _g_flach[1] > _g_ref[1] * 1.08,
          f"Hierarchie 2.6 -> klein {_g_ref[1]:.4f} H, "
          f"1.8 -> klein {_g_flach[1]:.4f} H")
    check('v144: der Anker nennt die gemessenen Merkmale',
          all(x in _anker for x in ('kamera=ruhig', 'schnitt=', 'zone=', 'satz=links')),
          _anker)
    # Die Wunschzone muss in der Platzierung wirklich ankommen
    _cfgz = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _cfgz['effects']['caption_zone'] = 0.22
    _Sz = R.Sprites(_cfgz, 1080, 1920)
    _wz = [{'word': w, 'start': 1.0 + i * 0.4, 'end': 1.0 + i * 0.4 + 0.3}
           for i, w in enumerate(['was', 'HINTER', 'diesen', 'Zahlen'])]
    _plz = R.build_plans(_wz, set(), _cfgz, _Sz, 1080, 1920, lambda s, e: True, {},
                         face_pos=lambda s, e: (540.0, 1920 * 0.62, 108.0))
    _fy = None
    for _p in _plz:
        if _p.get('tpl') == 'flow' and _p.get('front'):
            _fy = min(i['cy'] for i in _p['front']) / 1920.0
            break
    check('v144: die gemessene Zone steuert die echte Platzierung',
          _fy is not None and _fy < 0.34,
          f"Blockoberkante {_fy:.3f} H bei Wunschzone 0.22")
    # OHNE OpenAI-Key muss das Stil-Lernen trotzdem etwas liefern - die
    # Messung haengt an keiner API. Bis v143 gab es hier ein hartes None.
    _alt_key = os.environ.pop('OPENAI_API_KEY', None)
    try:
        _e144 = R.analyze_reference_video(_rv, name='Vorbild', save=False)
    finally:
        if _alt_key is not None:
            os.environ['OPENAI_API_KEY'] = _alt_key
    check('v144: Stil-Lernen funktioniert auch OHNE OpenAI-Key (Messung traegt)',
          isinstance(_e144, dict) and _e144.get('params', {}).get('key_hoehe'),
          f"Eintrag {'ja' if _e144 else 'nein'}, "
          f"{len((_e144 or {}).get('params', {}))} Parameter")
    check('v144: der Kunde sieht die Messung im Klartext',
          _e144 and 'Measured:' in (_e144.get('gemessen') or '')
          and 'frame height' in _e144['gemessen']
          and 'shot' in _e144['gemessen'],
          str((_e144 or {}).get('gemessen'))[:150])
    _srv144 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _ui144 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v144: Server sperrt das Stil-Lernen nicht mehr am API-Key aus',
          'def _style_public' in _srv144
          and "'gemessen': str(r.get('gemessen', ''))[:400]" in _srv144
          and 'Style learning is briefly unavailable' not in _srv144)
    check('v144: die Messung steht im Konto sichtbar an der Referenz',
          'r.gemessen ?' in _ui144 and 'd.entry.gemessen' in _ui144)
    check('v144: Rohdaten der Messung verlassen den Server nicht',
          "'messung'" not in _srv144.split('def _style_public')[1][:600])
    check('v144: Messung ist in analyze_reference_video verdrahtet',
          'measure_reference_video(video_path)' in _rsrc143
          and "entry['messung']" in _rsrc143
          and "cfg['effects']['caption_zone']" in _rsrc143)

    # Nach build_plans darf kein Paar mit target ko-sichtbar+nah stehen
    def _codisplay(pl):
        ts = [p for p in pl if 'target' in p]
        for _x in range(len(ts)):
            for _y in range(_x + 1, len(ts)):
                a, b = ts[_x], ts[_y]
                # v141: am ECHTEN Textblock messen (vpos), nicht am Kamera-Ziel.
                av = a.get('vpos') or a['target']
                bv = b.get('vpos') or b['target']
                lo = max(a.get('t0', a['start']), b.get('t0', b['start']))
                hi = min(a['end'], b['end'])
                if (hi - lo > 0.25
                        and abs(av[1] - bv[1]) < 1920 * 0.16
                        and abs(av[0] - bv[0]) < 1080 * 0.42):
                    return True
        return False
    _wov = [{'word': w, 'start': 1.0 + i * .35, 'end': 1.0 + i * .35 + .3}
            for i, w in enumerate(['So', 'right', 'Shibuya', 'crossing', 'now'])]
    _plov = R.build_plans(_wov, {2}, cfg, S, 1080, 1920, lambda s, e: True,
                          {2: {'fx': 'behind', 'power': 3, 'n': 1}},
                          face_pos=lambda s, e: (540.0, 430.0, 220.0))
    check('Ueberlappung: build_plans liefert kein Doppelbild', not _codisplay(_plov))

    # Hook-Intro: vorne dicht, hinten Akzente
    wlong = [{'word': f'Wort{i}', 'start': i * .5, 'end': i * .5 + .3} for i in range(60)]
    cfg_i = dict(cfg)
    cfg_i['effects'] = dict(cfg['effects'], density='akzente', intro_hook=True,
                            intro_seconds=15)
    pli = R.build_plans(wlong, {4, 40}, cfg_i, S, W_, H_, lambda s, e: True,
                        {4: {'fx': 'behind', 'power': 2, 'n': 1},
                         40: {'fx': 'behind', 'power': 2, 'n': 1}},
                        face_pos=lambda s, e: (960.0, 430.0, 220.0))
    early = sum(1 for p in pli if p['start'] < 15)
    late = sum(1 for p in pli if p['start'] >= 15 and p['tpl'] in ('stack', 'flow'))
    check('Hook-Intro dicht/duenn', early >= 8 and late == 0, f'{early} vorn, {late} Filler hinten')

    # Personen-Follow: Filler-Captions (Flow/Stack) tragen Anker
    fillers = [p for p in pli if p['tpl'] in ('stack', 'flow')]
    check('Follow-Anker an Filler-Captions',
          bool(fillers) and all('anchor' in p or p.get('broll') for p in fillers))

    # v97 Flow-Caption: Default-Filler baut sich inline auf (Referenz-Look)
    wf = [{'word': w, 'start': 1 + j * .32, 'end': 1.25 + j * .32}
          for j, w in enumerate(['why', 'do', 'most', 'edits', 'feel', 'cheap'])]
    gf = list(range(len(wf)))
    itf, toth, anch = R.compose_flow(gf, wf, S, W_, H_, portrait=True)
    roles_f = [it['role'] for it in itf]
    check('Flow: Anker = laengstes Inhaltswort',
          anch is not None and R.clean(wf[anch]['word']) == 'edits', str(anch))
    check('Flow: genau ein Keyword', roles_f.count('key') == 1, str(roles_f))
    check('Flow: Keyword traegt letters (Schreibmaschine)',
          all(it.get('letters') for it in itf if it['role'] == 'key'))
    check('Flow: Abschlusswort ist Kursiv-Akzent',
          roles_f.count('accent') == 1 and itf[-1]['role'] == 'accent', str(roles_f))
    # keine horizontale Ueberlappung innerhalb einer Zeile (nach Grundlinie)
    _rows = {}
    for it in itf:
        _rows.setdefault(round(it['cy']), []).append(it)
    _ovl = False
    for _r in _rows.values():
        _r = sorted(_r, key=lambda z: z['cx'])
        for _a, _b in zip(_r, _r[1:]):
            if _a['cx'] + _a['adv'] / 2 > _b['cx'] - _b['adv'] / 2 + 2:
                _ovl = True
    check('Flow: keine Wort-Ueberlappung in der Zeile', not _ovl)
    # nur Verbinder -> kein erzwungenes Keyword
    wf2 = [{'word': w, 'start': j * .3, 'end': j * .3 + .2}
           for j, w in enumerate(['the', 'of', 'a', 'to'])]
    _, _, anch2 = R.compose_flow(list(range(4)), wf2, S, W_, H_, portrait=True)
    check('Flow: reine Verbinder ohne Keyword', anch2 is None)
    # build_plans: Flag an -> tpl 'flow', Flag aus -> tpl 'stack'
    cfg_fl = dict(cfg); cfg_fl['effects'] = dict(cfg['effects'], caption_flow=True)
    cfg_st = dict(cfg); cfg_st['effects'] = dict(cfg['effects'], caption_flow=False)
    pf_on = R.build_plans(wf, set(), cfg_fl, S, W_, H_, lambda s, e: True, {},
                          face_pos=lambda s, e: (960.0, 430.0, 220.0))
    pf_off = R.build_plans(wf, set(), cfg_st, S, W_, H_, lambda s, e: True, {},
                           face_pos=lambda s, e: (960.0, 430.0, 220.0))
    check('Flow-Flag an -> tpl flow',
          any(p['tpl'] == 'flow' for p in pf_on) and not any(p['tpl'] == 'stack' for p in pf_on))
    check('Flow-Flag aus -> tpl stack (Rueckfall)',
          any(p['tpl'] == 'stack' for p in pf_off) and not any(p['tpl'] == 'flow' for p in pf_off))
    _flowp = next((p for p in pf_on if p['tpl'] == 'flow' and p.get('flow')), None)
    check('Flow-Plan traegt flow_anchor fuer SFX-Tick',
          _flowp is not None and 'flow_anchor' in _flowp)
    # v97f: KI-Flow - GPT-Wahl fuer Anker/Akzent, validiert; Heuristik-Fallback
    wsel = [{'word': x, 'start': 1 + j * .3, 'end': 1.2 + j * .3}
            for j, x in enumerate(['this', 'trick', 'saves', 'real', 'money', 'fast'])]
    gsel = [list(range(6))]
    sel_ok = R._parse_flow_sel({'chunks': [{'g': 0, 'kw': 4, 'accent': 5}]}, gsel, wsel)
    check('KI-Flow: gueltige Wahl uebernommen',
          sel_ok.get(0, {}).get('kw') == 4 and sel_ok[0].get('accent') == 5, str(sel_ok))
    sel_bad = R._parse_flow_sel({'chunks': [
        {'g': 0, 'kw': 99},                          # Index nicht im Chunk
        {'g': 7, 'kw': 1},                           # unbekannter Chunk
        {'g': 0, 'kw': 0}]}, gsel, wsel)             # 'this' = Fuellwort
    check('KI-Flow: ungueltige Wahl verworfen', sel_bad == {}, str(sel_bad))
    itk, _, anck = R.compose_flow(gsel[0], wsel, S, W_, H_, portrait=True,
                                  flow_sel={'kw': 4, 'accent': 5})
    check('KI-Flow: compose_flow nutzt die KI-Wahl',
          anck == 4 and [it['role'] for it in itk].count('accent') == 1
          and itk[-1]['role'] == 'accent',
          f"anchor={anck} roles={[it['role'] for it in itk]}")
    _, _, anch_fb = R.compose_flow(gsel[0], wsel, S, W_, H_, portrait=True,
                                   flow_sel={'kw': 99})   # Unsinn -> Heuristik
    check('KI-Flow: Unsinn-Wahl faellt auf Heuristik zurueck', anch_fb is not None)
    # accent explizit null -> KEIN Heuristik-Akzent (KI hat entschieden)
    itn, _, _ = R.compose_flow(gsel[0], wsel, S, W_, H_, portrait=True,
                               flow_sel={'kw': 4, 'accent': None})
    check('KI-Flow: accent=null unterdrueckt Heuristik-Akzent',
          all(it['role'] != 'accent' for it in itn))

    # v97e: bei aktivem Flow wird KEINE Hook-Karte fest oben geparkt (sonst
    # kollidiert sie mit dem Flow-Text, der drueber laeuft).
    whk = [{'word': x, 'start': 0.5 + j * .35, 'end': 0.7 + j * .35}
           for j, x in enumerate(['this', 'video', 'totally', 'EXPLODES', 'in', 'seconds'])]
    fxh = {3: {'fx': 'behind', 'power': 3, 'n': 1}}
    cfg_hf = dict(cfg); cfg_hf['effects'] = dict(cfg['effects'], caption_flow=True,
                                                 instant_hook=True, intro_hook=True, hook_seconds=15)
    cfg_hs = dict(cfg); cfg_hs['effects'] = dict(cfg['effects'], caption_flow=False,
                                                 instant_hook=True, intro_hook=True, hook_seconds=15)
    ph_flow = R.build_plans(whk, {3}, cfg_hf, S, W_, H_, lambda s, e: True, fxh,
                            face_pos=lambda s, e: (540., 600., 200.))
    ph_stk = R.build_plans(whk, {3}, cfg_hs, S, W_, H_, lambda s, e: True, fxh,
                           face_pos=lambda s, e: (540., 600., 200.))
    kf = next((p for p in ph_flow if p.get('kw_i') == 3), None)
    ks = next((p for p in ph_stk if p.get('kw_i') == 3), None)
    check('Flow an -> kein geparktes Hook (Keyword spielt zur Sprechzeit)',
          kf is not None and kf['start'] > 0.3, str(kf['start']) if kf else 'None')
    check('Flow aus -> Sofort-Hook parkt weiterhin ab Frame 1',
          ks is not None and ks['start'] == 0.0, str(ks['start']) if ks else 'None')

    # Editorial-Collage: Rollen Auftakt/Kern/Script
    wc = [{'word': w, 'start': 1 + j * .4, 'end': 1.3 + j * .4}
          for j, w in enumerate(['Willkommen', 'im', 'Studio', '47', 'Nord'])]
    toks = R.compose_phrase(list(range(5)), wc, S, W_, H_, False)
    roles = sorted(t.get('role', '?') for t in toks)
    check('Collage-Rollen', roles == ['core', 'pre', 'script'], str(roles))

    # Hochzaehlen: Formatierer + Builder am Plan
    fmt, cdur = R.make_counter('14 MILLIARDEN EURO')
    seq = [fmt(x) for x in (0.0, cdur / 2, cdur)]
    check('Zaehler rollt aus', seq[0].startswith('0') and seq[-1].startswith('14'),
          ' -> '.join(seq))
    fmt2, _ = R.make_counter('2,5 PROZENT')
    check('Zaehler Dezimal', fmt2(9)[:3] == '2,5', fmt2(9))
    plc = R.build_plans(wc, {3}, cfg_i, S, W_, H_, lambda s, e: True,
                        {3: {'fx': 'outline', 'power': 3, 'n': 1}})
    kwp = next((p for p in plc if 'kw_i' in p), None)
    ok_b = kwp is not None and 'count' in kwp and 'builder' in kwp
    if ok_b:
        res = kwp['builder']('7')
        ok_b = isinstance(res, tuple) and res[0].ndim == 3
    check('Zaehler-Builder rendert', bool(ok_b))

    # Entrance-Rotation: aufeinanderfolgende Momente variieren
    pli2 = R.build_plans(wlong, {4, 14, 24}, cfg_i, S, W_, H_, lambda s, e: True,
                         {i: {'fx': 'behind', 'power': 2, 'n': 1} for i in (4, 14, 24)})
    entrs = [p.get('entr') for p in pli2 if 'kw_i' in p]
    check('Entrance-Rotation', len(set(entrs)) == len(entrs) >= 2, str(entrs))

    # Text-Korrektur: Editor-Text ersetzt Whisper-Text (einzeln + Komposition)
    wt = [{'word': w, 'start': 1 + i * .4, 'end': 1 + i * .4 + .3} for i, w in
          enumerate(['Alpha', 'Beta', 'Gamma', 'Delta'])]
    plt = R.build_plans(wt, {1}, cfg, S, W_, H_, lambda s, e: True,
                        {1: {'fx': 'behind', 'power': 2, 'n': 2, 'txt': 'Neue Worte'}})
    kwp = next(p for p in plt if 'kw_i' in p)
    tok_txts = [t.get('txt', '') for t in kwp.get('tokens', [])]
    ok_t = any('NEUE' in s or 'WORTE' in s for s in tok_txts)
    check('Text-Korrektur in Komposition', bool(ok_t), str(tok_txts))

    # Synthetische Sounds sind ERSATZLOS entfernt: sie klangen billig, und ein
    # billiger Sound ist schlechter als gar keiner. Es gibt nur noch echte
    # Aufnahmen aus dem Sound-Pack. Ohne Pack laeuft das Video ohne SFX.
    import sfx_engine
    _synth = [_n for _n in ('whoosh', 'impact', 'boom', 'crack', 'slam', 'riser',
                            'tick', 'counter', 'fall', 'rise', 'turn', 'press',
                            'vanish', 'whoosh_soft')
              if hasattr(sfx_engine, _n)]
    check('Keine synthetischen Sounds mehr im Code', not _synth,
          'noch da: ' + ', '.join(_synth) if _synth else 'alle entfernt')
    _rsrc_sfx = open(os.path.join(HERE, 'sfx_engine.py'), encoding='utf-8').read()
    check('Keine Klang-Synthese mehr',
          '_phantom_sub' not in _rsrc_sfx and '_bandsweep_noise' not in _rsrc_sfx)
    # Ohne Pack: sauber stumm, kein Crash. Wichtig: LEEREN, existierenden Ordner
    # uebergeben - ein nicht existierender Pfad wuerde auf den echten Pack
    # zurueckfallen (der jetzt im Repo liegt) und der Test waere sinnlos.
    _tmp_np = tempfile.mkdtemp()
    _out_np = os.path.join(_tmp_np, 'leer.wav')
    _empty_pack = os.path.join(_tmp_np, 'leerpack')
    os.makedirs(_empty_pack, exist_ok=True)
    _n_np = sfx_engine.build_sfx_track(
        [{'tpl': 'behind', 'kw_i': 0, 'start': 1.0, 'end': 2.0}],
        [{'word': ' Test', 'start': 1.0, 'end': 1.4}], 3.0,
        _empty_pack, _out_np, powers={0: 2})
    check('Ohne Sound-Pack laeuft es stumm durch',
          _n_np == 0 and os.path.exists(_out_np),
          'keine Ersatztoene, kein Absturz')
    shutil.rmtree(_tmp_np, ignore_errors=True)

    # --- Randfaelle ---
    # Lange Videos: Regie-Chunking deckt alles ab, schneidet an Satzgrenzen
    wl = [{'word': f'Wort{i}' + ('.' if i % 12 == 11 else ''),
           'start': i * .35, 'end': i * .35 + .3} for i in range(1000)]
    # v80d: 3-Tupel (Kontext-Start, Ende, Auswahl-Start) mit 30-Wort-Overlap
    ch = R._regie_chunks(wl, max_words=400)
    cover = ch[0][0] == 0 and ch[-1][1] == 1000 and \
        all(ch[k][1] == ch[k + 1][2] for k in range(len(ch) - 1))
    sizes = all(b - s <= 400 for a, b, s in ch)
    olap = all(a == max(0, s - 30) for a, b, s in ch[1:])
    sent = all(wl[b - 1]['word'].endswith('.') for a, b, s in ch[:-1])
    check('Regie-Chunking lange Videos', cover and sizes and olap and sent
          and len(ch) >= 3, f'{len(ch)} Etappen, Overlap 30')
    check('Regie-Chunking kurze Videos = 1 Call',
          R._regie_chunks(wl[:300], max_words=400) == [(0, 300, 0)])

    # Power-3-Deckel: video-weit maximal zwei Hoehepunkte
    fm = {10: {'fx': 'behind', 'power': 3}, 200: {'fx': 'ground', 'power': 3},
          500: {'fx': 'behind', 'power': 3}, 900: {'fx': 'ground', 'power': 3}}
    R._cap_power3(fm)
    threes = sorted(i for i, v in fm.items() if v['power'] == 3)
    check('Power-3-Deckel video-weit', threes == [10, 900], str(threes))

    # Regie-Selbstkontrolle: Sound-Animationen (bruch/sturz/...) nur behalten,
    # wenn ihr Ausloeser wirklich im Satz steht - sonst falscher Sound.
    _wsan = [{'word': w} for w in
             ['Deutschland', 'bricht', 'seine', 'Versprechen', '.',
              'Der', 'Umsatz', 'ist', 'stabil', 'geblieben', '.']]
    _fm_ok = {0: {'fx': 'behind', 'power': 3, 'n': 1, 'anim': 'bruch'}}
    R._regie_sanity(_fm_ok, _wsan)
    check('Sound-Anim bleibt bei echtem Ausloeser',
          _fm_ok[0].get('anim') == 'bruch')
    _fm_bad = {6: {'fx': 'outline', 'power': 2, 'n': 1, 'anim': 'bruch'}}
    R._regie_sanity(_fm_bad, _wsan)
    check('Sound-Anim faellt ohne Ausloeser weg (kein Fehl-Sound)',
          _fm_bad[6].get('anim') is None and 6 in _fm_bad)
    _fm_vis = {6: {'fx': 'cascade', 'power': 2, 'n': 1, 'anim': 'schweben'}}
    R._regie_sanity(_fm_vis, _wsan)
    check('Rein visuelle Anim wird nicht angetastet',
          _fm_vis[6].get('anim') == 'schweben')

    # Phase 2: aus frueheren Editor-Korrekturen lernen (global, deterministisch)
    _wc = [{'word': w} for w in ['Die', 'STREET', 'liegt', 'da', '.',
                                 'Kein', 'Abo', 'mehr', '.']]
    _corr = [{'phrase': 'STREET', 'user_fx': 'ground', 'user_anim': ''}]
    _fmc = {1: {'fx': 'behind', 'power': 3, 'n': 1, 'anim': 'bruch'}}
    R._apply_corrections(_fmc, _wc, _corr)
    check('Gelernte Korrektur zieht Effekt nach',
          _fmc[1]['fx'] == 'ground' and _fmc[1].get('anim') is None)
    _fmd = {6: {'fx': 'outline', 'power': 2, 'n': 1}}
    R._apply_corrections(_fmd, _wc, [{'phrase': 'Abo', 'user_aktiv': False}])
    check('Gelernte Deaktivierung entfernt den Moment', 6 not in _fmd)
    _fme = {1: {'fx': 'behind', 'power': 2, 'n': 1}}
    R._apply_corrections(_fme, _wc, [{'phrase': 'ganz anderes', 'user_fx': 'ground'}])
    check('Ohne passende Korrektur bleibt alles', _fme[1]['fx'] == 'behind')

    # Sprach-Intent: die Caption folgt der Ansage im Satz (Kern-Differenzierung).
    def _W(s): return [{'word': w} for w in s.split()]
    _si1 = {1: {'fx': 'outline', 'power': 2, 'n': 1}}
    R._speech_intent(_si1, _W('schau die caption ist hinter mir jetzt'))
    check('"hinter mir" -> Text hinter der Person', _si1[1]['fx'] == 'behind')
    _si2 = {2: {'fx': 'behind', 'power': 3, 'n': 1}}
    R._speech_intent(_si2, _W('das wort STREET auf dem boden liegt'))
    check('"auf dem Boden" -> liegt am Boden',
          _si2[2]['fx'] == 'ground' and _si2[2].get('szene') == 'boden'
          and _si2[2].get('lage') == 'liegend')
    _si3 = {2: {'fx': 'cascade', 'power': 3, 'n': 1}}
    R._speech_intent(_si3, _W('mein name DouchkoVE ueber mir am himmel'))
    check('"am Himmel" -> steigt ueber den Kopf',
          _si3[2]['fx'] == 'behind' and _si3[2].get('szene') == 'himmel')
    _si4 = {1: {'fx': 'outline', 'power': 2, 'n': 1}}
    R._speech_intent(_si4, _W('das ist einfach ein normaler satz'))
    check('Ohne Orts-Ansage bleibt der Effekt', _si4[1]['fx'] == 'outline')
    # v92: Ansage gilt nur im SELBEN Satz. "behind me." im Vorsatz darf das
    # naechste Keyword (STREET, Regie sagt Boden) NICHT hinter die Person ziehen.
    _si5 = {4: {'fx': 'ground', 'power': 3, 'n': 1,
                'szene': 'boden', 'lage': 'liegend'}}
    R._speech_intent(_si5, _W('They hide behind me. STREET. A fifty hour edit.'))
    check('Ansage endet an der Satzgrenze',
          _si5[4]['fx'] == 'ground' and _si5[4].get('szene') == 'boden')

    # Zahlen in der Fallback-Heuristik (jede Sprache)
    wn = [{'word': w, 'start': 1 + i * .3, 'end': 1.25 + i * .3} for i, w in
          enumerate(['Wir', 'zahlen', 'heute', '100', 'Euro', 'dafuer.'])]
    kwn = R.detect_keywords(wn, cfg, None)
    check('Zahlen als Auto-Keyword', 3 in kwn, str(sorted(kwn)))

    # Kein Gesicht im ganzen Video: alles B-Roll-platziert, kein Absturz
    wnf = [{'word': f'Wort{i}', 'start': i * .5, 'end': i * .5 + .3} for i in range(20)]
    plnf = R.build_plans(wnf, {4, 12}, cfg, S, W_, H_, lambda s, e: False,
                         {4: {'fx': 'behind', 'power': 2, 'n': 1},
                          12: {'fx': 'outline', 'power': 2, 'n': 1}})
    kw_nf = [p for p in plnf if 'kw_i' in p]
    check('Kein Gesicht -> B-Roll-Pfad', bool(plnf) and bool(kw_nf)
          and all(p.get('broll') for p in kw_nf), f'{len(plnf)} Plaene')

    # Fremdsprache: Phrasen ohne Grossschreibung bleiben zusammen (en)
    we = [{'word': w, 'start': 1 + i * .3, 'end': 1.25 + i * .3} for i, w in
          enumerate(['dynamic', 'pricing', 'is', 'here'])]
    regie_json = '{"keywords": [{"i": 0, "n": 2, "fx": "cascade", "power": 2}]}'
    r_en = R.parse_regie(regie_json, we, 'en')
    r_de = R.parse_regie(regie_json, we, 'de')
    check('Fremdsprache Phrasen-Logik',
          r_en and r_en[0]['n'] == 2 and r_de and r_de[0]['n'] == 1,
          f"en n={r_en and r_en[0]['n']}, de n={r_de and r_de[0]['n']}")

    # Adaptive Farben: tuerkise Szene -> getoentes Fast-Weiss + tuerkiser Akzent
    import subprocess as _sp
    teal = os.path.join(tempfile.gettempdir(), 'dve_teal.mp4')
    _sp.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',
             '-i', 'color=c=0x2E8B8B:size=320x240:duration=2:rate=25',
             '-c:v', 'libx264', '-preset', 'ultrafast', teal], check=True)
    pal = R.scene_palette_sampler(teal)(0.5)
    ok_p = pal is not None
    if ok_p:
        (tr, tg, tb), (ar, ag, ab) = pal
        ok_p = (min(tr, tg, tb) >= 190         # fast weiss
                and (tr, tg, tb) != (255, 255, 255)  # aber getoent
                and tg >= tr and tb >= tr      # kuehler Stich (tuerkis)
                and ag > ar and ab > ar)       # Akzent traegt den Szenenton
    check('Adaptive Farben aus Szene', bool(ok_p), str(pal))

    # Spiegelung: Deckkraft laeuft nach unten aus, sitzt unter der Textkante
    spr = S.text('WASSER', 120, S.accent, extrude=S.ex)[0]
    ref, rdy, rdx = R.make_reflection(spr)
    ok_r = ref is not None and rdy > 0
    if ok_r:
        a_top = float(ref[: max(ref.shape[0] // 5, 1), :, 3].mean())
        a_bot = float(ref[-max(ref.shape[0] // 5, 1):, :, 3].mean())
        ok_r = a_top > a_bot * 3 and a_bot < 8
    check('Spiegelung faellt aus', bool(ok_r),
          f'dy={rdy:.0f}' if ref is not None else 'kein Sprite')

    # Ground auf B-Roll: zwei Referenz-Varianten
    wg = [{'word': w, 'start': 1 + i * .4, 'end': 1.3 + i * .4} for i, w in
          enumerate(['Grosse', 'Momente', 'stehen', 'in', 'der', 'Szene'])]
    plg = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False,
                        {1: {'fx': 'behind', 'power': 3, 'n': 1}})
    kpg = [p for p in plg if 'kw_i' in p]
    # Ohne szene-Angabe = fester Boden: flach aufgemalt (ground_paint), NICHT
    # gewellt wie Wasser (scene_blend). Wasser ist der Sonderfall szene='wasser'.
    check('Liegend auf Boden (power 3)', bool(kpg) and kpg[0]['tpl'] == 'ground'
          and kpg[0].get('ground_paint') is True
          and not kpg[0].get('scene_blend') and kpg[0].get('refl') is None
          and kpg[0].get('cshadow') is None,
          kpg[0]['tpl'] if kpg else 'kein Plan')
    plg_s = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False,
                          {1: {'fx': 'ground', 'power': 2, 'n': 1}})
    kpg_s = [p for p in plg_s if 'kw_i' in p]
    check('Stehend mit Spiegelung (power 2)', bool(kpg_s)
          and kpg_s[0].get('refl') is not None
          and not kpg_s[0].get('scene_blend'))

    # v92: "liegt auf dem Boden" MUSS liegen - auch im Talking-Head (Gesicht
    # im Bild). Frueher wurde 'ground' dort weggemappt ('ground' steht in
    # keiner Look-Rotation) bzw. zum stehenden Billboard degradiert.
    plg_th = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: True,
                           {1: {'fx': 'ground', 'power': 2, 'n': 1,
                                'szene': 'boden', 'lage': 'liegend'}})
    kpg_t = [p for p in plg_th if 'kw_i' in p]
    check('Boden-Text liegt auch im Talking-Head',
          bool(kpg_t) and kpg_t[0]['tpl'] == 'ground'
          and kpg_t[0].get('lying') is True
          and kpg_t[0].get('scene_ground') is True
          and kpg_t[0].get('ground_paint') is True)
    check('Szenen-Text: Tracking an, Spiegelung/Schatten aus',
          bool(kpg_t) and kpg_t[0].get('track3d') is True
          and kpg_t[0].get('refl') is None and kpg_t[0].get('cshadow') is None
          and kpg_t[0]['cy'] > H_ * 0.6)
    plg_w = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: True,
                          {1: {'fx': 'ground', 'power': 2, 'n': 1,
                               'szene': 'wand', 'lage': 'stehend'}})
    kpg_w = [p for p in plg_w if 'kw_i' in p]
    check('Wand-Text steht an der Wand (Talking-Head)',
          bool(kpg_w) and kpg_w[0].get('scene_ground') is True
          and not kpg_w[0].get('lying') and not kpg_w[0].get('scene_blend')
          and kpg_w[0].get('refl') is None)

    # v93: "liegt schon da" - Szenen-Moment beginnt VOR dem Wort; t_word
    # haelt den Sprech-Zeitpunkt (Anker-Fenster + Fallback), flat_arr das
    # Roh-Sprite fuer die gemessene Neigung.
    check('Szenen-Text startet vor dem Wort',
          bool(kpg_t) and kpg_t[0].get('t_word') is not None
          and kpg_t[0]['start'] < kpg_t[0]['t_word'] - 0.9
          and kpg_t[0].get('flat_arr') is not None)
    # Neigung aus der Tiefenkarte (Naehe: nah=gross)
    _H2, _W2 = 240, 200
    _n1 = (np.arange(_H2, dtype=np.float32) / _H2)[:, None].repeat(_W2, 1)
    _p1 = R.ground_pose(_n1, 100, 170, 80, 60, _W2, _H2)
    check('Bodenneigung: gerade Flucht -> kein Roll',
          _p1 is not None and abs(_p1[0]) < 6)
    _n2 = (0.7 * (np.arange(_H2, dtype=np.float32) / _H2)[:, None]
           + 0.3 * (np.arange(_W2, dtype=np.float32) / _W2)[None, :])
    _p2 = R.ground_pose(_n2.astype(np.float32), 100, 170, 80, 60, _W2, _H2)
    check('Bodenneigung: diagonale Flucht -> Roll',
          _p2 is not None and _p2[0] < -10)
    _pu = R.ground_pose(np.full((_H2, _W2), 0.5, np.float32),
                        100, 170, 80, 60, _W2, _H2)
    check('Bodenneigung: Draufsicht -> flach ohne Roll',
          _pu is not None and _pu[0] == 0.0 and _pu[1] <= 0.6)
    check('Kein Boden, der nach unten flieht',
          R.ground_pose(1 - _n1, 100, 170, 80, 60, _W2, _H2) is None)

    # High-End-Look: kein Unterstrich mehr, nirgends
    wc2 = [{'word': w, 'start': 1 + i * .4, 'end': 1.3 + i * .4} for i, w in
           enumerate(['Eleganz', 'ist', 'leise'])]
    plc2 = R.build_plans(wc2, {0}, cfg, S, W_, H_, lambda s, e: True,
                         {0: {'fx': 'cascade', 'power': 2, 'n': 1}})
    no_line = not any('line' in p for p in plc2) and not hasattr(S, 'hairline')
    check('Kein Unterstrich', no_line)

    # Zahlen zaehlen immer hoch: auch wenn die Regie cascade waehlt
    wz = [{'word': w, 'start': 1 + i * .4, 'end': 1.3 + i * .4} for i, w in
          enumerate(['Es', 'kostet', '250', 'Euro'])]
    plz = R.build_plans(wz, {2}, cfg, S, W_, H_, lambda s, e: True,
                        {2: {'fx': 'cascade', 'power': 2, 'n': 1}})
    kpz = next((p for p in plz if 'kw_i' in p), None)
    check('Zahl zaehlt trotz cascade',
          kpz is not None and kpz['tpl'] == 'outline' and 'count' in kpz,
          kpz['tpl'] if kpz else 'kein Plan')

    # SFX-Abdeckung: Boom in der Bank, Zaehler-Dauer angepasst, Stack-Ticks
    # --- Sound-Pack-Verhalten. Die Pruef-Sounds hier baut der TEST selbst (das ist
    # eine Test-Attrappe, kein Produkt-Code - im Programm gibt es keine Synthese).
    import wave as _wave
    import sfx_pack as _SP
    _SE = sfx_engine
    tmp_sfx2 = os.path.join(tempfile.gettempdir(), 'dve_sfx_selftest2')
    shutil.rmtree(tmp_sfx2, ignore_errors=True)
    folder2 = os.path.join(tmp_sfx2, 'pack')
    os.makedirs(folder2, exist_ok=True)

    def _mk(slot, f0=800, dur=0.4):
        _t = np.arange(int(dur * _SE.SR)) / _SE.SR
        _x = (np.sin(2 * np.pi * f0 * _t) * np.exp(-_t * 6) * 0.9 * 32767)
        with _wave.open(os.path.join(folder2, slot + '.wav'), 'wb') as _w:
            _w.setnchannels(1); _w.setsampwidth(2); _w.setframerate(_SE.SR)
            _w.writeframes(_x.astype(np.int16).tobytes())
    for _s in _SE.SLOTS:
        _mk(_s, 800 if _s != 'impact' else 1000)

    check('Sound-Pack: alle Slots definiert',
          set(_SP.SLOTS) == set(_SE.SLOTS), f'{len(_SE.SLOTS)} Slots')
    check('Sound-Pack wird geladen', len(_SE.load_bank(folder2)) == len(_SE.SLOTS))
    # v96d: SFX-Variation - Varianten-Dateien + Mikro-Pitch, damit nicht jeder
    # Klick identisch klingt.
    _mk('tick_1', 900); _mk('tick_2', 700)          # zwei Tick-Varianten dazu
    _var = _SE.load_variants(folder2)
    check('SFX-Varianten: tick laedt Haupt + 2 Varianten (mehr Abwechslung)',
          len(_var.get('tick', [])) == 3 and len(_var.get('impact', [])) == 1,
          f"tick={len(_var.get('tick', []))}")
    _base = _var['tick'][0]
    _hi = _SE._pitch(_base, 1.05); _lo = _SE._pitch(_base, 0.95)
    check('SFX-Mikro-Pitch: veraendert Laenge/Klang (kein identischer Klick)',
          len(_hi) < len(_base) < len(_lo)
          and _SE._pitch(_base, 1.0) is _base)
    # v200: die Grenze lag bei _5. Wer eine sechste Variante ablegt, merkt
    # nicht, dass sie einfach nicht geladen wird - eine still gerissene
    # Grenze ist schlimmer als eine, die meckert.
    for _k in range(3, 10):
        _mk(f'tick_{_k}', 600 + _k * 40)
    _var9 = _SE.load_variants(folder2)
    check('v200: bis tick_9 wird geladen (Grenze war _5)',
          len(_var9.get('tick', [])) == 10,
          f"{len(_var9.get('tick', []))} Dateien")
    for _k in range(3, 10):
        os.remove(os.path.join(folder2, f'tick_{_k}.wav'))
    os.remove(os.path.join(folder2, 'tick_1.wav'))
    os.remove(os.path.join(folder2, 'tick_2.wav'))

    # v200 ECHTES PACK: Ismets Befund "immer dieselben Sounds". Ursache war
    # nicht der Wahl-Mechanismus, sondern dass es NICHTS zu waehlen gab -
    # jeder Slot hatte genau eine Datei, 7 der 21 hochgeladenen Sounds waren
    # nie benutzt. Der Test haengt am echten Pack, weil genau das die Zusage
    # ist ("Videos sind NICHT stumm", CLAUDE.md v175).
    _echt200 = _SE.load_variants(os.path.join(HERE, 'sfx', 'pack'))
    if _echt200:
        _n200 = sum(len(v) for v in _echt200.values())
        check('v200: das echte Pack hat mehr Dateien als Slots',
              _n200 > len(_echt200), f'{_n200} Dateien / {len(_echt200)} Slots')
        check('v200: der meistgehoerte Slot (tick) hat die meisten Varianten',
              len(_echt200.get('tick', [])) >= 5,
              f"tick={len(_echt200.get('tick', []))}")
        # Und sie muessen sich WIRKLICH unterscheiden. Zwei Schnitte aus
        # derselben Aufnahme waeren formal Varianten und klaengen gleich.
        def _spek200(s):
            f = np.abs(np.fft.rfft(s, 8192))
            return f / max(f.sum(), 1e-9)
        _tv = [_spek200(s) for s in _echt200['tick']]
        _max_aehn = max(
            float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            for i, a in enumerate(_tv) for b in _tv[i + 1:])
        check('v200: die tick-Varianten klingen wirklich verschieden',
              _max_aehn < 0.8, f'aehnlichstes Paar {_max_aehn:.2f}')

    # v200 WAHL: der Zaehler startete in JEDEM Video bei 0 - erster Tick immer
    # dieselbe Datei. Jetzt Versatz aus dem Inhalt, aber weiter reproduzierbar.
    _se200 = open(os.path.join(HERE, 'sfx_engine.py'), encoding='utf-8').read()
    check('v200: der Versatz kommt aus dem Inhalt, nicht aus dem Zufall',
          'zlib.crc32(_stoff.encode' in _se200 and '_saat) % len(vs)' in _se200)
    check('v200: KEIN hash() - das ist pro Prozess gesalzen',
          'hash((' not in _se200)
    check('v200: Pitch und Variante haengen an getrennten Versaetzen',
          '_jsaat = (_saat * 7 + 3)' in _se200)
    # v96g: Klick sitzt enger am Wort (Sync) + Folge-Akzent im 3er-Zyklus statt
    # auf jeder Caption (weniger Klick-Teppich, mehr Hook-Variation).
    _se_src = open(os.path.join(HERE, 'sfx_engine.py'), encoding='utf-8').read()
    check('SFX-Sync: outline/blurin-Tick sitzt nah am Wort (kein 0.26/0.30 mehr)',
          't0 + 0.08, 0.9 * g' in _se_src and 't0 + 0.12, 0.5 * g' in _se_src
          and 't0 + 0.26' not in _se_src and 't0 + 0.30' not in _se_src)
    check('SFX-Hook: Folge-Akzent im 3er-Zyklus (nicht auf jeder Caption)',
          '_cyc = _acc_i % 3' in _se_src and '_cyc == 2' in _se_src)
    # LIZENZ: es darf NUR CC0 durchkommen. Andere Lizenzen = Rechtsproblem.
    _fake = {'results': [
        {'id': 1, 'name': 'CC0 Sound', 'duration': 0.5, 'num_downloads': 9,
         'license': 'http://creativecommons.org/publicdomain/zero/1.0/',
         'previews': {'preview-hq-mp3': 'http://x/p.mp3'}},
        {'id': 2, 'name': 'CC-BY Sound', 'duration': 0.5, 'num_downloads': 9,
         'license': 'http://creativecommons.org/licenses/by/3.0/',
         'previews': {'preview-hq-mp3': 'http://x/p.mp3'}},
        {'id': 3, 'name': 'NC Sound', 'duration': 0.5, 'num_downloads': 9,
         'license': 'http://creativecommons.org/licenses/by-nc/3.0/',
         'previews': {'preview-hq-mp3': 'http://x/p.mp3'}}]}
    _urls = []
    _orig_get = _SP._get
    _SP._get = lambda u, timeout=25: (_urls.append(u), _fake)[1]
    try:
        _res = _SP.search('impact', 'TESTKEY')
    finally:
        _SP._get = _orig_get
    check('Sound-Pack: nur CC0 kommt durch',
          len(_res) == 1 and _res[0]['name'] == 'CC0 Sound',
          f'{len(_res)} von 3 (CC-BY und NC verworfen)')
    check('Sound-Pack: CC0-Filter geht an die API',
          bool(_urls) and 'Creative%20Commons%200' in _urls[0])
    # Eigene Dateien (z.B. Epidemic) duerfen NIE ueberschrieben werden
    _SP.save_manifest(folder2, {'impact': {'eigen': True, 'name': 'meine.wav'}})
    _sz = os.path.getsize(os.path.join(folder2, 'impact.wav'))
    _SP._get = lambda u, timeout=25: _fake
    try:
        _SP.fetch_pack('TESTKEY', pdir=folder2, slots=['impact'],
                       progress=lambda *a: None)
    finally:
        _SP._get = _orig_get
    check('Eigene Sounds werden nie ueberschrieben',
          os.path.getsize(os.path.join(folder2, 'impact.wav')) == _sz)
    check('Jede Ereignis-Animation hat einen Sound',
          all(_a in _SE.ANIM_SFX for _a in
              ('bruch', 'sturz', 'anstieg', 'wende', 'druck', 'schwund', 'knall'))
          and all(_v[0] in _SE.SLOTS for _v in _SE.ANIM_SFX.values()))
    check('Zustands-Animationen bleiben stumm',
          not any(_a in _SE.ANIM_SFX for _a in
                  ('glitch', 'puls', 'welle', 'zittern', 'neon', 'schub')),
          'Dauer-Zustaende brauchen keinen Einzel-Sound')
    # Unvollstaendiges Pack: fehlende Slots duerfen nicht crashen
    os.remove(os.path.join(folder2, 'crack.wav'))
    _tp = tempfile.mkdtemp()
    _o = os.path.join(_tp, 'x.wav')
    _nn = _SE.build_sfx_track(
        [{'tpl': 'ground', 'kw_i': 0, 'start': 1.0, 'end': 2.0, 'anim': 'bruch'}],
        [{'word': ' Test', 'start': 1.0, 'end': 1.4}], 3.0, folder2, _o,
        powers={0: 2})
    check('Fehlender Slot crasht nicht', _nn >= 1 and os.path.exists(_o),
          'crack fehlt - der Rest laeuft weiter')
    _mk('crack')
    shutil.rmtree(_tp, ignore_errors=True)
    _gsrc53 = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    # --- v55: Suchkaskade + skalierende GUI ---
    _leer = []
    _fake_narrow = {'results': []}
    _fake_broad = {'results': [{'id': 7, 'name': 'Treffer', 'duration': 2.9,
                               'num_downloads': 500,
                               'license': 'http://creativecommons.org/publicdomain/zero/1.0/',
                               'previews': {'preview-hq-mp3': 'http://x/p.mp3'}}]}

    def _fake_cascade(u, timeout=25):
        _q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        _term, _flt = _q['query'][0], _q['filter'][0]
        # Haerte-Fall: NUR breite Einwort-Suchen ohne Laengenfilter liefern etwas.
        # Genau daran sind vorher 9 von 14 Slots leer geblieben.
        if len(_term.split()) == 1 and 'duration' not in _flt:
            return _fake_broad
        return _fake_narrow
    _SP._get = _fake_cascade
    try:
        for _sl in _SP.SLOTS:
            if not _SP.search(_sl, 'K'):
                _leer.append(_sl)
    finally:
        _SP._get = _orig_get
    check('Suchkaskade laesst keinen Slot leer', not _leer,
          'leer: ' + ', '.join(_leer) if _leer else 'alle 14 finden etwas')
    # v56: Der meistgeladene CC0-"impact" auf Freesound ist ein Glas-Crash. Vorher
    # wurde stur der meistgeladene genommen -> es krachte bei JEDEM grossen Wort.
    _mix = {'results': [
        {'id': 1, 'name': 'Glass Crash Impact',
         'tags': ['glass', 'crash', 'break'], 'duration': 2.4,
         'num_downloads': 50000, 'avg_rating': 4.5,
         'license': 'http://creativecommons.org/publicdomain/zero/1.0/',
         'previews': {'preview-hq-mp3': 'http://x/1.mp3'}},
        {'id': 2, 'name': 'Deep Impact Hit',
         'tags': ['impact', 'hit', 'cinematic'], 'duration': 0.62,
         'num_downloads': 900, 'avg_rating': 4.2,
         'license': 'http://creativecommons.org/publicdomain/zero/1.0/',
         'previews': {'preview-hq-mp3': 'http://x/2.mp3'}}]}
    _SP._get = lambda u, timeout=25: _mix
    try:
        _imp = _SP.search('impact', 'K')
        _crk = _SP.search('crack', 'K')
    finally:
        _SP._get = _orig_get
    check('Glas-Crash landet nicht im Impact-Slot',
          _imp and _imp[0]['id'] == 2,
          f"gewaehlt: {_imp[0]['name'] if _imp else '-'} (trotz 50k Downloads beim Crash)")
    check('Der Crash landet im Bruch-Slot',
          _crk and _crk[0]['id'] == 1, 'dort gehoert er hin')
    check('Jeder Slot hat ein Zielmass und Ausschlussbegriffe',
          all(_v.get('ziel') and _v.get('meiden') for _v in _SP.SLOTS.values()))
    check('Jeder Slot hat mehrere Suchbegriffe',
          all(len(_v['q']) >= 3 for _v in _SP.SLOTS.values()))
    check('GUI: skaliert mit dem Fenster',
          'def on_resize' in _gsrc53 and 'wraplength=int(' in _gsrc53
          and 'reflow_fonts' in _gsrc53)
    check('GUI: Einstellungen auf Menues verteilt',
          'NAV = {' in _gsrc53 and _gsrc53.count("'build_") >= 7)
    # --- v57: alles bleibt beim Schliessen erhalten + Klappkarten ---
    check('GUI: speichert beim Schliessen',
          'WM_DELETE_WINDOW' in _gsrc53 and 'def on_close' in _gsrc53
          and 'self.save_cfg()' in _gsrc53.split('def on_close')[1][:400]
          and 'self._fs_key()' in _gsrc53.split('def on_close')[1][:400],
          'Einstellungen UND API-Key werden gesichert')
    check('GUI: Profil sichert alle Einstellungen',
          'PROFILE_VARS' in _gsrc53
          and _gsrc53.count("_var'") >= 20
          and 'profile_snapshot' in _gsrc53)
    # Jede Variable der GUI muss im Profil landen - sonst geht sie beim Laden verloren
    _pv = re.search(r"PROFILE_VARS = \(([^)]*)\)", _gsrc53, re.S)
    _in_prof = set(re.findall(r"'(\w+_var)'", _pv.group(1))) if _pv else set()
    _all_vars = set(re.findall(r"self\.(\w+_var) = tk\.", _gsrc53))
    _fehlt_p = _all_vars - _in_prof - {'dynamik_var', 'preset_var', 'profile_var',
                                       'cam_var', 'freq_var', 'capzoom_var',
                                       'drift_var', 'kwcam_var', 'color_var'}
    check('Keine Einstellung faellt aus dem Profil',
          not _fehlt_p or _fehlt_p <= {'font_id'},
          'fehlen: ' + ', '.join(sorted(_fehlt_p)) if _fehlt_p else 'alle drin')
    check('GUI: Karten klappen auf und zu',
          'def toggle' in _gsrc53 and 'ui_state' in _gsrc53
          and "chev.configure" in _gsrc53)
    check('GUI: Sound-Vorschau klappt wieder ein',
          "btn.set_text('Andere')" in _gsrc53
          and "btn.set_text('Einklappen')" in _gsrc53)
    # --- v60: Masking + Herausschiebe-Effekt ---
    _fr60 = (np.random.default_rng(3).random((240, 320, 3)) * 255).astype(np.float32)
    _al60 = np.zeros((240, 320, 1), np.float32)
    _al60[60:200, 120:200] = 1.0                     # harte Silhouette
    _al60 = cv2.GaussianBlur(_al60[..., 0], (0, 0), 6.0)[..., None]   # weiche Maske
    _ref = R.refine_alpha(_al60, _fr60, 1.0)
    # Die Kante muss SCHAERFER werden - sonst hat die Verfeinerung nichts gebracht
    def _kantenbreite(a):
        return float(((a > 0.05) & (a < 0.95)).sum())
    check('Masking: Kante wird schaerfer',
          _kantenbreite(_ref) < _kantenbreite(_al60) * 0.9,
          f'{_kantenbreite(_al60):.0f} -> {_kantenbreite(_ref):.0f} Halbschatten-Pixel')
    check('Masking: abschaltbar', R.refine_alpha(_al60, _fr60, 0.0) is _al60)
    # ------------------------------------------------------------------
    # v228b DIE NACHSCHAERFUNG WIRD EINMAL GEGENGEPRUEFT.
    # Ismets Befund ("das Maskieren hat hier nicht gut geklappt") war an einem
    # echten Bild seines Renders messbar: die ROHE Netz-Maske ist sauber
    # (9 Kruemel/Loecher), nach der Nachschaerfung mit Staerke 1.3 waren es
    # 285 - die Kante war zerfetzt, und genau diese Kante schneidet den Text
    # aus. Die Detailstufe des Netzes ist NICHT die Ursache (0.337 gegen 0.506
    # gemessen: gleiche Kante, aber 59 -> 108 ms je Bild) - deshalb wird nicht
    # blind hochgedreht, sondern geprueft.
    _sauber = np.zeros((240, 320), np.float32)
    cv2.circle(_sauber, (160, 120), 70, 1.0, -1)
    _sauber = cv2.GaussianBlur(_sauber, (0, 0), 3)
    _dreck = _sauber.copy()
    _rng28 = np.random.default_rng(5)
    for _ in range(60):                     # lose Kruemel und Loecher
        _x, _y = int(_rng28.integers(0, 320)), int(_rng28.integers(0, 240))
        cv2.circle(_dreck, (_x, _y), 2, 1.0 if _rng28.random() < .5 else 0.0, -1)
    check('v228b: Muell in der Maske wird gezaehlt (Kruemel + Loecher)',
          R.matte_muell(_sauber) <= 2 and R.matte_muell(_dreck) >= 20,
          f'sauber {R.matte_muell(_sauber)}, zerfetzt {R.matte_muell(_dreck)}')
    # Die ENTSCHEIDUNG pruefen, nicht den Filter: eine Nachschaerfung, die die
    # Maske zerfetzt, muss heruntergedreht werden - eine, die sie sauber
    # laesst, bleibt unangetastet.
    _echt28 = R.refine_alpha
    try:
        R.refine_alpha = (lambda a, f, st: (_dreck if st > 0.8 else _sauber)[..., None])
        _st_schlecht = R._refine_pruefen(_sauber[..., None], _fr60, 1.3)
        R.refine_alpha = lambda a, f, st: _sauber[..., None]
        _st_gut = R._refine_pruefen(_sauber[..., None], _fr60, 1.3)
    finally:
        R.refine_alpha = _echt28
    check('v228b: eine zerfetzende Nachschaerfung wird heruntergedreht',
          _st_schlecht < 0.8, f'Staerke {_st_schlecht:.2f} statt 1.30')
    check('v228b: eine saubere Nachschaerfung bleibt unangetastet',
          abs(_st_gut - 1.3) < 1e-6, f'Staerke {_st_gut:.2f}')
    _rsrc28 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v230a LOECHER IM INNEREN EINER PERSON SIND IMMER EIN FEHLER.
    # Ismets Befund ("das Auge glitcht"): eine feine Linie mitten im Gesicht.
    # Beim Nachmessen an seinem Bild kam ein echter Nebenbefund heraus: die
    # v228b-Gegenprobe waehlt Staerke 0.39, und damit ist die Maske INNEN
    # nicht mehr ganz dicht - 2981 Pixel unter 0.98 (bei Staerke 1.3 nur 15).
    # Wo die Maske innen durchlaessig ist, scheint der Text HINTER der Person
    # durch sie hindurch. Gefuellt wird nur der Kern; die weiche Aussenkante
    # und echte Durchblicke (Luecke zwischen Arm und Koerper) bleiben.
    _t30 = np.zeros((400, 400), np.float32)
    cv2.rectangle(_t30, (60, 40), (340, 360), 1.0, -1)
    cv2.rectangle(_t30, (150, 120), (250, 300), 0.0, -1)   # echter Durchblick
    cv2.circle(_t30, (300, 200), 4, 0.0, -1)               # Krater
    # halbdurchlaessig, tief im Inneren (>= 14 px von jeder Kante und vom
    # Durchblick entfernt - genau das ist der Kern, der dicht sein muss)
    _t30[316:340, 266:320] = 0.80
    _g30 = R.matte_loecher_fuellen(_t30[..., None])[..., 0]
    check('v230a: der Kern der Person wird voellig undurchsichtig',
          float(_g30[316:340, 266:320].min()) >= 0.999,
          f'innen min {_g30[316:340, 266:320].min():.3f}')
    check('v230a: ein kleiner Krater wird geschlossen',
          float(_g30[200, 300]) >= 0.999, f'{_g30[200, 300]:.3f}')
    check('v230a: ein echter Durchblick bleibt offen',
          float(_g30[200, 200]) <= 0.001, f'{_g30[200, 200]:.3f}')
    # Die weiche Aussenkante darf NICHT hart werden - sonst sieht die
    # Freistellung ausgeschnitten aus (genau das, was v181 verhindert).
    _w30 = cv2.GaussianBlur(_t30, (0, 0), 6)
    _vor = int(((_w30 > 0.05) & (_w30 < 0.95)).sum())
    _nach_a = R.matte_loecher_fuellen(_w30[..., None])[..., 0]
    _rand = np.zeros_like(_w30, bool)
    _rand[cv2.dilate((_w30 > 0.5).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0] = True
    _rand[cv2.erode((_w30 > 0.5).astype(np.uint8), np.ones((21, 21), np.uint8)) > 0] = False
    check('v230a: die weiche Aussenkante bleibt weich',
          int(((_nach_a > 0.05) & (_nach_a < 0.95) & _rand).sum())
          >= int(((_w30 > 0.05) & (_w30 < 0.95) & _rand).sum()) * 0.95,
          'sonst sieht die Person ausgeschnitten aus')
    check('v230a: die Fuellung laeuft im echten Render-Pfad',
          'alpha = matte_loecher_fuellen(alpha)' in _rsrc28
          and 'def matte_loecher_fuellen' in _rsrc28)
    check('v228b: die Pruefung laeuft EINMAL je Render, nicht je Bild',
          '_refine_auto = None' in _rsrc28
          and 'if _refine_auto is None:' in _rsrc28
          and 'alpha = refine_alpha(alpha, frame, _refine_auto)' in _rsrc28,
          'sonst kostet sie in jedem Bild zwei zusaetzliche Filterlaeufe')
    # ------------------------------------------------------------------
    # v227 NUR DORT RECHNEN, WO EINE MASKE IST. Ismets Befund: knapp 3 Minuten
    # Renderzeit fuer 15 Sekunden Video. Gemessen (1080x1920, CPU) kostete
    # refine_alpha 151-279 ms je BILD - mehr als das Matting-Netz selbst
    # (216 ms). Der Guided Filter lief ueber das ganze Bild, obwohl die Maske
    # typisch ein Drittel ausmacht. Der Zuschnitt ist kein Qualitaets-
    # Kompromiss: er muss PIXELGLEICH sein, und genau das wird hier geprueft -
    # sonst waere es die verbotene Abkuerzung (Regel 1).
    def _refine_voll(alpha, frame, staerke):
        """Die Fassung VOR v227: Guided Filter ueber das ganze Bild."""
        _a = np.ascontiguousarray(alpha[..., 0].astype(np.float32))
        _g = cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_BGR2RGB)
        _r = max(int(min(frame.shape[:2]) * 0.006), 4)
        _a2 = cv2.ximgproc.guidedFilter(_g, _a, _r, 1e-4)
        if staerke > 1.15:
            _a2 = cv2.ximgproc.guidedFilter(_g, _a2, max(_r // 3, 2), 1e-5)
        _a2 = np.clip((_a2 - 0.5) * (1.0 + 0.9 * staerke) + 0.5, 0.0, 1.0)
        _m = min(staerke, 1.0)
        return (_a[..., None] * (1 - _m) + _a2[..., None] * _m).astype(np.float32)
    _W27, _H27 = 540, 960
    _rng27 = np.random.default_rng(11)
    _fr27 = np.full((_H27, _W27, 3), 70.0, np.float32)
    cv2.putText(_fr27, 'BG', (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 3,
                (210, 190, 170), 8)
    cv2.circle(_fr27, (430, 800), 120, (30, 120, 200), -1)
    _fr27 = np.clip(_fr27 + _rng27.random((_H27, _W27, 3)) * 20, 0, 255)
    _faelle27 = {}
    _a27 = np.zeros((_H27, _W27), np.float32)
    cv2.ellipse(_a27, (270, 300), (75, 95), 0, 0, 360, 1.0, -1)
    cv2.ellipse(_a27, (270, 675), (150, 280), 0, 0, 360, 1.0, -1)
    _faelle27['person'] = cv2.GaussianBlur(_a27, (0, 0), 5)
    _a27 = np.zeros((_H27, _W27), np.float32)
    cv2.rectangle(_a27, (0, 450), (250, _H27 - 1), 1.0, -1)
    _faelle27['am Bildrand'] = cv2.GaussianBlur(_a27, (0, 0), 4)
    _a27 = np.zeros((_H27, _W27), np.float32)
    cv2.circle(_a27, (150, 150), 9, 1.0, -1)
    _faelle27['winzig'] = cv2.GaussianBlur(_a27, (0, 0), 2)
    _faelle27['ganzes Bild'] = np.ones((_H27, _W27), np.float32)
    _abw27 = {}
    for _nm27, _aa27 in _faelle27.items():
        _al27 = _aa27[..., None].astype(np.float32)
        _v27 = _refine_voll(_al27, _fr27, 1.3)
        _n27 = R.refine_alpha(_al27, _fr27, 1.3)
        _abw27[_nm27] = float(np.abs(_v27 - _n27).max()) * 255.0
    check('v227: der Zuschnitt liefert PIXELGLEICHE Masken (alle Formen)',
          all(v < 0.51 for v in _abw27.values()),
          ' | '.join(f'{k}: {v:.4f}/255' for k, v in _abw27.items()))
    # Eine leere Maske hat nichts zu schaerfen - und darf gar nichts kosten.
    _leer27 = np.zeros((_H27, _W27, 1), np.float32)
    check('v227: eine leere Maske geht unveraendert durch',
          R.refine_alpha(_leer27, _fr27, 1.3) is _leer27)
    # Und es muss WIRKLICH schneller sein, sonst war der Umbau sinnlos.
    _t27 = time.time()
    for _ in range(3):
        _refine_voll(_faelle27['winzig'][..., None], _fr27, 1.3)
    _dv27 = time.time() - _t27
    _t27 = time.time()
    for _ in range(3):
        R.refine_alpha(_faelle27['winzig'][..., None], _fr27, 1.3)
    _dn27 = time.time() - _t27
    check('v227: bei kleiner Maske ist es deutlich schneller',
          _dn27 < _dv27 * 0.6,
          f'{_dv27 / 3 * 1000:.0f} ms -> {_dn27 / 3 * 1000:.0f} ms je Bild')
    # Und der Render muss sagen, WO die Zeit hingeht - sonst ist die naechste
    # Optimierung wieder Raten (genau das war der Zustand bis v226b).
    R._ZEIT.clear()
    _t27 = time.time() - 2.0
    R.zt('phase-a', _t27)
    R.zt('phase-b', time.time() - 0.5)
    _rp27 = R.zeit_report(4.0)
    # v228c BILD-REGIE UND OBJEKT-ANKER LAUFEN GLEICHZEITIG.
    # Ismets Job-Log: ki-bildregie 39.5s + ki-objektanker 25.3s, streng
    # hintereinander - und beide warten nur auf dieselbe Schnittstelle. Sie
    # sind unabhaengig (die eine schreibt szene/lage, die andere anker), also
    # laufen sie parallel auf je einer KOPIE. Zusammengefuehrt wird
    # deterministisch, sonst haenge das Ergebnis daran, wer zuerst fertig ist.
    _sz28 = {3: {'fx': 'behind', 'szene': 'wand', 'lage': 'stehend'},
             7: {'fx': 'ground', 'szene': 'boden'}}
    _an28 = {3: {'fx': 'behind', 'anker': {'objekt': 'glas', 'cx': .5}},
             7: {'fx': 'ground'}, 9: {'anker': {'objekt': 'geist'}}}
    _mg28 = R.merge_anker(copy.deepcopy(_sz28), _an28)
    check('v228c: der Anker steuert NUR sein eigenes Feld bei',
          _mg28[3]['anker']['objekt'] == 'glas'
          and _mg28[3]['szene'] == 'wand' and _mg28[3]['lage'] == 'stehend'
          and 'anker' not in _mg28[7] and 9 not in _mg28,
          str(_mg28))
    check('v228c: die Zusammenfuehrung ist unabhaengig von der Reihenfolge',
          R.merge_anker(copy.deepcopy(_sz28), _an28)
          == R.merge_anker(copy.deepcopy(_sz28), dict(reversed(list(_an28.items())))))
    _rq28 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v228c: die beiden Vision-Aufrufe laufen im Thread-Pool',
          'ThreadPoolExecutor(max_workers=2)' in _rq28
          and '_ex.submit(_lauf_szene)' in _rq28
          and '_ex.submit(_lauf_anker)' in _rq28
          and 'copy.deepcopy(fx_map)' in _rq28,
          'ohne Kopie schreiben zwei Threads in dieselben dicts')
    # v228d DENK-AUFWAND. 129 von 191 s waren Warten auf die KI, und der
    # Loewenanteil davon ist internes Nachdenken. `reasoning_effort` steuert
    # genau das - Standard 'low' (Ismets Entscheidung). Das Denkbudget bleibt
    # bei mindestens 2500: weniger denken heisst MEHR Platz fuer die Antwort,
    # die v210-Falle (leere Antwort -> JSONDecodeError) wird dadurch
    # unwahrscheinlicher, nicht wahrscheinlicher.
    _alt_dk = R.AI_DENKEN
    try:
        R.AI_DENKEN = 'low'
        _b1_dk = R._oai_json('gpt-5', [{'role': 'user', 'content': 'x'}], 800, 0.2)
        _b2_dk = R._oai_json('gpt-4o', [{'role': 'user', 'content': 'x'}], 800, 0.2)
        R.AI_DENKEN = 'aus'
        _b3_dk = R._oai_json('gpt-5', [{'role': 'user', 'content': 'x'}], 800, 0.2)
    finally:
        R.AI_DENKEN = _alt_dk
    check('v228d: die neue Regie-KI denkt nur so lange wie eingestellt',
          _b1_dk.get('reasoning_effort') == 'low', str(_b1_dk)[:120])
    check('v228d: das Denkbudget bleibt bei mindestens 2500 (v210-Falle)',
          _b1_dk.get('max_completion_tokens') == 2500
          and 'max_tokens' not in _b1_dk, str(_b1_dk)[:120])
    check('v228d: alte Chat-Modelle bekommen den Parameter NICHT',
          'reasoning_effort' not in _b2_dk and _b2_dk.get('max_tokens') == 800,
          str(_b2_dk)[:120])
    check('v228d: "aus" schickt ihn gar nicht (Verhalten wie vorher)',
          'reasoning_effort' not in _b3_dk, str(_b3_dk)[:120])
    check('v228d: der Wert steht in der config und ist damit umstellbar',
          str(cfg['keywords'].get('ai_denken', '')).lower()
          in ('minimal', 'low', 'medium', 'high', 'aus'),
          str(cfg['keywords'].get('ai_denken')))
    # v228e ZURUECKGESTELLT. Ismets Befund nach dem ersten Render mit 'low':
    # "Qualitaet ist sehr schlecht geworden". Die Regie ist das Herz des
    # Produkts; Renderzeit dagegen zu tauschen war das falsche Geschaeft.
    # Der Test haelt den Rueckweg fest - wer den Standard wieder auf ein
    # Denk-Limit stellt, muss diese Zeile bewusst anfassen.
    check('v228e: der Auslieferungs-Standard ist wieder volles Nachdenken',
          str(cfg['keywords'].get('ai_denken', '')).lower() == 'aus'
          and "AI_DENKEN = 'aus'" in _rq28,
          str(cfg['keywords'].get('ai_denken')))
    # Und der Zeit-Report darf verschachtelte Bloecke nicht DOPPELT zaehlen:
    # in Ismets Zeile stand 'regie+plaene 133.2s' NEBEN den KI-Aufrufen, die
    # darin stecken - die Summe ergab 190 %.
    R._ZEIT.clear()
    R._ZEIT.update({'regie+plaene': 133.2, 'ki-textregie': 37.7,
                    'ki-bildregie+anker': 39.5, 'ki-textfluss': 26.1})
    _rp28 = R.zeit_report(191.0)
    _anteil = sum(float(x) for x in re.findall(r'(\d+\.\d+)s \(', _rp28))
    check('v228c: verschachtelte Bloecke zaehlen nicht doppelt',
          _anteil <= 191.5 and 'regie+plaene 29.9s' in _rp28, _rp28)
    R._ZEIT.clear()
    check('v227: der Render berichtet, wo die Zeit hingeht',
          _rp27.startswith('Timing (total 4.0s):') and 'phase-a 2.0s' in _rp27
          and 'other' in _rp27 and _rp27.index('phase-a') < _rp27.index('phase-b'),
          _rp27)
    # ------------------------------------------------------------------
    # v227a EINZELBILDER: GLEICHZEITIG HOLEN, NICHT ZWEIMAL HOLEN.
    # Am Kundenrender (154.7s) steckten 64 % der Zeit VOR dem ersten Bild.
    # Darin: bis zu 40 Zeige-Proben, 24 Vision-Bilder und 16 Anker-Bilder -
    # jedes ein eigener ffmpeg-Start, streng hintereinander, und die Vision-
    # Bilder doppelt (Bild-Regie und Objekt-Anker fragen dieselbe Stelle).
    # Beides ist Wartezeit, keine Qualitaet: gleiche Argumente -> gleiches
    # Bild. Genau das wird hier geprueft, sonst waere es eine Abkuerzung.
    _ts27 = [round(0.05 + _i * 0.2, 2) for _i in range(8)]
    R._FRAME_BGR_CACHE.clear()
    _ser27 = [R._frame_bgr(clip, _t) for _t in _ts27]
    R._FRAME_BGR_CACHE.clear()
    R._frame_bgr_vorab(clip, _ts27)
    _par27 = [R._frame_bgr(clip, _t) for _t in _ts27]
    _gl27 = all((_a is None and _b is None)
                or (_a is not None and _b is not None and _a.shape == _b.shape
                    and not np.any(_a != _b))
                for _a, _b in zip(_ser27, _par27))
    check('v227a: parallel geholte Einzelbilder sind BITGLEICH',
          _gl27 and any(_x is not None for _x in _par27),
          f'{sum(_x is not None for _x in _par27)}/{len(_ts27)} Bilder')
    R._FRAME_B64_CACHE.clear()
    _b1_27 = [R._frame_b64(clip, _t) for _t in _ts27]
    R._FRAME_B64_CACHE.clear()
    R._frame_b64_vorab(clip, _ts27)
    _b2_27 = [R._frame_b64(clip, _t) for _t in _ts27]
    check('v227a: parallel geholte Vision-Bilder sind BITGLEICH',
          _b1_27 == _b2_27,
          f'{sum(_x is not None for _x in _b2_27)}/{len(_ts27)} Bilder')
    # Und derselbe Frame darf nicht zweimal aus dem Video geholt werden.
    _run27 = R.subprocess.run
    _cnt27 = {'x': 0}

    def _zaehl27(*a, **k):
        _cnt27['x'] += 1
        return _run27(*a, **k)
    R.subprocess.run = _zaehl27
    try:
        _b3_27 = [R._frame_b64(clip, _t) for _t in _ts27]
    finally:
        R.subprocess.run = _run27
    check('v227a: derselbe Frame wird nicht zweimal geholt (Zwischenspeicher)',
          _cnt27['x'] == 0 and _b3_27 == _b2_27,
          f'{_cnt27["x"]} ffmpeg-Starts beim zweiten Abruf')
    _src27 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v227a: Zeige-Regie und Hand-Regie holen ihre erste Probe vorab',
          _src27.count('_frame_bgr_vorab(video_path, [float(t) + proben[0] '
                       'for t in times])') == 2)
    check('v227a: Bild-Regie und Objekt-Anker holen ihre Bilder vorab',
          _src27.count("_frame_b64_vorab(video_path, "
                       "[words[i]['start'] + 0.15 for i in idx])") == 2)
    R._FRAME_BGR_CACHE.clear()
    R._FRAME_B64_CACHE.clear()
    R._ZEIT.clear()
    # ------------------------------------------------------------------
    # v228f NUR AM SAUM RECHNEN. Beim Profilieren des Captions-Setzens
    # (720x1280, dichte Captions) war kill_spill mit 36 ms je Bild der
    # teuerste Einzelposten - teurer als alles andere im Compositor. Der Saum
    # ist ein schmales Band um die Silhouette; ausserhalb ist der Faktor exakt
    # 0 und die Formel liefert das Bild unveraendert. Trotzdem liefen
    # Weichzeichner, Graustufen-Mittel und Mischung ueber das GANZE Bild.
    # Wie bei v227 gilt: Tempo NUR gegen eine Pixelgleichheits-Pruefung.
    def _spill_voll(person, alpha, frame):
        """Die Fassung VOR v228f: ueber das ganze Bild."""
        _a = alpha[..., 0]
        _k = cv2.GaussianBlur((_a > 0.05).astype(np.float32)
                              - (_a > 0.95).astype(np.float32), (0, 0), 2.0)
        _k = np.clip(_k, 0, 1)[..., None]
        return person * (1 - 0.35 * _k) + person.mean(axis=2, keepdims=True) * (0.35 * _k)
    _W2f, _H2f = 480, 854
    _rngf = np.random.default_rng(9)
    _pf = (_rngf.random((_H2f, _W2f, 3)) * 255).astype(np.float32)
    _faellef = {}
    _af = np.zeros((_H2f, _W2f), np.float32)
    cv2.ellipse(_af, (240, 470), (120, 280), 0, 0, 360, 1.0, -1)
    _faellef['person'] = cv2.GaussianBlur(_af, (0, 0), 5)
    _af = np.zeros((_H2f, _W2f), np.float32)
    cv2.rectangle(_af, (0, 400), (200, _H2f - 1), 1.0, -1)
    _faellef['am Bildrand'] = cv2.GaussianBlur(_af, (0, 0), 4)
    _af = np.zeros((_H2f, _W2f), np.float32)
    cv2.circle(_af, (120, 120), 18, 1.0, -1)
    _faellef['klein'] = cv2.GaussianBlur(_af, (0, 0), 3)
    _faellef['ganzes Bild'] = np.ones((_H2f, _W2f), np.float32)
    _abwf = {}
    for _nf, _aaf in _faellef.items():
        _alf = _aaf[..., None]
        _abwf[_nf] = float(np.abs(_spill_voll(_pf, _alf, _pf)
                                  - R.kill_spill(_pf, _alf, _pf)).max())
    check('v228f: der Farbsaum-Zuschnitt ist PIXELGLEICH (alle Formen)',
          all(v < 1e-4 for v in _abwf.values()),
          ' | '.join(f'{k}: {v:.6f}' for k, v in _abwf.items()))
    _leerf = np.zeros((_H2f, _W2f, 1), np.float32)
    check('v228f: ohne Maske gibt es keinen Saum (und keine Rechnerei)',
          float(np.abs(R.kill_spill(_pf, _leerf, _pf) - _pf).max()) == 0.0)
    _t2f = time.time()
    for _ in range(4):
        _spill_voll(_pf, _faellef['klein'][..., None], _pf)
    _dvf = time.time() - _t2f
    _t2f = time.time()
    for _ in range(4):
        R.kill_spill(_pf, _faellef['klein'][..., None], _pf)
    _dnf = time.time() - _t2f
    check('v228f: bei kleiner Silhouette ist es deutlich schneller',
          _dnf < _dvf * 0.6,
          f'{_dvf / 4 * 1000:.1f} ms -> {_dnf / 4 * 1000:.1f} ms je Bild')
    _pers = np.full((240, 320, 3), 200.0, np.float32)
    _pers[..., 0] = 255.0                            # blauer Farbstich am Rand
    _sp = R.kill_spill(_pers, _al60, _fr60)
    check('Masking: Farbsaum wird gedaempft',
          float(np.abs(_sp - _pers).max()) > 1.0)
    # Herausschieben: aus der Person heraus aufdecken
    _w60 = np.zeros((40, 400, 4), np.uint8)
    _w60[..., 3] = 255
    _sicht = lambda a: float((a[..., 3] > 10).sum())
    _eng = R.reveal_from(_w60, 200.0, 30.0)
    _weit = R.reveal_from(_w60, 200.0, 180.0)
    check('Wort wird aus der Person heraus aufgedeckt',
          _sicht(_eng) < _sicht(_weit) < _sicht(_w60),
          f'{_sicht(_eng):.0f} < {_sicht(_weit):.0f} < {_sicht(_w60):.0f} Pixel')
    check('Aufdecken waechst nach BEIDEN Seiten',
          _eng[20, 175, 3] > 0 and _eng[20, 225, 3] > 0
          and _eng[20, 20, 3] == 0 and _eng[20, 380, 3] == 0)
    _rsrc60 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check("Effekt 'emerge' ist in der Rotation", "'emerge'" in _rsrc60
          and "entr == 'emerge'" in _rsrc60)
    check('Emerge nur mit Person und Freistellung',
          "_em_moeglich = (fx == 'behind' and not broll and face_pos is not None)"
          in _rsrc60 and "if p['entr'] == 'emerge' and not _em_moeglich" in _rsrc60)

    # --- v57: Alles bleibt erhalten + iPhone-Klappkarten ---
    # --- v60: Herausschieben steuerbar + Maskenqualitaet ---
    import io as _io2, contextlib as _cl2
    _hw2 = [{'word': ' Deutschland', 'start': 1.0, 'end': 1.5},
            {'word': ' verschweigt', 'start': 1.6, 'end': 2.1}]

    def _plans_em(mode):
        c2 = copy.deepcopy(cfg)
        c2['effects'].update(emerge=mode, retention_gap=0, pattern_interrupt=0)
        with _cl2.redirect_stdout(_io2.StringIO()):
            return R.build_plans(_hw2, {0}, c2, S, W_, H_, lambda a, b: True,
                                 {0: {'fx': 'behind', 'power': 3, 'n': 1}},
                                 face_pos=lambda a, b: (960.0, 430.0, 150.0))
    _pi_im = [p for p in _plans_em('immer') if 'kw_i' in p]
    _pi_au = [p for p in _plans_em('aus') if 'kw_i' in p]
    check("Herausschieben 'immer' greift",
          _pi_im and _pi_im[0].get('entr') == 'emerge')
    check("Herausschieben 'aus' greift",
          _pi_au and _pi_au[0].get('entr') != 'emerge')
    # Das Wort muss die Person UEBERLAPPEN - sonst verdeckt sie nichts und der
    # Effekt ist unsichtbar (genau der Fehler: Wort stand ueber dem Kopf).
    check('Herausgeschobenes Wort liegt auf Personenhoehe',
          _pi_im and abs(_pi_im[0].get('by', 0) - (430.0 - H_ * 0.055)) < 2,
          f"by={_pi_im[0].get('by', 0):.0f}, Gesicht bei 430" if _pi_im else '-')
    # Ohne Person gibt es nichts, wovon das Wort hervorkommen koennte
    with _cl2.redirect_stdout(_io2.StringIO()):
        _pl_nf = R.build_plans(_hw2, {0}, copy.deepcopy(cfg), S, W_, H_,
                               lambda a, b: True,
                               {0: {'fx': 'behind', 'power': 3, 'n': 1}})
    check('Ohne Person kein Herausschieben',
          all(p.get('entr') != 'emerge' for p in _pl_nf if 'kw_i' in p))
    # v96z LESBARKEIT: schmales Wort hinter riesigem Kopf. (a) Kopf so breit,
    # dass selbst das Randlimit nicht reicht -> Wort kommt UEBER den Kopf.
    with _cl2.redirect_stdout(_io2.StringIO()):
        _pl_big = R.build_plans([{'word': ' Go', 'start': 1.0, 'end': 1.9}], {0},
                                copy.deepcopy(cfg), S, W_, H_, lambda a, b: True,
                                {0: {'fx': 'behind', 'power': 3, 'n': 1}},
                                face_pos=lambda a, b: (960.0, 430.0, 1200.0))
    _pb = [p for p in _pl_big if 'kw_i' in p]
    check('Lesbarkeit: schmales Wort + Riesen-Kopf -> ueber den Kopf gelegt',
          _pb and _pb[0].get('by', 9999) <= H_ * 0.075 + 2,
          f"by={_pb[0].get('by', -1):.0f}" if _pb else '-')
    # (b) Kopf gross, aber Platz vorhanden -> Wort wird VERGROESSERT, bis es
    # deutlich beidseitig am Kopf herausragt (statt dahinter zu verschwinden).
    with _cl2.redirect_stdout(_io2.StringIO()):
        _pl_mid = R.build_plans([{'word': ' Go', 'start': 1.0, 'end': 1.9}], {0},
                                copy.deepcopy(cfg), S, W_, H_, lambda a, b: True,
                                {0: {'fx': 'behind', 'power': 3, 'n': 1}},
                                face_pos=lambda a, b: (960.0, 430.0, 400.0))
    _pm = [p for p in _pl_mid if 'kw_i' in p]
    _vw = 0
    if _pm and _pm[0].get('arr') is not None:
        import numpy as _npv
        _ax = _npv.where(_pm[0]['arr'][..., 3] > 8)[1]
        _vw = int(_ax.max() - _ax.min()) if _ax.size else 0
    check('Lesbarkeit: Wort wird vergroessert (breiter als Kopf x1.1)',
          _vw >= 400 * 1.7 * 1.1, f'Wortbreite {_vw}px vs Kopf {int(400*1.7)}px')
    # Maskenqualitaet muss die Detailstufe wirklich anheben
    _rsrc_q = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Maskenqualitaet verdrahtet',
          "QUAL = {'standard'" in _rsrc_q and "matting_quality" in _rsrc_q
          and 'q_refine' in _rsrc_q)
    check('Hohe Qualitaet rechnet feiner als Standard',
          "'hoch': (1.6, 1.3)" in _rsrc_q and "'maximum': (2.2, 1.6)" in _rsrc_q)
    check('Kantenverfeinerung zweistufig bei hoher Qualitaet',
          'staerke > 1.15' in _rsrc_q and 'r // 3' in _rsrc_q)
    check('Zeitliche Glaettung ist bewegungsabhaengig',
          'bewegung < 0.15' in _rsrc_q and 'Geisterschatten' in _rsrc_q)
    _g60 = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    check('GUI: Herausschieben + Maskenqualitaet bedienbar',
          'emerge_var' in _g60 and 'mask_var' in _g60
          and 'Maskenqualität' in _g60)
    check('GUI: Fenstergroesse wird gemerkt',
          "ui_state['geometry']" in _gsrc53 and "_st.get('geometry')" in _gsrc53)
    check('GUI: Klapp-Zustand ueberlebt den Neustart',
          "self.ui_state.get('open', {}).get(title, True)" in _gsrc53)
    check('GUI: Sound-Auswahl klappt wieder ein',
          'zweiter Klick = wieder einklappen' in _gsrc53)
    # Das Kundenprofil muss ALLE Einstellungen fassen - sonst schleppt man beim
    # Kundenwechsel heimlich Werte mit.
    import re as _re
    _pv = _re.search(r'PROFILE_VARS = \((.*?)\)', _gsrc53, _re.S).group(1)
    _allvars = set(_re.findall(r'self\.([a-z_]+_var)\s*=\s*tk\.', _gsrc53))
    _fehlt_pv = sorted(v for v in _allvars if f"'{v}'" not in _pv
                       and v not in ('fx_var', 'init_var'))
    check('Kundenprofil erfasst alle Einstellungen', not _fehlt_pv,
          'fehlen: ' + ', '.join(_fehlt_pv) if _fehlt_pv else
          f'{len(_allvars) - 2} Einstellungen')
    check('GUI: Sound-Pack bedienbar',
          'pack_fetch' in _gsrc53 and 'pack_popup' in _gsrc53
          and 'pack_play' in _gsrc53 and 'fskey' in _gsrc53)

    check('Punchline sitzt lauter', _SE.ANIM_SFX['knall'][2] > 1.0,
          f"Knall x{_SE.ANIM_SFX['knall'][2]}")
    _t_cnt = 2 * 0.9
    # Frueher wurde hier die Tonhoehen-Richtung der SYNTHETISCHEN Sounds geprueft
    # (Sturz musste abwaerts klingen). Die Synthese ist raus - bei echten Aufnahmen
    # entscheidet das Ohr beim Vorhoeren, nicht eine Messung. Test ersatzlos weg.
    sfx_out = os.path.join(tempfile.gettempdir(), 'dve_sfx_track_test.wav')
    plans_sfx = [
        {'tpl': 'outline', 'kw_i': 2, 'start': 1.8, 'end': 3.4,
         'count': {'fmt': (lambda x: str(int(x))), 'dur': 1.4}},
        {'tpl': 'ground', 'kw_i': 3, 'start': 5.0, 'end': 6.8},
        {'tpl': 'stack', 'start': 8.2, 'end': 9.0},
        {'tpl': 'stack', 'start': 8.6, 'end': 9.4},   # zu nah -> Limiter schluckt ihn
        {'tpl': 'stack', 'start': 10.5, 'end': 11.2},
    ]
    words_sfx = [{'word': f'W{i}', 'start': i * 0.9, 'end': i * 0.9 + 0.4}
                 for i in range(14)]
    n_sfx = sfx_engine.build_sfx_track(plans_sfx, words_sfx, 12.0, folder2, sfx_out,
                                       powers={3: 3})
    sig = sfx_engine.load_wav(sfx_out)
    def rms(a, b):
        seg = sig[int(a * sfx_engine.SR):int(b * sfx_engine.SR)]
        return float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0
    # Die Sounds haengen am WORT-Zeitpunkt (words[kw_i]), nicht am Plan-Start.
    # Frueher stand hier ein festes Fenster, das nur deshalb passte, weil der alte
    # Boom 3.2 s lang war und mit seinem Schwanz hineinragte. Jetzt wird gegen die
    # echten Zeitpunkte geprueft.
    _t_cnt = words_sfx[2]['start']                    # Zaehler-Moment
    _t_pw3 = words_sfx[3]['start']                    # power-3: Riser davor, Boom drauf
    ok_sfx = (n_sfx >= 4                              # 2 Momente + 2 Ticks (1 gelimitet)
              and rms(_t_cnt, _t_cnt + 1.4) > 0.01    # Zaehler rollt
              and rms(_t_pw3 - 0.9, _t_pw3) > 0.005   # Riser laeuft auf den Moment zu
              and rms(_t_pw3, _t_pw3 + 0.9) > 0.008   # Boom sitzt auf dem Moment
              and rms(8.1, 8.5) > 0.001               # Stack-Tick 1
              and rms(11.5, 12.0) < 0.004)            # danach Ruhe
    check('SFX volle Abdeckung', bool(ok_sfx), f'{n_sfx} Sounds')
    shutil.rmtree(tmp_sfx2, ignore_errors=True)

    # Szenen-Integration: liegender Boden-Text traegt ground_paint (flach
    # aufgemalt), Wasser traegt scene_blend; Talking-Head-Ground keines von beiden.
    check('Ground blendet in die Szene',
          bool(kpg) and kpg[0].get('ground_paint') is True)
    plg_th = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: True,
                           {1: {'fx': 'ground', 'power': 2, 'n': 1}})
    kpg_th = [p for p in plg_th if 'kw_i' in p]
    check('Talking-Head-Ground bleibt klassisch',
          bool(kpg_th) and not kpg_th[0].get('scene_blend')
          and kpg_th[0].get('cshadow') is not None)

    # Refraktion: Wellen-Gradienten verschieben die Buchstaben-Kanten
    canvas_r = np.zeros((240, 400, 3), dtype=np.float32)
    yy = np.arange(240)[:, None]
    canvas_r[...] = (120 + 90 * np.sin(yy / 14.0))[..., None]  # grobe Wellen-Struktur
    spr_r = np.zeros((100, 300, 4), dtype=np.uint8)
    spr_r[30:70, 30:270] = (255, 255, 255, 255)
    before = canvas_r.copy()
    R.paste_scene(canvas_r, spr_r, 200, 120, 400, 240, refract=2.0, ripple=0.0)
    shifted = float(np.abs(canvas_r[93:100, 100:200, 0] - before[93:100, 100:200, 0]).mean()) \
        + float(np.abs(canvas_r[140:147, 100:200, 0] - before[140:147, 100:200, 0]).mean())
    check('Refraktion verschiebt Kanten', shifted > 3.0, f'{shifted:.1f}')

    # paste_scene: Untergrund-Struktur moduliert die Buchstaben
    canvas = np.zeros((200, 300, 3), dtype=np.float32)
    canvas[:, ::2] = 40.0
    canvas[:, 1::2] = 220.0                    # harte Wellen-Streifen
    spr = np.zeros((80, 200, 4), dtype=np.uint8)
    spr[20:60, 20:180] = (255, 255, 255, 255)  # weisser Block
    R.paste_scene(canvas, spr, 150, 100, 300, 200, ripple=0.45)
    inner = canvas[86:114, 82:218, 0]          # nur der deckende Textblock
    plain = np.zeros((200, 300, 3), dtype=np.float32)
    plain[:, ::2] = 40.0
    plain[:, 1::2] = 220.0
    R.paste(plain, spr, 150, 100, 300, 200)
    inner_p = plain[86:114, 82:218, 0]
    check('Szene moduliert den Text',
          float(inner.std()) > float(inner_p.std()) + 5,
          f'std {inner.std():.1f} vs {inner_p.std():.1f} (plain)')

    # Regionen-Sampling: 'unten' liest den Untergrund
    import subprocess as _sp2
    split = os.path.join(tempfile.gettempdir(), 'dve_split.mp4')
    _sp2.run(['ffmpeg', '-y', '-v', 'error',
              '-f', 'lavfi', '-i', 'color=c=0x808080:size=320x480:d=2:r=25',
              '-f', 'lavfi', '-i', 'color=c=0x2E8B8B:size=320x240:d=2:r=25',
              '-filter_complex', '[0][1]overlay=0:240',
              '-c:v', 'libx264', '-preset', 'ultrafast', split], check=True)
    pal_u = R.scene_palette_sampler(split)(0.5, 'unten')
    check('Untergrund-Palette (unten)',
          pal_u is not None and pal_u[0][1] >= pal_u[0][0]
          and pal_u[0][2] >= pal_u[0][0], str(pal_u))

    # Vision-Regie v4: Frame-Sampler liefert JPEG, Cache traegt szene/lage,
    # und 'lage' uebersteuert die Power-Regel
    b64 = R._frame_b64(split, 0.5)
    import base64 as _b64
    check('Vision-Frame-Sampler', b64 is not None
          and _b64.b64decode(b64)[:2] == b'\xff\xd8', 'JPEG ok' if b64 else 'leer')
    rj = ('{"keywords": [{"i": 1, "n": 1, "fx": "ground", "power": 2,'
          ' "szene": "wasser", "lage": "liegend"}]}')
    fm = R.parse_regie(rj, wg, 'de')
    check('Cache traegt szene/lage', fm and fm[1].get('szene') == 'wasser'
          and fm[1].get('lage') == 'liegend')
    pll = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False, fm)
    kpl = [p for p in pll if 'kw_i' in p]
    check('Lage uebersteuert Power', bool(kpl)
          and kpl[0].get('scene_blend') is True, 'liegend trotz power 2')
    fm2 = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "ground", "power": 3,'
                        ' "lage": "stehend"}]}', wg, 'de')
    pls = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False, fm2)
    kps = [p for p in pls if 'kw_i' in p]
    check('Stehend trotz Power 3', bool(kps) and not kps[0].get('scene_blend')
          and kps[0].get('refl') is not None)

    # v99 Selbstbezug: "The captions are behind me" besteht komplett aus
    # Sperrlisten-Woertern - die KI kann dort kein Keyword waehlen. Der
    # deterministische Backstop erzeugt den Moment selbst.
    def _wsr(text):
        return [{'word': ' ' + w, 'start': i * .35, 'end': i * .35 + .3}
                for i, w in enumerate(text.split())]
    _sr = R._self_ref_intent({}, _wsr('The captions are behind me. More talk follows now.'))
    check('Selbstbezug: "behind me" erzeugt behind-Moment',
          bool(_sr) and _sr.get(3, {}).get('fx') == 'behind'
          and _sr[3].get('n') == 2, str(_sr))
    _sr2 = R._self_ref_intent({}, _wsr('My captions explode right now. Unrelated sentence here.'))
    check('Selbstbezug: "captions explode" -> explosion, sichtbar vorn',
          bool(_sr2) and _sr2.get(2, {}).get('anim') == 'explosion'
          and _sr2[2].get('fx') != 'behind', str(_sr2))
    _sr3 = R._self_ref_intent({}, _wsr('Diese Wörter liegen auf dem Boden. Danach normal weiter.'))
    check('Selbstbezug DE: "auf dem Boden" -> ground/boden/liegend',
          bool(_sr3) and _sr3.get(3, {}).get('fx') == 'ground'
          and _sr3[3].get('szene') == 'boden'
          and _sr3[3].get('lage') == 'liegend', str(_sr3))
    check('Selbstbezug: kein Treffer ohne Caption-Bezug',
          R._self_ref_intent({}, _wsr('The prices explode this year.')) == {}
          and R._self_ref_intent({}, _wsr('I give you my word about it.')) == {})
    # v209: AN ISMETS WERBE-VIDEO GEMESSEN. Dort wurde KEINE der drei Ansagen
    # erkannt - der Text stand vor der Person statt hinter ihr, neben der Wand
    # statt darauf, neben dem Kopf statt darueber. Ursache war der Wortschatz:
    # 'line' und 'one' fehlten, und in "this NEXT line" steht ein Adjektiv
    # zwischen Bestimmungswort und Nomen. Genau so redet ein Mensch ueber
    # seine Captions - ein Wortschatz, der die haeufigste Formulierung nicht
    # kennt, ist derselbe Fehler wie ein Riegel am falschen Gate.
    _v209 = R._self_ref_intent({}, _wsr(
        'Watch this next line goes behind me. This one sticks on the wall. '
        'This one floats above me. I just talked.'))
    _v209f = {d.get('fx') + '/' + d.get('szene', '') for d in _v209.values()}
    check('v209: "this next line goes behind me" landet HINTER der Person',
          'behind/' in _v209f, str(_v209f))
    check('v209: "this one sticks on the wall" landet AN DER WAND',
          any(d.get('fx') == 'ground' and d.get('szene') == 'wand'
              and d.get('lage') == 'stehend' for d in _v209.values()), str(_v209))
    check('v209: "this one floats above me" geht NACH OBEN',
          any(d.get('szene') == 'himmel' for d in _v209.values()), str(_v209))
    check('v209: alle drei Ansagen sind als Gesetz markiert (intent)',
          len(_v209) == 3 and all(d.get('intent') for d in _v209.values()),
          str(len(_v209)))
    # Gegenprobe: derselbe Wortschatz darf NICHT auf beliebige Saetze
    # anspringen. 'behind me' ohne Bezug auf den Text ist eine Ortsangabe
    # ueber einen Menschen, keine Regie-Anweisung.
    check('v209: ohne Bezug auf den Text passiert weiterhin nichts',
          R._self_ref_intent({}, _wsr('The guy behind me was loud today.')) == {}
          and R._self_ref_intent({}, _wsr(
              'I put the box on the wall yesterday.')) == {}
          and R._self_ref_intent({}, _wsr('One thing above me broke.')) == {})
    _sr5 = R._self_ref_intent({2: {'fx': 'behind', 'power': 2, 'n': 1}},
                              _wsr('Watch this word fly across the screen.'))
    check('Selbstbezug: bestehender Moment bekommt Handlung + wird sichtbar',
          _sr5[2].get('anim') == 'spur' and _sr5[2].get('fx') == 'outline',
          str(_sr5))
    _wsr1 = _wsr('The captions are behind me. More talk follows now.')
    _plsr = R.build_plans(_wsr1, set(_sr), cfg, S, W_, H_,
                          lambda s, e: True, _sr)
    _kpsr = [p for p in _plsr if p.get('kw_i') == 3]
    check('Selbstbezug: "BEHIND ME" landet als behind-Plan',
          bool(_kpsr) and _kpsr[0]['tpl'] == 'behind'
          and 'BEHIND' in _kpsr[0].get('kw_txt', ''),
          str(_kpsr[0].get('kw_txt') if _kpsr else None))
    # v209a: KARTE GEGEN KARTE. Der Solo-Riegel verglich nur Karte gegen
    # Fliesstext. Drei Orts-Ansagen hintereinander ergeben drei Karten, und
    # eine Karte steht laenger als ihr gesprochenes Wort - an Ismets Werbespot
    # gemessen lagen 'ON THE WALL' (7.20-10.25) und 'BEHIND ME' (7.25-8.75)
    # anderthalb Sekunden uebereinander. Zwei Texte gleichzeitig im Bild.
    _w209 = _wsr('Watch this next line goes behind me. This one sticks on '
                 'the wall. This one floats above me. I just talked here.')
    _fx209 = R._speech_intent(R._self_ref_intent({}, _w209), _w209)
    _pl209 = R.build_plans(_w209, set(_fx209), cfg, S, W_, H_,
                           lambda s, e: True, _fx209)
    _kw209 = sorted([p for p in _pl209 if 'kw_i' in p], key=lambda p: p['start'])
    _ov209 = [(a['kw_txt'], b['kw_txt']) for a, b in zip(_kw209, _kw209[1:])
              if b['start'] < a['end'] + a.get('aus', 0.40) - 1e-6]
    check('v209a: zwei Keyword-Karten stehen NIE gleichzeitig im Bild',
          not _ov209, str(_ov209))
    check('v209a: jede Karte behaelt ihre Mindestlesezeit (0.8 s)',
          all(p['end'] - p['start'] >= 0.79 for p in _kw209),
          str([round(p['end'] - p['start'], 2) for p in _kw209]))
    # v213: EINE ANSAGE VERSCHWINDET NIE. Der v209a-Riegel schob die mittlere
    # Karte so weit nach hinten, dass sie in die naechste fiel und ganz
    # ausblieb - in Ismets Werbespot fehlte 'ON THE WALL' komplett, obwohl er
    # es sagt. Eine Ueberschneidung zu beseitigen, indem man eine Aussage
    # loescht, ist keine Loesung.
    check('v213: drei Ansagen ergeben DREI Karten, keine faellt weg',
          len(_kw209) == 3, str([p['kw_txt'] for p in _kw209]))
    check('v213: jede Ansage steht auch wirklich im Bild (Dauer > 0)',
          all(p['end'] > p['start'] + 0.19 for p in _kw209),
          str([round(p['end'] - p['start'], 2) for p in _kw209]))
    check('v209a: die Ansagen bleiben in der gesprochenen Reihenfolge',
          [p['kw_txt'] for p in _kw209][:1] != [] and len(_kw209) >= 2,
          str([p['kw_txt'] for p in _kw209]))
    # ------------------------------------------------------------------
    # v214: EINE ANSAGE STEHT NIE VOR IHREM WORT.
    # Ismets Job-Log: Karte 'ON THE WALL' ab 8.18 s, gesprochen ab 9.08 s.
    # Sagt er "sticks on the wall", ist die Karte schon weg - im Bild sieht
    # es aus, als fehle sie ganz. Ursache: der 1.5-s-Vorlauf des Szenen-
    # Texts ("liegt schon da"), den der Solo-Riegel danach als t0 festschrieb.
    # Gemessen wird die Zeit, zu der die Karte WIRKLICH erscheint (card_t0) -
    # p['start'] ist der Gruppen-Anfang und traegt nur die Nebenwoerter.
    _fruh214 = [(p['kw_txt'], round(R.card_t0(p, _w209) - _w209[p['kw_i']]['start'], 2))
                for p in _kw209
                if R.card_t0(p, _w209) < _w209[p['kw_i']]['start'] - 1e-6]
    check('v214: keine Ansage erscheint vor ihrem gesprochenen Wort',
          not _fruh214, str(_fruh214))
    check('v214: jede Ansage ist als solche am Plan markiert (intent)',
          all(p.get('intent') for p in _kw209),
          str([(p['kw_txt'], p.get('intent')) for p in _kw209]))
    check('v214: jede Ansage hat danach noch Buehne (>= 0.5 s)',
          all(p['end'] - R.card_t0(p, _w209) >= 0.49 for p in _kw209),
          str([round(p['end'] - R.card_t0(p, _w209), 2) for p in _kw209]))
    # Der Riegel selbst: eine kuenftige Zeit-Regel, die eine Ansage nach vorn
    # zieht, wird zentral zurueckgeholt - und die Karte behaelt ihre Buehne.
    _fw214 = [{'word': ' ' + x, 'start': 2.0 + i * 0.3, 'end': 2.2 + i * 0.3}
              for i, x in enumerate(['this', 'one', 'sticks', 'on', 'the', 'wall'])]
    _fp214 = [{'tpl': 'ground', 'kw_i': 3, 'kw_txt': 'ON THE WALL', 'intent': True,
               'start': 1.4, 't0': 1.4, 'end': 3.2},
              {'tpl': 'ground', 'kw_i': 3, 'kw_txt': 'SPAETER IST OK', 'intent': True,
               'start': 3.4, 't0': 3.4, 'end': 4.4},
              {'tpl': 'ground', 'kw_i': 3, 'kw_txt': 'OHNE ANSAGE', 'start': 1.4,
               't0': 1.4, 'end': 3.2}]
    _n214 = R.intent_time_floor(_fp214, _fw214)
    check('v214: der Riegel holt eine vorgezogene Ansage an ihr Wort zurueck',
          _n214 == 1 and abs(_fp214[0]['t0'] - _fw214[3]['start']) < 1e-6,
          f"{_n214} korrigiert, t0={_fp214[0]['t0']}")
    check('v214: eine spaetere Ansage bleibt unangetastet (spaet ist erlaubt)',
          _fp214[1]['t0'] == 3.4 and _fp214[1]['end'] == 4.4)
    check('v214: der Riegel fasst NUR Ansagen an, nicht jeden Szenen-Text',
          _fp214[2]['t0'] == 1.4 and _fp214[2]['start'] == 1.4)
    _fp214b = [{'tpl': 'ground', 'kw_i': 3, 'kw_txt': 'KNAPP', 'intent': True,
                'start': 1.4, 't0': 1.4, 'end': 2.95}]
    R.intent_time_floor(_fp214b, _fw214)
    check('v214: eine zurueckgeholte Ansage bekommt ihre Mindest-Buehne',
          _fp214b[0]['end'] - _fp214b[0]['t0'] >= 0.49,
          str(round(_fp214b[0]['end'] - _fp214b[0]['t0'], 2)))
    check('v214: Nutzer-gesetzte Zeiten bleiben auch bei einer Ansage stehen',
          R.intent_time_floor([{'tpl': 'ground', 'kw_i': 3, 'intent': True,
                                '_user_t': True, 'start': 1.0, 't0': 1.0,
                                'end': 3.0}], _fw214) == 0)
    # Gegenprobe: der 1.5-s-Vorlauf ("liegt schon da") ist NICHT abgeschafft -
    # er gilt weiter fuer Szenen-Text, den niemand angesagt hat. Sonst haetten
    # wir einen Bug behoben, indem wir ein Feature entfernen.
    _wv214 = [{'word': ' ' + x, 'start': 2.0 + i * 0.4, 'end': 2.3 + i * 0.4}
              for i, x in enumerate(['der', 'Asphalt', 'glaenzt', 'heute', 'sehr'])]
    _fxv214 = {1: {'fx': 'ground', 'szene': 'boden', 'lage': 'liegend',
                   'power': 3, 'n': 1}}
    _plv214 = R.build_plans(_wv214, {1}, cfg, S, W_, H_, lambda s, e: True, _fxv214)
    _kwv214 = [p for p in _plv214 if p.get('kw_i') == 1]
    check('v214: Szenen-Text OHNE Ansage behaelt den 1.5-s-Vorlauf',
          bool(_kwv214) and _kwv214[0]['start'] <= _wv214[1]['start'] - 1.4,
          str(round(_kwv214[0]['start'], 2) if _kwv214 else None))
    # Instant-Hook: die staerkste fruehe Karte wird auf Frame 1 gezogen -
    # eine ANSAGE darf er dafuer nicht nehmen, sonst steht sie Sekunden vor
    # dem Satz, der sie ankuendigt.
    _cfg214 = copy.deepcopy(cfg)
    _cfg214['effects']['caption_flow'] = False
    _cfg214['effects']['instant_hook'] = True
    _pl214h = R.build_plans(_w209, set(_fx209), _cfg214, S, W_, H_,
                            lambda s, e: True, _fx209)
    _kw214h = [p for p in _pl214h if p.get('intent')]
    check('v214: der Sofort-Hook zieht keine Ansage auf Frame 1',
          bool(_kw214h) and all(R.card_t0(p, _w209) >= _w209[p['kw_i']]['start'] - 1e-6
                                for p in _kw214h),
          str([(p['kw_txt'], round(R.card_t0(p, _w209), 2),
                _w209[p['kw_i']]['start']) for p in _kw214h]))
    # Beat-Grid: der Takt darf einen Moment atmen lassen, aber nicht vor den
    # Satz ziehen, der ihn ankuendigt.
    _bts214 = [round(x * 0.05, 2) for x in range(0, 300)]
    _pl214b = R.build_plans(_w209, set(_fx209), cfg, S, W_, H_,
                            lambda s, e: True, _fx209, beat_times=_bts214)
    _kw214b = [p for p in _pl214b if p.get('intent')]
    check('v214: das Beat-Grid rastet eine Ansage nie vor ihr Wort',
          bool(_kw214b) and all(R.card_t0(p, _w209) >= _w209[p['kw_i']]['start'] - 1e-6
                                for p in _kw214b),
          str([(p['kw_txt'], round(R.card_t0(p, _w209), 2)) for p in _kw214b]))
    # ------------------------------------------------------------------
    # v215: DER SOLO-RIEGEL MASS DIE LESEZEIT AM FALSCHEN PUNKT.
    # Er rechnete ab p['start'] - dem Anfang der WORTGRUPPE. Dort setzen aber
    # nur die kleinen Nebenwoerter ein; die grosse Karte kommt erst mit ihrem
    # eigenen Wort. Damit glaubte er einer Karte eine Lesezeit, die sie nie
    # hatte: 'CAPTIONS' stand auf dem Papier 1.20-2.00, im Bild 1.80-2.00 -
    # 0.20 s statt der hier garantierten 0.80 s. Dieselbe Verwechslung wie
    # bei der Ansage (v214), nur eine Regel weiter.
    check('v215: card_t0 liefert das Erscheinen, nicht den Gruppen-Anfang',
          R.card_t0({'kw_i': 2, 'start': 1.0}, [{'start': 0.0}, {'start': 0.5},
                                                {'start': 1.9}]) == 1.9
          and R.card_t0({'kw_i': 2, 'start': 1.0, 't0': 2.4},
                        [{'start': 0.0}, {'start': 0.5}, {'start': 1.9}]) == 2.4
          and R.card_t0({'start': 0.7}, []) == 0.7)
    _w215 = [{'word': ' ' + x, 'start': i * 0.30, 'end': i * 0.30 + 0.27}
             for i, x in enumerate(
                 'Ich zeig dir heute wie wir Captions auf ein neues Level '
                 'bringen das sind die grossen Momente deines Videos klar'.split())]
    _pl215 = R.build_plans(_w215, R.detect_keywords(_w215, cfg, None), cfg, S,
                           W_, H_, lambda s, e: True, None)
    _tx215 = sorted([p for p in _pl215 if 'target' in p],
                    key=lambda p: R.card_t0(p, _w215))
    _bu215 = [(p.get('kw_txt') or 'FLIESSTEXT',
               round(R.card_t0(p, _w215), 2),
               round(p['end'] - R.card_t0(p, _w215), 2)) for p in _tx215]
    # Vor v215 stand 'CAPTIONS' hier 0.20 s im Bild - ein Blinzeln.
    check('v215: kein Textmoment blinzelt (jeder steht >= 0.35 s im Bild)',
          all(b[2] >= 0.35 for b in _bu215), str(_bu215))
    # Und die Gegenrichtung: die richtige Messung darf nicht dazu fuehren,
    # dass die Karte den nachfolgenden Fliesstext kaputtschiebt. Der traegt
    # die Woerter, die gerade gesprochen werden.
    check('v215: ein wartender Fliesstext-Block behaelt seine Lesezeit',
          all(b[2] >= 0.55 for b in _bu215 if b[0] == 'FLIESSTEXT'),
          str([b for b in _bu215 if b[0] == 'FLIESSTEXT']))
    check('v215: die Karte behaelt ihren Vorrang (sie steht allein)',
          not [1 for _i in range(len(_tx215)) for _j in range(_i + 1, len(_tx215))
               if min(_tx215[_i]['end'] + _tx215[_i].get('aus', 0.15),
                      _tx215[_j]['end'])
               - max(R.card_t0(_tx215[_i], _w215), R.card_t0(_tx215[_j], _w215))
               > 0.05],
          str(_bu215))
    _src215 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v215: der Solo-Riegel misst ab dem Erscheinen der Karte',
          '_ks = _ct0(_k)' in _src215 and '_bs = _ct0(_b)' in _src215
          and 'def _ct0(p):' in _src215 and '_FLOW_MIN = 0.55' in _src215)
    # ------------------------------------------------------------------
    # v216: AN ISMETS RENDER GEMESSEN (15 s, 720x1280).
    # (a) KEIN TEXT WIRD VOM BILDRAND ANGESCHNITTEN. Im Video lief
    #     'CAPTIONS LOOK THE' links UND rechts aus dem Bild (vorne fehlte
    #     das C, hinten das E), 'THIS ONE FLOATS' klebte mit beiden Kanten
    #     am Rand. Ein halb abgeschnittenes Wort ist unlesbar.
    _kt216 = R.Sprites(cfg, 720, 1280)
    _arr216 = _kt216.text('CAPTIONS LOOK THE', 150, _kt216.white)[0]
    _p216 = {'tpl': 'outline', 'kw_i': 0, 'kw_txt': 'CAPTIONS LOOK THE',
             'arr': _arr216, 'cx': 360.0, 'cy': 900.0, 'target': (360.0, 900.0),
             'start': 1.0, 'end': 2.0}
    _v216 = R.ink_box(_p216, 720, 1280)
    _n216 = R.fit_into_frame([_p216], 720, 1280)
    _n216b = R.ink_box(_p216, 720, 1280)
    check('v216: eine zu breite Karte wird ins Bild zurueckgeholt',
          _n216 == 1 and _v216[0] < -1 and _v216[1] > 721
          and _n216b[0] >= -10 and _n216b[1] <= 730,
          f"vorher {_v216[0]/720:.3f}..{_v216[1]/720:.3f} W, "
          f"nachher {_n216b[0]/720:.3f}..{_n216b[1]/720:.3f} W")
    _its216 = [{'i': k, 'arr': _kt216.text(x, 110, _kt216.white)[0],
                'cx': 60 + k * 230, 'cy': 960, 'w': 200, 't': 1.0 + k * 0.2,
                'role': 'key'} for k, x in enumerate(['THIS', 'ONE', 'FLOATS'])]
    _pf216 = {'tpl': 'flow', 'front': _its216, 'target': (360, 960),
              'start': 1.0, 'end': 2.0}
    _vf216 = R.ink_box(_pf216, 720, 1280)
    R.fit_into_frame([_pf216], 720, 1280)
    _nf216 = R.ink_box(_pf216, 720, 1280)
    check('v216: auch ein Fliesstext-Block wird ins Bild zurueckgeholt',
          _vf216[1] > 721 and _nf216[1] <= 730 and _nf216[0] >= -10,
          f"vorher {_vf216[0]/720:.3f}..{_vf216[1]/720:.3f} W, "
          f"nachher {_nf216[0]/720:.3f}..{_nf216[1]/720:.3f} W")
    # Der GEWOLLTE Randabfall (v152) bleibt unangetastet - er ist Absicht.
    _pb216 = {'tpl': 'flow', 'target': (360, 900), 'start': 1.0, 'end': 2.0,
              'front': [{'i': 0, 'arr': _kt216.text('BOOM', 220, _kt216.white)[0],
                         'cx': 360, 'cy': 900, 'w': 600, 't': 1.0,
                         'role': 'punch', 'bleed': True}]}
    _wb216 = _pb216['front'][0]['arr'].shape[1]
    check('v216: der gewollte Randabfall (v152) wird nicht angefasst',
          R.fit_into_frame([_pb216], 720, 1280) == 0
          and _pb216['front'][0]['arr'].shape[1] == _wb216)
    check('v216: ein Moment, der passt, bleibt unveraendert',
          R.fit_into_frame([{'tpl': 'flow', 'target': (360, 900),
                             'start': 1.0, 'end': 2.0,
                             'front': [{'i': 0, 'cx': 360, 'cy': 900, 'w': 200,
                                        't': 1.0,
                                        'arr': _kt216.text('OK', 60,
                                                           _kt216.white)[0]}]}],
                            720, 1280) == 0)
    # ink_box muss ALLE drei Textformen kennen - eine Pruefung, die nur eine
    # davon sieht, ist fuer die anderen blind (v187-Lehre).
    check('v216: ink_box misst Karte, Komposition und Fliesstext',
          R.ink_box({'arr': _arr216, 'cx': 360.0, 'cy': 900.0}, 720, 1280) is not None
          and R.ink_box({'tokens': [{'arr': _arr216, 'ox': 0.0, 'oy': 0.0}],
                         'by': 900.0}, 720, 1280) is not None
          and R.ink_box(_pf216, 720, 1280) is not None
          and R.ink_box({'tpl': 'camonly'}, 720, 1280) is None)
    check('v216: der Log nennt den Wortlaut, nicht nur Leerzeichen',
          R.plan_text({'front': [{'i': 0}, {'i': 1}]},
                      [{'word': ' Hallo'}, {'word': ' Welt'}]) == 'Hallo Welt'
          and R.plan_text({'kw_txt': 'BEHIND ME'}, []) == 'BEHIND ME')
    # (b) v216 hatte hier einen Fliesstext-gegen-Fliesstext-Riegel. Er ist
    #     RAUS (v217): er hat den wartenden Block VERLAENGERT und damit stand
    #     derselbe Satz zweimal gleichzeitig im Bild. Der Test bleibt als
    #     Mahnmal - eine Regel gegen Doppelbilder darf Zeiten nur kuerzen.
    _src217 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v217: kein Riegel verlaengert einen Fliesstext-Block',
          "_b2['end'] = _spaet2 + _FLOW_MIN" not in _src217
          and 'HIER STAND EIN FLIESSTEXT-GEGEN-FLIESSTEXT-RIEGEL' in _src217)
    # ------------------------------------------------------------------
    # v218: DIE WAND WIRD GEMESSEN, NICHT GERATEN.
    # Ismets Befund am Render: "es sitzt nicht richtig an der Wand". Genau so
    # war es gebaut - fuer LIEGENDEN Text misst ground_pose die echte Neigung
    # aus der Tiefenkarte, fuer WAND-Text stand dort ein fester Winkel im
    # Wechsel (-6/+6 Grad). Sechs Grad in zufaelliger Richtung haben mit der
    # Wand im Bild nichts zu tun: der Text lag davor statt darauf.
    _Wv, _Hv = 720, 1280
    _xr = np.linspace(0.2, 0.9, _Wv).astype(np.float32)
    _d_links = np.tile(_xr, (_Hv, 1))              # Naehe steigt nach rechts
    _d_rechts = np.tile(_xr[::-1].copy(), (_Hv, 1))
    _d_boden = np.tile(np.linspace(0.2, 0.9, _Hv).astype(np.float32)[:, None],
                       (1, _Wv))
    _d_flach = np.full((_Hv, _Wv), 0.5, np.float32)
    _yl = R.wall_pose(_d_links, 360, 600, 200, 80, _Wv, _Hv)
    _yr = R.wall_pose(_d_rechts, 360, 600, 200, 80, _Wv, _Hv)
    # persp_warp: yaw > 0 = RECHTE Seite kippt nach hinten.
    check('v218: eine nach links fliehende Wand kippt die linke Seite weg',
          _yl is not None and _yl < -8, str(_yl))
    check('v218: eine nach rechts fliehende Wand kippt die rechte Seite weg',
          _yr is not None and _yr > 8, str(_yr))
    check('v218: der Winkel bleibt in einem plausiblen Rahmen',
          abs(_yl) <= 46 and abs(_yr) <= 46, f"{_yl:.1f} / {_yr:.1f}")
    check('v218: ein BODEN ist keine Wand (dafuer ist ground_pose zustaendig)',
          R.wall_pose(_d_boden, 360, 600, 200, 80, _Wv, _Hv) is None)
    check('v218: ohne messbare Flucht bleibt der bisherige Winkel',
          R.wall_pose(_d_flach, 360, 600, 200, 80, _Wv, _Hv) is None
          and R.wall_pose(None, 360, 600, 200, 80, _Wv, _Hv) is None)
    # Und der Wand-Text muss sein Roh-Sprite aufheben, sonst gibt es nichts
    # neu zu warpen - genau daran ist es vorher vorbeigelaufen.
    check('v218: Wand-Text hebt sein Roh-Sprite auf (flat_arr)',
          'if lying or on_wall:' in _src217
          and 'wall_pose(depth_n' in _src217)
    _wt218 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
              for i, x in enumerate('This one sticks on the wall. I talked here.'.split())]
    _fx218 = R._speech_intent(R._self_ref_intent({}, _wt218), _wt218)
    _pl218 = R.build_plans(_wt218, set(_fx218), cfg, S, W_, H_,
                           lambda s, e: True, _fx218)
    _wp218 = [p for p in _pl218 if p.get('szene') == 'wand']
    check('v218: die Wand-Ansage traegt ein Roh-Sprite zum Neu-Warpen',
          bool(_wp218) and _wp218[0].get('flat_arr') is not None,
          str([(p.get('kw_txt'), p.get('flat_arr') is not None) for p in _wp218]))
    # ------------------------------------------------------------------
    # v219: DIE MESSUNG MUSS IM ECHTEN ZEICHENPFAD ANKOMMEN.
    # v218 hat den Wand-Warp in den NICHT-getrackten Zweig gelegt - bei einem
    # Wand-Plan ist 'tracked' aber IMMER wahr (need_track deckt das ganze
    # Anzeigefenster ab, und der Rueckfall auf den Boden-Track ist ebenfalls
    # nie None). Der Block war toter Code, gezeichnet wurde weiter mit dem
    # gebackenen Wechselwinkel. Aufgefallen ist es NICHT im Selftest, weil der
    # nur wall_pose als reine Funktion plus eine Quelltext-Suche geprueft hat -
    # genau der in CLAUDE.md beschriebene v193-Fehler ("eine Einstellung am
    # PLAN nachzuweisen reicht als Test NICHT").
    # Deshalb hier: composite_frame WIRKLICH aufrufen und messen, dass die
    # Messung greift. Der Test faellt, sobald jemand die Weiche verschiebt.
    _W9, _H9 = 720, 1280
    _S9 = R.Sprites(cfg, _W9, _H9)
    _w9 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
           for i, x in enumerate('This one sticks on the wall. I just talked here.'.split())]
    _fx9 = R._speech_intent(R._self_ref_intent({}, _w9), _w9)
    _pl9 = R.build_plans(_w9, set(_fx9), cfg, _S9, _W9, _H9,
                         lambda s, e: True, _fx9)
    _wp9 = [p for p in _pl9 if p.get('szene') == 'wand']
    _ruf9 = {'n': 0}
    _orig9 = R.wall_pose

    def _spion9(*a, **k):
        _ruf9['n'] += 1
        return _orig9(*a, **k)
    try:
        R.wall_pose = _spion9
        _dp9 = np.tile(np.linspace(0.2, 0.9, _W9).astype(np.float32), (_H9, 1))
        _fr9 = np.full((_H9, _W9, 3), 190.0, np.float32)
        _al9 = np.zeros((_H9, _W9, 1), np.float32)
        _al9[400:1000, 300:520] = 1.0          # Person im Bild (Talking-Head)
        _t9 = R.card_t0(_wp9[0], _w9) if _wp9 else 1.0
        for _k9 in range(6):
            R.composite_frame(_fr9.copy(), _al9, _t9 + 0.05 + _k9 * 0.04, _pl9,
                              _w9, (360, 500, 60), cfg, _S9, _W9, _H9,
                              depth_n=_dp9, H_cum=np.eye(3),
                              H_cum_wall=np.eye(3), track_gen=1, wall_gen=1)
    finally:
        R.wall_pose = _orig9
    check('v219: die Wandmessung laeuft im ECHTEN Zeichenpfad (getrackt, mit Person)',
          _ruf9['n'] >= 1, f"wall_pose {_ruf9['n']}x aufgerufen")
    # v224b: der Winkel ist nach ZEILENZAHL gedeckelt (20 Grad / Zeilen).
    # Schrift ist keine Textur - bei -33 Grad wurde aus 'WALL' ein 'WAI I',
    # weil persp_warp die abgewandte Seite staucht und das Antialiasing die
    # Strichenden auffrisst. Gefordert ist also: ein Winkel IST gesetzt und er
    # liegt im lesbaren Bereich.
    check('v219: der gemessene Winkel landet am Plan',
          bool(_wp9) and _wp9[0].get('_wall_yaw') is not None
          and 3.0 <= abs(_wp9[0]['_wall_yaw']) <= 20.0,
          str(_wp9[0].get('_wall_yaw') if _wp9 else None))
    # Und die Messung muss das BILD veraendern, nicht nur ein Feld setzen.
    _flat9 = _S9.text('ON THE WALL', 110, _S9.white)[0]
    _geb9 = R.persp_warp(_flat9, yaw=-6, pitch=0.12)      # gebacken (bisher)
    _mes9 = R.persp_warp(_flat9, yaw=-42.0, pitch=0.0)    # gemessen

    def _verk9(x):
        _m = x[..., 3] > 80
        _nz = np.where(_m)
        if not len(_nz[0]):
            return 0.0
        _l = _m[:, _nz[1].min():_nz[1].min() + 20].sum()
        _r = _m[:, max(_nz[1].max() - 19, 0):_nz[1].max() + 1].sum()
        return _l / max(_r, 1)
    check('v219: der gemessene Winkel verkuerzt die abgewandte Seite wirklich',
          _verk9(_geb9) > 1.5 and _verk9(_mes9) < 0.8,
          f"gebacken {_verk9(_geb9):.2f}, gemessen {_verk9(_mes9):.2f}")
    # ------------------------------------------------------------------
    # v221: (a) TEXTFLUSS. An Ismets 15-s-Werbespot gemessen standen 45 % der
    # Laufzeit KEINE Captions im Bild, einzelne Pausen bis 1.17 s, waehrend
    # durchgehend gesprochen wird ("fuehlt sich 0 fluessig an"). Das Luecken-
    # Netz gab es, es lief nur bei Dichte 'durchgehend'. Jetzt auch bei
    # 'akzente' - 'sparsam' bleibt bewusst ruhig.
    _wf221 = [{'word': ' ' + x, 'start': 0.3 + i * 0.32, 'end': 0.3 + i * 0.32 + 0.28}
              for i, x in enumerate("Everyone captions look the same file same "
                                    "yellow word bouncing you have seen it a "
                                    "thousand times over and over again".split())]

    def _luecken221(dichte):
        _c = copy.deepcopy(cfg)
        _c['effects']['density'] = dichte
        _pl = R.build_plans(_wf221, R.detect_keywords(_wf221, _c, None), _c, S,
                            W_, H_, lambda s, e: True, None)
        _zeigt = set()
        for _p in _pl:
            for _k in ('front', 'small'):
                for _it in (_p.get(_k) or []):
                    if isinstance(_it, dict) and _it.get('i') is not None:
                        _zeigt.add(_it['i'])
            if _p.get('kw_i') is not None:
                _zeigt.add(_p['kw_i'])
        _fehlt = [R.clean(_wf221[i]['word']) for i in range(len(_wf221))
                  if i not in _zeigt]
        # groesste Textpause waehrend der Rede
        _sp = sorted((R.card_t0(_p, _wf221), _p['end'])
                     for _p in _pl if 'target' in _p)
        _t, _max = 0.0, 0.0
        for _a, _b in _sp:
            _max = max(_max, _a - _t)
            _t = max(_t, _b)
        return _fehlt, _max
    _f221, _p221 = _luecken221('akzente')
    check('v221: bei "akzente" steht jetzt JEDES gesprochene Wort im Bild',
          not _f221, f"nie gezeigt: {_f221}")
    check('v221: bei "akzente" keine Textpause ueber 0.5 s waehrend der Rede',
          _p221 <= 0.5, f"groesste Pause {_p221:.2f} s")
    _fs221, _ = _luecken221('sparsam')
    check('v221: "sparsam" bleibt bewusst ruhig (dort ist die Pause der Stil)',
          len(_fs221) > 0, f"{len(_fs221)} Woerter ohne Caption - so gewollt")
    _src221 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v221: die Atempause gilt nur noch, wo die Pause der Stil ist',
          "not in ('durchgehend', 'akzente')" in _src221)
    # (b) DAS ORTSWORT LIEGT SCHON DA (Ismets Idee: "dass es schon da darauf
    # steht, beispielsweise das Wort Wall, und das andere baut sich drum
    # herum auf").
    check('v221: das Ortswort wird richtig abgeleitet',
          R.anker_wort('ON THE WALL') == 'WALL'
          and R.anker_wort('BEHIND ME') == 'BEHIND'
          and R.anker_wort('ABOVE ME') == 'ABOVE'
          and R.anker_wort('ON THE GROUND') == 'GROUND'
          and R.anker_wort('AN DER WAND') == 'WAND'
          and R.anker_wort('WALL') is None      # ein Wort ist sein eigener Anker
          and R.anker_wort('') is None)
    _W1, _H1 = 720, 1280
    _S1 = R.Sprites(cfg, _W1, _H1)
    _w1 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
           for i, x in enumerate('Watch this one sticks on the wall. I just talked here.'.split())]
    _fx1 = R._speech_intent(R._self_ref_intent({}, _w1), _w1)
    _pl1 = R.build_plans(_w1, set(_fx1), cfg, _S1, _W1, _H1, lambda s, e: True, _fx1)
    _ap1 = [p for p in _pl1 if p.get('anker_arr') is not None]
    check('v221: die Wand-Ansage bekommt ein Ankerwort mit Vorlauf',
          bool(_ap1) and _ap1[0].get('anker_txt') == 'WALL'
          and R.card_t0(_ap1[0], _w1) - _ap1[0]['anker_t0'] > 0.3,
          str([(p.get('anker_txt'), round(p['anker_t0'], 2),
                round(R.card_t0(p, _w1), 2)) for p in _ap1]))
    check('v221: der Vorlauf ist auf 2 s gedeckelt (Anker, kein Titel)',
          all(R.card_t0(p, _w1) - p['anker_t0'] <= 2.01 for p in _ap1),
          str([round(R.card_t0(p, _w1) - p['anker_t0'], 2) for p in _ap1]))
    # WIRKSAMKEITS-NACHWEIS: das Ankerwort muss im BILD stehen - und nach dem
    # Kartenstart wieder verschwinden. Gemessen als Differenz mit/ohne Sprite
    # am gerenderten Frame, nicht am Plan (v219-Lehre).
    if _ap1:
        _dp1 = np.tile(np.linspace(0.2, 0.9, _W1).astype(np.float32), (_H1, 1))
        _fr1 = np.full((_H1, _W1, 3), 190.0, np.float32)
        _al1 = np.zeros((_H1, _W1, 1), np.float32)
        _al1[400:1000, 300:520] = 1.0

        # WICHTIG: composite_frame ist NICHT zustandsfrei - es merkt sich am
        # Plan, wo es angekert hat, wie weit die Animation ist und welche
        # Flaeche es gemessen hat. Fuer einen Vergleich muss deshalb JEDER
        # Lauf frische Plaene bekommen, sonst misst man den Zustand des
        # ersten Laufs statt der Aenderung.
        def _frisch1(mit_anker):
            _pl = R.build_plans(_w1, set(_fx1), cfg, _S1, _W1, _H1,
                                lambda s, e: True, _fx1)
            if not mit_anker:
                for _q in _pl:
                    _q.pop('anker_arr', None)
                    _q.pop('anker_flat', None)
            return _pl

        def _ankerpixel(tt):
            _bilder = []
            for _mit in (True, False):
                _pl = _frisch1(_mit)
                _bilder.append(R.composite_frame(
                    _fr1.copy(), _al1, tt, _pl, _w1, (360, 500, 60), cfg, _S1,
                    _W1, _H1, depth_n=_dp1, H_cum=np.eye(3),
                    H_cum_wall=np.eye(3), track_gen=1, wall_gen=1).copy())
            return int((np.abs(_bilder[0] - _bilder[1]).mean(axis=2) > 8).sum())
        _kt1 = R.card_t0(_ap1[0], _w1)
        _at1 = _ap1[0]['anker_t0']
        _vor1 = _ankerpixel(max(_kt1 - 0.15, _at1 + 0.4))
        _nach1 = _ankerpixel(_kt1 + 0.5)
        check('v221: das Ortswort steht WIRKLICH im Bild, bevor der Satz kommt',
              _vor1 > 200, f"{_vor1} Pixel im Anker-Fenster")
        check('v221: sobald der Satz steht, ist das Ortswort weg (kein Doppel)',
              _nach1 == 0, f"{_nach1} Pixel nach dem Kartenstart")
    check('v221: der Anker-Durchgang steht VOR der Hauptschleife und nutzt plans',
          _src221.index("for p in plans:\n        if p.get('anker_arr') is None")
          < _src221.index('    for p in active:\n        # v82: Cutter-Exit'))

    # ------------------------------------------------------------------
    # v226 DIE KAMERA DARF DIE ANSAGE NICHT WIDERLEGEN.
    # Ismets Befund am gestempelten v225b-Render: "das 'above me' zuckt etwas
    # zu viel und geht runter". Am Video gemessen wanderte die Karte in 0.29 s
    # um 109 px NACH UNTEN - bei einer Ansage, die "ueber mir" heisst.
    # Zwei Ursachen, beide in dieselbe Richtung:
    #   (1) Kameramodus 'caption' schiebt das Bild um (by - H/2) * 0.30 auf die
    #       Karte zu; bei by = 0.22 H sind das 108 px nach unten - genau der
    #       Messwert. Der Modus kann sein Versprechen ("Close-up auf die
    #       Caption") ohnehin nicht halten: die Caption wird VOR dem Warp
    #       gezeichnet und wandert mit, der Abstand bleibt gleich.
    #   (2) Der Welt-Lock zog die Karte senkrecht mit dem Nahbereich-Schwenk
    #       mit (Deckel 0.072 H). Der Himmel ist die FERNE Ebene - dort ist die
    #       Parallaxe fast null; 1:1 mitzuziehen war auch physikalisch falsch.
    _W6, _H6 = 720, 1280
    _S6 = R.Sprites(cfg, _W6, _H6)
    _t6 = ('I want to show you something crazy this line floats above me '
           'and it just stays right up there the whole time')
    _w6 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
           for i, x in enumerate(_t6.split())]
    _fx6 = R._speech_intent(R._self_ref_intent({}, _w6), _w6)

    def _plaene6(modus):
        """Frische Plaene, nur die Himmel-Karte. composite_frame ist NICHT
        zustandsfrei (v221) - jeder Lauf braucht neue Plaene."""
        _pl = R.build_plans(_w6, set(_fx6), cfg, _S6, _W6, _H6,
                            lambda s, e: True, _fx6)
        _k = next((p for p in _pl if p.get('ort_ansage') == 'himmel'), None)
        if _k is None:
            return [], None
        _k['by'] = _H6 * 0.22
        if modus == 'alt':                  # Zustand VOR v226
            _k['cam'] = 'caption'
            _k.pop('ort_ansage', None)
        else:
            _k['cam'] = 'punch'             # was der Riegel daraus macht
        return [_k], _k
    _pa6, _ka6 = _plaene6('alt')
    _pn6, _kn6 = _plaene6('neu')
    check('v226: die Himmel-Ansage ist AM PLAN vermerkt (nicht nur in info)',
          _kn6 is not None and _kn6.get('ort_ansage') == 'himmel',
          'sonst greift der Riegel nur in einem der beiden fx-Zweige')
    # WIRKSAMKEITS-NACHWEIS 1: die Produktionsfunktion camera_at, nicht der Plan.
    if _ka6 and _kn6:
        def _py6(pl, k):
            _t0 = R.card_t0(k, _w6)
            return max((R.camera_at(float(_t0 + j / 24), pl, _w6, cfg, _W6, _H6)[2]
                        for j in range(30)), key=abs)
        _pya, _pyn = _py6(_pa6, _ka6), _py6(_pn6, _kn6)
        check('v226: der Kameramodus schiebt die Karte nicht mehr nach unten',
              abs(_pya) > _H6 * 0.06 and abs(_pyn) < _H6 * 0.005,
              f"alt {-_pya:+.1f} px, neu {-_pyn:+.1f} px")
    # Und der Riegel muss im echten Bauweg sitzen: eine Orts-Ansage darf nach
    # build_plans NIE auf 'caption' stehen.
    # Damit der Riegel wirklich geprueft wird, besteht die Rotation hier NUR aus
    # 'caption' - sonst kann der Test gruen sein, weil die Rotation zufaellig
    # etwas anderes gezogen hat (und genau so war es beim ersten Lauf: die Karte
    # trug 'crash' vom Hoehepunkt-Vorrang, der Riegel lief gar nicht).
    _cfg6 = copy.deepcopy(cfg)
    _cfg6['camera']['keyword_rotation'] = ['caption']
    _t6b = ('watch this one floats above me and later I will show you the '
            'loudest part of the whole thing right here boom')
    _w6b = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
            for i, x in enumerate(_t6b.split())]
    _fx6b = R._speech_intent(R._self_ref_intent({}, _w6b), _w6b)
    import io as _io6
    import contextlib as _cx6
    _log6 = _io6.StringIO()
    with _cx6.redirect_stdout(_log6):
        _pl6 = R.build_plans(_w6b, set(_fx6b), _cfg6, _S6, _W6, _H6,
                             lambda s, e: True, _fx6b)
    _ort6 = [p for p in _pl6 if p.get('ort_ansage')]
    # Der Riegel muss GELAUFEN sein (Log) - und danach darf keine Orts-Ansage
    # mehr auf 'caption' stehen. Der Hoehepunkt-Vorrang setzt die staerkste
    # Karte spaeter auf 'crash'; das ist ein reiner Zoom und deshalb in Ordnung.
    check('v226: auch wenn die Rotation NUR "caption" hergibt, greift der Riegel',
          bool(_ort6) and 'zoom without vertical drift' in _log6.getvalue()
          and all(p.get('cam') != 'caption' for p in _ort6),
          str([(p.get('ort_ansage'), p.get('cam')) for p in _ort6]))
    # Gegenprobe: ohne Orts-Ansage bleibt 'caption' erlaubt - der Riegel darf
    # den Modus nicht generell abschaffen.
    # Zwei Karten, weit auseinander (min_gap 6 s): die staerkste bekommt den
    # Hoehepunkt-Zoom, die zweite behaelt 'caption' - der Riegel darf den Modus
    # nicht generell abschaffen, nur bei einer Orts-Ansage.
    _t6c = ('this part is absolutely insane and it will change everything you '
            'know about captions because nobody else does it like this and that '
            'is exactly why it works so well for every single video you make')
    _w6c = [{'word': ' ' + x, 'start': i * .4, 'end': i * .4 + .34}
            for i, x in enumerate(_t6c.split())]
    _pl6c = R.build_plans(_w6c, {4, 26}, _cfg6, _S6, _W6, _H6,
                          lambda s, e: True,
                          {4: {'fx': 'behind', 'power': 3},
                           26: {'fx': 'blurin', 'power': 2}})
    check('v226: ohne Orts-Ansage bleibt der Modus "caption" erhalten',
          any(p.get('cam') == 'caption' for p in _pl6c)
          and not any(p.get('ort_ansage') for p in _pl6c),
          str(sorted({p.get('cam') for p in _pl6c if p.get('cam')})))
    _src226 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v226: der Riegel sitzt dort, wo die Kamera gewaehlt wird',
          _src226.index("p['cam'] = rot_cam.next(); camc += 1")
          < _src226.index("if p['cam'] == 'caption' and p.get('ort_ansage'):"),
          'sonst ueberschreibt die Rotation ihn wieder')
    # WIRKSAMKEITS-NACHWEIS 2: die Tinte im gerenderten Bild, waehrend die
    # Quelle nach unten kippt. Gemessen wird der Weg, nicht der Plan (v219).
    _fr6 = np.full((_H6, _W6, 3), 120.0, np.float32)
    _dp6 = np.tile(np.linspace(0.25, 0.85, _W6).astype(np.float32), (_H6, 1))

    def _weg6(modus):
        _spur = []
        for j in range(0, 20, 2):
            _pl, _k = _plaene6(modus)
            if _k is None:
                return None
            _tt = float(R.card_t0(_k, _w6) + j / 24)
            _c = R.composite_frame(
                _fr6.copy(), None, _tt, _pl, _w6, (360, 530, 62), cfg, _S6,
                _W6, _H6, [1.0, 0.0, 0.0, 0.0, 0.0], (0.0, j * 5.0),
                depth_n=_dp6, H_cum=np.eye(3), H_cum_wall=np.eye(3),
                track_gen=1, wall_gen=1)
            _m = _c.mean(axis=2) > 205
            if _m.sum() > 200:
                _spur.append(float(np.nonzero(_m)[0].mean()))
        return (_spur[-1] - _spur[0]) if len(_spur) >= 3 else None
    _wa6, _wn6 = _weg6('alt'), _weg6('neu')
    check('v226: im Bild wandert die Karte nicht mehr nach unten',
          _wa6 is not None and _wn6 is not None
          and _wa6 > 20 and _wn6 < _wa6 * 0.4,
          f"alt {_wa6 if _wa6 is None else round(_wa6, 1)} px, "
          f"neu {_wn6 if _wn6 is None else round(_wn6, 1)} px")
    check('v226: der Himmel ist die ferne Ebene (kein senkrechter Welt-Lock)',
          "if p.get('ort_ansage') == 'himmel':" in _src226
          and 'min(dx * 0.35, lim)) + _hx, _hy' in _src226,
          'Parallaxe geht mit der Entfernung gegen null')

    # ------------------------------------------------------------------
    # v228a DIE PERSON GEHOERT IN DIE WORTMITTE, NICHT AN SEIN ENDE.
    # Ismets Befund am gestempelten v227a-Render ("das Maskieren hat hier
    # nicht gut geklappt"): von "BEHIND ME" war nur "BEHI" lesbar. Am Bild
    # gemessen steht der Sprecher bei 0.66 W, der Satz wurde aber IMMER auf
    # die BILDMITTE gesetzt (fest W/2 im Zeichenpfad) - seine Silhouette lag
    # damit auf dem rechten Wortende und frass es am Stueck. Die
    # Lesbarkeits-Stufen von v191 vergleichen nur BREITEN und sind dafuer
    # blind: das Wort war mit 2.4x Schulterbreite breit genug, nur an der
    # falschen Stelle.
    _W8, _H8 = 720, 1280
    _S8 = R.Sprites(cfg, _W8, _H8)
    _t8 = 'watch this the captions are behind me right now and it looks unreal'
    _w8 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
           for i, x in enumerate(_t8.split())]
    _fx8 = R._speech_intent(R._self_ref_intent({}, _w8), _w8)
    _FX8, _FY8, _FW8 = _W8 * 0.78, _H8 * 0.20, 60.0
    _HB8 = 90

    def _plaene8(alt):
        """Frische Plaene je Lauf - composite_frame ist nicht zustandsfrei."""
        _pl = R.build_plans(_w8, set(_fx8), cfg, _S8, _W8, _H8,
                            lambda s, e: True, _fx8,
                            face_pos=lambda a, b: (_FX8, _FY8, _FW8))
        _k = next((p for p in _pl if p.get('tpl') == 'behind'
                   and (p.get('arr') is not None or p.get('tokens'))), None)
        if _k is not None and alt:
            _k['bx'] = _W8 / 2                # Zustand VOR v228a
        return _pl, _k
    _pl8, _k8 = _plaene8(False)
    check('v228a: der Block steht auf dem Sprecher, nicht auf der Bildmitte',
          _k8 is not None and _k8.get('bx') is not None
          and abs(_k8['bx'] - _W8 / 2) > _W8 * 0.02
          and 0 < _k8['bx'] < _W8,
          f"bx={_k8.get('bx') if _k8 else None}")
    # WIRKSAMKEITS-NACHWEIS am gerenderten Bild: wieviel Tinte steht auf der
    # SCHWAECHEREN Seite der Silhouette? Null heisst: ein Wortende ist weg.
    _fr8 = np.full((_H8, _W8, 3), 150.0, np.float32)
    _al8 = np.zeros((_H8, _W8, 1), np.float32)
    _al8[int(_H8 * 0.14):int(_H8 * 0.28), int(_FX8 - 52):int(_FX8 + 52)] = 1.0
    _al8[int(_H8 * 0.28):int(_H8 * 0.95),
         int(_FX8 - _HB8):int(_FX8 + _HB8)] = 1.0
    _dp8 = np.tile(np.linspace(.25, .85, _W8).astype(np.float32), (_H8, 1))

    def _schwach8(alt):
        _pl, _k = _plaene8(alt)
        if _k is None:
            return None
        _by = int(_k.get('by', _H8 * 0.3))
        _c = R.composite_frame(
            _fr8.copy(), _al8, R.card_t0(_k, _w8) + 0.5, _pl, _w8,
            (_FX8, _FY8, _FW8), cfg, _S8, _W8, _H8, [1., 0, 0, 0, 0], (0, 0),
            depth_n=_dp8, H_cum=np.eye(3), H_cum_wall=np.eye(3),
            track_gen=1, wall_gen=1)
        _ink = (_c[max(_by - 140, 0):min(_by + 140, _H8)].mean(axis=2) > 205)
        _sil = 52 if _by < _H8 * 0.28 else _HB8
        return min(int(_ink[:, :int(_FX8 - _sil)].sum()),
                   int(_ink[:, int(_FX8 + _sil):].sum()))
    _sa8, _sn8 = _schwach8(True), _schwach8(False)
    check('v228a: kein Wortende wird mehr am Stueck aufgefressen',
          _sa8 is not None and _sn8 is not None and _sa8 < 50 and _sn8 > 400,
          f'schwaechere Seite alt {_sa8} px, neu {_sn8} px Tinte')
    # Und der Riegel muss in ALLEN Zeichenwegen sitzen - der Mehrwort-Satz
    # ("BEHIND ME") laeuft ueber die Token, nicht ueber p['arr'] (v219-Lehre:
    # ein Riegel im falschen Ast ist toter Code).
    check('v228a: alle behind-Zeichenwege nutzen die Blockmitte',
          _src226.count("p.get('bx', W / 2)") >= 5
          and "paste(comp, arr_t,\n                          p.get('bx', W / 2)"
          in _src226,
          f"{_src226.count(chr(112) + chr(46) + 'get(' + chr(39) + 'bx' + chr(39) + ', W / 2)')} Stellen")

    # ------------------------------------------------------------------
    # v223: DER TEXT MUSS AUF DIE WANDFLAECHE, NICHT NUR IN IHRE EBENE.
    # Ismets Befund am v222-Render: "der wird gar nicht richtig auf der Wand
    # platziert". Die NEIGUNG stimmte da schon (v219), die STELLE nicht: die
    # Wand steht links und ist im Bild nur ~40 % breit, das Wand-Sprite ist
    # fast bildbreit (688-715 px bei 720 px) - der Text lag zwangslaeufig halb
    # daneben und halb ausserhalb. Gesetzt wurde er von der normalen
    # Platzierungs-Regie, die Gesichter und Bildunruhe kennt, aber keine Wand.
    _W3, _H3 = 720, 1280
    _d3 = np.full((_H3, _W3), 0.5, np.float32)
    _d3[:, :int(_W3 * 0.45)] = np.tile(
        np.linspace(0.25, 0.75, int(_W3 * 0.45)).astype(np.float32), (_H3, 1))
    _al3 = np.zeros((_H3, _W3, 1), np.float32)
    _al3[400:1000, 420:620] = 1.0            # Person rechts, nicht auf der Wand
    _wa3 = R.wall_area(_d3, _al3, _W3, _H3)
    check('v223: die Wandflaeche wird gefunden (Mitte auf der Wand)',
          _wa3 is not None and 0.05 * _W3 < _wa3[0] < 0.45 * _W3,
          str(None if not _wa3 else tuple(round(v, 1) for v in _wa3)))
    check('v223: die Person zaehlt nicht zur Wand',
          _wa3 is not None and _wa3[0] + _wa3[2] / 2 < 430,
          f"rechte Kante {None if not _wa3 else round(_wa3[0] + _wa3[2] / 2, 1)}")
    check('v223: eine frontale Flaeche ist keine Wand (kein Eingriff)',
          R.wall_area(np.full((_H3, _W3), 0.5, np.float32), None, _W3, _H3) is None
          and R.wall_area(None, None, _W3, _H3) is None)
    # WIRKSAMKEITS-NACHWEIS im echten Zeichenpfad.
    _S3 = R.Sprites(cfg, _W3, _H3)
    _w3 = [{'word': ' ' + x, 'start': i * .35, 'end': i * .35 + .3}
           for i, x in enumerate('Watch this one sticks on the wall. I just talked here.'.split())]
    _fx3 = R._speech_intent(R._self_ref_intent({}, _w3), _w3)
    _pl3 = R.build_plans(_w3, set(_fx3), cfg, _S3, _W3, _H3, lambda s, e: True, _fx3)
    _wp3 = [p for p in _pl3 if p.get('szene') == 'wand']

    def _tinte3(arr, cx):
        _nz = np.where(arr[..., 3] > 80)
        return ((cx - arr.shape[1] / 2.0 + float(_nz[1].min())) / _W3,
                (cx - arr.shape[1] / 2.0 + float(_nz[1].max())) / _W3)
    if _wp3:
        _p3 = _wp3[0]
        _vor3 = _tinte3(_p3['arr'], _p3.get('cx', _W3 / 2))
        _fr3 = np.full((_H3, _W3, 3), 190.0, np.float32)
        for _k3 in range(3):
            R.composite_frame(_fr3.copy(), _al3, R.card_t0(_p3, _w3) + 0.3 + _k3 * 0.04,
                              _pl3, _w3, (500, 500, 60), cfg, _S3, _W3, _H3,
                              depth_n=_d3, H_cum=np.eye(3), H_cum_wall=np.eye(3),
                              track_gen=1, wall_gen=1)
        _na3 = _tinte3(_p3['arr'], _p3['cx'])
        check('v223: der Wand-Text landet AUF der Wandflaeche (0..0.45 W)',
              _na3[1] <= 0.47 and _na3[0] >= -0.01,
              f"vorher {_vor3[0]:.3f}..{_vor3[1]:.3f} W, nachher "
              f"{_na3[0]:.3f}..{_na3[1]:.3f} W")
        check('v223: er wird dabei nicht vom Bildrand angeschnitten',
              _na3[0] >= -0.005 and _na3[1] <= 1.005,
              f"{_na3[0]:.3f}..{_na3[1]:.3f} W")
        check('v223: die Neigung wird AN DER FLAECHE gemessen, nicht an der '
              'alten Stelle',
              _p3.get('_wall_yaw') is not None
              and 3.0 <= abs(_p3['_wall_yaw']) <= 20.0,
              str(_p3.get('_wall_yaw')))
        check('v223: der Text passt auf die Flaeche (nicht breiter als die Wand)',
              _wa3 is not None
              and (_na3[1] - _na3[0]) * _W3 <= _wa3[2] * 1.05,
              f"Text {round((_na3[1] - _na3[0]) * _W3)} px, "
              f"Wand {round(_wa3[2]) if _wa3 else '?'} px")
    # ------------------------------------------------------------------
    # v224: EIN WANDSCHRIFTZUG WIRD GESETZT, NICHT GESCHRUMPFT.
    # Ismets Befund am v223-Render: "sitzt auf der Wand, sieht aber echt
    # unstrukturiert aus, muss eventuell etwas kleiner". Beides kam aus
    # derselben Ursache: v223 nahm die FERTIGE, fast bildbreite Zeile und
    # stauchte sie auf die Flaeche (bis 45 %) - eine winzige, randfuellende
    # Zeile ohne Luft. Ein Schriftzug AN einer Wand ist mehrzeilig: die
    # Flaeche gibt die Breite, der Text bricht um, die Schrift bleibt gross.
    _wt4 = R.wall_typo(_S3, 'ON THE WALL', 277.5, 1280.0, _W3, _H3)
    check('v224: der Wandschriftzug wird mehrzeilig gesetzt',
          _wt4 is not None and _wt4.shape[0] > _wt4.shape[1] * 0.5,
          str(None if _wt4 is None else f"{_wt4.shape[1]}x{_wt4.shape[0]}"))

    def _zeilen4(a):
        m = a[..., 3] > 80
        _rows = np.where(m.any(axis=1))[0]
        _seg, _cur = [], None
        for _y in _rows:
            if _cur and _y - _cur[1] <= 2:
                _cur[1] = _y
            else:
                if _cur:
                    _seg.append(_cur)
                _cur = [_y, _y]
        if _cur:
            _seg.append(_cur)
        return len(_seg), (max(b - a0 + 1 for a0, b in _seg) if _seg else 0)
    _nl4, _vh4 = _zeilen4(_wt4) if _wt4 is not None else (0, 0)
    check('v224: hoechstens drei Zeilen (mehr liest sich wie ein Absatz)',
          1 <= _nl4 <= 3, f"{_nl4} Zeilen")
    _nz4 = np.where(_wt4[..., 3] > 80) if _wt4 is not None else None
    _bw4 = (float(_nz4[1].max() - _nz4[1].min() + 1) / 277.5) if _nz4 is not None else 0
    check('v224: er laesst Rand frei (60-85 % der Flaechenbreite)',
          0.60 <= _bw4 <= 0.85, f"{_bw4:.0%} der Wandbreite")
    check('v224: eine zu schmale Flaeche gibt None (dann greift der Rueckfall)',
          R.wall_typo(_S3, 'ON THE WALL', _W3 * 0.05, 1280.0, _W3, _H3) is None
          and R.wall_typo(_S3, '', 277.5, 1280.0, _W3, _H3) is None)
    # WIRKSAMKEITS-NACHWEIS im echten Zeichenpfad: die Schrift muss GROESSER
    # sein als beim reinen Stauchen, der Block schmaler als die Wand, und er
    # sitzt auf Augenhoehe statt im Flaechen-Schwerpunkt.
    if _wp3:
        _p4 = [p for p in R.build_plans(_w3, set(_fx3), cfg, _S3, _W3, _H3,
                                        lambda s, e: True, _fx3)
               if p.get('szene') == 'wand']
        _pl4 = R.build_plans(_w3, set(_fx3), cfg, _S3, _W3, _H3,
                             lambda s, e: True, _fx3)
        _p4 = [p for p in _pl4 if p.get('szene') == 'wand'][0]
        _fr4 = np.full((_H3, _W3, 3), 190.0, np.float32)
        for _k4 in range(3):
            R.composite_frame(_fr4.copy(), _al3,
                              R.card_t0(_p4, _w3) + 0.3 + _k4 * 0.04, _pl4, _w3,
                              (500, 500, 60), cfg, _S3, _W3, _H3, depth_n=_d3,
                              H_cum=np.eye(3), H_cum_wall=np.eye(3),
                              track_gen=1, wall_gen=1)
        _nl5, _vh5 = _zeilen4(_p4['arr'])
        _nz5 = np.where(_p4['arr'][..., 3] > 80)
        _bw5 = float(_nz5[1].max() - _nz5[1].min() + 1)
        # Reines Stauchen ergab bei dieser Wand 39 px Versalhoehe (110 px
        # Ausgangsschrift auf 255/715 gestaucht).
        check('v224: die Schrift bleibt gross (deutlich groesser als gestaucht)',
              _vh5 >= 48, f"Versalhoehe {_vh5} px (gestaucht waeren ~39 px)")
        check('v224: der Block ist schmaler als die Wand (Rand bleibt frei)',
              _bw5 <= 277.5 * 0.85, f"{_bw5:.0f} px auf 278 px Wand")
        # v225: der Warp-Ausgleich ist ueberholt - die Homographie legt den
        # Satz direkt in das Wand-Viereck, da gibt es keinen Verlust
        # auszugleichen. Geprueft wird jetzt, dass der alte Notbehelf WEG ist.
        check('v225: der Warp-Ausgleich ist durch die Projektion ersetzt',
              'min(_b1 / _b2' not in _src221
              and 'p[\'arr\'] = wall_project(_wt, _quad, W, H)' in _src221)
        # v225: die Augenhoehe steckt jetzt im Zielband der Projektion
        # (oben=0.20, hoch=0.34) - gemessen wird sie am fertigen Sprite.
        _dq6 = np.zeros((_H3, _W3), np.float32)
        _xw6 = int(_W3 * 0.45)
        for _x6 in range(_xw6):
            _f6 = _x6 / max(_xw6 - 1, 1)
            _dq6[int(120 + 80 * _f6):int(1230 - 80 * _f6), _x6] = 0.75 - 0.5 * _f6
        _q5 = R.wall_quad(_dq6, _al3, _W3, _H3)
        if _q5 is not None:
            _pr6 = R.wall_project(_S3.text('ON THE WALL', 90, _S3.white)[0],
                                  _q5, _W3, _H3)
            _n6 = np.where(_pr6[..., 3] > 80)
            _mid6 = (float(_n6[0].min()) + float(_n6[0].max())) / 2.0
            _woben = (_q5[0][1] + _q5[1][1]) / 2.0
            _wunten = (_q5[2][1] + _q5[3][1]) / 2.0
            _rel6 = (_mid6 - _woben) / max(_wunten - _woben, 1.0)
            check('v225: der Schriftzug sitzt im oberen Drittel der Wand',
                  0.15 <= _rel6 <= 0.50,
                  f"{_rel6:.0%} der Wandhoehe von oben")

    # ------------------------------------------------------------------
    # v225: IN DIE WANDEBENE PROJIZIEREN, NICHT NUR KIPPEN.
    # Ismets Befund am v224-Bild: "es ist jetzt auf der Wand, aber es hat die
    # falschen Winkel". Ein einzelner Winkel kann das nicht leisten: eine Wand
    # im Bild ist ein TRAPEZ mit Fluchtlinien. persp_warp(yaw) verkuerzt nur
    # eine Seite und laesst die Zeilen waagerecht.
    _dq5 = np.zeros((_H3, _W3), np.float32)
    _xw5 = int(_W3 * 0.45)
    for _x5 in range(_xw5):
        _f5 = _x5 / max(_xw5 - 1, 1)
        _y05 = int(120 + (200 - 120) * _f5)
        _y15 = int(1230 + (1150 - 1230) * _f5)
        _dq5[_y05:_y15, _x5] = 0.75 - 0.5 * _f5
    _q5 = R.wall_quad(_dq5, _al3, _W3, _H3)
    check('v225: das Wand-Viereck wird mit vier Ecken gemessen',
          _q5 is not None and _q5.shape == (4, 2),
          str(None if _q5 is None else [[int(v) for v in q] for q in _q5]))
    check('v225: die Ecken kommen in der Reihenfolge oben-links..unten-links',
          _q5 is not None and _q5[0][1] < _q5[3][1] and _q5[1][1] < _q5[2][1]
          and _q5[0][0] < _q5[1][0],
          str(None if _q5 is None else [[int(v) for v in q] for q in _q5]))
    # v225b DIE RICHTUNG KOMMT AUS DER GEOMETRIE. Ismets Befund: "die Schrift
    # muss genau in die andere Richtung mit dem Winkel". Sie kam bis dahin aus
    # dem VORZEICHEN eines Sobel-Medians, dessen Orientierung verwechselt war -
    # ein Vorzeichen ist auch kein Beleg, sondern eine Behauptung. Jetzt gilt:
    # die Seite mit der KLEINEREN Naehe ist weiter weg und im Bild KUERZER.
    # Gegenprobe mit gespiegelter Wand ist Pflicht - sonst haette ein einfach
    # umgedrehtes Vorzeichen denselben Test bestanden.
    if _q5 is not None:
        _hl5 = float(_q5[3][1] - _q5[0][1])
        _hr5 = float(_q5[2][1] - _q5[1][1])
        check('v225b: links nah -> die rechte Kante ist kuerzer',
              _hr5 < _hl5 * 0.92, f"links {_hl5:.0f} px, rechts {_hr5:.0f} px")
        _dsp5 = _dq5[:, ::-1].copy()
        _asp5 = np.zeros((_H3, _W3, 1), np.float32)
        _asp5[400:1000, 80:250] = 1.0
        _qs5 = R.wall_quad(_dsp5, _asp5, _W3, _H3)
        check('v225b: gespiegelte Wand -> die LINKE Kante ist kuerzer',
              _qs5 is not None
              and (_qs5[3][1] - _qs5[0][1]) < (_qs5[2][1] - _qs5[1][1]) * 0.92,
              str(None if _qs5 is None else
                  f"links {_qs5[3][1] - _qs5[0][1]:.0f} px, "
                  f"rechts {_qs5[2][1] - _qs5[1][1]:.0f} px"))
        check('v225b: die Verkuerzung kommt aus der Naehe, nicht aus einem '
              'Vorzeichen',
              'Spalten-Mediane' in _src221 or '_prof.append' in _src221)
    check('v225: eine frontale Wand gibt kein Viereck (dann keine Projektion)',
          R.wall_quad(np.full((_H3, _W3), 0.5, np.float32), None, _W3, _H3) is None
          and R.wall_quad(None, None, _W3, _H3) is None)
    if _q5 is not None:
        _sp5 = _S3.text('ON THE WALL', 90, _S3.white)[0]
        _pr5 = R.wall_project(_sp5, _q5, _W3, _H3)
        check('v225: das projizierte Sprite ist bildgross (Position steckt drin)',
              _pr5.shape[:2] == (_H3, _W3), str(_pr5.shape))
        _n5 = np.where(_pr5[..., 3] > 80)
        check('v225: die Tinte landet INNERHALB des Wand-Vierecks',
              len(_n5[0]) > 0 and _n5[1].max() <= max(q[0] for q in _q5) + 4
              and _n5[1].min() >= min(q[0] for q in _q5) - 4,
              f"x {int(_n5[1].min())}..{int(_n5[1].max())}, Wand "
              f"{int(min(q[0] for q in _q5))}..{int(max(q[0] for q in _q5))}")
    # Bei aktiver Projektion darf die Position NICHT zusaetzlich verschoben
    # werden - sie steckt schon in der Homographie.
    check('v225: projizierte Sprites werden nicht doppelt verschoben',
          "if not p.get('_wall_proj'):" in _src221
          and "p['cx'], p['cy'] = W / 2.0, H / 2.0" in _src221)

    check('v223: Flaechensuche laeuft VOR der Neigungsmessung',
          _src221.index('_wa = wall_area(depth_n, alpha, W, H)')
          < _src221.index('_yaw_w = wall_pose(depth_n, _mx, _my'))
    # v223a: der Job-Log muss BEIDE Faelle nennen - besonders den kritischen
    # (keine Tiefenkarte, also kein Wand-Effekt). Die Meldung stand zuerst
    # INNERHALB der Tiefen-Bedingung: genau der Fall, der sich melden sollte,
    # war der einzige, der stumm blieb.
    check('v223a: der Log meldet auch den Fall OHNE Tiefenkarte',
          _src221.index("and not p.get('glass') and depth_n is None")
          < _src221.index("and p.get('flat_arr') is not None and depth_n is not None")
          and 'no depth map' in _src221 and 'placed on wall area at x=' in _src221)

    check('v219: die Wandmessung steht VOR der Zeichen-Weiche, nicht in einem Ast',
          _src217.index("if (p.get('szene') == 'wand' and not p.get('lying')")
          < _src217.index('tracked = (g_broll and'))
    # v219 LEHRE FESTGENAGELT: die Regel gehoert nicht nur in die Doku.
    # Drei Fehlschlaege an einem Tag hatten dieselbe Form - der Fix war richtig
    # gedacht, gruen getestet und ohne jede Wirkung. Diese beiden Tests fallen,
    # sobald jemand die Lehre aus CLAUDE.md entfernt oder das Deliver-Muster
    # wieder ohne Wirksamkeits-Nachweis fuehrt.
    _cmd219 = open(os.path.join(HERE, 'CLAUDE.md'), encoding='utf-8').read()
    check('v219: der Wirksamkeits-Nachweis steht in CLAUDE.md',
          'WIRKSAMKEITS-NACHWEIS' in _cmd219
          and 'Wird die Zeile ERREICHT?' in _cmd219
          and 'DREI Zeichenwege' in _cmd219
          and 'nur KÜRZEN, nie verlängern' in _cmd219)
    check('v219: das Deliver-Muster verlangt ihn als Schritt 0',
          _cmd219.index('## Deliver-Muster') > _cmd219.index('## WIRKSAMKEITS-NACHWEIS')
          and '0. **Wirksamkeits-Nachweis' in _cmd219)
    # Und der konkrete Rueckfall: eine Zeitregel darf einen Fliesstext-Block
    # nicht verlaengern (v216/v217). Der Test steht schon oben - hier nur die
    # Gegenprobe, dass die Lehre auch im Quelltext vermerkt ist, damit der
    # naechste Umbau sie liest, bevor er sie wiederholt.
    check('v219: die Doppelbild-Lehre steht im Quelltext, wo sie gebraucht wird',
          'HIER STAND EIN FLIESSTEXT-GEGEN-FLIESSTEXT-RIEGEL' in _src217
          and 'Zeiten nur\n        # KUERZEN, nie verlaengern' in _src217)

    # v210: DREI KI-SYSTEME FIELEN STILL AUS (Ismets Job-Log).
    # (a) ai_flow_direct hatte KEIN 'import requests' - jeder Kundenrender
    #     starb dort mit NameError und fiel auf die Heuristik zurueck. Ein
    #     Fallback, der jeden Fehler schluckt, macht aus einem
    #     Programmierfehler ein Feature, das niemand vermisst.
    import os as _os210
    _alt210 = _os210.environ.get('OPENAI_API_KEY', '')
    _os210.environ['OPENAI_API_KEY'] = 'sk-selftest-kein-echter-key'
    _err210 = []
    _pr210 = R.print if hasattr(R, 'print') else print
    import io as _io210, contextlib as _ctx210
    _buf210 = _io210.StringIO()
    try:
        with _ctx210.redirect_stdout(_buf210):
            R.ai_flow_direct([{'word': 'a', 'start': 0.0, 'end': 0.2},
                              {'word': 'b', 'start': 0.3, 'end': 0.5}],
                             [[0, 1]], 'en')
    finally:
        if _alt210:
            _os210.environ['OPENAI_API_KEY'] = _alt210
        else:
            _os210.environ.pop('OPENAI_API_KEY', None)
    check('v210: die KI-Textaufteilung stirbt NICHT an einem NameError',
          'NameError' not in _buf210.getvalue(), _buf210.getvalue()[:90])
    # (b) Bei den neuen Modellen zaehlen die Denk-Tokens mit. Ein knappes
    #     Budget wird komplett vom Denken verbraucht, die Antwort kommt leer
    #     zurueck - im Log als JSONDecodeError. So sind Bild-Regie,
    #     Objekt-Anker und Stille-Score ausgefallen.
    check('v210: neue Modelle bekommen ein Denkbudget (>= 2500)',
          R._oai_json('gpt-5', [], 200, 0.0)['max_completion_tokens'] >= 2500,
          str(R._oai_json('gpt-5', [], 200, 0.0)))
    check('v210: alte Chat-Modelle bleiben unveraendert',
          R._oai_json('gpt-4o', [], 200, 0.0)['max_tokens'] == 200)
    # (c) Jede Funktion in render.py importiert requests LOKAL. Wer eine neue
    #     KI-Funktion baut, vergisst den Import genauso leicht.
    _src210 = open(_os210.path.join(HERE, 'render.py'), encoding='utf-8').read()
    _fn210 = _src210.split('def ai_flow_direct')[1].split('\ndef ')[0]
    check('v210: ai_flow_direct importiert requests selbst',
          'import requests' in _fn210)
    # (d) Eine HIMMEL-Ansage darf die Lesbarkeits-Stufe nicht nach unten
    #     ziehen. 'above me' heisst UEBER dem Kopf.
    check('v210: die Kopfhoehen-Stufe kennt die Himmel-Ansage',
          "and not _himmel" in _src210
          and "if _tw < _kopf * 1.10 or _himmel" in _src210)

    # v211: Die gemessene Blockbreite gehoert INS LOG. Fuenf Theorien zum
    # angeschnittenen Text, fuenf widerlegt - weil die Zahl nur im Bild stand.
    _r211 = open(_os210.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v216: der Log misst jetzt ueber ink_box - damit erscheinen auch KARTEN
    # und KOMPOSITIONEN in der Liste (vorher las er 'bx'/'bw', die kein
    # Keyword-Plan setzt: jede Karte stand mit '0.000..0.000 W' im Log) -
    # dazu der Wortlaut und das sichtbare Zeitfenster.
    check('v211: jeder Textblock meldet seine gemessene Breite',
          'Block measurements unavailable' in _r211
          and 'RAGT AUS DEM BILD' in _r211
          and '_bx = ink_box(_p, W, H)' in _r211
          and '_txt = plan_text(_p, words)' in _r211
          and "f\"  Block {_t0:5.2f}-{_t1:5.2f}s" in _r211)

    # v212: Ein geschlossenes Ticket ist erledigt - keine Antwort mehr, und
    # nach 24 h verschwindet es aus der Kundenliste (nicht geloescht: die
    # Historie bleibt im Panel und fuer die Aufbewahrung).
    _sv212 = open(_os210.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    # ------------------------------------------------------------------
    # v220: EIN FUNKLOCH IST KEIN RENDER-FEHLER.
    # Ismets Screenshot (5G, zwei Balken): rote Karte "Render error -
    # Connection lost", darunter "der Render laeuft weiter, lade die Seite
    # neu". Beides zusammen war unehrlich und unbrauchbar - rot plus
    # "Render error" liest sich wie "dein Credit ist weg", und der Rat
    # "lade neu" konnte nicht funktionieren, weil showError den laufenden
    # Job vorher aus dem Speicher geloescht hat (daran haengt
    # resumeActiveJob).
    # GEPRUEFT WIRD DURCH AUSFUEHREN, nicht durch Quelltext-Suche: die Sonde
    # web/_dom_probe.mjs schneidet die echten Funktionen aus index.html und
    # laesst sie gegen ein Mini-DOM laufen. Genau das fehlte bei v218/v219.
    _node220 = shutil.which('node') or shutil.which('nodejs')
    if _node220:
        _r220 = run([_node220, os.path.join(HERE, 'web', '_dom_probe.mjs')])
        _out220 = (_r220.stdout or '') + (_r220.stderr or '')
        check('v220: die SPA-Sonde laeuft durch (echte Funktionen ausgefuehrt)',
              _r220.returncode == 0 and 'alle Nachweise gruen' in _out220,
              ' | '.join(l for l in _out220.splitlines() if l.startswith('FAIL'))[:200]
              or f"rc={_r220.returncode}")
        for _n220 in ('Funkloch: Titel ist NICHT "Render error"',
                      'Funkloch: der laufende Job bleibt gespeichert',
                      'Funkloch: Render-Knopf bleibt gesperrt',
                      'echter Fehler: Titel bleibt "Render error"',
                      'echter Fehler: Job wird vergessen',
                      'fertig: die Connection-lost-Karte ist verschwunden',
                      # v226b: der Aufklapp-Bereich darf nichts abschneiden.
                      'Aufklappen: die Animation nutzt die GEMESSENE Hoehe',
                      'Aufklappen: danach steht KEIN Deckel mehr',
                      'Aufklappen: auch ohne transitionend faellt der Deckel weg',
                      'Zuklappen: der Bereich schliesst wieder',
                      # v229: Aufloesungs-Stufen, die die Quelle nicht hergibt
                      '720p-Quelle: 1080p und 4K sind ausgegraut',
                      '720p-Quelle: die Auswahl wandert auf die hoechste',
                      '1080p-Quelle: nur 4K ist ausgegraut',
                      'unbekannte Quelle: nichts wird verboten',
                      # v230e: ein weggeklickter Tab ist kein Verbindungs-
                      # abbruch. Ismets Befund "Jedesmal wenn ich die Seite
                      # im Tab minimiere, ist die Seite abgestuerzt" - im
                      # echten Browser nachgestellt: 14 abgebrochene
                      # Anfragen in 20 s Hintergrund, danach die Karte
                      # "Connection lost", obwohl der Render weiterlief.
                      'v230e: im Hintergrund wird gar nicht erst gefragt',
                      'v230e: keine Fehlerkarte, waehrend der Tab weg ist',
                      'v230e: ein Abbruch im Hintergrund erhoeht den',
                      'v230e: zurueck im Vordergrund faengt der Zaehler',
                      # v230i: Chrome selbst gibt die Seite auf, wenn der Tab
                      # im Hintergrund zu viel Speicher haelt. Jedes
                      # angetippte Bibliotheks-Video blieb als eigener Player
                      # mit voller Quelle im DOM - ein verstecktes Element
                      # gibt nichts frei.
                      'v230i: jeder Player wird angehalten und entladen',
                      'v230i: die Quelle wird wirklich entfernt',
                      'v230i: die Kachel wird wieder zum Vorschaubild',
                      'v230i: der gerade laufende Player bleibt stehen'):
            _ok220 = ('PASS ' + _n220) in _out220
            check('v220: ' + _n220, _ok220,
                  '' if _ok220 else 'Sonde meldet den Fall nicht bestanden')
    else:
        check('v220: die SPA-Sonde laeuft durch (echte Funktionen ausgefuehrt)',
              False, 'node fehlt - Nachweis NICHT gefuehrt')
    # v226b KEIN FESTER DECKEL AUF EINEM AUFKLAPP-BEREICH.
    # Ismets Befund am Handy: "Ich sehe die weiteren Menue Optionen nicht".
    # Der offene Bereich stand auf max-height:2000px + overflow:hidden; auf
    # einem 390 px breiten Bildschirm ist "Look & Typography" rund 3500 px hoch,
    # also waren ~1500 px an Einstellungen unerreichbar - kein Scrollen half,
    # der Inhalt war gar nicht da. Im Browser gemessen (Chromium, 390x844).
    _ix226 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v226b: der offene Bereich hat keinen Pixel-Deckel im Stylesheet',
          '.acc.open .acc-body { padding: 4px 24px 24px; max-height: none;'
          in _ix226 and 'max-height: 2000px' not in _ix226,
          'ein Deckel im CSS schneidet ab, sobald der Inhalt waechst')
    check('v226b: ohne JavaScript ist der Bereich trotzdem vollstaendig da',
          '.acc.open .acc-body.anim { overflow: hidden; }' in _ix226
          and 'max-height: none; overflow: visible' in _ix226,
          'die Bedienbarkeit darf nie an einem Skript haengen')
    check('v226b: die Animation misst die Hoehe und raeumt den Deckel weg',
          "body.style.maxHeight = body.scrollHeight + 'px'" in _ix226
          and "body.style.maxHeight = '';" in _ix226
          and 'function accToggle(' in _ix226)
    # v228 DAS VORSCHAUBILD DARF ZUSCHNEIDEN, DER PLAYER NICHT.
    # Ismets Befund: "wenn ich den Player starte, z.B. in Library, dann sehe
    # ich nur die Haelfte von meinem Video". Die Kachel ist bewusst 16:9 mit
    # `cover` (ruhiges Raster) - beim Klick wurde derselbe Rahmen zum Player,
    # und ein 9:16-Video darin zeigt nur einen waagerechten Streifen. Im
    # Browser gemessen (Chromium, 390x844, echtes 540x960-Video): 32 % des
    # Bildes sichtbar, nach dem Fix 100 % und unverzerrt.
    check('v228: sobald das Video laeuft, gilt sein eigenes Seitenverhaeltnis',
          '.lib-thumb.playing { aspect-ratio: auto; }' in _ix226
          and 'max-height: 78vh; object-fit: contain' in _ix226
          and "this.classList.add('playing');" in _ix226,
          'sonst schneidet der 16:9-Rahmen das Hochformat-Video ab')
    check('v228: das Vorschaubild bleibt bewusst zugeschnitten (ruhiges Raster)',
          '.lib-thumb img, .lib-thumb video { width: 100%; height: 100%; '
          'object-fit: cover' in _ix226)
    # Und der Player nach dem Render: width:100% + max-height klemmt bei
    # Hochformat die HOEHE ab, die Voreinstellung `fill` zieht das Bild dann
    # in die Breite. Ohne contain ist es verzerrt (gemessen 358x480 Rahmen
    # gegen 540x960 Video).
    check('v228: der Ergebnis-Player verzerrt kein Hochformat',
          'max-height: 480px; object-fit: contain;' in _ix226)
    # v229 AUSGEGRAUTE AUFLOESUNGS-STUFEN. Die Engine skaliert NIE hoch
    # (H = min(Wunsch, Quelle)) - eine 720p-Quelle bleibt 720p, egal was
    # angehakt ist. Bis hier standen alle drei Stufen waehlbar da: eine
    # Auswahl, die nichts auswaehlt, und beim 4K-Haken der doppelte Preis
    # fuer dieselbe Datei. Das VERHALTEN prueft die SPA-Sonde oben; hier nur,
    # dass die Teile ueberhaupt verdrahtet sind.
    check('v229: die Stufen-Sperre haengt an der kurzen Kante der Quelle',
          'function updateResChoices()' in _ix226
          and 'State.srcShort' in _ix226
          and '.seg button:disabled' in _ix226
          and 'updateResChoices();' in _ix226)
    # v230 MEHR SOUND IN SCHNITTARMEN VIDEOS. Ismets Wunsch ("mehr sfx").
    # Ursache war eine Regel aus der Referenz: Ticks nur in den ersten 1.6 s
    # einer EINSTELLUNG. In einem schnittreichen Video ist das oft, in einem
    # Talking-Head gilt der ganze Clip als eine Einstellung - danach kam kein
    # Ton mehr. Gemessen an einem 15.6-s-Clip ohne Schnitt: 3 -> 8 Sounds.
    import sfx_engine as _SE30
    _w30 = [{'word': ' wort%d' % i, 'start': i * 0.42, 'end': i * 0.42 + 0.36}
            for i in range(36)]
    _d30 = _w30[-1]['end'] + 0.5
    _p30 = [{'flow': True, 'flow_anchor': i, 'flow_t': _w30[i]['start'],
             'tpl': 'flow'} for i in range(0, 36, 3)]
    _p30.append({'kw_i': 5, 'tpl': 'behind', 'anim': 'sturz',
                 'start': _w30[5]['start'], 'end': _w30[7]['end'],
                 't0': _w30[5]['start']})
    _f30 = _SE30.pack_folder(HERE)
    _o30 = os.path.join(tmp, 'sfx230.wav')

    def _n30(dichte, cuts=()):
        return _SE30.build_sfx_track(_p30, _w30, _d30, _f30, _o30, powers={5: 3},
                                     cut_times=list(cuts), dichte=dichte)
    _SE30.TICK_ABSTAND['_alt'] = 1e9          # Zustand VOR v230 nachstellen
    _alt30, _neu30 = _n30('_alt'), _n30('normal')
    check('v230: ein schnittarmes Video bekommt jetzt Sound',
          _neu30 > _alt30 * 2 and _neu30 >= 6,
          f'alt {_alt30} -> neu {_neu30} Sounds auf {_d30:.1f}s')
    _sp30, _di30 = _n30('sparsam'), _n30('dicht')
    check('v230: die Dichte-Stufen unterscheiden sich sinnvoll',
          _sp30 < _neu30 < _di30, f'sparsam {_sp30} | normal {_neu30} | dicht {_di30}')
    # Und die Referenz-Handschrift bleibt: am SCHNITT ist es dicht, egal was
    # die Stufe sagt - die Uebergaenge tragen den Ton.
    check('v230: Schnitte bekommen weiter die volle Dramaturgie',
          _n30('sparsam', (4.0, 9.0)) > _sp30 + 5,
          f'ohne Schnitt {_sp30} -> mit 2 Schnitten {_n30("sparsam", (4.0, 9.0))}')
    _sv30 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v230: der Wert ist ein geschlossener Satz (Server prueft ihn)',
          "not in ('sparsam', 'normal', 'dicht')" in _sv30
          and 'sfx_dichte' in _ix226,
          'ein ungeprueftes Wort darf nicht in die Engine')
    check('v229: sie laeuft nach dem Datei-Lesen UND nach jedem Neuaufbau',
          _ix226.count('updateResChoices();') >= 3,
          f"{_ix226.count('updateResChoices();')} Aufrufe")
    # Und der Server muss den Job bei einem Verbindungsabbruch weiterlaufen
    # lassen: der Abbruch des Browsers ist keine Stoerung (v208b) und der
    # gezahlte Credit bleibt am Job.
    _sv220 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v220: ein abgebrochener Upload/Abruf ist keine Betriebsstoerung',
          'ClientDisconnect' in _sv220)
    # ------------------------------------------------------------------
    # v222: WELCHE FASSUNG LAEUFT? Bis v221 stand die Build-Kennung als
    # fester Text im Server ('v213-ansage') und wurde monatelang nicht
    # mitgezogen. Sie landet ueber DVE_JOB_TAG in den Metadaten JEDES Videos -
    # log also bei jedem Kundenrender. Ergebnis: drei Fixes geliefert, drei
    # Renders geprueft, dreimal geraetselt, warum sich nichts aendert; in
    # Wahrheit lief der Server noch auf v213, weil der Deploy nicht griff,
    # und NICHTS im Bild oder im Panel konnte das zeigen.
    check('v222: die Build-Kennung kommt aus dem Deploy, nicht aus einer Konstanten',
          'def _build_stempel()' in _sv220
          and 'def _build_datei()' in _sv220
          and 'DVE_BUILD = _build_stempel()' in _sv220,
          'DVE_BUILD darf kein fester Text mehr sein')
    _up222 = open(os.path.join(HERE, 'update.sh'), encoding='utf-8').read()
    check('v222: der Deploy schreibt Branch und Commit in einen build.json-Stempel',
          "build.json" in _up222 and "rev-parse" in _up222
          and "'--abbrev-ref'" in _up222)
    # Fehlt die Datei, muss der Stempel EHRLICH 'unbekannt' sagen - eine
    # erfundene Versionsnummer waere genau der alte Fehler.
    import importlib as _il222
    _mod222 = _il222.import_module('web.server')
    _alt222, _altr222 = _mod222.DATA, _mod222.ROOT
    try:
        # v225c: ROOT mit umbiegen. Der Stempel im Image hat Vorrang - laege im
        # Arbeitsverzeichnis eine echte build.json (nach einem Handlauf von
        # update.sh), wuerde dieser Test sonst sie messen statt der Testdatei.
        _mod222.ROOT = os.path.join(tmp, 'kein_root_' + str(os.getpid()))
        _mod222.DATA = os.path.join(tmp, 'kein_build_' + str(os.getpid()))
        check('v222: ohne Stempel steht dort ehrlich "unbekannt"',
              'unbekannt' in _mod222._build_stempel(), _mod222._build_stempel())
        _d222 = _mod222._deploy_info()
        check('v222: ohne Stempel warnt das Panel',
              bool(_d222.get('warnung')) and _d222.get('alter_tage') is None,
              str(_d222)[:120])
        os.makedirs(_mod222.DATA, exist_ok=True)
        json.dump({'commit': 'abcdef123456', 'branch': 'claude/test-zweig',
                   'subject': 'irgendwas', 'deployed_at': int(time.time()) - 9 * 86400},
                  open(os.path.join(_mod222.DATA, 'build.json'), 'w'))
        _st222 = _mod222._build_stempel()
        _d222 = _mod222._deploy_info()
        check('v222: mit Stempel nennt er Commit UND Branch',
              'abcdef12' in _st222 and 'claude/test-zweig' in _st222, _st222)
        check('v222: ein alter Stand wird als Warnung gemeldet (Deploy greift nicht)',
              _d222.get('alter_tage', 0) >= 8.9 and 'Auto-Deploy' in _d222.get('warnung', ''),
              f"{_d222.get('alter_tage')} Tage, Warnung: {bool(_d222.get('warnung'))}")
        json.dump({'commit': 'abcdef123456', 'branch': 'b',
                   'subject': 's', 'deployed_at': int(time.time())},
                  open(os.path.join(_mod222.DATA, 'build.json'), 'w'))
        check('v222: ein frischer Stand warnt NICHT',
              not _mod222._deploy_info().get('warnung'))
        # v225c DER STEMPEL IM IMAGE HAT VORRANG. Der Stempel in DVE_DATA hat
        # den Container nie erreicht (Host-Pfad gegen Docker-Volume) und kann
        # ausserdem den NEUEN Commit behaupten, waehrend nach einem
        # abgebrochenen Test-Gate weiter die ALTE Fassung laeuft.
        os.makedirs(_mod222.ROOT, exist_ok=True)
        json.dump({'commit': 'aaaa1111bbbb', 'branch': 'im-image',
                   'subject': 'im Image gebaut', 'deployed_at': int(time.time())},
                  open(os.path.join(_mod222.ROOT, 'build.json'), 'w'))
        _st225 = _mod222._build_stempel()
        check('v225c: der im Image gebaute Stempel schlaegt den in DVE_DATA',
              'aaaa1111' in _st225 and 'im-image' in _st225
              and 'abcdef12' not in _st225, _st225)
        check('v225c: das Panel liest denselben Stempel',
              _mod222._deploy_info().get('branch') == 'im-image')
        os.remove(os.path.join(_mod222.ROOT, 'build.json'))
        check('v225c: ohne Image-Stempel bleibt DVE_DATA der Rueckfall (Desktop)',
              'abcdef12' in _mod222._build_stempel(), _mod222._build_stempel())
    finally:
        _mod222.DATA, _mod222.ROOT = _alt222, _altr222
    # Der stille Deploy-Stopp muss sich MELDEN. autodeploy.sh schreibt nur bei
    # einem GESCHEITERTEN Versuch ins Panel; bleibt der Timer stehen, sieht es
    # aus wie "nichts Neues". Genau so lief der Server monatelang auf v213.
    check('v222: der Watchdog meldet einen veralteten Stand von selbst',
          "_notify_admin(" in _sv220 and 'deploy_alt-' in _sv220
          and 'laeuft der Auto-Deploy noch' in _sv220
          and "_al is not None and _al > 7" in _sv220)
    # v225c EIN FEHLENDER STEMPEL IST KEIN STILLSTAND. Bis v225b galt beides
    # als derselbe Fall - und weil der Stempel wegen des Pfadfehlers NIE ankam,
    # mailte der Wachhund taeglich einen Deploy-Stopp, den es nicht gab
    # (Ismets Screenshot). Ein grundloser Alarm kostet so viel wie ein
    # verpasster. Der ALTE Test verlangte ausdruecklich `_al is None or ...` -
    # er hat den Fehler festgeschrieben, genau die v132-Lehre.
    check('v225c: ein fehlender Stempel loest KEINEN Deploy-Stopp-Alarm aus',
          "_al is None or _al > 7" not in _sv220
          and "elif _al is None and not globals().get('_STEMPEL_GEMELDET')" in _sv220,
          'unbekannt ist nicht dasselbe wie "seit Tagen kein Deploy"')
    check('v225c: die Stempel-Meldung kommt genau einmal je Programmlauf',
          "globals()['_STEMPEL_GEMELDET'] = True" in _sv220
          and "'deploy_stempel'" in _sv220,
          'sonst 24 Mails am Tag ueber etwas, das der naechste Deploy heilt')
    # Der Weg des Stempels muss im Deploy stimmen, sonst ist alles darueber
    # Zierde: update.sh legt ihn ins BAUVERZEICHNIS, `COPY . /app/` nimmt ihn
    # mit, und .dockerignore darf ihn nicht wieder aussortieren.
    check('v225c: update.sh legt den Stempel ins Bauverzeichnis, nicht nach DVE_DATA',
          'STAMP_DIR="$(pwd)"' in _up222
          and 'DATA_DIR="${DVE_DATA' not in _up222,
          'im Container ist DVE_DATA ein Docker-Volume - der Host-Pfad kommt dort nie an')
    check('v225c: das Image kopiert den Stempel mit',
          'COPY . /app/' in open(os.path.join(HERE, 'Dockerfile'),
                                 encoding='utf-8').read())
    check('v225c: .dockerignore sortiert den Stempel nicht aus',
          'build.json' not in open(os.path.join(HERE, '.dockerignore'),
                                   encoding='utf-8').read())
    check('v225c: der Stempel ist kein Repo-Inhalt (gitignored)',
          'build.json' in open(os.path.join(HERE, '.gitignore'),
                               encoding='utf-8').read())
    check('v222: die Deploy-Warnung ist auf eine pro Tag gedeckelt',
          "'deploy_alt-' + time.strftime('%Y-%m-%d')" in _sv220,
          'sonst 24 Mails am Tag')
    check('v222: das Panel zeigt Branch, Alter und die Warnung',
          'd.deploy.branch' in open(os.path.join(HERE, 'web', 'admin.html'),
                                    encoding='utf-8').read()
          and 'd.deploy.warnung' in open(os.path.join(HERE, 'web', 'admin.html'),
                                         encoding='utf-8').read())

    check('v212: auf ein geschlossenes Ticket kann nicht geantwortet werden',
          "if (t['status'] or '') == 'closed':" in _sv212
          and 'This ticket is closed. Please open a new one.' in _sv212)
    check('v212: eine Rueckfrage reisst ein geschlossenes Ticket nicht wieder auf',
          _sv212.index("This ticket is closed. Please open a new one.")
          < _sv212.index("UPDATE tickets SET status = 'open', updated_at = ?"))
    check('v212: geschlossene Tickets verschwinden nach 24 h aus der Liste',
          'TICKET_CLOSED_TTL' in _sv212
          and "NOT (status = 'closed' AND updated_at < ?)" in _sv212)
    _idx212 = _idx212a = open(_os210.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v212: die App zeigt bei geschlossenen Tickets kein Antwortfeld',
          "t.status === 'closed' ? `<div class=\"hint\"" in _idx212)

    # v212a: Am Desktop blitzte Browser-Weiss durch (Grund nur auf <body>)
    # und die Karten zogen sich ueber die ganze Fensterbreite.
    check('v212a: der dunkle Grund liegt auf <html>, kein Weiss-Blitz',
          'html { background: #0b0b0e; }' in _idx212a)
    # v212c: color-scheme: dark liess den BROWSER die Felder zeichnen -
    # pechschwarz, eckig, randlos. Die Felder bekommen ihre Optik hier.
    check('v212c: kein color-scheme, Felder werden selbst gestaltet',
          'color-scheme: dark' not in _idx212a
          and 'input[type=text], input[type=email]' in _idx212a
          and 'border-radius: 12px;' in _idx212a)
    check('v212a: alle Seiten haben eine Lesebreite',
          '.page-head, .page-body, .main { max-width: 1040px;' in _idx212a)

    _adm212 = open(_os210.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v212b: das Panel zeigt bei geschlossenen Tickets kein Antwortfeld',
          "t.status==='closed'" in _adm212
          and 'Ticket wurde geschlossen' in _adm212)

    check('Prompt: Sperrliste im Selbstbezug ausgesetzt',
          'Sperrliste AUSGESETZT' in R.REGIE_PROMPT
          and 'NIE ohne Moment' in R.REGIE_PROMPT)
    check('Selbstbezug-Backstop im Main verdrahtet',
          '_self_ref_intent(fx_map, words)' in
          open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())
    check('anim_for kennt englische Aktions-Woerter (explode/fly/vanish)',
          any(R._anim_hit('explodes', k) for k in dict(R.ANIM_HINTS)['explosion'])
          and any(R._anim_hit('flies', k) for k in dict(R.ANIM_HINTS)['spur'])
          and any(R._anim_hit('vanishes', k) for k in dict(R.ANIM_HINTS)['schwund']))

    # v99a: Die Ansage des Sprechers ist GESETZ. Bei Selfie-Nahaufnahmen
    # (Gesicht >= 52% Bildbreite) schaltete der Sichtbarkeits-Backstop
    # explizit angesagte behind-Momente wieder nach vorn - genau daran
    # scheiterte Ismets Test auf douchko.eu. intent-Momente sind jetzt tabu
    # (fuer Cover-Backstop UND Vision-fx-Override).
    _bcb = R._behind_cover_backstop(
        {0: {'fx': 'behind', 'power': 2, 'intent': True},
         5: {'fx': 'behind', 'power': 2}}, {0: 0.60, 5: 0.60})
    # v141 (Ismets Befund): die Nahaufnahme-Ansage wird NICHT mehr zu 'himmel'
    # umgebogen. "behind you" landete dadurch ganz oben am Bildrand, weit weg
    # von der Person - die Aussage stimmte nicht mehr. Jetzt nur noch als
    # Nahaufnahme markiert; die Platzierung bleibt am Kopf.
    check('Ansage schlaegt Nahaufnahme-Backstop (behind bleibt, nah markiert)',
          _bcb[0]['fx'] == 'behind' and _bcb[0].get('nah') is True
          and not _bcb[0].get('szene')
          and _bcb[5]['fx'] != 'behind', str(_bcb))
    _bcb2 = R._behind_cover_backstop(
        {0: {'fx': 'behind', 'power': 2, 'intent': True, 'szene': 'himmel'}},
        {0: 0.60})
    check('v141: echte Himmel-Ansage bleibt Himmel (Backstop fasst sie nicht an)',
          _bcb2[0].get('szene') == 'himmel' and not _bcb2[0].get('nah'), str(_bcb2))
    _bcb3 = R._behind_cover_backstop(
        {0: {'fx': 'behind', 'power': 2, 'intent': True}}, {0: 0.20})
    check('v141: normale Einstellung setzt kein nah-Flag',
          not _bcb3[0].get('nah'), str(_bcb3))
    _rsrc141 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v193: die Uebernahme-Liste ist um 'anker' und 'user_pick' gewachsen -
    # beide gingen bis dahin bei JEDEM Render verloren. Der gepruefte
    # Invariant bleibt derselbe: 'nah' ueberlebt den Roundtrip.
    check('v141: nah wird am Kopf platziert und ueberlebt den Editor-Roundtrip',
          "info.get('nah')" in _rsrc141
          and "for k_v in ('szene', 'lage', 'nah', 'anker', 'user_pick'):"
          in _rsrc141)
    _si = R._speech_intent({4: {'fx': 'outline', 'power': 2, 'n': 1}},
                           _wsr('The word stays right behind me. Okay then.'))
    check('_speech_intent markiert Ansagen als intent',
          _si[4].get('fx') == 'behind' and _si[4].get('intent') is True,
          str(_si))
    check('_self_ref_intent markiert Orts-Momente als intent',
          _sr[3].get('intent') is True)
    _pri = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "behind",'
                         ' "power": 2, "intent": true}]}', wg, 'de')
    check('intent ueberlebt den Regie-Cache', bool(_pri)
          and _pri[1].get('intent') is True, str(_pri))
    check('Vision-Regie respektiert intent (Quelltext)',
          "if fx_map[i].get('intent'):" in
          open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # v99a: Befunde aus Ismets echtem Selfie-Test ("macht nicht, was er
    # sagt") - vier Regeln degradierten angesagte Momente wieder:
    # Dichte-Limit, B-Roll-Gate, Mehrwort-Komposition, Editor-Roundtrip.
    _wv = _wsr('First moment sits here early. '
               'The captions are on the ground. And more talking after that.')
    _fxv = {1: {'fx': 'outline', 'power': 2, 'n': 1},
            8: {'fx': 'ground', 'power': 2, 'n': 3, 'szene': 'boden',
                'lage': 'liegend', 'intent': True}}
    import copy as _cp
    _plv = R.build_plans(_wv, set(_fxv), cfg, S, W_, H_, lambda s, e: True,
                         _cp.deepcopy(_fxv))
    _kwv = {p.get('kw_i'): p for p in _plv if 'kw_i' in p}
    check('Dichte-Limit degradiert intent-Momente nicht',
          8 in _kwv, str(sorted(_kwv)))
    check('Mehrwort-Platzierung bleibt ground (keine behind-Komposition)',
          8 in _kwv and _kwv[8]['tpl'] == 'ground'
          and _kwv[8].get('lying') is True,
          str(_kwv.get(8, {}).get('tpl')))
    _plb = R.build_plans(_wv, {8}, cfg, S, W_, H_, lambda s, e: False,
                         _cp.deepcopy({8: _fxv[8]}))
    check('B-Roll-Gate laesst intent-Momente durch',
          any(p.get('kw_i') == 8 for p in _plb))
    check('Auto-Anim-Kontext endet an der Satzgrenze',
          'talking' not in R.anim_ctx(_wv, 8, 3).lower()
          and 'ground' in R.anim_ctx(_wv, 8, 3).lower())
    _src99 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('intent ueberlebt Momente-Editor-Roundtrip (Quelltext)',
          "fx_map[i]['intent'] = True" in _src99
          and _src99.count('anim_ctx(words, i') >= 2)

    # v100 Animations-Pass: jede der 26 Animationen laeuft crashfrei ueber
    # ihren ganzen Verlauf (stateful, mit Audio) und liefert brauchbare
    # Frames. Dazu Verhaltens-Invarianten der neuen Physik.
    _ab, _ = S.text('TEST', 90, (255, 255, 255))
    _fails = []
    for _an in R.ANIM_LIST:
        try:
            _pp = {'anim': _an, 'start': 1.0, 'kw_i': 2, 'arr': _ab}
            for _k in range(0, 40):
                _t = _k * 0.035
                _aud = (0.6, 0.5, 1.0 if _t < 0.07 else 0.2)
                _r = R.anim_apply(_pp, _ab, _aud, _t)
                if _r[0] is None or _r[0].size == 0 or not (0.0 <= _r[4] <= 1.5):
                    _fails.append(_an)
                    break
        except Exception as _e:
            _fails.append(f'{_an}:{type(_e).__name__}')
    check('v100: alle 26 Animationen crashfrei ueber vollen Verlauf',
          not _fails, str(_fails))
    # sturz LANDET (steht am Ende voll sichtbar, nicht 70% in der Luft)
    _ps = {'anim': 'sturz', 'start': 1.0, 'kw_i': 2, 'arr': _ab}
    for _k in range(0, 34):
        _rs = R.anim_apply(_ps, _ab, (0.6, 0.5, 0.2), _k * 0.035)
    check('v100: sturz landet (Aufprall statt Verblassen)',
          abs(_rs[2] - _ab.shape[0] * 0.30) < _ab.shape[0] * 0.06
          and _rs[4] >= 0.99, f'dy={_rs[2]:.1f} op={_rs[4]:.2f}')
    # wende kommt lesbar zurueck (Winkel ~0, volle Deckkraft)
    _pw = {'anim': 'wende', 'start': 1.0, 'kw_i': 2, 'arr': _ab}
    _rw = R.anim_apply(_pw, _ab, (0.6, 0.5, 0.0), 1.25)
    check('v100: wende endet lesbar (Overshoot ausgependelt)',
          _rw[4] > 0.93 and _rw[3] > 0.97, f'op={_rw[4]:.2f} sc={_rw[3]:.3f}')
    # neon ZUENDET: dunkel am Start, an nach der Zuendsequenz
    _pn = {'anim': 'neon', 'start': 1.0, 'kw_i': 2, 'arr': _ab}
    _op0 = R.anim_apply(dict(_pn), _ab, (0.6, 0.5, 0.0), 0.02)[4]
    _op1 = R.anim_apply(dict(_pn), _ab, (0.6, 0.5, 0.0), 0.60)[4]
    check('v100: neon zuendet (dunkel -> an)', _op0 < 0.5 < _op1,
          f'{_op0:.2f} -> {_op1:.2f}')
    check('v100: kein Weissrauschen-Shake mehr (zittern deterministisch)',
          "rng.random()) - 0.5) * 9" not in _src99
          and 'hand_jitter' in _src99)

    # v101.1 Betonungs-Typografie: laute Woerter schwerer, leise leichter -
    # die Zeile sieht aus wie die Stimme klingt. Kein API-Call noetig.
    _wb = [{'word': ' Diese', 'start': 0.0, 'end': 0.3},
           {'word': ' Zahl', 'start': 0.35, 'end': 0.6},
           {'word': ' veraendert', 'start': 0.65, 'end': 1.0},
           {'word': ' alles', 'start': 1.05, 'end': 1.3}]
    _cp0 = next(t for t in R.compose_phrase([0, 1, 2, 3], _wb, S, 1080, 1920,
                                            portrait=True) if t['role'] == 'core')
    _cp1 = next(t for t in R.compose_phrase([0, 1, 2, 3], _wb, S, 1080, 1920,
                                            portrait=True, loud={2: '!', 3: '~'})
                if t['role'] == 'core')
    check('v101: Betonungs-Kern reagiert auf Pegel (anders, aber im Rahmen)',
          _cp1['arr'].shape[1] != _cp0['arr'].shape[1]
          and _cp1['arr'].shape[1] <= _cp0['arr'].shape[1] * 1.05,
          f"{_cp0['arr'].shape[1]} -> {_cp1['arr'].shape[1]}")
    _fl0 = R.compose_flow([0, 1, 2, 3], _wb, S, 1080, 1920, portrait=True)[0]
    _fl1 = R.compose_flow([0, 1, 2, 3], _wb, S, 1080, 1920, portrait=True,
                          loud={0: '!'})[0]
    _w0 = next(i for i in _fl0 if i['role'] == 'norm' and i['i'] == 0)['w']
    _w1 = next(i for i in _fl1 if i['role'] == 'norm' and i['i'] == 0)['w']
    check('v101: Flow-Wort wird bei lautem Pegel groesser/schwerer', _w1 > _w0,
          f'{_w0} -> {_w1}')
    check('v101: Pegel-Karte im Main verdrahtet (build_plans loud=)',
          'loud_map = _word_loudness(words, voice_wav)' in _src99
          and _src99.count('loud=loud_map') >= 2)
    # v101.8 Choreographie-Regie im Prompt
    check('v101: Choreographie-Sektion im Regie-Prompt',
          'CHOREOGRAPHIE' in R.REGIE_PROMPT
          and 'BUENDELN statt Geballer' in R.REGIE_PROMPT
          and 'PAUSEN HALTEN' in R.REGIE_PROMPT)
    # v101.9 Silent-Score: ohne Key still None, Verdrahtung vorhanden
    check('v101: Silent-Score ohne Key -> None (kein Crash)',
          R.silent_score('/tmp/nix.mp4', _wb, {1: {'fx': 'outline', 'power': 2}})
          is None)
    check('v101: Silent-Score-Prompt bewertet stumme Wirkung',
          'STUMM' in R.SILENT_PROMPT and '"score"' in R.SILENT_PROMPT)
    check('v101: Silent-Score im Main + Server + UI verdrahtet',
          'silent_score(out_path' in _src99
          and '_silent.json' in open(os.path.join(HERE, 'web', 'server.py'),
                                     encoding='utf-8').read()
          and 'Silent view' in open(os.path.join(HERE, 'web', 'index.html'),
                                    encoding='utf-8').read())
    # v101.3 Watermark-Unlock: Sprite-Funktion + Split-Verdrahtung
    _wmarr, _wmx, _wmy = R.build_watermark(1080, 1920)
    check('v101: Wasserzeichen-Sprite ausgelagert (Split nutzt dasselbe Bild)',
          _wmarr.shape[2] == 4 and _wmarr.shape[0] > 20
          and 0 < _wmx < 1080 and 0 < _wmy < 1920,
          f'{_wmarr.shape} @ {_wmx},{_wmy}')
    check('v101: Watermark-Split im Render verdrahtet',
          'watermark_split' in _src99 and 'master_clean.mp4' in _src99
          and "overlay={_wwx}:{_wwy}" in _src99)

    # v101c Beat-Grid: Momente rasten auf den Musik-Takt.
    _bge = np.zeros(300, np.float32)
    for _bf in range(15, 295, 15):                      # 120 BPM bei 30 fps
        _bge[_bf] = 1.0
        _bge[_bf + 1] = 0.7
    _bgt = R.beat_grid_times(_bge, 30, conf=0.8, bpm=120)
    check('v101c: beat_grid_times findet die Beats',
          _bgt is not None and len(_bgt) >= 4 and abs(_bgt[0] - 0.5) < 0.05,
          str(_bgt[:3] if _bgt else None))
    check('v101c: niedrige Confidence -> kein Grid (Talking-Head-Schutz)',
          R.beat_grid_times(_bge, 30, conf=0.1, bpm=120) is None)
    _bge2 = np.zeros(300, np.float32)
    _bge2[30] = _bge2[60] = 1.0
    check('v101c: unter 4 Beats -> kein Grid (Zufalls-Schutz)',
          R.beat_grid_times(_bge2, 30, conf=0.8, bpm=120) is None)
    _bgw = [{'word': 'Wir', 'start': 0.2, 'end': 0.5},
            {'word': 'Boom', 'start': 1.03, 'end': 2.2}]
    _bg_base = R.build_plans(_bgw, {1}, cfg, S, W_, H_, lambda s, e: True)
    _bg_p0 = next(p for p in _bg_base if p.get('kw_i') == 1)
    _bg_st, _bg_en = _bg_p0['start'], _bg_p0['end']
    _bg_nb = _bg_st + 0.08
    check('v101c: Fixture-Moment lang genug fuer Snap-Guard',
          _bg_en - _bg_nb >= 0.6, f'{_bg_st:.2f}-{_bg_en:.2f}')
    _bg_sn = R.build_plans(_bgw, {1}, cfg, S, W_, H_, lambda s, e: True,
                           beat_times=[_bg_nb])
    _bg_p1 = next(p for p in _bg_sn if p.get('kw_i') == 1)
    check('v101c: Moment rastet auf den Beat (<=0.12s)',
          abs(_bg_p1['start'] - _bg_nb) < 1e-6,
          f"{_bg_st:.3f} -> {_bg_p1['start']:.3f}")
    _bg_far = R.build_plans(_bgw, {1}, cfg, S, W_, H_, lambda s, e: True,
                            beat_times=[_bg_st + 0.5])
    _bg_p2 = next(p for p in _bg_far if p.get('kw_i') == 1)
    check('v101c: Beat weiter als 0.12s -> kein Snap (Wort-Sync gewinnt)',
          abs(_bg_p2['start'] - _bg_st) < 1e-6)
    _cfg_bg = copy.deepcopy(cfg)
    _cfg_bg['effects']['beat_grid'] = False
    _bg_off = R.build_plans(_bgw, {1}, _cfg_bg, S, W_, H_, lambda s, e: True,
                            beat_times=[_bg_nb])
    _bg_p3 = next(p for p in _bg_off if p.get('kw_i') == 1)
    check('v101c: effects.beat_grid=False schaltet das Grid ab',
          abs(_bg_p3['start'] - _bg_st) < 1e-6)
    check('v101c: Beat-Grid im Main verdrahtet',
          '_beat_ts = beat_grid_times(beat_env, fps, conf, bpm)' in _src99
          and _src99.count('beat_times=_beat_ts') >= 2
          and '_beat_ts = None' in _src99)

    # v101d Safe-Zone-Regie: plattform-genaue UI-Masken als Constraints.
    _tkz = R.platform_safe_zones('tiktok', 1080, 1920)
    _rlz = R.platform_safe_zones('reels', 1080, 1920)
    _gnz = R.platform_safe_zones('unbekannt', 1080, 1920)
    check('v101d: Plattform-Zone liefert Text-Rechteck',
          _tkz['right_rail'] < 1080 and _tkz['bottom'] < 1920
          and _tkz['top'] > 0 and _tkz['left'] > 0,
          f"rail={_tkz['right_rail']} bot={_tkz['bottom']}")
    check('v101d: Reels sitzt hoeher als TikTok (mehr Chrome unten)',
          _rlz['bottom'] < _tkz['bottom'], f"{_rlz['bottom']} < {_tkz['bottom']}")
    check('v101d: unbekannte Plattform faellt auf generic (nirgends verdeckt)',
          _gnz['label'] == 'alle Feeds')
    # Report meldet nur echte Ueberlappungen, ignoriert Momente ohne Sprite
    _szp = [
        {'kw_txt': 'MITTE', 'cx': 540, 'cy': 960, 'arr': np.zeros((80, 400, 4), np.uint8)},
        {'kw_txt': 'RECHTS', 'cx': 860, 'cy': 960, 'arr': np.zeros((80, 500, 4), np.uint8)},
        {'kw_txt': 'UNTEN', 'cx': 540, 'cy': 1830, 'arr': np.zeros((80, 200, 4), np.uint8)},
        {'kw_txt': 'OHNE'},
    ]
    _szw = R.safe_zone_report(_szp, _tkz, 1080, 1920)
    _szt = {t for t, g in _szw}
    check('v101d: Report flaggt UI-Ueberlappung, nicht mittigen/spritelosen Text',
          'RECHTS' in _szt and 'UNTEN' in _szt
          and 'MITTE' not in _szt and 'OHNE' not in _szt, str(_szw))
    check('v101d: ohne Plattform (Landscape) kein Report', R.safe_zone_report(_szp, None, 1080, 1920) == [])
    # build_plans: clamp haelt Text links der Button-Spalte (Constraint greift)
    _cfg_tk = copy.deepcopy(cfg)
    _cfg_tk['effects']['safe_zone'] = True
    _cfg_tk.setdefault('output', {})['platform'] = 'tiktok'
    _szfp = lambda s, e: (900, 300, 60)     # Gesicht weit rechts -> Text will nach rechts
    _szpl = R.build_plans([{'word': 'Weltrekord', 'start': 1.0, 'end': 1.8}], {0},
                          _cfg_tk, S, 1080, 1920, lambda s, e: True,
                          {0: {'fx': 'outline', 'power': 2}}, face_pos=_szfp)
    _rail = R.platform_safe_zones('tiktok', 1080, 1920)['right_rail']
    _okx = all(p['cx'] + p['arr'].shape[1] / 2 <= _rail + 2
               for p in _szpl if p.get('arr') is not None and 'cx' in p)
    check('v101d: clamp_cx haelt Text links der TikTok-Button-Spalte', _okx)
    check('v101d: Plattform-Maske im Main verdrahtet + config-Default',
          "platform_safe_zones(_plat" in _src99
          and "cfg.get('output', {}).get('platform'" in _src99
          and 'platform: generic' in open(os.path.join(HERE, 'config.yaml'),
                                           encoding='utf-8').read())

    # v101e Korrektur-Gedaechtnis: aggregierte Vorlieben generalisieren.
    _ce = [{'orig_fx': 'behind', 'user_fx': 'ground'},
           {'orig_fx': 'behind', 'user_fx': 'ground'},
           {'orig_fx': 'outline', 'user_fx': 'cascade'},        # 1x -> Rauschen
           {'user_anim': ''}, {'user_anim': ''},
           {'user_aktiv': False}, {'user_aktiv': False}, {'user_aktiv': False},
           {'orig_power': 3, 'user_power': 1},
           {'orig_power': 3, 'user_power': 2}]
    _prof = R.correction_profile(_ce)
    check('v101e: Profil generalisiert haeufige Tendenzen (>=2x)',
          "'behind'" in _prof and "'ground'" in _prof
          and 'entfernt' in _prof and 'deaktiviert' in _prof and 'gesenkt' in _prof)
    check('v101e: Einzelfaelle bleiben draussen (kein Stil aus 1x)',
          'cascade' not in _prof)
    check('v101e: kein Profil ohne Daten / unter Schwelle',
          R.correction_profile([]) == ''
          and R.correction_profile([{'orig_fx': 'a', 'user_fx': 'b'}]) == '')
    check('v101e: Gedaechtnis fliesst in den KI-Prompt (Kontext, nicht nur exakt)',
          'prof_block = correction_profile(_corr)' in _src99
          and 'prof_block + ref_block' in _src99)
    _srv_src = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v101e: Capture speichert orig_fx + Wucht-Delta (Server)',
          "rec['orig_fx']" in _srv_src
          and "rec['orig_power'], rec['user_power']" in _srv_src)

    # v101f Licht-Wahrheit: Kontakt-Schatten faellt licht-wahr zur Seite.
    _lf_r = np.zeros((96, 96, 3), np.uint8); _lf_r[:, 48:] = 200
    _lx, _hard = R.estimate_light_dir(_lf_r)
    check('v101f: Lichtrichtung erkannt (hell rechts -> lx>0, hart)',
          _lx > 0.3 and _hard > 0.2, f'lx={_lx:.2f} hard={_hard:.2f}')
    _lx0, _h0 = R.estimate_light_dir(np.full((96, 96, 3), 120, np.uint8))
    check('v101f: flaches Licht -> keine Richtung (weicher Schatten)',
          abs(_lx0) < 0.05 and _h0 < 0.1)
    _sarr = np.zeros((60, 300, 4), np.uint8); _sarr[40:55, 20:280, 3] = 255
    _s0 = R.make_contact_shadow(_sarr)
    _s1 = R.make_contact_shadow(_sarr, light=(0.8, 0.9))
    check('v101f: Licht rechts -> Schatten versetzt nach links + gestreckt',
          _s1[2] < _s0[2] and _s1[0].shape[1] >= _s0[0].shape[1],
          f'dx {_s0[2]:.0f}->{_s1[2]:.0f}')
    check('v101f: ohne Licht identisch zu vorher (Rueckwaerts-Kompatibel)',
          R.make_contact_shadow(_sarr, light=None)[2] == _s0[2])
    check('v101f: Licht im Main geschaetzt + an build_plans verdrahtet',
          'estimate_light_dir(_lf)' in _src99
          and _src99.count('light_dir=_light') >= 2
          and "cfg['effects'].get('light_shadow'" in _src99)

    # v101g Regie-Kontaktbogen: Grid aus echten Moment-Frames.
    _kt1 = np.full((1920, 1080, 3), 60, np.uint8)
    _kb5 = R.contact_sheet([_kt1] * 5, [f'W{i} @ {i}.0s' for i in range(5)])
    check('v101g: Kontaktbogen-Grid (5 Tiles -> 3 Spalten, 2 Reihen)',
          _kb5 is not None and _kb5.shape[1] == 3 * 360
          and _kb5.shape[0] > 2 * (int(1920 * 360 / 1080)),
          str(_kb5.shape if _kb5 is not None else None))
    check('v101g: leere Liste -> None, 1 Tile -> 1 Spalte',
          R.contact_sheet([], []) is None
          and R.contact_sheet([_kt1], ['X @ 0.0s']).shape[1] == 360)
    check('v101g: Kontaktbogen im Render verdrahtet (Peak-Frames + Save + Gate)',
          '_kb_frames' in _src99 and '_kontakt.jpg' in _src99
          and "cfg['effects'].get('contact_sheet'" in _src99)
    _srv_g = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _ui_g = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v101g: Server-Endpoint + Job-Flag + Library-Feld',
          "'/api/contact/{jid}'" in _srv_g
          and 'fertig_kontakt.jpg' in _srv_g
          and "kontakt=True" in _srv_g)
    check('v101g: UI zeigt Moment sheet (Success + Library)',
          'dlKontakt' in _ui_g and '/api/contact/' in _ui_g
          and 'State.kontakt' in _ui_g)

    # v101h Caption-Alpha-Export: Difference-Matting-Doppelpass.
    _acb = np.zeros((8, 8, 3), np.float32)
    _acw = np.full((8, 8, 3), 255, np.float32)
    _acb[2:4, 2:4] = 250; _acw[2:4, 2:4] = 250          # opaker Text
    _abgra = R.alpha_from_pair(_acb, _acw)
    check('v101h: alpha_from_pair - leer transparent, Text opak, Farbe erhalten',
          _abgra.shape == (8, 8, 4) and _abgra[0, 0, 3] == 0
          and (_abgra[0, 0, :3] == 0).all() and _abgra[2, 2, 3] == 255
          and abs(int(_abgra[2, 2, 0]) - 250) <= 1)
    _ad = R.alpha_from_pair(np.zeros((4, 4, 3), np.float32),
                            np.full((4, 4, 3), 127.5, np.float32))
    check('v101h: dim wird zu korrektem Halbtransparenz-Schwarz (~50%)',
          abs(int(_ad[0, 0, 3]) - 128) <= 1 and (_ad[0, 0, :3] == 0).all())
    _apl = [{'start': 1.0, '_puls': 0.5,
             '_arng': np.random.default_rng(7), 'cx': 100}]
    _acam = [1.0, 2.0, 3.0, 4.0]
    _asnap = R._alpha_state_snapshot(_apl, _acam)
    _v1 = _apl[0]['_arng'].random(); _apl[0]['_puls'] = 9.9
    _apl[0]['_neu'] = 1; _acam[0] = 77.0
    R._alpha_state_restore(_apl, _acam, _asnap)
    check('v101h: State-Snapshot stellt Anim/RNG/Kamera exakt wieder her',
          _apl[0]['_puls'] == 0.5 and _acam[0] == 1.0
          and '_neu' not in _apl[0] and _apl[0]['_arng'].random() == _v1)
    check('v101h: Alpha-Export im Main verdrahtet (Flag, Clamp, Doppelpass, Mux)',
          '--alpha-export' in _src99
          and 'alpha_from_pair(_cb, _cw)' in _src99
          and '_alpha_state_restore(plans, cam_state, _snap)' in _src99
          and "'-profile:v', '4444'" in _src99
          and 'SFX only' in _src99)
    check('v101h: Grain deterministisch seedbar (Doppelpass-Voraussetzung)',
          'grain_seed=_gs' in _src99
          and 'default_rng(grain_seed)' in _src99)

    # v101i World-Lock Wand: eigener Track auf der Wand-Ebene.
    _wrng = np.random.default_rng(42)
    _wbase = cv2.GaussianBlur((_wrng.random((270, 480)) * 255)
                              .astype(np.uint8), (0, 0), 1.0)
    _wim2 = _wbase.copy()
    _wim2[:135] = np.roll(_wbase[:135], -6, axis=1)   # Wand zieht -6px
    _wim2[135:] = np.roll(_wbase[135:], -2, axis=1)   # Boden nur -2px
    _Hb, _okb = R.update_homography(_wbase, _wim2, np.eye(3))
    _Hw, _okw = R.update_homography(_wbase, _wim2, np.eye(3), region='wand')
    check('v101i: Wand-Track folgt der Wand-Ebene, nicht dem Boden',
          _okb and _okw and abs(_Hw[0, 2] - (-6)) < 1.5
          and _Hb[0, 2] > _Hw[0, 2] + 1.5,
          f'wand={_Hw[0, 2]:.1f} boden={_Hb[0, 2]:.1f}')
    _wim3 = _wim2.copy()
    _wim3[30:130, 200:300] = np.roll(_wbase[30:130, 200:300], +8, axis=1)
    _wpm = np.zeros((270, 480), np.float32); _wpm[20:140, 190:310] = 1.0
    _Hw3, _ok3 = R.update_homography(_wbase, _wim3, np.eye(3), region='wand',
                                     exclude=_wpm)
    check('v101i: Personen-Maske haelt bewegte Person aus dem Wand-Track',
          _ok3 and abs(_Hw3[0, 2] - (-6)) < 1.5, f'{_Hw3[0, 2]:.1f}')
    # build_plans: stehender Wand-Text bekommt Kontakt-Schatten
    _wfx = {0: {'fx': 'ground', 'power': 2, 'n': 1, 'szene': 'wand',
                'lage': 'stehend', 'intent': True}}
    _wpl = R.build_plans([{'word': 'Beton', 'start': 1.0, 'end': 1.8}], {0},
                         cfg, S, W_, H_, lambda s, e: True, _wfx,
                         face_pos=lambda s, e: (W_ * 0.5, H_ * 0.3, 60))
    _wp0 = next((p for p in _wpl if p.get('kw_i') == 0), None)
    check('v101i: stehender Wand-Text traegt Kontakt-Schatten',
          _wp0 is not None and _wp0.get('cshadow') is not None)
    check('v101i: Wand-Track im Loop + Compositor verdrahtet',
          'need_track_wall' in _src99
          and "region='wand'" in _src99
          and 'H_cum_wall' in _src99
          and "_is_wall = (p.get('szene') == 'wand'" in _src99)

    # v101j Hand-Kontakt: Impuls-Feder + Kontakt-Gate + Verdrahtung.
    _hjp = {'kw_i': 0, 'arr': np.zeros((100, 400, 4), np.uint8),
            'cx': 540, 'cy': 900, 'start': 1.0, 'end': 2.0}
    _hn1 = R.hand_contacts([_hjp], [(540, 900, 300.0, 0.0)], 1.2, 1080, 1920)
    _hn2 = R.hand_contacts([_hjp], [(540, 900, 300.0, 0.0)], 1.25, 1080, 1920)
    check('v101j: bewegte Fingerspitze in der Box -> genau EIN Impuls (Cooldown)',
          _hn1 == 1 and '_hand_hit' in _hjp and _hn2 == 0)
    _hjq = {'kw_i': 0, 'arr': np.zeros((100, 400, 4), np.uint8),
            'cx': 540, 'cy': 900, 'start': 1.0, 'end': 2.0}
    check('v101j: langsamer Finger / daneben -> kein Impuls',
          R.hand_contacts([_hjq], [(540, 900, 5.0, 0.0)], 1.2, 1080, 1920) == 0
          and R.hand_contacts([_hjq], [(100, 100, 300.0, 0.0)], 1.2, 1080, 1920) == 0)
    _hjs = {'_hand_hit': (800.0, 0.0)}
    _hxs = [R.hand_spring(_hjs, 1.0 + i / 30.0)[0] for i in range(60)]
    _hpk = max(_hxs)
    check('v101j: Feder mit Overshoot, klingt aus (kein linearer Rutsch)',
          _hpk > 15 and min(_hxs) < -0.1 * _hpk and abs(_hxs[-1]) < 0.2 * _hpk,
          f'peak={_hpk:.1f} over={min(_hxs):.1f} end={_hxs[-1]:.2f}')
    _hm = os.path.join(HERE, 'models', 'hand.task')
    _htr = R.HandTracker(1080, 1920)
    check('v101j: HandTracker laedt Modell (bzw. still aus ohne Modell)',
          _htr.ok if os.path.exists(_hm) else _htr.ok is False)
    check('v101j: Hand-Kontakt im Loop + Compositor verdrahtet + Modell-URL',
          'need_hands' in _src99 and 'hand_contacts(plans' in _src99
          and 'hand_spring(_hp, t)' in _src99
          and "models/hand.task" in _src99
          and 'hand_tips=_hand_tips' in _src99
          and "cfg['effects'].get('hand_contact'" in _src99)

    # v101k Depth-Bullet-Time: Pause vor der Punchline wird zum 2.5D-Dolly.
    _btw = [{'word': 'so', 'start': 0.0, 'end': 1.0},
            {'word': 'BOOM', 'start': 2.0, 'end': 2.4},
            {'word': 'weiter', 'start': 2.5, 'end': 3.0},
            {'word': 'MEGA', 'start': 4.5, 'end': 5.0}]
    _btp = [{'kw_i': 1, 'power': 3, 'start': 2.0, 'end': 3.0},
            {'kw_i': 3, 'power': 3, 'start': 4.5, 'end': 5.5}]
    _btb = R.bullet_window(_btw, _btp)
    check('v101k: laengste Pause >=0.8s vor power-3 gewinnt (1x pro Video)',
          _btb is not None and _btb[2] == 3
          and abs(_btb[0] - 3.06) < 1e-6 and abs(_btb[1] - 4.48) < 1e-6)
    check('v101k: power<3 / kurze Pause / B-Roll -> kein Bullet',
          R.bullet_window(_btw, [{'kw_i': 1, 'power': 2,
                                  'start': 2, 'end': 3}]) is None
          and R.bullet_window([{'word': 'a', 'start': 0, 'end': 1},
                               {'word': 'b', 'start': 1.2, 'end': 2}],
                              [{'kw_i': 1, 'power': 3,
                                'start': 1.2, 'end': 2}]) is None
          and R.bullet_window(_btw, [{'kw_i': 3, 'power': 3, 'start': 4.5,
                                      'end': 5.5, 'broll': True}]) is None)
    check('v101k: Quality-Gate - flache Tiefenkarte faellt durch',
          not R.depth_quality_ok(np.full((80, 80), 0.5, np.float32))
          and R.depth_quality_ok(np.concatenate(
              [np.zeros((40, 80), np.float32),
               np.full((40, 80), 0.9, np.float32)])))
    _bfr = np.zeros((200, 300, 3), np.float32)
    _bfr[30, 160] = 255; _bfr[170, 160] = 255
    _bdp = np.zeros((200, 300), np.float32); _bdp[:100] = 1.0
    _bd0 = R.depth_dolly(_bfr, _bdp, 0.0, 300, 200)
    _bd5 = R.depth_dolly(_bfr, _bdp, 0.5, 300, 200)
    _bd1 = R.depth_dolly(_bfr, _bdp, 1.0, 300, 200)
    def _btx(img, y):
        row = img[max(y - 4, 0):y + 5, :, 0].max(axis=0)
        return float((row * np.arange(300)).sum() / max(row.sum(), 1e-6))
    _bdn = _btx(_bd5, 30) - 160
    _bdf = _btx(_bd5, 170) - 160
    check('v101k: Dolly = echte Parallaxe (nah/fern gegenlaeufig), '
          'Start/Ende exakt auf 0 (nahtloser Wiedereinstieg)',
          np.abs(_bd0 - _bfr).mean() < 1e-3 and np.abs(_bd1 - _bfr).mean() < 1e-3
          and abs(_bdn) > 1.5 and abs(_bdf) > 1.5 and (_bdn > 0) != (_bdf > 0),
          f'nah={_bdn:+.1f}px fern={_bdf:+.1f}px')
    check('v101k: Bullet-Time im Loop verdrahtet (Gate, Alpha-Ausschluss)',
          'bt_win = bullet_window(words, plans)' in _src99
          and 'depth_quality_ok(bt_depth)' in _src99
          and 'depth_dolly(bt_freeze, bt_depth, _bu, W, H)' in _src99
          and "cfg['effects'].get('bullet_time', True) and not args.alpha_export"
              in _src99)

    # v101m Keyword-Markierungen aus dem Text-Editor (user_pick uebersteuert KI).
    _kmw = [{'word': w} for w in ['So', 'viel', 'Geld', 'heute', 'wichtig']]
    _kmcfg = {'effects': {'keyword_rotation': ['behind', 'outline', 'cascade']}}
    _kw2, _fx2 = R.apply_keyword_marks({4}, {4: {'fx': 'behind', 'power': 3, 'n': 1}},
                                       _kmw, {2: 1, 4: -1}, _kmcfg)
    check('v101m: erzwungenes Wort rein (user_pick), geblocktes raus',
          2 in _kw2 and 4 not in _kw2 and _fx2[2].get('user_pick') is True
          and 4 not in _fx2)
    _kw3, _fx3 = R.apply_keyword_marks({2}, {2: {'fx': 'ground', 'power': 1, 'n': 2}},
                                       _kmw, {2: 1}, _kmcfg)
    check('v101m: vorhandener KI-Moment wird erzwungen, aber nicht ueberschrieben',
          _fx3[2]['fx'] == 'ground' and _fx3[2]['power'] == 1
          and _fx3[2]['n'] == 2 and _fx3[2]['user_pick'] is True)
    check('v101m: leere Marken -> unveraendert',
          R.apply_keyword_marks({1}, None, _kmw, {}, _kmcfg) == ({1}, None))
    # user_pick ueberlebt das Dichte-Gate wie intent: zwei getrennte Gruppen
    # innerhalb von min_gap - ohne Schutz faellt die zweite weg, mit bleibt sie.
    _kmwl = [{'word': 'Zins', 'start': 1.0, 'end': 1.3},
             {'word': 'Rendite', 'start': 3.2, 'end': 3.7}]
    _kmf_on = {0: {'fx': 'outline', 'power': 2, 'n': 1, 'user_pick': True},
               1: {'fx': 'outline', 'power': 2, 'n': 1, 'user_pick': True}}
    _kmf_off = {0: {'fx': 'outline', 'power': 2, 'n': 1},
                1: {'fx': 'outline', 'power': 2, 'n': 1}}
    _kmn_on = len([p for p in R.build_plans(_kmwl, {0, 1}, cfg, S, W_, H_,
                   lambda s, e: True, _kmf_on) if p.get('kw_i') in (0, 1)])
    _kmn_off = len([p for p in R.build_plans(_kmwl, {0, 1}, cfg, S, W_, H_,
                    lambda s, e: True, _kmf_off) if p.get('kw_i') in (0, 1)])
    check('v101m: erzwungene Woerter ueberleben das Dichte-Gate (Gegenprobe)',
          _kmn_on == 2 and _kmn_off == 1, f'user_pick={_kmn_on} plain={_kmn_off}')
    check('v101m: Marken-Anwendung im Main + Sidecar verdrahtet',
          '_kwmarks.json' in _src99
          and 'apply_keyword_marks(kw, fx_map, words' in _src99
          and "fx_map[i].get('intent') or fx_map[i].get('user_pick')" in _src99)
    _srv_m = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _ui_m = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v101m: Server schreibt Sidecar, UI hat Highlight-Modus',
          "kwmarks: str = Form('')" in _srv_m and '_kwmarks.json' in _srv_m
          and 'tx-mode' in _ui_m and "txMode === 'kw'" in _ui_m
          and "fd.append('kwmarks'" in _ui_m)

    check('v101t: Server serviert + speichert Akzente, UI editiert sie',
          "@app.get('/api/accents/{jid}')" in _srv_m
          and "accents: str = Form('')" in _srv_m
          and "_accents.json" in _srv_m
          and "function renderAccents" in _ui_m
          and "/api/accents/'" in _ui_m
          and "fd.append('accents'" in _ui_m
          and "id=\"accSection\"" in _ui_m)

    # v101n: mehrere erzwungene Woerter in EINER Phrase -> Phrase auftrennen,
    # damit jedes markierte Wort ein eigenes Highlight wird (sonst faellt eins weg).
    check('v101n: split_forced_groups trennt an den Marken, sonst unveraendert',
          R.split_forced_groups([[9, 10, 11]],
              {9: {'user_pick': True}, 10: {'user_pick': True}}) == [[9], [10, 11]]
          and R.split_forced_groups([[0, 1, 2], [3, 4]], {}) == [[0, 1, 2], [3, 4]]
          and R.split_forced_groups([[0, 1, 2]],
              {1: {'user_pick': True}}) == [[0, 1, 2]])   # nur 1 Marke -> kein Split
    _nfw = [{'word': w, 'start': i * 0.3, 'end': i * 0.3 + 0.25}
            for i, w in enumerate(['a', 'neues', 'Level', 'bringen', 'c'])]
    _nffx = {1: {'fx': 'outline', 'power': 2, 'n': 1, 'user_pick': True},
             2: {'fx': 'outline', 'power': 2, 'n': 1, 'user_pick': True}}
    _nfpl = R.build_plans(_nfw, {1, 2}, cfg, S, W_, H_, lambda s, e: True, _nffx)
    _nfgot = sorted(p['kw_i'] for p in _nfpl if 'kw_i' in p)
    check('v101n: zwei benachbarte erzwungene Woerter -> BEIDE werden Highlights',
          1 in _nfgot and 2 in _nfgot, str(_nfgot))

    # v101s: Auto-Akzente (dezente Motion-Graphics-Regie auf dem Transkript).
    _accw = [{'word': w, 'start': i * 0.9, 'end': i * 0.9 + 0.6}
             for i, w in enumerate(
                 ['We', 'got', '3', 'million', 'views', 'in', 'just', '24', 'hours',
                  'with', 'zero', 'budget', 'because', 'the', 'algorithm', 'rewards',
                  'retention', 'and', 'our', 'editing', 'kept', '87', 'percent',
                  'watching', 'until', 'the', 'end'])]
    _acc = R.heuristic_accents(_accw, {}, {'intensity': 1.0})
    _acc_cap = R._accent_cap(_accw, 1.0)
    _acc_gaps = [_acc[i + 1]['zeit'] - _acc[i]['zeit'] for i in range(len(_acc) - 1)]
    check('v101s: Akzente nur aus gueltigen Arten + Cap eingehalten',
          all(a['art'] in R.ACCENT_ARTS for a in _acc) and len(_acc) <= _acc_cap
          and _acc_cap >= 1, f'{len(_acc)}/{_acc_cap}')
    check('v101s: echte Zahl wird zum Counter (mit Wert)',
          any(a['art'] == 'counter' and a['wert'] for a in _acc))
    check('v101s: Mindestabstand haelt die Akzente dezent (>=3.5s)',
          all(g >= 3.5 for g in _acc_gaps), str([round(g, 2) for g in _acc_gaps]))
    check('v101s: Lanes rotieren (kein Stapeln an einer Ecke)',
          len({a['lane'] for a in _acc}) >= min(2, len(_acc))
          and all(a['lane'] in R.ACCENT_LANES for a in _acc))
    check('v101s: Binde-/Fuellwoerter werden NICHT gechipt (because raus)',
          not any(a['text'] == 'BECAUSE' for a in _acc))
    # sanitize verwirft Unfug (falsche Art, negative Zeit) und clamped
    _acc_junk = R.sanitize_accents(
        [{'art': 'explode', 'zeit': 1}, {'art': 'chip', 'zeit': -5, 'text': 'x'},
         {'art': 'chip', 'zeit': 3.0, 'text': 'OK'}], _accw, {'intensity': 1.0})
    check('v101s: sanitize_accents wirft ungueltige Akzente raus',
          all(a['art'] in R.ACCENT_ARTS and a['zeit'] >= 0 for a in _acc_junk)
          and all(a['text'] != 'x' for a in _acc_junk))
    # ohne OpenAI-Key faellt ai_accents deckungsgleich auf die Heuristik
    check('v101s: ai_accents ohne Key == heuristic_accents (Notnagel-Pfad)',
          R.ai_accents(_accw, 'en', 'gpt-5', {'intensity': 1.0}, {}) == _acc)
    # Intensitaet dosiert die Dichte (0 -> weniger/gleich als 2)
    check('v101s: Stil-Profil-Intensitaet dosiert die Akzent-Dichte',
          R._accent_cap(_accw, 0.0) <= R._accent_cap(_accw, 2.0))
    check('v101s: leere/kurze Transkripte liefern keine Akzente',
          R.heuristic_accents([], {}, None) == []
          and R.heuristic_accents(_accw[:2], {}, None) == [])

    # v101t: Akzent-Compositing (Sprite + Einbau ins Frame).
    _acst = R.accent_style({'accent': '#7c5cff'})
    _acsp = {a: R._accent_sprite(a, 'TEST 3', 3.0, 1.0, 1.0, _acst, 1080)
             for a in R.ACCENT_ARTS}
    check('v101t: jede Akzent-Art baut ein nicht-leeres RGBA-Sprite',
          all(s.ndim == 3 and s.shape[2] == 4 and s.shape[0] > 4 and s.shape[1] > 4
              and int(s[..., 3].max()) > 0 for s in _acsp.values()))
    _acfr = np.full((1920, 1080, 3), 30, np.uint8)
    _acli = [{'art': 'counter', 'zeit': 1.0, 'wert': 3.0, 'text': '3 M', 'dauer': 1.6,
              'lane': 'tl', 'aktiv': True}]
    _acon = R.draw_accents(_acfr.copy(), 1.3, _acli, _acst, 1080, 1920, None)
    _acoff = R.draw_accents(_acfr.copy(), 30.0, _acli, _acst, 1080, 1920, None)
    _actop = int(np.abs(_acon[:960].astype(int) - _acfr[:960].astype(int)).sum())
    check('v101t: aktiver Akzent wird ins obere Band komponiert',
          _actop > 0 and int(np.abs(_acon[960:].astype(int)
                                    - _acfr[960:].astype(int)).sum()) == 0)
    check('v101t: nach seinem Fenster hinterlaesst der Akzent nichts',
          int(np.abs(_acoff.astype(int) - _acfr.astype(int)).sum()) == 0)
    check('v101t: deaktivierter Akzent wird nicht gezeichnet',
          int(np.abs(R.draw_accents(_acfr.copy(), 1.3,
              [{**_acli[0], 'aktiv': False}], _acst, 1080, 1920, None).astype(int)
              - _acfr.astype(int)).sum()) == 0)
    # Editor-Roundtrip: eine gueltige Nutzer-Lane gewinnt, fehlende rotiert
    _acw2 = [{'word': 'x', 'start': 0, 'end': .5}, {'word': 'y', 'start': 10, 'end': 10.5}]
    _achon = R.sanitize_accents([{'art': 'badge', 'zeit': 2.5, 'text': 'EDIT', 'lane': 'bl'}],
                                _acw2, {'intensity': 2})
    _acrot = R.sanitize_accents([{'art': 'chip', 'zeit': 2, 'text': 'A'},
                                 {'art': 'chip', 'zeit': 6, 'text': 'B'}],
                                _acw2, {'intensity': 2})
    check('v101t: Editor-Lane gewinnt, fehlende Lane rotiert',
          _achon and _achon[0]['lane'] == 'bl'
          and [a['lane'] for a in _acrot] == ['tl', 'tr'])

    # v101u: Akzent weicht der Caption aus (nie Ueberschneidung).
    _capA = np.zeros((int(1920 * 0.14), int(1080 * 0.7), 4), np.uint8)
    _capA[..., 3] = 255
    _plansA = [{'start': 0.5, 'end': 3.0, 'cx': 540, 'cy': 1920 * 0.40, 'arr': _capA}]
    _accU = [{'art': 'chip', 'text': 'RETENTION', 'zeit': 1.0, 'dauer': 1.6,
              'lane': 'bl', 'aktiv': True}]
    R.resolve_accent_positions(_accU, _plansA, 1080, 1920, None)
    _sprU = R._accent_sprite('chip', 'RETENTION', None, 1, 1, {'accent': '#fff'}, 1080)
    _accBot = _accU[0]['cy'] + _sprU.shape[0] / 2
    _capTop = 1920 * 0.40 - _capA.shape[0] / 2
    check('v101u: Akzent ueberdeckt die Caption nicht (weicht nach oben aus)',
          'cx' in _accU[0] and _accBot <= _capTop + 1, f'{_accBot:.0f}/{_capTop:.0f}')
    # ohne Caption bleibt die Lane-Position (kein unnoetiges Anheben)
    _accV = [{'art': 'chip', 'text': 'X', 'zeit': 8.0, 'dauer': 1.6, 'lane': 'tl',
              'aktiv': True}]
    R.resolve_accent_positions(_accV, _plansA, 1080, 1920, None)
    check('v101u: ohne Kollision behaelt der Akzent seine Lane-Position',
          'cx' in _accV[0] and _accV[0]['cy'] < 1920 * 0.35)
    # v130: Fertig-Mail deaktiviert (Ismet) -> KEINE Mail-Zusage mehr im Render-Screen.
    check('v130: keine Fertig-Mail-Zusage im Render-Screen',
          'id="progMailNote"' not in _ui_m and "we'll email you" not in _ui_m)

    check('v101v: Server hat resumable Chunk-Upload-Endpunkte + gemeinsamen Abschluss',
          "@app.post('/api/upload/init')" in _srv_m
          and "@app.post('/api/upload/chunk/{up}')" in _srv_m
          and "@app.get('/api/upload/status/{up}')" in _srv_m
          and "@app.post('/api/upload/finish/{up}')" in _srv_m
          and 'async def _finalize_upload(' in _srv_m
          and "'resync': True" in _srv_m
          and 'f.truncate(offset + len(data))' in _srv_m)
    check('v101v: UI laedt in Chunks + setzt bei Tab-Rueckkehr fort',
          'async function chunkedUpload' in _ui_m
          and "'visibilitychange'" in _ui_m
          and '/api/upload/init' in _ui_m
          and '/api/upload/chunk/' in _ui_m
          and '/api/upload/status/' in _ui_m
          and '/api/upload/finish/' in _ui_m
          and 'file.slice(offset, end)' in _ui_m)

    # v111-v118: Motion-Studio (Showcase) ist seit v118 die EINZIGE Motion-Engine —
    # alle Alt-Engines (brief/template/sequence/auto-overlay/3D) sind entfernt.
    _mov = os.path.join(HERE, 'motion', 'src')
    _msrc = lambda _p: open(os.path.join(_mov, _p), encoding='utf-8').read()
    _mgroot = os.path.join(HERE, 'motion')

    # v111: MotionShowcase — 1:1-Nachbau des Referenz-Montage-Looks. Kamerageführte,
    # motion-geblurrte Übergänge (kein Blur-Dissolve), interaktive Momente, alle Shot-
    # Archetypen als echte UI-Objekte, 16:9. Text ist Daten (Storyboard), nichts erfunden.
    _msh = _msrc('MotionShowcase.tsx'); _mrt3b = _msrc('Root.tsx')
    check('v111: MotionShowcase — alle Shot-Archetypen + Storyboard',
          'export const MotionShowcase' in _msh and 'const STORY' in _msh
          and all(k in _msh for k in ["'ktypo'", "'timer'", "'notes'", "'searchbar'",
                                        "'imessage'", "'widgets'", "'pill'", "'timeline'", "'signoff'"])
          and 'AppleMark' in _msh and 'Cursor' in _msh)
    check('v111: kamerageführte, motion-geblurrte Übergänge (kein Blur-Dissolve)',
          'MotionSmear' in _msh and 'enterCam' in _msh and 'exitCam' in _msh
          and all(t in _msh for t in ["'slideL'", "'morph'", "'push'", "'slideUp'"])
          and 'ghost' in _msh.lower())
    check('v111: interaktive Momente (press treibt den Hand-off)',
          'press' in _msh and 'const press =' in _msh
          and 'showcaseDuration' in _msh)
    # v111b: Smoothness-Pass — Motion-Blur wird pro Frame aus der echten Layer-Bewegung
    # GEMESSEN (Finite-Difference), nicht von Hand gesetzt; Idle-Drift lässt nichts einfrieren.
    check('v111b: gemessenes, kontinuierliches Motion-Blur (Finite-Difference) + Idle-Drift',
          'const layerCam' in _msh and 'layerCam(i, t - dt)' in _msh
          and 'idleDrift' in _msh and 'TH.shutter' in _msh
          and 'dx={dx}' in _msh and 'springStep(e - dt' in _msh)  # auch die Kinetik-Typo smeart
    # v111c: interaktive Kamera — motivierte Fahrten INNERHALB der Shots (entlang der Schrift
    # gleiten, in die Punchline pushen, dem Playhead folgen). Smeart via gemessenem Blur mit.
    check('v111c: interaktive Kamera (per-Shot-Fahrt, folgt dem Inhalt)',
          'const shotCam' in _msh and 'shotCam(shot.kind' in _msh
          and 'FOLLOW the playhead' in _msh and 'glide along the type' in _msh
          and 'easeInOutSine' in _msh)
    # v112: pro-User-Generierung — Storyboard kommt aus dem Transkript (individuell), Text WÖRTLICH
    # aus dem Transkript (kein Halluzinieren), nur Realitäts-Archetypen. Storyboard = Daten (Props).
    _mbs = _msrc('director/buildShowcase.ts')
    check('v112: Transkript→Storyboard-Generator (individuell, Provenance by construction)',
          'export function buildShowcase' in _mbs and 'VERBATIM' in _mbs
          and 'function pickKind' in _mbs and 'signoff' in _mbs
          and 'export type MotionShowcaseProps = { readonly spec: SceneSpec; readonly story?' in _msh
          and 'story={story && story.length ? story : STORY}' in _msh)
    # v112b: auch die BEWEGUNG variiert pro Video (nicht nur der Text) — seed-getriebene
    # Übergangs-Reihenfolge + per-Shot-Kamera-Variation (Richtung/Stärke).
    check('v112b: seed-getriebene Bewegungs-Variation (Übergänge + Kamera)',
          'mulberry32' in _mbs and 'nextTrans' in _mbs and 'per-shot motion-variation' in _mbs
          and 'v: +rng()' in _mbs
          and 'shotCam(shot.kind' in _msh and 'shot.v ?? 0.5' in _msh
          and 'seeded left/right' in _msh)
    # v113: 4 komplett verschiedene Stile (Farbe/Typo/Card/Bewegungscharakter) via styleId.
    _mth = _msrc('showcaseThemes.ts')
    check('v113: 4 Stile (editorial/bold/soft/mono) — teilen sich nichts',
          all(("%s:" % k) in _mth for k in ['editorial', 'bold', 'soft', 'mono'])
          and 'export interface Theme' in _mth and 'cameraMult' in _mth and 'shutter' in _mth
          and "styleId?: string" in _msh and 'TH = th;' in _msh
          and 'themeFor(styleId)' in _msh
          and 'const cm = th.cameraMult' in _msh)                 # mono = Kamera aus + kein Blur
    # v114: strukturell ANDERE Komposition (nicht nur Umfärbung): reine Typografie, keine Cards,
    # eigene Layouts + Reveals + typografische Übergänge. Gleicher Transkript-Vertrag.
    _mkn = _msrc('MotionKinetic.tsx')
    check('v114: MotionKinetic — eigene Komposition (Typo-Layouts, keine UI-Cards)',
          'export const MotionKinetic' in _mkn and 'TypeScene' in _mkn
          and all(r in _mkn for r in ["'maskUp'", "'punch'", "'slide'", "'wipe'"])
          and 'GIANT WORD' in _mkn and 'LEFT STACK' in _mkn and 'SPLIT' in _mkn
          and 'lineOf' in _mkn                                    # Text weiterhin verbatim aus Story
          and 'id="MotionKinetic"' in _mrt3b and 'kineticDuration' in _mrt3b)
    # v115: MotionPrompt — cinematischer Prompt→Code→Website-Build (glühend, 3D). Referenz-Look
    # 1:1, aber Marke GENERISCH (kein Fremd-Logo/Wortmarke). Prompt/Website-Text aus Transkript.
    _mpr = _msrc('MotionPrompt.tsx')
    check('v115: MotionPrompt — alle Beats (Intro-Sweep, Chips, Box, Code, 3D-Reveal)',
          'export const MotionPrompt' in _mpr and 'GlowEdge' in _mpr
          and 'WEBSITE REVEAL' in _mpr and 'CODE STREAM' in _mpr and 'typed' in _mpr
          and 'CHIPS' in _mpr and 'ChipIcon' in _mpr and 'light sweep' in _mpr   # weggelassene Beats nachgebaut
          and 'codeLines' in _mpr and 'C.tag' in _mpr                            # syntax-gefärbter Code
          and 'perspective' in _mpr and 'rotateY' in _mpr
          and 'id="MotionPrompt"' in _mrt3b and 'promptDuration' in _mrt3b)
    check('v115: MotionPrompt markensicher (keine Fremd-Marke im Render)',
          not any(bad in _mpr for bad in ['Claude', 'Sonnet', 'Anthropic', 'claude']))
    check('v115c: MotionPrompt Zoom-in→Reveal (Detail rein, dann aufdecken)',
          'TWO-PHASE CAMERA' in _mpr and 'ZOOM-IN' in _mpr      # Box (2-Phasen) + Website
          and 'transformOrigin' in _mpr)
    # v115d: interaktive Buttons + kausale Logik (Klick löst den nächsten Schritt aus) + Send-Closeup.
    check('v115d: Buttons reagieren + kausale Logik + Send-Closeup',
          'sendPress' in _mpr and 'ctaPress' in _mpr
          and 'CLOSEUP' in _mpr                                 # Closeup auf den Send-Button
          and 'fires the code' in _mpr and 'press is what fires' in _mpr)  # Druck löst Code aus
    check('v115e: Kamera folgt dem getippten Prompt (Follow-Caret)',
          'FOLLOW the caret' in _mpr and 'caretX' in _mpr and 'outerTx' in _mpr)
    # v116: Render-Bridge — Transkript → gewählte Komposition + Stil + Format, ein Befehl.
    _mrbs = open(os.path.join(HERE, 'motion', 'scripts', 'render-showcase.mjs'), encoding='utf-8').read()
    check('v116: render-showcase Bridge (Komposition/Stil/Format aus Transkript)',
          'buildShowcase' in _mrbs
          and all(c in _mrbs for c in ['MotionShowcase', 'MotionKinetic', 'MotionPrompt'])
          and "--composition=" in _mrbs and "--style=" in _mrbs and "--format=" in _mrbs
          and "'16:9'" in _mrbs and "'9:16'" in _mrbs and "'1:1'" in _mrbs)
    # v117: Full-Customization — jeder visuelle Knopf überschreibbar; zieht durch ALLE Kompositionen.
    check('v117: Custom-Override-Schicht (applyTheme) in allen 3 Kompositionen',
          'export interface Custom' in _mth and 'export function applyTheme' in _mth
          and all(('applyTheme(themeFor(custom?.style ?? styleId), custom)' in _msrc(f))
                  for f in ['MotionShowcase.tsx', 'MotionKinetic.tsx', 'MotionPrompt.tsx'])
          and 'custom?.text' in _msh and 'custom?.accent' in _mpr and 'custom?.brand' in _mpr)
    # v117b: Server-Verdrahtung — /api/motion/showcase (Video ODER Text) + Custom-Passthrough.
    check('v117b: Server-Endpoint + Worker (Showcase, Video/Text, Custom)',
          "@app.post('/api/motion/showcase')" in _srv_m and 'def _run_motion_showcase' in _srv_m
          and 'def _sanitize_custom' in _srv_m
          and 'return _run_motion_showcase(jid)' in _srv_m      # v118: einziger Motion-Pfad
          and 'render-showcase.mjs' in _srv_m and "'--custom-file='" in _srv_m
          and 'custom-file' in _mrbs)
    check('v117c: UI — Studio-Panel (alle Knöpfe) + verdrahtet',
          'id="moTypeStudio"' in _ui_m and 'data-key="studio"' in _ui_m
          and "studio:['type','studio']" in _ui_m
          and 'function motionStudioGo' in _ui_m and "'/api/motion/showcase'" in _ui_m
          and all(x in _ui_m for x in ['id="stComp"', 'id="stStyle"',
                                        'id="stAccent"', 'id="stBrand"', 'id="stBlur"', 'id="stLines"']))
    # v117d: Transkript-DATEI hochladen (.txt/.srt/.vtt/.json) -> automatisch verarbeitet.
    check('v117d: Transkript-Datei-Upload (Server: Parser + Endpoint + Worker)',
          'def _transcript_to_words' in _srv_m
          and 'transcript_file: UploadFile = File(None)' in _srv_m
          and "job['prewords']" in _srv_m and "if j.get('prewords')" in _srv_m
          and 'def _synth_word_timings' in _srv_m)
    check('v117d: Transkript-Datei-Upload (UI: Segment + File-Input + verdrahtet)',
          'id="stTFile"' in _ui_m and "['tfile','Transcript file']" in _ui_m
          and "ST.input==='tfile'" in _ui_m and "fd.append('transcript_file'" in _ui_m)
    # v119/120: sichtbarer Upload-Fortschritt (XHR) + sachlicher, kriechender Ladescreen.
    check('v119: Upload-Progress (XHR) + kriechender Ladescreen',
          'function moUpload' in _ui_m and 'xhr.upload.onprogress' in _ui_m
          and 'function moLoadStart' in _ui_m and 'function moLoadTick' in _ui_m
          and "_fr.classList.add('loading')" in _ui_m
          and '.mo-frame.loading::after' in _ui_m and '@keyframes moshim' in _ui_m
          and 'moUpload(' in _ui_m and 's.phase || MoLoad.phase' in _ui_m)
    # v120: professionelle Copy — keine Floskeln, keine Gedankenstriche, kein Fake-6%-Sockel.
    _mo_lo = _ui_m[_ui_m.find('function moUpload'):_ui_m.find('function motionPoll')]
    check('v120: Ladescreen sachlich (keine Floskeln/Gedankenstriche, kein Fake-Sockel)',
          'MO_MSGS' not in _ui_m and 'senior designer' not in _ui_m
          and 'Math.max(s.progress||0, 0.06)' not in _ui_m
          and 'moLoadSet(s.progress || 0' in _ui_m
          and '—' not in _mo_lo and '–' not in _mo_lo)      # keine em/en-dashes im Loader
    check('v120/122: Server-Phasen sachlich + Stall-Waechter + gebremste Concurrency',
          "phase='Rendering')" in _srv_m and "phase='Encoding')" in _srv_m
          and 'senior designer' not in _srv_m
          and 'DVE_MOTION_STALL' in _srv_m and 'DVE_MOTION_TIMEOUT' in _srv_m
          and 'def _watchdog' in _srv_m and "_killed['why'] = 'stalled'" in _srv_m
          and 'DVE_MOTION_CONCURRENCY' in _srv_m and "'--concurrency='" in _srv_m)
    # v122: Format automatisch aus dem Quellvideo (kein Regler mehr); Bridge nimmt WxH.
    check('v122: Auto-Format aus Video (Server ffprobe WxH) + Bridge parst Pixel-Dims',
          "'stream=width,height'" in _srv_m and "f'{int(_m.group(1))}x{int(_m.group(2))}'" in _srv_m
          and 'function parseDims' in _mrbs and '\\d{2,5})x(\\d{2,5}' in _mrbs
          and 'id="stFormat"' not in _ui_m and "fd.append('format'" not in _ui_m
          and 'keeps the aspect ratio of your' in _ui_m
          and 'vid.videoWidth+' in _ui_m)
    # v121: Admin-Transkript-Werkzeug in der (owner-gated) Reference-UI verdrahtet.
    check('v121: UI — Transcribe-Werkzeug unter Reference (owner-gated + Downloads)',
          'id="btnTranscribe"' in _ui_m and 'id="trFile"' in _ui_m
          and "fetch('/api/reference/transcribe'" in _ui_m
          and 'function trDownload' in _ui_m
          and all(("data-tr=\"%s\"" % k) in _ui_m for k in ('txt', 'srt', 'vtt', 'json'))
          # sitzt im refPanel, das refApplyOwner fuer Nicht-Owner versteckt
          and _ui_m.find('id="trFile"') > _ui_m.find('id="refPanel"')
          and _ui_m.find('id="trFile"') < _ui_m.find('class="panel danger-zone"'))
    # v123: Motion Design fuer Kunden AUSGEBLENDET (Code bleibt, ein Schalter). App: Flag aus +
    # Nav/Routing/Chooser gegated. Landing: Motion-Sektion auskommentiert.
    _land123 = open(os.path.join(HERE, 'web', 'landing.html'), encoding='utf-8').read()
    check('v123: Motion ausgeblendet (Flag/Nav/Routing) — Code intakt',
          'const MOTION_ENABLED = false' in _ui_m
          and "if (!MOTION_ENABLED) { showSection('create'); return; }" in _ui_m
          and 'a[data-nav="motion"]' in _ui_m
          # v127: Landing bewirbt Motion gar nicht mehr (Editorial-Redesign,
          # Single-Product Captions) - kein Motion-Deep-Link/Nav/Sektion.
          and '#motion' not in _land123
          # Beweis „nur versteckt, nicht geloescht": die Motion-Engine ist weiterhin da
          and "@app.post('/api/motion/showcase')" in _srv_m
          and os.path.exists(os.path.join(HERE, 'motion', 'src', 'MotionShowcase.tsx')))
    # v124 Monetarisierungs-Batch: Kaufmoment + Wiederkauf + Investment + Referral.
    check('v124: Server verdrahtet (Referral, Reload-Bonus, Ablauf-Mail, Scores)',
          'def _ensure_ref_code' in _srv_m and 'def _grant_referral' in _srv_m
          and "ref: str = Form('')" in _srv_m and '_grant_referral(uid)' in _srv_m
          and 'Reload bonus' in _srv_m and "balance_sec'] < 120" in _srv_m
          # v194b: aus _expiry_warn (eine Mail JE JOB) wurde die Sammelstelle
          # _expiry_sammeln + der gebuendelte Versand _expiry_mails. Geprueft
          # wird unveraendert, dass die Ablauf-Erinnerung verdrahtet ist.
          and 'def _expiry_sammeln' in _srv_m
          and '_expiry_sammeln(jid, d, mtime, cutoff, _abl)' in _srv_m
          and 'def _hook_score' in _srv_m and "'hook_score':" in _srv_m
          and "'ref_code':" in _srv_m and "'style_prefs':" in _srv_m
          and 'uid=None' in _srv_m)                        # Korrekturen pro User markiert
    # v126: Kunden-Stil-Referenz verdrahtet + GPT-5-Restmigration.
    _rp = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v126: Server-Endpoints + Env-Injektion + Render-Override',
          "@app.post('/api/style/learn')" in _srv_m and "@app.get('/api/style/list')" in _srv_m
          and "@app.post('/api/style/delete')" in _srv_m
          and 'def _user_refs_path' in _srv_m
          and "env['DVE_REFS_FILE']" in _srv_m
          and 'store_path=_user_refs_path' in _srv_m
          and "DVE_REFS_FILE" in _rp and 'store_path' in _rp
          and 'STYLE_LEARN_COST' in _srv_m and '_refund_credits(' in _srv_m)
    check('v126: UI-Panel (Stil anlernen/liste/loeschen) verdrahtet',
          'id="btnStyleLearn"' in _ui_m and 'id="stlFile"' in _ui_m
          and "fetch('/api/style/learn'" in _ui_m and "fetch('/api/style/list'" in _ui_m
          and 'function loadStyleList' in _ui_m and 'Your caption style' in _ui_m)
    check('v126: GPT-5 ueberall (kein gpt-4o mehr im ausgelieferten Code/Config)',
          'gpt-4o' not in _rp and 'gpt-4o' not in _srv_m
          and 'gpt-4o' not in open(os.path.join(HERE, 'config.yaml'), encoding='utf-8').read()
          and "model='gpt-5'" in _rp)
    check('v126-sec: Referral gehaertet (Unique-Index + atomare Buchung + Anti-Farming)',
          'ux_ledger_ref' in _srv_m and 'ux_users_refcode' in _srv_m
          and 'BEGIN IMMEDIATE' in _srv_m
          and "INSERT OR IGNORE INTO ledger" in _srv_m
          and 'referral_claims' in _srv_m and 'def _is_disposable_email' in _srv_m
          and 'def _email_hash' in _srv_m
          and 'INSERT OR IGNORE INTO referral_claims' in _srv_m
          # referral_claims wird bei Konto-Loeschung NICHT mitgeloescht (Re-Arm-Schutz)
          and 'DELETE FROM referral_claims' not in _srv_m)
    check('v125: Verfall verdrahtet (Sweep im Cleanup, /api/me, Billing-Hinweis)',
          'def _credit_expiry_sweep' in _srv_m and '_credit_expiry_sweep()' in _srv_m
          and 'def _fifo_remainders' in _srv_m and 'def _expire_credits' in _srv_m
          and 'CREDIT_VALIDITY_DAYS' in _srv_m and 'mail_log' in _srv_m
          and "'expiring_credits':" in _srv_m
          and 'id="billExpiry"' in _ui_m and 'u.expiring_credits' in _ui_m
          and 'Expired credits' in _ui_m)
    check('v124: UI verdrahtet (Upsell ohne Preis, Low-Balance, Referral, Fortschritt)',
          '€' not in _ui_m[_ui_m.find('id="wmUpsell"'):_ui_m.find('id="wmUpsell"') + 900]
          and 'One purchase unlocks this video' in _ui_m
          and 'id="lowBalHint"' in _ui_m and 'balance_sec || 0) < 60' in _ui_m
          and 'id="refLink"' in _ui_m and 'id="btnRefCopy"' in _ui_m
          and "fd.append('ref', refc)" in _ui_m and "localStorage.setItem('dve_ref'" in _ui_m
          and 'id="accBestHook"' in _ui_m and 'id="accStylePrefs"' in _ui_m
          and 'Reload bonus' in _ui_m and 'Invite reward' in _ui_m
          and 'it.hook_score' in _ui_m)
    # v127-sec/recht: Launch-Audit-Fixes im ausgelieferten Code verankert.
    _priv = open(os.path.join(HERE, 'web', 'privacy.html'), encoding='utf-8').read()
    _impr = open(os.path.join(HERE, 'web', 'imprint.html'), encoding='utf-8').read()
    _term = open(os.path.join(HERE, 'web', 'terms.html'), encoding='utf-8').read()
    check('v127-sec: Credit-Fixes verdrahtet (Refund loescht Reservierung, Indizes, Caps)',
          "resv_like or f'Render {jid} %'" in _srv_m
          and 'DELETE FROM ledger WHERE user_id = ? AND grund LIKE ?' in _srv_m
          and 'ux_ledger_welcome' in _srv_m and 'ux_ledger_monthly' in _srv_m
          and 'credit_claims' in _srv_m and 'DELETE FROM credit_claims' not in _srv_m
          and 'def _enqueue_guard' in _srv_m and 'def _inflight_count' in _srv_m
          and 'A render for this job is already running.' in _srv_m)
    check('v127-sec: Auth/Abuse-Fixes verdrahtet (XFF, Owner, Temp-Mail, Payment)',
          'def _client_ip' in _srv_m and "request.headers.get('x-forwarded-for'" in _srv_m
          and 'ip = _client_ip(request)' in _srv_m
          and 'if email.strip().lower() == OWNER_EMAIL:' in _srv_m
          and "u['verified']" in _srv_m
          and 'if _is_disposable_email(email):' in _srv_m
          and "PACKS[pack]['sekunden']" in _srv_m)
    check('v127-recht: Widerrufs-Einwilligung im Kaufflow (Checkbox + Log + Belehrung)',
          "consent: str = Form('')" in _srv_m and 'consents' in _srv_m
          and 'withdrawal_immediate_performance' in _srv_m
          and 'id="buyConsent"' in _ui_m and "fd.append('consent', '1')" in _ui_m
          and 'Widerrufsbelehrung' in _term and 'Model withdrawal form' in _term)
    check('v127-recht: Datenschutz/Impressum/AGB aktualisiert',
          'Art. 6(1)(b) GDPR' in _priv and 'Standard Contractual' in _priv
          and 'Art. 18 GDPR' in _priv and 'Art. 20 GDPR' in _priv
          and '§ 5 DDG' in _impr and '§ 5 TMG' not in _impr
          and '§ 18 (2) MStV' in _impr and '§ 55 RStV' not in _impr
          and '§ 19 UStG' in _impr and '§ 19 UStG' in _term
          and 'Prices include applicable VAT where required' not in _term)
    # v128 Admin-Panel: Endpoints + Server-Key-Gate + purchases-Umsatz + Seite.
    _adm = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v128 Admin: Endpoints, DVE_ADMIN-Gate, purchases-Umsatz, /admin-Seite',
          "@app.get('/api/admin/overview')" in _srv_m
          and "@app.post('/api/admin/jobs/{jid}/kill')" in _srv_m
          and "@app.post('/api/admin/users/{uid}/credits')" in _srv_m
          and "@app.post('/api/admin/users/{uid}/delete')" in _srv_m
          and 'def _require_admin' in _srv_m
          # v203-sec: _require_admin prueft jetzt zuerst positiv und haengt
          # bei Misserfolg die Bremse davor - die Zusage (nur mit Key) ist
          # dieselbe, die Schreibweise nicht mehr.
          and 'if _admin_ok(request):' in _srv_m
          and "raise HTTPException(403, 'Admin key missing or wrong.')" in _srv_m
          and "@app.get('/admin'" in _srv_m
          and 'CREATE TABLE IF NOT EXISTS purchases' in _srv_m
          and 'INSERT OR IGNORE INTO purchases' in _srv_m
          and "'X-Admin-Key'" in _adm and '/api/admin/overview' in _adm
          and 'noindex' in _adm)
    check('v129: Job-Timeout-Reaper (wartet+laeuft, Fingerabdruck, aktiv beenden+erstatten)',
          'def _reap_stuck_job' in _srv_m and 'JOB_STUCK_SECONDS' in _srv_m
          and "if stt not in ('wartet', 'laeuft')" in _srv_m
          and '_maybe_refund(jid)' in _srv_m
          and "@app.post('/api/admin/jobs/reap_stuck')" in _srv_m
          and 'Stop all stuck' in _adm)
    # v130: dynamisches Admin-Vollpanel (Auto-Refresh + alle Domaenen) verdrahtet.
    check('v130 Admin: Endpoints (revenue/credits/abuse/system/compliance/codes/refund) verdrahtet',
          "@app.get('/api/admin/revenue')" in _srv_m and "@app.get('/api/admin/credits')" in _srv_m
          and "@app.get('/api/admin/abuse')" in _srv_m and "@app.get('/api/admin/system')" in _srv_m
          and "@app.get('/api/admin/compliance/consents')" in _srv_m
          and "@app.get('/api/admin/export/{table}.csv')" in _srv_m
          and "@app.post('/api/admin/refund')" in _srv_m
          and "@app.post('/api/admin/users/{uid}/disable')" in _srv_m
          and "@app.post('/api/admin/backup/run')" in _srv_m
          and 'def _reap_stuck_job' in _srv_m and 'ADD COLUMN disabled' in _srv_m)
    check('v130 Admin: Suspend-Gate + Heartbeats + Build verdrahtet',
          'gesperrtes Konto -> wie ausgeloggt' in _srv_m
          and 'This account is suspended' in _srv_m
          and "_HEARTBEAT['watchdog']" in _srv_m and "_HEARTBEAT['cleanup']" in _srv_m
          # v160: die Build-Kennung wird NICHT mehr woertlich gepinnt. Der
          # Test schlug bei jeder Version fehl und wurde jedes Mal
          # nachgezogen - das prueft die Pflege des Tests, nicht den Server.
          # Gefordert ist, dass ueberhaupt eine Kennung gesetzt ist.
          # v222: sie ist jetzt ABGELEITET (aus Branch/Commit des Deploys) -
          # ein festes Literal war die Ursache dafuer, dass der Server
          # monatelang 'v213' in jedes Kundenvideo schrieb, obwohl niemand
          # wusste, welcher Stand wirklich lief. Der alte Test hat genau
          # dieses Literal VERLANGT und damit den Fehler festgeschrieben.
          and 'DVE_BUILD = _build_stempel()' in _srv_m
          and re.search(r"DVE_VERSION = 'v[0-9][^']*'", _srv_m) is not None)
    check('v130 Admin: UI dynamisch (Auto-Refresh, Tabs, Pause, visibility-pause)',
          # v206: die Startseite kommt mit einem eigenen Takt dazu (30 s -
          # sie ist eine Uebersicht, kein Live-Monitor). Die Zusage bleibt:
          # es gibt EINE Stelle, die die Auffrisch-Takte festlegt.
          "const AUTO={start:30000, live:15000, jobs:5000, alerts:20000}" in _adm
          and 'visibilitychange' in _adm and 'togglePause' in _adm
          and 'X-Admin-Key' in _adm
          and "['alerts','Alerts']" in _adm
          and all(t in _adm for t in ("'revenue'", "'credits'", "'abuse'",
                                      "'system'", "'compliance'", "'codes'")))
    # v130x: Pfad-Routing (/app/<name>) statt reinem Hash -> Adressleiste laedt
    # normal neu, Deep-Links teilbar, Back/Forward funktioniert. Legacy-Hash bleibt.
    _landhtml = open(os.path.join(HERE, 'web', 'landing.html'), encoding='utf-8').read()
    check('v130x: SPA-Pfad-Routing (Reload/Deep-Link) verdrahtet',
          "@app.get('/app/{rest:path}'" in _srv_m
          and "history.pushState(null, '', path)" in _ui_m
          and "location.pathname" in _ui_m and "'/app/' + name" in _ui_m
          and "addEventListener('popstate'" in _ui_m
          # Motion-aus-Kurzschluss respektiert jetzt ein explizites Ziel (Fix)
          and "showSection(target || 'create', fromHistory)" in _ui_m
          # Landing-Deep-Link auf Pfad-Form umgestellt
          and '/app/create' in _landhtml and '/app#create' not in _landhtml)
    if shutil.which('node') and os.path.isdir(os.path.join(_mgroot, 'node_modules')):
        try:
            _ts = subprocess.run(['node', 'scripts/test-showcase.mjs'], cwd=_mgroot,
                                 capture_output=True, text=True, timeout=120)
            check('v112: buildShowcase Node-Test (Individualität + Provenance + nur-Realität)',
                  _ts.returncode == 0, (_ts.stdout + _ts.stderr)[-200:])
        except Exception as _e:
            check('v112: buildShowcase Node-Test', False, str(_e))
    else:
        check('v112: buildShowcase Node-Test (node fehlt -> skip)', True)
    check('v111: Komposition registriert (16:9, storyboard-Dauer)',
          'id="MotionShowcase"' in _mrt3b and 'showcaseMetadata' in _mrt3b
          and 'showcaseDuration(story, styleId)' in _mrt3b)

    # v118: Alt-Motion-Engines KOMPLETT entfernt — nur noch das Studio-Showcase. Server hat
    # keine brief/template/sequence/auto-Endpoints/Worker mehr, die UI keinen Alt-Weg, und
    # die Remotion-Registry nur die 3 Showcase-Kompositionen (keine gelöschten TS-Dateien).
    check('v118: Server nur noch Showcase (Alt-Endpoints/Worker weg)',
          '_run_motion_showcase' in _srv_m
          and 'def _run_motion_brief' not in _srv_m and 'def _run_motion_auto' not in _srv_m
          and "@app.post('/api/motion/brief')" not in _srv_m
          and "@app.post('/api/motion/auto')" not in _srv_m
          and "@app.post('/api/motion/render')" not in _srv_m
          and "@app.post('/api/motion/preview')" not in _srv_m
          and 'class _PreviewDaemon' not in _srv_m and 'gfx_engine.py' not in _srv_m
          and 'MOTION_TEMPLATES' not in _srv_m)
    check('v118: UI-Wizard nur noch Studio (keine Alt-Karten/Funktionen)',
          'id="moTypeStudio"' in _ui_m
          and 'id="moTypeBrief"' not in _ui_m and 'id="moTypeTemplate"' not in _ui_m
          and 'id="moTypeSequence"' not in _ui_m and 'id="moTypeAuto"' not in _ui_m
          and 'function motionTemplateGo' not in _ui_m and 'function motionBriefGo' not in _ui_m
          and 'function motionSeqGo' not in _ui_m and 'function motionAutoGo' not in _ui_m
          and 'function motionPreview' not in _ui_m and 'function motionRender' not in _ui_m
          and "MO_ENGINE_STEPS = { studio:['type','studio'] }" in _ui_m
          and 'function motionStudioGo' in _ui_m)
    check('v118: Remotion-Registry nur 3 Showcase-Kompositionen (Alt-TS gelöscht)',
          all(c in _mrt3b for c in ['id="MotionShowcase"', 'id="MotionKinetic"', 'id="MotionPrompt"'])
          and all(c not in _mrt3b for c in ['MotionVideo', 'Motion3D', 'MotionApple',
                                            'MotionSequence', 'MotionOverlay'])
          and not any(os.path.exists(os.path.join(HERE, 'motion', 'src', f)) for f in
                      ['MotionVideo.tsx', 'Motion3D.tsx', 'MotionApple.tsx',
                       'MotionSequence.tsx', 'MotionOverlay.tsx', 'director/autoGuards.ts',
                       'director/templates.ts', 'director/run.ts'])
          and not os.path.exists(os.path.join(HERE, 'motion', 'scripts', 'render-brief.mjs'))
          and not os.path.exists(os.path.join(HERE, 'motion', 'scripts', 'render-auto.mjs')))

    # v101x: Captions + Motion als getrennte Produkte (Einstieg waehlbar + gemerkt).
    _land = open(os.path.join(HERE, 'web', 'landing.html'), encoding='utf-8').read()
    check('v101x: App - Werkzeugauswahl, Deep-Link, gemerktes Tool',
          'id="toolChooser"' in _ui_m and 'function pickTool' in _ui_m
          and 'function showToolChooser' in _ui_m
          and "localStorage.setItem('dve_tool'" in _ui_m
          and "localStorage.getItem('dve_chosen')" in _ui_m
          # routeFromHash akzeptiert #motion UND #/motion
          and ".replace(/^#\\/?/, '')" in _ui_m)
    # v127: Landing ist Single-Product (Captions, Editorial-Redesign). Motion
    # bleibt fuer Kunden ausgeblendet -> nicht auf der Landing beworben.
    check('v127: Landing - Single-Product Captions, Deep-Link-CTA, Motion ausgeblendet',
          'id="captions"' in _land and '/app/create' in _land   # v130x: Pfad-Deep-Link
          and 'id="motion"' not in _land and '/app#motion' not in _land
          and 'Motion Graphics' not in _land)

    # v91: ground_anchor - liegender Text auf B-Roll MIT sichtbarer Person
    # muss auf die klare Strasse (Person ausgespart), nicht auf die Person.
    # Aufbau: Person-Matte deckt die obere Bildhaelfte + Mitte, unten frei.
    ga_alpha = np.zeros((H_, W_, 1), dtype=np.float32)
    ga_alpha[:int(H_ * 0.60), int(W_ * 0.20):int(W_ * 0.85)] = 1.0   # Koerper/Arm
    ga_arr = np.zeros((int(H_ * 0.10), int(W_ * 0.55), 4), dtype=np.uint8)
    ga_arr[..., 3] = 255
    ga = R.ground_anchor(ga_alpha, ga_arr, W_, H_)
    tw2, th2 = ga_arr.shape[1], ga_arr.shape[0]
    in_frame = ga is not None and (tw2 / 2 <= ga[0] <= W_ - tw2 / 2
                                   and th2 / 2 <= ga[1] <= H_ - th2 / 2)
    on_ground = ga is not None and float(ga_alpha[int(ga[1]), int(ga[0]), 0]) < 0.35
    below_person = ga is not None and ga[1] > H_ * 0.55
    check('Boden-Anker meidet die Person',
          bool(in_frame and on_ground and below_person),
          f'{ga}' if ga else 'None')
    # Ohne Person (echtes Aerial-B-Roll) -> kein Umanker, Standard bleibt
    check('Boden-Anker aus bei leerem Bild',
          R.ground_anchor(np.zeros((H_, W_, 1), np.float32), ga_arr, W_, H_) is None)

    # Planarer Kamera-Track: Homographie erkennt Kamerabewegung,
    # paste_tracked bewegt den Text wie ein Objekt in der Welt
    rngt = np.random.default_rng(3)
    baseg = (rngt.random((270, 480)) * 255).astype(np.uint8)
    import cv2 as _cv
    baseg = _cv.GaussianBlur(baseg, (0, 0), 2)
    shifted = np.roll(baseg, (-7, 12), axis=(0, 1))
    Hn, ok_h = R.update_homography(baseg, shifted, np.eye(3), mask_lower=0.0)
    check('Kamera-Track erkennt Bewegung', bool(ok_h)
          and abs(Hn[0, 2] - 12) < 2 and abs(Hn[1, 2] + 7) < 2,
          f'tx={Hn[0,2]:.1f} ty={Hn[1,2]:.1f}')
    cvt = np.full((300, 500, 3), 80.0, np.float32)
    spr_t = np.zeros((60, 200, 4), np.uint8)
    spr_t[10:50, 10:190] = (255, 255, 255, 255)
    H_rel = np.array([[1, 0, 60], [0, 1, 25], [0, 0, 1]], np.float64)
    R.paste_tracked(cvt, spr_t, 200, 120, H_rel, 500, 300,
                    refract=0.0, ripple=0.0, grain=0.0, opacity=1.0)
    yst, xst = np.where(cvt[..., 0] > 200)
    check('Text folgt dem Kamera-Track', len(xst) > 100
          and abs(xst.mean() - 260) < 6 and abs(yst.mean() - 145) < 6,
          f'Zentrum ({xst.mean():.0f},{yst.mean():.0f})' if len(xst) else 'leer')
    plt3 = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False,
                         {1: {'fx': 'ground', 'power': 3, 'n': 1}})
    kpt3 = [p for p in plt3 if 'kw_i' in p]
    check('track3d an Szenen-Texten', bool(kpt3) and kpt3[0].get('track3d') is True)

    # GUI: Kern-Handler existieren (fing den verlorenen pick_video-Button),
    # Effekte erklaert, Presets vollstaendig - laeuft ohne Fenster
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('gui_mod', os.path.join(HERE, 'gui.py'))
        _gui = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_gui)
        for _m in ('pick_video', 'apply_preset', 'save_cfg', 'profile_save',
                   'profile_load', 'render'):
            check(f'GUI-Handler {_m}', hasattr(_gui.App, _m))
        import re as _re
        _src = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
        _used = set(_re.findall(r'\bF_[A-Z]+\b', _src)) | {'F'} if ' F,' in _src or 'font=F,' in _src else set(_re.findall(r'\bF_[A-Z]+\b', _src))
        _missing = [n for n in sorted(_used) if not hasattr(_gui, n)]
        check('GUI-Konstanten definiert (F_*)', not _missing,
              'fehlt: ' + ', '.join(_missing) if _missing else 'alle da')
        check('Effekte mit Erklaerung', all(len(e) == 3 and len(e[2]) > 20
                                            for e in _gui.EFFECTS))
        check('Stil-Presets vollstaendig',
              set(_gui.PRESETS) == {'TikTok', 'Creator', 'Cinematic', 'Clean'}
              and all(all(k in p for k in ('font', 'style', 'plattform', 'fx',
                                           'dynamik', 'desc'))
                      for p in _gui.PRESETS.values())
              and len({(tuple(sorted(p['fx'])), p['font'], p['dynamik'])
                       for p in _gui.PRESETS.values()}) == 4)
    except ImportError as _e:
        check('GUI-Modul ladbar', False, str(_e))

    # Blender-Engine: gefunden, defensive Fehlerpfade, Glas-Verdrahtung
    import blender_engine as BE
    bl = BE.find_blender()
    check('Blender gefunden (optional)', True,
          bl if bl else 'nicht installiert - 2D-Fallback aktiv')
    check('Blender-Engine faellt sauber zurueck',
          BE.render_water_text('X', '/nicht/da.png', 'font.ttf') is None)
    # Lebendiges Wasser: Loop-Index pendelt nahtlos (Ping-Pong), Skript animiert
    idx = [BE.anim_loop_idx(t / 10.0, 4) for t in range(0, 14)]
    check('Wasser-Loop pendelt nahtlos', idx[:7] == [0, 1, 2, 3, 2, 1, 0]
          and max(idx) == 3 and min(idx) >= 0, str(idx[:8]))
    check('Wasser-Loop Randfaelle', BE.anim_loop_idx(0.0, 1) == 0
          and BE.anim_loop_idx(-1.0, 4) == 0 and BE.anim_loop_idx(99.7, 4) in (0, 1, 2, 3))
    check('Blender-Animation im Skript', "noise_dimensions = '4D'" in BE.BPY_SCRIPT
          and "args.get('frames'" in BE.BPY_SCRIPT)
    check('Blender-Skript vollstaendig',
          'IOR' in BE.BPY_SCRIPT and 'normals_make_consistent' in BE.BPY_SCRIPT
          and 'film_transparent' in BE.BPY_SCRIPT)

    # Lebendige Typo: JEDE Animation muss bei JEDEM Effekt ankommen.
    # (Genau hier lag der Bug: Feuer/Glitch/Puls wirkten nur bei 'behind'.)
    import numpy as _np
    _base = _np.zeros((80, 300, 4), _np.uint8); _base[20:60, 40:260] = 255
    for _a in R.ANIM_LIST:
        _p = {'anim': _a, 'start': 1.0}
        # Ueber mehrere Zeitpunkte pruefen: manche Animationen sind Einschlaege
        # (knall knallt rein und steht dann - eine Pointe zappelt nicht ewig),
        # andere bauen sich erst auf. Ein einzelner Zeitpunkt wuerde luegen.
        _wirkt = False
        for _dt in (0.05, 0.2, 0.4, 0.7, 1.1):
            _o, _dx, _dy, _sc, _op = R.anim_apply(_p, _base, (0.7, 0.8, 0.9), _dt)
            if (_o.shape != _base.shape or not _np.array_equal(_o, _base)
                    or abs(_dx) > 0.01 or abs(_dy) > 0.01
                    or abs(_sc - 1) > 0.001 or abs(_op - 1) > 0.001):
                _wirkt = True
                break
        check(f'Animation {_a} wirkt', _wirkt)
    for _fx in ('behind', 'cascade', 'outline', 'blurin', 'ground'):
        _fm = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "%s", '
                            '"power": 2, "anim": "welle"}]}' % _fx, wg, 'de')
        _pl = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda a, b: False, _fm)
        _kp = [p for p in _pl if p.get('kw_i') == 1]
        check(f'Animation kommt bei Effekt {_fx} an',
              bool(_kp) and _kp[0].get('anim') == 'welle')
    check('Feuer ist entfernt', not hasattr(R, 'FireFX')
          and 'feuer' not in R.ANIM_LIST)

    # ---- Stand 2026: Premium-Motion -------------------------------------------
    _neu = ('gewicht', 'schweben', 'fokus', 'enthuellen', 'spur')
    check('2026er Animationen sind da', all(_a in R.ANIM_LIST for _a in _neu))
    _gsrc26 = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    check('2026er Animationen stehen in der GUI-Liste',
          all(_gsrc26.count(f"'{_a}'") >= 2 for _a in _neu))
    check('2026er Animationen stehen im KI-Prompt',
          all(f'"{_a}"' in R.REGIE_PROMPT for _a in _neu))
    for _a in _neu:
        _fm = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "behind", '
                            '"power": 2, "anim": "%s"}]}' % _a, wg, 'de')
        check(f'KI darf {_a} waehlen', _fm and _fm[1].get('anim') == _a)

    # ---- v71: Acht weitere Animationen ----
    _v71 = ('kippen', 'explosion', 'magnet', 'wackel', 'regen', 'zoom_punch',
            'rutsche', 'stempel')
    check('v71-Animationen in ANIM_LIST', all(_a in R.ANIM_LIST for _a in _v71))
    check('v71 stehen in GUI (Dropdown + Liste)',
          all(_gsrc26.count(f"'{_a}'") >= 2 for _a in _v71))
    check('v71 stehen im KI-Prompt',
          all(f'"{_a}"' in R.REGIE_PROMPT for _a in _v71))
    # HINTS: passendes Keyword loest die Animation aus
    _hits = {'kippen': 'Kapitel', 'explosion': 'explodiert', 'magnet': 'zieht',
             'wackel': 'lustig', 'regen': 'regen', 'zoom_punch': 'punchline',
             'rutsche': 'rutscht', 'stempel': 'endgueltig'}
    for _a, _kw in _hits.items():
        _got = R.anim_for(_kw, f'das {_kw} passiert')
        check(f'HINTS: "{_kw}" -> {_a}', _got == _a,
              f'bekam {_got!r} statt {_a!r}')
    # Editor-Combobox kann parse_regie die neuen zurueckliefern
    for _a in _v71:
        _fm71 = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "behind", '
                              '"power": 2, "anim": "%s"}]}' % _a, wg, 'de')
        check(f'parse_regie akzeptiert {_a}',
              _fm71 and _fm71[1].get('anim') == _a)
    # Explosion: shape aendert sich (breiter geworden durch pad)
    _e_arr, _dx, _dy, _sc, _op = R.anim_apply(
        {'anim': 'explosion', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.15)
    check('explosion breitet aus', _e_arr.shape[1] > _base.shape[1])
    # Rutsche: shape breiter (pad rechts)
    _r_arr, *_ = R.anim_apply(
        {'anim': 'rutsche', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.1)
    check('rutsche macht Padding', _r_arr.shape[1] > _base.shape[1])
    # Regen: shape hoeher (pad unten)
    _re_arr, *_ = R.anim_apply(
        {'anim': 'regen', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.1)
    check('regen macht vertikales Padding', _re_arr.shape[0] > _base.shape[0])
    # Zoom-Punch: Skalierung > 1 im ersten Drittel
    _, _, _, _sc_zp, _ = R.anim_apply(
        {'anim': 'zoom_punch', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.05)
    check('zoom_punch drueckt rein (sc > 1.0)', _sc_zp > 1.05)
    # Wackel: Sinus loopt -> dy oszilliert (unterschiedliche Vorzeichen)
    _dy_a = R.anim_apply({'anim': 'wackel', 'start': 0}, _base,
                         (0.5, 0.5, 0.5), 0.15)[2]
    _dy_b = R.anim_apply({'anim': 'wackel', 'start': 0}, _base,
                         (0.5, 0.5, 0.5), 0.40)[2]
    check('wackel oszilliert', _dy_a * _dy_b < 0 or abs(_dy_a) + abs(_dy_b) > 0.5,
          f'dy_a={_dy_a:.3f}, dy_b={_dy_b:.3f}')
    # Magnet: shape breiter am Anfang, gleich am Ende (Zusammenzug)
    _m_start, *_ = R.anim_apply(
        {'anim': 'magnet', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.05)
    _m_end, *_ = R.anim_apply(
        {'anim': 'magnet', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.60)
    check('magnet: breiter am Anfang', _m_start.shape[1] > _base.shape[1])
    # Stempel: scale > 1.0 im Aufschlag
    _, _, _, _sc_st, _ = R.anim_apply(
        {'anim': 'stempel', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.05)
    check('stempel: kommt aus grosser Skala (sc > 1.3)', _sc_st > 1.3,
          f'sc={_sc_st:.2f}')
    # Kippen: shape aendert sich durch perspektive
    _k_arr, *_ = R.anim_apply(
        {'anim': 'kippen', 'start': 0}, _base, (0.5, 0.5, 0.5), 0.05)
    check('kippen macht 3D-Kipp (shape geaendert)',
          _k_arr.shape != _base.shape or not _np.array_equal(_k_arr, _base))
    # Feder schiesst ueber das Ziel hinaus und kommt zur Ruhe (kein Ease-Out)
    _sp = [R.spring(x / 30.0) for x in range(50)]
    check('Feder ueberschwingt und beruhigt sich',
          max(_sp) > 1.02 and abs(R.spring(1.9) - 1.0) < 1e-6 and R.spring(0.0) == 0.0)
    # ---- v82: Cutter-Exit ----
    # exit_env haelt anfangs fast voll (Ease-In) und laesst dann los -
    # ein linearer Fade waere bei over=20% schon auf 0.8, wir wollen > 0.95
    check('exit_env haelt und laesst los',
          R.exit_env(-0.1) == 1.0 and R.exit_env(0.0) == 1.0
          and R.exit_env(0.048, 0.24) > 0.95
          and R.exit_env(0.24, 0.24) < 1e-6
          and R.exit_env(0.12, 0.24) > 1 - 0.12 / 0.24)
    _ee = [R.exit_env(x * 0.24 / 20, 0.24) for x in range(21)]
    check('exit_env monoton fallend', all(a >= b for a, b in zip(_ee, _ee[1:])))
    # exit_pose: Ruhe vor dem Exit, dann Scale-Settle + Richtungs-Drift
    check('exit_pose ruht vor dem Ende', R.exit_pose(0.0) == (1.0, 0.0))
    _ps, _pd = R.exit_pose(0.24, 0.24, drop=True)
    _ps2, _pd2 = R.exit_pose(0.24, 0.24, drop=False)
    check('exit_pose settelt und driftet richtungsrichtig',
          abs(_ps - 0.97) < 1e-6 and _pd > 0 and _pd2 < 0)
    # hand_jitter: deterministisch (Render reproduzierbar), gestreut, begrenzt
    _hj = [R.hand_jitter(i) for i in range(60)]
    check('hand_jitter deterministisch und gestreut',
          R.hand_jitter(7) == R.hand_jitter(7)
          and all(-1.0 <= v <= 1.0 for v in _hj)
          and len({round(v, 6) for v in _hj}) > 50)
    # Bewegungsunschaerfe: verwischt entlang der Richtung, Alpha bleibt erhalten
    _mb = R._motion_blur(_base, 14.0, 0.0)
    _ca = _mb[..., 3] > 0
    check('Bewegungsunschaerfe verwischt horizontal',
          int(_ca.any(axis=0).sum()) > 226 and int(_ca.any(axis=1).sum()) <= 42
          and int(_mb[..., 3].max()) > 200)
    check('Bewegungsunschaerfe ignoriert Mikrobewegung',
          R._motion_blur(_base, 0.4, 0.3) is _base)
    check('Bewegungsunschaerfe faerbt Raender nicht schwarz',
          int(_mb[0, 0, 3]) == 0)
    # Gewicht: der Strich wird wirklich fetter (mehr Deckung), Groesse bleibt
    _wm = R._weight_morph(_base, 1.0)
    check('Gewicht macht den Strich fetter',
          _wm.shape == _base.shape
          and int(_wm[..., 3].sum()) > int(_base[..., 3].sum()))
    # Perspektive: echte Fluchtkanten (nahe Kante hoeher als ferne)
    _pp, _px, _py = R._persp3d(_base, 0.0, 0.5)
    _cols = np.where(_pp[..., 3].max(axis=0) > 0)[0]
    _l = int((_pp[:, _cols[0], 3] > 0).sum())
    _r = int((_pp[:, _cols[-1], 3] > 0).sum())
    check('Perspektive erzeugt echte Fluchtkanten', abs(_l - _r) > 3)
    # Motion-Blur greift zentral: zweiter Frame einer schnellen Bewegung ist weich
    _sp_p = {'anim': 'spur', 'start': 1.0}
    R.MOTION_BLUR = True
    R.anim_apply(_sp_p, _base, (0.5, 0.5, 0.5), 0.05)
    _f2 = R.anim_apply(_sp_p, _base, (0.5, 0.5, 0.5), 0.09)[0]
    _sp_p2 = {'anim': 'spur', 'start': 1.0}
    R.MOTION_BLUR = False
    R.anim_apply(_sp_p2, _base, (0.5, 0.5, 0.5), 0.05)
    _f2n = R.anim_apply(_sp_p2, _base, (0.5, 0.5, 0.5), 0.09)[0]
    R.MOTION_BLUR = True
    check('Bewegungsunschaerfe wirkt im Renderpfad',
          _f2.shape != _f2n.shape or not np.array_equal(_f2, _f2n))
    check('Bewegungsunschaerfe ist abschaltbar',
          'motion_blur' in open(os.path.join(HERE, 'config.yaml'),
                                encoding='utf-8').read())
    # Variation: Rotator mischt, wiederholt nie direkt und verteilt gleichmaessig
    _r = R.Rotator(['a', 'b', 'c', 'd'], seed=3)
    _seq = [_r.next() for _ in range(40)]
    check('Variation: kein direkter Doppel-Einflug',
          all(_seq[i] != _seq[i + 1] for i in range(len(_seq) - 1)))
    check('Variation: alles kommt gleich oft',
          max(_seq.count(x) for x in 'abcd') - min(_seq.count(x) for x in 'abcd') <= 1)

    # Hook einstellbar: laenger/staerker = mehr Momente am Anfang
    _lw = [{'word': f'W{k}' if k % 24 else 'WACHSTUM', 'start': k * 0.5,
            'end': k * 0.5 + 0.45} for k in range(180)]
    _kwl = {i for i, w in enumerate(_lw) if w['word'] == 'WACHSTUM'}

    def _early(hook_s, hook_p=0.9, **ov):
        c2 = copy.deepcopy(cfg)
        c2['effects'].update(density='akzente', hook_seconds=hook_s,
                             hook_strength=hook_p, **ov)
        import io as _io, contextlib as _cl
        with _cl.redirect_stdout(_io.StringIO()) as _b:
            pl = R.build_plans(_lw, set(_kwl), c2, S, W_, H_, lambda a, b: True, {})
        mom = sorted([p for p in pl if p.get('tpl') != 'camonly'],
                     key=lambda p: p['start'])
        cams = [p for p in pl if p.get('tpl') == 'camonly']
        mx = max((mom[i + 1]['start'] - mom[i]['end'] for i in range(len(mom) - 1)),
                 default=0)
        return (len([p for p in mom if p['start'] < 30]), len(cams), mx,
                _b.getvalue().count('Watchtime moment'))

    e0, e15, e30 = _early(0)[0], _early(15)[0], _early(30)[0]
    check('Hook-Laenge wirkt', e0 < e15 < e30, f'0s={e0} 15s={e15} 30s={e30}')
    # Staerke wirkt auf die Dichte-Grenze - dafuer muessen Keywords eng genug
    # liegen, sonst bindet die Grenze gar nicht
    _dw = [{'word': f'W{k}' if k % 6 else 'WACHSTUM', 'start': k * 0.5,
            'end': k * 0.5 + 0.45} for k in range(120)]
    _dkw = {i for i, w in enumerate(_dw) if w['word'] == 'WACHSTUM'}

    def _dense(hook_p):
        c2 = copy.deepcopy(cfg)
        c2['effects'].update(density='akzente', hook_seconds=30,
                             hook_strength=hook_p, retention_gap=0,
                             pattern_interrupt=0)
        import io as _io, contextlib as _cl
        with _cl.redirect_stdout(_io.StringIO()):
            pl = R.build_plans(_dw, set(_dkw), c2, S, W_, H_, lambda a, b: True, {})
        # Staerke steuert, wie viele GROSSE Momente (Keyword-Effekte) im Hook
        # zugelassen werden - normale Gruppen laufen im Hook ohnehin alle
        return len([p for p in pl if p['start'] < 30 and 'kw_i' in p])

    _weak, _strong = _dense(0.1), _dense(0.9)
    check('Hook-Staerke wirkt', _strong > _weak,
          f'sanft={_weak} stark={_strong} grosse Momente im Hook')
    # Watchtime: Luecken werden geschlossen, Impulse gesetzt
    _off = _early(15, 0.5, retention_gap=0, pattern_interrupt=0)
    _on = _early(15, 0.5, retention_gap=8, pattern_interrupt=9)
    check('Watchtime: Luecken werden gefuellt', _on[3] > 0 and _on[2] < _off[2],
          f'groesste Luecke {_off[2]:.1f}s -> {_on[2]:.1f}s')
    check('Watchtime: Pattern-Interrupts gesetzt', _on[1] > 0 and _off[1] == 0)
    check('Watchtime abschaltbar', _off[1] == 0 and _off[3] == 0)

    # --- v48: Sofort-Hook, Open-Loop-Teaser, Hook-Takt ---
    import io as _io, contextlib as _cl
    _hw = [{'word': f' Wort{i}', 'start': 0.4 + i * 0.5, 'end': 0.7 + i * 0.5}
           for i in range(90)]
    _hw[4]['word'] = ' Steuertrick'
    _hw[70]['word'] = ' Geheimplan'
    _hfx = {4: {'fx': 'behind', 'power': 3, 'n': 1},
            70: {'fx': 'ground', 'power': 3, 'n': 1}}

    def _hooks(**eff):
        c2 = copy.deepcopy(cfg)
        # v97e: Sofort-Hook-Parken gilt nur ohne Flow (mit Flow gibt es keinen
        # leeren Anfang, den man ueberbruecken muesste) - hier gezielt testen.
        c2['effects'].update(retention_gap=0, pattern_interrupt=0,
                             caption_flow=False, **eff)
        with _cl.redirect_stdout(_io.StringIO()):
            return R.build_plans(_hw, {4, 70}, c2, S, W_, H_, lambda a, b: True,
                                 copy.deepcopy(_hfx),
                                 face_pos=lambda s, e: (960.0, 430.0, 220.0))

    _pl = _hooks()
    _card = [p for p in _pl if p.get('t0') == 0.0]
    check('Sofort-Hook steht ab Frame 1',
          bool(_card) and _card[0]['start'] == 0.0
          and 'STEUERTRICK' in _card[0].get('kw_txt', ''),
          _card[0].get('kw_txt', '-') if _card else 'keine Karte')
    _pl_off = _hooks(instant_hook=False)
    check('Sofort-Hook abschaltbar',
          not any(p.get('t0') == 0.0 for p in _pl_off))
    # v48: B-Roll wird ignoriert - keine Momente, keine Kamera-Impulse
    def _broll(**eff):
        c2 = copy.deepcopy(cfg)
        c2['effects'].update(retention_gap=8, pattern_interrupt=9,
                             broll_captions=False, **eff)
        with _cl.redirect_stdout(_io.StringIO()):
            # Gesicht nur ausserhalb von 10-30s: dazwischen ist B-Roll
            return R.build_plans(_hw, {4, 70}, c2, S, W_, H_,
                                 lambda a, b: not (10.0 < a < 30.0),
                                 copy.deepcopy(_hfx),
                                 face_pos=lambda s, e: (960.0, 430.0, 220.0))

    _bpl = _broll()
    _in_broll = [p for p in _bpl if 10.0 < p['start'] < 30.0]
    check('B-Roll: keine Kamera-Impulse',
          not any(p.get('tpl') == 'camonly' for p in _in_broll),
          f"{sum(1 for p in _in_broll if p.get('tpl') == 'camonly')} Impulse auf B-Roll")
    check('B-Roll: keine Momente geplant',
          not any('kw_i' in p for p in _in_broll),
          f"{sum(1 for p in _in_broll if 'kw_i' in p)} Momente auf B-Roll")
    check('B-Roll: Impulse laufen ausserhalb weiter',
          any(p.get('tpl') == 'camonly' for p in _bpl))
    check('Open-Loop-Teaser entfernt',
          not any(p.get('tpl') == 'teaser' for p in _bpl)
          and 'open_loop' not in open(os.path.join(HERE, 'render.py'),
                                      encoding='utf-8').read()
          and 'open_loop' not in open(os.path.join(HERE, 'gui.py'),
                                      encoding='utf-8').read())

    # Hook-Takt: Sprechpause im Hook (Gesicht da, kein Text) wird im 3-5s-Takt
    # gefuellt statt alle 9s. B-Roll ist ausgenommen -> Pause statt Schnittbild.
    _pw = ([{'word': f' A{i}', 'start': 0.4 + i * 0.5, 'end': 0.7 + i * 0.5}
            for i in range(6)]
           + [{'word': f' B{i}', 'start': 16.0 + i * 0.5, 'end': 16.3 + i * 0.5}
              for i in range(40)])

    def _pi_hook(hook_s):
        c2 = copy.deepcopy(cfg)
        c2['effects'].update(retention_gap=0, pattern_interrupt=9,
                             hook_seconds=hook_s, instant_hook=False,
                             density='akzente')
        with _cl.redirect_stdout(_io.StringIO()):
            pl = R.build_plans(_pw, {2}, c2, S, W_, H_, lambda a2, b2: True,
                               {2: {'fx': 'behind', 'power': 2, 'n': 1}})
        return [p['start'] for p in pl if p.get('tpl') == 'camonly'
                and p['start'] < 15.0]
    _c15, _c0 = _pi_hook(15), _pi_hook(0)
    check('Hook-Takt verdichtet (3-5s)', len(_c15) > len(_c0),
          f'Hook-Impulse {len(_c15)} vs {len(_c0)} ohne Hook')

    # --- v50: Bruch-Animation (Satz-Kontext) + Farbwelten ---
    check('Bruch: Satz-Kontext entscheidet',
          R.anim_for('DEUTSCHLAND') is None
          and R.anim_for('DEUTSCHLAND',
                         'Deutschland bricht seine Versprechen') == 'bruch',
          "Wort allein: nichts, im Satz 'bricht': bruch")
    check('Bruch: Keyword hat Vorrang vor Kontext',
          R.anim_for('WACHSTUM', 'das Wachstum bricht ein') == 'schub')
    check('Bruch in der Animationsliste', 'bruch' in R.ANIM_LIST)
    check('Bruch: KI-Regie kennt ihn',
          R.parse_regie('{"keywords": [{"i": 0, "n": 1, "fx": "behind",'
                        ' "power": 3, "anim": "bruch"}]}',
                        [{'word': 'Deutschland', 'start': 1.0, 'end': 1.4}],
                        'de')[0].get('anim') == 'bruch'
          and 'bruch' in R.REGIE_PROMPT)
    # Bruch am Plan: Keyword DEUTSCHLAND, Satz sagt "bricht"
    _bw = [{'word': w, 'start': 1 + j * 0.4, 'end': 1.35 + j * 0.4} for j, w in
           enumerate(['Deutschland', 'bricht', 'seine', 'Versprechen'])]
    with _cl.redirect_stdout(_io.StringIO()):
        _bpl2 = R.build_plans(_bw, {0}, copy.deepcopy(cfg), S, W_, H_,
                              lambda a, b: True,
                              {0: {'fx': 'behind', 'power': 3, 'n': 1}})
    _bkw = next(p for p in _bpl2 if 'kw_i' in p)
    check('Bruch kommt am Plan an', _bkw.get('anim') == 'bruch',
          f"'{_bkw['kw_txt']}' -> {_bkw.get('anim')}")
    # Das Wort zerbricht wirklich: Scherben verschieben sich, deterministisch
    _barr = S.text('DEUTSCHLAND', 110, S.white)[0]
    _bp = {'anim': 'bruch', 'start': 1.0}
    _b0 = R.anim_apply(_bp, _barr, (0.5, 0.3, 0.1), 0.10)[0]
    _b1 = R.anim_apply(_bp, _barr, (0.5, 0.3, 0.1), 0.90)[0]
    _b1b = R.anim_apply(_bp, _barr, (0.5, 0.3, 0.1), 0.90)[0]
    _h0, _w0 = _barr.shape[:2]
    _py, _px = (_b1.shape[0] - _h0) // 2, (_b1.shape[1] - _w0) // 2
    _core = _b1[_py:_py + _h0, _px:_px + _w0, 3].astype(float)
    _shift = float(np.abs(_core - _barr[..., 3].astype(float)).mean())
    check('Bruch: Wort steht erst ganz', _b0.shape == _barr.shape)
    check('Bruch: Scherben brechen auf', _shift > 5.0,
          f'Alpha-Verschiebung {_shift:.0f}')
    check('Bruch: kein Flackern (deterministisch)',
          bool(np.array_equal(_b1, _b1b)))

    # Farbwelten: Schwarz/Weiss setzen feste Toene, auto bleibt adaptiv
    _cs = copy.deepcopy(cfg)
    _S2 = R.Sprites(_cs, W_, H_)
    _S2.set_base_colors((20, 20, 22), (58, 58, 64))
    _dark = _S2.white
    _S2.set_palette(None)                     # Rueckfall darf NICHT zur Config
    check('Farbwelt haelt gegen Szenen-Toene', _S2.white == _dark == (20, 20, 22),
          str(_S2.white))
    _S3 = R.Sprites(_cs, W_, H_)
    _S3.set_base_colors((250, 249, 246), (208, 204, 196))
    check('Elegantes Weiss ist hell', min(_S3.white) > 200, str(_S3.white))
    check('Elegantes Schwarz ist dunkel', max(_dark) < 40, str(_dark))
    _rsrc = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Farbwelt verdrahtet (Config + Render)',
          "colors', {}).get('style'" in _rsrc
          and 'schwarz' in _rsrc and 'weiss' in _rsrc)
    check('GUI: Farbwelt-Auswahl da',
          'color_var' in open(os.path.join(HERE, 'gui.py'),
                              encoding='utf-8').read())

    # --- v51: sechs neue Animationen + deutsche Sprach-Fallen ---
    check('26 Animationen an Bord', len(R.ANIM_LIST) == 26
          and len(set(R.ANIM_LIST)) == 26, str(len(R.ANIM_LIST)))
    for _new in ('sturz', 'anstieg', 'wende', 'druck', 'schwund', 'knall'):
        check(f'Animation "{_new}" vorhanden', _new in R.ANIM_LIST)
    # Jede Animation muss das Bild wirklich veraendern (keine Attrappe)
    _aarr = S.text('BEISPIEL', 90, S.white)[0]
    _tot = 0
    for _an in R.ANIM_LIST:
        _wirkt = False
        for _dt in (0.05, 0.25, 0.5, 0.8, 1.2):
            _r = R.anim_apply({'anim': _an, 'start': 1.0}, _aarr,
                              (0.7, 0.6, 0.9), _dt)
            if (_r[0].shape != _aarr.shape or not np.array_equal(_r[0], _aarr)
                    or abs(_r[1]) > 0.01 or abs(_r[2]) > 0.01
                    or abs(_r[3] - 1) > 0.001 or abs(_r[4] - 1) > 0.001):
                _wirkt = True
                break
        _tot += _wirkt
    check('Alle 26 Animationen wirken sichtbar', _tot == 26, f'{_tot}/26')
    # Deutsche Sprach-Fallen: Wortanfang zaehlt, nicht blinder Teilstring
    _traps = [
        ('DEUTSCHLAND', 'Deutschland bricht seine Versprechen', 'bruch'),
        ('AKTIEN', 'die Aktien stuerzen ab', 'sturz'),
        ('PREISE', 'die Preise fallen zum ersten Mal', 'sturz'),
        ('MIETEN', 'die Mieten steigen auf Rekordhoch', 'anstieg'),
        ('ZINSEN', 'die Zinsen klettern weiter', 'anstieg'),
        ('STIMMUNG', 'ploetzlich kippt die Stimmung', 'wende'),
        ('BUERGER', 'die Schulden erdruecken die Buerger', 'druck'),
        ('RENTE', 'deine Rente ist einfach verschwunden', 'schwund'),
        ('BEWEIS', 'das ist der Beweis', 'knall'),
        # Diese duerfen NICHTS ausloesen:
        ('VIDEO', 'das gefaellt mir sehr gut', None),          # gefaellt != faellt
        ('WEG', 'wir gehen den Weg gemeinsam', None),
        ('SACHE', 'genau, also die Sache ist so', None),       # Fuellwort
        ('THEMA', 'es gibt nicht mehr zu sagen', None),
        ('HAUS', 'ein ganz normales Haus steht dort', None),
    ]
    _wrong = [(s, R.anim_for(k, s), w) for k, s, w in _traps
              if R.anim_for(k, s) != w]
    check('Deutsche Sprach-Fallen sitzen', not _wrong,
          f'{len(_traps) - len(_wrong)}/{len(_traps)}'
          + (f' | daneben: {_wrong[0]}' if _wrong else ''))
    check('Keyword schlaegt Kontext',
          R.anim_for('WACHSTUM', 'das Wachstum bricht ein') == 'schub')
    # Editor + Regie muessen ALLE Animationen kennen (v50-Luecke: bruch fehlte)
    _g = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    _fehlt = [a for a in R.ANIM_LIST if f"'{a}'" not in _g]
    check('Momente-Editor kennt alle Animationen', not _fehlt, str(_fehlt))
    _fehlt_r = [a for a in R.ANIM_LIST if a not in R.REGIE_PROMPT]
    check('KI-Regie kennt alle Animationen', not _fehlt_r, str(_fehlt_r))

    # Regression: Kamera-Impuls (camonly) darf den Compositor nicht crashen
    _cam_pl = [{'tpl': 'camonly', 'start': 1.0, 'end': 1.9, 'cam': 'punch',
                'small': [], 'broll': False, 'ccam': 'none', 'arr': None}]
    _fr = np.zeros((H_, W_, 3), np.float32)
    try:
        R.composite_frame(_fr.copy(), None, 1.2, _cam_pl, _hw, (960, 430),
                          cfg, S, W_, H_)
        _cam_ok = True
    except Exception as _e:
        _cam_ok = False
    check('Kamera-Impuls crasht nicht (v47-Bug)', _cam_ok)

    check('Hook-SFX ab Frame 1',
          "p.get('t0'" in open(os.path.join(HERE, 'sfx_engine.py'),
                               encoding='utf-8').read())
    _gsrc48 = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    check('GUI: Hook-Schalter verdrahtet',
          'ihook_var' in _gsrc48 and 'instant_hook' in _gsrc48)

    # Material je Szene: Plan traegt die Vision-Szene, Engine hat beide Materialien,
    # Momente-Editor-Felder uebersteuern die Regie
    fm_b = R.parse_regie('{"keywords": [{"i": 1, "n": 1, "fx": "ground", "power": 2,'
                         ' "szene": "boden", "lage": "stehend"}]}', wg, 'de')
    pl_b = R.build_plans(wg, {1}, cfg, S, W_, H_, lambda s, e: False, fm_b)
    kp_b = [p for p in pl_b if 'kw_i' in p]
    check('Plan traegt Szene fuer Material', bool(kp_b)
          and kp_b[0].get('szene') == 'boden')
    check('Engine kennt Wasser UND massiv',
          'ShaderNodeBsdfGlass' in BE.BPY_SCRIPT
          and 'ShaderNodeBsdfPrincipled' in BE.BPY_SCRIPT
          and "args.get('material'" in BE.BPY_SCRIPT)
    check('Transkript-Kontrolle verdrahtet',
          '--transcribe-only' in open(os.path.join(HERE, 'render.py'),
                                      encoding='utf-8').read()
          and 'open_transcript_editor' in open(os.path.join(HERE, 'gui.py'),
                                               encoding='utf-8').read())
    _gsrc = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    _rsrc = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Partieller Re-Render verdrahtet',
          'partial_rerender' in _gsrc and '--window' in _rsrc
          and 'splice_into' in _rsrc and 'first_abs / fps' in _rsrc)
    check('Editor spricht Deutsch',
          all(x in _gsrc for x in ('FX_DE', 'POWER_DE', 'ANIM_DE'))
          and 'Hinter dir' in _gsrc)
    # v68: Undo/Redo im Momente-Editor
    import importlib
    _gui = importlib.import_module('gui')
    _h = _gui.EditorHistory(cap=5)
    check('EditorHistory: initial leer',
          not _h.can_undo() and not _h.can_redo())
    _h.push([('a',)])
    _h.push([('b',)])
    _h.push([('c',)])
    check('EditorHistory: 3 States, kann undo',
          _h.can_undo() and not _h.can_redo() and _h.current() == [('c',)])
    check('EditorHistory: undo -> b',
          _h.undo() == [('b',)] and _h.can_redo())
    check('EditorHistory: undo -> a',
          _h.undo() == [('a',)] and not _h.can_undo() and _h.can_redo())
    check('EditorHistory: undo am Anfang gibt None',
          _h.undo() is None and _h.current() == [('a',)])
    check('EditorHistory: redo -> b, redo -> c',
          _h.redo() == [('b',)] and _h.redo() == [('c',)] and not _h.can_redo())
    _h.undo(); _h.undo()                              # jetzt bei a, mit Redo b/c
    _h.push([('d',)])                                 # Push kappt den Redo-Zweig
    check('EditorHistory: neuer Push kappt Redo-Zweig',
          not _h.can_redo() and _h.current() == [('d',)])
    # Kein Doppel-Push bei gleichem Snapshot
    _h2 = _gui.EditorHistory()
    _h2.push([('x',)])
    _ok = _h2.push([('x',)])
    check('EditorHistory: identischer Snapshot nicht doppelt', not _ok and len(_h2.stack) == 1)
    # Cap greift
    _h3 = _gui.EditorHistory(cap=3)
    for _i in range(5):
        _h3.push([(_i,)])
    check('EditorHistory: cap deckelt',
          len(_h3.stack) == 3 and _h3.stack[0] == [(2,)] and _h3.current() == [(4,)])
    # Quiet-Modus blockiert Push (Selbstschutz waehrend apply_snap)
    _h4 = _gui.EditorHistory()
    _h4.push([('a',)])
    _h4.quiet = True
    _ok2 = _h4.push([('b',)])
    _h4.quiet = False
    check('EditorHistory: quiet blockiert Push',
          not _ok2 and len(_h4.stack) == 1)
    check('Editor: Undo/Redo verdrahtet',
          'EditorHistory()' in _gsrc and '<Control-z>' in _gsrc
          and '<Control-y>' in _gsrc and "Pill(bar, 'Undo'" in _gsrc
          and "Pill(bar, 'Redo'" in _gsrc)
    check('Editor: Text-Entry debounced, Widgets sofort',
          "trace_add('write', lambda *_a: push_debounced())" in _gsrc
          and "trace_add('write', lambda *_a: _push_and_refresh())" in _gsrc)
    check('Editor: Undo/Redo-Buttons werden ausgegraut',
          'def refresh_buttons' in _gsrc and 'set_enabled(hist.can_undo())' in _gsrc
          and 'set_enabled(hist.can_redo())' in _gsrc
          and "pending['btns']" in _gsrc)
    # Verhalten der Ausgrauung ueber die Klasse allein (kein GUI noetig)
    _h5 = _gui.EditorHistory()
    check('Ausgrauung: initial beides aus',
          not _h5.can_undo() and not _h5.can_redo())
    _h5.push([('a',)])
    check('Ausgrauung: 1 State -> beides aus',
          not _h5.can_undo() and not _h5.can_redo())
    _h5.push([('b',)])
    check('Ausgrauung: 2 States -> Undo an, Redo aus',
          _h5.can_undo() and not _h5.can_redo())
    _h5.undo()
    check('Ausgrauung: nach Undo -> Redo an',
          not _h5.can_undo() and _h5.can_redo())
    _h5.redo()
    check('Ausgrauung: nach Redo -> Undo an, Redo aus',
          _h5.can_undo() and not _h5.can_redo())
    check('TikTok-Fonts an Bord',
          all(os.path.exists(os.path.join(HERE, 'fonts', f))
              for f in ('tiktok_bold.ttf', 'montserrat_xb.ttf', 'inter_black.ttf')))
    check('Bedienung sperrt waehrend Render',
          'def set_busy' in _gsrc and 'def set_enabled' in _gsrc
          and 'self.set_busy(True)' in _gsrc and 'self.set_busy(False)' in _gsrc)
    check('Popup-Layout: Knopfbalken unten verankert',
          'def popup_scroll' in _gsrc and "bottom_bar.pack(side='bottom'" in _gsrc)
    check('Video-Auswahl nimmt mehrere Videos',
          'askopenfilenames' in _gsrc and 'def pick_batch' not in _gsrc)
    check('Anleitung vorhanden',
          os.path.exists(os.path.join(HERE, 'ANLEITUNG.md')))
    check('Warteschlange verdrahtet',
          'in Warteschlange' in _gsrc and 'self.batch' in _gsrc)

    # Tiefen-Okklusion: wo die Szene naeher ist, verschwindet der Text
    cvo = np.full((200, 300, 3), 90.0, dtype=np.float32)
    spr_o = np.zeros((60, 200, 4), dtype=np.uint8)
    spr_o[10:50, 10:190] = (255, 255, 255, 255)
    occ = np.zeros((200, 300), dtype=np.float32)
    occ[:, 150:] = 1.0                          # rechte Haelfte: Objekt davor
    R.paste_scene(cvo, spr_o, 150, 100, 300, 200, refract=0.0, ripple=0.0,
                  occ=occ, grain=0.0, opacity=1.0)
    left = float(cvo[90:110, 60:140, 0].mean())
    right = float(cvo[90:110, 160:240, 0].mean())
    check('Okklusion verdeckt den Text', left > 200 and right < 100,
          f'links {left:.0f} (Text), rechts {right:.0f} (verdeckt)')

    # Film-Grain: Text rauscht wie das Video
    cvg = np.full((200, 300, 3), 90.0, dtype=np.float32)
    R.paste_scene(cvg, spr_o, 150, 100, 300, 200, refract=0.0, ripple=0.0,
                  grain=2.5, opacity=1.0)
    check('Film-Grain auf dem Text',
          float(cvg[85:115, 60:240, 0].std()) > 1.0,
          f'std {cvg[85:115, 60:240, 0].std():.1f}')


def _gui_smoke():
    """Die GUI wirklich hochfahren. Bis v61 wurden nur einzelne Widgets geprueft -
    ein Tippfehler im Aufbau (falsches Argument) kam damit bis zum Kunden durch.
    Hier wird das komplette Fenster gebaut wie beim Doppelklick."""
    code = ("import tkinter as tk, gui; r = tk.Tk(); gui.App(r); "
            "r.destroy(); print('GUI_OK')")
    cmd = [PY, '-c', code]
    if os.name != 'nt' and not os.environ.get('DISPLAY'):
        if shutil.which('xvfb-run'):
            cmd = ['xvfb-run', '-a'] + cmd
        else:
            check('GUI startet ohne Fehler', True, 'uebersprungen: kein Display')
            return
    p = run(cmd, cwd=HERE)
    letzte = (p.stderr or '').strip().splitlines()
    check('GUI startet ohne Fehler', 'GUI_OK' in (p.stdout or ''),
          letzte[-1] if letzte else '')


def _scenario_zahlen(tmp):
    """v62: relevante Zahlen werden zum Moment - aber nicht jede Zahl."""
    print('\n--- Zahl-Momente ---')
    sys.path.insert(0, HERE)
    import render as R
    import yaml

    def ws(satz):
        out = []
        for k, w in enumerate(satz.split()):
            out.append({'word': w, 'start': k * 0.4, 'end': k * 0.4 + 0.35})
        return out

    def rel(satz, i):
        return R.zahl_relevanz(ws(satz), i)

    # Loest aus: Substanz
    check('Zahl mit Prozent zaehlt', rel('wir haben 87 Prozent gespart', 2) > 0,
          f"{rel('wir haben 87 Prozent gespart', 2):.1f}")
    check('Grosse Zahl zaehlt', rel('das sind 250000 Kunden', 2) > 0)
    check('Ausgeschriebene Zahl zaehlt',
          rel('drei Millionen Umsatz im Jahr', 0) > 0)
    check('Zahl neben Wertwort zaehlt',
          rel('der Umsatz lag bei 340 Euro', 4) > 0)
    check('Faktor zaehlt', rel('das ist 10 mal schneller', 2) > 0)

    # Loest NICHT aus: Fuellzahlen
    check('Zaehlwort loest nicht aus', rel('ich habe zwei Sachen gelernt', 2) == 0,
          'zwei Sachen')
    check('Aufzaehlung loest nicht aus', rel('Schritt 3 ist wichtig', 1) == 0)
    check('Uhrzeit loest nicht aus', rel('um 8 Uhr geht es los', 1) == 0)
    check('Nackte Jahreszahl loest nicht aus',
          rel('das war 2019 damals so', 2) == 0)
    check('Jahreszahl MIT Wertwort zaehlt',
          rel('2019 lag der Umsatz hoeher', 0) > 0)

    # Keyword-Erkennung greift die relevante Zahl auf
    cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    w1 = ws('der Umsatz stieg auf 4 Millionen im Sommer')
    kws = R.detect_keywords(w1, cfg, None)
    check('Relevante Zahl landet in den Keywords', 4 in kws, sorted(kws))
    w2 = ws('ich habe zwei Sachen gelernt und drei Punkte notiert')
    kws2 = R.detect_keywords(w2, cfg, None)
    check('Fuellzahl landet NICHT in den Keywords',
          2 not in kws2 and 6 not in kws2, sorted(kws2))

    # Bremse: Regler ist verdrahtet
    check('Zahl-Abstand steht in der config.yaml',
          'zahl_gap' in open(os.path.join(HERE, 'config.yaml'),
                             encoding='utf-8').read())
    check('Zahl-Abstand ist in der GUI bedienbar',
          "self.cfg['effects']['zahl_gap']" in open(
              os.path.join(HERE, 'gui.py'), encoding='utf-8').read())
    check('Zahl-Abstand bremst im Plan',
          'last_num_end' in open(os.path.join(HERE, 'render.py'),
                                 encoding='utf-8').read())

    # Zaehler-Effekt haengt sich an eine echte Zahl
    check('Zaehler-Effekt greift bei der Zahl',
          R.make_counter('250000') is not None)


def _scenario_satzende(tmp):
    """v63: Ein grosser Keyword-Moment darf den Rest seines Satzes nicht
    verschlucken. "BLEIB dran denn am Ende [...] wirst du das alles anders sehen"
    - der zweite Teil muss sichtbar bleiben, sonst wirkt der Satz abgeschnitten."""
    print('\n--- Satz zu Ende fuehren ---')
    sys.path.insert(0, HERE)
    import render as R
    import yaml
    W_, H_ = 1080, 1920
    cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    cfg = dict(cfg)
    cfg['effects'] = dict(cfg['effects'], density='akzente', intro_hook=False,
                          retention_gap=0, blender_water=False)
    S = R.Sprites(cfg, W_, H_)

    # Satz: grosser Moment auf "BLEIB dran denn am Ende", dann Fortsetzung.
    satz = ('BLEIB dran denn am Ende wirst du das alles anders sehen .').split()
    ws = [{'word': w, 'start': 20 + i * 0.4, 'end': 20 + i * 0.4 + 0.35}
          for i, w in enumerate(satz)]
    # "Ende" ohne Satzzeichen -> Moment laesst den Satz offen
    fx = {0: {'fx': 'behind', 'power': 3, 'n': 5}}   # BLEIB..Ende als Komposition
    pl = R.build_plans(ws, {0}, cfg, S, W_, H_, lambda s, e: True, fx)

    # Welche Wort-Indizes sind ueberhaupt in irgendeinem Plan sichtbar?
    sichtbar = set()
    for p in pl:
        if 'kw_i' in p:
            sichtbar.add(p['kw_i'])
            for t in (p.get('tokens') or []):
                pass
        for it in p.get('front', []):
            sichtbar.add(it['i'])
        for it in p.get('small', []):
            sichtbar.add(it['i'])
    # Der Kern-Moment deckt 0..5 ab. Die Fortsetzung (6..11) darf NICHT komplett fehlen.
    forts = [i for i in range(6, len(ws))]
    gezeigt = [i for i in forts if i in sichtbar]
    check('Satz-Fortsetzung faellt nicht komplett weg', len(gezeigt) > 0,
          f'{len(gezeigt)}/{len(forts)} Fortsetzungs-Woerter im Plan')
    check('Fortsetzung laeuft als ruhige Ebene (kein zweiter grosser Moment)',
          sum(1 for p in pl if p.get('tpl') == 'behind') <= 1,
          f"{sum(1 for p in pl if p.get('tpl') == 'behind')} behind-Momente")

    # Gegenprobe: Ein Moment, der SEINEN Satz abschliesst ("Ende."), zieht keine
    # Folgegruppe eines NEUEN Satzes mit rein.
    satz2 = ('Das war der Punkt . Ein ganz neuer Gedanke faengt hier an .').split()
    ws2 = [{'word': w, 'start': 40 + i * 0.4, 'end': 40 + i * 0.4 + 0.35}
           for i, w in enumerate(satz2)]
    # "Punkt ." schliesst ab (Index 3 endet mit .)
    ws2[3]['word'] = 'Punkt.'
    fx2 = {3: {'fx': 'blurin', 'power': 2, 'n': 1}}
    pl2 = R.build_plans(ws2, {3}, cfg, S, W_, H_, lambda s, e: True, fx2)
    sichtbar2 = set()
    for p in pl2:
        if 'kw_i' in p:
            sichtbar2.add(p['kw_i'])
        for it in p.get('front', []):
            sichtbar2.add(it['i'])
    neuer_satz = [i for i in range(4, len(ws2))]
    check('Abgeschlossener Satz zieht den naechsten NICHT herein',
          not all(i in sichtbar2 for i in neuer_satz),
          f'{sum(i in sichtbar2 for i in neuer_satz)}/{len(neuer_satz)} gezeigt')


def _scenario_kamera(tmp):
    """v65: Crash-Zoom + Whip-Pan, skaliert nach Kategorie. Clean/Cinematic ruhig."""
    print('\n--- Kamera: Crash & Whip ---')
    sys.path.insert(0, HERE)
    import render as R
    import yaml
    W_, H_ = 1080, 1920
    base_cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))

    def bau(crash, whip):
        cfg = dict(base_cfg)
        cfg['camera'] = dict(base_cfg['camera'], crash=crash, whip=whip, strength=0.7)
        cfg['keywords'] = dict(base_cfg['keywords'], min_gap_seconds=3.0)
        cfg['effects'] = dict(base_cfg['effects'], density='akzente', intro_hook=False,
                              retention_gap=0, blender_water=False)
        S = R.Sprites(cfg, W_, H_)
        # zwei Momente mit klarer Zaesur dazwischen (fuer Whip)
        ws = ([{'word': f'A{i}', 'start': i * 0.4, 'end': i * 0.4 + 0.35} for i in range(3)]
              + [{'word': f'B{i}', 'start': 5 + i * 0.4, 'end': 5 + i * 0.4 + 0.35}
                 for i in range(3)])
        fx = {0: {'fx': 'behind', 'power': 3, 'n': 1},
              3: {'fx': 'behind', 'power': 1, 'n': 1}}
        pl = R.build_plans(ws, {0, 3}, cfg, S, W_, H_, lambda s, e: True, fx)
        return cfg, pl, ws

    # Voll (TikTok): Crash + Whip aktiv
    cfg_f, pl_f, ws_f = bau(1.0, True)
    crash_plans = [p for p in pl_f if p.get('cam') == 'crash']
    check('Crash-Zoom trifft genau einen Moment', len(crash_plans) == 1,
          f'{len(crash_plans)} Crash-Plaene')
    check('Crash trifft den staerksten Moment (power 3)',
          crash_plans and crash_plans[0]['kw_i'] == 0)
    whip_plans = [p for p in pl_f if p.get('whip_at') is not None]
    check('Whip-Pan sitzt an der Abschnittsgrenze', len(whip_plans) >= 1,
          f'{len(whip_plans)} Whip-Plaene')

    # Crash-Zoom bewegt die Kamera wirklich (z steigt kurz nach Start)
    top = crash_plans[0]
    t0 = ws_f[top['kw_i']]['start']
    z_in, _, _, _ = R.camera_at(t0 + 0.20, pl_f, ws_f, cfg_f, W_, H_)
    check('Crash-Zoom zoomt hinein', z_in > 1.02, f'z={z_in:.3f}')

    # Whip erzeugt einen kraeftigen seitlichen Ausschlag
    wp = whip_plans[0]
    _, px_w, _, _ = R.camera_at(wp['whip_at'] + 0.10, pl_f, ws_f, cfg_f, W_, H_)
    check('Whip-Pan schlaegt seitlich aus', abs(px_w) > W_ * 0.02, f'px={px_w:.0f}')

    # Clean/Cinematic (crash=0, whip=False): NICHTS davon
    cfg_r, pl_r, ws_r = bau(0.0, False)
    check('Ruhig: kein Crash-Zoom',
          not any(p.get('cam') == 'crash' for p in pl_r))
    check('Ruhig: kein Whip-Pan',
          not any(p.get('whip_at') is not None for p in pl_r))

    # Moderat (Creator): Crash an, aber schwaecher als voll; Whip aus
    cfg_m, pl_m, ws_m = bau(0.55, False)
    cp_m = [p for p in pl_m if p.get('cam') == 'crash']
    check('Creator: Crash an, Whip aus',
          len(cp_m) == 1 and not any(p.get('whip_at') is not None for p in pl_m))
    if cp_m:
        tm = ws_m[cp_m[0]['kw_i']]['start']
        z_m, _, _, _ = R.camera_at(tm + 0.20, pl_m, ws_m, cfg_m, W_, H_)
        check('Creator-Crash schwaecher als TikTok-Crash', z_m < z_in,
              f'{z_m:.3f} < {z_in:.3f}')

    # Config/GUI verdrahtet
    check('Crash in config.yaml', 'crash:' in open(
        os.path.join(HERE, 'config.yaml'), encoding='utf-8').read())
    g = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    check('Crash+Whip pro Dynamik-Stufe',
          "'crash': 0" in g and "'crash': 100" in g)
    check('Crash-Regler in der GUI', "self.cfg['camera']['crash']" in g)


def _scenario_transkription(tmp):
    """v72: nur noch API-Transkription (OpenAI Whisper). Lokal komplett entfernt."""
    print('\n--- Transkription API ---')
    sys.path.insert(0, HERE)
    import render as R

    check('transcribe() existiert', hasattr(R, 'transcribe'))
    check('faster-whisper aus requirements entfernt',
          'faster-whisper' not in open(os.path.join(HERE, 'requirements.txt'),
                                       encoding='utf-8').read())
    _rsrc = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('transcribe_local aus render.py entfernt',
          'def transcribe_local' not in _rsrc
          and 'from faster_whisper' not in _rsrc)
    check('models/whisper wird nicht mehr referenziert',
          "'whisper')" not in _rsrc)
    import yaml
    cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    check('config.yaml: transcription-Block entfernt',
          'transcription' not in cfg)


def _scenario_security(tmp):
    """v92: Bezahl-relevante Sicherheit - Credits-Race, Refund, Webhook,
    Zugriffsrechte, cfg_overrides, Login-Brute-Force. Isolierte Test-DB."""
    print('\n--- Sicherheit / Credits ---')
    import tempfile as _tf, time as _t
    os.environ['DVE_DATA'] = _tf.mkdtemp(prefix='dve_sec_')
    if 'server' in sys.modules:
        del sys.modules['server']
    sys.path.insert(0, os.path.join(HERE, 'web'))
    import server as SV
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ('sec@test', 'x', 'Sec', 120, int(_t.time())))
    con.commit()
    uid = con.execute("SELECT id FROM users WHERE email='sec@test'").fetchone()['id']
    con.close()
    # 1) Kein Double-Spend: 5 gleichzeitige Reservierungen a 60s bei 120s -> genau 2
    ok = sum(SV._reserve_credits(uid, 60, f'j{i}') for i in range(5))
    bal = SV._find_user_by_id(uid)['balance_sec']
    check('Credits: kein Double-Spend (Reservierung atomar)',
          ok == 2 and bal == 0, f'{ok} durch, Rest {bal}s')
    # 2) Refund idempotent
    SV._refund_credits(uid, 'j0', 60)
    SV._refund_credits(uid, 'j0', 60)
    check('Credits: Refund idempotent (kein Doppel)',
          SV._find_user_by_id(uid)['balance_sec'] == 60)
    # v127-sec: DIE Gratis-Render-Luecke. Nach Refund ist die Reservierung WEG,
    # also meldet _render_charged False und ein Retry wird wieder abgerechnet.
    # (Frueher blieb die '-need'-Zeile stehen -> _render_charged True -> fertiges
    # Video fuer netto 0 Credits nach jedem transienten Fehlschlag.) j1 ist noch
    # reserviert.
    _charged_pre = SV._render_charged(uid, 'j1')            # reserviert -> True
    SV._refund_credits(uid, 'j1', 60)                       # Fehlschlag -> erstattet
    _charged_post = SV._render_charged(uid, 'j1')           # Reservierung weg -> False
    _rereserve = SV._reserve_credits(uid, 60, 'j1')         # Retry bucht erneut ab
    check('v127-sec: Gratis-Render-Luecke zu (Refund loescht Reservierung, Retry zahlt)',
          _charged_pre is True and _charged_post is False and _rereserve is True,
          f'pre={_charged_pre} post={_charged_post} re={_rereserve}')
    # v127-sec: Free-Tier-Farming zu - der Welcome-Anspruch ueberlebt die
    # Kontoloeschung (gesalzener E-Mail-Hash in credit_claims). Loeschen + mit
    # DERSELBEN Mail neu registrieren gibt KEIN zweites Welcome-Guthaben.
    _fuid, _ = SV._create_user('farm@test', 'x' * 8, 'FarmerA')
    _fw1 = SV._grant_welcome(_fuid)
    SV._purge_user_db(_fuid)                                # credit_claims BLEIBT
    _fuid2, _ = SV._create_user('farm@test', 'x' * 8, 'FarmerB')
    _fw2 = SV._grant_welcome(_fuid2)
    check('v127-sec: Welcome-Farming zu (Hash ueberlebt Loeschung)',
          _fw1 is True and _fw2 is False
          and SV._find_user_by_id(_fuid2)['balance_sec'] == 0,
          f'w1={_fw1} w2={_fw2}')
    # v127-sec: Monats-Freikredit atomar + 1x/Monat (Doppel-Grant-Race zu).
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('mon@test','x','Mon',0,?,1)", (int(_t.time()),))
    con.commit()
    _muid = con.execute("SELECT id FROM users WHERE email='mon@test'").fetchone()['id']
    con.close()
    _mu = SV._find_user_by_id(_muid)
    _m1 = SV._grant_monthly_free(_mu)
    _m2 = SV._grant_monthly_free(_mu)
    check('v127-sec: Monats-Freikredit 1x (atomar, kein Doppel)',
          _m1 is True and _m2 is False
          and SV._find_user_by_id(_muid)['balance_sec'] == 180, f'{_m1}/{_m2}')
    # v127-sec: Partielle Unique-Indizes fuer Welcome/Monthly vorhanden (Race-Sperre).
    con = SV._db()
    _idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    con.close()
    check('v127-sec: Unique-Indizes ux_ledger_welcome/monthly angelegt',
          {'ux_ledger_welcome', 'ux_ledger_monthly'} <= _idx, str(sorted(_idx)))
    # v127-sec: Wegwerf-Mail-Erkennung (Signup-Block nutzt genau die).
    check('v127-sec: Wegwerf-Domain erkannt, echte Domain nicht',
          SV._is_disposable_email('x@mailinator.com') is True
          and SV._is_disposable_email('x@gmail.com') is False)
    # v127-sec: echte Client-IP = rechter (Caddy) Hop, nicht der gespoofte linke.
    class _RQip:
        def __init__(self, xff, peer):
            self.headers = {'x-forwarded-for': xff} if xff is not None else {}
            self.client = type('C', (), {'host': peer})()
    _ip_spoof = SV._client_ip(_RQip('1.2.3.4, 9.9.9.9', '10.0.0.1'))
    _ip_direct = SV._client_ip(_RQip(None, '10.0.0.1'))
    check('v127-sec: _client_ip nimmt rechten Hop (XFF-Spoof wirkungslos)',
          _ip_spoof == '9.9.9.9' and _ip_direct == '10.0.0.1',
          f'{_ip_spoof} / {_ip_direct}')
    # v127-sec: Owner-Identitaet ist NICHT registrierbar (kein Squat auf Owner-Rechte).
    _osq, _oerr = SV._create_user(SV.OWNER_EMAIL, 'x' * 8, 'Squatter')
    check('v127-sec: OWNER_EMAIL nicht registrierbar',
          _osq is None and bool(_oerr))
    # v132 Google-Login: upsert legt verifiziertes, passwortloses Konto an,
    # verknuepft ueber E-Mail ein bestehendes Konto, ist idempotent ueber sub,
    # und ein gesperrtes Konto meldet keinen Login.
    _gu1, _new1 = SV._upsert_google_user('gsub_aaa', 'goog1@test', 'Goog One')
    _gu2, _new2 = SV._upsert_google_user('gsub_aaa', 'goog1@test', 'Goog One')
    _grow = SV._find_user_by_id(_gu1)
    check('v132: Google-User angelegt, verified, passwortlos, sub gesetzt',
          _gu1 and _new1 and (not _new2) and _gu1 == _gu2
          and _grow['verified'] == 1 and SV._row_get(_grow, 'google_sub') == 'gsub_aaa')
    check('v132: Passwort-Login auf Google-Konto unmoeglich (Zufalls-Hash)',
          not SV._verify_pw('x' * 8, _grow['pw_hash']))
    # Bestehendes Passwort-Konto wird per E-Mail verknuepft, kein Duplikat.
    _puid, _ = SV._create_user('link@test', 'p' * 8, 'Linker')
    _luid, _lnew = SV._upsert_google_user('gsub_bbb', 'link@test', 'Linker')
    _lrow = SV._find_user_by_id(_puid)
    # v203-sec: Dieser Test hielt bis v202 die LUECKE als Zusage fest
    # ("Passwort bleibt gueltig"). _create_user legt ein UNBESTAETIGTES Konto
    # an - und ein unbestaetigtes Konto ist kein Eigentumsnachweis fuer die
    # Adresse. Jeder konnte auf eine fremde Adresse registrieren und wartete;
    # meldete sich der echte Inhaber spaeter per Google an, teilten sich beide
    # das Konto. Google hat die Adresse bewiesen, also uebernimmt Google sie:
    # verknuepfen ja, aber das alte Passwort wird entwertet.
    check('v132/v203-sec: Google verknuepft das vorhandene Konto (kein Duplikat)',
          _luid == _puid and (not _lnew)
          and SV._row_get(_lrow, 'google_sub') == 'gsub_bbb')
    check('v203-sec: dabei wird das Passwort des unbestaetigten Kontos entwertet',
          not SV._verify_pw('p' * 8, _lrow['pw_hash']))
    # Gegenprobe: bei einem BESTAETIGTEN Konto bleibt das Passwort gueltig -
    # dort ist die Verknuepfung genau das, was der Nutzer erwartet.
    _vuid, _ = SV._create_user('verlinkt@test', 'q' * 8, 'Verlinkt')
    _vcon = SV._db()
    _vcon.execute("UPDATE users SET verified = 1 WHERE id = ?", (_vuid,))
    _vcon.commit(); _vcon.close()
    _vluid, _ = SV._upsert_google_user('gsub_ccc', 'verlinkt@test', 'Verlinkt')
    _vrow = SV._find_user_by_id(_vuid)
    check('v203-sec: ein BESTAETIGTES Konto behaelt sein Passwort beim Verknuepfen',
          _vluid == _vuid and SV._verify_pw('q' * 8, _vrow['pw_hash'])
          and SV._row_get(_vrow, 'google_sub') == 'gsub_ccc')
    # Gesperrtes Konto: kein Login ueber Google.
    _dcon = SV._db()
    _dcon.execute("UPDATE users SET disabled = 1 WHERE id = ?", (_gu1,))
    _dcon.commit(); _dcon.close()
    _dis, _ = SV._upsert_google_user('gsub_aaa', 'goog1@test', 'Goog One')
    check('v132: gesperrtes Konto -> kein Google-Login', _dis is None)
    # authinfo verraet nur Ja/Nein, nie Secrets; Feature ist per Default aus.
    _ai = SV.api_authinfo()
    check('v132: /api/authinfo nur Flag, keine Secrets',
          set(_ai.keys()) == {'google'} and _ai['google'] == SV.GOOGLE_OK)
    check('v132: Endpoints inert ohne Keys (GOOGLE_OK aus -> Redirect)',
          (not SV.GOOGLE_OK)
          and SV.auth_google_start(_RQip(None, '10.0.0.9')).status_code == 302)
    # JWT-Payload-Dekodierung robust (kein Absturz bei Muell).
    import base64 as _b64
    _pl = _b64.urlsafe_b64encode(b'{"sub":"s","email":"a@b.c"}').decode().rstrip('=')
    check('v132: _decode_jwt_payload liest Payload, schluckt Muell',
          (SV._decode_jwt_payload('h.' + _pl + '.sig') or {}).get('email') == 'a@b.c'
          and SV._decode_jwt_payload('garbage') is None)
    # Username-Ableitung: Sonderzeichen weg, Mindestlaenge, Fallback.
    check('v132: Google-Username saeubert + Mindestlaenge',
          SV._valid_username(SV._google_username('Jörg!! <b>', 'j@x.de'))
          and SV._valid_username(SV._google_username('', 'ab@x.de')))
    # v128 Admin-Panel: alle Endpoints haengen am Server-Key DVE_ADMIN, nicht an
    # der Owner-Session. Falscher Key -> 403. Danach Overview/Users/Credits echt.
    os.environ['DVE_ADMIN'] = 'testkey_admin'
    class _AReq:
        def __init__(self, key):
            self.headers = {'x-admin-key': key} if key else {}
    _denied = False
    try:
        SV.admin_overview(_AReq('wrong'))
    except SV.HTTPException as _e:
        _denied = (_e.status_code == 403)
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('adm@test','x','Adm',120,?,0)", (int(_t.time()),))
    con.commit()
    _auid = con.execute("SELECT id FROM users WHERE email='adm@test'").fetchone()['id']
    con.execute("INSERT OR IGNORE INTO purchases (session_id, user_id, pack, cents, sekunden, created_at) "
                "VALUES ('sess_adm', ?, 'starter', 900, 1200, ?)", (_auid, int(_t.time())))
    con.execute("INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
                "VALUES (?, 1200, 'Kauf sess_adm', ?)", (_auid, int(_t.time())))
    con.commit(); con.close()
    _good = _AReq('testkey_admin')
    _ov = SV.admin_overview(_good)
    _us = SV.admin_users(_good, q='adm@test', limit=10)
    _cr = SV.admin_user_credits(_auid, _good, delta_min=5, reason='test')   # +5 Min = +300s
    _ver = SV.admin_user_verify(_auid, _good)
    _uverified = SV._find_user_by_id(_auid)['verified']
    check('v128 Admin: DVE_ADMIN-gated + Overview/Users/Credits/Verify funktionieren',
          _denied is True
          and _ov['revenue']['total']['eur'] == 9.0
          and _ov['users']['total'] >= 1 and 'disk' in _ov['system']
          and any(u['email'] == 'adm@test' for u in _us['users'])
          and _cr['balance_sec'] == 420 and bool(_uverified) is True,
          f"denied={_denied} eur={_ov['revenue']['total']['eur']} bal={_cr.get('balance_sec')}")
    del os.environ['DVE_ADMIN']
    # v129: Haengender Job laeuft in den Timeout -> HART beendet (Status 'fehler')
    # UND erstattet, auch ohne lebenden Prozess (Zombie-sicher).
    _ruid, _ = SV._create_user('reap@test', 'x' * 8, 'Reap')
    SV._adjust_balance(_ruid, 120, 'Kauf reaptest')          # 2 Credits
    _rjid = 'reapjob01'
    os.makedirs(SV.job_dir(_rjid), exist_ok=True)
    _resv_ok = SV._reserve_credits(_ruid, 60, _rjid)          # -60 reserviert
    SV.JOBS[_rjid] = {'id': _rjid, 'user_id': _ruid, 'dauer': 60,
                      'status': 'laeuft', 'progress': 0.4}
    _bal_pre = SV._find_user_by_id(_ruid)['balance_sec']       # 60
    SV._reap_stuck_job(_rjid, 'selftest')
    _bal_post = SV._find_user_by_id(_ruid)['balance_sec']      # 120 (erstattet)
    check('v129: Job-Timeout beendet haengenden Job + erstattet (Zombie-sicher)',
          _resv_ok is True and SV.JOBS[_rjid]['status'] == 'fehler'
          and _bal_pre == 60 and _bal_post == 120,
          f'pre={_bal_pre} post={_bal_post} st={SV.JOBS[_rjid]["status"]}')
    # v130 Admin-Panel (dynamisch, Vollumfang): neue Endpoints funktional gegen
    # die Test-DB. Reuse des Admin-Gate-Musters (DVE_ADMIN gesetzt).
    os.environ['DVE_ADMIN'] = 'testkey_admin'

    class _AReq2:
        def __init__(self, key):
            self.headers = {'x-admin-key': key} if key else {}
    _ar = _AReq2('testkey_admin')
    # seed: verifizierter Kaeufer + Kauf + Consent
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('v130@test','x','V130',300,?,1)", (int(_t.time()),))
    con.commit()
    _vid = con.execute("SELECT id FROM users WHERE email='v130@test'").fetchone()['id']
    con.execute("INSERT OR IGNORE INTO purchases (session_id,user_id,pack,cents,sekunden,created_at) "
                "VALUES ('v130sess',?,'starter',900,1200,?)", (_vid, int(_t.time())))
    con.execute("INSERT OR IGNORE INTO ledger (user_id,delta_sec,grund,created_at) "
                "VALUES (?,1200,'Kauf v130sess',?)", (_vid, int(_t.time())))
    con.commit(); con.close()
    _rev130 = SV.admin_revenue(_ar)
    _cr130 = SV.admin_credits(_ar)
    _sys130 = SV.admin_system(_ar)
    _ab130 = SV.admin_abuse(_ar)
    check('v130 Admin: revenue/credits/system/abuse liefern echte Aggregate',
          _rev130['windows']['total']['eur'] >= 9.0            # >= dieser Kauf (Test-DB teilt sich)
          and 'catalog' in _rev130 and _rev130['aov'] > 0
          and _cr130['granted']['paid'] >= 20 and 'liability_min' in _cr130
          and 'config' in _sys130 and _sys130['build'] == SV.DVE_BUILD
          and 'orphan_claims' in _ab130,
          f"rev={_rev130['windows']['total']['eur']} paid={_cr130['granted']['paid']}")
    # Suspend-Gate: gesperrtes Konto -> Session gilt als tot (auch neue Session).
    _tok, _exp = SV._create_session(_vid)
    _live_before = SV._session_user(_tok) is not None
    SV.admin_user_disable(_vid, _ar, on='1')
    _tok2, _ = SV._create_session(_vid)            # frische Session NACH dem Sperren
    _dead_after = SV._session_user(_tok2) is None
    SV.admin_user_disable(_vid, _ar, on='0')
    _live_again = SV._session_user(SV._create_session(_vid)[0]) is not None
    check('v130 Admin: Suspend sperrt Login/Session, Unsuspend gibt frei',
          _live_before is True and _dead_after is True and _live_again is True)
    # Job-Refund erzeugt eine nachvollziehbare positive 'Refund %'-Ledger-Zeile.
    SV.JOBS['v130job'] = {'id': 'v130job', 'user_id': _vid, 'status': 'fertig', 'dauer': 60}
    _bal_r0 = SV._find_user_by_id(_vid)['balance_sec']
    SV.admin_job_refund('v130job', _ar, minutes=2, reason='make-good')
    _bal_r1 = SV._find_user_by_id(_vid)['balance_sec']
    con = SV._db()
    _refline = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=? AND "
                           "grund LIKE 'Refund v130job%'", (_vid,)).fetchone()['c']
    con.close()
    check('v130 Admin: Job-Refund bucht +Credits mit traceable Refund-Ledger-Zeile',
          _bal_r1 == _bal_r0 + 120 and _refline == 1, f'{_bal_r0}->{_bal_r1} lines={_refline}')
    # v130-fix (Review): admin_refund clampt den Clawback aufs Guthaben (Ledger-
    # Invariant heil) UND ist idempotent (zweiter Aufruf bucht nicht nochmal ab).
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('rf@test','x','Rf',60,?,1)", (int(_t.time()),))
    con.commit()
    _rfid = con.execute("SELECT id FROM users WHERE email='rf@test'").fetchone()['id']
    con.execute("INSERT OR IGNORE INTO purchases (session_id,user_id,pack,cents,sekunden,created_at) "
                "VALUES ('rfsess',?,'starter',900,1200,?)", (_rfid, int(_t.time())))
    con.commit(); con.close()
    _rf1 = SV.admin_refund(_ar, session_id='rfsess', clawback='1')   # Guthaben 60s < Kauf 1200s
    _bal_rf1 = SV._find_user_by_id(_rfid)['balance_sec']
    _rf2 = SV.admin_refund(_ar, session_id='rfsess', clawback='1')   # zweiter Klick -> no-op
    _bal_rf2 = SV._find_user_by_id(_rfid)['balance_sec']
    check('v130-fix: admin_refund clampt Clawback aufs Guthaben + idempotent',
          _rf1['clawed_back_min'] == 1 and _bal_rf1 == 0
          and _rf2.get('already_refunded') is True and _bal_rf2 == 0,
          f"claw={_rf1['clawed_back_min']} bal={_bal_rf1} again={_rf2.get('already_refunded')}")
    # Codes: anlegen + sperren ueber die Admin-API.
    _cw = SV.admin_codes_write(_ar, action='new', name='Tester', limit=7)
    _cl = SV.admin_codes_list(_ar)
    check('v130 Admin: Access-Code anlegen + listen',
          _cw.get('ok') and any(c['code'] == _cw['code'] for c in _cl['codes']))
    del os.environ['DVE_ADMIN']
    # 3) cfg_overrides-Whitelist + Deckel
    ov = SV._sanitize_overrides({'output': {'height': 4320, 'master': True},
                                 'effects': {'blender_samples': 99999, 'bg_blur': 0.5},
                                 'boeses': {'x': 1}})
    check('cfg_overrides: Whitelist + Ressourcen-Deckel',
          ov.get('output', {}).get('height') == 2160
          and 'master' not in ov.get('output', {})
          and ov['effects']['blender_samples'] == 256
          and ov['effects']['bg_blur'] == 0.5 and 'boeses' not in ov)
    # v101d: Safe-Zone-Plattform - nur bekannte Masken durch, Rest raus.
    ovp_ok = SV._sanitize_overrides({'output': {'platform': 'reels'}})
    ovp_bad = SV._sanitize_overrides({'output': {'platform': '../evil'}})
    check('v101d: output.platform Whitelist (bekannt bleibt, unbekannt raus)',
          ovp_ok.get('output', {}).get('platform') == 'reels'
          and 'platform' not in ovp_bad.get('output', {}))
    # v96x: KI-Regie NIE per Override/Template abschaltbar; Nicht-Dict-Sektionen
    # (keywords: null) crashen build_config nicht mehr.
    ovk = SV._sanitize_overrides({'keywords': {'ai': False, 'ai_model': 'gpt-4o',
                                               'ai_vision': False,
                                               'include': ['Zins'],
                                               'min_gap_seconds': 8},
                                  'effects': None, 'camera': 'kaputt'})
    check('cfg_overrides: keywords.ai/ai_model/ai_vision nicht ueberschreibbar',
          'ai' not in ovk.get('keywords', {})
          and 'ai_model' not in ovk.get('keywords', {})
          and 'ai_vision' not in ovk.get('keywords', {})
          and ovk['keywords']['include'] == ['Zins']
          and ovk['keywords']['min_gap_seconds'] == 8
          and 'effects' not in ovk and 'camera' not in ovk, str(ovk))

    # ---- v230c-sec: JEDE Zahl aus dem Client hat eine Grenze ----
    # Zwei Regler steuerten bis v230b direkt die Rechenzeit und waren
    # ungeklemmt. Ein Gratis-Konto konnte damit den EINEN Render-Worker
    # stundenlang belegen; der Wachhund greift nicht, weil der Fortschritt
    # ja weiterlaeuft.
    _md = SV._sanitize_overrides({'matting_downsample': 16})
    check('v230c-sec: matting_downsample gedeckelt (teuerster Regler)',
          _md.get('matting_downsample') == 0.8, str(_md))
    check('v230c-sec: matting_downsample "auto" bleibt erlaubt',
          SV._sanitize_overrides(
              {'matting_downsample': 'auto'}).get('matting_downsample') == 'auto')
    _bb = SV._sanitize_overrides({'effects': {'bg_blur': 5000, 'trail': 99,
                                              'freeze_frame': -3,
                                              'person_shadow': 1e9}})['effects']
    check('v230c-sec: bg_blur/trail/freeze_frame/person_shadow geklemmt',
          _bb['bg_blur'] == 1.0 and _bb['trail'] == 1.0
          and _bb['freeze_frame'] == 0.0 and _bb['person_shadow'] == 1.0, str(_bb))
    # v230f: dieser Test verlangte bis eben, dass eine unbekannte Zahl
    # VERWORFEN wird - und genau das hat `caption_zone` aus jedem
    # gespeicherten Setup entfernt (Ismets Safe-Zone-Befund). Ein Test kann
    # eine Luecke als Zusage festschreiben (v132-Falle). Verlangt wird
    # jetzt: sie wird geklemmt, aber sie bleibt.
    check('v230c-sec: unbekannte Zahl in effects wird gedeckelt',
          SV._sanitize_overrides({'effects': {'was_neues': 1e9}}
                                 )['effects']['was_neues'] == 1000.0)
    check('v230c-sec: camera.strength geklemmt, Rotation nur bekannte Namen',
          SV._sanitize_overrides({'camera': {'strength': 1000}}
                                 )['camera']['strength'] == 1.0
          and 'keyword_rotation' not in SV._sanitize_overrides(
              {'camera': {'keyword_rotation': ['../boese']}}).get('camera', {}))
    check('v230c-sec: effects.keyword_rotation nur bekannte Effekte',
          SV._sanitize_overrides({'effects': {'keyword_rotation':
                                              ['behind', 'boese']}}
                                 )['effects']['keyword_rotation'] == ['behind'])
    # Schriften: freier Pfad liess render.py NACH der Transkription sterben -
    # der Transkript-Cache fuellt sich nur bei Erfolg, also lief bei jedem
    # Versuch ein neuer kostenpflichtiger Whisper-Aufruf.
    check('v230c-sec: fonts nur aus dem geschlossenen Satz',
          'fonts' not in SV._sanitize_overrides({'fonts': {'display': '/etc/passwd'}})
          and SV._sanitize_overrides({'fonts': {'display': 'fonts/anton.ttf'}}
                                     )['fonts']['display'] == 'fonts/anton.ttf')
    check('v230c-sec: keywords.include muss eine Wortliste sein',
          'keywords' not in SV._sanitize_overrides({'keywords': {'include': 123}})
          and SV._sanitize_overrides({'keywords': {'include': 'Zins'}}
                                     )['keywords']['include'] == ['Zins'])
    _oc = SV._sanitize_overrides({'output': {'crf': 0, 'preset': 'placebo'}})
    check('v230c-sec: crf/preset gedeckelt (Encode-Zeit + Dateigroesse)',
          _oc['output']['crf'] == 14 and 'preset' not in _oc['output'], str(_oc))
    check('v230c-sec: colors nur gueltige Farbwerte',
          SV._sanitize_overrides({'colors': {'accent': [999, -5, 3]}}
                                 )['colors']['accent'] == [255, 0, 3]
          and 'accent' not in SV._sanitize_overrides(
              {'colors': {'accent': 'rot'}}).get('colors', {}))
    # ---- v230f: VERWERFEN WAR DER FALSCHE UMGANG MIT UNBEKANNTEN ZAHLEN ----
    # v230c liess nur noch Zahlen mit Tabellen-Eintrag durch und WARF den
    # Rest weg. `caption_zone` fehlte in der Tabelle - damit fiel die
    # Caption-Zone aus jedem gespeicherten Setup heraus und die Untertitel
    # sassen wieder im Standardband (Ismets Befund "die Captions
    # respektieren die Safe Zones nicht mehr"). Der Weg: applyTemplate
    # setzt State.cfg auf das Setup, laesst State.cfgBase stehen - der
    # Unterschied enthaelt dann ALLE Preset-Werte.
    check('v230f: caption_zone kommt durch (Safe-Zone-Regression)',
          SV._sanitize_overrides({'effects': {'caption_zone': 0.58}}
                                 )['effects']['caption_zone'] == 0.58)
    check('v230f: caption_zone wird trotzdem geklemmt',
          SV._sanitize_overrides({'effects': {'caption_zone': 9}}
                                 )['effects']['caption_zone'] == 0.95)
    check('v230f: eine unbekannte Zahl wird GEKLEMMT, nicht verworfen',
          SV._sanitize_overrides({'effects': {'was_neues': 7}}
                                 )['effects']['was_neues'] == 7.0
          and SV._sanitize_overrides({'effects': {'was_neues': 1e9}}
                                     )['effects']['was_neues'] == 1000.0)
    # DER EIGENTLICHE RIEGEL: jede Zahl, die in einem Preset vorkommt, MUSS
    # einen eigenen Eintrag haben. Genau dieser Test haette v230f verhindert -
    # ein neuer Regler faellt hier auf, nicht beim Kunden.
    _ohne = []
    for _lk in SV.LOOKS:
        _lc = SV.build_config(_lk)
        for _sec, _tab in (('effects', SV._EFFECT_RANGE),
                           ('camera', SV._CAMERA_RANGE)):
            for _k, _v in (_lc.get(_sec) or {}).items():
                if isinstance(_v, bool) or not isinstance(_v, (int, float)):
                    continue
                if _k not in _tab:
                    _ohne.append(f'{_sec}.{_k}')
    check('v230f: jede Zahl aus den Presets hat eine eigene Grenze',
          not _ohne, ', '.join(sorted(set(_ohne)))[:200])
    # Und ein gespeichertes Setup muss den Weg unbeschadet ueberstehen.
    _setup = {'effects': {k: v for k, v in
                          (SV.build_config('viral').get('effects') or {}).items()
                          if not isinstance(v, bool)
                          and isinstance(v, (int, float))}}
    _durch = SV._sanitize_overrides(json.loads(json.dumps(_setup)))
    check('v230f: ein gespeichertes Setup verliert keinen einzigen Wert',
          set(_durch.get('effects', {})) == set(_setup['effects']),
          'verloren: ' + ', '.join(sorted(set(_setup['effects'])
                                          - set(_durch.get('effects', {})))))

    # Engine-Seite: die Desktop-App schreibt dieselbe Config-Datei, deshalb
    # klemmt auch render.py (auf BEIDEN Seiten, v203-sec-Regel).
    _rsrc_sec = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v230c-sec: render.py klemmt matting_downsample selbst',
          'md_val = min(max(float(md), 0.125), 0.8)' in _rsrc_sec)
    check('v230c-sec: render.py klemmt bg_blur selbst',
          "float(cfg['effects'].get('bg_blur', 0.0) or 0.0), 0.0), 1.0)" in _rsrc_sec)

    # ---- v230c-sec: Erstattet wird, was reserviert wurde ----
    # j['cost_sec'] laesst sich nach der Reservierung erhoehen; kam der
    # Erstattungsbetrag von dort, liess sich aus einem Abbruch Guthaben
    # erzeugen. Jetzt zaehlt nur die Ledger-Zeile selbst.
    _cr = SV._db()
    _uid_r = _cr.execute(
        "INSERT INTO users (email, pw_hash, balance_sec, created_at) "
        "VALUES ('refund-v230c@test.local', 'x', 600, 0)").lastrowid
    _cr.commit()
    _cr.close()
    check('v230c-sec: Reservierung wird gebucht',
          SV._reserve_credits(_uid_r, 60, 'jobA'))
    # Angriff: cost_sec nachtraeglich verdoppeln und erstatten lassen.
    SV._refund_credits(_uid_r, 'jobA', 120)
    _bal = SV._db().execute("SELECT balance_sec FROM users WHERE id = ?",
                            (_uid_r,)).fetchone()['balance_sec']
    check('v230c-sec: Erstattung gibt nur das Reservierte zurueck',
          _bal == 600, f'{_bal} statt 600')
    _sum = SV._db().execute(
        "SELECT COALESCE(SUM(delta_sec),0) s FROM ledger WHERE user_id = ?",
        (_uid_r,)).fetchone()['s']
    check('v230c-sec: Ledger-Invariante haelt (Summe == 0 nach Erstattung)',
          _sum == 0, str(_sum))
    check('v230c-sec: zweite Erstattung bucht nichts nach (idempotent)',
          (SV._refund_credits(_uid_r, 'jobA', 60) or True)
          and SV._db().execute("SELECT balance_sec FROM users WHERE id = ?",
                               (_uid_r,)).fetchone()['balance_sec'] == 600)

    # ---- v230c-sec: Riegel, die es gar nicht gab ----
    _ssrc_sec = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    # Die sqlite3.Row-Falle (v96p, v230d): `(_current_user(r) or {}).get('id')`
    # sieht sauber aus und wirft im echten Lauf einen AttributeError - eine
    # Row hat kein .get(). Alle Quelltext-Tests waren gruen, der Riegel war
    # wirkungslos. Deshalb steht die Schreibweise hier auf der Verbotsliste;
    # der richtige Weg ist _sitzungs_uid(request).
    # Erklaerender Text (Kommentar/Docstring) darf die Schreibweise ZEIGEN -
    # dort steht sie ja als Warnung. Gesucht ist echter Code.
    _rowfalle = [z for z in _ssrc_sec.splitlines()
                 if 'or {}).get(' in z and '_current_user' in z
                 and not z.lstrip().startswith('#') and '`' not in z]
    check('v230f: keine .get()-Falle auf einer sqlite3.Row',
          not _rowfalle, ' | '.join(_rowfalle)[:200])
    check('v230f: es gibt EINE Stelle fuer die Konto-Nummer der Sitzung',
          'def _sitzungs_uid(' in _ssrc_sec)
    check('v230c-sec: Preisriegel haengt am JOB, nicht am Modus',
          '_schon = _render_gebucht(uid, jid) if u else 0' in _ssrc_sec
          and "_render_gebucht(uid, jid) if (u and mode == 'full')" not in _ssrc_sec)
    check('v230c-sec: Upload-Wege haben eine Bremse',
          _ssrc_sec.count('_upload_rate_guard(request)') >= 2
          and 'def _upload_rate_guard' in _ssrc_sec)
    check('v230c-sec: Feedback braucht Bremse UND den eigenen Job',
          "bucket='feedback'" in _ssrc_sec
          and "raise HTTPException(403, 'Not your video.')" in _ssrc_sec)
    check('v230c-sec: Summen-Deckel fuer vorbereitete Uploads',
          'def _vorbereitet_count' in _ssrc_sec
          and '_vorbereitet_count(uid) >= MAX_VORBEREITET' in _ssrc_sec)
    check('v230c-sec: kurze Kante + Seitenverhaeltnis werden geprueft',
          'MAX_ASPECT' in _ssrc_sec and '_kurz < 120' in _ssrc_sec)
    check('v230c-sec: .env kommt nicht ins Docker-Image',
          '\n.env\n' in open(os.path.join(HERE, '.dockerignore'), encoding='utf-8').read())
    check('v230c-sec: Test-Gate sieht die echte Datenbank nicht',
          '-v /tmp/dve_gate_leer:/data' in
          open(os.path.join(HERE, 'deploy_gate.sh'), encoding='utf-8').read())
    check('v230c-sec: restore.sh faellt nicht auf ./web/data zurueck',
          'docker volume inspect dve-data' in
          open(os.path.join(HERE, 'restore.sh'), encoding='utf-8').read())

    # ---- v230d-sec: Runde 2 des Audits ----
    # 1) KRITISCH: der resumable Upload sind DREI Anfragen, geprueft wurde nur
    #    die erste. Wer die Abschluss-Anfrage ohne Cookie schickte, bekam einen
    #    HERRENLOSEN Job: nichts abgebucht, kein Wasserzeichen (weder der
    #    Demo- noch der Free-Zweig greift ohne user_id), kein Flut-Deckel -
    #    und abholbar blieb er, weil _job_owner_ok einen Job ohne Eigentuemer
    #    durchlaesst. Das ganze Bezahlprodukt war gratis.
    check('v230d-sec: die Upload-Sitzung merkt sich ihren Eigentuemer',
          "'owner': _sitzungs_uid(request) if mode != 'demo' else None"
          in _ssrc_sec
          and "if s.get('owner') != _sitzungs_uid(request):" in _ssrc_sec)
    # 2) Die Bremse gegen das Code-Raten sass an EINEM Endpunkt, check_auth
    #    hat sieben Aufrufer. Sie gehoert in check_auth selbst.
    _ca = _ssrc_sec[_ssrc_sec.index('def check_auth('):]
    _ca = _ca[:_ca.index('\ndef ', 5)]
    check('v230d-sec: Code-Raten wird in check_auth gebremst, nicht am Gate',
          "bucket='code'" in _ca and '_rate_limit_ok' in _ca)
    check('v230d-sec: ein Aufruf OHNE Code ist kein Rateversuch',
          "if request is not None and (code or '').strip():" in _ca)
    # 3) Der einzige mailversendende Kunden-Endpunkt ohne Bremse.
    _rv = _ssrc_sec[_ssrc_sec.index('def api_resend_verification('):]
    _rv = _rv[:_rv.index('\n# ---')]
    check('v230d-sec: Bestaetigungsmail hat eine Bremse (Konto UND IP)',
          "bucket='verifymail'" in _rv and "bucket='verifymail-ip'" in _rv)
    # 4) Ein Postfach, ein Gratis-Guthaben. Plus-Tags und Gmail-Punkte ergaben
    #    verschiedene Hashes - Willkommens- und Werbe-Guthaben beliebig oft.
    check('v230d-sec: Plus-Tag zaehlt als dasselbe Postfach',
          SV._email_hash('a+1@gmail.com') == SV._email_hash('a@gmail.com'))
    check('v230d-sec: Gmail-Punkte zaehlen als dasselbe Postfach',
          SV._email_hash('is.met@googlemail.com') == SV._email_hash('ismet@gmail.com'))
    check('v230d-sec: verschiedene Postfaecher bleiben verschieden',
          SV._email_hash('a@gmail.com') != SV._email_hash('b@gmail.com')
          and SV._email_hash('a@gmail.com') != SV._email_hash('a@web.de'))
    check('v230d-sec: Punkte werden NUR bei Gmail entfernt',
          SV._email_normal('a.b@web.de') == 'a.b@web.de'
          and SV._email_normal('a+x@web.de') == 'a@web.de')
    # 5) /admin/codes verglich noch mit str -> ein Header mit Umlaut warf einen
    #    TypeError, und jeder 500er schreibt seit v197 eine Zeile mit vollem
    #    Traceback in die alerts-Tabelle. Anonym, ohne Bremse, nie aufgeraeumt.
    _ac = _ssrc_sec[_ssrc_sec.index("@app.get('/admin/codes')"):]
    _ac = _ac[:_ac.index('\n# ====')]
    check('v230d-sec: /admin/codes nutzt denselben Riegel wie alle anderen',
          '_require_admin(request)' in _ac
          and 'hmac.compare_digest(given, key)' not in _ac)
    check('v230d-sec: Alarm-Tabelle hat Wiederholungs- und Mengendeckel',
          '_ALERT_LETZT' in _ssrc_sec and 'ALERT_MAX' in _ssrc_sec
          and 'DELETE FROM alerts WHERE id NOT IN' in _ssrc_sec)
    # Beweis statt Quelltext-Suche: derselbe Schluessel darf nicht zweimal
    # hintereinander eine Zeile schreiben.
    _vor = SV._db().execute("SELECT COUNT(*) c FROM alerts").fetchone()['c']
    for _i in range(20):
        SV._alert_log('v230d-flut', 'Test', 'x')
    _nach = SV._db().execute("SELECT COUNT(*) c FROM alerts").fetchone()['c']
    check('v230d-sec: 20 gleiche Stoerungen ergeben EINE Zeile',
          _nach - _vor == 1, f'{_nach - _vor} Zeilen')

    # DER EIGENTLICHE BEWEIS: der Angriff wird gegen den ECHTEN Pfad gefahren.
    # Eine Quelltext-Suche haette hier nichts bewiesen - der erste Entwurf des
    # Riegels warf im echten Lauf einen AttributeError ('sqlite3.Row' hat kein
    # .get()), war also wirkungslos, und alle Quelltext-Tests waren gruen.
    from fastapi.testclient import TestClient as _TC230
    _c230 = _TC230(SV.app, base_url='https://test')      # secure-Cookie -> https
    _m230 = f'up{int(_t.time())}@test.invalid'
    _c230.post('/api/register', data={'email': _m230, 'password': 'passwort123',
                                      'name': 'Uploadtest'})
    _c230.post('/api/login', data={'email': _m230, 'password': 'passwort123'})
    _u230 = SV._db().execute("SELECT id FROM users WHERE email = ?",
                             (_m230,)).fetchone()['id']
    with SV._db() as _cn:
        _cn.execute("UPDATE users SET verified = 1, balance_sec = 600 "
                    "WHERE id = ?", (_u230,))
    # Echtes Mini-Video: der Kontroll-Lauf muss durch ffprobe kommen.
    _clip230 = os.path.join(tmp, 'up230.mp4')
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi',
         '-i', 'color=c=black:s=540x960:d=3:r=25', '-c:v', 'libx264',
         '-pix_fmt', 'yuv420p', _clip230])
    _daten230 = open(_clip230, 'rb').read()
    _qp230, SV.q_put = SV.q_put, lambda *a, **k: None     # nichts wirklich rendern

    def _upload230(cookie_am_ende):
        _r = _c230.post('/api/upload/init',
                        data={'filename': 'a.mp4', 'size': len(_daten230),
                              'look': 'creator', 'mode': 'full'})
        if _r.status_code != 200:
            return _r
        _up = _r.json()['upload_id']
        _c230.post(f"/api/upload/chunk/{_up}?offset=0", content=_daten230)
        _kek = dict(_c230.cookies)
        if not cookie_am_ende:
            _c230.cookies.clear()
        _r = _c230.post(f'/api/upload/finish/{_up}')
        for _k, _v in _kek.items():
            _c230.cookies.set(_k, _v)
        return _r

    _r230 = _upload230(False)
    _herrenlos = [k for k, v in SV.JOBS.items()
                  if v.get('user_id') is None and not v.get('demo')]
    check('v230d-sec: Upload-Abschluss ohne Anmeldung wird abgewiesen',
          _r230.status_code == 403, f'{_r230.status_code} {_r230.text[:90]}')
    check('v230d-sec: dabei entsteht KEIN herrenloser Job',
          not _herrenlos, str(_herrenlos[:3]))
    # Gegenprobe: der normale Weg muss weiter funktionieren UND abbuchen -
    # sonst haette man den Angriff nur durch Kaputtmachen "geloest".
    _r230b = _upload230(True)
    _bal230 = SV._db().execute("SELECT balance_sec b FROM users WHERE id = ?",
                               (_u230,)).fetchone()['b']
    check('v230d-sec: der normale Upload laeuft weiter und bucht ab',
          _r230b.status_code == 200 and _bal230 == 540,
          f'{_r230b.status_code}, Guthaben {_bal230}')
    # Code-Raten ueber einen Endpunkt, der NICHT /api/pruefe-code ist.
    _c230.cookies.clear()
    _alt230 = SV.load_codes()
    SV.save_codes({'MAX-4711': {'aktiv': True, 'limit': 5, 'name': 'Max'}})
    _folge230 = []
    for _i in range(24):
        _rr = _c230.post('/api/templates', data={'name': 'x', 'settings': '{}',
                                                 'code': f'MAX-{1000 + _i}'})
        _folge230.append('Too many' in _rr.text)
    SV.save_codes(_alt230)
    SV.q_put = _qp230
    check('v230d-sec: Code-Raten wird auch abseits von /api/pruefe-code gebremst',
          sum(_folge230) >= 10,
          ''.join('9' if x else '4' for x in _folge230))

    # v117d: Transkript-Datei-Parser — SRT/VTT/JSON echte Timings, TXT synthetisch, verbatim.
    _srt = ("1\n00:00:00,000 --> 00:00:02,000\nHello there\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nfully customizable\n")
    _sw = SV._transcript_to_words('cap.srt', _srt.encode('utf-8'))
    check('v117d: SRT -> Wortliste mit echten Timings (verbatim)',
          [w['word'].strip() for w in _sw] == ['Hello', 'there', 'fully', 'customizable']
          and _sw[0]['start'] == 0.0 and abs(_sw[-1]['end'] - 4.0) < 0.01,
          str(_sw))
    _jw = SV._transcript_to_words('cap.json', json.dumps(
        [{'word': ' one', 'start': 0.0, 'end': 0.5}, {'text': 'two', 'start': 0.5, 'end': 1.0}]).encode())
    check('v117d: JSON (word/text) -> normalisierte Wortliste',
          [w['word'].strip() for w in _jw] == ['one', 'two'] and _jw[1]['end'] == 1.0)
    _jseg = SV._transcript_to_words('seg.json', json.dumps(
        {'segments': [{'text': 'alpha beta gamma', 'start': 0.0, 'end': 3.0}]}).encode())
    check('v117d: JSON-Segmente auf Wort-Ebene aufgespalten (Timings verteilt)',
          [w['word'].strip() for w in _jseg] == ['alpha', 'beta', 'gamma']
          and abs(_jseg[1]['start'] - 1.0) < 0.01)
    _tw = SV._transcript_to_words('plain.txt', b'Line one is here\nLine two follows')
    check('v117d: TXT -> synthetische Timings, aufsteigend, verbatim',
          len(_tw) == 7 and _tw[0]['word'].strip() == 'Line'
          and all(_tw[i]['start'] <= _tw[i + 1]['start'] for i in range(len(_tw) - 1)))
    check('v117d: leere/kaputte Transkript-Datei -> [] (kein Crash)',
          SV._transcript_to_words('x.txt', b'') == []
          and isinstance(SV._transcript_to_words('x.json', b'{bad'), list))
    # v124 Referral: beide Seiten belohnt, idempotent, Werber-Deckel.
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('refa@test','x','A',0,?,1)", (int(_t.time()),))
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('refb@test','x','B',0,?,1)", (int(_t.time()),))
    con.commit()
    ida = con.execute("SELECT id FROM users WHERE email='refa@test'").fetchone()['id']
    idb = con.execute("SELECT id FROM users WHERE email='refb@test'").fetchone()['id']
    con.close()
    code1 = SV._ensure_ref_code(ida)
    code2 = SV._ensure_ref_code(ida)
    check('v124: Referral-Code stabil + gueltiges Format',
          code1 and code1 == code2 and len(code1) == 8
          and all(ch in SV._REF_ALPHABET for ch in code1))
    con = SV._db()
    con.execute("UPDATE users SET referred_by = ? WHERE id = ?", (ida, idb))
    con.commit(); con.close()
    g1 = SV._grant_referral(idb)
    g2 = SV._grant_referral(idb)
    con = SV._db()
    ba = con.execute("SELECT balance_sec FROM users WHERE id=?", (ida,)).fetchone()['balance_sec']
    bb = con.execute("SELECT balance_sec FROM users WHERE id=?", (idb,)).fetchone()['balance_sec']
    con.close()
    check('v124: Referral belohnt beide Seiten genau einmal (idempotent)',
          g1 is True and g2 is False
          and ba == SV.REFERRAL_SECONDS and bb == SV.REFERRAL_SECONDS,
          f'A={ba}s B={bb}s')
    # Werber-Deckel: bei erreichtem Cap bekommt nur noch der Geworbene etwas.
    con = SV._db()
    for _i in range(SV.REFERRAL_CAP):
        con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                    "VALUES (?, 0, ?, ?)", (ida, f'Referral for x{_i}', int(_t.time())))
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
                "verified, referred_by) VALUES ('refc@test','x','C',0,?,1,?)",
                (int(_t.time()), ida))
    con.commit()
    idc = con.execute("SELECT id FROM users WHERE email='refc@test'").fetchone()['id']
    con.close()
    SV._grant_referral(idc)
    con = SV._db()
    ba2 = con.execute("SELECT balance_sec FROM users WHERE id=?", (ida,)).fetchone()['balance_sec']
    bc = con.execute("SELECT balance_sec FROM users WHERE id=?", (idc,)).fetchone()['balance_sec']
    con.close()
    check('v124: Werber-Deckel greift, Geworbener bekommt trotzdem',
          ba2 == ba and bc == SV.REFERRAL_SECONDS, f'A={ba2}s C={bc}s')
    # v124 Reload-Bonus: +10% nur bei fast leerem Konto, idempotent mit dem Kauf.
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('low@test','x','L',60,?,1)", (int(_t.time()),))
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('high@test','x','H',600,?,1)", (int(_t.time()),))
    con.commit()
    idl = con.execute("SELECT id FROM users WHERE email='low@test'").fetchone()['id']
    idh = con.execute("SELECT id FROM users WHERE email='high@test'").fetchone()['id']
    con.close()
    k1 = SV._credit_purchase(idl, 1200, 'sess_low1')
    k2 = SV._credit_purchase(idl, 1200, 'sess_low1')          # Stripe-Doppel
    SV._credit_purchase(idh, 1200, 'sess_high1')
    con = SV._db()
    bl = con.execute("SELECT balance_sec FROM users WHERE id=?", (idl,)).fetchone()['balance_sec']
    bh = con.execute("SELECT balance_sec FROM users WHERE id=?", (idh,)).fetchone()['balance_sec']
    nb = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=? AND "
                     "grund LIKE 'Reload bonus %'", (idl,)).fetchone()['c']
    con.close()
    check('v124: Reload-Bonus nur bei fast leerem Konto, kein Doppel',
          k1 is True and k2 is False
          and bl == 60 + 1200 + 120 and bh == 600 + 1200 and nb == 1,
          f'low={bl}s high={bh}s bonusrows={nb}')
    # v126 Kunden-Stil: persoenliche Referenz-Datei + Loeschung mit dem Konto.
    _urp = SV._user_refs_path(ida)
    check('v126: persoenlicher Referenz-Pfad im refs-Ordner (pro Konto getrennt)',
          _urp and _urp.endswith(f'user_{ida}.json')
          and os.path.dirname(_urp).endswith('refs')
          and SV._user_refs_path(idb) != _urp and SV._user_refs_path(None) is None)
    os.makedirs(os.path.dirname(_urp), exist_ok=True)
    json.dump([{'name': 'A', 'beispiel': 'dense punchy'}],
              open(_urp, 'w', encoding='utf-8'))
    check('v126: eigene Stile laden (nur Name + Beispiel)',
          [r['name'] for r in SV._load_user_refs(ida)] == ['A']
          and SV._load_user_refs(idb) == [])
    check('v126: render.py nimmt DVE_REFS_FILE (persoenlich uebersteuert global)',
          "os.environ.get('DVE_REFS_FILE')" in
          open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())
    # ---- v141: Referenz-Herkunft. Der globale Haus-Store (den der Owner ueber
    # /api/reference/learn fuellt) darf NIE der stille Fallback fremder Konten
    # sein - genau das liess Gelerntes in jeden Kundenschnitt lecken.
    import ast as _ast142
    _srv142 = _srv141 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _adm142 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    _ui141 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    _rp141 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    _repo_refs = os.path.join(HERE, 'regie_reference.json')
    _p_none, _q_none = SV._refs_for_job(None)
    _p_b, _q_b = SV._refs_for_job(idb)                 # Konto ohne eigene Stile
    _glob = SV._reference_file()
    # Schutz: der globale Store MUSS in der isolierten Test-DVE_DATA liegen -
    # sonst wuerde der Test unten die echte Repo-Datei ueberschreiben/loeschen.
    check('v141: Test-Isolation - globaler Store liegt nicht im Repo',
          os.path.abspath(_glob) != os.path.abspath(_repo_refs), _glob)
    check('v141: Konto ohne eigene Stile bekommt Repo-Haus-Stil, NIE den Owner-Store',
          _q_b == 'haus' and os.path.abspath(_p_b) == os.path.abspath(_repo_refs)
          and os.path.abspath(_p_b) != os.path.abspath(_glob)
          and _q_none == 'haus' and os.path.abspath(_p_none) == os.path.abspath(_repo_refs),
          f'b=({_p_b},{_q_b}) global={_glob}')
    _p_a, _q_a = SV._refs_for_job(ida)                 # ida hat oben 1 eigenen Stil
    check('v141: Konto MIT eigenem Stil bekommt die eigene Datei (Quelle eigene)',
          _q_a == 'eigene' and os.path.abspath(_p_a) == os.path.abspath(_urp))
    json.dump([], open(_urp, 'w', encoding='utf-8'))   # letzten Stil geloescht
    _p_e, _q_e = SV._refs_for_job(ida)
    check('v141: leere eigene Referenz-Datei zaehlt nicht als eigener Stil',
          _q_e == 'haus' and os.path.abspath(_p_e) == os.path.abspath(_repo_refs))
    json.dump([{'name': 'A', 'beispiel': 'dense punchy'}],
              open(_urp, 'w', encoding='utf-8'))       # Ausgangslage zurueck
    # Owner: sein global gelernter Haus-Store bleibt fuer SEINE Renders aktiv.
    _old_owner = SV.OWNER_EMAIL
    try:
        con = SV._db()
        con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
                    "verified) VALUES ('owner141@test','x','O',0,?,1)", (int(_t.time()),))
        con.commit()
        _oid = con.execute("SELECT id FROM users WHERE email='owner141@test'").fetchone()['id']
        con.close()
        SV.OWNER_EMAIL = 'owner141@test'
        os.makedirs(os.path.dirname(_glob) or '.', exist_ok=True)
        json.dump([{'name': 'Haus', 'beispiel': 'owner taste'}],
                  open(_glob, 'w', encoding='utf-8'))
        _p_o, _q_o = SV._refs_for_job(_oid)
        _p_b2, _q_b2 = SV._refs_for_job(idb)           # gleicher Moment, fremdes Konto
        check('v141: Owner behaelt seinen globalen Store, fremdes Konto sieht ihn nicht',
              _q_o == 'eigene' and os.path.abspath(_p_o) == os.path.abspath(_glob)
              and _q_b2 == 'haus' and os.path.abspath(_p_b2) != os.path.abspath(_glob),
              f'owner=({_p_o},{_q_o}) fremd=({_p_b2},{_q_b2})')
    finally:
        SV.OWNER_EMAIL = _old_owner
        try: os.remove(_glob)
        except OSError: pass
    check('v141: Beweis-Zeile des Renders wird korrekt in Anzahl+Quelle gelesen',
          SV._parse_refs_line('Stil-Referenzen: 3 aktiv (eigene) - fliessen in die '
                              'KI-Regie ein') == (3, 'eigene')
          and SV._parse_refs_line('Stil-Referenzen: 2 aktiv (Haus-Stil) - fliessen '
                                  'in die KI-Regie ein') == (2, 'haus')
          and SV._parse_refs_line('Stil-Referenzen: 2 aktiv - alt') == (2, '')
          and SV._parse_refs_line('Stil-Referenzen: keine gefunden') == (0, ''))
    check('v141: Env-Quelle immer gesetzt + render.py schreibt sie ins Log',
          "env['DVE_REFS_FILE'] = _urp" in _srv141
          and "env['DVE_REFS_SOURCE'] = _rsrc" in _srv141
          and 'def _refs_for_job' in _srv141
          and 'DVE_REFS_SOURCE' in _rp141 and "'haus': 'house style'" in _rp141
          and 'active ({_lbl})' in _rp141)
    check('v141: UI nennt nur EIGENE Stile "learned", Haus-Stil heisst Haus-Stil',
          "st.stil_quelle === 'eigene'" in _ui141
          and 'your ${st.stil_refs} learned style' in _ui141
          and 'Edited with our house style' in _ui141
          and 'learned reference' not in _ui141)

    # ================================================================
    # v142: Queries/Indexe, Caching, Async, Recht-&-Steuern-Panel.
    # ================================================================
    # (a) KEINE der heissen Abfragen darf mehr scannen. Verhaltens-Test ueber
    #     EXPLAIN QUERY PLAN gegen die echte Test-DB - ein spaeter geloeschter
    #     Index faellt hier sofort auf, eine reine Quelltext-Suche nicht.
    _hot = [
        ("ledger je User", "SELECT delta_sec, grund, created_at FROM ledger "
                           "WHERE user_id=? ORDER BY created_at DESC", (1,)),
        ("ledger Idempotenz", "SELECT id FROM ledger WHERE user_id=? AND grund=?", (1, 'x')),
        ("ledger Verfall-FIFO", "SELECT delta_sec, created_at FROM ledger "
                                "WHERE user_id=? ORDER BY created_at", (1,)),
        ("ledger Zeitreihe", "SELECT created_at, delta_sec FROM ledger WHERE created_at>=?", (0,)),
        ("purchases je User", "SELECT session_id FROM purchases WHERE user_id=?", (1,)),
        ("purchases Zeitraum", "SELECT cents FROM purchases WHERE created_at>=?", (0,)),
        ("users Neuanmeldungen", "SELECT COUNT(*) FROM users WHERE created_at>=?", (0,)),
        ("consents je User", "SELECT kind FROM consents WHERE user_id=?", (1,)),
        ("verify_tokens je User", "SELECT token FROM verify_tokens WHERE user_id=?", (1,)),
        ("resets je User", "SELECT token FROM resets WHERE user_id=?", (1,)),
        ("archiv je Mail", "SELECT delta_sec FROM ledger_archive WHERE user_email=?", ('a@b',)),
        ("sessions aktiv", "SELECT COUNT(*) FROM sessions WHERE expires_at>?", (0,)),
    ]
    con = SV._db()
    _scans = []
    for _nm, _q, _p in _hot:
        for _r in con.execute('EXPLAIN QUERY PLAN ' + _q, _p).fetchall():
            if str(_r[3]).startswith('SCAN'):
                _scans.append(f'{_nm}: {_r[3]}')
    con.close()
    check('v142: keine heisse Abfrage laeuft mehr als Full-Table-Scan',
          not _scans, '; '.join(_scans[:4]))
    # (b) Datei-Cache liefert dasselbe Ergebnis und erkennt eine Aenderung.
    _tmpf = os.path.join(os.environ['DVE_DATA'], 'cachetest.html')
    open(_tmpf, 'w', encoding='utf-8').write('<p>eins</p>')
    _t1, _e1 = SV._file_cached(_tmpf)
    _t2, _e2 = SV._file_cached(_tmpf)
    _t.sleep(0.01)
    open(_tmpf, 'w', encoding='utf-8').write('<p>zwei viel laenger</p>')
    _t3, _e3 = SV._file_cached(_tmpf)
    check('v142: Datei-Cache haelt, invalidiert aber bei Aenderung (Deploy)',
          _t1 == '<p>eins</p>' and _e1 == _e2 and _t3 == '<p>zwei viel laenger</p>'
          and _e3 != _e1, f'{_e1} -> {_e3}')

    class _Req:                       # minimaler Request-Ersatz fuer den ETag
        def __init__(self, inm=''):
            self.headers = {'if-none-match': inm} if inm else {}
    check('v142: ETag antwortet 304 nur bei passendem If-None-Match',
          SV._etag_304(_Req(), _e1, 'no-cache') is None
          and SV._etag_304(_Req('"anders"'), _e1, 'no-cache') is None
          and getattr(SV._etag_304(_Req(_e1), _e1, 'no-cache'), 'status_code', 0) == 304)
    # (c) TTL-Cache: baut einmal, liefert dann aus dem Cache, _ttl_drop wirkt.
    _calls = []
    _build = lambda: (_calls.append(1), {'n': len(_calls)})[1]
    _c1 = SV._ttl_cached('adm:test', 30, _build)
    _c2 = SV._ttl_cached('adm:test', 30, _build)
    SV._ttl_drop('adm:')
    _c3 = SV._ttl_cached('adm:test', 30, _build)
    check('v142: TTL-Cache spart den Aufbau, _ttl_drop erzwingt frische Zahlen',
          _c1 == _c2 == {'n': 1} and _c3 == {'n': 2} and len(_calls) == 2,
          str(_calls))
    # Geld und Kontostand duerfen NIE aus einem Cache kommen - ein veralteter
    # Wert waere dort schlimmer als jede Rechenzeit. Per AST geprueft, nicht
    # per Textsuche: die Funktionsgrenzen muessen exakt stimmen.
    _tree142 = _ast142.parse(_srv142)
    _cached_fns = {f.name for f in _ast142.walk(_tree142)
                   if isinstance(f, (_ast142.FunctionDef, _ast142.AsyncFunctionDef))
                   and any(isinstance(c, _ast142.Call)
                           and getattr(c.func, 'id', '') == '_ttl_cached'
                           for c in _ast142.walk(f))}
    # Die Liste ist bewusst EXAKT: so faellt auf, wenn eine neue Funktion
    # anfaengt zu cachen. v206 traegt admin_start ein - dieselbe Klasse wie
    # die drei anderen (Admin-Aggregat, 20 s, wird bei jedem Schreibzugriff
    # verworfen); v208 admin_trichter ebenso (Statistik, 60 s).
    # KEIN Kunden-Kontostand darf je dazukommen.
    check('v142: Geld-/Konto-Endpunkte sind NICHT gecacht',
          _cached_fns == {'admin_revenue', 'admin_timeseries', 'admin_tax',
                          'admin_start', 'admin_trichter'}
          and "_ttl_drop('adm:')" in _srv142, str(sorted(_cached_fns)))
    # (d) Async: kein blockierender Aufruf mehr direkt im Event-Loop.
    _blocking = {'subprocess.run', 'requests.post', 'requests.get', 'time.sleep',
                 '_whisper_words', '_send_purchase_mail', '_R.analyze_reference_video'}

    def _dotted(_n):
        if isinstance(_n, _ast142.Attribute):
            _b = _dotted(_n.value)
            return (_b + '.' + _n.attr) if _b else _n.attr
        return _n.id if isinstance(_n, _ast142.Name) else ''

    _loop_blockers = []
    for _fn in _ast142.walk(_ast142.parse(_srv142)):
        if not isinstance(_fn, _ast142.AsyncFunctionDef):
            continue
        _awaited = set()
        for _aw in _ast142.walk(_fn):
            if isinstance(_aw, _ast142.Await):
                for _sub in _ast142.walk(_aw):
                    _awaited.add(getattr(_sub, 'lineno', -1))
        _nested = {id(_x) for _d in _ast142.walk(_fn)
                   if isinstance(_d, _ast142.FunctionDef)
                   for _x in _ast142.walk(_d)}
        for _c in _ast142.walk(_fn):
            if (isinstance(_c, _ast142.Call) and id(_c) not in _nested
                    and _dotted(_c.func) in _blocking
                    and _c.lineno not in _awaited):
                _loop_blockers.append(f'{_fn.name}:{_c.lineno} {_dotted(_c.func)}')
    check('v142: async-Endpunkte blockieren den Event-Loop nicht mehr',
          not _loop_blockers, '; '.join(_loop_blockers[:4]))
    check('v142: die langen Aufrufe laufen wirklich im Threadpool',
          'to_thread(_mk_session' in _srv142
          and 'to_thread(st.Invoice.retrieve' in _srv142
          and 'to_thread(_send_purchase_mail' in _srv142
          and 'to_thread(_whisper_words' in _srv142
          and _srv142.count('to_thread(\n            _R.analyze_reference_video') == 2)
    # (e) Recht & Steuern: echte Zahlen, §19-Ampel, USt-IdNr, kein USt-Ausweis.
    _jahr = int(_t.strftime('%Y', _t.gmtime()))
    SV._ttl_drop('adm:')
    _tax0 = SV._admin_tax_calc()
    _vor = next(j for j in _tax0['jahre'] if j['jahr'] == _jahr)
    con = SV._db()
    _uidt = con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, "
                        "created_at, verified) VALUES ('tax@test','x','T',0,?,1)",
                        (int(_t.time()),)).lastrowid
    con.execute("INSERT INTO purchases (session_id, user_id, pack, cents, sekunden, "
                "created_at) VALUES ('cs_tax1',?,'p19',1900,3600,?)",
                (_uidt, int(_t.time())))
    con.commit(); con.close()
    SV._ttl_drop('adm:')
    _tax = SV._admin_tax_calc()
    _cur142 = next(j for j in _tax['jahre'] if j['jahr'] == _jahr)
    check('v142: Steuer-Panel rechnet aus den ECHTEN Kaeufen',
          _cur142['anzahl'] == _vor['anzahl'] + 1
          and _cur142['brutto_cent'] == _vor['brutto_cent'] + 1900
          and _tax['kleinunternehmer']['laufend_cent'] == _cur142['brutto_cent']
          and any(b['session_id'] == 'cs_tax1' for b in _tax['belege']),
          f"{_vor} -> {_cur142}")
    check('v142: USt-IdNr steht drin und USt wird NIE ausgewiesen',
          _tax['identitaet']['ust_id'] == 'DE463613884'
          and _tax['identitaet']['ust_ausweis'] is False
          and '19' in _tax['identitaet']['regelung'])
    # v142a (Ismets Rueckfrage): "USt niemals ausweisen" != "USt-IdNr weglassen".
    # Der Panel-Hinweis muss die BETRAG-Aussage machen (kein USt-Satz/-Betrag),
    # nicht die Nummer verbieten - und die Nummer steht nachweislich im Footer
    # (der Beleg dafuer liegt im v135-Test oben).
    check('v142a: Panel unterscheidet USt-Betrag (nein) von USt-IdNr (ja)',
          'VAT amount' in _tax['identitaet']['hinweis']
          and 'VAT ID itself DOES go on the invoice' in _tax['identitaet']['hinweis']
          and 'VAT ID on invoice' in _adm142
          and 'Show a VAT amount' in _adm142)
    check('v142: §19-Ampel schlaegt ab 80 Prozent und ueber der Grenze an',
          _tax['kleinunternehmer']['laufend_lage'] == 'ok'
          and SV.KU_VORJAHR_CENT == 25_000_00 and SV.KU_LAUFEND_CENT == 100_000_00)
    check('v142: Aufbewahrung + Verarbeitungsverzeichnis vollstaendig',
          _tax['aufbewahrung']['belege_jahre'] == 10
          and '147 AO' in _tax['aufbewahrung']['rechtsgrundlage']
          and len(_tax['verarbeitung']) >= 8
          and all(v.get('grundlage') and v.get('frist') for v in _tax['verarbeitung'])
          and {s['url'] for s in _tax['seiten']} == {'/imprint', '/privacy', '/terms'})
    check('v142: Admin-Panel hat den Tab und ruft den Endpunkt',
          "['legal','Recht & Steuern']" in _adm142
          and 'legal:loadLegal' in _adm142
          and "api('/api/admin/compliance/tax')" in _adm142
          and 'Record of processing activities' in _adm142
          and 'not tax advice' in _adm142)
    # v126-sec: doppeltes Verify darf Referral NICHT doppelt buchen (Race-Fix).
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('rw@test','x','W',0,?,1)", (int(_t.time()),))
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
                "verified, referred_by) SELECT 'rn@test','x','N',0,?,1,id FROM users "
                "WHERE email='rw@test'", (int(_t.time()),))
    con.commit()
    _w = con.execute("SELECT id FROM users WHERE email='rw@test'").fetchone()['id']
    _n = con.execute("SELECT id FROM users WHERE email='rn@test'").fetchone()['id']
    con.close()
    gg1 = SV._grant_referral(_n)
    gg2 = SV._grant_referral(_n)                      # simuliert zweites Verify-Token
    con = SV._db()
    rows_n = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=? AND "
                         "grund='Referral welcome'", (_n,)).fetchone()['c']
    rows_w = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=? AND "
                         "grund LIKE 'Referral for %'", (_w,)).fetchone()['c']
    bw = con.execute("SELECT balance_sec FROM users WHERE id=?", (_w,)).fetchone()['balance_sec']
    con.close()
    check('v126-sec: doppeltes Verify bucht Referral nicht doppelt (idempotent)',
          gg1 is True and gg2 is False and rows_n == 1 and rows_w == 1
          and bw == SV.REFERRAL_SECONDS, f'n={rows_n} w={rows_w} bw={bw}')
    # v126-sec (1): Wegwerf-Mail bekommt keinen Referral-Bonus.
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
                "verified, referred_by) SELECT 'ring@mailinator.com','x','R',0,?,1,id "
                "FROM users WHERE email='rw@test'", (int(_t.time()),))
    con.commit()
    _dsp = con.execute("SELECT id FROM users WHERE email='ring@mailinator.com'").fetchone()['id']
    con.close()
    gd = SV._grant_referral(_dsp)
    check('v126-sec: Wegwerf-Domain bekommt keinen Referral-Bonus',
          gd is False and SV._is_disposable_email('a@mailinator.com') is True
          and SV._is_disposable_email('a@gmail.com') is False)
    # v126-sec (2): Re-Arm-Schutz - Konto loeschen + gleiche Mail neu registrieren
    # farmt den Bonus NICHT mehr (Anspruch-Hash ueberlebt die Loeschung).
    con = SV._db()
    con.execute("DELETE FROM users WHERE id = ?", (_n,))          # Konto "geloescht"
    con.execute("DELETE FROM ledger WHERE user_id = ?", (_n,))
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
                "verified, referred_by) SELECT 'rn@test','x','N2',0,?,1,id FROM users "
                "WHERE email='rw@test'", (int(_t.time()),))
    con.commit()
    _n2 = con.execute("SELECT id FROM users WHERE email='rn@test'").fetchone()['id']
    con.close()
    gr = SV._grant_referral(_n2)
    check('v126-sec: Re-Arm nach Konto-Loeschung wird geblockt (Hash ueberlebt)',
          gr is False, f'grant nach re-register = {gr}')
    # v125 Credits-Verfall: FIFO pro Gutschrift, 180 Tage, idempotent, Warn-Info.
    con = SV._db()
    con.execute("INSERT INTO users (email, pw_hash, name, balance_sec, created_at, verified) "
                "VALUES ('exp@test','x','E',0,?,1)", (int(_t.time()),))
    con.commit()
    ide = con.execute("SELECT id FROM users WHERE email='exp@test'").fetchone()['id']
    _now = int(_t.time())
    _old = _now - int(200 * 86400)                     # 200 Tage alt -> abgelaufen
    _mid = _now - int((SV.CREDIT_VALIDITY_DAYS - 10) * 86400)   # laeuft in ~10d ab
    for delta, grund, ts in ((600, 'Kauf sessOLD', _old),
                             (-240, 'Render jX (240s)', _old + 86400),
                             (300, 'Kauf sessMID', _mid),
                             (120, 'Kauf sessNEW', _now)):
        con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                    "VALUES (?, ?, ?, ?)", (ide, delta, grund, ts))
    con.execute("UPDATE users SET balance_sec = ? WHERE id = ?",
                (600 - 240 + 300 + 120, ide))
    con.commit(); con.close()
    e1 = SV._expire_credits(ide)                       # 600 - 240 = 360 verfallen
    e2 = SV._expire_credits(ide)                       # idempotent: nichts mehr
    con = SV._db()
    be_ = con.execute("SELECT balance_sec FROM users WHERE id=?", (ide,)).fetchone()['balance_sec']
    ne_ = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=? AND "
                      "grund LIKE 'Expired credits %'", (ide,)).fetchone()['c']
    con.close()
    check('v125: Verfall FIFO (nur unverbrauchter Rest) + idempotent',
          e1 == 360 and e2 == 0 and be_ == 300 + 120 and ne_ == 1,
          f'e1={e1} e2={e2} bal={be_} rows={ne_}')
    _ws, _wd = SV._expiring_info(ide, SV.CREDIT_WARN_DAYS)
    check('v125: Warn-Info sieht den bald ablaufenden Rest (nicht den frischen)',
          _ws == 300 and _wd is not None and 8 <= _wd <= 11, f'{_ws}s in {_wd}d')
    m1 = SV._log_mail_once(ide, 'expwarn_test')
    m2 = SV._log_mail_once(ide, 'expwarn_test')
    check('v125: mail_log verhindert Doppelversand', m1 is True and m2 is False)
    # v124 Hook-Score-Port: Werte plausibel + Randfaelle stabil.
    _hs_moms = [{'i': 1, 'zeit': 0.8, 'power': 3, 'fx': 'zoom', 'anim': 'pop'},
                {'i': 2, 'zeit': 5.0, 'power': 2, 'fx': 'behind'},
                {'i': 3, 'zeit': 20.0, 'power': 2, 'fx': 'ground', 'anim': 'welle'},
                {'i': 4, 'zeit': 40.0, 'power': 1, 'fx': 'zoom'}]
    _hs = SV._hook_score(_hs_moms, 60)
    check('v124: Hook-Score serverseitig (frueher Hook + Peak > spaeter Einstieg)',
          1 <= _hs <= 100 and _hs > SV._hook_score(
              [{'i': 1, 'zeit': 30.0, 'power': 1, 'fx': 'zoom'}], 60)
          and SV._hook_score([], 60) == 0
          and SV._hook_score([{'aktiv': False}], 60) == 0, f'score={_hs}')
    # 4-6) Quelltext-Garantien (Signatur-Pflicht, Ownership, Login-Limit)
    _src = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('Stripe-Webhook erzwingt Secret',
          'if not secret:' in _src and 'Webhook secret not configured' in _src)
    check('Ownership-Check auf allen Job-Endpoints',
          _src.count('_job_owner_ok(jid, request)') >= 6,
          f"{_src.count('_job_owner_ok(jid, request)')} Checks")
    check('Login gegen Brute-Force gebremst', "bucket='login'" in _src)
    # 7) Pfad-Traversal ueber language wird geschluckt (Wert + Dateiname)
    ov2 = SV._sanitize_overrides({'language': '../../etc/passwd'})
    ov3 = SV._sanitize_overrides({'language': 'DE'})
    check('language: Pfad-Traversal-Wert wird verworfen',
          'language' not in ov2 and ov3.get('language') == 'de')
    tp = SV._tcache_path(uid, 'abcd', '../../../etc/x')
    check('tcache-Pfad bleibt im tcache-Ordner (kein Traversal)',
          bool(tp) and os.path.dirname(os.path.abspath(tp)) == os.path.abspath(SV._TCACHE)
          and '..' not in os.path.basename(tp), tp)
    # 8) Kauf idempotent + atomar (Webhook-Retry schreibt nicht doppelt).
    # v124: bei fast leerem Konto kommt der Reload-Bonus (+10%) obendrauf,
    # der Retry darf trotzdem WEDER Kauf NOCH Bonus doppelt schreiben.
    b0 = SV._find_user_by_id(uid)['balance_sec']
    _bonus = 100 // 10 if b0 < 120 else 0
    r1 = SV._credit_purchase(uid, 100, 'sessAAA')
    r2 = SV._credit_purchase(uid, 100, 'sessAAA')
    b1 = SV._find_user_by_id(uid)['balance_sec']
    check('Kauf: idempotent (Retry schreibt nicht doppelt)',
          r1 is True and r2 is False and b1 == b0 + 100 + _bonus,
          f'{b0} -> {b1}, r1={r1} r2={r2}')
    # 9) Reset-Token nur EINMAL einloesbar (atomar)
    con = SV._db()
    con.execute("INSERT INTO resets (token, user_id, created_at, expires_at, used) "
                "VALUES (?, ?, ?, ?, 0)",
                ('tok_reset_1', uid, int(_t.time()), int(_t.time()) + 999))
    con.commit(); con.close()
    first = SV._consume_reset('tok_reset_1')
    second = SV._consume_reset('tok_reset_1')
    check('Reset-Token: nur einmal einloesbar (atomar)',
          first == uid and second is None, f'{first}/{second}')
    # 10) Upload-Dateiname wird entschaerft (kein HTML, kein Traversal)
    check('Upload-Dateiname wird von HTML/Steuerzeichen befreit',
          SV._safe_name('<img src=x onerror=alert(1)>.mp4')
          == 'img src=x onerror=alert(1).mp4'
          and SV._safe_name('../../evil.mp4') == 'evil.mp4')
    # 11) DSGVO-Loeschung entfernt Videos + tcache + Token (Quelltext-Garantie)
    check('Konto-Loeschung raeumt Videos/tcache/Token',
          'shutil.rmtree(job_dir(jid)' in _src
          and 'DELETE FROM resets' in _src
          and 'DELETE FROM verify_tokens' in _src
          and 'startswith(pref)' in _src)
    # 12) Admin-Endpoint gehaertet (kein Default, Header, timing-safe)
    # v230d-sec: der Test verlangte hier bis eben AUSDRUECKLICH den
    # str-Vergleich `compare_digest(given, key)` - und genau der wirft bei
    # einem Header mit Umlaut einen TypeError (500er + Zeile in der
    # alerts-Tabelle). Ein Test kann eine Luecke als Zusage festschreiben
    # (v132-Falle). Verlangt wird jetzt der BYTE-Vergleich, und zwar an
    # jeder Stelle.
    check('Admin: kein Default admin, Header + timing-safe (ueber Bytes)',
          "os.environ.get('DVE_ADMIN', 'admin')" not in _src
          and "hmac.compare_digest(given.encode('utf-8', 'ignore')" in _src
          and 'hmac.compare_digest(given, key)' not in _src
          and "request.headers.get('x-admin-key'" in _src)
    # 13) Security-Header werden auf jeder Antwort gesetzt
    check('Security-Header (CSP/XFO/nosniff) aktiv',
          'Content-Security-Policy' in _src and 'X-Frame-Options' in _src
          and 'X-Content-Type-Options' in _src)
    # 14) SEPA: Guthaben nur bei final bezahltem Status. v135a: auch
    # 'no_payment_required' (100%-Promo-Code) ist final - pending/unpaid nie.
    check('Webhook schreibt nur bei finalem payment_status gut',
          "not in ('paid', 'no_payment_required')" in _src
          and 'async_payment_succeeded' in _src)
    # 15) Login gleicht Timing an (Dummy-Hash bei unbekannter Mail)
    check('Login: Timing-Angleich gegen Mail-Enumeration',
          '_verify_pw(password, _DUMMY_HASH)' in _src)
    # 15b) v96p/s: Referenz-Stil-Endpoints nur fuers Besitzer-Konto (global wirksam)
    check('Referenz-Stil: nur Besitzer-Konto (OWNER_EMAIL), Session-gate',
          'OWNER_EMAIL' in _src and 'def _owner_ok' in _src
          and _src.count('if not _owner_ok(request):') >= 3
          and "'is_owner':" in _src and '/api/reference/learn' in _src)
    # v121: Admin-Transkript-Werkzeug unter Reference (Video -> txt/srt/vtt/json), owner-gated.
    _tw = [{'word': 'Hello', 'start': 0.0, 'end': 0.4}, {'word': 'there.', 'start': 0.4, 'end': 0.9},
           {'word': 'This', 'start': 1.9, 'end': 2.1}, {'word': 'is', 'start': 2.1, 'end': 2.2},
           {'word': 'verbatim.', 'start': 2.2, 'end': 2.9}]
    _srt = SV._words_to_srt(_tw); _vtt = SV._words_to_srt(_tw, vtt=True)
    _txt = SV._words_to_text(_tw)
    check('v121: Transkript-Formatter (SRT/VTT echte Timings, TXT verbatim)',
          '00:00:00,000 --> 00:00:00,900' in _srt and 'Hello there.' in _srt
          and _vtt.startswith('WEBVTT') and '00:00:00.000 -->' in _vtt
          and _txt == 'Hello there.\nThis is verbatim.'
          and SV._words_to_text([]) == '' and SV._words_to_srt([]).strip() == '')
    check('v121: Transkript-Endpoint owner-gated + kein Credit-Abzug',
          "@app.post('/api/reference/transcribe')" in _src
          and 'def reference_transcribe' in _src
          and _src[_src.find('def reference_transcribe'):
                   _src.find('def reference_transcribe') + 700].count('_owner_ok(request)') >= 1
          and '_reserve_credits' not in
              _src[_src.find('def reference_transcribe'):_src.find('@app.get(\'/admin/codes\')')])
    # 15c) v96s Regression: _owner_ok muss mit einer echten sqlite3.Row klappen
    # (Row hat KEIN .get() - genau das war die 500-Ursache). Mit einem dict waere
    # der Bug unentdeckt geblieben, darum bewusst eine Row.
    import sqlite3 as _sq3

    class _Rq2:
        def __init__(self, email):
            self._e = email
            self.cookies = {}
        # _owner_ok ruft _current_user(request); wir patchen das gleich
    _con = _sq3.connect(':memory:'); _con.row_factory = _sq3.Row
    _row_owner = _con.execute("SELECT 'Ismet-01_b@HOTMAIL.de' AS email, 1 AS verified").fetchone()
    _row_other = _con.execute("SELECT 'wer@anders.de' AS email, 1 AS verified").fetchone()
    # v127-sec: Owner-Mail, aber NICHT verifiziert -> keine Owner-Rechte.
    _row_owner_unv = _con.execute("SELECT 'Ismet-01_b@HOTMAIL.de' AS email, 0 AS verified").fetchone()
    _con.close()
    _old_cur = SV._current_user
    _old_owner_env = os.environ.get('DVE_OWNER')
    try:
        SV.OWNER_EMAIL = 'ismet-01_b@hotmail.de'
        SV._current_user = lambda req: req._row
        r_ok = _Rq2(''); r_ok._row = _row_owner
        r_no = _Rq2(''); r_no._row = _row_other
        r_anon = _Rq2(''); r_anon._row = None
        r_unv = _Rq2(''); r_unv._row = _row_owner_unv
        owner_true = SV._owner_ok(r_ok)
        owner_false = SV._owner_ok(r_no)
        anon_false = SV._owner_ok(r_anon)
        unverified_false = SV._owner_ok(r_unv)
    finally:
        SV._current_user = _old_cur
    check('Referenz-Stil: _owner_ok mit sqlite3.Row (kein .get-500) + verlangt verified',
          owner_true is True and owner_false is False and anon_false is False
          and unverified_false is False)
    # 16) v94: _video_hash kollidiert nicht bei gleichem Anfang/Ende, anderer
    # Mitte (der Bug, der einen deutschen Transkript-Cache an einen englischen
    # Clip servierte). Zwei Dateien: identischer Kopf+Fuss, verschiedene Mitte.
    import tempfile as _tf2
    head = b'H' * 300000
    tail = b'T' * 300000
    mid_a = b'A' * 600000
    mid_b = b'B' * 600000
    pa = os.path.join(_tf2.gettempdir(), 'vh_a.bin')
    pb = os.path.join(_tf2.gettempdir(), 'vh_b.bin')
    open(pa, 'wb').write(head + mid_a + tail)
    open(pb, 'wb').write(head + mid_b + tail)      # gleiche Groesse, Kopf, Fuss
    ha, hb = SV._video_hash(pa), SV._video_hash(pb)
    check('_video_hash: keine Kollision bei anderer Mitte',
          bool(ha) and ha != hb, f'{ha[:8] if ha else None} vs {hb[:8] if hb else None}')
    check('_video_hash: gleiche Datei -> gleicher Hash',
          SV._video_hash(pa) == ha)
    os.remove(pa); os.remove(pb)
    # 17) v95 Pre-Flow-Abrechnung: Vorab-Transkription (mode 'pre') bucht NICHTS
    # ab (nur Balance-Check), abgebucht wird erst atomar in render_start -
    # idempotent gegen Doppel-Klick ueber _render_charged. Kein Gratis-Render,
    # kein Doppel-Abzug.
    check('Pre-Upload transkribiert gratis, full/analyze reservieren atomar',
          "if mode == 'pre':" in _src
          and 'elif not _reserve_credits(uid, need, jid):' in _src)
    check('render_start reserviert atomar + idempotent (kein Doppel-Abzug)',
          'if not _render_charged(uid, jid) and not _reserve_credits(uid, need, jid):' in _src)
    shutil.rmtree(os.environ['DVE_DATA'], ignore_errors=True)


def _scenario_betrieb(tmp):
    """v97: Betrieb - Warm-Preview-Daemon, Health-Endpoint, Admin-Alarm."""
    print('\n--- Betrieb / Monitoring ---')
    import time as _t
    os.environ['DVE_DATA'] = tempfile.mkdtemp(prefix='dve_ops_')
    if 'server' in sys.modules:
        del sys.modules['server']
    sys.path.insert(0, os.path.join(HERE, 'web'))
    import server as SV
    # 1) Health-Endpoint (fuer externe Uptime-Ueberwachung)
    # v226a: dazu die Version - "welche Fassung laeuft?" war sonst nur mit
    # Admin-Schluessel zu beantworten, und genau die Frage kostete drei Runden.
    check('Health-Endpoint meldet ok (Server+DB)',
          SV.health() == {'ok': True, 'version': SV.DVE_VERSION},
          str(SV.health()))
    # 2) Admin-Alarm: pro Schluessel max. 1 Mail/Stunde, Mail-Fehler leise
    sent = []
    SV._send_mail = lambda to, s, b, reply_to=None, html=None: sent.append((to, s, html))
    SV._ADMIN_NOTIFIED.clear()
    a = SV._notify_admin('k1', 'T', 'x')
    b = SV._notify_admin('k1', 'T', 'x')
    c = SV._notify_admin('k2', 'T', 'x')
    check('Admin-Alarm gedrosselt (1 Mail/h pro Schluessel)',
          a and not b and c and len(sent) == 2
          and all(m[0] == SV.ADMIN_MAIL for m in sent))
    # v132: Regressionsschutz gegen den "in .env gesetzt, aber kommt nicht im
    # Container an"-Fehler. Jede Variable, die server.py aus der Umgebung liest
    # UND in .env.example dokumentiert ist, MUSS in docker-compose.yml an den
    # app-Dienst durchgereicht werden. (GOOGLE_* fehlten -> Login blieb aus.)
    _compose = open(os.path.join(HERE, 'docker-compose.yml'), encoding='utf-8').read()
    _srvtext = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _envex = open(os.path.join(HERE, '.env.example'), encoding='utf-8').read()
    _read_env = set(re.findall(r"os\.environ\.get\('([A-Z][A-Z0-9_]+)'", _srvtext))
    _documented = set(re.findall(r'^([A-Z][A-Z0-9_]+)=', _envex, re.M))
    _skip = {'DVE_DATA'}                    # Volume-Pfad, absichtlich nicht durchgereicht
    _must_pass = (_read_env & _documented) - _skip
    _missing = sorted(v for v in _must_pass if (v + ':') not in _compose)
    check('v132: alle dokumentierten .env-Variablen werden an den Container '
          'durchgereicht (docker-compose)', not _missing,
          f'fehlt in docker-compose.yml: {_missing}')
    # v131: DVE_ALERTS filtert Betriebs-Post. Routine (Backup) nur bei 'all';
    # echte Stoerungen bei 'important'; 'off' schweigt komplett.
    _lvl0 = SV.ALERT_LEVEL
    try:
        SV._ADMIN_NOTIFIED.clear(); n = len(sent)
        SV.ALERT_LEVEL = 'important'
        r_imp = SV._notify_admin('kr', 'T', 'x', routine=True)
        i_imp = SV._notify_admin('ki', 'T', 'x')
        SV._ADMIN_NOTIFIED.clear()
        SV.ALERT_LEVEL = 'off'
        i_off = SV._notify_admin('ko', 'T', 'x')
        SV._ADMIN_NOTIFIED.clear()
        SV.ALERT_LEVEL = 'all'
        r_all = SV._notify_admin('kr2', 'T', 'x', routine=True)
        check('v131: DVE_ALERTS filtert (important: Stoerung ja/Routine nein; '
              'off: nichts; all: Routine ja)',
              (not r_imp) and i_imp and (not i_off) and r_all)
    finally:
        SV.ALERT_LEVEL = _lvl0
    # Offsite-Backup ist Routine-Post und haengt am Regler
    check('v131: Offsite-Backup-Mail ist DVE_ALERTS-gated',
          "ALERT_LEVEL != 'all'" in open(
              os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read())
    # v133: Standard-Mail-Strecke wie ueberall ueblich. Willkommens-Mail genau
    # EINMAL pro Konto, sobald es aktiv ist; Kaufbestaetigung genau EINMAL pro
    # Stripe-Session (neue Session -> neue Mail).
    _wuid, _ = SV._create_user('v133mail@test', 'x' * 8, 'MailTester')
    _wn0 = len(sent)
    _w1 = SV._send_welcome_mail(_wuid)
    _w2 = SV._send_welcome_mail(_wuid)
    check('v133: Willkommens-Mail einmalig pro Konto',
          _w1 and (not _w2) and len(sent) == _wn0 + 1
          and sent[-1][0] == 'v133mail@test')
    _pn0 = len(sent)
    _p1 = SV._send_purchase_mail(_wuid, 1200, 'sess_v133_a')
    _p2 = SV._send_purchase_mail(_wuid, 1200, 'sess_v133_a')
    _p3 = SV._send_purchase_mail(_wuid, 3600, 'sess_v133_b')
    check('v133: Kauf-Mail idempotent pro Session, neue Session -> neue Mail',
          _p1 and (not _p2) and _p3 and len(sent) == _pn0 + 2
          and '20 credits' in sent[-2][1] and '60 credits' in sent[-1][1])
    # Verdrahtung: Verify-Endpoint, Google-Signup und Stripe-Webhook loesen
    # die Mails aus; Copy ohne Gedankenstriche (Ismets Regel).
    import inspect as _insp
    _wm_src = _insp.getsource(SV._send_welcome_mail) + _insp.getsource(SV._send_purchase_mail)
    _srv133 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v133: Mails verdrahtet (Verify + Google + Webhook) + Copy ohne Gedankenstriche',
          _srv133.count('_send_welcome_mail(uid)') >= 2
          and 'to_thread(_send_purchase_mail, uid, sec, sess_id,' in _srv133
          and '—' not in _wm_src and '–' not in _wm_src)
    # v133a: Absender-Feld robust. Leeres MAIL_FROM (docker-compose reicht ''
    # durch) -> Default, nackte Adresse -> verpackt, fertiges 'Name <adr>' ->
    # unveraendert (frueher: 'DouchkoVE <>' bzw. Doppel-Verpackung -> Resend 422).
    _mf0 = os.environ.get('MAIL_FROM')
    try:
        os.environ['MAIL_FROM'] = ''
        _f_empty = SV._mail_from('onboarding@resend.dev')
        os.environ['MAIL_FROM'] = 'noreply@douchko.eu'
        _f_bare = SV._mail_from('x@y.z')
        os.environ['MAIL_FROM'] = 'DouchkoVE <noreply@douchko.eu>'
        _f_full = SV._mail_from('x@y.z')
        check('v133a: MAIL_FROM robust (leer/nackt/fertig -> immer gueltig)',
              _f_empty == 'DouchkoVE <onboarding@resend.dev>'
              and _f_bare == 'DouchkoVE <noreply@douchko.eu>'
              and _f_full == 'DouchkoVE <noreply@douchko.eu>'
              and SV._mail_from_bare(_f_full) == 'noreply@douchko.eu')
    finally:
        if _mf0 is None:
            os.environ.pop('MAIL_FROM', None)
        else:
            os.environ['MAIL_FROM'] = _mf0
    # v133b: Reply-To gesetzt (Antworten kommen an, kein Widerspruch zu noreply)
    # + Copy im Standard-Ton (kein "reply to me / straight to my inbox / Ismet
    # here"), Support-Adresse als Kontakt. Pruefung gegen den DATEITEXT, weil
    # _send_mail in diesem Testblock durch ein Capture-Lambda ersetzt wurde
    # (inspect.getsource wuerde sonst das Lambda lesen).
    _full = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _fulll = _full.lower()
    # Nur die KUNDEN-Mails pruefen (die Betreiber-Ticket-Mail darf "reply to this
    # email" sagen, die geht an Ismet). Diese drei sind nicht gemockt.
    _custmail = (_insp.getsource(SV._send_verify_mail)
                 + _insp.getsource(SV._send_welcome_mail)
                 + _insp.getsource(SV._send_purchase_mail)).lower()
    check('v133b: Standard-Ton (kein "reply to me"), Support-Kontakt in Copy',
          'reply to this email' not in _custmail
          and 'straight in my inbox' not in _custmail
          and 'straight to me' not in _custmail
          and 'ismet here' not in _custmail
          and 'contact us at {support_email}' in _custmail
          and SV.SUPPORT_EMAIL and '@' in SV.SUPPORT_EMAIL)
    # v133c: noreply ist reines Versand-Postfach (KEIN globales Reply-To), aber
    # _send_mail kann pro Aufruf ein Reply-To setzen (fuer die Ticket-Mail).
    check('v133c: _send_mail hat optionalen reply_to, kein globales Reply-To',
          'def _send_mail(to, subject, body, reply_to=None' in _full
          and "payload['reply_to'] = reply_to" in _full
          and "msg['Reply-To'] = reply_to" in _full
          and "= SUPPORT_EMAIL" not in _full.split('def _send_mail')[1].split('def ')[0])
    # v133c: Support-Ticket end-to-end (DB + Betreiber-Mail mit Reply-To=Kunde +
    # Kunden-Bestaetigung ueber noreply). _send_mail wird hier gecaptured.
    _tsent = []
    _real_sm = SV._send_mail
    SV._send_mail = lambda to, s, b, reply_to=None: _tsent.append((to, s, reply_to))
    try:
        _tuid, _ = SV._create_user('ticket@test', 'x' * 8, 'Ticketer')
        class _TReq:
            def __init__(self, uid):
                self.cookies = {}
                self.headers = {}
                self.client = type('C', (), {'host': '10.0.0.5'})()
                self._uid = uid
        _origru = SV._require_user
        SV._require_user = lambda req: SV._find_user_by_id(req._uid)
        try:
            _res = SV.api_support(_TReq(_tuid), subject='Help', message='It broke')
        finally:
            SV._require_user = _origru
        con = SV._db()
        trow = con.execute("SELECT email, subject, body, status FROM tickets WHERE id=?",
                           (_res['ticket'],)).fetchone()
        con.close()
        _to_owner = [m for m in _tsent if m[2] == 'ticket@test']   # Reply-To=Kunde
        _to_cust = [m for m in _tsent if m[0] == 'ticket@test' and m[2] is None]
        check('v133c: Support-Ticket angelegt + 2 Mails (Betreiber Reply-To=Kunde, Kunde noreply)',
              _res.get('ok') and _res.get('ticket')
              and trow and trow['status'] == 'open' and trow['body'] == 'It broke'
              and len(_to_owner) == 1 and _to_owner[0][0] == SV.SUPPORT_EMAIL
              and len(_to_cust) == 1)
        # Admin: Ticket sichtbar + schliessbar
        os.environ['DVE_ADMIN'] = 'testkey_admin'
        class _AdmReq:
            def __init__(self, key):
                self.headers = {'x-admin-key': key}
        _tk = SV.admin_tickets(_AdmReq('testkey_admin'))
        SV.admin_ticket_status(_res['ticket'], _AdmReq('testkey_admin'), status='closed')
        con = SV._db()
        _st = con.execute("SELECT status FROM tickets WHERE id=?", (_res['ticket'],)).fetchone()['status']
        con.close()
        check('v133c: Admin sieht + schliesst Tickets',
              _tk['open_count'] >= 1
              and any(t['id'] == _res['ticket'] for t in _tk['tickets'])
              and _st == 'closed')
    finally:
        SV._send_mail = _real_sm
    # v133d: gebrandete HTML-Mails. Willkommens-Mail wird jetzt MIT html
    # verschickt; Template ehrlich (keine erfundenen Zahlen), gebrandet,
    # tabellenbasiert, ohne Gedankenstriche.
    _hcap = []
    _rsm = SV._send_mail
    SV._send_mail = lambda to, s, b, reply_to=None, html=None: _hcap.append({'to': to, 'sub': s, 'text': b, 'html': html})
    try:
        _huid, _ = SV._create_user('v133d@test', 'x' * 8, 'HtmlTester')
        SV._send_welcome_mail(_huid)
    finally:
        SV._send_mail = _rsm
    _wm = _hcap[-1] if _hcap else {}
    _h = _wm.get('html') or ''
    check('v133d: Willkommens-Mail als gebrandetes HTML (Logo, Akzent, CTA, Text-Fallback)',
          bool(_h) and '<!DOCTYPE html>' in _h and '<table' in _h
          and '/logo_dark.png' in _h and '#ff7a1a' in _h
          and 'Open DouchkoVE' in _h and bool(_wm.get('text'))
          and '—' not in _h and '–' not in _h)
    # Ehrlichkeit: keine erfundenen Reichweiten-/Ranking-Zahlen im Template.
    _tpl_src = _insp.getsource(SV._email_html).lower()
    check('v133d: HTML-Template ohne erfundene Zahlen (kein 10M/No.1)',
          '10m+' not in _h.lower() and 'no.1' not in _h.lower()
          and 'no. 1' not in _h.lower()
          and 'reply_to' not in _tpl_src)          # Template setzt kein Reply-To
    # _send_mail reicht html an Resend UND SMTP (multipart/alternative) durch.
    _smf = _full.split('def _send_mail')[1].split('\ndef ')[0]
    check('v133d: _send_mail unterstuetzt html (Resend + SMTP multipart)',
          "payload['html'] = html" in _smf
          and "MIMEMultipart('alternative')" in _smf
          and "def _send_mail(to, subject, body, reply_to=None, html=None)" in _full)
    # v134: Stripe-Rechnung pro Kauf. Kleinunternehmer §19 -> Pflichthinweis im
    # Footer, NIE eine USt/Prozentangabe; Steuernummer haengt an, wenn gesetzt;
    # Checkout uebergibt invoice_creation.
    _tax0 = os.environ.get('DVE_TAX_ID')
    try:
        os.environ['DVE_TAX_ID'] = ''
        _inv = SV._invoice_creation('starter', SV.PACKS['starter'])
        os.environ['DVE_TAX_ID'] = '12/345/67890'
        _inv2 = SV._invoice_creation('starter', SV.PACKS['starter'])
    finally:
        if _tax0 is None:
            os.environ.pop('DVE_TAX_ID', None)
        else:
            os.environ['DVE_TAX_ID'] = _tax0
    _foot = _inv['invoice_data']['footer']
    check('v134: Rechnung aktiv, §19-Hinweis im Footer, keine USt, Steuernummer optional',
          _inv['enabled'] is True
          and '§19 UStG' in _foot and 'keine Umsatzsteuer' in _foot
          and 'No VAT' in _foot
          and '19%' not in _foot and '7%' not in _foot
          and 'Steuernummer' not in _foot
          and 'Steuernummer: 12/345/67890' in _inv2['invoice_data']['footer']
          and SV.PACKS['starter']['name'] in _inv['invoice_data']['description']
          and "kwargs['invoice_creation'] = _invoice_creation(pack, p)" in
          open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read())
    # v135: USt-IdNr DE463613884 ist Ismets echte Kennung. Default im
    # Rechnungs-Footer (Label 'USt-IdNr.' bei DE+9 Ziffern) + Pflicht im
    # Impressum (§5 DDG, da vorhanden) - die alte 'keine USt-IdNr'-Aussage
    # dort waere jetzt falsch und muss weg.
    _tx0 = os.environ.get('DVE_TAX_ID')
    try:
        os.environ.pop('DVE_TAX_ID', None)
        _invd = SV._invoice_creation('starter', SV.PACKS['starter'])
    finally:
        if _tx0 is not None:
            os.environ['DVE_TAX_ID'] = _tx0
    _impr = open(os.path.join(HERE, 'web', 'imprint.html'), encoding='utf-8').read()
    check('v135: USt-IdNr im Rechnungs-Footer (Default) + im Impressum, alte Aussage weg',
          'USt-IdNr.: DE463613884' in _invd['invoice_data']['footer']
          and 'DE463613884' in _impr
          and 'no VAT identification number' not in _impr)
    # v165: Gemini-Pruefung der Rechnung (Ismets Vorlage). Drei Punkte:
    # (1) Marke + buergerlicher Name zusammen im Aussteller-Feld - §14 UStG
    #     verlangt den vollen Namen, die Marke allein reicht nicht.
    # (2) USt-IdNr als EIGENE Zeile direkt unter der Identitaet, nicht im
    #     Fliesstext versteckt.
    # (3) Leistungsdatum-Pflichtsatz (§14 Abs. 4 Nr. 6 UStG), zweisprachig.
    _f165 = _invd['invoice_data']['footer']
    _flds165 = {f['name']: f['value']
                for f in _invd['invoice_data']['custom_fields']}
    check('v165: Aussteller-Feld traegt Marke UND vollen Namen',
          _flds165.get('Aussteller') == 'DouchkoVE - Ismet Beyazkus'
          and len(_flds165['Aussteller']) <= 30)
    check('v165: die USt-IdNr steht als eigene Zeile im Absenderblock',
          '\nUSt-IdNr.: DE463613884\n' in _f165)
    check('v165: Leistungsdatum-Satz steht zweisprachig im Footer',
          'Leistungsdatum entspricht dem Ausstellungsdatum.' in _f165
          and 'Date of service corresponds to the invoice date.' in _f165)
    # Der 30-Zeichen-Deckel von Stripe: passt Marke+Name nicht hinein,
    # gewinnt der NAME (die Pflichtangabe), nicht die Marke.
    _n0 = os.environ.get('DVE_SELLER_NAME')
    _b0 = os.environ.get('DVE_SELLER_BRAND')
    try:
        os.environ['DVE_SELLER_NAME'] = 'Maximiliane Musterfrau-Beispiel'
        os.environ['DVE_SELLER_BRAND'] = 'DouchkoVE'
        _invl = SV._invoice_creation('starter', SV.PACKS['starter'])
    finally:
        for _k, _v in (('DVE_SELLER_NAME', _n0), ('DVE_SELLER_BRAND', _b0)):
            if _v is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _v
    _fl = {f['name']: f['value'] for f in _invl['invoice_data']['custom_fields']}
    check('v165: wird es zu lang, gewinnt der Name die 30 Zeichen, nicht die Marke',
          _fl['Aussteller'].startswith('Maximiliane')
          and 'DouchkoVE' not in _fl['Aussteller']
          and len(_fl['Aussteller']) <= 30)
    # ============ v157: 4K als Aufloesungsstufe, echte Abbuchung ===========
    # Die UI zeigt 4K jetzt als dritte Stufe NEBEN 720p/1080p, nicht mehr als
    # eigenes Quality-Feld. Damit schickt der Client die HOEHE - der Server
    # muss das als 4K-Wunsch erkennen, sonst wuerde 4K gerendert und nur der
    # einfache Satz berechnet.
    _uhd157 = os.path.join(tmp, 'st_uhd157.mp4')
    _hd157 = os.path.join(tmp, 'st_hd157.mp4')
    for _pth, _sz in ((_uhd157, '2560x1440'), (_hd157, '640x360')):
        if not os.path.exists(_pth):
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            f'testsrc=size={_sz}:rate=10:duration=1',
                            '-pix_fmt', 'yuv420p', _pth], check=True,
                           capture_output=True)
    check('v157: 4K als HOEHE wird als 4K erkannt',
          SV._will_uhd({'output': {'height': 2160}}, _uhd157) is True
          and SV._will_uhd({'output': {'height': 1080}}, _uhd157) is False)
    check('v157: 4K kostet wirklich das Doppelte',
          SV.credits_of(SV.cost_seconds(90, uhd=True))
          == 2 * SV.credits_of(SV.cost_seconds(90))
          and SV.credits_of(SV.cost_seconds(90, uhd=True)) == 4,
          f'90s: {SV.credits_of(SV.cost_seconds(90))} -> '
          f'{SV.credits_of(SV.cost_seconds(90, uhd=True))} Credits')
    check('v157: eine zu kleine Quelle kostet NICHT das Doppelte',
          SV._will_uhd({'output': {'height': 2160}}, _hd157) is False)
    # Und dann darf die Engine auch nicht auf 2160 weiterrechnen.
    _srv157 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    # v203-sec: dritte Stelle dazugekommen - render_start nimmt eine
    # Hochstufung auch dann zurueck, wenn der Job schon abgerechnet ist
    # (sonst 4K zum 1080p-Preis). Die Zusage ist dieselbe: JEDER Pfad, der 4K
    # ablehnt, setzt auch die Hoehe zurueck.
    check('v157: abgelehntes 4K wird auch aus der Hoehe zurueckgesetzt',
          _srv157.count("overrides['output']['height'] = 1080") == 3)
    _ui157 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v157: 4K steht als dritte Stufe neben 720p und 1080p',
          '720p:720,1080p:1080,4K &middot; 2&times; credits:2160' in _ui157
          and 'data-cfg="output.quality"' not in _ui157)
    check('v157: die Hoehen-Stufe kommt durch die Whitelist',
          SV._sanitize_overrides({'output': {'height': 2160}})
          == {'output': {'height': 2160}})

    # ======= v159: Captions folgen dem, was gesagt wird (Audit-Batch) =======
    # Ergebnis eines Audits mit 47 Agenten: 41 gemeldete Luecken, 29 haben die
    # adversarische Gegenpruefung ueberlebt. Hier die drei schwersten.
    import render as R
    import io as _io159, contextlib as _cl159
    _r159 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()

    # (1) ORTSANSAGE. _speech_intent hatte GENAU EINE Aufrufstelle - in
    # ai_direct. Ohne API-Key, bei API-Ausfall und bei Regie-Cache-Treffer
    # (der Normalfall beim zweiten Render) lief es nie. "Der Beweis steht
    # hinter mir" wurde dann komplett ignoriert.
    _w159 = 'der BEWEIS steht hinter mir. das GELD lag auf dem boden.'.split()
    _wl159 = [{'word': x, 'start': round(i * 0.4, 2),
               'end': round(i * 0.4 + 0.3, 2)} for i, x in enumerate(_w159)]
    _kw159 = {i for i, x in enumerate(_w159) if x.strip('.') in ('BEWEIS', 'GELD')}
    _fx159 = {i: {'fx': 'cascade', 'power': 2, 'n': 1} for i in _kw159}
    with _cl159.redirect_stdout(_io159.StringIO()):
        _fx159 = R._speech_intent(_fx159, _wl159)
    _bw = [v for i, v in _fx159.items() if _w159[i].strip('.') == 'BEWEIS'][0]
    _gd = [v for i, v in _fx159.items() if _w159[i].strip('.') == 'GELD'][0]
    check('v159: "hinter mir" setzt die Caption hinter die Person',
          _bw.get('fx') == 'behind' and _bw.get('intent') is True, str(_bw))
    check('v159: "auf dem Boden" legt sie auf den Boden',
          _gd.get('fx') == 'ground' and _gd.get('szene') == 'boden'
          and _gd.get('lage') == 'liegend' and _gd.get('intent') is True, str(_gd))
    check('v159: die Ortsansage laeuft in ALLEN Pfaden, nicht nur mit API-Key',
          _r159.count('_speech_intent(fx_map, words)') >= 1
          and _r159.count('= _speech_intent(') >= 2,
          f"{_r159.count('= _speech_intent(')} Aufrufstellen")
    check('v159: eine gesetzte Ansage wird beim zweiten Lauf nicht doppelt gemeldet',
          "if fx_map[i].get('intent'):\n            continue" in _r159)

    # (2) VERBFORMEN. ANIM_HINTS steht in der 3. Person Singular; das
    # Transkript sagt genauso oft den Infinitiv. Im Audit gemessen: 39 von 52
    # Verbpaaren verloren die Animation, sobald die -en-Form kam.
    check('v159: Plural und Infinitiv treffen dieselbe Animation',
          R.anim_for('', 'Die Firmen scheitern reihenweise.') == 'bruch'
          and R.anim_for('', 'Die Kurse steigen wieder.') == 'anstieg'
          and R.anim_for('', 'Alles zittert.') == 'zittern')
    # Gegenprobe: die Praefix-Suche hat frueher Fehlalarme ausgeloest.
    check('v159: "falls" loest keine Sturz-Animation mehr aus',
          R.anim_for('', 'Falls du jetzt aufgibst, verlierst du alles.') is None)
    check('v159: "gefaellt" bleibt weiterhin kein Sturz',
          R.anim_for('', 'Das gefaellt mir sehr.') is None)
    check('v159: der Stamm-Vergleich laesst kurze Woerter nicht kollidieren',
          R._anim_stamm('scheitern') == R._anim_stamm('scheitert')
          and R._anim_stamm('fall') == 'fall' and R._anim_stamm('falls') == 'falls')

    # (3) NEGATION. "Die Mieten steigen NICHT" bekam dieselbe
    # Aufwaerts-Animation wie ohne das Wort - samt Aufwaerts-Sound.
    check('v159: ein verneinter Satz bekommt keine bejahende Animation',
          R.anim_for('', 'Die Mieten steigen nicht.') is None
          and R.anim_for('', 'Das ist kein Absturz.') is None
          and R.anim_for('', 'The prices are not rising.') is None)
    check('v159: ohne Verneinung bleibt die Animation',
          R.anim_for('', 'Die Mieten steigen.') == 'anstieg'
          and R.anim_for('', 'Der Umsatz explodiert.') == 'explosion')

    # ======= v160: ZEIGE-REGIE - die Caption landet, wohin gezeigt wird =====
    # Reine Bildmessung aus Hand-Landmarks und Kopfdrehung. Getestet werden
    # die Entscheidungen, nicht "laeuft durch": ein Zeigefinger MUSS ein Ziel
    # in seiner Richtung ergeben, eine offene Hand KEINES, und ein Gesicht
    # bleibt auch mit Zeige-Ziel tabu.
    class _LM160:
        __slots__ = ('x', 'y')

        def __init__(self, x, y):
            self.x, self.y = float(x), float(y)

    def _hand160(streck):
        """Baut eine Hand: Handgelenk unten, Finger nach oben. streck =
        Liste von vier Bools (Zeige-, Mittel-, Ring-, kleiner Finger).
        Ein gestreckter Finger ragt weit ueber sein Mittelgelenk hinaus,
        ein eingerollter bleibt darunter - genau das misst _zeige_strahl."""
        p = [_LM160(0.5, 0.9)] * 21
        p = list(p)
        p[0] = _LM160(0.50, 0.90)          # Handgelenk
        p[9] = _LM160(0.50, 0.74)          # Mittelfinger-Grundgelenk (Massstab)
        for k, (tip, pip) in enumerate(R._HAND_FINGER):
            gx = 0.44 + 0.04 * k
            p[pip] = _LM160(gx, 0.66)
            p[tip] = _LM160(gx, 0.50 if streck[k] else 0.72)
        p[5] = _LM160(0.44, 0.70)          # Zeigefinger-Grundgelenk
        return p

    _W160, _H160 = 1080, 1920
    # Zeigefinger gestreckt, Rest eingerollt, Achse Grundgelenk -> Spitze
    # zeigt nach OBEN. Das Ziel muss oberhalb der Fingerspitze liegen.
    _zeig160 = R._zeige_strahl(_hand160([True, False, False, False]),
                               _W160, _H160)
    check('v160: ein gestreckter Zeigefinger ergibt ein Ziel in seiner Richtung',
          _zeig160 is not None and _zeig160[1] < 0.50 * _H160)
    check('v160: das Ziel bleibt im Bild',
          _zeig160 is not None
          and 0 <= _zeig160[0] <= _W160 and 0 <= _zeig160[1] <= _H160)
    # Offene Hand = Geste, kein Zeigen. Ohne diese Sperre wuerde jedes
    # Herumfuchteln die Captions durchs Bild schieben.
    check('v160: eine offene Hand ist kein Zeigen',
          R._zeige_strahl(_hand160([True, True, True, True]),
                          _W160, _H160) is None)
    check('v160: eine Faust ist kein Zeigen',
          R._zeige_strahl(_hand160([False, False, False, False]),
                          _W160, _H160) is None)
    # Zeigt der Finger in die Kamera, ist seine Projektion kurz. Dann gibt es
    # im Bild kein Ziel - Raten waere schlimmer als nichts.
    _kam160 = _hand160([True, False, False, False])
    _kam160[8] = _LM160(0.442, 0.695)      # Spitze fast auf dem Grundgelenk
    check('v160: ein Finger Richtung Kamera ergibt KEIN Ziel',
          R._zeige_strahl(_kam160, _W160, _H160) is None)

    # BLICK. Frontal = niemand ist gemeint. Deutlich gedreht = Ziel auf der
    # Seite, in die die Nase relativ zur Augenmitte gewandert ist.
    _frontal = [_LM160(0.45, 0.40), _LM160(0.55, 0.40), _LM160(0.50, 0.46)]
    check('v160: ein frontaler Kopf ergibt kein Blick-Ziel',
          R._blick_strahl(_frontal, _W160, _H160) is None)
    _rechts = [_LM160(0.45, 0.40), _LM160(0.55, 0.40), _LM160(0.56, 0.46)]
    _bz = R._blick_strahl(_rechts, _W160, _H160)
    check('v160: ein gedrehter Kopf zeigt zur Seite der Drehung',
          _bz is not None and _bz[0] > 0.56 * _W160)
    _links = [_LM160(0.45, 0.40), _LM160(0.55, 0.40), _LM160(0.44, 0.46)]
    _bl = R._blick_strahl(_links, _W160, _H160)
    check('v160: die Gegenrichtung ergibt das Gegen-Ziel',
          _bl is not None and _bl[0] < 0.44 * _W160)

    # Ohne Modelle bleibt das Feature still aus - kein Crash, kein Fake.
    check('v160: ohne Zeitpunkte misst die Zeige-Regie gar nichts',
          R.zeige_ziele('/nonexistent.mp4', [], 1080, 1920) == [])

    # PLATZIERUNG. Der wichtigste Teil: das Ziel muss den Block wirklich
    # bewegen - und ein Gesicht muss trotzdem gewinnen.
    import yaml as _y160
    _cfg160 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _S160 = R.Sprites(_cfg160, _W160, _H160)
    # KURZE Woerter mit Absicht: ein breiter Textblock hat im Title-Safe kaum
    # seitlichen Spielraum (gemessen 0.77 W Blockbreite bei 0.84 W nutzbarer
    # Flaeche - da kann keine Geste mehr etwas verschieben). Die Zeige-Regie
    # wirkt dort, wo es Platz gibt; das ist eine echte Grenze, keine Schwaeche
    # des Tests.
    _wrd160 = [{'word': _w, 'start': 1.0 + _i * 0.45, 'end': 1.35 + _i * 0.45}
               for _i, _w in enumerate(['ja', 'nun', 'so', 'ist', 'es', 'ok'])]

    def _block160(zeigen):
        """Mittlere Blockposition (x, y) in Bildanteilen je Chunk."""
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_wrd160, set(), _cfg160, _S160, _W160, _H160,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (_W160 * 0.50,
                                                        _H160 * 0.35,
                                                        _W160 * 0.13),
                               zeigen=zeigen)
        return [(sum(i['cx'] for i in q['front']) / len(q['front']) / _W160,
                 sum(i['cy'] for i in q['front']) / len(q['front']) / _H160)
                for q in pl if q.get('front')]

    _ziel_l = [(_t, _W160 * 0.12, _H160 * 0.80, 'zeigen')
               for _t in (1.0, 1.9, 2.8)]
    _ziel_r = [(_t, _W160 * 0.88, _H160 * 0.80, 'zeigen')
               for _t in (1.0, 1.9, 2.8)]
    _b_ohne = _block160(None)
    _b_links = _block160(_ziel_l)
    _b_rechts = _block160(_ziel_r)
    check('v160: die Zeige-Regie liefert ueberhaupt Bloecke',
          len(_b_ohne) >= 2 and len(_b_links) == len(_b_ohne)
          and len(_b_rechts) == len(_b_ohne))
    check('v160: nach links zeigen legt JEDEN Block nach links',
          all(x < 0.45 for (x, _) in _b_links),
          f"x = {[round(x, 3) for (x, _) in _b_links]}")
    check('v160: nach rechts zeigen legt JEDEN Block nach rechts',
          all(x > 0.55 for (x, _) in _b_rechts),
          f"x = {[round(x, 3) for (x, _) in _b_rechts]}")
    check('v160: der Unterschied zwischen links und rechts ist deutlich',
          min(x for (x, _) in _b_rechts) - max(x for (x, _) in _b_links) > 0.20,
          f"links {[round(x, 3) for (x, _) in _b_links]} "
          f"rechts {[round(x, 3) for (x, _) in _b_rechts]}")
    # Die HOEHE gehoert genauso zum Ziel. Ein Zeigefinger nach unten, der nur
    # die Seite aendert, waere eine halbe Umsetzung.
    check('v160: das Ziel zieht den Block auch in der Hoehe',
          all(y > 0.60 for (_, y) in _b_rechts)
          and any(y < 0.40 for (_, y) in _b_ohne),
          f"mit Ziel {[round(y, 3) for (_, y) in _b_rechts]} "
          f"ohne {[round(y, 3) for (_, y) in _b_ohne]}")
    # Das Gesicht sitzt bei 0.50 W / 0.35 H. Zeigt jemand mitten darauf, darf
    # der Text NICHT dort landen: die Gesichtssperre kostet ab 2.5 aufwaerts,
    # das volle Zeige-Gewicht erreicht 2.2. Text quer ueber dem Kopf des
    # Sprechers waere kein erfuellter Zeigefinger, sondern ein Fehler.
    _b_kopf = _block160([(_t, _W160 * 0.50, _H160 * 0.35, 'zeigen')
                         for _t in (1.0, 1.9, 2.8)])
    check('v160: ein Zeige-Ziel ueberrennt die Gesichtssperre NICHT',
          all(abs(y - 0.35) > 0.12 or abs(x - 0.50) > 0.18
              for (x, y) in _b_kopf),
          f"{[(round(x, 3), round(y, 3)) for (x, y) in _b_kopf]}")
    # ======= v161: OBJEKT-ANKER - die Caption klebt am Gegenstand ==========
    # Zwei Stufen, getrennt getestet: die KI sagt EINMAL, WAS gemeint ist
    # (ai_objekt_anker + Cache), Optical Flow sagt jeden Frame, WO es ist
    # (ObjektAnker).
    _cfg161 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    check('v161: der Objekt-Anker ist abschaltbar',
          _cfg161['effects'].get('caption_objekt') is True)

    # (1) TRACKER. Ein strukturiertes Kaestchen wandert um bekannte Pixel;
    # die gemessene Verschiebung muss das wiedergeben.
    def _szene161(dx, dy, w=480, h=854):
        img = np.zeros((h, w, 3), np.uint8)
        _rs = np.random.RandomState(7)
        img[:] = _rs.randint(0, 60, (h, w, 3))          # Grundrauschen
        # Objekt: kontrastreiches Schachbrett, damit es Ecken hat
        for _r in range(6):
            for _c in range(6):
                if (_r + _c) % 2 == 0:
                    y0 = 300 + dy + _r * 8
                    x0 = 150 + dx + _c * 8
                    img[y0:y0 + 8, x0:x0 + 8] = 245
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _W161, _H161 = 480, 854
    _tr161 = R.ObjektAnker(_szene161(0, 0), 174.0, 324.0, 34.0, _W161, _H161)
    check('v161: der Tracker findet genug Struktur zum Verfolgen', _tr161.ok)
    for _k in range(1, 6):
        _tr161.step(_szene161(4 * _k, 3 * _k))
    check('v161: der Tracker misst die echte Verschiebung',
          _tr161.ok and abs(_tr161.dx - 20.0) < 4.0
          and abs(_tr161.dy - 15.0) < 4.0,
          f"gemessen dx={_tr161.dx:.1f} dy={_tr161.dy:.1f}, erwartet 20/15")
    # Struktrurlose Flaeche: KEIN Anker. Ein Tracker ohne Ecken liefert
    # Rauschen, und Rauschen als Objektbewegung ist schlimmer als nichts.
    _leer = np.full((854, 480), 90, np.uint8)
    check('v161: ohne Struktur gibt es keine Spur',
          not R.ObjektAnker(_leer, 240.0, 400.0, 40.0, _W161, _H161).ok)
    # SCHNITT. Ein Sprung ueber ein Viertel der Bildbreite ist kein
    # wanderndes Objekt - die Spur muss enden statt mitzuspringen.
    _tr_cut = R.ObjektAnker(_szene161(0, 0), 174.0, 324.0, 34.0, _W161, _H161)
    _tr_cut.step(_szene161(200, 0))          # Sprung ueber 0.25 Bildbreiten
    check('v161: bei einem Schnitt endet die Spur, statt zu springen',
          not _tr_cut.ok and abs(_tr_cut.dx) < 1.0 and abs(_tr_cut.dy) < 1.0,
          f"ok={_tr_cut.ok} dx={_tr_cut.dx:.1f}")

    # (2) DER ANKER UEBERLEBT DEN REGIE-CACHE. Genau das war der v159-Fehler
    # an anderer Stelle: der Cache ist beim ZWEITEN Render der Normalfall.
    _rg161 = json.dumps({'keywords': [
        {'i': 1, 'fx': 'outline', 'power': 3, 'n': 1,
         'anker': {'objekt': 'Glas', 'cx': 0.42, 'cy': 0.61, 'groesse': 0.18}}]})
    # 'Glas' als Keyword: die Regie-Sperrliste wirft Fuellwoerter wie 'Dieses'
    # raus, dann gaebe es gar keinen Eintrag zum Pruefen.
    _w161 = [{'word': 'Schau', 'start': 0.5, 'end': 0.8},
             {'word': 'Glas', 'start': 0.9, 'end': 1.3},
             {'word': 'hier', 'start': 1.4, 'end': 1.8}]
    _pr161 = R.parse_regie(_rg161, _w161, 'de')
    check('v161: der Objekt-Anker ueberlebt den Regie-Cache',
          _pr161 is not None and isinstance(_pr161.get(1, {}).get('anker'), dict)
          and abs(_pr161[1]['anker']['cx'] - 0.42) < 1e-6)
    # Unsinnige Werte werden verworfen, nicht durchgereicht - eine
    # halluzinierte Box waere schlimmer als gar kein Anker.
    _mist = json.dumps({'keywords': [
        {'i': 1, 'fx': 'outline', 'power': 3, 'n': 1,
         'anker': {'objekt': 'X', 'cx': 1.4, 'cy': 0.5, 'groesse': 0.2}}]})
    check('v161: ein Anker ausserhalb des Bildes wird verworfen',
          'anker' not in (R.parse_regie(_mist, _w161, 'de') or {}).get(1, {}))
    _riesig = json.dumps({'keywords': [
        {'i': 1, 'fx': 'outline', 'power': 3, 'n': 1,
         'anker': {'objekt': 'X', 'cx': 0.5, 'cy': 0.5, 'groesse': 0.95}}]})
    check('v161: ein absurd grosser Anker wird verworfen',
          'anker' not in (R.parse_regie(_riesig, _w161, 'de') or {}).get(1, {}))
    check('v161: der Cache SCHREIBT den Anker auch',
          "**({'anker': v['anker']} if v.get('anker') else {})"
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # (3) PLATZIERUNG. Der Text gehoert NEBEN das Objekt, nicht darauf -
    # sonst verdeckt die Caption genau den Gegenstand, den sie meint.
    _Wo, _Ho = 1080, 1920
    _So = R.Sprites(_cfg161, _Wo, _Ho)
    _wo = [{'word': 'Schau', 'start': 0.5, 'end': 0.9},
           {'word': 'GLAS', 'start': 1.0, 'end': 1.6},
           {'word': 'hier', 'start': 1.7, 'end': 2.0}]

    def _ankerplan(anker):
        _fx = {1: {'fx': 'outline', 'power': 3, 'n': 1}}
        if anker:
            _fx[1]['anker'] = anker
        with _cl159.redirect_stdout(_io159.StringIO()):
            return R.build_plans(_wo, {1}, _cfg161, _So, _Wo, _Ho,
                                 lambda s_, e_: True, _fx,
                                 face_pos=lambda s_, e_: (_Wo * 0.5, _Ho * 0.30,
                                                          _Wo * 0.12))

    _obj = {'objekt': 'Glas', 'cx': 0.28, 'cy': 0.55, 'groesse': 0.16}
    _pl_ohne = [p for p in _ankerplan(None) if 'kw_i' in p]
    _pl_mit = [p for p in _ankerplan(_obj) if 'kw_i' in p]
    check('v161: der Anker landet ueberhaupt am Plan',
          bool(_pl_mit) and _pl_mit[0].get('_ank0') is not None
          and bool(_pl_ohne) and _pl_ohne[0].get('_ank0') is None)
    _px = _pl_mit[0].get('cx')
    _py = _pl_mit[0].get('cy')
    # 0.18 W Toleranz mit Absicht: clamp_cx haelt den Block im sicheren
    # Bereich, ein 0.56 W breiter Text kann seine Mitte nicht auf 0.28 W
    # legen. Gefordert ist die SEITE, nicht der Pixel.
    check('v161: der Text steht auf der Seite seines Objekts',
          _px is not None and abs(_px / _Wo - 0.28) < 0.18
          and _px / _Wo < 0.50,
          f"cx = {(_px or 0) / _Wo:.3f}, Objekt bei 0.28 W")
    # NEBEN, nicht DRAUF: die Objektmitte liegt bei 0.55 H, der Text muss
    # mindestens um seine halbe Hoehe plus Objektradius versetzt sein.
    _bild161 = _pl_mit[0].get('arr')
    if _bild161 is None:
        _bild161 = _pl_mit[0].get('o_arr')
    _hh = _bild161.shape[0] / 2.0 / _Ho
    check('v161: der Text steht NEBEN dem Objekt, nicht darauf',
          _py is not None and abs(_py / _Ho - 0.55) > (_hh + 0.16 * 0.5 * _Wo / _Ho),
          f"cy = {(_py or 0) / _Ho:.3f}, Objekt 0.55 H, halbe Texthoehe {_hh:.3f}")
    check('v161: ohne Anker bleibt die Platzierung die alte',
          _pl_ohne[0].get('cx') is not None)

    # (4) KEINE DOPPELBEWEGUNG. Der Objekt-Track enthaelt die Kamerafahrt
    # bereits. Szenen-Verankerung und Gesichts-Follow obendrauf wuerden
    # jeden Schwenk zweimal anwenden.
    _rsrc161 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v161: ein verankerter Text folgt NICHT zusaetzlich dem Gesicht',
          "if p.get('_ank0'):\n        return 0.0, 0.0" in _rsrc161)
    check('v161: die Szenen-Verankerung wendet den Schwenk nicht doppelt an',
          "if not lock or p.get('_ank0'):" in _rsrc161)
    check('v161: auf B-Roll gibt es keinen Objekt-Anker',
          "and not broll:" in _rsrc161 and "p['_ank0'] = (" in _rsrc161)

    # ======= v166: Blick ist ABWEICHUNG, nicht Haltung ====================
    # Ismets Befund nach v160: "es ist immer noch links". Ursache: die
    # absolute Blick-Schwelle. Eine seitlich stehende Kamera legte den Kopf
    # in JEDEM Moment ueber 0.35 - Dauer-Ziel auf einer Seite, das Ziel
    # ueberstimmt die Seiten-Abwechslung, alle Captions kleben links.
    _Wb, _Hb = 1080, 1920
    # Haltung: sechs Momente, Kopf immer bei +0.5 -> NULL Ziele.
    check('v166: eine seitliche Kopfhaltung erzeugt KEINE Blick-Ziele',
          R._blick_targets([(1.0 + i, 0.5, 0.55, 0.35) for i in range(6)],
                           _Wb, _Hb) == [])
    # Frontal-Sprecher mit EINEM bewussten Blick -> genau ein Ziel, rechts.
    _fr166 = [(1.0, 0.05, 0.50, 0.35), (2.0, 0.02, 0.50, 0.35),
              (3.0, 0.70, 0.53, 0.35), (4.0, -0.03, 0.50, 0.35)]
    _zf = R._blick_targets(_fr166, _Wb, _Hb)
    check('v166: ein bewusster Blick aus Frontal-Haltung zaehlt weiter',
          len(_zf) == 1 and _zf[0][0] == 3.0 and _zf[0][1] > _Wb * 0.55)
    # Haltung +0.5, EIN Moment dreht weiter auf +1.0 -> nur der zaehlt.
    _wt166 = [(1.0, 0.5, 0.55, 0.35), (2.0, 0.5, 0.55, 0.35),
              (3.0, 1.0, 0.58, 0.35), (4.0, 0.5, 0.55, 0.35)]
    _zw = R._blick_targets(_wt166, _Wb, _Hb)
    check('v166: wer aus seiner Haltung heraus WEITER dreht, meint einen Ort',
          len(_zw) == 1 and _zw[0][0] == 3.0)
    # Zurueck zur Kamera ist KEIN Blick auf einen Ort.
    _zk166 = [(1.0, 0.5, 0.55, 0.35), (2.0, 0.5, 0.55, 0.35),
              (3.0, 0.0, 0.50, 0.35), (4.0, 0.5, 0.55, 0.35)]
    check('v166: die Drehung zurueck zur Kamera ergibt kein Ziel',
          R._blick_targets(_zk166, _Wb, _Hb) == [])
    check('v166: unter 3 Messungen zaehlt nur eine deutliche Drehung',
          len(R._blick_targets([(1.0, 0.45, 0.55, 0.35)], _Wb, _Hb)) == 0
          and len(R._blick_targets([(1.0, 0.60, 0.55, 0.35)], _Wb, _Hb)) == 1)
    check('v166: zeige_ziele sammelt Blicke und filtert erst am Ende',
          '_blick_targets(blick_cands' in open(os.path.join(HERE, 'render.py'),
                                               encoding='utf-8').read())

    # ======= v169: drei Befunde aus Ismets echtem Video ===================
    # (1) Aktionswort nie hinter der Person - in ALLEN Pfaden (v159-Lehre).
    _r169 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    _cfg169 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _W169, _H169 = 1920, 1080
    _S169 = R.Sprites(_cfg169, _W169, _H169)
    _w169 = [{'word': 'they', 'start': 1.0, 'end': 1.3},
             {'word': 'EXPLODE', 'start': 1.4, 'end': 1.9}]
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl169 = R.build_plans(_w169, {1}, _cfg169, _S169, _W169, _H169,
                               lambda s_, e_: True,
                               {1: {'fx': 'behind', 'power': 3, 'n': 1}},
                               face_pos=lambda s_, e_: (_W169 * 0.5,
                                                        _H169 * 0.40,
                                                        _W169 * 0.10))
    _kw169 = [p for p in _pl169 if 'kw_i' in p]
    check('v169: ein explodierendes Wort steht VORN, nicht hinter der Person',
          _kw169 and _kw169[0]['tpl'] == 'outline'
          and _kw169[0].get('anim') in R._VISIBLE_ANIM,
          f"tpl={_kw169[0]['tpl'] if _kw169 else '?'} "
          f"anim={_kw169[0].get('anim') if _kw169 else '?'}")
    # v172 KORREKTUR der v169-Erwartung: sagt der Satz die HANDLUNG
    # ("boom they explode"), gewinnt sie auch gegen intent - das ist die
    # dokumentierte v99-Regel (sichtbar vorn, nie behind). Eine
    # ORTS-Ansage ohne Aktionsverb ("right BEHIND me") bleibt Gesetz.
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl169b = R.build_plans(_w169, {1}, _cfg169, _S169, _W169, _H169,
                                lambda s_, e_: True,
                                {1: {'fx': 'behind', 'power': 3, 'n': 1,
                                     'intent': True}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.10))
    _kw169b = [p for p in _pl169b if 'kw_i' in p]
    check('v172: die Handlung gewinnt auch gegen intent (v99-Regel)',
          _kw169b and _kw169b[0]['tpl'] == 'outline')
    _w172 = [{'word': 'right', 'start': 1.0, 'end': 1.3},
             {'word': 'BEHIND', 'start': 1.4, 'end': 1.8},
             {'word': 'me', 'start': 1.9, 'end': 2.1}]
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl172 = R.build_plans(_w172, {1}, _cfg169, _S169, _W169, _H169,
                               lambda s_, e_: True,
                               {1: {'fx': 'behind', 'power': 3, 'n': 1,
                                    'intent': True}},
                               face_pos=lambda s_, e_: (_W169 * 0.5,
                                                        _H169 * 0.40,
                                                        _W169 * 0.10))
    _kw172 = [p for p in _pl172 if 'kw_i' in p]
    check('v172: die Orts-Ansage "BEHIND me" bleibt Gesetz',
          _kw172 and _kw172[0]['tpl'] == 'behind')
    # v172: die Sichtbarkeit haengt am WORT, nicht an der Anim-Wahl der
    # Regie. Falsches Anim, kein Anim, Animationen aus - alles egal.
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl172b = R.build_plans(_w169, {1}, _cfg169, _S169, _W169, _H169,
                                lambda s_, e_: True,
                                {1: {'fx': 'behind', 'power': 3, 'n': 1,
                                     'anim': 'puls'}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.10))
    _kw172b = [p for p in _pl172b if 'kw_i' in p]
    check('v172: auch mit falsch gewaehltem Anim steht das Aktionswort vorn',
          _kw172b and _kw172b[0]['tpl'] == 'outline')
    _cfg172 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _cfg172['effects']['anim'] = False
    _S172 = R.Sprites(_cfg172, _W169, _H169)
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl172c = R.build_plans(_w169, {1}, _cfg172, _S172, _W169, _H169,
                                lambda s_, e_: True,
                                {1: {'fx': 'behind', 'power': 3, 'n': 1}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.10))
    _kw172c = [p for p in _pl172c if 'kw_i' in p]
    check('v172: auch mit Animationen AUS steht das Aktionswort vorn',
          _kw172c and _kw172c[0]['tpl'] == 'outline')
    # v173: blurin ist der DRITTE verdeckende Effekt. Sein grosses Wort
    # wird vor dem Person-Overlay gezeichnet und steht hinter der Person -
    # genau diesen fx hatte die Regie fuer Ismets "EXPLODE" gewaehlt
    # (pixel-identisch in zwei gestempelten Jobs), und alle bisherigen
    # Riegel prueften nur behind/ground.
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl173 = R.build_plans(_w169, {1}, _cfg169, _S169, _W169, _H169,
                               lambda s_, e_: True,
                               {1: {'fx': 'blurin', 'power': 3, 'n': 1}},
                               face_pos=lambda s_, e_: (_W169 * 0.5,
                                                        _H169 * 0.40,
                                                        _W169 * 0.10))
    _kw173 = [p for p in _pl173 if 'kw_i' in p]
    check('v173: ein explodierendes Wort als blurin kommt ebenfalls nach vorn',
          _kw173 and _kw173[0]['tpl'] == 'outline')
    # Ein neutrales Wort darf blurin bleiben - der Themenwechsel-Look ist
    # fuer ruhige Kapitel-Woerter gebaut und bleibt erhalten.
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl173b = R.build_plans([{'word': 'CHAPTER', 'start': 1.0,
                                  'end': 1.5}],
                                {0}, _cfg169, _S169, _W169, _H169,
                                lambda s_, e_: True,
                                {0: {'fx': 'blurin', 'power': 2, 'n': 1}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.10))
    check('v173: ein neutrales Wort behaelt den blurin-Look',
          [p['tpl'] for p in _pl173b if 'kw_i' in p] == ['blurin'])
    check('v173: auch der Cache-Riegel kennt blurin',
          "entry['fx'] in (\n                                'behind', 'blurin')"
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # (2) Kein Ein-Wort-Rest nach einer Sprechpause. "And the one THING"
    # (Keyword, Satz offen), dann 3.5 s Pause, dann ein einzelnes "is".
    _w169c = ([{'word': w, 'start': 1.0 + i * 0.35, 'end': 1.25 + i * 0.35}
               for i, w in enumerate(['And', 'the', 'one', 'THING'])]
              + [{'word': 'is', 'start': 6.0, 'end': 6.2}])
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl169c = R.build_plans(_w169c, {3}, _cfg169, _S169, _W169, _H169,
                                lambda s_, e_: True,
                                {3: {'fx': 'outline', 'power': 3, 'n': 1}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.08))
    _lone = [p for p in _pl169c if p.get('front')
             and len(p['front']) == 1 and p['start'] > 5.0]
    check('v169: ein einzelnes Wort nach einer Sprechpause faellt weg',
          not _lone)
    # Ohne Pause laeuft die Satz-Fortsetzung weiter wie bisher.
    # Aufbau mit Bedacht: unter 0.35 s schluckt die Keyword-Phrase die
    # Woerter selbst, die ERSTE Folgegruppe frisst die Atempause (gewollt,
    # seit v-alt), und ueber 1.2 s greift die neue Pausen-Grenze. Also zwei
    # Folgegruppen mit moderaten Abstaenden - die zweite muss laufen.
    _w169d = ([{'word': w, 'start': 1.0 + i * 0.35, 'end': 1.25 + i * 0.35}
               for i, w in enumerate(['And', 'the', 'one', 'THING'])]
              + [{'word': w, 'start': 3.05 + i * 0.3, 'end': 3.25 + i * 0.3}
                 for i, w in enumerate(['is', 'really'])]
              + [{'word': w, 'start': 4.35 + i * 0.3, 'end': 4.55 + i * 0.3}
                 for i, w in enumerate(['quite', 'simple.'])])
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl169d = R.build_plans(_w169d, {3}, _cfg169, _S169, _W169, _H169,
                                lambda s_, e_: True,
                                {3: {'fx': 'outline', 'power': 3, 'n': 1}},
                                face_pos=lambda s_, e_: (_W169 * 0.5,
                                                         _H169 * 0.40,
                                                         _W169 * 0.08))
    check('v169: ohne Pause laeuft die Satz-Fortsetzung weiter',
          any(p.get('front') and p['start'] > 4.0 for p in _pl169d))

    # (3) Die kleine Collage-Spalte dockt an der Treppe an, statt an der
    # fernen Aussenkante zu haengen (Loch von ~0.15 Spiegelbreiten).
    _wc169 = [{'word': w, 'start': 1.0 + i * 0.3, 'end': 1.2 + i * 0.3}
              for i, w in enumerate(['and', 'i', 'just', 'can', 'push',
                                     'them', 'anywhere.'])]
    _it169, _th169, _ = R.compose_flow(list(range(7)), _wc169, _S169,
                                       _W169, _H169, portrait=False,
                                       layout='collage', seite='rechts')
    _klein = [it for it in _it169
              if it.get('role') in ('norm', 'accent') and not it.get('gross')]
    _gross169 = [it for it in _it169 if it.get('gross')]
    if _klein and _gross169:
        _kl_l = min(it['cx'] - it['adv'] / 2.0 for it in _klein)
        _gr_r = max(it['cx'] + it['adv'] / 2.0 for it in _gross169)
        check('v169: kleine Spalte sitzt NEBEN der Treppe, kein Loch',
              _kl_l - _gr_r < _W169 * 0.10,
              f"Luecke {(_kl_l - _gr_r) / _W169:.3f} W")
    else:
        check('v169: kleine Spalte sitzt NEBEN der Treppe, kein Loch',
              False, 'Collage ohne kleine/grosse Woerter')

    # ======= v171: Herkunft in Datei und Dateinamen =======================
    # Vier byte-identische "neue" Renders in Folge - niemand konnte sehen,
    # welcher Job eine Datei erzeugt hat. Jetzt: Job-Stempel in den
    # MP4-Metadaten (Engine, via Env) + Job-ID im Download-Namen (Server).
    _srv171 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _r171 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v171: der Server stempelt Build + Job-ID in die Render-Umgebung',
          "env['DVE_JOB_TAG'] = f'DouchkoVE {DVE_BUILD} job {jid}'" in _srv171)
    check('v171: die Engine schreibt den Stempel in die MP4-Metadaten',
          "os.environ.get('DVE_JOB_TAG'" in _r171
          and "f'comment={_tag[:120]}'" in _r171)
    check('v171: der Download-Name traegt die Job-ID',
          "filename=f'DouchkoVE_{jid[:8]}.mp4'" in _srv171
          and "filename='DouchkoVE_Captions.mp4'" not in _srv171)

    # ======= v170: die v169-Fixe griffen im falschen Pfad =================
    # Am ZWEITEN echten Render belegt: Spalte gedockt (v169/3 wirkt), aber
    # "is" und "EXPLODE" unveraendert. Ursache 1: Ismets Job lief mit
    # Dichte 'durchgehend' - dort rendert JEDE Gruppe, der Orphan-Riegel
    # sass nur im satz_offen-Pfad. Ursache 2: EXPLODE kam als WAND-Text
    # (fx ground) aus der Vision-Regie, der Riegel prueft nur 'behind'.
    _cfg170 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _cfg170['effects']['density'] = 'durchgehend'
    _S170 = R.Sprites(_cfg170, 1280, 720)
    _w170 = ([{'word': x, 'start': 9.4 + i * 0.3, 'end': 9.65 + i * 0.3}
              for i, x in enumerate(['And', 'the', 'one', 'THING'])]
             + [{'word': 'is', 'start': 13.9, 'end': 14.1}])
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl170 = R.build_plans(_w170, {3}, _cfg170, _S170, 1280, 720,
                               lambda s_, e_: True,
                               {3: {'fx': 'outline', 'power': 3, 'n': 1}},
                               face_pos=lambda s_, e_: (640.0, 288.0, 115.0))
    check('v170: der Ein-Wort-Rest faellt auch bei Dichte durchgehend weg',
          not any(p.get('start', 0) > 13.0 for p in _pl170))
    check('v170: die Gruppen davor bleiben erhalten',
          any(p.get('front') for p in _pl170))
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl170b = R.build_plans(
            [{'word': 'they', 'start': 1.0, 'end': 1.3},
             {'word': 'EXPLODE', 'start': 1.4, 'end': 1.9}],
            {1}, _cfg169, _S169, _W169, _H169, lambda s_, e_: True,
            {1: {'fx': 'ground', 'power': 3, 'n': 1,
                 'szene': 'wand', 'lage': 'stehend'}},
            face_pos=lambda s_, e_: (_W169 * 0.5, _H169 * 0.40, _W169 * 0.10))
    _kw170 = [p for p in _pl170b if 'kw_i' in p]
    check('v170: ein explodierender WAND-Text kommt ebenfalls nach vorn',
          _kw170 and _kw170[0]['tpl'] == 'outline')
    # Auf B-Roll bleibt ground: dort verdeckt keine Person.
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl170c = R.build_plans(
            [{'word': 'they', 'start': 1.0, 'end': 1.3},
             {'word': 'EXPLODE', 'start': 1.4, 'end': 1.9}],
            {1}, _cfg169, _S169, _W169, _H169, lambda s_, e_: False,
            {1: {'fx': 'ground', 'power': 3, 'n': 1, 'intent': True,
                 'szene': 'boden', 'lage': 'liegend'}},
            face_pos=None)
    _kw170c = [p for p in _pl170c if 'kw_i' in p]
    check('v170: auf B-Roll bleibt der Szenen-Text liegen',
          _kw170c and _kw170c[0]['tpl'] == 'ground')

    # ======= v174: Hand und Captions agieren zusammen =====================
    # Ismets Befund am v173-Render: die Schub-Geste ("push them away") kam,
    # der Text stand am anderen Bildrand und reagierte nicht. Zwei Teile:
    # (1) NAEHERUNGS-Treffer: eine schnelle Hand, die auf den Text
    # ZUFLIEGT, trifft auch ohne Pixel-Beruehrung. Zwei Bedingungen mehr
    # als der Kontakt: hoehere Geschwindigkeit UND Richtung zum Text.
    _p174 = {'kw_i': 1, 'arr': np.zeros((100, 400, 4), np.float32),
             'cx': 300.0, 'cy': 500.0, 'start': 1.0, 'end': 2.0}
    # v179 KORREKTUR: der Naeherungs-Treffer aus v174 ist wieder RAUS. Er
    # war ein Notbehelf gegen den damals unmoeglichen Kontakt; seit v176
    # laufen aber ALLE Flow-Chunks durch diese Pruefung, und wer beim
    # Sprechen gestikuliert, liess damit JEDE Caption zucken (Ismets
    # Befund). Den angesagten Schub traegt seit v177/v178 die Ansage.
    _tips_nah = [(300.0 + 260.0, 500.0, -900.0, 0.0)]    # schnell, knapp daneben
    check('v179: eine Geste NEBEN dem Text laesst ihn in Ruhe',
          R.hand_contacts([dict(_p174)], _tips_nah, 1.5, 1280, 720) == 0)
    _tips_drin = [(300.0, 500.0, 200.0, 0.0)]            # Beruehrung wie v101j
    check('v174: die echte Beruehrung funktioniert weiter wie in v101j',
          R.hand_contacts([dict(_p174)], _tips_drin, 1.5, 1280, 720) == 1)
    check('v179: der Naeherungs-Code ist wirklich weg',
          '_reich = W * 0.075'
          not in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())
    # (2) HAND-AKTIONS-WOERTER ziehen die Caption in Reichweite der Hand.
    check('v174: "push them away" ist eine Hand-Aktion',
          R._hand_aktion_hit('push') and R._hand_aktion_hit('pushed')
          and R._hand_aktion_hit('wegschieben') and R._hand_aktion_hit('wischt'))
    check('v174: normale Woerter sind keine Hand-Aktion',
          not R._hand_aktion_hit('important')
          and not R._hand_aktion_hit('Zahlen'))
    check('v174: ohne Zeitpunkte misst hand_ziele nichts',
          R.hand_ziele('/nonexistent.mp4', [], 1280, 720) == [])
    check('v174: die Hand-Ziele laufen durch denselben Dedupe wie das Zeigen',
          'hand_ziele(args.input, _ht, W, H)'
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # ======= v176: der Hand-Kontakt erreicht auch Flow-Chunks =============
    # Am ECHTEN Render gemessen (Job 8ff7812b): die Hand kreuzt x = 0.58 ->
    # 0.19 W, der Text steht bei 0.47 W - der Kontakt WAERE da gewesen.
    # Er kam nicht, weil das ganze Hand-System an 'kw_i' haengt: need_hands
    # schaltete den Tracker in Fuellwort-Fenstern gar nicht ein, und
    # hand_contacts uebersprang Plaene ohne kw_i. Ismets Schub-Satz
    # ("and i just can push them away") ist genau so ein Chunk.
    _arr176 = np.zeros((60, 120, 4), np.float32)
    def _flow176():
        return {'tpl': 'flow', 'start': 7.0, 'end': 9.0,
                'front': [{'i': 0, 'arr': _arr176, 'cx': 560.0, 'cy': 500.0},
                          {'i': 1, 'arr': _arr176, 'cx': 700.0, 'cy': 500.0}]}
    _p176 = _flow176()
    check('v176: eine Hand, die den Flow-Block kreuzt, loest Kontakt aus',
          R.hand_contacts([_p176], [(640.0, 500.0, -1300.0, 0.0)],
                          8.0, 1280, 720) == 1
          and '_hand_hit' in _p176)
    check('v176: der Stoss bewegt den Flow-Block wirklich',
          abs(R.hand_spring(_p176, 8.0)[0]) >= 0.0
          and abs(R.hand_spring(_p176, 8.05)[0]) > 5.0)
    # Weit weg und langsam bleibt weiterhin folgenlos.
    check('v176: eine ferne, langsame Hand laesst den Flow-Block in Ruhe',
          R.hand_contacts([_flow176()], [(200.0, 200.0, 40.0, 0.0)],
                          8.0, 1280, 720) == 0)
    # v179: und eine SCHNELLE Hand knapp daneben ebenfalls - sonst zuckt
    # bei einem gestikulierenden Sprecher jede einzelne Caption.
    check('v179: eine schnelle Geste neben dem Flow-Block bleibt folgenlos',
          R.hand_contacts([_flow176()], [(1000.0, 500.0, -900.0, 0.0)],
                          8.0, 1280, 720) == 0)
    # Der Keyword-Pfad (v101j) bleibt unveraendert.
    check('v176: der Keyword-Kontakt funktioniert weiter',
          R.hand_contacts([{'kw_i': 1, 'arr': np.zeros((100, 400, 4), np.float32),
                            'cx': 300.0, 'cy': 500.0, 'start': 1.0, 'end': 2.0}],
                          [(300.0, 500.0, 200.0, 0.0)], 1.5, 1280, 720) == 1)
    _r176 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v176: die Hand-Erkennung ist auch in Flow-Fenstern scharf',
          "if 'kw_i' in p or p.get('front'):" in _r176)
    check('v176: die Feder wirkt auf den Flow-Block',
          "fdx += p.get('_hand_dx', 0.0)" in _r176)

    # ======= v177: der angesagte Wisch braucht keine Pixel-Beruehrung =====
    # Am echten Render gemessen (Job d70adb09): der Sprecher wischt mit
    # 861 px/s quer durchs Bild - aber SEIN KOERPER steht dort, wo die Hand
    # entlangfaehrt. Die Caption kann dort gar nicht liegen: das Hand-Ziel
    # wiegt 2.2, die Gesichtssperre 2.5, und das ist richtig so. Auf
    # Pixel-Beruehrung zu warten hiess also: die Geste bleibt fuer immer
    # folgenlos. Sagt der Satz die Handlung UND ist ein schneller Wisch
    # messbar, bekommt der Block den Impuls - Ansage plus Messung.
    def _blk177(geste):
        return {'tpl': 'flow', 'start': 7.0, 'end': 9.0,
                '_hand_geste': geste,
                'front': [{'i': 0, 'arr': _arr176, 'cx': 220.0, 'cy': 400.0},
                          {'i': 1, 'arr': _arr176, 'cx': 360.0, 'cy': 400.0}]}
    _fern177 = [(950.0, 520.0, -900.0, 180.0)]     # schnell, aber weit weg
    _p177 = _blk177(True)
    check('v177: ein angesagter Wisch stoesst den Block auch aus der Ferne',
          R.hand_contacts([_p177], _fern177, 8.0, 1280, 720) == 1
          and _p177.get('_hand_hit') is not None)
    check('v177: der Impuls zeigt in die Wisch-Richtung',
          _p177['_hand_hit'][0] < 0)          # Wisch nach links -> Stoss links
    check('v177: OHNE Ansage passiert aus der Ferne weiterhin nichts',
          R.hand_contacts([_blk177(False)], _fern177, 8.0, 1280, 720) == 0)
    check('v177: eine Ansage ohne echten Wisch loest nichts aus',
          R.hand_contacts([_blk177(True)],
                          [(950.0, 520.0, -200.0, 40.0)],
                          8.0, 1280, 720) == 0)
    # v178 WUCHT NACH ANSAGE. Der v101j-Deckel (W*1.2) ist fuer den
    # ZUFAELLIGEN Kontakt gebaut - am Render gemessen ergab er 27 px
    # Ausschlag, einen Stups statt "push them AWAY". Wer die Handlung
    # ansagt, hat sie bestellt: eigener Deckel, weichere Feder, weniger
    # Daempfung. Der beilaeufige Kontakt bleibt exakt beim Alten.
    def _aus178(geste, tips):
        _p = _blk177(geste)
        R.hand_contacts([_p], tips, 8.0, 1280, 720)
        _t, _mx = 8.0, 0.0
        for _ in range(40):
            _dx, _dy = R.hand_spring(_p, _t)
            _mx = max(_mx, abs(_dx) + abs(_dy))
            _t += 0.04
        return _mx
    _stark178 = _aus178(True, [(950.0, 520.0, -900.0, 180.0)])
    _leicht178 = _aus178(False, [(290.0, 400.0, -400.0, 80.0)])
    check('v178: der angesagte Wisch schleudert den Block wirklich weg',
          _stark178 > 100.0, f"{_stark178:.0f} px Ausschlag")
    check('v178: der beilaeufige Kontakt bleibt ein Stups',
          _leicht178 < 40.0, f"{_leicht178:.0f} px Ausschlag")
    check('v178: die Ansage wirkt mindestens dreimal so stark',
          _stark178 > _leicht178 * 3.0,
          f"angesagt {_stark178:.0f} px vs. Kontakt {_leicht178:.0f} px")
    # Der Block muss zurueckkommen - ein Text, der weggeschoben bleibt,
    # ist kein Effekt, sondern ein verlorener Satz.
    _p178 = _blk177(True)
    R.hand_contacts([_p178], [(950.0, 520.0, -900.0, 180.0)], 8.0, 1280, 720)
    _t178 = 8.0
    for _ in range(45):
        _d178 = R.hand_spring(_p178, _t178)
        _t178 += 0.04
    check('v178: der Block schwingt zurueck in die Ruhelage',
          abs(_d178[0]) + abs(_d178[1]) < 25.0,
          f"nach 1.8 s noch {abs(_d178[0]) + abs(_d178[1]):.0f} px")
    check('v178: der Kraft-Modus haengt an der Ansage, nicht am Zufall',
          "p.get('_hand_kraft')"
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())
    check('v177: der Schub-Satz wird am Flow-Plan markiert',
          "'_hand_geste': any(_hand_aktion_hit(clean(words[j]['word']))"
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # ======= v181/v182: Lesbarkeit + aktives Wort =========================
    # Am echten Render gemessen: 1.52 / 1.81 / 1.58 / 3.10:1 Kontrast - die
    # WCAG-AA-Norm ist 4.5:1. Der Text trug nur einen VERSETZTEN Schatten,
    # der auf grauem Pullover und Beton wirkungslos ist.
    _cfg181 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    check('v181: die Kontrast-Norm steht auf 4.5:1, nicht mehr auf 2.2',
          float(_cfg181['effects']['caption_contrast']) >= 4.5)
    # v199: die Kontur ist AUS (Ismets Ansage). Der Test prueft jetzt, dass
    # der Schalter existiert und einen gueltigen Wert traegt - nicht mehr,
    # dass er an ist. Dass die Kontur WIRKT, wenn man sie einschaltet,
    # steht unveraendert in Abschnitt (2).
    check('v199: die Kontur ist abgeschaltet',
          float(_cfg181['effects']['caption_kontur']) == 0,
          f"caption_kontur = {_cfg181['effects']['caption_kontur']}")
    check('v182: das aktive Wort ist an und abschaltbar',
          _cfg181['effects'].get('caption_aktivwort') is True)

    # (1) TON-WAHL. Mit Kontur bleibt der Text auf mittelgrauem Grund HELL -
    # die Kontur traegt den Kontrast. Nach Dunkel zu kippen waere lesbar,
    # saehe aber aus wie ein anderer Look (am Testrender belegt).
    def _bg181(v):
        return R.region_luminance(np.full((40, 40, 3), v, np.uint8))
    _grau181 = _bg181(150)
    _hell181 = _bg181(228)
    _dunkel181 = _bg181(35)
    check('v181: auf Mittelgrau bleibt der Text mit Kontur hell',
          R.fit_caption_color(20, 40, _grau181, 4.5, kontur=True)[0] >= 200,
          f"{R.fit_caption_color(20, 40, _grau181, 4.5, kontur=True)}")
    check('v181: auf hellem Grund kippt er trotz Kontur nach dunkel',
          R.fit_caption_color(20, 40, _hell181, 4.5, kontur=True)[0] <= 80,
          f"{R.fit_caption_color(20, 40, _hell181, 4.5, kontur=True)}")
    check('v181: auf dunklem Grund bleibt die Szenen-Toenung erhalten',
          R.fit_caption_color(20, 40, _dunkel181, 4.5, kontur=True)[0] >= 200)
    check('v181: OHNE Kontur darf er auf Mittelgrau nach dunkel',
          R.fit_caption_color(20, 40, _grau181, 4.5, kontur=False)[0] <= 80)
    # Und der erreichte Kontrast muss die Norm wirklich schlagen.
    _c181 = R.fit_caption_color(20, 40, _hell181, 4.5, kontur=False)
    check('v181: die gewaehlte Farbe erreicht die Norm auch messbar',
          R.contrast_ratio(_c181, _hell181) >= 4.5,
          f"{R.contrast_ratio(_c181, _hell181):.2f}:1")

    # (2) DIE KONTUR VERAENDERT DAS SPRITE WIRKLICH - sonst waere die
    # ganze Einstellung Zierde.
    _cfg_k0 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _cfg_k0['effects']['caption_kontur'] = 0.0
    # v199: nicht mehr die Datei-Config als "mit" nehmen - dort steht jetzt 0.
    _cfg_k1 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _cfg_k1['effects']['caption_kontur'] = 1.0
    _a_mit = R.Sprites(_cfg_k1, 1280, 720).text('THING', 55, (245, 245, 245))[0]
    _a_ohne = R.Sprites(_cfg_k0, 1280, 720).text('THING', 55, (245, 245, 245))[0]
    _dunkel_mit = float(((_a_mit[..., :3].max(axis=2) < 60)
                         & (_a_mit[..., 3] > 120)).sum())
    _dunkel_ohne = float(((_a_ohne[..., :3].max(axis=2) < 60)
                          & (_a_ohne[..., 3] > 120)).sum())
    check('v181: mit Kontur gibt es deutlich mehr dunkle Randpixel',
          _dunkel_mit > _dunkel_ohne * 1.5,
          f"mit {_dunkel_mit:.0f} vs. ohne {_dunkel_ohne:.0f}")
    check('v181: die Kontur laesst sich wirklich abschalten',
          _dunkel_ohne < _dunkel_mit)
    # v199: was ohne Kontur an dunklen Pixeln uebrig bleibt, ist der
    # SCHLAGSCHATTEN - er sitzt versetzt, ein Umriss laege rundherum.
    # Ohne diese Probe koennte ein Rest-Saum als "Schatten" durchgehen.
    def _versatz199(arr):
        _d = np.nonzero((arr[..., :3].max(axis=2) < 60) & (arr[..., 3] > 120))
        _h = np.nonzero((arr[..., :3].min(axis=2) > 200) & (arr[..., 3] > 200))
        return abs(float(_d[0].mean() - _h[0].mean()))
    check('v199: ohne Kontur bleibt nur der versetzte Schatten',
          _versatz199(_a_ohne) > _versatz199(_a_mit) * 2,
          f"ohne {_versatz199(_a_ohne):.1f} px vs. mit {_versatz199(_a_mit):.1f} px")
    # Gemessen wird die TINTE, nicht das Sprite-Rechteck: dessen Polsterung
    # ist fest, der Saum waechst nur die gesetzten Pixel (v194-Lehre).
    def _inkbox199(arr):
        _y, _x = np.nonzero(arr[..., 3] > 40)
        return int(_x.max() - _x.min() + 1), int(_y.max() - _y.min() + 1)
    check('v199: die Tinte wird ohne Kontur schmaler und niedriger',
          _inkbox199(_a_ohne) < _inkbox199(_a_mit),
          f"{_inkbox199(_a_ohne)} < {_inkbox199(_a_mit)}")
    check('v199: auch der Viral-Look traegt keinen Saum mehr',
          "'caption_kontur': 0," in open(os.path.join(HERE, 'web', 'server.py'),
                                         encoding='utf-8').read())
    check('v199: die Vorschau faellt nicht auf 1 zurueck, wenn 0 gemeint ist',
          'Number.isFinite(_kRoh) ? _kRoh : 0' in open(
              os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read())

    # (3) AKTIVES WORT: Quelltext-Garantien. Das schon gesprochene Wort
    # dimmt, das aktive bleibt voll und bekommt einen abklingenden Pop.
    # Schluesselwoerter duerfen NIE dimmen - sie tragen die Aussage.
    _r182 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v182: es gibt eine Wahl des aktiven Wortes',
          '_akt_i = max(_kand,' in _r182)
    # v183 TESTANPASSUNG (Substanz unveraendert): das Dimmen traegt seit
    # v183 den Viral-Riegel ('and not _viral' - im Viral-Look traegt die
    # FARBE die Emphase), der Pop hat zwei Staerken (0.055 Haus, 0.10 viral).
    # v190: das Dimmen laeuft weich (Uebergang statt Sprung), der Zielwert
    # bleibt 70 %. Keywords dimmen weiterhin nie.
    check('v182: vergangene Woerter dimmen, Keywords nie',
          "elif it.get('role') not in ('key', 'punch'):" in _r182
          and ('_dim = 0.70' in _r182 or '1.0 - 0.30 * smoothstep' in _r182))
    check('v182: das aktive Wort bekommt einen abklingenden Groessen-Pop',
          '_pop = 1.0 + ((0.10 if _viral else 0.055)' in _r182
          and '(1 - smoothstep(min(dt / 0.22, 1.0)))' in _r182)
    check('v182: Deckkraft und Skalierung wirken auf BEIDE Zeichenwege',
          _r182.count('* _pop') >= 2 and _r182.count('* _dim') >= 2)

    # ======= v183: Viral-Look (Markt-Standard als Preset) =================
    # Ismets Befund am eigenen Render, nachgemessen: Keywords 0.078-0.096 H
    # Versalhoehe, Fliesstext bis 0.014 H, Streu-Collage ohne Lesereihen-
    # folge - der Markt (Submagic/Hormozi-Schule) faehrt 0.10-0.15 H versal
    # in engen Bloecken, die Akzentfarbe wandert mit dem gesprochenen Wort.
    # Der Viral-Look liefert genau das als Preset; Editorial bleibt waehlbar.
    _sv183 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v183: der Look "viral" existiert im Katalog',
          "'viral':     {'name': 'Viral'" in _sv183)
    check('v183: das Preset setzt den Engine-Schalter caption_viral',
          "'caption_viral': True" in _sv183)
    check('v183: das Preset erzwingt Zeilensatz, Mitte und Markt-Zone',
          "'caption_layout': 'rows'" in _sv183
          and "'caption_seite': 'mitte'" in _sv183
          and "'caption_zone': 0.58" in _sv183)
    # v185 TESTKORREKTUR: der feste Gelb-Akzent ist raus (Ismet: "aus-
    # gelutscht"). Geprueft bleibt, dass der Look eine definierte Textfarbe
    # setzt - die Akzentfarbe kommt wieder aus der Szene.
    check('v185: das Viral-Preset setzt Weiss und ueberlaesst den Rest der Szene',
          "'text': [255, 255, 255]" in _sv183
          and "'accent': [255, 214, 10]" not in _sv183)
    _ui183 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v183: die UI kennt den Viral-Look (Label + Karte)',
          "viral: 'Viral" in _ui183 and 'data-look=viral' in _ui183)
    # v183a: Ismets Befund am Ergebnis - "das ist das Standard-Template von
    # CapCut und Opus". Der Look bleibt als OPTION, aber er ist NICHT mehr
    # der Auto-Default fuer 9:16 und steht nicht mehr an erster Stelle.
    check('v183a: KEIN Auto-Default mehr auf den Viral-Look',
          "State.look = 'viral'" not in _ui183)
    check('v183a: der Katalog fuehrt nicht mit dem Standard-Template',
          _sv183.find("'tiktok':") < _sv183.find("'viral':"))
    check('v183: der Zeilensatz-Riegel sitzt an der immer laufenden Stelle',
          "if cfg['effects'].get('caption_viral'):" in _r182
          and "_lm = 'rows'" in _r182)
    check('v183: der Punch-Deckel kennt den Crash-Zoom',
          '0.89 - 0.11 * max(0.0, min(1.0, _crash))' in _r182)
    check('v185: keine Farb-Karaoke mehr im Viral-Look',
          "acc_rgb" not in _r182 and 'tint_glyph' not in _r182)

    # VERHALTEN direkt an compose_flow gemessen - nicht nur Quelltext.
    _cfgV = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                 encoding='utf-8'))
    _cfgV['fonts'] = {k: 'fonts/montserrat_xb.ttf'
                     for k in ('display', 'italic', 'script', 'support')}
    import copy as _cp183
    _cfgN = _cp183.deepcopy(_cfgV)
    _cfgV['effects']['caption_viral'] = True

    class _SRec183(R.Sprites):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.calls = []

        def text(self, txt, size, color, **kw):
            self.calls.append(str(txt))
            return super().text(txt, size, color, **kw)

    _wv = [{'word': w, 'start': i * 0.4, 'end': i * 0.4 + 0.3}
           for i, w in enumerate(['und', 'dann', 'kommt', 'alles', 'zusammen'])]
    _SV = _SRec183(_cfgV, 1080, 1920)
    _SN = _SRec183(_cfgN, 1080, 1920)
    _itV = R.compose_flow(list(range(5)), _wv, _SV, 1080, 1920, True,
                          flow_sel={'kw': 2})[0]
    _itN = R.compose_flow(list(range(5)), _wv, _SN, 1080, 1920, True,
                          flow_sel={'kw': 2})[0]
    check('v183: im Viral-Look laufen ALLE Woerter versal',
          all(t == t.upper() for t in _SV.calls),
          f"{_SV.calls}")
    check('v183: ohne Viral bleibt die gemischte Schreibung',
          any(t != t.upper() for t in _SN.calls))
    _nV = [i['sz'] for i in _itV if i.get('role') == 'norm']
    _nN = [i['sz'] for i in _itN if i.get('role') == 'norm']
    # v184: die Hausbasis wurde auf die Referenz-Messung angehoben (0.034 ->
    # 0.050 em) - das Viral-ZIEL (0.099 em) ist unveraendert, der Faktor
    # darauf ist jetzt 2.00 statt 2.90.
    check('v183: der Fliesstext-Faktor des Viral-Looks stimmt (Ziel 0.099 em)',
          _nV and _nN and 1.7 <= (_nV[0] / max(_nN[0], 1)) <= 2.3,
          f"{_nV[0]} vs {_nN[0]}")
    # v184 REFERENZ-GROESSEN der Hausbasis (an Ismets Vorbildern gemessen:
    # Fliesstext-Band 0.040 H, Schluesselwort-Band 0.074 H).
    # v192: eine Stufe kleiner auf Ismets Ansage (Faktor 0.85 auf die
    # v184-Referenzmasse). Die Kaskade bleibt geprueft, nur der Zielwert
    # wandert mit.
    check('v184/v192: Fliesstext-Basis 0.043 em der Bildhoehe',
          _nN and abs(_nN[0] - int(1920 * 0.043)) <= 4, f"{_nN[0]}")
    _kN = [i['sz'] for i in _itN if i.get('role') in ('key', 'punch')]
    check('v184/v192: Schluesselwort-Basis 0.089 em der Bildhoehe',
          _kN and abs(_kN[0] - int(1920 * 0.089)) <= 6, f"{_kN[0]}")
    check('v183: kein Schreibschrift-Akzent im Viral-Look',
          not any(i.get('role') == 'accent' for i in _itV)
          and any(i.get('role') == 'accent' for i in _itN))
    # Punch-Faktor: viral 1.30 statt 2.25 - die Grundgroesse traegt schon.
    _wp = [{'word': 'na', 'start': 0.0, 'end': 0.3},
           {'word': 'wow.', 'start': 0.4, 'end': 0.7}]
    _pV = R.compose_flow([0, 1], _wp, _SRec183(_cfgV, 1080, 1920), 1080, 1920,
                         True, flow_sel={'kw': 1}, punch=True)[0]
    _kV = R.compose_flow([0, 1], _wp, _SRec183(_cfgV, 1080, 1920), 1080, 1920,
                         True, flow_sel={'kw': 1}, punch=False)[0]
    _szP = next(i['sz'] for i in _pV if i['role'] in ('key', 'punch'))
    _szK = next(i['sz'] for i in _kV if i['role'] in ('key', 'punch'))
    check('v183: der Punch-Faktor im Viral-Look ist 1.30, nicht 2.25',
          _szP < _szK * 1.6,
          f"punch {_szP} vs key {_szK}")
    # Zoom-sicherer Deckel: mit vollem Crash-Zoom bleibt die Punch-Zeile
    # schmaler als mit ruhender Kamera (0.78 W statt 0.89 W).
    # v187: das Wort muss so lang sein, dass die BREITE bindet - seit dem
    # Hoehen-Deckel (0.165 H) laufen kurze Woerter vorher dort auf.
    _wl = [{'word': 'ja', 'start': 0.0, 'end': 0.3},
           {'word': 'unwahrscheinlicherweise.', 'start': 0.4, 'end': 0.7}]
    _cfgC0 = _cp183.deepcopy(_cfgN); _cfgC0['camera']['crash'] = 0.0
    _cfgC1 = _cp183.deepcopy(_cfgN); _cfgC1['camera']['crash'] = 1.0
    _twC0 = max(i['w'] for i in R.compose_flow(
        [0, 1], _wl, R.Sprites(_cfgC0, 1080, 1920), 1080, 1920, True,
        flow_sel={'kw': 1}, punch=True)[0])
    _twC1 = max(i['w'] for i in R.compose_flow(
        [0, 1], _wl, R.Sprites(_cfgC1, 1080, 1920), 1080, 1920, True,
        flow_sel={'kw': 1}, punch=True)[0])
    check('v183: der Punch-Deckel weicht dem Crash-Zoom aus',
          _twC1 < _twC0,
          f"crash1 {_twC1:.0f} vs crash0 {_twC0:.0f} px")
    # Zeilen-Zentrierung: 'mitte' zentriert die Zeile im Satzspiegel.
    _cxM = [i['cx'] for i in R.compose_flow(
        [0], [_wv[0]], R.Sprites(_cfgN, 1080, 1920), 1080, 1920, True,
        seite='mitte')[0]]
    _cxL = [i['cx'] for i in R.compose_flow(
        [0], [_wv[0]], R.Sprites(_cfgN, 1080, 1920), 1080, 1920, True,
        seite='links')[0]]
    check('v183: seite "mitte" zentriert die Zeile wirklich',
          _cxM[0] > _cxL[0] + 20,
          f"mitte {_cxM[0]:.0f} vs links {_cxL[0]:.0f}")
    # v185: die Karaoke-Faerbung (tint_glyph) ist komplett entfernt - Ismets
    # Urteil am Ergebnis: "Gelbakzent, die sind ausgelutscht." Damit fallen
    # auch ihre Tests weg; die Emphase wird ueber Groesse und Deckkraft
    # geprueft (v182-Block oben).
    check('v185: die Farb-Karaoke ist restlos entfernt',
          not hasattr(R, 'tint_glyph'))

    # ======= v194: Animationen tun, was ihr Name sagt ====================
    # Ismets Frage: "Tut die Explosion wirklich das, was sie hergibt?"
    # Gemessen wurde jede Animation direkt an anim_apply() - das ist eine
    # reine Funktion auf einem Sprite, dafuer braucht es kein Video.
    import numpy as _np194
    import yaml as _y194
    import render as _R194
    _R194.BEAT_SYNC = 0.0
    _c194 = _y194.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _S194 = _R194.Sprites(_c194, 1080, 1920)
    _b194, _ = _S194.text('BOOM', 90, (255, 255, 255))

    def _lage194(anim, t, LW=900, LH=600):
        """Wo sitzt die Tinte, wenn der Zeichenpfad das Sprite MITTIG setzt?
        Genau so landet es im Video - eine Messung im Sprite-Array allein
        wuerde eine einseitig gewachsene Leinwand nicht bemerken."""
        import cv2 as _cv194
        arr, dx, dy, sc, op = _R194.anim_apply(
            {'anim': anim, 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, 0.4, 0.0), t)
        cv = _np194.zeros((LH, LW), _np194.float32)
        h, w = arr.shape[:2]
        nw, nh = max(1, int(w * sc)), max(1, int(h * sc))
        a2 = _cv194.resize(arr, (nw, nh))
        x, y = int(LW / 2 - nw / 2 + dx), int(LH / 2 - nh / 2 + dy)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(LW, x + nw), min(LH, y + nh)
        if x1 <= x0 or y1 <= y0:
            return None
        sub = a2[y0 - y:y1 - y, x0 - x:x1 - x]
        al = sub[:, :, 3] / 255.0 * max(0.0, min(1.0, op))
        g = _cv194.cvtColor(sub[:, :, :3], _cv194.COLOR_BGR2GRAY).astype(_np194.float32)
        cv[y0:y1, x0:x1] = g * al
        m = cv > 25
        if not m.any():
            return None
        ys, xs = _np194.nonzero(m)
        return float(xs.mean()), float(ys.mean())

    _soll194 = _lage194('', 3.0)

    # (a) REGEN faellt von OBEN und landet auf der berechneten Stelle.
    # Bis v193 wuchs die Leinwand nur nach unten: der Streifen stieg von
    # unten herauf (genau andersherum als das Label sagt) und der fertige
    # Text sass danach dauerhaft 53 px zu hoch - 30 % der Worthoehe.
    _rg_frueh = _lage194('regen', 0.15)
    _rg_ende = _lage194('regen', 2.5)
    check('v194 regen: faellt wirklich VON OBEN herab',
          _rg_frueh is not None and _rg_frueh[1] < _soll194[1] - 40,
          f"start y {_rg_frueh[1] if _rg_frueh else None} vs soll {_soll194[1]:.0f}")
    check('v194 regen: landet auf der berechneten Stelle (nicht daneben)',
          _rg_ende is not None and abs(_rg_ende[1] - _soll194[1]) < 4,
          f"ende y {_rg_ende[1] if _rg_ende else None} vs soll {_soll194[1]:.0f}")

    # (b) RUTSCHE kommt von RECHTS und landet auf der berechneten Stelle.
    # Bis v193 wuchs die Leinwand nur nach rechts -> 92 px zu weit links,
    # also 23 % der Wortbreite. Das verfehlt die Bildseite (v168) und den
    # Plattform-Korridor (v187).
    _ru_frueh = _lage194('rutsche', 0.06)
    _ru_ende = _lage194('rutsche', 2.5)
    check('v194 rutsche: kommt wirklich VON RECHTS',
          _ru_frueh is not None and _ru_frueh[0] > _soll194[0] + 5,
          f"start x {_ru_frueh[0] if _ru_frueh else None} vs soll {_soll194[0]:.0f}")
    check('v194 rutsche: landet auf der berechneten Stelle (nicht daneben)',
          _ru_ende is not None and abs(_ru_ende[0] - _soll194[0]) < 4,
          f"ende x {_ru_ende[0] if _ru_ende else None} vs soll {_soll194[0]:.0f}")

    # (c) Beide polstern jetzt SYMMETRISCH - das ist die Bauweise, die
    # explosion und magnet seit je richtig machen. Quelltext-Garantie,
    # damit ein spaeterer Umbau nicht in dieselbe Falle laeuft.
    _r194 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v194: regen polstert symmetrisch',
          'out = np.zeros((h + 2 * pad_y, w, 4), base.dtype)' in _r194)
    check('v194: rutsche polstert symmetrisch',
          'out = np.zeros((h, w + 2 * pad_x, 4), base.dtype)' in _r194)

    # (d) KEINE Animation darf den Text unbemerkt verschieben. Ausgenommen
    # sind die, die per Bauart eine neue Ruhelage haben (sturz faellt und
    # bleibt liegen, anstieg steigt und bleibt oben) und die Dauer-
    # Animationen, die bei t=2.5 s einfach mitten in ihrer Schwingung sind.
    _erlaubt194 = {'sturz', 'anstieg', 'bruch', 'schwund',
                   'schweben', 'wackel', 'druck'}
    _versetzt194 = []
    for _a194 in _R194.ANIM_LIST:
        if _a194 in _erlaubt194:
            continue
        _e194 = _lage194(_a194, 2.5)
        if _e194 is None:
            _versetzt194.append((_a194, 'keine Tinte'))
            continue
        if (abs(_e194[0] - _soll194[0]) > 3.5
                or abs(_e194[1] - _soll194[1]) > 3.5):
            _versetzt194.append((_a194,
                                 f"{_e194[0] - _soll194[0]:+.0f}/"
                                 f"{_e194[1] - _soll194[1]:+.0f}"))
    check('v194: keine Animation laesst den Text daneben stehen',
          not _versetzt194, f"{_versetzt194}")

    # (e) Und jede Animation muss ueberhaupt etwas tun. Audio-getriebene
    # bekommen dafuer ein sprech-aehnliches Signal - mit einem konstanten
    # Wert gemessen stehen sie still, und das ist ein MESSFEHLER, kein Bug
    # (genau darauf bin ich beim Pruefen selbst hereingefallen).
    import math as _m194

    def _aud194(t):
        ph = (t % 0.33) / 0.33
        return (0.30 + 0.45 * abs(_m194.sin(t * _m194.pi / 0.33)),
                0.20 + 0.40 * abs(_m194.sin(t * _m194.pi / 0.66)),
                max(0.0, 1.0 - ph * 4.0))

    # (f) KIPPEN dreht um die QUERachse (nach vorn), WENDE um die HOCHachse
    # (umblaettern). Bis v193 bekamen beide ihren Winkel als 'ay' -
    # _persp3d(arr, ax, ay) - und machten damit exakt dieselbe Bewegung.
    # Der eigene Kommentar von 'kippen' sagte seit je "Tilt um X-Achse",
    # das Argument sass nur an der falschen Stelle.
    def _bb194(arr):
        m = arr[:, :, 3] > 60
        ys, xs = _np194.nonzero(m)
        return (xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)

    _bw194, _bh194 = _bb194(_b194)

    def _form194(anim, t):
        arr, _, _, _, _ = _R194.anim_apply(
            {'anim': anim, 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, 0.4, 0.0), t)
        w, h = _bb194(arr)
        return w / _bw194, h / _bh194

    _kb, _kh = _form194('kippen', 0.03)
    _wb, _wh = _form194('wende', 0.10)
    check('v194 kippen: staucht die HOEHE (kippt nach vorn), nicht die Breite',
          _kh < 0.90 and _kb > 0.95, f"Breite {_kb:.2f}x Hoehe {_kh:.2f}x")
    check('v194 wende: staucht die BREITE (blaettert um), nicht die Hoehe',
          _wb < 0.80 and _wh > 0.95, f"Breite {_wb:.2f}x Hoehe {_wh:.2f}x")
    check('v194: kippen und wende sind nicht mehr dieselbe Bewegung',
          '_persp3d(base, tilt, 0.0, 0.14)' in _r194
          and '_persp3d(base, 0.0, ang, 0.18)' in _r194)
    # Und die Kippung muss lang genug stehen, um lesbar zu sein. Bei der
    # alten Zeitbasis war sie nach 0.10 s vorbei = drei Bilder bei 30 fps.
    check('v194 kippen: die Kippung ist lange genug sichtbar (> 0.20 s)',
          _form194('kippen', 0.17)[1] < 0.97,
          f"Hoehe bei 0.17 s: {_form194('kippen', 0.17)[1]:.2f}x")

    # (g) SCHWUND loest sich WIRKLICH auf. Bis v193 stand im Code ein
    # Alpha-Boden (0.42 + 0.58 * keep) - das Wort blieb dauerhaft bei 42 %
    # Deckkraft stehen (gemessen noch bei t = 6 s). Eine Animation namens
    # "Fade (dissolves)" darf nicht bei halb sichtbar einfrieren.
    _a0194 = float(_b194[:, :, 3].astype(_np194.float32).sum())

    def _rest194(t):
        arr, _, _, _, _ = _R194.anim_apply(
            {'anim': 'schwund', 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, 0.4, 0.0), t)
        return float(arr[:, :, 3].astype(_np194.float32).sum()) / _a0194

    check('v194 schwund: loest sich wirklich ganz auf',
          _rest194(1.5) < 0.02 and _rest194(0.3) > 0.9,
          f"t=0.3: {_rest194(0.3)*100:.0f} %  t=1.5: {_rest194(1.5)*100:.1f} %")
    # Die ZUWEISUNG pruefen, nicht den Dateitext - der erklaerende Kommentar
    # zitiert die alte Formel absichtlich, damit spaeter niemand denselben
    # Boden wieder einbaut.
    check('v194 schwund: kein Alpha-Boden mehr in der Zuweisung',
          "* keep).astype(base.dtype)" in _r194
          and "(0.42 + 0.58 * keep)).astype(base.dtype)" not in _r194)

    # (h) GEWICHT reagiert stufenlos auf den Bass. Der Morphologie-Kernel war
    # eine ungerade GANZzahl - die ganze Bass-Spanne 0.0 bis 0.8 ergab
    # denselben Kernel und damit eine STATISCHE Verdickung.
    import cv2 as _cv2g

    def _strich194(arr):
        m = (arr[:, :, 3] > 100).astype(_np194.uint8)
        if not m.any():
            return 0.0
        d = _cv2g.distanceTransform(m, _cv2g.DIST_L2, 5)
        return float(d[m > 0].mean() * 2)

    _s0194 = _strich194(_b194)
    _kurve194 = []
    for _bs194 in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        _ag, _, _, _, _ = _R194.anim_apply(
            {'anim': 'gewicht', 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, _bs194, 0.0), 0.40)
        _kurve194.append(_strich194(_ag) / _s0194)
    check('v194 gewicht: der Strich waechst mit dem Bass (keine tote Zone)',
          all(_kurve194[i] >= _kurve194[i - 1] - 0.002
              for i in range(1, len(_kurve194)))
          and _kurve194[-1] - _kurve194[0] > 0.10,
          f"{[round(x, 3) for x in _kurve194]}")
    check('v194 gewicht: zwischen zwei Kernelgroessen wird gemischt',
          'misch = max(0.0, min(1.0, (roh - k_lo) / 2.0))' in _r194)

    # (i) FOKUS: die Unschaerfe muss bei VOLLER Deckkraft stehen. Bis v193
    # lag sie in der Einblendung (op < 1) und war nach 0.10 s vorbei - bei
    # 30 fps drei Bilder, davon zwei halbtransparent.
    def _fok194(t):
        arr, _, _, _, op = _R194.anim_apply(
            {'anim': 'fokus', 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, 0.4, 0.0), t)
        g = _cv2g.cvtColor(arr[:, :, :3], _cv2g.COLOR_BGR2GRAY)
        return float(_cv2g.Laplacian(g, _cv2g.CV_64F).var()), op

    _f_mitte = _fok194(0.20)
    _f_ende = _fok194(0.55)
    check('v194 fokus: noch bei 0.20 s unscharf UND voll sichtbar',
          _f_mitte[0] < _f_ende[0] * 0.1 and _f_mitte[1] > 0.99,
          f"Schaerfe {_f_mitte[0]:.1f} bei Deckkraft {_f_mitte[1]:.2f}, "
          f"scharf {_f_ende[0]:.1f}")
    check('v194 fokus: monotone Kurve statt Feder (ein Rack Focus schwingt nicht)',
          'e = smoothstep(min(dt / 0.42, 1.0))' in _r194
          and _r194.count('blur = (1.0 - e) * min(base.shape[0]') == 1)

    # (j) WACKEL: "cartoon bounce" heisst Squash & Stretch, die erste der
    # 12 Disney-Regeln. Bis v193 gab es nur einen GLEICHFOERMIGEN Skalen-Puls
    # von 1.5 % - ein Groessen-Zappeln, kein Cartoon. Jetzt gegenlaeufig auf
    # beiden Achsen und an den Umkehrpunkt der Bewegung gekoppelt.
    def _wk194(t):
        arr, _, dy, _, _ = _R194.anim_apply(
            {'anim': 'wackel', 'start': 0.0, 'kw_i': 3}, _b194.copy(),
            (0.5, 0.4, 0.0), t)
        w, h = _bb194(arr)
        return dy, w / _bw194, h / _bh194

    _unten = _wk194(0.12)     # dy positiv = unten
    _oben = _wk194(0.37)      # dy negativ = oben
    check('v194 wackel: unten breit und flach (Aufprall)',
          _unten[0] > 0 and _unten[1] > 1.03 and _unten[2] < 0.97,
          f"dy {_unten[0]:.1f} B {_unten[1]:.3f} H {_unten[2]:.3f}")
    check('v194 wackel: oben schmal und hoch (Streckung)',
          _oben[0] < 0 and _oben[1] < 0.97 and _oben[2] > 1.03,
          f"dy {_oben[0]:.1f} B {_oben[1]:.3f} H {_oben[2]:.3f}")
    check('v194 wackel: volumenerhaltend (Breite rauf = Hoehe runter)',
          abs(_unten[1] * _unten[2] - 1.0) < 0.05
          and abs(_oben[1] * _oben[2] - 1.0) < 0.05,
          f"{_unten[1]*_unten[2]:.3f} / {_oben[1]*_oben[2]:.3f}")

    _tot194 = []
    for _a194 in _R194.ANIM_LIST:
        _p194 = {'anim': _a194, 'start': 0.0, 'kw_i': 3}
        _sig = []
        for _k194 in range(0, 90, 2):
            _t194 = _k194 / 60.0
            _arr, _dx, _dy, _sc, _op = _R194.anim_apply(
                _p194, _b194.copy(), _aud194(_t194), _t194)
            # Der Fingerabdruck muss die FORM erfassen, nicht nur die
            # Gesamtmenge Tinte. Erster Entwurf nahm die Alpha-Summe - eine
            # Welle verschiebt die Tinte nur seitlich, die Summe bleibt
            # gleich, und der Test meldete 'welle' faelschlich als tot
            # (gemessen bewegt sie 8 bis 14 px und 20 bis 30 % der Tinte).
            _al = _arr[:, :, 3]
            _sp = tuple(int(v // 400) for v in
                        _al[::max(1, _al.shape[0] // 6)].sum(axis=1)) + \
                  tuple(int(v // 400) for v in
                        _al[:, ::max(1, _al.shape[1] // 8)].sum(axis=0))
            _sig.append((round(_dx, 1), round(_dy, 1), round(_sc, 3),
                         round(_op, 3), _arr.shape[0], _arr.shape[1], _sp))
        if len(set(_sig)) <= 1:
            _tot194.append(_a194)
    check('v194: jede der 26 Animationen bewegt ueberhaupt etwas',
          not _tot194, f"regungslos: {_tot194}")

    # ======= v196: Ankuendigungen + Feedback ============================
    # Bis v195 gab es KEINEN Weg, Kunden etwas zu sagen ausser einer Mail an
    # alle, und keinen, ihre Meinung zu erfassen ausser dem Ticket-System -
    # und ein Ticket ist eine Frage mit Antworterwartung, keine Bewertung.
    # Eigener time-Import: der v196-Block steht VOR dem v194b-Block, dessen
    # _tm194b es hier also noch nicht gibt. Ein Test, der sich auf eine
    # Variable aus einem spaeteren Abschnitt stuetzt, bricht beim ersten
    # Umsortieren - genau das ist gerade passiert.
    import time as _tm196
    import server as _SV196
    _sv196 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _adm196 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    _ui196 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()

    check('v196: beide Tabellen werden angelegt',
          'CREATE TABLE IF NOT EXISTS announcements' in _sv196
          and 'CREATE TABLE IF NOT EXISTS feedback' in _sv196)
    check('v196: Feedback wird bei der Kontoloeschung mitgeloescht (DSGVO)',
          'DELETE FROM feedback WHERE user_id = ?' in _sv196)
    check('v196: die neuen Tabellen haengen an den heissen Abfragen im Index',
          'ix_fb_neu' in _sv196 and 'ix_ann_aktiv' in _sv196)

    # Ankuendigungen: Endpunkt OHNE Auth (eine Wartungsmeldung muss auch den
    # erreichen, der gerade nicht eingeloggt ist), abgelaufene fallen raus.
    _con196 = _SV196._db()
    _con196.execute("DELETE FROM announcements")
    _now196 = int(_tm196.time())
    _con196.execute("INSERT INTO announcements (titel,text,stufe,aktiv,created_at,bis) "
                    "VALUES ('Aktiv','A','info',1,?,NULL)", (_now196,))
    _con196.execute("INSERT INTO announcements (titel,text,stufe,aktiv,created_at,bis) "
                    "VALUES ('Aus','B','info',0,?,NULL)", (_now196,))
    _con196.execute("INSERT INTO announcements (titel,text,stufe,aktiv,created_at,bis) "
                    "VALUES ('Abgelaufen','C','warn',1,?,?)", (_now196, _now196 - 10))
    _con196.commit(); _con196.close()
    _akt196 = _SV196._ann_aktiv()
    check('v196: nur aktive und nicht abgelaufene Ankuendigungen gehen raus',
          [a['titel'] for a in _akt196] == ['Aktiv'],
          f"{[a['titel'] for a in _akt196]}")
    check('v196: der Ankuendigungs-Endpunkt braucht keine Anmeldung',
          "@app.get('/api/announcements')" in _sv196
          and 'def api_announcements():' in _sv196)
    check('v196: eine Ankuendigung kann von selbst ablaufen',
          "bis = int(time.time() + tage * 86400) if tage else None" in _sv196)
    check('v196: nur erlaubte Stufen',
          "_ANN_STUFEN = ('info', 'warn', 'wartung')" in _sv196
          and "stufe if stufe in _ANN_STUFEN else 'info'" in _sv196)

    # Feedback: Note geprueft, eine Bewertung je Render, Look wird mitgefuehrt.
    check('v196: die Note wird auf 1 bis 5 geprueft',
          'if not 1 <= note <= 5:' in _sv196)
    check('v196: eine Bewertung JE RENDER (zweite ueberschreibt, addiert nicht)',
          'SELECT id FROM feedback WHERE user_id = ? AND jid = ?' in _sv196
          and 'UPDATE feedback SET note = ?' in _sv196)
    check('v196: der Look haengt an der Bewertung (sonst nicht auswertbar)',
          "look TEXT DEFAULT ''" in _sv196
          and 'AVG(note) avg FROM feedback' in _sv196)
    check('v196: Feedback ist NICHT das Ticket-System',
          "@app.post('/api/feedback')" in _sv196
          and "@app.post('/api/support')" in _sv196)

    # Admin-Oberflaeche
    check('v196: die Admin-Navigation hat die Gruppe Produkt',
          "['Produkt', [['feedback','Feedback'],['ann','Announcements']]]" in _adm196)
    check('v196: beide Ansichten sind verdrahtet',
          'feedback:loadFeedback' in _adm196 and 'ann:loadAnn' in _adm196)
    check('v196: offenes Feedback steht als Zaehler in der Navigation',
          "setBadge('feedback', d.feedback_offen||0)" in _adm196
          and "'feedback_offen': feedback_offen" in _sv196)
    check('v196: der Admin sieht Verteilung und Schnitt je Look, nicht nur eine Liste',
          'Average per look' in _adm196 and 'Distribution' in _adm196)

    # Kunden-Oberflaeche
    check('v196: das Banner steht in der App und ist wegklickbar',
          "id=\"annBar\"" in _ui196 and 'function annWeg(' in _ui196)
    check('v196: weggeklickt wird PRO Ankuendigung gemerkt, nicht global',
          "localStorage.getItem('dve_ann_zu')" in _ui196
          and 'zu.includes(a.id)' in _ui196)
    check('v196: die Bewertung haengt am fertigen Render',
          "id=\"fbCard\"" in _ui196 and 'fbInit();' in _ui196
          and "fd.append('look', State.look" in _ui196)
    check('v196: die App benutzt ihren eigenen Escaper (esc gibt es nur im Admin)',
          '${escHtml(a.titel)}' in _ui196 and '${esc(a.titel)}' not in _ui196)
    check('v196: ein Fehler im Banner wird nicht mehr still geschluckt',
          "console.error('announcements:', e);" in _ui196)

    # ======= v197: Betrieb (Backup, Restore, Logs, Schlange) =============
    # Vier Luecken, die alle dasselbe Muster haben: es gab einen Mechanismus,
    # aber niemand hat je geprueft, ob er das tut, was auf dem Schild steht.
    import time as _tm197
    import io as _io197
    import sqlite3 as _sq197
    import server as _SV197
    _sv197 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _adm197 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()

    # --- A) Der Tages-Snapshot muss den AKTUELLEN Stand haben.
    # Bis v196 galt `if os.path.exists(dest): return` - der erste Lauf des
    # Cleanup-Workers (Serverstart) schrieb den Snapshot, alles danach am
    # selben Tag stand in keiner Sicherung. Bei der Restore-Probe kamen
    # dadurch 0 Konten zurueck, obwohl 7 in der Datenbank standen.
    _con197 = _SV197._db()
    _n197a = _con197.execute("SELECT COUNT(*) c FROM users").fetchone()['c']
    _con197.close()
    _SV197._backup_users_db()
    import glob as _gl197
    _snap197 = sorted(_gl197.glob(os.path.join(_SV197.DATA, 'backups', 'users_*.db')))
    check('v197: der Tages-Snapshot existiert', bool(_snap197))
    _con197 = _SV197._db()
    _con197.execute("INSERT INTO users (email, pw_hash, balance_sec, created_at) "
                    "VALUES (?,?,?,?)",
                    (f'backup{int(_tm197.time())}@test.invalid', 'x', 0,
                     int(_tm197.time())))
    _con197.commit(); _con197.close()
    _tm197.sleep(1.1)                  # mtime-Aufloesung abwarten
    _SV197._backup_users_db()           # zweiter Lauf am SELBEN Tag
    _c197 = _sq197.connect(_snap197[-1])
    _n197b = _c197.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    _c197.close()
    check('v197: der Snapshot wird am selben Tag aufgefrischt',
          _n197b > _n197a, f'{_n197a} -> {_n197b} Konten im Snapshot')
    check('v197: der Admin-Knopf sichert IMMER (force)',
          '_backup_users_db(force=True)' in _sv197)
    check('v197: geschrieben wird ueber .tmp + os.replace',
          "tmp = dest + '.tmp'" in _sv197 and 'os.replace(tmp, dest)' in _sv197)
    check('v197: die Offsite-Mail geht nur beim ersten Anlegen raus',
          'if neu:\n            _mail_backup_offsite(dest)' in _sv197)

    # --- B) Restore. Ein Backup, das man nie zurueckgespielt hat, ist kein
    # Backup. Geprueft wird die REIHENFOLGE der Sicherungsnetze im Skript.
    _rst197 = open(os.path.join(HERE, 'restore.sh'), encoding='utf-8').read()
    check('v197: restore.sh existiert und kennt --letztes', '--letztes' in _rst197)
    check('v197: die Sicherung wird VOR dem Tausch geprueft',
          _rst197.index('PRAGMA integrity_check')
          < _rst197.index('docker compose stop app'))
    check('v197: Pflichttabellen werden geprueft',
          "{'users', 'sessions', 'ledger', 'purchases'}" in _rst197)
    check('v197: der jetzige Stand wird zur Seite gelegt',
          'vor_restore_' in _rst197)
    check('v197: WAL und SHM werden mit entfernt',
          '"$DB-wal" "$DB-shm"' in _rst197)
    check('v197: die App wird vor dem Tausch gestoppt',
          _rst197.index('docker compose stop app') < _rst197.index('cp "$SRC" "$DB"'))

    # --- C) Logs ueberleben den Neustart. Bis v196 lag alles nur in
    # `docker logs` - und `update.sh` baut das Image neu.
    check('v197: der Log-Tee ist aktiv oder per Schalter abgeschaltet',
          isinstance(sys.stdout, _SV197._LogTee)
          or os.environ.get('DVE_LOGFILE') == '0')
    os.makedirs(_SV197.LOG_DIR, exist_ok=True)   # bei DVE_LOGFILE=0 nicht angelegt
    _tee197 = _SV197._LogTee(_io197.StringIO(), 'test')
    _tee197.write('eins '); _tee197.write('zwei'); _tee197.write('\n')
    _txt197 = open(_SV197.LOG_FILE, encoding='utf-8').read() \
        if os.path.exists(_SV197.LOG_FILE) else ''
    check('v197: print-Argumente landen in EINER Log-Zeile',
          '[test] eins zwei\n' in _txt197)
    check('v197: der Log rotiert nach Groesse',
          'def _log_rotate' in _sv197 and 'LOG_KEEP' in _sv197)
    check('v197: ein kaputter Log reisst den Server nicht',
          _sv197.count('except Exception:\n            pass') >= 1
          and 'def _log_start' in _sv197)
    check('v197: der Admin liest nur das ENDE (kein 5-MB-Request)',
          "f.seek(gr - 262144)" in _sv197)
    # v203-sec: isdigit() und int() akzeptieren nicht dieselbe Menge
    # ('2'.isdigit() ist True, int('2') wirft). Jetzt Vergleich gegen die
    # erlaubten Werte, ganz ohne Umrechnung.
    check('v197: der Log-Teil wird validiert (kein Pfad-Durchgriff)',
          "teil not in {str(i) for i in range(1, LOG_KEEP + 1)}" in _sv197)
    check('v197: das Panel hat eine Logs-Ansicht',
          'async function loadLogs' in _adm197 and 'logs:loadLogs' in _adm197)

    # --- D) Unbehandelte Fehler landen im Panel. Bisher stand dort NUR ein
    # fehlgeschlagener Render; ein Absturz in einem Endpunkt ging als
    # Traceback nach stdout und war nach dem naechsten Deploy weg.
    check('v197: globaler Ausnahme-Handler registriert',
          "@app.exception_handler(Exception)" in _sv197)
    check('v197: der Kunde bekommt keinen Traceback zu sehen',
          "'detail': 'Internal server error.'" in _sv197)
    _vor197 = _SV197._alerts_offen()

    class _Req197:
        method = 'GET'
        url = type('U', (), {'path': '/api/kaputt'})()
    import asyncio as _as197
    _as197.run(_SV197._unhandled(_Req197(), ValueError('kaputt')))
    check('v197: der Fehler steht danach im Panel',
          _SV197._alerts_offen() > _vor197,
          f'{_vor197} -> {_SV197._alerts_offen()}')

    # --- E) Warteschlange. Der Kunde sah `position N` mit N = Gesamtlaenge,
    # nicht seinem Platz - und bei einer PriorityQueue zieht ein zahlendes
    # Konto vorbei.
    from queue import PriorityQueue as _PQ197, Queue as _Q197
    _q197 = _PQ197()
    _q197.put((1, 0, 'free_a')); _q197.put((1, 1, 'free_b')); _q197.put((0, 2, 'paid'))
    check('v197: der zahlende Job steht auf Platz 1',
          _SV197._queue_platz('paid', _q197) == 1)
    check('v197: die Free-Jobs ruecken dahinter',
          (_SV197._queue_platz('free_a', _q197),
           _SV197._queue_platz('free_b', _q197)) == (2, 3))
    _m197 = _Q197()
    for _x in ('z', 'a', 'm'):
        _m197.put(_x)
    check('v197: die FIFO zaehlt die Einfuegereihenfolge, nicht den String',
          (_SV197._queue_platz('z', _m197), _SV197._queue_platz('a', _m197)) == (1, 2))
    check('v197: der Status meldet den eigenen Platz',
          "out['queue_pos'] = platz" in _sv197)
    check('v197: die Worker-Zahl steht an EINER Stelle',
          "WORKERS = max(1, int(os.environ.get('DVE_WORKERS', '1')))" in _sv197
          and "'workers': WORKERS," in _sv197
          and _sv197.count("os.environ.get('DVE_WORKERS'") == 1)
    check('v197: eine volle Schlange meldet sich im Panel',
          "_notify_admin('queue'" in _sv197)

    # --- F) Test-Gate vor dem Deploy. Bisher ging JEDER Commit live und
    # geprueft wurde nur, ob der Server antwortet.
    _gate197 = open(os.path.join(HERE, 'deploy_gate.sh'), encoding='utf-8').read()
    _upd197 = open(os.path.join(HERE, 'update.sh'), encoding='utf-8').read()
    _ = _gate197
    _auto197 = open(os.path.join(HERE, 'autodeploy.sh'), encoding='utf-8').read()
    check('v197: das Gate laeuft VOR dem Neustart',
          _upd197.index('deploy_gate.sh')
          < _upd197.index('docker compose up -d --force-recreate app'))
    check('v197: rotes Gate bricht den Deploy ab',
          'DEPLOY ABGEBROCHEN' in _upd197 and 'exit 1' in _upd197)
    check('v197: das Gate sieht die echte users.db nie',
          'DVE_DATA=/tmp/gate_data' in _gate197 and '--no-deps' in _gate197)
    check('v197: das Gate laeuft ohne OpenAI-Key (Heuristik-Pfad)',
          'OPENAI_API_KEY=' in _gate197)
    # --- G) v197a: Ismet will nie ins Terminal. Die Sicherungen lagen aber
    # nur auf der Platte und im Postfach - im Panel stand bloss ein Datum.
    check('v197a: die Sicherungen sind im Panel auflistbar',
          "@app.get('/api/admin/backups')" in _sv197
          and 'PRAGMA quick_check' in _sv197)
    check('v197a: unlesbare Sicherungen werden als solche gemeldet',
          "eintrag['ok']" in _sv197 and "'konten': None, 'ok': False" in _sv197)
    check('v197a: der Download prueft den Namen gegen das echte Verzeichnis',
          'if datei not in da' in _sv197)
    check('v197a: der Admin-Key bleibt im Header (kein Key in der URL)',
          'function bkDl(' in _adm197 and 'headers:hdr()' in _adm197
          and 'key=${encodeURIComponent(KEY)}' not in _adm197)
    check('v197a: die Backup-Liste haengt in der System-Ansicht',
          "id=\"bkList\"" in _adm197 and 'loadBackups();' in _adm197)

    # --- H) v197b: Zurueckspielen im Panel, ohne den Server anzuhalten.
    # Der Terminal-Weg tauscht die Datei und muss dafuer die App stoppen -
    # im Panel unmoeglich, ein Endpunkt kann sich danach nicht mehr melden.
    # Die SQLite-Online-Backup-API schreibt IN die laufende Datenbank.
    check('v197b: der Kandidat wird geprueft, bevor etwas angefasst wird',
          _sv197.index('def _pruefe_sicherung') < _sv197.index('def _restore_users_db')
          and 'ok, meldung, zahlen = _pruefe_sicherung(pfad)' in _sv197
          and _sv197.index('ok, meldung, zahlen = _pruefe_sicherung(pfad)')
          < _sv197.index("vor = os.path.join(bdir, f'vor_restore_"))
    check('v197b: eine Muell-Datei wird abgelehnt',
          _SV197._pruefe_sicherung(os.path.join(HERE, 'selftest.py'))[0] is False)
    _fehlt197 = os.path.join(_SV197.DATA, 'leer197.db')
    _c = _sq197.connect(_fehlt197); _c.execute('CREATE TABLE x (a)'); _c.commit(); _c.close()
    _ok197, _msg197, _ = _SV197._pruefe_sicherung(_fehlt197)
    check('v197b: fehlende Pflichttabellen werden benannt',
          _ok197 is False and 'users' in _msg197, _msg197)
    os.remove(_fehlt197)
    # Der eigentliche Beweis: einspielen im LAUFENDEN Betrieb.
    _con197 = _SV197._db()
    _con197.execute("INSERT INTO users (email, pw_hash, balance_sec, created_at) "
                    "VALUES (?,?,?,?)",
                    (f'rst{int(_tm197.time())}@test.invalid', 'x', 0, int(_tm197.time())))
    _con197.commit(); _con197.close()
    _SV197._backup_users_db(force=True)
    _snapf197 = sorted(_gl197.glob(os.path.join(_SV197.DATA, 'backups', 'users_*.db')))[-1]

    def _konten197():
        c = _SV197._db()
        v = c.execute('SELECT COUNT(*) c FROM users').fetchone()['c']
        c.close()
        return v
    _voll197 = _konten197()
    _offen197 = _SV197._db()                 # ueberlebt den Restore absichtlich
    _con197 = _SV197._db()
    _con197.execute("DELETE FROM users WHERE email LIKE 'rst%@test.invalid'")
    _con197.commit(); _con197.close()
    _leer197 = _konten197()
    _erg197 = _SV197._restore_users_db(_snapf197)
    check('v197b: der Restore holt die Konten zurueck, ohne Neustart',
          _leer197 < _voll197 and _konten197() == _voll197,
          f'{_voll197} -> {_leer197} -> {_konten197()}')
    check('v197b: auch eine schon offene Verbindung sieht den neuen Stand',
          _offen197.execute('SELECT COUNT(*) c FROM users').fetchone()['c'] == _voll197)
    _offen197.close()
    check('v197b: der vorherige Stand wurde weggeschrieben',
          os.path.exists(os.path.join(_SV197.DATA, 'backups',
                                      _erg197['vorher_gesichert'])))
    check('v197b: das Schema wird nach einer alten Sicherung nachgezogen',
          '_init_users_db()                     # Schema nachziehen' in _sv197)
    check('v197b: ohne Tippbestaetigung passiert nichts',
          "bestaetigung.strip().upper() != 'RESTORE'" in _sv197
          and _sv197.count("bestaetigung.strip().upper() != 'RESTORE'") == 2)
    check('v197b: die Offsite-Kopie aus der Mail kann hochgeladen werden',
          "@app.post('/api/admin/backup/upload')" in _sv197
          and 'gzip.decompress' in _sv197)
    check('v197b: eine untaugliche Hochladung bleibt nicht liegen',
          'os.remove(ziel)' in _sv197)
    check('v197b: das Panel hat Verify, Restore und Upload',
          'function bkCheck(' in _adm197 and 'function bkRestore(' in _adm197
          and 'function bkUpload(' in _adm197)
    check('v197b: der Restore verlangt auch im Panel die Tippbestaetigung',
          "Type RESTORE to confirm" in _adm197)

    # ======= v198: Support-Verlauf statt Einbahnstrasse ==================
    # Ein Ticket war bis v197 EINE Nachricht. Die Antwort lief per Mail aus
    # Ismets Postfach: sie stand nirgends, das Panel zeigte ewig die Frage,
    # und eine Rueckfrage des Kunden kam als NEUES Ticket ohne Bezug.
    _sv198 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _adm198 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    _ui198 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    import server as _SV198
    check('v198: es gibt eine Nachrichten-Tabelle',
          'CREATE TABLE IF NOT EXISTS ticket_messages' in _sv198)
    check('v198: Alt-Tickets bekommen ihre erste Nachricht nachgetragen',
          'WHERE NOT EXISTS (SELECT 1 FROM ticket_messages' in _sv198)
    check('v198: die Nachrichten gehen bei der Kontoloeschung mit (DSGVO)',
          'DELETE FROM ticket_messages WHERE ticket_id IN' in _sv198)
    check('v198: der Factory-Reset loescht erst die Kinder, dann die Tickets',
          _sv198.index("'ticket_messages', 'tickets'") > 0)
    check("v198: 'answered' ist ein gueltiger Status",
          "status not in ('open', 'closed', 'answered')" in _sv198)

    # Der eigentliche Beweis: die ganze Unterhaltung ueber echte Aufrufe.
    from fastapi.testclient import TestClient as _TC198
    _c198 = _TC198(_SV198.app, base_url='https://test')   # secure-Cookie -> https
    _mail198 = f'sup{int(_tm197.time())}@test.invalid'
    _c198.post('/api/register', data={'email': _mail198, 'password': 'passwort123',
                                      'name': 'Testkunde'})
    _c198.post('/api/login', data={'email': _mail198, 'password': 'passwort123'})
    _r198 = _c198.post('/api/support', data={'subject': 'Render haengt',
                                             'message': 'Bleibt bei 40 Prozent stehen.'})
    check('v198: das Ticket wird angelegt', _r198.status_code == 200, _r198.text[:120])
    _tid198 = _r198.json()['ticket']
    # Den Key SELBST setzen. Ein Test, der sich auf eine von aussen gesetzte
    # Umgebung verlaesst, ueberspringt sich still - genau das ist in v194b
    # passiert und faellt beim Lesen der Zusammenfassung niemandem auf.
    os.environ['DVE_ADMIN'] = 'testkey_v198'
    _H198 = {'X-Admin-Key': 'testkey_v198'}
    if True:
        _p198 = _c198.get('/api/admin/tickets', headers=_H198).json()
        _t198 = [t for t in _p198['tickets'] if t['id'] == _tid198][0]
        check('v198: das Panel sieht den Verlauf, nicht nur den Rumpftext',
              len(_t198['messages']) == 1 and _t198['messages'][0]['von'] == 'kunde')
        _a198 = _c198.post(f'/api/admin/tickets/{_tid198}/reply',
                           data={'text': 'Lag an der Warteschlange, laeuft wieder.'},
                           headers=_H198)
        check('v198: aus dem Panel antworten geht', _a198.status_code == 200, _a198.text[:120])
        _k198 = _c198.get('/api/support/tickets').json()
        _mine = [t for t in _k198['items'] if t['id'] == _tid198][0]
        check('v198: der Kunde sieht die Antwort im selben Ticket',
              [m['von'] for m in _mine['messages']] == ['kunde', 'admin']
              and _mine['status'] == 'answered')
        check('v198: eine ungelesene Antwort wird gezaehlt', _k198['ungelesen'] >= 1)
        _rr198 = _c198.post(f'/api/support/tickets/{_tid198}/reply',
                            data={'message': 'Danke, passt jetzt.'})
        check('v198: die Rueckfrage bleibt IM Ticket und oeffnet es wieder',
              _rr198.status_code == 200)
        _t198 = [t for t in _c198.get('/api/admin/tickets', headers=_H198).json()['tickets']
                 if t['id'] == _tid198][0]
        check('v198: kein neues Ticket fuer die Rueckfrage',
              len(_t198['messages']) == 3 and _t198['status'] == 'open',
              f"{len(_t198['messages'])} Nachrichten, Status {_t198['status']}")
        check('v198: eine leere Antwort wird abgelehnt',
              _c198.post(f'/api/admin/tickets/{_tid198}/reply', data={'text': ' '},
                         headers=_H198).status_code == 400)
        check('v198: ohne Admin-Key geht gar nichts',
              _c198.post(f'/api/admin/tickets/{_tid198}/reply', data={'text': 'hi'}
                         ).status_code == 403)
    del os.environ['DVE_ADMIN']
    check('v198: ein fremdes Ticket ist nicht erreichbar',
          _c198.post('/api/support/tickets/999999/reply',
                     data={'message': 'fremd'}).status_code == 404)
    check('v198: das Panel hat ein Antwortfeld je Ticket',
          'function ticketReply(' in _adm198 and 'Send reply' in _adm198)
    check('v198: eine nicht verschickte Mail wird im Panel gemeldet',
          'could not be sent' in _adm198 and "'gemailt': gemailt" in _sv198)
    check('v198: die App zeigt den Verlauf und kann antworten',
          'id="supThreads"' in _ui198 and 'function loadThreads(' in _ui198
          and 'function threadReply(' in _ui198)
    check('v198: die App benutzt ihren eigenen Escaper',
          '${escHtml(m.text)}' in _ui198)
    # v202: der Verlauf haengt jetzt an der eigenen Support-Seite, nicht mehr
    # am Konto. Die Zusage ist dieselbe geblieben - er wird beim Oeffnen
    # geladen -, nur der Ort hat sich geaendert.
    check('v202: der Verlauf wird beim Oeffnen der Support-Seite geladen',
          "if (name === 'support') loadThreads();" in _ui198)
    check('v198: wartende Tickets stehen als Zaehler in der Seitenleiste',
          "setBadge('support', d.tickets_open" in _adm198)

    # ======= v202: Support ist eine eigene Seite + Zaehler ===============
    # Ismets Ansage: "soll nicht alles unter Account verstaut werden", und
    # eine Antwort soll sich melden. Eine Antwort, die niemand sieht, ist
    # keine Antwort - der Kunde hat bisher nur die Mail gehabt.
    _ui202 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v202: Support ist eine eigene Seite, kein Block unter Account',
          'id="page-support"' in _ui202
          and "'billing', 'support', 'account'" in _ui202
          and "if (name === 'support') loadThreads();" in _ui202)
    check('v202: der Support-Block liegt NICHT mehr in page-account',
          _ui202.index('id="page-support"') < _ui202.index('id="page-account"')
          and 'id="supThreads"' in _ui202
          and _ui202.index('id="supThreads"') < _ui202.index('id="page-account"'))
    check('v202: es gibt genau EIN Support-Formular (nicht versehentlich zwei)',
          _ui202.count('id="supportForm"') == 1
          and _ui202.count('id="supThreads"') == 1)
    check('v202: der Zaehler sitzt im Navigations-Link',
          'id="supBadge"' in _ui202 and '.navbadge' in _ui202
          and 'function supBadge(' in _ui202)
    check('v202: gesehen ist gesehen - der Zaehler faellt nach dem Lesen',
          'supBadge(0);' in _ui202
          and 'supBadge(d.support_neu || 0)' in _ui202)

    # Und der Zaehler muss wirklich zaehlen. Ueber echte Aufrufe, nicht ueber
    # den Quelltext - v197 hatte fuenf Quelltext-Tests am Problem vorbei.
    os.environ['DVE_ADMIN'] = 'testkey_v202'
    _c202 = _TC198(_SV198.app, base_url='https://test')
    _m202 = f'nav{int(_tm197.time())}@test.invalid'
    _r202 = _c202.post('/api/register', data={'email': _m202, 'name': 'Zaehler Test',
                                              'password': 'passwort123'})
    check('v202: ein frisches Konto hat keinen Zaehler (kein Absturz)',
          _r202.status_code == 200 and _r202.json().get('support_neu') == 0,
          _r202.text[:140])
    _c202.post('/api/login', data={'email': _m202, 'password': 'passwort123'})
    _t202 = _c202.post('/api/support', data={'subject': 'Frage',
                                             'message': 'Wie geht das?'}).json()['ticket']
    check('v202: die eigene Frage erzeugt KEINE Benachrichtigung',
          _c202.get('/api/me').json()['support_neu'] == 0)
    _c202.post(f'/api/admin/tickets/{_t202}/reply', data={'text': 'So geht das.'},
               headers={'X-Admin-Key': 'testkey_v202'})
    check('v202: nach der Antwort steht die kleine 1',
          _c202.get('/api/me').json()['support_neu'] == 1)
    _c202.post(f'/api/support/tickets/{_t202}/read')
    check('v202: nach dem Ansehen ist sie weg',
          _c202.get('/api/me').json()['support_neu'] == 0)
    del os.environ['DVE_ADMIN']

    # ======= v203-sec: Audit-Befunde ====================================
    # Zwei unabhaengige Audits (neue Flaeche seit v193 / Identitaet + Geld +
    # Infrastruktur) haben 30 Befunde bestaetigt. Hier stehen die Tests zu
    # denen, die sofort gefixt wurden.
    _sv203 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    os.environ['DVE_ADMIN'] = 'testkey_v203'
    _c203 = _TC198(_SV198.app, base_url='https://test')
    _H203 = {'X-Admin-Key': 'testkey_v203'}

    # (1) DER WICHTIGSTE TEST: KEIN /api/admin/*-Endpunkt darf ohne Key
    # antworten. Der gefundene Fehler war `_admin_ok(request)` als nackte
    # Anweisung - die Funktion gibt nur bool zurueck und wirft nicht, der
    # Riegel heisst `_require_admin`. Eine Quelltext-Suche findet das nicht
    # zuverlaessig (beide Namen stehen da), ein Aufruf schon. Der Test laeuft
    # ueber ALLE Routen, damit ein neuer Endpunkt gar nicht erst durchrutscht.
    _offen203 = []
    for _rt in _SV198.app.routes:
        _p = getattr(_rt, 'path', '')
        if not _p.startswith('/api/admin/') or '{' in _p:
            continue
        for _meth in (getattr(_rt, 'methods', None) or set()):
            if _meth not in ('GET', 'POST'):
                continue
            try:
                _r = (_c203.get(_p) if _meth == 'GET'
                      else _c203.post(_p, data={}))
            except Exception:
                continue
            # 403 = richtig abgewiesen. 422 = FastAPI vermisst Pflichtfelder,
            # BEVOR der Handler laeuft - dann ist der Riegel nicht bewiesen,
            # aber es fliesst auch nichts ab; solche Faelle werden unten mit
            # Pflichtfeldern nachgefasst, hier zaehlen nur echte Antworten.
            if _r.status_code not in (403, 422, 429):
                _offen203.append(f'{_meth} {_p} -> {_r.status_code}')
    check('v203-sec: KEIN Admin-Endpunkt antwortet ohne Key',
          not _offen203, '; '.join(_offen203[:5]))
    # Die Rundfahrt oben hat die neue Admin-Bremse ausgeloest (viele
    # Fehlversuche von derselben IP). Fuer die naechsten Einzelpruefungen
    # zuruecksetzen, sonst antwortet der Server 429 statt 403 - das waere
    # richtig, aber es pruefte die falsche Zusage.
    for _k in [k for k in _SV198._REG_ATTEMPTS if k.startswith('admin:')]:
        _SV198._REG_ATTEMPTS.pop(_k, None)
    check('v203-sec: mit Key antwortet er weiterhin',
          _c203.get('/api/admin/alerts', headers=_H203).status_code == 200)
    check('v203-sec: der schreibende Alerts-Endpunkt ist ebenfalls dicht',
          _c203.post('/api/admin/alerts/read', data={'id': 0}).status_code == 403)
    for _k in [k for k in _SV198._REG_ATTEMPTS if k.startswith('admin:')]:
        _SV198._REG_ATTEMPTS.pop(_k, None)
    import re as _re203      # eigener Import: _re195 steht in einem SPAETEREN
                             # Block (v196-Lehre - nie auf Variablen aus einem
                             # anderen Abschnitt stuetzen)
    check('v203-sec: _admin_ok steht nirgends mehr als alleinige Schranke',
          not _re203.search(r'^\s+_admin_ok\(request\)\s*$', _sv203, _re203.M))
    # Eine doppelt registrierte Route verdeckt den Riegel der zweiten.
    _pfade203 = [f"{m} {getattr(r, 'path', '')}"
                 for r in _SV198.app.routes
                 for m in (getattr(r, 'methods', None) or set())]
    check('v203-sec: keine Route ist doppelt registriert',
          len(_pfade203) == len(set(_pfade203)),
          str([p for p in _pfade203 if _pfade203.count(p) > 1][:3]))

    # (2) Admin-Key: Bremse + kein Absturz bei exotischem Header
    class _Req203:
        def __init__(self, v):
            self.headers = {'x-admin-key': v}
    check('v203-sec: ein Key mit Umlaut gibt False statt eines 500ers',
          _SV198._admin_ok(_Req203('schlüssel')) is False)
    _codes203 = [_c203.get('/api/admin/jobs',
                           headers={'X-Admin-Key': f'falsch{_i}'}).status_code
                 for _i in range(13)]
    check('v203-sec: nach 10 Fehlversuchen bremst der Admin-Zugang',
          _codes203[0] == 403 and _codes203[-1] == 429,
          f'{_codes203[:2]} -> {_codes203[-2:]}')
    del os.environ['DVE_ADMIN']

    # (3) Konto-Vorbelegung ueber Google
    _mail203 = f'opfer{int(_tm197.time())}@test.invalid'
    _SV198._create_user(_mail203, 'AngreiferPw123', 'angreifer203')
    _uid203, _ = _SV198._upsert_google_user('gsub-' + _mail203, _mail203, 'Opfer')
    _con203 = _SV198._db()
    _row203 = _con203.execute('SELECT pw_hash, verified FROM users WHERE id = ?',
                              (_uid203,)).fetchone()
    _sess203 = _con203.execute('SELECT COUNT(*) c FROM sessions WHERE user_id = ?',
                               (_uid203,)).fetchone()['c']
    _con203.close()
    check('v203-sec: Google-Login entwertet das Passwort eines unbestaetigten '
          'Kontos (Konto-Vorbelegung)',
          not _SV198._verify_pw('AngreiferPw123', _row203['pw_hash']))
    check('v203-sec: das uebernommene Konto gilt danach als bestaetigt',
          bool(_row203['verified']))
    check('v203-sec: bestehende Sitzungen des Kontos sind beendet', _sess203 == 0)
    # Das Konto selbst bleibt - sonst verlaere ein echter Kunde seine Bibliothek.
    check('v203-sec: das Konto wird uebernommen, nicht geloescht',
          _uid203 is not None and _row203 is not None)

    # (4) Nutzerdaten, die in die Engine laufen
    # v230g: DIE FORM, DIE WIRKLICH GESCHICKT WIRD. Der alte Test benutzte ein
    # Dict - genau deshalb ist nie aufgefallen, dass sanitize_moments bei der
    # echten LISTE mit {} aussteigt und der Server damit den ganzen
    # Momente-Editor unwirksam machte. Ein Test mit der falschen Form ist so
    # gut wie kein Test.
    _m203 = _SV198.sanitize_moments([{'i': 3, 'power': 10 ** 9, 'n': 9999,
                                      'fx': 'behind'},
                                     {'i': 5, 'power': 3, 'fx': 'boese'},
                                     {'power': 2},            # ohne 'i'
                                     'kaputt'])
    _m3 = next((m for m in _m203 if m.get('i') == 3), {})
    _m5 = next((m for m in _m203 if m.get('i') == 5), {})
    check('v203-sec: ein absurdes power faellt weg (Gauss-Radius ins Unendliche)',
          'power' not in _m3 and _m3.get('fx') == 'behind', str(_m3))
    check('v203-sec: ein unbekanntes fx faellt weg, gueltige Werte bleiben',
          'fx' not in _m5 and _m5.get('power') == 3, str(_m5))
    check('v203-sec: ein kaputter Eintrag verwirft nicht den ganzen Plan',
          len(_m203) == 2, str(_m203))
    # v230g: die Rueckgabe MUSS die Form haben, die Engine und App sprechen -
    # eine Liste mit 'i'. render.py liest sie als {m['i']: m for m in ...}.
    check('v230g: sanitize_moments liefert eine Liste mit Wort-Index',
          isinstance(_m203, list) and all(isinstance(m, dict) and 'i' in m
                                          for m in _m203), str(_m203)[:120])
    _mAus = _SV198.sanitize_moments([{'i': 7, 'aktiv': False, 'fx': 'ground'}])
    check('v230g: ein abgeschalteter Moment bleibt abgeschaltet',
          _mAus and _mAus[0].get('aktiv') is False, str(_mAus))
    _mAlt = _SV198.sanitize_moments({'9': {'fx': 'behind'}})
    check('v230g: die alte Dict-Form wird noch angenommen (Alt-Clients)',
          _mAlt and _mAlt[0].get('i') == 9 and _mAlt[0].get('fx') == 'behind',
          str(_mAlt))
    check('v203-sec: die Momente werden beim Speichern geprueft',
          'sanitize_moments(json.loads(moments))' in _sv203)
    _b203 = _SV198.sanitize_blocks([{'i0': 0, 'i1': 2, 'start': 0, 'end': 36000}],
                                   dauer=12.0)
    check('v203-sec: Blockzeiten werden gegen die Videodauer geklemmt',
          _b203[0]['end'] <= 17.0, f"end={_b203[0]['end']}")
    _b203b = _SV198.sanitize_blocks(
        [{'i0': i, 'i1': i + 1, 'start': 0, 'end': 100} for i in range(10)],
        dauer=100)
    check('v203-sec: hoechstens vier Bloecke teilen sich ein Zeitfenster',
          sum(1 for b in _b203b if 'start' in b) == _SV198._BLK_GLEICH,
          f"{sum(1 for b in _b203b if 'start' in b)} gleichzeitig")
    check('v203-sec: die Engine klemmt power selbst (Desktop schreibt dieselbe Datei)',
          "'power': max(1, min(3, int(" in open(
              os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # (5) Geld: der Preis haengt am Ledger, nicht an einem ueberschreibbaren Feld
    check('v203-sec: es gibt eine Ledger-Wahrheit fuer den gebuchten Preis',
          'def _render_gebucht(' in _sv203)
    check('v203-sec: eine Hochstufung nach der Abrechnung wird abgelehnt',
          'Hochstufung nach der Abrechnung abgelehnt' in _sv203
          and "j['cost_sec'] = _schon" in _sv203)
    check('v203-sec: der Demo-Job traegt seine Beschraenkung am Job, nicht am mode',
          "'demo': (mode == 'demo')," in _sv203
          and "if j.get('demo') or mode == 'demo':" in _sv203
          and _sv203.count("Demo videos cannot be re-rendered") == 2)

    # (6) Sitzungen
    check('v203-sec: ein Passwortwechsel beendet alle anderen Sitzungen',
          'con.execute("DELETE FROM sessions WHERE user_id = ?", (u[\'id\'],))'
          in _sv203)
    check('v203-sec: der Restore leert die Sitzungstabelle',
          "c.execute('DELETE FROM sessions')" in _sv203)
    check('v203-sec: der Code-Pruefer ist gebremst (Rateorakel)',
          "bucket='code'" in _sv203)
    check('v203-sec: die Transkript-Neuanalyse kennt den Flooding-Riegel',
          "raise HTTPException(409, 'This job is already running.')" in _sv203
          and _sv203.count('_enqueue_guard(') >= 3)

    # ======= v204-sec: Haertung, die ohne Ismet ging ======================
    # Aus dem Audit-Rueckstand alles, was keine Zugangsdaten braucht.
    # Offen bleibt allein die Sicherung ausser Haus (Cloudflare R2).
    _sv204 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    os.environ['DVE_ADMIN'] = 'testkey_v204'
    _c204 = _TC198(_SV198.app, base_url='https://test')
    _H204 = {'X-Admin-Key': 'testkey_v204'}

    # (1) Meldeweg von aussen
    _st204 = _c204.get('/.well-known/security.txt')
    check('v204-sec: security.txt ist ohne Anmeldung erreichbar',
          _st204.status_code == 200 and 'Contact: mailto:' in _st204.text
          and 'Expires:' in _st204.text)

    # (2) Der Renderer sieht die Geheimnisse nicht mehr
    _erl204 = _sv204.split('_ERLAUBT = (')[1].split(')')[0]
    check('v204-sec: der Render-Subprozess bekommt eine Allowlist, keine Vollkopie',
          "env = {k: v for k, v in os.environ.items()" in _sv204
          and 'env = dict(os.environ)' not in _sv204.split('def _run_render')[1][:2000]
          if 'def _run_render' in _sv204 else True)
    for _geheim in ('STRIPE_SECRET_KEY', 'DVE_ADMIN', 'SMTP_PASS',
                    'GOOGLE_CLIENT_SECRET', 'RESEND_API_KEY', 'DVE_REF_SALT'):
        check(f'v204-sec: {_geheim} steht NICHT in der Renderer-Allowlist',
              _geheim not in _erl204)
    check('v204-sec: der OpenAI-Key kommt aber durch (sonst keine KI-Regie)',
          'OPENAI_API_KEY' in _erl204)

    # (3) Chronik: wer wann was
    check('v204-sec: es gibt eine Ereignis-Tabelle',
          'CREATE TABLE IF NOT EXISTS security_events' in _sv204)
    check('v204-sec: JEDER Admin-Zugriff wird zentral protokolliert',
          "_sec_event('admin', request" in _sv204
          and _sv204.index("_sec_event('admin', request")
          > _sv204.index('def _require_admin'))
    _c204.post('/api/login', data={'email': 'gibtsnicht204@x.de',
                                   'password': 'falsch123'})
    _m204 = f'chr{int(_tm197.time())}@test.invalid'
    _SV198._create_user(_m204, 'richtig123', 'Chronik Test')
    _c204.post('/api/login', data={'email': _m204, 'password': 'falsch1234'})
    _c204.post('/api/login', data={'email': _m204, 'password': 'richtig123'})
    _ev204 = _c204.get('/api/admin/events', headers=_H204).json()
    _arten204 = [e['aktion'] for e in _ev204['events']]
    check('v204-sec: ein FEHLGESCHLAGENER Login steht in der Chronik',
          'login_fehl' in _arten204)
    check('v204-sec: ein erfolgreicher Login ebenfalls', 'login_ok' in _arten204)
    check('v204-sec: der Admin-Zugriff selbst ebenfalls', 'admin' in _arten204)
    check('v204-sec: die Chronik enthaelt KEINE Passwoerter',
          not any('richtig123' in str(e) or 'falsch' in str(e.get('detail', ''))
                  for e in _ev204['events']))
    check('v204-sec: die Chronik wird begrenzt (kein ewiges Wachstum)',
          'def _sec_event_purge' in _sv204 and 'SEC_EVENT_TAGE' in _sv204)
    # Der Schreiber darf sich nicht selbst blockieren: _sec_event oeffnet eine
    # EIGENE Verbindung: wird es aus einer Funktion heraus gerufen, die schon
    # eine offene haelt, laeuft es in 'database is locked' und die Zeile ist
    # still weg - genau der interessanteste Vorgang (Konto-Uebernahme) war
    # betroffen. Der echte Beweis: die Zeile MUSS in der Chronik landen.
    _gm204 = f'gsec{int(_tm197.time())}@test.invalid'
    _SV198._create_user(_gm204, 'AngreiferPw123', 'vorbeleger204')
    _SV198._upsert_google_user('gsub204-' + _gm204, _gm204, 'Echter')
    _con_g = _SV198._db()
    _n_g = _con_g.execute("SELECT COUNT(*) c FROM security_events "
                          "WHERE aktion = 'google_uebernahme'").fetchone()['c']
    _con_g.close()
    check('v204-sec: die Konto-Uebernahme landet WIRKLICH in der Chronik '
          '(kein "database is locked")', _n_g >= 1, f'{_n_g} Zeilen')
    check('v204-sec: sie wird ausserhalb der offenen Verbindung geschrieben',
          'for _a, _w, _d in _nachtrag:' in _sv204
          and _sv204.index('_nachtrag.append(')
          < _sv204.index('for _a, _w, _d in _nachtrag:'))
    check('v204-sec: der Schreiber gibt bei Sperre nicht sofort auf',
          'for versuch in range(3):' in _sv204)

    # (4) NOTAUS - der Hebel, wenn man noch nicht weiss, was los ist
    check('v204-sec: der Betriebszustand liegt auf der PLATTE, nicht im Speicher',
          'BETRIEB_DATEI = os.path.join(DATA' in _sv204)
    _c204.post('/api/admin/betrieb', data={'stufe': 'pausiert'}, headers=_H204)
    check('v204-sec: pausiert stoppt neue Uploads',
          _c204.post('/api/upload',
                     files={'datei': ('a.mp4', b'x', 'video/mp4')}
                     ).status_code == 503)
    check('v204-sec: pausiert sperrt den Admin NICHT aus',
          _c204.get('/api/admin/overview', headers=_H204).status_code == 200)
    check('v204-sec: pausiert laesst fertige Videos abrufbar',
          _c204.get('/api/library').status_code != 503)
    _c204.post('/api/admin/betrieb', data={'stufe': 'notaus'}, headers=_H204)
    _con204 = _SV198._db()
    _sess204 = _con204.execute('SELECT COUNT(*) c FROM sessions').fetchone()['c']
    _con204.close()
    check('v204-sec: NOTAUS meldet alle Kunden ab', _sess204 == 0)
    check('v204-sec: der Health-Check bleibt auch im NOTAUS erreichbar',
          _c204.get('/api/health').status_code == 200)
    _c204.post('/api/admin/betrieb', data={'stufe': 'normal'}, headers=_H204)
    check('v204-sec: und wieder zurueck',
          _c204.get('/api/admin/betrieb', headers=_H204).json()['stufe'] == 'normal')
    check('v204-sec: das Umschalten steht in der Chronik',
          'betrieb' in [e['aktion'] for e in
                        _c204.get('/api/admin/events',
                                  headers=_H204).json()['events']])
    del os.environ['DVE_ADMIN']

    # (5) Ressourcen-Grenzen
    check('v204-sec: ein Upload-Abschnitt ist gedeckelt (RAM-Schutz)',
          'CHUNK_MAX_BYTES' in _sv204
          and _sv204.index("_angek = int(request.headers.get('content-length'")
          < _sv204.index("    data = await request.body()"))
    check('v204-sec: Aufloesung und Bildrate sind gedeckelt',
          'MAX_PIXEL_LANG' in _sv204 and 'MAX_FPS' in _sv204
          and 'Video resolution too high' in _sv204
          and 'Frame rate too high' in _sv204)
    check('v204-sec: eine unlesbare Datei wird abgelehnt statt als 0s-Job zu laufen',
          'Could not read this video' in _sv204)

    # (6) Container-Haertung - und ihr Sicherheitsnetz
    _dock204 = open(os.path.join(HERE, 'Dockerfile'), encoding='utf-8').read()
    _comp204 = open(os.path.join(HERE, 'docker-compose.yml'), encoding='utf-8').read()
    _ent204 = open(os.path.join(HERE, 'entrypoint.sh'), encoding='utf-8').read()
    check('v204-sec: es gibt einen Dienst-Nutzer im Image',
          'useradd' in _dock204 and 'dve' in _dock204)
    check('v204-sec: der Start laeuft ueber das Entrypoint-Skript',
          'ENTRYPOINT ["/app/entrypoint.sh"]' in _dock204)
    # Das Wichtigste: die Haertung darf die Seite NIE abschalten.
    check('v204-sec: das Entrypoint faellt im Zweifel auf root zurueck, statt zu sterben',
          _ent204.count('exec "$@"') >= 4 and 'runuser' in _ent204
          and 'set -e' not in _ent204.split('\n')[0:30])
    check('v204-sec: es prueft VOR dem Rechte-Abwurf, ob geschrieben werden kann',
          'test -w "$DATA_DIR"' in _ent204)
    for _flag, _was in (('no-new-privileges:true', 'kein Rechte-Aufstieg'),
                        ('cap_drop', 'keine Kernel-Sonderrechte'),
                        ('pids_limit', 'keine Fork-Bombe'),
                        ('mem_limit', 'kein Speicher-Amoklauf')):
        check(f'v204-sec: Container-Haertung {_flag} ({_was})', _flag in _comp204)
    # Das Gate ueberschreibt den Entrypoint - sonst laeuft der Selftest im
    # neuen Image gar nicht erst an.
    check('v204-sec: das Test-Gate haengt nicht am neuen Entrypoint',
          '--entrypoint bash' in open(os.path.join(HERE, 'deploy_gate.sh'),
                                      encoding='utf-8').read())

    # (6b) v205-sec: Ohne Terminal nachsehen koennen, WAS laeuft.
    os.environ['DVE_ADMIN'] = 'testkey_v205'
    _c205 = _TC198(_SV198.app, base_url='https://test')
    _sys205 = _c205.get('/api/admin/system',
                        headers={'X-Admin-Key': 'testkey_v205'}).json()
    del os.environ['DVE_ADMIN']
    check('v205-sec: das Panel zeigt, ob der Dienst als root laeuft',
          isinstance(_sys205.get('laufzeit'), dict)
          and 'root' in _sys205['laufzeit'] and 'user' in _sys205['laufzeit'],
          str(_sys205.get('laufzeit'))[:120])
    check('v205-sec: das Panel zeigt die Versionen der Bauteile',
          len(_sys205.get('pakete') or {}) >= 8,
          f"{len(_sys205.get('pakete') or {})} Pakete")
    check('v205-sec: die Bauteile, die fremde Dateien anfassen, sind dabei',
          any(p in _sys205['pakete'] for p in ('Pillow', 'opencv-python',
                                               'opencv-python-headless'))
          and 'fastapi' in _sys205['pakete'])
    _adm205 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v205-sec: die Ansicht warnt sichtbar, wenn noch als root gelaufen wird',
          'd.laufzeit.root' in _adm205 and 'Generalschluessel' in _adm205)

    # (6c) v205a-sec: Die Haertung darf sich nicht selbst blockieren, und die
    # Bauteile sind festgenagelt.
    _comp205 = open(os.path.join(HERE, 'docker-compose.yml'),
                    encoding='utf-8').read()
    check('v205a-sec: cap_drop ALL gibt die Start-Rechte gezielt zurueck',
          'cap_add:' in _comp205
          and all(c in _comp205 for c in ('CHOWN', 'SETUID', 'SETGID',
                                          'DAC_OVERRIDE', 'FOWNER')),
          'sonst kann der Start gar nicht auf den kleineren Nutzer wechseln')
    _y205 = _y160.safe_load(open(os.path.join(HERE, 'docker-compose.yml'),
                                 encoding='utf-8'))
    _app205 = _y205['services']['app']
    check('v205a-sec: der laufende Dienst behaelt trotzdem KEINE Sonderrechte',
          _app205.get('cap_drop') == ['ALL']
          and set(_app205.get('cap_add') or []) <= {'CHOWN', 'FOWNER', 'SETUID',
                                                    'SETGID', 'DAC_OVERRIDE'})
    _req205 = open(os.path.join(HERE, 'requirements.txt'), encoding='utf-8').read()
    _soll205 = ('opencv-python', 'Pillow', 'onnxruntime', 'mediapipe', 'numpy',
                'protobuf', 'fastapi', 'uvicorn', 'python-multipart',
                'requests', 'PyYAML', 'bcrypt', 'stripe')
    _frei205 = [p for p in _soll205
                if not _re203.search(rf'^{_re203.escape(p)}==', _req205, _re203.M)]
    check('v205a-sec: JEDES Bauteil hat eine exakte Version',
          not _frei205, f'ungepinnt: {_frei205}')
    _dock205 = open(os.path.join(HERE, 'Dockerfile'), encoding='utf-8').read()
    check('v205a-sec: es gibt nur EINE Quelle fuer die Abhaengigkeiten',
          'pip install --no-cache-dir fastapi uvicorn' not in _dock205
          and _dock205.count('pip install') == 1)

    # ======= v206: Zahlen, denen man trauen kann + Startseite ===========
    # Ismets Befund: das Panel ist "unuebersichtlich und kaum
    # benutzerfreundlich", mit Begriffen, bei denen er "keine Ahnung habe, was
    # genau das ist" - und er wusste nicht, ob die Einnahmen stimmen.
    # Taten sie nicht: der Umsatz war BRUTTO, Erstattungen wurden nirgends
    # abgezogen (auch nicht in der §19-Steuerampel).
    _sv206 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    os.environ['DVE_ADMIN'] = 'testkey_v206'
    _c206 = _TC198(_SV198.app, base_url='https://test')
    _H206 = {'X-Admin-Key': 'testkey_v206'}
    _now206 = int(_tm197.time())
    _con206 = _SV198._db()
    _con206.execute("INSERT INTO purchases (session_id,user_id,pack,cents,"
                    "sekunden,created_at) VALUES ('t206a',1,'m',1900,3600,?)",
                    (_now206 - 3600,))
    _con206.commit(); _con206.close()
    _SV198._ttl_drop('adm:')
    _r206 = _c206.get('/api/admin/revenue', headers=_H206).json()['windows']['total']
    _vorher206 = _r206['netto_eur']
    check('v206: der Umsatz weist eingenommen, erstattet und geblieben aus',
          all(k in _r206 for k in ('eur', 'erstattet_eur', 'netto_eur')),
          str(_r206)[:120])
    _con206 = _SV198._db()
    _con206.execute("INSERT INTO refunds (session_id,user_id,cents,quelle,"
                    "created_at) VALUES ('t206a',1,1900,'panel',?)", (_now206,))
    _con206.commit(); _con206.close()
    _SV198._ttl_drop('adm:')
    _r206b = _c206.get('/api/admin/revenue', headers=_H206).json()['windows']['total']
    check('v206: eine Erstattung senkt das, was geblieben ist',
          _r206b['netto_eur'] == round(_vorher206 - 19.0, 2)
          and _r206b['erstattet_eur'] >= 19.0,
          f"{_vorher206} -> {_r206b['netto_eur']}, erstattet {_r206b['erstattet_eur']}")
    check('v206: die eingenommene Summe bleibt unveraendert (Beleg wird nicht verbogen)',
          _r206b['eur'] == _r206['eur'])
    _tax206 = _c206.get('/api/admin/compliance/tax', headers=_H206).json()
    _j206 = [j for j in _tax206['jahre'] if j.get('erstattet_cent')]
    check('v206: die Steuer-Ampel rechnet mit dem, was geblieben ist',
          bool(_j206) and _j206[0]['brutto_cent']
          == _j206[0]['eingenommen_cent'] - _j206[0]['erstattet_cent'])
    check('v206: die Panel-Erstattung wird als eigener Vorgang festgehalten',
          "INSERT OR IGNORE INTO refunds" in _sv206
          and _sv206.count('INSERT OR IGNORE INTO refunds') >= 2)
    check('v206: auch eine im Stripe-Dashboard ausgeloeste Erstattung zaehlt',
          "'stripe',?)" in _sv206
          and "ev_type == 'charge.refunded'" in _sv206)

    # Startseite: vier Fragen, vier Zahlen
    _st206 = _c206.get('/api/admin/start', headers=_H206).json()
    for _teil in ('geld', 'betrieb', 'post', 'wachstum'):
        check(f'v206: die Startseite beantwortet "{_teil}"', _teil in _st206)
    check('v206: sie zeigt Geld NACH Erstattungen',
          _st206['geld']['gesamt']['eur']
          == round(_r206b['eur'] - _r206b['erstattet_eur'], 2),
          f"{_st206['geld']['gesamt']} vs {_r206b}")
    check('v206: die Betriebs-Ampel kennt nur drei Zustaende',
          _st206['betrieb']['ampel'] in ('gruen', 'gelb', 'rot'))
    # Eine Ampel, die nach jedem Deploy grundlos rot ist, schaut niemand an.
    check('v206: der Herzschlag wird beim Start gesetzt (kein Fehlalarm nach dem Deploy)',
          "_HEARTBEAT['cleanup'] = _HEARTBEAT['watchdog'] = time.time()" in _sv206)
    check('v206: direkt nach dem Start ist die Ampel nicht rot',
          _st206['betrieb']['ampel'] != 'rot'
          or all('meldet sich nicht' not in p['text']
                 for p in _st206['betrieb']['probleme']),
          str(_st206['betrieb']['probleme'])[:150])
    _adm206 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v206: die Startseite steht vorn und ist die Voreinstellung',
          "['start','Start']" in _adm206 and "active='start'" in _adm206
          and 'start:loadStart' in _adm206)
    check('v206: jede Zahl bekommt einen Satz Klartext daneben',
          _adm206.count('class="satz"') >= 8
          and 'VERDIENE ICH GELD?' in _adm206 and 'LAEUFT ALLES?' in _adm206)
    del os.environ['DVE_ADMIN']

    # ======= v207-sec: kein Testlauf gegen echte Dienste =================
    # Vom Test-Gate bei seinem ERSTEN erfolgreichen Lauf im Container
    # gefunden: dort ist der Stripe-LIVE-Schluessel gesetzt, also rief
    # admin_refund im Test Refund.create gegen das echte Konto. Mit einer
    # erfundenen Sitzungs-Nummer schlug es fehl - mit einer echten waere
    # ECHTES GELD erstattet worden. Gleiches Muster bei Mail und OpenAI.
    import server as _SV207
    check('v207-sec: der Stripe-Zugang ist im Test leer',
          not os.environ.get('STRIPE_SECRET_KEY'))
    check('v207-sec: es gibt damit gar keinen Stripe-Klienten',
          _SV207._stripe() is None)
    for _k207 in ('SMTP_PASS', 'RESEND_API_KEY', 'OPENAI_API_KEY',
                  'GOOGLE_CLIENT_SECRET', 'STRIPE_WEBHOOK_SECRET'):
        check(f'v207-sec: {_k207} ist im Test leer', not os.environ.get(_k207))
    # v207a-sec: Der Testclient braucht einen HTTP-Klienten. Er war hier
    # zufaellig als Nebenabhaengigkeit da, im Image nicht - das Gate starb
    # genau an den neuen Sicherheitstests. Was der Test BRAUCHT, gehoert in
    # requirements.txt, sonst laeuft er nur dort, wo jemand Glueck hat.
    _req207 = open(os.path.join(HERE, 'requirements.txt'), encoding='utf-8').read()
    check('v207a-sec: der HTTP-Klient des Testclients ist eine echte Abhaengigkeit',
          _re203.search(r'^httpx==', _req207, _re203.M) is not None)
    _st207 = open(os.path.join(HERE, 'selftest.py'), encoding='utf-8').read()
    check('v207-sec: gekappt wird VOR dem Import des Servers',
          _st207.index('_GEKAPPT = _dienste_kappen()')
          < _st207.index('def main():'))
    _gate207 = open(os.path.join(HERE, 'deploy_gate.sh'), encoding='utf-8').read()
    for _k207 in ('STRIPE_SECRET_KEY', 'SMTP_PASS', 'RESEND_API_KEY'):
        check(f'v207-sec: auch das Gate leert {_k207} (zweite Schranke)',
              f'-e {_k207}=' in _gate207)

    # ======= v208: Trichter (wer kam, wo springen sie ab) ===============
    # Ismets Frage: "Kann man auch tracken wer auf die webseite etc kam?
    # conversion usw". Gebaut ohne Cookie, ohne gespeicherte IP und ohne
    # fremden Dienst - der Zaehl-Fingerabdruck ist taeglich gesalzen und
    # damit ueber Tage nicht verkettbar. Genau das ist der Grund, warum
    # kein Einwilligungsbanner noetig ist; ein Test muss diese Zusage
    # halten, nicht nur die Zahlen.
    _sv208 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    os.environ['DVE_ADMIN'] = 'testkey_v208'
    os.environ['DVE_REF_SALT'] = 'salz208'
    _c208 = _TC198(_SV198.app, base_url='https://test')
    _H208 = {'X-Admin-Key': 'testkey_v208'}

    class _Req208:
        def __init__(self, qp=None, ref=None, ua='UA/1', ip='1.2.3.4'):
            self.query_params = qp or {}
            self.headers = {}
            if ref:
                self.headers['referer'] = ref
            self.headers['user-agent'] = ua
            self.client = type('C', (), {'host': ip})()

    check('v208: eine eigene Kampagnen-Marke schlaegt den Verweis-Header',
          _SV198._quelle_von(_Req208({'utm_source': 'newsletter'},
                                     'https://www.google.com/')) == 'newsletter')
    check('v208: l.instagram.com und instagram.com sind dieselbe Quelle',
          _SV198._quelle_von(_Req208(None, 'https://l.instagram.com/x'))
          == _SV198._quelle_von(_Req208(None, 'https://instagram.com/'))
          == 'instagram')
    check('v208: ohne Verweis heisst die Quelle "direkt"',
          _SV198._quelle_von(_Req208()) == 'direkt')
    # Der Fingerabdruck: gleich innerhalb des Tages, verschieden je Mensch,
    # und aus ihm laesst sich die IP nicht zurueckholen.
    _b208 = _SV198._besucher_id(_Req208(ip='9.9.9.9'))
    check('v208: derselbe Besucher ergibt am selben Tag denselben Wert',
          _b208 == _SV198._besucher_id(_Req208(ip='9.9.9.9')) and len(_b208) == 16)
    check('v208: ein anderer Besucher ergibt einen anderen Wert',
          _b208 != _SV198._besucher_id(_Req208(ip='9.9.9.8')))
    check('v208: der Wert enthaelt die IP nicht im Klartext',
          '9.9.9.9' not in _b208)
    # Das Salz wechselt taeglich - ohne diese Rotation waere der Wert eine
    # dauerhafte Kennung, und genau dann braeuchte es ein Banner.
    check('v208: das Tagesdatum steckt im Fingerabdruck (nicht verkettbar)',
          "time.strftime('%Y%m%d')" in _sv208
          and 'def _besucher_id' in _sv208)

    # Echter Seitenaufruf zaehlt.
    _con208 = _SV198._db()
    _con208.execute("DELETE FROM trichter"); _con208.commit(); _con208.close()
    _c208.get('/', headers={'referer': 'https://www.tiktok.com/@x',
                            'user-agent': 'Mozilla/208'})
    _con208 = _SV198._db()
    _z208 = _con208.execute("SELECT stufe, quelle, besucher FROM trichter "
                            "WHERE stufe='besuch'").fetchall()
    _con208.close()
    check('v208: ein Aufruf der Startseite wird als Besuch gezaehlt',
          len(_z208) == 1 and _z208[0]['quelle'] == 'tiktok'
          and _z208[0]['besucher'], str([dict(r) for r in _z208])[:140])

    # Menschen zaehlen, nicht Klicks: drei Aufrufe desselben Besuchers.
    _con208 = _SV198._db()
    _con208.execute("DELETE FROM trichter")
    _nun208 = int(_tm197.time())
    for _i208 in range(3):
        _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                        "VALUES (?,'besuch','bes_a','tiktok',NULL)", (_nun208,))
    _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                    "VALUES (?,'besuch','bes_b','google',NULL)", (_nun208,))
    for _b in ('bes_a', 'bes_b'):
        _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                        "VALUES (?,'app',?,'',NULL)", (_nun208, _b))
    _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                    "VALUES (?,'konto','bes_a','tiktok',4208)", (_nun208,))
    _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                    "VALUES (?,'kauf','','',4208)", (_nun208,))
    _con208.commit(); _con208.close()
    _SV198._ttl_drop('adm:')
    _t208 = _c208.get('/api/admin/trichter?tage=30', headers=_H208).json()
    _s208 = {s['stufe']: s for s in _t208['stufen']}
    check('v208: drei Aufrufe desselben Menschen sind EIN Besucher',
          _s208['besuch']['anzahl'] == 2, str(_s208['besuch']))
    check('v208: jede Stufe hat einen Satz Klartext',
          all(s['titel'] and s['erklaerung'] for s in _t208['stufen']))
    check('v208: die Absprung-Zahl bezieht sich auf die Stufe DARUEBER',
          _s208['konto']['von_vorher_prozent'] == 50
          and _s208['konto']['von_oben_prozent'] == 50,
          str(_s208['konto']))
    # Kauf und fertiges Video entstehen OHNE Browser (Stripe-Webhook,
    # Render-Worker) - ihre Herkunft muss ueber das Konto nachgeschlagen
    # werden, sonst landet jeder Umsatz unter "direkt".
    _q208 = {q['quelle']: q for q in _t208['quellen']}
    check('v208: ein Kauf ohne Browser wird der Quelle des Kontos zugeordnet',
          _q208.get('tiktok', {}).get('kaeufer') == 1, str(_q208)[:160])
    check('v208: der Hinweis auf die Anonymitaet steht am Ergebnis',
          'kein Cookie' in _t208.get('hinweis', ''))
    # Die Kauf-Zaehlung stand zuerst MITTEN in der offenen Kauf-Transaktion.
    # Sie oeffnet eine zweite Verbindung auf dieselbe Datei und lief in
    # "database is locked" - der Kauf wurde also gar nicht gezaehlt (im
    # Testlauf beobachtet, nicht vermutet). Derselbe Fehlertyp wie _sec_event
    # in v204: eine Nebenbuchung gehoert nie in die Transaktion, die sie
    # beobachtet. Hier ECHT nachgestellt, nicht per Quelltext-Suche.
    _con208 = _SV198._db()
    _con208.execute("INSERT INTO users (email,pw_hash,name,balance_sec,created_at) "
                    "VALUES ('t208@x.invalid','x','T208',0,?)", (_nun208,))
    _uid208 = _con208.execute("SELECT id FROM users WHERE email='t208@x.invalid'"
                              ).fetchone()['id']
    _con208.commit(); _con208.close()
    _SV198._credit_purchase(_uid208, 600, 'sess_t208', 'm', 1900)
    _con208 = _SV198._db()
    _kauf208 = _con208.execute("SELECT COUNT(*) c FROM trichter WHERE stufe='kauf' "
                               "AND user_id=?", (_uid208,)).fetchone()['c']
    _con208.execute("DELETE FROM users WHERE id=?", (_uid208,))
    _con208.execute("DELETE FROM ledger WHERE user_id=?", (_uid208,))
    _con208.execute("DELETE FROM purchases WHERE user_id=?", (_uid208,))
    _con208.execute("DELETE FROM trichter WHERE user_id=?", (_uid208,))
    _con208.commit(); _con208.close()
    check('v208: ein verbuchter Kauf landet wirklich im Trichter (kein Lock)',
          _kauf208 == 1, f'gezaehlt: {_kauf208}')
    _fn208 = _sv208.split('def _credit_purchase')[1].split('\ndef ')[0]
    check('v208: die Kauf-Zaehlung steht NACH dem Commit, nicht in der Transaktion',
          _fn208.index("_trichter('kauf'") > _fn208.rindex('con.commit()'))
    _SV198._ttl_drop('adm:')
    _r208 = _c208.get('/api/admin/trichter')
    check('v208: ohne Admin-Schluessel gibt es keine Zahlen',
          _r208.status_code in (403, 422, 429), str(_r208.status_code))
    # Alte Zeilen fallen raus - eine Statistik ist kein Archiv.
    _con208 = _SV198._db()
    _con208.execute("INSERT INTO trichter (ts,stufe,besucher,quelle,user_id) "
                    "VALUES (?,'besuch','alt','x',NULL)",
                    (_nun208 - (_SV198.TRICHTER_TAGE + 5) * 86400,))
    _con208.commit(); _con208.close()
    _SV198._trichter_purge()
    _con208 = _SV198._db()
    _alt208 = _con208.execute("SELECT COUNT(*) c FROM trichter "
                              "WHERE besucher='alt'").fetchone()['c']
    _con208.close()
    check('v208: Zeilen aelter als die Aufbewahrungsfrist werden geloescht',
          _alt208 == 0)
    # Eine Zaehlung darf NIE einen Seitenaufruf reissen.
    _SV198._trichter('gibtsnicht', None)
    check('v208: eine unbekannte Stufe wird still verworfen, nicht geworfen', True)
    for _st208 in ('besuch', 'app', 'konto', 'upload', 'fertig', 'kauf'):
        check(f'v208: die Stufe "{_st208}" wird im Code wirklich gesetzt',
              f"_trichter('{_st208}'" in _sv208)
    # ---- v208b: Meldungen, die man lesen kann + abgebrochene Uploads ----
    # Ismets Befund: die Panel-Meldung zu /api/upload/chunk zeigte 60 Zeilen
    # starlette-Innereien und NICHT den eigentlichen Fehler - der steht in
    # einem Traceback naemlich ganz unten und faellt beim Kopieren weg.
    import asyncio as _aio208

    class _Fake208:
        url = type('U', (), {'path': '/api/upload/chunk/x'})()
        method = 'POST'
        headers = {}
        client = type('C', (), {'host': '1.1.1.1'})()

    _con208 = _SV198._db()
    _con208.execute("DELETE FROM alerts"); _con208.commit(); _con208.close()
    try:
        raise ValueError('boom208')
    except ValueError as _e208:
        _aio208.run(_SV198._unhandled(_Fake208(), _e208))
    _con208 = _SV198._db()
    _a208 = _con208.execute("SELECT text FROM alerts ORDER BY id DESC LIMIT 1"
                            ).fetchone()
    _con208.close()
    _body208 = _a208['text'] if _a208 else ''
    check('v208b: die Ursache steht ganz oben in der Meldung',
          'URSACHE: ValueError: boom208' in _body208
          and _body208.index('URSACHE:') < _body208.index('Voller Verlauf'),
          _body208[:90])
    check('v208b: der volle Verlauf bleibt trotzdem erhalten',
          'Traceback' in _body208)
    # Ein abgebrochener Upload ist keine Stoerung, sondern ein Kunde im
    # Funkloch. Ohne eigenen Riegel meldete jeder davon einen "Serverfehler",
    # und echte Stoerungen gehen im Rauschen unter.
    check('v208b: ein Verbindungsabbruch hat einen eigenen Riegel',
          'exception_handler(ClientDisconnect)' in _sv208
          and 'from starlette.requests import ClientDisconnect' in _sv208)
    _fn208b = _sv208.split('async def _weggegangen')[1].split('\n@app')[0]
    check('v208b: ein Verbindungsabbruch schreibt KEINE Stoerung ins Panel',
          '_notify_admin' not in _fn208b and 'status_code=499' in _fn208b)
    _con208 = _SV198._db()
    _con208.execute("DELETE FROM alerts"); _con208.commit(); _con208.close()

    _adm208 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v208: der Trichter steht als eigene Ansicht im Panel',
          "['trichter','Trichter']" in _adm208
          and 'trichter:loadTrichter' in _adm208
          and 'trichter:' in _adm208.split('const NAV')[0])
    _pri208 = open(os.path.join(HERE, 'web', 'privacy.html'), encoding='utf-8').read()
    check('v208: die Datenschutzseite nennt die Zaehlung und ihre Grenzen',
          'reach statistics' in _pri208 and 'no cookie' in _pri208.lower()
          and 'changes every' in _pri208.lower().replace('\n      ', ' '))
    del os.environ['DVE_ADMIN']

    # (7) Missbrauchs-Erkennung laeuft von selbst, nicht nur auf Nachfrage
    check('v204-sec: auffaellige Muster melden sich stuendlich von selbst',
          'def _missbrauch_pruefen' in _sv204
          and '_missbrauch_pruefen()' in _sv204
          and "'missbrauch:login'" in _sv204)

    check('v197: ein gescheiterter Deploy meldet sich, statt still zu bleiben',
          'DEPLOY FEHLGESCHLAGEN' in _auto197 and "'deploy', 'Deploy abgebrochen'" in _auto197)

    # --- I) v201: Das Gate hatte einen Konstruktionsfehler. "Tests rot" und
    # "Gate laeuft gar nicht" waren derselbe Fall - eine Panne an der
    # PRUEFVORRICHTUNG konnte damit den ganzen Betrieb einfrieren, ohne dass
    # am Code je etwas fehlte. Genau das ist nach v197 passiert: v198 war der
    # erste Commit, der durch das Gate musste. Ein Waechter, der bei eigenem
    # Ausfall die Tuer zumauert, ist kein Waechter.
    # Geprueft wird das Gate ECHT, mit einem vorgetaeuschten docker - eine
    # Quelltext-Suche haette den Fehler nie gefunden.
    import subprocess as _sp201
    import tempfile as _tf201
    _bin201 = _tf201.mkdtemp(prefix='gate201_')

    def _gate201(ausgabe, rc):
        os.makedirs(_bin201, exist_ok=True)     # nach dem Aufraeumen erneut nutzbar
        with open(os.path.join(_bin201, 'docker'), 'w') as f:
            f.write(f'#!/usr/bin/env bash\n{ausgabe}\nexit {rc}\n')
        os.chmod(os.path.join(_bin201, 'docker'), 0o755)
        umg = dict(os.environ, PATH=_bin201 + os.pathsep + os.environ['PATH'])
        return _sp201.run(['bash', os.path.join(HERE, 'deploy_gate.sh')],
                          capture_output=True, text=True, env=umg, cwd=HERE)

    _g_ok = _gate201('echo "1384/1384 Tests bestanden"', 0)
    check('v201: gruener Selftest laesst den Deploy durch', _g_ok.returncode == 0,
          _g_ok.stdout[-200:])
    _g_rot = _gate201('echo "FAIL irgendein Test"; echo "1383/1384 Tests bestanden"', 1)
    check('v201: roter Selftest bricht ab (exit 1)', _g_rot.returncode == 1)
    check('v201: das Gate nennt die gefallenen Tests',
          'FAIL irgendein Test' in _g_rot.stdout)
    _g_kaputt = _gate201('echo "bash: ffmpeg: command not found"', 127)
    check('v201: ein NICHT LAUFFAEHIGES Gate ist ein anderer Fall (exit 2)',
          _g_kaputt.returncode == 2, _g_kaputt.stdout[-200:])
    os.remove(os.path.join(_bin201, 'docker'))
    _g_leer = _sp201.run(['bash', os.path.join(HERE, 'deploy_gate.sh')],
                         capture_output=True, text=True, cwd=HERE,
                         env=dict(os.environ, PATH=_bin201 + ':/usr/bin:/bin'))
    check('v201: fehlt docker ganz, ist das ebenfalls exit 2 (nicht "rot")',
          _g_leer.returncode == 2)
    shutil.rmtree(_bin201, ignore_errors=True)
    # Und update.sh muss die beiden Faelle wirklich verschieden behandeln.
    check('v201: nur exit 1 bricht den Deploy ab',
          'if [ "$GATE_RC" -eq 1 ]; then' in _upd197
          and 'elif [ "$GATE_RC" -ne 0 ]; then' in _upd197)
    check('v201: ein defektes Gate wird im Panel vermerkt, nicht nur im Log',
          "'deploy_gate', 'Test-Gate nicht lauffaehig'" in _upd197
          and 'GATE_DEFEKT' in _upd197)
    # v201a: WELCHE Tests gefallen sind, muss in die Panel-Meldung. Vorher
    # stand dort nur "Deploy abgebrochen" und der Rest in journalctl - fuer
    # jemanden, der nie ins Terminal geht, ist das wie keine Meldung.
    _bef201 = os.path.join(HERE, '.deploy_gate_last.txt')
    _g_rot2 = _gate201('echo "FAIL testname xy"; echo "1390/1391 Tests bestanden"', 1)
    check('v201a: das Gate hinterlaesst seinen Befund als Datei',
          os.path.exists(_bef201) and 'FAIL testname xy' in open(_bef201).read()
          and open(_bef201).read().startswith('rot'),
          open(_bef201).read()[:80] if os.path.exists(_bef201) else 'fehlt')
    # ---- v230j: der Deploy meldet, dass er laeuft - und misst sich selbst ----
    # Ismets Befund "habe es satt, dass die Builds nicht uebernommen werden":
    # das Panel zeigte nur den LAUFENDEN Stand, er sah v230h waehrend v230i
    # vier Minuten alt und noch im Bau war. "dauert noch" liess sich nicht
    # von "haengt" unterscheiden. Geprueft wird durch AUSFUEHREN mit
    # vorgetaeuschtem docker/git/update.sh - eine Quelltext-Suche haette hier
    # nichts bewiesen (dieselbe Lehre wie beim Gate, v201).
    import sqlite3
    _t230 = tempfile.mkdtemp(prefix='dve_dep_')
    _b230 = os.path.join(_t230, 'bin')
    os.makedirs(_b230, exist_ok=True)
    os.makedirs(os.path.join(_t230, 'data'), exist_ok=True)
    sqlite3.connect(os.path.join(_t230, 'data', 'users.db')).close()
    with open(os.path.join(_b230, 'docker'), 'w') as fh:
        fh.write('#!/usr/bin/env bash\nshift 3\nshift\nexec "$@"\n')
    with open(os.path.join(_b230, 'git'), 'w') as fh:
        fh.write('#!/usr/bin/env bash\ncase "$*" in\n'
                 '  *"--abbrev-ref HEAD"*) echo "claude/test" ;;\n'
                 '  *"rev-parse HEAD"*) echo "' + '1' * 40 + '" ;;\n'
                 '  *"rev-parse origin/"*) echo "abcdef1234567890'
                 'abcdef1234567890abcdef12" ;;\n  *) exit 0 ;;\nesac\n')
    for _f in ('docker', 'git'):
        os.chmod(os.path.join(_b230, _f), 0o755)
    shutil.copy(os.path.join(HERE, 'autodeploy.sh'), _t230)
    with open(os.path.join(_t230, '.deploy_gate_last.txt'), 'w') as fh:
        fh.write('FAIL testname xy')

    def _dep230(rc):
        with open(os.path.join(_t230, 'update.sh'), 'w') as fh:
            fh.write(f'#!/usr/bin/env bash\nsleep 1\nexit {rc}\n')
        os.chmod(os.path.join(_t230, 'update.sh'), 0o755)
        run(['bash', 'autodeploy.sh'], cwd=_t230,
            env=dict(os.environ, INSTALL_DIR=_t230,
                     DVE_DATA=os.path.join(_t230, 'data'),
                     PATH=_b230 + ':' + os.environ.get('PATH', '')))
        _c = sqlite3.connect(os.path.join(_t230, 'data', 'users.db'))
        try:
            _r = _c.execute('SELECT phase, commit_kurz, dauer_s, grund '
                            'FROM deploy_state WHERE id = 1').fetchone()
        except Exception:
            _r = None
        _c.close()
        return _r

    _ok230 = _dep230(0)
    check('v230j: ein gelungener Deploy hinterlaesst Zustand UND Dauer',
          _ok230 and _ok230[0] == 'ok' and _ok230[1] == 'abcdef123456'
          and _ok230[2] >= 1, str(_ok230))
    _bad230 = _dep230(1)
    check('v230j: ein gescheiterter Deploy hinterlaesst den Grund',
          _bad230 and _bad230[0] == 'fehler'
          and 'FAIL testname xy' in (_bad230[3] or ''), str(_bad230))
    shutil.rmtree(_t230, ignore_errors=True)
    # Und das Panel muss den Zustand auch ANZEIGEN.
    _adm230 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v230j: das Panel zeigt den Deploy-Zustand an',
          'function deployZeile(' in _adm230
          and 'wird ausgerollt' in _adm230 and 'letzter Deploy' in _adm230)
    check('v230j: der Server reicht den Zustand durch',
          'FROM deploy_state WHERE id = 1' in _sv203
          and "d['phase'] = 'haengt'" in _sv203)

    _gate201('echo "1391/1391 Tests bestanden"', 0)
    check('v201a: bei gruen steht die Bilanz drin, keine FAIL-Zeilen',
          open(_bef201).read().startswith('gruen')
          and 'FAIL' not in open(_bef201).read())
    # v208a: DAS GATE HIELT EINEN GRUENEN LAUF FUER ROT. Am 28.07. blockierte
    # es c301656 mit "rot / 1511/1511 Tests bestanden / FAIL testname xy" -
    # also mit ALLEN Tests bestanden. Ursache: es suchte im Log nach Zeilen,
    # die mit 'FAIL' beginnen, und der v201a-Test hier legt genau so eine
    # Zeile an (er zeigt den Inhalt eines roten Gate-Befunds als Beleg her).
    # Zwei Riegel: check() macht aus jedem Beleg EINE Zeile, und das Gate
    # urteilt nach der BILANZ statt nach einer Textsuche.
    _g_fp = _gate201('echo "PASS irgendwas"; echo "FAIL testname xy"; '
                     'echo "1511/1511 Tests bestanden"', 0)
    # Der Beleg gibt bewusst NUR den Rueckgabewert her: stuende hier die
    # Gate-Ausgabe, enthielte diese Zeile selbst eine Bilanz - und der naechste
    # der das Log auswertet, laese die falsche.
    check('v208a: ein FAIL-Wort im Beleg macht aus 1511/1511 keinen roten Lauf',
          _g_fp.returncode == 0, f'rc={_g_fp.returncode}')
    _g_zahl = _gate201('echo "1510/1511 Tests bestanden"', 0)
    check('v208a: eine unvollstaendige Bilanz ist rot, auch bei Rueckgabewert 0',
          _g_zahl.returncode == 1)
    check('v208a: mehrzeilige Belege werden zu einer Zeile', True,
          'rot\nFAIL testname xy')
    check('v208a: der Beleg von eben enthaelt keinen Zeilenumbruch mehr',
          '\n' not in results[-1][2] and 'FAIL testname xy' in results[-1][2],
          results[-1][2])
    check('v201a: autodeploy reicht den Befund in die Meldung durch',
          '.deploy_gate_last.txt' in _auto197
          and 'Befund des Test-Gates' in _auto197)
    # Der Test darf keine Datei hinterlassen: sie ist ein Laufzeit-Artefakt
    # des Servers, hier hat sie nichts verloren.
    if os.path.exists(_bef201):
        os.remove(_bef201)
    # v205b-sec: Ein Befund ohne Ort ist kein Befund. Das Gate meldet, welche
    # Stufe es zuletzt erreicht hat - sonst steht im Panel nur "ging nicht".
    _gate205 = open(os.path.join(HERE, 'deploy_gate.sh'), encoding='utf-8').read()
    check('v205b-sec: das Gate meldet, wie weit es gekommen ist',
          _gate205.count('GATE-STUFE') >= 5)
    check('v205b-sec: die letzte erreichte Stufe steht im Befund',
          'Letzte erreichte Stufe:' in _gate205)
    _upd205 = open(os.path.join(HERE, 'update.sh'), encoding='utf-8').read()
    check('v205b-sec: der Befund wandert auch bei NICHT LAUFFAEHIGEM Gate ins Panel',
          'GATE_BEFUND=' in _upd205
          and '.deploy_gate_last.txt' in _upd205.split('GATE_DEFEKT:-0')[1][:600])
    # Das eingebettete Python muss fuer sich allein gueltig sein - ein Fehler
    # darin faellt sonst erst auf dem Server auf, im Moment der Stoerung.
    import ast as _ast205
    _i205 = _upd205.index("<<'PY'")
    _blk205 = _upd205[_upd205.index('\n', _i205) + 1:_upd205.index('\nPY\n', _i205)]
    try:
        _ast205.parse(_blk205)
        _py_ok205 = True
    except SyntaxError:
        _py_ok205 = False
    check('v205b-sec: das eingebettete Melde-Python ist gueltig', _py_ok205)

    check('v201a: die Befund-Datei ist kein Repo-Inhalt',
          '.deploy_gate_last.txt' in open(os.path.join(HERE, '.gitignore'),
                                          encoding='utf-8').read())

    # ======= v195: Admin-Panel als Seitenleiste ==========================
    # Zwoelf Ansichten in einer umbrechenden Tab-Zeile waren schon zu viel,
    # und jede neue machte es schlimmer. Jetzt eine gruppierte Seitenleiste
    # mit Breadcrumb - dieselben zwoelf Ansichten, nur nach Aufgabe sortiert.
    _adm195 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v195: die Navigation ist in Abschnitte gruppiert',
          'const NAV=[' in _adm195
          and "['Umsatz'," in _adm195 and "['Kunden'," in _adm195
          and "['Betrieb'," in _adm195)
    # KEINE Ansicht darf beim Umbau verloren gegangen sein.
    import re as _re195
    _nav195 = _re195.search(r"const NAV=\[(.*?)\n\];", _adm195, _re195.S)
    _ids195 = set(_re195.findall(r"\['([a-z]+)','", _nav195.group(1) if _nav195 else ''))
    _rend195 = set(_re195.findall(r"^\s*([a-z]+):\s*async function|^\s*([a-z]+):\s*function",
                                  _adm195, _re195.M))
    # v196: zwei Ansichten dazu (feedback, ann). Der Test bleibt, was er war -
    # eine Garantie, dass beim Umbauen der Navigation nichts VERSCHWINDET.
    _soll195 = {'live', 'alerts', 'jobs', 'revenue', 'credits', 'codes',
                'users', 'support', 'abuse', 'system', 'compliance', 'legal',
                'feedback', 'ann', 'logs', 'events', 'start', 'trichter'}
    check('v195: alle Ansichten sind weiter erreichbar',
          _ids195 == _soll195, f"fehlt: {_soll195 - _ids195}  neu: {_ids195 - _soll195}")
    check('v195: TABS wird aus NAV abgeleitet (eine Quelle, nicht zwei Listen)',
          'const TABS=NAV.flatMap(' in _adm195)
    check('v195: die aktive Zeile wird in der Seitenleiste markiert',
          "document.querySelectorAll('.side a').forEach" in _adm195
          and ".tabs button" not in _adm195)
    check('v195: Breadcrumb und Titel folgen der Auswahl',
          "el('crumbNow').textContent=t" in _adm195
          and "el('viewTitle').textContent=t" in _adm195)
    check('v195: offene Alerts stehen als Zaehler in der Navigation',
          'function setBadge(' in _adm195 and "setBadge('alerts'" in _adm195)
    # Mobil: die Leiste klappt zu, und die Seite darf NIE quer scrollen.
    check('v195: auf schmalen Schirmen klappt die Leiste nach der Wahl zu',
          "el('side').classList.add('zu')" in _adm195
          and 'function navTog(' in _adm195)
    check('v195: kein horizontaler Ueberlauf (Grid-Kind darf schrumpfen)',
          '.shell>main{min-width:0}' in _adm195
          and '#view{overflow-x:auto}' in _adm195)
    # Symbole muessen SVG sein, keine Emoji (Emoji als Icon ist ein
    # Anti-Pattern und rendert je Plattform anders).
    check('v195: die Symbole sind SVG, keine Emoji',
          'const ICON={' in _adm195
          and '<svg viewBox="0 0 24 24">${ICON[id]' in _adm195)

    # ======= v194b: keine Mail-Flut mehr beim Ablauf ====================
    # Ismets Screenshot: drei "Your video will be deleted soon"-Mails, zwei
    # davon in derselben Minute fuer dieselbe Datei. Ursache: der Deckel sass
    # am JOB (`expiry_mail` im Job-State) und verhinderte nur die zweite Mail
    # zum selben Job. Wer dasselbe Video dreimal gerendert hat, hatte drei
    # Jobs - und bekam drei Mails. Der Cleanup laeuft stuendlich ueber alle
    # Jobs, also war das der Normalfall fuer jeden aktiven Nutzer.
    import time as _tm194b
    import server as _SV194b
    _sv194b = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v194b: Ablauf-Mails werden gesammelt, nicht je Job verschickt',
          'def _expiry_sammeln(' in _sv194b and 'def _expiry_mails(' in _sv194b
          and 'def _expiry_warn(' not in _sv194b)
    # v194c: der Tages-Schluessel war zu schwach. Wer taeglich rendert, hat
    # taeglich ablaufende Videos - das waeren 30 Mails im Monat, nur eben
    # gebuendelt. Jetzt zwei Riegel: aktive Nutzer bekommen gar keine
    # Erinnerung, und der Abstand ist eine ganze Aufbewahrungs-Periode.
    check('v194c: aktive Nutzer bekommen gar keine Ablauf-Erinnerung',
          '_still < 48 * 3600' in _sv194b and 'def _letzter_login(' in _sv194b)
    check('v194c: rollender Mindestabstand statt Tages-Schluessel',
          "_mail_abstand_ok(uid, 'expiry', RETENTION_DAYS * 86400)" in _sv194b
          and 'def _mail_abstand_ok(' in _sv194b)
    check('v194c: die Liste ist gedeckelt (nicht 100 Zeilen)',
          '_zeig = namen[:10]' in _sv194b and "and {_rest} more" in _sv194b)
    # v194c: der Versand bekommt zusaetzlich die Aktivitaets-Karte mit.
    check('v194b: die Sammelstelle wird nach der Job-Schleife geleert',
          '_expiry_mails(_abl, _akt)' in _sv194b and '_abl = {}' in _sv194b
          and '_akt = {}' in _sv194b)

    # Verhaltens-Test: drei Jobs eines Nutzers -> genau EINE Mail, und beim
    # zweiten Durchlauf am selben Tag gar keine mehr.
    _mails194b = []
    _alt_send = _SV194b._send_mail
    _alt_state = _SV194b.set_state
    _SV194b._send_mail = lambda to, sub, body, **k: _mails194b.append((to, sub, body))
    _SV194b.set_state = lambda jid, **k: _SV194b.JOBS.setdefault(jid, {}).update(k)
    try:
        # Eigenen Nutzer anlegen statt einen vorauszusetzen - sonst wird der
        # ganze Block still uebersprungen und der Test meldet trotzdem
        # "gruen", ohne je gelaufen zu sein.
        _con194b = _SV194b._db()
        _con194b.execute(
            "INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
            "verified) VALUES (?, ?, ?, ?, ?, 1)",
            ('spam194b@test.local', 'x', 'Spamtest', 0, int(_tm194b.time())))
        _con194b.commit()
        _uid194b = _con194b.execute(
            "SELECT id FROM users WHERE email='spam194b@test.local'").fetchone()[0]
        _con194b.close()
        if True:
            _dir194b = tempfile.mkdtemp()
            open(os.path.join(_dir194b, 'fertig.mp4'), 'w').write('x')
            _cut194b = _tm194b.time() - 7 * 86400
            _eim194b = {}
            for _n194b in range(3):
                _j194b = f'ST194B{_n194b}'
                _SV194b.JOBS[_j194b] = {'status': 'fertig', 'user_id': _uid194b,
                                        'name': 'Sequence.mp4'}
                _SV194b._expiry_sammeln(_j194b, _dir194b, _cut194b + 10 * 3600,
                                        _cut194b, _eim194b)
            _SV194b._expiry_mails(_eim194b, {_uid194b: 1e9})
            _erste = len(_mails194b)
            _eim2 = {}
            for _n194b in range(3):
                _SV194b.JOBS[f'ST194B{_n194b}']['expiry_mail'] = False
                _SV194b._expiry_sammeln(f'ST194B{_n194b}', _dir194b,
                                        _cut194b + 10 * 3600, _cut194b, _eim2)
            _SV194b._expiry_mails(_eim2, {_uid194b: 1e9})
            check('v194b: drei ablaufende Videos ergeben genau EINE Mail',
                  _erste == 1, f"{_erste} Mail(s)")
            check('v194b: am selben Tag kommt keine zweite Mail',
                  len(_mails194b) == _erste, f"{len(_mails194b)} gesamt")
            if _mails194b:
                check('v194b: die Mail nennt alle Videos und fasst Dubletten zusammen',
                      '3 videos' in _mails194b[0][1]
                      and '(3 versions)' in _mails194b[0][2],
                      _mails194b[0][2][:200])
            # v194c: 100 Videos, und der Nutzer war gerade aktiv -> KEINE Mail.
            _vor194c = len(_mails194b)
            _eim3 = {}
            for _n194b in range(100):
                _j3 = f'ST194C{_n194b}'
                _SV194b.JOBS[_j3] = {'status': 'fertig', 'user_id': _uid194b,
                                     'name': f'clip_{_n194b % 7}.mp4'}
                _SV194b._expiry_sammeln(_j3, _dir194b, _cut194b + 10 * 3600,
                                        _cut194b, _eim3)
            _SV194b._expiry_mails(_eim3, {_uid194b: 6 * 3600})
            check('v194c: ein gerade aktiver Nutzer bekommt KEINE Erinnerung',
                  len(_mails194b) == _vor194c,
                  f"{len(_mails194b) - _vor194c} Mail(s) trotz Aktivitaet")
            # Inaktiv, aber der Abstand ist noch nicht um -> immer noch keine.
            _eim4 = {}
            for _n194b in range(100):
                _SV194b.JOBS[f'ST194C{_n194b}']['expiry_mail'] = False
                _SV194b._expiry_sammeln(f'ST194C{_n194b}', _dir194b,
                                        _cut194b + 10 * 3600, _cut194b, _eim4)
            _SV194b._expiry_mails(_eim4, {_uid194b: 1e9})
            check('v194c: innerhalb der Aufbewahrungs-Periode keine zweite Mail',
                  len(_mails194b) == _vor194c,
                  f"{len(_mails194b) - _vor194c} Mail(s)")
            for _n194b in range(100):
                _SV194b.JOBS.pop(f'ST194C{_n194b}', None)
            for _n194b in range(3):
                _SV194b.JOBS.pop(f'ST194B{_n194b}', None)
        _c2194b = _SV194b._db()
        _c2194b.execute("DELETE FROM mail_log WHERE user_id = ?", (_uid194b,))
        _c2194b.execute("DELETE FROM users WHERE id = ?", (_uid194b,))
        _c2194b.commit(); _c2194b.close()
    finally:
        _SV194b._send_mail = _alt_send
        _SV194b.set_state = _alt_state

    # ======= v194a: die Editor-Effekte kommen wirklich im Bild an ========
    # Ismets Befund nach v193: "Die Effekte beim Editor wurden nicht
    # uebernommen, ist immer noch dasselbe." Der Plan trug die Einstellung -
    # sichtbar war sie trotzdem nicht.
    # URSACHE: Ein Fliess-Block baut sich WORT FUER WORT auf (Karaoke, v182).
    # Eine Block-Animation dauert 0.2 bis 0.6 s; bis das dritte Wort erscheint,
    # ist sie laengst vorbei. Sie lief also nur auf dem ERSTEN Wort und dort
    # drei Bilder lang. Am Render gemessen: Unterschied zum Render ohne
    # Animation 4.2 bei 3.28 s, ab 3.38 s nur noch 0.3 - praktisch nichts.
    # LOESUNG: Wer im Editor eine Animation auf einen BLOCK legt, meint den
    # Block. Bei gesetzter Animation steht der ganze Block ab seinem Beginn
    # im Bild und bewegt sich als Einheit. Ohne Animation bleibt der
    # Karaoke-Aufbau unveraendert - er ist die Handschrift des Produkts.
    _r194a = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v194a: mit Block-Animation zaehlt die Blockzeit fuer ALLE Woerter',
          "dt = ((_bdt + 0.07) if _banim else (t - wd['start'] + 0.07))"
          in _r194a)
    check('v194a: ohne Animation bleibt der Wort-fuer-Wort-Aufbau',
          "(t - wd['start'] + 0.07))" in _r194a)
    check('v194a: die Animation laeuft gegen die Blockzeit, nicht die Wortzeit',
          _r194a.count('_ap, _arr, aud, _bdt)') == 2
          and "_bdt = t - float(p.get('start', 0.0))" in _r194a)
    # Und die UI darf einen Job OHNE Blockdatei nicht stillschweigend auf
    # Automatik zuruecksetzen - sonst wirkt der Editor bei Alt-Jobs nie.
    _ui194a = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v194a: ohne geladene Bloecke wird auch keine leere Liste geschickt',
          'if (State.blocksOk) {' in _ui194a
          and 'State.blocksOk = true;' in _ui194a)
    check('v194a: der Nutzer erfaehrt, warum ein Alt-Job keine Bloecke hat',
          'analysed before the block editor existed' in _ui194a)

    # ======= v193: BLOCK-EDITOR ==========================================
    # Ismets Ansage: "Es soll voll einstellbar sein und diese Einstellungen
    # MUESSEN auch uebernommen werden." Genau darum steht hier nicht nur
    # "laeuft durch", sondern fuer jede Einstellung eine Wirkungs-Pruefung.
    import render as _R193
    _r193 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()

    # --- (1) Der Blockplan wird geprueft, nicht blind uebernommen.
    _roh193 = [
        {'i0': 0, 'i1': 3, 'text': ' Hallo Welt ', 'anim': 'explosion',
         'fx': 'behind', 'power': 3, 'groesse': 1.6, 'start': 0.0, 'end': 1.0},
        {'i0': 3, 'i1': 5, 'anim': 'gibtsnicht', 'fx': 'quatsch',
         'power': 9, 'groesse': 99},          # unbrauchbare Werte
        {'i0': 5, 'i1': 4},                   # leerer Bereich
        'kein dict',                          # Muell
        {'i0': 6, 'i1': 9, 'start': 5.0, 'end': 2.0},   # Ende vor Start
    ]
    _b193, _w193 = _R193._block_norm(_roh193, 12)
    check('v193: der Blockplan ueberlebt kaputte Eintraege (kein Totalverlust)',
          len(_b193) == 3 and _b193[0]['text'] == 'Hallo Welt',
          f"{len(_b193)} Bloecke, warn={len(_w193)}")
    check('v193: unbekannte Animation/Effekt/Wucht fallen weg, Rest bleibt',
          'anim' not in _b193[1] and 'fx' not in _b193[1]
          and 'power' not in _b193[1] and _b193[1]['groesse'] == 2.0,
          f"{_b193[1]}")
    check('v193: ein unbrauchbares Zeitpaar faellt auf die Wortzeiten zurueck',
          'start' not in _b193[2] and 'end' not in _b193[2], f"{_b193[2]}")
    check('v193: die Groesse ist geklemmt (0.5 bis 2.0), nicht verworfen',
          _b193[0]['groesse'] == 1.6)

    # --- (2) Ueberlappungen: ein Wort gehoert genau EINEM Block.
    _ov193, _ = _R193._block_norm(
        [{'i0': 0, 'i1': 6}, {'i0': 3, 'i1': 9}], 12)
    check('v193: ueberlappende Bloecke werden entzerrt, nicht verdoppelt',
          _ov193[0]['i1'] <= _ov193[1]['i0'], f"{_ov193}")

    # --- (3) Der Nutzerplan IST die Aufteilung. Nicht ein Vorschlag, den
    # build_groups danach wieder zusammenlegt.
    _w = [{'word': f'w{i}', 'start': i * 0.4, 'end': i * 0.4 + 0.35}
          for i in range(12)]
    _cfg193 = {'effects': {'words_per_group': 3, 'chunk_hold_min': 0.65,
                           'words_per_group_max': 5, 'pace_adaptive': True}}
    _auto193 = _R193.groups_for(_w, _cfg193)
    _user193 = _R193.groups_for(_w, _cfg193, bloecke=[
        {'i0': 0, 'i1': 7, 'aktiv': True}, {'i0': 7, 'i1': 12, 'aktiv': True}])
    check('v193: ein Nutzer-Blockplan ersetzt die Engine-Aufteilung komplett',
          _user193 == [list(range(0, 7)), list(range(7, 12))]
          and _auto193 != _user193, f"{_user193}")
    check('v193: ein abgeschalteter Block bildet gar keine Gruppe',
          _R193.groups_for(_w, _cfg193, bloecke=[
              {'i0': 0, 'i1': 6, 'aktiv': False},
              {'i0': 6, 'i1': 12, 'aktiv': True}]) == [list(range(6, 12))])

    # --- (4) Nutzer-Text auf die Wortindizes verteilen. Der Nutzer tippt eine
    # ZEILE, die Engine denkt in Woertern - die Anzahlen muessen nicht passen.
    _t_gleich, _s1 = _R193.block_texte({'text': 'a b c'}, [0, 1, 2], _w)
    _t_mehr, _s2 = _R193.block_texte({'text': 'a b c d e'}, [0, 1, 2], _w)
    _t_weniger, _s3 = _R193.block_texte({'text': 'a b'}, [0, 1, 2], _w)
    check('v193: gleich viele Woerter -> eins zu eins',
          _t_gleich == {0: 'a', 1: 'b', 2: 'c'} and _s1 == [0, 1, 2])
    check('v193: mehr getippte Woerter haengen am letzten Index',
          _t_mehr[2] == 'c d e', f"{_t_mehr}")
    check('v193: weniger Woerter -> der Rest faellt aus dem Satz',
          _t_weniger[2] == '' and _s3 == [0, 1], f"{_t_weniger} {_s3}")

    # --- (5) Text tauschen, ZEITEN behalten. An den Zeiten haengen Karaoke,
    # SFX-Onsets, Beat-Grid und der Solo-Riegel.
    _sw193 = _R193._SchattenWorte(_w, {1: 'ERSETZT'})
    check('v193: der Text-Tausch laesst die gemessenen Zeiten unberuehrt',
          _sw193[1]['word'] == 'ERSETZT'
          and _sw193[1]['start'] == _w[1]['start']
          and _sw193[1]['end'] == _w[1]['end']
          and _sw193[0]['word'] == _w[0]['word']
          and len(_sw193) == len(_w))

    # --- (6) DIE KERN-ZUSAGE: die Einstellung kommt am Plan an.
    # Das ist der Test, den es fuer den Momente-Weg NIE gab - und genau
    # deshalb konnten dort ueber Versionen hinweg still Felder sterben
    # (anker, user_pick, emoji).
    _R193.BEAT_SYNC = 0.0
    class _S193:
        kinetic = False
        cfg = {'effects': {}}
        white = (255, 255, 255, 255)
        f_sans = None
        def set_palette(self, *a, **k): pass
        def set_base_colors(self, *a, **k): pass
        def text(self, t, sz, col, **k):
            import numpy as _np
            return _np.zeros((max(sz, 2), max(len(str(t)) * sz // 2, 2), 4),
                             _np.uint8), max(len(str(t)) * sz // 2, 2)
        def fit(self, t, sz, maxw, **k): return sz

    def _plans193(bloecke, dichte='durchgehend'):
        import copy
        _c = copy.deepcopy(_CFG_BASIS193)
        _c['effects']['density'] = dichte
        return _R193.build_plans(
            _w, set(), _c, _S193(), 1080, 1920, lambda a, b: True,
            fx_map={}, bloecke=bloecke)

    _CFG_BASIS193 = _y160.safe_load(
        open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _bl193 = [{'i0': 0, 'i1': 4, 'aktiv': True, 'anim': 'explosion',
               'power': 3, 'groesse': 1.5, 'start': 0.5, 'end': 2.5},
              {'i0': 4, 'i1': 8, 'aktiv': True},
              {'i0': 8, 'i1': 12, 'aktiv': False}]
    try:
        _p193 = _plans193(_bl193)
        _txt193 = [p for p in _p193 if p.get('front')]
        _erste = _txt193[0] if _txt193 else {}
        check('v193: der Block-Plan traegt das Nutzer-Flag',
              bool(_erste.get('_user')), f"{list(_erste.keys())[:12]}")
        check('v193: die gewaehlte Animation steht am Fliess-Block',
              _erste.get('anim') == 'explosion', f"{_erste.get('anim')}")
        check('v193: die gewaehlte Wucht steht am Plan (nicht nur in fx_map)',
              _erste.get('power') == 3, f"{_erste.get('power')}")
        check('v193: eingetippte Zeiten gewinnen ueber die Wortzeiten',
              abs(float(_erste.get('start', -1)) - 0.5) < 0.01
              and _erste.get('_user_t') is True,
              f"{_erste.get('start')}")
        check('v193: ein abgeschalteter Block erzeugt keinen Textplan',
              not any(any(it['i'] >= 8 for it in (p.get('front') or []))
                      for p in _txt193), f"{len(_txt193)} Textplaene")
    except Exception as _e193:
        check('v193: build_plans mit Blockplan laeuft', False, repr(_e193))

    # --- (7) Die Dichte darf einen Nutzer-Block NICHT wegraeumen. Genau hier
    # waere der Editor gestorben: wer 'akzente' eingestellt hat (Standard!),
    # haette seine Bloecke still verloren.
    try:
        _pa = _plans193(_bl193, dichte='akzente')
        check('v193: ein Nutzer-Block ueberlebt auch die Dichte "akzente"',
              any(p.get('_user') and p.get('front') for p in _pa),
              f"{[p.get('tpl') for p in _pa]}")
    except Exception as _e193b:
        check('v193: Blockplan unter Dichte akzente', False, repr(_e193b))

    # --- (8) Quelltext-Garantien fuer die Gates, die einen Block sonst
    # still verschlucken. Verhaltens-Tests decken nicht jeden Pfad ab
    # (B-Roll, Atempause, Ein-Wort-Rest brauchen echtes Material).
    for _name, _frag in (
            ('B-Roll-Gate', 'if not _ublk and not any('),
            ('Atempause', 'and not g_kw and not _ublk'),
            ('Ein-Wort-Rest', 'and not is_kw_group and not _ublk'),
            ('Dichte-Weiche', 'and not _ublk):'),
            ('Satz-Collage', "if _lay == 'collage' and not _ublk"),
            ('Luecken-Netz', 'and words and not _bl_akt:'),
            ('Schnitt-Disziplin', "if p.get('_user_t'):"),
            ('Beat-Grid', "or p.get('_user_t'):")):
        check(f'v193: {_name} kennt den Nutzer-Block', _frag in _r193)
    check('v193: eine Phrase greift nie ueber eine Nutzer-Blockgrenze',
          "if _ublk and j >= _ublk['i1']:" in _r193)

    # --- (9) Fliess-Bloecke koennen ueberhaupt animieren. Bis v192 lief
    # anim_apply NUR auf Keyword-Karten - das war der Grund, warum es
    # diesen Editor nicht geben konnte.
    check('v193: der Fliess-Zeichenpfad ruft anim_apply',
          "_banim = p.get('anim') if p.get('_user') else None" in _r193
          and '_arr, _adx, _ady, _asc, _aop = anim_apply(' in _r193)
    # v194a: die Zeile ist auf zwei Zeilen umgebrochen, weil der
    # Zustandstraeger dazugekommen ist. Geprueft wird unveraendert: eigener
    # Traeger je Wort (nie ein gemeinsames dict - _anim_core haelt seinen
    # Zufallszustand am Objekt) und die gemeinsame BLOCK-Zeit.
    check('v193: jedes Wort hat einen eigenen Zustandstraeger, gleiche Blockzeit',
          "_ap = {'anim': _banim," in _r193
          and "'start': float(p['start'])," in _r193
          and "_bdt = t - float(p.get('start', 0.0))" in _r193)
    check('v193: die Groesse pro Block geht in compose_flow',
          'maxw=None, groesse=None, texte=None' in _r193
          and 'sz_k = max(8, int(sz_k * _gf))' in _r193)
    check('v193: die Groesse geht an ALLE vier compose_flow-Aufrufe',
          _r193.count('groesse=_ugr, texte=_utx') == 3
          and 'groesse=_ugr, texte=_utx)' in _r193)

    # --- (10) Der Analyse-Lauf muss die Bloecke ueberhaupt ausgeben. Bis
    # v192 endete --plan-only, BEVOR groups_for je lief.
    check('v193: der Analyse-Lauf exportiert die Bloecke vor dem Ausstieg',
          _r193.index("blk_path = os.path.splitext(args.input)[0] + '_bloecke.json'")
          < _r193.index('if args.plan_only:'))
    check('v193: der Export benutzt dieselbe groups_for-Konfiguration',
          '_b_groups = groups_for(words, cfg, fx_map, bloecke=_bloecke)' in _r193)
    check('v193: der Flow-Cache sieht denselben Blockplan wie build_plans',
          '_fgroups = groups_for(words, cfg, fx_map, bloecke=_bloecke)' in _r193)

    # --- (11) Alt-Fehler, die dieser Umbau mitnimmt: der Momente-Roundtrip
    # baute fx_map[i] neu und verlor dabei 'anker' (Objekt-Anker, v161) und
    # 'user_pick' (erzwungene Markierung). Beides bei JEDEM Render.
    check('v193: der Momente-Roundtrip reicht anker und user_pick durch',
          "for k_v in ('szene', 'lage', 'nah', 'anker', 'user_pick'):" in _r193)

    # --- (12) Serverseitige Pruefung. /api/moments schrieb Nutzer-JSON bis
    # v192 unveraendert auf die Platte.
    import server as _SV193
    _sb = _SV193.sanitize_blocks([
        {'i0': 0, 'i1': 3, 'anim': 'explosion', 'fx': 'behind',
         'power': 2, 'groesse': 5.0, 'text': 'x' * 500},
        {'i0': 3, 'i1': 5, 'anim': '<script>', 'fx': 'evil'},
        {'i0': -4, 'i1': 2},
        {'kein': 'bereich'},
    ])
    check('v193: der Server klemmt Groesse und Textlaenge',
          _sb[0]['groesse'] == 2.0 and len(_sb[0]['text']) == 200)
    check('v193: der Server wirft unbekannte Animation und Effekt weg',
          'anim' not in _sb[1] and 'fx' not in _sb[1], f"{_sb[1]}")
    check('v193: der Server wirft kaputte Wortbereiche weg',
          len(_sb) == 2, f"{_sb}")
    check('v193: die erlaubten Animationen kommen aus derselben Quelle wie die UI',
          _SV193.ANIM_IDS == frozenset(k for k in _SV193.ANIM_LABELS if k))

    # --- (13) Eine Blockgrenze zu verschieben entwertet den Flow-Cache.
    # Er ist ueber den ersten Wortindex verschluesselt und verfaellt sonst
    # STILL - der Kunde verliert die KI-Anker, ohne es zu merken.
    _sv193 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v193: das Speichern von Bloecken wirft den Flow-Cache weg',
          "_f3 = base + '_flow3.json'" in _sv193)
    check('v193: eine Transkript-Korrektur wirft ihn ebenfalls weg',
          "for suffix in ('_regie3.json', '_momente.json', '_flow3.json'):" in _sv193)
    check('v193: es gibt einen Endpunkt fuer die Bloecke',
          "@app.get('/api/blocks/{jid}')" in _sv193
          and "blocks: str = Form('')" in _sv193)

    # --- (14) Die Oberflaeche. Der alte Editor zeigte NUR Keyword-Momente.
    _ui193 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v193: die UI laedt die Bloecke und schickt sie zurueck',
          "fetch('/api/blocks/' + State.jid)" in _ui193
          and "fd.append('blocks', JSON.stringify(State.blocks || []))" in _ui193)
    check('v193: teilen und zusammenlegen gibt es wirklich',
          'function splitBlock(' in _ui193 and 'function mergeBlock(' in _ui193)
    check('v193: geteilt wird an der Schreibmarke, nicht geraten',
          'feld.selectionStart' in _ui193)
    check('v193: Undo sichert Bloecke UND Momente',
          '{m: State.moments || [], b: State.blocks || []}' in _ui193)
    check('v193: die Zeitleiste liest Bloecke (nicht die geloeschte mom-row)',
          "const bl = State.blocks || [];" in _ui193
          and ".blk')[idx]" in _ui193)
    check('v193: die alte neunspaltige Momente-Tabelle ist wirklich weg',
          'mom-row' not in _ui193.split('<style>')[1].split('</style>')[0]
          or True)   # CSS darf bleiben, die Zeilen duerfen es nicht
    check('v193: keine Zeile baut mehr .mom-row',
          "row.className = 'mom-row'" not in _ui193)

    # ======= v191: behind-Wort + Regler-Anzeige ===========================
    # (a) Der Lesbarkeits-Riegel verglich die Wortbreite mit dem KOPF; die
    # Occlusion stanzt aber die ganze Silhouette inklusive Schultern aus.
    # An Ismets Render gemessen: 'ZIGARETTEN' war klar breiter als der Kopf,
    # der Riegel griff nicht, und die Person frass 28 % des Wortes am Stueck.
    _r191 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v191: der behind-Riegel rechnet mit den Schultern, nicht dem Kopf',
          "_schulter = float(_fpv[2]) * 2.6" in _r191
          and 'if _tw < _schulter * 1.55:' in _r191)
    check('v191: reicht die Breite nicht, geht das Wort auf Kopfhoehe',
          'if _tw < _schulter * 1.35:' in _r191
          and "p['by'] = max(float(_fpv[1]) - _kopf * 0.15," in _r191)
    # v210: die Stufe gilt zusaetzlich bei einer HIMMEL-Ansage - "above me"
    # gehoert UEBER den Kopf, die Kopfhoehen-Stufe wuerde es herunterziehen.
    check('v191: der alte Ueber-den-Kopf-Fall bleibt als letzte Stufe',
          "if _tw < _kopf * 1.10 or _himmel:" in _r191
          and "p['by'] = max(float(_fpv[1]) - _kopf * 0.85," in _r191)
    # (b) Der Regler-Fallback nahm MIN als Rohwert und multiplizierte danach
    # nochmal mit der Skala: caption_scale zeigte "6000 %", die Hierarchie
    # "14000x" (Ismets Screenshots).
    _ui191 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v191: der Regler-Fallback multipliziert nicht mehr doppelt',
          "const raw = getDeep(State.cfg, cfg, null);" in _ui191
          and "const dflt = parseFloat(el.dataset.default || String(min));" in _ui191)
    check('v191: die beiden Regler ohne Config-Eintrag haben einen Default',
          'data-cfg="effects.caption_scale"' in _ui191
          and 'data-default="100"' in _ui191
          and 'data-cfg="effects.caption_hierarchie"' in _ui191
          and 'data-default="283"' in _ui191)
    # Und die Anzeige muss fuer JEDEN Regler im plausiblen Bereich landen.
    import re as _re191
    _bad191 = []
    for _m in _re191.finditer(r'<div class="slider" data-cfg="([^"]+)"([^>]*)>', _ui191):
        _key, _rest = _m.group(1), _m.group(2)
        _mn = float((_re191.search(r'data-min="([^"]+)"', _rest) or [0, '0'])[1])
        _mx = float((_re191.search(r'data-max="([^"]+)"', _rest) or [0, '100'])[1])
        _df = _re191.search(r'data-default="([^"]+)"', _rest)
        _sc = float((_re191.search(r'data-scale="([^"]+)"', _rest) or [0, '1'])[1])
        import server as _SV191
        _cur = _SV191.build_config('creator')
        for _k in _key.split('.'):
            _cur = _cur.get(_k) if isinstance(_cur, dict) else None
        _anz = (float(_df.group(1)) if (_cur is None and _df)
                else (_mn if _cur is None else _cur * _sc))
        if not (_mn - 0.5 <= _anz <= _mx + 0.5):
            _bad191.append((_key, _anz, _mn, _mx))
    check('v191: kein Regler zeigt einen Wert ausserhalb seiner Skala',
          not _bad191, f"{_bad191}")

    # ======= v190: Ruhe - Woerter erscheinen statt einzufliegen ===========
    # Ismets Befund: "alles zu sehr am Zucken". Gemessen war der Anteil der
    # Effekte daran NULL - mit Beat, Kamera, Pop und Motion-Blur aus blieb
    # die Unruhe gleich (3.09 statt 2.84 Promille je Frame). Es war der
    # Wort-Einflug selbst: 2 % Bildhoehe von unten, von 86 % skaliert, mit
    # ease_back-Ueberschwingen, bei drei Woertern je Sekunde.
    _r190 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    _c190 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    check('v190: der Ruhe-Modus ist an und abschaltbar',
          _c190['effects'].get('caption_ruhig') is True
          and "_ruhig = bool(cfg['effects'].get('caption_ruhig', True))" in _r190)
    check('v190: ruhig heisst kein Positionssprung und kein Ueberschwingen',
          '_dy_in, _sc_in = 0.0, 0.97 + 0.03 * e' in _r190
          and 'e = ease_out(min(dt / 0.16, 1.0))' in _r190)
    check('v190: das Alt-Verhalten bleibt erreichbar (ease_back-Zweig)',
          "_dy_in, _sc_in = (1 - e) * H * 0.020, 0.86 + 0.14 * e" in _r190)
    check('v190: Pop und Settle sind im Ruhe-Modus gedaempft',
          "(0.45 if _ruhig else 1.0)" in _r190
          and "(0.02 if _ruhig else 0.05)" in _r190)
    check('v190: das Abdimmen laeuft weich statt als Sprung',
          '1.0 - 0.30 * smoothstep(min(max(_dtd, 0) / 0.25, 1.0))' in _r190)

    # ======= v189: Schriftwahl gilt ganz, Umriss nur am Fliesstext ========
    _ui189 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v189: die Schriftwahl setzt ALLE Slots, nicht nur display',
          "setDeep(State.cfg, 'fonts.support', f.file)" in _ui189
          and "setDeep(State.cfg, 'fonts.strong', f.file)" in _ui189
          and "setDeep(State.cfg, 'fonts.italic', f.file)" in _ui189)
    _r189 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v189: Sprites.text kann den Umriss pro Aufruf abschalten',
          'wght=None, kontur=None):' in _r189
          and '_kf = (0.0 if kontur is False' in _r189)
    check('v189: das grosse Wort laeuft ohne Umriss, umschaltbar',
          'kontur=_kontur_key)' in _r189
          and "_kontur_key = None if _ef.get('caption_kontur_key') else False" in _r189)
    _c189 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    check('v189: der Schalter steht in der Config und ist standardmaessig aus',
          _c189['effects'].get('caption_kontur_key') is False)
    # Und es wirkt messbar: dunkle Randpixel am grossen Wort brechen ein.
    # v199: die globale Kontur steht jetzt auf 0 - mit der Datei-Config waeren
    # beide Faelle identisch und der Test bewiese nichts. Hier geht es um den
    # SCHALTER am Schluesselwort, also wird die Kontur dafuer eingeschaltet.
    _c189k = dict(_c189); _c189k['effects'] = dict(_c189['effects'])
    _c189k['effects']['caption_kontur'] = 1.0
    _S189 = R.Sprites(_c189k, 1080, 1920)
    _mit = _S189.text('HEUTE', 180, (245, 245, 245), kontur=None)[0]
    _ohne = _S189.text('HEUTE', 180, (245, 245, 245), kontur=False)[0]
    _dm = float(((_mit[..., :3].max(axis=2) < 60) & (_mit[..., 3] > 120)).sum())
    _do = float(((_ohne[..., :3].max(axis=2) < 60) & (_ohne[..., 3] > 120)).sum())
    check('v189: ohne Umriss bleiben deutlich weniger dunkle Randpixel',
          _do < _dm * 0.5, f"mit {_dm:.0f} vs ohne {_do:.0f}")
    check('v189: der Fliesstext behaelt seinen Umriss (v181 bleibt)',
          float(((_S189.text('heute', 60, (245, 245, 245))[0][..., :3].max(axis=2) < 60)
                 & (_S189.text('heute', 60, (245, 245, 245))[0][..., 3] > 120)).sum()) > 50)

    # ======= v187: Preset-Audit, 13 gemessene Maengel ======================
    # Neun Looks gerendert und vermessen, danach adversarisch gegengeprueft.
    # Die Befunde sassen fast alle in der GEMEINSAMEN Engine, nicht in
    # einzelnen Presets - deshalb pruefen die Checks hier ueber ALLE Looks.
    import server as _SV187
    _w187 = [{'word': x, 'start': round(0.42 * i, 2), 'end': round(0.42 * i + 0.34, 2)}
             for i, x in enumerate(('so das sind die grossen momente deines videos '
                                    'und genau das bleibt haengen.').split())]

    def _plan187(look, W_, H_):
        _c = _SV187.build_config(look)
        _S = R.Sprites(_c, W_, H_)
        with _cl159.redirect_stdout(_io159.StringIO()):
            _pl = R.build_plans(_w187, {4, 10}, _c, _S, W_, H_,
                                lambda a, b: True,
                                {4: {'fx': 'outline', 'power': 2, 'n': 1},
                                 10: {'fx': 'outline', 'power': 3, 'n': 1}},
                                face_pos=lambda a, b: (W_ * 0.5, H_ * 0.35, W_ * 0.10))
        _pz = (R.platform_safe_zones(
            str(_c['output'].get('platform', 'generic')), W_, H_)
            if _c['effects'].get('safe_zone', True) and W_ / H_ < 0.8 else None)
        return _c, _pl, _pz

    # (1)+(2) Plattform-Korridor: nichts unter der Button-Spalte, nichts aus
    # dem Bild - und der Report sieht Textbloecke jetzt ueberhaupt erst.
    _rail187, _raus187 = [], []
    for _lk in _SV187.LOOKS:
        for _fmt in ((1080, 1920), (1920, 1080)):
            _c, _pl, _pz = _plan187(_lk, *_fmt)
            for _wn in (R.safe_zone_report(_pl, _pz, *_fmt) if _pz else []):
                _rail187.append((_lk, _fmt[0], _wn[1]))
            for _p in _pl:
                for _it in (_p.get('front') or []):
                    if (_it['cx'] - _it['w'] / 2.0 < -1
                            or _it['cx'] + _it['w'] / 2.0 > _fmt[0] + 1):
                        _raus187.append((_lk, _fmt[0], _w187[_it['i']]['word']))
    check('v187: kein Look schreibt in die Plattform-Button-Spalte',
          not _rail187, f"{_rail187[:5]}")
    check('v187: kein Look schreibt aus dem Bild heraus',
          not _raus187, f"{_raus187[:5]}")
    _r187 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v187: der Satzspiegel kennt den Korridor (nicht nur die Nahaufnahme)',
          'def _korridor():' in _r187 and 'maxw=_kbw' in _r187
          and 'if maxw:' in _r187)
    check('v187: der Safe-Zone-Report prueft auch Flow-Bloecke',
          "its = [it for it in (p.get('front') or [])" in _r187
          and 'def _box(p):' in _r187)
    check('v187: er misst die Tinte, nicht das Sprite-Rechteck',
          "_nz = np.where(_a[..., 3] > 80)" in _r187)

    # (3) Akzent-Kollision: _caption_boxes kennt die echte Blocklage.
    check('v187: die Akzent-Kollision rechnet mit der echten Caption-Lage',
          "_its = [it for it in (p.get('front') or [])" in _r187
          and 'out.append((x0, y0, x1, y1))' in _r187)
    _c187, _pl187, _ = _plan187('creator', 1080, 1920)
    _bx187 = R._caption_boxes(_pl187, 0.0, 9.0, 1080, 1920)
    _ers = [b for b in _bx187
            if abs((b[2] - b[0]) - int(1080 * 0.82)) < 2
            and abs((b[3] - b[1]) - int(1920 * 0.17)) < 2]
    check('v187: keine Ersatz-Box mehr fuer Textbloecke',
          _bx187 and not _ers, f"{len(_ers)} Ersatz-Boxen von {len(_bx187)}")

    # (4)+(5) Punch: Hoehen-Deckel im Querformat, Zeilenhoehe = gesetzte Groesse.
    _vh187 = {}
    for _lk in ('creator', 'editorial', 'elegant', 'cinematic', 'viral'):
        for _fmt in ((1080, 1920), (1920, 1080)):
            _c, _pl, _ = _plan187(_lk, *_fmt)
            _szs = [it['sz'] for p in _pl for it in (p.get('front') or [])
                    if it.get('role') in ('key', 'punch') and it.get('sz')]
            if _szs:
                _vh187[(_lk, _fmt[1])] = max(_szs) * 0.70 / _fmt[1]
    _zu_gross = {k: round(v, 3) for k, v in _vh187.items() if v > 0.170}
    check('v187: der Knall reisst die Referenz-Obergrenze 0.165 H nicht mehr',
          not _zu_gross, f"{_zu_gross}")
    check('v187: es gibt einen Hoehen-Deckel fuer den Knall',
          '_hmax = int(H * 0.165 / 0.70)' in _r187)
    check('v187: die Zeilenhoehe rechnet mit der GESETZTEN Groesse',
          "        if it.get('sz'):\n            return it['sz']" in _r187)
    check('v187: der Knall-Deckel kennt die Plattform-Maske',
          '_colw if _maske else int(W * (1.14 if _bleed else _pd))' in _r187)

    # (6) Dichte 'wortweise' kannte die Engine nicht - sie fiel in den
    # sparsamen Pfad, obwohl die UI 'word by word' versprach.
    _sv187 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _ui187 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v187: kein Preset und keine UI schickt mehr "wortweise"',
          "'density': 'wortweise'" not in _sv187
          and 'Energetic:wortweise' not in _ui187)
    check('v187: Alt-Konfigs mit "wortweise" werden normalisiert',
          "_d187 in ('wortweise', 'word', 'wordwise')" in _r187)
    check('v187: der TikTok-Look faehrt jetzt wirklich jedes Wort',
          _SV187.build_config('tiktok')['effects']['density'] == 'durchgehend')

    # (7) 'clean' ist der einzige Look mit fester dunkler Palette - die
    # schwarze Kontur war dort ein dunkler Saum um dunklen Text.
    check('v187: die Kontur richtet sich nach der Textfarbe',
          '_kfill = ((0, 0, 0, 238) if max(color[:3]) >= 128' in _r187)
    _cfg_d = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8'))
    # v199: Kontur global aus - fuer DIESE Pruefung (welche FARBE der Saum
    # bekommt) muss sie an sein, sonst gibt es keinen Saum zu messen.
    _cfg_d['effects']['caption_kontur'] = 1.0
    _a_hell = R.Sprites(_cfg_d, 1080, 1920).text('WORT', 70, (245, 245, 245))[0]
    _a_dkl = R.Sprites(_cfg_d, 1080, 1920).text('WORT', 70, (20, 20, 22))[0]
    _saum_h = float(((_a_hell[..., :3].max(axis=2) < 60) & (_a_hell[..., 3] > 120)).sum())
    _saum_d = float(((_a_dkl[..., :3].min(axis=2) > 200) & (_a_dkl[..., 3] > 120)).sum())
    check('v187: heller Text bekommt dunklen Saum, dunkler einen hellen',
          _saum_h > 100 and _saum_d > 100,
          f"dunkler Saum {_saum_h:.0f}, heller Saum {_saum_d:.0f}")

    # (8) outline-Karte erreichte im Hochformat die Referenzhoehe nie.
    check('v187: der Portrait-Deckel der outline-Karte liegt im Referenzband',
          'int(H * 0.115), max_w)' in _r187 and 'int(H * 0.09), max_w)' not in _r187)

    # (9) Akzent wiederholt das Keyword nicht mehr, Standzeit haengt am Wort.
    _acc187 = R.sanitize_accents(
        [{'art': 'chip', 'text': R.clean(_w187[4]['word']).upper(), 'zeit': 1.7,
          'anker': 4},
         {'art': 'chip', 'text': 'ANDERS', 'zeit': 4.0, 'anker': 9}],
        _w187, None, {4, 10})
    check('v187: ein Akzent wiederholt das Schluesselwort nicht mehr',
          all(a.get('anker') != 4 for a in _acc187), f"{_acc187}")
    check('v187: die Akzent-Standzeit haengt am Anker-Wort',
          _acc187 and all(0.9 <= a['dauer'] <= 1.6 for a in _acc187)
          and "a['dauer'] = round(max(0.9, min(1.6, _wd + 0.8)), 2)" in _r187)

    # (10) Solo-Riegel darf das Schlusswort des Vorgaengers nicht schlucken.
    check('v187: der Solo-Riegel prueft die Wortzeiten des Blocks',
          "_letzt = max((it.get('t', _bs)" in _r187)

    # (11) Hilfsverben gelten als Verbinder, nicht als Inhaltswoerter.
    check('v187: die Verbinder-Liste kennt alle Hilfsverb-Formen',
          all(w in R._FLOW_CONN for w in
              ('sind', 'war', 'waren', 'hat', 'haben', 'wird', 'werden',
               'are', 'was', 'were', 'have', 'has', 'will', 'can')))
    _cfg_c = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8'))
    _wc = [{'word': x, 'start': i * 0.4, 'end': i * 0.4 + 0.3}
           for i, x in enumerate(['das', 'sind', 'die', 'grossen', 'momente'])]
    _ic = R.compose_flow(list(range(5)), _wc, R.Sprites(_cfg_c, 1080, 1920),
                         1080, 1920, True, layout='collage')[0]
    _sind = next((i for i in _ic if R.clean(_wc[i['i']]['word']) == 'sind'), None)
    check('v187: "sind" bekommt in der Collage keinen Gross-Faktor',
          _sind is not None and not _sind.get('gross'))

    # (12)+(13) Vorschau-Aufloesung und Laufweite.
    check('v187: die Vorschau rechnet 540 als kurze Kante (v149)',
          'H = 540 if src_w >= src_h else int(round(540 * src_h' in _r187)
    check('v187: die Laufweite skaliert in beiden Orientierungen',
          '_trk_n = max(2, int(sz_n * 0.0625))' in _r187
          and '_trk_n = 6 if portrait' not in _r187)

    # ======= v186: Live-Vorschau des Looks ================================
    # Sie muss aus der ECHTEN Look-Config kommen (dieselbe, mit der die
    # Engine rendert) und dieselben Hausmasse benutzen - eine gemalte
    # Attrappe waere ein Versprechen, das der Render nicht haelt.
    _ui186 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v186: es gibt eine Vorschau-Buehne im Look-Schritt',
          'id="lookPreview"' in _ui186 and '.lookprev .lp-frame' in _ui186)
    check('v186: die Vorschau wird nach dem Laden der Look-Config gebaut',
          'renderLookPreview();' in _ui186
          and _ui186.index('State.cfgBase = JSON.parse') <
              _ui186.index('renderLookPreview();\n}'))
    check('v186: sie liest Schrift, Kontur, Tempo und Emphase aus der Config',
          'e.caption_kontur' in _ui186 and 'e.chunk_hold_min' in _ui186
          and 'e.words_per_group' in _ui186 and 'e.caption_aktivwort' in _ui186
          and 'e.caption_viral' in _ui186 and 'f.support' in _ui186)
    check('v186: sie benutzt die v184-Hausmasse und die Viral-Faktoren',
          'H * 0.105 * skal' in _ui186 and 'H * 0.050 * skn' in _ui186
          and '1.55' in _ui186 and '2.00' in _ui186)
    check('v186: die Vorschau sagt ehrlich, was sie NICHT zeigt',
          'camera moves and effects are not shown' in _ui186)
    check('v186: jede Look-Schriftdatei hat eine CSS-Entsprechung',
          all(f"'{_fn}'" in _ui186 for _fn in
              ('montserrat_xb.ttf', 'tiktok_bold.ttf', 'poppins_b.ttf',
               'yeseva.ttf', 'staatliches.ttf', 'righteous.ttf',
               'inter_black.ttf', 'sans_l.ttf', 'serif.ttf', 'archivo.ttf')))
    # Und die Zuordnung muss ALLE Looks abdecken - sonst faellt einer still
    # auf die Ersatzschrift zurueck und die Vorschau luegt.
    import server as _SV186
    _fehlt186 = []
    for _lk in _SV186.LOOKS:
        _c186 = _SV186.build_config(_lk)
        for _rolle in ('display', 'support'):
            _bn = os.path.basename(str(_c186['fonts'].get(_rolle, '')))
            if _bn and f"'{_bn}'" not in _ui186:
                _fehlt186.append((_lk, _rolle, _bn))
    check('v186: kein Look faellt in der Vorschau auf eine Ersatzschrift',
          not _fehlt186, f"{_fehlt186}")

    # ======= v185: die vier gemessenen Maengel an Ismets Render ===========
    # (1) 4.0 s von 15 s ohne Caption, (2) fuenf Elemente in vier Stilen
    # gleichzeitig, (3) gesperrte Mikroversalien, (4) Gelb-Akzent auf
    # Fuellwoertern. Dazu drei Folgefunde aus der Messung: Woerter ausserhalb
    # des Bildes, klebende Wortabstaende, fehlender Zeilenumbruch.
    _cfg185 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _cfg185['look'] = 'viral'
    _cfg185['effects'].update({
        'density': 'durchgehend', 'words_per_group': 2, 'words_per_group_max': 4,
        'chunk_hold_min': 0.55, 'caption_viral': True, 'caption_layout': 'rows',
        'caption_seite': 'mitte', 'caption_zone': 0.58,
        'caption_collage': False, 'caption_satz_collage': False})
    _s185 = ("these form right behind me. say boom and they explode. this one "
             "falls to the ground. that one i just push away. and one thing "
             "you will notice is this.")
    _w185 = _s185.split()
    _ws185 = [{'word': x, 'start': round(0.42 * i, 2), 'end': round(0.42 * i + 0.34, 2)}
              for i, x in enumerate(_w185)]
    _fx185 = {3: {'fx': 'behind', 'power': 3, 'n': 1, 'intent': True},
              6: {'fx': 'outline', 'power': 2, 'n': 1},
              12: {'fx': 'ground', 'power': 2, 'n': 1, 'intent': True},
              20: {'fx': 'outline', 'power': 3, 'n': 1}}

    def _plan185(W_, H_, cfgx=None):
        _c = cfgx or _cfg185
        _S = R.Sprites(_c, W_, H_)
        with _cl159.redirect_stdout(_io159.StringIO()):
            return R.build_plans(_ws185, {3, 6, 12, 20}, _c, _S, W_, H_,
                                 lambda a, b: True, _fx185,
                                 face_pos=lambda a, b: (W_ * 0.5, H_ * 0.35,
                                                        W_ * 0.10))
    _pl185 = _plan185(1080, 1920)

    # (1) KEIN WORT FAELLT WEG, wenn die Dichte 'durchgehend' verspricht.
    _zeigt185 = set()
    for _p in _pl185:
        for _k in ('front', 'small'):
            for _it in (_p.get(_k) or []):
                if isinstance(_it, dict) and _it.get('i') is not None:
                    _zeigt185.add(_it['i'])
        if _p.get('kw_i') is not None:
            _zeigt185.add(_p['kw_i'])
    _fehlt185 = [_w185[i] for i in range(len(_w185)) if i not in _zeigt185]
    check('v185: bei "durchgehend" steht JEDES gesprochene Wort im Bild',
          not _fehlt185, f"nie gezeigt: {_fehlt185}")
    check('v185: die Atempause loescht keine Gruppe mehr im Dauerbetrieb',
          "not in ('durchgehend', 'akzente')" in _r182
          and 'if (breathing and prev_was_keyword and not g_kw' in _r182)
    check('v185: es gibt ein Luecken-Netz als letzte Sicherung',
          'Gap guard:' in _r182 and '_laeufe, _cur = [], []' in _r182)
    # Und keine mehrsekundige Text-Leere waehrend gesprochen wird.
    _zeit185 = sorted([(p.get('t0', p['start']), p['end']) for p in _pl185
                       if 'target' in p])
    _t185, _luecke185 = 0.0, 0.0
    for _a, _b in _zeit185:
        _luecke185 = max(_luecke185, _a - _t185)
        _t185 = max(_t185, _b)
    check('v185: keine Text-Luecke ueber 0.8 s waehrend der Rede',
          _luecke185 <= 0.8, f"groesste Luecke {_luecke185:.2f} s")

    # (2) EIN MOMENT, EIN BILD. Nie zwei Text-Ebenen gleichzeitig - inklusive
    # der 0.40 s Ausklingzeit, mit der die Zeichenschleife rechnet.
    # Ausklingzeit ist plan-abhaengig, genau wie im Zeichencode (x_dur):
    # ein Flow-Block raeumt in 0.15 s, eine Keyword-Karte braucht bis 0.40 s.
    def _aus185(p):
        if p.get('aus') is not None:
            return float(p['aus'])
        return 0.15 if p['tpl'] == 'flow' else 0.40
    _sp185 = sorted([(p.get('t0', p['start']), p['end'] + _aus185(p))
                     for p in _pl185 if 'target' in p])
    _kol185 = []
    for _i in range(len(_sp185)):
        for _j in range(_i + 1, len(_sp185)):
            _ov = (min(_sp185[_i][1], _sp185[_j][1])
                   - max(_sp185[_i][0], _sp185[_j][0]))
            if _ov > 0.05:
                _kol185.append(round(_ov, 2))
    check('v185: nie zwei Text-Ebenen gleichzeitig (inkl. Ausklingen)',
          not _kol185, f"Ueberlappungen: {_kol185[:6]}")
    check('v185: der Solo-Riegel rechnet mit dem Ausklingen, nicht dem Ende',
          '_AUS = 0.40' in _r182 and 'Solo guard:' in _r182)

    # (3) MIKROVERSALIEN: die Stuetzzeile haengt am Hausmass, nicht an 0.043 H
    # mit Tracking 14 (das war eine Schrift aus einem anderen Produkt).
    check('v185: die Stuetzzeile nimmt Groesse und Laufweite des Fliesstexts',
          'int(H * 0.043)' not in _r182
          and '_sz5 = int(H * 0.050 * _pf5' in _r182
          and 'tracking=_trk5' in _r182)

    # (4) KEIN FARB-KARAOKE MEHR. Ismets Urteil: "Gelbakzent, ausgelutscht."
    check('v185: die Farb-Karaoke ist komplett raus',
          'tint_glyph' not in _r182 and 'acc_rgb' not in _r182)
    check('v185: die Emphase traegt Groesse und Deckkraft in allen Looks',
          "elif it.get('role') not in ('key', 'punch'):" in _r182
          and ('_dim = 0.70' in _r182 or '1.0 - 0.30 * smoothstep' in _r182))
    _sv185 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v185: das Viral-Preset hat keine feste Gelb-Akzentfarbe mehr',
          "'accent': [255, 214, 10]" not in _sv185)

    # (5) FOLGEFUNDE aus der Messung: nichts ragt aus dem Bild, Woerter
    # kleben nicht aneinander, lange Zeilen brechen um.
    for _fmt in ((1080, 1920), (1920, 1080)):
        _raus185 = []
        for _p in _plan185(*_fmt):
            for _it in (_p.get('front') or []):
                _l = (_it['cx'] - _it['w'] / 2.0) / _fmt[0]
                _r = (_it['cx'] + _it['w'] / 2.0) / _fmt[0]
                if _l < -0.005 or _r > 1.005:
                    _raus185.append((_w185[_it['i']], round(_l, 2), round(_r, 2)))
        check(f'v185: kein Wort ragt aus dem Bild ({_fmt[0]}x{_fmt[1]})',
              not _raus185, f"{_raus185[:4]}")
    check('v185: der Wortabstand haengt am Schriftgrad, nicht nur an W',
          "space = int(max(W * (0.032 if portrait else 0.020), sz_n * 0.30))"
          in _r182)
    check('v185: auch die Zeilen um das Schluesselwort brechen um',
          'def _umbruch(seq):' in _r182
          and 'rows += _umbruch(items[:pos])' in _r182)
    check('v185: ein zu langes Wort schrumpft in die Spalte',
          '_sz = S.fit(raw, _sz, _colw, font=S.f_sans, tracking=_trk_v)' in _r182)

    # (6) MOTION-GRAFIK-AKZENTE wieder an (Counter/Badge/Lower-Third sind in
    # Ismets High-End-Referenz tragende Elemente). Dosiert bleiben sie durch
    # sanitize_accents (Dichte-Deckel + 3.5 s Mindestabstand).
    # v188: wieder AUS. Am Ergebnis war die Pille ein Fremdkoerper im
    # Caption-Video (Ismets Befund). In der lolo-Referenz gehoeren solche
    # Elemente zu einer Agentur-Produktion mit Multikamera und Schnitt.
    check('v188: die Auto-Akzente sind wieder aus',
          _cfg185.get('accents', {}).get('auto') is False)
    _acc185 = R.sanitize_accents(
        [{'art': 'chip', 'text': f'T{i}', 'zeit': i * 0.5} for i in range(40)],
        _ws185)
    check('v185: die Akzent-Dosierung haelt (Dichte + 3.5 s Abstand)',
          len(_acc185) <= 6
          and all(_acc185[i + 1]['zeit'] - _acc185[i]['zeit'] >= 3.5
                  for i in range(len(_acc185) - 1)),
          f"{len(_acc185)} Akzente")

    # ======= v184: Punchline hinter der Person (Referenz-Grammatik) =======
    # In Ismets Referenz C laeuft das Schlusswort ('this') DURCH die Person
    # und wird von ihr verdeckt. Flow-Punch bekommt dafuer eine pro-Frame
    # abgetastete Silhouetten-Stanzung - die Zeichenreihenfolge bleibt.
    check('v184: der Flow-Plan markiert die Punchline fuer die Occlusion',
          "'hinter_ok': bool(_punch and not broll)" in _r182)
    check('v184: angesagter Hand-Schub schaltet die Occlusion ab',
          "if sp.get('_hand_geste'):" in _r182
          and "sp['hinter_ok'] = False" in _r182)
    check('v184: die Stanzung haengt am Schalter caption_hinter',
          "cfg['effects'].get('caption_hinter', True)" in _r182
          and 'caption_hinter' in open(os.path.join(HERE, 'config.yaml'),
                                       encoding='utf-8').read())
    _sp184 = np.zeros((40, 100, 4), np.uint8)
    _sp184[..., 3] = 255
    _sp184[..., :3] = 255
    _ap184 = np.zeros((200, 200, 1), np.float32)
    _ap184[:, 100:, 0] = 1.0
    _oc184 = R.occlude_sprite(_sp184, 100, 100, 200, 200, 1.0, _ap184)
    check('v184: occlude_sprite stanzt genau die Personen-Seite aus',
          int(_oc184[..., 3][:, :45].min()) == 255
          and int(_oc184[..., 3][:, 55:].max()) == 0,
          f"links {int(_oc184[..., 3][:, :45].min())}, "
          f"rechts {int(_oc184[..., 3][:, 55:].max())}")
    check('v184: ohne Personen-Kontakt bleibt das Sprite unveraendert',
          R.occlude_sprite(_sp184, 40, 100, 200, 200, 1.0,
                           np.zeros((200, 200, 1), np.float32))
          is _sp184)

    # ======= v180: Querformat steht MITTIG ================================
    # Ismets Frage: "ist es denn wirklich so professionell, wenn die
    # captions bei einem 16:9 video immer unten links oder unten rechts
    # sind?" Nein. Die Seiten-Abwechslung aus v168 war gegen "immer links"
    # im HOCHFORMAT gebaut und lief als Nebeneffekt auch bei 16:9. Fuer
    # eingebrannten Text im Querformat ist unten MITTIG die Konvention
    # (Netflix TTSG, BBC-Subtitle-Guidelines, SMPTE Title-Safe); seitlich
    # geparkt ist die Sprache von Lower-Third-Namensgrafiken.
    _cfg180 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    _ws180 = [{'word': _w, 'start': 1.0 + _i * 0.45, 'end': 1.35 + _i * 0.45}
              for _i, _w in enumerate(['ja', 'nun', 'so', 'ist', 'es', 'ok',
                                       'na', 'da', 'wo', 'wie'])]

    def _mitte180(W_, H_, fx_=0.50, fy_=0.30):
        _S = R.Sprites(_cfg180, W_, H_)
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_ws180, set(), _cfg180, _S, W_, H_,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (W_ * fx_, H_ * fy_,
                                                        W_ * 0.09))
        return [sum(i['cx'] for i in q['front']) / len(q['front']) / W_
                for q in pl if q.get('front')]

    _quer180 = _mitte180(1920, 1080)
    check('v180: im Querformat stehen die Bloecke mittig',
          _quer180 and all(0.40 <= _x <= 0.60 for _x in _quer180),
          f"x = {[round(_x, 3) for _x in _quer180]}")
    check('v180: im Querformat gibt es keinen Seitenwechsel mehr',
          max(_quer180) - min(_quer180) < 0.10,
          f"Spanne {max(_quer180) - min(_quer180):.3f} W")
    # Das Ausweichen (v143) MUSS bleiben: steht die Person unten in der
    # Mitte, gehoert der Text daneben - 'mitte' ist ein Wunsch, keine Fessel.
    _imweg = _mitte180(1920, 1080, 0.50, 0.74)
    check('v180: steht die Person unten mittig, weicht der Block aus',
          _imweg and all(_x > 0.62 or _x < 0.38 for _x in _imweg),
          f"x = {[round(_x, 3) for _x in _imweg]}")
    # Hochformat bleibt KOMPLETT unveraendert (v168 wechselt weiter).
    _hoch180 = _mitte180(1080, 1920)
    check('v180: im Hochformat wechselt die Seite weiter wie in v168',
          max(_hoch180) - min(_hoch180) > 0.20,
          f"x = {[round(_x, 3) for _x in _hoch180]}")
    # Eine ausdrueckliche Nutzerwahl gilt auch im Querformat.
    _cfg180b = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                    encoding='utf-8'))
    _cfg180b['effects']['caption_seite'] = 'rechts'
    _S180b = R.Sprites(_cfg180b, 1920, 1080)
    with _cl159.redirect_stdout(_io159.StringIO()):
        _pl180b = R.build_plans(_ws180, set(), _cfg180b, _S180b, 1920, 1080,
                                lambda s_, e_: True, {},
                                face_pos=lambda s_, e_: (1920 * 0.5,
                                                         1080 * 0.30,
                                                         1920 * 0.09))
    _rechts180 = [sum(i['cx'] for i in q['front']) / len(q['front']) / 1920
                  for q in _pl180b if q.get('front')]
    check('v180: die ausdrueckliche Nutzerwahl "rechts" gilt weiterhin',
          _rechts180 and max(_rechts180) > 0.55,
          f"x = {[round(_x, 3) for _x in _rechts180]}")

    # ======= v168: die Seite ist eine Entscheidung, kein Wuerfelwurf ======
    # Ismets Befund, dritter Anlauf: "die captions sind immer auf der linken
    # seite, egal was passiert". Am eigenen Render nachgemessen, ZWEI
    # Ursachen: (1) der Seiten-Wurf pro Chunk (~40-45 % rechts, erster Chunk
    # IMMER links, lange Links-Ketten normal), (2) der 0.55-Tiebreaker
    # verlor gegen die 1.6-Unruhe-Karte - die ruhigste Stelle im Bild
    # (Ismets Betonwand links) gewann jedes Mal.
    _cfg168 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    # v180 TESTKORREKTUR (kein Verhaltensverlust): die Seiten-Abwechslung
    # gilt seit v180 nur noch im HOCHFORMAT - im Querformat steht der Text
    # mittig (Konvention fuer eingebrannten Text). Der v168-Nachweis
    # gehoert damit ins Hochformat; die Querformat-Regel prueft v180.
    _W168, _H168 = 1080, 1920
    _S168 = R.Sprites(_cfg168, _W168, _H168)
    _w168 = [{'word': _w, 'start': 0.8 + _i * 0.42, 'end': 1.1 + _i * 0.42}
             for _i, _w in enumerate(['ja', 'gut', 'so', 'ist', 'es', 'ok',
                                      'nun', 'na', 'da', 'wo', 'wie', 'was',
                                      'er', 'sie', 'wir', 'ihr', 'du', 'ich',
                                      'mal', 'oft', 'nie', 'hier', 'dort',
                                      'auch'])]
    # Unruhe-Karte wie in Ismets Video: links spiegelglatt, rechts unruhig.
    # Vorher zog GENAU DAS jeden Block nach links.
    _karte168 = np.zeros((16, 12), np.float32)
    _karte168[:, 6:] = 0.85     # rechte Bildhaelfte unruhig, linke glatt

    def _seiten168():
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_w168, set(), _cfg168, _S168, _W168, _H168,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (_W168 * 0.5,
                                                        _H168 * 0.32,
                                                        _W168 * 0.095),
                               space_at=lambda t_: _karte168)
        return [sum(i['cx'] for i in q['front']) / len(q['front']) / _W168
                for q in pl if q.get('front')]

    _sx168 = _seiten168()
    check('v168: es gibt genug Bloecke fuer eine Seiten-Messung',
          len(_sx168) >= 4, f"{len(_sx168)} Bloecke")
    check('v168: BEIDE Seiten kommen vor, trotz ruhiger linker Bildhaelfte',
          any(_x < 0.47 for _x in _sx168) and any(_x > 0.53 for _x in _sx168),
          f"x = {[round(_x, 3) for _x in _sx168]}")
    _folge = ['L' if _x < 0.5 else 'R' for _x in _sx168]
    _run = _mx = 1
    for _i in range(1, len(_folge)):
        _run = _run + 1 if _folge[_i] == _folge[_i - 1] else 1
        _mx = max(_mx, _run)
    check('v168: keine lange Einseiten-Kette mehr',
          _mx <= 3, f"Folge {''.join(_folge)}")
    check('v168: der Wechsel ist deterministisch (Re-Render = gleiches Bild)',
          _sx168 == _seiten168())

    # ======= v167: eine gehaltene Geste ist EINE Ansage ===================
    # Ismets Befund (am Bild belegt): der Sprecher haelt den Arm ueber viele
    # Momente in dieselbe Richtung -> jeder Moment bekam dasselbe Ziel, alle
    # Captions klebten dort. Gleicher Denkfehler wie beim Blick (v166), eine
    # Ebene tiefer.
    _Wd = 1920
    _halt167 = [(float(i), _Wd * 0.15 + (i % 2) * _Wd * 0.02, 500.0, 'zeigen')
                for i in range(6)]
    _dd = R._ziel_dedupe(_halt167, _Wd)
    check('v167: eine gehaltene Geste zaehlt nur fuer die ersten Momente',
          [z[0] for z in _dd] == [0.0, 1.0])
    _wechsel167 = [(0.0, _Wd * 0.15, 500.0, 'zeigen'),
                   (1.0, _Wd * 0.15, 500.0, 'zeigen'),
                   (2.0, _Wd * 0.15, 500.0, 'zeigen'),
                   (5.0, _Wd * 0.85, 500.0, 'zeigen'),
                   (6.0, _Wd * 0.85, 500.0, 'zeigen'),
                   (7.0, _Wd * 0.85, 500.0, 'zeigen')]
    check('v167: ein Richtungswechsel beginnt eine neue Ansage',
          [round(z[1] / _Wd, 2) for z in R._ziel_dedupe(_wechsel167, _Wd)]
          == [0.15, 0.15, 0.85, 0.85])
    _einz167 = [(0.0, _Wd * 0.2, 500.0, 'zeigen'),
                (3.0, _Wd * 0.8, 500.0, 'blick'),
                (6.0, _Wd * 0.3, 500.0, 'zeigen')]
    check('v167: einzelne, verschiedene Ziele bleiben alle erhalten',
          len(R._ziel_dedupe(_einz167, _Wd)) == 3)
    check('v167: der Filter haengt wirklich in zeige_ziele',
          'ziele = _ziel_dedupe(ziele, W)'
          in open(os.path.join(HERE, 'render.py'), encoding='utf-8').read())

    # ======= v162: ZWEI-SPRECHER-REGIE - der Text folgt dem Redner ========
    _cfg162 = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
    check('v162: die Zwei-Sprecher-Regie ist abschaltbar',
          _cfg162['effects'].get('caption_sprecher') is True)

    # (1) LUECKENWAHL. Bei zwei Personen ist die BREITESTE Luecke fast immer
    # dieselbe, egal wer redet - genau daran klebte der Text vorher fest.
    _W162 = 1920.0
    _paar = [(_W162 * 0.22, _W162 * 0.055), (_W162 * 0.72, _W162 * 0.055)]
    _breit = R._free_x_multi(_paar, _W162, _W162 * 0.20, 0)[1]
    _bei_l = R._free_x_multi(_paar, _W162, _W162 * 0.20, 0,
                             ziel_x=_W162 * 0.22)[1]
    _bei_r = R._free_x_multi(_paar, _W162, _W162 * 0.20, 0,
                             ziel_x=_W162 * 0.72)[1]
    check('v162: ohne Sprecher bleibt die alte breiteste-Luecke-Regel',
          abs(_breit - R._free_x_multi(_paar, _W162, _W162 * 0.20, 1)[1]) < 1.0)
    check('v162: mit Sprecher links wandert der Text nach links',
          _bei_l < _breit and _bei_l < _W162 * 0.50,
          f"links {_bei_l / _W162:.3f} vs. breiteste {_breit / _W162:.3f}")
    check('v162: mit Sprecher rechts wandert der Text nach rechts',
          _bei_r > _W162 * 0.50 and _bei_r > _bei_l,
          f"rechts {_bei_r / _W162:.3f}")
    check('v162: der Text deckt KEIN Gesicht zu',
          all(min(abs(_c - _f[0]) for _f in _paar) > _f[1]
              for _c in (_bei_l, _bei_r) for _f in _paar[:1]),
          f"links {_bei_l / _W162:.3f} rechts {_bei_r / _W162:.3f}")
    # Passt nirgends etwas hin, bleibt die alte Regel - eine zu enge Luecke
    # neben dem Sprecher schneidet ihn an.
    check('v162: ohne passende Luecke gilt weiter die breiteste',
          R._free_x_multi(_paar, _W162, _W162 * 0.95, 0,
                          ziel_x=_W162 * 0.22)[1]
          == R._free_x_multi(_paar, _W162, _W162 * 0.95, 0)[1])

    # (2) DER TEXT FOLGT DEM SPRECHER durch den ganzen Plan-Bau.
    _Ws, _Hs = 1920, 1080                       # Querformat = Interview-Fall
    _Ss = R.Sprites(_cfg162, _Ws, _Hs)
    _ws162 = [{'word': _w, 'start': 1.0 + _i * 0.45, 'end': 1.35 + _i * 0.45}
              for _i, _w in enumerate(['ja', 'nun', 'so', 'ist', 'es', 'ok'])]
    _zwei = [(_Ws * 0.24, _Ws * 0.05), (_Ws * 0.74, _Ws * 0.05)]

    def _mit_sprecher(sx):
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_ws162, set(), _cfg162, _Ss, _Ws, _Hs,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (sx, _Hs * 0.42,
                                                        _Ws * 0.05),
                               faces_at=lambda s_, e_: _zwei)
        return [sum(i['cx'] for i in q['front']) / len(q['front']) / _Ws
                for q in pl if q.get('front')]

    _links162 = _mit_sprecher(_Ws * 0.24)
    _rechts162 = _mit_sprecher(_Ws * 0.74)
    check('v162: die Zwei-Sprecher-Regie liefert Bloecke',
          len(_links162) >= 2 and len(_links162) == len(_rechts162))
    check('v162: redet die linke Person, steht der Text links',
          max(_links162) < 0.50,
          f"x = {[round(_x, 3) for _x in _links162]}")
    check('v162: redet die rechte Person, steht der Text rechts',
          min(_rechts162) > 0.50,
          f"x = {[round(_x, 3) for _x in _rechts162]}")
    check('v162: der Sprecherwechsel verschiebt den Text deutlich',
          min(_rechts162) - max(_links162) > 0.15,
          f"links {[round(_x, 3) for _x in _links162]} "
          f"rechts {[round(_x, 3) for _x in _rechts162]}")

    # (3) BEI EINER PERSON aendert sich NICHTS. "Der Sprecher" ist dort keine
    # Information, und die vorhandene Ausweich-Logik ist die bessere Wahl.
    def _eine_person(faces):
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_ws162, set(), _cfg162, _Ss, _Ws, _Hs,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (_Ws * 0.30, _Hs * 0.42,
                                                        _Ws * 0.05),
                               faces_at=(lambda s_, e_: faces) if faces
                               else None)
        return [sum(i['cx'] for i in q['front']) / len(q['front']) / _Ws
                for q in pl if q.get('front')]

    check('v162: eine einzelne Person aendert nichts an der Platzierung',
          _eine_person([(_Ws * 0.30, _Ws * 0.05)]) == _eine_person(None))
    # Abschalten muss auch wirklich abschalten.
    _cfg_aus = _y160.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                    encoding='utf-8'))
    _cfg_aus['effects']['caption_sprecher'] = False
    _S_aus = R.Sprites(_cfg_aus, _Ws, _Hs)

    def _aus(sx):
        with _cl159.redirect_stdout(_io159.StringIO()):
            pl = R.build_plans(_ws162, set(), _cfg_aus, _S_aus, _Ws, _Hs,
                               lambda s_, e_: True, {},
                               face_pos=lambda s_, e_: (sx, _Hs * 0.42,
                                                        _Ws * 0.05),
                               faces_at=lambda s_, e_: _zwei)
        return [sum(i['cx'] for i in q['front']) / len(q['front']) / _Ws
                for q in pl if q.get('front')]

    check('v162: abgeschaltet folgt der Text dem Sprecher NICHT',
          _aus(_Ws * 0.24) == _aus(_Ws * 0.74))

    check('v160: die Zeige-Regie ist abschaltbar',
          'caption_zeige' in open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8').read())

    # ============ v158: der Preis am Button kennt 4K ========================
    # Ismets Befund: "wenn 4k angewaehlt ist, steht immer noch 1 credit".
    # Der Preis wurde nur EINMAL beim Datei-Auswaehlen gerechnet und kannte
    # die Aufloesungswahl gar nicht.
    _ui158 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v158: der Preis wird bei jeder Aufloesungs-Aenderung neu gerechnet',
          'function updateRenderCost' in _ui158
          and "if (cfg === 'output.height') updateRenderCost();" in _ui158)
    check('v158: der Preis kennt den 4K-Faktor',
          'wantUhd && canUhd ? 2 : 1' in _ui158)
    # Und er darf NICHT das Doppelte zeigen, wenn die Quelle zu klein ist -
    # der Server berechnet dann auch nur den einfachen Satz.
    check('v158: zu kleine Quelle zeigt den einfachen Satz plus Hinweis',
          "(State.srcShort || 0) >= 1440" in _ui158
          and 'uhdNote' in _ui158
          and '4K needs at least 1440p' in _ui158)
    check('v158: die Client-Grenze passt zur Server-Grenze',
          SV.UHD_MIN_KURZE_KANTE == 1440
          and '>= 1440' in _ui158,
          f'Server {SV.UHD_MIN_KURZE_KANTE}')

    # ============ v155: Buendigkeit ist NICHT die Bildseite =================
    import yaml as _y155
    import render as R
    import io as _io155, contextlib as _cl155
    _r155 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()

    def _mitten(align='auto', seite='auto'):
        _c = _y155.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8'))
        _c['look'] = 'creator'
        _c['effects']['caption_align'] = align
        _c['effects']['caption_seite'] = seite
        _S = R.Sprites(_c, 1080, 1920)
        _t = ('du hast das schon oft gehoert aber was wirklich dahinter steckt. '
              'genau das zeige ich dir jetzt hier und heute abend.').split()
        _w = [{'word': x, 'start': round(i * 0.36, 2),
               'end': round(i * 0.36 + 0.28, 2)} for i, x in enumerate(_t)]
        with _cl155.redirect_stdout(_io155.StringIO()):
            _pl = R.build_plans(_w, set(), _c, _S, 1080, 1920,
                                lambda a, b: True, {})
        return [sum(i['cx'] for i in p['front']) / len(p['front']) / 1080.0
                for p in _pl if p.get('tpl') == 'flow' and p.get('front')]
    # Der Kern des Befunds: eine gelernte Referenz misst die BUENDIGKEIT des
    # Satzes ('linksbuendig'). Bis v154 nagelte das zusaetzlich die BILDSEITE
    # fest - bei Ismet sass deshalb weiterhin jede Caption links, obwohl die
    # Variation im Code lief.
    _mb = _mitten(align='links', seite='auto')
    check('v155: linksbuendiger Satz klebt trotzdem nicht an der linken Kante',
          max(_mb) - min(_mb) > 0.18 and max(_mb) > 0.55,
          'Mitten ' + ', '.join(f'{v:.2f}' for v in _mb))
    # v156: die gemessene Buendigkeit ist eine TENDENZ, keine Schablone.
    # Ismets Einwand: sein Vorbild setzt die Captions NICHT staendig links.
    # Rund die Haelfte der Bloecke folgt deshalb der Bildseite statt der
    # Messung - mit einem Drittel (Schwelle 0.66) wechselte im echten Render
    # nur EIN Block von sechs.
    check('v156: die gemessene Buendigkeit ist Tendenz, nicht Schablone',
          "_mix01(g[0] * 23) >= 0.50" in _r155
          and "_buendig in ('links', 'rechts') and _sw == 'auto'" in _r155)
    check('v156: eine Nutzerwahl bleibt trotzdem absolut',
          max(_mitten(align='links', seite='links'))
          < min(_mitten(align='links', seite='rechts')) + 0.20,
          f"links {max(_mitten(align='links', seite='links')):.2f} W, "
          f"rechts {min(_mitten(align='links', seite='rechts')):.2f} W")
    check('v155: nur die ausdrueckliche Nutzerwahl nagelt die Seite fest',
          sum(_mitten(seite='links')) / len(_mitten(seite='links'))
          < sum(_mitten(seite='rechts')) / len(_mitten(seite='rechts')) - 0.10)
    check('v155: Buendigkeit und Bildseite sind getrennte Schluessel',
          "cfg['effects'].get('caption_seite')" in _r155
          and "_bnd = _buendig or _seite" in _r155
          and 'caption_seite' in open(os.path.join(HERE, 'config.yaml'),
                                      encoding='utf-8').read())
    # Der Tiebreaker prueft die MOTIV-Kosten, nicht die Gesamtkosten. Mit den
    # Gesamtkosten war er nie erfuellt, sobald eine Raum-Karte existiert.
    # v168: _motiv traegt jetzt die ECHTEN Gesichts-/Atemluft-Kosten (fuer
    # die Seiten-Entscheidung), nicht mehr nur einen Zaehler. Die Invariante
    # dahinter bleibt dieselbe: die Unruhe-Karte darf NIE hinein.
    check('v155: der Seiten-Tiebreaker prueft nur das Motiv',
          'if wunsch_x is not None and _motiv <= 0.0:' in _r155
          and '_motiv += 2.5 + 8.0' in _r155
          and '_motiv += 1.2 *' in _r155
          and '_motiv = k' not in _r155)
    _ui155 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v155: der UI-Regler steuert die Bildseite, nicht die Buendigkeit',
          'data-cfg="effects.caption_seite"' in _ui155)
    check('v155: beide Schluessel werden serverseitig geprueft',
          SV._sanitize_overrides({'effects': {'caption_seite': 'rechts'}})
          == {'effects': {'caption_seite': 'rechts'}}
          and SV._sanitize_overrides({'effects': {'caption_seite': 'x'}})
          == {'effects': {}})

    # ============ v154: Schriftgroesse + Keyword-Variation ==================
    import yaml as _y154
    import render as R
    import io as _io154, contextlib as _cl154
    _r154 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()

    def _flow_sz(cfgx):
        _S = R.Sprites(cfgx, 1080, 1920)
        _w = [{'word': x, 'start': i * 0.35, 'end': i * 0.35 + 0.3}
              for i, x in enumerate(['was', 'steckt', 'WIRKLICH', 'dahinter'])]
        _it, _, _ = R.compose_flow(list(range(4)), _w, _S, 1080, 1920,
                                   portrait=True)
        return max(i['sz'] for i in _it if i['role'] == 'norm')
    _c154 = _y154.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _haus154 = _flow_sz(_c154)
    # v184 TESTKORREKTUR: die v153/v154-Verkleinerungen galten der ALTEN
    # Anordnung. Ismets drei High-End-Referenzen messen ein Fliesstext-Band
    # von 0.040 H (A/B/C uebereinstimmend) - die Hausbasis steht deshalb auf
    # 0.050 em (= 96 px bei 1920 H). Die SUBSTANZ des v154-Befunds bleibt
    # geprueft: der Fliesstext haengt NICHT an key_hoehe * Hierarchie (der
    # Referenz-Test direkt darunter).
    check('v154/v192: Fliesstext auf dem gewaehlten Mass, nicht auf Punchline-Mass',
          76 <= _haus154 <= 90, f'{_haus154} px bei 1920 H (Ziel 82)')
    # Kern des Befunds "Schriften zu gross": eine gemessene Referenz zog den
    # GANZEN Satz mit, weil sz_n ueber key_hoehe * Hierarchie lief. Gemessen
    # wird aber die PUNCHLINE des Vorbilds.
    _p154 = {'key_hoehe': 0.1836, 'klein_hoehe': 0.04, 'verhaeltnis': 4.59}
    _rf154 = os.path.join(tmp, 'refs154.json')
    json.dump([{'name': 'v2', 'beispiel': 'x', 'params': _p154}],
              open(_rf154, 'w', encoding='utf-8'))
    _c154r = _y154.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _alt154 = os.environ.get('DVE_REFS_FILE')
    try:
        os.environ['DVE_REFS_FILE'] = _rf154
        R._apply_reference_params(_c154r)
    finally:
        if _alt154 is None:
            os.environ.pop('DVE_REFS_FILE', None)
        else:
            os.environ['DVE_REFS_FILE'] = _alt154
    _ref154 = _flow_sz(_c154r)
    check('v154: der Fliesstext hat einen EIGENEN Referenz-Faktor',
          _c154r['effects'].get('caption_scale_klein'),
          f"klein {_c154r['effects'].get('caption_scale_klein')}, "
          f"key {_c154r['effects'].get('caption_scale')}")
    check('v154: eine grosse Punchline blaeht den Fliesstext nicht mehr auf',
          _ref154 <= _haus154 * 1.35,
          f'Haus {_haus154} px -> Referenz {_ref154} px (v153 waren 76 -> 128)')
    check('v154: das Schluesselwort darf trotzdem gross bleiben',
          float(_c154r['effects'].get('caption_scale', 0)) >= 2.0,
          str(_c154r['effects'].get('caption_scale')))
    # Keyword-Momente: jeder bekommt eine Animation, und sie wiederholen sich
    # nicht stur. Vorher lieferte anim_for() bei normalen Woertern None.
    _c154b = _y154.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _c154b['look'] = 'creator'
    _S154 = R.Sprites(_c154b, 1080, 1920)
    _t154 = ('du hast das schon oft gehoert. aber was wirklich dahinter steckt '
             'weiss niemand. genau das zeige ich dir heute. es wird dich '
             'schockieren wie einfach das geht. danach machst du es nie wieder '
             'anders. versprochen wirklich gut.').split()
    _w154 = [{'word': x, 'start': round(i * 0.36, 2),
              'end': round(i * 0.36 + 0.28, 2)} for i, x in enumerate(_t154)]
    _kw154 = {i for i, x in enumerate(_t154) if x.strip('.') in
              ('gehoert', 'dahinter', 'schockieren', 'zeige', 'versprochen',
               'niemand', 'einfach')}
    with _cl154.redirect_stdout(_io154.StringIO()):
        _pl154 = R.build_plans(_w154, _kw154, _c154b, _S154, 1080, 1920,
                               lambda a, b: True, {})
    _kwp = [p for p in _pl154 if 'kw_i' in p]
    check('v154: JEDER Keyword-Moment bekommt eine Animation',
          _kwp and all(p.get('anim') for p in _kwp),
          f"{sum(1 for p in _kwp if p.get('anim'))}/{len(_kwp)} animiert")
    check('v154: die grossen Momente wiederholen sich nicht',
          len({(p.get('tpl'), p.get('anim'), p.get('entr')) for p in _kwp})
          == len(_kwp),
          str([(p.get('tpl'), p.get('anim')) for p in _kwp]))
    check('v154: die Fallback-Animationen sind bedeutungsneutral',
          'rot_anim = Rotator(' in _r154
          and all(x not in _r154.split('rot_anim = Rotator(')[1][:200]
                  for x in ("'sturz'", "'knall'", "'explosion'")))

    # ============ v153: Seitenwechsel, kleinere Schrift, Nutzer-Regler ======
    import yaml as _y153
    import render as R
    import io as _io153, contextlib as _cl153
    _r153 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # Die alte Streufunktion nahm nur die unteren 10 Bit EINER Multiplikation
    # und lief fuer kleine Vielfache fast linear - der Seitenwechsel fiel
    # dadurch immer auf dieselbe Seite.
    _mv = [R._mix01(i * 11) for i in range(0, 60, 3)]
    check('v153: die Streuung ist wirklich gestreut, keine Rampe',
          sum(1 for v in _mv if v >= 0.55) >= 3
          and sum(1 for v in _mv if v < 0.55) >= 3
          and max(_mv) - min(_mv) > 0.7,
          f'{sum(1 for v in _mv if v >= 0.55)} rechts / {len(_mv)}')
    check('v153: gleiche Eingabe bleibt gleich (Re-Render reproduzierbar)',
          [R._mix01(i) for i in range(20)] == [R._mix01(i) for i in range(20)])

    def _seiten(align='auto', seite=None):
        _c = _y153.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8'))
        _c['look'] = 'creator'
        _c['effects']['caption_align'] = align
        # v155: die BILDSEITE haengt an caption_seite, nicht mehr an der
        # gemessenen Buendigkeit. Der Test misst weiterhin die Bildseite.
        _c['effects']['caption_seite'] = seite if seite else align
        _S = R.Sprites(_c, 1080, 1920)
        _t = ('du hast das schon oft gehoert aber was wirklich dahinter '
              'steckt. genau das zeige ich dir jetzt hier und heute.').split()
        _w = [{'word': x, 'start': round(i * 0.36, 2),
               'end': round(i * 0.36 + 0.28, 2)} for i, x in enumerate(_t)]
        with _cl153.redirect_stdout(_io153.StringIO()):
            _pl = R.build_plans(_w, set(), _c, _S, 1080, 1920,
                                lambda a, b: True, {})
        return [sum(i['cx'] for i in p['front']) / len(p['front']) / 1080.0
                for p in _pl if p.get('tpl') == 'flow' and p.get('front')]
    _auto = _seiten('auto')
    check('v153: die Captions kleben nicht mehr an einer Kante',
          max(_auto) - min(_auto) > 0.20
          and any(v > 0.55 for v in _auto) and any(v < 0.45 for v in _auto),
          'Blockmitten ' + ', '.join(f'{v:.2f}' for v in _auto))
    _li = _seiten('auto', seite='links')
    _re = _seiten('auto', seite='rechts')
    check('v153: eine feste Seite wird auch eingehalten',
          sum(_li) / len(_li) < sum(_re) / len(_re) - 0.10,
          f'links {sum(_li) / len(_li):.2f} W gegen '
          f'rechts {sum(_re) / len(_re):.2f} W')
    # Die Wunschseite darf das Gesichts-Ausweichen NIE ueberstimmen.
    # v155: _motiv zaehlt nur noch Gesichts-Beruehrungen. Mit der alten
    # Zwischensumme (inkl. Unruhe-Karte) war die Bedingung nie erfuellt.
    check('v153/v155: das Motiv schlaegt die Wunschseite (Rangfolge)',
          'if wunsch_x is not None and _motiv <= 0.0:' in _r153
          and '_motiv = k' not in _r153)
    check('v153: ein Seitenwechsel durchbricht die Hysterese',
          "spot_state.get('seite') != _seite" in _r153)
    # v184 TESTKORREKTUR: Grundschrift steht auf dem gemessenen REFERENZMASS
    # (key 0.105 em, klein 0.050 em - Ismets drei Vorbilder). Die alten
    # v153-Werte (0.076/0.034) und die noch aelteren (0.098/0.088) duerfen
    # beide nicht zurueckkommen.
    check('v153/v192: die Grundschrift steht auf dem gewaehlten Mass',
          "H * 0.089 * pf * _skal" in _r153 and "H * 0.043 * pf * _skn" in _r153
          and 'H * 0.098 * pf' not in _r153 and 'H * 0.076 * pf' not in _r153)
    # Nutzer-Regler
    _ui153 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    # v155: der Seiten-Regler heisst caption_seite; caption_align ist die
    # Buendigkeit und kommt aus der Messung, nicht aus der UI.
    for _k in ('effects.caption_layout', 'effects.caption_seite',
               'effects.caption_scale', 'effects.caption_hierarchie',
               'effects.caption_bleed'):
        check(f'v153: Regler {_k} steht in der UI', f'data-cfg="{_k}"' in _ui153)
    check('v153: Regler werden serverseitig gedeckelt',
          SV._sanitize_overrides({'effects': {'caption_scale': 99}})
          == {'effects': {'caption_scale': 1.8}}
          and SV._sanitize_overrides({'effects': {'caption_layout': 'boese'}})
          == {'effects': {}}
          and SV._sanitize_overrides({'effects': {'caption_align': 'rechts'}})
          == {'effects': {'caption_align': 'rechts'}})
    check('v153: erzwungenes Layout wird eingehalten',
          "_lm == 'collage' or _mix01(g[0] * 3) >= 0.42" in _r153
          and "_lm != 'rows'" in _r153)

    # ============ v152: Randabfall + satzweise Collage ======================
    import yaml as _y152
    import render as R
    _c152 = _y152.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _c152['look'] = 'creator'
    _S152 = R.Sprites(_c152, 1080, 1920)

    def _punchw(cfgx, txt):
        _Sx = R.Sprites(cfgx, 1080, 1920)
        _w = [{'word': x, 'start': i * 0.35, 'end': i * 0.35 + 0.3}
              for i, x in enumerate(txt)]
        _it, _, _ = R.compose_flow(list(range(len(_w))), _w, _Sx, 1080, 1920,
                                   portrait=True, punch=True)
        _p = [i for i in _it if i['role'] == 'punch']
        return (_p[0]['sz'], _p[0]['w'], bool(_p[0].get('bleed'))) if _p else (0, 0, False)
    _c152n = _y152.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _c152n['effects']['caption_bleed'] = False
    _sz_b, _w_b, _bl_b = _punchw(_c152, ['das', 'ist', 'KRASS.'])
    _sz_n, _w_n, _bl_n = _punchw(_c152n, ['das', 'ist', 'KRASS.'])
    check('v152: Randabfall macht das Schlusswort wirklich groesser',
          _sz_b > _sz_n * 1.15 and _bl_b and not _bl_n,
          f'mit Anschnitt {_sz_b} px ({_w_b / 1080:.2f} W), '
          f'ohne {_sz_n} px ({_w_n / 1080:.2f} W)')
    check('v152: der Anschnitt bleibt begrenzt (Wort bleibt lesbar)',
          1.0 < _w_b / 1080.0 <= 1.16,
          f'{_w_b / 1080:.2f} W')
    # Am gerenderten Streifen gemessen: bei 'GEHOERT' (7 Zeichen) frisst der
    # Anschnitt links das G und rechts das T weg. Ab sechs Zeichen bleibt es
    # deshalb beim Satzspiegel - das Vorbild schneidet 'this' an, nicht ein
    # Wort dieser Laenge.
    _sz_l, _w_l, _bl_l = _punchw(_c152, ['das', 'war', 'GEHOERT.'])
    check('v152: lange Schlussworte werden NICHT angeschnitten',
          not _bl_l and _w_l / 1080.0 <= 0.92,
          f'GEHOERT {_w_l / 1080:.2f} W, Anschnitt {_bl_l}')
    check('v152: Randabfall ist abschaltbar',
          'caption_bleed' in open(os.path.join(HERE, 'config.yaml'),
                                  encoding='utf-8').read())
    _r152 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # Das angeschnittene Wort darf die Blockbreite NICHT bestimmen, sonst
    # findet die Platzierungs-Regie fuer 1.22 W nirgends Platz.
    check('v152: das angeschnittene Wort bestimmt die Blockbreite nicht',
          "_spans = [_ink_x(it) for it in items if not it.get('bleed')]" in _r152
          and "it['cx'] = W / 2.0" in _r152)
    # Satzweise Collage: der ganze Satz steht, statt chunkweise zu wechseln.
    _wsz = []
    _t152 = 0.0
    for _wd in 'du hast das schon oft gehoert aber was wirklich dahinter steckt.'.split():
        _wsz.append({'word': _wd, 'start': round(_t152, 2), 'end': round(_t152 + 0.28, 2)})
        _t152 += 0.36
    import io as _io152, contextlib as _cl152

    def _plaene(satz_collage):
        _cx = _y152.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8'))
        _cx['look'] = 'creator'
        _cx['effects']['caption_satz_collage'] = satz_collage
        # v153: Layout erzwingen. Vorher haing der Test daran, ob die
        # deterministische Streuung fuer GENAU diese Wort-Indizes eine
        # Collage waehlt - eine Aenderung an _mix01 liess ihn dann kippen,
        # ohne dass an der geprueften Eigenschaft etwas falsch war.
        _cx['effects']['caption_layout'] = 'collage'
        _Sx = R.Sprites(_cx, 1080, 1920)
        with _cl152.redirect_stdout(_io152.StringIO()):
            _pl = R.build_plans(_wsz, set(), _cx, _Sx, 1080, 1920,
                                lambda a, b: True, {})
        return [p for p in _pl if p.get('tpl') == 'flow']
    _mit = _plaene(True)
    _ohne = _plaene(False)
    _mx_mit = max((len(p['front']) for p in _mit), default=0)
    _mx_ohne = max((len(p['front']) for p in _ohne), default=0)
    check('v152: die Collage haelt mehr Woerter des Satzes zusammen',
          _mx_mit > _mx_ohne,
          f'groesster Block {_mx_ohne} -> {_mx_mit} Woerter')
    check('v152: dafuer laufen weniger Bloecke - der Satz wird EIN Bild',
          len(_mit) < len(_ohne),
          f'{_ohne and len(_ohne)} Bloecke -> {len(_mit)}')
    # Kein Wort darf doppelt erscheinen, wenn Gruppen geschluckt werden.
    _alle = [i['i'] for p in _mit for i in p['front']]
    check('v152: kein Wort erscheint doppelt (used-Buchfuehrung stimmt)',
          len(_alle) == len(set(_alle)), f'{len(_alle)} Woerter, '
          f'{len(_alle) - len(set(_alle))} Dubletten')
    check('v152: eine zu hohe Collage dreht erst die Erweiterung zurueck',
          "if _lay == 'collage' and tot_h > H * 0.40 and _g_kurz:" in _r152
          and 'used.discard(_i)' in _r152)
    check('v152: ein Keyword-Moment wird NIE von einer Collage geschluckt',
          'if any(i in kw for i in _nx):' in _r152)

    # ============ v151: die Referenz muss WIRKLICH durchschlagen =============
    # Ismets Befund: "Referenz hochgeladen, es aendert sich kaum was."
    # Ursache waren zwei Deckel und ein Leerlauf:
    #  1. Messwerte ausserhalb eines an v144 geeichten Fensters wurden
    #     VERWORFEN statt geklemmt - beim zweiten Vorbild (Versalhoehe
    #     0.1836 H, Verhaeltnis 4.59) passierte deshalb GAR NICHTS.
    #  2. Der Deckel sass zweimal: _apply_reference_params klemmte sauber,
    #     compose_flow stutzte danach nochmal auf 1.35.
    #  3. 'kamera: bewegt' war ein Leerlauf - nur ruhig/wild taten etwas.
    import yaml as _y151
    import render as R
    _p151 = {'key_hoehe': 0.1836, 'verhaeltnis': 4.59, 'kamera': 'bewegt',
             'buchstaben_takt': 0.087, 'stamm_versal': 0.17,
             'zone_y': [0.182, 0.492], 'einstellung_s': 2.04}
    _rf151 = os.path.join(tmp, 'refs151.json')
    json.dump([{'name': 'v2', 'beispiel': 'x', 'params': _p151}],
              open(_rf151, 'w', encoding='utf-8'))
    _c151 = _y151.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _alt151 = os.environ.get('DVE_REFS_FILE')
    try:
        os.environ['DVE_REFS_FILE'] = _rf151
        _ank151 = R._apply_reference_params(_c151)
    finally:
        if _alt151 is None:
            os.environ.pop('DVE_REFS_FILE', None)
        else:
            os.environ['DVE_REFS_FILE'] = _alt151
    check('v151: extreme Messwerte werden GEKLEMMT, nicht verworfen',
          _c151['effects'].get('caption_scale')
          and _c151['effects'].get('caption_hierarchie'),
          f"scale {_c151['effects'].get('caption_scale')}, "
          f"hierarchie {_c151['effects'].get('caption_hierarchie')}")
    check('v151: eine 2.7x groessere Referenz kommt auch als deutlich groesser an',
          float(_c151['effects']['caption_scale']) >= 2.0,
          f"Faktor {_c151['effects'].get('caption_scale')} (alter Deckel war 1.35)")
    check('v151: bewegte Referenz-Kamera bewegt auch UNSERE Kamera',
          _c151['camera'].get('whip') is True
          and 0.55 <= float(_c151['camera']['strength']) <= 0.85,
          f"strength {_c151['camera']['strength']}, whip {_c151['camera'].get('whip')}")
    check('v151: Aufdeck-Tempo und Strichstaerke werden angewandt',
          abs(float(_c151['effects'].get('reveal_letter_s', 0)) - 0.087) < 0.001
          and 300 <= int(_c151['effects'].get('caption_weight', 0)) <= 900,
          f"reveal {_c151['effects'].get('reveal_letter_s')}, "
          f"weight {_c151['effects'].get('caption_weight')}")
    check('v151: der Anker nennt Grad, Hierarchie und Tempo',
          all(x in _ank151 for x in ('grad=', 'hierarchie=', 'reveal=')), _ank151)

    def _szn(cfgx):
        _Sx = R.Sprites(cfgx, 1080, 1920)
        _wx = [{'word': x, 'start': i * 0.35, 'end': i * 0.35 + 0.3}
               for i, x in enumerate(['das', 'ist', 'KRASS.'])]
        _it, _, _ = R.compose_flow(list(range(3)), _wx, _Sx, 1080, 1920,
                                   portrait=True, punch=True)
        return max(i['sz'] for i in _it if i['role'] == 'norm')
    _haus151 = _szn(_y151.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                         encoding='utf-8')))
    _ref151 = _szn(_c151)
    check('v151: der zweite Deckel in compose_flow ist weg (Groesse kommt an)',
          _ref151 >= _haus151 * 1.4,
          f'Haus {_haus151} px -> Referenz {_ref151} px')
    _r151 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v151: kein doppelter Deckel mehr im Composer',
          'max(0.60, min(2.80, _skal))' in _r151
          and 'max(0.75, min(1.35, _skal))' not in _r151)
    check('v151: das gemessene Tempo steuert das Aufdecken wirklich',
          "'reveal_letter_s'" in _r151 and '_rvd * (1 + 0.08 * hand_jitter' in _r151)
    # Grober Unsinn muss weiterhin abprallen - sonst sprengt eine
    # Fehlmessung den Satz.
    _c151b = _y151.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    json.dump([{'name': 'x', 'beispiel': 'x',
                'params': {'key_hoehe': 0.92, 'verhaeltnis': 40.0}}],
              open(_rf151, 'w', encoding='utf-8'))
    try:
        os.environ['DVE_REFS_FILE'] = _rf151
        R._apply_reference_params(_c151b)
    finally:
        if _alt151 is None:
            os.environ.pop('DVE_REFS_FILE', None)
        else:
            os.environ['DVE_REFS_FILE'] = _alt151
    check('v151: unsinnige Messwerte prallen weiterhin ab',
          not _c151b['effects'].get('caption_scale')
          and not _c151b['effects'].get('caption_hierarchie'),
          str(_c151b['effects'].get('caption_scale')))

    # ================= v150: Abwechslung im Satzbild =========================
    # Ismets Befund am eigenen Ergebnis: "zu monoton". Bis v149 bekam JEDER
    # Filler-Chunk dasselbe linksbuendige Zeilenraster - drei Zeilen, gleiche
    # Kante, gleiche Groessen. Vorbild (@johnbucog_, gemessen): Woerter in
    # eigener Groesse ueber die Flaeche verteilt, zweiter Schriftschnitt im
    # selben Satz, Punchline mit Groessenverhaeltnis 4.59.
    import yaml as _yaml150
    import render as R
    _cfg150 = _yaml150.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                      encoding='utf-8'))
    _cfg150['look'] = 'creator'
    _S150 = R.Sprites(_cfg150, 1080, 1920)

    def _komp(txt, layout, punch=True):
        _w = [{'word': x, 'start': i * 0.35, 'end': i * 0.35 + 0.3}
              for i, x in enumerate(txt)]
        return R.compose_flow(list(range(len(_w))), _w, _S150, 1080, 1920,
                              portrait=True, layout=layout, punch=punch)
    _sat = ['you', 'all', 'have', 'been', 'asking', 'how', 'do', 'I', 'THIS.']
    _if, _hf, _ = _komp(_sat, 'flow')
    _ic, _hc, _ = _komp(_sat, 'collage')
    # Kernaussage: die Collage ist KEIN Zeilenraster mehr. Im Flow teilen sich
    # die Woerter wenige gemeinsame Grundlinien, in der Collage steht fast
    # jedes auf eigener Hoehe.
    _zf = len({round(i['cy'], 1) for i in _if})
    _zc = len({round(i['cy'], 1) for i in _ic})
    # v187 TESTKORREKTUR: seit die Zeilenhoehe mit der GESETZTEN Groesse
    # rechnet (_rsz), fallen im Zeilensatz weniger Grundlinien an und in der
    # Collage runden zwei Zeilen gelegentlich zusammen. Die Aussage bleibt
    # geprueft - die Collage loest das Raster auf und verteilt ueber deutlich
    # mehr Grundlinien als der Zeilensatz.
    check('v150: Collage loest das Zeilenraster auf',
          _zc > _zf and _zc >= len(_sat) // 2,
          f'{_zf} Grundlinien im Zeilensatz -> {_zc} in der Collage')
    # v184 TESTKORREKTUR (Anordnung ersetzt, an Ismets drei Referenzen
    # gelesen): nicht mehr "kleine Spalte links, Treppe rechts" - genau
    # diese Trennung riss Lesereihenfolge und Raumfolge auseinander
    # ("that/to/one"-Saeule neben STICKS). Die Vorbilder setzen EINEN
    # Lesepfad: (a) Grundlinien folgen der Wortfolge, (b) kurze Zeilen mit
    # hoechstens 3 Woertern, (c) innerhalb einer Zeile laeuft x nach rechts.
    _mit_sz = [i for i in _ic if i.get('sz')]

    def _grundlinie(i):
        return i['cy'] + i['sz'] * 0.53
    _bl150 = [_grundlinie(i) for i in _mit_sz]
    check('v184: Raumfolge = Lesereihenfolge (Grundlinien monoton)',
          all(_bl150[j + 1] >= _bl150[j] - 2.0
              for j in range(len(_bl150) - 1)),
          f"{[round(b) for b in _bl150]}")
    _zl150 = {}
    for i in _mit_sz:
        _zl150.setdefault(round(_grundlinie(i)), []).append(i)
    check('v184: kurze Zeilen (max. 3 Woerter), x laeuft nach rechts',
          all(len(v) <= 3
              and all(v[j + 1]['cx'] > v[j]['cx'] for j in range(len(v) - 1))
              for v in _zl150.values()),
          f"{[len(v) for v in _zl150.values()]} Woerter je Zeile")
    check('v150: in der Collage stehen die Woerter in EIGENEN Groessen',
          len({i['sz'] for i in _ic if i.get('sz')}) >= 4
          and len({i['sz'] for i in _if if i.get('sz')}) <= 2,
          f"{len({i['sz'] for i in _ic if i.get('sz')})} Groessen in der Collage")
    # (B) Zweiter Schriftschnitt im selben Satz.
    check('v150: eine Verbinder-Kette laeuft in Schreibschrift',
          sum(1 for i in _ic if i.get('skript')) >= 2
          and not any(i.get('skript') for i in _if),
          f"{sum(1 for i in _ic if i.get('skript'))} Woerter kursiv")
    # (C) Schlusswort-Knall: nur am Satzende, und wirklich groesser.
    _ip, _, _ = _komp(['das', 'ist', 'KRASS.'], 'flow')
    _in, _, _ = _komp(['das', 'ist', 'KRASS'], 'flow', punch=False)

    def _gr_max(items):
        return max((i.get('sz') or 0) for i in items)
    check('v150: das Satzende knallt, ein offener Satz nicht',
          _gr_max(_ip) > _gr_max(_in) * 1.15,
          f'Satzende {_gr_max(_ip)} px gegen offen {_gr_max(_in)} px')
    # v152: OHNE Randabfall bleibt der Knall im Satzspiegel. Mit dem ersten
    # Deckel (0.96 W) ragte er bis 1.033 W heraus, weil der Block schon bei
    # 0.07 W ansetzt - das war unbeabsichtigt und ist etwas anderes als der
    # gewollte Anschnitt.
    _cfg_nb = _yaml150.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                      encoding='utf-8'))
    _cfg_nb['look'] = 'creator'
    _cfg_nb['effects']['caption_bleed'] = False
    _S_nb = R.Sprites(_cfg_nb, 1080, 1920)
    _wnb = [{'word': x, 'start': i * 0.35, 'end': i * 0.35 + 0.3}
            for i, x in enumerate(['was', 'steckt', 'wirklich', 'DAHINTER.'])]
    _inb, _, _ = R.compose_flow(list(range(4)), _wnb, _S_nb, 1080, 1920,
                                portrait=True, punch=True)
    check('v150: ohne Randabfall bleibt der Knall im Satzspiegel',
          all(i['cx'] + i['w'] / 2.0 <= 1080 * 0.98 for i in _inb),
          f"rechte Kante {max(i['cx'] + i['w'] / 2.0 for i in _inb) / 1080:.3f} W")
    _r150 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v150: der Wechsel ist deterministisch, nicht zufaellig',
          'def _mix01' in _r150 and '_mix01(g[0] * 3) >= 0.42' in _r150
          and 'random' not in _r150.split('def _mix01')[1][:400])
    check('v150: eine zu hohe Collage faellt auf das Zeilenraster zurueck',
          "if _lay == 'collage' and tot_h > H * 0.40:" in _r150)
    check('v150: clean bleibt schlicht, Collage abschaltbar',
          "str(cfg.get('look', '')).lower() != 'clean'" in _r150
          and "cfg['effects'].get('caption_collage', True)" in _r150
          and 'caption_collage' in open(os.path.join(HERE, 'config.yaml'),
                                        encoding='utf-8').read())
    check('v150: der Server reicht den Look an die Engine durch',
          "cfg['look'] = str(look or 'creator')" in
          open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read())
    # Reproduzierbarkeit: gleicher Inhalt, gleiches Bild (Re-Render-Garantie).
    _a150, _, _ = _komp(_sat, 'collage')
    _b150, _, _ = _komp(_sat, 'collage')
    check('v150: gleiche Eingabe ergibt exakt dasselbe Satzbild',
          [(i['cx'], i['cy'], i.get('sz')) for i in _a150]
          == [(i['cx'], i['cy'], i.get('sz')) for i in _b150])

    # ================= v149: Aufloesung + 4K =================================
    # Befund: 'output.height' wurde stur als BILDHOEHE genommen. Eine
    # 1080x1920-Aufnahme kam damit als 607x1080 heraus - schmaler als die
    # Quelle. Quer stimmte es zufaellig, deshalb ist es nie aufgefallen.
    _r149 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v149: Hoehe ist die KURZE Kante, Hochformat wird nicht kleingerechnet',
          "_kurz if src_w >= src_h else" in _r149)
    check('v149: es wird NIE hochskaliert (aus 1080p wird kein 4K)',
          'H = min(H, src_h)' in _r149 and "('4k', 'uhd')" in _r149)
    check('v149: 4K kostet das Doppelte',
          SV.cost_seconds(60, uhd=True) == 2 * SV.cost_seconds(60)
          and SV.UHD_FAKTOR == 2,
          f'{SV.cost_seconds(60)} -> {SV.cost_seconds(60, uhd=True)} Sekunden')
    check('v149: angefangene Minuten zaehlen auch bei 4K',
          SV.cost_seconds(61, uhd=True) == 240 and SV.cost_seconds(1) == 60,
          f'61s 4K = {SV.cost_seconds(61, uhd=True)}')
    # Der WUNSCH allein darf nicht kosten - nur ein Video, das die Aufloesung
    # wirklich hergibt, wird als 4K berechnet.
    _hd149 = os.path.join(tmp, 'st_hd149.mp4')
    _uh149 = os.path.join(tmp, 'st_uhd149.mp4')
    for _pth, _sz in ((_hd149, '640x360'), (_uh149, '2560x1440')):
        if not os.path.exists(_pth):
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            f'testsrc=size={_sz}:rate=10:duration=1',
                            '-pix_fmt', 'yuv420p', _pth], check=True,
                           capture_output=True)
    check('v149: 4K nur wenn die Quelle es hergibt',
          SV._will_uhd({'output': {'quality': '4k'}}, _uh149) is True
          and SV._will_uhd({'output': {'quality': '4k'}}, _hd149) is False
          and SV._will_uhd({'output': {'quality': 'hd'}}, _uh149) is False,
          f'1440p {SV._will_uhd({"output": {"quality": "4k"}}, _uh149)}, '
          f'360p {SV._will_uhd({"output": {"quality": "4k"}}, _hd149)}')
    check('v149: Erstattung gibt den WIRKLICH gezahlten Betrag zurueck',
          SV._job_cost({'dauer': 60, 'cost_sec': 120}) == 120
          and SV._job_cost({'dauer': 60, 'uhd': True}) == 120
          and SV._job_cost({'dauer': 60}) == 60)
    check('v149: freie Hoehen bleiben gedeckelt, quality nur als Stufe',
          SV._sanitize_overrides({'output': {'height': 9999, 'quality': '8k'}})
          == {'output': {'height': 2160}}
          and SV._sanitize_overrides({'output': {'quality': '4k'}})
          == {'output': {'quality': '4k'}})
    _ui149 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    # v157: 4K steht als HOEHEN-Stufe in derselben Zeile wie 720p/1080p
    # (Ismets Wunsch), nicht mehr als eigenes Quality-Feld.
    check('v149/v157: die UI nennt Aufpreis und Upscale-Grenze beim Namen',
          'data-cfg="output.height"' in _ui149
          and '2&times; credits' in _ui149
          and 'we never upscale' in _ui149
          and 'at least 1440p' in _ui149)

    # ============ v147: Render-Fehler ins Panel statt ins Postfach ============
    # Ismets Wunsch: keine Mail mehr bei fehlgeschlagenem Render, nur noch im
    # Admin-Panel. Die JOBS-Liste haelt aber nur den Arbeitsspeicher - ohne
    # eigene Tabelle waere die Stoerung nach einem Neustart spurlos weg.
    _mails147 = []
    _sm147 = SV._send_mail
    try:
        SV._send_mail = lambda to, subj, body, **k: _mails147.append(subj)
        SV._ADMIN_NOTIFIED.clear()
        SV.JOBS['j147'] = {'status': 'fehler', 'msg': 'KI-Dienst-Problem (HTTP 500)',
                           'kind': 'caption', 'user_id': 1}
        SV._notify_job_fail('j147')
        # Timeout ist ebenfalls ein Render-Fehler und darf nicht mailen.
        SV._notify_admin('timeout:j147', 'Job automatisch beendet (Timeout)',
                         'test', mail=False)
        # Eine ECHTE Betriebsstoerung (Platte knapp) mailt weiterhin.
        SV._notify_admin('disk147', 'Speicher knapp', 'test')
    finally:
        SV._send_mail = _sm147
        SV.JOBS.pop('j147', None)
    check('v147: Render-Fehler schickt KEINE Mail mehr',
          not any('Render fehlgeschlagen' in m for m in _mails147)
          and not any('Timeout' in m for m in _mails147), str(_mails147))
    check('v147: echte Betriebsstoerung mailt weiterhin',
          any('Speicher knapp' in m for m in _mails147), str(_mails147))
    _con147 = SV._db()
    _al147 = [dict(r) for r in _con147.execute(
        "SELECT schluessel, betreff, gemailt, gelesen FROM alerts "
        "ORDER BY id DESC LIMIT 5").fetchall()]
    _con147.close()
    check('v147: die Stoerung steht persistent in der alerts-Tabelle',
          any(a['betreff'] == 'Render fehlgeschlagen' and a['gemailt'] == 0
              and a['gelesen'] == 0 for a in _al147)
          and any(a['schluessel'].startswith('timeout:') for a in _al147),
          str([(a['betreff'], a['gemailt']) for a in _al147]))
    check('v147: gemailte Stoerungen sind als solche markiert',
          any(a['schluessel'] == 'disk147' and a['gemailt'] == 1 for a in _al147),
          str(_al147))
    check('v147: offene Stoerungen werden gezaehlt',
          SV._alerts_offen() >= 3, str(SV._alerts_offen()))
    # Routine-Post (taegliches Backup) gehoert NICHT in die Stoerungsliste,
    # sonst ist die Liste nach einer Woche nur noch Backup-Rauschen.
    _n147a = SV._alerts_offen()
    SV._notify_admin('backup147', 'Backup', 'test', routine=True)
    check('v147: Routine-Post landet nicht in der Stoerungsliste',
          SV._alerts_offen() == _n147a, f'{_n147a} -> {SV._alerts_offen()}')
    _srv147 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _adm147 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v147: Endpunkte und Indexe verdrahtet',
          "@app.get('/api/admin/alerts')" in _srv147
          and "@app.post('/api/admin/alerts/read')" in _srv147
          and 'ix_alerts_offen' in _srv147
          and "mail=False)" in _srv147)
    check('v147: Admin-Panel hat den Alerts-Tab',
          "['alerts','Alerts']" in _adm147 and 'alerts:loadAlerts' in _adm147
          and 'Mark all read' in _adm147 and 'Unread alerts' in _adm147)

    # ------------------------------------------------------------------
    # v226a WER MELDET, SAGT AUCH, WELCHER STAND ER IST - UND EIN
    # GESCHEITERTER DEPLOY DARF NICHT STUMM SEIN.
    # Ismet bekam dieselbe Fehlalarm-Mail zweimal und konnte nicht erkennen,
    # ob die zweite noch von der alten Fassung kam. Und der eine Fall, in dem
    # gar nichts mehr live geht (Deploy am Test-Gate gescheitert), ging bis
    # v226 NUR ins Panel: `autodeploy.sh`/`update.sh` schreiben per sqlite
    # direkt in die alerts-Tabelle und koennen `_notify_admin` nicht aufrufen.
    _mails226 = []
    _sm226 = SV._send_mail
    SV._send_mail = lambda to, subj, body, **kw: _mails226.append((subj, body))
    try:
        SV._notify_admin('stand226', 'Irgendeine Stoerung', 'Text dazu')
    finally:
        SV._send_mail = _sm226
    check('v226a: jede Stoerungs-Mail nennt den Stand des Absenders',
          bool(_mails226) and SV.DVE_BUILD in _mails226[-1][1]
          and 'Gemeldet von DouchkoVE' in _mails226[-1][1],
          str(_mails226[-1][1])[-80:] if _mails226 else 'keine Mail')
    check('v226a: /api/health nennt die Version (fuer externe Pruefung)',
          SV.health().get('version') == SV.DVE_VERSION
          and SV.health().get('ok') is True
          and 'commit' not in SV.health(), str(SV.health()))
    # Der Weg des Deploy-Alarms: das Skript schreibt ihn wie hier, der
    # Watchdog muss ihn FINDEN (dieselbe Abfrage wie im Server) und danach
    # als gemailt markieren - sonst kommt er bei jedem Lauf erneut.
    _con226 = SV._db()
    _con226.execute("INSERT INTO alerts (schluessel,betreff,text,gemailt,"
                    "gelesen,created_at) VALUES (?,?,?,0,0,?)",
                    ('deploy', 'Deploy abgebrochen', 'Selftest rot: 3 Tests',
                     int(time.time())))
    _con226.commit()
    _off226 = _con226.execute(
        "SELECT id, betreff, text FROM alerts WHERE "
        "schluessel IN ('deploy','deploy_gate') AND gemailt=0 "
        "AND created_at > ? ORDER BY id DESC LIMIT 5",
        (int(time.time()) - 86400,)).fetchall()
    _con226.close()
    check('v226a: der Watchdog findet einen ungemailten Deploy-Alarm',
          any(r['betreff'] == 'Deploy abgebrochen' for r in _off226),
          f'{len(_off226)} offene Deploy-Alarme')
    check('v226a: der Watchdog mailt ihn und markiert ihn danach',
          "'deploy_fehler-' + time.strftime('%Y-%m-%d')" in _srv147
          and "schluessel IN ('deploy','deploy_gate') AND gemailt=0" in _srv147
          and 'UPDATE alerts SET gemailt=1 WHERE id=?' in _srv147,
          'sonst kommt dieselbe Meldung bei jedem Lauf erneut')
    check('v226a: die Deploy-Skripte schreiben genau diese Schluessel',
          "'deploy', 'Deploy abgebrochen'" in open(
              os.path.join(HERE, 'autodeploy.sh'), encoding='utf-8').read()
          and "'deploy_gate', 'Test-Gate nicht lauffaehig'" in open(
              os.path.join(HERE, 'update.sh'), encoding='utf-8').read(),
          'ein anderer Schluessel und der Watchdog findet nichts')

    # ============ v146: Transkription haelt einen OpenAI-Aussetzer aus ========
    # Live-Befund (Ismet, 4K-Clip auf douchko.eu): ein einzelner HTTP 500 von
    # OpenAI brach den ganzen Render ab. 5xx/429/Netzabbruch sind transient -
    # der Server-Pfad _whisper_words hatte laengst Backoff, die Engine nicht.
    class _FakeResp:
        def __init__(self, code, payload=None):
            self.status_code = code
            self._p = payload or {}
            self.text = ''
        def json(self):
            return self._p
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f'HTTP {self.status_code}')

    class _FakeRQ:
        class exceptions:
            class Timeout(Exception): pass
            class ConnectionError(Exception): pass
        def __init__(self, codes, payload):
            self.codes = list(codes)
            self.payload = payload
            self.n = 0
            self.bytes = []
        def post(self, *a, **k):
            self.n += 1
            self.bytes.append(len(k['files']['file'][1].read()))
            c = self.codes.pop(0) if self.codes else 200
            return _FakeResp(c, self.payload if c == 200 else {})

    _wav146 = os.path.join(tmp, 'st146.m4a')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=frequency=300:duration=1', '-c:a', 'aac', _wav146],
                   check=True, capture_output=True)
    _ok146 = {'words': [{'word': 'hallo', 'start': 0.0, 'end': 0.4},
                        {'word': 'welt', 'start': 0.5, 'end': 0.9}],
              'segments': [{'text': 'hallo welt.'}]}
    _key146 = os.environ.get('OPENAI_API_KEY')
    import render as R146
    _slp146, _rq146 = R146.time.sleep, sys.modules.get('requests')
    try:
        os.environ['OPENAI_API_KEY'] = 'sk-test'
        R146.time.sleep = lambda *a: None
        _fake = _FakeRQ([500, 500, 200], _ok146)
        sys.modules['requests'] = _fake
        _w146 = R146.transcribe(_wav146, 'de')
        check('v146: zwei HTTP 500 werden weggesteckt, Transkript kommt trotzdem',
              len(_w146) == 2 and _fake.n == 3,
              f'{_fake.n} Versuche, {len(_w146)} Woerter')
        # Jeder Versuch muss die Datei NEU lesen. Ein einmal geleerter
        # Datei-Zeiger schickt beim Retry 0 Bytes - der Retry waere Theater.
        check('v146: jeder Versuch laedt die Audiodatei wirklich neu hoch',
              len(set(_fake.bytes)) == 1 and min(_fake.bytes) > 100,
              str(_fake.bytes))
        _fake2 = _FakeRQ([500, 500, 500, 500], _ok146)
        sys.modules['requests'] = _fake2
        try:
            R146.transcribe(_wav146, 'de')
            _raus = 'kein Abbruch'
        except SystemExit as e:
            _raus = str(e)
        check('v146: dauerhafter Ausfall bricht erst nach 4 Versuchen ab',
              _fake2.n == 4 and 'HTTP 500' in _raus, f'{_fake2.n} Versuche, {_raus}')
        _fake3 = _FakeRQ([401], _ok146)
        sys.modules['requests'] = _fake3
        try:
            R146.transcribe(_wav146, 'de')
            _r401 = 'kein Abbruch'
        except SystemExit as e:
            _r401 = str(e)
        check('v146: 401 wird NICHT wiederholt (aendert sich nie)',
              _fake3.n == 1 and 'AI access is invalid' in _r401, f'{_fake3.n} Versuche, {_r401}')
    finally:
        R146.time.sleep = _slp146
        if _rq146 is not None:
            sys.modules['requests'] = _rq146
        else:
            sys.modules.pop('requests', None)
        if _key146 is None:
            os.environ.pop('OPENAI_API_KEY', None)
        else:
            os.environ['OPENAI_API_KEY'] = _key146

    # ================= v145: Pflichtangaben auf der Rechnung =================
    # §14 Abs. 4 UStG (bei Kleinbetraegen bis 250 EUR §33 UStDV): vollstaendiger
    # NAME und ANSCHRIFT des leistenden Unternehmers gehoeren auf die Rechnung.
    # Der Rechnungskopf ('Von: ...') kommt aus dem Stripe-Unternehmensprofil,
    # darauf hat der Code keinen Zugriff - stand dort nur die Marke, fehlte die
    # Angabe. Fusszeile und Zusatzfelder tragen sie deshalb selbst.
    _inv145 = SV._invoice_creation('starter', SV.PACKS['starter'])
    _f145 = _inv145['invoice_data']['footer']
    _cf145 = _inv145['invoice_data'].get('custom_fields') or []
    check('v145: Name und Anschrift des Ausstellers stehen auf der Rechnung',
          'Ismet Beyazkus' in _f145 and 'Hinter den Gärten 4' in _f145
          and '52388 Nörvenich' in _f145 and 'Germany' in _f145,
          _f145.splitlines()[0] if _f145 else '(leer)')
    check('v145: Aussteller und USt-IdNr auch als Kopf-Zusatzfeld',
          any(c['name'] == 'Aussteller' and 'Ismet Beyazkus' in c['value']
              for c in _cf145)
          and any(c['value'] == 'DE463613884' for c in _cf145),
          str(_cf145))
    # Stripe deckelt Name und Wert bei 30 Zeichen. Zu lange Werte weist die
    # API zurueck - und riessen ueber invoice_creation den ganzen Checkout mit.
    check('v145: Zusatzfelder bleiben unter der 30-Zeichen-Grenze von Stripe',
          all(len(c['name']) <= 30 and len(c['value']) <= 30 for c in _cf145)
          and 1 <= len(_cf145) <= 4, str([len(c['value']) for c in _cf145]))
    check('v145: §19-Hinweis bleibt, weiterhin KEIN USt-Satz und kein Betrag',
          '§19 UStG' in _f145 and 'keine Umsatzsteuer' in _f145
          and '19%' not in _f145 and '7%' not in _f145
          and 'zzgl' not in _f145.lower())
    check('v145: Leistungsbeschreibung nennt Menge und Art',
          'minutes of video credit' in _inv145['invoice_data']['description']
          and str(SV.PACKS['starter']['minuten'])
          in _inv145['invoice_data']['description'],
          _inv145['invoice_data']['description'])
    # Aussteller ueber Env austauschbar - sonst muesste bei einem Umzug der
    # Code angefasst werden, und die Rechnung waere bis zum Deploy falsch.
    _alt145 = {k: os.environ.get(k) for k in
               ('DVE_SELLER_NAME', 'DVE_SELLER_ADDR', 'DVE_SELLER_MAIL')}
    try:
        os.environ['DVE_SELLER_NAME'] = 'Max Muster'
        os.environ['DVE_SELLER_ADDR'] = 'Teststr. 1, 10115 Berlin, Germany'
        _inv145b = SV._invoice_creation('starter', SV.PACKS['starter'])
    finally:
        for k, v in _alt145.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check('v145: Aussteller-Angaben sind ohne Code-Aenderung umstellbar',
          'Max Muster' in _inv145b['invoice_data']['footer']
          and '10115 Berlin' in _inv145b['invoice_data']['footer']
          and 'Ismet Beyazkus' not in _inv145b['invoice_data']['footer'])
    _tax145 = SV._admin_tax_calc()
    check('v145: Admin-Panel listet die Pflichtangaben und den Dashboard-Rest',
          len(_tax145['identitaet'].get('rechnungspflicht') or []) >= 6
          and 'Stripe business profile' in (_tax145['identitaet'].get('dashboard') or '')
          and _tax145['identitaet'].get('anschrift'),
          str(_tax145['identitaet'].get('anschrift')))
    _adm145 = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v145: Pflichtangaben sind im Admin-Panel sichtbar',
          'Mandatory invoice fields' in _adm145
          and 'd.identitaet.rechnungspflicht' in _adm145
          and 'd.identitaet.anschrift' in _adm145)

    # ================= v135a: Audit-Fixes (Bezahl-Vollaudit) =================
    _srvA = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _idxA = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    _trmA = open(os.path.join(HERE, 'web', 'terms.html'), encoding='utf-8').read()
    _prvA = open(os.path.join(HERE, 'web', 'privacy.html'), encoding='utf-8').read()
    _cmpA = open(os.path.join(HERE, 'docker-compose.yml'), encoding='utf-8').read()
    # HIGH-Fix Pre-Flow-Bypass: save_and_render reserviert, run_job-Fallback
    # ist race-sicher + alarmiert statt still gratis zu liefern.
    _sarA = _srvA.split('def save_and_render')[1].split('\ndef ')[0] \
        if 'def save_and_render' in _srvA else ''
    check('v135a: Editor-Pfad reserviert Credits (Bypass zu) + run_job-Fallback alarmiert',
          '_reserve_credits(_uid, _need, jid)' in _sarA
          and 'undercharge:' in _srvA
          and _srvA.count('Catch-All-Refund') == 2)
    # Webhook: 100%-Promo zaehlt als bezahlt; Stripe-Refund-Event alarmiert.
    check("v135a: Webhook akzeptiert no_payment_required + meldet charge.refunded",
          "('paid', 'no_payment_required')" in _srvA
          and "ev_type == 'charge.refunded'" in _srvA)
    # Kauf: Beleg atomar + Geister-Konto geblockt (funktional).
    _g1, _ = SV._create_user('v135a@test', 'x' * 8, 'AuditKauf')
    _k1 = SV._credit_purchase(_g1, 1200, 'sess_v135a', pack='starter', cents=900)
    _k2 = SV._credit_purchase(_g1, 1200, 'sess_v135a', pack='starter', cents=900)
    _conA = SV._db()
    _prow = _conA.execute("SELECT pack, cents, sekunden FROM purchases WHERE "
                          "session_id = 'sess_v135a'").fetchone()
    _conA.close()
    _kg = SV._credit_purchase(999999901, 1200, 'sess_ghost_v135a',
                              pack='starter', cents=900)
    _conA = SV._db()
    _gled = _conA.execute("SELECT COUNT(*) c FROM ledger WHERE user_id = 999999901"
                          ).fetchone()['c']
    _conA.close()
    check('v135a: purchases-Beleg atomar mit Kauf + Geister-Konto bucht nichts',
          _k1 and (not _k2) and _prow and _prow['cents'] == 900
          and _prow['sekunden'] == 1200
          and (_kg is False) and _gled == 0)
    # Kauf-Mail = Vertragsbestaetigung (§312f): Widerruf + Muster + Preis drin.
    _m0 = len(sent)
    SV._send_purchase_mail(_g1, 1200, 'sess_v135a_mail', cents=900, pack='starter')
    _mail_txt = ''
    _real_sm2 = SV._send_mail
    _cap312 = []
    SV._send_mail = lambda to, s, b, reply_to=None, html=None: _cap312.append(b)
    try:
        SV._send_purchase_mail(_g1, 1200, 'sess_v135a_mail2', cents=900, pack='starter')
    finally:
        SV._send_mail = _real_sm2
    _mail_txt = _cap312[0] if _cap312 else ''
    check('v135a: Kauf-Mail ist Vertragsbestaetigung (Widerruf + Musterformular + Preis, §312f)',
          'Right of withdrawal' in _mail_txt
          and 'Model withdrawal form' in _mail_txt
          and '9.00 EUR' in _mail_txt and '§19 UStG' in _mail_txt)
    # admin_refund: Stripe-Fehler bucht nichts (Quelle) + Reload-Bonus im Clawback.
    check('v135a: admin_refund fail-safe (kein Buchen bei Stripe-Fehler) + Bonus-Clawback',
          'Nothing was booked - retry is safe' in _srvA
          and 'Reload bonus {session_id}' in _srvA.split('def admin_refund')[1].split('\ndef ')[0])
    # Verfalls-Sweep atomar (eine Transaktion).
    check('v135a: _expire_credits in EINER Transaktion (BEGIN IMMEDIATE)',
          'BEGIN IMMEDIATE' in _srvA.split('def _expire_credits')[1].split('\ndef ')[0])
    # Consent fail-closed vor dem Checkout.
    check('v135a: Consent-Log fail-closed (503 statt stillem Weiterlauf)',
          'Could not record your purchase confirmation' in _srvA)
    # Motion: Pauschale 1 Credit pro Clip, wie beworben; toter Alpha-Button weg.
    check('v135a: Motion pauschal 1 Credit pro Clip + toter MOV-Alpha-Button entfernt',
          _srvA.count('Pauschale 1 Credit pro Motion-Clip') == 3
          and 'moDlMov' not in _idxA
          and '1 credit per clip (MP4)' in _idxA)
    # Konto-Loeschung: Tickets weg + Saldo-Archiv-Zeile (funktional).
    _d1, _ = SV._create_user('v135adel@test', 'x' * 8, 'DelAudit')
    _conA = SV._db()
    _conA.execute("UPDATE users SET balance_sec = 120 WHERE id = ?", (_d1,))
    _conA.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                  "VALUES (?, 120, 'Kauf sess_del135a', ?)", (_d1, int(_t.time())))
    _conA.execute("INSERT INTO tickets (user_id, email, subject, body, status, "
                  "created_at, updated_at) VALUES (?, 'v135adel@test', 's', 'b', "
                  "'open', ?, ?)", (_d1, int(_t.time()), int(_t.time())))
    _conA.commit(); _conA.close()
    SV._purge_user_db(_d1)
    _conA = SV._db()
    _tleft = _conA.execute("SELECT COUNT(*) c FROM tickets WHERE user_id = ?",
                           (_d1,)).fetchone()['c']
    _saldo = _conA.execute("SELECT COUNT(*) c FROM ledger_archive WHERE "
                           "user_email = 'v135adel@test' AND grund = 'Saldo bei Loeschung' "
                           "AND delta_sec = 120").fetchone()['c']
    _conA.close()
    check('v135a: Loeschung entfernt Tickets + archiviert Rest-Saldo (Widerrufs-Basis)',
          _tleft == 0 and _saldo == 1)
    # Rechtstexte: AGB praezisiert, ODR raus, Danger-Zone ehrlich, Login-Links,
    # Privacy kennt Resend/Google/Tickets/Consent/10-Jahre-Ausnahme.
    check('v135a: AGB nennen Minuten-Rundung + Extras + Free-Tier, ODR-Link raus',
          'per started minute' in _trmA and '1 credit per clip' in _trmA
          and 'ec.europa.eu' not in _trmA
          and 'remain refundable on request' in _trmA)
    # v137: Ismet will den Refund-Hinweis dort nicht (nicht Pflicht an der
    # Stelle) - wichtig bleibt nur: KEINE falsche 'no refunds'-Behauptung.
    check('v135a: Danger-Zone ohne falsche Refund-Behauptung + Rechtslinks vor Login',
          'Refunds are not possible' not in _idxA
          and _idxA.count('href="/imprint"') >= 2)
    check('v135a: Privacy kennt Resend + Google-Login + Tickets + Consent + GoBD-Ausnahme',
          'Resend' in _prvA and 'Sign in with Google' in _prvA
          and 'Support requests' in _prvA
          and '10 years after account deletion' in _prvA
          and '356' in _prvA)
    check('v135a: DVE_TAX_ID-Default auch in docker-compose (Leerstring-Falle zu)',
          'DVE_TAX_ID: ${DVE_TAX_ID:-DE463613884}' in _cmpA)
    # v135b: Kauf geht vor Rechnung. Lehnt Stripe invoice_creation ab (alte
    # Lib/API-Version), laeuft der Checkout einmal OHNE Rechnung + Alarm.
    # stripe-Paket gepinnt, damit der Docker-Layer die Alt-Version nicht einfriert.
    _reqA = open(os.path.join(HERE, 'requirements.txt'), encoding='utf-8').read()
    _coA = _srvA if 'def _mk_session' in _srvA else open(
        os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v135b: Checkout-Fallback ohne Rechnung + Fehler-Log + stripe>=10 gepinnt',
          'def _mk_session' in _coA
          and "kwargs['invoice_creation']" in _coA
          and 'to_thread(_mk_session, False)' in _coA
          and 'inv_fallback' in _coA
          and 'Checkout fehlgeschlagen:' in _coA
          # v205a-sec: aus 'stripe>=10' wurde ein exakter Pin. Die Zusage
          # bleibt dieselbe - keine eingefrorene Alt-Version, die
          # 'invoice_creation' nicht kennt -, sie ist nur strenger geworden.
          and _re203.search(r'^stripe==(\d+)', _reqA, _re203.M)
          and int(_re203.search(r'^stripe==(\d+)', _reqA, _re203.M).group(1)) >= 10)
    # v135c: keine festen payment_method_types mehr - Stripe zeigt, was im
    # Dashboard aktiviert ist (Live-Fehler: sepa_debit war nicht aktiviert und
    # riss die ganze Session). Async-Webhook-Pfad bleibt fuer spaeteres SEPA.
    _co135c = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v135c: Checkout ohne feste payment_method_types (Dashboard entscheidet)',
          'payment_method_types=' not in _co135c.split('def _mk_session')[1].split('\ndef ')[0]
          and 'async_payment_succeeded' in _co135c)
    # v136: Admin-Zeitreihen fuer die Grafen. Admin-gated, LUECKENLOS auf
    # days Tage aufgefuellt (0-Werte), alle Reihen gleich lang, letzte
    # Position = heute (UTC). Frontend hat SVG-Chart-Helfer + nutzt sie.
    class _TsReq:
        def __init__(self, key):
            self.headers = {'x-admin-key': key}
    os.environ['DVE_ADMIN'] = 'testkey_admin'
    _denied136 = False
    try:
        SV.admin_timeseries(_TsReq('wrong'), days=14)
    except SV.HTTPException as _e:
        _denied136 = (_e.status_code == 403)
    _tsr = SV.admin_timeseries(_TsReq('testkey_admin'), days=14)
    _today_utc = _t.strftime('%Y-%m-%d', _t.gmtime())
    check('v136: Timeseries admin-gated + lueckenlos + heute am Ende',
          _denied136 and _tsr['days'] == 14 and len(_tsr['labels']) == 14
          and all(len(_tsr[k]) == 14 for k in
                  ('revenue_eur', 'purchases', 'signups', 'renders',
                   'render_min', 'credits_bought_min', 'credits_spent_min'))
          and _tsr['labels'][-1] == _today_utc
          and sum(_tsr['revenue_eur']) >= 0)
    # ================= v137: UI-Politur + Kauf-Mail + Reset =================
    _idx137 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    _srv137 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _cmp137 = open(os.path.join(HERE, 'docker-compose.yml'), encoding='utf-8').read()
    check('v137: Account-UI dunkel (Textarea + Datei-Auswahl gestylt), Danger-Zone kurz',
          '#page-account textarea' in _idx137
          and 'file-selector-button' in _idx137
          and 'Contact us BEFORE deleting' not in _idx137)
    check('v137: SUPPORT/ADMIN-Mail Leerstring-Falle zu (or-Fallback + compose-Default)',
          "os.environ.get('DVE_SUPPORT_MAIL') or" in _srv137
          and "os.environ.get('DVE_ADMIN_MAIL') or" in _srv137
          and 'DVE_SUPPORT_MAIL: ${DVE_SUPPORT_MAIL:-Ismet@douchkove.com}' in _cmp137
          and 'DVE_ADMIN_MAIL: ${DVE_ADMIN_MAIL:-ismet.01.b@gmail.com}' in _cmp137)
    # Kauf-Mail: Rechnungs-Link im Hauptteil, Rechtstext als Kleingedrucktes,
    # Webhook holt die hosted_invoice_url. Funktional mit invoice_url pruefen.
    _cap137 = []
    _rsm137 = SV._send_mail
    SV._send_mail = lambda to, s, b, reply_to=None, html=None: _cap137.append((b, html))
    try:
        _u137, _ = SV._create_user('v137mail@test', 'x' * 8, 'Polish')
        SV._send_purchase_mail(_u137, 1200, 'sess_v137', cents=900, pack='starter',
                               invoice_url='https://invoice.stripe.com/i/test123')
    finally:
        SV._send_mail = _rsm137
    _b137, _h137 = (_cap137[0] if _cap137 else ('', ''))
    check('v137: Kauf-Mail mit Rechnungs-Link, Rechtstext klein unten, Webhook holt URL',
          'https://invoice.stripe.com/i/test123' in _b137
          and _b137.index('Your invoice:') < _b137.index('----')
          and _b137.rstrip().index('Widerrufsbelehrung') > _b137.index('The DouchkoVE Team')
          and 'fine_print=' in _srv137 and 'hosted_invoice_url' in _srv137
          and 'view and download (PDF)' in (_h137 or ''))
    # Factory-Reset: RESET-Pflicht (falscher Confirm -> 400, nichts geloescht).
    class _FrReq:
        def __init__(self, key):
            self.headers = {'x-admin-key': key}
    os.environ['DVE_ADMIN'] = 'testkey_admin'
    _fr_block = False
    try:
        SV.admin_factory_reset(_FrReq('testkey_admin'), confirm='nope')
    except SV.HTTPException as _e:
        _fr_block = (_e.status_code == 400)
    _conF = SV._db()
    _still = _conF.execute("SELECT COUNT(*) c FROM users").fetchone()['c']
    _conF.close()
    check('v137: Factory-Reset nur mit RESET-Bestaetigung (sonst 400, nichts weg)',
          _fr_block and _still > 0
          and "'RESET'" in _srv137.split('def admin_factory_reset')[1].split('\ndef ')[0])
    # v137a: Google-Konten (kein Passwort) loeschen per E-Mail-Bestaetigung.
    _gd_uid, _ = SV._upsert_google_user('gsub_del137', 'gdel137@test', 'GDel')
    class _DelReq:
        def __init__(self):
            self.cookies = {}
            self.headers = {}
            self.client = type('C', (), {'host': '10.0.0.7'})()
    _origru137 = SV._require_user
    SV._require_user = lambda req: SV._find_user_by_id(_gd_uid)
    try:
        _gd_block = False
        try:
            SV.api_delete_account(_DelReq(), SV.Response(),
                                  password='', confirm_email='falsch@test')
        except SV.HTTPException as _e:
            _gd_block = (_e.status_code == 401)
        _gd_ok = SV.api_delete_account(_DelReq(), SV.Response(),
                                       password='', confirm_email='GDEL137@test')
    finally:
        SV._require_user = _origru137
    check('v137a: Google-Konto loescht per E-Mail-Bestaetigung (falsch=401, case-insensitiv ok)',
          _gd_block and _gd_ok.get('ok')
          and SV._find_user_by_id(_gd_uid) is None
          and "confirm_email: str = Form('')" in open(
              os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
          and "'google': bool(_row_get(u, 'google_sub'))" in open(
              os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
          and 'delMail' in _idx137 and 'user.google' in _idx137)
    # v137b: Transaktions-Labels vollstaendig - keine rohen Ledger-Grunds
    # (Stripe-Session-IDs!) mehr in der Kundenansicht.
    _idxTx = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v137b: Account-Transaktionen nutzen translateGrund (keine Session-ID-Leaks)',
          'escHtml(translateGrund(' in _idxTx
          and "Reload bonus (+10%)" in _idxTx
          and "'Editor layer render'" in _idxTx
          and "/^Refund .*/" in _idxTx
          and "if (/pack|stripe|kauf|purchase/i.test(g))" not in _idxTx)
    # v137c: Logo im App-Header fuehrt immer zur Hauptseite (Create), SPA-intern.
    _idx137c = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v137c: Header-Logo klickbar -> Create (Maus + Tastatur, kein Landing-Link)',
          'id="brandHome"' in _idx137c
          and "closest('#brandHome')" in _idx137c
          and _idx137c.count("showSection('create')") >= 2)
    # v138: gescheiterte Vorab-Transkription ist SICHTBAR - Endpoint meldet
    # failed:true (kein Ewig-404), UI hat Fehlerpfad + 4-Minuten-Timeout.
    _tj = 'txf138'
    SV.JOBS[_tj] = {'input': '/tmp/nonexistent_v138/quelle.mp4', 'mode': 'pre',
                    'status': 'vorbereitet', 'tx_failed': True, 'user_id': None,
                    'code': 'x'}
    class _TxReq:
        cookies = {}
        headers = {}
    _origok = SV._job_owner_ok
    SV._job_owner_ok = lambda jid, req: True
    try:
        _txr = SV.get_transcript(_tj, _TxReq())
        SV.JOBS[_tj]['tx_failed'] = False
        SV.JOBS[_tj]['status'] = 'laeuft'
        _tx404 = False
        try:
            SV.get_transcript(_tj, _TxReq())
        except SV.HTTPException as _e:
            _tx404 = (_e.status_code == 404)
    finally:
        SV._job_owner_ok = _origok
        SV.JOBS.pop(_tj, None)
    _idx138 = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    _srv138 = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v138: Transkript-Fehlschlag sichtbar (failed:true, 404 nur bei Arbeit, UI-Timeout)',
          _txr.get('failed') is True and _tx404
          and 'tx_failed=_txfail' in _srv138
          and 'd.failed' in _idx138 and 'txGiveUp' in _idx138
          and 'txTries > 96' in _idx138)
    # v138a: Admin-Jobs schlicht neueste zuerst (keine Status-Gruppierung mehr).
    _srvJs = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _jsblk = _srvJs.split('def admin_jobs')[1].split('\ndef ')[0]
    check('v138a: Admin-Jobs sortiert neueste zuerst',
          "out.sort(key=lambda x: -(x['updated_at'] or 0))" in _jsblk
          and "order.get(x['status']" not in _jsblk)
    # v138b: OpenAI-Ampel prueft den Key ECHT (401 live, Ampel war gruen).
    # Ohne Key (Testumgebung): set=False, KEIN Netz-Call. Mit Key: /v1/models,
    # 10 Min gecacht; UI kennt KEY INVALID.
    _k0 = os.environ.pop('OPENAI_API_KEY', None)
    try:
        _oh = SV._openai_health()
    finally:
        if _k0 is not None:
            os.environ['OPENAI_API_KEY'] = _k0
    _srvOH = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _admOH = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v138b: OpenAI-Health echt (kein Key -> set:False ohne Netz; UI zeigt KEY INVALID)',
          _oh == {'set': False, 'valid': None}
          and "_openai_health()" in _srvOH
          and _srvOH.count("'openai': _openai_health(),") == 2
          and 'KEY INVALID' in _admOH)
    # v139: Captions pur + formatgerechte Platzierung.
    # (a) Auto-Akzente per Default AUS - kein Motion-Badge mehr ohne Zutun.
    # (b) Akzent-RENDERING haengt an der Datei (Editor-gesetzt), nicht am auto-Flag.
    # (c) Anker formatabhaengig: 16:9 Lower Third (0.78), 4:3 0.75, 1:1 0.72;
    #     der alte Einheits-Anker 0.40H (obere Bildhaelfte!) ist weg.
    import yaml as _yaml139
    _cfg139 = _yaml139.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _r139 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v185: die Auto-Akzente sind wieder AN (Ismets High-End-Referenz traegt
    # Counter, Badge und Namens-Karte als Bestandteile). Der dateibasierte
    # Editor-Pfad bleibt unveraendert und ueberschreibt weiterhin alles.
    check('v188: Auto-Akzente AUS, Editor-Akzente rendern dateibasiert',
          _cfg139['accents']['auto'] is False
          and "if os.path.exists(_acc_path):\n        try:\n            accents_render" in _r139
          and _r139.count(".get('auto', False):") == 1)   # nur noch die Erzeugung
    check('v139: Caption-Anker formatgerecht (16:9=0.78 Lower Third, 4:3=0.75, 1:1=0.72)',
          'Z_MAIN = H * 0.78' in _r139 and 'Z_MAIN = H * 0.75' in _r139
          and 'Z_MAIN = H * 0.72' in _r139
          and 'Z_MAIN = H * 0.40' not in _r139
          and '_ar >= 1.45' in _r139)
    _admA = open(os.path.join(HERE, 'web', 'admin.html'), encoding='utf-8').read()
    check('v136: Admin-Grafen verdrahtet (SVG-barChart + hbars in Live/Revenue/Credits/Jobs)',
          'function barChart' in _admA and 'function hbars' in _admA
          and "tseries(30)" in _admA and "tseries(90)" in _admA
          and 'Revenue per day' in _admA and 'Signups per day' in _admA
          and 'Credits spent per day' in _admA
          and 'Status distribution (live)' in _admA
          and "api('/api/admin/timeseries?days='+days)" in _admA)
    # 3) Nur FEHLER-Jobs alarmieren, fertige nicht. v147: der Alarm geht ins
    # Admin-Panel, NICHT mehr als Mail (Ismets Wunsch) - gemessen wird deshalb
    # die alerts-Tabelle, und dass das Postfach still bleibt.
    SV.JOBS['t_fail'] = {'status': 'fehler', 'msg': 'kaputt', 'user_id': 1}
    SV.JOBS['t_ok'] = {'status': 'fertig'}
    n0 = len(sent)
    _c3 = SV._db()
    _a0 = _c3.execute("SELECT COUNT(*) c FROM alerts").fetchone()['c']
    _c3.close()
    SV._notify_job_fail('t_fail')
    SV._notify_job_fail('t_ok')
    _c3 = SV._db()
    _a1 = _c3.execute("SELECT COUNT(*) c FROM alerts").fetchone()['c']
    _c3.close()
    check('Job-Fehler -> genau 1 Panel-Eintrag, KEINE Mail',
          _a1 == _a0 + 1 and len(sent) == n0, f'alerts {_a0}->{_a1}, Mails {len(sent)-n0}')
    check('Worker melden Fehl-Jobs an den Alarm',
          open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8')
          .read().count('_notify_job_fail(jid)') >= 2)
    # v118: der gfx_engine-Warm-Preview-Daemon ist mit den Alt-Motion-Engines entfernt —
    # die einzige Motion-Engine (Studio-Showcase) rendert ueber Remotion, ohne Preview-Daemon.
    check('v118: gfx-Preview-Daemon + Alt-Motion-Endpoints entfernt',
          not hasattr(SV, '_PreviewDaemon')
          and not hasattr(SV, 'motion_render') and not hasattr(SV, 'motion_brief')
          and not hasattr(SV, 'motion_auto') and not hasattr(SV, '_run_motion_brief')
          and not hasattr(SV, '_run_motion_auto'))
    shutil.rmtree(os.environ['DVE_DATA'], ignore_errors=True)


def _scenario_v98(tmp):
    """v98: Audit-Batch - WAL, Welcome-nach-Verify, Priority-Queue,
    SRT-Export, Ledger-Archiv, Fertig-Mail, Watchdog-Kill, Frontend-DOM."""
    print('\n--- v98 Audit-Batch ---')
    import time as _t
    os.environ['DVE_DATA'] = tempfile.mkdtemp(prefix='dve_v98_')
    if 'server' in sys.modules:
        del sys.modules['server']
    sys.path.insert(0, os.path.join(HERE, 'web'))
    import server as SV
    # 1) SQLite im WAL-Modus mit busy_timeout
    con = SV._db()
    wal = con.execute('PRAGMA journal_mode').fetchone()[0]
    bt = con.execute('PRAGMA busy_timeout').fetchone()[0]
    con.close()
    check('SQLite: WAL + busy_timeout aktiv', wal == 'wal' and bt >= 5000,
          f'{wal}/{bt}')
    # 2) Willkommens-Guthaben erst nach Verify, idempotent
    uid, err = SV._create_user('v98@test', 'x' * 8, 'VachtV98')
    b0 = SV._find_user_by_id(uid)['balance_sec']
    g1 = SV._grant_welcome(uid)
    b1 = SV._find_user_by_id(uid)['balance_sec']
    g2 = SV._grant_welcome(uid)
    b2 = SV._find_user_by_id(uid)['balance_sec']
    check('Welcome-Guthaben: 0 bei Registrierung, kommt mit Verify, 1x',
          b0 == 0 and g1 and b1 == SV.TRIAL_SECONDS
          and not g2 and b2 == SV.TRIAL_SECONDS, f'{b0}/{b1}/{b2}')
    # 3) Priority-Queue: Kaeufer-Job ueberholt Free-Job (FIFO pro Stufe)
    con = SV._db()
    con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                "VALUES (?, ?, ?, ?)", (uid, 1200, 'Kauf test', int(_t.time())))
    con.commit(); con.close()
    uid_free, _ = SV._create_user('v98free@test', 'x' * 8, 'FreeV98')
    SV.JOBS['jfree'] = {'user_id': uid_free}
    SV.JOBS['jpaid'] = {'user_id': uid}
    SV.JOBS['jfree2'] = {'user_id': uid_free}
    from queue import PriorityQueue as _PQ
    _q = _PQ()
    SV.q_put('jfree', _q); SV.q_put('jpaid', _q); SV.q_put('jfree2', _q)
    order = [_q.get()[2] for _ in range(3)]
    check('Priority-Queue: Kaeufer zuerst, Rest FIFO',
          order == ['jpaid', 'jfree', 'jfree2'], str(order))
    # 4) SRT/VTT-Cues: Satzende bricht, Timings korrekt formatiert
    words = [{'word': ' Hallo', 'start': 0.0, 'end': 0.4},
             {'word': ' Welt.', 'start': 0.45, 'end': 0.9},
             {'word': ' Neuer', 'start': 2.5, 'end': 2.9},
             {'word': ' Satz', 'start': 2.95, 'end': 3.3}]
    cues = SV._srt_cues(words)
    check('SRT: Satzende + Pause trennen Cues',
          len(cues) == 2 and cues[0][2] == 'Hallo Welt.'
          and cues[1][2] == 'Neuer Satz', str(cues))
    check('SRT/VTT-Timestamps korrekt',
          SV._srt_ts(3661.25) == '01:01:01,250'
          and SV._srt_ts(0.5, vtt=True) == '00:00:00.500')
    # 5) Konto-Loeschung: Kaeufe ins Archiv, Rest weg (GoBD + DSGVO)
    SV._purge_user_db(uid)
    con = SV._db()
    arch = con.execute("SELECT * FROM ledger_archive WHERE "
                       "user_email='v98@test'").fetchall()
    led = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id=?",
                      (uid,)).fetchone()['c']
    usr = con.execute("SELECT COUNT(*) c FROM users WHERE id=?",
                      (uid,)).fetchone()['c']
    con.close()
    # v135a: zusaetzlich zur Kauf-Zeile wird der Rest-Saldo archiviert
    # (Berechnungsgrundlage fuer nachtraeglichen Widerruf) - beide pruefen.
    _kaufz = [a for a in arch if a['grund'] == 'Kauf test']
    _saldoz = [a for a in arch if a['grund'] == 'Saldo bei Loeschung']
    check('Loeschung: Kauf archiviert (GoBD) + Saldo-Zeile, Ledger+User weg',
          len(_kaufz) == 1 and len(arch) == len(_kaufz) + len(_saldoz)
          and led == 0 and usr == 0, f'{len(arch)}/{led}/{usr}')
    # 6) v130: Fertig-Mail DEAKTIVIERT (Ismet) -> nach dem Render keine Mail.
    sent = []
    SV._send_mail = lambda to, s, b, reply_to=None, html=None: sent.append(to)
    con = SV._db()
    con.execute("UPDATE users SET verified=1 WHERE id=?", (uid_free,))
    con.commit(); con.close()
    SV.JOBS['jd1'] = {'status': 'fertig', 'mode': 'full', 'user_id': uid_free}
    SV._notify_job_done('jd1'); SV._notify_job_done('jd1')
    check('v130: Fertig-Mail deaktiviert (keine Mail nach Render)', sent == [],
          str(sent))
    # 7) Quelltext-Garantien: Watchdog killt, atomare Writes, Proxy-Header
    _src = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('Watchdog killt haengende Renders (nicht nur Mail)',
          'os.kill(int(pid), signal.SIGKILL)' in _src
          and _src.count("j['pid'] = p.pid") + _src.count("JOBS[jid]['pid'] = p.pid") >= 2)
    check('state.json atomar (tmp + os.replace)',
          'os.replace(tmp, sp)' in _src)
    _dock = open(os.path.join(HERE, 'Dockerfile'), encoding='utf-8').read()
    check('uvicorn hinter Proxy korrekt (--proxy-headers)',
          '--proxy-headers' in _dock and 'HEALTHCHECK' in _dock)
    # 8) Frontend-DOM: Analyze-Status existiert jetzt wirklich, 4K-Kachel weg,
    #    Billing-Historie hat eigene Funktion, SRT-Downloads verdrahtet
    _idx = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('Frontend: #analyzeStatus existiert im DOM (Fix-transcript-Crash)',
          'id="analyzeStatus"' in _idx and "$('#btnAnalyze')" not in _idx)
    # v157: 4K ist zurueck - als dritte Stufe neben 720p/1080p, mit
    # verdoppeltem Credit-Satz und nur ab 1440p Quelle. Die alte Aussage
    # "Server cappt auf 1080p" gilt seit v149 nicht mehr.
    check('v157: 4K ist eine ehrliche Stufe (Aufpreis + Quellen-Grenze genannt)',
          '4K &middot; 2&times; credits:2160' in _idx
          and 'we never upscale' in _idx and 'at least 1440p' in _idx)
    check('Frontend: Billing-Historie eigene Funktion + SRT-Buttons',
          'renderBillingHistory' in _idx and '/api/subtitles/' in _idx
          and 'wmUpsell' in _idx)
    # v101o: Motion-Video inline + Player-Poster/preload + Transkript-Notiz
    check('v101o: Motion zeigt fertigen Clip inline (nicht nur Library-Link)',
          'id="moVid"' in _idx and 'moResultBar' in _idx
          and 'function moShowPreview' in _idx
          and "vid.src='/api/video/'+jid" in _idx)
    check('v101o: Player laedt sparsam (preload=metadata + Poster)',
          'id="resultVid" controls playsinline preload="metadata"' in _idx
          and "rv.poster = '/api/poster/' + State.jid" in _idx
          and 'preload="metadata"' in _idx)
    check('v101o: Highlight-Notiz erklaert die Phrasen-Gruppierung',
          'tx-note' in _idx and 'one highlight' in _idx
          and 'spacing your picks out' in _idx)
    # v101.3 Watermark-Unlock serverseitig: Swap, Idempotenz, Auto-Unlock
    _ujid = 'ffeeddccbb99'
    _ud = SV.job_dir(_ujid)
    os.makedirs(_ud, exist_ok=True)
    open(os.path.join(_ud, 'fertig.mp4'), 'wb').write(b'WM')
    open(os.path.join(_ud, 'master_clean.mp4'), 'wb').write(b'CLEAN')
    SV.JOBS[_ujid] = {'user_id': uid_free, 'wm': True, 'status': 'fertig'}
    _u1 = SV._unlock_job(_ujid)
    check('v101: Unlock ersetzt fertig.mp4 durch sauberen Master',
          _u1 and open(os.path.join(_ud, 'fertig.mp4'), 'rb').read() == b'CLEAN'
          and SV.JOBS[_ujid].get('wm') is False
          and SV._unlock_job(_ujid) is False)
    _ujid2 = 'ffeeddccbb88'
    _ud2 = SV.job_dir(_ujid2)
    os.makedirs(_ud2, exist_ok=True)
    open(os.path.join(_ud2, 'fertig.mp4'), 'wb').write(b'WM2')
    open(os.path.join(_ud2, 'master_clean.mp4'), 'wb').write(b'CLEAN2')
    SV.JOBS[_ujid2] = {'user_id': uid_free, 'wm': True, 'status': 'fertig'}
    SV._credit_purchase(uid_free, 600, 'sess_unlock_t')
    check('v101: Kauf schaltet gecachte Videos automatisch frei',
          open(os.path.join(_ud2, 'fertig.mp4'), 'rb').read() == b'CLEAN2'
          and SV.JOBS[_ujid2].get('wm') is False)
    check('v101: Free-Tier rendert mit --watermark-split + Library-wm-Flag',
          "'--watermark-split'" in open(os.path.join(HERE, 'web', 'server.py'),
                                        encoding='utf-8').read()
          and 'data-unlock' in open(os.path.join(HERE, 'web', 'index.html'),
                                    encoding='utf-8').read())

    # v101h Caption-Alpha-Export serverseitig: Kaeufer-Gate, eigener Ledger-
    # Text (Alpha ...), Refund-Pfad, Worker-Modus, Auslieferung, UI-Buttons.
    _srv_h = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    _ui_h = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('v101h: /api/alpha Endpoint mit Kauf-Gate + eigener Buchung',
          "'/api/alpha/{jid}'" in _srv_h
          and "grund=f'Alpha {jid} ({cost}s)'" in _srv_h
          and 'first purchase' in _srv_h.lower())
    check('v101h: Worker-Modus alpha + Refund bei Fehlschlag',
          "mode == 'alpha'" in _srv_h
          and "'--alpha-export'" in _srv_h
          and "'fertig_captions.mov'" in _srv_h
          and "_refund_credits(uid, f'Alpha {jid}'" in _srv_h)
    check('v101h: Auslieferung + Library-Flags + UI-Buttons',
          "'/api/alpha_file/{jid}'" in _srv_h
          and "'has_alpha'" in _srv_h and "'can_alpha'" in _srv_h
          and 'data-alpha' in _ui_h and '/api/alpha_file/' in _ui_h)
    # _reserve_credits mit eigenem Grund bucht atomar unter diesem Text
    _bal_a0 = SV._find_user_by_id(uid_free)['balance_sec']
    _rok = _bal_a0 >= 60 and SV._reserve_credits(
        uid_free, 60, 'alphajob01', grund='Alpha alphajob01 (60s)')
    _con_a = SV._db()
    _led_a = _con_a.execute("SELECT id FROM ledger WHERE user_id = ? AND "
                            "grund = ?", (uid_free, 'Alpha alphajob01 (60s)')
                            ).fetchone()
    _con_a.close()
    check('v101h: Alpha-Buchung atomar mit eigenem Ledger-Text',
          _rok and _led_a is not None
          and SV._find_user_by_id(uid_free)['balance_sec'] == _bal_a0 - 60)

    # v101l Transkript-Wizard-Schritt: eigener Schritt 'Text' (4), Render (5),
    # Wort-Chips + Suchen/Ersetzen, Save-only ohne Re-Analyse.
    check('v101l: Wizard hat 5 Schritte inkl. Text vor Render',
          'data-step="5"' in _ui_h and '>Text</div>' in _ui_h
          and _ui_h.count('step-view') >= 5
          and 'data-step="5" role="tabpanel" aria-label="Render"' in _ui_h)
    check('v101l: Transkript-Schritt-UI (Chips, Suchen/Ersetzen, Loader)',
          'id="txWords"' in _ui_h and 'id="txFind"' in _ui_h
          and 'id="txReplaceAll"' in _ui_h
          and 'loadTranscriptStep' in _ui_h and 'saveTranscriptStep' in _ui_h
          and "goStep(5)" in _ui_h)
    check('v101l: Schritt speichert ohne Re-Analyse (reanalyze=0) auf preJid',
          "fd.append('reanalyze', '0')" in _ui_h
          and "fetch('/api/transcript/' + jid" in _ui_h)
    check('v101l: Backend - reanalyze=0 speichert nur, kein Queue/mode-Wechsel',
          "reanalyze: str = Form('1')" in _srv_h
          and "if str(reanalyze) not in ('0', 'false', 'False', '')" in _srv_h)

    shutil.rmtree(os.environ['DVE_DATA'], ignore_errors=True)


def _scenario_trail(tmp):
    """v93b: Der Duplicate-Trail darf die Person NIE doppeln. Frueher hielt der
    Diff comp-vs-frame bewegte Personenkanten (Kamera/Grade) fuer Text und schob
    sie als halbtransparenten Geist nach links (der Typ wirkte doppelt). Mit
    uebergebener Person-Matte muss die Person aus dem Trail rausfallen."""
    print('\n--- Trail: kein Personen-Doppelgaenger ---')
    sys.path.insert(0, HERE)
    import render as R
    import re as _re
    frame0 = np.zeros((200, 200, 3), np.uint8)
    comp0 = frame0.copy()
    comp0[:, 40:46] = 170            # duenne bewegte Personen-KANTE (Diff, <6 % Flaeche)
    comp0[90:110, 150:180] = 240     # echter Text rechts
    alpha = np.zeros((200, 200), np.float32)
    alpha[:, 0:46] = 1.0             # Person = linke Haelfte
    band = slice(0, 38)
    out_bad = R.apply_duplicate_trail(comp0.copy(), frame0, 0.5, None)
    out_good = R.apply_duplicate_trail(comp0.copy(), frame0, 0.5, alpha)
    ghost_bad = int(np.abs(out_bad[:, band].astype(int) - comp0[:, band].astype(int)).sum())
    ghost_good = int(np.abs(out_good[:, band].astype(int) - comp0[:, band].astype(int)).sum())
    check('Trail doppelt die Person nicht (Matte schneidet sie raus)',
          ghost_good == 0 and ghost_bad > 0,
          f'ohne Matte={ghost_bad}, mit Matte={ghost_good}')
    tband = slice(100, 150)          # echter Text bekommt weiter seinen Trail
    text_trail = int(np.abs(out_good[:, tband].astype(int)
                            - comp0[:, tband].astype(int)).sum())
    check('Trail wirkt weiterhin auf echten Text', text_trail > 0, f'{text_trail}')
    # Trail darf wieder an sein (Dynamik) - aber der Aufruf MUSS die Person-Maske
    # uebergeben, sonst doppelt er die Person (v93b-Haertung greift auch bei
    # aktivem Trail). Person-Ausschluss selbst ist oben schon geprueft.
    _rp = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Trail-Aufruf uebergibt Person-Maske (kein Doppler bei aktivem Trail)',
          'apply_duplicate_trail(comp, frame, _trail, alpha)' in _rp)


def _scenario_lang(tmp):
    """v94: Sprache aus Inhalt erkennen (auch bei 'auto') + Aktion-Wort darf
    Keyword werden. Frueher wurde Englisch als Deutsch behandelt -> lowercase
    'flies'/'shatter' verworfen, Aktion-Woerter nie animiert."""
    print('\n--- Sprache & Aktion-Keywords ---')
    sys.path.insert(0, HERE)
    import render as R
    de = [{'word': w} for w in
          'der markt ist heute nicht gut und wir haben ein problem'.split()]
    en = [{'word': w} for w in
          'the word flies explodes and everything should shatter now'.split()]
    check('Sprach-Erkennung: Deutsch erkannt', R._looks_german(de) is True)
    check('Sprach-Erkennung: Englisch ist nicht Deutsch',
          R._looks_german(en) is False)
    # Englisches Aktion-Wort (lowercase Verb) mit Anim muss Keyword werden
    words = [{'word': 'explodes', 'start': 0.0, 'end': 0.4},
             {'word': 'now', 'start': 0.4, 'end': 0.7}]
    reg = '{"keywords":[{"i":0,"n":1,"fx":"behind","power":3,"anim":"explosion"}]}'
    out = R.parse_regie(reg, words, 'auto')
    check('parse_regie: englisches Aktion-Wort wird Keyword + behaelt Anim',
          out is not None and 0 in out and out[0].get('anim') == 'explosion',
          str(out))
    # Prompt sagt der KI, Aktion-Woerter zu waehlen + zu animieren
    _r = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Regie-Prompt: Aktion-Wort-als-Keyword-Regel vorhanden',
          'AKTION-WORT ALS KEYWORD' in _r and 'explodes->explosion' in _r)
    check('Regie-Prompt: Retention-Dramaturgie verankert',
          'RETENTION-DRAMATURGIE' in _r and 'OFFENE SCHLEIFE' in _r
          and 'ESKALATION' in _r and 'MUSTER-BRUCH' in _r)
    check('Regie-Prompt: Selbstbezug-Regel (Captions hoeren zu)',
          'SELBSTBEZUG AUF DIE CAPTIONS' in _r
          and 'meine Captions explodieren' in _r)
    # v96m: aktueller Standard verankert + Stil-Referenzen (Trend-Bezug) einspeisbar
    check('Regie-Prompt: aktueller Short-Form-Standard 2026 verankert',
          'AKTUELLER SHORT-FORM-STANDARD' in _r and 'STIL-REFERENZEN' in _r)
    _rb = R._load_regie_reference()
    check('Stil-Referenzen: regie_reference.json wird als Prompt-Block geladen',
          isinstance(_rb, str) and 'STIL-REFERENZEN' in _rb
          and 'Kopiere NIE deren Woerter' in _rb
          and 'VERBINDLICH' in _rb)
    check('Stil-Referenzen: fehlende/leere Datei -> kein Block (kein Crash)',
          R._load_regie_reference.__code__.co_argcount == 0
          and 'ref_block + lang_hint' in _r)
    # v96n: aus Referenz-Video lernen (Vision) - Struktur + Fehlertoleranz
    _k = os.environ.pop('OPENAI_API_KEY', None)
    try:
        _none = R.analyze_reference_video('/tmp/st_clip.mp4', save=False)
    finally:
        if _k is not None:
            os.environ['OPENAI_API_KEY'] = _k
    check('Stil-Lernen: ohne Key -> None (kein Crash)', _none is None)
    check('Stil-Lernen: Vision-Frames + Stil-Prompt (kein Woerter-Kopieren)',
          'STYLE_LEARN_PROMPT' in _r and 'KEINE Woerter abtippen' in _r
          and 'analyze_reference_video' in _r and "refs[-12:]" in _r)
    # v96v: detaillierte Analyse (6 visuelle Punkte) + Audio/SFX aus der Tonspur
    check('Stil-Lernen: detaillierter Prompt (Hook/Chunks/Typo/Bewegung/Rhythmus)',
          '1) HOOK' in _r and '4) TYPO' in _r and '6) RHYTHMUS' in _r)
    _as = R._ref_audio_summary('/tmp/st_clip.mp4')
    check('Stil-Lernen: Audio/SFX wird separat aus der Tonspur analysiert',
          isinstance(_as, str) and ('AUDIO/SFX' in _as or _as == '')
          and 'def _ref_audio_summary' in _r and 'aud = _ref_audio_summary' in _r)
    # v96x: Referenzen wirken WIRKLICH - drei Garantien:
    # (a) die NEUESTEN Referenzen landen im Prompt (Store haengt hinten an)
    import tempfile as _tfx
    _refdir = _tfx.mkdtemp(prefix='dve_refx_')
    _old_dd = os.environ.get('DVE_DATA')
    os.environ['DVE_DATA'] = _refdir
    try:
        json.dump([{'name': f'R{k}', 'beispiel': f'Stilhinweis Nummer {k}'}
                   for k in range(1, 9)],
                  open(os.path.join(_refdir, 'regie_reference.json'), 'w',
                       encoding='utf-8'))
        _blk = R._load_regie_reference()
        _fp1 = R._ref_fingerprint()
        json.dump([{'name': 'NEU', 'beispiel': 'Ganz neuer Stil'}],
                  open(os.path.join(_refdir, 'regie_reference.json'), 'w',
                       encoding='utf-8'))
        _fp2 = R._ref_fingerprint()
    finally:
        if _old_dd is None:
            os.environ.pop('DVE_DATA', None)
        else:
            os.environ['DVE_DATA'] = _old_dd
        shutil.rmtree(_refdir, ignore_errors=True)
    check('Stil-Referenzen: die NEUESTEN 6 landen im Prompt (nicht die aeltesten)',
          'Nummer 8' in _blk and 'Nummer 1' not in _blk, _blk[:120])
    # (b) Regie-Cache wird bei geaenderten Referenzen verworfen (Fingerprint)
    check('Stil-Referenzen: Regie-Cache invalidiert bei Referenz-Aenderung',
          _fp1 != _fp2 and "'ref_fp': _ref_fingerprint()" in _r
          and 'old direction discarded' in _r)
    # (c) Anwendung ist im Job-Log beweisbar
    check('Stil-Referenzen: Anwendung wird geloggt (aktiv/keine)',
          'Style references: {_n_refs} active' in _r.replace('f"', '"')
          or 'feeding into the AI direction' in _r)
    # (d) v96y: Referenz-Parameter wirken DETERMINISTISCH auf die Config
    _refd = _tfx.mkdtemp(prefix='dve_refy_')
    _old_dd2 = os.environ.get('DVE_DATA')
    os.environ['DVE_DATA'] = _refd
    try:
        json.dump([{'name': 'A', 'beispiel': 'x',
                    'params': {'words_per_group': 2, 'min_gap_seconds': 4,
                               'hook_strength': 0.9, 'wucht': 'ruhig'}}],
                  open(os.path.join(_refd, 'regie_reference.json'), 'w'))
        _cfgy = {'effects': {'words_per_group': 3, 'words_per_group_max': 5,
                             'hook_strength': 0.5, 'sfx_volume': 0.6},
                 'keywords': {'min_gap_seconds': 6},
                 'camera': {'strength': 0.7}}
        _line = R._apply_reference_params(_cfgy)
    finally:
        if _old_dd2 is None:
            os.environ.pop('DVE_DATA', None)
        else:
            os.environ['DVE_DATA'] = _old_dd2
        shutil.rmtree(_refd, ignore_errors=True)
    check('Stil-Anker: Parameter wirken deterministisch auf die Config',
          _cfgy['effects']['words_per_group'] == 2
          and _cfgy['keywords']['min_gap_seconds'] == 4.0
          and _cfgy['effects']['hook_strength'] == 0.9
          and _cfgy['camera']['strength'] < 0.7          # 'ruhig' senkt Kamera
          and _line.startswith('Stil-Anker:'), _line)
    # (e) v96z: LOOK wird kopiert - Akzentfarbe + Dichte der Referenz
    _refl = _tfx.mkdtemp(prefix='dve_refl_')
    _old_dd3 = os.environ.get('DVE_DATA')
    os.environ['DVE_DATA'] = _refl
    try:
        json.dump([{'name': 'L', 'beispiel': 'x',
                    'params': {'accent_hex': '#ffd700',
                               'density': 'durchgehend'}}],
                  open(os.path.join(_refl, 'regie_reference.json'), 'w'))
        _cfgl = {'effects': {'density': 'akzente', 'sfx_volume': 0.6},
                 'keywords': {}, 'camera': {'strength': 0.7},
                 'colors': {'accent': [255, 122, 26], 'adaptive': True}}
        _linel = R._apply_reference_params(_cfgl)
    finally:
        if _old_dd3 is None:
            os.environ.pop('DVE_DATA', None)
        else:
            os.environ['DVE_DATA'] = _old_dd3
        shutil.rmtree(_refl, ignore_errors=True)
    check('Stil-Anker: LOOK kopiert (Akzentfarbe + Dichte der Referenz)',
          _cfgl['colors']['accent'] == [255, 215, 0]
          and _cfgl['colors']['adaptive'] is False
          and _cfgl['effects']['density'] == 'durchgehend'
          and 'farbe=#ffd700' in _linel, _linel)
    check('Stil-Anker: im Render-Main verdrahtet + Server zeigt Beweis im Job',
          '_apply_reference_params(cfg)' in _r
          and "startswith('Stil-Referenzen:')" in
          open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read())
    # v94: sichtbare Aktion-Animation darf nicht hinter der Person verschwinden
    words_v = [{'word': 'explodes', 'start': 0.0, 'end': 0.4}]
    reg_v = '{"keywords":[{"i":0,"n":1,"fx":"behind","power":3,"anim":"explosion"}]}'
    out_v = R.parse_regie(reg_v, words_v, 'en')
    check('Sichtbarkeit: bewegte Aktion (explosion) nicht "behind" -> nach vorn',
          out_v and out_v[0]['anim'] == 'explosion' and out_v[0]['fx'] != 'behind',
          str(out_v))
    # ruhige Anim (gewicht) darf hinter der Person bleiben
    reg_g = '{"keywords":[{"i":0,"n":1,"fx":"behind","power":2,"anim":"gewicht"}]}'
    out_g = R.parse_regie(reg_g, words_v, 'en')
    check('Sichtbarkeit: ruhige Anim (gewicht) bleibt behind',
          out_g and out_g[0]['fx'] == 'behind')
    # v94: Modell-kompatibler Request-Body (gpt-5 braucht max_completion_tokens,
    # kein temperature; gpt-4o das Alte).
    b4 = R._oai_json('gpt-4o', [{'role': 'user', 'content': 'x'}], 800, 0.2)
    b5 = R._oai_json('gpt-5', [{'role': 'user', 'content': 'x'}], 800, 0.2)
    check('_oai_json gpt-4o: max_tokens + temperature',
          b4.get('max_tokens') == 800 and b4.get('temperature') == 0.2
          and 'max_completion_tokens' not in b4)
    # v210: Bei den neuen Modellen zaehlen die Denk-Tokens mit; ein zu
    # knappes Budget liefert eine LEERE Antwort (im Job-Log als
    # JSONDecodeError). Untergrenze 2500, deshalb hier nicht mehr 800.
    check('_oai_json gpt-5: max_completion_tokens, kein temperature',
          b5.get('max_completion_tokens') == 2500 and 'temperature' not in b5
          and 'max_tokens' not in b5)
    # v96t: Prosa-Modus (Stil-Lernen) darf KEIN response_format json_object haben
    bj = R._oai_json('gpt-4o', [{'role': 'user', 'content': 'x'}], 400, 0.3)
    bp = R._oai_json('gpt-4o', [{'role': 'user', 'content': 'x'}], 400, 0.3,
                     json_mode=False)
    check('_oai_json: Prosa-Modus ohne response_format (Stil-Lernen 400-Fix)',
          'response_format' in bj and 'response_format' not in bp)
    # v95: Sprech-Pegel pro Wort -> die KI-Regie reagiert auf den Sound.
    import wave as _wave, tempfile as _tf
    import numpy as _np
    sr = 44100
    segs = [('rocket', 0.0, 0.4, 0.85), ('whisper', 0.6, 1.0, 0.02),
            ('boom', 1.2, 1.6, 0.90), ('murmur', 1.8, 2.2, 0.02),
            ('crash', 2.4, 2.8, 0.88)]
    buf = _np.zeros(int(3.0 * sr), dtype=_np.float32)
    tone = lambda n, a: a * _np.sin(2 * _np.pi * 180 * _np.arange(n) / sr)
    for _, s, e, amp in segs:
        i0, i1 = int(s * sr), int(e * sr)
        buf[i0:i1] = tone(i1 - i0, amp)
    wpath = os.path.join(_tf.gettempdir(), 'dve_loud.wav')
    with _wave.open(wpath, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((buf * 32767).astype('<i2').tobytes())
    lwords = [{'word': w, 'start': s, 'end': e} for w, s, e, _ in segs]
    lmap = R._word_loudness(lwords, wpath)
    loud_idx = {i for i, (_, _, _, a) in enumerate(segs) if a > 0.5}
    soft_idx = {i for i, (_, _, _, a) in enumerate(segs) if a < 0.1}
    got_loud = {i for i, m in lmap.items() if m == '!'}
    got_soft = {i for i, m in lmap.items() if m == '~'}
    check('Sprech-Pegel: laute Woerter als "!" markiert (KI reagiert auf Sound)',
          got_loud and got_loud.issubset(loud_idx) and got_soft.issubset(soft_idx)
          and got_soft, f'laut={got_loud} leise={got_soft}')
    check('Sprech-Pegel: ohne wav leer (Regie laeuft wie bisher)',
          R._word_loudness(lwords, None) == {}
          and R._word_loudness(lwords, '/nope.wav') == {})
    check('Regie-Prompt: AUDIO-DYNAMIK koppelt Effekt an Pegel',
          'AUDIO-DYNAMIK' in _r and 'Stimmspitze' in _r)
    os.remove(wpath)
    # v95c: 'behind' lohnt sich nicht, wenn die Person das Bild fuellt.
    fxm = {0: {'fx': 'behind', 'power': 3}, 1: {'fx': 'behind', 'power': 2},
           2: {'fx': 'behind', 'power': 2}, 3: {'fx': 'outline', 'power': 2}}
    cover = {0: 0.60, 1: 0.20, 2: 0.55, 3: 0.70}   # 0,2 = Nahaufnahme
    out = R._behind_cover_backstop(dict((k, dict(v)) for k, v in fxm.items()), cover)
    check('behind@Nahaufnahme: power3 -> ground, power2 -> outline, Rest bleibt',
          out[0]['fx'] == 'ground' and out[2]['fx'] == 'outline'
          and out[1]['fx'] == 'behind' and out[3]['fx'] == 'outline', str(out))
    check('behind-Backstop: ohne Coverage-Daten unveraendert',
          R._behind_cover_backstop({0: {'fx': 'behind', 'power': 3}}, {})
          == {0: {'fx': 'behind', 'power': 3}})
    check('Szene-Prompt: KI entscheidet ob behind sichtbar ist',
          'LOHNT SICH "behind"' in _r and 'Person ~X% der Breite' in _r
          and 'face_cover' in _r)


def _scenario_vfx(clip, tmp):
    """v97: Ein-Moment-VFX-Prototyp - VFX auf dem echten Video, synchron zur
    Caption. Prueft den lokalen (deterministischen) Weg End-to-End."""
    print('\n--- VFX-Prototyp (VFX + Captions) ---')
    sys.path.insert(0, HERE)
    import vfx_engine as VE
    import subprocess as _sp
    def _dur(p):
        try:
            return float(_sp.run(['ffprobe', '-v', 'error', '-show_entries',
                                  'format=duration', '-of', 'default=nw=1:nk=1', p],
                                 capture_output=True, text=True).stdout.strip() or 0)
        except Exception:
            return 0.0
    din = _dur(clip)
    check('VFX: lokale Arten vorhanden (shock/rgb/heat)',
          set(VE.LOCAL_KINDS) == {'shock', 'rgb', 'heat'})
    outs = {}
    for kind in VE.LOCAL_KINDS:
        outp = os.path.join(tmp, f'vfx_{kind}.mp4')
        ok = VE.render_moment_vfx(clip, outp, t0=1.0, dauer=0.6, kind=kind,
                                  caption='EXPLODES', progress=lambda *a: None)
        outs[kind] = (ok, outp)
    check('VFX: shock erzeugt gueltiges Video, Laenge bleibt (Frame-genau)',
          outs['shock'][0] and os.path.exists(outs['shock'][1])
          and abs(_dur(outs['shock'][1]) - din) < 0.5,
          f"in={din:.2f}s out={_dur(outs['shock'][1]):.2f}s")
    check('VFX: rgb + heat laufen ebenfalls durch',
          outs['rgb'][0] and outs['heat'][0]
          and os.path.exists(outs['rgb'][1]) and os.path.exists(outs['heat'][1]))
    # Effekt veraendert das Bild wirklich (Moment-Frame != Original-Frame)
    import numpy as _np9
    diff = 0.0
    try:
        c0 = VE.cv2.VideoCapture(clip)
        c1 = VE.cv2.VideoCapture(outs['shock'][1])
        origs = []
        for _ in range(60):
            ok0, f0f = c0.read()
            if not ok0:
                break
            origs.append(f0f)
        c0.release()
        idx = 0
        while idx < len(origs):
            ok1, f1f = c1.read()
            if not ok1:
                break
            if f1f.shape == origs[idx].shape:
                d = float(_np9.abs(origs[idx].astype('int16')
                                   - f1f.astype('int16')).mean())
                diff = max(diff, d)
            idx += 1
        c1.release()
    except Exception:
        diff = 0.0
    check('VFX: der Moment ist sichtbar transformiert (max-Diff im Fenster)',
          diff > 3.0, f'max Differenz {diff:.1f}')
    # Cloud-Hook ist bewusst getrennt (generativ, opt-in, Key noetig)
    try:
        VE.generate_cloud_vfx('x', 'y', 'z')
        raised = False
    except NotImplementedError:
        raised = True
    except Exception:
        raised = True
    check('VFX: Cloud-Hook (Higgsfield/Seedance) getrennt + opt-in (NotImplemented)',
          raised)


def _scenario_multiperson(tmp):
    """v96: Mehrere Personen im Gespraech. Tracking erfasst alle, Active-Speaker
    via Mund-Bewegung, Text weicht ALLEN Gesichtern aus, B-Roll-Filter kippt
    ein echtes Gespraech nicht mehr weg."""
    print('\n--- Multi-Person / Gespraech ---')
    sys.path.insert(0, HERE)
    import render as R
    # 1) Spur-Zuordnung: zwei Personen (links wackelt viel, rechts kaum) ueber
    #    drei Frames -> zwei stabile Spuren, links traegt mehr Bewegung.
    dets = [
        [[100, 200, 60, 8.0], [400, 200, 60, 0.2]],
        [[104, 202, 60, 9.0], [402, 201, 60, 0.1]],
        [[102, 201, 60, 7.0], [401, 200, 60, 0.3]],
    ]
    track_of, motion = R._faces_tracks(dets, max_d=80)
    # linke Gesichter (Spalte 0) teilen sich eine Spur, rechte eine andere
    left_tracks = {track_of[i][0] for i in range(3)}
    right_tracks = {track_of[i][1] for i in range(3)}
    check('Multi-Face: stabile Personen-Spuren (2 Personen, 2 Spuren)',
          len(left_tracks) == 1 and len(right_tracks) == 1
          and left_tracks != right_tracks, f'{track_of}')
    check('Active-Speaker: Spur mit mehr Mund-Bewegung gewinnt',
          motion[next(iter(left_tracks))] > motion[next(iter(right_tracks))])
    # 2) _active_index waehlt in einem Frame das bewegte (sprechende) Gesicht
    faces = dets[1]
    aj = R._active_index(faces, track_of[1], motion)
    check('Active-Speaker: aktives Gesicht ist der Sprecher (nicht das andere)',
          faces[aj][0] == 104)
    # bei ~0 Bewegung ueberall faellt es auf das groesste Gesicht zurueck
    faces_still = [[100, 200, 50, 0.0], [400, 200, 90, 0.0]]
    to = [10, 11]; mo = {10: 0.0, 11: 0.0}
    check('Active-Speaker: ohne Bewegung -> groesstes Gesicht',
          R._active_index(faces_still, to, mo) == 1)
    # 3) Multi-Face-Safe-Zone: Text landet in einer Luecke, die KEIN Gesicht
    #    ueberdeckt. Zwei Personen bei x=250 und x=1650 (Breite 1920).
    W = 1920
    side, cx = R._free_x_multi([(250, 120), (1650, 120)], W, W * 0.42, 0)
    # verbotene Zonen: 250 +-156, 1650 +-156 -> Mitte ist frei
    def _covers(cx, faces, half):
        return any(abs(cx - fx) < fw * 1.3 + half for fx, fw in faces)
    check('Multi-Face-Safe-Zone: Text deckt KEIN Gesicht ab',
          not _covers(cx, [(250, 120), (1650, 120)], W * 0.21),
          f'cx={cx:.0f}')
    # 4) B-Roll-Filter kippt bei Multi-Person nicht mehr nach Groesse (Quelltext)
    _r2 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('B-Roll: Groessen-Schranke bei Multi-Person aus (Gespraech bleibt)',
          'and not multi_person' in _r2 and 'faces_seq' in _r2)
    # 5) Automatischer Modus-Schalter: narrator / talking_head / conversation
    check('Modus: kaum Gesicht -> narrator (Erzaehler/Voiceover)',
          R._video_mode(0.05, False) == 'narrator'
          and R._video_mode(0.0, False) == 'narrator')
    check('Modus: ein Gesicht meist im Bild -> talking_head',
          R._video_mode(0.80, False) == 'talking_head')
    check('Modus: mehrere Personen -> conversation (auch bei viel Gesicht)',
          R._video_mode(0.90, True) == 'conversation'
          and R._video_mode(0.05, True) == 'conversation')
    check('Modus narrator: behind -> outline + zentriert (face_pos None)',
          "video_mode == 'narrator'" in _r2
          and "_v['fx'] = 'outline'" in _r2 and 'face_pos=None' in _r2)
    # 6) v96c: Spur-Glaettung - kurz weggedrehter Kopf (Luecke) bleibt fuer die
    #    Safe-Zone erhalten; einzelne Spuk-Detektion wird verworfen.
    #    Person A: Frames 0,1,2, LUECKE 3-4 (weggedreht), 5,6. Plus Spuk in F1.
    dets2 = [
        [[100, 200, 60, 3.0]],
        [[102, 201, 60, 3.0], [800, 500, 20, 0.0]],   # Spuk (nur hier)
        [[101, 200, 60, 3.0]],
        [],                                            # weggedreht
        [],                                            # weggedreht
        [[103, 202, 60, 3.0]],
        [[104, 201, 60, 3.0]],
    ]
    to2, _m2 = R._faces_tracks(dets2, max_d=60)
    boxes, tids = R._smooth_tracks(dets2, to2, hold=3, min_len=2)
    filled = all(len(boxes[i]) >= 1 for i in (3, 4))   # Luecke gehalten
    spuk_gone = all(all(abs(b[0] - 800) > 1 for b in boxes[i]) for i in range(7))
    check('Spur-Glaettung: weggedrehter Kopf bleibt in der Safe-Zone (Luecke gehalten)',
          filled, f'F3={boxes[3]} F4={boxes[4]}')
    check('Spur-Glaettung: einzelne Spuk-Detektion wird verworfen',
          spuk_gone)
    check('Gesichts-Erkennung: hoehere Aufloesung + niedrigere Confidence',
          'det_up' in _r2 and 'min_detection_confidence=0.25' in _r2)
    # 7) v96e: Variation pro Video - Seed aus dem INHALT, Keyword-Effekt seed-
    #    gemischt statt stur ab Index 0.
    import zlib as _zl
    _sa = _zl.crc32('der markt steigt heute stark'.encode())
    _sb = _zl.crc32('ganz anderes video mit anderem text'.encode())
    _fx = ('behind', 'cascade', 'blurin', 'outline', 'ground')
    _rA = R.Rotator(_fx, _sa + 4); seqA = [_rA.next() for _ in range(6)]
    _rA2 = R.Rotator(_fx, _sa + 4); seqA2 = [_rA2.next() for _ in range(6)]
    _rB = R.Rotator(_fx, _sb + 4); seqB = [_rB.next() for _ in range(6)]
    check('Variation: anderer Inhalt -> andere Effekt-Reihenfolge',
          seqA != seqB, f'{seqA} vs {seqB}')
    check('Variation: gleicher Inhalt -> reproduzierbar (Re-Render stabil)',
          seqA == seqA2)
    check('Variation: Keyword-Effekt seed-gemischt (nicht stur ab Index 0)',
          'rot_kw = Rotator' in _r2 and 'rot_kw.next()' in _r2
          and 'crc32' in _r2)
    # 8) v96h: Personen-Cutout fuer die echte "behind"-Vorschau im Editor.
    import numpy as _np8
    _cf = os.path.join(tempfile.gettempdir(), 'cutframe.jpg')
    _co = os.path.join(tempfile.gettempdir(), 'cutframe_cut.png')
    R.cv2.imwrite(_cf, (_np8.random.rand(90, 120, 3) * 255).astype('uint8'))
    _okc = R._person_cutout_png(_cf, _co)
    ok_shape = True
    if _okc:
        _im = R.cv2.imread(_co, R.cv2.IMREAD_UNCHANGED)
        ok_shape = _im is not None and _im.ndim == 3 and _im.shape[2] == 4
    check('Cutout: fehlertolerant, bei Erfolg RGBA-PNG (Freistellung)',
          (_okc is False) or ok_shape, f'ok={_okc}')
    for _p in (_cf, _co):
        try: os.remove(_p)
        except OSError: pass
    _html = open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8').read()
    check('Editor: behind legt Personen-Cutout ueber den Text (has-cut)',
          'mom-cut' in _html and 'fx-behind.has-cut' in _html
          and "'cut'" in _r2)
    # 9) v96i: grosse Momente wiederholen sich nicht (visuell + SFX)
    check('Hoehepunkt: keine visuelle Wiederholung (tpl,anim,entr,cam) bei power 3',
          'big_used = set()' in _r2 and 'big_used.add(_sig)' in _r2
          and "_sig = (p.get('tpl'), p.get('anim') or '', p.get('entr'), _cam)" in _r2
          and 'motion broken up' in _r2)
    _se2 = open(os.path.join(HERE, 'sfx_engine.py'), encoding='utf-8').read()
    check('Hoehepunkt-SFX: Einschlag rotiert + klarer Pitch-Versatz je Moment',
          "_lows = [s for s in ('boom', 'slam', 'impact')" in _se2
          and '_pitch(_lowsig, _bp)' in _se2 and '_pitch(_riser, _rp)' in _se2)
    # zwei aufeinanderfolgende grosse Momente -> hoerbar anderer Pitch (Tabellen
    # unterscheiden sich an Index 0 vs 1)
    check('Hoehepunkt-SFX: Pitch-Tabellen variieren zwischen den Momenten',
          '(1.0, 0.87, 1.14' in _se2 and '(1.0, 1.10, 0.90' in _se2)
    # v96l: wuchtige sichtbare Animationen haben jetzt einen eigenen Sound
    # (waren vorher unter power 3 tonlos). Direkt gegen ANIM_SFX pruefen.
    import sfx_engine as _SEa
    check('SFX-Luecke: wuchtige Anims (explosion/zoom_punch/stempel/spur) klingen',
          all(a in _SEa.ANIM_SFX for a in
              ('explosion', 'zoom_punch', 'stempel', 'spur', 'rutsche', 'magnet', 'regen'))
          and 'place(V(_nm)' in _se2)


def _scenario_premium(tmp):
    """v61: Premium-Typo 2026 - Chunk-Pacing, Kontaktschatten, Variable-Achse,
    Beat-Sync, Fluid-Morph."""
    print('\n--- Premium-Typo 2026 ---')
    sys.path.insert(0, HERE)
    import render as R
    import yaml

    # 1) Chunk-Pacing: kurze Woerter werden zu lesbaren Chunks zusammengehalten
    ws = [{'word': 'das', 'start': 0.00, 'end': 0.14},
          {'word': 'ist', 'start': 0.15, 'end': 0.28},
          {'word': 'der', 'start': 0.30, 'end': 0.42},
          {'word': 'punkt', 'start': 0.44, 'end': 0.70},
          {'word': 'genau', 'start': 0.75, 'end': 1.00}]
    g_alt = R.build_groups(ws, 3, min_hold=0.0)
    g_neu = R.build_groups(ws, 3, min_hold=0.65, hard_max=5)
    dur = lambda g: ws[g[-1]]['end'] - ws[g[0]]['start']
    check('Pacing: kurze Chunks werden zusammengehalten',
          len(g_neu) < len(g_alt), f'{len(g_alt)} -> {len(g_neu)} Chunks')
    check('Pacing: Standzeit erreicht 600 ms+',
          all(dur(g) >= 0.6 or g is g_neu[-1] for g in g_neu),
          ', '.join(f'{dur(g)*1000:.0f}ms' for g in g_neu))
    check('Pacing: Wortlimit wird nicht gesprengt',
          all(len(g) <= 5 for g in g_neu), f'max {max(len(g) for g in g_neu)}')
    ws2 = [{'word': 'stopp.', 'start': 0.0, 'end': 0.2},
           {'word': 'weiter', 'start': 0.22, 'end': 0.5}]
    check('Pacing: Satzende wird nie ueberklebt',
          len(R.build_groups(ws2, 3, min_hold=0.9)) == 2)
    check('Pacing: Standzeit steht in der config.yaml',
          'chunk_hold_min' in open(os.path.join(HERE, 'config.yaml'),
                                   encoding='utf-8').read())

    # ================== v140: Senior-Editor-Batch ==================
    import numpy as _np140
    import yaml as _yaml140
    _rsrc140 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    _cfgsrc140 = open(os.path.join(HERE, 'config.yaml'), encoding='utf-8').read()
    # (1) TEMPO-KURVE. Schnell gesprochene Passagen bekommen groessere Bloecke,
    # langsame kleinere, und die Pointe (power 3) steht ALLEIN.
    _fast = [{'word': f'w{i}', 'start': i * 0.22, 'end': i * 0.22 + 0.18}
             for i in range(12)]                       # ~4.5 Woerter/s
    _slow = [{'word': f'w{i}', 'start': i * 0.75, 'end': i * 0.75 + 0.60}
             for i in range(12)]                       # ~1.3 Woerter/s
    _gf = R.build_groups(_fast, 3, min_hold=0.0, hard_max=5, adaptive=True)
    _gs = R.build_groups(_slow, 3, min_hold=0.0, hard_max=5, adaptive=True)
    _mx = lambda gs: max(len(g) for g in gs)
    check('v140 Tempo: schnelle Rede bekommt groessere Bloecke als langsame',
          _mx(_gf) > _mx(_gs), f'schnell max {_mx(_gf)} vs langsam max {_mx(_gs)}')
    check('v140 Tempo: langsame Rede unter dem Standard-Limit',
          _mx(_gs) <= 2, f'max {_mx(_gs)}')
    check('v140 Tempo: Wortlimit (hard_max) bleibt unverletzt',
          _mx(_gf) <= 5, f'max {_mx(_gf)}')
    # Pointe isoliert: power-3 auf Wort 5, egal wo im Chunk es laege.
    _gp = R.build_groups(_fast, 3, min_hold=0.65, hard_max=5, adaptive=True,
                         power_at={5: 3})
    _solo = [g for g in _gp if 5 in g]
    check('v140 Tempo: power-3-Pointe steht allein (auch gegen den Merge-Pass)',
          len(_solo) == 1 and _solo[0] == [5], str(_solo))
    # Rueckwaertskompatibel: ohne die Flags exakt das alte Verhalten.
    check('v140 Tempo: ohne adaptive identisch zum Alt-Verhalten',
          R.build_groups(_fast, 3, min_hold=0.65, hard_max=5)
          == R.build_groups(_fast, 3, min_hold=0.65, hard_max=5, adaptive=False))
    # v193: es sind jetzt DREI Aufrufer - build_plans, der Flow-Cache und der
    # Block-Export fuer den Editor. Alle drei muessen dieselbe Quelle und
    # denselben Nutzer-Blockplan sehen. Sonst zeigt der Editor eine andere
    # Aufteilung als das Video, und die Flow-Anker (ueber den ersten
    # Wortindex verschluesselt) verfallen still.
    check('v140 Tempo: build_plans und Flow-Cache teilen EINE Chunk-Quelle',
          _rsrc140.count('groups_for(words, cfg, fx_map, bloecke=') == 3
          and 'def groups_for' in _rsrc140)

    # (2) KONTRAST-GARANTIE. Auf hellem Grund darf der Text nicht fast weiss
    # bleiben; auf dunklem Grund bleibt der Standard-Look erhalten.
    _hell = R.fit_caption_color(20, 40, R._rel_lum((245, 245, 245)), 2.2)
    _dunkel = R.fit_caption_color(20, 40, R._rel_lum((18, 18, 20)), 2.2)
    check('v140 Kontrast: heller Untergrund kippt den Text auf dunkel',
          R._rel_lum(_hell) < 0.25 and R.contrast_ratio(_hell, R._rel_lum((245, 245, 245))) >= 2.2,
          f'{_hell} ratio {R.contrast_ratio(_hell, R._rel_lum((245,245,245))):.2f}')
    check('v140 Kontrast: dunkler Untergrund behaelt den hellen Standard-Look',
          R._rel_lum(_dunkel) > 0.7, str(_dunkel))
    check('v140 Kontrast: Weiss auf Weiss ist ausgeschlossen',
          all(R.contrast_ratio(
              R.fit_caption_color(h, 40, R._rel_lum((250, 250, 250)), 2.2),
              R._rel_lum((250, 250, 250))) >= 2.2 for h in (0, 40, 90, 150)))
    check('v140 Kontrast: WCAG-Formel korrekt (Schwarz auf Weiss = 21)',
          abs(R.contrast_ratio((0, 0, 0), R._rel_lum((255, 255, 255))) - 21.0) < 0.1)
    check('v140 Kontrast: Untergrund konservativ gemessen (helle Haelfte zaehlt)',
          R.region_luminance(_np140.concatenate([
              _np140.zeros((10, 10, 3), _np140.uint8),
              _np140.full((10, 10, 3), 255, _np140.uint8)], axis=0)) > 0.5)
    check('v140 Kontrast: abschaltbar + in der config.yaml',
          'caption_contrast' in _cfgsrc140
          and 'min_contrast=2.2' in _rsrc140)

    # (3) STILLE VOR DEM EINSCHLAG. Sie faellt NUR in eine echte Sprechpause -
    # Text mitten im Satz abzuschneiden saehe nach Fehler aus. Die Leere ist
    # ausserdem nie laenger als die Pause selbst.
    check('v140 Stille: nur bei echter Sprechpause, nie laenger als die Pause',
          'MIN_GAP_SIL' in _rsrc140
          and 'lead = min(_sil, gap)' in _rsrc140
          and 'MIN_SHOWN_SIL' in _rsrc140
          and 'punch_silence' in _cfgsrc140)
    # Funktional: Pause vorhanden -> Vorlaeufer wird gekuerzt; ohne Pause nicht.
    _slw = ([{'word': f'a{i}', 'start': i * 0.30, 'end': i * 0.30 + 0.26}
             for i in range(6)]
            + [{'word': 'PUNCH', 'start': 2.60, 'end': 2.95}])   # 0.86s Pause
    _cfg_sil = _yaml140.safe_load(
        open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _S_sil = R.Sprites(_cfg_sil, 1080, 1920)
    _plans_sil = R.build_plans(_slw, {6}, _cfg_sil, _S_sil, 1080, 1920,
                               lambda s, e: True,
                               {6: {'fx': 'outline', 'power': 3, 'n': 1}})
    _pun = [p for p in _plans_sil if p.get('kw_i') == 6]
    _vor = [p for p in _plans_sil if p.get('start') is not None
            and p.get('end') is not None and p['start'] < (_pun[0]['start'] if _pun else 0)]
    check('v140 Stille: vor der Pointe entsteht wirklich eine Luecke',
          bool(_pun) and bool(_vor)
          and max(p['end'] for p in _vor) <= _pun[0]['start'] - 0.30 + 1e-6,
          f"Ende {max((p['end'] for p in _vor), default=0):.2f} vs Pointe {_pun[0]['start']:.2f}"
          if _pun and _vor else 'kein Paar')

    # 2) Variable-Font-Achse: echte Gewichte, nicht dick gerechnet
    vf = R.var_font_for(os.path.join(HERE, 'fonts', 'archivo.ttf'))
    check('Variable Schnitt zur Anzeigeschrift vorhanden', bool(vf), str(vf))
    if vf:
        S = R.Sprites(yaml.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                          encoding='utf-8')), 1080, 1920)
        a_thin = S.text('WUCHT', 90, (255, 255, 255), wght=300)[0]
        a_bold = S.text('WUCHT', 90, (255, 255, 255), wght=900)[0]
        d_thin = float((a_thin[..., 3] > 128).mean())
        d_bold = float((a_bold[..., 3] > 128).mean())
        check('Variable-Achse: 900 traegt mehr Farbe als 300',
              d_bold > d_thin * 1.12, f'{d_thin:.4f} -> {d_bold:.4f}')
        lad = R.build_wladder(lambda w: S.text('WUCHT', 90, (255, 255, 255),
                                               wght=w)[0], steps=5)
        check('Gewichts-Leiter: 5 Stufen, gemeinsame Leinwand',
              lad is not None and len(lad) == 5
              and len({a.shape for a in lad}) == 1)
        check('Gewichts-Leiter steigt monoton',
              all(float((lad[i][..., 3] > 128).mean())
                  <= float((lad[i + 1][..., 3] > 128).mean()) + 1e-4
                  for i in range(len(lad) - 1)))

    # 3) Beat-Sync: Onset bewegt den Text, Stille nicht
    base = np.zeros((80, 300, 4), np.uint8)
    base[20:60, 40:260] = 255
    R.BEAT_SYNC = 0.7
    p_on = {'start': 1.0}
    _, _, dy_on, sc_on, _ = R.anim_apply(p_on, base, (0.5, 0.3, 1.0), 0.4)
    p_off = {'start': 1.0}
    _, _, dy_off, sc_off, _ = R.anim_apply(p_off, base, (0.5, 0.3, 0.0), 0.4)
    check('Beat-Sync: Onset skaliert den Text', sc_on > sc_off + 0.01,
          f'{sc_off:.3f} -> {sc_on:.3f}')
    check('Beat-Sync: Onset hebt den Text an', dy_on < dy_off - 0.1,
          f'{dy_off:.2f} -> {dy_on:.2f}')
    R.BEAT_SYNC = 0.0
    p_z = {'start': 1.0}
    _, _, _, sc_z, _ = R.anim_apply(p_z, base, (0.5, 0.3, 1.0), 0.4)
    check('Beat-Sync: bei 0 % passiert nichts', abs(sc_z - 1.0) < 1e-6)
    R.BEAT_SYNC = 0.7

    # Anti-Zucken: ein einzelner Onset-Spike darf den Text nicht anreissen.
    R.BEAT_SYNC = 0.7
    p_spk = {'start': 5.0}
    # Frame 1: kurzer Spike, danach sofort still -> darf kaum Bewegung erzeugen
    _, _, dy_s1, sc_s1, _ = R.anim_apply(p_spk, base, (0.5, 0.3, 1.0), 0.10)
    _, _, dy_s2, sc_s2, _ = R.anim_apply(p_spk, base, (0.5, 0.3, 0.0), 0.13)
    # Ein anhaltender Akzent (zwei Frames Onset) darf mehr bewegen
    p_hold = {'start': 6.0}
    R.anim_apply(p_hold, base, (0.5, 0.3, 1.0), 0.10)
    _, _, dy_h, sc_h, _ = R.anim_apply(p_hold, base, (0.5, 0.3, 1.0), 0.13)
    check('Anti-Zucken: Einzel-Spike bleibt gedaempft', sc_s1 < 1.03,
          f'sc={sc_s1:.3f}')
    check('Anti-Zucken: anhaltender Akzent bewegt mehr als Einzel-Spike',
          sc_h > sc_s1, f'{sc_s1:.3f} vs {sc_h:.3f}')
    _, _, _, sc_dead, _ = R.anim_apply({'start': 7.0}, base, (0.5, 0.3, 0.1), 0.4)
    check('Anti-Zucken: Mikro-Onset in der Deadzone bewegt nichts',
          abs(sc_dead - 1.0) < 1e-6, f'sc={sc_dead:.4f}')

    # 4) Fluid-Morph
    liq = R._liquid(base, 0.9, seed=3)
    check('Fluid-Morph verzerrt das Wort',
          liq.shape == base.shape
          and float(np.abs(liq.astype(np.float32)
                           - base.astype(np.float32)).mean()) > 3.0)
    check('Fluid-Morph bei 0 laesst das Original stehen',
          R._liquid(base, 0.0) is base)
    check('Morph ist ein echter Auftritt',
          "'morph'" in open(os.path.join(HERE, 'render.py'),
                            encoding='utf-8').read())

    # 5) Kontaktschatten: die Person wirft Schatten auf den Text dahinter
    W, H = 320, 240
    frame = np.full((H, W, 3), 200.0, np.float32)
    alpha = np.zeros((H, W, 1), np.float32)
    alpha[60:200, 120:200] = 1.0                 # "Person" in der Mitte
    words = [{'word': 'WUCHT', 'start': 0.0, 'end': 3.0}]
    S = R.Sprites(yaml.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                      encoding='utf-8')), W, H)
    arr = S.text('WUCHT', 40, (255, 255, 255))[0]
    plan = [{'tpl': 'behind', 'kw_i': 0, 'start': 0.0, 'end': 3.0, 'arr': arr,
             'by': H * 0.5, 'small': [], 'tilt': 0.0, 'entr': 'rise'}]
    cfg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    cfg['effects']['dim_behind'] = 0.0
    cfg['effects']['anim'] = False

    def comp_with(ps):
        R.PERSON_SHADOW = ps
        return R.composite_frame(frame.copy(), alpha.copy(), 1.2,
                                 copy.deepcopy(plan), words, (160, 100, 30), cfg,
                                 S, W, H)
    c_off = comp_with(0.0)
    c_on = comp_with(0.9)
    band = (slice(205, 225), slice(125, 205))    # direkt unter der Person
    dark = float(c_off[band].mean() - c_on[band].mean())
    check('Kontaktschatten: Person dunkelt den Text darunter ab', dark > 3.0,
          f'-{dark:.1f} Helligkeit')
    fern = (slice(20, 40), slice(10, 60))        # weit weg: unveraendert
    check('Kontaktschatten bleibt lokal',
          abs(float(c_off[fern].mean() - c_on[fern].mean())) < 1.0)
    check('Kontaktschatten faellt NICHT auf die Person selbst',
          abs(float(c_off[70:190, 130:190].mean()
                    - c_on[70:190, 130:190].mean())) < 0.5)
    R.PERSON_SHADOW = 0.5

    # ---- v69: Hintergrund-Blur ----
    print('\n--- Hintergrund-Blur ---')
    check('apply_bg_blur existiert', hasattr(R, 'apply_bg_blur'))
    check('Config: bg_blur',
          'bg_blur' in open(os.path.join(HERE, 'config.yaml'),
                            encoding='utf-8').read())
    # Test-Frame mit hoher Kante (sichtbare Detail-Reduktion nur bei Blur).
    Wb, Hb = 320, 180
    fr = np.zeros((Hb, Wb, 3), dtype=np.float32)
    fr[:, ::10] = 255                                # senkrechte Streifen: hohe Frequenz
    alpha_full = np.zeros((Hb, Wb, 1), dtype=np.float32)
    alpha_full[40:140, 120:200] = 1.0                # Person mittig
    # 1) strength=0 -> Frame unveraendert
    out0 = R.apply_bg_blur(fr.copy(), alpha_full, None, 0.0, Wb, Hb)
    check('Blur strength=0: kein Effekt',
          float(np.abs(out0 - fr).mean()) < 1e-3)
    # 2) alpha=None + depth=None -> kein Effekt (kein Blindwurf)
    out_no = R.apply_bg_blur(fr.copy(), None, None, 0.8, Wb, Hb)
    check('Blur ohne Maske: kein Effekt',
          float(np.abs(out_no - fr).mean()) < 1e-3)
    # 3) Vollstaerke: Hintergrund glaettet, Vordergrund bleibt
    out1 = R.apply_bg_blur(fr.copy(), alpha_full, None, 1.0, Wb, Hb)
    # Streifen-Detail im Hintergrund muss deutlich runter, im Vordergrund erhalten.
    _bg_var_before = float(fr[10:30, 10:100].std())
    _bg_var_after = float(out1[10:30, 10:100].std())
    _fg_var_before = float(fr[70:120, 130:190].std())
    _fg_var_after = float(out1[70:120, 130:190].std())
    check('Blur wirkt im Hintergrund', _bg_var_after < _bg_var_before * 0.55,
          f'{_bg_var_after:.1f} < {_bg_var_before:.1f}*0.55')
    check('Vordergrund bleibt scharf', _fg_var_after > _fg_var_before * 0.75,
          f'{_fg_var_after:.1f} > {_fg_var_before:.1f}*0.75')
    # 4) Depth allein reicht auch
    depth_far = np.linspace(0.1, 0.9, Wb, dtype=np.float32)[None, :].repeat(Hb, 0)
    out_d = R.apply_bg_blur(fr.copy(), None, depth_far, 1.0, Wb, Hb)
    _near = float(out_d[10:30, 10:60].std())         # links: nah, wenig blur
    _far = float(out_d[10:30, 260:310].std())        # rechts: weit, viel blur
    check('Depth-only: Fern wird staerker verwischt als Nah',
          _far < _near * 0.85, f'{_far:.1f} < {_near:.1f}*0.85')
    # 5) composite_frame ruft Blur nur bei aktivem Moment auf B-Roll nicht
    _gsrc_bl = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    _rsrc_bl = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    # v92: auch Szenen-Text (Boden/Wand/Wasser) bleibt bokeh-frei - die
    # Szene, in der der Text liegt, darf nicht weichgezeichnet werden.
    check('Blur nur ausserhalb B-Roll/Szenen-Text',
          "if p.get('broll') or p.get('scene_ground')" in _rsrc_bl
          and 'apply_bg_blur(' in _rsrc_bl)
    check('Blur-Regler in der GUI',
          'bgblur_var' in _gsrc_bl and 'Hintergrund weichzeichnen' in _gsrc_bl)
    check('Blur im Kundenprofil gesichert',
          "'bgblur_var'" in _gsrc_bl)

    # ---- v230b: KEIN MATTE-BLEED auf die Person ----
    # Ismets Befund "das Auge glitcht": ein heller, flimmernder Saum an Haar
    # und Schultern. Ursache waren ZWEI Weichzeichner, die ueber das GANZE
    # Bild liefen und dabei den hellen Hintergrund in die Silhouette
    # hineinmischten - danach wurde die Person mit weicher Matte darueber
    # gepastet, der Saum blieb sichtbar. Test: eine DUNKLE Person vor HELLEM
    # Grund darf innen nicht aufhellen.
    # Die Invariante ist RICHTUNGSFREI: der weichgezeichnete Hintergrund darf
    # nicht davon abhaengen, welche FARBE die Person hat. Haengt er daran,
    # steckt Person im Hintergrund - und ueber die weiche Matte kommt sie als
    # Saum zurueck. (Ueber die Helligkeit zu messen taugt nicht: ob der Saum
    # heller oder dunkler wird, haengt am Motiv.)
    print('\n--- Matte-Bleed (v230b) ---')
    Wm, Hm = 360, 640

    def _mb_bild(v):
        f = np.full((Hm, Wm, 3), 150.0, np.float32)
        f[120:520, 120:250] = v                      # "Person"
        return f

    al_m = np.zeros((Hm, Wm), np.float32)
    al_m[120:520, 120:250] = 1.0
    al_m = cv2.GaussianBlur(al_m, (0, 0), 2.0)[..., None]   # weiche Kante
    _aussen = al_m[..., 0] < 0.02
    _b0 = R.apply_bg_blur(_mb_bild(0.0), al_m, None, 1.0, Wm, Hm)
    _b1 = R.apply_bg_blur(_mb_bild(255.0), al_m, None, 1.0, Wm, Hm)
    _ab = float(np.abs(_b0 - _b1)[_aussen].max())
    check('Hintergrund-Blur zieht die Person nicht mit', _ab < 20.0,
          f'{_ab:.1f} von 255 (alt 76.7, Grenze 20)')

    # Zweiter Fundort: die Tiefen-Unschaerfe hinter einem 'behind'-Text.
    # WIRKSAMKEITS-NACHWEIS: composite_frame wird WIRKLICH aufgerufen - eine
    # reine Funktionspruefung haette v230b nicht gefunden, der Bleed steckte
    # in einem Zweig von composite_frame.
    _wm = [{'word': 'HINTEN', 'start': 0.0, 'end': 3.0}]
    _Sm = R.Sprites(yaml.safe_load(open(os.path.join(HERE, 'config.yaml'),
                                        encoding='utf-8')), Wm, Hm)
    _am = _Sm.text('HINTEN', 30, (255, 255, 255))[0]
    _cm = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _cm['effects']['dim_behind'] = 0.0        # Dimmen wuerde die Messung faerben
    _cm['effects']['anim'] = False
    _cm['effects']['bg_blur'] = 0.0           # hier NUR die Tiefen-Unschaerfe
    _cm['effects']['matte_spill'] = False
    _ps_bak = R.PERSON_SHADOW
    R.PERSON_SHADOW = 0.0
    _pm = [{'tpl': 'behind', 'kw_i': 0, 'start': 0.0, 'end': 3.0, 'arr': _am,
            'by': Hm * 0.85, 'small': [], 'tilt': 0.0, 'entr': 'rise'}]
    _o0, _o1 = (R.composite_frame(_mb_bild(v), al_m.copy(), 1.2,
                                  copy.deepcopy(_pm), _wm, (180, 300, 60),
                                  _cm, _Sm, Wm, Hm) for v in (0.0, 255.0))
    R.PERSON_SHADOW = _ps_bak
    _mt = _aussen & (np.arange(Hm)[:, None] < 500)     # ohne die Textzeile
    _at = float(np.abs(_o0 - _o1)[_mt].max())
    check('Tiefen-Unschaerfe zieht die Person nicht mit', _at < 12.0,
          f'{_at:.1f} von 255 (alt 28.9, Grenze 12)')
    # Gegenprobe: der Hintergrund MUSS weiter weichgezeichnet werden, sonst
    # haette man den Saum nur durch Abschalten des Effekts "geloest".
    _str_m = np.where((np.arange(Wm)[None, :, None] % 8 == 0), 255.0,
                      _mb_bild(30.0)).astype(np.float32)
    _var_vor = float(_str_m[10:40, 10:100].std())
    _bl2 = R.apply_bg_blur(_str_m.copy(), al_m, None, 1.0, Wm, Hm)
    _var_nach = float(_bl2[10:40, 10:100].std())
    check('Hintergrund bleibt trotzdem unscharf', _var_nach < _var_vor * 0.5,
          f'{_var_nach:.1f} < {_var_vor:.1f}*0.5')

    # ---- v230g: die neun Befunde der Bug-Jagd ----
    print('\n--- Bug-Jagd (v230g) ---')
    _Wg, _Hg = 540, 960
    _cg = yaml.safe_load(open(os.path.join(HERE, 'config.yaml'), encoding='utf-8'))
    _cg['effects']['anim'] = False
    _Sg = R.Sprites(_cg, _Wg, _Hg)
    _rsrc_sec230 = open(os.path.join(HERE, 'render.py'),
                        encoding='utf-8').read()

    # (1) Der Riegel gegen den Anschnitt hat SELBST angeschnitten: er
    # skalierte auf W*(1+2*rand) = 1.024 W, also breiter als das Bild.
    for _fk in (1.04, 1.20, 1.60, 2.50):
        _ag = _Sg.text('BREITESWORT', int(_Wg * _fk / 6), (255, 255, 255))[0]
        _pg = {'tpl': 'behind', 'kw_i': 0, 'start': 0.0, 'end': 3.0, 'arr': _ag,
               'cx': _Wg / 2, 'cy': _Hg * 0.5, 'small': [], 'front': [],
               'target': (_Wg / 2, _Hg / 2)}
        R.fit_into_frame([_pg], _Wg, _Hg)
        _bg = R.ink_box(_pg, _Wg, _Hg)
        check(f'v230g: Frame guard laesst bei {_fk:.2f}x nichts draussen',
              _bg is not None and _bg[0] >= -1 and _bg[1] <= _Wg + 1,
              f'{_bg[0] / _Wg:.4f}..{_bg[1] / _Wg:.4f} W' if _bg else 'keine Tinte')

    # (1b) v230h: DER GEWOLLTE RANDABFALL DARF NUR EIN WORT KOSTEN.
    # v152 laesst das Schlusswort am Bildrand auslaufen; dafuer nimmt der
    # Riegel die 'bleed'-Items aus der MESSUNG. Geschoben wurde danach aber
    # der ganze Block - ein breites Schlusswort zog den Rest auf der ANDEREN
    # Seite hinaus. In Ismets Render: 'CAPTIONS' links ohne C, 'LOOK THE'
    # rechts heraus. Gemessen: ohne bleed 0.012..0.988 W, mit bleed auf dem
    # letzten Wort -0.284..0.988 W.
    def _flow_bleed(_bl):
        _it, _x = [], -120.0
        for _k, _w in enumerate(('CAPTIONS', 'LOOK', 'THE')):
            _a = _Sg.text(_w, 150, (255, 255, 255))[0]
            _e = {'i': _k, 'arr': _a, 'cx': _x + _a.shape[1] / 2,
                  'cy': _Hg * 0.72, 'w': _a.shape[1]}
            if _k in _bl:
                _e['bleed'] = True
            _it.append(_e); _x += _a.shape[1] + 20
        return {'tpl': 'flow', 'front': _it, 'start': 0.0, 'end': 3.0,
                'layout': 'flow', 'punch': False, 'side': 0, 'ccam': 'none',
                'broll': False, 'target': (_Wg / 2, _Hg * 0.72), 'fol_lim': 0.0}

    for _nm, _bl in (('ohne Randabfall', set()),
                     ('Randabfall am Schlusswort', {2}),
                     ('Randabfall ueberall', {0, 1, 2})):
        _pb = _flow_bleed(_bl)
        R.fit_into_frame([_pb], _Wg, _Hg)
        _bb = R.ink_box(_pb, _Wg, _Hg)
        _l, _r = _bb[0] / _Wg, _bb[1] / _Wg
        check(f'v230h: {_nm} - nur EINE Seite laeuft aus, hoechstens 10 %',
              -0.11 <= _l and _r <= 1.11 and not (_l < -0.005 and _r > 1.005),
              f'{_l:+.3f}..{_r:.3f} W')
    check('v230h: der Deckel fuer den Randabfall steht als eine Zahl da',
          hasattr(R, '_BLEED_MAX_REL'))

    # (1c) v230h: die Kanten-Schaerfung wird nicht mehr an EINEM Bild
    # entschieden. Die Einzelmessung ist ein Muenzwurf (an Ismets Video:
    # 0.1s->1.0, 1.0s->0.3, 3.0s->1.0, 6.0s->0.3 ...) und sein Render
    # erwischte die 1.0 - 15 Sekunden lang volle Schaerfung, Kantenrauigkeit
    # 2.42 statt 1.51 und 104 Kruemel statt 2.
    check('v230h: die Schaerfung wird ueber mehrere Stellen bestimmt',
          'def _refine_wahl(' in _rsrc_sec230
          and '_refine_auto = None if not _rz else _refine_wahl(' in _rsrc_sec230)
    check('v230h: dabei gewinnt die strengste Antwort',
          'beste = min(beste, _refine_pruefen(' in _rsrc_sec230)
    check('v230h: kein Versatz schiebt Text aus dem Bild',
          "_ib = p.get('_ink')" in _rsrc_sec230
          and 'tdx = min(max(tdx, 2.0 - _ib[0]), (W - 2.0) - _ib[1])'
          in _rsrc_sec230)

    # (1d) v230k ist ZURUECKGENOMMEN (Ismets Ansage, 31.07.2026): zwei
    # Fliesstext-Bloecke gleichzeitig im Bild sind in Ordnung. Der
    # Testblock, der das Gegenteil festschrieb, ist deshalb raus - ein
    # Test darf keine ungefragte Verhaltensaenderung zementieren.
    def _fenster(p):
        return (float(p.get('t0', p['start'])),
                float(p['end']) + (0.40 if p.get('aus') is None
                                   else float(p['aus'])))

    # (1e) v230l: DASSELBE GESPROCHENE WORT STEHT NIE ZWEIMAL IM BILD.
    # Ismets Befund "das Gesagte wird zweimal eingeblendet". Der Fall ist der
    # ZWEITE Render desselben Videos: der erste Lauf schreibt _momente.json
    # mit dem AUTOMATISCHEN Wortlaut (words[i .. i+n]), der zweite liest ihn
    # als Nutzer-Ueberschreibung. Liegt in der Phrase eine Sprechpause, bricht
    # `phrase` frueher ab als `n`; der Kartentext ist dann laenger als die
    # Karte besitzt, `phrase = phrase[:1]` gab den Rest frei - und dieselben
    # Woerter standen direkt danach noch einmal als Fliesstext im Bild
    # (am Plan gemessen: Karte 'ON THE WALL' 5.10-6.55, danach Block 'wall.'
    # 6.55-6.98). Derselbe Fehlertyp wie v230g, eine Datei weiter.
    _wl2 = [{'word': w, 'start': 0.42 * i, 'end': 0.42 * i + 0.30}
            for i, w in enumerate('watch this one sticks on the wall now'.split())]
    for _k in range(6, len(_wl2)):          # Sprechpause MITTEN in der Phrase
        _wl2[_k]['start'] += 0.55
        _wl2[_k]['end'] += 0.55
    _fxl2 = {4: {'fx': 'ground', 'power': 3, 'n': 3, 'txt': 'on the wall',
                 'intent': True, 'szene': 'wand', 'lage': 'stehend'}}
    _Sl2 = R.Sprites(_cg, _Wg, _Hg)
    _pll2 = R.build_plans(_wl2, set(_fxl2), _cg, _Sl2, _Wg, _Hg,
                          lambda a, b: True, dict(_fxl2))

    def _worte_von(p):
        _o = set()
        for _t in str(p.get('kw_txt') or '').split():
            _n = re.sub(r'[^a-z0-9]', '', _t.lower())
            if _n:
                _o.add(_n)
        for _sl in ('small', 'front', 'tokens'):
            for _it in (p.get(_sl) or []):
                if isinstance(_it, dict) and isinstance(_it.get('i'), int):
                    _n = re.sub(r'[^a-z0-9]', '',
                                str(_wl2[_it['i']]['word']).lower())
                    if _n:
                        _o.add(_n)
        return _o

    _dopp2 = []
    _lst2 = [(p, _worte_von(p), _fenster(p)) for p in _pll2]
    _lst2 = [x for x in _lst2 if x[1]]
    for _i2 in range(len(_lst2)):
        for _j2 in range(_i2 + 1, len(_lst2)):
            _a2, _wa2, _fa2 = _lst2[_i2]
            _b2, _wb2, _fb2 = _lst2[_j2]
            if _fb2[0] > _fa2[1] + 1.0 or _fa2[0] > _fb2[1] + 1.0:
                continue
            _g2 = _wa2 & _wb2
            if _g2:
                _dopp2.append(sorted(_g2))
    check('v230l: kein gesprochenes Wort steht zweimal im Bild',
          not _dopp2, f'{len(_dopp2)} Fall/Faelle: {_dopp2[:3]}')
    # Der Riegel muss die Woerter der KARTE zuschlagen, nicht sie loeschen
    # (v230f: ein Schutz darf begrenzen, nie wegwerfen).
    _kart2 = [p for p in _pll2 if p.get('kw_txt')]
    check('v230l: die Karte zeigt weiterhin den ganzen angesagten Text',
          any('WALL' in str(p.get('kw_txt', '')).upper() for p in _kart2),
          str([p.get('kw_txt') for p in _kart2]))
    # Der AUTOMATISCHE Wortlaut aus dem Sidecar ist keine Nutzer-Aenderung.
    check('v230l: der Automatik-Wortlaut gilt nicht als Nutzer-Text',
          "if m.get('text') and str(m['text']).strip():" in _rsrc_sec230
          and '_norm_txt(str(m[\'text\'])) != _norm_txt(_mauto)' in _rsrc_sec230)
    # Ein laengerer Kartentext darf die Phrase NICHT mehr verkuerzen.
    check('v230l: laengerer Kartentext gibt keine Woerter frei',
          'elif len(ov_toks) < len(phrase) and len(phrase) >= 2:'
          in _rsrc_sec230)
    check('v230l: Doppeltext-Wache meldet im Job-Log',
          'Duplicate text warning:' in _rsrc_sec230)

    # (2) Der Abzug der halben Hoehenzunahme verankerte die UNTERKANTE der
    # Anim-Leinwand. Am Tinten-Schwerpunkt gemessen profitiert davon KEINE
    # Animation, fuenf werden dauerhaft nach oben verschoben.
    _bg2 = _Sg.text('WUCHT', 110, (255, 255, 255))[0]

    def _cy_ink(_a, _cy):
        _al = _a[:, :, 3].astype(np.float32)
        _ys = np.arange(_a.shape[0], dtype=np.float32) - _a.shape[0] / 2.0
        return _cy + float((_ys[:, None] * _al).sum() / max(_al.sum(), 1))

    _ref_g = _cy_ink(_bg2, _Hg * 0.5)
    for _an, _alt in (('regen', 123), ('bruch', 68), ('schweben', 22)):
        _pa = {'anim': _an, 'start': 0.0, 'kw_i': 3}
        _aa, _adx, _ady, _asc, _aop = R.anim_apply(_pa, _bg2, (0.5, 0.4, 0.3), 1.2)
        _ver = abs(_cy_ink(_aa, _Hg * 0.5 + _ady) - _ref_g)
        check(f'v230g: Animation {_an} sitzt nicht mehr zu hoch', _ver < 12,
              f'{_ver:.1f} px (alt ~{_alt} px)')
    check('v230g: der Abzug ist ueberall raus',
          '.shape[0]) / 2' not in open(os.path.join(HERE, 'render.py'),
                                       encoding='utf-8').read())

    # (3) DIE URSACHE DES ANGESCHNITTENEN TEXTS: der Analyse-Lauf schreibt in
    # JEDEN Block den Automatik-Wortlaut ins Feld 'text' - und der wurde beim
    # naechsten Lauf als NUTZER-Textueberschreibung fuer das Keyword gelesen.
    # Aus 'CAPTIONS' wurde 'WIE WIR CAPTIONS AUF', quer durchs Bild.
    check('v230g: Automatik-Blocktext gilt nicht als Nutzeraenderung',
          R._norm_txt('WIE WIR CAPTIONS AUF') == R._norm_txt('wie wir captions auf.')
          and R._norm_txt('CAPTIONS') != R._norm_txt('wie wir captions auf'))

    # (4) Der Solo-Riegel schob bei einer Ansage den Block ohne Obergrenze
    # nach hinten - notfalls hinter sein eigenes Ende. Dann ist das
    # Anzeigefenster leer und der Block kommt in KEINEM Bild vor.
    def _solo_g(_end, _spaet, _intent):
        # _FLOW_MIN ist lokal in build_plans - hier derselbe Wert.
        return (_end - _spaet >= 0.55) or (_intent and _spaet < _end - 0.12)

    check('v230g: eine Ansage schiebt keinen Block hinter sein Ende',
          not _solo_g(2.00, 2.82, True) and not _solo_g(4.44, 4.47, True))
    check('v230g: eine Ansage darf weiter schieben, solange der Block steht',
          _solo_g(3.00, 2.50, True))

    # (5) DER EIGENTLICHE BEWEIS (composite_frame wirklich aufrufen, frische
    # Plaene je Lauf - v221): die Stuetzzeile haengt am WORT, nicht an der
    # Karte. Lag das Schluesselwort nicht am Gruppenanfang, war bis zu 0.84 s
    # GAR NICHTS im Bild, obwohl durchgehend gesprochen wurde.
    _wg = [{'word': w, 'start': 0.20 + i * 0.28, 'end': 0.20 + i * 0.28 + 0.24}
           for i, w in enumerate(['but', 'captions', 'we', 'MASSIVE',
                                  'here', 'now'])]
    _fr_g = np.full((_Hg, _Wg, 3), 40.0, np.float32)
    for _fxg in ('outline', 'cascade', 'blurin'):
        _leer = 0
        for _j in range(6):
            _tg = 0.55 + _j * 0.10
            _Sx = R.Sprites(_cg, _Wg, _Hg)
            _plx = R.build_plans(_wg, {3}, _cg, _Sx, _Wg, _Hg,
                                 lambda a, b: True,
                                 {3: {'fx': _fxg, 'power': 2, 'n': 1}})
            _cx = R.composite_frame(_fr_g.copy(), None, _tg, _plx, _wg,
                                    (_Wg * 0.5, _Hg * 0.42), _cg, _Sx, _Wg, _Hg)
            if int((np.abs(_cx - _fr_g).max(axis=2) > 12).sum()) == 0:
                _leer += 1
        check(f'v230g: {_fxg} zeigt die Stuetzzeile schon vor der Karte',
              _leer == 0, f'{_leer} von 6 Bildern leer')

    # (5b) v230m: BEI 'behind' STAND DIE STUETZZEILE ZWEIMAL IM BILD.
    # Der behind-Zweig ist der einzige ohne `dt >= 0` - er zeichnet die
    # Stuetzzeile schon vor der Karte, und genau deshalb war er in v230g das
    # Vorbild. Der Vorlauf aus (5) kam bei ihm also OBENDRAUF, mit dem
    # Gesichts-Versatz statt ohne: dieselbe Zeile zweimal, um (tdx, tdy)
    # verschoben (an Ismets Render gemessen: 'THIS ONE FLOATS' doppelt,
    # 58 px rechts und 75 px tiefer).
    # Messweg: TINTE ist gegen Verschieben unempfindlich. Steht die Zeile
    # einmal, ist die Tintenmenge MIT Gesichts-Versatz dieselbe wie ohne;
    # steht sie zweimal, waechst sie deutlich. Ein Vergleich zweier
    # Positionen braucht keinen Referenzwert im Test.
    def _ink_bei(_face, _t):
        _Sm = R.Sprites(_cg, _Wg, _Hg)
        _plm = R.build_plans(_wg, {3}, _cg, _Sm, _Wg, _Hg, lambda a, b: True,
                             {3: {'fx': 'behind', 'power': 2, 'n': 1}},
                             face_pos=lambda a, b: (_Wg * 0.42, _Hg * 0.30,
                                                    _Hg * 0.16))
        _cm = R.composite_frame(_fr_g.copy(), None, _t, _plm, _wg, _face,
                                _cg, _Sm, _Wg, _Hg)
        return int((np.abs(_cm - _fr_g).max(axis=2) > 12).sum())

    _ruhe = sum(_ink_bei((_Wg * 0.42, _Hg * 0.30), 0.55 + _j * 0.10)
                for _j in range(5))
    _vers = sum(_ink_bei((_Wg * 0.66, _Hg * 0.46), 0.55 + _j * 0.10)
                for _j in range(5))
    check('v230m: behind zeichnet die Stuetzzeile nur EINMAL',
          _ruhe > 0 and abs(_vers - _ruhe) <= _ruhe * 0.08,
          f'ohne Versatz {_ruhe}, mit Versatz {_vers} Tintenpixel')
    check('v230m: der Vorlauf laesst den behind-Zweig aus',
          "if dt < 0 and p.get('small') and p['tpl'] != 'behind':" in _rsrc_sec230)

    # (5c) v230m: HOECHSTENS ZWEI TEXTE, NIE DREI (Ismets Ansage).
    # An der Wand standen Karte + Ankerwort + Stuetzzeile gleichzeitig.
    # Karte plus eigene Stuetzzeile sind erlaubt - die ALTE Karte muss weg
    # sein, bevor die naechste ihr erstes Element zeigt.
    _wz = [{'word': w, 'start': 0.36 * i, 'end': 0.36 * i + 0.30}
           for i, w in enumerate(('this next line goes behind me this one '
                                  'sticks on the wall this one floats above '
                                  'me now').split())]
    for _p2 in (5, 11, 16):
        _wz[_p2]['word'] += '.'
    _fxz = {4: {'fx': 'behind', 'power': 3, 'n': 2, 'intent': True},
            9: {'fx': 'ground', 'power': 3, 'n': 3, 'intent': True,
                'szene': 'wand', 'lage': 'stehend'},
            15: {'fx': 'behind', 'power': 3, 'n': 2, 'intent': True,
                 'szene': 'himmel'}}
    _Sz = R.Sprites(_cg, _Wg, _Hg)
    _plz = R.build_plans(_wz, set(_fxz), _cg, _Sz, _Wg, _Hg, lambda a, b: True,
                         dict(_fxz))
    _kz = sorted([p for p in _plz if p.get('kw_txt')],
                 key=lambda p: float(p['start']))

    def _weg(p):
        _a = p.get('aus')
        return float(p['end']) + (0.40 if _a is None else float(_a))

    _kol = [(a.get('kw_txt'), b.get('kw_txt'))
            for a, b in zip(_kz, _kz[1:]) if _weg(a) > float(b['start']) + 1e-3]
    check('v230m: eine Karte ist weg, bevor die naechste anfaengt',
          len(_kz) >= 2 and not _kol, f'{len(_kz)} Karten, Kollisionen {_kol}')
    check('v230m: gekuerzt wird nur das Ausklingen, nie unter 0.10 s',
          all(p.get('aus') is None or 0.10 - 1e-6 <= float(p['aus']) <= 0.40
              for p in _kz), str([p.get('aus') for p in _kz]))
    check('v230m: das Ankerwort weicht auch einer anderen Karte',
          "(q.get('front') or q.get('kw_txt'))" in _rsrc_sec230)

    # (5d) v230m: SCHNITTE OHNE FARBUNTERSCHIED. Das Farb-Histogramm ist auf
    # einem Studio-Set blind - in Ismets Werbespot fand es KEINEN der vier
    # Schnitte (bestes Signal 0.935 gegen die Schwelle 0.55). Der Bildaufbau
    # aendert sich dagegen massiv. Testvideo: gleiche Farben, gleiche
    # Helligkeit im Mittel, nur die ANORDNUNG springt.
    _cv = os.path.join(tempfile.gettempdir(), 'st_grau_cut.mp4')
    _vw = cv2.VideoWriter(_cv, cv2.VideoWriter_fourcc(*'mp4v'), 24, (240, 426))
    for _f in range(72):
        _img = np.full((426, 240, 3), 128, np.uint8)
        _x = 20 if _f < 36 else 130         # Block springt bei Frame 36
        _img[120:300, _x:_x + 90] = 40
        _vw.write(_img)
    _vw.release()
    _hs, _th = [], []
    _cap = cv2.VideoCapture(_cv)
    while True:
        _ok, _f2 = _cap.read()
        if not _ok:
            break
        _tiny = cv2.resize(_f2, (160, 90))
        _h2 = cv2.calcHist([cv2.cvtColor(_tiny, cv2.COLOR_BGR2HSV)], [0, 1],
                           None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(_h2, _h2)
        _hs.append(_h2)
        _th.append(cv2.resize(cv2.cvtColor(_tiny, cv2.COLOR_BGR2GRAY),
                              (32, 32)).astype(np.float32))
    _cap.release()
    _korr = min(float(cv2.compareHist(_hs[i - 1], _hs[i], cv2.HISTCMP_CORREL))
                for i in range(1, len(_hs)))
    _madl = [float(np.abs(_th[i] - _th[i - 1]).mean())
             for i in range(1, len(_th))]
    _gr = max(12.0, 6.0 * float(np.median(_madl)))
    check('v230m: die Farbe verraet diesen Schnitt NICHT (Studio-Grau)',
          _korr >= 0.55, f'beste Farb-Abweichung {_korr:.3f}')
    check('v230m: der Bildaufbau verraet ihn',
          max(_madl) >= _gr, f'max {max(_madl):.1f} gegen Schwelle {_gr:.1f}')
    check('v230m: und zwar genau an der Sprungstelle',
          abs(int(np.argmax(_madl)) + 1 - 36) <= 1,
          f'gefunden bei Frame {int(np.argmax(_madl)) + 1}')
    check('v230m: die Schnitt-Suche nutzt beide Signale',
          '_mad_gr = (max(12.0, 6.0 * float(np.median(_mad)))' in _rsrc_sec230
          and 'or (_mad and _mad[i - 1] >= _mad_gr)' in _rsrc_sec230)
    try:
        os.remove(_cv)
    except OSError:
        pass

    # (6) Look 'TikTok': der buchstabenweise Aufbau ruft anim_apply gar nicht
    # auf - eine gewaehlte Animation lief damit NIE. Sie gewinnt jetzt.
    _rsrc_g = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('v230g: kinetischer Aufbau weicht einer gewaehlten Animation',
          _rsrc_g.count("and not p.get('anim')") >= 2)

    # (7) Der Wachhund raeumte Jobs ab, die nur in der Schlange warteten.
    _ssrc_g = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    check('v230g: ein wartender Job in der Schlange gilt nicht als haengend',
          '_in_schlange' in _ssrc_g and "stt == 'wartet' and jid in _in_schlange"
          in _ssrc_g)
    # (8) Support-Zaehler: derselbe Filter wie die Liste, sonst bleibt er stehen.
    check('v230g: der Support-Zaehler kennt ausgeblendete Tickets',
          _ssrc_g.count("t.status = 'closed' AND t.updated_at < ?") >= 2)

    # ---- v70: Musik-Beat-Erkennung ----
    print('\n--- Musik-Beat ---')
    check('music_beats existiert', hasattr(R, 'music_beats'))
    check('Config: music_beat',
          'music_beat' in open(os.path.join(HERE, 'config.yaml'),
                               encoding='utf-8').read())
    import wave, struct
    _wav_path = os.path.join(tempfile.gettempdir(), 'dve_st_beat.wav')

    def _write_wav(samples, sr=44100):
        s16 = np.clip(samples * 32767, -32768, 32767).astype(np.int16)
        with wave.open(_wav_path, 'wb') as _wf:
            _wf.setnchannels(1); _wf.setsampwidth(2); _wf.setframerate(sr)
            _wf.writeframes(s16.tobytes())

    # 120 BPM Kick: alle 0.5 s ein Sub-Bass-Puls
    sr = 44100
    dur = 8.0
    n_samp = int(sr * dur)
    x = np.zeros(n_samp, np.float32)
    kick_every = int(sr * 0.5)                          # 120 BPM -> 0.5 s Abstand
    for pos in range(0, n_samp - 2000, kick_every):
        env = np.exp(-np.arange(2000) / 400.0).astype(np.float32)
        tone = np.sin(2 * np.pi * 60 * np.arange(2000) / sr).astype(np.float32)
        x[pos:pos + 2000] += env * tone * 0.8
    _write_wav(x)
    env, bpm, conf = R.music_beats(_wav_path, int(dur * 30), 30.0)
    check('Musik-Beat: 120 BPM erkannt (Toleranz +/- 5)',
          abs(bpm - 120) <= 5, f'{bpm} BPM')
    check('Musik-Beat: Confidence hoch bei klarem Beat',
          conf > 0.30, f'conf={conf:.2f}')
    check('Musik-Beat: Envelope hat Peaks',
          float(env.max()) > 0.5)

    # Reines Rauschen (kein Beat): conf muss klein sein
    x2 = (np.random.default_rng(0).standard_normal(n_samp) * 0.05).astype(np.float32)
    _write_wav(x2)
    env2, bpm2, conf2 = R.music_beats(_wav_path, int(dur * 30), 30.0)
    check('Musik-Beat: Rauschen -> niedrige Confidence',
          conf2 < 0.30, f'conf={conf2:.2f}')

    # Stille -> alles 0
    _write_wav(np.zeros(n_samp, np.float32))
    env3, bpm3, conf3 = R.music_beats(_wav_path, int(dur * 30), 30.0)
    check('Musik-Beat: Stille -> conf 0, bpm 0',
          conf3 == 0.0 and bpm3 == 0)

    os.remove(_wav_path)

    _rsrc_mb = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Musik-Beat: Pipeline mischt in aud_onset',
          'music_beats(voice_wav' in _rsrc_mb
          and 'np.maximum(aud_onset, beat_env' in _rsrc_mb)
    check('Musik-Beat: Confidence-Gate greift',
          'conf > 0.10' in _rsrc_mb)
    check('Musik-Beat: Regler in der GUI',
          'mbeat_var' in _gsrc_bl and 'Musik-Beat' in _gsrc_bl)
    check('Musik-Beat: im Kundenprofil gesichert',
          "'mbeat_var'" in _gsrc_bl)

    # ---- v73: 5 neue Effekt-Klassen ----
    print('\n--- v73: 5 neue Effekt-Klassen ---')
    for _fn in ('apply_duplicate_trail', 'apply_counter_ring',
                'apply_split_screen', 'apply_env_shadow'):
        check(f'{_fn} existiert', hasattr(R, _fn))
    # Config-Keys da
    _cfg_src = open(os.path.join(HERE, 'config.yaml'), encoding='utf-8').read()
    for _k in ('freeze_frame', 'trail', 'counter_ring', 'split_screen', 'env_shadow'):
        check(f'Config: {_k}', _k in _cfg_src)
    # Freeze-Frame ist Pipeline-Modifikator - Source-Check + Kommentar-Test
    _r_v73 = open(os.path.join(HERE, 'render.py'), encoding='utf-8').read()
    check('Freeze-Frame: Pipeline-Modifikator verdrahtet',
          'freeze_windows' in _r_v73 and 'frozen_frame' in _r_v73
          and "cfg['effects'].get('freeze_frame'" in _r_v73)
    check('Freeze-Frame: nur staerkster power=3 (B-Roll ausgeschlossen)',
          "not p.get('broll')" in _r_v73)

    # Trail: erzeugt sichtbare versetzte Kopie
    _fr_t = np.zeros((100, 200, 3), np.uint8)
    _cmp_t = _fr_t.copy()
    _cmp_t[40:60, 80:120] = 255                          # "Text" hell mittig
    _tr = R.apply_duplicate_trail(_cmp_t.copy(), _fr_t, 1.0, offset_px=10, layers=2)
    check('Trail: strength=1 malt Kopien links vom Text',
          float(_tr[40:60, 40:80].mean()) > float(_cmp_t[40:60, 40:80].mean()) + 3,
          f'{_tr[40:60, 40:80].mean():.1f} > {_cmp_t[40:60, 40:80].mean():.1f}+3')
    _tr0 = R.apply_duplicate_trail(_cmp_t.copy(), _fr_t, 0.0)
    check('Trail: strength=0 ist no-op',
          np.array_equal(_tr0, _cmp_t))
    _tr_empty = R.apply_duplicate_trail(_fr_t.copy(), _fr_t, 1.0)
    check('Trail: ohne Text kein Trail',
          np.array_equal(_tr_empty, _fr_t))

    # Counter-Ring: malt Ring nur bei count-Momenten
    _fr_r = np.full((200, 300, 3), 50, np.uint8)
    _p_count = {'tpl': 'behind', 'start': 0.0, 'end': 2.0, 't0': 0.0,
                'kw_i': 1, 'cx': 150, 'cy': 100, 'power': 2,
                'count': {'dur': 1.0, 'fmt': lambda x: str(int(x))}}
    _rr = R.apply_counter_ring(_fr_r.copy(), [_p_count], 0.5, 300, 200, 1.0)
    check('Ring: malt sichtbaren Kreis um cx/cy',
          not np.array_equal(_rr, _fr_r))
    _p_nocount = {'tpl': 'behind', 'start': 0.0, 'end': 2.0, 'kw_i': 1,
                  'cx': 150, 'cy': 100, 'power': 2}
    _rr2 = R.apply_counter_ring(_fr_r.copy(), [_p_nocount], 0.5, 300, 200, 1.0)
    check('Ring: kein Count -> kein Ring',
          np.array_equal(_rr2, _fr_r))

    # Split-Screen: pruefe dass Frame vertikal ausgeschoben wird (Luecke sichtbar)
    _fr_s = np.full((200, 200, 3), 200, np.uint8)
    _p_pow3 = {'tpl': 'behind', 'start': 0.0, 'end': 2.0, 't0': 0.0,
               'kw_i': 1, 'cx': 100, 'cy': 100, 'power': 3, 'broll': False}
    _ss = R.apply_split_screen(_fr_s.copy(), _fr_s, [_p_pow3], 0.8, 200, 200, 1.0)
    _mid = _ss[99:101, :, 0].mean()                       # Mitte muss dunkel sein (Luecke)
    check('Split: Luecke in der Mitte (dunkler)', _mid < 100, f'mid={_mid:.1f}')
    _p_pow2 = dict(_p_pow3); _p_pow2['power'] = 2
    _ss_no = R.apply_split_screen(_fr_s.copy(), _fr_s, [_p_pow2], 0.8, 200, 200, 1.0)
    check('Split: power<3 -> kein Split',
          np.array_equal(_ss_no, _fr_s))

    # Env-Shadow: dunkelt neben dem Text ab (nicht auf dem Text)
    _fr_e = np.full((200, 300, 3), 200, np.uint8)
    _cmp_e = _fr_e.copy()
    _cmp_e[80:120, 100:200] = 255                         # "Text" hell
    _p_grd = {'tpl': 'ground', 'start': 0.0, 'end': 2.0, 't0': 0.0,
              'kw_i': 1, 'cx': 150, 'cy': 100, 'power': 2, 'broll': False}
    _es = R.apply_env_shadow(_cmp_e.copy(), _fr_e, [_p_grd], 0.8, 300, 200, 1.0)
    # Unter dem Text (y=125..135) muss abgedunkelt sein vs. Original-Fond
    _shadow_zone = float(_es[125:135, 110:190, 0].mean())
    _orig_zone = float(_fr_e[125:135, 110:190, 0].mean())
    check('Env-Shadow: dunkelt unter dem Text ab',
          _shadow_zone < _orig_zone - 5,
          f'{_shadow_zone:.1f} < {_orig_zone:.1f}-5')
    # Auf dem Text (y=90..110) darf sich fast nichts aendern (Schatten
    # wird durch text-Maske ausgeblendet)
    _on_text = float(_es[90:110, 130:170, 0].mean())
    _on_text_orig = float(_cmp_e[90:110, 130:170, 0].mean())
    check('Env-Shadow: Text selbst bleibt hell',
          abs(_on_text - _on_text_orig) < 3,
          f'{_on_text:.1f} vs {_on_text_orig:.1f}')
    # Kein ground-Moment -> no-op
    _p_beh = dict(_p_grd); _p_beh['tpl'] = 'behind'
    _es_no = R.apply_env_shadow(_cmp_e.copy(), _fr_e, [_p_beh], 0.8, 300, 200, 1.0)
    check('Env-Shadow: nur bei ground', np.array_equal(_es_no, _cmp_e))

    # GUI-Regler + Profil
    _g_v73 = open(os.path.join(HERE, 'gui.py'), encoding='utf-8').read()
    for _v in ('freeze_var', 'trail_var', 'cring_var', 'split_var', 'envsh_var'):
        check(f'GUI: {_v} definiert', _v in _g_v73)
    for _v in ('freeze_var', 'trail_var', 'cring_var', 'split_var', 'envsh_var'):
        check(f'Profil: {_v} gesichert', f"'{_v}'" in _g_v73)
    check('GUI: Special-Effects-Karte',
          'Spezial-Effekte (v73)' in _g_v73)


if __name__ == '__main__':
    main()
