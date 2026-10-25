param([string]$Script, [string]$InstallDir, [string]$Scenario, [string]$EventsPath)
$ErrorActionPreference = 'Stop'
$global:recoveryFixtureKilled = $false
$global:recoveryFixtureTime = [DateTime]'2026-01-01T00:00:00'
function Record-Event([string]$Name) {
    [IO.File]::AppendAllText($EventsPath, $Name + "`n")
}
function Get-Date {
    $global:recoveryFixtureTime = $global:recoveryFixtureTime.AddSeconds(1)
    return $global:recoveryFixtureTime
}
function Start-Sleep { param($Milliseconds) }
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($ClassName -ne 'Win32_Process' -or $Filter -ne "Name = 'python.exe' OR Name = 'pythonw.exe'") {
        throw 'Unexpected process query'
    }
    Record-Event 'process-query'
    return @(
        [pscustomobject]@{ExecutablePath=(Join-Path $InstallDir 'python\pythonw.exe'); ProcessId=123},
        [pscustomobject]@{ExecutablePath=(Join-Path ($InstallDir + '-foreign') 'python\pythonw.exe'); ProcessId=456}
    )
}
function Stop-Process {
    param($Id, [switch]$Force, $ErrorAction)
    if ($Id -ne 123 -or -not $Force) { throw 'Attempted to stop a foreign process' }
    $global:recoveryFixtureKilled = $true
    Record-Event 'kill-owned'
}
function Invoke-WebRequest { throw 'No token exists in this fixture; HTTP must not run' }
function Remove-Item {
    param($Path, [switch]$Force, $ErrorAction)
    if ($Path -ne (Join-Path $env:LOCALAPPDATA 'Uoink\.first-run-done')) { throw 'Unexpected removal' }
    Record-Event 'clear-sentinel'
}
# Replace only the two OS boundaries embedded in the source: native --stop
# invocation and socket probe. Execute the remaining production control flow.
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Script did not parse' }
$probe = @($ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-Port5179Bound'
}, $true))
$stop = @($ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and $node.Extent.Text -like '& *--stop'
}, $true))
if ($probe.Count -ne 1 -or $stop.Count -ne 1) { throw 'OS boundary changed; review the mocks' }
$replacements = @(
    [pscustomobject]@{Start=$probe[0].Body.Extent.StartOffset; End=$probe[0].Body.Extent.EndOffset; Text=@'
{
    Record-Event 'port-probe'
    if ($Scenario -eq 'free') { return $false }
    if ($Scenario -eq 'kill-frees' -and $global:recoveryFixtureKilled) { return $false }
    return $true
}
'@},
    [pscustomobject]@{Start=$stop[0].Extent.StartOffset; End=$stop[0].Extent.EndOffset; Text=@'
Record-Event 'stop-intent'
if ($Scenario -eq 'stop-fails') { $global:LASTEXITCODE = 1 } else { $global:LASTEXITCODE = 0 }
'@}
)
$source = [IO.File]::ReadAllText($Script)
foreach ($replacement in ($replacements | Sort-Object Start -Descending)) {
    $source = $source.Substring(0, $replacement.Start) + $replacement.Text + $source.Substring($replacement.End)
}
& ([ScriptBlock]::Create($source)) -InstallDir $InstallDir
exit $LASTEXITCODE
