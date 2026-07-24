# DouchkoVE Captions — Arbeitsanweisung für Claude Code

Automatische Premium-Untertitel im Editorial-Stil + Apple-Style Motion-Graphics.
**Eine gemeinsame Engine, zwei Gesichter:**
1. **Windows-Desktop-App** (`gui.py`) — läuft lokal auf Ismets PC mit seinem
   `OPENAI_API_KEY`.
2. **Web-Produkt douchko.eu** (`web/server.py`, FastAPI) — das ist inzwischen der
   Hauptweg: echte Kunden, Credits, Stripe. **Beta.**

**Jede Entscheidung dient der Qualität.** Stand: v101k (Juli 2026) —
Innovations-Batch komplett: Betonungs-Typografie (Variable-Font nach
Sprech-Pegel), Choreographie-Regie, Silent-Score, Watermark-Unlock
(Kauf schaltet gecachte Videos ohne Neu-Render frei), Beat-Grid,
Safe-Zone-Regie (Plattform-UI-Masken tiktok/reels/shorts,
`output.platform`), Korrektur-Gedächtnis (Vorlieben-Profil in die
KI-Regie), Licht-Wahrheit (gerichteter Kontakt-Schatten),
Regie-Kontaktbogen (`/api/contact/{jid}`), Caption-Alpha-Export
(ProRes-4444-Ebene via Difference-Matting-Doppelpass, `--alpha-export`,
`/api/alpha/{jid}` für Käufer), World-Lock Wand (eigener Wand-Track),
Hand-Kontakt (MediaPipe `models/hand.task`, Feder-Impuls + Occlusion),
Depth-Bullet-Time (2.5D-Dolly in der Pause vor power-3). NICHT gebaut
(bewusst): Tiefen-Fokuszug, persistente Welt-Anker (SLAM),
Hook-A/B-Varianten.

## Oberste Regeln (nicht verhandelbar)
1. **Qualität über alles.** Niemals ein Feature vereinfachen, degradieren oder
   durch eine Heuristik ersetzen, um Zeit/Kosten zu sparen. Im Zweifel: die
   aufwändigere, bessere Lösung. Gilt auch für Optik — nichts darf "billig" oder
   "draufgeklatscht" aussehen; Maßstab ist ein Senior-VFX/Motion-Designer 2026.
2. **Kein Deliver ohne grünen Selftest.** Erst wenn ALLE Tests grün sind, gilt
   etwas als fertig. Nie Teilstände als fertig ausgeben.
3. **Fragen statt raten.** Bei Unklarheit über Architektur/Verhalten nachfragen,
   nicht annehmen. Ismet entscheidet.
4. **Nichts ungefragt umbauen.** Keine Architektur-Änderungen ohne Bestätigung.
5. **Ehrlich bleiben.** Tests laufen hier auf Linux/CPU mit synthetischem
   Material und OHNE OpenAI-Key (Heuristik-Pfad). Echte GPU-/KI-/Qualitäts-
   wirkung sieht Ismet erst auf Windows bzw. live auf douchko.eu mit echtem
   Material — das immer klar sagen, nie so tun als sei es final verifiziert.

## Kommunikation
Ismet ist direkt und terse. **Effizienzmodus:** keine Floskeln, kurze klare
Sätze, nur Code + exakte Schritte. Technische Tiefe bleibt voll erhalten,
nur Füllmaterial weg. Korrektur ohne Rechtfertigung annehmen. Bei visuellen
Änderungen: Beweis liefern (Frame-Streifen / Beispiel-Video), nicht behaupten.

## Deploy (Web) — WICHTIG für neue Chats
- Entwicklung läuft auf dem Branch `claude/caveman-repo-xt386k` (committen +
  pushen, wenn eine Einheit fertig+grün ist).
