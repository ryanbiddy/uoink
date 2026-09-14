param([Parameter(Mandatory=$true)][ValidateSet('drain')][string]$taskMode)
$taskCase='positive'
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-generated-native-compatibility-proposal01'
$taskRuns=@{drain='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-generated-native-compatibility01'}
$taskRun=$taskRuns[$taskMode]
$taskPython='C:\Python314\python.exe'
$taskAdmissionPath=Join-Path $taskProposal ('ROOT-ADMISSION-'+$taskMode+'.json')
$taskSourceMapPath=Join-Path $taskProposal 'SOURCE-INPUTS.json'
$taskLauncherPath=Join-Path $taskProposal 'run_controller_generated_compatibility01.ps1'
$taskControls=@()
foreach($taskPair in @(@('ROOT-ADMISSION.json',$taskAdmissionPath),@('SOURCE-INPUTS.json',$taskSourceMapPath),@('run_controller_generated_compatibility01.ps1',$taskLauncherPath))){
    $taskControls += [ordered]@{name=$taskPair[0];path=$taskPair[1];sha256=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
$taskMap=Get-Content -LiteralPath $taskSourceMapPath -Raw | ConvertFrom-Json
if($taskAdmission.root_reviewed -isnot [bool] -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.scope -cne 'generated-controller-core-start-compatibility-only' -or $taskAdmission.case -cne $taskCase -or $taskAdmission.operation_mode -cne $taskMode -or $taskAdmission.run_path -cne $taskRun){throw 'Exact root case admission required'}
if($taskAdmission.source_inputs_sha256 -cne $taskControls[1].sha256 -or $taskAdmission.launcher_sha256 -cne $taskControls[2].sha256){throw 'Admitted input bindings differ'}
if(Test-Path -LiteralPath $taskRun){throw 'Fresh generated observation directory required'}
$taskSources=@()
$taskPaths=[ordered]@{}
$taskSourceNames=@('plain_state_reader.py','state_bridge.py','owned_cpu_tensor_port.py','model_binding_registry.py','owned_factory_port.py','owned_guard.py','fake_torch_support.py','fixed_schema_helpers.py','worker_runtime_owner.py','reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py','durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py','win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py','generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_journal_setup.py','generated_writer_exclusion.py','generated_worker_factory_inputs.py','generated_worker_runtime_bridge.py','generated_adapter_flow.py','dummy_bootstrap.py')
foreach($taskName in $taskSourceNames){$taskPaths[$taskName]=Join-Path $taskProposal $taskName}
if(@($taskMap.source_paths.PSObject.Properties).Count -ne 29 -or @($taskMap.source_sha256.PSObject.Properties).Count -ne 29 -or @($taskMap.native_bindings.PSObject.Properties).Count -ne 9){throw 'Fixed input membership refused'}
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
New-Item -ItemType Directory -Path (Join-Path $taskRun 'registry') -ErrorAction Stop | Out-Null
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
$taskExpectedChildExit=1
function Assert-True($x){if($x -isnot [bool] -or $x -cne $true){throw 'Required true observation'}}
function Assert-False($x){if($x -isnot [bool] -or $x -cne $false){throw 'Required false observation'}}
function Assert-Strings($a,$e){
    if(@($a).Count -ne @($e).Count){throw 'String membership'}
    for($i=0;$i -lt @($e).Count;$i++){if($a[$i] -isnot [string] -or $a[$i] -cne $e[$i]){throw 'String order'}}
}
try{
    $taskControllerPath=Join-Path $taskRun 'controller-result.json'
    $taskContenderPath=Join-Path $taskRun 'contender-result.json'
    $taskChildPath=Join-Path $taskRun 'child-result.json'
    $taskPartial=[ordered]@{present=$false;bytes=$null;sha256=$null;final_guard_or_clean_owner_credit=$false}
    if(Test-Path -LiteralPath $taskChildPath){
        $taskChildFile=Get-Item -LiteralPath $taskChildPath
        if($taskChildFile.PSIsContainer -or $taskChildFile.Length -gt 1048576){throw 'Partial receipt bound'}
        $taskPartial.present=$true;$taskPartial.bytes=$taskChildFile.Length
        $taskPartial.sha256=(Get-FileHash -LiteralPath $taskChildPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $taskPartial | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'child-receipt-observation.json') -Encoding utf8
    if((Get-Item -LiteralPath $taskControllerPath).Length -gt 1048576 -or (Get-Item -LiteralPath $taskContenderPath).Length -gt 1048576){throw 'Receipt size bound'}
    $taskController=Get-Content -LiteralPath $taskControllerPath -Raw | ConvertFrom-Json
    $taskContender=Get-Content -LiteralPath $taskContenderPath -Raw | ConvertFrom-Json
    $taskValid=$true
    foreach($taskReceipt in @($taskController,$taskContender)){
        if($taskReceipt.schema -cne 'uoink.generated-windows-interrupted-owner-retirement.v1' -or $taskReceipt.operation_mode -cne $taskMode -or $taskReceipt.case -cne $taskCase -or $taskReceipt.guard_valid -cne $true -or $taskReceipt.model_calls -ne 0 -or @($taskReceipt.model_imports).Count -ne 0 -or @($taskReceipt.guard_denials).Count -ne 0 -or $taskReceipt.metadata_traps -ne 12 -or $taskReceipt.registry_traps -ne 25 -or $null -ne $taskReceipt.error_type -or $taskReceipt.pending_pipe_operations -ne 0){$taskValid=$false}
        if($taskReceipt.work_budget_closed -cne $false -or @($taskReceipt.reserved_cleanup_calls).Count -ne 0 -or $taskReceipt.kernel32_path_verified -cne $true){$taskValid=$false}
        $taskExpectedCasts=0
        if($taskReceipt.role -ceq 'controller'){$taskExpectedCasts=2}
        $taskExpectedDispatches=34+@($taskReceipt.native_api_calls).Count+$taskExpectedCasts
        if($taskReceipt.fixed_dispatch_valid -cne $true -or $taskReceipt.fixed_dispatch_function_count -ne 33 -or $taskReceipt.fixed_dispatch_invalid_contexts -ne 0 -or $taskReceipt.fixed_attribute_cast_calls -ne $taskExpectedCasts -or $taskReceipt.fixed_dispatch_completed_calls -ne $taskExpectedDispatches -or $taskReceipt.fixed_dispatch_audit_events -ne $taskExpectedDispatches){$taskValid=$false}
        foreach($taskSource in $taskSources){if($taskReceipt.source_sha256.($taskSource.name) -cne $taskSource.sha256){$taskValid=$false}}
    }
    if($taskController.role -cne 'controller' -or $taskContender.role -cne 'contender' -or $taskNativeExit -ne 0 -or $taskController.native_exit_planned -ne 0 -or $taskContender.native_exit_planned -ne 0){throw 'Complete process outcomes'}
    foreach($receipt in @($taskController,$taskContender)){if($null -ne $receipt.quarantine_error_type){throw 'Fallback quarantine failed'}}
    $taskResult=$taskController.result
    $taskExclusion=$taskController.writer_exclusion
    $taskRefusal=$taskContender.result
    if($taskContender.role -cne 'contender' -or $taskContender.native_exit_planned -ne 0 -or $null -ne $taskContender.writer_exclusion -or $taskRefusal.status -cne 'sharing_refused' -or $taskRefusal.attempt_count -ne 1 -or $taskRefusal.winerror -ne 32 -or $taskRefusal.valid_journal_handle_returned -cne $false -or $taskRefusal.journal_content_reads -ne 0 -or $taskRefusal.journal_writes -ne 0 -or $taskRefusal.own_directory_guards_retired -cne $true -or $taskRefusal.passive_inherited_guard_retired_by_process_exit_only -cne $true -or $taskRefusal.semantic_labels_are_authority -cne $false -or $taskRefusal.model_calls -ne 0){throw 'Contender refusal contract differs'}
    if($taskRefusal.semantic_choice -cne 'independent-contender' -or $taskRefusal.semantic_revision -cne 'different-revision'){throw 'Fixed passive contender labels differ'}
    if($taskExclusion.completed -cne $true -or $null -ne $taskExclusion.failure_type -or $taskExclusion.stop_attempted -cne $false -or $null -ne $taskExclusion.stop_wait_observed -or $taskExclusion.guard_released -cne $true -or $taskExclusion.worker_handles_closed -cne $true -or $taskExclusion.worker_unconfirmed -cne $false -or $taskExclusion.passive_inherited_guard_count -ne 1 -or $taskExclusion.inherited_control_handle_absent -cne $true -or $taskExclusion.primary_journal_held_through_contender_exit -cne $true -or $taskExclusion.model_calls -ne 0 -or $taskExclusion.observed_pid -le 0 -or $taskExclusion.observed_creation_time -le 0){throw 'Exact contender lifetime was not retired'}
    if($taskExclusion.exit_observation.child_native_exit -ne 0 -or $taskExclusion.exit_observation.process_wait_observed -cne $true -or $taskExclusion.exit_observation.job_active_processes -ne 0){throw 'Contender process/job exit missing'}
    if(@($taskContender.native_api_calls).Count -ne 103 -or @($taskContender.native_api_calls | Where-Object {$_ -ceq 'CreateFileW'}).Count -ne 18 -or @($taskContender.native_api_calls | Where-Object {$_ -ceq 'CloseHandle'}).Count -ne 17 -or @($taskContender.native_api_calls | Where-Object {$_ -ceq 'GetFileInformationByHandleEx'}).Count -ne 51 -or @($taskContender.native_api_calls | Where-Object {$_ -ceq 'GetFinalPathNameByHandleW'}).Count -ne 17){throw 'Finite contender API membership differs'}
    if($taskRefusal.open_call_index -ne 85 -or $taskContender.native_api_calls[$taskRefusal.open_call_index] -cne 'CreateFileW'){throw 'One journal attempt must follow exact ancestor retention'}
    foreach($taskAsset in $taskContender.generated_asset_io.PSObject.Properties){if($taskAsset.Value.seeks -ne 0 -or $taskAsset.Value.reads -ne 0 -or $taskAsset.Value.bytes -ne 0){throw 'Contender must not read generated content'}}
    if(@($taskController.native_api_calls | Where-Object {$_ -ceq 'CreateProcessW'}).Count -ne 2 -or @($taskController.native_api_calls | Where-Object {$_ -ceq 'ResumeThread'}).Count -ne 2){throw 'Two create/resume pairs'}
    if(@($taskController.native_api_calls | Where-Object {$_ -ceq 'TerminateJobObject'}).Count -ne 1 -or @($taskController.native_api_calls | Where-Object {$_ -ceq 'TerminateProcess'}).Count -ne 0){throw 'Primary one-stop latch'}
    if($taskResult.lifecycle_phase -ne 8 -or $taskResult.read_set_released -cne $true -or $taskResult.pipe_retired -cne $true -or $taskResult.adoption_case -cne 'positive' -or $taskResult.model_calls -ne 0){throw 'Released parent state'}
    Assert-False $taskResult.parent_guards_held_through_exit
    if($taskResult.exit_observation.child_native_exit -ne 1 -or $taskResult.exit_observation.process_wait_observed -cne $true -or $taskResult.exit_observation.job_active_processes -ne 0){throw 'Retained primary exit/job'}
    if(@($taskResult.write_access_observations).Count -ne 10){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){
        $taskLocked=$taskResult.write_access_observations[$taskIndex]
        $taskOpen=$taskResult.write_access_observations[$taskIndex+5]
        if($taskLocked.write_open_refused -cne $true -or $taskLocked.winerror -ne 32 -or $taskOpen.write_open_succeeded -cne $true -or $taskOpen.bytes_written -ne 0){$taskValid=$false}
    }
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
    $taskActions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','next_generated_segment')
    Assert-Strings $taskResult.operation_events $taskActions
    if($taskResult.operation_mode -cne 'drain' -or $taskResult.cursor_state -cne 'active' -or @($taskResult.segments).Count -ne 1){throw 'Interrupted segment counts'}
    $taskSegment=$taskResult.segments[0]
    if(@($taskSegment.PSObject.Properties).Count -ne 4 -or $taskSegment.start -isnot [double] -or $taskSegment.end -isnot [double] -or $taskSegment.start -ne 0.0 -or $taskSegment.end -ne 0.5 -or $taskSegment.text -cne 'Uoink generated adoption fixture: config.json. No model data.' -or @($taskSegment.words).Count -ne 0){throw 'First fixed segment'}
    if(@($taskResult.cursor_start.PSObject.Properties).Count -ne 3 -or $taskResult.cursor_start.cursor_id -cne 'generated-cursor-01' -or $taskResult.cursor_start.started -cne $true -or $taskResult.cursor_start.produced_segments -ne 0){throw 'Cursor start'}
    # Actual-adapter state is observed independently by the unchanged-guard bootstrap.
    $taskStateNames=@('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')
    foreach($taskReceipt in @($taskController,$taskContender)){
        if(@($taskReceipt.adapter_state.PSObject.Properties).Count -ne 5){$taskValid=$false}
        foreach($taskName in $taskStateNames){if($taskReceipt.adapter_state.$taskName -isnot [bool] -or $taskReceipt.adapter_state.$taskName -cne $true){$taskValid=$false}}
    }
    $taskAuthorityEvents=@('generated_release','generated_admit','generated_bind','owned_start_validated','worker_start_bound')
    if(@($taskResult.authority_events).Count -ne 5){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){if($taskResult.authority_events[$taskIndex] -cne $taskAuthorityEvents[$taskIndex]){$taskValid=$false}}
    if($taskResult.actual_adapter_context -cne 'faster_whisper_session' -or $taskResult.binding_calls -ne 1){$taskValid=$false}
    foreach($taskField in @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit')){
        if($taskResult.$taskField -isnot [bool] -or $taskResult.$taskField -cne $true){$taskValid=$false}
    }
    foreach($taskName in @('adapter_context_unwound_before_explicit_cleanup','explicit_interrupted_owner_cleanup','retained_facade_and_stream_refused','controller_handshake_begun')){Assert-True $taskResult.$taskName}
    $taskExpectedPolicy=[ordered]@{
        action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true
        generated_root=$taskRun;inherited_manifest_sha256=$taskResult.manifest_sha256;local_files_only=$true
        namespace_sha256='f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9';profile_id='generated-asr-reliability-v1';real_runtime_approved=$false
        recipe_sha256='6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33';revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf';usage='reliability'
    }
    $taskPolicyCanonical=$taskExpectedPolicy | ConvertTo-Json -Compress -Depth 5
    $taskPolicyDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($taskPolicyCanonical))).ToLowerInvariant()
    foreach($taskObserved in @($taskResult)){
        if(@($taskObserved.adapter_start.PSObject.Properties).Count -ne $taskExpectedPolicy.Count){$taskValid=$false}
        foreach($taskName in $taskExpectedPolicy.Keys){
            $taskValue=$taskObserved.adapter_start.$taskName
            $taskExpected=$taskExpectedPolicy[$taskName]
            if($null -eq $taskValue -or $taskValue.GetType() -ne $taskExpected.GetType() -or $taskValue -cne $taskExpected){$taskValid=$false}
        }
        $taskAck=$taskObserved.adapter_start_ack
        if(@($taskAck.PSObject.Properties).Count -ne 3 -or $taskAck.action -cne 'generated_adapter_start_bound' -or $taskAck.policy_sha256 -cne $taskPolicyDigest -or ($taskAck.model_calls -isnot [long] -and $taskAck.model_calls -isnot [int]) -or $taskAck.model_calls -ne 0){$taskValid=$false}
    }
    $taskOwnerStateNames=@('methods_unchanged','closed_entries_unchanged','module_identities_unchanged','owned_guard_restored_none','require_owned_runtime_unchanged','retained_bridge_type_valid')
    foreach($taskReceipt in @($taskController,$taskContender)){
        if(@($taskReceipt.owner_state.PSObject.Properties).Count -ne 6){throw 'Exact owner guard fields required'}
        foreach($taskName in $taskOwnerStateNames){
            if($taskReceipt.owner_state.$taskName -isnot [bool] -or $taskReceipt.owner_state.$taskName -cne $true){throw 'Runtime owner binding guard failed'}
        }
    }
    foreach($receipt in @($taskController,$taskContender)){if($null -ne $receipt.retained_runtime_owner){throw 'Parent retained child bridge'}}
    foreach($asset in $taskController.generated_asset_io.PSObject.Properties){if($asset.Value.seeks -ne 0 -or $asset.Value.reads -ne 0 -or $asset.Value.bytes -ne 0){throw 'Parent content read'}}
    $taskRecovery=$taskResult.interrupted_owner_recovery
    if($taskRecovery.interruption_type -cne 'KeyboardInterrupt' -or $taskRecovery.stage -cne 'after_second_segment_exchange'){throw 'Fixed interruption'}
    foreach($name in @('interruption_identity_match','ordinary_completion_refused','ordinary_reconciliation_refused','manager_reconciliation_confirmed','owner_still_revoked','token_still_revoked','same_owner_and_record','journal_open_until_recovery_clear')){Assert-True $taskRecovery.$name}
    Assert-False $taskRecovery.native_interrupt_crash_or_restart_claim
    $taskObserved=$taskResult.interrupted_retirement_observation
    foreach($name in @('retained_witness_current_at_completion','active_manager_attempt_absent_at_completion','same_manager_owner_token_permit_delegate','aggregate_quarantine_history_retained','all_individual_handles_confirmed_closed','owner_closed_and_revoked','token_still_revoked','primary_stop_latch_consumed','primary_process_wait_observed')){Assert-True $taskObserved.$name}
    Assert-False $taskObserved.ordinary_parent_guard_claim_available
    Assert-False $taskObserved.final_child_guard_or_clean_owner_claim
    if($taskObserved.retained_handle_count -ne 16 -or $taskObserved.primary_native_exit -ne 1 -or $taskObserved.primary_job_active_processes -ne 0 -or $taskObserved.pre_interruption_revision -lt 0 -or $taskObserved.post_quarantine_revision -le $taskObserved.pre_interruption_revision -or $taskObserved.token_revision_at_completion -ne $taskObserved.post_quarantine_revision){throw 'Witness/revision result'}
    $taskEvents=@($taskObserved.native_events)
    if(($taskEvents | ConvertTo-Json -Depth 6 -Compress) -cne (@($taskController.interrupted_native_events) | ConvertTo-Json -Depth 6 -Compress)){throw 'Retained call observations changed'}
    $taskExpectedEvents=@(@('TerminateJobObject','job',$false,1),@('WaitForSingleObject','process',$false,0),@('GetProcessTimes','process',$true,1),@('WaitForSingleObject','process',$true,0),@('GetExitCodeProcess','process',$true,1),@('QueryInformationJobObject','job',$true,1),@('CloseHandle','server',$true,1),@('CloseHandle','thread',$true,1),@('CloseHandle','process',$true,1),@('CloseHandle','job',$true,1),@('CloseHandle','member4',$true,1),@('CloseHandle','member3',$true,1),@('CloseHandle','member2',$true,1),@('CloseHandle','member1',$true,1),@('CloseHandle','member0',$true,1))
    if($taskEvents.Count -ne $taskExpectedEvents.Count){throw 'Retained call membership'}
    $last=-1
    for($i=0;$i -lt $taskEvents.Count;$i++){
        $event=$taskEvents[$i];$expected=$taskExpectedEvents[$i]
        if(@($event.PSObject.Properties).Count -ne 5 -or $event.api -cne $expected[0] -or $event.owner -cne $expected[1] -or $event.manager_attempt_active_at_call -isnot [bool] -or $event.manager_attempt_active_at_call -cne $expected[2] -or $event.native_result -ne $expected[3] -or $event.call_index -le $last -or $event.call_index -ge @($taskController.native_api_calls).Count -or $taskController.native_api_calls[$event.call_index] -cne $event.api){throw 'Retained call identity/order/result'}
        $last=$event.call_index
    }
    $taskJournal=$taskResult.durable_journal
    if(($taskRefusal.physical | ConvertTo-Json -Compress) -cne ($taskJournal.physical | ConvertTo-Json -Compress) -or $taskRefusal.journal_path -cne $taskJournal.journal_path){throw 'Independent contender physical target differs'}
    if(@($taskJournal.physical).Count -ne 2 -or $taskJournal.physical[0] -is [bool] -or ([string]$taskJournal.physical[0]) -cnotmatch '^[0-9]{1,20}$' -or $taskJournal.physical[1] -isnot [string] -or $taskJournal.physical[1] -cnotmatch '^[0-9a-f]{32}$'){throw 'Bounded journal physical identity required'}
    $taskVolume=[UInt64]::Parse([string]$taskJournal.physical[0],[Globalization.CultureInfo]::InvariantCulture)
    $taskJournalName=$taskVolume.ToString('x16',[Globalization.CultureInfo]::InvariantCulture)+'-'+$taskJournal.physical[1]+'.journal'
    $taskJournalPath=Join-Path (Join-Path $taskRun 'registry') $taskJournalName
    if($taskJournal.journal_path -cne $taskJournalPath -or $taskJournal.journal_bytes -le 6 -or $taskJournal.journal_bytes -gt 20666 -or $taskJournal.journal_hex -isnot [string] -or $taskJournal.journal_hex -cnotmatch '^[0-9a-f]+$' -or $taskJournal.journal_hex.Length -ne 2*$taskJournal.journal_bytes -or $taskJournal.journal_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $taskJournal.head -cnotmatch '^[0-9a-f]{64}$'){throw 'Fixed generated journal receipt bound'}
    if($taskJournal.creation_handle_transferred_without_close -cne $true -or $taskJournal.journal_handle_closed -cne $true -or $taskJournal.directory_guards_retired -cne $true -or $taskJournal.native_power_loss_or_restart_claim -cne $false -or $taskJournal.flush_successes -ne 5){throw 'Generated journal retirement missing'}
    $taskPhases=@('INITIALIZED','RESERVED','WORKER_BOUND','QUARANTINED','CLEARED')
    if(@($taskJournal.phases).Count -ne 5){throw 'Five confirmed phases required'}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){if($taskJournal.phases[$taskIndex] -cne $taskPhases[$taskIndex]){throw 'Journal phase order differs'}}
    $taskExpectedMilestones=@(@('CreateProcessW','RESERVED',2),@('ResumeThread','WORKER_BOUND',3),@('CloseHandle','CLEARED',5))
    if(@($taskJournal.milestones).Count -ne 3){throw 'Three journal ordering observations required'}
    $taskLastMilestone=-1
    for($taskIndex=0;$taskIndex -lt 3;$taskIndex++){
        $taskMilestone=$taskJournal.milestones[$taskIndex]
        $taskExpectedMilestone=$taskExpectedMilestones[$taskIndex]
        if($taskMilestone.api -cne $taskExpectedMilestone[0] -or $taskMilestone.phase -cne $taskExpectedMilestone[1] -or $taskMilestone.flush_successes -ne $taskExpectedMilestone[2] -or $taskMilestone.head -cnotmatch '^[0-9a-f]{64}$' -or $taskMilestone.call_index -le $taskLastMilestone -or $taskMilestone.call_index -ge @($taskController.native_api_calls).Count -or $taskController.native_api_calls[$taskMilestone.call_index] -cne $taskMilestone.api){throw 'Exact before-call journal milestone differs'}
        $taskLastMilestone=$taskMilestone.call_index
    }
    if($taskJournal.milestones[2].head -cne $taskJournal.head -or @($taskJournal.io_events).Count -gt 256 -or @($taskJournal.io_events).Count -lt 4){throw 'Journal event or head bound'}
    if(@($taskExclusion.milestones).Count -ne 2 -or @($taskController.native_api_calls | Where-Object {$_ -ceq 'ResumeThread'}).Count -ne 2){throw 'Two exact owned start/resume pairs required'}
    $taskPriorContenderIndex=-1
    for($taskIndex=0;$taskIndex -lt 2;$taskIndex++){
        $taskMilestone=$taskExclusion.milestones[$taskIndex]
        $taskAPI=@('CreateProcessW','ResumeThread')[$taskIndex]
        if($taskMilestone.api -cne $taskAPI -or $taskMilestone.phase -cne 'RESERVED' -or $taskMilestone.head -cne $taskJournal.milestones[0].head -or $taskMilestone.flush_successes -ne 2 -or $taskMilestone.call_index -le $taskPriorContenderIndex -or $taskMilestone.call_index -ge $taskJournal.milestones[0].call_index -or $taskController.native_api_calls[$taskMilestone.call_index] -cne $taskAPI){throw 'Contender must precede primary start under same reserved head'}
        $taskPriorContenderIndex=$taskMilestone.call_index
    }
    $taskLastIO=-1
    foreach($taskEvent in $taskJournal.io_events){
        if($taskEvent.api -cnotin @('SetFilePointerEx','ReadFile','WriteFile','FlushFileBuffers') -or $taskEvent.result -isnot [bool] -or $taskEvent.result -cne $true -or $taskEvent.call_index -le $taskLastIO -or $taskEvent.call_index -ge @($taskController.native_api_calls).Count -or $taskController.native_api_calls[$taskEvent.call_index] -cne $taskEvent.api){throw 'Journal I/O observation differs'}
        if($taskEvent.api -ceq 'SetFilePointerEx' -and ($taskEvent.actual_offset -ne $taskEvent.requested_offset -or $taskEvent.actual_offset -lt 0 -or $taskEvent.actual_offset -gt 20666)){throw 'Journal seek differs'}
        if($taskEvent.api -cin @('ReadFile','WriteFile') -and ($taskEvent.requested_bytes -le 0 -or $taskEvent.requested_bytes -gt 65536 -or $taskEvent.actual_bytes -lt 0 -or $taskEvent.actual_bytes -gt $taskEvent.requested_bytes)){throw 'Journal transfer bound'}
        $taskLastIO=$taskEvent.call_index
    }
    $taskFlushes=@($taskJournal.io_events | Where-Object {$_.api -ceq 'FlushFileBuffers'})
    if($taskFlushes.Count -ne 5 -or @($taskController.native_api_calls | Where-Object {$_ -ceq 'FlushFileBuffers'}).Count -ne 5 -or $taskFlushes[1].call_index -ge $taskJournal.milestones[0].call_index -or $taskFlushes[2].call_index -ge $taskJournal.milestones[1].call_index -or $taskFlushes[4].call_index -ge $taskJournal.milestones[2].call_index){throw 'Observed flush ordering differs'}
    # Open once with no sharing, after controller exit and claimed handle close.
    $taskJournalStream=[IO.File]::Open($taskJournalPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
    try{
        if($taskJournalStream.Length -ne $taskJournal.journal_bytes){throw 'Closed journal size differs'}
        $taskJournalBytes=[byte[]]::new([int]$taskJournalStream.Length)
        $taskRead=0
        while($taskRead -lt $taskJournalBytes.Length){$taskN=$taskJournalStream.Read($taskJournalBytes,$taskRead,$taskJournalBytes.Length-$taskRead);if($taskN -le 0){throw 'Closed journal read incomplete'};$taskRead+=$taskN}
        if($taskJournalStream.ReadByte() -ne -1){throw 'Closed journal grew during observation'}
    }finally{$taskJournalStream.Dispose()}
    $taskJournalHex=[Convert]::ToHexString($taskJournalBytes).ToLowerInvariant()
    $taskJournalHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskJournalBytes)).ToLowerInvariant()
    if($taskJournalHex -cne $taskJournal.journal_hex -or $taskJournalHash -cne $taskJournal.journal_sha256 -or $taskJournalHex.Substring(0,12) -cne '554f5253310a' -or $taskJournalHex.Substring($taskJournalHex.Length-64) -cne $taskJournal.head){throw 'Closed journal content differs from confirmed receipt'}
    [ordered]@{path=$taskJournalPath;bytes=$taskJournalBytes.Length;sha256=$taskJournalHash;matches_controller_confirmed_bytes=$true;exclusive_postexit_read_closed=$true;power_loss_or_restart_proven=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'closed-journal-observation.json') -Encoding utf8

    if(@($taskJournal.PSObject.Properties).Count -ne 24 -or @($taskRecovery.PSObject.Properties).Count -ne 13 -or @($taskObserved.PSObject.Properties).Count -ne 21){throw 'Exact interrupted receipt fields'}
    foreach($name in @('explicit_interrupted_owner_recovery','old_owner_still_revoked','old_token_still_revoked','injected_interrupt_identity_observed','same_manager_and_service_attempt')){Assert-True $taskJournal.$name}
    Assert-False $taskJournal.fresh_process_query_after_retirement
    Assert-False $taskJournal.native_power_loss_or_restart_claim
    if($taskJournal.injected_interrupt_type -cne 'KeyboardInterrupt' -or $taskJournal.injected_stage -cne 'after_next_segment_before_return'){throw 'Fixed journal interruption'}
    Assert-Strings $taskJournal.before_recovery_phases @('INITIALIZED','RESERVED','WORKER_BOUND','QUARANTINED')
    Assert-Strings $taskRecovery.phases_before_recovery @('INITIALIZED','RESERVED','WORKER_BOUND','QUARANTINED')
    foreach($digest in @($taskJournal.before_recovery_sha256,$taskRecovery.quarantine_sha256,$taskObserved.quarantine_sha256,$taskObserved.quarantine_head,$taskObserved.close_head)){if($digest -isnot [string] -or $digest -cnotmatch '^[0-9a-f]{64}$'){throw 'Exact recovery hash'}}
    if($taskJournal.before_recovery_sha256 -cne $taskRecovery.quarantine_sha256 -or $taskJournal.before_recovery_sha256 -cne $taskObserved.quarantine_sha256 -or $taskObserved.close_head -cne $taskJournal.head){throw 'Recovery prefix/head binding'}
    # Decode exactly five bounded frames from the exclusive read above.
    $taskFrameOffset=6;$taskPrevious=('0'*64)
    $taskFrames=@();$taskFrameHeads=@();$taskFrameEnds=@()
    $taskFrameFields=@('generation','phase','physical','previous','process','reason','schema','semantics','sequence')
    for($taskFrameIndex=0;$taskFrameIndex -lt 5;$taskFrameIndex++){
        if($taskFrameOffset+4 -gt $taskJournalBytes.Length){throw 'Journal frame length missing'}
        $taskLength=[int]([uint64]$taskJournalBytes[$taskFrameOffset]*16777216+[uint64]$taskJournalBytes[$taskFrameOffset+1]*65536+[uint64]$taskJournalBytes[$taskFrameOffset+2]*256+[uint64]$taskJournalBytes[$taskFrameOffset+3])
        $taskFrameOffset+=4
        if($taskLength -le 0 -or $taskLength -gt 4096 -or $taskFrameOffset+$taskLength+32 -gt $taskJournalBytes.Length){throw 'Journal frame payload bound'}
        $taskPayload=[byte[]]::new($taskLength);[Array]::Copy($taskJournalBytes,$taskFrameOffset,$taskPayload,0,$taskLength)
        $taskFrameOffset+=$taskLength
        $taskDigest=[byte[]]::new(32);[Array]::Copy($taskJournalBytes,$taskFrameOffset,$taskDigest,0,32)
        $taskFrameOffset+=32
        $taskHead=[Convert]::ToHexString($taskDigest).ToLowerInvariant()
        if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskPayload)).ToLowerInvariant() -cne $taskHead){throw 'Journal frame digest'}
        foreach($taskByte in $taskPayload){if($taskByte -gt 127){throw 'Journal canonical ASCII'}}
        $taskPayloadText=[Text.Encoding]::ASCII.GetString($taskPayload)
        $taskFrame=ConvertFrom-Json -InputObject $taskPayloadText -Depth 16
        Assert-Strings @($taskFrame.PSObject.Properties.Name | Sort-Object -CaseSensitive) $taskFrameFields
        $taskCanonicalFrame=[ordered]@{}
        foreach($name in $taskFrameFields){$taskCanonicalFrame[$name]=$taskFrame.$name}
        if(($taskCanonicalFrame | ConvertTo-Json -Depth 8 -Compress) -cne $taskPayloadText){throw 'Journal canonical fixed record'}
        if(($taskFrame.schema -isnot [long] -and $taskFrame.schema -isnot [int]) -or $taskFrame.schema -ne 1 -or ($taskFrame.sequence -isnot [long] -and $taskFrame.sequence -isnot [int]) -or $taskFrame.sequence -ne $taskFrameIndex -or $taskFrame.phase -cne $taskPhases[$taskFrameIndex] -or $taskFrame.previous -cne $taskPrevious){throw 'Journal chain sequence/schema'}
        if(($taskFrame.physical | ConvertTo-Json -Compress) -cne ($taskJournal.physical | ConvertTo-Json -Compress) -or @($taskFrame.semantics).Count -ne 5){throw 'Journal frame identity/semantics'}
        if($taskFrameIndex -eq 0){
            if($null -ne $taskFrame.generation -or $null -ne $taskFrame.process -or $null -ne $taskFrame.reason){throw 'Initialized frame'}
        }else{
            if($taskFrame.generation -isnot [string] -or $taskFrame.generation -cnotmatch '^[0-9a-f]{64}$'){throw 'Generation binding'}
            if($taskFrameIndex -eq 1){
                if($null -ne $taskFrame.process -or $null -ne $taskFrame.reason){throw 'Reserved frame'}
            }else{
                if($taskFrame.generation -cne $taskFrames[1].generation -or ($taskFrame.semantics | ConvertTo-Json -Compress) -cne ($taskFrames[1].semantics | ConvertTo-Json -Compress) -or @($taskFrame.process).Count -ne 2){throw 'Worker frame generation/process'}
                if($taskFrameIndex -eq 2){
                    foreach($value in $taskFrame.process){if(($value -isnot [long] -and $value -isnot [int] -and $value -isnot [System.Numerics.BigInteger]) -or $value -le 0){throw 'Fixed process identity integers'}}
                    if($taskFrame.process[0] -gt 4294967295 -or $taskFrame.process[1] -gt [UInt64]::MaxValue -or $null -ne $taskFrame.reason){throw 'Worker process identity bounds'}
                }else{
                    if(($taskFrame.process | ConvertTo-Json -Compress) -cne ($taskFrames[2].process | ConvertTo-Json -Compress)){throw 'Retained process identity changed'}
                    if($taskFrameIndex -eq 3){if($taskFrame.reason -cne 'operation_failed'){throw 'Quarantine reason'}}
                    elseif($null -ne $taskFrame.reason){throw 'Clear reason'}
                }
            }
        }
        $taskFrames+=,$taskFrame;$taskFrameHeads+=,$taskHead;$taskFrameEnds+=,$taskFrameOffset;$taskPrevious=$taskHead
    }
    if($taskFrameOffset -ne $taskJournalBytes.Length -or $taskPrevious -cne $taskJournal.head -or $taskFrameHeads[3] -cne $taskObserved.quarantine_head -or $taskFrames[4].previous -cne $taskObserved.quarantine_head){throw 'Exact final head and five-frame membership'}
    $taskPrefix=[byte[]]::new($taskFrameEnds[3]);[Array]::Copy($taskJournalBytes,0,$taskPrefix,0,$taskPrefix.Length)
    $taskPrefixHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskPrefix)).ToLowerInvariant()
    if($taskPrefixHash -cne $taskObserved.quarantine_sha256){throw 'Exact recorded four-frame prefix'}
    foreach($pair in @(@(0,1),@(1,2),@(2,4))){if($taskJournal.milestones[$pair[0]].head -cne $taskFrameHeads[$pair[1]]){throw 'Decoded milestone head'}}
    if($taskEvents[1].call_index -ge $taskFlushes[3].call_index){throw 'Quarantine stop must precede its confirmed frame'}
    [ordered]@{frames=5;phases=$taskPhases;frame_heads=$taskFrameHeads;quarantine_prefix_bytes=$taskPrefix.Length;quarantine_prefix_sha256=$taskPrefixHash;pre_interruption_revision=$taskObserved.pre_interruption_revision;post_quarantine_revision=$taskObserved.post_quarantine_revision;completion_revision=$taskObserved.token_revision_at_completion;primary_native_exit=1;primary_job_active_processes=0;process_job_observed_before_individual_close=$true;final_child_state_claimed=$false;ordinary_parent_guard_claim_available=$false;native_crash_restart_or_power_loss_claim=$false} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRun 'interrupted-journal-observation.json') -Encoding utf8
    if($taskEvents[-1].call_index -ge $taskFlushes[4].call_index -or $taskFlushes[3].call_index -ge $taskEvents[2].call_index){throw 'Retirement must follow quarantine and precede clear'}
}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}
$taskStdoutBytes=(Get-Item -LiteralPath $taskStdout).Length
$taskStderrBytes=(Get-Item -LiteralPath $taskStderr).Length
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskValid -or $taskStdoutBytes -ne 0 -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{case=$taskCase;controller_native_exit=$taskNativeExit;expected_primary_retained_exit=1;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskValid;receipt_error_type=$taskReceiptError;stdout_bytes=$taskStdoutBytes;stderr_bytes=$taskStderrBytes;operation_mode=$taskMode;scope='Generated interrupted owner; retained parent retirement only';final_child_state_claimed=$false;ordinary_parent_guard_claim_available=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
