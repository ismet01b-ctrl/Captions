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
bash update.sh
