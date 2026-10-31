@echo off
setlocal
set "UOINK_ROOT=%~dp0"
set "UOINK_PYTHON=%UOINK_ROOT%python\python.exe"
if not exist "%UOINK_PYTHON%" set "UOINK_PYTHON=python"
rem Agent subcommands run the agent CLI, as cli\uoink.cmd does. No arguments,
rem helper flags and the helper's own commands (doctor, rebuild-index, search,
rem clips) still run server.py. Isolation flags may come before the subcommand.
call :first_command %*
for %%C in (tools call capture recent get note status connect skill serve mcp --text -h --help) do (
    if "%UOINK_COMMAND%"=="%%C" goto agent_cli
)
"%UOINK_PYTHON%" "%UOINK_ROOT%server.py" %*
exit /b %ERRORLEVEL%

:agent_cli
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%UOINK_PYTHON%" "%UOINK_ROOT%uoink_cli.py" %*
exit /b %ERRORLEVEL%

:first_command
set "UOINK_COMMAND="
:first_command_next
if "%~1"=="--isolated-profile" goto first_command_skip
if "%~1"=="--isolated-port" goto first_command_skip
if "%~1"=="--isolated-from-install-dir" goto first_command_skip
set "UOINK_COMMAND=%~1"
exit /b 0
:first_command_skip
shift
shift
goto first_command_next
