# Launch server.py in the background with no console window.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $PSCommandPath

# Prefer the interpreter bundled with the installed product. In a source
# checkout, use the repo venv created by REQUIREMENTS.md before falling back
# to a system pythonw. This keeps the double-click path on the same dependency
# environment as `python server.py`.
$bundled = Join-Path $here "python\pythonw.exe"
$venv = Join-Path $here ".venv\Scripts\pythonw.exe"
if (Test-Path $bundled) {
    $py = $bundled
} elseif (Test-Path $venv) {
    $py = $venv
} else {
    Write-Warning "Bundled and .venv pythonw.exe not found; falling back to system 'pythonw' on PATH."
    $py = "pythonw"
}

Start-Process -FilePath $py -ArgumentList "`"$here\server.py`"" -WindowStyle Hidden
Write-Host "Uoink server launched. Logs: $here\server.log"
