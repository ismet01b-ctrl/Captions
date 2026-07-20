# DouchkoVE Captions — Projektstatus (Juli 2026)

Automatische Premium-Untertitel im Editorial-Stil. Windows, C:\premium_captions, DirectML-GPU.

## Kern-Features
- **Motion: 3 neue Overlay-Templates + MOV-Alpha-Export (Premiere).**
  Ismet: "Viel mehr motion graphics. Als mov anwaehlbar fuer Premiere. Alles
  nur high end." (1) Neue Templates (Overlay-Klasse, KEIN DouchkoVE-Finale -
  gehoeren aufs Kunden-Footage): 'lowerthird' (Chip Name+Rolle slidet von
  links, Akzent-Balken), 'chat' (Bubbles abwechselnd links/rechts, Akzent-
  Bubble, Stack-Push), 'notify' (Banner droppen von oben, stapeln). Jetzt
  6 Templates x 4 Stile x 3 Formate. (2) MOV-Export: export='mov' rendert
  ProRes 4444 MIT Alpha (yuva444p12le, PCM-Audio, 60fps) via rawvideo-Pipe -
  ohne Hintergrund/Korn, Schatten halbtransparent; daneben IMMER fertig.mp4
  als Browser-Vorschau. VERIFIZIERT: ffprobe prores/yuva444p12le, Alpha-Frame
  87% transparent / 7% opak, Schachbrett-Composite sauber. (3) Web: Export-
  Segment (MP4 / MOV-Alpha), 6 Template-Buttons, /api/mov/{jid} Download,
  Library zeigt 'MOV - Alpha'-Button (has_mov). Browser-Smoke: 0 JS-Fehler,
  Spec korrekt. EHRLICH: MOV ~90MB/10s (ProRes-normal); Overlay-Templates
  auf 9:16 komponiert, 1:1/16:9 nutzen dieselben relativen Anker (geprueft
  als Standbild nur 9:16) - bei Bedarf Feinpolish.

- **Motion: Kundenfitness + Overlap-QA.**
  Ismet: "Mach alles fit fuer Kunden. Kontrolliere alles ob da was nicht
  ueberlappt." Overlap-QA ueber 4 Stile x 3 Templates (Standbilder):
  widgets-Karten ueberlappten (Battery/100% auf Kalender) -> neu als
  2-Spalten-Masonry mit Luecken, rechnerisch 0 Box-Overlaps. appstore-Titel
  lief unter den Open-Button -> txt_spr(max_w) skaliert den Titel auf die
  freie Breite (mit 'MySuperLongBrandName' verifiziert). Kundenfitness:
  _restore_jobs kennt jetzt Motion-Jobs (ueberleben Neustart - vorher Credit
  weg; live bestaetigt); Wasserzeichen fuer Nicht-Kaeufer (konsistent mit
  Captions). Voller Render rc=0 mit Audio; Web mobil ohne Overlap (0 JS-Fehler).
- **Motion-Graphics IN DER WEB-UI (Editor + Backend + Format).**
  Ismet: "Mach alle 3" (Presets+Feintuning, Standbild-Preview). Komplett
  verdrahtet - eigener Job-Typ, beruehrt die Caption-Pipeline nicht:
  (3) Format-Override (9:16/1:1/16:9) in gfx_engine (BASE=min(W,H)).
  (2) Backend server.py: GET /api/motion/schema, POST /api/motion/preview
  (1 Standbild ~2s, eingeloggt), POST /api/motion/render (Credits reservieren
  -> Job kind='motion' -> Queue). run_job-Branch + _run_motion() ruft
  gfx_engine als Subprocess (analog render.py), Fortschritt aus 'Frame x/y'.
  Kosten 1 Credit/Clip; Refund bei Fehler passt (cost_seconds(11)=60).
  (1) Frontend index.html: neue 'Motion'-Seite - Template/Stil/Format-Segmente,
  Woerter/Akzent/Motion/Grain-Regler, Bild+Logo-Upload, LIVE-Preview (<img>
  aus /preview, debounced), Render+Poll -> Library.
  VERIFIZIERT: TestClient (preview 200 PNG 2.4s, render 200, 60 Credits
  abgezogen, Job enqueued) + echter Headless-Browser (Motion-Seite rendert,
  0 JS-Fehler, Live-Preview-Bild geladen). EHRLICH: Motion-Job noch nicht in
  _restore_jobs (Neustart-Resume) beruecksichtigt; 1:1/16:9-Layout braucht
  Positions-Feinpolish; echter Server-Lasttest auf Windows/Prod steht aus.
- **UI-Motion: Web-Vertrag (Schema + JSON-Einstieg + Live-Preview).**
  Vorbereitung fuer die "full customizable" Web-UI, OHNE die Produktion
  anzufassen: (1) MOTION_SCHEMA + motion_schema() - Feld-Liste (Template/Stil/
  Format/Woerter/Akzent/Font/Bewegung/Korn/Vignette/Lift/Bild/Logo/SFX) mit Typ
  + Default-Quelle; das Frontend baut daraus automatisch die Regler, das Backend
  validiert dagegen. CLI --schema gibt es als JSON. (2) --motion-cfg <json>:
  EIN JSON {style,template,pills,image,cfg,preview} treibt den Render - der
  Einstieg fuer den Web-Job-Worker (analog render.py als Subprocess). (3)
  preview=<sekunde> rendert nur 1 Standbild (PNG) in ~2s -> Live-Vorschau bei
  jeder Regler-Aenderung; cfg-Override treibt nachweislich alles (Custom-Akzent
  faerbt Blitz/Balken/Zeiger/Fuellung). Fehlt noch: Format-Override (Engine
  aktuell fest 9:16), Frontend-Seite + Backend-Endpoint/Queue-Anbindung
  (naechster Schritt, Ismets Go).
