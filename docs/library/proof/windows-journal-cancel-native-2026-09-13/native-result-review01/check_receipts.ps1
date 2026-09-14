$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$run='_scratch/windows-journal-cancel01'
$proposal='_scratch/windows-journal-cancel-proposal01'
$sourceNames=@('reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py','durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py','win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py','generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_adapter_flow.py','generated_journal_setup.py','generated_writer_exclusion.py','dummy_bootstrap.py')
$allowed=@($sourceNames | ForEach-Object {$run+'/'+$_;$proposal+'/'+$_})+@(
    ($run+'/controller-result.json'),($run+'/child-result.json'),($run+'/contender-result.json'),
    ($run+'/exit.json'),($run+'/native-exit.json'),($run+'/closed-journal-observation.json'),
    ($run+'/before.json'),($run+'/after.json'),($run+'/ROOT-ADMISSION.json'),
    ($run+'/SOURCE-INPUTS.json'),($run+'/run_journal_cancel01.ps1'),
    ($run+'/controller-stdout.log'),($run+'/controller-stderr.log'),
    ($proposal+'/ROOT-ADMISSION-cancel.json'),($proposal+'/SOURCE-INPUTS.json'),($proposal+'/run_journal_cancel01.ps1'),
    '_scratch/WINDOWS-JOURNAL-CANCEL01-ACTUAL.json','_scratch/WINDOWS-JOURNAL-CANCEL01-ADMISSION-ACTUAL.json'
)
$utf8=[Text.UTF8Encoding]::new($false,$true);$reads=[ordered]@{}
function Need($value,[string]$why){if(-not $value){throw $why}}
function Yes($value,[string]$why){Need ($value -is [bool] -and $value -eq $true) $why}
function No($value,[string]$why){Need ($value -is [bool] -and $value -eq $false) $why}
function Same($a,$b,[string]$why){Need (($a | ConvertTo-Json -Depth 15 -Compress) -ceq ($b | ConvertTo-Json -Depth 15 -Compress)) $why}
function ReadText([string]$relative){
    Need ($relative -cin $allowed) 'Outside fixed text-read set'
    $path=Join-Path $repo $relative
    $before=Get-Item -LiteralPath $path -Force
    Need (-not $before.PSIsContainer -and $before.Length -le 1048576 -and ($before.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Text file/cap/reparse'
    $dir=[IO.DirectoryInfo]::new($before.DirectoryName)
    while($null -ne $dir){$item=Get-Item -LiteralPath $dir.FullName -Force;Need ($item.PSIsContainer -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Text ancestor';$dir=$dir.Parent}
    $raw=[IO.File]::ReadAllBytes($path)
    Need (-not ($raw -contains 0)) 'NUL text'
    $text=$utf8.GetString($raw)
    $after=Get-Item -LiteralPath $path -Force
    Need ($after.Length -eq $before.Length -and $after.LastWriteTimeUtc.Ticks -eq $before.LastWriteTimeUtc.Ticks) 'Text changed while read'
    $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
    if($reads.Contains($relative)){Need ($reads[$relative].sha256 -ceq $hash) 'Repeated text changed'}
    $reads[$relative]=[ordered]@{source=$relative;bytes=$raw.LongLength;sha256=$hash}
    return $text.TrimStart([char]0xfeff)
}
function Json([string]$relative){return (ReadText $relative | ConvertFrom-Json -AsHashtable)}
$c=Json ($run+'/controller-result.json');$child=Json ($run+'/child-result.json');$contender=Json ($run+'/contender-result.json')
$exit=Json ($run+'/exit.json');$native=Json ($run+'/native-exit.json');$closed=Json ($run+'/closed-journal-observation.json')
$before=Json ($run+'/before.json');$after=Json ($run+'/after.json')
$outer=Json '_scratch/WINDOWS-JOURNAL-CANCEL01-ACTUAL.json';$admissionActual=Json '_scratch/WINDOWS-JOURNAL-CANCEL01-ADMISSION-ACTUAL.json'
Need ($outer.chunk_id -ceq '793018' -and $outer.exit_code -eq 0 -and $admissionActual.chunk_id -ceq 'a3cc13' -and $admissionActual.exit_code -eq 0) 'Actual outer outcomes'
Need ($exit.controller_native_exit -eq 0 -and $exit.expected_child_native_exit -eq 0 -and $exit.outer_exit -eq 0 -and $null -eq $exit.receipt_error_type) 'Recorded exits'
Yes $exit.receipt_valid 'Launcher receipt verdict';Yes $exit.inputs_unchanged 'Launcher inputs';Yes $native.child_returned 'Controller returned'
Need ($native.native_exit -eq 0 -and $exit.stdout_bytes -eq 0 -and $exit.stderr_bytes -eq 0 -and $exit.operation_mode -ceq 'cancel') 'Raw native/log observations'
Need ((ReadText ($run+'/controller-stdout.log')).Length -eq 0 -and (ReadText ($run+'/controller-stderr.log')).Length -eq 0) 'Current empty logs'
$map=Json ($proposal+'/SOURCE-INPUTS.json')
Need ($reads[$proposal+'/SOURCE-INPUTS.json'].sha256 -ceq 'f5e1b8b4d282c28c7ac12aad05b4e2466340769215574948682b69633e4fa4b3') 'Reviewed source map'
Need ($map.source_paths.Count -eq 18 -and $map.source_sha256.Count -eq 18 -and $before.sources.Count -eq 18 -and $before.controls.Count -eq 3 -and $after.source_and_controls.Count -eq 21) 'Source/control counts'
$controlNames=@('ROOT-ADMISSION.json','SOURCE-INPUTS.json','run_journal_cancel01.ps1')
foreach($name in @($sourceNames)+$controlNames){
    $originalName=if($name -ceq 'ROOT-ADMISSION.json'){'ROOT-ADMISSION-cancel.json'}else{$name}
    $source=$proposal+'/'+$originalName;$copy=$run+'/'+$name
    $null=ReadText $source;$null=ReadText $copy
    $b=@(@($before.sources)+@($before.controls) | Where-Object {$_.name -ceq $name})
    $a=@($after.source_and_controls | Where-Object {$_.name -ceq $name})
    Need ($b.Count -eq 1 -and $a.Count -eq 1 -and $b[0].path -ceq (Join-Path $repo $source)) 'Exact source/control membership'
    $hash=$reads[$source].sha256
    Need ($reads[$copy].sha256 -ceq $hash -and $b[0].sha256 -ceq $hash -and $a[0].before_sha256 -ceq $hash -and $a[0].source_after_sha256 -ceq $hash -and $a[0].copy_after_sha256 -ceq $hash) 'Source/control before/copy/after'
    if($name -cin $sourceNames){Need ($map.source_sha256[$name] -ceq $hash -and $map.source_paths[$name] -ceq (Join-Path $repo $source)) 'Source map equality'}
}
Need ($reads[$proposal+'/run_journal_cancel01.ps1'].sha256 -ceq '70ab9cc3879ed792db0f8deaec4fd343f6a96438811bad9e37977ae510fa11d6') 'Reviewed launcher'
Need ($reads[$proposal+'/ROOT-ADMISSION-cancel.json'].sha256 -ceq '89c44b6611f4145f5f90c739fb700305a7454433f2cb463a62549a8475a127bb') 'Exact admission'
$admission=Json ($run+'/ROOT-ADMISSION.json')
Yes $admission.root_reviewed 'Root reviewed';Yes $admission.native_execution_admitted 'Native admission'
Need ($admission.scope -ceq 'generated-windows-journal-cancel-only' -and $admission.case -ceq 'positive' -and $admission.operation_mode -ceq 'cancel' -and $admission.run_path -ceq (Join-Path $repo $run)) 'Exact admission scope'
Need ($admission.source_inputs_sha256 -ceq $reads[$proposal+'/SOURCE-INPUTS.json'].sha256 -and $admission.launcher_sha256 -ceq $reads[$proposal+'/run_journal_cancel01.ps1'].sha256) 'Admission controls'
$roleSummaries=@()
foreach($pair in @(@('controller',$c,2),@('child',$child,0),@('contender',$contender,0))){
    $r=$pair[1]
    Need ($r.role -ceq $pair[0] -and $r.schema -ceq 'uoink.generated-windows-journal-cancel.v1' -and $r.case -ceq 'positive' -and $r.operation_mode -ceq 'cancel' -and $null -eq $r.error_type -and $null -eq $r.directory_refusal) 'Role identity/error'
    Yes $r.guard_valid 'Guard';Yes $r.fixed_dispatch_valid 'Dispatch';Yes $r.kernel32_path_verified 'Recorded kernel path'
    Need ($r.native_exit_planned -eq 0 -and $r.guard_denials.Count -eq 0 -and $r.pending_pipe_operations -eq 0 -and $r.metadata_traps -eq 12 -and $r.registry_traps -eq 25 -and $r.model_calls -eq 0 -and $r.model_imports.Count -eq 0) 'Guard/counter membership'
    No $r.work_budget_closed 'Work budget';Need ($r.reserved_cleanup_calls.Count -eq 0 -and $r.reserved_cleanup_wait_caps.Count -eq 0) 'Reserved cleanup unused'
    Need ($r.fixed_dispatch_function_count -eq 33 -and $r.fixed_dispatch_invalid_contexts -eq 0 -and $r.fixed_attribute_cast_calls -eq $pair[2] -and $r.fixed_dispatch_completed_calls -eq (34+$r.native_api_calls.Count+$pair[2]) -and $r.fixed_dispatch_audit_events -eq $r.fixed_dispatch_completed_calls) 'Dispatch accounting'
    Need ($r.source_sha256.Count -eq 18) 'Role source membership'
    foreach($name in $sourceNames){Need ($r.source_sha256[$name] -ceq $map.source_sha256[$name]) 'Role source pin'}
    Need ($r.adapter_state.Count -eq 5) 'Adapter state fields'
    foreach($value in $r.adapter_state.Values){Yes $value 'Restored closed adapter state'}
    $roleSummaries += [ordered]@{role=$r.role;elapsed_seconds=$r.elapsed_seconds;guard_valid=$r.guard_valid;dispatches=$r.fixed_dispatch_completed_calls;native_api_calls=$r.native_api_calls.Count;pending_io=$r.pending_pipe_operations}
}
$result=$c.result
$events=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')
Same $result.operation_events $events 'Controller four actions';Same $child.result.operation_events $events 'Child four actions'
Need ($result.cursor_state -ceq 'cancelled' -and $child.result.cursor_state -ceq 'cancelled' -and $child.result.produced_segments -eq 1 -and $result.segments.Count -eq 1 -and $result.cursor_start.produced_segments -eq 0 -and $child.result.cursor_start.produced_segments -eq 0) 'One lazy generated segment'
$segment=$result.segments[0]
Need ($segment.Count -eq 4 -and $segment.start -eq 0.0 -and $segment.end -eq 0.5 -and $segment.text -ceq 'Uoink generated adoption fixture: config.json. No model data.' -and $segment.words.Count -eq 0) 'Exact generated segment'
$cancellation=$result.cancellation_journal
Need ($cancellation.Count -eq 8 -and $cancellation.phase_before -ceq 'WORKER_BOUND' -and $cancellation.phase_after -ceq 'WORKER_BOUND' -and $cancellation.confirmed_before_sha256 -cmatch '^[0-9a-f]{64}$' -and $cancellation.confirmed_before_sha256 -ceq $cancellation.confirmed_after_sha256) 'Bound journal cancellation'
foreach($name in @('same_token_and_handle','gate_held_before_stop','journal_open_before_stop','clear_deferred_until_adapter_finally')){Yes $cancellation[$name] 'Same held lifetime before adapter stop'}
Need ($result.actual_adapter_context -ceq 'faster_whisper_session' -and $result.lifecycle_phase -eq 8 -and $result.binding_calls -eq 1 -and $result.model_calls -eq 0) 'Actual adapter result'
foreach($name in @('actual_factory_and_permit','adapter_owned_cleanup','retained_facade_and_stream_refused','read_set_released','pipe_retired','parent_guards_held_through_exit','adapter_globals_restored','real_resolver_approval_unchanged_none')){Yes $result[$name] 'Adapter cleanup invariant'}
foreach($observation in @($result.exit_observation,$c.writer_exclusion.exit_observation)){Need ($observation.child_native_exit -eq 0 -and $observation.job_active_processes -eq 0) 'Owned child/job exit';Yes $observation.process_wait_observed 'Owned process wait'}
Need ($result.adapter_start_ack.Count -eq 3 -and $child.result.adapter_start_ack.Count -eq 3) 'Startup ack fields'
foreach($name in @('action','policy_sha256','model_calls')){Need ($result.adapter_start_ack.Contains($name) -and $child.result.adapter_start_ack.Contains($name) -and $result.adapter_start_ack[$name] -ceq $child.result.adapter_start_ack[$name]) 'Startup ack identity'}
foreach($start in @($result.adapter_start,$child.result.adapter_start)){Yes $start.generated_only 'Generated startup';Yes $start.local_files_only 'Offline startup';No $start.constructor_called 'No constructor';No $start.real_runtime_approved 'Runtime remains closed'}
$journal=$result.durable_journal
Same $journal.phases @('INITIALIZED','RESERVED','WORKER_BOUND','CLEARED') 'Four journal phases'
Need ($journal.flush_successes -eq 4 -and $journal.milestones.Count -eq 3 -and $journal.journal_bytes -eq 2118) 'Journal counts'
foreach($name in @('creation_handle_transferred_without_close','journal_handle_closed','directory_guards_retired')){Yes $journal[$name] 'Journal retirement'}
No $journal.native_power_loss_or_restart_claim 'No power-loss claim'
$expectedMilestones=@(@('CreateProcessW','RESERVED',2),@('ResumeThread','WORKER_BOUND',3),@('CloseHandle','CLEARED',4))
$last=-1
for($i=0;$i -lt 3;$i++){
    $m=$journal.milestones[$i];$e=$expectedMilestones[$i]
    Need ($m.api -ceq $e[0] -and $m.phase -ceq $e[1] -and $m.flush_successes -eq $e[2] -and $m.call_index -gt $last -and $m.call_index -lt $c.native_api_calls.Count -and $c.native_api_calls[$m.call_index] -ceq $m.api) 'Journal milestone order'
    $last=$m.call_index
}
$flushes=@($journal.io_events | Where-Object {$_.api -ceq 'FlushFileBuffers'})
Need ($flushes.Count -eq 4 -and @($c.native_api_calls | Where-Object {$_ -ceq 'FlushFileBuffers'}).Count -eq 4) 'Four actual flush events'
$last=-1
foreach($event in $journal.io_events){Yes $event.result 'Journal I/O success';Need ($event.call_index -gt $last -and $event.call_index -lt $c.native_api_calls.Count -and $c.native_api_calls[$event.call_index] -ceq $event.api) 'Journal I/O call binding';$last=$event.call_index}
Need ($flushes[1].call_index -lt $journal.milestones[0].call_index -and $flushes[2].call_index -lt $journal.milestones[1].call_index -and $flushes[3].call_index -lt $journal.milestones[2].call_index) 'Flush before publication/close'
Need ($closed.bytes -eq 2118 -and $closed.path -ceq $journal.journal_path -and $closed.sha256 -ceq $journal.journal_sha256 -and $closed.sha256 -ceq '11dbc95a56ae1397fb0663113f8ba606e461f8253e00600608ca9e81381f9fb8') 'Retained exclusive postexit comparison'
Yes $closed.matches_controller_confirmed_bytes 'Retained closed comparison';Yes $closed.exclusive_postexit_read_closed 'Retained exclusive close';No $closed.power_loss_or_restart_proven 'No restart proof'
Need ($contender.result.status -ceq 'sharing_refused' -and $contender.result.attempt_count -eq 1 -and $contender.result.winerror -eq 32 -and $contender.result.journal_content_reads -eq 0 -and $contender.result.journal_writes -eq 0) 'Contender exclusion'
Yes $c.writer_exclusion.completed 'Contender completion';Yes $c.writer_exclusion.primary_journal_held_through_contender_exit 'Primary lifetime';Yes $c.writer_exclusion.worker_handles_closed 'Contender handles';No $c.writer_exclusion.worker_unconfirmed 'Contender confirmed'
Same $contender.result.physical $journal.physical 'Shared physical journal target'
Need ($before.native_inputs.Count -eq 9 -and $before.fixtures.Count -eq 5 -and $after.support_and_fixtures.Count -eq 14 -and $map.native_bindings.Count -eq 9) 'Retained support/fixture membership'
foreach($row in @($before.native_inputs)+@($before.fixtures)){
    $a=@($after.support_and_fixtures | Where-Object {$_.path -ceq $row.path})
    Need ($a.Count -eq 1 -and $a[0].bytes -eq $row.bytes -and $a[0].before_sha256 -ceq $row.sha256 -and $a[0].after_sha256 -ceq $row.sha256) 'Retained support/fixture unchanged'
}
foreach($row in $before.native_inputs){Need ($map.native_bindings.Contains($row.path) -and $map.native_bindings[$row.path].bytes -eq $row.bytes -and $map.native_bindings[$row.path].sha256 -ceq $row.sha256) 'Support metadata map only'}
foreach($fixture in $before.fixtures){
    $rb=@($child.result.readback.members | Where-Object {$_.name -ceq $fixture.name})
    Need ($rb.Count -eq 1 -and $rb[0].bytes -eq $fixture.bytes -and $rb[0].sha256 -ceq $fixture.sha256) 'Generated readback receipt'
    Need ($child.generated_asset_io[$fixture.name].seeks -eq 1 -and $child.generated_asset_io[$fixture.name].reads -eq 2 -and $child.generated_asset_io[$fixture.name].bytes -eq $fixture.bytes) 'Child bounded generated reads'
}
Yes $after.inputs_unchanged 'After receipt invariant'
foreach($relative in @($reads.Keys)){$null=ReadText $relative}
[ordered]@{
    verdict='PASS_WITH_GENERATED_NATIVE_SCOPE'
    actual_outer_chunk=$outer.chunk_id;actual_outer_seconds=$outer.wall_time_seconds
    controller_native_exit=0;child_native_exit=0;contender_native_exit=0;outer_exit=0
    operation_events=$events;segments=1;cancellation_journal=$cancellation
    lifecycle_phase=8;four_journal_phases=$journal.phases;flush_successes=4
    retained_closed_journal_bytes=$closed.bytes;retained_closed_journal_sha256=$closed.sha256
    roles=$roleSummaries;current_source_control_pairs=21;unchanged_support_fixture_metadata_rows=14
    journal_or_support_or_fixture_files_opened=$false;native_reruns=0;runtime_or_release_approved=$false
    text_reads=@($reads.Values)
} | ConvertTo-Json -Depth 10
