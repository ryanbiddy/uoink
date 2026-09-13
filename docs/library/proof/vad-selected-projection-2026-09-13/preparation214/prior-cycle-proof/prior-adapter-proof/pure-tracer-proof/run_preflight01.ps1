$ErrorActionPreference = 'Stop'
$proposalPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$attemptPath = Join-Path $proposalPath 'symbolic-preflight01'
if (Test-Path -LiteralPath $attemptPath) { throw 'Fresh attempt directory required' }
New-Item -ItemType Directory -Path $attemptPath | Out-Null
$archiveNames = @('symbolic_trace.py', 'qualify_symbolic.py', 'BRIEF-GRAMMAR-2026-09-13.md', 'PREQUALIFICATION-CLARIFICATION-2026-09-13.md', 'PREFLIGHT-SETUP-CORRECTION-2026-09-13.md')
foreach ($archiveName in $archiveNames) {
    Copy-Item -LiteralPath (Join-Path $proposalPath $archiveName) -Destination (Join-Path $attemptPath $archiveName)
}
git diff --no-index -- (Join-Path $proposalPath 'draft01\symbolic_trace.py') (Join-Path $proposalPath 'symbolic_trace.py') | Set-Content -LiteralPath (Join-Path $attemptPath 'source-clarification.diff') -Encoding UTF8
if ($LASTEXITCODE -gt 1) { throw 'Source diff generation failed' }
git diff --no-index -- (Join-Path $proposalPath 'preflight-setup-draft01\qualify_symbolic.py') (Join-Path $proposalPath 'qualify_symbolic.py') | Set-Content -LiteralPath (Join-Path $attemptPath 'setup-correction.diff') -Encoding UTF8
if ($LASTEXITCODE -gt 1) { throw 'Setup diff generation failed' }
$sourceBefore = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'symbolic_trace.py') -Algorithm SHA256).Hash.ToLowerInvariant()
$harnessBefore = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'qualify_symbolic.py') -Algorithm SHA256).Hash.ToLowerInvariant()
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$interpreterPath = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe'
$startedUtc = [DateTime]::UtcNow.ToString('o')
& $interpreterPath -I -S -B (Join-Path $attemptPath 'qualify_symbolic.py') 'symbolic-preflight01' 1> (Join-Path $attemptPath 'stdout.json') 2> (Join-Path $attemptPath 'stderr.log')
$readerExit = $LASTEXITCODE
$receipt = [ordered]@{
    label = 'symbolic-preflight01'
    started_utc = $startedUtc
    finished_utc = [DateTime]::UtcNow.ToString('o')
    interpreter = $interpreterPath
    arguments = @('-I', '-S', '-B', 'qualify_symbolic.py', 'symbolic-preflight01')
    actual_reader_exit = $readerExit
    source_sha256_before = $sourceBefore
    source_sha256_after = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'symbolic_trace.py') -Algorithm SHA256).Hash.ToLowerInvariant()
    harness_sha256_before = $harnessBefore
    harness_sha256_after = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'qualify_symbolic.py') -Algorithm SHA256).Hash.ToLowerInvariant()
    scope = 'Literal synthetic pickle bytes only; no checkpoint, adapter main, model or product execution'
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attemptPath 'launch-receipt.json') -Encoding UTF8
Get-Content -Raw -LiteralPath (Join-Path $attemptPath 'stdout.json')
Get-Content -Raw -LiteralPath (Join-Path $attemptPath 'stderr.log')
Write-Output ('ACTUAL_READER_EXIT=' + $readerExit)
exit $readerExit
