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
import copy
import glob
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from queue import Queue

import yaml
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get('DVE_DATA', os.path.join(HERE, 'data'))
# v96p: Besitzer-Konto. Nur dieses Konto sieht/bedient die Stil-Referenzen
# (global wirksam). Ueberschreibbar per DVE_OWNER.
OWNER_EMAIL = os.environ.get('DVE_OWNER', 'ismet-01_b@hotmail.de').strip().lower()
JOBS_DIR = os.path.join(DATA, 'jobs')
CODES_FILE = os.path.join(DATA, 'codes.json')
USERS_DB = os.path.join(DATA, 'users.db')
MAX_MB = int(os.environ.get('DVE_MAX_MB', '300'))
MAX_SECONDS = int(os.environ.get('DVE_MAX_SECONDS', '180'))
SESSION_DAYS = 30
TRIAL_SECONDS = int(os.environ.get('DVE_TRIAL_SECONDS', '120'))  # 2 Min gratis
RETENTION_DAYS = float(os.environ.get('DVE_RETENTION_DAYS', '7'))


# v84: Credits statt roher Minuten. Intern bleibt alles Sekunden (bewaehrt),
# 1 Credit = 1 Minute Video. Abgerechnet wird pro ANGEFANGENER Minute -
# so ist die Balance immer ein glattes Vielfaches von 60 und die Credit-
# Anzeige nie krumm (Guthaben-Gutschriften sind ebenfalls ganze Minuten).
import math as _math


def credits_of(sec):
    """Sekunden -> ganze Credits (fuer die Anzeige)."""
    return int(sec) // 60


def cost_seconds(dur_sec):
    """Was ein Video kostet: pro angefangener Minute, mindestens 1 Credit."""
    return max(1, _math.ceil(float(dur_sec) / 60.0)) * 60

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
    con = sqlite3.connect(USERS_DB)
    con.row_factory = sqlite3.Row
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
    """)
    con.commit()
    # v80x: verified-Spalte nachziehen. Bestands-Accounts werden als
    # verifiziert uebernommen (Grandfathering), Neue starten bei 0.
    cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
    if 'verified' not in cols:
        con.execute("ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        con.execute("UPDATE users SET verified = 1")
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
    con = _db()
    try:
        cur = con.execute(
            "INSERT INTO users (email, pw_hash, name, balance_sec, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (email.strip().lower(), _hash_pw(pw), name.strip()[:60],
             TRIAL_SECONDS, int(time.time())))
        uid = cur.lastrowid
        if TRIAL_SECONDS > 0:
            con.execute(
                "INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, TRIAL_SECONDS, 'Welcome credit', int(time.time())))
        con.commit()
        return uid, None
    except sqlite3.IntegrityError:
        return None, 'This email is already registered.'
    finally:
        con.close()


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
    return row


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
def _send_mail(to, subject, body):
    """Mail-Versand. Bevorzugt Resend (HTTP/443, von Hostern nie geblockt),
    faellt auf SMTP zurueck. Wirft bei Fehler."""
    resend_key = os.environ.get('RESEND_API_KEY', '').strip()
    if resend_key:
        import requests as _rq
        sender = os.environ.get('MAIL_FROM', 'onboarding@resend.dev')
        r = _rq.post('https://api.resend.com/emails',
                     headers={'Authorization': f'Bearer {resend_key}'},
                     json={'from': f'DouchkoVE <{sender}>', 'to': [to],
                           'subject': subject, 'text': body}, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f'Resend {r.status_code}: {r.text[:200]}')
        return
    import smtplib
    from email.mime.text import MIMEText
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER', '').strip()
    pw = os.environ.get('SMTP_PASS', '').replace(' ', '').strip()
    sender = os.environ.get('MAIL_FROM', user)
    if not user or not pw:
        raise RuntimeError('SMTP not configured')
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = f'DouchkoVE <{sender}>'
    msg['To'] = to
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
    hallo = f'Hey {name},' if name else 'Hey,'
    subject = (f'Welcome to DouchkoVE, {name}!' if name
               else 'Welcome to DouchkoVE!')
    try:
        _send_mail(
            email, subject,
            f'{hallo}\n\n'
            f"Ismet here, the person behind DouchkoVE. Thank you so much for "
            f"signing up, it genuinely means a lot while we're still in beta.\n\n"
            f'Just one quick step: tap the link below to confirm your email. '
            f'Then your account is fully set up and your free credits are ready '
            f'to use.\n\n'
            f'{base}/app?verify={tok}\n\n'
            f"Once you're in, drop a talking-head video and let the AI direction "
            f"do its thing. Heads-up: we're in beta and every video is rendered "
            f"on our own server, so it takes a few minutes for now. That will get "
            f"much faster once we leave beta.\n\n"
            f'If anything feels off or you have an idea, just reply to this '
            f'email, it comes straight to me.\n\n'
            f'The link is valid for 48 hours.\n\n'
            f'Talk soon,\nIsmet from DouchkoVE')
        return True
    except Exception as e:
        print(f'Verify-Mail fehlgeschlagen: {type(e).__name__}: {e}')
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
        'beschreibung_en': 'Weekly posting schedule. Cheapest per-credit price under €0.35.',
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
    Standard: dauerhafter Free-Tier statt einmaligem Trial). Idempotent
    ueber Ledger-Eintrag pro Monat."""
    if not u or not u['verified']:
        return False
    stamp = time.strftime('%Y-%m')
    grund = f'Monthly free credit {stamp}'
    con = _db()
    row = con.execute("SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
                      (u['id'], grund)).fetchone()
    con.close()
    if row:
        return False
    _adjust_balance(u['id'], 180, grund)
    return True


