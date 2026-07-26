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
Depth-Bullet-Time (2.5D-Dolly in der Pause vor power-3),
Zeige-Regie (Caption landet, wohin der Sprecher zeigt oder schaut),
Objekt-Anker (Caption dockt am genannten Gegenstand an und bleibt daran),
Zwei-Sprecher-Regie (Caption springt auf die Seite des aktiven Redners). NICHT gebaut
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
  Nahaufnahme Flag `nah` = bleibt auf Kopf-/Schulterhöhe und wird so weit
  vergrößert, dass er beidseitig am Kopf vorbeiragt. **NICHT mehr `himmel`** —
  das schob den Text an den oberen Bildrand, weg von der Person, und die
  Ansage stimmte nicht mehr (v141, Ismets Befund).
- "on the ground / an der Wand / im Wasser / am Himmel" → fx `ground`+szene+lage.
- "explode / fällt / fliegt / …" → passende Animation, sichtbar vorn (nie behind).
- Selbstbezug-Sätze bestehen oft nur aus Sperrlisten-Wörtern → `_self_ref_intent`
  erzeugt den Moment notfalls selbst (läuft in ALLEN Pfaden, auch ohne Key).
- **`intent`-Flag = Ansage ist Gesetz.** Es schützt den Moment vor Degradierung
  durch Dichte-Limit, B-Roll-Gate, Mehrwort-Komposition, Nahaufnahme-Backstop
  und Editor-Roundtrip. NUR eine bewusste Nutzer-Änderung im Editor löscht es.
- **Ansage-Erkennung läuft in ALLEN Pfaden (v159).** `_speech_intent` und
  `_self_ref_intent` stehen in `main()` an der immer laufenden Stelle, NICHT
  nur in `ai_direct`. Sonst fällt die Ansage weg, sobald kein Key da ist, die
  API ausfällt **oder der Regie-Cache greift**, und der Cache ist der
  Normalfall beim zweiten Render desselben Videos. Wer eine neue
  Semantik-Prüfung baut, hängt sie dort hin, nicht in den KI-Zweig. Im
  KI-Pfad läuft `_speech_intent` dadurch zweimal; der Riegel
  `if fx_map[i].get('intent'): continue` hält das Log sauber.
- **Vokabellisten treffen Verbformen (v159).** `ANIM_HINTS` steht in der
  3. Person Singular, Transkripte sagen Infinitiv und Plural. `_anim_hit`
  vergleicht deshalb über `_anim_stamm()`. Blindes `startswith` erst ab
  6 Zeichen Stichwortlänge, sonst schlug 'fall' in "FALLS" an.
  Verneinte Sätze bekommen KEINE Animation (`_hat_negation`): eine Anim, die
  die Handlung ausführt, widerspricht dem Satz, und ihr SFX tut es hörbar.

### Hand-Regie (v174) — "der Text weicht der Hand, die ihn schubst"
**Angesagt schlägt beiläufig (v177/v178).** Der angesagte Wisch hat eigene
Werte (Deckel W*3.6, Impuls 2.2, Feder K=52/C=5.2 → ~143 px Spitze); der
zufällige Kontakt bleibt bei v101j (~16 px). Wer daran dreht, muss BEIDE
Wege prüfen — und dass der Block in die Ruhelage zurückkehrt.
**Der angesagte Wisch braucht keine Berührung (v177).** Die Hand fährt vor
dem eigenen Körper entlang — dort kann die Caption nie liegen (Gesichtssperre
2.5 > Hand-Ziel 2.2, richtig so). Sagt der Satz die Handlung UND ist ein
Wisch > 0.50 W/s messbar, bekommt der Block den Impuls ohne Trefferprüfung.
**Das Hand-System darf NIE an `kw_i` hängen (v176).** `need_hands`,
`hand_contacts` und die Feder gelten auch für Flow-Chunks — Schub-Sätze
sind fast immer Füllwort-Chunks ohne Keyword. Dreimal derselbe Fehlertyp
(v159/v170/v176): ein Riegel am falschen Gate.
**Drei Stufen, sauber getrennt (v179):** angesagter Wisch → voller Schub
(~143 px), echte Berührung → Stups (~16 px), Geste daneben → NICHTS. Der
v174-Näherungstreffer ist raus: zusammen mit v176 (alle Flow-Chunks) ließ
er bei einem gestikulierenden Sprecher jede Caption zucken. Ein Notbehelf
muss zurückgebaut werden, sobald die richtige Lösung steht.
`hand_ziele()` zieht die Caption bei Hand-Aktions-Wörtern (push/shove/
wegschieben/wischen, `_HAND_AKTION`) in Reichweite der Hand; `hand_contacts`
trifft zusätzlich per **Näherung** (0.075 W), wenn die Hand schnell
(≥0.25 W/s) und in RICHTUNG des Texts fliegt. Ohne Nähe-Platzierung läuft
jede Schub-Geste ins Leere — die Platzierungs-Regie legt Text sonst von der
Person weg. **Abnahme-Lehre: nie einen Einzelframe bewerten** — Exit-Blenden
und wortweiser Aufbau sehen im Standbild wie Fehler aus (zweimal passiert:
"is", "EXPLODE").

