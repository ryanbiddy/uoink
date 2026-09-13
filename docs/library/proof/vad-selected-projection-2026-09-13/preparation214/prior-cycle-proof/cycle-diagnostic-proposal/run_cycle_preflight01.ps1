$ErrorActionPreference = 'Stop'
$proposalPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$attemptPath = Join-Path $proposalPath 'cycle-diagnostic-preflight01'
if (Test-Path -LiteralPath $attemptPath) { throw 'Fresh qualification directory required' }
New-Item -ItemType Directory -Path $attemptPath | Out-Null
New-Item -ItemType Directory -Path (Join-Path $attemptPath 'before') | Out-Null
foreach ($archiveName in @('read_symbolic_inventory.py', 'qualify_cycle.py', 'BRIEF-2026-09-13.md', 'QUALIFICATION-SCOPE-2026-09-13.md')) {
    Copy-Item -LiteralPath (Join-Path $proposalPath $archiveName) -Destination (Join-Path $attemptPath $archiveName)
}
foreach ($archiveName in @('read_checkpoint_inventory.py', 'symbolic_trace.py', 'read_symbolic_inventory.py', 'qualify_adapter.py', 'SHA256.json')) {
    Copy-Item -LiteralPath (Join-Path $proposalPath ('before\' + $archiveName)) -Destination (Join-Path $attemptPath ('before\' + $archiveName))
}
git diff --no-index -- (Join-Path $proposalPath 'before\read_symbolic_inventory.py') (Join-Path $proposalPath 'read_symbolic_inventory.py') | Set-Content -LiteralPath (Join-Path $attemptPath 'source-composition.diff') -Encoding UTF8
if ($LASTEXITCODE -gt 1) { throw 'Source diff failed' }
git diff --no-index -- (Join-Path $proposalPath 'before\qualify_adapter.py') (Join-Path $proposalPath 'qualify_cycle.py') | Set-Content -LiteralPath (Join-Path $attemptPath 'pre-run-setup.diff') -Encoding UTF8
if ($LASTEXITCODE -gt 1) { throw 'Setup diff failed' }
$sourceBefore = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'read_symbolic_inventory.py') -Algorithm SHA256).Hash.ToLowerInvariant()
$harnessBefore = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'qualify_cycle.py') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceBefore -ne '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd') { throw 'Adapter differs from reviewed source' }
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$interpreterPath = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe'
$startedUtc = [DateTime]::UtcNow.ToString('o')
& $interpreterPath -I -S -B (Join-Path $attemptPath 'qualify_cycle.py') 'cycle-diagnostic-preflight01' 1> (Join-Path $attemptPath 'stdout.json') 2> (Join-Path $attemptPath 'stderr.log')
$qualificationExit = $LASTEXITCODE
[ordered]@{
    label = 'cycle-diagnostic-preflight01'
    started_utc = $startedUtc
    finished_utc = [DateTime]::UtcNow.ToString('o')
    actual_qualification_exit = $qualificationExit
    interpreter = $interpreterPath
    arguments = @('-I', '-S', '-B', 'qualify_cycle.py', 'cycle-diagnostic-preflight01')
    forbidden_live_binding_set_before_startup = $true
    forbidden_live_binding = $env:IG_FORBIDDEN_LIVE
    source_sha256_before = $sourceBefore
    source_sha256_after = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'read_symbolic_inventory.py') -Algorithm SHA256).Hash.ToLowerInvariant()
    harness_sha256_before = $harnessBefore
    harness_sha256_after = (Get-FileHash -LiteralPath (Join-Path $attemptPath 'qualify_cycle.py') -Algorithm SHA256).Hash.ToLowerInvariant()
    scope = 'In-memory synthetic ZIP/pickle bytes and inert receipt/file fixtures only'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $attemptPath 'launch-receipt.json') -Encoding UTF8
Get-Content -Raw -LiteralPath (Join-Path $attemptPath 'stdout.json')
Get-Content -Raw -LiteralPath (Join-Path $attemptPath 'stderr.log')
Write-Output ('ACTUAL_QUALIFICATION_EXIT=' + $qualificationExit)
exit $qualificationExit


