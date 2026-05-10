@echo off
:: Stops the Yoink helper server. Uses the PID file written by server.py at
:: startup. If the file is missing (server isn't running, or hard-killed
:: previously), this is a no-op.
setlocal
set "PIDFILE=%~dp0server.pid"
if not exist "%PIDFILE%" goto :done
set /p PID=<"%PIDFILE%"
if "%PID%"=="" goto :done
:: Best-effort terminate. Errors are silenced so a stale PID doesn't surface.
taskkill /PID %PID% /F >nul 2>&1
del /Q "%PIDFILE%" >nul 2>&1
:done
endlocal