### Zeige-Regie (v160) — "Captions landen, wohin gezeigt wird"
`zeige_ziele()` misst an den Moment-Zeitpunkten, wohin der Sprecher **zeigt**
(Hand-Landmarks) oder **schaut** (Kopfdrehung aus den Gesichts-Keypoints).
Reine Bildmessung, kein API-Ruf. Zeigen schlägt Blick. Das Ziel geht als
`ziel` in `spot()` und als Seitenwahl in `pick_side()`.
- **Gestreckt/eingerollt wird gegen das HANDGELENK gemessen**, nicht gegen die
  Senkrechte. Sonst hängt das Ergebnis an der Handdrehung im Bild.
- **Offene Hand = Geste, kein Zeigen.** Ohne diese Sperre schiebt jedes
  Herumfuchteln die Captions durchs Bild.
- **Finger Richtung Kamera → kein Ziel.** Kurze Projektion heißt: im Bild gibt
  es keinen gemeinten Ort. Raten ist schlechter als nichts.
- **Das Gesicht bleibt tabu.** Zeige-Gewicht 2.2, Gesichtsberührung ab 2.5.
  Wer auf den eigenen Kopf zeigt, bekommt den Text daneben.
- **Eine gehaltene Geste ist EINE Ansage (v167).** `_ziel_dedupe` lässt von
  aufeinanderfolgenden Zielen am selben Ort nur die ersten zwei Momente
  durch. Sonst nagelt ein über das halbe Video gehaltener Arm alle Captions
  auf eine Seite (Ismets Befund, am Bild belegt).
