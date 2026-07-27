#!/usr/bin/env bash
# v197 TEST-GATE vor dem Deploy.
#
# WARUM: autodeploy.sh zog bis v196 JEDEN Commit und startete neu. Geprueft
# wurde danach nur, ob /api/pricing antwortet - also ob der Server ueberhaupt
# laeuft. Ein kaputter Renderer ging damit live, und der Kunde zahlt einen
# Credit fuer ein kaputtes Video. Das ist der teuerste Fehler im ganzen
# Betrieb, und er ist billig zu verhindern.
#
# WIE: die Tests laufen im NEU GEBAUTEN Image, bevor der laufende Container
# angefasst wird. Rot = Abbruch, die alte Version laeuft unveraendert weiter.
# Der Container wird bewusst mit --rm und ohne Volumes gestartet: der Test
# darf die echte users.db nie sehen (CLAUDE.md-Regel).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Test-Gate: Selftest im neuen Image"

docker compose run --rm --no-deps \
  -e DVE_DATA=/tmp/gate_data \
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
'

echo "==> Test-Gate: gruen"
