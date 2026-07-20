# -*- coding: utf-8 -*-
"""DouchkoVE Motion-Graphics-Engine (v97 Prototyp): prozedurale, animierte
Overlays im High-End-Look - Unterstreichung, Kreis um Zahlen, Box-Highlight,
Partikel-Burst. Kein Asset-Pack, alles gezeichnet: 2x-Supersampling gegen
Treppchen, echte Ease-Kurven (Out-Quart/Spring mit Overshoot), kurze Dauern,
dezenter Glow. Billig wirkt Motion-Graphics durch lineares Timing und harte
Kanten - genau das vermeidet dieses Modul.

Prototyp-CLI baut ein Demo-Video mit mehreren Momenten auf echtem Material.
"""
import math
import os
import subprocess
import tempfile
import numpy as np

try:
    import cv2
except Exception:                      # pragma: no cover
    cv2 = None
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SS = 2                                  # Supersampling-Faktor (Kantenglaette)


def ease_out_quart(t):
    t = min(max(t, 0.0), 1.0)
    return 1.0 - (1.0 - t) ** 4


def ease_spring(t, over=0.12):
    """Ease-Out mit leichtem Overshoot - der 'teure' Pop."""
    t = min(max(t, 0.0), 1.0)
    return 1.0 + over * math.sin(t * math.pi) * (1.0 - t) * 4 if t > 0.55 \
        else ease_out_quart(t / 0.55) * (1.0 + over)


def _font(sz, bold=True):
    p = os.path.join(HERE, 'fonts', 'archivo.ttf')
    try:
        return ImageFont.truetype(p, sz)
    except Exception:
        return ImageFont.load_default()