- **UI-Motion: Micro-Life + Template 'appstore' (Prototyp).**
  Ismet: "1, 2, in der Web ui Full Customisible." (1) Micro-Life: Widgets
  leben - Basis (Material+feste Labels) wird EINMAL gebaut, w_paint malt pro
  Frame die dynamischen Teile: Prozent-Zahl + Balken rollen hoch (1->57%,
  ->100%), Uhrzeiger ticken, Progress-Balken fuellt, Kalender-Dots erscheinen
  nacheinander. (2) Template 'appstore' (Referenz-Video 2): Hero-Karte baut
  sich Element fuer Element auf - Icon/Titel/Untertitel/Open-Button/Rating-
  Zeile (4.8* gezeichneter Stern / 4+ / #1), gestaffelte Elastic-Einfluege.
  Jetzt 4 Stile x 3 Templates (pills/widgets/appstore). CLI --template.
  Web-UI-Full-Customize = naechster grosser Schritt (Plan an Ismet, Bestaetigung
  vor dem Bau der Web-Integration).
- **UI-Motion: Style-System + Einblendungen (Prototyp).**
  Ismet: "Ich braeuchte verschiedene Stile. Voll einstellbar. Eingefuegte
  Bilder sollten passend sein." -> render_ui_motion ist jetzt STYLE-getrieben:
  UI_STYLES (studio/dark/bold/mono) treibt Hintergrund (Mesh-Blooms), Karten-
  Material, Akzent, Font, Bewegungsstaerke, Korn, Vignette; cfg-dict
  ueberschreibt jedes Feld. image_card() montiert ein Nutzerbild ins GLEICHE
  Material (Radius, Rim-Glint, Boden-Schatten, Palette-Grade) -> "passend"
  statt Fremdkoerper; das Hero-Bild fliegt als Einblendung mit rein. CLI:
  --style/--image/--pills. Bloom-Fix: amt ist jetzt Spitzen-Helligkeit (col
  nur Farbrichtung) - vorher clippte der Bloom auf Dunkel zu Weiss. Prototyp
  in gfx_engine (--demo ui), noch nicht in der Web-Pipeline.
- **v97f: KI-Flow - GPT waehlt Anker-/Akzent-Wort der Flow-Captions.**
  Ismet: "Ich dachte die ki entscheidet fast alles." Bisher war das Flow-
  Keyword die Laengen-Heuristik (laengstes Inhaltswort) - wirkte zufaellig.
  Jetzt: `ai_flow_direct()` - EIN GPT-Call pro Video bekommt alle Filler-
  Chunks mit Wort-Indizes und waehlt pro Chunk das bedeutungstragende
  Anker-Wort (Substantiv/Verb/Zahl/Name) + optional ein emotionales
  Akzent-Wort (accent=null unterdrueckt bewusst auch den Heuristik-Akzent).
  Validierung strikt in `_parse_flow_sel()` (Index im Chunk, kein Fuellwort,
  Substanzlaenge) - Unsinn faellt still auf die Heuristik zurueck. Cache
  neben dem Input (_flow3.json), Log "KI-Flow: N Anker gewaehlt".
  compose_flow nimmt die Wahl per flow_sel, build_plans reicht flow_map durch.
  BEWEIS (Frames): Heuristik setzt 'EDITS' gross, KI-Wahl setzt 'CHEAP' -
  die Pointe, nicht das laengste Wort. Selftest 502/502 (5 neue KI-Flow-Tests)
  + render1/2c + GUI gruen. EHRLICH: Sandbox ohne echten Key - der echte
  GPT-Call ist auf Windows/Server zu verifizieren; Fallback-Pfad ist getestet.
- **v97e: Keine geparkte Hook-Karte bei aktivem Flow.**
  Ismet (Screenshot IMG_6578): "Es wird ein 'Titel generiert mit einem random
  Word' das bleibt die ganze Zeit oben (unpassend) und die captions kommen
  darauf. Ich dachte die ki entscheidet fast alles." Das oben stehende Wort
  war die Sofort-Hook-Karte (v48): das staerkste fruehe Keyword wird ab Frame 1
  fest oben geparkt, bis es gesprochen ist. Mit Flow ist das doppelt falsch:
  Flow baut ab dem ersten Wort durchgehend Captions auf (kein leerer Anfang,
  den man ueberbruecken muesste), und die geparkte Karte sitzt oben genau dort,
  wo der Flow-Text drueber laeuft -> Kollision + wirkt wie ein zufaelliger Titel.
  Fix: bei `caption_flow` wird NICHT mehr geparkt - das Keyword spielt normal
  zu seiner Sprechzeit (dramatischer Moment bleibt, nur eben nicht ab Frame 1
  oben festgenagelt). Ohne Flow bleibt der Sofort-Hook wie gehabt. Verifiziert:
  Flow an -> Keyword-Start = Sprechzeit; Flow aus -> Start 0. Selftest 497/497.
- **v97d: Flow-"Zoom ins Leere" behoben.**
  Ismet: "Der Zoom. Wohin zoomt der? Einfach so in die leere. Die captions
  wurden nicht verfolgt." Ursache (von v97 eingeschleppt): der else-Zweig
  uebernahm vom alten Stack die Seiten-Kamera (next_side_cam -> capzoom), die
  auf `p['target']` zoomt. Bei Flow war target=(W*0.07, zc) = leerer linker
  Rand auf halber Hoehe -> die Kamera zoomte ins Nichts, entkoppelt von der
  oben-links verankerten Caption. Fix: Filler-Flow bekommt `ccam='none'`
  (keine Zoom-Fahrt - ruhig wie die Referenz), target zeigt jetzt auf die echte
  Caption-Position (oben) statt zc (korrekt fuer die Ueberlappungs-Logik). Die
  dramatischen Keyword-Momente behalten ihre Kamera (crash/push/punch).
  Vorher/Nachher-Frames bestaetigt: altes Framing war ins Leere gezogen, neues
  bleibt natuerlich. Selftest bleibt gruen.
- **v97c: Flow-Caption Bewegung/Tracking + Preset-Umfang.**
  Ismet: "Ich will, dass sich auch mal captions passend bewegen, und diese mit
  Tracking verfolgt werden." + Frage nach Preset-Geltung. (1) SANFTES Folgen:
  der Flow-Block folgt der Person wieder, aber stark gedaempft (EMA 0.10) und
  eng begrenzt (Clamp W*0.045) - fuehlt sich verbunden an, wandert NICHT
  (der alte 0.22/0.09-Follow hatte die Struktur gebrochen). Schaltbar per
  `effects.caption_follow` (Default true). (2) Keyword-Settle: das getippte
  Anker-Wort landet minimal groesser und setzt sich weich auf 1.0 - gezielte,
  ruhige Bewegung statt Deko. (3) Preset-Umfang: Flow gilt fuer alle Presets
  ausser 'Clean' (dort caption_flow:false -> schlichte lesbare Untertitel, wie
  vorgesehen). Antwort auf die Frage: Flag steht global auf true in config.yaml,
  kein Preset ausser Clean ueberschreibt es. Selftest bleibt gruen. EHRLICH:
  Follow-Staerke ist auf ruhiges Talking-Head getunt - echte Wirkung bei viel
  Bewegung auf Windows pruefen; Feintuning der Daempfung/Clamp jederzeit moeglich.
- **v97b: Flow-Caption STRUKTUR (Nachbesserung).**
  Ismet: "Die captions haben keine Struktur, sie sind einfach irgendwo
  platziert." Ursache: (1) greedy Breiten-Umbruch + (2) Personen-Tracking
  liessen die Bloecke herumwandern. Fix: feste Zeilen nach ROLLE statt
  Breiten-Umbruch (Verbinder-vor-Keyword = Zeile 1, KEYWORD = eigene Zeile,
  Rest inkl. Kursiv-Akzent = Zeile darunter), alles LINKS buendig mit
  konstanter Zeilenhoehe; Block FEST im Bild verankert (kein Tracking mehr fuer
  Flow - stabile Position ist Voraussetzung fuer Struktur); Kursiv-Akzent ohne
  Rotation (die Kursive gibt den Slant). Auf echtem Clip verifiziert: klarer,
  konsistenter Aufbau statt Streuung. Selftest weiter 505/505.
- **v97: Flow-Caption-Effekt (Referenz-Look @migs.visuals) - Hybrid.**
  Ismets Ziel-Referenzen (2 Videos) sind reine Typo-Choreografie, nicht Deko:
  der Filler-Text baut sich INLINE Wort fuer Wort auf (stehend, ersetzt sich
  nicht), mit Hierarchie im Stack - Verbinder in mittlerer Support-Sans, EIN
  Anker-Wort gross+fett+GROSSBUCHSTABEN mit Glow (per Schreibmaschine enthuellt),
  ein Abschlusswort kursiv (Playfair) in Akzentfarbe. Entscheidung HYBRID:
  Filler-Captions fliessen im migs-Stil, die dramatischen KI-Keyword-Momente
  (behind/cascade/Kamera-Crash) bleiben unangetastet - DouchkoVEs Signatur +
  Referenz-Flow. Umsetzung: neue `compose_flow()` (Rollen/Layout mit Umbruch,
  Grundlinie unten), neuer `tpl='flow'` im else-Zweig von build_plans (nur wenn
  `effects.caption_flow: true`, sonst Rueckfall auf alten `stack`), Draw-Branch
  in composite_frame (Wort-Reveal, Keyword-Wipe ueber die letters, Kursiv-Pop),
  Block im OBEREN Drittel statt mittig ueberm Gesicht, knackiger Flow-Exit
  (x_dur 0.15) damit ein Satz raeumt, bevor der naechste an derselben Stelle
  steht. Sound: leiser Tick auf das Anker-Wort (sfx_engine, `flow`-Zweig, kein
  Riser/Boom - Filler klingt, dramatisiert nicht). Nutzt die LOOK-Fonts +
  Akzentfarbe (adaptiv). Auf echtem Talking-Head-Clip verifiziert (Frames).
  Selftest 505/505 (Logic 495 inkl. 9 neue Flow-Tests, render1 6, 2a/2b 1,
  2c 2) + GUI-Smoke OK. Nebenbei: render2c "Phrasen-Highlight" wurde
  API-unabhaengig gemacht (Cache mit gueltigem ref_fp, wie beabsichtigt).
  EHRLICH: Text im Demo ist Platzhalter - echtes Material zeigt Ismets KI-Texte;
  Keyword-/Akzent-Wahl im Filler ist heuristisch (laengstes Inhaltswort). Echte
  Wirkung auf Windows mit echtem Material + Sound-Pack pruefen.
- **v96z: Behind-Wort lesbar + Referenz-LOOK wird kopiert.**
  (1) Lesbarkeits-Bug (bestand unabhaengig vom Lernen): ein behind-Wort, das
  schmaler ist als der Kopf (~1.7x Gesichtsbox inkl. Haare), verschwand komplett
  hinter der Person. Jetzt wird die Schrift vergroessert, bis das Wort deutlich
  beidseitig herausragt; reicht das Randlimit nicht, kommt es UEBER den Kopf.
  Breite Woerter bleiben auf Personenhoehe (emerge intakt, Alt-Test gruen).
  (2) Stil-Kopie vertieft: der Parameter-Call sieht jetzt die Original-FRAMES
  und extrahiert zusaetzlich accent_hex (dominante Caption-Farbe) + density.
  _apply_reference_params kopiert beides deterministisch (Referenz-Farbe wird
  Caption-Akzentfarbe, schlaegt adaptive Szenen-Toene; Dichte uebernommen).
  Mehrere Referenzen werden gemittelt - je mehr, desto stabiler der Anker.
  WICHTIG: Referenzen einmal NEU lernen (alte Eintraege haben keine Farb-/
  Dichte-Parameter). Selftest 486/486 + render1/render2a green. EHRLICH: "Stil
  1:1 kopieren" heisst hier Farbe/Dichte/Chunks/Wucht/Hook - Fonts und exakte
  Animations-Looks bleiben unsere Engine.
- **v96y: Referenz-Einfluss SICHTBAR gemacht (deterministisch + UI-Beweis).**
  "Sieht 1:1 aus wie vorher" hatte nach v96x zwei moegliche Restursachen: der
  Prompt-Hinweis ist fuer GPT zu weich (deterministisches gpt-5 trifft bei
  aehnlichem Anker dieselbe Wahl), und niemand konnte SEHEN, ob Referenzen
  ueberhaupt aktiv waren. Beides behoben: (1) Beim Stil-Lernen extrahiert ein
  zweiter JSON-Call MESSBARE Parameter (words_per_group, min_gap_seconds,
  hook_strength, wucht) und speichert sie am Referenz-Eintrag ('params').
  `_apply_reference_params` wendet den Mittelwert der neuesten Referenzen
  DETERMINISTISCH auf die Config an (Chunk-Laenge, Highlight-Dichte, Hook,
  wucht -> Kamera/SFX-Pegel, gedeckelt) - der Effekt ist sichtbar, egal wie
  GPT den Prompt gewichtet. Log-Zeile "Stil-Anker: chunks=..., gap=..., ...".
  (2) UI-Beweis: der Server parst "Stil-Referenzen: N aktiv"/"Stil-Anker: ..."
  aus dem Render-Log in den Job-State; der Director's Cut zeigt "Style anchor:
  N learned reference(s) shaped this edit (...)" bzw. "No learned style
  references were active" - nie wieder raten. (3) Prompt-Anweisung verschaerft
  (VERBINDLICH fuer Dichte/Chunks/Wucht/Hook), Fingerprint deckt jetzt die
  ganze Referenz-Datei ab (auch Parameter-Aenderungen invalidieren den
  Regie-Cache). WICHTIG: bestehende Referenzen haben noch keine 'params' -
  einmal NEU lernen, dann greift der deterministische Anker.
  Selftest 483/483 + Render green.
- **v96x: Voll-Audit "KI wendet Gelerntes nicht an" - 4 Bruchstellen gefixt.**
  Kompletter Ketten-Audit (tcache, Presets/Looks, Referenz-Kette, Docker/Env)
  per 4 parallelen Quelltext-Pruefungen. Befund: Looks sind unschuldig (kein
  Preset setzt keywords.*), tcache cached nur das Transkript, Docker-Env sauber
  (DVE_DATA=/data, Volume persistent, env vererbt). Vier ECHTE Bruchstellen
  gefixt: (1) Regie-Cache-Bypass: existierte _regie3.json (Analyze-Flow,
  Re-Render nach Momente-Edit), lief ai_direct NIE - frisch gelernte Referenzen
  wirkten auf diese Renders nicht. Jetzt traegt _regie3.json einen ref_fp-
  Fingerprint; aendern sich die Referenzen, wird der Cache verworfen und die KI
  plant neu. (2) refs[:6]-Bug: der Loader nahm die AELTESTEN 6, der Store haengt
  neue hinten an - ab der 7. Referenz fiel das frisch Gelernte aus dem Prompt.
  Jetzt refs[-6:] (neueste). (3) Kein Anwendungs-Log: ein leerer Block war
  unsichtbar. Jetzt loggt ai_direct "Stil-Referenzen: N aktiv" bzw. "keine
  gefunden" - im Job-Log beweisbar. (4) Overrides/Templates konnten die KI-Regie
  abschalten oder das Modell pinnen: _sanitize_overrides liess die keywords-
  Sektion ungefiltert durch (alte gespeicherte Presets pinnten z.B. still
  ai_model='gpt-4o' gegen den gpt-5-Default; keywords:null crashte
  build_config). Jetzt Whitelist (include/exclude/auto/emphasize_last/
  min_gap_seconds) - ai/ai_model/ai_vision/ai_validate sind NIE per Client
  aenderbar (KI-Regie = Kern, nicht optional), Nicht-Dict-Sektionen fliegen
  raus. Bonus: server._reference_file nutzt exakt render._reference_store_path
  (kein Pfad-Split ohne DVE_DATA, relevant fuer Windows-lokal).
  Selftest 481/481 + Render green.
- **v96n: Aus Referenz-Videos lernen (Vision -> Stil-Referenz).**
  `analyze_reference_video()`: sampelt Frames eines High-End-Caption-Videos,
  laesst GPT-4o-Vision den STIL beschreiben (Pacing, Dichte, betonte Woerter,
  Effekt-Wucht, Hook) und legt das als Stil-Referenz in regie_reference.json ab
  (max 12). EHRLICH: die Regie-KI uebernimmt daraus EDITORIALE Entscheidungen
  (wo + wie stark), NICHT den exakten Look - Fonts/Animationen/Kamera kommen aus
  unserer Engine. Video-Dateien direkt in die JSON zu legen bringt nichts (der
  Text-Teil der KI kann kein Video ansehen) - erst die Vision-Analyse macht
  daraus einen nutzbaren Stilhinweis. Fehlertolerant ohne Key. Selftest 467/467.
- **v96p: Stil-Referenz-Menue nur fuer das Besitzer-Konto.**
  Statt Admin-Key jetzt an ismet-01_b@hotmail.de gebunden (per DVE_OWNER
  ueberschreibbar). `_owner_ok` prueft die Session (case-insensitiv), alle drei
  Referenz-Endpoints (list/learn/delete) sind darauf gegated; /api/me liefert
  `is_owner`, das Panel ist NUR fuer dieses Konto sichtbar (Server erzwingt es
  zusaetzlich). Kein Admin-Key-Feld mehr. Selftest 468/468.
- **v96o: Web-Button - Referenz-Videos ohne Terminal hochladen.**
  Account-Seite -> "Reference styles (admin)": Admin-Key, optionaler Name,
  Video-Upload -> `/api/reference/learn` laesst Vision den Stil beschreiben und
  speichert ihn; Liste zum Ansehen/Loeschen (`/api/reference/list`,
  `/api/reference/delete`). Alle drei Endpoints ADMIN-gated (timing-safe), weil
  Referenzen GLOBAL alle Renders beeinflussen - nicht jeder User darf den Stil
  aller aendern. Admin-Key wird lokal gemerkt. Selftest 468/468. EHRLICH: die
  Vision-Analyse braucht den echten OPENAI_API_KEY auf dem Server; Sandbox testet
  Endpoints/Auth/Struktur, nicht die Beschreibungs-Qualitaet.
- **v96m: KI schneidet nach aktuellem Standard + einspeisbare Trend-Referenzen.**
  Frage: waehlt die KI nach heutigem Standard, braucht sie Vorlagen/Trend-Bezug?
  Ehrliche Antwort: die KI funktioniert ohne Vorlagen, aber few-shot-Referenzen
  + ein expliziter Standard-Anker heben die Qualitaet und halten sie aktuell.
  Zwei Bausteine: (1) Fester Block AKTUELLER SHORT-FORM-STANDARD (2026) im
  Regie-Prompt - Hook in Sek 0-2, 2-3-Wort-Chunks, nur Schluesselwort betont,
  Bewegung mit Absicht, Eskalation zum Ende, Muster-Bruch. (2) `regie_reference.
  json` - Ismet legt dort aktuelle, starke Video-Beispiele als Prosa-Stilhinweis
  ab (Trend-Bezug); `_load_regie_reference` speist sie als STIL-REFERENZEN in den
  Prompt (Geschmack/Dichte/Wucht nachahmen, NIE die Woerter kopieren). Fehlt die
  Datei, laeuft alles wie bisher. So bleibt die Regie ohne Codeaenderung aktuell -
  neue Trends einfach in die JSON schreiben. Selftest 465/465 + Render green.
  EHRLICH: Wirkung nur mit echtem Key sichtbar; die mitgelieferten 2 Beispiele
  sind Platzhalter - ersetze sie durch echte aktuelle Referenzen.
- **v96l: Effekt-Audit + SFX-Luecke bei wuchtigen Animationen geschlossen.**
  Audit (alle grün): 26 Animationen sind implementiert (anim_apply), im Regie-
  Prompt angeboten UND vom Parser akzeptiert (Whitelist gegen ANIM_LIST). fx
  (behind/cascade/blurin/outline/ground) laufen alle, anim_apply wird auf JEDEM
  fx-Typ aufgerufen -> fx+anim+Kamera+SFX kombinieren sich frei; die KI kann pro
  Moment fx/anim/szene/lage/power/emoji unabhaengig setzen. GEFUNDENE LUECKE:
  nur 7 Anims hatten einen eigenen Action-Sound - wuchtige, sichtbare
  Animationen (explosion, zoom_punch, stempel, spur, rutsche, magnet, regen)
  knallten im Bild, blieben aber unter power 3 tonlos. Jetzt haben sie passende
  Einschlaege/Whooshes (slam/whoosh/turn/fall), der Anim-Sound laeuft ueber V()
  (Pitch/Pegel variiert). Selftest 462/462 + Render green.
- **v96k: Grosse Momente sehen wirklich verschieden aus (echter Fix).**
  v96i griff zu frueh: es prueft (fx, anim), aber Mehrwort-Hoehepunkte werden
  IMMER zur 'behind'-Komposition - der fx-Wechsel verpuffte, zwei Hoehepunkte
  sahen gleich aus. Jetzt wird die Kombi NACH dem Setzen aller sichtbaren
  Attribute geprueft: (Effekt-Ebene tpl, Animation, Einflug entr, Kamera).
  Wiederholt sich ein Hoehepunkt, wird die MOTION aufgebrochen - anderer Einflug
  + andere Kamera, und nur wenn's dann noch identisch waere, eine andere Impact-
  Animation. Kein zweiter Hoehepunkt bewegt sich mehr wie der davor.
  Selftest 461/461 + Render green.
- **v96j: Hoehepunkt-SFX klingt wirklich anders + Elapsed-Zeit ueberlebt Reload.**
  - **SFX**: v96i rotierte boom/slam/impact - hatte das Pack aber nur EINEN Boom,
    kam trotzdem immer derselbe Sound. Jetzt ein FESTER, klar hoerbarer Pitch-
    Versatz pro grossem Moment (Riser UND Einschlag, eigene Tabellen), zusaetzlich
    zur Slot-Rotation. Auch mit nur einer Boom-Datei klingt kein Hoehepunkt wie
    der davor.
  - **Elapsed-Timer**: beim Neuladen der Seite waehrend eines Renders sprang die
    verstrichene Zeit auf 0. Jetzt wird `renderStart` aus dem gespeicherten Job-
    Start (ts) wiederhergestellt - der Zaehler laeuft korrekt weiter.
  Selftest 461/461 + Render green.
- **v96i: Grosse Momente wiederholen sich nicht - weder visuell noch im Sound.**
  - **Visuell**: kein zweiter Hoehepunkt (power 3) mit derselben (Effekt,
    Animation)-Kombi. `big_used` merkt sich die benutzten Kombis; bei EXAKTER
    Doppelung wird zuerst ein anderer Effekt aus der Rotation gezogen, sonst
    wenigstens die Animation nicht wiederholt. Nur bei exakter Doppelung
    eingegriffen - die KI-Wahl bleibt sonst unangetastet.
  - **SFX**: der grosse Einschlag war immer riser+boom (identisch). Jetzt rotiert
    der tiefe Hit durch die vorhandenen Slots (boom/slam/impact) und V() legt
    Pitch/Pegel-Variation drauf - jeder Hoehepunkt klingt anders.
  Selftest 460/460 + Render green.
- **v96h: Editor-"behind"-Vorschau sitzt jetzt WIRKLICH hinter der Person.**
  Die v96g-Loesung (Text nur dimmen) reichte nicht - die Person war im flachen
  Thumbnail eingebacken, CSS konnte den Text nicht ZWISCHEN Hintergrund und
  Person legen. Jetzt echte Freistellung: `_person_cutout_png` matte pro Moment
  ein RGBA-PNG der Person (dieselbe RVM-Matte wie der Render, auf den Thumb-Frame
  angewandt, `{i}_cut.png`). Der Editor legt fuer 'behind' die Ebenen bg-Thumb ->
  Text -> Personen-Cutout - der Text sitzt sichtbar hinter der Person, genau wie
  im Video. Fehlertolerant: ohne onnxruntime/Modell kein Cutout, Vorschau bleibt
  flach (kein Crash). Thumb-Endpoint serviert jetzt auch .png. Selftest 458/458
  + Render green.
- **v96g: SFX-Sync + Hook-Variation + "behind"-Vorschau ehrlicher.**
  - **Klick-Sync**: die Tick-Akzente sassen bis zu 0.30s HINTER dem Wort
    (outline +0.26, blurin +0.30, cascade bis +0.27) - klang unsynchron. Jetzt
    eng am Onset (outline/blurin +0.08/+0.12, cascade +0.04/0.11/0.18).
  - **Hook-Variation / weniger Klick-Teppich**: der Folge-Caption-Akzent lief
    auf JEDER Caption -> im dichten Hook ein monotoner Klick. Jetzt im 3er-Zyklus
    lauter Tick / leiser Tick / GAR KEINER (Atempause), dazu V()-Pitch/Pegel-
    Variation. Weniger Klicks, mehr Abwechslung genau da, wo es auffiel.
  - **Editor-"behind"-Vorschau**: zeigte den Text hell VOR der Person (statische
    Vorschau ohne Freistellung) - wirkte falsch. Jetzt wird "behind" gedimmt und
    UNTER das dunkle Overlay gelegt, sitzt sichtbar "hinten". EHRLICH: echte
    Freistellung/Occlusion gibt es nur im Video, die Vorschau ist eine Andeutung.
  Selftest 456/456 + Render green.
- **v96f: Animations-Vorschau im Momente-Editor.**
  Wunsch: beim Waehlen einer Animation sehen, wie sie aussieht. Neu: die
  Vorschau-Zelle spielt eine CSS-Annaeherung der gewaehlten Animation ab
  (explosion/bruch/sturz/anstieg/spur/kippen/wende/puls/welle/gewicht/schweben/
  fokus/schwund/magnet/neon ... auf 15 Keyframe-Familien gemappt). Spielt beim
  Wechsel der Animation-Auswahl und beim Klick/Tap auf die Vorschau ab ("tap ▶"),
  nicht bei jedem Tastendruck. Rein clientseitig - kein Render, keine Kosten,
  sofortiges Feedback. EHRLICH: es ist eine Annaeherung fuer das GEFUEHL, nicht
  der exakte Render (der echte Effekt mit Person/Occlusion/3D kommt erst im
  Video). Frontend-Change (index.html), Python-Selftests unveraendert 454/454.
- **v96e: Kein Video sieht mehr aus wie das andere.**
  Zwei Ursachen fuer den "alle Videos gleich"-Eindruck behoben: (1) der
  Variations-Seed war nur die WORTZAHL - zwei verschiedene Videos mit gleich
  vielen Woertern bekamen dieselbe Stil-Mischung. Jetzt kommt der Seed aus dem
  INHALT (crc32 des Transkript-Texts): jedes andere Video -> andere, aber
  reproduzierbare Mischung; gleiches Video -> gleiches Ergebnis (Cache/Re-Render
  stabil). (2) Der Keyword-Effekt lief bei fehlender KI-Ansage stur ab Index 0
  (jedes Video: behind, cascade, blurin, ...). Jetzt ueber den seed-gemischten
  Rotator (Shuffle-Bag: jeder Effekt gleich oft, nie direkt doppelt) - die
  Effekt-Reihenfolge unterscheidet sich sichtbar. Auch die Start-Seite (side_
  toggle) haengt am Seed. Zusammen mit der KI-Regie (variiert ueber Inhalt +
  Prompt) und der SFX-Variation (v96d) fuehlen sich zwei Videos jetzt anders an.
  Selftest 454/454 + Render green.
- **v96d: Mehr SFX-Abwechslung (nicht immer derselbe Klick).**
  Der Tick/Klick lief oft (cascade-Buchstabenlaeufer, outline, blurin, Folge-
  Captions) - und jeder Slot hatte nur EINE Datei, also immer exakt derselbe
  Sound. Neu: (1) pro Slot koennen Varianten liegen (slot_1.wav, slot_2.wav ...),
  `load_variants` laedt alle, der Picker `V(slot)` wechselt reihum durch;
  (2) Mikro-Variation `_pitch` + Pegel-Jitter pro Platzierung (deterministische
  Folge) - so klingt selbst mit nur EINER Datei jeder Einsatz minimal anders.
  Alle wiederkehrenden Platzierungen (tick/whoosh_soft/whoosh/impact) laufen jetzt
  ueber V(). `fetch_pack` laedt beim Sound-Pack-Download bis zu 2 weitere CC0-
  Treffer je Slot als Varianten. Kein Synthetik, weiter nur echte CC0-Sounds.
  Selftest 451/451 + Render green. EHRLICH: hoerbar wird die Abwechslung erst
  im echten Ton (Sandbox prueft Varianten-Laden + Pitch-Shift, nicht den Klang).
- **v96c: Bessere Gesichts-Erkennung (auch nicht-frontal) + robustere Safe-Zones.**
  Wunsch: Gesichter, die nicht frontal in die Kamera schauen, muessen auch
  erkannt werden und die Safe-Zone bei mehreren Personen halten.
  - **Hoehere Detektions-Aufloesung**: BlazeFace sucht jetzt auf einem 1.8x
    hochskalierten Bild (`det_up`) - angewinkelte, halb abgewandte und kleinere
    Koepfe werden deutlich besser gefunden; Boxen werden zurueckskaliert.
  - **Niedrigere Confidence** (0.4 -> 0.25): faengt schwaechere/schraege
    Detektionen. Die dadurch moeglichen Fehltreffer siebt die Spur-Mindestlaenge
    wieder aus.
  - **Spur-Glaettung** (`_smooth_tracks`): dreht sich ein Kopf kurz weg (ein paar
    Frames ohne Detektion), wird die Luecke interpoliert und die Box an den
    Raendern gehalten - die Safe-Zone vergisst die Person NICHT mehr und der Text
    springt nicht auf sie. Einzelne Spuk-Detektionen (min_len<2) fliegen raus.
  - **Koerperbreite Safe-Zone** (`_free_x_multi` Faktor 1.3 -> 1.9): gesperrt wird
    Schulter-/Koerperbreite, nicht nur die Gesichtsbox - v.a. bei seitlich
    gedrehten Personen schneidet der Text niemanden mehr an.
  - Multi-Person wird aus den GEGLAETTETEN Spuren bestimmt (kurz abgewandte
    zweite Person zaehlt weiter als Gespraech).
  Selftest 449/449 + alle Render-Etappen green (Spur-Glaettung, Spuk-Filter,
  Safe-Zone synthetisch getestet). EHRLICH: die echte Erkennungs-Rate bei
  Profil-/Schraeg-Gesichtern ist nur auf Windows mit echtem Mehr-Personen-
  Material messbar; Sandbox-Clip hat keine Gesichter. BlazeFace bleibt ein
  Gesichts-Detektor - eine komplett vom Ruecken gefilmte Person hat kein
  Gesicht und wird nur ueber die gehaltene Spur (kurze Wegdreh-Phasen) erfasst.
- **v96b: Automatischer Modus-Schalter (Erzaehler / Talking-Head / Gespraech).**
  Ismet muss nichts umstellen - der Render erkennt selbst, was fuer ein Video es
  ist, und setzt die Captions passend. `_video_mode(face_frac, multi_person)`
  aus den Tracking-Statistiken:
  - **narrator** (Gesicht in <35% der Frames: Voiceover, Screen-Recording,
    B-Roll mit Erzaehler) -> zentrierte, editoriale Platzierung (face_pos/faces_at
    = None), und 'behind' wird zu 'outline' (ohne Person ergibt "hinter der
    Person" keinen Sinn).
  - **talking_head** (ein Gesicht meist im Bild) -> Face-relative Platzierung
    wie gehabt.
  - **conversation** (mehrere Personen, v96) -> Active-Speaker + Multi-Face-
    Safe-Zone.
  Der erkannte Modus wird ins Log geschrieben. Selftest 446/446 + Render green
  (der synthetische Clip hat kein Gesicht -> narrator-Zweig lief real durch).
- **v96: Multi-Person - alles funktioniert auch, wenn mehrere im Video reden.**
  Bisher war die Pipeline auf EINEN Talking-Head ausgelegt: das Face-Tracking
  behielt pro Frame nur das staerkste Gesicht (`max(score)`), darauf hingen
  B-Roll-Erkennung, Safe-Zone, Platzierung, Kamera und `face_cover`. Ein
  Gespraech mit zwei Personen konnte a) als B-Roll wegfallen (Groessen-/
  Identitaets-Filter) und b) Text ueber das zweite Gesicht legen.
  Jetzt (Hybrid, von Ismet gewaehlt): das Tracking erfasst ALLE Gesichter pro
  Frame, ordnet sie zu stabilen Personen-Spuren (`_faces_tracks`, Nearest-
  Neighbor) und bestimmt den ACTIVE-SPEAKER ueber die Mund-Bewegung (Frame-
  Differenz im unteren Drittel der Gesichtsbox, `_active_index`; ohne klare
  Bewegung -> groesstes Gesicht). Position/Kamera/Effekte/behind folgen dem
  aktiven Sprecher. Der Text weicht per Multi-Face-Safe-Zone (`_free_x_multi`)
  ALLEN Gesichtern aus (breiteste freie Luecke). Bei erkanntem Gespraech
  (>=2 Gesichter in >10% der Frames) werden Sprecher-Identitaets- UND Groessen-
  Filter abgeschaltet, damit kein echtes Gespraech als B-Roll verworfen wird.
  Bei nur einer Person aendert sich nichts. Selftest 442/442 + alle Render-
  Etappen green (reine Helfer synthetisch getestet: Spur-Zuordnung, Active-
  Speaker-Wahl, Safe-Zone, B-Roll-Fix). EHRLICH: Der Active-Speaker laeuft
  ueber eine Bewegungs-Heuristik (kein Audio-Visual-Sync-Modell) - bei schlechtem
  Licht/starker Ueberlappung kann er mal danebenliegen. Sandbox testet nur mit
  synthetischem Einzelperson-Clip; echte Zwei-Personen-Qualitaet siehst du erst
  auf Windows mit echtem Material.
- **v95c: KI entscheidet, ob "behind" hinter der Person sichtbar ist.**
  Problem: Bei einer Nahaufnahme (Person ganz nah an der Kamera, fuellt fast das
  ganze Bild) legt "behind" den Text hinter die Person und dimmt ihn - man sieht
  praktisch nichts. Loesung: Der Gesichts-Breitenanteil pro Moment (aus dem
  vorhandenen Face-Tracking, `face_w/W`) geht jetzt als "Person ~X% der Breite"
  in die Vision-Regie, plus SZENE_PROMPT-Regel: fuellt die Person das Bild, weg
  von "behind" hin zu sichtbar (outline/cascade/ground). Die KI ENTSCHEIDET pro
  Frame (kein Zwang). Dazu ein konservativer Backstop `_behind_cover_backstop`
  (Gesichts-Breite >= 52% -> power3 wird ground, sonst outline), der nur bei
  extremer Nahaufnahme greift und auch wirkt, wenn keine Vision-KI lief (kein
  Key). Selftest 436/436 + render1 green. Ehrlich: sichtbar erst mit echtem
  Material; Sandbox prueft Backstop-Logik + Prompt/Signal-Verdrahtung.
