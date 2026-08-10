@echo off
rem Like start.bat, but the collector fabricates laps (no Assetto Corsa needed).
rem Use this to test the screens, the popup and the sync before an event.

cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
    echo Run windows\install.ps1 first.
    pause
    exit /b 1
)

start "HydroSim server" .venv\Scripts\python.exe serve_windows.py
timeout /t 3 /nobreak >nul
start "HydroSim collector (demo)" .venv\Scripts\python.exe -m collector --demo
timeout /t 2 /nobreak >nul
start "" msedge --new-window --kiosk "http://127.0.0.1:8088/kiosk" --edge-kiosk-type=fullscreen
