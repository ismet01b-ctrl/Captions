# -*- coding: utf-8 -*-
"""DouchkoVE Studio"""
import json, os, re, subprocess, sys, threading, queue, tempfile
import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox, ttk, font as tkfont
import yaml
import sfx_pack
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, 'config.yaml')

# ---------------- Design-System (Apple-Dark) ----------------
# Ruhige, tiefe Flaechen, ein einziger Akzent, viel Luft. Kein Farb-Zirkus.
BG      = '#151517'   # Fenster-Grund
SIDE    = '#1b1b1e'   # Seitenleiste, minimal abgehoben
SURF    = '#1e1e21'   # Karte
SURF2   = '#2a2a2e'   # Regler-Rille, Eingabefelder
SURF3   = '#3a3a3f'   # aktives Segment
LINE    = '#2e2e33'   # Trennlinie
FG      = '#f5f5f7'   # Text
MUT     = '#98989d'   # Erklaerung
MUT2    = '#6b6b70'   # Beschriftung
ACCENT  = '#0a84ff'   # ein Akzent: Systemblau
ACC_HI  = '#409cff'
IVORY   = '#f5f5f7'
DARK    = '#151517'
GREEN   = '#30d158'
RADIUS  = 14          # Eckenradius der Karten

F        = ('Segoe UI', 10)
F_S      = ('Segoe UI', 9)
F_M      = ('Segoe UI', 10)
F_B      = ('Segoe UI', 10, 'bold')
F_SEC    = ('Segoe UI', 9, 'bold')
F_TITLE  = ('Segoe UI Semibold', 15)
F_H1     = ('Segoe UI Semibold', 20)
F_BRAND  = ('Georgia', 17, 'bold italic')
F_NAV    = ('Segoe UI', 10)
F_NAV_A  = ('Segoe UI Semibold', 10)

CARD, TILE, GOLD, GOLD_HI = SURF, SURF2, ACCENT, '#e7d3a8'

FONT_CHOICES = [
    {'id': 'kino',    'label': 'Kino',      'file': 'fonts/archivo.ttf',     'italic': 'fonts/serif_i.ttf',
     'script': 'fonts/playfair_i.ttf'},
    {'id': 'tiktok',  'label': 'TikTok',    'file': 'fonts/tiktok_bold.ttf', 'italic': 'fonts/tiktok_bold.ttf'},
    {'id': 'montse',  'label': 'Creator',   'file': 'fonts/montserrat_xb.ttf', 'italic': 'fonts/montserrat_xb.ttf'},
    {'id': 'inter',   'label': 'Cinematic', 'file': 'fonts/inter_black.ttf', 'italic': 'fonts/inter_black.ttf'},
    {'id': 'anton',   'label': 'Impact',    'file': 'fonts/anton.ttf',       'italic': 'fonts/anton.ttf'},
    {'id': 'archivo', 'label': 'Black',     'file': 'fonts/archivo.ttf',     'italic': 'fonts/archivo.ttf'},
    {'id': 'bebas',   'label': 'Condensed', 'file': 'fonts/bebas.ttf',       'italic': 'fonts/bebas.ttf'},
    {'id': 'poppins', 'label': 'Clean',     'file': 'fonts/poppins_b.ttf',   'italic': 'fonts/poppins_b.ttf'},
    {'id': 'staat',   'label': 'Poster',    'file': 'fonts/staatliches.ttf', 'italic': 'fonts/staatliches.ttf'},
    {'id': 'alfa',    'label': 'Slab',      'file': 'fonts/alfaslab.ttf',    'italic': 'fonts/alfaslab.ttf'},
    {'id': 'yeseva',  'label': 'Fashion',   'file': 'fonts/yeseva.ttf',      'italic': 'fonts/yeseva.ttf'},
    {'id': 'bangers', 'label': 'Comic',     'file': 'fonts/bangers.ttf',     'italic': 'fonts/bangers.ttf'},
    {'id': 'right',   'label': 'Retro',     'file': 'fonts/righteous.ttf',   'italic': 'fonts/righteous.ttf'},
    {'id': 'lobster', 'label': 'Script',    'file': 'fonts/lobster.ttf',     'italic': 'fonts/lobster.ttf'},
    {'id': 'marker',  'label': 'Brush',     'file': 'fonts/marker.ttf',      'italic': 'fonts/marker.ttf'},
]
EFFECTS = [
    ('behind',  'Hinter dir',
     'Großes Wort taucht hinter der Person auf und schaut über die Schulter.'),
    ('cascade', 'Buchstaben-Aufbau',
     'Das Wort baut sich Buchstabe für Buchstabe auf, wie getippt.'),
    ('blurin',  'Aus der Unschärfe',
     'Grosser Titel kommt weich aus der Unschärfe, das Video dunkelt kurz ab.'),
    ('outline', 'Nur Umriss',
     'Das Wort als feine Kontur-Linie — edel und dezent.'),
    ('ground',  'In der Szene',
     'Text steht oder liegt IN der Szene: auf Wasser als Wasser-Glas (Blender), '
     'am Boden mit Schatten - bewegt sich mit der Kamera, Objekte koennen ihn verdecken.'),
]
# Die Bereiche der Seitenleiste. Jeder buendelt, was thematisch zusammengehoert -
# vorher lag alles in drei ueberladenen Listen.
NAV = {
    'Video':    'build_start',
    'Hook':     'build_hook',
    'Text':     'build_text',
    'Effekte':  'build_feintuning',
    'Sound':    'build_sound',
    'Ausgabe':  'build_output',
    'Profi':    'build_profi',
}

LANG_SEG = [('Deutsch', 'de'), ('Englisch', 'en'), ('Auto', 'auto')]
RES_SEG  = [('720p', 720), ('1080p', 1080), ('4K', 2160)]
WPG_SEG  = [('2', 2), ('3', 3), ('4', 4)]
PLATFORM_SEG = [('YouTube', 'akzente'), ('Ausgewogen', 'ausgewogen'),
                ('TikTok & Reels', 'durchgehend')]

# Vier klar getrennte Looks - jeder hat einen anderen Zweck, eine andere Schrift,
# eine andere Effekt-Handschrift. Keine Ueberschneidungen, kein Effekt-Salat.
PRESETS = {
    'TikTok': {'desc': 'Wort für Wort, fett, laut. Shorts, Reels, FYP.',
               'plattform': 'durchgehend',
               'fx': ['behind', 'outline'], 'dynamik': 'Energisch',
               'wpg': 2, 'gap': 4, 'dim': 45, 'sfxvol': 50,
               'font': 'tiktok', 'style': '3d kinetisch'},
    'Creator': {'desc': 'Talking-Head & Business. Keywords sitzen, Rest bleibt ruhig.',
                'plattform': 'ausgewogen',
                'fx': ['behind', 'cascade'], 'dynamik': 'Ausgewogen',
                'wpg': 3, 'gap': 7, 'dim': 38, 'sfxvol': 30,
                'font': 'montse', 'style': '3d'},
    'Cinematic': {'desc': 'Wenige, große Momente in der Szene. B-Roll, Doku, Marken.',
                  'plattform': 'akzente',
                  'fx': ['blurin', 'ground'], 'dynamik': 'Ruhig',
                  'wpg': 3, 'gap': 11, 'dim': 30, 'sfxvol': 22,
                  'font': 'inter', 'style': '3d'},
    'Clean': {'desc': 'Nur lesbare Untertitel. Nichts lenkt ab. Interviews, Corporate.',
              'plattform': 'ausgewogen',
              'fx': ['cascade'], 'dynamik': 'Ruhig',
              'wpg': 3, 'gap': 14, 'dim': 10, 'sfxvol': 0,
              'font': 'poppins', 'style': 'klassisch'},
}
DYNAMIK = {
    'Ruhig':      {'strength': 45, 'freq': 4, 'capzoom': True,  'drift': False, 'kw': False,
                   'crash': 0,  'whip': False},   # Clean/Cinematic: ruhig, kein Crash/Whip
    'Ausgewogen': {'strength': 70, 'freq': 3, 'capzoom': True,  'drift': True,  'kw': True,
                   'crash': 55, 'whip': False},   # Creator: moderater Crash, kein Whip
    'Energisch':  {'strength': 85, 'freq': 2, 'capzoom': True,  'drift': True,  'kw': True,
                   'crash': 100, 'whip': True},   # TikTok: voller Crash + Whip-Pan
}



def popup_scroll(win, bottom_bar):
    """Scrollflaeche fuer Popup-Fenster. Der Knopf-Balken wird ZUERST unten
    verankert - sonst frisst der Canvas den Platz und der Knopf landet mitten
    im Fenster. Die Zeilen werden auf volle Fensterbreite gezogen."""
    bottom_bar.pack(side='bottom', fill='x')
    holder = tk.Frame(win, bg=BG)
    holder.pack(side='top', fill='both', expand=True)
    cv = tk.Canvas(holder, bg=BG, highlightthickness=0, yscrollincrement=16)
    sb = tk.Scrollbar(holder, command=cv.yview)
    inner = tk.Frame(cv, bg=BG)
    inner.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))
    iw = cv.create_window((0, 0), window=inner, anchor='nw')
    cv.bind('<Configure>', lambda e: cv.itemconfigure(iw, width=e.width))
    cv.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    cv.pack(side='left', fill='both', expand=True, padx=(16, 0))
    for w in (win, cv, inner):
        w.bind('<MouseWheel>',
               lambda e: cv.yview_scroll(-3 if e.delta > 0 else 3, 'units'))
    return inner


def make_font_tile(path, w=188, h=54):
    img = Image.new('RGB', (w, h), TILE)
    d = ImageDraw.Draw(img)
    size = 30
    f = ImageFont.truetype(os.path.join(HERE, path), size)
    bb = d.textbbox((0, 0), 'Premium', font=f)
    while bb[2] - bb[0] > w - 26 and size > 14:
        size -= 2
        f = ImageFont.truetype(os.path.join(HERE, path), size)
        bb = d.textbbox((0, 0), 'Premium', font=f)
    d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]),
           'Premium', font=f, fill='#f2f1ee')
    out = os.path.join(tempfile.gettempdir(), f'dve_tile_{os.path.basename(path)}.png')
    img.save(out)
    return out


def hover(widget, on, off):
    widget.bind('<Enter>', lambda e: widget.configure(**on))
    widget.bind('<Leave>', lambda e: widget.configure(**off))


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    cv.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, **kw)
    cv.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, **kw)
    cv.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, **kw)
    cv.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, **kw)
    cv.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
    cv.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)


# ---------------- Widgets ----------------
class Card(tk.Canvas):
    """Abgerundete Karte mit echtem Radius. tkinter-Frames koennen keine runden
    Ecken - darum liegt der Inhalt auf einer Canvas, die den Hintergrund malt und
    sich automatisch auf die Hoehe des Inhalts zieht."""
    def __init__(self, parent, pad=22, bg=BG, fill=SURF):
        super().__init__(parent, bg=bg, highlightthickness=0)
        self.pad, self.fill_c = pad, fill
        self.body = tk.Frame(self, bg=fill)
        self.win = self.create_window(pad, pad, anchor='nw', window=self.body)
        self.body.bind('<Configure>', self._fit)
        self.bind('<Configure>', self._fit)

    def _fit(self, e=None):
        w = self.winfo_width()
        if w > 1:
            self.itemconfigure(self.win, width=w - 2 * self.pad)
        h = self.body.winfo_reqheight() + 2 * self.pad
        if abs(self.winfo_reqheight() - h) > 1:
            self.configure(height=h)
        self.delete('bgshape')
        round_rect(self, 1, 1, max(w - 1, 4), h - 1, RADIUS,
                   fill=self.fill_c, outline='', tags='bgshape')
        self.tag_lower('bgshape')


class Pill(tk.Canvas):
    def __init__(self, parent, text, command, primary=True, width=190, bg=BG):
        super().__init__(parent, width=width, height=38, bg=bg, highlightthickness=0,
                         cursor='hand2')
        self.command, self.primary, self.w, self.text = command, primary, width, text
        self.hovering = False
        self.disabled = False
        self.bind('<Button-1>', lambda e: None if self.disabled else self.command())
        self.bind('<Enter>', lambda e: self.set_hover(True))
        self.bind('<Leave>', lambda e: self.set_hover(False))
        self.draw()

    def set_hover(self, v):
        self.hovering = v and not self.disabled
        self.draw()

    def set_enabled(self, on):
        self.disabled = not on
        self.hovering = False
        self.configure(cursor='arrow' if self.disabled else 'hand2')
        self.draw()

    def set_text(self, text, primary=None):
        self.text = text
        if primary is not None:
            self.primary = primary
        self.draw()

    def draw(self):
        self.delete('all')
        if self.disabled:
            round_rect(self, 1, 1, self.w - 1, 37, 10, fill=SURF2, outline='')
            self.create_text(self.w / 2, 19, text=self.text, font=F, fill=MUT2)
            return
        if self.primary:
            fill = ACC_HI if self.hovering else ACCENT
            round_rect(self, 1, 1, self.w - 1, 37, 10, fill=fill, outline='')
            self.create_text(self.w / 2, 19, text=self.text,
                             font=('Segoe UI Semibold', 10), fill='#ffffff')
        else:
            fill = SURF3 if self.hovering else SURF2
            round_rect(self, 1, 1, self.w - 1, 37, 10, fill=fill, outline='')
            self.create_text(self.w / 2, 19, text=self.text, font=F, fill=FG)


class Switch(tk.Canvas):
    """iOS-Schalter: Kapsel, Knopf gleitet."""
    def __init__(self, parent, variable, bg=SURF):
        super().__init__(parent, width=46, height=28, bg=bg, highlightthickness=0,
                         cursor='hand2')
        self.var = variable
        self.bind('<Button-1>', lambda e: self.var.set(not self.var.get()))
        self.var.trace_add('write', lambda *a: self.draw())
        self.draw()

    def draw(self):
        self.delete('all')
        on = bool(self.var.get())
        round_rect(self, 2, 3, 44, 25, 11, fill=ACCENT if on else '#3a3a3f', outline='')
        x = 33 if on else 13
        self.create_oval(x - 9, 5, x + 9, 23, fill='#ffffff', outline='')


class Segmented(tk.Frame):
    """macOS-Segmentsteuerung: eine Kapsel, das aktive Feld hebt sich ab."""
    def __init__(self, parent, options, variable, bg=SURF):
        super().__init__(parent, bg=bg)
        self.var = variable
        self.btns = {}
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, height=34)
        self.cv.pack(fill='x')
        self.options = list(options)
        self.cv.bind('<Configure>', lambda e: self.draw())
        self.cv.bind('<Button-1>', self.click)
        self.cv.configure(cursor='hand2')
        self.var.trace_add('write', lambda *a: self.draw())
        self._widths = []

    def _measure(self):
        f = ('Segoe UI', 9)
        tmp = tkfont.Font(family='Segoe UI', size=9)
        self._widths = [max(tmp.measure(lbl) + 30, 62) for lbl, _v in self.options]
        return sum(self._widths)

    def click(self, e):
        x = 4
        for (lbl, val), w in zip(self.options, self._widths or [0]):
            if x <= e.x < x + w:
                self.var.set(val)
                return
            x += w

    def draw(self):
        self.cv.delete('all')
        total = self._measure()
        self.cv.configure(width=total + 8)
        round_rect(self.cv, 0, 2, total + 8, 34, 9, fill=SURF2, outline='')
        cur = self.var.get()
        x = 4
        for (lbl, val), w in zip(self.options, self._widths):
            act = (val == cur)
            if act:
                round_rect(self.cv, x, 5, x + w, 31, 7, fill=SURF3, outline='')
            self.cv.create_text(x + w / 2, 18, text=lbl,
                                font=('Segoe UI Semibold', 9) if act else ('Segoe UI', 9),
                                fill=FG if act else MUT)
            x += w


class Chip(tk.Canvas):
    """Auswahl-Chip: an = gefuellt im Akzent, aus = ruhige Flaeche."""
    def __init__(self, parent, text, variable, mark_custom, bg=SURF):
        self.text = text
        tmp = tkfont.Font(family='Segoe UI', size=9)
        self.w = tmp.measure(text) + 32
        super().__init__(parent, width=self.w, height=32, bg=bg,
                         highlightthickness=0, cursor='hand2')
        self.var, self.mark_custom = variable, mark_custom
        self.bind('<Button-1>', self.toggle)
        self.var.trace_add('write', lambda *a: self.draw())
        self.draw()

    def toggle(self, e=None):
        self.var.set(not self.var.get())
        self.mark_custom()

    def draw(self):
        self.delete('all')
        on = bool(self.var.get())
        round_rect(self, 1, 1, self.w - 1, 31, 9,
                   fill=ACCENT if on else SURF2, outline='')
        self.create_text(self.w / 2, 16, text=self.text,
                         font=('Segoe UI Semibold', 9) if on else ('Segoe UI', 9),
                         fill='#ffffff' if on else MUT)


class Slider(tk.Canvas):
    """Regler im macOS-Stil: schlanke Rille, gefuellter Weg, greifbarer Knopf.
    Ziehen, klicken und Pfeiltasten - der Wert steht immer rechts daneben."""
    def __init__(self, parent, variable, lo, hi, suffix='', bg=SURF, width=380):
        super().__init__(parent, height=44, bg=bg, highlightthickness=0,
                         cursor='hand2')
        self.var, self.lo, self.hi, self.suffix = variable, lo, hi, suffix
        self.drag = False
        self.disabled = False
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Button-1>', self.grab)
        self.bind('<B1-Motion>', self.move)
        self.bind('<ButtonRelease-1>', lambda e: setattr(self, 'drag', False))
        self.var.trace_add('write', lambda *a: self.draw())

    def set_enabled(self, on):
        self.disabled = not on
        self.configure(cursor='arrow' if self.disabled else 'hand2')
        self.draw()

    def _geom(self):
        w = max(self.winfo_width(), 60)
        return 10, w - 78          # Bahn von x0 bis x1, rechts Platz fuer den Wert

    def _from_x(self, x):
        x0, x1 = self._geom()
        f = min(max((x - x0) / max(x1 - x0, 1), 0.0), 1.0)
        return int(round(self.lo + f * (self.hi - self.lo)))

    def grab(self, e):
        if self.disabled:
            return
        self.drag = True
        self.var.set(self._from_x(e.x))

    def move(self, e):
        if self.drag and not self.disabled:
            self.var.set(self._from_x(e.x))

    def draw(self):
        self.delete('all')
        x0, x1 = self._geom()
        try:
            val = float(self.var.get())
        except Exception:
            val = self.lo
        f = (val - self.lo) / max(self.hi - self.lo, 1e-6)
        f = min(max(f, 0.0), 1.0)
        cx = x0 + f * (x1 - x0)
        acc = SURF3 if self.disabled else ACCENT
        round_rect(self, x0, 18, x1, 26, 4, fill=SURF2, outline='')
        if cx > x0 + 2:
            round_rect(self, x0, 18, cx, 26, 4, fill=acc, outline='')
        self.create_oval(cx - 10, 12, cx + 10, 32,
                         fill='#f5f5f7' if not self.disabled else '#5a5a5f',
                         outline='')
        self.create_text(x1 + 34, 22, text=f'{self.var.get()}{self.suffix}',
                         font=('Segoe UI Semibold', 10),
                         fill=FG if not self.disabled else MUT2)


class Progress(tk.Canvas):
    def __init__(self, parent, bg=BG):
        super().__init__(parent, height=4, bg=bg, highlightthickness=0)
        self.frac = 0.0
        self.bind('<Configure>', lambda e: self.draw())

    def set(self, frac):
        self.frac = max(0.0, min(frac, 1.0))
        self.draw()

    def draw(self):
        self.delete('all')
        w = self.winfo_width()
        round_rect(self, 0, 0, max(w, 4), 4, 2, fill=SURF2, outline='')
        if self.frac > 0.01:
            round_rect(self, 0, 0, max(w * self.frac, 4), 4, 2, fill=ACCENT, outline='')


# ---------------- App ----------------
class App:
    def __init__(self, root):
        self.root = root
        root.title('DouchkoVE Studio')
        root.configure(bg=BG)
        geo = None
        try:
            _st = json.load(open(os.path.join(HERE, 'ui_state.json'),
                                 encoding='utf-8'))
            geo = _st.get('geometry')
        except Exception:
            pass
        root.geometry(geo or '1180x880')      # Fenstergroesse wie beim Schliessen
        root.minsize(1040, 720)
        self.cfg = yaml.safe_load(open(CFG_PATH, encoding='utf-8'))
        self.video_path = None
        self.proc = None
        self.out_path = None
        self.q = queue.Queue()
        self._imgs = []
        self.ui_state = self._ui_state_load()
        self._card_open = {}
        self._wraps = []
        self._last_w = 0
        self.font_cells = []
        self.total_frames = 0
        self._applying = False
        self.active_canvas = None
        root.bind_all('<MouseWheel>', self.on_wheel)          # Windows/macOS
        root.bind_all('<Button-4>', lambda e: self.on_wheel(e, 1))    # Linux
        root.bind_all('<Button-5>', lambda e: self.on_wheel(e, -1))
        self.build()
        self.poll_queue()

    def on_wheel(self, e, direction=None):
        c = self.active_canvas
        if c is None:
            return
        if direction is None:
            direction = 1 if getattr(e, 'delta', 0) > 0 else -1
        c.yview_scroll(-direction * 3, 'units')

    def init_vars(self):
        cfg = self.cfg
        cur_fx = cfg['effects'].get('keyword_rotation', [])
        self.fx_vars = {k: tk.BooleanVar(value=k in cur_fx) for k, *_ in EFFECTS}
        self.wpg_var = tk.IntVar(value=int(cfg['effects'].get('words_per_group', 3)))
        self.gap_var = tk.IntVar(value=int(cfg['keywords'].get('min_gap_seconds', 6)))
        self.dim_var = tk.IntVar(value=int(cfg['effects'].get('dim_behind', 0.38) * 100))
        self.hold_var = tk.IntVar(value=int(float(cfg['effects'].get('chunk_hold_min', 0.65)) * 1000))
        self.zahl_var = tk.IntVar(value=int(float(cfg['effects'].get('zahl_gap', 15))))
        self.beat_var = tk.IntVar(value=int(float(cfg['effects'].get('beat_sync', 0.7)) * 100))
        self.pshadow_var = tk.IntVar(value=int(float(cfg['effects'].get('person_shadow', 0.5)) * 100))
        self.sfxvol_var = tk.IntVar(value=int(cfg['effects'].get('sfx_volume', 0.35) * 100))
        self.cam_str = tk.IntVar(value=int(cfg['camera'].get('strength', 0.7) * 100))
        self.crash_var = tk.IntVar(value=int(float(cfg['camera'].get('crash', 0.55)) * 100))
        self.whip_var = tk.BooleanVar(value=bool(cfg['camera'].get('whip', False)))
        self.freq_var = tk.IntVar(value=int(cfg['camera'].get('side_every', 3)))
        side_rot = cfg['camera'].get('side_rotation') or []
        kw_rot = cfg['camera'].get('keyword_rotation') or []
        self.capzoom_var = tk.BooleanVar(value='capzoom' in side_rot)
        self.drift_var = tk.BooleanVar(value='drift' in side_rot)
        self.kwcam_var = tk.BooleanVar(value=len(kw_rot) > 0)
        self.ai_var = tk.BooleanVar(value=cfg['keywords'].get('ai', True))
        self.anim_var = tk.BooleanVar(value=cfg['effects'].get('anim', True))
        self.intro_var = tk.BooleanVar(value=cfg['effects'].get('intro_hook', True))
        self.hooksec_var = tk.IntVar(value=int(cfg['effects'].get('hook_seconds', 15)))
        self.ihook_var = tk.BooleanVar(value=cfg['effects'].get('instant_hook', True))
        self.hookpow_var = tk.StringVar(
            value=('stark' if float(cfg['effects'].get('hook_strength', 0.5)) >= 0.75
                   else ('sanft' if float(cfg['effects'].get('hook_strength', 0.5)) <= 0.3
                         else 'normal')))
        self.retgap_var = tk.IntVar(value=int(cfg['effects'].get('retention_gap', 12)))
        self.pint_var = tk.BooleanVar(
            value=float(cfg['effects'].get('pattern_interrupt', 9)) > 0)
        self.safe_var = tk.BooleanVar(value=cfg['effects'].get('safe_zone', True))
        self.lang_var = tk.StringVar(value=cfg.get('language', 'de'))
        self.res_var = tk.IntVar(value=int(cfg['output'].get('height', 1080)))
        self.master_var = tk.BooleanVar(value=cfg['output'].get('master', False))
        self.speed_var = tk.StringVar(value=str(cfg['output'].get('speed', 'standard')))
        self.platform_var = tk.StringVar(value=str(cfg['effects'].get('density', 'akzente')))
        self.style_var = tk.StringVar(value=str(cfg['effects'].get('text_style', '3d')))
        self.color_var = tk.StringVar(
            value=str(cfg.get('colors', {}).get('style', 'auto')))
        self.emerge_var = tk.StringVar(
            value=str(cfg['effects'].get('emerge', 'auto')))
        self.mask_var = tk.StringVar(
            value=str(cfg.get('matting_quality', 'standard')))
        self.dynamik_var = tk.StringVar(value='Ausgewogen')

    def build(self):
        side = tk.Frame(self.root, bg=SIDE, width=200)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=SIDE)
        brand.pack(fill='x', padx=22, pady=(26, 4))
        tk.Label(brand, text='DouchkoVE', font=F_BRAND, bg=SIDE, fg=FG).pack(anchor='w')
        tk.Label(brand, text='S T U D I O', font=('Segoe UI', 7, 'bold'), bg=SIDE,
                 fg=MUT2).pack(anchor='w')
        tk.Frame(side, bg=LINE, height=1).pack(fill='x', padx=22, pady=(16, 16))

        self.nav = {}
        self.sections = {}
        for name in NAV:
            row = tk.Frame(side, bg=SIDE, cursor='hand2')
            row.pack(fill='x')
            bar = tk.Frame(row, bg=SIDE, width=3, height=38)
            bar.pack(side='left', fill='y')
            bar.pack_propagate(False)
            lbl = tk.Label(row, text=name, font=F_NAV, bg=SIDE, fg=MUT, anchor='w',
                           padx=19, pady=9, cursor='hand2')
            lbl.pack(side='left', fill='x', expand=True)
            for w in (row, lbl):
                w.bind('<Button-1>', lambda e, n=name: self.show_section(n))
            self.nav[name] = (row, bar, lbl)

        foot_side = tk.Frame(side, bg=SIDE)
        foot_side.pack(side='bottom', fill='x', padx=22, pady=20)
        self.side_status = tk.Label(foot_side, text='Bereit', font=F_S, bg=SIDE, fg=MUT2,
                                    anchor='w')
        self.side_status.pack(anchor='w')

        main = tk.Frame(self.root, bg=BG)
        main.pack(side='left', fill='both', expand=True)

        head = tk.Frame(main, bg=BG)
        head.pack(fill='x', padx=30, pady=(24, 4))
        vcard = Card(head, pad=13, bg=BG, fill=SURF)
        vcard.pack(side='left', fill='x', expand=True)
        vchip = vcard.body
        self.video_lbl = tk.Label(vchip, text='Kein Video gewählt  ·  mehrere Videos '
                                  'möglich (Strg gedrückt halten)', font=F, bg=SURF,
                                  fg=MUT, anchor='w')
        self.video_lbl.pack(side='left', fill='x', expand=True)
        self.pick_lbl = tk.Label(vchip, text='Video wählen',
                                 font=('Segoe UI Semibold', 10),
                                 bg=SURF, fg=ACCENT, cursor='hand2', padx=6)
        self.pick_lbl.pack(side='right')
        self.pick_lbl.bind('<Button-1>', lambda e: None if getattr(self, 'busy', False)
                           else self.pick_video())
        self.batch = []

        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill='both', expand=True, padx=30, pady=(14, 0))
        for name in NAV:
            self.sections[name] = self.make_scroll_section()

        self.init_vars()
        for name, builder in NAV.items():
            self.inner = self.sections[name]['inner']
            getattr(self, builder)()

        foot = tk.Frame(main, bg=BG)
        foot.pack(fill='x', padx=30, pady=(14, 22))
        self.progress = Progress(foot)
        self.progress.pack(fill='x', pady=(0, 12))
        info = tk.Frame(foot, bg=BG)
        info.pack(fill='x')
        row = tk.Frame(foot, bg=BG)
        row.pack(fill='x', pady=(10, 0))
        left = tk.Frame(info, bg=BG)
        left.pack(side='left', fill='x', expand=True)
        self.status = tk.Label(left, text='Bereit', font=F_S, bg=BG, fg=MUT, anchor='w')
        self.status.pack(anchor='w')
        links = tk.Frame(left, bg=BG)
        links.pack(anchor='w')
        self.log_toggle = tk.Label(links, text='Details anzeigen', font=F_S, bg=BG,
                                   fg=MUT2, cursor='hand2')
        self.log_toggle.pack(side='left')
        self.log_toggle.bind('<Button-1>', lambda e: self.toggle_log())
        folder = tk.Label(links, text='   ·   Ausgabe-Ordner', font=F_S, bg=BG, fg=MUT2,
                          cursor='hand2')
        folder.pack(side='left')
        folder.bind('<Button-1>', lambda e: self.open_folder())

        self.prev_btn = Pill(row, 'Vorschau · 15 Sek', lambda: self.render(preview=True),
                             primary=False, width=170)
        self.prev_btn.pack(side='right', padx=(10, 0))
        self.trans_btn = Pill(row, 'Transkript', self.check_transcript,
                              primary=False, width=120)
        self.trans_btn.pack(side='right', padx=(10, 0))
        self.mom_btn = Pill(row, 'Momente', self.open_moments, primary=False, width=120)
        self.mom_btn.pack(side='right', padx=(10, 0))
        self.render_btn = Pill(row, 'Video generieren', lambda: self.render(),
                               primary=True, width=200)
        self.render_btn.pack(side='right')

        self.busy = False
        self.log_visible = False
        self.log = tk.Text(main, bg='#101114', fg=GREEN, font=('Consolas', 9),
                           relief='flat', height=8, state='disabled',
                           highlightthickness=0)
        for name, s in self.sections.items():
            self.bind_wheel_recursive(s['frame'], s['canvas'])
        self.root.bind('<Prior>', lambda e: self.active_canvas and
                       self.active_canvas.yview_scroll(-14, 'units'))
        self.root.bind('<Next>', lambda e: self.active_canvas and
                       self.active_canvas.yview_scroll(14, 'units'))
        self.show_section(self.ui_state.get('section', 'Video'))
        # Beim Schliessen wird ALLES gesichert: Einstellungen, Schluessel, welche
        # Karten offen sind und wo man zuletzt war. Vorher wurde nur beim Klick auf
        # 'Video generieren' gespeichert - wer nur einstellte und schloss, verlor alles.
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.detect_preset()

    def make_scroll_section(self):
        frame = tk.Frame(self.content, bg=BG)
        canvas = tk.Canvas(frame, bg=BG, highlightthickness=0, yscrollincrement=16)
        import tkinter.ttk as ttk
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('DVE.Vertical.TScrollbar', gripcount=0, background=SURF3,
                        troughcolor=BG, bordercolor=BG, arrowcolor=MUT2,
                        lightcolor=SURF3, darkcolor=SURF3)
        # Auswahlfelder dunkel: das weisse ttk-Standardfeld zerreisst den Look
        style.configure('DVE.TCombobox', fieldbackground=SURF2, background=SURF2,
                        foreground=FG, arrowcolor=MUT, bordercolor=SURF2,
                        lightcolor=SURF2, darkcolor=SURF2, selectbackground=SURF2,
                        selectforeground=FG, padding=6)
        style.map('DVE.TCombobox', fieldbackground=[('readonly', SURF2)],
                  background=[('readonly', SURF2)])
        sb = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview,
                           style='DVE.Vertical.TScrollbar')
        canvas.configure(yscrollcommand=sb.set)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind('<Configure>',
                   lambda e, c=canvas: c.configure(scrollregion=c.bbox('all')))
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        def _cfg(e, c=canvas, i=cw):
            c.itemconfigure(i, width=e.width)
            self.on_resize(e.width)
        canvas.bind('<Configure>', _cfg)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        return {'frame': frame, 'canvas': canvas, 'inner': inner}

    def show_section(self, name):
        if name not in self.sections:
            name = 'Video'
        self.current_section = name
        for n, s in self.sections.items():
            s['frame'].pack_forget()
            row, bar, lbl = self.nav[n]
            bar.configure(bg=SIDE)
            lbl.configure(fg=MUT, font=F_NAV, bg=SIDE)
            row.configure(bg=SIDE)
        s = self.sections[name]
        s['frame'].pack(fill='both', expand=True)
        row, bar, lbl = self.nav[name]
        bar.configure(bg=ACCENT)
        lbl.configure(fg=FG, font=F_NAV_A, bg=SURF)
        row.configure(bg=SURF)
        self.active_canvas = s['canvas']

    def bind_wheel_recursive(self, widget, canvas):
        widget.bind('<MouseWheel>',
                    lambda e, c=canvas: c.yview_scroll(-3 if e.delta > 0 else 3, 'units'))
        widget.bind('<Button-4>', lambda e, c=canvas: c.yview_scroll(-3, 'units'))
        widget.bind('<Button-5>', lambda e, c=canvas: c.yview_scroll(3, 'units'))
        for child in widget.winfo_children():
            self.bind_wheel_recursive(child, canvas)

    # ---------- Mitskalieren ----------
    def _wrap(self, lbl, frac=0.92):
        """Merkt sich ein Text-Label mit seinem Breiten-Anteil. Beim Vergroessern
        des Fensters bricht der Text neu um, statt stur schmal zu bleiben."""
        self._wraps.append((lbl, frac))
        return lbl

    def on_resize(self, w):
        if w <= 1 or abs(w - getattr(self, '_last_w', 0)) < 8:
            return
        self._last_w = w
        inner_w = max(w - 90, 260)              # abzueglich Karten-Polster
        for lbl, frac in list(self._wraps):
            try:
                lbl.configure(wraplength=int(inner_w * frac))
            except Exception:
                self._wraps.remove((lbl, frac))
        if getattr(self, 'font_cells', None):
            # Kachel + Abstand ist real ~172 px breit. Zu klein geschaetzt und die
            # Kacheln laufen rechts aus der Karte raus.
            usable = w - 44 - 44 - 20          # Rand + Karten-Polster + Scrollbar
            per = max(int(usable // 174), 2)
            if per != getattr(self, '_font_per', 0):
                self.reflow_fonts(per)

    def reflow_fonts(self, per_row):
        self._font_per = per_row
        for n, cell in enumerate(self.font_cells):
            cell.grid(row=n // per_row, column=n % per_row, padx=(0, 10),
                      pady=(0, 12))

    # ---------- Bausteine ----------
    def card(self, title, subtitle=None):
        """Karte mit runden Ecken - auf- und zuklappbar wie in den iPhone-
        Einstellungen. Der Zustand wird gemerkt und beim naechsten Start
        wiederhergestellt."""
        cd = Card(self.inner, pad=22, bg=BG, fill=SURF)
        cd.pack(fill='x', pady=(0, 16))
        c = cd.body
        head = tk.Frame(c, bg=SURF, cursor='hand2')
        head.pack(fill='x')
        t = tk.Label(head, text=title, font=F_TITLE, bg=SURF, fg=FG, cursor='hand2')
        t.pack(side='left')
        chev = tk.Label(head, text='⌄', font=('Segoe UI', 14), bg=SURF, fg=MUT,
                        cursor='hand2')
        chev.pack(side='right')
        sub = None
        if subtitle:
            sub = tk.Label(c, text=subtitle, font=F_S, bg=SURF, fg=MUT,
                           justify='left')
            sub.pack(anchor='w', pady=(3, 0))
            self._wrap(sub, 0.92)
        content = tk.Frame(c, bg=SURF)
        content.pack(fill='x')
        state = self.ui_state.get('open', {}).get(title, True)

        def toggle(_e=None):
            now = not self._card_open.get(title, True)
            self._card_open[title] = now
            self.ui_state.setdefault('open', {})[title] = now
            chev.configure(text='⌄' if now else '›')
            if now:
                if sub is not None:
                    sub.pack(anchor='w', pady=(3, 0), before=content)
                content.pack(fill='x')
            else:
                if sub is not None:
                    sub.pack_forget()
                content.pack_forget()
            self.root.after(10, cd._fit)

        for w in (head, t, chev):
            w.bind('<Button-1>', toggle)
        self._card_open[title] = True
        if not state:
            toggle()
        return content

    def sep(self, parent, pady=(14, 14)):
        tk.Frame(parent, bg=LINE, height=1).pack(fill='x', pady=pady)

    def row(self, parent, title, desc=None, first=False):
        """Eine Einstellungs-Zeile: links Name + Erklaerung, rechts das Bedienelement.
        Genau so liest man eine Einstellung in einer Sekunde - statt Textwaende."""
        if not first:
            self.sep(parent, pady=(13, 13))
        r = tk.Frame(parent, bg=SURF)
        r.pack(fill='x', pady=(14, 0) if first else (0, 0))
        left = tk.Frame(r, bg=SURF)
        left.pack(side='left', fill='x', expand=True)
        tk.Label(left, text=title, font=F_B, bg=SURF, fg=FG).pack(anchor='w')
        if desc:
            d = tk.Label(left, text=desc, font=F_S, bg=SURF, fg=MUT, justify='left')
            d.pack(anchor='w', pady=(2, 0))
            self._wrap(d, 0.55)          # linke Spalte, rechts steht das Bedienelement
        right = tk.Frame(r, bg=SURF)
        right.pack(side='right', padx=(20, 0))
        return right

    def switch_row(self, parent, title, desc, var, pady=None, first=False):
        right = self.row(parent, title, desc, first=first)
        Switch(right, var).pack(pady=2)
        return right

    def setting(self, parent, title, desc=None):
        tk.Label(parent, text=title, font=F_B, bg=SURF, fg=FG).pack(anchor='w',
                                                                    pady=(16, 0))
        if desc:
            d = tk.Label(parent, text=desc, font=F_S, bg=SURF, fg=MUT, justify='left')
            d.pack(anchor='w', pady=(2, 6))
            self._wrap(d, 0.92)

    # ---------- Sektion: Start ----------
    def build_start(self):
        c = self.card('Plattform', 'Bestimmt, wie dicht die Captions laufen.')
        r = self.row(c, 'Ausgabeformat',
                     'YouTube: wenige, große Momente.  Ausgewogen: Momente mit '
                     'Kontext.  TikTok & Reels: durchgehende Captions, Wort für Wort.',
                     first=True)
        Segmented(r, PLATFORM_SEG, self.platform_var).pack()

        c = self.card('Preset', 'Ein Klick, ein fertiger Look.')
        grid = tk.Frame(c, bg=SURF)
        grid.pack(fill='x', pady=(14, 4))
        self.preset_tiles = {}
        for n, (name, p) in enumerate(PRESETS.items()):
            cell = Card(grid, pad=14, bg=SURF, fill=SURF2)
            cell.grid(row=n // 2, column=n % 2, padx=(0, 10), pady=(0, 10),
                      sticky='nsew')
            grid.columnconfigure(n % 2, weight=1, uniform='p')
            inner = cell.body
            headr = tk.Frame(inner, bg=SURF2)
            headr.pack(fill='x')
            dot = tk.Label(headr, text='●', font=('Segoe UI', 9), bg=SURF2, fg=SURF3)
            dot.pack(side='left', padx=(0, 8))
            t1 = tk.Label(headr, text=name, font=('Segoe UI Semibold', 11), bg=SURF2,
                          fg=FG, cursor='hand2')
            t1.pack(side='left')
            t2 = tk.Label(inner, text=p['desc'], font=F_S, bg=SURF2, fg=MUT,
                          justify='left', cursor='hand2')
            t2.pack(anchor='w', pady=(4, 0))
            self._wrap(t2, 0.42)
            for w in (cell, inner, headr, t1, t2, dot):
                w.bind('<Button-1>', lambda e, nm=name: self.apply_preset(nm))
            self.preset_tiles[name] = (cell, dot, None)
        self.preset_state = tk.Label(c, text='', font=F_S, bg=SURF, fg=MUT2)
        self.preset_state.pack(anchor='w')

        c = self.card('Kundenprofil',
                      'Den Look eines Kunden speichern und mit einem Klick wieder laden.')
        row = tk.Frame(c, bg=SURF)
        row.pack(anchor='w', pady=(14, 2), fill='x')
        self.profile_name = tk.StringVar()
        self.profile_box = ttk.Combobox(row, textvariable=self.profile_name,
                                        values=sorted(self._profiles().keys()),
                                        width=24, font=F_S, style='DVE.TCombobox')
        self.profile_box.pack(side='left')
        self.profile_box.bind('<<ComboboxSelected>>', self.profile_load)
        Pill(row, 'Speichern', self.profile_save, primary=False,
             width=130, bg=SURF).pack(side='left', padx=10)
        self.profile_lbl = tk.Label(c, text='', font=F_S, bg=SURF, fg=MUT2)
        self.profile_lbl.pack(anchor='w')

    # ---------- Sektion: Hook ----------
    def build_hook(self):
        c = self.card('Hook',
                      'Die ersten Sekunden entscheiden, ob jemand dranbleibt. '
                      '65–71 % wischen oder bleiben in den ersten 3 Sekunden.')
        self.switch_row(c, 'Hook aktiv',
                        'Der Videoanfang läuft dichter und energischer. '
                        'Danach übernimmt der gewählte Modus.',
                        self.intro_var, first=True)
        r = self.row(c, 'Länge',
                     'Faustregel: Shorts 8–15 s, YouTube 30 s, langes Format 60 s.')
        Segmented(r, [('8 s', 8), ('15 s', 15), ('30 s', 30), ('60 s', 60)],
                  self.hooksec_var).pack()
        r = self.row(c, 'Stärke',
                     'Wie dicht die Momente im Hook stehen. Stark: fast jeder Satz '
                     'bekommt einen Effekt (TikTok). Sanft: nur die Highlights (Doku).')
        Segmented(r, [('Sanft', 'sanft'), ('Normal', 'normal'), ('Stark', 'stark')],
                  self.hookpow_var).pack()
        self.switch_row(c, 'Sofort-Hook',
                        'Das stärkste frühe Statement steht als Karte ab dem ersten '
                        'Bild — kein leerer Videoanfang.',
                        self.ihook_var)

        c = self.card('Watchtime halten',
                      'Gegen das Wegklicken in der Mitte des Videos.')
        r = self.row(c, 'Kein Leerlauf länger als',
                     'Reißt eine Strecke ohne Ereignis zu weit auf, wird das stärkste '
                     'Wort darin zu einem dezenten Moment erhoben.', first=True)
        Segmented(r, [('8 s', 8), ('12 s', 12), ('20 s', 20), ('Aus', 0)],
                  self.retgap_var).pack()
        self.switch_row(c, 'Pattern-Interrupt',
                        'Auch ohne Text gibt die Kamera in ruhigen Passagen alle paar '
                        'Sekunden einen Impuls. Auf B-Roll bleibt sie ruhig.',
                        self.pint_var)
        self.switch_row(c, 'Safe-Zone 9:16',
                        'Im Hochformat bleiben die TikTok-Buttons rechts und die '
                        'Beschreibung unten frei.', self.safe_var)

    # ---------- Sektion: Text ----------
    def build_text(self):
        c = self.card('Typografie', 'Die Schrift der Captions.')
        self.font_grid = tk.Frame(c, bg=SURF)
        self.font_grid.pack(anchor='w', fill='x', pady=(14, 0))
        cur_file = self.cfg['fonts'].get('display', 'fonts/serif.ttf').replace('\\\\', '/')
        self.font_id = tk.StringVar(value=next((f['id'] for f in FONT_CHOICES
                                                if f['file'] == cur_file), 'kino'))
        self.font_tiles = {}
        self.font_cells = []
        for fc in FONT_CHOICES:
            cell = tk.Frame(self.font_grid, bg=SURF)
            try:
                img = tk.PhotoImage(file=make_font_tile(fc['file']))
            except Exception:
                img = None
            self._imgs.append(img)
            b = tk.Label(cell, image=img, text=fc['label'] if img is None else '',
                         bg=TILE, cursor='hand2', highlightthickness=2)
            b.pack()
            b.bind('<Button-1>', lambda e, fid=fc['id']: self.select_font(fid))
            tk.Label(cell, text=fc['label'], font=('Segoe UI', 8), bg=SURF,
                     fg=MUT2).pack(pady=(4, 0))
            self.font_tiles[fc['id']] = b
            self.font_cells.append(cell)
        self.reflow_fonts(5)
        self.select_font(self.font_id.get())

        c = self.card('Stil & Farbe')
        r = self.row(c, 'Text-Stil',
                     'Klassisch: flach, ruhig, clean.  3D: Tiefe, Extrusion, Licht — '
                     'wie ein Objekt im Raum.  Kinetisch: der Text lebt und reagiert '
                     'auf die Betonung.  3D + Kinetisch: der volle Look.', first=True)
        Segmented(r, [('Klassisch', 'klassisch'), ('3D', '3d'),
                      ('Kinetisch', 'kinetisch'), ('3D + Kin.', '3d kinetisch')],
                  self.style_var).pack()
        r = self.row(c, 'Farbwelt',
                     'Automatisch: die Captions greifen die Farben der Szene auf '
                     '(Empfehlung).  Elegantes Schwarz: für helle Bilder — Studio, '
                     'weiße Wand, Tageslicht.  Elegantes Weiß: der High-End-Look auf '
                     'dunklem und farbigem Material.')
        Segmented(r, [('Automatisch', 'auto'), ('Schwarz', 'schwarz'),
                      ('Weiß', 'weiss')], self.color_var).pack()
        self.setting(c, 'Abdunkeln hinter dem Text',
                     'Wie stark das Bild hinter einem großen Wort abdunkelt, damit der '
                     'Text steht. Zu viel wirkt billig — 30–45 % ist der Bereich.')
        Slider(c, self.dim_var, 0, 70, ' %').pack(fill='x')

        c = self.card('Premium-Typo',
                      'Die drei Stellschrauben, an denen man 2026 teure Captions von '
                      'Vorlagen-Look unterscheidet.')
        self.setting(c, 'Standzeit pro Wortgruppe', 'Wie lange eine Wortgruppe mindestens '
                     'stehen bleibt. Unter 600 ms wirkt es gehetzt und billig — '
                     '600–900 ms ist der aktuelle High-End-Standard.')
        Slider(c, self.hold_var, 0, 1200, ' ms').pack(fill='x')
        self.setting(c, 'Beat-Sync', 'Wie stark Text auf die Betonung der Stimme reagiert. '
                     'Text und Sprache treffen denselben Akzent — der Grund, warum teure '
                     'Edits „auf den Punkt" wirken.')
        Slider(c, self.beat_var, 0, 100, ' %').pack(fill='x')
        self.setting(c, 'Schatten der Person auf den Text',
                     'Die Person wirft einen weichen Schatten auf den Text hinter ihr. '
                     'Ohne ihn ist der Text nur ausgeschnitten — mit ihm sitzt er im Raum.')
        Slider(c, self.pshadow_var, 0, 100, ' %').pack(fill='x')
        self.setting(c, 'Abstand zwischen Zahl-Captions',
                     'Relevante Zahlen (Prozent, Umsatz, Millionen, Faktor) werden zum '
                     'großen Moment. Damit es nicht bei jeder Zahl knallt, liegt hier der '
                     'Mindestabstand. 0 = keine Bremse.')
        Slider(c, self.zahl_var, 0, 60, ' s').pack(fill='x')

        c = self.card('Sprache')
        r = self.row(c, 'Sprache im Video', 'Auto erkennt die Sprache selbst.',
                     first=True)
        Segmented(r, LANG_SEG, self.lang_var).pack()

    # ---------- Sektion: Effekte ----------
    def build_feintuning(self):
        c = self.card('Effekte', 'Welche Caption-Effekte überhaupt vorkommen dürfen.')
        chips = tk.Frame(c, bg=SURF)
        chips.pack(anchor='w', pady=(14, 6))
        for key, title, _d in EFFECTS:
            Chip(chips, title, self.fx_vars[key], self.mark_custom,
                 bg=SURF).pack(side='left', padx=(0, 8))
        for _k, title, desc in EFFECTS:
            r = tk.Frame(c, bg=SURF)
            r.pack(fill='x', pady=(6, 0))
            tk.Label(r, text=title, font=('Segoe UI Semibold', 9), bg=SURF, fg=FG,
                     width=18, anchor='nw').pack(side='left')
            d = tk.Label(r, text=desc, font=F_S, bg=SURF, fg=MUT,
                         justify='left', anchor='w')
            d.pack(side='left', fill='x')
            self._wrap(d, 0.62)

        c = self.card('Dynamik', 'Die künstliche Kamera-Bewegung im Video.')
        r = self.row(c, 'Bewegung',
                     'Ruhig: dezent, fast unmerklich — Interviews, Corporate.  '
                     'Ausgewogen: sichtbare, ruhige Bewegung — Standard.  '
                     'Energisch: häufige, kräftige Bewegungen — Shorts und Reels.',
                     first=True)
        Segmented(r, [(k, k) for k in DYNAMIK], self.dynamik_var).pack()
        self.dynamik_var.trace_add('write', lambda *a: self.apply_dynamik())
        self.setting(c, 'Crash-Zoom auf den stärksten Moment',
                     'Ein schneller, harter Zoom auf den einen wichtigsten Moment im Clip '
                     '— mit knackigem Stopp. Der Signature-Move für Aufmerksamkeit. '
                     'Nur einmal pro Clip, damit es nicht billig wird. 0 = aus.')
        Slider(c, self.crash_var, 0, 100, ' %').pack(fill='x')
        r = self.row(c, 'Whip-Pan an Abschnittsgrenzen',
                     'Schneller, verwischter Kameraschwenk als Übergang zwischen '
                     'Abschnitten. Sehr energisch — passt zu Shorts/Reels, nicht zu '
                     'Clean oder Cinematic.')
        Switch(r, self.whip_var).pack(side='right')

        c = self.card('Freistellung & Masken',
                      'Die Person wird vom Hintergrund freigestellt, damit Wörter '
                      'HINTER ihr liegen können.')
        r = self.row(c, 'Herausschieben',
                     'Das Wort steckt hinter der Person und wird von ihr '
                     'hervorgeschoben — erst der Teil direkt hinter ihr, dann wächst '
                     'es nach beiden Seiten heraus. Immer: der Signature-Look. '
                     'Auto: kommt abwechselnd mit anderen Einflügen.', first=True)
        Segmented(r, [('Auto', 'auto'), ('Immer', 'immer'), ('Aus', 'aus')],
                  self.emerge_var).pack()
        r = self.row(c, 'Maskenqualität',
                     'Wie fein die Freistellung rechnet. Standard ist schnell, aber '
                     'die Kante matscht an Haaren und Schultern. Hoch ist der '
                     'Empfehlungswert. Maximum holt einzelne Haarsträhnen und '
                     'Brillenbügel — kostet aber spürbar Rechenzeit.')
        Segmented(r, [('Standard', 'standard'), ('Hoch', 'hoch'),
                      ('Maximum', 'maximum')], self.mask_var).pack()

        c = self.card('Lebendige Typo',
                      '13 Animationen. Das Wort reagiert auf den Satz: „Deutschland '
                      'bricht seine Versprechen" — das Wort zerbricht wirklich.')
        self.switch_row(c, 'Animationen aktiv',
                        'Die KI-Regie wählt die passende Animation aus dem Inhalt. '
                        'Im Momente-Editor kannst du jede einzeln überschreiben.',
                        self.anim_var, first=True)

    # ---------- Sektion: Sound ----------
    def build_sound(self):
        c = self.card('Sound-Pack',
                      'Ohne Sound-Pack läuft das Video OHNE Sound-Effekte. Es gibt '
                      'keine synthetischen Ersatztöne mehr — lieber Stille als ein '
                      'billiger Sound. Hier lädst du echte, aufgenommene Sounds '
                      '(CC0 = Public Domain, kommerziell frei, keine Namensnennung).')
        kr = tk.Frame(c, bg=SURF)
        kr.pack(fill='x', pady=(14, 4))
        tk.Label(kr, text='Freesound-Key', font=F_S, bg=SURF, fg=MUT,
                 width=14, anchor='w').pack(side='left')
        self.fskey = tk.Entry(kr, font=F, bg=SURF2, fg=FG, insertbackground=ACCENT,
                              relief='flat', highlightthickness=0, show='•')
        self.fskey.pack(side='left', fill='x', expand=True, ipady=7)
        self.fskey.insert(0, self._fs_key_load())
        tk.Label(c, text='Kostenlos auf freesound.org → Settings → API credentials. '
                 'Der Schlüssel bleibt auf diesem Rechner.',
                 font=F_S, bg=SURF, fg=MUT2).pack(anchor='w', pady=(4, 0))
        br = tk.Frame(c, bg=SURF)
        br.pack(anchor='w', pady=(12, 4))
        self.pack_btn = Pill(br, 'Echte Sounds laden', self.pack_fetch,
                             primary=False, width=190, bg=SURF)
        self.pack_btn.pack(side='left')
        self.pack_pick_btn = Pill(br, 'Anhören & auswählen', self.pack_popup,
                                  primary=False, width=190, bg=SURF)
        self.pack_pick_btn.pack(side='left', padx=10)
        self.pack_lbl = tk.Label(c, text='', font=F_S, bg=SURF, fg=MUT, anchor='w',
                                 justify='left')
        self.pack_lbl.pack(anchor='w', pady=(4, 0))
        self._wrap(self.pack_lbl, 0.92)
        self.pack_status()

        c = self.card('Lautstärke')
        self.setting(c, 'Sound-Effekte',
                     'Impact bei großen Wörtern, Whoosh bei Einflügen, und die '
                     'Animations-Sounds (etwas bricht, fällt, steigt). Alles wird '
                     'passend zur Betonung gesetzt. 0 % = aus.')
        Slider(c, self.sfxvol_var, 0, 100, ' %').pack(fill='x')
        self.sfxvol_var.trace_add('write', lambda *a: self.mark_custom())

    # ---------- Sektion: Ausgabe ----------
    def build_output(self):
        c = self.card('Ausgabe')
        r = self.row(c, 'Qualität',
                     '720p reicht für Social, 1080p ist der Standard. 4K nur bei '
                     '4K-Quellmaterial — dauert deutlich länger.', first=True)
        Segmented(r, RES_SEG, self.res_var).pack()
        r = self.row(c, 'Tempo',
                     'Wie stark beim Speichern komprimiert wird. Der Look ändert sich '
                     'dabei NICHT — nur Rechenzeit und Dateigröße.')
        Segmented(r, [('Schnell', 'schnell'), ('Standard', 'standard'),
                      ('Maximal', 'maximal')], self.speed_var).pack()
        self.switch_row(c, 'Premiere-Master (ProRes)',
                        'Zusätzlich eine verlustarme .mov für den Schnitt.',
                        self.master_var)

    # ---------- Sektion: Profi ----------
    def build_profi(self):
        c = self.card('Feinregler', 'Der Regler, der den Charakter bestimmt.')
        self.setting(c, 'Abstand zwischen Momenten',
                     'Mindest-Pause zwischen zwei großen Caption-Momenten. Klein '
                     '(2–4 s): viele Effekte, sehr dicht — TikTok. Groß (10–15 s): '
                     'seltene, dafür wirkungsvolle Momente — lange YouTube-Videos. '
                     'Die normalen Untertitel laufen davon unabhängig weiter.')
        Slider(c, self.gap_var, 2, 15, ' s').pack(fill='x')
        for v in (self.gap_var, self.dim_var):
            v.trace_add('write', lambda *a: self.mark_custom())

        c = self.card('Intelligenz')
        self.switch_row(c, 'KI-Regie',
                        'Wählt Keywords, Phrasen, Effekte und Animationen wie ein '
                        'Editor. Wenige Cent pro Video.', self.ai_var, first=True)

        c = self.card('Keywords', 'Wörter, die immer oder nie hervorgehoben werden.')
        self.setting(c, 'Immer hervorheben',
                     'Kommagetrennt, z. B.: Schufa, Score, Konto')
        self.kw_in = tk.Entry(c, font=F, bg=SURF2, fg=FG, insertbackground=ACCENT,
                              relief='flat', highlightthickness=0)
        self.kw_in.insert(0, ', '.join(self.cfg['keywords'].get('include') or []))
        self.kw_in.pack(fill='x', ipady=9)
        self.setting(c, 'Nie hervorheben')
        self.kw_ex = tk.Entry(c, font=F, bg=SURF2, fg=FG, insertbackground=ACCENT,
                              relief='flat', highlightthickness=0)
        self.kw_ex.insert(0, ', '.join(self.cfg['keywords'].get('exclude') or []))
        self.kw_ex.pack(fill='x', ipady=9)


    # ---------- Zustand sichern ----------
    def _ui_state_path(self):
        return os.path.join(HERE, 'ui_state.json')

    def _ui_state_load(self):
        try:
            return json.load(open(self._ui_state_path(), encoding='utf-8'))
        except Exception:
            return {}

    def on_close(self):
        """Alles sichern, damit das Programm genau so wieder aufgeht, wie es
        geschlossen wurde."""
        try:
            self.save_cfg()                  # alle Einstellungen -> config.yaml
        except Exception:
            pass
        try:
            self._fs_key()                   # Freesound-Key -> sfx/.freesound_key
        except Exception:
            pass
        try:
            self.ui_state['section'] = self.current_section
            self.ui_state['geometry'] = self.root.geometry()
            json.dump(self.ui_state, open(self._ui_state_path(), 'w',
                                          encoding='utf-8'),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
        self.root.destroy()

    # ---------- Sound-Pack ----------
    def _fs_key_path(self):
        return os.path.join(HERE, 'sfx', '.freesound_key')

    def _fs_key_load(self):
        p = self._fs_key_path()
        if os.path.exists(p):
            try:
                return open(p, encoding='utf-8').read().strip()
            except Exception:
                pass
        return os.environ.get('FREESOUND_API_KEY', '')

    def _fs_key(self):
        k = self.fskey.get().strip()
        if k:
            try:
                os.makedirs(os.path.dirname(self._fs_key_path()), exist_ok=True)
                open(self._fs_key_path(), 'w', encoding='utf-8').write(k)
            except Exception:
                pass
        return k

    def pack_status(self):
        sfx_pack.scan_eigene()
        st = sfx_pack.pack_status()
        man = st['manifest']
        eig = sum(1 for v in man.values() if v.get('eigen'))
        if st['belegt'] == 0:
            txt = ('⚠  Kein Sound-Pack — deine Videos bekommen aktuell KEINE '
                   'Sound-Effekte. Key eintragen und laden. Eigene Dateien kannst du '
                   'auch direkt in sfx\\pack ablegen (z. B. impact.wav).')
        else:
            txt = (f"{st['belegt']} von {st['gesamt']} Sounds belegt"
                   + (f', davon {eig} eigene Dateien' if eig else ' (CC0)')
                   + '.  Ordner: sfx\\pack')
        self.pack_lbl.configure(text=txt)

    def pack_fetch(self):
        key = self._fs_key()
        if not key:
            messagebox.showinfo('Kein Schlüssel',
                                'Bitte zuerst den Freesound-Key eintragen.\n'
                                'Kostenlos auf freesound.org → Settings → '
                                'API credentials.')
            return
        self.pack_btn.set_enabled(False)
        self.pack_lbl.configure(text='Lade CC0-Sounds …')

        def work():
            lines = []
            try:
                ok, fail = sfx_pack.fetch_pack(key, progress=lines.append)
                self.q.put(('pack', (ok, fail, lines)))
            except Exception as e:
                self.q.put(('pack', (0, [str(e)], lines)))
        threading.Thread(target=work, daemon=True).start()

    def pack_play(self, path):
        """Sound anhoeren. Auf Windows ueber winsound, sonst ueber ffplay."""
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            try:
                subprocess.Popen(['ffplay', '-nodisp', '-autoexit', '-v', 'quiet',
                                  path], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def pack_popup(self):
        """Vorhoeren und auswaehlen. Welcher Sound GUT klingt, kann kein Programm
        messen - das entscheidet das Ohr. Darum diese Liste."""
        key = self._fs_key()
        pdir = sfx_pack.pack_dir()
        top = tk.Toplevel(self.root)
        top.title('Sound-Pack — anhören und auswählen')
        top.configure(bg=BG)
        top.geometry('900x680')
        tk.Label(top, text='Sound-Pack', font=F_H1, bg=BG, fg=FG).pack(
            anchor='w', padx=24, pady=(20, 2))
        tk.Label(top, text='Pro Zeile: was der Sound im Video macht. „Andere“ holt '
                 'weitere CC0-Kandidaten zum Vergleichen — hör sie an und nimm den, '
                 'der sitzt.', font=F_S, bg=BG, fg=MUT, wraplength=840,
                 justify='left').pack(anchor='w', padx=24, pady=(0, 12))
        cv = tk.Canvas(top, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(top, orient='vertical', command=cv.yview)
        inner = tk.Frame(cv, bg=BG)
        inner.bind('<Configure>',
                   lambda e: cv.configure(scrollregion=cv.bbox('all')))
        cv.create_window((0, 0), window=inner, anchor='nw', width=860)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side='left', fill='both', expand=True, padx=(24, 0), pady=(0, 20))
        sb.pack(side='right', fill='y', pady=(0, 20))
        self.active_canvas = cv
        man = sfx_pack.load_manifest(pdir)

        for slot, meta in sfx_pack.SLOTS.items():
            cd = Card(inner, pad=14, bg=BG, fill=SURF)
            cd.pack(fill='x', pady=(0, 8))
            b = cd.body
            head = tk.Frame(b, bg=SURF)
            head.pack(fill='x')
            tk.Label(head, text=slot.upper(), font=('Segoe UI Semibold', 10),
                     bg=SURF, fg=FG, width=13, anchor='w').pack(side='left')
            tk.Label(head, text=meta['use'], font=F_S, bg=SURF, fg=MUT,
                     anchor='w').pack(side='left', fill='x', expand=True)
            cur = man.get(slot, {})
            src_txt = ('eigene Datei' if cur.get('eigen')
                       else (cur.get('name', '')[:28] + ' (CC0)') if cur
                       else 'synthetisch')
            lbl = tk.Label(b, text='Aktuell: ' + src_txt, font=F_S, bg=SURF,
                           fg=MUT2, anchor='w')
            lbl.pack(anchor='w', pady=(4, 0))
            btns = tk.Frame(b, bg=SURF)
            btns.pack(anchor='w', pady=(6, 0))
            f_cur = os.path.join(pdir, slot + '.wav')
            Pill(btns, '▶ Anhören', lambda p=f_cur: self.pack_play(p),
                 primary=False, width=120, bg=SURF).pack(side='left')
            alt_btn = Pill(btns, 'Andere', primary=False, width=110, bg=SURF,
                           command=lambda: None)
            alt_btn.command = (lambda s=slot, l=lbl, bx=b, ab=alt_btn:
                               self.pack_alts(s, l, bx, key, ab))
            alt_btn.pack(side='left', padx=8)

    def pack_alts(self, slot, lbl, box, key, btn=None):
        """Holt Alternativen fuer einen Slot und listet sie zum Anhoeren auf.
        Nochmal klicken klappt die Liste wieder ein."""
        if not key:
            messagebox.showinfo('Kein Schlüssel', 'Bitte erst den Freesound-Key '
                                                  'eintragen.')
            return
        if getattr(box, '_alts', None):
            box._alts.destroy()
            box._alts = None
            if btn:
                btn.set_text('Andere')
            return                              # zweiter Klick = wieder einklappen
        if btn:
            btn.set_text('Einklappen')
        wrap = tk.Frame(box, bg=SURF)
        wrap.pack(fill='x', pady=(8, 0))
        box._alts = wrap
        tk.Label(wrap, text='Suche …', font=F_S, bg=SURF, fg=MUT).pack(anchor='w')

        def work():
            try:
                cands = sfx_pack.search(slot, key, n=6)
            except Exception as e:
                cands = []
            self.root.after(0, lambda: show(cands))

        def show(cands):
            for w in wrap.winfo_children():
                w.destroy()
            if not cands:
                tk.Label(wrap, text='Keine CC0-Treffer.', font=F_S, bg=SURF,
                         fg=MUT).pack(anchor='w')
                return
            for c in cands:
                r = tk.Frame(wrap, bg=SURF)
                r.pack(fill='x', pady=2)
                # Schlagworte mit anzeigen: so siehst du sofort, WAS der Sound ist
                # (ein 'Impact' kann ein Glas-Crash sein - genau der Fall vorher).
                tg = ', '.join(c.get('tags', [])[:4])
                txt = f"{c['name'][:34]}  ·  {c['duration']}s  ·  {c['downloads']}×"
                if tg:
                    txt += f"\n{tg}"
                tk.Label(r, text=txt, font=F_S, bg=SURF, fg=MUT, anchor='w',
                         justify='left').pack(side='left', fill='x', expand=True)
                Pill(r, 'Nehmen', lambda cc=c, s=slot, l=lbl: self.pack_take(cc, s, l),
                     primary=False, width=100, bg=SURF).pack(side='right')
        threading.Thread(target=work, daemon=True).start()

    def pack_take(self, cand, slot, lbl):
        pdir = sfx_pack.pack_dir()
        os.makedirs(pdir, exist_ok=True)
        dest = os.path.join(pdir, slot + '.wav')

        def work():
            try:
                sfx_pack.fetch_one(cand, dest)
                man = sfx_pack.load_manifest(pdir)
                man[slot] = {'id': cand['id'], 'name': cand['name'],
                             'license': 'CC0',
                             'quelle': f"https://freesound.org/s/{cand['id']}/",
                             'dauer': cand['duration']}
                sfx_pack.save_manifest(pdir, man)
                self.root.after(0, lambda: (
                    lbl.configure(text='Aktuell: ' + cand['name'][:28] + ' (CC0)'),
                    self.pack_play(dest), self.pack_status()))
            except Exception as e:
                self.root.after(0, lambda: lbl.configure(
                    text='Fehler beim Laden: ' + type(e).__name__))
        threading.Thread(target=work, daemon=True).start()

    # ---------- Preset-Logik ----------
    def apply_preset(self, name):
        if getattr(self, 'busy', False):
            return
        p = PRESETS[name]
        self._applying = True
        for k, v in self.fx_vars.items():
            v.set(k in p['fx'])
        self.wpg_var.set(p['wpg'])
        self.gap_var.set(p['gap'])
        self.dim_var.set(p['dim'])
        self.sfxvol_var.set(p['sfxvol'])
        self.dynamik_var.set(p['dynamik'])
        if p.get('font'):
            self.select_font(p['font'])
        if p.get('style'):
            self.style_var.set(p['style'])
        if p.get('plattform'):
            self.platform_var.set(p['plattform'])
        self.apply_dynamik()
        self._applying = False
        self.active_preset = name
        self.mark_preset_tiles(name)
        self.preset_state.configure(text=f'Aktiv: {name}')

    def apply_dynamik(self):
        d = DYNAMIK[self.dynamik_var.get()]
        self.cam_str.set(d['strength'])
        self.freq_var.set(d['freq'])
        self.capzoom_var.set(d['capzoom'])
        self.drift_var.set(d['drift'])
        self.kwcam_var.set(d['kw'])
        self.crash_var.set(d['crash'])
        self.whip_var.set(d['whip'])
        if not self._applying:
            self.mark_custom()

    def mark_custom(self):
        if self._applying:
            return
        self.active_preset = None
        self.mark_preset_tiles(None)
        self.preset_state.configure(text='Aktiv: Eigene Einstellungen')

    def mark_preset_tiles(self, name):
        for n, (cell, dot, _) in self.preset_tiles.items():
            dot.configure(fg=ACCENT if n == name else SURF3)

    def detect_preset(self):
        cur_fx = {k for k, v in self.fx_vars.items() if v.get()}
        for name, p in PRESETS.items():
            if cur_fx == set(p['fx']) and self.wpg_var.get() == p['wpg'] \
               and self.gap_var.get() == p['gap'] and self.dim_var.get() == p['dim'] \
               and self.font_id.get() == p.get('font', self.font_id.get()) \
               and self.style_var.get() == p.get('style', self.style_var.get()) \
               and self.platform_var.get() == p.get('plattform',
                                                     self.platform_var.get()):
                self.active_preset = name
                self.mark_preset_tiles(name)
                self.preset_state.configure(text=f'Aktiv: {name}')
                return
        self.active_preset = None
        self.preset_state.configure(text='Aktiv: Eigene Einstellungen')

    # ---------- Auswahl ----------
    def select_font(self, fid):
        if getattr(self, 'busy', False) and not self._applying:
            return
        self.font_id.set(fid)
        for k, b in self.font_tiles.items():
            b.configure(highlightbackground=GOLD if k == fid else TILE,
                        highlightcolor=GOLD if k == fid else TILE)

    def _profile_path(self):
        return os.path.join(HERE, 'profile.json')

    def _profiles(self):
        try:
            return json.load(open(self._profile_path(), encoding='utf-8'))
        except Exception:
            return {}

    def pick_video(self):
        """Ein oder mehrere Videos waehlen. Mehrere = Warteschlange: sie rendern
        automatisch nacheinander durch."""
        paths = filedialog.askopenfilenames(
            title='Video(s) wählen — mehrere mit Strg oder Shift',
            filetypes=[('Videos', '*.mp4 *.mov *.mkv *.avi *.m4v'), ('Alle', '*.*')])
        if not paths:
            return
        paths = list(paths)
        self.video_path = paths[0]
        self.batch = paths[1:]
        self.show_video_label()
        if self.batch:
            self.log_line(f'{len(paths)} Videos gewählt — sie rendern nacheinander '
                          f'durch (Warteschlange).')

    def show_video_label(self):
        name = os.path.basename(self.video_path) if self.video_path else ''
        extra = f'  (+{len(self.batch)} in Warteschlange)' if self.batch else ''
        self.video_lbl.configure(text=(name + extra) if name
                                 else 'Kein Video gewählt', fg=FG if name else MUT)
    def check_transcript(self):
        if getattr(self, 'busy', False):
            return
        if not self.video_path:
            messagebox.showinfo('DouchkoVE', 'Bitte zuerst ein Video wählen.')
            return
        tpath = os.path.splitext(self.video_path)[0] + '_transcript2.json'
        if os.path.exists(tpath):
            self.open_transcript_editor(tpath)
            return
        if self.proc:
            return
        self.set_busy(True)
        self.status.configure(text='Transkribiere für die Kontrolle …')
        self.log_line('Transkription läuft (nur Transkript, kein Render) …')
        cmd = [sys.executable.replace('pythonw', 'python'), '-u',
               os.path.join(HERE, 'render.py'), self.video_path, '--transcribe-only']
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        def worker():
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', creationflags=flags, cwd=HERE,
                               env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            self.root.after(0, lambda: self._transcript_done(tpath, r.returncode))
        threading.Thread(target=worker, daemon=True).start()

    def _transcript_done(self, tpath, code):
        self.set_busy(False)
        self.status.configure(text='Bereit')
        if code == 0 and os.path.exists(tpath):
            self.open_transcript_editor(tpath)
        else:
            messagebox.showerror('DouchkoVE', 'Transkription fehlgeschlagen - '
                                 'Details im Log.')

    def open_transcript_editor(self, tpath):
        try:
            words = json.load(open(tpath, encoding='utf-8'))
        except Exception:
            messagebox.showerror('DouchkoVE', 'Transkript-Datei defekt — löschen '
                                 'und erneut pruefen.')
            return
        win = tk.Toplevel(self.root)
        win.title('Transkript prüfen')
        win.configure(bg=BG)
        win.geometry('860x660')
        tk.Label(win, text='Verhoerer korrigieren - Zeile anklicken, Woerter tippen. '
                 'Timing bleibt erhalten.', font=F_S, bg=BG, fg=MUT,
                 wraplength=700, justify='left').pack(anchor='w', padx=16, pady=(12, 6))
        bar = tk.Frame(win, bg=BG)
        inner = popup_scroll(win, bar)
        CHUNK = 10
        rows = []
        for a in range(0, len(words), CHUNK):
            grp = words[a:a + CHUNK]
            fr = tk.Frame(inner, bg=SURF, padx=8, pady=4)
            fr.pack(fill='x', pady=2)
            tk.Label(fr, text=f"{grp[0].get('start', 0):6.1f}s", font=F_S, bg=SURF,
                     fg=MUT, width=7).pack(side='left')
            tv = tk.StringVar(value=' '.join(str(w.get('word', '')).strip()
                                             for w in grp))
            tk.Entry(fr, textvariable=tv, font=F_M, bg=SURF2, fg=FG,
                     insertbackground=FG, relief='flat'
                     ).pack(side='left', fill='x', expand=True, padx=(4, 12), ipady=4)
            rows.append((a, grp, tv))

        def save():
            # Liste komplett neu aufbauen - index-sicher, auch wenn Zeilen
            # die Wortzahl aendern
            final, changed = [], 0
            for a, grp, tv in rows:
                new_words = tv.get().split()
                old_words = [str(w.get('word', '')).strip() for w in grp]
                if new_words == old_words:
                    final.extend(grp)
                    continue
                changed += 1
                if len(new_words) == len(grp):
                    for w, nw in zip(grp, new_words):     # 1:1 - Timing exakt behalten
                        w['word'] = nw
                    final.extend(grp)
                elif not new_words:                       # Zeile geleert = loeschen
                    continue
                else:
                    # Wortzahl geaendert: Timings gleichmaessig ueber die Zeile verteilen
                    t0 = float(grp[0].get('start', 0.0))
                    t1 = float(grp[-1].get('end', t0 + 1.0))
                    n = len(new_words)
                    for k, nw in enumerate(new_words):
                        final.append({'word': nw,
                                      'start': round(t0 + (t1 - t0) * k / n, 3),
                                      'end': round(t0 + (t1 - t0) * (k + 1) / n, 3)})
            json.dump(final, open(tpath, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            win.destroy()
            self.log_line(f'Transkript gespeichert ({changed} Zeilen korrigiert). '
                          'Der Render nutzt es automatisch.')
        Pill(bar, 'Speichern', save, primary=True, width=170,
             bg=BG).pack(side='right', padx=16, pady=12)
        tk.Label(bar, text='Korrekturen wirken beim nächsten Render automatisch.',
                 font=F_S, bg=BG, fg=MUT2).pack(side='left', padx=16)

    # -------- Partieller Re-Render: nur geaenderte Momente ins fertige Video
    def partial_rerender(self, changed):
        base = os.path.splitext(self.video_path)[0]
        target = next((base + ext for ext in ('_captions.mp4', '_captions.mov')
                       if os.path.exists(base + ext)), None)
        if not target:
            self.log_line('Noch kein fertiges Video vorhanden - die Aenderungen '
                          'greifen automatisch beim naechsten Render.')
            return
        if self.proc:
            messagebox.showinfo('DouchkoVE', 'Es läuft gerade ein Render — '
                                'bitte kurz warten.')
            return
        act = [m for m in changed if isinstance(m, dict) and 'zeit' in m]
        if not act:
            return
        if not messagebox.askyesno(
                'DouchkoVE',
                f'{len(act)} Moment(e) geaendert.\n\nNur diese Stellen neu rendern '
                f'und direkt in\n{os.path.basename(target)} einsetzen? (schnell)'):
            self.log_line('Ok — die Änderungen greifen beim nächsten Voll-Render.')
            return
        # Zeitfenster bilden und ueberlappende zusammenlegen
        wins = sorted((max(float(m['zeit']) - 0.8, 0.0), float(m['zeit']) + 5.0)
                      for m in act)
        merged = [list(wins[0])]
        for a, b in wins[1:]:
            if a <= merged[-1][1] + 0.5:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        self.set_busy(True)
        self.status.configure(text='Momente werden neu gerendert ...')
        self.side_status.configure(text='Rendert ...')
        self.log_line(f'Partieller Re-Render: {len(merged)} Segment(e) -> '
                      f'{os.path.basename(target)}')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        env = dict(os.environ, PYTHONIOENCODING='utf-8')

        def worker():
            import tempfile as _tf
            ok_all = True
            for k, (t0, t1) in enumerate(merged, 1):
                seg = os.path.join(_tf.gettempdir(), f'dve_segment_{k}.mp4')
                cmd = [sys.executable.replace('pythonw', 'python'), '-u',
                       os.path.join(HERE, 'render.py'), self.video_path,
                       '--window', f'{t0:.2f}', f'{t1:.2f}',
                       '--splice-into', target, '--out', seg]
                tpath = os.path.splitext(self.video_path)[0] + '_transcript2.json'
                if os.path.exists(tpath):
                    cmd += ['--transcript', tpath]
                self.root.after(0, lambda k=k, n=len(merged):
                                self.log_line(f'Segment {k}/{n} rendert ...'))
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace',
                                   creationflags=flags, cwd=HERE, env=env)
                if r.returncode != 0:
                    ok_all = False
                    tail = (r.stdout or '').strip().splitlines()[-3:]
                    self.root.after(0, lambda t=tail:
                                    [self.log_line(x) for x in t])
                    break
            def done():
                self.set_busy(False)
                self.status.configure(text='Video aktualisiert!' if ok_all
                                      else 'Fehler beim Re-Render - Details im Log')
                self.side_status.configure(text='Bereit')
                if ok_all:
                    self.log_line(f'Fertig: {os.path.basename(target)} wurde an '
                                  f'{len(merged)} Stelle(n) aktualisiert.')
                    if messagebox.askyesno('DouchkoVE',
                                           'Momente eingesetzt! Video ansehen?'):
                        try:
                            os.startfile(target)
                        except Exception:
                            pass
            self.root.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    # Alle Regler und Schalter der GUI an einem Ort. Vorher speicherte das Profil
    # nur 9 davon - Hook-Laenge, Farbwelt, Aufloesung, Keywords und alles andere
    # gingen verloren. Wer hier eine Einstellung ergaenzt, muss nichts weiter tun.
    PROFILE_VARS = ('platform_var', 'intro_var', 'hooksec_var', 'hookpow_var',
                    'ihook_var', 'retgap_var', 'pint_var', 'safe_var',
                    'style_var', 'color_var', 'dynamik_var', 'gap_var',
                    'sfxvol_var', 'dim_var', 'anim_var', 'ai_var', 'lang_var',
                    'res_var', 'speed_var', 'master_var', 'wpg_var',
                    # Kamera-Werte: werden zwar aus der Dynamik abgeleitet, aber
                    # wenn beim Profilwechsel die Dynamik gleich bleibt, feuert der
                    # Ableiter nicht - dann blieben sie auf dem alten Stand.
                    'capzoom_var', 'drift_var', 'freq_var', 'kwcam_var',
                    'emerge_var', 'mask_var',
                    # v61 Premium-Typo
                    'hold_var', 'beat_var', 'pshadow_var', 'zahl_var',
                    'crash_var', 'whip_var')

    def profile_snapshot(self):
        snap = {'font': self.font_id.get(),
                'effekte': {k: bool(v.get()) for k, v in self.fx_vars.items()},
                'kw_in': self.kw_in.get(), 'kw_ex': self.kw_ex.get()}
        for name in self.PROFILE_VARS:
            v = getattr(self, name, None)
            if v is not None:
                snap[name] = v.get()
        return snap

    def profile_save(self):
        name = self.profile_name.get().strip()
        if not name:
            self.profile_lbl.configure(text='Bitte erst einen Namen eingeben.')
            return
        profs = self._profiles()
        profs[name] = self.profile_snapshot()   # der KOMPLETTE Zustand
        json.dump(profs, open(self._profile_path(), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        self.profile_box['values'] = sorted(profs.keys())
        self.profile_lbl.configure(
            text=f"Profil '{name}' gespeichert ({len(profs[name])} Einstellungen)")

    def profile_load(self, *_):
        p = self._profiles().get(self.profile_name.get().strip())
        if not p:
            return
        for name in self.PROFILE_VARS:
            v = getattr(self, name, None)
            if v is not None and name in p:
                try:
                    v.set(p[name])
                except Exception:
                    pass
        # Alte Profile (vor v57) hatten kurze Schluessel - die weiter verstehen
        for alt, neu in (('platform', 'platform_var'), ('intro', 'intro_var'),
                         ('style', 'style_var'), ('dynamik', 'dynamik_var'),
                         ('gap', 'gap_var'), ('sfxvol', 'sfxvol_var'),
                         ('anim', 'anim_var'), ('lang', 'lang_var')):
            if alt in p and neu not in p:
                try:
                    getattr(self, neu).set(p[alt])
                except Exception:
                    pass
        for k, on in (p.get('effekte') or {}).items():
            if k in self.fx_vars:
                self.fx_vars[k].set(bool(on))
        if 'kw_in' in p:
            self.kw_in.delete(0, 'end'); self.kw_in.insert(0, p['kw_in'])
        if 'kw_ex' in p:
            self.kw_ex.delete(0, 'end'); self.kw_ex.insert(0, p['kw_ex'])
        self.font_id.set(p.get('font', self.font_id.get()))
        self.select_font(self.font_id.get())
        self.profile_lbl.configure(text=f"Profil '{self.profile_name.get()}' geladen")

    def save_cfg(self):
        fc = next(f for f in FONT_CHOICES if f['id'] == self.font_id.get())
        self.cfg['fonts']['display'] = fc['file']
        self.cfg['fonts']['italic'] = fc['italic']
        self.cfg['fonts']['script'] = fc.get('script', 'fonts/lobster.ttf')
        fx = [k for k, *_ in EFFECTS if self.fx_vars[k].get()] or ['behind']
        self.cfg['effects']['keyword_rotation'] = fx
        self.cfg['effects']['breathing'] = True
        self.cfg['effects']['words_per_group'] = (
            2 if self.platform_var.get() == 'durchgehend' else int(self.wpg_var.get()))
        self.cfg['effects']['dim_behind'] = round(self.dim_var.get() / 100.0, 2)
        self.cfg['effects']['chunk_hold_min'] = round(self.hold_var.get() / 1000.0, 3)
        self.cfg['effects']['zahl_gap'] = int(self.zahl_var.get())
        self.cfg['effects']['beat_sync'] = round(self.beat_var.get() / 100.0, 2)
        self.cfg['effects']['person_shadow'] = round(self.pshadow_var.get() / 100.0, 2)
        self.cfg['effects']['dim_blurin'] = round(self.dim_var.get() / 100.0 * 0.8, 2)
        self.cfg['effects']['tracking'] = True
        self.cfg['effects']['scene_lock'] = True
        self.cfg['effects']['sfx'] = self.sfxvol_var.get() > 0
        self.cfg['effects']['broll_captions'] = False
        self.cfg['effects']['sfx_volume'] = round(self.sfxvol_var.get() / 100.0, 2)
        self.cfg['keywords']['min_gap_seconds'] = int(self.gap_var.get())
        self.cfg['keywords']['auto'] = True
        self.cfg['keywords']['ai'] = bool(self.ai_var.get())
        self.cfg['keywords']['emphasize_last'] = True
        self.cfg['camera']['strength'] = round(self.cam_str.get() / 100.0, 2)
        self.cfg['camera']['crash'] = round(self.crash_var.get() / 100.0, 2)
        self.cfg['camera']['whip'] = bool(self.whip_var.get())
        self.cfg['camera']['side_every'] = int(self.freq_var.get())
        side = []
        if self.capzoom_var.get(): side.append('capzoom')
        if self.drift_var.get(): side.append('drift')
        self.cfg['camera']['side_rotation'] = side
        self.cfg['camera']['keyword_rotation'] = \
            ['caption', 'punch', 'pan', 'push', 'pullback'] if self.kwcam_var.get() else []
        self.cfg['keywords']['include'] = [w.strip() for w in self.kw_in.get().split(',') if w.strip()]
        self.cfg['keywords']['exclude'] = [w.strip() for w in self.kw_ex.get().split(',') if w.strip()]
        self.cfg['language'] = self.lang_var.get()
        self.cfg['output']['height'] = int(self.res_var.get())
        self.cfg['output']['master'] = bool(self.master_var.get())
        self.cfg['output']['speed'] = self.speed_var.get()
        self.cfg['effects']['text_style'] = self.style_var.get()
        self.cfg.setdefault('colors', {})['style'] = self.color_var.get()
        self.cfg['effects']['emerge'] = self.emerge_var.get()
        self.cfg['matting_quality'] = self.mask_var.get()
        self.cfg['effects']['density'] = self.platform_var.get()
        self.cfg['effects']['anim'] = bool(self.anim_var.get())
        self.cfg['effects']['intro_hook'] = bool(self.intro_var.get())
        self.cfg['effects']['hook_seconds'] = int(self.hooksec_var.get())
        self.cfg['effects']['instant_hook'] = bool(self.ihook_var.get())
        self.cfg['effects']['hook_strength'] = {'sanft': 0.25, 'normal': 0.5,
                                                'stark': 0.9}.get(
            self.hookpow_var.get(), 0.5)
        self.cfg['effects']['retention_gap'] = int(self.retgap_var.get())
        self.cfg['effects']['pattern_interrupt'] = 9 if self.pint_var.get() else 0
        self.cfg['effects']['safe_zone'] = bool(self.safe_var.get())
        yaml.safe_dump(self.cfg, open(CFG_PATH, 'w', encoding='utf-8'),
                       allow_unicode=True, sort_keys=False)

    FX_LIST = ('behind', 'outline', 'ground', 'blurin', 'cascade')
    FX_DE = {'behind': 'Hinter dir', 'outline': 'Nur Umriss', 'ground': 'In der Szene',
             'blurin': 'Aus der Unschärfe', 'cascade': 'Buchstaben-Aufbau'}
    FX_DE_R = {v: k for k, v in FX_DE.items()}
    POWER_DE = {'1': 'Dezent', '2': 'Normal', '3': 'Groß'}
    POWER_DE_R = {v: k for k, v in POWER_DE.items()}
    ANIM_DE = {'': 'keine', 'glitch': 'Glitch', 'puls': 'Puls', 'welle': 'Welle',
               'zittern': 'Zittern', 'neon': 'Neon', 'schub': 'Schub',
               'bruch': 'Bruch (zerbricht)', 'sturz': 'Sturz (fällt)',
               'anstieg': 'Anstieg (steigt)', 'wende': 'Wende (kippt um)',
               'druck': 'Druck (erdrückt)', 'schwund': 'Schwund (löst sich auf)',
               'knall': 'Knall (Pointe)',
               'gewicht': 'Gewicht (Strich wird fetter)',
               'schweben': 'Schweben (3D-Drift, edel)',
               'fokus': 'Fokus (kommt scharf ins Bild)',
               'enthuellen': 'Enthüllen (wird freigewischt)',
               'spur': 'Spur (Tempo mit Nachzieher)'}
    ANIM_DE_R = {v: k for k, v in ANIM_DE.items()}
    SZENE_LIST = ('auto', 'wasser', 'boden', 'wand', 'person')
    LAGE_LIST = ('auto', 'liegend', 'stehend', 'frei')
    ANIM_LIST = ('', 'glitch', 'puls', 'welle', 'zittern', 'neon', 'schub',
                 'bruch', 'sturz', 'anstieg', 'wende', 'druck', 'schwund', 'knall',
                 'gewicht', 'schweben', 'fokus', 'enthuellen', 'spur')

    def open_moments(self):
        if getattr(self, 'busy', False):
            return
        if not self.video_path:
            messagebox.showinfo('DouchkoVE', 'Bitte zuerst ein Video wählen.')
            return
        self.save_cfg()
        self.set_busy(True)
        self.side_status.configure(text='Analysiere ...')
        threading.Thread(target=self._moments_worker, daemon=True).start()

    def _moments_worker(self):
        base = os.path.splitext(self.video_path)[0]
        cmd = [sys.executable.replace('pythonw', 'python'), '-u',
               os.path.join(HERE, 'render.py'), self.video_path, '--plan-only']
        tpath = base + '_transcript2.json'
        if os.path.exists(tpath):
            cmd += ['--transcript', tpath]
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        r = subprocess.run(cmd, capture_output=True, creationflags=flags, env=env)
        self.root.after(0, lambda: self._moments_done(base + '_momente.json',
                                                      r.returncode))

    def _moments_done(self, path, rc):
        self.set_busy(False)
        self.side_status.configure(text='Bereit')
        if rc != 0 or not os.path.exists(path):
            messagebox.showinfo('DouchkoVE', 'Analyse fehlgeschlagen. Details im Protokoll.')
            return
        moments = json.load(open(path, encoding='utf-8'))
        win = tk.Toplevel(self.root)
        win.title('Captions bearbeiten')
        win.configure(bg=BG)
        win.geometry('1020x620')
        head = tk.Label(win, text='Das sind die großen Caption-Momente deines Videos. '
                                  'Text tippen, Effekt wählen, Haken raus = Moment weg. '
                                  'Speichern rendert nur geänderte Momente neu.',
                        font=F_S, bg=BG, fg=MUT)
        head.pack(anchor='w', padx=16, pady=(12, 6))
        bar = tk.Frame(win, bg=BG)
        inner = popup_scroll(win, bar)
        heads = tk.Frame(inner, bg=BG)
        heads.pack(fill='x', pady=(0, 2))
        for txt_h, w_h in (('An', 3), ('Zeit', 7), ('Text', 24), ('Effekt', 17),
                           ('Größe', 8), ('Animation', 9), ('Szene', 9), ('Lage', 9)):
            tk.Label(heads, text=txt_h, font=F_SEC, bg=BG, fg=MUT2, width=w_h,
                     anchor='w').pack(side='left', padx=2)
        rows = []
        skipped = 0
        import copy as _copy
        orig_moments = _copy.deepcopy(moments)
        for m in moments:
            if not isinstance(m, dict) or 'i' not in m:
                skipped += 1
                continue
            try:
                zeit = float(m.get('zeit', 0.0))
                fr = tk.Frame(inner, bg=SURF, padx=10, pady=6)
                fr.pack(fill='x', pady=3)
                av = tk.BooleanVar(value=bool(m.get('aktiv', True)))
                tk.Checkbutton(fr, variable=av, bg=SURF, activebackground=SURF,
                               highlightthickness=0).pack(side='left')
                tk.Label(fr, text=f"{zeit:6.1f}s", font=F_S, bg=SURF,
                         fg=MUT, width=7).pack(side='left')
                tv = tk.StringVar(value=str(m.get('text', '') or ''))
                tk.Entry(fr, textvariable=tv, font=F_M, bg=SURF2, fg=FG,
                         insertbackground=FG, relief='flat', width=22
                         ).pack(side='left', fill='x', expand=True,
                                padx=(4, 8), ipady=3)
                fv = tk.StringVar(value=self.FX_DE.get(
                    m.get('fx') if m.get('fx') in self.FX_LIST else 'behind'))
                ttk.Combobox(fr, textvariable=fv, values=list(self.FX_DE.values()),
                             width=16, state='readonly').pack(side='left', padx=2)
                pv = tk.StringVar(value=self.POWER_DE.get(
                    str(m.get('power', 2)) if str(m.get('power', 2)) in ('1', '2', '3')
                    else '2'))
                ttk.Combobox(fr, textvariable=pv, values=list(self.POWER_DE.values()),
                             width=7, state='readonly').pack(side='left', padx=2)
                nv = tk.StringVar(value=self.ANIM_DE.get(
                    m.get('anim') if m.get('anim') in self.ANIM_LIST else ''))
                ttk.Combobox(fr, textvariable=nv, values=list(self.ANIM_DE.values()),
                             width=8, state='readonly').pack(side='left', padx=2)
                # Vision-Regie: Szene (Material) und Lage - 'auto' = KI entscheidet
                sv = tk.StringVar(value=m.get('szene') if m.get('szene')
                                  in self.SZENE_LIST else 'auto')
                ttk.Combobox(fr, textvariable=sv, values=self.SZENE_LIST, width=7,
                             state='readonly').pack(side='left', padx=2)
                lv = tk.StringVar(value=m.get('lage') if m.get('lage')
                                  in self.LAGE_LIST else 'auto')
                ttk.Combobox(fr, textvariable=lv, values=self.LAGE_LIST, width=8,
                             state='readonly').pack(side='left', padx=2)
                rows.append((m, av, fv, pv, nv, tv, sv, lv))
            except Exception as e:
                skipped += 1
                try:
                    fr.destroy()
                except Exception:
                    pass
                self.log_line(f'Moment übersprungen (defekter Eintrag: {type(e).__name__})')
        if skipped:
            tk.Label(inner, text=f'{skipped} defekte Eintraege uebersprungen - '
                                 f'Momente-Datei ggf. löschen und neu analysieren.',
                     font=F_S, bg=BG, fg=MUT).pack(anchor='w', pady=6)
        if not rows:
            tk.Label(inner, text='Keine gültigen Momente gefunden.\n'
                                 'Lösche die Datei "' + os.path.basename(path) +
                                 '" neben dem Video und klicke erneut auf Momente.',
                     font=F_M, bg=BG, fg=FG, justify='left').pack(anchor='w', pady=12)

        def save():
            for m, av, fv, pv, nv, tv, sv, lv in rows:
                m['aktiv'] = bool(av.get())
                m['fx'] = self.FX_DE_R.get(fv.get(), 'behind')
                m['power'] = int(self.POWER_DE_R.get(pv.get(), '2'))
                m['anim'] = self.ANIM_DE_R.get(nv.get(), '')
                m['text'] = tv.get().strip() or m.get('text', '')
                m['szene'] = '' if sv.get() == 'auto' else sv.get()
                m['lage'] = '' if lv.get() == 'auto' else lv.get()
            json.dump(moments, open(path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            orig_by_i = {m.get('i'): m for m in orig_moments if isinstance(m, dict)}
            changed = [m for m in moments
                       if isinstance(m, dict) and m != orig_by_i.get(m.get('i'))]
            win.destroy()
            self.log_line(f'{sum(1 for m in moments if m.get("aktiv"))} aktive '
                          f'Momente gespeichert ({len(changed)} geändert).')
            if changed:
                self.partial_rerender(changed)
        Pill(bar, 'Speichern', save, primary=True, width=170,
             bg=BG).pack(side='right', padx=16, pady=12)
        tk.Label(bar, text='Geänderte Momente werden einzeln neu gerendert.',
                 font=F_S, bg=BG, fg=MUT2).pack(side='left', padx=16)

    def set_busy(self, busy):
        """Waehrend Render/Analyse: alles sperren, was den Lauf durcheinanderbringen
        koennte. Nur Abbrechen bleibt aktiv."""
        self.busy = busy
        for b in (self.render_btn, self.prev_btn, self.mom_btn, self.trans_btn):
            b.set_enabled(not busy)
        try:
            self.pick_lbl.configure(fg=MUT2 if busy else FG,
                                    cursor='arrow' if busy else 'hand2')
        except Exception:
            pass
        state = 'disabled' if busy else 'normal'
        for w in self._all_inputs():
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _all_inputs(self):
        """Alle Eingabe-Widgets der drei Tabs einsammeln."""
        out = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (tk.Entry, tk.Scale, tk.Checkbutton, ttk.Combobox)):
                    out.append(c)
                walk(c)
        for sec in self.sections.values():
            walk(sec['inner'])
        return out

    def render(self, preview=False):
        if self.proc or getattr(self, 'busy', False):
            return
        if not self.video_path:
            messagebox.showinfo('DouchkoVE', 'Bitte zuerst ein Video wählen.')
            return
        self.save_cfg()
        self.log_clear()
        self.total_frames = 0
        self.progress.set(0)
        self.set_busy(True)
        self.side_status.configure(text='Rendert ...')
        self.status.configure(text='Vorschau wird erstellt...' if preview else 'Analyse läuft …')
        base = os.path.splitext(self.video_path)[0]
        ext = '.mov' if self.master_var.get() else '.mp4'
        self.out_path = base + (('_vorschau' if preview else '_captions') + ext)
        cmd = [sys.executable.replace('pythonw', 'python'), '-u',
               os.path.join(HERE, 'render.py'), self.video_path, '--out', self.out_path]
        if preview:
            cmd += ['--duration', '15', '--preview']
        tpath = base + '_transcript2.json'
        if os.path.exists(tpath):
            cmd += ['--transcript', tpath]
            self.log_line('Vorhandenes Transkript wird genutzt (kein API-Aufruf).')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace',
                                     creationflags=flags, cwd=HERE, env=env)
        threading.Thread(target=self.reader, daemon=True).start()

    def reader(self):
        for line in self.proc.stdout:
            self.q.put(line.rstrip())
        code = self.proc.wait()
        self.q.put(('DONE', code))

    def poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple) and item[0] == 'pack':
                    ok, fail, lines = item[1]
                    self.pack_btn.set_enabled(True)
                    self.pack_status()
                    for ln in lines:
                        self.log_line(ln)
                    if fail:
                        self.log_line('Nicht belegt: ' + ', '.join(map(str, fail)))
                    continue
                if isinstance(item, tuple) and item[0] == 'DONE':
                    ok = item[1] == 0
                    self.proc = None
                    self.set_busy(False)
                    self.side_status.configure(text='Bereit')
                    self.progress.set(1.0 if ok else 0)
                    self.status.configure(text='Fertig!' if ok else 'Fehler - Details anzeigen')
                    if ok and self.batch:          # Warteschlange: naechstes Video
                        nxt = self.batch.pop(0)
                        self.video_path = nxt
                        self.show_video_label()
                        self.log_line(f'Warteschlange: starte {os.path.basename(nxt)}')
                        self.root.after(800, self.render)
                        self.set_busy(True)
                        continue
                    if ok and not self.batch and messagebox.askyesno(
                            'DouchkoVE', 'Fertig! Video jetzt ansehen?'):
                        try:
                            os.startfile(self.out_path)
                        except Exception:
                            pass
                else:
                    self.handle_line(item)
        except queue.Empty:
            pass
        self.root.after(120, self.poll_queue)

    def handle_line(self, item):
        m = re.search(r'Frame (\d+)/(\d+)', item)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            self.total_frames = tot
            self.progress.set(cur / max(tot, 1))
            eta = re.search(r'noch ~(\S+)', item)
            extra = f'  ·  noch {eta.group(1)} min' if eta else ''
            self.status.configure(text=f'Rendert...  {cur}/{tot} Frames  '
                                       f'({cur / max(tot,1):.0%}){extra}')
            return
        if 'Transkribiere' in item:
            self.status.configure(text='Transkription läuft …')
        elif 'KI-Regie analysiert' in item:
            self.status.configure(text='KI-Regie analysiert das Transkript...')
        elif 'Szenen-Analyse' in item or 'Gesichts-Tracking' in item:
            self.status.configure(text='Szenen- und Gesichts-Analyse...')
        low = item.lower()
        if any(s in low for s in ('error', 'traceback')) \
           or any(s in item for s in ('Lade', 'Keywords', 'Matting', 'Fertig', 'Transk', 'Eingabe',
                                      'FEHLER', 'Szenen', 'Kompositionen', 'KI-Regie', 'Vorschau',
                                      'nicht nutzbar')):
            self.log_line(item)

    # ---------- Log ----------
    def toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log.pack(fill='x', padx=30, pady=(0, 18))
            self.log_toggle.configure(text='Details ausblenden')
        else:
            self.log.pack_forget()
            self.log_toggle.configure(text='Details anzeigen')

    def log_line(self, s):
        self.log.configure(state='normal')
        self.log.insert('end', s + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def log_clear(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def open_folder(self):
        folder = os.path.dirname(self.video_path) if self.video_path else HERE
        os.startfile(folder) if os.name == 'nt' else subprocess.run(['xdg-open', folder])


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
