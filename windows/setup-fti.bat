@echo off
rem ONE-CLICK setup of the FTI expo stand. Double-click this file on the sim
rem PC while it still has internet. It:
rem   1. fetches the FTI version of HydroSim (git branch "fti")
rem   2. installs Python dependencies (install.ps1, only the first time)
rem   3. configures the stand (install-fti.ps1): finds Assetto Corsa and the
rem      Radical, writes autopilot.ini + admin code, creates the FTI event,
rem      downloads the fonts, offers autostart
rem Safe to run again: existing settings are kept.

cd /d "%~dp0.."
echo == HydroSim FTI setup ==

where git >nul 2>&1
if errorlevel 1 (
    echo Git not found - skipping update. Make sure this folder has the "fti" version.
) else (
    git fetch origin
    git checkout fti
    git pull --ff-only origin fti
    if errorlevel 1 (
        echo.
        echo Could not update from GitHub. Fix the message above, or continue with what is here.
        pause
    )
)

rem A Python environment copied or moved from another folder breaks: rebuild it.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -c "import flask, waitress" >nul 2>&1
    if errorlevel 1 (
        echo Python environment does not work here - rebuilding it...
        rmdir /s /q .venv
    )
)
if not exist .venv\Scripts\python.exe (
    powershell -NoProfile -ExecutionPolicy Bypass -File windows\install.ps1
    if errorlevel 1 goto failed
)
powershell -NoProfile -ExecutionPolicy Bypass -File windows\install-fti.ps1
if errorlevel 1 goto failed

echo.
echo Setup done. Read the "Next steps" above, then test with windows\start-fti.bat
pause
exit /b 0

:failed
echo.
echo Setup stopped because of the error above.
pause
exit /b 1
