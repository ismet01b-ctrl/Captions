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
if ! bash deploy_gate.sh; then
  echo ""
  echo "=========================================="
  echo "  ✗ DEPLOY ABGEBROCHEN - Selftest rot."
  echo "    Die laufende Version bleibt unveraendert."
  echo "=========================================="
  exit 1
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
