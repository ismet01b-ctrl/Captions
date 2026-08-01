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
5. **Sicherheit wird beim Bauen mitgedacht, nicht nachträglich auditiert**
   (Ismets Ansage, Juli 2026). Wer einen neuen Endpunkt baut, beantwortet
   BEVOR er ihn abgibt: Wer darf ihn aufrufen, und wo steht die Prüfung?
   Gehören die Daten dem Aufrufer (Ownership/IDOR)? Was kostet ein Aufruf
   den Server, und was passiert bei tausend (Rate-Limit)? Fließt ein
   Parameter in einen Dateipfad, eine Kommandozeile oder SQL? Landet
   fremder Text irgendwo im HTML — **auch im Admin-Panel** (dort liegt der
   Admin-Key im sessionStorage, ein vergessenes `esc()` ist Kontoübernahme
   per Support-Ticket)? Wird die Aktion protokolliert? Der Selftest bekommt
   für jede dieser Antworten einen Test — Sicherheit, die nur im Kopf des
   Autors stand, ist beim nächsten Umbau weg.
   **Je mächtiger die Aktion, desto mehr als nur der Admin-Key.** Seit v197b
   kann ein einziger Endpunkt alle Konten ersetzen (`backup/upload`); das ist
   eine andere Klasse als "Daten lesen" und verlangt eine eigene Schranke.
6. **Ehrlich bleiben.** Tests laufen hier auf Linux/CPU mit synthetischem
   Material und OHNE OpenAI-Key (Heuristik-Pfad). Echte GPU-/KI-/Qualitäts-
   wirkung sieht Ismet erst auf Windows bzw. live auf douchko.eu mit echtem
   Material — das immer klar sagen, nie so tun als sei es final verifiziert.

## ERST FRAGEN, DANN BAUEN (Ismets Ansage, 31.07.2026, "merk dir das fuer
## immer")
Vor JEDER Aenderung am Verhalten oder an der Optik: kurz fragen, was gewollt
ist. Nicht loslegen, weil ein Befund plausibel aussieht. Ein Befund ist eine
FRAGE an Ismet, keine Arbeitsanweisung an mich — was wie ein Fehler aussieht,
kann gewollt sein (Beispiel: zwei Fliesstext-Bloecke gleichzeitig im Bild sind
in Ordnung; v230k hat das ungefragt "repariert").

## MEINE WIEDERKEHRENDEN FEHLER — vor JEDEM Deliver durchgehen
(Ismets Ansage, mehrfach: "Lerne aus allen deinen Fehlern.") Diese Liste ist
keine Sammlung von Anekdoten, sondern eine **Checkliste**. Jeder Punkt ist
mindestens zweimal wirklich passiert und hat Ismet Zeit, Geld oder einen
Render gekostet. Neue Fehler kommen HIER dazu, nicht nur in den
Versions-Abschnitt.

1. **Ein Schutz darf begrenzen, niemals wegwerfen.** Eine Allowlist, ein
   Filter, ein Sanitizer: unbekannte Werte klemmen, nicht entfernen. Ein
   stiller Wegfall schaltet ein Feature ab, ohne Meldung und ohne Test
   (v230f `caption_zone`, v210 vier tote KI-Systeme). Wenn Entfernen wirklich
   nötig ist, muss es protokolliert oder getestet sein.
2. **Erst den echten Pfad LAUFEN LASSEN, dann behaupten.** Quelltext lesen,
   greppen und "sieht richtig aus" haben mich mehrfach getäuscht: v230d
   (`(_current_user(r) or {}).get('id')` wirft AttributeError auf einer
   `sqlite3.Row`), v218 (toter Code im falschen Zweig), v193 (Plan trug den
   Wert, im Bild passierte nichts). Der Beweis ist der Aufruf plus eine
   Messung, nie die Textsuche.
3. **Prüfen, ob ein bestehender Test die REGEL schützt oder den FEHLER.**
   Dreimal einen Test angetroffen, der genau das Kaputte festschrieb
   (v230f "unbekannte Zahl fliegt raus", v230d der `str`-Vergleich beim
   Admin-Key, v222 `_al is None or _al > 7`). Wer einen Test anpassen muss,
   um seinen Fix grün zu bekommen, prüft zuerst, welcher von beiden recht hat.
4. **Ein Riegel gehört in die Funktion, nicht an EIN Gate.** Erst ALLE
   Aufrufer suchen. v230d gleich dreimal (`check_auth` 1 von 7,
   `resend_verification`, `/admin/codes`), davor v159/v170/v176.
5. **Qualität ist nie die Währung.** Renderzeit, Kosten und Bequemlichkeit
   dürfen nie gegen die Regie oder die Optik getauscht werden — v228d
   (`reasoning_effort: low`) war genau dieser Tausch und Ismets Antwort war
   "Qualität ist sehr schlecht geworden". Erst messen, WELCHER Schritt
   teuer ist; nur echte Leerarbeit darf weg.
6. **Vergleiche müssen ausgerichtet sein.** Ich habe Ismet gesagt, der
   Bildfehler stecke in seinem Quellvideo — falsch, weil ich durch ein
   festes Fenster gemessen habe, während die Kamera 3 % zoomt. Erst nach
   SIFT-Ausrichtung war die Wahrheit sichtbar. Vor jeder "das war schon
   vorher so"-Aussage: ausrichten, sonst nichts sagen.
7. **Der eigene Testaufbau ist auch Code und hat Fehler.** Synthetische
   Fälle brauchen die ECHTEN Größenverhältnisse (ein 320x240-Testbild
   beweist nichts über 720x1280), Messfenster müssen dort liegen, wo der
   Effekt ist, und Werkzeuge haben eigene Fallen (`schneide()` verlor das
   `async`, ein früherer Abschnitt ersetzte `setTimeout` durch eine
   Warteschlange). Symptom: der Test ist grün und misst nichts.
8. **Eine Regel, die Zeiten ändert, darf nur kürzen.** Verlängern beseitigt
   die Überschneidung in den Zahlen und erzeugt sie im Bild (v216/v217).
   Und jede neue Zeit-, Bewegungs- oder Platzierungsregel muss zuerst
   beantworten, was sie mit einem `intent`-Moment macht (v214/v226).
9. **Vor der Ursachensuche prüfen, WELCHE Fassung lief.** Build-Stempel im
   Video (`ffprobe -show_entries format_tags`) bzw. Panel-Ansicht Build.
   Drei Runden gingen verloren, weil der Stempel log (v222/v225c).
10. **Sagen, was NICHT bewiesen ist.** Kein "gefixt", wenn nur ein
    Ersatzpfad grün ist; nicht reproduzierbar heißt: nicht reproduzierbar
    (v230e Renderer-Absturz). Lieber eine Zeile Unsicherheit als eine
    Runde umsonst.

## Kommunikation
Ismet ist direkt und terse. **Effizienzmodus:** keine Floskeln, kurze klare
Sätze, nur Code + exakte Schritte. Technische Tiefe bleibt voll erhalten,
nur Füllmaterial weg. Korrektur ohne Rechtfertigung annehmen. Bei visuellen
Änderungen: Beweis liefern (Frame-Streifen / Beispiel-Video), nicht behaupten.

