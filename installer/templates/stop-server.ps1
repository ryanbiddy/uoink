# Stops the Uoink helper server. The .bat wrapper is what the Start Menu
# shortcut points at; this PS script is the canonical implementation.
#
# Two-stage shutdown:
#   1) PID file path -- read server.pid, verify it actually points at our
#      pythonw.exe (a stale PID could otherwise end an unrelated process
#      that inherited the same PID), then kill it.
#   2) Defensive sweep -- if PID file was missing or stale, use CIM to find
#      any pythonw.exe whose command line references this install's
#      server.py and stop those too.
# Finishes with a balloon notification so the user gets the same kind of
# visible confirmation they got on start.

$installDir = $PSScriptRoot
$pidFile = Join-Path $installDir 'server.pid'
$stoppedAny = $false

# NOTE: $pid is a PowerShell automatic variable holding the *current*
# process id, so we use $serverPid to avoid clobbering it. The previous
# version assigned to $pid and then did Stop-Process -Id $pid, which on
# some PS versions silently killed the running PowerShell host instead.
if (Test-Path $pidFile) {
    $serverPid = (Get-Content -Raw -ErrorAction SilentlyContinue $pidFile).Trim()
    if ($serverPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$serverPid) -ErrorAction SilentlyContinue
        # Only kill if the PID actually belongs to a pythonw.exe -- otherwise
        # a stale entry could terminate something innocent.
        if ($proc -and $proc.ProcessName -eq 'pythonw') {
            Stop-Process -Id ([int]$serverPid) -Force -ErrorAction SilentlyContinue
            $stoppedAny = $true
        }
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
}

# Defensive sweep for the hard-kill / missing-PID-file case.
$cmdLineMatch = "*" + $installDir + "\server.py*"
$swept = Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like $cmdLineMatch }
foreach ($p in $swept) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    $stoppedAny = $true
}

# Confirmation balloon. Symmetric with the start-up notification so the
# user knows the click did something. Skipped if nothing was actually
# running (no need to tell them about a no-op).
if ($stoppedAny) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $n = New-Object System.Windows.Forms.NotifyIcon
        # Brand the balloon with the bundled uoink.ico when present; fall back
        # to the generic OS info icon if it's missing or can't be loaded.
        $icoPath = Join-Path $installDir 'uoink.ico'
        if (Test-Path $icoPath) {
            try { $n.Icon = New-Object System.Drawing.Icon($icoPath) }
            catch { $n.Icon = [System.Drawing.SystemIcons]::Information }
        } else {
            $n.Icon = [System.Drawing.SystemIcons]::Information
        }
        $n.BalloonTipIcon = 'Info'
        $n.BalloonTipTitle = 'Uoink stopped'
        $n.BalloonTipText = "Start it again from your Start Menu when you're ready to uoink."
        $n.Visible = $true
        $n.ShowBalloonTip(5000)
        Start-Sleep -Seconds 6
        $n.Dispose()
    } catch {
        # Notification UI failed -- the kill itself already succeeded, so
        # silence and exit cleanly.
    }
}
