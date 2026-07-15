# DouchkoVE Captions — Arbeitsanweisung für Claude Code

Automatische Premium-Untertitel im Editorial-Stil. Python/Windows-Desktop-App.
Läuft **lokal auf Ismets PC** mit seinem eigenen `OPENAI_API_KEY`. Kein Verkauf,
kein Server, kein Abo, kein Lizenzsystem. **Jede Entscheidung dient der Qualität.**

## Oberste Regeln (nicht verhandelbar)
1. **Qualität über alles.** Niemals ein Feature vereinfachen, degradieren oder
   durch eine Heuristik ersetzen, um Zeit/Kosten zu sparen. Im Zweifel: die
   aufwändigere, bessere Lösung.
2. **Kein Deliver ohne grünen Selftest.** Erst wenn ALLE Tests grün sind, gilt
   etwas als fertig. Nie Teilstände als fertig ausgeben.
3. **Fragen statt raten.** Bei Unklarheit über Architektur/Verhalten nachfragen,
   nicht annehmen. Ismet entscheidet.
4. **Nichts ungefragt umbauen.** Keine Architektur-Änderungen ohne Bestätigung.
5. **Ehrlich bleiben.** Tests laufen hier auf CPU mit synthetischem Material.
   Echte GPU-/Qualitätswirkung sieht Ismet auf Windows mit echtem Material —
   das immer klar sagen, nie so tun als sei es final verifiziert.

## Kommunikation
Ismet ist direkt und terse. **Effizienzmodus:** keine Floskeln, kurze klare
Sätze, nur Code + exakte Schritte. Technische Tiefe bleibt voll erhalten,
nur Füllmaterial weg. Korrektur ohne Rechtfertigung annehmen.

## Stack
Python, tkinter (Canvas-basierte Custom-Widgets), ffmpeg, Blender 4.5.11,
OpenAI Whisper API (Transkription) + GPT-4o (KI-Regie), RVM-Matting (ONNX),
MediaPipe Face, DirectML (Ismets GPU). Fonts als Variable-Font-Instanzen.

## Dateien
- `render.py` — Pipeline: Transkription → KI-Regie → Matting → Face-Tracking →
  Compositing → Kamera → Encode
- `gui.py` — tkinter-GUI (Apple-Dark, Canvas-Cards, iOS-Switch, Segmented)
- `selftest.py` — Testsuite
- `blender_engine.py` — 3D-Wasserglas-Renderer
- `sfx_engine.py` / `sfx_pack.py` — CC0-Sound-System (Freesound)
- `config.yaml` — alle Einstellungen
- `PROJEKT_STATUS.md` — **komplette Versionshistorie v1–v67, hier zuerst lesen**
- `ANLEITUNG.md` — Nutzer-Anleitung

## KI-Regie (Kern der Qualität — NICHT optional machen)
- `ai_direct()` — GPT-4o wählt Keywords/Phrasen/Effekte/Wucht
- `ai_scene_direct()` — GPT-4o-Vision entscheidet Szene/Lage pro Moment
Beide laufen über Ismets lokalen `OPENAI_API_KEY`. Die Heuristik-Fallbacks
existieren nur als Notnagel bei fehlendem Key — nie als Standardweg bewerben.

## Transkription
Nur OpenAI Whisper API (`whisper-1`) - beste Qualitaet fuer Namen/Fachbegriffe.
Lokale faster-whisper-Option wurde in v72 komplett entfernt (Qualitaet > alles,
kein Umschalt-Ballast).

## Selftest — Ablauf (Pflicht vor jedem Deliver)
Gesamt 265/265 grün (Stand v67). Läuft nur unter Linux/CPU mit synthetischen
Assets; GUI-Tests headless via `xvfb-run`.

```bash
# Testmaterial: /tmp/st_clip.mp4  + /tmp/st_transcript.json
# In Etappen (Rendern ist langsam, sonst Timeout):
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=logic     # 255
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render1   # 6
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2a  # 1
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2b  # 1
python selftest.py /tmp/st_clip.mp4 /tmp/st_transcript.json --part=render2c  # 2
```
GUI-Smoke separat:
```bash
xvfb-run -a python3 -c "import tkinter as tk, gui; r=tk.Tk(); gui.App(r); r.destroy(); print('GUI_OK')"
```

## Deliver-Muster (jede neue Version)
1. Selftest erweitern (neues Feature bekommt Tests)
2. Volle Regression grün
3. `PROJEKT_STATUS.md`-Eintrag (was neu, ehrliche Ursache, Beweis, Test-Hinweise)
4. Zip nach Ablage (ohne `__pycache__/models/sfx`)
5. Deutscher Summary im Effizienzmodus

## Wichtige Prinzipien (aus der Historie)
- **Sound:** nur echte CC0-Library-Sounds (Freesound), kein Synthetik-Fallback.
  Stille ist besser als billiger Ton. Ohne `sfx/pack` laufen Videos STUMM.
- **B-Roll:** in ALLEN Systemen ausschließen (auch Kamera-Impulse).
- **GUI:** Rounded Cards nur via Canvas (nicht tk.Frame).
- **Animationen:** immer über zentrales `anim_apply()` routen.
- **Config-Sicherheit:** in Tests NIE `app.save_cfg()` gegen echte config.yaml.
- **Selftest-Integrität:** 4 Presets (TikTok/Creator/Cinematic/Clean) ohne
  überlappende fx/Fonts/Kameras/Dichten.
- **Blender-Demo:** `/tmp/demo_cfg.yaml` (4 Frames / 36–40 Samples / 1000px).

## Offene echte Punkte
- Sound-Pack: Ismet wählt/schickt CC0-Zip → ohne Pack stumm.
- OpenAI-Key-Rotation (lokal in Ismets Umgebung).
- Windows-Test mit echtem Material + neuer Maskenqualität 'hoch'.
