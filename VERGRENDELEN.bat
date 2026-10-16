@echo off
rem Enkel voor HydroTeam, na het testen: Windows vergrendelen (Ctrl/Alt uit,
rem geen Taakbeheer/afmelden/afsluiten). Vraagt administratorrechten. Daarna herstarten.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0windows\lockdown.ps1\"'"
echo Klaar. Herstart nu de pc.
pause
