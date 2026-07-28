#!/usr/bin/env bash
# v201 TEST-GATE vor dem Deploy.
#
# WARUM: autodeploy.sh zog bis v196 JEDEN Commit und startete neu. Geprueft
# wurde danach nur, ob /api/pricing antwortet - also ob der Server ueberhaupt
# laeuft. Ein kaputter Renderer ging damit live, und der Kunde zahlt einen
# Credit fuer ein kaputtes Video. Das ist der teuerste Fehler im ganzen
# Betrieb, und er ist billig zu verhindern.
#
# WIE: die Tests laufen im NEU GEBAUTEN Image, bevor der laufende Container
# angefasst wird. Der Container wird bewusst mit --rm und ohne Abhaengigkeiten
# gestartet, mit eigenem DVE_DATA: der Test darf die echte users.db nie sehen.
#
# v201 - ZWEI VERSCHIEDENE FEHLER, ZWEI VERSCHIEDENE ANTWORTEN:
#   exit 1  Die Tests sind ROT. Der Code ist kaputt -> Deploy abbrechen.
#   exit 2  Das Gate konnte gar nicht LAUFEN (Image startet nicht, ffmpeg
#           fehlt, docker zickt). Dann ist NICHTS ueber den Code gesagt.
#           In v197 war beides derselbe Fall, und damit konnte eine Panne
#           an der Pruefvorrichtung den ganzen Betrieb einfrieren: kein
#           Feature ging mehr live, obwohl am Code nie etwas fehlte.
#           Ein Waechter, der bei eigenem Ausfall die Tuer zumauert, ist
#           kein Waechter. Der Deploy laeuft dann weiter - laut, mit
#           Meldung im Panel, aber er laeuft.
set -uo pipefail
cd "$(dirname "$0")"

LOG="$(mktemp)"
# v201a: Das Ergebnis muss autodeploy.sh lesen koennen, damit im Panel steht,
# WELCHE Tests gefallen sind. Nur im Terminal zu meckern hilft niemandem, der
# nie ins Terminal geht.
BEFUND="$(dirname "$0")/.deploy_gate_last.txt"
trap 'rm -f "$LOG"' EXIT

echo "==> Test-Gate: Selftest im neuen Image"

set +e
docker compose run --rm --no-deps \
  -e DVE_DATA=/tmp/gate_data \
  -e DVE_LOGFILE=0 \
  -e OPENAI_API_KEY= \
  --entrypoint bash app -c '
set -e
mkdir -p /tmp/gate_data
# Synthetisches Testmaterial - wir haben im Image kein echtes Video und
# wollen auch keins: der Selftest laeuft auf CPU mit erfundenem Stoff.
ffmpeg -y -v error -f lavfi -i "color=c=0x2b2430:s=540x960:d=6:r=30" \
       -f lavfi -i "sine=frequency=200:duration=6" \
       -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest /tmp/st_clip.mp4
python - <<PY
import json
worte = "Ich zeig dir heute wie wir Captions auf ein neues Level bringen das sind die grossen Momente deines Videos klar".split()
w=[]; t=0.0
for x in worte:
    w.append({"word": x, "start": round(t,2), "end": round(t+0.24,2)})
    t += 0.265
json.dump({"words": w, "text": " ".join(worte)}, open("/tmp/st_transcript.json","w"))
PY
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=logic
' 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e

# Die Entscheidung haengt am ERGEBNIS, nicht nur am Rueckgabewert. Der
# Selftest schreibt am Ende immer "<n>/<m> Tests bestanden"; fehlt die
# Zeile, ist er gar nicht bis zum Ende gekommen.
if grep -qE '[0-9]+/[0-9]+ Tests bestanden' "$LOG"; then
  if [ "$RC" -eq 0 ] && ! grep -q '^FAIL' "$LOG"; then
    echo "==> Test-Gate: gruen ($(grep -oE '[0-9]+/[0-9]+ Tests bestanden' "$LOG" | tail -1))"
    printf 'gruen\n%s\n' "$(grep -oE '[0-9]+/[0-9]+ Tests bestanden' "$LOG" | tail -1)" > "$BEFUND"
    exit 0
  fi
  echo "==> Test-Gate: ROT - die folgenden Tests sind gefallen:"
  grep '^FAIL' "$LOG" | head -20
  { echo 'rot'; grep -oE '[0-9]+/[0-9]+ Tests bestanden' "$LOG" | tail -1;
    grep '^FAIL' "$LOG" | head -20; } > "$BEFUND"
  exit 1
fi

echo "==> Test-Gate: NICHT LAUFFAEHIG (Rueckgabewert $RC, keine Test-Bilanz)."
echo "    Ueber den Code ist damit nichts gesagt. Letzte Zeilen:"
tail -12 "$LOG" | sed 's/^/      /'
{ echo 'defekt'; echo "Rueckgabewert $RC, keine Test-Bilanz"; tail -12 "$LOG"; } > "$BEFUND"
exit 2
