# -*- coding: utf-8 -*-
"""DouchkoVE Selbsttest: rendert alle Szenarien und prueft die Ergebnisse automatisch.
Aufruf: python selftest.py <testclip.mp4> <transcript.json> [pan_test.mp4] [mixed_test.mp4]"""
import json
import copy
import os
import re
import shutil
import cv2
import urllib.parse
import subprocess
import sys
import tempfile

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
    results.append((name, ok, detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail else ''))


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
        _scenario_trail(tmp)
        _scenario_lang(tmp)

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
    check('Matting-Gating aktiv', 'Matting-Fenster' in log and 'von ~' in log)
    check('Wort-Timing nachjustiert', 'nachjustiert' in log)
    check('SFX intelligent gesetzt', 'Onset' in log)
    check('Sound-Pack wird im Render benutzt', 'Sound-Pack:' in log)


def _scenario_2a(clip, transcript, tmp, mixed):
    # 2) B-Roll bleibt textfrei
    if mixed:
        out2 = os.path.join(tmp, 'st_mixed.mp4')
        code, log = render(mixed, transcript, out2)
        check('B-Roll-Szenen erkannt', 'B-Roll eingestuft' in log)
        check('B-Roll komplett textfrei', '0 ueber B-Roll' in log)

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
        json.dump({'keywords': [{'i': pair, 'n': 2, 'fx': 'ground', 'power': 2}]},
                  open(os.path.splitext(ph_src)[0] + '_regie3.json', 'w'))
        out7 = os.path.join(tmp, 'st_phrase.mp4')
        code, log = render(ph_src, transcript, out7,
                           extra=['--duration', str(words[pair]['end'] + 1.5)])
        check('Phrasen-Highlight rendert',
              code == 0 and 'KI-Regie:' in log and os.path.exists(out7))


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
    check('Baseline-Grid: Anker im unteren Drittel',
          abs(_anchor('cascade') - 1080 * 0.40) < 1e-6)

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
    # Nach build_plans darf kein Paar mit target ko-sichtbar+nah stehen
    def _codisplay(pl):
        ts = [p for p in pl if 'target' in p]
        for _x in range(len(ts)):
            for _y in range(_x + 1, len(ts)):
                a, b = ts[_x], ts[_y]
                lo = max(a.get('t0', a['start']), b.get('t0', b['start']))
                hi = min(a['end'], b['end'])
                if (hi - lo > 0.25
                        and abs(a['target'][1] - b['target'][1]) < 1920 * 0.16
                        and abs(a['target'][0] - b['target'][0]) < 1080 * 0.42):
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
    late = sum(1 for p in pli if p['start'] >= 15 and p['tpl'] == 'stack')
    check('Hook-Intro dicht/duenn', early >= 8 and late == 0, f'{early} vorn, {late} Stacks hinten')

    # Personen-Follow: Stacks tragen Anker
    stacks = [p for p in pli if p['tpl'] == 'stack']
    check('Follow-Anker an Stacks',
          bool(stacks) and all('anchor' in p or p.get('broll') for p in stacks))

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
                _b.getvalue().count('Watchtime-Moment'))

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
        c2['effects'].update(retention_gap=0, pattern_interrupt=0, **eff)
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
    # 3) cfg_overrides-Whitelist + Deckel
    ov = SV._sanitize_overrides({'output': {'height': 4320, 'master': True},
                                 'effects': {'blender_samples': 99999, 'bg_blur': 0.5},
                                 'boeses': {'x': 1}})
    check('cfg_overrides: Whitelist + Ressourcen-Deckel',
          ov.get('output', {}).get('height') == 1920
          and 'master' not in ov.get('output', {})
          and ov['effects']['blender_samples'] == 256
          and ov['effects']['bg_blur'] == 0.5 and 'boeses' not in ov)
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
    # 8) Kauf idempotent + atomar (Webhook-Retry schreibt nicht doppelt)
    b0 = SV._find_user_by_id(uid)['balance_sec']
    r1 = SV._credit_purchase(uid, 100, 'sessAAA')
    r2 = SV._credit_purchase(uid, 100, 'sessAAA')
    b1 = SV._find_user_by_id(uid)['balance_sec']
    check('Kauf: idempotent (Retry schreibt nicht doppelt)',
          r1 is True and r2 is False and b1 == b0 + 100,
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
    check('Admin: kein Default admin, Header + timing-safe',
          "os.environ.get('DVE_ADMIN', 'admin')" not in _src
          and 'hmac.compare_digest(given, key)' in _src
          and "request.headers.get('x-admin-key'" in _src)
    # 13) Security-Header werden auf jeder Antwort gesetzt
    check('Security-Header (CSP/XFO/nosniff) aktiv',
          'Content-Security-Policy' in _src and 'X-Frame-Options' in _src
          and 'X-Content-Type-Options' in _src)
    # 14) SEPA: Guthaben nur bei wirklich bezahltem Status
    check('Webhook schreibt nur bei payment_status paid gut',
          "sess.get('payment_status') != 'paid'" in _src
          and 'async_payment_succeeded' in _src)
    # 15) Login gleicht Timing an (Dummy-Hash bei unbekannter Mail)
    check('Login: Timing-Angleich gegen Mail-Enumeration',
          '_verify_pw(password, _DUMMY_HASH)' in _src)
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
    _s = open(os.path.join(HERE, 'web', 'server.py'), encoding='utf-8').read()
    trails = [float(x) for x in _re.findall(r"'trail':\s*([0-9.]+)", _s)]
    check('Kein Preset hat Trail an (Person-Doppler-Quelle aus)',
          bool(trails) and all(t == 0.0 for t in trails), f'{trails}')


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
    # KERN von B: _apply_action_anim erzwingt Animationen ohne GPT
    w2 = [{'word': w} for w in
          'the word flies and everything explodes then shatter'.split()]
    fm = R._apply_action_anim({}, w2)
    anims = {w2[i]['word']: v.get('anim') for i, v in fm.items()}
    check('Aktion-Anim erzwungen: flies->spur, explodes->explosion, shatter->bruch',
          anims.get('flies') == 'spur' and anims.get('explodes') == 'explosion'
          and anims.get('shatter') == 'bruch', str(anims))
    fm2 = R._apply_action_anim({5: {'fx': 'outline', 'power': 3, 'n': 1}}, w2)
    check('Aktion-Anim: vorhandenes Wort behaelt fx, kriegt nur Anim dazu',
          fm2[5].get('fx') == 'outline' and fm2[5].get('anim') == 'explosion')
    # Deutsch: "die Preise fallen" -> fallen wird sturz
    wd = [{'word': w} for w in 'die preise fallen heute stark'.split()]
    fmd = R._apply_action_anim({}, wd)
    check('Aktion-Anim Deutsch: fallen->sturz',
          any(v.get('anim') == 'sturz' for v in fmd.values()), str(fmd))


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
