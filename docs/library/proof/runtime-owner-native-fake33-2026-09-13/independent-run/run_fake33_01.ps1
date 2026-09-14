$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01'
$taskRun=Join-Path $taskProposal 'runs\owner-native-fake01'
$taskAdmissionPath=Join-Path $taskProposal 'ROOT-ADMISSION.json'
$taskAdmissionHashBefore=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHashBefore){throw 'Admission changed during read'}
if($taskAdmission.root_reviewed -isnot [bool] -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.scope -cne 'runtime-owner-native-fake-33-only' -or $taskAdmission.label -cne 'owner-native-fake01'){throw 'Exact root admission required'}
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
    'reservation_file_port.py'='708554378ab8a8e6c4477e637c999256665cbd2855b94c6fa3c2d04a19d3a224'
    'snapshot_reservations.py'='e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98'
    'snapshot_lifecycle.py'='a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd'
    'durable_lifecycle.py'='ef1519262dc0762c96d86582e211e8c2d9dfcbf93d8a3a03b0a6fc4dba5de352'
    'win32_worker_connection.py'='60d22036d6827205be5d0657af8e4693aa534605bdfb1b501878eb2a889fe25f'
    'windows_reservation_port.py'='b93076ab07b8c0567f6608520c99f5e5523be3dd388010a5a49037a4a899f775'
    'owned_generation_protocol.py'='bd5204ef0d3fc2a459df19bc5f02fd7b6d78041e2306b4031ab888387aa362c0'
    'win32_private_pipe.py'='73a1109a55f2bc807594655c71b24a3e35eb88d7f744497df2cc328dc224cae7'
    'pinned_buffer_namespace.py'='2cc25a7a254f35d802336ef121cc860887a4301b3257588438dddec392fe0b7b'
    'inherited_readset.py'='02be8e04f4bea3030faf0882ae48ead40716c5782f95e2790e1a9897c5be76e3'
    'generated_worker_flow.py'='1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238'
    'generated_operation_flow.py'='6f09b4e6490b2078e792e49559a9dd0db95a895a778c31294a3577eeabdc98ed'
    'trusted_asr_resolver.py'='16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'
    'asr_loading_adapter.py'='635d2c22db75d12ffe6965fb656fdca47450ccbbaeb4d8cc8aaff9fcc79dd243'
    'generated_journal_setup.py'='e6a0b9aab01c1ee4f8da948bd76b420c709d10b79b094026493384a2fe89d9d6'
    'generated_writer_exclusion.py'='8173d7394f4a893c14d2979283a0c17ed273e25f196e14560590be3a0f22058b'
    'generated_worker_factory_inputs.py'='dbf5f1859fbe6f90d0f892e5a8dc7652f7336b32f51bf1dec0278f5fecfca046'
    'generated_worker_runtime_bridge.py'='11eff72f6d96b5c4248987635b5373672da706e1ac0fac53188aac7a3a253716'
    'generated_adapter_flow.py'='4d1bc0ac6e25733b13cc2d16c327be23d90c68d22b1402736ff8147b302a0e8c'
    'generated_factory_fixture.py'='1c60507a82c238116b630f146c44e7a81fdc57eb74f05841489c3128f150eb6f'
    'generated_unit_cases.py'='58ce1ba84b4baa457c3973cea5745ad3be94caa4ce627da732d67e9c8e148979'
    'generated_bootstrap_fixture.py'='6ea5e4e7cebff54380193b1ad0cc1b1cf08e4a7f34a8162d2f0f6ce73371d469'
    'connection_cases.py'='2e598f26c7edd2e60b06495a62a350411ceb0a60ed6fd3486c1a1294d04cbea6'
    'generated_native_owner_fixture.py'='a86b143a11f4abb8683f859ff7fd9f04b374aa591a6f478b724a4866fab51beb'
    'native_owner_cases.py'='2a2ec0245524532e383472e737b60a9dea125c27118b75c16ec00ade634e851d'
    'qualify_owner.py'='b1771412162632a9e9f98a0321bb5b030372546a7e9cf932318d10b34d53b02b'
    'EXPECTED-CASES.json'='2c1fadce72b41ed443fcbcd2be88758db9f1cb55e530c7a33010377c598d164e'
}
$taskSourcePaths=@{
    'plain_state_reader.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\plain_state_reader.py'
    'state_bridge.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\state_bridge.py'
    'owned_cpu_tensor_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\owned_cpu_tensor_port.py'
    'model_binding_registry.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\model_binding_registry.py'
    'owned_factory_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\owned_factory_port.py'
    'owned_guard.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\owned_guard.py'
    'fake_torch_support.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\fake_torch_support.py'
    'fixed_schema_helpers.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\fixed_schema_helpers.py'
    'worker_runtime_owner.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\worker_runtime_owner.py'
    'reservation_file_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\reservation_file_port.py'
    'snapshot_reservations.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\snapshot_reservations.py'
    'snapshot_lifecycle.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\snapshot_lifecycle.py'
    'durable_lifecycle.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\durable_lifecycle.py'
    'win32_worker_connection.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\win32_worker_connection.py'
    'windows_reservation_port.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\windows_reservation_port.py'
    'owned_generation_protocol.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\owned_generation_protocol.py'
    'win32_private_pipe.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\win32_private_pipe.py'
    'pinned_buffer_namespace.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\pinned_buffer_namespace.py'
    'inherited_readset.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\inherited_readset.py'
    'generated_worker_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_worker_flow.py'
    'generated_operation_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_operation_flow.py'
    'trusted_asr_resolver.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\trusted_asr_resolver.py'
    'asr_loading_adapter.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\asr_loading_adapter.py'
    'generated_journal_setup.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_journal_setup.py'
    'generated_writer_exclusion.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_writer_exclusion.py'
    'generated_worker_factory_inputs.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_worker_factory_inputs.py'
    'generated_worker_runtime_bridge.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_worker_runtime_bridge.py'
    'generated_adapter_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_adapter_flow.py'
    'generated_factory_fixture.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_factory_fixture.py'
    'generated_unit_cases.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_unit_cases.py'
    'generated_bootstrap_fixture.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_bootstrap_fixture.py'
    'connection_cases.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\connection_cases.py'
    'generated_native_owner_fixture.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\generated_native_owner_fixture.py'
    'native_owner_cases.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\native_owner_cases.py'
    'qualify_owner.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\qualify_owner.py'
    'EXPECTED-CASES.json'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01\EXPECTED-CASES.json'
}
$taskInputNames=@('plain_state_reader.py','state_bridge.py','owned_cpu_tensor_port.py','model_binding_registry.py','owned_factory_port.py','owned_guard.py','fake_torch_support.py','fixed_schema_helpers.py','worker_runtime_owner.py','reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py','durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py','win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py','generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_journal_setup.py','generated_writer_exclusion.py','generated_worker_factory_inputs.py','generated_worker_runtime_bridge.py','generated_adapter_flow.py','generated_factory_fixture.py','generated_unit_cases.py','generated_bootstrap_fixture.py','connection_cases.py','generated_native_owner_fixture.py','native_owner_cases.py','qualify_owner.py','EXPECTED-CASES.json','SOURCE-INPUTS.json','run_fake33_01.ps1')
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
if($taskExpectedCases.schema -cne 'uoink.runtime-owner-native-expected-cases.v1' -or $taskExpectedCases.count -ne 33 -or @($taskExpectedCases.ordered_cases).Count -ne 33){throw 'Expected case input refused'}
if(@($taskAdmission.expected_cases).Count -ne 33){throw 'Admission case count refused'}
for($taskIndex=0;$taskIndex -lt 33;$taskIndex++){
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
[ordered]@{label='owner-native-fake01';inputs=$taskRecords;interpreter=$taskPython;arguments=@('-I','-S','-B','qualify_owner.py');scope='Original17 owner/bootstrap plus16 generated child-route cases; fake adoption/transport only';no_native_or_model_activity=$true;planned_cases=$taskExpectedCases.ordered_cases;startup_binding_set=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
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
    $taskMembership=(@($taskResult.cases).Count -eq 33 -and @($taskResult.expected_cases).Count -eq 33)
    if($taskMembership){
        for($taskIndex=0;$taskIndex -lt 33;$taskIndex++){
            if($taskResult.cases[$taskIndex].name -cne $taskExpectedCases.ordered_cases[$taskIndex] -or $taskResult.expected_cases[$taskIndex] -cne $taskExpectedCases.ordered_cases[$taskIndex]){$taskMembership=$false}
        }
    }
    $taskCountExit=1
    if($taskFail -eq 0 -and $taskResult.guard_valid -ceq $true){$taskCountExit=0}
    $taskReceiptValid=(
        $taskResult.schema -ceq 'uoink.runtime-owner-native-fake.v1' -and $taskMembership -and
        $taskPass+$taskFail -eq 33 -and $taskResult.count -eq 33 -and $taskResult.skipped -eq 0 -and
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
