$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-native-exit-scope-repair01\candidate'
$taskRun=Join-Path $taskProposal 'adapter-preflight03'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh adapter qualification label required'}
$taskAdmission=Join-Path $taskProposal 'ROOT-ADMISSION.md'
if(-not (Test-Path -LiteralPath $taskAdmission -PathType Leaf)){throw 'Root exact-source admission record required before execution'}
$taskExpected=@{
    'asr_loading_adapter.py'='03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900'
    'trusted_asr_resolver.py'='16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'
    'qualify_adapter.py'='68eaeeaaa3d32d6c97102aae17e4f7490702a495b9e2cb72adf38aab438ff545'
}
$taskFiles=@(
    @('asr_loading_adapter.py',(Join-Path $taskProposal 'asr_loading_adapter.py')),
    @('trusted_asr_resolver.py',(Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proposal01\trusted_asr_resolver.py')),
    @('qualify_adapter.py',(Join-Path $taskProposal 'qualify_adapter.py')),
    @('BRIEF.md',(Join-Path $taskProposal 'BRIEF.md')),
    @('PORT-CONTRACTS.md',(Join-Path $taskProposal 'PORT-CONTRACTS.md')),
    @('TEST-PLAN.md',(Join-Path $taskProposal 'TEST-PLAN.md')),
    @('REVIEW.md',(Join-Path $taskProposal 'REVIEW.md')),
    @('CALL-SITE-SPLICES.md',(Join-Path $taskProposal 'CALL-SITE-SPLICES.md')),
    @('SOURCE-BINDINGS.json',(Join-Path $taskProposal 'SOURCE-BINDINGS.json')),
    @('WAVEFORM-STARTUP-CORRECTION.md',(Join-Path $taskProposal 'WAVEFORM-STARTUP-CORRECTION.md')),
    @('HARNESS-PREPARATION.md',(Join-Path $taskProposal 'HARNESS-PREPARATION.md')),
    @('QUALIFICATION03-PROTOCOL.md',(Join-Path $taskProposal 'QUALIFICATION03-PROTOCOL.md')),
    @('adapter-addition.patch.txt',(Join-Path $taskProposal 'adapter-addition.patch.txt')),
    @('run_preflight03.ps1',(Join-Path $taskProposal 'run_preflight03.ps1')),
    @('ROOT-ADMISSION.md',$taskAdmission)
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
$taskPython=Join-Path $taskBase '_scratch\ig-native\Scripts\python.exe'
$taskStdout=Join-Path $taskRun 'stdout.json'
$taskStderr=Join-Path $taskRun 'stderr.log'
[ordered]@{label='adapter-preflight03';inputs=$taskRecords;interpreter=$taskPython;startup_binding_set=$true;torch_backend_autoload_disabled=$true;arguments=@('-I','-S','-B','qualify_adapter.py');fake_ports_only=$true;actual_asset_fixtures=$false;real_approval_available=$false;planned_case_count=58} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
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
    $taskResult=Get-Content -LiteralPath $taskStdout -Raw | ConvertFrom-Json
    $taskPass=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $true }).Count
    $taskFail=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $false }).Count
    $taskUnique=@($taskResult.cases.name | Sort-Object -Unique).Count
    $taskCountExit=1
    if($taskFail -eq 0){$taskCountExit=0}
    $taskReceiptValid=(
        $taskResult.schema -ceq 'uoink.inert-asr-adapter-qualification.v1' -and
        @($taskResult.cases).Count -eq 58 -and $taskUnique -eq 58 -and
        $taskPass+$taskFail -eq 58 -and $taskResult.passed -eq $taskPass -and $taskResult.failed -eq $taskFail -and
        $taskResult.qualification_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskCountExit -and
        $taskResult.startup_binding_asserted -ceq $true -and $taskResult.torch_backend_autoload_disabled_before_startup -ceq $true -and
        $taskResult.real_resolver_approval_unchanged_none -ceq $true -and $taskResult.real_resolver_functions_unchanged -ceq $true -and
        $taskResult.adapter_globals_restored -ceq $true -and $taskResult.guard_valid -ceq $true -and
        $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 11 -and
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