- Der Server zieht selbst: `autodeploy.sh` (systemd-Timer, alle 2 Min) prüft
  den Branch, bei neuen Commits läuft `update.sh` (Rebuild + Neustart).
  → Änderungen sind ~5-15 Min nach dem Push auf douchko.eu live.
- Kein Push = kein Deploy. Ismet testet live erst NACH dem Deploy.

## Stack
Python. Engine: ffmpeg, OpenAI Whisper API (`whisper-1`, Transkription) +
GPT-4o / GPT-4o-Vision (KI-Regie), RVM-Matting (ONNX, Person freistellen),
Depth-ONNX (Szenen-Occlusion), MediaPipe Face, Blender 4.5.11 (3D-Wasserglas),
Variable-Font-Instanzen. Desktop-GUI: tkinter (Canvas-Custom-Widgets).
Web: FastAPI + SQLite (WAL), reines HTML/JS-SPA (kein Framework), Stripe,
Caddy (HTTPS-Reverse-Proxy) + Docker Compose.

## Dateien
Engine + Desktop:
- `render.py` — **Caption-Pipeline** (Herzstück): Transkription → KI-Regie →
  Matting → Face-Tracking → Compositing → Kamera → Encode. Enthält alle 26
  Text-Animationen (`anim_apply`/`_anim_core`).
- `gfx_engine.py` — **Motion-Graphics-Engine** (Apple-Style UI-Motion). 6
  Templates (pills/widgets/appstore/lowerthird/chat/notify), 4 Styles, MP4 +
  ProRes-4444-Alpha-MOV. Warmer Preview-Daemon (`--preview-server`).
- `gui.py` — tkinter-Desktop-GUI (Apple-Dark, Canvas-Cards, iOS-Switch).
- `blender_engine.py` — 3D-Wasserglas-Renderer (stehender Szenen-Text).
- `sfx_engine.py` / `sfx_pack.py` — CC0-Sound-System (Freesound).
- `vfx_engine.py` — Cloud-VFX-Hook (Higgsfield/Seedance), opt-in, NotImplemented.
- `config.yaml` — alle Engine-Einstellungen.

Web-Produkt (`web/`):
- `web/server.py` — FastAPI-Backend: Auth, Credits/Stripe, Job-Queue (Caption
  + Motion-Fast-Lane), Library, Momente-Editor-API, Health/Monitoring,
  Warm-Preview-Daemon, DB-Backup, Watchdog.
- `web/index.html` — SPA (Create/Motion/Library/Billing/Account). Ein File.
- `web/landing.html` — Marketing-Landing (**Englisch**, international, an
  Branchen-Konventionen ausgerichtet; KEINE Konkurrenz-Namen, kein Datenschutz-
  Block auf der Seite).
- `web/imprint/privacy/terms.html`, `web/codes.py`.
- `Dockerfile`, `docker-compose.yml` (app + caddy), `autodeploy.sh`, `update.sh`.

Doku:
- `PROJEKT_STATUS.md` — **komplette Versionshistorie, HIER ZUERST LESEN.**
  Neueste Einträge stehen oben unter `## Kern-Features` (v100 → v98 → …).
- `ANLEITUNG.md` — Nutzer-Anleitung.

## KI-Regie (Kern der Qualität — NICHT optional machen)
- `ai_direct()` — GPT-4o wählt Keywords/Phrasen/Effekte (fx)/Wucht(power)/
  Animation. Prompt = `REGIE_PROMPT` (Retention-Dramaturgie, Sperrliste,
  ORT-/HANDLUNG-Mapping, Selbstbezug, Audio-Dynamik).
- `ai_scene_direct()` — GPT-4o-Vision entscheidet Szene/Lage pro Moment
  (wasser/boden/wand/himmel/person, liegend/stehend/frei).
Beide laufen über Ismets `OPENAI_API_KEY` (Desktop lokal, Web über Server-Env).
Heuristik-Fallbacks existieren nur als Notnagel bei fehlendem Key — nie als
Standardweg bewerben. Determin. Leitplanken danach: `_regie_sanity`,
`_speech_intent`, `_self_ref_intent`, `_behind_cover_backstop`, `_cap_power3`.