- **v95b: KI-Regie reagiert auf den Sound-Pegel.**
  Wunsch: Captions/Regie/Motion sollen an der ECHTEN Stimme haengen, nicht nur
  am Text. Neu: `_word_loudness()` misst den Sprech-Pegel pro Wort (RMS aus der
  vorhandenen wav, 50ms-Fenster) und markiert die lautesten Substanz-Woerter
  mit "!", die leisesten mit "~". Diese Marken stehen jetzt in der WORTLISTE,
  die an GPT geht - plus eine Prompt-Regel AUDIO-DYNAMIK: laute Woerter =
  starke Moment-Kandidaten, mehr power, wuchtigere Effekte/Anims (explosion,
  zoom_punch, bruch); leise = ruhig (cascade, schweben, wenig power) oder kein
  Moment. So sitzt die Caption-Wucht dort, wo die Stimme sie setzt. Der alte
  `_audio_boost` (Power-Bump NACH der KI, +1 Stufe) bleibt als Sicherheitsnetz.
  Additiv, kein Umbau: fehlt die wav, laeuft die Regie wie bisher. Selftest
  433/433 (synthetische laut/leise-wav + Prompt-Check). Ehrlich: die Sound->
  Effekt-Kopplung wirkt nur mit echtem Key + echtem Material sichtbar; Sandbox
  prueft die Pegel-Messung und die Prompt-Verankerung, nicht den Geschmack.
- **v95: Pre-Flow-Abrechnung repariert (Transkription ist gratis).**
  Frage von Ismet: "Kostet das Transkribieren Geld?" - Antwort: Nein, jetzt
  garantiert. Die Vorab-Transkription laeuft schon beim Datei-Auswaehlen
  (`mode: 'pre'`), waehrend der User noch Presets einstellt. Bug: der Upload
  buchte fuer JEDEN eingeloggten Modus atomar ab - auch fuer 'pre'. Wer ein
  Video auswaehlte und dann abbrach, verlor Guthaben; und `render_start`
  scheiterte danach am Balance-Check (Guthaben war schon weg). Fix: 'pre'
  prueft nur noch, ob genug Guthaben DA ist (kein Prewarming fuer 0-Credit-
  User, spart Whisper-Kosten), bucht aber NICHTS ab. Abgebucht wird erst
  atomar in `render_start` (der echte Render-Klick) - idempotent gegen
  Doppel-Klick/Retry ueber `_render_charged` (kein Doppel-Abzug), bei
  Render-Fehler erstattet `_maybe_refund`. Kein Gratis-Render-Loch, keine
  Falsch-Abbuchung. Selftest 430/430 (2 neue Abrechnungs-Checks). Ehrlich:
  Der Client-Fast-Path (Upload+Transkription beim Auswaehlen -> beim Render
  nur noch `render_start`) existiert seit v83; v95 macht die Geld-Logik
  dahinter korrekt.
- **v94: GPT-5-Regie, Hash-Kollisions-Fix, Retention-Psychologie, UI-Politur.**
  Root cause "Effekte kommen nicht": `_video_hash` las nur Anfang+Ende der
  Datei - zwei VERSCHIEDENE Clips teilten denselben Transkript-Cache (deutscher
  Plan wurde englischem Clip serviert). Fix: 8 Lesepunkte quer durch die Datei
  (+Selftest gegen Kollision). `language: auto` wird jetzt aus dem INHALT
  aufgeloest (`_looks_german`) - vorher liefen englische Clips unter
  Deutsch-Regeln (lowercase-Keywords verworfen). Regie-Modell per
  `keywords.ai_model: gpt-5` (Requests modell-kompatibel via `_oai_json`:
  `max_completion_tokens`, kein temperature bei neuen Modellen - sonst
  stiller Heuristik-Fallback). Dynamik nach Ueberdaempfung zurueckgeholt
  (Prompt lebendig, TikTok-Trail 0.22, person-sicher dank v93b-Maske).
  NEU: **Retention-Dramaturgie** im Regie-Prompt (Hook, offene Schleife,
  Muster-Bruch, Eskalation, Mikro-Belohnung) - die Psychologie bestimmt, wo
  Momente liegen und wie stark, in jedem Look auf seine Art; KI variiert
  bewusst (keine zwei Videos gleich), Garantien (Safe-Zones, Caps, kein
  B-Roll-Text) bleiben im Code. Ein deterministischer Aktion->Anim-Zwang wurde
  gebaut und auf Ismets Einwand REVERTIERT (Wort-Erwaehnung != Moment; die KI
  entscheidet kontextabhaengig). UI: dunkle Preset-Dropdowns (+Account-Inputs),
  Setup-Balken zeigt letztes Preset + "Save preset?" bei Aenderungen, eigene
  Presets als Dropdown auf der Look-Seite (bewusst KEINE Karten - sollen sich
  von unseren Presets unterscheiden), Sprach-Picker raus (Auto-Detect + Info).
  Selftests 425/425. Ehrlich: KI-Wirkung (gpt-5, Dramaturgie) ist nur auf
  echtem Material mit echtem Key sichtbar - Sandbox testet Struktur, nicht
  Geschmack.
- **v93b: Personen-Doppelgaenger in der TikTok-Voreinstellung behoben.**
  Frames von Ismet zeigten die Person halbtransparent gedoppelt (senkrechte
  Kamm-Streifen am Kiefer/Hals, Text mit Echo-Schatten `|||VIDEO`). Ursache:
  der Duplicate-Trail (`apply_duplicate_trail`) erkennt "Text" ueber ein Diff
  comp-vs-frame - Kamera-Schwenk/Grade verschieben aber auch die Personen-/
  Hintergrundkanten, die landen faelschlich in der Text-Maske und werden nach
  links versetzt gedoppelt. Die TikTok-Voreinstellung hatte `trail: 0.45`
  (zwei weitere Looks 0.30/0.35). Zwei Fixes: (1) Trail in ALLEN Presets aus
  (0.0) - der Effekt ist ein Diff-Hack, der Text nie sauber von bewegtem Bild
  trennt und wirkt billig, das Gegenteil von "wie ein Cutter". (2) Funktion
  gehaertet: mit Person-Matte wird die Person hart aus der Trail-Maske
  geschnitten - selbst wenn der Regler manuell an ist, kann die Person nie
  wieder doppeln. Selftest: neuer `_scenario_trail` (ohne Matte doppelt die
  Person, mit Matte nicht; echter Text bekommt weiter Trail; kein Preset hat
  Trail an). 416/416 + Render 10/10 gruen. Ehrlich: auf echtem Windows-Material
  muss Ismet gegenpruefen, dass der Geist wirklich weg ist.
- **v92-sec2: Zweite Audit-Runde (Konkurrenz-Vergleich Submagic/Opus/
  Captions.ai) - 9 Funde gefixt, alle per Selftest gesichert.** Nach dem
  ersten Audit ein vollstaendiger Vergleich "ist die Sicherheit wirklich
  gegeben, fuer alles". Kern (bcrypt, atomare Credits, Webhook-Signatur,
  server-seitige Preise, IDOR-Ownership, sichere Cookies, 256-Bit-Tokens)
  war auf Marktniveau. Neu behoben:
  1) **Admin-Endpoint gehaertet** (`/admin/codes`): erratbarer Default `admin`
     raus (fehlt `DVE_ADMIN` -> Endpoint tot), Schluessel jetzt per Header
     `X-Admin-Key` statt Query (landet sonst in Logs/History), `hmac.compare_digest`.
  2) **DSGVO-Loeschung wirklich komplett** (Art. 17): Konto-Loeschung entfernt
     jetzt auch die Job-Ordner (Original-Upload = Gesicht/Stimme, fertige
     Videos, Transkripte), den Transkript-Cache und `resets`/`verify_tokens` -
     vorher blieb das bis zum 7/30-Tage-Sweep liegen trotz "komplett loeschen".
  3) **Pfad-Traversal ueber `language` geschlossen**: der Sprach-Wert aus
     cfg_overrides floss ungefiltert in einen Dateinamen (`_tcache_path`,
     `shutil.copyfile`) -> `../../` haette fremde `.json` lesbar gemacht.
     Jetzt Regex-Whitelist (`[a-z]{2,8}|auto`) + gehaerteter Pfadbau.
  4) **SEPA-Doppelbuchung verhindert**: Webhook schreibt Guthaben nur noch bei
     `payment_status=='paid'` gut und lauscht auf `async_payment_succeeded` -
     vorher haetten verzoegerte Zahlungen Credits VOR Geldeingang gebracht.
  5) **Kauf-Gutschrift atomar+idempotent**: partieller UNIQUE-Index auf
     `ledger(user_id,'Kauf %')` + `INSERT OR IGNORE` -> zwei gleichzeitige
     Webhook-Retries koennen nicht doppelt gutschreiben.
  6) **Security-Header ueberall**: CSP, X-Frame-Options, nosniff, Referrer-
     Policy, HSTS - zentral in Caddy UND als App-Middleware. Vorher: null.
  7) **XSS-Haertung Frontend**: Upload-Dateiname server-seitig entschaerft
     (`_safe_name`) und im Client per `escHtml`/`textContent` gerendert
     (Library, File-Info, Summary, toast) - vorher roh via innerHTML.
  8) **Token-Einloesung atomar** (`_consume_reset`/`_consume_verify`): ein
     `UPDATE ... WHERE used=0` statt SELECT-dann-UPDATE (kein Doppel-Einloesen).
  9) **Login-Timing angeglichen**: bei unbekannter E-Mail laeuft trotzdem ein
     bcrypt-Check (Dummy-Hash) -> keine Enumeration ueber die Antwortzeit.
  Selftest 413/413 gruen (+10 Security-Tests). Bewusst NICHT hart gemacht,
  solange E-Mail-Zustellung (Resend-DNS) noch wackelt: Verifikations-Zwang vor
  dem Rendern und enumerierungsfreie Registrierung wuerden Nutzer aussperren,
  wenn keine Mail ankommt - Abuse ist ueber Trial-Cap (2 Min) + Rate-Limit
  (5 Registrierungen/h/IP) begrenzt; Kauf ist bereits an `verified` gebunden.
  Ehrlich: reine statische Analyse auf CPU, kein Live-Pentest.
- **v92-sec: Sicherheits-Audit vor Stripe-Live - Credits, Zugriffsrechte,
  Webhook.** Vollstaendiges Audit von Auth/Sessions/SQL/Credits/Stripe/
  Uploads. Solide war schon: SQL 100% parametrisiert, bcrypt, Session-Cookie
  httponly+secure+samesite, Video/Poster-Ownership, Webhook-Idempotenz,
  Upload-Limits, DB-Backup. Behoben (alles Code, per Selftest gesichert):
  1) **Credits-Race (Double-Spend) geschlossen**: Guthaben wird beim Upload
     ATOMAR reserviert (`_reserve_credits`: ein bedingtes UPDATE, das nur
     abzieht wenn genug da ist) statt nur geprueft und spaeter abgezogen.
     Frueher konnte man mit 1 Credit N Videos gleichzeitig hochladen und N
     Renders bekommen. Fehlgeschlagene Renders werden erstattet
     (`_maybe_refund`, idempotent, nur wenn kein Video geliefert wurde).
  2) **Stripe-Webhook ohne Secret wird abgelehnt** (503) statt durchgewunken -
     vorher haette ohne gesetztes Secret jeder ein gefaelschtes
     "Zahlung erfolgreich" schicken und sich Gratis-Guthaben schreiben koennen.
  3) **IDOR geschlossen**: Ownership-Check (`_job_owner_ok`) jetzt auf ALLEN
     Job-Endpoints (moments/transcript/thumb/status GET + moments/transcript
     POST) - vorher konnten Fremde ueber die jid Transkripte/Momente/Frames
     lesen bzw. fremde Jobs ueberschreiben.
  4) **Login rate-limited** (20/15min/IP, eigener Bucket) gegen Passwort-
     Brute-Force; Register/Reset hatten es schon.
  5) **cfg_overrides-Whitelist**: nur bekannte Config-Sektionen, teure Regler
     gedeckelt (Aufloesung <=1080p, ProRes-Master raus, Blender-Werte
     begrenzt) - kein Ressourcen-Missbrauch pro Render mehr.
  Selftest 403/403 gruen (+6 Security-Tests, isolierte Test-DB: Double-Spend-
  Race, Refund-Idempotenz, Overrides-Deckel, Webhook-Secret-Pflicht,
  Ownership-Abdeckung, Login-Limit). WICHTIG fuer Live: `STRIPE_WEBHOOK_SECRET`
  in der .env MUSS gesetzt sein, sonst verweigert der Webhook (Absicht).
- **v93: Szenen-Text ist Teil der Welt - liegt schon da, bewegt sich nicht,
  Neigung folgt der echten Flaeche.** Ismets Abnahme-Kritik am STREET-Frame:
  Neigung passte nicht zum Pflaster, und das Wort soll schon liegen, wenn
  die Kamera hinschwenkt - ohne Eigenbewegung. Umgesetzt fuer alle
  Szenen-Texte (Boden/Wasser/Wand):
  1) **Gemessene Neigung (ground_pose)**: Aus der Tiefenkarte wird am Anker
     die Fluchtrichtung der Flaeche gemessen (Naehe-Gradient): Roll folgt
     der Diagonale des Pflasters, Pitch der Staerke des Gefaelles;
     Draufsicht (uniforme Tiefe) = flach ohne Roll. Kein generisches
     yaw/pitch mehr. Lazy gemessen, sobald die Flaeche sichtbar ist.
  2) **Pre-Lying**: Szenen-Momente starten 1.5s vor dem Wort (t_word merkt
     sich den Sprech-Zeitpunkt). Ab t_word-0.6 versucht der Anker jeden
     Frame; gezeichnet wird erst, wenn die Kamera die Flaeche freigibt -
     die Kamera findet ein Wort, das schon da liegt. Wird das verankerte
     Wort vor dem Wort-Zeitpunkt komplett aus dem Bild geschoben, ankert es
     still neu auf der jetzt sichtbaren Flaeche.
  3) **Starr (rigid)**: liegender Text hat KEINE Eigenbewegung mehr - keine
     Track-Daempfung, kein Drift-Deckel, kein Einflug, keine Anim, kein
     Atmen. Er klebt exakt auf der Flaeche und verlaesst das Bild mit dem
     Schwenk wie ein echtes gemaltes Objekt. Nur schneller 0.12s-Fade beim
     ersten Erscheinen.
  4) **Anker v3**: Fenster ab t_word-0.6 (frueher = Track-Referenz in der
     Sprecher-Phase = Muell); Teilverdeckung bis 70% erlaubt (Arm vor dem
     Wort = Signature-Look); B-Roll-Band = Bildmitte der freigeschwenkten
     Flaeche (dort haelt die Kamera), Talking-Head-Band = unten; Decay-Union
     0.6 gegen den 'Geist' der Person; immer voll im Bild.
  5) **Schnitt-Erkennung entschaerft**: harter Pixel-Diff + KEINE kohaerente
     Bewegung (Phasen-Korrelation) = Schnitt. Ein schneller Schwenk ist KEIN
     Schnitt mehr - der Welt-Anker ueberlebt ihn (trk_fail-Toleranz 12).
  Beweis (echter Promo-Clip, Frames): STREET liegt ab ~0.1s VOR dem Wort
  voll lesbar mitten auf dem freigeschwenkten Pflaster (Draufsicht = flach,
  wie die Steine), bleibt starr und gleitet mit dem Rueckschwenk natuerlich
  aus dem Bild. Talking-Head-FIFTY (front_layer) unveraendert. Selftest
  397/397 gruen (+5: Pre-Lying-Start, 4x Bodenneigung). Ehrlich: das
  Lesbarkeits-Fenster diktiert die Kamerafuehrung (langsamer Schwenk +
  laengerer Hold = laenger lesbar); GPU-Matte/GPT prueft Ismet live.
- **v92: Interaktions-Pass - Captions tun, was gesagt wird, in JEDER
  Einstellung.** Systematischer Durchstich statt Einzelfixes; Ziel: das
  intelligenteste Caption-Tool, Text interagiert mit dem Gesagten.
  1) **'ground' wird immer honoriert**: Der Effekt ist eine PLATZIERUNGS-
     Ansage. Vorher wurde er im Talking-Head weggemappt, weil 'ground' in
     keiner Look-Rotation steht -> "liegt auf dem Boden" konnte mit Gesicht
     im Bild NIE auf dem Boden landen. Jetzt: Wunsch 'ground' zaehlt immer.
  2) **Szenen-Text ueberall (scene_ground)**: liegend (Boden/Wasser) und
     Wand-Text laufen jetzt auch MIT Person im Bild ueber den Premium-Pfad:
     Perspektive, Person-Okklusion, planares Kamera-Tracking, Matting-/
     Tiefen-Fenster. Kein stehendes Billboard mit Spiegelung mehr.
  3) **person_mask()**: bereinigte Personen-Maske (Opening gegen Bruecken,
     groesste Komponente, Dilation fuer Haare/Finger). Genutzt von Okklusion,
     Boden-Anker, Bokeh, kill_spill, Personen-Schatten und Repaste - die rohe
     RVM-Matte malte Halos um Hintergrund-Blobs (Autos, Pflaster).
  4) **Boden-Anker v2**: Union der Personen-Maske ueber die ersten ~3 Frames
     (eine Einzel-Maske ist bei Bewegung fragmentiert), avoid_x = Face-Track
     (Gegenseite der Person bevorzugen), Kaskade der Freiflaechen-Schwelle,
     nie ueber der Bildmitte. Findet er keinen freien Boden (Sprecher fuellt
     das Bild): **front_layer** - das Wort liegt perspektivisch VOR der
     Person (nach dem Repaste gezeichnet). Lesbar statt unsichtbar.
  5) **Fenster-Render-Bug**: need_depth/need_track wurden mit fi statt der
     absoluten Frame-Nummer (fa) indiziert - bei --window waren Tracking und
     Tiefen-Okklusion schlicht nie aktiv. Volle Renders waren korrekt.
  6) **Sprach-Intent v2**: Ansage gilt nur im SELBEN Satz wie das Keyword
     ("behind me." im Vorsatz zieht "STREET." nicht mehr um); bei mehreren
     Ansagen gewinnt die naechste; Umlaut-Varianten (ueber/über, straße).
  7) **Bokeh diszipliniert**: kein bg_blur auf Szenen-Text (die Szene ist
     der Star) und nur noch fuer echte Keyword-Momente (nicht fuer Stacks);
     Tiefenkarte raus aus dem Bokeh (Kanten-Halos).
  8) **REGIE_PROMPT**: Interaktions-Regel verschaerft - Platzierungen
     funktionieren in jeder Einstellung, mutig waehlen, wenn der Satz sie
     ansagt.
  Beweis (echter Promo-Clip, Frames geprueft): "FIFTY" liegt im Talking-Head
  lesbar vorn auf dem Boden (front_layer, kein freier Boden im Bild);
  "STREET" liegt weiter getrackt auf dem Pflaster (B-Roll, keine Regression);
  Halos massiv reduziert. Selftest 392/392 gruen (+4: Boden liegt im
  Talking-Head, Tracking/Spiegelung/Schatten-Regeln, Wand-Text,
  Intent-Satzgrenze). Ehrlich: CPU-Matte auf schwierigem Material zeigt
  weiter leichte Kanten; echte GPU-Qualitaet + GPT-Regie sieht Ismet auf
  dem Server/Windows.
