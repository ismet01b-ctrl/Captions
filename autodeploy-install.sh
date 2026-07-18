#!/usr/bin/env bash
# DouchkoVE Auto-Deploy EINRICHTEN - genau EINMAL als root ausfuehren.
#
# Danach nie wieder Terminal: der Server prueft alle 2 Min selbst auf neue
# Commits und deployt automatisch (git pull + Build + Restart + Health-Check).
#
# Nutzung (ein Paste auf dem Server):
#   curl -fsSL https://raw.githubusercontent.com/ismet01b-ctrl/Captions/claude/caveman-repo-xt386k/autodeploy-install.sh | sudo bash
#
# Oder lokal in /opt/douchko:
#   sudo bash autodeploy-install.sh
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR:-/opt/douchko}"

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "FEHLER: $INSTALL_DIR ist kein Git-Repo. Erst deploy.sh laufen lassen." >&2
  exit 1
fi

cd "$INSTALL_DIR"

echo "==> Aktuelle Version jetzt deployen (holt u.a. autodeploy.sh)"
bash update.sh

echo "==> systemd-Service + Timer schreiben"
cat > /etc/systemd/system/douchko-autodeploy.service <<EOF
[Unit]
Description=DouchkoVE Auto-Deploy (pull + rebuild bei neuen Commits)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
# flock: ein langer Build darf nicht doppelt starten
ExecStart=/usr/bin/flock -n /run/douchko-autodeploy.lock bash $INSTALL_DIR/autodeploy.sh
EOF

cat > /etc/systemd/system/douchko-autodeploy.timer <<EOF
[Unit]
Description=DouchkoVE Auto-Deploy alle 2 Minuten

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

echo "==> Timer aktivieren"
systemctl daemon-reload
systemctl enable --now douchko-autodeploy.timer

echo ""
echo "=========================================="
echo "  ✓ AUTO-DEPLOY AKTIV"
echo "  Ab jetzt geht jeder Push von selbst live (max ~2 Min)."
echo "  Du musst nie wieder ins Terminal."
echo "=========================================="
echo "  Status ansehen:  systemctl status douchko-autodeploy.timer"
echo "  Live-Log:        journalctl -u douchko-autodeploy.service -f"
echo "  Ausschalten:     sudo systemctl disable --now douchko-autodeploy.timer"
