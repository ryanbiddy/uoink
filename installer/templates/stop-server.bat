@echo off
:: Stops the Yoink helper server. Thin wrapper around stop-server.ps1 --
:: the PS script holds the canonical logic (PID validation, defensive
:: sweep, confirmation balloon) and is what the Start Menu shortcut
:: ultimately runs through. Hidden window so clicking the shortcut
:: doesn't flash a console.
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0stop-server.ps1"
