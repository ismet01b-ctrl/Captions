# DouchkoVE Web — Aufsetzen

Deine Tester müssen **nichts** installieren. Sie öffnen einen Link, geben ihren
Code ein, ziehen ihr Video rein und bekommen das fertige Video zurück.

**Dein OpenAI-Key liegt auf dem Server.** Kein Nutzer sieht ihn je. Genau das
war der Grund, ihn nicht in eine .exe zu packen — dort stünde er im Klartext
drin und jeder könnte auf deine Rechnung verbrauchen, so viel er will.

---

## In 4 Schritten online

### 1. Einen Server mieten
Du brauchst eine Maschine mit **mindestens 4 CPU-Kernen und 8 GB RAM**
(Hetzner CPX31 ≈ 15 €/Monat, DigitalOcean, Scaleway — egal welcher).
Eine GPU brauchst du nicht: es läuft auf CPU, nur langsamer.

### 2. Hochladen und starten
```bash
git clone <dein-repo>        # oder das Zip hochladen und entpacken
cd premium_captions

docker build -t douchko -f web/Dockerfile .

docker run -d --name douchko \
  -p 80:8000 \
  -v /var/douchko-data:/data \
  -e OPENAI_API_KEY="sk-dein-key" \
  -e DVE_ADMIN="dein-geheimes-wort" \
  --restart unless-stopped \
  douchko
```

Das war's. Der Server läuft auf Port 80.

### 3. Codes vergeben
```bash
docker exec douchko python web/codes.py neu "Lukas" 5
  -> Code fuer Lukas: LUKAS-3761   (5 Videos)

docker exec douchko python web/codes.py liste       # wer hat wie viel verbraucht
docker exec douchko python web/codes.py sperre LUKAS-3761
docker exec douchko python web/codes.py limit LUKAS-3761 20
```

Den Code schickst du deinem Freund zusammen mit dem Link. Fertig.

### 4. Kontrolle behalten
Der Verbrauch steht auch im Browser:
`http://dein-server/admin/codes?schluessel=dein-geheimes-wort`

---

## Was du einstellen kannst

| Umgebungsvariable | Standard | Bedeutung |
|---|---|---|
| `OPENAI_API_KEY` | — | **Pflicht.** Für die Transkription. |
| `DVE_ADMIN` | `admin` | Passwort für die Verbrauchs-Übersicht. |
| `DVE_MAX_SECONDS` | `180` | Längstes erlaubtes Video. |
| `DVE_MAX_MB` | `300` | Größte erlaubte Datei. |
| `DVE_WORKERS` | `1` | Wie viele Videos gleichzeitig rendern. |

**Zu `DVE_WORKERS`:** Lass es bei 1, solange du nicht viele Kerne hast. Zwei
Videos gleichzeitig reißen sich um denselben Prozessor — beide dauern dann
doppelt so lang, gewonnen ist nichts.

---

## Was du wissen musst, bevor du loslegst

**Rendern kostet Rechenzeit.** Auf deinem PC ist das gratis, auf dem Server
nicht. Ein 60-Sekunden-Video braucht auf 4 CPU-Kernen grob 3–6 Minuten. Bei
kostenlosen Testern zahlst du drauf — das ist als Testphase in Ordnung, aber
genau der Punkt, an dem sich die Paywall später rechnet. Das Kontingent pro
Code ist deine Bremse.

**Dazu kommen die OpenAI-Kosten** für die Transkription (wenige Cent pro Video).
Auch die zahlst du. Deshalb das Limit pro Code.

**Blender-Wasser ist serverseitig aus.** 500 MB Installation und sehr langsam.
Alles andere läuft: Matting, Gesichts-Tracking, alle Effekte, alle Animationen.

**Sound-Effekte:** Leg deinen fertigen `sfx/pack`-Ordner ins Projekt, bevor du
das Docker-Bild baust. Dann haben alle Tester sofort die richtigen Sounds — CC0
erlaubt die Weitergabe ausdrücklich. Ohne den Ordner laufen die Videos stumm
(keine synthetischen Ersatztöne, das war Absicht).

---

## Der Weg zur Paywall

Das Code-System ist schon die halbe Miete. Aus einem Code wird ein Abo:
Statt `codes.py` legt dann ein Bezahldienst (Stripe & Co.) die Einträge an,
und das Kontingent wird monatlich zurückgesetzt. Der Rest — Upload, Warteschlange,
Rendern, Download — bleibt genau wie er ist.
