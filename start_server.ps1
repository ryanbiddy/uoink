# Launch server.py in the background with no console window.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process -FilePath "pythonw" -ArgumentList "`"$here\server.py`"" -WindowStyle Hidden
Write-Host "Yoink server launched. Logs: $here\server.log"
