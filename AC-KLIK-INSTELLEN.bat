@echo off
rem Eenmalig: leert waar de autopilot in het startmenu van Assetto Corsa moet
rem klikken (het stuur-icoon linksboven). Laat START-STAND draaien, dubbelklik
rem dit, druk op X op het stuur en klik in AC op het stuur-icoon.
cd /d "%~dp0"
.venv\Scripts\python.exe -m autopilot --where
echo.
echo Herstart nu de stand: STOP-STAND en daarna START-STAND.
pause
