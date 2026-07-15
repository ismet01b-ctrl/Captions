@echo off
chcp 65001 >nul
title DouchkoVE - Rendern
if "%~1"=="" (
    echo Einfach eine Videodatei auf diese Datei ziehen.
    pause
    exit /b
)
cd /d "%~dp0"
echo Rendere: %~nx1
echo.
python render.py "%~1"
echo.
echo Fertig. Das Video liegt im selben Ordner wie das Original.
pause
