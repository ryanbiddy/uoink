@echo off
REM Launch server.py in the background with no console window.
setlocal
cd /d "%~dp0"
start "" pythonw "server.py"
endlocal