def _render_charged(user_id, jid):
    """v80s: Wurde dieser Job schon abgerechnet? Re-Render = inklusive."""
    con = _db()
    row = con.execute(
        "SELECT id FROM ledger WHERE user_id = ? AND grund LIKE ?",
        (user_id, f'Render {jid} %')).fetchone()
    con.close()
    return row is not None


def _reserve_credits(uid, need, jid):
    """v92: Guthaben beim Upload ATOMAR reservieren (nicht erst nach dem
    Render abziehen). Ein einziges bedingtes UPDATE zieht 'need' nur ab,
    wenn wirklich genug da ist - fest gegen gleichzeitige Uploads
    (SQLite serialisiert Writes). Frueher wurde nur *geprueft*, dann spaeter
    abgezogen -> wer mit 1 Credit 10 Videos gleichzeitig hochlud, bekam 10.
    Gibt True bei Erfolg (Guthaben abgezogen + Ledger), sonst False."""
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
            (uid, -need, f'Render {jid} ({need}s)', int(time.time())))
        con.commit()
        return True
    finally:
        con.close()


def _refund_credits(uid, jid, need):
    """Reservierung zurueckbuchen. Idempotent ueber den 'Refund {jid}'-Ledger-
    Eintrag - Stripe/Worker koennen mehrfach ausloesen."""
    if not uid or need <= 0:
        return
    con = _db()
    try:
        if con.execute("SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
                       (uid, f'Refund {jid}')).fetchone():
            return
        con.execute("UPDATE users SET balance_sec = balance_sec + ? WHERE id = ?",
                    (need, uid))
        con.execute(
            "INSERT INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, need, f'Refund {jid}', int(time.time())))
        con.commit()
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
    _refund_credits(uid, jid, cost_seconds(j.get('dauer', 0)))


def _pack_processed(user_id, session_id):
    """Idempotenz-Check: wurde diese Stripe-Session bereits gutgeschrieben?"""
    con = _db()
    row = con.execute(
        "SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
        (user_id, f'Kauf {session_id}')).fetchone()
    con.close()
    return row is not None


def _credit_purchase(uid, sec, session_id):
    """v92-sec: Kauf ATOMAR + idempotent gutschreiben. Der 'INSERT OR IGNORE'
    prallt am partiellen UNIQUE-Index (user_id, 'Kauf {id}') ab, wenn dieselbe
    Stripe-Session schon verbucht ist - auch bei zwei gleichzeitigen Webhooks.
    Nur wenn wirklich eine neue Zeile entstand, wird das Guthaben erhoeht.
    Gibt True zurueck, wenn frisch gutgeschrieben wurde."""
    con = _db()
    try:
        cur = con.execute(
            "INSERT OR IGNORE INTO ledger (user_id, delta_sec, grund, created_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, sec, f'Kauf {session_id}', int(time.time())))
        if cur.rowcount != 1:
            con.commit()
            return False                     # schon verbucht
        con.execute("UPDATE users SET balance_sec = MAX(0, balance_sec + ?) "
                    "WHERE id = ?", (sec, uid))
        con.commit()
        return True
    finally:
        con.close()


app = FastAPI(title='DouchkoVE')


# v92-sec: Security-Header auf JEDER Antwort. Zweite Verteidigungslinie gegen
# XSS (CSP), Clickjacking (frame-ancestors/XFO), Token-Leak per Referer
# (Referrer-Policy) und MIME-Sniffing (nosniff). Caddy setzt sie am Rand
# zusaetzlich - hier greifen sie auch, falls die App direkt erreichbar ist.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "        # index.html nutzt Inline-<script> + onclick=
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self'; "
    "connect-src 'self' https://api.stripe.com; "
    "frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self' https://checkout.stripe.com"
)


# Build-Stempel: zeigt an, welcher Stand wirklich live ist (per Header sichtbar).
DVE_BUILD = 'v96q-reffeedback'


@app.middleware('http')
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers['Content-Security-Policy'] = _CSP
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    resp.headers['X-DVE-Version'] = DVE_BUILD
    return resp


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


@app.post('/api/checkout')
async def api_checkout(request: Request, pack: str = Form(...)):
    """Erstellt eine Stripe-Checkout-Session und liefert die URL zurueck.
    Weiterleitung dorthin macht der Client (window.location)."""
    u = _require_user(request)
    if not u['verified']:
        raise HTTPException(403, 'Please verify your email before purchasing - '
                                 'check your inbox, or resend the link in '
                                 'Account settings.')
    if pack not in PACKS:
        raise HTTPException(400, 'Unknown pack.')
    st = _stripe()
    if not st:
        raise HTTPException(503, 'Payment is not configured yet. '
                                 'Please try again later.')
    p = PACKS[pack]
    base = os.environ.get('DVE_PUBLIC_URL', '').rstrip('/') or str(request.base_url).rstrip('/')
    try:
        session = st.checkout.Session.create(
            mode='payment',
            payment_method_types=['card', 'sepa_debit'],
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
        return {'ok': True, 'url': session.url}
    except Exception as e:
        cls = type(e).__name__
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
    if ev_type not in ('checkout.session.completed',
                       'checkout.session.async_payment_succeeded'):
        return {'ok': True, 'ignored': ev_type}
    sess = event.get('data', {}).get('object', {})
    if sess.get('payment_status') != 'paid':
        return {'ok': True, 'pending': sess.get('payment_status')}
    meta = sess.get('metadata') or {}
    try:
        uid = int(meta.get('user_id'))
        sec = int(meta.get('sekunden'))
        pack = meta.get('pack', '?')
        sess_id = sess.get('id', '')
    except Exception:
        raise HTTPException(400, 'Metadata incomplete.')
    # Atomar + idempotent (siehe _credit_purchase). Doppelte/erneute Webhooks
    # fuer dieselbe Session koennen nicht doppelt gutschreiben.
    if not _credit_purchase(uid, sec, sess_id):
        return {'ok': True, 'idempotent': True}
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
JOBS = {}
QUEUE = Queue()
LOCK = threading.Lock()

# Presets als Startpunkt. Der Nutzer kann alles individuell nachjustieren.
LOOKS = {
    'tiktok':    {'name': 'TikTok', 'desc': 'Word by word, bold, loud.'},
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

def _sanitize_overrides(ov):
    """v92 SECURITY: cfg_overrides kommt vom Client und wird tief in die
    Render-Config gemerged. Ohne Filter koennte ein Nutzer beliebige Keys
    setzen (4K-Aufloesung, ProRes-Master, riesige Blender-Werte) und so die
    Server-Last pro Render hochtreiben. Nur bekannte Sektionen zulassen und
    die teuren Regler hart deckeln."""
    if not isinstance(ov, dict):
        return {}
    out = {k: v for k, v in ov.items() if k in _OV_SECTIONS}
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
                o['height'] = min(max(int(o['height']), 480), 1920)
            except Exception:
                o.pop('height', None)
        o.pop('master', None)          # ProRes-Master nie per Override (Riesen-Files)
    e = out.get('effects')
    if isinstance(e, dict):
        for k, cap in (('blender_samples', 256), ('blender_anim_frames', 24),
                       ('blender_width', 1920)):
            if k in e:
                try:
                    e[k] = min(int(e[k]), cap)
                except Exception:
                    e.pop(k, None)
    return out


def build_config(look, overrides=None):
    """Config-Kaskade: config.yaml -> Preset -> User-Overrides.
    Serverseitige Zwaenge werden am Ende hart ueberschrieben (Blender aus).

    Presets sind Stand 2026 - jeder ist eine vollstaendige High-End-Konfig
    quer durch alle Effekte, Kamera, Farben und Schrift. Nutzer kann alles
    einzeln nachtunen; die Defaults sind aber schon deploybar."""
    cfg = yaml.safe_load(open(os.path.join(ROOT, 'config.yaml'), encoding='utf-8'))

    # --- 2026er High-End-Presets (voll ausgereizt, produktionsreif)
    PRESETS = {
        'tiktok': {
            'effects': {
                # Wortweise, dicht, energisch - Reels/Shorts-Kern-Modus 2026
                'density': 'wortweise', 'text_style': '3d kinetisch',
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
            },
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
def job_dir(jid):
    return os.path.join(JOBS_DIR, jid)


def set_state(jid, **kw):
    j = JOBS.setdefault(jid, {})
    j.update(kw)
    try:
        json.dump({k: v for k, v in j.items() if k not in ('input', 'code')},
                  open(os.path.join(job_dir(jid), 'state.json'), 'w',
                       encoding='utf-8'), ensure_ascii=False)
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
    env = dict(os.environ)

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
    log = []
    t0_render = time.time()
    frame_start_t = None
    for line in p.stdout:
        log.append(line.rstrip())
        ln = line.strip()
        # letzte 8 nicht-leeren Zeilen als log_tail
        tail = [x for x in log[-40:] if x.strip()][-8:]

        phase = None
        progress = None
        eta = None
        if 'Transkribiere' in ln:
            phase = 'Listening to every word you said …'
            progress = 0.05
        elif 'Woerter' in ln and 'Transkript' in ln:
            phase = 'Pinning each word to the exact millisecond …'
            progress = 0.10
        elif 'Gesichts-Tracking' in ln:
            phase = 'Finding you in the frame and splitting the scenes …'
            progress = 0.20
        elif 'Musik-Beat' in ln:
            phase = 'Feeling out the rhythm of your music …'
            progress = 0.28
        elif 'KI-Regie' in ln and 'analysiert' in ln:
            phase = 'Our AI director is reading your script …'
            progress = 0.35
        elif 'Vision-Regie' in ln:
            phase = 'Taking a closer look at your footage, frame by frame …'
            progress = 0.38
        elif ln.startswith('Keywords'):
            phase = 'The big moments are locked in …'
            progress = 0.40
        elif 'Adaptive Farben' in ln:
            phase = 'Picking caption colors straight from your scene …'
            progress = 0.43
        elif 'Kompositionen' in ln:
            phase = 'Laying your words out like a magazine spread …'
            progress = 0.45
        elif 'Matting-Fenster' in ln:
            phase = 'Cutting you cleanly out from the background …'
            progress = 0.47
        elif 'Tiefen-Okklusion' in ln:
            phase = 'Working out what sits in front of you …'
            progress = 0.49
        elif 'Kamera-Track' in ln:
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
        elif ln.startswith('Fertig') or 'Encode fertig' in ln:
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


def worker():
    while True:
        jid = QUEUE.get()
        try:
            run_job(jid)
        except Exception as e:
            set_state(jid, status='fehler',
                      msg=f'Unerwarteter Fehler: {type(e).__name__}: {e}')
        finally:
            QUEUE.task_done()


def run_job(jid):
    """Voller Render: Analyse -> Momente -> Video-Bau."""
    j = JOBS[jid]
    d = job_dir(jid)
    mode = j.get('mode', 'full')
    if mode == 'pre':
        # v83: Sofort-Transkription. Laeuft im Hintergrund waehrend der User
        # noch Presets einstellt. Schreibt quelle_transcript2.json - der
        # volle Render findet den Cache automatisch und spart die Whisper-
        # Wartezeit. Schlaegt sie fehl, ist das NICHT fatal: der Render
        # transkribiert dann einfach selbst.
        rc, log, out = _run_render(jid, extra_args=['--transcribe-only'],
                                   out_name='plan.mp4', progress_start=0.10)
        set_state(jid, status='vorbereitet', progress=1.0,
                  phase='Transcript ready' if rc == 0 else 'Prepared')
        # Hat der User waehrenddessen schon Render gedrueckt? Dann direkt
        # weiter. dict.pop ist unter dem GIL atomar - entweder holt der
        # Worker den Auftrag oder /api/render_start, nie beide.
        nxt = JOBS[jid].pop('next_mode', None)
        if nxt:
            JOBS[jid]['mode'] = nxt
            set_state(jid, status='wartet', progress=0.0, phase='Queued …')
            QUEUE.put(jid)
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
    if mode == 'demo':
        # v89: anonyme Kostprobe - immer Wasserzeichen, nur die ersten 10s.
        _extra = ['--watermark', '--duration', '10']
    elif _uid and not _has_purchased(_uid):
        _extra = ['--watermark']
    rc, log, out = _run_render(jid, extra_args=_extra)
    log_txt = '\n'.join(log)
    # v80g: Menschliche Fehlermeldungen aus dem Render-Log herausklauben
    if 'OPENAI_API_KEY ist nicht gesetzt' in log_txt:
        set_state(jid, status='fehler', progress=0,
                  msg='Server is not fully configured '
                      '(AI key missing). Please contact support.')
        _maybe_refund(jid)
        return
    for line in reversed(log):                 # letzte FEHLER-Zeile gewinnt
        if line.startswith('FEHLER:'):
            # v80o: Kontext mitliefern - die Zeilen um den Fehler herum
            # helfen bei der Diagnose direkt in der Web-UI.
            idx = len(log) - 1 - list(reversed(log)).index(line)
            ctx = [x for x in log[max(0, idx - 5):idx + 6] if x.strip()]
            set_state(jid, status='fehler', progress=0,
                      msg=line.replace('FEHLER:', '').strip(),
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
            verbrauch = cost_seconds(j.get('dauer', 0))
            _adjust_balance(uid, -verbrauch,
                            f'Render {jid} ({verbrauch}s)')
        set_state(jid, status='fertig', progress=1.0, phase='Done',
                  out='fertig.mp4')
    else:
        letzte = [x for x in log[-15:] if x.strip()]
        set_state(jid, status='fehler', progress=0,
                  msg='Render failed.',
                  detail='\n'.join(letzte))
        _maybe_refund(jid)
    # Quellvideo aufheben, damit "Momente-Editor" nach Analyse den Re-Render kann.
    # Erst beim Job-Cleanup loeschen.


def _backup_users_db():
    """v80x: Taeglicher Snapshot der users.db nach DATA/backups.
    14 Stueck rotierend. SQLite-Online-Backup-API - konsistent auch
    waehrend laufender Writes."""
    bdir = os.path.join(DATA, 'backups')
    os.makedirs(bdir, exist_ok=True)
    stamp = time.strftime('%Y%m%d')
    dest = os.path.join(bdir, f'users_{stamp}.db')
    if os.path.exists(dest):
        return                                   # heute schon gesichert
    try:
        src = sqlite3.connect(USERS_DB)
        dst = sqlite3.connect(dest)
        src.backup(dst)
        dst.close(); src.close()
        # Rotation: nur die 14 neuesten behalten
        snaps = sorted(f for f in os.listdir(bdir) if f.startswith('users_'))
        for old in snaps[:-14]:
            os.remove(os.path.join(bdir, old))
        print(f"DB-Backup: {dest}")
    except Exception as e:
        print(f"DB-Backup fehlgeschlagen: {type(e).__name__}: {e}")


def _cleanup_worker():
    """v80g: Alte Job-Verzeichnisse loeschen. Standard 7 Tage, ueber
    DVE_RETENTION_DAYS ueberschreibbar. Laeuft stuendlich.
    v80x: macht nebenbei den taeglichen users.db-Snapshot."""
    import time as _t
    retention = RETENTION_DAYS
    while True:
        _backup_users_db()
        try:
            cutoff = _t.time() - retention * 86400
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
            QUEUE.put(jid)
            requeued += 1
    if restored:
        print(f"Job-Restore: {restored} Jobs geladen, {requeued} neu eingereiht")


_restore_jobs()
threading.Thread(target=_cleanup_worker, daemon=True).start()

for _ in range(int(os.environ.get('DVE_WORKERS', '1'))):
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------- Endpunkte
def _page(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        raise HTTPException(404)
    # v83a: HTML nie cachen. Ohne Cache-Control cachen iOS/Safari heuristisch
    # tagelang - nach jedem Deploy lief bei Nutzern sonst das ALTE Frontend
    # gegen den neuen Server. no-cache = Browser fragt jedes Mal nach
    # (bekommt 200 mit frischem Inhalt), Assets/Videos bleiben unberuehrt.
    return HTMLResponse(open(p, encoding='utf-8').read(),
                        headers={'Cache-Control': 'no-cache, must-revalidate'})


# v80m: Rate-Limit gegen Spam-Registrierungen (in-memory, pro IP)
_REG_ATTEMPTS = {}       # ip -> [timestamps]


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
                 name: str = Form('')):
    """v80h: Neuer Account, 2 Min Willkommens-Guthaben."""
    # Rate-Limit gegen Spam
    ip = request.client.host if request.client else 'unknown'
    if not _rate_limit_ok(ip):
        raise HTTPException(429, 'Too many sign-up attempts. Please try again in an hour.')
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not _valid_email(email):
        raise HTTPException(400, 'Please enter a valid email address.')
    if not _valid_username(name):
        raise HTTPException(400, 'Please pick a username (3-24 characters, '
                                 'letters, numbers, spaces, . _ -).')
    if not _valid_pw(password):
        raise HTTPException(400, 'Password needs at least 8 characters.')
    uid, err = _create_user(email, password, name)
    if err:
        raise HTTPException(409, err)
    _send_verify_mail(uid, email, name.strip())        # v80x
    tok, exp = _create_session(uid)
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    u = _find_user_by_id(uid)
    return {'ok': True, 'email': u['email'], 'name': u['name'],
            'username': u['name'], 'credits': credits_of(u['balance_sec']),
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified'])}


@app.post('/api/login')
def api_login(request: Request, response: Response, email: str = Form(...),
              password: str = Form(...)):
    """v80h: Login. Gleiche Fehlermeldung fuer 'nicht vorhanden' und 'Passwort
    falsch', damit man E-Mails nicht enumerieren kann."""
    # v92 SECURITY: Rate-Limit gegen Passwort-Brute-Force (20 Versuche / 15 min / IP)
    ip = request.client.host if request.client else 'unknown'
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
        raise HTTPException(401, 'Email or password is wrong.')
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
    con.close()
    lt = time.localtime()
    days_in_month = [31, 29 if lt.tm_year % 4 == 0 else 28, 31, 30, 31, 30,
                     31, 31, 30, 31, 30, 31][lt.tm_mon - 1]
    return {'ok': True, 'email': u['email'], 'name': u['name'],
            'username': u['name'], 'credits': credits_of(u['balance_sec']),
            'created_at': int(u['created_at']),
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified']),
            'renders': rc, 'purchased': _has_purchased(u['id']),
            'is_owner': str(u['email']).strip().lower() == OWNER_EMAIL,
            'free_reset_days': days_in_month - lt.tm_mday + 1}


@app.post('/api/forgot_password')
def api_forgot_password(request: Request, email: str = Form(...)):
    """v80w: Reset-Link per Mail. Antwort immer identisch - kein
    E-Mail-Enumeration. Rate-Limit teilt sich den Topf mit Registrierung."""
    ip = request.client.host if request.client else 'unknown'
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
    return {'ok': True}


@app.post('/api/resend_verification')
def api_resend_verification(request: Request):
    u = _require_user(request)
    if u['verified']:
        return {'ok': True, 'msg': 'Already verified.'}
    ok = _send_verify_mail(u['id'], u['email'], u['name'] or '')
    if not ok:
        raise HTTPException(500, 'Could not send the email. Try again later.')
    return {'ok': True, 'msg': 'Verification email sent.'}


@app.post('/api/change_password')
def api_change_password(request: Request, old: str = Form(...),
                        new: str = Form(...)):
    """v80m: Passwort im eingeloggten Zustand aendern."""
    u = _require_user(request)
    if not _verify_pw(old, u['pw_hash']):
        raise HTTPException(401, 'Current password is wrong.')
    if not _valid_pw(new):
        raise HTTPException(400, 'New password needs at least 8 characters.')
    con = _db()
    con.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
                (_hash_pw(new), u['id']))
    con.commit()
    con.close()
    return {'ok': True}


@app.post('/api/delete_account')
def api_delete_account(request: Request, response: Response,
                       password: str = Form(...)):
    """v80m: DSGVO - Nutzer kann sein Konto komplett loeschen.
    Passwort-Bestaetigung noetig. Alle Sessions, Ledger-Eintraege,
    Templates werden ebenfalls entfernt."""
    u = _require_user(request)
    if not _verify_pw(password, u['pw_hash']):
        raise HTTPException(401, 'Password is wrong.')
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
    con = _db()
    con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM ledger WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM resets WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM verify_tokens WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM users WHERE id = ?", (uid,))
    con.commit()
    con.close()
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


def _asset(name, media):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p, media_type=media,
                        headers={'Cache-Control': 'public, max-age=86400'})


@app.get('/favicon.ico')
@app.get('/favicon.png')
def favicon():
    return _asset('favicon.png', 'image/png')


@app.get('/logo_white.png')
def logo_white():
    return _asset('logo_white.png', 'image/png')


@app.get('/logo_dark.png')
def logo_dark():
    return _asset('logo_dark.png', 'image/png')


@app.get('/', response_class=HTMLResponse)
def landing():
    return _page('landing.html')


@app.get('/app', response_class=HTMLResponse)
def index():
    return _page('index.html')


@app.get('/imprint', response_class=HTMLResponse)
def imprint():
    return _page('imprint.html')


@app.get('/privacy', response_class=HTMLResponse)
def privacy():
    return _page('privacy.html')


@app.get('/terms', response_class=HTMLResponse)
def terms():
    return _page('terms.html')


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
def pruefe(code: str = Form(...)):
    ok, msg = check_code(code)
    if not ok:
        return JSONResponse({'ok': False, 'msg': msg}, status_code=403)
    c = load_codes()[code.strip()]
    rest = (c['limit'] - c.get('genutzt', 0)) if c.get('limit') else None
    return {'ok': True, 'name': c.get('name', ''), 'rest': rest}


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


@app.post('/api/upload')
async def upload(request: Request, datei: UploadFile = File(...),
                 look: str = Form('creator'), code: str = Form(''),
                 mode: str = Form('full'), cfg_overrides: str = Form('{}')):
    if mode == 'demo':
        ip = request.client.host if request.client else 'unknown'
        if not _demo_ok(ip):
            raise HTTPException(429, 'Demo limit reached for today. '
                                     'Create a free account to keep going.')
    else:
        ok, msg = check_auth(code, request)
        if not ok:
            raise HTTPException(403, msg)
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

    try:
        dur = float(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', src],
            capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        dur = 0
    if dur > MAX_SECONDS:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(413, f'Video too long ({dur:.0f}s). '
                                 f'Maximum {MAX_SECONDS} seconds.')

    # v80i: Pre-Check auf Guthaben. Ohne Balance kein Render.
    # v89: Demo kostet nichts und braucht keinen Account.
    u = _current_user(request) if mode != 'demo' else None
    uid = None
    if u:
        uid = u['id']
        need = cost_seconds(dur)
        # v95: Vorab-Transkription (mode 'pre') kostet NICHTS. Sie laeuft schon,
        # waehrend der User noch Presets einstellt - abgebucht wird erst beim
        # echten Render (/api/render_start reserviert dann atomar). Hier nur
        # pruefen, dass ueberhaupt genug Guthaben DA ist - sonst lohnt das
        # Prewarming nicht (der User koennte eh nicht rendern) und wir sparen
        # Ismets Whisper-Kosten.
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
        # v92: ATOMAR reservieren statt nur pruefen (schliesst den Race, in dem
        # gleichzeitige Uploads mehrfach denselben Credit ausgeben). Klappt es
        # nicht, ist zu wenig Guthaben da. Bei Render-Fehler wird erstattet.
        elif not _reserve_credits(uid, need, jid):
            shutil.rmtree(d, ignore_errors=True)
            have = credits_of(u['balance_sec'])
            fehlt = credits_of(need) - have
            raise HTTPException(
                402,
                f"Not enough credits (video costs {credits_of(need)} "
                f"credit{'s' if credits_of(need) != 1 else ''}, you have "
                f"{have}). Missing {max(1, fehlt)} - please top up.")

    JOBS[jid] = {'id': jid, 'input': src, 'look': look, 'code': code.strip(),
                 'user_id': uid, 'vhash': _video_hash(src),   # v88b: Transkript-Cache
                 'mode': mode, 'cfg_overrides': overrides,
                 'status': 'wartet', 'progress': 0.0,
                 'phase': 'Queued …',
                 'dauer': round(dur, 1), 'name': _safe_name(datei.filename)}
    set_state(jid, **{k: v for k, v in JOBS[jid].items()
                      if k not in ('input', 'code')})
    QUEUE.put(jid)
    return {'job': jid, 'position': QUEUE.qsize()}


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
    if u and mode == 'full':
        need = cost_seconds(j.get('dauer', 0))
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
            QUEUE.put(jid)
        return {'job': jid, 'chained': True}
    j['mode'] = mode
    set_state(jid, status='wartet', progress=0.0, phase='Queued …')
    QUEUE.put(jid)
    return {'job': jid, 'position': QUEUE.qsize()}


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
        out['phase'] = f'Queued (position {QUEUE.qsize()}) …'
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
        return FileResponse(p, media_type='video/mp4',
                            filename='DouchkoVE_Captions.mp4')
    return FileResponse(p, media_type='video/mp4')


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
    return FileResponse(poster_path, media_type='image/jpeg')


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
        if j.get('status') != 'fertig':
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
        raise HTTPException(404, 'Transcript not ready yet.')
    return {'words': json.load(open(tp, encoding='utf-8'))}


@app.post('/api/transcript/{jid}')
async def save_transcript(request: Request, jid: str,
                          edits: str = Form(...), code: str = Form('')):
    """v80y: Wort-Korrekturen speichern (nur Text, Timings bleiben),
    Regie-/Momente-Cache invalidieren, Analyse neu starten."""
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
    # Caches weg - Regie + Momente basieren auf altem Text
    for suffix in ('_regie3.json', '_momente.json'):
        try:
            os.remove(base + suffix)
        except OSError:
            pass
    j['mode'] = 'analyze'
    j['status'] = 'wartet'
    j['progress'] = 0.0
    j['phase'] = 'Queued (re-analyzing with corrected transcript) …'
    set_state(jid, **{k: v for k, v in j.items() if k not in ('input', 'code')})
    QUEUE.put(jid)
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
    return FileResponse(thumb_path,
                        media_type='image/png' if name.endswith('.png') else 'image/jpeg')


CORRECTIONS_PATH = os.path.join(DATA, 'corrections.json')

def _load_corrections():
    try:
        d = json.load(open(CORRECTIONS_PATH, encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []

def _capture_corrections(old_mom_path, edited):
    """Vergleicht die neuen (editierten) Momente mit dem vorherigen Stand und
    speichert JEDE Aenderung (Effekt getauscht, Animation weg/gesetzt, Moment
    deaktiviert) global. Beim naechsten Render zieht die KI-Wahl automatisch
    dorthin nach (Phase 2 'aus Fehlern lernen', global)."""
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
        if str(m.get('anim', '')) != str(o.get('anim', '')):
            rec['user_anim'] = str(m.get('anim', ''))
        if bool(m.get('aktiv', True)) != bool(o.get('aktiv', True)):
            rec['user_aktiv'] = bool(m.get('aktiv', True))
        if rec:
            rec['phrase'] = phrase
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
                          moments: str = Form(...), code: str = Form('')):
    """Momente speichern und Voll-Render starten."""
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    if not _job_owner_ok(jid, request):
        raise HTTPException(403, 'This job belongs to another account.')
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    try:
        mom = json.loads(moments)
    except Exception:
        raise HTTPException(400, 'Moments JSON invalid.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
    # v92 Phase 2: aus dem Edit lernen. Diff gegen die VORHERIGE Momente-Datei
    # (KI-Original bzw. letzter Stand) - was der Nutzer aendert, wird global
    # gespeichert und beim naechsten Render automatisch beruecksichtigt.
    try:
        _capture_corrections(mom_path, mom)
    except Exception as e:
        print(f"Korrektur-Erfassung uebersprungen ({type(e).__name__})")
    json.dump(mom, open(mom_path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    # Voll-Render mit den neuen Momenten
    j['mode'] = 'full'
    j['status'] = 'wartet'
    j['progress'] = 0.0
    j['phase'] = 'Queued (re-render) …'
    set_state(jid, **{k: v for k, v in j.items()
                      if k not in ('input', 'code')})
    QUEUE.put(jid)
    return {'ok': True, 'job': jid, 'position': QUEUE.qsize()}


def _admin_ok(request: Request):
    key = os.environ.get('DVE_ADMIN', '').strip()
    given = request.headers.get('x-admin-key', '')
    return bool(key) and hmac.compare_digest(given, key)


def _owner_ok(request: Request):
    """v96p: Nur das Besitzer-Konto (OWNER_EMAIL) darf die Stil-Referenzen
    sehen/aendern - sie wirken global auf alle Renders. Ueber die Session, kein
    Extra-Key noetig."""
    u = _current_user(request)
    return bool(u) and str(u.get('email', '')).strip().lower() == OWNER_EMAIL


def _reference_file():
    # regie_reference.json liegt im Projekt-Root neben render.py
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'regie_reference.json')


def _load_references():
    try:
        d = json.load(open(_reference_file(), encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []


@app.get('/api/reference/list')
def reference_list(request: Request):
    """v96o: gelernte Stil-Referenzen (Admin). Global - beeinflusst ALLE Renders."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    return {'refs': _load_references()}


@app.post('/api/reference/learn')
async def reference_learn(request: Request, datei: UploadFile = File(...),
                          name: str = Form('')):
    """v96o: Referenz-Video hochladen -> GPT-4o-Vision beschreibt den Stil ->
    als Stil-Referenz speichern. Nur Besitzer-Konto, da global wirksam."""
    if not _owner_ok(request):
        raise HTTPException(403, 'Access denied.')
    ext = os.path.splitext(datei.filename or '')[1].lower() or '.mp4'
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv'):
        raise HTTPException(400, 'Only video files (mp4, mov, webm, mkv).')
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
                f.close(); os.remove(tmp)
                raise HTTPException(413, 'Reference video too large (max 200 MB).')
            f.write(chunk)
    try:
        import render as _R
        entry = _R.analyze_reference_video(
            tmp, name=(_safe_name(name) or _safe_name(datei.filename or 'Referenz')))
    except Exception as e:
        entry = None
        print(f'reference_learn Fehler: {type(e).__name__}: {e}')
    finally:
        try: os.remove(tmp)
        except OSError: pass
    if not entry:
        raise HTTPException(502, 'Could not analyze the video '
                                 '(AI key missing or analysis failed).')
    return {'entry': entry, 'refs': _load_references()}


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


@app.get('/admin/codes')
def admin_codes(request: Request):
    """v92-sec: Admin-Schluessel jetzt (1) ohne erratbaren Default 'admin'
    (fehlt DVE_ADMIN -> Endpoint tot), (2) per Header X-Admin-Key statt
    Query-Parameter (landet sonst in Access-Logs/History/Referer),
    (3) timing-safe verglichen."""
    key = os.environ.get('DVE_ADMIN', '').strip()
    given = request.headers.get('x-admin-key', '')
    if not key or not hmac.compare_digest(given, key):
        raise HTTPException(403, 'Access denied.')
    return load_codes()
