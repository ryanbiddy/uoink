$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskRun=$taskBase+'\_scratch\runtime-owner-native-connection01'
$taskProposal=$taskBase+'\_scratch\runtime-owner-native-connection-native-proposal01'
function Need($ok,[string]$why){if(-not $ok){throw $why}}
function Sha([byte[]]$bytes){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
function Same($left,$right){($left | ConvertTo-Json -Depth 16 -Compress) -ceq ($right | ConvertTo-Json -Depth 16 -Compress)}
$names=@('controller-result.json','child-result.json','contender-result.json','before.json','after.json','exit.json','native-exit.json','closed-journal-observation.json','controller-stdout.log','controller-stderr.log')
$data=@{};$inputs=@()
foreach($name in $names){
 $raw=[IO.File]::ReadAllBytes((Join-Path $taskRun $name));Need ($raw.Length -le 1048576) 'Receipt bound'
 $inputs += [ordered]@{name=$name;bytes=$raw.Length;sha256=(Sha $raw)}
 if($name.EndsWith('.json')){$data[$name]=[Text.Encoding]::UTF8.GetString($raw) | ConvertFrom-Json}else{Need ($raw.Length -eq 0) 'Empty streams'}
}
$c=$data['controller-result.json'];$h=$data['child-result.json'];$t=$data['contender-result.json']
$b=$data['before.json'];$a=$data['after.json'];$e=$data['exit.json'];$ne=$data['native-exit.json'];$closed=$data['closed-journal-observation.json']
Need ($e.outer_exit -eq 0 -and $e.controller_native_exit -eq 0 -and $e.receipt_valid -ceq $true -and $e.inputs_unchanged -ceq $true -and $null -eq $e.receipt_error_type -and $ne.native_exit -eq 0 -and $ne.child_returned -ceq $true) 'Recorded exits'
$mapPath=$taskProposal+'\SOURCE-INPUTS.json'
Need ((Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq '59f9e0d3cd15e632e8b5dd8e225d5b4c66d81020b8f0ec541128bcdd910940b4') 'Reviewed source map'
$map=Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json
$sourceNames=@($map.source_paths.PSObject.Properties.Name)
$controlPaths=@{'ROOT-ADMISSION.json'=$taskProposal+'\ROOT-ADMISSION-cancel.json';'SOURCE-INPUTS.json'=$mapPath;'run_native_owner_cancel01.ps1'=$taskProposal+'\run_native_owner_cancel01.ps1'}
$controlHashes=@{'ROOT-ADMISSION.json'='7e641689c4985a4df4d1f860613f2da859f1f98843a16b43ec01cbad6125dbfd';'SOURCE-INPUTS.json'='59f9e0d3cd15e632e8b5dd8e225d5b4c66d81020b8f0ec541128bcdd910940b4';'run_native_owner_cancel01.ps1'='8f1a5c2e935c05d24790616ef0a005ba753c5ac77043db88fc0cef300afd0203'}
Need ($sourceNames.Count -eq 29 -and @($b.sources).Count -eq 29 -and @($b.controls).Count -eq 3 -and @($a.source_and_controls).Count -eq 32 -and $a.inputs_unchanged -ceq $true) 'Source/control counts'
foreach($name in ($sourceNames+@($controlPaths.Keys))){
 $path=if($controlPaths.ContainsKey($name)){$controlPaths[$name]}else{Join-Path $taskProposal $name}
 $hash=if($controlHashes.ContainsKey($name)){$controlHashes[$name]}else{$map.source_sha256.$name}
 $before=@(($b.sources+$b.controls)|Where-Object {$_.name -ceq $name});$after=@($a.source_and_controls|Where-Object {$_.name -ceq $name})
 Need ($before.Count -eq 1 -and $after.Count -eq 1 -and $before[0].path -ceq $path -and $before[0].sha256 -ceq $hash) 'Unique input record'
 Need ($after[0].before_sha256 -ceq $hash -and $after[0].source_after_sha256 -ceq $hash -and $after[0].copy_after_sha256 -ceq $hash) 'Recorded input stability'
 Need ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $hash -and (Get-FileHash -LiteralPath (Join-Path $taskRun $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $hash) 'Actual fixed text copies'
}
Need (@($b.native_inputs).Count -eq 9 -and @($b.fixtures).Count -eq 5 -and @($a.support_and_fixtures).Count -eq 14) 'Recorded support/fixture counts'
# Recorded support and fixture paths below are never dereferenced.
foreach($row in $b.native_inputs){Need ($row.bytes -eq $map.native_bindings.($row.path).bytes -and $row.sha256 -ceq $map.native_bindings.($row.path).sha256) 'Recorded support binding'}
foreach($row in ($b.native_inputs+$b.fixtures)){
 $after=@($a.support_and_fixtures|Where-Object {$_.path -ceq $row.path})
 Need ($after.Count -eq 1 -and $after[0].bytes -eq $row.bytes -and $after[0].before_sha256 -ceq $row.sha256 -and $after[0].after_sha256 -ceq $row.sha256) 'Recorded other-input stability'
}
$roles=@()
foreach($pair in @(@($c,'controller',8215,2),@($h,'child',237,0),@($t,'contender',103,0))){
 $r=$pair[0];$role=$pair[1];$calls=$pair[2];$casts=$pair[3]
 Need ($r.role -ceq $role -and $r.schema -ceq 'uoink.generated-windows-runtime-owner-cancel.v1' -and $r.case -ceq 'positive' -and $r.operation_mode -ceq 'cancel' -and $r.native_exit_planned -eq 0 -and $null -eq $r.error_type -and $r.guard_valid -ceq $true) 'Role success'
 Need (@($r.guard_denials).Count -eq 0 -and $r.metadata_traps -eq 12 -and $r.registry_traps -eq 25 -and $r.pending_pipe_operations -eq 0 -and @($r.reserved_cleanup_calls).Count -eq 0 -and @($r.reserved_cleanup_wait_caps).Count -eq 0 -and $r.work_budget_closed -ceq $false) 'Guard and pending I/O'
 Need ($r.fixed_dispatch_valid -ceq $true -and $r.fixed_dispatch_function_count -eq 33 -and $r.fixed_dispatch_invalid_contexts -eq 0 -and $r.fixed_attribute_cast_calls -eq $casts -and @($r.native_api_calls).Count -eq $calls -and $r.fixed_dispatch_completed_calls -eq (34+$calls+$casts) -and $r.fixed_dispatch_audit_events -eq (34+$calls+$casts)) '33-function dispatch accounting'
 Need ($r.kernel32_path_verified -ceq $true -and $r.model_calls -eq 0 -and @($r.model_imports).Count -eq 0 -and @($r.owner_state.PSObject.Properties).Count -eq 6 -and @($r.adapter_state.PSObject.Properties).Count -eq 5) 'Native/model scope'
 foreach($field in @($r.owner_state.PSObject.Properties)+@($r.adapter_state.PSObject.Properties)){Need ($field.Value -is [bool] -and $field.Value -ceq $true) 'Owner/adapter guards'}
 Need (@($r.source_sha256.PSObject.Properties).Count -eq 29) 'Role source count'
 foreach($name in $sourceNames){Need ($r.source_sha256.$name -ceq $map.source_sha256.$name) 'Role source hash'}
 $roles += [ordered]@{role=$role;api_calls=$calls;dispatch=$r.fixed_dispatch_completed_calls;elapsed_seconds=$r.elapsed_seconds;exit=0;guard_valid=$true}
}
$owner=$h.result.runtime_owner
$ownerEvents=@('owner_ready','readset_adopted','policy_acknowledged','begun','namespace_materialized','generated_inputs_issued','actual_factory_registered','control_committed','control_committed','segment_committed','control_committed','actual_factory_retired','child_readset_released','closed_frame_committed','closed_frame_written','owner_and_channel_revoked')
$actions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')
$factoryEvents=@('model_constructor','model_build','strict_load','vad_parent_after_owned_guard','vad_instantiate')
Need ((Same $owner $h.retained_runtime_owner) -and $null -eq $c.retained_runtime_owner -and $null -eq $t.retained_runtime_owner -and @($owner.PSObject.Properties).Count -eq 19) 'Retained child-only owner'
Need ($owner.state -ceq 'closed' -and $null -eq $owner.failure_type -and (Same $owner.events $ownerEvents) -and (Same $owner.generated_factory_events $factoryEvents)) 'Owner sequence'
foreach($field in @('clean_closed','factory_attempted','generated_state_retained','channel_revoked','owned_guard_restored_none','generated_duration_only')){Need ($owner.$field -ceq $true) 'Owner completion'}
Need ($owner.owner_active_at_exit -ceq $false -and $owner.real_runtime_approved -ceq $false -and $owner.model_calls -eq 0 -and $owner.model_inference_calls -eq 0 -and $owner.produced_segments -eq 1) 'Generated owner only'
foreach($r in @($c.result,$h.result,$owner)){Need ((Same $r.operation_events $actions)) 'Four actions'}
Need ($c.result.cursor_state -ceq 'cancelled' -and $h.result.cursor_state -ceq 'cancelled' -and $h.result.child_flow_return -eq 0 -and @($c.result.segments).Count -eq 1) 'One segment cancellation'
$segment=$c.result.segments[0]
Need ($segment.start -eq 0 -and $segment.end -eq .5 -and $segment.text -ceq 'Uoink generated adoption fixture: config.json. No model data.' -and @($segment.words).Count -eq 0) 'Synthetic segment'
Need ($c.result.lifecycle_phase -eq 8 -and $c.result.read_set_released -ceq $true -and $c.result.pipe_retired -ceq $true -and $c.result.parent_guards_held_through_exit -ceq $true -and $c.result.retained_facade_and_stream_refused -ceq $true) 'Parent ownership retirement'
foreach($x in @($c.result.exit_observation,$c.writer_exclusion.exit_observation)){Need ($x.child_native_exit -eq 0 -and $x.process_wait_observed -ceq $true -and $x.job_active_processes -eq 0) 'Owned exit/empty job'}
Need ($c.writer_exclusion.completed -ceq $true -and $c.writer_exclusion.guard_released -ceq $true -and $c.writer_exclusion.worker_handles_closed -ceq $true -and $c.writer_exclusion.worker_unconfirmed -ceq $false -and $c.writer_exclusion.primary_journal_held_through_contender_exit -ceq $true) 'Contender custody'
Need ($t.result.status -ceq 'sharing_refused' -and $t.result.winerror -eq 32 -and $t.result.attempt_count -eq 1 -and $t.result.journal_content_reads -eq 0 -and $t.result.journal_writes -eq 0) 'Contender no I/O'
$fixtureNames=@('config.json','model.bin','preprocessor_config.json','tokenizer.json','vocabulary.json')
Need ($h.result.adoption.status -ceq 'released' -and $h.result.adoption.owned_members -eq 5 -and $h.result.adoption.inheritance_cleared -eq 5 -and $h.result.adoption.identities_checked -eq 5 -and $h.result.adoption.read_set_released -ceq $true -and $h.result.adoption.read_set_unconfirmed -ceq $false -and @($h.result.adoption.handles_closed|Where-Object {$_ -cne $true}).Count -eq 0) 'Child readset release'
for($i=0;$i -lt 5;$i++){
 $name=$fixtureNames[$i];$fixture=$b.fixtures[$i];$member=$c.result.authenticated_manifest.members[$i]
 $fixtureBytes=[Text.Encoding]::ASCII.GetBytes('Uoink generated adoption fixture: '+$name+'. No model data.'+[char]10)
 Need ($fixture.name -ceq $name -and $fixture.path -ceq (Join-Path $taskRun $name) -and $fixture.bytes -eq $fixtureBytes.Length -and $fixture.sha256 -ceq (Sha $fixtureBytes)) 'Recorded fixture constants'
 Need ($member.name -ceq $name -and $member.sha256 -ceq $fixture.sha256 -and (Same $member.identity $h.result.adoption.observed_identities[$i])) 'Inherited identity'
 Need ($h.generated_asset_io.$name.seeks -eq 1 -and $h.generated_asset_io.$name.reads -eq 2 -and $h.generated_asset_io.$name.bytes -eq $fixture.bytes -and $c.generated_asset_io.$name.bytes -eq 0 -and $t.generated_asset_io.$name.bytes -eq 0) 'Generated native reads'
 Need ($owner.readback.members[$i].sha256 -ceq $fixture.sha256 -and $owner.readback.members[$i].bytes -eq $fixture.bytes) 'Owner readback'
}
Need ((Same $owner.readback $h.result.readback) -and (Same $owner.cursor_start $h.result.cursor_start) -and (Same $c.result.adapter_start $h.result.adapter_start) -and (Same $c.result.adapter_start_ack $h.result.adapter_start_ack)) 'Reply binding'
$j=$c.result.durable_journal;$cancel=$c.result.cancellation_journal
Need ($j.journal_bytes -gt 6 -and $j.journal_bytes -le 16534 -and $j.journal_hex -cmatch '^[0-9a-f]+$' -and $j.journal_hex.Length -eq 2*$j.journal_bytes) 'Recorded journal bound'
$raw=[Convert]::FromHexString($j.journal_hex)
Need ((Sha $raw) -ceq $j.journal_sha256 -and [Text.Encoding]::ASCII.GetString($raw,0,6) -ceq ('UORS1'+[char]10)) 'Journal magic/checksum'
$pos=6;$prior='0'*64;$rows=@();$heads=@();$ends=@();$phases=@('INITIALIZED','RESERVED','WORKER_BOUND','CLEARED')
for($i=0;$i -lt 4;$i++){
 Need ($pos+4 -le $raw.Length) 'Frame prefix'
 $len=([uint32]$raw[$pos]*16777216)+([uint32]$raw[$pos+1]*65536)+([uint32]$raw[$pos+2]*256)+[uint32]$raw[$pos+3];$pos+=4
 Need ($len -gt 0 -and $len -le 4096 -and $pos+$len+32 -le $raw.Length) 'Frame length'
 $payload=[byte[]]::new($len);[Array]::Copy($raw,$pos,$payload,0,$len);$pos+=$len
 $digest=[Convert]::ToHexString($raw,$pos,32).ToLowerInvariant();$pos+=32
 Need ((Sha $payload) -ceq $digest) 'Frame checksum'
 $row=[Text.Encoding]::UTF8.GetString($payload)|ConvertFrom-Json
 Need (@($row.PSObject.Properties).Count -eq 9 -and $row.schema -eq 1 -and $row.sequence -eq $i -and $row.phase -ceq $phases[$i] -and $row.previous -ceq $prior -and (Same $row.physical $j.physical) -and $null -eq $row.reason) 'Four-frame chain'
 if($i -lt 2){Need ($null -eq $row.process) 'No early process'}else{Need (@($row.process).Count -eq 2 -and $row.process[0] -gt 0 -and $row.process[1] -gt 0) 'Process binding'}
 if($i -eq 0){Need ($null -eq $row.generation) 'Initial generation'}else{Need ($row.generation -cmatch '^[0-9a-f]{64}$') 'Generation shape'}
 if($i -gt 1){Need ((Same $row.semantics $rows[1].semantics) -and $row.generation -ceq $rows[1].generation) 'Same reserved identity'}
 if($i -eq 3){Need ((Same $row.process $rows[2].process)) 'Same cleared process'}
 $rows+=,$row;$heads+=,$digest;$ends+=,$pos;$prior=$digest
}
Need ($pos -eq $raw.Length -and $prior -ceq $j.head -and (Same $j.phases $phases)) 'Complete four-frame stream'
$prefix=[byte[]]::new($ends[2]);[Array]::Copy($raw,0,$prefix,0,$prefix.Length)
Need ($cancel.phase_before -ceq 'WORKER_BOUND' -and $cancel.phase_after -ceq 'WORKER_BOUND' -and $cancel.confirmed_before_sha256 -ceq (Sha $prefix) -and $cancel.confirmed_after_sha256 -ceq (Sha $prefix)) 'Unchanged journal during cursor cancel'
foreach($field in @('same_token_and_handle','gate_held_before_stop','journal_open_before_stop','clear_deferred_until_adapter_finally')){Need ($cancel.$field -ceq $true) 'Held lifetime'}
Need ((Same $j.physical $t.result.physical) -and $j.journal_path -ceq $t.result.journal_path -and $closed.path -ceq $j.journal_path -and $closed.bytes -eq $raw.Length -and $closed.sha256 -ceq (Sha $raw) -and $closed.matches_controller_confirmed_bytes -ceq $true -and $closed.exclusive_postexit_read_closed -ceq $true -and $closed.power_loss_or_restart_proven -ceq $false) 'Recorded postexit journal observation'
$flushes=@($j.io_events|Where-Object {$_.api -ceq 'FlushFileBuffers'})
Need ($flushes.Count -eq 4 -and $j.flush_successes -eq 4 -and $j.journal_handle_closed -ceq $true -and $j.directory_guards_retired -ceq $true -and $j.creation_handle_transferred_without_close -ceq $true) 'Four flushes and closed journal'
$last=-1
foreach($io in $j.io_events){Need ($io.result -ceq $true -and $io.call_index -gt $last -and $c.native_api_calls[$io.call_index] -ceq $io.api) 'Journal I/O index';$last=$io.call_index}
$expected=@('CreateProcessW','ResumeThread','CloseHandle')
Need (@($j.milestones).Count -eq 3) 'Three lifetime milestones'
for($i=0;$i -lt 3;$i++){
 $m=$j.milestones[$i]
 Need ($m.api -ceq $expected[$i] -and $m.phase -ceq $phases[$i+1] -and $m.head -ceq $heads[$i+1] -and $m.flush_successes -eq ($i+2) -and $c.native_api_calls[$m.call_index] -ceq $m.api -and $flushes[$i+1].call_index -lt $m.call_index) 'Flush before lifetime transition'
}
[ordered]@{scope='Passive recorded receipts only; no physical journal/fixtures/support or candidate execution';status='PASS';roles=$roles;source_control_pairs=32;source_copies_match=$true;recorded_support_rows=9;recorded_fixture_rows=5;owner_events_match=$true;factory_events_match=$true;one_segment_cancel=$true;owned_exit_and_empty_jobs=$true;journal_bytes=$raw.Length;journal_sha256=(Sha $raw);frame_ends=$ends;frame_heads=$heads;cancel_prefix_sha256=(Sha $prefix);journal_process=$rows[2].process;four_flushes_before_milestones=$true;inputs=$inputs}|ConvertTo-Json -Depth 8
