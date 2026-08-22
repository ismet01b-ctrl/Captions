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

# v230j DER DEPLOY MELDET, DASS ER LAEUFT - UND MISST SICH SELBST.
# Bis v230i zeigte das Panel nur den LAUFENDEN Stand. Damit liess sich
# "dauert noch" nicht von "haengt" unterscheiden: Ismet sah v230h, waehrend
# v230i vier Minuten alt und noch im Bau war - fuer ihn sah es aus, als
# wuerden Builds gar nicht uebernommen. Jede Runde schreibt jetzt Beginn,
# Ende und DAUER in die Datenbank des laufenden Containers; das Panel zeigt
# damit eine echte Zahl vom eigenen Server statt einer Schaetzung.
# v230d4: die Funktion steht VOR der Ruhe-Weiche, weil auch der Ruhe-Fall
# melden muss (Lebendpuls). Sie stand darunter und war dort unerreichbar.
START_TS="$(date +%s)"
dstate() {                       # $1 phase  $2 commit  $3 dauer  $4 grund
  docker compose exec -T app python - "$1" "$2" "$3" "${4:-}" "$START_TS" \
    <<'DSTATE_PY' >/dev/null 2>&1 || true
import os, sqlite3, sys, time
phase, commit, dauer, grund, start = (sys.argv[1:6] + [''] * 5)[:5]
con = sqlite3.connect(os.path.join(os.environ.get('DVE_DATA', '/app/web/data'),
                                   'users.db'), timeout=10)
con.execute("CREATE TABLE IF NOT EXISTS deploy_state ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), "
            "phase TEXT NOT NULL DEFAULT '', "
            "commit_kurz TEXT NOT NULL DEFAULT '', "
            "started_at INTEGER NOT NULL DEFAULT 0, "
            "finished_at INTEGER NOT NULL DEFAULT 0, "
            "dauer_s INTEGER NOT NULL DEFAULT 0, "
            "grund TEXT NOT NULL DEFAULT '')")
con.execute("INSERT INTO deploy_state (id, phase, commit_kurz, started_at, "
            "finished_at, dauer_s, grund) VALUES (1,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET phase=excluded.phase, "
            "commit_kurz=excluded.commit_kurz, "
            "started_at=excluded.started_at, "
            "finished_at=excluded.finished_at, dauer_s=excluded.dauer_s, "
            "grund=excluded.grund",
            (phase, commit[:12], int(start or 0),
             0 if phase == 'baut' else int(time.time()),
             int(dauer or 0), grund[:400]))
con.commit(); con.close()
DSTATE_PY
}

if [ "$LOCAL" = "$REMOTE" ]; then
  # v230d4 DER LEBENDPULS. Bis v230d3 endete der Ruhe-Fall hier lautlos, und
  # damit war "es gibt nichts Neues" von "der Timer steht" nicht zu
  # unterscheiden. Der Wachhund hat deshalb ersatzweise das ALTER des
  # laufenden Stands gemeldet - und mailte taeglich einen Stillstand, obwohl
  # nur niemand gepusht hatte (Ismets Befund: 8 Tage lang zugespammt).
  # Ein Alarm, der bei normalem Betrieb feuert, ist nach zwei Mails Tapete
  # (v225c-Lehre, zweite Runde). Also meldet der Deploy selbst, dass er
  # nachgesehen hat; das Alter allein ist kein Befund mehr.
  # Hoechstens alle 30 Minuten, sonst 720 docker-exec am Tag fuer nichts.
  BEAT="$INSTALL_DIR/.deploy_beat"
  if [ ! -f "$BEAT" ] || [ $(( $(date +%s) - $(stat -c %Y "$BEAT" 2>/dev/null || echo 0) )) -ge 1800 ]; then
    dstate ruhe "$LOCAL" 0 "nichts Neues"
    touch "$BEAT"
  fi
  exit 0                       # nichts Neues - fertig
fi

echo "$(date -Is) Neue Version ${REMOTE:0:8} auf $BRANCH -> deploye"

START_TS="$(date +%s)"       # Bauzeit ab HIER messen, nicht ab Skriptstart
dstate baut "$REMOTE" 0 ""

# v197: Bricht update.sh am Test-Gate ab, laeuft die ALTE Version weiter -
# richtig so. Nur hat das bisher niemand erfahren: git steht danach schon auf
# dem neuen Commit, der naechste Timer-Lauf sieht "nichts Neues" und schweigt.
# Ein stiller Fehlschlag ist schlimmer als ein lauter. Die Meldung geht in die
# alerts-Tabelle des LAUFENDEN Containers und steht damit im Admin-Panel.
if bash update.sh; then
  DAUER=$(( $(date +%s) - START_TS ))
  dstate ok "$REMOTE" "$DAUER" ""
  echo "$(date -Is) Deploy fertig in ${DAUER}s (${REMOTE:0:8})"
  exit 0
fi
DAUER=$(( $(date +%s) - START_TS ))
echo "$(date -Is) DEPLOY FEHLGESCHLAGEN (${REMOTE:0:8}) nach ${DAUER}s"
# v201a: WELCHE Tests gefallen sind, gehoert in die Meldung. Bis dahin stand
# im Panel nur "Deploy abgebrochen" und der Rest in journalctl - fuer jemanden,
# der nie ins Terminal geht, ist das dasselbe wie keine Meldung.
BEFUND="$(cat .deploy_gate_last.txt 2>/dev/null | head -25)"
dstate fehler "$REMOTE" "$DAUER" "$BEFUND"
docker compose exec -T app python - "$REMOTE" "$BEFUND" <<'PY' || true
import os, sqlite3, sys, time
DATA = os.environ.get('DVE_DATA', '/app/web/data')
befund = (sys.argv[2] if len(sys.argv) > 2 else '').strip()
con = sqlite3.connect(os.path.join(DATA, 'users.db'), timeout=10)
con.execute("INSERT INTO alerts (schluessel,betreff,text,gemailt,gelesen,"
            "created_at) VALUES (?,?,?,0,0,?)",
            ('deploy', 'Deploy abgebrochen',
             f'Commit {sys.argv[1][:8]} ging NICHT live - update.sh ist '
             f'gescheitert. Die laufende Version ist unveraendert.\n\n'
             + (f'Befund des Test-Gates:\n{befund}\n\n' if befund else '')
             + 'Mehr auf dem Server: journalctl -u douchko-deploy -n 120',
             int(time.time())))
con.commit(); con.close()
print('Deploy-Fehler im Panel vermerkt')
PY
exit 1
