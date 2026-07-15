@echo off
chcp 65001 >nul
title DouchkoVE - Einrichtung
echo ============================================
echo   DouchkoVE Captions - Einmalige Einrichtung
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [FEHLER] Python wurde nicht gefunden.
    echo Bitte Python 3.12 installieren und dabei "Add to PATH" anhaken:
    echo https://www.python.org/downloads/release/python-31210/
    echo.
    pause
    exit /b 1
)
echo [OK] Python gefunden

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [FEHLER] ffmpeg wurde nicht gefunden.
    echo Bitte ffmpeg installieren und C:\ffmpeg\bin in den Path eintragen.
    echo Download: https://www.gyan.dev/ffmpeg/builds/
    echo.
    pause
    exit /b 1
)
echo [OK] ffmpeg gefunden
echo.

echo Installiere Python-Pakete, das dauert einige Minuten...
python -m pip install --upgrade pip >nul
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [FEHLER] Paket-Installation fehlgeschlagen. Bild an Claude schicken.
    pause
    exit /b 1
)
echo.
echo Installiere GPU-Bibliotheken (NVIDIA), ca. 1-2 GB...
python -m pip install "onnxruntime-gpu[cuda,cudnn]"
echo.

if defined OPENAI_API_KEY (
    echo [OK] OpenAI API-Key ist bereits gesetzt.
) else (
    set /p APIKEY="Bitte OpenAI API-Key eingeben (sk-...): "
    setx OPENAI_API_KEY "%APIKEY%" >nul
    echo [OK] API-Key gespeichert.
)
echo.
echo ============================================
echo   Einrichtung fertig!
echo   Ab jetzt: Doppelklick auf "DouchkoVE.bat"
echo   oder ein Video auf "Video hierher ziehen.bat" ziehen.
echo ============================================
pause
