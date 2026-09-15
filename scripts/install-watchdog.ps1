[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "Uoink Helper",
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"

$installRoot = (Resolve-Path -LiteralPath $InstallDir).Path
$serverPath = Join-Path $installRoot "server.py"
if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) {
    throw "server.py was not found under '$installRoot'."
}

if (-not $PythonPath) {
    $bundled = Join-Path $installRoot "python\pythonw.exe"
    if (Test-Path -LiteralPath $bundled -PathType Leaf) {
        $PythonPath = $bundled
    } else {
        $command = Get-Command pythonw.exe -ErrorAction SilentlyContinue
        if (-not $command) {
            $command = Get-Command python.exe -ErrorAction Stop
        }
        $PythonPath = $command.Source
    }
}
$pythonExe = (Resolve-Path -LiteralPath $PythonPath).Path

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument ('"{0}"' -f $serverPath) `
    -WorkingDirectory $installRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited

if ($PSCmdlet.ShouldProcess($TaskName, "register or update Uoink watchdog")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Starts Uoink at logon and retries three times after failure." `
        -Force | Out-Null
    Write-Host "Installed Scheduled Task '$TaskName' for $serverPath"
}
