# Passive review of fixed text and recorded generated receipts only. No candidate is loaded.
$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$run=Join-Path $repo '_scratch\windows-retired-owner-recovery01'
$proposal=Join-Path $repo '_scratch\windows-retired-owner-recovery-proposal01'
$utf8=[Text.UTF8Encoding]::new($false,$true)
$bindings=[Collections.Generic.List[object]]::new()
function Require($value,[string]$message){if(-not $value){throw $message}}
function Sha([byte[]]$raw){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()}
function Text([string]$path){
    $item=Get-Item -LiteralPath $path -Force
    Require (-not $item.PSIsContainer -and $item.Length -le 1048576 -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Bounded ordinary text required'
    Require ([IO.Path]::GetExtension($path) -cin @('.json','.ps1','.py','.md')) 'Text extension required'
    $raw=[IO.File]::ReadAllBytes($path)
    Require ($raw.Length -eq $item.Length -and -not ($raw -contains 0)) 'Text bytes changed or NUL'
    $value=$utf8.GetString($raw)
    $bindings.Add([ordered]@{path=$path;bytes=$raw.Length;sha256=(Sha $raw)})
    return $value
}
function Read([string]$name){Text (Join-Path $run $name) | ConvertFrom-Json -AsHashtable}
function Same($left,$right){($left | ConvertTo-Json -Depth 15 -Compress) -ceq ($right | ConvertTo-Json -Depth 15 -Compress)}
function TrueFields($obj,[string[]]$names){foreach($name in $names){Require ($obj[$name] -is [bool] -and $obj[$name]) ('True field: '+$name)}}
$sourceNames=@('reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py','durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py','win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py','generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_adapter_flow.py','generated_journal_setup.py','generated_writer_exclusion.py','dummy_bootstrap.py')
$mapText=Text (Join-Path $proposal 'SOURCE-INPUTS.json')
Require ($bindings[-1].sha256 -ceq '9d988684ca8dfe487521f7d711ec67855393922d53ffe3cce3e13a2c660e34c3') 'Reviewed native map'
$map=$mapText | ConvertFrom-Json -AsHashtable
Require ($map.source_paths.Count -eq 18 -and $map.source_sha256.Count -eq 18 -and $map.native_bindings.Count -eq 9) 'Native map membership'
$before=Read 'before.json'; $after=Read 'after.json'; $outcome=Read 'exit.json'
$native=Read 'native-exit.json'; $closed=Read 'closed-journal-observation.json'
Require ($outcome.outer_exit -eq 0 -and $outcome.controller_native_exit -eq 0 -and $outcome.expected_child_native_exit -eq 0) 'Actual native exits'
TrueFields $outcome @('inputs_unchanged','receipt_valid')
Require ($null -eq $outcome.receipt_error_type -and $outcome.operation_mode -ceq 'cancel' -and $outcome.stdout_bytes -eq 0 -and $outcome.stderr_bytes -eq 0) 'Outer receipt'
Require ($native.schema -ceq 'uoink.native-exit.v1' -and $native.child_returned -eq $true -and $native.native_exit -eq 0 -and $native.Count -eq 3) 'Immediate native exit'
TrueFields $after @('inputs_unchanged')
Require ($before.sources.Count -eq 18 -and $before.controls.Count -eq 3 -and $after.source_and_controls.Count -eq 21) 'Source/control membership'
$controlNames=@('ROOT-ADMISSION.json','SOURCE-INPUTS.json','run_retired_recovery01.ps1')
$controlLeaves=@('ROOT-ADMISSION-cancel.json','SOURCE-INPUTS.json','run_retired_recovery01.ps1')
$controlHashes=@('5b603707a9efd1736d9e6bfa07b45283c93cdad896d12696d6b21bbbe8c8bfc0','9d988684ca8dfe487521f7d711ec67855393922d53ffe3cce3e13a2c660e34c3','75a9baea9307658a99217816f7653adfdbb9d0df44286a5b244ea5d3cad43444')
$bound=@($before.sources)+@($before.controls)
for($i=0;$i -lt 21;$i++){
    $row=$bound[$i];$record=$after.source_and_controls[$i]
    if($i -lt 18){$name=$sourceNames[$i];$leaf=$name;$expected=$map.source_sha256[$name];Require ($map.source_paths[$name] -ceq (Join-Path $proposal $leaf)) 'Fixed source path'}
    else{$j=$i-18;$name=$controlNames[$j];$leaf=$controlLeaves[$j];$expected=$controlHashes[$j]}
    Require ($row.name -ceq $name -and $row.path -ceq (Join-Path $proposal $leaf) -and $row.sha256 -ceq $expected) 'Before binding'
    Require ($record.name -ceq $name -and $record.before_sha256 -ceq $expected -and $record.source_after_sha256 -ceq $expected -and $record.copy_after_sha256 -ceq $expected) 'After binding'
    $null=Text (Join-Path $proposal $leaf);Require ($bindings[-1].sha256 -ceq $expected) 'Current source text'
    $null=Text (Join-Path $run $name);Require ($bindings[-1].sha256 -ceq $expected) 'Current copied text'
}
Require ($before.native_inputs.Count -eq 9 -and $before.fixtures.Count -eq 5 -and $after.support_and_fixtures.Count -eq 14) 'Support/fixture metadata membership'
$meta=@($before.native_inputs)+@($before.fixtures)
for($i=0;$i -lt 14;$i++){
    $b=$meta[$i];$a=$after.support_and_fixtures[$i]
    Require ($a.path -ceq $b.path -and $a.bytes -eq $b.bytes -and $a.before_sha256 -ceq $b.sha256 -and $a.after_sha256 -ceq $b.sha256) 'Recorded metadata binding'
    if($i -lt 9){Require ($map.native_bindings.Contains($b.path) -and $map.native_bindings[$b.path].bytes -eq $b.bytes -and $map.native_bindings[$b.path].sha256 -ceq $b.sha256) 'Support metadata versus pinned map'}
}
# Support and fixture paths are compared as strings only, never used by Text/Get-Item.
$roles=[ordered]@{}; $stats=[ordered]@{}
$apis=@('CreateFileW','GetFinalPathNameByHandleW','GetFileInformationByHandleEx','CloseHandle','GetCurrentProcess','DuplicateHandle','CreateJobObjectW','SetInformationJobObject','QueryInformationJobObject','AssignProcessToJobObject','TerminateJobObject','TerminateProcess','WaitForSingleObject','GetProcessTimes','ResumeThread','InitializeProcThreadAttributeList','UpdateProcThreadAttribute','DeleteProcThreadAttributeList','CreateProcessW','CreateNamedPipeW','ConnectNamedPipe','CreateEventW','ReadFile','WriteFile','GetOverlappedResult','CancelIoEx','GetFileType','GetHandleInformation','SetHandleInformation','GetExitCodeProcess','GetModuleFileNameW','SetFilePointerEx','FlushFileBuffers')
foreach($role in @('controller','child','contender')){
    $r=Read ($role+'-result.json');$roles[$role]=$r
    Require ($r.schema -ceq 'uoink.generated-windows-retired-owner-recovery.v1' -and $r.role -ceq $role -and $r.case -ceq 'positive' -and $r.operation_mode -ceq 'cancel') 'Role scope'
    TrueFields $r @('guard_valid','fixed_dispatch_valid','kernel32_path_verified')
    Require ($null -eq $r.error_type -and $null -eq $r.directory_refusal -and $r.native_exit_planned -eq 0) 'Role result error'
    foreach($list in @('guard_denials','model_imports','reserved_cleanup_calls','reserved_cleanup_wait_caps')){Require ($r[$list].Count -eq 0) ('Nonempty '+$list)}
    Require ($r.work_budget_closed -eq $false -and $r.model_calls -eq 0 -and $r.pending_pipe_operations -eq 0 -and $r.fixed_dispatch_invalid_contexts -eq 0) 'Role remaining work/guard failures'
    Require ($r.metadata_traps -eq 12 -and $r.registry_traps -eq 25 -and $r.fixed_dispatch_function_count -eq 33) 'Fixed API guards'
    $cast=if($role -ceq 'controller'){2}else{0}
    Require ($r.fixed_attribute_cast_calls -eq $cast -and $r.fixed_dispatch_completed_calls -eq $r.fixed_dispatch_audit_events -and $r.fixed_dispatch_completed_calls -eq ($r.native_api_calls.Count+34+$cast)) 'Exact dispatch accounting'
    foreach($api in $r.native_api_calls){Require ($api -cin $apis) 'API outside fixed 33'}
    Require ($r.source_sha256.Count -eq 18 -and $r.adapter_state.Count -eq 5) 'Role source/adapter membership'
    foreach($name in $sourceNames){Require ($r.source_sha256[$name] -ceq $map.source_sha256[$name]) 'Role source binding'}
    TrueFields $r.adapter_state @('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')
    $stats[$role]=[ordered]@{calls=$r.native_api_calls.Count;dispatch=$r.fixed_dispatch_completed_calls;elapsed_seconds=$r.elapsed_seconds}
}
$c=$roles.controller.result;$child=$roles.child.result;$contender=$roles.contender.result;$j=$c.durable_journal;$recovery=$c.retired_owner_recovery
$events=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')
Require ((Same $c.operation_events $events) -and (Same $child.operation_events $events) -and $c.segments.Count -eq 1 -and $child.produced_segments -eq 1 -and $c.cursor_state -ceq 'cancelled' -and $child.cursor_state -ceq 'cancelled') 'One segment then cancellation'
TrueFields $c @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit','adapter_owned_cleanup','retained_facade_and_stream_refused','read_set_released','pipe_retired','parent_guards_held_through_exit')
Require ($c.lifecycle_phase -eq 8 -and $c.binding_calls -eq 1 -and $child.child_flow_return -eq 0) 'Final lifecycle/child'
foreach($exit in @($c.exit_observation,$roles.controller.writer_exclusion.exit_observation)){Require ($exit.Count -eq 3 -and $exit.child_native_exit -eq 0 -and $exit.process_wait_observed -eq $true -and $exit.job_active_processes -eq 0) 'Retained process/job observation'}
TrueFields $roles.controller.writer_exclusion @('completed','guard_released','worker_handles_closed','inherited_control_handle_absent','primary_journal_held_through_contender_exit')
Require ($roles.controller.writer_exclusion.worker_unconfirmed -eq $false -and $null -eq $roles.controller.writer_exclusion.failure_type) 'Contender retirement'
TrueFields $child.adoption @('read_set_released')
Require ($child.adoption.read_set_unconfirmed -eq $false -and $child.adoption.handles_closed.Count -eq 5 -and @($child.adoption.handles_closed | Where-Object {$_ -ne $true}).Count -eq 0) 'Child adopted handle retirement'
$cancel=$c.cancellation_journal
Require ($cancel.phase_before -ceq 'WORKER_BOUND' -and $cancel.phase_after -ceq 'WORKER_BOUND' -and $cancel.confirmed_before_sha256 -ceq $cancel.confirmed_after_sha256) 'No early clear'
TrueFields $cancel @('same_token_and_handle','gate_held_before_stop','journal_open_before_stop','clear_deferred_until_adapter_finally')
Require ($recovery.Count -eq 12 -and $recovery.interruption_type -ceq 'KeyboardInterrupt' -and $recovery.stage -ceq 'after_teardown_before_clear' -and $recovery.native_interrupt_crash_or_restart_claim -eq $false) 'Fixed Python interruption scope'
TrueFields $recovery @('interruption_identity_match','ordinary_completion_refused','manager_reconciliation_confirmed','owner_still_revoked','token_still_revoked','same_owner_and_record','journal_open_until_recovery_clear')
$phases=@('INITIALIZED','RESERVED','WORKER_BOUND','CLEARED')
Require ((Same $j.phases $phases) -and (Same $recovery.phases_before_recovery $phases[0..2]) -and (Same $j.before_clear_phases $phases[0..2]) -and $j.flush_successes -eq 4) 'Recovery phases/flush count'
Require ($recovery.before_recovery_sha256 -ceq $j.before_clear_sha256 -and $j.before_clear_sha256 -ceq $cancel.confirmed_before_sha256) 'Same before-clear bytes'
TrueFields $j @('creation_handle_transferred_without_close','journal_handle_closed','directory_guards_retired','explicit_retired_owner_recovery','old_owner_still_revoked','old_token_still_revoked','injected_interrupt_identity_observed','same_manager_and_service_attempt')
Require ($j.injected_interrupt_type -ceq 'KeyboardInterrupt' -and $j.injected_stage -ceq 'after_teardown_before_clear' -and $j.native_power_loss_or_restart_claim -eq $false -and $j.fresh_process_query_after_retirement -eq $false -and $j.os_interrupt_or_crash_claim -eq $false) 'Journal limits'
Require ($j.journal_hex -cmatch '^[0-9a-f]+$' -and $j.journal_hex.Length -le 40000 -and $j.journal_hex.Length % 2 -eq 0) 'Recorded hex cap'
$raw=[Convert]::FromHexString($j.journal_hex)
Require ([Text.Encoding]::ASCII.GetString($raw,0,6) -ceq ("UORS1"+[char]10) -and $raw.Length -eq $j.journal_bytes -and (Sha $raw) -ceq $j.journal_sha256) 'Recorded frame magic/hash'
$frames=@();$ends=@();$heads=@();$offset=6;$previous='0'*64
for($i=0;$i -lt 4;$i++){
    Require ($offset+4 -le $raw.Length) 'Length prefix'
    $length=([long]$raw[$offset]*16777216)+([long]$raw[$offset+1]*65536)+([long]$raw[$offset+2]*256)+$raw[$offset+3];$offset+=4
    Require ($length -gt 0 -and $length -le 4096 -and $offset+$length+32 -le $raw.Length) 'Frame bound'
    $payload=[byte[]]$raw[$offset..($offset+$length-1)];$offset+=$length
    $head=[Convert]::ToHexString([byte[]]$raw[$offset..($offset+31)]).ToLowerInvariant();$offset+=32
    Require ((Sha $payload) -ceq $head) 'Frame checksum'
    $frame=$utf8.GetString($payload) | ConvertFrom-Json -AsHashtable
    Require ($frame.Count -eq 9 -and $frame.schema -eq 1 -and $frame.sequence -eq $i -and $frame.phase -ceq $phases[$i] -and $frame.previous -ceq $previous -and (Same $frame.physical $j.physical)) 'Frame identity/order'
    $frames+=,$frame;$ends+=,$offset;$heads+=,$head;$previous=$head
}
Require ($offset -eq $raw.Length -and $previous -ceq $j.head -and (Sha ([byte[]]$raw[0..($ends[2]-1)])) -ceq $recovery.before_recovery_sha256) 'Complete four-frame and before-clear prefix'
Require ($null -eq $frames[0].generation -and $null -eq $frames[0].process -and $null -eq $frames[1].process -and $null -ne $frames[2].process -and (Same $frames[2].process $frames[3].process)) 'Generation/process transitions'
for($i=1;$i -lt 4;$i++){Require ($frames[$i].generation -ceq $frames[1].generation -and (Same $frames[$i].semantics $frames[0].semantics)) 'Same generation/semantics'}
Require ($closed.bytes -eq $raw.Length -and $closed.sha256 -ceq (Sha $raw) -and $closed.power_loss_or_restart_proven -eq $false) 'Recorded exclusive postexit identity'
TrueFields $closed @('matches_controller_confirmed_bytes','exclusive_postexit_read_closed')
Require ($j.milestones.Count -eq 3) 'Primary milestone count'
for($i=0;$i -lt 3;$i++){
    $m=$j.milestones[$i];$api=@('CreateProcessW','ResumeThread','CloseHandle')[$i]
    Require ($m.api -ceq $api -and $m.phase -ceq $phases[$i+1] -and $m.head -ceq $heads[$i+1] -and $m.flush_successes -eq $i+2 -and $roles.controller.native_api_calls[$m.call_index] -ceq $api) 'Milestone versus recorded API index'
}
$writes=@();$flushes=@();$last=-1
foreach($io in $j.io_events){
    Require ($io.call_index -gt $last -and $roles.controller.native_api_calls[$io.call_index] -ceq $io.api -and $io.result -eq $true) 'Ordered journal API results';$last=$io.call_index
    if($io.api -ceq 'WriteFile'){Require ($io.actual_bytes -eq $io.requested_bytes) 'Complete write';$writes+=,$io}
    elseif($io.api -ceq 'FlushFileBuffers'){$flushes+=,$io}
    elseif($io.api -ceq 'SetFilePointerEx'){Require ($io.actual_offset -eq $io.requested_offset) 'Exact seek'}
    else{Require ($io.api -ceq 'ReadFile' -and $io.actual_bytes -ge 0 -and $io.actual_bytes -le $io.requested_bytes) 'Bounded read'}
}
Require ($writes.Count -eq 4 -and $flushes.Count -eq 4) 'Four complete writes/flushes'
$start=0
for($i=0;$i -lt 4;$i++){
    Require ($writes[$i].actual_bytes -eq $ends[$i]-$start -and $writes[$i].call_index -lt $flushes[$i].call_index) 'Per-frame append then flush';$start=$ends[$i]
    if($i -lt 3){Require ($flushes[$i].call_index -lt $writes[$i+1].call_index) 'Confirmed ordering'}
}
Require ($flushes[1].call_index -lt $j.milestones[0].call_index -and $flushes[2].call_index -lt $j.milestones[1].call_index -and $flushes[3].call_index -lt $j.milestones[2].call_index) 'Flush before primary create/resume/close'
Require ($contender.status -ceq 'sharing_refused' -and $contender.winerror -eq 32 -and $contender.attempt_count -eq 1 -and $contender.valid_journal_handle_returned -eq $false -and $contender.journal_content_reads -eq 0 -and $contender.journal_writes -eq 0 -and (Same $contender.physical $j.physical) -and $contender.journal_path -ceq $j.journal_path) 'Same physical writer refusal'
$actual=Text (Join-Path $repo '_scratch\RETIRED-RECOVERY-NATIVE-ACTUAL.json') | ConvertFrom-Json -AsHashtable
Require ($actual.chunk_id -ceq 'e97a44' -and $actual.exit_code -eq 0 -and $actual.output -ceq '') 'Actual outer native result'
$rootActual=Text (Join-Path $repo '_scratch\RETIRED-RECOVERY-NATIVE-ROOT-CHECK-ACTUAL.json') | ConvertFrom-Json -AsHashtable
Require ($rootActual.chunk_id -ceq '5214fa' -and $rootActual.exit_code -eq 0) 'Root passive result'
$rootResult=$rootActual.output | ConvertFrom-Json -AsHashtable
Require ($rootResult.journal_sha256 -ceq (Sha $raw) -and $rootResult.before_recovery_sha256 -ceq $recovery.before_recovery_sha256) 'Independent root agreement'
# Re-read only already-selected fixed text inputs and verify unchanged bytes.
foreach($binding in $bindings.ToArray()){Require ((Sha ([IO.File]::ReadAllBytes($binding.path))) -ceq $binding.sha256) 'Review input changed'}
[ordered]@{status='PASS_RECORDED_GENERATED_RETIRED_OWNER_RECOVERY';candidate_executions=0;physical_journal_fixture_support_reads=0;source_control_pairs=21;roles=3;api_bindings=33;metadata_traps_per_role=12;registry_traps_per_role=25;phases=$phases;frame_ends=$ends;before_clear_sha256=$recovery.before_recovery_sha256;journal_sha256=(Sha $raw);journal_bytes=$raw.Length;flush_call_indices=@($flushes.call_index);primary_milestones=$j.milestones;revoked_owner_and_token_preserved=$true;recorded_retirement_confirmed=$true;stats=$stats;input_texts=$bindings;unchanged_inputs=$true;model_restart_runtime_acceptance=$false} | ConvertTo-Json -Depth 8
