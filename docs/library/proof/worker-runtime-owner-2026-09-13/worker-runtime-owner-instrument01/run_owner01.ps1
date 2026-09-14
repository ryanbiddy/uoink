$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-instrument01'
$taskRun=Join-Path $taskProposal 'runs\rto01'
$taskAdmissionPath=Join-Path $taskProposal 'ROOT-ADMISSION.json'
$taskAdmissionHashBefore=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHashBefore){throw 'Admission changed during read'}
if($taskAdmission.root_reviewed -isnot [bool] -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.scope -cne 'runtime-owner-generated-11-only' -or $taskAdmission.label -cne 'rto01'){throw 'Exact root admission required'}
if(Test-Path -LiteralPath $taskRun){throw 'Fresh qualification label required'}
$taskExpected=@{
    'plain_state_reader.py'='3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c'
    'state_bridge.py'='b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2'
    'owned_cpu_tensor_port.py'='ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964'
    'model_binding_registry.py'='48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb'
    'owned_factory_port.py'='2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4'
    'owned_guard.py'='7672f614d81cf0be5e7bd408f8f856af328fe34e6ca7ee707c9d0db838e56d1f'
    'fake_torch_support.py'='5e1381eac70634292945422dfaf70786bb5fb96cbab7ea14a3fcc08fa29a185b'
    'fixed_schema_helpers.py'='d61e9a48ecfa906862fedb5b91415f1d2a0b71adc27d3e43ef245842c9e5b188'
    'worker_runtime_owner.py'='5647023ed03c5acfd8b1aa981a56171dd92228ccc0972f12546bb0b3d411ce87'
    'generated_factory_fixture.py'='1c60507a82c238116b630f146c44e7a81fdc57eb74f05841489c3128f150eb6f'
    'generated_unit_cases.py'='58ce1ba84b4baa457c3973cea5745ad3be94caa4ce627da732d67e9c8e148979'
    'qualify_owner.py'='e08653d576dd3ca8367efde9e9438f485de5835f3831e0f7a1f8571fefa6acc1'
    'EXPECTED-CASES.json'='954ca4783d70c2dc654e19a110aee6b7c453cd1e6f00098c46bd1b84a4738ba3'
}
$taskSourcePaths=@{
    'plain_state_reader.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\plain_state_reader.py'
    'state_bridge.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\state_bridge.py'
    'owned_cpu_tensor_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\owned_cpu_tensor_port.py'
    'model_binding_registry.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\model_binding_registry.py'
    'owned_factory_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\owned_factory_port.py'
    'owned_guard.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\owned_guard.py'
    'fake_torch_support.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\fake_torch_support.py'
    'fixed_schema_helpers.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\fixed_schema_helpers.py'
    'worker_runtime_owner.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\worker_runtime_owner.py'
    'generated_factory_fixture.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\generated_factory_fixture.py'
    'generated_unit_cases.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-proposal02\generated_unit_cases.py'
    'qualify_owner.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-instrument01\qualify_owner.py'
    'EXPECTED-CASES.json'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\worker-runtime-owner-instrument01\EXPECTED-CASES.json'
}
$taskInputNames=@('plain_state_reader.py','state_bridge.py','owned_cpu_tensor_port.py','model_binding_registry.py','owned_factory_port.py','owned_guard.py','fake_torch_support.py','fixed_schema_helpers.py','worker_runtime_owner.py','generated_factory_fixture.py','generated_unit_cases.py','qualify_owner.py','EXPECTED-CASES.json','SOURCE-INPUTS.json','run_owner01.ps1')
$taskRecords=@()
foreach($taskName in $taskInputNames){
    $taskSource=Join-Path $taskProposal $taskName
    if($taskSourcePaths.ContainsKey($taskName)){$taskSource=$taskSourcePaths[$taskName]}
    $taskHash=(Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskExpected.ContainsKey($taskName) -and $taskExpected[$taskName] -cne $taskHash){throw 'Executable source pin mismatch'}
    if($taskAdmission.input_sha256.$taskName -cne $taskHash){throw 'Root admission input mismatch'}
    $taskRecords += [ordered]@{name=$taskName;source=$taskSource;sha256=$taskHash}
}
$taskExpectedCases=Get-Content -LiteralPath (Join-Path $taskProposal 'EXPECTED-CASES.json') -Raw | ConvertFrom-Json
if($taskExpectedCases.schema -cne 'uoink.runtime-owner-expected-cases.v1' -or $taskExpectedCases.count -ne 11 -or @($taskExpectedCases.ordered_cases).Count -ne 11){throw 'Expected case input refused'}
if(@($taskAdmission.expected_cases).Count -ne 11){throw 'Admission case count refused'}
for($taskIndex=0;$taskIndex -lt 11;$taskIndex++){
    if($taskAdmission.expected_cases[$taskIndex] -cne $taskExpectedCases.ordered_cases[$taskIndex]){throw 'Admission case sequence mismatch'}
}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskRecord in $taskRecords){
    Copy-Item -LiteralPath $taskRecord.source -Destination (Join-Path $taskRun $taskRecord.name) -ErrorAction Stop
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRecord.sha256){throw 'Input copy mismatch'}
}
Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop
if((Get-FileHash -LiteralPath (Join-Path $taskRun 'ROOT-ADMISSION.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHashBefore){throw 'Admission copy mismatch'}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:PYANNOTE_METRICS_ENABLED='0'
$taskPython='C:\Python314\python.exe'
$taskStdout=Join-Path $taskRun 'stdout.json'
$taskStderr=Join-Path $taskRun 'stderr.log'
[ordered]@{label='rto01';inputs=$taskRecords;interpreter=$taskPython;arguments=@('-I','-S','-B','qualify_owner.py');scope='11 generated fake factory and owner cases only';no_native_or_model_activity=$true;planned_cases=$taskExpectedCases.ordered_cases;startup_binding_set=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
# BEGIN EXACT NATIVE RECEIPT BLOCK
$PSNativeCommandUseErrorActionPreference=$false
$global:LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'qualify_owner.py') 1> $taskStdout 2> $taskStderr
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
$taskAdmissionSourceAfter=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmissionCopyAfter=(Get-FileHash -LiteralPath (Join-Path $taskRun 'ROOT-ADMISSION.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if($taskAdmissionSourceAfter -cne $taskAdmissionHashBefore -or $taskAdmissionCopyAfter -cne $taskAdmissionHashBefore){$taskUnchanged=$false}
$taskAfter += [ordered]@{name='ROOT-ADMISSION.json';before_sha256=$taskAdmissionHashBefore;copy_after_sha256=$taskAdmissionCopyAfter;source_after_sha256=$taskAdmissionSourceAfter}
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
    $taskMembership=(@($taskResult.cases).Count -eq 11 -and @($taskResult.expected_cases).Count -eq 11)
    if($taskMembership){
        for($taskIndex=0;$taskIndex -lt 11;$taskIndex++){
            if($taskResult.cases[$taskIndex].name -cne $taskExpectedCases.ordered_cases[$taskIndex] -or $taskResult.expected_cases[$taskIndex] -cne $taskExpectedCases.ordered_cases[$taskIndex]){$taskMembership=$false}
        }
    }
    $taskCountExit=1
    if($taskFail -eq 0 -and $taskResult.guard_valid -ceq $true){$taskCountExit=0}
    $taskReceiptValid=(
        $taskResult.schema -ceq 'uoink.runtime-owner-synthetic.v1' -and $taskMembership -and
        $taskPass+$taskFail -eq 11 -and $taskResult.count -eq 11 -and $taskResult.skipped -eq 0 -and
        $taskResult.passed -eq $taskPass -and $taskResult.failed -eq $taskFail -and
        $taskResult.elapsed_seconds -is [ValueType] -and $taskResult.elapsed_seconds -ge 0 -and $taskResult.elapsed_seconds -lt 3600 -and
        $taskResult.native_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskCountExit -and
        $taskResult.guard_valid -ceq $true -and $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 12 -and
        $taskResult.content_reads_closed -ceq $true -and $taskResult.captures_installed -ceq $true -and $taskResult.capture_valid -ceq $true -and
        $taskResult.baseline_winreg_identity_unchanged -ceq $true -and $taskResult.registry_namespace_unchanged -ceq $true -and
        $taskResult.registry_traps_installed -ceq $true -and $taskResult.registry_trap_count -ge 1 -and $taskResult.registry_trap_count -le 64 -and
        @($taskResult.registry_trap_names).Count -eq $taskResult.registry_trap_count -and @($taskResult.registry_denials).Count -eq 0 -and
        @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.heavy_roots_loaded).Count -eq 0 -and
        $taskResult.methods_unchanged -ceq $true -and $taskResult.closed_entries_unchanged -ceq $true -and
        $taskResult.owner_binding_valid -ceq $true -and
        $taskResult.stdout_capture -ceq '' -and $taskResult.stderr_capture -ceq ''
    )
    foreach($taskName in $taskExpected.Keys){if($taskResult.input_sha256.$taskName -cne $taskExpected[$taskName]){$taskReceiptValid=$false}}
}catch{$taskReceiptError=$_.Exception.GetType().Name}
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskReceiptValid -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{native_exit=$taskNativeExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskReceiptValid;receipt_parse_error_type=$taskReceiptError;stdout_bytes=$taskStdoutBytes;stderr_bytes=$taskStderrBytes;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