- **v91: Boden-Text liegt wirklich auf der Strasse (nicht auf der Person).**
  Bug (aus echtem Promo-Clip): das grosse Signature-Wort ("STREET") auf
  B-Roll landete auf dem Pulli/Arm statt auf dem Pflaster. Zwei Ursachen,
  beide behoben:
  1) **Anker am Bild-Zentrum**: liegender Boden-Text wurde fix mittig
     verankert - bei einem Selfie-Kameraschwenk-nach-unten steht dort die
     Person. Neu: `ground_anchor()` nutzt die RVM-Person-Matte, spart die
     Person aus und sucht die klare Strasse (voll im Bild, Anker auf Boden,
     leicht vorne). Greift nur bei sichtbarer Person; echtes Aerial-B-Roll
     (kaum Person) behaelt den Standard-Anker.
  2) **Okklusion & Matte fehlten auf B-Roll**: die Person-Matte wurde in
     ground-B-Roll-Fenstern gar nicht berechnet, und die Tiefen-Referenz
     wurde am Text-Ort (= auf der Person) gemessen -> Okklusion griff nie.
     Neu: Matting laeuft auch in ground-B-Roll-Fenstern, und `occ_for`
     vereinigt Tiefe MIT der Person-Matte -> die Person laeuft sauber VOR
     dem liegenden Wort (Wort liegt hinter ihr auf dem Boden).
  3) **Wasser != fester Boden**: `scene_blend` (Wasser-Wellen/Refract) lief
     bisher auf JEDEM liegenden Text - Strasse sah "fluessig" aus. Neu:
     nur szene='wasser' -> `scene_blend`; fester Boden -> `ground_paint`
     (flach aufgemalt, kein Refract, wenig Ripple, leicht transluzent, die
     Pflaster-Textur scheint durch). Liegender Boden-Text wird ausserdem
     schmaler gefasst, damit er nach der Perspektive ganz im Bild bleibt.
  Zusatz (gleicher Promo-Fix): kurze isolierte Keyword-Momente auf B-Roll
  fielen an der 1s-Mindestbuehne raus, weil die Verlaengerung als "laeuft in
  B-Roll" abgelehnt wurde - fuer szenen-verankerten Text ist das falsch
  (er braucht die Person nicht). Jetzt darf broll-Text ueber das Wort hinaus
  stehen bleiben.
  Getestet (Sandbox CPU, synthetisch): Selftest 376/376 gruen (+2 fuer
  `ground_anchor`: meidet die Person / aus bei leerem Bild; "Liegend auf
  Boden" = ground_paint statt scene_blend). Am echten Promo-Clip verifiziert
  (Frames): STREET liegt flach auf dem Pflaster vor der Person, getrackt,
  voll lesbar, Arm deckt nur den oberen Rand. `broll_captions` bleibt eine
  Pro-Render-Option (Default = B-Roll textfrei), kein Default-Umbau.
  Echte GPU-/Qualitaetswirkung sieht Ismet erst auf Windows mit echtem
  Material.
- **v89: Wechselgruende sichtbar machen - anonyme Demo + Director's Cut.**
  Strategie-Erkenntnis: Der Produkt-Unterschied (Text IN der Szene statt
  Karaoke AUF dem Video) war vor dem Kauf unsichtbar; und "Credits statt
  Abo" stand nirgends. Umgesetzt:
  1) **10s-Demo ohne Account** (staerkster Hebel): Auf der Login-Seite kann
     jeder ein Video hochladen und bekommt die ersten 10 Sekunden mit
     Wasserzeichen gerendert - ohne Registrierung. Upload-Modus 'demo':
     kein Auth, kein Charge, erzwungen ['--watermark','--duration','10'],
     2 Demos pro IP pro Tag (in-memory, fuer Beta ausreichend). Nach dem
     Ergebnis: CTA "Create your free account for the full video".
  2) **Director's Cut auf der Fertig-Karte**: kleine Karte zeigt die von der
     KI-Regie gewaehlten Momente (Zeit, Wort, Effekt, Anim, peak) - macht
     die unsichtbare Regie sichtbar, genau das, wofuer man zahlt. Daten aus
     /api/moments (existierte schon).
  3) **Landing**: "Or try it on your own video first - free, no account" +
     "No subscription, ever"; Minuten -> Credits in der Hero-Zeile.
  Getestet: E2E im Sandbox-Server (Demo-Upload ohne Login 200, dritter
  Versuch am selben Tag 429), Demo-Worker-Branch per Stub verifiziert
  (Wasserzeichen + 10s erzwungen, kein Charge, status fertig), JS-Syntax +
  keine ID-Duplikate. Offen fuer spaeter: Landing-Side-by-side (braucht
  einen echten Beispiel-Clip von Ismet), Live-Frame-Preview pro Look,
  Stil-Klon (Referenzvideo -> eigener Look-Preset).
- **v88b: Logo, Fortschritts-Texte, Retro-Blur, Transkript-Cache.**
  1) **Logo** (DV-Monogramm) integriert: aus dem Screenshot freigestellt
     (Letterbox weg, Ink->Alpha) in Weiss-auf-transparent (`web/logo_white.png`)
     und Dunkel-Variante; Favicon = weisses Logo auf violettem Rundquadrat
     (`web/favicon.png`). Eingebaut in App-Header, Login-Hero und Landing-
     Header (neben dem Schriftzug), als Favicon (Routen /favicon.png|ico,
     /logo_white.png, /logo_dark.png) und ins Video-Wasserzeichen (Logo links
     vom "DouchkoVE"-Schriftzug, gleiche dezente Transluzenz).
  2) **Fortschritts-Texte** waren noch deutsch -> jetzt Englisch und kreativer
     ("Listening to every word you said …", "Our AI director is reading your
     script …", "Painting your video · second N · sliding text behind you" …).
  3) **Retro-Blur behoben**: `apply_duplicate_trail` erkannte "Text" per Diff
     comp-vs-Originalframe - auf Nacht-B-Roll (Blur/Grade/Warp veraendern das
     Bild ueberall) deckte die Maske fast das ganze Bild ab und der Trail
     schmierte alles zu. Guard: deckt die Maske > 6 % der Flaeche ab, kein
     Trail. Retro-Trail zusaetzlich 0.50 -> 0.35 gezaehmt.
  4) **Transkript-Cache** (Antwort auf Ismets Frage: ja, geht): pro Nutzer +
     Videoinhalt-Hash + Sprache. Dasselbe Video wird nie zweimal transkribiert,
     auch nicht nach erneutem Upload - Whisper-Aufruf faellt beim zweiten Mal
     komplett weg. Cache-Cleanup nach 30 Tagen. Sprachwechsel = eigener Key
     (re-transkribiert bewusst).
  Getestet: 374/374 logic + render1 gruen; Watermark-Frame visuell (Logo +
  Schriftzug), Logo/Favicon-Routen 200, Cache-Helfer (Hash stabil, Pfad,
  anon=None), Retro-Trail 0.35.
- **v88: UI-/Render-Feinschliff aus Ismets Feedback.**
  1) **Caption-Ueberlappung behoben** (der SHIBUYA/RIGHT-Doppelbild-Fehler):
     neue Modulfunktion `resolve_overlaps` verallgemeinert den v82-Stack-Fix
     auf ALLE Text-Momente. Ueberlappen sich zwei Captions zeitlich (inkl.
     Abgang) und liegen ihre Anker nah beieinander (< H*0.16 / < W*0.42), wird
     der fruehere vorgezogen, bis er raeumt, bevor der spaetere steht. Laeuft
     NACH der Hook-Logik (die t0 auf 0 zieht). Anker-Naehe schuetzt echte
     Neben-Platzierungen (links/rechts). +3 Selftests.
  2) **Live-Log entfernt** aus der Render-Fortschritts-Seite (zeigte rohes
     mediapipe-stderr, wirkte kaputt). Ersetzt durch einen ruhigen Beta-
     Hinweis: dauert in der Beta ein paar Minuten (CPU, Frame fuer Frame),
     nach der Beta nur noch Sekunden; Seite darf geschlossen werden, Video
     landet in der Library.
  3) **Beta-Badge auf der Landing-Page** (auch mobil) - kleines "Beta" neben
     dem Logo.
  4) **Verify-Mail persoenlicher**: warme Mail von Ismet statt Formbrief
     (Begruessung mit Username, Beta-Hinweis, "antworte einfach auf diese
     Mail").
  5) **Einstellungen entschlackt**: Step-3-Fine-Tune von 6 Akkordeons /
     ~26 Reglern auf 3 Akkordeons / ~11 Regler. Text&Pacing (Hook, Woerter
     pro Karte, Dichte, Sprache), Style&Effects (Font, Farbwelt, Wort-
     Effekte, BG-Blur, Freistellung), Camera&Output (Kamera-Staerke,
     Aufloesung). Entfernte Regler (hook_strength, instant_hook, chunk_hold,
     beat/music-sync, emerge, anim, freeze/trail/counter/split/env_shadow,
     crash/whip, adaptive, encode-speed, sfx-volume, master) behalten ihren
     Preset-Wert - nur aus der UI raus, Feature bleibt.
  Getestet: Selftest 374/374 logic + 10/10 render + GUI_OK; Playwright-Smoke
  durch die echte Web-UI (Landing-Beta da, 3 Akkordeons, 5 FX-Chips, 15
  Fonts, kein Live-Log, 0 JS-Fehler).
- **v87: Drei neue Web-Looks (Editorial / Poster / Retro).** Die Preset-
  Auswahl auf douchko.eu geht von 5 auf 8. Jeder Look ist eine vollstaendige
  High-End-Konfig (Effekte/Kamera/Farben/Schrift), bewusst mit eigener
  Schrift und eigenem fx/Kamera/Dichte-Profil, damit sie sich klar
  unterscheiden:
  - **Editorial** (Schrift Yeseva One, Serif): Magazin/"New Editorial" -
    Hochkontrast-Serifen, viel Ruhe, EIN Akzent, klassische Bewegung, ruhige
    Kamera. Der 2026er A24/Vox-Ton fuer hochwertig-redaktionell statt laut.
  - **Poster** (Schrift Staatliches, kondensierte Versalien): Plakat/Impact -
    grosse harte Statements, hoher Kontrast, ground/outline dominieren,
    punchy Kamera (crash/whip). Laut, aber kein Wort-Maschinengewehr.
  - **Retro** (Schrift Righteous, rund + Lobster-Script): warmer
    Retro/Vaporwave-Ton, Trails + Reflexionen, mittlere Dichte - fuer
    Musik/Lifestyle/Nightlife.
  Datengetrieben: PRESETS + LOOKS in web/server.py, Tiles bauen sich per
  /api/looks selbst, Font-Vorschau-CSS pro Look ergaenzt (@font-face war
  schon da). Nur Web betroffen - render.py/gui.py unveraendert, der
  Desktop-Preset-Satz (und dessen Selftest-Constraint) bleibt wie er ist.
  Getestet: build_config aller drei Looks valide (Fonts existieren), je ein
  echter 2s-Render lief sauber durch (exit 0, MP4 da - der eine Traceback ist
  der bekannte harmlose mediapipe-__del__-Shutdown), /api/looks liefert 8,
  default_config je Look die richtige Schrift, Preview-CSS ausgeliefert.
  render.py/gui.py unberuehrt -> Selftest bleibt 371/371 (v86).
- **v86: Farbwelt pro Shot + Baseline-Grid (Ruhe-Feinschliff aus dem Audit).**
  Zwei Quellen unnoetiger Unruhe beseitigt, die einzeln kaum auffallen, in
  Summe aber "billig" wirken lassen:
  1) **Farbwelt pro Shot statt pro Sekunde.** Die adaptiven Caption-Farben
     wurden auf `int(t)` gecacht - zwei Captions 0.4s auseinander ueber eine
     Sekundengrenze bekamen aus DERSELBEN Einstellung leicht verschiedene
     Toene (sichtbarer Tint-Sprung, obwohl sich das Bild nicht aenderte).
     `scene_palette_sampler` kennt jetzt die Schnitte (cut_times) und keyt den
     Cache auf den Shot-Index: alle Captions eines Shots teilen exakt eine
     Farbe, die Farbe wechselt nur dort, wo das Bild sowieso schneidet. Sehr
     lange Dauer-Takes duerfen alle 6s langsam nachziehen (Licht-Drift).
  2) **Baseline-Grid.** Querformat setzte cascade (0.39), outline (0.398) und
     stack (0.435) auf drei knapp verschiedene Hoehen - aufeinanderfolgende
     Momente unterschiedlichen Typs huepften minimal. Jetzt teilen sie EINEN
     Unteres-Drittel-Anker (Z_MAIN = H*0.40); 'behind' bleibt oben (Z_BEHIND
     = H*0.34), 'ground' die Bodenebene. Hochformat: v_zone rastet die Hoehe
     aufs Raster (H*0.025) und waehlt das Band (oben/unten) mit Hysterese
     (Grenze um H*0.34 muss deutlich ueberschritten werden) - Gesichts-Jitter
     verschiebt den Text nicht mehr kontinuierlich.
  Selftest: +4 Tests (cascade/outline auf einer Linie, Anker im unteren
  Drittel, Hochformat aufs Raster, Palette identisch ueber Sekundengrenze).
  Regression: 371/371 logic + 10/10 render + GUI_OK. Sandbox/CPU/synthetisch -
  echte Wirkung auf Windows mit echtem Material.
- **v85: Schnitt-Disziplin + echtes Kerning (Render-Craft aus dem Audit).**
  Zwei Typografie-/Timing-Punkte aus dem v82-Audit, die ein Video von
  "Auto-Pipeline" zu "handgeschnitten" heben:
  1) **Kerning.** `Sprites.text()` setzte jeden Buchstaben einzeln und schob
     ihn um seine eigene Ink-Breite vor - PIL wendet Kerning-Paare (VA, To,
     LT, Ta ...) aber nur an, wenn ein String am Stueck gezeichnet wird. Die
     Folge waren zu grosse Luecken an genau diesen Paaren (der klassische
     burnt-in-Tell). Jetzt wird pro Paar die echte Kerning-Korrektur
     abgezogen (`kern = adv(prev+ch) - adv(prev) - adv(ch)`), das Einzel-
     Setzen (fuer Schatten/Extrusion/Buchstaben-Boxen) bleibt erhalten.
     Nicht-gekernte Paare sind exakt wie vorher; Serif-Display spart real
     ~30px auf "TAVATo". Haengt an PIL-raqm (in Standard-Pillow-Wheels drin,
     im Sandbox verifiziert - auf Windows/Server beim ersten echten Render
     kurz gegenchecken).
  2) **Schnitt-Disziplin (BBC/Netflix-Regel).** Ein Untertitel darf nicht
     ueber einen harten Schnitt hinweg stehen bleiben. Die Szenen-Analyse
     kannte die Schnitte laengst, beendete laufende Captions aber nie daran.
     `track_faces` gibt die Schnitt-Frames jetzt mit, `build_plans` zieht das
     Ende jedes Moments so weit vor, dass sein Abgang (exit_env, bis ~0.32s)
     noch VOR dem Schnitt fertig ist (`cut_snap`, default an). Schnitte zu
     nah am Start werden in Ruhe gelassen (lieber kurzer Moment als
     Null-Frame-Blitz).
  Selftest: +5 Tests (Kerning-Invariante + Sprite rendert; Schnitt-Straddle
  mit/ohne Feature + Ende vorgezogen). Regression: 367/367 logic + 10/10
  render + GUI_OK. Sandbox/CPU/synthetisch - echte Wirkung sieht Ismet auf
  Windows mit echtem Material.
- **v84: Eigene Seiten statt Popups + private Video-Bibliothek + Credits (Web).**
  Grosser Web-UI-Umbau, alles ueber einen Client-Router (Hash-Routen
  #/create #/library #/billing #/account) - keine Modals mehr fuer History/
  Account/Kauf.
  - **Header:** "DouchkoVE" mit kleinem "Beta"-Badge, Top-Nav (Create /
    Library / Billing / Account), Credit-Chip (klickbar -> Billing),
    Username, Sign out. Auf Mobil scrollt die Nav, Username blendet aus.
  - **Library (neu):** private Bibliothek aller fertigen Renders des Users.
    Kachel mit Standbild (/api/poster, beim ersten Abruf aus dem Video
    gegriffen + gecacht), Klick spielt inline ab, Download-Button, und ein
    Ablauf-Countdown pro Video ("Deletes in 6d 23h", RETENTION_DAYS).
    Ownership hart: /api/video und /api/poster liefern 403 fuer fremde/
    anonyme Zugriffe, wenn der Job eine user_id hat. /api/library listet
    nur die eigenen fertigen Jobs.
  - **Billing (eigene Kategorie):** Guthaben gross oben, Credit-Pakete
    (Kauf), darunter Transaktionen (Kauf + Verbrauch als Ledger). Alles auf
    einer Seite statt zwei Popups.
  - **Account:** nicht mehr "Loeschen zuerst". Profil (Username, E-Mail,
    Mitglied seit, Verifizierungs-Badge + Resend), Plan & Credits
    (Guthaben, Wasserzeichen-Status, naechste Gratis-Credits), Passwort
    aendern, und "Danger zone" (Konto loeschen) eingeklappt ganz unten.
  - **Registrierung:** Username statt Vorname (3-24 Zeichen, Pflicht,
    Server- und Client-validiert; keine globale Eindeutigkeit erzwungen -
    reiner Anzeigename).
  - **Credits statt Minuten:** 1 Credit = 1 Minute, abgerechnet pro
    ANGEFANGENER Minute (cost_seconds), so ist die Balance immer glatt und
    die Credit-Anzeige nie krumm. Intern bleibt der Sekunden-Ledger. Pakete,
    Pre-Checks, Verbrauch, Header, History alles in Credit-Sprache.
  Getestet: Backend-Unit (cost_seconds/credits_of/username), Sandbox-Server
  E2E (register mit Username, /api/me, /api/library, /api/poster+Cache,
  Ownership 403 fuer fremd+anonym, pricing-credits) und ein Playwright-
  Smoke durch die echte SPA (Login -> Library-Kachel + Inline-Player ->
  Billing-Pakete -> Account-Infos -> Credit-Chip-Navigation), 0 JS-Fehler
  (nur favicon-404, vorbestehend).
- **v83: Sofort-Transkription beim Datei-Auswaehlen (Web).** Vorher: Upload +
  Whisper starteten erst beim Render-Klick - die Minuten, in denen der User
  Presets einstellt, waren tote Zeit. Jetzt: Beim Auswaehlen laedt die Datei
  sofort still im Hintergrund hoch (Job-Modus 'pre'), der Server laeuft
  render.py --transcribe-only und legt quelle_transcript2.json ab (den Cache
  nutzt der Render automatisch, war schon so). Der Render-Klick schickt nur
  noch Look/Settings an POST /api/render_start/{jid} - kein zweiter Upload,
  keine Whisper-Wartezeit. Details:
  - Klick waehrend die Transkription noch laeuft: next_mode wird hinterlegt,
    der Worker reiht danach selbst ein (race-sicher ueber atomares dict.pop,
    beide Seiten koennen den Auftrag nur einmal ziehen).
  - Sprache nachtraeglich geaendert: Transkript-Cache wird verworfen, der
    Render transkribiert mit dem richtigen Sprach-Hinweis neu.
  - Pre-Schritt scheitert (Netz, Key, was auch immer): NICHT fatal - Status
    wird trotzdem 'vorbereitet', der volle Render transkribiert selbst.
    Frontend-Fehler im Fast-Path fallen lautlos auf den klassischen
    Upload-Weg zurueck (inkl. 404 wenn der Pre-Job abgelaufen ist).
  - Nebeneffekt: der iOS-Stale-File-Fall (v80r) trifft den Fast-Path nicht
    mehr, weil die Datei schon auf dem Server liegt.
  - Abrechnung unveraendert: belastet wird erst der fertige Voll-Render,
    einmal pro Job. Fremde Jobs starten: 403. Guthaben-Check auch im
    render_start. Cleanup/Restore behandeln pre-Jobs wie alle anderen.
  Getestet im Sandbox-Server E2E: pre-Upload -> vorbereitet -> render_start
  (200, Job laeuft), Chained-Fall (Klick waehrend Pre laeuft -> haengt sich
  an), Fremd-User -> 403. Whisper selbst failt in der Sandbox am Dummy-Key -
  echter Durchlauf steht auf dem Server aus.
- **v82: Hand-Made-Motion-Pass (Senior-Cutter-Look).** Grundlage: Research-Sweep
  (5 Agenten) zu High-End-Caption-Design 2026/27 (Material 3 / iOS-Springs /
  Netflix-Timed-Text / AE-Praxis) + zwei Code-Audits von render.py. Kernbefund:
  Entrances waren stark (spring, morph, emerge, Motion-Blur), aber ALLE Exits
  linear und uniform - der klarste Vorlagen-Tell. Umgesetzt:
  1) `exit_env()`/`exit_pose()`: Exits halten erst fast voll (Ease-In 1-x^3)
  und lassen dann los, dazu 3% Scale-Settle + Richtungs-Drift. Exit-Dauer
  skaliert mit Schriftgroesse (0.20-0.32s), Power-3 haelt 40ms extra,
  Exit SPIEGELT den Entrance (edge geht seitlich raus, zoom nach vorn,
  Hintergrund-Text weicht nach oben). Aktiv-Fenster 0.25->0.40s (der alte
  /0.28-Fade wurde am Fensterrand hart abgeschnitten - sichtbarer Pop).
  2) `hand_jitter()`: deterministische Streuung pro Wort (Sinus-Hash) -
  Entrance-Dauern +-8-10%, Letter-Stagger +-0.5 Frames. Ein Cutter setzt
  nie zwei Keyframes exakt gleich; metronomische Gleichheit ist der Tell.
  3) Lese-Vorlauf 70ms: kleine Woerter/Tokens erscheinen VOR dem gesprochenen
  Wort (Broadcast-Praxis: Lesen fuehrt Hoeren, 50-100ms).
  4) Lineare Alpha-Rampen -> smoothstep (behind/ground/blurin); Cascade-Wipe
  mit ease_out statt Ladebalken-Linear; harte Pixel-Rises (26/10/30px) ->
  aufloesungsrelativ (H*0.024/0.009/0.028).
  5) Physik-Feinschliff: explosion = schneller ease_out-Impact + Feder-Recoil
  (6% ueber Ruhelage); magnet beschleunigt ins Zentrum (1-x^2) + 1-Frame-
  Landesquash; wackel mit zweitem inkommensurablem Sinus + Wort-Phase;
  Kamera-breathe mit 2. Frequenz (7.3s); Whip-Pan asymmetrisch (30% rein,
  70% settle); Beat-Sync-Decay zeitbasiert statt framebasiert (60fps-Material
  verfiel doppelt so schnell).
  6) Stack-Doppelbild-Fix: endet eine Gruppe nahtlos in die naechste an
  derselben Position, wird ihr Ende um die Exit-Dauer vorgezogen (Broadcast-
  Regel: nie zwei Texte uebereinander am selben Ort).
  BUGFIX dabei: 'explodiert' stand in ZWEI Anim-Hint-Listen (schub UND
  explosion); schub kam zuerst und schattete die explosion-Animation ab.
  Selftest: 5 neue Tests (exit_env-Kurvenform, Monotonie, exit_pose-Richtung,
  hand_jitter-Determinismus/Streuung); _regie_chunks-Test an v80d-3-Tupel
  angepasst. Regression: 362/362 logic + 10/10 render + GUI_OK (Sandbox,
  CPU, synthetisches Material - echte Wirkung prueft Ismet auf Windows).
  Hinweis Sandbox-Fixture: /tmp/st_transcript.json muss eine BLANKE Wortliste
  sein (kein {"words": ...}-Wrapper) mit realistischer Whisper-Schreibung
  (Substantive gross), sonst greift die v80d-Phrasenregel nicht.
  Ehrlich offen (v83-Kandidaten, aus den Audits): Captions an Schnitten
  clampen (Shot-Change-Regel), Kerning (PIL rendert per-Glyph), em-relatives
  Tracking, Baseline-Grid der 7 Vertikal-Anker, Palette pro Shot statt pro
  Sekunde, Counter-Arrival-Spring, instant_hook-Desync-Deckel.