def _glow_line(d, xy, col, w):
    """Linie mit dezentem Glow: breiter, transparenter Unterzug + Kernlinie."""
    r, g, b, a = col
    d.line(xy, fill=(r, g, b, int(a * 0.28)), width=int(w * 2.2))
    d.line(xy, fill=col, width=w)
    # runde Kappen
    for (x, y) in (xy[0], xy[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)


def gfx_underline(d, x0, x1, y, prog, col, w):
    """Unterstreichung zieht sich unter das Wort (Ease-Out, leichter Overshoot)."""
    p = ease_spring(prog, 0.06)
    end = x0 + (x1 - x0) * min(p, 1.04)
    if end > x0 + 2:
        _glow_line(d, [(x0, y), (end, y)], col, w)


def gfx_circle(d, bbox, prog, col, w):
    """Kreis wird um das Wort GEZEICHNET (Stroke-Progress wie von Hand,
    leicht geneigt und minimal unrund - Marker-Feel, kein Klipart)."""
    x0, y0, x1, y1 = bbox
    pad = (x1 - x0) * 0.10
    box = (x0 - pad, y0 - pad * 1.6, x1 + pad, y1 + pad * 1.6)
    p = ease_out_quart(prog)
    start = -75
    d.arc(box, start, start + 385 * p, fill=col, width=w)
    if p > 0.94:                        # Ueberlapp am Ende = handgezeichnet
        d.arc((box[0] + 3 * SS, box[1] + 4 * SS, box[2] - 2 * SS, box[3] + 2 * SS),
              start + 340, start + 385, fill=col, width=max(w - SS, 1))


def gfx_box(d, bbox, prog, col):
    """Highlight-Box klappt hinter dem Wort auf (Scale-X, Spring)."""
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2
    p = min(ease_spring(prog, 0.10), 1.08)
    hw = (x1 - x0) / 2 * p
    pad = (y1 - y0) * 0.28
    d.rounded_rectangle((cx - hw - pad, y0 - pad, cx + hw + pad, y1 + pad),
                        radius=(y1 - y0) * 0.24, fill=col)


def gfx_burst(d, cx, cy, prog, col, r_max, n=12, seed=3):
    """Partikel-Burst: kraeftige Striche fliegen radial, laufen aus und
    verblassen. Der Burst selbst lebt nur ~0.6s (danach unsichtbar) - kurz und
    knackig, kein Dauergeriesel."""
    p_t = min(prog / 0.38, 1.0)          # Burst-Fenster: die ersten ~38% des Moments
    if prog > 0.55:
        return
    rng = np.random.default_rng(seed)
    p = ease_out_quart(p_t)
    fade = int(255 * (1.0 - min(prog / 0.55, 1.0)) ** 1.2)
    if fade <= 0:
        return
    for k in range(n):
        ang = (k / n) * 2 * math.pi + float(rng.random()) * 0.5
        ln = r_max * (0.85 + 0.55 * float(rng.random()))
        r0 = ln * (0.20 + 0.80 * p)
        r1 = ln * (0.52 + 0.68 * p)
        w = max(int((6 - 3.5 * p) * SS), 2)
        c = (col[0], col[1], col[2], fade)
        _glow_line(d, [(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                       (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)], c, w)


def _text_sprite(txt, sz, col=(255, 255, 255, 255), stroke=3):
    f = _font(sz)
    dummy = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    bb = dummy.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    img = Image.new('RGBA', (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((4 - bb[0], 4 - bb[1]), txt, font=f, fill=col,
           stroke_width=stroke, stroke_fill=(12, 12, 14, 230))
    return img


def _smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _letter_sprites(txt, sz, col=(250, 248, 244, 255)):
    """Buchstaben einzeln (fuer Stagger-Animation), plus Gesamtbreite."""
    f = _font(sz)
    dummy = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    lets = []
    for i, ch in enumerate(txt):
        x_off = dummy.textlength(txt[:i], font=f)
        bb = dummy.textbbox((0, 0), ch, font=f)
        img = Image.new('RGBA', (max(bb[2] - bb[0] + 8, 4),
                                 max(bb[3] - bb[1] + 24, 4)), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((4 - bb[0], 12 - bb[1]), ch, font=f, fill=col)
        lets.append((x_off, bb[1], img))
    total = dummy.textlength(txt, font=f)
    return lets, total


def _soft_shadow(img, blur=7, alpha=110):
    """Weicher Schlagschatten aus der Alpha-Maske - liegt AUF der Szene."""
    from PIL import ImageFilter
    a = img.getchannel('A').point(lambda v: int(v * alpha / 255))
    sh = Image.new('RGBA', img.size, (8, 8, 10, 0))
    sh.putalpha(a)
    return sh.filter(ImageFilter.GaussianBlur(blur))


def _studio_shadow(img, blur, alpha, shrink=1.0):
    """Studio-Schatten MIT Padding: der Blur laeuft vollstaendig aus, nichts
    wird an der Sprite-Kante abgeschnitten (_soft_shadow clippt - sah 'abgehakt'
    aus). In halber Aufloesung gerechnet (Schatten hat keine Details)."""
    from PIL import ImageFilter
    pad = int(blur * 3)
    w = max(int(img.width * shrink), 2)
    h = max(int(img.height * shrink), 2)
    a = img.resize((w // 2, h // 2), Image.BILINEAR).getchannel('A')
    a = a.point(lambda v: int(v * alpha / 255))
    p2 = pad // 2
    m = Image.new('L', (w // 2 + 2 * p2, h // 2 + 2 * p2), 0)
    m.paste(a, (p2, p2))
    m = m.filter(ImageFilter.GaussianBlur(blur / 2))
    sh = Image.new('RGBA', m.size, (10, 11, 15, 0))
    sh.putalpha(m)
    return sh.resize((m.width * 2, m.height * 2), Image.BILINEAR)


# ---------------------------------------------------------------- Demo v2 (AE)
def render_demo2(input_video, out_video, progress=print):
    """AE-Look statt Sticker-Pack: (1) Kinetic-Type (Buchstaben-Stagger mit
    Blur-in + Rise, Hairline-Unterstrich), (2) grosser Text laeuft HINTER der
    Person durch (RVM-Matte pro Frame), (3) Zahl mit Hairline-Ring, (4) subtiler
    Zoom-Punch OHNE Weiss-Blitz. Alle Overlays KLEBEN im Raum (globales
    Kamera-Drift-Tracking via Phasenkorrelation), weiche Schlagschatten,
    Film-Grain auf der Grafik, gedeckte Farben (off-white statt Deko-Orange)."""
    if cv2 is None:
        return False
    from PIL import ImageFilter
    import onnxruntime as ort
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    off_w = (250, 248, 244, 255)

    # RVM fuer echte Occlusion (Text hinter der Person)
    try:
        sess = ort.InferenceSession(os.path.join(HERE, 'models/rvm.onnx'),
                                    providers=['CPUExecutionProvider'])
        rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
        dsr = np.array([0.25], np.float32)
    except Exception:
        sess = None

    # Momente
    T_KIN = (0.8, 2.6)          # Kinetic-Type "PREMIUM LOOK"
    T_BEH = (3.1, 6.0)          # "BEHIND" wandert hinter der Person durch
    T_NUM = (6.4, 8.2)          # "250%" mit Hairline-Ring
    T_PCH = (8.5, 9.3)          # subtiler Zoom-Punch

    kin_txt = 'PREMIUM LOOK'
    kin_sz = int(H * 0.045) * SS
    kin_lets, kin_w = _letter_sprites(kin_txt, kin_sz)
    beh_img = _text_sprite('BEHIND', int(H * 0.16) * SS,
                           (250, 248, 244, 235), stroke=0)
    num_img = _text_sprite('250%', int(H * 0.075) * SS, off_w, stroke=0)

    rng = np.random.default_rng(7)
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), fps, (W, H))
    prev_small = None
    drift = np.zeros(2, np.float32)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps

        # --- globales Kamera-Drift (Overlays kleben im Raum, nicht am Screen)
        small = cv2.cvtColor(cv2.resize(frame, (320, 180)),
                             cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_small is not None:
            (dx, dy), _resp = cv2.phaseCorrelate(prev_small, small)
            drift += np.array([dx * W / 320.0, dy * H / 180.0], np.float32)
        prev_small = small
        ddx, ddy = int(round(-drift[0])), int(round(-drift[1]))

        # --- RVM-Matte (nur berechnet, waehrend/vor dem Behind-Fenster)
        matte = None
        if sess is not None and t < T_BEH[1] + 0.3:
            src = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            out = sess.run(None, {'src': src.transpose(2, 0, 1)[None],
                                  'r1i': rec[0], 'r2i': rec[1],
                                  'r3i': rec[2], 'r4i': rec[3],
                                  'downsample_ratio': dsr})
            rec = out[2:6]
            if T_BEH[0] <= t < T_BEH[1]:
                matte = np.clip(out[1][0, 0], 0.0, 1.0)[..., None]

        ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        used = False

        # (1) Kinetic-Type: Buchstaben-Stagger, Blur-in + Rise, Hairline drunter
        if T_KIN[0] <= t < T_KIN[1]:
            used = True
            k = (t - T_KIN[0]) / (T_KIN[1] - T_KIN[0])
            fade = 1.0 if k < 0.85 else max(0.0, 1.0 - (k - 0.85) / 0.15)
            x0 = (W * SS - kin_w) // 2 + ddx * SS
            y0 = int(H * 0.72) * SS + ddy * SS
            for li, (xo, _bt, lim) in enumerate(kin_lets):
                lp = min(max((t - T_KIN[0] - li * 0.045) / 0.32, 0.0), 1.0)
                if lp <= 0:
                    continue
                e = ease_out_quart(lp)
                let = lim
                if lp < 1.0:
                    let = lim.filter(ImageFilter.GaussianBlur((1 - e) * 5))
                a = let.getchannel('A').point(lambda v: int(v * e * fade))
                let = let.copy(); let.putalpha(a)
                ly = y0 + int((1 - e) * 16 * SS)
                ov.alpha_composite(_soft_shadow(let, 6, 90),
                                   (int(x0 + xo), ly + 4 * SS))
                ov.alpha_composite(let, (int(x0 + xo), ly))
            up = _smoothstep((t - T_KIN[0] - 0.45) / 0.5)
            if up > 0:
                yl = y0 + kin_lets[0][2].height + 2 * SS
                cxl = x0 + kin_w / 2
                half = kin_w / 2 * up
                d.line([(cxl - half, yl), (cxl + half, yl)],
                       fill=(250, 248, 244, int(215 * fade)), width=2 * SS)

        # (3) Zahl mit Hairline-Ring, klebt im Raum
        if T_NUM[0] <= t < T_NUM[1]:
            used = True
            k = (t - T_NUM[0]) / (T_NUM[1] - T_NUM[0])
            fade = 1.0 if k < 0.85 else max(0.0, 1.0 - (k - 0.85) / 0.15)
            e = ease_out_quart(min((t - T_NUM[0]) / 0.3, 1.0))
            nx = (W * SS - num_img.width) // 2 + ddx * SS
            ny = int(H * 0.68) * SS + ddy * SS
            ni = num_img
            a = ni.getchannel('A').point(lambda v: int(v * e * fade))
            ni = ni.copy(); ni.putalpha(a)
            ov.alpha_composite(_soft_shadow(ni, 7, 100), (nx, ny + 5 * SS))
            ov.alpha_composite(ni, (nx, ny))
            rp = _smoothstep((t - T_NUM[0] - 0.18) / 0.5)
            if rp > 0:
                pad = num_img.width * 0.14
                box = (nx - pad, ny - pad * 0.7,
                       nx + num_img.width + pad, ny + num_img.height + pad * 0.4)
                d.arc(box, -80, -80 + 372 * rp,
                      fill=(250, 248, 244, int(230 * fade)), width=int(2.5 * SS))

        # (2) Text HINTER der Person: langsamer Lauf + echte Occlusion
        beh_layer = None
        if T_BEH[0] <= t < T_BEH[1] and matte is not None:
            used = True
            k = (t - T_BEH[0]) / (T_BEH[1] - T_BEH[0])
            fade = min(k / 0.10, 1.0) * (1.0 if k < 0.88 else
                                         max(0.0, 1.0 - (k - 0.88) / 0.12))
            trav = _smoothstep(k)
            bx = int(W * SS * (0.58 - 0.28 * trav)) - beh_img.width // 2 \
                + int(ddx * SS * 1.12)
            by = int(H * 0.30) * SS + ddy * SS
            bl = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            bi = beh_img.copy()
            a = bi.getchannel('A').point(lambda v: int(v * fade))
            bi.putalpha(a)
            bl.alpha_composite(bi, (bx, by))
            beh_layer = bl

        if used or beh_layer is not None:
            base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) \
                .convert('RGBA')
            if beh_layer is not None:
                comp = base.copy()
                comp.alpha_composite(beh_layer.resize((W, H), Image.LANCZOS))
                cn = np.array(comp.convert('RGB')).astype(np.float32)
                bn = np.array(base.convert('RGB')).astype(np.float32)
                merged = cn * (1 - matte) + bn * matte      # Person bleibt VORN
                base = Image.fromarray(merged.astype(np.uint8)).convert('RGBA')
            sm = ov.resize((W, H), Image.LANCZOS)
            # Film-Grain nur auf der Grafik (Material-Match)
            sa = np.array(sm)
            if sa[..., 3].any():
                noise = rng.normal(0, 5, sa.shape[:2])[..., None]
                sa[..., :3] = np.clip(sa[..., :3].astype(np.float32)
                                      + noise * (sa[..., 3:4] / 255.0),
                                      0, 255).astype(np.uint8)
                sm = Image.fromarray(sa)
            base.alpha_composite(sm)
            frame = cv2.cvtColor(np.array(base.convert('RGB')), cv2.COLOR_RGB2BGR)

        # (4) subtiler Zoom-Punch: Spring-Scale + Richtungs-Blur, KEIN Blitz
        if T_PCH[0] <= t < T_PCH[1]:
            k = (t - T_PCH[0]) / (T_PCH[1] - T_PCH[0])
            sc = 1.0 + 0.05 * math.sin(min(k / 0.55, 1.0) * math.pi) \
                * (1.0 - k * 0.5)
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, sc)
            frame = cv2.warpAffine(frame, M, (W, H),
                                   borderMode=cv2.BORDER_REFLECT)
            if k < 0.35:                       # Motion-Blur nur am Anschlag
                frame = cv2.blur(frame, (1, 5))
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp,
                        '-i', input_video, '-map', '0:v:0', '-map', '1:a:0?',
                        '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-shortest', out_video],
                       check=True, timeout=300)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    progress('AE-Demo v2 fertig')
    return True


# ---------------------------------------------------------------- Demo-Render
def render_demo(input_video, out_video, accent=(255, 122, 26), progress=print):
    """Demo: 4 Motion-Graphics + 1 lokaler VFX auf echtem Material. Jeder Moment
    ~1.6s: Text steht, Grafik zeichnet sich in 0.45s, haelt, blendet weich aus."""
    if cv2 is None:
        return False
    import vfx_engine as VE
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ac = (accent[0], accent[1], accent[2], 255)
    white = (250, 248, 244, 255)

    # Momente: (t0, dauer, art, text)
    MOM = [(0.8, 2.0, 'underline', 'PREMIUM LOOK'),
           (3.0, 2.0, 'circle', '250%'),
           (5.2, 1.8, 'box', 'MOTION'),
           (7.0, 1.6, 'burst', 'BOOM')]
    sz = int(H * 0.055)
    ty = int(H * 0.70)

    sprites = {}
    for _, _, art, txt in MOM:
        col = (16, 16, 18, 255) if art == 'box' else white
        sprites[art] = _text_sprite(txt, sz * SS,
                                    col if art != 'circle' else white,
                                    stroke=0 if art == 'box' else 3 * SS)

    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), fps, (W, H))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        ov = None
        for (t0, du, art, txt) in MOM:
            if not (t0 <= t < t0 + du):
                continue
            k = (t - t0) / du
            draw_p = min((t - t0) / 0.45, 1.0)          # Zeichnen in 450ms
            fade = 1.0 if k < 0.82 else max(0.0, 1.0 - (k - 0.82) / 0.18)
            ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            sp = sprites[art]
            tx = (W * SS - sp.width) // 2
            tyy = ty * SS
            bbox = (tx, tyy, tx + sp.width, tyy + sp.height)
            if art == 'box':
                gfx_box(d, bbox, draw_p, (ac[0], ac[1], ac[2], int(255 * fade)))
            # Text (bei box NACH der Box)
            txt_img = sp
            if fade < 1.0:
                txt_img = sp.copy()
                txt_img.putalpha(txt_img.getchannel('A').point(
                    lambda a: int(a * fade)))
            # Text erst ab leichtem Einflug (Pop)
            tp = min((t - t0) / 0.28, 1.0)
            scl = 0.9 + 0.1 * ease_spring(tp, 0.08)
            si = txt_img.resize((max(int(sp.width * scl), 1),
                                 max(int(sp.height * scl), 1)))
            ov.alpha_composite(si, ((W * SS - si.width) // 2,
                                    tyy - (si.height - sp.height) // 2))
            gcol = (ac[0], ac[1], ac[2], int(255 * fade))
            if art == 'underline':
                gfx_underline(d, bbox[0] - 6 * SS, bbox[2] + 6 * SS,
                              bbox[3] + 14 * SS, draw_p, gcol, 6 * SS)
            elif art == 'circle':
                gfx_circle(d, bbox, draw_p, gcol, 5 * SS)
            elif art == 'burst':
                gfx_burst(d, W * SS // 2, tyy - 8 * SS, k,
                          ac, W * SS * 0.16)
            break
        if ov is not None:
            small = ov.resize((W, H), Image.LANCZOS)
            base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) \
                .convert('RGBA')
            base.alpha_composite(small)
            frame = cv2.cvtColor(np.array(base.convert('RGB')),
                                 cv2.COLOR_RGB2BGR)
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    # lokaler VFX-Moment obendrauf (zoom-punch/shock) via vfx_engine
    mid = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp,
                        '-i', input_video, '-map', '0:v:0', '-map', '1:a:0?',
                        '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-shortest', mid], check=True, timeout=300)
        okv = VE.render_moment_vfx(mid, out_video, t0=8.6, dauer=0.55,
                                   kind='shock', caption='IMPACT',
                                   progress=progress)
    finally:
        for p in (tmp, mid):
            try:
                os.remove(p)
            except OSError:
                pass
    progress('Motion-Graphics-Demo fertig')
    return bool(okv)


def _ease_over(t, over=1.10):
    """Snap-in mit Overshoot + Settle (die Kern-Kurve fuer teuren Look):
    schnell auf 'over', federt auf 1.0. t in 0..1."""
    t = min(max(t, 0.0), 1.0)
    e = 1.0 - (1.0 - t) ** 3                     # ease-out-cubic (snap)
    return 1.0 + (over - 1.0) * math.sin(min(t / 0.62, 1.0) * math.pi) * (1.0 - t * 0.35) \
        if t < 1.0 else 1.0


def _word_img(txt, font, col, stroke, stroke_col=(8, 8, 10, 255)):
    dummy = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    bb = dummy.textbbox((0, 0), txt, font=font, stroke_width=stroke)
    pad = stroke + 10
    img = Image.new('RGBA', (bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2),
                    (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad - bb[0], pad - bb[1]), txt, font=font,
                             fill=col, stroke_width=stroke, stroke_fill=stroke_col)
    return img


def render_demo3(input_video, out_video, progress=print):
    """Der ECHTE High-End-Short-Form-Standard (Recherche 2026): wort-fuer-Wort
    synchron, Inter-Black all-caps mit schwarzem Outline, EIN Keyword gelb, das
    aktive Wort bekommt einen Scale-Bump. Timing macht den teuren Look:
    Snap-in mit Overshoot+Settle (~140ms), Motion-Blur nur am Anschlag, kurze
    Stille zwischen Phrasen, dezenter Drop-Shadow. Restraint statt Deko."""
    if cv2 is None:
        return False
    from PIL import ImageFilter
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    YEL = (247, 194, 4, 255)
    WHT = (252, 252, 250, 255)
    sz = int(H * 0.058) * SS
    try:
        font = ImageFont.truetype(os.path.join(HERE, 'fonts', 'inter_black.ttf'), sz)
    except Exception:
        font = _font(sz)
    stroke = max(int(sz * 0.11), 3)

    # Phrasen (Wort, start, dauer_bis_naechstes, keyword?) - wie ein echter
    # Talking-Head-Rhythmus. In echt kommt das aus dem Whisper-Wort-Timing.
    PHRASES = [
        [('THIS', 0.6), ('CHANGES', 0.95), ('EVERYTHING', 1.35, True)],
        [('WATCH', 2.7), ('HOW', 3.0), ('FAST', 3.35, True), ('IT', 3.75), ('MOVES', 3.95)],
        [('NOBODY', 5.2), ('EDITS', 5.6), ('LIKE', 5.95), ('THIS', 6.2, True)],
        [('THATS', 7.4), ('THE', 7.7), ('DIFFERENCE', 8.0, True)],
    ]
    # jedes Wort vorab rendern (weiss + gelb Variante)
    cache = {}
    for ph in PHRASES:
        for w in ph:
            t = w[0]
            key = len(w) > 2 and w[2]
            cache[(t, False)] = _word_img(t, font, WHT, stroke)
            if key:
                cache[(t, True)] = _word_img(t, font, YEL, stroke)

    def phrase_end(ph):
        return ph[-1][1] + 1.0                    # letztes Wort haelt ~1s

    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), fps, (W, H))
    i = 0
    gap = int(W * 0.018)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        # aktive Phrase finden
        ph = None
        for p in PHRASES:
            if p[0][1] - 0.12 <= t < phrase_end(p) + 0.25:
                ph = p
                break
        if ph is not None:
            pe = phrase_end(ph)
            p_out = 1.0 if t < pe else max(0.0, 1.0 - (t - pe) / 0.25)   # Phrase blendet weich aus
            vis = [w for w in ph if t >= w[1] - 0.02]
            if vis:
                # Layout: eine zentrierte Zeile, bei Bedarf 2 Zeilen
                items = []
                for w in vis:
                    key = len(w) > 2 and w[2]
                    img = cache[(w[0], bool(key))]
                    ap_t = (t - w[1]) / 0.14                     # 140ms Pop
                    sc = _ease_over(ap_t, 1.12) if ap_t < 1 else 1.0
                    items.append((w, img, sc, ap_t))
                # Zeilen umbrechen (max ~92% Breite)
                maxw = W * SS * 0.92
                lines, cur, cw = [], [], 0
                for it in items:
                    iw = it[1].width * (it[2] if it[2] > 1 else 1.0)
                    if cur and cw + iw + gap * SS > maxw:
                        lines.append((cur, cw)); cur, cw = [], 0
                    cur.append(it); cw += iw + gap * SS
                if cur:
                    lines.append((cur, cw))
                ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
                line_h = int(sz * 1.18)
                total_h = line_h * len(lines)
                y = int(H * 0.70) * SS - total_h // 2
                for (ln, lw) in lines:
                    x = int(W * SS - (lw - gap * SS)) // 2
                    for (w, img, sc, ap_t) in ln:
                        iw = img.width
                        sw, sh = max(int(iw * sc), 1), max(int(img.height * sc), 1)
                        wi = img.resize((sw, sh), Image.LANCZOS)
                        # Motion-Blur nur am Anschlag (erste ~40ms)
                        if 0 <= ap_t < 0.3:
                            wi = wi.filter(ImageFilter.GaussianBlur((0.3 - ap_t) * 9))
                        op = min(max(ap_t / 0.5, 0.0), 1.0) * p_out
                        yr = int((1 - min(ap_t, 1.0)) * 14 * SS) if ap_t < 1 else 0
                        if op < 1.0:
                            a2 = wi.getchannel('A').point(lambda v: int(v * op))
                            wi = wi.copy(); wi.putalpha(a2)
                        # Drop-Shadow
                        sh_im = _soft_shadow(wi, 8, 120)
                        cxw = x + iw // 2
                        px = int(cxw - sw // 2)
                        py = int(y + (line_h - sh) // 2 + yr)
                        ov.alpha_composite(sh_im, (px, py + 5 * SS))
                        ov.alpha_composite(wi, (px, py))
                        x += iw + gap * SS
                    y += line_h
                base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert('RGBA')
                base.alpha_composite(ov.resize((W, H), Image.LANCZOS))
                frame = cv2.cvtColor(np.array(base.convert('RGB')), cv2.COLOR_RGB2BGR)
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-i', input_video,
                        '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'libx264',
                        '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-shortest', out_video], check=True, timeout=300)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    progress('Standard-Demo v3 fertig')
    return True


