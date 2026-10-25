# Uoink installer upgrade prep -- stop the old helper + clear the splash
# sentinel BEFORE the new files land. Invoked from installer\uoink.iss's
# PrepareToInstall hook via Exec(powershell.exe). Shipped as Flags: dontcopy
# so it lives in {tmp} during install and is never deployed to {app}.
#
# Why this exists (two related v2.2.0 bugs both rooted in stale state):
#
#   Bug 1 -- the old pythonw.exe helper from the prior install keeps holding
#   127.0.0.1:5179 after the user clicks Install. The new helper [Run]
#   launches into a bound port, exits silently, and the user is stuck on
#   the previous build until the next reboot. Hit on 2.1.0->2.1.1 and
#   2.1.1->2.2.0.
#
#   Bug 2 -- the .first-run-done sentinel from the previous install lives at
#   %LOCALAPPDATA%\Uoink\.first-run-done. The new helper sees it and skips
#   the splash, so upgraders never get the "Uoink is running" confirmation.
#
# This script handles both. Failure to stop recovery or release the port
# returns a nonzero exit so setup stops before replacing files. All actions
# are logged to %TEMP%\uoink-upgrade-prep.log for post-mortem if a user
# reports the new helper still not starting.

param([string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Uoink'))

$ErrorActionPreference = 'Continue'
$logPath = Join-Path $env:TEMP 'uoink-upgrade-prep.log'

function Write-PrepLog($message) {
    $line = "{0}  {1}" -f ([DateTime]::Now.ToString('s')), $message
    try { $line | Out-File -FilePath $logPath -Append -Encoding utf8 } catch {}
}

function Test-Port5179Bound {
    # Cheap TCP connect with a tight timeout. Returns $true iff something is
    # listening on 127.0.0.1:5179. We avoid Test-NetConnection because it is
    # 5+ seconds slow when nothing answers and is missing on stripped-down
    # Windows SKUs.
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', 5179, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(250)
        if ($ok) {
            try { $client.EndConnect($iar) | Out-Null; return $true } catch { return $false }
        }
        return $false
    } catch { return $false } finally {
        if ($client) { try { $client.Close() } catch {} }
    }
}

function Wait-PortFree($timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Port5179Bound)) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return -not (Test-Port5179Bound)
}

# Stop retrying before probing the old helper or replacing installed files.
# Older installs have no supervisor and continue through the existing flow.
$recoveryScript = Join-Path $InstallDir 'uoink_supervisor.py'
if (Test-Path -LiteralPath $recoveryScript) {
    try {
        $ErrorActionPreference = 'Stop'
        & (Join-Path $InstallDir 'python\python.exe') $recoveryScript --stop
        if ($LASTEXITCODE -ne 0) { throw 'Could not pause helper recovery before upgrade.' }
    } catch {
        Write-PrepLog ('Upgrade stopped: could not pause helper recovery. ' + $_.Exception.Message)
        exit 1
    } finally {
        $ErrorActionPreference = 'Continue'
    }
}
Write-PrepLog '==== upgrade prep start ===='
Write-PrepLog ("LOCALAPPDATA={0}" -f $env:LOCALAPPDATA)
$portStart = Test-Port5179Bound
Write-PrepLog ("port 5179 bound at start? {0}" -f $portStart)

# ---- Step 1: graceful POST /helper/quit ----------------------------------
# Token lives at <install>\token.txt. We try the Uoink path first, then the
# legacy Yoink path so a user who never touched 2.0/2.1 but jumps Yoink ->
# 2.2 still gets a clean handoff.
$tokenCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Uoink\token.txt'),
    (Join-Path $env:LOCALAPPDATA 'Yoink\token.txt')
)
$token = $null
foreach ($tp in $tokenCandidates) {
    if (Test-Path $tp) {
        try {
            $token = ([System.IO.File]::ReadAllText($tp)).Trim()
            if ($token) {
                Write-PrepLog ("read token from {0}" -f $tp)
                break
            }
        } catch {
            Write-PrepLog ("could not read {0}: {1}" -f $tp, $_.Exception.Message)
        }
    }
}

if ($token) {
    try {
        $headers = @{ 'X-Uoink-Token' = $token; 'Content-Type' = 'application/json' }
        $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:5179/helper/quit' `
            -Method POST -Headers $headers -Body '{}' -UseBasicParsing `
            -TimeoutSec 3 -ErrorAction Stop
        Write-PrepLog ("POST /helper/quit -> HTTP {0}" -f $resp.StatusCode)
    } catch {
        # Expected if no helper is running, or if it shut down so fast the
        # response never came back. Either way: not fatal.
        Write-PrepLog ("POST /helper/quit failed (often benign): {0}" -f $_.Exception.Message)
    }
} else {
    Write-PrepLog 'no token file found -- skipping graceful quit'
}

# ---- Step 2: wait up to 3 seconds for the port to free -------------------
$freed = Wait-PortFree 3
Write-PrepLog ("port 5179 free after graceful wait? {0}" -f $freed)

# ---- Step 3: hard-kill stale python(w).exe under Yoink/Uoink roots --------
# Do this even when the HTTP port is already free: GUI subprocesses such as
# uoink_splash.py can hold pywebview DLLs open without binding 5179, causing
# Inno to abort while replacing site-packages files.
$roots = @(
    $InstallDir,
    (Join-Path $env:LOCALAPPDATA 'Uoink'),
    (Join-Path $env:LOCALAPPDATA 'Yoink')
)
if (-not $freed) {
    Write-PrepLog 'port still bound -- escalating to Stop-Process under Yoink/Uoink roots'
} else {
    Write-PrepLog 'port is free -- still stopping Yoink/Uoink python processes to unlock GUI DLLs'
}
try {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction Stop
} catch {
    Write-PrepLog ("Get-CimInstance failed (CIM service down?): {0}" -f $_.Exception.Message)
    $procs = @()
}
foreach ($p in $procs) {
    $exe = $p.ExecutablePath
    if (-not $exe) { continue }
    $matched = $false
    foreach ($r in $roots) {
        if ($exe.StartsWith($r.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { $matched = $true; break }
    }
    if (-not $matched) { continue }
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-PrepLog ("Stop-Process pid={0} exe={1}" -f $p.ProcessId, $exe)
    } catch {
        Write-PrepLog ("Stop-Process pid={0} failed: {1}" -f $p.ProcessId, $_.Exception.Message)
    }
}
$freedAfterKill = Wait-PortFree 2
Write-PrepLog ("port 5179 free after Stop-Process wait? {0}" -f $freedAfterKill)
if (-not $freedAfterKill) {
    Write-PrepLog 'Upgrade stopped: port 5179 is still in use. Close Uoink or restart Windows, then run setup again.'
    exit 1
}

# ---- Step 4: clear the splash sentinel ------------------------------------
# Force the splash to fire on first launch after upgrade, same as a clean
# install. Pascal also runs DeleteFile() against this path as a belt-and-
# suspenders backup in case PowerShell itself failed to launch.
$sentinel = Join-Path $env:LOCALAPPDATA 'Uoink\.first-run-done'
if (Test-Path $sentinel) {
    try {
        Remove-Item -Path $sentinel -Force -ErrorAction Stop
        Write-PrepLog ("removed first-run sentinel: {0}" -f $sentinel)
    } catch {
        Write-PrepLog ("could not remove first-run sentinel: {0}" -f $_.Exception.Message)
    }
} else {
    Write-PrepLog 'no first-run sentinel present (clean install or already cleared)'
}

Write-PrepLog '==== upgrade prep done ===='
exit 0
