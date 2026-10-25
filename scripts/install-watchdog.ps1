[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath,
    [ValidateSet('Register', 'Unregister', 'Status', 'Disable', 'Ownership')]
    [string]$Mode = 'Register'
)

$ErrorActionPreference = 'Stop'
# Isolated installs never own ordinary login startup.
if ($env:UOINK_ISOLATED_PROFILE -or (Test-Path -LiteralPath (Join-Path $InstallDir 'isolated-install.json'))) {
    throw 'Isolated Uoink does not change login startup.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = 'Uoink Helper-' + $identity.User.Value
$installRoot = (Resolve-Path -LiteralPath $InstallDir).Path
$supervisorPath = Join-Path $installRoot 'uoink_supervisor.py'
$runPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$expectedRun = '"{0}" "{1}"' -f (Join-Path $installRoot 'python\pythonw.exe'), (Join-Path $installRoot 'server.py')
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    $owned = @($existing.Actions | Where-Object { $_.Arguments -eq ('"{0}" --startup' -f $supervisorPath) })
    if ($owned.Count -ne 1 -or $existing.Principal.UserId -notin @($identity.Name, $identity.User.Value)) {
        throw 'The helper task belongs to another install. Login startup was not changed.'
    }
}
$oldTask = Get-ScheduledTask -TaskName 'Uoink Helper' -ErrorAction SilentlyContinue
$oldArgument = '"{0}"' -f (Join-Path $installRoot 'server.py')
$ownedOldTask = $oldTask -and $oldTask.Principal.UserId -in @($identity.Name, $identity.User.Value) -and
    @($oldTask.Actions | Where-Object { $_.Arguments -eq $oldArgument }).Count -eq 1
if ($Mode -eq 'Status') {
    if ($existing -and $existing.State -ne 'Disabled') { Write-Output 'enabled' } else { Write-Output 'disabled' }
    return
}
if ($Mode -eq 'Ownership') {
    # Migration must also respect an owned task whose login trigger is disabled.
    if ($existing) { Write-Output 'owned' } else { Write-Output 'absent' }
    return
}
if ($Mode -in @('Unregister', 'Disable')) {
    if ($existing -and $PSCmdlet.ShouldProcess($taskName, $Mode)) {
        if ($Mode -eq 'Disable') {
            Disable-ScheduledTask -TaskName $taskName | Out-Null
        } else {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
    }
    if ($ownedOldTask -and $PSCmdlet.ShouldProcess('Uoink Helper', $Mode)) {
        if ($Mode -eq 'Disable') { Disable-ScheduledTask -TaskName 'Uoink Helper' | Out-Null }
        else { Unregister-ScheduledTask -TaskName 'Uoink Helper' -Confirm:$false }
    }
    # Also clean an owned Run value retained after a failed upgrade migration.
    $legacy = Get-ItemProperty -LiteralPath $runPath -Name Uoink -ErrorAction SilentlyContinue
    if ($legacy -and $legacy.Uoink -eq $expectedRun -and $PSCmdlet.ShouldProcess('Uoink Run value', $Mode)) {
        Remove-ItemProperty -LiteralPath $runPath -Name Uoink -ErrorAction Stop
    }
    return
}
if (-not (Test-Path -LiteralPath $supervisorPath -PathType Leaf)) {
    throw 'uoink_supervisor.py is missing. Login startup was not changed.'
}
if (-not $PythonPath) { $PythonPath = Join-Path $installRoot 'python\pythonw.exe' }
$pythonExe = (Resolve-Path -LiteralPath $PythonPath).Path
$action = New-ScheduledTaskAction -Execute $pythonExe `
    -Argument ('"{0}" --startup' -f $supervisorPath) -WorkingDirectory $installRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
# Python owns the retry budget. Never stack scheduler retries.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($taskName, 'Register helper recovery and migrate login startup')) {
    $legacy = Get-ItemProperty -LiteralPath $runPath -Name Uoink -ErrorAction SilentlyContinue
    $legacyValue = if ($legacy) { $legacy.Uoink } else { $null }
    if ($legacyValue -and $legacyValue -ne $expectedRun) {
        throw 'The Uoink Run entry belongs to another install. Login startup was not changed.'
    }
    # Register enabled before removing the Run value. Even if setup is killed
    # between those operations, login still works. Both entry paths enter the
    # same supervisor lock, including legacy server.py launches in this build.
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal `
        -Description 'Starts Uoink at login with bounded crash recovery.' -Force | Out-Null
    try {
        if ($ownedOldTask) { Disable-ScheduledTask -TaskName 'Uoink Helper' -ErrorAction Stop | Out-Null }
        if ($legacyValue) { Remove-ItemProperty -LiteralPath $runPath -Name Uoink -ErrorAction Stop }
    } catch {
        if ($legacyValue) {
            New-ItemProperty -LiteralPath $runPath -Name Uoink -Value $legacyValue -PropertyType String -Force | Out-Null
        } elseif ($existing -and $existing.State -ne 'Disabled') {
            Register-ScheduledTask -TaskName $taskName -InputObject $existing -Force | Out-Null
        }
        if ($ownedOldTask -and $oldTask.State -ne 'Disabled') {
            Enable-ScheduledTask -TaskName 'Uoink Helper' -ErrorAction Stop | Out-Null
        }
        throw
    }
    if ($ownedOldTask) { Unregister-ScheduledTask -TaskName 'Uoink Helper' -Confirm:$false }
    Write-Output "Installed helper recovery task '$taskName'."
}
