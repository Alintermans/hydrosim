@echo off
rem HydroSim — start everything on the sim PC:
rem   1. the timing server (leaderboard + admin + sync to sim.hydroteam.be)
rem   2. the collector (reads Assetto Corsa, reports laps)
rem   3. the kiosk browser on http://127.0.0.1:8088/kiosk
rem Drag the kiosk window to the second screen once; Windows remembers it.

cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
    echo Run windows\install.ps1 first.
    pause
    exit /b 1
)

start "HydroSim server" .venv\Scripts\python.exe serve_windows.py
timeout /t 3 /nobreak >nul
start "HydroSim collector" .venv\Scripts\python.exe -m collector
timeout /t 2 /nobreak >nul
start "" msedge --new-window --kiosk "http://127.0.0.1:8088/kiosk" --edge-kiosk-type=fullscreen

echo.
echo HydroSim is running. Close the two console windows to stop it.
echo Kiosk exit: Ctrl+Alt+Del or Alt+F4.