- **v73-v81: Web-Plattform douchko.eu** (nur in Git-Historie dokumentiert):
  Accounts (E-Mail+Passwort, bcrypt, Verifikation), Stripe-Checkout+Webhook,
  Credits/Ledger, Free-Tier+Wasserzeichen, Transkript-Editor, 17 Sprachen,
  Hook-Score, Resend-Mail, Job-Restore, DB-Backups, Emoji-Rendering,
  Zwei-Stufen-Encode, Legal-Seiten (Impressum/Privacy/Terms).
- **v60: Herausschieben steuerbar + Maskenqualitaet.**
  1) HERAUSSCHIEBEN (`effects.emerge`: auto | immer | aus): Das Wort steckt hinter
  der Person und wird von ihr hervorgeschoben - erst der Teil direkt hinter ihr,
  dann waechst es gemaechlich nach beiden Seiten heraus (`reveal_from`). War vorher
  nur 1 von 8 zufaelligen Einflug-Arten und gar nicht steuerbar. 'immer' macht es
  zum Signature-Look.
  BUGFIX dabei: Das Wort lag auf fester Hoehe (H*0.292) - bei hoch sitzendem Kopf
  UEBER der Person. Dann verdeckt sie nichts und der ganze Effekt ist unsichtbar.
  Jetzt wird es an die Gesichtshoehe gehaengt (face_y - H*0.055), damit es die
  Person wirklich ueberlappt. Per Selftest erzwungen.
  2) MASKENQUALITAET (`matting_quality`: standard | hoch | maximum): Das Matting-Netz
  rechnet die Maske intern VERKLEINERT - bisher auf 25 % (CPU). Genau daran haengt,
  ob Haare und Schultern sauber freigestellt sind oder ob die Kante matscht.
  'hoch' (Empfehlung) rechnet 1.6x feiner, 'maximum' 2.2x. Dazu: Kantenverfeinerung
  ZWEISTUFIG ab Qualitaet 'hoch' (zweiter Guided-Filter-Durchgang mit kleinem Radius
  holt Haarstraehnen und Brillenbuegel zurueck, die der grobe erste Durchgang
  glattbuegelt). Zeitliche Glaettung jetzt BEWEGUNGSABHAENGIG: bei schneller
  Bewegung wuerde das Mitteln einen Geisterschatten hinter der Person ziehen.
  GUI: neue Karte "Freistellung & Masken" unter Effekte. (Logic 172/172, gesamt 185/185.)
- **v59: Web-Version** (`web/`): kein Download, kein Setup. Nutzer oeffnet Link,
  laedt Video hoch, bekommt es fertig zurueck. OpenAI-Key liegt AUF DEM SERVER
  (nie beim Nutzer - in einer .exe waere er in 2 Minuten ausgelesen). Zugangscodes
  mit Kontingent (`web/codes.py`), Warteschlange, Docker. Ende-zu-Ende getestet.
  Naechster Schritt: Ismet mietet Server (netcup VPS 2000 G12, 8 vCPU/16GB, ~14 EUR),
  dann Deployment. Web-Anleitung: `web/ANLEITUNG_WEB.md`.
- **v57: Alles bleibt erhalten + iPhone-Klappkarten.**
  1) BEIM SCHLIESSEN wird alles gesichert (`on_close` an WM_DELETE_WINDOW):
  Einstellungen -> config.yaml, Freesound-Key -> sfx/.freesound_key, zuletzt
  geoeffneter Bereich + Klapp-Zustand der Karten -> ui_state.json, und NEU auch die
  FENSTERGROESSE. Das Programm geht genau so wieder auf, wie es geschlossen wurde.
  2) BUGFIX KUNDENPROFIL: `PROFILE_VARS` liess vier Kamera-Schalter aus
  (capzoom/drift/freq/kwcam). Die werden zwar aus der Dynamik abgeleitet - aber
  wenn beim Kundenwechsel die Dynamik gleich bleibt, feuert der Ableiter nicht und
  die Werte des VORIGEN Kunden blieben heimlich stehen. Jetzt vollstaendig (23
  Einstellungen). Selftest erzwingt, dass kein `*_var` mehr fehlen kann.
  3) KLAPPKARTEN im iPhone-Stil: jede Karte hat einen Pfeil rechts, klappt auf und
  zu; der Zustand ueberlebt den Neustart. Im Sound-Vorhoerpanel klappt "Andere"
  beim zweiten Klick wieder ein.
  Der API-Key liegt BEWUSST NICHT im Kundenprofil - er gehoert zum Rechner, nicht
  zum Kunden. (Logic 156/156, gesamt 169/169.)
- **v56: SFX-Auswahl bewertet statt blind meistgeladen (Crash-Bug).**
  BEFUND aus dem Test: es krachte bei Woertern, bei denen nichts zerbricht.
  URSACHE: `sort=downloads_desc` + `pick=0` - es wurde stur der meistgeladene
  CC0-Treffer genommen. Und der meistgeladene CC0-Sound zum Wort "impact" ist auf
  Freesound ein Glas-Crash. Der landete im HAUPT-Slot und knallte damit bei jedem
  grossen Wort. (Die Animations-Logik war unschuldig - per Test geprueft: bei
  neutralem Text loest keine Animation aus.)
  FIX: `score(cand, slot)` bewertet jeden Kandidaten. Jeder Slot hat jetzt ein
  ZIELMASS (ideale Laenge - ein 3-s-Impact taugt nichts) und AUSSCHLUSSBEGRIFFE
  (impact meidet glass/crash/shatter/explosion/gun/scream ...). Bewertung schlaegt
  Download-Zahl. Tags werden mitgeladen und fliessen in die Bewertung ein.
  Belegt per Selftest: der Glas-Crash faellt im Impact-Slot auf den letzten Platz
  (trotz 50k Downloads) und gewinnt im Bruch-Slot - dort gehoert er hin.
  Vorhoer-Panel zeigt jetzt die Schlagworte, damit sichtbar ist, WAS ein Sound
  ist (ein "Impact" kann ein Glas-Crash sein). (Logic 147/147, gesamt 160/160.)
- **v55: Suchkaskade (leere Slots gefixt) + skalierende GUI + Menue-Struktur.**
  1) BUGFIX LEERE SLOTS: 9 von 14 Sound-Slots blieben leer. Ursache: pro Slot gab
  es EINE Anfrage mit vier Suchwoertern + engem Laengenfilter + CC0-Filter. Passte
  eine Bedingung nicht, kam null zurueck - ohne Ausweichversuch. Jetzt hat jeder
  Slot eine KASKADE: 4 Suchbegriffe von eng nach breit, und zur Not faellt der
  Laengenfilter weg. Laengen-Fenster ausserdem grosszuegiger. Selftest simuliert
  den Haertefall (nur breite Einwort-Suchen ohne Laengenfilter liefern etwas) -
  kein Slot bleibt leer.
  2) GUI SKALIERT MIT (`on_resize`): Alle Erklaerungstexte sind in einem Register
  (`_wrap`) mit Breiten-Anteil und brechen beim Vergroessern neu um, statt schmal
  zu bleiben. Schrift-Kacheln fliessen um (`reflow_fonts`). BUGFIX dabei: Kachel-
  breite mit 118 px zu klein geschaetzt (real ~172) - die Kacheln liefen rechts
  aus der Karte raus.
  3) MENUE-STRUKTUR: aus 3 ueberladenen Bereichen wurden 7 thematische:
  Video · Hook · Text · Effekte · Sound · Ausgabe · Profi (NAV-Dict, Sektionen
  werden daraus gebaut). ttk-Combobox dunkel gestylt (das weisse Standardfeld
  zerriss den Look). (Logic 144/144, gesamt 157/157.)
- **v54: Synthetische Sounds ERSATZLOS entfernt.**
  Die aus Formeln erzeugten Sounds (Sinus + Rauschen) klangen billig - kein
  Messwert der Welt aendert das. Sie sind komplett raus: alle 14 Generatoren,
  `_phantom_sub`, `_bandsweep_noise`, `_reverb`, die ganze Klangsynthese.
  Selftest erzwingt, dass sie nicht zurueckkommen.
  KONSEQUENZ (bewusst): Ohne Sound-Pack laeuft das Video OHNE Sound-Effekte.
  Kein Rueckfall, keine Ersatztoene. Lieber Stille als ein billiger Sound.
  Renderer und GUI sagen das deutlich, statt still etwas Schlechtes zu tun.
  Fehlende einzelne Slots werden uebersprungen (place() prueft), nicht ersetzt.
  ZAEHLER-SOUND: wurde frueher in passender Laenge SYNTHETISIERT (der Sound musste
  exakt so lange rollen wie die Zahl hochzaehlt). Jetzt aus den ECHTEN Ticks des
  Packs gebaut: ausrollende Ticks + Einschlag auf der Zielzahl.
  BUGFIX: `bank.get('impact') or bank.get('slam')` crashte - `or` auf numpy-Arrays
  ist mehrdeutig. Vom Selftest gefangen.
  Selftest: die Pruef-Toene baut der TEST selbst (Attrappe, kein Produkt-Code);
  das Render-Szenario legt ein Test-Pack an, sonst waere der SFX-Weg ungeprueft.
  Entfernt: die Tonhoehen-Tests (Sturz muss abwaerts klingen) - bei echten
  Aufnahmen entscheidet das Ohr beim Vorhoeren, nicht eine Messung.
  (Logic 140/140, gesamt 153/153.)
- **v53: Sound-Pack — echte Aufnahmen statt Synthese (`sfx_pack.py`).**
  Die eingebauten Sounds sind aus Formeln erzeugt (Sinus + Rauschen) und klingen
  darum zwangslaeufig billig. Eine Studio-Aufnahme holt man mit Mathematik nicht
  ein — egal wie gut die Messwerte sind. Loesung: das Programm laedt echte Sounds.
  LIZENZ (der eigentliche Knackpunkt): Epidemic-Sound-Dateien duerfen NICHT in die
  Software eingebettet werden — sie sind an ein Abo gebunden, das waere eine
  Lizenzverletzung. Darum: Bezug ausschliesslich ueber Freesound mit CC0-Filter.
  CC0 = Public Domain: kommerziell frei, keine Namensnennung, Weitergabe erlaubt.
  Der Filter geht an die API UND wird im Code nochmal geprueft (doppelt gesichert);
  CC-BY und CC-BY-NC werden verworfen. Selftest erzwingt das dauerhaft.
  14 Slots (impact, whoosh, riser, crack, fall, rise, turn, press, vanish, slam …),
  je mit eigenen Suchbegriffen und Laengen-Filter. Download -> WAV -> Stille weg ->
  loudnorm, damit das Timing exakt sitzt.
  RANGFOLGE: eigene Datei (sfx/pack/<slot>.wav, z.B. spaeter aus Epidemic) >
  geladener CC0-Sound > synthetischer Rueckfall. Eigene Dateien werden NIE
  ueberschrieben (Manifest-Flag 'eigen'), sie bleiben beim Nutzer und stecken nicht
  in der Software — damit ist der Epidemic-Weg legal offen.
  GUI: Karte "Sound-Pack" (Key-Feld, "Echte Sounds laden") + Vorhoer-Popup: pro Slot
  die Kandidaten anhoeren und auswaehlen. Bewusst so gebaut: welcher Sound GUT
  klingt, kann kein Programm messen — das entscheidet das Ohr.
  Der Freesound-Key liegt lokal in sfx/.freesound_key (oder FREESOUND_API_KEY),
  nie im Repo. Neue Selftests: 6 (Logic 142/142, gesamt 154/154).
- **v52: Sound-Design 2026 (mobile-first) + Animations-SFX + GUI im Apple-Stil.**
  1) ANIMATIONS-SFX (`sfx_engine.ANIM_SFX`): Die Sounds hingen bisher NUR am Effekt —
  ein Wort das zerbricht klang wie eines das aufsteigt. Jetzt hat jede EREIGNIS-
  Animation einen eigenen Klang als Ebene ueber dem Effekt-Sound: bruch→crack,
  sturz→fall, anstieg→rise, wende→turn, druck→press, schwund→vanish, knall→slam.
  Die sechs ZUSTANDS-Animationen (glitch/puls/welle/zittern/neon/schub) bleiben
  bewusst stumm — Dauer-Zustaende brauchen keinen Einzel-Sound.
  Selftest misst die Tonhoehen-RICHTUNG: Sturz 1033→180 Hz (faellt), Anstieg
  280→1280 Hz (steigt). Ein Sound, der luegt, faellt durch.
  2) MOBILE-FIRST NEUBAU der ganzen Bank (v8). Der alte Satz war Kino-Trailer-Logik:
  fetter Sub, viel Hall, 2-3 s lange Ausklaenge. Gemessen: Boom hatte 99 % seiner
  Energie unter 150 Hz, Impact 97 %, Slam 97 % — Handy-Lautsprecher geben unter
  ~150 Hz nichts wieder, die Kern-Sounds waren auf dem Zielgeraet praktisch LAUTLOS.
  Neu: Wucht ueber Obertonstapel statt Sub (`_phantom_sub` — das Ohr rekonstruiert
  den fehlenden Grundton), Hall von wet 0.20-0.30 auf 0.04-0.14, Ausklang-Trim
  (`_trim`), helle Transienten (`_snap`) fuer Definition. Ergebnis im Handy-Band
  (150 Hz-10 kHz): Boom 1 %→62 %, Impact 3 %→67 %, Slam 2 %→63 %. Dauern von
  2-3 s auf 0.07-1.03 s. Punchline (knall) sitzt mit x1.18 lauter (Feed-Standard).
  Selftest erzwingt beides dauerhaft: >=55 % im Handy-Band, <=1.1 s.
  NICHT eingebaut: virale Meme-Sounds (Metal-Pipe u.ae.) — fremdes lizenziertes
  Audio, in Wochen veraltet, und unter einem Business-Talking-Head unpassend.
  3) BUGFIX Selftest: 'SFX volle Abdeckung' pruefte ein festes Zeitfenster und war
  nur deshalb gruen, weil der alte Boom 3.2 s lang war und mit seinem Schwanz
  hineinragte. Die Sounds haengen am Wort-Zeitpunkt — jetzt wird dagegen geprueft.
  4) GUI im Apple-Stil: echte runde Karten (`Card` auf Canvas — tk-Frames koennen
  keine Radien), iOS-Schalter, macOS-Segmente, ECHTE Regler (`Slider`: ziehen,
  klicken, gefuellte Bahn, Wert daneben — vorher das rohe tk.Scale). Zeilen-Layout
  statt Textwaende: links Name + kurze Erklaerung, rechts das Bedienelement.
  Systemblau als einziger Akzent, groesseres Fenster, und durchgaengig ECHTE
  UMLAUTE (vorher "Laenge/Staerke/gewaehlt" — sah nach Bastelei aus).
  Verifiziert per Screenshot auf virtuellem Bildschirm (Xvfb), nicht blind gebaut.
  Neue Selftests: 8 (Logic 136/136, gesamt 148/148).
- **v51: Sechs neue Animationen (deutscher Sprachgebrauch) + wortgenaues Matching.**
  Neu: `sturz` (faellt/kippt weg, Schwerkraft-Kurve), `anstieg` (steigt + skaliert),
  `wende` (Drehung um die Hochachse via Breiten-Skalierung, kommt LESBAR zurueck —
  kein Spiegeltext), `druck` (vertikale Stauchung + Absacken), `schwund` (fleckige
  Alpha-Aufloesung ueber geglaettete Rausch-Maske, steigt auf; loest sich nur bis
  42 % auf, bleibt lesbar), `knall` (Einschlag 1.45 -> 1.0 in 0.14 s + Nachbeben).
  Zusammen mit den bestehenden: 13 Animationen.
  WORTGENAUES MATCHING (`_anim_hit`): Die alte Teilstring-Suche war eine Falle —
  'fällt' schlug in 'gefällt' an, "das gefaellt mir" haette das Wort abstuerzen
  lassen. Jetzt zaehlt der Wortanfang; nur Stichwoerter ab 7 Zeichen duerfen mitten
  in Komposita stecken ('Staatsschulden' -> druck). Mehrdeutige Woerter bewusst
  NICHT als Ausloeser: 'mehr' ("nicht mehr"), 'genau'/'sicher' (Fuellwoerter),
  'weg' (der Weg), 'gefallen' (= gefaellt mir). 14 Fallen-Testsaetze im Selftest.
  BUGFIX aus v50: `bruch` fehlte im Momente-Editor-Dropdown (nur render kannte ihn).
  Selftest prueft jetzt, dass GUI UND Regie-Prompt ALLE Animationen kennen.
  BUGFIX Selftest: 'Animation X wirkt' mass nur bei dt=0.4 s — Einschlaege wie
  `knall` (wirkt nur in den ersten 0.30 s) fielen faelschlich durch. Misst jetzt
  ueber mehrere Zeitpunkte. Neue Selftests: 18 (Logic 129/129).
