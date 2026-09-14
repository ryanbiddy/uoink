# Passive fixed text/JSON checker only. Never dot-source or import a candidate.
param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedAdmissionSha256)
$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$run='_scratch/runtime-owner-native-connection01'
$proposal='_scratch/runtime-owner-native-connection-native-proposal01'
$sourceNames=@('plain_state_reader.py','state_bridge.py','owned_cpu_tensor_port.py','model_binding_registry.py','owned_factory_port.py','owned_guard.py','fake_torch_support.py','fixed_schema_helpers.py','worker_runtime_owner.py','reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py','durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py','win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py','generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_journal_setup.py','generated_writer_exclusion.py','generated_worker_factory_inputs.py','generated_worker_runtime_bridge.py','generated_adapter_flow.py','dummy_bootstrap.py')
$allowed=@($sourceNames | ForEach-Object {$run+'/'+$_;$proposal+'/'+$_})+@(
    ($run+'/controller-result.json'),($run+'/child-result.json'),($run+'/contender-result.json'),
    ($run+'/exit.json'),($run+'/native-exit.json'),($run+'/closed-journal-observation.json'),
    ($run+'/before.json'),($run+'/after.json'),($run+'/ROOT-ADMISSION.json'),
    ($run+'/SOURCE-INPUTS.json'),($run+'/run_native_owner_cancel01.ps1'),
    ($run+'/controller-stdout.log'),($run+'/controller-stderr.log'),
    ($proposal+'/ROOT-ADMISSION-cancel.json'),($proposal+'/SOURCE-INPUTS.json'),($proposal+'/run_native_owner_cancel01.ps1')
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
Need ($exit.controller_native_exit -eq 0 -and $exit.expected_child_native_exit -eq 0 -and $exit.outer_exit -eq 0 -and $null -eq $exit.receipt_error_type) 'Recorded exits'
Yes $exit.receipt_valid 'Launcher receipt verdict';Yes $exit.inputs_unchanged 'Launcher inputs';Yes $native.child_returned 'Controller returned'
Need ($native.native_exit -eq 0 -and $exit.stdout_bytes -eq 0 -and $exit.stderr_bytes -eq 0 -and $exit.operation_mode -ceq 'cancel') 'Raw native/log observations'
Need ((ReadText ($run+'/controller-stdout.log')).Length -eq 0 -and (ReadText ($run+'/controller-stderr.log')).Length -eq 0) 'Current empty logs'
$map=Json ($proposal+'/SOURCE-INPUTS.json')
Need ($reads[$proposal+'/SOURCE-INPUTS.json'].sha256 -ceq '59f9e0d3cd15e632e8b5dd8e225d5b4c66d81020b8f0ec541128bcdd910940b4') 'Reviewed source map'
Need ($map.source_paths.Count -eq 29 -and $map.source_sha256.Count -eq 29 -and $before.sources.Count -eq 29 -and $before.controls.Count -eq 3 -and $after.source_and_controls.Count -eq 32) 'Source/control counts'
$controlNames=@('ROOT-ADMISSION.json','SOURCE-INPUTS.json','run_native_owner_cancel01.ps1')
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
Need ($reads[$proposal+'/run_native_owner_cancel01.ps1'].sha256 -ceq '8f1a5c2e935c05d24790616ef0a005ba753c5ac77043db88fc0cef300afd0203') 'Reviewed launcher'
Need ($reads[$proposal+'/ROOT-ADMISSION-cancel.json'].sha256 -ceq $ExpectedAdmissionSha256) 'Exact admission'
$admission=Json ($run+'/ROOT-ADMISSION.json')
Yes $admission.root_reviewed 'Root reviewed';Yes $admission.native_execution_admitted 'Native admission'
Need ($admission.scope -ceq 'generated-windows-runtime-owner-cancel-only' -and $admission.case -ceq 'positive' -and $admission.operation_mode -ceq 'cancel' -and $admission.run_path -ceq (Join-Path $repo $run)) 'Exact admission scope'
Need ($admission.source_inputs_sha256 -ceq $reads[$proposal+'/SOURCE-INPUTS.json'].sha256 -and $admission.launcher_sha256 -ceq $reads[$proposal+'/run_native_owner_cancel01.ps1'].sha256) 'Admission controls'
$roleSummaries=@()
foreach($pair in @(@('controller',$c,2),@('child',$child,0),@('contender',$contender,0))){
    $r=$pair[1]
    Need ($r.role -ceq $pair[0] -and $r.schema -ceq 'uoink.generated-windows-runtime-owner-cancel.v1' -and $r.case -ceq 'positive' -and $r.operation_mode -ceq 'cancel' -and $null -eq $r.error_type -and $null -eq $r.directory_refusal) 'Role identity/error'
    Yes $r.guard_valid 'Guard';Yes $r.fixed_dispatch_valid 'Dispatch';Yes $r.kernel32_path_verified 'Recorded kernel path'
    Need ($r.native_exit_planned -eq 0 -and $r.guard_denials.Count -eq 0 -and $r.pending_pipe_operations -eq 0 -and $r.metadata_traps -eq 12 -and $r.registry_traps -eq 25 -and $r.model_calls -eq 0 -and $r.model_imports.Count -eq 0) 'Guard/counter membership'
    No $r.work_budget_closed 'Work budget';Need ($r.reserved_cleanup_calls.Count -eq 0 -and $r.reserved_cleanup_wait_caps.Count -eq 0) 'Reserved cleanup unused'
    Need ($r.fixed_dispatch_function_count -eq 33 -and $r.fixed_dispatch_invalid_contexts -eq 0 -and $r.fixed_attribute_cast_calls -eq $pair[2] -and $r.fixed_dispatch_completed_calls -eq (34+$r.native_api_calls.Count+$pair[2]) -and $r.fixed_dispatch_audit_events -eq $r.fixed_dispatch_completed_calls) 'Dispatch accounting'
    Need ($r.source_sha256.Count -eq 29) 'Role source membership'
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
Need ($journal.flush_successes -eq 4 -and $journal.milestones.Count -eq 3 -and $journal.journal_bytes -gt 6 -and $journal.journal_bytes -le 16534) 'Journal counts'
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
Need ($closed.bytes -eq $journal.journal_bytes -and $closed.path -ceq $journal.journal_path -and $closed.sha256 -ceq $journal.journal_sha256) 'Retained exclusive postexit comparison'
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

# Decode only the journal bytes already embedded in controller-result.json.
# This is a four-record receipt check, not the runtime journal implementation.
Need ($journal.journal_hex -is [string] -and $journal.journal_hex -cmatch '^[0-9a-f]+$' -and $journal.journal_hex.Length -eq 2*$journal.journal_bytes) 'Recorded journal hex bound'
$raw=[Convert]::FromHexString($journal.journal_hex)
Need ($raw.Length -eq $closed.bytes -and [Text.Encoding]::ASCII.GetString($raw,0,6) -ceq "UORS1`n") 'Recorded journal magic/size'
$recordedHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
Need ($recordedHash -ceq $closed.sha256 -and $recordedHash -ceq $journal.journal_sha256) 'Recorded whole journal digest'
$offset=6;$previous='0'*64;$decoded=@();$frameEnds=@();$heads=@()
for($i=0;$i -lt 4;$i++){
    Need ($raw.Length-$offset -ge 4) 'Recorded frame header'
    $length=[long]$raw[$offset]*16777216+[long]$raw[$offset+1]*65536+[long]$raw[$offset+2]*256+[long]$raw[$offset+3]
    $offset+=4
    Need ($length -gt 0 -and $length -le 4096 -and $raw.Length-$offset -ge $length+32) 'Recorded frame bound'
    $payload=[byte[]]$raw[$offset..($offset+$length-1)]
    $digest=[Convert]::ToHexString([byte[]]$raw[($offset+$length)..($offset+$length+31)]).ToLowerInvariant()
    Need ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($payload)).ToLowerInvariant() -ceq $digest) 'Recorded frame digest'
    $text=$utf8.GetString($payload);$row=$text|ConvertFrom-Json -AsHashtable
    Need ($row.Count -eq 9 -and ($row.schema -is [int] -or $row.schema -is [long]) -and $row.schema -eq 1 -and ($row.sequence -is [int] -or $row.sequence -is [long]) -and $row.sequence -eq $i -and $row.phase -ceq @('INITIALIZED','RESERVED','WORKER_BOUND','CLEARED')[$i] -and $null -eq $row.reason -and $row.previous -ceq $previous) 'Recorded frame schema/order'
    $canonical=[ordered]@{generation=$row.generation;phase=$row.phase;physical=$row.physical;previous=$row.previous;process=$row.process;reason=$row.reason;schema=$row.schema;semantics=$row.semantics;sequence=$row.sequence}|ConvertTo-Json -Depth 8 -Compress
    Need ($text -ceq $canonical) 'Exact canonical record; no duplicate or extra fields'
    Same $row.physical $journal.physical 'Recorded physical identity'
    Same $row.semantics @($journal.physical[0],$journal.physical[1],'large-v3-turbo','0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf','6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33') 'Fixed semantic record'
    if($i -eq 0){Need ($null -eq $row.generation -and $null -eq $row.process) 'Initial record has no worker'}
    else{
        Need ($row.generation -is [string] -and $row.generation -cmatch '^[0-9a-f]{64}$') 'Recorded generation'
        if($i -gt 1){Need ($row.generation -ceq $decoded[1].generation) 'Same recorded generation'}
        if($i -eq 1){Need ($null -eq $row.process) 'Reserved record precedes worker'}
        else{
            Need ($row.process.Count -eq 2 -and ($row.process[0] -is [int] -or $row.process[0] -is [long] -or $row.process[0] -is [uint64]) -and ($row.process[1] -is [int] -or $row.process[1] -is [long] -or $row.process[1] -is [uint64]) -and [decimal]$row.process[0] -gt 0 -and [decimal]$row.process[0] -lt 4294967296 -and [decimal]$row.process[1] -gt 0 -and [decimal]$row.process[1] -lt 18446744073709551616) 'Recorded process identity bounds'
            if($i -eq 3){Same $row.process $decoded[2].process 'Clear retains bound process identity'}
        }
    }
    $offset+=$length+32;$previous=$digest;$decoded+=,$row;$frameEnds+=,$offset;$heads+=,$digest
}
Need ($offset -eq $raw.Length -and $previous -ceq $journal.head) 'Four complete records and final head'
for($i=0;$i -lt 3;$i++){Need ($journal.milestones[$i].head -ceq $heads[$i+1]) 'Recorded phase head matches milestone'}
$boundPrefix=[byte[]]$raw[0..($frameEnds[2]-1)]
Need ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($boundPrefix)).ToLowerInvariant() -ceq $cancellation.confirmed_before_sha256) 'Cancellation preserved the exact WORKER_BOUND prefix'
Need ($journal.physical.Count -eq 2 -and $journal.physical[0] -isnot [bool] -and ([string]$journal.physical[0]) -cmatch '^[0-9]{1,20}$' -and $journal.physical[1] -is [string] -and $journal.physical[1] -cmatch '^[0-9a-f]{32}$') 'Recorded physical format'
$volume=[UInt64]::Parse([string]$journal.physical[0],[Globalization.CultureInfo]::InvariantCulture)
$journalName=$volume.ToString('x16',[Globalization.CultureInfo]::InvariantCulture)+'-'+$journal.physical[1]+'.journal'
Need ($journal.journal_path -ceq (Join-Path (Join-Path $repo ($run+'/registry')) $journalName) -and $contender.result.journal_path -ceq $journal.journal_path) 'Recorded journal path only; never opened'

