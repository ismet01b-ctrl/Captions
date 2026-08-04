# -*- coding: utf-8 -*-
"""DouchkoVE Web - vollstaendige Web-Version mit allen Reglern der Desktop-App.

Was fehlt bewusst (server-seitig sinnlos):
- Blender-Wasser (500 MB Install, sehr langsam auf CPU - hart aus).
- Freesound-Key-Verwaltung (Sound-Pack liegt auf dem Server).
- Kundenprofile (Session-basiert - hier nicht relevant).
- Windows-Setup-Sachen.

Was NEU vs. v59:
- Alle v69-v73-Effekte als Regler (Blur, Musik-Beat, Freeze, Trail, Ring,
  Split, Env-Shadow).
- Momente-Editor mit Undo/Redo (v68a).
- Font-Auswahl, Fein-Regler, Momente-Rerender.
- Preset (Look) als Startpunkt, individuelles Feintuning per JSON-Overrides.
"""
import base64
import copy
import glob
import hashlib
import hmac
import io
import json
import os
import tempfile
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from queue import Queue

import yaml
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
# v208b: Ein abgebrochener Upload ist KEINE Stoerung. Wer den Tab schliesst
# oder im Zug den Empfang verliert, kappt die Leitung mitten im Chunk -
# starlette wirft dann ClientDisconnect, und das landete als "Serverfehler"
# im Panel.
from starlette.requests import ClientDisconnect

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get('DVE_DATA', os.path.join(HERE, 'data'))
# v101p: der Remotion-Motion-Director (motion/) ist ein separater Node-Stack. Er ist
# NUR verfuegbar, wenn Node + die installierten Deps im Container liegen. Fehlt beides
# (z.B. Motion-Layer beim Build uebersprungen), bleibt das Brief-Feature einfach aus -
# der Rest der App laeuft unveraendert (Feature-Detection statt harter Kopplung).
MOTION_DIR = os.path.join(ROOT, 'motion')
MOTION_BRIEF_OK = bool(shutil.which('node')) and os.path.isdir(
    os.path.join(MOTION_DIR, 'node_modules'))
# v96p: Besitzer-Konto. Nur dieses Konto sieht/bedient die Stil-Referenzen
# (global wirksam). Ueberschreibbar per DVE_OWNER.
OWNER_EMAIL = os.environ.get('DVE_OWNER', 'ismet-01_b@hotmail.de').strip().lower()
JOBS_DIR = os.path.join(DATA, 'jobs')
CODES_FILE = os.path.join(DATA, 'codes.json')
USERS_DB = os.path.join(DATA, 'users.db')
MAX_MB = int(os.environ.get('DVE_MAX_MB', '300'))
# v204-sec: Obergrenze fuer EINEN Upload-Abschnitt (der Body landet vor
# jeder Pruefung im RAM). Das Frontend schickt wenige MB je Abschnitt.
CHUNK_MAX_BYTES = int(os.environ.get('DVE_CHUNK_MB', '32')) * 1024 * 1024
# v204-sec: Rechenlast-Grenzen. 4K (3840) mit Reserve fuer krumme
# Formate; 60 fps ist die hoechste Bildrate, die im Feed etwas bringt.
MAX_PIXEL_LANG = int(os.environ.get('DVE_MAX_PIXEL', '4096'))
MAX_FPS = float(os.environ.get('DVE_MAX_FPS', '60'))
MAX_SECONDS = int(os.environ.get('DVE_MAX_SECONDS', '180'))
# v230c-sec: Seitenverhaeltnis. 16:9 ist 1.78, ein Kinoformat 2.4 - 6:1 laesst
# jedem echten Video Luft und stoppt die Streifen, die den Speicher sprengen.
MAX_ASPECT = float(os.environ.get('DVE_MAX_ASPECT', '6'))
# Wie viele fertig vorbereitete, aber nie gerenderte Uploads ein Konto
# gleichzeitig liegen haben darf. Der bisherige Deckel zaehlte nur, was
# GERADE laeuft - ein 'pre'-Upload faellt danach heraus und der naechste war
# sofort erlaubt: unbegrenzt Plattenplatz und Whisper-Aufrufe je Konto.
MAX_VORBEREITET = int(os.environ.get('DVE_MAX_PRE', '8'))
SESSION_DAYS = 30
TRIAL_SECONDS = int(os.environ.get('DVE_TRIAL_SECONDS', '120'))  # 2 Min gratis
RETENTION_DAYS = float(os.environ.get('DVE_RETENTION_DAYS', '7'))
# v132: "Mit Google anmelden" (OAuth). KOMPLETT inert, solange die beiden Keys
# fehlen - kein Button, kein Endpoint-Effekt. Erst wenn du in der Google Cloud
# eine OAuth-Client-ID anlegst und beide Werte in die .env setzt, erscheint der
# Button. Aendert am Passwort-Login NICHTS.
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
GOOGLE_OK = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
# v133c: Support-Postfach. HIERHIN gehen die Support-Ticket-Meldungen (mit
# Reply-To = Kundenadresse). noreply@douchko.eu verschickt nur, nimmt aber
# KEINE Antworten mehr an (kein globales Reply-To). Steht als Kontakt in Mails.
# 'or'-Fallback: docker-compose reicht bei fehlender .env-Zeile einen LEEREN
# String durch, der einen get-Default schlagen wuerde (gleiche Falle wie
# DVE_TAX_ID in v135a - live stand 'email .' in der Kauf-Mail).
SUPPORT_EMAIL = (os.environ.get('DVE_SUPPORT_MAIL') or 'Ismet@douchkove.com').strip()

# ================= v197: Logs, die einen Neustart ueberleben =================
# Bis v196 lag der gesamte Betriebs-Log NUR in `docker logs`. `update.sh` baut
# das Image neu und startet den Container neu - damit war der Log weg, und
# genau dann will man nachsehen, warum etwas kaputtgegangen ist. Alles, was
# auf stdout/stderr geht (die 43 print-Stellen, Tracebacks, uvicorn), wird
# zusaetzlich in eine rotierende Datei geschrieben. Der Konsolen-Strom bleibt
# unveraendert, `docker logs` funktioniert weiter.
LOG_DIR = os.path.join(DATA, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'server.log')
LOG_MAX = int(os.environ.get('DVE_LOG_MB', '5')) * 1024 * 1024
LOG_KEEP = 5


def _log_rotate():
    """Rotiert bei Ueberschreiten von LOG_MAX. os.replace, damit ein
    gleichzeitig lesender Admin-Aufruf nie eine halbe Datei sieht."""
    try:
        if os.path.getsize(LOG_FILE) < LOG_MAX:
            return
    except OSError:
        return
    for i in range(LOG_KEEP - 1, 0, -1):
        alt = f'{LOG_FILE}.{i}'
        if os.path.exists(alt):
            os.replace(alt, f'{LOG_FILE}.{i + 1}')
    os.replace(LOG_FILE, LOG_FILE + '.1')


class _LogTee:
    """Schreibt jede Zeile mit Zeitstempel zusaetzlich in LOG_FILE.
    Scheitert IMMER leise - ein kaputter Log darf nie den Server reissen."""
    def __init__(self, strom, tag):
        self._s, self._tag = strom, tag
        self._lock = threading.Lock()
        self._buf = ''

    def write(self, text):
        # print() ruft write() je Argument EINZELN auf ("a", " ", "b", "\n").
        # Ohne Zeilenpuffer stuende jedes Argument in einer eigenen
        # Log-Zeile - unlesbar. Erst am Zeilenende wird geschrieben.
        n = self._s.write(text)
        try:
            with self._lock:
                self._buf += text
                if '\n' not in self._buf:
                    if len(self._buf) > 65536:       # Notbremse ohne Umbruch
                        self._buf, rest = '', self._buf
                        self._schreib([rest])
                    return n
                teile = self._buf.split('\n')
                self._buf = teile.pop()
                self._schreib(teile)
        except Exception:
            pass
        return n

    def _schreib(self, zeilen):
        zeilen = [z for z in zeilen if z.strip()]
        if not zeilen:
            return
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        _log_rotate()
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            for z in zeilen:
                f.write(f'{stamp} [{self._tag}] {z}\n')

    def flush(self):
        self._s.flush()

    def isatty(self):
        return getattr(self._s, 'isatty', lambda: False)()

    def fileno(self):
        return self._s.fileno()

    @property
    def encoding(self):
        return getattr(self._s, 'encoding', 'utf-8')


def _log_start():
    """Einmalig beim Import. DVE_LOGFILE=0 schaltet die Datei ab (Tests)."""
    if os.environ.get('DVE_LOGFILE', '1') == '0':
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        return
    if not isinstance(sys.stdout, _LogTee):
        sys.stdout = _LogTee(sys.stdout, 'out')
        sys.stderr = _LogTee(sys.stderr, 'err')


_log_start()


# v84: Credits statt roher Minuten. Intern bleibt alles Sekunden (bewaehrt),
# 1 Credit = 1 Minute Video. Abgerechnet wird pro ANGEFANGENER Minute -
# so ist die Balance immer ein glattes Vielfaches von 60 und die Credit-
# Anzeige nie krumm (Guthaben-Gutschriften sind ebenfalls ganze Minuten).
import math as _math


def credits_of(sec):
    """Sekunden -> ganze Credits (fuer die Anzeige)."""
    return int(sec) // 60


# v149: 4K kostet das Doppelte. Matting, Tiefenkarte, Gesichts-Tracking und
# Encode laufen alle auf voller Aufloesung - die vierfache Pixelmenge ist echte
# Rechenzeit, kein Schalter. Ein Faktor 2 deckt sie, ohne den Preis zu
# verdoppeln, wo er nichts kostet.
UHD_FAKTOR = 2
# Darunter lohnt 4K nicht: aus einer 1080p-Quelle wird kein 4K, nur ein grosses
# weiches 1080p. Die Engine skaliert deshalb nie hoch - und wir berechnen es
# auch nicht.
UHD_MIN_KURZE_KANTE = 1440


def cost_seconds(dur_sec, uhd=False):
    """Was ein Video kostet: pro angefangener Minute, mindestens 1 Credit.
    v149: bei 4K das Doppelte."""
    return (max(1, _math.ceil(float(dur_sec) / 60.0)) * 60
            * (UHD_FAKTOR if uhd else 1))


def _job_cost(j):
    """v149: was DIESER Job kostet. Bevorzugt den beim Anlegen festgehaltenen
    Betrag - sonst wuerde eine Erstattung nach einem 4K-Render nur die Haelfte
    zurueckgeben, weil die reine Dauer den Faktor nicht kennt."""
    j = j or {}
    c = j.get('cost_sec')
    if c:
        return int(c)
    return cost_seconds(j.get('dauer', 0), uhd=bool(j.get('uhd')))


def _quelle_kurze_kante(pfad):
    """Kurze Kante der Quelldatei in Pixeln, 0 wenn nicht lesbar."""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', pfad],
            capture_output=True, text=True, timeout=30)
        w, h = (int(x) for x in r.stdout.strip().split('x')[:2])
        return min(w, h)
    except Exception:
        return 0


# v230al 4K IST AUS DER OBERFLAECHE RAUS (Ismets Entscheidung). Begruendung
# geschaeftlich, nicht technisch: TikTok, Reels und Shorts rechnen jedes Video
# auf 1080p herunter - der Kunde zahlt also den doppelten Satz und die doppelte
# Renderzeit fuer ein Ergebnis, das bei seinem Zuschauer identisch ankommt. Und
# ausgerechnet diese teuerste Stufe war die fragilste (Speicher-Tod, v230ak).
# Der CODE bleibt vollstaendig: ein `DVE_4K=1` in der .env schaltet die Stufe
# wieder frei - Ausbauen und spaeter neu bauen waere Verschwendung.
def _4k_erlaubt():
    return str(os.environ.get('DVE_4K', '')).strip().lower() in ('1', 'true', 'ja', 'yes')


def _will_uhd(overrides, pfad):
    """Wird dieser Job wirklich in 4K gerendert? Nur dann darf er auch das
    Doppelte kosten. Der Wunsch allein reicht nicht - eine 1080p-Quelle
    bleibt 1080p, egal was angehakt ist."""
    try:
        o = ((overrides or {}).get('output') or {})
        q = str(o.get('quality', '')).lower()
        h = int(o.get('height') or 0)
    except Exception:
        return False
    # v157: die UI schickt 4K jetzt als HOEHE (eine Stufe neben 720p/1080p),
    # nicht mehr als eigenes Quality-Feld. Beide Wege muessen zaehlen - sonst
    # wuerde 4K gerendert, aber nur der einfache Satz berechnet.
    if q not in ('4k', 'uhd') and h < 2160:
        return False
    if not _4k_erlaubt():
        return False                   # v230al: Stufe abgeschaltet
    return _quelle_kurze_kante(pfad) >= UHD_MIN_KURZE_KANTE


def _hook_score(moms, dauer=0.0):
    """v124: Server-Port der Client-Heuristik computeHookScore (index.html).
    Inhaltlich synchron halten, damit Ergebnis-Kachel und Library-Verlauf
    dieselbe Zahl zeigen. Bewertet: Hook-Abdeckung (erste 8s), klarer
    Hoehepunkt, Dichte-Balance, Animations-Anteil, Effekt-Vielfalt."""
    act = [m for m in (moms or [])
           if isinstance(m, dict) and m.get('aktiv') is not False]
    if not act:
        return 0
    try:
        dur = float(dauer) if dauer else 0.0
    except (TypeError, ValueError):
        dur = 0.0
    if dur <= 0:
        dur = max(float(m.get('zeit') or 0) for m in act) + 5
    score = 0.0
    early = [m for m in act if float(m.get('zeit') or 0) <= 8]
    if len(early) >= 1:
        score += 20
    if len(early) >= 2:
        score += 10
    if early and min(float(m.get('zeit') or 0) for m in early) <= 1.2:
        score += 10
    if any(int(m.get('power') or 2) >= 3 for m in act):
        score += 15
    per_min = len(act) / max(dur / 60.0, 0.2)
    score += 25 if 3 <= per_min <= 9 else (
        max(0.0, 25 - abs(per_min - 6) * 4) if per_min > 0 else 0)
    score += round(sum(1 for m in act if m.get('anim')) / len(act) * 10)
    score += min(len({m.get('fx') for m in act}), 5) * 2
    return max(1, min(100, round(score)))

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

# v88b: Transkript-Cache pro Nutzer + Videoinhalt. Dasselbe Video soll nie
# zweimal transkribiert werden - auch nicht, wenn es (nach Einstellungs-
# aenderungen) neu hochgeladen wird. Schluessel = (User, Inhalts-Hash, Sprache).
_TCACHE = os.path.join(DATA, 'tcache')
os.makedirs(_TCACHE, exist_ok=True)


def _video_hash(path):
    """Schneller, stabiler Inhalts-Hash. v94: NICHT mehr nur Anfang+Ende.
    Clips aus derselben App/Vorlage teilen oft identischen Header und Footer
    (gleiche Groesse, gleiche erste/letzte 256 KB) -> zwei VERSCHIEDENE Videos
    bekamen denselben Hash -> falscher Transkript-Cache wurde serviert (ein
    deutscher Clip vergiftete einen englischen). Jetzt 8 Stellen QUER durch die
    Datei lesen; die Mitte, wo sich der Inhalt garantiert unterscheidet, zaehlt
    mit. Bleibt schnell (2 MB gelesen statt GB)."""
    import hashlib
    try:
        sz = os.path.getsize(path)
        h = hashlib.sha1(str(sz).encode())
        chunk, points = 262144, 8
        with open(path, 'rb') as f:
            if sz <= chunk:
                return hashlib.sha1(str(sz).encode() + f.read()).hexdigest()
            for k in range(points):
                off = int((sz - chunk) * k / (points - 1))
                f.seek(off)
                h.update(f.read(chunk))
        return h.hexdigest()
    except Exception:
        return None


def _tcache_path(uid, vhash, lang):
    if not uid or not vhash:
        return None
    # v92-sec: lang landet im Dateinamen. Ein Angreifer koennte ueber
    # cfg_overrides["language"] = "../../.." Pfad-Traversal ausloesen (der
    # Cache wird per shutil.copyfile gelesen/geschrieben). Hart auf reine
    # Kleinbuchstaben eindampfen - kein Slash, kein Punkt, kein '..'.
    lang = re.sub(r'[^a-z]', '', (lang or 'auto').strip().lower())[:8] or 'auto'
    uid = int(uid)                                  # int-Cast entfernt jeden Trick
    return os.path.join(_TCACHE, f'{uid}_{vhash}_{lang}.json')


def _job_transcript_path(src):
    return os.path.splitext(src)[0] + '_transcript2.json'


def _safe_name(name):
    """v92-sec: Angezeigter Upload-Dateiname. Nur Basename, Steuerzeichen und
    Winkelklammern raus, Laenge gekappt. Verhindert, dass ein praeparierter
    Dateiname (z.B. '<img onerror=...>.mp4') irgendwo als HTML wirkt."""
    base = os.path.basename(name or '').strip()
    base = re.sub(r'[\x00-\x1f<>]', '', base)
    return base[:80] or 'video.mp4'


# ================================================================
# v80h: User-Accounts (Email + Passwort, bcrypt-Hashing, SQLite)
# ================================================================
def _db():
    # WAL + busy_timeout: Leser blockieren Schreiber nicht mehr und ein kurz
    # gesperrter Write wartet statt sofort mit 'database is locked' auf einem
    # Geld-Endpoint zu scheitern. synchronous=NORMAL ist das Standard-Pairing
    # zu WAL (taegliche Backups existieren).
    con = sqlite3.connect(USERS_DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('PRAGMA synchronous=NORMAL')
    # v142: Lese-Cache pro Verbindung (8 MB) und Sortier-/Join-Temporaries im
    # RAM statt auf Platte. Reines Tuning ohne Verhaltens-Aenderung, wirkt dort,
    # wo die Aggregat-Abfragen des Admin-Panels teuer sind. Bewusst KEIN
    # foreign_keys=ON: die Loeschpfade sind auf die bisherige Reihenfolge
    # gebaut, das waere eine Verhaltens-Aenderung.
    con.execute('PRAGMA cache_size=-8000')
    con.execute('PRAGMA temp_store=MEMORY')
    return con


def _init_users_db():
    con = _db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      email         TEXT UNIQUE NOT NULL,
      pw_hash       TEXT NOT NULL,
      name          TEXT DEFAULT '',
      balance_sec   INTEGER NOT NULL DEFAULT 0,
      created_at    INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token         TEXT PRIMARY KEY,
      user_id       INTEGER NOT NULL REFERENCES users(id),
      created_at    INTEGER NOT NULL,
      expires_at    INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_sess_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS resets (
      token         TEXT PRIMARY KEY,
      user_id       INTEGER NOT NULL REFERENCES users(id),
      created_at    INTEGER NOT NULL,
      expires_at    INTEGER NOT NULL,
      used          INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS verify_tokens (
      token         TEXT PRIMARY KEY,
      user_id       INTEGER NOT NULL REFERENCES users(id),
      created_at    INTEGER NOT NULL,
      expires_at    INTEGER NOT NULL,
      used          INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS ledger (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id       INTEGER NOT NULL REFERENCES users(id),
      delta_sec     INTEGER NOT NULL,
      grund         TEXT NOT NULL,
      created_at    INTEGER NOT NULL
    );
    -- v98: GoBD/§147 AO - Kaufbuchungen muessen 10 Jahre aufbewahrt werden,
    -- auch nach Konto-Loeschung (DSGVO Art. 17(3)(b) erlaubt das explizit).
    -- Beim Loeschen wandern nur die 'Kauf %'-Zeilen hierher, alles andere
    -- (Renders, Refunds, Gratis-Gutschriften) wird wirklich geloescht.
    CREATE TABLE IF NOT EXISTS ledger_archive (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      user_email    TEXT NOT NULL,
      delta_sec     INTEGER NOT NULL,
      grund         TEXT NOT NULL,
      created_at    INTEGER NOT NULL,
      archived_at   INTEGER NOT NULL
    );
    """)
    con.commit()
    # v80x: verified-Spalte nachziehen. Bestands-Accounts werden als
    # verifiziert uebernommen (Grandfathering), Neue starten bei 0.
    cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
    if 'verified' not in cols:
        con.execute("ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        con.execute("UPDATE users SET verified = 1")
        con.commit()
    # v124: Referral. ref_code = eigener Einladungscode (lazy erzeugt),
    # referred_by = users.id des Werbers (gesetzt bei der Registrierung).
    if 'ref_code' not in cols:
        con.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
        con.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
        con.commit()
    # v130 Admin: reversible Konto-Sperre (Suspend). Gesperrte Konten koennen
    # sich nicht mehr einloggen und bestehende Sessions gelten als tot.
    if 'disabled' not in cols:
        con.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
        con.commit()
    # v132: Google-OAuth. google_sub = stabile Google-Nutzer-ID (kommt aus dem
    # id_token, aendert sich nie, auch wenn der Nutzer die E-Mail umbenennt).
    # Ein Konto kann Passwort UND Google haben (per E-Mail verknuepft).
    if 'google_sub' not in cols:
        con.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_gsub "
                    "ON users(google_sub) WHERE google_sub IS NOT NULL")
        con.commit()
    # v125: einmalige System-Mails (z.B. Verfall-Warnung) gegen Doppelversand.
    con.execute("CREATE TABLE IF NOT EXISTS mail_log ("
                "user_id INTEGER NOT NULL, key TEXT NOT NULL, sent_at INTEGER NOT NULL, "
                "UNIQUE(user_id, key))")
    # v133c: Support-Ticketsystem. Kunde schickt ueber das Formular ein Ticket;
    # es landet hier UND als Mail beim Betreiber (Reply-To = Kunde). Status
    # open/closed, im Admin-Panel sichtbar.
    con.execute("CREATE TABLE IF NOT EXISTS tickets ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
                "email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'open', "
                "created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status, created_at)")
    # v198 SUPPORT-VERLAUF. Ein Ticket war bis v197 eine Einbahnstrasse: der
    # Kunde schrieb, die Antwort lief per Mail aus Ismets Postfach. Damit stand
    # die halbe Unterhaltung nirgends, eine Rueckfrage des Kunden erzeugte ein
    # NEUES Ticket, und wer geantwortet hat, wusste nur das Postfach.
    # Jede Nachricht ist jetzt eine Zeile; `tickets.body` bleibt als erste.
    con.execute("CREATE TABLE IF NOT EXISTS ticket_messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ticket_id INTEGER NOT NULL, "
                "von TEXT NOT NULL, "                 # 'kunde' | 'admin'
                "text TEXT NOT NULL, "
                "gelesen INTEGER NOT NULL DEFAULT 0, "  # vom Kunden gesehen
                "created_at INTEGER NOT NULL)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tmsg ON ticket_messages"
                "(ticket_id, created_at)")
    # Nachtrag fuer Alt-Tickets: die erste Nachricht steckt in tickets.body.
    # Ohne das faengt jeder alte Verlauf mit der Antwort an.
    try:
        offen = con.execute(
            "SELECT t.id, t.body, t.created_at FROM tickets t "
            "WHERE NOT EXISTS (SELECT 1 FROM ticket_messages m "
            "WHERE m.ticket_id = t.id)").fetchall()
        for r in offen:
            con.execute("INSERT INTO ticket_messages (ticket_id, von, text, "
                        "gelesen, created_at) VALUES (?, 'kunde', ?, 1, ?)",
                        (r[0], r[1], r[2]))
    except Exception as e:
        print(f'Ticket-Nachtrag uebersprungen: {type(e).__name__}: {e}')
    # v196 ANKUENDIGUNGEN. Bis v195 gab es keinen Weg, Kunden etwas zu sagen,
    # ausser einer Mail an alle - und die ist fuer "Wartung heute 20 Uhr" oder
    # "neuer Look da" das falsche Mittel (zu laut, nicht abbestellbar ohne
    # Kollateralschaden). Eine Ankuendigung steht IN der App, ist stufig
    # (info/warn/wartung) und laeuft optional von selbst ab.
    con.execute("CREATE TABLE IF NOT EXISTS announcements ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, titel TEXT NOT NULL, "
                "text TEXT NOT NULL, stufe TEXT NOT NULL DEFAULT 'info', "
                "aktiv INTEGER NOT NULL DEFAULT 1, "
                "created_at INTEGER NOT NULL, bis INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ann_aktiv "
                "ON announcements(aktiv, created_at)")
    # v196 FEEDBACK. Bewusst NICHT dasselbe wie ein Support-Ticket: das Ticket
    # ist eine Frage mit Antworterwartung, Feedback ist eine Bewertung ohne.
    # Es haengt am fertigen Render (jid + look) - nur dort ist die Meinung
    # konkret und damit auswertbar ("welcher Look enttaeuscht?").
    con.execute("CREATE TABLE IF NOT EXISTS feedback ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
                "jid TEXT DEFAULT '', look TEXT DEFAULT '', "
                "note INTEGER NOT NULL, text TEXT DEFAULT '', "
                "created_at INTEGER NOT NULL, gelesen INTEGER NOT NULL DEFAULT 0)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_fb_neu "
                "ON feedback(gelesen, created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_fb_user ON feedback(user_id)")
    # v126-sec: Referral-Anspruch pro E-Mail, PSEUDONYM (gesalzener Hash, KEINE
    # Klartext-Mail). UEBERLEBT die Kontoloeschung bewusst - sonst liesse sich der
    # Bonus per Loeschen+Neuregistrieren beliebig oft farmen. DSGVO: berechtigtes
    # Interesse Betrugsabwehr (Art. 6(1)(f)), gehoert in die Datenschutzerklaerung.
    con.execute("CREATE TABLE IF NOT EXISTS referral_claims ("
                "email_hash TEXT PRIMARY KEY, claimed_at INTEGER NOT NULL)")
    # v127-sec: Gratis-Kredit-Anspruch pro E-Mail (Welcome einmalig, Monats-
    # Freikredit 1x/Monat), PSEUDONYM (gesalzener Hash). UEBERLEBT die
    # Kontoloeschung bewusst - sonst laesst sich der Free-Tier per Loeschen+
    # Neuregistrieren mit derselben Mail beliebig oft farmen. kind = 'welcome'
    # oder 'monthly-YYYY-MM'. DSGVO: berechtigtes Interesse Betrugsabwehr
    # (Art. 6(1)(f)), in der Datenschutzerklaerung genannt.
    con.execute("CREATE TABLE IF NOT EXISTS credit_claims ("
                "email_hash TEXT NOT NULL, kind TEXT NOT NULL, "
                "claimed_at INTEGER NOT NULL, PRIMARY KEY (email_hash, kind))")
    # v127-recht: Nachweis der Widerrufs-Einwilligung (§ 356 (4) BGB). Der
    # Kunde bestaetigt beim Kauf ausdruecklich die sofortige Ausfuehrung UND die
    # Kenntnis vom Erloeschen des Widerrufsrechts fuer verbrauchte Credits; hier
    # mit Zeitstempel protokolliert (Beweislast).
    con.execute("CREATE TABLE IF NOT EXISTS consents ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "kind TEXT NOT NULL, created_at INTEGER NOT NULL)")
    # v147: STOERUNGEN persistent statt per Mail. Ismet will Job-Fehler nicht
    # mehr im Postfach, sondern im Admin-Panel - und die JOBS-Liste haelt nur
    # den Arbeitsspeicher, ein Neustart loescht sie. Deshalb eine eigene
    # Tabelle: jede Stoerung landet hier IMMER, unabhaengig von DVE_ALERTS.
    # v230j DEPLOY-ZUSTAND. Eine einzige Zeile, geschrieben vom Deploy-Skript
    # auf dem Host (per `docker compose exec`, derselbe Weg wie die
    # Alarm-Meldungen). Damit sieht das Panel, ob gerade etwas gebaut wird,
    # wie lange schon - und wie lange der letzte Deploy WIRKLICH gedauert hat.
    con.execute("CREATE TABLE IF NOT EXISTS deploy_state ("
                "id INTEGER PRIMARY KEY CHECK (id = 1), "
                "phase TEXT NOT NULL DEFAULT '', commit_kurz TEXT NOT NULL DEFAULT '', "
                "started_at INTEGER NOT NULL DEFAULT 0, "
                "finished_at INTEGER NOT NULL DEFAULT 0, "
                "dauer_s INTEGER NOT NULL DEFAULT 0, "
                "grund TEXT NOT NULL DEFAULT '')")
    con.execute("CREATE TABLE IF NOT EXISTS alerts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, schluessel TEXT NOT NULL, "
                "betreff TEXT NOT NULL, text TEXT NOT NULL, "
                "gemailt INTEGER NOT NULL DEFAULT 0, "
                "gelesen INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)")
    # v204-sec SICHERHEITS-PROTOKOLL. Bis v203 hielt NICHTS fest, wer wann was
    # getan hat: kein Admin-Zugriff, kein Login, kein Passwortwechsel, keine
    # Erstattung. Nach einem Vorfall waere gar nicht rekonstruierbar gewesen,
    # was passiert ist - und die DSGVO verlangt in Art. 33 eine Meldung binnen
    # 72 Stunden, die man ohne Spuren nicht schreiben kann.
    # Bewusst eine EIGENE Tabelle, nicht die alerts: alerts sind Stoerungen,
    # die jemand abhakt; das hier ist eine Chronik, die niemand abhakt.
    con.execute("CREATE TABLE IF NOT EXISTS security_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts INTEGER NOT NULL, "
                "aktion TEXT NOT NULL, "          # login_ok, admin, pw_change ...
                "wer TEXT NOT NULL DEFAULT '', "  # 'user:12' | 'admin' | 'anon'
                "ip TEXT NOT NULL DEFAULT '', "
                "ziel TEXT NOT NULL DEFAULT '', " # Pfad / betroffenes Konto
                "detail TEXT NOT NULL DEFAULT '')")
    con.execute("CREATE INDEX IF NOT EXISTS ix_secev_ts ON security_events(ts)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_secev_akt "
                "ON security_events(aktion, ts)")
    # v208 TRICHTER. Bis v207 wusste das Panel nur, wie viele Konten es gibt -
    # nicht, wie viele Leute die Seite gesehen und NICHT gekauft haben. Genau
    # das ist die interessante Zahl: sie sagt, WO man Leute verliert.
    # Bewusst selbst gebaut statt Google Analytics: das braeuchte in
    # Deutschland einen Einwilligungs-Banner (Cookies, Schrems II), und ein
    # Banner kostet sofort Anmeldungen. Hier verlaesst kein Datum das Haus.
    # KEINE IP, KEIN Cookie: 'besucher' ist ein Fingerabdruck aus einem
    # taeglich wechselnden Zufallswert + IP + Browserkennung. Er laesst sich
    # nicht ueber Tage hinweg verketten und nicht zurueckrechnen - deshalb
    # ist er keine personenbezogene Kennung und braucht keine Einwilligung.
    con.execute("CREATE TABLE IF NOT EXISTS trichter ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts INTEGER NOT NULL, "
                "stufe TEXT NOT NULL, "        # besuch|app|konto|upload|fertig|kauf
                "besucher TEXT NOT NULL DEFAULT '', "
                "quelle TEXT NOT NULL DEFAULT '', "   # tiktok, instagram, direkt ...
                "user_id INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tri_ts ON trichter(ts, stufe)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tri_bes ON trichter(besucher, ts)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tri_uid ON trichter(user_id)")
    # v206 ERSTATTUNGEN. Bis v205 wurde eine Erstattung NIRGENDS vom Umsatz
    # abgezogen: purchases blieb unveraendert, der Stripe-Hinweis schrieb nur
    # eine Meldung, und die Steuer-Ampel (§19-Grenzen) rechnete aus derselben
    # Brutto-Zahl. Im Panel stand also, was Kunden gezahlt haben - nicht, was
    # geblieben ist. Genau deshalb war die Zahl nicht vertrauenswuerdig.
    # Eigene Tabelle statt purchases zu aendern: der Kauf-Beleg ist ein
    # Buchungsbeleg (GoBD, 10 Jahre) und wird nicht nachtraeglich verbogen -
    # eine Erstattung ist ein EIGENER Vorgang.
    con.execute("CREATE TABLE IF NOT EXISTS refunds ("
                "session_id TEXT PRIMARY KEY, "
                "user_id INTEGER, "
                "cents INTEGER NOT NULL DEFAULT 0, "
                "quelle TEXT NOT NULL DEFAULT 'panel', "   # panel | stripe
                "created_at INTEGER NOT NULL)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_refunds_ts ON refunds(created_at)")
    # v128 Admin: Kauf-Beleg mit ECHTEM Betrag (cents) fuer die Umsatz-Ansicht.
    # Das Ledger kennt nur Sekunden, nicht das bezahlte Geld - hier steht der
    # tatsaechlich gezahlte Betrag (amount_total, also inkl. evtl. Rabatt).
    # Idempotent ueber die Stripe-Session-ID (PRIMARY KEY).
    con.execute("CREATE TABLE IF NOT EXISTS purchases ("
                "session_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, pack TEXT, "
                "cents INTEGER NOT NULL, sekunden INTEGER NOT NULL, created_at INTEGER NOT NULL)")
    # v230v Betriebs-Einstellungen, die NICHT ins Repo gehoeren: die Zugaenge
    # zur Sicherung ausser Haus. Sie kommen ueber das Panel herein, nicht ueber
    # eine Datei auf dem Server - Ismet arbeitet nicht im Terminal (v197).
    # Geheimnisse werden NIE wieder ausgeliefert, nur "gesetzt: ja/nein".
    con.execute("CREATE TABLE IF NOT EXISTS app_settings ("
                "k TEXT PRIMARY KEY, v TEXT NOT NULL, ts INTEGER NOT NULL)")
    con.commit()
    # v92-sec: Kauf-Gutschriften gegen Doppelbuchung absichern. Stripe kann
    # denselben Webhook mehrfach senden; ohne DB-Constraint konnten zwei
    # gleichzeitige Deliveries beide am Idempotenz-SELECT vorbei und doppelt
    # gutschreiben. Partieller UNIQUE-Index nur auf 'Kauf %' - Renders/Refunds/
    # Monthly bleiben unberuehrt. Falls Altdaten Duplikate haben, nicht crashen.
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_kauf "
                    "ON ledger(user_id, grund) WHERE grund LIKE 'Kauf %'")
        con.commit()
    except sqlite3.IntegrityError as e:
        print(f'WARN: ux_ledger_kauf nicht angelegt (Altdaten-Duplikate?): {e}')
    # v126-sec: dieselbe Doppelbuchungs-Sperre fuer Referral-Gutschriften. Die
    # Gruende 'Referral welcome' (1x pro Geworbenem) und 'Referral for {uid}'
    # (1x pro Werber+Geworbenem) sind je Paar eindeutig - der Index macht den
    # SELECT-dann-INSERT-Pfad idempotent (Race beim doppelten Verify tot).
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_ref "
                    "ON ledger(user_id, grund) WHERE grund LIKE 'Referral %'")
        con.commit()
    except sqlite3.IntegrityError as e:
        print(f'WARN: ux_ledger_ref nicht angelegt (Altdaten-Duplikate?): {e}')
    # v126-sec: Einladungscodes eindeutig - schuetzt _ensure_ref_code beim
    # gleichzeitigen ersten /api/me-Aufruf gegen Kollision.
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_refcode "
                    "ON users(ref_code) WHERE ref_code IS NOT NULL")
        con.commit()
    except sqlite3.IntegrityError as e:
        print(f'WARN: ux_users_refcode nicht angelegt: {e}')
    # v127-sec: Welcome- und Monats-Freikredit gegen Doppel-Gutschrift bei
    # gleichzeitigen Requests (Doppel-Verify / zwei /api/me am Monatswechsel).
    # Bisher hatten nur Kauf/Referral einen solchen Index - genau der Pfad,
    # der hier fehlte. Partiell, damit Renders/Refunds unberuehrt bleiben.
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_welcome "
                    "ON ledger(user_id, grund) WHERE grund = 'Welcome credit'")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_monthly "
                    "ON ledger(user_id, grund) WHERE grund LIKE 'Monthly free credit %'")
        con.commit()
    except sqlite3.IntegrityError as e:
        print(f'WARN: ux_ledger_welcome/monthly nicht angelegt (Altdaten-Duplikate?): {e}')
    # v142 PERFORMANCE (gemessen, nicht vermutet): mit EXPLAIN QUERY PLAN gegen
    # das frische Schema liefen 13 von 15 Kern-Abfragen als FULL TABLE SCAN -
    # Ledger je Nutzer, Verfall-FIFO, Kauf-Belege, Consents, Token-Aufraeumen,
    # Archiv, aktive Sessions. Die partiellen UNIQUE-Indexe oben decken NUR
    # ihre jeweiligen Buchungsgruende ab, nicht die normalen Lesepfade. Bei
    # heute wenigen Zeilen faellt das nicht auf; jede Ledger-Zeile mehr macht
    # /api/me linear langsamer, und genau das waechst mit jedem Kunden.
    # IF NOT EXISTS -> idempotent, laeuft bei jedem Start ueber Bestandsdaten.
    for _ddl in (
        "CREATE INDEX IF NOT EXISTS ix_ledger_user_time ON ledger(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_ledger_user_grund ON ledger(user_id, grund)",
        "CREATE INDEX IF NOT EXISTS ix_ledger_time ON ledger(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_purch_user ON purchases(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_purch_time ON purchases(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_users_created ON users(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_consents_user ON consents(user_id, kind)",
        "CREATE INDEX IF NOT EXISTS ix_verify_user ON verify_tokens(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_resets_user ON resets(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_arch_mail ON ledger_archive(user_email)",
        "CREATE INDEX IF NOT EXISTS ix_arch_time ON ledger_archive(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_sess_exp ON sessions(expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_mail_log_user ON mail_log(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_alerts_time ON alerts(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_alerts_offen ON alerts(gelesen, created_at DESC)",
    ):
        try:
            con.execute(_ddl)
        except sqlite3.OperationalError as e:
            print(f'WARN: Index nicht angelegt: {e}')
    con.commit()
    try:
        con.execute('PRAGMA optimize')      # Statistiken fuer den Planer
    except Exception:
        pass
    con.close()


_init_users_db()


def _hash_pw(pw):
    """bcrypt-Hash. Wenn bcrypt fehlt, faellt auf pbkdf2_sha256 zurueck."""
    try:
        import bcrypt
        return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('ascii')
    except ImportError:
        import hashlib
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt.encode(), 260000)
        return f'pbkdf2$260000${salt}${h.hex()}'


def _verify_pw(pw, stored):
    """Vergleicht Passwort mit gespeichertem Hash - bcrypt oder pbkdf2."""
    if not stored:
        return False
    try:
        if stored.startswith('$2'):     # bcrypt
            import bcrypt
            return bcrypt.checkpw(pw.encode('utf-8'), stored.encode('ascii'))
    except Exception:
        return False
    if stored.startswith('pbkdf2$'):
        import hashlib
        try:
            _, it, salt, hexh = stored.split('$')
            h = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'),
                                    salt.encode(), int(it))
            return secrets.compare_digest(h.hex(), hexh)
        except Exception:
            return False
    return False


# v92-sec: Fester Dummy-Hash. Bei Login mit unbekannter E-Mail wird trotzdem
# eine bcrypt-Pruefung gefahren, damit die Antwortzeit gleich bleibt und man
# nicht per Timing erraten kann, welche E-Mails existieren.
_DUMMY_HASH = _hash_pw(secrets.token_hex(16))


EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def _valid_email(s):
    return bool(s) and len(s) <= 254 and EMAIL_RE.match(s)


def _valid_pw(s):
    return bool(s) and 8 <= len(s) <= 200


_USERNAME_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9 _.-]{1,22})[A-Za-z0-9]$')


def _valid_username(s):
    """v84: Anzeigename (Username) statt Vorname. 3-24 Zeichen, Buchstaben/
    Zahlen/Leerzeichen/._-, muss mit Buchstabe/Zahl anfangen und enden.
    Keine globale Eindeutigkeit erzwungen - reiner Anzeigename, das haelt
    die Registrierung reibungslos (kein 'Name vergeben')."""
    return bool(s) and bool(_USERNAME_RE.match(s.strip()))


def _create_user(email, pw, name=''):
    # v98: Startguthaben erst NACH E-Mail-Bestaetigung (_grant_welcome) -
    # vorher liess sich Ismets OpenAI-Key per Massen-Registrierung farmen
    # (Wegwerf-Adressen, nie bestaetigt, sofort 120s Renderzeit).
    # v127-sec: die Besitzer-Identitaet ist NICHT registrierbar. Sonst koennte
    # jemand, solange OWNER_EMAIL noch kein Konto hat, sie einfach anlegen und
    # bekaeme (via _owner_ok) die globale Stil-Referenz-Regie + Gratis-Whisper.
    if email.strip().lower() == OWNER_EMAIL:
        return None, 'This email is already registered.'
    con = _db()
    try:
        cur = con.execute(
            "INSERT INTO users (email, pw_hash, name, balance_sec, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (email.strip().lower(), _hash_pw(pw), name.strip()[:60],
             0, int(time.time())))
        uid = cur.lastrowid
        con.commit()
        return uid, None
    except sqlite3.IntegrityError:
        return None, 'This email is already registered.'
    finally:
        con.close()


def _grant_welcome(uid):
    """Willkommens-Guthaben bei der E-Mail-Bestaetigung. v127-sec: ATOMAR und
    doppelt abgesichert:
      1) credit_claims (E-Mail-Hash, ueberlebt Loeschung) -> pro Person nur
         EINMAL, blockt Loeschen+Neuregistrieren-Farming.
      2) partieller Unique-Index ux_ledger_welcome -> blockt den Doppel-Verify-
         Race (zwei gueltige Token gleichzeitig eingeloest).
    Beide Inserts + der Balance-Update haengen an EINER Transaktion; scheitert
    einer, wird alles zurueckgerollt (kein halber Zustand)."""
    if TRIAL_SECONDS <= 0:
        return False
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')                # Schreibsperre gegen TOCTOU
        urow = con.execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()
        if not urow:
            con.execute('ROLLBACK')
            return False
        claim = con.execute(
            "INSERT OR IGNORE INTO credit_claims (email_hash, kind, claimed_at) "
            "VALUES (?, 'welcome', ?)", (_email_hash(urow['email']), int(time.time())))
        if claim.rowcount != 1:
            con.execute('ROLLBACK')
            return False                              # diese E-Mail hat's schon gehabt
        led = con.execute(
            "INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, 'Welcome credit', ?)", (uid, TRIAL_SECONDS, int(time.time())))
        if led.rowcount != 1:
            con.execute('ROLLBACK')
            return False                              # Konto hatte es schon (Re-Verify)
        con.execute("UPDATE users SET balance_sec = balance_sec + ? WHERE id = ?",
                    (TRIAL_SECONDS, uid))
        con.execute('COMMIT')
        return True
    finally:
        con.close()


# v124 Referral: beide Seiten bekommen Minuten, der Bonus fliesst erst wenn der
# Geworbene seine E-Mail bestaetigt (sonst liesse sich das mit Wegwerf-Adressen
# farmen). Pro Werber ein Deckel, alles idempotent ueber Ledger-Eintraege.
REFERRAL_SECONDS = 600          # 10 Minuten fuer jede Seite
REFERRAL_CAP = 10               # max. belohnte Einladungen pro Konto
_REF_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # ohne I/O/0/1 (Verwechslung)

# v126-sec: bekannte Wegwerf-Mail-Domains. Der Referral-Bonus wird fuer diese
# NICHT gutgeschrieben (Temp-Mail-Ringe). Kein Sign-up-Block - nur der Bonus.
_DISPOSABLE_DOMAINS = frozenset({
    'mailinator.com', 'guerrillamail.com', 'guerrillamail.info', 'guerrillamailblock.com',
    'sharklasers.com', 'grr.la', '10minutemail.com', '10minutemail.net', 'tempmail.com',
    'temp-mail.org', 'tempmail.net', 'tempr.email', 'throwawaymail.com', 'getnada.com',
    'nada.email', 'yopmail.com', 'yopmail.net', 'trashmail.com', 'trashmail.de',
    'dispostable.com', 'maildrop.cc', 'moakt.com', 'mohmal.com', 'fakeinbox.com',
    'mailnesia.com', 'mintemail.com', 'spamgourmet.com', 'mytemp.email', 'emailondeck.com',
    'inboxkitten.com', 'burnermail.io', 'anonaddy.me', 'mailsac.com', 'tmail.ws',
    'wegwerfmail.de', 'wegwerfemail.de', 'byom.de', 'einrot.com', 'cool.fr.nf',
    '33mail.com', 'mailcatch.com', 'spam4.me', 'temp-mail.io', 'luxusmail.org',
})


def _email_domain(email):
    return str(email or '').strip().lower().rsplit('@', 1)[-1] if '@' in str(email or '') else ''


def _is_disposable_email(email):
    return _email_domain(email) in _DISPOSABLE_DOMAINS


def _ref_salt():
    """Stabiler Salt fuer den Referral-E-Mail-Hash. Aus DVE_REF_SALT, sonst einmal
    persistent in DATA erzeugt - damit derselbe Hash ueber Neustarts hinweg gilt."""
    s = os.environ.get('DVE_REF_SALT', '').strip()
    if s:
        return s
    p = os.path.join(DATA, 'ref_salt')
    try:
        if os.path.exists(p):
            return open(p, encoding='utf-8').read().strip()
        os.makedirs(DATA, exist_ok=True)
        s = secrets.token_hex(16)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(s)
        return s
    except Exception:
        return 'dve-static-ref-salt'          # Notnagel: immerhin konsistent im Prozess


def _email_normal(email):
    """v230d-sec: EIN POSTFACH, EIN GRATIS-GUTHABEN.
    Alle Sperren gegen Mehrfach-Kassieren (credit_claims, referral_claims)
    haengen am Hash der eingegebenen Adresse - und die wurde nur
    kleingeschrieben. Bei Gmail landen ismet+1@gmail.com, ismet+2@gmail.com
    und is.met@gmail.com im SELBEN Postfach, ergaben aber drei verschiedene
    Hashes: Willkommens- und Werbe-Guthaben liessen sich beliebig oft
    einsammeln, jede Bestaetigungsmail kam ja real an.
    Normalisiert wird NUR fuer diesen Vergleich - die Anmelde-Identitaet
    bleibt die Adresse, die der Kunde eingegeben hat (sonst koennte sich
    ein bestehendes Konto ploetzlich nicht mehr anmelden).
    Punkte werden nur bei Anbietern entfernt, die sie nachweislich
    ignorieren; ein Plus-Tag ignorieren praktisch alle."""
    e = str(email or '').strip().lower()
    if '@' not in e:
        return e
    lokal, _, domain = e.partition('@')
    lokal = lokal.split('+', 1)[0]
    if domain in ('gmail.com', 'googlemail.com'):
        lokal = lokal.replace('.', '')
        domain = 'gmail.com'
    return f'{lokal}@{domain}' if lokal else e


def _email_hash(email):
    import hashlib
    return hashlib.sha256((_ref_salt() + ':' + _email_normal(email))
                          .encode('utf-8')).hexdigest()


def _ensure_ref_code(uid):
    """Einladungscode lazy erzeugen (8 Zeichen, kollisionsfrei), einmal pro Konto."""
    con = _db()
    try:
        row = con.execute("SELECT ref_code FROM users WHERE id = ?", (uid,)).fetchone()
        if row and row['ref_code']:
            return row['ref_code']
        # v126-sec: nur setzen, wenn noch leer (WHERE ref_code IS NULL). Bei einem
        # parallelen Aufruf gewinnt genau einer; der andere liest danach den Wert.
        # Kollisionen faengt ux_users_refcode (IntegrityError -> neuer Versuch).
        for _ in range(20):
            code = ''.join(secrets.choice(_REF_ALPHABET) for _ in range(8))
            try:
                cur = con.execute("UPDATE users SET ref_code = ? "
                                  "WHERE id = ? AND ref_code IS NULL", (code, uid))
                con.commit()
            except sqlite3.IntegrityError:
                continue                          # Code kollidiert -> neuer Wuerfel
            if cur.rowcount == 1:
                return code
            got = con.execute("SELECT ref_code FROM users WHERE id = ?",
                              (uid,)).fetchone()
            if got and got['ref_code']:
                return got['ref_code']            # ein paralleler Aufruf war schneller
        return ''
    finally:
        con.close()


def _grant_referral(new_uid):
    """Bei der E-Mail-Bestaetigung des Geworbenen: beide Seiten gutschreiben.
    v126-sec: alles in EINER BEGIN-IMMEDIATE-Transaktion (Schreibsperre ab dem
    ersten Zugriff), sodass Cap-Zaehlung und Buchung atomar sind; die
    Gutschriften laufen ueber INSERT OR IGNORE gegen ux_ledger_ref, sodass ein
    doppeltes Verify (zwei gueltige Token) NICHT doppelt bucht. Das Guthaben
    wird nur erhoeht, wenn die Ledger-Zeile wirklich frisch entstand. Kein
    Selbstwerben. Gibt True zurueck, wenn frisch belohnt wurde."""
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')            # Schreibsperre: kein TOCTOU
        nu = con.execute("SELECT referred_by, email FROM users WHERE id = ?",
                         (new_uid,)).fetchone()
        ref_id = nu['referred_by'] if nu else None
        if not ref_id or ref_id == new_uid \
                or not con.execute("SELECT id FROM users WHERE id = ?", (ref_id,)).fetchone():
            con.execute('ROLLBACK')
            return False
        # v126-sec (1): Wegwerf-Mail bekommt keinen Referral-Bonus (Ring-Schutz).
        if _is_disposable_email(nu['email']):
            con.execute('ROLLBACK')
            return False
        # v126-sec (2): pro E-Mail nur EINMAL - der Anspruch ueberlebt eine
        # Kontoloeschung (PSEUDONYM, gesalzener Hash). Loescht+neu registriert =
        # kein neuer Bonus. INSERT OR IGNORE ist zugleich das Idempotenz-Gate.
        claim = con.execute("INSERT OR IGNORE INTO referral_claims (email_hash, claimed_at) "
                            "VALUES (?, ?)", (_email_hash(nu['email']), int(time.time())))
        if claim.rowcount != 1:
            con.execute('ROLLBACK')
            return False
        now = int(time.time())
        # Geworbener: nur gutschreiben, wenn die 'Referral welcome'-Zeile frisch ist.
        cur = con.execute("INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
                          "VALUES (?, ?, 'Referral welcome', ?)",
                          (new_uid, REFERRAL_SECONDS, now))
        if cur.rowcount != 1:
            con.execute('ROLLBACK')
            return False                          # schon belohnt (idempotent)
        con.execute("UPDATE users SET balance_sec = balance_sec + ? WHERE id = ?",
                    (REFERRAL_SECONDS, new_uid))
        # Werber: unter dem Deckel, ebenfalls idempotent pro (Werber, Geworbener).
        rewarded = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id = ? "
                               "AND grund LIKE 'Referral for %'", (ref_id,)).fetchone()['c']
        if rewarded < REFERRAL_CAP:
            rc = con.execute("INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
                             "VALUES (?, ?, ?, ?)",
                             (ref_id, REFERRAL_SECONDS, f'Referral for {new_uid}', now))
            if rc.rowcount == 1:
                con.execute("UPDATE users SET balance_sec = balance_sec + ? WHERE id = ?",
                            (REFERRAL_SECONDS, ref_id))
        con.execute('COMMIT')
        return True
    except Exception:
        try: con.execute('ROLLBACK')
        except Exception: pass
        raise
    finally:
        con.close()


# v125 Credits-Verfall: das "6 Monate gueltig" der Preisseite ist jetzt CODE, nicht
# nur Text. Modell: FIFO pro Gutschrift. Jede positive Ledger-Zeile ist eine
# Gutschrift mit Datum; jeder Verbrauch (negative Zeilen, inklusive frueherer
# Verfaelle) zehrt die aelteste Gutschrift zuerst auf. Was nach 180 Tagen von
# einer Gutschrift uebrig ist, verfaellt mit eigenem Ledger-Eintrag. Dadurch ist
# der Verfall idempotent: der Eintrag selbst zaehlt beim naechsten Lauf als
# Verbrauch und stellt die alten Gutschriften auf 0.
CREDIT_VALIDITY_DAYS = float(os.environ.get('DVE_CREDIT_DAYS', '180'))
CREDIT_WARN_DAYS = 14


def _fifo_remainders(uid):
    """Ledger -> Liste der Gutschriften mit Restbetrag nach FIFO-Verbrauch:
    [{'created_at': ts, 'left': sec}, ...] (nur left > 0)."""
    con = _db()
    try:
        rows = con.execute("SELECT delta_sec, created_at FROM ledger "
                           "WHERE user_id = ? ORDER BY created_at, id", (uid,)).fetchall()
    finally:
        con.close()
    grants = [{'created_at': r['created_at'], 'left': r['delta_sec']}
              for r in rows if r['delta_sec'] > 0]
    consumed = sum(-r['delta_sec'] for r in rows if r['delta_sec'] < 0)
    for g in grants:                                   # aelteste zuerst aufzehren
        if consumed <= 0:
            break
        eat = min(g['left'], consumed)
        g['left'] -= eat
        consumed -= eat
    return [g for g in grants if g['left'] > 0]


def _expire_credits(uid):
    """Abgelaufene Gutschrift-Reste verfallen lassen (ein negativer Ledger-
    Eintrag pro Lauf). Gibt die verfallenen Sekunden zurueck, 0 wenn nichts.
    v135a: ALLES in EINER Transaktion (BEGIN IMMEDIATE) - vorher liefen
    FIFO-Snapshot und Buchung in getrennten Verbindungen, ein Render/Kauf
    dazwischen konnte zu viel oder zu wenig verfallen lassen."""
    cutoff = time.time() - CREDIT_VALIDITY_DAYS * 86400
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')
        rows = con.execute("SELECT delta_sec, created_at FROM ledger "
                           "WHERE user_id = ? ORDER BY created_at, id",
                           (uid,)).fetchall()
        grants = [{'created_at': r['created_at'], 'left': r['delta_sec']}
                  for r in rows if r['delta_sec'] > 0]
        consumed = sum(-r['delta_sec'] for r in rows if r['delta_sec'] < 0)
        for g in grants:
            if consumed <= 0:
                break
            eat = min(g['left'], consumed)
            g['left'] -= eat
            consumed -= eat
        expired = sum(g['left'] for g in grants
                      if g['left'] > 0 and g['created_at'] < cutoff)
        if expired <= 0:
            con.execute('ROLLBACK')
            return 0
        bal = con.execute("SELECT balance_sec FROM users WHERE id = ?",
                          (uid,)).fetchone()
        if not bal:
            con.execute('ROLLBACK')
            return 0
        expired = min(expired, bal['balance_sec'])     # Drift-Schutz
        if expired <= 0:
            con.execute('ROLLBACK')
            return 0
        con.execute("UPDATE users SET balance_sec = MAX(0, balance_sec - ?) "
                    "WHERE id = ?", (expired, uid))
        con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (uid, -expired, 'Expired credits '
                     + time.strftime('%Y-%m-%d'), int(time.time())))
        con.execute('COMMIT')
        return expired
    finally:
        con.close()


def _mail_abstand_ok(uid, key, abstand_s):
    """True, wenn seit der letzten Mail dieser Art mindestens `abstand_s`
    vergangen sind - und merkt sich dabei den neuen Zeitpunkt.

    v194c: Der Tages-Schluessel aus v194b war zu schwach. Er deckelt auf
    EINE Mail pro Tag, aber Videos laufen laufend ab: wer taeglich rendert,
    bekaeme 30 Mails im Monat. Ein rollender Mindestabstand deckelt wirklich.
    """
    now = int(time.time())
    con = _db()
    try:
        row = con.execute("SELECT sent_at FROM mail_log WHERE user_id = ? "
                          "AND key = ?", (uid, key)).fetchone()
        if row and now - int(row['sent_at']) < abstand_s:
            return False
        con.execute("INSERT INTO mail_log (user_id, key, sent_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, key) DO UPDATE SET sent_at = excluded.sent_at",
                    (uid, key, now))
        con.commit()
        return True
    finally:
        con.close()


def _letzter_login(uid):
    """Sekunden seit dem letzten Login. Sehr grosse Zahl, wenn keiner bekannt
    ist. Zusammen mit dem neuesten Job ist das der Test 'ist der Kunde
    gerade ohnehin da' - wer taeglich rendert, braucht keine Erinnerung,
    dass Dateien ablaufen. Er sieht die Library."""
    con = _db()
    try:
        row = con.execute("SELECT MAX(created_at) AS t FROM sessions "
                          "WHERE user_id = ?", (uid,)).fetchone()
        return (time.time() - float(row['t'])) if (row and row['t']) else 1e9
    except Exception:
        return 1e9
    finally:
        con.close()


def _log_mail_once(uid, key):
    """True genau beim ersten Mal pro (User, Schluessel), sonst False."""
    con = _db()
    try:
        cur = con.execute("INSERT OR IGNORE INTO mail_log (user_id, key, sent_at) "
                          "VALUES (?, ?, ?)", (uid, key, int(time.time())))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def _expiring_info(uid, window_days):
    """(Sekunden, Tage bis zum fruehesten Verfall) fuer Reste, die innerhalb
    von window_days ablaufen. (0, None) wenn nichts ansteht."""
    now = time.time()
    soon = [g for g in _fifo_remainders(uid)
            if g['created_at'] + CREDIT_VALIDITY_DAYS * 86400 < now + window_days * 86400]
    if not soon:
        return 0, None
    earliest = min(g['created_at'] for g in soon) + CREDIT_VALIDITY_DAYS * 86400
    return sum(g['left'] for g in soon), max(0, int((earliest - now) / 86400))


def _credit_expiry_sweep():
    """Stuendlich im Cleanup: Verfall buchen + einmalige Warn-Mail 14 Tage
    vorher (nur verifizierte Konten). Fehler bleiben leise."""
    con = _db()
    try:
        users = con.execute("SELECT id, email, name, verified FROM users").fetchall()
    finally:
        con.close()
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    for u in users:
        try:
            exp = _expire_credits(u['id'])
            if exp:
                print(f'Verfall: {credits_of(exp)} Credits bei User {u["id"]}')
            if not u['verified']:
                continue
            warn_sec, days = _expiring_info(u['id'], CREDIT_WARN_DAYS)
            if warn_sec <= 0 or credits_of(warn_sec) <= 0:
                continue
            key = 'expwarn_' + time.strftime(
                '%Y%m', time.localtime(time.time() + (days or 0) * 86400))
            if not _log_mail_once(u['id'], key):
                continue
            n = credits_of(warn_sec)
            _send_mail(u['email'], 'Some of your credits expire soon',
                       f'Hi{" " + u["name"] if u["name"] else ""},\n\n'
                       f'{n} credit{"s" if n != 1 else ""} in your DouchkoVE account '
                       f'will expire in about {days} day{"s" if days != 1 else ""}. '
                       f'Credits stay valid for six months after they are added.\n\n'
                       f'Use them on your next video:\n{base}/app#create\n\n'
                       f'DouchkoVE')
            print(f'Verfall-Warnung an User {u["id"]}: {n} Credits, {days}d')
        except Exception as e:
            print(f'Verfall-Sweep-Fehler (User {u["id"]}): {type(e).__name__}: {e}')


def _find_user_by_email(email):
    con = _db()
    row = con.execute("SELECT * FROM users WHERE email = ?",
                      (email.strip().lower(),)).fetchone()
    con.close()
    return row


def _find_user_by_id(uid):
    con = _db()
    row = con.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    con.close()
    return row


def _create_session(uid):
    tok = secrets.token_urlsafe(32)
    now = int(time.time())
    exp = now + SESSION_DAYS * 86400
    con = _db()
    con.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)", (tok, uid, now, exp))
    # alte abgelaufene Sessions gleich mit weg
    con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    con.commit()
    con.close()
    return tok, exp


def _session_user(token):
    if not token:
        return None
    con = _db()
    row = con.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.expires_at > ?",
        (token, int(time.time()))).fetchone()
    con.close()
    # v130 Admin: gesperrtes Konto -> wie ausgeloggt (kein Zugriff mehr).
    if row is not None and _row_get(row, 'disabled'):
        return None
    return row


def _row_get(row, key, default=None):
    """sqlite3.Row hat kein .get(); sicher auf evtl. fehlende Spalten zugreifen."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _kill_session(token):
    if not token:
        return
    con = _db()
    con.execute("DELETE FROM sessions WHERE token = ?", (token,))
    con.commit()
    con.close()


def _adjust_balance(uid, delta_sec, grund):
    con = _db()
    con.execute("UPDATE users SET balance_sec = MAX(0, balance_sec + ?) "
                "WHERE id = ?", (delta_sec, uid))
    con.execute(
        "INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
        "VALUES (?, ?, ?, ?)",
        (uid, delta_sec, grund[:120], int(time.time())))
    con.commit()
    con.close()


# ---------------------------------------------------------------- Mail (v80w)
def _mail_from(default_addr):
    """v133a: Absender ROBUST bauen. MAIL_FROM darf fehlen, leer sein (docker-
    compose reicht dann '' durch, was frueher 'DouchkoVE <>' ergab -> Resend
    422), eine nackte Adresse sein ODER schon im 'Name <adresse>'-Format
    stehen (so empfiehlt es .env.example; frueher wurde das doppelt verpackt).
    Ergebnis ist immer ein gueltiges 'Name <adresse>'."""
    raw = (os.environ.get('MAIL_FROM') or '').strip() or default_addr
    if '<' in raw:
        return raw                                     # schon fertig formatiert
    return f'DouchkoVE <{raw}>'


def _mail_from_bare(frm):
    """Nackte Adresse aus 'Name <adresse>' (fuer den SMTP-Envelope)."""
    m = re.search(r'<([^>]+)>', frm)
    return m.group(1) if m else frm


def _send_mail(to, subject, body, reply_to=None, html=None):
    """Mail-Versand. Bevorzugt Resend (HTTP/443, von Hostern nie geblockt),
    faellt auf SMTP zurueck. Wirft bei Fehler.
    v133c: KEIN Standard-Reply-To mehr - der noreply-Absender ist ein reines
    Versand-Postfach, Antworten darauf laufen ins Leere (so gewollt). reply_to
    wird NUR pro Aufruf gesetzt (Support-Ticket-Mail an den Betreiber).
    v133d: html optional - dann geht eine gestaltete HTML-Mail raus, body bleibt
    die Plaintext-Alternative (Fallback fuer Clients ohne HTML)."""
    resend_key = os.environ.get('RESEND_API_KEY', '').strip()
    if resend_key:
        import requests as _rq
        payload = {'from': _mail_from('onboarding@resend.dev'),
                   'to': [to], 'subject': subject, 'text': body}
        if html:
            payload['html'] = html
        if reply_to:
            payload['reply_to'] = reply_to
        r = _rq.post('https://api.resend.com/emails',
                     headers={'Authorization': f'Bearer {resend_key}'},
                     json=payload, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f'Resend {r.status_code}: {r.text[:200]}')
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER', '').strip()
    pw = os.environ.get('SMTP_PASS', '').replace(' ', '').strip()
    if not user or not pw:
        raise RuntimeError('SMTP not configured')
    frm = _mail_from(user)
    sender = _mail_from_bare(frm)
    if html:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))   # Fallback zuerst
        msg.attach(MIMEText(html, 'html', 'utf-8'))
    else:
        msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = frm
    msg['To'] = to
    if reply_to:
        msg['Reply-To'] = reply_to                    # v133c: nur pro Aufruf
    # v81c: IPv4 erzwingen. Docker-Container ohne IPv6-Route scheitern an
    # Gmails AAAA-Records mit 'Errno 101 Network is unreachable'.
    import socket
    addr = socket.getaddrinfo(host, port, socket.AF_INET,
                              socket.SOCK_STREAM)[0][4][0]
    s = smtplib.SMTP(timeout=20)
    s._host = host                    # SNI/Zertifikat-Check gegen Hostname
    try:
        s.connect(addr, port)
        s.starttls()
        s.login(user, pw)
        s.sendmail(sender, [to], msg.as_string())
    finally:
        try:
            s.quit()
        except Exception:
            pass


def _esc_html(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _email_html(heading, paragraphs, cta_text=None, cta_url=None, steps=None,
                fine_print=None):
    """v133d: gebrandetes, tabellenbasiertes HTML-Mail-Template (Inline-CSS,
    Gmail/Outlook/Apple-Mail-sicher). Heller Body, dunkles Logo, oranger Akzent
    und CTA - der DouchkoVE-Look. Ehrlich, ohne erfundene Zahlen. Rueckgabe ist
    reines HTML; die Plaintext-Alternative bleibt der body im Aufrufer.
    heading/paragraphs/steps/cta_text muessen bereits HTML-sicher sein."""
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    acc = '#ff7a1a'
    p_html = ''.join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#3f3f46;">{p}</p>'
        for p in paragraphs)
    steps_html = ''
    if steps:
        rows = ''
        for i, s in enumerate(steps, 1):
            rows += (
                '<tr>'
                f'<td valign="top" style="padding:0 12px 12px 0;">'
                f'<div style="width:26px;height:26px;border-radius:50%;background:{acc};'
                'color:#ffffff;font-weight:700;font-size:14px;text-align:center;'
                f'line-height:26px;">{i}</div></td>'
                f'<td valign="top" style="padding:2px 0 12px;font-size:15px;'
                f'line-height:1.5;color:#3f3f46;">{s}</td></tr>')
        steps_html = ('<table role="presentation" cellpadding="0" cellspacing="0" '
                      f'style="margin:4px 0 20px;">{rows}</table>')
    cta_html = ''
    if cta_text and cta_url:
        cta_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="margin:6px 0 6px;"><tr>'
            f'<td style="border-radius:10px;background:{acc};">'
            f'<a href="{cta_url}" style="display:inline-block;padding:13px 30px;'
            'font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;'
            f'font-family:Arial,Helvetica,sans-serif;">{cta_text}</a>'
            '</td></tr></table>')
    # v137: Kleingedrucktes (Pflicht-Rechtstext) unauffaellig UNTER dem CTA -
    # nicht mitten im Inhalt, aber auf dem dauerhaften Datentraeger (Mail).
    fine_html = ''
    if fine_print:
        fp = ''.join(
            f'<p style="margin:0 0 7px;font-size:10.5px;line-height:1.5;'
            f'color:#a1a1aa;">{p}</p>' for p in fine_print)
        fine_html = ('<div style="border-top:1px solid #e4e4e7;margin-top:20px;'
                     f'padding-top:12px;">{fp}</div>')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '</head><body style="margin:0;padding:0;background:#f4f4f5;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f4f5;padding:28px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;'
        'overflow:hidden;border:1px solid #e4e4e7;">'
        '<tr><td style="padding:30px 32px 0;text-align:center;">'
        f'<img src="{base}/logo_dark.png" width="120" alt="DouchkoVE" '
        'style="height:auto;max-width:120px;display:inline-block;"></td></tr>'
        f'<tr><td style="padding:0 32px;"><div style="height:3px;width:44px;'
        f'background:{acc};border-radius:2px;margin:18px auto 0;"></div></td></tr>'
        '<tr><td style="padding:22px 32px 6px;font-family:Arial,Helvetica,sans-serif;">'
        f'<h1 style="margin:0 0 16px;font-size:23px;line-height:1.25;color:#18181b;'
        f'font-weight:800;">{heading}</h1>{p_html}{steps_html}{cta_html}'
        f'{fine_html}</td></tr>'
        '<tr><td style="padding:10px 32px 30px;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="border-top:1px solid #e4e4e7;padding-top:16px;">'
        '<p style="margin:0 0 6px;font-size:13px;color:#71717a;">Need help? '
        f'Contact us at <a href="mailto:{SUPPORT_EMAIL}" style="color:{acc};'
        f'text-decoration:none;">{SUPPORT_EMAIL}</a>.</p>'
        '<p style="margin:0;font-size:12px;color:#a1a1aa;">DouchkoVE · Premium '
        'captions and motion, finished after your edit · '
        f'<a href="{base}" style="color:#a1a1aa;">douchko.eu</a></p>'
        '</div></td></tr></table></td></tr></table></body></html>')


def _create_reset(uid):
    tok = secrets.token_urlsafe(32)
    now = int(time.time())
    con = _db()
    con.execute("INSERT INTO resets (token, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)", (tok, uid, now, now + 1800))  # 30 Min
    con.execute("DELETE FROM resets WHERE expires_at < ?", (now,))
    con.commit()
    con.close()
    return tok


def _send_verify_mail(uid, email, name=''):
    """Verify-Token erzeugen + Mail raus. 48h gueltig. Fehler nicht fatal."""
    tok = secrets.token_urlsafe(32)
    now = int(time.time())
    con = _db()
    con.execute("INSERT INTO verify_tokens (token, user_id, created_at, "
                "expires_at) VALUES (?, ?, ?, ?)", (tok, uid, now, now + 172800))
    con.execute("DELETE FROM verify_tokens WHERE expires_at < ?", (now,))
    con.commit()
    con.close()
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    hallo = f'Hi {name},' if name else 'Hi,'
    link = f'{base}/app?verify={tok}'
    cr = TRIAL_SECONDS // 60
    free_line = (f'Once confirmed, your {cr} free credits are ready to use.\n\n'
                 if cr > 0 else '')
    free_html = (f'Once confirmed, your {cr} free credits are ready to use.'
                 if cr > 0 else '')
    ename = _esc_html(name)
    hi = f'Hi {ename},' if name else 'Hi,'
    try:
        _send_mail(
            email, 'Confirm your email for DouchkoVE',
            f'{hallo}\n\n'
            f'Thanks for signing up for DouchkoVE. Please confirm your email '
            f'address to activate your account:\n\n'
            f'{link}\n\n'
            f'{free_line}'
            f'This link is valid for 48 hours. If you did not create this '
            f'account, you can safely ignore this email.\n\n'
            f'Need help? Contact us at {SUPPORT_EMAIL}.\n\n'
            f'The DouchkoVE Team',
            html=_email_html(
                'Confirm your email',
                [hi,
                 'Thanks for signing up for DouchkoVE. Confirm your email '
                 'address to activate your account.']
                + ([free_html] if free_html else [])
                + ['This link is valid for 48 hours. If you did not create '
                   'this account, you can ignore this email.'],
                cta_text='Confirm email', cta_url=link))
        return True
    except Exception as e:
        print(f'Verify-Mail fehlgeschlagen: {type(e).__name__}: {e}')
        return False


def _send_welcome_mail(uid):
    """v133: Willkommens-Mail, sobald das Konto AKTIV ist. Branchen-Standard:
    Verify-Mail beim Registrieren, Willkommens-Mail nach der Bestaetigung
    (bei Google-Signup sofort, da ist die Mail schon bestaetigt). Genau EINMAL
    pro Konto (mail_log-Schluessel 'welcome'); Fehler nie fatal."""
    u = _find_user_by_id(uid)
    if not u:
        return False
    if not _log_mail_once(uid, 'welcome'):
        return False                                   # schon geschickt
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    name = (u['name'] or '').strip()
    hallo = f'Hi {name},' if name else 'Hi,'
    cr = TRIAL_SECONDS // 60
    free_line = (f'Your {cr} free credits are ready to use. One credit equals '
                 f'one minute of finished video.\n\n' if cr > 0 else '')
    ename = _esc_html(name)
    hi = f'Hi {ename},' if name else 'Hi,'
    free_html = (f'Your {cr} free credits are ready to use. One credit equals '
                 f'one minute of finished video.' if cr > 0 else '')
    try:
        _send_mail(
            u['email'], 'Welcome to DouchkoVE',
            f'{hallo}\n\n'
            f'Your account is ready. {free_line}'
            f'Getting started:\n'
            f'1. Open the app: {base}/app/create\n'
            f'2. Upload a talking head clip (vertical works best)\n'
            f'3. Let the AI pick the key moments, then render\n\n'
            f'Credits are one time purchases and stay valid for 6 months. '
            f'There is no subscription and nothing renews automatically.\n\n'
            f'Need help? Contact us at {SUPPORT_EMAIL}.\n\n'
            f'The DouchkoVE Team',
            html=_email_html(
                'Welcome to DouchkoVE',
                [hi, 'Your account is ready.']
                + ([free_html] if free_html else [])
                + ['Credits are one time purchases and stay valid for 6 months. '
                   'There is no subscription and nothing renews automatically.',
                   'Here is how to get started:'],
                cta_text='Open DouchkoVE', cta_url=f'{base}/app/create',
                steps=['Upload a talking head clip (vertical works best).',
                       'Let the AI pick the key moments.',
                       'Hit render and download your finished video.']))
        return True
    except Exception as e:
        print(f'Welcome-Mail fehlgeschlagen: {type(e).__name__}: {e}')
        return False


def _send_purchase_mail(uid, sec, session_id, cents=None, pack=None,
                        invoice_url=None):
    """v133: Kaufbestaetigung nach frisch verbuchtem Stripe-Kauf. Idempotent
    pro Session (mail_log).
    v137: Aufgeraeumt nach Ismets Feedback. Hauptteil = nur das Wichtige
    (Danke, Bestellung, Preis, Gueltigkeit, RECHNUNGS-LINK, CTA). Die
    Pflicht-Rechtstexte (§312f Vertragsbestaetigung: Consent-Zeitstempel,
    Widerrufsbelehrung, Musterformular) stehen als Kleingedrucktes UNTEN -
    ganz weglassen geht nicht, sonst laeuft die Widerrufsfrist bis zu 12
    Monate weiter (Art. 246a EGBGB, dauerhafter Datentraeger = diese Mail)."""
    u = _find_user_by_id(uid)
    if not u:
        return False
    if not _log_mail_once(uid, f'kauf:{str(session_id)[:48]}'):
        return False
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    name = (u['name'] or '').strip()
    hallo = f'Hi {name},' if name else 'Hi,'
    months = max(1, round(CREDIT_VALIDITY_DAYS / 30))
    ename = _esc_html(name)
    hi = f'Hi {ename},' if name else 'Hi,'
    n = sec // 60
    pname = PACKS.get(pack, {}).get('name', '') if pack else ''
    order = (f'DouchkoVE {pname} Pack, {n} credits'
             if pname else f'{n} credits')
    price = (f'{int(cents) / 100:.2f} EUR (no VAT, §19 UStG)'
             if cents is not None else 'see your invoice')
    inv_txt = (f'Your invoice: {invoice_url}' if invoice_url
               else 'Your invoice arrives by email shortly.')
    inv_html = (f'Your invoice: <a href="{invoice_url}" '
                f'style="color:#ff7a1a;">view and download (PDF)</a>'
                if invoice_url else 'Your invoice arrives by email shortly.')
    # §356(4)-Consent-Zeitstempel aus dem Kauf-Protokoll (juengster Eintrag).
    consent_ts = ''
    try:
        con = _db()
        _c = con.execute(
            "SELECT MAX(created_at) t FROM consents WHERE user_id = ? AND "
            "kind = 'withdrawal_immediate_performance'", (uid,)).fetchone()
        con.close()
        if _c and _c['t']:
            consent_ts = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(_c['t']))
    except Exception:
        pass
    legal = (
        'Right of withdrawal (Widerrufsbelehrung): You may withdraw from this '
        'purchase within 14 days without giving reasons; unused credits are '
        'then refunded. The right expires for credits already used, because '
        'you expressly requested immediate performance during checkout'
        + (f' (recorded {consent_ts})' if consent_ts else '') + '. '
        f'To withdraw, email {SUPPORT_EMAIL}. '
        'Model withdrawal form: To DouchkoVE, Ismet Beyazkus, Hinter den '
        f'Gaerten 4, 52388 Noervenich, Germany, {SUPPORT_EMAIL}: I hereby '
        'withdraw from my contract for the purchase of [order], ordered on '
        f'[date]. [Name], [address], [date]. Full terms: {base}/terms')
    try:
        _send_mail(
            u['email'], f'{n} credits added to your account',
            f'{hallo}\n\n'
            f'Thank you for your purchase. {n} credits have been added '
            f'to your account, and the watermark has been removed from your '
            f'finished videos.\n\n'
            f'Your order: {order}\n'
            f'Price: {price}\n'
            f'Validity: {months} months from purchase. No subscription, '
            f'nothing renews automatically.\n\n'
            f'{inv_txt}\n\n'
            f'Open the app: {base}/app/create\n\n'
            f'Need help? Contact us at {SUPPORT_EMAIL}.\n\n'
            f'The DouchkoVE Team\n\n'
            f'----\n{legal}',
            html=_email_html(
                'Payment received',
                [hi,
                 f'Thank you for your purchase. <b>{n} credits</b> have been '
                 'added to your account, and the watermark has been removed '
                 'from your finished videos.',
                 f'Your order: <b>{_esc_html(order)}</b><br>'
                 f'Price: {_esc_html(price)}<br>'
                 f'Validity: {months} months from purchase. No subscription, '
                 'nothing renews automatically.',
                 inv_html],
                cta_text='Open DouchkoVE', cta_url=f'{base}/app/create',
                fine_print=[_esc_html(legal)]))
        return True
    except Exception as e:
        print(f'Kauf-Mail fehlgeschlagen: {type(e).__name__}: {e}')
        return False


def _consume_verify(token):
    if not token:
        return None
    # v92-sec: ATOMAR konsumieren. Frueher SELECT dann UPDATE - zwei parallele
    # Requests konnten beide den SELECT passieren. Jetzt markiert ein einziges
    # UPDATE ... WHERE used=0 den Token; nur wer rowcount==1 gewinnt.
    con = _db()
    try:
        cur = con.execute(
            "UPDATE verify_tokens SET used = 1 WHERE token = ? AND used = 0 "
            "AND expires_at > ?", (token, int(time.time())))
        if cur.rowcount != 1:
            con.rollback()
            return None
        row = con.execute("SELECT user_id FROM verify_tokens WHERE token = ?",
                          (token,)).fetchone()
        con.execute("UPDATE users SET verified = 1 WHERE id = ?",
                    (row['user_id'],))
        con.commit()
        return row['user_id']
    finally:
        con.close()


def _consume_reset(token):
    """Token pruefen + als benutzt markieren (atomar). Gibt user_id oder None."""
    if not token:
        return None
    con = _db()
    try:
        cur = con.execute(
            "UPDATE resets SET used = 1 WHERE token = ? AND used = 0 "
            "AND expires_at > ?", (token, int(time.time())))
        if cur.rowcount != 1:
            con.rollback()
            return None
        row = con.execute("SELECT user_id FROM resets WHERE token = ?",
                          (token,)).fetchone()
        con.commit()
        return row['user_id']
    finally:
        con.close()


def _current_user(request):
    """Session-Cookie -> User-Row oder None."""
    return _session_user(request.cookies.get('dve_session'))


def _sitzungs_uid(request):
    """Konto-Nummer der aktuellen Sitzung oder None.
    Eigene Funktion, weil _current_user eine sqlite3.Row liefert - die hat
    KEIN .get(), und `(_current_user(r) or {}).get('id')` wirft deshalb einen
    AttributeError statt None zu liefern (dieselbe Falle wie bei _owner_ok,
    v96p; gefunden hat sie ein echter Durchlauf, nicht das Lesen)."""
    u = _current_user(request)
    return u['id'] if u else None


def _require_user(request):
    """FastAPI-Dependency-Style: wirft 401 wenn kein User."""
    u = _current_user(request)
    if not u:
        raise HTTPException(401, 'Not signed in.')
    return u


# ================================================================
# v80i: Credit-Packs + Stripe-Checkout + Konsum + Historie
# ================================================================
# Pricing: Preis (Cent) und Guthaben (Sekunden). Marge kalkuliert auf
# ~15-16 Cent Kosten pro Minute reales KI-Setup (Text-Regie 2-Pass +
# selektive Vision-Regie + Whisper).
# v84: Credit-Pakete. 1 Credit = 1 Minute fertiges Video, abgerechnet pro
# angefangener Minute. 'minuten'/'sekunden' bleiben als interne Guthaben-
# Groesse (Sekunden-Ledger), nach aussen wird in Credits gesprochen.
PACKS = {
    'starter': {
        'name': 'Starter',
        'preis_cent': 900,
        'minuten': 20,
        'sekunden': 20 * 60,
        'beschreibung_en': 'Test the waters. Enough for 6-8 short reels or 3-4 mid-length videos.',
        'hinweis_en': 'Credits valid for 6 months',
        'features_en': ['20 credits (1 credit = 1 minute of video)',
                        'All effects & animations',
                        'Full moments editor access', 'Credits valid 6 months'],
    },
    'creator': {
        'name': 'Creator',
        'preis_cent': 1900,
        'minuten': 60,
        'sekunden': 60 * 60,
        'beschreibung_en': 'Weekly posting schedule. Under €0.35 per credit.',
        'hinweis_en': 'Save 30% vs Starter · Most popular',
        'empfohlen': True,
        'features_en': ['60 credits (1 credit = 1 minute of video)',
                        '30% cheaper per credit',
                        'Priority queue in busy hours', 'Credits valid 6 months'],
    },
    'pro': {
        'name': 'Pro',
        'preis_cent': 3900,
        'minuten': 150,
        'sekunden': 150 * 60,
        'beschreibung_en': 'Daily creator or small agency. Lowest cost per credit we offer.',
        'hinweis_en': 'Save 42% vs Starter · Best value',
        'bester_wert': True,
        'features_en': ['150 credits (1 credit = 1 minute of video)',
                        '42% cheaper per credit',
                        'Priority queue', 'Credits valid 6 months'],
    },
}


def _stripe():
    """Stripe-Client mit Key aus der Umgebung. None wenn nicht konfiguriert."""
    key = os.environ.get('STRIPE_SECRET_KEY', '').strip()
    if not key:
        return None
    try:
        import stripe as _s
        _s.api_key = key
        return _s
    except ImportError:
        return None


def _has_purchased(user_id):
    """v80y: Hat der User jemals gekauft? Entscheidet ueber Wasserzeichen."""
    con = _db()
    row = con.execute("SELECT id FROM ledger WHERE user_id = ? AND grund "
                      "LIKE 'Kauf %'", (user_id,)).fetchone()
    con.close()
    return row is not None


def _grant_monthly_free(u):
    """v80y: 3 Min/Monat gratis fuer verifizierte Accounts (Konkurrenz-
    Standard: dauerhafter Free-Tier statt einmaligem Trial).
    v127-sec: ATOMAR + doppelt abgesichert wie _grant_welcome:
      1) credit_claims kind='monthly-YYYY-MM' (E-Mail-Hash, ueberlebt Loeschung)
         -> pro Person nur 1x/Monat, blockt Loeschen+Neuregistrieren-Farming.
      2) partieller Unique-Index ux_ledger_monthly -> blockt den Race, wenn zwei
         /api/me am Monatswechsel gleichzeitig laufen."""
    if not u or not u['verified']:
        return False
    stamp = time.strftime('%Y-%m')
    grund = f'Monthly free credit {stamp}'
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')
        urow = con.execute("SELECT email FROM users WHERE id = ?", (u['id'],)).fetchone()
        if not urow:
            con.execute('ROLLBACK')
            return False
        claim = con.execute(
            "INSERT OR IGNORE INTO credit_claims (email_hash, kind, claimed_at) "
            "VALUES (?, ?, ?)", (_email_hash(urow['email']), f'monthly-{stamp}',
                                 int(time.time())))
        if claim.rowcount != 1:
            con.execute('ROLLBACK')
            return False                              # diese E-Mail hat diesen Monat schon
        led = con.execute(
            "INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, ?, ?)", (u['id'], 180, grund, int(time.time())))
        if led.rowcount != 1:
            con.execute('ROLLBACK')
            return False
        con.execute("UPDATE users SET balance_sec = balance_sec + 180 WHERE id = ?",
                    (u['id'],))
        con.execute('COMMIT')
        return True
    finally:
        con.close()


def _render_charged(user_id, jid):
    """v80s: Wurde dieser Job schon abgerechnet? Re-Render = inklusive."""
    con = _db()
    row = con.execute(
        "SELECT id FROM ledger WHERE user_id = ? AND grund LIKE ?",
        (user_id, f'Render {jid} %')).fetchone()
    con.close()
    return row is not None


def _render_gebucht(user_id, jid):
    """v203-sec: Wie viele Sekunden wurden fuer diesen Job wirklich abgebucht?
    Der Ledger ist die Wahrheit ueber den Preis - nicht ein Feld am Job, das
    ein spaeterer Aufruf ueberschreiben kann. 0 heisst: noch nichts gebucht."""
    con = _db()
    row = con.execute(
        "SELECT COALESCE(SUM(-delta_sec), 0) s FROM ledger "
        "WHERE user_id = ? AND grund LIKE ? AND delta_sec < 0",
        (user_id, f'Render {jid} %')).fetchone()
    con.close()
    return int(row['s'] or 0)


def _reserve_credits(uid, need, jid, grund=None):
    """v92: Guthaben beim Upload ATOMAR reservieren (nicht erst nach dem
    Render abziehen). Ein einziges bedingtes UPDATE zieht 'need' nur ab,
    wenn wirklich genug da ist - fest gegen gleichzeitige Uploads
    (SQLite serialisiert Writes). Frueher wurde nur *geprueft*, dann spaeter
    abgezogen -> wer mit 1 Credit 10 Videos gleichzeitig hochlud, bekam 10.
    Gibt True bei Erfolg (Guthaben abgezogen + Ledger), sonst False.
    v101h: grund optional (Alpha-Ebene bucht mit eigenem Ledger-Text)."""
    if need <= 0:
        return True
    con = _db()
    try:
        cur = con.execute(
            "UPDATE users SET balance_sec = balance_sec - ? "
            "WHERE id = ? AND balance_sec >= ?", (need, uid, need))
        if cur.rowcount != 1:
            con.rollback()
            return False
        con.execute(
            "INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, -need, grund or f'Render {jid} ({need}s)', int(time.time())))
        con.commit()
        return True
    finally:
        con.close()


def _refund_credits(uid, jid, need, resv_like=None):
    """Reservierung zurueckbuchen UND die Reservierungs-Zeile entfernen.

    v126-sec: frueher wurde nur eine Gegenbuchung 'Refund {jid}' eingefuegt und
    die '-need'-Reservierung stehen gelassen. Dadurch meldete der Existenz-Check
    (_render_charged / Alpha-Guard) den Job weiter als "schon bezahlt" - ein
    Retry nach transientem Fehlschlag lieferte ein fertiges Video fuer netto 0
    Credits. Jetzt loeschen wir die offene Reservierung selbst: der naechste
    Versuch wird wieder normal abgerechnet, und das Ledger-Invariant
    (Summe(delta) == balance_sec) bleibt erhalten (geloeschte -need + balance
    +need = 0, exakt wie die alte Gegenbuchung). Idempotent ueber rowcount:
    nur wenn WIRKLICH eine offene Reservierung verschwand, wird gutgeschrieben -
    Watchdog + Worker duerfen mehrfach ausloesen. `resv_like` = LIKE-Muster der
    Reservierungs-Zeile (Default Render; Alpha/Style geben ihres explizit)."""
    if not uid or need <= 0:
        return
    like = resv_like or f'Render {jid} %'
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')                # Schreibsperre gegen TOCTOU
        # v230c-sec ERSTATTET WIRD, WAS WIRKLICH RESERVIERT WURDE.
        # Bis v230b kam der Betrag von aussen (`need` = _job_cost(j), also aus
        # j['cost_sec']). Dieses Feld laesst sich nach der Reservierung noch
        # erhoehen (Aufloesung hochstufen) - eine fehlgeschlagene Reservierung
        # gab dann MEHR zurueck, als je gezahlt wurde: aus einem Abbruch liess
        # sich Guthaben erzeugen und die Ledger-Invariante brach. Der einzige
        # Wert, der nicht luegen kann, steht in der Zeile selbst.
        _row = con.execute(
            "SELECT COALESCE(SUM(delta_sec), 0) FROM ledger "
            "WHERE user_id = ? AND grund LIKE ?", (uid, like)).fetchone()
        _resv = -int(_row[0] or 0)                    # Reservierungen sind negativ
        cur = con.execute("DELETE FROM ledger WHERE user_id = ? AND grund LIKE ?",
                          (uid, like))
        if cur.rowcount < 1 or _resv <= 0:
            con.execute('ROLLBACK')
            return                                    # nichts offen -> schon erstattet
        con.execute("UPDATE users SET balance_sec = balance_sec + ? WHERE id = ?",
                    (_resv, uid))
        con.execute('COMMIT')
    finally:
        con.close()


def _maybe_refund(jid):
    """Bei Job-Fehler die Reservierung erstatten - aber nur, wenn (noch) KEIN
    fertiges Video ausgeliefert wurde. Ein fehlgeschlagener Re-Render eines
    bereits gelieferten Videos wird NICHT erstattet (das Video existiert)."""
    j = JOBS.get(jid) or {}
    uid = j.get('user_id')
    if not uid:
        return
    if os.path.exists(os.path.join(job_dir(jid), 'fertig.mp4')):
        return
    # Motion-Jobs tragen ihre Kosten explizit (MOV kostet mehr als die Dauer
    # hergibt); sonst wie gehabt aus der Videodauer.
    _refund_credits(uid, jid, _job_cost(j))


def _pack_processed(user_id, session_id):
    """Idempotenz-Check: wurde diese Stripe-Session bereits gutgeschrieben?"""
    con = _db()
    row = con.execute(
        "SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
        (user_id, f'Kauf {session_id}')).fetchone()
    con.close()
    return row is not None


def _unlock_job(jid):
    """v101 Watermark-Unlock: gecachten sauberen Master aktivieren. Ersetzt
    fertig.mp4 durch master_clean.mp4 (atomar), raeumt auf, loescht das
    wm-Flag. True wenn wirklich freigeschaltet wurde (idempotent)."""
    d = job_dir(jid)
    mc = os.path.join(d, 'master_clean.mp4')
    if not os.path.exists(mc):
        return False
    try:
        os.replace(mc, os.path.join(d, 'fertig.mp4'))
        try:
            os.remove(os.path.join(d, 'wm.png'))
        except OSError:
            pass
        set_state(jid, wm=False)
        return True
    except OSError:
        return False


def _unlock_all_jobs(uid):
    """Beim ersten Kauf: ALLE gecachten Free-Renders des Kunden auf einmal
    freischalten - 'dein Kauf entfernt das Wasserzeichen' gilt sofort auch
    rueckwirkend fuer alles, was noch auf dem Server liegt."""
    n = 0
    for jid, j in list(JOBS.items()):
        if j.get('user_id') == uid and j.get('wm'):
            if _unlock_job(jid):
                n += 1
    if n:
        print(f"Watermark-Unlock: {n} Video(s) fuer User {uid} freigeschaltet")
    return n


def _credit_purchase(uid, sec, session_id, pack=None, cents=None):
    """v92-sec: Kauf ATOMAR + idempotent gutschreiben. Der 'INSERT OR IGNORE'
    prallt am partiellen UNIQUE-Index (user_id, 'Kauf {id}') ab, wenn dieselbe
    Stripe-Session schon verbucht ist - auch bei zwei gleichzeitigen Webhooks.
    Nur wenn wirklich eine neue Zeile entstand, wird das Guthaben erhoeht.
    Gibt True zurueck, wenn frisch gutgeschrieben wurde.
    v135a: (a) purchases-Beleg liegt jetzt in DERSELBEN Transaktion wie die
    Kauf-Zeile (kein Beleg-Verlust bei Fehler dazwischen). (b) Existiert das
    Konto nicht mehr (geloescht, Webhook kommt spaeter), wird NICHTS verbucht,
    ein Admin-Alarm geht raus (Geld kassiert -> manuell in Stripe erstatten)."""
    con = _db()
    try:
        # v135a: Geister-Konto zuerst pruefen - Geld ohne Konto ist ein Fall
        # fuer manuellen Stripe-Refund, nicht fuer eine Buchung ins Leere.
        if not con.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
            con.rollback()
            try:
                _notify_admin(f'ghostbuy:{session_id}',
                              'Kauf fuer geloeschtes Konto eingegangen',
                              f'Stripe-Session {session_id}: Konto {uid} '
                              f'existiert nicht mehr. Zahlung manuell im '
                              f'Stripe-Dashboard erstatten.')
            except Exception:
                pass
            return False
        cur = con.execute(
            "INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, sec, f'Kauf {session_id}', int(time.time())))
        if cur.rowcount != 1:
            # v135a: Beleg nachziehen, falls er beim Erstlauf verloren ging
            # (Stripe-Retries erreichen diesen Zweig).
            if cents is not None:
                con.execute("INSERT OR IGNORE INTO purchases "
                            "(session_id, user_id, pack, cents, sekunden, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (session_id, uid, pack or '?', int(cents), sec,
                             int(time.time())))
            con.commit()
            return False                     # schon verbucht
        # v124 Reload-Bonus: Wer nachkauft, waehrend das Konto praktisch leer ist
        # (< 2 Minuten Rest), bekommt still 10% obendrauf. Belohnt genau das
        # Verhalten "sofort nachladen statt abwandern"; haengt am selben
        # Idempotenz-Pfad wie der Kauf (nur bei frisch verbuchter Kauf-Zeile).
        _row = con.execute("SELECT balance_sec FROM users WHERE id = ?", (uid,)).fetchone()
        _bonus = sec // 10 if (_row and _row['balance_sec'] < 120) else 0
        con.execute("UPDATE users SET balance_sec = MAX(0, balance_sec + ?) "
                    "WHERE id = ?", (sec + _bonus, uid))
        if _bonus:
            con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (uid, _bonus, f'Reload bonus {session_id}', int(time.time())))
        if cents is not None:                # v135a: Beleg atomar mit dem Kauf
            con.execute("INSERT OR IGNORE INTO purchases "
                        "(session_id, user_id, pack, cents, sekunden, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (session_id, uid, pack or '?', int(cents), sec,
                         int(time.time())))
        con.commit()
        # v208 Stufe 6 - NACH dem commit. Innerhalb der offenen Transaktion
        # oeffnete _trichter eine ZWEITE Verbindung auf dieselbe Datei und lief
        # in "database is locked"; der Kauf wurde dann gar nicht gezaehlt.
        # Derselbe Fehlertyp wie _sec_event in v204: eine Nebenbuchung gehoert
        # nie in die Transaktion, die sie beobachtet. Der Webhook kommt von
        # Stripe, nicht aus einem Browser - es gibt hier weder Besucher-Kennung
        # noch Verweis; die Herkunft wird beim Auswerten ueber die Konto-Nummer
        # nachgeschlagen.
        _trichter('kauf', None, user_id=uid, quelle='', besucher='')
        try:
            _unlock_all_jobs(uid)            # v101: Kauf entfernt Wasserzeichen
        except Exception as e:               # Unlock darf den Kauf nie reissen
            print(f'Auto-Unlock fehlgeschlagen: {e}')
        return True
    finally:
        con.close()


app = FastAPI(title='DouchkoVE')


# v92-sec: Security-Header auf JEDER Antwort. Zweite Verteidigungslinie gegen
# XSS (CSP), Clickjacking (frame-ancestors/XFO), Token-Leak per Referer
# (Referrer-Policy) und MIME-Sniffing (nosniff). Caddy setzt sie am Rand
# zusaetzlich - hier greifen sie auch, falls die App direkt erreichbar ist.
# v230ah SCRIPT-CSP OHNE `unsafe-inline`. Bis hierher durfte jedes Inline-
# Skript laufen - also auch eines, das ein Angreifer irgendwo hineinbekommt.
# Die Seiten sind bewusst je EINE Datei (Markup, Stil und Skript zusammen);
# statt sie aufzuteilen, steht der SHA256-Fingerabdruck jedes Inline-Blocks
# in der Regel. Der Browser laesst dann genau diese Bloecke laufen und sonst
# keinen. Die Fingerabdruecke werden aus den ausgelieferten Dateien berechnet
# und bei jeder Aenderung neu (mtime), damit die Regel nach einem Deploy nicht
# gegen die alte Fassung steht.
# Style bleibt bei 'unsafe-inline': `style="..."` steht an hunderten Stellen im
# Markup, und ein Fingerabdruck deckt Attribute gar nicht ab. Der Gewinn waere
# klein, der Umbau riesig - bewusste Entscheidung, nicht Vergessen.
_CSP_HTML = ('index.html', 'landing.html', 'admin.html', 'example.html',
             'imprint.html', 'privacy.html', 'terms.html')
_CSP_CACHE = {'stempel': None, 'wert': None}
_CSP_LOCK = threading.Lock()


def _inline_script_hashes():
    """SHA256 jedes Inline-<script>-Blocks der ausgelieferten Seiten."""
    hashes, stempel = [], []
    for name in _CSP_HTML:
        p = os.path.join(HERE, name)
        try:
            stt = os.stat(p)
        except OSError:
            continue
        stempel.append((name, stt.st_mtime_ns, stt.st_size))
        try:
            txt = open(p, encoding='utf-8').read()
        except OSError:
            continue
        for m in re.finditer(r'<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>',
                             txt, re.S):
            h = base64.b64encode(
                hashlib.sha256(m.group(1).encode('utf-8')).digest()).decode()
            hashes.append(f"'sha256-{h}'")
    return tuple(stempel), sorted(set(hashes))


def _csp():
    """Die Regel selbst - mit den Fingerabdruecken der aktuellen Dateien."""
    with _CSP_LOCK:
        stempel, hashes = _inline_script_hashes()
        if _CSP_CACHE['stempel'] == stempel and _CSP_CACHE['wert']:
            return _CSP_CACHE['wert']
        wert = (
            "default-src 'self'; "
            "script-src 'self' " + ' '.join(hashes) + "; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "font-src 'self'; "
            "object-src 'none'; "                 # kein <object>/<embed>
            "connect-src 'self' https://api.stripe.com; "
            "frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self' https://checkout.stripe.com"
        )
        _CSP_CACHE['stempel'], _CSP_CACHE['wert'] = stempel, wert
        return wert


# Build-Stempel: zeigt an, welcher Stand wirklich live ist (per Header sichtbar).
# v222 DER STEMPEL MUSS AUS DEM DEPLOY KOMMEN, NICHT AUS EINER KONSTANTEN.
# Bis v221 stand hier fester Text - 'v213-ansage', monatelang nicht mitgezogen.
# Er landet ueber DVE_JOB_TAG in den Metadaten JEDES Videos, log also bei jedem
# Kundenrender. Ergebnis: drei Fixes geliefert, drei Renders geprueft, dreimal
# geraetselt, warum sich nichts aendert - in Wahrheit lief der Server noch auf
# dem alten Stand, weil der Deploy nicht griff, und NICHTS konnte das zeigen.
# v225c DER STEMPEL GEHOERT INS IMAGE, NICHT IN DAS DATENVERZEICHNIS.
# v222 schrieb ihn nach DVE_DATA - auf dem HOST. Im Container ist DVE_DATA aber
# `/data`, ein Docker-Volume (`dve-data`), das mit dem Host-Verzeichnis nichts
# zu tun hat. Der Server hat die Datei also NIE gesehen: das Panel zeigte
# dauerhaft 'Commit unbekannt', der Wachhund mailte "Seit Tagen kein Deploy",
# und die Video-Metadaten trugen weiterhin keinen Commit - genau die drei
# Dinge, die v222 beheben sollte. Der Fehlalarm hat es aufgedeckt.
# Zweiter, schwererer Grund fuer den Wechsel: ein Stempel im Datenverzeichnis
# behauptet den NEUEN Commit, sobald `git pull` durch ist - auch wenn das
# Test-Gate danach abbricht und weiterhin die ALTE Fassung laeuft. Ein Stempel,
# der luegen kann, ist wertlos. Im Image kann er es nicht: `update.sh` legt
# `build.json` in das Bauverzeichnis, `COPY . /app/` nimmt sie mit, und der
# laufende Container liest damit ausschliesslich seinen EIGENEN Stand.
DVE_VERSION = 'v230ap'


def _build_datei():
    """Der Stempel des laufenden Stands. Reihenfolge ist wichtig: zuerst der
    im Image mitgebaute (der kann nicht luegen), dann als Rueckfall das
    Datenverzeichnis (Desktop/Handbetrieb ohne Docker)."""
    for p in (os.path.join(ROOT, 'build.json'),
              os.path.join(DATA, 'build.json')):
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, 'build.json')


def _build_stempel():
    """Branch + Commit des LAUFENDEN Stands. Fehlt die Datei (Erst-Start,
    Handbetrieb), bleibt die Programm-Version - dann steht dort ehrlich
    'unbekannt' statt einer Zahl, die niemand geprueft hat."""
    try:
        with open(_build_datei(), encoding='utf-8') as fh:
            b = json.load(fh)
        c = str(b.get('commit') or '')[:8]
        br = str(b.get('branch') or '')
        if c:
            return f"{DVE_VERSION} {c}" + (f" ({br})" if br else '')
    except Exception:
        pass
    return f'{DVE_VERSION} (Commit unbekannt)'


DVE_BUILD = _build_stempel()


def _deploy_info():
    """v222: Branch, Commit und ALTER des laufenden Stands - fuer das Panel.
    Das Alter ist der eigentliche Wert: ein Deploy, der nie stattfand, war
    bisher unsichtbar. `autodeploy.sh` meldet nur einen GESCHEITERTEN
    Versuch; steht der Server auf einem anderen Branch, sieht er dauerhaft
    'nichts Neues' und schweigt. Genau so lief der Server monatelang auf
    v213, waehrend die Arbeit auf einem anderen Zweig lag."""
    out = {'version': DVE_VERSION, 'commit': '', 'branch': '',
           'subject': '', 'deployed_at': 0, 'alter_tage': None, 'warnung': ''}
    try:
        with open(_build_datei(), encoding='utf-8') as fh:
            b = json.load(fh)
        out['commit'] = str(b.get('commit') or '')[:12]
        out['branch'] = str(b.get('branch') or '')
        out['subject'] = str(b.get('subject') or '')[:120]
        out['deployed_at'] = int(b.get('deployed_at') or 0)
        if out['deployed_at']:
            _t = (time.time() - out['deployed_at']) / 86400.0
            out['alter_tage'] = round(_t, 1)
            if _t > 3:
                out['warnung'] = (f"Der laufende Stand ist {_t:.0f} Tage alt. "
                                  f"Wenn seitdem gepusht wurde, greift der "
                                  f"Auto-Deploy nicht - Branch auf dem Server "
                                  f"pruefen.")
    except Exception:
        out['warnung'] = ('Kein Build-Stempel vorhanden. Der laufende Stand ist '
                          'unbekannt - dieser Container wurde vor v225c gebaut. '
                          'Nach dem naechsten Deploy steht hier Branch und '
                          'Commit.')
    # v230j WAS GERADE PASSIERT, NICHT NUR WAS LAEUFT.
    # Das Panel zeigte bisher ausschliesslich den LAUFENDEN Stand. Damit laesst
    # sich "dauert noch" nicht von "haengt" unterscheiden - Ismets Befund
    # ("habe es satt, dass die Builds nicht uebernommen werden", waehrend der
    # Deploy in Wahrheit nur vier Minuten alt war). autodeploy.sh schreibt
    # seinen Zustand jetzt in `deploy_state`, und der Deploy MISST SICH SELBST:
    # jede fertige Runde legt ihre Dauer ab. Damit steht im Panel eine echte
    # Zahl vom eigenen Server statt einer Schaetzung.
    try:
        con = _db()
        r = con.execute("SELECT phase, commit_kurz, started_at, finished_at, "
                        "dauer_s, grund FROM deploy_state WHERE id = 1"
                        ).fetchone()
        con.close()
        if r:
            d = {k: r[k] for k in r.keys()}
            d['laeuft_seit'] = (int(time.time() - (d.get('started_at') or 0))
                                if d.get('phase') == 'baut' else 0)
            # Ein 'baut', das ewig steht, ist ein Haenger - nicht "dauert noch".
            if d['phase'] == 'baut' and d['laeuft_seit'] > 45 * 60:
                d['phase'] = 'haengt'
            out['deploy'] = d
    except Exception:
        pass
    return out


# ================= v204-sec NOTAUS =================
# Bis v203 gab es Massnahmen gegen EIN Konto (sperren, Sitzungen widerrufen),
# aber keinen Hebel fuer "jetzt sofort alles anhalten". Genau den braucht man
# in der einen Stunde, in der man noch nicht weiss, was los ist.
# Drei Stufen, im Panel schaltbar:
#   normal    - Betrieb wie immer
#   pausiert  - keine NEUEN Registrierungen, Uploads, Renders, Kaeufe.
#               Laufendes laeuft aus, Downloads bleiben offen. Der Kunde
#               sieht eine ehrliche Meldung statt eines kaputten Knopfs.
#   notaus    - zusaetzlich sind ALLE Sitzungen beendet (einmalig beim
#               Umschalten) und die App antwortet nur noch lesend.
# Der Zustand liegt als Datei in DATA, nicht im Prozessspeicher: ein Neustart
# darf einen Notaus nicht aufheben.
BETRIEB_DATEI = os.path.join(DATA, 'betrieb.txt')
_BETRIEB_STUFEN = ('normal', 'pausiert', 'notaus')
# Pfade, die AUCH im Notaus erreichbar bleiben muessen - sonst sperrt man sich
# selbst aus (Panel) oder der Uptime-Pinger schlaegt Alarm.
_NOTAUS_FREI = ('/api/health', '/api/admin/', '/admin', '/api/announcements',
                '/api/pricing', '/imprint', '/privacy', '/terms')


def betrieb_stufe():
    try:
        v = open(BETRIEB_DATEI, encoding='utf-8').read().strip().lower()
        return v if v in _BETRIEB_STUFEN else 'normal'
    except Exception:
        return 'normal'


def betrieb_setzen(stufe):
    stufe = (stufe or '').strip().lower()
    if stufe not in _BETRIEB_STUFEN:
        raise HTTPException(400, 'stufe must be normal, pausiert or notaus')
    os.makedirs(DATA, exist_ok=True)
    with open(BETRIEB_DATEI, 'w', encoding='utf-8') as f:
        f.write(stufe)
    if stufe == 'notaus':
        try:
            con = _db()
            con.execute('DELETE FROM sessions')      # alle Kunden abgemeldet
            con.commit(); con.close()
        except Exception as e:
            print(f'Notaus: Sitzungen nicht geleert: {e}')
    return stufe


# Welche Wege sind bei 'pausiert' zu? Nur das, was NEUE Arbeit oder Geld
# ausloest - Ansehen und Herunterladen bleibt erlaubt.
_PAUSE_ZU = ('/api/upload', '/api/upload/', '/api/render_start', '/api/moments',
             '/api/transcript', '/api/checkout', '/api/register',
             '/api/motion', '/api/style/learn', '/api/alpha')


@app.middleware('http')
async def _betriebs_schranke(request, call_next):
    """Greift VOR jedem Endpunkt - ein Notaus, den man in 30 Endpunkten
    einzeln einbauen muss, ist keiner."""
    stufe = betrieb_stufe()
    if stufe != 'normal':
        pfad = request.url.path
        frei = any(pfad.startswith(p) for p in _NOTAUS_FREI)
        if not frei:
            if stufe == 'notaus' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
                return JSONResponse(
                    {'detail': 'Maintenance: the service is paused. '
                               'Please try again later.'}, status_code=503)
            if stufe == 'pausiert' and any(pfad.startswith(p) for p in _PAUSE_ZU):
                return JSONResponse(
                    {'detail': 'Maintenance: new jobs are paused right now. '
                               'Your existing videos stay available.'},
                    status_code=503)
    return await call_next(request)


@app.middleware('http')
async def _security_headers(request, call_next):
    resp = await call_next(request)
    # v142: jede erfolgreiche schreibende Anfrage verwirft die Admin-Aggregate.
    # Zentral hier statt in 20 Endpunkten - so kann kein neuer Schreibpfad die
    # Invalidierung vergessen (Kauf, Refund, Credits, Factory-Reset).
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and resp.status_code < 400:
        _ttl_drop('adm:')
    resp.headers['Content-Security-Policy'] = _csp()
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Strict-Transport-Security'] = ('max-age=31536000; '
                                                 'includeSubDomains; preload')
    # v230ah: die Seite braucht KEINE Kamera, kein Mikrofon, keinen Standort -
    # also bekommt sie sie auch nicht. Ein eingeschleustes Skript kann damit
    # nicht einmal fragen.
    resp.headers['Permissions-Policy'] = (
        'camera=(), microphone=(), geolocation=(), payment=(), usb=(), '
        'magnetometer=(), gyroscope=(), accelerometer=(), interest-cohort=()')
    # v230ah: der Build-Stempel ging bisher an JEDEN Aufrufer und nannte
    # Version, Commit UND Branch. Fuer Fremde ist das nur ein Fingerabdruck
    # der Fassung; gebraucht wird er von Ismet. Also nur noch mit Admin-Key
    # (das Panel und /api/health zeigen ihn ohnehin).
    if _admin_ok(request):
        resp.headers['X-DVE-Version'] = DVE_BUILD
    return resp


@app.exception_handler(ClientDisconnect)
async def _weggegangen(request, exc):
    """v208b: Der Kunde hat die Verbindung gekappt (Tab zu, Funkloch, Upload
    abgebrochen). Es gibt niemanden mehr, dem man antworten koennte, und es
    ist kein Fehler unseres Servers - also KEIN Eintrag unter Stoerungen.
    Ohne diesen Riegel meldete jeder abgebrochene Upload einen "Serverfehler",
    und echte Stoerungen gehen in dem Rauschen unter."""
    pfad = getattr(getattr(request, 'url', None), 'path', '?')
    print(f'Client hat die Verbindung getrennt: {pfad}')
    return JSONResponse({'detail': 'Client disconnected.'}, status_code=499)


@app.exception_handler(Exception)
async def _unhandled(request, exc):
    """v197: Bis v196 landete nur ein FEHLGESCHLAGENER RENDER in der
    alerts-Tabelle. Ein Absturz in einem Endpunkt (Kauf, Login, Library)
    ging als Traceback nach stdout und war nach dem naechsten Deploy weg -
    niemand hat je erfahren, dass ein Kunde einen 500er gesehen hat.
    Jeder unbehandelte Fehler steht jetzt im Admin-Panel unter Alerts.
    Der Deckel in _notify_admin (1 Mail/Stunde je Schluessel) verhindert,
    dass ein dauerhaft kaputter Endpunkt das Postfach flutet; die
    Panel-Zeile wird trotzdem jedes Mal geschrieben.
    Der Kunde bekommt KEINEN Traceback zu sehen."""
    import traceback
    spur = traceback.format_exc()
    pfad = getattr(getattr(request, 'url', None), 'path', '?')
    # v208b: Die URSACHE steht ganz oben, nicht am Ende. Ein Traceback faengt
    # mit dem AEUSSERSTEN Rahmen an (Middleware, Routing) und nennt den
    # eigentlichen Fehler erst in der letzten Zeile - wer die Meldung im Panel
    # liest oder kopiert, sieht ohne diese Umkehrung nur Bibliotheks-Innereien.
    _letzte = [z for z in spur.strip().splitlines() if z.strip()][-6:]
    try:
        _notify_admin(f'exc:{type(exc).__name__}:{pfad}',
                      f'Serverfehler {type(exc).__name__} in {pfad}',
                      f'{request.method} {pfad}\n\n'
                      f'URSACHE: {type(exc).__name__}: {exc}\n\n'
                      + '\n'.join(_letzte)
                      + f'\n\nVoller Verlauf:\n{spur}')
    except Exception:
        pass
    print(f'ERROR unbehandelt {request.method} {pfad}: '
          f'{type(exc).__name__}: {exc}\n{spur}')
    return JSONResponse({'detail': 'Internal server error.'}, status_code=500)


@app.get('/api/pricing')
def api_pricing():
    # v84: Credits mitliefern (1 Credit = 1 Minute), Anzeige-Sprache im
    # Frontend spricht Credits statt roher Minuten.
    packs = {}
    for pid, p in PACKS.items():
        q = dict(p)
        q['credits'] = int(p['sekunden']) // 60
        packs[pid] = q
    return {'packs': packs,
            'trial_sec': TRIAL_SECONDS,
            'trial_credits': credits_of(TRIAL_SECONDS),
            'credit_minutes': 1,
            'stripe_ready': _stripe() is not None}


def _invoice_creation(pack_id, p):
    """v134: Stripe erstellt fuer jeden Kauf automatisch eine Rechnung
    (Post-Payment-Invoice, 0,4% Gebuehr) und mailt sie dem Kunden. Recht:
    Kleinunternehmer §19 UStG -> NIEMALS USt ausweisen, stattdessen der
    Pflichthinweis im Footer. Alle Pakete liegen unter 250 EUR =
    Kleinbetragsrechnung (§33 UStDV), vereinfachte Pflichtangaben, keine
    Kundenanschrift noetig. Steuernummer optional ueber DVE_TAX_ID.
    Firmenname/Anschrift im Rechnungskopf kommen aus den Stripe-
    Unternehmensdaten (Dashboard, einmalig pflegen)."""
    # v135: Ismets USt-IdNr als fester Default (Pflichtangabe §14 UStG:
    # Steuernummer ODER USt-IdNr; sie steht auch oeffentlich im Impressum).
    # 'or'-Fallback statt get-Default: docker-compose reicht bei fehlender
    # .env-Zeile einen LEEREN String durch, der den get-Default schlagen wuerde.
    tax_id = (os.environ.get('DVE_TAX_ID') or 'DE463613884').strip()
    label = ('USt-IdNr.' if re.match(r'(?i)^DE\d{9}$', tax_id)
             else 'Steuernummer')
    # v145: VOLLSTAENDIGE Aussteller-Angaben in die Rechnung.
    # Der Rechnungskopf ('Von: ...') kommt aus den Stripe-Unternehmensdaten im
    # Dashboard - darauf hat der Code keinen Zugriff. Steht dort nur die Marke,
    # fehlt der Rechnung der vollstaendige Name und die Anschrift des
    # leistenden Unternehmers (§14 Abs. 4 Nr. 1 UStG; bei Kleinbetraegen bis
    # 250 EUR §33 UStDV ebenfalls Pflicht). Deshalb tragen Fusszeile UND
    # Zusatzfelder die Identitaet noch einmal selbst - dann stimmt die
    # Rechnung auch, wenn im Dashboard etwas fehlt oder spaeter verstellt wird.
    name = (os.environ.get('DVE_SELLER_NAME') or 'Ismet Beyazkus').strip()
    marke = (os.environ.get('DVE_SELLER_BRAND') or 'DouchkoVE').strip()
    adresse = (os.environ.get('DVE_SELLER_ADDR')
               or 'Hinter den Gärten 4, 52388 Nörvenich, Germany').strip()
    mail = (os.environ.get('DVE_SELLER_MAIL') or 'Ismet@douchkove.com').strip()
    kopf = ' · '.join(x for x in (f'{name} ({marke})' if marke else name,
                                  adresse, mail) if x)
    # v165: Leistungsdatum ist Pflichtangabe (§14 Abs. 4 Nr. 6 UStG). Bei
    # Credits ist die Leistung mit dem Kauf erbracht (Guthaben-Freischaltung),
    # darum genuegt der Verweis auf das Ausstellungsdatum.
    footer = (kopf + (f'\n{label}: {tax_id}' if tax_id else '') + '\n'
              'Gemäß §19 UStG wird keine Umsatzsteuer berechnet. / '
              'No VAT is charged in accordance with §19 UStG '
              '(German small business scheme).\n'
              'Leistungsdatum entspricht dem Ausstellungsdatum. / '
              'Date of service corresponds to the invoice date.')
    # Zusatzfelder stehen im Rechnungskopf, nicht unten im Kleingedruckten.
    # Stripe deckelt sie bei 30 Zeichen je Name und Wert - laengere Werte
    # weist die API zurueck und riesse den ganzen Checkout mit. Die Anschrift
    # passt dort nicht hinein, sie steht deshalb nur in der Fusszeile.
    # v165: Marke UND buergerlicher Name zusammen ("DouchkoVE - Ismet
    # Beyazkus") - §14 UStG verlangt den vollstaendigen Namen des leistenden
    # Unternehmers, die Marke allein reicht nicht. 30-Zeichen-Deckel von
    # Stripe beachten: passt beides nicht hinein, gewinnt der NAME, denn der
    # ist die Pflichtangabe, die Marke nicht.
    _ausst = f'{marke} - {name}' if marke else name
    if len(_ausst) > 30:
        _ausst = name
    felder = [{'name': 'Aussteller', 'value': _ausst[:30]}]
    if tax_id:
        felder.append({'name': label[:30], 'value': tax_id[:30]})
    return {
        'enabled': True,
        'invoice_data': {
            'description': (f"DouchkoVE {p['name']} Pack, "
                            f"{p['minuten']} minutes of video credit"),
            'footer': footer,
            'custom_fields': felder,
            'metadata': {'pack': pack_id},
        },
    }


@app.post('/api/checkout')
async def api_checkout(request: Request, pack: str = Form(...),
                       consent: str = Form('')):
    """Erstellt eine Stripe-Checkout-Session und liefert die URL zurueck.
    Weiterleitung dorthin macht der Client (window.location)."""
    u = _require_user(request)
    if not u['verified']:
        raise HTTPException(403, 'Please verify your email before purchasing - '
                                 'check your inbox, or resend the link in '
                                 'Account settings.')
    if pack not in PACKS:
        raise HTTPException(400, 'Unknown pack.')
    # v127-recht: Widerrufs-Einwilligung ist Pflicht vor dem Kauf (§ 356 (4) BGB).
    # Der Client hakt die Bestaetigung aktiv an; ohne sie kein Checkout. Mit
    # Zeitstempel protokolliert (Beweislast fuer die wirksame Verzichtserklaerung).
    if str(consent).strip() not in ('1', 'true', 'on', 'yes'):
        raise HTTPException(400, 'Please confirm the immediate-performance notice '
                                 'before purchasing.')
    try:
        con = _db()
        con.execute("INSERT INTO consents (user_id, kind, created_at) "
                    "VALUES (?, 'withdrawal_immediate_performance', ?)",
                    (u['id'], int(time.time())))
        con.commit()
        con.close()
    except Exception as e:
        # v135a: FAIL-CLOSED. Ohne protokollierten Consent fehlt der Beweis
        # fuer den Widerrufsverzicht (§356 Abs. 4 BGB) - ein Kauf ohne Beweis
        # ist schlechter als ein um Sekunden verzoegerter Kauf.
        print(f'Consent-Log fehlgeschlagen: {e}')
        raise HTTPException(503, 'Could not record your purchase confirmation. '
                                 'Please try again in a moment.')
    st = _stripe()
    if not st:
        raise HTTPException(503, 'Payment is not configured yet. '
                                 'Please try again later.')
    p = PACKS[pack]
    base = os.environ.get('DVE_PUBLIC_URL', '').rstrip('/') or str(request.base_url).rstrip('/')

    def _mk_session(with_invoice):
        kwargs = dict(
            mode='payment',
            # v135c: KEINE festen payment_method_types mehr. Der Live-Fehler
            # war 'sepa_debit is invalid' - im Stripe-Konto nicht aktiviert,
            # Stripe lehnte damit die GANZE Session ab. Ohne die Vorgabe zeigt
            # Stripe automatisch alle im Dashboard aktivierten Zahlarten
            # (Karte jetzt; SEPA/weitere sobald dort freigeschaltet, ohne
            # Code-Aenderung). Der Webhook kann async-Zahlarten schon (v92).
            line_items=[{
                'quantity': 1,
                'price_data': {
                    'currency': 'eur',
                    'unit_amount': p['preis_cent'],
                    'product_data': {
                        'name': f"DouchkoVE {p['name']} Pack",
                        'description': f"{p['minuten']} minutes of video credit",
                    },
                },
            }],
            metadata={
                'user_id': str(u['id']),
                'user_email': u['email'],
                'pack': pack,
                'sekunden': str(p['sekunden']),
            },
            customer_email=u['email'],
            success_url=f'{base}/app?bezahlt=1&pack={pack}',
            cancel_url=f'{base}/app?bezahlt=0',
            allow_promotion_codes=True,
        )
        if with_invoice:
            kwargs['invoice_creation'] = _invoice_creation(pack, p)  # v134: §19
        return st.checkout.Session.create(**kwargs)

    # v142 ASYNC: st.checkout.Session.create ist ein blockierender HTTPS-Call
    # zu Stripe (typisch 200-800 ms, im Stoerfall Sekunden). In einem
    # 'async def'-Endpunkt haelt er den EINZIGEN Event-Loop an - waehrend ein
    # Kunde bezahlt, steht die Seite fuer alle anderen. In den Threadpool.
    import asyncio as _aio
    try:
        try:
            session = await _aio.to_thread(_mk_session, True)
        except Exception as e:
            # v135b: Der KAUF geht immer vor der Rechnung. Lehnt Stripe die
            # Session wegen invoice_creation ab (alte Lib/API-Version kennt den
            # Parameter nicht -> InvalidRequestError), einmal OHNE Rechnung
            # retryen + Alarm; Rechnung dann manuell im Dashboard nachziehen.
            if type(e).__name__ == 'InvalidRequestError' and 'invoice' in str(e).lower():
                print(f'Checkout: invoice_creation abgelehnt ({e}) - retry ohne Rechnung')
                _notify_admin('inv_fallback', 'Stripe-Rechnung im Checkout abgelehnt',
                              f'invoice_creation wurde von Stripe abgelehnt: {e}\n'
                              f'Kauf laeuft OHNE automatische Rechnung weiter - '
                              f'Stripe-Lib/API-Version pruefen, Rechnung manuell '
                              f'im Dashboard erstellen.')
                session = await _aio.to_thread(_mk_session, False)
            else:
                raise
        return {'ok': True, 'url': session.url}
    except Exception as e:
        cls = type(e).__name__
        print(f'Checkout fehlgeschlagen: {cls}: {e}')      # v135b: echte Ursache ins Log
        if cls == 'AuthenticationError':
            msg = 'Payment provider rejected our credentials. Server-side config issue, support has been notified.'
        elif cls == 'APIConnectionError':
            msg = 'Could not reach the payment provider. Please try again in a minute.'
        else:
            msg = f'Payment error ({cls}). Please try again in a minute.'
        raise HTTPException(500, msg)


@app.post('/api/stripe/webhook')
async def api_stripe_webhook(request: Request):
    """Stripe ruft hier an sobald eine Zahlung wirklich durch ist. Wir
    verifizieren die Signatur und schreiben das Guthaben gut. Idempotent -
    Stripe kann Webhooks mehrfach senden."""
    import asyncio as _aio2
    st = _stripe()
    if not st:
        raise HTTPException(503, 'Stripe not configured.')
    secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '').strip()
    payload = await request.body()
    sig = request.headers.get('stripe-signature', '')
    # v92 SECURITY: Ohne Webhook-Secret wird NICHT gutgeschrieben. Frueher
    # wurde die Signatur nur geprueft "if secret" - ohne Secret akzeptierte
    # der Endpoint jeden POST, jeder haette sich mit einem gefaelschten
    # "checkout.session.completed" gratis Guthaben schreiben koennen. Die
    # Signatur ist die EINZIGE Echtheits-Garantie und daher Pflicht.
    if not secret:
        raise HTTPException(503, 'Webhook secret not configured.')
    try:
        st.Webhook.construct_event(payload, sig, secret)   # Signatur MUSS passen
        event = json.loads(payload)
    except Exception as e:
        raise HTTPException(400, f'Webhook invalid: {type(e).__name__}')
    ev_type = event.get('type')
    # v92-sec: Bei Karte kommt 'completed' sofort mit payment_status='paid'.
    # Bei SEPA/verzoegerten Methoden ist 'completed' noch NICHT bezahlt
    # (payment_status='unpaid'/'processing') - das Geld kommt erst spaeter per
    # 'async_payment_succeeded'. Frueher wurde bei 'completed' bedingungslos
    # gutgeschrieben -> SEPA-Nutzer haetten Credits VOR (evtl. scheiterndem)
    # Geldeingang bekommen. Jetzt: nur gutschreiben, wenn wirklich bezahlt.
    # v135a: Stripe-seitige Erstattung (z.B. im Dashboard ausgeloest) sichtbar
    # machen - sonst weicht die interne Buchhaltung still von Stripe ab.
    if ev_type == 'charge.refunded':
        ch = event.get('data', {}).get('object', {}) or {}
        # v206: Eine im Stripe-Dashboard ausgeloeste Erstattung muss GENAUSO
        # vom Umsatz abgehen wie eine aus dem Panel. Bis v205 gab es dafuer
        # nur eine Meldung - die interne Buchhaltung lief still auseinander.
        try:
            _sess_id = ''
            _pi = ch.get('payment_intent')
            if _pi and _stripe():
                _li = _stripe().checkout.Session.list(payment_intent=_pi, limit=1)
                _d = (_li.get('data') if isinstance(_li, dict) else _li.data) or []
                if _d:
                    _sess_id = (_d[0].get('id') if isinstance(_d[0], dict)
                                else _d[0].id) or ''
            if _sess_id:
                _c_ref = _db()
                _r_uid = _c_ref.execute("SELECT user_id FROM purchases WHERE "
                                        "session_id = ?", (_sess_id,)).fetchone()
                _c_ref.execute(
                    "INSERT OR IGNORE INTO refunds (session_id, user_id, cents, "
                    "quelle, created_at) VALUES (?,?,?,'stripe',?)",
                    (_sess_id, (_r_uid['user_id'] if _r_uid else None),
                     int(ch.get('amount_refunded', 0) or 0), int(time.time())))
                _c_ref.commit(); _c_ref.close()
        except Exception as e:
            print(f'Stripe-Erstattung nicht vermerkt: {type(e).__name__}: {e}')
        try:
            _notify_admin(f"stref:{ch.get('id', '?')}",
                          'Stripe-Erstattung eingegangen',
                          f"Charge {ch.get('id')} ueber "
                          f"{int(ch.get('amount_refunded', 0)) / 100:.2f} EUR "
                          f"wurde (teil)erstattet. Credits ggf. im Admin-Panel "
                          f"zurueckbuchen (Users -> Kauf -> Refund).")
        except Exception:
            pass
        return {'ok': True, 'noted': 'refund'}
    if ev_type not in ('checkout.session.completed',
                       'checkout.session.async_payment_succeeded'):
        return {'ok': True, 'ignored': ev_type}
    sess = event.get('data', {}).get('object', {})
    # v135a: 'no_payment_required' ist bei 100%-Promo-Codes der finale Status -
    # die signierte Session ist genauso vertrauenswuerdig wie 'paid'. Frueher
    # bekam ein Gratis-Code-Kaeufer nie seine Credits.
    if sess.get('payment_status') not in ('paid', 'no_payment_required'):
        return {'ok': True, 'pending': sess.get('payment_status')}
    meta = sess.get('metadata') or {}
    try:
        uid = int(meta.get('user_id'))
        pack = meta.get('pack', '?')
        sess_id = sess.get('id', '')
        # v127-sec: gutgeschriebene Sekunden aus dem SERVER-Katalog ableiten,
        # nicht der Metadaten-Zahl vertrauen. So ist die Gutschrift fest an
        # PACKS gekoppelt und nie von einer abweichenden 'sekunden'-Angabe
        # entkoppelt. Unbekanntes Paket -> Fallback auf die Metadaten.
        sec = int(PACKS[pack]['sekunden']) if pack in PACKS else int(meta.get('sekunden'))
    except Exception:
        raise HTTPException(400, 'Metadata incomplete.')
    # v128/v135a: echter Zahlbetrag (amount_total = inkl. Rabatt; Fallback
    # Katalogpreis) - wandert jetzt IN die Kauf-Transaktion (_credit_purchase),
    # damit Kauf-Zeile und Beleg nie auseinanderfallen.
    try:
        _cents = int(sess.get('amount_total') if sess.get('amount_total') is not None
                     else PACKS.get(pack, {}).get('preis_cent', 0))
    except Exception:
        _cents = PACKS.get(pack, {}).get('preis_cent', 0)
    # Atomar + idempotent (siehe _credit_purchase). Doppelte/erneute Webhooks
    # fuer dieselbe Session koennen nicht doppelt gutschreiben; Retries ziehen
    # einen evtl. fehlenden purchases-Beleg nach.
    if not _credit_purchase(uid, sec, sess_id, pack=pack, cents=_cents):
        return {'ok': True, 'idempotent': True}
    # v137: Rechnungs-Link direkt in unsere Kauf-Mail (Stripe mailt die
    # Rechnung wegen der Finalisierungs-Nachfrist erst ~1h spaeter). Ist die
    # Rechnung noch Entwurf, gibt es noch keine URL - dann sagt die Mail
    # ehrlich 'arrives shortly'. Darf den Kauf nie reissen.
    inv_url = None
    try:
        inv_id = sess.get('invoice')
        if inv_id:
            # v142 ASYNC: noch ein blockierender Stripe-Call im Event-Loop.
            _inv = await _aio2.to_thread(st.Invoice.retrieve, inv_id)
            inv_url = (_inv.get('hosted_invoice_url') if isinstance(_inv, dict)
                       else getattr(_inv, 'hosted_invoice_url', None))
    except Exception as e:
        print(f'Invoice-URL nicht abrufbar: {e}')
    try:
        # v142 ASYNC: der Mailversand geht ueber HTTPS (Resend/SMTP) und hing
        # bisher im Event-Loop. Stripe wartet auf unsere 200 - jede Sekunde
        # hier ist eine Sekunde, in der die ganze Seite steht.
        await _aio2.to_thread(_send_purchase_mail, uid, sec, sess_id,
                              cents=_cents, pack=pack,
                              invoice_url=inv_url)       # v133/v137
    except Exception as e:                             # darf den Kauf nie reissen
        print(f'Kauf-Mail fehlgeschlagen: {e}')
    print(f"Kauf verbucht: user={uid} pack={pack} +{sec // 60} Min")
    return {'ok': True, 'gutgeschrieben_sek': sec}


@app.get('/api/stats')
def api_stats():
    """v80z: Echte Aggregat-Zahlen fuer Social Proof. Keine Fake-Counter."""
    con = _db()
    r = con.execute("SELECT COUNT(*) c, COALESCE(SUM(-delta_sec), 0) s "
                    "FROM ledger WHERE grund LIKE 'Render %'").fetchone()
    con.close()
    return {'renders': r['c'], 'minutes': int(r['s'] // 60)}


@app.get('/api/history')
def api_history(request: Request):
    """Kauf- und Verbrauchs-Historie fuer den eingeloggten User."""
    u = _require_user(request)
    con = _db()
    rows = con.execute(
        "SELECT delta_sec, grund, created_at FROM ledger "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
        (u['id'],)).fetchall()
    con.close()
    items = [{'delta_sec': r['delta_sec'], 'grund': r['grund'],
              'zeit': int(r['created_at'])} for r in rows]
    return {'balance_sec': u['balance_sec'], 'items': items}

# Fonts fuer die Font-Kacheln (Preview mit tatsaechlicher Schrift)
_fonts_dir = os.path.join(ROOT, 'fonts')
if os.path.isdir(_fonts_dir):
    app.mount('/fonts', StaticFiles(directory=_fonts_dir), name='fonts')
# v230q: Assets der Landing-Page (Demo-Video + Standbild). Eigener Mount,
# damit sie ohne Anmeldung und ohne Job-Logik ausgeliefert werden - sie
# gehoeren zur Seite, nicht zu einem Kunden.
_assets_dir = os.path.join(HERE, 'assets')
if os.path.isdir(_assets_dir):
    app.mount('/assets', StaticFiles(directory=_assets_dir), name='assets')
_mprev_dir = os.path.join(HERE, 'motion_previews')
if os.path.isdir(_mprev_dir):
    app.mount('/motion_previews', StaticFiles(directory=_mprev_dir),
              name='motion_previews')
JOBS = {}
# v130 Admin: Liveness-Zeitstempel der Hintergrund-Threads (Watchdog/Cleanup),
# damit das Admin-Panel echten Herzschlag statt Vermutung zeigt.
_HEARTBEAT = {}
# v98: Echte Priority-Queue - die Pakete bewerben 'Priority queue', jetzt
# stimmt es auch: Jobs zahlender Kunden (je ein Kauf im Ledger) laufen vor
# Free-Tier-Jobs. Innerhalb einer Stufe bleibt es strikt FIFO (Sequenz-Nr).
from queue import PriorityQueue
import itertools as _it
QUEUE = PriorityQueue()
_QSEQ = _it.count()
# v197: beides an EINER Stelle. Die Worker-Zahl stand vorher nur als
# os.environ-Ausdruck an der Thread-Schleife und ein zweites Mal im
# System-Endpunkt - zwei Wahrheiten fuer denselben Wert.
WORKERS = max(1, int(os.environ.get('DVE_WORKERS', '1')))
QUEUE_WARN = int(os.environ.get('DVE_QUEUE_WARN', '5'))


def q_put(jid, q=None):
    """Job einreihen: Prio 0 = Kunde hat gekauft, 1 = Free-Tier/Demo.
    q-Parameter nur fuer den Selftest (die echte QUEUE haben laufende
    Worker-Threads im Griff)."""
    uid = (JOBS.get(jid) or {}).get('user_id')
    prio = 1
    try:
        if uid and _has_purchased(uid):
            prio = 0
    except Exception:
        pass
    (q if q is not None else QUEUE).put((prio, next(_QSEQ), jid))


# v127-sec: Flooding-Schutz. Die Caption-Queue ist unbounded und wird von genau
# EINEM Worker geleert; ohne Deckel kann ein Konto (Pre-Mode + Re-Render sind
# gratis) sie mit hunderten Jobs fluten und alle anderen tagelang aushungern
# plus die Platte fuellen. Wir begrenzen die gleichzeitig wartenden/laufenden
# Caption-Jobs pro Konto - zielt nur auf Flooding, normale Nutzung (1-2 offen)
# bleibt unberuehrt.
CAPTION_INFLIGHT_CAP = int(os.environ.get('DVE_INFLIGHT_CAP', '3'))


def _inflight_count(uid):
    if not uid:
        return 0
    return sum(1 for j in list(JOBS.values())
               if j.get('user_id') == uid and j.get('kind') != 'motion'
               and j.get('status') in ('wartet', 'laeuft'))


def _vorbereitet_count(uid):
    """v230c-sec: fertig transkribierte, aber nie gerenderte Uploads.
    Genau die zaehlt _inflight_count NICHT - ein 'pre'-Upload steht danach auf
    'vorbereitet' und faellt heraus. Damit war der Deckel eine RATEN-Bremse und
    keine Summe: ein Gratis-Konto konnte in Schleife hochladen, jedes Mal eine
    kostenpflichtige Whisper-Transkription ausloesen und bis 300 MB je Upload
    fuer 7 Tage auf derselben Platte ablegen, auf der die Kundendatenbank
    liegt. Abgebucht wird beim Pre-Upload bewusst nichts (das ist der
    Geschwindigkeitsvorteil) - also braucht es hier eine SUMMEN-Grenze."""
    if not uid:
        return 0
    return sum(1 for j in list(JOBS.values())
               if j.get('user_id') == uid and j.get('kind') != 'motion'
               and j.get('status') == 'vorbereitet')


def _upload_rate_guard(request):
    """v230c-sec: Bremse pro IP auf den Upload-Wegen. Es gab hier gar keine -
    `_rate_limit_ok` deckte nur reg/login/goauth/support/admin ab. Der Deckel
    ist bewusst grosszuegig (60/h): ein Kunde, der zehn Videos hintereinander
    hochlaedt, ist normal; 600 sind es nicht."""
    if not _rate_limit_ok(_client_ip(request), window_sec=3600,
                          max_attempts=60, bucket='upload'):
        raise HTTPException(429, 'Too many uploads from this connection. '
                                 'Please try again later.')


def _enqueue_guard(uid):
    if uid and _inflight_count(uid) >= CAPTION_INFLIGHT_CAP:
        raise HTTPException(429, 'You already have several renders in the queue. '
                                 'Please wait for one to finish before starting more.')


MQUEUE = Queue()          # Fast-Lane nur fuer Motion-Clips
LOCK = threading.Lock()

# Presets als Startpunkt. Der Nutzer kann alles individuell nachjustieren.
LOOKS = {
    'tiktok':    {'name': 'TikTok', 'desc': 'Word by word, bold, loud.'},
    'viral':     {'name': 'Viral', 'desc': 'Big bold caps, karaoke accent.'},
    'creator':   {'name': 'Creator', 'desc': 'Talking-head & business.'},
    'editorial': {'name': 'Editorial', 'desc': 'Magazine serif, calm, high-end.'},
    'poster':    {'name': 'Poster', 'desc': 'Big condensed caps, hard statements.'},
    'retro':     {'name': 'Retro', 'desc': 'Warm rounded, playful, music & lifestyle.'},
    'elegant':   {'name': 'Elegant', 'desc': 'Dense captions, but classy, no jitter.'},
    'cinematic': {'name': 'Cinematic', 'desc': 'Few, big moments.'},
    'clean':     {'name': 'Clean', 'desc': 'Readable subtitles only.'},
}

# Font-Kacheln wie in der Desktop-App
FONTS = [
    {'id': 'kino',    'label': 'Kino',      'file': 'fonts/archivo.ttf',
     'script': 'fonts/playfair_i.ttf'},
    {'id': 'tiktok',  'label': 'TikTok',    'file': 'fonts/tiktok_bold.ttf'},
    {'id': 'montse',  'label': 'Creator',   'file': 'fonts/montserrat_xb.ttf'},
    {'id': 'inter',   'label': 'Cinematic', 'file': 'fonts/inter_black.ttf'},
    {'id': 'anton',   'label': 'Impact',    'file': 'fonts/anton.ttf'},
    {'id': 'archivo', 'label': 'Black',     'file': 'fonts/archivo.ttf'},
    {'id': 'bebas',   'label': 'Condensed', 'file': 'fonts/bebas.ttf'},
    {'id': 'poppins', 'label': 'Clean',     'file': 'fonts/poppins_b.ttf'},
    {'id': 'staat',   'label': 'Poster',    'file': 'fonts/staatliches.ttf'},
    {'id': 'alfa',    'label': 'Slab',      'file': 'fonts/alfaslab.ttf'},
    {'id': 'yeseva',  'label': 'Fashion',   'file': 'fonts/yeseva.ttf'},
    {'id': 'bangers', 'label': 'Comic',     'file': 'fonts/bangers.ttf'},
    {'id': 'right',   'label': 'Retro',     'file': 'fonts/righteous.ttf'},
    {'id': 'lobster', 'label': 'Script',    'file': 'fonts/lobster.ttf'},
    {'id': 'marker',  'label': 'Brush',     'file': 'fonts/marker.ttf'},
]

FX_LABELS = [
    ('behind',  'Behind you'),
    ('cascade', 'Letter build-up'),
    ('blurin',  'From the blur'),
    ('outline', 'Outline only'),
    ('ground',  'In the scene'),
]

ANIM_LABELS = {
    '': 'none', 'glitch': 'Glitch', 'puls': 'Pulse', 'welle': 'Wave',
    'zittern': 'Shake', 'neon': 'Neon', 'schub': 'Boost',
    'bruch': 'Shatter (breaks apart)', 'sturz': 'Drop (falls)',
    'anstieg': 'Rise (lifts up)', 'wende': 'Flip (turns over)',
    'druck': 'Pressure (crushed)', 'schwund': 'Fade (dissolves)',
    'knall': 'Bang (punchline)', 'gewicht': 'Weight (stroke thickens)',
    'schweben': 'Float (3D drift)', 'fokus': 'Focus (sharpens in)',
    'enthuellen': 'Reveal (wiped free)', 'spur': 'Trail (speed echo)',
    'kippen': 'Tilt (folds forward)',
    'explosion': 'Explosion (flies out + back)',
    'magnet': 'Magnet (pulls together)',
    'wackel': 'Wobble (cartoon bounce)',
    'regen': 'Rain (falls from above)',
    'zoom_punch': 'Zoom punch (hard push)',
    'rutsche': 'Slide (from the right)',
    'stempel': 'Stamp (slams down)',
}
# v193: erlaubte Animations-IDs fuer die serverseitige Pruefung des
# Blockplans. Aus derselben Quelle wie die UI-Labels, damit beide nie
# auseinanderlaufen.
ANIM_IDS = frozenset(k for k in ANIM_LABELS if k)


# ---------------------------------------------------------------- Zugangscodes
def load_codes():
    if os.path.exists(CODES_FILE):
        try:
            return json.load(open(CODES_FILE, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_codes(c):
    tmp = CODES_FILE + '.tmp'
    json.dump(c, open(tmp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    os.replace(tmp, CODES_FILE)


def check_code(code):
    codes = load_codes()
    c = codes.get((code or '').strip())
    if not c:
        return False, 'Zugangscode ungültig.'
    if not c.get('aktiv', True):
        return False, 'Dieser Zugangscode wurde deaktiviert.'
    if c.get('limit') and c.get('genutzt', 0) >= c['limit']:
        return False, (f"Kontingent aufgebraucht ({c['genutzt']}/{c['limit']} Videos). "
                       'Melde dich bei Ismet.')
    return True, ''


def check_auth(code, request):
    """v80h: Neuer Auth-Wrapper - akzeptiert entweder ein gueltiges Session-
    Cookie (User-Account) ODER einen Legacy-Code (Freundes-Kreis).
    Rueckgabe wie check_code: (ok: bool, msg: str)."""
    if request is not None:
        u = _current_user(request)
        if u:
            return True, ''
    # v230d-sec DIE BREMSE GEHOERT HIERHIN, NICHT AN EIN GATE.
    # v203-sec hat richtig erkannt, dass ein Alt-Code NAME-1234 nur 10.000
    # Moeglichkeiten hat und eine vollwertige zweite Identitaet ist - und die
    # Bremse an genau EINEN Endpunkt gehaengt (/api/pruefe-code). check_auth
    # hat sieben Aufrufer; ueber POST /api/templates liefen 4712 Rateversuche
    # ohne ein einziges 429 durch und der Treffer wurde mit 200 gemeldet.
    # Derselbe Fehlertyp wie v159/v170/v176: Riegel am falschen Gate.
    # Der Zaehler laeuft nur, wenn ueberhaupt ein Code geschickt wurde -
    # ein anonymer Aufruf ohne Code ist kein Rateversuch.
    if request is not None and (code or '').strip():
        if not _rate_limit_ok(_client_ip(request), window_sec=900,
                              max_attempts=10, bucket='code'):
            return False, ('Too many attempts. Please try again in a few '
                           'minutes.')
    return check_code(code)


def count_use(code):
    with LOCK:
        codes = load_codes()
        if code in codes:
            codes[code]['genutzt'] = codes[code].get('genutzt', 0) + 1
            codes[code]['zuletzt'] = time.strftime('%Y-%m-%d %H:%M')
            save_codes(codes)


# ---------------------------------------------------------------- Config-Merge
def deep_merge(base, override):
    """Rekursives Merge: override ueberschreibt base an Blaettern.
    Nur Dicts werden merged, alles andere ersetzt."""
    if not isinstance(override, dict):
        return override
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_OV_SECTIONS = {'effects', 'camera', 'colors', 'fonts', 'keywords', 'output',
                'matting_quality', 'matting_downsample', 'language'}

# v230c-sec JEDE ZAHL AUS DEM CLIENT BEKOMMT EINE GRENZE.
# Bis v230b klemmte _sanitize_overrides genau fuenf Regler; alles andere lief
# ungeprueft in die Render-Config. Zwei davon steuern direkt die Rechenzeit:
# `matting_downsample` (das KI-Netz rechnet das Bild GROESSER statt kleiner,
# gemessen Faktor 50-90 und bis 5 GB Speicher) und `effects.bg_blur` (der
# Gauss-Radius haengt linear daran, gemessen Faktor 48 bei 100). Ein einziges
# Gratis-Konto konnte damit den EINEN Render-Worker stundenlang belegen - der
# Wachhund greift nicht, weil der Fortschritt ja weiterlaeuft.
# Regel jetzt: was hier keine Grenze hat, kommt gar nicht erst durch.
_EFFECT_RANGE = {
    'words_per_group': (1, 8), 'words_per_group_max': (1, 10),
    'chunk_hold_min': (0.10, 5.0), 'caption_contrast': (1.0, 21.0),
    'caption_kontur': (0.0, 0.30), 'punch_silence': (0.0, 2.0),
    'zahl_gap': (0, 300), 'beat_sync': (0.0, 1.0), 'person_shadow': (0.0, 1.0),
    'dim_behind': (0.0, 1.0), 'dim_blurin': (0.0, 1.0), 'sfx_volume': (0.0, 2.0),
    'intro_seconds': (0, 300), 'hook_seconds': (0, 300),
    'hook_strength': (0.0, 1.0), 'retention_gap': (0, 300),
    'pattern_interrupt': (0, 300), 'bg_blur': (0.0, 1.0),
    'music_beat': (0.0, 1.0), 'freeze_frame': (0.0, 1.0), 'trail': (0.0, 1.0),
    'counter_ring': (0.0, 1.0), 'split_screen': (0.0, 1.0),
    'env_shadow': (0.0, 1.0), 'caption_scale': (0.60, 1.80),
    'caption_hierarchie': (1.40, 5.00), 'blender_samples': (1, 256),
    'blender_anim_frames': (1, 24), 'blender_width': (16, 1920),
    # v230f NACHGETRAGEN. caption_zone fehlte hier - und weil ein fehlender
    # Eintrag den Wert VERWARF, sassen die Captions bei jedem gespeicherten
    # Setup wieder in der Standard-Zone (Ismets Befund "die Captions
    # respektieren die Safe Zones nicht mehr"). Der Weg dorthin:
    # applyTemplate setzt State.cfg auf das gespeicherte Setup, laesst
    # State.cfgBase aber stehen - der Unterschied enthaelt dann ALLE
    # Preset-Werte, auch die, die der Kunde nie angefasst hat.
    'caption_zone': (0.05, 0.95), 'caption_scale_klein': (0.20, 3.00),
    'caption_weight': (1, 1000), 'reveal_letter_s': (0.0, 2.0),
    'matte_refine': (0.0, 3.0), 'refine': (0.0, 3.0),
    'caption_glow': (0.0, 4.0), 'caption_outline': (0.0, 4.0),
    'beat_grid': (0.0, 4.0), 'sfx_dichte_wert': (0.0, 10.0),
}
# Zahlen ohne eigenen Eintrag werden GEKLEMMT, nicht verworfen. Verwerfen war
# der Fehler von v230c: ein vergessener Schluessel verschwand lautlos und ein
# Feature war weg, ohne dass ein Test oder eine Meldung es zeigte. Die Grenze
# ist trotzdem eng genug, dass niemand daraus Rechenzeit macht - die teuren
# Regler (matting_downsample, bg_blur, blender_*) haben ihre eigene.
_ZAHL_ALLGEMEIN = (-1000.0, 1000.0)
_CAMERA_RANGE = {'strength': (0.0, 1.0), 'crash': (0.0, 1.0),
                 'side_every': (1, 60)}
_FX_IDS = {'behind', 'cascade', 'blurin', 'outline', 'ground'}
_CAM_IDS = {'caption', 'punch', 'pan', 'push', 'pullback', 'crash', 'capzoom',
            'drift', 'none'}


def _klemm_zahlen(d, tabelle, allgemein=_ZAHL_ALLGEMEIN):
    """Zahlenwerte gegen die Tabelle klemmen.

    v230f: Ein Wert OHNE Eintrag wird auf einen weiten allgemeinen Bereich
    GEKLEMMT, nicht mehr verworfen. Das Verwerfen (v230c) hat einen
    vergessenen Schluessel lautlos verschwinden lassen - `caption_zone` fiel
    damit aus jedem gespeicherten Setup heraus und die Captions sassen
    wieder in der Standard-Zone. Ein stiller Fallback, der ein Feature
    abschaltet, ist genau der Fehler, den v210 schon einmal gekostet hat.
    Die teuren Regler haben ihre eigene, enge Grenze in der Tabelle;
    `allgemein=None` erzwingt weiterhin einen Eintrag (fuer Sektionen, in
    denen es GAR keine freien Zahlen geben darf, z. B. colors).
    Wahrheitswerte bleiben, Texte werden nur in der Laenge gedeckelt."""
    for k in list(d):
        v = d[k]
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            r = tabelle.get(k) or allgemein
            if not r:
                d.pop(k, None)
                continue
            try:
                w = min(max(float(v), r[0]), r[1])
                d[k] = int(round(w)) if (isinstance(r[0], int)
                                         and isinstance(r[1], int)) else w
            except Exception:
                d.pop(k, None)
        elif isinstance(v, str) and len(v) > 64:
            d[k] = v[:64]


def _erlaubte_fonts():
    """Geschlossener Satz zulaessiger Schriftdateien: die Kacheln aus /api/fonts
    plus alles, was die eigenen Presets setzen. Alles andere ist ein freier
    Pfad in einen Dateinamen - und ein Pfad, der auf ein Kundenvideo zeigt,
    laesst den Render mit einem unbehandelten Fehler sterben (ein Gratis-Konto
    konnte so den Worker dauerhaft beschaeftigen)."""
    global _FONT_OK
    if _FONT_OK is None:
        ok = set()
        for f in FONTS:
            ok.add(f.get('file'))
            if f.get('script'):
                ok.add(f['script'])
        try:
            for name in ('creator', 'clean', 'editorial', 'viral'):
                for v in (build_config(name).get('fonts') or {}).values():
                    if isinstance(v, str):
                        ok.add(v)
        except Exception:
            pass
        _FONT_OK = {v for v in ok if isinstance(v, str)}
    return _FONT_OK


_FONT_OK = None

def _sanitize_overrides(ov):
    """v92 SECURITY: cfg_overrides kommt vom Client und wird tief in die
    Render-Config gemerged. Ohne Filter koennte ein Nutzer beliebige Keys
    setzen (4K-Aufloesung, ProRes-Master, riesige Blender-Werte) und so die
    Server-Last pro Render hochtreiben. Nur bekannte Sektionen zulassen und
    die teuren Regler hart deckeln."""
    if not isinstance(ov, dict):
        return {}
    out = {k: v for k, v in ov.items() if k in _OV_SECTIONS}
    # v96x: Sektionen muessen Dicts sein (ausser language) - 'keywords': null
    # o.ae. wuerde build_config crashen.
    for k in list(out):
        if k not in ('language', 'matting_quality', 'matting_downsample') \
                and not isinstance(out[k], dict):
            out.pop(k)
    # v96x QUALITAET: Die KI-Regie ist der Kern und NIE abschaltbar - kein
    # Override/Template darf keywords.ai/ai_model/ai_vision/ai_validate setzen.
    # (Alte gespeicherte Presets pinnten sonst z.B. still ein veraltetes
    # ai_model gegen den gpt-5-Default oder koennten die Regie ganz abschalten.)
    kwo = out.get('keywords')
    if isinstance(kwo, dict):
        _KW_OK = {'include', 'exclude', 'auto', 'emphasize_last',
                  'min_gap_seconds'}
        out['keywords'] = {k: v for k, v in kwo.items() if k in _KW_OK}
        # v230c-sec: die TYPEN muessen auch stimmen. `include: 123` kam bis
        # v230b durch und liess render.py NACH der Transkription mit einem
        # unbehandelten TypeError sterben - der Transkript-Zwischenspeicher
        # wird nur bei Erfolg geschrieben, also lief bei jedem Versuch ein
        # neuer, kostenpflichtiger Whisper-Aufruf. Ein Gratis-Konto konnte so
        # beliebig oft auf Rechnung des Betreibers transkribieren lassen.
        for _lk in ('include', 'exclude'):
            if _lk in out['keywords']:
                v = out['keywords'][_lk]
                if isinstance(v, str):
                    v = [v]
                if isinstance(v, list):
                    out['keywords'][_lk] = [str(x)[:60] for x in v[:200]
                                            if isinstance(x, (str, int, float))
                                            and not isinstance(x, bool)]
                else:
                    out['keywords'].pop(_lk, None)
        _klemm_zahlen(out['keywords'], {'min_gap_seconds': (0.0, 60.0)})
        if not out['keywords']:
            out.pop('keywords')
    # v92-sec: language fliesst bis in einen Dateinamen (Transkript-Cache).
    # Nur ein sauberer Sprachcode oder 'auto' darf durch - alles andere raus,
    # damit kein Pfad-Traversal moeglich ist.
    if 'language' in out:
        lv = str(out.get('language') or '').strip().lower()
        if not re.fullmatch(r'[a-z]{2,8}|auto', lv):
            out.pop('language', None)
        else:
            out['language'] = lv
    o = out.get('output')
    if isinstance(o, dict):
        if 'height' in o:
            try:
                # v230al: Deckel haengt am Schalter. Geklemmt wird, NICHT
                # verworfen - ein stiller Wegfall schaltet ein Feature ab,
                # ohne dass es jemand merkt (v230f-Lehre).
                _max_h = 2160 if _4k_erlaubt() else 1080
                o['height'] = min(max(int(o['height']), 480), _max_h)
            except Exception:
                o.pop('height', None)
        # v149: 4K nur als bekannte Stufe, nie als freie Zahl. Die Hoehe
        # rechnet die Engine selbst aus dem Quellformat aus.
        if 'quality' in o and str(o.get('quality')).lower() not in ('hd', '4k'):
            o.pop('quality', None)
        if not _4k_erlaubt() and str(o.get('quality', '')).lower() in ('4k', 'uhd'):
            o['quality'] = 'hd'        # v230al: geklemmt, nicht entfernt
        o.pop('master', None)          # ProRes-Master nie per Override (Riesen-Files)
        # v101d: Safe-Zone-Plattform - nur bekannte Masken zulassen.
        if 'platform' in o and str(o.get('platform')).lower() not in \
                ('generic', 'tiktok', 'reels', 'shorts'):
            o.pop('platform', None)
        # v230c-sec: crf/preset/speed steuern die Encode-Zeit und die
        # Dateigroesse. crf 0 plus preset 'placebo' ist ein Vielfaches an
        # Rechenzeit und Bytes - beides auf Kosten des Betreibers.
        if 'crf' in o:
            try:
                o['crf'] = int(min(max(int(o['crf']), 14), 34))
            except Exception:
                o.pop('crf', None)
        if 'preset' in o and str(o.get('preset')).lower() not in \
                ('ultrafast', 'veryfast', 'faster', 'fast', 'medium', 'slow'):
            o.pop('preset', None)
        if 'speed' in o and str(o.get('speed')).lower() not in \
                ('schnell', 'standard', 'fein'):
            o.pop('speed', None)
        _klemm_zahlen(o, {'height': (480, 2160 if _4k_erlaubt() else 1080),
                          'crf': (14, 34)},
                      allgemein=(0.0, 10000.0))
    e = out.get('effects')
    if isinstance(e, dict):
        # v153: Caption-Regler aus der UI. Groessen hart deckeln - ein Client
        # koennte sonst eine Schrift anfordern, die das Bild sprengt und den
        # Render unnoetig teuer macht.
        for k, lo, hi in (('caption_scale', 0.60, 1.80),
                          ('caption_hierarchie', 1.40, 5.00)):
            if k in e:
                try:
                    e[k] = round(min(max(float(e[k]), lo), hi), 3)
                except Exception:
                    e.pop(k, None)
        if 'caption_layout' in e and str(e.get('caption_layout')).lower() \
                not in ('auto', 'rows', 'collage'):
            e.pop('caption_layout', None)
        for _ck in ('caption_align', 'caption_seite'):
            if _ck in e and str(e.get(_ck)).lower() \
                    not in ('auto', 'links', 'rechts', 'mitte'):
                e.pop(_ck, None)
        # v230 Sound-Dichte: geschlossener Satz, alles andere fliegt raus.
        # Ein unbekannter Wert faellt in der Engine still auf 'normal' zurueck -
        # aber ein Wert, den niemand geprueft hat, gehoert gar nicht erst
        # durch (dieselbe Regel wie bei der Caption-Dichte, v186).
        if 'sfx_dichte' in e and str(e.get('sfx_dichte')).lower() \
                not in ('sparsam', 'normal', 'dicht'):
            e.pop('sfx_dichte', None)
        # v230c-sec: ab hier gilt die Tabelle fuer ALLE Zahlen (auch
        # blender_*, bg_blur, freeze_frame, trail, person_shadow ...).
        for _lk in ('keyword_rotation',):
            if _lk in e:
                if isinstance(e[_lk], list):
                    e[_lk] = [x for x in e[_lk][:12]
                              if isinstance(x, str) and x in _FX_IDS]
                    if not e[_lk]:
                        e.pop(_lk, None)
                else:
                    e.pop(_lk, None)
        _klemm_zahlen(e, _EFFECT_RANGE)
    c = out.get('camera')
    if isinstance(c, dict):
        for _lk in ('keyword_rotation', 'side_rotation'):
            if _lk in c:
                if isinstance(c[_lk], list):
                    c[_lk] = [x for x in c[_lk][:12]
                              if isinstance(x, str) and x in _CAM_IDS]
                    if not c[_lk]:
                        c.pop(_lk, None)
                else:
                    c.pop(_lk, None)
        _klemm_zahlen(c, _CAMERA_RANGE)
    col = out.get('colors')
    if isinstance(col, dict):
        if 'style' in col and str(col.get('style')).lower() \
                not in ('auto', 'schwarz', 'weiss'):
            col.pop('style', None)
        for _ck in ('text', 'accent'):
            if _ck in col:
                v = col[_ck]
                if (isinstance(v, list) and len(v) == 3
                        and all(isinstance(x, (int, float))
                                and not isinstance(x, bool) for x in v)):
                    col[_ck] = [int(min(max(x, 0), 255)) for x in v]
                else:
                    col.pop(_ck, None)
        # colors kennt nur style/text/accent/adaptive - eine freie Zahl
        # gibt es hier nicht, also darf sie auch nicht durch.
        _klemm_zahlen(col, {}, allgemein=None)
    # Schriften: nur aus dem geschlossenen Satz (siehe _erlaubte_fonts).
    fo = out.get('fonts')
    if isinstance(fo, dict):
        _ok = _erlaubte_fonts()
        out['fonts'] = {k: v for k, v in fo.items()
                        if k in ('display', 'italic', 'support', 'script',
                                 'strong') and isinstance(v, str) and v in _ok}
        if not out['fonts']:
            out.pop('fonts', None)
    # Der teuerste Regler der ganzen Pipeline: er skaliert das Bild, das ins
    # KI-Netz geht. Ueber 0.8 rechnet das Netz GROESSER als das Original.
    if 'matting_downsample' in out:
        _md = out['matting_downsample']
        if isinstance(_md, str) and _md.strip().lower() == 'auto':
            out['matting_downsample'] = 'auto'
        else:
            try:
                out['matting_downsample'] = min(max(float(_md), 0.125), 0.8)
            except Exception:
                out.pop('matting_downsample', None)
    if 'matting_quality' in out and str(out['matting_quality']).lower() \
            not in ('standard', 'hoch', 'maximum'):
        out.pop('matting_quality', None)
    return out


def build_config(look, overrides=None):
    """Config-Kaskade: config.yaml -> Preset -> User-Overrides.
    Serverseitige Zwaenge werden am Ende hart ueberschrieben (Blender aus).

    Presets sind Stand 2026 - jeder ist eine vollstaendige High-End-Konfig
    quer durch alle Effekte, Kamera, Farben und Schrift. Nutzer kann alles
    einzeln nachtunen; die Defaults sind aber schon deploybar."""
    cfg = yaml.safe_load(open(os.path.join(ROOT, 'config.yaml'), encoding='utf-8'))
    # v150: der gewaehlte Look muss in der Config stehen. Die Engine
    # entscheidet daran, ob sie die Collage-Anordnung einstreuen darf -
    # 'clean' bleibt bewusst schlicht.
    cfg['look'] = str(look or 'creator')

    # --- 2026er High-End-Presets (voll ausgereizt, produktionsreif)
    PRESETS = {
        'viral': {
            'effects': {
                # v183: Der Markt-Standard 2026 (Submagic/Hormozi-Schule).
                # ALLE Woerter versal + extrabold auf ~0.07-0.115 H, enge
                # 2-4-Wort-Bloecke unten mittig, die Akzentfarbe wandert mit
                # dem gesprochenen Wort (Karaoke). Kern-Schalter ist
                # caption_viral - er steuert Groesse, Versalsatz und die
                # Karaoke-Faerbung in der Engine. Default fuer 9:16-Uploads.
                'density': 'durchgehend', 'text_style': '3d',
                'hook_seconds': 10, 'hook_strength': 0.70, 'instant_hook': True,
                'pattern_interrupt': 7, 'retention_gap': 9,
                'words_per_group': 2, 'words_per_group_max': 4,
                'chunk_hold_min': 0.55,
                'dim_behind': 0.40, 'dim_blurin': 0.32,
                'beat_sync': 0.85, 'music_beat': 0.70, 'person_shadow': 0.55,
                'zahl_gap': 10,
                'bg_blur': 0.50, 'freeze_frame': 0.40, 'trail': 0.0,
                'counter_ring': 0.45, 'split_screen': 0.0, 'env_shadow': 0.20,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['behind', 'outline', 'ground'],
                'sfx_volume': 0.55, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
                'caption_viral': True,
                'caption_aktivwort': True,
                'caption_collage': False,
                'caption_satz_collage': False,
                'caption_layout': 'rows',
                'caption_seite': 'mitte',
                # v199: auch hier aus. Im Viral-Template ist der Saum
                # eigentlich konstitutiv (gelbes Karaoke-Wort auf hellem
                # Material), aber Ismets Ansage galt den Schriften, nicht
                # einem Look. Eine Zahl zurueck, wenn das Template darunter
                # leidet.
                'caption_kontur': 0,
                'caption_flow': True,
                # Markt-Zone: mittig-unten (0.58 H). Die Haus-Zone 0.25 H
                # ("ueber dem Kopf") liest sich im Viral-Kontext wie ein
                # Titel, nicht wie Sprechtext. spot() weicht weiter aus.
                'caption_zone': 0.58,
            },
            'camera': {
                'strength': 0.80, 'crash': 0.80, 'whip': False, 'side_every': 3,
                'keyword_rotation': ['punch', 'push', 'caption'],
                'side_rotation': ['capzoom', 'drift'],
            },
            # v185: KEIN fester Gelb-Akzent mehr (Ismets Urteil am Ergebnis:
            # "ausgelutscht"). Gelb auf dem gesprochenen Wort ist der Marker
            # jedes CapCut/Opus-Templates. Die Emphase traegt jetzt Groesse
            # und Deckkraft; die Farbwelt kommt wieder aus der Szene, damit
            # der Look zum Material gehoert statt zur Vorlage.
            'colors': {'style': 'auto', 'adaptive': True,
                       'text': [255, 255, 255]},
            'fonts': {
                'display': 'fonts/montserrat_xb.ttf',
                'italic': 'fonts/montserrat_xb.ttf',
                'script': 'fonts/montserrat_xb.ttf',
                'support': 'fonts/montserrat_xb.ttf',    # eine Familie, v143
            },
            'output': {'platform': 'tiktok'},
            'matting_quality': 'hoch',
        },
        'tiktok': {
            'effects': {
                # Wortweise, dicht, energisch - Reels/Shorts-Kern-Modus 2026
                # v187: 'wortweise' kannte die Engine nicht und fiel in den
                # sparsamen Pfad - der Look zeigte die Haelfte der Woerter.
                'density': 'durchgehend', 'text_style': '3d kinetisch',
                'hook_seconds': 8, 'hook_strength': 0.85, 'instant_hook': True,
                'pattern_interrupt': 6, 'retention_gap': 8,
                'words_per_group': 2, 'words_per_group_max': 4,
                'chunk_hold_min': 0.55,
                'dim_behind': 0.42, 'dim_blurin': 0.34,
                'beat_sync': 0.90, 'music_beat': 0.85, 'person_shadow': 0.60,
                'zahl_gap': 10,
                'bg_blur': 0.60, 'freeze_frame': 0.50, 'trail': 0.22,
                'counter_ring': 0.55, 'split_screen': 0.30, 'env_shadow': 0.15,
                'emerge': 'immer', 'anim': True,
                'keyword_rotation': ['behind', 'outline', 'ground'],
                'sfx_volume': 0.65, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.90, 'crash': 1.00, 'whip': True, 'side_every': 2,
                'keyword_rotation': ['punch', 'push', 'caption'],
                'side_rotation': ['capzoom', 'drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/tiktok_bold.ttf',
                'italic': 'fonts/tiktok_bold.ttf',
                'script': 'fonts/tiktok_bold.ttf',
                'support': 'fonts/tiktok_bold.ttf',      # v143: 0.219, eine Familie
            },
            'output': {'platform': 'tiktok'},   # v101d: engere TikTok-UI-Maske
            'matting_quality': 'hoch',
        },
        'creator': {
            'effects': {
                # Talking-Head + Business - klar, ruhig-dynamisch, professionell
                'density': 'akzente', 'text_style': '3d',
                'hook_seconds': 15, 'hook_strength': 0.55, 'instant_hook': True,
                'pattern_interrupt': 9, 'retention_gap': 12,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.75,
                'dim_behind': 0.38, 'dim_blurin': 0.30,
                'beat_sync': 0.75, 'music_beat': 0.45, 'person_shadow': 0.55,
                'zahl_gap': 15,
                'bg_blur': 0.55, 'freeze_frame': 0.30, 'trail': 0.0,
                'counter_ring': 0.40, 'split_screen': 0.0, 'env_shadow': 0.45,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['behind', 'cascade', 'blurin', 'outline'],
                'sfx_volume': 0.50, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.70, 'crash': 0.55, 'whip': False, 'side_every': 3,
                'keyword_rotation': ['caption', 'punch', 'pan', 'push'],
                'side_rotation': ['capzoom', 'drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/montserrat_xb.ttf',
                'italic': 'fonts/montserrat_xb.ttf',
                'script': 'fonts/playfair_i.ttf',
                'support': 'fonts/poppins_b.ttf',        # v143: 0.243, sachlich
            },
            'matting_quality': 'hoch',
        },
        'elegant': {
            'effects': {
                # NEU: Der "Elegant"-Preset - dichte Captions, aber gepflegt.
                # Fuer Kunden die viele Text-Momente wollen (Business/Talking-Head
                # mit hoher Info-Dichte) OHNE dass es kindisch/zappelig wird.
                # Keine glitzernden Extras, ruhige Kamera, klassische Serifen-
                # Anmutung, sanfte Animationen, viel Bokeh + Kontaktschatten.
                'density': 'akzente', 'text_style': '3d',
                'hook_seconds': 15, 'hook_strength': 0.5, 'instant_hook': True,
                'pattern_interrupt': 12, 'retention_gap': 10,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.85,               # gemaechlicher Puls
                'dim_behind': 0.34, 'dim_blurin': 0.28,
                'beat_sync': 0.55, 'music_beat': 0.30, 'person_shadow': 0.60,
                'zahl_gap': 15,
                'bg_blur': 0.65, 'freeze_frame': 0.60, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.0, 'env_shadow': 0.55,
                'emerge': 'auto', 'anim': True,
                # Nur die ruhigen, edlen Effekte in Rotation
                'keyword_rotation': ['behind', 'blurin', 'outline', 'cascade'],
                'sfx_volume': 0.40, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.55, 'crash': 0.35, 'whip': False, 'side_every': 4,
                'keyword_rotation': ['caption', 'push', 'pan'],
                'side_rotation': ['drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/inter_black.ttf',
                'italic': 'fonts/playfair_i.ttf',
                'script': 'fonts/playfair_i.ttf',
                'support': 'fonts/inter_black.ttf',      # v143: 0.280, eine Familie
            },
            'matting_quality': 'hoch',
        },
        'cinematic': {
            'effects': {
                # Wenige, grosse Momente. Kino-Bokeh, Freeze-Signature.
                'density': 'sparsam', 'text_style': 'klassisch',
                'hook_seconds': 30, 'hook_strength': 0.35, 'instant_hook': False,
                'pattern_interrupt': 14, 'retention_gap': 18,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.95,
                'dim_behind': 0.34, 'dim_blurin': 0.28,
                'beat_sync': 0.55, 'music_beat': 0.30, 'person_shadow': 0.65,
                'zahl_gap': 20,
                'bg_blur': 0.70, 'freeze_frame': 1.00, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.20, 'env_shadow': 0.65,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['blurin', 'ground', 'outline'],
                'sfx_volume': 0.38, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.55, 'crash': 0.40, 'whip': False, 'side_every': 4,
                'keyword_rotation': ['pan', 'pullback', 'caption'],
                'side_rotation': ['drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/inter_black.ttf',
                'italic': 'fonts/serif_i.ttf',
                'script': 'fonts/playfair_i.ttf',
                'support': 'fonts/montserrat_xb.ttf',    # v143: 0.286, breiter Fuss
            },
            'matting_quality': 'maximum',
        },
        'clean': {
            'effects': {
                # Nur lesbare Untertitel, keinerlei Deko. Minimalismus 2026.
                'density': 'sparsam', 'text_style': 'klassisch',
                'hook_seconds': 0, 'hook_strength': 0.0, 'instant_hook': False,
                'pattern_interrupt': 0, 'retention_gap': 0,
                'words_per_group': 3, 'words_per_group_max': 4,
                'chunk_hold_min': 0.80,
                'dim_behind': 0.0, 'dim_blurin': 0.0,
                'beat_sync': 0.0, 'music_beat': 0.0, 'person_shadow': 0.0,
                'zahl_gap': 0,
                'bg_blur': 0.0, 'freeze_frame': 0.0, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.0, 'env_shadow': 0.0,
                'emerge': 'aus', 'anim': False,
                'keyword_rotation': ['outline'],
                'sfx_volume': 0.0, 'sfx': False,
                'reflection': False, 'occlusion': False, 'track3d': False,
                'safe_zone': True,
                # v97c: 'Clean' bleibt schlichte lesbare Untertitel - kein
                # Flow-Aufbau, keine Keyword-Hervorhebung/Gold-Akzent.
                'caption_flow': False,
            },
            'camera': {
                'strength': 0.0, 'crash': 0.0, 'whip': False, 'side_every': 10,
                'keyword_rotation': [], 'side_rotation': [],
            },
            'colors': {'style': 'schwarz', 'adaptive': False},
            'fonts': {
                'display': 'fonts/poppins_b.ttf',
                'italic': 'fonts/poppins_b.ttf',
                'script': 'fonts/poppins_b.ttf',
            },
            'matting_quality': 'standard',
        },
        'editorial': {
            'effects': {
                # NEU v87: Magazin / "New Editorial". Hochkontrast-Serifen, viel
                # Ruhe, EIN Akzent, klassische Bewegung - der 2026er A24/Vox-Ton.
                # Fuer alle, die hochwertig-redaktionell statt laut wollen.
                'density': 'akzente', 'text_style': 'klassisch',
                'hook_seconds': 20, 'hook_strength': 0.40, 'instant_hook': True,
                'pattern_interrupt': 13, 'retention_gap': 14,
                'words_per_group': 3, 'words_per_group_max': 5,
                'chunk_hold_min': 0.90,
                'dim_behind': 0.30, 'dim_blurin': 0.24,
                'beat_sync': 0.45, 'music_beat': 0.25, 'person_shadow': 0.55,
                'zahl_gap': 18,
                'bg_blur': 0.60, 'freeze_frame': 0.50, 'trail': 0.0,
                'counter_ring': 0.0, 'split_screen': 0.0, 'env_shadow': 0.50,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['blurin', 'outline', 'behind'],
                'sfx_volume': 0.35, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.50, 'crash': 0.30, 'whip': False, 'side_every': 4,
                'keyword_rotation': ['caption', 'pan', 'push'],
                'side_rotation': ['drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/yeseva.ttf',
                'italic': 'fonts/playfair_i.ttf',
                'script': 'fonts/playfair_i.ttf',
                'support': 'fonts/serif.ttf',            # v143: 0.228, Magazin
            },
            'matting_quality': 'hoch',
        },
        'poster': {
            'effects': {
                # NEU v87: Plakat / Impact. Grosse kondensierte Versalien, harte
                # Statements, hoher Kontrast - laut, aber KEIN Wort-Maschinengewehr
                # (die Chunks bleiben lesbar stehen). Ground/Outline dominieren.
                'density': 'akzente', 'text_style': '3d',
                'hook_seconds': 10, 'hook_strength': 0.75, 'instant_hook': True,
                'pattern_interrupt': 7, 'retention_gap': 9,
                'words_per_group': 2, 'words_per_group_max': 4,
                'chunk_hold_min': 0.60,
                'dim_behind': 0.44, 'dim_blurin': 0.36,
                'beat_sync': 0.80, 'music_beat': 0.60, 'person_shadow': 0.62,
                'zahl_gap': 12,
                'bg_blur': 0.55, 'freeze_frame': 0.50, 'trail': 0.0,
                'counter_ring': 0.50, 'split_screen': 0.25, 'env_shadow': 0.20,
                'emerge': 'immer', 'anim': True,
                'keyword_rotation': ['ground', 'outline', 'cascade'],
                'sfx_volume': 0.60, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.85, 'crash': 0.90, 'whip': True, 'side_every': 2,
                'keyword_rotation': ['punch', 'push', 'caption'],
                'side_rotation': ['capzoom', 'drift'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/staatliches.ttf',
                'italic': 'fonts/staatliches.ttf',
                'script': 'fonts/staatliches.ttf',
                'support': 'fonts/archivo.ttf',          # v143: 0.321, Plakat
            },
            'matting_quality': 'hoch',
        },
        'retro': {
            'effects': {
                # NEU v87: Warmer Retro/Vaporwave-Ton. Runde Schrift, verspielt
                # aber gepflegt, Trails + Reflexionen, mittlere Dichte. Fuer
                # Musik/Lifestyle/Nightlife-Content.
                'density': 'akzente', 'text_style': '3d',
                'hook_seconds': 12, 'hook_strength': 0.60, 'instant_hook': True,
                'pattern_interrupt': 10, 'retention_gap': 11,
                'words_per_group': 2, 'words_per_group_max': 4,
                'chunk_hold_min': 0.70,
                'dim_behind': 0.40, 'dim_blurin': 0.32,
                'beat_sync': 0.70, 'music_beat': 0.55, 'person_shadow': 0.50,
                'zahl_gap': 14,
                'bg_blur': 0.50, 'freeze_frame': 0.40, 'trail': 0.0,
                'counter_ring': 0.45, 'split_screen': 0.30, 'env_shadow': 0.30,
                'emerge': 'auto', 'anim': True,
                'keyword_rotation': ['cascade', 'behind', 'ground'],
                'sfx_volume': 0.55, 'sfx': True,
                'reflection': True, 'occlusion': True, 'track3d': True,
                'safe_zone': True,
            },
            'camera': {
                'strength': 0.75, 'crash': 0.50, 'whip': True, 'side_every': 3,
                'keyword_rotation': ['push', 'caption', 'pan'],
                'side_rotation': ['capzoom'],
            },
            'colors': {'style': 'auto', 'adaptive': True},
            'fonts': {
                'display': 'fonts/righteous.ttf',
                'italic': 'fonts/righteous.ttf',
                'script': 'fonts/lobster.ttf',
                'support': 'fonts/righteous.ttf',        # v143: 0.202, eine Familie
            },
            'matting_quality': 'hoch',
        },
    }
    preset = PRESETS.get(look, PRESETS['creator'])
    cfg = deep_merge(cfg, preset)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    # Serverseitige Zwaenge - unabhaengig vom User-Wunsch
    cfg['effects']['blender_water'] = False
    # v80f: Neue Features als sichtbare Defaults verankern
    cfg['effects'].setdefault('chapters', True)
    cfg['effects'].setdefault('emoji', True)
    cfg.setdefault('output', {}).setdefault('orientation', 'auto')
    cfg.setdefault('keywords', {}).setdefault('vision_min_power', 2)
    cfg['keywords'].setdefault('ai_validate', True)
    return cfg


# ---------------------------------------------------------------- Render-Worker
def _parse_refs_line(ln):
    """v141: liest die Beweis-Zeile des Renders
    'Stil-Referenzen: N aktiv (eigene|Haus-Stil) - ...' und gibt (anzahl,
    quelle) zurueck. Quelle ist '' bei alten Logs ohne Klammer - die UI zeigt
    dann bewusst NICHT 'learned', weil die Herkunft unbekannt ist."""
    # v148: die Engine schreibt englisch ('N active (own|house style)').
    # Die deutschen Muster bleiben stehen, damit Job-Logs von vor dem Deploy
    # weiter gelesen werden - sonst zeigte die Library dort ploetzlich nichts.
    m = re.search(r'(\d+)\s+(?:active|aktiv)', ln or '')
    n = int(m.group(1)) if m else 0
    if '(own)' in ln or '(eigene)' in ln:
        q = 'eigene'
    elif 'house style' in ln or 'Haus-Stil' in ln:
        q = 'haus'
    else:
        q = ''
    return n, q


def job_dir(jid):
    # Sicherheit: jid kommt teils aus der URL - hart auf Hex sanitisieren,
    # damit '../'-Traversal unmoeglich ist (uuid4.hex-Jobs bleiben identisch).
    jid = re.sub(r'[^0-9a-fA-F]', '', str(jid or ''))[:32] or '_'
    return os.path.join(JOBS_DIR, jid)


def set_state(jid, **kw):
    j = JOBS.setdefault(jid, {})
    # v130: Render-Latenz messbar machen. started_at beim Uebergang auf 'laeuft',
    # finished_at beim ersten terminalen Status - lokale Zeitvariablen waren
    # vorher nicht persistiert, Durchsatz-/Latenz-Statistik war unmoeglich.
    _st = kw.get('status')
    if _st == 'laeuft' and not j.get('started_at'):
        kw.setdefault('started_at', time.time())
    if _st in ('fertig', 'fehler', 'analysiert') and j.get('started_at') \
            and not j.get('finished_at'):
        kw['finished_at'] = time.time()
    j.update(kw)
    try:
        # v98: atomar via tmp + os.replace - ein Crash mitten im Schreiben
        # hinterliess sonst eine halbe state.json und der (bezahlte) Job war
        # nach dem Neustart nicht mehr restaurierbar.
        sp = os.path.join(job_dir(jid), 'state.json')
        tmp = sp + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in j.items()
                       if k not in ('input', 'code')}, f, ensure_ascii=False)
        os.replace(tmp, sp)
    except Exception:
        pass


def _run_render(jid, extra_args=None, out_name='fertig.mp4', progress_start=0.05):
    """Ruft render.py als Subprocess und streamt Log + Fortschritt in state."""
    j = JOBS[jid]
    d = job_dir(jid)
    src = j['input']
    out = os.path.join(d, out_name)
    cfg = build_config(j.get('look', 'creator'), j.get('cfg_overrides'))
    cfg_path = os.path.join(d, 'config.yaml')
    yaml.safe_dump(cfg, open(cfg_path, 'w', encoding='utf-8'), allow_unicode=True)

    cmd = [sys.executable, os.path.join(ROOT, 'render.py'), src,
           '--config', cfg_path, '--out', out] + (extra_args or [])
    # v204-sec: Bis v203 war das eine VOLLKOPIE der Umgebung - der
    # Render-Subprozess kannte damit den Stripe-LIVE-Schluessel, den
    # Admin-Key, das SMTP-Passwort und die Google-Geheimnisse. Er braucht
    # davon genau eins. Ein Fehler in einer Video-Bibliothek haette so
    # nebenbei die Kasse offengelegt. Jetzt eine Allowlist: was nicht
    # ausdruecklich hier steht, sieht der Renderer nicht.
    _ERLAUBT = (
        'PATH', 'HOME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'PWD', 'SHELL',
        'PYTHONPATH', 'PYTHONUNBUFFERED', 'PYTHONHASHSEED',
        'OPENAI_API_KEY',                 # das EINE echte Geheimnis
        'DVE_DATA', 'DVE_CHROMIUM', 'DVE_REFS_FILE', 'DVE_LOGFILE',
        'DVE_MAX_SECONDS', 'DVE_MAX_MB', 'DVE_WORKERS',
        'LD_LIBRARY_PATH', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR',
        'MPLBACKEND', 'OPENCV_LOG_LEVEL', 'GLOG_minloglevel',
        'CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS', 'NUMEXPR_MAX_THREADS',
    )
    env = {k: v for k, v in os.environ.items()
           if k in _ERLAUBT or k.startswith('DVE_RENDER_')}
    # v126 Kunden-Stil: hat das Konto eigene Stil-Referenzen, bekommt der Render-
    # Subprozess deren Datei (DVE_REFS_FILE) - Prompt-Block und Mess-Parameter
    # kommen dann aus dem PERSOENLICHEN Geschmack statt aus dem Haus-Stil.
    # v141 FIX (Ismets Befund): Frueher wurde DVE_REFS_FILE NUR gesetzt, wenn
    # das Konto eigene Referenzen hat. Ohne eigene fiel render.py auf
    # DATA/regie_reference.json zurueck - und GENAU dorthin schreibt der
    # Owner-Endpoint /api/reference/learn. Ergebnis: was der Owner auf seinem
    # Konto lernte, steuerte JEDEN fremden Kundenschnitt (und die UI nannte es
    # faelschlich "learned references" des Kunden). Jetzt ist die Quelle IMMER
    # explizit gesetzt, es gibt keinen impliziten Fallback mehr:
    #   eigene Referenzen        -> persoenliche Datei      (Quelle 'eigene')
    #   Owner mit Haus-Referenzen-> globale Owner-Datei      (Quelle 'eigene')
    #   sonst                    -> mitgelieferte Repo-Defaults (Quelle 'haus')
    # Die globale Owner-Datei erreicht ein fremdes Konto nie mehr.
    _urp, _rsrc = _refs_for_job(j.get('user_id'))
    env['DVE_REFS_FILE'] = _urp
    env['DVE_REFS_SOURCE'] = _rsrc
    # v171: Herkunfts-Stempel in die Datei (Build + Job-ID in den
    # MP4-Metadaten). Vier byte-identische "neue" Renders in Folge, und
    # weder Ismet noch der Support konnten sehen, welcher Job eine Datei
    # erzeugt hat.
    env['DVE_JOB_TAG'] = f'DouchkoVE {DVE_BUILD} job {jid}'

    # v88b: Transkript aus dem Cache holen, falls dasselbe Video (gleicher
    # Nutzer, gleiche Sprache) schon einmal transkribiert wurde. render.py
    # nutzt eine daneben liegende quelle_transcript2.json automatisch und
    # ueberspringt damit den Whisper-Aufruf komplett.
    _tp = _job_transcript_path(src)
    _cache = _tcache_path(j.get('user_id'), j.get('vhash'),
                          cfg.get('language', 'auto'))
    if _cache and os.path.exists(_cache) and not os.path.exists(_tp):
        try:
            shutil.copyfile(_cache, _tp)
            print(f'Transkript-Cache-Treffer fuer Job {jid}')
        except Exception:
            pass

    set_state(jid, status='laeuft', phase='Warming up the engines …',
              progress=progress_start, log_tail=[], eta_sec=None)
    p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    j['pid'] = p.pid                  # v98: Watchdog kann haengende Renders killen
    log = []
    t0_render = time.time()
    frame_start_t = None
    for line in p.stdout:
        log.append(line.rstrip())
        ln = line.strip()
        # letzte 8 nicht-leeren Zeilen als log_tail
        tail = [x for x in log[-40:] if x.strip()][-8:]

        # v96y: Referenz-Beweis in den Job-State - der User sieht am fertigen
        # Job, ob (und wie viele) Stil-Referenzen den Schnitt gesteuert haben.
        # v148: die Engine schreibt englisch. Die alten deutschen Marker
        # bleiben als Fallback stehen - im Cache und in job-Logs von vor dem
        # Deploy stehen sie noch, und eine Fortschrittsanzeige, die dort
        # stumm bleibt, waere eine Verschlechterung.
        if ln.startswith('Style references:') or ln.startswith('Stil-Referenzen:'):
            try:
                _n, _q = _parse_refs_line(ln)
                set_state(jid, stil_refs=_n, stil_quelle=_q)
            except Exception:
                pass
        elif ln.startswith('Style anchor:') or ln.startswith('Stil-Anker:'):
            set_state(jid, stil_anker=ln.split(':', 1)[1].strip())

        phase = None
        progress = None
        eta = None
        if 'Transcribing' in ln or 'Transkribiere' in ln:
            phase = 'Listening to every word you said …'
            progress = 0.05
        elif ('words' in ln and 'transcript' in ln) \
                or ('Woerter' in ln and 'Transkript' in ln):
            phase = 'Pinning each word to the exact millisecond …'
            progress = 0.10
        elif 'Face tracking' in ln or 'Gesichts-Tracking' in ln:
            phase = 'Finding you in the frame and splitting the scenes …'
            progress = 0.20
        elif 'Music beat' in ln or 'Musik-Beat' in ln:
            phase = 'Feeling out the rhythm of your music …'
            progress = 0.28
        elif ('AI director' in ln and 'analysing' in ln) \
                or ('KI-Regie' in ln and 'analysiert' in ln):
            phase = 'Our AI director is reading your script …'
            progress = 0.35
        elif 'Vision director' in ln or 'Vision-Regie' in ln:
            phase = 'Taking a closer look at your footage, frame by frame …'
            progress = 0.38
        elif ln.startswith('Keywords'):
            phase = 'The big moments are locked in …'
            progress = 0.40
        elif 'Adaptive colours' in ln or 'Adaptive Farben' in ln:
            phase = 'Picking caption colors straight from your scene …'
            progress = 0.43
        elif 'Compositions:' in ln or 'Kompositionen' in ln:
            phase = 'Laying your words out like a magazine spread …'
            progress = 0.45
        elif 'Matting window' in ln or 'Matting-Fenster' in ln:
            phase = 'Cutting you cleanly out from the background …'
            progress = 0.47
        elif 'Depth occlusion' in ln or 'Tiefen-Okklusion' in ln:
            phase = 'Working out what sits in front of you …'
            progress = 0.49
        elif 'Camera track' in ln or 'Kamera-Track' in ln:
            phase = 'Locking the text onto the moving scene …'
            progress = 0.50
        elif 'Frame' in ln and '/' in ln:
            try:
                cur_s, tot_s = ln.split('Frame')[1].split('|')[0].strip().split('/')
                cur, tot = int(cur_s), int(tot_s)
                frac = 0.52 + 0.43 * (cur / max(tot, 1))
                progress = round(min(frac, 0.95), 3)
                # Live-Story: was jetzt gerade auf dem Frame passiert
                sec_at = cur / 25.0
                if frac < 0.62:
                    phase = f'Painting your video · second {sec_at:.0f} · sliding text behind you'
                elif frac < 0.75:
                    phase = f'Painting your video · second {sec_at:.0f} · bringing the animations to life'
                elif frac < 0.85:
                    phase = f'Painting your video · second {sec_at:.0f} · gliding the camera through the shot'
                else:
                    phase = f'Painting your video · second {sec_at:.0f} · final polish and color grade'
                if frame_start_t is None:
                    frame_start_t = time.time()
                    frame_start_i = cur
                elif cur > 0:
                    dt = time.time() - frame_start_t
                    dc = cur - frame_start_i
                    if dc > 0:
                        eta = int((tot - cur) * (dt / dc))
            except Exception:
                pass
        elif ln.startswith('Done:') or ln.startswith('Fertig') \
                or 'Encode fertig' in ln:
            phase = 'Encoding the final cut and saving it to your Library …'
            progress = 0.97

        if phase is not None or progress is not None or tail:
            kw = {'log_tail': tail}
            if phase is not None: kw['phase'] = phase
            if progress is not None: kw['progress'] = progress
            if eta is not None: kw['eta_sec'] = eta
            set_state(jid, **kw)
    p.wait()
    open(os.path.join(d, 'log.txt'), 'a', encoding='utf-8').write('\n'.join(log) + '\n')
    # v88b: Frisch erzeugtes Transkript in den Cache legen (fuer den naechsten
    # Upload derselben Datei). Nur bei Erfolg und wenn wirklich eins da ist.
    if p.returncode == 0 and _cache and not os.path.exists(_cache) \
            and os.path.exists(_tp):
        try:
            shutil.copyfile(_tp, _cache)
        except Exception:
            pass
    return p.returncode, log, out


# v138b: ECHTE OpenAI-Key-Pruefung fuer die Health-Ampel. Die alte Ampel war
# gruen, sobald irgendein Wert gesetzt war - live war der Key aber 401
# (Whisper lehnte ab) und niemand sah es. Leichter /v1/models-Call, 10 Min
# gecacht; Netzfehler ergeben None (unklar), nicht falsches Rot.
_OPENAI_CHECK = {'t': 0.0, 'ok': None}


def _openai_health():
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        return {'set': False, 'valid': None}
    now = time.time()
    if now - _OPENAI_CHECK['t'] > 600:
        try:
            import requests as _rq
            r = _rq.get('https://api.openai.com/v1/models',
                        headers={'Authorization': f'Bearer {key}'}, timeout=6)
            _OPENAI_CHECK.update(t=now, ok=(r.status_code == 200))
        except Exception:
            _OPENAI_CHECK.update(t=now, ok=None)
    return {'set': True, 'valid': _OPENAI_CHECK['ok']}


# ---------------------------------------------------------- Admin-Alarm
ADMIN_MAIL = (os.environ.get('DVE_ADMIN_MAIL') or 'ismet.01.b@gmail.com').strip()
_ADMIN_NOTIFIED = {}

# v131: EIN Regler gegen Postfach-Spam. Ismet will nicht jede Kleinigkeit
# als Mail. Stufen (DVE_ALERTS):
#   all       - alles, inkl. taegliche Backup-Mail (frueheres Verhalten).
#   important - NUR echte Stoerungen (Job-Fehler, Platte knapp, Timeout).
#               Routine-Post (taegliches Offsite-Backup) wird NICHT gemailt. (Default)
#   off       - gar keine Betriebs-Mails.
# Kunden-Mails (Verify, Reset, Kauf) sind davon UNBERUEHRT.
ALERT_LEVEL = os.environ.get('DVE_ALERTS', 'important').strip().lower()
if ALERT_LEVEL not in ('all', 'important', 'off'):
    ALERT_LEVEL = 'important'


ALERT_TAGE = int(os.environ.get('DVE_ALERT_DAYS', '90'))
ALERT_MAX = int(os.environ.get('DVE_ALERT_MAX', '5000'))
_ALERT_LETZT = {}          # Schluessel -> letzter Schreibzeitpunkt


def _alert_log(key, subject, body, gemailt=False):
    """v147: Stoerung in die alerts-Tabelle schreiben. Scheitert leise - eine
    kaputte Meldung darf nie den Betrieb reissen."""
    # v230d-sec ZWEI DECKEL. Die Tabelle wurde NIRGENDS aufgeraeumt, und ein
    # anonymer Aufruf konnte einen 500er ausloesen - gemessen 452 KB je 100
    # Anfragen in genau der Datei, in der auch Konten und Guthaben liegen und
    # die per Mail gesichert wird. Zwei Riegel: (1) derselbe Schluessel
    # hoechstens alle 5 Minuten (ein Fehler, der 1000-mal auftritt, ist
    # EIN Befund - die Wiederholungen sagen nichts Neues), (2) alte Zeilen
    # fliegen raus. Ein Alarmprotokoll, das ueberlaufen kann, verdeckt genau
    # die Stoerung, wegen der es angelegt wurde.
    _k = str(key)[:120]
    _now = time.time()
    _letzt = _ALERT_LETZT.get(_k, 0)
    if _now - _letzt < 300:
        return
    _ALERT_LETZT[_k] = _now
    if len(_ALERT_LETZT) > 500:                     # Speicher-Deckel
        for _alt in sorted(_ALERT_LETZT, key=_ALERT_LETZT.get)[:200]:
            _ALERT_LETZT.pop(_alt, None)
    try:
        con = _db()
        con.execute("INSERT INTO alerts (schluessel, betreff, text, gemailt, "
                    "gelesen, created_at) VALUES (?,?,?,?,0,?)",
                    (_k, str(subject)[:200], str(body)[:4000],
                     1 if gemailt else 0, int(_now)))
        con.execute("DELETE FROM alerts WHERE created_at < ? AND gelesen = 1",
                    (int(_now) - ALERT_TAGE * 86400,))
        # Harte Obergrenze, unabhaengig vom Alter: was aelter ist als die
        # letzten ALERT_MAX Zeilen, ist ohnehin nicht mehr die Stoerung von
        # heute.
        con.execute("DELETE FROM alerts WHERE id NOT IN "
                    "(SELECT id FROM alerts ORDER BY id DESC LIMIT ?)",
                    (ALERT_MAX,))
        con.commit()
        con.close()
    except Exception as e:
        print(f'Alert nicht gespeichert: {e}')


SEC_EVENT_TAGE = int(os.environ.get('DVE_SECLOG_DAYS', '180'))


def _sec_event(aktion, request=None, wer='', ziel='', detail=''):
    """v204-sec: Eine Zeile in die Chronik. Scheitert IMMER leise - ein
    Protokoll darf nie den Betrieb reissen. Bewusst ohne Inhalte: hier steht
    WER WANN WAS, nicht was in der Nachricht stand (Datensparsamkeit)."""
    ip = ''
    if request is not None:
        try:
            ip = _client_ip(request)
        except Exception:
            ip = ''
    werte = (int(time.time()), str(aktion)[:40], str(wer)[:40], str(ip)[:60],
             str(ziel)[:200], str(detail)[:400])
    # Ein Protokoll, das unter Last still Zeilen verliert, ist im Ernstfall
    # wertlos - und genau dann ist Last. Bei 'database is locked' wird kurz
    # gewartet und erneut versucht (SQLite serialisiert Schreibzugriffe).
    for versuch in range(3):
        try:
            con = _db()
            con.execute("INSERT INTO security_events (ts, aktion, wer, ip, "
                        "ziel, detail) VALUES (?,?,?,?,?,?)", werte)
            con.commit()
            con.close()
            return
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            if versuch < 2:
                time.sleep(0.15 * (versuch + 1))
                continue
            # Nach drei Versuchen aufgeben - aber LAUT, damit ein dauerhaft
            # blockiertes Protokoll auffaellt statt still zu verschwinden.
            print(f'Sicherheits-Protokoll nicht geschrieben ({aktion}): '
                  f'{type(e).__name__}: {e}')


def _sec_event_purge():
    """Aufbewahrung begrenzen. Ein Protokoll, das ewig waechst, ist selbst ein
    Datenschutz-Problem - und niemand liest 400 MB."""
    try:
        con = _db()
        con.execute("DELETE FROM security_events WHERE ts < ?",
                    (int(time.time()) - SEC_EVENT_TAGE * 86400,))
        con.commit()
        con.close()
    except Exception as e:
        print(f'Sicherheits-Protokoll nicht aufgeraeumt: {e}')


# v212: Wie lange ein GESCHLOSSENES Ticket noch beim Kunden steht.
TICKET_CLOSED_TTL = int(os.environ.get('DVE_TICKET_CLOSED_TTL', '86400'))
TRICHTER_TAGE = int(os.environ.get('DVE_FUNNEL_DAYS', '400'))
_TRICHTER_STUFEN = ('besuch', 'app', 'konto', 'upload', 'fertig', 'kauf')
# Woher kam jemand? Der Verweis-Header nennt die Domain, ein ?utm_source=
# in eigenen Links nennt die Kampagne. Beides auf einen kurzen Namen bringen -
# 'l.instagram.com' und 'instagram.com' sind dieselbe Quelle.
_QUELLEN = (('tiktok', 'tiktok'), ('instagram', 'instagram'), ('youtu', 'youtube'),
            ('facebook', 'facebook'), ('fb.', 'facebook'), ('linkedin', 'linkedin'),
            ('x.com', 'x'), ('twitter', 'x'), ('t.co', 'x'),
            ('reddit', 'reddit'), ('google', 'google'), ('bing', 'bing'),
            ('duckduckgo', 'duckduckgo'), ('pinterest', 'pinterest'),
            ('whatsapp', 'whatsapp'), ('telegram', 'telegram'))


def _quelle_von(request):
    """utm_source schlaegt den Verweis-Header - der ist gesetzt, weil WIR ihn
    in den Link geschrieben haben, und damit die genauere Angabe."""
    try:
        utm = (request.query_params.get('utm_source') or '').strip().lower()[:40]
        if utm:
            return re.sub(r'[^a-z0-9_.-]', '', utm) or 'unbekannt'
        ref = (request.headers.get('referer') or '').strip().lower()
        if not ref:
            return 'direkt'
        host = ref.split('//', 1)[-1].split('/', 1)[0]
        eigen = os.environ.get('DVE_PUBLIC_URL', 'douchko.eu')
        if host and host.split(':')[0] in eigen:
            return 'intern'
        for muster, name in _QUELLEN:
            if muster in host:
                return name
        return re.sub(r'[^a-z0-9_.-]', '', host)[:40] or 'direkt'
    except Exception:
        return 'direkt'


def _besucher_id(request):
    """Taeglich wechselnder Fingerabdruck. KEINE IP wird gespeichert, und der
    Wert laesst sich weder zurueckrechnen noch ueber Tage verketten - genau
    deshalb ist er keine personenbezogene Kennung."""
    try:
        salz = os.environ.get('DVE_REF_SALT', '') or 'dve'
        tag = time.strftime('%Y%m%d')
        roh = f"{salz}|{tag}|{_client_ip(request)}|" \
              f"{(request.headers.get('user-agent') or '')[:120]}"
        return hashlib.sha256(roh.encode('utf-8')).hexdigest()[:16]
    except Exception:
        return ''


def _trichter(stufe, request=None, user_id=None, quelle=None, besucher=None):
    """Eine Stufe festhalten. Scheitert IMMER leise - eine Zaehlung darf nie
    einen Seitenaufruf reissen."""
    if stufe not in _TRICHTER_STUFEN:
        return
    try:
        bes = besucher if besucher is not None else (
            _besucher_id(request) if request is not None else '')
        q = quelle
        if q is None:
            q = _quelle_von(request) if request is not None else ''
    except Exception as e:
        print(f'Trichter nicht gezaehlt ({stufe}): {type(e).__name__}: {e}')
        return
    # Kurz erneut versuchen: eine gleichzeitige Schreib-Transaktion sperrt die
    # Datei fuer einen Wimpernschlag, und eine verlorene Zeile faellt niemandem
    # auf - die Statistik ist dann einfach leise falsch.
    for _v in range(3):
        try:
            con = _db()
            con.execute("INSERT INTO trichter (ts, stufe, besucher, quelle, user_id) "
                        "VALUES (?,?,?,?,?)",
                        (int(time.time()), stufe, bes or '', (q or '')[:40], user_id))
            con.commit()
            con.close()
            return
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            if _v == 2:
                print(f'Trichter nicht gezaehlt ({stufe}): {type(e).__name__}: {e}')
            else:
                time.sleep(0.15 * (_v + 1))


def _trichter_purge():
    try:
        con = _db()
        con.execute("DELETE FROM trichter WHERE ts < ?",
                    (int(time.time()) - TRICHTER_TAGE * 86400,))
        con.commit(); con.close()
    except Exception as e:
        print(f'Trichter nicht aufgeraeumt: {e}')


def _alerts_offen():
    """Anzahl ungelesener Stoerungen - fuer den Zaehler im Live-Tab."""
    try:
        con = _db()
        n = con.execute("SELECT COUNT(*) c FROM alerts WHERE gelesen=0").fetchone()['c']
        con.close()
        return int(n)
    except Exception:
        return 0


def _notify_admin(key, subject, body, routine=False, mail=True):
    """Stoerung melden. Sie landet IMMER in der alerts-Tabelle (Admin-Panel);
    ob zusaetzlich eine Mail rausgeht, entscheiden DVE_ALERTS und mail=.
    Pro Stoerungs-Schluessel max. 1 Mail/Stunde (kein Postfach-Spam, wenn
    z.B. die Platte voll bleibt). Scheitert leise - ein kaputter
    Mail-Weg darf nie den Betrieb reissen.
    v131: durch DVE_ALERTS gefiltert. routine=True (z.B. taegliches Backup)
    geht NUR bei DVE_ALERTS=all raus; echte Stoerungen bei 'all'/'important'.
    v147: mail=False meldet NUR ins Panel. Ismets Wunsch fuer Render-Fehler -
    die will er sehen, wenn er hinschaut, nicht im Postfach."""
    now = time.time()
    darf = (mail and ALERT_LEVEL != 'off'
            and not (routine and ALERT_LEVEL != 'all')
            and now - _ADMIN_NOTIFIED.get(key, 0) >= 3600)
    if not routine:
        # Routine-Post (taegliches Backup) ist keine Stoerung und wuerde die
        # Liste zumuellen. Alles andere wird protokolliert, auch ungemailt.
        _alert_log(key, subject, body, gemailt=darf)
    if not darf:
        return False
    _ADMIN_NOTIFIED[key] = now
    try:
        # v226a WER MELDET, SAGT AUCH, WELCHER STAND ER IST. Ismet bekam
        # dieselbe Fehlalarm-Mail zweimal und konnte nicht sehen, ob die
        # zweite noch von der alten Fassung kam oder ob der Fix nicht griff -
        # das war eine halbe Stunde Rueckwaerts-Rechnen fuer eine Zeile, die
        # der Absender kostenlos mitliefern kann.
        _send_mail(ADMIN_MAIL, f'[DouchkoVE] {subject}',
                   f'{body}\n\n--\nGemeldet von DouchkoVE {DVE_BUILD}')
        return True
    except Exception as e:
        print(f'Admin-Mail fehlgeschlagen: {e}')
        return False


def _ist_speicher_tod(rc, log):
    """War es der Speicher? Drei Wege, alle drei zaehlen: die Engine bricht
    seit v230ak selbst mit 3 ab, das Betriebssystem schiesst mit -9 (bzw. 137)
    ab, und Python selbst wirft im Notfall MemoryError."""
    if rc == 3:
        return True
    if rc is not None and (rc < 0 and -rc == 9 or rc == 137):
        return True
    text = '\n'.join((log or [])[-40:])
    return 'not enough memory' in text or 'MemoryError' in text


def _render_fehler_text(rc, log):
    """v230aj: WARUM ist der Render gestorben? Bis hier stand in jedem Fall
    'Render failed.' - auch dann, wenn das Betriebssystem den Prozess wegen
    Speichermangels ABGESCHOSSEN hat. Im Log sieht man davon nichts: der
    Prozess ist einfach weg, und die letzten Zeilen kommen vom ffmpeg-
    Zulieferer, der ins Leere schreibt ('Broken pipe'). Genau so ist ein
    4K-Job bei Bild 100 von 293 gestorben, und niemand konnte sagen, ob
    Speicher, Absturz oder Zeitlimit schuld war.
    Ein Signal-Tod kommt bei subprocess als NEGATIVE Rueckgabe an (-9 =
    KILL); manche Shells melden ihn als 137 (128 + 9)."""
    sig = -rc if rc is not None and rc < 0 else (rc - 128 if rc and rc > 128 else 0)
    text = '\n'.join(log[-40:]) if log else ''
    mem = ''
    for zeile in reversed(log or []):
        if zeile.startswith('Memory:') or ' | Memory:' in zeile:
            mem = zeile[zeile.index('Memory:'):].strip()
            break
    if sig == 9:
        return ('The render was stopped by the server - it ran out of memory. '
                + (f'Last reading: {mem}. ' if mem else '')
                + 'A 4K render needs several gigabytes; try 1080p, or tell us '
                  'and we will raise the limit. Your credits were refunded.')
    if sig in (11, 6, 7):
        return ('The render crashed (signal %d). Your credits were refunded - '
                'please send us the job number, this is on us.' % sig)
    if 'MemoryError' in text:
        return ('The render ran out of memory. '
                + (f'Last reading: {mem}. ' if mem else '')
                + 'Your credits were refunded.')
    return 'Render failed.'


def _notify_job_fail(jid):
    """Nach jedem Job pruefen: fehlgeschlagen -> Eintrag im Admin-Panel.
    v147: KEINE Mail mehr (Ismets Wunsch). Der Eintrag bleibt persistent in
    der alerts-Tabelle - die JOBS-Liste haelt nur den Arbeitsspeicher und
    waere nach einem Neustart weg."""
    j = JOBS.get(jid) or {}
    if j.get('status') != 'fehler':
        return
    msg = str(j.get('msg', ''))[:300]
    _notify_admin(f'jobfail:{msg[:60]}', 'Render fehlgeschlagen',
                  f'Job {jid} ({j.get("kind", "caption")})\n'
                  f'User-ID: {j.get("user_id", "?")}\nMeldung: {msg}\n\n'
                  f'Credits wurden automatisch erstattet (falls reserviert).',
                  mail=False)


def _notify_job_done(jid):
    """v98 -> v130: 'Dein Video ist fertig'-Mail. Auf Ismets Wunsch DEAKTIVIERT.
    Nach dem Render wird KEINE Mail mehr verschickt. Bleibt als No-op erhalten
    (Aufrufer in worker/motion_worker unveraendert); zum Reaktivieren die alte
    Logik aus der Git-Historie zuruecknehmen."""
    return


def worker():
    while True:
        _, _, jid = QUEUE.get()
        try:
            run_job(jid)
        except Exception as e:
            set_state(jid, status='fehler',
                      msg=f'Unerwarteter Fehler: {type(e).__name__}: {e}')
            # v135a: auch der Catch-All erstattet - vorher blieb bei einem
            # unerwarteten Crash die Reservierung stehen (bezahlt, kein Video).
            try:
                _maybe_refund(jid)
            except Exception as e2:
                print(f'Catch-All-Refund {jid}: {e2}')
        finally:
            _notify_job_fail(jid)
            _notify_job_done(jid)
            QUEUE.task_done()


def _queue_platz(jid, q):
    """v197: Der Kunde sah bisher `Queued (position N)` mit N = qsize, also
    der GESAMTLAENGE der Schlange - nicht seinem Platz darin. Bei einer
    PriorityQueue ist das doppelt falsch: ein zahlendes Konto zieht vorbei
    (Prio 0), ein Free-Job rutscht nach hinten. Gezaehlt wird jetzt, wie
    viele Eintraege VOR diesem liegen. 1 = als naechstes dran.
    Der Heap wird nur gelesen (list()), nie veraendert."""
    try:
        eintraege = list(q.queue)
    except Exception:
        return max(1, q.qsize())
    treffer = [e for e in eintraege
               if (e[-1] if isinstance(e, tuple) else e) == jid]
    if not treffer:
        return max(1, q.qsize())               # laeuft evtl. schon
    meiner = treffer[0]
    if not isinstance(meiner, tuple):
        # MQUEUE ist eine schlichte FIFO - dort zaehlt die Einfuegereihenfolge.
        # Ein Groessenvergleich waere hier ein Stringvergleich und damit Unsinn.
        return eintraege.index(meiner) + 1
    return 1 + sum(1 for e in eintraege if e < meiner)


def motion_worker():
    """Fast-Lane: Motion-Clips (~10s Render) laufen an der Caption-Queue
    vorbei - ein 3-Minuten-Caption-Job blockiert sie nicht mehr."""
    while True:
        jid = MQUEUE.get()
        try:
            run_job(jid)
        except Exception as e:
            set_state(jid, status='fehler',
                      msg=f'Unerwarteter Fehler: {type(e).__name__}: {e}')
            try:
                _maybe_refund(jid)                     # v135a: siehe worker()
            except Exception as e2:
                print(f'Catch-All-Refund {jid}: {e2}')
        finally:
            _notify_job_fail(jid)
            _notify_job_done(jid)
            MQUEUE.task_done()


def _whisper_words(audio_path, language='auto'):
    """Self-contained Whisper-Transkription (whisper-1, Wort-Timings) fuer das Auto-Overlay.
    Bewusst NICHT render.transcribe(): das nutzt sys.exit und importiert die schwere
    render-Pipeline. Hier nur ein schlanker HTTP-Call; Fehler werden als Exception geworfen
    (der Aufrufer erstattet + zeigt sie), nie sys.exit."""
    import requests as _rq
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('Server has no OPENAI_API_KEY set.')

    def _reason(resp):
        try:
            return ((resp.json().get('error') or {}).get('message') or resp.text or '')[:220]
        except Exception:
            return (resp.text or '')[:220]

    # 429/5xx sind oft transient (Rate-Limit) -> mit Backoff neu versuchen. Ein echtes
    # Quota-/Billing-Problem ("insufficient_quota") ueberlebt die Retries und wird als
    # klarer Grund durchgereicht, damit man weiss: OpenAI-Konto pruefen, nicht der Code.
    r = None
    for attempt in range(4):
        with open(audio_path, 'rb') as f:
            r = _rq.post('https://api.openai.com/v1/audio/transcriptions',
                         headers={'Authorization': f'Bearer {key}'},
                         data={'model': 'whisper-1', 'response_format': 'verbose_json',
                               'timestamp_granularities[]': ['word', 'segment'],
                               **({} if language == 'auto' else {'language': language})},
                         files={'file': (os.path.basename(audio_path), f, 'audio/mp4')},
                         timeout=600)
        if r.status_code < 400:
            break
        _rsn = _reason(r)
        _quota = 'quota' in _rsn.lower() or 'billing' in _rsn.lower()
        # nur transiente Fehler wiederholen, kein Quota/4xx (ausser 429)
        if (r.status_code == 429 and not _quota) or 500 <= r.status_code < 600:
            if attempt < 3:
                time.sleep(2 ** attempt)   # 1s, 2s, 4s
                continue
        break
    if r is None or r.status_code >= 400:
        _rsn = _reason(r) if r is not None else 'no response'
        if r is not None and r.status_code == 413:
            raise RuntimeError('Audio track too large for transcription.')
        if r is not None and r.status_code == 429:
            if 'quota' in _rsn.lower() or 'billing' in _rsn.lower():
                raise RuntimeError('OpenAI account is out of quota/credits — top up billing on the OpenAI account.')
            raise RuntimeError('Transcription rate-limited after retries — try again in a few minutes.')
        raise RuntimeError(f'Transcription HTTP {r.status_code if r is not None else "?"}: {_rsn}')
    data = r.json()
    return [{'word': w['word'].strip(), 'start': round(w['start'], 3), 'end': round(w['end'], 3)}
            for w in data.get('words', [])]


def _ts_stamp(t, sep=','):
    """Sekunden -> SRT/VTT-Zeitstempel HH:MM:SS,mmm (SRT) bzw. HH:MM:SS.mmm (VTT)."""
    t = max(0.0, float(t)); ms = int(round((t - int(t)) * 1000)); s = int(t)
    return f'{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}{sep}{ms:03d}'


def _words_to_cues(words, max_words=9, max_gap=0.7, max_dur=6.0):
    """Wortliste [{word,start,end}] -> Untertitel-Cues. Neue Zeile an Satzende,
    langer Pause (>max_gap), nach max_words Woertern oder max_dur Sekunden."""
    cues, cur = [], []
    for w in words:
        tok = (w.get('word') or '').strip()
        if not tok:
            continue
        if cur:
            gap = float(w.get('start', 0)) - float(cur[-1].get('end', 0))
            dur = float(w.get('end', 0)) - float(cur[0].get('start', 0))
            if len(cur) >= max_words or gap > max_gap or dur > max_dur:
                cues.append(cur); cur = []
        cur.append(w)
        if tok.endswith(('.', '!', '?', '…')) and len(cur) >= 3:
            cues.append(cur); cur = []
    if cur:
        cues.append(cur)
    return [{'start': float(c[0].get('start', 0)), 'end': float(c[-1].get('end', 0)),
             'text': ' '.join((x.get('word') or '').strip() for x in c).strip()}
            for c in cues if c]


def _words_to_srt(words, vtt=False):
    """Wortliste -> SRT- bzw. WebVTT-Text (echte Timings)."""
    sep = '.' if vtt else ','
    cues = _words_to_cues(words)
    out = ['WEBVTT', ''] if vtt else []
    for i, c in enumerate(cues, 1):
        if not vtt:
            out.append(str(i))
        out.append(f"{_ts_stamp(c['start'], sep)} --> {_ts_stamp(c['end'], sep)}")
        out.append(c['text']); out.append('')
    return '\n'.join(out).strip() + '\n'


def _words_to_text(words):
    """Wortliste -> Fliesstext, an Satzenden umgebrochen (lesbares Transkript)."""
    line, paras = [], []
    for w in words:
        tok = (w.get('word') or '').strip()
        if not tok:
            continue
        line.append(tok)
        if tok.endswith(('.', '!', '?', '…')):
            paras.append(' '.join(line)); line = []
    if line:
        paras.append(' '.join(line))
    return '\n'.join(paras).strip()


def _run_motion_showcase(jid):
    """v117 Full-customizable Showcase: Video ODER Transkript-Text -> Storyboard
    (buildShowcase) -> gewaehlte Komposition (showcase/kinetic/prompt) + Stil + Format
    + ALLE Custom-Einstellungen -> eigenstaendiges MP4. render-showcase.mjs macht die
    Arbeit; Python besitzt Queue/Credits/Library. Text ist verbatim (kein Halluzinieren)."""
    j = JOBS[jid]
    d = job_dir(jid)
    out = os.path.join(d, 'fertig.mp4')
    set_state(jid, status='laeuft', phase='Preparing', progress=0.08, log_tail=[])
    wpath = os.path.join(d, 'words.json')
    # 1) Woerter: aus HOCHGELADENEM Transkript (Datei), aus dem Video transkribieren, ODER
    #    aus eingegebenem Text synthetisieren.
    if j.get('prewords'):
        words = j['prewords']
    elif j.get('showcase_video'):
        src = j['showcase_video']
        apath = os.path.join(d, 'audio.m4a')
        _br = max(24, min(64, int(24 * 8192 / max(float(j.get('dauer') or 1.0), 1.0))))
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-vn', '-ac', '1',
                            '-ar', '16000', '-c:a', 'aac', '-b:a', f'{_br}k', apath],
                           capture_output=True, text=True, timeout=180)
        except Exception as e:
            set_state(jid, status='fehler', progress=0, msg='Could not read the video audio.',
                      detail=f'{type(e).__name__}: {e}'); _maybe_refund(jid); return
        try:
            words = _whisper_words(apath, j.get('language', 'auto'))
        except Exception as e:
            set_state(jid, status='fehler', progress=0,
                      msg=f'Transcription failed: {str(e)[:180]}',
                      detail=f'{type(e).__name__}: {e}'); _maybe_refund(jid); return
        if not words:
            set_state(jid, status='fehler', progress=0, msg='No speech found in the video.')
            _maybe_refund(jid); return
    else:
        text = (j.get('transcript_text') or '').strip()
        if not text:
            set_state(jid, status='fehler', progress=0, msg='No text or video provided.')
            _maybe_refund(jid); return
        # synthetische Wort-Timings (0.32s/Wort + kleine Pause an Satzenden) fuer Voiceover-Sync.
        words = _synth_word_timings(text)
    with open(wpath, 'w', encoding='utf-8') as f:
        json.dump(words, f)
    # 2) Custom-Overrides -> Datei (alle Einstell-Knoepfe).
    custom = dict(j.get('custom') or {})
    cpath = os.path.join(d, 'custom.json')
    json.dump(custom, open(cpath, 'w', encoding='utf-8'))
    set_state(jid, phase='Preparing', progress=0.2)
    comp = j.get('composition', 'showcase')
    style = j.get('style', 'editorial')
    # Format AUTOMATISCH aus dem Quellvideo (echtes Seitenverhaeltnis, kein Nutzer-Regler
    # mehr). Nur wenn ein Video vorliegt; bei Text/Transkript-Datei bleibt der Default 9:16.
    fmt = '9:16'
    if j.get('showcase_video'):
        try:
            _pr = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                  '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x',
                                  j['showcase_video']], capture_output=True, text=True, timeout=30)
            _m = re.match(r'(\d+)x(\d+)', (_pr.stdout or '').strip())
            if _m:
                fmt = f'{int(_m.group(1))}x{int(_m.group(2))}'
        except Exception:
            fmt = '9:16'
    brand = str(custom.get('brand') or 'DouchkoVE')
    # --log=info (NICHT error): sonst schluckt Remotion die "Rendered N/M"-Zeilen und der
    # Balken haengt den ganzen (minutenlangen) Render bei 20% fest. Wir parsen Bundling,
    # Rendered und Encoded und bewegen den Balken sichtbar durch alle Phasen.
    # Gebremste Concurrency: unbeschraenkt startet Remotion 1 Chromium-Tab pro CPU-Kern —
    # auf einem vielkernigen Container sprengt das den Speicher, Chromium haengt/stirbt und
    # der Render kommt nie voran (klassischer „bleibt haengen"-Fall). 2 ist container-sicher.
    _conc = os.environ.get('DVE_MOTION_CONCURRENCY', '2')
    cmd = ['node', os.path.join('scripts', 'render-showcase.mjs'),
           os.path.abspath(wpath), os.path.abspath(out),
           '--composition=' + comp, '--style=' + style, '--format=' + fmt,
           '--brand=' + brand, '--custom-file=' + os.path.abspath(cpath),
           '--concurrency=' + str(_conc), '--log=info']
    p = subprocess.Popen(cmd, cwd=MOTION_DIR, env=dict(os.environ),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    JOBS[jid]['pid'] = p.pid
    # Stall-Waechter: ein haengender Render darf die (einspurige) Motion-Queue NICHT
    # blockieren (sonst haengen alle Folge-Jobs frueh bei „Queued" fest). Kommt STALL
    # Sekunden lang KEINE Ausgabe mehr, oder ueberschreitet der Render den Gesamt-Deckel,
    # wird der Prozess gekillt -> stdout-Schleife endet -> Fehler-Zweig + Erstattung.
    _killed = {'v': False, 'why': ''}
    _stall = float(os.environ.get('DVE_MOTION_STALL', '240'))    # 4 min ohne jede Ausgabe
    _max = float(os.environ.get('DVE_MOTION_TIMEOUT', '1200'))   # 20 min Gesamt-Deckel
    _t0 = time.time(); _last = [time.time()]; _wd_stop = threading.Event()
    def _watchdog():
        while not _wd_stop.wait(5):
            now = time.time()
            if now - _last[0] > _stall:
                _killed['v'] = True; _killed['why'] = 'stalled'
            elif now - _t0 > _max:
                _killed['v'] = True; _killed['why'] = 'timeout'
            if _killed['v']:
                try:
                    p.kill()
                except Exception:
                    pass
                return
    _wd = threading.Thread(target=_watchdog, daemon=True); _wd.start()
    log = []
    for line in p.stdout:
        _last[0] = time.time()                                   # Lebenszeichen fuer den Waechter
        log.append(line.rstrip())
        mb = re.search(r'Bundl\w+ (\d+)%', line)                 # 0.20 -> 0.28 waehrend Bundling
        if mb:
            set_state(jid, progress=0.20 + 0.08 * int(mb.group(1)) / 100.0,
                      phase='Preparing')
            continue
        mr = re.search(r'Rendered (\d+)/(\d+)', line)            # 0.30 -> 0.90 Frames
        if mr:
            fr, tot = int(mr.group(1)), max(int(mr.group(2)), 1)
            set_state(jid, progress=0.30 + 0.60 * fr / tot, phase='Rendering')
            continue
        me = re.search(r'Encoded (\d+)/(\d+)', line)             # 0.90 -> 0.98 Encoding
        if me:
            fr, tot = int(me.group(1)), max(int(me.group(2)), 1)
            set_state(jid, progress=0.90 + 0.08 * fr / tot, phase='Encoding')
    p.wait()
    _wd_stop.set()
    if _killed['v']:
        _why = ('stalled with no progress' if _killed['why'] == 'stalled'
                else 'took too long')
        set_state(jid, status='fehler', progress=0,
                  msg=f'This render {_why} and was stopped. Your credits were refunded.',
                  detail='\n'.join([x for x in log[-15:] if x.strip()]))
        _maybe_refund(jid); return
    if p.returncode == 0 and os.path.exists(out):
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', '1.0', '-i', out,
                            '-frames:v', '1', '-vf', 'scale=360:-2', os.path.join(d, 'poster.jpg')],
                           check=False, timeout=30)
        except Exception:
            pass
        set_state(jid, status='fertig', progress=1.0, phase='Done', video_url=f'/api/video/{jid}')
    else:
        set_state(jid, status='fehler', progress=0, msg='Motion render failed.',
                  detail='\n'.join([x for x in log[-15:] if x.strip()]))
        _maybe_refund(jid)


def _run_motion(jid):
    """Motion-Render: seit v118 nur noch das Full-customizable Studio-Showcase
    (Video/Transkript/Text -> Remotion-Komposition). Alle Alt-Engines entfernt."""
    return _run_motion_showcase(jid)


def run_job(jid):
    """Voller Render: Analyse -> Momente -> Video-Bau."""
    j = JOBS[jid]
    d = job_dir(jid)
    if j.get('kind') == 'motion':
        _run_motion(jid)
        return
    mode = j.get('mode', 'full')
    if mode == 'pre':
        # v83: Sofort-Transkription. Laeuft im Hintergrund waehrend der User
        # noch Presets einstellt. Schreibt quelle_transcript2.json - der
        # volle Render findet den Cache automatisch und spart die Whisper-
        # Wartezeit. Schlaegt sie fehl, ist das NICHT fatal: der Render
        # transkribiert dann einfach selbst.
        rc, log, out = _run_render(jid, extra_args=['--transcribe-only'],
                                   out_name='plan.mp4', progress_start=0.10)
        # v138: Fehlschlag SICHTBAR machen. Vorher blieb bei rc!=0 einfach die
        # Transkript-Datei aus -> /api/transcript lieferte ewig 404 und der
        # Editor zeigte fuer immer 'Listening ...'. Jetzt traegt der Job ein
        # tx_failed-Flag (+ letzte Log-Zeilen fuer die Admin-Diagnose).
        _txfail = (rc != 0)
        set_state(jid, status='vorbereitet', progress=1.0,
                  phase='Transcript ready' if rc == 0 else 'Prepared',
                  tx_failed=_txfail,
                  tx_error=('\n'.join([x for x in (log or [])[-8:] if x.strip()])
                            if _txfail else None))
        # Hat der User waehrenddessen schon Render gedrueckt? Dann direkt
        # weiter. dict.pop ist unter dem GIL atomar - entweder holt der
        # Worker den Auftrag oder /api/render_start, nie beide.
        nxt = JOBS[jid].pop('next_mode', None)
        if nxt:
            JOBS[jid]['mode'] = nxt
            set_state(jid, status='wartet', progress=0.0, phase='Queued …')
            q_put(jid)
        return
    if mode == 'alpha':
        # v101h: Caption-Ebene (ProRes 4444 mit Alpha) fuer den Schnittplatz.
        # Nutzt Transkript/Regie-Caches neben dem Quellvideo - kein Whisper,
        # keine neue KI-Regie, nur der Doppelpass-Render.
        JOBS[jid]['mode'] = 'full'          # nach dem Lauf normal weiter
        rc, log, out = _run_render(jid, extra_args=['--alpha-export'],
                                   out_name='fertig_captions.mov',
                                   progress_start=0.10)
        mov = os.path.join(d, 'fertig_captions.mov')
        if rc == 0 and os.path.exists(mov):
            set_state(jid, status='fertig', progress=1.0,
                      phase='Editor layer ready', alpha=True, out='fertig.mp4')
        else:
            letzte = [x for x in (log or [])[-15:] if x.strip()]
            set_state(jid, status='fertig', progress=1.0, alpha=False,
                      msg='Editor layer failed.', detail='\n'.join(letzte),
                      out='fertig.mp4')
            uid = j.get('user_id')
            if uid:
                _refund_credits(uid, f'Alpha {jid}',
                                _job_cost(j),
                                resv_like=f'Alpha {jid} %')
        return
    if mode == 'analyze':
        rc, log, out = _run_render(jid, extra_args=['--plan-only'],
                                   out_name='plan.mp4', progress_start=0.10)
        if rc == 0:
            # Momente-Datei liegt neben dem Quellvideo
            base = os.path.splitext(j['input'])[0]
            mom_path = base + '_momente.json'
            if os.path.exists(mom_path):
                set_state(jid, status='analysiert', progress=1.0,
                          phase='Moments ready',
                          moments_url=f'/api/moments/{jid}')
                return
        set_state(jid, status='fehler', progress=0,
                  msg='Analysis failed.',
                  detail='\n'.join([x for x in log[-15:] if x.strip()]))
        _maybe_refund(jid)
        return

    _extra = []
    _uid = j.get('user_id')
    # v203-sec: aus j['demo'] statt aus mode. mode wird umgeschrieben, das Flag
    # nicht - es ueberlebt jeden Editor-Roundtrip und den Neustart (set_state).
    if j.get('demo') or mode == 'demo':
        # v89: anonyme Kostprobe - immer Wasserzeichen, nur die ersten 10s.
        _extra = ['--watermark', '--duration', '10']
    elif _uid and not _has_purchased(_uid):
        # v101 Watermark-Unlock: sauber rendern + identisch wassermarkieren -
        # der erste Kauf schaltet GENAU dieses Video ohne Neu-Render frei.
        _extra = ['--watermark-split']
    rc, log, out = _run_render(jid, extra_args=_extra)
    log_txt = '\n'.join(log)
    # v80g: Menschliche Fehlermeldungen aus dem Render-Log herausklauben
    if 'OPENAI_API_KEY is not set' in log_txt \
            or 'OPENAI_API_KEY ist nicht gesetzt' in log_txt:
        set_state(jid, status='fehler', progress=0,
                  msg='Server is not fully configured '
                      '(AI key missing). Please contact support.')
        _maybe_refund(jid)
        return
    # v230ak NIE WIEDER EIN 4K-RENDER, DER EINFACH STIRBT. Reisst der Prozess
    # den Speicherdeckel, bricht die Engine seit v230ak selbst sauber ab
    # (Rueckgabe 3); wird er trotzdem abgeschossen, kommt -9 an. In BEIDEN
    # Faellen ist das Ergebnis fuer den Kunden dasselbe: kein Video. Statt ihn
    # damit stehen zu lassen, laeuft der Job EINMAL in 1080p nach - das
    # schafft dieselbe Maschine sicher - und der 4K-Aufschlag wird erstattet.
    # Kein stiller Tausch: die Meldung sagt, was passiert ist.
    if (_ist_speicher_tod(rc, log) and j.get('uhd')
            and not j.get('uhd_fallback')):
        j['uhd_fallback'] = True
        ov = dict(j.get('cfg_overrides') or {})
        out_cfg = dict(ov.get('output') or {})
        out_cfg['height'] = 1080
        out_cfg.pop('quality', None)
        ov['output'] = out_cfg
        j['cfg_overrides'] = ov
        # Der Aufschlag wird zurueckgegeben, BEVOR neu gerechnet wird - ein
        # Absturz im zweiten Lauf darf das Geld nicht verschlucken.
        uid = j.get('user_id')
        alt_kosten = _job_cost(j)
        neu_kosten = cost_seconds(j.get('dauer', 0), uhd=False)
        if uid and alt_kosten > neu_kosten and _render_charged(uid, jid):
            _refund_credits(uid, f'{jid} 4K-Aufschlag',
                            alt_kosten - neu_kosten)
        j['uhd'] = False
        j['cost_sec'] = neu_kosten
        set_state(jid, status='laeuft', progress=0.05,
                  phase='4K did not fit in memory - rendering 1080p instead')
        print(f'[{jid}] 4K gescheitert (Speicher) - zweiter Lauf in 1080p')
        rc, log, out = _run_render(jid, extra_args=_extra)
        if rc == 0 and os.path.exists(out):
            set_state(jid, hinweis='Your 4K render did not fit into this '
                                   'server\'s memory, so we delivered 1080p '
                                   'and refunded the 4K surcharge.')

    for line in reversed(log):                 # letzte FEHLER-Zeile gewinnt
        if line.startswith('ERROR:') or line.startswith('FEHLER:'):
            # v80o: Kontext mitliefern - die Zeilen um den Fehler herum
            # helfen bei der Diagnose direkt in der Web-UI.
            idx = len(log) - 1 - list(reversed(log)).index(line)
            ctx = [x for x in log[max(0, idx - 5):idx + 6] if x.strip()]
            set_state(jid, status='fehler', progress=0,
                      msg=line.split(':', 1)[1].strip(),
                      detail='\n'.join(ctx))
            _maybe_refund(jid)
            return
    if rc == 0 and os.path.exists(out):
        count_use(j['code'])
        # v80i: Video-Sekunden vom User-Guthaben abziehen (falls User-Account)
        # v80s: nur EINMAL pro Job - Re-Render nach Momente-Edit ist inklusive
        # (Konkurrenz-Standard, sonst zahlt man jede Korrektur doppelt).
        uid = j.get('user_id')
        if uid and not _render_charged(uid, jid):
            verbrauch = _job_cost(j)
            # v135a: race-sicher reservieren (WHERE balance >= need) statt
            # MAX(0)-Clamp. Nach den Reservierungs-Fixes in render_start und
            # save_and_render sollte dieser Pfad nie mehr feuern - wenn doch
            # und die Deckung fehlt: Rest ehrlich buchen + Admin-Alarm statt
            # stiller Gratis-Auslieferung mit kaputter Ledger-Invariante.
            if not _reserve_credits(uid, verbrauch, jid):
                _u = _find_user_by_id(uid)
                _rest = max(0, int(_u['balance_sec'])) if _u else 0
                teil = min(verbrauch, _rest)
                if teil > 0:
                    _adjust_balance(uid, -teil, f'Render {jid} ({teil}s)')
                _notify_admin(f'undercharge:{jid}',
                              'Render ohne volle Deckung durchgelaufen',
                              f'Job {jid}: {verbrauch}s faellig, nur {_rest}s '
                              f'auf Konto {uid}. Reservierungs-Pfad pruefen.')
        if os.path.exists(os.path.join(job_dir(jid), 'master_clean.mp4')):
            set_state(jid, wm=True)          # v101: freischaltbar nach Kauf
        if os.path.exists(os.path.join(job_dir(jid), 'fertig_kontakt.jpg')):
            set_state(jid, kontakt=True)     # v101g: Momente-Beweisbogen da
        # v101 Silent-Score: render.py legt <input>_silent.json ab, wenn die
        # Stumm-Bewertung lief - in den Job-State fuer die UI uebernehmen.
        try:
            _slp = os.path.splitext(j.get('input', ''))[0] + '_silent.json'
            if os.path.exists(_slp):
                _sl = json.load(open(_slp, encoding='utf-8'))
                set_state(jid, silent_score=int(_sl.get('score', 0)),
                          silent_hints=_sl.get('hinweise', [])[:3])
        except Exception:
            pass
        # v124 Hook-Score in den Job-State: dieselbe Heuristik wie die Ergebnis-
        # Kachel im Client, aus der finalen Momente-Datei. Damit hat die Library
        # einen Verlauf (Bestwert, Trend) ohne N Zusatz-Requests.
        try:
            _mp = os.path.splitext(j.get('input', ''))[0] + '_momente.json'
            if os.path.exists(_mp):
                set_state(jid, hook_score=_hook_score(
                    json.load(open(_mp, encoding='utf-8')), j.get('dauer', 0)))
        except Exception:
            pass
        set_state(jid, status='fertig', progress=1.0, phase='Done',
                  out='fertig.mp4')
        # v208 Stufe 5: der Kunde hat zum ersten Mal ein ERGEBNIS gesehen.
        # Das ist die wichtigste Stufe vor dem Kauf - wer hier abspringt, hat
        # das Produkt gesehen und trotzdem nicht gekauft.
        _trichter('fertig', None, user_id=j.get('user_id'), quelle='', besucher='')
    else:
        letzte = [x for x in log[-15:] if x.strip()]
        set_state(jid, status='fehler', progress=0,
                  msg=_render_fehler_text(rc, log),
                  detail='\n'.join(letzte))
        _maybe_refund(jid)
    # Quellvideo aufheben, damit "Momente-Editor" nach Analyse den Re-Render kann.
    # Erst beim Job-Cleanup loeschen.


# ======================================================================
# v230v SICHERUNG AUSSER HAUS (Cloudflare R2)
# ----------------------------------------------------------------------
# Bis hierher lag die einzige Sicherung auf DERSELBEN Platte wie die
# Datenbank. Stirbt sie, ist das Guthaben zahlender Kunden weg - das
# groesste Einzelrisiko im ganzen Betrieb. Der Mail-Weg (_mail_backup_offsite)
# lief nur bei DVE_ALERTS=all, also im Normalbetrieb GAR NICHT, und er
# verschickte die Datenbank unverschluesselt.
#
# Vier Entscheidungen, jede mit Grund:
#  * Die Zugaenge kommen ueber das PANEL, nicht ueber eine Datei auf dem
#    Server. Alles laeuft ueber das Panel (Ismets Ansage, v197) - ein Weg,
#    der ein Terminal braucht, wird nie benutzt.
#  * Verschluesselt wird VOR dem Verlassen des Servers. Wer den Bucket
#    aufmacht, sieht Zufallsrauschen.
#  * Das Passwort wird EINMAL angezeigt und muss ausser Haus liegen. Eine
#    verschluesselte Kopie, deren Schluessel nur auf der toten Platte lag,
#    ist keine Sicherung.
#  * Keine neue Abhaengigkeit erzwungen: gibt es `cryptography` im Bild,
#    laeuft AES-256-GCM. Sonst greift ein Verfahren aus der Standard-
#    bibliothek (scrypt + HMAC-SHA256 als Schluesselstrom, danach HMAC ueber
#    den Geheimtext). Welches benutzt wurde, steht IM Kopf der Datei - das
#    Zurueckspielen findet es also selbst heraus.
# ======================================================================
R2_FELDER = ('r2_endpoint', 'r2_key', 'r2_secret', 'r2_bucket')
R2_GEHEIM = ('r2_secret', 'r2_pass')
R2_STAENDE = 30                      # so viele Sicherungen bleiben liegen


def _set_get(k, default=''):
    try:
        con = _db()
        r = con.execute('SELECT v FROM app_settings WHERE k=?', (k,)).fetchone()
        return r['v'] if r else default
    except Exception:
        return default


def _set_put(k, v):
    con = _db()
    con.execute('INSERT INTO app_settings(k,v,ts) VALUES(?,?,?) '
                'ON CONFLICT(k) DO UPDATE SET v=excluded.v, ts=excluded.ts',
                (k, str(v), int(time.time())))
    con.commit()


def _r2_bereit():
    """Sind alle vier Zugangsdaten UND ein Passwort gesetzt?

    `bool(...)` ist hier KEINE Kosmetik: `a and b` gibt in Python b zurueck,
    also stand ohne die Klammer das PASSWORT in der Antwort von
    /api/admin/offsite. Ein Geheimnis darf den Server nie wieder verlassen -
    darum steht in der Antwort ausschliesslich 'gesetzt: ja/nein'."""
    return bool(all(_set_get(k).strip() for k in R2_FELDER)
                and _set_get('r2_pass').strip())


# ---- Verschluesselung --------------------------------------------------
_KRYPT_KOPF = b'DVE1'


def _krypt_schluessel(pw, salz):
    """scrypt: aus einem Passwort werden zwei 32-Byte-Schluessel."""
    roh = hashlib.scrypt(pw.encode('utf-8'), salt=salz, n=2 ** 14, r=8, p=1,
                         dklen=64)
    return roh[:32], roh[32:]


def _hmac_strom(k, nonce, laenge):
    """Schluesselstrom aus HMAC-SHA256 im Zaehlerbetrieb. HMAC (nicht der
    nackte Hash) ist hier Absicht: damit gibt es die Laengen-Verlaengerungs-
    Falle gar nicht erst."""
    out = bytearray()
    i = 0
    while len(out) < laenge:
        out += hmac.new(k, nonce + i.to_bytes(8, 'big'), hashlib.sha256).digest()
        i += 1
    return bytes(out[:laenge])


def _krypt_pack(roh, pw):
    """Klartext -> Datei. Kopf: DVE1 | Verfahren | Salz | Nonce."""
    salz = os.urandom(16)
    nonce = os.urandom(16)
    k_enc, k_mac = _krypt_schluessel(pw, salz)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        art = b'G'                                   # AES-256-GCM
        ct = AESGCM(k_enc).encrypt(nonce[:12], roh, _KRYPT_KOPF + art)
        return _KRYPT_KOPF + art + salz + nonce + ct
    except Exception:
        art = b'H'                                   # Standardbibliothek
        ct = bytes(a ^ b for a, b in zip(roh, _hmac_strom(k_enc, nonce, len(roh))))
        tag = hmac.new(k_mac, _KRYPT_KOPF + art + salz + nonce + ct,
                       hashlib.sha256).digest()
        return _KRYPT_KOPF + art + salz + nonce + ct + tag


def _krypt_unpack(blob, pw):
    """Datei -> Klartext. Wirft ValueError bei falschem Passwort oder wenn
    jemand die Datei angefasst hat - beides darf NIE stillschweigend als
    'Sicherung ist in Ordnung' durchgehen."""
    if len(blob) < 5 + 32 or blob[:4] != _KRYPT_KOPF:
        raise ValueError('not a DouchkoVE backup file')
    art = blob[4:5]
    salz, nonce, rest = blob[5:21], blob[21:37], blob[37:]
    k_enc, k_mac = _krypt_schluessel(pw, salz)
    if art == b'G':
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            return AESGCM(k_enc).decrypt(nonce[:12], rest, _KRYPT_KOPF + art)
        except Exception:
            raise ValueError('wrong password or damaged file')
    if art != b'H':
        raise ValueError('unknown backup format')
    ct, tag = rest[:-32], rest[-32:]
    soll = hmac.new(k_mac, _KRYPT_KOPF + art + salz + nonce + ct,
                    hashlib.sha256).digest()
    if not hmac.compare_digest(soll, tag):
        raise ValueError('wrong password or damaged file')
    return bytes(a ^ b for a, b in zip(ct, _hmac_strom(k_enc, nonce, len(ct))))


# ---- S3-Signatur (SigV4) ----------------------------------------------
def _sig_hmac(k, m):
    return hmac.new(k, m.encode('utf-8'), hashlib.sha256).digest()


def _r2_ruf(method, pfad, daten=b'', query='', timeout=30):
    """EIN signierter Aufruf gegen R2. R2 spricht die S3-Schnittstelle;
    signiert wird mit AWS SigV4, Region 'auto'. Absichtlich ohne boto3 -
    die Abhaengigkeiten sind exakt festgenagelt (v205a-sec), und fuer vier
    Aufrufe lohnt kein neues Bauteil."""
    import requests
    import urllib.parse
    ep = _set_get('r2_endpoint').strip().rstrip('/')
    key = _set_get('r2_key').strip()
    secret = _set_get('r2_secret').strip()
    bucket = _set_get('r2_bucket').strip()
    if not (ep and key and secret and bucket):
        raise RuntimeError('offsite storage is not configured')
    if not ep.startswith('https://'):
        raise RuntimeError('endpoint must start with https://')
    host = ep.split('://', 1)[1].split('/')[0]
    kanon_pfad = '/' + bucket + (('/' + pfad) if pfad else '')
    kanon_pfad = urllib.parse.quote(kanon_pfad, safe='/~')
    jetzt = time.gmtime()
    stamp = time.strftime('%Y%m%dT%H%M%SZ', jetzt)
    tag = time.strftime('%Y%m%d', jetzt)
    hash_body = hashlib.sha256(daten or b'').hexdigest()
    kopf = {'host': host, 'x-amz-content-sha256': hash_body, 'x-amz-date': stamp}
    signierte = ';'.join(sorted(kopf))
    kanon = '\n'.join([
        method, kanon_pfad, query,
        ''.join(f'{k}:{kopf[k]}\n' for k in sorted(kopf)),
        signierte, hash_body])
    bereich = f'{tag}/auto/s3/aws4_request'
    zu_signieren = '\n'.join(['AWS4-HMAC-SHA256', stamp, bereich,
                              hashlib.sha256(kanon.encode()).hexdigest()])
    k = _sig_hmac(('AWS4' + secret).encode('utf-8'), tag)
    k = _sig_hmac(k, 'auto')
    k = _sig_hmac(k, 's3')
    k = _sig_hmac(k, 'aws4_request')
    sig = hmac.new(k, zu_signieren.encode('utf-8'), hashlib.sha256).hexdigest()
    kopf['Authorization'] = (f'AWS4-HMAC-SHA256 Credential={key}/{bereich}, '
                             f'SignedHeaders={signierte}, Signature={sig}')
    url = f'https://{host}{kanon_pfad}' + (f'?{query}' if query else '')
    r = requests.request(method, url, data=daten or None, headers=kopf,
                         timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f'offsite storage said {r.status_code}: '
                           f'{r.text[:200]}')
    return r


def _r2_put(name, blob):
    _r2_ruf('PUT', name, blob)


def _r2_get(name):
    return _r2_ruf('GET', name).content


def _r2_del(name):
    _r2_ruf('DELETE', name)


def _r2_liste():
    """Namen und Groessen im Bucket, neueste zuerst."""
    import xml.etree.ElementTree as ET
    r = _r2_ruf('GET', '', query='list-type=2&max-keys=200')
    ns = '{http://s3.amazonaws.com/doc/2006-03-01/}'
    out = []
    for c in ET.fromstring(r.content).findall(f'{ns}Contents'):
        out.append({'name': (c.findtext(f'{ns}Key') or ''),
                    'bytes': int(c.findtext(f'{ns}Size') or 0),
                    'ts': (c.findtext(f'{ns}LastModified') or '')})
    return sorted(out, key=lambda x: x['name'], reverse=True)


def _offsite_r2(dest):
    """Einen Snapshot verschluesselt hochladen und alte Staende aufraeumen.
    Scheitert LAUT (Alarm im Panel): eine Sicherung, von der man erst im
    Ernstfall erfaehrt, dass sie nicht lief, ist keine."""
    if not _r2_bereit():
        return False
    name = os.path.basename(dest) + '.enc'
    roh = open(dest, 'rb').read()
    _r2_put(name, _krypt_pack(roh, _set_get('r2_pass')))
    _set_put('r2_letzte', f'{int(time.time())}|{name}|{len(roh)}')
    try:
        alt = [x['name'] for x in _r2_liste() if x['name'].endswith('.enc')]
        for weg in alt[R2_STAENDE:]:
            _r2_del(weg)
    except Exception as e:
        print(f'Offsite-Rotation uebersprungen: {type(e).__name__}: {e}')
    print(f'Offsite: {name} hochgeladen ({len(roh)} Bytes)')
    return True


def _db_geaendert():
    """v230y WANN WURDE ZULETZT IN DIE DATENBANK GESCHRIEBEN?

    NICHT `getmtime(USERS_DB)`. Die Datenbank laeuft im WAL-Modus: ein
    INSERT landet in `users.db-wal`, die Datei `users.db` selbst wird dabei
    GAR NICHT angefasst und behaelt ihre alte Zeit - bis irgendwann ein
    Checkpoint laeuft. Der Frische-Test des Snapshots hat genau auf diese
    Datei geschaut und darum entschieden "seit dem Snapshot wurde nichts
    geschrieben", obwohl Konten dazugekommen waren.
    Folge: der taegliche Snapshot konnte STILL veralten - im schlimmsten Fall
    enthielt "die Sicherung von heute" den leeren Stand vom Serverstart. Im
    Test-Gate im Container genau so aufgetreten (3 Konten in der Datenbank,
    0 im Snapshot); lokal lief zufaellig vorher ein Checkpoint, deshalb war
    es hier nie zu sehen.
    Gemessen wird deshalb die NEUESTE der drei Dateien."""
    m = 0.0
    for suf in ('', '-wal', '-shm'):
        try:
            m = max(m, os.path.getmtime(USERS_DB + suf))
        except OSError:
            pass
    return m


# v230z: Meldungen, die genau EINMAL je Programmlauf kommen sollen. Ein
# Zustand, der stuendlich dieselbe Mail ausloest, wird nach zwei Tagen
# weggefiltert - und dann sieht ihn niemand mehr.
_EINMAL = {}


def _snapshot_gegenprobe(dest, soll=None):
    """v230z DIE SICHERUNG PRUEFT SICH SELBST.

    Ein Netz, das sich nicht selbst prueft, ist Dekoration: die taegliche
    Sicherung lief jahrelang, meldete "DB-Backup: ..." und konnte trotzdem
    den LEEREN Stand vom Serverstart enthalten (v230y, WAL-Falle). Aufgefallen
    ist das nur, weil ein Test im Container zufaellig hinsah - im Betrieb
    haette es niemand gemerkt, bis die Sicherung gebraucht wird. Und dann ist
    es zu spaet.

    Also nach JEDER Sicherung: die Zahlen im Snapshot gegen die laufende
    Datenbank halten. Weniger Konten oder weniger Kaeufe als jetzt = Alarm
    mit Mail. Mehr ist in Ordnung (zwischen Sicherung und Vergleich kann ein
    Konto geloescht worden sein), weniger nie - der Snapshot wird direkt aus
    der laufenden Datenbank gezogen.

    Scheitert die Gegenprobe selbst, ist das AUCH ein Alarm: eine Pruefung,
    die still ausfaellt, ist genau das Problem, das sie loesen soll.
    """
    try:
        ok, meldung, zahlen = _pruefe_sicherung(dest)
        if not ok:
            _notify_admin('backup_pruef', 'Die Sicherung ist nicht lesbar',
                          f'{os.path.basename(dest)}: {meldung}\n\n'
                          'Die Datei liegt da, taugt aber nichts. Bitte im '
                          'Panel unter Betrieb -> System nachsehen.', mail=True)
            return False
        # v230aa VERGLICHEN WIRD MIT DEM STAND BEIM SICHERN, NICHT MIT JETZT.
        # Ein Snapshot ist ein Zeitpunkt: meldet sich eine Sekunde spaeter
        # jemand an, hat die laufende Datenbank mehr Konten - das ist normal
        # und darf kein Alarm sein. Sonst regnet es Fehlalarme, und nach der
        # dritten Mail schaut niemand mehr hin (die schlimmste Sorte Wachhund).
        # `soll` sind die Zahlen VOR dem Kopieren; der Snapshot muss sie
        # mindestens enthalten.
        if soll is None:
            con = _db()
            soll = {
                'konten': con.execute('SELECT COUNT(*) c FROM users').fetchone()['c'],
                'kaeufe': con.execute('SELECT COUNT(*) c FROM purchases').fetchone()['c'],
            }
        fehlt = [f"{k}: {zahlen.get(k)} statt {soll[k]}"
                 for k in ('konten', 'kaeufe')
                 if int(zahlen.get(k, -1)) < int(soll[k])]
        if fehlt:
            _notify_admin('backup_pruef', 'Die Sicherung ist unvollstaendig',
                          f'{os.path.basename(dest)} enthaelt weniger als die '
                          f'laufende Datenbank:\n  ' + '\n  '.join(fehlt) +
                          '\n\nDas heisst: im Ernstfall fehlen diese Daten.',
                          mail=True)
            return False
        print(f"  Backup-Gegenprobe: {zahlen.get('konten')} Konten, "
              f"{zahlen.get('kaeufe')} Kaeufe - stimmt mit der Datenbank")
        return True
    except Exception as e:
        _notify_admin('backup_pruef', 'Die Sicherung liess sich nicht pruefen',
                      f'{type(e).__name__}: {e}', mail=True)
        return False


def _backup_users_db(force=False):
    """v80x: Taeglicher Snapshot der users.db nach DATA/backups.
    14 Stueck rotierend. SQLite-Online-Backup-API - konsistent auch
    waehrend laufender Writes.

    v197: Der Snapshot wurde bis v196 nur EINMAL je Kalendertag geschrieben
    (`if os.path.exists(dest): return`). Der erste Lauf ist der Start des
    Cleanup-Workers - alles, was danach am selben Tag passierte, stand in
    KEINEM Backup, und nach einem Neustart um 23:50 enthielt "das Backup von
    heute" praktisch nichts. Bei der Restore-Probe kamen dadurch 0 Konten
    zurueck, obwohl 7 in der DB standen. Der Tages-Snapshot wird jetzt
    aufgefrischt, solange die DB neuer ist als er.
    Geschrieben wird ueber eine .tmp-Datei mit os.replace - ein Abbruch
    mitten im Auffrischen darf den vorhandenen Snapshot nicht zerstoeren.
    Die Offsite-Mail geht weiter nur EINMAL je Tag raus (beim ersten
    Anlegen), sonst kaeme stuendlich Post."""
    bdir = os.path.join(DATA, 'backups')
    os.makedirs(bdir, exist_ok=True)
    stamp = time.strftime('%Y%m%d')
    dest = os.path.join(bdir, f'users_{stamp}.db')
    neu = not os.path.exists(dest)
    if not neu and not force:
        try:
            # v230aa GLEICHSTAND HEISST NICHT "NICHTS PASSIERT".
            # Die Zeitstempel des Dateisystems sind im Container auf die
            # Sekunde genau. Wird in DERSELBEN Sekunde gesichert und
            # geschrieben, sind beide Zeiten gleich - mit `<=` galt das als
            # "seit dem Snapshot nichts geschrieben", und der Schreibzugriff
            # fiel bis zum naechsten Tag aus der Sicherung. Lokal (Nanosekunden)
            # trat der Fall nie ein, im Test-Gate jedes Mal.
            # Bei Gleichstand wird jetzt AUFGEFRISCHT. Der Preis ist eine
            # 370-KB-Kopie pro Stunde; eine Sicherung, die einen Schreibzugriff
            # verschluckt, waere der falsche Tausch.
            if _db_geaendert() < os.path.getmtime(dest):
                return                       # seit dem Snapshot nichts geschrieben
        except OSError:
            pass
    # v230w EIGENE .tmp-DATEI JE LAUF. Bis hierher hiess sie fuer alle
    # gleich `<dest>.tmp` - und `_backup_users_db` laeuft an ZWEI Stellen:
    # im Cleanup-Arbeiter (Hintergrund-Thread, startet mit dem Server) und
    # auf Knopfdruck bzw. im Test. Laufen beide gleichzeitig, loescht der
    # eine die halb geschriebene Datei des anderen, und `os.replace` schiebt
    # einen LEEREN Stand ueber den guten Snapshot. Genau das ist im
    # Test-Gate passiert: 3 Konten in der Datenbank, 0 im Snapshot.
    # Der Fehler war immer da; meine Offsite-Kopie hat den ersten Lauf
    # laenger gemacht und damit das Zeitfenster aufgerissen.
    tmp = f'{dest}.{os.getpid()}.{threading.get_ident()}.tmp'
    # v230aa: die Zahlen VOR dem Kopieren merken - der Snapshot muss sie
    # mindestens enthalten. Mit den Zahlen von NACHHER verglichen waere jede
    # Anmeldung in der Zwischenzeit ein Fehlalarm.
    try:
        _c0 = _db()
        soll = {'konten': _c0.execute('SELECT COUNT(*) c FROM users').fetchone()['c'],
                'kaeufe': _c0.execute('SELECT COUNT(*) c FROM purchases').fetchone()['c']}
    except Exception:
        soll = None
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        src = sqlite3.connect(USERS_DB)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close(); src.close()
        os.replace(tmp, dest)
        # Rotation: nur die 14 neuesten behalten (.tmp zaehlt nicht mit)
        snaps = sorted(f for f in os.listdir(bdir)
                       if f.startswith('users_') and f.endswith('.db'))
        for old in snaps[:-14]:
            os.remove(os.path.join(bdir, old))
        # Liegengebliebene Bruchstuecke abgebrochener Laeufe (aelter als eine
        # Stunde) wegraeumen - sonst fuellen sie ueber Monate die Platte.
        for f in os.listdir(bdir):
            if f.endswith('.tmp') and f != os.path.basename(tmp):
                pf = os.path.join(bdir, f)
                try:
                    if time.time() - os.path.getmtime(pf) > 3600:
                        os.remove(pf)
                except OSError:
                    pass
        print(f"DB-Backup: {dest}{'' if neu else ' (aufgefrischt)'}")
        _snapshot_gegenprobe(dest, soll)
        if neu:
            # v230v: die Kopie ausser Haus zuerst - sie ist die einzige, die
            # einen Plattenschaden ueberlebt. Scheitert sie, ist das ein
            # ECHTER Alarm: eine Sicherung, von deren Ausfall man erst im
            # Ernstfall erfaehrt, ist keine.
            try:
                if not _offsite_r2(dest):
                    _mail_backup_offsite(dest)      # alter Weg als Rueckfall
            except Exception as e:
                _notify_admin('offsite', 'Sicherung ausser Haus fehlgeschlagen',
                              f'{type(e).__name__}: {e}', mail=True)
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        print(f"DB-Backup fehlgeschlagen: {type(e).__name__}: {e}")


def _mail_backup_offsite(dest):
    """v98: Der Snapshot lag bisher auf DERSELBEN Platte wie die DB -
    stirbt der Server, ist das Credit-Ledger zahlender Kunden weg. Taeglich
    geht das gzip-te Backup per Mail an ADMIN_MAIL (Postfach = Offsite).
    Nur bis 8 MB (Gmail-Limit 25 MB, die DB ist winzig); scheitert leise.
    v131: Routine-Post - nur bei DVE_ALERTS=all. Das lokale, rotierende
    Backup auf der Platte bleibt IMMER (siehe _backup_users_db)."""
    if ALERT_LEVEL != 'all':
        return
    try:
        import gzip
        raw = open(dest, 'rb').read()
        gz = gzip.compress(raw)
        if len(gz) > 8 * 1024 * 1024:
            print(f'Backup-Mail uebersprungen: {len(gz)/1e6:.1f} MB zu gross')
            return
        import smtplib
        from email.message import EmailMessage
        user = os.environ.get('SMTP_USER', '').strip()
        pw = os.environ.get('SMTP_PASS', '').replace(' ', '').strip()
        if not user or not pw:
            return                    # kein SMTP konfiguriert -> kein Offsite
        msg = EmailMessage()
        msg['From'] = os.environ.get('MAIL_FROM', user)
        msg['To'] = ADMIN_MAIL
        msg['Subject'] = f'[DouchkoVE] DB-Backup {os.path.basename(dest)}'
        msg.set_content('Taegliches Offsite-Backup der users.db (gzip). '
                        'Entpacken: gunzip <datei>.')
        msg.add_attachment(gz, maintype='application', subtype='gzip',
                           filename=os.path.basename(dest) + '.gz')
        host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        port = int(os.environ.get('SMTP_PORT', '587'))
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        print('Backup-Mail an', ADMIN_MAIL, 'geschickt')
    except Exception as e:
        print(f'Backup-Mail fehlgeschlagen: {type(e).__name__}: {e}')


def _expiry_sammeln(jid, d, mtime, cutoff, eimer):
    """v194b: Ablaufende Videos EINSAMMELN statt sofort mailen.

    Bis v194a ging pro JOB eine Mail raus. Der Deckel (`expiry_mail` im
    Job-State) verhinderte nur die zweite Mail zum SELBEN Job - wer dasselbe
    Video dreimal gerendert hat, bekam drei Jobs und damit drei identische
    Mails, alle in derselben Minute (Ismets Screenshot: 2x "Sequence.mp4"
    um 18:35). Der Cleanup laeuft stuendlich ueber ALLE Jobs, also war das
    kein Randfall, sondern der Normalfall fuer jeden aktiven Nutzer.
    Jetzt wird je Durchlauf gesammelt und danach EINE Mail je Nutzer
    geschickt."""
    if mtime >= cutoff + 48 * 3600:                    # noch > 48h Restzeit
        return
    j = JOBS.get(jid)
    if not j or j.get('status') != 'fertig' or j.get('expiry_mail'):
        return
    uid = j.get('user_id')
    if not uid or not os.path.exists(os.path.join(d, 'fertig.mp4')):
        return
    hours = max(1, int((mtime + RETENTION_DAYS * 86400 - time.time()) / 3600))
    eimer.setdefault(uid, []).append((jid, j.get('name') or 'your video', hours))


def _expiry_mails(eimer, _aktiv=None):
    """Eine Mail je Nutzer, mit ALLEN ablaufenden Videos darin.

    Zusaetzlicher Riegel ueber `mail_log`: hoechstens eine Ablauf-Mail pro
    Nutzer und Tag. Der Job-Flag allein reicht nicht - er zaehlt Jobs, und
    genau das war das Problem."""
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    _aktiv = _aktiv or {}
    for uid, posten in eimer.items():
        u = _find_user_by_id(uid)
        if not u or not u['verified']:
            continue
        # v194c ZWEI RIEGEL statt eines Tages-Schluessels.
        # (a) Wer gerade ohnehin da ist, braucht keine Erinnerung. Er sieht
        #     die Library. Ein Vielrenderer bekaeme sonst dauerhaft Post,
        #     weil bei ihm JEDEN Tag etwas ablaeuft - bei 100 Videos waeren
        #     das 30 Mails im Monat, nur eben gebuendelt.
        # (b) Rollender Mindestabstand von einer RETENTION-Periode. Damit
        #     kann es hoechstens eine Erinnerung je Aufbewahrungs-Zyklus
        #     geben, egal wie viele Videos ablaufen.
        _still = min(_letzter_login(uid), _aktiv.get(uid, 1e9))
        if _still < 48 * 3600:
            for jid, _n, _h in posten:
                set_state(jid, expiry_mail=True)       # abhaken, nicht mailen
            print(f'Ablauf-Mail: User {uid} war vor {_still/3600:.0f}h aktiv '
                  f'- keine Erinnerung noetig')
            continue
        if not _mail_abstand_ok(uid, 'expiry', RETENTION_DAYS * 86400):
            for jid, _n, _h in posten:
                set_state(jid, expiry_mail=True)       # trotzdem abhaken
            continue
        for jid, _n, _h in posten:
            set_state(jid, expiry_mail=True)           # vor dem Senden
        posten.sort(key=lambda x: x[2])
        knapp = posten[0][2]
        # Gleicher Dateiname mehrfach = mehrere Renders derselben Quelle.
        # Das sind echte, getrennte Eintraege in der Library, aber als Liste
        # gelesen wirkt es wie ein Fehler. Also zusammenfassen mit Anzahl.
        # Ueber die GANZE Liste gruppieren, nicht nur nebeneinanderliegende
        # Eintraege - sonst steht derselbe Dateiname mehrfach da, sobald ein
        # anderes Video dazwischenliegt.
        _grp = {}
        for _j, n, h in posten:
            if n in _grp:
                _grp[n][1] += 1
                _grp[n][2] = min(_grp[n][2], h)
            else:
                _grp[n] = [n, 1, h]
        namen = sorted(_grp.values(), key=lambda x: x[2])
        # Deckel: bei 100 ablaufenden Videos will niemand 100 Zeilen lesen.
        # Die ersten zehn stehen da, der Rest wird gezaehlt.
        _zeig = namen[:10]
        liste = '\n'.join(
            f'  - {n}' + (f' ({c} versions)' if c > 1 else '') + f' - {h}h left'
            for n, c, h in _zeig)
        if len(namen) > len(_zeig):
            _rest = sum(c for _n, c, _h in namen[len(_zeig):])
            liste += f'\n  - and {_rest} more'
        if len(posten) == 1:
            zeile = f'"{posten[0][1]}" in your DouchkoVE library will be'
            rest = f' deleted in about {knapp} hours.'
        else:
            zeile = f'{len(posten)} videos in your DouchkoVE library will be'
            rest = (f' deleted soon, the first one in about {knapp} hours:\n\n'
                    f'{liste}')
        betreff = ('Your video will be deleted soon' if len(posten) == 1
                   else f'{len(posten)} videos will be deleted soon')
        try:
            _send_mail(u['email'], betreff,
                       f'Hi{" " + u["name"] if u["name"] else ""},\n\n'
                       f'{zeile}{rest}\n\n'
                       f'Files are removed automatically after '
                       f'{RETENTION_DAYS:.0f} days.\n\n'
                       f'Download them here while they last:\n{base}/app#library\n\n'
                       f'DouchkoVE')
            print(f'Ablauf-Mail: {len(posten)} Video(s) an User {uid}')
        except Exception as e:
            print(f'Ablauf-Mail fehlgeschlagen (User {uid}): {type(e).__name__}: {e}')

def _missbrauch_pruefen():
    """v204-sec: Bis v203 gab es Missbrauchs-Zahlen nur auf Nachfrage im Panel,
    und sie lebten im Prozessspeicher - jeder Deploy loeschte sie. Damit fiel
    NIE etwas von selbst auf. Diese Pruefung laeuft stuendlich gegen die
    Chronik und meldet ins Panel. Bewusst grosszuegige Schwellen: eine Meldung,
    die jede Woche ohne Grund kommt, liest nach einem Monat niemand mehr."""
    seit = int(time.time()) - 3600
    con = _db()
    try:
        def zahl(q, *p):
            r = con.execute(q, p).fetchone()
            return int(r[0] if r else 0)
        fehl = zahl("SELECT COUNT(*) FROM security_events WHERE aktion = "
                    "'login_fehl' AND ts > ?", seit)
        konten = zahl("SELECT COUNT(DISTINCT wer) FROM security_events WHERE "
                      "aktion = 'login_fehl' AND ts > ?", seit)
        adm = zahl("SELECT COUNT(*) FROM security_events WHERE aktion = "
                   "'admin_fehlversuch' AND ts > ?", seit)
        neu_konten = zahl("SELECT COUNT(*) FROM users WHERE created_at > ?", seit)
        renders = zahl("SELECT COUNT(*) FROM ledger WHERE grund LIKE 'Render %' "
                       "AND created_at > ?", seit)
    finally:
        con.close()
    if fehl >= 50 or konten >= 10:
        _notify_admin('missbrauch:login', 'Auffaellig viele Fehl-Logins',
                      f'{fehl} Fehlversuche auf {konten} Konten in der letzten '
                      f'Stunde. Sieht nach Durchprobieren aus.', mail=False)
    if adm >= 20:
        _notify_admin('missbrauch:admin', 'Admin-Key wird durchprobiert',
                      f'{adm} falsche Admin-Keys in der letzten Stunde.',
                      mail=False)
    if neu_konten >= 30:
        _notify_admin('missbrauch:reg', 'Auffaellig viele Registrierungen',
                      f'{neu_konten} neue Konten in der letzten Stunde.',
                      mail=False)
    if renders >= 60:
        _notify_admin('missbrauch:render', 'Auffaellig viele Renders',
                      f'{renders} Renders in der letzten Stunde.', mail=False)


def _cleanup_worker():
    """v80g: Alte Job-Verzeichnisse loeschen. Standard 7 Tage, ueber
    DVE_RETENTION_DAYS ueberschreibbar. Laeuft stuendlich.
    v80x: macht nebenbei den taeglichen users.db-Snapshot."""
    import time as _t
    retention = RETENTION_DAYS
    while True:
        _HEARTBEAT['cleanup'] = time.time()          # v130: Liveness-Beweis
        _backup_users_db()
        # v230z: Und wenn ueberhaupt nichts mehr gesichert wird, faellt das
        # ohne diese Zeile niemandem auf - die Gegenprobe oben laeuft ja nur,
        # WENN eine Sicherung geschrieben wurde. Einmal pro Programmlauf
        # gemeldet, sonst kaeme stuendlich dieselbe Post.
        try:
            _bdir = os.path.join(DATA, 'backups')
            _snaps = sorted(f for f in os.listdir(_bdir)
                            if f.startswith('users_') and f.endswith('.db'))
            _alter = (time.time() - os.path.getmtime(os.path.join(_bdir, _snaps[-1]))
                      ) / 3600.0 if _snaps else 1e9
            if _alter > 26 and not _EINMAL.get('backup_alt'):
                _EINMAL['backup_alt'] = True
                _notify_admin('backup_alt', 'Seit ueber einem Tag keine Sicherung',
                              f'Die neueste Sicherung ist {_alter:.0f} Stunden alt'
                              if _snaps else 'Es gibt ueberhaupt keine Sicherung.',
                              mail=True)
        except Exception:
            pass
        try:
            _sec_event_purge()               # v204-sec: Chronik begrenzen
            _trichter_purge()                # v208: Trichter begrenzen
            _missbrauch_pruefen()            # v204-sec: auffaellige Muster melden
        except Exception as e:
            print(f'Missbrauchs-Pruefung uebersprungen: {type(e).__name__}: {e}')
        try:
            _credit_expiry_sweep()           # v125: Verfall buchen + Warn-Mails
        except Exception as e:
            print(f'Verfall-Sweep uebersprungen: {type(e).__name__}: {e}')
        try:
            cutoff = _t.time() - retention * 86400
            _abl = {}                        # v194b: uid -> ablaufende Videos
            _akt = {}                        # v194c: uid -> Sekunden seit Job
            if os.path.isdir(JOBS_DIR):
                for jid in os.listdir(JOBS_DIR):
                    d = os.path.join(JOBS_DIR, jid)
                    if not os.path.isdir(d):
                        continue
                    try:
                        mtime = os.path.getmtime(d)
                    except Exception:
                        continue
                    if mtime < cutoff:
                        shutil.rmtree(d, ignore_errors=True)
                        JOBS.pop(jid, None)
                        print(f"Cleanup: Job {jid} nach {retention:.0f}d entfernt")
                        continue
                    # v124 Ablauf-Mail: laeuft ein fertiges Video in < 48h ab,
                    # einmalig erinnern (Service-Mail: die Datei wird real
                    # geloescht). Rueckkehr-Trigger, nichts erfunden.
                    # v194b: nur SAMMELN - verschickt wird gebuendelt, nachdem
                    # alle Jobs durchgesehen sind.
                    try:
                        _j194 = JOBS.get(jid)
                        if _j194 and _j194.get('user_id'):
                            _u194 = _j194['user_id']
                            _akt[_u194] = min(_akt.get(_u194, 1e9),
                                              _t.time() - mtime)
                        _expiry_sammeln(jid, d, mtime, cutoff, _abl)
                    except Exception:
                        pass
                    # ProRes-MOVs sind ~90MB - frueher raus als die MP4s
                    # (Standard 48h, DVE_MOV_HOURS). Die MP4-Vorschau bleibt.
                    mov = os.path.join(d, 'fertig.mov')
                    mov_h = float(os.environ.get('DVE_MOV_HOURS', '48'))
                    if os.path.isfile(mov) and \
                            os.path.getmtime(mov) < _t.time() - mov_h * 3600:
                        try:
                            os.remove(mov)
                            print(f"Cleanup: MOV {jid} nach {mov_h:.0f}h entfernt")
                        except OSError:
                            pass
            if _abl:
                try:
                    _expiry_mails(_abl, _akt)
                except Exception as e:
                    print(f'Ablauf-Mails uebersprungen: {type(e).__name__}: {e}')
            # v88b: Transkript-Cache aufraeumen (Dateien > 30 Tage). Winzig,
            # aber soll nicht ewig wachsen.
            tcut = _t.time() - 30 * 86400
            if os.path.isdir(_TCACHE):
                for fn in os.listdir(_TCACHE):
                    fp = os.path.join(_TCACHE, fn)
                    try:
                        if os.path.isfile(fp) and os.path.getmtime(fp) < tcut:
                            os.remove(fp)
                    except OSError:
                        pass
        except Exception as e:
            print(f"Cleanup-Fehler: {type(e).__name__}: {e}")
        _t.sleep(3600)


def _restore_jobs():
    """v80u: Job-Persistenz. Nach Container-Neustart JOBS aus den
    state.json-Dateien wieder aufbauen. Unterbrochene Renders (wartet/laeuft)
    kommen zurueck in die Queue - fuer den User sieht es aus, als waere
    nichts passiert. Fertige Jobs bleiben abrufbar (Video/Momente/Editor)."""
    restored = requeued = 0
    if not os.path.isdir(JOBS_DIR):
        return
    for jid in os.listdir(JOBS_DIR):
        d = os.path.join(JOBS_DIR, jid)
        sp = os.path.join(d, 'state.json')
        if not os.path.isfile(sp):
            continue
        try:
            st = json.load(open(sp, encoding='utf-8'))
        except Exception:
            continue
        # Motion-Jobs haben kein Quellvideo - eigener Pfad (motion.json liegt im
        # Job-Ordner). Sonst braucht ein Job ein 'quelle.*' zum Wieder-Rendern.
        if st.get('kind') == 'motion':
            mp = os.path.join(d, 'motion.json')
            if os.path.exists(mp):
                try:
                    st['motion'] = json.load(open(mp, encoding='utf-8'))
                except Exception:
                    st.setdefault('motion', {})
            st.setdefault('id', jid)
            JOBS[jid] = st
            restored += 1
            if st.get('status') in ('wartet', 'laeuft'):
                st['status'] = 'wartet'
                st['progress'] = 0.0
                st['phase'] = 'Queued (restored after restart) …'
                MQUEUE.put(jid)
                requeued += 1
            continue
        src = None
        for f in os.listdir(d):
            if f.startswith('quelle.'):
                src = os.path.join(d, f)
                break
        if not src:
            continue
        st['input'] = src
        st.setdefault('code', '')
        st.setdefault('id', jid)
        JOBS[jid] = st
        restored += 1
        if st.get('status') in ('wartet', 'laeuft'):
            st['status'] = 'wartet'
            st['progress'] = 0.0
            st['phase'] = 'Queued (restored after restart) …'
            q_put(jid)
            requeued += 1
    if restored:
        print(f"Job-Restore: {restored} Jobs geladen, {requeued} neu eingereiht")


# v129: Globaler Job-Timeout. Ein Job gilt als HAENGEND, wenn er im Status
# 'wartet' ODER 'laeuft' steht und sich sein Fortschritt (status/progress/phase)
# ueber JOB_STUCK Sekunden NICHT mehr aendert. Deckt drei Faelle, die der alte
# 45-Min-Waechter NICHT abfing: (1) 'wartet'-Jobs wurden nie getimt, (2) ein nach
# Neustart wiederhergestellter 'laeuft'-Job hat KEINEN lebenden Prozess mehr -
# es lief also keine Fehler-Schleife, die ihn je beendet haette (Zombie), (3) der
# Timer lag nur im RAM und wurde bei jedem Neustart genullt. Fortschritt-Finger-
# abdruck statt reiner Laufzeit -> ein gesund rechnender Render (Progress zaehlt
# hoch) wird nie faelschlich gekillt, ein eingefrorener schon.
JOB_STUCK_SECONDS = float(os.environ.get('DVE_JOB_TIMEOUT', str(40 * 60)))


def _reap_stuck_job(jid, why=''):
    """Einen haengenden Job HART beenden: evtl. Prozess killen, Status auf
    'fehler' setzen UND erstatten - unabhaengig davon, ob noch ein Prozess lebt
    (Zombie-sicher). Idempotent: _maybe_refund erstattet nur eine offene, noch
    nicht gelieferte Reservierung; ein zweites set_state('fehler') schadet nicht."""
    j = JOBS.get(jid) or {}
    pid = j.get('pid')
    if pid:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (OSError, ValueError):
            pass
    set_state(jid, status='fehler', progress=0, phase='Timed out',
              msg='This render timed out and was stopped automatically. '
                  'Your credits were refunded.', wd_fp=None, wd_since=None)
    try:
        _maybe_refund(jid)
    except Exception as e:
        print(f'Reap-Refund {jid}: {e}')
    if why:
        # v147: ebenfalls nur ins Panel - ein Timeout IST ein Render-Fehler.
        _notify_admin(f'timeout:{jid}', 'Job automatisch beendet (Timeout)', why,
                      mail=False)
    return True


def _watchdog_worker():
    """Betriebs-Wachhund, alle 2 Minuten: (a) alle ~10 Min Platte knapp -> Mail,
    (b) haengende Jobs (kein Fortschritt seit JOB_STUCK Sekunden) HART beenden +
    erstatten (siehe _reap_stuck_job). In-Memory-Fingerabdruck je Job; sobald
    sich Status/Progress/Phase aendert, laeuft die Uhr neu."""
    stuck = {}            # jid -> (fingerprint, seit_ts)
    disk_every = 5        # ~alle 10 Minuten (bei 120s Takt)
    tick = 0
    while True:
        time.sleep(120)
        tick += 1
        _HEARTBEAT['watchdog'] = time.time()          # v130: Liveness-Beweis
        try:
            if tick % disk_every == 0:
                free_gb = shutil.disk_usage(DATA).free / 1e9
                if free_gb < 2.0:
                    _notify_admin('disk', 'Speicher knapp auf douchko.eu',
                                  f'Nur noch {free_gb:.1f} GB frei unter {DATA}.\n'
                                  f'Cleanup laeuft, reicht aber offenbar nicht.')
                # v222 DER STILLE DEPLOY-STOPP. Der Server lief monatelang auf
                # v213, waehrend die Arbeit weiterging - und NICHTS hat es
                # gemeldet: autodeploy.sh schreibt nur bei einem GESCHEITERTEN
                # Versuch ins Panel. Bleibt der Timer stehen, haengt ein Build
                # im flock oder scheitert `git fetch`, sieht es genauso aus wie
                # "es gibt nichts Neues" - stille Funkstille. Der Watchdog
                # meldet deshalb jetzt selbst, wenn der laufende Stand alt ist.
                # Ein Deckel je Woche, damit die Meldung nicht zur Tapete wird.
                # v225c ZWEI VERSCHIEDENE LAGEN, ZWEI VERSCHIEDENE MELDUNGEN.
                # Bis v225b galt "kein Stempel" als dasselbe wie "Stand ist
                # 20 Tage alt" - und weil der Stempel wegen eines Pfadfehlers
                # NIE ankam, mailte der Wachhund taeglich einen Stillstand, den
                # es nicht gab. Ein grundloser Alarm kostet genauso viel wie ein
                # verpasster: nach der zweiten Mail schaut niemand mehr hin.
                #   Stand messbar alt   -> echter Befund, taeglich erlaubt.
                #   Kein Stempel        -> "ich WEISS es nicht". Genau EINMAL
                #                          je Programmlauf, kein Dauerfeuer.
                try:
                    _dp = _deploy_info()
                    _al = _dp.get('alter_tage')
                    if _al is not None and _al > 7:
                        _notify_admin(
                            # Tagesschluessel: der Stunden-Deckel von
                            # _notify_admin ergaebe hier 24 Mails am Tag. Ein
                            # Betriebsstillstand darf gemeldet werden, aber
                            # einmal taeglich reicht - sonst ist die Meldung
                            # nach zwei Tagen Tapete (v194b-Lehre).
                            'deploy_alt-' + time.strftime('%Y-%m-%d'),
                            'Seit Tagen kein Deploy - laeuft der Auto-Deploy noch?',
                            (f'Der laufende Stand ist {_al:.0f} Tage alt.\n'
                             f"Branch: {_dp.get('branch') or 'unbekannt'}\n"
                             f"Commit: {_dp.get('commit') or 'unbekannt'}\n\n"
                             'Wurde seitdem gepusht, greift der Auto-Deploy '
                             'nicht. Auf dem Server pruefen:\n'
                             '  systemctl status douchko-deploy.timer\n'
                             '  cd /opt/douchko && git status && bash update.sh\n\n'
                             'Bis dahin gehen KEINE Aenderungen live - und '
                             'jedes Kundenvideo wird mit dem alten Stand '
                             'gerendert.'))
                    elif _al is None and not globals().get('_STEMPEL_GEMELDET'):
                        globals()['_STEMPEL_GEMELDET'] = True
                        _notify_admin(
                            'deploy_stempel', 'Kein Build-Stempel - Stand unbekannt',
                            ('Dieser Container traegt keinen Build-Stempel, der '
                             'laufende Stand ist damit nicht feststellbar (auch '
                             'nicht in den Video-Metadaten).\n\n'
                             'Das ist KEIN Stillstand: bis v225b lag der Stempel '
                             'auf dem Host, der Container hat ihn nie gesehen. '
                             'Mit dem naechsten Deploy wird er ins Image gebaut '
                             'und diese Meldung verschwindet von selbst.\n\n'
                             'Kommt sie danach wieder, hat der Deploy nicht '
                             'gegriffen.'))
                except Exception:
                    pass
                # v226a EIN GESCHEITERTER DEPLOY WAR STUMM. `autodeploy.sh`
                # und `update.sh` schreiben ihren Befund per sqlite DIREKT in
                # die alerts-Tabelle - sie koennen `_notify_admin` nicht
                # aufrufen, also ging nie eine Mail raus. Der eine Fall, in
                # dem gar nichts mehr live geht, war damit genau der Fall, von
                # dem Ismet nichts erfuhr (er schaut nicht stuendlich ins
                # Panel). Der Watchdog holt das nach: ungemailte Deploy-Alarme
                # aus den letzten 24 h gehen als EINE Mail raus und werden
                # danach als gemailt markiert.
                try:
                    _con_d = _db()
                    _offen = _con_d.execute(
                        "SELECT id, betreff, text FROM alerts WHERE "
                        "schluessel IN ('deploy','deploy_gate') AND gemailt=0 "
                        "AND created_at > ? ORDER BY id DESC LIMIT 5",
                        (int(time.time()) - 86400,)).fetchall()
                    if _offen:
                        _txt = '\n\n'.join(
                            f"{r['betreff']}\n{str(r['text'])[:900]}"
                            for r in _offen)
                        if _notify_admin(
                                'deploy_fehler-' + time.strftime('%Y-%m-%d'),
                                'Deploy ist gescheitert - es geht nichts live',
                                _txt + '\n\nDie laufende Fassung ist '
                                'unveraendert. Im Panel unter Alerts steht '
                                'der vollstaendige Befund.'):
                            _con_d.executemany(
                                'UPDATE alerts SET gemailt=1 WHERE id=?',
                                [(r['id'],) for r in _offen])
                            _con_d.commit()
                    _con_d.close()
                except Exception:
                    pass
            # v197 Skalierungs-Signal. Der Server rendert mit EINEM Worker auf
            # EINER Maschine. Das ist bewusst so (ein Render zieht CPU und RAM;
            # zwei parallele Jobs machen beide langsamer, nicht die Summe
            # schneller). Nur: bisher hat niemand gemerkt, WANN es eng wird -
            # der Kunde wartet, im Panel steht nichts. Steht die Schlange
            # dauerhaft voll, ist das die Ansage "zweite Maschine oder
            # DVE_WORKERS hoch". Deckel: 1 Meldung/Stunde (_notify_admin).
            if QUEUE.qsize() >= QUEUE_WARN:
                _notify_admin('queue', 'Render-Schlange laeuft voll',
                              f'{QUEUE.qsize()} Caption-Jobs warten '
                              f'(Grenze {QUEUE_WARN}), {WORKERS} Worker.\n'
                              f'Kunden warten entsprechend laenger. Mehr Worker '
                              f'per DVE_WORKERS, mehr Durchsatz nur mit mehr '
                              f'Maschine.')
            now = time.time()
            with LOCK:
                items = [(jid, j.get('status'), round(j.get('progress') or 0, 3),
                          j.get('phase')) for jid, j in JOBS.items()]
            # v230g EIN JOB, DER BRAV IN DER SCHLANGE STEHT, HAENGT NICHT.
            # Der Fingerabdruck ist (Status, Fortschritt, Phase); ein
            # wartender Job hat konstant ('wartet', 0.0, 'Queued …') - der
            # Warteschlangenplatz landet nur in der ANTWORT von /api/status,
            # nie im Job-Zustand. Nach 40 Minuten reinen WARTENS wurde er
            # deshalb als haengend abgeraeumt: Status 'fehler', Meldung
            # „This render timed out", und das fertige Video verschwand
            # spaeter aus der Bibliothek. Genau der Fall, der bei voller
            # Schlange eintritt - also wenn viel los ist. Die Uhr laeuft
            # jetzt erst, wenn der Job wirklich dran ist.
            _in_schlange = set()
            try:
                _in_schlange = {e[-1] for e in list(getattr(QUEUE, 'queue', []))
                                if isinstance(e, tuple)} | \
                               {e for e in list(getattr(MQUEUE, 'queue', []))
                                if isinstance(e, str)}
            except Exception:
                _in_schlange = set()
            live = set()
            for jid, stt, prog, phase in items:
                if stt not in ('wartet', 'laeuft'):
                    continue
                if stt == 'wartet' and jid in _in_schlange:
                    stuck.pop(jid, None)      # wartet regulaer -> Uhr aus
                    live.add(jid)
                    continue
                live.add(jid)
                fp = (stt, prog, phase)
                prev = stuck.get(jid)
                if prev and prev[0] == fp:
                    if now - prev[1] > JOB_STUCK_SECONDS:
                        _reap_stuck_job(
                            jid, f'Job {jid} ohne Fortschritt seit '
                                 f'{(now - prev[1]) / 60:.0f} Min (Status {stt}, '
                                 f'Phase „{phase}") -> beendet + erstattet.')
                        stuck.pop(jid, None)
                else:
                    stuck[jid] = (fp, now)          # neu gesehen / Fortschritt -> Uhr neu
            for jid in [k for k in stuck if k not in live]:
                stuck.pop(jid, None)                # erledigte Jobs vergessen
        except Exception as e:
            print(f'Watchdog-Fehler: {e}')


_restore_jobs()
# v206: Herzschlag beim Start setzen. Der Wachhund meldet sich erst nach
# seinem ersten Schlaf (120 s) - ohne diese Zeile stuende auf der Startseite
# nach JEDEM Deploy zwei Minuten lang "Wachhund meldet sich nicht", also ein
# roter Alarm ohne Anlass. Eine Ampel, die regelmaessig grundlos rot ist,
# schaut nach einer Woche niemand mehr an.
_HEARTBEAT['cleanup'] = _HEARTBEAT['watchdog'] = time.time()
threading.Thread(target=_cleanup_worker, daemon=True).start()
threading.Thread(target=_watchdog_worker, daemon=True).start()

for _ in range(WORKERS):
    threading.Thread(target=worker, daemon=True).start()
threading.Thread(target=motion_worker, daemon=True).start()


# ================================================================
# v142 CACHING. Drei Ebenen, bewusst getrennt - jede loest ein anderes
# Problem, und keine darf frische Daten verstecken:
#   (1) Datei-Cache im Prozess: index.html ist ~500 KB und wurde bei JEDEM
#       Aufruf neu von Platte gelesen und dekodiert. Jetzt einmal, gehalten,
#       ueber (mtime, groesse) invalidiert - ein Deploy tauscht die Datei und
#       wird sofort gesehen, ohne Neustart und ohne manuelles Leeren.
#   (2) ETag + 304: Cache-Control bleibt 'no-cache' (der Browser MUSS nach
#       jedem Deploy nachfragen, sonst laeuft altes Frontend gegen neuen
#       Server). Neu ist die ANTWORT darauf: unveraendert heisst jetzt ~200
#       Byte 304 statt einer halben Megabyte HTML.
#   (3) TTL-Cache fuer teure Aggregate (das Admin-Panel pollt im Sekunden-
#       takt). Kurz genug, dass niemand veraltete Zahlen sieht, lang genug,
#       dass das Panel die Datenbank nicht dauerhaft beschaeftigt.
# NICHT gecacht: alles mit Geld oder Kontostand (/api/me, Ledger, Checkout,
# Webhook). Dort ist ein veralteter Wert schlimmer als jede Rechenzeit.
# ================================================================
_FILE_CACHE = {}                 # pfad -> (stempel, text, etag)
_FILE_CACHE_LOCK = threading.Lock()


def _file_cached(path):
    """Datei-Inhalt + ETag aus dem Prozess-Cache, invalidiert ueber
    (mtime_ns, groesse)."""
    stt = os.stat(path)
    stamp = (stt.st_mtime_ns, stt.st_size)
    with _FILE_CACHE_LOCK:
        hit = _FILE_CACHE.get(path)
        if hit and hit[0] == stamp:
            return hit[1], hit[2]
    text = open(path, encoding='utf-8').read()
    etag = '"' + hashlib.sha1(text.encode('utf-8')).hexdigest()[:24] + '"'
    with _FILE_CACHE_LOCK:
        _FILE_CACHE[path] = (stamp, text, etag)
    return text, etag


def _etag_304(request, etag, cache_control):
    """Antwortet mit 304, wenn der Browser diese Version schon hat."""
    inm = (request.headers.get('if-none-match') or '') if request else ''
    if inm and etag in [t.strip() for t in inm.split(',')]:
        return Response(status_code=304, headers={'ETag': etag,
                                                  'Cache-Control': cache_control})
    return None


_TTL_CACHE = {}                  # key -> (ablauf, wert)
_TTL_LOCK = threading.Lock()


def _ttl_cached(key, ttl, build):
    """Kleiner TTL-Cache fuer teure, unkritische Aggregate. build() laeuft nur,
    wenn der Eintrag fehlt oder abgelaufen ist. Bewusst simpel: kein
    Hintergrund-Refresh, kein Stampede-Schutz - bei einem Admin-Panel mit einem
    einzigen Nutzer waere beides Ballast."""
    now = time.time()
    with _TTL_LOCK:
        hit = _TTL_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]
    val = build()
    with _TTL_LOCK:
        _TTL_CACHE[key] = (now + ttl, val)
    return val


def _ttl_drop(prefix=''):
    """Cache-Eintraege verwerfen (nach schreibenden Aktionen), damit das Panel
    nie die Zahlen von VOR der eigenen Aenderung zeigt."""
    with _TTL_LOCK:
        for k in [k for k in _TTL_CACHE if k.startswith(prefix)]:
            _TTL_CACHE.pop(k, None)


# ---------------------------------------------------------------- Endpunkte
def _page(name, request=None):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        raise HTTPException(404)
    # v83a: HTML nie cachen. Ohne Cache-Control cachen iOS/Safari heuristisch
    # tagelang - nach jedem Deploy lief bei Nutzern sonst das ALTE Frontend
    # gegen den neuen Server. no-cache = Browser fragt jedes Mal nach
    # (bekommt 200 mit frischem Inhalt), Assets/Videos bleiben unberuehrt.
    # v142: die Nachfrage wird jetzt mit ETag beantwortet.
    _cc = 'no-cache, must-revalidate'
    text, etag = _file_cached(p)
    hit = _etag_304(request, etag, _cc)
    if hit is not None:
        return hit
    return HTMLResponse(text, headers={'Cache-Control': _cc, 'ETag': etag})


# v80m: Rate-Limit gegen Spam-Registrierungen (in-memory, pro IP)
_REG_ATTEMPTS = {}       # ip -> [timestamps]


def _client_ip(request):
    """v127-sec: echte Client-IP fuer Rate-Limits/Demo-Quota.
    uvicorn laeuft mit --forwarded-allow-ips '*' und traut damit dem LINKSSTEN
    X-Forwarded-For-Eintrag - der ist voll client-gesetzt und damit spoofbar
    (jede Anfrage eine neue Fake-IP -> Login-Brute-Force und Demo-Quota liefen
    ins Leere). Caddy ist der EINZIGE Proxy vor der App und haengt die real
    gesehene Peer-IP RECHTS an die Kette. Wir nehmen deshalb den LETZTEN
    Eintrag - den kann der Client nicht faelschen. Ohne XFF: direkte Peer-IP.
    (Sollte spaeter ein CDN vor Caddy kommen, hier den vorletzten Hop nehmen.)"""
    xff = request.headers.get('x-forwarded-for', '')
    if xff:
        parts = [p.strip() for p in xff.split(',') if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else 'unknown'


def _rate_limit_ok(ip, window_sec=3600, max_attempts=5, bucket='reg'):
    """Rate-Limit pro IP und Aktion (getrennte Buckets: reg/login/reset).
    Reicht fuer echte Nutzer, stoppt automatisierten Spam + Passwort-
    Brute-Force. In-Memory (ein Web-Prozess)."""
    key = f'{bucket}:{ip}'
    now = time.time()
    xs = [t for t in _REG_ATTEMPTS.get(key, []) if now - t < window_sec]
    xs.append(now)
    _REG_ATTEMPTS[key] = xs[-max_attempts:]
    return len(xs) <= max_attempts


@app.post('/api/register')
def api_register(request: Request, response: Response,
                 email: str = Form(...), password: str = Form(...),
                 name: str = Form(''), ref: str = Form('')):
    """v80h: Neuer Account. v98: Willkommens-Guthaben kommt erst mit der
    E-Mail-Bestaetigung (_grant_welcome), nicht mehr hier. v124: optionaler
    Einladungscode (ref), Bonus fliesst erst nach der Bestaetigung."""
    # Rate-Limit gegen Spam
    ip = _client_ip(request)
    if not _rate_limit_ok(ip):
        raise HTTPException(429, 'Too many sign-up attempts. Please try again in an hour.')
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not _valid_email(email):
        raise HTTPException(400, 'Please enter a valid email address.')
    # v127-sec: Wegwerf-Mail-Domains beim Sign-up abweisen. Bisher wurde nur der
    # Referral-Bonus fuer solche Adressen verweigert; der Free-Tier (Welcome +
    # Monats-Kredit) liess sich per Temp-Mail-Ring dennoch farmen. Bewusst nur
    # bekannte Wegwerf-Domains - echte Anbieter bleiben unberuehrt.
    if _is_disposable_email(email):
        raise HTTPException(400, 'Please use a permanent email address '
                                 '(disposable inboxes are not supported).')
    if not _valid_username(name):
        raise HTTPException(400, 'Please pick a username (3-24 characters, '
                                 'letters, numbers, spaces, . _ -).')
    if not _valid_pw(password):
        raise HTTPException(400, 'Password needs at least 8 characters.')
    uid, err = _create_user(email, password, name)
    if err:
        raise HTTPException(409, err)
    # v124: Einladungscode zuordnen (still, ungueltige Codes brechen nichts).
    _ref = re.sub(r'[^A-Z2-9]', '', (ref or '').strip().upper())[:8]
    if _ref:
        try:
            con = _db()
            r = con.execute("SELECT id FROM users WHERE ref_code = ?", (_ref,)).fetchone()
            if r and r['id'] != uid:
                con.execute("UPDATE users SET referred_by = ? WHERE id = ?", (r['id'], uid))
                con.commit()
            con.close()
        except Exception:
            pass
    # v208: Hier bekommt der anonyme Besucher zum ersten Mal eine Konto-Nummer.
    # Nur ueber diese eine Zeile laesst sich spaeter sagen, aus WELCHER Quelle
    # ein zahlender Kunde kam - der Kauf selbst kommt per Stripe-Webhook ohne
    # Browser an und hat keine Herkunft mehr.
    _trichter('konto', request, user_id=uid)
    _send_verify_mail(uid, email, name.strip())        # v80x
    tok, exp = _create_session(uid)
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    u = _find_user_by_id(uid)
    # Frisches Konto: es kann noch keine Support-Antwort geben.
    return {'ok': True, 'email': u['email'], 'name': u['name'],
            'support_neu': 0,                              # v202
            'username': u['name'], 'credits': credits_of(u['balance_sec']),
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified'])}


@app.post('/api/login')
def api_login(request: Request, response: Response, email: str = Form(...),
              password: str = Form(...)):
    """v80h: Login. Gleiche Fehlermeldung fuer 'nicht vorhanden' und 'Passwort
    falsch', damit man E-Mails nicht enumerieren kann."""
    # v92 SECURITY: Rate-Limit gegen Passwort-Brute-Force (20 Versuche / 15 min / IP)
    ip = _client_ip(request)
    if not _rate_limit_ok(ip, window_sec=900, max_attempts=20, bucket='login'):
        raise HTTPException(429, 'Too many login attempts. Please wait a few minutes.')
    email = (email or '').strip().lower()
    row = _find_user_by_email(email)
    if not row:
        # v92-sec: Auch ohne Treffer eine bcrypt-Pruefung fahren, damit die
        # Antwortzeit gleich lang ist - sonst verraet das Timing, welche
        # E-Mails existieren (Login-Text ist bewusst schon identisch).
        _verify_pw(password, _DUMMY_HASH)
        raise HTTPException(401, 'Email or password is wrong.')
    if not _verify_pw(password, row['pw_hash']):
        # v204-sec: Fehlversuche gehoeren in die Chronik. Nur die Konto-ID,
        # nicht das eingegebene Passwort - ein Protokoll, das Geheimnisse
        # mitschreibt, ist selbst das Leck.
        _sec_event('login_fehl', request, wer=f"user:{row['id']}")
        raise HTTPException(401, 'Email or password is wrong.')
    if _row_get(row, 'disabled'):                    # v130: gesperrtes Konto
        _sec_event('login_gesperrt', request, wer=f"user:{row['id']}")
        raise HTTPException(403, 'This account is suspended. Contact support.')
    _sec_event('login_ok', request, wer=f"user:{row['id']}")
    tok, exp = _create_session(row['id'])
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    return {'ok': True, 'email': row['email'], 'name': row['name'],
            'username': row['name'], 'credits': credits_of(row['balance_sec']),
            'balance_sec': row['balance_sec'], 'verified': bool(row['verified'])}


@app.post('/api/logout')
def api_logout(request: Request, response: Response):
    _kill_session(request.cookies.get('dve_session'))
    response.delete_cookie('dve_session', path='/')
    return {'ok': True}


# ------------------------------------------------- v132: Google-OAuth-Login
# Autorisierungs-Code-Flow. Der id_token wird server-zu-server (mit dem
# Client-Secret ueber TLS) direkt bei Google abgeholt - der Kanal ist damit
# authentisch. Zusaetzlich pruefen wir aud/iss/exp und email_verified als
# Guertel-und-Hosentraeger. Alles inert, solange GOOGLE_OK False ist.
_GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
_GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
_GOOGLE_ISS = ('accounts.google.com', 'https://accounts.google.com')


def _google_redirect_uri():
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    return base + '/api/auth/google/callback'


def _decode_jwt_payload(token):
    """Nur den Payload-Teil eines JWT dekodieren (KEINE Signaturpruefung -
    die entfaellt hier bewusst, weil der Token gerade eben ueber den mit dem
    Client-Secret authentisierten TLS-Kanal direkt von Google kam)."""
    import base64
    try:
        p = token.split('.')[1]
        p += '=' * (-len(p) % 4)                       # Base64url-Padding
        return json.loads(base64.urlsafe_b64decode(p.encode()))
    except Exception:
        return None


def _upsert_google_user(sub, email, name, ref=''):
    """Google-Nutzer finden oder anlegen. Reihenfolge: erst ueber die stabile
    google_sub, dann ueber die E-Mail (verknuepft ein bestehendes Passwort-
    Konto). Neu angelegte Konten sind SOFORT verified=1 (Google hat die Mail
    bestaetigt) und bekommen das Willkommens-Guthaben. Rueckgabe: (uid, is_new)."""
    email = (email or '').strip().lower()
    _nachtrag = []            # Chronik-Zeilen, erst NACH con.close() schreiben
    con = _db()
    try:
        row = con.execute("SELECT id, disabled FROM users WHERE google_sub = ?",
                          (sub,)).fetchone()
        if not row:
            row = con.execute("SELECT id, disabled, verified FROM users "
                              "WHERE email = ?", (email,)).fetchone()
            if row:
                # v203-sec KONTO-VORBELEGUNG. Hier wurde bisher STILL verknuepft,
                # egal ob das vorhandene Konto seine Adresse je bestaetigt hatte -
                # und das Passwort dieses Kontos galt danach unveraendert weiter.
                # Die Registrierung verlangt keine Bestaetigung, jeder konnte also
                # ein Konto auf eine FREMDE Adresse anlegen und warten. Meldete
                # sich der echte Inhaber spaeter mit Google an, landete er in genau
                # diesem Konto, und beide teilten es sich: der Angreifer saehe
                # Library, Transkripte und Original-Uploads und koennte gekaufte
                # Credits verbrauchen, ohne dass irgendetwas auffaellt.
                # (Am Code nachgestellt: nach der Verknuepfung war _verify_pw mit
                # dem Angreifer-Passwort weiterhin True.)
                #
                # Google hat die Adresse bewiesen (email_verified wird im Callback
                # geprueft), ein unbestaetigtes Konto hat gar nichts bewiesen.
                # Also uebernimmt Google die Adresse: verknuepfen, aber das alte
                # Passwort unbrauchbar machen und alle Anmeldungen beenden.
                # NICHT loeschen - gehoerte das Konto doch einem echten Kunden,
                # der nur nie bestaetigt hat, behaelt er Bibliothek und Guthaben.
                # Ein Kauf war ohne Bestaetigung ohnehin nicht moeglich.
                _war_unbestaetigt = not _row_get(row, 'verified')
                con.execute("UPDATE users SET google_sub = ? WHERE id = ?",
                            (sub, row['id']))
                if _war_unbestaetigt:
                    con.execute("UPDATE users SET pw_hash = ?, verified = 1 "
                                "WHERE id = ?",
                                (_hash_pw(secrets.token_urlsafe(24)), row['id']))
                    con.execute("DELETE FROM resets WHERE user_id = ?", (row['id'],))
                    con.execute("DELETE FROM verify_tokens WHERE user_id = ?",
                                (row['id'],))
                    print(f'Google-Login uebernimmt unbestaetigtes Konto zu {email}: '
                          f'altes Passwort verworfen, Sitzungen beendet.')
                    # Die Chronik-Zeile wird NACH con.close() geschrieben:
                    # _sec_event oeffnet eine eigene Verbindung, und solange
                    # diese hier die Schreibsperre haelt, blockiert sie sich
                    # selbst ('database is locked'). Ein Protokoll, das
                    # ausgerechnet den interessantesten Vorgang nicht
                    # festhalten kann, ist wertlos.
                    _nachtrag.append(('google_uebernahme', f"user:{row['id']}",
                                      'unbestaetigtes Konto, Passwort entwertet'))
                # In BEIDEN Faellen alle bestehenden Anmeldungen beenden - sass
                # dort jemand anderes, endet das hier.
                con.execute("DELETE FROM sessions WHERE user_id = ?", (row['id'],))
                con.commit()
        if row:
            if _row_get(row, 'disabled'):
                con.close()
                return None, False                     # gesperrt -> kein Login
            return row['id'], False
        # Neu anlegen: passwortlos (unnutzbarer Zufalls-Hash), verified, gsub.
        uname = _google_username(name, email)
        pw_hash = _hash_pw(secrets.token_urlsafe(24))
        cur = con.execute(
            "INSERT INTO users (email, pw_hash, name, balance_sec, created_at, "
            "verified, google_sub) VALUES (?, ?, ?, 0, ?, 1, ?)",
            (email, pw_hash, uname, int(time.time()), sub))
        uid = cur.lastrowid
        # Referral zuordnen (still; ungueltige Codes brechen nichts).
        _ref = re.sub(r'[^A-Z2-9]', '', (ref or '').strip().upper())[:8]
        if _ref:
            r = con.execute("SELECT id FROM users WHERE ref_code = ?", (_ref,)).fetchone()
            if r and r['id'] != uid:
                con.execute("UPDATE users SET referred_by = ? WHERE id = ?",
                            (r['id'], uid))
        con.commit()
        return uid, True
    except sqlite3.IntegrityError:
        # Race: parallel angelegt -> jetzt sicher vorhanden.
        row = con.execute("SELECT id FROM users WHERE google_sub = ? OR email = ?",
                          (sub, email)).fetchone()
        return (row['id'] if row else None), False
    finally:
        con.close()
        # ERST hier: solange con offen ist, haelt sie die Schreibsperre und
        # _sec_event (eigene Verbindung) liefe in 'database is locked'.
        # Im finally, weil jeder Pfad der Funktion vorher zurueckkehrt - eine
        # Zeile hinter dem try/finally waere schlicht nie erreicht worden.
        for _a, _w, _d in _nachtrag:
            _sec_event(_a, wer=_w, detail=_d)


def _google_username(name, email):
    """Anzeigename aus Google ableiten und an unsere Regeln anpassen (3-24,
    erlaubte Zeichen). Faellt auf den E-Mail-Localpart zurueck."""
    cand = (name or '').strip() or (email.split('@')[0] if '@' in email else 'user')
    cand = re.sub(r'[^A-Za-z0-9 ._-]', '', cand).strip()
    cand = re.sub(r'^[^A-Za-z0-9]+', '', cand)[:24].strip()
    if len(cand) < 3:
        cand = (cand + 'user')[:24]
    return cand or 'user'


@app.get('/api/authinfo')
def api_authinfo():
    """Oeffentlich: sagt dem Frontend, ob der Google-Button gezeigt werden
    soll. Gibt NIE Secrets zurueck, nur das Ja/Nein."""
    return {'google': GOOGLE_OK}


@app.get('/api/auth/google/start')
def auth_google_start(request: Request, ref: str = ''):
    """Schritt 1: zu Googles Zustimmungs-Seite umleiten. state-Cookie gegen
    CSRF; optionaler ref-Code wird ueber ein kurzes Cookie durchgereicht."""
    if not GOOGLE_OK:
        return RedirectResponse('/app?autherror=disabled', status_code=302)
    ip = _client_ip(request)
    if not _rate_limit_ok(ip, window_sec=900, max_attempts=30, bucket='goauth'):
        return RedirectResponse('/app?autherror=rate', status_code=302)
    state = secrets.token_urlsafe(24)
    from urllib.parse import urlencode
    url = _GOOGLE_AUTH_URL + '?' + urlencode({
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': _google_redirect_uri(),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account',
    })
    resp = RedirectResponse(url, status_code=302)
    # 10-Min-Cookies, httponly, gleiche Herkunft (lax reicht - Google leitet per GET zurueck).
    resp.set_cookie('dve_oauth_state', state, max_age=600, httponly=True,
                    samesite='lax', secure=True, path='/')
    _refc = re.sub(r'[^A-Za-z2-9]', '', (ref or '').strip().upper())[:8]
    if _refc:
        resp.set_cookie('dve_oauth_ref', _refc, max_age=600, httponly=True,
                        samesite='lax', secure=True, path='/')
    return resp


@app.get('/api/auth/google/callback')
def auth_google_callback(request: Request, code: str = '', state: str = '',
                         error: str = ''):
    """Schritt 2: Code gegen Tokens tauschen, id_token pruefen, ein-/ausloggen."""
    if not GOOGLE_OK:
        return RedirectResponse('/app?autherror=disabled', status_code=302)
    if error or not code:
        return RedirectResponse('/app?autherror=cancel', status_code=302)
    # CSRF: state aus dem Cookie muss zum zurueckgegebenen state passen.
    cookie_state = request.cookies.get('dve_oauth_state', '')
    if not cookie_state or not state or not hmac.compare_digest(cookie_state, state):
        return RedirectResponse('/app?autherror=state', status_code=302)
    ref = request.cookies.get('dve_oauth_ref', '')
    try:
        import requests as _rq
        tok = _rq.post(_GOOGLE_TOKEN_URL, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': _google_redirect_uri(),
            'grant_type': 'authorization_code',
        }, timeout=15)
        if tok.status_code != 200:
            print(f'Google-Token-Tausch fehlgeschlagen: {tok.status_code} {tok.text[:200]}')
            return RedirectResponse('/app?autherror=token', status_code=302)
        idt = tok.json().get('id_token', '')
        claims = _decode_jwt_payload(idt) or {}
    except Exception as e:
        print(f'Google-Callback-Fehler: {type(e).__name__}: {e}')
        return RedirectResponse('/app?autherror=token', status_code=302)
    # Belt-and-suspenders: Zielgruppe, Aussteller, Ablauf, Mail-Bestaetigung.
    if claims.get('aud') != GOOGLE_CLIENT_ID:
        return RedirectResponse('/app?autherror=aud', status_code=302)
    if str(claims.get('iss', '')) not in _GOOGLE_ISS:
        return RedirectResponse('/app?autherror=iss', status_code=302)
    try:
        if int(claims.get('exp', 0)) < int(time.time()):
            return RedirectResponse('/app?autherror=exp', status_code=302)
    except (TypeError, ValueError):
        return RedirectResponse('/app?autherror=exp', status_code=302)
    sub = str(claims.get('sub', '')).strip()
    email = str(claims.get('email', '')).strip().lower()
    ev = claims.get('email_verified')
    email_ok = (ev is True) or (str(ev).lower() == 'true')
    if not sub or not email or not email_ok or not _valid_email(email):
        return RedirectResponse('/app?autherror=email', status_code=302)
    name = claims.get('given_name') or claims.get('name') or ''
    uid, is_new = _upsert_google_user(sub, email, name, ref)
    if not uid:
        return RedirectResponse('/app?autherror=disabled', status_code=302)
    if is_new:
        try:
            _grant_welcome(uid)                        # Mail ist Google-bestaetigt
        except Exception as e:
            print(f'Welcome-Credit (Google) {uid}: {e}')
        try:
            _send_welcome_mail(uid)                    # v133: sofort aktiv
        except Exception as e:
            print(f'Welcome-Mail (Google) {uid}: {e}')
    tok2, _exp = _create_session(uid)
    resp = RedirectResponse('/app/create', status_code=302)
    resp.set_cookie('dve_session', tok2, httponly=True, samesite='lax',
                    secure=True, max_age=SESSION_DAYS * 86400, path='/')
    resp.delete_cookie('dve_oauth_state', path='/')
    resp.delete_cookie('dve_oauth_ref', path='/')
    return resp


@app.get('/api/me')
def api_me(request: Request):
    """Aktuellen Nutzer laden (fuer Auto-Login beim Seiten-Reload)."""
    u = _current_user(request)
    if not u:
        return {'ok': False}
    if _grant_monthly_free(u):
        u = _find_user_by_id(u['id'])          # frisches Guthaben anzeigen
    # v80z: Investment sichtbar machen (Renders) + Rueckkehr-Trigger
    # (Tage bis zum naechsten Gratis-Reset) + Wasserzeichen-Status
    con = _db()
    rc = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id = ? AND "
                     "grund LIKE 'Render %'", (u['id'],)).fetchone()['c']
    # v124 Referral-Stand: wie viele Einladungen wurden schon belohnt.
    ref_used = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id = ? AND "
                           "grund LIKE 'Referral for %'", (u['id'],)).fetchone()['c']
    # v202: ungelesene Support-Antworten fuer den Zaehler in der Navigation.
    # Bewusst HIER und nicht als eigener Endpunkt: /api/me wird ohnehin bei
    # jedem Seitenaufruf geholt, ein zweiter Ruf waere reine Last.
    sup_neu = con.execute(
        "SELECT COUNT(*) c FROM ticket_messages m JOIN tickets t "
        "ON t.id = m.ticket_id WHERE t.user_id = ? AND m.von = 'admin' "
        "AND m.gelesen = 0 AND NOT (t.status = 'closed' AND t.updated_at < ?)",
        (u['id'], int(time.time()) - TICKET_CLOSED_TTL)).fetchone()['c']
    con.close()
    # v124 Stil-Gedaechtnis: eigene Editor-Korrekturen, aus denen die Regie lernt.
    style_prefs = sum(1 for c in _load_corrections()
                      if c.get('user_id') == u['id'])
    # v125: laeuft in den naechsten 30 Tagen etwas ab? (fuer den Billing-Hinweis)
    try:
        _exp_sec, _exp_days = _expiring_info(u['id'], 30)
    except Exception:
        _exp_sec, _exp_days = 0, None
    lt = time.localtime()
    days_in_month = [31, 29 if lt.tm_year % 4 == 0 else 28, 31, 30, 31, 30,
                     31, 31, 30, 31, 30, 31][lt.tm_mon - 1]
    return {'ok': True, 'email': u['email'], 'name': u['name'],
            'support_neu': sup_neu,                        # v202
            'username': u['name'], 'credits': credits_of(u['balance_sec']),
            'created_at': int(u['created_at']),
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified']),
            'google': bool(_row_get(u, 'google_sub')),    # v137a
            'renders': rc, 'purchased': _has_purchased(u['id']),
            'is_owner': str(u['email']).strip().lower() == OWNER_EMAIL,
            'motion_brief': MOTION_BRIEF_OK,   # v101p: Brief->Motion verfuegbar?
            'ref_code': _ensure_ref_code(u['id']),                # v124 Referral
            'ref_used': ref_used, 'ref_cap': REFERRAL_CAP,
            'ref_minutes': REFERRAL_SECONDS // 60,
            'style_prefs': style_prefs,                           # v124 Investment
            'expiring_credits': credits_of(_exp_sec),             # v125 Verfall
            'expiring_days': _exp_days,
            'free_reset_days': days_in_month - lt.tm_mday + 1}


@app.post('/api/forgot_password')
def api_forgot_password(request: Request, email: str = Form(...)):
    """v80w: Reset-Link per Mail. Antwort immer identisch - kein
    E-Mail-Enumeration. Rate-Limit teilt sich den Topf mit Registrierung."""
    ip = _client_ip(request)
    if not _rate_limit_ok(ip):
        raise HTTPException(429, 'Too many attempts. Please try again in an hour.')
    u = _find_user_by_email((email or '').strip().lower())
    if u:
        tok = _create_reset(u['id'])
        base = os.environ.get('DVE_PUBLIC_URL', '').rstrip('/') or \
            str(request.base_url).rstrip('/')
        link = f'{base}/app?reset={tok}'
        try:
            _send_mail(u['email'], 'Reset your DouchkoVE password',
                       f'Hi{" " + u["name"] if u["name"] else ""},\n\n'
                       f'someone (hopefully you) requested a password reset '
                       f'for your DouchkoVE account.\n\n'
                       f'Reset link (valid 30 minutes):\n{link}\n\n'
                       f'If this wasn\'t you, just ignore this email - '
                       f'your password stays unchanged.\n\n- DouchkoVE')
        except Exception as e:
            print(f'Mail-Versand fehlgeschlagen: {type(e).__name__}: {e}')
    return {'ok': True,
            'msg': 'If this email is registered, a reset link is on its way.'}


@app.post('/api/reset_password')
def api_reset_password(response: Response, token: str = Form(...),
                       password: str = Form(...)):
    """v80w: Token einloesen, neues Passwort setzen, direkt einloggen."""
    if not _valid_pw(password):
        raise HTTPException(400, 'Password needs at least 8 characters.')
    uid = _consume_reset(token)
    if not uid:
        raise HTTPException(400, 'This reset link is invalid or has expired. '
                                 'Please request a new one.')
    con = _db()
    con.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
                (_hash_pw(password), uid))
    con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))  # alle raus
    con.commit()
    con.close()
    tok, _ = _create_session(uid)
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    u = _find_user_by_id(uid)
    return {'ok': True, 'email': u['email'], 'name': u['name'],
            'balance_sec': u['balance_sec']}


@app.post('/api/verify_email')
def api_verify_email(token: str = Form(...)):
    """v80x: Verify-Token einloesen."""
    uid = _consume_verify(token)
    if not uid:
        raise HTTPException(400, 'This verification link is invalid or has '
                                 'expired. Request a new one in Account settings.')
    granted = _grant_welcome(uid)
    try:
        _grant_referral(uid)                 # v124: Einladungs-Bonus (beide Seiten)
    except Exception as e:                   # darf die Bestaetigung nie reissen
        print(f'Referral-Grant fehlgeschlagen: {e}')
    try:
        _send_welcome_mail(uid)              # v133: Konto ist jetzt aktiv
    except Exception as e:
        print(f'Welcome-Mail (Verify) fehlgeschlagen: {e}')
    return {'ok': True, 'welcome_granted': granted}


@app.post('/api/resend_verification')
def api_resend_verification(request: Request):
    u = _require_user(request)
    if u['verified']:
        return {'ok': True, 'msg': 'Already verified.'}
    # v230d-sec: der einzige mailversendende Kunden-Endpunkt OHNE Bremse
    # (forgot_password 5/h, support 10/h, ticket-reply 20/h - dieser nichts).
    # Ein einziges unbestaetigtes Konto konnte damit das Sende-Kontingent des
    # Betreibers leerlaufen lassen; danach bekommt KEIN echter Kunde mehr eine
    # Passwort-Reset- oder Kaufbeleg-Mail. Und _send_mail blockiert bis zu
    # 20 s je Aufruf in einem Thread, den sich alle Kunden-Endpunkte teilen.
    # Zwei Riegel: pro Konto (der Angreifer hat immer eins) und pro IP.
    if not _rate_limit_ok(str(u['id']), window_sec=3600, max_attempts=5,
                          bucket='verifymail') \
            or not _rate_limit_ok(_client_ip(request), window_sec=3600,
                                  max_attempts=10, bucket='verifymail-ip'):
        raise HTTPException(429, 'Verification email already sent. Please check '
                                 'your inbox (and spam) and try again later.')
    ok = _send_verify_mail(u['id'], u['email'], u['name'] or '')
    if not ok:
        raise HTTPException(500, 'Could not send the email. Try again later.')
    return {'ok': True, 'msg': 'Verification email sent.'}


# ---------------------------------------------------- v196 Ankuendigungen
def _ann_aktiv():
    """Aktive Ankuendigungen, abgelaufene automatisch aus."""
    now = int(time.time())
    con = _db()
    try:
        rows = con.execute(
            "SELECT id, titel, text, stufe, created_at, bis FROM announcements "
            "WHERE aktiv = 1 AND (bis IS NULL OR bis > ?) "
            "ORDER BY created_at DESC LIMIT 5", (now,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


@app.get('/api/announcements')
def api_announcements():
    """Was der Kunde in der App als Banner sieht. Bewusst OHNE Auth: eine
    Wartungsmeldung muss auch den erreichen, der gerade nicht eingeloggt ist."""
    return {'items': _ann_aktiv()}


@app.post('/api/feedback')
def api_feedback(request: Request, note: int = Form(...), text: str = Form(''),
                 jid: str = Form(''), look: str = Form('')):
    """Bewertung zu einem fertigen Render. Kein Ticket - hier wird nichts
    beantwortet, hier wird gemessen."""
    u = _current_user(request)
    if not u:
        raise HTTPException(403, 'Please sign in first.')
    try:
        note = int(note)
    except (TypeError, ValueError):
        raise HTTPException(400, 'Rating must be a number.')
    if not 1 <= note <= 5:
        raise HTTPException(400, 'Rating must be between 1 and 5.')
    text = (text or '').strip()[:2000]
    jid = (jid or '').strip()[:64]
    look = (look or '').strip()[:32]
    # v230c-sec ZWEI RIEGEL, DIE HIER FEHLTEN.
    # 1) Die Dubletten-Sperre unten haengt am PAAR (user_id, jid) - mit einer
    #    frei erfundenen jid war sie damit wirkungslos: 500 Anfragen ergaben
    #    500 Zeilen. Der Sterne-Durchschnitt im Panel liess sich so auf 1.0
    #    ziehen, und die einzige geschaeftskritische Datenbank vollschreiben.
    #    Bewertet wird jetzt nur der EIGENE Render.
    # 2) Der Nachbar-Endpunkt /api/support hat seit jeher ein Rate-Limit,
    #    dieser hatte keins. Ein Riegel, den nur die halbe Nachbarschaft hat,
    #    ist keiner.
    if not _rate_limit_ok(_client_ip(request), window_sec=3600,
                          max_attempts=30, bucket='feedback'):
        raise HTTPException(429, 'Too many ratings. Please try again later.')
    # _job_owner_ok reicht hier NICHT: es laesst eine unbekannte jid durch
    # (kein Job -> kein Eigentuemer -> True). Genau das war der Angriff.
    if jid and (JOBS.get(jid) or {}).get('user_id') != u['id']:
        raise HTTPException(403, 'Not your video.')
    # Ein Kunde darf zu EINEM Render einmal bewerten - sonst kippt jeder
    # Durchschnitt, sobald jemand den Knopf mehrfach drueckt.
    con = _db()
    try:
        if jid:
            alt = con.execute("SELECT id FROM feedback WHERE user_id = ? AND jid = ?",
                              (u['id'], jid)).fetchone()
            if alt:
                con.execute("UPDATE feedback SET note = ?, text = ?, created_at = ?, "
                            "gelesen = 0 WHERE id = ?",
                            (note, text, int(time.time()), alt['id']))
                con.commit()
                return {'ok': True, 'updated': True}
        con.execute("INSERT INTO feedback (user_id, jid, look, note, text, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (u['id'], jid, look, note, text, int(time.time())))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@app.get('/api/feedback/mine')
def api_feedback_mine(request: Request, jid: str = ''):
    """Hat der Kunde diesen Render schon bewertet? Damit die App nicht
    nochmal fragt und die eigene Note anzeigen kann."""
    u = _current_user(request)
    if not u or not jid:
        return {'note': None}
    con = _db()
    try:
        r = con.execute("SELECT note, text FROM feedback WHERE user_id = ? AND jid = ?",
                        (u['id'], jid.strip()[:64])).fetchone()
        return {'note': r['note'], 'text': r['text']} if r else {'note': None}
    finally:
        con.close()


@app.post('/api/support')
def api_support(request: Request, subject: str = Form(''),
                message: str = Form(...)):
    """v133c: Support-Ticket aus dem Formular. Legt das Ticket an, mailt es an
    den Betreiber (Reply-To = Kundenadresse -> direkt aus dem Postfach
    antworten) und schickt dem Kunden eine Eingangsbestaetigung ueber noreply.
    Nur eingeloggt; rate-limitiert gegen Spam."""
    u = _require_user(request)
    ip = _client_ip(request)
    if not _rate_limit_ok(ip, window_sec=3600, max_attempts=10, bucket='support'):
        raise HTTPException(429, 'Too many messages. Please try again later.')
    subject = (subject or '').strip()[:200] or '(no subject)'
    message = (message or '').strip()[:5000]
    if len(message) < 3:
        raise HTTPException(400, 'Please write a short message.')
    now = int(time.time())
    con = _db()
    cur = con.execute(
        "INSERT INTO tickets (user_id, email, subject, body, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, 'open', ?, ?)",
        (u['id'], u['email'], subject, message, now, now))
    tid = cur.lastrowid
    con.execute("INSERT INTO ticket_messages (ticket_id, von, text, gelesen, "
                "created_at) VALUES (?, 'kunde', ?, 1, ?)", (tid, message, now))
    con.commit(); con.close()
    # An den Betreiber: Reply-To = Kunde, damit man direkt antworten kann.
    try:
        _send_mail(SUPPORT_EMAIL or ADMIN_MAIL,
                   f'[Support #{tid}] {subject}',
                   f'New support ticket #{tid}\n\n'
                   f'From: {u["email"]} (user id {u["id"]}, {u["name"] or "no name"})\n\n'
                   f'{message}\n\n'
                   f'--\nReply to this email to answer the customer directly.',
                   reply_to=u['email'])
    except Exception as e:
        print(f'Support-Mail an Betreiber fehlgeschlagen: {e}')
    # An den Kunden: Eingangsbestaetigung ueber noreply (kein Reply-To).
    try:
        hallo = f'Hi {u["name"]},' if (u['name'] or '').strip() else 'Hi,'
        _send_mail(u['email'], f'We received your message (#{tid})',
                   f'{hallo}\n\n'
                   f'Thanks for reaching out. We received your message and will '
                   f'get back to you by email as soon as possible.\n\n'
                   f'Your message:\n{message}\n\n'
                   f'The DouchkoVE Team')
    except Exception as e:
        print(f'Support-Bestaetigung an Kunde fehlgeschlagen: {e}')
    return {'ok': True, 'ticket': tid}


def _ticket_verlauf(con, tid):
    """Nachrichten eines Tickets, aelteste zuerst."""
    return [{'id': r['id'], 'von': r['von'], 'text': r['text'],
             'gelesen': bool(r['gelesen']), 'created_at': r['created_at']}
            for r in con.execute(
                "SELECT id, von, text, gelesen, created_at FROM ticket_messages "
                "WHERE ticket_id = ? ORDER BY created_at, id", (tid,)).fetchall()]


@app.get('/api/support/tickets')
def api_support_tickets(request: Request):
    """v198: Der Kunde sieht seinen eigenen Verlauf in der App. Vorher stand
    die Antwort nur in seinem Postfach - und eine Rueckfrage darauf erzeugte
    ein neues Ticket ohne Bezug zum alten."""
    u = _require_user(request)
    con = _db()
    # v212: Geschlossene Tickets verschwinden 24 h nach dem Schliessen aus
    # der Kundenansicht. Vorher stapelten sich erledigte Vorgaenge fuer immer
    # in der Liste. Gefiltert wird beim LESEN, nicht geloescht - die Historie
    # bleibt im Panel und fuer die Aufbewahrung erhalten.
    _zu = int(time.time()) - TICKET_CLOSED_TTL
    tk = con.execute(
        "SELECT id, subject, status, created_at, updated_at FROM tickets "
        "WHERE user_id = ? AND NOT (status = 'closed' AND updated_at < ?) "
        "ORDER BY updated_at DESC LIMIT 50",
        (u['id'], _zu)).fetchall()
    aus = []
    for t in tk:
        aus.append({'id': t['id'], 'subject': t['subject'], 'status': t['status'],
                    'created_at': t['created_at'], 'updated_at': t['updated_at'],
                    'messages': _ticket_verlauf(con, t['id'])})
    # v230g DER ZAEHLER MUSS DENSELBEN FILTER HABEN WIE DIE LISTE.
    # Er zaehlte ALLE ungelesenen Antworten, die Liste blendet geschlossene
    # Tickets aber 24 h nach dem Schliessen aus (v212). Stand die letzte
    # ungelesene Antwort in so einem Ticket, war sie fuer den Kunden
    # unerreichbar - die Liste kam leer zurueck, der Browser markierte
    # nichts als gelesen, und die Zahl am Support-Link blieb fuer immer
    # stehen. Ein Zaehler, der stehen bleibt, nachdem man hingeschaut hat,
    # ist Muell (v202). Der Riegel gehoert an den ZAEHLER, nicht an den
    # Browser: mit demselben Filter faellt er von selbst, sobald das Ticket
    # ausblendet.
    neu = con.execute(
        "SELECT COUNT(*) c FROM ticket_messages m JOIN tickets t "
        "ON t.id = m.ticket_id WHERE t.user_id = ? AND m.von = 'admin' "
        "AND m.gelesen = 0 AND NOT (t.status = 'closed' AND t.updated_at < ?)",
        (u['id'], _zu)).fetchone()['c']
    con.close()
    return {'items': aus, 'ungelesen': neu}


@app.post('/api/support/tickets/{tid}/read')
def api_support_read(tid: int, request: Request):
    u = _require_user(request)
    con = _db()
    con.execute("UPDATE ticket_messages SET gelesen = 1 WHERE ticket_id = "
                "(SELECT id FROM tickets WHERE id = ? AND user_id = ?)",
                (tid, u['id']))
    con.commit(); con.close()
    return {'ok': True}


@app.post('/api/support/tickets/{tid}/reply')
def api_support_reply(tid: int, request: Request, message: str = Form(...)):
    """Rueckfrage des Kunden im BESTEHENDEN Ticket."""
    u = _require_user(request)
    if not _rate_limit_ok(_client_ip(request), window_sec=3600,
                          max_attempts=20, bucket='support'):
        raise HTTPException(429, 'Too many messages. Please try again later.')
    text = (message or '').strip()[:5000]
    if len(text) < 3:
        raise HTTPException(400, 'Please write a short message.')
    now = int(time.time())
    con = _db()
    t = con.execute("SELECT id, subject, status, updated_at FROM tickets "
                    "WHERE id = ? AND user_id = ?", (tid, u['id'])).fetchone()
    if not t:
        con.close()
        raise HTTPException(404, 'Unknown ticket.')
    # v212: Ein GESCHLOSSENES Ticket ist erledigt. Eine Rueckfrage darauf
    # riss es bisher wieder auf - damit war 'geschlossen' nur eine Meinung.
    # Wer noch etwas braucht, macht ein neues Ticket auf; der alte Verlauf
    # bleibt bis zum Ablauf lesbar.
    if (t['status'] or '') == 'closed':
        con.close()
        raise HTTPException(409, 'This ticket is closed. Please open a new one.')
    con.execute("INSERT INTO ticket_messages (ticket_id, von, text, gelesen, "
                "created_at) VALUES (?, 'kunde', ?, 1, ?)", (tid, text, now))
    # Eine Rueckfrage macht das Ticket wieder offen - sonst faellt sie aus
    # dem Blick, weil das Panel nach offenen Tickets sortiert.
    con.execute("UPDATE tickets SET status = 'open', updated_at = ? WHERE id = ?",
                (now, tid))
    con.commit(); con.close()
    try:
        _send_mail(SUPPORT_EMAIL or ADMIN_MAIL,
                   f'[Support #{tid}] {t["subject"]} (reply)',
                   f'{u["email"]} replied on ticket #{tid}:\n\n{text}',
                   reply_to=u['email'])
    except Exception as e:
        print(f'Support-Rueckfrage-Mail fehlgeschlagen: {e}')
    return {'ok': True}


@app.post('/api/change_password')
def api_change_password(request: Request, response: Response,
                        old: str = Form(...), new: str = Form(...)):
    """v80m: Passwort im eingeloggten Zustand aendern."""
    u = _require_user(request)
    if not _verify_pw(old, u['pw_hash']):
        raise HTTPException(401, 'Current password is wrong.')
    if not _valid_pw(new):
        raise HTTPException(400, 'New password needs at least 8 characters.')
    con = _db()
    con.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
                (_hash_pw(new), u['id']))
    # v203-sec: Bis v202 blieb nach einem Passwortwechsel JEDE andere Sitzung
    # gueltig - bis zu 30 Tage lang. Wer sein Passwort aendert, weil er einen
    # Fremdzugriff vermutet, erreichte damit genau nichts. Der Reset-Weg macht
    # es seit jeher richtig (DELETE FROM sessions); die beiden Pfade
    # widersprachen sich. Jetzt fliegen alle raus - auch die eigene -, und der
    # Aendernde bekommt sofort eine frische Sitzung, damit er eingeloggt bleibt.
    con.execute("DELETE FROM sessions WHERE user_id = ?", (u['id'],))
    con.commit()
    con.close()
    _sec_event('pw_wechsel', request, wer=f"user:{u['id']}",
               detail='alle anderen Sitzungen beendet')
    tok, _exp = _create_session(u['id'])
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    return {'ok': True, 'sessions_beendet': True}


def _purge_user_db(uid):
    """v98: DB-Teil der Konto-Loeschung. Kaufbuchungen wandern VOR dem
    Loeschen ins ledger_archive (GoBD/§147 AO: 10 Jahre Aufbewahrung fuer
    Buchungsbelege; DSGVO Art. 17(3)(b) erlaubt diese Ausnahme explizit) -
    alles andere (Renders, Refunds, Gratis-Gutschriften) wird geloescht."""
    con = _db()
    _mail = con.execute("SELECT email FROM users WHERE id = ?",
                        (uid,)).fetchone()
    con.execute(
        "INSERT INTO ledger_archive (user_email, delta_sec, grund, "
        "created_at, archived_at) "
        "SELECT ?, delta_sec, grund, created_at, ? FROM ledger "
        "WHERE user_id = ? AND grund LIKE 'Kauf %'",
        (_mail['email'] if _mail else f'user#{uid}', int(time.time()), uid))
    # v135a: Rest-Saldo als eigene Archiv-Zeile sichern. Die AGB versprechen
    # eine Erstattung ungenutzter Credits aus Kaeufen < 14 Tage - ohne diese
    # Zeile waere nach der Loeschung die Berechnungsgrundlage weg.
    _balrow = con.execute("SELECT balance_sec FROM users WHERE id = ?",
                          (uid,)).fetchone()
    if _balrow and _balrow['balance_sec'] > 0:
        con.execute(
            "INSERT INTO ledger_archive (user_email, delta_sec, grund, "
            "created_at, archived_at) VALUES (?, ?, ?, ?, ?)",
            (_mail['email'] if _mail else f'user#{uid}',
             _balrow['balance_sec'], 'Saldo bei Loeschung',
             int(time.time()), int(time.time())))
    con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM ledger WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM resets WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM verify_tokens WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM mail_log WHERE user_id = ?", (uid,))   # v125
    # v135a: Support-Tickets enthalten Klartext-Mail + Nachrichten - 'Deletion
    # is permanent' gilt auch fuer sie.
    con.execute("DELETE FROM ticket_messages WHERE ticket_id IN "
                "(SELECT id FROM tickets WHERE user_id = ?)", (uid,))
    con.execute("DELETE FROM tickets WHERE user_id = ?", (uid,))
    # v196: Feedback haengt an der Person -> mitloeschen. Ankuendigungen sind
    # global und gehoeren niemandem, die bleiben.
    con.execute("DELETE FROM feedback WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM users WHERE id = ?", (uid,))
    con.commit()
    con.close()
    # v126: persoenliche Stil-Referenzen gehoeren zum Konto -> mit loeschen.
    try:
        _urp = _user_refs_path(uid)
        if _urp and os.path.exists(_urp):
            os.remove(_urp)
    except OSError:
        pass


@app.post('/api/delete_account')
def api_delete_account(request: Request, response: Response,
                       password: str = Form(''), confirm_email: str = Form('')):
    """v80m: DSGVO - Nutzer kann sein Konto komplett loeschen.
    v137a: Google-Konten haben nie ein Passwort gesehen (Zufalls-Hash bei der
    Anlage) - sie bestaetigen stattdessen durch Eintippen der eigenen
    E-Mail-Adresse. Passwort-Konten bestaetigen weiter mit Passwort."""
    u = _require_user(request)
    is_google = bool(_row_get(u, 'google_sub'))
    ok = False
    if password:
        ok = _verify_pw(password, u['pw_hash'])
    elif is_google and confirm_email:
        ok = (confirm_email.strip().lower()
              == str(u['email']).strip().lower())
    if not ok:
        raise HTTPException(401, 'Please type your account email to confirm.'
                            if is_google and not password
                            else 'Password is wrong.')
    uid = u['id']
    # v92-sec (DSGVO Art. 17): WIRKLICH alles loeschen. Frueher blieben die
    # gerenderten Videos, die Original-Uploads (Gesicht/Stimme!), Transkripte
    # und der Transkript-Cache bis zum Retention-Sweep (7/30 Tage) liegen -
    # obwohl "komplett loeschen" versprochen war. Jetzt: Job-Ordner von Platte,
    # tcache-Dateien, In-Memory-Jobs, plus resets/verify_tokens.
    my_jids = [jid for jid, j in list(JOBS.items()) if j.get('user_id') == uid]
    for jid in my_jids:
        shutil.rmtree(job_dir(jid), ignore_errors=True)
        JOBS.pop(jid, None)
    try:
        pref = f'{uid}_'
        for fn in os.listdir(_TCACHE):
            if fn.startswith(pref):
                try:
                    os.remove(os.path.join(_TCACHE, fn))
                except OSError:
                    pass
    except OSError:
        pass
    _purge_user_db(uid)
    # Templates fuer diesen User loeschen
    try:
        all_tpl = _load_templates()
        key = 'u:' + u['email']
        if key in all_tpl:
            all_tpl.pop(key)
            _save_templates(all_tpl)
    except Exception:
        pass
    response.delete_cookie('dve_session', path='/')
    return {'ok': True}


def _asset(name, media, request=None):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        raise HTTPException(404)
    # v142: ETag zusaetzlich zum max-age. Nach Ablauf der 24h fragt der Browser
    # nach - bisher kam dann immer das komplette Bild, jetzt ein 304.
    stt = os.stat(p)
    etag = '"%x-%x"' % (stt.st_mtime_ns, stt.st_size)
    _cc = 'public, max-age=86400'
    hit = _etag_304(request, etag, _cc)
    if hit is not None:
        return hit
    return FileResponse(p, media_type=media,
                        headers={'Cache-Control': _cc, 'ETag': etag})


@app.get('/favicon.ico')
@app.get('/favicon.png')
def favicon(request: Request):
    return _asset('favicon.png', 'image/png', request)


@app.get('/logo_white.png')
def logo_white(request: Request):
    return _asset('logo_white.png', 'image/png', request)


@app.get('/logo_dark.png')
def logo_dark(request: Request):
    return _asset('logo_dark.png', 'image/png', request)


@app.get('/api/health')
def health():
    """Fuer externe Uptime-Ueberwachung (z.B. UptimeRobot, kostenlos, alle
    5 Min anpingen): 200 = Server + Datenbank leben, alles andere loest
    dort den Alarm aus. Bewusst ohne Login und ohne interne Details.
    v226a: die Programm-Version steht dabei - "welche Fassung laeuft
    gerade?" war bisher nur mit Admin-Schluessel oder ueber die Metadaten
    eines fertigen Videos zu beantworten, und genau diese Frage kostete
    drei Runden. Sie ist kein Geheimnis: derselbe Text steht im Kommentar
    JEDES ausgelieferten Videos. Der Commit bleibt draussen."""
    try:
        con = _db()
        con.execute('SELECT 1').fetchone()
        con.close()
    except Exception:
        raise HTTPException(503, 'db unavailable')
    return {'ok': True, 'version': DVE_VERSION}


@app.get('/', response_class=HTMLResponse)
def landing(request: Request):
    _trichter('besuch', request)
    return _page('landing.html', request)


@app.get('/before-after', response_class=HTMLResponse)
def before_after(request: Request):
    """v230ao: EINE Seite mit dem einzigen Argument, das wirklich ueberzeugt -
    derselbe Clip zweimal, gross, plus die Entscheidungen der Regie. Statt der
    fuenf duennen Keyword-Seiten aus einem fremden SEO-Vorschlag (v230am).
    Zaehlt wie die Startseite als Besuch: sie ist ein zweiter Eingang."""
    _trichter('besuch', request)
    return _page('example.html', request)


@app.get('/app', response_class=HTMLResponse)
def index(request: Request):
    # v208: Wer die App oeffnet, hat mehr getan als nur die Landing zu sehen -
    # das ist die erste echte Huerde. Angemeldete zaehlen hier nicht mit,
    # sonst zaehlt jeder Seitenwechsel eines Bestandskunden als neue Chance.
    if not _current_user(request):
        _trichter('app', request)
    return _page('index.html', request)


@app.get('/app/{rest:path}', response_class=HTMLResponse)
def index_deep(rest: str, request: Request):
    """v130x: Deep-Link-Routing. Die SPA nutzt jetzt echte Pfade (/app/create,
    /app/library, ...) statt nur Hash. Damit reagiert die Adressleiste normal
    (Enter laedt neu) und Links sind teilbar. Jeder /app/<...>-Aufruf liefert
    dieselbe SPA; der Client-Router liest den Pfad und zeigt den Bereich."""
    return _page('index.html', request)


@app.get('/imprint', response_class=HTMLResponse)
def imprint(request: Request):
    return _page('imprint.html', request)


@app.get('/privacy', response_class=HTMLResponse)
def privacy(request: Request):
    return _page('privacy.html', request)


@app.get('/terms', response_class=HTMLResponse)
def terms(request: Request):
    return _page('terms.html', request)


# Legacy DE-routes -> redirect
@app.get('/impressum')
def impressum_legacy():
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/imprint')


@app.get('/datenschutz')
def datenschutz_legacy():
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/privacy')


@app.post('/api/pruefe-code')
def pruefe(request: Request, code: str = Form(...)):
    # v203-sec: Alt-Zugangscodes sind NAME-1234 - also 10.000 Moeglichkeiten je
    # erratbarem Namensteil, und dieser Endpunkt sagte bei einem Treffer sofort
    # Name und Restkontingent. Ohne Anmeldung, ohne Bremse war das ein
    # Rateorakel: ein Skript findet einen gueltigen Code in Minuten, und ein
    # Code ist eine vollwertige zweite Identitaet. Dieselbe Bremse wie beim
    # Login, nur strenger, weil hier niemand ein eigenes Konto hat.
    if not _rate_limit_ok(_client_ip(request), window_sec=900,
                          max_attempts=10, bucket='code'):
        raise HTTPException(429, 'Too many attempts. Please try again later.')
    ok, msg = check_code(code)
    if not ok:
        return JSONResponse({'ok': False, 'msg': msg}, status_code=403)
    c = load_codes()[code.strip()]
    rest = (c['limit'] - c.get('genutzt', 0)) if c.get('limit') else None
    return {'ok': True, 'name': c.get('name', ''), 'rest': rest}


@app.get('/.well-known/security.txt')
@app.get('/security.txt')
def security_txt():
    """v204-sec: Der Meldeweg fuer Finder von aussen (RFC 9116). Wer eine
    Luecke entdeckt, soll sie melden koennen, statt sie zu verkaufen oder
    zu veroeffentlichen - und er soll sehen, dass jemand zuhoert.
    Bewusst OHNE Anmeldung und ohne Cache-Hindernis."""
    ablauf = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                           time.gmtime(time.time() + 365 * 86400))
    basis = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    return Response(
        content=(f"Contact: mailto:{SUPPORT_EMAIL}\n"
                 f"Expires: {ablauf}\n"
                 f"Preferred-Languages: de, en\n"
                 f"Canonical: {basis}/.well-known/security.txt\n"
                 f"Policy: {basis}/terms\n"
                 f"\n"
                 f"# Thanks for looking. Please give us a reasonable window to\n"
                 f"# fix an issue before making it public. We answer every\n"
                 f"# report, including the ones that turn out to be false\n"
                 f"# alarms.\n"),
        media_type='text/plain; charset=utf-8')


@app.get('/robots.txt')
def robots_txt():
    """v230ah: Suchmaschinen sollen die Startseite und die Rechtstexte finden -
    und sonst nichts. Alles hinter /app ist privat (Kundendaten, Jobs), das
    Panel erst recht; ein Crawler dort erzeugt nur Last und Fehlermeldungen.
    KEIN Schutz, sondern eine Bitte - der Riegel bleibt die Anmeldung."""
    basis = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    return Response(
        content=("User-agent: *\n"
                 "Allow: /$\n"
                 "Disallow: /app\n"
                 "Disallow: /api/\n"
                 "Disallow: /admin\n"
                 "Disallow: /assets/\n"
                 f"\nSitemap: {basis}/sitemap.xml\n"),
        media_type='text/plain; charset=utf-8')


@app.get('/sitemap.xml')
def sitemap_xml():
    """v230ah: die oeffentlichen Seiten, mehr gibt es nicht zu indexieren."""
    basis = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    heute = time.strftime('%Y-%m-%d', time.gmtime())
    seiten = [('/', '1.0'), ('/before-after', '0.8'), ('/terms', '0.3'),
              ('/privacy', '0.3'), ('/imprint', '0.3')]
    eintraege = ''.join(
        f'<url><loc>{basis}{p}</loc><lastmod>{heute}</lastmod>'
        f'<priority>{prio}</priority></url>' for p, prio in seiten)
    return Response(
        content=('<?xml version="1.0" encoding="UTF-8"?>'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 f'{eintraege}</urlset>'),
        media_type='application/xml')


@app.get('/api/looks')
def looks():
    return LOOKS


@app.get('/api/fonts')
def fonts():
    return FONTS


@app.get('/api/fx_labels')
def fx_labels():
    return FX_LABELS


@app.get('/api/anim_labels')
def anim_labels():
    return ANIM_LABELS


@app.get('/api/default_config')
def default_config(look: str = 'creator'):
    """Voreinstellungen fuer die UI. Der Client kann alles ueberschreiben."""
    return build_config(look)


# v89: Anonyme Demo. Der staerkste Wechselgrund ist das eigene Video -
# also darf jeder OHNE Account 10 Sekunden mit Wasserzeichen rendern.
# Missbrauchsschutz: 2 Demos pro IP pro Tag (in-memory; Neustart resettet,
# fuer die Beta voellig ausreichend).
_DEMO_IPS = {}


def _demo_ok(ip, limit=2, window=86400):
    now = time.time()
    hits = [t for t in _DEMO_IPS.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        return False
    hits.append(now)
    _DEMO_IPS[ip] = hits
    return True


@app.post('/api/unlock/{jid}')
def api_unlock(jid: str, request: Request):
    """v101 Watermark-Unlock: nach dem ersten Kauf laesst sich ein gecachtes
    Free-Video ohne Neu-Render sauber freischalten (Button in der Library).
    Idempotent; der Kauf selbst schaltet auch automatisch alles frei."""
    u = _require_user(request)
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    if not _has_purchased(u['id']):
        raise HTTPException(402, 'Your first purchase removes the watermark.')
    ok = _unlock_job(jid)
    j = JOBS.get(jid) or {}
    return {'ok': True, 'unlocked': ok, 'wm': bool(j.get('wm'))}


@app.post('/api/alpha/{jid}')
def api_alpha(jid: str, request: Request):
    """v101h Caption-Alpha-Export: transparente Caption-Ebene (ProRes 4444)
    fuer Premiere/Resolve. Nur fuer Kaeufer; kostet wie ein weiterer Render
    (Doppelpass = doppelte Compositing-Arbeit). Idempotent pro Job."""
    u = _require_user(request)
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j or j.get('kind') == 'motion':
        raise HTTPException(404, 'Unknown job.')
    d = job_dir(jid)
    if os.path.exists(os.path.join(d, 'fertig_captions.mov')):
        return {'ok': True, 'ready': True}
    if not _has_purchased(u['id']):
        raise HTTPException(402, 'The editor layer is available after your '
                                 'first purchase.')
    if not os.path.exists(os.path.join(d, 'fertig.mp4')):
        raise HTTPException(409, 'Render the video first.')
    if not j.get('input') or not os.path.exists(j['input']):
        raise HTTPException(410, 'The source video has expired - upload it '
                                 'again to create an editor layer.')
    if j.get('status') in ('laeuft', 'wartet'):
        raise HTTPException(409, 'A render for this job is already running.')
    cost = _job_cost(j)
    con = _db()
    _done = con.execute("SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
                        (u['id'], f'Alpha {jid} ({cost}s)')).fetchone()
    con.close()
    if not _done and not _reserve_credits(u['id'], cost, jid,
                                          grund=f'Alpha {jid} ({cost}s)'):
        raise HTTPException(402, 'Not enough credits for the editor layer.')
    j['mode'] = 'alpha'
    set_state(jid, status='wartet', progress=0.0, phase='Queued …', alpha=None)
    q_put(jid)
    return {'ok': True, 'queued': True, 'cost_min': cost // 60}


@app.get('/api/alpha_file/{jid}')
def alpha_file(jid: str, request: Request):
    """v101h: fertige Caption-Ebene ausliefern."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This video belongs to another account.')
    p = os.path.join(job_dir(jid), 'fertig_captions.mov')
    if not os.path.exists(p):
        raise HTTPException(404, 'No editor layer for this job yet.')
    return FileResponse(p, media_type='video/quicktime',
                        filename='DouchkoVE_Captions_Layer.mov')


MOTION_AUTO_MAX_MB = 400        # Upload-Cap fuers Showcase-Video
MOTION_AUTO_MAX_SEC = 900       # max. Videolaenge (15 min)


def _synth_word_timings(text):
    """Synthetische Wort-Timings (0.32s/Wort + Pause an Satzenden) fuer Voiceover-Sync."""
    words, _t = [], 0.0
    for w in str(text).split():
        words.append({'word': ' ' + w, 'start': round(_t, 2), 'end': round(_t + 0.3, 2)})
        _t += 0.32
        if w.endswith(('.', '!', '?')):
            _t += 0.4
    return words


def _srt_ts_sec(s):
    """SRT/VTT-Zeitstempel (HH:MM:SS,mmm oder HH:MM:SS.mmm, Stunden optional) -> Sekunden."""
    m = re.match(r'(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})', s.strip())
    if not m:
        return None
    h = int(m.group(1) or 0)
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4).ljust(3, '0')) / 1000.0


def _transcript_to_words(filename, raw):
    """v117d: Hochgeladenes Transkript (.json/.srt/.vtt/.txt) -> Wortliste
    [{word,start,end}] fuer buildShowcase. Text bleibt VERBATIM (kein Halluzinieren).
    JSON: Liste von {word|text,start,end} ODER {"words":[...]} ODER {"segments":[{text,start,end}]}.
    SRT/VTT: Cues parsen, Woerter gleichmaessig ueber die Cue-Dauer verteilen.
    TXT/Fallback: synthetische Timings. Gibt [] zurueck, wenn nichts Brauchbares drin ist."""
    name = (filename or '').lower()
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, (bytes, bytearray)) else str(raw)
    txt = txt.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not txt:
        return []

    def _norm_list(items):
        out, prev = [], 0.0
        for it in items:
            if not isinstance(it, dict):
                continue
            w = it.get('word', it.get('text', ''))
            if not isinstance(w, str) or not w.strip():
                continue
            try:
                st = float(it.get('start', prev))
                en = float(it.get('end', st + 0.3))
            except (TypeError, ValueError):
                st, en = prev, prev + 0.3
            if en <= st:
                en = st + 0.05
            out.append({'word': (' ' + w.strip()) if not w.startswith(' ') else w,
                        'start': round(st, 3), 'end': round(en, 3)})
            prev = en
        return out

    # 1) JSON
    if name.endswith('.json') or txt[:1] in ('{', '['):
        try:
            data = json.loads(txt)
        except Exception:
            data = None
        if isinstance(data, dict):
            data = data.get('words') or data.get('segments') or data.get('transcript') or data
        if isinstance(data, list):
            # Segmente (mehrere Woerter pro text) auf Wort-Ebene aufspalten.
            words = []
            for it in data:
                if isinstance(it, dict) and isinstance(it.get('text'), str) and len(it['text'].split()) > 1 \
                        and 'word' not in it:
                    seg = it['text'].strip()
                    try:
                        st = float(it.get('start', 0.0)); en = float(it.get('end', st + 0.3))
                    except (TypeError, ValueError):
                        st, en = 0.0, 0.3
                    toks = seg.split()
                    step = (en - st) / max(1, len(toks))
                    for k, tok in enumerate(toks):
                        words.append({'word': ' ' + tok, 'start': round(st + k * step, 3),
                                      'end': round(st + (k + 1) * step, 3)})
                else:
                    words.extend(_norm_list([it]))
            if words:
                return words
        if isinstance(data, str) and data.strip():
            return _synth_word_timings(data)
        # kein brauchbares JSON -> als Klartext behandeln

    # 2) SRT / VTT (Cue-Bloecke mit --> Zeitstempeln)
    if '-->' in txt:
        words = []
        for m in re.finditer(r'([0-9:.,]+)\s*-->\s*([0-9:.,]+)([^\n]*)\n(.*?)(?=\n\s*\n|\Z)', txt, re.S):
            st, en = _srt_ts_sec(m.group(1)), _srt_ts_sec(m.group(2))
            if st is None or en is None or en <= st:
                continue
            body = re.sub(r'<[^>]+>', ' ', m.group(4))                 # VTT-Tags raus
            body = re.sub(r'\{\\[^}]*\}', ' ', body)                   # ASS-Overrides raus
            toks = body.split()
            if not toks:
                continue
            step = (en - st) / len(toks)
            for k, tok in enumerate(toks):
                words.append({'word': ' ' + tok, 'start': round(st + k * step, 3),
                              'end': round(st + (k + 1) * step, 3)})
        if words:
            return words

    # 3) Klartext (Cue-Nummern/WEBVTT-Kopf entfernen), synthetische Timings
    lines = [ln for ln in txt.split('\n')
             if ln.strip() and not ln.strip().isdigit() and not ln.strip().upper().startswith('WEBVTT')]
    return _synth_word_timings(' '.join(lines))


def _sanitize_custom(raw):
    """v117: nur erlaubte, validierte Einstell-Knoepfe durchlassen (kein beliebiges JSON)."""
    try:
        c = json.loads(raw or '{}')
    except Exception:
        return {}
    if not isinstance(c, dict):
        return {}
    out = {}
    def hexok(v):
        return isinstance(v, str) and bool(re.match(r'^#[0-9a-fA-F]{6}$', v))
    for k in ('accent', 'ink', 'sub', 'bg', 'bgDark'):
        if hexok(c.get(k)):
            out[k] = c[k]
    if isinstance(c.get('style'), str) and c['style'] in ('editorial', 'bold', 'soft', 'mono'):
        out['style'] = c['style']
    if isinstance(c.get('font'), str) and 0 < len(c['font']) <= 160:
        out['font'] = c['font']
    if isinstance(c.get('brand'), str) and c['brand'].strip():
        out['brand'] = c['brand'][:40]
    if isinstance(c.get('upper'), bool):
        out['upper'] = c['upper']
    if isinstance(c.get('weight'), (int, float)):
        out['weight'] = max(300, min(900, int(c['weight'])))
    if isinstance(c.get('tracking'), str) and len(c['tracking']) <= 12:
        out['tracking'] = c['tracking']
    for k in ('grain', 'vignette', 'shutter', 'cameraMult', 'trans'):
        if isinstance(c.get(k), (int, float)):
            out[k] = max(0.0, min(3.0, float(c[k])))
    if isinstance(c.get('text'), list):
        _t = [str(x)[:80] for x in c['text'][:16] if isinstance(x, str) and x.strip()]
        if _t:
            out['text'] = _t
    if isinstance(c.get('logo'), str) and c['logo'].startswith('data:') and len(c['logo']) < 2_000_000:
        out['logo'] = c['logo']
    return out


@app.post('/api/motion/showcase')
async def motion_showcase(request: Request,
                          video: UploadFile = File(None),
                          transcript_file: UploadFile = File(None),
                          text: str = Form(''),
                          composition: str = Form('showcase'),
                          style: str = Form('editorial'),
                          format: str = Form('9:16'),
                          custom: str = Form('{}')):
    """v117 Full-customizable: Video ODER Transkript-Text -> gewaehlte Komposition + Stil +
    Format + alle Custom-Einstellungen -> eigenstaendiges Motion-Video. v135a: Pauschale 1 Credit pro Clip (MP4), wie beworben."""
    u = _require_user(request)
    if not MOTION_BRIEF_OK:
        raise HTTPException(503, 'The motion engine is warming up on this server - try again shortly.')
    comp = composition if composition in ('showcase', 'kinetic', 'prompt') else 'showcase'
    style = style if style in ('editorial', 'bold', 'soft', 'mono') else 'editorial'
    fmt = format if format in ('16:9', '9:16', '1:1') else '9:16'
    cust = _sanitize_custom(custom)
    jid = uuid.uuid4().hex[:12]
    d = job_dir(jid)
    os.makedirs(d, exist_ok=True)
    job = {'kind': 'motion', 'showcase': True, 'user_id': u['id'], 'name': 'Motion.mp4',
           'composition': comp, 'style': style, 'format': fmt, 'custom': cust, 'status': 'wartet'}
    has_video = bool(video and getattr(video, 'filename', ''))
    has_tfile = bool(transcript_file and getattr(transcript_file, 'filename', ''))
    if has_video:
        src = os.path.join(d, 'source.mp4')
        cap = MOTION_AUTO_MAX_MB * 1024 * 1024
        total = 0
        try:
            with open(src, 'wb') as f:
                while True:
                    chunk = await video.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > cap:
                        raise HTTPException(413, f'Video too large (max {MOTION_AUTO_MAX_MB} MB).')
                    f.write(chunk)
        except HTTPException:
            shutil.rmtree(d, ignore_errors=True); raise
        if total == 0:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(400, 'Upload a video or enter text.')
        # v142 ASYNC: ffprobe auf einem frisch hochgeladenen Video ist
        # blockierend. In diesem 'async def'-Endpunkt hielt es den Event-Loop
        # an - jetzt im Threadpool.
        import asyncio as _aio5
        try:
            _pr = await _aio5.to_thread(
                subprocess.run,
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', src],
                capture_output=True, text=True, timeout=30)
            dur = float((_pr.stdout or '0').strip() or 0)
        except Exception:
            dur = 0.0
        if dur <= 0:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(400, 'Could not read that video.')
        if dur > MOTION_AUTO_MAX_SEC:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(413, 'Video too long (max 15 min).')
        job['showcase_video'] = src
        job['dauer'] = dur
        _cost = 60                    # v135a: Pauschale 1 Credit pro Motion-Clip
    elif has_tfile:
        cap = 4 * 1024 * 1024                         # Transkript-Datei: max 4 MB
        raw, total = b'', 0
        while True:
            chunk = await transcript_file.read(1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, 'Transcript file too large (max 4 MB).')
            raw += chunk
        try:
            words = _transcript_to_words(getattr(transcript_file, 'filename', ''), raw)
        except Exception:
            words = []
        if not words:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(400, 'Could not read any text from that transcript file.')
        words = words[:4000]
        job['prewords'] = words
        est = max(6.0, (words[-1].get('end') or len(words) / 2.5))
        _cost = 60                    # v135a: Pauschale 1 Credit pro Motion-Clip
    else:
        txt = (text or '').strip()
        if not txt:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(400, 'Upload a video or enter text.')
        job['transcript_text'] = txt[:4000]
        est = max(6.0, len(txt.split()) / 2.5)   # ~2.5 words/sec
        _cost = 60                    # v135a: Pauschale 1 Credit pro Motion-Clip
    if not _reserve_credits(u['id'], _cost, jid):
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(402, 'Not enough credits for this render.')
    job['cost_sec'] = _cost
    JOBS[jid] = job
    set_state(jid, status='wartet', progress=0.0, phase='Queued', kind='motion')
    MQUEUE.put(jid)
    return {'jid': jid, 'status_url': f'/api/status/{jid}'}


async def _finalize_upload(request, jid, d, src, filename, look, code, mode, overrides):
    """Gemeinsamer Abschluss fuer Einmal- UND Chunk-Upload: Dauer pruefen, Credits
    (atomar) reservieren, Job anlegen + einreihen. Datei liegt bereits komplett in
    src. Wirft 413/402 bei zu lang / zu wenig Guthaben und raeumt dann d auf."""
    import asyncio as _aio
    # v204-sec: Bis v203 war die Dauer die EINZIGE inhaltliche Schranke -
    # Aufloesung und Bildrate wurden nie geprueft. Ein 8K-Clip mit 120 Bildern
    # je Sekunde kostet damit denselben Credit wie ein normales Handy-Video,
    # rechnet aber ein Vielfaches: die Pipeline laeuft ueber JEDES Bild
    # (Matting, Gesichter, Compositing). Bei EINEM Worker legt das alle
    # anderen Kunden fuer Stunden lahm. Jetzt werden Breite, Hoehe und
    # Bildrate im selben ffprobe-Aufruf mitgelesen und gedeckelt.
    _dw = _dh = 0
    _fps = 0.0
    try:
        # v98: to_thread - der sync ffprobe blockierte sonst den Event-Loop.
        _r = await _aio.to_thread(
            subprocess.run,
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height,avg_frame_rate',
             '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', src],
            capture_output=True, text=True)
        _zeilen = [z.strip() for z in (_r.stdout or '').splitlines() if z.strip()]
        # Reihenfolge: width, height, avg_frame_rate, duration
        if len(_zeilen) >= 4:
            _dw, _dh = int(float(_zeilen[0])), int(float(_zeilen[1]))
            _num, _, _den = _zeilen[2].partition('/')
            try:
                _fps = float(_num) / float(_den or 1)
            except (TypeError, ValueError, ZeroDivisionError):
                _fps = 0.0
            dur = float(_zeilen[3] or 0)
        else:
            dur = float(_zeilen[-1] or 0) if _zeilen else 0
    except Exception:
        dur = 0
    if dur > MAX_SECONDS:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(413, f'Video too long ({dur:.0f}s). '
                                 f'Maximum {MAX_SECONDS} seconds.')
    # Eine Datei, deren Dauer sich nicht ermitteln laesst, ist keine, die wir
    # rendern wollen: bis v203 lief sie als 0-Sekunden-Job einfach durch und
    # kam ungeprueft in die Schwerlast-Pipeline.
    if dur <= 0:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, 'Could not read this video. Please export it '
                                 'again (MP4/MOV) and retry.')
    if _dw and _dh and max(_dw, _dh) > MAX_PIXEL_LANG:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(413, f'Video resolution too high ({_dw}x{_dh}). '
                                 f'Maximum {MAX_PIXEL_LANG} px on the long edge.')
    # v230c-sec DIE KURZE KANTE UND DAS SEITENVERHAELTNIS FEHLTEN.
    # Bis v230b war nur die LANGE Kante gedeckelt. Ein 8x4096-Clip (Datei nur
    # wenige KB gross, unter jeder Dauer-/Bildraten-Grenze) laeuft im
    # Standbild-Zwischenspeicher durch den festen Filter 'scale=384:-2' und
    # wird auf 384x196608 HOCHskaliert: gemessen 226 MB je zwischengespeichertem
    # Bild, und der Speicher haelt bis zu 156 davon. Der Container hat 6 GB.
    if _dw and _dh:
        _kurz, _lang = min(_dw, _dh), max(_dw, _dh)
        if _kurz < 120:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(413, f'Video too small ({_dw}x{_dh}). '
                                     f'The short edge needs at least 120 px.')
        if _lang > _kurz * MAX_ASPECT:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(
                413, f'Unusual aspect ratio ({_dw}x{_dh}). Supported up to '
                     f'{MAX_ASPECT}:1 - please export as 9:16, 1:1 or 16:9.')
    if _fps > MAX_FPS + 0.5:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(413, f'Frame rate too high ({_fps:.0f} fps). '
                                 f'Maximum {MAX_FPS} fps.')
    u = _current_user(request) if mode != 'demo' else None
    uid = None
    _uhd, need = False, 0
    if u:
        uid = u['id']
        # v127-sec: Flooding-Deckel - pro Konto nur wenige gleichzeitig
        # wartende/laufende Jobs (Pre-Mode bucht nichts ab, waere sonst gratis
        # unbegrenzt). Datei wieder wegraeumen, bevor wir ablehnen.
        if _inflight_count(uid) >= CAPTION_INFLIGHT_CAP:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(429, 'You already have several videos in the queue. '
                                     'Please wait for one to finish before uploading more.')
        # v230c-sec: dazu die SUMMEN-Grenze (siehe _vorbereitet_count).
        if mode == 'pre' and _vorbereitet_count(uid) >= MAX_VORBEREITET:
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(
                429, 'Too many prepared uploads waiting. Please render or '
                     'delete some of them before uploading more.')
        # v149: 4K erst bezahlen, wenn es auch 4K WIRD. Die Pruefung sitzt
        # bewusst hier, vor der Reservierung - nicht im Render.
        _uhd = _will_uhd(overrides, src)
        need = cost_seconds(dur, uhd=_uhd)
        if mode == 'pre':
            if u['balance_sec'] < need:
                shutil.rmtree(d, ignore_errors=True)
                have = credits_of(u['balance_sec'])
                fehlt = credits_of(need) - have
                raise HTTPException(
                    402,
                    f"Not enough credits (video costs {credits_of(need)} "
                    f"credit{'s' if credits_of(need) != 1 else ''}, you have "
                    f"{have}). Missing {max(1, fehlt)} - please top up.")
        elif not _reserve_credits(uid, need, jid):
            shutil.rmtree(d, ignore_errors=True)
            have = credits_of(u['balance_sec'])
            fehlt = credits_of(need) - have
            raise HTTPException(
                402,
                f"Not enough credits (video costs {credits_of(need)} "
                f"credit{'s' if credits_of(need) != 1 else ''}, you have "
                f"{have}). Missing {max(1, fehlt)} - please top up.")
    _vh = await _aio.to_thread(_video_hash, src)
    if not _will_uhd(overrides, src) and isinstance(overrides.get('output'), dict):
        # Wunsch war 4K, die Quelle gibt es nicht her: Stufe wieder rausnehmen,
        # damit der Render gar nicht erst gross rechnet. Auch die Hoehe, sonst
        # rechnete die Engine weiter auf 2160 und der Kunde zahlte den
        # einfachen Satz fuer die vierfache Rechenzeit.
        overrides['output'].pop('quality', None)
        try:
            if int(overrides['output'].get('height') or 0) > 1080:
                overrides['output']['height'] = 1080
        except Exception:
            overrides['output'].pop('height', None)
    # v203-sec: 'demo' stand bis v202 NUR im Feld mode - und mode wird von
    # jedem spaeteren Aufruf ueberschrieben. Ein Demo-Job (anonym, nichts
    # reserviert, kein Konto) liess sich ueber /api/moments in einen vollen
    # Render umschreiben: Wasserzeichen weg, 10-Sekunden-Grenze weg, bezahlt
    # nichts. Die Eigenschaft gehoert an den JOB, nicht an einen Zustand, den
    # der naechste Request umschreibt.
    _trichter('upload', request, user_id=uid)          # v208 Stufe 4
    JOBS[jid] = {'id': jid, 'input': src, 'look': look, 'code': (code or '').strip(),
                 'user_id': uid, 'vhash': _vh, 'mode': mode,
                 'demo': (mode == 'demo'),
                 'cfg_overrides': overrides, 'status': 'wartet', 'progress': 0.0,
                 'phase': 'Queued …', 'dauer': round(dur, 1),
                 'uhd': bool(_uhd) if uid else False,
                 'cost_sec': need if uid else 0,
                 'name': _safe_name(filename)}
    set_state(jid, **{k: v for k, v in JOBS[jid].items()
                      if k not in ('input', 'code')})
    q_put(jid)
    return {'job': jid, 'position': _queue_platz(jid, QUEUE)}


# v101v: Resumable Chunk-Upload. Auf dem Handy bricht ein normaler fetch()-Upload
# ab, sobald der Tab in den Hintergrund geht (Screen-Lock, App-Wechsel). Der
# Chunk-Upload laedt die Datei in kleinen Stuecken; verlaesst der Nutzer den Tab,
# pausiert es und SETZT beim Zurueckkommen an der letzten bestaetigten Byte-Grenze
# FORT, statt alles zu verlieren. Sessions leben im Prozess (Single-Worker).
UPLOADS = {}
UPLOAD_TTL = 3600
_ALLOWED_EXT = ('.mp4', '.mov', '.m4v', '.webm', '.mkv')


def _upload_gc():
    now = time.time()
    for k in [k for k, v in list(UPLOADS.items())
              if now - v.get('ts', now) > UPLOAD_TTL]:
        v = UPLOADS.pop(k, None)
        if v:
            shutil.rmtree(v.get('dir', ''), ignore_errors=True)


@app.post('/api/upload/init')
async def upload_init(request: Request, filename: str = Form(...),
                      size: int = Form(0), look: str = Form('creator'),
                      code: str = Form(''), mode: str = Form('full'),
                      cfg_overrides: str = Form('{}')):
    """Startet eine resumable Upload-Session. Prueft Auth + Endung + Groessen-Cap
    vorab und legt die (leere) Zieldatei an. Rueckgabe: upload_id + received=0."""
    if mode == 'demo':
        ip = _client_ip(request)
        if not _demo_ok(ip):
            raise HTTPException(429, 'Demo limit reached for today. '
                                     'Create a free account to keep going.')
    else:
        ok, msg = check_auth(code, request)
        if not ok:
            raise HTTPException(403, msg)
    _upload_rate_guard(request)
    if look not in LOOKS:
        look = 'creator'
    ext = os.path.splitext(filename or '')[1].lower() or '.mp4'
    if ext not in _ALLOWED_EXT:
        raise HTTPException(400, 'Only video files (mp4, mov, webm, mkv).')
    if size and size > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f'Video too large (max {MAX_MB} MB).')
    try:
        overrides = _sanitize_overrides(json.loads(cfg_overrides) if cfg_overrides else {})
    except Exception:
        overrides = {}
    _upload_gc()
    up = uuid.uuid4().hex[:16]
    jid = uuid.uuid4().hex[:12]
    d = job_dir(jid)
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, 'quelle' + ext)
    open(src, 'wb').close()
    # v230d-sec DIE SITZUNG MERKT SICH, WEM SIE GEHOERT.
    # Der resumable Upload sind drei Anfragen (init/chunk/finish), und geprueft
    # wurde nur die erste. `_finalize_upload` bestimmte den Kunden aus dem
    # Cookie der GERADE laufenden Anfrage - wer die Abschluss-Anfrage ohne
    # Cookie schickte, bekam einen HERRENLOSEN Job: nichts abgebucht, kein
    # Wasserzeichen (weder der Demo- noch der Free-Zweig greift ohne user_id),
    # kein Flut-Deckel, und abholbar blieb er trotzdem, weil `_job_owner_ok`
    # einen Job ohne Eigentuemer immer durchlaesst. Das komplette Bezahlprodukt
    # war damit gratis und unbegrenzt. Der Eigentuemer steht jetzt an der
    # SITZUNG, nicht am einzelnen Request.
    UPLOADS[up] = {'jid': jid, 'dir': d, 'src': src, 'received': 0,
                   'size': int(size or 0), 'look': look, 'code': code,
                   'mode': mode, 'overrides': overrides, 'filename': filename,
                   # Achtung: _current_user liefert eine sqlite3.Row - die hat
                   # KEIN .get() (dieselbe Falle wie bei _owner_ok, v96p).
                   'owner': _sitzungs_uid(request) if mode != 'demo' else None,
                   'ts': time.time()}
    return {'upload_id': up, 'received': 0}


@app.get('/api/upload/status/{up}')
def upload_status(up: str):
    """Wie viele Bytes hat der Server sicher? Der Client fragt das nach dem
    Zurueckkommen und setzt genau dort fort."""
    s = UPLOADS.get(up)
    if not s:
        raise HTTPException(404, 'Upload session expired - please start over.')
    return {'received': s['received'], 'size': s['size']}


@app.post('/api/upload/chunk/{up}')
async def upload_chunk(up: str, request: Request, offset: int = 0):
    """Haengt einen Chunk an genau der Byte-Grenze `offset` an. Passt offset nicht
    zum Serverstand (halb geschriebener, abgebrochener Chunk), antwortet 409 mit der
    Wahrheit - der Client re-synct und schickt ab dort neu. Idempotent + partial-safe:
    wir seeken auf offset und truncaten, ueberschreiben also evtl. Muell sauber."""
    s = UPLOADS.get(up)
    if not s:
        raise HTTPException(404, 'Upload session expired - please start over.')
    if offset != s['received']:
        return JSONResponse({'received': s['received'], 'resync': True}, status_code=409)
    # v204-sec: Bis v203 wurde der ganze Body erst in den Arbeitsspeicher
    # gelesen und DANN die Groesse geprueft - bei 300 MB Cap also bis zu
    # 300 MB (mit Starlettes Zwischenliste eher das Doppelte) RAM je Anfrage,
    # und zwar VOR jeder Pruefung. Ein paar parallele Anfragen genuegten, um
    # die Maschine an den Rand zu bringen. Der angekuendigte Umfang steht im
    # Header, also wird er zuerst gelesen. Ein Chunk ist im Frontend ein paar
    # MB gross; 32 MB sind grosszuegig und trotzdem eine Grenze.
    try:
        _angek = int(request.headers.get('content-length') or 0)
    except (TypeError, ValueError):
        _angek = 0
    if _angek > CHUNK_MAX_BYTES:
        raise HTTPException(413, f'Chunk too large (max '
                                 f'{CHUNK_MAX_BYTES // (1024 * 1024)} MB).')
    if s['received'] + _angek > MAX_MB * 1024 * 1024:
        shutil.rmtree(s['dir'], ignore_errors=True)
        UPLOADS.pop(up, None)
        raise HTTPException(413, f'Video too large (max {MAX_MB} MB).')
    data = await request.body()
    if not data:
        return {'received': s['received']}
    if s['received'] + len(data) > MAX_MB * 1024 * 1024:
        shutil.rmtree(s['dir'], ignore_errors=True)
        UPLOADS.pop(up, None)
        raise HTTPException(413, f'Video too large (max {MAX_MB} MB).')
    with open(s['src'], 'r+b') as f:
        f.seek(offset)
        f.write(data)
        f.truncate(offset + len(data))
    s['received'] = offset + len(data)
    s['ts'] = time.time()
    return {'received': s['received']}


@app.post('/api/upload/finish/{up}')
async def upload_finish(up: str, request: Request):
    """Alle Chunks da -> Datei ist komplett. Gleicher Abschluss wie der Einmal-
    Upload (Dauer, Credits, Job, Queue)."""
    s = UPLOADS.pop(up, None)
    if not s:
        raise HTTPException(404, 'Upload session expired - please start over.')
    if not os.path.exists(s['src']) or os.path.getsize(s['src']) == 0:
        shutil.rmtree(s['dir'], ignore_errors=True)
        raise HTTPException(400, 'Upload incomplete - please try again.')
    # v230d-sec: derselbe Kunde muss abschliessen, der begonnen hat. Ohne das
    # liess sich der Job durch Weglassen des Cookies herrenlos machen (siehe
    # upload_init). Ein Wechsel des Kontos mitten im Upload ist kein Szenario,
    # das es zu unterstuetzen gaebe.
    if s.get('owner') != _sitzungs_uid(request):
        shutil.rmtree(s['dir'], ignore_errors=True)
        raise HTTPException(403, 'Session changed during upload - '
                                 'please sign in and upload again.')
    return await _finalize_upload(request, s['jid'], s['dir'], s['src'],
                                  s['filename'], s['look'], s['code'], s['mode'],
                                  s['overrides'])


@app.post('/api/upload')
async def upload(request: Request, datei: UploadFile = File(...),
                 look: str = Form('creator'), code: str = Form(''),
                 mode: str = Form('full'), cfg_overrides: str = Form('{}')):
    if mode == 'demo':
        ip = _client_ip(request)
        if not _demo_ok(ip):
            raise HTTPException(429, 'Demo limit reached for today. '
                                     'Create a free account to keep going.')
    else:
        ok, msg = check_auth(code, request)
        if not ok:
            raise HTTPException(403, msg)
    _upload_rate_guard(request)
    if look not in LOOKS:
        look = 'creator'
    try:
        overrides = json.loads(cfg_overrides) if cfg_overrides else {}
    except Exception:
        overrides = {}
    overrides = _sanitize_overrides(overrides)
    jid = uuid.uuid4().hex[:12]
    d = job_dir(jid)
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv'):
        raise HTTPException(400, 'Only video files (mp4, mov, webm, mkv).')
    src = os.path.join(d, 'quelle' + ext)
    groesse = 0
    with open(src, 'wb') as f:
        while True:
            chunk = await datei.read(1 << 20)
            if not chunk:
                break
            groesse += len(chunk)
            if groesse > MAX_MB * 1024 * 1024:
                f.close()
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, f'Video too large (max {MAX_MB} MB).')
            f.write(chunk)

    return await _finalize_upload(request, jid, d, src, datei.filename,
                                  look, code, mode, overrides)


@app.post('/api/render_start/{jid}')
async def render_start(jid: str, request: Request, look: str = Form('creator'),
                       code: str = Form(''), mode: str = Form('full'),
                       cfg_overrides: str = Form('{}')):
    """v83: Startet den Render auf einem bereits hochgeladenen Pre-Job.
    Das Video liegt schon auf dem Server, die Transkription laeuft oder ist
    fertig - hier kommen nur noch Look/Settings an. Spart den zweiten Upload
    und die Whisper-Wartezeit komplett."""
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    j = JOBS.get(jid)
    if not j or not os.path.exists(j.get('input', '')):
        raise HTTPException(404, 'Upload expired - please upload again.')
    u = _current_user(request)
    uid = u['id'] if u else None
    if j.get('user_id') != uid:
        raise HTTPException(403, 'Not your upload.')
    if j.get('demo'):
        raise HTTPException(403, 'Demo videos cannot be re-rendered. '
                                 'Create a free account and upload again.')
    if mode not in ('full', 'analyze'):
        mode = 'full'
    if look in LOOKS:
        j['look'] = look
    try:
        overrides = json.loads(cfg_overrides) if cfg_overrides else {}
    except Exception:
        overrides = {}
    overrides = _sanitize_overrides(overrides)
    # Sprache nachtraeglich geaendert? Dann lief die Vorab-Transkription mit
    # dem falschen Sprach-Hinweis - Cache verwerfen, der Render macht es neu.
    old_lang = (j.get('cfg_overrides') or {}).get('language')
    if overrides.get('language') != old_lang:
        try:
            os.remove(os.path.splitext(j['input'])[0] + '_transcript2.json')
        except OSError:
            pass
    j['cfg_overrides'] = overrides
    # v149: im Editor kann 4K noch an- oder abgewaehlt werden. Der Preis
    # richtet sich nach dem, was jetzt gerendert wird - und 4K wird nur
    # berechnet, wenn die Quelle es hergibt.
    _uhd2 = _will_uhd(overrides, j.get('input') or '')
    if not _uhd2 and isinstance(overrides.get('output'), dict):
        overrides['output'].pop('quality', None)
        try:
            if int(overrides['output'].get('height') or 0) > 1080:
                overrides['output']['height'] = 1080
        except Exception:
            overrides['output'].pop('height', None)
    # v203-sec PREIS NACH DER ABRECHNUNG. Bis v202 wurden cfg_overrides, uhd
    # und cost_sec BEDINGUNGSLOS hier gesetzt - und das Abbuch-Gate darunter
    # ist ueber _render_charged idempotent, bucht also nicht nach. Zwei Aufrufe
    # genuegten: erst 1080p starten (wird zum einfachen Satz gebucht), dann
    # denselben Job mit 4K-Overrides erneut - der Render lief in 4K, bezahlt
    # war 1080p. Schlimmer noch: Erstattungen gehen ueber _job_cost(j), also
    # ueber cost_sec. Ein nachtraeglich erhoehtes cost_sec gab bei einem
    # fehlgeschlagenen Render MEHR zurueck, als je bezahlt wurde - aus einem
    # Abbruch liess sich Guthaben erzeugen. Derselbe Fehlertyp wie v159/v170:
    # der Riegel sass hinter der Mutation.
    # Ist bereits gebucht, gilt der GEBUCHTE Stand. Wer 4K will, startet einen
    # neuen Render und zahlt ihn.
    # v230c-sec: DER RIEGEL DARF NICHT AM MODUS HAENGEN. Bis v230b stand hier
    # `if (u and mode == 'full')` - mit mode='analyze' war `_schon` also
    # zwangsweise 0, und der else-Zweig schrieb uhd/cost_sec ungeprueft hoch.
    # Ein Kunde startete normal in 1080p (einmal gebucht), rief denselben Job
    # dann mit mode='analyze' und output.height=2160 auf und bekam den
    # anschliessenden 'inklusive'-Re-Render in 4K zum 1080p-Preis. Was bereits
    # gebucht wurde, ist eine Eigenschaft des JOBS, nicht des Aufrufs -
    # derselbe Fehlertyp wie v203-sec, eine Tuer weiter.
    _schon = _render_gebucht(uid, jid) if u else 0
    if _schon > 0:
        _neu_kosten = cost_seconds(j.get('dauer', 0), uhd=bool(_uhd2))
        if _neu_kosten > _schon:
            _uhd2 = bool(j.get('uhd'))          # Hochstufung faellt zurueck
            if isinstance(overrides.get('output'), dict):
                overrides['output'].pop('quality', None)
                try:
                    if int(overrides['output'].get('height') or 0) > 1080:
                        overrides['output']['height'] = 1080
                except Exception:
                    overrides['output'].pop('height', None)
            j['cfg_overrides'] = overrides
            print(f'Render {jid}: Hochstufung nach der Abrechnung abgelehnt '
                  f'(gebucht {_schon}s, verlangt {_neu_kosten}s).')
        j['uhd'] = bool(_uhd2)
        j['cost_sec'] = _schon               # Erstattung = wirklich Gezahltes
    else:
        j['uhd'] = bool(_uhd2)
        j['cost_sec'] = cost_seconds(j.get('dauer', 0), uhd=_uhd2)
    if u and mode == 'full':
        need = _job_cost(j)
        # v95: Das ist der Abbuch-Punkt des Pre-Flows. Der Upload (mode 'pre')
        # hat NUR transkribiert, nichts abgebucht - erst hier wird atomar
        # reserviert. Idempotent gegen Doppel-Klick/Retry ueber den Ledger-
        # Eintrag 'Render {jid}': war schon reserviert, nicht doppelt ziehen.
        # Bei Render-Fehler erstattet _maybe_refund.
        if not _render_charged(uid, jid) and not _reserve_credits(uid, need, jid):
            have = credits_of(u['balance_sec'])
            fehlt = credits_of(need) - have
            raise HTTPException(
                402,
                f"Not enough credits (video costs {credits_of(need)} "
                f"credit{'s' if credits_of(need) != 1 else ''}, you have "
                f"{have}). Missing {max(1, fehlt)} - please top up.")
    if j.get('status') in ('wartet', 'laeuft'):
        # Pre-Transkription laeuft noch: Auftrag hinterlegen, der Worker
        # reiht danach selbst ein. Race-sicher ueber atomares dict.pop
        # (siehe run_job) - nachpruefen, ob der Worker GENAU jetzt fertig
        # wurde und den Auftrag nicht mehr gesehen hat.
        j['next_mode'] = mode
        if j.get('status') == 'vorbereitet' and j.pop('next_mode', None):
            j['mode'] = mode
            set_state(jid, status='wartet', progress=0.0, phase='Queued …')
            q_put(jid)
        return {'job': jid, 'chained': True}
    j['mode'] = mode
    set_state(jid, status='wartet', progress=0.0, phase='Queued …')
    q_put(jid)
    return {'job': jid, 'position': _queue_platz(jid, QUEUE)}


@app.get('/api/status/{jid}')
def status(jid: str, request: Request):
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        # State evtl. auf Platte
        sp = os.path.join(job_dir(jid), 'state.json')
        if os.path.exists(sp):
            return json.load(open(sp, encoding='utf-8'))
        raise HTTPException(404, 'Unknown job.')
    out = {k: v for k, v in j.items() if k not in ('input', 'code')}
    if j.get('status') == 'wartet':
        _q = MQUEUE if j.get('kind') == 'motion' else QUEUE
        platz = _queue_platz(jid, _q)
        out['queue_pos'] = platz
        out['phase'] = (f'Queued (position {platz} of {max(platz, _q.qsize())}) …'
                        if platz else 'Queued …')
    return out


def _job_owner_ok(jid, request):
    """v84: Nur der Ersteller darf ein Job-Video sehen. Jobs ohne user_id
    (Alt-Bestand / Code-Login) bleiben ueber die jid zugaenglich - die ist
    ohnehin ein nicht erratbares Geheimnis. Jobs MIT user_id sind privat."""
    j = JOBS.get(jid)
    if not j:
        sp = os.path.join(job_dir(jid), 'state.json')
        if os.path.exists(sp):
            try:
                j = json.load(open(sp, encoding='utf-8'))
            except Exception:
                j = None
    owner = (j or {}).get('user_id')
    if owner is None:
        return True
    u = _current_user(request)
    return bool(u and u['id'] == owner)


@app.get('/api/video/{jid}')
def video(jid: str, request: Request, download: int = 0):
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This video belongs to another account.')
    p = os.path.join(job_dir(jid), 'fertig.mp4')
    if not os.path.exists(p):
        raise HTTPException(404, 'Not ready yet.')
    # download=1 erzwingt den Speichern-Dialog; sonst inline (Library-Player).
    if download:
        # v171: die Job-ID gehoert in den Dateinamen. Vorher hiess JEDER
        # Download gleich - der Browser zaehlte nur _1/_2 hoch, und niemand
        # konnte unterscheiden, ob eine Datei aus einem neuen Render stammt
        # oder derselbe alte Download ist.
        return FileResponse(p, media_type='video/mp4',
                            filename=f'DouchkoVE_{jid[:8]}.mp4')
    # v142: der Library-Player spult und laedt Bereiche nach. 'private' - das
    # Video gehoert einem Konto und darf in keinem geteilten Cache landen.
    # Kurze Frist, weil ein Kauf das Wasserzeichen entfernt und dieselbe URL
    # danach eine andere Datei liefert.
    return FileResponse(p, media_type='video/mp4',
                        headers={'Cache-Control': 'private, max-age=600'})


@app.get('/api/contact/{jid}')
def contact_sheet_file(jid: str, request: Request):
    """v101g: Regie-Kontaktbogen - alle Momente des Renders als ein Grid-JPG
    (echte komponierte Frames). Liegt neben fertig.mp4."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This video belongs to another account.')
    p = os.path.join(job_dir(jid), 'fertig_kontakt.jpg')
    if not os.path.exists(p):
        raise HTTPException(404, 'No contact sheet for this job.')
    return FileResponse(p, media_type='image/jpeg',
                        filename='DouchkoVE_Moments.jpg')


@app.get('/api/poster/{jid}')
def poster(jid: str, request: Request):
    """v84: Standbild fuer die Library-Kachel. Beim ersten Abruf aus dem
    fertigen Video gegriffen und gecacht."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This video belongs to another account.')
    d = job_dir(jid)
    mp4 = os.path.join(d, 'fertig.mp4')
    if not os.path.exists(mp4):
        raise HTTPException(404, 'Not ready yet.')
    poster_path = os.path.join(d, 'poster.jpg')
    if not os.path.exists(poster_path):
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-v', 'error', '-ss', '0.8', '-i', mp4,
                 '-frames:v', '1', '-vf', 'scale=360:-2', poster_path],
                check=True, timeout=30)
        except Exception:
            raise HTTPException(404, 'No poster available.')
    # v142: Library-Kachel. Das Poster aendert sich nach dem Render nie mehr.
    return FileResponse(poster_path, media_type='image/jpeg',
                        headers={'Cache-Control': 'private, max-age=86400'})


@app.get('/api/library')
def api_library(request: Request):
    """v84: Private Bibliothek. Alle fertigen Renders des eingeloggten
    Users, abspielbar, mit Ablauf-Countdown (Auto-Loeschung nach
    RETENTION_DAYS)."""
    u = _require_user(request)
    items = []
    for jid, j in list(JOBS.items()):
        if j.get('user_id') != u['id']:
            continue
        # v230ae: waehrend eines EBENEN-Renders steht der Job wieder auf
        # 'wartet'/'laeuft' - das fertige Video verschwand dadurch komplett
        # aus der Bibliothek, obwohl die Datei da liegt. Ein laufender
        # Zusatz-Render darf das Ergebnis nicht wegnehmen.
        _alpha_run = (j.get('status') in ('wartet', 'laeuft')
                      and 'alpha' in j and j.get('alpha') is None)
        if j.get('status') != 'fertig' and not _alpha_run:
            continue
        d = job_dir(jid)
        mp4 = os.path.join(d, 'fertig.mp4')
        if not os.path.exists(mp4):
            continue
        try:
            finished = os.path.getmtime(mp4)
            expires = os.path.getmtime(d) + RETENTION_DAYS * 86400
        except OSError:
            continue
        items.append({
            'jid': jid,
            'name': j.get('name') or 'video.mp4',
            'dauer': j.get('dauer', 0),
            'created': int(finished),
            'expires_at': int(expires),
            'has_mov': os.path.exists(os.path.join(d, 'fertig.mov')),
            # v98: SRT-Button nur zeigen, wenn ein Transkript existiert
            'has_srt': bool(j.get('input')) and os.path.exists(
                os.path.splitext(j['input'])[0] + '_transcript2.json'),
            'wm': bool(j.get('wm')),
            # v101g: Regie-Kontaktbogen (Grid aller Momente) vorhanden?
            'kontakt': os.path.exists(os.path.join(d, 'fertig_kontakt.jpg')),
            # v101h: Caption-Ebene (ProRes 4444) schon gerendert? Quelle noch da
            # (sonst kann keine Ebene mehr gebaut werden)?
            'has_alpha': os.path.exists(os.path.join(d, 'fertig_captions.mov')),
            'can_alpha': bool(j.get('input')) and os.path.exists(j.get('input', '')),
            # v230ae: laeuft gerade ein Ebenen-Render? Sonst steht der Knopf
            # nach einem Neuladen wieder auf "Editor layer", obwohl der Job
            # laeuft - und ein zweiter Klick bekommt nur einen 409er.
            # Der Worker setzt `mode` sofort auf 'full' zurueck; der Marker
            # ist deshalb `alpha is None` waehrend Job laeuft/wartet.
            'alpha_running': _alpha_run,
            # v124: Scores fuer den Verlauf im Konto (Bestwert, Trend).
            'hook_score': int(j.get('hook_score') or 0),
            'silent_score': int(j.get('silent_score') or 0),
        })
    items.sort(key=lambda x: x['created'], reverse=True)
    return {'items': items, 'retention_days': RETENTION_DAYS}


@app.get('/api/moments/{jid}')
def get_moments(jid: str, request: Request):
    """Momente-Datei aus der Analyse laden."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
    if not os.path.exists(mom_path):
        raise HTTPException(404, 'Moments not analyzed yet.')
    return json.load(open(mom_path, encoding='utf-8'))


@app.get('/api/blocks/{jid}')
def get_blocks(jid: str, request: Request):
    """v193 Block-Editor: die Textbloecke eines Jobs, so wie sie im Video
    stehen werden. Eine Zeile im Editor = ein Eintrag hier."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    blk = os.path.splitext(j['input'])[0] + '_bloecke.json'
    if not os.path.exists(blk):
        raise HTTPException(404, 'Blocks not analyzed yet.')
    try:
        return json.load(open(blk, encoding='utf-8'))
    except Exception:
        raise HTTPException(404, 'Blocks not readable.')


# v193: erlaubte Werte. Der Riegel steht SERVERSEITIG, nicht nur in der
# Engine. /api/moments schrieb Nutzer-JSON bis v192 unveraendert auf die
# Platte - bei einem Editor mit zehn Feldern je Zeile ist das keine
# theoretische Luecke mehr, sondern der Normalfall.
_BLK_FX = ('', 'behind', 'cascade', 'blurin', 'outline', 'ground')
_BLK_MAX = 4000            # Bloecke je Job (3 Min Sprache sind rund 200)
_BLK_GLEICH = 4            # v203-sec: hoechstens so viele Bloecke gleichzeitig


def sanitize_blocks(roh, max_i=10 ** 6, dauer=None):
    """Blockplan auf erlaubte Werte reduzieren. Unbekannte Felder fallen weg,
    kaputte Eintraege werden uebersprungen - aber ein einzelner Fehler darf
    nie den ganzen Plan verwerfen (genau das passiert heute in render.py mit
    der Momente-Datei: EIN falscher Wert, und alle Nutzer-Einstellungen des
    Videos sind still weg)."""
    if not isinstance(roh, list):
        return []
    aus = []
    for b in roh[:_BLK_MAX]:
        if not isinstance(b, dict):
            continue
        try:
            i0, i1 = int(b.get('i0')), int(b.get('i1'))
        except (TypeError, ValueError):
            continue
        if not (0 <= i0 < i1 <= max_i):
            continue
        e = {'i0': i0, 'i1': i1, 'aktiv': b.get('aktiv', True) is not False}
        t = b.get('text')
        if isinstance(t, str) and t.strip():
            e['text'] = t.strip()[:200]
        a = str(b.get('anim') or '').strip().lower()
        if a and a in ANIM_IDS:
            e['anim'] = a
        f = str(b.get('fx') or '').strip().lower()
        if f in _BLK_FX and f:
            e['fx'] = f
        try:
            p = int(b.get('power') or 0)
            if p in (1, 2, 3):
                e['power'] = p
        except (TypeError, ValueError):
            pass
        try:
            g = float(b.get('groesse') or 0)
            if g > 0:
                e['groesse'] = round(max(0.5, min(2.0, g)), 3)
        except (TypeError, ValueError):
            pass
        # v203-sec: Bis v202 wurde nur gegen 36000 s geklemmt - nie gegen die
        # Laenge des Videos. Ein Kunde konnte JEDEN Block auf start=0/end=36000
        # setzen; dann ist in jedem Bild jeder Block aktiv, und die Zeichen-
        # schleife laeuft pro Bild ueber alle Woerter statt ueber drei. Aus
        # linearer Renderzeit wird quadratische - der EINE Worker haengt
        # stundenlang, alle anderen Kunden warten. Die Obergrenze ist jetzt die
        # bezahlte Videodauer (mit kleinem Zuschlag fuer das Ausklingen).
        _max_t = 36000.0 if not dauer else max(1.0, float(dauer)) + 5.0
        for k in ('start', 'end'):
            v = b.get(k)
            if v in (None, ''):
                continue
            try:
                e[k] = round(max(0.0, min(_max_t, float(v))), 3)
            except (TypeError, ValueError):
                pass
        if 'start' in e and 'end' in e and e['end'] <= e['start']:
            e.pop('start'), e.pop('end')
        aus.append(e)
    aus.sort(key=lambda x: (x['i0'], x['i1']))
    # Zweiter Riegel, unabhaengig von der Dauer: hoechstens _BLK_GLEICH Bloecke
    # duerfen sich EIN Zeitfenster teilen. Wer mehr setzt, verliert seine
    # eigenen Zeiten (Rueckfall auf die Wortzeiten) - die Bloecke bleiben.
    _offen = []
    for e in aus:
        if 'start' not in e or 'end' not in e:
            continue
        _offen = [o for o in _offen if o['end'] > e['start']]
        if len(_offen) >= _BLK_GLEICH:
            e.pop('start', None), e.pop('end', None)
            continue
        _offen.append(e)
    return aus


_MOM_FX = ('', 'behind', 'cascade', 'blurin', 'outline', 'ground', 'zoom')
_MOM_MAX = 2000


def sanitize_moments(roh):
    """v203-sec: Fuer 'blocks' gab es sanitize_blocks, fuer 'moments' im SELBEN
    Request nichts - der Nutzer-JSON ging unveraendert auf die Platte und von
    dort in die Engine. 'power' wurde dabei ungeklemmt uebernommen und geht
    linear in den Radius des Hintergrund-Blurs ein: ein grosser Wert ergibt
    einen Gauss-Kernel, dessen Berechnung pro BILD Minuten dauert. Ein einziger
    Render legt damit den einen Worker lahm.

    Gleiche Bauart wie sanitize_blocks: unbekannte Felder fallen weg, ein
    kaputter Eintrag wird uebersprungen und verwirft NIE den ganzen Plan.

    v230g DIE FORM WAR DIE FALSCHE - UND DAMIT WAR DER GANZE EDITOR TOT.
    `_momente.json` ist eine LISTE von Eintraegen mit dem Wort-Index im Feld
    'i'; so schreibt render.py sie (13655), so liest render.py sie zurueck
    (`{m['i']: m for m in json.load(...)}`), so liefert `/api/moments/{jid}`
    sie an die App, und genau so schickt die App sie zurueck. Diese Funktion
    verlangte ein Dict und stieg bei allem anderen mit `{}` aus - der Server
    hat die Datei danach mit `{}` ueberschrieben. Ergebnis: JEDER Klick im
    Momente-Editor (Effekt, Animation, Wucht, Text, Moment abschalten) ging
    beim Speichern verloren, und der Re-Render war bitgleich zum Original.
    `aktiv` fehlte ausserdem in der Allowlist - ein abgeschalteter Moment
    liess sich also selbst dann nicht abschalten, wenn die Form gestimmt
    haette. Beides gemessen: Datei nach dem Speichern exakt `{}`, mittlere
    Bilddifferenz Original gegen "gespeicherten" Re-Render 0.000.
    Die Dict-Form wird weiter angenommen (Alt-Clients), aber immer als LISTE
    zurueckgegeben - das ist die Form, die Engine und App sprechen."""
    if isinstance(roh, dict):
        # Alt-Form {"12": {...}} -> Liste mit 'i'
        roh = [dict(m, i=k) for k, m in roh.items() if isinstance(m, dict)]
    if not isinstance(roh, list):
        return []
    aus = []
    for m in roh[:_MOM_MAX]:
        if not isinstance(m, dict):
            continue
        try:
            i = int(m.get('i'))
        except (TypeError, ValueError):
            continue
        if not 0 <= i <= 10 ** 6:
            continue
        e = {'i': i}
        f = str(m.get('fx') or '').strip().lower()
        if f in _MOM_FX and f:
            e['fx'] = f
        try:
            p = int(m.get('power') or 0)
            if p in (1, 2, 3):
                e['power'] = p
        except (TypeError, ValueError):
            pass
        try:
            n = int(m.get('n') or 0)
            if 1 <= n <= 8:
                e['n'] = n
        except (TypeError, ValueError):
            pass
        a = str(m.get('anim') or '').strip().lower()
        if a and a in ANIM_IDS:
            e['anim'] = a
        for feld, erlaubt in (('szene', ('', 'wasser', 'boden', 'wand', 'himmel',
                                         'person')),
                              ('lage', ('', 'liegend', 'stehend', 'frei'))):
            v = str(m.get(feld) or '').strip().lower()
            if v in erlaubt and v:
                e[feld] = v
        for feld, laenge in (('text', 200), ('emoji', 16), ('objekt', 60)):
            v = m.get(feld)
            if isinstance(v, str) and v.strip():
                e[feld] = v.strip()[:laenge]
        for feld in ('nah', 'intent', 'user_pick'):
            if m.get(feld) is True:
                e[feld] = True
        # v230g: 'aktiv' ist der Schalter "Moment abschalten" - er MUSS auch
        # als False durchkommen, sonst laesst sich nichts abschalten. Die
        # anderen Flags oben sind Zusagen, die es nur als True gibt.
        if 'aktiv' in m:
            e['aktiv'] = bool(m.get('aktiv'))
        anker = m.get('anker')
        if isinstance(anker, (list, tuple)) and len(anker) == 2:
            try:
                e['anker'] = [round(max(0.0, min(1.0, float(anker[0]))), 4),
                              round(max(0.0, min(1.0, float(anker[1]))), 4)]
            except (TypeError, ValueError):
                pass
        aus.append(e)
    return aus


@app.get('/api/accents/{jid}')
def get_accents(jid: str, request: Request):
    """v101t: Auto-Akzent-Plan eines Jobs (dezente Motion-Graphics) fuer den
    Momente-Editor. Leere Liste, wenn (noch) keiner erzeugt wurde."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    acc_path = os.path.splitext(j['input'])[0] + '_accents.json'
    if not os.path.exists(acc_path):
        return []
    try:
        return json.load(open(acc_path, encoding='utf-8'))
    except Exception:
        return []


TEMPLATES_PATH = os.path.join(DATA, 'templates.json')


def _load_templates():
    if not os.path.exists(TEMPLATES_PATH):
        return {}
    try:
        return json.load(open(TEMPLATES_PATH, encoding='utf-8'))
    except Exception:
        return {}


def _save_templates(data):
    os.makedirs(DATA, exist_ok=True)
    json.dump(data, open(TEMPLATES_PATH, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


def _tpl_owner(code, request):
    """v80h: Templates werden pro User (Email) gespeichert wenn eingeloggt,
    sonst pro Code als Fallback."""
    u = _current_user(request) if request else None
    if u:
        return 'u:' + u['email']
    return code


@app.get('/api/templates')
def list_templates(request: Request, code: str = ''):
    ok, _ = check_auth(code, request)
    if not ok:
        return {'templates': []}
    all_ = _load_templates()
    return {'templates': all_.get(_tpl_owner(code, request), [])}


@app.post('/api/templates')
async def save_template(request: Request, name: str = Form(...),
                        settings: str = Form(...), code: str = Form('')):
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    name = name.strip()[:60]
    if not name:
        raise HTTPException(400, 'Name is missing.')
    try:
        payload = json.loads(settings)
    except Exception:
        raise HTTPException(400, 'Settings JSON invalid.')
    owner = _tpl_owner(code, request)
    all_ = _load_templates()
    entries = all_.setdefault(owner, [])
    entries = [e for e in entries if e.get('name') != name]
    entries.append({'name': name, 'settings': payload})
    all_[owner] = entries[-20:]
    _save_templates(all_)
    return {'ok': True, 'count': len(all_[owner])}


@app.delete('/api/templates/{name}')
def delete_template(request: Request, name: str, code: str = ''):
    ok, _ = check_auth(code, request)
    if not ok:
        raise HTTPException(403, 'Not signed in.')
    owner = _tpl_owner(code, request)
    all_ = _load_templates()
    entries = [e for e in all_.get(owner, []) if e.get('name') != name]
    all_[owner] = entries
    _save_templates(all_)
    return {'ok': True}


@app.get('/api/transcript/{jid}')
def get_transcript(jid: str, request: Request):
    """v80y: Transkript zum Korrigieren laden."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    tp = os.path.splitext(j['input'])[0] + '_transcript2.json'
    if not os.path.exists(tp):
        # v138: Fertig-ohne-Datei ODER explizites tx_failed = die Vorab-
        # Transkription ist GESCHEITERT -> das dem Client sagen (failed:true),
        # statt ewig 404 (= 'poll weiter'). 404 nur solange wirklich noch
        # gearbeitet wird. Nicht fatal: der volle Render transkribiert selbst.
        still_working = (j.get('mode') == 'pre'
                         and j.get('status') in ('wartet', 'laeuft'))
        if j.get('tx_failed') or (not still_working
                                  and j.get('status') == 'vorbereitet'):
            return {'words': [], 'failed': True}
        raise HTTPException(404, 'Transcript not ready yet.')
    return {'words': json.load(open(tp, encoding='utf-8'))}


def _srt_cues(words, max_chars=42, max_dur=5.0, gap_break=0.8):
    """v98: Wort-Timings -> Untertitel-Cues. Neue Zeile bei Satzende,
    Sprechpause >0.8s, 42 Zeichen (Netflix-Richtwert) oder 5s Standzeit."""
    cues, cur, t0, t1 = [], [], None, None
    for w in words:
        txt = str(w.get('word', '')).strip()
        if not txt:
            continue
        ws, we = float(w.get('start', 0.0)), float(w.get('end', 0.0))
        if cur and (len(' '.join(cur + [txt])) > max_chars
                    or ws - t1 > gap_break or we - t0 > max_dur):
            cues.append((t0, t1, ' '.join(cur)))
            cur, t0 = [], None
        if t0 is None:
            t0 = ws
        cur.append(txt)
        t1 = we
        if txt[-1:] in '.!?':
            cues.append((t0, t1, ' '.join(cur)))
            cur, t0 = [], None
    if cur:
        cues.append((t0, t1, ' '.join(cur)))
    return cues


def _srt_ts(t, vtt=False):
    ms = int(round(max(0.0, float(t)) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{'.' if vtt else ','}{ms:03d}"


@app.get('/api/subtitles/{jid}')
def get_subtitles(jid: str, request: Request, fmt: str = 'srt'):
    """v98: SRT/VTT-Export des Transkripts - Standard bei jeder Konkurrenz,
    Creator brauchen die Datei fuer YouTube/Schnittprogramme. Kostenlos
    (Transkript ist beim Render eh bezahlt worden)."""
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    tp = os.path.splitext(j['input'])[0] + '_transcript2.json'
    if not os.path.exists(tp):
        raise HTTPException(404, 'Transcript not ready yet.')
    vtt = (fmt == 'vtt')
    cues = _srt_cues(json.load(open(tp, encoding='utf-8')))
    if not cues:
        raise HTTPException(404, 'Transcript is empty.')
    out = ['WEBVTT', ''] if vtt else []
    for i, (a, b, txt) in enumerate(cues, 1):
        if not vtt:
            out.append(str(i))
        out.append(f'{_srt_ts(a, vtt)} --> {_srt_ts(b, vtt)}')
        out.append(txt)
        out.append('')
    ext = 'vtt' if vtt else 'srt'
    return Response(
        content='\n'.join(out),
        media_type='text/vtt' if vtt else 'application/x-subrip',
        headers={'Content-Disposition':
                 f'attachment; filename="captions.{ext}"'})


@app.post('/api/transcript/{jid}')
async def save_transcript(request: Request, jid: str,
                          edits: str = Form(...), code: str = Form(''),
                          reanalyze: str = Form('1'), kwmarks: str = Form('')):
    """v80y: Wort-Korrekturen speichern (nur Text, Timings bleiben),
    Regie-/Momente-Cache invalidieren, Analyse neu starten.
    v101l: reanalyze=0 (Wizard-Schritt VOR dem Render) speichert nur - kein
    Re-Analyse-Umweg; der folgende Voll-Render zieht den korrigierten Text
    automatisch aus dem Cache."""
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    try:
        changes = json.loads(edits)
        assert isinstance(changes, list)
    except Exception:
        raise HTTPException(400, 'Edits JSON invalid.')
    base = os.path.splitext(j['input'])[0]
    tp = base + '_transcript2.json'
    if not os.path.exists(tp):
        raise HTTPException(404, 'Transcript not ready yet.')
    words = json.load(open(tp, encoding='utf-8'))
    n = 0
    for ch in changes:
        try:
            i = int(ch['i']); w = str(ch['word'])[:60]
        except Exception:
            continue
        if 0 <= i < len(words) and w.strip():
            words[i]['word'] = w
            n += 1
    json.dump(words, open(tp, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    # v101m: Keyword-Markierungen (Text-Editor) als Sidecar neben dem Input.
    # {index: 1|-1} - erzwingen/entfernen. Nur gueltige Indizes/Werte, gedeckelt.
    kmp = base + '_kwmarks.json'
    if kwmarks:
        try:
            _km = json.loads(kwmarks)
            _clean = {str(int(k)): int(v) for k, v in dict(_km).items()
                      if int(v) in (1, -1) and 0 <= int(k) < len(words)}
            if _clean:
                json.dump(dict(list(_clean.items())[:400]),
                          open(kmp, 'w', encoding='utf-8'))
            elif os.path.exists(kmp):
                os.remove(kmp)                # alle Marken entfernt
        except Exception:
            pass
    # Caches weg - Regie + Momente basieren auf altem Text
    # v193: '_flow3.json' MUSS mit weg. Es ist ueber den ersten Wortindex
    # eines Chunks verschluesselt; nach einer Transkript-Korrektur kann sich
    # die Chunk-Bildung verschieben (Interpunktion, Wortlaenge), und die
    # gecachten Anker zeigen dann auf den falschen Block. _parse_flow_sel
    # verwirft das still - der Kunde verliert die KI-Anker, ohne es zu
    # merken. Der Blockplan bleibt bewusst STEHEN: er ist Nutzerarbeit, und
    # die Wortindizes aendern sich beim reinen Umschreiben eines Wortes nicht.
    for suffix in ('_regie3.json', '_momente.json', '_flow3.json'):
        try:
            os.remove(base + suffix)
        except OSError:
            pass
    if str(reanalyze) not in ('0', 'false', 'False', ''):
        # v203-sec: Der v127-sec-Flooding-Riegel stand nur in save_and_render,
        # nicht in diesem direkt benachbarten Pfad - derselbe Fehlertyp wie
        # v159/v170/v176 (Riegel am falschen Gate). Ohne ihn konnte ein Konto
        # denselben Job beliebig oft neu einreihen; jeder Lauf loescht vorher
        # den Regie-Cache, die KI-Regie lief also jedes Mal neu gegen die
        # OpenAI-API. Das kostet ECHTES Geld und blockiert den einen Worker.
        if j.get('status') in ('wartet', 'laeuft'):
            raise HTTPException(409, 'This job is already running.')
        _u_tr = _current_user(request)
        _enqueue_guard(_u_tr['id'] if _u_tr else None)
        j['mode'] = 'analyze'
        j['status'] = 'wartet'
        j['progress'] = 0.0
        j['phase'] = 'Queued (re-analyzing with corrected transcript) …'
        set_state(jid, **{k: v for k, v in j.items() if k not in ('input', 'code')})
        q_put(jid)
    return {'ok': True, 'changed': n}


@app.get('/api/thumb/{jid}/{name}')
def get_thumb(jid: str, name: str, request: Request):
    """Video-Frame-Preview fuer einen Moment (v80e). Wird im Momente-Editor
    hinter der Text-Preview eingeblendet, damit man sieht was zu dem
    Zeitpunkt wirklich im Bild ist."""
    from fastapi.responses import FileResponse
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    if (not (name.endswith('.jpg') or name.endswith('.png'))
            or '/' in name or '\\' in name or '..' in name):
        raise HTTPException(400, 'Invalid thumbnail name.')
    thumb_dir = os.path.splitext(j['input'])[0] + '_thumbs'
    thumb_path = os.path.join(thumb_dir, name)
    if not os.path.exists(thumb_path):
        raise HTTPException(404, 'Thumbnail not found.')
    # v142: Thumbs sind pro Job unveraenderlich. Der Momente-Editor laedt
    # dutzende davon - ohne Cache-Header holte der Browser sie bei jedem
    # Oeffnen neu. 'private', weil sie zu genau einem Konto gehoeren.
    return FileResponse(thumb_path,
                        media_type='image/png' if name.endswith('.png') else 'image/jpeg',
                        headers={'Cache-Control': 'private, max-age=86400'})


CORRECTIONS_PATH = os.path.join(DATA, 'corrections.json')

def _load_corrections():
    try:
        d = json.load(open(CORRECTIONS_PATH, encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []

def _capture_corrections(old_mom_path, edited, uid=None):
    """Vergleicht die neuen (editierten) Momente mit dem vorherigen Stand und
    speichert JEDE Aenderung (Effekt getauscht, Animation weg/gesetzt, Moment
    deaktiviert) global. Beim naechsten Render zieht die KI-Wahl automatisch
    dorthin nach (Phase 2 'aus Fehlern lernen', global). v124: Eintraege tragen
    zusaetzlich die user_id, damit das Konto zeigen kann, wie viel die Regie
    aus den EIGENEN Edits gelernt hat (das Lernen selbst bleibt global)."""
    if not os.path.exists(old_mom_path):
        return
    try:
        old = {m.get('i'): m for m in json.load(open(old_mom_path, encoding='utf-8'))}
    except Exception:
        return
    corr = _load_corrections()
    changed = 0
    for m in edited:
        o = old.get(m.get('i'))
        if o is None:
            continue
        phrase = (o.get('text') or m.get('text') or '').strip()
        if not phrase:
            continue
        rec = {}
        if m.get('fx') and str(m.get('fx')) != str(o.get('fx', '')):
            rec['user_fx'] = str(m['fx'])
            rec['orig_fx'] = str(o.get('fx', ''))   # v101e: From->To fuers Profil
        if str(m.get('anim', '')) != str(o.get('anim', '')):
            rec['user_anim'] = str(m.get('anim', ''))
        if bool(m.get('aktiv', True)) != bool(o.get('aktiv', True)):
            rec['user_aktiv'] = bool(m.get('aktiv', True))
        try:                                         # v101e: Wucht-Delta fuers Profil
            _op, _up = int(o.get('power')), int(m.get('power'))
            if _op != _up:
                rec['orig_power'], rec['user_power'] = _op, _up
        except (TypeError, ValueError):
            pass
        if rec:
            rec['phrase'] = phrase
            if uid:
                rec['user_id'] = uid
            corr.append(rec)
            changed += 1
    if changed:
        os.makedirs(DATA, exist_ok=True)
        json.dump(corr[-500:], open(CORRECTIONS_PATH, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print(f"Gelernt: {changed} Korrektur(en) gespeichert "
              f"({len(corr[-500:])} gesamt)")


@app.post('/api/moments/{jid}')
async def save_and_render(request: Request, jid: str,
                          moments: str = Form(...), code: str = Form(''),
                          accents: str = Form(''), blocks: str = Form('')):
    """Momente speichern und Voll-Render starten."""
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    if j.get('demo'):
        # v203-sec: siehe _finalize_upload. Ein Demo-Job hat nie jemand bezahlt
        # und gehoert keinem Konto - er darf nicht in einen vollen Render
        # umgeschrieben werden.
        raise HTTPException(403, 'Demo videos cannot be re-rendered. '
                                 'Create a free account and upload again.')
    # v127-sec: Re-Render ist "inklusive" (nicht erneut abgerechnet) - deshalb
    # hier gegen Missbrauch absichern: nicht doppelt einreihen, waehrend schon
    # ein Render laeuft, und pro Konto nicht die Queue fluten (freie Renders auf
    # dem einzigen Worker). Sonst kann ein Kunde mit 1 bezahlten Job beliebig
    # oft gratis schweres Compositing ausloesen.
    if j.get('status') in ('wartet', 'laeuft'):
        raise HTTPException(409, 'A render for this job is already running.')
    _u0 = _current_user(request)
    _enqueue_guard(_u0['id'] if _u0 else None)
    try:
        mom = sanitize_moments(json.loads(moments))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, 'Moments JSON invalid.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
    # v92 Phase 2: aus dem Edit lernen. Diff gegen die VORHERIGE Momente-Datei
    # (KI-Original bzw. letzter Stand) - was der Nutzer aendert, wird global
    # gespeichert und beim naechsten Render automatisch beruecksichtigt.
    try:
        _u = _current_user(request)
        _capture_corrections(mom_path, mom, uid=(_u['id'] if _u else None))
    except Exception as e:
        print(f"Korrektur-Erfassung uebersprungen ({type(e).__name__})")
    json.dump(mom, open(mom_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    # v193 BLOCK-EDITOR: die Blockliste mitspeichern. Leerer String heisst
    # "nicht angefasst" (Alt-Clients, Momente-only-Aufrufe); "[]" heisst
    # ausdruecklich "keine Nutzer-Bloecke mehr, zurueck zur Automatik" -
    # dann wird die Datei geloescht statt eine leere Liste zu schreiben,
    # sonst haette der Nutzer ein Video ganz ohne Text.
    if blocks:
        try:
            _blk_roh = json.loads(blocks)
        except Exception:
            raise HTTPException(400, 'Blocks JSON invalid.')
        _blk = sanitize_blocks(_blk_roh, dauer=j.get('dauer'))
        _blk_path = base + '_bloecke.json'
        if _blk:
            json.dump(_blk, open(_blk_path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
        elif os.path.exists(_blk_path):
            os.remove(_blk_path)
        # Die Blockgrenzen bestimmen die Chunks. Der Flow-Cache ist ueber den
        # ERSTEN Wortindex eines Chunks verschluesselt - nach einer
        # Verschiebung zeigen seine Anker auf den falschen Block und fallen
        # still weg. Also mit wegwerfen, statt eine Altlast weiterzuschleppen.
        _f3 = base + '_flow3.json'
        if os.path.exists(_f3):
            try:
                os.remove(_f3)
            except OSError:
                pass
    # v101t: editierte Auto-Akzente mitspeichern (leerer String = unveraendert;
    # "[]" = der Nutzer hat bewusst alle entfernt). render.py laedt die Datei.
    if accents:
        try:
            _acc = json.loads(accents)
            if isinstance(_acc, list):
                json.dump(_acc, open(base + '_accents.json', 'w', encoding='utf-8'),
                          ensure_ascii=False, indent=1)
        except Exception:
            print('Akzent-Edit ignoriert (JSON ungueltig)')
    # v135a AUDIT-FIX (HIGH): Dieser Pfad war der Bezahl-Bypass. Der Editor-
    # Roundtrip (Upload 'pre' -> Analyse -> Momente speichern) queued den
    # Voll-Render, ohne je zu reservieren - die post-hoc-Abbuchung clampte
    # bei 0, zwei parallele Pre-Uploads ergaben ein Gratis-Video. Jetzt:
    # exakt derselbe Abbuch-Punkt wie in render_start, idempotent ueber die
    # 'Render {jid}'-Ledger-Zeile (Re-Render nach Edit bleibt inklusive).
    _uid = j.get('user_id')
    if _uid:
        _need = _job_cost(j)
        if not _render_charged(_uid, jid) and not _reserve_credits(_uid, _need, jid):
            _uu = _find_user_by_id(_uid)
            _have = credits_of(_uu['balance_sec'] if _uu else 0)
            _fehlt = credits_of(_need) - _have
            raise HTTPException(
                402,
                f"Not enough credits (video costs {credits_of(_need)} "
                f"credit{'s' if credits_of(_need) != 1 else ''}, you have "
                f"{_have}). Missing {max(1, _fehlt)} - please top up.")
    # Voll-Render mit den neuen Momenten
    j['mode'] = 'full'
    j['status'] = 'wartet'
    j['progress'] = 0.0
    j['phase'] = 'Queued (re-render) …'
    # v130-fix: Render-Zeitstempel fuer den neuen Pass zuruecksetzen, sonst
    # messen Avg-Renderzeit/ETA im Admin-Panel noch die Analyse-Phase mit.
    j['started_at'] = None
    j['finished_at'] = None
    set_state(jid, **{k: v for k, v in j.items()
                      if k not in ('input', 'code')})
    q_put(jid)
    return {'ok': True, 'job': jid, 'position': _queue_platz(jid, QUEUE)}


def _admin_ok(request: Request):
    key = os.environ.get('DVE_ADMIN', '').strip()
    given = request.headers.get('x-admin-key', '')
    # v203-sec: compare_digest auf str verlangt reines ASCII - ein Header mit
    # Umlaut oder Emoji warf einen TypeError und damit einen 500er (der seit
    # v197 auch noch eine Zeile in die alerts-Tabelle schrieb). Ueber Bytes
    # verglichen gibt es ein sauberes 403. Zeitkonstant bleibt es.
    return bool(key) and hmac.compare_digest(given.encode('utf-8', 'ignore'),
                                             key.encode('utf-8'))


def _owner_ok(request: Request):
    """v96p: Nur das Besitzer-Konto (OWNER_EMAIL) darf die Stil-Referenzen
    sehen/aendern - sie wirken global auf alle Renders. Ueber die Session, kein
    Extra-Key noetig. Hinweis: _current_user liefert eine sqlite3.Row - die hat
    KEIN .get(), darum Klammer-Zugriff (der .get()-Fehler war die 500-Ursache)."""
    u = _current_user(request)
    if not u:
        return False
    try:
        email = u['email']
        verified = u['verified']
    except Exception:
        return False
    # v127-sec: zusaetzlich verifiziert verlangen (Belt-and-Suspenders neben dem
    # Register-Block auf OWNER_EMAIL): Owner-Rechte nie an ein unbestaetigtes
    # Konto, das nur die richtige Adresse behauptet.
    return bool(verified) and str(email or '').strip().lower() == OWNER_EMAIL


def _reference_file():
    # v96x: EXAKT derselbe Pfad wie der Render (render._reference_store_path) -
    # sonst schreiben Web und Render bei fehlendem DVE_DATA (lokal/Windows) an
    # zwei verschiedene Orte und der Render findet das Gelernte nie. Im Docker
    # (DVE_DATA=/data) identisch mit DATA/regie_reference.json.
    try:
        import render as _R
        return _R._reference_store_path()
    except Exception:
        return os.path.join(DATA, 'regie_reference.json')


def _load_references():
    try:
        d = json.load(open(_reference_file(), encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []


@app.get('/api/reference/diag')
def reference_diag(request: Request):
    """v96s: Umgebungs-Check fuer das Stil-Lernen (owner-only). GET ohne Upload -
    zeigt genau, warum /learn scheitert (Key, ffmpeg, render-Import, Schreibrecht)."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    import shutil as _sh
    out = {'build': DVE_BUILD, 'openai_key': bool(os.environ.get('OPENAI_API_KEY')),
           'ffmpeg': bool(_sh.which('ffmpeg')), 'ffprobe': bool(_sh.which('ffprobe')),
           'data_writable': os.access(DATA, os.W_OK)}
    rf = _reference_file()
    out['ref_file'] = rf
    out['ref_dir_writable'] = os.access(os.path.dirname(rf), os.W_OK)
    out['ref_file_writable'] = (os.access(rf, os.W_OK) if os.path.exists(rf)
                                else out['ref_dir_writable'])
    try:
        d = os.path.join(DATA, 'reftmp')
        os.makedirs(d, exist_ok=True)
        _t = os.path.join(d, 'diag.txt')
        open(_t, 'w').write('ok'); os.remove(_t)
        out['tmp_writable'] = True
    except Exception as e:
        out['tmp_writable'] = f'{type(e).__name__}: {e}'
    try:
        import render as _R
        out['render_import'] = True
        out['has_analyze'] = hasattr(_R, 'analyze_reference_video')
    except Exception as e:
        out['render_import'] = f'{type(e).__name__}: {e}'
    return out


@app.get('/api/reference/list')
def reference_list(request: Request):
    """v96o: gelernte Stil-Referenzen (Admin). Global - beeinflusst ALLE Renders."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    return {'refs': _load_references()}


@app.post('/api/reference/learn')
async def reference_learn(request: Request, datei: UploadFile = File(...),
                          name: str = Form('')):
    """v96o: Referenz-Video hochladen -> GPT-5 (Vision) beschreibt den Stil ->
    als Stil-Referenz speichern. Nur Besitzer-Konto, da global wirksam."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv'):
        raise HTTPException(400, 'Only video files (mp4, mov, webm, mkv).')
    tmp = None
    try:
        d = os.path.join(DATA, 'reftmp')
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, uuid.uuid4().hex[:10] + ext)
        groesse = 0
        with open(tmp, 'wb') as f:
            while True:
                chunk = await datei.read(1 << 20)
                if not chunk:
                    break
                groesse += len(chunk)
                if groesse > 200 * 1024 * 1024:
                    raise HTTPException(413, 'Reference video too large (max 200 MB).')
                f.write(chunk)
        if not os.environ.get('OPENAI_API_KEY'):
            raise HTTPException(400, 'Server has no OPENAI_API_KEY set - the AI '
                                     'cannot look at the video. Set it in the '
                                     'server environment and try again.')
        import render as _R
        import asyncio as _aio3
        # v142 ASYNC: analyze_reference_video zieht Frames mit ffmpeg und fragt
        # danach die Vision-KI - zusammen leicht eine Minute. Bisher stand die
        # gesamte Seite fuer alle Nutzer, solange das lief.
        entry = await _aio3.to_thread(
            _R.analyze_reference_video,
            tmp, name=(_safe_name(name) or _safe_name(datei.filename or 'Referenz')))
        if not entry:
            raise HTTPException(502, 'The AI could not analyze this video '
                                     '(no frames extracted or the vision request '
                                     'failed). Try a shorter mp4.')
        return {'entry': entry, 'refs': _load_references()}
    except HTTPException:
        raise
    except Exception as e:
        # Owner-only Endpoint -> echten Grund zeigen, damit man es diagnostizieren kann.
        raise HTTPException(500, f'{type(e).__name__}: {e}')
    finally:
        if tmp:
            try: os.remove(tmp)
            except OSError: pass


@app.post('/api/reference/delete')
def reference_delete(request: Request, idx: int = Form(...)):
    """v96o: eine gelernte Stil-Referenz loeschen (nur Besitzer-Konto)."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    refs = _load_references()
    if 0 <= idx < len(refs):
        refs.pop(idx)
        try:
            json.dump(refs, open(_reference_file(), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
        except Exception:
            raise HTTPException(500, 'Could not save.')
    return {'refs': refs}


# ================================================================
# v126 Kunden-Stil: jedes Konto kann der Regie den eigenen Wunsch-Stil aus
# Referenz-Videos anlernen. Persoenliche Referenzen uebersteuern beim Render
# den globalen Haus-Stil (DVE_REFS_FILE im Render-Subprozess). Lernen kostet
# 1 Credit; schlaegt die Analyse fehl, gibt es ihn zurueck.
# ================================================================
STYLE_LEARN_COST = 60           # 1 Credit pro gelerntem Stil
STYLE_MAX = 6                   # max. gespeicherte Stile pro Konto


def _user_refs_path(uid):
    """Persoenliche Stil-Referenz-Datei eines Kontos (None ohne uid)."""
    if not uid:
        return None
    d = os.path.join(DATA, 'refs')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'user_{int(uid)}.json')


def _load_user_refs(uid):
    p = _user_refs_path(uid)
    try:
        refs = json.load(open(p, encoding='utf-8')) if p and os.path.exists(p) else []
        return refs if isinstance(refs, list) else []
    except Exception:
        return []


def _refs_for_job(uid):
    """v141: entscheidet EXPLIZIT, welche Stil-Referenz-Datei ein Render-
    Subprozess sieht, und woher sie stammt. Rueckgabe (pfad, quelle) mit
    quelle in {'eigene','haus'}.

    Reihenfolge:
      1. persoenliche Referenzen des Kontos (/api/style/learn)     -> 'eigene'
      2. NUR fuer das Besitzer-Konto: die globale Haus-Datei, die
         /api/reference/learn schreibt                            -> 'eigene'
      3. sonst die mitgelieferten Repo-Defaults                   -> 'haus'

    Punkt 2 ist der Kern des v141-Fixes: vorher war die globale Datei der
    stille Fallback FUER ALLE - das Gelernte des Owners lief in jeden fremden
    Kundenschnitt. Jetzt bleibt sie auf das Konto beschraenkt, das sie fuellt.
    """
    _repo = os.path.join(ROOT, 'regie_reference.json')
    if not uid:
        return _repo, 'haus'
    p = _user_refs_path(uid)
    if p and os.path.exists(p) and _load_user_refs(uid):
        return p, 'eigene'
    row = None
    con = None
    try:
        con = _db()
        row = con.execute('SELECT email FROM users WHERE id=?', (uid,)).fetchone()
    except Exception:
        pass
    finally:
        if con is not None:
            try: con.close()
            except Exception: pass
    if row and str(row['email'] or '').strip().lower() == OWNER_EMAIL:
        g = _reference_file()
        if g and os.path.exists(g) and _load_references():
            return g, 'eigene'
    return _repo, 'haus'


@app.post('/api/style/learn')
async def style_learn(request: Request, datei: UploadFile = File(...),
                      name: str = Form('')):
    """Kunden-Stil anlernen: Referenz-Video hochladen, GPT-5 (Vision)
    beschreibt den Stil, Ergebnis landet in der PERSOENLICHEN Referenz-Datei.
    Kostet 1 Credit (atomar reserviert, Refund bei Fehlschlag)."""
    u = _require_user(request)
    if not u['verified']:
        raise HTTPException(403, 'Verify your email first.')
    if len(_load_user_refs(u['id'])) >= STYLE_MAX:
        raise HTTPException(409, f'You already have {STYLE_MAX} styles. '
                                 'Delete one first.')
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv'):
        raise HTTPException(400, 'Only video files (mp4, mov, webm, mkv).')
    # v144: KEIN Hard-Stop mehr ohne OpenAI-Key. Der wirksame Teil des
    # Stil-Lernens ist die MESSUNG aus Bild und Ton (Groesse, Hierarchie,
    # Zone, Satz, Farbe, Kamera, Schnitt, Sounddesign) - die laeuft lokal.
    # Ein API-Ausfall darf den Kunden nicht mehr komplett aussperren.
    sid = uuid.uuid4().hex[:10]
    if not _reserve_credits(u['id'], STYLE_LEARN_COST, f'style_{sid}',
                            grund=f'Style learn style_{sid} ({STYLE_LEARN_COST}s)'):
        raise HTTPException(402, 'Learning a style costs 1 credit.')
    tmp = None
    try:
        d = os.path.join(DATA, 'reftmp')
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, sid + ext)
        groesse = 0
        with open(tmp, 'wb') as f:
            while True:
                chunk = await datei.read(1 << 20)
                if not chunk:
                    break
                groesse += len(chunk)
                if groesse > 200 * 1024 * 1024:
                    raise HTTPException(413, 'Reference video too large (max 200 MB).')
                f.write(chunk)
        if groesse == 0:
            raise HTTPException(400, 'Empty upload.')
        import render as _R
        import asyncio as _aio4
        # v142 ASYNC: siehe /api/reference/learn - minutenlange Blockade des
        # Event-Loops, hier sogar auf einem Kunden-Endpunkt.
        entry = await _aio4.to_thread(
            _R.analyze_reference_video,
            tmp, name=(_safe_name(name) or _safe_name(datei.filename or 'Style')),
            store_path=_user_refs_path(u['id']))
        if not entry:
            raise HTTPException(502, 'The analysis could not read this video. '
                                     'Try a shorter mp4 with visible captions.')
        return {'entry': {'name': entry.get('name', ''),
                          'beispiel': entry.get('beispiel', ''),
                          'gemessen': entry.get('gemessen', '')},
                'refs': _style_public(_load_user_refs(u['id']))}
    except HTTPException:
        _refund_credits(u['id'], f'style_{sid}', STYLE_LEARN_COST,
                        resv_like=f'Style learn style_{sid} %')
        raise
    except Exception as e:
        _refund_credits(u['id'], f'style_{sid}', STYLE_LEARN_COST,
                        resv_like=f'Style learn style_{sid} %')
        raise HTTPException(500, f'{type(e).__name__}: {e}')
    finally:
        if tmp:
            try: os.remove(tmp)
            except OSError: pass


def _style_public(refs):
    """v144: was ein Konto von seinem gelernten Stil zu sehen bekommt. Neu
    dabei ist 'gemessen' - die Klartext-Zeile der Messung. Ohne sie bleibt
    'Stil gelernt' eine Behauptung, die der Kunde nicht pruefen kann.
    Rohdaten (params/messung) gehen NICHT raus."""
    return [{'name': str(r.get('name', '')),
             'beispiel': str(r.get('beispiel', ''))[:240],
             'gemessen': str(r.get('gemessen', ''))[:400]}
            for r in (refs or []) if isinstance(r, dict)]


@app.get('/api/style/list')
def style_list(request: Request):
    """Eigene gelernte Stile (nur Name + Kurzbeschreibung, keine Rohdaten)."""
    u = _require_user(request)
    return {'refs': _style_public(_load_user_refs(u['id'])),
            'max': STYLE_MAX, 'cost_credits': STYLE_LEARN_COST // 60}


@app.post('/api/style/delete')
def style_delete(request: Request, idx: int = Form(...)):
    """Einen eigenen Stil loeschen (Index in der eigenen Liste)."""
    u = _require_user(request)
    refs = _load_user_refs(u['id'])
    if 0 <= idx < len(refs):
        refs.pop(idx)
        try:
            json.dump(refs, open(_user_refs_path(u['id']), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=2)
        except Exception:
            raise HTTPException(500, 'Could not save.')
    return {'refs': [{'name': str(r.get('name', '')),
                      'beispiel': str(r.get('beispiel', ''))[:240]}
                     for r in refs if isinstance(r, dict)]}


@app.post('/api/reference/transcribe')
async def reference_transcribe(request: Request, datei: UploadFile = File(...),
                               language: str = Form('auto')):
    """Admin/Owner-Werkzeug unter Reference: ein Video hochladen -> Whisper-Transkript
    (whisper-1, Wort-Timings ueber den Server-OPENAI_API_KEY) als Klartext, SRT, WebVTT
    und Wort-JSON zurueckgeben. NUR Besitzer-Konto (session-gated), kein Credit-Abzug."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.m4a', '.mp3', '.wav', '.aac'):
        raise HTTPException(400, 'Upload a video or audio file.')
    if not os.environ.get('OPENAI_API_KEY'):
        raise HTTPException(400, 'Server has no OPENAI_API_KEY set - transcription needs it.')
    lang = (language or 'auto').strip().lower()
    if not re.match(r'^[a-z]{2}$', lang):
        lang = 'auto'
    d = os.path.join(DATA, 'reftmp')
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, uuid.uuid4().hex[:10] + ext)
    apath = src + '.m4a'
    try:
        groesse = 0
        with open(src, 'wb') as f:
            while True:
                chunk = await datei.read(1 << 20)
                if not chunk:
                    break
                groesse += len(chunk)
                if groesse > 300 * 1024 * 1024:
                    raise HTTPException(413, 'File too large (max 300 MB).')
                f.write(chunk)
        if groesse == 0:
            raise HTTPException(400, 'Empty upload.')
        # schlanke Mono-16kHz-Spur ziehen (Whisper-Limit 25 MB); Bitrate nach Laenge.
        # v142 ASYNC: ffprobe, ffmpeg und der Whisper-Upload sind alle drei
        # blockierend und zusammen minutenlang. Im Event-Loop legten sie den
        # kompletten Server still - jetzt im Threadpool.
        import asyncio as _aio5
        try:
            _pr = await _aio5.to_thread(
                subprocess.run,
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', src],
                capture_output=True, text=True, timeout=30)
            dur = float((_pr.stdout or '0').strip() or 0)
        except Exception:
            dur = 0.0
        _br = max(24, min(96, int(24 * 8192 / max(dur, 1.0)))) if dur else 64
        _ar = await _aio5.to_thread(
            subprocess.run,
            ['ffmpeg', '-y', '-v', 'error', '-i', src, '-vn', '-ac', '1',
             '-ar', '16000', '-c:a', 'aac', '-b:a', f'{_br}k', apath],
            capture_output=True, text=True, timeout=300)
        if not os.path.exists(apath) or os.path.getsize(apath) < 200:
            raise HTTPException(400, 'No usable audio track in this file. '
                                     + (_ar.stderr or '')[-200:])
        words = await _aio5.to_thread(_whisper_words, apath, lang)
        if not words:
            raise HTTPException(502, 'No speech found in this file.')
        return {'ok': True, 'language': lang, 'duration': round(dur, 2),
                'word_count': len(words), 'text': _words_to_text(words),
                'srt': _words_to_srt(words, vtt=False),
                'vtt': _words_to_srt(words, vtt=True), 'words': words}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f'{type(e).__name__}: {e}')
    finally:
        for _p in (src, apath):
            try: os.remove(_p)
            except OSError: pass


@app.get('/admin/codes')
def admin_codes(request: Request):
    """v92-sec: Admin-Schluessel jetzt (1) ohne erratbaren Default 'admin'
    (fehlt DVE_ADMIN -> Endpoint tot), (2) per Header X-Admin-Key statt
    Query-Parameter (landet sonst in Access-Logs/History/Referer),
    (3) timing-safe verglichen."""
    # v230d-sec: DIESELBE PRUEFUNG WIE UEBERALL. Hier stand noch der alte
    # str-Vergleich - und `hmac.compare_digest` auf Strings wirft bei einem
    # Header mit Umlaut einen TypeError. Ergebnis: ein anonymer Aufruf mit
    # einem Nicht-ASCII-Zeichen im Schluessel erzeugte einen 500er, und seit
    # v197 schreibt jeder 500er eine Zeile mit vollem Traceback in die
    # alerts-Tabelle derselben Datenbank, in der die Konten liegen (gemessen
    # 452 KB je 100 Aufrufe, ohne Anmeldung, ohne Bremse). v203-sec hat genau
    # das in `_admin_ok` behoben - aber nur dort. Ein Riegel, den nur die
    # halbe Nachbarschaft hat, ist keiner.
    _require_admin(request)
    return load_codes()


# ============================================================ v128 Admin-Panel
# Tier 1: Betrieb (Health/Jobs) + Nutzer/Credits + Umsatz. ALLE Endpoints haengen
# am Server-Schluessel DVE_ADMIN (Header X-Admin-Key, timing-safe) - NICHT an der
# Owner-Session. Fehlt DVE_ADMIN, ist das ganze Panel tot (kein erratbarer Default).


def _require_admin(request: Request):
    """v203-sec: Der Admin-Key war die einzige Schranke vor Aktionen, die seit
    v197b ALLE Konten ersetzen koennen (backup/upload) - und er hatte weder
    Bremse noch Spur. Der Kunden-Login ist seit v92 mit 20 Versuchen/15 min
    gedeckelt; der maechtigere Zugang war ungebremst durchprobierbar, und ein
    Fehlversuch hinterliess nichts, was Ismet je gesehen haette.
    Jetzt: 10 Fehlversuche pro Viertelstunde und IP, danach dicht - und die
    erste Meldung landet im Panel (der 1-Stunden-Deckel in _notify_admin
    verhindert die Flut). Ein RICHTIGER Key laeuft nicht ins Limit, weil nur
    Fehlversuche gezaehlt werden."""
    if _admin_ok(request):
        # v204-sec: Zentral hier, damit kein neuer Admin-Endpunkt das
        # Protokollieren vergessen kann - derselbe Gedanke wie beim
        # Riegel selbst.
        try:
            _sec_event('admin', request, wer='admin',
                       ziel=getattr(getattr(request, 'url', None), 'path', ''),
                       detail=getattr(request, 'method', ''))
        except Exception:
            pass
        return
    _sec_event('admin_fehlversuch', request, wer='anon',
               ziel=getattr(getattr(request, 'url', None), 'path', ''))
    # Die Bremse darf den Riegel nie ersetzen: scheitert die IP-Ermittlung
    # (exotischer Aufrufer, interner Aufruf ohne Verbindung), gilt weiterhin
    # 403. Ein 500er an dieser Stelle waere schlimmer als keine Bremse.
    try:
        ip = _client_ip(request)
    except Exception:
        ip = 'unknown'
    if not _rate_limit_ok(ip, window_sec=900, max_attempts=10, bucket='admin'):
        _notify_admin('adminfail', 'Admin-Key wird durchprobiert',
                      f'Mehr als 10 falsche Admin-Keys in 15 Minuten von {ip}.\n'
                      f'Weitere Versuche von dieser Adresse werden abgewiesen.\n'
                      f'Wenn das nicht du warst: DVE_ADMIN in der .env aendern '
                      f'und den Container neu starten.', mail=False)
        raise HTTPException(429, 'Too many attempts.')
    raise HTTPException(403, 'Admin key missing or wrong.')


def _admin_purchaser_ids():
    con = _db()
    rows = con.execute("SELECT DISTINCT user_id FROM ledger WHERE grund LIKE 'Kauf %'").fetchall()
    con.close()
    return {r['user_id'] for r in rows}


# ---- v130 admin helpers (grounded read-side) ----
# v205-sec: Die Bauteile, die fremde Dateien anfassen, stehen zuerst - bei
# ihnen ist eine alte Version am teuersten.
_PAKETE_WICHTIG = ('opencv-python', 'opencv-python-headless', 'Pillow',
                   'onnxruntime', 'mediapipe', 'numpy', 'protobuf',
                   'fastapi', 'uvicorn', 'starlette', 'python-multipart',
                   'requests', 'PyYAML', 'bcrypt', 'stripe', 'httpx')


def _paket_versionen():
    """Welche Version welchen Bauteils laeuft WIRKLICH? Aus dem laufenden
    Prozess gelesen, nicht aus requirements.txt - die sagt bei den meisten
    ohnehin nur "irgendeine"."""
    try:
        import importlib.metadata as _md
    except Exception:
        return {}
    aus = {}
    for name in _PAKETE_WICHTIG:
        try:
            aus[name] = _md.version(name)
        except Exception:
            continue
    return aus


def _laufzeit_info():
    """Laeuft der Dienst als root oder als Dienst-Nutzer? Das ist die einzige
    ehrliche Probe fuer die v204-Haertung - die Meldung des Entrypoints geht
    nach `docker logs` und ist nach dem naechsten Deploy weg."""
    import platform as _pf
    try:
        uid = os.getuid()
    except Exception:
        uid = -1
    nutzer = ''
    try:
        import pwd as _pwd
        nutzer = _pwd.getpwuid(uid).pw_name
    except Exception:
        nutzer = os.environ.get('USER', '')
    return {'user': nutzer, 'uid': uid, 'root': uid == 0,
            'python': _pf.python_version(), 'plattform': _pf.platform()[:80],
            'ffmpeg': _ffmpeg_version()}


def _ffmpeg_version():
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True,
                           text=True, timeout=5)
        return (r.stdout or '').split('\n')[0][:60]
    except Exception:
        return 'unbekannt'


def _disk_info():
    try:
        du = shutil.disk_usage(DATA)
        return {'free_gb': round(du.free / 2 ** 30, 1), 'total_gb': round(du.total / 2 ** 30, 1),
                'used_pct': round(100 * du.used / du.total)}
    except Exception:
        return None


def _mem_info():
    """v230aj: Wieviel Speicher hat dieser Container, und was ist gerade frei?
    Ohne diese Zahl war 'der Render ist gestorben' nicht von 'zu wenig RAM'
    zu unterscheiden - und Ismet geht nicht ins Terminal. cgroup v2 zuerst,
    v1 als Rueckfall, sonst die Maschine (MemTotal/MemAvailable)."""
    def lies(p):
        try:
            return open(p).read().strip()
        except OSError:
            return ''
    out = {'limit_gb': None, 'used_gb': None, 'host_gb': None, 'frei_gb': None}
    for lim, cur in (('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
                     ('/sys/fs/cgroup/memory/memory.limit_in_bytes',
                      '/sys/fs/cgroup/memory/memory.usage_in_bytes')):
        roh = lies(lim)
        if roh and roh != 'max':
            try:
                n = int(roh)
            except ValueError:
                continue
            if 0 < n < (1 << 62):
                out['limit_gb'] = round(n / 2 ** 30, 1)
                try:
                    out['used_gb'] = round(int(lies(cur) or 0) / 2 ** 30, 2)
                except ValueError:
                    pass
                break
    try:
        for zeile in open('/proc/meminfo'):
            if zeile.startswith('MemTotal:'):
                out['host_gb'] = round(int(zeile.split()[1]) / 2 ** 20, 1)
            elif zeile.startswith('MemAvailable:'):
                out['frei_gb'] = round(int(zeile.split()[1]) / 2 ** 20, 1)
    except OSError:
        pass
    return out


def _last_backup_ts():
    try:
        bdir = os.path.join(DATA, 'backups')
        snaps = [os.path.join(bdir, f) for f in os.listdir(bdir) if f.startswith('users_')]
        return int(max(os.path.getmtime(s) for s in snaps)) if snaps else None
    except Exception:
        return None


def _db_size_mb():
    try:
        return round(os.path.getsize(USERS_DB) / 2 ** 20, 1)
    except Exception:
        return None


def _stripe_health():
    skey = os.environ.get('STRIPE_SECRET_KEY', '').strip()
    return {'ready': _stripe() is not None,
            'mode': 'live' if skey.startswith('sk_live_') else ('test' if skey else 'none'),
            'webhook_secret': bool(os.environ.get('STRIPE_WEBHOOK_SECRET', '').strip())}


def _mail_health():
    if os.environ.get('RESEND_API_KEY', '').strip():
        transport = 'resend'
    elif os.environ.get('SMTP_USER', '').strip():
        transport = 'smtp'
    else:
        transport = 'none'
    return {'transport': transport, 'from': os.environ.get('MAIL_FROM', ''), 'admin_to': ADMIN_MAIL}


def _admin_email(uid):
    if not uid:
        return None
    u = _find_user_by_id(uid)
    return u['email'] if u else None


def _sum_grund(con, like, sign=0):
    q = "SELECT COALESCE(SUM(delta_sec),0) s FROM ledger WHERE grund LIKE ?"
    if sign > 0:
        q += " AND delta_sec > 0"
    elif sign < 0:
        q += " AND delta_sec < 0"
    return con.execute(q, (like,)).fetchone()['s']


def _revrow(con, since, until=None):
    # v206: Zusaetzlich zu 'eingenommen' auch 'erstattet' und 'geblieben'.
    # Bis v205 gab es nur die Brutto-Zahl - die sagt, was Kunden gezahlt
    # haben, nicht was geblieben ist.
    if until is None:
        r = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents, "
                        "COALESCE(SUM(sekunden),0) sek FROM purchases WHERE created_at >= ?",
                        (since,)).fetchone()
        rr = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents "
                         "FROM refunds WHERE created_at >= ?", (since,)).fetchone()
    else:
        r = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents, "
                        "COALESCE(SUM(sekunden),0) sek FROM purchases "
                        "WHERE created_at >= ? AND created_at < ?", (since, until)).fetchone()
        rr = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents FROM refunds "
                         "WHERE created_at >= ? AND created_at < ?",
                         (since, until)).fetchone()
    _erst = int(rr['cents'] or 0)
    return {'count': r['c'],
            'eur': round(r['cents'] / 100.0, 2),          # eingenommen (brutto)
            'erstattet_eur': round(_erst / 100.0, 2),     # davon zurueckgezahlt
            'erstattungen': int(rr['c'] or 0),
            'netto_eur': round((r['cents'] - _erst) / 100.0, 2),   # geblieben
            'minutes': r['sek'] // 60}


@app.get('/admin', response_class=HTMLResponse)
def admin_page(request: Request):
    return _page('admin.html', request)


@app.get('/api/admin/overview')
def admin_overview(request: Request):
    """Live-Ops-Puls (Poll-Ziel, ~15s). Guenstig: purchases-Aggregat + In-Memory-
    Queues. Zeigt Umsatz, Signups, aktive Sessions, beide Queues, Liability,
    Jobs, System-Health-Ampel, aktive Alerts, Build."""
    _require_admin(request)
    now = int(time.time()); day = 86400
    con = _db()
    u_total = con.execute("SELECT COUNT(*) c FROM users").fetchone()['c']
    u_verif = con.execute("SELECT COUNT(*) c FROM users WHERE verified = 1").fetchone()['c']
    liability = con.execute("SELECT COALESCE(SUM(balance_sec),0) s FROM users").fetchone()['s']
    rev = {'today': _revrow(con, now - day), 'week': _revrow(con, now - 7 * day),
           'month': _revrow(con, now - 30 * day), 'total': _revrow(con, 0)}

    def _signup(since):
        return con.execute("SELECT COUNT(*) c FROM users WHERE created_at >= ?",
                           (since,)).fetchone()['c']
    signups = {'today': _signup(now - day), 'week': _signup(now - 7 * day),
               'month': _signup(now - 30 * day), 'total': u_total}
    sessions_active = con.execute("SELECT COUNT(*) c FROM sessions WHERE expires_at > ?",
                                  (now,)).fetchone()['c']
    rr = con.execute("SELECT COUNT(*) c, COALESCE(SUM(-delta_sec),0) s FROM ledger "
                     "WHERE grund LIKE 'Render %'").fetchone()
    tickets_open = con.execute("SELECT COUNT(*) c FROM tickets WHERE status='open'").fetchone()['c']
    feedback_offen = con.execute(
        "SELECT COUNT(*) c FROM feedback WHERE gelesen=0").fetchone()['c']   # v196
    con.close()
    purchasers = len(_admin_purchaser_ids())

    def _jstat(s):
        return sum(1 for j in list(JOBS.values()) if j.get('status') == s)
    stripe = _stripe_health()
    hb = dict(_HEARTBEAT)
    return {
        'now': now,
        'build': DVE_BUILD,
        # v222: nicht nur WELCHER Stand, sondern auch WIE ALT er ist. Ein
        # Deploy, der seit Tagen nicht mehr durchkam, war bisher unsichtbar -
        # autodeploy.sh meldet nur einen FEHLGESCHLAGENEN Versuch, nicht einen,
        # der nie stattfand (z.B. weil der Server auf einem anderen Branch
        # steht: dann sieht er "nichts Neues" und schweigt fuer immer).
        'deploy': _deploy_info(),
        'users': {'total': u_total, 'verified': u_verif, 'purchasers': purchasers,
                  'free': u_total - purchasers},
        'signups': signups,
        'sessions_active': sessions_active,
        'revenue': rev,
        'credits': {'liability_min': liability // 60},
        'renders': {'count': rr['c'], 'minutes': rr['s'] // 60},
        'jobs': {'waiting': _jstat('wartet'), 'running': _jstat('laeuft'),
                 'failed': _jstat('fehler'), 'queue': QUEUE.qsize(),
                 'motion_queue': MQUEUE.qsize()},
        'alerts_active': len(_ADMIN_NOTIFIED),
        'alerts_offen': _alerts_offen(),
        'tickets_open': tickets_open,                  # v133c
        'feedback_offen': feedback_offen,              # v196
        'system': {'disk': _disk_info(), 'db_mb': _db_size_mb(),
                   'last_backup': _last_backup_ts(),
                   'openai': _openai_health(),
                   'stripe': stripe, 'mail': _mail_health(),
                   'motion': bool(MOTION_BRIEF_OK),
                   'retention_days': RETENTION_DAYS,
                   'admin_key_set': bool(os.environ.get('DVE_ADMIN', '').strip()),
                   'heartbeats': {'watchdog': hb.get('watchdog'), 'cleanup': hb.get('cleanup')}},
    }


@app.get('/api/admin/alerts')
def admin_alerts(request: Request, limit: int = 100, offen: int = 0):
    """v147: Stoerungsliste. Ersetzt die Fehler-Mail - Render-Fehler und
    Timeouts stehen hier, nicht mehr im Postfach.

    v203-sec: Hier stand `_admin_ok(request)` als nackte Anweisung. `_admin_ok`
    gibt nur einen bool zurueck und WIRFT NICHT - der Rueckgabewert wurde
    verworfen, der Endpunkt war damit anonym aus dem Internet lesbar. Live
    nachgestellt: HTTP 200 ohne jeden Header. Seit v197 schreibt der globale
    Exception-Handler zusaetzlich jeden Traceback in genau diese Tabelle, dazu
    stehen dort Stripe-Session- und Charge-IDs, Job- und Konto-Nummern.
    Der Riegel heisst `_require_admin` - `_admin_ok` ist der bool-Test dahinter
    und darf NIE allein als Schranke stehen."""
    _require_admin(request)
    lim = min(max(int(limit), 1), 500)
    con = _db()
    q = ("SELECT id, schluessel, betreff, text, gemailt, gelesen, created_at "
         "FROM alerts ")
    if offen:
        q += "WHERE gelesen=0 "
    q += "ORDER BY created_at DESC LIMIT ?"
    rows = [dict(r) for r in con.execute(q, (lim,)).fetchall()]
    n_offen = con.execute("SELECT COUNT(*) c FROM alerts WHERE gelesen=0").fetchone()['c']
    con.close()
    return {'alerts': rows, 'offen': n_offen}


@app.post('/api/admin/alerts/read')
def admin_alerts_read(request: Request, id: int = Form(0)):
    """Eine Stoerung oder alle als gelesen markieren (id=0 -> alle).
    v203-sec: derselbe verworfene Rueckgabewert wie in admin_alerts - dieser
    Endpunkt SCHREIBT sogar und war anonym benutzbar (jemand konnte alle
    Stoerungsmeldungen abhaken, bevor Ismet sie sieht)."""
    _require_admin(request)
    con = _db()
    if int(id) > 0:
        con.execute("UPDATE alerts SET gelesen=1 WHERE id=?", (int(id),))
    else:
        con.execute("UPDATE alerts SET gelesen=1 WHERE gelesen=0")
    con.commit()
    n = con.execute("SELECT COUNT(*) c FROM alerts WHERE gelesen=0").fetchone()['c']
    con.close()
    return {'ok': True, 'offen': n}


@app.get('/api/admin/jobs')
def admin_jobs(request: Request):
    """Jobs-Poll-Ziel (~5s, In-Memory). Erweiterte Projektion + Status-
    Verteilung + Queue-Zusammensetzung + Durchschnitts-Renderzeit + At-Risk."""
    _require_admin(request)
    now = time.time()
    out = []; dist = {}; durations = []; paid_wait = 0; free_wait = 0
    for jid, j in list(JOBS.items()):
        st = j.get('status'); dist[st] = dist.get(st, 0) + 1
        uid = j.get('user_id')
        started = j.get('started_at'); finished = j.get('finished_at')
        if st == 'fertig' and started and finished and finished > started:
            durations.append(finished - started)
        if st == 'wartet':
            paid = False
            try:
                paid = bool(uid and _has_purchased(uid))
            except Exception:
                pass
            paid_wait += 1 if paid else 0
            free_wait += 0 if paid else 1
        eta = None; prog = j.get('progress') or 0
        if st == 'laeuft' and started and prog > 0.02:
            el = now - started
            eta = max(0, int(el / prog - el))
        updated = None
        try:
            updated = int(os.path.getmtime(os.path.join(job_dir(jid), 'state.json')))
        except OSError:
            pass
        at_risk = bool(st in ('wartet', 'laeuft') and updated
                       and now - updated > JOB_STUCK_SECONDS * 0.7)
        out.append({'jid': jid, 'user_id': uid, 'email': _admin_email(uid),
                    'status': st, 'phase': j.get('phase'), 'progress': prog,
                    'kind': j.get('kind', 'caption'), 'mode': j.get('mode'),
                    'dauer': j.get('dauer'), 'name': j.get('name'),
                    'has_pid': bool(j.get('pid')), 'eta_sec': eta,
                    'started_at': int(started) if started else None,
                    'updated_at': updated, 'at_risk': at_risk,
                    'wm': bool(j.get('wm')), 'alpha': j.get('alpha')})
    # v138a: schlicht NEUESTE ZUERST (Ismets Wunsch). Die alte Status-
    # Gruppierung schob z.B. 'vorbereitet'-Jobs ans Ende der Liste.
    out.sort(key=lambda x: -(x['updated_at'] or 0))
    avg = round(sum(durations) / len(durations)) if durations else None
    return {'jobs': out, 'distribution': dist, 'avg_render_sec': avg,
            'queue': {'caption': QUEUE.qsize(), 'motion': MQUEUE.qsize(),
                      'paid_waiting': paid_wait, 'free_waiting': free_wait}}


@app.post('/api/admin/jobs/{jid}/kill')
def admin_kill_job(jid: str, request: Request):
    _require_admin(request)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    pid = j.get('pid'); killed = False
    if pid:
        try:
            os.kill(int(pid), signal.SIGKILL); killed = True
        except (OSError, ValueError) as e:
            print(f'Admin-Kill {jid}: {e}')
    set_state(jid, status='fehler', progress=0, msg='Stopped by admin.')
    try:
        _maybe_refund(jid)
    except Exception as e:
        print(f'Admin-Kill Refund {jid}: {e}')
    return {'ok': True, 'killed': killed}


@app.post('/api/admin/jobs/reap_stuck')
def admin_reap_stuck(request: Request):
    """Alle wartenden/laufenden Jobs auf einmal beenden + erstatten."""
    _require_admin(request)
    jids = [jid for jid, j in list(JOBS.items()) if j.get('status') in ('wartet', 'laeuft')]
    for jid in jids:
        _reap_stuck_job(jid, f'Admin-Sammel-Stopp: Job {jid} beendet + erstattet.')
    return {'ok': True, 'reaped': len(jids)}


@app.get('/api/admin/jobs/{jid}/log')
def admin_job_log(jid: str, request: Request):
    _require_admin(request)
    p = os.path.join(job_dir(jid), 'log.txt')
    if os.path.exists(p):
        try:
            return {'log': open(p, encoding='utf-8', errors='replace').read()[-40000:]}
        except OSError:
            pass
    j = JOBS.get(jid) or {}
    return {'log': j.get('detail') or j.get('msg') or '(no log available)'}


@app.post('/api/admin/jobs/{jid}/retry')
def admin_job_retry(jid: str, request: Request):
    _require_admin(request)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    if j.get('status') in ('wartet', 'laeuft'):
        raise HTTPException(409, 'Job is already queued/running.')
    set_state(jid, status='wartet', progress=0, phase='Queued (admin retry) …',
              started_at=None, finished_at=None)
    if j.get('kind') == 'motion':
        MQUEUE.put(jid)
    else:
        q_put(jid)
    return {'ok': True}


@app.post('/api/admin/jobs/{jid}/refund')
def admin_job_refund(jid: str, request: Request,
                     minutes: int = Form(0), reason: str = Form('')):
    """Kulanz-Gutschrift fuer einen (evtl. schon gelieferten) Job. Traceable
    ueber eine 'Refund {jid} admin'-Ledger-Zeile (positiv)."""
    _require_admin(request)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    uid = j.get('user_id')
    if not uid:
        raise HTTPException(400, 'Job has no user.')
    sec = int(minutes) * 60 if minutes else _job_cost(j)
    if sec <= 0:
        raise HTTPException(400, 'Nothing to refund.')
    _adjust_balance(uid, sec, f'Refund {jid} admin {(reason or "")[:40]}')
    nu = _find_user_by_id(uid)
    return {'ok': True, 'refunded_min': sec // 60,
            'credits': credits_of(nu['balance_sec']) if nu else None}


@app.post('/api/admin/jobs/{jid}/unlock')
def admin_job_unlock(jid: str, request: Request):
    """Wasserzeichen zwangsweise entfernen (Support-Kulanz). IRREVERSIBEL: der
    saubere Master ersetzt fertig.mp4 (os.replace)."""
    _require_admin(request)
    ok = _unlock_job(jid)
    return {'ok': True, 'unlocked': bool(ok)}


@app.post('/api/admin/jobs/{jid}/delete')
def admin_job_delete(jid: str, request: Request):
    _require_admin(request)
    shutil.rmtree(job_dir(jid), ignore_errors=True)
    JOBS.pop(jid, None)
    return {'ok': True}


@app.get('/api/admin/start')
def admin_start(request: Request):
    """v206 STARTSEITE. Das Panel ist ueber 15 Ansichten gewachsen und war fuer
    jemanden gebaut, der die Begriffe schon kennt (AOV, ARPPU, inflight_cap).
    Ismet ist kein Entwickler - fuer ihn war es "unuebersichtlich und kaum
    benutzerfreundlich", und er wusste nicht einmal, ob die Umsatzzahlen
    stimmen. Zu Recht: sie waren brutto (siehe v206-Erstattungen).

    Diese Ansicht beantwortet die vier Fragen, die er wirklich hat, in
    Klartext und mit EINER Zahl je Frage:
      1. Verdiene ich Geld?
      2. Laeuft alles?
      3. Will jemand etwas von mir?
      4. Waechst es?
    Alles Technische bleibt in den bestehenden Ansichten - es steht nur nicht
    mehr vorn."""
    _require_admin(request)
    return _ttl_cached('adm:start', 20, _admin_start_calc)


def _admin_start_calc():
    now = int(time.time())
    tag = 86400
    con = _db()
    try:
        def geld(seit):
            r = con.execute("SELECT COALESCE(SUM(cents),0) c, COUNT(*) n FROM "
                            "purchases WHERE created_at >= ?", (seit,)).fetchone()
            e = con.execute("SELECT COALESCE(SUM(cents),0) c FROM refunds "
                            "WHERE created_at >= ?", (seit,)).fetchone()
            return {'eur': round((r['c'] - e['c']) / 100.0, 2),
                    'kaeufe': r['n'],
                    'erstattet_eur': round(e['c'] / 100.0, 2)}

        def zahl(q, *p):
            r = con.execute(q, p).fetchone()
            return int(r[0] if r else 0)

        heute, woche, monat = geld(now - tag), geld(now - 7 * tag), geld(now - 30 * tag)
        gesamt = geld(0)
        # Wachstum: diese 30 Tage gegen die 30 davor
        _vor = con.execute(
            "SELECT COALESCE(SUM(cents),0) c FROM purchases "
            "WHERE created_at >= ? AND created_at < ?",
            (now - 60 * tag, now - 30 * tag)).fetchone()['c']
        _trend = None
        if _vor > 0:
            _trend = round((monat['eur'] * 100 - _vor) / _vor * 100)
        kunden_gesamt = zahl("SELECT COUNT(*) FROM users")
        kunden_neu = zahl("SELECT COUNT(*) FROM users WHERE created_at >= ?",
                          now - 7 * tag)
        zahler = zahl("SELECT COUNT(DISTINCT user_id) FROM purchases")
        renders_woche = zahl("SELECT COUNT(*) FROM ledger WHERE grund LIKE "
                             "'Render %' AND created_at >= ?", now - 7 * tag)
        tickets = zahl("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
        feedback = zahl("SELECT COUNT(*) FROM feedback WHERE gelesen = 0")
        stoerungen = zahl("SELECT COUNT(*) FROM alerts WHERE gelesen = 0")
        note = con.execute("SELECT AVG(note) a, COUNT(*) c FROM feedback").fetchone()
    finally:
        con.close()
    hb = _HEARTBEAT
    disk = _disk_info() or {}
    # "Laeuft alles?" - eine Ampel statt sechs Zahlen. Rot nur bei etwas, das
    # den Betrieb WIRKLICH bedroht; alles andere ist gelb.
    probleme = []
    if betrieb_stufe() != 'normal':
        probleme.append(('rot', f'Betrieb steht auf "{betrieb_stufe()}"'))
    if (disk.get('free_gb') or 99) < 2:
        probleme.append(('rot', f"Nur noch {disk.get('free_gb')} GB Platz frei"))
    elif (disk.get('free_gb') or 99) < 10:
        probleme.append(('gelb', f"Noch {disk.get('free_gb')} GB Platz frei"))
    for name, key in (('Aufraeumer', 'cleanup'), ('Wachhund', 'watchdog')):
        ts = hb.get(key)
        if not ts or now - ts > 3 * 3600:
            probleme.append(('rot', f'{name} meldet sich nicht'))
    if QUEUE.qsize() >= QUEUE_WARN:
        probleme.append(('gelb', f'{QUEUE.qsize()} Videos warten in der Schlange'))
    if stoerungen:
        probleme.append(('gelb', f'{stoerungen} ungelesene Stoerungsmeldungen'))
    ampel = 'rot' if any(p[0] == 'rot' for p in probleme) else (
        'gelb' if probleme else 'gruen')
    return {
        'geld': {'heute': heute, 'woche': woche, 'monat': monat,
                 'gesamt': gesamt, 'trend_prozent': _trend},
        'betrieb': {'ampel': ampel,
                    'probleme': [{'stufe': a, 'text': b} for a, b in probleme],
                    'laeuft_gerade': sum(1 for j in JOBS.values()
                                         if j.get('status') == 'laeuft'),
                    'wartet': QUEUE.qsize()},
        'post': {'tickets': tickets, 'feedback': feedback,
                 'note': round(note['a'], 1) if note['a'] else None,
                 'bewertungen': note['c']},
        'wachstum': {'kunden': kunden_gesamt, 'neu_7t': kunden_neu,
                     'zahler': zahler, 'renders_7t': renders_woche},
    }


@app.get('/api/admin/trichter')
def admin_trichter(request: Request, tage: int = 30):
    """v208: Wo verliere ich die Leute? Sechs Stufen und die Herkunft.

    Die Zuordnung ist der knifflige Teil: 'kauf' und 'fertig' entstehen ohne
    Browser (Stripe-Webhook bzw. Render-Worker), haben also keine Herkunft.
    Sie wird ueber die Konto-Nummer nachgeschlagen - das Konto haengt an der
    Registrierung, und DIE kam aus einem Browser mit Verweis.
    """
    _require_admin(request)
    return _ttl_cached(f'adm:trichter:{int(tage)}', 60,
                       lambda: _trichter_calc(tage))


def _trichter_calc(tage: int = 30):
    tage = max(1, min(365, int(tage)))
    seit = int(time.time()) - tage * 86400
    con = _db()
    try:
        # Je Stufe zaehlen wir MENSCHEN, nicht Ereignisse: wer dreimal die
        # Landing oeffnet, ist ein Besucher. Vor der Anmeldung ueber den
        # Tages-Fingerabdruck, danach ueber die Konto-Nummer.
        stufen = {}
        for st in _TRICHTER_STUFEN:
            spalte = 'user_id' if st in ('konto', 'upload', 'fertig', 'kauf') \
                else 'besucher'
            r = con.execute(
                f"SELECT COUNT(DISTINCT {spalte}) n FROM trichter "
                f"WHERE stufe = ? AND ts >= ? AND {spalte} IS NOT NULL "
                f"AND {spalte} != ''", (st, seit)).fetchone()
            stufen[st] = int(r['n'] or 0)

        # Herkunft: fuer jedes Konto die Quelle seiner ERSTEN Spur. Damit
        # laesst sich ein Kauf der Quelle zuordnen, aus der der Mensch kam.
        quelle_von_konto = {}
        for r in con.execute(
                "SELECT user_id, quelle FROM trichter WHERE user_id IS NOT NULL "
                "AND quelle != '' ORDER BY ts").fetchall():
            quelle_von_konto.setdefault(r['user_id'], r['quelle'])

        quellen = {}
        for r in con.execute(
                "SELECT quelle, COUNT(DISTINCT besucher) n FROM trichter "
                "WHERE stufe = 'besuch' AND ts >= ? AND quelle != '' "
                "GROUP BY quelle ORDER BY n DESC LIMIT 20", (seit,)).fetchall():
            quellen[r['quelle']] = {'besucher': int(r['n']), 'konten': 0,
                                    'kaeufer': 0}
        for st, feld in (('konto', 'konten'), ('kauf', 'kaeufer')):
            for r in con.execute(
                    "SELECT DISTINCT user_id FROM trichter WHERE stufe = ? "
                    "AND ts >= ? AND user_id IS NOT NULL", (st, seit)).fetchall():
                q = quelle_von_konto.get(r['user_id'])
                if q:
                    quellen.setdefault(q, {'besucher': 0, 'konten': 0,
                                           'kaeufer': 0})[feld] += 1
        erste = con.execute("SELECT MIN(ts) t FROM trichter").fetchone()['t']
    finally:
        con.close()

    # Jede Stufe mit Klartext: was ist das, und was heisst der Wert.
    text = {
        'besuch': ('Besucher', 'Haben die Startseite gesehen.'),
        'app': ('App geoeffnet', 'Haben angefangen, statt nur zu lesen.'),
        'konto': ('Konto angelegt', 'Haben sich registriert.'),
        'upload': ('Video hochgeladen', 'Haben es wirklich probiert.'),
        'fertig': ('Ergebnis gesehen', 'Haben ein fertiges Video bekommen.'),
        'kauf': ('Gekauft', 'Zahlende Kunden.'),
    }
    reihe = []
    vorher = None
    for st in _TRICHTER_STUFEN:
        n = stufen[st]
        reihe.append({
            'stufe': st, 'titel': text[st][0], 'erklaerung': text[st][1],
            'anzahl': n,
            # Anteil an der VORHERIGEN Stufe - das ist die Zahl, die sagt, wo
            # es klemmt. Der Anteil an ganz oben verschleiert das.
            'von_vorher_prozent': (round(n / vorher * 100) if vorher else None),
            'von_oben_prozent': (round(n / stufen['besuch'] * 100)
                                 if stufen['besuch'] else None),
        })
        vorher = n or None
    return {'tage': tage, 'stufen': reihe,
            'quellen': [{'quelle': k, **v} for k, v in
                        sorted(quellen.items(),
                               key=lambda x: -x[1]['besucher'])][:20],
            'seit': erste,
            'hinweis': ('Anonym gezaehlt: kein Cookie, keine IP gespeichert. '
                        'Der Zaehl-Fingerabdruck wechselt taeglich.')}


@app.get('/api/admin/revenue')
def admin_revenue(request: Request, days: int = 90):
    """Alles Geld aus der purchases-Tabelle (v128+). v142: 20s TTL-Cache - das
    Panel pollt, die Aggregate scannen mehrere Tabellen. Jede schreibende
    Anfrage verwirft den Cache (Middleware), es kann also keine Zahl von VOR
    einer Admin-Aktion stehen bleiben."""
    _require_admin(request)
    return _ttl_cached(f'adm:revenue:{int(days)}', 20,
                       lambda: _admin_revenue_calc(days))


def _admin_revenue_calc(days: int = 90):
    """Fenster, Zeitreihe, pro Paket, AOV/ARPPU, Wiederkaeufer, Top-Spender,
    Pre-v128-Schaetzung, Katalog."""
    now = int(time.time()); day = 86400; days = max(7, min(365, days))
    con = _db()
    windows = {'today': _revrow(con, now - day), 'week': _revrow(con, now - 7 * day),
               'month': _revrow(con, now - 30 * day), 'total': _revrow(con, 0)}
    packs = con.execute("SELECT pack, COUNT(*) c, COALESCE(SUM(cents),0) cents "
                        "FROM purchases GROUP BY pack ORDER BY cents DESC").fetchall()
    per_pack = [{'pack': r['pack'], 'count': r['c'], 'eur': round(r['cents'] / 100.0, 2)}
                for r in packs]
    tot = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents, "
                      "COUNT(DISTINCT user_id) u FROM purchases").fetchone()
    aov = round(tot['cents'] / 100.0 / tot['c'], 2) if tot['c'] else 0.0
    arppu = round(tot['cents'] / 100.0 / tot['u'], 2) if tot['u'] else 0.0
    rb = con.execute("SELECT user_id, COUNT(*) c FROM purchases GROUP BY user_id").fetchall()
    repeat = sum(1 for r in rb if r['c'] > 1); once = sum(1 for r in rb if r['c'] == 1)
    series = con.execute("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                         "COALESCE(SUM(cents),0) cents FROM purchases WHERE created_at >= ? "
                         "GROUP BY d ORDER BY d", (now - days * day,)).fetchall()
    ser = [{'d': r['d'], 'eur': round(r['cents'] / 100.0, 2)} for r in series]
    top = con.execute("SELECT p.user_id uid, COALESCE(SUM(p.cents),0) cents, COUNT(*) c, "
                      "u.email email FROM purchases p LEFT JOIN users u ON u.id = p.user_id "
                      "GROUP BY p.user_id ORDER BY cents DESC LIMIT 15").fetchall()
    tops = [{'uid': r['uid'], 'email': r['email'] or '(deleted)',
             'eur': round(r['cents'] / 100.0, 2), 'orders': r['c']} for r in top]
    # Pre-v128: Kauf-Ledger-Zeilen ohne purchases-Match -> aus Sekunden schaetzen.
    known = {('Kauf ' + r['session_id']) for r in
             con.execute("SELECT session_id FROM purchases").fetchall()}
    sek2cent = {v['sekunden']: v['preis_cent'] for v in PACKS.values()}
    kauf = con.execute("SELECT grund, delta_sec FROM ledger WHERE grund LIKE 'Kauf %' "
                       "AND delta_sec > 0").fetchall()
    pre_n = 0; pre_cent = 0
    for r in kauf:
        if r['grund'] in known:
            continue
        pre_n += 1
        pre_cent += sek2cent.get(r['delta_sec'], 0)
    con.close()
    catalog = [{'id': k, 'eur': v['preis_cent'] / 100.0, 'credits': v['sekunden'] // 60,
                'per_credit': round(v['preis_cent'] / 100.0 / (v['sekunden'] // 60), 3)}
               for k, v in PACKS.items()]
    return {'windows': windows, 'per_pack': per_pack, 'aov': aov, 'arppu': arppu,
            'buyers': {'once': once, 'repeat': repeat}, 'series': ser,
            'top_spenders': tops, 'catalog': catalog, 'stripe': _stripe_health(),
            'pre_v128_estimate': {'count': pre_n, 'eur_est': round(pre_cent / 100.0, 2)}}


@app.get('/api/admin/timeseries')
def admin_timeseries(request: Request, days: int = 30):
    """v136: Tages-Zeitreihen fuer die Admin-Grafen. Alle Reihen sind auf
    LUECKENLOSE Tage aufgefuellt (0 fuer leere Tage), damit die Balken-Achse
    ehrlich ist - eine Reihe nur aus Verkaufstagen wuerde Flauten verstecken.
    v142: 20s TTL-Cache, Invalidierung wie bei /revenue."""
    _require_admin(request)
    return _ttl_cached(f'adm:series:{int(days)}', 20,
                       lambda: _admin_timeseries_calc(days))


def _admin_timeseries_calc(days: int = 30):
    days = max(7, min(180, days))
    now = int(time.time()); day = 86400
    start_day = now - (days - 1) * day
    # Tagesgrenze auf UTC-Mitternacht des Starttags ziehen (timegm = TZ-fest,
    # strftime('unixepoch') in SQLite gruppiert ebenfalls nach UTC)
    import calendar as _cal
    start = int(_cal.timegm(time.strptime(
        time.strftime('%Y-%m-%d', time.gmtime(start_day)), '%Y-%m-%d')))
    labels = [time.strftime('%Y-%m-%d', time.gmtime(start_day + i * day))
              for i in range(days)]
    con = _db()

    def daily(sql, args):
        return {r['d']: r for r in con.execute(sql, args).fetchall()}
    rev = daily("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                "COALESCE(SUM(cents),0) cents, COUNT(*) c FROM purchases "
                "WHERE created_at >= ? GROUP BY d", (start,))
    sig = daily("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                "COUNT(*) c FROM users WHERE created_at >= ? GROUP BY d", (start,))
    ren = daily("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                "COUNT(*) c, COALESCE(SUM(-delta_sec),0) s FROM ledger "
                "WHERE created_at >= ? AND grund LIKE 'Render %' AND delta_sec < 0 "
                "GROUP BY d", (start,))
    bought = daily("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                   "COALESCE(SUM(delta_sec),0) s FROM ledger WHERE created_at >= ? "
                   "AND grund LIKE 'Kauf %' AND delta_sec > 0 GROUP BY d", (start,))
    spent = daily("SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
                  "COALESCE(SUM(-delta_sec),0) s FROM ledger WHERE created_at >= ? "
                  "AND delta_sec < 0 AND (grund LIKE 'Render %' OR grund LIKE "
                  "'Alpha %' OR grund LIKE 'Style learn %') GROUP BY d", (start,))
    con.close()

    def series(src, field, scale=1.0):
        out = []
        for lb in labels:
            r = src.get(lb)
            v = (r[field] if r else 0) / scale
            out.append(round(v, 2) if scale != 1.0 else int(v))
        return out
    return {
        'days': days, 'labels': labels,
        'revenue_eur': series(rev, 'cents', 100.0),
        'purchases': series(rev, 'c'),
        'signups': series(sig, 'c'),
        'renders': series(ren, 'c'),
        'render_min': series(ren, 's', 60.0),
        'credits_bought_min': series(bought, 's', 60.0),
        'credits_spent_min': series(spent, 's', 60.0),
    }


@app.get('/api/admin/credits')
def admin_credits(request: Request):
    """Credit-Oekonomie aus der Ledger-Grund-Taxonomie: gratis vs bezahlt vs
    admin, Verbrauch (render+alpha+style), Verfall/Breakage, Liability + Aging."""
    _require_admin(request)
    con = _db()
    paid = _sum_grund(con, 'Kauf %', 1)
    welcome = _sum_grund(con, 'Welcome credit', 1)
    monthly = _sum_grund(con, 'Monthly free credit %', 1)
    referral = _sum_grund(con, 'Referral %', 1)
    reload_b = _sum_grund(con, 'Reload bonus %', 1)
    admin_grant = _sum_grund(con, 'Admin adjust %', 1)
    admin_claw = -_sum_grund(con, 'Admin adjust %', -1)
    refunded = _sum_grund(con, 'Refund %', 1)
    render_used = -_sum_grund(con, 'Render %', -1)
    alpha_used = -_sum_grund(con, 'Alpha %', -1)
    style_used = -_sum_grund(con, 'Style learn %', -1)
    expired = -_sum_grund(con, 'Expired credits %', -1)
    liability = con.execute("SELECT COALESCE(SUM(balance_sec),0) s FROM users").fetchone()['s']
    uids = [r['id'] for r in con.execute("SELECT id FROM users").fetchall()]
    con.close()
    now = time.time(); buckets = {'d0_30': 0, 'd30_90': 0, 'd90_180': 0}; soon = 0
    for uid in uids:
        for g in _fifo_remainders(uid):
            remain = CREDIT_VALIDITY_DAYS - (now - g['created_at']) / 86400
            if remain <= 30:
                buckets['d0_30'] += g['left']; soon += g['left']
            elif remain <= 90:
                buckets['d30_90'] += g['left']
            else:
                buckets['d90_180'] += g['left']

    def m(x):
        return int(x) // 60
    return {
        'granted': {'paid': m(paid), 'welcome': m(welcome), 'monthly': m(monthly),
                    'referral': m(referral), 'reload_bonus': m(reload_b),
                    'admin': m(admin_grant), 'refund': m(refunded),
                    'free_total': m(welcome + monthly + referral + reload_b)},
        'consumed': {'render': m(render_used), 'alpha': m(alpha_used),
                     'style_learn': m(style_used), 'admin_clawback': m(admin_claw),
                     'expired_breakage': m(expired)},
        'liability_min': m(liability),
        'aging_min': {k: m(v) for k, v in buckets.items()},
        'expiring_30d_min': m(soon),
    }


@app.get('/api/admin/abuse')
def admin_abuse(request: Request):
    """Missbrauchs-Signale: Farming (verwaiste Anspruch-Hashes), Wegwerf-Mails,
    unbestaetigte Konten, Referral-Graph, Rate-Limit-Lockouts, offene Resets,
    Demo-IP-Missbrauch. Vieles In-Memory (setzt sich bei Neustart zurueck)."""
    _require_admin(request)
    now = time.time()
    con = _db()
    users = con.execute("SELECT id, email, verified, created_at, disabled FROM users").fetchall()
    cur_hashes = {_email_hash(u['email']) for u in users}
    cc = con.execute("SELECT email_hash FROM credit_claims").fetchall()
    rcl = con.execute("SELECT email_hash FROM referral_claims").fetchall()
    pending_resets = con.execute("SELECT COUNT(*) c FROM resets WHERE used = 0 "
                                 "AND expires_at > ?", (int(now),)).fetchone()['c']
    refs = con.execute("SELECT referred_by rb, COUNT(*) c FROM users "
                       "WHERE referred_by IS NOT NULL GROUP BY referred_by "
                       "ORDER BY c DESC LIMIT 15").fetchall()
    con.close()
    orphan_credit = sum(1 for r in cc if r['email_hash'] not in cur_hashes)
    orphan_ref = sum(1 for r in rcl if r['email_hash'] not in cur_hashes)
    disposable = [{'id': u['id'], 'email': u['email']} for u in users
                  if _is_disposable_email(u['email'])]
    unverified = [{'id': u['id'], 'email': u['email'], 'created_at': u['created_at']}
                  for u in users if not u['verified']][:100]
    top_ref = [{'uid': r['rb'], 'email': _admin_email(r['rb']), 'invited': r['c']}
               for r in refs]
    locks = []
    for key, ts in list(_REG_ATTEMPTS.items()):
        recent = [t for t in ts if now - t < 900]
        if len(recent) >= 15:
            locks.append({'key': key, 'hits': len(recent)})
    demo = []
    for ip, v in list(_DEMO_IPS.items()):
        hits = len([t for t in v if now - t < 86400])
        if hits >= 2:
            demo.append({'ip': ip, 'hits': hits})
    return {'orphan_claims': {'credit': orphan_credit, 'referral': orphan_ref},
            'disposable_accounts': disposable, 'unverified_accounts': unverified,
            'pending_resets': pending_resets, 'top_referrers': top_ref,
            'rate_limit_lockouts': locks, 'demo_ip_abuse': demo,
            'note': 'Lockouts/demo/alerts are in-memory and reset on restart.'}


@app.get('/api/admin/system')
def admin_system(request: Request):
    """Alle Betriebs-Konstanten + Health an einem Ort. Nur bool-Present fuer
    Secrets, nie Werte. Config ist env/boot-time (nur Anzeige, kein Live-Toggle)."""
    _require_admin(request)
    hb = dict(_HEARTBEAT)
    return {
        'build': DVE_BUILD,
        'keys': {'openai': _openai_health(),
                 'stripe': _stripe_health(), 'mail': _mail_health(),
                 'admin_key': bool(os.environ.get('DVE_ADMIN', '').strip()),
                 'ref_salt': bool(os.environ.get('DVE_REF_SALT', '').strip())
                 or os.path.exists(os.path.join(DATA, 'ref_salt'))},
        'disk': _disk_info(), 'db_mb': _db_size_mb(), 'last_backup': _last_backup_ts(),
        'mem': _mem_info(),

        'heartbeats': {'watchdog': hb.get('watchdog'), 'cleanup': hb.get('cleanup')},
        'alerts_active': len(_ADMIN_NOTIFIED),
        'alerts_offen': _alerts_offen(),
        # v205-sec: Was laeuft hier eigentlich? Zwei Fragen, die man sonst nur
        # im Terminal beantworten kann - und Ismet geht nicht ins Terminal.
        # (1) Laeuft der Dienst wirklich ohne Generalschluessel (nicht root)?
        #     Die Meldung von entrypoint.sh steht in `docker logs`, NICHT in
        #     server.log - die Datei faengt erst an, wenn Python laeuft.
        # (2) Welche Fremdbauteile in WELCHER Version stecken drin? Ohne diese
        #     Liste laesst sich requirements.txt nicht ehrlich festnageln.
        'laufzeit': _laufzeit_info(),
        'pakete': _paket_versionen(),
        'config': {
            'workers': WORKERS,
            'queue_warn': QUEUE_WARN,
            'inflight_cap': CAPTION_INFLIGHT_CAP,
            'motion_concurrency': int(os.environ.get('DVE_MOTION_CONCURRENCY', '2')),
            'max_mb': int(os.environ.get('DVE_MAX_MB', '300')),
            'max_seconds': int(os.environ.get('DVE_MAX_SECONDS', '180')),
            'retention_days': RETENTION_DAYS,
            'credit_valid_days': CREDIT_VALIDITY_DAYS,
            'job_timeout_min': round(JOB_STUCK_SECONDS / 60),
            'trial_seconds': TRIAL_SECONDS,
            'referral_seconds': REFERRAL_SECONDS, 'referral_cap': REFERRAL_CAP,
            'public_url': os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu'),
            'owner_email': OWNER_EMAIL,
            'motion_available': bool(MOTION_BRIEF_OK),
            'google_login': GOOGLE_OK,                 # v132
            'alerts_level': ALERT_LEVEL,               # v131
        },
    }


@app.get('/api/admin/mailthrottle')
def admin_mailthrottle(request: Request):
    """v203-sec: Diese Funktion hing bis v202 auf '/api/admin/alerts' - demselben
    Pfad wie admin_alerts weiter oben. Starlette bedient die ZUERST registrierte
    Route, also war diese hier toter Code und die ungeschuetzte Variante die
    wirksame. Beim Lesen sah es so aus, als sei der Pfad abgesichert (hier steht
    ja _require_admin) - eine Doppelregistrierung versteckt den Fehler doppelt.
    Sie zeigt etwas anderes als admin_alerts (den Mail-Deckel im Prozess, nicht
    die Tabelle) und bekommt deshalb einen eigenen, ehrlichen Pfad."""
    _require_admin(request)
    now = time.time()
    items = [{'key': k, 'ago_min': round((now - ts) / 60)}
             for k, ts in sorted(_ADMIN_NOTIFIED.items(), key=lambda x: -x[1])][:40]
    return {'alerts': items,
            'note': 'In-memory notification throttle state; resets on restart.'}


@app.get('/api/admin/feedback')
def admin_feedback(request: Request, filt: str = 'all', limit: int = 300):
    """v196: Bewertungen sichten. filt = all/neu/schlecht."""
    _require_admin(request)
    limit = max(1, min(1000, limit))
    where = ''
    if filt == 'neu':
        where = 'WHERE f.gelesen = 0'
    elif filt == 'schlecht':
        where = 'WHERE f.note <= 2'
    con = _db()
    try:
        rows = con.execute(
            f"SELECT f.id, f.user_id, f.jid, f.look, f.note, f.text, "
            f"f.created_at, f.gelesen, u.email, u.name "
            f"FROM feedback f LEFT JOIN users u ON u.id = f.user_id "
            f"{where} ORDER BY f.created_at DESC LIMIT ?", (limit,)).fetchall()
        # Verteilung und Schnitt - eine Liste allein sagt nichts ueber die Lage.
        vert = {n: 0 for n in range(1, 6)}
        for r in con.execute("SELECT note, COUNT(*) c FROM feedback GROUP BY note"):
            vert[int(r['note'])] = r['c']
        ges = sum(vert.values())
        schnitt = (sum(n * c for n, c in vert.items()) / ges) if ges else 0
        # Schnitt je Look: DAS ist die Zahl, die eine Produktentscheidung traegt.
        looks = [dict(r) for r in con.execute(
            "SELECT look, COUNT(*) c, AVG(note) avg FROM feedback "
            "WHERE look <> '' GROUP BY look ORDER BY c DESC").fetchall()]
        offen = con.execute("SELECT COUNT(*) c FROM feedback WHERE gelesen = 0"
                            ).fetchone()['c']
        return {'items': [dict(r) for r in rows], 'verteilung': vert,
                'gesamt': ges, 'schnitt': round(schnitt, 2),
                'looks': looks, 'offen': offen}
    finally:
        con.close()


@app.post('/api/admin/feedback/{fid}/read')
def admin_feedback_read(fid: int, request: Request):
    _require_admin(request)
    con = _db()
    try:
        con.execute("UPDATE feedback SET gelesen = 1 WHERE id = ?", (fid,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@app.get('/api/admin/announcements')
def admin_ann_list(request: Request):
    _require_admin(request)
    con = _db()
    try:
        rows = con.execute(
            "SELECT id, titel, text, stufe, aktiv, created_at, bis "
            "FROM announcements ORDER BY created_at DESC LIMIT 200").fetchall()
        return {'items': [dict(r) for r in rows]}
    finally:
        con.close()


_ANN_STUFEN = ('info', 'warn', 'wartung')


@app.post('/api/admin/announcements')
def admin_ann_save(request: Request, titel: str = Form(...), text: str = Form(...),
                   stufe: str = Form('info'), tage: float = Form(0),
                   aid: int = Form(0)):
    """Anlegen oder aendern. tage > 0 setzt ein Ablaufdatum - eine
    Wartungsmeldung, die jemand vergisst abzuschalten, ist schlimmer als
    keine."""
    _require_admin(request)
    titel = (titel or '').strip()[:120]
    text = (text or '').strip()[:2000]
    if not titel or not text:
        raise HTTPException(400, 'Title and text are required.')
    stufe = stufe if stufe in _ANN_STUFEN else 'info'
    try:
        tage = max(0.0, min(365.0, float(tage or 0)))
    except (TypeError, ValueError):
        tage = 0.0
    bis = int(time.time() + tage * 86400) if tage else None
    con = _db()
    try:
        if aid:
            con.execute("UPDATE announcements SET titel=?, text=?, stufe=?, bis=? "
                        "WHERE id=?", (titel, text, stufe, bis, int(aid)))
        else:
            con.execute("INSERT INTO announcements (titel, text, stufe, aktiv, "
                        "created_at, bis) VALUES (?, ?, ?, 1, ?, ?)",
                        (titel, text, stufe, int(time.time()), bis))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@app.post('/api/admin/announcements/{aid}/toggle')
def admin_ann_toggle(aid: int, request: Request):
    _require_admin(request)
    con = _db()
    try:
        con.execute("UPDATE announcements SET aktiv = 1 - aktiv WHERE id = ?", (aid,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@app.post('/api/admin/announcements/{aid}/delete')
def admin_ann_del(aid: int, request: Request):
    _require_admin(request)
    con = _db()
    try:
        con.execute("DELETE FROM announcements WHERE id = ?", (aid,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@app.get('/api/admin/tickets')
def admin_tickets(request: Request, status: str = 'all', limit: int = 200):
    """v133c: Support-Tickets sichten. status = all/open/closed."""
    _require_admin(request)
    limit = max(1, min(500, limit))
    con = _db()
    where = ''
    params = []
    if status in ('open', 'closed'):
        where = 'WHERE status = ?'
        params.append(status)
    rows = con.execute(
        f"SELECT id, user_id, email, subject, body, status, created_at, updated_at "
        f"FROM tickets {where} ORDER BY (status='open') DESC, created_at DESC "
        f"LIMIT ?", (*params, limit)).fetchall()
    open_count = con.execute("SELECT COUNT(*) c FROM tickets WHERE status='open'").fetchone()['c']
    aus = [{'id': r['id'], 'uid': r['user_id'], 'email': r['email'],
            'subject': r['subject'], 'body': r['body'],
            'status': r['status'], 'created_at': r['created_at'],
            'updated_at': r['updated_at'],
            # v198: der ganze Verlauf, nicht nur die erste Nachricht.
            'messages': _ticket_verlauf(con, r['id'])} for r in rows]
    con.close()
    return {'tickets': aus, 'open_count': open_count}


@app.post('/api/admin/tickets/{tid}/reply')
def admin_ticket_reply(tid: int, request: Request, text: str = Form(...)):
    """v198: Antworten AUS DEM PANEL. Bis v197 lief die Antwort ueber Ismets
    Postfach (Reply-To am Benachrichtigungs-Mail). Das funktioniert, aber
    dann steht die halbe Unterhaltung nirgends: das Panel zeigte die Frage
    und nie die Antwort, und eine Rueckfrage des Kunden kam als NEUES Ticket
    ohne Bezug. Die Antwort steht jetzt im Verlauf UND geht als Mail raus -
    der Kunde soll nicht in die App schauen muessen, um sie zu sehen."""
    _require_admin(request)
    text = (text or '').strip()[:5000]
    if len(text) < 2:
        raise HTTPException(400, 'Empty reply.')
    now = int(time.time())
    con = _db()
    t = con.execute("SELECT id, email, subject, user_id FROM tickets WHERE id = ?",
                    (tid,)).fetchone()
    if not t:
        con.close()
        raise HTTPException(404, 'Unknown ticket.')
    con.execute("INSERT INTO ticket_messages (ticket_id, von, text, gelesen, "
                "created_at) VALUES (?, 'admin', ?, 0, ?)", (tid, text, now))
    con.execute("UPDATE tickets SET status = 'answered', updated_at = ? "
                "WHERE id = ?", (now, tid))
    con.commit(); con.close()
    gemailt = True
    try:
        base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
        _send_mail(t['email'], f'Re: {t["subject"]} (#{tid})',
                   f'{text}\n\n'
                   f'--\nYou can reply here: {base}/app#account\n'
                   f'DouchkoVE Support',
                   reply_to=SUPPORT_EMAIL or ADMIN_MAIL)
    except Exception as e:
        gemailt = False
        print(f'Support-Antwort-Mail an Kunde fehlgeschlagen: {e}')
    return {'ok': True, 'gemailt': gemailt}


@app.post('/api/admin/factory_reset')
def admin_factory_reset(request: Request, confirm: str = Form('')):
    """v137: Kompletter Neustart auf null fuer die Zeit VOR dem Launch -
    loescht ALLE Kunden-/Testdaten (Users, Credits, Kaeufe, Tickets, Consents,
    Jobs, Caches). Nur mit confirm='RESET'. Zahlungsbelege bleiben vollstaendig
    im Stripe-Dashboard erhalten (dort liegt die steuerliche Wahrheit)."""
    _require_admin(request)
    if (confirm or '').strip() != 'RESET':
        raise HTTPException(400, "Type RESET to confirm the full wipe.")
    con = _db()
    tables = ['sessions', 'ledger', 'ledger_archive', 'purchases',
              'ticket_messages', 'tickets',            # v198: erst die Kinder
              'consents', 'resets', 'verify_tokens', 'mail_log',
              'feedback', 'announcements',                       # v196
              'credit_claims', 'referral_claims', 'users']
    counts = {}
    for t in tables:
        try:
            counts[t] = con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()['c']
            con.execute(f"DELETE FROM {t}")             # feste Liste, kein User-Input
        except sqlite3.OperationalError:
            counts[t] = None
    con.commit()
    con.close()
    # Jobs (Speicher + Platte) und Transkript-Cache leeren
    for jid in list(JOBS.keys()):
        shutil.rmtree(job_dir(jid), ignore_errors=True)
        JOBS.pop(jid, None)
    try:
        for fn in os.listdir(JOBS_DIR):
            shutil.rmtree(os.path.join(JOBS_DIR, fn), ignore_errors=True)
    except OSError:
        pass
    try:
        for fn in os.listdir(_TCACHE):
            try:
                os.remove(os.path.join(_TCACHE, fn))
            except OSError:
                pass
    except OSError:
        pass
    _ADMIN_NOTIFIED.clear()
    print(f'FACTORY RESET durch Admin: {counts}')
    return {'ok': True, 'wiped': counts}


@app.post('/api/admin/tickets/{tid}/status')
def admin_ticket_status(tid: int, request: Request, status: str = Form(...)):
    """v133c: Ticket auf open/closed setzen."""
    _require_admin(request)
    # v198: 'answered' kommt aus der Panel-Antwort dazu. Wer den Wert hier
    # vergisst, kann ein beantwortetes Ticket nicht mehr von Hand umsetzen.
    if status not in ('open', 'closed', 'answered'):
        raise HTTPException(400, 'status must be open, answered or closed')
    con = _db()
    cur = con.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                      (status, int(time.time()), tid))
    con.commit(); con.close()
    if cur.rowcount != 1:
        raise HTTPException(404, 'Ticket not found')
    return {'ok': True, 'id': tid, 'status': status}


@app.get('/api/admin/compliance/consents')
def admin_consents(request: Request, limit: int = 200):
    _require_admin(request)
    limit = max(1, min(1000, limit))
    con = _db()
    rows = con.execute("SELECT c.id, c.user_id, c.kind, c.created_at, u.email "
                       "FROM consents c LEFT JOIN users u ON u.id = c.user_id "
                       "ORDER BY c.created_at DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return {'consents': [{'id': r['id'], 'uid': r['user_id'],
                          'email': r['email'] or '(deleted)', 'kind': r['kind'],
                          'created_at': r['created_at']} for r in rows]}


@app.get('/api/admin/compliance/archive')
def admin_archive(request: Request):
    _require_admin(request)
    con = _db()
    rows = con.execute("SELECT user_email, delta_sec, grund, created_at, archived_at "
                       "FROM ledger_archive ORDER BY archived_at DESC LIMIT 500").fetchall()
    con.close()
    return {'archive': [dict(r) for r in rows]}


# ================================================================
# v142 RECHT & STEUERN. Ismets Frage war: "wo kann ich die gesetzlich
# vorgeschriebenen Daten einsehen". Bisher lagen sie verstreut - Consents und
# Archiv im Compliance-Tab, Umsatz im Revenue-Tab, Aufbewahrungsfristen nur
# als Env-Variable, die §19-Grenze nirgends. Dieser Endpunkt sammelt ALLES
# an einer Stelle und rechnet die Werte aus den ECHTEN Buchungen.
#
# WICHTIG / ehrlich: das ist eine Übersicht aus den eigenen Daten, keine
# Steuerberatung und kein Ersatz fuer die Buchhaltung. Die Zahlen kommen aus
# purchases (tatsaechlich gezahlte Betraege laut Stripe), nicht aus Stripe
# selbst - eine Abweichung zu Stripe waere ein Alarmzeichen und muss dort
# geprueft werden.
# ================================================================
# §19 UStG (Fassung ab 2025): Kleinunternehmer bleibt, wer im VORJAHR nicht
# ueber 25.000 EUR Gesamtumsatz lag UND im laufenden Jahr 100.000 EUR nicht
# ueberschreitet. Wird die 100.000 im Laufe des Jahres gerissen, endet die
# Regelung SOFORT ab diesem Umsatz - ab dann muss USt ausgewiesen werden.
# Darum warnt das Panel schon ab 80 % der jeweiligen Grenze.
KU_VORJAHR_CENT = 25_000_00
KU_LAUFEND_CENT = 100_000_00


def _tax_year_bounds(year):
    """Jahresgrenzen in UTC-Sekunden (wie alle created_at in der DB)."""
    import calendar as _cal
    a = int(_cal.timegm(time.strptime(f'{year}-01-01', '%Y-%m-%d')))
    b = int(_cal.timegm(time.strptime(f'{year + 1}-01-01', '%Y-%m-%d')))
    return a, b


@app.get('/api/admin/compliance/tax')
def admin_tax(request: Request):
    """Steuer- und Rechts-Uebersicht: Identitaet, §19-Schwellen, Umsatz je
    Jahr und Monat, Rechnungen, Aufbewahrung, Verarbeitungsverzeichnis."""
    _require_admin(request)
    return _ttl_cached('adm:tax', 30, _admin_tax_calc)


def _admin_tax_calc():
    con = _db()
    jahr = int(time.strftime('%Y', time.gmtime()))
    # --- Umsatz je Kalenderjahr (brutto = tatsaechlich gezahlt)
    jahre = []
    for y in range(jahr - 4, jahr + 1):
        a, b = _tax_year_bounds(y)
        # v206: Die §19-Schwellen (25.000 / 100.000 EUR) gehoeren auf das, was
        # WIRKLICH eingenommen wurde. Eine erstattete Zahlung ist kein Umsatz -
        # bis v205 lief die Ampel auf der Brutto-Summe und haette zu frueh
        # ausgeschlagen.
        r = con.execute("SELECT COUNT(*) c, COALESCE(SUM(cents),0) cents "
                        "FROM purchases WHERE created_at >= ? AND created_at < ?",
                        (a, b)).fetchone()
        if r['c'] or y >= jahr - 1:
            _rf = con.execute("SELECT COALESCE(SUM(cents),0) c FROM refunds "
                              "WHERE created_at >= ? AND created_at < ?",
                              (a, b)).fetchone()['c']
            jahre.append({'jahr': y, 'anzahl': r['c'],
                          'brutto_cent': r['cents'] - int(_rf or 0),
                          'eingenommen_cent': r['cents'],
                          'erstattet_cent': int(_rf or 0)})
    _cur = next((j for j in jahre if j['jahr'] == jahr), {'brutto_cent': 0})
    _prev = next((j for j in jahre if j['jahr'] == jahr - 1), {'brutto_cent': 0})
    def _lage(ist, grenze):
        q = ist / float(grenze) if grenze else 0.0
        return 'ok' if q < 0.8 else ('warn' if q < 1.0 else 'ueber')
    kleinunternehmer = {
        'vorjahr_cent': _prev['brutto_cent'], 'vorjahr_grenze_cent': KU_VORJAHR_CENT,
        'vorjahr_lage': _lage(_prev['brutto_cent'], KU_VORJAHR_CENT),
        'laufend_cent': _cur['brutto_cent'], 'laufend_grenze_cent': KU_LAUFEND_CENT,
        'laufend_lage': _lage(_cur['brutto_cent'], KU_LAUFEND_CENT),
    }
    # --- Monate des laufenden Jahres (fuer die Voranmeldungs-Logik / Beleg)
    a, b = _tax_year_bounds(jahr)
    mon = con.execute(
        "SELECT strftime('%Y-%m', created_at, 'unixepoch') m, COUNT(*) c, "
        "COALESCE(SUM(cents),0) cents FROM purchases "
        "WHERE created_at >= ? AND created_at < ? GROUP BY m ORDER BY m",
        (a, b)).fetchall()
    monate = [{'monat': r['m'], 'anzahl': r['c'], 'brutto_cent': r['cents']}
              for r in mon]
    # --- Belege: jede Kauf-Zeile ist ein aufbewahrungspflichtiger Beleg
    bel = con.execute(
        "SELECT p.session_id, p.pack, p.cents, p.sekunden, p.created_at, u.email "
        "FROM purchases p LEFT JOIN users u ON u.id = p.user_id "
        "ORDER BY p.created_at DESC LIMIT 500").fetchall()
    belege = [dict(r) for r in bel]
    # --- Aufbewahrung
    arch = con.execute("SELECT COUNT(*) c, MIN(created_at) a, MAX(created_at) b "
                       "FROM ledger_archive").fetchone()
    ncons = con.execute("SELECT COUNT(*) c FROM consents").fetchone()['c']
    nledger = con.execute("SELECT COUNT(*) c FROM ledger").fetchone()['c']
    con.close()
    return {
        'identitaet': {
            'regelung': 'Kleinunternehmer nach §19 UStG (small business scheme)',
            'ust_id': (os.environ.get('DVE_TAX_ID') or 'DE463613884').strip(),
            'ust_ausweis': False,
            'name': (os.environ.get('DVE_SELLER_NAME') or 'Ismet Beyazkus').strip(),
            'anschrift': (os.environ.get('DVE_SELLER_ADDR')
                          or 'Hinter den Gärten 4, 52388 Nörvenich, '
                             'Germany').strip(),
            'hinweis': 'Never show a VAT amount or rate on invoices (that is what '
                       '"state VAT" means). The VAT ID itself DOES go on the '
                       'invoice as an identifier, together with the §19 note - '
                       'both are already in the Stripe footer.',
            'rechnungspflicht': [
                'Full name and address of the issuer (§14 (4) 1 UStG) - '
                'carried by the invoice footer and the "Aussteller" field, '
                'independently of the Stripe business profile.',
                'Issue date (§14 (4) 3) - set by Stripe.',
                'Quantity and description of the service (§14 (4) 5) - the '
                'line item carries pack name and minutes of video credit.',
                'Total amount (§14 (4) 7) - set by Stripe, gross, no VAT line.',
                '§19 note - in the footer, on every invoice, no threshold.',
                'VAT ID as identifier (§27a UStG) - in the footer and in the '
                'invoice header field.',
            ],
            'dashboard': 'The invoice HEADER ("From: ...") comes from the '
                         'Stripe business profile, not from this code. Set the '
                         'legal name and full address there as well, otherwise '
                         'the header shows the brand only.',
        },
        'jahr': jahr, 'jahre': jahre, 'monate': monate,
        'kleinunternehmer': kleinunternehmer,
        'belege': belege,
        'aufbewahrung': {
            'belege_jahre': 10, 'rechtsgrundlage': '§147 AO / GoBD',
            'archiv_zeilen': arch['c'], 'archiv_von': arch['a'], 'archiv_bis': arch['b'],
            'ledger_zeilen': nledger,
            'consent_zeilen': ncons,
            'video_tage': RETENTION_DAYS,
            'credit_tage': CREDIT_VALIDITY_DAYS,
        },
        # Art. 30 DSGVO: Verzeichnis der Verarbeitungstaetigkeiten. Bewusst aus
        # dem ECHTEN Schema abgeleitet und nicht frei getextet - so faellt auf,
        # wenn eine neue Tabelle dazukommt und hier nicht auftaucht.
        'verarbeitung': [
            {'daten': 'users (email, name, credit balance, Google ID)',
             'zweck': 'Account and contract performance', 'grundlage': 'Art. 6(1)(b)',
             'frist': 'until the account is deleted'},
            {'daten': 'sessions / verify_tokens / resets',
             'zweck': 'Login, email confirmation, password reset',
             'grundlage': 'Art. 6(1)(b)', 'frist': 'until the token expires'},
            {'daten': 'ledger (credit bookings)',
             'zweck': 'Credit accounting', 'grundlage': 'Art. 6(1)(b)',
             'frist': 'until the account is deleted'},
            {'daten': 'purchases / ledger_archive (purchase records)',
             'zweck': 'Bookkeeping', 'grundlage': 'Art. 6(1)(c) + §147 AO',
             'frist': '10 years, survives account deletion'},
            {'daten': 'consents (withdrawal consent)',
             'zweck': 'Proof under §356(4) BGB', 'grundlage': 'Art. 6(1)(c)',
             'frist': '3 years (limitation period)'},
            {'daten': 'referral_claims / credit_claims (salted hashes)',
             'zweck': 'Fraud prevention on free credit',
             'grundlage': 'Art. 6(1)(f)', 'frist': 'permanent, pseudonymous'},
            {'daten': 'tickets (support messages)',
             'zweck': 'Customer support', 'grundlage': 'Art. 6(1)(b)',
             'frist': 'until resolved, correspondence kept'},
            {'daten': 'video files (upload + render)',
             'zweck': 'Delivering the service', 'grundlage': 'Art. 6(1)(b)',
             'frist': f'{RETENTION_DAYS:.0f} days, then deleted automatically'},
        ],
        'seiten': [
            {'titel': 'Imprint (§5 DDG)', 'url': '/imprint'},
            {'titel': 'Privacy policy', 'url': '/privacy'},
            {'titel': 'Terms / right of withdrawal', 'url': '/terms'},
        ],
    }


@app.get('/api/admin/export/{table}.csv')
def admin_export_csv(table: str, request: Request, since: int = 0, until: int = 0):
    _require_admin(request)
    import csv
    import io
    until = until or int(time.time()) + 1
    con = _db()
    if table == 'purchases':
        rows = con.execute("SELECT session_id, user_id, pack, cents, sekunden, created_at "
                           "FROM purchases WHERE created_at >= ? AND created_at < ? "
                           "ORDER BY created_at", (since, until)).fetchall()
    elif table == 'ledger':
        rows = con.execute("SELECT user_id, delta_sec, grund, created_at FROM ledger "
                           "WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
                           (since, until)).fetchall()
    elif table == 'users':
        rows = con.execute("SELECT id, email, name, verified, disabled, balance_sec, "
                           "created_at FROM users ORDER BY created_at").fetchall()
    else:
        con.close()
        raise HTTPException(400, 'Unknown table (users|purchases|ledger).')
    con.close()
    buf = io.StringIO(); w = csv.writer(buf)
    if rows:
        w.writerow(rows[0].keys())
    for r in rows:
        w.writerow(list(r))
    return Response(content=buf.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{table}.csv"'})


@app.post('/api/admin/backup/run')
def admin_backup_run(request: Request):
    _require_admin(request)
    _backup_users_db(force=True)     # v197: der Knopf muss IMMER sichern
    return {'ok': True, 'last_backup': _last_backup_ts()}


RESTORE_PFLICHT = ('users', 'sessions', 'ledger', 'purchases')


def _pruefe_sicherung(pfad):
    """Kandidat pruefen, BEVOR irgendetwas angefasst wird. Eine kaputte
    Sicherung darf nie eine funktionierende Datenbank ueberschreiben.
    Gibt (ok, meldung, zahlen) zurueck - wirft nicht."""
    try:
        c = sqlite3.connect(f'file:{pfad}?mode=ro', uri=True, timeout=10)
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            c.close()
            return False, 'Die Datei ist beschaedigt (integrity_check).', {}
        da = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        fehlt = [t for t in RESTORE_PFLICHT if t not in da]
        if fehlt:
            c.close()
            return False, f'Pflichttabellen fehlen: {", ".join(fehlt)}', {}
        zahlen = {'konten': c.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                  'kaeufe': c.execute('SELECT COUNT(*) FROM purchases').fetchone()[0],
                  'tabellen': len(da)}
        c.close()
        return True, 'ok', zahlen
    except Exception as e:
        return False, f'Nicht lesbar: {type(e).__name__}: {e}', {}


def _restore_users_db(pfad):
    """v197b: Zurueckspielen OHNE den Server anzuhalten.

    Der Terminal-Weg (`restore.sh`) tauscht die Datei und muss dafuer die App
    stoppen. Im Panel geht das nicht - ein Endpunkt, der seinen eigenen Server
    anhaelt, kann sich danach nicht mehr melden. Deshalb hier der andere Weg:
    die SQLite-Online-Backup-API schreibt die Sicherung IN die laufende
    Datenbank. SQLite haelt dabei selbst die noetigen Sperren, WAL bleibt
    stimmig, offene Verbindungen sehen danach den neuen Inhalt. Kein
    Dateitausch, kein Neustart.

    Reihenfolge der Sicherungsnetze bleibt dieselbe wie im Skript:
      1. Kandidat pruefen (siehe _pruefe_sicherung) - vorher passiert nichts.
      2. Den JETZIGEN Stand als vor_restore_*.db wegschreiben. Auch ein
         Restore kann die falsche Entscheidung sein.
      3. Einspielen, danach das Schema nachziehen: eine alte Sicherung kennt
         spaeter dazugekommene Tabellen/Spalten nicht.
    """
    ok, meldung, zahlen = _pruefe_sicherung(pfad)
    if not ok:
        raise HTTPException(400, meldung)
    bdir = os.path.join(DATA, 'backups')
    os.makedirs(bdir, exist_ok=True)
    vor = os.path.join(bdir, f'vor_restore_{time.strftime("%Y%m%d_%H%M%S")}.db')
    src = sqlite3.connect(USERS_DB, timeout=30)
    dst = sqlite3.connect(vor)
    src.backup(dst)
    dst.close(); src.close()
    # Rotation: 5 Sicherheitskopien reichen, sie fallen nicht unter die
    # Tages-Rotation der Snapshots (anderer Dateiname).
    alte = sorted((f for f in os.listdir(bdir) if f.startswith('vor_restore_')),
                  reverse=True)[5:]
    for f in alte:
        try:
            os.remove(os.path.join(bdir, f))
        except OSError:
            pass
    src = sqlite3.connect(pfad, timeout=30)
    dst = sqlite3.connect(USERS_DB, timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    # v203-sec: Die Sicherung enthaelt die sessions-Tabelle. Ohne dieses
    # Loeschen gilt nach dem Zurueckspielen der ANMELDE-Zustand des
    # Sicherungszeitpunkts: abgemeldete Geraete waeren wieder drin, eine
    # gesperrte Sitzung wieder gueltig. Nach einem Datenbank-Rueckwurf ist
    # "alle melden sich neu an" die richtige Erwartung.
    try:
        c = sqlite3.connect(USERS_DB, timeout=30)
        c.execute('DELETE FROM sessions')
        c.commit(); c.close()
    except Exception as e:
        print(f'RESTORE: sessions konnten nicht geleert werden: {e}')
    _init_users_db()                     # Schema nachziehen (alte Sicherung)
    _ttl_drop('adm:')                    # Aggregate im Cache sind jetzt falsch
    print(f'RESTORE eingespielt: {os.path.basename(pfad)} '
          f'({zahlen.get("konten")} Konten, {zahlen.get("kaeufe")} Kaeufe), '
          f'vorheriger Stand in {os.path.basename(vor)}')
    _notify_admin('restore', 'Datenbank zurueckgespielt',
                  f'Eingespielt: {os.path.basename(pfad)}\n'
                  f'{zahlen.get("konten")} Konten, {zahlen.get("kaeufe")} Kaeufe.\n'
                  f'Der vorherige Stand liegt als {os.path.basename(vor)} '
                  f'in {bdir} und kann genauso zurueckgeholt werden.')
    return {'ok': True, 'quelle': os.path.basename(pfad),
            'vorher_gesichert': os.path.basename(vor), **zahlen}


@app.post('/api/admin/backup/check')
def admin_backup_check(request: Request, datei: str = Form(...)):
    """Probe ohne Wirkung: taugt diese Sicherung ueberhaupt etwas?"""
    _require_admin(request)
    bdir = os.path.join(DATA, 'backups')
    if datei not in (set(os.listdir(bdir)) if os.path.isdir(bdir) else set()):
        raise HTTPException(404, 'Unknown backup file.')
    ok, meldung, zahlen = _pruefe_sicherung(os.path.join(bdir, datei))
    return {'ok': ok, 'meldung': meldung, **zahlen}


@app.post('/api/admin/backup/restore')
def admin_backup_restore(request: Request, datei: str = Form(...),
                         bestaetigung: str = Form('')):
    """Sicherung aus dem Backup-Verzeichnis einspielen. Tippbestaetigung
    wie beim Factory-Reset - das hier ueberschreibt alle Konten."""
    _require_admin(request)
    if bestaetigung.strip().upper() != 'RESTORE':
        raise HTTPException(400, 'Confirmation missing.')
    bdir = os.path.join(DATA, 'backups')
    if datei not in (set(os.listdir(bdir)) if os.path.isdir(bdir) else set()):
        raise HTTPException(404, 'Unknown backup file.')
    return _restore_users_db(os.path.join(bdir, datei))


@app.post('/api/admin/backup/upload')
async def admin_backup_upload(request: Request, file: UploadFile = File(...),
                              bestaetigung: str = Form('')):
    """Sicherung aus dem Postfach hochladen und einspielen. Das ist der Weg
    fuer den Ernstfall: liegt die Platte im Argen, ist die Offsite-Kopie in
    der Mail die einzige, die es noch gibt. .db oder .db.gz."""
    _require_admin(request)
    if bestaetigung.strip().upper() != 'RESTORE':
        raise HTTPException(400, 'Confirmation missing.')
    roh = await file.read()
    if len(roh) > 200 * 1024 * 1024:
        raise HTTPException(400, 'File too large.')
    name = os.path.basename(file.filename or 'upload.db')
    if name.endswith('.gz'):
        import gzip
        try:
            roh = gzip.decompress(roh)
        except Exception:
            raise HTTPException(400, 'Not a valid .gz file.')
        name = name[:-3]
    if not name.endswith('.db'):
        raise HTTPException(400, 'Expected a .db or .db.gz file.')
    bdir = os.path.join(DATA, 'backups')
    os.makedirs(bdir, exist_ok=True)
    ziel = os.path.join(bdir, f'upload_{time.strftime("%Y%m%d_%H%M%S")}.db')
    with open(ziel, 'wb') as f:
        f.write(roh)
    try:
        return _restore_users_db(ziel)
    except HTTPException:
        os.remove(ziel)                  # untaugliche Datei nicht liegenlassen
        raise


@app.get('/api/admin/offsite')
def admin_offsite(request: Request):
    """Zustand der Sicherung ausser Haus. Geheimnisse werden NIE
    ausgeliefert - nur 'gesetzt: ja/nein'. Wer den Bildschirm sieht, soll
    nicht den Schluessel mitlesen koennen."""
    _require_admin(request)
    letzte = _set_get('r2_letzte')
    t, name, groesse = 0, '', 0
    if '|' in letzte:
        teile = letzte.split('|')
        t = int(teile[0] or 0)
        name = teile[1] if len(teile) > 1 else ''
        groesse = int(teile[2] or 0) if len(teile) > 2 else 0
    out = {'bereit': _r2_bereit(),
           'endpoint': _set_get('r2_endpoint'),
           'bucket': _set_get('r2_bucket'),
           'key_gesetzt': bool(_set_get('r2_key').strip()),
           'secret_gesetzt': bool(_set_get('r2_secret').strip()),
           'pass_gesetzt': bool(_set_get('r2_pass').strip()),
           'letzte_ts': t, 'letzte_name': name, 'letzte_bytes': groesse,
           'staende': R2_STAENDE, 'dateien': []}
    if out['bereit']:
        try:
            out['dateien'] = _r2_liste()[:40]
        except Exception as e:
            out['fehler'] = f'{type(e).__name__}: {e}'
    return out


@app.post('/api/admin/offsite/settings')
def admin_offsite_settings(request: Request, endpoint: str = Form(''),
                           key: str = Form(''), secret: str = Form(''),
                           bucket: str = Form(''), passwort: str = Form('')):
    """Zugaenge speichern. Leer gelassene Felder bleiben, wie sie sind -
    sonst muesste man das Geheimnis bei jeder Kleinigkeit neu eintippen."""
    _require_admin(request)
    if endpoint.strip():
        e = endpoint.strip().rstrip('/')
        if not e.startswith('https://'):
            raise HTTPException(400, 'Endpoint must start with https://')
        _set_put('r2_endpoint', e)
    if bucket.strip():
        b = bucket.strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,62}', b):
            raise HTTPException(400, 'Invalid bucket name.')
        _set_put('r2_bucket', b)
    if key.strip():
        _set_put('r2_key', key.strip())
    if secret.strip():
        _set_put('r2_secret', secret.strip())
    if passwort.strip():
        if len(passwort.strip()) < 12:
            raise HTTPException(400, 'Password needs at least 12 characters.')
        _set_put('r2_pass', passwort.strip())
    _sec_event('offsite_settings', request,
               detail='Zugaenge fuer die Sicherung ausser Haus geaendert')
    return {'ok': True, 'bereit': _r2_bereit()}


@app.post('/api/admin/offsite/passwort')
def admin_offsite_passwort(request: Request):
    """v230x DAS PASSWORT NACHSCHLAGEN.

    Ismets Frage: "was, wenn ich das Passwort vergesse?" Zwei Faelle - solange
    der Server lebt, braucht er es gar nicht (das Zurueckspielen nimmt das
    gespeicherte). Ist die Platte tot, ist es MIT ihr weg, und die Kopie ist
    unwiderruflich unlesbar. Genau dafuer gibt es diesen Knopf: nachschlagen,
    solange es noch geht.

    Bewusst POST und ein eigener Aufruf, nicht im Zustand mitgeliefert - so
    steht es nicht bei jedem Laden der Seite im Speicher des Browsers. Wer
    den Admin-Schluessel hat, kaeme ohnehin an die ganze Datenbank; der
    Aufruf wird trotzdem protokolliert."""
    _require_admin(request)
    pw = _set_get('r2_pass')
    if not pw:
        raise HTTPException(400, 'No password set yet.')
    _sec_event('offsite_passwort', request,
               detail='Verschluesselungs-Passwort im Panel angesehen')
    return {'passwort': pw}


@app.post('/api/admin/offsite/test')
def admin_offsite_test(request: Request):
    """Probe: eine kleine Datei hoch, wieder herunter, entschluesseln und
    VERGLEICHEN, danach wieder loeschen. Ein Backup, das man nie
    zurueckgeholt hat, ist kein Backup (v197)."""
    _require_admin(request)
    if not _r2_bereit():
        raise HTTPException(400, 'Not configured yet.')
    name = f'probe_{int(time.time())}.enc'
    inhalt = os.urandom(2048)
    # Ein falscher Zugang ist ein BEDIENFEHLER, kein Serverfehler: die
    # Meldung muss lesbar zurueckkommen (und nicht als 500er im Alarm-Log
    # landen, wo die echten Stoerungen stehen).
    try:
        _r2_put(name, _krypt_pack(inhalt, _set_get('r2_pass')))
        try:
            zurueck = _krypt_unpack(_r2_get(name), _set_get('r2_pass'))
            gleich = (zurueck == inhalt)
        finally:
            try:
                _r2_del(name)
            except Exception:
                pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f'{type(e).__name__}: {e}'[:300])
    if not gleich:
        raise HTTPException(500, 'Probe came back different.')
    return {'ok': True, 'bytes': len(inhalt)}


@app.post('/api/admin/offsite/run')
def admin_offsite_run(request: Request):
    """Jetzt sichern und hochladen."""
    _require_admin(request)
    if not _r2_bereit():
        raise HTTPException(400, 'Not configured yet.')
    _backup_users_db(force=True)
    bdir = os.path.join(DATA, 'backups')
    snaps = sorted(f for f in os.listdir(bdir)
                   if f.startswith('users_') and f.endswith('.db'))
    if not snaps:
        raise HTTPException(500, 'No snapshot to upload.')
    try:
        _offsite_r2(os.path.join(bdir, snaps[-1]))
    except Exception as e:
        raise HTTPException(502, f'{type(e).__name__}: {e}'[:300])
    return {'ok': True, 'datei': snaps[-1] + '.enc'}


@app.post('/api/admin/offsite/restore')
def admin_offsite_restore(request: Request, datei: str = Form(...),
                          bestaetigung: str = Form(''),
                          passwort: str = Form('')):
    """Stand aus dem Bucket zurueckholen und einspielen. `passwort` nur,
    wenn die Kopie mit einem ANDEREN Passwort verschluesselt wurde (etwa
    nach einem Serverwechsel) - sonst nimmt er das gespeicherte."""
    _require_admin(request)
    if bestaetigung.strip().upper() != 'RESTORE':
        raise HTTPException(400, 'Confirmation missing.')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', datei or ''):
        raise HTTPException(400, 'Invalid file name.')
    try:
        blob = _r2_get(datei)
    except Exception as e:
        raise HTTPException(502, f'{type(e).__name__}: {e}'[:300])
    try:
        roh = _krypt_unpack(blob, (passwort.strip() or _set_get('r2_pass')))
    except ValueError as e:
        raise HTTPException(400, str(e))
    bdir = os.path.join(DATA, 'backups')
    os.makedirs(bdir, exist_ok=True)
    ziel = os.path.join(bdir, f'offsite_{time.strftime("%Y%m%d_%H%M%S")}.db')
    with open(ziel, 'wb') as f:
        f.write(roh)
    try:
        return _restore_users_db(ziel)
    except HTTPException:
        os.remove(ziel)
        raise


@app.get('/api/admin/backups')
def admin_backups(request: Request):
    """v197a: Die Sicherungen waren nur ueber die Kommandozeile oder das
    Postfach erreichbar. Im Panel stand bloss ein Datum - man sah also,
    DASS gesichert wurde, kam aber nicht an die Datei."""
    _require_admin(request)
    bdir = os.path.join(DATA, 'backups')
    aus = []
    for f in sorted(os.listdir(bdir) if os.path.isdir(bdir) else [], reverse=True):
        if not f.endswith('.db'):
            continue
        p = os.path.join(bdir, f)
        eintrag = {'datei': f, 'bytes': os.path.getsize(p),
                   'zeit': os.path.getmtime(p),
                   'art': ('vor_restore' if f.startswith('vor_restore')
                           else 'upload' if f.startswith('upload_') else 'snapshot'),
                   'konten': None, 'ok': False}
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True, timeout=5)
            eintrag['ok'] = c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            eintrag['konten'] = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            c.close()
        except Exception:
            pass                       # unlesbar -> ok bleibt False, das IST die Info
        aus.append(eintrag)
    return {'items': aus, 'dir': bdir}


@app.get('/api/admin/backup/download')
def admin_backup_download(request: Request, datei: str):
    """Einzelne Sicherung herunterladen. Der Name wird gegen das echte
    Verzeichnis geprueft - kein Pfad-Durchgriff ueber '..'."""
    _require_admin(request)
    bdir = os.path.join(DATA, 'backups')
    da = set(os.listdir(bdir)) if os.path.isdir(bdir) else set()
    if datei not in da or not datei.endswith('.db'):
        raise HTTPException(404, 'Unknown backup file.')
    return FileResponse(os.path.join(bdir, datei), media_type='application/octet-stream',
                        filename=datei)


@app.get('/api/admin/logs')
def admin_logs(request: Request, zeilen: int = 300, teil: str = ''):
    """v197: Log-Ende im Panel. `teil` waehlt eine rotierte Datei
    ('1'..'5'), leer = die laufende. Nur das ENDE wird gelesen (256 KB),
    ein 5-MB-Log darf keinen Request blockieren."""
    _require_admin(request)
    pfad = LOG_FILE if not teil else f'{LOG_FILE}.{teil}'
    # v203-sec: isdigit() und int() akzeptieren NICHT dieselbe Menge.
    # '²'.isdigit() ist True, int('²') wirft ValueError - das ergab einen
    # 500er statt einer sauberen 400 und schrieb bei jedem Aufruf eine Zeile
    # in die alerts-Tabelle. Der Vergleich gegen die erlaubten Werte kommt
    # ganz ohne Umrechnung aus.
    if teil and teil not in {str(i) for i in range(1, LOG_KEEP + 1)}:
        raise HTTPException(400, 'Unknown log part.')
    da = [os.path.basename(LOG_FILE)] + [
        f'{os.path.basename(LOG_FILE)}.{i}' for i in range(1, LOG_KEEP + 1)
        if os.path.exists(f'{LOG_FILE}.{i}')]
    if not os.path.exists(pfad):
        return {'text': '(kein Log vorhanden)', 'dateien': da, 'bytes': 0}
    gr = os.path.getsize(pfad)
    with open(pfad, 'rb') as f:
        if gr > 262144:
            f.seek(gr - 262144)
            f.readline()                      # angeschnittene Zeile verwerfen
        roh = f.read().decode('utf-8', 'replace')
    zs = roh.rstrip('\n').split('\n')
    return {'text': '\n'.join(zs[-max(10, min(zeilen, 2000)):]),
            'dateien': da, 'bytes': gr}


@app.get('/api/admin/betrieb')
def admin_betrieb(request: Request):
    _require_admin(request)
    return {'stufe': betrieb_stufe(), 'stufen': list(_BETRIEB_STUFEN)}


@app.post('/api/admin/betrieb')
def admin_betrieb_setzen(request: Request, stufe: str = Form(...)):
    """v204-sec NOTAUS. 'notaus' beendet zusaetzlich ALLE Kundensitzungen -
    das ist der Hebel fuer die Stunde, in der man noch nicht weiss, was los
    ist. Zurueck geht es mit derselben Schaltflaeche."""
    _require_admin(request)
    alt_stufe = betrieb_stufe()
    neu_stufe = betrieb_setzen(stufe)
    _sec_event('betrieb', request, wer='admin',
               detail=f'{alt_stufe} -> {neu_stufe}')
    if neu_stufe != 'normal':
        _notify_admin(f'betrieb:{neu_stufe}', f'Betrieb auf {neu_stufe} gesetzt',
                      f'Der Betriebszustand wurde von {alt_stufe} auf '
                      f'{neu_stufe} geschaltet.', mail=False)
    return {'ok': True, 'stufe': neu_stufe}


@app.get('/api/admin/events')
def admin_events(request: Request, limit: int = 200, aktion: str = ''):
    """v204-sec: die Chronik. Wer wann was - Admin-Zugriffe, Logins,
    Passwortwechsel, Notaus."""
    _require_admin(request)
    lim = min(max(int(limit), 1), 1000)
    con = _db()
    if aktion:
        rows = con.execute(
            "SELECT * FROM security_events WHERE aktion = ? "
            "ORDER BY ts DESC LIMIT ?", (aktion[:40], lim)).fetchall()
    else:
        rows = con.execute("SELECT * FROM security_events ORDER BY ts DESC "
                           "LIMIT ?", (lim,)).fetchall()
    arten = [r['aktion'] for r in con.execute(
        "SELECT aktion FROM security_events GROUP BY aktion ORDER BY aktion")]
    con.close()
    return {'events': [dict(r) for r in rows], 'arten': arten,
            'aufbewahrung_tage': SEC_EVENT_TAGE}


@app.post('/api/admin/mail/test')
def admin_mail_test(request: Request):
    _require_admin(request)
    try:
        _send_mail(ADMIN_MAIL, 'DouchkoVE admin test mail',
                   'This is a test mail from the admin panel. Delivery works.')
    except Exception as e:
        raise HTTPException(502, f'Mail failed: {type(e).__name__}: {e}')
    return {'ok': True, 'to': ADMIN_MAIL}


@app.post('/api/admin/cleanup/run')
def admin_cleanup_run(request: Request):
    _require_admin(request)
    now = time.time(); cutoff = RETENTION_DAYS * 86400; removed = 0
    if os.path.isdir(JOBS_DIR):
        for jid in list(os.listdir(JOBS_DIR)):
            d = os.path.join(JOBS_DIR, jid)
            try:
                if os.path.isdir(d) and now - os.path.getmtime(d) > cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    JOBS.pop(jid, None)
                    removed += 1
            except OSError:
                pass
    return {'ok': True, 'removed': removed}


@app.post('/api/admin/expiry/run')
def admin_expiry_run(request: Request):
    _require_admin(request)
    _credit_expiry_sweep()
    return {'ok': True}


@app.post('/api/admin/refund')
def admin_refund(request: Request, session_id: str = Form(...), clawback: str = Form('1')):
    """Echte Stripe-Erstattung nach session_id (best-effort) + optionaler Credit-
    Clawback + traceable 'Refund {session}'-Ledger-Zeile. Bewegt ECHTES Geld."""
    _require_admin(request)
    con = _db()
    p = con.execute("SELECT user_id, cents, sekunden FROM purchases WHERE session_id = ?",
                    (session_id,)).fetchone()
    # v130-fix: Idempotenz. Existiert schon eine 'Refund {session}'-Ledger-Zeile,
    # war dieser Kauf bereits erstattet -> No-op (kein zweiter Geld-Refund, kein
    # zweiter Clawback). 'Refund %' hat keinen Unique-Index, also hier pruefen.
    already = con.execute("SELECT 1 FROM ledger WHERE grund LIKE ?",
                          (f'Refund {session_id}%',)).fetchone()
    con.close()
    if not p:
        raise HTTPException(404, 'No purchase with that session_id.')
    if already:
        return {'ok': True, 'already_refunded': True,
                'stripe': 'skipped (already refunded)', 'clawed_back_min': 0}
    uid = p['user_id']; sek = p['sekunden']
    # v135a: der 10%-Reload-Bonus dieses Kaufs gehoert mit zurueckgeholt.
    con = _db()
    _bon = con.execute("SELECT COALESCE(SUM(delta_sec),0) s FROM ledger WHERE "
                       "user_id = ? AND grund = ?",
                       (uid, f'Reload bonus {session_id}')).fetchone()['s']
    con.close()
    claw_base = sek + max(0, int(_bon or 0))
    stripe_result = 'skipped (no stripe configured)'
    st = _stripe()
    if st:
        try:
            sess = st.checkout.Session.retrieve(session_id)
            pi = sess.get('payment_intent') if isinstance(sess, dict) else getattr(sess, 'payment_intent', None)
            if pi:
                # Stripe-Idempotency-Key: ein Doppelklick erstattet nie doppelt Geld.
                st.Refund.create(payment_intent=pi, idempotency_key=f'refund_{session_id}')
                stripe_result = 'refunded'
            else:
                stripe_result = 'no payment_intent on session'
        except Exception as e:
            # v135a: bei Stripe-Fehler NICHTS buchen. Frueher wurde die
            # 'Refund %'-Zeile trotzdem geschrieben -> der Idempotenz-Check
            # sperrte jeden Retry und das echte Geld war per API nie mehr
            # erstattbar. Jetzt: sauberer Fehler, Retry bleibt moeglich.
            raise HTTPException(502, f'Stripe refund failed: {type(e).__name__}: '
                                     f'{e}. Nothing was booked - retry is safe.')
    # v206: Die Erstattung wird als eigener Vorgang festgehalten - sonst
    # zaehlt das Panel dieses Geld weiter als Einnahme (und die Steuer-Ampel
    # auch). Erst NACH dem erfolgreichen Stripe-Aufruf, damit hier nie eine
    # Erstattung steht, die es in Wirklichkeit nicht gab.
    try:
        _c_ref = _db()
        _c_ref.execute("INSERT OR IGNORE INTO refunds (session_id, user_id, "
                       "cents, quelle, created_at) VALUES (?,?,?,'panel',?)",
                       (session_id, uid, int(p['cents'] or 0), int(time.time())))
        _c_ref.commit(); _c_ref.close()
    except Exception as e:
        print(f'Erstattung nicht vermerkt ({session_id}): {type(e).__name__}: {e}')
    # v135a: Clawback ATOMAR (BEGIN IMMEDIATE) - kein TOCTOU zwischen Lesen
    # der Balance und Buchen; Ledger-Zeile entspricht exakt der Bewegung.
    do_claw = str(clawback).strip() in ('1', 'true', 'on', 'yes')
    claw_sec = 0
    con = _db()
    try:
        con.isolation_level = None
        con.execute('BEGIN IMMEDIATE')
        cur = con.execute("SELECT balance_sec FROM users WHERE id = ?",
                          (uid,)).fetchone()
        if do_claw and cur:
            claw_sec = min(claw_base, max(0, cur['balance_sec']))
        con.execute("UPDATE users SET balance_sec = balance_sec - ? WHERE id = ?",
                    (claw_sec, uid))
        con.execute("INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (uid, -claw_sec,
                     f'Refund {session_id} admin'
                     + (' clawback' if claw_sec else ' (money only)'),
                     int(time.time())))
        con.execute('COMMIT')
    finally:
        con.close()
    return {'ok': True, 'stripe': stripe_result, 'clawed_back_min': claw_sec // 60}


@app.get('/api/admin/users')
def admin_users(request: Request, q: str = '', limit: int = 50, offset: int = 0,
                sort: str = 'created_at', flt: str = ''):
    _require_admin(request)
    limit = max(1, min(200, limit)); offset = max(0, offset)
    sort_col = {'created_at': 'created_at', 'balance': 'balance_sec',
                'email': 'email'}.get(sort, 'created_at')
    where = []; args = []
    if q.strip():
        where.append("email LIKE ?"); args.append(f'%{q.strip().lower()}%')
    if flt == 'unverified':
        where.append("verified = 0")
    elif flt == 'verified':
        where.append("verified = 1")
    elif flt == 'disabled':
        where.append("disabled = 1")
    wsql = (' WHERE ' + ' AND '.join(where)) if where else ''
    con = _db()
    total = con.execute(f"SELECT COUNT(*) c FROM users{wsql}", args).fetchone()['c']
    rows = con.execute(
        f"SELECT id, email, name, verified, disabled, balance_sec, created_at "
        f"FROM users{wsql} ORDER BY {sort_col} DESC LIMIT ? OFFSET ?",
        args + [limit, offset]).fetchall()
    con.close()
    buyers = _admin_purchaser_ids()
    return {'total': total, 'limit': limit, 'offset': offset,
            'users': [{'id': r['id'], 'email': r['email'], 'name': r['name'],
                       'verified': bool(r['verified']),
                       'disabled': bool(_row_get(r, 'disabled')),
                       'credits': credits_of(r['balance_sec']),
                       'balance_sec': r['balance_sec'], 'created_at': r['created_at'],
                       'purchased': r['id'] in buyers} for r in rows]}


@app.get('/api/admin/users/{uid}')
def admin_user_detail(uid: int, request: Request):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    now = int(time.time())
    con = _db()
    led = con.execute("SELECT delta_sec, grund, created_at FROM ledger "
                      "WHERE user_id = ? ORDER BY created_at DESC LIMIT 100", (uid,)).fetchall()
    pur = con.execute("SELECT session_id, pack, cents, sekunden, created_at FROM purchases "
                      "WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
    cons = con.execute("SELECT kind, created_at FROM consents WHERE user_id = ? "
                       "ORDER BY created_at DESC", (uid,)).fetchall()
    ltv = con.execute("SELECT COALESCE(SUM(cents),0) cents, COUNT(*) c FROM purchases "
                      "WHERE user_id = ?", (uid,)).fetchone()
    rcount = con.execute("SELECT COUNT(*) c FROM ledger WHERE user_id = ? AND "
                         "grund LIKE 'Render %'", (uid,)).fetchone()['c']
    active_sess = con.execute("SELECT COUNT(*) c FROM sessions WHERE user_id = ? "
                              "AND expires_at > ?", (uid, now)).fetchone()['c']
    con.close()
    refby = _row_get(u, 'referred_by')
    try:
        exp_sec, exp_days = _expiring_info(uid, 30)
    except Exception:
        exp_sec, exp_days = 0, None
    return {
        'user': {'id': u['id'], 'email': u['email'], 'name': u['name'],
                 'verified': bool(u['verified']), 'disabled': bool(_row_get(u, 'disabled')),
                 'credits': credits_of(u['balance_sec']), 'balance_sec': u['balance_sec'],
                 'created_at': u['created_at'],
                 'is_owner': str(u['email']).strip().lower() == OWNER_EMAIL,
                 'disposable': _is_disposable_email(u['email']),
                 'ref_code': _row_get(u, 'ref_code'),
                 'referred_by_email': _admin_email(refby) if refby else None,
                 'ltv_eur': round(ltv['cents'] / 100.0, 2), 'orders': ltv['c'],
                 'render_count': rcount, 'active_sessions': active_sess,
                 'expiring_credits': credits_of(exp_sec), 'expiring_days': exp_days},
        'ledger': [{'delta_sec': r['delta_sec'], 'grund': r['grund'],
                    'created_at': r['created_at']} for r in led],
        'purchases': [{'session_id': r['session_id'], 'pack': r['pack'],
                       'eur': round(r['cents'] / 100.0, 2), 'minutes': r['sekunden'] // 60,
                       'created_at': r['created_at']} for r in pur],
        'consents': [{'kind': r['kind'], 'created_at': r['created_at']} for r in cons],
    }


@app.post('/api/admin/users/{uid}/credits')
def admin_user_credits(uid: int, request: Request,
                       delta_min: int = Form(...), reason: str = Form('')):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    delta = int(delta_min) * 60
    if delta < 0:
        delta = max(delta, -u['balance_sec'])
    if delta == 0:
        return {'ok': True, 'credits': credits_of(u['balance_sec']), 'changed': 0}
    reason = (reason or '').strip()[:80] or 'manual'
    _adjust_balance(uid, delta, f'Admin adjust {reason}')
    nu = _find_user_by_id(uid)
    return {'ok': True, 'credits': credits_of(nu['balance_sec']), 'balance_sec': nu['balance_sec']}


@app.post('/api/admin/users/{uid}/verify')
def admin_user_verify(uid: int, request: Request):
    _require_admin(request)
    con = _db()
    con.execute("UPDATE users SET verified = 1 WHERE id = ?", (uid,))
    con.commit(); con.close()
    return {'ok': True}


@app.post('/api/admin/users/{uid}/resend_verify')
def admin_user_resend(uid: int, request: Request):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    if u['verified']:
        return {'ok': True, 'already_verified': True}
    _send_verify_mail(uid, u['email'], u['name'])
    return {'ok': True}


@app.post('/api/admin/users/{uid}/reset')
def admin_user_reset(uid: int, request: Request):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    tok = _create_reset(uid)
    base = os.environ.get('DVE_PUBLIC_URL', 'https://douchko.eu').rstrip('/')
    link = f'{base}/app?reset={tok}'
    try:
        _send_mail(u['email'], 'Reset your DouchkoVE password',
                   f'Hi{" " + u["name"] if u["name"] else ""},\n\n'
                   f'a password reset was requested for your account.\n\n'
                   f'Reset link (valid 30 minutes):\n{link}\n\n- DouchkoVE')
    except Exception as e:
        return {'ok': True, 'mail': f'failed: {type(e).__name__}', 'link': link}
    return {'ok': True, 'mail': 'sent'}


@app.post('/api/admin/users/{uid}/revoke_sessions')
def admin_user_revoke(uid: int, request: Request):
    _require_admin(request)
    con = _db()
    n = con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,)).rowcount
    con.commit(); con.close()
    return {'ok': True, 'revoked': n}


@app.post('/api/admin/users/{uid}/disable')
def admin_user_disable(uid: int, request: Request, on: str = Form('1')):
    _require_admin(request)
    val = 1 if str(on).strip() in ('1', 'true', 'on', 'yes') else 0
    con = _db()
    con.execute("UPDATE users SET disabled = ? WHERE id = ?", (val, uid))
    if val:
        con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))   # sofort ausloggen
    con.commit(); con.close()
    return {'ok': True, 'disabled': bool(val)}


@app.get('/api/admin/users/{uid}/export')
def admin_user_export(uid: int, request: Request):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    con = _db()
    led = [dict(r) for r in con.execute(
        "SELECT delta_sec, grund, created_at FROM ledger WHERE user_id = ?", (uid,)).fetchall()]
    pur = [dict(r) for r in con.execute(
        "SELECT session_id, pack, cents, sekunden, created_at FROM purchases "
        "WHERE user_id = ?", (uid,)).fetchall()]
    cons = [dict(r) for r in con.execute(
        "SELECT kind, created_at FROM consents WHERE user_id = ?", (uid,)).fetchall()]
    con.close()
    return {'user': {'id': u['id'], 'email': u['email'], 'name': u['name'],
                     'verified': bool(u['verified']), 'created_at': u['created_at'],
                     'balance_sec': u['balance_sec']},
            'ledger': led, 'purchases': pur, 'consents': cons}


@app.post('/api/admin/users/{uid}/delete')
def admin_user_delete(uid: int, request: Request):
    _require_admin(request)
    u = _find_user_by_id(uid)
    if not u:
        raise HTTPException(404, 'Unknown user.')
    for jid in [jid for jid, j in list(JOBS.items()) if j.get('user_id') == uid]:
        shutil.rmtree(job_dir(jid), ignore_errors=True); JOBS.pop(jid, None)
    _purge_user_db(uid)
    return {'ok': True}


@app.get('/api/admin/codes')
def admin_codes_list(request: Request):
    _require_admin(request)
    c = load_codes()
    return {'codes': [dict({'code': k}, **v) for k, v in c.items()]}


@app.post('/api/admin/codes')
def admin_codes_write(request: Request, action: str = Form(...), code: str = Form(''),
                      name: str = Form(''), limit: int = Form(5)):
    _require_admin(request)
    import random
    import string
    c = load_codes()
    if action == 'new':
        code = (name.upper()[:6].replace(' ', '') or 'CODE') + '-' + \
            ''.join(random.choices(string.digits, k=4))
        c[code] = {'name': name or 'Tester', 'limit': int(limit), 'genutzt': 0, 'aktiv': True}
    elif action in ('block', 'unblock') and code in c:
        c[code]['aktiv'] = (action == 'unblock')
    elif action == 'limit' and code in c:
        c[code]['limit'] = int(limit)
    else:
        raise HTTPException(400, 'Unknown action or code.')
    save_codes(c)
    return {'ok': True, 'code': code}
