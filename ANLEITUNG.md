# DouchkoVE Captions — Was macht welche Einstellung?

Kurzfassung des Ablaufs: **Video(s) wählen → (optional Transkript prüfen) → Preset
wählen → (optional Momente bearbeiten) → Video generieren.** Alles andere ist Feinschliff.

---

## Während ein Render läuft

Alle Knöpfe und Einstellungen sind **gesperrt** (ausgegraut) — damit du nichts
umstellst, was der laufende Render schon halb verarbeitet hat. Sobald er fertig ist,
wird alles automatisch wieder freigegeben.

## Oben: Video wählen

Ein Klick, ein Dialog. Du kannst **mehrere Videos gleichzeitig markieren** (Strg oder
Shift gedrückt halten) — dann bilden sie eine Warteschlange und rendern automatisch
nacheinander durch. Abends einreihen, morgens sind alle fertig. Das Label zeigt, wie
viele noch warten.

---

## Die vier Knöpfe unten

| Knopf | Was passiert |
|---|---|
| **Video generieren** | Der volle Render. Alles wird berechnet, das fertige Video landet neben dem Original als `_captions.mp4`. |
| **Momente** | Öffnet den **Caption-Editor** (siehe unten). Beim ersten Öffnen analysiert das Tool das Video kurz. |
| **Transkript** | Zeigt, was die Spracherkennung verstanden hat, und lässt dich Verhörer korrigieren. Beim ersten Mal pro Video läuft die Transkription (15–45 s), danach öffnet es sofort. |
| **Vorschau · 15 Sek** | Rendert nur die ersten 15 Sekunden — schneller Check, ob der Look sitzt. |

---

## Der Caption-Editor („Momente")

Das ist dein Regiepult. Jede Zeile ist **ein großer Caption-Moment** (nicht jeder
Untertitel — die laufen automatisch). Spalten:

- **An** — Haken raus = dieser Moment fällt weg, der Text läuft dann als normaler Untertitel.
- **Zeit** — Wann im Video der Moment kommt.
- **Text** — Was dort steht. Tippfehler oder Verhörer hier korrigieren.
- **Effekt** — Wie der Text auftritt:
  - *Hinter dir* — Großes Wort taucht hinter der Person auf, schaut über die Schulter.
  - *Buchstaben-Aufbau* — Das Wort baut sich Buchstabe für Buchstabe auf.
  - *Aus der Unschärfe* — Großer Titel kommt weich aus der Unschärfe, Video dunkelt kurz ab.
  - *Nur Umriss* — Feine Kontur-Linie, edel und dezent.
  - *In der Szene* — Der Text steht **in** der Welt: auf Wasser als echtes Wasser-Glas
    (Blender), am Boden mit Schatten. Er bewegt sich mit der Kamera und kann von
    Objekten verdeckt werden.
