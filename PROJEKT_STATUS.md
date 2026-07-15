# DouchkoVE Captions — Projektstatus (Juli 2026)

Automatische Premium-Untertitel im Editorial-Stil. Windows, C:\premium_captions, DirectML-GPU.

## Kern-Features
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
