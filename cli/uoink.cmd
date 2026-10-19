@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%~dp0..\python\python.exe" "%~dp0..\uoink_cli.py" %*
exit /b %ERRORLEVEL%