- **v50: Bruch-Animation (satzbewusst) + Farbwelten.**
  1) BRUCH (`anim: bruch`, 7. Animation): Das Wort zerbricht. `_bruch_shards()`
  schneidet 4 Scherben entlang gezackter, aber DURCHGEHENDER Bruchkanten
  (Sinus-Zacken + entlang y geglaettetes Rauschen — rohes Zeilenrauschen erzeugte
  1-Pixel-Kaemme, also fransige Kanten). Erst 0.30 s steht das Wort ganz, dann
  driften die Scherben ueber 0.50 s auseinander (Rotation + Schwerkraft, quadratisch
  beschleunigt). Scherben-Geometrie wird pro Moment gecacht -> deterministisch,
  kein Flackern. Der Text bleibt die ganze Zeit lesbar (Versatz nur ~3 % Breite).
  2) SATZ-KONTEXT (der eigentliche Kniff): `anim_for(txt, context)` bekommt jetzt
  die umgebenden Woerter (i-4 bis i+8). Bei "Deutschland bricht seine Versprechen"
  ist das Keyword DEUTSCHLAND — im Wort selbst steht nichts von brechen. Erst der
  Satz loest die Animation aus. Keyword hat Vorrang, Kontext entscheidet nur, wenn
  das Wort selbst nichts hergibt ("Wachstum bricht ein" -> schub, nicht bruch).
  Gilt fuer ALLE Animationen, nicht nur bruch. REGIE_PROMPT kennt bruch inkl. Beispiel.
  3) FARBWELTEN (`colors.style`: auto | schwarz | weiss): Elegantes Schwarz
  (20,20,22 + Graphit 58,58,64) fuer helle Bilder, Elegantes Weiss (250,249,246 +
  warmes Grau 208,204,196) als High-End-Look auf dunklem Material. Feste Farbwelt
  schaltet die adaptive Szenen-Palette bewusst AB (sonst waere die Wahl wirkungslos)
  — `Sprites.set_base_colors()` ueberschreibt auch die Rueckfall-Farben, damit
  `set_palette(None)` nicht heimlich die Config-Toene zurueckholt.
  GUI: Segmented-Auswahl unter "Farben & Material". Neue Selftests: 14 (Logic 111/111).
- **v48: Sofort-Hook + Hook-Takt + B-Roll wird ignoriert.** (65–71 % entscheiden in
  den ersten 3 Sekunden.)
  1) SOFORT-HOOK (`effects.instant_hook`, Default an): Das staerkste Statement der
  ersten min(hook_seconds, 8) Sekunden wird zur Hook-Karte — `t0=0` am Plan zieht
  Einflug, Kamera und SFX auf Frame 1 vor; die Karte steht, bis das Statement
  gesprochen ist. Rangfolge: KI-Regie-power, dann Textlaenge, dann Fruehe.
  Kompositionen (wortgetaktete tokens) und B-Roll-Momente sind ausgenommen.
  Liegt das Statement ohnehin in den ersten 0.35 s, passiert nichts.
  2) HOOK-TAKT (automatisch): Pattern-Interrupt-Schwelle im Hook-Fenster auf
  3/4/5 s verdichtet (deterministisch variiert), danach wie gehabt `pattern_interrupt`.
  Belegt per Selftest: Sprechpause im Hook bekommt 4 Impulse statt 1.
  3) B-ROLL WIRD IGNORIERT (nach Windows-Test auf Kundenmaterial): Kamera-Impulse
  des Pattern-Interrupts feuerten auf B-Roll und zoomten/schwenkten fremdes
  Footage nachtraeglich. Impulse werden jetzt per `face_ok` gegen B-Roll geprueft
  und dort uebersprungen (Konsolen-Hinweis); die Taktung laeuft ausserhalb weiter.
  Momente und Keyword-Kameras waren auf B-Roll bereits gesperrt.
  ENTFERNT: Open-Loop-Teaser (aus v48-Zwischenstand) — auf Ismets Wunsch wieder
  vollstaendig ausgebaut (Template, Config, GUI, Tests).
  GUI: ein neuer Schalter im Hook-Bereich (Sofort-Hook).
- **v48-Bugfix (kritisch)**: `camonly`-Kamera-Impulse crashten den Compositor mit
  `KeyError 'kw_i'`, sobald ihr Zeitfenster aktiv wurde — jeder Render mit
  Pattern-Interrupt-Einsaetzen war betroffen. Guard im Zeichen-Loop + Regressionstest.
- **v47: Hook einstellbar + Watchtime-Mechanik.**
  1) HOOK EINSTELLBAR - war fest auf 15s verdrahtet. Jetzt `effects.hook_seconds`
  (8/15/30/60, 0 = aus) und `effects.hook_strength` (0..1; GUI: Sanft/Normal/Stark).
  Die Staerke steuert die Dichte-Grenze im Hook: gap_eff = min_gap * (1 - 0.66*pow),
  d.h. stark = bis zu dreifache Moment-Dichte. Belegt: Hook 0s/15s/30s -> 3/9/17
  Momente in den ersten 30 Sekunden.
  2) WATCHTIME - LUECKENFUELLER (`effects.retention_gap`, Default 12s, 0 = aus):
  Reisst eine textlose Strecke weiter auf als der Grenzwert, wird das staerkste Wort
  im Fenster zum Moment erhoben (power=1, dezent; Effekt aus eigenem Rotator).
  Belegt: groesste Luecke 10.6s -> 9.1s bei Grenzwert 8s.
  3) WATCHTIME - PATTERN-INTERRUPT (`effects.pattern_interrupt`, Default 9s, 0 = aus):
  In Passagen ohne jedes Ereignis werden Kamera-Impuls-Plaene ('camonly', punch/push/
  pan aus dem Rotator) eingeschoben - Bewegung fuers Auge ohne Text. camera_at nimmt
  jetzt auch Plaene ohne kw_i (t0 faellt auf p['start'] zurueck).
  4) Selftest deckt alles ab: Hook-Laenge wirkt, Hook-Staerke wirkt (misst GROSSE
  Momente - im Hook laufen normale Gruppen ohnehin alle), Luecken werden gefuellt,
  Impulse gesetzt, beides abschaltbar.
- **v46: Animationen grundsaetzlich repariert + Variations-Motor.**
  1) FEUER ENTFERNT (Nutzer: "sieht Katastrophe aus") - FireFX-Klasse und alle
  Verwendungen raus.
  2) DIESELBE BUG-KLASSE BEI GLITCH UND PULS GEFUNDEN: sie wirkten - wie Feuer -
  NUR am Effekt 'behind' und verpufften bei cascade/outline/blurin/ground. Jetzt
  EIN zentrales System: anim_apply(p, base, aud, dt) -> (arr, dx, dy, scale, opacity);
  JEDER Zeichenpfad ruft es auf (behind-Token, behind/blurin-Haupt, cascade, outline,
  ground getrackt + ungetrackt). Eine Auswahl kann strukturell nicht mehr verpuffen.
  3) SECHS ANIMATIONEN statt drei: glitch, puls, welle (Sinus-Warp durch die
  Buchstaben), zittern (Shake auf Onsets), neon (Flackern + Glimmen), schub
  (Vorwaerts-Druck auf dem Bass). ANIM_HINTS und KI-Regie-Prompt entsprechend neu.
  4) VARIATIONS-MOTOR gegen Monotonie: neue Rotator-Klasse (Bag-Shuffle) - mischt
  die Liste, spielt sie ab, mischt neu; nie zweimal derselbe Wert hintereinander,
  aber alles kommt gleich oft vor. Angewandt auf Kamera-Bewegungen und Einfluege.
  Seed aus der Wortzahl -> reproduzierbar. Zwei neue Einfluege: 'swing' (schwingt
  seitlich herein, federt aus) und 'flip' (klappt aus der Tiefe nach vorn) - beide
  in beiden Zeichenpfaden umgesetzt.
  5) Selftest prueft jetzt JEDE Animation einzeln UND dass sie bei JEDEM der fuenf
  Effekte ankommt, plus die Variations-Eigenschaften (keine Wiederholung,
  Gleichverteilung).
- **v45: Feuer-Bug behoben (vom Nutzer gemeldet).** Die Animation "Feuer" wurde im
  Moment-Editor angeboten, aber im Render NUR am Effekt "Hinter dir" (behind)
  angehaengt - bei "In der Szene", "Buchstaben-Aufbau", "Nur Umriss" und "Aus der
  Unschaerfe" verpuffte die Auswahl still. Zusaetzlich waren Zaehler-Momente
  ausdruecklich vom Feuer ausgeschlossen. Jetzt:
  - FireFX wird generisch am Ende des Plan-Baus fuer JEDEN Effekt nachgeruestet
    (Basis: f_arr bei outline, sonst arr; Tokens bekommen es am core-Token).
  - Neuer Helfer fire_frame(p, base, a_rms) liefert (Feuer-Frame, y-Ausgleich) und
    ist in allen Zeichenpfaden eingehaengt: cascade (Breite bleibt, crop_w gilt
    weiter), outline (auf f_arr), blurin, ground getrackt UND ungetrackt.
  - FireFX.set_source(): Zaehler tauschen ihre Ziffern jeden Frame - die Flamme
    folgt der neuen Quelle, OHNE zurueckgesetzt zu werden (sonst Flackern).
  - Blender-Pass tauscht p['arr'] nach dem Plan-Bau -> FireFX wird auf dem neuen
    Glas-Bild neu aufgebaut.
  - Selftest prueft jetzt FUER JEDEN der fuenf Effekte, dass Feuer wirklich
    ankommt - diese Fehlerklasse (Auswahl im Editor, aber kein Effekt im Video)
    kann nicht mehr still zurueckkehren.
- **v44: Bedien-Sperre + aufgeraeumte Presets.**
  1) SPERRE WAEHREND LAUFENDER ARBEIT - neue Methode set_busy(): sperrt alle vier
  Pills (echter disabled-Zustand in der Pill-Klasse: grau, kein Cursor, Klick wird
  verworfen), das "Video waehlen"-Label und ALLE Eingabe-Widgets der drei Tabs
  (Entry/Scale/Checkbutton/Combobox via _all_inputs()). Zusaetzlich pruefen
  apply_preset/select_font/open_moments/check_transcript/render das busy-Flag.
  Greift bei: Voll-Render, Vorschau, Momente-Analyse, Transkription, partiellem
  Re-Render und zwischen Warteschlangen-Videos. Entsperrt automatisch im DONE-Handler.
  2) PRESETS NEU - die alten ueberlappten (Viral vs Social Punch fast identisch, Kino
  mit allen 5 Effekten = Effekt-Salat). Jetzt VIER trennscharfe Looks, jeder mit
  eigener Plattform-Dichte, eigenem Effekt-Paar, eigener Schrift, eigener Kamera:
  TikTok (durchgehend/behind+outline/TikTok Sans/energisch/50% SFX),
  Creator (ausgewogen/behind+cascade/Montserrat/ausgewogen/30%),
  Cinematic (akzente/blurin+ground/Inter/ruhig/22%),
  Clean (ausgewogen/cascade/Poppins/ruhig/0% SFX).
  Presets setzen jetzt auch die Plattform-Dichte mit; Selftest erzwingt, dass keine
  zwei Presets dieselbe fx/font/dynamik-Kombination haben.
- **v43: Bugfixes + Bedienbarkeit.**
  1) POPUP-LAYOUT REPARIERT - Transkript- und Moment-Fenster hatten den Canvas mit
  side='left' gepackt, ohne Breiten-Bindung: Zeilen abgeschnitten, Speichern-Knopf
  schwebte mitten im Fenster. Neuer Helfer popup_scroll(): Knopfbalken ZUERST
  side='bottom' verankert, dann Canvas; Canvas-<Configure> zieht die Zeilen auf volle
  Breite. Fenster groesser (860x660 / 1020x620).
  2) FUSSLEISTE - Status und Knopfreihe lagen in einer Zeile und ueberlappten; jetzt
  zwei Zeilen.
  3) STAPEL-KNOPF ENTFERNT - "Video waehlen" nimmt jetzt direkt mehrere Dateien
  (askopenfilenames, Strg/Shift); mehrere = Warteschlange. pick_batch geloescht.
  4) ERKLAERUNGEN UEBERALL - Text-Stil, Qualitaet, Tempo (nur Rechenzeit/Dateigroesse,
  NICHT der Look), Dynamik, Abstand zwischen Momenten, Sound-Effekte haben jetzt
  Klartext-Hinweise in der GUI. Zusaetzlich ANLEITUNG.md: jede Funktion erklaert.
- **v42: Benutzerfreundlichkeits-Paket (alle Punkte vom Nutzer beauftragt).**
  1) PARTIELLER RE-RENDER - der grosse Neuzugang: Im Momente-Editor speichern ->
  nur die geaenderten Momente werden neu gerendert (render.py --window T0 T1,
  Video-only mit 1.2s Track/Matting-Vorlauf) und frame-exakt ins fertige
  _captions-Video eingesetzt (--splice-into; Grenzen aus first_abs/last_abs auf dem
  Frame-Raster; Audio-Spur bleibt unangetastet -> keine Ton-Naehte). Ueberlappende
  Fenster werden zusammengelegt. Ehrliche Grenze: geaenderte SFX eines Moments
  aendern sich erst beim naechsten Voll-Render (Audio wird nicht angefasst).
  2) TRANSKRIPT-FIX - ensure_models lief VOR dem --transcribe-only-Ausstieg
  (sah aus wie ein Render). Jetzt: Modelle uebersprungen, Transkript-Cache wird
  automatisch erkannt -> Klick oeffnet den Editor in <1s (nur die allererste
  Transkription pro Video braucht die Whisper-API, 15-45s).
  3) MOMENTE-EDITOR = CAPTION-EDITOR - Spaltenueberschriften, alles Deutsch:
  Effekte heissen wie in der Legende (Hinter dir/In der Szene/...), Groesse
  Dezent/Normal/Gross, Animation keine/Feuer/Glitch/Puls. Intern bleiben die
  englischen Keys (FX_DE/POWER_DE/ANIM_DE-Mappings, verlustfrei rueckuebersetzt).
  4) TIKTOK-TREND-FONTS (Juli 2026, recherchiert): TikTok Sans Bold (offizielle
  TikTok-Schrift, Open Source seit Mitte 2025), Montserrat ExtraBold (fuehrt die
  2026er Caption-Listen an), Inter Black (viraler Clean-Cinematic-Look). Kacheln
  'Elegant' (serif) und 'Editorial' (abril) entfernt. Als variable Fonts geladen
  und auf statische Gewichte instanziert (fonts/tiktok_bold|montserrat_xb|
  inter_black.ttf).
  5) STIL-PRESETS: 'Elegant'/'Editorial' ersetzt durch 'Viral' (TikTok Sans,
  Wort-fuer-Wort, energisch) und 'Creator' (Montserrat, Business/Talking-Head).
  6) FEINREGLER (Abstand, Sound-Pegel) in den Profi-Tab verschoben.
- **v41: Vier Ausbauten auf einmal.**
  1) MATERIAL JE SZENE - Blender rendert das Material passend zur Vision-Regie:
  Wasser -> fluessiges Glas (animiert), Boden/Wand -> massives mattes 3D in der
  Szenen-Farbe (Principled, Roughness 0.55, leichter Metall-Schimmer). Glas auf
  Asphalt gibt es nicht mehr. Wellen-Animation laeuft nur auf Wasser (solid = 1 Frame,
  spart Renderzeit). "Aus dem Wasser"-Einflug nur bei Wasser-Material.
  2) MOMENT-EDITOR ERWEITERT - zwei neue Spalten: Szene (auto/wasser/boden/wand/person)
  und Lage (auto/liegend/stehend/frei). 'auto' = Vision-Regie entscheidet; alles andere
  uebersteuert sie. Momente-Export schreibt die Regie-Entscheidungen mit, Korrekturen
  ueberleben Neuanalysen.
  3) STAPEL-WARTESCHLANGE - "Stapel" neben "Video waehlen": mehrere Videos waehlen,
  sie rendern automatisch nacheinander (abends einreihen, morgens fertig). Label zeigt
  die verbleibende Warteschlange.
  4) TRANSKRIPT-KONTROLLE - "Transkript"-Button: transkribiert (render.py
  --transcribe-only) und oeffnet den Korrektur-Editor (10-Woerter-Zeilen). Gleiche
  Wortzahl = Timing bleibt exakt; andere Wortzahl = Timing wird gleichmaessig ueber
  die Zeile verteilt; leere Zeile = Woerter loeschen. Der Render nutzt die Korrektur
  automatisch (Transkript-Cache).
- **Wichtiger Altfehler behoben (v41)**: Die GUI-Konstante F_M war seit mindestens v31
  nie definiert - der Moment-Editor crashte bei JEDEM Oeffnen mit NameError. Jetzt
  definiert; neuer Selftest prueft alle benutzten F_*-Konstanten statisch.
- **Dynamische Wasser-Animation (v40)**: 1) LEBENDIGES WASSER - Blender rendert pro
  Moment eine Loop-Sequenz (4D-Noise laeuft, `effects.blender_anim_frames`, Default 12),
  die Pipeline spielt sie als nahtlosen Ping-Pong-Loop (anim_loop_idx): die Wellen
  wandern sichtbar ueber die Buchstaben. 2) "AUS DEM WASSER"-Einflug - Glas-Texte
  steigen beim Erscheinen aus der Flaeche auf: erst tief, transparent und verschwommen
  wie unter der Oberflaeche, dann klar (emerge ueber 0.9s). Beides laeuft durch
  Kamera-Track + Okklusion. Qualitaet/Tempo-Regler: `blender_anim_frames` (1 = Standbild
  wie v37), `blender_samples`, `blender_width`. Renderzeit pro Moment steigt linear mit
  den Frames - Cache greift wie gehabt.
- **GUI v39 Fixes**: "Video waehlen" repariert (pick_video war beim Entfernen der
  Farb-Methoden mitgeloescht - aus v37 wiederhergestellt). Effekte heissen jetzt
  verstaendlich und haben eine Erklaerungs-Legende (z.B. "Aus der Unschaerfe" statt
  "Kinotitel", "In der Szene" beschreibt Wasser-Glas/Track/Verdeckung). Selftest
  prueft jetzt GUI-Handler und Preset-Struktur (fensterlos) - der verlorene Button
  waere damit sofort aufgefallen.
- **GUI v38: Stil-Presets statt Detail-Schrauben**: Fuenf Presets, die jeweils
  Effekt-Set, Dynamik, Momente-Dichte, SFX-Pegel, Schrift UND Text-Stil setzen -
  Elegant (cinematic/high-end, Serifen, ruhig), Kino (voller Look), Social Punch
  (schnell/laut), Editorial (Magazin), Clean (minimal). Die Umgebungs-Anpassung
  (adaptive Farben, Wasser-/Boden-Material, Licht, Okklusion) laeuft in JEDEM
  Preset immer - Presets steuern den Geschmack, nicht die Adaptivitaet.
- **Entfernt (obsolet durch Adaptivitaet)**: Akzentfarben-Wahl inkl. Farbwaehler -
  Farben kommen aus der Szene. config `colors.accent` bleibt nur als stiller
  Fallback, wenn das Sampling eines Frames scheitert. Alte Kundenprofile mit
  gespeicherter Akzentfarbe laden weiter (Feld wird ignoriert).
- **Blender-Wasser-Text (v37, freigegeben)**: Stehende Szenen-Texte auf B-Roll sind
  echtes 3D-Wasser-Glas aus Blender (headless, `blender_engine.py`): IOR 1.33,
  Fluessigkeits-Bump, Mesh-Reparatur gegen Bevel-Selbstschnitte (Normalen!),
  Refraktions-Platte = unterer Bild-Bereich des Moment-Frames, Ausreisser
  (Boote/Texte) zur Wasser-Mitte geklemmt, Szenen-Palette als Tint. EIN Render pro
  Moment (gecacht in %TEMP%/douchko_blender) - Bewegung uebernimmt der Kamera-Track,
  Verdeckung die Tiefen-Okklusion, Filmlook Grain+Kamera-Blur. Liegende Texte
  behalten den versenkten 2D-Referenz-Look. Fallback: ohne Blender laeuft alles 2D
  weiter. Windows: Blender installieren (blender.org, Version 4.x) - wird automatisch
  gefunden; alternativ `render.blender_path` in config.yaml. Schalter:
  `effects.blender_water`, Qualitaet: `effects.blender_samples` (128; auf GPU gern
  256). Hinweis: offizieller Blender-Build hat den Denoiser - Ergebnisse werden
  sauberer als in der Entwicklungs-Umgebung. Selftest-Renders laufen bewusst ohne
  Blender-Pass (Zeitdeckel); die Engine ist per Logic-Checks abgedeckt.
