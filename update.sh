#!/usr/bin/env bash
# DouchkoVE Deploy-Skript. Ein Befehl, macht immer alles richtig:
#   bash update.sh
# Zieht neuen Code, baut das Image (nur was sich geaendert hat),
# startet den Container neu und prueft ob die App wirklich antwortet.
set -e
cd "$(dirname "$0")"

echo "==> [0/5] System-Check"
df -h / | tail -1 | awk '{print "  Festplatte: " $4 " frei (" $5 " belegt)"}'
free -h | awk '/^Mem:/{print "  RAM: " $7 " verfuegbar"}'

echo "==> [1/5] Code aktualisieren"
git pull

echo "==> [2/5] Image bauen (Code-Layer wird immer neu kopiert)"
docker compose build app

echo "==> [3/5] Test-Gate (die Tests laufen im NEUEN Image)"
# v197: Erst pruefen, DANN umschalten. Faellt der Selftest durch, bleibt die
# laufende Version unangetastet - ein kaputter Renderer darf nie live gehen,
# der Kunde zahlt sonst einen Credit fuer ein kaputtes Video.
# v201: Das Gate unterscheidet jetzt zwei Faelle. Rot = Code kaputt, Abbruch.
# Nicht lauffaehig = die PRUEFVORRICHTUNG ist kaputt; darueber ist nichts
# ueber den Code gesagt, und ein Waechter, der bei eigenem Ausfall die Tuer
# zumauert, friert den ganzen Betrieb ein. Dann wird deployt, aber laut.
set +e
bash deploy_gate.sh
GATE_RC=$?
set -e
if [ "$GATE_RC" -eq 1 ]; then
  echo ""
  echo "=========================================="
  echo "  ✗ DEPLOY ABGEBROCHEN - Selftest rot."
  echo "    Die laufende Version bleibt unveraendert."
  echo "=========================================="
  exit 1
elif [ "$GATE_RC" -ne 0 ]; then
  echo ""
  echo "=========================================="
  echo "  ! Test-Gate nicht lauffaehig - Deploy laeuft TROTZDEM."
  echo "    Der Code ist damit UNGEPRUEFT live gegangen."
  echo "=========================================="
  GATE_DEFEKT=1
fi

echo "==> [4/5] Container neu starten"
docker compose up -d --force-recreate app

echo "==> [5/5] Health-Check (max 30s) ..."
for i in $(seq 1 30); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/pricing', timeout=2)" 2>/dev/null; then
    echo ""
    echo "=========================================="
    echo "  ✓ DEPLOY OK - App laeuft und antwortet"
    echo "=========================================="
    # v201: Ein defektes Gate muss im Panel stehen, nicht nur in journalctl.
    # Sonst laeuft der Betrieb monatelang ungeprueft und niemand weiss es.
    if [ "${GATE_DEFEKT:-0}" = "1" ]; then
      # v205b-sec: Bis hier stand im Panel nur DASS das Gate nicht lief,
      # nicht WARUM - und "schau in journalctl" ist fuer jemanden, der nie
      # ins Terminal geht, dasselbe wie keine Meldung.
      GATE_BEFUND="$(tail -c 1800 .deploy_gate_last.txt 2>/dev/null || true)"
      docker compose exec -T app python - "$GATE_BEFUND" <<'PY' || true
import os, sqlite3, sys, time
befund = (sys.argv[1] if len(sys.argv) > 1 else '').strip()
con = sqlite3.connect(os.path.join(os.environ.get('DVE_DATA', '/app/web/data'),
                                   'users.db'), timeout=10)
con.execute("INSERT INTO alerts (schluessel,betreff,text,gemailt,gelesen,"
            "created_at) VALUES (?,?,?,0,0,?)",
            ('deploy_gate', 'Test-Gate nicht lauffaehig',
             'Der Deploy ist durchgelaufen, aber der Selftest konnte im neuen '
             'Image gar nicht starten - dieser Stand ist also UNGEPRUEFT live.'
             + chr(10) + chr(10) + 'Befund:' + chr(10) + (befund or '(keiner)'),
             int(time.time())))
con.commit(); con.close()
print('Gate-Defekt im Panel vermerkt')
PY
    fi
    docker compose logs app --tail 5
    exit 0
  fi
  sleep 1
done

echo ""
echo "=========================================="
echo "  ✗ App antwortet nicht - letzte Logs:"
echo "=========================================="
docker compose logs app --tail 30
exit 1
