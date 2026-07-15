#!/usr/bin/env bash
# DouchkoVE Web Deploy - Ein Befehl. Auf frischem Ubuntu/Debian ausfuehren.
# Voraussetzungen: root/sudo, IP + Domain zeigen aufeinander.
#
# Was passiert:
#   1. Docker + docker compose installieren (falls fehlt)
#   2. Repo klonen (oder aktualisieren) nach /opt/douchko
#   3. .env aus Umgebung schreiben (OPENAI_API_KEY, DVE_ADMIN, DOMAIN)
#   4. Container bauen und starten
#   5. Ersten Zugangscode anlegen
#
# Nutzung:
#   export OPENAI_API_KEY="sk-..."
#   export DVE_ADMIN="dein-admin-wort"
#   export DOMAIN="douchko.eu"
#   curl -fsSL https://raw.githubusercontent.com/ismet01b-ctrl/Captions/claude/caveman-repo-xt386k/deploy.sh | bash
#
# Oder lokal:
#   ./deploy.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ismet01b-ctrl/Captions.git}"
BRANCH="${BRANCH:-claude/caveman-repo-xt386k}"
INSTALL_DIR="${INSTALL_DIR:-/opt/douchko}"

: "${OPENAI_API_KEY:?OPENAI_API_KEY muss gesetzt sein (export OPENAI_API_KEY=sk-...)}"
: "${DVE_ADMIN:?DVE_ADMIN muss gesetzt sein (export DVE_ADMIN=passwort)}"
: "${DOMAIN:?DOMAIN muss gesetzt sein (export DOMAIN=douchko.eu)}"

log() { echo -e "\033[36m[deploy]\033[0m $*"; }
err() { echo -e "\033[31m[fehler]\033[0m $*" >&2; }

# 1. Docker + docker compose
if ! command -v docker >/dev/null 2>&1; then
    log "Docker fehlt - installiere via get.docker.com"
    curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
    err "docker compose Plugin fehlt - installiere manuell und starte neu."
    exit 1
fi

# 2. Repo holen / aktualisieren
if [ -d "$INSTALL_DIR/.git" ]; then
    log "Repo existiert - aktualisiere in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
else
    log "Klone Repo nach $INSTALL_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# 3. .env schreiben (0600, nur root lesbar)
log "Schreibe .env"
cat > .env <<EOF
OPENAI_API_KEY=$OPENAI_API_KEY
DVE_ADMIN=$DVE_ADMIN
DOMAIN=$DOMAIN
DVE_WORKERS=1
DVE_MAX_SECONDS=180
DVE_MAX_MB=300
EOF
chmod 600 .env

# 4. Container bauen + starten
log "Baue Container (kann 5-15 min dauern - ONNX-Modelle werden gezogen)"
docker compose build
log "Starte Stack"
docker compose up -d

# 5. Warten bis App gesund ist
log "Warte auf App-Container (max 90 s)"
for i in $(seq 1 45); do
    if docker compose exec -T app python -c "import server" 2>/dev/null; then
        log "App laeuft"
        break
    fi
    sleep 2
done

# 6. Ersten Test-Code anlegen (falls noch keine codes.json)
if ! docker compose exec -T app python -c "import json; json.load(open('/data/codes.json'))" 2>/dev/null; then
    log "Lege ersten Test-Code an: TESTER-1000 (10 Videos)"
    docker compose exec -T app python /app/web/codes.py neu "Tester" 10 || true
fi

echo
log "Fertig. App laeuft auf https://$DOMAIN"
log "Caddy holt Let's Encrypt-Zertifikat beim ersten HTTPS-Request (dauert ~30 s)."
log "Admin-Uebersicht: https://$DOMAIN/admin/codes?schluessel=$DVE_ADMIN"
log ""
log "Naechste Schritte:"
log "  - Test aufrufen: https://$DOMAIN"
log "  - Weitere Codes: docker compose exec app python /app/web/codes.py neu <Name> <Anzahl>"
log "  - Verbrauch:     docker compose exec app python /app/web/codes.py liste"
log "  - Update:        cd $INSTALL_DIR && ./deploy.sh"
