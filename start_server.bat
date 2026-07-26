@echo off
REM Launch server.py in the background with no console window.
setlocal
cd /d "%~dp0"
set "PYTHONW=%~dp0python\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"
start "" "%PYTHONW%" "%~dp0server.py"
endlocal