- **Sichtbarkeit hängt am WORT (v172), nicht an der Anim-Wahl.**
  `anim_for(txt)` in `_VISIBLE_ANIM` → nie behind/ground/**blurin** (alle
  drei zeichnen vor dem Person-Overlay, v173) — unabhängig davon,
  welches Anim die Regie wählte und ob `effects.anim` an ist. Der Riegel
  sitzt in `build_plans` außerhalb des Anim-Blocks (v159-Lehre). Rangfolge:
  die HANDLUNG im Satz gewinnt auch gegen intent; eine ORTS-Ansage
  ("behind me") hat kein Aktionsverb und bleibt dadurch Gesetz. B-Roll
  behält Szenen-Text (keine Person, die verdeckt).
- **Ein-Wort-Rest nach Pause fällt in ALLEN Dichte-Pfaden weg (v170).**
  Der Riegel steht VOR den Pfad-Weichen (akzente/intro/durchgehend/forts) —
  er saß erst nur in satz_offen, und Ismets Job lief mit 'durchgehend'.
- **Blick ist Abweichung, nicht Haltung (v166).** `_blick_targets` filtert
  gegen den Median der Kopfdrehungen. Eine absolute Schwelle macht aus einer
  seitlich stehenden Kamera ein Dauer-Ziel und nagelt alle Captions auf eine
  Seite (Ismets Befund). Zeigen bleibt absolut — eine Geste ist eine Ansage.
- Bei gesetztem Ziel fallen Wunschzone und Wunschseite weg (`return k`), der
  Rest der Kosten bleibt. Ein Ziel bricht die Hysterese (`kalt`).
- **Grenze:** ein breiter Block hat im Title-Safe kaum Spielraum (0.773 W bei
  0.84 W nutzbar). Die Regie wirkt, wo Platz ist.

### Zwei-Sprecher-Regie (v162) — "Der Text folgt dem Redner"
`sprecher_at()` liefert die x-Position des aktiven Gesichts, aber **nur bei
mehreren Personen**. Das Signal ist alt (`_active_index`, Mundbewegung, v96);
neu ist, dass die Captions es lesen und nicht nur die Kamera.
- **Kein Tiebreaker.** `wunsch_x` wirkt nur ohne Motiv-Berührung, und neben
  zwei Personen ist fast jede Stelle berührt. Deshalb eigener Kosten-Term
  (Gewicht 1.3), der immer wirkt, aber unter der Gesichtssperre (2.5) bleibt.
- **`_free_x_multi` nimmt die Lücke NEBEN dem Sprecher**, nicht die breiteste.
  Passt keine, gilt wieder die breiteste (sonst wird der Sprecher angeschnitten).
- **Auf das erkannte Gesicht einrasten.** `face_pos` ist über 41 Frames
  geglättet und liegt beim Wechsel zwischen beiden Personen — ohne Einrasten
  landet der Text in der Mitte, wo niemand sitzt. Hysterese gegen Flackern,
  aber ein echter Sprecherwechsel bricht die Platzierungs-Hysterese.

### Objekt-Anker (v161) — "Captions kleben am Gegenstand"
`ai_objekt_anker()` fragt GPT-5-Vision **einmal pro Moment** nach einem
sichtbaren Bezugsobjekt; `ObjektAnker` (Optical Flow) verfolgt es **jeden
Frame** ohne Token. Die KI sagt WAS, die Messung sagt WO.
- **Der Anker muss in den Regie-Cache** (`parse_regie` + Cache-Schreiber).
  Sonst ist er beim zweiten Render weg — derselbe Fehlertyp wie v159.
- **Der LK-Status ist bei einem Schnitt wertlos.** LK rastet auf einer
  ähnlichen Stelle ein und meldet plausible Mini-Bewegung (gemessen: -3.6 px
  bei 200 px Sprung). Nur die **Vorwärts-Rückwärts-Probe** (Median-Flow,
  Schwelle 1 px) erkennt das. Wer hier etwas ändert, darf sie nicht
  wegoptimieren.
- **Verlorene Spur friert ein**, sie springt nicht auf null zurück.
- **Neben das Objekt, nie darauf** — sonst verdeckt die Caption genau das,
  worum es geht. Erst darunter, dann darüber, sonst gar nicht.
- **Keine Doppelbewegung**: verankerte Plans bekommen weder `track_offset`
  (Gesicht) noch `scene_shift` (Schwenk) obendrauf.
- Nicht jeder Look legt sein Bild in `arr` — `outline` benutzt `o_arr`.

### Platzierungs-Regie (v143) — "Captions passen sich dem Bild an"
Ein Textblock bekommt seine Position aus `spot()` in `build_plans`, nicht aus
Konstanten. Reihenfolge: harte Sperren (Title-Safe 5 %, Plattform-UI-Maske,
Gesichtsbox), weiche Kosten (Motiv-Unruhe aus `scene_space_sampler`, Abstand
zur Wunschzone), **Hysterese** (alte Stelle gewinnt, solange sie nicht klar
schlechter ist), Rasterung auf `VZ_GRID`. Bei echter Nahaufnahme verengt
`_freie_breite` die Spalte, damit der Block NEBEN den Kopf passt.
**Ohne Hysterese springt der Text** — 10 px Gesichtsbreite reichten im ersten
Entwurf für 0.19 W Versatz. Das ist kein Detail, das ist der Unterschied
zwischen Regie und Zittern.

### Schriftgroessen (v154)
Das **Schluesselwort und der Fliesstext haben getrennte Referenz-Faktoren**
(`caption_scale` aus `key_hoehe`, `caption_scale_klein` aus `klein_hoehe`).
Den Fliesstext ueber key_hoehe mal Hierarchie abzuleiten war der Grund, warum
eine Referenz mit grosser Punchline den ganzen Satz aufblies.
Hausmass: 0.076 em Schluesselwort, 0.034 em Fliesstext. **Wer daran dreht,
muss den Punch-Faktor mitziehen** — sonst faellt der Randabfall (v152) unter
die Bildbreite und ist unsichtbar.
Jeder Keyword-Moment bekommt eine Animation; `anim_for()` liefert bei
normalen Woertern None, deshalb rotiert ein **bedeutungsneutraler Fallback**.

### Buendigkeit vs. Bildseite (v155/v156)
**`caption_align` = Buendigkeit der Zeilen** (kommt aus der Referenz-Messung).
**`caption_seite` = wo im Bild der Block sitzt** (nur ausdrueckliche
Nutzerwahl, sonst 'auto'). Beides in einen Schalter zu legen war der Grund,
warum eine gelernte Referenz mit 'links' jede Caption an die linke Kante
nagelte.
Der Seiten-Tiebreaker prueft `_motiv`, und `_motiv` zaehlt **nur
Gesichts-Beruehrungen** — mit der Unruhe-Karte darin war er nie erfuellt.
v156: die gemessene Buendigkeit ist eine **Tendenz**, rund die Haelfte der
Bloecke folgt der Bildseite. Eine Messung auf alle Chunks anzuwenden macht
aus einer Tendenz eine Schablone.

### Viral-Look (v183) — Markt-Standard als Preset, Default fuer 9:16
Look 'viral' (Server-Preset + Engine-Schalter `effects.caption_viral`):
alles versal + extrabold (Montserrat XB), Schluesselwort 2.15x / Fliesstext
2.90x Hausmass, enge 2-4-Wort-Bloecke mittig-unten (caption_zone 0.58),
Karaoke: die Akzentfarbe (fest Gelb, adaptive AUS - Konstanz ist der Look)
wandert mit dem gesprochenen Wort (`tint_glyph`, Kontur bleibt dunkel),
vergangene Woerter dimmen NICHT, Pop 10 %. Kein Schreibschrift-Akzent.
- **Der Zeilensatz-Riegel sitzt in build_plans** (immer laufende Stelle,
  v159-Lehre), nicht nur im Preset.
- **Der Punch-Deckel kennt den Crash-Zoom** (0.89 W - 0.11 W * crash, alle
  Looks): der Zoom sitzt genau auf Punch-Momenten und schob die Kante aus
  dem Bild (gemessen 0.999 W). Wer am Deckel dreht, muss den Zoom mitdenken.
- **'mitte'-Zeilen und Zeilen breiter als der Satzspiegel werden ZENTRIERT**
  (alle Looks) - buendig bei x0 war der halbe Anschnitt.
- Hochformat-Upload waehlt in der UI Viral vor; `State.lookChosen` schuetzt
  jede bewusste Wahl. Editorial & Co. bleiben unveraendert waehlbar.
- Viral-Groessen sind MULTIPLIKATOREN auf die Hausmasse - eine gelernte
  Referenz (caption_scale) skaliert weiter relativ, v151-Kaskade intakt.

### Lesbarkeit + aktives Wort (v181/v182)
**Kontur ist Pflicht, nicht Deko.** Ein versetzter Schlagschatten trägt auf
grauem Stoff nicht — gemessen 1.5 bis 3.1:1, Norm ist 4.5:1. `caption_kontur`
zeichnet einen dunklen Saum auf der HINTEREN Ebene (0.055 der Schriftgröße);
`caption_contrast` steht auf 4.5.
- **Mit Kontur bleibt der Text hell**, bis der Untergrund wirklich hell ist
  (bg_lum ≥ 0.45). Nach Dunkel zu kippen ist lesbar, sieht aber aus wie ein
  anderer Look.
- `fit_caption_color` fällt notfalls auf reines Weiß/Schwarz — ein Szenen-Ton,
  den man nicht lesen kann, ist keine Handschrift.
- **Die Kontur zählt nicht zur Layout-Breite** (`_ink_x` misst den
  Glyphenkörper). Rest 0.003 W durch Antialiasing bleibt.
- **v182 aktives Wort:** gesprochenes Wort voll + Pop, vergangene auf 70 %,
  Keywords dimmen NIE. Kein Farbwechsel — der Akzent gehört dem Schlusswort.

### Querformat steht mittig (v180)
**16:9 = unten mittig**, das ist die Konvention für eingebrannten Text
(Netflix TTSG, BBC, SMPTE). Links/rechts geparkt ist Lower-Third-Sprache.
Die Seiten-Abwechslung (v168) gilt **nur im Hochformat** — sie war gegen
"immer links" bei 9:16 gebaut und lief vorher als Nebeneffekt auch quer.
Mitte ist ein **Wunsch, keine Fessel**: `spot()` weicht weiter aus (Person
unten mittig → Block auf 0.75 W gemessen), Zeige-Ziel, Hand-Geste,
Sprecherwechsel und `caption_seite` überstimmen sie.

### Seite als Entscheidung (v168) — NACH v153 lesen
"Immer links, egal was" hatte drei gemessene Ursachen: (1) der Seiten-Wurf
pro Chunk (~40-45 % rechts, erster Chunk immer links, lange Ketten normal) →
jetzt **echter Wechsel mit Zustand** (`spot_state['seite_lauf']`, jeder
vierte bleibt, Start am Video-Seed); (2) der 0.55-Tiebreaker verlor gegen
die 1.6-Unruhe-Karte — die ruhigste Bildhälfte gewann IMMER → jetzt
entscheidet der **Motiv-Anteil allein** (nur Gesicht + Atemluft): die
Wunschseite gilt, wenn sie genauso gesichtsfrei ist wie die beste Stelle;
Unruhe wählt nur noch die Position INNERHALB der Seite; (3) die
Seiten-Suche muss in der **Wunschzonen-Höhe** bleiben (±0.18 H) und
innerhalb der Seite gilt Motiv → Nähe zur Wunschmitte → Kosten. Sonst
erkauft sie sich die Seite mit einer falschen Höhe oder klebt an der
Fensterkante zur Mitte. Das v143-Ausweichen bleibt unberührt: steht die
Person auf der Wunschseite, fällt die Seite zurück.

### Seite + Streuung (v153)
`_mix01` ist der **32-Bit-Finalizer**, nicht eine einzelne Multiplikation mit
`& 1023` — die lief fuer kleine Vielfache als lineare Rampe, jeder
"deterministische Wechsel" fiel damit immer gleich aus.
Die **Wunschseite ist ein Tiebreaker, keine Kraft**: `wunsch_x` wirkt nur an
Stellen ohne Motiv-Beruehrung. Als Kosten-Term uebertoente sie das
Gesichts-Ausweichen — zweimal gemessen, zweimal falsch. Ein Seitenwechsel
setzt die Hysterese zurueck (sie ist gegen Zittern da, nicht gegen Regie).

### Randabfall + satzweise Collage (v152)
Der Anschnitt am Satzende gilt nur bis **5 Zeichen** — bei 7 frisst er die
Randglyphen und das Wort ist unlesbar (am Render gemessen). Das
angeschnittene Wort darf die **Blockbreite nicht bestimmen** und wird auf die
Bildmitte zentriert.
Die satzweise Collage schluckt Folgegruppen über `used`; die **Chunk-Bildung
bleibt unangetastet**. Keyword-Momente werden nie geschluckt. Passt es nicht
in 0.40 H, wird erst die Erweiterung zurückgedreht, nicht das Layout.

### Referenz anwenden (v151) — klemmen, nicht verwerfen
Ein gemessener Wert ausserhalb des Plausibilitaetsfensters wird **geklemmt**,
nie verworfen. Verwerfen heisst: der Kunde laedt eine Referenz hoch und sieht
nichts — genau das ist bei den auffaelligsten Vorbildern passiert, weil die
Fenster an einem einzigen Video geeicht waren.
**Deckel nur an EINER Stelle.** `_apply_reference_params` entscheidet;
`compose_flow` sichert danach nur noch gegen Unsinn. Zwei Deckel
hintereinander halbieren die Wirkung, ohne dass es im Code auffaellt.
Jeder Messwert, den `_reference_params()` durchreicht, muss auch angewandt
werden — sonst ist er Zierde. Gegenprobe: Schluessel aus `_reference_params()`
gegen die Nutzung in `_apply_reference_params` diffen.

### Abwechslung im Satzbild (v150)
Ein Filler-Chunk bekommt NICHT mehr immer dasselbe Zeilenraster. `compose_flow`
kennt zwei Anordnungen (`layout='flow'|'collage'`): die Collage setzt kleine
Woerter links in eine Spalte und treppt die Inhaltswoerter rechts daneben nach
unten, jedes in eigener Groesse; eine Verbinder-Kette laeuft in Schreibschrift
mit. Der Wechsel ist **deterministisch** (`_mix01`), nie zufaellig — ein
Re-Render muss dasselbe Bild ergeben.
Sperren, die man nicht aufweichen darf: verengte Spalte (Nahaufnahme) → immer
Zeilensatz; Collage über 0.40 H → Rückfall auf Zeilensatz; `clean` bleibt
schlicht. Schwelle ist `len(g) >= 3` — mit 4 lief die Collage im echten Render
gar nicht an.
Der Schlusswort-Knall (`punch`) greift nur am Satzende und ist auf 0.89 W
gedeckelt, weil der Block bei x0 = 0.07 W ansetzt.
**Bei jeder Änderung hier einen Frame-Streifen rendern.** Zwei der drei Fehler
in v150 waren in der Komposition unsichtbar und erst im fertigen Bild zu sehen.

### Referenz-Funktion (v144) — gemessen, nicht geschaetzt
`measure_reference_video()` in `render.py` liest den Stil eines hochgeladenen
Vorbilds direkt aus Bild und Ton — deterministisch, ohne KI, ohne API-Key.
GPT-5 Vision liefert nur noch die Prosa-Beschreibung; alle wirksamen Zahlen
kommen aus der Messung. Erkennung von Schrift: Fuellgrad 0.14-0.74,
Strichbreite 0.06-0.40 der Zeichenhoehe, Zeilen-Bindung, zeitliche
Wasserzeichen-Karte (>85 % gleiche helle Stelle = Logo), Textband in zwei
Durchgaengen. **Das Band muss wachsen**: das 70-Prozent-Fenster findet nur die
schwerste Stelle, ein fettes Schluesselwort draengt die Fliesstext-Zeile sonst
heraus und das Groessenverhaeltnis wird 1.0. Gewachsen wird nur entlang echter
ZEILEN (>= 2 Teile auf einer Grundlinie), max. 1.6 Zeilenhoehen je Schritt,
Deckel 0.40 H.
Angewendet werden (`_apply_reference_params`): Kamera, `chunk_hold_min`,
SFX-Pegel, `caption_zone`, `caption_align`, `caption_glow`, `caption_outline`,
Akzentfarbe, `caption_scale`, `caption_hierarchie`. Groessen wandern als
Anteil der BILDHOEHE (Formatausgleich `pf` bleibt davor), Umrechnung ueber
cap/em 0.70 und x-Hoehe/em 0.52, beides gedeckelt.
**Kein API-Key noetig** — `analyze_reference_video` misst zuerst und liefert
auch ohne OpenAI einen Eintrag. `/api/style/learn` darf deshalb kein 503 mehr
werfen. Der Kunde sieht die Messung im Konto als Klartext-Zeile (`gemessen`,
englisch); Rohdaten bleiben auf dem Server.
**Testvideos fuer die Messung nie mit `cv2.putText` bauen** — Hershey-Schriften
haben weder Punzen noch Antialiasing und besitzen die geprueften Merkmale gar
nicht. Echte Schriftdateien nehmen, Captions wechseln lassen (stehender Text
gilt sonst als Wasserzeichen), Stoerer wandern lassen.

### Typografie-Regeln aus der Referenz (v143, gemessen)
- Jeder Look setzt **eigene** `fonts.support`. Stammbreite/Versalhöhe ≥ 0.20
  (Referenz 0.22). `sans_l` = 0.102 ist nur für `clean` richtig.
- Schlüsselwort nimmt die **Display-Schrift des Looks** (`fonts.strong`
  übersteuert), nicht mehr hart `poppins_b`.
- Versalhöhe Schlüsselwort zu x-Höhe Kleintext = **2.2 bis 2.6**.
- Die Referenz **füllt die Spalte nicht**: groß ansetzen, nur lange Wörter
  schrumpfen lassen. Eine "Spalte füllen"-Funktion ergibt 3.1× und ist falsch.
- Querformat **vergrößert** (`pf` 1.35), es verkleinert nicht. Alle anderen
  Composer gleichen die kurze H-Kante um 1.68 bis 2.00 aus.

## Animationen (26 Stück, Stand 2026)
Alle über zentrales `anim_apply()` routen (Beat-Sync + Motion-Blur legt es
oben drauf). Kern in `_anim_core`. Qualitätsmaßstab (v100): Federn mit
Overshoot statt ease_out, Anticipation→Impact→Settle statt Endlos-Drift,
Envelope-Follower statt rohem Audio, verwürfelte Staffelung statt linearer
Muster, Tremor statt Weißrauschen. Keine Anim darf mechanisch/synthetisch/
1-Frame-zufällig wirken. Katalog: `ANIM_LIST`; Keyword→Anim-Heuristik
`ANIM_HINTS`/`anim_for` (DE+EN, an Satzgrenzen gekappt via `anim_ctx`).

## Aufloesung (v149)
`output.height` ist das Zielmass der **kurzen Kante**, nicht der Bildhoehe
(hoch 1080x1920, quer 1920x1080). `output.quality: 4k` hebt es auf 2160.
Es wird **nie hochskaliert** — `H = min(H, src_h)`. 4K kostet im Web-Produkt
den doppelten Credit-Satz und wird nur berechnet, wenn die Quelle mindestens
1440p kurze Kante hat (`_will_uhd`). **`_will_uhd` muss BEIDE Wege kennen** —
`quality: 4k` und `height >= 2160` (die UI schickt seit v157 die Hoehe).
Wird 4K abgelehnt, muss auch die HOEHE zurueckfallen, sonst rechnet die
Engine gross und der Kunde zahlt den einfachen Satz. Der gezahlte Betrag steht als `cost_sec`
am Job; Erstattungen gehen ueber `_job_cost(j)`, nie ueber `cost_seconds(dauer)`.

## Sprache der Ausgaben (v148)
`render.py` schreibt seine `print()`/`sys.exit()`-Meldungen **englisch** — der
Job-Log landet im Web-Produkt beim Kunden. Kommentare und Docstrings bleiben
deutsch. Wer eine Log-Zeile aendert, muss BEIDE Leser mitziehen:
`web/server.py` (Fortschritts-Phasen, `_parse_refs_line`, `ERROR:`-Erkennung)
und `gui.py` (Desktop-Statuszeile). Die alten deutschen Marker stehen als
Fallback daneben — gecachte Logs von vor v148 sollen weiter lesbar bleiben.

## Betriebs-Meldungen (v147)
Render-Fehler und Job-Timeouts gehen **nicht** mehr per Mail raus, sondern nur
in die Tabelle `alerts` und den Admin-Tab **Alerts**. `_notify_admin(...,
mail=False)`. Echte Betriebsstoerungen (Platte knapp, Ghost-Buy, Stripe)
mailen weiter. Routine-Post (Backup) wird gar nicht protokolliert.

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
  Motion-Clip pauschal 1 Cr (MP4; Motion-ProRes-Alpha existiert seit v118 nicht
  mehr). Caption-Alpha-Layer = eigener Render, kostet erneut pro angef. Min.
  Free 3 Min/Monat + Wasserzeichen
  bis zum ersten Kauf. Willkommens-Guthaben (120s) erst NACH E-Mail-Verify.
- **Bewusst NICHT bauen** (Fokus, aus Konkurrenz-Analyse): kein Abo/Hybrid,
  kein AI-B-Roll, kein Clipping/Avatare, kein Sprachen-Wettlauf, kein
  Feature-Stacking. Positionierung: Finishing-Tool nach dem Schnitt.
- Sicherheit: WAL+busy_timeout, `--proxy-headers` (IP-Rate-Limits), Credits
  atomar+idempotent, Ownership-Checks, Upload-Caps, jid-Path-Traversal dicht,
  Stripe-Webhook-Secret-Pflicht. Konto-Löschung: Kaufbuchungen → `ledger_archive`
  (GoBD/§147 AO 10 Jahre; DSGVO Art.17(3)(b)), Rest echt gelöscht.
- **Performance (v142, nicht wieder aufweichen):** alle heißen Queries laufen
  über Indexe — Selftest prüft per `EXPLAIN QUERY PLAN`, dass KEINE davon
  scannt. Caching in drei Ebenen: Prozess-Datei-Cache (mtime-invalidiert),
  ETag+304 auf HTML/Assets, 20s-TTL nur auf Admin-Aggregate (Middleware
  verwirft ihn bei jedem Schreibzugriff). **Geld/Kontostand nie cachen.**
  Blockierende Aufrufe in `async def`-Endpunkten sind ein Fehler (legen den
  ganzen Server still) → `asyncio.to_thread`. Sync-`def`-Endpunkte bleiben
  sync (FastAPI-Threadpool, korrekt für SQLite).
- **Recht & Steuern (Admin-Tab, v142):** `/api/admin/compliance/tax` bündelt
  Steuer-Identität, §19-Schwellen-Ampel (Vorjahr 25.000 €, laufend 100.000 €,
  Warnung ab 80 %), Umsatz je Jahr/Monat, Belege, Aufbewahrungsfristen und das
  Verarbeitungsverzeichnis (Art. 30 DSGVO). Übersicht, KEINE Steuerberatung.
- Betrieb: `/api/health` (für externen Uptime-Pinger), Admin-Störungsmails
  (1/h/Schlüssel), Watchdog killt hängende Renders (45min) + erstattet,
  Offsite-DB-Backup per Mail, Warm-Preview-Daemon (~0.5s statt 2s).
- OFFEN (Ismet): Demo-Video in den Hero, UptimeRobot auf /api/health,
  Kontaktadresse vereinheitlichen. **Stripe läuft LIVE.**

## Selftest — Ablauf (Pflicht vor jedem Deliver)
Gesamt **1117/1117 grün (Stand v183)** + Renders 7/1/5/2 + GUI. Läuft nur unter Linux/CPU mit
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
  Stille ist besser als billiger Ton. Ohne `sfx/pack` liefe alles STUMM —
  der Pack IST da (14/14 Slots, v175 geprüft), also klingt es.
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
- Windows-Test mit echtem Material + Maskenqualität 'hoch' + MOV-Import Premiere.
- Semantik-Regie & v100-Animationen auf ECHTEM Material verifizieren (hier nur
  Heuristik/CPU/synthetisch getestet).

**ERLEDIGT, nicht mehr als offen behandeln (v175, am Repo/Live geprüft):**
- **Sound-Pack liegt vollständig im Repo**: `sfx/pack` 14/14 Slots belegt
  (impact, whoosh, whoosh_soft, riser, tick, counter, boom, crack, fall,
  rise, turn, press, vanish, slam), Manifest `pack.json`, alle mit Ismets
  eigener Lizenz. Prüfen mit `python -c "import sfx_pack; print(sfx_pack.pack_status())"`.
  Videos sind NICHT stumm.
- **Stripe ist im Live-Modus** (Ismets Bestätigung). Keine Live-Umstellung
  mehr planen oder als offenen Punkt nennen.
