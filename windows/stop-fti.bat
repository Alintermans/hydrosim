@echo off
rem Stops the expo stand: autopilot (releases the keyboard), collector,
rem server, Assetto Corsa and the expo screen.
taskkill /F /T /FI "WINDOWTITLE eq HydroSim*" >nul 2>&1
taskkill /F /IM acs.exe >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*autopilot*browser-profile*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo HydroSim expo stand stopped.
