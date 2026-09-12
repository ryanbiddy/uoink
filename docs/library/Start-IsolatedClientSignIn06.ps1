[CmdletBinding()]
param([switch]$PreflightOnly)

$ErrorActionPreference = 'Stop'
$taskInstallRoot = 'E:\AI\projects\uoink\installation-receipts\Agent Install 06'
$taskClientRoot = Join-Path $taskInstallRoot 'p4-client\profile\client'
$taskClaudeExe = 'C:\Users\hello\.local\bin\claude.exe'
$taskRecordRoot = Join-Path $taskInstallRoot 'signin-launcher'

function Assert-OwnedPath([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path)
    $boundary = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($full -ine $boundary -and -not $full.StartsWith($boundary + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A prepared sign-in path is outside its isolated directory.'
    }
    $node = $full
    while ($node) {
        if (Test-Path -LiteralPath $node) {
            $item = Get-Item -LiteralPath $node -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'A prepared sign-in path contains a reparse point.'
            }
        }
        $parent = [IO.Path]::GetDirectoryName($node)
        if ($parent -eq $node) { break }
        $node = $parent
    }
    return $full
}

$taskPrepPath = Assert-OwnedPath (Join-Path $taskClientRoot 'client-config-preparation.json') $taskClientRoot
$taskPrep = Get-Content -LiteralPath $taskPrepPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($taskPrep.candidate -ne '6697dffc30c98e97b22ecc9a5a35dfd3e8a91f5d' -or $taskPrep.apply_enabled -ne $false) {
    throw 'The prepared client does not match package-06.'
}
foreach ($entry in $taskPrep.hashes.PSObject.Properties) {
    $file = Assert-OwnedPath (Join-Path $taskClientRoot $entry.Name) $taskClientRoot
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw ('Prepared client file changed: ' + $entry.Name)
    }
}
$taskLaunch = Get-Content -LiteralPath (Join-Path $taskClientRoot 'launch-isolated.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$taskExpectedConfig = Join-Path $taskClientRoot 'claude-config'
if ([IO.Path]::GetFullPath($taskLaunch.environment.CLAUDE_CONFIG_DIR) -ine $taskExpectedConfig -or
    [IO.Path]::GetFullPath($taskLaunch.cwd) -ine $taskClientRoot) {
    throw 'Wrong client configuration directory.'
}
$null = Assert-OwnedPath $taskExpectedConfig $taskClientRoot
if (-not (Test-Path -LiteralPath $taskClaudeExe -PathType Leaf)) { throw 'Claude executable is missing.' }
if ($PreflightOnly) {
    [pscustomobject]@{ preflight = 'passed'; prepared_files = @($taskPrep.hashes.PSObject.Properties).Count;
        configuration = $taskExpectedConfig; authentication_started = $false; model_started = $false } | ConvertTo-Json
    return
}

$null = Assert-OwnedPath $taskRecordRoot $taskInstallRoot
$null = New-Item -ItemType Directory -Path $taskRecordRoot -Force
$taskRecordPath = Join-Path $taskRecordRoot ('signin-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N') + '.json')
$taskRecord = [ordered]@{ started_utc = [DateTime]::UtcNow.ToString('o'); configuration = $taskExpectedConfig;
    state = 'sign_in_starting'; login_exit = $null; status_exit = $null; logged_in = $false;
    model_started = $false; usage_credits_off = 'not_confirmed'; credentials_copied = $false;
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
function Save-SignInRecord { $taskRecord | ConvertTo-Json | Set-Content -LiteralPath $taskRecordPath -Encoding UTF8 }
Save-SignInRecord
try {
    foreach ($key in 'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL',
        'CLAUDE_CODE_OAUTH_TOKEN','CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR','CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
        'CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY') {
        Remove-Item -LiteralPath ('Env:' + $key) -ErrorAction SilentlyContinue
    }
    foreach ($entry in $taskLaunch.environment.PSObject.Properties) {
        [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, 'Process')
    }
    if ([IO.Path]::GetFullPath($env:CLAUDE_CONFIG_DIR) -ine $taskExpectedConfig) { throw 'Wrong sign-in profile.' }
    Set-Location -LiteralPath $taskClientRoot
    $Host.UI.RawUI.WindowTitle = 'Uoink - Claude sign-in'
    Clear-Host
    Write-Host 'Uoink test client: sign in to Claude' -ForegroundColor Cyan
    Write-Host 'Finish sign-in in the browser that opens. Keep this window open until it finishes.'
    Write-Host 'If Claude offers a code, paste it into this window only.'
    Write-Host ''
    & $taskClaudeExe auth login --claudeai
    $taskRecord.login_exit = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Claude sign-in did not complete.' }
    $taskStatusText = & $taskClaudeExe auth status --json
    $taskRecord.status_exit = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Claude could not confirm sign-in.' }
    $taskStatus = ($taskStatusText -join "`n") | ConvertFrom-Json
    $taskRecord.logged_in = ($taskStatus.loggedIn -eq $true)
    if (-not $taskRecord.logged_in) { throw 'Claude did not report a signed-in account.' }
    $taskRecord.state = 'signed_in'
    Write-Host ''
    Write-Host 'Signed in. Return to Codex and say done.' -ForegroundColor Green
    Write-Host 'No model calls have started.'
} catch {
    $taskRecord.state = 'sign_in_incomplete'
    Write-Host ''
    Write-Host 'Sign-in did not finish. Return to Codex so I can check the result.' -ForegroundColor Yellow
} finally {
    $taskRecord.finished_utc = [DateTime]::UtcNow.ToString('o')
    Save-SignInRecord
    $taskStatusText = $null
    $taskStatus = $null
}
$null = Read-Host 'Press Enter to close this window'