- **Größe** — *Dezent* (klein, ruhig) / *Normal* / *Groß* (füllt das Bild, mit Sound).
- **Animation** — Der Text lebt zusätzlich. Alle wirken auf **jedem** Effekt:
  *Glitch* (digitaler Riss auf harten Beats), *Puls* (atmet auf dem Bass),
  *Welle* (eine Woge läuft durch die Buchstaben), *Zittern* (nervöse Energie —
  Angst, Stress, Chaos), *Neon* (glimmt und flackert wie Leuchtreklame),
  *Schub* (drückt bei jedem Beat nach vorn — Wachstum, Durchbruch),
  *Bruch* (das Wort zerbricht — Bruchkanten laufen durch, die Scherben kippen weg).
  **Neu dazu (die Klassiker deutscher Talking-Head-Videos):**
  **Sturz** — das Wort fällt und kippt weg. *Die Preise fallen, die Aktien stürzen ab,
  Verlust, Rezession, Pleite, Talfahrt.*
  **Anstieg** — das Wort steigt auf. *Die Mieten steigen, Rekord, Gewinn, teurer,
  klettert, verdoppelt.*
  **Wende** — das Wort dreht sich um die eigene Achse und kommt lesbar zurück.
  *Plötzlich kippt die Stimmung, Umkehr, Gegenteil, stattdessen.*
  **Druck** — das Wort wird flachgedrückt und sackt ab. *Schulden, Last, Zwang,
  Abgaben, erdrückt.*
  **Schwund** — das Wort löst sich fleckig auf und steigt wie Rauch. *Verschwunden,
  verloren, vorbei, verpufft.*
  **Knall** — das Wort knallt groß herein und steht dann. Für die Pointe:
  *Fakt, Beweis, endgültig, definitiv.*
  Oder *keine*.
  **Wichtig — der Satz entscheidet:** Das Tool schaut auf den ganzen **Satz**, nicht nur
  auf das hervorgehobene Wort. Bei „Deutschland **bricht** seine Versprechen" zerbricht
  also DEUTSCHLAND — obwohl im Wort selbst nichts von brechen steht. Genauso bei
  „die **Mieten steigen** ins Unermessliche" (Anstieg) oder „deine **Rente** ist
  **verschwunden**" (Schwund). Das gilt für alle Animationen.
  Was das Wort selbst sagt, hat weiter Vorrang: bei „das **Wachstum** bricht ein"
  gewinnt Wachstum → *Schub*, nicht Bruch.
- **Farbwelt** (neu) — Drei Möglichkeiten:
  *Automatisch* — die Captions greifen die Farben der Szene auf (Empfehlung).
  *Elegantes Schwarz* — Tiefschwarz mit Graphit-Akzent. Der Look für helle Bilder:
  Studio, weiße Wand, Tageslicht, Produktaufnahmen auf Weiß.
  *Elegantes Weiß* — Softweiß mit warmem Grau. Der High-End-Look für dunkle und
  farbige Bilder. Material, Licht und Verdeckung bleiben immer automatisch.
  Zu finden unter *Farben & Material*.
- **Szene** — Worauf der Text sitzt. *auto* = die KI schaut sich das Bild an und entscheidet.
  Nur überschreiben, wenn sie danebenliegt (z. B. Wasser statt Boden erkannt).
- **Lage** — *liegend* = Text liegt flach auf der Fläche (wie aufgemalt).
  *stehend* = Text steht aufrecht in der Szene. *auto* = KI entscheidet.

**Speichern** rendert **nur die geänderten Momente** neu und setzt sie direkt ins
fertige Video ein. Kein kompletter Neu-Render für eine kleine Korrektur.
(Ausnahme: geänderte Sound-Effekte greifen erst beim nächsten Voll-Render.)

---

## Tab „Start"

- **Plattform** — Wie dicht Captions gesetzt werden.
  *YouTube*: wenige, große Momente. *Ausgewogen*: Momente mit Kontext dazwischen.
  *TikTok & Reels*: durchgehende Captions, Wort für Wort.
- **Hook** — Der Videoanfang läuft dichter und energischer; dort entscheidet sich,
  ob jemand dranbleibt. Jetzt frei einstellbar:
  - *Länge*: 8 / 15 / 30 / 60 Sekunden (Schalter aus = kein Hook).
    Faustregel: Shorts 8–15 s, YouTube-Video 30 s, langes Format 60 s.
  - *Stärke*: **Sanft** (nur die Highlights — Doku, Interview), **Normal**,
    **Stark** (fast jeder Satz bekommt einen Effekt — TikTok, Reels).
  - **Sofort-Hook** (neu in v48): Das stärkste frühe Statement steht als Karte
    **ab dem ersten Bild** und bleibt, bis es gesprochen wird — kein leerer
    Videoanfang. 65–71 % der Zuschauer entscheiden in den ersten 3 Sekunden,
    ob sie bleiben. (Schalter im Hook-Bereich, Standard: an.)
  - **Hook-Takt** (neu in v48, automatisch): Im Hook-Fenster kommen die
    Kamera-Impulse des Pattern-Interrupts im 3–5-Sekunden-Takt statt alle
    9 Sekunden — genau dort fällt die Bleiben-oder-Wischen-Entscheidung.
