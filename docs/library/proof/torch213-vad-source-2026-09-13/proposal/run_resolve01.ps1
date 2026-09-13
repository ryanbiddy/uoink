$ErrorActionPreference = 'Stop'
$taskProposal = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\torch213-vad-source-proposal01'
$taskSource = Join-Path $taskProposal 'collect_torch_text.py'
$taskExpected = '6971aa91d430f0b43f3a3215d2dfe8a0c467b234ead827d311b1323b348fdc93'
$taskLaunch = Join-Path $taskProposal 'resolve01-launch'
$taskResult = Join-Path $taskProposal 'retrievals\resolve01'
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reviewed collector hash mismatch' }
if ((Test-Path -LiteralPath $taskLaunch) -or (Test-Path -LiteralPath $taskResult)) { throw 'Fresh resolve01 and launch labels required' }
New-Item -ItemType Directory -Path $taskLaunch -ErrorAction Stop | Out-Null
$taskNames = @('collect_torch_text.py','run_resolve01.ps1','RESOLVE01-PROTOCOL.md','BRIEF.md','PLAN.md','FINAL-REPORT.md','CASE-MEMBERSHIP.json')
$taskRecords = @()
foreach ($taskName in $taskNames) {
    $taskOriginal = Join-Path $taskProposal $taskName
    $taskCopy = Join-Path $taskLaunch $taskName
    $taskHash = (Get-FileHash -LiteralPath $taskOriginal -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $taskOriginal -Destination $taskCopy -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash) { throw 'Launch copy mismatch' }
    $taskRecords += [ordered]@{name=$taskName;source=$taskOriginal;sha256=$taskHash}
}
$taskEnvironmentOverrides = @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','SSLKEYLOGFILE','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','GIT_SSL_CAINFO','GIT_SSL_CAPATH','NODE_EXTRA_CA_CERTS','PYTHONHTTPSVERIFY','GH_TOKEN','GITHUB_TOKEN')
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' -or $_.Name -match '_TOKEN$' -or $_.Name.ToUpperInvariant() -in $taskEnvironmentOverrides } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$taskArguments = @('-I','-S','-B',$taskSource,'--mode','resolve','--label','resolve01','--admission','reviewed-torch213-vad-public-text-only')
[ordered]@{label='resolve01';started_utc=[DateTime]::UtcNow.ToString('o');source_sha256=$taskExpected;inputs=$taskRecords;startup_binding_set=$true;environment_scrub='provider credentials, proxies, certificate overrides and SSL key log; no values retained';arguments=$taskArguments;scope='official GitHub tag/commit API text only; at most four requests';source_stage_authorized=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskLaunch 'plan.json') -Encoding utf8
& 'C:\Python314\python.exe' @taskArguments 1> (Join-Path $taskLaunch 'stdout.json') 2> (Join-Path $taskLaunch 'stderr.log')
$taskExit = $LASTEXITCODE
$taskUnchanged = $true
foreach ($taskRecord in $taskRecords) {
    if ((Get-FileHash -LiteralPath (Join-Path $taskLaunch $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { $taskUnchanged = $false }
    if ((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { $taskUnchanged = $false }
}
[ordered]@{finished_utc=[DateTime]::UtcNow.ToString('o');native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true;source_stage_authorized=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLaunch 'exit.json') -Encoding utf8
if (-not $taskUnchanged) { throw 'Collector or launch input changed' }
exit $taskExit
