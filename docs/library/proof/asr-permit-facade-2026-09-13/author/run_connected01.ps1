$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-permit-facade-qualification02'
$taskRun=Join-Path $taskProposal 'connected01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh adapter qualification label required'}
$taskAdmission=Join-Path $taskProposal 'ROOT-ADMISSION.md'
if(-not (Test-Path -LiteralPath $taskAdmission -PathType Leaf)){throw 'Root exact-source admission record required before execution'}
$taskExpected=@{
    'asr_loading_adapter.py'='2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c'
    'connection_cases.py'='0ef40eab642099f83ce35d2e70a0d0521d57ad2f7e8d467e940cb2600365630a'
    'snapshot_lifecycle.py'='a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd'
    'trusted_asr_resolver.py'='16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'
    'qualify_adapter.py'='3c631f7f1b1aa67f08d9b563df641db9b7a52dc1dbdb9f221f7f75080797571a'
}
$taskExpectedCases=@(
    'exact_lease_permit_and_usage_reach_owned_startup',
    'retained_facade_refuses_after_context_close',
    'lazy_segments_require_live_owned_lease',
    'foreign_factory_refused_before_native_reservation',
    'binding_or_start_failure_preserves_original_and_quarantine',
    'unconfirmed_close_keeps_snapshot_quarantined'
)
$taskFiles=@(
    @('asr_loading_adapter.py',(Join-Path $taskProposal 'asr_loading_adapter.py')),
    @('connection_cases.py',(Join-Path $taskProposal 'connection_cases.py')),
    @('snapshot_lifecycle.py',(Join-Path $taskProposal 'snapshot_lifecycle.py')),
    @('trusted_asr_resolver.py',(Join-Path $taskProposal 'trusted_asr_resolver.py')),
    @('qualify_adapter.py',(Join-Path $taskProposal 'qualify_adapter.py')),
    @('BRIEF.md',(Join-Path $taskProposal 'BRIEF.md')),
    @('PROTOCOL.md',(Join-Path $taskProposal 'PROTOCOL.md')),
    @('EXPECTED-CASES.json',(Join-Path $taskProposal 'EXPECTED-CASES.json')),
    @('SOURCE-BINDINGS.json',(Join-Path $taskProposal 'SOURCE-BINDINGS.json')),
    @('run_connected01.ps1',(Join-Path $taskProposal 'run_connected01.ps1')),
    @('ROOT-ADMISSION.md',(Join-Path $taskProposal 'ROOT-ADMISSION.md'))
)
$taskRecords=@()
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskPair in $taskFiles){
    $taskHash=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskExpected.ContainsKey($taskPair[0]) -and $taskHash -ne $taskExpected[$taskPair[0]]){throw 'Reviewed executable input hash mismatch'}
    $taskCopy=Join-Path $taskRun $taskPair[0]
    Copy-Item -LiteralPath $taskPair[1] -Destination $taskCopy -ErrorAction Stop
    if((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash){throw 'Input copy hash mismatch'}
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskHash}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:HF_DATASETS_OFFLINE='1'
$env:PYANNOTE_METRICS_ENABLED='0'
$taskPython='C:\Python314\python.exe'
$taskStdout=Join-Path $taskRun 'stdout.json'
$taskStderr=Join-Path $taskRun 'stderr.log'
[ordered]@{label='connected01';inputs=$taskRecords;interpreter=$taskPython;startup_binding_set=$true;torch_backend_autoload_disabled=$true;arguments=@('-I','-S','-B','qualify_adapter.py');fake_ports_only=$true;actual_asset_fixtures=$false;real_approval_available=$false;planned_case_count=6;expected_case_ids=$taskExpectedCases} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
# BEGIN EXACT NATIVE RECEIPT BLOCK
# Override any inherited native-error promotion at this invocation boundary.
$PSNativeCommandUseErrorActionPreference=$false
$global:LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'qualify_adapter.py') 1> $taskStdout 2> $taskStderr
$taskNativeExit=$global:LASTEXITCODE
# Persist the completed-child outcome before any input or result postcheck.
$taskNativeReceipt=[ordered]@{schema='uoink.native-exit.v1';child_returned=$true;native_exit=$taskNativeExit}
$taskNativeBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskNativeReceipt | ConvertTo-Json -Compress))
$taskNativeStream=[IO.File]::Open((Join-Path $taskRun 'native-exit.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{
    $taskNativeStream.Write($taskNativeBytes,0,$taskNativeBytes.Length)
    $taskNativeStream.Flush($true)
}finally{$taskNativeStream.Dispose()}
if($taskNativeExit -isnot [int]){throw 'Returned native exit was not captured as an integer'}
# END EXACT NATIVE RECEIPT BLOCK
$taskAfter=@()
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    $taskCopyHash=(Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskSourceHash=(Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskCopyHash -ne $taskRecord.sha256 -or $taskSourceHash -ne $taskRecord.sha256){$taskUnchanged=$false}
    $taskAfter += [ordered]@{name=$taskRecord.name;before_sha256=$taskRecord.sha256;copy_after_sha256=$taskCopyHash;source_after_sha256=$taskSourceHash}
}
$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8
$taskReceiptValid=$false
$taskReceiptError=$null
try{
    if((Get-Item -LiteralPath $taskStdout).Length -gt 65536){throw 'Bounded result text exceeded'}
    $taskResult=Get-Content -LiteralPath $taskStdout -Raw | ConvertFrom-Json
    $taskPass=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $true }).Count
    $taskFail=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $false }).Count
    $taskUnique=@($taskResult.cases.name | Sort-Object -Unique).Count
    $taskMembership=(@($taskResult.cases.name).Count -eq $taskExpectedCases.Count)
    if($taskMembership){for($taskI=0;$taskI -lt $taskExpectedCases.Count;$taskI++){if($taskResult.cases[$taskI].name -cne $taskExpectedCases[$taskI]){$taskMembership=$false}}}
    $taskCountExit=1
    if($taskFail -eq 0){$taskCountExit=0}
    $taskReceiptValid=(
        $taskMembership -and $taskResult.skipped -eq 0 -and
        $taskResult.content_reads_closed -ceq $true -and $taskResult.adapter_release_restored -ceq $true -and
        $taskResult.ordered_membership_matches -ceq $true -and
        $taskResult.offline_flags.HF_HUB_OFFLINE -ceq '1' -and $taskResult.offline_flags.TRANSFORMERS_OFFLINE -ceq '1' -and
        $taskResult.offline_flags.HF_DATASETS_OFFLINE -ceq '1' -and $taskResult.offline_flags.PYANNOTE_METRICS_ENABLED -ceq '0' -and
        $taskResult.schema -ceq 'uoink.inert-asr-adapter-qualification.v1' -and
        @($taskResult.cases).Count -eq 6 -and $taskUnique -eq 6 -and
        $taskPass+$taskFail -eq 6 -and $taskResult.passed -eq $taskPass -and $taskResult.failed -eq $taskFail -and
        $taskResult.qualification_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskCountExit -and
        $taskResult.startup_binding_asserted -ceq $true -and $taskResult.torch_backend_autoload_disabled_before_startup -ceq $true -and
        $taskResult.real_resolver_approval_unchanged_none -ceq $true -and $taskResult.real_resolver_functions_unchanged -ceq $true -and
        $taskResult.adapter_globals_restored -ceq $true -and $taskResult.guard_valid -ceq $true -and
        $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 12 -and
        @($taskResult.metadata_trap_mismatches).Count -eq 0 -and
        @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.heavy_roots_loaded).Count -eq 0
    )
    foreach($taskName in $taskExpected.Keys){
        if($taskResult.input_sha256.$taskName -cne $taskExpected[$taskName]){$taskReceiptValid=$false}
    }
}catch{$taskReceiptError=$_.Exception.GetType().Name}
$taskStderrBytes=(Get-Item -LiteralPath $taskStderr).Length
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskReceiptValid -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{native_exit=$taskNativeExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskReceiptValid;receipt_parse_error_type=$taskReceiptError;stderr_bytes=$taskStderrBytes;startup_binding_set=$true;torch_backend_autoload_disabled=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