- **B-Roll wird ignoriert** (v48): Auf Schnittbildern ohne Sprecher (Drohne,
  Produktaufnahmen, Footage) passiert jetzt gar nichts mehr — kein Text, keine
  Keyword-Momente und **auch keine Kamera-Impulse** (Zoom/Schwenk). Fremdes
  Material behält seine eigene Bildkomposition. Die Impulse laufen nahtlos
  weiter, sobald der Sprecher wieder im Bild ist.
- **Watchtime halten** — Zwei Mechaniken gegen das Wegklicken:
  - *Kein Leerlauf länger als 8/12/20 Sek*: Lange Strecken ohne visuelles Ereignis
    sind die klassischen Absprungstellen. Reißt die Lücke zu weit auf, hebt das Tool
    das stärkste Wort im Fenster zu einem **dezenten** Moment — der Blick bekommt
    wieder etwas zu tun, ohne dass es marktschreierisch wird. (Aus = keine Füller.)
  - *Pattern-Interrupt*: Auch in ruhigen Passagen ohne Text gibt die Kamera alle paar
    Sekunden einen Impuls (Push, Schwenk). Ein Ereignis fürs Auge, ganz ohne Text —
    der klassische Retention-Trick aus dem Schnitt.
- **Safe-Zone 9:16** — Im Hochformat bleiben die TikTok-Buttons rechts und die
  Beschreibung unten frei — der Text rutscht automatisch aus dem Weg.
- **Kundenprofil** — Alle Einstellungen unter einem Namen speichern und mit einem
  Klick wiederherstellen. Pro Kunde ein Profil.
- **Preset** — Ein Klick setzt den kompletten Look (Plattform-Dichte, Effekte, Kamera,
  Schrift, Text-Stil, Sound). Die vier Looks überschneiden sich bewusst nicht:
  | Preset | Für wen | Effekte | Schrift | Momente |
  |---|---|---|---|---|
  | **TikTok** | Shorts, Reels, FYP | Hinter dir + Nur Umriss | TikTok Sans | alle 4 s, laut |
  | **Creator** | Talking-Head, Business | Hinter dir + Buchstaben-Aufbau | Montserrat | alle 7 s |
  | **Cinematic** | B-Roll, Doku, Marken | Aus der Unschärfe + In der Szene | Inter | alle 11 s, ruhig |
  | **Clean** | Interviews, Corporate | nur Buchstaben-Aufbau | Poppins | alle 14 s, ohne Sound |

  Die Umgebungs-Anpassung (Szenen-Farben, Wasser-/Boden-Material, Kamera-Track,
  Verdeckung) läuft in **jedem** Preset. Presets steuern den Geschmack, nie die
  Intelligenz.

- **Typografie** — Die Schrift der Captions. *TikTok* / *Creator* / *Cinematic* sind die
  aktuellen Trend-Schriften, der Rest sind Stil-Alternativen.
- **Text-Stil**
  - *Klassisch* — flacher Text, ruhig und clean.
  - *3D* — der Text hat Tiefe, Extrusion und Licht, wirkt wie ein Objekt im Raum.
  - *Kinetisch* — der Text lebt: skaliert, kippt und reagiert auf die Betonung der Stimme.
  - *3D + Kinetisch* — beides zusammen, der volle Look.
- **Farben & Material** — Keine Einstellung nötig. Die Farben kommen aus dem Bild,
  das Material aus der Szene (Wasser → Glas, Boden → massiv), Licht und Verdeckung
  passen sich automatisch an.