def _scene_accent(frame):
    """Akzentfarbe AUS der Szene: der saturierteste helle Farbton -> so gehoert
    der Text ins Bild (amber-Lampe -> amber, gruener Scope -> gruen)."""
    small = cv2.resize(frame, (64, 114))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    score = (hsv[:, 1] / 255.0) * (hsv[:, 2] / 255.0) ** 0.6
    k = int(np.argmax(score))
    h = hsv[k, 0]
    # kraeftige, gehobene Version des Szenen-Farbtons
    pick = cv2.cvtColor(np.uint8([[[h, 210, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
    if float(score[k]) < 0.18:                     # kaum Farbe -> warmes Off-White
        return (245, 238, 225)
    return (int(pick[2]), int(pick[1]), int(pick[0]))   # RGB


def render_editorial(input_video, out_video, progress=print):
    """PROTOTYP Editorial-Look (wie die 2 Referenzvideos): neutrale schwere Sans
    (Inter-Black), gestapelte Groessen-Hierarchie links, das Hero-Wort riesig +
    Szenen-Farbe + Glow, ganze Typo HINTER der Person durchgewebt (RVM-Matte),
    weiches Blur-in statt Bounce. Kein Outline-Balken, kein Deko. Restraint."""
    if cv2 is None:
        return False
    from PIL import ImageFilter
    import onnxruntime as ort
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    try:
        sess = ort.InferenceSession(os.path.join(HERE, 'models/rvm.onnx'),
                                    providers=['CPUExecutionProvider'])
        rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
        dsr = np.array([0.25], np.float32)
    except Exception:
        sess = None
    fp = os.path.join(HERE, 'fonts', 'inter_black.ttf')

    def F(px):
        try:
            return ImageFont.truetype(fp, int(px))
        except Exception:
            return _font(int(px))
    sz_h = int(H * 0.118) * SS          # Hero-Wort
    sz_n = int(H * 0.050) * SS          # Neben-Woerter
    # (Wort, start, hero?) - in echt aus Whisper-Timing
    PHRASES = [
        [('this', 0.6, 0), ('is', 0.95, 0), ('the', 1.15, 0), ('DIFFERENCE', 1.45, 1)],
        [('watch', 3.1, 0), ('how', 3.4, 0), ('it', 3.7, 0), ('MOVES', 3.95, 1)],
        [('nobody', 5.4, 0), ('edits', 5.8, 0), ('like', 6.15, 0), ('THIS', 6.45, 1)],
        [('thats', 7.6, 0), ('the', 7.9, 0), ('SECRET', 8.2, 1)],
    ]
    off_w = (244, 240, 232, 255)
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), fps, (W, H))
    accent = (245, 238, 225)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        if i % 6 == 0:                              # Farbe selten neu picken (stabil)
            accent = _scene_accent(frame)

        ph = None
        for p in PHRASES:
            if p[0][1] - 0.15 <= t < p[-1][1] + 1.5:
                ph = p
                break

        matte = None
        if sess is not None:
            src = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            out = sess.run(None, {'src': src.transpose(2, 0, 1)[None], 'r1i': rec[0],
                                  'r2i': rec[1], 'r3i': rec[2], 'r4i': rec[3],
                                  'downsample_ratio': dsr})
            rec = out[2:6]
            if ph is not None:
                matte = np.clip(out[1][0, 0], 0.0, 1.0)[..., None]

        if ph is not None:
            pe = ph[-1][1] + 1.5
            p_out = 1.0 if t < pe - 0.35 else max(0.0, (pe - t) / 0.35)
            vis = [w for w in ph if t >= w[1] - 0.02]
            txt_layer = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            glow_layer = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            # gestapelt links, vertikal um die obere Bildmitte
            heights = [sz_h if w[2] else sz_n for w in vis]
            gap = int(sz_n * 0.34)
            total = sum(int(h * 1.02) for h in heights) + gap * max(len(vis) - 1, 0)
            x = int(W * 0.06) * SS
            y = int(H * 0.30) * SS
            for (w, hgt) in zip(vis, heights):
                word, ws, hero = w
                col = (accent[0], accent[1], accent[2], 255) if hero else off_w
                wi = _word_img(word.upper() if hero else word, F(hgt), col,
                               stroke=0, stroke_col=(0, 0, 0, 0))
                ap_t = min(max((t - ws) / 0.30, 0.0), 1.0)     # 300ms weiches Ein
                e = _smoothstep(ap_t)
                op = e * p_out
                if op <= 0:
                    y += int(hgt * 1.02) + gap
                    continue
                cur = wi
                if ap_t < 1.0:                                  # Blur-in
                    cur = wi.filter(ImageFilter.GaussianBlur((1 - e) * 7))
                a = cur.getchannel('A').point(lambda v: int(v * op))
                cur = cur.copy(); cur.putalpha(a)
                yr = int((1 - e) * 10 * SS)
                px, py = x, y + yr
                # weicher Schatten fuer Tiefe (dezent)
                txt_layer.alpha_composite(_soft_shadow(cur, 9, 90), (px, py + 5 * SS))
                if hero:                                        # Glow in Szenenfarbe
                    g = Image.new('RGBA', cur.size, (0, 0, 0, 0))
                    ga = cur.getchannel('A')
                    g.paste((accent[0], accent[1], accent[2], int(190 * op)), (0, 0), ga)
                    g = g.filter(ImageFilter.GaussianBlur(16))
                    glow_layer.alpha_composite(g, (px, py))
                txt_layer.alpha_composite(cur, (px, py))
                y += int(hgt * 1.02) + gap

            base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert('RGBA')
            base.alpha_composite(glow_layer.resize((W, H), Image.LANCZOS))
            base.alpha_composite(txt_layer.resize((W, H), Image.LANCZOS))
            comp = np.array(base.convert('RGB')).astype(np.float32)
            if matte is not None:                               # Person kommt VORN
                bn = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32)
                comp = comp * (1 - matte) + bn * matte
            frame = cv2.cvtColor(comp.astype(np.uint8), cv2.COLOR_RGB2BGR)
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-i', input_video,
                        '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'libx264',
                        '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-shortest', out_video], check=True, timeout=300)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    progress('Editorial-Prototyp fertig')
    return True


