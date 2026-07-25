[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SetupScript,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$ExpectedVersion
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $SetupScript -PathType Leaf)) {
    throw "Release installer-link source is missing: $SetupScript"
}

$source = [System.IO.File]::ReadAllText($SetupScript)
$pattern = '(?m)^(?<prefix>\s*const\s+PUBLISHED_INSTALLER_VERSION\s*=\s*["''])(?<version>\d+\.\d+\.\d+)(?<suffix>["''];?\s*)$'
$versionMatches = [regex]::Matches($source, $pattern)

if ($versionMatches.Count -ne 1) {
    throw "Release build requires exactly one PUBLISHED_INSTALLER_VERSION declaration in $SetupScript; found $($versionMatches.Count)."
}

$replacement = '${prefix}' + $ExpectedVersion + '${suffix}'
$updated = [regex]::Replace($source, $pattern, $replacement, 1)
$updatedMatches = [regex]::Matches($updated, $pattern)

if (
    $updatedMatches.Count -ne 1 -or
    $updatedMatches[0].Groups['version'].Value -ne $ExpectedVersion
) {
    throw "Release build could not stage installer link version $ExpectedVersion."
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($SetupScript, $updated, $utf8NoBom)
Write-Host "Release installer link staged for v$ExpectedVersion"
