#!/usr/bin/env bash
# DouchkoVE Deploy-Skript. Ein Befehl, macht immer alles richtig:
#   bash update.sh
# Zieht neuen Code, baut das Image (nur was sich geaendert hat),
# startet den Container neu und prueft ob die App wirklich antwortet.
set -e
cd "$(dirname "$0")"

echo "==> [0/4] System-Check"
df -h / | tail -1 | awk '{print "  Festplatte: " $4 " frei (" $5 " belegt)"}'
free -h | awk '/^Mem:/{print "  RAM: " $7 " verfuegbar"}'

echo "==> [1/4] Code aktualisieren"
git pull

echo "==> [2/4] Image bauen (Code-Layer wird immer neu kopiert)"
docker compose build app

echo "==> [3/4] Container neu starten"
docker compose up -d --force-recreate app

echo "==> [4/4] Health-Check (max 30s) ..."
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
