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


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('output')
    a = ap.parse_args()
    raise SystemExit(0 if render_demo(a.input, a.output) else 1)