- **Planarer Kamera-Track (v36, der AE-Kern)**: Szenen-Texte werden nicht mehr 2D
  mitgeschoben, sondern von einer pro Frame akkumulierten HOMOGRAPHIE bewegt
  (goodFeaturesToTrack + LK-Flow + RANSAC auf der Bodenebene, 480p-Grau, nur in
  Szenen-Text-Fenstern). Der Text waechst, kippt und zieht perspektivisch vorbei wie
  ein Objekt in der Welt - identisches Verhalten wie ein After-Effects-Plane-Track,
  verifiziert synchron zur einbelegten Referenz. Getrackte Texte werden weiter voraus
  verankert (kommen auf die Kamera zu); adaptive Daempfung deckelt den Drift des
  Text-Zentrums (Lesbarkeit bei extremem FPV-Tempo, AE-Praxis). Cut-Erkennung setzt
  den Track neu auf, Ausfall-Zaehler faellt sauber auf 2D zurueck.
  Schalter: `effects.track3d` (Default an).
- **Realismus-Paket (v35)**: 1) TIEFEN-OKKLUSION - Depth Anything V2 (ONNX, laeuft wie
  RVM auf CUDA/DirectML/CPU, nur in Szenen-Text-Fenstern) verdeckt den Text durch alles,
  was naeher an der Kamera ist (Boot faehrt VOR dem Text durch); d_ref wird am Text-Ort
  gemessen, Maske zeitlich geglaettet, Spiegelung wird mit-okkludiert. Modell laedt
  ensure_models beim ersten Start (~99 MB). Schalter: `effects.occlusion`.
  2) KAMERA-MOTION-BLUR - Szenen-Texte verwischen proportional zur Kamerabewegung
  (aus dem Scene-Tracking-Signal), statt verraeterisch scharf zu bleiben.
  3) FILM-GRAIN - Szenen-Texte rauschen pro Frame wie das Video, nicht klinisch sauber.
- **KI-Regie v4 mit Vision (Umgebungs-Regie)**: Nach der Text-Regie schaut sich gpt-4o
  pro gewaehltem Moment einen Frame an (max. 24/Video, low-detail, wenige Cent) und
  entscheidet "szene" (wasser/boden/wand/himmel/person) und "lage" (liegend/stehend/frei)
  plus Effekt-Korrektur, wenn der Frame etwas anderes verlangt als das Transkript.
  "lage" uebersteuert die Power-Heuristik. Felder ueberleben Regie-Cache und
  Moment-Editor-Edits. Schalter: `keywords.ai_vision` (Default an); ohne Key/Vision
  greift die Power-Regel als Fallback.
- **KI-Regie v3** (gpt-4o): versteht Satzbau (Satzzeichen aus Whisper-Segmenten zurückgeholt),
  wählt Keywords/Phrasen (1-4 Wörter), Effekte, power 1-3 und semantische Animationen
  (feuer/glitch/puls). Caches: `<video>_transcript2.json`, `<video>_regie3.json`.
  **Neu: Etappen-Analyse** für lange Videos (Chunks an Satzgrenzen, globale Indizes,
  video-weiter Power-3-Deckel) — die Regie fällt bei 20min+ nicht mehr still auf die Automatik.
- **Editorial-Kompositionen**: Phrasen als Magazin-Layout, ohne Unterstriche (High-End-Look) (Auftakt / Kern / Script-Wort),
  wortgetaktet, hinter der Person, szenen-verankert.
- **Studio-Licht-Typo (v31)**: Buchstaben mit vertikalem Licht-Verlauf + Glanzband,
  gestaffelt abdunkelnde 3D-Extrusion, Kontakt-Schatten unter ground-Texten,
  direktionaler Motion Blur auf Einfluegen.
- **Lebendige Typo**: prozedurales Feuer, Glitch auf Onsets, Puls auf Bass —
  Tonspur-Analyse pro Frame (audio_envelopes).
- **Hochzählende Zahlen**: zählen IMMER hoch (unabhängig vom Anim-Schalter; wählt die
  Regie cascade für eine Zahl, wird auf outline umgeschaltet). Counter-SFX rollt exakt
  so lange wie die Zahl zählt (Dezimal/Tausender erhalten).
- **Entrance-Rotation** (5 Stile, Expo-Easing) + **Kamera v2** (caption-Close-up, Schwenk,
  weiche Pushes).
- **Personen-Following**: Wortgruppen hängen an der Person, große Momente an der Szene.
- **SFX v6**: geschichtete Sounds (Impact = Sub + Knock-Korpus + Crack; Whoosh =
  Sweep + Sub-Schwell + Luft-Layer) mit Schroeder-Hall statt Rausch-Ausklang,
  Peak-Normalisierung. Eigene/gekaufte WAVs in `sfx/` ersetzen weiterhin alles.
- **SFX v5 (Basis)**: dunkles Sound-Design mit Raum-Tails, volle Abdeckung: Riser+Boom auf
  power-3, Landungs-Impact auf ground, Buchstaben-Ticks auf cascade, Micro-Ticks auf
  Wortgruppen (mit Anti-Matsch-Limiter). Default-Mix 0.5. Bank versioniert sich selbst
  (`.bank_*`-Marker), eigene WAVs in `sfx/` ersetzen die generierten.
- **Plattform-Modi** + **Hook-Intro** (erste 15s dicht) + **Safe-Zone 9:16**
  (Buttons/Beschreibung bleiben frei, per Quell-Diff bewiesen).
- **Moment-Editor**: `--plan-only` → `<video>_momente.json`, GUI-Fenster mit editierbarem
  Text, Häkchen, Effekt/Power/Anim; Edits überleben Neu-Analysen.
- **Vorschau**: `--preview` = 540p in Sekunden statt Minuten.
- **Fonts**: 14 Kacheln; Standard "Kino" = Archivo Black + Playfair Italic 600 als
  Script-Wort (Referenz: "Cinematic fonts"-Short). Script-Font pro Kachel.

