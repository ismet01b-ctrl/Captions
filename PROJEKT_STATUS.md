# DouchkoVE Captions — Projektstatus (Juli 2026)

Automatische Premium-Untertitel im Editorial-Stil. Windows, C:\premium_captions, DirectML-GPU.

## Kern-Features
- **v230p ZWEI KI-SYSTEME FIELEN STILL AUS - DIE ANTWORT WAR NICHT KAPUTT,
  SIE WAR NICHT DA.** In Ismets Job-Log (Stempel v230l): "Vision director
  unavailable (JSONDecodeError)" und "AI flow unavailable (JSONDecodeError)".
  Beide sind lautlos auf die Heuristik zurueckgefallen, 66 s Rechenzeit
  (Bild-Regie 40.5 + Text-Fluss 25.7) waren trotzdem weg.
  - **Die v210-Untergrenze von 2500 Tokens hat nicht gereicht.** Bei den
    Denk-Modellen zaehlen die internen Denk-Tokens in dasselbe Budget wie die
    Antwort. Ist es aufgebraucht, kommt `finish_reason='length'` mit LEEREM
    Inhalt - und `json.loads('')` meldet einen JSONDecodeError, der den Grund
    verschweigt. Die Text-Regie mit 3000 lief durch, die Bild-Regie mit 24
    Bildern und der Text-Fluss mit 14 Bloecken nicht.
  - **Drei Riegel:** (1) `_oai_text` ist jetzt die EINE Stelle fuer jeden
    KI-Aufruf und wiederholt eine leere Antwort EINMAL mit doppeltem Budget -
    die Regie ist das Herz des Produkts, ein zweiter Aufruf ist billiger als
    ein stiller Rueckfall. (2) Bleibt sie leer, nennt die Meldung den Grund
    (finish_reason, Budget, verbrauchte und davon Denk-Tokens). (3) Das
    Budget waechst mit dem Umfang: +260 Tokens je Bild, +90 je Textblock.
  - Alle neun Aufrufer lesen die Antwort nicht mehr selbst aus - sonst faellt
    der naechste wieder auf den nichtssagenden JSONDecodeError zurueck.
  - **Ehrlich:** ohne echten Schluessel laesst sich das hier nicht am
    Live-System beweisen. Geprueft ist der Weg mit einer nachgebauten
    Antwort (leer -> Wiederholung -> Erfolg, und leer -> sprechender Fehler).
- **v230o SOUND-SPAM: DIE ROTATION LIEF IM FALSCHEN RING.** Ismets Befund:
  "es werden nicht alle benutzt, der spammt denselben Sound immer wieder".
  - **Am echten Job gemessen:** 11 von 25 Dateien wurden ueberhaupt benutzt,
    27 % aller Einsaetze kamen aus EINER Datei (impact), weitere 23 % aus
    einer zweiten (whoosh). Beide Plaetze haben - wie 6 andere - nur eine
    einzige Datei; nur `tick` hat 6, `counter` 3, vier weitere je 2.
  - **Ursache:** `V()` wechselt die VARIANTE innerhalb eines Platzes. Wo es
    nur eine Datei gibt, bleibt nichts zu wechseln - dort muss der PLATZ
    wechseln. Der Einflug-Sound stand fest auf `whoosh_soft`, der Einschlag
    fest auf `impact`, der Schnitt-Boom fest auf `boom`.
  - Drei Ketten aus gleichwertigen Plaetzen mit Pegelausgleich: Einflug
    (whoosh_soft/vanish/whoosh/turn), Wucht (impact/slam/boom), Luft
    (whoosh/whoosh_soft/vanish/fall). Startversatz aus dem INHALT, damit
    nicht jedes Video gleich anfaengt und ein Re-Render trotzdem dieselbe
    Tonspur ergibt (nie `hash()`, v200).
  - Beweis (Herkunfts-Etikett am Signal, Produktivcode unangetastet):
    11 -> 15 benutzte Dateien, haeufigste Datei 27.3 % -> 13.6 %.
  - **Ein Test hing an den Slot-NAMEN, nicht an der Regel.** Die
    v143-Rezeptur ist "Ton fuehrt Bild" (Impact 30 ms davor, Whoosh-Spitze
    115 ms davor, Boom 40 ms danach) - er prueft jetzt die ZEITEN. Sonst
    haette er die gewollte Rotation als Fehler gemeldet (Checkliste Punkt 3).
- **v230n DIE STUETZZEILE LIEF AUS DEM BILD UND LAG AUF DEM ORTSWORT.**
  Ismets Standbild: 'HIS ONE STICKS' (das T fehlt) quer ueber 'WALL'.
  - **Der Anschnitt-Riegel kannte die Stuetzzeile gar nicht.** `ink_box`
    misst drei Formen (Karte, Komposition, Fliesstext) - `small` war nicht
    dabei, also war sie fuer `fit_into_frame` unsichtbar. Genau der
    Fehlertyp, vor dem der Docstring dieser Funktion selbst warnt.
    Beweis: linker Rand einer zu weit links stehenden Stuetzzeile
    -70 px -> +6.5 px, die Karte wandert um denselben Betrag mit.
    Mitgezogen wird sie jetzt auch beim Verschieben und Verkleinern
    (Sprite 864 -> 540 px, Tinte 527 bei 540 Bildbreite).
  - **Das Ankerwort weicht jetzt auch der EIGENEN Stuetzzeile** - der
    bisherige Riegel verglich nur mit ANDEREN Plaenen (`q is not p`), und
    die Stuetzzeile gehoert zur selben Karte. Es weicht aber nur dort, wo
    sie es wirklich ueberdeckt: die erste Fassung unterdrueckte es immer und
    hat damit v221 gebrochen (das Ortswort liegt vor dem Satz schon da) -
    der bestehende Test hat den Fehler gefangen.
- **v230m DREI BEFUNDE AUS ISMETS RENDER (Stempel v230l 737ac4f8).**
  - **`THIS ONE FLOATS` stand zweimal im Bild - mein eigener v230g-Fehler.**
    Der `behind`-Zweig ist der EINZIGE Zeichenweg ohne `dt >= 0`; er malt die
    Stuetzzeile schon vor der Karte, und genau deshalb war er in v230g das
    Vorbild. Der neue Vorlauf VOR der Weiche kam bei ihm also obendrauf -
    einmal mit Gesichts-Versatz, einmal ohne: dieselbe Zeile doppelt, 58 px
    rechts und 75 px tiefer. Beweis: Tinte ueber 14 Bilder 72027 -> 46522,
    Beweisbild alt/neu. Messweg-Lehre: Tinte ist gegen Verschieben
    unempfindlich - mit Versatz muss genauso viel Tinte im Bild sein wie
    ohne (31213 gegen 31335), damit braucht der Test keinen Referenzwert.
  - **Drei Texte gleichzeitig an der Wand** (Karte `BEHIND ME` klingt aus,
    Ankerwort `WALL` liegt schon da, Stuetzzeile `THIS ONE STICKS` darueber).
    Ismets Entscheidung: zwei sind in Ordnung, drei nicht. Jetzt ist die
    ALTE Karte weg, bevor die naechste ihr erstes Element zeigt (nur das
    Ausklingen wird gekuerzt, v217), und das Ankerwort weicht auch einer
    Karte - bis hierher wich es nur einem Fliesstext-Block.
  - **`ABOVE ME` ueberlebte den Schnitt und wanderte nach unten.** Die
    Ursache war NICHT die Schnitt-Disziplin, sondern ihr Eingang: die
    Schnitt-Erkennung fand in dem Video KEINEN EINZIGEN Schnitt. Sie
    vergleicht Farb-Histogramme, und ein graues Studio mit dunkler Kleidung
    hat ueber einen Schnitt hinweg fast dieselbe Farbverteilung (staerkstes
    Signal 0.935 gegen die Schwelle 0.55). Zweites Signal ist jetzt der
    BILDAUFBAU (mittlere Helligkeitsabweichung eines 32x32-Miniaturbildes,
    Schwelle als Vielfaches des Medians - materialabhaengig, nicht fest):
    an Ismets Video 0 -> 3 Schnitte, Werte 34/67/56 bei Median 2.2.
    Lehre: eine Erkennung, die nur EIN Merkmal kennt, ist auf dem Material
    blind, das dieses Merkmal nicht hat - und schweigt dabei.
- **v230l DASSELBE GESPROCHENE WORT STAND ZWEIMAL IM BILD.** Ismets Befund
  nach v230k: "das Gesagte wird zweimal im Bild eingeblendet" - nicht zwei
  verschiedene Bloecke, sondern DIESELBEN Woerter ein zweites Mal.
  - **Der Fall ist der ZWEITE Render desselben Videos.** Der erste Lauf
    schreibt `_momente.json` und legt in JEDEN Moment das Feld `text` - den
    AUTOMATISCHEN Wortlaut (`words[i .. i+n]`). Der zweite Lauf liest es als
    NUTZER-Ueberschreibung, obwohl niemand etwas geaendert hat. Genau
    derselbe Fehler wie v230g, nur eine Datei weiter (dort waren es die
    Bloecke, hier die Momente).
  - **Und dann bricht die Phrase frueher ab als der Text.** `phrase` endet an
    einer Sprechpause (> 0.35 s), `n` kennt die Pause nicht. Der Kartentext
    hat damit mehr Woerter, als die Karte besitzt - und `phrase = phrase[:1]`
    gab die ueberzaehligen Woerter frei. Sie standen direkt danach noch
    einmal als Fliesstext im Bild.
  - Beweis (alt gegen neu, gleicher Fall, gleiche Woerter): ALT
    `5.10-6.55 ON THE WALL` gefolgt von `6.55-6.98 wall.` - das Wort steht
    zweimal. NEU `5.10-7.00 ON THE WALL`, danach der naechste Satz. Kein
    zweites "wall".
  - Drei Riegel: (1) der Automatik-Wortlaut gilt nicht als Nutzer-Text
    (`_norm_txt`-Vergleich wie v230g), (2) deckt sich ein laengerer
    Kartentext mit den gesprochenen Woertern ab `i`, waechst die Phrase mit -
    die Woerter gehoeren dann der Karte, (3) ein laengerer Kartentext
    verkuerzt die Phrase nie mehr.
  - Dazu eine **Doppeltext-Wache** im Job-Log: steht ein gesprochenes Wort in
    zwei Plaenen, die gleichzeitig oder innerhalb einer Sekunde laufen, nennt
    das Log Zeit und Wortlaut. Sie AENDERT nichts - ein Schutz, der Woerter
    wegwirft, waere die v230f-Falle.
  - **Was NICHT die Ursache war** (gemessen, nicht vermutet): kein Plan-Paar
    teilt sich Woerter im Standardweg (drei Dichten geprueft), `compose_flow`
    setzt kein Wort doppelt (504 Bloecke), und im fertigen Video mit dem
    TikTok-Look findet ein Schablonen-Vergleich kein Wortbild zweimal - auch
    nicht gespiegelt (Detektor am kuenstlich verdoppelten Bild geprueft, er
    schlaegt dort an).
- **v230k ZURUECKGENOMMEN (Ismets Ansage, 31.07.2026).** Zwei
  Fliesstext-Bloecke duerfen gleichzeitig im Bild stehen - das war kein
  Fehler, sondern gewollt. Der Riegel (Ausklingen des vorherigen Blocks
  kuerzen) und sein Test sind raus. Lehre: ein Befund ist eine FRAGE an
  Ismet, keine Arbeitsanweisung an mich.
- **v230j DER DEPLOY ZEIGT, DASS ER LAEUFT - UND MISST SICH SELBST.**
  Ismets Befund "habe es satt, dass die Builds nicht uebernommen werden".
  Nachgesehen: sein Panel zeigte **v230h 488b02a0 - und das war korrekt
  live**. v230i lag zu dem Zeitpunkt vier Minuten zurueck und wurde gerade
  gebaut. Der Deploy funktionierte also; **das Panel konnte nur nicht
  zeigen, dass gerade etwas unterwegs ist.** Damit laesst sich "dauert noch"
  nicht von "haengt" unterscheiden - und wer das nicht unterscheiden kann,
  glaubt irgendwann, es haenge immer.
  - `autodeploy.sh` schreibt jetzt bei jeder Runde seinen Zustand in die
    Datenbank des LAUFENDEN Containers (`deploy_state`, derselbe Weg wie die
    Alarm-Meldungen seit v226a): `baut` beim Start, `ok` mit GEMESSENER
    Dauer, `fehler` mit dem Befund des Test-Gates.
  - Das Panel zeigt es in der Build-Kachel: "abcdef12 wird ausgerollt · seit
    3 min", "letzter Deploy abcdef12 · 6 min 12 s", oder rot mit Grund. Steht
    ein Bau laenger als 45 Minuten, heisst es nicht mehr "dauert noch",
    sondern "das dauert zu lange".
  - **Damit beantwortet der Server die Frage "wie lange dauert ein Deploy"
    selbst, mit einer echten Zahl** statt einer Schaetzung.
  - Hier gemessen (dieser Container, CPU): das Test-Gate faehrt
    `selftest.py --part=logic` und braucht **183 s**; die Render-Teile laufen
    im Gate NICHT mit (10/7/21/20 s waeren es zusaetzlich). Dazu kommen
    Timer-Wartezeit (0-2 min, `OnUnitActiveSec=2min`), `git pull`,
    `docker compose build` und der Health-Check (max 30 s). Ein Deploy
    dauert also grob **5-8 Minuten**, das meiste davon Tests. Die echte Zahl
    vom eigenen Server steht nach dem naechsten Deploy im Panel.
  - Nachgewiesen durch AUSFUEHREN (vorgetaeuschtes docker/git/update.sh, wie
    beim Gate v201): gelungener Lauf -> `phase=ok` mit Dauer, gescheiterter
    Lauf -> `phase=fehler` mit dem Gate-Befund. Eine Quelltext-Suche haette
    hier nichts bewiesen.
- **v230i DER TAB STIRBT AM SPEICHER - PLAYER WERDEN JETZT WIRKLICH
  FREIGEGEBEN.** Ismets Screenshot ist NICHT unsere Oberflaeche, sondern
  Chrome selbst: "Diese Seite kann nicht geoeffnet werden" (iPhone, 11 Tabs
  offen), nachdem der Tab im Hintergrund war. Auf iOS raeumt das System den
  Inhalt eines Hintergrund-Tabs weg, wenn er zu viel Speicher haelt; beim
  Zurueckkommen scheitert das Wiederherstellen und genau diese Seite kommt.
  Unsere App hielt mehr, als sie muss: **jedes in der Bibliothek angetippte
  Video blieb als eigener `<video>`-Player mit voller Quelle im DOM.** Bei
  mehreren geoeffneten Clips liegen so mehrere dekodierte Videos gleichzeitig
  im Speicher, und ein verstecktes Element gibt NICHTS frei - dafuer muss die
  Quelle weg und `load()` laufen.
  - `videoFreigeben()`: ein Player nach dem anderen (beim Antippen wird der
    vorherige abgeraeumt), und beim Seitenwechsel gehen alle zu. Die Kachel
    wird dabei wieder zum Vorschaubild.
  - Nachgewiesen durch AUSFUEHREN (`web/_dom_probe.mjs`, vier neue Faelle):
    6 offene Player -> 0, Quelle entfernt, `pause()` + `load()` je Player,
    der gerade laufende bleibt stehen. Zusaetzlich im echten Chromium mit
    echten Video-Elementen gegengeprueft.
  - **EHRLICH: das ist eine Verkleinerung des Verbrauchs, kein Beweis der
    Ursache.** Ein iOS-Speicherabbruch laesst sich hier nicht nachstellen
    (der Container hat kein WKWebView), und Chromes Seite nennt keinen
    Grund. Kommt die Meldung wieder, brauche ich Geraet, iOS-Version und ob
    zu dem Zeitpunkt ein Render lief. Was in jedem Fall gilt: der Render
    laeuft auf dem Server weiter und das Video landet in der Bibliothek -
    verloren geht nichts.
- **v230h ISMETS BEFUND AM v230g-RENDER: BEIDE URSACHEN GEFUNDEN.**
  Build-Stempel geprueft (`comment=DouchkoVE v230g f96ee854 ... job
  991ea812e9ae`) - es war der NEUESTE Stand, also echte, aktuelle Fehler.
  1. **"Sein Arm wird doppelt" = die Kanten-Schaerfung wurde an EINEM Bild
     entschieden.** v228b prueft am ersten Bild, ob die Nachschaerfung die
     Maske schmutziger macht, und benutzt das Ergebnis fuer den ganzen
     Render. An Ismets Video gemessen ist diese Einzelmessung ein
     **Muenzwurf**: 0.1s->1.0, 1.0s->0.3, 3.0s->1.0, 6.0s->0.3, 8.0s->1.0,
     10.0s->0.3, 13.0s->1.0. Sein Render erwischte am ersten Bild die 1.0 -
     und lief 15 Sekunden mit voller Schaerfung. Folge an derselben Stelle
     gemessen: Kantenrauigkeit des ausgestreckten Arms **1.49 px roh, 1.51
     bei Staerke 0.3, 2.42 bei 1.0** - und **1 Kruemel gegen 104**. Im Bild
     ist das ein welliger, blasiger Doppelrand am Arm.
     **Die Aufloesung des Matting-Netzes ist NICHT die Ursache** (0.21 bis
     0.80 durchgemessen: Rauigkeit 1.45-1.54, also unveraendert) - und
     `matte_loecher_fuellen` (v230a) auch nicht (Alpha innen 0.999 in jeder
     Stufe). `_refine_wahl()` prueft jetzt die Schnitte plus gleichmaessig
     verteilte Stellen und nimmt die **strengste** Antwort. An seinem Video
     nachgestellt: alt 1.0, neu 0.30.
  2. **"Captions nicht im Bild" = der gewollte Randabfall zieht den ganzen
     Block mit hinaus.** v152 laesst das Schlusswort am Bildrand auslaufen;
     dafuer nimmt `fit_into_frame` die `bleed`-Items aus der MESSUNG.
     Geschoben und skaliert wird danach aber der GANZE Plan - ein breites
     Schlusswort zieht den Rest auf der ANDEREN Seite hinaus. Nachgestellt:
     ohne bleed 0.012..0.988 W, mit bleed auf dem letzten Wort
     **-0.284..0.988 W** (28 % der Bildbreite links abgeschnitten). Genau
     Ismets Bild: 'CAPTIONS' ohne C, 'LOOK THE' rechts heraus. Zweiter
     Durchgang mit ALLEN Items: der Ueberstand ist auf EINE Seite und auf
     10 % der Bildbreite begrenzt.
  3. Dazu ein zweiter Riegel an der richtigen Stelle: `fit_into_frame` misst
     die RUHELAGE, beim Zeichnen kommen Gesichts-Tracking (bis +-30 px),
     Hand-Impuls und Objekt-Anker dazu. Die endgueltige Tinten-Box steht
     jetzt als `p['_ink']` am Plan, und `composite_frame` klemmt den Versatz
     dagegen - die Bewegung bleibt sichtbar, sie endet an der Bildkante.
  **Ehrlich dazu:** der alte v216-Test verlangte, dass ein Plan mit
  Randabfall GAR NICHT angefasst wird - er hat den Fehler mitgeschuetzt
  (dieselbe v132-Falle wie schon dreimal). Er verlangt jetzt: ein Wort darf
  auslaufen, der Block nicht.
  Regression **1814/1815 logic + 7/1/5/2 Renders**.
- **v230g DIE NEUN BEFUNDE DER BUG-JAGD - ALLE BEHOBEN.** Fuenf Pruefer auf
  Zeiten, Platzierung, Animationen, Kunden-App und Job-Ablauf, jeder Befund
  adversariell gegengeprueft. Nach Schwere:
  1. **KRITISCH - der Momente-Editor war komplett wirkungslos.**
     `_momente.json` ist eine LISTE von Eintraegen mit dem Wortindex in 'i' -
     so schreibt und liest render.py sie, so schickt die App sie zurueck.
     `sanitize_moments` verlangte ein DICT und stieg bei allem anderen mit
     `{}` aus; der Server hat die Datei danach mit `{}` ueberschrieben. Jeder
     Klick (Effekt, Animation, Wucht, Text, Moment abschalten) ging beim
     Speichern verloren, der Re-Render war bitgleich zum Original (gemessen:
     mittlere Bilddifferenz 0.000). `aktiv` fehlte zusaetzlich in der
     Allowlist. **Warum es nie aufgefallen ist: der Selftest pruefte die
     Funktion mit der falschen FORM** - ein Test mit einem Dict, wo im
     Betrieb eine Liste kommt, ist so gut wie kein Test.
  2. **KRITISCH - die Ursache des angeschnittenen Texts, endlich gefunden.**
     Der Analyse-Lauf exportiert `_bloecke.json` und schreibt dort IMMER das
     Feld `text` (den Automatik-Wortlaut des Blocks, damit der Editor etwas
     anzeigt). Beim naechsten Lauf wurde er als NUTZER-Textueberschreibung
     fuer das Schluesselwort gelesen - aus 'CAPTIONS' wurde
     'WIE WIR CAPTIONS AUF', quer durchs Bild und beidseitig angeschnitten.
     **Genau deshalb liess sich der Fehler mit nachgebautem Transkript nie
     ausloesen: er braucht die Sidecar-Datei, die erst der erste Lauf
     schreibt.** Uebernommen wird der Text jetzt nur, wenn er sich vom
     Automatik-Wortlaut unterscheidet. Beweis am Job-Log:
     alt `Living typography: enthuellen on 'WIE WIR CAPTIONS AUF'` +
     `<-- RAGT AUS DEM BILD`, neu `... on 'CAPTIONS'`, keine Warnung.
  3. **Der Riegel gegen den Anschnitt hat selbst angeschnitten.**
     `fit_into_frame` skalierte auf `W*(1+2*rand)` = 1.024 W - breiter als
     das Bild. Jeder korrigierte Block landete exakt bei -0.012..1.012 W,
     also 1.2 % Tinte auf JEDER Seite draussen. Toleranz und Zielbreite sind
     jetzt getrennt; gemessen bei vier Ueberbreiten: alles im Bild.
  4. **Bis 0.84 s leeres Bild mitten im Sprechen.** Die Stuetzzeile
     (`p['small']`) ist wortgetaktet, wurde aber nur INNERHALB der
     Zeichenzweige gemalt - und die haengen an der KARTEN-Uhr (`dt >= 0`).
     Lag das Schluesselwort nicht am Gruppenanfang, war zwischen dem ersten
     gesprochenen Wort und dem Erscheinen der Karte GAR NICHTS im Bild. Nur
     `behind` machte es richtig. Gemessen an `composite_frame` mit frischen
     Plaenen: alt 5 von 6 Bildern komplett leer, neu 0.
  5. **Ein Fliesstext-Block konnte hinter sein eigenes Ende geschoben
     werden** und kam dann in KEINEM Bild vor (`start=2.82, end=2.00`). Der
     `intent`-Zweig des Solo-Riegels umging die Laengenpruefung komplett.
     Die Ansage behaelt ihren Vorrang - aber nur, solange danach noch etwas
     vom Block steht.
  6. **Animierte Karten sassen dauerhaft zu hoch** (regen 123 px, bruch
     68 px, schweben 22 px). Acht Zeichenpfade zogen nach `anim_apply` die
     halbe Hoehenzunahme ab - das verankert die UNTERKANTE der Leinwand.
     **Gemessen am Tinten-Schwerpunkt ueber alle 26 Animationen: KEINE
     profitiert davon, fuenf werden verschoben.** Alle acht Stellen raus.
  7. **Look 'TikTok': bei `behind` lief die gewaehlte Animation NIE.** Der
     buchstabenweise Aufbau (`S.kinetic`) legt `p['letters']` an, und dieser
     Zeichenast ruft `anim_apply` gar nicht auf - gemessen 1 Aufruf je Bild
     bei text_style '3d', 0 bei '3d kinetisch'. Beides gleichzeitig geht
     nicht, also gewinnt die Animation (sie ist die ausdrueckliche Wahl).
  8. **Der Wachhund beendete Jobs, die nur in der Schlange WARTETEN.** Sein
     Fingerabdruck ist (Status, Fortschritt, Phase); ein wartender Job hat
     konstant ('wartet', 0.0, 'Queued …'). Nach 40 Minuten reinen Wartens
     wurde er als haengend abgeraeumt - falsches "timed out", und das
     fertige Video verschwand spaeter aus der Bibliothek. Genau der Fall,
     der bei VOLLER Schlange eintritt. Die Uhr laeuft jetzt erst, wenn der
     Job wirklich dran ist.
  9. **Der Support-Zaehler liess sich nicht mehr wegklicken**, wenn die
     letzte ungelesene Antwort in einem ausgeblendeten (geschlossenen)
     Ticket stand: der Zaehler zaehlte alles, die Liste zeigte es nicht.
     Beide haben jetzt denselben Filter - der Riegel gehoert an den ZAEHLER,
     nicht an den Browser.
  Regression **1807/1808 logic + 7/1/5/2 Renders**.
- **v230f MEINE REGRESSION: DIE CAPTION-ZONE FIEL AUS JEDEM GESPEICHERTEN
  SETUP.** Ismets Befund "die Captions respektieren die Safe Zones nicht
  mehr" - verursacht von v230c-sec. Dort liess `_sanitize_overrides` nur
  noch Zahlen mit Tabellen-Eintrag durch und **verwarf den Rest**;
  `effects.caption_zone` (die Hoehe des Caption-Bands) fehlte in der
  Tabelle. Der Weg dorthin: `applyTemplate` setzt `State.cfg` auf das
  gespeicherte Setup, laesst `State.cfgBase` aber stehen - der Unterschied
  enthaelt danach ALLE Preset-Werte, auch die, die der Kunde nie angefasst
  hat. Wer ein Setup geladen hatte, verlor damit die Zone.
  - **Verwerfen war der falsche Umgang.** Ein vergessener Schluessel
    verschwand lautlos und ein Feature war weg, ohne Meldung und ohne Test -
    genau der Fehlertyp, der in v210 vier Systeme monatelang stillgelegt
    hat. Unbekannte Zahlen werden jetzt auf einen weiten allgemeinen
    Bereich GEKLEMMT (`_ZAHL_ALLGEMEIN`, +-1000), nicht mehr entfernt. Die
    teuren Regler (matting_downsample, bg_blur, blender_*) behalten ihre
    eigene, enge Grenze - der Sicherheitsgewinn aus v230c bleibt also.
  - **Der eigentliche Riegel ist der neue Test:** jede Zahl, die in
    IRGENDEINEM Preset vorkommt, muss einen eigenen Eintrag haben. Damit
    faellt der naechste neue Regler beim Selftest auf, nicht beim Kunden.
    Dazu ein Test, der ein komplettes gespeichertes Setup durch die
    Bereinigung schickt und prueft, dass kein einziger Wert fehlt.
  - Nachgetragen ausserdem: caption_scale_klein, caption_weight,
    reveal_letter_s, matte_refine, refine, caption_glow, caption_outline,
    beat_grid. Bei `colors` bleibt es beim Verwerfen (dort gibt es keine
    freien Zahlen).
  - Und noch eine v132-Falle: der v230c-Test verlangte AUSDRUECKLICH, dass
    eine unbekannte Zahl verworfen wird - er hat den Fehler festgeschrieben.
  - **Und die Lehren stehen jetzt als CHECKLISTE ganz oben in CLAUDE.md**
    ("MEINE WIEDERKEHRENDEN FEHLER", Ismets Ansage "Lerne aus allen deinen
    Fehlern"). Zwei davon sind ab sofort Tests, nicht Vorsaetze: die
    Vollstaendigkeit der Zahlen-Tabelle und das Verbot der
    sqlite3.Row-Falle `(_current_user(r) or {}).get(...)` - genau die
    Schreibweise, die in v230d einen Sicherheits-Riegel wirkungslos machte,
    waehrend alle Quelltext-Tests gruen waren.
  Regression **1787/1788 logic + 7/1/5/2 Renders**.
- **v230e EIN WEGGEKLICKTER TAB IST KEIN VERBINDUNGSABBRUCH.**
  Ismets Befund: "Jedesmal wenn ich die Seite im Tab minimiere, ist die Seite
  abgestuerzt." Im echten Browser nachgestellt (Chromium, 390x844, echter
  Server): sobald der Tab in den Hintergrund geht, brechen die laufenden
  Anfragen ab. `pollRender`/`pollAnalyze` unterschieden nicht, WARUM eine
  Anfrage scheiterte - nach 10 Fehlversuchen kam die grosse Karte
  "Connection lost - your render is still running", und der Render-Knopf
  blieb gesperrt. Fuer den Kunden sieht das aus wie ein Absturz, dabei lief
  sein Render die ganze Zeit unveraendert weiter.
  - **Gemessen, alt:** 14 abgebrochene Anfragen in 20 s Hintergrund, Karte
    nach rund 12 s, Knopf gesperrt. **Neu:** 0 Anfragen im Hintergrund,
    keine Karte, Knopf frei.
  - Regel jetzt: im Hintergrund wird **gar nicht erst gefragt**
    (`whenVisible()`), und ein Fehler, der DORT auftritt, zaehlt nicht. Beim
    Zurueckkommen faengt der Fehlerzaehler bei null an - sonst reichen nach
    einer langen Pause wenige echte Aussetzer fuer die Karte. Dieselbe
    Mechanik, die der Chunk-Upload seit v101v benutzt; sie hat jetzt EINE
    Quelle statt zweier Kopien.
  - **Nachweis durch Ausfuehren**, nicht durch Quelltext-Suche: die Sonde
    `web/_dom_probe.mjs` schneidet die echte `pollRender` aus index.html und
    laesst sie gegen ein Mini-DOM mit umgeschaltetem `document.hidden`
    laufen. Vier neue Faelle im Selftest. Zwei Fallen dabei, beide behoben:
    `schneide()` verlor das `async` vor dem Funktionsnamen (das erste
    `await` war dann ein Syntaxfehler), und ein frueherer Abschnitt der
    Sonde ersetzt `globalThis.setTimeout` durch eine Warteschlange - ohne
    die echte Uhr lief der 1.2-s-Takt nie an und der Test mass nichts.
  - **Nicht behoben, weil nicht reproduzierbar:** ein echter Browser-Absturz
    (Renderer-Crash) trat in keinem Lauf auf - weder im Leerlauf noch mit
    laufendem Render, auch nicht nach dreimaligem Einfrieren des Tabs
    (`Page.setWebLifecycleState`). Bleibt das Verhalten nach dem Deploy
    bestehen, ist es ein anderer Fehler und braucht Ismets Geraet + Browser.
- **v230d-sec RUNDE 2 DES AUDITS: FUENF WEITERE LUECKEN, EINE KRITISCH.**
  Sechs Pruefer auf noch nicht abgesuchten Flaechen (Anmeldung, Eigentum,
  Dateipfade, HTML/Panel, Geld, Admin), jeder Befund musste einen
  Widerlegungs-Versuch ueberstehen. 8 Befunde, 5 haben ueberlebt.
  1. **KRITISCH - der Chunk-Upload liess sich herrenlos machen.** Der
     resumable Upload sind DREI Anfragen (init/chunk/finish), geprueft wurde
     nur die erste; `_finalize_upload` bestimmte den Kunden aus dem Cookie
     der GERADE laufenden Anfrage. Wer die Abschluss-Anfrage ohne Cookie
     schickte, bekam einen Job mit `user_id=None`: **nichts abgebucht, kein
     Wasserzeichen** (weder der Demo- noch der Free-Zweig greift ohne
     user_id), kein Flut-Deckel - und abholbar blieb er trotzdem, weil
     `_job_owner_ok` einen Job ohne Eigentuemer immer durchlaesst. Das
     komplette Bezahlprodukt war damit gratis, unbegrenzt und ohne
     Wasserzeichen. Der Eigentuemer steht jetzt an der SITZUNG.
  2. **Die Bremse gegen das Code-Raten sass am falschen Gate.** v203-sec hat
     richtig erkannt, dass ein Alt-Code NAME-1234 nur 10.000 Moeglichkeiten
     hat, und die Bremse an genau EINEN Endpunkt gehaengt. `check_auth` hat
     sieben Aufrufer; ueber `POST /api/templates` liefen 4712 Rateversuche
     ohne ein einziges 429 und der Treffer wurde mit 200 gemeldet. Die
     Bremse sitzt jetzt IN `check_auth` (derselbe Fehlertyp wie v159/v170).
  3. **`/api/resend_verification` war der einzige mailversendende
     Kunden-Endpunkt ohne Bremse** (forgot_password 5/h, support 10/h,
     ticket-reply 20/h). Ein unbestaetigtes Konto konnte das Sende-Kontingent
     leerlaufen lassen - danach bekommt KEIN echter Kunde mehr eine
     Passwort-Reset- oder Kaufbeleg-Mail. Jetzt 5/h je Konto, 10/h je IP.
  4. **Gratis-Guthaben war unbegrenzt farmbar.** Alle Sperren haengen am
     Hash der Adresse, und die wurde nur kleingeschrieben - `a+1@gmail.com`,
     `a+2@gmail.com` und `a.b@gmail.com` landen im SELBEN Postfach, ergaben
     aber verschiedene Hashes. `_email_normal` normalisiert jetzt fuer den
     VERGLEICH (Plus-Tag ueberall, Punkte nur bei Gmail); die
     Anmelde-Identitaet bleibt unveraendert, sonst koennte sich ein
     bestehendes Konto ploetzlich nicht mehr anmelden.
  5. **`/admin/codes` verglich den Schluessel noch mit `str`.**
     `hmac.compare_digest` auf Strings wirft bei einem Header mit Umlaut
     einen TypeError - jeder anonyme Aufruf erzeugte einen 500er, und seit
     v197 schreibt jeder 500er eine Zeile mit vollem Traceback in die
     alerts-Tabelle derselben Datei, in der Konten und Guthaben liegen
     (gemessen 452 KB je 100 Aufrufe, nie aufgeraeumt). v203-sec hat genau
     das in `_admin_ok` behoben - nur dort. Jetzt `_require_admin`, plus
     zwei Deckel an der Tabelle (derselbe Schluessel hoechstens alle 5 Min,
     harte Obergrenze `ALERT_MAX`).
  **Wirksamkeits-Nachweis, und er hat sich gelohnt:** der erste Entwurf des
  Upload-Riegels war Quelltext-gruen und im echten Lauf WIRKUNGSLOS -
  `(_current_user(request) or {}).get('id')` wirft einen AttributeError,
  weil `_current_user` eine `sqlite3.Row` liefert (dieselbe Falle wie v96p).
  Gefunden hat das erst der echte Angriff gegen die echte App. Der Selftest
  faehrt ihn jetzt: Angriff -> 403 und kein herrenloser Job, Gegenprobe ->
  normaler Upload 200 und Guthaben 600 -> 540, Code-Raten -> nach 10
  Versuchen dicht.
  **Verworfen (Gegenprobe hat sie umgestossen):** E-Mail-Enumeration ueber
  die Antwortzeit von forgot_password, `/api/checkout` ohne Rate-Limit,
  Admin-Schluessel ueber `/admin/codes` durchprobierbar.
  Regression **1776/1777 logic + 7/1/5/2 Renders** (der eine Fehlschlag ist
  "GUI startet ohne Fehler" - dieser Container hat fuer python3.11 kein
  tkinter, das Docker-Image schon).
- **v230c-sec SIEBEN BESTAETIGTE LUECKEN GESCHLOSSEN (Runde 1 des Audits).**
  Ismets Frage nach der Cyber-Sicherheit. Ein Pruef-Durchlauf mit
  adversarieller Gegenprobe (jeder Befund musste einen Widerlegungs-Versuch
  ueberstehen) hat sieben ausnutzbare Wege gefunden - **kein Diebstahl
  fremder Kundendaten, sondern Sabotage und Kosten**. Roter Faden: ein
  Riegel, den nur die halbe Nachbarschaft hat.
  1. **Ungeklemmte Regler waren der schwerste Fall.** `_sanitize_overrides`
     klemmte genau fuenf Werte; alles andere lief ungeprueft in die
     Render-Config. `matting_downsample` laesst das KI-Netz das Bild
     GROESSER statt kleiner rechnen (gemessen Faktor 50-90 an Zeit, bis
     5 GB Speicher bei 6 GB Containergrenze), `effects.bg_blur` steuert den
     Gauss-Radius linear (gemessen ~12 s je EINZELBILD bei 100 statt
     0.25 s). Ein Gratis-Konto konnte den EINEN Render-Worker damit
     stundenlang belegen; der Wachhund greift NICHT, weil der Fortschritt
     ja weiterlaeuft. Jetzt gilt: **was keine Grenze in der Tabelle hat,
     kommt gar nicht erst durch** (`_EFFECT_RANGE`/`_CAMERA_RANGE`,
     `_klemm_zahlen`), plus Klemmung in render.py selbst - die Desktop-App
     schreibt dieselbe Datei.
  2. **`fonts.*` war ein freier Dateipfad.** Ein Pfad auf das eigene
     Kundenvideo liess render.py NACH der Transkription mit einem
     unbehandelten Fehler sterben; der Transkript-Zwischenspeicher wird nur
     bei Erfolg geschrieben, also lief bei jedem Versuch ein neuer,
     kostenpflichtiger Whisper-Aufruf. Jetzt geschlossener Satz aus
     `/api/fonts` + Presets. Dasselbe fuer `keywords.include: 123`.
  3. **Der Preisriegel hing am MODUS statt am JOB.** `_render_gebucht(...)
     if (u and mode == 'full')` - mit `mode='analyze'` war "schon gebucht"
     zwangsweise 0. Erst 1080p starten (einmal gebucht), dann denselben Job
     mit analyze + `output.height=2160` aufrufen: der folgende
     'inklusive'-Re-Render lief in 4K zum 1080p-Preis. Exakt der
     v203-sec-Fehlertyp, eine Tuer weiter.
  4. **Erstattet wurde, was `cost_sec` behauptete.** Dieses Feld liess sich
     nach der Reservierung erhoehen - ein fehlgeschlagener Render gab dann
     MEHR zurueck als je gezahlt wurde: aus einem Abbruch liess sich
     Guthaben erzeugen und die Ledger-Invariante brach. `_refund_credits`
     liest den Betrag jetzt aus der Ledger-ZEILE selbst.
  5. **`/api/feedback` hatte weder Bremse noch Eigentumspruefung.** Die
     Dubletten-Sperre haengt am Paar (user_id, jid), und `jid` kam roh aus
     dem Formular - mit erfundenen Nummern ergaben 500 Anfragen 500 Zeilen
     (nachgestellt). Der Sterne-Durchschnitt im Panel liess sich auf 1.0
     ziehen und die einzige geschaeftskritische Datenbank vollschreiben.
     Der Nachbar-Endpunkt `/api/support` hat sein Rate-Limit seit jeher.
     **`_job_owner_ok` reicht hier nicht** - es laesst eine unbekannte jid
     durch (kein Job -> kein Eigentuemer -> True); genau das war der Weg.
  6. **Der Upload hatte gar keine Bremse** (`_rate_limit_ok` deckte nur
     reg/login/goauth/support/admin) und der Flooding-Deckel zaehlte nur,
     was GERADE laeuft. Ein 'pre'-Upload steht danach auf 'vorbereitet' und
     faellt heraus - unbegrenzt Whisper-Aufrufe und bis 300 MB je Upload
     fuer 7 Tage auf derselben Platte wie die Kundendatenbank. Jetzt
     60 Uploads/h je IP plus ein SUMMEN-Deckel (`_vorbereitet_count`, 8).
  7. **Nur die LANGE Bildkante war gedeckelt.** Ein 8x4096-Clip (Datei
     wenige KB, unter jeder Dauer- und Bildratengrenze) wird im
     Standbild-Zwischenspeicher durch `scale=384:-2` auf 384x196608
     HOCHskaliert: gemessen 226 MB je Bild, bis 156 Bilder im Speicher,
     Container hat 6 GB. Jetzt kurze Kante >= 120 px und
     Seitenverhaeltnis <= 6:1.
  Dazu drei Betriebs-Befunde: **die `.env` fehlte in `.dockerignore`**
  (`COPY . /app/` backt Stripe-LIVE-Key, Admin-Key, SMTP-Passwort und
  OpenAI-Key ins Image - ausgerechnet ins Arbeitsverzeichnis des
  Render-Subprozesses, dem v204-sec sie per Allowlist genommen hat);
  **`restore.sh` fiel auf `./web/data` zurueck** und meldete "OK", ohne
  etwas wiederherzustellen (der Container liest das Volume `dve-data`);
  **das Test-Gate haengte das echte Daten-Volume an**, obwohl sein Kommentar
  das Gegenteil behauptet - der Selftest raeumt seine Verzeichnisse per
  rmtree weg, und die einzige Schranke war eine Umgebungsvariable.
  Regression **1761/1762 logic + 7/1/5/2 Renders** (der eine Fehlschlag ist
  "GUI startet ohne Fehler" - dieser Container hat fuer python3.11 kein
  tkinter, das Docker-Image schon).
- **v230b DER FUNKELNDE SAUM AN HAAR UND SCHULTER (Ismets "das Auge glitcht") -
  GEFUNDEN UND BEHOBEN.** Ismet hat die Quelldatei geschickt und den Look
  genannt (Editorial); damit liess sich der Fehler lokal nachstellen. Er ist
  echt und er kommt aus unserer Pipeline - **an derselben Stelle zweimal
  derselbe Denkfehler**:
  - **Ein Weichzeichner, der ueber das GANZE Bild laeuft, mischt an der
    Silhouette dunkles Haar mit heller Wand.** Danach wird die Person mit
    ihrer WEICHEN Matte wieder darueber gepastet - und der Mischwert bleibt
    als heller Saum auf dem Haar stehen. Zwei Fundorte:
    1. `apply_bg_blur` (Bokeh waehrend eines Moments, im Editorial-Preset
       0.6). Gemessen an Ismets Bild + echter RVM-Matte: das 8-px-Band
       INNERHALB der Silhouette war **+8.85 Graustufen zu hell (max +39,
       10934 Pixel ueber +8)**. Nachher: **+0.06, max +7, 0 Pixel**. Die
       Hintergrund-Unschaerfe selbst bleibt gleich stark (Laplace-Varianz
       1.5 vorher wie nachher) - es ist keine Abschwaechung, sondern
       weggelassene Falscharbeit.
    2. Die **Tiefen-Unschaerfe hinter einem `behind`-Text** in
       `composite_frame` (`comp*0.55 + blur(comp)*0.45`). Sie lief ebenfalls
       ueber das ganze Bild, also auch ueber die Person - und sie laeuft
       GENAU in den angesagten "behind me"-Momenten, in denen Ismet den
       Fehler gesehen hat.
  - **Der Fix ist in beiden Faellen derselbe:** der Hintergrund wird
    ALPHA-GEWICHTET weichgezeichnet (`blur(bild*(1-a)) / blur(1-a)`) -
    Personen-Pixel gehen gar nicht erst in den Mittelwert ein. Zusaetzlich
    bleibt die Person voll scharf (`fg = max(blur(a), a)`); vorher reichte
    die weichgezeichnete Vordergrund-Maske ~20 px IN die Person hinein.
  - **Beweisweg (WIRKSAMKEITS-NACHWEIS):** ein Spion auf `composite_frame`
    hat EIN- und AUSGANG bei t=9.583 s auf Platte gelegt. Ergebnis: das Bild
    VOR dem Compositor ist im Kopfbereich **bitgleich zur Quelle (0.00)** -
    der Saum entsteht also im Compositor, nicht beim Dekodieren oder
    Matting. Vorher/Nachher-Streifen an drei Zeitpunkten:
    `scratchpad/auge_fix.png`.
  - **Test-Invariante ist RICHTUNGSFREI:** der weichgezeichnete Hintergrund
    darf nicht davon abhaengen, welche FARBE die Person hat. Ueber die
    Helligkeit zu messen taugt nicht - ob der Saum heller oder dunkler
    wird, haengt am Motiv (auf Ismets Material heller, im Testbild dunkler).
    Gemessen: Hintergrund-Blur **76.7 -> 9.9** von 255, Tiefen-Unschaerfe
    **28.9 -> 5.0**. Beide Tests rufen den echten Pfad auf
    (`composite_frame`, nicht nur die Einzelfunktion).
  - **Ausgeschlossen wurde vorher, einzeln nachgerendert:** Kontaktschatten,
    Farbsaum-Entfernung (`matte_spill`), Umgebungsschatten, Kamera und die
    Person-Occlusion - keiner davon aendert den Saum.
  - Regression **1737/1738 logic + 7/1/5/2 Renders**; der eine Fehlschlag ist
    "GUI startet ohne Fehler" und liegt an diesem Container (python3.11 hat
    hier kein tkinter, das Docker-Image schon).
- **v230a DIE MASKE IST INNEN WIEDER DICHT (Nebenbefund aus Ismets "Auge glitcht").**
  Ismets Screenshot zeigte eine feine senkrechte Linie mitten im Gesicht.
  **Die Linie selbst ist damit NICHT erklaert** - an ihrer Stelle ist die
  Maske nachweislich voellig dicht (Alpha 1.000), dort kann nichts
  durchscheinen. Beim Nachmessen kam aber ein echter Fehler heraus:
  - Die v228b-Gegenprobe waehlt auf Ismets Material Staerke 0.39. Damit ist
    die Maske INNEN nicht mehr ganz undurchsichtig: **2981 Pixel unter 0.98**
    (bei Staerke 1.3 nur 15). Wo die Maske innen durchlaessig ist, scheint
    der Text HINTER der Person als Schleier durch sie hindurch.
  - `matte_loecher_fuellen()` macht den KERN der Silhouette dicht (die um
    14 px geschrumpfte Flaeche) und schliesst umschlossene Krater bis 200 px.
    Gemessen 2981 -> 33 Pixel. **Unangetastet bleiben:** die weiche
    Aussenkante (Haare, Finger - im Test bitgleich 16436 Pixel weicher Saum)
    und echte Durchblicke (die Luecke zwischen Arm und Koerper bleibt offen).
  - **Was noch offen ist:** die Linie in Ismets Bild. Ausgeschlossen sind
    bisher: die Maske an dieser Stelle (dicht), meine beiden Tempo-Eingriffe
    (bitgleich), Nachschaerfung des Bildes (gibt es nicht), Trail/Kontakt-
    schatten/Counter-Ring (aus). Sie wandert MIT dem Gesicht (relative Lage
    zur Nase konstant, waehrend der Kopf sich bewegt). Ismet sagt, im
    Quellvideo ist sie nicht. Zum Bisektieren fehlt mir die Quelldatei.
  - Regression **1735/1735 logic + 7/1/5/2 Renders + GUI_OK**.
- **v230 MEHR SOUND - UND WARUM ES VORHER FAST KEINEN GAB.**
  Ismets Wunsch: "dass mehr sfx benutzt werden". Die Ursache war eine Regel
  aus der Referenz-Messung (v143): Ticks nur in den **ersten 1.6 s einer
  Einstellung**. In dem schnittreichen Vorbild ist das oft - in einem
  Talking-Head-Video gilt der GANZE Clip als eine Einstellung, und nach 1.6 s
  kam kein einziger Ton mehr. Eine Regel, die auf fremdem Material geeicht
  war und auf dem eigenen zur Stummschaltung wurde.
  - Neu: nach dem Schnitt-Fenster darf weiter getickt werden, aber nur mit
    **Mindestabstand** (`effects.sfx_dichte`: sparsam 3.2 s | normal 1.8 s |
    dicht 1.1 s) und etwas leiser - der Tick begleitet den Satz, er taktet
    ihn nicht. Am Schnitt bleibt die volle Dramaturgie (Riser, Whoosh,
    Impact, Boom) unangetastet.
  - **Gemessen** an einem 15.6-s-Clip mit 12 Ankerwoertern: ohne Schnitt
    **3 -> 8 Sounds** (normal), 6 bei sparsam, 13 bei dicht. Mit zwei
    Schnitten 12 -> 15 - dort dominiert weiter der Uebergang.
  - In der Kunden-App als "How much sound design?" waehlbar; der Server
    laesst nur die drei bekannten Werte durch (v186-Regel: ein Wort, das
    niemand geprueft hat, darf nicht in die Engine).
  - **Ein alter Test hat die alte Umsetzung festgenagelt** (`'_t0 - _shot0 >
    1.60' in src`) und waere hier rot geworden. Er prueft jetzt die ZUSAGE
    (dicht am Schnitt, danach Mindestabstand) statt der Codezeile - sonst
    haette er den Fehler geschuetzt statt der Regel (v132-Lehre).
  - Regression **1730/1730 logic + 7/1/5/2 Renders + GUI_OK + SPA-Sonde**.
- **v229 EINE AUSWAHL, DIE NICHTS AUSWAEHLT, GEHOERT AUSGEGRAUT.**
  Ismets Wunsch: laedt jemand ein 720p-Video hoch, sollen die hoeheren
  Aufloesungs-Stufen ausgrauen. Er hat recht, und es war mehr als Kosmetik:
  die Engine skaliert NIE hoch (`H = min(Wunsch, Quelle)`), also bekam der
  Kunde bei 720p immer 720p - egal was angehakt war. Beim 4K-Haken hat er
  fuer dieselbe Datei sogar den doppelten Credit-Satz gezahlt.
  - `updateResChoices()` sperrt jede Stufe oberhalb der kurzen Kante der
    Quelle (`State.srcShort`, im Browser aus der Datei gelesen - kein
    Server-Ruf). Steht die Auswahl auf einer gesperrten Stufe (Preset, alter
    Job), wandert sie auf die hoechste erreichbare und die Kostenanzeige
    rechnet neu.
  - **Ist die Aufloesung unbekannt (0), bleibt alles waehlbar** - lieber eine
    Stufe zu viel anbieten als eine echte verbieten.
  - Laeuft nach dem Datei-Lesen, nach jedem Widget-Neuaufbau und beim
    Betreten der Feineinstellung.
  - **Nachgewiesen durch AUSFUEHREN** (`web/_dom_probe.mjs`, echte Funktion
    gegen ein Mini-DOM) und zusaetzlich im Browser gemessen (Chromium,
    390x844): 720p-Quelle -> 1080p und 4K gesperrt, Auswahl auf 720p;
    1080p-Quelle -> nur 4K gesperrt; 4K-Quelle -> nichts gesperrt.
  - Regression **1726/1726 logic + SPA-Sonde gruen**.
- **v228f DER FARBSAUM RECHNETE UEBER DAS GANZE BILD.**
  Ismets Frage: "kann man die Renderzeit noch reduzieren, ohne an Qualitaet
  zu verlieren?" - Antwort: ja, aber nur noch in kleinen Schritten. Beim
  Profilieren des Captions-Setzens (720x1280, dichte Captions) war
  `kill_spill` mit **36 ms je Bild der teuerste Einzelposten** im Compositor.
  - Der Saum ist ein schmales Band um die Silhouette; ausserhalb ist der
    Faktor exakt 0 und die Formel liefert das Bild unveraendert. Trotzdem
    liefen Weichzeichner, Graustufen-Mittel und Mischung ueber das GANZE Bild
    - dieselbe Leerarbeit wie bei `refine_alpha` in v227.
  - Zuschnitt auf das Band plus 10 Sigma Rand: **exakt pixelgleich** (0.000000
    ueber vier Formen inkl. randberuehrend und bildfuellend), 1.9x bis 15x
    schneller. Mit nur 4 Sigma Rand war EIN Wert um 1/255 daneben - gemessen,
    also nachgebessert statt weggerundet.
  - Erwartet an Ismets Render: Captions setzen 24.9 s -> rund 18 s.
  - **Was NICHT mehr geht, ohne Qualitaet zu kosten:** der Rest der Zeit ist
    Warten auf die KI (rund 100 s von 160). Text-Regie und Text-Fluss haengen
    echt voneinander ab; kuerzer denken lassen war v228d und ist an Ismets
    Urteil gescheitert.
  - Regression **1720/1720 logic + 7/1/5/2 Renders + GUI_OK**.
- **v228e ZURUECKGESTELLT: die KI denkt wieder voll nach.**
  Ismets Befund nach dem ersten Render mit `ai_denken: low`: "Qualitaet ist
  sehr schlecht geworden". Damit ist die Abwaegung entschieden - die Regie
  ist das Herz des Produkts, Renderzeit dagegen zu tauschen war das falsche
  Geschaeft. Standard wieder `aus` (kein `reasoning_effort`, Verhalten wie
  vor v228d). Der Schalter bleibt in der config, damit die Entscheidung
  jederzeit umkehrbar ist; ein Test haelt den Auslieferungs-Standard fest.
  - Die Zeit-Gewinne, die NICHTS mit Qualitaet zu tun haben, bleiben alle:
    Standbilder parallel + nur einmal (v227a), Kantenverfeinerung nur wo die
    Maske ist (v227, pixelgleich), Bild-Regie und Objekt-Anker gleichzeitig
    (v228c, deterministisch zusammengefuehrt).
  - **Lehre:** ein Qualitaets-Regler gehoert dem, der das Ergebnis sieht. Er
    wird angeboten, mit Zahlen, und nach dem ersten Gegenbefund ohne
    Diskussion zurueckgestellt - nicht verteidigt.
  - Regression **1717/1717 logic**.
- **v228d DIE KI DENKT KUERZER (Ismets Entscheidung).**
  Nach v228c bleiben rund 100 s reine KI-Wartezeit, und bei den neuen
  Modellen geht der Loewenanteil davon nicht in die Antwort, sondern ins
  interne Nachdenken. Genau dafuer gibt es `reasoning_effort`.
  - Neu `keywords.ai_denken` in der config: minimal | low | medium | high |
    aus. **Standard 'low'** - Ismets Ansage ("ja go"), nachdem die Abwaegung
    benannt war: spuerbar schneller, dafuer denkt die Regie kuerzer nach.
    'aus' schickt den Parameter gar nicht (Verhalten wie vor v228d), und
    genau das ist der Rueckweg, wenn die Regie schlechter wird.
  - **Das Denkbudget bleibt bei mindestens 2500** (v210-Falle: ein knappes
    Budget wird vom Denken aufgebraucht und die Antwort kommt LEER zurueck).
    Weniger denken heisst MEHR Platz fuer die Antwort - der Riegel wird
    dadurch sicherer, nicht wackliger.
  - Alte Chat-Modelle (gpt-4o) bekommen den Parameter nicht (getestet).
  - **EHRLICHE GRENZE:** wieviel es bringt, steht erst im naechsten
    Timing-Log - hier laeuft kein Schluessel, also ist die Zeitersparnis
    NICHT gemessen. Und ob die Regie darunter leidet, sieht Ismet am
    fertigen Video, nicht ich an einem Test.
  - Regression **1716/1716 logic + 7/1/5/2 Renders + GUI_OK**.
- **v228c 129 VON 191 SEKUNDEN WAREN WARTEN AUF DIE KI.**
  Ismets Timing-Zeile am echten Render: `regie+plaene 133.2s (70%)` - und
  darin `ki-bildregie 39.5s | ki-textregie 37.7s | ki-textfluss 26.1s |
  ki-objektanker 25.3s`. Zusammen **128.6 s = 96 % des Vorbereitungsblocks
  und 67 % der ganzen Renderzeit**. Freistellen (18.3 s) und Captions setzen
  (24.9 s) sind dagegen klein - und die Standbilder, die in v227a noch teuer
  waren, liegen jetzt bei 2.3 s.
  - **Bild-Regie und Objekt-Anker laufen jetzt GLEICHZEITIG** (39.5 + 25.3 s
    -> rund 40 s). Sie sind voneinander unabhaengig: die eine schreibt
    szene/lage, die andere anker. Jeder Thread bekommt eine KOPIE der fx_map,
    danach fuehrt `merge_anker()` deterministisch zusammen - das Ergebnis
    haengt nicht daran, wer zuerst fertig wird (getestet, auch mit
    umgedrehter Reihenfolge). Erwartet: **191 s -> rund 166 s**.
  - Text-Regie und Text-Fluss lassen sich NICHT parallelisieren: der
    Text-Fluss braucht die Blockaufteilung, und die haengt an den Momenten
    aus der Text-Regie. Echte Abhaengigkeit, kein Versaeumnis.
  - **Die Timing-Zeile hat doppelt gezaehlt.** `regie+plaene` umschliesst die
    KI-Aufrufe; die Prozente summierten sich auf 190 %. Der Elternblock zeigt
    jetzt nur noch, was nach Abzug seiner Kinder bleibt.
  - **Log im Panel ist mit einem Klick kopierbar** (ganzer Log oder nur die
    Timing-Zeile) - Ismets Wunsch, und der einzige Weg, wie diese Zahlen
    ueberhaupt bei mir ankommen.
  - Regression **1711/1711 logic + 7/1/5/2 Renders + GUI_OK**.
- **v228b DIE NACHSCHAERFUNG ZERFETZTE DIE MASKE - NICHT DIE DETAILSTUFE.**
  Ismet hat "hochdrehen" entschieden. Die Messung sagt: das waere der falsche
  Hebel gewesen, und das gehoert gesagt statt still geliefert.
  - **Am echten Bild aus seinem Render gemessen** (720x1280, CPU): die ROHE
    Netz-Maske ist sauber - 9 lose Kruemel/Loecher. Nach der Nachschaerfung
    (Guided Filter, Staerke 1.3 bei Qualitaet 'hoch') waren es **285**. Genau
    diese Kante schneidet den Text aus, also sieht man die Fetzen am Wort.
  - **Detailstufe hochdrehen bringt NICHTS:** 0.337 gegen 0.506 gemessen -
    dieselbe Kante, aber 59 -> 108 ms je Bild (+83 % Matting-Zeit). Ein
    Bildvergleich zeigt es ebenso: die rohen Masken beider Stufen sind
    ununterscheidbar sauber, beide zerfallen erst nach der Nachschaerfung.
  - Ursache: der Guided Filter zieht die Maskenkante an die BILDkante. Auf
    echtem Kameramaterial holt das Haare und Finger zurueck; auf weichem,
    rauschfreiem Material (KI-Footage) findet er keine echte Kante mehr und
    rechnet Stoff-Rauschen zu Silhouette um. Der Kontrast-Zug (x2.17) macht
    daraus harte Flecken.
  - Behoben ohne festen Wert: **eine Gegenprobe am ERSTEN Bild** je Render
    (`_refine_pruefen`). Macht die Nachschaerfung die Maske schmutziger, wird
    sie heruntergedreht, notfalls aus. Auf Ismets Material: 1.3 -> 0.39,
    Muell 285 -> 32. Auf sauberem Material bleibt sie unangetastet (getestet).
    Kosten: zwei Filterlaeufe EINMAL je Render, nicht je Bild.
  - Regression **1707/1707 logic + 7/1/5/2 Renders + GUI_OK**.
- **v228a DIE PERSON GEHOERT IN DIE WORTMITTE, NICHT AN SEIN ENDE.**
  Ismets Befund am gestempelten v227a-Render: "das Maskieren hat hier nicht
  gut geklappt" - von "BEHIND ME" war nur "BEHI" lesbar. Am Bild gemessen ist
  es KEIN Maskenfehler: der Sprecher steht bei 0.66 W, der Satz wurde aber
  IMMER auf die BILDMITTE gesetzt (fest `W / 2` im Zeichenpfad). Seine
  Silhouette lag damit auf dem rechten Wortende und frass es am Stueck.
  - Die v191-Lesbarkeitsstufen vergleichen nur BREITEN und sind dafuer blind:
    das Wort war mit 2.4x Schulterbreite breit genug, nur an der falschen
    Stelle. Jetzt steht der Block auf `p['bx']` = Position des Sprechers,
    geklemmt auf den Bildrand.
  - **Steht die Person am Bildrand, reicht Verschieben nicht** - der Block
    liefe aus dem Bild. Dann gilt die v191-Stufe 2 (Kopfhoehe): dort ist die
    Silhouette nur die Kopfbreite statt der Schultern. Die Schwelle ist in
    BUCHSTABEN gerechnet (gut zwei Versalien), nicht in Prozent - was
    herausragt, muss lesbar sein.
  - **Der Riegel musste in VIER Zeichenwege** (Token-Komposition, Einzel-
    Sprite, Buchstaben-Aufbau, Herausschiebe-Effekt). Der haeufigste Fall ist
    die Mehrwort-Komposition ("BEHIND ME" sind zwei Woerter) - sie laeuft gar
    nicht ueber `p['arr']`, ein Riegel nur dort waere toter Code gewesen
    (v219-Lehre, dritter Fall derselben Art).
  - **Beweis am gerenderten Bild** (Sprecher bei 0.78 W, frische Plaene je
    Lauf): Tinte auf der schwaecheren Seite der Silhouette **0 px -> 1701 px**.
    Null heisst woertlich: ein Wortende war komplett weg.
  - Regression **1703/1703 logic + 7/1/5/2 Renders + GUI_OK**.
  - **OFFEN und gemessen:** die Silhouetten-Kante, die den Text beschneidet,
    ist ausgefranst (Treppen von mehreren Pixeln). Die Freistellung rechnet
    auf dem Server intern mit Detailstufe ~0.34; feiner kostet Renderzeit
    (gemessen 1080x1920: 0.25 -> 100 ms, 0.375 -> 172 ms, 0.4 -> 216 ms je
    Bild). Das ist eine Abwaegung, die Ismet trifft.
- **v228 DER PLAYER ZEIGTE NUR EIN DRITTEL DES VIDEOS.**
  Ismets Befund: "wenn ich den Player starte, z.B. in Library, dann sehe ich
  nur die Haelfte von meinem Video". Die Bibliotheks-Kachel ist bewusst 16:9
  mit `object-fit: cover` - das haelt das Raster ruhig. Beim Klick wurde aber
  DERSELBE Rahmen zum Player, und ein 9:16-Video in einem 16:9-Fenster mit
  `cover` zeigt nur einen waagerechten Streifen.
  - **Im Browser gemessen** (Chromium, 390x844, echtes 540x960-Video):
    Rahmen 388x218 -> **32 % des Bildes sichtbar**. Nach dem Fix Rahmen
    370x658, **100 % sichtbar, unverzerrt**.
  - Sobald ein Video laeuft, bekommt der Rahmen die Klasse `playing` und
    damit das Seitenverhaeltnis des Videos (`aspect-ratio: auto`,
    `object-fit: contain`, Deckel 78vh). Das Vorschaubild bleibt
    zugeschnitten - das ist Absicht, kein Fehler.
  - **Zweiter Fund an derselben Stelle:** der Ergebnis-Player nach dem Render
    (`#resultVid`) stand auf `width:100%; max-height:480px` ohne `object-fit`.
    Bei Hochformat klemmt der Browser die HOEHE ab, laesst die Breite stehen -
    und die Voreinstellung `fill` zieht das Bild in die Breite (gemessen
    Rahmen 358x480 gegen Video 540x960, also sichtbar verzerrt). Jetzt
    `contain`.
  - Regression **1700/1700 logic + SPA-Sonde gruen**.
- **v227a DIE ZEIT LAG VOR DEM ERSTEN BILD - UND WAR WARTEZEIT.**
  Ismets Timing-Zeile am echten Render (15 s Video, 154.7 s Gesamtzeit):
  `regie+plaene 99.5s (64%) | matting 21.6s (14%) | compositing 20.2s (13%)`.
  Der teuerste Block ist also NICHT die Bild-fuer-Bild-Arbeit, sondern die
  Vorbereitung - und darin steckt vor allem Warten auf ffmpeg.
  - Gefunden: bis zu 40 Zeige-Proben, 24 Vision-Bilder und 16 Anker-Bilder,
    JEDES ein eigener ffmpeg-Start, streng hintereinander. Sie blockieren sich
    nicht gegenseitig, sie warteten nur der Reihe nach.
  - Und die Vision-Bilder wurden DOPPELT geholt: Bild-Regie und Objekt-Anker
    fragen exakt dieselbe Stelle (`words[i]['start'] + 0.15`).
  - Behoben: Zwischenspeicher (derselbe Frame nur einmal) plus paralleles
    Vorabholen der ersten Probe/aller Vision-Bilder. **Gleiche Argumente ->
    BITGLEICHES Bild**, gemessen ueber 30 Zeitpunkte; hier wird nichts anders
    gemessen, nur nicht mehr nacheinander gewartet. Gemessen 2.5x (BGR) und
    2.7x (Vision-JPEG) auf 4 Kernen, zweiter Abruf 0 ms.
  - Der Timing-Block ist jetzt feiner: `ki-textregie`, `ki-bildregie`,
    `ki-objektanker`, `ki-textfluss`, `vision-frames`, `einzelframes`,
    `zeige-regie`, `raumkarte`. Was von den 99.5 s uebrig bleibt, ist das
    Bauen der Schrift-Sprites - das zeigt der naechste Render.
  - **EHRLICHE GRENZE:** wieviel schneller es bei Ismet wird, haengt an den
    Kernen seines Servers (hier 4) und daran, wieviel der 99.5 s auf die
    Einzelbilder ging. Der naechste Timing-Log sagt es.
  - Regression **1697/1697 logic + 7/1/5/2 Renders + GUI_OK**.
- **v227 RENDERZEIT: ERST MESSEN, DANN SCHNEIDEN.**
  Ismets Befund: "fuer ein 15 Sekunden Video knapp 3 Minuten Renderzeit ist
  schon gottlos". Bis hier gab es KEINE Zeitmessung - nur eine
  Bilder-pro-Sekunde-Zeile, die nicht sagt, welcher Schritt sie kostet. Ohne
  Messung optimieren heisst hier: Qualitaet abschalten. Also erst der
  Messschritt, dann ein Schnitt, der nichts kostet.
  - **Neu: `Timing (total …)` am Ende jedes Renders** - alle Phasen absteigend
    nach Kosten (decode, matting, tiefe, planar-track, objekt-anker, haende,
    compositing, encode-write, gesichter-durchgang, regie+plaene, sfx-bauen,
    audio-mux, modelle-laden) plus `other` fuer alles Ungemessene. Am
    Testrender steht `other` bei 4 % - die Messung ist also nahezu
    vollstaendig und nicht bloss ein Gefuehl.
  - **Gefunden: die Kantenverfeinerung der Freistellung war der teuerste
    Schritt im ganzen Programm.** Gemessen bei 1080x1920 auf CPU:
    `refine_alpha` 151-279 ms je Bild - MEHR als das Matting-Netz selbst
    (216 ms bei Detailstufe 0.4). Ursache: der Guided Filter lief zweimal
    ueber das GANZE Bild, obwohl die Maske typisch ein Drittel davon ausmacht;
    im leeren Rest rechnet er nachweislich Nullen.
  - Behoben durch Zuschnitt auf die Maske plus vier Radien Rand - weiter
    reicht der Filter nicht. **Das Ergebnis ist PIXELGLEICH** (gemessen ueber
    vier Formen inkl. randberuehrend und bildfuellend: max. 0.0000/255
    Abweichung), also keine Qualitaets-Abwaegung, sondern weggelassene
    Leerarbeit. Tempo: Person mittig 1.8x, am Bildrand 3.7x, kleine Maske 8x,
    leere Maske 14x, bildfuellend unveraendert.
  - **EHRLICHE GRENZE:** wieviel das an Ismets 3 Minuten spart, haengt daran,
    auf wievielen Bildern ueberhaupt freigestellt wird (`Matting window: N of
    M frames` im Log). Der naechste Schritt braucht EINEN echten Render mit
    der neuen Timing-Zeile - dann steht schwarz auf weiss, welcher Schritt
    die Zeit frisst, statt dass geraten wird.
  - Regression **1692/1692 logic + 7/1/5/2 Renders + GUI_OK**.
- **v226b EIN AUFKLAPP-BEREICH DARF KEINEN PIXEL-DECKEL HABEN.**
  Ismets Befund am Handy: "Ich sehe die weiteren Menue Optionen nicht". Der
  offene Bereich stand im Stylesheet auf `max-height: 2000px` +
  `overflow: hidden`. Im Browser gemessen (Chromium, 390x844) ist
  "Look & Typography" rund **3500 px** hoch - **1502 px an Einstellungen waren
  abgeschnitten und mit keinem Scrollen erreichbar**, weil der Inhalt gar nicht
  gezeichnet wurde. Genau das zeigt der Screenshot: die Kacheln "From the blur"
  und "Outline only" halb sichtbar, dann endet die Karte.
  - Der Deckel war nur fuer die Aufklapp-Animation da. Offen heisst jetzt
    `max-height: none; overflow: visible`; die Animation setzt einen
    GEMESSENEN Pixelwert (`scrollHeight`) nur fuer ihre Dauer und raeumt ihn
    danach weg - inklusive Sicherheitsnetz, falls `transitionend` ausbleibt
    (Hintergrund-Tab, reduzierte Bewegung).
  - **Ohne JavaScript ist der Bereich vollstaendig sichtbar** (nur ohne
    Animation). Bedienbarkeit darf nie an einem Skript haengen.
  - Nachgewiesen durch AUSFUEHREN: `web/_dom_probe.mjs` ruft die echte
    `accToggle` gegen ein Mini-DOM auf (Deckel = gemessene Hoehe, danach leer,
    auch ohne transitionend) - eine Quelltext-Suche zaehlt hier nicht (v219).
  - Regression **1688/1688 logic**.
- **v226a WER MELDET, SAGT AUCH, WELCHER STAND ER IST.**
  Ismet bekam die Fehlalarm-Mail ein zweites Mal und konnte nicht erkennen, ob
  sie noch von der alten Fassung kam oder ob v225c nicht griff. Die Antwort
  liess sich nur ueber Commit-Zeiten und Video-Metadaten rekonstruieren - fuer
  eine Zeile, die der Absender kostenlos mitliefern kann.
  - Jede Stoerungs-Mail endet jetzt mit `Gemeldet von DouchkoVE <Stand>`.
  - `/api/health` nennt die Version (nicht den Commit). Kein Geheimnis: der
    gleiche Text steht im Kommentar JEDES ausgelieferten Videos. Damit kann
    auch ein externer Pinger sehen, welche Fassung laeuft.
  - **Ein gescheiterter Deploy war STUMM.** `autodeploy.sh` und `update.sh`
    schreiben ihren Befund per sqlite direkt in die alerts-Tabelle - sie
    koennen `_notify_admin` nicht aufrufen, also ging nie eine Mail raus.
    Genau der Fall, in dem gar nichts mehr live geht, war der Fall, von dem
    Ismet nichts erfuhr. Der Watchdog holt es nach: ungemailte
    deploy/deploy_gate-Alarme der letzten 24 h gehen als EINE Mail raus und
    werden danach als gemailt markiert.
  - Regression **1681/1681 logic**.
- **v226 DIE KAMERA DARF DIE ANSAGE NICHT WIDERLEGEN.**
  Ismets Befund am gestempelten v225b-Render: "das 'above me' zuckt etwas zu
  viel und geht runter". Am Video gemessen: die Karte wanderte in 0.29 s um
  109 px NACH UNTEN - bei einer Ansage, die "ueber mir" heisst. Zwei Ursachen,
  beide in dieselbe Richtung.
  - **Kameramodus 'caption' halt sein Versprechen nicht.** Er schiebt das Bild
    um `(by - H/2) * 0.30` auf die Karte zu; bei `by = 0.22 H` sind das 108 px
    nach unten - genau der Messwert. Nur: die Caption wird VOR dem Warp
    gezeichnet und wandert mit. Der Abstand zwischen Kamera und Karte bleibt
    gleich, es rutscht bloss alles zusammen ("Close-up auf die Caption" war
    also nie eins). Bei einer ORTS-Ansage ist das nicht nur wirkungslos,
    sondern falsch: die Karte verlaesst den angesagten Ort. Orts-Ansagen
    bekommen jetzt den reinen Zoom ('punch').
  - **Der Himmel ist die ferne Ebene.** Der Welt-Lock zog die Karte senkrecht
    1:1 mit dem Nahbereich-Schwenk mit (Deckel 0.072 H). Parallaxe geht mit
    der Entfernung gegen null - 1:1 war auch physikalisch falsch. Senkrecht
    steht die Karte jetzt, waagerecht folgt sie gedaempft (0.35).
  - Die Ansage steht als `p['ort_ansage']` AM PLAN: eine Himmel-Ansage laeuft
    je nach Fall durch den ground- ODER den behind-Zweig, und nur der
    ground-Zweig schreibt `p['szene']` - ein Riegel daran haette in der
    Haelfte der Faelle nicht gegriffen (v159-Lehre).
  - **Beweis:** `camera_at` (die Produktionsfunktion) 107.3 px -> 0.0 px
    senkrechter Bildversatz; am gerenderten Bild mit Schwenk nach unten
    40.4 px -> 4.4 px Weg der Tinte. Der erste Testentwurf war GRUEN, ohne
    etwas zu pruefen: die Karte trug 'crash' vom Hoehepunkt-Vorrang, der
    Riegel lief gar nicht. Jetzt besteht die Rotation im Test nur aus
    'caption', und der Riegel muss sich im Log melden.
  - Nicht angefasst: die kurze Standzeit der Karte (~0.55 s) - sie liegt am
    Schnitt 0.4 s nach dem Wort, nicht an einer Regel. Und die
    Gewichts-Animation bleibt; sie pulst den Strich, sie verschiebt nichts.
  - Regression **1676/1676 logic + 7/1/5/2 Renders + GUI_OK**.
- **v225c DER BUILD-STEMPEL KAM IM CONTAINER NIE AN (Fehlalarm-Mail).**
  Ismets Screenshot: "[DouchkoVE] Seit Tagen kein Deploy - laeuft der
  Auto-Deploy noch? / Der laufende Stand ist unbekannt (kein Build-Stempel)".
  Die Mail ist ein FEHLALARM - und beweist gerade dadurch, dass der Deploy
  laeuft: nur v222-Code kann sie ueberhaupt verschicken.
  - Ursache: `update.sh` schrieb den Stempel nach `$DVE_DATA` - auf dem HOST.
    Im Container ist `DVE_DATA=/data` ein Docker-Volume (`dve-data`, kein
    Bind-Mount). Derselbe Name, ein anderer Ort. Der Server hat die Datei nie
    gesehen; damit waren ALLE DREI v222-Ziele tot: Panel "Commit unbekannt",
    Video-Metadaten ohne Commit, taeglich eine Stillstands-Mail.
  - Behoben: der Stempel geht ins BAUVERZEICHNIS, `COPY . /app/` nimmt ihn
    mit, der Container liest ausschliesslich seinen EIGENEN Stand
    (`_build_datei()`: Image zuerst, DVE_DATA nur als Desktop-Rueckfall).
    Nebeneffekt, der wichtiger ist als der Bugfix: ein Stempel neben der
    Datenbank behauptete den neuen Commit schon nach `git pull` - auch wenn
    das Test-Gate danach abbrach und weiter die ALTE Fassung lief. Im Image
    kann er nicht luegen.
  - Der Wachhund unterscheidet jetzt zwei Lagen: messbar alt = echter Befund
    (taeglich erlaubt), kein Stempel = "ich weiss es nicht" (genau EINMAL je
    Programmlauf). Ein grundloser Alarm kostet so viel wie ein verpasster.
  - **Ein Test hatte den Fehler festgeschrieben** (`_al is None or _al > 7`),
    dieselbe Falle wie v132. Neu abgeklopft wird jetzt der ganze Weg:
    update.sh -> Bauverzeichnis -> Dockerfile-COPY -> .dockerignore ->
    Leser-Reihenfolge.
  - **Beweis:** mit `build.json` im Projektverzeichnis meldet ein frisch
    gestarteter Server `DVE_BUILD = v225b ec9cc305
    (claude/caveman-repo-xt386k)` und `warnung: ''` - vorher immer
    "Commit unbekannt". Derselbe Wert laeuft ueber `DVE_JOB_TAG` in die
    Metadaten jedes Videos.
  - Regression **1669/1669 logic + 7/1/5/2 Renders + GUI_OK**.
- **v225b DIE VERKUERZUNG KOMMT AUS DER ENTFERNUNG, NICHT AUS EINEM VORZEICHEN.**
  Ismets Befund am v225-Bild: "die Schrift muss genau in die andere Richtung
  mit dem Winkel". Er hatte recht, und die Ursache war peinlich einfach: die
  Richtung kam aus dem VORZEICHEN eines Sobel-Medians, dessen Orientierung ich
  verwechselt hatte. Ein Vorzeichen ist kein Beleg, sondern eine Behauptung -
  und eine, die man nur am fertigen Bild widerlegen kann, also erst beim Kunden.
  - Die Richtung ist jetzt GEOMETRISCH begruendet: `wall_quad()` bildet je
    Bildspalte den Median der Tiefe, vergleicht die linke mit der rechten
    Haelfte, und die weiter entfernte Seite wird im Bild KUERZER. Perspektive
    statt Rateraten - vertauschen kann sich das nicht mehr.
  - Gefunden beim Messen: die Naehe an den Aussenspalten kam als 0.0 zurueck,
    weil die Gradienten-Maske ueber die Wandkante hinausreicht und dort keine
    Tiefe liegt. Nullwerte fliegen jetzt raus (`> 0.02`, mind. 3 Pixel je
    Spalte, mind. 6 Spalten) - vorher fiel die ganze Messung durch und es gab
    ueberhaupt kein Viereck.
  - **Beweis, beide Richtungen:** linke Wandseite nah -> links 980 px,
    rechts 591 px. Dieselbe Wand gespiegelt -> links 587 px, rechts 980 px.
    Ein Gegentest, der bei vertauschter Richtung fallen MUSS.
  - Die ehrliche Grenze aus v225 bleibt: das Viereck ist immer noch
    rechteckiger als die echte Wand (Oberkante 180 -> 190 statt 120 -> 200),
    weil die Tiefenmaske grob ist. Naechster Schritt bleibt die
    Kantenerkennung im BILD (Hough-Linien).
  - Regression **1660/1660 logic + 7/1/5/2 Renders + GUI_OK**. Getestet mit
    synthetischen Tiefenkarten (das echte Tiefen-Modell laedt hier nicht) -
    am echten Material sieht Ismet es erst nach dem Deploy.
- **v225 IN DIE WANDEBENE PROJIZIEREN, NICHT NUR KIPPEN.**
  Ismets Befund am v224-Bild: "es ist jetzt auf der Wand, aber es hat die
  falschen Winkel". Er hat recht, und ein einzelner Winkel konnte das nie
  leisten: eine Wand im Bild ist ein TRAPEZ mit Fluchtlinien - Oberkante
  faellt, Unterkante steigt, beide laufen auf einen Fluchtpunkt zu.
  `persp_warp(yaw)` verkuerzt nur eine Seite und laesst die Zeilen WAAGERECHT.
  - `wall_quad()` misst die Flaeche als VIERECK (vier Ecken ueber die
    Extremwerte von x+y und x-y - stabiler als approxPolyDP),
    `wall_project()` legt den Satz per Homographie hinein: Fluchtlinien,
    Neigung und Verkuerzung in einem Schritt, ohne Winkel-Basteln.
    Der Warp-Ausgleich aus v224a ist damit ueberholt und entfernt.
  - Das projizierte Sprite liegt in BILDkoordinaten; `cx`/`cy` werden dann
    NICHT mehr gesetzt (das waere eine zweite Verschiebung).
  - **EHRLICHE GRENZE - der Befund ist NICHT vollstaendig behoben:** das aus
    der Tiefenkarte gewonnene Viereck ist zu rechteckig. Am Testfall gemessen
    liefert es die Oberkante 180 -> 190 px, die echte Wandkante laeuft
    120 -> 200 px. Die Maske entsteht auf 96x128 und wird an den Raendern
    beschnitten (dort ueberwiegt der senkrechte Gradient), die Ecken wandern
    dadurch nach innen. Der Schriftzug sitzt sauber, mehrzeilig und mittig auf
    der Flaeche - die FLUCHTLINIEN trifft er noch nicht, er wirkt weiter
    frontal aufgeklebt. Der naechste Schritt ist die Kantenerkennung im BILD
    (Hough-Linien auf den Wandkanten) statt in der groben Tiefenmaske; die
    Fluchtlinien liegen dort exakt.
  - Regression **1657/1657 logic + 7/1/5/2 Renders + GUI_OK**.
- **v224 EIN WANDSCHRIFTZUG WIRD GESETZT, NICHT GESCHRUMPFT.**
  Ismets Befund am v223-Render: "sitzt auf der Wand, sieht aber echt
  unstrukturiert aus, muss eventuell etwas kleiner". Beides kam aus derselben
  Ursache: v223 nahm die FERTIGE, fast bildbreite Zeile und stauchte sie auf
  die Flaeche (bis 45 %) - eine winzige, randfuellende Zeile ohne Luft.
  - `wall_typo()` SETZT den Text fuer die Flaeche neu: mehrzeilig (max drei
    Zeilen), linksbuendig an einer gemeinsamen Achse, auf 72 % der
    Flaechenbreite - der freie Rand ist es, der 'strukturiert' aussieht.
    Gemessen: Versalhoehe 52 px statt 39 px beim Stauchen, Block 66 % der
    Wandbreite statt randfuellend.
  - Platziert wird auf **Augenhoehe** (oberes Drittel der Flaeche), nicht im
    Schwerpunkt - der liegt bei einer bildhohen Wand in der Bildmitte, wo der
    Text ohne Bezug schwebt.
  - **v224b DER WINKEL IST GEDECKELT, WEIL SCHRIFT KEINE TEXTUR IST.** v218
    liess bis 46 Grad zu; am Beweisbild wurde bei -33 Grad aus 'WALL' ein
    'WAI I' - persp_warp staucht die abgewandte Seite, das Antialiasing frisst
    die Strichenden. Jetzt max 20 Grad, geteilt durch die ZEILENZAHL (ein
    dreizeiliger Block vertraegt weniger als eine Zeile). Der Warp-Ausgleich
    ist auf 1.25 gedeckelt - mehr quetscht die Schrift.
  - **v224c MONTIERT WIRD AN DER TINTE, NICHT AN DER SCHRIFTGROESSE.** Ein
    Text-Sprite ist deutlich hoeher als seine Schriftgroesse (Glow-Polster).
    Mit Zeilenabstand `gr*1.12` wurde jede Zeile oben abgeschnitten - von 'ON'
    und 'THE' stand nur die untere Haelfte da. Gemessen wird jetzt die Tinte
    jeder Zeile, ueberlagert per Maximum, und symmetrisch gepolstert (v194:
    einseitig polstern ist ein Positionsfehler).
  - **v224d DIE MESSUNG LAEUFT AN BEIDEN ZEICHENWEGEN.** Sie stand nur im
    ground-Zweig - der greift erst, wenn die Karte im Anzeigefenster ist. Das
    ANKERWORT liegt davor (v221) und wurde deshalb in der alten, bildbreiten
    Fassung an der alten Stelle gezeichnet: neben der Wand statt darauf.
    Jetzt rufen beide Wege dieselbe Aufbereitung (`_wand_aufbereiten`,
    idempotent ueber `_pose_done`).
  - **v224e EIN MOMENT, EIN BILD - auch fuer das Ankerwort.** Es lag auf dem
    Fliesstext ('WALL' auf 'this one'). Es liegt in der Welt und wartet, es
    ist kein zweiter Untertitel: steht ein Fliesstext-Block, weicht der Anker.
    Damit fuellt er genau die Pausen, in denen sonst nichts im Bild ist.
  - **VIER Beweisbilder gebraucht** - jedes hat einen eigenen Fehler gezeigt,
    den keine Zahl gemeldet haette (zerfallene Buchstaben, abgeschnittene
    Zeilen, Anker neben der Wand, Anker auf dem Fliesstext). CLAUDE.md-Lehre
    "bei jeder Aenderung hier einen Frame-Streifen rendern" (v150), bestaetigt.
  - Regression **1651/1651 logic + 7/1/5/2 Renders + GUI_OK**.
- **v223 DER WAND-TEXT MUSS AUF DIE FLAECHE, NICHT NUR IN IHRE EBENE.**
  Ismets Befund am v222-Render (Build-Stempel bestaetigt: `v222`, der Code
  lief also endlich): "der wird gar nicht richtig auf der Wand platziert".
  Die NEIGUNG stimmte da schon (v219), die STELLE nicht.
  - **URSACHE, gemessen:** die Wand steht links und ist im Bild nur rund
    40 % breit; das Wand-Sprite ist fast bildbreit (688-715 px bei 720 px).
    Der Text konnte dort gar nicht "auf" der Wand sein - er lag quer ueber
    Wand UND Person und ragte links aus dem Bild (im Render zu sehen: nur
    'ON' bzw. 'WAL' stand drin). Gesetzt hat ihn die normale
    Platzierungs-Regie: die kennt Gesichter und Bildunruhe, aber keine
    Wandflaeche.
  - **`wall_area()`** misst die zusammenhaengende Flaeche, deren Tiefe sich
    WAAGERECHT aendert und auf der keine Person steht. Der Text wird in ihre
    Mitte gelegt und auf ihre Breite verkleinert (Untergrenze 45 % - unter
    der waere er auf der Wand nicht mehr lesbar). Beweis: Tinte vorher
    0.194..0.806 W, nachher 0.035..0.389 W bei einer Wand von 0..0.45 W;
    Textbreite 255 px auf 278 px Wand.
  - **REIHENFOLGE-FEHLER dabei gefunden:** erst gemessen, dann verschoben -
    also an der ALTEN Stelle (Bildmitte) gemessen, wo die Flaeche frontal
    ist. `wall_pose` gab dort None zurueck und der Text behielt den
    gebackenen Winkel. Jetzt: Flaeche finden, dann DORT messen (yaw -32.9
    statt None).
  - **ZWEITE ANSCHNITT-PRUEFUNG:** der v217-Riegel laeuft in `build_plans` -
    VOR dieser Neuverzerrung. Nach dem Warp sitzt die Tinte anders; ohne
    zweite Pruefung lief genau das wieder aus dem Bild, was v217 abgeriegelt
    hatte.
  - **v223a DER LOG MELDET BEIDE FAELLE.** Ohne Tiefenkarte gibt es keinen
    Wand-Effekt - und genau dieser Fall war zuerst der einzige, der stumm
    blieb (die Meldung stand INNERHALB der Tiefen-Bedingung). Jetzt sagt der
    Job-Log entweder `plane -33 deg, placed on wall area at x=0.21 W` oder
    `no depth map - keeping default angle and position`.
  - Regression **1643/1643 logic + 7/1/5/2 Renders + GUI_OK**.
- **v222 DER SERVER LIEF SEIT v213 - UND NICHTS KONNTE DAS ZEIGEN.**
  Ismets dritter Befund "immer noch nicht an der Wall" war richtig, aber die
  Ursache lag nicht im Code: **alle drei hochgeladenen Renders tragen in
  ihren Metadaten `DouchkoVE v213-ansage`** (ffprobe, format_tags/comment).
  v214 bis v221 sind nie live gegangen. Dazu passt die Messung: die Renders
  sind untereinander pixelgleich (mittlere Differenz < 1).
  - **Warum es niemand sehen konnte:** `DVE_BUILD` war ein FESTER Text im
    Server, seit v213 nicht mitgezogen. Er landet ueber `DVE_JOB_TAG` in den
    Metadaten JEDES Kundenvideos und im Panel - und log dort ueberall.
    Drei Runden wurden damit auf die Frage verschwendet, ob der Code wirkt.
  - **Warum der Deploy schweigt:** `autodeploy.sh` meldet nur einen
    GESCHEITERTEN Versuch. Steht der Server auf einem anderen Branch, sieht
    er dauerhaft "nichts Neues" und schweigt fuer immer - kein Alarm, keine
    Panel-Meldung, nichts. Genau dieses Muster.
  - **FIX:** `update.sh` schreibt Branch, Commit, Betreff und Zeit nach
    `DVE_DATA/build.json` (liegt AUSSERHALB des Images, ueberlebt den
    Neubau). `_build_stempel()` liest es; fehlt die Datei, steht dort
    ehrlich "Commit unbekannt" statt einer erfundenen Nummer. Das Panel
    zeigt Branch und ALTER des laufenden Stands und warnt ab 3 Tagen:
    "wenn seitdem gepusht wurde, greift der Auto-Deploy nicht".
  - **Ein Test schrieb den Fehler fest:** der v130-Test VERLANGTE
    `DVE_BUILD = 'v...'` als Literal - also genau die Konstante, die das
    Problem war. Angepasst. (CLAUDE.md-Lehre "ein Test kann eine Luecke als
    Zusage festschreiben", diesmal am eigenen Bein.)
  - **Der stille Stopp meldet sich jetzt selbst:** der Watchdog prueft alle
    10 Minuten das Alter des laufenden Stands und schreibt ab 7 Tagen (oder
    bei fehlendem Stempel) eine Meldung ins Panel plus Mail - EINE pro Tag
    (Tagesschluessel; der Stunden-Deckel von `_notify_admin` haette 24 am
    Tag ergeben, und eine taegliche Tapete meldet nichts mehr, v194b-Lehre).
    Bisher schrieb nur `autodeploy.sh` bei einem GESCHEITERTEN Versuch -
    steht der Timer, haengt ein Build im flock oder scheitert `git fetch`,
    sah das genauso aus wie "es gibt nichts Neues".
  - **NACHGEPRUEFT, dass es NICHT das Test-Gate ist:** der Selftest unter
    exakten Server-Bedingungen (leeres `models/`, Transkript in der
    `{"words": ...}`-Form aus `deploy_gate.sh`, alle Aussendienste leer,
    eigenes DVE_DATA) laeuft **1634/1634 gruen**. Das Gate blockiert also
    nicht; der Deploy kommt gar nicht erst dort an.
  - **v213 liegt NUR auf `claude/caveman-repo-xt386k`** (`origin/main` und
    `origin/claude/caveman-repo-8ohsfu` stehen beide auf dem
    Upload-Commit `234f33a` und enthalten 27c19fe nicht). Der Server hat
    diesen Branch also bis 27c19fe gezogen und danach aufgehoert - die
    Ursache liegt im Server-Prozess (Timer/flock/git), nicht im Branch und
    nicht im Code. Dieser eine Schritt braucht Ismets Zugang; aus der
    Sandbox gibt es keinen Weg auf die Maschine (kein SSH, douchko.eu ist
    ueber den Proxy gesperrt).
  - Regression **1634/1634 logic + 7/1/5/2 Renders + GUI_OK**.
- **v221 TEXTFLUSS + DAS ORTSWORT LIEGT SCHON DA (Ismets Befund + Idee).**
  - **(a) "Fuehlt sich 0 fluessig an" - gemessen, nicht geraten:** an Ismets
    15-s-Werbespot standen **45 % der Laufzeit KEINE Captions** im Bild,
    einzelne Pausen bis **1.17 s**, waehrend durchgehend gesprochen wird. Das
    Luecken-Netz (v185) gab es, es lief nur bei Dichte 'durchgehend' -
    Textpausen galten in 'akzente' als gewollte Handschrift. Am echten
    Material ist das keine Handschrift, sondern ein Stocken. Netz und
    Atempausen-Verzicht gelten jetzt auch fuer 'akzente'; 'sparsam' bleibt
    bewusst ruhig, DORT ist die Pause der Stil.
  - **(b) DAS NETZ FUELLT KEINE KARTEN-FENSTER (v221b, sonst waere es ein
    Rueckschritt gewesen):** der erste Anlauf legte Netz-Bloecke IN die
    Standzeit einer Keyword-Karte, der Solo-Riegel raeumte daraufhin die
    Karte weg - die Ansagen standen nur noch **0.2 s** im Bild, also genau
    Ismets "eine Millisekunde da", nur schlimmer. Sechs bestehende Tests
    haben das gefangen. Waehrend einer Karte ist das Bild NICHT leer; dort
    fehlt kein Text. Zusaetzlich: bei einer ANSAGE gibt die Karte im
    Solo-Riegel nicht mehr nach - der Fliesstext wartet.
  - **(c) DAS ORTSWORT LIEGT SCHON DA (Ismets Idee):** "es waere ja auch eine
    Option, dass es schon da darauf steht. Beispielsweise das Wort Wall. Und
    das andere baut sich drum herum auf." Genau so: ab dem SATZANFANG liegt
    nur das Ortswort ('WALL') auf der Flaeche - in derselben gemessenen
    Wandebene wie die spaetere Karte -, und sobald der Sprecher es
    ausspricht, steht der ganze Satz da ('ON THE WALL'). `anker_wort()`
    nimmt das letzte inhaltstragende Wort. Vorlauf gedeckelt auf 2.0 s
    (mehr waere ein Titel, kein Anker).
    **Das widerspricht v214 NICHT:** die KARTE erscheint weiter erst zu
    ihrem Wort; frueher da ist nur der Anker, und er verschwindet nicht
    vorher - genau das war der v214-Fehler.
  - **WIRKSAMKEITS-NACHWEIS:** das Ankerwort ist im gerenderten Bild
    gemessen - 799 Pixel im Anker-Fenster, 0 Pixel nach dem Kartenstart
    (Differenz mit/ohne Sprite). Dabei aufgefallen und behoben:
    `composite_frame` ist NICHT zustandsfrei (Anker, Animationsphase und
    Flaechenmessung liegen am Plan), ein Vergleich braucht also FRISCHE
    Plaene pro Lauf - sonst misst man den Zustand des ersten Durchgangs.
  - Der Anker-Durchgang laeuft ueber `plans`, nicht ueber `active`, und
    zieht `p['start']` NICHT vor: sonst haetten Ueberlappungs- und
    Solo-Riegel eine falsche Startzeit (die Verwechslung aus v214/v215).
  - Regression **1624/1624 logic + 7/1/5/2 Renders + GUI_OK**.
- **v220 EIN FUNKLOCH IST KEIN RENDER-FEHLER.** Ismets Screenshot (5G, zwei
  Balken): rote Karte "Render error - Connection lost", darunter der Satz
  "der Render laeuft weiter, schau in die Library oder lade neu". Beides
  zusammen war unehrlich UND unbrauchbar.
  - **Rot plus "Render error" liest sich wie "dein Credit ist weg"** - genau
    die Angst, die ein Bezahlprodukt nicht erzeugen darf. Der Render lief in
    Wahrheit weiter.
  - **Der Rat "lade neu" konnte nicht funktionieren:** `showError` hat den
    laufenden Job aus dem Speicher GELOESCHT (`dve_active_job`), und genau
    daran haengt `resumeActiveJob` beim naechsten Seitenaufruf. Die App hat
    empfohlen, was sie sich selbst gerade unmoeglich gemacht hat.
  - **Der Render-Knopf wurde freigegeben, waehrend der Job noch lief** - ein
    Klick, und der Kunde zahlt denselben Clip zweimal. Bleibt jetzt gesperrt.
  - Neu: eigener weicher Zustand (neutrale Farbe, Titel "Connection lost",
    Job bleibt gespeichert), die Seite versucht es langsamer WEITER statt
    aufzugeben, und sobald das Netz zurueck ist verschwindet die Karte von
    selbst ("Back online - still rendering"). Echte Render-Fehler bleiben
    unveraendert rot.
  - **WIRKSAMKEITS-NACHWEIS (neue Pflicht, siehe CLAUDE.md):** die
    Fehlerbehandlung ist Browser-JavaScript - eine Quelltext-Suche aus dem
    Python-Selftest beweist NICHTS (das war der v218/v219-Fehler). Neu ist
    `web/_dom_probe.mjs`: die Sonde schneidet die echten Funktionen aus
    `index.html`, fuehrt sie gegen ein Mini-DOM AUS und prueft das
    Verhalten - 9 Nachweise, aufgerufen aus dem Selftest (Node 22 liegt im
    Image, der Nachweis laeuft also auch im Deploy-Gate).
  - Regression **1614/1614 logic + 7/1/5/2 Renders + GUI_OK**.
- **v219a LEHREN FESTGENAGELT (Ismets Ansage "lerne aus deinen Fehlern").**
  Drei Fehlschlaege an einem Tag hatten dieselbe Form: der Fix war richtig
  gedacht, gruen getestet und ohne jede Wirkung - Ismet hat dreimal umsonst
  gerendert. Neuer Pflicht-Abschnitt `WIRKSAMKEITS-NACHWEIS` in CLAUDE.md,
  direkt vor dem Deliver-Muster, und dort als Schritt 0 verankert:
  (1) wird die Zeile ERREICHT (jede umschliessende Bedingung mit ihrem Wert
  im Zielfall; `composite_frame`s ground-Zweig hat DREI Zeichenwege, jeder
  mit `continue` - Sprite-Korrekturen gehoeren VOR die Weiche),
  (2) der Test muss die Funktion AUFRUFEN, die im Produkt laeuft (Spion +
  Aufrufzaehler statt Quelltext-Suche),
  (3) der Unterschied muss MESSBAR sein (alt gegen neu am Bild),
  (4) eine Regel gegen Doppelbilder darf Zeiten nur KUERZEN,
  (5) zwei Videos pixelweise vergleichen beantwortet in 10 Sekunden, ob
  ueberhaupt die neue Fassung lief.
  Drei Tests halten die Lehren fest - sie fallen, sobald jemand den
  Abschnitt entfernt oder das Deliver-Muster wieder ohne Schritt 0 fuehrt.
  Regression **1606/1606 logic**.
- **v219 v218 WAR TOTER CODE - die Wandmessung lief nie.** Ismets zweiter
  Render war PIXELGLEICH mit dem ersten (mittlere Differenz < 1 auf allen
  gepruefeten Zeitpunkten). Gefunden mit vier parallelen Pruefstraengen im
  Renderer, jeder Befund adversariell gegengeprueft.
  - **URSACHE:** der v218-Block lag im NICHT-getrackten Zweig von
    `composite_frame`. Bei einem Wand-Plan ist `tracked` aber IMMER wahr:
    `need_track` wird fuer JEDEN ground-Plan gesetzt, mit dem Fenster
    [start-0.35, end+0.6], und das Zeichenfenster [start, end+aus] liegt
    vollstaendig darin - `_hc` ist also in jedem gezeichneten Frame gesetzt.
    Der getrackte Zweig endet mit `continue`. Gemessen mit Spionen auf
    wall_pose: 0 Aufrufe im Normalfall, 0 auch ohne Person, und nur dann 1,
    wenn man H_cum UND H_cum_wall kuenstlich auf None zwingt (kommt im
    Betrieb nur bei `track3d: false` vor). Gezeichnet wurde weiter mit dem
    gebackenen Wechselwinkel (+-6 Grad, Pitch 0.12).
  - **Zweiter Bypass im Talking-Head:** findet `ground_anchor` keine freie
    Wandflaeche - im Hochformat fast immer, das Wand-Sprite ist 688-715 px
    breit bei 720 px Bildbreite -, wird `front_layer=True` gesetzt und noch
    weiter oben gezeichnet, ebenfalls ohne jede Pose. Es gibt in diesem
    Zweig DREI Zeichenwege.
  - **FIX:** die Messung steht jetzt GANZ OBEN im ground-Zweig, VOR der
    Weiche - damit gilt sie fuer alle drei Wege. Derselbe Fehlertyp wie
    v159/v170/v176: ein Riegel am falschen Gate.
  - **WARUM DER SELFTEST ES NICHT GEFUNDEN HAT:** v218 prueft `wall_pose`
    nur als reine Funktion plus eine Quelltext-Suche (`'wall_pose(depth_n'
    in src`). Beides war gruen, waehrend im Bild nichts passierte - genau
    der in CLAUDE.md dokumentierte v193-Fehler. Neu sind vier Tests, die
    `composite_frame` WIRKLICH aufrufen (getrackt, mit Person, mit
    Tiefenkarte) und messen: wall_pose wird aufgerufen, der Winkel landet
    am Plan, das Sprite aendert sich (abgewandte Seite von 2.23 auf 0.52
    verkuerzt), und die Messung steht vor der Weiche.
  - **EHRLICHE GRENZE:** das Tiefen-Modell laesst sich im Container nicht
    laden (huggingface.co gesperrt). Geprueft ist der Pfad mit erzeugten
    Tiefenkarten, nicht an Ismets Wand.
  - Regression **1603/1603 logic + 7/1/5/2 Renders + GUI_OK**.
- **v218 DIE WAND WIRD GEMESSEN, NICHT GERATEN.** Ismets Befund am Render:
  "es sitzt nicht richtig an der Wand". Genau so war es gebaut: fuer
  LIEGENDEN Text misst `ground_pose` die echte Neigung der Flaeche aus der
  Tiefenkarte, fuer WAND-Text gab es das nicht - dort stand ein FESTER
  Winkel, der pro Moment zwischen -6 und +6 Grad wechselte
  (`g_yaw = -6 if side_toggle % 2 == 0 else 6`). Sechs Grad in zufaelliger
  Richtung haben mit der Wand im Bild nichts zu tun; der Text lag davor
  statt darauf.
  - `wall_pose()` misst die WAAGERECHTE Fluchtrichtung aus der Tiefenkarte
    und liefert den Yaw, mit dem `persp_warp` den Text in die Wandebene
    legt. Ein senkrechtes Gefaelle (Boden/Decke) gibt None zurueck - dafuer
    ist `ground_pose` zustaendig -, ebenso eine frontale Wand ohne Flucht.
  - **Der Wand-Text hebt jetzt sein Roh-Sprite auf** (`flat_arr`, bisher nur
    bei `lying`). Ohne das gaebe es nichts neu zu warpen - genau daran ist
    es vorbeigelaufen: die Messung haette man einbauen koennen, sie waere
    ohne das Roh-Sprite wirkungslos geblieben.
  - Beweis an synthetischen Tiefenkarten: Wand flieht nach links -> yaw
    -31.2 Grad (linke Seite kippt weg), nach rechts -> +31.2 Grad, Boden
    und frontale Wand -> None (bisheriger Winkel bleibt).
  - **EHRLICHE GRENZE:** das Tiefen-Modell laesst sich in diesem Container
    nicht laden (huggingface.co gesperrt) - gemessen ist `wall_pose` an
    erzeugten Tiefenkarten, nicht an Ismets Video. Wie es am echten
    Material sitzt, sieht er erst im naechsten Render.
  - Selftest: 7 neue Tests. Regression **1599/1599 logic + 7/1/5/2 Renders
    + GUI_OK**.
- **v217 NUR DER ANSCHNITT-RIEGEL, OHNE DEN DOPPELBILD-FEHLER.**
  v216 hatte zwei Teile; einer war richtig, einer falsch. Der
  Fliesstext-gegen-Fliesstext-Riegel VERLAENGERTE bei Gedraenge den
  wartenden Block - dadurch stand derselbe Satz zweimal gleichzeitig im
  Bild ('EVERYONE'S ... LOOK THE' hinter der Person, 'CAPTIONS LOOK THE'
  unten; Ismets Screenshot). In keinem Zeit-Test faellt das auf, weil sich
  die ZAHLEN sauber nicht ueberschneiden - doppelt war der INHALT.
  **Lehre: eine Regel gegen Doppelbilder darf Zeiten nur KUERZEN, nie
  verlaengern.** Der Riegel ist raus, ein Test haelt ihn draussen.
  Der Anschnitt-Riegel (unten (a)+(c)) bleibt - Ismets Ansage: "achte
  darauf, dass alle captions auch im bild sind".
  Befunde am hochgeladenen Video (15 s, 720x1280, 24 fps).
  - **(a) Text lief aus dem Bild.** 'CAPTIONS LOOK THE' war links UND rechts
    angeschnitten (vorne fehlte das C, hinten das E), 'THIS ONE FLOATS'
    klebte mit beiden Aussenkanten am Rand, 'BEHIND ME' und 'ON THE WALL'
    waren links angeschnitten. Die Breite entsteht auf fuenf Wegen (Karte,
    Editorial-Komposition, Fliesstext, Referenz-Skalierung, Perspektiv-
    Verzerrung), jeder mit eigener Begrenzung - und `S.fit` SCHAETZT die
    Breite aus Einzelzeichen-Kaesten (Leerzeichen zaehlen fast nichts) und
    hat eine harte Untergrenze; passt es danach nicht, prueft es niemand
    nach. Statt fuenf Schaetzungen zu flicken: `fit_into_frame()` misst ganz
    am Ende von `build_plans` EINMAL das fertige Bild und verkleinert bzw.
    verschiebt notfalls. Der GEWOLLTE Randabfall (v152, 'bleed') bleibt
    unangetastet. Meldung im Log: `Frame guard: N moment(s) scaled/moved
    back into frame`.
  - **(b) ZURUECKGEBAUT (v217).** Zwei gleichzeitige Fliesstext-Bloecke
    bleiben damit ein OFFENER Punkt - besser offen als mit einem Doppelbild
    erkauft.
  - **(c) Das Messwerkzeug war blind fuer die gesuchten Faelle.** Der
    v211-Block-Log las 'bx'/'bw' - die setzt kein Keyword-Plan: JEDE Karte
    stand mit `0.000..0.000 W` im Log, also genau die Momente, die im Bild
    angeschnitten waren. Fliesstext-Bloecke meldeten statt ihres Wortlauts
    eine Reihe Leerzeichen (der Text steht nicht im Item, nur der
    Wortindex). Neu: `ink_box()` misst die TINTE aller drei Textformen
    (Karte / Komposition / Fliesstext), `plan_text()` holt den Wortlaut aus
    dem Transkript, und die Zeile nennt das SICHTBARE Zeitfenster
    (`Block 8.25- 9.85s`) - damit ist eine Ueberschneidung im Log ablesbar,
    ohne das Video Frame fuer Frame durchzugehen.
  - **KEIN Bug war:** 'ON THE WALL' wirkt blass, gemessener Kontrast aber
    5.69:1 (Norm 4.5:1) - das ist die gewollte Szenen-Integration, nicht
    zu wenig Kontrast. Nicht angefasst.
  - **EHRLICHE GRENZE:** (a) liess sich mit nachgebautem Transkript NICHT
    ausloesen - Ismets Konfiguration (gelernte Referenz / Look) liegt hier
    nicht vor. Der Riegel ist am Einzeltest belegt (Karte 1.77 W -> 1.01 W,
    Fliesstext 1.06 W -> 1.01 W), nicht an seinem Video. Der reparierte Log
    zeigt beim naechsten Render sofort, welcher Block herauslaeuft.
  - Selftest: 9 neue Tests, v211-Test auf die neue Zusage gezogen.
    Regression **1592/1592 logic + 7/1/5/2 Renders + GUI_OK**.
- **v215 DER SOLO-RIEGEL MASS DIE LESEZEIT AM FALSCHEN PUNKT.**
  Aufgefallen beim Gegenpruefen von v214, gleiche Verwechslung eine Regel
  weiter: der Riegel rechnete die Lesezeit einer Karte ab `p['start']` - dem
  Anfang der WORTGRUPPE. Dort setzen aber nur die kleinen Nebenwoerter ein;
  die grosse Karte kommt erst mit ihrem eigenen Wort (jeder Zeichen-Zweig
  rechnet mit `t - p.get('t0', words[kw_i]['start'])` und ueberspringt
  negative Werte).
  - **BEWEIS:** `CAPTIONS` stand auf dem Papier 1.20-2.00, im Bild aber nur
    1.80-2.00 - **0.20 s statt der im Code garantierten 0.80 s**, genau das
    Blinzeln, das `_KW_MIN` verhindern soll. Nachher: 0.44 s, alle
    Fliesstext-Bloecke unveraendert oder laenger.
  - **Beide Richtungen, nicht nur eine.** Die richtige Messung allein haette
    das Blinzeln nur weitergereicht: die Karte bekam ihre 0.80 s, der
    nachfolgende Fliesstext-Block sank auf 0.27 s. Ein Block traegt die
    Woerter, die GERADE GESPROCHEN werden - deshalb `_FLOW_MIN = 0.55`:
    muesste ein wartender Block darunter, gibt die Karte nach statt ihn
    kaputtzuschieben. Der Block wird dabei nie beschnitten, es gehen keine
    Woerter verloren.
  - `card_t0(p, words)` ist die eine Stelle, die "wann erscheint die Karte
    wirklich" beantwortet - benutzt vom Solo-Riegel, vom Ansage-Riegel (v214)
    und von den Tests.
  - **Selftest robuster statt Test geschoent:** `v101h: Alpha-Kanal traegt
    Text` prueft die Alpha-Ebene nicht mehr bei fest 1.20 s, sondern SUCHT
    den Caption-Moment. Bei Dichte 'akzente' sind Textpausen die gewollte
    Handschrift (das Luecken-Netz laeuft laut Code nur bei 'durchgehend') -
    lag der geratene Zeitpunkt in einer, fiel der Test, obwohl die Ebene in
    Ordnung war. Die Zusage ist jetzt schaerfer: irgendwo traegt die Ebene
    Text auf Transparenz, und NIRGENDS ist sie eine Vollflaeche.
  - Selftest: 5 neue Tests. Regression **1585/1585 logic + 7/1/5/2 Renders
    + GUI_OK**, alles gruen.
- **v214 EINE ANSAGE STEHT NIE VOR IHREM WORT.**
  Ismets Werbespot, an seinem Job-Log belegt: `Block 8.18s | ON THE WALL`,
  gesprochen wird der Satz aber erst ab 9.08 s. Sagt er "sticks on the wall",
  ist die Karte schon wieder weg - im Bild sieht es aus, als fehle sie ganz.
  - **EHRLICHE URSACHE: nicht der Overlap guard.** Der kuerzt nur Enden, er
    zieht nichts nach vorn. Schuld war der 1.5-Sekunden-Vorlauf des
    Szenen-Texts ("LIEGT SCHON DA", `p['start'] = start - 1.5`, seit v55) -
    ein Regie-Effekt fuer Text, den NIEMAND angesagt hat: die Kamera schwenkt
    auf ein Wort, das schon in der Welt liegt. Auf eine ANSAGE angewandt ist
    er die Verneinung der Ansage. Den vorgezogenen Wert schrieb anschliessend
    der Solo-Riegel als `t0` fest, und `t0` IST die Uhr, nach der jeder
    Zeichen-Zweig die Karte einblendet - ab da war sie wirklich sichtbar zu
    frueh.
  - **BEWEIS (dieselbe Wortfolge, vorher/nachher, Sandbox):**
    vorher `ON THE WALL` sichtbar ab 2.25 s bei Wort 3.50 s (**1.25 s zu
    frueh**), und `BEHIND ME` blieb dadurch 0.10 s stehen - ein Blitz;
    nachher stehen alle drei Ansagen exakt auf ihrem Wort (Differenz 0.00)
    mit je 1.2 s Buehne.
  - **Vier Stellen, eine Regel.** `intent` steht jetzt AM PLAN (vorher nur in
    `fx_map`, weshalb keine Zeit-Regel es sehen konnte); der 1.5-s-Vorlauf
    ueberspringt Ansagen; der Sofort-Hook waehlt keine Ansage mehr als
    Frame-1-Karte; das Beat-Grid rastet eine Ansage nur nach HINTEN.
    Dazu `intent_time_floor()` als zentraler Riegel GANZ AM ENDE von
    `build_plans` - dort laufen alle Zeit-Regeln zusammen. Schlaegt er an
    (`Announcement guard: N announced moment(s) moved back`), hat eine Regel
    die Ansage vorgezogen; die Meldung sagt, dass nachzusehen ist.
  - **Der Vorlauf ist NICHT abgeschafft.** Szenen-Text ohne Ansage behaelt
    seine 1.5 s ("liegt schon da") - dafuer gibt es einen eigenen Test.
    Einen Bug beheben, indem man ein Feature entfernt, waere keine Loesung.
  - Lehre (zum vierten Mal derselbe Fehlertyp): eine neue Zeit-Regel muss
    zuerst beantworten, was sie mit einem `intent`-Moment macht.
  - Selftest: 11 neue Tests (Kartenstart >= Wortstart fuer jede Ansage,
    intent am Plan, Mindest-Buehne, Riegel holt zurueck / laesst Spaeteres
    und Nicht-Ansagen und Nutzer-Zeiten in Ruhe, Vorlauf bleibt fuer
    Szenen-Text, Sofort-Hook, Beat-Grid). Regression: **1580/1580 logic**
    + Renders 7/1/4von5/2 + GUI_OK.
  - **Ehrlich offen (Sandbox, NICHT von dieser Aenderung):**
    (a) `render2b` meldet 4/5 - `v101h: Alpha-Kanal traegt Text` prueft die
    Alpha-Ebene bei fest 1.20 s, und im hiesigen synthetischen Transkript ist
    dort eine Caption-Luecke. Vor der Aenderung gemessen: identisch 4/5.
    (b) Dabei aufgefallen und NICHT angefasst (waere eine Timing-Aenderung in
    JEDEM Video, das gehoert Ismet): der Solo-Riegel misst die Lesezeit einer
    Karte ab `p['start']` (Anfang der Wortgruppe) statt ab ihrem Erscheinen.
    Gemessen stand `CAPTIONS` auf dem Papier 1.06-1.86, sichtbar war sie
    1.59-1.86 - 0.27 s statt der im Code garantierten 0.80 s.
    (c) In derselben Passage bekommen 'wie' und 'wir' gar keine Caption
    (Dichte 'akzente'), daher das Loch 1.1-1.5 s.
    (d) Depth-Occlusion lief hier nie mit: huggingface.co ist im Container
    gesperrt, `models/depth.onnx` liess sich nicht laden.
- **v210 DREI KI-SYSTEME LIEFEN GAR NICHT.** Aus Ismets Job-Log:
  `AI flow unavailable (NameError)`, `Vision director unavailable
  (JSONDecodeError)`, `Object anchor: vision skipped`, `Silent score
  unavailable`. Vier Meldungen, zwei Ursachen - und beide fielen brav auf
  eine Notloesung zurueck, weshalb es NIE jemandem auffiel.
  - **Der NameError war ein fehlender Import.** `render.py` importiert
    `requests` in JEDER Funktion lokal; in `ai_flow_direct` fehlte die Zeile.
    Die KI-Textaufteilung ist damit bei JEDEM Kundenrender gestorben.
    Nachgestellt (NameError -> ProxyError, also erreicht sie jetzt das Netz).
  - **Der JSONDecodeError war ein zu kleines DENKBUDGET.** Bei gpt-5/o-Serie
    zaehlen die internen Denk-Tokens in `max_completion_tokens`. Ein knappes
    Budget (200 bei einem der Aufrufe) wird komplett vom Denken verbraucht,
    die Antwort kommt LEER zurueck, und `json.loads('')` wirft
    JSONDecodeError. Nicht die API war kaputt. Untergrenze jetzt 2500, alte
    Chat-Modelle unveraendert.
  - **'above me' ging nicht nach oben** (Log: `Legibility: 'ABOVE ME' raised
    to head height`). Die Lesbarkeits-Stufe zieht ein zu schmales Wort auf
    Kopfhoehe, damit der Koerper es nicht zerschneidet - bei einer
    HIMMEL-Ansage ist das genau das Gegenteil der Ansage. Bei szene
    'himmel' gilt jetzt direkt die Stufe "ueber den Kopf".
  Lehre: **ein Fallback, der jeden Fehler schluckt, macht aus einem
  Programmierfehler ein Feature, das niemand vermisst.** Wer eine neue
  KI-Funktion baut, braucht einen Test, der ohne echten Schluessel prueft,
  dass sie NICHT an einem NameError stirbt.
  Zwei Alt-Tests schrieben die alten Werte fest und wurden mitgezogen.
  Tests: 1558/1558 logic (5 neu) + Renders 7/1/5/2 + GUI.
- **v209a ZWEI TEXTE GLEICHZEITIG IM BILD.** Ismets zweiter Render zeigte
  Woerter doppelt. Ursache am Plan nachgestellt (ohne sein Video): der
  Solo-Riegel vergleicht nur Karte gegen FLIESSTEXT, nie Karte gegen KARTE.
  Drei Orts-Ansagen hintereinander ergeben drei Karten, und eine Karte steht
  laenger als ihr gesprochenes Wort - gemessen lagen 'ON THE WALL'
  (7.20-10.25) und 'BEHIND ME' (7.25-8.75) anderthalb Sekunden uebereinander.
  Zum dritten Mal derselbe Fehlertyp (v159/v170/v176): der Riegel am
  falschen Gate. Aufgeloest wird NICHT durch Kuerzen der ersten Karte
  (0.2 s = Aufblitzen, schlimmer als die Ueberlappung), sondern: die erste
  kuerzt bis hoechstens auf ihre Lesezeit, dann WARTET die zweite und bleibt
  dafuer laenger stehen. Beweis: 7.20-8.00 / 8.40-9.20 / 9.95-12.05, keine
  Ueberschneidung, jede Karte >= 0.80 s.
- **v209 DIE ANSAGEN IM WERBE-VIDEO WURDEN NICHT ERKANNT.** Ismets Befund am
  eigenen Werbespot: "Die captions passen sich nicht an". Am Video gemessen -
  KEINE der drei Ansagen wurde umgesetzt: "this next line goes behind me"
  stand vor der Person, "this one sticks on the wall" schwebte neben der
  Wand, "this one floats above me" stand neben dem Kopf.
  Ursache ist ein Wortschatz-Loch, kein Regie-Fehler: `_self_ref_intent`
  erkennt einen Satz nur dann als Ansage ueber die Captions, wenn ein
  bekanntes Bezugswort darin steht - bis v208 nur caption/subtitle/word/text.
  So redet aber niemand. Ein Mensch sagt "this next LINE" und "this ONE".
  - `line/lines/zeile/zeilen/satz/saetze/one/ones` ergaenzt, dazu die
    Bestimmungswoerter `that/those/my/jene/mein`.
  - Das Bestimmungswort darf jetzt ZWEI Woerter vor dem Nomen stehen -
    "this NEXT line" haette sonst weiter nicht getroffen.
  - Beweis: dasselbe Skript ergibt jetzt 3 Momente (behind / ground+wand+
    stehend / himmel), alle mit `intent`. Vorher: 0.
  - Gegenprobe im Selftest: "The guy behind me was loud", "I put the box on
    the wall yesterday", "One thing above me broke" loesen weiterhin NICHTS
    aus. Ein Wortschatz, der zu weit greift, verschiebt Captions bei jeder
    beilaeufigen Ortsangabe.
  Lehre: ein Wortschatz, der die HAEUFIGSTE Formulierung nicht kennt, ist
  derselbe Fehler wie ein Riegel am falschen Gate (v159/v170/v176) - das
  Feature ist gebaut, getestet und gruen, und trifft im Alltag trotzdem nie.
  Die Tests deckten "The captions are behind me" ab; die Kundensprache nicht.
  OFFEN aus demselben Video (Ursache noch nicht bewiesen): die erste Zeile
  ist 0.8 s lang links und rechts angeschnitten, und in derselben Zeit stehen
  zwei Textelemente gleichzeitig im Bild. Mit den Standard-Einstellungen bei
  720x1280 laesst sich beides NICHT nachstellen (gemessen: Umbruch haelt
  0.069 bis 0.889 W) - dafuer fehlen Look und gelernter Stil des Jobs.
  Tests: 1553/1553 logic (8 neu) + Renders 7/1/5/2 + GUI.
- **v208b Eine Fehlermeldung, die den Fehler auch nennt.** Ismet schickte die
  Panel-Meldung zu `/api/upload/chunk/...`: 60 Zeilen starlette-Innereien und
  NICHT die Zeile, die sagt, was kaputt ist. Grund ist die Bauart eines
  Tracebacks - er faengt beim AEUSSERSTEN Rahmen an (Middleware, Routing) und
  nennt die Ursache erst ganz unten, also genau dort, wo beim Kopieren
  abgeschnitten wird.
  - `_unhandled` schreibt jetzt `URSACHE: <Typ>: <Text>` und die letzten sechs
    Zeilen ZUERST, den vollen Verlauf darunter.
  - Neuer eigener Riegel fuer `ClientDisconnect` (HTTP 499, KEIN Panel-
    Eintrag): ein abgebrochener Upload - Tab zu, Funkloch, App im Hintergrund -
    ist keine Stoerung unseres Servers. Ohne den Riegel meldet jeder davon
    einen "Serverfehler", und echte Stoerungen gehen im Rauschen unter.
  Ehrlich: welcher Fehler bei Ismets Upload wirklich auftrat, ist mit der
  abgeschnittenen Meldung NICHT feststellbar. Der Verbindungsabbruch ist die
  wahrscheinlichste Erklaerung (die Fehlerform passt), aber bewiesen ist das
  erst, wenn die naechste Meldung die Ursache oben stehen hat.
  Tests: 1545/1545 logic (4 neu) + Renders 7/1/5/2 + GUI.
- **v208 TRICHTER: wer kam, und wo springen sie ab.** Ismets Frage: "Kann man
  auch tracken wer auf die webseite etc kam? conversion usw". Bis v207 wusste
  das Panel nur, wie viele Konten es GIBT - nicht, wie viele es gar nicht erst
  geworden sind. Sechs Stufen: Besuch -> App geoeffnet -> Konto -> Upload ->
  fertiges Video -> Kauf, dazu die Herkunft (tiktok/instagram/google/direkt).
  - **Ohne Cookie, ohne gespeicherte IP, ohne fremden Dienst.** Gezaehlt wird
    ueber einen Fingerabdruck `sha256(salz|DATUM|ip|user-agent)[:16]`. Das
    Datum im Salz ist der Kern: der Wert wechselt taeglich, laesst sich also
    nicht ueber Tage verketten und nicht zurueckrechnen. Deshalb braucht es
    kein Einwilligungsbanner - anders als bei Google Analytics, das die Daten
    ausserdem in die USA gibt (Schrems II).
  - **Gezaehlt werden MENSCHEN, nicht Klicks.** Vor der Anmeldung ueber den
    Tages-Fingerabdruck, danach ueber die Konto-Nummer. Wer dreimal die
    Startseite oeffnet, ist ein Besucher.
  - **Kauf und fertiges Video entstehen OHNE Browser** (Stripe-Webhook bzw.
    Render-Worker) - sie haben keine Herkunft. Sie wird ueber das Konto
    nachgeschlagen (die Registrierung kam aus einem Browser mit Verweis).
    Ohne das laege jeder Umsatz unter "direkt" und die Herkunfts-Tabelle
    waere wertlos.
  - **Die Zahl, die zaehlt, ist der Anteil an der Stufe DARUEBER**, nicht der
    an ganz oben. Nur der sagt, WO es klemmt; der Gesamtanteil verschleiert es.
  - Eine Zaehlung scheitert IMMER leise - sie darf nie einen Seitenaufruf
    reissen. Alte Zeilen fallen nach `DVE_FUNNEL_DAYS` (400) raus.
  - Panel: eigene Ansicht **Trichter** unter Umsatz, mit denselben
    Klartext-Saetzen wie die v206-Startseite. Datenschutzseite ergaenzt
    (Zweck, Rotation, Aufbewahrung).
  - Ehrlich: die Zaehlung beginnt mit dem Deploy, rueckwirkend gibt es nichts.
    "direkt" ist bei Instagram/TikTok normal - deren Apps schicken die
    Herkunft oft nicht mit; dafuer sind die `?utm_source=`-Links da.
  Tests: 1541/1541 logic (30 neu) + Renders 7/1/5/2 + GUI.
- **v208a DAS TEST-GATE HIELT EINEN GRUENEN LAUF FUER ROT.** Ismets Meldung
  aus dem Panel: "Commit c3016564 ging NICHT live ... rot, 1511/1511 Tests
  bestanden, FAIL testname xy". Also ALLE Tests bestanden und trotzdem
  blockiert. Ursache: das Gate suchte im Log nach Zeilen, die mit `FAIL`
  beginnen - und genau so eine Zeile erzeugt der v201a-Test selbst: er legt
  absichtlich einen ROTEN Gate-Befund an und zeigt dessen Inhalt als Beleg
  her. Der Beleg war mehrzeilig, also stand 'FAIL testname xy' am
  Zeilenanfang.
  - `check()` macht aus jedem Beleg EINE Zeile. Ein bestandener Test darf
    nicht wie ein gefallener aussehen.
  - Das Gate urteilt nach der BILANZ (`bestanden == geprueft` plus
    Rueckgabewert 0), nicht nach einer Textsuche.
  - Beide Faelle mit vorgetaeuschtem docker nachgestellt: Log MIT
    FAIL-Wort und voller Bilanz -> gruen; Bilanz 1510/1511 bei
    Rueckgabewert 0 -> rot.
  Lehre: ein Waechter, der Text sucht statt das Ergebnis zu lesen, haelt
  irgendwann den Falschen auf - und ein Fehlalarm kostet genauso viel wie
  ein verpasster Fehler, weil dann gar nichts mehr live geht (v198 bis v200
  standen aus demselben Grund wochenlang still).
  Nebenbefund, im Testlauf beobachtet: `_trichter('kauf')` stand MITTEN in
  der offenen Kauf-Transaktion, oeffnete eine zweite Verbindung auf dieselbe
  Datei und lief in "database is locked" - der Kauf wurde also gar nicht
  gezaehlt. Jetzt nach dem Commit, mit kurzem Wiederholversuch. Derselbe
  Fehlertyp wie `_sec_event` in v204.
- **v207a-sec Dem Image fehlte der HTTP-Klient des Testclients.** Zweiter
  Befund des Gates, unmittelbar nach v207: der Selftest fuehrt die
  Sicherheits-Pruefungen ueber echte HTTP-Aufrufe (fastapi.testclient), und
  starlette braucht dafuer httpx bzw. httpx2. In der Entwicklungsumgebung war
  httpx zufaellig als NEBENabhaengigkeit da, im Image nicht - das Gate starb
  an genau der Stelle, an der es die neuen Sicherheitstests fahren wollte.
  `httpx==0.28.1` steht jetzt in requirements.txt (diese Kombination mit
  starlette 1.3.1 laeuft hier nachweislich gruen; ein geratener httpx2-Pin
  haette den Build blockieren koennen). Neuer Test: was der Selftest BRAUCHT,
  muss eine echte Abhaengigkeit sein - sonst laeuft er nur dort, wo jemand
  Glueck hat. Tests: 1511/1511 logic.
- **v207-sec DER SELFTEST GING AN DAS ECHTE STRIPE.** Gefunden vom Test-Gate
  bei seinem ERSTEN erfolgreichen Lauf - genau wofuer es gebaut wurde.
  Im Container ist `STRIPE_SECRET_KEY` aus der .env gesetzt. Der v130-Test
  ruft `admin_refund` mit der erfundenen Sitzung 'rfsess' auf; `_stripe()` war
  damit nicht None, also lief `st.Refund.create(...)` gegen das LIVE-Konto.
  Die erfundene Nummer liess es scheitern ("No such checkout.session") - mit
  einer ECHTEN haette der Selbsttest echtes Geld an einen Kunden erstattet.
  Dieselbe Klasse bei Mail (der Test legt Konten an, im Container ist SMTP
  konfiguriert - es waeren echte Verify-Mails rausgegangen) und bei OpenAI.
  - `selftest.py` kappt jetzt ganz oben, VOR dem Import von `web.server`,
    alle Aussendienste: Stripe, Stripe-Webhook, SMTP, Resend, OpenAI, Google.
    Vor dem Import, weil der Server Teile davon beim Import in
    Modul-Variablen liest. Er sagt auch, was er gekappt hat.
  - `deploy_gate.sh` leert dieselben Werte ein ZWEITES Mal. Ein Testlauf, der
    Geld bewegen kann, darf nicht an einer einzigen Vorsichtsmassnahme haengen.
  - Beweis: mit `STRIPE_SECRET_KEY=sk_live_...` gestartet, nach dem Import ist
    der Wert leer und `_stripe()` gibt None zurueck.
  CLAUDE.md hatte die Regel seit jeher fuer config.yaml und users.db - sie
  galt nur nie fuer Dienste ausser Haus. Jetzt schon.
  Tests: 1510/1510 logic (11 neu) + Renders 7/1/5/2 + GUI.
- **v206 ZAHLEN, DENEN MAN TRAUEN KANN + STARTSEITE.** Ismets Befund: das
  Panel sei "unuebersichtlich und kaum benutzerfreundlich", teilweise stuenden
  dort Infos, bei denen er "keine Ahnung habe, was genau das ist" - und er
  wisse nicht einmal, ob die Einnahmen stimmen.
  - **Sie stimmten nicht.** Der Umsatz war BRUTTO: `purchases` wurde bei einer
    Erstattung nie korrigiert, der Stripe-Hinweis schrieb nur eine Meldung,
    und die §19-Steuerampel (25.000/100.000 EUR) rechnete aus derselben Zahl.
    Im Panel stand also, was Kunden GEZAHLT haben, nicht was geblieben ist.
    Neu: Tabelle `refunds` - eigener Vorgang, weil der Kaufbeleg ein
    Buchungsbeleg ist (GoBD, 10 Jahre) und nicht nachtraeglich verbogen wird.
    Gefuellt aus dem Panel UND aus dem Stripe-Dashboard (`charge.refunded`
    sucht die Session zum payment_intent und traegt sie nach - vorher lief die
    interne Buchhaltung dort still auseinander). Umsatz und Ampel rechnen mit
    netto, das Panel zeigt eingenommen / erstattet / geblieben.
  - **Startseite** als erste Ansicht: vier Fragen, vier grosse Zahlen, jede
    mit einem Satz Klartext. "Verdiene ich Geld?" (30 Tage netto, Trend gegen
    die 30 Tage davor), "Laeuft alles?" (eine Ampel statt sechs Zahlen; rot
    nur bei echter Bedrohung), "Will jemand etwas von mir?" (offene Tickets,
    neue Bewertungen), "Waechst es?" (Konten, neue, Zahler, Renders).
    Alles Technische bleibt unveraendert in den bestehenden Ansichten.
  - Mitgenommen: der Wachhund setzt seinen Herzschlag erst nach 120 s - ohne
    Startwert haette die neue Ampel nach JEDEM Deploy zwei Minuten grundlos
    rot gezeigt. Eine Ampel, die regelmaessig ohne Anlass rot ist, schaut
    nach einer Woche niemand mehr an.
  - Beinahe-Fehler beim Bauen: in der Steuer-Abfrage `_von/_bis` benutzt, die
    Schleifenvariablen heissen `a/b` - das waere live abgestuerzt.
  - Der v142-Test haelt die Liste der gecachten Endpunkte EXAKT fest;
    `admin_start` ist bewusst eingetragen (Admin-Aggregat, 20 s, wird bei
    jedem Schreibzugriff verworfen). Ein Kunden-Kontostand darf nie dazu.
  Tests: 1499/1499 logic (16 neu) + Renders 7/1/5/2 + GUI.
- **v205b-sec DAS GATE SAGT JETZT, WO ES STIRBT.** Ismets Screenshot zeigte
  elf Meldungen "Test-Gate nicht lauffaehig" seit v204: die Deploys gehen
  durch (der v201-Rueckfall wirkt), aber sie gehen UNGEPRUEFT live - und die
  Meldung sagte nicht, warum. "Details auf dem Server: journalctl" ist fuer
  jemanden, der nie ins Terminal geht, dasselbe wie keine Meldung. Das war
  meine Luecke, nicht seine.
  - `deploy_gate.sh` meldet vier STUFEN (Container laeuft / Verzeichnis
    angelegt / Testvideo erzeugt / Selftest gestartet). Der Befund nennt die
    zuletzt erreichte Stufe - oder ausdruecklich "KEINE, der Container ist
    gar nicht angelaufen".
  - `update.sh` haengt den Befund auch im Fall "nicht lauffaehig" an die
    Panel-Meldung (bisher nur bei roten Tests).
  - Das eingebettete Melde-Python wird im Selftest auf Gueltigkeit geprueft -
    ein Syntaxfehler darin faellt sonst erst im Moment der Stoerung auf, also
    genau dann, wenn man die Meldung braucht. (Beim Bauen genau passiert: ein
    fehlendes Pluszeichen haette die Meldung selbst zerlegt.)
  VERMUTUNG, noch nicht bewiesen: v205a koennte das Gate schon nebenbei
  repariert haben. `cap_drop: ALL` nahm auch DAC_OVERRIDE, und /app gehoert
  seit v204 dem Dienst-Nutzer - der Testlauf als root konnte dort also
  moeglicherweise nicht mehr schreiben. `docker compose run` erbt das
  `cap_add` aus v205a. Der naechste Deploy zeigt es; falls nicht, steht der
  Ort jetzt in der Meldung.
  Tests: 1483/1483 logic (4 neu) + Renders 7/1/5/2 + GUI.
- **v205a-sec DIE HAERTUNG HAT SICH SELBST BLOCKIERT + Bauteile festgenagelt.**
  - **Eigentor aus v204, am Live-System aufgefallen:** die neue Panel-Anzeige
    meldete "root - die Haertung ist auf den alten Weg zurueckgefallen".
    Ursache: `cap_drop: ALL` nimmt dem Container ALLE Sonderrechte - darunter
    ausgerechnet CHOWN, SETUID, SETGID, DAC_OVERRIDE und FOWNER, also genau
    die, die der Start braucht, um /data zu uebergeben und auf den kleineren
    Nutzer zu wechseln. Die Haertung hat die Haertung verhindert. Der Rueckfall
    im entrypoint.sh hat gewirkt wie gebaut (Seite lief weiter statt zu
    sterben) - ohne ihn waere douchko.eu beim Deploy unten gewesen.
    Die fuenf Rechte kommen per `cap_add` zurueck. Sie gelten nur fuer die
    Startsekunde: sobald der Prozess die Kennung wechselt, entzieht Linux sie
    automatisch, der laufende Dienst hat also weiterhin KEINE.
  - **Alle 13 Bauteile exakt gepinnt** - und zwar mit den Versionen aus dem
    LAUFENDEN Container (Panel -> System -> Bauteile), nicht geraten:
    opencv 4.11.0.86, Pillow 12.3.0, onnxruntime 1.27.0, mediapipe 0.10.14,
    numpy 1.26.4, protobuf 4.25.9, fastapi 0.139.2, uvicorn 0.51.0,
    python-multipart 0.0.32, requests 2.34.2, PyYAML 6.0.3, bcrypt 5.0.0,
    stripe 15.3.1. Die Testumgebung hier hat voellig andere Versionen
    (numpy 2.4.6 gegen `numpy<2`) - geraten haette nur Deploys blockiert.
  - fastapi/uvicorn/python-multipart wurden im Dockerfile SEPARAT und
    ungepinnt nachgeschoben und standen in requirements.txt gar nicht drin.
    Jetzt eine einzige Liste.
  - Der v135b-Test verlangte woertlich `stripe>=10`; ein exakter Pin erfuellt
    dieselbe Zusage strenger, der Test prueft jetzt die Hauptversion.
  Tests: 1479/1479 logic (8 neu) + Renders 7/1/5/2 + GUI.
- **v205-sec OHNE TERMINAL NACHSEHEN, WAS LAEUFT.** Zwei Fragen, die man
  bisher nur auf der Kommandozeile beantworten konnte - und Ismet geht nicht
  auf die Kommandozeile.
  (1) **Laeuft der Dienst wirklich ohne Generalschluessel?** Die Meldung von
      `entrypoint.sh` geht nach `docker logs` und steht NICHT in server.log -
      die Datei faengt erst an, wenn Python laeuft (mein Hinweis an Ismet war
      insofern falsch). Das Panel zeigt jetzt unter System, als welcher Nutzer
      der Dienst laeuft, und warnt sichtbar, wenn es noch root ist (also die
      Haertung auf den alten Weg zurueckgefallen ist).
  (2) **Welche Fremdbauteile in welcher Version stecken drin?** Aus dem
      LAUFENDEN Prozess gelesen (`importlib.metadata`), nicht aus
      requirements.txt - die sagt bei den meisten ohnehin nur "irgendeine".
      Das ist die Liste, die zum Festnageln der Versionen fehlt.
  Dazu Python- und ffmpeg-Version. Tests: 1475/1475 logic (4 neu).
- **v204-sec HAERTUNG: acht der zehn offenen Audit-Punkte erledigt.** Ismets
  Ansage "mach alles, was du ohne mich kannst".
  - **Sicherheits-Chronik** (`security_events`): wer wann was. Admin-Zugriffe
    werden ZENTRAL in `_require_admin` protokolliert - so kann kein neuer
    Endpunkt es vergessen -, dazu Logins (Erfolg/Fehlschlag/gesperrt),
    Passwortwechsel, Konto-Uebernahme und jedes Umschalten des Betriebs.
    Bewusst OHNE Inhalte: WER WANN WAS, keine Nachrichten, keine Passwoerter.
    Aufbewahrung 180 Tage (`DVE_SECLOG_DAYS`), neue Ansicht **Chronik** im
    Panel mit Filter je Ereignisart.
    Dabei zwei eigene Fehler gefunden und behoben: der Schreiber gab bei
    'database is locked' sofort auf (jetzt drei Versuche), und aus
    `_upsert_google_user` heraus blockierte er sich SELBST - die offene
    Verbindung dieser Funktion hielt die Schreibsperre, also verschwand
    ausgerechnet die Zeile zur Konto-Uebernahme still. Jetzt wird sie im
    `finally` NACH `con.close()` geschrieben (hinter dem try stand sie
    unerreichbar, weil jeder Pfad vorher zurueckkehrt).
  - **NOTAUS** (`/api/admin/betrieb`, drei Stufen): `pausiert` stoppt neue
    Uploads, Renders, Kaeufe und Registrierungen, laesst fertige Videos aber
    abrufbar; `notaus` beendet zusaetzlich ALLE Kundensitzungen. Der Zustand
    liegt als Datei in DATA, nicht im Prozessspeicher - ein Neustart darf
    einen Notaus nicht aufheben. Die Schranke sitzt in der MIDDLEWARE, also
    vor jedem Endpunkt; Health-Check und Admin-Panel bleiben bewusst frei,
    sonst sperrt man sich selbst aus. Am Testfall belegt.
  - **Der Renderer kennt die Geheimnisse nicht mehr.** `env = dict(os.environ)`
    gab dem Subprozess Stripe LIVE, Admin-Key, SMTP-Passwort und die
    Google-Geheimnisse mit. Jetzt eine Allowlist - er bekommt `OPENAI_API_KEY`
    und ein paar harmlose Pfade.
  - **Container-Haertung:** Dienst-Nutzer statt root, dazu
    `no-new-privileges`, `cap_drop: ALL`, `pids_limit`, `mem_limit`.
    Das Umschalten macht `entrypoint.sh` und NICHT ein `USER` im Dockerfile:
    das bestehende /data-Volume gehoert root, ein harter Wechsel haette den
    Server beim naechsten Deploy ausgesperrt. Das Skript uebergibt /data,
    prueft VOR dem Rechte-Abwurf, ob der Nutzer wirklich schreiben kann, und
    faellt bei jedem Zweifel auf den alten Weg zurueck - eine Haertung, die
    im Zweifel die Seite abschaltet, ist schlimmer als die Luecke.
  - **Ressourcen-Grenzen:** Aufloesung (4096 px lange Kante) und Bildrate
    (60 fps) werden jetzt geprueft - bisher war die Dauer die einzige
    inhaltliche Schranke, ein 8K/120fps-Clip kostete denselben Credit und
    blockierte den einen Worker stundenlang. Eine Datei ohne lesbare Dauer
    wird abgelehnt statt als 0-Sekunden-Job durchzulaufen. `upload_chunk`
    prueft die angekuendigte Groesse im Header, BEVOR der Koerper im
    Arbeitsspeicher landet (vorher bis 300 MB je Anfrage, ungeprueft).
  - **Missbrauchs-Erkennung** laeuft stuendlich gegen die Chronik und meldet
    ins Panel (viele Fehl-Logins, Admin-Durchprobieren, Registrierungswellen,
    Render-Wellen). Vorher gab es Zahlen nur auf Nachfrage, im Prozessspeicher,
    nach jedem Deploy weg - es fiel also NIE etwas von selbst auf.
  - **security.txt** (RFC 9116) unter `/.well-known/security.txt`.
  NICHT gemacht und warum: die Sicherung ausser Haus braucht Ismets
  Cloudflare-Schluessel (er legt sie selbst an, nie im Chat). Das Pinnen der
  Abhaengigkeiten braucht ein `pip freeze` AUS DEM CONTAINER - die Versionen
  in der Testumgebung widersprechen requirements.txt (numpy 2.4.6 gegen
  `numpy<2`), geraten zu pinnen wuerde nur Deploys blockieren.
  Tests: 1471/1471 logic (40 neu) + Renders 7/1/5/2 + GUI.
- **v203-sec SICHERHEITS-AUDIT: 30 bestaetigte Befunde, die schweren gefixt.**
  Zwei Workflows mit je einem Gegenpruefer, der jeden Befund WIDERLEGEN sollte
  (16 Roh-Befunde verworfen). Teil 1: die Flaeche seit v193. Teil 2: Identitaet,
  Geld gegen den heutigen Code, Infrastruktur, Lieferkette, Vollstaendigkeit.
  - **CRITICAL, live nachgestellt: `/api/admin/alerts` war ANONYM lesbar und
    beschreibbar.** Der Handler rief `_admin_ok(request)` als nackte Anweisung
    auf - die Funktion gibt nur `bool` zurueck und wirft nicht. Der Riegel
    heisst `_require_admin`. Beweis: GET ohne jeden Header -> HTTP 200 mit der
    kompletten Stoerungstabelle; POST /alerts/read -> alle Meldungen abgehakt.
    Seit v197 schreibt der globale Exception-Handler JEDEN Traceback dorthin,
    dazu stehen Stripe-Session- und Charge-IDs, Job- und Konto-Nummern drin.
    Verschaerfend: die Route war ZWEIMAL registriert; Starlette bedient die
    zuerst registrierte, die mit `_require_admin` gesicherte Variante war toter
    Code - beim Lesen sah der Pfad damit abgesichert aus. Der Fehler stammt aus
    v147, wurde aber durch v197 (Tracebacks in dieselbe Tabelle) erst richtig
    gefaehrlich.
  - **HIGH Konto-Vorbelegung ueber Google.** `_upsert_google_user` verknuepfte
    still ueber die E-Mail, ohne zu pruefen, ob das vorhandene Konto seine
    Adresse je bestaetigt hatte - und das Passwort blieb gueltig. Jeder konnte
    auf eine fremde Adresse registrieren und warten; meldete sich der echte
    Inhaber per Google an, teilten sich beide das Konto (Library, Transkripte,
    Original-Uploads, gekaufte Credits). Jetzt: verknuepfen ja, aber altes
    Passwort entwerten, Konto als bestaetigt markieren, alle Sitzungen beenden.
    Bewusst NICHT loeschen - gehoerte es einem echten Kunden, behaelt er alles.
  - **HIGH 4K zum halben Preis + Guthaben aus der Erstattung.** In
    `render_start` wurden `cfg_overrides`, `uhd` und `cost_sec` gesetzt, BEVOR
    abgerechnet wird - und die Abrechnung ist ueber `_render_charged`
    idempotent, bucht also nicht nach. Zwei Aufrufe genuegten. Und weil
    Erstattungen ueber `_job_cost(j)` laufen, gab ein nachtraeglich erhoehtes
    `cost_sec` bei einem Abbruch mehr zurueck als je gezahlt wurde. Der Preis
    haengt jetzt am Ledger (`_render_gebucht`).
  - **HIGH Demo-Job -> voller Gratis-Render.** 'demo' stand nur im Feld `mode`,
    und `mode` schreibt jeder spaetere Aufruf um. Ueber den Momente-Editor
    wurde daraus ein voller Render: Wasserzeichen weg, 10-Sekunden-Grenze weg,
    nichts bezahlt. Jetzt `j['demo']` an der Anlage, gelesen im Worker, und
    beide Re-Render-Pfade lehnen Demo-Jobs ab.
  - **Dazu gefixt:** Admin-Key ohne Bremse (jetzt 10 Fehlversuche/15 min +
    Panel-Meldung), Passwortwechsel beendete keine anderen Sitzungen (30 Tage
    lang!), `/api/pruefe-code` war ein ungebremstes Rateorakel auf
    4-stellige Codes, die Transkript-Neuanalyse kannte den Flooding-Riegel
    nicht (jeder Lauf loescht den Regie-Cache = neue OpenAI-Kosten),
    Nutzer-Momente gingen UNGEPRUEFT in die Engine (`power` ungeklemmt treibt
    den Gauss-Radius ins Unendliche), Blockzeiten waren nicht gegen die
    Videodauer geklemmt (quadratische Renderzeit), Restore holte widerrufene
    Sitzungen zurueck, ein Admin-Key mit Umlaut ergab einen 500er,
    `logs?teil=hoch-2` ebenso (isdigit() und int() akzeptieren nicht dieselbe
    Menge).
  - **Der wichtigste neue Test** faehrt ALLE `/api/admin/*`-Routen ohne Key ab
    und prueft auf Abweisung, plus eine Pruefung auf doppelt registrierte
    Routen. Eine Quelltext-Suche findet diesen Fehlertyp nicht - beide Namen
    (`_admin_ok`/`_require_admin`) stehen ja im Code.
  - **Zwei Alt-Tests hielten das falsche Verhalten fest** und wurden ehrlich
    nachgezogen: v132 verlangte ausdruecklich "Passwort bleibt gueltig" nach
    der Google-Verknuepfung - also genau die Luecke. v128 prueft den
    Admin-Riegel jetzt in seiner neuen Schreibweise.
  OFFEN (bewusst nicht angefasst, weil Betrieb/Architektur - Ismets Freigabe
  noetig): Container laeuft als root ohne Haertung waehrend er fremde Videos
  parst; Abhaengigkeiten ungepinnt ohne Lockfile; Modelle ohne Pruefsumme von
  `resolve/main`; Offsite-Backup laeuft im Standardbetrieb GAR NICHT
  (haengt an DVE_ALERTS=all, Standard ist 'important') und waere unverschluesselt;
  kein Sicherheits-Ereignisprotokoll; Render-Subprozess erbt alle Geheimnisse;
  keine Grenze fuer Aufloesung/FPS; `upload_chunk` puffert bis 500 MB im RAM;
  kein Notaus; keine Missbrauchs-Erkennung; kein security.txt.
  Tests: 1431/1431 logic (27 neu) + Renders 7/1/5/2 + GUI.
- **v202 SUPPORT RAUS AUS DEM KONTO + BENACHRICHTIGUNG.** Ismets Ansage.
  (1) **Eigene Seite.** Support stand als Block ganz unten unter "Account",
      zwischen Passwort aendern und Konto loeschen. Dort sucht ihn niemand.
      Jetzt eigener Eintrag in der Navigation und eine eigene Seite; der
      Verlauf laedt beim Oeffnen (`showSection`), nicht mehr ueber
      `renderAccount`.
  (2) **Die kleine 1.** Ungelesene Antworten stehen als Zaehler im
      Navigations-Link. Die Zahl kommt als `support_neu` aus `/api/me` -
      bewusst dort und nicht als eigener Endpunkt, weil /api/me ohnehin bei
      jedem Seitenaufruf geholt wird. Beim Oeffnen der Seite faellt sie
      sofort auf 0: ein Zaehler, der stehen bleibt, nachdem man hingeschaut
      hat, ist Muell.
  Beweis ueber echte Aufrufe: frisches Konto 0, eigene Frage 0 (die eigene
  Nachricht ist keine Benachrichtigung), nach der Admin-Antwort 1, nach dem
  Ansehen wieder 0.
  Mitgenommener Beinahe-Fehler: `/api/me` und die REGISTRIERUNG geben
  dieselbe Zeile zurueck. Die Sammelersetzung hat `support_neu` in beide
  geschrieben - in der Registrierung gibt es die Zaehl-Abfrage nicht, das
  waere ein 500er bei JEDER Anmeldung gewesen.
  Tests: 1404/1404 logic (9 neu) + Renders 7/1/5/2 + GUI.
- **v201 DAS TEST-GATE HAT DEN BETRIEB EINGEFROREN.** Ismets Befund: "kann
  immer noch nicht antworten bei Admin Panel". Der Support-Verlauf (v198) war
  gebaut, getestet und gepusht - nur nie live. Ursache ist ein
  Konstruktionsfehler in meinem eigenen v197-Gate: "Tests rot" und "Gate
  laeuft gar nicht" waren derselbe Fall (`if ! bash deploy_gate.sh`). Faellt
  die PRUEFVORRICHTUNG aus - Image startet nicht, ffmpeg fehlt, docker zickt -,
  bricht der Deploy ab, obwohl am Code nie etwas fehlte. v198 war der erste
  Commit, der da durch musste; seitdem stand alles.
  Ein Waechter, der bei eigenem Ausfall die Tuer zumauert, ist kein Waechter.
  - `exit 1` = Tests rot -> Abbruch, alte Version bleibt (unveraendert).
  - `exit 2` = Gate nicht lauffaehig -> Deploy laeuft WEITER, laut, mit
    Eintrag in der alerts-Tabelle ("dieser Stand ist UNGEPRUEFT live").
  - Entschieden wird am ERGEBNIS, nicht nur am Rueckgabewert: fehlt die Zeile
    "<n>/<m> Tests bestanden", ist der Selftest gar nicht bis zum Ende
    gekommen. Rot heisst rot nur mit Bilanz UND `FAIL`-Zeilen.
  Beweis: das Gate laeuft im Selftest gegen einen VORGETAEUSCHTEN docker,
  alle vier Ausgaenge belegt (gruen 0, rot 1, kaputt 2, docker fehlt 2). Eine
  Quelltext-Suche haette den Fehler nie gefunden - v197 hatte fuenf Tests auf
  das Gate, alle gruen, alle am Problem vorbei.
  EHRLICH: dass das Gate auf DEM SERVER scheiterte, ist eine begruendete
  Annahme - ich komme von hier nicht an douchko.eu. Falls es nicht das Gate
  war, steht die Ursache jetzt im Panel unter Alerts.
  **v201a:** der BEFUND gehoert in die Meldung. Das Gate schreibt sein
  Ergebnis nach `.deploy_gate_last.txt`, `autodeploy.sh` haengt die gefallenen
  Tests an den Panel-Eintrag. "Deploy abgebrochen" ohne Grund ist fuer
  jemanden, der nie ins Terminal geht, dasselbe wie keine Meldung.
  BESTAETIGT (Ismets Screenshot): live stand `v197-betrieb` - v198 bis v200
  sind tatsaechlich nie angekommen.
  Tests: 1395/1395 logic (11 neu) + Renders 7/1/5/2 + GUI.
- **v200 SOUND-VARIANTEN: nicht mehr immer derselbe Klick.** Ismets Befund
  ("es muessen mehr Variationen rein"). Ursache gemessen, nicht geraten - und
  sie lag NICHT beim Wahl-Mechanismus: den gibt es seit v96d (`load_variants`,
  Reihum-Wechsel, Pitch-Jitter). Es gab nur **nichts zu waehlen**: jeder der
  14 Slots hatte genau EINE Datei, und **7 der 21 hochgeladenen Sounds waren
  nie benutzt worden** - sie lagen unangetastet in `sfx/incoming`.
  - Aus diesen 7 sind 11 Varianten geschnitten (Einzel-Anschlag per
    Onset-Erkennung, kurze Ausblende gegen Knacken, dieselbe ffmpeg-Kette wie
    `fetch_one`: Stille weg + loudnorm). Pack jetzt **25 Dateien fuer 14
    Slots**, vorher 14.
  - Schwerpunkt `tick` - der laeuft bei fast jeder Wortgruppe und ist damit
    der meistgehoerte Sound im Video. **6 Varianten** (Maus, Tastatur, Handy,
    Kamera-Ausloeser, mechanischer Knopf, Uhr), spektrale Schwerpunkte 2289
    bis 8860 Hz, aehnlichstes Paar 0.66 - also klar unterscheidbar.
    Sechs aufeinanderfolgende Ticks: Aehnlichkeit 0.20 bis 0.66 statt vorher
    praktisch identisch.
  - Zwei Fehler im Wahl-Mechanismus mitgenommen: (1) die Varianten-Suche
    endete bei `_5` - wer eine sechste Datei ablegt, merkt nicht, dass sie
    still ignoriert wird (jetzt bis `_9`); (2) der Zaehler startete in JEDEM
    Video bei 0, also war der erste Tick immer dieselbe Datei und die
    Reihenfolge ueber alle Videos gleich. Jetzt Versatz aus dem INHALT
    (crc32 ueber Transkript + Laenge) - bewusst NICHT `hash()`, das ist pro
    Prozess gesalzen und haette bei jedem Start eine andere Tonspur ergeben.
    Belegt: gleicher Clip zweimal = bitgleiche Spur, anderer Clip = andere.
  - Pitch- und Varianten-Versatz laufen jetzt getrennt, sonst haette Variante
    3 immer denselben Pitch.
  EHRLICH: hier gemessen wurde die spektrale Verschiedenheit, nicht der
  Hoereindruck im fertigen Video - das hoert Ismet.
  Tests: 1384/1384 logic (7 neu) + Renders 7/1/5/2 + GUI.
- **v199 UMRISS WEG.** Ismets Ansage: die Kontur um die Schriften raus.
  `effects.caption_kontur` steht auf 0, auch im Viral-Preset. Gemessen am
  Sprite: dunkle Randpixel 13234 -> 4776, Tinten-Box 674x73 -> 669x68. Was
  uebrig bleibt, ist der SCHLAGSCHATTEN, kein Rest-Saum - belegt ueber den
  Versatz der dunklen Pixel gegen die Glyphe (mit Kontur 1.3 px vertikal, also
  rundherum; ohne 13.9 px nach unten, also versetzt).
  EHRLICH: die Kontur war der Lesbarkeits-Garant aus v181 (ohne sie auf
  grauem Stoff/Beton 1.5-3.1:1 gemessen, WCAG-Norm 4.5:1). Der Ausgleich
  laeuft jetzt allein ueber die Textfarbe - `fit_caption_color` bekommt
  `kontur=False` und darf auf mittelgrauem Grund wieder nach DUNKEL kippen
  (gemessen 5.4:1 statt 3.0:1 mit weissem Text). Heisst: auf hellerem
  Material werden Captions oefter dunkel statt hell. Wenn das stoert, ist es
  eine Zahl (`caption_kontur: 1.0`).
  Drei bestehende Tests massen die Kontur gegen die Datei-Config und waren
  damit ab sofort inhaltslos (beide Faelle identisch) - sie schalten sie
  jetzt fuer ihre Messung selbst ein. Dazu ein Vorschau-Fehler mitgenommen:
  `parseFloat(undefined) ?? 1` ergibt NaN, der Rueckfall griff nie.
  Tests: 1377/1377 logic (4 neu) + Renders 7/1/5/2 + GUI.
- **v198 SUPPORT-VERLAUF: antworten im Panel.** Ein Ticket war bis v197 eine
  Einbahnstrasse: der Kunde schrieb, die Antwort lief per Mail aus Ismets
  Postfach (Reply-To am Benachrichtigungs-Mail). Das funktioniert, aber die
  halbe Unterhaltung stand nirgends - das Panel zeigte ewig die Frage und nie
  die Antwort, niemand konnte sehen, ob ueberhaupt geantwortet wurde, und eine
  Rueckfrage des Kunden kam als NEUES Ticket ohne Bezug zum alten.
  Neue Tabelle `ticket_messages`; `tickets.body` bleibt die erste Nachricht,
  Alt-Tickets bekommen sie beim Start nachgetragen (sonst faengt jeder alte
  Verlauf mit der Antwort an).
  - **Panel:** je Ticket der ganze Verlauf plus Antwortfeld. Die Antwort steht
    sofort im Verlauf UND geht als Mail an den Kunden - er soll nicht in die
    App schauen muessen, um sie zu sehen. Scheitert der Mailversand, sagt das
    Panel es (`gemailt`), statt Erfolg zu melden. Status wird `answered`;
    wartende Tickets stehen als Zaehler in der Seitenleiste.
  - **App (Konto):** der Kunde sieht seine Unterhaltungen und antwortet direkt
    darin. Seine Rueckfrage bleibt IM Ticket und setzt es wieder auf `open` -
    sonst faellt sie aus dem Blick, weil das Panel nach offenen sortiert.
  - DSGVO: `ticket_messages` gehen bei der Kontoloeschung mit; der
    Factory-Reset loescht erst die Kinder, dann die Tickets.
  Beweis: voller Durchlauf ueber echte HTTP-Aufrufe im Selftest - Ticket an,
  Panel sieht 1 Nachricht, Antwort raus, Kunde sieht 2 und 1 ungelesen,
  Rueckfrage rein, Panel sieht 3 im SELBEN Ticket mit Status open. Fremdes
  Ticket 404, leere Antwort 400, ohne Admin-Key 403.
  Tests: 1373/1373 logic (21 neu) + Renders 7/1/5/2 + GUI.
- **v197 BETRIEB: vier Luecken, alle mit demselben Muster.** Es gab jeweils
  einen Mechanismus, aber niemand hatte je geprueft, ob er das tut, was auf
  dem Schild steht.
  (1) **Test-Gate vor dem Deploy.** `autodeploy.sh` zog bis v196 JEDEN
      Commit und startete neu; geprueft wurde danach nur, ob `/api/pricing`
      antwortet - also ob der Server ueberhaupt laeuft. Ein kaputter
      Renderer ging damit live und der Kunde zahlte einen Credit fuer ein
      kaputtes Video. Neu: `deploy_gate.sh` laesst den logic-Selftest im
      NEU GEBAUTEN Image laufen, bevor der laufende Container angefasst
      wird (`--rm --no-deps`, `DVE_DATA=/tmp/gate_data`, kein OpenAI-Key -
      die echte users.db sieht der Test nie). Rot = Abbruch, die alte
      Version laeuft unveraendert weiter. Und ein gescheiterter Deploy
      meldet sich: `git` steht danach schon auf dem neuen Commit, der
      naechste Timer-Lauf saehe "nichts Neues" und schwiege - deshalb
      schreibt `autodeploy.sh` eine Zeile in die alerts-Tabelle des
      laufenden Containers.
  (2) **Restore geprobt - und dabei einen echten Backup-Bug gefunden.**
      `restore.sh` spielt eine Sicherung zurueck: Kandidat PRUEFEN
      (`integrity_check` + Pflichttabellen users/sessions/ledger/purchases)
      BEVOR irgendetwas angefasst wird, App stoppen, jetzigen Stand als
      `vor_restore_<zeit>.db` zur Seite legen (WAL/SHM mit weg), einspielen,
      starten, Health pruefen. **Die Probe deckte auf, dass die Sicherung
      selbst kaputt war:** `_backup_users_db` hatte `if os.path.exists(dest):
      return` ("heute schon gesichert"). Der erste Lauf ist der Start des
      Cleanup-Workers - alles, was danach am selben Tag passierte, stand in
      KEINER Sicherung, und nach einem Neustart um 23:50 enthielt "das
      Backup von heute" praktisch nichts. Beweis aus der Probe: 7 Konten in
      der DB, 0 im Snapshot. Jetzt wird der Tages-Snapshot aufgefrischt,
      solange die DB neuer ist (ueber .tmp + `os.replace`, ein Abbruch darf
      den vorhandenen Snapshot nicht zerstoeren); die Offsite-Mail geht
      weiter nur einmal je Tag raus, der Admin-Knopf sichert mit `force`
      IMMER. Probe danach: 7 -> 3 (simulierter Verlust) -> 7 zurueck.
  (3) **Logs ueberleben den Neustart, Fehler landen im Panel.** Der
      Betriebs-Log lag nur in `docker logs`, und `update.sh` baut das Image
      neu - genau dann will man nachsehen, warum etwas kaputtging. Ein
      `_LogTee` schreibt stdout/stderr zusaetzlich zeilenweise mit
      Zeitstempel nach `DATA/logs/server.log` (5 MB, 5 Generationen,
      `DVE_LOGFILE=0` schaltet ab). Zeilenpuffer noetig, weil `print()`
      je Argument EINZELN `write()` ruft - ohne ihn stuende jedes Argument
      in einer eigenen Zeile. Dazu ein globaler `@app.exception_handler`:
      bis v196 stand in der alerts-Tabelle NUR ein fehlgeschlagener Render;
      ein Absturz in einem Endpunkt ging als Traceback nach stdout und war
      nach dem naechsten Deploy weg - niemand erfuhr je, dass ein Kunde
      einen 500er gesehen hat. Der Kunde bekommt weiterhin keinen
      Traceback. Neue Admin-Ansicht **Logs** (liest nur das Ende, 256 KB).
  (4) **Warteschlange sagt die Wahrheit.** Der Kunde sah `Queued
      (position N)` mit N = qsize, also der GESAMTLAENGE - nicht seinem
      Platz. Bei einer PriorityQueue ist das doppelt falsch: ein zahlendes
      Konto zieht vorbei (Prio 0). `_queue_platz` zaehlt jetzt, wie viele
      Eintraege VOR diesem liegen (1 = als naechstes dran); bei der
      Motion-FIFO die Einfuegereihenfolge, nicht ein Stringvergleich.
      Skalierung bleibt bewusst bei EINEM Worker auf EINER Maschine (ein
      Render zieht CPU und RAM; zwei parallele Jobs machen beide langsamer,
      nicht die Summe schneller) - nur meldet der Watchdog jetzt, WANN es
      eng wird (`DVE_QUEUE_WARN`, Standard 5). Die Worker-Zahl steht als
      `WORKERS` an einer Stelle statt zweimal als os.environ-Ausdruck.
  (5) **v197a: alles im Panel, kein Terminal.** Ismets Ansage. Die
      Sicherungen lagen nur auf der Platte und im Postfach - im Panel stand
      bloss ein Datum, man sah also DASS gesichert wurde, kam aber nicht an
      die Datei und wusste nicht, ob sie lesbar ist. Neu unter System:
      Liste aller Sicherungen mit `quick_check`, Kontenzahl, Groesse, Zeit
      und Download-Knopf. Eine unlesbare Sicherung wird als solche
      markiert - genau das ist die Information, die zaehlt. Der Download
      laeuft ueber fetch+Blob, weil der Admin-Key im HEADER steht; in der
      URL landete er in History und Server-Log.
  (6) **v197b: auch der Restore laeuft im Panel.** Ismet hat die Ansage
      wiederholt - nichts mehr am Terminal. Der Einwand aus v197a war
      richtig, aber die Schlussfolgerung falsch: der Terminal-Weg muss die
      App stoppen, WEIL er die Datei tauscht. Es gibt einen zweiten Weg.
      `_restore_users_db` schreibt die Sicherung ueber die
      SQLite-Online-Backup-API IN die laufende Datenbank; SQLite haelt die
      Sperren selbst, WAL bleibt stimmig, kein Neustart. Am Testfall
      belegt: 7 Konten -> 2 (Verlust) -> 7 zurueck, und eine schon offene
      Verbindung sieht danach ebenfalls 7. Dieselben Sicherungsnetze wie im
      Skript: Kandidat pruefen BEVOR etwas angefasst wird (integrity_check
      + Pflichttabellen, eine Muell-Datei wird abgelehnt), jetzigen Stand
      als `vor_restore_*.db` wegschreiben (der Weg zurueck ist derselbe
      Knopf), einspielen, Schema nachziehen (eine alte Sicherung kennt
      spaeter dazugekommene Tabellen nicht). Tippbestaetigung 'RESTORE' wie
      beim Factory-Reset. Dazu **Upload-Restore** fuer den Ernstfall: ist
      die Platte weg, ist die Kopie im Postfach die einzige, die es noch
      gibt - `.db` oder `.db.gz` hochladen und einspielen. `restore.sh`
      bleibt als Notnagel, wenn die App gar nicht mehr startet.
  Tests: 1352/1352 logic (49 neu) + Renders 7/1/5/2 + GUI.
  EHRLICH: der Test lief hier auf Linux/CPU ohne OpenAI-Key. Die
  Restore-Probe lief echt durch (Verifizieren, Sicherheitskopie,
  Einspielen), Schritt 5 (`docker compose up`) konnte in der Sandbox
  mangels `.env` nicht laufen - den letzten Schritt sieht Ismet erst auf
  dem Server. Das Test-Gate selbst ist auf dem Server ebenfalls noch
  ungelaufen.
- **v196 ANKUENDIGUNGEN + FEEDBACK: zwei echte Luecken geschlossen.**
  (1) **Ankuendigungen.** Bis v195 gab es genau EINEN Weg, Kunden etwas zu
      sagen: eine Mail an alle. Fuer "Wartung heute 20 Uhr" oder "neuer Look
      da" ist das zu laut, kommt zu spaet und laesst sich nicht abbestellen,
      ohne wichtige Post mitzuverlieren.
      NEU: Admin schreibt Titel + Text, waehlt eine Stufe (Info / Warnung /
      Wartung) und optional ein Ablaufdatum in Tagen. Das Banner steht in der
      App, ist wegklickbar - und **weggeklickt wird PRO Ankuendigung
      gemerkt**, nicht global, sonst verpasst der Kunde die naechste.
      Der Endpunkt braucht bewusst KEINE Anmeldung: eine Wartungsmeldung muss
      auch den erreichen, der gerade nicht eingeloggt ist. Ein Ablaufdatum
      gibt es, weil eine Wartungsmeldung, die jemand vergisst abzuschalten,
      schlimmer ist als keine.
  (2) **Feedback.** Bewusst NICHT dasselbe wie ein Support-Ticket: das Ticket
      ist eine Frage mit Antworterwartung, Feedback ist eine Bewertung ohne.
      Die Sterne stehen am FERTIGEN RENDER - nur dort ist die Meinung
      konkret, und nur dort haengt der LOOK dran. Ohne Look-Bezug ist eine
      Note nicht auswertbar; mit ihm beantwortet sie die Frage, die zaehlt:
      welcher Look enttaeuscht. Der Admin sieht Verteilung, Schnitt und
      **Schnitt je Look**, nicht nur eine Liste. Eine Bewertung je Render -
      die zweite ueberschreibt, sonst kippt jeder Durchschnitt, sobald
      jemand den Knopf mehrfach drueckt.
  Navigation: neue Gruppe **Produkt** (Feedback, Announcements), offenes
  Feedback als Zaehler daneben. Konto-Loeschung nimmt das Feedback mit
  (DSGVO); Ankuendigungen sind global und gehoeren niemandem.
  EIGENER FEHLER, ehrlich notiert: das Banner blieb im ersten Anlauf leer.
  Der Code rief `esc()` - den gibt es nur im Admin, in der Kunden-App heisst
  der Helfer `escHtml`. Ein `try/catch` schluckte die Ausnahme, und ein
  leeres Banner sieht aus wie "keine Ankuendigungen". Der Catch loggt jetzt.
  Tests: 20 neue Pruefungen, logic 1303/1303, render1 7/7, render2a 1/1,
  render2b 5/5, render2c 2/2, GUI_OK. Browser Ende zu Ende: Ankuendigung im
  Admin angelegt -> beim Kunden sichtbar -> weggeklickt -> nach Reload weg;
  Bewertung abgeschickt -> im Admin mit Look und Schnitt sichtbar; alle 14
  Ansichten durchgeklickt, keine Konsolenfehler.
- **v195 ADMIN-PANEL: SEITENLEISTE STATT TAB-REIHE.**
  Ismets Vorlage (Screenshot eines fremden Admin-Panels): links eine
  gruppierte Navigation, oben ein Breadcrumb. Uebernommen wurde der AUFBAU,
  nichts sonst - kein Name, keine Farben, keine Inhalte von dort.
  WARUM: zwoelf Ansichten lagen in einer umbrechenden Tab-Zeile. Das war
  schon zu viel, und jede neue Ansicht haette es schlimmer gemacht. Eine
  gruppierte Leiste haelt beliebig viele Punkte aus und sagt nebenbei, was
  zusammengehoert.
  AUFTEILUNG (dieselben zwoelf Ansichten, nur sortiert):
  oben Live / Alerts / Jobs, dann **Umsatz** (Revenue, Credits, Codes),
  **Kunden** (Users, Support, Abuse), **Betrieb** (System, Compliance,
  Recht & Steuern).
  DAZU: Breadcrumb und Seitentitel folgen der Auswahl (auch im Browser-Tab),
  offene Alerts stehen als Zaehler direkt in der Navigation - vorher musste
  man den Tab anklicken, um zu sehen, ob etwas ansteht. Symbole sind SVG,
  keine Emoji.
  MOBIL: die Leiste klappt ein und nach der Wahl wieder zu. Beim Testen fiel
  auf, dass die Seite auf dem Handy QUER lief - ein Grid-Kind hat per
  Voreinstellung min-width:auto und kann nicht schmaler werden als seine
  breiteste Tabelle. Gemessen und behoben: horizontaler Ueberstand 0 px auf
  allen vier geprueften Ansichten bei 390 px Breite.
  `TABS` wird jetzt aus `NAV` abgeleitet - eine Quelle statt zweier Listen,
  die auseinanderlaufen koennen. Der Selftest prueft, dass alle zwoelf
  Ansichten erreichbar bleiben.
  BEWEIS: `adm_live.png` (Desktop), `adm_mob_nav.png` (Handy).
  Tests: 9 neue Pruefungen, logic 1283/1283, render1 7/7, render2a 1/1,
  render2b 5/5, render2c 2/2, GUI_OK. Browser-Smoke: alle zwoelf Ansichten
  durchgeklickt, keine Konsolenfehler.
- **v194c MAIL-DECKEL RICHTIG GEZOGEN (Ismets Einwand: "was ist wenn jemand
  100 Videos macht").**
  Er hatte recht. Der Tages-Deckel aus v194b half nur gegen den Ausbruch,
  nicht gegen den Dauerregen: Videos laufen LAUFEND ab, also haette ein
  Nutzer, der taeglich rendert, jeden Tag eine Mail bekommen - 30 im Monat,
  nur eben gebuendelt. Ein Deckel, der pro Tag zaehlt, deckelt bei taeglicher
  Nutzung nichts.
  ZWEI RIEGEL STATT EINES:
  (a) **Wer ohnehin da ist, bekommt gar keine Erinnerung.** War der Nutzer
      in den letzten 48 h aktiv (Login oder ein Job), faellt die Mail weg -
      er sieht die Library. Die Mail ist ein Rueckkehr-Trigger fuer Leute,
      die es vergessen haben, kein Statusbericht.
  (b) **Rollender Mindestabstand von einer ganzen Aufbewahrungs-Periode**
      (`_mail_abstand_ok`, 7 Tage). Damit gibt es hoechstens EINE Erinnerung
      je Zyklus, egal wie viele Videos ablaufen.
  Dazu ist die Liste gedeckelt: hoechstens zehn Zeilen, danach "and N more",
  und gleiche Dateinamen werden ueber die GANZE Liste zusammengefasst (nicht
  nur nebeneinanderliegende).
  GEMESSEN am Testfall "100 Videos": aktiver Nutzer 0 Mails; inaktiver
  Nutzer 1 Mail mit 7 Zeilen statt 100; am naechsten Tag weitere 100
  ablaufende Videos -> immer noch 0 zusaetzliche Mails.
  Tests: 5 neue Pruefungen, darunter der 100-Video-Fall als Verhaltens-Test.
  logic 1274/1274, render1 7/7, render2a 1/1, render2b 5/5, render2c 2/2,
  GUI_OK.
- **v194b MAIL-FLUT GESTOPPT (Ismets Screenshot: 3 Mails, 2 in derselben
  Minute fuer dieselbe Datei).**
  URSACHE: Der Deckel gegen Doppel-Mails sass am JOB (`expiry_mail` im
  Job-State). Er verhinderte nur die zweite Mail zum SELBEN Job. Wer
  dasselbe Video dreimal gerendert hat, hatte drei Jobs - und bekam drei
  identische Mails. Der Cleanup laeuft stuendlich ueber ALLE Jobs, also war
  das kein Randfall, sondern der Normalfall fuer jeden aktiven Nutzer.
  NEU: `_expiry_sammeln` sammelt je Durchlauf ein, `_expiry_mails` schickt
  danach EINE Mail je Nutzer mit allen ablaufenden Videos darin. Zusaetzlich
  ein Riegel ueber `mail_log`: hoechstens eine Ablauf-Mail pro Nutzer und
  TAG. Mehrere Renders derselben Datei werden in der Liste zu einer Zeile
  mit Anzahl zusammengefasst ("Sequence.mp4 (3 versions)").
  GEPRUEFT: alle anderen Kunden-Mails haben schon einen Deckel oder duerfen
  keinen haben - Willkommen und Verfall-Warnung ueber `mail_log`, der
  Kaufbeleg ist ein Rechnungsdokument und muss pro Kauf rausgehen.
  Tests: 6 neue Pruefungen, darunter ein Verhaltens-Test (drei ablaufende
  Videos -> genau eine Mail, zweiter Durchlauf am selben Tag -> keine).
  logic 1270/1270, render1 7/7, render2a 1/1, render2b 5/5, render2c 2/2,
  GUI_OK.
- **v194a EDITOR-EFFEKTE KOMMEN JETZT WIRKLICH AN.**
  Ismets Befund nach v193: "Die Effekte beim Editor wurden nicht uebernommen,
  ist immer noch dasselbe."
  ER HATTE RECHT, und die v193-Tests haben es NICHT gefunden, weil sie am
  Plan geprueft haben statt am Bild. Der Plan trug die Einstellung korrekt
  (`anim='explosion'`, `_user=True`) - sichtbar war sie trotzdem nicht.
  URSACHE: Ein Fliess-Block baut sich WORT FUER WORT auf (Karaoke-Aufbau,
  v182). Eine Block-Animation dauert 0.2 bis 0.6 s. Bis das dritte Wort
  erscheint, ist sie laengst vorbei - sie lief also nur auf dem ERSTEN Wort
  und dort drei Bilder lang. Am gerenderten Video gemessen (Block
  3.24 bis 4.30 s, 'explosion'): Unterschied zum Render ohne Animation 4.2
  bei 3.28 s, 0.6 bei 3.34 s, ab 3.38 s nur noch 0.3 - praktisch nichts.
  Ein Block, dessen Woerter nacheinander erscheinen, kann nicht explodieren.
  LOESUNG: Wer im Editor eine Animation auf einen BLOCK legt, meint den
  Block. Bei gesetzter Animation steht der ganze Block ab seinem Beginn im
  Bild und bewegt sich als Einheit. Ohne Animation bleibt der Karaoke-Aufbau
  unveraendert - er ist die Handschrift des Produkts, nur eben nicht
  vereinbar mit einer Block-Animation.
  NACHHER gemessen, dieselbe Stelle: 6.7 / 6.1 / 5.2 / 4.2 / 4.3 / 4.3 ueber
  das ganze Block-Fenster statt 4.2 und dann nichts.
  ZWEITE LUECKE, gleich mitgeschlossen: Jobs, die VOR dem Block-Editor
  analysiert wurden, haben keine Blockdatei. Die UI schickte trotzdem eine
  leere Liste mit - serverseitig heisst das "zurueck zur Automatik". Der
  Editor waere bei jedem Alt-Job wirkungslos geblieben, ohne Meldung. Jetzt
  wird ohne geladene Bloecke gar nichts geschickt, und der Nutzer bekommt
  gesagt, dass er das Transkript einmal speichern muss.
  LEHRE fuer die Tests: eine Einstellung am PLAN nachzuweisen reicht nicht.
  Der Beweis ist der Unterschied im gerenderten BILD, ueber das ganze
  Zeitfenster, nicht nur am Anfang.
  BEWEIS: `editor_fix.jpg` (mit/ohne im selben Frame).
  Tests: 6 neue Pruefungen, logic 1264/1264, render1 7/7, render2a 1/1,
  render2b 5/5, render2c 2/2, GUI_OK.
- **v194 ANIMATIONEN GEPRUEFT: 5 von 26 taten nicht, was ihr Name sagt.**
  Ismets Frage: "Tut die Explosion wirklich das, was sie hergibt?"
  Geprueft wurde JEDE der 26 Animationen - Code gelesen UND gemessen.
  Gemessen wurde direkt an `anim_apply()`; das ist eine reine Funktion auf
  einem Sprite, dafuer braucht es kein Video. 21 Animationen sind sauber.
  (1) **kippen war dieselbe Bewegung wie wende.** `_persp3d(arr, ax, ay)`
      dreht mit ax um die QUERachse und mit ay um die HOCHachse. Uebergeben
      wurde der Winkel als ay - also drehte "Tilt (folds forward)" um die
      Hochachse, genau wie "Flip (turns over)". Der eigene Kommentar sagte
      seit je "Tilt um X-Achse", nur das Argument sass falsch. Dazu war die
      Kippung nach 0.10 s vorbei (3 Bilder bei 30 fps) - Ursache war nicht
      die Daempfung, sondern die FREQUENZ: spring() erreicht sein Ziel beim
      ersten Kosinus-Nulldurchgang, x = 1/(2*freq) = 0.238.
      JETZT: Hoehe 0.70x -> 1.00x ueber 0.30 s, wende bleibt Breite 0.56x.
  (2) **schwund loeste sich nie auf.** Ein Alpha-Boden (0.42 + 0.58*keep)
      fror das Wort bei 42 % Deckkraft ein - gemessen noch bei t = 6 s.
      "Fade (dissolves)" wurde blass statt zu verschwinden.
      JETZT: 100 % -> 0 % in 1.1 s.
  (3) **regen stieg von UNTEN auf.** Die Leinwand wuchs nur nach unten, der
      Streifen landete am oberen Rand - und weil der Zeichenpfad mittig
      setzt, sass der fertige Text dauerhaft 53 px zu hoch (30 % der
      Worthoehe). "Rain (falls from above)" lief also in die Gegenrichtung.
      JETZT: startet 104 px darueber, landet exakt auf der Sollposition.
  (4) **rutsche kam von LINKS und blieb 92 px daneben stehen** (23 % der
      Wortbreite) - derselbe einseitige Polster-Fehler. Das verfehlt die
      berechnete Bildseite (v168) und den Plattform-Korridor (v187).
      JETZT: kommt von rechts, landet exakt auf der Sollposition.
      explosion und magnet polstern seit je symmetrisch und waren richtig -
      das ist die Bauweise, die beide jetzt uebernehmen.
  (5) **gewicht pumpte nicht, es verdickte einmal.** Der Morphologie-Kernel
      war eine ungerade GANZzahl: die ganze Bass-Spanne 0.0 bis 0.8 ergab
      denselben Kernel. Gemessen: Strichbreite 1.177x konstant, erst bei
      Bass 1.0 ein Sprung. Ein Regler, der ueber 80 % seines Bereichs nichts
      tut, ist kein Regler. JETZT: zwischen zwei Kernelgroessen gemischt,
      monoton steigend.
      EHRLICH: das ist der FALLBACK-Weg. Wo eine echte Variable-Font-Achse
      vorliegt (viral/creator/elegant/cinematic), schwingt der Strich rund
      1.9x; der Fallback schafft rund 1.2x. Die anderen fuenf Looks haben
      keinen variablen Schnitt - das ist eine Font-Frage, keine Code-Frage,
      und Ismets Entscheidung.
  (6) **wackel hatte kein Squash & Stretch.** "Cartoon bounce" ohne die
      erste der 12 Disney-Regeln war ein gleichfoermiger 1.5-%-Skalen-Puls.
      JETZT: gegenlaeufig und an den Umkehrpunkt gekoppelt - unten 5 %
      breiter und 5.5 % flacher, oben 5 % schmaler und 4 % hoeher,
      volumenerhaltend.
  EIGENER MESSFEHLER, ehrlich notiert: im ersten Durchgang stand `schub`
  bei 0.00 % Aenderung da und sah tot aus. Ursache war MEINE Messung - die
  Animation haengt am Audio-Onset, und ich hatte einen konstanten Wert
  eingespeist. Mit einem sprech-aehnlichen Signal bewegt sie 9.9 px und
  8.4 % Skalierung. Neun Animationen sind audio-getrieben; wer sie misst,
  muss ein echtes Signal anlegen. Derselbe Fehler steckte in meinem ersten
  Test-Fingerabdruck: er nahm die Alpha-SUMME, und eine Welle verschiebt
  Tinte nur seitlich - `welle` wurde faelschlich als tot gemeldet, obwohl
  sie 8 bis 14 px und 25 % der Tinte bewegt.
  OFFEN, bewusst nicht angefasst: sturz endet 53 px tiefer und anstieg
  43 px hoeher als die berechnete Stelle. Der Code sagt ausdruecklich, dass
  sie fallen bzw. steigen und DORT stehen bleiben - das ist Absicht, aber
  es umgeht die Platzierungs-Regie. Ismet entscheidet, ob sie zurueckfedern
  sollen.
  BEWEIS: `v194_beweis.jpg` (alt gegen neu, 5 Animationen im Streifen).
  Tests: 15 neue Pruefungen, logic 1259/1259, render1 7/7, render2a 1/1,
  render2b 5/5, render2c 2/2, GUI_OK.
- **v193 BLOCK-EDITOR: Captions sind jetzt wirklich editierbar.**
  Ismets Ansage: "Wie in Premiere Pro editierbar. Simple und uebersichtlich.
  Ein Editor statt Momente. Voll einstellbar, und diese Einstellungen
  MUESSEN auch uebernommen werden."
  AUSGANGSLAGE (am Code belegt, nicht geschaetzt): es gab ZWEI Editoren und
  beide konnten das nicht. "Fix transcript" korrigierte nur Woerter, "Edit
  moments" nur Keyword-Momente mit acht Dropdowns. **Fliesswort-Bloecke
  waren ueberhaupt nicht editierbar** - brach ein Umbruch schlecht, konnte
  der Kunde nur globale Regler verstellen und erneut zahlen.
  NEU: eine Liste, eine Zeile = ein Block, so wie er im Bild steht. Text
  tippen, an der Schreibmarke teilen, zwei Zeilen zusammenlegen, Haken raus
  = faellt weg. "Style" klappt Effekt, Animation, Wucht, Groesse und Zeiten
  fuer genau diese Zeile auf. Die Moment-Bedienfelder sind damit dort, wo
  sie hingehoeren, statt in einem zweiten Editor.
  DAS EIGENTLICHE PROBLEM war nicht die Oberflaeche:
  (a) Ein Block hatte keine IDENTITAET. `build_groups` bildete ihn bei
      jedem Render neu aus Pausen, Satzzeichen, Sprechtempo und der
      KI-Wucht. Der einzige Schluessel war der erste Wortindex, und der
      verschiebt sich staendig. Loesung: `_bloecke.json` ist jetzt die
      QUELLE der Aufteilung, nicht ein Nachschlagen obendrauf. Liegt ein
      Nutzerplan vor, gewinnt er vollstaendig (`groups_for`).
  (b) **Fliess-Bloecke konnten gar nicht animieren.** Alle neun
      `anim_apply`-Aufrufe hingen an Keyword-Karten (`p['arr']`). Deshalb
      war eine Animation auf einem normalen Textblock bis v192 unmoeglich.
      Jetzt hat der Fliess-Zeichenpfad einen eigenen Aufruf: jedes Wort
      bekommt einen eigenen Zustandstraeger, alle rechnen gegen dieselbe
      BLOCK-Zeit - der Block bewegt sich als Einheit, die Feder-Streuung je
      Wort bleibt natuerlich.
  (c) **Eine Groesse pro Block gab es nicht.** Die Schriftgrade kamen
      ausschliesslich aus globalen Config-Werten. `compose_flow` hat jetzt
      einen `groesse`-Parameter, durchgereicht an ALLE VIER Aufrufstellen
      (Rueckfall auf Zeilensatz und Luecken-Netz eingeschlossen - sonst
      waere die Einstellung je nach Layout mal da, mal weg).
  (d) **ACHT GATES haetten den Block still weggeraeumt**: B-Roll-Gate,
      Atempause, Ein-Wort-Rest, Dichte-Weiche, Satz-Collage, Luecken-Netz,
      Schnitt-Disziplin, Beat-Grid. Besonders die Dichte-Weiche: wer
      'akzente' eingestellt hat (Standard!) haette seine Bloecke verloren,
      ohne eine Meldung zu sehen. Jeder Gate kennt jetzt den Nutzer-Block.
  MITGENOMMENE ALT-FEHLER (beim Kartieren gefunden, alle am Code belegt):
  * Der Momente-Roundtrip baute `fx_map[i]` als frisches dict und verlor
    dabei `anker` (Objekt-Anker v161) und `user_pick` bei JEDEM Render.
    Der Objekt-Anker erreichte `build_plans` also nie.
  * `p['power']` wurde NIE auf einen Plan geschrieben - sieben Leser
    bekamen konstant den Default 2. Dadurch liefen Depth-Bullet-Time, die
    Stille vor dem Einschlag, Split-Screen, Freeze-Frame und zwei
    Timing-Regeln nie an. Jetzt steht die Wucht am Plan.
  * `/api/moments` schrieb Nutzer-JSON unveraendert auf die Platte. Es gibt
    jetzt `sanitize_blocks` SERVERSEITIG (Allowlists, Klemmung, Deckel).
  * `_flow3.json` ueberlebte Transkript-Korrekturen und wurde still
    ungueltig. Wird jetzt beim Transkript-Edit UND beim Block-Speichern
    mitgeworfen.
  * Ein einzelner kaputter Wert verwarf die GANZE Momente-Datei still.
    Der Blockplan faengt pro Eintrag und meldet, was er verwirft.
  BEWEIS (am gerenderten Bild gemessen, nicht behauptet):
  * Text-Override: "wie wir Captions auf" -> "WIE WIR UNTERTITEL AUF" steht
    im Bild.
  * Block abgeschaltet: im Fenster 2.16-3.22 s kein neuer Text.
  * Groesse 1.6: Fliesstext 1.47x, groesstes Wort 1.48x (die Restluecke ist
    die Spaltenbreite, dieselbe Physik wie beim Punch-Deckel v183/v187).
  * Animation auf einem reinen Fliess-Block: 'explosion' spreizt das Wort
    auf 1.13x bei 3.30 s, 1.07x bei 3.40 s, zurueck auf 1.00x bei 3.55 s -
    genau die Feder-Kurve der Animation.
  * Server Ende zu Ende: GET /api/blocks 200, POST speichert, `<script>`
    als Animation und `groesse: 77` werden verworfen bzw. auf 2.0 geklemmt,
    `_flow3.json` weg, "[]" setzt auf Automatik zurueck.
  * UI im Browser: teilen, zusammenlegen, Undo, abschalten - keine
    Konsolenfehler.
  EHRLICH: getestet auf Linux/CPU mit synthetischem Material und OHNE
  OpenAI-Key. Der Testclip hat kein Gesicht, also sind Occlusion,
  Hand-Kontakt und Zwei-Sprecher-Regie im Zusammenspiel mit Nutzer-Bloecken
  hier NICHT verifiziert.
  Tests: 47 neue Pruefungen, logic 1238/1238, render1 7/7, render2a 1/1,
  render2b 5/5, render2c 2/2, GUI_OK. Zwei alte Quelltext-Tests (v140,
  v141) wurden auf die neuen Zeilen gezogen, Invariante unveraendert.
- **v192 EINE STUFE KLEINER (Nutzer-Entscheidung, keine Messkorrektur).**
  Ismets Ansage nach dem v191-Render: "mach es ruhig etwas kleiner".
  Faktor 0.85 auf die v184-Referenzmasse, in `compose_flow`:
  Schluesselwort 0.105 -> 0.089 em (Versalhoehe rund 0.062 H),
  Fliesstext 0.050 -> 0.043 em. Die Kaskade bleibt intakt: `pf`
  (Formatausgleich), `caption_scale`/`caption_scale_klein` aus einer
  gelernten Referenz und der Viral-Multiplikator rechnen weiter relativ
  auf die neue Basis.
  EHRLICH: das Schluesselwort liegt damit knapp UNTER dem an Ismets drei
  Referenz-Clips gemessenen Band (0.074 bis 0.165 H Versalhoehe). Das ist
  eine bewusste Geschmacks-Entscheidung des Nutzers, kein korrigierter
  Messfehler - wer spaeter "zurueck auf Referenz" will, dreht die beiden
  Konstanten auf 0.105/0.050.
  Vier Selftest-Schwellen wurden ehrlich auf das neue Ziel gezogen
  (v184-Basis key/klein, v154-Fliesstext-Fenster, v153-Konstanten-Grep),
  jede mit Begruendung im Testcode.
  BEWEIS: `v192_vgl.jpg`, 4-Kachel-Streifen alt/neu am selben Frame.
  Tests: logic 1190/1190, render1 7/7, render2a 1/1, render2b 5/5,
  render2c 2/2, GUI_OK.
- **v191 REGLER-ANZEIGE + behind-Wort NICHT MEHR ZERSCHNITTEN.**
  Zwei Befunde Ismets, beide am Beleg nachgerechnet.
  (a) REGLER LOGEN. Die Screenshots zeigten "Caption size 6000 %" und
      "Size contrast 14000x". Ursache: der Regler-Bauer nahm bei fehlendem
      Config-Eintrag `min` als ROHwert und multiplizierte danach nochmal
      mit der Anzeige-Skala (60 x 100, 140 x 100). Betroffen war jeder
      Regler, dessen Schluessel nicht in der Config steht - genau die
      beiden. Jetzt liest der Fallback `data-default` in ANZEIGE-Einheiten
      (caption_scale 100 %, caption_hierarchie 283x = das tatsaechliche
      Hausmass 0.105/0.050 em) und klemmt echte Werte an die Skala.
      Ein Selftest prueft ab sofort JEDEN Regler gegen seinen Bereich.
  (b) DAS WORT HINTER DER PERSON WURDE ZERSCHNITTEN. Am neuen Render
      gemessen: 'ZIGARETTEN' spannte 0.239 bis 0.759 W, und die Person
      frass 28 % davon AM STUECK - lesbar blieb "ZIGA...TTEN".
      URSACHE: der v96z-Riegel verglich die Wortbreite mit dem KOPF
      (1.7x Gesichtsbox). Ausgestanzt wird aber die ganze Silhouette
      inklusive SCHULTERN, rund 2.6x Gesichtsbox. Das Wort war klar
      breiter als der Kopf, der Riegel griff nicht, und der Koerper
      zerschnitt es trotzdem.
      NEU, drei Stufen: (1) vergroessern, bis das Wort die Schultern
      beidseitig deutlich ueberragt; (2) reicht das nicht, geht das Wort
      auf KOPFHOEHE - dort ist die Silhouette nur die Gesichtsbox breit
      (das ist die v99-Regel fuer Nahaufnahmen, jetzt auch fuer den
      Normalfall); (3) ist es selbst dort zu schmal, liegt es ueber dem
      Kopf. Jede Stufe schreibt ihre Begruendung ins Log.
  1190/1190 logic + Renders 7/1/5/2 + GUI gruen.
  EHRLICH: die Wirkung von (b) auf echtem Material sieht Ismet erst nach
  dem Deploy - der Testclip hier hat kein Gesicht.
- **v190 RUHE: Woerter erscheinen, statt einzufliegen.**
  Ismets Befund: "alles zu sehr am Zucken". ERST GEMESSEN, dann gebaut -
  und die Messung hat die naheliegende Vermutung widerlegt.
  MESSUNG (Editorial-Render, Ink-Schwerpunkt je Frame in ruhigen Phasen):
  alles an 2.84 Promille W. Ohne Beat-Sync 2.72. Ohne Kamera 2.95. Ohne
  Aktivwort-Pop 2.52. Ohne Motion-Blur 2.84. Mit ALLEM aus 3.09.
  Der Anteil der Effekte an der Unruhe ist also NULL - abschalten machte
  es sogar minimal schlechter. Die Ursache war der Wort-Einflug selbst:
  jedes Wort kam 2 % der Bildhoehe von unten, von 86 % hochskaliert, mit
  ease_back-UEBERSCHWINGEN und gestreutem Timing. Bei drei Woertern je
  Sekunde ist das Dauerbewegung.
  GEBAUT (`effects.caption_ruhig`, Standard an): Woerter erscheinen an
  ihrer Endposition, ohne Positionssprung und ohne Ueberschwingen, mit
  knappem Scale-Ansatz (0.97 statt 0.86) und laengerer Blende. Pop und
  Settle auf 45 bzw. 40 % gedaempft. Das Abdimmen der vergangenen Woerter
  laeuft ueber 0.25 s statt als Helligkeitssprung - bei drei Woertern je
  Sekunde sprang bis v189 mit JEDEM Wort ein Nachbar von 100 auf 70 %.
  BEWEIS: Bildaenderung je Frame von 45.1 auf 38.2 %, Helligkeitssprung
  von 5.39 auf 5.13. Das Alt-Verhalten bleibt ueber den Schalter erreichbar.
  EHRLICHE GRENZE: der groessere Teil der verbleibenden Bewegung ist die
  EREIGNISDICHTE selbst - alle 0.3 bis 0.4 s ein neues Wort, alle rund
  1 s ein neuer Block. Das ist der wortweise Aufbau, also der Referenz-
  Look, kein Fehler. Wer noch mehr Ruhe will, dreht an Standzeit und
  Woertern je Block, nicht an der Animation.
  1184/1184 logic + Renders 7/1/5/2 + GUI gruen.
- **v188/v189 AKZENTE RAUS, SCHRIFTWAHL GANZ, UMRISS NUR AM FLIESSTEXT.**
  Drei Befunde Ismets am Ergebnis, alle umgesetzt.
  v188: die Auto-Motion-Grafik ist wieder AUS. v185 hatte sie eingeschaltet,
  weil die lolo-Referenz Counter und Namens-Karten enthaelt. Am Ergebnis
  war es falsch - dort gehoeren sie zu einer AGENTUR-Produktion mit
  Multikamera und Schnitt; im nackten Talking-Head wirkt die Pille als
  Fremdkoerper. Gerendert wird wieder nur, was im Momente-Editor steht.
  v189 SCHRIFTWAHL: die Font-Kachel setzte nur `fonts.display`. Das
  Schluesselwort nahm die gewaehlte Schrift, der Fliesstext blieb beim
  Preset-Font - der Kunde waehlte EINE Schrift und sah ZWEI. Jetzt setzt
  die Auswahl display, support, italic und strong; die Schreibschrift
  (Akzentwort) bleibt ein eigener Schnitt. Passt auch zur Referenz-
  Grammatik: EINE Familie in zwei Groessen.
  v189 UMRISS: das grosse Schluesselwort laeuft ohne Kontur (Ismets Ansage).
  Dort traegt die Flaeche den Kontrast; der Saum machte das Wort plakativ
  statt gesetzt. Der FLIESSTEXT behaelt ihn - dort ist er der
  Lesbarkeits-Garant aus v181. Umschaltbar ueber
  `effects.caption_kontur_key` (Standard false).
  BEWEIS: Frame-Vergleich mit/ohne Umriss, dunkle Randpixel am grossen
  Wort von 11132 auf 2027.
  TESTKORREKTUR, ehrlich begruendet: die v143-Groessenmessung verglich
  Alpha-Boxen - seit das grosse Wort keinen Saum mehr traegt, der
  Fliesstext aber schon, fiel das gemessene Verhaeltnis scheinbar von 2.2
  auf 1.82, obwohl sich an den Glyphen nichts geaendert hat. `_kern` misst
  jetzt den hellen Glyphenkoerper, genau wie `_ink_x` in der Engine.
  1179/1179 logic + Renders 7/1/5/2 + GUI gruen.
- **v186/v187 PRESET-AUDIT + LIVE-VORSCHAU.**
  Alle neun Looks in beiden Formaten gerendert und vermessen, danach
  adversarisch gegengeprueft: von 50 gemeldeten Positionen blieben 13
  echte Maengel, 7 davon schwer. Fast alle sassen in der GEMEINSAMEN
  Engine, nicht in einzelnen Presets - deshalb wirken die Fixes ueberall.
  SCHWER (alle behoben und nachgemessen):
  1. DER FLOW-SATZSPIEGEL KANNTE DIE PLATTFORM-MASKE NICHT. Feste 0.86 W
     ab 0.07 W gegen einen sicheren Korridor von 0.788 W. spot() konnte
     nicht mehr klemmen (untere und obere Grenze fielen zusammen), der
     Laufzeit-Zoom schob den Block danach zusaetzlich nach rechts. EINE
     Ursache fuer BEIDE Symptome: Text unter den TikTok-Buttons (9 von 17
     Woertern, bis 0.957 W) UND am Bildrand abgeschnittene Buchstaben.
     Neu: `_korridor()` liefert die zoom-bereinigte nutzbare Breite,
     compose_flow bekommt sie als `maxw` - getrennt von `colw`, das die
     Nahaufnahme-Sperre bleibt (sonst haetten Randabfall und Punch-Deckel
     nie wieder gegriffen). Der Knall-Deckel kennt die Maske ebenfalls.
     Gemessen ueber alle 9 Looks x 2 Formate: 0 Verstoesse, 0 Ausreisser.
  2. DER LOG SAGTE DAS GEGENTEIL. `safe_zone_report` prueft nur Plaene mit
     'arr'/'cx', also ausschliesslich Keyword-Karten - jeder Flow-Block
     fiel durch. Deshalb hat nie jemand gewarnt. Riegel am falschen Gate,
     derselbe Fehlertyp wie v159/v170/v176. Jetzt mit Flow-Zweig, und er
     misst die TINTE statt des Sprite-Rechtecks (bis 180 px Glow-Polster
     haetten sonst Fehlalarme erzeugt).
  3. DIE AKZENT-PILLE LAG AUF DER CAPTION. Die Kollisionspruefung gibt es,
     aber `_caption_boxes` las cx/cy vom Plan - die haben Flow-Bloecke
     nicht - und fiel auf eine Ersatzbox aus der Zeit VOR v143 zurueck
     (mittig, 0.31 bis 0.48 H). Jetzt Union-Box aus den Items. Direkte
     Folge davon, dass v185 die Akzente wieder eingeschaltet hat.
  4. DER SCHLUSSWORT-KNALL WAR NUR UEBER DIE BREITE GEDECKELT. Querformat
     lief auf 0.22 bis 0.28 H (Referenz-Obergrenze 0.165 H). Jetzt harter
     Hoehen-Deckel. EHRLICHE GRENZE, NICHT GEFIXT: im Hochformat erreicht
     ein langes Wort den Faktor 2.25 nie - bei 1080 W braeuchte ein
     8-Zeichen-Wort ueber 1500 px. Erzwingbar nur mit Anschnitt (v152
     verbietet ihn ab 6 Zeichen, am Render belegt) oder Zeilenumbruch.
     Beides waere schlechter als ein etwas kleineres Wort.
  5. DIE ZEILENHOEHE RECHNETE MIT DER NOMINALEN GROESSE. Beim Knall klafften
     Soll (153 px) und gesetzt (344 px) um Faktor 2.25 auseinander, die
     Glyphe ragte je 80 px in die Nachbarzeilen - echte Tinte auf Tinte.
     `_rsz` nimmt jetzt immer die gesetzte Groesse.
  6. DER TIKTOK-PRESET WAR KAPUTT. Er schickte `density: wortweise`, einen
     Wert, den die Engine an keinem ihrer fuenf Gates kennt - er fiel in
     den sparsamen Pfad. Der Look, den die UI als "word by word" verkauft,
     zeigte die Haelfte der Woerter, und die v185-Zusagen liefen dort nie.
     Preset und UI auf 'durchgehend', plus Normalisierung in der Engine
     fuer bereits gespeicherte Kunden-Konfigs.
  7. CLEAN HATTE KEINE KONTRAST-GARANTIE. Als einziger Look feste dunkle
     Palette mit adaptive:false, damit laeuft `fit_caption_color` nicht -
     und die Kontur war hart schwarz, also dunkler Saum um dunklen Text
     (gemessen 1.37:1). Die Kontur richtet sich jetzt nach der Textfarbe.
  MITTEL (alle behoben): outline-Karte erreichte im Hochformat konstruktiv
  nie die Referenzhoehe (Deckel 0.09 -> 0.115 em, Breite am echten
  Korridor); Auto-Akzent wiederholte woertlich das Schluesselwort und
  stand mit veralteter Standzeit weiter (Keyword-Menge wird jetzt bis in
  `sanitize_accents` durchgereicht, Standzeit haengt am Anker-Wort);
  Solo-Riegel kappte Bloecke, bevor ihr letztes Wort ueberhaupt einsetzte;
  Verbinder-Liste kannte 'ist', aber nicht sind/war/hat/wird - die
  Betonung landete auf Hilfsverben; Vorschau-Modus nahm 540 als Bildhoehe
  statt als kurze Kante (v149-Regel); Laufweite skalierte im Hochformat
  nicht mit dem Schriftgrad.
  VERWORFEN (11 Meldungen): Standbild-Artefakte aus Aufbau- und
  Ausklingphasen, Einheitenfehler, Eigenheiten des gesichtslosen
  Grau-Testclips, Doppelmeldungen desselben Codefehlers.
  v186 LIVE-VORSCHAU: unter der Look-Auswahl laeuft eine 9:16-Buehne mit
  einer echten Caption-Sequenz, gebaut aus der ECHTEN Look-Config
  (`/api/default_config`) - Schriftdatei, Hausmasse 0.105/0.050 em,
  Viral-Faktoren, Kontur, Woerter je Block, Standzeit, Aktivwort-Emphase,
  Versalsatz. Dazu Fakten-Chips und der ausdrueckliche Hinweis, dass
  Kamera, Freistellung und Effekte NICHT gezeigt werden - eine geschoente
  Attrappe waere schlimmer als keine Vorschau. Browser-getestet ueber alle
  Looks, keine JS-Fehler.
  EHRLICH: Linux/CPU, synthetischer Grau-Clip ohne Gesicht, ohne Key.
  Occlusion, Zwei-Sprecher-Regie und Hand-Kontakt liessen sich damit nicht
  pruefen. Tests: +30 neue Checks (v186/v187), fuenf Alt-Checks ehrlich
  nachgezogen. 1173/1173 logic + Renders 7/1/5/2 + GUI gruen.
- **v185 DIE VIER GEMESSENEN MAENGEL - plus drei Folgefunde.**
  Ismets Viral-Render (Build v184) durchgemessen statt beurteilt. Was
  objektiv falsch war, ist behoben; an "sieht aus wie lolo" wurde NICHT
  gearbeitet (in dieser Referenz stecken zwei Kameras, B-Roll und eine
  Titelsequenz - das kann kein Renderer erzeugen, siehe unten).
  (1) VIER SEKUNDEN LOCH von 15 s, dazu 4 von 30 Woertern nie im Bild.
      URSACHE (reproduziert): die Atempause nach einem Keyword-Moment
      loeschte die KOMPLETTE Folgegruppe, und eine Keyword-Karte zeigt nur
      EIN Wort ihrer Gruppe. Zusammen ergab das mehrsekundige Leere.
      Die Atempause gilt jetzt nicht mehr bei Dichte 'durchgehend' (dort
      ist "jedes Wort steht im Bild" eine Zusage, kein Stil), dazu ein
      LUECKEN-NETZ als letzte Sicherung: was am Ende kein Plan zeigt,
      bekommt eine schlichte Flow-Caption. Der v170-Riegel (Ein-Wort-Rest
      nach langer Pause faellt weg) bleibt davon unberuehrt.
  (2) FUENF ELEMENTE IN VIER STILEN gleichzeitig (BEHIND, Me, RIGHT,
      WORDS, THESE FORM). resolve_overlaps raeumte nur bei gleicher
      Position auf - Karte oben plus Block unten galt als saubere
      Neben-Platzierung. In ALLEN Referenzen traegt ein grosser Moment das
      Bild allein. Neuer Solo-Riegel: solange eine Keyword-Karte steht,
      raeumt jeder andere Textplan. Gerechnet wird mit dem AUSKLINGEN
      (0.40 s Exit-Fenster), nicht mit dem Ende - mit dem blossen Ende
      sagten die Zahlen "keine Ueberschneidung", waehrend im Bild 'WIR'
      auf 'ZEIG' lag (Frame fuer Frame belegt). Gedraengte Karten bekommen
      zusaetzlich ein kurzes eigenes Ausklingen ('aus' am Plan).
  (3) MIKROVERSALIEN: die Stuetzzeile lief hart auf 0.043 H mit Tracking
      14 - gesperrte Winzversalien, die zu keinem Look gehoerten. Sie
      nimmt jetzt Groesse und Laufweite des Fliesstexts, inklusive
      Referenz- und Viral-Skalierung.
  (4) GELB-AKZENT RAUS (Ismet: "ausgelutscht"). Die Farb-Karaoke ist
      komplett entfernt (tint_glyph, acc_rgb, feste Akzentfarbe im
      Preset). Sie war der Marker jedes CapCut/Opus-Templates und landete
      ausserdem auf Fuellwoertern (AND, THAT, TO, IS). Die Emphase traegt
      jetzt in allen Looks Groessen-Pop plus Dimmen auf 70 %.
  FOLGEFUNDE aus derselben Messung, alle behoben:
  - Woerter ausserhalb des Bildes ('Level' bei 1.15 W, 'deines' bei
    1.57 W): die Zeilen um das Schluesselwort wurden nie umbrochen, und
    ein einzelnes langes Wort bekam kein S.fit. Beides jetzt da.
  - Klebende Wortabstaende ("SINDDIE", "AUFEIN"): der Abstand hing nur an
    der Bildbreite und fiel mit den v184-Groessen unter 0.17 em. Jetzt
    mindestens ein Drittel Geviert.
  - MOTION-GRAFIK-AKZENTE wieder AN (accents.auto). v139 hatte sie auf
    Ismets Ansage abgeschaltet ("Captions pur") - seine eigene High-End-
    Referenz traegt aber genau diese Elemente (Views-Counter mit Icon,
    Badge "7X", Namens-Karte mit Pfeil). Dosiert bleiben sie durch
    sanitize_accents (Dichte-Deckel plus 3.5 s Mindestabstand).
  BEWEIS: Testrender Hochformat, gemessen - kein Gelb mehr, keine
  Textluecke ueber 0.8 s, nie zwei Textebenen gleichzeitig, nichts
  ausserhalb des Bildes, Chip-Akzent laeuft.
  EHRLICH: CPU, synthetischer Grau-Clip, ohne Key. Die Wirkung auf echtem
  Material prueft Ismet nach dem Deploy. Tests: +17 neue v185-Checks;
  vier Alt-Checks ehrlich nachgezogen (v139 Akzente jetzt an, v150
  Zeilenschwelle durch den neuen Umbruch, v182/v183 Farb-Karaoke raus).
  1142/1142 logic + Renders 7/1/5/2 + GUI gruen.
  NICHT GEBAUT und warum: die lolo-Referenz enthaelt 15 Schnitte in
  23.7 s, Multikamera, B-Roll, Screen-Recordings, eine designte
  Titelsequenz und Farbkorrektur. Captions sind darin rund 20 % des
  Eindrucks. Diesen Teil kann Software liefern, den Rest nicht.
- **v184 REFERENZ-GRAMMATIK (an Ismets drei High-End-Vorbildern gemessen).**
  Ismet: "Das sind alles high end Animationen. Die habe ich dir schon 1000x
  geschickt. Konntest es trotzdem nicht nachbauen." Drei Referenzen durch
  die eigene Mess-Engine + Frame-Analyse gezogen (A @kram.visuals,
  B @migs.visuals, C @johnbacog_). Gemeinsame Grammatik: Satz waechst Wort
  fuer Wort und BLEIBT; jedes Wort schliesst raeumlich ans vorige an
  (Lesepfad); Verbinder-Ketten in Schreibschrift INLINE; EIN riesiges
  Schlusswort, das teils HINTER der Person verschwindet; Groessen: Band
  0.074 H (B-Key) bis 0.184 H (C-Punch), Fliesstext-Band 0.040 H in ALLEN
  DREI. Unsere Basis (0.053/0.018 H) war die Haelfte davon.
  DREI UMBAUTEN:
  1. CLUSTER-LESEPFAD ersetzt die v150-Spalten-Collage. Kurze Zeilen
     (1-3 Woerter) mit deterministischem Treppen-Einzug, enger Zeilenfall
     (1.06), gemeinsame GRUNDLINIE je Zeile (Vorbild 'add CREATORS'),
     Schluesselwort IM Pfad mit hoechstens einem kleinen Wort davor.
     EHRLICHE URSACHE des alten Looks: v150 stellte Verbinder in eine
     EIGENE Spalte neben die Treppe - Lesereihenfolge und Raumfolge fielen
     auseinander ('that/to/one'-Saeule neben STICKS). Neue Regel, an der
     der Block haengt: RAUMFOLGE = LESEREIHENFOLGE.
  2. REFERENZ-GROESSEN: key 0.076 -> 0.105 em (Versal ~0.074 H = Ref B),
     Fliesstext 0.034 -> 0.050 em (Band ~0.040 H = alle drei Refs). Punch
     2.25x ergibt ~0.165 H und trifft die C-Punchline. Die v153/v154-
     Verkleinerungen galten der ALTEN Anordnung; die Viral-Faktoren sind
     auf die neue Basis umgerechnet (Ziel unveraendert), zwei Alt-Tests
     ehrlich nachgezogen (hier dokumentiert, nicht still).
  3. PUNCH HINTER DER PERSON (Ref C 'this'): occlude_sprite() stanzt die
     Personen-Silhouette pro Frame an der Zielposition aus der Sprite-
     Alpha - Zeichenreihenfolge des Frames bleibt unangetastet. Nur am
     Satzende, nie auf B-Roll, nie bei angesagtem Hand-Schub, Schalter
     effects.caption_hinter. Sichtbar nur bei echter Ueberlappung.
  BEWEIS: Cluster-Streifen Hochformat (ein/neues/Level/BRINGEN-Treppe,
  das/MOMENTE/deines/Videos/Klar mit Script-Akzent) an Ismet geschickt;
  Occlusion per Unit-Test belegt (Stanzung exakt auf der Personen-Seite).
  EHRLICH: CPU/synthetisch/ohne Key; Occlusion auf echtem Material und die
  Groessen-Wirkung prueft Ismet nach dem Deploy. Tests: v150-Anordnungs-
  Checks durch Lesepfad-Invarianten ersetzt, +7 neue v184-Checks,
  1126/1126 logic + Renders 7/1/5/2 + GUI gruen.
- **v183a VIRAL-LOOK ZURUECKGESTUFT (Ismets Befund am Ergebnis).**
  "Jetzt hast du einfach das Standard-Template von CapCut und Opus
  kopiert." Stimmt: Versal-Montserrat + gelbes Karaoke-Wort IST das
  meistkopierte Caption-Design - genau das "KEINE STANDARD MUELL" aus dem
  v181-Briefing, und ich habe es trotzdem zum Default gemacht. EHRLICHE
  URSACHE: "Marktniveau" wurde mit "Markt-Template" verwechselt. Die
  GROESSEN-Messung (0.10-0.15 H) war richtig, die STIL-Kopie war falsch.
  Konsequenz: der Auto-Default fuer 9:16 ist RAUS (kein Kunde landet
  ungefragt im Template), der Look steht nicht mehr an erster Stelle im
  Katalog. Er bleibt als waehlbare Option - wer das Template will, kriegt
  es. Die beiden globalen v183-Fixes (zoom-sicherer Punch-Deckel,
  Mitte-Zentrierung) bleiben - das waren echte Fehler, kein Stil.
  OFFEN: was "high level" fuer DouchkoVE heisst, entscheidet Ismet
  (Referenz-Clips angefragt statt drittes Raten).
- **v183 VIRAL-LOOK (Markt-Standard als Preset, Default fuer 9:16).**
  Ismets Urteil: "Das Produkt selbst ist nicht mal ansatzweise so gut. Es
  ist keine High-Level-Typografie/Captions." Erst gemessen: sein Render
  (creator-Look) faehrt Keywords bei 0.078-0.096 H Versalhoehe, Fliesstext
  bis 0.014 H, Streu-Collage ohne klare Lesereihenfolge, Akzente klein in
  Schreibschrift. Der Markt (Submagic/Hormozi-Schule, Recherche Juli 2026)
  faehrt 0.10-0.15 H VERSAL fuer praktisch alle Woerter, enge 2-4-Wort-
  Bloecke mittig-unten, EINE harte Akzentfarbe die mit dem gesprochenen
  Wort wandert. Das ist ein anderer STIL, keine bessere Technik - aber es
  ist der Stil, der 2026 als "high level captions" verkauft wird.
  NEUER LOOK 'viral' (Server-Preset + Engine-Schalter `caption_viral`):
  - ALLE Woerter versal + extrabold (Montserrat XB, eine Familie). Groesse
    als MULTIPLIKATOR auf die Hausmasse: Schluesselwort 2.15x (0.163 em,
    ~0.115 H Versal), Fliesstext 2.90x (0.099 em, ~0.069 H). Kurze Woerter
    stehen voll, lange schrumpfen in die Zeile (v143-Prinzip). Eine
    gelernte Referenz (caption_scale) skaliert weiter relativ dazu.
  - KARAOKE-AKZENT: die Akzentfarbe (fest Gelb 255/214/10, adaptive aus -
    der Look lebt von der Konstanz) wandert mit dem gesprochenen Wort
    (`tint_glyph` faerbt den Glyphenkoerper, die v181-Kontur bleibt
    dunkel). Vergangene Woerter dimmen im Viral-Look NICHT - die Farbe
    traegt die Emphase. Pop 10 % statt 5.5 % (auf Marktgroesse sonst
    unsichtbar). Kein Schreibschrift-Akzent - zwei Akzent-Systeme
    nebeneinander entwerten sich.
  - Zeilensatz statt Collage (Riegel an der immer laufenden Stelle in
    build_plans, v159-Lehre - ein User-Override caption_layout=collage
    saehe zerrissen aus), Bloecke mittig (caption_seite mitte), Markt-Zone
    0.58 H statt Haus-Zone 0.25 H. spot() weicht weiter aus.
  - words_per_group 2/4, density durchgehend, chunk_hold 0.55, Kontur 1.5.
  ZWEI GLOBALE FIXES (alle Looks, am Testrender belegt):
  - Zeilen mit seite 'mitte' und Zeilen BREITER als der Satzspiegel werden
    im Spiegel ZENTRIERT (Netflix-Konvention; buendig bei x0 lag die
    Punch-Kante bei 0.96 W).
  - Der Punch-Deckel kennt den CRASH-ZOOM: 0.89 W minus 0.11 W mal
    camera.crash. Der Zoom sitzt genau auf Punch-Momenten und schob die
    0.89-W-Kante aus dem Bild (gemessen 0.999 W = angeschnitten, MOMENTE-
    Fall). crash 0 = Alt-Verhalten. Der gewollte Randabfall (bleed, <= 5
    Zeichen) bleibt bei 1.14 W.
  DEFAULT-REGEL: Hochformat-Upload waehlt in der Web-UI 'Viral' vor
  (State.lookChosen schuetzt jede bewusste Wahl; Querformat bleibt
  Creator). Editorial und alle anderen Looks bleiben unveraendert waehlbar.
  BEWEIS: Hochformat- und Querformat-Testrender (Frame-Streifen an Ismet):
  Versalien mit Karaoke-Gelb, keine Rand-Anschnitte mehr (Text-Spanne
  gemessen max 0.964 W unter vollem Crash-Zoom, vorher 0.999 W = Kontakt).
  EHRLICH: CPU/synthetisch/ohne Key - die echte Optik prueft Ismet nach
  dem Deploy auf echtem Material. Tests: +18 (Preset/UI-Garantien,
  compose_flow-Verhalten: Versalsatz, 2.9x-Mass, kein Script-Akzent,
  Punch 1.30, Zoom-Deckel, Mitte-Zentrierung, tint_glyph-Farbmessung);
  zwei v182-String-Checks ehrlich nachgezogen (Substanz unveraendert).
- **v181/v182 LESBARKEIT + AKTIVES WORT.** Ismets Urteil am v180-Render:
  "Grundgeruest steht. Es ist aber noch nicht high end." Erst gemessen,
  dann recherchiert.
  MESSUNG an seinem Render (WCAG-Kontrast Text gegen Untergrund):
  0.6 s = 1.52:1, 4.0 s = 3.10:1, 10.0 s = 1.81:1, 14.5 s = 1.58:1.
  Norm ist 4.5:1 - ALLE vier darunter. Der Text trug nur einen VERSETZTEN
  Schlagschatten; auf grauem Pullover und Betonwand ist der wirkungslos.
  Nicht die Choreographie war das Problem, sondern das Finish.
  MARKTSTAND (Recherche, Juli 2026): aktives Wort hervorgehoben
  (Karaoke-Emphase) ist der dominante Stil, 78.6 % aller Captions sind
  animiert; weiss + duenne dunkle Kontur gilt als Gold-Standard, weil sie
  auf hell UND dunkel traegt; 2-5 Woerter je Chunk, 600-900 ms Standzeit.
  Pacing, Wort-fuer-Wort-Aufbau und Groessenhierarchie hatten wir bereits.
  v181 LESBARKEIT:
  - Echte KONTUR am Glyphenrand (0.055 der Schriftgroesse, rund 2-4 px im
    Hausmass), auf der HINTEREN Ebene, damit das Studio-Licht sie nicht
    aufhellt. Ueber `effects.caption_kontur` regelbar/abschaltbar.
  - `caption_contrast` von 2.2 auf 4.5 (WCAG AA).
  - `fit_caption_color` faellt notfalls auf reines Weiss/Schwarz zurueck:
    ein Szenen-Ton, den man nicht lesen kann, ist keine Handschrift.
  - MIT Kontur bleibt der Text auf mittelgrauem Grund HELL. Erster Versuch
    kippte ihn nach Dunkel - lesbar, sah am Testrender aber aus wie ein
    anderer Look (schwarze Buchstaben auf grauer Wand). Erst ab wirklich
    hellem Untergrund (Fenster, Himmel) gewinnt Dunkel.
  BEWEIS: Testrender auf mittelgrauem Untergrund, Frame-Streifen an Ismet -
  vorher flaues Hellgrau auf Grau, nachher Weiss mit sauberem dunklem Saum.
  v182 AKTIVES WORT: das gerade gesprochene Wort steht voll und mit
  abklingendem Groessen-Pop (5.5 % ueber 0.22 s), die schon gesprochenen
  dimmen auf 70 %. Schluesselwoerter dimmen NIE - sie tragen die Aussage.
  Bewusst ohne Farbwechsel: der Akzentton gehoert im Hausstil dem
  Schlusswort, zwei Akzente nebeneinander entwerten sich.
  NEBENEFFEKT GEFUNDEN UND EINGEORDNET: die Kontur macht die gemessene
  Ink-Breite minimal groesser. `_ink_x` misst deshalb den GLYPHENKOERPER
  statt jeden Alpha-Pixel; ein Rest von 0.003 W bleibt (Antialiasing
  zwischen Glyphe und Saum). In einem EXTREMEN Nahaufnahme-Testfall
  (Kopfbox ueber 0.01-0.79 H) kippte das die Hoehen-Wahl von 0.170 auf
  0.595 H - die Spalte (x) und sx blieben identisch bei 0.089. Ein Test,
  den 3 Promille Breite umwerfen, misst Rauschen statt Regel: die
  x-Pruefung bleibt hart, die y-Pruefung geht nur noch gegen den sicheren
  Bereich. NICHT still weggedreht - hier dokumentiert.
  NICHT GEBAUT (Ismets Wahl): die Schriftgroesse auf Marktniveau
  (0.110 H -> 0.15 H Versalhoehe) steht weiter aus.
- **v180 Querformat steht MITTIG.** Ismets Frage: "ist es denn wirklich so
  professionell, wenn die captions bei einem 16:9 video immer unten links
  oder unten rechts sind?" Nein - und im Code nachgesehen: die
  Seiten-Abwechslung aus v168 war NICHT aufs Hochformat begrenzt. Sie war
  gegen sein "immer links" bei 9:16 gebaut und lief als Nebeneffekt auch
  bei 16:9.
  WARUM MITTIG RICHTIG IST:
  - Fuer eingebrannten Text im Querformat ist unten MITTIG die Konvention
    (Netflix TTSG, BBC-Subtitle-Guidelines, SMPTE Title-Safe). Links oder
    rechts geparkt ist die Sprache von Lower-Third-Namensgrafiken, nicht
    von gesprochenem Text.
  - 16:9 hat wenig Hoehe, die Person sitzt fast immer mittig - seitlicher
    Text rutscht an den unruhigen Bildrand (in Ismets Clip genau ins
    Fenster).
  - Im Querformat ruht der Blick mittig; wechselnde Seiten zwingen den
    Zuschauer, den Text zu suchen.
  MITTE IST EIN WUNSCH, KEINE FESSEL: `spot()` darf weiter ausweichen.
  Gemessen (1920x1080): Person oben mittig -> Bloecke bei 0.49/0.49/0.49/
  0.44 W; Person UNTEN mittig, also im Weg -> 0.75/0.74/0.75/0.70 W. Das
  v143-Ausweichen ist unberuehrt, ebenso Zeige-Ziel, Hand-Geste,
  Sprecherwechsel und die ausdrueckliche Nutzerwahl (`caption_seite`,
  geprueft mit 'rechts' -> 0.66 W).
  HOCHFORMAT UNVERAENDERT: dort wechselt die Seite weiter wie in v168
  (gemessen 0.34 / 0.67 / 0.33 / 0.77 W).
  TESTKORREKTUR: die v168-Nachweise liefen auf 1920x1080 und pruefen jetzt
  im Hochformat - die Querformat-Regel deckt v180 ab. Kein Verhalten
  verloren, nur die Zustaendigkeit sauber getrennt.
- **v179 Nur noch die angesagte Caption wird geschubst.** Ismets Abnahme
  von v178: "jetzt ist es schon sehr gut. Das Problem: alle captions sind
  jetzt etwas davon betroffen." Zu Recht - und die Ursache war eine
  Wechselwirkung meiner eigenen letzten drei Versionen:
  - v174 hatte einen NAEHERUNGS-Treffer eingebaut (Reichweite 0.075 W,
    schnelle Hand in Richtung Text). Das war ein Notbehelf, weil damals
    ueberhaupt kein Kontakt zustande kam.
  - v176 hat die Pruefung dann auf ALLE Flow-Chunks ausgeweitet.
  Zusammen hiess das: wer beim Sprechen gestikuliert - also praktisch
  jeder - loeste an JEDER Caption im Video ein Zucken aus.
  Der Naeherungs-Treffer ist jetzt RAUS. Er wird nicht mehr gebraucht:
  den angesagten Schub traegt seit v177/v178 die Ansage plus der
  gemessene Wisch, voellig unabhaengig von der Entfernung. Fuer alles
  andere gilt wieder die klare v101j-Regel: es zaehlt, was die Hand
  WIRKLICH beruehrt.
  Damit stehen drei saubere Stufen: angesagter Wisch -> voller Schub
  (~143 px), echte Beruehrung -> Stups (~16 px), Geste daneben -> nichts.
  Als Invarianten im Selftest festgeschrieben, inklusive der Gegenprobe,
  dass der Naeherungs-Code wirklich verschwunden ist.
  LEHRE: ein Notbehelf muss zurueckgebaut werden, sobald die richtige
  Loesung steht. Sonst addieren sich beide zu einem neuen Fehler.
- **v178 Wucht nach Ansage: aus dem Stups wird ein echter Schub.** v177
  loeste den Impuls endlich aus - am Render gemessen aber nur 27 px
  Ausschlag (Blockmitte 0.5995 -> 0.6365 H bei 8.30 s, zurueck auf 0.6001
  bei 8.50 s). Ein Stups, kein "push them AWAY". Ursache: der Deckel
  W*1.2 und die Feder K=120/C=9 stammen aus v101j und sind fuer den
  ZUFAELLIGEN Kontakt gebaut - ein Handzucken darf das Layout nicht
  zerlegen, das ist richtig.
  Wer die Handlung ANSAGT, hat sie bestellt. Der angesagte Wisch bekommt
  deshalb einen eigenen Satz Werte: Deckel W*3.6 (dreifach),
  Impuls-Gewicht 2.2 statt 0.9, weichere Feder mit weniger Daempfung
  (K=52, C=5.2). Der beilaeufige Kontakt bleibt EXAKT bei den
  v101j-Werten - beide Wege sind getrennt getestet.
  GEMESSENE KURVE: Spitze -143 px bei 0.16 s nach dem Stoss,
  Nulldurchgang bei 0.44 s, Nachschwingen +38 px, Ruhelage nach rund 1 s.
  Das ist eine unterdaempfte Feder mit sichtbarem Overshoot, kein Ruck.
  Selftest: angesagt 172 px Gesamtausschlag, Kontakt 16 px - Faktor > 3
  ist als Invariante festgeschrieben, ebenso die Rueckkehr in die
  Ruhelage (ein Text, der weggeschoben BLEIBT, waere ein verlorener Satz
  statt eines Effekts).
  BEWEIS fuer v177 davor, am echten Render (Job 57c2fb53 gegen d70adb09):
  vorher stand die Blockmitte drei Nachkommastellen lang still (0.5946 /
  0.5945 / 0.5944 H), nachher schwang sie mit. Frame-Streifen an Ismet.
- **v177 Der angesagte Wisch braucht keine Pixel-Beruehrung.** v176 hat
  gewirkt (Hand-Erkennung laeuft jetzt in Flow-Fenstern, Kontakt und Feder
  greifen), und trotzdem passierte im Render nichts. Ursache diesmal am
  Job d70adb09 GEMESSEN, mit MediaPipe auf den echten Frames:
  - Die Fingerspitzen wischen von x = 0.72 auf 0.64 W mit 690-861 px/s,
    dann verliert der Detektor die Hand (Bewegungsunschaerfe) und findet
    sie erst wieder bei (0.17, 0.95) - also am unteren Bildrand.
  - `hand_ziele` liefert korrekt Ziele bei 0.63 und 0.69 W. Angewandt
    wurden sie NICHT: dort steht der Sprecher. Das Hand-Ziel wiegt 2.2,
    die Gesichtssperre 2.5 - der Block bleibt bei 0.17 W. Das ist
    RICHTIG so, Text quer ueber dem Kopf waere ein Fehler.
  Damit war die Lage klar: die Hand faehrt vor dem eigenen Koerper
  entlang, die Caption kann dort per Definition nicht liegen, und auf
  Pixel-Beruehrung zu warten heisst, dass die Geste FUER IMMER folgenlos
  bleibt. Kein Riegel-Fehler mehr, sondern eine falsche Grundannahme.
  NEU: sagt der Satz die Handlung ("I can just push them away", erkannt
  ueber `_HAND_AKTION`) UND ist ein schneller Wisch messbar (> 0.50 W/s),
  bekommt der Block den Impuls in Wisch-Richtung - ohne Beruehrungspruefung.
  Ansage plus Messung, nichts geraten. Ohne Ansage bleibt alles beim
  Alten (Beruehrung bzw. Naeherung aus v174), eine Ansage ohne echten
  Wisch loest nichts aus.
  Beweis (Selftest): Wisch weit weg + Ansage -> Impuls, Richtung stimmt;
  ohne Ansage -> 0; Ansage ohne Wisch -> 0.
  LEHRE: erst messen, wo die Bewegung wirklich verlaeuft. Drei Versionen
  lang habe ich Gates repariert, obwohl die Geometrie das Problem war.
- **v176 Der Hand-Kontakt erreicht endlich die Flow-Chunks.** Ismets
  Befund "die Hand-Erkennung und Captions agieren nicht zusammen", diesmal
  am ECHTEN Render nachgemessen (Job 8ff7812b, v174-Stempel) statt geraten:
  MediaPipe auf seine Frames losgelassen, Handflaeche bei 8.0 s auf
  x = 0.58 W, bei 8.2 s auf x = 0.19 W - die Hand KREUZT den Text, der bei
  0.47 W steht. Der Kontakt waere da gewesen und kam trotzdem nicht.
  URSACHE: das komplette Hand-System haengt an `'kw_i' in p`. `need_hands`
  schaltete den Tracker in Fuellwort-Fenstern gar nicht erst ein, und
  `hand_contacts` uebersprang jeden Plan ohne kw_i. Ismets Schub-Satz
  ("and i just can push them away") ist ein reiner Fuellwort-Chunk - der
  v174-Naeherungstreffer lief also in einer Funktion, die diesen Plan nie
  zu Gesicht bekam. Genau der Fehlertyp aus v159/v170, drittes Mal:
  ein Riegel am falschen Gate.
  DREI STELLEN, alle noetig:
  1. `need_hands` schaltet jetzt auch in Flow-Fenstern scharf.
  2. `hand_contacts` kennt Flow-Chunks: sie haben kein einzelnes `arr`,
     sondern viele Wort-Sprites - die Trefferbox kommt aus deren Huelle.
  3. Die Beruehrungs-Feder wird auf den Flow-Block ADDIERT. Vorher lief
     der Impuls nur ueber track_offset/scene_shift (Keyword-Sprites) -
     ein Flow-Chunk konnte gestossen werden und blieb trotzdem stehen.
  BEWEIS (Selftest): Hand kreuzt Flow-Block -> Kontakt = 1, Feder-Versatz
  32 px nach zwei Ticks; ferne langsame Hand -> 0; Keyword-Pfad (v101j)
  unveraendert.
  MESSUNG statt Vermutung: die Positionen oben stammen aus einem echten
  MediaPipe-Lauf auf Ismets Renderframes, nicht aus dem Selftest.
  NICHT LIVE VERIFIZIERT: wie stark der Stoss im fertigen Video wirkt,
  zeigt erst der naechste Render.
- **v175 Doku-Korrektur: Sound und Stripe sind FERTIG, nicht offen.** Ismets
  Hinweis, nachdem ich beides als fehlend aufgezaehlt hatte. Am Repo bzw.
  von ihm bestaetigt:
  - `sfx/pack` ist VOLLSTAENDIG: 14/14 Slots belegt (impact, whoosh,
    whoosh_soft, riser, tick, counter, boom, crack, fall, rise, turn,
    press, vanish, slam) plus Manifest `pack.json`, alle Eintraege mit
    Ismets eigener Lizenz, alles git-getrackt. Gegenprobe:
    `python -c "import sfx_pack; print(sfx_pack.pack_status())"` ->
    belegt 14, gesamt 14. Videos sind NICHT stumm.
  - **Stripe laeuft im LIVE-Modus.**
  Beide Punkte standen noch in CLAUDE.md unter "Offene echte Punkte" und im
  Geschaefts-Abschnitt - daher habe ich sie wiederholt als fehlend genannt,
  statt nachzusehen. Beide Stellen sind jetzt korrigiert und ausdruecklich
  als ERLEDIGT markiert, damit kein neuer Chat denselben Fehler macht.
  LEHRE (dieselbe wie beim Standbild-Fehlurteil in v174): erst MESSEN, dann
  behaupten - auch bei der eigenen Doku. Eine Zeile in CLAUDE.md ist kein
  Beweis fuer den heutigen Stand.
- **v174 Hand und Captions agieren zusammen** (Ismets Befund am
  v173-Render: Schub-Geste bei "push them away", der Text stand am anderen
  Bildrand und reagierte nicht). Zwei Teile:
  1. NAEHERUNGS-TREFFER im Hand-Kontakt (v101j): eine schnelle Hand, die
     auf den Text ZUFLIEGT, trifft auch ohne Pixel-Beruehrung (Reichweite
     0.075 W). Dafuer zwei Bedingungen mehr als beim echten Kontakt:
     hoehere Mindestgeschwindigkeit (0.25 W/s statt 0.10) UND die
     Bewegungsrichtung muss ZUM Text zeigen (Skalarprodukt >= 0.5). Eine
     wegfliegende oder lahme Hand trifft weiter nichts.
  2. HAND-AKTIONS-WOERTER ziehen die Caption in Reichweite: sagt der
     Sprecher push/shove/swipe/wegschieben/wischen/anfassen, misst
     `hand_ziele()` die Handposition an diesen Wort-Zeitpunkten
     (Handflaechen-Mitte, Landmark 9 - die Spitze zittert, das Gelenk
     steht) und speist sie als Zeige-Ziel ein. Gleicher Weg wie v160/v167:
     Platzierung, Dedupe, Hysterese identisch. Laeuft ueber ALLE Woerter,
     nicht nur Keywords - der Schub-Satz war bei Ismet ein
     Fuellwort-Chunk.
  EHRLICHE KORREKTUR im selben Zug: "EXPLODE" war NIE verdeckt. Der
  Frame-Verlauf (3.4/3.7/4.0/4.3 s) zeigt das Wort voll deckend vorn;
  mein Standbild bei exakt 4.0 s traf die EXIT-BLENDE und ich habe drei
  Versionen lang (v169/v170/v172/v173) eine Ausblend-Phase als
  "hinter der Person" fehlgedeutet - derselbe Standbild-Fehler wie beim
  "is" (v172). Die gebauten Riegel bleiben drin: es sind echte, getestete
  Luecken (Cache-, Anim-, Wort-, blurin-Pfad), nur der Ausloeser war
  keiner. Lehre fuer die Abnahme: NIE einen Einzelframe bewerten, immer
  den Verlauf ueber die Moment-Lebensdauer.
  NICHT LIVE VERIFIZIERT: ob MediaPipe die Schub-Hand im echten Clip
  zuverlaessig findet, zeigt erst der naechste Render.
- **v173 blurin ist der DRITTE verdeckende Effekt.** Der v172-Render
  (Stempel-Job 34dcd388) zeigte "EXPLODE" unveraendert hinter der Person -
  und der 4s-Frame war PIXEL-IDENTISCH mit dem Vorjob, obwohl 8s sich
  komplett unterschied. Das bewies: der Moment laeuft durch einen Pfad,
  den keiner der Riegel beruehrt. Es ist `blurin`: sein grosses Wort wird
  VOR dem Person-Overlay gezeichnet (`comp = person * alpha_p + ...`) und
  steht damit genauso hinter der Person wie behind und ground. Genau
  diesen fx hatte die KI-Regie fuer "EXPLODE" gewaehlt - in beiden Jobs
  gleich, daher die identischen Pixel. Alle drei Riegel (Wort-Riegel
  v172, Anim-Riegel v169/v170, Cache-Riegel parse_regie) kennen jetzt
  blurin. Ein neutrales Wort ("CHAPTER") behaelt den blurin-Look - der
  Themenwechsel-Effekt ist fuer ruhige Woerter gebaut und bleibt.
  Damit sind ALLE personengebundenen fx abgedeckt; die Liste der
  verdeckenden Effekte steht jetzt an einer Stelle im Kopf: behind,
  ground (mit Person), blurin.
  Der 8s-Moment des v172-Renders ist abgenommen: Spalte frei (+0.05 W
  Luecke), Seite wechselt, kein Fenster-Kontakt.
- **v172 Sichtbarkeit haengt am WORT, nicht an der Anim-Wahl.** Erster
  eindeutig belegter Neu-Render (v171-Stempel, Job 4ab2692c): "EXPLODE"
  stand IMMER NOCH hinter der Person. Der v169/v170-Riegel prueft die
  GEWAEHLTE Animation - waehlt die KI-Regie ein anderes Anim (oder keins,
  oder sind Animationen im Job aus), feuert er nie. Ob ein Wort eine
  sichtbare Handlung IST, sagt das Wort selbst: `anim_for(txt)` in
  _VISIBLE_ANIM -> nie behind/ground, unabhaengig von der Regie-Wahl und
  von `effects.anim`. Der Riegel sitzt ausserhalb des Anim-Blocks.
  RANGFOLGE GEKLAERT (dokumentierte v99-Regel): sagt der Satz die
  HANDLUNG ("boom they explode"), gewinnt sie auch gegen intent - eine
  ORTS-Ansage ("right BEHIND me") hat kein Aktionsverb und bleibt dadurch
  automatisch Gesetz. Der v169-Test hatte das falsch herum erwartet
  (intent-behind trotz Aktionswort) und wurde korrigiert.
  ENTWARNUNG "is" (14s): KEIN Fehler. Die Frames bei 14.5/14.8 zeigen
  "is this" - der Flow-Chunk waechst wortweise, der Clip endet mitten im
  Satz. Das Standbild hat getaeuscht. Der Orphan-Riegel (v169/v170)
  bleibt fuer den echten Fall (Einzelwort nach Pause), hier war keiner.
  FEINSCHLIFF Collage: die kleine Spalte beginnt jetzt an fester Kante
  und waechst nach AUSSEN - die alte Form (rechte Kante minus Wortbreite)
  schob breite Woerter in die Treppe (gemessen: 'and i' lag 0.016
  Spiegelbreiten AUF 'can'). Neue Luecke: +0.052 W.
  ABNAHME des gestempelten Renders sonst: BEHIND Me sauber (Gold-Akzent
  neben dem Kopf), Seiten wechseln (rechts/links-Collage 6s links, 8s
  rechts, 10s rechts), Sprechpausen korrekt textfrei.
- **v171 Herkunft in Datei und Dateinamen.** Vier byte-identische "neue"
  Renders in Folge (MD5 gleich) - und weder Ismet noch der Support konnten
  sehen, WELCHER Job eine heruntergeladene Datei erzeugt hat: jeder
  Download hiess "DouchkoVE_Captions.mp4", der Browser zaehlte nur _1/_2
  hoch. Jetzt:
  1. Der Server stempelt Build + Job-ID in die Render-Umgebung
     (DVE_JOB_TAG), die Engine schreibt sie in die MP4-Metadaten
     (comment-Feld). `ffprobe` zeigt sofort, aus welchem Render und
     welchem Build eine Datei stammt - auch bei Dateien, die ein Kunde
     per Mail schickt.
  2. Der Download-Name traegt die Job-ID: DouchkoVE_<jobid>.mp4. Zwei
     Downloads desselben Jobs sind sofort als solche erkennbar.
  Desktop (gui.py) unveraendert: ohne DVE_JOB_TAG kein Metadaten-Feld.
  Offen bleibt die eigentliche Frage, WARUM Ismets Downloads viermal
  dieselbe Datei waren (Library-Doppel-Download, nie gestarteter Job oder
  haengendes Deploy) - genau das macht dieser Stempel ab jetzt sichtbar.
- **v170 Die v169-Fixe griffen im falschen Pfad** (am zweiten echten Render
  belegt: Collage-Spalte gedockt, aber "is" und "EXPLODE" unveraendert).
  EHRLICHE URSACHEN, beide reproduziert:
  1. Ismets Job lief mit Dichte 'durchgehend'. Dort (und im Hook-Intro)
     rendert JEDE Gruppe - der Orphan-Riegel sass aber nur im
     satz_offen-Pfad. Lokal nachgestellt: mit 'durchgehend' erschien das
     einsame "is" wieder. Der Riegel steht jetzt VOR den Pfad-Weichen
     (v159-Lehre: ein Schutz, der nicht an der immer laufenden Stelle
     haengt, ist keiner): ein Ein-Wort-Haeppchen (<=4 Zeichen) nach einer
     Pause >=1.2 s faellt in ALLEN Dichte-Pfaden weg. intent/user_pick
     bleiben unantastbar.
  2. EXPLODE kam als WAND-Text (fx ground, szene wand) aus der
     Vision-Regie - der v169-Riegel prueft nur 'behind'. Szenen-Text steht
     genauso HINTER der Person. Jetzt: sichtbare Anim + behind ODER ground
     -> outline. AUSNAHMEN mit Absicht: auf B-Roll bleibt ground (keine
     Person, die verdeckt), und die woertliche Ansage (intent) bleibt
     Gesetz.
  Beweis (Selftest): durchgehend + "is" nach 3.5 s Pause -> kein Plan mehr;
  EXPLODE als Wand-Text -> outline + explosion; B-Roll-Boden-Text bleibt
  ground.
  NICHT LIVE VERIFIZIERT: das Ergebnis am echten Clip sieht Ismet nach dem
  Deploy - dritter Anlauf an diesem Video, diesmal mit dem Pfad, den sein
  Job wirklich nimmt.
- **v169 Drei Befunde aus Ismets ECHTEM Video behoben** (erste Abnahme am
  fertigen Produkt-Render, 15s-Testclip; "behind me" hat er ausdruecklich
  als gut abgenommen).
  1. AKTIONSWORT NIE HINTER DER PERSON - IN ALLEN PFADEN. "EXPLODE" stand
     hinter dem Sprecher, der Koerper verdeckte die Punchline (4s im Video).
     Der Riegel existierte im Cache-Pfad (parse_regie) und im Ansage-Pfad -
     kam die Animation aber aus der Auto-Wahl in build_plans oder der
     KI-Frischwahl, lief er ins Leere. Derselbe Fehlertyp wie v159: ein
     Schutz, der nicht an der immer laufenden Stelle haengt, ist keiner.
     Jetzt in build_plans: sichtbare Anim + fx 'behind' -> 'outline'.
     Die ausdrueckliche Ansage ("behind me", intent) bleibt Gesetz.
  2. KEIN EIN-WORT-REST NACH EINER SPRECHPAUSE. Ein einzelnes "is" stand
     3.5 s nach dem Keyword allein unten im Bild wie ein Bug (14s im
     Video). Ursache: die Satz-Fortsetzung (satz_offen) kannte keine
     Pausen-Grenze. Jetzt: eine Pause ueber 1.2 s beendet den sichtbaren
     Satz, und ein Ein-Wort-Haeppchen (<=4 Zeichen) traegt als eigener
     Moment nichts - Stille ist besser. Testbau mit Bedacht: unter 0.35 s
     schluckt die Keyword-Phrase die Woerter selbst, die ERSTE Folgegruppe
     frisst die Atempause (gewollt, seit v-alt) - der Test prueft die
     zweite.
  3. DIE KLEINE COLLAGE-SPALTE DOCKT AN DER TREPPE AN. Bei seite 'rechts'
     stand sie an der fernen Spiegel-Aussenkante: zwischen Treppe ("can
     push them") und Spalte ("and i just") klaffte ein Loch von ~0.15
     Spiegelbreiten, die Spalte wirkte verwaist und hing an Ismets hellem
     Fenster (8s im Video). Jetzt startet sie an der Treppen-Innenkante
     (gemessene Luecke danach: -0.016 W, also buendig).
  ABNAHME-NOTIZEN zum selben Video, KEIN Fehler: die Caption-Luecke bei
  11-14s ist eine echte Sprechpause (gemessen -64 dB gegen -20 dB beim
  Sprechen). Seiten-Abwechslung rechts/links/rechts/links vorhanden.
  NICHT LIVE VERIFIZIERT: die drei Fixes sind am Selftest belegt, das
  Ergebnis am echten Clip sieht Ismet nach dem Deploy.
- **v168 Die Seite ist eine Entscheidung, kein Wuerfelwurf.** Ismets Befund,
  dritter Anlauf: "die captions sind immer auf der linken seite, egal was
  passiert" - und die Anweisung, bei Unsicherheit zu FRAGEN statt zu raten.
  Diesmal am eigenen Render nachgemessen (Selftest-Clip, Querformat,
  DBG-Instrumentierung in spot()). DREI Ursachen, alle belegt:
  1. DER SEITEN-WURF. `_mix01(g0*11) >= 0.55` wuerfelte pro Chunk
     unabhaengig: nur ~40-45 % rechts, der erste Chunk IMMER links
     (_mix01(0) = 0.0), auf typischen Chunk-Ketten gemessen 3 von 12
     rechts. Lange Links-Ketten waren der Normalfall. Jetzt traegt
     spot_state die Seite: jeder Block WECHSELT, rund jeder vierte bleibt
     deterministisch stehen, die Startseite haengt am Video-Seed.
     Re-Render ergibt dasselbe Bild.
  2. DER TIEBREAKER VERLOR GEGEN DIE UNRUHE-KARTE. Wunschseite 0.55,
     Unruhe 1.6: steht der Sprecher rechts der Mitte und ist die Wand links
     ruhig (exakt Ismets Testbild: Betonwand links, Fenster rechts), ist
     die ruhigste Stelle IMMER links - gemessen wx=0.7 W, Ergebnis
     0.098 W. Ein einzelner Toleranzwert kann das nicht trennen: Unruhe
     (bis ~1.4) darf die Regie nicht stoppen, Atemluft/Gesicht (ab ~1.1)
     schon - die Bereiche ueberlappen. Deshalb entscheidet jetzt der
     MOTIV-Anteil (nur Gesicht + Atemluft) allein: die Wunschseite gilt,
     wenn ihre beste Stelle genauso gesichtsfrei ist wie die beste Stelle
     insgesamt. Die Unruhe-Karte waehlt nur noch die Position INNERHALB
     der Seite. Das Ausweichen vor der Person (v143) bleibt dadurch
     unangetastet - steht sie auf der Wunschseite, faellt die Seite zurueck.
  3. ZWEI FALLEN BEIM UMBAU, beide vom Selftest gefangen: (a) die
     Seiten-Suche wich auf eine Zeile UEBER dem Kopf aus (motivfrei, aber
     ein Lower-Third-Block stand am oberen Rand, nur um die Seite zu
     behaupten) -> die Suche bleibt jetzt in der Wunschzonen-Hoehe
     (+-0.18 H). (b) Innerhalb der Seite zog die Unruhe den Block an die
     Fensterkante zur Bildmitte ("rechts" sass bei 0.505 W, sah aus wie
     mittig) -> Rangfolge Motiv, dann Naehe zur Wunschmitte, dann Kosten.
  BEWEIS am echten Render (Selftest-Clip, 960x540): vorher Tinten-
  Schwerpunkte 0.51/0.50/0.50/0.29/0.27/0.27 (zweite Haelfte klebt links),
  nachher 0.52/0.50/0.49/0.68/0.72/0.71 (wechselt). Frame-Streifen an
  Ismet geliefert. Neuer Selftest: beide Seiten kommen vor trotz ruhiger
  linker Bildhaelfte, keine Einseiten-Kette ueber 3, deterministisch,
  v143-Ausweichen unveraendert gruen.
  TESTKORREKTUR: die v155/v153-Quelltext-Checks pinnten `_motiv += 1.0`
  woertlich; _motiv traegt jetzt die echten Gesichts-/Atemluft-Kosten.
  Die Invariante dahinter (Unruhe nie im Motiv) prueft der Test weiter.
  EINSCHRAENKUNG: verifiziert am Selftest-Clip; Ismets Testclip aus dem
  Screenshot lag hier nicht vor. Die Ketten-Statistik haengt von den
  echten Chunk-Indizes ab.
- **v167 Eine gehaltene Geste ist EINE Ansage.** Ismets Befund nach v166:
  "immernoch" links, mit Screenshot. Der Screenshot zeigt die Ursache: der
  Sprecher haelt den Arm ueber viele Momente in dieselbe Richtung, und die
  Captions sitzen exakt dort. Das ist die Zeige-Regie, die tat, was gebaut
  war - die HAND-Erkennung war bewusst absolut geblieben ("eine Geste ist
  eine Ansage"). Haelt jemand die Pose aber ueber das halbe Video, wird aus
  einer Ansage fuenfzehn, jedes Ziel ueberstimmt die Seiten-Abwechslung, und
  alles klebt auf einer Seite. Gleicher Denkfehler wie beim Blick (v166),
  eine Ebene tiefer.
  FIX: `_ziel_dedupe()` am Ende von `zeige_ziele()`. Aufeinanderfolgende
  Ziele am praktisch selben Ort (x-Abstand unter 0.12 W) sind EINE Gruppe;
  von jeder Gruppe bleiben die ersten zwei Momente, danach ist die Ansage
  erfuellt und die normale Abwechslung uebernimmt. Ein neues Ziel woanders
  beginnt eine neue Gruppe: wer erst links und dann rechts hinzeigt, bekommt
  beides. Einzelne, verschiedene Ziele bleiben alle erhalten.
  Beweis (Selftest): 6 gehaltene Momente -> nur die ersten 2 tragen das
  Ziel; links-dann-rechts -> 2 + 2; drei verschiedene Einzelziele -> alle 3.
  NICHT LIVE VERIFIZIERT: ob SEIN Testclip damit wieder wechselnde Seiten
  zeigt, sieht Ismet erst nach dem Deploy. Naechste Messstation bleibt die
  Log-Zeile "Pointing direction: X pointing, Y gaze".
- **v166 Blick ist ABWEICHUNG, nicht Haltung.** Ismets Befund nach v160:
  "es ist immer noch links die captions". EHRLICHE URSACHE: die Blick-Regie
  aus v160 arbeitete mit einer ABSOLUTEN Schwelle (0.35 Augenabstaende
  Nasenversatz). Die haelt nur Frontal-Sprecher auf. Wer sein Video mit
  leicht seitlich stehender Kamera aufnimmt - der Normalfall bei
  Selfie-Setups - liegt in JEDEM Moment darueber. Ergebnis: jeder Moment
  bekam dasselbe Blick-Ziel, das Ziel ueberstimmt Wunschzone und
  Seiten-Abwechslung (so gebaut, fuer echte Gesten richtig), und ALLE
  Captions klebten auf einer Seite. Die v160-Pruefung hatte nur Frontal-
  und Dreh-Momente einzeln getestet, nie eine DAUERHALTUNG ueber mehrere
  Momente.
  FIX: `_blick_targets()` sammelt erst alle Kopfdrehungen der Momente und
  filtert dann gegen die GRUNDHALTUNG des Sprechers (Median der Drehungen):
  - Haltung dauerhaft +0.5 -> Median +0.5, Abweichung ~0 -> NULL Ziele.
  - Frontal-Haltung, EIN bewusster Blick +0.7 -> genau der zaehlt.
  - Haltung +0.5, ein Moment dreht WEITER auf +1.0 -> genau der zaehlt.
  - Drehung ZURUECK zur Kamera -> kein Ziel (wer zur Kamera schaut, meint
    keinen Ort im Bild; die Abweichung muss in die Blickrichtung gehen).
  - Unter 3 Messungen gibt es keinen brauchbaren Median -> dann zaehlt nur
    eine wirklich deutliche Drehung (0.55).
  Zeigen (Hand) bleibt unveraendert absolut - eine Zeigegeste ist eine
  Ansage, keine Haltung.
  Beweis im Selftest: alle fuenf Faelle einzeln geprueft, dazu die
  v160-Regression unveraendert gruen (Frontal/gedreht/Gegenrichtung).
  NICHT LIVE VERIFIZIERT: ob damit SEIN Video wieder wechselnde Seiten
  zeigt, sieht Ismet erst am echten Render nach dem Deploy. Wenn es danach
  immer noch klebt, ist die naechste Messstation der Job-Log (Zeile
  "Pointing direction: X pointing, Y gaze") - steht dort weiter eine hohe
  Gaze-Zahl, liegt es NICHT an der Haltungs-Filterung.
- **v164 Gratis-Teaser wieder ENTFERNT** (Ismets Entscheidung: die Vorschau
  kostet ihn API + Rechenzeit, auch wenn beim Kunden 0 Credits stehen).
  Sauberer Revert des v163-Commits: Endpoint `/api/teaser/{jid}`, Teaser-Modus
  im Worker, no_charge-Sperren, Stundendeckel, UI-Knopf und die v163-Tests
  sind komplett raus. Die v157-Testkorrektur (Zaehlung >= 2 statt == 2) ist
  mit zurueckgedreht und stimmt wieder woertlich, weil die dritte Stelle weg
  ist. Stand: 1020/1020 Tests.
- **v162 ZWEI-SPRECHER-REGIE: der Text folgt dem, der gerade redet.** Sind
  mehrere Personen im Bild, springt die Caption auf die Seite des aktiven
  Sprechers. In einem Interview sah man dem Bild bisher nie an, wem der Satz
  gehoert.
  Das Zuordnungs-Signal lag seit v96 fertig da: `track_faces` waehlt ueber
  die MUNDBEWEGUNG das aktive Gesicht (`_active_index`), und `face_pos`
  liefert genau dessen Position. Genutzt hat das bisher nur die KAMERA - die
  Captions sassen unabhaengig davon in der breitesten Luecke.
  DER ENTSCHEIDENDE PUNKT: die Sprecher-Naehe ist KEIN Tiebreaker. Die
  vorhandene Wunschseite (`wunsch_x`) wirkt nur an Stellen ohne
  Motiv-Beruehrung - neben zwei Personen ist praktisch JEDE Stelle beruehrt,
  der Sprecherwechsel waere folgenlos geblieben. Das ist derselbe Fehler wie
  in v153, nur an anderer Stelle. Die Sprecher-Naehe ist deshalb ein eigener
  Kosten-Term mit Gewicht 1.3, der immer wirkt. Er liegt unter der
  Gesichtssperre (ab 2.5): der Text landet NEBEN dem Sprecher, nie auf ihm.
  ZWEITE STELLE: `_free_x_multi` (Keyword-Sprites im Querformat) waehlte die
  BREITESTE passende Luecke. Bei zwei Personen ist die fast immer dieselbe,
  egal wer redet. Jetzt gewinnt die NAECHSTE Luecke am Sprecher, und der
  Mittelpunkt wird darin zu ihm hin gezogen. Passt nirgends etwas hinein,
  bleibt die alte Regel - eine zu enge Luecke neben dem Sprecher wuerde ihn
  anschneiden.
  EINRASTEN STATT MITTELN: `face_pos` ist ueber 41 Frames geglaettet und
  liegt beim Sprecherwechsel eine Weile ZWISCHEN beiden Personen. Ohne das
  Einrasten auf das naechstgelegene ERKANNTE Gesicht landet der Text genau
  in der Mitte, wo niemand sitzt. Dazu eine Hysterese: gewechselt wird erst,
  wenn das andere Gesicht deutlich naeher ist, sonst flackert der Text bei
  jedem Erkennungs-Zittern hin und her. Ein echter Sprecherwechsel BRICHT
  die Hysterese der Platzierung (wie ein Seitenwechsel: das ist Regie, kein
  Zittern).
  BEI EINER PERSON passiert nichts. Dort ist "der Sprecher" keine
  Information, und die vorhandene Ausweich-Logik ist die bessere Wahl.
  BEWEIS (Selftest, 1920x1080, Personen bei 0.24 W und 0.74 W): redet die
  linke Person -> Blockmitten 0.255 / 0.247 W. Redet die rechte -> 0.747 /
  0.753 W. Abgeschaltet: identische Positionen fuer beide Sprecher.
  Abschaltbar ueber `effects.caption_sprecher`.
  NUR AUF SYNTHETIK GEPRUEFT: die Sprecher-Zuordnung selbst (Mundbewegung im
  echten Gespraech, schnelle Wechsel, Zwischenrufe) ist hier mit gesetzten
  Positionen getestet, nicht an echtem Interview-Material.
- **v161 OBJEKT-ANKER: die Caption dockt am Gegenstand an.** Sagt jemand
  "dieses Glas hier", setzt sich der Text NEBEN das Glas und bleibt daran
  kleben, auch wenn die Kamera schwenkt.
  ZWEI STUFEN, BEWUSST GETRENNT: GPT-5-Vision sagt EINMAL pro Moment, WAS
  gemeint ist (Objektname, grober Mittelpunkt, Groesse). Wohin es wandert,
  misst Optical Flow - jeden Frame, lokal, ohne einen einzigen Token. Ein
  Vision-Aufruf je Frame waere weder bezahlbar noch stabil: das Modell raet
  bei jedem Frame ein paar Pixel anders und der Text wuerde zittern.
  DER ANKER UEBERLEBT DEN REGIE-CACHE (`parse_regie` liest ihn, der
  Cache-Schreiber legt ihn ab). Ohne das waere er beim ZWEITEN Render
  desselben Videos weg - genau der Fehler, der in v159 an anderer Stelle
  gefunden wurde. Beim zweiten Render kostet der Anker dadurch nichts mehr.
  NEBEN, NICHT DRAUF: eine Caption quer ueber dem Gegenstand verdeckt genau
  das, worum es geht. Bevorzugt darunter (Bildunterschrift-Logik), sonst
  darueber, sonst gar nicht.
  DER WICHTIGSTE FUND: die Vorwaerts-Rueckwaerts-Probe. Der Status von
  `calcOpticalFlowPyrLK` ist bei einem Schnitt WERTLOS - LK meldet keinen
  Misserfolg, sondern rastet auf einer aehnlich aussehenden Stelle ein und
  liefert eine kleine, voellig plausible Verschiebung. Im Test: das Objekt
  sprang 200 px, LK meldete -3.6 px und "erfolgreich". Der Sprung-Riegel lief
  damit ins Leere. Ein Punkt zaehlt jetzt erst, wenn er RUECKWAERTS wieder
  dort landet, wo er herkam (Median-Flow-Standard, Schwelle 1 px). Danach:
  Schnitt erkannt, Spur beendet, dx = 0.0.
  WEITERE SPERREN: unter 8 Startpunkten kein Anker (ohne Ecken ist der Median
  Rauschen, und Rauschen als Objektbewegung ist schlimmer als nichts). Eine
  verlorene Spur FRIERT den Stand ein, sie springt nicht auf null zurueck -
  ein Text, der bei jeder Verdeckung an seine Startstelle huepft, ist
  schlimmer als einer, der kurz stehen bleibt. Halluzinierte Boxen
  (ausserhalb des Bildes, ueber 0.60 Bildbreiten) werden verworfen. Auf
  B-Roll kein Anker - dort gehoert der Text zur Szene, nicht zu einem
  Gegenstand darin.
  KEINE DOPPELBEWEGUNG: ein verankerter Text folgt NICHT zusaetzlich dem
  Gesicht (`track_offset`) und bekommt die Szenen-Verankerung nicht obendrauf
  (`scene_shift`) - die Objektspur enthaelt die Kamerafahrt bereits, sonst
  wuerde jeder Schwenk zweimal angewandt.
  BEWEIS (Selftest): Tracker misst 20.0 / 15.0 px bei echten 20 / 15.
  Platzierung 1080x1920, Objekt bei 0.28 W / 0.55 H -> Text bei 0.354 W /
  0.682 H (halbe Texthoehe 0.070 H, also sauber darunter). Ohne Anker
  0.500 W / 0.450 H.
  FEHLER GEFUNDEN UND BEHOBEN: die Platzierung prueft `arr` - der Look
  'outline' legt sein Bild aber in `o_arr`. Der Anker wurde gesetzt und nie
  angewandt, der Text blieb in der Bildmitte stehen. Nur im Selftest
  aufgefallen, nicht am Code.
  NUR AUF SYNTHETIK GEPRUEFT: der Tracker lief hier auf gebauten
  Schachbrett-Frames, nicht auf echtem Material. Wie gut GPT-5-Vision ein
  Objekt im echten Bild verortet, sieht Ismet erst live.
  Abschaltbar ueber `effects.caption_objekt`.
- **v160 ZEIGE-REGIE: die Caption landet, wohin der Sprecher zeigt.** Ismets
  Vorgabe: das Tool muss innovativ sein, sonst hat es am Markt keine Chance.
  Das Material dafuer lag seit v101j im Haus (MediaPipe-Hand-Landmarker) bzw.
  seit v96 (Gesichts-Keypoints) - benutzt wurde es nur fuer Occlusion und
  Kamera. Die Platzierungs-Regie hat es nie gelesen.
  Jetzt zwei Quellen, in dieser Rangfolge:
  1. ZEIGEN. Zeigefinger gestreckt, die anderen eingerollt. Gemessen wird
     ueber die Distanz zum HANDGELENK (eine gestreckte Spitze ist weiter weg
     als ihr eigenes Mittelgelenk) - unabhaengig davon, wie die Hand im Bild
     gedreht liegt. Ein Vergleich gegen die Senkrechte waere das nicht.
     Die Fingerachse Grundgelenk -> Spitze ist der Strahl, das Ziel liegt auf
     halbem Weg zum Bildrand.
  2. BLICK. Ohne Zeigen verraet die Kopfdrehung die Richtung: die Nasenspitze
     wandert relativ zur Augenmitte in die Blickrichtung, Massstab ist der
     Augenabstand. Erst ab 0.35 Augenabstaenden - wer in die Kamera spricht,
     meint keinen Ort im Bild.
  Beides ist reine BILDMESSUNG, kein API-Ruf, kein Modell-Rat. Gemessen wird
  nur an den gewaehlten Momenten, drei kleine Frames je Moment, nicht ueber
  das ganze Video.
  BEWUSSTE SPERREN: eine offene Hand ist eine Geste, kein Zeigen (sonst
  schiebt jedes Herumfuchteln die Captions durchs Bild). Ein Finger Richtung
  Kamera hat im Bild kein Ziel - dann lieber keines als ein geratenes.
  DAS GESICHT BLEIBT TABU. Das Zeige-Gewicht erreicht 2.2, eine
  Gesichtsberuehrung kostet ab 2.5. Zeigt jemand auf seinen eigenen Kopf,
  landet der Text daneben, nicht darauf - das ist kein erfuellter
  Zeigefinger, sondern ein Fehler.
  BEWEIS (Selftest, 1080x1920, Gesicht bei 0.50 W / 0.35 H, kurze Chunks):
  nach links gezeigt -> Blockmitten 0.247 / 0.230 W, nach rechts gezeigt ->
  0.647 / 0.674 W. Ohne Ziel 0.336 / 0.674 W. Die Hoehe zieht mit: 0.17 H
  ohne Ziel, 0.72 H bei einem Ziel bei 0.80 H.
  EHRLICHE GRENZE: ein BREITER Textblock hat im Title-Safe kaum seitlichen
  Spielraum - gemessen 0.773 W Blockbreite bei 0.84 W nutzbarer Flaeche, da
  verschiebt keine Geste mehr etwas. Die Zeige-Regie wirkt dort, wo Platz
  ist. Das ist eine Eigenschaft der Bildflaeche, keine Schwaeche der Messung.
  Abschaltbar ueber `effects.caption_zeige`.
  NUR AUF SYNTHETIK GEPRUEFT: die Landmark-Auswertung selbst wurde hier mit
  gebauten Hand-/Gesichts-Koordinaten getestet, nicht mit echtem Videomaterial
  einer zeigenden Person. Wie zuverlaessig MediaPipe eine echte Zeigegeste
  liefert, sieht Ismet erst live.
  TESTKORREKTUR: der v130-Admin-Test pinnte die Build-Kennung woertlich
  (`DVE_BUILD = 'v158-preis'`) und schlug damit bei JEDER Version fehl. Er
  prueft jetzt per Regex, dass ueberhaupt eine Kennung gesetzt ist - das war
  eine Pruefung der Test-Pflege, nicht des Servers.
- **v159 Die Ansage gilt jetzt wirklich immer.** Ismets Wunsch: "die captions
  muessen auf jedenfall passen, was auch gesagt wird". Ein Audit ueber die
  semantische Regie hat drei echte Loecher gefunden, alle drei sind zu.
  1. ORTSANSAGE IN ALLEN PFADEN. `_speech_intent` hatte bis v158 GENAU EINE
     Aufrufstelle: innerhalb von `ai_direct`. Die laeuft aber nicht ohne
     `OPENAI_API_KEY`, nicht bei API-Ausfall und nicht, wenn der Regie-Cache
     greift. Der Cache ist der NORMALFALL beim zweiten Render desselben
     Videos. In all diesen Faellen wurde "der Beweis steht HINTER MIR"
     komplett ignoriert, obwohl CLAUDE.md die Ansage als Gesetz fuehrt.
     `_self_ref_intent` stand aus genau diesem Grund schon an der immer
     laufenden Stelle; `_speech_intent` steht jetzt daneben. Ein Riegel
     (`if fx_map[i].get('intent'): continue`) verhindert, dass der KI-Pfad
     denselben Treffer doppelt ins Log schreibt.
  2. VERBFORMEN. `ANIM_HINTS` ist in der 3. Person Singular geschrieben
     ('scheitert', 'zittert'), ein Transkript sagt genauso oft 'scheitern'
     oder 'zitterten'. GEMESSEN: 39 von 52 geprueften Verbpaaren verloren
     ihre Animation, sobald die -en-Form kam. Beide Seiten werden jetzt ueber
     `_anim_stamm()` auf den Wortstamm gekuerzt (Endung nur abschneiden,
     solange >= 4 Zeichen stehen bleiben). Nebenbefund derselben Stelle: das
     blinde `startswith` gilt jetzt erst ab 6 Zeichen Stichwortlaenge, denn
     'fall' schlug in "FALLS du aufgibst" an und kippte den Block samt
     Sturz-Sound, obwohl im Satz nichts faellt.
  3. VERNEINUNG. "Die Mieten steigen NICHT" bekam dieselbe Aufwaerts-Animation
     wie "Die Mieten steigen", samt Aufwaerts-Sound. Das Video sagte damit das
     Gegenteil des Satzes. `_hat_negation()` (Wortliste DE+EN) verwirft die
     Animation im verneinten Satz. Lieber keine als eine falsche.
  BEWEIS (ohne API-Key, Heuristik-Pfad): "hinter mir" -> fx `behind`,
  intent=True. "auf dem Boden" -> fx `ground`, szene `boden`, lage `liegend`.
  "Die Firmen scheitern" -> `bruch` (vorher None). "Falls du aufgibst" -> None
  (vorher `sturz`). "Die Mieten steigen nicht." -> None, "Die Mieten steigen."
  -> `anstieg`.
  EHRLICH: das Audit hat mehr gefunden, als hier drin ist. Offen bleiben
  "links von mir"/"on my left" (wird nirgends erkannt), deutsche Zahlformate
  (1.500 wird als 1,5 gelesen), und ohne API-Key ist die Keyword-Wahl bei
  englischen Transkripten kaum brauchbar (Grossschreibungs-Heuristik). Das
  sind eigene Baustellen, keine Nebenfixes.
  Ebenfalls ehrlich: "Die Preise fallen stark." liefert jetzt `schub` statt
  `sturz`, weil 'stark' in `ANIM_HINTS` frueher steht als 'fallen'. Die
  Reihenfolge der Liste ist damit selbst eine Regie-Entscheidung, die noch
  niemand getroffen hat.
  TESTS: 976/976 logic gruen, Renders 7/1/5/2, GUI gruen.
- **v158 Der Preis am Render-Button kennt 4K.** Ismets Befund: "wenn 4k
  angewaehlt ist, steht immer noch 1 credit". Der Preis wurde EINMAL beim
  Datei-Auswaehlen gerechnet (`Math.ceil(dur/60)`) und kannte die
  Aufloesungswahl gar nicht - der Server bucht aber das Doppelte ab.
  Neu: `updateRenderCost()` laeuft bei jeder Aenderung der Aufloesung.
  Sie kennt auch die QUELLE: der Server berechnet 4K nur ab 1440p kurzer
  Kante, also darf der Button bei einer kleineren Quelle auch nicht das
  Doppelte anzeigen. Dann steht dort der einfache Satz plus ein Hinweis in
  Akzentfarbe, warum 4K hier nicht greift. Client- und Server-Grenze sind
  im Selftest gegeneinander geprueft.
- **v157 4K als dritte Aufloesungsstufe** (Ismets Wunsch: "Mach die 4k neben
  dem 1080p"). Statt eines eigenen Quality-Feldes steht 4K jetzt in
  derselben Zeile wie 720p und 1080p, beschriftet mit dem Aufpreis.
  DABEI EIN LOCH GESCHLOSSEN: die UI schickt damit die HOEHE (2160) statt
  `quality: 4k`. `_will_uhd` prueft nur auf `quality` - 4K waere gerendert,
  aber nur der einfache Satz berechnet worden. Beide Wege zaehlen jetzt.
  Zweitens: wenn die Quelle 4K nicht hergibt, wurde bisher nur `quality`
  aus den Overrides entfernt. Die HOEHE blieb auf 2160 stehen, die Engine
  haette weiter gross gerechnet und der Kunde den einfachen Satz gezahlt.
  Jetzt faellt auch die Hoehe auf 1080 zurueck.
  Die Abbuchung selbst wurde gegengeprueft: 90 s kosten normal 2 Credits,
  in 4K 4 Credits.
- **v156 Gemessene Buendigkeit ist eine Tendenz, keine Schablone.** Ismets
  Einwand auf v155: "Das Video war aber auch nicht so, dass da staendig die
  Captions auf der linken Seite waren." Stimmt. Auch ein Vorbild, dessen
  linke Kanten im Schnitt weniger streuen, setzt einzelne Bloecke anders -
  sein zweites Referenzvideo misst sogar korrekt 'frei'. Ein gemessenes
  'links' auf ALLE Chunks anzuwenden macht aus einer Tendenz eine Schablone.
  Rund die Haelfte der Bloecke folgt jetzt der wechselnden Bildseite statt
  der Messung, deterministisch ausgewaehlt. Mit einem Drittel (Schwelle
  0.66) wechselte im echten Render nur EIN Block von sechs.
  Eine ausdrueckliche Nutzerwahl im Regler bleibt absolut.
  BEWEIS am echten Render, dieselbe linksbuendige Referenz: Blockmitten
  0.27 bis 0.77 W (Spanne 0.50) statt 0.27 bis 0.53 W (Spanne 0.26).
  TESTKORREKTUR: der v153-Test setzte `caption_align` und mass die
  BILDSEITE - seit v155 sind das getrennte Schluessel, der Test prueft jetzt
  `caption_seite`.
- **v155 Buendigkeit ist NICHT die Bildseite.** Ismet: "es ist immer noch
  alles auf der linken Seite im Video" - obwohl v153 die Variation gebaut
  hatte und sie im Testrender messbar lief (Blockmitten 0.33 bis 0.81 W).
  Ursache: in SEINEM Konto liegt eine gelernte Referenz, die 'ausrichtung:
  links' misst. v153 hat daraus BEIDES gemacht:
    BUENDIGKEIT - stehen die Zeilen linksbuendig zueinander? Das misst die
      Referenz, und das gehoert zum Stil.
    BILDSEITE   - sitzt der Block links oder rechts im Frame? Das soll
      variieren.
  Zwei verschiedene Dinge, ein Schalter. Getrennt: `caption_align` ist die
  Buendigkeit (aus der Messung), `caption_seite` die Bildseite (nur aus
  ausdruecklicher Nutzerwahl, sonst 'auto').
  ZWEITER FEHLER an derselben Stelle: der Seiten-Tiebreaker prueft auf
  `_motiv <= 0`, aber `_motiv` enthielt die Zwischensumme INKLUSIVE
  Unruhe-Karte - die liefert an jeder Stelle einen Beitrag, die Bedingung war
  also praktisch nie erfuellt. `_motiv` zaehlt jetzt nur noch
  Gesichts-Beruehrungen.
  EHRLICH: mit linksbuendiger Referenz bleibt die Streuung kleiner (gemessen
  0.27 bis 0.53 W) als ohne (0.33 bis 0.81 W) - ein linksbuendiger Block
  kann nicht so weit nach rechts wandern wie ein rechtsbuendiger.
- **v154 Schriftgroesse + Keyword-Variation** (Ismets dritter Befund:
  "Schriften zu gross. Keywords immer gleiche Animation und Optik.")
  - **DER FLIESSTEXT HING AM SCHLUESSELWORT.** `caption_scale` skalierte nur
    `sz_k`; `sz_n` wurde daraus ueber die Hierarchie abgeleitet. Gemessen
    wird aber die PUNCHLINE des Vorbilds (96. Perzentil, im zweiten
    Referenzvideo das riesige Schlusswort mit 0.1836 H). Dieser Wert auf den
    Fliesstext angewandt machte ihn 68 % groesser: 76 -> 128 px. Der
    Fliesstext hat jetzt einen EIGENEN gemessenen Faktor
    (`caption_scale_klein` aus `klein_hoehe`), gedeckelt auf 1.30.
    Ergebnis: Haus 65 px, mit Referenz 85 px statt 128 px.
  - **HAUSMASS nochmal runter**: 0.088 -> 0.076 em Schluesselwort, 0.040 ->
    0.034 em Fliesstext. Der Punch-Faktor musste zum zweiten Mal mit
    (1.95 -> 2.25), sonst rutscht der Randabfall aus v152 unter die
    Bildbreite und ist nicht mehr zu sehen.
  - **KEYWORDS STANDEN STILL.** `anim_for()` findet nur etwas, wenn das Wort
    oder sein Satz einen Hinweis traegt ("faellt", "explodiert"). Bei
    normalen Keywords traf gemessen KEIN Hinweis, `p['anim']` blieb None -
    der grosse Moment stand einfach da. Neu: eine Rotation
    bedeutungsneutraler Animationen als Fallback (gewicht, puls, schweben,
    fokus, welle, enthuellen, schub, neon). Bewusst NICHT sturz/knall - die
    muessen zum Wortsinn passen.
  - GEAENDERTE ERWARTUNG (kein Testkosmetik-Fix): der v143-Test verlangte,
    dass ein langes Schluesselwort die Zeile bis 0.83 W spannt. Nach drei
    Verkleinerungen gilt das bewusst nicht mehr; die untere Grenze bleibt,
    damit es nicht zum Fliesstext zusammenfaellt.
- **v153 Seitenwechsel, kleinere Schrift, Nutzer-Regler.** Ismets Befund:
  "Captions sind immer auf einer Seite" und "mach die Schrift etwas kleiner".
  - **DIE STREUFUNKTION WAR KAPUTT.** `_mix01` nahm nur die unteren 10 Bit
    EINER Knuth-Multiplikation. Fuer kleine Vielfache lief sie dadurch fast
    linear: gemessen ergab n*11 fuer 0,3,6,9,12,15 die Folge 0.27, 0.22,
    0.18, 0.13, 0.09, 0.04 - eine fallende Rampe, kein Zufall. Der
    Seitenwechsel fiel deshalb IMMER auf dieselbe Seite. Jetzt der uebliche
    32-Bit-Finalizer mit drei Shift-Multiply-Runden. Das betraf auch die
    Layout-Wahl aus v150, dort war es nur zufaellig brauchbar.
  - **SEITE.** Der Satzspiegel sass fest bei x0 = 0.07 W. Jetzt wechselt die
    Seite deterministisch; Zeilen koennen rechtsbuendig stehen, die Collage
    wird gespiegelt (kleine Spalte aussen rechts, grosse Treppe nach links).
    Dazu ein `wunsch_x` in der Platzierungs-Regie - ohne den zog die
    Mitten-Anziehung jeden Block wieder in dieselbe Zone.
  - **RANGFOLGE, zweimal falsch gemacht.** Als reiner Kosten-Term (Gewicht
    1.3, dann 0.55) uebertoente die Wunschseite das Gesichts-Ausweichen: der
    Block blieb im Querformat links, egal ob die Person links oder rechts
    stand (beide Male gemessen x = 0.155 W). Die Seite gilt jetzt nur noch
    als TIEBREAKER zwischen Stellen, die das Motiv ohnehin freilaesst.
    Beweis: Person links -> Block 0.453 W, Person rechts -> Block 0.327 W.
    Ein Seitenwechsel durchbricht ausserdem die Hysterese - sie soll Zittern
    verhindern, nicht die Regie.
  - **SCHRIFT.** 0.098 -> 0.088 em Schluesselwort, 0.045 -> 0.040 em
    Fliesstext. Der Punch-Faktor musste von 1.60 auf 1.95 mit, sonst
    erreichte das Schlusswort die Bildbreite nicht mehr und der Randabfall
    aus v152 lief ins Leere (gemessen 0.96 W statt 1.14 W).
  - **NUTZER-REGLER** im Feintuning: Anordnung (Auto/Rows/Collage), Seite
    (Auto/Links/Rechts/Mitte), Caption-Groesse 60-180 %, Groessenkontrast
    1.4-5.0, Randabfall an/aus. Serverseitig gedeckelt, damit kein Client
    eine Schrift anfordert, die das Bild sprengt.
  - **DRITTER ANLAUF an derselben Stelle.** Die Tiebreaker-Bedingung prueft
    jetzt die MOTIV-Kosten, nicht die Gesamtkosten. Beim zweiten Versuch
    stand sie gegen `k`, und `k` enthaelt bereits den Zonen-Wunsch - der ist
    nie null, also griff der Tiebreaker nirgends und die Blockmitten lagen
    alle zwischen 0.49 und 0.67 W. Jetzt streuen sie ueber 0.36 W.
  - **TESTKORREKTUR, ehrlich benannt:** der v143-Ausweichtest setzte das
    Gesicht auf 0.40 H. Nach der Schriftverkleinerung sitzt der Block
    vollstaendig UNTER dieser Box - es gab dort gar keine Kollision mehr,
    der Test mass ein Ausweichen vor einem Hindernis, das ihn nicht
    beruehrt. Das Gesicht steht jetzt auf Blockhoehe (0.68 H). Gegenprobe
    mit echtem Konflikt: Person links -> Block 0.453 W, Person rechts ->
    0.186 W. Das Verhalten wurde NICHT angepasst, nur die Messstelle.
  Tests 941 logic + 7/1/5/2 Renders + GUI gruen.
- **v152 Randabfall + satzweise Collage** (beides von Ismet beauftragt, um
  naeher an die Vorbilder zu kommen).
  - **RANDABFALL.** Das Vorbild laesst sein Schlusswort links und rechts aus
    dem Bild laufen - nur deshalb kann es 0.18 H hoch stehen. Bei fuenf
    Zeichen braeuchte diese Versalhoehe rund 1480 px Breite, das Bild hat
    1080; ohne Anschnitt schrumpft `S.fit` es zwangslaeufig auf die Spalte.
    Der Anschnitt gilt NUR am Satzende, nur bei unverengter Spalte und nur
    bis 5 Zeichen: am gerenderten Streifen gemessen frisst er bei 'GEHOERT'
    (7 Zeichen) links das G und rechts das T weg - das Wort war nicht mehr zu
    lesen. Das Vorbild schneidet 'this' an, also vier Zeichen. Deckel 1.14 W.
    Das angeschnittene Wort geht NICHT in die Blockbreite ein (sonst faende
    die Platzierungs-Regie fuer 1.14 W nirgends Platz) und wird auf die
    Bildmitte zentriert, damit der Anschnitt beidseitig gleich ist.
    Messung: 'KRASS' 175 -> 300 px Grad.
  - **SATZWEISE COLLAGE.** Im Vorbild bleibt der ganze Satz stehen und
    waechst ueber rund zwei Sekunden zu einem Bild; bei uns wurde er
    chunkweise ausgetauscht. Die Collage zieht jetzt die folgenden Gruppen
    desselben Satzes mit herein (max. 8 Woerter, nur direkt anschliessend,
    nur im selben Bildzustand). Die Chunk-Bildung selbst bleibt
    UNANGETASTET - sie steuert Dichte, Tempo-Kurve und Pointen-Isolierung,
    daran zu drehen haette Nebenwirkungen bis in die Kamera. Geschluckte
    Woerter laufen ueber `used`, denselben Weg, den Phrasen schon nutzen.
    Sperren: ein Keyword-Moment wird NIE geschluckt (der grosse Moment
    gehoert ihm allein), und passt die Collage nicht in 0.40 H, wird ERST die
    Erweiterung zurueckgedreht - ein 8-Wort-Chunk im Zeilensatz waere
    schlechter als eine kurze Collage.
  Tests 927 logic + 7/1/5/2 Renders + GUI gruen, Beweis-Streifen gerendert.
- **v151 Die Referenz schlaegt jetzt wirklich durch.** Ismets Befund: "Ich
  habe ein Referenz Video hochgeladen, es aendert sich aber kaum was." Der
  Befund stimmte. Die MESSUNG war richtig (Versalhoehe 0.1836 H, Verhaeltnis
  4.59, Kamera bewegt, Buchstaben-Takt 0.087 s) - die ANWENDUNG hat sie
  verschluckt. Drei Ursachen, alle nachgerechnet:
  1. **Werte ausserhalb des Fensters wurden VERWORFEN statt geklemmt.** Die
     Fenster in `_apply_reference_params` waren am ERSTEN Vorbild geeicht
     (key_hoehe 0.030-0.140, verhaeltnis 1.4-4.0). Das zweite Vorbild liegt
     mit 0.1836 und 4.59 knapp darueber - also passierte gar nichts. Genau
     die auffaelligsten Vorbilder fielen so durch. Jetzt prueft das Fenster
     nur noch auf groben Unsinn (0.015-0.40 bzw. 1.1-8.0), der Rest wird an
     den Rand geklemmt.
  2. **Der Deckel sass zweimal.** `_apply_reference_params` klemmte sauber,
     `compose_flow` stutzte danach noch einmal auf 1.35. Ein Vorbild mit
     2.68x Hausmass kam damit als 1.35 an, also knapp der halbe Unterschied.
     Der Composer sichert jetzt nur noch gegen Unsinn (0.60-2.80), die Regie
     entscheidet davor.
  3. **`kamera: bewegt` war ein Leerlauf.** Nur 'ruhig' und 'wild' taten
     etwas; eine bewegte Referenz aenderte an unserer Kamera nichts.
  Zusaetzlich werden jetzt zwei bisher gemessene, aber weggeworfene Werte
  angewandt: **Buchstaben-Takt** steuert das Aufdeck-Tempo des
  Schluesselworts (`reveal_letter_s`, Vorbild 0.087 s je Zeichen gegen unser
  Hausmass 0.17 s je Wort), **Stammbreite** das Grundgewicht der
  Stuetzschrift (`caption_weight`).
  BEWEIS: derselbe Clip zweimal gerendert, einmal ohne und einmal mit der
  Referenz - Kleintext 86 -> 143 px (1.66x), Zone 0.25 H -> 0.34 H,
  Schnitt leichter, Aufdecken schneller.
  EHRLICHE GRENZE: die gemessene Versalhoehe ist bei LANGEN Woertern nicht
  erreichbar. 0.1836 H bei fuenf Zeichen braeuchte rund 1480 px Breite, das
  Bild hat 1080. `S.fit` schrumpft dann auf die Spalte - das Vorbild laesst
  sein 'this' dagegen bewusst links und rechts aus dem Bild laufen. Randabfall
  ist NICHT gebaut (Lesbarkeit), das ist der verbleibende Unterschied bei
  langen Schlussworten.
  Tests 917 logic + 7/1/5/2 Renders + GUI gruen.
- **v150 Abwechslung im Satzbild (Ismets Befund: "zu monoton").** Bis v149
  bekam JEDER Filler-Chunk dasselbe linksbuendige Zeilenraster: drei Zeilen,
  gleiche Kante, gleiche Groessen. Ueber ein ganzes Video sah damit jeder
  Moment gleich aus. Grundlage der Aenderung ist ein zweites Referenzvideo
  (@johnbucog_, 1.96 s, 9:16), mit `measure_reference_video` vermessen:
  Versalhoehe Schluesselwort **0.1836 H**, Groessenverhaeltnis **4.59**
  (unseres lag bei 2.2-2.9), Zone 0.18-0.49 H, Kamera bewegt.
  - **(A) COLLAGE.** Zweite Anordnung neben dem Zeilensatz: kleine Woerter
    bilden links eine schmale Spalte, die Inhaltswoerter treppen rechts
    daneben nach unten weg, jedes in eigener Groesse. Der Satz wird dadurch
    zu einem Bild statt zu drei buendigen Zeilen. Der Wechsel kommt
    deterministisch aus dem ersten Wort-Index (`_mix01`) - reproduzierbar
    ueber Re-Renders, aber ohne sichtbares Muster.
  - **(B) VARIATION.** Groessenstufen je Wort (Inhaltswoerter 1.75-2.10x,
    Verbinder 0.92-1.08x) statt einer Einheitsgroesse, und eine
    zusammenhaengende Verbinder-Kette laeuft in der Schreibschrift schraeg
    mit - ein zweiter Schriftschnitt im selben Satz, wie im Vorbild
    ("how do I do"). Hoechstens vier Woerter duerfen gross stehen, sonst
    waere der Block bei zehn Woertern 0.44 H hoch und passte an keinem Kopf
    mehr vorbei.
  - **(C) SCHLUSSWORT-KNALL.** Am Satzende (Punkt/!/?) setzt das Ankerwort
    1.60x groesser an und darf ueber die volle Breite laufen.
  - **DREI KORREKTUREN, die der Beweis-Streifen erzwungen hat:**
    1. Mit der Schwelle `len(g) >= 4` lief die Collage im echten Render KEIN
       EINZIGES MAL an - die Chunk-Bildung liefert 2 bis 4 Woerter
       (`words_per_group`). Der erste Streifen zeigte acht Mal dasselbe
       Raster. Schwelle jetzt 3.
    2. Der Knall-Deckel 0.96 W liess die rechte Kante bis **1.033 W** ragen,
       weil der Block schon bei x0 = 0.07 W ansetzt. Jetzt 0.89 W.
    3. `_rsz` nahm zuerst auch im Zeilensatz die WIRKLICH gesetzte Groesse
       statt der Sollgroesse. Das aenderte dort die Zeilenhoehe und damit die
       ganze Platzierung - der v143-Nahaufnahme-Test fiel sofort um. Die
       echte Groesse gilt jetzt nur in der Collage.
  - **Sperren:** bei verengter Spalte (Nahaufnahme, `_freie_breite`) bleibt es
    beim Zeilensatz - die Collage staffelt nach RECHTS und haette den Block
    unter den Kopf gedraengt statt neben ihn. Eine Collage ueber 0.40 H faellt
    auf das Zeilenraster zurueck. `clean` bleibt schlicht, `caption_collage`
    schaltet alles ab. Der Server reicht den gewaehlten Look jetzt als
    `cfg['look']` an die Engine durch.
  - **NICHT gebaut (bewusst, mit Ismet offen):** das satzweise Stehenbleiben.
    Im Vorbild waechst der GANZE Satz ueber rund zwei Sekunden zu einem Bild;
    bei uns steht der Text nur ueber seinen Chunk. Das zu aendern hiesse in
    die Chunk-Bildung und damit in die Dichte-Regie eingreifen.
  Tests 908 logic + 7/1/5/2 Renders + GUI gruen, Beweis-Streifen aus einem
  echten Render (vier von acht Frames zeigen die Collage).
- **v149 4K als bezahlte Stufe - und ein Aufloesungs-Fehler, der teurer war.**
  Ismets Frage 'warum hab ich da kein 4K Output' hat einen aelteren Fehler
  aufgedeckt: `output.height` wurde stur als BILDHOEHE genommen. Eine
  1080x1920-Aufnahme kam damit als **607x1080** heraus, also SCHMALER als die
  Quelle - im Hochformat hat die Engine jedes Video kleingerechnet. Im
  Querformat stimmte es zufaellig, deshalb ist es nie aufgefallen.
  Jetzt ist `height` das Zielmass der KURZEN Kante: hoch 1080x1920, quer
  1920x1080. Zusaetzlich `output.quality: hd|4k` (kurze Kante 2160).
  **Es wird NIE hochskaliert** (`H = min(H, src_h)`): aus 1080p wird kein 4K,
  sondern nur ein grosses weiches 1080p - teurer zu rechnen und schlechter
  anzusehen. Nebenwirkung: eine 960x540-Quelle wurde bisher auf 1920x1080
  aufgeblasen, das faellt jetzt weg.
  **Preis:** 4K kostet den doppelten Credit-Satz (`UHD_FAKTOR = 2`), weil
  Matting, Tiefenkarte, Gesichts-Tracking und Encode alle auf der vierfachen
  Pixelmenge laufen. Berechnet wird es NUR, wenn die Quelle mindestens 1440p
  kurze Kante hat (`_will_uhd`) - der Wunsch allein kostet nichts, und die
  Stufe wird dann auch aus den Overrides entfernt, damit der Render gar nicht
  erst gross rechnet. Die Pruefung sitzt vor der Reservierung, und der
  gezahlte Betrag steht als `cost_sec` am Job: sonst haette eine Erstattung
  nach einem 4K-Render nur die Haelfte zurueckgegeben (neues `_job_cost`,
  ersetzt sechs Aufrufe von `cost_seconds(dauer)`). Im Editor kann die Stufe
  noch kippen, `save_and_render` rechnet den Preis dort neu.
  UI: Stufe 'HD / 4K - 2x credits' im Feintuning, mit dem Hinweis auf die
  1440p-Grenze und darauf, dass nicht hochskaliert wird.
- **v148 Engine spricht Englisch.** Das Web-Produkt ist englisch, die Engine
  schrieb aber deutsch - im Fehlerkasten stand `KI-Dienst-Problem (HTTP 500)`
  und `Eingabe erkannt als LANDSCAPE` mitten in einer englischen Oberflaeche
  (Ismets Screenshot). Alle 130 Ausgaben und 19 Abbruch-Meldungen in
  `render.py` sind jetzt englisch.
  ERSETZT WURDEN NUR STRING-LITERALE INNERHALB VON `print()`/`sys.exit()`:
  ein erster Versuch lief ueber alle String-Tokens und uebersetzte prompt auch
  Kommentare und Docstrings mit ("teure Motion-Graphics of billigen
  Ease-Out-Presets") - deutsche Fuellwoerter wie ' von ' stehen eben auch in
  Prosa. Der zweite Anlauf bestimmt die Zeilenbereiche der Aufrufe per AST und
  fasst nur die an.
  **Beide Log-Leser wurden mitgezogen:** `web/server.py` mappt die Marker auf
  die Fortschritts-Phasen, `gui.py` auf die Desktop-Statuszeile. Die deutschen
  Marker bleiben als Fallback daneben stehen - in Job-Logs und im
  Transkript-Cache von vor dem Deploy stehen sie noch, und eine
  Fortschrittsanzeige, die dort ploetzlich stumm bleibt, waere eine
  Verschlechterung. Das gilt auch fuer `_parse_refs_line` und die
  `FEHLER:`/`ERROR:`-Erkennung. Die Texte der Desktop-GUI selbst bleiben
  deutsch, das ist Ismets eigene App.
- **v147 Render-Fehler ins Admin-Panel statt ins Postfach.** Ismets Wunsch.
  `_notify_job_fail` und die Timeout-Meldung mailen nicht mehr. Damit die
  Information nicht verloren geht, gibt es eine neue Tabelle `alerts`: jede
  Stoerung landet dort IMMER, unabhaengig von `DVE_ALERTS`. Noetig, weil die
  `JOBS`-Liste nur im Arbeitsspeicher steht - nach einem Neustart waere die
  Stoerung spurlos weg. Neuer Admin-Tab **Alerts** mit ungelesen-Markierung,
  'mark read' je Zeile und fuer alle, plus Zaehler im Live-Tab. Routine-Post
  (taegliches Backup) wird bewusst NICHT protokolliert, sonst ist die Liste
  nach einer Woche nur noch Backup-Rauschen. Echte Betriebsstoerungen (Platte
  knapp, Ghost-Buy, Stripe) mailen weiterhin.
- **v145 Rechnung: Pflichtangaben vollstaendig, unabhaengig vom Dashboard.**
  Befund an einer echten Stripe-Rechnung: der Kopf zeigte nur die Marke
  ('Von: DouchkoVE'). Vollstaendiger Name und Anschrift des leistenden
  Unternehmers sind aber Pflicht (§14 Abs. 4 Nr. 1 UStG; bei Kleinbetraegen
  bis 250 EUR §33 UStDV ebenso). Der Rechnungskopf kommt aus dem
  Stripe-Unternehmensprofil, darauf hat der Code keinen Zugriff. Deshalb
  tragen jetzt FUSSZEILE und ZUSATZFELDER die Identitaet selbst:
  Fusszeile `Ismet Beyazkus (DouchkoVE) · Hinter den Gärten 4, 52388
  Nörvenich, Germany · Ismet@douchkove.com` + `USt-IdNr.: DE463613884` +
  §19-Hinweis; Zusatzfelder im Kopf `Aussteller` und `USt-IdNr.`.
  Die Anschrift passt NICHT in ein Zusatzfeld - Stripe deckelt Name und Wert
  bei 30 Zeichen, ein zu langer Wert wird abgewiesen und riesse ueber
  `invoice_creation` den ganzen Checkout mit. Sie steht deshalb nur in der
  Fusszeile, die Laenge ist getestet.
  Aussteller ueber `DVE_SELLER_NAME` / `DVE_SELLER_ADDR` / `DVE_SELLER_MAIL` /
  `DVE_SELLER_BRAND` umstellbar (Defaults = Impressum), damit ein Umzug keine
  Code-Aenderung braucht. Weiterhin NIE ein USt-Satz oder -Betrag.
  Der Admin-Tab 'Recht & Steuern' listet jetzt die sechs Pflichtangaben mit
  Status und nennt ausdruecklich den einen Punkt, der nur im Stripe-Dashboard
  zu erledigen ist (Rechnungskopf). Tests 877 logic gruen.
- **v144 Referenz-Funktion: gemessen statt geschaetzt.** Die Stil-Referenz im
  Konto uebernimmt jetzt nachpruefbar den Stil des hochgeladenen Vorbilds.
  EHRLICHE URSACHE des alten Zustands: bis v143 lief das Stil-Lernen ueber
  eine Prosa-Beschreibung von GPT-5 Vision (6 Frames, `detail: low`), aus der
  eine ZWEITE Anfrage sechs Zahlen SCHAETZTE. Schriftgroesse, Hierarchie,
  Position, Ausrichtung, Kamera, Schnitt-Tempo und Sounddesign kamen darin
  ueberhaupt nicht vor. Die Referenz konnte also gar nicht aehnlich aussehen.
  - **`measure_reference_video()`** rechnet den Stil direkt aus Bild und Ton,
    deterministisch, ohne KI, ohne API-Key. Text wird nicht ueber eine
    Helligkeitsschwelle gefunden (damit lieferte das Vorbild eine Zone bis
    0.857 H und ein Groessenverhaeltnis von 4.66), sondern ueber Fuellgrad
    0.14-0.74, Strichbreite 0.06-0.40 der Zeichenhoehe, Zeilen-Bindung
    (Buchstaben haben Nachbarn auf der Grundlinie, ein Lampenreflex nicht),
    eine zeitliche Wasserzeichen-Karte (was in >85 % der Frames an derselben
    Stelle hell ist, ist Logo, nicht Caption) und ein zweistufiges
    TEXTBAND. Gemessen werden: Versalhoehe des Schluesselworts, x-Hoehe des
    Kleintexts, Verhaeltnis, Zone, Ausrichtung, Akzentfarbe, Glow/Kontur,
    Stammbreite, Wort- und Buchstaben-Takt, dazu Kamera (Zoom/Pan/Unruhe),
    Schnittdichte, mittlere Einstellungslaenge, Pegel, Stereobreite,
    Musikbett ja/nein, Ton-auf-dem-Schnitt und dessen Vorlauf.
  - **Band-Wachstum (der Fehler, den der Testbau aufdeckte).** Das
    70-Prozent-Fenster findet die SCHWERSTE Stelle, nicht den ganzen Block:
    ein fettes Schluesselwort traegt so viel Masse, dass die duenne
    Fliesstext-Zeile darueber aus dem Band faellt - dann misst die Funktion
    Schluessel gegen Schluessel und das Verhaeltnis wird 1.0. Das Band zieht
    jetzt jede echte ZEILE (>= 2 Teile auf einer Grundlinie) nach, die
    hoechstens 1.6 Zeilenhoehen entfernt steht, hart gedeckelt auf 0.40 H.
    Einzelne Reflexe koennen das Band damit nicht aufziehen.
  - **Ausrichtung ueber das Verhaeltnis, nicht ueber eine feste Differenz.**
    Die alte Schwelle 0.01 W war an einem Video geeicht; ein Block, der seine
    Breite nur wenig aendert, fiel auf 'frei' zurueck, obwohl die linken
    Kanten exakt buendig standen. Jetzt Quotient (< 0.65) mit Rauschboden.
  - **Was jetzt wirklich in der Config ankommt:** Kamerastaerke/Whip/Crash aus
    der gemessenen Kamera, `chunk_hold_min` aus der Einstellungslaenge,
    SFX-Pegel aus Musikbett + Schnitt-Ton, `caption_zone` aus der Textzone,
    `caption_align`, `caption_glow`, `caption_outline`, Akzentfarbe - und NEU
    `caption_scale` + `caption_hierarchie`, also Schriftgrad und
    Groessenkontrast. Uebertragen wird der Anteil der BILDHOEHE, der
    Formatausgleich `pf` (Querformat 1.35) bleibt davor, sonst schrumpfte der
    Satz im 16:9 wieder zusammen. Umrechnung Versalhoehe -> Grad ueber
    cap/em 0.70, x-Hoehe/em 0.52. Beides gedeckelt (0.75-1.35 bzw. 1.6-3.4),
    damit eine Fehlmessung den Satz nicht sprengen kann.
  - **Kein Hard-Stop mehr am API-Key.** `analyze_reference_video` misst zuerst
    und braucht OpenAI nur noch fuer die Prosa-Beschreibung. Faellt die API
    aus, entsteht der Eintrag trotzdem aus der Messung; `/api/style/learn`
    gibt kein 503 mehr zurueck. Bis v143 sperrte ein API-Ausfall das ganze
    Stil-Lernen aus, obwohl kein Messwert davon abhaengt.
  - **Sichtbarer Beweis im Konto.** Jede Referenz zeigt jetzt eine
    Klartext-Zeile der Messung, z. B. `Measured: key word 7.4% of frame
    height, size contrast 3.0x, text zone 17-38% height, left aligned, accent
    #f4bb33, calm camera, 1.50s average shot, no music bed, sound on the cut
    (142 ms early)`. Rohdaten (`params`/`messung`) verlassen den Server nicht.
  - **Testmaterial.** Das alte synthetische Testvideo war mit `cv2.putText`
    gesetzt - Hershey-Strichschriften ohne Punzen und ohne Antialiasing, also
    genau ohne die Merkmale, an denen die Messung Schrift erkennt. Es pruefte
    damit nichts. Neu: echte Schriftdateien (poppins_b / sans_l), zwei
    einander abloesende Caption-Bloecke (sonst haelt die Wasserzeichen-Karte
    stehenden Text zu Recht fuer ein Logo), ein echter Schnitt, zwei WANDERNDE
    helle Stoerer bei 0.60 und 0.74 H, und eine echte Tonspur mit
    gestaltetem Schnitt-Ton (Zischer 115 ms, Tiefton-Impuls 30 ms vor dem
    Schnitt). Die Messung findet daraus Zone 0.174-0.377, Verhaeltnis 2.96,
    Ausrichtung links, Akzent #f4bb33 gegen gesetztes #f9bb26, Einstellung
    1.50 s, Schnitt-Ton mit 142 ms Vorlauf.
  - **Grenze, klar gesagt:** die 12/12-Uebereinstimmung mit Ismets echtem
    Referenzvideo wurde vor dem Band-Wachstum und der neuen Ausrichtungsregel
    gemessen; die Datei liegt nicht mehr im Container, die Gegenprobe steht
    also noch aus. Alles hier ist Linux/CPU/synthetisch, ohne OpenAI-Key.
  Tests 869 logic + 7/1/5/2 Renders gruen.
- **v143b Schrift eine Stufe kleiner + Ausweich-Kosten korrigiert.** Ismets
  Befund am Frame-Streifen: das Schluesselwort war zu gross. Es sass mit
  Versalhoehe 0.081 H an der OBERKANTE des gemessenen Referenzbands
  (0.051-0.085). Jetzt `sz_k` 0.115 -> 0.098 em = 0.069 H, also die Mitte.
  WICHTIG: `sz_n` musste im selben Verhaeltnis mit (0.050 -> 0.045). Schrumpft
  nur das Schluesselwort, faellt die Hierarchie von 2.4 auf 1.93 zurueck - also
  fast auf den Zustand, den v143 gerade behoben hatte. Jetzt 2.18-2.48
  (Referenz 2.2-2.6), x-Hoehe 0.030 H bleibt im Band 0.023-0.033.
  ZWEITER, VERSTECKTER FEHLER, der dadurch erst sichtbar wurde: der kleinere
  Block wich der Person nicht mehr aus - er passte knapp an beiden Positionen
  vorbei. Ursache: die Ueberlappungs-Kosten in `spot()` waren auf die
  BLOCKFLAECHE normiert, ein 13-px-Anschnitt kostete dadurch gemessen 0.0125,
  praktisch nichts. Neu: Grundstrafe 2.5 fuer JEDE Beruehrung plus ein
  Atemluft-Term, der schon ab 0.06 W Naehe ansteigt. BEWEIS 16:9: Person links
  (Box 0.155-0.345) -> Block 0.464-0.782; Person rechts (0.655-0.845) -> Block
  0.211-0.529; Person mittig (0.405-0.595) -> Block 0.098-0.416.
  Tests 842 logic + 7/1/5/2 Renders gruen, 0 Randverletzungen im echten Render
  (links 0.093, rechts 0.915 W).
- **v143 Referenz-Niveau: Schriftgewicht, Hierarchie, Platzierungs-Regie, Schnitt-Ton.**
  Grundlage war Ismets Referenzvideo (@migs.visuals, 5.5 s, 9:16), forensisch
  vermessen (Typografie, Animation, Ton) und gegen unsere Engine gestellt.
  - **(1) Der groesste Befund war NICHT die Position, sondern das Gewicht.**
    KEIN einziges Preset setzte `fonts.support`; `deep_merge` liess damit alle
    acht Looks auf `config.yaml:16` = `fonts/sans_l.ttf` landen. Gemessen
    (Stammbreite/Versalhoehe oberhalb des Querbalkens): sans_l **0.102** gegen
    **0.22** in der Referenz, also weniger als die halbe Strichstaerke - in
    JEDEM Preset. Dazu lief das Flow-Schluesselwort hart auf `poppins_b`,
    ebenfalls in jedem Look. Der Fliesstext sah deshalb ueberall gleich aus,
    nur die Akzentfarbe unterschied sich. Neu: sieben eigene Support-Schriften
    (tiktok 0.219, creator 0.243, editorial 0.228, poster 0.321, retro 0.202,
    elegant 0.280, cinematic 0.286), und das Schluesselwort nimmt die
    Display-Schrift des Looks (`fonts.strong` kann uebersteuern). 'clean'
    bleibt bewusst auf sans_l - dort ist schlicht das gewollte Ergebnis.
  - **(2) Groessenhierarchie.** Referenz: Versalhoehe Schluesselwort zu
    x-Hoehe Kleintext = 2.2 bis 2.6. Bei uns gemessen 1.10 - alles fast gleich
    gross. `sz_k` von 0.074 auf 0.115 em; danach 2.25 bis 2.60, Versalhoehe
    0.080-0.083 H (Referenzband 0.051-0.085). WICHTIG und kontraintuitiv: die
    Referenz FUELLT die Spalte nicht. 'CREATORS' (8 Zeichen) spannt 0.828 W bei
    Versalhoehe 0.051 H, "DON'T" (5) nur 0.638 W bei 0.085 H, 'no' (2) sogar
    nur 0.124 W. Der Grad ist nicht breitengetrieben - gross ansetzen, nur
    lange Woerter schrumpfen. Ein erster Versuch mit einer 'Spalte fuellen'-
    Funktion ergab 3.1x statt 1.8x und wurde wieder entfernt.
  - **(3) Platzierungs-Regie (Ismets eigentlicher Punkt).** Gemessen: Person
    links, rechts, hoch, tief und in Nahaufnahme ergaben FUENFMAL exakt
    dieselbe Caption-Position (hoch x=0.164/y=0.234, quer x=0.090/y=0.780).
    Ursachen: `compose_flow` bekam ueberhaupt keine Bildinformation
    (`x0 = W*0.07` fest); im Hochformat wurde `v_zone()` sogar AUFGERUFEN und
    das Ergebnis danach durch die feste `H*0.13` ersetzt (zwei Zeilen
    untereinander); im Querformat war die vertikale Adaptivitaet komplett aus
    (`if portrait else Z_MAIN`); `pick_side` nutzte nur das Stack-Template.
    Neu: `scene_space_sampler` liefert pro Shot eine Raum-Karte (Kantenenergie
    + Helligkeitsstreuung, ein ffmpeg-Abtastframe je Shot) und `spot()` waehlt
    daraus die Stelle - harte Sperren Title-Safe/Plattform-Maske/Gesichtsbox,
    weiche Kosten Motiv-Unruhe und Wunschzone, **Hysterese** gegen Springen und
    Rasterung gegen Pixelwandern. `_freie_breite` verengt die Spalte bei einer
    echten Nahaufnahme (Koepfe belegen ueber 40 % der Breite), damit der Block
    NEBEN den Kopf passt statt darunter zu fliehen. BEWEIS: Kopf rechts ->
    Block 0.046-0.445 W bei y 0.155-0.352 H, Kopf links -> Block 0.446-0.845 W;
    10 px Aenderung der Gesichtsbreite verschieben ihn NICHT (Hysterese).
  - **(4) Querformat-Groesse.** `pf` war 0.62, also eine VERKLEINERUNG, waehrend
    alle Nachbar-Composer die kurze H-Kante um Faktor 1.68 bis 2.00 ausgleichen
    (compose_phrase 0.16/0.085, behind 0.213/0.11, blurin 0.199/0.10, ground
    0.20/0.10, stack 0.104/0.062). compose_flow war der einzige Ausreisser.
    Jetzt 1.35. Dazu Spaltenbreite 0.55 W quer und Tracking relativ zum Grad
    statt absoluter 6 px (die waren quer ueber 25 % em, der Satz fiel
    auseinander).
  - **(5) Schnitt-Dramaturgie im Ton.** Am Referenzvideo gemessen: KEINE Musik
    (Side-Signal in Sprechpassagen exakt null, L/R bitidentisch), stattdessen
    Sub-Riser 18-80 Hz mit +40 dB ueber 1.6 s, HF-Whoosh 4-16 kHz ab 115 ms
    vorher mit Spitze 15 ms VOR dem Bild, Impact 30 ms vor dem Bild, Boom
    40 ms danach mit 620 ms Ausklang. Ton fuehrt Bild, durchgehend.
    `build_sfx_track` bekam die Schnittzeiten bisher gar nicht - es konnte also
    nichts auf einem Schnitt sitzen. Jetzt verdrahtet, mit den gemessenen
    Vorlaufzeiten, abwechselnd voll und straff. Flow-Ticks nur noch in den
    ersten 1.6 s einer Einstellung (Referenz: 6 Ticks auf 5 s, alle im ersten
    Drittel) - durchgehende Ticks klingen wie ein Maschinengewehr.
    Gebaut ausschliesslich aus vorhandenen Pack-Slots. **Ohne Sound-Pack bleibt
    es weiterhin STUMM**, die Projektregel ist unangetastet.
  - Tests: 840 logic + Renders + GUI gruen. Neu u.a. Versalhoehe im
    Referenzband, Hierarchie 2.0-2.9, Querformat vergroessert statt zu
    schrumpfen, Block folgt der Kopfhoehe, Block weicht seitlich aus,
    Nahaufnahme neben statt unter dem Kopf, Hysterese gegen 10-px-Zittern,
    Ton-Vorlauf, Tick-Begrenzung, Stumm-Regel.
  - EHRLICH: alles auf Linux/CPU mit synthetischem Material und ohne
    OpenAI-Key. Die Geometrie ist hart gemessen, die ENDGUELTIGE Optik
    entscheidet der Frame-Streifen auf echtem Material. Der Ton ist verdrahtet,
    aber ohne CC0-Pack nicht hoerbar. Nicht angefasst: `Z_MAIN`/`v_zone` fuer
    die Keyword-Templates (die adaptieren im Hochformat bereits, im Querformat
    noch nicht - eigene Runde), und die Treppen-Einrueckung der Referenz
    (dort pro Zeile von Hand gesetzt, kein konstanter Schritt).
- **v142 Vor dem Live-Gang: Queries/Indexe, Caching, Async, Recht-&-Steuern-Panel.**
  - **(1) Indexe - 13 von 15 Kern-Abfragen waren Full-Table-Scans.** Gemessen mit
    EXPLAIN QUERY PLAN gegen das frische Schema, nicht vermutet: Ledger je Nutzer,
    Verfall-FIFO, Kauf-Belege, Consents, Token-Aufraeumen, Archiv und aktive
    Sessions scannten die ganze Tabelle. Die vorhandenen partiellen UNIQUE-Indexe
    decken NUR ihre Buchungsgruende ab (Kauf/Referral/Welcome/Monthly), nicht die
    normalen Lesepfade. 13 Indexe ergaenzt (`ix_ledger_user_time`,
    `ix_ledger_user_grund`, `ix_ledger_time`, `ix_purch_user`, `ix_purch_time`,
    `ix_users_created`, `ix_consents_user`, `ix_verify_user`, `ix_resets_user`,
    `ix_arch_mail`, `ix_arch_time`, `ix_sess_exp`, `ix_mail_log_user`) plus
    `PRAGMA optimize`, `cache_size=-8000`, `temp_store=MEMORY`. BEWEIS: derselbe
    EXPLAIN-Lauf danach = 0 Scans, als Selftest festgenagelt (ein spaeter
    geloeschter Index faellt sofort auf). Bewusst KEIN `foreign_keys=ON` - die
    Loeschpfade sind auf die bisherige Reihenfolge gebaut, das waere eine
    Verhaltens-Aenderung ohne Auftrag.
  - **(2) Caching, drei Ebenen.** (a) Prozess-Cache fuer die HTML-Dateien
    (index.html ~260 KB wurde bei JEDEM Aufruf neu von Platte gelesen),
    invalidiert ueber mtime+Groesse, ein Deploy wird also sofort gesehen.
    (b) ETag + 304: `Cache-Control: no-cache` bleibt (der Browser MUSS nach jedem
    Deploy nachfragen), aber die Antwort auf die Nachfrage ist jetzt 304 statt
    Vollversand. BEWEIS live gemessen: `/app` 261.113 Byte -> 0 Byte, Favicon
    7.405 -> 0. (c) 20s-TTL-Cache auf die teuren Admin-Aggregate (revenue,
    timeseries, tax); jede erfolgreiche schreibende Anfrage verwirft ihn zentral
    in der Middleware, damit das Panel nie die Zahlen von VOR der eigenen Aktion
    zeigt. Zusaetzlich Cache-Header auf Poster/Thumbs (private, 1 Tag) und Video
    (private, 10 min - kurz, weil ein Kauf das Wasserzeichen entfernt und
    dieselbe URL danach eine andere Datei liefert). NICHT gecacht: alles mit Geld
    oder Kontostand; per AST im Selftest festgenagelt.
  - **(3) Async - das war ein echter Fehler, kein Tuning.** Mehrere `async def`-
    Endpunkte riefen blockierende Funktionen direkt im Event-Loop auf. Dadurch
    stand der KOMPLETTE Server fuer ALLE Nutzer still, solange einer davon lief:
    `/api/style/learn` und `/api/reference/learn` (ffmpeg + Vision-KI, leicht
    eine Minute), `/api/reference/transcribe` (ffprobe + ffmpeg + Whisper),
    `/api/checkout` (Stripe-HTTPS) und der Stripe-Webhook (Invoice-Abruf +
    Mailversand). Alle in `asyncio.to_thread` verlagert - dasselbe Muster, das
    v98 schon fuer ffprobe im Upload nutzte. Der Selftest prueft das per AST:
    kein blockierender Aufruf mehr ohne await in einem async-Endpunkt.
    EHRLICH: die sync `def`-Endpunkte bleiben sync. FastAPI faehrt sie im
    Threadpool, das ist mit SQLite korrekt; sie pauschal auf `async def`
    umzuschreiben wuerde die Blockade erst erzeugen.
  - **(4) Neuer Admin-Tab "Recht & Steuern".** Ismets Frage war, wo die
    gesetzlich vorgeschriebenen Daten einsehbar sind - bisher lagen sie
    verstreut, die §19-Grenze nirgends. Neu an einer Stelle, gerechnet aus den
    echten Buchungen: Steuer-Identitaet (Kleinunternehmer §19, USt-IdNr
    DE463613884, "USt niemals ausweisen"), §19-Schwellen-Ampel (Vorjahr 25.000 /
    laufend 100.000, Warnung ab 80 %), Umsatz je Kalenderjahr und Monat inkl.
    Balkengraf, alle Kauf-Belege, Aufbewahrungsfristen (§147 AO 10 Jahre, Archiv,
    Video-Frist, Credit-Frist), Verarbeitungsverzeichnis nach Art. 30 DSGVO und
    Links auf Impressum/Datenschutz/AGB. Klar als Uebersicht deklariert, nicht
    als Steuerberatung; die Zahlen stammen aus `purchases` - weicht Stripe ab,
    gilt Stripe.
  - Tests: 823 logic + 7/1/5/2 Renders + GUI-Smoke gruen. EHRLICH: Linux/CPU,
    synthetisches Material, ohne OpenAI-Key. Die Index- und Cache-Wirkung ist
    hier gemessen; die Async-Wirkung ist strukturell bewiesen (kein blockierender
    Aufruf mehr im Loop), unter echter Last auf douchko.eu aber noch nicht
    beobachtet.
- **v141 Stil-Referenzen ehrlich + zwei Platzierungs-Fehler behoben.** Alle drei
  Punkte kamen aus Ismets Screenshots, alle drei waren echte Fehler im Code.
  - **(1) Referenz-Leck (der schwerste).** `_run_render` setzte `DVE_REFS_FILE`
    NUR, wenn das Konto eigene Stile hatte. Ohne eigene fiel `render.py` auf
    `DATA/regie_reference.json` zurueck - und GENAU dorthin schreibt der
    Owner-Endpoint `/api/reference/learn`. Folge: was auf dem Owner-Konto
    gelernt wurde, steuerte JEDEN fremden Kundenschnitt, und die UI nannte es
    dem Kunden gegenueber "N learned references" (er hatte nie etwas gelernt).
    Neu: `_refs_for_job(uid)` entscheidet EXPLIZIT, es gibt keinen stillen
    Fallback mehr - eigene Stile -> persoenliche Datei; Owner-Konto -> seine
    globale Haus-Datei (sein Gelerntes bleibt fuer SEINE Renders aktiv);
    alle anderen -> die mitgelieferten Repo-Defaults. `DVE_REFS_SOURCE`
    ('eigene'/'haus') geht mit in den Subprozess, `render.py` schreibt die
    Quelle in die Beweis-Zeile (`Stil-Referenzen: N aktiv (eigene|Haus-Stil)`),
    der Server liest sie via `_parse_refs_line` in `stil_quelle`.
  - **(1b) Director's cut sagt jetzt die Wahrheit UND das Detail.** Nur eigene
    Stile heissen "your N learned styles". Der Haus-Stil heisst Haus-Stil, mit
    Hinweis, wo man den eigenen anlernt. Die Mess-Parameter stehen im Klartext
    statt als Roh-Tokens ("2 words per caption, 5.0s between highlights, hook
    intensity 60%") - der Kunde sieht, was sein Stil konkret verstellt hat.
  - **(2) "behind you" stand am oberen Bildrand.** `_behind_cover_backstop`
    bog angesagte behind-Momente bei bildfuellender Nahaufnahme auf
    `szene='himmel'` um - der Text landete dadurch ganz oben, wo die Person
    gar nicht ist. Die Ansage stimmte optisch nicht mehr. Neu: nur noch ein
    `nah`-Flag; die Platzierung bleibt auf Kopf-/Schulterhoehe und die
    bestehende Lesbarkeits-Logik vergroessert das Wort, bis es beidseitig am
    Kopf vorbeiragt (ueber den Kopf nur noch als letzte Rettung, mit Log).
    Echte Himmel-Ansagen ("ueber mir") setzen `szene` selbst und bleiben
    unberuehrt. `nah` ueberlebt den Editor-Roundtrip. CLAUDE.md angepasst -
    die alte Regel stand dort als Invariante drin.
  - **(3) Caption-Doppelbild.** `resolve_overlaps` verglich `target` - bei der
    Flow-Caption ist das aber das KAMERA-Ziel am linken Rand (x = 0.07*W),
    nicht der Textblock in der Mitte. Der horizontale Abstand zu einem
    Keyword-Moment lag damit bei 0.43*W und riss die 0.42*W-Schranke: der
    Ueberlappungs-Schutz griff bei Flow-Captions NIE. Neu: die Flow-Caption
    traegt zusaetzlich `vpos` (echter Textblock), der Schutz misst daran.
  - Tests: 811 logic + 7/1/5/2 Renders gruen. Neu u.a. Owner-Store bleibt beim
    Owner, fremdes Konto sieht ihn nicht, leere eigene Datei zaehlt nicht als
    eigener Stil, Log-Zeile -> (Anzahl, Quelle), Flow-Caption wird am echten
    Textblock geprueft. EHRLICH: alles auf Linux/CPU mit synthetischem
    Material und OHNE OpenAI-Key. Ob das Doppelbild in Ismets konkretem Video
    genau diese Ursache hatte, ist damit NICHT bewiesen - der Screenshot passt
    zum Fehlerbild, das Video selbst lag hier nicht vor.
- **v140 Senior-Editor-Batch: Kontrast-Garantie, Tempo-Kurve, Stille vor der Pointe.** Aus der
  Produktanalyse (Code gelesen, nicht geraten) kamen drei echte Luecken, alle drei gebaut:
  - **(1) Kontrast-Garantie (war ein echter Fehler).** `scene_palette_sampler` nahm den Szenen-
    Farbton, hob den Text aber IMMER auf V=246 (fast weiss); nirgends wurde gemessen, wie hell der
    Untergrund ist. Auf hellem Grund (Fenster, weisse Wand, Himmel, Schnee) stand damit Weiss auf
    Weiss. Neu: `region_luminance()` misst konservativ (65. Perzentil = helle Haelfte),
    `fit_caption_color()` waehlt die erste Helligkeit, die den WCAG-Mindestkontrast schafft - erst
    hell (Standard-Look bleibt), sonst DERSELBE Farbton in dunkel. `effects.caption_contrast: 2.2`
    (0 = Alt-Verhalten). BEWEIS: Hell-Clip vorher/nachher gerendert, Kontrast 1.2 -> 12.6,
    Vergleichsbild an Ismet.
  - **(2) Tempo-Kurve.** `words_per_group` war EIN Wert fuers ganze Video = konstantes Timing, der
    deutlichste Maschinen-Verraeter. Neu: Blockgroesse folgt dem echten Sprechtempo (ab 3.2 Woerter/s
    ein Wort mehr gegen Flackern, unter 1.8 eins weniger fuer Gewicht), Merge-Schwelle ebenso, und
    ein power-3-Wort steht ALLEIN (auch gegen den Merge-Pass). `effects.pace_adaptive`.
    WICHTIG (gemessen, nicht behauptet): erst mit +2 Woertern gebaut, das kostete Caption-Abdeckung
    (18/20 -> 14/20 Frames), weil groessere Bloecke haeufiger eine B-Roll-Grenze ueberspannen und
    dann ganz wegfallen. Auf +1 entschaerft -> 16/20. Der Rest ist die gewollte Folge groesserer
    Bloecke. Beide build_groups-Aufrufer laufen jetzt ueber EINE Quelle (`groups_for`), sonst zeigen
    die Flow-Indizes auf den falschen Chunk.
  - **(3) Stille vor dem Einschlag.** Vor einem power-3-Moment verschwindet der Text kurz, das Bild
    atmet, dann schlaegt das Wort ein. ERSTE FASSUNG WAR FALSCH: sie schnitt Text auch mitten im
    Satz ab (saehe nach Bug aus, nicht nach Regie) und liess den Alpha-Test auffliegen. Jetzt greift
    sie NUR, wenn der Sprecher wirklich eine Pause macht (>= 0.15s), und ist nie laenger als diese
    Pause. `effects.punch_silence: 0.34`.
  Beweis: 14 neue Tests (u.a. WCAG-Formel, Weiss-auf-Weiss ausgeschlossen, Pointe isoliert,
  Rueckwaertskompatibilitaet ohne Flags, funktionale Luecke vor der Pointe), Logik 797/797 +
  Renders 7/1/5/2 gruen. Wie immer synthetisch/CPU - die Wirkung auf echtem Material sieht Ismet live.
- **v139 Captions pur + formatgerechte Platzierung (Senior-Editor-Standard).** Ismets Screenshot
  zeigte einen 'CAPTIONS'-Motion-Pill im generierten Video = die v101s-AUTO-Akzente. (a) Auto-
  Akzente per Default AUS (`config.yaml accents.auto: false`) - keine KI-/Heuristik-Badges mehr
  ohne Zutun; das Akzent-RENDERING haengt jetzt an der _accents.json-Datei statt am auto-Flag,
  damit bewusst im Momente-Editor gesetzte Akzente ('+ Add accent') weiter funktionieren.
  (b) Platzierung: Vorher sassen ALLE Nicht-Hochformate auf einem festen 0.40H-Anker = obere
  Bildhaelfte, mitten im Gesicht. Jetzt formatgerecht nach recherchierten Editor-Standards
  (SMPTE/Netflix Title-Safe, TikTok/Reels-Safe-Zones): 16:9+ = Lower Third (Block-Mitte 0.78H,
  Unterkante bleibt im 90%-Title-Safe), 4:3 = 0.75H, 1:1/4:5 = 0.72H; Hochformat behaelt die
  gesichtsbewusste v_zone (untere Mittel-Zone, Plattform-Maske). Beweis: 16:9-Testrender
  vorher/nachher (Frames an Ismet geschickt: Text unten statt Bildmitte, Pill weg; der Pill im
  ersten Proof kam aus einer ALTEN _accents.json neben dem Testclip = bestaetigt die neue
  Datei-Logik). Volle Regression: Logik 783/783 + Renders 7/1/5/2 gruen (16:9-Anker-Test auf
  0.78H umgestellt). Wie immer: synthetisch/CPU - Echtwirkung prueft Ismet live.
- **v138b OpenAI-Ampel prueft den Key ECHT.** Live-Ursache des Transkript-Fehlschlags gefunden:
  render.py bekam 401 von OpenAI ('KI-Zugang ungueltig') - der Key im Container ist ungueltig/
  beschaedigt. Die Health-Ampel war trotzdem gruen, weil sie nur 'Wert vorhanden' prueft. Neu:
  `_openai_health()` macht einen leichten /v1/models-Call (10 Min gecacht; Netzfehler -> unklar,
  nicht falsch-rot; ohne Key kein Netz-Call), beide Admin-Ansichten zeigen jetzt ok / KEY INVALID /
  MISSING. Der Key selbst muss von Ismet erneuert werden (.env auf dem Server). Selftest gruen.
- **v138a Admin-Jobs: neueste zuerst.** Ismets Wunsch - die alte Status-Gruppierung (laufend >
  wartend > Fehler > Rest) schob z.B. den frischen 'vorbereitet'-Job ans Listenende. Jetzt rein
  chronologisch nach letzter Aktivitaet. Selftest gruen.
- **v138 Transkript-Editor: Endlos-'Listening ...' behoben.** Ismets Live-Befund: 'Review your
  words' laedt ewig. Ursache: Schlug die Vorab-Transkription (pre-Mode, --transcribe-only) fehl,
  entstand nie eine _transcript2.json -> /api/transcript/{jid} antwortete fuer immer 404 ('noch
  nicht fertig') und die UI pollte endlos ohne Fehleranzeige. Fix: (a) run_job markiert den
  Fehlschlag jetzt am Job (tx_failed + letzte Log-Zeilen als tx_error fuer die Admin-Diagnose),
  (b) /api/transcript liefert failed:true wenn der Pre-Job fertig ist aber keine Datei hat (404
  NUR noch solange wirklich gearbeitet wird), (c) UI: failed -> ehrliche Meldung ('wird beim
  Render transkribiert, einfach weitermachen') + eigener 4-Minuten-Timeout. Der Flow war nie
  blockiert (Weiter-Button ging immer; der volle Render transkribiert selbst) - es SAH nur kaputt
  aus. Die LIVE-URSACHE des Fehlschlags selbst steht im Job-Log (Admin -> Jobs -> Log) - offen,
  bis Ismet das Log liefert. Verdacht: v135b-Image-Rebuild hat ungepinnte Deps (opencv etc.)
  aktualisiert. Beweis: funktionaler Endpoint-Test (failed:true vs 404) + UI-Checks, Selftest gruen.
- **v137c Header-Logo -> Hauptseite.** Ismet: Klick aufs Logo oben links soll von ueberall zur
  Hauptseite fuehren (Create), NICHT zur Landing. Umgesetzt als SPA-Navigation (`showSection('create')`,
  kein Reload, URL wird /app/create), Maus + Tastatur (role=link, tabindex, Enter/Space), Cursor-
  Pointer + Title. Selftest gruen.
- **v137b Transaktions-Labels sauber (Session-ID-Leak zu).** Ismets Screenshot: 'Reload bonus
  cs_live_...' stand ROH in der Account-Transaktionsliste - die Account-Seite hatte eine eigene
  Halb-Uebersetzung, die den Reload-Bonus (und Alpha/Admin/Refund) nicht kannte. Fix: EINE zentrale
  `translateGrund()` fuer beide Listen, vervollstaendigt um 'Reload bonus (+10%)', 'Editor layer
  render', 'Account adjustment', 'Refund'. Inhaltlich war alles korrekt (Reload-Bonus = +10% bei
  Nachkauf unter 2 Credits Rest, bewusstes v124-Feature). Selftest gruen.
- **v137a Google-Konten koennen sich jetzt loeschen.** Ismets Fund: Konto-Loeschung verlangte
  IMMER das Passwort - Google-Konten haben aber nie eins gesehen (Zufalls-Hash bei der Anlage),
  Loeschung war fuer sie unmoeglich (DSGVO-Problem!). Fix: `/api/delete_account` akzeptiert fuer
  Konten mit `google_sub` alternativ die eigene E-Mail-Adresse als Bestaetigung (case-insensitiv,
  falsche Eingabe = 401); Passwort-Konten bestaetigen unveraendert per Passwort. `/api/me` liefert
  `google`-Flag; das Frontend tauscht im Danger-Bereich das Passwort-Feld gegen das E-Mail-Feld und
  der 'Change password'-Block zeigt Google-Nutzern den ehrlichen Hinweis (Passwort nachtraeglich
  setzbar via 'Forgot password'). Beweis: funktionaler Test (falsch=401, richtig=geloescht),
  Selftest gruen.
- **v137 UI-Politur + Kauf-Mail aufgeraeumt + Factory-Reset.** Ismets Live-Feedback nach dem
  Testkauf (der KOMPLETT durchlief: Zahlung, Credits, Mail): (a) **UI:** Support-Textarea und
  Datei-Auswahl-Buttons waren Browser-Default-weiss -> dunkel gestylt (Textarea wie Inputs,
  input[type=file] mit ::file-selector-button im Card-Look). (b) **Danger-Zone:** Refund-Hinweis
  raus (an der Stelle keine Pflicht; Belehrung steht in AGB + Kauf-Mail; wichtig war nur, dass die
  alte FALSCHE 'no refunds'-Aussage weg ist). (c) **Kauf-Mail:** Hauptteil nur noch das Wichtige
  (Danke, Bestellung, Preis, Gueltigkeit, RECHNUNGS-LINK, CTA); Pflicht-Rechtstexte (§312f:
  Consent-Zeitstempel, Widerrufsbelehrung, Musterformular) als Kleingedrucktes unten - ganz
  weglassen ginge nicht (Widerrufsfrist liefe sonst bis 12 Monate). Der Webhook holt jetzt die
  hosted_invoice_url der Stripe-Rechnung und verlinkt sie direkt (Stripe mailt selbst erst nach
  der 1h-Finalisierungs-Nachfrist). (d) **Leerstring-Falle Nr. 3:** DVE_SUPPORT_MAIL/DVE_ADMIN_MAIL
  kamen als '' im Container an -> in der Live-Mail stand 'email .' - or-Fallback + compose-Defaults.
  (e) **Factory-Reset:** POST /api/admin/factory_reset (confirm='RESET') + Knopf im System-Tab -
  wischt ALLE lokalen Kunden-/Testdaten (Users, Ledger, purchases, Tickets, Consents, Claims, Jobs,
  Caches) fuer den frischen Launch; Stripe-Dashboard behaelt alle Zahlungsbelege. Beweis: 4 neue
  Tests + node--check, Selftest gruen.
- **v136 Admin-Panel: dynamische Grafen.** Ismet: leicht ablesbare, dynamische Diagramme wo passend.
  Neuer Endpoint `GET /api/admin/timeseries?days=N` (7-180, admin-gated): LUECKENLOSE Tages-Reihen
  (0-Werte fuer leere Tage, UTC-Tagesgrenzen, heute = letzter Balken) fuer Umsatz, Kaeufe, Signups,
  Renders, Render-Minuten, Credits gekauft/verbraucht. Frontend: reines SVG ohne Framework
  (CSP-sicher): `barChart()` (Tages-Balken, Hover = Datum+Wert, heutiger Balken voll orange, Peak+
  Summe oben, Datums-Achse) + `hbars()` (horizontale Verteilungsbalken mit Label/Wert). Eingebaut:
  Live-Tab (Umsatz/Signups/Renders/Verbrauch je Tag, aktualisiert mit dem 15s-Poll, Zeitreihe
  60s-gecacht), Jobs-Tab (Status-Verteilung als Farb-Balken, live 5s), Revenue-Tab (90-Tage-Umsatz
  ersetzt die Mini-Sparkline; Paket-Anteile als Balken), Credits-Tab (gekauft vs. verbraucht je Tag,
  Granted-Mix, Verbrauchs-Mix, Liability-Aging rot/gelb/gruen). Beweis: 2 neue Tests (Endpoint
  funktional: 403/lueckenlos/heute-am-Ende; Frontend verdrahtet) + node--check der Admin-JS,
  Selftest gruen. Optik verifiziert Ismet im Browser.
- **v135c Checkout-Fix Teil 2: echte Ursache war sepa_debit.** Dank v135b-Logging zeigte das
  Stripe-Log den wirklichen Fehler: 'The payment method type provided: sepa_debit is invalid'
  (SEPA-Lastschrift ist in Ismets Live-Konto nicht aktiviert; die harte Vorgabe
  `payment_method_types=['card','sepa_debit']` riss damit die GANZE Session). Fix: keine festen
  payment_method_types mehr - Stripe zeigt automatisch alle im Dashboard aktivierten Zahlarten
  (Karte sofort; SEPA/Klarna/etc. sobald dort freigeschaltet, ohne Code-Aenderung). Der
  async_payment-Webhook-Pfad (v92) bleibt fuer spaeteres SEPA erhalten. Die v135b-Fixes
  (stripe>=10, Rechnungs-Fallback, Fehler-Logging) waren trotzdem richtig und bleiben.
- **v135b Checkout-Fix: InvalidRequestError beim Kaufen.** Live-Befund von Ismet direkt nach dem
  v134-Deploy. Ursache (sehr wahrscheinlich): `stripe` war in requirements.txt UNGEPINNT und die im
  Docker-Layer eingefrorene Alt-Version kennt den `invoice_creation`-Parameter nicht -> Stripe lehnt
  die ganze Checkout-Session ab. Fix dreifach: (1) `stripe>=10` gepinnt (erzwingt Layer-Rebuild),
  (2) Fallback im Checkout: lehnt Stripe `invoice_creation` ab, laeuft der Kauf einmal OHNE
  automatische Rechnung weiter + Admin-Alarm (der KAUF geht immer vor der Rechnung; Rechnung dann
  manuell im Dashboard), (3) die echte Stripe-Fehlermeldung wird jetzt ins Server-Log gedruckt
  (vorher nur der Klassenname zum Kunden). Beweis: v135b-Garantie, Selftest gruen. Echte
  Verifikation = Ismets Testkauf nach dem Deploy.
- **v135a Bezahl-Vollaudit umgesetzt: 35 adversarial bestaetigte Befunde gefixt.** Workflow-Audit
  (5 Spezialisten: Zahlungstechnik, Preis-Konsistenz, Verbraucherrecht, Rechnungsrecht, DSGVO;
  40 Roh-Befunde, jeder von einem Gegenpruefer attackiert, 35 bestaetigt, 5 widerlegt). Die Fixes:
  - **HIGH Bezahl-Bypass zu:** Der Editor-Pfad (Upload 'pre' -> Analyse -> Momente speichern) queued
    den Voll-Render OHNE Reservierung; die post-hoc-Abbuchung clampte bei 0 -> Gratis-Videos moeglich,
    Ledger-Invariante kaputt. Jetzt reserviert `save_and_render` exakt wie `render_start` (idempotent,
    Re-Render bleibt inklusive), und der run_job-Fallback bucht race-sicher + alarmiert bei Unterdeckung.
  - **Geld-Pfade:** Worker-Catch-All erstattet jetzt (`_maybe_refund`); `admin_refund` bucht bei
    Stripe-Fehler NICHTS mehr (Retry bleibt moeglich statt Selbst-Sperre), holt den Reload-Bonus mit
    zurueck und clawbackt atomar (BEGIN IMMEDIATE); 100%-Promo-Codes (`no_payment_required`) werden
    gutgeschrieben; `charge.refunded` loest Admin-Alarm aus; `_credit_purchase` schreibt den
    purchases-Beleg atomar mit der Kauf-Zeile (Retries tragen fehlende Belege nach) und blockt
    Kaeufe fuer geloeschte Konten (Alarm statt Buchung ins Leere); Verfalls-Sweep in EINER Transaktion;
    Consent-Log fail-closed (503 statt Kauf ohne §356(4)-Beweis).
  - **Motion ehrlich:** Pauschale 1 Credit pro Clip (MP4), wie ueberall beworben (vorher Code: pro
    angefangener Minute, bis 15 Cr) - Kulanz-Richtung, nie teurer als beworben. Toter 'MOV Alpha'-
    Button entfernt (Feature existiert seit v118 nicht). CLAUDE.md-Fakt korrigiert.
  - **§312f BGB:** Kauf-Mail ist jetzt echte Vertragsbestaetigung (Bestellung + Preis + Consent-
    Zeitstempel + Widerrufsbelehrung + Muster-Widerrufsformular + AGB-Link).
  - **Texte konsistent:** Danger-Zone sagt nicht mehr 'Refunds are not possible' (widersprach AGB);
    AGB nennen Minuten-Rundung, Extras (Alpha-Layer erneut pro angef. Min, Motion 1 Cr, Style-Learn
    1 Cr), Free-Tier; abgeschalteter EU-ODR-Link raus; Rechtslinks + AGB-Hinweis auch VOR dem Login;
    'Cheapest'-Doppelclaim entschaerft. Editor-Layer-Button zeigt Preis (1 cr/min).
  - **DSGVO:** privacy.html kennt jetzt Resend (USA, SCC/DPF), Google-Login, Support-Tickets,
    Consent-Log (+Frist), die 10-Jahre-GoBD-Ausnahme nach Loeschung und die OAuth-Kurzzeit-Cookies;
    Hosting-Absatz nennt alle Drittland-Schritte. Loeschung entfernt jetzt auch Tickets und
    archiviert den Rest-Saldo (Berechnungsgrundlage fuer nachtraeglichen Widerruf).
  - **Steuer:** DVE_TAX_ID-Leerstring-Falle zu (or-Fallback + compose-Default DE463613884).
  Beweis: 13 neue v135a-Garantien + 2 bestehende Tests an neues Verhalten angepasst,
  Selftest 767/767 gruen. Uebrig als bewusstes Restrisiko: 6-Monats-Verfall bezahlter Credits
  (AGB-Klauselrisiko §307 BGB, bewusste Geschaeftsentscheidung, transparent kommuniziert).
- **v135 USt-IdNr DE463613884 ueberall verankert.** Ismet hat eine USt-IdNr -> damit ist sie im
  Impressum PFLICHT (§5 DDG "soweit vorhanden"); die alte Aussage "no VAT identification number is
  shown" dort war ab jetzt falsch und ist ersetzt. Rechnungs-Footer: `DVE_TAX_ID`-Default =
  DE463613884, Label-Logik (DE+9 Ziffern -> 'USt-IdNr.', sonst 'Steuernummer'), erfuellt §14 UStG
  (Steuernummer ODER USt-IdNr). In CLAUDE.md als Steuer-Identitaet festgeschrieben (nie vergessen,
  NIEMALS USt ausweisen). Beweis: v135-Test (Footer-Default + Impressum + alte Aussage weg),
  Selftest 754/754 gruen. Parallel laeuft ein adversarial verifizierter Vollaudit
  (Bezahltechnik/Preis-Konsistenz/Verbraucherrecht/Rechnungsrecht/DSGVO); Befunde folgen als v135a.
- **v134 Rechnungen ueber Stripe (§19 UStG).** Ismet: in Deutschland muss eine Rechnung raus, Weg mit
  den wenigsten Fehlerquellen. Entscheidung: Stripe Post-Payment-Invoices statt Eigenbau (lueckenlose
  Nummern, garantierte Erstellung/Zustellung/Archiv bei Stripe, 0,4% Gebuehr = ~4 Cent pro 9-EUR-Kauf).
  `_invoice_creation()` haengt an jeder Checkout-Session: Kleinunternehmer-Pflichthinweis §19 UStG im
  Footer (DE+EN), NIE USt ausgewiesen, Steuernummer optional via `DVE_TAX_ID` (.env + compose).
  Alle Pakete < 250 EUR = Kleinbetragsrechnung §33 UStDV (vereinfachte Pflichtangaben, keine
  Kundenanschrift noetig). Kauf-Mail sagt jetzt "Your invoice arrives in a separate email". OFFEN bei
  Ismet (Stripe-Dashboard, einmalig): Unternehmensdaten (Name/Anschrift) pflegen, Rechnungs-Mails an
  Kunden aktivieren, Nummernkreis "fortlaufend pro Konto". Beweis: v134-Test (Footer/§19/keine
  USt/Steuernummer/Verdrahtung), Selftest gruen. Live-Wirkung erst nach echtem Testkauf sichtbar.
- **v133d Gebrandete HTML-Mails (Vorbild OpusClip, aber ehrlich).** Ismet zeigte die OpusClip-
  Willkommensmail (gestaltetes HTML), unsere war reiner Text. Neu: `_email_html()` - ein
  tabellenbasiertes, inline-gestyltes Mail-Template (Gmail/Outlook/Apple-Mail-sicher), heller Body,
  schwarzes DouchkoVE-Logo (live von `/logo_dark.png`), oranger Akzent + CTA-Button, Footer mit
  Support-Kontakt. `_send_mail(..., html=...)` schickt jetzt eine HTML-Mail MIT Plaintext-Alternative
  (Resend `html`-Feld bzw. SMTP `multipart/alternative`). Verify-, Willkommens- und Kauf-Mail nutzen
  es (CTA "Confirm email" / "Open DouchkoVE"). BEWUSST ehrlich: KEINE erfundenen Zahlen wie "10M+"
  oder "No.1" (Ismets Regel: nicht als Supermacht darstellen), keine Gedankenstriche. Beweis: 3 neue
  Tests (HTML gebrandet + Text-Fallback, keine Fake-Zahlen, Resend+SMTP-multipart), Selftest 752/752
  gruen. Optik hier nur als HTML-Vorschau gerendert; final sieht Ismet es im echten Postfach.
- **v133c Support-Ticketsystem + noreply ist reines Versand-Postfach.** Ismet: bei noreply soll nichts
  ankommen, Support laeuft ueber ein Ticketsystem auf der Seite -> an seine Mail. Umgesetzt: (a) das
  globale Reply-To (v133b) ENTFERNT - `_send_mail(..., reply_to=None)` setzt Reply-To nur noch pro
  Aufruf; Bestaetigungs-/Willkommens-/Kauf-Mails haben keins mehr (Antwort an noreply laeuft ins
  Leere). (b) Neues Ticketsystem: Tabelle `tickets`, `POST /api/support` (eingeloggt, rate-limitiert)
  legt Ticket an, mailt es an `DVE_SUPPORT_MAIL` MIT Reply-To=Kundenadresse (Betreiber antwortet direkt
  aus dem Postfach) und schickt dem Kunden eine Eingangsbestaetigung ueber noreply. (c) Frontend:
  Support-Formular in der Account-Seite (Betreff + Nachricht -> Ticketnummer). (d) Admin: neuer
  Support-Tab (Liste, open/closed, Schliessen/Wieder-oeffnen) + offene Tickets in der Live-Uebersicht.
  Beweis: v133c-Tests (reply_to optional/kein globales, Ticket end-to-end mit 2 Mails inkl.
  Reply-To=Kunde, Admin sieht+schliesst), Selftest 749/749 gruen.
- **v133b Mail-Ton wie etablierte Anbieter + Reply-To.** Ismet-Befund: Absender ist `noreply`, aber der
  Text sagte "antworte hier drauf" (Widerspruch), und der Ton war zu persoenlich ("Ismet here, straight
  to my inbox"). Fix: (a) `Reply-To` auf `DVE_SUPPORT_MAIL` (Default `Ismet@douchkove.com`) in BEIDEN
  Versandwegen (Resend `reply_to` + SMTP-Header) -> Antworten landen wirklich im Support-Postfach,
  Versand bleibt ueber die verifizierte Sende-Domain. (b) Verify/Welcome/Kauf-Mails neu getextet im
  neutralen Standard-Ton ("The DouchkoVE Team", Kontakt via Support-Adresse, kein "reply to me"), ohne
  Gedankenstriche. Beweis: v133b-Test (Reply-To == Support, Copy ohne "reply to me"-Phrasen),
  Selftest gruen.
- **v133a Mail-Absender-Fix (Resend 422 "Invalid from field").** Live-Befund von Ismet: Test-Mail im
  Admin schlug mit Resend 422 fehl. ZWEI echte Bugs in `_send_mail`: (1) docker-compose reicht ein
  leeres `MAIL_FROM` als '' durch -> `os.environ.get`-Default griff nie -> Absender wurde
  'DouchkoVE <>' (ungueltig). (2) Steht MAIL_FROM im von .env.example EMPFOHLENEN Format
  'DouchkoVE <adresse>', wurde es doppelt verpackt ('DouchkoVE <DouchkoVE <adresse>>', ebenfalls
  ungueltig). Neu: `_mail_from()` normalisiert alle drei Faelle (leer -> Default, nackte Adresse ->
  verpackt, fertiges Format -> unveraendert), `_mail_from_bare()` liefert die nackte Adresse fuer den
  SMTP-Envelope. Beweis: v133a-Test mit allen drei Faellen, Selftest 745/745 gruen.
- **v133 Standard-Mail-Strecke ("wie alle anderen Firmen").** Ismet: Mail-Ablauf wie branchenueblich.
  Neu: (a) **Willkommens-Mail** genau EINMAL pro Konto, sobald es aktiv ist - nach E-Mail-Bestaetigung
  bzw. bei Google-Signup sofort (da ist die Mail schon bestaetigt, deshalb kommt dort bewusst KEINE
  Verify-Mail - das ist korrekt so). Inhalt: Gratis-Credits, 3 Schritte zum ersten Render, kein Abo.
  (b) **Kaufbestaetigung** nach frisch verbuchtem Stripe-Kauf: Credits gutgeschrieben, Wasserzeichen
  weg, Gueltigkeit; idempotent pro Stripe-Session ueber mail_log (doppelte Webhooks -> keine zweite
  Mail). Beide Mails scheitern leise (reissen nie Verify/Kauf), laufen ueber mail_log-Schluessel
  'welcome' bzw. 'kauf:<session>'. Render-fertig-Mail bleibt AUS (Ismets Wunsch, v130). Beweis: 3 neue
  Tests (Einmaligkeit, Session-Idempotenz + neue Session -> neue Mail, Verdrahtung + Copy ohne
  Gedankenstriche), Selftest 744/744 gruen.
- **v132 "Mit Google anmelden" (OAuth 2.0), optional + inert per Default.** Ismet wollte Google-
  Registrierung. Autorisierungs-Code-Flow: `/api/auth/google/start` (state-Cookie gegen CSRF, ref-Code
  wird mitgereicht) leitet zur Google-Zustimmung; `/api/auth/google/callback` tauscht den Code
  server-zu-server (Client-Secret ueber TLS) gegen den id_token, prueft `aud`/`iss`/`exp`/
  `email_verified` und loggt ein. `_upsert_google_user`: findet ueber stabile `google_sub`, sonst ueber
  E-Mail (verknuepft ein bestehendes Passwort-Konto, kein Duplikat), sonst neu = SOFORT verified=1
  (Google hat die Mail bestaetigt) + Willkommens-Guthaben. Neue Konten sind passwortlos (unnutzbarer
  Zufalls-Hash), Passwort-Reset kann spaeter trotzdem eins setzen. Gesperrte Konten (`disabled`) kommen
  auch ueber Google nicht rein. Frontend: "Continue with Google"-Button auf der Auth-Seite, versteckt
  bis `/api/authinfo` `{google:true}` meldet; OAuth-Fehler landen als `?autherror=`-Toast. WICHTIG:
  KOMPLETT aus, solange `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` fehlen - kein Button, Endpoints
  redirecten nur. Passwort-Login voellig unberuehrt. Migration: `users.google_sub` + partieller
  Unique-Index. Beweis: 8 neue Tests (Anlage/Verknuepfung/Idempotenz/Sperre/authinfo/inert/JWT/
  Username), Selftest 740/740 gruen. NOCH NICHT auf echtem Google-Client verifiziert (hier ohne Keys
  getestet) - Ismet legt den OAuth-Client in der Google Cloud an, dann live pruefen.
- **v131 Betriebs-Post mit EINEM Regler (`DVE_ALERTS`).** Ismet: nicht jede Kleinigkeit als Mail
  bekommen. Drei Stufen: `all` (alles, inkl. taegliche Backup-Mail = frueheres Verhalten),
  `important` (Default: NUR echte Stoerungen - Job-Fehler, Platte knapp, Timeout; keine Routine-Post),
  `off` (gar keine Betriebs-Mails). `_notify_admin(..., routine=False)` filtert davor, Routine-Post
  (Offsite-Backup-Mail) haengt jetzt an der Stufe `all`. WICHTIG: Kunden-Mails (Verify/Reset/Kauf)
  sind UNBERUEHRT, und das lokale rotierende DB-Backup auf der Platte laeuft immer weiter - nur der
  taegliche Mail-Versand des Snapshots ist ausgeschaltet, solange nicht `all`. Beweis: 2 neue Tests
  (Stufen-Filter + Backup-Gate), Selftest 732/732 gruen.
- **v130 Admin-Panel Vollausbau (dynamisch, 9 Tabs) + Suspend + Heartbeats.** Ismet: Admin-Menue
  dynamischer + alle Infos, die ein Admin-Menue braucht. Grundlage: Inventar-Workflow (5 Agenten
  kartierten 142 echte Datenpunkte im Code, ein Design-Agent synthetisierte die Spezifikation), danach
  Bau + adversariale Sicherheits-Review. Alle Endpoints weiter am Server-Key `DVE_ADMIN`.
  - **Dynamisch (der Kern-Wunsch):** Live-Ops-Tab pollt alle 15s, Jobs-Tab alle 5s; pausiert bei
    verstecktem Tab (visibilitychange) und per Button; „live · updated Xs ago"-Anzeige + Puls.
    Schwere Aggregate (Revenue/Credits/Abuse/User-Listen) laden on-demand, kein Dauer-Poll.
  - **9 Tabs:** Live (Umsatz/Signups/Sessions/Queues/Liability/Health-Ampel/Alerts/Build),
    Jobs (Verteilung, Queue-Zusammensetzung paid/free, Avg-Renderzeit, At-Risk, Aktionen
    Log/Retry/Kill/Refund/Unlock/Delete + Stop-all-stuck), Revenue (Fenster, Trend-Sparkline, pro
    Paket, AOV/ARPPU, Wiederkaeufer, Top-Spender, Katalog, Pre-v128-Schaetzung, CSV), Credits
    (gratis/bezahlt/admin, Verbrauch render+alpha+style, Breakage, Liability-Aging), Users
    (Suche/Filter/Sort/Pagination, CRM-Detail mit LTV/Orders/Sessions/Consents/Referral + Aktionen
    Credits/Verify/Reset/Revoke/Suspend/Export/Delete + Stripe-Refund pro Kauf), Abuse (verwaiste
    Farming-Hashes, Wegwerf-Konten, Unverifizierte, Referral-Graph, Rate-Limit-Lockouts, Demo-IPs),
    System (Keys/Health nur bool, Config-Werte, Heartbeats, Aktionen Backup/Test-Mail/Cleanup/Expiry),
    Compliance (Widerruf-Consent-Log, GoBD-Archiv, CSV), Codes (Tester-Zugangscodes anlegen/sperren).
  - **Neue Infrastruktur:** `users.disabled` (reversible Sperre; `_session_user`+Login blocken
    gesperrte Konten sofort), `purchases`-Umsatz (schon v128), Render-Zeitstempel in `set_state`
    (started_at/finished_at -> Avg-Renderzeit), `_HEARTBEAT` in Watchdog/Cleanup (echter Herzschlag),
    DVE_BUILD auf v130 aktualisiert (war veraltet). Admin-Refunds hinterlassen eine nachvollziehbare
    positive 'Refund %'-Ledger-Zeile (schliesst die alte Refund-Blindstelle fuer manuelle Faelle).
  - **Bewusst NICHT** (Anti-Feature-Stacking): keine Chart-Library (nur Inline-Sparklines), kein
    WebSocket/SSE (visibility-pausiertes Polling reicht), kein Live-Config-Toggle (Env/Boot-time, nur
    Anzeige), keine MRR/Churn/Cohort-Analytik (Einmalkauf-Modell), kein Marketing-Tooling.
  - **Adversariale Review danach (2 bestaetigte Funde gefixt):** (1) `admin_refund`-Clawback war
    weder idempotent noch geclampt -> Doppelklick zog Credits doppelt ab und eine Clawback groesser
    als das Guthaben brach das Ledger-Invariant; jetzt: No-op bei bereits erstatteter Session
    ('Refund {session}'-Ledger-Marker), Clawback auf das aktuelle Guthaben gedeckelt, Stripe-
    Idempotency-Key. (2) Momente-Editor-Re-Renders froren started_at/finished_at auf der Analyse-
    Phase ein -> Avg-Renderzeit/ETA im Panel falsch; jetzt beim Re-Render zurueckgesetzt.
  Selftest **729/729 gruen** (funktional: revenue/credits/system/abuse-Aggregate, Suspend sperrt
  Login+Session/Unsuspend gibt frei, Job-Refund bucht +Credits mit traceable Ledger-Zeile, Codes
  anlegen/listen; plus Verdrahtungs- + UI-Dynamik-Garantien). Alle 26 Endpoints Runtime-gesmoked
  (0 Fehler), UI live in 9 Tabs gesmoked (0 JS-Fehler). EHRLICH: nur Linux/CPU/Test-DB; Stripe-Refund
  ist echt-Geld-Code, best-effort und ungetestet live.
- **v129 Globaler Job-Timeout (haengende/Zombie-Jobs enden automatisch).** Ismet sah im Admin-Panel
  mehrere Motion-Jobs ewig auf „Queued (restored after restart)" bzw. „laeuft" haengen. Ursache: der
  alte 45-Min-Waechter beobachtete NUR `laeuft`, killte nur den Prozess und verliess sich darauf,
  dass die Render-Schleife den Job auf Fehler setzt + erstattet - bei einem nach Neustart
  wiederhergestellten Job laeuft aber KEINE Schleife mehr (Zombie), und `wartet`-Jobs wurden nie
  getimt; der Timer lag zudem nur im RAM (Neustart nullte ihn). Neu: Fortschritt-Fingerabdruck
  (status/progress/phase). Aendert sich ein Job DVE_JOB_TIMEOUT Sekunden (Default 40 Min) nicht,
  wird er von `_reap_stuck_job` HART beendet: evtl. Prozess killen, Status auf `fehler`, Credits
  erstattet - unabhaengig davon, ob noch ein Prozess lebt. Ein gesund hochzaehlender Render setzt die
  Uhr zurueck, wird also nie faelschlich gekillt. Admin-Panel: „Stop all stuck" beendet alle
  wartenden/laufenden Jobs auf einmal (`/api/admin/jobs/reap_stuck`). Selftest **721/721 gruen**
  (funktional: Reaper beendet haengenden Job + erstattet, Zombie-sicher; plus Verdrahtung).
- **v128 Admin-Panel Tier 1 (Betrieb/Nutzer/Umsatz) + Orange-Vereinheitlichung.** Ismet: eigenes
  Admin-Menue + Orange auf allen Seiten.
  - **Orange ueberall (v127a):** SPA (index.html) und Impressum/Datenschutz/AGB liefen noch auf dem
    alten Violett (#7c5cff) = generischer KI-Lila-Look. Jetzt durchgehend Landing-Orange #ff7a1a
    (Akzent/Glow/Buttons/Success-Card entpurpelt, Recht-Seiten warmes Near-Black). 0 Violett im
    ganzen web/. Sekundaere Delight-Farben (Gold/Konfetti) bleiben.
  - **Admin-Panel (`/admin`, eigene Seite `admin.html`):** ALLE Endpoints haengen am Server-Key
    `DVE_ADMIN` (Header X-Admin-Key, timing-safe) - NICHT an der Owner-Session; fehlt der Key, ist
    das Panel tot. Drei Tabs:
    - **Overview:** echter Umsatz heute/7T/30T/gesamt (neue `purchases`-Tabelle speichert den
      TATSAECHLICH gezahlten Betrag amount_total pro Stripe-Session, idempotent), Nutzerzahlen
      (gesamt/verifiziert/zahlend), offene Credit-Verbindlichkeit, Render-Summe, Job-/Queue-Status,
      System-Health mit Ampel (OpenAI-Key?, Stripe live/test?, Webhook-Secret?, Disk, DB-Groesse,
      letztes Backup, Admin-Key gesetzt?).
    - **Jobs:** wartende/laufende/fehlgeschlagene Jobs; Aktion „Kill" killt den Prozess (Render-Loop
      endet -> Fehler-Zweig + automatische Erstattung).
    - **Users:** Suche/Liste (E-Mail, verifiziert?, Credits, zahlend?, Beitritt); Detail mit
      Ledger-Historie + Aktionen: Credits gutschreiben/abziehen (nie unter 0, mit Grund im Ledger),
      als verifiziert markieren, Verify-Mail neu senden, Konto loeschen (Kaeufe -> Archiv wie die
      Selbst-Loeschung).
  - **Wo/Zugang:** URL `/<domain>/admin`, Admin-Key eingeben (aus Server-Env `DVE_ADMIN`). Das alte
    Owner-Panel (Reference styles + Transcribe) bleibt separat in Account und haengt weiter an der
    Owner-Mail. NICHT gebaut (bewusst, Tier 2/3): Missbrauch-Signale, Consents-Log, Job-Suche,
    Wartungsmodus/Toggles - kommen erst bei Bedarf.
  Selftest **719/719 gruen** (funktional gegen isolierte Test-DB: falscher Key -> 403, Overview mit
  echtem Umsatz, Nutzer-Liste, Credits-Adjust, Verify; plus Verdrahtungs-Garantien). Live-Smoke:
  Server hochgezogen, /admin mit Key geladen, Overview + Nutzer-Detail per Screenshot bestaetigt.
- **v127 Launch-Audit-Fixes (Credits/Auth/Missbrauch/Recht) + Landing-Redesign.** Ismet vor
  dem Launch: "Keine Bugs wegen Credits, die verloren gehen, kein Hack, rechtssicher?" Dazu ein
  adversarialer Audit ueber 6 Achsen (Credits, Auth, Injection/XSS, Payment, Missbrauch, Recht),
  jeder Fund von einem zweiten Agenten gegengeprueft. Ergebnis: **Injection/XSS/SQL = 0 Funde,
  Stripe-Webhook signaturgeprueft + nicht faelschbar**, aber 18 bestaetigte Punkte (5 hoch, 10
  mittel, 5 niedrig). EHRLICH: alle hier nur unter Linux/CPU mit isolierter Test-DB verifiziert.
  - **CREDIT-VERLUST (die zwei hoch):** Ein fehlgeschlagener + erstatteter Render lieferte den
    Retry GRATIS aus (netto 0 Credits) - `_render_charged` prueft nur die Existenz der
    Reservierungs-Zeile, die der alte Refund stehen liess. Gleiche Luecke beim Alpha-Export.
    Fix: `_refund_credits` LOESCHT jetzt die Reservierung (idempotent ueber rowcount) statt eine
    Gegenbuchung zu setzen; das Ledger-Invariant (Summe==balance) bleibt exakt gleich, aber der
    Retry wird wieder normal abgerechnet. `resv_like`-Muster fuer Render/Alpha/Style.
  - **DOPPEL-GUTSCHRIFT (mittel/niedrig):** Monats-Freikredit und Welcome hatten - anders als
    Kauf/Referral - keinen Unique-Index, zwei parallele Requests konnten doppelt gutschreiben.
    Fix: partielle Unique-Indizes `ux_ledger_welcome`/`ux_ledger_monthly`, beide Grants laufen in
    EINER `BEGIN IMMEDIATE`-Transaktion mit `INSERT OR IGNORE`.
  - **FREE-TIER-FARMING (mittel, Ismet-Wahl "Mail-Hash speichern"):** Konto loeschen + mit
    derselben Mail neu = Freikredite erneut. Neue Tabelle `credit_claims` (gesalzener E-Mail-HASH,
    kein Klartext, kind=welcome/monthly-YYYY-MM) ueberlebt die Loeschung bewusst -> pro Person
    genau 1x. Zusaetzlich Wegwerf-Mail-Domains beim Sign-up abgewiesen (`_is_disposable_email`,
    vorher nur der Referral-Bonus). DSGVO Art. 6(1)(f), steht in /privacy.
  - **RATE-LIMIT-SPOOF (mittel):** `X-Forwarded-For` war client-spoofbar (uvicorn traut dem
    linken Hop), also Login-Brute-Force + Gratis-Demo-Quota aushebelbar. Fix: `_client_ip` nimmt
    den RECHTEN (von Caddy angehaengten, echten) Hop; alle Rate-Limit-/Demo-Pfade nutzen ihn.
  - **QUEUE-/RE-RENDER-FLOODING (mittel):** ein Konto konnte die unbounded Queue (ein Worker)
    mit Gratis-Jobs (Pre-Mode/Re-Render) fluten und alle aushungern. Fix: `_enqueue_guard`
    (max. 3 gleichzeitig wartende/laufende Jobs pro Konto, DVE_INFLIGHT_CAP) an Upload + Re-Render;
    Re-Render lehnt zusaetzlich ab, wenn schon einer laeuft.
  - **OWNER-SQUAT (niedrig):** Owner-Rechte (globale Stil-Regie, Gratis-Whisper) hingen nur an
    einer evtl. unregistrierten Mail. Fix: `OWNER_EMAIL` ist nicht mehr registrierbar; `_owner_ok`
    verlangt zusaetzlich `verified`.
  - **PAYMENT-HAERTUNG (niedrig):** Webhook schreibt Sekunden jetzt aus dem SERVER-Katalog
    `PACKS[pack]` gut statt der Metadaten-Zahl zu vertrauen (an den Katalog gekoppelt).
  - **RECHT:** Datenschutz - Rechtsgrundlagen pro Zweck (Art. 6(1)(b)/(f)), US-Transfer-Mechanismus
    (SCC/DPF + Art.-28-DPA) ergaenzt, Zusammenfassung entschaerft (7-Tage-Loeschung nur fuer
    Videos), Rechte-Liste um Art. 18/20 vervollstaendigt. AGB - Widerrufs-Einwilligung wird jetzt
    aktiv erfasst: Pflicht-Checkbox im Kauf (sofortige Ausfuehrung + Verzicht bewusst, § 356(4)
    BGB), server-seitig mit Zeitstempel in `consents` protokolliert; volle Widerrufsbelehrung +
    Muster-Widerrufsformular; §3 Credit-Verfall bei Loeschung um den 14-Tage-Refund-Vorbehalt
    ergaenzt. Impressum - TMG->DDG, RStV->MStV, Kleinunternehmer § 19 UStG (keine USt-IdNr).
  - **Landing-Redesign (Ismet: "sieht komplett nach KI aus"):** neue Editorial-Landing mit dem
    ui-ux-pro-max-Skill (Exaggerated Minimalism) - Newsreader-Serif-Headlines, Mono-Labels,
    warmes Schwarz + ein Orange, nummerierte Feature-Zeilen, Scroll-Reveal (respektiert
    prefers-reduced-motion). Motion bleibt fuer Kunden ausgeblendet (Single-Product Captions).
    ALLE Gedankenstriche raus (harte Ismet-Regel). Auf Desktop + Mobil gerendert + freigegeben.
  - **Offen fuer Ismet (nicht code-loesbar):** Stripe Live-Keys + Webhook-Secret scharfstellen;
    OpenAI-DPA/AVV formal unterschreiben (der Privacy-Text nennt den Mechanismus bereits);
    optional DVE_REF_SALT setzen; UptimeRobot auf /api/health.
  Selftest **717/717 gruen** (funktional: Gratis-Render-Luecke zu / Refund loescht Reservierung /
  Retry zahlt, Welcome-Farming nach Loeschung geblockt, Monats-Kredit 1x atomar, Unique-Indizes
  da, XFF-Spoof wirkungslos, OWNER_EMAIL nicht registrierbar, Wegwerf-Domain erkannt; plus
  Verdrahtungs-/Recht-Text-Garantien). render.py unveraendert.
- **v126 Kunden-Stil-Referenz + GPT-5-Restmigration + Referral-Haertung (live).** Ismet:
  eine innovative, machbare Funktion vor dem Launch, nur noch GPT-5.
  - **Kunden-Stil (die Innovation):** Jedes Konto lernt der Regie den EIGENEN Wunsch-Stil aus
    Referenz-Videos an, nicht nur der Owner. `render._reference_store_path()` respektiert jetzt
    `DVE_REFS_FILE`; der Server injiziert pro Render-Subprozess die PERSOENLICHE Referenz-Datei
    des Kontos (`data/refs/user_<id>.json`), sodass Prompt-Block UND deterministische
    Mess-Parameter aus dem persoenlichen Geschmack kommen statt aus dem Haus-Stil. Endpoints
    `/api/style/{learn,list,delete}` (learn kostet 1 Credit, atomar reserviert + Refund bei
    Fehlschlag, Cap 6/Konto, GPT-5-Vision via `analyze_reference_video(store_path=...)`).
    Account-Panel "Your caption style", Landing-Bullet "Learns your style". Lernt den
    editorialen Stil (Pacing/Betonung/Hook), NICHT Fonts oder Woerter. Persoenliche Referenzen
    werden mit dem Konto geloescht. EHRLICH: die Verdrahtung ist end-to-end verifiziert
    (Override, Pro-Konto-Trennung, Env-Injektion, Prompt+Params lesen die Datei); die echte
    GPT-5-Vision-Analyse laeuft erst live mit Key.
  - **GPT-5 ueberall:** letzte `gpt-4o`-Nennungen aus render.py/server.py/config.yaml raus
    (waren nur noch Kommentare, alle Defaults liefen schon auf gpt-5). Der `_oai_json`-Kompat-
    Helfer bleibt (erkennt gpt-5/o-Serie an max_completion_tokens).
  - **Referral gehaertet (Fix aus adversarialem Review des live gepushten v124):** drei
    bestaetigte Races behoben. Neue partielle Unique-Indizes `ux_ledger_ref` (Referral-Gruende)
    + `ux_users_refcode`; `_grant_referral` laeuft jetzt in EINER `BEGIN IMMEDIATE`-Transaktion
    mit `INSERT OR IGNORE` (doppeltes Verify bucht nicht mehr doppelt, Cap-Zaehlung atomar);
    `_ensure_ref_code` setzt via `UPDATE ... WHERE ref_code IS NULL` + Kollisions-Retry.
  - **Referral Anti-Farming (Ismet: beide absichern):** (1) Re-Arm via Konto-Loeschen +
    Neuregistrieren ist tot - neue Tabelle `referral_claims` speichert einen gesalzenen,
    persistenten E-Mail-HASH (kein Klartext) der belohnten Konten, der die Loeschung bewusst
    ueberlebt (DSGVO Art. 6(1)(f), steht jetzt in /privacy). INSERT OR IGNORE darauf ist zugleich
    das Idempotenz-Gate. (2) Bekannte Wegwerf-Mail-Domains bekommen keinen Referral-Bonus
    (`_is_disposable_email`, ~45 Domains). Kein Sign-up-Block, nur der Bonus.
  Selftest **706/706 gruen** (funktional: Pro-Konto-Referenzpfad, Override, doppeltes Verify
  idempotent, Wegwerf-Domain geblockt, Re-Arm nach Loeschung geblockt; plus Verdrahtung +
  GPT-5-Garantie).
- **v125 Echter 6-Monats-Credits-Verfall (live).** Das "Credits valid for 6 months" der
  Preisseite ist jetzt Code, nicht nur Text (Ismet: vor dem Launch implementieren, keine
  Bestandsguthaben betroffen). Modell: **FIFO pro Gutschrift**. Jede positive Ledger-Zeile
  (Kauf, Welcome, Monats-Gratis, Referral, Bonus) traegt ihr Datum; Verbrauch (negative
  Zeilen, inklusive frueherer Verfaelle) zehrt die aelteste Gutschrift zuerst auf. Was nach
  180 Tagen (DVE_CREDIT_DAYS) von einer Gutschrift uebrig ist, verfaellt mit eigenem
  Ledger-Eintrag "Expired credits" (dadurch idempotent: der Eintrag zaehlt beim naechsten
  Lauf als Verbrauch). Stuendlicher Sweep im Cleanup-Worker bucht Verfall und schickt
  **einmalig** 14 Tage vorher eine ehrliche Warn-Mail (neue mail_log-Tabelle gegen
  Doppelversand, nur verifizierte Konten). `/api/me` liefert expiring_credits/expiring_days,
  Billing zeigt "N credits expire in D days" nur, wenn wirklich etwas ablaeuft.
  Selftest **696/696 gruen** (funktional: FIFO-Verfall nur des unverbrauchten Rests,
  Idempotenz, Warn-Fenster sieht Bald-Ablaufendes und nicht Frisches, mail_log-Einmaligkeit).
- **v124 Monetarisierungs-Batch: Kaufmoment, Wiederkauf, Investment, Referral (live).**
  Ismet: Gewinn maximieren, aber ehrlich (keine Preis-Schreierei, keine Gedankenstriche,
  kein Supermacht-Ton). Vier Pakete:
  - **Kaufmoment:** Wasserzeichen-Upsell am fertigen Video umgeschrieben (ohne Preisnennung,
    Akzent-Rahmen, Button "Remove watermark"). Dazu Low-Balance-Hinweis nach dem Render,
    wenn unter 1 Credit uebrig ist.
  - **Wiederkauf:** (1) Ablauf-Mail 48h bevor ein fertiges Library-Video geloescht wird
    (einmalig pro Job via State-Flag, nur verifizierte Konten, Service-Mail, nichts erfunden).
    (2) Reload-Bonus: Nachkauf bei fast leerem Konto (< 2 Min Rest) bringt still +10%,
    eigener Ledger-Eintrag "Reload bonus {session}", haengt am Kauf-Idempotenz-Pfad
    (Stripe-Retry bucht weder Kauf noch Bonus doppelt).
  - **Investment sichtbar:** Hook-Score jetzt SERVERSEITIG pro Video (`_hook_score`,
    Python-Port der Client-Heuristik, aus der finalen Momente-Datei in den Job-State),
    `/api/library` liefert hook_score + silent_score, Library-Karten zeigen den Score,
    Account-Panel "Your progress" (Bestwert, Schnitt letzte 5, Stil-Zaehler). Editor-
    Korrekturen tragen jetzt die user_id (Lernen bleibt global, Anzeige ist ehrlich pro User).
  - **Referral:** Einladungscode pro Konto (8 Zeichen, Alphabet ohne I/O/0/1, lazy erzeugt),
    Link `?ref=CODE` wird im Client gemerkt und bei der Registrierung mitgeschickt. Belohnung
    10 Min fuer BEIDE Seiten erst nach E-Mail-Verify des Geworbenen (kein Wegwerf-Farming),
    Werber-Deckel 10, alles idempotent ueber Ledger-Eintraege. Account-Panel "Invite a creator".
  DB-Migration: users.ref_code + users.referred_by. Selftest **692/692 gruen** (funktional:
  Referral beidseitig/einmalig/Deckel, Reload-Bonus nur bei leerem Konto + Stripe-Retry,
  Hook-Score-Port; plus Verdrahtungs-Garantien). OFFEN: 6-Monats-Verfall existiert nur als
  Marketing-Text, nicht im Code. Entscheidung Ismet: echt implementieren (kommt als v125,
  Seite ist noch nicht veroeffentlicht, kein Eingriff in Bestandsguthaben).
- **v123 Motion Design ausgeblendet — Fokus zurück auf Captions (live).** Ismet-Entscheidung
  nach 2 Tagen: die Motion-Qualität kommt (an echtem Material beurteilt) nicht an Tools wie
  Jitter ran; statt weiter zu kämpfen wird Motion für Kunden ausgeblendet. **Nichts gelöscht,
  ein Schalter:** `MOTION_ENABLED = false` in `web/index.html`. Damit:
  - **App:** „Motion"-Nav-Link versteckt, `PAGES` ohne `motion`, `routeFromHash`/`showToolChooser`
    führen ohne Tool-Auswahl direkt zu Captions (auch alte `#motion`-Bookmarks/`dve_tool`-Prefs
    landen sauber in Create).
  - **Landing:** Motion-Produktsektion + Nav-Link + Hero-Chooser-Karte auskommentiert/entfernt,
    Hero wieder Ein-Produkt („Make your talking-head video look professionally edited"),
    Pricing-FAQ ohne Motion-Zeile.
  - **Code bleibt komplett liegen** (Server-Endpoint, Remotion-Kompositionen, Tests) — zum
    Wiederanschalten `MOTION_ENABLED = true` + den Landing-Kommentar entfernen. Voll reversibel.
  Selftest **685/685 grün** (v123-Garantie: ausgeblendet UND Code intakt; alle Motion-Engine-
  Tests laufen weiter, weil der Code da ist). Positionierung wieder scharf: reines Finishing-
  Tool für Captions, kein Feature-Stacking.
- **v122 Motion: Auto-Format + „18%-Hänger" gehärtet (live).** Ismet: „Hängt jetzt auf 18% die
  ganze Zeit. Nimm das mit dem Format raus, es soll automatisch das Format des Videos zurückgeben."
  - **Auto-Format:** Der Format-Regler ist raus. Bei Video-Eingabe liest der Server das echte
    Seitenverhältnis (ffprobe `width,height`) und rendert exakt in diesen Pixel-Maßen
    (`render-showcase.mjs` nimmt jetzt `--format=WxH`, macht sie gerade + deckelt die lange
    Kante auf 1920). Skript/Transkript ohne Video → Default 9:16. Der Ergebnis-Rahmen übernimmt
    per `onloadedmetadata` das echte Video-Seitenverhältnis. Beweis: Bridge mit `1280x718`
    rendert ein gültiges 1280×718-MP4.
  - **18%-Hänger (Queue-Blockade):** 18% war der Frontend-„Queued"-Wert — der Job wurde also
    gar nicht abgearbeitet. Der volle Worker-Pfad läuft lokal sauber durch (Text→fertig in 75s),
    also ist die Ursache serverseitig: (a) **unbegrenzte Remotion-Concurrency** startet 1
    Chromium-Tab pro CPU-Kern → auf vielkernigem Container Speicher-Überlauf, Chromium hängt →
    jetzt gebremst auf `--concurrency=2` (`DVE_MOTION_CONCURRENCY`). (b) Ein hängender Render
    blockierte die einspurige Queue 15 min → jetzt **Stall-Wächter**: kommt 4 min lang keine
    Ausgabe (`DVE_MOTION_STALL`) oder reißt der 20-min-Deckel (`DVE_MOTION_TIMEOUT`), wird der
    Prozess gekillt → klare Fehlermeldung + Gutschrift, Queue frei. Selftest **684/684 grün**.
    EHRLICH: die Server-Ursache kann ich hier nicht direkt beobachten; die Härtung adressiert
    die zwei wahrscheinlichsten Gründe. Falls es weiter klemmt, steht die echte Remotion-
    Fehlermeldung jetzt im Job-Detail.
- **v121 Admin-Transkript-Werkzeug unter Reference (live).** Ismet: „Bau eine Funktion ein,
  die das Transkript von einem Video ausgibt, nur bei Admin-Berechtigung unter Reference."
  Umgesetzt im bestehenden owner-gated Reference-Bereich (Create-Seite, `#refPanel`, sichtbar
  nur fürs Besitzer-Konto): neues Aufklapp-Panel „Transcribe a video". Video/Audio hochladen →
  Server zieht eine schlanke 16-kHz-Spur (ffmpeg) → Whisper (`whisper-1`, Wort-Timings über den
  Server-`OPENAI_API_KEY`) → Ausgabe als **Klartext, .srt, .vtt und Wort-.json** (Downloads +
  Copy). Text bleibt verbatim, **kein Credit-Abzug**. Endpoint `/api/reference/transcribe` ist
  serverseitig `_owner_ok`-gated (403 für alle anderen); das UI-Panel steckt im refPanel, das
  für Nicht-Owner versteckt bleibt. Neue Formatter `_words_to_srt/_vtt/_text/_words_to_cues`
  (echte Timings, Cue-Umbruch an Satzende/Pause). Selftest **683/683 grün** (Formatter- +
  Gating- + UI-Garantien). EHRLICH: hier ohne Key nur Formatter/Gating getestet — die echte
  Transkription läuft erst live mit gesetztem `OPENAI_API_KEY`.
- **v120 Ladescreen sachlich-professionell + „6%"-Hänger behoben (live).** Ismet: „Mach
  unnötige Beschreibungen und alle Gedankenstriche weg. Professionell, nicht möchtegern. Bleibt
  beim Rendern immer bei 6% stehen, fix das."
  - **Copy entschlackt:** rotierende „Regisseur"-Zeilen raus, Floskel „renders like a senior
    designer" raus, ALLE Gedankenstriche (— / –) aus der Motion-Studio-UI + Ladescreen +
    Server-Phasen entfernt. Ladescreen zeigt jetzt nur noch Phase + Prozent
    (Preparing/Rendering/Encoding), sonst nichts.
  - **„6%"-Hänger:** Ursache war ein künstlicher Frontend-Sockel `Math.max(progress, 0.06)` —
    lag der Job noch in der (einspurigen) Queue, zeigte er stur 6%. Sockel raus: der Balken
    spiegelt den ECHTEN Serverwert (der Creep verhindert 0%). Zusätzlich Backend gehärtet:
    harte Render-Zeitgrenze (`DVE_MOTION_TIMEOUT`, 15 min) killt einen hängenden Render, damit
    er die Queue nicht blockiert (Folge-Jobs hingen sonst früh fest) — mit Fehlermeldung +
    Gutschrift. (Zusammen mit dem v-Fix `--log=info`, der die echten Fortschritts-Zeilen wieder
    durchlässt.) Selftest **680/680 grün**, UI-JS `node --check` ok.
- **v119 Sichtbarer Upload + dynamischer Ladescreen (live).** Ismet: „Mach es sichtbar, dass
  der Upload läuft. Mach es dynamisch, psychologisch den Ladescreen." Umgesetzt:
  - **Upload-Fortschritt:** Der Showcase-Call läuft jetzt über **XHR** statt `fetch`
    (`moUpload` mit `xhr.upload.onprogress`) — der Balken zeigt echten Upload-% (Video/
    Transkript) im Band 2–16%, dann übernimmt der Render. Vorher war der Upload eine
    Blackbox (fetch kann keinen Upload-Progress).
  - **Dynamischer Ladescreen:** Der Balken **kriecht immer weiter** (eased creep alle 340ms,
    lässt bewusst etwas Luft) — friert nie ein, auch zwischen den 1,5s-Polls. Rotierende
    „Regisseur"-Zeilen (`MO_MSGS`: „Directing the camera…/Adding motion blur…/Timing it to
    your voice…") wechseln alle 2,6s mit Fade. Der Frame bekommt einen **Shimmer**
    (`.mo-frame.loading::after`, Sweep-Gradient). Die Phase-Zeile spiegelt die **echte**
    Server-Phase (Preparing/Rendering/Encoding) — lebendig, aber ehrlich (kein Fake-%).
  - Fertig/Fehler stoppen Creep + Shimmer sauber; Verbindungsabbruch nach ~30s abgefangen.
  Selftest **678/678 grün**, UI-JS syntaxgeprüft (node --check). Rein Frontend; die echte
  Optik sieht Ismet live.
- **v118 Alt-Motion-Engines komplett entfernt — nur noch das Studio-Showcase (live).**
  Ismet: „Entferne alle andere mit Motion Design." Umgesetzt: der Motion-Wizard hat nur noch
  EINEN Weg — das Full-customizable **Studio** (Showcase / Kinetic / Prompt, alle Knöpfe).
  Alle vier Alt-Engines raus:
  - **Server:** Endpoints `/api/motion/brief`, `/api/motion/auto`, `/api/motion/render`,
    `/api/motion/preview`, `/api/motion/schema`, `/api/mov/{jid}` gelöscht; Worker
    `_run_motion_brief`/`_run_motion_auto` weg; `_run_motion` ruft nur noch
    `_run_motion_showcase`; der gfx_engine-Warm-Preview-Daemon (`_PreviewDaemon`) +
    `_motion_sanitize` + `MOTION_TEMPLATES/TRANSITIONS/COST_*` entfernt. Kein `gfx_engine.py`-
    Aufruf mehr aus dem Web (Datei bleibt auf Platte für den Desktop). Showcase-Helfer
    (`_whisper_words`, `MOTION_AUTO_MAX_*`, `cost_seconds`, `MOTION_BRIEF_OK`-Gate) bleiben.
  - **Motion-TS:** 27 Dateien gelöscht (MotionVideo/Motion3D/MotionApple/MotionSequence/
    MotionOverlay, SceneRenderer, three/apple/blocks, director/{autoDirect,autoGuards,run,
    run-auto,templates,heuristic,schema,vocabulary}, lib/{layout,overlap,motion,transitions},
    render-brief.mjs, render-auto.mjs, 3 Alt-Tests). `Root.tsx` registriert nur noch
    MotionShowcase/Kinetic/Prompt. `demo-spec.ts` Typ-Import von der gelöschten MotionVideo
    inlined. `tsc --noEmit` clean.
  - **UI:** 4 Typ-Karten + 6 tote Step-Views (upload/describe/template/style/build/render)
    raus; Studio bekam eine eigene Ergebnis-Ansicht (Video + Download, vorher in der geteilten
    render-Ansicht); tote JS-Funktionen (motionTemplateGo/BriefGo/SeqGo/AutoGo/Render/Preview/
    Spec/moSync/moGallery/renderSeqRows/moSeg/hexToRgb) entfernt; `MO_ENGINE_STEPS` = nur
    `studio`. JS syntaxgeprüft (node --check).
  - **Selftest:** ~30 tote Alt-Engine-Checks (v101w/y/z, v102/e, v103/b, v104/5/6, v107d,
    v108/b, v109b, v110, autoguards/templates/transitions-Node-Tests, PreviewDaemon) entfernt;
    3 neue v118-Garantien (Server/UI/Registry sind wirklich alt-frei). **677/677 grün**, GUI-
    Smoke grün, End-to-End-Render (SRT→1080×1920-MP4) grün. NUR Linux/CPU getestet.
- **v117d Transkript-DATEI-Upload im Studio (live).** Ismet: „Ich will, dass man da die
  Videos/Transkript als Datei hochladen kann. Dieser soll dann automatisch passieren." Umgesetzt:
  im Studio dritter Eingabe-Modus „Transcript file" neben „Script / text" und „A video".
  Akzeptiert `.txt/.srt/.vtt/.json`, wird automatisch geparst und verarbeitet — kein manuelles
  Abtippen. Neuer Parser `_transcript_to_words(filename, raw)`: SRT/VTT-Cues und JSON
  (`{word|text,start,end}` / `{"words":[…]}` / `{"segments":[…]}`) liefern ECHTE Wort-Timings
  (Segmente werden auf Wort-Ebene über die Cue-Dauer verteilt → Voiceover-Sync); TXT/Fallback
  bekommt synthetische Timings (0.32s/Wort). Text bleibt VERBATIM. Server: neuer Param
  `transcript_file` an `/api/motion/showcase` (max 4 MB), Ergebnis → `job['prewords']`, Worker
  nimmt vorhandene Wörter direkt (kein Whisper), Credits nach Transkript-Dauer/Wortzahl. Beweis:
  SRT „Upload your transcript / fully automatic / text stays verbatim" → geparst → gerendert,
  gültiges 1080×1920-MP4 (kinetic/bold). Selftest 713/713 (7 neue: SRT/JSON-word/JSON-segment/
  TXT-Timings/leer-robust + 2 Verdrahtungs-Garantien). NUR Linux/CPU getestet.
- **v117 Full-customizable Motion-Studio (live).** Neuer Weg im Motion-Wizard: „Studio — full
  control". Eingabe = Video ODER eigenes Skript/Transkript. Wählbar: Komposition (Card-Montage /
  Kinetik-Typo / Prompt-Build), Stil (editorial/bold/soft/mono), Format (9:16/1:1/16:9). Und ALLES
  einstellbar via Custom-Override (`showcaseThemes.applyTheme`, zieht durch alle 3 Kompositionen):
  Akzent, Textfarbe, Font (Sans/Mono/Serif), Versalien, Motion-Blur, Kamera-Intensität, Grain,
  Marke, Text pro Beat. Text bleibt VERBATIM (kein Halluzinieren). Server: `/api/motion/showcase`
  (+ `_run_motion_showcase`, `_sanitize_custom`), Credits nach Länge (Video) bzw. Wortzahl (Text).
  Bridge `render-showcase.mjs --custom-file`. Default-Marke überall DouchkoVE. Fix: Kinetik-Giant-
  Word passt jetzt in schmale 9:16-Formate. Selftest 706/706, tsc clean, End-to-End-Smoke grün.
  NUR Linux/CPU getestet — echte Wirkung live. Offen: Font-DATEI-Upload (aktuell Presets), Sound,
  Alt-Engines aufräumen.

- **v111d Logik-Pass: kohärentes Skript + interne Konsistenz (Ismet: "unfertiges Video, kein Senior gibt das so ab").**
  Kritik war berechtigt — der 1:1-Nachbau hatte zusammenhanglose Fragmente (aus den Referenz-
  Einzelframes kopiert) ohne roten Faden + interne Fehler. Behoben: (1) EIN kohärentes Skript
  läuft in logischer Reihenfolge durch alle Shots — "Your story deserves better motion / Not
  another template pack — real, hand-made design / [search] your transcript: every word / buttery
  smooth, Apple-style motion / never invented / the mechanics: real UI / frame by frame / perfectly
  timed to your voice / sixty frames a second / made with DouchkoVE". On-Screen-Text ist jeweils
  Phrase aus der Zeile (ehrt v110). (2) Timer-Card repariert: Ring FÜLLT sich und die Prozent-
  Anzeige zählt SYNCHRON mit hoch (eine Wahrheit statt Ring bewegt/Zahl steht) — "Well"/"Pause"-
  Platzhalter raus. (3) Apple-Logo raus (off-brand im eigenen Promo). (4) Widget-Card-Fremdinhalt
  ("Bart_VFX/34K views") → on-brand ("Real UI, real depth / built by hand"). (5) Pill "Never
  invented" bekommt ein einzeichnendes Häkchen statt sinnfreiem Mini-iPhone. (6) Hell/Dunkel-
  Strobing behoben: die zwei Dark-UI-Momente (Notes+Search) geclustert → nur noch 2 Value-Wechsel
  statt Geflacker. EHRLICH offen: noch stumm (Sound braucht CC0-Pack) — ein Senior liefert mit
  Sound-Design; visuell ist die Logik jetzt kohärent. Selftest 692/692, tsc clean, 60s-Video
  gerendert. NUR Linux/CPU/720p.
- **v111 MotionShowcase: 1:1-Nachbau des Referenz-Montage-Looks (Ismet: "Kann sowas gebaut werden?").**
  Neue self-contained Komposition `MotionShowcase.tsx` (+ in Root registriert, 16:9,
  Storyboard-Dauer ~27s) baut den kompletten Referenz-Clip (@beingmayy, 37s) Shot fuer Shot
  nach — als ECHTE UI-Objekte, nichts Abstraktes: (1) Kinetik-Typo weiss + echtes Apple-Vektor-
  Logo, (2) Timer-Card (Progress-Ring + "Well" + Pause, orange), (3) Dark Notes/Reader mit
  Nav-Chrome (Back/Share/•••/gelbes Haekchen) + tippendem Text + Lupe die reinspringt,
  (4) weisse Search-Bar die von oben reinfaellt + blauer Result-Link mit kurzem RGB-Chromatik-
  Split, (5) zweite Kinetik-Typo (orange "60 Frames Per Second"), (6) iMessage-Bubbles
  (gruen "🧈 Buttery Smooth" + blau "Apple Style Animations"), (7) Widget-Stage YouTube-Card
  ("So in today's video / Bart_VFX / 34K views / NEW") + Schraubenschluessel-Reihe + Cursor
  der reinfaehrt und tippt, (8/9) Pill-Buttons mit Mini-Device (blau "Track Order" + dark),
  (10) NLE-Timeline-Card (Ruler 00-04f + farbige Clips + laufender Playhead), (11) Marken-
  Sign-off (UNSER "made with DouchkoVE", nie das Quell-Wasserzeichen).
  KERN was Ismet wollte — die UEBERGAENGE: jeder Hand-off ist KAMERAGEFUEHRT (slideL/slideUp
  mit echtem gerichtetem Motion-Blur via 5 Ghost-Echos entlang der Bewegungsachse, scale-morph
  durch einen Punkt wie in der Referenz f_22, dolly-push), BEIDE Szenen bleiben scharf — NIE
  ein Blur-Dissolve (explizite Ismet-Regel). Und INTERAKTIV: `press` rampt in den letzten
  ~0.3s vor dem Hand-off hoch (Lupe wird gedrueckt, Cursor tippt, Pause-Button sinkt) und
  treibt die Kamerabewegung in den naechsten Shot. Alles pure in `t` (seekbar, RAM-flat,
  deterministisch, kein Math.random). Text ist DATEN (Storyboard) — die Komponente erfindet
  nichts; der KI-Regisseur koennte dieses Storyboard spaeter aus einem Transkript emittieren.
  BEWEIS: 11 Verifikations-Stills gerendert (jede matcht ihre Referenz: Notes≈f_7, Search≈f_10,
  iMessage≈f_16, Widgets≈f_19, Timeline≈f_31) + volles 27s-Video (1280x720, h264) gerendert.
  Selftest 690/690 gruen, tsc clean. NUR Linux/CPU/synthetisch — Feintuning am echten Material
  offen. OFFEN als Naechstes: Server/UI-Verdrahtung (eigener Motion-Typ) + KI-Shot-Wahl pro
  Transkript-Beat (der Weg zu "individuell fuer jeden").
- **v110 Transkript-Provenance: kein halluzinierter Text + Voiceover-Sync (Ismet-Bedingung).**
  Zwei harte Regeln fuer den Auto-Overlay durchgesetzt: (1) KEIN eingeblendetes Wort darf
  erfunden sein - jeder On-Screen-Text (headline/lowerthird/keyword/chips/stat-label) MUSS
  woertlich im gesprochenen Transkript stehen (oder der vom Nutzer gesetzte Markenname).
  (2) Timing laeuft am Transkript (Snap auf Wort-Onsets), damit es zu einem Voiceover passt.
  Umsetzung DETERMINISTISCH in autoGuards (`groundBeat`): nach normalisiertem Abgleich mit
  dem Transkript wird ungegroundeter Text NICHT gezeigt, sondern zu einem TEXT-FREIEN
  Grafik-Akzent degradiert (headline->pulse, lowerthird/chips->sweep, keyword->burst,
  stat->pulse) - Rhythmus bleibt, Halluzination raus. stat-Zahlen muessen ebenfalls
  tatsaechlich gesprochen sein (`nums.has(value)`), sonst degradiert. brand-Beat wird auf
  den vertrauenswuerdigen Markennamen gezwungen, nie Modell-Text. Der GPT-Regie-Prompt
  bekommt zusaetzlich die HARD RULE "NEVER invent text ... copy VERBATIM from the transcript".
  WICHTIG: die KI ist weiterhin Regisseur (welcher Moment, welche Behandlung) - sie ist
  nur nicht mehr Autor. Reine KI-Video-Generierung (veo/kling) waere hier falsch: sie
  wuerde Text-Pixel erfinden und nicht Wort-genau zum Voiceover sitzen - genau die zwei
  Dinge, die Ismet ausschliesst. BEWEIS: neuer Node-Unit-Test (erfundene Headline/Keyword
  degradiert, ungesprochene Zahl 999 raus, gesprochene 42 bleibt, chips gefiltert, brand
  erzwungen, jedes ueberlebende Wort im Transkript) gruen; Selftest 686/686. tsc clean.
  Nur Linux/CPU/synthetisch getestet - echte KI-Regie + Material erst live.
- **v108c (A) reine Grafik-Beats + (B) 16:9/1:1 fuer alle Engines (Ismet: "A und B").**
  (A) Der Auto-Overlay ist nicht mehr nur Text: 4 REINE GRAFIK-Beats ohne Text -
  burst (Impact: Ring + Funken-Burst), sweep (Akzent-Band wischt durchs Bild), pulse
  (Vollbild-Akzent-Energie), brackets (Fokus-Ecken schnappen ein). Guards akzeptieren
  sie (kein Text-Payload), Heuristik streut sie ein (kurze Zeile -> burst, Abschnitt ->
  sweep), KI-Prompt kennt sie ("mix these in for rhythm, restrained"). BEWEIS: 20s-Clip
  gerendert -> Regie mischt headline/chips/lowerthird/burst/keyword; Burst-Frame zeigt
  Ring + Funken ohne Text.
  (B) 16:9 UND 1:1 fuer Template + Sequence (waren fix 9:16): neuer DeviceStage -
  Hochkant-Mockup wird als ECHTES Device (gerundeter Bezel + Schlagschatten) zentriert
  auf einer Liquid-Glass-Buehne mit Akzent-Glow gerendert, NICHT gestreckt (AppleScene
  bekommt vw/vh-Override, MotionSequence-Transitions nutzen Stage-Masse). 9:16 bleibt
  full-bleed. Format-Wahl im UI (Template-Style + neuer Sequence-Schritt), Server reicht
  --format durch. Auto-Overlay war schon aspect-automatisch. BEWEIS: 16:9-Homescreen +
  16:9-Sequence gerendert - Phone sauber zentriert im Device-Frame. tsc clean.
  Regression 685/685.

- **v108 FULL-CUSTOMIZABLE: Video hochladen -> KI legt Motion-Graphics drauf (Ismet:
  "ein User laedt ein Video hoch, eine KI entscheidet was wie rein kommt. Muss unseren
  High-Quality-Standard erfuellen, wie ein Senior-Motion-Designer denken. Kein billiger
  Standard-Muell. Aufwendig, dynamisch, hand-made, logische Denkweise als Standard").**
  Entscheidungen (via Frage): Overlay AUFS Video + KI sieht Frames+Transkript + alles in
  einem Rutsch. Komplett neue Pipeline (getrennt von Captions):
  1) UPLOAD (/api/motion/auto): Video streamen (Cap 400MB/15min), Credits nach Laenge.
  2) VERSTEHEN: Whisper-Transkript (render.transcribe, Wort-Timings) + 6 Frames (ffmpeg).
  3) REGIE (autoDirect.ts, der Senior-Brain): GPT-5-VISION bekommt Transkript + Frames,
     REGIE_AUTO-Prompt (SENIOR MOTION DESIGNER: sparsam, aufs Wort gelandet, Bedeutung
     zuerst, Varianz der Platzierung, ans Material angepasst, kein Clutter) -> Plan von
     Beats {t,dur,kind,text,anchor,enter,emphasis}. Heuristik-Fallback (aus Wort-Timings:
     Hook-Headline, Keyword-Pops, Stat bei Zahlen, Chips, Lower-Thirds, Brand-Signoff)
     laeuft ohne Key/offline.
  4) LEITPLANKEN (autoGuards.ts, "logische Denkweise als Standard"): sanitize (Junk raus)
     -> Snap auf Wort-Onset -> sort -> KEIN Overlap (Atempause zwischen Beats) -> Dichte-
     Cap nach Videolaenge -> Anker abwechseln -> in Video clippen. Node-Unit-Test.
  5) RENDER (MotionOverlay.tsx): OffthreadVideo (Original-Ton bleibt) + Beats obendrauf,
     jede in Safe-Zone mit Senior-Animation (Feder-Entrance je Stil + Defocus-Out), eine
     Bildsprache (dunkles Glas + Akzent). Kinds: headline/lowerthird/keyword/chips/stat/
     brand. Brand: eigenes Logo (Pfeiler 2). Plattform-Safe-Zones (tiktok/reels/shorts).
  UI: 4. Motion-Typ "From your video" (Upload + Akzent + Plattform + Brand).
  BEWEIS: Ende-zu-Ende auf synthetischem Video (st_clip) + Heuristik gerendert -> Headline
  "Ich zeig dir heute wie wir Captions" + Akzentlinie, dann Chips im Lower-Band, getimt
  aufs Transkript, Original-Ton drin (overlay.mp4). 25s Render. tsc clean, Guards-Test
  gruen. Regression 683/683. EHRLICH: KI-Regie (GPT-5-Vision) ist hier NICHT getestet
  (kein Key) - nur der Render/Overlay + Heuristik + Guards; die echte Senior-Qualitaet
  der KI-Entscheidungen siehst Ismet erst live mit seinem Key auf echtem Material.

- **v107d Echtes GPU-Post ausprobiert - und es rendert auf CPU! (Ismet: "hatte doch
  gesagt, wir sollen es probieren").** Ich hatte Bloom/DoF als "braucht GPU" abgetan -
  Ismet wollte es trotzdem testen. Ergebnis: @react-three/postprocessing + postprocessing
  installiert, EffectComposer in Motion3D (im ThreeCanvas): ECHTES Bloom (mipmapBlur,
  luminanceThreshold 0.62 - die emissiven Screens/Glas-Blobs bluten jetzt echt Licht
  aus), ECHTES Depth-of-Field (Bokeh - Hero scharf, Seiten-Phones + Hintergrund weich)
  und Vignette - alles ueber WebGL-Render-Targets. Laeuft headless auf software-GL
  (--gl=angle), nur langsamer. RENDERZEIT-MESSUNG: ohne Post ~157s, MIT echtem Post
  ~319s (5,3 Min) fuer 8,4s/230 Frames - Post ~verdoppelt die Zeit. Deutlich edler
  (echtes Lichtausbluten + Kino-Tiefenunschaerfe statt DOM-Fake). Docker: npm ci zieht
  die neuen Deps ueber die committete package-lock.json. tsc clean. Regression 678/678.
  LEHRE: die CPU-Grenze war weniger hart als gedacht - Render-Targets gehen in ANGLE,
  nur teurer. (Motion-Blur weiter offen; DoF/Bloom sind jetzt ECHT statt gefaked.)

- **v107c 3D-Promo Finish-Pass: Reflexionen, Boden, Grade (Ismet: "bau alles ein,
  wir schauen wie lange es dauert").** Alles rein, was auf dem CPU-Server (software-GL,
  KEINE GPU) geht: (1) UMGEBUNGS-REFLEXIONEN - prozedurales Studio-HDRI-lite
  (equirect Canvas: dunkler Raum + helle Softbox-Streifen + warmer Boden) an
  scene.environment; Glas-Blobs (metalness 0.5, envMapIntensity 1.6) und Handy-Glas
  spiegeln jetzt Licht (groesster Realismus-Sprung, ohne PMREM/Render-Target). (2)
  GLOSSY-BODEN + accent-Glow-Pool (additiv) + weiche KONTAKTSCHATTEN unter jedem Device
  -> die Phones stehen im Raum statt zu schweben. (3) KAMERA-CHOREOGRAFIE: schneller
  Dolly-in mit Settle + langsamer Orbit-Bogen (easeInOut) statt konstanter Fahrt. (4)
  POST-GRADE (DOM): warm-kalter Kino-Tint (multiply) + Highlight-Lift (screen) +
  Vignette, plus etwas mehr Grain. BEWEIS: --3d gerendert (promo3d3.mp4) - Hero-Frame
  zeigt Glow-Pool am Boden, Vignette-Fokus, reflektierende Kanten. RENDERZEIT: ~157s
  (2,6 Min) fuer 8,4s Clip / 230 Frames auf CPU. tsc clean. Regression 677/677.
  EHRLICH - was echte GPU braucht (bewusst NICHT gebaut, wuerde hier nicht rendern):
  echtes Bloom/DoF/Motion-Blur (Postprocessing-Render-Targets), echtes Glas
  (Transmission), PMREM-geblurrte Reflexionen. Naechste Stufe = 3D auf GPU-Instanz.

- **v107b 3D-Promo realitaetsnah: echte Dark-Mode-Screens fliegen im Raum (Ismet:
  "passe es so realitaetsnah wie moeglich an, soll fluessig aussehen").** Statt leerer
  Kacheln tragen die fliegenden Panels jetzt ECHTE iOS-Dark-Screens: makeScreen() malt
  pro Variante einen kompletten Screen auf Canvas (Statusleiste 13:39/5G/Akku, Home =
  4x4-App-Grid + Glas-Dock, Chat = WhatsApp-Nav + gruene/dunkle Bubbles + Input, Notify
  = grosse Uhr + gestapelte Banner) -> THREE.CanvasTexture (SRGB, als map UND emissiveMap,
  damit die Screens wie eingeschaltet leuchten). Komposition wie ein echtes Produkt-Promo:
  Hero-Home-Phone gross mittig vorne, Chat-Phone links + Notify-Phone rechts faechern
  dahinter ein, gerundete Device-Koerper (transparente Ecken via Canvas-Alpha) + Bezel-
  Highlight + weicher Schlagschatten. Fluessig: Feder-Fly-in (damping 0.82) gestaffelt,
  danach sanftes Float+Sway, Kamera easeInOut-Dolly ueber 2.4s. Glas-Blobs nach hinten
  (Hintergrund-Glow), Bloom-Halo. BEWEIS: --3d headless gerendert (promo3d2.mp4) - Hero-
  Frame zeigt lesbaren Home-Screen (App-Grid, Dock, 5G-Statusbar), Seiten-Phones Chat +
  Notify, Kamerafahrt. tsc clean. Regression 676/676. EHRLICH: Screens sind Canvas-
  gezeichnet (getreue Nachbildung, nicht pixelgleich die React-Mockups); naechste Stufe
  waere echte Mockup-Frames als Textur + Reflexionen/DOF.

- **v107 Pfeiler 3: High-End-3D-Promo-Look (Ismet: "mach dich an Pfeiler 3 dran";
  Referenz Notion-Promo - rote Glas-Blobs, Produkt-Fly-in, Kamerafahrten).** Erste
  Version. Die bestehende 3D-Composition (Motion3D, --3d, Three.js) von abstrakten
  Metall-Solids zu einem Promo-Look umgebaut (motion/src/three/Scene3D.tsx): (1)
  gluehende GLAS-BLOBS im Zentrum - translucent-emissive Schale ueber hellem Kern +
  Wire-Rim (fake-Glas ohne Transmission, damit software-GL/ANGLE es rendert), atmen
  auf dem Beat; (2) fliegende DEVICE-PANELS - duenne dunkle Slabs mit emissiver
  Screen-Flaeche + gluehenden UI-Balken, fliegen per Feder gestaffelt aus der Tiefe
  ein, mit Perspektiv-Tilt; (3) additiver Bloom-HALO (CanvasTexture-Radialverlauf)
  hinter dem Hero; (4) KINO-KAMERA: Dolly-Push-In ueber die ersten ~2.2s + sanfter
  Orbit. Deterministisch (Seed + absolute Zeit, kein useFrame -> seekbar),
  software-GL-sicher (nur Standard/Basic-Material + Transparenz, KEINE Transmission/
  Render-Targets). Tuning-Pass: Blobs kompakter, Halo dezenter, damit die Panels
  lesbar bleiben. BEWEIS: --3d headless mit --gl=angle gerendert (promo3d.mp4, 7.3MB,
  230 Frames) - Frame-Streifen zeigt rote Glas-Blobs + einfliegende App-Panels + Glow
  + Kamerafahrt. tsc clean. Regression 676/676. EHRLICH: solider v1, aber noch Luft
  nach oben (Panels koennten echte gerundete Devices sein, Blobs glasiger, echte
  Mockup-Screens als Textur) - hier nur CPU/software-GL/synthetisch beurteilt.

- **v106 iOS-Dark-Mode-Re-Theme nach Ismets echten Screenshots (Ismet: "So sieht die
  UI aus ungefaehr, das ist meins. Orientiere dich daran").** Ismet schickte 4
  Screenshots seines echten iPhones (Home, WhatsApp, Einstellungen, Sperrbildschirm) -
  alles iOS DARK MODE. Die Mockups waren hell -> jetzt authentisch dunkel: INK ->
  hell (#f3f5fb), dunkles Glas (charcoal rgba(58,62,74)+backdrop blur/saturate statt
  weiss), dunkler Liquid-Hintergrund (near-black + warme Blobs; Wallpaper-Screens
  cinematic dunkel-warm). Statusleiste jetzt echt: 13:39, Signal, "5G", Akku-Pill
  (gelb, Low-Power). CHAT komplett auf WhatsApp-Dark neu: gruene Outgoing-Bubbles
  (#075e54) mit Tails + doppelten Read-Ticks (blau #53bdeb), dunkle Incoming-Bubbles
  (#1f2c33) mit Sender-Name im Akzent, Nav-Bar (Back, Avatar, Name, "online", Video +
  Call), Tipp-Indikator, echte Input-Bar (+, Feld mit Cursor, Sticker, Kamera, gruener
  Mic/Send-Button #25d366). Home/Notify: dunkle Wallpaper, weisse App-Labels, Glas-Dock,
  heller Lockscreen-Clock. (Ismets persoenliche Inhalte - Fotos, Name, Nachrichten -
  bewusst NICHT uebernommen, nur der Stil; Mockups nutzen generische Platzhalter.)
  Press-Interaktion + Liquid-Glass-Helper + Logo/Font bleiben. BEWEIS: 6-Segment-Kette
  dunkel gerendert (seq_dark.mp4) - Streifen zeigt alle 6 Templates im iOS-Dark-Look,
  Chat = WhatsApp-Dark. tsc clean. Regression 675/675.

- **v105 iOS-26 Liquid-Glass-Look + interaktive Transitions + Synth-Sounds raus
  (Ismet: "alle Templates im iOS-26-Liquid-Glass-Stil, damit alles aktuell bleibt.
  Transition muss interagieren - bei der Suche drueckt man suchen, dann kommt passend
  das naechste. Nimm die synthetischen Sounds raus, klingen grauenhaft").** DREI Sachen:
  (1) LIQUID GLASS ueberall: neuer glass()-Helper (durchscheinend, backdrop blur+saturate
  180%, Spekular-Rand, Tiefe) + farbiger Liquid-Hintergrund (LiquidBg: 3 Akzent-getoente
  Blobs, damit das Glas Farbe bricht). Angewandt auf Pills, App-Card, Search-Feld, Dock,
  Chat-Bubbles/Input, Notify-Banner - alles frosted Glas ueber vibrierender Farbe statt
  flachem Weiss. (2) INTERAKTIVE Transition: der Uebergang wird durch die Aktion der Szene
  AUSGELOEST. MotionSequence berechnet einen press-Ramp, der ~0.2s VOR dem Exit auf 1
  geht; AppleScene bekommt press und spielt die Bedien-Aktion: Search -> Feld leuchtet im
  Akzent auf, Waveform + Vorschlaege klappen weg (submit), Ripple; App-Card -> "Open"
  gedrueckt; Home -> erste App gedrueckt; Chat -> Sende-Button; Notify -> Banner. Erst die
  Aktion, DANN faehrt die Kamera. (3) Die 6 synthetischen SFX + gen_sfx.py GELOESCHT
  (klangen schlecht) - Verdrahtung bleibt dormant, Sequenz rendert stumm bis ein echtes
  Pack in public/sfx liegt (Regel "Stille besser als billiger Ton"). BEWEIS: 6-Segment-
  Kette gerendert - Glas-Look-Streifen (alle Szenen durchscheinend/farbig) + Search-Press-
  Streifen (tippen -> suchen druecken: Feld leuchtet, Vorschlaege weg -> naechste Szene
  faehrt rein). tsc clean. Regression 673/673.

- **v104 Pfeiler 2: eigene Bilder/Logos/Schriften ueberall (Ismet: "jeder soll seine
  eigenen Bilder, Logos, Schriften etc. ueberall einfuegen koennen").** Erste Version.
  EIGENES LOGO/BILD: ersetzt das App-Icon in App card, die erste Kachel im Home screen,
  den Chat-Avatar und das Notification-Icon - dein Logo zieht sich durch alle Szenen.
  EIGENE SCHRIFT: die hochgeladene Font faerbt ALLE Mockup-Texte (Titel, Labels,
  Nachrichten). Technik: Uploads werden serverseitig validiert (Bild-/Font-MIME, 4MB-Cap),
  als data-URI base64-kodiert und ueber eine Temp-Datei (assets.json, --assets=<pfad>) an
  den Director gereicht (data-URIs sind zu gross fuer argv). Der Director legt sie in
  spec.ui.logo bzw. spec.font (family 'DVEUserFont'). AppleScene rendert das Logo via
  Remotion <Img> (rundes Masken-Icon) und laedt die Font via FontFace unter delayRender
  (blockt bis bereit, wie die gebundelte Inter). Gilt fuer Template UND Sequence; UI:
  "Your brand (optional)" mit Logo- + Font-Upload in beiden Schritten. BEWEIS: App card
  einzeln + 4-Szenen-Kette (App card->Home->Chat->Notify) mit Test-Logo (teal Ø) +
  Serifen-Font gerendert - Logo erscheint in JEDER Szene, alle Texte in Serif
  (brand_appcard.mp4, brand_seq.mp4 an Ismet). tsc clean. Regression 671/671.
  OFFEN (bewusst v1): eigene Screenshots in den App-card-Strip / Bilder in pills+search
  als Brand-Mark; Font-Weight-Achse; Brief-Pfad (MotionVideo) bekommt Logo/Font noch nicht.

- **v103c Transitions umgebaut: interaktiv/kamera-raeumlich statt Blur (Ismet: "Ich
  will NICHT, dass die Transition out in Blur ist. Ich will, dass sie interaktiv ist -
  eins wird angezeigt, dann wird das andere passend reingeschoben, Kamera schwenkt").**
  Der komplette Defocus/Blur-Ansatz ist raus. Neue Bibliothek = 6 KAMERA-Hand-offs,
  BEIDE Szenen bleiben rasiermesser-scharf: push (horizontaler Kamera-Pan, zwei Screens
  Kante-an-Kante, voll deckend), panv (vertikaler Pan, naechste Szene schiebt von unten
  hoch), cover (aktuelle Szene haelt + sinkt minimal, neue rutscht mit elastischem
  easeOutBack drueber), dolly (Kamera-Push-Through: raus skaliert weg, rein steigt aus
  kleinerem Frame - scharf), swoosh (horizontaler 3D-Schwenk rotateY + Perspektive,
  wuerfelartig), tilt (vertikaler 3D-Schwenk rotateX). Erste Szene = sauberer
  Scale+Fade-Intro, letzte = Scale+Fade-Outro (KEIN Blur). Affine: blur/blurX raus,
  rotateX rein. Sound-Mapping neu (alle 6 Files weiter genutzt): push->whoosh,
  panv->swish, cover->click, dolly->whoosh2, swoosh->pop, tilt->airy. Auto-Variety +
  pro-Szene-Override unveraendert; UI-Dropdown-Labels neu (Camera pan/tilt, Slide over,
  Dolly in, 3D swing/flip). BEWEIS: 6-Segment-Kette neu gerendert (seq_cam.mp4) -
  Frame-Streifen zeigt scharfe raeumliche Hand-offs (zwei Screens gleichzeitig scharf
  beim Pan, 3D-Tilt sichtbar), Ton weiter exakt an den 5 Grenzen. tsc clean, Node-Unit-
  Test angepasst (Identity-Enden, KEIN Blur-Feld, Alpha in Range). Regression 667/667.

- **v103b Mehrere verschiedene aufwaendige Transitions + Sound-Verdrahtung (Ismet:
  "mehrere passende verschiedene aufwaendige Transitions, wie von einem High-End-
  Senior-SaaS-Motion-Designer. Ausserdem den passenden Sound").** Statt EINER Blur-
  Cross gibt es jetzt eine Transition-Bibliothek (motion/src/lib/transitions.ts) mit
  6 Arten: Blur-Zoom (airy), Push (cleaner iOS-Nav-Slide), Whip-Pan (mit ECHTER
  direktionaler Motion-Blur via SVG feGaussianBlur stdDeviation="x 0", Peak in der
  Mitte), Glass-Slide (steigt von unten mit elastischem easeOutBack-Overshoot +
  Fokuszug), App-Open/Iris (zoomt aus kleiner zentrierter Kachel), 3D-Swoosh
  (flacher rotateY-Handoff mit Perspektive). Jede Transition hat sauber Identity an
  ihrem aufgeloesten Ende (Node-Unit-Test prueft das). Auto-Variety: pickTransitions
  laeuft die kuratierte Reihenfolge mit Stride 5 (coprim zu 6) ab -> KEINE zwei
  benachbarten Grenzen gleich, deterministisch aus dem Seed. Optional pro Szene im
  Wizard fixierbar (Dropdown "Auto/Whip/Glass/App open/Push/3D swoosh/Blur zoom";
  erste Szene = "Start", inert). SOUND: pro Transition ein SFX-Key, gemountet als
  Remotion <Audio staticFile('sfx/<key>.wav')> genau am Swipe-Peak - ABER nur wenn
  das CC0-Asset wirklich existiert (Director fs-prueft public/sfx, setzt spec.sfx).
  Kein Pack -> stumm (Projektregel "Stille besser als billiger Ton"). BEWEIS: 6-
  Segment-Kette (25.6s) headless gerendert -> 5 sichtbar verschiedene Uebergaenge
  (Frame-Streifen an Ismet, Whip-Motion-Blur klar zu sehen). tsc clean, Transition-
  Node-Unit-Test gruen (Identity-Enden, kein Repeat, Override sanitisiert).
  Regression 666/666.
  SOUND-NACHTRAG: Ismet-Entscheid = "Sounds selbst designen" (ausdrueckliches OK,
  bewusste Ausnahme der CC0-Regel NUR fuer Motion-Transition-SFX). 6 Sounds selbst
  synthetisiert (motion/scripts/gen_sfx.py, echtes Sound-Design: zeitvariabler
  Chamberlin-SVF-Bandpass auf geformtem Rauschen, Pitch/Formant-Sweeps passend zur
  Bewegung, saubere Attack/Decay-Huellkurven, Stereo-Breite - KEINE Beeps):
  whoosh(whip), whoosh2(3D-swoosh, mit Doppler-Shimmer), swish(glass), airy(blurzoom),
  click(push, 60ms-Transient), pop(iris, Pitch-Drop). 48kHz Stereo in public/sfx/.
  BEWEIS: 6-Segment-Kette neu gerendert MIT Ton (AAC-Stereo im MP4); Audio-Analyse
  zeigt exakt 5 Bursts an den Grenzen (3.88/7.91/12.34/16.37/21.41s) und ECHTE Stille
  dazwischen. Regression 667/667. (An Ismet: seq_sound.mp4.)

- **v103 Sequencer + seamless Transitions (Ismet, Referenz Notion-Promo: "Die
  Motion muessen genau so aneinander geknuepft werden koennen mit guten seamless
  Transitions - es soll die 50 Stunden Arbeit abnehmen").** Erster von 3 Pfeilern.
  Mehrere Mockups werden jetzt zu EINEM Video verkettet - mit weichen Blur-Zoom-
  Crossuebergaengen statt harten Schnitten. NEU: MotionSequence-Composition
  (motion/src/MotionSequence.tsx) nutzt Remotions <Sequence> pro Segment (lokale
  Zeitachse), ueberblendet 0.55s Ueberlappung (SEQ_TRANSITION) via easeOutQuint-
  Rein + easeInOutCubic-Raus, scale 1.0->1.1 + blur 16px->0, jedes Segment eigener
  Seed. sequenceSpec() (templates.ts) baut den Ketten-Spec (dur = Summe minus
  Uebergaenge). run.ts: --sequence=<json> -> sequenceSpec (trusted, skip strict
  Zod). render-brief.mjs routet isSequence -> MotionSequence. Server
  (/api/motion/brief): neues Form-Feld sequence (max 8 Segmente, je {template,
  text}, gegen MOTION_TEMPLATES validiert, <2 -> ignoriert), gibt --sequence=
  durch. UI: dritter Typ "Sequence" (Wizard-Fork sequence:[type,build,render]),
  Build-Schritt mit Szenen-Zeilen (+ Add scene) + Akzentfarbe, motionSeqGo() POSTet
  die Kette. BEWEIS: 4-Segment-Kette (pills->appcard->chat->notify, --accent=
  #e0483d) headless gerendert -> 17.6s MP4 mit sichtbaren Blur-Cross-Uebergaengen
  (Frame-Streifen an Ismet). tsc clean, Node-Render OK. Regression 662/662 gruen.
  OFFEN (2 weitere Pfeiler, bewusst separat): eigene Bilder/Logos/Schriften ueberall
  einfuegen; High-End-3D-Promo-Look. EHRLICH: nur Linux/CPU/synthetisch + software-
  GL getestet; echte Optik sieht Ismet live.

- **v102e Fix: mehrwortige Template-Eingaben (Ismet: "Search mit mehr als 1
  Wort klappt nicht - solche Logikfehler vermeiden, bei allen").** URSACHE: ein
  generischer parts()-Splitter zerlegte den Text bei fehlendem Komma per
  Leerzeichen und nahm p[0] -> 'Ask anything' wurde 'Ask'. FIX: jedes Template
  hat jetzt seine eigene, robuste Parsing-Logik (neue reine Funktion
  parseTemplateText): search = GANZE Phrase (nie wortgesplittet); appcard/notify/
  chat = komma-basiert (mehrwortige Felder bleiben ganz), degradiert sauber bei
  odd input; pills = Komma ODER Woerter. 10-Faelle-Node-Unit-Test
  (motion/scripts/test-templates.mjs) laeuft jetzt IM Selftest mit (graceful skip
  ohne node). Search+App-Card mehrwortig neu gerendert (voller Text) an Ismet.
  Regression 658/658 gruen.

- **v102d Chat-Tipp-Indikator (3 Punkte).** Vor jeder EINGEHENDEN Nachricht
  pulst ~0.7s eine graue "..."-Bubble (3 wellen-animierte Punkte), dann poppt die
  Nachricht. Ausgehende Nachrichten haben keinen Indikator. tsc clean, gerendert,
  656/656 gruen. (Bestaetigt: das GESAMTE Mockup-Set ist reines Remotion/React.)

- **v102c UI-Mockups mit Realismus-Detail (Ismet: "mehr Detail + Politur, als
  waere es echt").** Jede der 6 Mockups liest sich jetzt wie ein echter iOS-Screen.
  Geteilte STATUSLEISTE (9:41 + Signal/WLAN/Akku als Vektor) auf Search/Home/
  Notify. App card: echte App-Store-Produktkarte - Icon, ★★★★★ 289K, Open,
  SCREENSHOT-STRIP (3 Platzhalter mit UI-Andeutung, gestaffelt rein), Statzeile
  mit Trennlinien. Search: "Search"-Titel + Feld + Waveform + SUGGESTIONS-Dropdown
  (4 Zeilen mit Lupe). Home screen: 4x4-Grid mit APP-LABELS, PAGE-DOTS, frosted
  DOCK (4 Icons, backdrop-blur), Badge. Chat: echte iMessage-Ansicht - NAV-BAR
  (Back-Chevron, Avatar-Initiale, Kontaktname), Bubbles mit Tails, DELIVERED-
  Receipt, EINGABELEISTE ("iMessage" + Sende-Button). Notify: LOCKSCREEN (grosse
  9:41 + Datum) + gestapelte frosted Banner. accent->HSL-Ableitung faerbt Icons
  konsistent. Chat-Feld jetzt "Kontakt, Nachrichten" (p[0]=Name). Alles rein
  vektoriell (kein Emoji) -> headless-sicher. GEPRUEFT: tsc clean, alle 6 neu
  gerendert (2x3-Grid an Ismet). Regression 656/656 gruen.

- **v102b UI-Mockup-Templateset komplett (Ismet: "alte Templates loeschen, diese
  hier rein, alle auf einmal, Apple auf der Seite nicht erwaehnen").** Die alten
  Bloeck-Templates (title/lowerthird/stat/quote) sind RAUS; das Templateset ist
  jetzt die 6 UI-Mockups aus der Referenz, alle als Remotion-Szenen (MotionApple,
  Light-Theme): Pills (embosst) / App card (Store-Download-Karte: Icon, Titel,
  Open-Button, 4.8-Stern/12+/#1-Statzeile) / Search bar (Lupe + tippender Query +
  Waveform) / Home screen (App-Grid mit Badge, gestaffeltes Pop-In) / Chat
  (iMessage-artige Bubbles, ab-/eingehend) / Notification (Banner dropt von oben
  mit Icon/Titel/Body/"now"). Datenmodell: SceneSpec bekam `ui`-Payload
  {template,title,subtitle,lines,accent} (+ Zod optional); templateSpec baut nur
  noch UI-Specs; run.ts ueberspringt die strikte Validierung fuer die (trusted)
  Template-Specs; render-brief.mjs routet ALLE Templates auf MotionApple; Icons/
  Sterne/Sparkles rein VEKTORiell (kein Emoji -> headless-sicher). Server-Template-
  Liste + UI-Galerie + Feld-Hinweise auf die 6 umgestellt; Text-Mindestlaenge
  template-tauglich (Search/Home kurz/leer ok). WICHTIG: "Apple" wird auf der
  Seite NICHT beworben - neutrale Labels (App card / Search bar / Home screen …),
  Selftest-Garantie prueft das. GEPRUEFT: tsc clean, alle 6 headless gerendert
  (2x3-Grid an Ismet). Regression 656/656 gruen. Alte Python-gfx-Endpunkte
  bleiben ungenutzt im Server.

- **v102 Apple/iOS-Mockup-Look (Ismet-Referenzvideo: "solche Motion Graphics
  rede ich die ganze Zeit").** Referenz = der helle Apple-UI-Stil (App-Icon-Reveal,
  App-Store-Karte, Such-Bar, Homescreen, premium embosste Pills) - genau die
  frueher zurueckgestellte widgets/appstore/chat/notify-Familie. FLAGGSCHIFF
  gebaut: die hellen 3D-Pills. Neu motion/src/apple/AppleScene.tsx +
  MotionApple.tsx (eigene Composition, Light-Theme): weiches Blau-Weiss-
  Gradientfeld, weisse embosste Pills (Drop-Shadow + Innen-Highlight + Hairline,
  dunkler Text), staggered entrancePose-Feder + Blur-In, schwebende Vektor-
  Sparkles (Akzent + Gold, headless-sicher statt Emoji). render-brief.mjs routet
  APPLE-Templates (pills) auf MotionApple; Root registriert die Composition. Das
  "Pills"-Template rendert ab jetzt genau den Referenz-Look (kein UI/Server-Umbau
  noetig - laeuft ueber den bestehenden template-Pfad). GEPRUEFT: tsc clean,
  headless gerendert (Frame-Streifen deckungsgleich mit der Referenz) - Video an
  Ismet. Regression 655/655 gruen. NOCH offen (bewusst, je eigener Build):
  App-Store-Karte, Such-Bar, Homescreen, Chat, Notify.

- **v101z2 Template-Animation auf Senior-SaaS-Niveau (Ismet: "smooth, high end,
  wie ein Senior SaaS Motion Designer").** Die Remotion-Bloecke (chipRow/kinetic
  Headline/statCard/bigQuote/accentUnderline) hatten nur eine Basis-Feder + Fade.
  Neu lib/motion.ts: `entrancePose()` (Feder-Overshoot + Slide + FOCUS-PULL-Blur,
  der beim Landen aufloest), `idleFloat()` (winziges Leben im Halten statt
  Standbild), `blurCss()`. Angewandt: ChipRow poppt verwuerfelt-gestaffelt mit
  Blur-In + weichem Akzent-Schatten; KineticHeadline zieht pro Wort aus dem Fokus
  (wordPose.blur); StatCard federt + zaehlt eased hoch; BigQuote-Anfuehrung landet
  einen Tick vor der Zeile; AccentUnderline zieht mit hellem, mitlaufendem Node +
  Glow-Puls entlang eines Tracks. Szene-Ebene (overlap.ts): Idle-Float im Hold +
  Rack-Focus-Defocus (Blur) beim Ausgang statt hartem Fade; SceneRenderer legt den
  Szenen-Blur auf. Alles deterministisch/seekbar (pure in t). GEPRUEFT: tsc clean,
  Templates headless neu gerendert (Pills-Stagger-Blur-In + Big-Stat-Feder-Count
  sichtbar) - Videos an Ismet. Regression 654/654 gruen. Wirkt auch auf den
  KI-Brief (gleiche Bloecke) - hebt die ganze 2D-Engine.

- **v101z Templates ueber Remotion statt alter Python-gfx-Engine (Ismet: "Template
  raus, das ist alte Python; ueber Remotion einfuegen").** Der Motion-Wizard nutzt
  jetzt AUSSCHLIESSLICH Remotion. Kuratiertes Template-Set aus den vorhandenen
  Bausteinen: Pills (chipRow), Title (kineticHeadline), Lower third (headline +
  accentUnderline), Big stat (statCard, zaehlt hoch), Quote (bigQuote). Neu
  motion/src/director/templates.ts: `templateSpec(id,text,{accent,format})` ->
  deterministische SceneSpec; run.ts-Zweig rendert bei `--template=<id>` das
  Template statt der KI-Regie; render-brief.mjs reicht --template/--accent/--format
  durch (Templates immer 2D MotionVideo). Server: /api/motion/brief nimmt template
  + accent (validiert gegen MOTION_TEMPLATES / Hex), _run_motion_brief haengt
  --template/--accent an. UI: der Template-Schritt zeigt die Remotion-Templates
  (Text-Kacheln), Style-Schritt auf Akzentfarbe + Format reduziert; die alte
  gfx-Bewerbung (Studio/Dark/Bold/Mono, Motion/Grain, Bild-Insert, MOV-Seg) ist
  raus, moRender feuert jetzt motionTemplateGo -> denselben Remotion-Brief-Endpunkt.
  BEWIESEN: 3+1 Templates headless gerendert (Pills/Lower-Third/Stat, akzentfarben)
  + Playwright-Screenshot des Schritts an Ismet; tsc clean. 2 neue Garantien,
  Regression 654/654 gruen. Die Python-gfx-Endpunkte (/api/motion/render|schema|
  preview) bleiben im Server, werden vom Wizard aber NICHT mehr genutzt (spaeter
  entfernbar). NOCH nicht portiert (bewusst, spaeter): widgets/appstore/chat/notify.

- **v101y Motion als Schritt-fuer-Schritt-Wizard (Ismet: "Mach Motion genau so
  wie Captions, step by step").** Die Motion-Seite war ein Ein-Bildschirm-Formular
  (alles auf einmal); jetzt fuehrt sie wie der Caption-Flow durch nummerierte
  Schritte mit eigenem Stepper. Schritt 1 "What do you want to make?" gabelt in
  zwei Engines; der Stepper ist ENGINE-ADAPTIV: Brief-AI = Type/Describe/Generate
  (3), Template = Type/Template/Style/Generate (4). Pro Schritt eine Karte + Back/
  Continue, klickbare Stepper-Chips (nur zurueck/aktuell), Generieren erst im
  letzten Schritt (richtiger Button je Engine eingeblendet, Ergebnis inline).
  Reiner Frontend-Umbau: alle Element-IDs erhalten -> bestehende Wiring
  (motionBriefGo/motionRender/motionPoll/moSync/moSeg) unveraendert; goMoStep/
  setMoEngine/renderMoStepper neu. BEWIESEN: Playwright-Screenshots aller Schritte
  (Type, Describe, Template) an Ismet - Stepper + Karten rendern sauber. 1 neue
  Quelltext-Garantie, Regression 652/652 gruen.

- **v101x Captions & Motion als getrennte Produkte (Ismet: "Leute brauchen nur
  Motion ODER nur Captions - loes das").** Beide Zielgruppen bekommen jetzt einen
  klaren, eigenen Einstieg statt in EIN Tool getrichtert zu werden. LANDING:
  Zwei-Produkt-Hero ("Two tools for one job") mit zwei Karten -> Auto-Captions
  (/app#create) und Motion Graphics (/app#motion), je eigener Deep-Link; darunter
  ein eigener Produkt-Abschnitt pro Tool (#captions / #motion) mit eigenem Titel,
  Feature-Grid und CTA; Nav Captions/Motion/Pricing. Motion-Sektion bewirbt das
  echte 3D. APP: Erst-Besuch-Auswahl "What are you here to make?" (#toolChooser)
  -> routet direkt ins gewaehlte Tool; routeFromHash akzeptiert /app#motion UND
  #/motion (Landing-Deep-Link); das zuletzt genutzte Tool wird gemerkt
  (localStorage dve_tool) -> ein Motion-only-Nutzer landet naechstes Mal direkt in
  Motion. BEWIESEN: Playwright-Screenshots (Landing-Hero + In-App-Chooser rendern
  sauber) an Ismet. 2 neue Quelltext-Garantien, Regression 651/651 gruen. Landing
  bleibt Englisch/international, keine Konkurrenznamen, kein Datenschutz-Block.

- **v101w Echtes 3D fuer die Motion-Graphics (Ismet: "Ich will 3D, high end").**
  Die Brief-Motion-Graphics sind jetzt echtes 3D via Three.js (@remotion/three) -
  keine 2.5D-CSS mehr. Neu im motion/-Stack: Scene3D (R3F) - facettierter Metall-
  Hero-Koerper mit PBR-Material (metalness 0.85), der ueber die Szenen morpht
  (Ikosaeder/Torusknoten/Oktaeder/Dodekaeder), ein Ring tiefen-gestreuter 3D-
  Splitter, Drei-Punkt-Licht (Key weiss / Rim Akzent / Fill), langsam driftende
  Kamera (CameraRig, imperativ -> seekbar), Beat-Puls, Fog fuer Tiefe; Motion3D-
  Composition (gleicher SceneSpec-Vertrag) mit Farbwelt-Gradient hinter transp.
  ThreeCanvas + Grain. render-brief.mjs `--3d` -> rendert Motion3D mit `--gl=angle`
  (SwiftShader-Software-GL, headless, GPU-LOS). Server + UI: 3D-Toggle im Brief-
  Panel (default AN) -> /api/motion/brief d3 -> --3d. Deterministisch (Position aus
  Seed, Bewegung aus absoluter Zeit, kein useFrame -> Remotion kann jeden Frame
  seeken). GEPRUEFT in der Sandbox: Feasibility-Spike (Torusknoten headless
  gerendert) UND voller 3D-Brief-Clip (278 Frames -> 1080x1920, 10.3 MB, Metall-
  Hero + Splitter + Kamera-Drift) - Strip + Video an Ismet. tsc clean (R3F-JSX via
  @ts-nocheck, Rest voll typisiert). Regression 649/649 gruen. EHRLICH: headless-3D
  bewiesen mit dem Playwright-Chromium; prod nutzt Debian-`chromium` (apt) - dessen
  `--gl=angle`-Software-GL muss beim ersten Deploy verifiziert werden. 2D bleibt
  ueber den Toggle waehlbar.

- **v101v Resumable Chunk-Upload (Ismet: "Upload bricht ab, wenn ich am Handy den
  Tab wechsle").** DER echte Fix: ein normaler fetch/XHR-Upload stirbt, sobald der
  mobile Tab in den Hintergrund geht (Screen-Lock, App-Wechsel) - die ganze Datei
  war weg. Jetzt laedt die Datei in 2-MB-Chunks: Server-Endpunkte
  `/api/upload/init` (Session + leere Zieldatei, Auth/Endung/Cap vorab),
  `/api/upload/chunk/{up}?offset=N` (haengt an genau der Byte-Grenze an; partial-
  safe via seek+write+truncate; falscher Offset -> 409 mit Serverstand),
  `/api/upload/status/{up}` (Resume-Punkt), `/api/upload/finish/{up}` (Dauer/
  Credits/Job/Queue). Frontend `chunkedUpload()`: schickt Chunks sequentiell,
  pausiert bei `document.hidden` (waitVisible) und SETZT beim Zurueckkommen an der
  vom Server bestaetigten Grenze FORT, Retry mit Backoff + Offset-Resync bei
  Netz-Abriss. Beide Upload-Wege (Render + Hintergrund-Vorab) laufen darueber; der
  Einmal-Upload bleibt als Fallback. Gemeinsamer `_finalize_upload()` (kein Credit-
  Logik-Drift). BEWIESEN: Live-Integrationstest gegen echten Server - init ->
  erzwungenes 409-Resync -> Resume -> finish, Datei byte-identisch reassembliert,
  Job angelegt; Alt-Upload weiter gruen. 2 neue Quelltext-Garantien. Regression
  647/647 gruen. EHRLICH: iOS Safari kann NICHT im Hintergrund weiterladen (kein
  Background-Fetch) - der Upload PAUSIERT beim Tab-Weg und laeuft beim Zurueck-
  kommen weiter; er bricht aber nie mehr ab / verliert nichts.

- **v101u Handy-Weggehen + kein Caption/Akzent-Overlap + High-End-Akzente
  (Ismet-Batch).** DREI Dinge auf einmal: (1) HANDY: Fertig-Mail existiert schon
  (_notify_job_done, Caption + Motion, verifizierte Accounts, 1x/Job) - jetzt sagt
  es die Render-Seite auch klar an ("Close the tab - we'll email you", nur bei
  verifiziertem Account per progMailNote). (2) KEIN OVERLAP: die Captions dieses
  Produkts sitzen ~0.40H (Mitte) - Akzente in bl/br kollidierten. Neu
  resolve_accent_positions() legt die Akzent-Position EINMAL vor dem Rendern gegen
  die echten Caption-Boxen im jeweiligen Zeitfenster fest (_caption_boxes) und hebt
  einen kollidierenden Akzent knapp UEBER die oberste Caption; danach stabil (kein
  Per-Frame-Springen). (3) HIGH-END-OPTIK: _accent_sprite komplett aufgewertet auf
  Senior-Niveau - weicher Schlagschatten (Lesbarkeit auf JEDEM Footage),
  Akzent-Aussenglow, Glas-Pille mit Vertikal-Gradient, Akzent-Rand, Punkt-Glow,
  Counter mit Fortschritts-Fuellbalken, Badge = Vektor-Haken, pop = Text +
  Unterstrich-Wisch (alles via PIL GaussianBlur, deterministisch). BEWIESEN:
  echter Render (Frames + Video an Ismet), Overlap-Unit-Test (Akzent-Unterkante <=
  Caption-Oberkante). 4 neue Tests. Regression 645/645 + render1 7/7 gruen.
  EHRLICH: Optik-Feinschliff + KI-Platzierung final erst auf echtem Material/GPU.

- **v101t Auto-Akzente Etappe 3/4: Editor (sehen/aendern/loeschen/hinzufuegen).**
  Die Akzente sind jetzt im Momente-Editor kuratierbar. render.py schreibt den
  Akzent-Plan ZUSAMMEN mit den Momenten (bei der Ausgabe/plan-only), sodass er im
  Editor vorliegt; der Voll-Render laedt danach nur noch (editierte Datei gewinnt).
  Server: `GET /api/accents/{jid}` (Plan laden) + `save_and_render` nimmt
  `accents`-Form entgegen und schreibt `<base>_accents.json` ("[]" = bewusst alle
  entfernt). UI: neue Sektion "Motion-graphic accents" unter der Momente-Tabelle -
  pro Akzent Zeit / Text / Art (counter/chip/badge/pop) / Position (4 Lanes) /
  an-aus + Loeschen, dazu "+ Add accent". sanitize_accents ehrt jetzt eine gueltige
  Nutzer-Lane (Editor gewinnt), rotiert nur fehlende. BEWIESEN: plan-only schreibt
  den Akzent-File (2 Akzente), eine simulierte Editor-Aenderung ("MY EDIT", Lane
  bl) ueberlebt den Re-Export unveraendert. 3 neue Tests (Lane-Ehrung, Server-+UI-
  Quelltext-Garantien). Regression 642/642 gruen. OFFEN: Stil-Profil pro Konto
  (Etappe 4). Browser-Smoke NICHT gelaufen (node --check + Quelltext-Garantien
  gruen) - Live-Klick erst nach Deploy verifizierbar.

- **v101t Auto-Akzente Etappe 2/4: Compositing ins Caption-Video.** Der dezente
  Akzent wird zum kleinen Alpha-Sprite und sitzt jetzt WIRKLICH im Video. Neu in
  render.py: `_accent_sprite()` (PIL-RGBA: dunkle Glas-Pille, Akzent-Rand + -Punkt,
  weisse Bold-Type; counter=Punkt+Hochzaehlen, chip=Punkt, badge=Vektor-Haken,
  pop=betonter Text + Unterstrich-Wisch), `_accent_place()` (Lane -> Ecke im
  OBEREN Band, safe-zone-fromm ueber platform_safe_zones, meidet die Caption-Zone
  unten), `draw_accents()` (Feder-Einflug/Halt/Abgang, Counter zaehlt hoch, reine
  paste()-Blits). Pipeline: nach build_plans wird der Akzent-Plan geladen (editierter
  `<base>_accents.json` hat Vorrang -> Etappe 3 Editor; sonst ai_accents/Heuristik,
  dann geschrieben = editierbar), gestylt vom Profil; die Render-Schleife legt die
  Akzente nach den Captions oben drauf. BEWIESEN: echter Ende-zu-Ende-Render des
  Test-Clips mit 2 Akzenten (Counter "3 MILLION" oben-links, Chip "VERIFIED"
  oben-rechts) - Frames + Video an Ismet, Akzente kollidieren nicht mit den
  Captions. 5 neue Compositing-Tests. Regression 640/640 + render1 7/7 + render2a
  1/1 gruen. NUR im finalen MP4 (Alpha-Caption-Export noch ohne Akzente - separat).
  OFFEN: Editor-UI (Etappe 3), Profil-Speicher pro Konto (Etappe 4). EHRLICH:
  KI-Platzierung erst live mit Key + echtem Material final; hier Heuristik/synthetisch.

- **v101s Auto-Akzente Etappe 1/4: Akzent-Regie (Ismet: "Transkript mit passenden
  Motion Graphics bestuecken, dezent, individuell, editierbar").** Fundament fuer
  automatische DEZENTE Motion-Graphics-Akzente auf dem Caption-Transkript - KEIN
  B-Roll (Finishing-Linie bleibt). Neu in render.py: `ai_accents()` (GPT-5 waehlt
  WENIGE Stellen + Art: counter/chip/badge/pop, Spiegel von ai_direct),
  `heuristic_accents()` (deterministischer Notnagel ohne Key: echte Zahl->counter,
  markanter Begriff->chip), `sanitize_accents()` (harte Leitplanke: Dichte-Cap,
  Mindestabstand 3.5s, gueltige Arten/Lanes, Lane-Rotation), `accent_style()`
  (persoenliches Stil-Profil: accent-Farbe/intensity/vibe dosiert die Dichte).
  config.yaml `accents:`-Block (auto/ai_model gpt-5/intensity). BEWUSSTE
  ENTSCHEIDUNGEN (Ismet, per Frage): Auto-Vorschlag + im Editor editierbar /
  dezente Akzente statt voller Grafik-Szenen / persoenliches Stil-Profil (baut auf
  Korrektur-Gedaechtnis). NOCH NICHT verdrahtet (folgt Etappe 2-4): Editor-UI,
  Compositing ins Video, Profil-Speicher pro Konto - DAHER laeuft im echten Render
  noch KEIN Akzent (rein additives Fundament, kein Kostentreiber). 9 neue Tests
  (Cap, Counter-auf-Zahl, Mindestabstand, Lane-Rotation, Fuellwort-Filter,
  sanitize-Leitplanke, Key-loser Notnagel = Heuristik, Intensitaets-Dosierung).
  Regression 636/636 gruen. EHRLICH: KI-Trefferqualitaet (ai_accents) erst live
  mit Key + echtem Material beurteilbar; hier nur Heuristik + Invarianten.

- **v101r Motion Graphics OHNE Text (Ismet: "Ich will Motion Graphics, kein Text").**
  Bisher war der Brief-Output reine kinetische TYPOGRAFIE (Headline/Stat/Quote).
  Jetzt hat die Remotion-Engine ein echtes GRAFIK-Vokabular: 5 neue Full-Bleed-
  Blocks (`gradientMesh` lebendes Farbfeld / `glowOrb` Licht-Sphaere mit Bloom +
  rotierendem Specular-Sweep + Beat-Puls / `orbitRings` rotierende Ringe mit
  wanderndem Arc + Glow-Node / `shapeField` gestreute Geo-Formen mit
  verwuerfeltem Spring-Stagger + Parallax / `waveLines` beat-reaktive
  Soundwave). Alle deterministisch (closed-form Spring + seeded PRNG, kein
  Math.random), Beat-gekoppelt ueber neuen `beatPulse()`. NEUER "No text"-Modus:
  Checkbox im Brief-Panel (default AN) -> `/api/motion/brief?no_text=1` ->
  `render-brief.mjs --no-text` -> Director/Heuristik emittiert NUR Grafik-Blocks,
  null Wort auf dem Screen. Default-Pfad (Text) legt die Grafik jetzt HINTER die
  Typo (mesh immer slot 0, Text via zIndex darueber) -> auch Text-Clips sehen
  nicht mehr flach aus. GPT-5-Director-Prompt + Zod-Schema + SceneRenderer
  (Full-Bleed-Branch) mitgezogen. GEPRUEFT in der Sandbox: tsc --noEmit clean,
  Director erzeugt schema-valide No-Text-Spec (0 Text-Blocks) UND Default-Spec
  (Grafik+Text gemischt), echter Headless-Render 278 Frames -> 1080x1920 h264,
  Frame-Streifen an Ismet (Orb+Ringe / Shapes+Wave / Settle). Python-Captions +
  Selftest voellig unberuehrt (627/627). EHRLICH: Optik-Feinschliff (Mesh-
  Saettigung, Farbwelten) erst auf echtem GPU-Render final beurteilbar.

- **v101q Hotfix Motion-Brief: "Render failed" behoben (Browser-Download).**
  BEFUND (aus Ismets Live-Screenshot reproduziert): das Brief-Panel erschien
  live (Docker-Build + Node + npm ci ok), aber jeder Render brach mit "Motion
  render failed" ab. URSACHE: Remotion zog sich zur RENDER-Zeit Chrome Headless
  Shell von `remotion.media` — auf einem Server mit Egress-Allowlist (prod)
  antwortet das mit 403, der Render stirbt. Auch der `remotion browser ensure`
  im Docker-Build lief ins Leere (gleicher Host geblockt). FIX: kein Runtime-
  Download mehr. (1) Dockerfile installiert System-`chromium` via apt (bringt
  seine Chrome-Libs mit), setzt `DVE_CHROMIUM=/usr/bin/chromium`, der nutzlose
  `remotion browser ensure`-Schritt ist raus. (2) render-brief.mjs findet den
  Browser automatisch (Flag > `DVE_CHROMIUM`/`REMOTION_BROWSER_EXECUTABLE` >
  `/usr/bin/chromium` etc.) und reicht ihn als `--browser-executable` an
  `remotion render`. BEWIESEN in der Sandbox: derselbe Brief aus dem Screenshot
  ("Dynamic Apple Style Intro for DouchkoVE.") rendert Ende-zu-Ende durch — 218
  Frames -> 1080x1920 h264, 1.1 MB — sowohl mit explizitem Flag als auch rein
  ueber die Env-Auto-Erkennung. Beweis-Video an Ismet geschickt.

- **v101p gpt-5 ueberall + Motion-Director LIVE ("Mach live").** ZWEI Dinge:
  (1) MODELL: alle Regie-KI-Aufrufe in render.py ziehen jetzt gpt-5 als
  Default (6 Funktions-Defaults `model='gpt-5'` + 4 `ai_model`-Fallbacks),
  config.yaml stand schon auf gpt-5, der Motion-Director ebenfalls. `_oai_json`
  laesst bei gpt-5/o-Serie automatisch `temperature` weg. (2) LIVE-WIRING:
  der separate Remotion-Stack (motion/) haengt jetzt am Web-Produkt. Neu:
  `POST /api/motion/brief` (Form `brief`) reserviert 1 Credit atomar
  (`_reserve_credits`, 402 bei zu wenig), legt einen Motion-Job an; der Worker
  ruft `_run_motion_brief()` -> spawnt `node scripts/render-brief.mjs` (Brief
  -> validierte SceneSpec -> Remotion-Render -> fertig.mp4), streamt
  `Rendered n/m` in den Fortschritt, zieht ein Poster, setzt fertig/video_url
  bzw. fehler+Gutschrift. Der fertige Clip landet automatisch in der Library
  (gleicher Zustands-Vertrag wie Template-Motion) und spielt inline (reuse
  motionPoll v101o). FEATURE-DETECTION: `MOTION_BRIEF_OK` (node + motion/
  node_modules) faellt bei fehlendem Node/Build auf `false`, /api/me meldet
  `motion_brief`, das SPA blendet das Brief-Panel dann komplett aus -> Captions
  + bestehende Motion-Templates laufen unberuehrt weiter (503 als Notnagel).
  DEPLOY: Dockerfile installiert Node 22 + `npm ci` im motion/-Layer, KOMPLETT
  best-effort (`|| echo`, kein Build-Kipp), neues .dockerignore haelt den
  Kontext schlank. render-brief.mjs jetzt nebenlaeufig-sicher (eigener temp-
  Dir je Aufruf). EHRLICH: Docker-Image hier NICHT baubar (kein Daemon in der
  Sandbox) - abgesichert durch den nicht-fatalen Motion-Layer + update.sh
  (`set -e` haelt bei Build-Fehler den alten Container am Netz) + Laufzeit-
  Feature-Detection. gpt-5-Wirkung + echte Motion-Optik erst live auf
  douchko.eu mit GPU beurteilbar. Python-Selftest 627/627 gruen, JS + server.py
  Syntax ok.

- **motion/ — Remotion-PoC (TS/Canvas, NEUER separater Stack, Ismet-Entscheidung).**
  Eigenständiger TypeScript/Remotion-Ordner NUR fuer Motion-Graphics. Die
  Caption-Engine (render.py/gfx_engine.py) + FastAPI bleiben Python,
  UNANGETASTET. Verbindung nur ueber einen flachen, deterministischen
  JSON-Vertrag (SceneSpec). Enthaelt: closed-form Damped-Spring +
  Whisper->Beat-Bindung (lib/spring.ts), Continuous-Flow Overlap-Manager
  (lib/overlap.ts: Szene A klingt aus / B fliegt ein), Safe-Zone-Lane-Solver,
  Blocks (KineticHeadline mit Variable-Font, StatCard-Count-up,
  AccentUnderline, DeviceFrame, Grain), eine data-driven Composition
  (Root/MotionVideo), Demo-Spec. GEPRUEFT: tsc --noEmit clean UND echter
  Headless-Render in der Sandbox (252 Frames -> 1080x1920 h264 MP4,
  deterministisch, Inter Variable offline gebundelt). Warum ueberhaupt:
  Live-60fps-Preview + GPU-Compositing + Variable-Weight-Kinetik, das PIL/
  numpy nicht kann. Naechste Schichten (NICHT gebaut): AI-Director
  (Brief -> validierte SceneSpec, wie ai_direct), kuratiertes
  Block-Vokabular, Einbindung in die Motion-Seite. EHRLICH: die echte
  Optik-Qualitaet ist erst auf GPU/Studio beurteilbar; der CPU-Sandbox-Render
  beweist die Pipeline, nicht den Geschmack. Setup: `cd motion && npm install
  && npm run dev|render`. Python-Selftest davon unberuehrt (627/627).

- **v101o Motion inline + Player sparsamer + Highlight-Notiz (Ismet-Wunsch).**
  (1) MOTION-VIDEO INLINE: nach dem Render erscheint der fertige Clip jetzt
  direkt in der Vorschau-Flaeche der Motion-Seite (moVid-Player), statt nur
  "saved to Library" zu verlinken - darunter Download MP4 / MOV·Alpha /
  "Adjust & re-render". moShowPreview() schaltet bei Regler-Aenderung oder neuem
  Render zurueck auf die Still-Vorschau; alle Regler bleiben, alles weiter
  einstellbar. MOV-Export spielt inline die daneben liegende fertig.mp4-
  Vorschau. (2) PLAYER GEGEN DAS RUCKELN: resultVid + moVid mit
  preload="metadata" (laedt nicht mehr die ganze Datei eifrig) + poster
  (/api/poster) - Standbild sofort, Video on demand. (3) NOTIZ im Highlight-
  Modus: erklaert, dass Captions in kurze Phrasen gruppiert sind und jede
  Phrase EIN Highlight zeigt - erzwingt man mehrere sehr dicht, koennen sie
  gekuerzt werden; Picks verteilen gibt jedem seinen vollen Moment. 3 neue
  Tests (DOM). Regression 627/627 + GUI_OK, Browser-Smoke ohne JS-Fehler.

- **v101n Fix: mehrere erzwungene Woerter pro Phrase kommen jetzt ALLE durch.**
  Ismet: "nicht alle Woerter die ich will kommen". Ursache (per echtem Render
  reproduziert, KEIN Bug): Woerter werden zu Phrasen-Gruppen gebuendelt, eine
  Phrase = EIN Highlight. Zwei Marken in derselben Gruppe ("neues Level" in
  Gruppe [9,10,11]) -> nur eine wurde ein Moment, "Level" fiel weg. Fix:
  split_forced_groups() trennt eine Phrase an den erzwungenen Woertern auf,
  sobald >=2 Marken drin liegen - jedes markierte Wort beginnt eine eigene
  Untergruppe und wird ein eigenes Highlight. Betrifft NUR Gruppen mit >=2
  user_pick-Marken; alle anderen Phrasen bleiben exakt wie sie waren. BEWEIS:
  6 erzwungene Woerter (inkl. Nachbarpaar) -> vorher FEHLEN [Level], jetzt
  FEHLEN []. 3 neue Tests (Split-Logik, Nachbar-Paar wird zu 2 Highlights,
  Gegenprobe unveraendert). Regression 624/624 + render1 7/7 + GUI_OK.

- **v101m Keyword-Markierung im Text-Schritt (Nutzer uebersteuert die KI).**
  Im Text-Schritt gibt es jetzt einen zweiten Modus "Pick highlights":
  Wort antippen zyklisch neutral -> ERZWINGEN (lila + ✨) -> BLOCKIEREN
  (durchgestrichen) -> neutral. QUALITAETS-ENTSCHEIDUNG (Ismet wollte es im
  Text-Editor, NICHT den empfohlenen Vorschau-Schritt): die Markierungen
  ERSETZEN die KI-Regie nicht, sie UEBERSTEUERN sie danach. render.py:
  apply_keyword_marks() laeuft NACH KI-Regie + Heuristik + Kapiteln (letzte
  Instanz), liest ein Sidecar <input>_kwmarks.json ({index: 1|-1}); erzwungene
  Momente tragen user_pick=True und ueberleben - wie intent, aber OHNE dessen
  semantische Platzierung - das Dichte-Gate UND das B-Roll-Gate (Gegenprobe im
  Test: 2 dichte erzwungene Woerter -> beide bleiben; ohne Schutz nur 1).
  Vorhandene KI-Momente werden nur erzwungen, nicht ueberschrieben (Effekt/
  Wucht bleiben). Server schreibt das Sidecar ueber den bestehenden
  Transkript-Save (neues Feld kwmarks, gedeckelt/validiert). Der Render zieht
  es automatisch. 6 neue Tests. Regression 622/622 + 7/1/5/2 Renders + GUI_OK.
  Browser-Smoke ohne JS-Fehler (Screenshot an Ismet). HINWEIS/EHRLICH: das ist
  bewusst "blind" (vor der KI-Analyse, ohne Vorschaubild) - die reichere
  Auswahl mit KI-Vorschlag + Frames bleibt der Momente-Editor nach dem Render.

- **v101l Transkript-Schritt im Wizard (Text vor Render).** Der Transkript-
  Editor war bisher NUR im Momente-Editor versteckt (Button "Fix transcript"
  ganz unten) - auf dem Hauptweg Upload->Look->Fine-tune->Render kam man gar
  nicht dran. Neu: eigener Wizard-Schritt **4 "Text"** zwischen Fine-tune und
  Render (Render ist jetzt 5). Nutzt den Pre-Upload-Job (State.preJid) - die
  Transkription laeuft seit der Datei-Auswahl, ist beim Ankommen meist fertig;
  sonst dynamischer "am Transkribieren"-Loader mit Poll. Wort-Chips zum
  Antippen+Tippen (Enter bestaetigt), geaenderte Woerter markiert, Live-Zaehler,
  **Suchen & Ersetzen** fuer wiederkehrende Namen/Marken (mit Flash-Animation
  auf den Treffern). Speichern ohne Analyse-Umweg: POST /api/transcript mit
  neuem `reanalyze=0` (nur Text sichern + Regie/Momente-Cache invalidieren,
  KEIN Re-Queue) - der folgende Voll-Render zieht den korrigierten Text aus
  dem Cache. Doppelt gesichert: auch startUpload('full') speichert offene
  Korrekturen vor dem Render (falls der Nutzer den Schritt ueberspringt).
  Der alte Momente-Editor-Button bleibt heil (reanalyze default 1). Browser-
  Smoke: SPA laedt ohne JS-Fehler, Schritt rendert im App-Design (Screenshot
  an Ismet). 4 neue Tests (5 Schritte im DOM, Chip/Suchen-UI, reanalyze=0
  Frontend+Backend). Regression 616/616 + Renders + GUI_OK.

- **v101k Depth-Bullet-Time (Innovations-Batch 11 - BATCH KOMPLETT).** Die
  laengste Sprech-Pause >= 0.8s DIREKT vor einem power-3-Moment wird zum
  Bullet-Time-Moment: das Bild friert ein und eine virtuelle Kamera faehrt
  per 2.5D-Tiefen-Reprojektion (depth.onnx) seitlich hinein und wieder
  zurueck. s(u)=sin(pi*u): Start UND Ende exakt auf 0 - der Schnitt zurueck
  ins Live-Bild ist nahtlos, die DAUER bleibt unveraendert (die Pause war eh
  still, Audio unangetastet). Parallaxe um die Median-Tiefenebene (nah/fern
  gegenlaeufig, Beweis: Punkt nah +4.9px / fern -4.4px bei u=0.5), dazu
  leichter Push-in. Genau 1x pro Video (bullet_window waehlt die laengste
  Pause), Quality-Gate depth_quality_ok (flache Tiefenkarte -> kein Effekt,
  "lieber kein Effekt als ein billiger"), laedt das Tiefen-Modell notfalls
  selbst, im Alpha-Export aus (Hintergrund-Effekt). Abschaltbar:
  effects.bullet_time. Matting/Faces laufen auf dem Dolly-Frame weiter -
  behind-Occlusion bleibt konsistent. 5 neue Tests (Kandidaten-Wahl,
  Ausschluesse, Gate, Parallaxe+Nahtlosigkeit, Verdrahtung). Regression
  612/612 + 7/1/5/2 Renders + GUI_OK. EHRLICH: der Test-Clip hat keine
  0.8s-Pause vor power-3 - der Effekt selbst laeuft hier nur ueber die
  synthetischen Helper-Tests; echte Wirkung erst live.

- **v101j Hand-Kontakt (Innovations-Batch 10).** Beruehrt der Sprecher eine
  Caption mit der Hand, reagiert sie PHYSISCH: MediaPipe-HandLandmarker
  (models/hand.task, neu in MODEL_URLS) sucht in Moment-Fenstern (need_hands,
  jedes 2. Frame, gated) die 10 Fingerspitzen; hand_contacts() gibt einem
  beruehrten Moment EINEN Impuls in Fingerrichtung (Mindest-Tempo W*0.10/s
  gegen ruhende Finger, 0.35s-Cooldown, Impuls gedeckelt); hand_spring()
  federt ihn unterdaempft aus (K=120/C=9: schneller Wisch ~30px Auslenkung,
  -6px Overshoot, klingt aus - kein linearer Rutsch). Offsets fliessen
  zentral ueber track_offset (Billboard) + scene_shift (behind/ground).
  Dazu HAND-OCCLUSION: bei frischem Kontakt (<0.5s) wird die Person-Matte
  lokal um die Fingerspitzen (r=8.5%H, weich) wieder UEBER den Text gelegt -
  die Hand liegt sichtbar vor dem Wort. Alpha-Export-kompatibel ('_'-Keys im
  Snapshot; Occlusion malt frame-Pixel -> im Doppelpass korrekt ein Loch).
  Ohne Modell/mediapipe: still aus, klar geloggt, kein Fake. Abschaltbar:
  effects.hand_contact. 5 neue Tests (Kontakt-Gate/Cooldown, Feder-
  Physik, Tracker-Load, Verdrahtung). Regression 607/607 + 7/1/5/2 Renders
  + GUI_OK. EHRLICH: echte Beruehrungs-Wirkung (Erkennungsquote, Timing)
  ist nur mit echtem Material auf douchko.eu/Windows beurteilbar - hier
  Physik + Gating + Modell-Load verifiziert, synthetische Bilder enthalten
  keine erkennbaren Haende.

- **v101i World-Lock Wand (Innovations-Batch 9).** Wand-Texte ("an der
  Wand", szene 'wand', stehend) hingen bisher am BODEN-Track
  (update_homography maskiert unteres Bilddrittel aufwaerts) - Boden und
  Wand haben bei Kamerabewegung verschiedene Parallaxe, der Wand-Text
  rutschte. Neu: (1) update_homography(region='wand') trackt die OBERE
  Bildhaelfte (die Wand-Ebene); (2) exclude=Personen-Maske haelt bewegte
  Personen-Pixel aus den Features (sonst zieht die Schulter den
  "Welt-Anker" mit); (3) der Loop fuehrt einen ZWEITEN Akkumulator
  H_cum_wall (+wall_gen) nur in Wand-Fenstern (need_track_wall), Schnitt
  resettet beide; composite_frame waehlt pro Plan die richtige Ebene
  (_is_wall -> H_cum_wall). (4) Stehender Wand-Text bekommt einen dezenten,
  licht-wahren Kontakt-Schatten auf der Wand (strength 0.30, nutzt v101f
  light_dir) - vorher schwebte er schattenlos. Synthetischer Beweis:
  Wand zieht -6px/Boden -2px -> Wand-Track -6.9, Boden-Track -3.7
  (Mischung, wie designt); bewegte "Person" verfaelscht den Wand-Track
  ohne exclude, mit exclude wieder -7.3~-6. 4 neue Tests. Regression
  602/602 + 7/1/5/2 Renders + GUI_OK. EHRLICH: echte Wand-Szenen mit
  Kamerabewegung gibt es nur live - hier synthetisch bewiesen.

- **v101h Caption-Alpha-Export (Innovations-Batch 8).** Transparente
  Caption-Ebene (ProRes 4444, yuva444) fuer Premiere/Resolve - passt exakt
  zur Finishing-Tool-Positionierung. TECHNIK: Difference-Matting-Doppelpass -
  jedes Frame wird zweimal komponiert (ueber Schwarz + ueber Weiss), daraus
  loest alpha_from_pair() das Alpha EXAKT (alpha = 1 - (weiss-schwarz)/255):
  Person-Occlusion (behind) wird automatisch zum LOCH im Alpha, dim_behind zu
  korrektem Halbtransparenz-Schwarz. Voraussetzung bitidentische Paesse:
  _alpha_state_snapshot/_restore setzt Anim-Federn, RNG-States (inkl.
  numpy-Generator-BitState) und Kamera zwischen den Paessen zurueck; das
  Szenen-Grain ist jetzt pro Frame seedbar (grain_seed aus t). BEWUSST AUS im
  Alpha-Modus (auf einer Overlay-Ebene physisch nicht transportierbar, klar
  geloggt): Kamera-Moves, Freeze, Split-Screen, BG-Blur. SFX kommen als
  eigene PCM-Tonspur mit (Kunde hat sein Original-Audio selbst). BEWEIS:
  Ebene ueber Original vs. Normal-Render (ohne Kamera) -> mean-diff 1.0-2.3
  (Codec-Rauschen), Bild an Ismet geschickt. WEB: POST /api/alpha/{jid}
  (Kaeufer-Gate 402, kostet wie ein weiterer Render, atomare Buchung
  'Alpha {jid}', Refund bei Fehlschlag), Worker-Modus 'alpha' (nutzt
  Transkript-/Regie-Caches, kein Whisper doppelt), GET /api/alpha_file/{jid},
  Library-Buttons 'Editor layer' -> 'Layer (MOV)'. CLI: --alpha-export.
  13 neue Tests (Alpha-Mathe, Dim, State-Restore inkl. RNG, Verdrahtung,
  Server-Gates/Buchung, echter 4444-Render + Sync + Alpha-Inhalt in
  render2b). Regression 598/598 + 7/1/5/2 Renders + GUI_OK.

- **v101g Regie-Kontaktbogen (Innovations-Batch 7).** Beim Voll-Render wird
  pro Keyword-Moment der Frame auf dem Hoehepunkt (Start + 40% der Dauer)
  eingesammelt und als EIN Grid-JPG neben das Video gelegt
  (fertig_kontakt.jpg, contact_sheet(): 3 Spalten, Label 'WORT @ 12.3s' pro
  Tile). Echtes Compositing - exakt die Pixel, die auch im Video stehen
  (inkl. Wasserzeichen im Free-Tier, kein Leak sauberer Frames).
  BEWUSSTE ABWEICHUNG vom urspruenglichen "vor dem Credit-Render"-Plan:
  eine Pre-Render-Vorschau waere nur ein Fake-Composite (Editor zeigt
  Thumbs+Cutouts bereits) - der Bogen ist stattdessen der BEWEIS aus dem
  echten Render. Web: GET /api/contact/{jid} (Owner-Check), Job-Flag
  kontakt=True, 'Moment sheet'-Button im Success-Screen + 'Moments' in der
  Library. Abschaltbar: effects.contact_sheet. 6 neue Tests (Grid-Geometrie,
  Leer/Einzel-Fall, Render-/Server-/UI-Verdrahtung, echter Bogen im
  render1-Voll-Render). Regression 589/589 + 7/1/1/2 Renders + GUI_OK.

- **v101f Licht-Wahrheit Stufe 1 (Innovations-Batch 6).** Der Kontakt-Schatten
  unter dem stehenden Text war bisher ein symmetrischer Blob direkt darunter.
  Neu: estimate_light_dir() schaetzt die dominante Lichtrichtung aus einem
  Mittel-Frame (Luminanz links vs rechts + Haerte aus dem Gefaelle), und
  make_contact_shadow(light=(lx,hard)) laesst den Schatten LICHT-WAHR zur Seite
  fallen - weg vom Licht (Licht rechts -> Schatten nach links versetzt und in
  diese Richtung gestreckt), hartes Licht macht ihn kraeftiger, flaches Licht
  bleibt weich/rund. Ein Schaetzung pro Clip (Licht ist meist konstant),
  abschaltbar via effects.light_shadow. Ohne light-Argument bleibt exakt der
  alte symmetrische Schatten (Rueckwaerts-Kompatibilitaet, alle Alt-Tests
  gruen). BEWUSSTE GRENZE: gilt nur fuer den stehenden Billboard-Text - flach
  auf die Flaeche gemalter (liegender) Text bekommt weiterhin KEINEN Schatten
  ("Farbe hat keine Hoehe", bestehende Design-Entscheidung nicht ueberfahren).
  6 neue Tests. Regression 584/584 + Renders + GUI_OK. EHRLICH: die
  Schatzung/Wirkung ist nur auf ECHTEM Material sichtbar - hier mit
  synthetischen Helligkeits-Frames getestet (Richtung + Versatz stimmen).

- **v101e Korrektur-Gedaechtnis (Innovations-Batch 5).** Bisher zog nur
  _apply_corrections EXAKT dieselbe Phrase nach (deterministisch, kein
  Transfer auf neue Stellen). Neu: correction_profile() verdichtet alle
  frueheren Editor-Korrekturen des Kontos zu einem kurzen Vorlieben-Profil
  (welcher Effekt wird bevorzugt getauscht: 'behind'->'ground', wird Anim
  entfernt, Wucht gesenkt, Momente deaktiviert) und speist es als KONTEXT in
  den KI-Regie-Prompt (prof_block vor ref_block) - so generalisiert die KI
  aus alten Korrekturen auf NEUE, aehnliche Phrasen. Nur Muster ab 2
  Vorkommen (Einzelfaelle = Rauschen, kein Stil). Capture-Seite (Server)
  erweitert: speichert jetzt orig_fx (From->To) und Wucht-Delta
  (orig_power/user_power), damit das Profil Richtung und Dosis kennt; alte
  Records ohne diese Felder bleiben kompatibel. Der deterministische
  Per-Phrase-Pfad bleibt als letzte Instanz (Nutzer gewinnt exakt). 5 neue
  Tests. Regression 579/579 + Renders + GUI_OK. EHRLICH: ohne OPENAI_API_KEY
  laeuft nur der Heuristik-Pfad; die Prompt-Injektion wirkt erst live mit
  Key auf douchko.eu (hier nur Profil-Logik + Verdrahtung getestet).

- **v101d Safe-Zone-Regie (Innovations-Batch 4).** Statt eines pauschalen
  "Safe-Zone an/aus" kennt die Pipeline jetzt die echten UI-Rechtecke der
  drei grossen Feeds (Stand 2026): PLATFORM_UI + platform_safe_zones()
  liefern pro Plattform (tiktok/reels/shorts/generic) das nutzbare Text-
  Rechteck (Button-Spalte rechts, Caption-Zeile unten, Reiter oben bleiben
  frei). Diese Zonen speisen als ECHTE Constraints die Platzierung:
  v_zone() zieht floor_top/cap_bot aus der Maske (Reels sitzt hoeher als
  TikTok, weil unten mehr Chrome liegt), clamp_cx() endet am rechten Rand
  an der Button-Spalte statt am Bildrand. Zusaetzlich safe_zone_report():
  meldet Momente, deren Sprite trotz Constraint ins UI ragt (zu breit/tief)
  - beratend, aendert nichts. Plattform aus output.platform (config-Default
  generic = Schnittmenge, nirgends verdeckt); TikTok-Preset opted in; Client-
  Override auf {generic,tiktok,reels,shorts} whitelisted (kein Pfad-Risiko).
  9 neue Tests (Zonen-Geometrie, Reels<TikTok, generic-Fallback, Report-
  Treffsicherheit, clamp-Constraint im Voll-build_plans, Main+Config-
  Verdrahtung, Sanitizer-Whitelist). Regression 574/574 + 6/1/1/2 Renders +
  GUI_OK. EHRLICH: die UI-Rechteck-Werte sind aus den 2026er-Layouts
  abgeleitet, hier synthetisch getestet - final prueft Ismet an echten
  Screenshots der drei Apps.
  BETRIEB: Sandbox-Session erneut auf v100 zurueckgesetzt (v101a-c lokal
  weg, Remote hatte alles) - Recovery per git reset --hard auf
  origin/branch, Safe-Zone-Arbeit war noch uncommitted und wurde neu
  aufgetragen. Bestaetigt die Lehre: nach jeder gruenen Einheit sofort
  pushen (jetzt geschehen).

- **v101c Beat-Grid (Innovations-Batch 3).** Liegt Musik mit klarem Takt
  unter dem Clip, rasten Keyword-Momente auf den naechsten Beat ein
  ("cut on the beat", Editor-Handwerk). beat_grid_times() zieht die
  Beat-Zeitpunkte aus der music_beats()-Envelope (lokale Maxima > 0.55;
  Selbstschutz: conf < 0.30 oder < 4 Beats -> kein Grid, reine
  Talking-Heads bleiben unberuehrt). build_plans verschiebt NUR den
  Einstieg, max. 0.12s (unter der Wort-Sync-Wahrnehmungsschwelle) und nie
  unter 0.6s Reststandzeit; laeuft NACH Schnitt-Disziplin, vor dem Sort.
  SFX bleiben bewusst auf den Sprech-Onsets (Ton gehoert zum Wort, Bild
  darf zum Takt atmen). Abschaltbar: effects.beat_grid=false. 8 neue
  Tests (Beat-Extraktion, Confidence-/Mindest-Beats-Schutz, Snap <=0.12s,
  kein Snap >0.12s, Config-Gate, Main-Verdrahtung).
  Regression 566/566 + 6/1/1/2 Renders + GUI_OK. EHRLICH: hier nur mit
  synthetischer Envelope getestet - Wirkung auf echtem Musik-Material
  sieht Ismet erst live.

- **v101b Watermark-Unlock (Innovations-Batch 2/4).** Free-Tier-Renders
  laufen jetzt als SPLIT: sauber rendern, Master als master_clean.mp4 im
  Job-Ordner cachen, Auslieferung per ffmpeg-Overlay mit EXAKT demselben
  Sprite wassermarkieren (build_watermark() ausgelagert - eingebrannter
  Pfad und Overlay nutzen dasselbe Bild; Pixel-Beweis: Diff nur unten
  rechts, Rest mean 0.31). Der erste Kauf schaltet frei: _credit_purchase
  ruft _unlock_all_jobs (alle gecachten Videos des Kunden, atomarer
  os.replace), zusaetzlich POST /api/unlock/{jid} + "Unlock HD"-Button in
  der Library (402 -> Pricing). Kein Neu-Render, kein Ergebnis-Risiko -
  Kauf im Moment der hoechsten Zahlungsbereitschaft. Demo bleibt beim
  eingebrannten Wasserzeichen (kein Master noetig). Cleanup raeumt den
  Master mit dem Job-Ordner ab (7 Tage). 5 neue Tests (Sprite, Split-
  Verdrahtung, Swap+Idempotenz, Auto-Unlock beim Kauf, UI-Flag).
  Regression 558/558 + Renders + GUI_OK.
  HINWEIS Betrieb: Die Sandbox-Session wurde zwischendurch auf einen
  aelteren Stand zurueckgesetzt (v101a-Commit war lokal weg, Remote hatte
  ihn) - Arbeit war dank Push gesichert; Lehre: nach jeder gruenen Einheit
  sofort pushen.

- **v101a Innovations-Batch Teil 1/4 (Ismet: "Mach alles" aus der
  Innovations-Liste).** Drei von 13 Features:
  (1) BETONUNGS-TYPOGRAFIE: _word_loudness() (Sprech-Pegel pro Wort, 50ms-
  RMS) speist jetzt auch die Typografie - compose_phrase baut den Kern bei
  Pegel-Marken pro Wort mit echter Variable-Font-Gewichtsachse (laut '!' =
  wght 900 + 6% groesser, leise '~' = wght 500 + 6% kleiner, normal 760 =
  optisch identisch zum statischen Schnitt), Grundlinie unten (CAPS), Zeile
  passt sich in max_w ein; compose_flow skaliert/gewichtet norm-Woerter.
  Main misst einmal (loud_map) und reicht durch build_plans. Kein API-Call.
  Beweis: Sprite-Vergleich (ZAHL schwer neben DIESE normal), Flow-Wort
  282->311px bei '!'.
  (8) CHOREOGRAPHIE-REGIE: REGIE_PROMPT Punkt 4 - Buendeln statt
  Wort-Geballer, Pausen nach power-3 halten, Pops nur auf Schluesselwoerter,
  EIN Stil-Wechsel auf dem Wendepunkt.
  (9) SILENT-SCORE: silent_score() bewertet das FERTIGE Video stumm (74%
  der Views laufen ohne Ton) - 1 Vision-Call, max 6 Moment-Frames detail
  low, JSON {score 0-100, max 3 Hinweise}; render.py schreibt
  <input>_silent.json + Log-Zeile, server uebernimmt in den Job-State,
  UI zeigt "Silent view"-Kachel + Muted-view-Tipps im Director's Report.
  Ohne Key: still None, nichts passiert. Config: keywords.silent_score.
  Tests: 7 neue (Kern reagiert auf Pegel im Rahmen, Flow-Wort waechst,
  Verdrahtung Main/Server/UI, Prompt-Garantien, ohne Key kein Crash).
  Regression 563/563 + GUI_OK. Ehrlich: Silent-Score-Qualitaet und
  Betonungs-Optik auf echtem Material prueft Ismet.

- **v100 Animations-Pass (Ismet: "Fixe alle Animationen. Dynamisch, high
  end, Stand 2026, wie von einem Senior-VFX-Spezialisten").** Methodik:
  alle 26 Animationen als Filmstreifen-Proben gerendert (animprobe-Harness,
  10 Frames ueber 1.3s, stateful mit Audio) und wie ein Motion-Designer
  beurteilt. 13 waren unter Standard und wurden neu gebaut - Prinzipien:
  Envelope-Follower statt Roh-Audio, Federn mit Overshoot statt ease_out,
  Anticipation/Impact/Settle statt Endlos-Drift, deterministisch
  verwuerfelte Staffelung statt linearer Muster, Tremor statt Weissrauschen:
  * sturz: 3 Akte (Luft holen -> Gravitations-Fall mit Rotation ->
    AUFPRALL mit Squash + Nachfedern, steht voll sichtbar). Vorher fiel es
    ins Nichts und hing 70% transparent in der Luft.
  * anstieg: Feder mit Overshoot + vertikalem Stretch waehrend der
    Bewegung (Squash & Stretch), steht exakt.
  * wende: asymmetrisch - quint-schnell raus, federt mit ~8 Grad
    Overshoot zurueck, dimmt am Steilpunkt (Tiefe). Vorher symmetrischer
    Sinus = Fahne im Wind.
  * druck: Last KOMMT AN (ease-in), staucht ueber das Ziel, federt
    gedaempft. Vorher linearer Dauer-Squash.
  * explosion: Streu-Richtung deterministisch verwuerfelt - das
    Parity-Zickzack (Spalte auf/ab im Takt) war als Muster lesbar.
  * regen: Gravitation (x^2) + Bounce beim Aufschlag + verwuerfelte
    Staffelung. Vorher weiche ease_out-Landung im Gleichschritt.
  * rutsche: Feder-Overshoot pro Streifen + verwuerfelte Staffelung.
  * zittern: Tremor aus zwei ueberlagerten Frequenzen mit Wort-Phase +
    abklingendem Onset-Kick + 0.8 Grad Mikro-Rotation. Vorher
    Weissrauschen (jeder Frame neuer Zufall = Renderfehler-Optik).
  * glitch: klingt ueber 2-4 Frames ab + RGB-Split (Chromatic).
    Vorher 1-Frame-Zufallsversatz.
  * neon: ZUENDET (3 deterministische Stotter, dann an), flackert danach
    selten und nur auf 0.78; Glow atmet mit Stimme und Zuendzustand.
    Vorher 5%-Zufalls-Vollbild-Strobo.
  * puls/schub: Envelope-Follower (schneller Attack, traeger Release)
    statt rohem Bass-Wert bzw. festem 0.66s-Metronom.
  * welle: Energie klingt ab (voll -> 36% Restschwingen) + Oberwelle
    gegen die Sinus-Signatur.
  Die 13 bereits guten (knall, stempel, fokus, gewicht, schweben, kippen,
  spur, enthuellen, bruch, magnet, zoom_punch, schwund, cascade-Path)
  blieben unangetastet. API/Namen/Dauern unveraendert, SFX-Timing
  kompatibel (Sounds sitzen auf Wort-Onsets, nicht auf Anim-Phasen).
  Beweis: Vorher/Nachher-Filmstreifen + Showcase-MP4 (13 Anims a 1.5s),
  Verhaltens-Invarianten im Selftest (sturz landet bei dy~0.30h voll
  sichtbar, wende endet lesbar, neon 0.27->0.96, alle 26 crashfrei ueber
  40 Frames mit Zustand). Regression 556/556 + GUI_OK. Ehrlich: Wirkung
  im echten Video (mit Motion-Blur + Beat-Sync obendrauf) prueft Ismet
  auf douchko.eu/Windows.

- **v99a Ansage ist Gesetz (Ismet testete mit ECHTEM Selfie-Video auf
  douchko.eu: "der macht nicht das, was er sagt").** Diagnose am
  hochgeladenen Video (15s Selfie, Strasse): die v99-Momente ENTSTANDEN
  korrekt, wurden aber von VIER nachgelagerten Systemen wieder degradiert
  oder verfaelscht - jedes fuer sich sinnvoll, aber keines wusste, dass der
  Sprecher die Platzierung WOERTLICH bestellt hat:
  (1) Nahaufnahme-Backstop (_behind_cover_backstop): Gesicht >=52%
  Bildbreite schaltete angesagtes 'behind' auf outline. Jetzt: intent-
  Momente bleiben behind und bekommen szene 'himmel' - das Wort steigt
  HINTER dem Kopf hervor und endet lesbar UEBER ihm ('hinter mir' UND
  sichtbar). Vision-fx-Override respektiert intent ebenfalls.
  (2) Dichte-Limit in build_plans degradierte den Moment zum normalen
  Caption-Text, wenn er <min_gap nach dem vorigen kam. Jetzt: intent
  erzwingt is_kw_group und gewinnt die Wort-Wahl der Gruppe.
  (3) Mehrwort-Regel: Phrasen >=2 Woerter wurden IMMER zur Editorial-
  Komposition (tpl 'behind') - 'ON THE GROUND' lag nie auf dem Boden.
  Jetzt: Platzierungs-Ansagen (ground, behind+himmel) rendern als
  Szenen-Sprite. Dazu B-Roll-Gate: Kamera schwenkt auf den Boden ->
  kein Gesicht -> Gruppe wurde uebersprungen; intent-Momente ueberleben.
  (4) Momente-Editor-Roundtrip verlor das intent-Flag (Export/Merge-
  Whitelist) -> direkt nach dem Export griff Regel 2 wieder. Jetzt wird
  intent exportiert-unabhaengig im Merge erhalten; aendert der Nutzer den
  Effekt im Editor bewusst, erlischt die Ansage (User gewinnt zuletzt).
  DAZU: Auto-Anim-Kontext endete nicht an Satzgrenzen - 'explode' aus dem
  FOLGESATZ faerbte 'ON THE GROUND' mit einer Explosions-Anim (anim_ctx()
  kappt jetzt beide anim_for-Aufrufe am Satzende). intent ueberlebt
  zusaetzlich den Regie-Cache (parse_regie-Passthrough); Cache wird nur
  noch bei echter KI-Wahl geschrieben (_regie_wahl), sonst bliebe die
  Auto-Heuristik nach einem Selbstbezug-only-Lauf faelschlich aus.
  BEWEIS auf Ismets echtem Video (nachgestelltes Transkript, ohne Key):
  vorher 2 von 3 angesagten Momenten im Plan, nachher 3 von 3 - Frames:
  'BEHIND' steigt golden hinter dem Kopf hervor, 'ON THE GROUND' liegt
  perspektivisch auf dem Gehweg (vom Koerper korrekt verdeckt), 'EXPLODE'
  vorn mit Explosion, keine Fehl-Anim mehr. 10 neue Tests (Backstop/
  Vision/Dichte/B-Roll/Komposition/anim_ctx/Cache/Editor-Quelltext).
  Ehrlich: Ismets Original-Test lief evtl. auch vor dem v99-Deploy -
  auf douchko.eu nach dem naechsten Deploy neu testen.

- **v99 Selbstbezug-Regie (Ismet: "Wenn jemand sagt 'The captions are
  behind me', soll der Satz sich hinter der Person bilden. 'The captions
  explode' -> explodieren.").** Kern-Erkenntnis: Das Verstaendnis existierte
  in der KI-Regie schon teilweise (SELBSTBEZUG-/AKTION-WORT-Regeln,
  _speech_intent, ORT-Tabelle, echte RVM-Occlusion bei fx 'behind') - aber
  genau die Beispiel-Saetze SCHEITERTEN: "The captions are behind me"
  besteht komplett aus Sperrlisten-Woertern (the/captions/are/behind/me),
  die KI durfte dort kein Keyword waehlen, und _speech_intent kann nur
  EXISTIERENDE Momente umlenken. Drei Bausteine:
  (1) _self_ref_intent(): deterministischer Backstop, der Selbstbezug
  erkennt (caption/captions/untertitel/subtitle immer; wort/text nur mit
  Artikel - "ich gebe dir mein Wort" bleibt ein Versprechen) und den Moment
  notfalls ERZEUGT: Orts-Ansage -> gleiche Tabelle wie _speech_intent
  ("behind me" -> fx behind, Phrase "BEHIND ME" hinter der Person; "auf dem
  Boden" -> ground/boden/liegend), Handlung -> gleiche Vokabeln wie anim_for
  ("explode" -> anim explosion, sichtbar vorn als outline, NIE behind).
  Existiert im Satz schon ein Moment, wird nur die Handlung ergaenzt
  (behind wird dabei sichtbar). Laeuft in ALLEN Pfaden (KI, Regie-Cache,
  Heuristik ohne Key) im Main; Heuristik-Keywords bleiben dabei erhalten
  (_had_regie-Weiche).
  (2) REGIE_PROMPT verschaerft: In Selbstbezug-Saetzen ist die Sperrliste
  AUSGESETZT - die KI darf/soll die angesagte Handlung oder den Ort selbst
  als Keyword waehlen ("Ein Selbstbezug-Satz darf NIE ohne Moment bleiben").
  (3) ANIM_HINTS um englische Aktions-Vokabeln erweitert (explod/burst,
  fall/drop/crash, rise/grow/soar, disappear/vanish/gone, fly/shoot/race,
  rain/pour, shake/tremble, flip/tilt/fold) - staerkt auch anim_for und
  _regie_sanity fuer englische Videos.
  BEWEIS: E2E-Render ohne API-Key mit "The captions are behind me. And my
  captions explode right now." -> Log "Selbstbezug: 2 Caption(s) tun, was
  der Sprecher ansagt", Frame bei 2.4s zeigt "BEHIND ME" von der Person
  verdeckt (echte Matting-Occlusion), Frame bei 5.0s zeigt "EXPLODE" vorn
  mit Explosions-Anim. 10 neue Tests (Ort EN, Tat EN, DE Boden, 2x Negativ,
  Ergaenzen-statt-Doppeln, build_plans-Durchstich "BEHIND ME" als
  behind-Plan, Prompt-Garantie, Main-Verdrahtung, EN-Vokabeln).
  Regression 541/541 + GUI_OK. Ehrlich: Optik der Occlusion auf echtem
  Material (echte RVM-Matte statt Synthetik-Kreis) prueft Ismet auf Windows.

- **v98 Audit-Batch (Ismet: "Mach alles, was Sinn macht" - nach der
  Konkurrenz-/Produkt-Analyse mit 9 Agenten).** 20 Punkte:
  QUICK-WINS/BUGS: (1) "Fix transcript"-Crash: JS schrieb auf #analyzeStatus/
  #btnAnalyze, die es im DOM nicht gab -> TypeError, Momente-Editor oeffnete
  nach "Save & re-analyze" nie wieder. Jetzt aStat()/aBtn()-Helfer +
  echtes Status-Element in der doneCard, gesperrt wird der echte
  "Edit moments"-Button. (2) "Priority queue" stand in den Paketen, war aber
  FIFO -> jetzt ECHT: PriorityQueue, Kaeufer-Jobs (Kauf im Ledger) vor
  Free-Tier, innerhalb der Stufe FIFO (q_put()). (3) SQLite WAL +
  busy_timeout=10s + synchronous=NORMAL - keine 'database is locked'-500er
  auf Geld-Endpunkten. (4) uvicorn --proxy-headers + forwarded-allow-ips
  (Dockerfile): vorher sah der Server fuer JEDEN Request die Caddy-IP,
  alle IP-Rate-Limits waren faktisch global. Dazu HEALTHCHECK im Container
  + Log-Rotation (compose, 10m/3). (5) Willkommens-Guthaben (120s) erst
  NACH E-Mail-Bestaetigung (_grant_welcome, idempotent) - vorher war
  Ismets OpenAI-Key per Massen-Registrierung farmbar. (6) 4K-Kachel raus
  (Server cappt eh auf 1080p - stumme Luege). (7) Billing-Transaktionsliste
  repariert (doppelter Funktionsname renderTransactions - die zweite
  Definition ueberschrieb die erste, #historyBody blieb leer). (8) Kosten
  am Render-Button ("Build video now · N credits") sobald die Dauer bekannt
  ist. (9) Polling gibt nach ~30s ohne Server ehrlich auf (Render/Motion/
  Analyze) statt endlos einzufrieren.
  WACHSTUM: (10) LANDING KOMPLETT DEUTSCH (lang=de, du-Form, SEO-Titel) mit
  Fakten-Fixes (3 Min statt "5 minutes", 8 Looks statt "four presets",
  falsches "100% EU-hosted" entfernt). (11) Pricing-Sektion auf der Landing:
  9/19/39 EUR, Preis pro Credit, "6 Monate gueltig" als Badge in jeder
  Karte, Einmalkauf-Banner mit Submagic-Vergleich, ehrlicher
  Datenschutz-Block (OpenAI benannt). (12) SRT/VTT-Export
  (/api/subtitles/{jid}, _srt_cues: 42 Zeichen/Satzende/0.8s-Pause/5s) +
  Buttons in doneCard und Library - Standard bei jeder Konkurrenz, war
  unsere groesste Feature-Luecke. (13) Wasserzeichen-Upsell in der doneCard
  (nur Nicht-Kaeufer, /api/me.purchased). (14) Demo-CTA: nach der
  10s-Demo jetzt ein klickbarer "Create free account"-Button (springt zum
  Register-Formular). (15) "Dein Video ist fertig"-Mail (mode full/motion,
  verifizierte Accounts, 1x pro Job, mit 7-Tage-Loeschhinweis).
  TECHNIK: (16) Watchdog KILLT haengende Renders nach 45 Min (PID-Tracking
  in _run_render/_run_motion, SIGKILL, normaler Fehlerpfad erstattet) -
  vorher nur Mail, bei 1 Worker stand sonst alles. (17) state.json atomar
  (tmp + os.replace). (18) Upload: ffprobe + Video-Hash via
  asyncio.to_thread (blockierte den Event-Loop inkl. /api/health).
  (19) Offsite-Backup: taegliche users.db als gzip-Mail an ADMIN_MAIL
  (Postfach = Offsite; Snapshot lag bisher auf derselben Platte).
  RECHT: (20) Konto-Loeschung archiviert Kaufbuchungen in ledger_archive
  (GoBD/§147 AO 10 Jahre; DSGVO Art. 17(3)(b) erlaubt das) statt sie zu
  loeschen - Rest (Renders/Refunds/Gutschriften) wird weiter echt geloescht
  (_purge_user_db).
  BEWUSST NICHT gemacht (Fokus, aus der Analyse): kein Abo, kein AI-B-Roll,
  kein Clipping/Avatare, kein Sprachen-Wettlauf, kein Feature-Stacking.
  VERSCHOBEN (brauchen eigenes Go + echtes Material): Mehrsprachen-Render
  (Wort-Timings brechen bei Uebersetzung - Timing-Redistribution noetig),
  Brand-Kit, Stil-Referenz als Kundenfeature, Beispielvideo im Hero.
  OFFEN FUER ISMET: UptimeRobot auf /api/health zeigen lassen; Kontakt-
  Adresse vereinheitlichen (mailto auf der Landing zeigt Ismet@douchkove.com,
  Impressum/Privacy pruefen). Tests: neue Szene 'v98 Audit-Batch'
  (WAL, Welcome-nach-Verify, Prio-Queue-Reihenfolge, SRT-Cues/Timestamps,
  Ledger-Archiv, Fertig-Mail, Quelltext-Garantien, Frontend-DOM).
  Browser-Smoke: Landing deutsch + Pricing rendert, App-DOM ok, 0 JS-Fehler.

- **Warm-Preview + Monitoring (Ismet: "Mach 1 und 3").**
  (1) PREVIEW-TEMPO: /api/motion/preview lief pro Aufruf als frischer
  Python-Subprocess (~2s). Jetzt haelt _PreviewDaemon EINEN warmen
  gfx_engine-Prozess (--preview-server: JSON-Zeile rein, Standbild raus);
  dazu in der Engine ein BG/GRAIN-Cache pro (Stil, Format) - identische
  Arrays, pixelgleich (Diff warm vs. kalt = 0 verifiziert) - und PNG-Encode
  auf compress_level=1 (PNG bleibt verlustfrei; das Korn macht die Datei eh
  inkompressibel: 0.15s statt 0.58s bei +1% Groesse). Ergebnis Ende-zu-Ende:
  0.4-0.65s statt ~2s. Crash-Recovery verifiziert (Daemon gekillt ->
  naechste Preview startet ihn neu, 1.2s; Notnagel-Kaltstart bleibt als
  Fallback). Endpoint rendert jetzt via asyncio.to_thread (blockierte
  vorher den Event-Loop). Nach 500 Previews wird der Prozess praeventiv
  frisch gestartet (Speicher-Hygiene).
  (2) MONITORING: /api/health (ohne Login: prueft DB, 200/503 - gedacht
  fuer externen Gratis-Pinger wie UptimeRobot alle 5 Min, muss Ismet einmal
  einrichten); _notify_admin() mailt Stoerungen ueber den vorhandenen
  SMTP-Weg an DVE_ADMIN_MAIL (Default ismet.01.b@gmail.com), gedrosselt auf
  1 Mail/Stunde pro Stoerungs-Schluessel; beide Worker melden fehlgeschlagene
  Jobs; Watchdog-Thread alle 10 Min: Platte <2 GB frei -> Mail, Job >45 Min
  im Status 'laeuft' -> Mail. Neue Selftest-Szene 'Betrieb / Monitoring'
  (Health, Drossel, Fehl-Job-Alarm, Daemon rendert/ueberlebt kaputte
  Eingaben/bleibt warm). Regression gruen.

- **Optimierungs-Batch (Ismet: "Mach schonmal alles, was du machen kannst.
  Es soll an Qualitaet nicht verlieren.").** 8 Punkte umgesetzt:
  (1) PERFORMANCE Engine: Sprite-Memoization (_pill_memo/_wm_memo - Pillen/
  Wordmark werden pro sichtbarer Zeichenzahl nur 1x gemalt) + Schatten-Cache
  in put() (_shc; nur op>=0.999, vblur<=0.3, |rot|<3 Grad; Key pinnt Sprite-
  Referenz via 'is'). Benchmark pills-Demo: 178s -> 131s (26% schneller).
  QUALITAETS-NACHWEIS: Rotations-Quantisierung erst 0.5 Grad (28% schneller,
  aber Pixel-Diff zeigte sichtbares Schatten-Stepping -> VERWORFEN), final
  0.1 Grad (<=0.05 Grad Fehler = Subpixel im Half-Res-Blur). Verifiziert:
  x264 ist deterministisch (md5-gleich bei Doppel-Encode) -> Rest-Diff
  zwischen Vorher/Nachher-Video ist Rate-Control-Verstaerkung, und die
  Frame-zu-Frame-Bewegungsprofile sind identisch (z.B. 6.58<->6.60 mean),
  kein Stepping, keine Spruenge.
  (2) EMOJI in WhatsApp-Bubbles: _emoji_img() (NotoColorEmoji, embedded_color)
  + _emoji_split() zerlegt Text in Text-/Emoji-Runs; Herz/Flamme/Augen im
  Render verifiziert.
  (3) TEMPLATE-GALERIE statt Text-Segmente: 6 echte Vorschau-Thumbnails
  (web/motion_previews/*.jpg, 270x480, aus den Templates selbst gerendert,
  je 10-20 KB), 3-Spalten-Grid, Akzent-Rahmen auf Auswahl. Browser-Smoke:
  6 Tiles geladen, Klick wechselt Auswahl, 0 JS-Fehler.
  (4) MOTION-FAST-LANE: eigene MQUEUE + motion_worker - ein 10s-Motion-Clip
  wartet nicht mehr hinter langen Caption-Renders; Status zeigt die richtige
  Queue-Position. Verifiziert (Job landet in MQUEUE, Position korrekt).
  (5) PREVIEW-RATE-LIMIT: /api/motion/preview max. 1 Call/1.2s pro User ->
  429; Frontend faengt 429 ab und wiederholt still nach 1.3s (Preview-
  Opacity wird immer restauriert). Mechanik direkt verifiziert.
  (6) MOV-CLEANUP: fertig.mov aelter als DVE_MOV_HOURS (48h) wird geloescht,
  fertig.mp4-Vorschau bleibt - ProRes-Dateien sind gross.
  (7) MOTION-POSTER: _run_motion schreibt poster.jpg (Frame bei 6.8s) fuer
  die Library-Ansicht.
  (8) AUFGERAEUMT: 4 Sandbox-Testjobs entfernt; data/ bleibt via .gitignore
  draussen. Volle Regression gruen: 512/512 + GUI_OK (nach den Aenderungen
  erneut gelaufen).

- **Markt-/Sicherheits-/Bug-Review (Ismets Drei-Fragen-Check).**
  (1) PREISE: Konkurrenz recherchiert (Submagic $20/mo/30 Videos, Captions.ai
  $9.99-24.99/mo Abo, Opus $15/mo/150min, Zeemo ~$6.67/mo). Unsere 9/19/39 Euro
  einmalig (20/60/150 Cr, 0.45->0.26 Euro/min) liegen im Markt; Alleinstellung:
  KEIN Abo + 6 Monate gueltig; Free 3/Monat + Wasserzeichen = exakt das
  Submagic-Muster. Keine Preisaenderung noetig.
  (2) SICHERHEIT: Audit -> 3 Funde, alle gefixt (Commit 'Security-Haertung'):
  jid-Path-Traversal zentral in job_dir() dichtgemacht, 8-MB-Cap auf
  Motion-Uploads, Schema-Endpoint gecacht. Auth-Gates verifiziert. OFFEN
  (bewusst, niedrig): kein Rate-Limit auf /api/motion/preview (eingeloggt,
  ~2s CPU/Call) und kein CSRF-Token (Cookie samesite=lax mildert) - beides
  fuer spaeter notiert.
  (3) BUGS: volle Regression gruen - 502/502 logic + render1 6 + render2a 1 +
  render2b 1 + render2c 2 = 512/512 + GUI_OK; Backend-Suite (Auth, Credits,
  Refunds, Motion-Flows, Traversal) gruen. Bekannte Nicht-Bugs/Offen:
  Windows-/Prod-Test (Ismet), Stripe-Live (bewusst zum Schluss).

- **Motion: ProRes-Vorschau zeigt echte Transparenz.**
  Ismet: "Wenn ich ProRes auswaehle, soll der Hintergrund verschwinden."
  Engine: Preview mit export='mov' rendert jetzt ein ECHTES Alpha-PNG ohne
  Hintergrund (81.5% transparent verifiziert); Frontend legt ein Schachbrett
  dahinter (.mo-frame.alpha, wie im Schnittprogramm), moSync toggelt es mit
  der Export-Wahl. Dabei Race-Condition gefixt: bei schnellen Klicks konnte
  eine ALTE Preview-Antwort die neue ueberschreiben -> Sequenz-Token, ver-
  altete Antworten werden verworfen. Browser-verifiziert (Screenshot:
  WhatsApp-Bubbles frei auf Schachbrett, 0 JS-Fehler).

- **Motion: Notify auf iOS Stand 2026 (Liquid Glass) + Bewegungs-QA.**
  Ismet: "Die Mitteilung kann bitte auf Stand 2026 gebracht werden."
  ios_banner v2: transluzenter Glas-Chip (Alpha 205 - im Alpha-MOV scheint
  das Footage durch), Liquid-Glass-Radius, helle Glas-Kante oben, Icon +
  fetter Titel + Body + 'now'; CAPS-App-Zeile raus (iOS-10-Aera). Padding-
  Fix: Titel stoesst nie ans 'now'. Bewegungs-QA per Zeitverlaufs-Sheet:
  WhatsApp-Chat und Liquid-Glass-Notify ueber die volle Timeline sauber
  (Drop, Push mit Abstand, scharf, Exit).

- **Motion: Realitaets-Look - Chat=WhatsApp, Notify=iOS-Push.**
  Ismet: "Chat sollte mehr nach WhatsApp aussehen. Alle Motion Graphics
  sollten Bezug auf die Realitaet haben." Chat: echte WhatsApp-Bubbles -
  Outgoing gruen (D8F8C6 hell / 005C4B dark) mit Schwaenzchen oben-aussen,
  Uhrzeit + BLAUE Doppelhaken; Incoming weiss/202C33. Farben = WhatsApp
  Light/Dark je nach Stil (RIMMODE). Notify: echter iOS-Push-Banner - Icon,
  App-Name in CAPS + 'now' rechts, fetter Titel, grauer Body; hell (F5F5F7)
  / dunkel (1C1C1E) je Stil. Die uebrigen 4 Templates sind bereits real
  modelliert (iOS-Widgets, App-Store-Karte, Broadcast-Lower-Third,
  Keynote-Pills). Standbilder beide Stile verifiziert.

- **Motion: Zeitverlaufs-QA aller 6 Templates + 3 Bugfixes.**
  Ismet: "Bei Notification kommt das fast am selben Ort. Ueberpruefe alle."
  QA: alle 6 Templates voll gerendert, Frames alle 0.35s als Kontaktblatt
  geprueft + analytischer Transienten-Sweep (Elastic-Overshoot vs. Nachbar-
  Luft). 3 Funde, alle gefixt: (1) HAUPTBUG State-Key-Kollision chat/notify:
  Y-Stack-EMA und vel() (Blur) nutzten dieselben prev_e-Keys -> Position
  kollabierte auf ~20% des Ziels, Banner klebten verblurrt uebereinander
  ("fast am selben Ort"). Fix: eigene Keys nty/cby; Audit aller Keys, Rest
  sauber. (2) Notify-Transienten: Overshoot 55px > 35px Luft -> step 250,
  Drop 0.10H (jetzt 35px bei 80px Luft). (3) CLI --template kannte die 3
  Overlay-Templates nicht (argparse; Web-Pfad war ok) -> Choices aus
  MOTION_SCHEMA. NACHWEIS: Vorher/Nachher-Sheets; alle 6 Templates ueber die
  volle Timeline sauber (pills/widgets/appstore/lowerthird/chat/notify).

- **Motion: UI-Kontext-Sync + ProRes-Preis (2 Credits).**
  Ismet: "Passe das UI an, damit alles passt. ProRes mit extra credits."
  (1) UI: moSync() - Felder passen sich dem Template an: Woerter-Feld mit
  Template-spezifischem Label/Placeholder (pills: 3 Woerter, appstore: Brand,
  lowerthird: Name+Rolle, chat: 3 Messages, notify: 2 Zeilen), bei widgets
  ausgeblendet (nutzt keine Texte); Bild-Upload nur bei pills; totes Logo-Feld
  entfernt (war in der Engine nie verdrahtet). Render-Button zeigt den Preis
  dynamisch ("1 credit" / "2 credits - ProRes 4444 Alpha"), Export-Segment
  mit Preisen, nach MOV-Render direkter Download-Link im Status.
  (2) Preis: MOV = 2 Credits (MOTION_COST_MOV=120), MP4 = 1; Job traegt
  cost_sec, _maybe_refund nutzt ihn (Refund exakt). VERIFIZIERT: TestClient
  mov -120/refund +120/mp4 -60; Browser: Felder togglen korrekt pro Template,
  Button-Preis wechselt, 0 JS-Fehler.

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
