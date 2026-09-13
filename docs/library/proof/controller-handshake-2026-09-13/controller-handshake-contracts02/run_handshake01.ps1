$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-handshake-contracts02'
$taskRun=Join-Path $taskProposal 'runs\hs01'
$taskAdmissionPath=Join-Path $taskProposal 'ROOT-ADMISSION.json'
$taskAdmissionHash=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
if($taskAdmission.root_reviewed -isnot [bool] -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.scope -cne 'controller-handshake-fake-port-8-only' -or $taskAdmission.label -cne 'hs01'){throw 'Exact root admission required'}
if(Test-Path -LiteralPath $taskRun){throw 'Fresh qualification label required'}
$taskExpected=@{
    'snapshot_lifecycle.py'='a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd'
    'owned_generation_protocol.py'='78c395da77ff5a0dd660a27a7ea47d6e52061fc016937aa7046556f1fa026507'
    'handshake_cases.py'='cd55230d2545f2247fdb058eca7d251f68bd9af107cd5d2e6c14365cd3861cfa'
    'qualify_handshake.py'='fe0f509b2081d02e3aa8a24f13732a01f43236e03202289dd9ea2a051fdaefdb'
}
$taskInputNames=@('snapshot_lifecycle.py','owned_generation_protocol.py','handshake_cases.py','qualify_handshake.py','EXPECTED-CASES.json','run_handshake01.ps1')
$taskRecords=@()
foreach($taskName in $taskInputNames){
    $taskSource=Join-Path $taskProposal $taskName
    $taskHash=(Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskExpected.ContainsKey($taskName) -and $taskExpected[$taskName] -cne $taskHash){throw 'Executable source pin mismatch'}
    if($taskAdmission.input_sha256.$taskName -cne $taskHash){throw 'Root admission input mismatch'}
    $taskRecords += [ordered]@{name=$taskName;source=$taskSource;sha256=$taskHash}
}
$taskRecords += [ordered]@{name='ROOT-ADMISSION.json';source=$taskAdmissionPath;sha256=$taskAdmissionHash}
$taskExpectedCases=Get-Content -LiteralPath (Join-Path $taskProposal 'EXPECTED-CASES.json') -Raw | ConvertFrom-Json
if($taskExpectedCases.schema -cne 'uoink.handshake-expected-cases.v1' -or $taskExpectedCases.count -ne 8 -or @($taskExpectedCases.ordered_cases).Count -ne 8){throw 'Expected case input refused'}
if(@($taskAdmission.expected_cases).Count -ne 8){throw 'Admission case count refused'}
for($taskIndex=0;$taskIndex -lt 8;$taskIndex++){
    if($taskAdmission.expected_cases[$taskIndex] -cne $taskExpectedCases.ordered_cases[$taskIndex]){throw 'Admission case sequence mismatch'}
}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskRecord in $taskRecords){
    Copy-Item -LiteralPath $taskRecord.source -Destination (Join-Path $taskRun $taskRecord.name) -ErrorAction Stop
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRecord.sha256){throw 'Input copy mismatch'}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:PYANNOTE_METRICS_ENABLED='0'
$taskPython='C:\Python314\python.exe'
$taskStdout=Join-Path $taskRun 'stdout.json'
$taskStderr=Join-Path $taskRun 'stderr.log'
[ordered]@{label='hs01';inputs=$taskRecords;interpreter=$taskPython;arguments=@('-I','-S','-B','qualify_handshake.py');scope='8 generated-memory fake API cases only';no_native_or_model_activity=$true;planned_cases=$taskExpectedCases.ordered_cases;startup_binding_set=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
# BEGIN EXACT NATIVE RECEIPT BLOCK
$PSNativeCommandUseErrorActionPreference=$false
$global:LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'qualify_handshake.py') 1> $taskStdout 2> $taskStderr
$taskNativeExit=$global:LASTEXITCODE
$taskNativeReceipt=[ordered]@{schema='uoink.native-exit.v1';child_returned=$true;native_exit=$taskNativeExit}
$taskNativeBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskNativeReceipt | ConvertTo-Json -Compress))
$taskNativeStream=[IO.File]::Open((Join-Path $taskRun 'native-exit.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$taskNativeStream.Write($taskNativeBytes,0,$taskNativeBytes.Length);$taskNativeStream.Flush($true)}finally{$taskNativeStream.Dispose()}
if($taskNativeExit -isnot [int]){throw 'Native exit was not captured as an integer'}
# END EXACT NATIVE RECEIPT BLOCK
$taskAfter=@()
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    $taskCopyHash=(Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskSourceHash=(Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskCopyHash -cne $taskRecord.sha256 -or $taskSourceHash -cne $taskRecord.sha256){$taskUnchanged=$false}
    $taskAfter += [ordered]@{name=$taskRecord.name;before_sha256=$taskRecord.sha256;copy_after_sha256=$taskCopyHash;source_after_sha256=$taskSourceHash}
}
$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8
$taskReceiptValid=$false
$taskReceiptError=$null
$taskStdoutBytes=(Get-Item -LiteralPath $taskStdout).Length
$taskStderrBytes=(Get-Item -LiteralPath $taskStderr).Length
try{
    if($taskStdoutBytes -gt 131073 -or $taskStderrBytes -gt 32768){throw 'Capture bounds exceeded'}
    $taskResult=Get-Content -LiteralPath $taskStdout -Raw | ConvertFrom-Json
    $taskPass=@($taskResult.cases | Where-Object {$_.passed -is [bool] -and $_.passed -ceq $true}).Count
    $taskFail=@($taskResult.cases | Where-Object {$_.passed -is [bool] -and $_.passed -ceq $false}).Count
    $taskMembership=(@($taskResult.cases).Count -eq 8 -and @($taskResult.expected_cases).Count -eq 8)
    if($taskMembership){
        for($taskIndex=0;$taskIndex -lt 8;$taskIndex++){
            if($taskResult.cases[$taskIndex].name -cne $taskExpectedCases.ordered_cases[$taskIndex] -or $taskResult.expected_cases[$taskIndex] -cne $taskExpectedCases.ordered_cases[$taskIndex]){$taskMembership=$false}
        }
    }
    $taskCountExit=1
    if($taskFail -eq 0 -and $taskResult.guard_valid -ceq $true){$taskCountExit=0}
    $taskReceiptValid=(
        $taskResult.schema -ceq 'uoink.controller-handshake-synthetic.v1' -and $taskMembership -and
        $taskPass+$taskFail -eq 8 -and $taskResult.count -eq 8 -and $taskResult.skipped -eq 0 -and
        $taskResult.passed -eq $taskPass -and $taskResult.failed -eq $taskFail -and
        $taskResult.elapsed_seconds -is [ValueType] -and $taskResult.elapsed_seconds -ge 0 -and $taskResult.elapsed_seconds -lt 3600 -and
        $taskResult.native_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskCountExit -and
        $taskResult.guard_valid -ceq $true -and $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 12 -and
        $taskResult.content_reads_closed -ceq $true -and $taskResult.captures_installed -ceq $true -and $taskResult.capture_valid -ceq $true -and
        $taskResult.baseline_winreg_identity_unchanged -ceq $true -and $taskResult.registry_namespace_unchanged -ceq $true -and
        $taskResult.registry_traps_installed -ceq $true -and $taskResult.registry_trap_count -ge 1 -and $taskResult.registry_trap_count -le 64 -and
        @($taskResult.registry_trap_names).Count -eq $taskResult.registry_trap_count -and @($taskResult.registry_denials).Count -eq 0 -and
        @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.heavy_roots_loaded).Count -eq 0 -and
        $taskResult.stdout_capture -ceq '' -and $taskResult.stderr_capture -ceq ''
    )
    foreach($taskName in $taskExpected.Keys){if($taskResult.input_sha256.$taskName -cne $taskExpected[$taskName]){$taskReceiptValid=$false}}
}catch{$taskReceiptError=$_.Exception.GetType().Name}
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskReceiptValid -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{native_exit=$taskNativeExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskReceiptValid;receipt_parse_error_type=$taskReceiptError;stdout_bytes=$taskStdoutBytes;stderr_bytes=$taskStderrBytes;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
