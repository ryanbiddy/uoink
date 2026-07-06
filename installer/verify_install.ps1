param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion,

    [int]$TimeoutSeconds = 25,

    [switch]$ProbeHealth
)

$ErrorActionPreference = 'Continue'
$logPath = Join-Path $env:TEMP 'uoink-install-verify.log'

function Write-VerifyLog($message) {
    $line = "{0}  {1}" -f ([DateTime]::Now.ToString('s')), $message
    try { $line | Out-File -FilePath $logPath -Append -Encoding utf8 } catch {}
}

Write-VerifyLog '==== install verification start ===='
Write-VerifyLog ("expected version={0}" -f $ExpectedVersion)

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionFile = Join-Path $appDir 'VERSION'
try {
    $fileVersion = ([System.IO.File]::ReadAllText($versionFile)).Trim()
    Write-VerifyLog ("VERSION file={0}" -f $fileVersion)
    if ($fileVersion -ne $ExpectedVersion) {
        Write-VerifyLog ("VERSION mismatch: expected {0}, got {1}" -f $ExpectedVersion, $fileVersion)
        exit 20
    }
} catch {
    Write-VerifyLog ("could not read VERSION file: {0}" -f $_.Exception.Message)
    exit 21
}

# Bundle-presence guard. The v3.2.1 break shipped because new top-level modules
# reached build.ps1 staging but never made it into uoink.iss [Files]. This
# asserts the files that have bitten us (or would) are actually in {app}.
$requiredFiles = @(
    'source_manifest.py',
    'openapi_bridge.py',
    'reddit_extractor.py',
    'x_extractor.py',
    'defaults\style_anchors.json'
)
foreach ($rf in $requiredFiles) {
    $rfPath = Join-Path $appDir $rf
    if (-not (Test-Path $rfPath)) {
        Write-VerifyLog ("MISSING bundled file: {0}" -f $rf)
        exit 23
    }
}
Write-VerifyLog ("bundled files present: {0}" -f ($requiredFiles -join ', '))

if (-not $ProbeHealth) {
    Write-VerifyLog 'files-only install verification OK; live health probe skipped'
    exit 0
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$lastError = $null
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:5179/health' -TimeoutSec 2
        $json = $health | ConvertTo-Json -Depth 6 -Compress
        Write-VerifyLog ("health={0}" -f $json)
        if ($health.ok -eq $true -and [string]$health.version -eq $ExpectedVersion) {
            Write-VerifyLog 'install verification OK'
            exit 0
        }
        $lastError = "expected version $ExpectedVersion, got $($health.version)"
    } catch {
        $lastError = $_.Exception.Message
        Write-VerifyLog ("health probe failed: {0}" -f $lastError)
    }
    Start-Sleep -Milliseconds 750
}

Write-VerifyLog ("install verification FAILED: {0}" -f $lastError)
exit 22