# Exact publication, product retirement and retained child receipt.
$ownerFields=@('methods_unchanged','closed_entries_unchanged','module_identities_unchanged','owned_guard_restored_none','require_owned_runtime_unchanged','retained_bridge_type_valid')
foreach($r in @($c,$child,$contender)){
    Need ($r.owner_state.Count -eq 6) 'Six owner binding guards'
    foreach($name in $ownerFields){Yes $r.owner_state[$name] 'Owner binding identity guard'}
}
Need ($null -eq $c.retained_runtime_owner -and $null -eq $contender.retained_runtime_owner) 'Owner bridge only in primary child'
$owner=$child.result.runtime_owner
Need ($owner.Count -eq 19 -and $owner.connection -ceq 'generated-owner-native-v1' -and $owner.state -ceq 'closed' -and $null -eq $owner.failure_type -and $owner.produced_segments -eq 1 -and $owner.model_calls -eq 0 -and $owner.model_inference_calls -eq 0) 'Fixed retained owner completion'
foreach($name in @('generated_duration_only','clean_closed','factory_attempted','generated_state_retained','channel_revoked','owned_guard_restored_none')){Yes $owner[$name] 'Owner completion field'}
No $owner.owner_active_at_exit 'Owner revoked';No $owner.real_runtime_approved 'Real runtime closed'
$ownerEvents=@('owner_ready','readset_adopted','policy_acknowledged','begun','namespace_materialized','generated_inputs_issued','actual_factory_registered','control_committed','control_committed','segment_committed','control_committed','actual_factory_retired','child_readset_released','closed_frame_committed','closed_frame_written','owner_and_channel_revoked')
Same $owner.events $ownerEvents 'Exact owner event order'
Same $owner.generated_factory_events @('model_constructor','model_build','strict_load','vad_parent_after_owned_guard','vad_instantiate') 'Exact generated factory events'
Same $owner.operation_events $events 'Owner four actions'
Same $owner.readback $child.result.readback 'Owner readback binding';Same $owner.cursor_start $child.result.cursor_start 'Owner cursor binding'
Same $owner $child.retained_runtime_owner 'Retained receipt unchanged after successful child return'

