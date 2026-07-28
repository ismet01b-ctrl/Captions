#!/usr/bin/env bash
# v204-sec: Der Dienst lief bis v203 als root - und er schiebt FREMDE Videos
# durch ffmpeg, opencv und Pillow. Bricht dort etwas aus, gehoert dem Angreifer
# sofort alles im Container. Ab hier laeuft er als unprivilegierter Nutzer.
#
# WARUM EIN SKRIPT UND KEIN SCHLICHTES "USER dve" IM DOCKERFILE:
# /data ist ein bestehendes Docker-Volume, das seit dem ersten Start root
# gehoert. Ein blosses USER dve haette den Server beim naechsten Deploy nicht
# mehr schreiben lassen - die Seite waere unten gewesen. Dieses Skript startet
# als root, uebergibt /data an den Dienst-Nutzer und LEGT DANN die Rechte ab.
#
# FAIL-SAFE: Wenn irgendetwas daran nicht klappt (kein runuser, Rechte lassen
# sich nicht setzen), laeuft der Dienst wie bisher weiter - laut, mit Warnung
# im Log. Eine Haertung, die im Zweifel die Seite abschaltet, ist schlimmer
# als die Luecke, die sie schliesst.
set -u

DVE_USER="${DVE_USER:-dve}"
DATA_DIR="${DVE_DATA:-/data}"

warn() { echo "WARN entrypoint: $*" >&2; }

start_as_root() {
  warn "laeuft als root weiter (Haertung uebersprungen: $1)"
  exec "$@"
}

# Schon unprivilegiert gestartet? Dann nichts zu tun.
if [ "$(id -u)" != "0" ]; then
  exec "$@"
fi

if ! id "$DVE_USER" >/dev/null 2>&1; then
  warn "Nutzer $DVE_USER gibt es nicht - starte als root"
  exec "$@"
fi

if ! command -v runuser >/dev/null 2>&1; then
  warn "runuser fehlt - starte als root"
  exec "$@"
fi

# Datenverzeichnis uebergeben. Bei einem grossen Volume kann das dauern, aber
# es passiert nur, wenn die Rechte noch nicht stimmen.
mkdir -p "$DATA_DIR" 2>/dev/null || true
if [ "$(stat -c %U "$DATA_DIR" 2>/dev/null || echo '?')" != "$DVE_USER" ]; then
  if ! chown -R "$DVE_USER":"$DVE_USER" "$DATA_DIR" 2>/dev/null; then
    warn "konnte $DATA_DIR nicht uebergeben - starte als root"
    exec "$@"
  fi
fi

# Der Renderer schreibt Zwischendateien neben die Quelle und braucht einen
# beschreibbaren Cache (matplotlib/fontconfig/npm legen dort ab).
for p in /tmp /app/motion; do
  [ -d "$p" ] && chown -R "$DVE_USER":"$DVE_USER" "$p" 2>/dev/null || true
done

# Gegenprobe VOR dem Umschalten: kann der Nutzer wirklich schreiben? Lieber
# hier merken als nach dem Rechte-Abwurf im laufenden Betrieb.
if ! runuser -u "$DVE_USER" -- test -w "$DATA_DIR" 2>/dev/null; then
  warn "$DVE_USER kann $DATA_DIR nicht beschreiben - starte als root"
  exec "$@"
fi

echo "entrypoint: Dienst laeuft als $DVE_USER (nicht root)"
exec runuser -u "$DVE_USER" -- "$@"
