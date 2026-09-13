param([Parameter(Mandatory=$true)][ValidateSet('drain')][string]$taskMode)
$taskCase='positive'
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-actual-adapter-native-proposal01'
$taskShared='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-worker-namespace-proposal01'
$taskRuns=@{drain='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-actual-adapter-drain01'}
$taskRun=$taskRuns[$taskMode]
$taskPython='C:\Python314\python.exe'
$taskAdmissionPath=Join-Path $taskProposal ('ROOT-ADMISSION-'+$taskMode+'.json')
$taskSourceMapPath=Join-Path $taskProposal 'SOURCE-INPUTS.json'
$taskLauncherPath=Join-Path $taskProposal 'run_actual_adapter01.ps1'
$taskControls=@()
foreach($taskPair in @(@('ROOT-ADMISSION.json',$taskAdmissionPath),@('SOURCE-INPUTS.json',$taskSourceMapPath),@('run_actual_adapter01.ps1',$taskLauncherPath))){
    $taskControls += [ordered]@{name=$taskPair[0];path=$taskPair[1];sha256=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
$taskMap=Get-Content -LiteralPath $taskSourceMapPath -Raw | ConvertFrom-Json
if($taskAdmission.root_reviewed -isnot [bool] -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.scope -cne 'generated-actual-asr-adapter-only' -or $taskAdmission.case -cne $taskCase -or $taskAdmission.operation_mode -cne $taskMode -or $taskAdmission.run_path -cne $taskRun){throw 'Exact root case admission required'}
if($taskAdmission.source_inputs_sha256 -cne $taskControls[1].sha256 -or $taskAdmission.launcher_sha256 -cne $taskControls[2].sha256){throw 'Admitted input bindings differ'}
if(Test-Path -LiteralPath $taskRun){throw 'Fresh generated observation directory required'}
$taskSources=@()
$taskPaths=[ordered]@{
    'snapshot_lifecycle.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-worker-namespace-proposal01\snapshot_lifecycle.py'
    'win32_worker_connection.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-worker-namespace-proposal01\win32_worker_connection.py'
    'win32_private_pipe.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-dummy-worker-timeout-proposal02\win32_private_pipe.py'
    'pinned_buffer_namespace.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-worker-namespace-proposal01\pinned_buffer_namespace.py'
    'owned_generation_protocol.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\child-readset-adoption-proposal02\owned_generation_protocol.py'
    'inherited_readset.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\child-readset-adoption-proposal02\inherited_readset.py'
    'generated_worker_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\child-readset-adoption-proposal02\generated_worker_flow.py'
    'dummy_bootstrap.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-actual-adapter-native-proposal01\dummy_bootstrap.py'
    'generated_operation_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-operation-native-proposal01\generated_operation_flow.py'
    'trusted_asr_resolver.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-trusted-manifest-resolver-proof02\proposal\trusted_asr_resolver.py'
    'asr_loading_adapter.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-permit-facade-proposal01\asr_loading_adapter.py'
    'generated_adapter_flow.py'='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-actual-adapter-proposal01\generated_adapter_flow.py'
}
if(@($taskMap.source_paths.PSObject.Properties).Count -ne 12 -or @($taskMap.source_sha256.PSObject.Properties).Count -ne 12 -or @($taskMap.native_bindings.PSObject.Properties).Count -ne 9){throw 'Fixed input membership refused'}
foreach($taskName in $taskPaths.Keys){
    $taskPath=$taskPaths[$taskName]
    $taskHash=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskMap.source_paths.$taskName -cne $taskPath -or $taskMap.source_sha256.$taskName -cne $taskHash){throw 'Fixed source input differs'}
    $taskSources += [ordered]@{name=$taskName;path=$taskPath;sha256=$taskHash}
}
$taskNativePaths=@('C:\Python314\python.exe','C:\Python314\python314.dll','C:\Python314\python3.dll','C:\Python314\DLLs\_ctypes.pyd','C:\Python314\DLLs\libffi-8.dll','C:\Windows\System32\kernel32.dll','C:\Python314\Lib\ctypes\__init__.py','C:\Python314\Lib\ctypes\_endian.py','C:\Python314\Lib\ctypes\_layout.py')
$taskNative=@()
foreach($taskPath in $taskNativePaths){
    $taskFile=Get-Item -LiteralPath $taskPath
    $taskHash=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskFile.Length -ne $taskMap.native_bindings.$taskPath.bytes -or $taskHash -cne $taskMap.native_bindings.$taskPath.sha256){throw 'Fixed installed support input differs'}
    $taskNative += [ordered]@{path=$taskPath;bytes=$taskFile.Length;sha256=$taskHash}
}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskInput in ($taskSources+$taskControls)){
    Copy-Item -LiteralPath $taskInput.path -Destination (Join-Path $taskRun $taskInput.name) -ErrorAction Stop
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskInput.name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInput.sha256){throw 'Copied input differs'}
}
$taskNames=@('config.json','model.bin','preprocessor_config.json','tokenizer.json','vocabulary.json')
$taskFixtures=@()
foreach($taskName in $taskNames){
    $taskPath=Join-Path $taskRun $taskName
    $taskBytes=[Text.Encoding]::ASCII.GetBytes('Uoink generated adoption fixture: '+$taskName+". No model data.`n")
    $taskStream=[IO.File]::Open($taskPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$taskStream.Write($taskBytes,0,$taskBytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
    $taskFixtures += [ordered]@{name=$taskName;path=$taskPath;bytes=$taskBytes.Length;sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant();writer_closed=$true}
}
[ordered]@{scope='Actual adapter and generated facade with five ASCII files; no model data';case=$taskCase;operation_mode=$taskMode;sources=$taskSources;controls=$taskControls;native_inputs=$taskNative;fixtures=$taskFixtures} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'before.json') -Encoding utf8
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:PYANNOTE_METRICS_ENABLED='0'
$taskStdout=Join-Path $taskRun 'controller-stdout.log'
$taskStderr=Join-Path $taskRun 'controller-stderr.log'
# BEGIN EXACT NATIVE RECEIPT BLOCK
$PSNativeCommandUseErrorActionPreference=$false
$global:LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'dummy_bootstrap.py') controller 1> $taskStdout 2> $taskStderr
$taskNativeExit=$global:LASTEXITCODE
$taskNativeReceipt=[ordered]@{schema='uoink.native-exit.v1';child_returned=$true;native_exit=$taskNativeExit}
$taskNativeBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskNativeReceipt | ConvertTo-Json -Compress))
$taskNativeStream=[IO.File]::Open((Join-Path $taskRun 'native-exit.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$taskNativeStream.Write($taskNativeBytes,0,$taskNativeBytes.Length);$taskNativeStream.Flush($true)}finally{$taskNativeStream.Dispose()}
if($taskNativeExit -isnot [int]){throw 'Native exit was not captured as an integer'}
# END EXACT NATIVE RECEIPT BLOCK
$taskUnchanged=$true
$taskSourceAfter=@()
foreach($taskInput in ($taskSources+$taskControls)){
    $taskOriginalHash=(Get-FileHash -LiteralPath $taskInput.path -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskCopyHash=(Get-FileHash -LiteralPath (Join-Path $taskRun $taskInput.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskOriginalHash -cne $taskInput.sha256 -or $taskCopyHash -cne $taskInput.sha256){$taskUnchanged=$false}
    $taskSourceAfter += [ordered]@{name=$taskInput.name;before_sha256=$taskInput.sha256;source_after_sha256=$taskOriginalHash;copy_after_sha256=$taskCopyHash}
}
$taskOtherAfter=@()
foreach($taskInput in ($taskNative+$taskFixtures)){
    $taskFile=Get-Item -LiteralPath $taskInput.path
    $taskHash=(Get-FileHash -LiteralPath $taskInput.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskFile.Length -ne $taskInput.bytes -or $taskHash -cne $taskInput.sha256){$taskUnchanged=$false}
    $taskOtherAfter += [ordered]@{path=$taskInput.path;bytes=$taskFile.Length;before_sha256=$taskInput.sha256;after_sha256=$taskHash}
}
[ordered]@{source_and_controls=$taskSourceAfter;support_and_fixtures=$taskOtherAfter;inputs_unchanged=$taskUnchanged} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8
$taskValid=$false
$taskReceiptError=$null
$taskExpectedChildExit=0
if($taskCase -ceq 'wrong_identity'){$taskExpectedChildExit=2}
try{
    $taskControllerPath=Join-Path $taskRun 'controller-result.json'
    $taskChildPath=Join-Path $taskRun 'child-result.json'
    if((Get-Item -LiteralPath $taskControllerPath).Length -gt 131072 -or (Get-Item -LiteralPath $taskChildPath).Length -gt 131072){throw 'Receipt size bound'}
    $taskController=Get-Content -LiteralPath $taskControllerPath -Raw | ConvertFrom-Json
    $taskChild=Get-Content -LiteralPath $taskChildPath -Raw | ConvertFrom-Json
    $taskValid=$true
    foreach($taskReceipt in @($taskController,$taskChild)){
        if($taskReceipt.schema -cne 'uoink.generated-actual-asr-adapter.v1' -or $taskReceipt.operation_mode -cne $taskMode -or $taskReceipt.case -cne $taskCase -or $taskReceipt.guard_valid -cne $true -or $taskReceipt.model_calls -ne 0 -or @($taskReceipt.model_imports).Count -ne 0 -or @($taskReceipt.guard_denials).Count -ne 0 -or $taskReceipt.metadata_traps -ne 12 -or $taskReceipt.registry_traps -ne 25 -or $null -ne $taskReceipt.error_type -or $taskReceipt.pending_pipe_operations -ne 0){$taskValid=$false}
        if($taskReceipt.work_budget_closed -cne $false -or @($taskReceipt.reserved_cleanup_calls).Count -ne 0 -or $taskReceipt.kernel32_path_verified -cne $true){$taskValid=$false}
        $taskExpectedCasts=0
        if($taskReceipt.role -ceq 'controller'){$taskExpectedCasts=1}
        $taskExpectedDispatches=33+@($taskReceipt.native_api_calls).Count+$taskExpectedCasts
        if($taskReceipt.fixed_dispatch_valid -cne $true -or $taskReceipt.fixed_dispatch_function_count -ne 32 -or $taskReceipt.fixed_dispatch_invalid_contexts -ne 0 -or $taskReceipt.fixed_attribute_cast_calls -ne $taskExpectedCasts -or $taskReceipt.fixed_dispatch_completed_calls -ne $taskExpectedDispatches -or $taskReceipt.fixed_dispatch_audit_events -ne $taskExpectedDispatches){$taskValid=$false}
        foreach($taskSource in $taskSources){if($taskReceipt.source_sha256.($taskSource.name) -cne $taskSource.sha256){$taskValid=$false}}
    }
    if($taskController.role -cne 'controller' -or $taskChild.role -cne 'child' -or $taskNativeExit -ne 0 -or $taskController.native_exit_planned -ne 0 -or $taskChild.native_exit_planned -ne $taskExpectedChildExit -or $taskChild.result.child_flow_return -ne $taskExpectedChildExit){$taskValid=$false}
    $taskResult=$taskController.result
    if($taskResult.lifecycle_phase -ne 8 -or $taskResult.read_set_released -cne $true -or $taskResult.pipe_retired -cne $true -or $taskResult.parent_guards_held_through_exit -cne $true -or $taskResult.adoption_case -cne $taskCase -or $taskResult.model_calls -ne 0){$taskValid=$false}
    if($taskResult.exit_observation.child_native_exit -ne $taskExpectedChildExit -or $taskResult.exit_observation.process_wait_observed -cne $true -or $taskResult.exit_observation.job_active_processes -ne 0){$taskValid=$false}
    if(@($taskController.native_api_calls | Where-Object {$_ -ceq 'CreateProcessW'}).Count -ne 1 -or @($taskChild.native_api_calls | Where-Object {$_ -in @('CreateFileW','CreateProcessW')}).Count -ne 0){$taskValid=$false}
    if(@($taskResult.write_access_observations).Count -ne 10){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){
        $taskLocked=$taskResult.write_access_observations[$taskIndex]
        $taskOpen=$taskResult.write_access_observations[$taskIndex+5]
        if($taskLocked.write_open_refused -cne $true -or $taskLocked.winerror -ne 32 -or $taskOpen.write_open_succeeded -cne $true -or $taskOpen.bytes_written -ne 0){$taskValid=$false}
    }
    $taskAdoption=$taskChild.result.adoption
    if($taskAdoption.owned_members -ne 5 -or $taskAdoption.inheritance_cleared -ne 5 -or @($taskAdoption.handles_closed).Count -ne 5 -or $taskAdoption.complete_native_namespace_protection -cne $false -or $taskAdoption.model_calls -ne 0){$taskValid=$false}
    $taskManifest=$taskResult.authenticated_manifest
    if($taskManifest.schema -cne 'uoink.generated-inherited-readset.v1' -or $taskManifest.case -cne $taskCase -or @($taskManifest.members).Count -ne 5){$taskValid=$false}
    $taskCanonicalRows=@()
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){
        $taskRow=$taskManifest.members[$taskIndex]
        $taskIdentity=$taskRow.identity
        if($taskRow.name -cne $taskFixtures[$taskIndex].name -or $taskRow.sha256 -cne $taskFixtures[$taskIndex].sha256 -or $taskIdentity.size -ne $taskFixtures[$taskIndex].bytes){$taskValid=$false}
        $taskCanonicalIdentity=[ordered]@{directory=$taskIdentity.directory;file_id=$taskIdentity.file_id;final_path=$taskIdentity.final_path;links=$taskIdentity.links;size=$taskIdentity.size;volume_serial=$taskIdentity.volume_serial}
        $taskCanonicalRows += [ordered]@{handle=$taskRow.handle;identity=$taskCanonicalIdentity;name=$taskRow.name;sha256=$taskRow.sha256}
    }
    $taskCanonical=[ordered]@{case=$taskManifest.case;members=$taskCanonicalRows;namespace_sha256=$taskManifest.namespace_sha256;schema=$taskManifest.schema} | ConvertTo-Json -Compress -Depth 8
    $taskManifestHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($taskCanonical))).ToLowerInvariant()
    if($taskManifestHash -cne $taskResult.manifest_sha256){$taskValid=$false}
    $taskExpectedIdentities=5
    if($taskCase -ceq 'wrong_identity'){$taskExpectedIdentities=1}
    if(@($taskAdoption.observed_identities).Count -ne $taskExpectedIdentities){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt $taskExpectedIdentities;$taskIndex++){
        $taskActualIdentity=$taskAdoption.observed_identities[$taskIndex]
        $taskExpectedIdentity=$taskManifest.members[$taskIndex].identity
        foreach($taskField in @('directory','final_path','links','size','volume_serial')){
            if($taskActualIdentity.$taskField -cne $taskExpectedIdentity.$taskField){$taskValid=$false}
        }
        if($taskCase -ceq 'positive'){
            if($taskActualIdentity.file_id -cne $taskExpectedIdentity.file_id){$taskValid=$false}
        }else{
            $taskActualId=[Convert]::FromHexString($taskActualIdentity.file_id)
            $taskExpectedId=[Convert]::FromHexString($taskExpectedIdentity.file_id)
            if($taskActualId.Length -ne 16 -or $taskExpectedId.Length -ne 16){$taskValid=$false}
            for($taskByteIndex=0;$taskByteIndex -lt 16;$taskByteIndex++){
                $taskExpectedByte=$taskActualId[$taskByteIndex]
                if($taskByteIndex -eq 0){$taskExpectedByte=$taskExpectedByte -bxor 1}
                if($taskExpectedId[$taskByteIndex] -ne $taskExpectedByte){$taskValid=$false}
            }
        }
    }
    foreach($taskFixture in $taskFixtures){
        $taskName=$taskFixture.name
        $taskChildIO=$taskChild.generated_asset_io.$taskName
        $taskParentIO=$taskController.generated_asset_io.$taskName
        if($taskParentIO.seeks -ne 0 -or $taskParentIO.reads -ne 0 -or $taskParentIO.bytes -ne 0){$taskValid=$false}
        if($taskCase -ceq 'positive'){
            if($taskChildIO.seeks -ne 1 -or $taskChildIO.reads -ne 2 -or $taskChildIO.bytes -ne $taskFixture.bytes){$taskValid=$false}
            $taskRows=@($taskChild.result.readback.members | Where-Object {$_.name -ceq $taskName})
            if($taskRows.Count -ne 1 -or $taskRows[0].bytes -ne $taskFixture.bytes -or $taskRows[0].sha256 -cne $taskFixture.sha256){$taskValid=$false}
        }elseif($taskChildIO.seeks -ne 0 -or $taskChildIO.reads -ne 0 -or $taskChildIO.bytes -ne 0){$taskValid=$false}
    }
    if($taskCase -ceq 'positive'){
        if($taskAdoption.status -cne 'released' -or $taskAdoption.identities_checked -ne 5 -or $taskAdoption.materialization_started -cne $true -or $taskAdoption.read_set_unconfirmed -cne $false -or $taskAdoption.read_set_released -cne $true -or $taskResult.controller_handshake_begun -cne $true -or @($taskChild.result.readback.members).Count -ne 5){$taskValid=$false}
        foreach($taskClosed in $taskAdoption.handles_closed){if($taskClosed -cne $true){$taskValid=$false}}
    }else{
        if($taskAdoption.status -cne 'refused' -or $taskAdoption.identities_checked -ne 1 -or $taskAdoption.materialization_started -cne $false -or $taskAdoption.read_set_unconfirmed -cne $true -or $taskAdoption.read_set_released -cne $false -or $taskResult.controller_handshake_begun -cne $false -or $null -ne $taskChild.result.readback -or $taskResult.adoption_response.reason -cne 'inherited_file_identity_mismatch'){$taskValid=$false}
        foreach($taskClosed in $taskAdoption.handles_closed){if($taskClosed -cne $false){$taskValid=$false}}
    }

    # Exact generated operation observations, in addition to unchanged native/adoption checks.
    $taskExpectedCount=2
    $taskExpectedState='eof'
    $taskExpectedActions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','next_generated_segment','next_generated_segment')
    if($taskMode -ceq 'cancel'){
        $taskExpectedCount=1
        $taskExpectedState='cancelled'
        $taskExpectedActions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')
    }
    if($taskResult.operation_mode -cne $taskMode -or $taskResult.cursor_state -cne $taskExpectedState -or $taskChild.result.cursor_state -cne $taskExpectedState -or $taskChild.result.produced_segments -ne $taskExpectedCount -or $taskResult.retained_facade_and_stream_refused -cne $true -or $taskChild.result.generated_duration_only -cne $true){$taskValid=$false}
    foreach($taskObserved in @($taskResult,$taskChild.result)){
        if(@($taskObserved.operation_events).Count -ne $taskExpectedActions.Count){$taskValid=$false}
        for($taskIndex=0;$taskIndex -lt $taskExpectedActions.Count;$taskIndex++){
            if($taskObserved.operation_events[$taskIndex] -cne $taskExpectedActions[$taskIndex]){$taskValid=$false}
        }
        if(@($taskObserved.cursor_start.PSObject.Properties).Count -ne 3 -or $taskObserved.cursor_start.cursor_id -cne 'generated-cursor-01' -or $taskObserved.cursor_start.started -isnot [bool] -or $taskObserved.cursor_start.started -cne $true -or $taskObserved.cursor_start.produced_segments -isnot [long] -and $taskObserved.cursor_start.produced_segments -isnot [int] -or $taskObserved.cursor_start.produced_segments -ne 0){$taskValid=$false}
    }
    $taskTextNames=@('config.json','tokenizer.json')
    if(@($taskResult.segments).Count -ne $taskExpectedCount){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt $taskExpectedCount;$taskIndex++){
        $taskSegment=$taskResult.segments[$taskIndex]
        $taskExpectedText='Uoink generated adoption fixture: '+$taskTextNames[$taskIndex]+'. No model data.'
        if(@($taskSegment.PSObject.Properties).Count -ne 4 -or $taskSegment.start -isnot [double] -or $taskSegment.end -isnot [double] -or $taskSegment.start -ne ($taskIndex/2.0) -or $taskSegment.end -ne (($taskIndex+1)/2.0) -or $taskSegment.text -isnot [string] -or $taskSegment.text -cne $taskExpectedText -or @($taskSegment.words).Count -ne 0){$taskValid=$false}
    }
    if($taskChild.result.readback.payload_bytes -ne 328 -or $taskChild.result.readback.namespace_sha256 -cne $taskManifest.namespace_sha256){$taskValid=$false}

    # Actual-adapter state is observed independently by the unchanged-guard bootstrap.
    $taskStateNames=@('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')
    foreach($taskReceipt in @($taskController,$taskChild)){
        if(@($taskReceipt.adapter_state.PSObject.Properties).Count -ne 5){$taskValid=$false}
        foreach($taskName in $taskStateNames){if($taskReceipt.adapter_state.$taskName -isnot [bool] -or $taskReceipt.adapter_state.$taskName -cne $true){$taskValid=$false}}
    }
    $taskAuthorityEvents=@('generated_release','generated_admit','generated_bind','owned_start_validated','worker_start_bound')
    if(@($taskResult.authority_events).Count -ne 5){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){if($taskResult.authority_events[$taskIndex] -cne $taskAuthorityEvents[$taskIndex]){$taskValid=$false}}
    if($taskResult.actual_adapter_context -cne 'faster_whisper_session' -or $taskResult.binding_calls -ne 1){$taskValid=$false}
    foreach($taskField in @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit','adapter_owned_cleanup')){
        if($taskResult.$taskField -isnot [bool] -or $taskResult.$taskField -cne $true){$taskValid=$false}
    }
    if($taskChild.result.real_resolver_approval_unchanged_none -cne $true -or $taskChild.result.real_resolver_functions_unchanged -cne $true){$taskValid=$false}
    $taskExpectedPolicy=[ordered]@{
        action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true
        generated_root=$taskRun;inherited_manifest_sha256=$taskResult.manifest_sha256;local_files_only=$true
        namespace_sha256='f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9';profile_id='generated-asr-reliability-v1';real_runtime_approved=$false
        recipe_sha256='6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33';revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf';usage='reliability'
    }
    $taskPolicyCanonical=$taskExpectedPolicy | ConvertTo-Json -Compress -Depth 5
    $taskPolicyDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($taskPolicyCanonical))).ToLowerInvariant()
    foreach($taskObserved in @($taskResult,$taskChild.result)){
        if(@($taskObserved.adapter_start.PSObject.Properties).Count -ne $taskExpectedPolicy.Count){$taskValid=$false}
        foreach($taskName in $taskExpectedPolicy.Keys){
            $taskValue=$taskObserved.adapter_start.$taskName
            $taskExpected=$taskExpectedPolicy[$taskName]
            if($null -eq $taskValue -or $taskValue.GetType() -ne $taskExpected.GetType() -or $taskValue -cne $taskExpected){$taskValid=$false}
        }
        $taskAck=$taskObserved.adapter_start_ack
        if(@($taskAck.PSObject.Properties).Count -ne 3 -or $taskAck.action -cne 'generated_adapter_start_bound' -or $taskAck.policy_sha256 -cne $taskPolicyDigest -or ($taskAck.model_calls -isnot [long] -and $taskAck.model_calls -isnot [int]) -or $taskAck.model_calls -ne 0){$taskValid=$false}
    }
}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}
$taskStdoutBytes=(Get-Item -LiteralPath $taskStdout).Length
$taskStderrBytes=(Get-Item -LiteralPath $taskStderr).Length
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskValid -or $taskStdoutBytes -ne 0 -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{case=$taskCase;controller_native_exit=$taskNativeExit;expected_child_native_exit=$taskExpectedChildExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskValid;receipt_error_type=$taskReceiptError;stdout_bytes=$taskStdoutBytes;stderr_bytes=$taskStderrBytes;operation_mode=$taskMode;scope='Actual ASR adapter with generated data only; no model acceptance'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
