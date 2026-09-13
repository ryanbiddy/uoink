$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskDir = Join-Path $taskRoot '_scratch\vad-selected-metadata-map01'
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$taskScript = Join-Path $taskDir 'map_receipt.py'
$taskHashBefore = (Get-FileHash -LiteralPath $taskScript -Algorithm SHA256).Hash.ToLowerInvariant()
& (Join-Path $taskRoot '_scratch\ig-native\Scripts\python.exe') -I -S -B $taskScript 1> (Join-Path $taskDir 'map01-stdout.log') 2> (Join-Path $taskDir 'map01-stderr.log')
$taskExit = $LASTEXITCODE
$taskHashAfter = (Get-FileHash -LiteralPath $taskScript -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{ reader_exit=$taskExit; source_sha256_before=$taskHashBefore; source_sha256_after=$taskHashAfter; source_unchanged=($taskHashBefore -eq $taskHashAfter); startup_binding_set=$true } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDir 'map01-launch.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskDir 'map01-stdout.log')
Get-Content -LiteralPath (Join-Path $taskDir 'map01-stderr.log')
exit $taskExit
