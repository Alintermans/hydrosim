@echo off
rem HydroSim EXPO stand (FTI) — unmanned, offline. Starts, each in its own
rem minimised window that restarts itself if it ever stops:
rem   1. the timing server        (leaderboard on http://127.0.0.1:8088)
rem   2. the collector            (reads Assetto Corsa, reports laps)
rem   3. the autopilot            (wheel button -> AC, one lap, keyboard lock,
rem                                opens the expo screen on the 2nd monitor)
rem Put a shortcut to this file in shell:startup so it runs at logon.
rem Admin: type the admin code from autopilot\autopilot.ini to release the
rem keyboard, then run windows\stop-fti.bat.

cd /d "%~dp0.."

if not exist .venv\Scripts\python.exe (
    echo Run windows\install.ps1 and windows\install-fti.ps1 first.
    pause
    exit /b 1
)
if not exist autopilot\autopilot.ini (
    echo Run windows\install-fti.ps1 first.
    pause
    exit /b 1
)

start "HydroSim server" /min cmd /c windows\forever.bat .venv\Scripts\python.exe serve_windows.py
timeout /t 4 /nobreak >nul
start "HydroSim collector" /min cmd /c windows\forever.bat .venv\Scripts\python.exe -m collector
start "HydroSim autopilot" /min cmd /c windows\forever.bat .venv\Scripts\python.exe -m autopilot
