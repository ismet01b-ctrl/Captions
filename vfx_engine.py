# -*- coding: utf-8 -*-
"""DouchkoVE VFX-Engine (v97 Prototyp): transformiert das ECHTE Video an EINEM
Aktions-Moment, synchron zur Caption - der Kern der Idee "VFX + Captions".

Zwei Wege, bewusst getrennt:
  1) LOKAL (deterministisch, kostenlos, local-first): Shockwave+Flash, RGB-Split,
     Hitze. Laeuft auf Ismets PC, kein Cloud, kein Gluecksspiel - zuverlaessig.
  2) CLOUD (generativ, Higgsfield/Seedance): echter Kopf-in-Flammen-Look etc.
     Pluggbarer Hook `generate_cloud_vfx` - braucht API-Key + Credits, Ergebnis
     ist ein Gluecksspiel. Bewusst opt-in und NUR fuer wenige Schluessel-Momente.

Prototyp-Ziel: EINEN Moment beweisen. Der ganze Clip wird durchgereicht, nur im
Fenster [t0, t0+dauer] liegt der Effekt; die Caption sitzt exakt darauf.
"""
import os
import subprocess
import tempfile
import numpy as np

try:
    import cv2
except Exception:                       # pragma: no cover
    cv2 = None

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_KINDS = ('shock', 'rgb', 'heat')