def render_stackbuild(input_video, out_video, progress=print):
    """PROTOTYP der EFFEKTE aus den 2 Referenzvideos (@migs.visuals /
    @johnbucog_) - NICHT der Text, den macht die KI-Regie. Reine Typo-
    Choreografie:
      1. Aufbau-Stack: Woerter stapeln sich Wort fuer Wort, ersetzen sich NICHT.
      2. Hierarchie inline: kleine Verbinder = mittlere Sans; KEYWORD = gross,
         fett, GROSSBUCHSTABEN, weisser Glow; Akzent = kursive Serif, warmes Gold.
      3. Keyword-Reveal = Schreibmaschine (Buchstabe fuer Buchstabe, ~0.16s),
         volle Breite reserviert -> kein Layout-Zittern.
      4. Verbinder/Akzent = weicher Pop-in (Scale + Fade).
      5. Weicher Schatten fuer Lesbarkeit, dezenter Glow auf Hervorhebung.
    Text bleibt im oberen Drittel VOR der Person (migs-Look)."""
    if cv2 is None:
        return False
    from PIL import ImageFilter
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fdir = os.path.join(HERE, 'fonts')

    def FF(name, px):
        try:
            return ImageFont.truetype(os.path.join(fdir, name), int(px))
        except Exception:
            return _font(int(px))
    sz_n = int(H * 0.049) * SS           # Verbinder
    sz_h = int(H * 0.076) * SS           # Keyword (GROSS)
    sz_a = int(H * 0.058) * SS           # Kursiv-Akzent
    F_N = lambda: FF('poppins_b.ttf', sz_n)
    F_H = lambda: FF('inter_black.ttf', sz_h)
    F_A = lambda: FF('playfair_i.ttf', sz_a)
    COL_N = (250, 248, 245, 255)
    COL_H = (255, 255, 255, 255)
    COL_A = (255, 189, 74, 255)          # warmes Gold
    # (Wort, dt, art) art: 'n' normal | 'H' hero-keyword | 'a' kursiv-akzent
    # In echt kommt das aus Whisper-Timing + KI-Regie (Keyword/Akzent-Wahl).
    SENT = [
        (0.5, [('why', 0.0, 'n'), ('do', 0.22, 'n'), ('most', 0.44, 'n'),
               ('EDITS', 0.70, 'H'), ('feel', 1.20, 'n'), ('cheap', 1.45, 'a')]),
        (4.2, [('its', 0.0, 'n'), ('not', 0.22, 'n'), ('the', 0.40, 'n'),
               ('CAMERA', 0.62, 'H'), ('its', 1.15, 'n'), ('the', 1.33, 'n'),
               ('details', 1.55, 'a')]),
        (7.9, [('this', 0.0, 'n'), ('is', 0.22, 'n'), ('what', 0.40, 'n'),
               ('PREMIUM', 0.64, 'H'), ('feels', 1.20, 'n'), ('like', 1.42, 'a')]),
    ]
    HOLD = 1.0                           # Satz haelt nach letztem Wort
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), fps, (W, H))

    def measure(txt, font):
        l, t, r, b = font.getbbox(txt if txt else 'X')
        asc, desc = font.getmetrics()
        return (r - l), asc, desc, l

    def sprite(txt, font, col, box_w=None):
        w_full, asc, desc, lbear = measure(txt if txt else 'X', font)
        w = box_w if box_w is not None else w_full
        im = Image.new('RGBA', (max(w, 1) + 8, asc + desc + 8), (0, 0, 0, 0))
        if txt:
            ImageDraw.Draw(im).text((4 - lbear, 4), txt, font=font, fill=col)
        return im, asc

    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        sent = None
        for s0, words in SENT:
            if s0 - 0.12 <= t < s0 + words[-1][1] + HOLD + 0.45:
                sent = (s0, words)
                break
        if sent is not None:
            s0, words = sent
            t_end = s0 + words[-1][1] + HOLD
            s_out = 1.0 if t < t_end else max(0.0, (t_end + 0.35 - t) / 0.35)
            fonts = {'n': F_N(), 'H': F_H(), 'a': F_A()}
            cols = {'n': COL_N, 'H': COL_H, 'a': COL_A}
            # --- Layout: inline-Fluss mit Umbruch, Grundlinie ausgerichtet ---
            max_w = int(W * 0.88) * SS
            x0 = int(W * 0.06) * SS
            space = int(W * 0.020) * SS
            items = []
            for (word, dt, art) in words:
                ws = s0 + dt
                if t < ws - 0.02:
                    continue
                fnt = fonts[art]
                disp = word.upper() if art == 'H' else word
                full_w, asc, desc, _ = measure(disp, fnt)
                items.append((word, disp, art, ws, fnt, full_w, asc, desc))
            # in Zeilen brechen (volle Breite je Wort -> stabil)
            lines = []
            cur = []
            cur_w = 0
            for it in items:
                ww = it[5]
                if cur and cur_w + space + ww > max_w:
                    lines.append(cur)
                    cur = []
                    cur_w = 0
                cur.append(it)
                cur_w += (space if len(cur) > 1 else 0) + ww
            if cur:
                lines.append(cur)
            txt_layer = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            glow_layer = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
            y = int(H * 0.11) * SS
            for line in lines:
                l_asc = max(it[6] for it in line)
                l_desc = max(it[7] for it in line)
                baseline = y + l_asc
                x = x0
                for (word, disp, art, ws, fnt, full_w, asc, desc) in line:
                    col = cols[art]
                    # Reveal-Fortschritt
                    if art == 'H':                       # Schreibmaschine
                        pr = min(max((t - ws) / 0.16, 0.0), 1.0)
                        n = max(1, int(math.ceil(pr * len(disp)))) if pr > 0 else 0
                        shown = disp[:n]
                        op = min(max((t - ws) / 0.08, 0.0), 1.0) * s_out
                        spr, sasc = sprite(shown, fnt, col, box_w=full_w)
                        scale = 1.0
                    else:                                # weicher Pop-in
                        e = _smoothstep(min(max((t - ws) / 0.14, 0.0), 1.0))
                        op = e * s_out
                        spr, sasc = sprite(disp, fnt, col)
                        scale = 0.86 + 0.14 * e
                    if op <= 0.01:
                        x += full_w + space
                        continue
                    if scale != 1.0:
                        nw = max(1, int(spr.width * scale))
                        nh = max(1, int(spr.height * scale))
                        spr = spr.resize((nw, nh), Image.LANCZOS)
                        sasc = int(sasc * scale)
                    a = spr.getchannel('A').point(lambda v: int(v * op))
                    spr = spr.copy()
                    spr.putalpha(a)
                    px = x
                    py = baseline - sasc - 4
                    if art in ('H', 'a'):                # Glow auf Hervorhebung
                        gcol = (255, 255, 255) if art == 'H' else (255, 176, 66)
                        g = Image.new('RGBA', spr.size, (0, 0, 0, 0))
                        g.paste(gcol + (int(150 * op),), (0, 0), spr.getchannel('A'))
                        g = g.filter(ImageFilter.GaussianBlur(13))
                        glow_layer.alpha_composite(g, (px, py))
                    txt_layer.alpha_composite(spr, (px, py))
                    x += full_w + space
                y = baseline + l_desc + int(sz_n * 0.30)
            # weicher Schatten aus der ganzen Text-Ebene (Lesbarkeit)
            shadow = _soft_shadow(txt_layer, blur=10, alpha=120)
            base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert('RGBA')
            base.alpha_composite(shadow.resize((W, H), Image.LANCZOS), (0, 3))
            base.alpha_composite(glow_layer.resize((W, H), Image.LANCZOS))
            base.alpha_composite(txt_layer.resize((W, H), Image.LANCZOS))
            frame = cv2.cvtColor(np.array(base.convert('RGB')), cv2.COLOR_RGB2BGR)
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    try:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-i', input_video,
                        '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'libx264',
                        '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-shortest', out_video], check=True, timeout=300)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    progress('Stack-Build-Prototyp fertig')
    return True