## Referenz-Level (neu, Juli 2026)
- **Adaptive Farben v2**: Caption-Töne greifen pro Moment die Szene auf — Text = dominanter
  Szenenton entsättigt & fast auf Weiß gehoben (nie #FFFFFF), Akzent = leuchtende Version
  desselben Tons. Sampling per ffmpeg (robust bei HEVC/VFR, wo cv2-Seeks auf Windows
  scheitern), regions-bezogen: ground sampelt den Untergrund ('unten') statt Himmel/Fels.
  `colors.adaptive: true`, Fallback = Config-Farben.
- **Wasser-Look v3 (pixelvermessen an der Referenz)**: liegender Text mit
  auslaufenden Kanten (Alpha-Feather), flachem Licht (kein Glanzband unter Wasser),
  ruhiger Wellen-Modulation, Spitzlichter der Oberflaeche stechen durch den Text
  (Wasser liegt sichtbar DAVOR). Messwerte Helligkeits-Ratio/Kanten/Textur an das
  Original angeglichen; Restdifferenz stammt aus der Wasser-Unruhe des Footage.
- **Wasser-Look v2 (Basis)**: ground auf B-Roll hat zwei Varianten.
  LIEGEND (power 3, "HOW"-Look): flach IM Wasser, ohne 3D-Kante/Schatten/Spiegelung,
  mit echter REFRAKTION — die Untergrund-Gradienten sind eine Displacement-Map, die
  Wellen verschieben die Buchstaben-Pixel pro Frame, dazu Farb-Kopplung (kanalweise)
  und weiche Kanten. STEHEND (power <=2, "TRACKING"-Look): aufrecht mit 3D-Extrusion
  und Wasser-Spiegelung. Talking-Head-Ground bleibt klassisch (Kontakt-Schatten).
- **Spiegelung**: ground-Momente bekommen eine Wasser-/Boden-Reflexion (gestaucht,
  weichgezeichnet, auslaufende Deckkraft). `effects.reflection: true`.
- **Text steht in der Welt**: Szenen-Verankerung greift jetzt auch auf B-Roll
  (Drohne/FPV) mit größerem Parallaxe-Spielraum (0.30·W statt 0.12·W); ground ist auf
  B-Roll erlaubt (behind wird zu ground gemappt). Verifiziert per Render direkt auf dem
  Referenz-Footage.

## Randfälle (neu abgesichert)
- **Kein Gesicht im ganzen Video** (Voiceover/Screen-Recording): Captions fallen nicht mehr
  weg, sondern werden szenen-verankert gesetzt (Konsolen-Hinweis). B-Roll-Regel für
  gemischte Videos bleibt unverändert.
- **Lange Videos**: Regie-Chunking (s.o.); Whisper-Audio-Bitrate passt sich der Dauer an,
  bleibt auch bei 60min+ unter dem 25-MB-API-Limit.
- **Fremdsprachen**: Regie-Prompt bekommt Sprach-Hinweis; Phrasen-Logik akzeptiert
  Kleinschreibungs-Sprachen ("dynamic pricing"); englische Stoppwörter ergänzt;
  Zahlen werden in jeder Sprache von der Fallback-Heuristik erfasst.
- **Video ohne Tonspur + Cache-Transkript**: TypeError-Crash behoben.

## Selbsttest
`python selftest.py clip.mp4 transcript.json [pan.mp4] [mixed.mp4] --part=X`
Etappen: `logic` (97 Checks, Sekunden) · `render1` · `render2a` · `render2b` · `render2c`.
Stand: 109/109 (v48) auf Synthetik-Assets (Linux/CPU) grün — inkl. pan/mixed:
die Synthetik-Clips haben jetzt ein prozedural schattiertes Gesicht, das BlazeFace
erkennt (Score 0.94), der Pan-Clip eine teal-stichige Szene (Adaptiv-Akzent = cyan
fuer den Verankerungs-Check) und der Mixed-Clip harte Schnitte (Szenen-Klassifikation
Talking-Head vs. B-Roll). Kompletter Lauf mit echten Clips auf Windows steht aus.

## Offen
- Windows-Test des Gesamtstands durch Ismet (inkl. voller Selftest mit echten Clips).
- API-Key-Rotation (Key war auf Screenshots sichtbar) — im Code ist nichts hartkodiert,
  Rotation im OpenAI-Dashboard genügt.
- Randfall zwei Sprecher: aktuell wird der dominante Sprecher gewählt, der zweite als
  B-Roll behandelt (bewusste Limitierung, echtes Multi-Speaker-Tracking wäre ein Ausbau).
- GPL: RVM ist GPL-3.0 (bestätigt). Fürs aktuelle Service-Modell unkritisch (keine
  Software-Weitergabe). Vor einem Verkauf: Rechtsberatung oder Matting-Austausch gegen
  eine permissive Alternative (z.B. MediaPipe Selfie Segmentation, Apache-2.0).


## OFFENE PUNKTE (Stand v60)

1. **OpenAI-Key rotieren** — seit vielen Versionen offen, Key war auf Screenshots.
2. **Sound-Pack fertig auswaehlen** — Ismet laedt die CC0-Sounds im Programm
   (Sound -> Key -> "Echte Sounds laden" -> "Anhoeren & auswaehlen") und schickt
   den Ordner `sfx/pack` als Zip. Der wird dann fest ins Web-Paket gelegt, damit
   die Tester keinen Freesound-Key brauchen (CC0 erlaubt die Weitergabe).
   OHNE Pack laufen Videos STUMM - synthetische Sounds wurden ersatzlos entfernt.
3. **Web-Server aufsetzen** — Hetzner CX-Reihe war ueberall ausgebucht.
   Empfehlung jetzt: netcup VPS 2000 G12 (8 vCPU, 16 GB, ~14 EUR/Monat),
   Ubuntu 24.04. Sobald die IP steht: Docker-Befehle aus web/ANLEITUNG_WEB.md.
   Netlify geht NICHT (kann keine minutenlangen Renders).
4. **Windows-Test auf Kundenmaterial** mit der neuen Maskenqualitaet ('hoch').
5. **Spaeter: Paywall** — aus dem Zugangscode wird ein Abo (Stripe legt die
   Eintraege an statt codes.py). Rest der Web-Architektur bleibt.

## v61 - Premium-Typo 2026 (Stand High-End-Editing)

Recherchierter Abgleich mit dem aktuellen High-End-Standard (TikTok/Reels 2026).
Fuenf Punkte umgesetzt - alle mit Regler in der GUI (Karte "Premium-Typo"):

1. **Chunk-Pacing** - Wort-fuer-Wort im 200-240-WPM-Takt gilt 2026 als billig.
   Neu: `chunk_hold_min` (Standard 650 ms). Zu kurze Wortgruppen werden mit der
   naechsten zusammengehalten, bis sie mindestens 600-900 ms stehen. Satzenden
   werden nie ueberklebt, Wortlimit `words_per_group_max` (Standard 5).
2. **Kontaktschatten** - Die Person wirft jetzt einen weichen Schatten auf den
   Text hinter ihr (`person_shadow`, Standard 50 %). Vorher war der Text nur
   ausgeschnitten; jetzt sitzt er im Raum. Faellt nur ausserhalb der Silhouette
   und nur, solange ein Hintergrund-Text aktiv ist.
3. **Echte Variable-Font-Achse** - `gewicht` rechnete den Strich bisher nur dick
   (Morphologie). Neu: variable Schnitte an Bord (archivo_var, inter_var,
   montserrat_var). Die Gewichts-Leiter (300-900) wird einmal gerendert, im Frame
   wird nur noch die Stufe gewaehlt - kein Font-Rendering pro Frame, aber echte
   Achsen-Interpolation. Ohne variablen Schnitt greift der alte Weg.
4. **Beat-/Stimm-Sync** - `beat_sync` (Standard 70 %) koppelt Skalierung und
   Mikro-Hub an den Sprech-Onset statt an eine feste Kurve. Laeuft zentral in
   `anim_apply()`, greift also auf JEDER Animation - auch ohne gesetzte anim.
5. **Fluid-Morph** - neuer Auftritt `morph`: das Wort fliesst aus einer weichen
   Rauschfeld-Verzerrung in seine Form, statt hart geschnitten zu werden. In der
   Auftritts-Rotation (auch Token-Pfad).

Bewusst NICHT gebaut: handgezeichnete Annotations-Layer (Marker-Striche, Kringel).
Trend, aber bei Premium-Marken wirkt die gewollte Unsauberkeit daneben.

Regression: 221/221 gruen (render1 6, render2a 1, render2b 1, render2c 2, logic 211
inkl. 18 neuer Premium-Typo-Tests).

### v61a - Fix: GUI liess sich nicht oeffnen

Ursache: In der neuen Karte "Premium-Typo" wurde `self.setting(..., first=True)`
aufgerufen - `setting()` kennt dieses Argument nicht (nur `row()` kennt es).
Das Fenster brach beim Aufbau ab. Behoben.

Warum es durchkam: Der Selftest hat die GUI nie hochgefahren, sondern nur einzelne
Widgets und Verdrahtungen geprueft. Neu: `_gui_smoke()` baut das komplette Fenster
wie beim Doppelklick - ein Aufbau-Fehler faellt ab jetzt sofort auf.
Regression: 222/222 gruen.

## v62 - Zahl-Momente

Problem: Relevante Zahlen wurden nicht gezeigt. Ursache war doppelt.
1. `detect_keywords` machte JEDE Ziffer zum Keyword. Bei mehreren Zahlen im
   Umfeld verdraengten sich die Momente ueber die `min_gap`-Sperre gegenseitig -
   ausgerechnet die wichtige Zahl fiel dann raus.
2. Ausgeschriebene Zahlen ("drei Millionen", "achtzig Prozent") wurden gar nicht
   erkannt.

Neu: `zahl_relevanz(words, i)` bewertet, ob eine Zahl die Aussage traegt.
- Loest aus: Prozent, Waehrung, Faktor (10x), Zahlen ab 1000, Zahl neben einem
  Wertwort (Umsatz, Wachstum, Kunden, Follower, Rekord ...), Jahreszahl MIT
  Wertwort im Umfeld. Ausgeschriebene Zahlen zaehlen mit.
- Loest NICHT aus: Zaehlwoerter ("zwei Sachen"), Aufzaehlungen ("Schritt 3"),
  Uhrzeiten ("um 8 Uhr"), nackte Jahreszahlen ("das war 2019 damals").

Drei Bremsen, damit es NICHT bei jeder Zahl knallt:
- Die normale `min_gap_seconds`-Sperre gilt weiter.
- `zahl_gap` (Standard 15 s, Regler in der GUI, 0 = aus): hoechstens eine
  Zahl-Caption pro Fenster. Faellt die Zahl raus, geht der Moment ans
  naechstbeste Wort - nicht an die naechste Zahl.
- Pro Wortgruppe gewinnt nur die staerkste Zahl (Score-Bonus 9 x Relevanz).

Der Zaehler-Effekt (`make_counter`, Hochzaehlen) haengt sich automatisch an.
Regression: 238/238 gruen (16 neue Zahl-Tests).

## v63 - Satz zu Ende fuehren

Problem (vom Kunden gemeldet, mit Screenshot): Ein grosser Moment zeigte
"BLEIB dran denn am Ende" - der Satz ging aber weiter ("... wirst du das alles
anders sehen") und der Rest fehlte komplett. Wirkte, als haette man vergessen
weiterzumachen.

Ursache: Ein Keyword-Moment deckt nur seine eigene Wortgruppe ab. Die
Folgegruppen desselben Satzes haben kein eigenes Keyword und fielen bei Dichte
"akzente" durch die Plattform-Sperre komplett weg.

Fix: Laesst ein Moment seinen Satz offen (letztes Wort ohne . ! ?), laufen die
folgenden Wortgruppen als ruhige Caption weiter, bis der Satz abgeschlossen ist -
kein zweiter grosser Moment, nur lesbar. Begrenzt:
- nur wenn das Transkript ueberhaupt Satzzeichen hat (sonst gaebe es kein
  Satzende -> lief endlos),
- hoechstens 2 Fortsetzungsgruppen,
- nur innerhalb von 4 s nach dem Moment,
- nicht im Hook-Intro und nicht auf B-Roll.
Ein abgeschlossener Satz zieht den naechsten NICHT herein.

Regression: 241/241 gruen (3 neue Tests: Fortsetzung sichtbar, bleibt ruhige
Ebene, abgeschlossener Satz zieht nichts herein).

## v64 - Anti-Zucken bei Keywords

Problem (Kunde): Keywords wackelten manchmal zu stark hin und her, fast ein Zucken.

Ursache: Das Onset-Signal (audio_envelopes) war roh - der Frame-zu-Frame-Sprung
der Lautstaerke. Einzelne Spikes durch Konsonanten/Plosive erzeugten Ausreisser.
Seit v61 koppelt Beat-Sync JEDES Keyword an dieses Signal, mit sofortigem Anstieg
(max(ons, ...)) und relativ viel vertikalem Hub. Ein Ein-Frame-Spike riss den Text
darum kurz hoch und wieder runter = Zucken. Vertikale Spruenge fallen als Zucken
staerker auf als Skalierung.

Fix an drei Stellen:
1. Onset wird an der Quelle geglaettet - Huellkurve mit begrenztem Anstieg
   (max +0.5/Frame) und weichem Ausklang. Ein echter Akzent kommt durch, ein
   Ein-Frame-Ausreisser nicht mehr.
2. Beat-Sync bekommt eine Deadzone (< 0.15 bewegt nichts) und denselben
   begrenzten Anstieg - kein Anreissen durch einen einzelnen Spike.
3. Vertikaler Hub von 0.020 auf 0.012 gesenkt. Die Bewegung bleibt spuerbar,
   aber ruhig.

Regelbar bleibt es ueber den Beat-Sync-Regler (0 % = ganz aus).
Regression: 244/244 gruen (3 neue Anti-Zucken-Tests).

## v65 - Crash-Zoom + Whip-Pan (nach Kategorie skaliert)

Zwei High-Energy-Kamerabewegungen ergaenzt, die 2026 zum High-End-Stand gehoeren -
aber bewusst dosiert, damit Premium nicht billig wirkt.

1. **Crash-Zoom**: schneller, harter Zoom (~0.32 s rein) mit entschiedenem Stopp,
   danach kurzer Halt und weiches Aus. Trifft NUR den einen staerksten Moment im
   Clip (hoechste power, bei Gleichstand laengstes Wort). Der harte Stopp bleibt
   erhalten, weil die Kamera-EMA danach ruhig stehen laesst statt nachzuwippen.
2. **Whip-Pan**: schneller Seitwaerts-Schwenk als Uebergang an echten Abschnitt-
   grenzen (Sprechpause >= 1.4 s zwischen zwei Momenten). Der horizontale
   Motion-Blur entsteht im Compositor aus der px-Geschwindigkeit - ohne ihn waere
   es nur ein Rutschen. Richtung alterniert.

Skalierung ueber die Dynamik-Stufe (greift automatisch bei den Presets):
- Ruhig  (Clean, Cinematic): Crash 0, Whip aus - bleibt ruhig, wie gewuenscht.
- Ausgewogen (Creator):      Crash 55 %, Whip aus.
- Energisch (TikTok):        Crash 100 %, Whip an.
Beide zusaetzlich einzeln regelbar (Crash-% Slider, Whip-Schalter) und ueber
camera.strength global daempfbar (0 = ganze Kamera aus).

Dolly-Zoom/Zolly bewusst NICHT gebaut - Gimmick fuer KI-B-Roll, nicht fuer
Talking-Head mit Captions.

Regression: 256/256 gruen (12 neue Kamera-Tests inkl. Kategorie-Skalierung).

## v66 - Verkaufsfertig, Schritt 1: Lokale Transkription (Key-Blocker geloest)

Entscheidung (an Claude delegiert): Transkription laeuft ab jetzt LOKAL ueber
faster-whisper - kein OpenAI-Key mehr im Kernpfad, keine laufenden Kosten pro
Kunde, funktioniert offline. Die SaaS-Konkurrenz transkribiert nur deshalb
server-seitig, weil sie Browser-Tools sind; fuer eine Desktop-App ist lokal
strikt besser.

Umsetzung:
- `transcribe(audio, lang, cfg)` waehlt jetzt die Engine: 'local' (Default) oder
  'api'. Der alte OpenAI-Pfad bleibt als `_transcribe_api` erhalten.
- `transcribe_local` nutzt faster-whisper, Modell in models/whisper/ (offline nach
  1. Lauf; fuer die Auslieferung mit-bundeln, dann kein Download beim Kunden).
- Rueckgabe im exakt gleichen Format wie die API (word/start/end + Satzzeichen aus
  Segmenten). Floats sauber gecastet (kein np.float64 -> JSON-sicher).
- config: transcription.engine/model/device/compute. Default model 'base'
  (gute DE-Qualitaet, ~145 MB, schnell auf CPU). CTranslate2 kann kein DirectML,
  laeuft also CPU - fuer Transkription unkritisch (einmal pro Video).

Die zwei KI-Regie-Aufrufe (Keyword/Szene) bleiben optional wie bisher: ohne Key
faellt alles auf die Heuristik zurueck, die die kompletten Premium-Features traegt.
Damit laeuft das Produkt zu 100 % offline und ohne laufende Kosten aus. KI-Regie
bleibt ein optionales Pro-Feature (eigener Key), spaeter ueber Server routbar.

WICHTIG fuer den Windows-Build: faster-whispers eigener Download kann bei Abbruch
ein korruptes Modell hinterlassen (hier einmal passiert -> 145 MB, aber 0 Woerter).
Fuer die Auslieferung das Modell mit-bundeln statt beim Kunden laden.

Regression: 265/265 gruen (10 neue Transkriptions-Tests inkl. echter lokaler
Transkription auf Sprach-Sample).

--- OFFENE PUNKTE bis verkaufsfertig (Roadmap) ---
[x] 1. Lokale Transkription (Key-Blocker) - v66
[ ] 2. Sound-Pack einbinden (Ismet schickt Zip) - stumme Videos sonst
[ ] 3. Lizenzsystem: Aktivierung im Client + Pruefung online (Abo)
[ ] 4. Stripe-Abo: Checkout + Webhook -> Lizenz aktiv (Keys als Platzhalter)
[ ] 5. Lizenzserver auf netcup VPS (FastAPI: Marketing + Stripe + Validierung)
[ ] 6. EU AI Act Art. 50: optionaler Offenlegungs-Hinweis/Metadaten (ab 2.8.2026)
[ ] 7. Windows-Build/Packaging (Modell + Sound-Pack mit-bundeln)

## v73 - Fuenf neue Effekt-Klassen

Fuenf komplett neue Effekte, alle als Post-Overlay oder Pipeline-
Modifikator - keine tiefe Umstellung der 5 tpl-Pfade noetig.

1. **Freeze-Frame** (`effects.freeze_frame`, Sekunden): auf dem staerksten
   power=3-Moment (laengstes Wort bei Gleichstand) friert das Video fuer
   0.4-1.5 s ein, waehrend die Caption weiterlaeuft. Regie-Trick fuer
   Punchlines. Nur EINMAL pro Clip - sonst wird's kitschig. B-Roll
   ausgeschlossen. Pipeline-Modifikator im For-Loop, `frozen_frame`-Cache
   haelt das erste Frame ab Fensterstart.

2. **Duplicate-Trail** (`effects.trail`, 0-1): der Text hinterlaesst
   versetzte Kopien nach links mit fallender Deckkraft (Speed-Gefuehl wie
   in Musikvideos). Post-Effekt via Diff comp vs. frame - extrahiert die
   Text-Region und dupliziert sie. Ohne Text im Frame passiert nichts
   (kein Blindwurf).

3. **Zaehler-Ring** (`effects.counter_ring`, 0-1): kreisrunder Fortschritts-
   bogen um Zahl-Momente (die mit `count`-Metadaten). Laeuft synchron zum
   Zaehler von 0 auf 360°. Wirkt wie ein Sport-Timer/Score-Ring. Bei
   Momenten ohne Zahl: no-op.

4. **Split-Screen** (`effects.split_screen`, 0-1): das Frame wird
   horizontal in zwei Haelften geteilt, die an einer Luecke (bis 5% der
   Bildhoehe) auseinander driften. Text sitzt in der Luecke. Greift nur
   bei power=3-Momenten ohne B-Roll. Rein/raus mit der ueblichen Moment-
   Fade-Kurve.

5. **Environment-Text-Schatten** (`effects.env_shadow`, 0-1): ground-
   Momente (In der Szene) bekommen einen weichen Kontakt-Schatten unter
   dem Text. Diff-Extraktion der Text-Region, nach unten/rechts verschoben,
   Gauss-Blur, dunkelt AUSSERHALB der Text-Pixel ab (der Text selbst bleibt
   hell). Ergaenzt Blender-Wasser (das die Schatten schon fuer Wasser
   liefert) fuer Non-Blender-Faelle.

Alle Regler in einer neuen Karte "Spezial-Effekte (v73)" im Effekte-Tab.
Alle Defaults bei 0.0 - der Nutzer entscheidet, was er will. Kein Regler
wirft blind: jeder prueft Vorbedingungen (Text im Frame, power=3, ground-
Moment, count-Metadaten) und ist sonst no-op.

Selftest: +32 Tests (Existenz aller Funktionen, Config-Keys, Verhaltens-
Tests pro Effekt inkl. no-op-Bedingungen, GUI-Regler-Verdrahtung, Profil-
Sicherung). Regression: **357/357 gruen** (vorher 325/325, +32 neu).

GUI-Smoke `xvfb-run` -> GUI_OK.

Ehrliche Grenze: Duplicate-Trail arbeitet ueber Diff comp/frame - wenn das
Video-Background sehr aehnlich zur Text-Farbe ist, faellt der Trail weniger
auf. Freeze-Frame haelt strikt das erste Frame ab Fensterstart - bei
Bewegungen davor sieht man einen harten Snap; das ist gewollt (Standbild).
Split-Screen ist eine bewusste Kino-Anleihe, wird bei power=3-Momenten
schnell zu haeufig - default 0 % ist bewusst.

## v72 - Lokale Transkription komplett raus

Der `local`-Pfad (faster-whisper) war seit v67 nur noch Option, in
v72 vollstaendig entfernt. Begruendung: Qualitaet > alles - die API
liefert Namen/Fachbegriffe zuverlaessiger, und der Umschalt-Ballast
(Modell-Download, DirectML/CTranslate2-Sonderfall, CPU-Fallback)
lohnt sich fuer ein persoenliches Tool nicht.

Entfernt:
- `transcribe_local()` und `from faster_whisper import` aus render.py
- `_transcribe_api()` als eigene Funktion (Inhalt jetzt direkt in
  `transcribe()`)
- Config-Block `transcription:` (engine/model/device/compute)
- `models/whisper/` wird nicht mehr angelegt oder referenziert
- `faster-whisper` aus requirements.txt

`transcribe(audio, lang, cfg=None)` behaelt die Signatur - `cfg` wird
ignoriert (Rueckwaerts-Kompatibilitaet fuer bestehende Aufrufer).

Selftest v66-Block ersetzt durch v72-Block: prueft dass local wirklich
weg ist (nicht nur ungenutzt). Der Whisper-Modell-Fail, der seit v66
umgebungsbedingt rot war, ist ersatzlos raus.

Regression: **325/325 gruen** (kein einziger Fail mehr). GUI-Smoke OK.

## v71 - Acht weitere Animationen (18 -> 26)

Vorher 18 Animationen, jetzt 26. Jede loest ein anderes Ereignis auf,
keine ist Kosmetik. Alle laufen ueber `anim_apply()` und wirken bei
allen 5 Effekten (kein "still verpuffen"-Bug moeglich).

Neu:
- **kippen** - Wort kippt nach vorn wie ein Buch das aufklappt
  (Tilt um X-Achse mit Feder-Ausklang). Fuer Kapitel/oeffnet.
- **explosion** - 8 vertikale Streifen fliegen radial auseinander und
  ziehen sich wieder zusammen (Impact + Retract, 0.55 s).
- **magnet** - umgekehrte Explosion: Streifen kommen aus Streuung
  zusammen mit wachsender Deckkraft. Fuer Sog/Anziehung.
- **wackel** - Cartoon-Sinus-Loop auf y + kleine Skala. Amplitude
  moduliert von der Stimme. Fuer Witz/Quatsch/kindisch.
- **regen** - Streifen fallen von oben nacheinander (linke zuerst),
  weichen mit ease_out ein. Fuer Regen/Tropfen/Rieselt.
- **zoom_punch** - startet bei 1.25x, faellt quadratisch auf 1.0.
  Ganz kurz, sitzt genau auf Onset. Fuer Punchline/Achtung/Wumms.
- **rutsche** - Streifen kommen einzeln von rechts rein (gestaffelt).
  Fuer rutscht/gleitet/slidet.
- **stempel** - kommt aus 1.8x rein mit weichem Impact-Blur, stanzt
  scharf, kleines Nachbeben. Fuer endgueltig/offiziell/beschlossen.

HINTS-Konflikte bereinigt (Bug-Vorbeugung):
- `schub` hatte `explo` -> ging auf `explosion` weg
- `sturz` hatte `rutscht` -> ging auf `rutsche` weg
- `knall` hatte `endgueltig` -> ging auf `stempel` weg

REGIE_PROMPT + Editor-Combobox + ANIM_HINTS (Keyword-Matching) fuer
alle 8 erweitert. Selbstschutz: der bestehende Test "Editor kennt alle
Animationen" faengt automatisch, wenn die Liste auseinanderlaeuft.

Selftest: +36 Tests netto (jede Animation wirkt bei jedem Effekt, GUI-
Liste + KI-Prompt kennen sie, parse_regie akzeptiert sie, HINTS-Match
korrekt, spezifische Verhaltens-Tests pro Anim).
Regression: 325/326 gruen (vorher 290/291, +35 netto). Whisper-Fail
unveraendert.

GUI-Smoke `xvfb-run` -> GUI_OK.

## v70 - Musik-Beat-Erkennung

Beat-Sync haengt jetzt nicht mehr nur an Sprech-Onsets, sondern reagiert
auch auf den Musik-Beat (Kick/Sub-Bass). Text pulsiert mit Musik UND
Stimme - wie ein handgeschnittener Musik-Cut.

Umsetzung:
- Neue Funktion `music_beats(voice_wav, n_frames, fps)` in `render.py`.
  Ohne librosa - eigene Kette: Tiefpass < 200 Hz -> Amplitude-Delta ->
  Peak-Threshold (nur echte Peaks in die Auto-Korrelation, damit
  Rauschen nicht zaehlt) -> Auto-Korrelation im Bereich 60-180 BPM ->
  Peak-Suche. Rueckgabe: (beat_env, bpm, conf).
- Confidence-Berechnung kombiniert: (a) Peak-over-Median (robust gegen
  Harmonische), (b) z-Score des Peaks (gegen zufaellige Rauschmuster).
  So triggert reines Talking-Head nicht faelschlich.
- Pipeline mischt Beat-Envelope in `aud_onset` per `max(...)`, gewichtet
  mit `music_beat * conf`. Confidence-Gate bei 0.10: kein klarer Beat
  -> kein Effekt.
- Config: `effects.music_beat` (0-1, Default 0.6). GUI-Regler direkt
  unter Beat-Sync in der Karte "Sonstiges/Feintuning".
- Kundenprofil sichert `mbeat_var`.

Selftest: +13 neue Tests (Funktion existiert, Config, 120 BPM erkannt
(+/- 5 BPM), Confidence hoch bei klarem Beat > 0.30, Envelope-Peaks,
Rauschen -> Confidence < 0.30, Stille -> alles 0, Pipeline-Kopplung,
Confidence-Gate, GUI-Regler, Profil-Sicherung).
Regression: 290/291 gruen (vorher 279/280, +11 netto - der Whisper-
Modell-Check unveraendert).

GUI-Smoke `xvfb-run` -> GUI_OK.

Ehrliche Grenze: Erkennt Kick/Sub-Bass zuverlaessig, subtile Snare-only-
oder Off-Beat-Muster koennen niedrigere Confidence liefern. In-The-Wild-
Test auf Musik-Videos macht Ismet auf Windows. Der Confidence-Gate
verhindert False-Positives - im Zweifel wirkt der Musik-Beat nicht.

## v69 - Hintergrund-Blur (Depth-basiert)

Bokeh-artiger Kino-Blur waehrend jedes Caption-Moments: Person + Text
bleiben scharf, der Hintergrund wird weichgezeichnet. Lenkt den Blick
wie in einem Interview mit offener Blende. Auf B-Roll bewusst AUS -
dort ist die Umgebung das Motiv.

Umsetzung:
- Neue Funktion `apply_bg_blur(frame, alpha, depth_n, strength, W, H)`
  in `render.py`. Blur auf 1/4-Aufloesung (Gaussian, sigma ~4 % der
  Bildbreite), dann hochskaliert. Alpha ist Vordergrund-Maske
  (weichgezeichnet fuer Bokeh-Rand). Wenn Depth vorhanden, verlaengert
  das den Blur weiter in die Ferne (Nah bleibt scharf, weit weg mehr).
- Blur-Staerke folgt der Moment-Fade-Kurve: ramp 0.20 s rein, halten,
  0.35 s raus - der Blur atmet mit dem Text. Power-3-Momente kriegen
  einen kleinen Zuschlag.
- Ohne Alpha UND ohne Depth: kein Blindwurf (Selbstschutz).
- Config: `effects.bg_blur` (0-1, Default 0.5). GUI-Regler in Karte
  "Freistellung & Masken" (unter Maskenqualitaet).
- Kundenprofil sichert `bgblur_var`, damit es beim Profilwechsel
  mitwandert.

Selftest: 10 neue Tests (Funktion existiert, Config, strength=0 no-op,
Maske-fehlt no-op, Blur wirkt im Hintergrund, Vordergrund bleibt scharf,
Depth-only Fern > Nah, B-Roll-Ausschluss, GUI-Regler, Profil-Sicherung).
Regression: 279/280 gruen (vorher 269/270, +10 neu). Der pre-existierende
Whisper-Modell-Check bleibt umgebungsbedingt rot.

GUI-Smoke `xvfb-run` -> GUI_OK.

Ehrliche Grenze: Rechenzeit steigt pro Moment-Frame um ~1-2 ms (bei 1080p);
das ist unkritisch. Sichtbare Bokeh-Qualitaet vs. Blur-Sigma bewertet
Ismet am echten Windows-Material - Gaussian bei 4 % kann bei sehr
homogenen Hintergruenden zu weich wirken (dann Regler zurueck) oder
bei viel Struktur zu wenig (Regler hoch).

## v68a - Undo/Redo: Buttons ausgrauen (Klarheit)

Nachtrag zu v68. Die Undo/Redo-Buttons waren immer klickbar - auch wenn
nichts zurueckzuholen oder vorzuholen war. Klick ins Leere passierte
schweigend nichts. Fuer einen bedienerfreundlichen Editor gilt: sichtbar
= klickbar. Buttons werden jetzt ausgegraut, wenn der Stack am Ende ist.

Umsetzung:
- Neue Funktion `refresh_buttons()` liest `hist.can_undo/can_redo` und
  ruft `Pill.set_enabled()`.
- Wird nach jedem Push (Trace + debounced) und nach jedem Undo/Redo
  aufgerufen.
- Initialer Aufruf beim Editor-Aufbau: Startzustand hat 1 Snapshot,
  also beide grau - Nutzer sieht sofort "nix zu tun".
- Neuer Wrapper `_push_and_refresh()` fuer sofort-Traces (Comboboxen,
  Checkbox); debounced ruft nach dem 400ms-`after` denselben Wrapper.

Selftest: +6 neue Tests (Buttons-Ausgrauung Source-Check + 5 Verhaltens-
Tests ueber `can_undo/can_redo` in EditorHistory).
Regression: 269/270 gruen (vorher 263/264, +6 neu). Der eine bekannte
Fail (Whisper-Modell) unveraendert.

GUI-Smoke `xvfb-run` -> GUI_OK.

## v68 - Undo/Redo im Momente-Editor

Editor konnte bisher keinen Fehlklick zurueckdrehen - versehentlich Effekt
verstellt, Haken raus, Text ueberschrieben = Fenster schliessen + neu
analysieren, damit die alte Fassung zurueckkam. Ab jetzt Strg+Z / Strg+Y
(auch Strg+Shift+Z fuer Mac-Gewohnheit) plus zwei Buttons "Undo"/"Redo"
im Knopfbalken.

Umsetzung:
- Neue Klasse `EditorHistory` in `gui.py` (Modulebene, testbar) - haelt
  Snapshot-Stack, kennt `push/undo/redo/current/can_*` und `quiet`-Flag.
  Deckel `cap=200` gegen unbegrenztes Wachstum.
- Snapshot = eine Zeile pro Moment mit den 7 Widget-Werten
  (aktiv/fx/power/anim/text/szene/lage). Traces auf allen tk-Variablen.
- Text-Entry pusht DEBOUNCED (400 ms Ruhe) - sonst haetten wir einen
  Snapshot pro Tastendruck und Strg+Z ginge Buchstabe fuer Buchstabe
  zurueck. Combobox/Checkbox pushen sofort.
- `apply_snap()` setzt `quiet=True`, damit das Zurueckschreiben der Werte
  nicht neue Snapshots ausloest (Endlos-Selbstschutz).
- Doppelte Snapshots werden verworfen (Combobox feuert 2x pro Aenderung).
- Bindings `<Control-z/Z/y/Y/Shift-Z>` am Toplevel; werden beim Schliessen
  wieder entfernt, sonst wuerden sie im Hauptfenster mitlaufen.
- `save()` cancelt einen anstehenden Debounce-Push (State-Konsistenz).

Selftest: 12 neue Tests (initial leer, push/undo/redo, Grenzen, kein
Doppel-Push, Cap greift, quiet blockiert, neuer Push kappt Redo-Zweig,
Source-Checks fuer Bindings + debounced/sofort-Traces).
Regression: 263/264 gruen (vorher 251/252, +12 neu). Der einzelne FAIL
"Whisper-Modell liegt im App-Ordner" ist Umgebungsprüfung, existiert
seit v66 und ist auf Ismets PC gruen (Modell da).

GUI-Smoke: `xvfb-run` -> GUI_OK. Fensteraufbau ohne Regression.

## v67 - Zurueck auf Qualitaets-Kurs: lokal fuer Ismet, API-Transkription

Richtungswechsel: Kein Verkauf, kein Abo, kein Server. Tool laeuft lokal auf
Ismets PC mit seinem eigenen OPENAI_API_KEY. Alle Entscheidungen = Qualitaet.

- Transkription: Default wieder OpenAI Whisper API (whisper-1) = beste Qualitaet
  bei Fachbegriffen/Namen. Lokales faster-whisper bleibt als Offline-Option
  (transcription.engine: local), ist aber nicht mehr Default.
- KI-Regie (Keyword + Szene): laeuft wie immer ueber den lokalen Key. Kein
  optionales Pro-Feature, keine Heuristik-Degradierung.
- Gestrichen: Lizenzsystem, Stripe, Server-Proxy, Verkaufsfertig-Roadmap.

Regression: 265/265 gruen.
