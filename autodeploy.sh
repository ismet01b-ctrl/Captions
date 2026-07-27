#!/usr/bin/env bash
# DouchkoVE Pull-Auto-Deploy (wird vom systemd-Timer alle 2 Min aufgerufen).
# Holt den aktuellen Branch und deployt NUR, wenn es wirklich neue Commits
# gibt. Kein Secret noetig - der Server zieht selbst. Der flock im Timer
# verhindert, dass ein langer Build (5-15 min) doppelt startet.
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/douchko}"
cd "$INSTALL_DIR"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch --quiet origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0                       # nichts Neues - fertig
fi

echo "$(date -Is) Neue Version ${REMOTE:0:8} auf $BRANCH -> deploye"

# v197: Bricht update.sh am Test-Gate ab, laeuft die ALTE Version weiter -
# richtig so. Nur hat das bisher niemand erfahren: git steht danach schon auf
# dem neuen Commit, der naechste Timer-Lauf sieht "nichts Neues" und schweigt.
# Ein stiller Fehlschlag ist schlimmer als ein lauter. Die Meldung geht in die
# alerts-Tabelle des LAUFENDEN Containers und steht damit im Admin-Panel.
if bash update.sh; then
  exit 0
fi
echo "$(date -Is) DEPLOY FEHLGESCHLAGEN (${REMOTE:0:8})"
docker compose exec -T app python - "$REMOTE" <<'PY' || true
import os, sqlite3, sys, time
DATA = os.environ.get('DVE_DATA', '/app/web/data')
con = sqlite3.connect(os.path.join(DATA, 'users.db'), timeout=10)
con.execute("INSERT INTO alerts (schluessel,betreff,text,gemailt,gelesen,"
            "created_at) VALUES (?,?,?,0,0,?)",
            ('deploy', 'Deploy abgebrochen',
             f'Commit {sys.argv[1][:8]} ging NICHT live - update.sh ist '
             f'gescheitert (meist rotes Test-Gate). Die laufende Version ist '
             f'unveraendert. Details auf dem Server:\n'
             f'  journalctl -u douchko-deploy -n 100', int(time.time())))
con.commit(); con.close()
print('Deploy-Fehler im Panel vermerkt')
PY
exit 1
