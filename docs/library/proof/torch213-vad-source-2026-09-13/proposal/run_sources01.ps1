$ErrorActionPreference = 'Stop'
$taskProposal = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\torch213-vad-source-proposal01'
$taskSource = Join-Path $taskProposal 'collect_torch_text.py'
$taskExpected = '6971aa91d430f0b43f3a3215d2dfe8a0c467b234ead827d311b1323b348fdc93'
$taskCommit = 'cf30153c4c131c8164ee7798e5022d810682e2cb'
$taskResolve = Join-Path $taskProposal 'retrievals\resolve01\receipt.json'
$taskResolveHash = 'd10ebf095e330aae8ad818644ddd5638228c2a9d1db57021c50967b2bd52daa4'
$taskUrls = Join-Path $taskProposal 'SOURCES01-URLS.json'
$taskUrlsHash = '513e3f2f8f90e24d11b9b6ddd6cd83b88877de93ecd399f29e02805dfbf43b44'
$taskLaunch = Join-Path $taskProposal 'sources01-launch'
$taskResult = Join-Path $taskProposal 'retrievals\sources01'
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reviewed collector hash mismatch' }
if ((Get-FileHash -LiteralPath $taskResolve -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskResolveHash) { throw 'Reviewed resolve receipt mismatch' }
if ((Get-FileHash -LiteralPath $taskUrls -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskUrlsHash) { throw 'Reviewed exact URL plan mismatch' }
$taskBinding = Get-Content -LiteralPath $taskResolve -Raw | ConvertFrom-Json
if ($taskBinding.binding.commit -ne $taskCommit -or $taskBinding.binding.initial_ref_object -ne $taskCommit -or $taskBinding.binding.tag -ne 'v2.13.0' -or $taskBinding.binding.tree_declaration -ne '7cda5eae52ace99ca4daa7e623920cc93782cc6c' -or $taskBinding.mode -ne 'resolve' -or $taskBinding.intended_exit -ne 0 -or $taskBinding.status -ne 'public_text_collected_pending_source_review') { throw 'Reviewed binding fields mismatch' }
if ((Test-Path -LiteralPath $taskLaunch) -or (Test-Path -LiteralPath $taskResult)) { throw 'Fresh sources01 and launch labels required' }
New-Item -ItemType Directory -Path $taskLaunch -ErrorAction Stop | Out-Null
$taskFiles = @(
    @('collect_torch_text.py',$taskSource),
    @('run_sources01.ps1',(Join-Path $taskProposal 'run_sources01.ps1')),
    @('SOURCES01-PROTOCOL.md',(Join-Path $taskProposal 'SOURCES01-PROTOCOL.md')),
    @('SOURCES01-URLS.json',$taskUrls),
    @('resolved-binding.json',$taskResolve),
    @('ROOT-RESOLVE-ADMISSION.md',(Join-Path $taskProposal 'resolve01-launch\ROOT-ADMISSION.md')),
    @('BRIEF.md',(Join-Path $taskProposal 'BRIEF.md')),
    @('PLAN.md',(Join-Path $taskProposal 'PLAN.md')),
    @('FINAL-REPORT.md',(Join-Path $taskProposal 'FINAL-REPORT.md')),
    @('CASE-MEMBERSHIP.json',(Join-Path $taskProposal 'CASE-MEMBERSHIP.json'))
)
$taskRecords = @()
foreach ($taskPair in $taskFiles) {
    $taskCopy = Join-Path $taskLaunch $taskPair[0]
    $taskHash = (Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $taskPair[1] -Destination $taskCopy -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash) { throw 'Launch copy mismatch' }
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskHash}
}
$taskEnvironmentOverrides = @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','SSLKEYLOGFILE','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','GIT_SSL_CAINFO','GIT_SSL_CAPATH','NODE_EXTRA_CA_CERTS','PYTHONHTTPSVERIFY','GH_TOKEN','GITHUB_TOKEN')
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' -or $_.Name -match '_TOKEN$' -or $_.Name.ToUpperInvariant() -in $taskEnvironmentOverrides } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$taskArguments = @('-I','-S','-B',$taskSource,'--mode','sources','--label','sources01','--expected-commit',$taskCommit,'--expected-ref-object',$taskCommit,'--admission','reviewed-torch213-vad-public-text-only')
[ordered]@{label='sources01';started_utc=[DateTime]::UtcNow.ToString('o');source_sha256=$taskExpected;inputs=$taskRecords;startup_binding_set=$true;environment_scrub='provider credentials, proxies, certificate overrides and SSL key log; no values retained';arguments=$taskArguments;scope='repeat exact official binding then nineteen immutable-commit source texts';source_execution_authorized=$false;model_or_runtime_authorized=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskLaunch 'plan.json') -Encoding utf8
& 'C:\Python314\python.exe' @taskArguments 1> (Join-Path $taskLaunch 'stdout.json') 2> (Join-Path $taskLaunch 'stderr.log')
$taskExit = $LASTEXITCODE
$taskUnchanged = $true
foreach ($taskRecord in $taskRecords) {
    if ((Get-FileHash -LiteralPath (Join-Path $taskLaunch $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { $taskUnchanged = $false }
    if ((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { $taskUnchanged = $false }
}
[ordered]@{finished_utc=[DateTime]::UtcNow.ToString('o');native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true;source_execution_authorized=$false;model_or_runtime_authorized=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLaunch 'exit.json') -Encoding utf8
if (-not $taskUnchanged) { throw 'Collector or launch input changed' }
exit $taskExit
