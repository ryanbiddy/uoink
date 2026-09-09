param([Parameter(Mandatory=$true)][string]$Candidate)
$ErrorActionPreference = 'Stop'
$candidateRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
Set-Location -LiteralPath $candidateRepo
$candidateBranch = (& git branch --show-current).Trim()
$candidateHead = (& git rev-parse HEAD).Trim()
if ($candidateBranch -ne 'cc/living-library-candidate' -or $candidateHead -ne $Candidate) {
    throw 'Build requires the exact frozen candidate branch and SHA'
}
if (& git status --porcelain --untracked-files=no) { throw 'Tracked candidate must be clean before build' }
$candidateRoot = [IO.Path]::GetFullPath($candidateRepo).TrimEnd('\')
$candidatePrefix = $candidateRoot + '\'
$candidateAncestor = $candidateRoot
while ($candidateAncestor) {
    $candidateEntry = Get-Item -LiteralPath $candidateAncestor -Force
    if ($candidateEntry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Reparse checkout ancestor: ' + $candidateAncestor) }
    $candidateAncestor = Split-Path -Parent $candidateAncestor
}
$candidateTargets = @('build','build\cache','build\_ffmpeg_tmp','installer\staging','installer\staging\python')
$candidateChecked = @()
foreach ($relative in $candidateTargets) {
    $target = [IO.Path]::GetFullPath((Join-Path $candidateRoot $relative))
    if (-not $target.StartsWith($candidatePrefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw ('Build target escaped candidate: ' + $target)
    }
    $ancestor = $target
    while ($ancestor -and $ancestor.StartsWith($candidatePrefix,[StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $ancestor) {
            $entry = Get-Item -LiteralPath $ancestor -Force
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Reparse build ancestor: ' + $ancestor) }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    if (Test-Path -LiteralPath $target) {
        $links = @(Get-ChildItem -LiteralPath $target -Recurse -Force -Attributes ReparsePoint -ErrorAction Stop)
        if ($links.Count) { throw ('Reparse entry under build target: ' + $target) }
    }
    $candidateChecked += $target
}
$candidateReceipt = Join-Path $candidateRoot ('_scratch\candidate-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $candidateReceipt) { throw 'Fresh build receipt directory required' }
New-Item -ItemType Directory -Path $candidateReceipt | Out-Null
$candidateProfile = Join-Path $candidateReceipt 'profile'
New-Item -ItemType Directory -Path $candidateProfile | Out-Null
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
foreach ($name in @('APPDATA','LOCALAPPDATA','XDG_DATA_HOME','TEMP','TMP','UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR')) {
    [Environment]::SetEnvironmentVariable($name,$candidateProfile,'Process')
}
$env:UOINK_INDEX_PATH = Join-Path $candidateProfile 'unused-index.db'
$candidateStarted = [DateTimeOffset]::UtcNow
$candidateResult = [ordered]@{
    candidate=$Candidate; branch=$candidateBranch; started_utc=$candidateStarted.ToString('o')
    build_script_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath build.ps1).Hash.ToLowerInvariant()
    recursive_targets_checked=$candidateChecked; clean_switch=$false
    profile=$candidateProfile; receipt_directory=$candidateReceipt
    status='running'; installed=$false; pushed=$false; published=$false
}
$candidateJson = Join-Path $candidateReceipt 'receipt.json'
$candidateResult | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $candidateJson
try {
    & .\build.ps1 *>&1 | Tee-Object -FilePath (Join-Path $candidateReceipt 'build.log')
    if ($LASTEXITCODE -ne 0) { throw ('Build exited ' + $LASTEXITCODE) }
    $candidateExe = Join-Path $candidateRoot 'build\Uoink-Setup-3.8.0.exe'
    if (-not (Test-Path -LiteralPath $candidateExe)) { throw 'Expected installer artifact missing' }
    $candidateResult.status='built; not installed'
    $candidateResult.artifact=[ordered]@{
        path=$candidateExe; bytes=(Get-Item -LiteralPath $candidateExe).Length
        sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $candidateExe).Hash.ToLowerInvariant()
    }
} catch {
    $candidateResult.status='failed'
    $candidateResult.error=$_.Exception.Message
    throw
} finally {
    $candidateResult.finished_utc=[DateTimeOffset]::UtcNow.ToString('o')
    $candidateResult.elapsed_s=([DateTimeOffset]::UtcNow-$candidateStarted).TotalSeconds
    $candidateResult.tracked_changes_after=@(& git status --porcelain --untracked-files=no)
    $candidateResult | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $candidateJson
}
