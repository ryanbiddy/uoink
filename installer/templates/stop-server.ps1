# PowerShell fallback for Stop-Server. The .bat wrapper is what the Start
# Menu shortcut points at; this script is here for users who prefer to
# invoke PS directly, and as a more thorough sweep when the PID file is
# missing or stale.
$installDir = $PSScriptRoot
$pidFile = Join-Path $installDir 'server.pid'

if (Test-Path $pidFile) {
    $pid = (Get-Content -Raw -ErrorAction SilentlyContinue $pidFile).Trim()
    if ($pid -match '^\d+$') {
        Stop-Process -Id [int]$pid -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
}

# Defensive sweep — kill any pythonw.exe whose command line points at this
# install's server.py. Catches the hard-kill case where server.pid was left
# behind on a previous crash.
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like ("*" + $installDir + "\server.py*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