### Semantische Regie (v99/v99a) — "Captions tun, was der Sprecher sagt"
Sagt jemand WO/WAS die Caption tun soll, MUSS die Caption das abbilden:
- "behind me" → fx `behind` (Text hinter der Person, echte RVM-Occlusion; bei
  Nahaufnahme szene `himmel` = steigt über den Kopf, statt unsichtbar).
- "on the ground / an der Wand / im Wasser / am Himmel" → fx `ground`+szene+lage.
- "explode / fällt / fliegt / …" → passende Animation, sichtbar vorn (nie behind).
- Selbstbezug-Sätze bestehen oft nur aus Sperrlisten-Wörtern → `_self_ref_intent`
  erzeugt den Moment notfalls selbst (läuft in ALLEN Pfaden, auch ohne Key).
- **`intent`-Flag = Ansage ist Gesetz.** Es schützt den Moment vor Degradierung
  durch Dichte-Limit, B-Roll-Gate, Mehrwort-Komposition, Nahaufnahme-Backstop
  und Editor-Roundtrip. NUR eine bewusste Nutzer-Änderung im Editor löscht es.

## Animationen (26 Stück, Stand 2026)
Alle über zentrales `anim_apply()` routen (Beat-Sync + Motion-Blur legt es
oben drauf). Kern in `_anim_core`. Qualitätsmaßstab (v100): Federn mit
Overshoot statt ease_out, Anticipation→Impact→Settle statt Endlos-Drift,
Envelope-Follower statt rohem Audio, verwürfelte Staffelung statt linearer
Muster, Tremor statt Weißrauschen. Keine Anim darf mechanisch/synthetisch/
1-Frame-zufällig wirken. Katalog: `ANIM_LIST`; Keyword→Anim-Heuristik
`ANIM_HINTS`/`anim_for` (DE+EN, an Satzgrenzen gekappt via `anim_ctx`).

## Transkription
Nur OpenAI Whisper API (`whisper-1`) — beste Qualität für Namen/Fachbegriffe.
Lokale faster-whisper-Option in v72 komplett entfernt (Qualität > alles).

## Web-Produkt: Geschäftsmodell & Sicherheit
- **Steuer-Identität (NIE vergessen): Kleinunternehmer §19 UStG, USt-IdNr
  `DE463613884`.** Steht im Impressum (§5 DDG Pflicht, da vorhanden) und im
  Stripe-Rechnungs-Footer (`DVE_TAX_ID`-Default). NIEMALS USt ausweisen.
- **Preise: Einmalkauf-Credits 9€/20, 19€/60, 39€/150, 6 Monate gültig.
  KEIN Abo — das ist das Alleinstellungsmerkmal** (Abo-Frust ist die Beschwerde
  Nr. 1 bei ALLER Konkurrenz). 1 Credit = 1 Min fertiges Video (pro angef. Min);
  Motion-Clip 1 Cr (MP4) / 2 Cr (ProRes-Alpha). Free 3 Min/Monat + Wasserzeichen
  bis zum ersten Kauf. Willkommens-Guthaben (120s) erst NACH E-Mail-Verify.
- **Bewusst NICHT bauen** (Fokus, aus Konkurrenz-Analyse): kein Abo/Hybrid,
  kein AI-B-Roll, kein Clipping/Avatare, kein Sprachen-Wettlauf, kein
  Feature-Stacking. Positionierung: Finishing-Tool nach dem Schnitt.
- Sicherheit: WAL+busy_timeout, `--proxy-headers` (IP-Rate-Limits), Credits
  atomar+idempotent, Ownership-Checks, Upload-Caps, jid-Path-Traversal dicht,
  Stripe-Webhook-Secret-Pflicht. Konto-Löschung: Kaufbuchungen → `ledger_archive`
  (GoBD/§147 AO 10 Jahre; DSGVO Art.17(3)(b)), Rest echt gelöscht.