def _shock_frame(img, k):
    """Radiale Schockwelle + Weiss-Blitz + Zoom-Punch. k in 0..1 (0 = Aufschlag)."""
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    flash = max(0.0, 1.0 - k * 2.2)                     # kurzer heller Blitz
    out = out * (1 - 0.55 * flash) + 255.0 * 0.55 * flash
    cx, cy = w / 2.0, h / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy) + 1e-3
    ring = k * max(w, h) * 0.72                          # Ring waechst nach aussen
    amp = 20.0 * np.exp(-((r - ring) / (max(w, h) * 0.06)) ** 2) * (1.0 - k)
    mapx = (xx + dx / r * amp).astype(np.float32)
    mapy = (yy + dy / r * amp).astype(np.float32)
    warped = cv2.remap(np.clip(out, 0, 255).astype(np.uint8), mapx, mapy,
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    sc = 1.0 + 0.06 * (1.0 - k)                          # Zoom-Punch federt aus
    M = cv2.getRotationMatrix2D((cx, cy), 0, sc)
    return cv2.warpAffine(warped, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def _rgb_frame(img, k):
    """Chromatische Aberration / RGB-Split (Schock, Glitch, Energie)."""
    shift = int(round(14 * (1.0 - k)))
    if shift <= 0:
        return img
    b, g, r = cv2.split(img)
    r = np.roll(r, shift, axis=1)
    b = np.roll(b, -shift, axis=1)
    return cv2.merge([b, g, r])


def _heat_frame(img, k):
    """Hitze-Flimmern + warmer Glut-Ton (Feuer, Wut, Druck)."""
    h, w = img.shape[:2]
    yy = np.arange(h, dtype=np.float32)[:, None]
    wob = (np.sin(yy * 0.15 + k * 30.0) * 4.0 * (1.0 - k)).astype(np.float32)
    xx = (np.tile(np.arange(w, dtype=np.float32), (h, 1)) + wob)
    ymap = np.tile(yy, (1, w)).astype(np.float32)
    warp = cv2.remap(img, xx, ymap, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    warm = warp.astype(np.float32)
    warm[..., 2] = np.clip(warm[..., 2] * (1.0 + 0.25 * (1 - k)), 0, 255)   # mehr Rot
    warm[..., 0] = np.clip(warm[..., 0] * (1.0 - 0.12 * (1 - k)), 0, 255)   # weniger Blau
    return warm.astype(np.uint8)


_LOCAL = {'shock': _shock_frame, 'rgb': _rgb_frame, 'heat': _heat_frame}


def _caption_overlay(img, text, font_path=None, alpha=1.0):
    """Einfache, fette Center-Caption fuer den Prototyp (nicht die volle Engine)."""
    from PIL import Image, ImageDraw, ImageFont
    h, w = img.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert('RGBA')
    layer = Image.new('RGBA', pil.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fp = font_path or os.path.join(HERE, 'fonts', 'archivo.ttf')
    sz = int(h * 0.11)
    try:
        font = ImageFont.truetype(fp, sz)
    except Exception:
        font = ImageFont.load_default()
    tb = d.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    x, y = (w - tw) / 2, h * 0.66
    a = int(255 * max(0.0, min(1.0, alpha)))
    for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):    # Outline
        d.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, a))
    d.text((x, y), text, font=font, fill=(255, 122, 26, a))
    merged = Image.alpha_composite(pil, layer).convert('RGB')
    return cv2.cvtColor(np.array(merged), cv2.COLOR_RGB2BGR)


def generate_cloud_vfx(segment_path, prompt, out_path, api_key=None):
    """CLOUD-Hook (generativ, Higgsfield/Seedance). Bewusst NICHT verdrahtet:
    braucht Ismets API-Key + Credits + Netzwerk und liefert ein Gluecksspiel.
    Hier ist die EINE Stelle, an der der echte generative Call reinkommt (segment
    raus -> transformierten Clip zurueck). Bis dahin: NotImplemented, der lokale
    Weg traegt den Prototyp."""
    raise NotImplementedError(
        "Cloud-VFX (Higgsfield/Seedance) noch nicht verdrahtet - braucht API-Key. "
        "Der lokale VFX-Weg (kind=shock/rgb/heat) laeuft ohne Cloud.")


def render_moment_vfx(input_video, out_video, t0, dauer=0.6, kind='shock',
                      caption=None, progress=print):
    """Legt EINEN VFX-Moment auf das echte Video. Frame-genau im Fenster
    [t0, t0+dauer]; die Caption haelt etwas laenger, damit man sie liest.
    Rueckgabe: True bei Erfolg. Audio wird aus dem Original uebernommen."""
    if cv2 is None:
        progress("cv2 fehlt - VFX-Prototyp nicht verfuegbar")
        return False
    if kind not in _LOCAL:
        progress(f"Unbekannte VFX-Art '{kind}', nutze 'shock'")
        kind = 'shock'
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        progress("Konnte Video nicht oeffnen")
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f0 = int(t0 * fps)
    f1 = int((t0 + dauer) * fps)
    cap_hold = int((t0 + dauer + 0.5) * fps)             # Caption bleibt kurz stehen
    fn = _LOCAL[kind]
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    vw = cv2.VideoWriter(tmp, fourcc, fps, (w, h))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if f0 <= i < f1 and f1 > f0:
            k = (i - f0) / float(f1 - f0)
            frame = fn(frame, k)
        if caption and f0 <= i < cap_hold:
            fade = 1.0 if i < f1 else max(0.0, 1.0 - (i - f1) / max(cap_hold - f1, 1))
            try:
                frame = _caption_overlay(frame, str(caption).upper(), alpha=fade)
            except Exception:
                pass
        vw.write(frame)
        i += 1
    cap.release()
    vw.release()
    if i == 0:
        progress("Keine Frames gelesen")
        return False
    # Audio aus dem Original druebermuxen (VideoWriter schreibt nur Bild)
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-i', tmp, '-i', input_video,
             '-map', '0:v:0', '-map', '1:a:0?', '-c:v', 'libx264', '-crf', '18',
             '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', out_video],
            check=True, timeout=300)
    except Exception:
        # kein Audio / kein libx264 -> wenigstens das Bild retten
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', tmp,
                            '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                            out_video], check=True, timeout=300)
        except Exception as e:
            progress(f"Encode fehlgeschlagen ({type(e).__name__})")
            try: os.remove(tmp)
            except OSError: pass
            return False
    try: os.remove(tmp)
    except OSError: pass
    progress(f"VFX-Moment gesetzt: {kind} @ {t0:.2f}s"
             + (f" + Caption '{caption}'" if caption else ""))
    return True


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='DouchkoVE Ein-Moment-VFX-Prototyp')
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--t0', type=float, default=1.0)
    ap.add_argument('--dur', type=float, default=0.6)
    ap.add_argument('--kind', default='shock', choices=list(LOCAL_KINDS))
    ap.add_argument('--caption', default='')
    a = ap.parse_args()
    ok = render_moment_vfx(a.input, a.output, a.t0, a.dur, a.kind,
                           a.caption or None)
    raise SystemExit(0 if ok else 1)
