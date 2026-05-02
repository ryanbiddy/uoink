@echo off
REM Fallback launcher in case the .pyw association is broken.
REM Uses pythonw so no console window appears.
setlocal
cd /d "%~dp0"
start "" pythonw "youtube_extractor.pyw"
endlocal
