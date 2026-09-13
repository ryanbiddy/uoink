$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proposal01'
$taskRun=Join-Path $taskProposal 'identity-diagnostic01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh diagnostic label required'}
$taskPrevious=Join-Path $taskProposal 'resolver-preflight01'
$taskFiles=@(
    @('diagnose_identity.py',(Join-Path $taskProposal 'diagnose_identity.py')),
    @('run_identity_diagnostic01.ps1',(Join-Path $taskProposal 'run_identity_diagnostic01.ps1')),
    @('IDENTITY-DIAGNOSTIC01-BRIEF.md',(Join-Path $taskProposal 'IDENTITY-DIAGNOSTIC01-BRIEF.md')),
    @('run01-plan.json',(Join-Path $taskPrevious 'plan.json')),
    @('run01-exit.json',(Join-Path $taskPrevious 'exit.json')),
    @('run01-stdout.json',(Join-Path $taskPrevious 'stdout.json'))
)
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
$taskRecords=@()
foreach($taskPair in $taskFiles){
    $taskHash=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskCopy=Join-Path $taskRun $taskPair[0]
    Copy-Item -LiteralPath $taskPair[1] -Destination $taskCopy -ErrorAction Stop
    if((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash){throw 'Input copy mismatch'}
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskHash}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='identity-diagnostic01';inputs=$taskRecords;arguments=@('-I','-S','-B','diagnose_identity.py');startup_binding_set=$true;fixed_retained_generated_files=40;no_fixture_writes=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& (Join-Path $taskBase '_scratch\ig-native\Scripts\python.exe') -I -S -B (Join-Path $taskRun 'diagnose_identity.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit=$LASTEXITCODE
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}
    if((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}
}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if(-not $taskUnchanged){throw 'Diagnostic input changed'}
exit $taskExit