- **Ausgabe**
  - *Qualität* — Auflösung: 720p für Social, 1080p Standard, 4K nur bei 4K-Quellen.
  - *Tempo* — **nur Rechenzeit vs. Dateigröße, der Look ändert sich nicht.**
    *Schnell*: kurze Rechenzeit, etwas größere Datei. *Standard*: ausgewogen (Empfehlung).
    *Maximal*: kleinste Datei bei bester Qualität, dauert am längsten.
  - *Premiere-Master (ProRes)* — verlustarme .mov für den Schnitt in Premiere.
    Riesige Dateien, nur wenn du weiterschneidest.

## Tab „Feintuning"

- **Effekte** — Welche der fünf Effekte überhaupt vorkommen dürfen (siehe Editor oben).
  Das Tool rotiert dann zwischen den erlaubten.
- **Dynamik** — Die künstliche Kamera-Bewegung (Zooms, Schwenks, Pushs auf Keywords).
  *Ruhig*: fast unmerklich, Interviews/Corporate. *Ausgewogen*: sichtbare, ruhige
  Bewegung (Standard). *Energisch*: häufige, kräftige Bewegungen, Shorts/Reels.

## Tab „Profi"

- **Feinregler → Abstand zwischen Momenten** — Mindest-Pause zwischen zwei großen
  Caption-Momenten. Klein (2–4 s) = sehr dicht, gut für TikTok. Groß (10–15 s) =
  seltene, dafür wirkungsvolle Momente, gut für lange YouTube-Videos. Die normalen
  Untertitel laufen davon unabhängig weiter.
- **Feinregler → Sound-Effekte** — Lautstärke der automatischen Sounds (Impact bei
  großen Wörtern, Whoosh bei Einflügen, Ticks bei Zahlen). 0 % = ganz aus.
- **Intelligenz (KI-Regie)** — Die KI liest das Transkript und entscheidet, welche
  Wörter Momente verdienen; die Bild-KI schaut sich zusätzlich Frames an und wählt
  Szene und Lage. Aus = einfache Regeln statt KI.
- **Keywords & Sprache** — *Immer*: diese Wörter werden garantiert zum Moment.
  *Nie*: diese nie. *Sprache im Video*: hilft der Spracherkennung.


## Sound-Pack — WICHTIG: ohne Pack keine Sounds

Es gibt keine eingebauten Sounds mehr. Die waren aus Formeln erzeugt und klangen
billig — die sind raus. **Ohne Sound-Pack rendert das Programm dein Video ohne
Sound-Effekte** (der Originalton bleibt natürlich). Das ist Absicht: lieber Stille
als ein billiger Sound.

Also: einmal den Pack laden, dann hast du echte, aufgenommene Sounds.

**So geht's (einmalig, ~10 Minuten):**
1. Kostenlos auf **freesound.org** registrieren → Settings → API credentials →
   „New credential". Den **API-Key** kopieren.
2. In DouchkoVE unter **Profi → Sound-Pack** den Key eintragen.
3. **„Echte Sounds laden"** klicken. Das Programm lädt für alle 14 Sounds den
   meistgenutzten CC0-Sound herunter.
4. **„Anhören & auswählen"** öffnen. Pro Sound siehst du, was er im Video macht.
   Hör sie an, klick „Andere" für Alternativen, nimm die, die sitzen.
   *Das ist der wichtige Schritt* — welcher Sound gut klingt, kann kein Programm
   messen, das entscheidest du.

**Warum CC0?** Das heißt Public Domain: kommerziell frei nutzbar, keine
Namensnennung nötig, keine Lizenzprobleme. Andere Lizenzen lädt das Programm
bewusst gar nicht erst.

**Eigene Sounds (z. B. aus einem Epidemic-Sound-Abo):** Leg die Datei einfach als
`sfx\pack\impact.wav` (bzw. `crack.wav`, `slam.wav` …) ab — sie gewinnt immer und
wird nie überschrieben. So bleibt deine Lizenz sauber: die Datei liegt bei dir,
nicht in der Software.