def _elastic(t):
    """Elastic-Ease nach der Referenz-Kurve (@dav6cious-Kommentar): schneller
    Anstieg, ~18% Overshoot bei ~340ms, weiches Zurueckfedern, Settle ~1s.
    Gedaempfte Feder: f(t) = 1 - e^(-5t)(cos(9.2t) + (5/9.2)sin(9.2t))."""
    if t <= 0:
        return 0.0
    if t >= 1.6:
        return 1.0
    return 1.0 - math.exp(-5.0 * t) * (math.cos(9.2 * t)
                                       + (5.0 / 9.2) * math.sin(9.2 * t))


def render_ui_motion(out_video, progress=print):
    """PROTOTYP 'UI-Motion' (Stil @dav6cious/refined.motion/mcvisuals):
    Apple-Style UI-Motion-Graphics - Pill-Stack mit Typewriter auf weichem
    Studio-Verlauf, Elastic-Overshoot (gemessene Kurve), permanenter
    Kamera-Glide, Stagger-Push, Geschwindigkeits-Blur. Sound: NUR echte
    Pack-Sounds - whoosh_soft ~60ms VOR dem Motion-Peak, press auf der
    Landung, sparsam (~1 SFX / 1.2s). 60fps."""
    from PIL import ImageFilter
    W, H, FPS = 1080, 1920, 60
    DUR = 10.5
    N = int(DUR * FPS)
    fdir = os.path.join(HERE, 'fonts')

    def F(name, px):
        try:
            return ImageFont.truetype(os.path.join(fdir, name), int(px))
        except Exception:
            return _font(int(px))

    # --- Studio-Hintergrund: sehr heller Vertikal-Verlauf + Vignette ---
    top = np.array([246, 247, 250], np.float32)
    bot = np.array([225, 231, 240], np.float32)
    gy = np.linspace(0, 1, H)[:, None, None]
    bg = (top[None, None, :] * (1 - gy) + bot[None, None, :] * gy)
    xx, yy = np.meshgrid(np.linspace(-1, 1, W), np.linspace(-1, 1, H))
    vig = 1.0 - 0.10 * np.clip(xx ** 2 + yy ** 2 * 0.6, 0, 1)[..., None]
    BG = Image.fromarray(np.clip(bg * vig, 0, 255).astype(np.uint8)).convert('RGBA')

    ACC = (255, 122, 26)                     # Akzent (DouchkoVE-Orange)

    def rounded_card(w, h, r, fill=(255, 255, 255, 255)):
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=fill)
        return im

    def pill_sprite(txt, n_chars, acc_last=3):
        """Kapsel mit Typewriter-Stand (n_chars sichtbar), letzte Buchstaben
        in Akzentfarbe (wie 'Write'/'Solve' in der Referenz). 2x gerendert."""
        S2 = 2
        f = F('poppins_b.ttf', 96 * S2)
        d0 = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        full_w = d0.textlength(txt, font=f)
        pw = int(full_w + 200 * S2)
        ph = int(230 * S2)
        im = rounded_card(pw, ph, ph // 2)
        d = ImageDraw.Draw(im)
        x = 100 * S2
        asc, desc = f.getmetrics()
        y = (ph - asc - desc) // 2
        for k, ch in enumerate(txt[:max(int(n_chars), 0)]):
            col = ACC if k >= len(txt) - acc_last else (26, 28, 34)
            d.text((x, y), ch, font=f, fill=col + (255,))
            x += d0.textlength(ch, font=f)
        return im.resize((pw // S2, ph // S2), Image.LANCZOS)

    def logo_sprite(sz):
        """Logo-Karte: weisses Rounded-Square, orangenes Play-Dreieck."""
        S2 = 2
        s = sz * S2
        im = rounded_card(s, s, int(s * 0.24))
        d = ImageDraw.Draw(im)
        c, r = s / 2, s * 0.20
        d.polygon([(c - r * 0.7, c - r), (c - r * 0.7, c + r), (c + r * 1.1, c)],
                  fill=ACC + (255,))
        return im.resize((sz, sz), Image.LANCZOS)

    def wordmark_sprite(n_chars):
        S2 = 2
        f = F('inter_black.ttf', 120 * S2)
        txt = 'DouchkoVE'
        d0 = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        w = int(d0.textlength(txt, font=f)) + 20
        asc, desc = f.getmetrics()
        im = Image.new('RGBA', (w, asc + desc), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = 0
        for k, ch in enumerate(txt[:max(int(n_chars), 0)]):
            col = ACC if k >= 7 else (26, 28, 34)     # 'VE' in Akzent
            d.text((x, 0), ch, font=f, fill=col + (255,))
            x += d0.textlength(ch, font=f)
        return im.resize((im.width // S2, im.height // S2), Image.LANCZOS)

    def put(canvas, spr, cx, cy, scale=1.0, op=1.0, vblur=0.0, rot=0.0,
            lift=1.0):
        """Sprite mit Studio-Schatten, Scale, Opacity, Geschw.-Blur, Rotation.
        lift = Hoehe ueber Grund (1=aufliegend): je hoeher, desto weiter/weicher
        faellt der Ambient-Schatten (die Referenz-Karten 'schweben')."""
        if op <= 0.01 or scale <= 0.01:
            return
        w = max(int(spr.width * scale), 1)
        h = max(int(spr.height * scale), 1)
        s = spr.resize((w, h), Image.LANCZOS)
        if abs(rot) > 0.15:
            s = s.rotate(rot, resample=Image.BICUBIC, expand=True)
        if vblur > 0.3:
            s = s.filter(ImageFilter.GaussianBlur(min(vblur, 6.0)))
        if op < 1.0:
            a = s.getchannel('A').point(lambda v: int(v * op))
            s = s.copy(); s.putalpha(a)
        # Zweischichtiger Schatten, Offset nach Lichtrichtung (oben-links).
        amb = _studio_shadow(s, blur=int(30 * lift), alpha=int(40 * op),
                             shrink=0.99)
        canvas.alpha_composite(amb, (int(cx - amb.width / 2 + 6 * lift),
                                     int(cy - amb.height / 2 + 26 * lift)))
        con = _studio_shadow(s, blur=9, alpha=int(50 * op), shrink=0.97)
        canvas.alpha_composite(con, (int(cx - con.width / 2 + 2),
                                     int(cy - con.height / 2 + 9 * lift)))
        canvas.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2)))

    PILLS = [('Write', 2.30), ('Create', 4.10), ('Solve', 5.90)]
    T_LOGO, T_UP, T_EXIT, T_WM = 0.45, 1.70, 7.60, 8.30
    PH = 230                                  # Pill-Hoehe (Sprite nach /2)
    GAP = 26
    # (Akzent-Zeit, Slot, Gain): Akzent = wo der SOUND-PEAK sitzen soll.
    # Gemessen an der Referenz: Sound-Peak ~40ms vor dem Motion-Peak; der
    # Motion-Peak der Elastic-Kurve liegt ~340ms nach Start (erster Overshoot).
    events = []
    events.append((T_LOGO + 0.28, 'whoosh_soft', 0.60))
    events.append((T_LOGO + 0.36, 'press', 0.30))
    events.append((T_UP + 0.25, 'whoosh_soft', 0.35))
    for _, ts in PILLS:
        events.append((ts + 0.28, 'whoosh_soft', 0.55))
        events.append((ts + 0.36, 'press', 0.26))
    events.append((T_EXIT + 0.12, 'vanish', 0.50))
    events.append((T_WM + 0.28, 'whoosh_soft', 0.60))
    events.append((T_WM + 0.36, 'impact', 0.32))

    logo_big = logo_sprite(360)
    logo_small = logo_sprite(180)
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (W, H))
    prev_e = {}
    def vel(key, e):
        v = abs(e - prev_e.get(key, e)) * FPS
        prev_e[key] = e
        return v

    def idle(phase, amp=1.0):
        """Ruhende Karten schweben permanent (nie ganz still) - langsames Bob
        + Mikro-Neigung, pro Element phasenversetzt."""
        fy = 7.0 * amp * math.sin(t * 1.35 + phase)
        fr_ = 0.9 * amp * math.sin(t * 1.05 + phase * 1.7)
        return fy, fr_

    for i in range(N):
        t = i / FPS
        fr = BG.copy()
        # Kamera: kraeftigerer, organischer Glide + langsamer Push-in-Zyklus.
        # cshift wird pro Ebene mit einem Tiefen-Faktor multipliziert (Parallax):
        # ferne Ebenen bewegen sich weniger, nahe mehr.
        cx0 = 26 * math.sin(t * 0.55) + 10 * math.sin(t * 1.3 + 1.0)
        cy0 = 18 * math.cos(t * 0.4) + 7 * math.sin(t * 0.9)
        gs = 1.0 + 0.05 * _smoothstep((math.sin(t * 0.5 - 1.2) + 1) / 2) + 0.02

        def cam(depth):
            """depth 0=fern (Hintergrund) .. 1.4=nah (Vordergrund)."""
            return cx0 * depth, cy0 * depth

        # --- Logo: elastisch rein mit Rotations-Overshoot, dann hoch-morphen ---
        if t < T_EXIT:
            e_in = _elastic(t - T_LOGO)
            e_up = _elastic(t - T_UP)
            pdx, pdy = cam(0.7)
            lx = W / 2 + pdx
            ly = H * 0.40 - e_up * H * 0.20 + pdy
            lsc = (0.15 + 0.85 * e_in) * (1.0 - 0.5 * e_up) * gs
            lrot = (1 - e_in) * -22 + (1 - e_up) * 10       # dreht sich ein
            fy, fr_ = idle(0.0, 0.7)
            lop = min(max((t - T_LOGO) / 0.12, 0), 1)
            if t > T_EXIT - 0.3:
                lop *= max(0.0, (T_EXIT - t) / 0.3)
            put(fr, logo_big, lx, ly + fy * (e_up < 0.1), lsc, lop,
                vblur=vel('lg', e_in + e_up) * 5, rot=lrot + fr_ * (e_in > 0.9),
                lift=1.15)
        # --- Pills: fliegen ABWECHSELND von den Seiten rein (Rotations-
        #     Overshoot), stapeln sich, schweben danach ---
        if t < T_EXIT + 0.4:
            base_y = H * 0.58
            for k, (txt, ts) in enumerate(PILLS):
                if t < ts:
                    continue
                e_in = _elastic(t - ts)
                side = -1 if k % 2 == 0 else 1
                pushes = sum(1 for _, t2 in PILLS[k + 1:] if t >= t2)
                y_target = base_y - pushes * (PH + GAP)
                yp = prev_e.get(f'y{k}', y_target)
                yp += 0.20 * (y_target - yp)                 # EMA-Feder
                prev_e[f'y{k}'] = yp
                n_ch = (t - ts) / 0.05
                spr = pill_sprite(txt, n_ch)
                ex = 1.0 if t < T_EXIT else max(0.0, 1.0 - (t - T_EXIT - k * 0.07) / 0.28)
                if ex <= 0:
                    continue
                pdx, pdy = cam(1.15 - 0.12 * pushes)         # Parallax pro Tiefe
                fy, fr_ = idle(k * 2.1, 1.0 if pushes > 0 else 0.6)
                slide = (1 - e_in) * side * W * 0.55         # Einflug von der Seite
                enter_rot = (1 - e_in) * side * 9            # kippt beim Reinfliegen
                settle = (1 - e_in) * H * 0.03
                exit_off = (1 - ex) * -side * W * 0.4        # fliegt seitlich raus
                put(fr, spr, W / 2 + pdx + slide + exit_off,
                    yp + pdy + settle + fy,
                    (0.82 + 0.18 * e_in) * gs,
                    min((t - ts) / 0.09, 1) * ex,
                    vblur=vel(f'p{k}', e_in) * 4.5,
                    rot=enter_rot + fr_ + (1 - ex) * side * 12, lift=1.2)
        # --- Finale: Logo + Wortmarke settlen ---
        if t >= T_WM:
            e_f = _elastic(t - T_WM)
            n_ch = (t - T_WM - 0.15) / 0.045
            wm = wordmark_sprite(n_ch)
            pdx, pdy = cam(0.9)
            fy, fr_ = idle(0.0, 0.6)
            put(fr, logo_small, W / 2 - wm.width / 2 - 120 + pdx,
                H * 0.48 + pdy + fy, (0.2 + 0.8 * e_f) * gs,
                min((t - T_WM) / 0.10, 1), vblur=vel('lf', e_f) * 5,
                rot=(1 - e_f) * -18 + fr_, lift=1.15)
            if n_ch > 0:
                put(fr, wm, W / 2 + 110 + pdx, H * 0.48 + pdy + fy * 0.6, gs,
                    min((t - T_WM - 0.1) / 0.15, 1), lift=1.0)
        vw.write(cv2.cvtColor(np.array(fr.convert('RGB')), cv2.COLOR_RGB2BGR))
        if i % 120 == 0:
            progress(f'  Frame {i}/{N}')
    vw.release()

    # --- Sound: NUR echte Pack-Sounds, exakt auf die Events gelegt ---
    audio = None
    try:
        import sfx_engine as SE
        bank = SE.load_bank(os.path.join(HERE, 'sfx', 'pack'))
        if bank:
            total = np.zeros(int((DUR + 1.0) * SE.SR), np.float32)
            for (te, slot, gain) in events:
                sig = bank.get(slot)
                if sig is None:
                    continue
                # Peak-Ausrichtung: der lauteste Punkt des Samples landet 40ms
                # vor der Akzent-Zeit; Vorlauf auf max. 0.25s getrimmt (press
                # z.B. hat 1s Anlauf - unbeschnitten kaeme der Hit 1s zu spaet).
                pk = int(np.argmax(np.abs(sig)))
                cut = max(pk - int(0.25 * SE.SR), 0)
                sig = sig[cut:]
                pk -= cut
                a = int((te - 0.04) * SE.SR) - pk
                if a < 0:
                    sig = sig[-a:]
                    a = 0
                b = min(a + len(sig), len(total))
                if b > a:
                    total[a:b] += sig[:b - a] * gain
            peak = float(np.abs(total).max() or 1.0)
            if peak > 0.9:
                total *= 0.9 / peak
            audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
            SE._save(audio, total)
    except Exception as e:
        progress(f'  SFX uebersprungen: {e}')
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', tmp]
    if audio:
        cmd += ['-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac']
    cmd += ['-c:v', 'libx264', '-crf', '17', '-pix_fmt', 'yuv420p',
            '-shortest', out_video]
    try:
        subprocess.run(cmd, check=True, timeout=300)
    finally:
        for p in (tmp, audio):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
    progress('UI-Motion-Prototyp fertig')
    return True


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('input', nargs='?', default=None)
    ap.add_argument('output')
    ap.add_argument('--demo', default='ed',
                    choices=['1', '2', '3', 'ed', 'sb', 'ui'])
    a = ap.parse_args()
    if a.demo == 'ui':
        raise SystemExit(0 if render_ui_motion(a.output) else 1)
    fn = {'1': render_demo, '2': render_demo2, '3': render_demo3,
          'ed': render_editorial, 'sb': render_stackbuild}[a.demo]
    raise SystemExit(0 if fn(a.input, a.output) else 1)
