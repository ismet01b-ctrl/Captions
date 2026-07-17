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
JOBS_DIR = os.path.join(DATA, 'jobs')
CODES_FILE = os.path.join(DATA, 'codes.json')
USERS_DB = os.path.join(DATA, 'users.db')
MAX_MB = int(os.environ.get('DVE_MAX_MB', '300'))
MAX_SECONDS = int(os.environ.get('DVE_MAX_SECONDS', '180'))
SESSION_DAYS = 30
TRIAL_SECONDS = int(os.environ.get('DVE_TRIAL_SECONDS', '120'))  # 2 Min gratis

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(DATA, exist_ok=True)


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


EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def _valid_email(s):
    return bool(s) and len(s) <= 254 and EMAIL_RE.match(s)


def _valid_pw(s):
    return bool(s) and 8 <= len(s) <= 200


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
    """SMTP-Versand (Gmail App-Passwort o.ae.). Wirft bei Fehler."""
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
    with smtplib.SMTP(host, port, timeout=20) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(sender, [to], msg.as_string())


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
    try:
        _send_mail(email, 'Verify your DouchkoVE email',
                   f'Hi{" " + name if name else ""},\n\n'
                   f'welcome to DouchkoVE! Please confirm your email address '
                   f'(needed before purchasing credits):\n\n'
                   f'{base}/app?verify={tok}\n\n'
                   f'Link is valid for 48 hours.\n\n- DouchkoVE')
        return True
    except Exception as e:
        print(f'Verify-Mail fehlgeschlagen: {type(e).__name__}: {e}')
        return False


def _consume_verify(token):
    if not token:
        return None
    con = _db()
    row = con.execute(
        "SELECT user_id FROM verify_tokens WHERE token = ? AND used = 0 "
        "AND expires_at > ?", (token, int(time.time()))).fetchone()
    if row:
        con.execute("UPDATE verify_tokens SET used = 1 WHERE token = ?", (token,))
        con.execute("UPDATE users SET verified = 1 WHERE id = ?",
                    (row['user_id'],))
        con.commit()
    con.close()
    return row['user_id'] if row else None


