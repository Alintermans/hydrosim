@echo off
rem Na de beurs: zet Ctrl/Alt, Taakbeheer, afmelden en afsluiten terug.
rem Vraagt administratorrechten (klik Ja met de muis). Daarna herstarten.
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0windows\unlock.ps1\"'"
echo Klaar. Herstart nu de pc.
pause
