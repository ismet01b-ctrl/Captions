# DouchkoVE Premium Captions

Automatische Premium-Untertitel im Editorial-Stil. Ein Klick, fertiges Video.

## So einfach geht es jetzt

1. Einmalig: Doppelklick auf **setup.bat**. Die prueft alles, installiert alles und fragt nach deinem API-Key.
2. Rendern, Weg A: Video auf **"Video hierher ziehen.bat"** ziehen. Fertig.
3. Rendern, Weg B: Doppelklick auf **"Premium Captions.bat"**. Da stellst du Farbe, Effekte, Kamera, Keywords und Qualitaet per Klick ein und siehst den Fortschritt.

Das fertige Video liegt immer neben dem Original, mit _captions im Namen.

Voraussetzung fuer setup.bat: Python 3.12 (mit "Add to PATH") und ffmpeg muessen installiert sein. Die Anleitung dafuer steht unten.

## Manuelle Einrichtung (Referenz, macht setup.bat automatisch)

1. Python 3.10 bis 3.12 installieren (python.org, beim Installieren "Add to PATH" anhaken)
2. ffmpeg installieren und in den PATH legen (gyan.dev/ffmpeg/builds, "release full")
3. Im Ordner eine Konsole oeffnen und ausfuehren:

```
pip install -r requirements.txt
```

4. OpenAI API-Key setzen (einmalig, PowerShell als Admin):

```
setx OPENAI_API_KEY "sk-dein-key"
```

Danach die Konsole neu oeffnen.

Hinweis GPU: onnxruntime-gpu braucht CUDA 12. Wenn das Matting laut Konsole auf "CPUExecutionProvider" laeuft statt "CUDAExecutionProvider", fehlen die CUDA-Bibliotheken. Das Tool funktioniert dann trotzdem, nur langsamer. Schnellste Loesung: `pip install onnxruntime-gpu[cuda,cudnn]`.

Beim ersten Start laedt das Tool zwei Modelle automatisch herunter (ca. 15 MB).

## Nutzung

```
python render.py video.mp4
```

Ergebnis: video_captions.mp4 im selben Ordner. Ausserdem wird video_transcript.json gespeichert.

Weitere Beispiele:

```
python render.py video.mp4 --out fertig.mp4
python render.py video.mp4 --keywords "Schufa,Score,Konto"
python render.py video.mp4 --transcript video_transcript.json
```

Der letzte Befehl nutzt das gespeicherte Transkript und spart den API-Aufruf. Praktisch, wenn du nur am Stil drehst und neu renderst.

Keywords korrigieren: Transkript-JSON oeffnen, Schreibfehler fixen, dann mit --transcript neu rendern. Woerter erzwingen oder verbieten geht in der config.yaml unter keywords.

## Stil anpassen

Alles liegt in der config.yaml. Die wichtigsten Hebel:

- colors.accent: deine Markenfarbe als RGB
- fonts: eigene TTF-Dateien in den fonts-Ordner legen und Pfade eintragen
- effects.keyword_rotation: Effekte entfernen oder Reihenfolge aendern. Nur [behind] eintragen heisst: immer der grosse Behind-Moment.
- camera.strength: 0 schaltet alle Kamerabewegungen ab
- camera.side_rotation: [none] heisst komplett statische Kamera bei Seitentexten

## Grenzen (ehrlich)

- Gebaut fuer Talking-Head-Videos mit einer Person. Mehrere Personen verwirren das Matting und das Tracking.
- Das Freistellen ist bei ruhigem Hintergrund und gutem Licht sehr sauber. Bei schnellen Bewegungen oder Haaren vor unruhigem Hintergrund koennen Kanten flackern.
- Whisper macht selten Wortfehler. Vor wichtigen Uploads das Transkript-JSON kurz gegenlesen.
- 4K-Quellen: output.height auf 1080 lassen und in Premiere hochskalieren, so wie du es kennst. Natives 4K-Rendering geht, dauert aber deutlich laenger (matting_downsample dann auf 0.125).