def _consume_reset(token):
    """Token pruefen + als benutzt markieren. Gibt user_id oder None."""
    if not token:
        return None
    con = _db()
    row = con.execute(
        "SELECT user_id FROM resets WHERE token = ? AND used = 0 "
        "AND expires_at > ?", (token, int(time.time()))).fetchone()
    if row:
        con.execute("UPDATE resets SET used = 1 WHERE token = ?", (token,))
        con.commit()
    con.close()
    return row['user_id'] if row else None


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
PACKS = {
    'starter': {
        'name': 'Starter',
        'preis_cent': 900,
        'minuten': 20,
        'sekunden': 20 * 60,
        'beschreibung_en': 'Test the waters. Enough for 6-8 short reels or 3-4 mid-length videos.',
        'hinweis_en': 'Credits valid for 6 months',
        'features_en': ['20 minutes of finished video', 'All effects & animations',
                        'Full moments editor access', 'Credits valid 6 months'],
    },
    'creator': {
        'name': 'Creator',
        'preis_cent': 1900,
        'minuten': 60,
        'sekunden': 60 * 60,
        'beschreibung_en': 'Weekly posting schedule. Cheapest per-minute price under €0.35.',
        'hinweis_en': 'Save 30% vs Starter · Most popular',
        'empfohlen': True,
        'features_en': ['60 minutes of finished video', '30% cheaper per minute',
                        'Priority queue in busy hours', 'Credits valid 6 months'],
    },
    'pro': {
        'name': 'Pro',
        'preis_cent': 3900,
        'minuten': 150,
        'sekunden': 150 * 60,
        'beschreibung_en': 'Daily creator or small agency. Lowest cost per minute we offer.',
        'hinweis_en': 'Save 42% vs Starter · Best value',
        'bester_wert': True,
        'features_en': ['150 minutes of finished video', '42% cheaper per minute',
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


def _pack_processed(user_id, session_id):
    """Idempotenz-Check: wurde diese Stripe-Session bereits gutgeschrieben?"""
    con = _db()
    row = con.execute(
        "SELECT id FROM ledger WHERE user_id = ? AND grund = ?",
        (user_id, f'Kauf {session_id}')).fetchone()
    con.close()
    return row is not None


app = FastAPI(title='DouchkoVE')


@app.get('/api/pricing')
def api_pricing():
    return {'packs': PACKS,
            'trial_sec': TRIAL_SECONDS,
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
    # v80l: Signatur separat verifizieren, dann mit Roh-JSON weiterarbeiten -
    # spart Aerger mit StripeObject vs dict.
    try:
        if secret:
            st.Webhook.construct_event(payload, sig, secret)  # nur Signatur-Check
        event = json.loads(payload)
    except Exception as e:
        raise HTTPException(400, f'Webhook invalid: {type(e).__name__}')
    ev_type = event.get('type')
    if ev_type != 'checkout.session.completed':
        return {'ok': True, 'ignored': ev_type}
    sess = event.get('data', {}).get('object', {})
    meta = sess.get('metadata') or {}
    try:
        uid = int(meta.get('user_id'))
        sec = int(meta.get('sekunden'))
        pack = meta.get('pack', '?')
        sess_id = sess.get('id', '')
    except Exception:
        raise HTTPException(400, 'Metadata incomplete.')
    if _pack_processed(uid, sess_id):
        return {'ok': True, 'idempotent': True}
    _adjust_balance(uid, sec, f'Kauf {sess_id}')
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
                'bg_blur': 0.60, 'freeze_frame': 0.50, 'trail': 0.45,
                'counter_ring': 0.55, 'split_screen': 0.30, 'env_shadow': 0.15,
                'emerge': 'immer', 'anim': True,
                'keyword_rotation': ['behind', 'outline', 'ground'],
                'sfx_volume': 0.55, 'sfx': True,
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
                'sfx_volume': 0.40, 'sfx': True,
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
                'sfx_volume': 0.30, 'sfx': True,
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
                'sfx_volume': 0.28, 'sfx': True,
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
    set_state(jid, status='laeuft', phase='Transcribing …',
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
            phase = 'Deine Stimme wird verschriftet …'
            progress = 0.05
        elif 'Woerter' in ln and 'Transkript' in ln:
            phase = 'Jeder Wort-Zeitpunkt wird feinjustiert …'
            progress = 0.10
        elif 'Gesichts-Tracking' in ln:
            phase = 'Dein Gesicht wird verfolgt, Szenen werden getrennt …'
            progress = 0.20
        elif 'Musik-Beat' in ln:
            phase = 'Der Musik-Beat wird analysiert …'
            progress = 0.28
        elif 'KI-Regie' in ln and 'analysiert' in ln:
            phase = 'Die KI liest dein Transkript und plant die Regie …'
            progress = 0.35
        elif 'Vision-Regie' in ln:
            phase = 'Die KI schaut sich einzelne Frames an …'
            progress = 0.38
        elif ln.startswith('Keywords'):
            phase = 'Die grossen Momente stehen fest …'
            progress = 0.40
        elif 'Adaptive Farben' in ln:
            phase = 'Die Caption-Farben werden aus der Szene abgeleitet …'
            progress = 0.43
        elif 'Kompositionen' in ln:
            phase = 'Wortgruppen werden zu Magazin-Layouts komponiert …'
            progress = 0.45
        elif 'Matting-Fenster' in ln:
            phase = 'Deine Person wird sauber vom Hintergrund freigestellt …'
            progress = 0.47
        elif 'Tiefen-Okklusion' in ln:
            phase = 'Objekte vor dir werden erkannt (die verdecken den Text) …'
            progress = 0.49
        elif 'Kamera-Track' in ln:
            phase = 'Kamera-Bewegung wird nachverfolgt …'
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
                    phase = f'Das Video wird gebaut · Sekunde {sec_at:.0f} · Text hinter dir wird gerendert'
                elif frac < 0.75:
                    phase = f'Das Video wird gebaut · Sekunde {sec_at:.0f} · Animationen laufen'
                elif frac < 0.85:
                    phase = f'Das Video wird gebaut · Sekunde {sec_at:.0f} · Kamera-Fahrten werden ueberlagert'
                else:
                    phase = f'Das Video wird gebaut · Sekunde {sec_at:.0f} · Feinschliff und Farb-Korrektur'
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
            phase = 'Fertiges Video wird encodiert und gespeichert …'
            progress = 0.97

        if phase is not None or progress is not None or tail:
            kw = {'log_tail': tail}
            if phase is not None: kw['phase'] = phase
            if progress is not None: kw['progress'] = progress
            if eta is not None: kw['eta_sec'] = eta
            set_state(jid, **kw)
    p.wait()
    open(os.path.join(d, 'log.txt'), 'a', encoding='utf-8').write('\n'.join(log) + '\n')
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
        return

    _extra = []
    _uid = j.get('user_id')
    if _uid and not _has_purchased(_uid):
        _extra = ['--watermark']
    rc, log, out = _run_render(jid, extra_args=_extra)
    log_txt = '\n'.join(log)
    # v80g: Menschliche Fehlermeldungen aus dem Render-Log herausklauben
    if 'OPENAI_API_KEY ist nicht gesetzt' in log_txt:
        set_state(jid, status='fehler', progress=0,
                  msg='Server is not fully configured '
                      '(AI key missing). Please contact support.')
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
            return
    if rc == 0 and os.path.exists(out):
        count_use(j['code'])
        # v80i: Video-Sekunden vom User-Guthaben abziehen (falls User-Account)
        # v80s: nur EINMAL pro Job - Re-Render nach Momente-Edit ist inklusive
        # (Konkurrenz-Standard, sonst zahlt man jede Korrektur doppelt).
        uid = j.get('user_id')
        if uid and not _render_charged(uid, jid):
            verbrauch = max(1, int(round(j.get('dauer', 0))))
            _adjust_balance(uid, -verbrauch,
                            f'Render {jid} ({verbrauch}s)')
        set_state(jid, status='fertig', progress=1.0, phase='Done',
                  out='fertig.mp4')
    else:
        letzte = [x for x in log[-15:] if x.strip()]
        set_state(jid, status='fehler', progress=0,
                  msg='Render failed.',
                  detail='\n'.join(letzte))
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
    retention = float(os.environ.get('DVE_RETENTION_DAYS', '7'))
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
    return open(p, encoding='utf-8').read()


# v80m: Rate-Limit gegen Spam-Registrierungen (in-memory, pro IP)
_REG_ATTEMPTS = {}       # ip -> [timestamps]


def _rate_limit_ok(ip, window_sec=3600, max_attempts=5):
    """Max 5 Registrierungen pro Stunde pro IP. Reicht fuer echte Nutzer,
    stoppt automatisierten Spam."""
    now = time.time()
    xs = [t for t in _REG_ATTEMPTS.get(ip, []) if now - t < window_sec]
    xs.append(now)
    _REG_ATTEMPTS[ip] = xs[-max_attempts:]
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
    if not _valid_email(email):
        raise HTTPException(400, 'Please enter a valid email address.')
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
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified'])}


@app.post('/api/login')
def api_login(response: Response, email: str = Form(...),
              password: str = Form(...)):
    """v80h: Login. Gleiche Fehlermeldung fuer 'nicht vorhanden' und 'Passwort
    falsch', damit man E-Mails nicht enumerieren kann."""
    email = (email or '').strip().lower()
    row = _find_user_by_email(email)
    if not row or not _verify_pw(password, row['pw_hash']):
        raise HTTPException(401, 'Email or password is wrong.')
    tok, exp = _create_session(row['id'])
    response.set_cookie('dve_session', tok, httponly=True, samesite='lax',
                        secure=True, max_age=SESSION_DAYS * 86400, path='/')
    return {'ok': True, 'email': row['email'], 'name': row['name'],
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
            'balance_sec': u['balance_sec'], 'verified': bool(u['verified']),
            'renders': rc, 'purchased': _has_purchased(u['id']),
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
    con = _db()
    con.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM ledger WHERE user_id = ?", (uid,))
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


@app.post('/api/upload')
async def upload(request: Request, datei: UploadFile = File(...),
                 look: str = Form('creator'), code: str = Form(''),
                 mode: str = Form('full'), cfg_overrides: str = Form('{}')):
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    if look not in LOOKS:
        look = 'creator'
    try:
        overrides = json.loads(cfg_overrides) if cfg_overrides else {}
    except Exception:
        overrides = {}
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
    u = _current_user(request)
    uid = None
    if u:
        uid = u['id']
        need = max(1, int(round(dur)))
        if u['balance_sec'] < need:
            shutil.rmtree(d, ignore_errors=True)
            fehlt = need - u['balance_sec']
            raise HTTPException(
                402,
                f"Not enough credit (video needs {need // 60}:"
                f"{need % 60:02d} min, you have {u['balance_sec'] // 60}:"
                f"{u['balance_sec'] % 60:02d} min). "
                f"Missing {fehlt // 60 + 1} min - please top up.")

    JOBS[jid] = {'id': jid, 'input': src, 'look': look, 'code': code.strip(),
                 'user_id': uid,
                 'mode': mode, 'cfg_overrides': overrides,
                 'status': 'wartet', 'progress': 0.0,
                 'phase': 'Queued …',
                 'dauer': round(dur, 1), 'name': datei.filename}
    set_state(jid, **{k: v for k, v in JOBS[jid].items()
                      if k not in ('input', 'code')})
    QUEUE.put(jid)
    return {'job': jid, 'position': QUEUE.qsize()}


@app.get('/api/status/{jid}')
def status(jid: str):
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


@app.get('/api/video/{jid}')
def video(jid: str):
    p = os.path.join(job_dir(jid), 'fertig.mp4')
    if not os.path.exists(p):
        raise HTTPException(404, 'Not ready yet.')
    return FileResponse(p, media_type='video/mp4',
                        filename='DouchkoVE_Captions.mp4')


@app.get('/api/moments/{jid}')
def get_moments(jid: str):
    """Momente-Datei aus der Analyse laden."""
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
def get_transcript(jid: str):
    """v80y: Transkript zum Korrigieren laden."""
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
def get_thumb(jid: str, name: str):
    """Video-Frame-Preview fuer einen Moment (v80e). Wird im Momente-Editor
    hinter der Text-Preview eingeblendet, damit man sieht was zu dem
    Zeitpunkt wirklich im Bild ist."""
    from fastapi.responses import FileResponse
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    if not name.endswith('.jpg') or '/' in name or '\\' in name or '..' in name:
        raise HTTPException(400, 'Invalid thumbnail name.')
    thumb_dir = os.path.splitext(j['input'])[0] + '_thumbs'
    thumb_path = os.path.join(thumb_dir, name)
    if not os.path.exists(thumb_path):
        raise HTTPException(404, 'Thumbnail not found.')
    return FileResponse(thumb_path, media_type='image/jpeg')


@app.post('/api/moments/{jid}')
async def save_and_render(request: Request, jid: str,
                          moments: str = Form(...), code: str = Form('')):
    """Momente speichern und Voll-Render starten."""
    ok, msg = check_auth(code, request)
    if not ok:
        raise HTTPException(403, msg)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    try:
        mom = json.loads(moments)
    except Exception:
        raise HTTPException(400, 'Moments JSON invalid.')
    base = os.path.splitext(j['input'])[0]
    mom_path = base + '_momente.json'
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


@app.get('/admin/codes')
def admin_codes(schluessel: str = ''):
    if schluessel != os.environ.get('DVE_ADMIN', 'admin'):
        raise HTTPException(403, 'Access denied.')
    return load_codes()
