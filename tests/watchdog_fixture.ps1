param([string]$Script, [string]$InstallDir, [string]$Scenario)
$ErrorActionPreference = 'Stop'
$env:UOINK_ISOLATED_PROFILE = ''
$events = [System.Collections.Generic.List[string]]::new()
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$expectedName = 'Uoink Helper-' + $identity.User.Value
$expectedArgument = '"{0}" --startup' -f (Join-Path $InstallDir 'uoink_supervisor.py')
$runValue = '"{0}" "{1}"' -f (Join-Path $InstallDir 'python\pythonw.exe'), (Join-Path $InstallDir 'server.py')
$global:recoveryFixtureTask = $null
if ($Scenario -in @('update', 'unregister', 'disable', 'status', 'foreign')) {
    $global:recoveryFixtureTask = [pscustomobject]@{
        Actions = @([pscustomobject]@{Arguments=$expectedArgument})
        Principal = [pscustomobject]@{UserId=$identity.Name}
        State = 'Ready'
    }
}
if ($Scenario -eq 'foreign') { $global:recoveryFixtureTask.Actions[0].Arguments = 'foreign' }
function Assert-Equal($Actual, $Expected) {
    if ($Actual -cne $Expected) { throw "Expected [$Expected], got [$Actual]" }
}
function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    if ($TaskName -eq 'Uoink Helper') {
        if ($Scenario -eq 'legacy-task') {
            return [pscustomobject]@{
                Actions=@([pscustomobject]@{Arguments=('"{0}"' -f (Join-Path $InstallDir 'server.py'))})
                Principal=[pscustomobject]@{UserId=$identity.Name}
                State='Ready'
            }
        }
        return $null
    }
    Assert-Equal $TaskName $expectedName
    return $global:recoveryFixtureTask
}
function New-ScheduledTaskAction {
    param($Execute, $Argument, $WorkingDirectory)
    Assert-Equal $Execute (Join-Path $InstallDir 'python\pythonw.exe')
    Assert-Equal $Argument $expectedArgument
    Assert-Equal $WorkingDirectory $InstallDir
    return 'action'
}
function New-ScheduledTaskTrigger {
    param([switch]$AtLogOn, $User)
    Assert-Equal $AtLogOn.IsPresent $true
    Assert-Equal $User $identity.Name
    return 'trigger'
}
function New-ScheduledTaskSettingsSet {
    param([switch]$Disable, [switch]$StartWhenAvailable, [switch]$AllowStartIfOnBatteries,
          [switch]$DontStopIfGoingOnBatteries, $ExecutionTimeLimit, $MultipleInstances)
    Assert-Equal $Disable.IsPresent $false
    foreach ($setting in @($StartWhenAvailable, $AllowStartIfOnBatteries, $DontStopIfGoingOnBatteries)) {
        Assert-Equal $setting.IsPresent $true
    }
    Assert-Equal $ExecutionTimeLimit ([TimeSpan]::Zero)
    Assert-Equal $MultipleInstances 'IgnoreNew'
    return 'settings'
}
function New-ScheduledTaskPrincipal {
    param($UserId, $LogonType, $RunLevel)
    Assert-Equal $UserId $identity.Name
    Assert-Equal $LogonType 'Interactive'
    Assert-Equal $RunLevel 'Limited'
    return 'principal'
}
function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $Settings, $Principal, $Description, [switch]$Force, $InputObject)
    Assert-Equal $TaskName $expectedName
    Assert-Equal $Action 'action'
    Assert-Equal $Trigger 'trigger'
    Assert-Equal $Settings 'settings'
    Assert-Equal $Principal 'principal'
    Assert-Equal $Force.IsPresent $true
    Assert-Equal $Description 'Starts Uoink at login with bounded crash recovery.'
    $events.Add('register')
    if ($Scenario -eq 'register-failure') { throw 'injected registration failure' }
}
function Enable-ScheduledTask {
    param($TaskName, $ErrorAction)
    Assert-Equal $TaskName $expectedName
    $events.Add('enable')
    if ($Scenario -eq 'enable-failure') { throw 'injected enable failure' }
}
function Disable-ScheduledTask {
    param($TaskName, $ErrorAction)
    if ($TaskName -eq 'Uoink Helper') { $events.Add('disable-old'); return }
    Assert-Equal $TaskName $expectedName
    $events.Add('disable')
}
function Unregister-ScheduledTask {
    param($TaskName, $Confirm)
    if ($TaskName -eq 'Uoink Helper') { Assert-Equal $Confirm $false; $events.Add('unregister-old'); return }
    Assert-Equal $TaskName $expectedName
    Assert-Equal $Confirm $false
    $events.Add('unregister')
}
function Get-ItemProperty {
    param($LiteralPath, $Name, $ErrorAction)
    Assert-Equal $LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    Assert-Equal $Name 'Uoink'
    if ($Scenario -in @('clean', 'legacy-task', 'absent')) { return $null }
    return [pscustomobject]@{Uoink=$runValue}
}
function Remove-ItemProperty {
    param($LiteralPath, $Name, $ErrorAction)
    Assert-Equal $LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    Assert-Equal $Name 'Uoink'
    $events.Add('remove-run')
    if ($Scenario -eq 'remove-failure') { throw 'injected removal failure' }
}
function New-ItemProperty {
    param($LiteralPath, $Name, $Value, $PropertyType, [switch]$Force)
    Assert-Equal $LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    Assert-Equal $Name 'Uoink'
    Assert-Equal $Value $runValue
    Assert-Equal $PropertyType 'String'
    Assert-Equal $Force.IsPresent $true
    $events.Add('restore-run')
}
$mode = switch ($Scenario) {
    'unregister' { 'Unregister' }
    'absent' { 'Unregister' }
    'disable' { 'Disable' }
    'status' { 'Status' }
    default { 'Register' }
}
$failed = $false
$result = $null
try {
    $result = & $Script -InstallDir $InstallDir -Mode $mode -WhatIf:($Scenario -eq 'whatif')
} catch {
    if ($_.Exception.Message -notmatch 'injected|belongs to another install') { throw }
    $failed = $true
}
[pscustomobject]@{events=@($events); failed=$failed; result=$result} | ConvertTo-Json -Compress