- Betrieb: `/api/health` (für externen Uptime-Pinger), Admin-Störungsmails
  (1/h/Schlüssel), Watchdog killt hängende Renders (45min) + erstattet,
  Offsite-DB-Backup per Mail, Warm-Preview-Daemon (~0.5s statt 2s).
- OFFEN (Ismet): Stripe Live-Modus scharfstellen, Demo-Video in den Hero,
  UptimeRobot auf /api/health, Kontaktadresse vereinheitlichen.

## Selftest — Ablauf (Pflicht vor jedem Deliver)
Gesamt **612/612 grün (Stand v101k)** + Renders 7/1/5/2 + GUI. Läuft nur unter Linux/CPU mit
synthetischen Assets und OHNE OpenAI-Key; GUI-Tests headless via `xvfb-run`.
Der Server-Code (`web/server.py`) wird im `logic`-Teil mitgetestet (isolierte
Test-DB, Quelltext-Garantien).

```bash
# Testmaterial: /tmp/st_clip.mp4  + /tmp/st_transcript.json
# In Etappen (Rendern ist langsam, sonst Timeout):
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=logic
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render1   # 6
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2a  # 1
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2b  # 1
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2c  # 2
```
GUI-Smoke separat:
```bash
xvfb-run -a python3 -c "import tkinter as tk, gui; r=tk.Tk(); gui.App(r); r.destroy(); print('GUI_OK')"
```
Web-Smoke (optional): Server auf Port starten, Playwright gegen `/` und `/app`
(Login → Testuser in users.db verifizieren → Seite prüfen → Testuser löschen).

## Deliver-Muster (jede neue Version)
1. Selftest erweitern (neues Feature bekommt Tests; visuelle Sachen bekommen
   Verhaltens-Invarianten, nicht nur "läuft durch").
2. Volle Regression grün + ggf. Browser-Smoke.
3. `PROJEKT_STATUS.md`-Eintrag oben (was neu, EHRLICHE Ursache, Beweis,
   Test-Hinweise).
4. Commit + Push auf den Feature-Branch (→ Auto-Deploy).
5. Deutscher Summary im Effizienzmodus, mit Beweis (Frames/Video) bei Optik.

## Wichtige Prinzipien (aus der Historie)
- **Sound:** nur echte CC0-Library-Sounds (Freesound), kein Synthetik-Fallback.
  Stille ist besser als billiger Ton. Ohne `sfx/pack` laufen Videos STUMM.
  SFX sitzen auf Wort-Onsets, nicht auf Anim-Phasen.
- **B-Roll:** in ALLEN Systemen ausschließen (auch Kamera-Impulse) — AUSSER
  explizit angesagte (`intent`) Szenen-Texte, die dort hingehören.
- **GUI:** Rounded Cards nur via Canvas (nicht tk.Frame).
- **Animationen:** immer über zentrales `anim_apply()` routen.
- **Config-Sicherheit:** in Tests NIE `app.save_cfg()` gegen echte config.yaml;
  Web-Tests NIE gegen die echte users.db (isolierte `DVE_DATA`).
- **Landing:** Englisch, international, Modellnamen unsichtbar (kein "GPT-4o"
  im Hero), keine Konkurrenz-Namen, kein Datenschutz-Block (gehört in /privacy).

## Offene echte Punkte
- Sound-Pack: Ismet wählt/schickt CC0-Zip → ohne Pack stumm.
- Windows-Test mit echtem Material + Maskenqualität 'hoch' + MOV-Import Premiere.
- Stripe Live-Modus (Keys + Webhook, zum Schluss).
- Semantik-Regie & v100-Animationen auf ECHTEM Material verifizieren (hier nur
  Heuristik/CPU/synthetisch getestet).