**HARTE OBERGRENZE: 5 ZEILEN (Ismets Ansage, 29.07.2026, "nie wieder so
viel schreiben, fuer immer").** Ergebnis + was zu tun ist, sonst nichts.
Keine Ueberschriften, keine Aufzaehlung der Befunde, keine Beweisketten,
keine Ursachen-Erklaerung, keine Ehrlich-Grenzen-Absaetze - das steht
alles im Commit und in PROJEKT_STATUS.md. Details NUR auf Nachfrage.
Wer beim Schreiben denkt "das muss er noch wissen": nein, muss er nicht.

**KURZ UND KNACKIG (Ismets Ansage, Juli 2026).** Antworten so kurz wie
möglich. Keine langen Analysen, keine Aufzählung von Nebenbefunden, kein
Wiederholen dessen, was er schon weiß. Ergebnis zuerst, Details nur auf
Nachfrage. Gilt auch für Deliver-Summaries.

**SEHR KURZ + FÜR LAIEN — das ist EINE Regel (Ismet hat sie mehrfach
wiederholt).** Der Standard ist eine Handvoll Zeilen, nicht eine Seite. Auch
ein Audit mit 30 Befunden wird zu vier Sätzen: was war offen, ist es zu, was
ist noch offen. Tabellen, Aufzählungen von Nebenbefunden und Belegketten nur
auf Nachfrage. Wer sich beim Schreiben denkt "das gehört noch dazu", liegt
fast immer falsch — es gehört in den Commit, nicht in die Antwort.

**FÜR LAIEN ERKLÄREN (Ismets Ansage, Juli 2026 — gilt dauerhaft).** Ismet ist
kein Entwickler. Erklärungen kommen ohne Fachwörter: was ist es, was heißt das
für ihn, was kostet es ihn wenn nichts passiert. Ein Bild statt eines
Fachbegriffs ("das Videoprogramm hat den Generalschlüssel" statt "Container
läuft als root"). Fachbegriff höchstens in Klammern dahinter, damit er ihn
wiedererkennt, wenn er ihn woanders liest. Das gilt für ALLES — Sicherheit,
Technik, Recht, Betrieb —, nicht nur für Zusammenfassungen. Die technische
Tiefe bleibt in Code und Commit-Nachricht, nicht in der Antwort an ihn.

**Geschäftlich: KNALLHART (Ismets ausdrückliche Ansage, Juli 2026).**
Rolle bei Business-Fragen ist Mitgründer/Investor, nicht Dienstleister.
Nicht zustimmen, wenn etwas falsch oder dumm ist. Kein Trost, kein
Schönreden, keine höfliche Umschreibung. Wenn er sich im Kreis dreht:
das benennen, auch wenn es unangenehm ist. Neue Produkt-Ideen sind NUR
dann eine Antwort, wenn das aktuelle Problem wirklich am Produkt liegt
und nicht am Vertrieb.

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
- `web/admin.html` — Ops-Konsole. **Navigation ist EINE Quelle** (`NAV`,
  gruppiert; `TABS` wird daraus abgeleitet). Wer eine Ansicht ergaenzt, traegt
  sie in `NAV` ein und legt ein SVG in `ICON` — keine Emoji als Symbole.
  Grid-Kinder brauchen `min-width:0`, sonst schiebt eine breite Tabelle die
  ganze Seite quer.
- `web/imprint/privacy/terms.html`, `web/codes.py`.
- `Dockerfile`, `docker-compose.yml` (app + caddy), `autodeploy.sh`, `update.sh`,
  `deploy_gate.sh` (Selftest im neuen Image vor dem Umschalten), `restore.sh`
  (users.db zurueckspielen, mit Kandidaten-Pruefung + Sicherheitskopie).

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
- **Der Wortschatz muss die KUNDENSPRACHE treffen (v209).** `_self_ref_intent`
  erkennt eine Ansage nur, wenn ein Bezugswort auf die Captions im Satz steht.
  Bis v208 waren das nur caption/subtitle/word/text - und in Ismets eigenem
  Werbespot wurde deshalb KEINE der drei Ansagen umgesetzt, weil er "this next
  LINE" und "this ONE" sagt. Ergaenzt: line/zeile/satz/one (+ Bestimmungswort
  bis zwei Woerter davor, "this NEXT line"). Gegenprobe ist Pflicht: "the guy
  behind me was loud" darf NICHTS ausloesen. Lehre: ein Wortschatz, der die
  haeufigste Formulierung nicht kennt, ist derselbe Fehler wie ein Riegel am
  falschen Gate - das Feature ist gruen getestet und trifft trotzdem nie.
  Wer hier etwas ergaenzt, testet mit einem ECHTEN Sprechtext, nicht mit dem
  Lehrbuchsatz.
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

### KI-Aufrufe (v210) — ein stiller Fallback verdeckt einen Bug
- **`render.py` importiert `requests` in JEDER Funktion lokal.** In
  `ai_flow_direct` fehlte die Zeile: die KI-Textaufteilung starb bei JEDEM
  Kundenrender an einem NameError und fiel still auf die Heuristik zurueck.
  Wer eine neue KI-Funktion baut, braucht einen Test, der ohne echten
  Schluessel prueft, dass sie NICHT mit NameError endet.
- **Bei gpt-5/o-Serie zaehlen die DENK-Tokens in `max_completion_tokens`.**
  Ein knappes Budget wird vom Denken aufgebraucht, die Antwort kommt LEER -
  im Log als JSONDecodeError. So fielen Bild-Regie, Objekt-Anker und
  Stille-Score aus. `_oai_json` setzt fuer neue Modelle 2500 als Untergrenze.
- **Ein Fallback, der jeden Fehler schluckt, macht aus einem
  Programmierfehler ein Feature, das niemand vermisst.** Vier Systeme waren
  monatelang aus, ohne dass ein Test oder ein Kunde es merkte.
- **Und 2500 haben nicht gereicht (v230p).** Dieselben zwei Systeme fielen
  in Ismets v230l-Log wieder aus. Die Antwort war nicht kaputt, sie war
  NICHT DA: `finish_reason='length'`, Inhalt leer, das Denken hatte das
  ganze Budget. Ein JSONDecodeError nennt diesen Grund NICHT. Jetzt geht
  jeder Aufruf ueber `_oai_text` — eine leere Antwort wird EINMAL mit
  doppeltem Budget wiederholt, danach nennt die Meldung finish_reason,
  Budget und Denk-Tokens. Das Budget waechst ausserdem mit dem Umfang
  (+260 je Bild, +90 je Textblock). Merksatz: wer eine Fehlermeldung baut,
  fragt, ob sie die URSACHE nennt oder nur das Symptom.

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

### Animationen pruefen (v194) — Name ist eine Zusage
`anim_apply()` ist eine REINE FUNKTION auf einem Sprite. Wer eine Animation
pruefen will, ruft sie direkt ueber eine Zeitreihe auf und misst — kein
Video noetig. Gemessen wird die TINTE (Breite, Hoehe, Teile, Streuung,
Strichstaerke ueber Distanztransform), nicht das Sprite-Rechteck.
- **Einseitig polstern ist ein Positionsfehler.** Wer die Leinwand nur auf
  einer Seite wachsen laesst, verschiebt den fertigen Text um die halbe
  Polsterbreite — der Zeichenpfad setzt das Sprite mittig. `regen` sass
  53 px zu hoch, `rutsche` 92 px zu weit links. `explosion`/`magnet`
  polstern symmetrisch und sind der Massstab.
- **`_persp3d(arr, ax, ay)`: ax = Querachse (nach vorn kippen), ay =
  Hochachse (umblaettern).** Vertauscht macht `kippen` dasselbe wie `wende`.
- **`spring()` endet frueher, als die Zeitkonstante suggeriert.** Sie
  erreicht 1.0 beim ersten Kosinus-Nulldurchgang, also bei x = 1/(2*freq) —
  nicht bei x = 1. Fuer monotone Rampen (Blur, Kippung) ist sie das falsche
  Werkzeug; dort gehoert `smoothstep` hin.
- **Ganzzahlige Morphologie-Kernel quantisieren einen Regler tot.**
  `k = int(round(amt*4)) | 1` ergab fuer die ganze Bass-Spanne denselben
  Kernel. Zwischen zwei Kernelgroessen mischen.
- **Neun Animationen sind AUDIO-getrieben** (glitch, puls, welle, zittern,
  neon, schub, druck, gewicht, wackel). Mit einem konstanten Audio-Wert
  gemessen stehen sie still — das ist ein Messfehler, kein Bug. Immer ein
  sprech-aehnliches Signal anlegen.
- **Ein Fingerabdruck aus der Alpha-SUMME ist blind fuer Verformung.**
  Eine Welle verschiebt Tinte nur seitlich; die Summe bleibt gleich. Form
  messen (Zeilen-/Spaltenprofil), nicht Menge.
- **Nicht jeder Restversatz ist ein Fehler:** `sturz` bleibt unten liegen,
  `anstieg` oben — das ist ihre Bauart. Dauer-Animationen (schweben,
  wackel, puls, welle) sind bei einer Stichprobe einfach mitten in ihrer
  Schwingung.

### Block-Editor (v193) — "eine Zeile, ein Block, und die Einstellung gilt"
`_bloecke.json` ist die **Quelle der Chunk-Bildung**, kein Nachschlagen
obendrauf. Liegt ein Nutzerplan vor, gibt `groups_for` ihn zurueck und
`build_groups` laeuft gar nicht erst — eine Aufteilung, die danach vom
Merge-Pass wieder zusammengelegt wird, ist keine.
- **Ein Block hat nur ueber den Wortbereich Identitaet.** Der alte Weg
  (Schluessel = erster Wortindex einer FRISCH berechneten Aufteilung, so wie
  `flow_map`) verfaellt still, sobald sich eine Grenze verschiebt. Weil der
  Nutzerplan die Gruppen SELBST bildet, kann sein Schluessel nicht danebenzeigen.
- **Acht Gates muessen den Nutzer-Block kennen** (`_ublk` / `_bl_akt`):
  B-Roll, Atempause, Ein-Wort-Rest, Dichte-Weiche, Satz-Collage,
  Luecken-Netz, Schnitt-Disziplin, Beat-Grid. Wer ein neues Gate baut, haengt
  den Riegel dort hin. Die Dichte-Weiche ist die gefaehrlichste: mit
  'akzente' (Standard) verschwaende der Block sonst ohne jede Meldung.
- **Das Luecken-Netz ist bei Nutzer-Bloecken AUS.** Die Zusage "jedes Wort
  steht im Bild" gilt der Automatik, nicht gegen eine Loeschung.
- **Eine Block-Animation braucht den GANZEN Block im Bild (v194a).** Ein
  Fliess-Block baut sich Wort fuer Wort auf; eine Animation von 0.2 bis
  0.6 s ist vorbei, bevor das dritte Wort da ist - sie lief nur auf dem
  ersten Wort und dort drei Bilder lang (am Render gemessen: Unterschied
  4.2 bei 3.28 s, ab 3.38 s noch 0.3). Bei gesetzter Animation steht der
  Block deshalb ab seinem Beginn ganz da. Ohne Animation bleibt der
  Karaoke-Aufbau.
- **Eine Einstellung am PLAN nachzuweisen reicht als Test NICHT.** Genau
  daran ist v193 vorbeigelaufen: der Plan trug `anim`, im Bild passierte
  nichts. Der Beweis ist der Unterschied im gerenderten Bild ueber das
  ganze Zeitfenster.
- **Fliess-Bloecke konnten bis v192 gar nicht animieren** — alle neun
  `anim_apply`-Aufrufe hingen an `p['arr']` (Keyword-Karten). Der
  Fliess-Pfad hat jetzt einen eigenen Aufruf: **eigener Zustandstraeger je
  Wort, gemeinsame BLOCK-Zeit**. Ein gemeinsames dict waere falsch,
  `_anim_core` haelt seinen Zufallszustand am Objekt und wuerde je Frame
  N-mal weitergetickt.
- **Groesse ist NICHT power.** Power ist Dramaturgie (Kamera, SFX,
  Tempo-Kurve, `pace_power_map`), Groesse ist der Schriftgrad. Beides in
  einen Regler zu legen waere der v155/v156-Fehler. Der `groesse`-Parameter
  muss an ALLE VIER `compose_flow`-Aufrufe (auch Rueckfall und Luecken-Netz).
- **Der Analyse-Lauf muss die Bloecke exportieren**, bevor `--plan-only`
  aussteigt — und mit derselben `groups_for`-Konfiguration wie der
  Voll-Render, sonst zeigt der Editor eine andere Aufteilung als das Video.
- **Serverseitig sanitisieren** (`sanitize_blocks`), nicht erst in der
  Engine. Und **pro Eintrag fangen**: ein kaputter Wert darf nie den ganzen
  Plan verwerfen (genau das passiert bei `_momente.json`).
- **`_flow3.json` muss mit weg**, wenn sich Blockgrenzen oder das Transkript
  aendern. Sonst zeigen die gecachten Anker auf den falschen Chunk und
  verfallen still.
- Mitgenommene Alt-Fehler: der Momente-Roundtrip verlor `anker` und
  `user_pick` bei JEDEM Render; `p['power']` wurde nie an einen Plan
  geschrieben (sieben Leser bekamen konstant 2, sechs Effekte liefen nie an).

### Schriftgroessen (v154)
Das **Schluesselwort und der Fliesstext haben getrennte Referenz-Faktoren**
(`caption_scale` aus `key_hoehe`, `caption_scale_klein` aus `klein_hoehe`).
Den Fliesstext ueber key_hoehe mal Hierarchie abzuleiten war der Grund, warum
eine Referenz mit grosser Punchline den ganzen Satz aufblies.
Hausmass aktuell (v192): **0.089 em Schluesselwort, 0.043 em Fliesstext**
(v154 stand auf 0.076/0.034, v184 auf 0.105/0.050). **Wer daran dreht,
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

### Regler + behind-Wort (v191)
- **Ein Regler-Fallback darf nie mit der Anzeige-Skala multipliziert
  werden.** `min` als Rohwert x 100 ergab "6000 %" und "14000x". Regler
  ohne Config-Eintrag brauchen `data-default` in ANZEIGE-Einheiten, und
  der Selftest prueft jeden Regler gegen seinen Bereich.
- **Verdeckt wird von der SILHOUETTE, nicht vom Kopf.** Der
  Lesbarkeits-Riegel fuer `behind` verglich mit 1.7x Gesichtsbox;
  ausgestanzt wird die ganze Person inklusive Schultern (~2.6x). Ein Wort
  kann klar breiter als der Kopf sein und trotzdem in der Mitte
  zerschnitten werden (gemessen 28 % am Stueck). Drei Stufen:
  vergroessern ueber die Schultern, sonst auf KOPFHOEHE heben, sonst ueber
  den Kopf legen.

### Ruhe im Bild (v190) — erst messen, dann abschalten
Ismets "alles zu sehr am Zucken" wurde GEMESSEN, nicht geraten, und die
naheliegende Vermutung war falsch: mit Beat-Sync, Kamera, Aktivwort-Pop
und Motion-Blur AUS blieb die Unruhe unveraendert (3.09 statt 2.84
Promille je Frame). Ursache war der Wort-EINFLUG: 2 % Bildhoehe von
unten, von 86 % skaliert, mit ease_back-Ueberschwingen.
- `effects.caption_ruhig` (Standard an): Woerter erscheinen an ihrer
  Endposition, kein Sprung, kein Overshoot, Scale ab 0.97, laengere
  Blende. Pop und Settle gedaempft, Abdimmen ueber 0.25 s statt als
  Helligkeitssprung. Alt-Verhalten bleibt ueber den Schalter erreichbar.
- **Der Rest ist EREIGNISDICHTE, kein Fehler:** alle 0.3 bis 0.4 s ein
  neues Wort, alle rund 1 s ein neuer Block. Wer mehr Ruhe will, dreht an
  `chunk_hold_min` und `words_per_group`, nicht an der Animation.

### Schriftwahl + Umriss (v189)
- **Eine Nutzer-Schriftwahl gilt fuer den GANZEN Satz.** Die Font-Kachel
  setzt display, support, italic und strong. Nur `fonts.display` zu setzen
  ergab zwei Schriften im selben Block (Schluesselwort gewaehlt,
  Fliesstext vom Preset). Die Schreibschrift bleibt ein eigener Schnitt.
- **Der Umriss gehoert dem Fliesstext, nicht dem grossen Wort.** Dort
  traegt die Flaeche den Kontrast; der Saum wirkt plakativ. Schalter
  `effects.caption_kontur_key` (Standard aus), Parameter `kontur=` an
  `Sprites.text`. Wer Groessen misst, muss den hellen GLYPHENKOERPER
  nehmen - eine Alpha-Box vergleicht sonst Glyphe gegen Glyphe-plus-Saum.
- **Auto-Motion-Grafik bleibt AUS** (`accents.auto`). In den High-End-
  Referenzen gehoert sie zu einer Agentur-Produktion mit Multikamera und
  Schnitt; im nackten Talking-Head ist sie ein Fremdkoerper. Was der
  Nutzer im Momente-Editor anlegt, wird weiterhin gerendert.

### Plattform-Korridor + Vorschau (v186/v187)
- **Der Satzspiegel haengt am Korridor, nicht an einer Konstanten.**
  `_korridor()` liefert die zoom-bereinigte nutzbare Breite (Title-Safe,
  Button-Spalte, Kamera-Stauchung). compose_flow bekommt sie als `maxw`.
  `colw` bleibt getrennt davon die NAHAUFNAHME-Sperre - haengt beides am
  selben Parameter, greifen Randabfall und Punch-Deckel nie wieder.
- **Jeder Report muss Flow-Bloecke kennen.** `safe_zone_report` und
  `_caption_boxes` lasen cx/cy vom Plan; Flow-Bloecke tragen ihren Text in
  `front`. Beide fielen dadurch still durch (Log sagte "Button-Spalte
  frei", Akzent legte sich auf die Caption). Wer eine neue Pruefung baut,
  muss BEIDE Plan-Formen abdecken. Gemessen wird die TINTE, nicht das
  Sprite-Rechteck (bis 180 px Glow-Polster).
- **Dichte-Werte sind ein geschlossener Satz:** sparsam / akzente /
  durchgehend. 'wortweise' kannte die Engine nie und fiel in den sparsamen
  Pfad - der TikTok-Look zeigte jahrelang die Haelfte der Woerter. Neue
  Werte gehoeren an ALLE fuenf Gates oder gar nicht in die UI.
- **Der Knall ist in H gedeckelt (0.165 H), nicht nur in W.** Im
  Hochformat bleibt er bei langen Woertern unter dem Faktor 2.25 - das ist
  Physik (1080 W reichen nicht), kein Bug. Nicht mit Anschnitt erzwingen,
  v152 verbietet ihn ab 6 Zeichen.
- **Die Kontur richtet sich nach der Textfarbe.** Hart schwarz war im Look
  'clean' (feste dunkle Palette) ein dunkler Saum um dunklen Text.
- **Die Look-Vorschau kommt aus der echten Config** (`/api/default_config`,
  dieselben Hausmasse wie compose_flow). Sie zeigt bewusst nur Typografie
  und sagt das auch - eine geschoente Attrappe waere schlimmer als keine.

### Ein Moment, ein Bild + kein Wort faellt weg (v185)
- **Der Solo-Riegel rechnet mit dem AUSKLINGEN, nicht mit dem Ende.** Ein
  Plan bleibt nach `end` noch bis 0.40 s im Bild (`active`-Fenster). Mit dem
  blossen Ende gerechnet melden die Zahlen "keine Ueberschneidung", waehrend
  im Bild zwei Texte uebereinander liegen. Gedraengte Karten bekommen ein
  eigenes kurzes `aus` am Plan; die Zeichenschleife liest es.
- **Der Solo-Riegel gilt auch KARTE gegen KARTE (v209a).** Bis v209 verglich
  er nur Karte gegen Fliesstext - zwei Karten konnten sich beliebig
  ueberlagern. Bei Orts-Ansagen ist das der Normalfall: drei Saetze
  hintereinander ergeben drei Karten, und eine Karte steht laenger als ihr
  gesprochenes Wort (an Ismets Werbespot gemessen: 'ON THE WALL' 7.20-10.25
  gegen 'BEHIND ME' 7.25-8.75). Beim Aufloesen kuerzt die ERSTE nie unter
  ihre Lesezeit - stattdessen WARTET die zweite und bleibt dafuer laenger
  stehen. Eine auf 0.2 s gestauchte Karte blitzt nur auf und ist schlimmer
  als die Ueberschneidung.
- **Solange eine Keyword-Karte steht, raeumt jeder andere Textplan.** Die
  Karte hat Vorrang bis 0.80 s Mindestlesezeit, danach raeumt sie selbst.
  Vorher galt "Karte oben, Block unten" als saubere Neben-Platzierung - das
  ergab fuenf Elemente in vier Stilen gleichzeitig.
- **Dichte 'durchgehend' ist eine Zusage: JEDES gesprochene Wort steht im
  Bild.** Deshalb dort keine Atempause nach Keyword-Momenten, plus ein
  Luecken-Netz am Ende von `build_plans`. In 'akzente'/'sparsam' sind
  Textpausen dagegen die gewollte Handschrift - das Netz laeuft dort nicht.
  Der v170-Riegel (Ein-Wort-Rest nach Pause) gilt auch im Netz.
- **Keine Farb-Karaoke.** Gelb auf dem gesprochenen Wort ist der Marker des
  CapCut/Opus-Templates (Ismet: "ausgelutscht") und landet auf Fuellwoertern.
  Emphase = Groessen-Pop plus Dimmen auf 70 %, in allen Looks.
- **Wortabstand haengt am Schriftgrad** (mind. ein Drittel Geviert), Zeilen
  um das Schluesselwort brechen um, ein zu langes Wort schrumpft per `S.fit`
  in die Spalte. Ohne diese drei ragten Woerter bis 1.57 W aus dem Bild.
- **Motion-Grafik-Akzente sind wieder an** (`accents.auto`). Sie sind in den
  High-End-Referenzen tragende Elemente; dosiert werden sie von
  `sanitize_accents` (Dichte-Deckel + 3.5 s Abstand), nicht per Schalter.

### Referenz-Grammatik (v184) — der Massstab fuer "high level"
An Ismets drei Referenz-Clips gemessen (kram.visuals/migs.visuals/
johnbacog_), NICHT geschaetzt. Gemeinsame Grammatik der Vorbilder:
- **RAUMFOLGE = LESEREIHENFOLGE.** Der Cluster-Lesepfad (compose_flow,
  layout 'collage') setzt kurze Zeilen (1-3 Woerter) mit Treppen-Einzug,
  engem Zeilenfall (1.06) und gemeinsamer GRUNDLINIE je Zeile. Die alte
  v150-Anordnung (Verbinder-Spalte NEBEN der Treppe) riss Lese- und
  Raumfolge auseinander - das war Ismets "keine high level Typografie".
- **Groessen sind Referenzmass, kein Geschmack:** key 0.105 em (Versal
  ~0.074 H), Fliesstext 0.050 em (Band ~0.040 H, in allen drei Refs
  identisch), Punch 2.25x (~0.165 H). Die v153/v154-Verkleinerungen sind
  damit UEBERHOLT - wer schrumpft, muss gegen die Referenzen messen.
  **v192 ist genau so ein bewusster Schritt darunter** (Faktor 0.85 ->
  0.089/0.043 em, Ismets Ansage). Der Referenzwert bleibt der Massstab,
  die gelieferte Groesse ist eine Nutzer-Entscheidung.
- **Punch hinter der Person** (`occlude_sprite`, effects.caption_hinter):
  das Schlusswort laeuft durch die Person, die Silhouette wird pro Frame
  an der Zielposition ausgestanzt. Nur Satzende, nie B-Roll, nie bei
  angesagtem Hand-Schub. Die Zeichenreihenfolge des Frames bleibt.
- Viral-Faktoren sind auf die neue Basis umgerechnet (1.55/2.00), das
  absolute Viral-Ziel (0.163/0.099 em) ist unveraendert.

### Viral-Look (v183/v183a) — Option, NICHT das Gesicht des Produkts
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
- Viral-Groessen sind MULTIPLIKATOREN auf die Hausmasse - eine gelernte
  Referenz (caption_scale) skaliert weiter relativ, v151-Kaskade intakt.
- **v183a: KEIN Auto-Default.** Ismets Befund am Ergebnis: Versal-
  Montserrat + gelbes Karaoke-Wort ist das CapCut/Opus-Standard-Template
  ("KEINE STANDARD MUELL", v181-Briefing). "Marktniveau" heisst die
  GROESSEN und die Handwerks-Qualitaet des Markts, NICHT sein
  meistkopierter Stil. Der Look bleibt waehlbare Option (wer das Template
  will, kriegt es), steht aber nicht vorn und wird nie vorgewaehlt. Die
  Produkt-Identitaet ist Editorial - was "high level" konkret heisst,
  entscheidet Ismet (Referenzen messen statt raten).

### Lesbarkeit + aktives Wort (v181/v182)
**v199: die Kontur ist AUS** (`caption_kontur: 0`, Ismets Ansage "die
outlines bei den Schriften weg" - auch im Viral-Preset). Der Kontrast haengt
damit allein an der Textfarbe: `fit_caption_color` bekommt `kontur=False`
und kippt auf hellem Untergrund wieder nach dunkel, statt hell zu bleiben.
Auf mittelgrauem Grund ist das die schwaechere Loesung (gemessen 5.4:1 statt
weiss bei 3.0:1 - der Text wird dort also dunkel). Der Abschnitt darunter
beschreibt, warum es sie gab; die Mechanik bleibt ueber den Regler erreichbar.
Wer Tests anfasst, die die Kontur MESSEN, muss sie sich dafuer selbst
einschalten - mit der Datei-Config sind beide Faelle jetzt identisch und der
Test bewiese nichts (drei Tests sind genau darauf reingefallen).

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

## Kunden-Mails (v194b) — ein Deckel je NUTZER, nicht je Job
Die Ablauf-Erinnerung ging bis v194a pro JOB raus. Der Deckel (`expiry_mail`
im Job-State) verhinderte nur die zweite Mail zum selben Job — wer dasselbe
Video dreimal gerendert hatte, bekam drei Mails, alle in derselben Minute
(Ismets Screenshot). **Ein Deckel, der Jobs zaehlt, deckelt nichts.**
- `_expiry_sammeln` sammelt, `_expiry_mails` verschickt gebuendelt: EINE
  Mail je Nutzer mit allen ablaufenden Videos.
- Zusaetzlich `mail_log`-Schluessel `expiry-YYYY-MM-DD`: hoechstens eine
  Ablauf-Mail pro Nutzer und Tag.
- **Ein Tages-Deckel deckelt bei taeglicher Nutzung nichts (v194c).** Videos
  laufen laufend ab; wer taeglich rendert, bekaeme taeglich Post. Richtig
  sind zwei Riegel: **aktive Nutzer** (Login oder Job in 48 h) bekommen die
  Erinnerung gar nicht, und der Abstand ist eine ganze Aufbewahrungs-Periode
  (`_mail_abstand_ok`, rollend statt Tagesschluessel).
- **Listen in Mails deckeln.** Zehn Zeilen, dann "and N more"; gleiche Namen
  ueber die GANZE Liste gruppieren, nicht nur nebeneinanderliegende.
- Wer eine neue Kunden-Mail baut, deckelt sie ueber `_mail_abstand_ok(uid, …)`
  bzw. `_log_mail_once(uid, …)` und prueft, ob der Empfaenger ueberhaupt
  weg war. Ausnahme: der Kaufbeleg ist ein Rechnungsdokument und geht pro
  Kauf raus.

## Reichweite messen (v208) — Trichter ohne Cookie
Sechs Stufen (`_TRICHTER_STUFEN`): besuch -> app -> konto -> upload ->
fertig -> kauf, dazu die Herkunft. Panel-Ansicht **Trichter** unter Umsatz.
- **Kein Cookie, keine gespeicherte IP, kein fremder Dienst.** Gezaehlt wird
  ueber `sha256(salz|DATUM|ip|user-agent)[:16]`. Das DATUM im Salz ist der
  ganze Trick: der Wert wechselt taeglich, ist nicht rueckrechenbar und
  nicht ueber Tage verkettbar - deshalb kein Einwilligungsbanner. Wer das
  Datum herausnimmt, macht daraus eine dauerhafte Kennung und braucht ein
  Banner plus Rechtsgrundlage.
- **Menschen zaehlen, nicht Klicks.** Vor der Anmeldung ueber den
  Fingerabdruck, danach ueber die Konto-Nummer.
- **Kauf und fertiges Video haben keinen Browser** (Stripe-Webhook,
  Render-Worker). Ihre Herkunft kommt ueber das Konto (`quelle_von_konto`,
  erste Spur gewinnt) - sonst laege jeder Umsatz unter "direkt".
- **Die Zahl, die zaehlt, ist der Anteil an der Stufe DARUEBER.** Der Anteil
  an ganz oben verschleiert, wo es klemmt.
- Eine Zaehlung scheitert IMMER leise; `_trichter` darf nie einen
  Seitenaufruf reissen. Aufbewahrung `DVE_FUNNEL_DAYS` (400 Tage).
- Wer eine Stufe ergaenzt, traegt sie in `_TRICHTER_STUFEN` UND in die
  Klartext-Tabelle in `_trichter_calc` ein - eine Stufe ohne Erklaerung ist
  im Panel wertlos, und die Datenschutzseite muss den Zweck nennen.

## Kunden-App: Layout-Fallen (v226b)
- **Ein Aufklapp-Bereich darf keinen festen `max-height` haben.** Der offene
  Zustand stand auf `max-height: 2000px; overflow: hidden` - nur damit die
  Animation lief. Auf einem 390 px breiten Handy ist "Look & Typography" rund
  3500 px hoch: **1502 px an Einstellungen waren abgeschnitten und mit keinem
  Scrollen erreichbar** (Ismets Befund "Ich sehe die weiteren Menue Optionen
  nicht"). Offen heisst jetzt `max-height: none`; den Pixelwert setzt das JS
  gemessen und nur fuer die Dauer der Animation (plus Sicherheitsnetz, falls
  `transitionend` ausbleibt). Merksatz: eine Animation, die Bedienelemente
  verschluckt, ist den Preis nicht wert - und ohne JS muss der Bereich
  trotzdem VOLLSTAENDIG da sein.
- **Was ein Vorschaubild darf, darf ein Player nicht (v228).** Die
  Bibliotheks-Kachel ist 16:9 mit `object-fit: cover` - richtig fuer ein
  ruhiges Raster. Beim Klick wurde derselbe Rahmen zum Player: von einem
  9:16-Video waren 32 % zu sehen. Wer einen Rahmen doppelt benutzt, muss ihn
  beim Rollenwechsel umschalten (`.playing` -> `aspect-ratio: auto` +
  `contain`). Und `width:100%` + `max-height` ohne `object-fit` VERZERRT ein
  Hochformat-Video, weil die Voreinstellung `fill` ist.
- Am Handy geprueft wird im BROWSER (Chromium, 390x844) und ueber
  `web/_dom_probe.mjs`, nicht per Quelltext-Suche. `scrollHeight` ist nur bei
  `overflow: hidden` aussagekraeftig - bei `visible` liefert es die eigene
  Hoehe und verschweigt den Ueberhang.

## Ankuendigungen + Feedback (v196)
- **Ankuendigung** = Banner IN der App (`announcements`, Stufen info/warn/
  wartung, optionales Ablaufdatum). `/api/announcements` braucht bewusst
  KEINE Anmeldung - eine Wartungsmeldung muss auch den erreichen, der
  gerade nicht eingeloggt ist. Weggeklickt wird **pro Ankuendigung** im
  localStorage gemerkt, nie global.
- **Support ist eine eigene Seite (v202), kein Block unter Account.** Dazu ein
  Zaehler im Navigations-Link: ungelesene Antworten kommen als `support_neu`
  aus `/api/me` (das wird ohnehin bei jedem Seitenaufruf geholt - ein eigener
  Endpunkt waere reine Last) und werden beim Oeffnen der Seite sofort
  zurueckgesetzt. Ein Zaehler, der stehen bleibt, nachdem man hingeschaut hat,
  ist Muell. Achtung beim Ergaenzen von `/api/me`: die REGISTRIERUNG gibt
  dieselbe Zeile zurueck, hat die Zaehl-Abfrage aber nicht - eine
  Sammelersetzung baut dort einen 500er ein.
- **Ein Ticket ist ein VERLAUF (v198), keine Nachricht.** `ticket_messages`
  ist die Quelle, `tickets.body` bleibt nur die erste Zeile. Geantwortet wird
  im Panel; die Antwort geht ZUSAETZLICH als Mail raus (niemand soll in die
  App schauen muessen, um sie zu sehen), und eine Rueckfrage des Kunden bleibt
  im selben Ticket und setzt es wieder auf `open`. Status ist offen/answered/
  closed - wer einen Wert ergaenzt, muss ihn auch in `admin_ticket_status`
  erlauben. Alt-Tickets bekommen ihre erste Nachricht beim Start nachgetragen,
  sonst faengt jeder alte Verlauf mit der Antwort an.
- **Feedback ist NICHT das Ticket-System.** Ticket = Frage mit Antwort,
  Feedback = Bewertung ohne. Die Sterne haengen am fertigen Render, damit
  der LOOK mitkommt - ohne ihn ist eine Note nicht auswertbar. Eine
  Bewertung je Render (die zweite ueberschreibt).
- Die Kunden-App hat `escHtml`, NICHT `esc` (das gibt es nur in
  `admin.html`). Und ein `try/catch` um einen Renderer muss loggen: ein
  leeres Banner sieht sonst aus wie "nichts vorhanden".

## Kunden-App: Hintergrund-Tab (v230e)
- **Ein Fehlerzähler muss wissen, WARUM eine Anfrage scheiterte.** Im
  Hintergrund bricht das Handy laufende Anfragen ab; gezählt wurden sie wie
  echte Ausfälle, und nach 10 kam die Karte „Connection lost" — während der
  Render unverändert weiterlief. Regel: im Hintergrund gar nicht erst
  fragen (`whenVisible()`), dort auftretende Fehler zählen nicht, und beim
  Zurückkommen fängt der Zähler bei null an.
- **Die Sonde `web/_dom_probe.mjs` hat zwei eigene Fallen:** `schneide()`
  muss das `async` VOR dem Funktionsnamen mitnehmen (sonst ist das erste
  `await` ein Syntaxfehler), und ein früherer Abschnitt ersetzt
  `globalThis.setTimeout` durch eine Warteschlange — wer echte Zeit braucht,
  nimmt `ECHTER_TIMEOUT`. Beides fällt als „Test misst nichts" auf, nicht
  als Fehler.
- **Was NICHT reproduzierbar war:** ein echter Renderer-Absturz. Weder im
  Leerlauf noch mit laufendem Render, auch nicht nach dreimaligem Einfrieren
  des Tabs. Kommt der Befund wieder, braucht es Gerät und Browser.

## Eine Allowlist darf nichts VERWERFEN (v230f — meine eigene Regression)
`_sanitize_overrides` liess nach v230c-sec nur noch Zahlen mit
Tabellen-Eintrag durch und warf den Rest weg. `effects.caption_zone` fehlte
— und fiel damit aus jedem gespeicherten Setup heraus: die Captions sassen
wieder im Standardband (Ismets „die Captions respektieren die Safe Zones
nicht mehr"). Der Weg: `applyTemplate` setzt `State.cfg` auf das Setup und
laesst `State.cfgBase` stehen, der Unterschied enthaelt danach ALLE
Preset-Werte.
- **Unbekannte Zahlen klemmen, nicht entfernen** (`_ZAHL_ALLGEMEIN`). Ein
  stiller Wegfall schaltet ein Feature ab, ohne dass ein Test oder eine
  Meldung es zeigt — derselbe Fehlertyp wie v210. Die teuren Regler behalten
  ihre eigene enge Grenze, der Sicherheitsgewinn bleibt.
- **Der Riegel ist der Test, nicht die Sorgfalt:** jede Zahl, die in
  irgendeinem Preset vorkommt, muss einen eigenen Eintrag haben. So faellt
  der naechste neue Regler im Selftest auf, nicht beim Kunden. Dazu ein
  Test, der ein ganzes gespeichertes Setup durchschickt und auf
  Vollstaendigkeit prueft.
- Und wieder die v132-Falle: der v230c-Test verlangte ausdruecklich, dass
  eine unbekannte Zahl VERWORFEN wird — er hat den Fehler festgeschrieben.

## Eine Pruefung, die nur EINE Form kennt (v230n)
`ink_box` misst drei Formen eines Textmoments — Karte, Komposition,
Fliesstext. Die **Stuetzzeile (`small`) war nicht dabei**, also war sie fuer
den Anschnitt-Riegel unsichtbar und lief aus dem Bild ('HIS ONE STICKS' ohne
das T, Ismets Standbild). Genau davor warnt der Docstring dieser Funktion
selbst — und trotzdem ist die vierte Form dazugekommen, ohne dort eingetragen
zu werden. Wer eine neue Textform baut, traegt sie in `ink_box`,
`_verschiebe_plan` UND `_skaliere_plan` ein; sonst misst der Riegel sie nicht,
oder er verschiebt die Karte und laesst die Zeile stehen.
Und: **ein Riegel mit `q is not p` uebersieht die eigene Karte.** Das
Ankerwort wich jedem fremden Block, nur nicht der Stuetzzeile derselben
Karte. Beim Nachbessern nicht ueberdrehen — die erste Fassung unterdrueckte
das Ankerwort immer und brach v221; der bestehende Test hat es gefangen.

## Eine Erkennung mit EINEM Merkmal ist blind — und schweigt (v230m)
Ismets `ABOVE ME` überlebte den Schnitt und wanderte in der Nahaufnahme nach
unten. Die Schnitt-Disziplin war NICHT schuld: die Schnitt-Erkennung hatte in
dem Video **keinen einzigen Schnitt** gefunden. Sie vergleicht Farb-Histogramme,
und ein graues Studio mit dunkler Kleidung sieht vor und nach dem Schnitt fast
gleich aus (stärkstes Signal 0.935 gegen die Schwelle 0.55).
- **Zweites Signal: der BILDAUFBAU** (mittlere Helligkeitsabweichung eines
  32x32-Miniaturbildes). Schwelle als Vielfaches des Medians, nicht fest — ein
  Handyvideo wackelt durchgehend, ein Stativ-Interview nie.
- **Wer eine Erkennung baut, fragt: auf welchem Material hat mein Merkmal
  keinen Kontrast?** Dort liefert sie nicht "unsicher", sondern "nichts" — und
  alles, was darauf aufbaut (Schnitt-Disziplin, Farbwelt pro Shot,
  Ton-Dramaturgie, Raum-Karte), fällt lautlos aus.
- **Der `behind`-Zweig ist der einzige Zeichenweg ohne `dt >= 0`.** Er malt die
  Stützzeile schon vor der Karte. Wer etwas "vor die Weiche" zieht, weil ein
  Zweig es richtig macht, baut es bei genau diesem Zweig DOPPELT ein (v230g →
  dieselbe Zeile zweimal, um den Gesichts-Versatz verschoben).
- **Tinte ist gegen Verschieben unempfindlich** — mit Versatz muss genauso viel
  Tinte im Bild sein wie ohne. So braucht ein Doppel-Test keinen Referenzwert.
  Zeilen-Erkennung taugt dafür NICHT: zwei Kopien, die sich um 20 px
  überlappen, verschmelzen zu einem Band und der Test misst nichts.

## Ein Sidecar schreibt zurueck, was es liest (v230l — zweimal derselbe Fehler)
Ismets „das Gesagte wird zweimal im Bild eingeblendet" hatte dieselbe Wurzel
wie der Anschnitt in v230g, nur eine Datei weiter: der Analyse-Lauf schreibt
in JEDEN Eintrag den AUTOMATISCHEN Wortlaut (`_bloecke.json` das Feld `text`,
`_momente.json` ebenso), und der naechste Lauf liest ihn als
NUTZER-Ueberschreibung — obwohl niemand etwas geaendert hat.
- **Regel: ein zurueckgeschriebenes Feld ist erst dann eine Nutzer-Aenderung,
  wenn es sich vom Automatik-Wert UNTERSCHEIDET** (`_norm_txt`-Vergleich).
  Wer ein neues Sidecar-Feld exportiert, beantwortet sofort, wie der naechste
  Lauf „unveraendert" von „geaendert" unterscheidet.
- **Ein Kartentext darf nie mehr Woerter zeigen, als die Karte besitzt.**
  `phrase` bricht an einer Sprechpause ab, `n` kennt die Pause nicht; der
  alte `phrase = phrase[:1]` gab die ueberzaehligen Woerter frei und sie
  standen direkt danach noch einmal als Fliesstext im Bild (gemessen: Karte
  `ON THE WALL` 5.10-6.55, danach Block `wall.` 6.55-6.98). Deckt sich der
  Text mit den gesprochenen Woertern ab `i`, waechst die Phrase mit.
- **Die Doppeltext-Wache meldet, sie raeumt nicht auf.** Sie schreibt Zeit
  und Wortlaut ins Job-Log, wenn ein gesprochenes Wort in zwei Plaenen steht,
  die gleichzeitig oder innerhalb einer Sekunde laufen. Woerter wegzuwerfen
  waere die v230f-Falle.
- **Der Suchweg ist die eigentliche Lehre:** vier Ebenen wurden gemessen,
  bevor die Ursache feststand — innerhalb eines Blocks (504 Bloecke, 0),
  zwischen den Plaenen (drei Dichten, 0), im fertigen Bild per Schablone
  (0, Detektor vorher am kuenstlich verdoppelten Bild geprueft) und
  gespiegelt (0). Erst der zweite Render mit Sidecar zeigte den Fall. Wer
  einen Kundenbefund nicht reproduziert, hat meistens den ERSTEN Lauf
  getestet.

## Sicherheit: Lehren aus Audit-Runde 2 (v230d-sec)
- **Ein mehrstufiger Vorgang wird an JEDER Stufe geprüft, und die
  Berechtigung gehört an den VORGANG, nicht an den einzelnen Request.** Der
  resumable Upload sind drei Anfragen; geprüft wurde nur die erste, und der
  Kunde kam aus dem Cookie der gerade laufenden. Wer beim Abschluss das
  Cookie wegließ, bekam einen Job ohne Eigentümer — und damit **kein
  Wasserzeichen, keine Abbuchung, keinen Flut-Deckel**, weil alle drei an
  `user_id` hängen. Wo eine Kette aus mehreren Aufrufen besteht, gehört der
  Eigentümer in den Sitzungszustand.
- **Ein Riegel, den nur die halbe Nachbarschaft hat, ist keiner** — dreimal
  in dieser Runde: die Code-Bremse saß an einem von sieben `check_auth`-
  Aufrufern, `/api/resend_verification` war der einzige Mail-Endpunkt ohne
  Limit, `/admin/codes` benutzte noch den `str`-Vergleich, den v203-sec in
  `_admin_ok` längst durch Bytes ersetzt hatte. Wer einen Riegel baut,
  sucht ALLE Aufrufer der geschützten Funktion ab und hängt ihn möglichst
  in die Funktion selbst.
- **Ein Protokoll, das ein Fremder füllen kann und niemand aufräumt, ist
  ein Angriff.** Ein anonymer 500er schrieb einen vollen Traceback in
  `alerts` — 452 KB je 100 Aufrufe, in derselben Datei wie Konten und
  Guthaben. Jede Log-Tabelle braucht einen Wiederholungs- und einen
  Mengendeckel.
- **Gleichheit von E-Mail-Adressen ist nicht Groß-/Kleinschreibung.**
  Plus-Tags und (bei Gmail) Punkte bezeichnen dasselbe Postfach. Für
  Missbrauchs-Sperren normalisieren — für die Anmelde-Identität NICHT,
  sonst sperrt man bestehende Kunden aus.
- **Der Wirksamkeits-Nachweis hat hier einen wirkungslosen Fix gefangen:**
  `(_current_user(request) or {}).get('id')` wirft einen AttributeError
  (`sqlite3.Row` hat kein `.get()`, v96p-Falle). Alle Quelltext-Tests waren
  grün, im echten Lauf ging der Angriff weiter durch. Sicherheits-Riegel
  gehören per echtem Angriff getestet, nicht per Textsuche.

## Sicherheit: Lehren aus dem zweiten Audit (v230c-sec)
Sieben bestätigte Wege, alle aus derselben Familie: **Sabotage und Kosten,
nicht Diebstahl.** Wer hier etwas ergänzt, prüft zuerst diese vier Fragen.
- **Jede Zahl aus dem Client braucht eine Grenze — und was keine hat, kommt
  gar nicht erst durch.** `_sanitize_overrides` klemmte fünf Werte und ließ
  den Rest laufen. Zwei davon steuern direkt die Rechenzeit
  (`matting_downsample` Faktor 50–90, `effects.bg_blur` Faktor 48) und ein
  einziges Gratis-Konto konnte den EINEN Worker stundenlang belegen. Eine
  Allowlist mit Bereichen (`_EFFECT_RANGE`) ist die einzige Form, die beim
  nächsten neuen Regler nicht wieder aufgeht. **Geklemmt wird auf beiden
  Seiten** — die Desktop-App schreibt dieselbe Config-Datei.
- **Der Wachhund rettet nicht vor einem LANGSAMEN Job.** Sein Fingerabdruck
  ist (Status, Fortschritt, Phase); solange der Fortschritt kriecht, läuft
  die Uhr immer neu. Rechenzeit begrenzt man am Eingang, nicht am Timeout.
- **Ein Riegel darf nicht am MODUS hängen, wenn die Eigenschaft am JOB
  hängt.** `_render_gebucht(...) if mode == 'full'` machte aus "schon
  bezahlt" ein "je nach Aufruf" — 4K zum 1080p-Preis. Und **erstattet wird,
  was in der Ledger-Zeile steht**, nie was ein überschreibbares Feld
  (`cost_sec`) behauptet: sonst erzeugt ein Abbruch Guthaben.
- **`_job_owner_ok` beweist kein Eigentum an einer UNBEKANNTEN jid.** Kein
  Job → kein Eigentümer → `True`. Wo eine ID aus dem Formular kommt, muss
  der Job EXISTIEREN und dem Aufrufer gehören.
- **Ein Deckel auf das Gleichzeitige ist kein Deckel auf die Summe.**
  `_inflight_count` zählt 'wartet'/'laeuft'; ein vorbereiteter Upload fällt
  heraus und der nächste ist sofort erlaubt. Wer nichts abbucht, braucht
  eine Summen-Grenze (`_vorbereitet_count`) — sonst sind Whisper-Rechnung
  und Plattenplatz unbegrenzt.
- **Eine Grenze auf die lange Kante ist keine auf die Fläche.** 8x4096 ist
  unter jedem Limit und wird intern auf 384x196608 hochskaliert (226 MB je
  zwischengespeichertem Bild). Kurze Kante und Seitenverhältnis mitprüfen.
- **Betrieb: was neben dem Repo liegt, landet im Image.** `.env` fehlte in
  `.dockerignore`, also backte `COPY . /app/` den Stripe-LIVE-Key ins
  Arbeitsverzeichnis genau des Prozesses, dem v204-sec ihn weggenommen hat.
  Und ein Skript, dessen Standard-Pfad auf dem Server nicht existiert
  (`restore.sh` → `./web/data` statt Volume `dve-data`), meldet Erfolg,
  ohne etwas zu tun — die gefährlichste Sorte Fehler bei einem Notfall-Werkzeug.

## Sicherheit: Lehren aus dem Audit (v203-sec)
Zwei adversariell gegengeprüfte Audits, 30 bestätigte Befunde. Die Muster,
die sich wiederholen:
- **Ein Wächter, der nicht wirft, ist keiner.** `_admin_ok` gibt nur `bool`
  zurück; als nackte Anweisung aufgerufen (`_admin_ok(request)`) sicherte sie
  GAR NICHTS. Zwei Endpunkte waren dadurch anonym erreichbar. Der werfende
  Riegel heißt `_require_admin` — `_admin_ok` ist nur der Test dahinter.
  Der Selftest fährt jetzt ALLE `/api/admin/*`-Routen ohne Key ab; eine
  Quelltext-Suche findet diesen Fehler nicht (beide Namen stehen ja da).
- **Eine doppelt registrierte Route verdeckt den Riegel der zweiten.**
  Starlette bedient die ZUERST registrierte; die gesicherte Variante war
  toter Code und sah beim Lesen nach Absicherung aus. Selftest prüft auf
  doppelte Pfade.
- **Der Riegel gehört VOR die Mutation.** In `render_start` wurden Preis und
  Qualität gesetzt, bevor abgerechnet wurde — und die Abrechnung ist
  idempotent, buchte also nicht nach: 4K zum 1080p-Preis, und über die
  Erstattung ließ sich Guthaben erzeugen. Der Preis hängt jetzt am LEDGER
  (`_render_gebucht`), nicht an einem überschreibbaren Feld. Derselbe
  Fehlertyp wie v159/v170/v176.
- **Eine Eigenschaft, die schützt, darf nicht in einem Feld stehen, das der
  nächste Request umschreibt.** 'demo' stand nur in `mode`; über den
  Momente-Editor wurde daraus ein voller Gratis-Render ohne Wasserzeichen.
  Jetzt `j['demo']`, gesetzt bei der Anlage, gelesen im Worker.
- **Ein unbestätigtes Konto ist kein Eigentumsnachweis.** Der Google-Login
  verknüpfte still über die E-Mail — wer vorher auf eine fremde Adresse
  registrierte, teilte sich danach das Konto mit dem echten Inhaber. Google
  hat die Adresse bewiesen, also übernimmt es sie: verknüpfen, altes Passwort
  entwerten, Sitzungen beenden. NICHT löschen (sonst verlöre ein echter Kunde
  seine Bibliothek).
- **Nutzerdaten, die in die Engine laufen, gehören geklemmt — auf BEIDEN
  Seiten.** `sanitize_moments` am Server, plus harte Klemmung in `render.py`:
  die Desktop-App schreibt dieselbe Datei. Ein ungeklemmtes `power` treibt den
  Gauß-Radius ins Unendliche und legt den einen Worker lahm.
- **Ein Passwortwechsel muss die anderen Sitzungen beenden.** Der Reset-Weg
  tat es seit jeher, der Wechsel-Weg nicht — die beiden widersprachen sich.
- **Ein Test kann eine Lücke als Zusage festschreiben.** Der v132-Test
  verlangte ausdrücklich "Passwort bleibt gültig" nach der Google-Verknüpfung.
  Wer einen Test anpasst, muss prüfen, ob er die Regel schützt oder den Fehler.

## Betrieb: Deploy, Backup, Logs, Schlange (v197)
- **Das Gate kennt ZWEI Fehler (v201).** `exit 1` = Tests rot, Code kaputt,
  Deploy abbrechen. `exit 2` = das Gate konnte gar nicht laufen (Image startet
  nicht, ffmpeg fehlt, docker zickt) - darueber ist ueber den Code NICHTS
  gesagt, also wird deployt, aber laut und mit Eintrag im Panel. In v197 war
  beides derselbe Fall: eine Panne an der PRUEFVORRICHTUNG fror damit den
  ganzen Betrieb ein, und v198 bis v200 gingen nie live. Ein Waechter, der bei
  eigenem Ausfall die Tuer zumauert, ist kein Waechter. Das Gate wird im
  Selftest mit einem VORGETAEUSCHTEN docker durchgespielt (alle drei
  Ausgaenge) - eine Quelltext-Suche haette den Fehler nie gefunden.
- **Das Gate urteilt nach der BILANZ, nicht nach einer Textsuche (v208a).**
  Es hielt `1511/1511 Tests bestanden` fuer ROT und blockierte einen
  einwandfreien Commit, weil irgendwo im Log eine Zeile mit `FAIL` begann -
  naemlich im BELEG eines BESTANDENEN Tests (der v201a-Test legt absichtlich
  einen roten Gate-Befund an und zeigt ihn her). Zwei Riegel: `check()` macht
  aus jedem Beleg EINE Zeile, und gruen heisst jetzt `bestanden == geprueft`
  plus Rueckgabewert 0. Merksatz: ein Waechter, der Text sucht statt das
  Ergebnis zu lesen, haelt irgendwann den Falschen auf - und ein falscher
  Alarm kostet genauso viel wie ein verpasster, weil dann nichts mehr live geht.
- **Der Befund gehoert in die Meldung (v201a).** `deploy_gate.sh` schreibt
  sein Ergebnis nach `.deploy_gate_last.txt` (gitignored), `autodeploy.sh`
  haengt die gefallenen Tests an die Panel-Meldung. "Deploy abgebrochen" ohne
  Grund ist fuer jemanden, der nie ins Terminal geht, dasselbe wie keine
  Meldung.
- **Nichts geht ungeprueft live.** `update.sh` ruft `deploy_gate.sh` (Selftest
  im NEU GEBAUTEN Image, `--rm --no-deps`, eigenes `DVE_DATA`, kein Key) VOR
  `docker compose up`. Rot = Abbruch, die alte Version laeuft weiter. Wer den
  Deploy anfasst, darf diese Reihenfolge nicht drehen.
- **Ein Pfad heisst auf dem Host und im Container gleich und ist trotzdem ein
  anderer Ort (v225c).** `update.sh` schrieb den Build-Stempel nach
  `$DVE_DATA` - auf dem HOST. Im Container ist `DVE_DATA=/data` ein
  Docker-Volume (`dve-data`, KEIN Bind-Mount), also hat der Server die Datei
  nie gesehen: Panel dauerhaft "Commit unbekannt", taeglich eine
  "Seit Tagen kein Deploy"-Mail, Video-Metadaten ohne Commit - genau die drei
  Dinge, die v222 beheben sollte, alle drei tot. Was der Container wissen
  soll, gehoert ins IMAGE (Datei ins Bauverzeichnis, `COPY . /app/` nimmt sie
  mit) oder in eine Umgebungsvariable, nie in ein Verzeichnis, das nur auf dem
  Host so heisst. Zweiter Grund fuer denselben Weg: ein Stempel neben der
  Datenbank behauptet den NEUEN Commit, sobald `git pull` durch ist - auch
  wenn das Test-Gate danach abbricht und weiter die ALTE Fassung laeuft. Ein
  Stempel, der luegen kann, ist wertlos.
- **Jede Meldung nennt den Stand des Absenders (v226a).** Ismet bekam
  dieselbe Fehlalarm-Mail zweimal und konnte nicht erkennen, ob die zweite
  noch von der alten Fassung kam. Die Antwort brauchte Commit-Zeiten und
  Video-Metadaten - fuer eine Zeile, die der Absender gratis mitliefert.
  `_notify_admin` haengt `Gemeldet von DouchkoVE <Stand>` an, `/api/health`
  nennt die Version (nicht den Commit).
- **Ein gescheiterter Deploy war STUMM (v226a).** `autodeploy.sh`/`update.sh`
  schreiben per sqlite DIREKT in die alerts-Tabelle - sie koennen
  `_notify_admin` nicht aufrufen, also ging nie eine Mail raus. Genau der
  Fall, in dem gar nichts mehr live geht, war der Fall, von dem niemand
  erfuhr. Der Watchdog mailt ungemailte `deploy`/`deploy_gate`-Alarme nach.
  Merksatz: wer aus einem Skript heraus meldet, prueft, ob den Eintrag
  ueberhaupt jemand ABHOLT.
- **Ein fehlender Messwert ist kein schlechter Messwert (v225c).** Der
  Wachhund behandelte "kein Stempel" wie "Stand ist 20 Tage alt" und mailte
  taeglich einen Stillstand, den es nicht gab. Zwei Lagen, zwei Meldungen:
  messbar alt = echter Befund (taeglich erlaubt), kein Stempel = "ich weiss es
  nicht" (genau EINMAL je Programmlauf). Und der alte Test verlangte
  ausdruecklich `_al is None or _al > 7` - er hat den Fehler festgeschrieben,
  dieselbe Falle wie v132.
- **Ein stiller Fehlschlag ist schlimmer als ein lauter.** Nach `git pull`
  steht der Server schon auf dem neuen Commit; scheitert das Gate, saehe der
  naechste Timer-Lauf "nichts Neues". Deshalb schreibt `autodeploy.sh` bei
  Fehlschlag eine Zeile in die alerts-Tabelle des LAUFENDEN Containers.
- **Alles geht ueber das Admin-Panel, nichts ueber das Terminal (Ismets
  Ansage, Juli 2026).** Auch das Zurueckspielen: `_restore_users_db` schreibt
  die Sicherung ueber die SQLite-Online-Backup-API IN die laufende Datenbank -
  kein Dateitausch, kein Neustart, offene Verbindungen sehen danach den neuen
  Inhalt. Der Skript-Weg (`restore.sh`) bleibt als Notnagel, wenn die App gar
  nicht mehr startet. Wer eine neue Betriebs-Aufgabe baut, baut sie ins Panel.
- **Ein Backup, das man nie zurueckgespielt hat, ist kein Backup.**
  `restore.sh` prueft den Kandidaten (integrity_check + Pflichttabellen),
  BEVOR es die laufende DB anfasst, und legt den jetzigen Stand als
  `vor_restore_*.db` zur Seite. Genau diese Probe hat den Backup-Bug
  gefunden: `_backup_users_db` sicherte nur EINMAL je Kalendertag, also den
  Stand beim Worker-Start - alles danach fehlte. Ein Deckel, der auf den
  KALENDERTAG schaut statt auf den Inhalt, deckelt den falschen Wert
  (derselbe Fehlertyp wie v194b/c bei den Mails).
- **`print()` ruft `write()` je Argument einzeln.** Ein Log-Tee ohne
  Zeilenpuffer schreibt jedes Argument in eine eigene Zeile.
- **Die URSACHE gehoert an den ANFANG der Meldung (v208b).** Ein Traceback
  nennt den eigentlichen Fehler in der LETZTEN Zeile - also genau dort, wo
  eine Panel-Ansicht oder ein Copy-Paste abschneidet. `_unhandled` schreibt
  `URSACHE: <Typ>: <Text>` plus die letzten sechs Zeilen nach oben, den
  vollen Verlauf darunter. Und **ein abgebrochener Upload ist keine
  Stoerung**: `ClientDisconnect` hat einen eigenen Riegel (499, kein
  Panel-Eintrag). Wer jeden Funkloch-Abbruch meldet, verstopft die Liste,
  in der die echten Stoerungen stehen.
- **Unbehandelte Fehler gehoeren ins Panel**, nicht nach stdout - stdout ist
  nach dem naechsten Deploy weg. Der globale `@app.exception_handler` schreibt
  in `alerts`; der Kunde sieht nie einen Traceback.
- **Eine Positionsangabe muss die eigene Position sein.** `qsize()` ist die
  Laenge der Schlange, nicht der Platz darin - und bei der PriorityQueue zieht
  ein zahlendes Konto vorbei. `_queue_platz` zaehlt die Eintraege davor.
- Skalierung bleibt bewusst 1 Worker/1 Maschine (`DVE_WORKERS`). Ein Render
  zieht CPU und RAM; parallele Jobs machen beide langsamer. Der Watchdog
  meldet ueber `DVE_QUEUE_WARN`, wann es eng wird - das ist das Signal fuer
  mehr Maschine, nicht mehr Threads.

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
- **Umsatz ist NETTO (v206).** `purchases` ist der Kaufbeleg und wird NIE
  nachträglich verbogen (GoBD); eine Erstattung ist ein eigener Vorgang in
  `refunds` — aus dem Panel UND aus dem Stripe-Dashboard (`charge.refunded`
  trägt sie nach). Umsatz und §19-Ampel rechnen mit „geblieben", das Panel
  zeigt alle drei Zahlen. Bis v205 war alles brutto: eine Erstattung zählte
  weiter als Einnahme, auch in der Steuer-Ampel.
- **Das Panel hat eine STARTSEITE (v206).** Sie beantwortet vier Fragen —
  Verdiene ich Geld? Läuft alles? Will jemand etwas von mir? Wächst es? —
  mit je EINER großen Zahl und einem Satz Klartext daneben. Ismet ist kein
  Entwickler; „AOV", „ARPPU", „inflight_cap" sagen ihm nichts. Alles
  Technische bleibt in den bestehenden Ansichten, es steht nur nicht mehr
  vorn. Wer eine Kennzahl ergänzt, schreibt den erklärenden Satz dazu.
  **Eine Ampel, die grundlos rot ist, schaut nach einer Woche niemand mehr
  an** — deshalb wird der Herzschlag beim Start gesetzt (der Wachhund meldet
  sich sonst erst nach 120 s, also nach JEDEM Deploy zwei Minuten „rot").
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

## Matte-Bleed (v230b) — ein Weichzeichner darf die Person nicht ansaugen
Ismets "das Auge glitcht" war ein **heller, flimmernder Saum an Haar und
Schulter**, und die Ursache stand zweimal im selben Code-Muster: ein
Weichzeichner lief ueber das GANZE Bild, mischte dort an der Silhouette
dunkles Haar mit heller Wand — und danach wurde die Person mit ihrer
WEICHEN Matte wieder darueber gepastet, sodass der Mischwert als Saum auf
dem Haar stehen blieb. Fundorte: `apply_bg_blur` (Bokeh) und die
Tiefen-Unschaerfe hinter einem `behind`-Text in `composite_frame`.
- **Regel: wer den Hintergrund weichzeichnet, rechnet ALPHA-GEWICHTET**
  (`blur(bild*(1-a)) / blur(1-a)`). Personen-Pixel duerfen gar nicht erst
  in den Mittelwert eingehen. Und die Vordergrund-Maske darf nur nach
  AUSSEN weich sein (`fg = max(blur(a), a)`) — die weichgezeichnete Maske
  reichte vorher ~20 px IN die Person hinein.
- **Die Test-Invariante ist RICHTUNGSFREI:** der weichgezeichnete
  Hintergrund darf nicht davon abhaengen, welche FARBE die Person hat. Ueber
  die Helligkeit zu messen taugt nicht — auf Ismets Material wurde der Saum
  HELLER, im synthetischen Testbild DUNKLER. Ein Helligkeits-Test waere je
  nach Motiv gruen gewesen, ohne etwas zu beweisen.
- **Ein synthetischer Testfall muss die echten GROESSENVERHAELTNISSE haben.**
  Der erste Entwurf (320x240) zeigte alt wie neu +0.02 — die Maskenweichheit
  haengt an `H*0.008`, bei 240 px sind das 2 px statt 10. Ein Test in
  Briefmarkengroesse beweist nichts ueber ein 720x1280-Bild.
- **Der Spion ist das Werkzeug der Wahl:** EIN- und AUSGANG von
  `composite_frame` bei EINEM Zeitpunkt auf Platte legen. Damit war in einem
  Lauf klar, dass das Bild VOR dem Compositor bitgleich zur Quelle ist
  (0.00) — Dekodieren und Matting waren damit raus, ohne sie einzeln
  durchzuprobieren.

## Renderzeit (v227) — messen ist Pflicht, raten ist verboten
Jeder Render endet mit `Timing (total …)`: alle Phasen absteigend nach Kosten
plus `other` für alles Ungemessene. Wer an der Geschwindigkeit dreht, liest
zuerst DIESE Zeile aus einem echten Job-Log — Regel 1 verbietet, Qualität
gegen Zeit zu tauschen, also darf nur echte Leerarbeit weg.
- **Der teuerste Schritt war nicht das KI-Netz, sondern die Nacharbeit.**
  `refine_alpha` (Guided Filter, zieht die Maskenkante an die Bildkante)
  kostete bei 1080x1920 auf CPU 151-279 ms je Bild, das Matting-Netz selbst
  216 ms. Er lief zweimal über das GANZE Bild, obwohl die Maske ein Drittel
  ausmacht. Zuschnitt auf die Maske + 4 Radien Rand → **pixelgleich**
  (0.0000/255 über vier Formen), 1.8x bis 14x schneller.
- **Derselbe Fund ein zweites Mal (v228f):** `kill_spill` (Farbsaum an der
  Silhouette) lief ebenfalls über das ganze Bild, obwohl nur ein schmales
  Band zählt — 36 ms je Bild, teuerster Einzelposten im Compositor.
  Zuschnitt auf das Band + 10 Sigma Rand: exakt pixelgleich, 1.9x-15x
  schneller. Wer eine Funktion mit einer weichen Maske multipliziert, prüft
  ZUERST, wo diese Maske überhaupt ungleich null ist.
- Merksatz: bevor eine Einstellung heruntergedreht wird, prüfen, ob die
  Funktion überhaupt dort rechnet, wo etwas ist. `boundingRect` auf der Maske
  ist billiger als jede Qualitätsdiskussion.
- **Eine Qualitäts-Einstellung hochzudrehen ist auch nur eine Vermutung
  (v228b).** Ismets zerfetzte Maskenkante sah nach "zu grob gerechnet" aus.
  Gemessen war die ROHE Netz-Maske sauber (9 Krümel), erst die Nachschärfung
  machte 285 daraus — und eine feinere Detailstufe (0.337 → 0.506) änderte an
  der Kante nichts, kostete aber +83 % Matting-Zeit. Wer an Qualität dreht,
  misst vorher, WELCHER Schritt sie kaputt macht. Der Guided Filter hilft auf
  echtem Kameramaterial und schadet auf weichem KI-Material; deshalb steht
  dort jetzt eine Gegenprobe am ersten Bild statt eines festen Werts.
- Ein Tempo-Test gehört an eine PIXELGLEICHHEITS-Prüfung gekoppelt. Ohne sie
  ist "schneller" nur die verbotene Abkürzung mit besserem Namen.
- **Am echten Render gemessen (v227a): 64 % der Zeit lagen VOR dem ersten
  Bild** (`regie+plaene 99.5s` von 154.7s), und darin vor allem Warten auf
  ffmpeg: bis zu 40 Zeige-Proben + 24 Vision-Bilder + 16 Anker-Bilder, jedes
  ein eigener Prozessstart, streng hintereinander - und die Vision-Bilder
  DOPPELT (Bild-Regie und Objekt-Anker fragen dieselbe Stelle). Jetzt
  Zwischenspeicher + paralleles Vorabholen, bitgleiche Bilder, 2.5-2.7x.
  Merksatz: wer eine neue Analyse baut, die Standbilder zieht, holt sie ueber
  `_frame_bgr_vorab` / `_frame_b64_vorab` - ein Prozessstart je Bild in einer
  Schleife ist der teuerste Weg, den es gibt.
- **Am echten Render gemessen (v228c): 129 von 191 s waren WARTEN AUF DIE
  KI** (Bild-Regie 39.5 + Text-Regie 37.7 + Text-Fluss 26.1 + Objekt-Anker
  25.3). Bild-Regie und Objekt-Anker laufen jetzt gleichzeitig (je eine KOPIE
  der fx_map, `merge_anker` fuehrt deterministisch zusammen). Text-Regie und
  Text-Fluss haengen echt voneinander ab - der Fluss braucht die
  Blockaufteilung. Wer hier weiter will, dreht am MODELL oder am Denkbudget,
  und das ist eine Qualitaetsfrage fuer Ismet, keine technische.
- **`keywords.ai_denken` (v228d) steuert `reasoning_effort`; Standard ist
  seit v228e wieder 'aus'.** Ismets Befund nach dem ersten Render mit 'low':
  "Qualitaet ist sehr schlecht geworden" - die Regie ist das Herz des
  Produkts, Renderzeit dagegen zu tauschen war das falsche Geschaeft. Der
  Schalter bleibt, der Standard denkt voll nach. Das Denkbudget bleibt bei >= 2500: weniger
  denken heisst MEHR Platz fuer die Antwort (v210-Falle).
- **Verschachtelte Zeit-Bloecke duerfen nicht doppelt zaehlen** (`_ZEIT_KIND`):
  `regie+plaene` umschliesst die KI-Aufrufe, die Prozente summierten sich auf
  190 %.
- Noch NICHT gemessen (braucht echtes Material): Tiefen-Modell je Bild,
  MediaPipe-Hände bei voller Auflösung, x264-Preset. Und die Pipeline läuft
  strikt seriell (dekodieren → freistellen → Tiefe → setzen → kodieren);
  Überlappen wäre eine Architektur-Änderung → Ismet entscheidet.

## Selftest — Ablauf (Pflicht vor jedem Deliver)
Gesamt **1849/1850 (Stand v230p)** + Renders 7/1/5/2 + GUI. Der eine rote Test
ist der GUI-Start: in diesem Container ist `tkinter` gar nicht installiert
(Ersatz-Stub), das ist eine Umgebungs-Grenze, kein Code-Fehler. Läuft nur unter Linux/CPU mit
synthetischen Assets und OHNE OpenAI-Key; GUI-Tests headless via `xvfb-run`.
Der Server-Code (`web/server.py`) wird im `logic`-Teil mitgetestet (isolierte
Test-DB, Quelltext-Garantien).

```bash
# Testmaterial: /tmp/st_clip.mp4  + /tmp/st_transcript.json
# Erzeugen wie in deploy_gate.sh - ABER: das Transkript muss eine BLANKE
# Wortliste sein ([{word,start,end}, ...]). deploy_gate.sh schreibt die
# {"words": ...}-Form; die reicht nur fuer --part=logic, render.py liest
# daraus 2 "Woerter" und bricht ab.
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

## WIRKSAMKEITS-NACHWEIS (v219, Ismets Ansage "lerne aus deinen Fehlern")
**Vor jedem Deliver einer Verhaltens-/Optik-Änderung ist zu BEWEISEN, dass der
geänderte Code im echten Pfad LÄUFT.** Nicht dass er da steht — dass er läuft.
Drei Fehlschläge an einem Tag hatten dieselbe Form: der Fix war richtig
gedacht, grün getestet und ohne jede Wirkung. Ismet hat dreimal umsonst
gerendert. Die Pflichtfragen, in dieser Reihenfolge:

1. **Wird die Zeile ERREICHT?** Jede umschliessende Bedingung von aussen nach
   innen durchgehen und ihren Wert im Zielfall aufschreiben. `composite_frame`
   ist die Falle: der `ground`-Zweig allein hat DREI Zeichenwege (getrackt /
   ungetrackt / `front_layer`), und jeder endet mit `continue`. Eine
   Sprite- oder Pose-Korrektur gehört VOR die Weiche, nie in einen Ast.
   Bei `tracked` gilt: für einen ground-Plan ist es IMMER wahr, weil
   `need_track` das ganze Anzeigefenster abdeckt (v219).
2. **Der Test muss die Funktion AUFRUFEN, die im Produkt läuft.** Eine
   Quelltext-Suche (`'wall_pose(' in src`) und eine reine Funktionsprüfung
   waren bei v218 beide grün, während im Bild nichts passierte. Also:
   `build_plans` UND `composite_frame` echt aufrufen, notfalls mit einem
   Spion auf der neuen Funktion (`R.x = spion`), und den AUFRUFZÄHLER prüfen.
   Das ist die v193-Lehre, verschärft: nicht nur "Plan trägt den Wert",
   sondern "der Wert kommt im Bild an".
2b. **Browser-JavaScript wird AUSGEFÜHRT, nicht gelesen.** Node 22 liegt im
   Image. `web/_dom_probe.mjs` schneidet Funktionen aus `index.html` und lässt
   sie gegen ein Mini-DOM laufen; der Selftest ruft die Sonde auf. Wer SPA-
   Verhalten ändert, erweitert die Sonde — eine Quelltext-Suche zählt nicht.
3. **Der Unterschied muss MESSBAR sein.** Alt gegen neu am gerenderten Bild
   oder am Sprite vergleichen (v219: abgewandte Textseite von 2.23 auf 0.52
   verkürzt). "Plausibel" ist kein Beweis.
4. **Eine Regel gegen Doppelbilder darf Zeiten nur KÜRZEN, nie verlängern**
   (v216/v217). Sonst beseitigt sie die Überschneidung in den ZAHLEN und
   erzeugt sie im INHALT — kein Zeit-Test fällt darauf.
4b. **`composite_frame` ist NICHT zustandsfrei.** Anker, Animationsphase und
   Flächenmessung liegen AM PLAN. Ein alt-gegen-neu-Vergleich braucht deshalb
   FRISCHE Pläne pro Lauf — sonst misst der zweite Durchgang den Zustand des
   ersten (v221, hat einen eigenen Test zum Fallen gebracht).
5. **Wenn ein Fix nicht reproduzierbar ist, sagen — nicht liefern und hoffen.**
   Zwei Videos pixelweise vergleichen (`mittlere Differenz < 1` = derselbe
   Render) beantwortet in 10 Sekunden, ob überhaupt die neue Fassung lief.
6. **ZUERST prüfen, WELCHE Fassung das Video gerendert hat** (v222). Der
   Build-Stempel steht in den Metadaten jedes Videos:
   `ffprobe -show_entries format_tags` → `comment=DouchkoVE <stand> job <jid>`.
   Stimmt der Stand nicht mit dem eigenen Commit überein, ist die Frage nach
   dem Code sinnlos — dann hängt der Deploy. Drei Runden gingen genau dafür
   verloren, weil `DVE_BUILD` ein festes Literal war und log. Steht dort
   `(Commit unbekannt)`, ist der Container älter als v225c — dann sagt der
   Stempel gar nichts, und die Frage muss über das Panel (Ansicht Build)
   beantwortet werden.
7. **Eine Richtung aus einem VORZEICHEN ist eine Behauptung** (v225b). Ob eine
   Wand nach links oder rechts flieht, kam aus dem Vorzeichen eines
   Sobel-Medians — dessen Orientierung ich verwechselt hatte, und das faellt
   erst am fertigen Bild auf, also beim Kunden. Richtungen gehoeren
   geometrisch begruendet (die weiter entfernte Seite ist im Bild kuerzer) und
   mit einem GESPIEGELTEN Gegentest belegt, der bei vertauschter Richtung
   fallen muss. Gilt fuer jede Seiten-, Dreh- oder Kipp-Entscheidung.

## Deliver-Muster (jede neue Version)
0. **Wirksamkeits-Nachweis nach dem Abschnitt darüber.** Ohne ihn gilt eine
   Verhaltens-/Optik-Änderung als NICHT fertig, auch wenn alle Tests grün sind.
1. Selftest erweitern (neues Feature bekommt Tests; visuelle Sachen bekommen
   Verhaltens-Invarianten, nicht nur "läuft durch").
2. Volle Regression grün + ggf. Browser-Smoke.
3. `PROJEKT_STATUS.md`-Eintrag oben (was neu, EHRLICHE Ursache, Beweis,
   Test-Hinweise).
4. Commit + Push auf den Feature-Branch (→ Auto-Deploy).
5. Deutscher Summary im Effizienzmodus, mit Beweis (Frames/Video) bei Optik.

## Wichtige Prinzipien (aus der Historie)
- **Sound-VARIANTEN (v200): ein Slot ist eine LISTE, keine Datei.**
  `sfx/pack/<slot>.wav` plus `<slot>_1..9.wav`; `V()` wechselt reihum durch.
  Ismets Befund "immer dieselben Sounds" lag NICHT am Wahl-Mechanismus (den
  gab es seit v96d), sondern daran, dass es nichts zu waehlen gab: jeder Slot
  hatte genau EINE Datei, 7 der 21 hochgeladenen Sounds lagen ungenutzt in
  `sfx/incoming`. Wer Sounds nachlegt, legt sie als `_N` daneben - `tick`
  zuerst, der laeuft bei fast jeder Wortgruppe.
  - **Der Varianten-Versatz muss aus dem INHALT kommen** (crc32 ueber Text +
    Laenge), nicht aus einem bei 0 startenden Zaehler: sonst ist der erste
    Tick in JEDEM Video dieselbe Datei. Und **nie `hash()`** - Pythons
    String-Hash ist pro Prozess gesalzen, ein Re-Render ergaebe eine andere
    Tonspur.
  - Pitch- und Varianten-Versatz sind GETRENNT, sonst laeuft Variante 3 immer
    mit demselben Pitch.
  - Zwei Schnitte aus derselben Aufnahme sind formal Varianten und klingen
    gleich - der Selftest misst die spektrale Aehnlichkeit (< 0.8).
- **Eine an fremdem Material geeichte Regel kann auf dem eigenen zur
  Stummschaltung werden (v230).** "Ticks nur in den ersten 1.6 s einer
  Einstellung" stammt aus einer schnittreichen Referenz; in einem
  Talking-Head ist der ganze Clip EINE Einstellung, also kam nach 1.6 s gar
  kein Ton mehr. Jetzt: am Schnitt volle Dramaturgie, danach Ticks mit
  Mindestabstand (`effects.sfx_dichte`, Standard 'normal' = 1.8 s). Gemessen
  3 -> 8 Sounds auf 15.6 s. Wer eine Referenz-Regel uebernimmt, fragt: was
  macht sie, wenn das Merkmal (hier: der Schnitt) FEHLT?
- **Eine Rotation muss im richtigen Ring laufen (v230o).** `V()` wechselt die
  VARIANTE innerhalb eines Slots - 8 der 14 Slots haben aber nur EINE Datei.
  Dort muss der SLOT wechseln, sonst hoert man dieselbe Aufnahme mit
  +-8 % Tonhoehe (Ismets "spammt denselben Sound"). Drei Ketten aus
  gleichwertigen Slots mit Pegelausgleich: Einflug, Wucht, Luft. Gemessen am
  echten Job: 11 -> 15 benutzte Dateien, haeufigste 27.3 % -> 13.6 %.
  Wer hier prueft, misst die HERKUNFT der Signale (Etikett am Array), nicht
  den Quelltext - und ein Test darf an der REGEL haengen (Ton fuehrt Bild),
  nie am Slot-Namen, sonst meldet er die gewollte Abwechslung als Fehler.
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
  **Und NIE gegen einen echten AUSSENDIENST (v207-sec).** `selftest.py` leert
  ganz oben, VOR dem Import von `web.server`, alle Zugänge: Stripe, SMTP,
  Resend, OpenAI, Google. Gefunden hat das der erste erfolgreiche Lauf des
  Test-Gates IM CONTAINER — dort ist der Stripe-LIVE-Schlüssel aus der .env
  gesetzt, und `admin_refund` rief im Test tatsächlich `Refund.create` gegen
  das echte Konto. Mit erfundener Sitzungs-Nummer schlug es fehl; mit einer
  echten wäre echtes Geld erstattet worden. Der Gate-Aufruf leert dieselben
  Werte ein zweites Mal — ein Testlauf, der Geld bewegen kann, darf nicht an
  EINER Vorsichtsmaßnahme hängen.
- **Landing:** Englisch, international, Modellnamen unsichtbar (kein "GPT-4o"
  im Hero), keine Konkurrenz-Namen, kein Datenschutz-Block (gehört in /privacy).

## STAND 29.07.2026 - HIER WEITERMACHEN (fuer den naechsten Chat)

### ERLEDIGT (v214): Ansage wurde vor ihr Wort gezogen
Ismets Befund (`Block 8.18s | ON THE WALL`, gesprochen ab 9.08 s) ist behoben.
**Die Ursache war NICHT der Overlap guard** - der kuerzt nur Enden. Schuld war
der 1.5-s-Vorlauf des Szenen-Texts ("liegt schon da"), den der Solo-Riegel
danach als `t0` festschrieb; `t0` ist die Uhr, nach der die Karte einblendet.
Behoben an vier Stellen (Vorlauf, Sofort-Hook, Beat-Grid, `intent` steht jetzt
AM PLAN) plus `intent_time_floor()` als zentralem Riegel am Ende von
`build_plans`. Der Vorlauf gilt weiter fuer Szenen-Text OHNE Ansage.
Lehre bleibt: **wer eine neue Zeit-Regel baut, fragt zuerst, was sie mit einem
`intent`-Moment macht** - sie darf ihn nur nach HINTEN schieben.

### ERLEDIGT (v226): die Kamera widerlegte die Ansage
Ismets Befund am gestempelten v225b-Render: "das 'above me' zuckt etwas zu viel
und geht runter". Am Video gemessen wanderte die Karte in 0.29 s um 109 px NACH
UNTEN - bei einer Ansage, die "ueber mir" heisst.
- **Kameramodus 'caption' kann sein Versprechen nicht halten.** Er schiebt das
  Bild um `(by - H/2) * 0.30` auf die Karte zu; bei `by = 0.22 H` sind das
  108 px nach unten - genau der Messwert. Nur: die Caption wird VOR dem Warp
  ins Bild gezeichnet und wandert mit. Der Abstand zwischen Kamera und Karte
  bleibt gleich, es rutscht bloss alles zusammen. Ein Name, der eine Zusage
  macht, die der Code nicht einloest (v194-Lehre) - und bei einer ORTS-Ansage
  ist das Ergebnis nicht nur wirkungslos, sondern falsch: die Karte verlaesst
  den angesagten Ort. Orts-Ansagen bekommen deshalb den reinen Zoom.
- **Der Himmel ist die ferne Ebene.** Der Welt-Lock (`scene_shift`) zog die
  Karte senkrecht 1:1 mit dem Nahbereich-Schwenk mit (bis 0.072 H). Parallaxe
  geht mit der Entfernung gegen null - 1:1 war auch physikalisch falsch.
- **Die Lehre ist dieselbe wie v214, eine Achse weiter: nicht nur ZEIT-Regeln
  muessen die Ansage respektieren, auch BEWEGUNGS-Regeln** (Kamera, Welt-Lock,
  Tracking, Anim-Drift). Wer eine neue baut, fragt zuerst: was macht sie mit
  einem `intent`-Moment, dessen Ansage eine Richtung nennt?
- Die Ansage steht als `p['ort_ansage']` AM PLAN. Sie muss dort stehen und
  nicht in `info`: eine Himmel-Ansage laeuft je nach Fall durch den ground-
  ODER den behind-Zweig, und nur der ground-Zweig schreibt `p['szene']` -
  ein Riegel daran haette in der Haelfte der Faelle nicht gegriffen (v159).
- Beweis: `camera_at` 107.3 px -> 0.0 px senkrechter Bildversatz; am
  gerenderten Bild mit Schwenk 40.4 px -> 4.4 px Weg der Tinte.

### ERLEDIGT (v215): Solo-Riegel mass die Lesezeit am falschen Punkt
Gleiche Verwechslung wie v214, eine Regel weiter: gerechnet wurde ab
`p['start']` (Anfang der WORTGRUPPE) statt ab dem Erscheinen der Karte.
`CAPTIONS` stand auf dem Papier 1.20-2.00, im Bild 1.80-2.00 - **0.20 s statt
der garantierten 0.80 s**. Behoben ueber `card_t0(p, words)`, der EINEN Stelle
fuer "wann erscheint die Karte wirklich".
**Beide Richtungen:** die richtige Messung allein haette das Blinzeln nur an
den Fliesstext weitergereicht (0.27 s). `_FLOW_MIN = 0.55` - muesste ein
wartender Block darunter, gibt die KARTE nach. Ein Block traegt die Woerter,
die gerade gesprochen werden; er wird nie beschnitten.
**Kein Bug war:** Woerter ohne Caption bei Dichte 'akzente'. Das Luecken-Netz
laeuft laut Code bewusst nur bei 'durchgehend' - Textpausen sind dort die
gewollte Handschrift. Der Alpha-Test suchte deshalb den Caption-Moment nicht,
sondern riet ihn (fest 1.20 s); er sucht ihn jetzt.

### Was in dieser Runde fertig wurde (v208-v219)
- v208/v208a Trichter + Test-Gate urteilt nach der Bilanz statt Textsuche
- v208b Ursache zuerst in der Fehlermeldung, ClientDisconnect ist keine Stoerung
- v209 Ansage-Wortschatz: line/one + Adjektiv zwischen Bestimmungswort und Nomen
- v209a/v213 Solo-Riegel Karte gegen Karte, ohne dass eine Ansage verschwindet
- v210 ai_flow_direct hatte kein `import requests` (NameError bei JEDEM Render);
  Denkbudget >= 2500 fuer gpt-5 (leere Antwort -> JSONDecodeError);
  Himmel-Ansage wird nicht mehr auf Kopfhoehe heruntergezogen
- v211 Blockmasse ins Job-Log (genau das hat den Befund oben moeglich gemacht)
- v212/a/b/c Tickets: geschlossen = dicht, nach 24 h aus der Kundenliste;
  Desktop-Lesebreite; KEIN color-scheme (machte Eingabefelder pechschwarz)
- v214 Ansage steht nie vor ihrem Wort (`intent` am Plan, 1.5-s-Vorlauf nur
  fuer NICHT angesagten Szenen-Text, Sofort-Hook + Beat-Grid respektieren die
  Ansage, `intent_time_floor()` als zentraler Riegel)
- v215 Solo-Riegel misst ab dem Erscheinen der Karte (`card_t0`), und ein
  wartender Fliesstext-Block behaelt seine Lesezeit (`_FLOW_MIN`)
- v216/v217 kein Text am Bildrand angeschnitten (`fit_into_frame`), Block-Log
  misst endlich Karten. Der Fliesstext-gegen-Fliesstext-Riegel ist RAUS: er
  verlaengerte den wartenden Block und liess denselben Satz doppelt stehen.
  **Eine Regel gegen Doppelbilder darf Zeiten nur KUERZEN, nie verlaengern.**
- v218/v219 Wand-Text sitzt in der gemessenen Wandebene (`wall_pose` aus der
  Tiefenkarte statt festem +-6-Grad-Wechsel; Wand hebt jetzt `flat_arr` auf).
  **v218 war toter Code:** der Block lag im nicht-getrackten Zweig, und bei
  einem Wand-Plan ist `tracked` IMMER wahr (need_track deckt das ganze
  Anzeigefenster ab). Der ground-Zweig hat DREI Zeichenwege (getrackt,
  ungetrackt, `front_layer`) - eine Sprite-Korrektur gehoert VOR die Weiche.
  Gefunden hat es nur ein Test, der `composite_frame` wirklich aufruft;
  Quelltext-Suche plus reine Funktionspruefung waren gruen (v193-Fehler).

### Noch offen aus den Renders
- **Zwei Fliesstext-Bloecke gleichzeitig sind IN ORDNUNG** (Ismets Ansage,
  31.07.2026). v230k hatte das ungefragt "repariert" und ist wieder raus.
- **Der Anschnitt ist mit v216 generell abgeriegelt** (`fit_into_frame` misst
  das FERTIGE Bild und verkleinert notfalls). Die URSACHE ist weiterhin nicht
  bekannt - sie liess sich mit nachgebautem Transkript nicht ausloesen. Wenn
  er wiederkommt: der Block-Log nennt jetzt Karten, Wortlaut und Zeitfenster,
  die herauslaufende Zeile traegt `<-- RAGT AUS DEM BILD`.
- 24 fps Quelle ruckelt auf dem Handy. Video technisch sauber gemessen
  (keine doppelten/fehlenden Bilder) - Ismet soll Seedance auf 30 fps stellen.
- 'above me' greift jetzt, am echten Material noch nicht bestaetigt.

### Vor dem Launch (Ismets Seite)
1. **Sicherung ausser Haus fehlt komplett** - Cloudflare R2, Schluessel in die
   .env auf dem Server, NIE im Chat. Groesstes Risiko.
2. UptimeRobot auf /api/health.
3. Ein echter Windows-Render mit echtem Material.
4. Demo-Video auf die Startseite.

## Offene echte Punkte
- Windows-Test mit echtem Material + Maskenqualität 'hoch' + MOV-Import Premiere.
- Semantik-Regie & v100-Animationen auf ECHTEM Material verifizieren (hier nur
  Heuristik/CPU/synthetisch getestet).

### Sicherheits-Rückstand (Stand v221, am Code nachgeprüft)
**Nur noch ZWEI Punkte offen — der Rest ist gebaut.** Nicht wieder als offen
führen: Dienst-Nutzer statt root (v204/v205a), Sicherheits-Ereignisprotokoll
(Tabelle `security_events`), FPS-/Auflösungsgrenze (`DVE_MAX_FPS`, Default 60),
Render-Subprozess bekommt nur noch eine Allowlist (`_ERLAUBT`, das einzige
echte Geheimnis darin ist `OPENAI_API_KEY`), Notaus (`_BETRIEB_STUFEN`
normal/pausiert/notaus, beendet auf Wunsch alle Sitzungen), `security.txt`
unter `/.well-known/`, gepinnte Bauteile in EINER requirements.txt.

1. **Sicherung außer Haus fehlt komplett. OFFEN — braucht Ismets Zugang.**
   `_mail_backup_offsite` steigt bei `ALERT_LEVEL != 'all'` sofort aus, und
   der Standard ist `important` — im Normalbetrieb liegt also KEINE Kopie
   außerhalb des Servers, und die vorhandene wäre unverschlüsselt (gzip per
   Mail). Stirbt die Platte, ist das Credit-Ledger zahlender Kunden weg.
   **Das größte Risiko im ganzen Betrieb.** Ismets Entscheidung (Juli 2026):
   **Cloudflare R2** (10 GB gratis). Hetzner Object Storage ist mit 7,72 €/
   Monat Grundpreis für eine 0,2-MB-Datei der falsche Dienst. Zu bauen:
   verschlüsseln vor dem Verlassen des Servers, eigener Schalter (NICHT an
   DVE_ALERTS hängen), 30 Stände, Prüf- und Rückhol-Knopf im Panel. Ismet
   legt Bucket + Schlüssel selbst an und trägt sie in die `.env` ein —
   **niemals im Chat.**
2. **Kein Lockfile mit Hashes.** Die Versionen sind exakt gepinnt (v205a), aber
   ohne Hash-Prüfung; die KI-Modelle werden weiter ohne Prüfsumme über
   `resolve/main` geladen. Wer das angeht, braucht ein `pip freeze` AUS DEM
   CONTAINER — die Sandbox-Versionen widersprechen requirements.txt, geraten
   zu pinnen blockiert nur Deploys.

**ERLEDIGT, nicht mehr als offen behandeln (v175, am Repo/Live geprüft):**
- **Sound-Pack liegt vollständig im Repo**: `sfx/pack` 14/14 Slots belegt
  (impact, whoosh, whoosh_soft, riser, tick, counter, boom, crack, fall,
  rise, turn, press, vanish, slam), Manifest `pack.json`, alle mit Ismets
  eigener Lizenz. Prüfen mit `python -c "import sfx_pack; print(sfx_pack.pack_status())"`.
  Videos sind NICHT stumm.
- **Stripe ist im Live-Modus** (Ismets Bestätigung). Keine Live-Umstellung
  mehr planen oder als offenen Punkt nennen.
