#!/usr/bin/env bash
# v197 WIEDERHERSTELLUNG der users.db.
#
#   bash restore.sh <backup-datei>
#   bash restore.sh --letztes
#
# Die Sicherung lief seit v80x taeglich (DATA/backups + Offsite per Mail),
# aber niemand hatte je geprueft, ob daraus wieder ein laufender Server wird.
# Ein Backup, das man nie zurueckgespielt hat, ist kein Backup.
#
# Sicherheitsnetz in dieser Reihenfolge:
#   1. Kandidat PRUEFEN, bevor irgendetwas angefasst wird (integrity_check +
#      Pflichttabellen). Eine kaputte Sicherung darf nie eine funktionierende
#      Datenbank ueberschreiben.
#   2. App stoppen - SQLite waehrend eines Writes zu tauschen zerlegt die WAL.
#   3. Den JETZIGEN Stand zur Seite legen. Auch ein Restore kann die falsche
#      Entscheidung sein; ohne diese Kopie waere sie unumkehrbar.
#   4. Einspielen, App starten, Health pruefen.
set -euo pipefail
cd "$(dirname "$0")"
DATA_DIR="${DVE_DATA:-./web/data}"
DB="$DATA_DIR/users.db"
BDIR="$DATA_DIR/backups"

if [ $# -lt 1 ]; then
  echo "Aufruf: bash restore.sh <backup-datei>   |   bash restore.sh --letztes"
  echo ""
  echo "Vorhandene Sicherungen in $BDIR:"
  ls -lh "$BDIR" 2>/dev/null | tail -n +2 || echo "  (keine)"
  exit 1
fi

if [ "$1" = "--letztes" ]; then
  SRC="$(ls -1t "$BDIR"/users_*.db 2>/dev/null | head -1 || true)"
  [ -n "$SRC" ] || { echo "✗ Keine Sicherung in $BDIR gefunden."; exit 1; }
else
  SRC="$1"
fi
[ -f "$SRC" ] || { echo "✗ Datei nicht gefunden: $SRC"; exit 1; }

echo "==> [1/5] Sicherung pruefen: $SRC"
python3 - "$SRC" <<'PY'
import sqlite3, sys
q = sys.argv[1]
con = sqlite3.connect(q)
ok = con.execute("PRAGMA integrity_check").fetchone()[0]
if ok != 'ok':
    sys.exit(f"✗ Datei ist beschaedigt: {ok}")
da = {r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
brauchen = {'users', 'sessions', 'ledger', 'purchases'}
fehlt = brauchen - da
if fehlt:
    sys.exit(f"✗ Pflichttabellen fehlen: {sorted(fehlt)}")
n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
g = con.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
print(f"  ok - {n} Konten, {g} Kaeufe, {len(da)} Tabellen")
con.close()
PY

echo "==> [2/5] App stoppen"
docker compose stop app 2>/dev/null || echo "  (lief nicht - weiter)"

echo "==> [3/5] Jetzigen Stand zur Seite legen"
mkdir -p "$BDIR"
if [ -f "$DB" ]; then
  VOR="$BDIR/vor_restore_$(date +%Y%m%d_%H%M%S).db"
  cp "$DB" "$VOR"
  # WAL und SHM muessen mit weg, sonst mischt SQLite alt und neu.
  rm -f "$DB-wal" "$DB-shm"
  echo "  gesichert nach $VOR"
  # Rotation: die 5 neuesten Sicherheitskopien reichen. Sie fallen nicht
  # unter die Tages-Rotation der Snapshots (anderer Dateiname).
  ls -1t "$BDIR"/vor_restore_*.db 2>/dev/null | tail -n +6 | while read -r alt; do
    rm -f "$alt"
  done
else
  echo "  (keine bestehende Datenbank)"
fi

echo "==> [4/5] Einspielen"
mkdir -p "$DATA_DIR"
cp "$SRC" "$DB"
echo "  $SRC -> $DB"

echo "==> [5/5] App starten und pruefen"
docker compose up -d app
for i in $(seq 1 30); do
  if docker compose exec -T app python -c \
     "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health',timeout=2)" 2>/dev/null; then
    echo ""
    echo "=========================================="
    echo "  ✓ WIEDERHERSTELLUNG OK - App antwortet"
    echo "=========================================="
    exit 0
  fi
  sleep 1
done
echo ""
echo "=========================================="
echo "  ✗ App antwortet nicht. Zurueck geht es mit:"
echo "     bash restore.sh $BDIR/vor_restore_*.db"
echo "=========================================="
docker compose logs app --tail 30
exit 1