# Retain direct adoption and policy checks without opening generated files.
Need ($child.result.child_flow_return -eq 0 -and $child.result.model_calls -eq 0) 'Successful generated child return'
$adopt=$child.result.adoption
Need ($adopt.status -ceq 'released' -and $adopt.owned_members -eq 5 -and $adopt.inheritance_cleared -eq 5 -and $adopt.identities_checked -eq 5 -and $adopt.observed_identities.Count -eq 5 -and $adopt.handles_closed.Count -eq 5 -and $adopt.model_calls -eq 0) 'Complete inherited adoption'
Yes $adopt.materialization_started 'Generated materialization';Yes $adopt.read_set_released 'Child read set retired';No $adopt.read_set_unconfirmed 'No child uncertainty';No $adopt.complete_native_namespace_protection 'No broader namespace claim'
foreach($value in $adopt.handles_closed){Yes $value 'Each inherited member retired'}
$manifest=$result.authenticated_manifest
Need ($manifest.schema -ceq 'uoink.generated-inherited-readset.v1' -and $manifest.case -ceq 'positive' -and $manifest.members.Count -eq 5 -and $manifest.namespace_sha256 -ceq 'f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9') 'Fixed authenticated manifest'
$manifestRows=@()
for($i=0;$i -lt 5;$i++){
    $member=$manifest.members[$i];$id=$member.identity;$fixture=$before.fixtures[$i]
    Need ($member.name -ceq $fixture.name -and $member.sha256 -ceq $fixture.sha256 -and $id.size -eq $fixture.bytes -and $id.links -eq 1) 'Member identity and generated digest'
    No $id.directory 'Generated member regular file';Same $id $adopt.observed_identities[$i] 'Recorded child identity matches authenticated identity'
    $manifestRows+=,[ordered]@{handle=$member.handle;identity=[ordered]@{directory=$id.directory;file_id=$id.file_id;final_path=$id.final_path;links=$id.links;size=$id.size;volume_serial=$id.volume_serial};name=$member.name;sha256=$member.sha256}
}
$canonicalManifest=[ordered]@{case=$manifest.case;members=$manifestRows;namespace_sha256=$manifest.namespace_sha256;schema=$manifest.schema}|ConvertTo-Json -Depth 8 -Compress
Need ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($canonicalManifest))).ToLowerInvariant() -ceq $result.manifest_sha256) 'Authenticated manifest digest'
$expectedPolicy=[ordered]@{action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true;generated_root=(Join-Path $repo $run);inherited_manifest_sha256=$result.manifest_sha256;local_files_only=$true;namespace_sha256=$manifest.namespace_sha256;profile_id='generated-asr-reliability-v1';real_runtime_approved=$false;recipe_sha256='6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33';revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf';usage='reliability'}
$canonicalPolicy=$expectedPolicy|ConvertTo-Json -Depth 8 -Compress
$policyHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($canonicalPolicy))).ToLowerInvariant()
foreach($observed in @($result,$child.result)){
    Need ($observed.adapter_start.Count -eq $expectedPolicy.Count -and $observed.adapter_start_ack.action -ceq 'generated_adapter_start_bound' -and $observed.adapter_start_ack.policy_sha256 -ceq $policyHash -and $observed.adapter_start_ack.model_calls -eq 0) 'Exact policy acknowledgement'
    foreach($name in $expectedPolicy.Keys){Need ($observed.adapter_start.Contains($name) -and $observed.adapter_start[$name].GetType() -eq $expectedPolicy[$name].GetType() -and $observed.adapter_start[$name] -ceq $expectedPolicy[$name]) 'Policy field identity'}
}
foreach($relative in @($reads.Keys)){$null=ReadText $relative}
[ordered]@{
    verdict='PASS_WITH_GENERATED_NATIVE_SCOPE'
    controller_native_exit=0;child_native_exit=0;contender_native_exit=0;outer_exit=0
    operation_events=$events;segments=1;cancellation_journal=$cancellation
    lifecycle_phase=8;four_journal_phases=$journal.phases;flush_successes=4
    retained_closed_journal_bytes=$closed.bytes;retained_closed_journal_sha256=$closed.sha256
    decoded_journal_frames=$decoded.Count;owner_events=$ownerEvents;retained_owner_matches_return=$true
    actual_outer_tool_provenance_checked=$false
    roles=$roleSummaries;current_source_control_pairs=32;unchanged_support_fixture_metadata_rows=14
    journal_or_support_or_fixture_files_opened=$false;native_reruns=0;runtime_or_release_approved=$false
    text_reads=@($reads.Values)
} | ConvertTo-Json -Depth 10
