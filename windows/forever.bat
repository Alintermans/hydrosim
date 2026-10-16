@echo off
rem Runs the given command forever: if it crashes or is closed, it restarts
rem after 5 seconds. Used by start-fti.bat — nobody is at the stand to notice.
:loop
%*
echo.
echo [%time%] stopped (exit code %errorlevel%) - restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop
