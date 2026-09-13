$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proposal01'
$taskRun=Join-Path $taskBase '_scratch\astra-asr-resolver-synthetic01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh qualification label required'}
$taskFiles=@(
    @('trusted_asr_resolver.py',(Join-Path $taskProposal 'trusted_asr_resolver.py')),
    @('qualify_resolver.py',(Join-Path $taskProposal 'qualify_resolver.py')),
    @('identity_regressions.py',(Join-Path $taskProposal 'identity_regressions.py')),
    @('original73-harness.py',(Join-Path $taskProposal 'resolver-preflight01\qualify_resolver.py')),
    @('six-model-plan.json',(Join-Path $taskBase '_scratch\runtime-migration-owner-protocol01\inputs\six-model-plan.json')),
    @('BRIEF.md',(Join-Path $taskProposal 'BRIEF.md')),
    @('IDENTITY-REPAIR02-BRIEF.md',(Join-Path $taskProposal 'IDENTITY-REPAIR02-BRIEF.md')),
    @('QUALIFICATION02-PROTOCOL.md',(Join-Path $taskProposal 'QUALIFICATION02-PROTOCOL.md')),
    @('identity-source-repair.patch.txt',(Join-Path $taskProposal 'identity-source-repair.patch.txt')),
    @('identity-harness-setup.patch.txt',(Join-Path $taskProposal 'identity-harness-setup.patch.txt')),
    @('run_preflight02.ps1',(Join-Path $taskProposal 'run_preflight02.ps1'))
)
$taskRecords=@()
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskPair in $taskFiles){
    $taskHash=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskCopy=Join-Path $taskRun $taskPair[0]
    Copy-Item -LiteralPath $taskPair[1] -Destination $taskCopy -ErrorAction Stop
    if((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash){throw 'Input copy hash mismatch'}
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskHash}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='resolver-preflight02';inputs=$taskRecords;startup_binding_set=$true;arguments=@('-I','-S','-B','qualify_resolver.py');generated_placeholder_files_only=$true;real_approval_available=$false;original_case_count=73;additional_identity_cases=14} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& (Join-Path $taskBase '_scratch\ig-native\Scripts\python.exe') -I -S -B (Join-Path $taskRun 'qualify_resolver.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit=$LASTEXITCODE
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}
    if((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}
}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if(-not $taskUnchanged){throw 'Qualification input changed'}
exit $taskExit
