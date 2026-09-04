@echo off
setlocal
set "UOINK_ROOT=%~dp0"
set "UOINK_PYTHON=%UOINK_ROOT%python\python.exe"
if not exist "%UOINK_PYTHON%" set "UOINK_PYTHON=python"
"%UOINK_PYTHON%" "%UOINK_ROOT%server.py" %*
exit /b %ERRORLEVEL%
