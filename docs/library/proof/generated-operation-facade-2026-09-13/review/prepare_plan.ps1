$ErrorActionPreference='Stop'
$taskScratch='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskOutput=Join-Path $taskScratch 'generated-operation-proof-proposal01'
# Read retained JSON/text and generated placeholders only. Never import or invoke a candidate.
# This prepares a finite copy list; it does not copy evidence or seal a proof directory.
function Need($condition,[string]$message){if(-not $condition){throw $message}}
function Fields($object,[string[]]$names,[string]$context){
    foreach($name in $names){Need ($null -ne $object.PSObject.Properties[$name]) "Missing $context.$name"}
}
function Same($a,$b){return (($a | ConvertTo-Json -Depth 30 -Compress) -ceq ($b | ConvertTo-Json -Depth 30 -Compress))}
function ReadJson([string]$path){return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)}
function SaveFresh([string]$name,$value){
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($value | ConvertTo-Json -Depth 35)+"`n")
    $stream=[IO.File]::Open((Join-Path $taskOutput $name),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
$common=@('schema','role','case','operation_mode','result','error_type','native_exit_planned','elapsed_seconds','guard_valid','guard_denials','metadata_traps','registry_traps','fixed_dispatch_valid','fixed_dispatch_function_count','fixed_dispatch_completed_calls','fixed_dispatch_audit_events','fixed_dispatch_invalid_contexts','fixed_attribute_cast_calls','native_api_calls','generated_asset_io','pending_pipe_operations','reserved_cleanup_calls','reserved_cleanup_wait_caps','work_budget_closed','kernel32_path_verified','ctypes_bootstrap_loads','source_sha256','model_imports','model_calls')
$controllerFields=@('operation_mode','segments','operation_events','cursor_state','cursor_start','retained_facade_and_stream_refused','lifecycle_phase','read_set_released','pipe_retired','exit_observation','write_access_observations','parent_guards_held_through_exit','adoption_case','adoption_response','authenticated_manifest','manifest_sha256','controller_handshake_begun','model_calls')
$childFields=@('child_flow_return','adoption','readback','operation_events','cursor_state','produced_segments','generated_duration_only','cursor_start','model_calls')
$adoptionFields=@('status','owned_members','inheritance_cleared','identities_checked','observed_identities','materialization_started','read_set_unconfirmed','read_set_released','handles_closed','complete_native_namespace_protection','model_calls')
$names=@('config.json','model.bin','preprocessor_config.json','tokenizer.json','vocabulary.json')
$summaries=@()
foreach($mode in @('drain','cancel')){
    $dir=Join-Path $taskScratch "generated-operation-$($mode)01"
    $c=ReadJson "$dir\controller-result.json"; $h=ReadJson "$dir\child-result.json"
    $b=ReadJson "$dir\before.json"; $a=ReadJson "$dir\after.json"
    $n=ReadJson "$dir\native-exit.json"; $e=ReadJson "$dir\exit.json"
    $outer=ReadJson (Join-Path $taskScratch "GENERATED-OPERATION-$($mode.ToUpperInvariant())01-ACTUAL.json")
    Fields $c.result $controllerFields 'controller.result'; Fields $h.result $childFields 'child.result'
    Fields $h.result.adoption $adoptionFields 'child.adoption'
    Fields $c.result.exit_observation @('child_native_exit','process_wait_observed','job_active_processes') 'exit_observation'
    Need ($c.role -ceq 'controller' -and $h.role -ceq 'child') 'Endpoint roles'
    foreach($r in @($c,$h)){
        Fields $r $common 'endpoint'
        Need ($r.schema -ceq 'uoink.generated-operation-facade.v1' -and $r.operation_mode -ceq $mode -and $r.case -ceq 'positive') 'Endpoint identity'
        Need ($r.error_type -eq $null -and $r.native_exit_planned -eq 0 -and $r.guard_valid -ceq $true -and @($r.guard_denials).Count -eq 0) 'Endpoint outcome/guard'
        Need ($r.fixed_dispatch_valid -ceq $true -and $r.fixed_dispatch_function_count -eq 32 -and $r.fixed_dispatch_invalid_contexts -eq 0 -and $r.metadata_traps -eq 12 -and $r.registry_traps -eq 25) 'Guard membership'
        $casts=0;if($r.role -ceq 'controller'){$casts=1}
        Need ($r.fixed_attribute_cast_calls -eq $casts -and $r.fixed_dispatch_completed_calls -eq (33+@($r.native_api_calls).Count+$casts) -and $r.fixed_dispatch_audit_events -eq $r.fixed_dispatch_completed_calls) 'Dispatch accounting'
        Need ($r.pending_pipe_operations -eq 0 -and $r.work_budget_closed -ceq $false -and @($r.reserved_cleanup_calls).Count -eq 0 -and @($r.reserved_cleanup_wait_caps).Count -eq 0 -and $r.kernel32_path_verified -ceq $true) 'Cleanup/kernel fields'
        Need ($r.model_calls -eq 0 -and @($r.model_imports).Count -eq 0 -and $r.result.model_calls -eq 0) 'Generated-only receipt'
        Fields $r.result.cursor_start @('cursor_id','started','produced_segments') 'cursor_start'
        Need (@($r.result.cursor_start.PSObject.Properties).Count -eq 3 -and $r.result.cursor_start.cursor_id -ceq 'generated-cursor-01' -and $r.result.cursor_start.started -ceq $true -and $r.result.cursor_start.produced_segments -eq 0) 'Lazy cursor start'
    }
    $count=2;$state='eof';$actions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','next_generated_segment','next_generated_segment')
    if($mode -ceq 'cancel'){$count=1;$state='cancelled';$actions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')}
    Need ((Same $c.result.operation_events $actions) -and (Same $h.result.operation_events $actions) -and $c.result.cursor_state -ceq $state -and $h.result.cursor_state -ceq $state -and $h.result.produced_segments -eq $count) 'Mode events/state'
    Need (@($c.result.segments).Count -eq $count -and $h.result.generated_duration_only -ceq $true -and $c.result.retained_facade_and_stream_refused -ceq $true) 'Segments and stale references'
    for($i=0;$i -lt $count;$i++){
        $s=$c.result.segments[$i]; Fields $s @('start','end','text','words') 'segment'
        $textName=@('config.json','tokenizer.json')[$i]
        Need ($s.start -eq ($i/2.0) -and $s.end -eq (($i+1)/2.0) -and $s.text -ceq "Uoink generated adoption fixture: $textName. No model data." -and @($s.words).Count -eq 0) 'Exact generated segment'
    }
    Need ($c.result.lifecycle_phase -eq 8 -and $c.result.read_set_released -ceq $true -and $c.result.pipe_retired -ceq $true -and $c.result.parent_guards_held_through_exit -ceq $true -and $c.result.controller_handshake_begun -ceq $true) 'Parent lifetime'
    Need ($c.result.exit_observation.child_native_exit -eq 0 -and $c.result.exit_observation.process_wait_observed -ceq $true -and $c.result.exit_observation.job_active_processes -eq 0 -and $h.result.child_flow_return -eq 0) 'Observed child/job exit'
    Need (@($c.result.write_access_observations).Count -eq 10) 'Write probe membership'
    Need ($h.result.adoption.status -ceq 'released' -and $h.result.adoption.owned_members -eq 5 -and $h.result.adoption.inheritance_cleared -eq 5 -and $h.result.adoption.identities_checked -eq 5 -and $h.result.adoption.materialization_started -ceq $true -and $h.result.adoption.read_set_unconfirmed -ceq $false -and $h.result.adoption.read_set_released -ceq $true -and $h.result.adoption.complete_native_namespace_protection -ceq $false) 'Child adoption/lifetime'
    Need ($h.result.readback.payload_bytes -eq 328 -and @($h.result.readback.members).Count -eq 5 -and @($h.result.adoption.observed_identities).Count -eq 5 -and @($h.result.adoption.handles_closed).Count -eq 5) 'Readback/identity membership'
    Need ($b.sources.Count -eq 9 -and $b.controls.Count -eq 3 -and $b.native_inputs.Count -eq 9 -and $b.fixtures.Count -eq 5 -and $a.source_and_controls.Count -eq 12 -and $a.support_and_fixtures.Count -eq 14 -and $a.inputs_unchanged -ceq $true) 'Input membership'
    for($i=0;$i -lt 5;$i++){
        $name=$names[$i];$fixture=$b.fixtures[$i];$member=$h.result.readback.members[$i]
        Fields $member @('name','bytes','sha256') 'readback member'
        Need ($fixture.name -ceq $name -and $member.name -ceq $name -and $member.bytes -eq $fixture.bytes -and $member.sha256 -ceq $fixture.sha256 -and $h.result.adoption.handles_closed[$i] -ceq $true) 'Fixture readback and closure'
        Need ((Same $h.result.adoption.observed_identities[$i] $c.result.authenticated_manifest.members[$i].identity)) 'Child/parent identity equality'
        $p=$c.result.write_access_observations[$i];$q=$c.result.write_access_observations[$i+5]
        Need ($p.write_open_refused -ceq $true -and $p.winerror -eq 32 -and $q.write_open_succeeded -ceq $true -and $q.bytes_written -eq 0) 'Share denial/release'
        foreach($r in @($c,$h)){Fields $r.generated_asset_io.$name @('seeks','reads','bytes') 'asset I/O'}
        Need ($c.generated_asset_io.$name.seeks -eq 0 -and $c.generated_asset_io.$name.reads -eq 0 -and $c.generated_asset_io.$name.bytes -eq 0 -and $h.generated_asset_io.$name.seeks -eq 1 -and $h.generated_asset_io.$name.reads -eq 2 -and $h.generated_asset_io.$name.bytes -eq $fixture.bytes) 'Child-only retained file reads'
    }
    foreach($v in @($b.sources)+@($b.controls)){
        $rows=@($a.source_and_controls | Where-Object {$_.name -ceq $v.name});Need ($rows.Count -eq 1) 'Source after membership'
        $z=$rows[0];Need ($z.before_sha256 -ceq $v.sha256 -and $z.source_after_sha256 -ceq $v.sha256 -and $z.copy_after_sha256 -ceq $v.sha256) 'Source before/after'
        Need ((Get-FileHash -LiteralPath $v.path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $v.sha256 -and (Get-FileHash -LiteralPath (Join-Path $dir $v.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $v.sha256) 'Current text source bindings'
    }
    foreach($v in @($b.native_inputs)+@($b.fixtures)){
        $rows=@($a.support_and_fixtures | Where-Object {$_.path -ceq $v.path});Need ($rows.Count -eq 1) 'Other after membership'
        $z=$rows[0];Need ($z.bytes -eq $v.bytes -and $z.before_sha256 -ceq $v.sha256 -and $z.after_sha256 -ceq $v.sha256) 'Recorded support/fixture before-after'
    }
    Fields $n @('schema','child_returned','native_exit') 'native exit'; Fields $e @('case','controller_native_exit','expected_child_native_exit','outer_exit','inputs_unchanged','receipt_valid','receipt_error_type','stdout_bytes','stderr_bytes','operation_mode','scope') 'launcher exit'
    Need ($n.native_exit -eq 0 -and $n.child_returned -ceq $true -and $e.controller_native_exit -eq 0 -and $e.outer_exit -eq 0 -and $e.receipt_valid -ceq $true -and $e.inputs_unchanged -ceq $true -and $e.receipt_error_type -eq $null -and $e.stdout_bytes -eq 0 -and $e.stderr_bytes -eq 0 -and $outer.exit_code -eq 0) 'Native/launcher/tool outcomes'
    Need ((Get-Item -LiteralPath "$dir\controller-stdout.log").Length -eq 0 -and (Get-Item -LiteralPath "$dir\controller-stderr.log").Length -eq 0) 'Actual empty logs'
    $summaries += [ordered]@{mode=$mode;receipt_fields_present=$true;segment_count=$count;cursor_state=$state;actions=$actions;controller_seconds=$c.elapsed_seconds;child_seconds=$h.elapsed_seconds;actual_tool=$outer;dispatch_controller=$c.fixed_dispatch_completed_calls;dispatch_child=$h.fixed_dispatch_completed_calls;sources_and_controls=12;recorded_support_and_fixtures=14;support_files_reopened=$false;native_model_scope=$false}
}
$entries=@();$groups=@()
foreach($pair in @(@('generated-operation-facade-proposal01','source-proposal'),@('generated-operation-native-proposal01','native-preparation'),@('generated-operation-drain01','drain01'),@('generated-operation-cancel01','cancel01'))){
    $dir=Join-Path $taskScratch $pair[0];$files=@(Get-ChildItem -LiteralPath $dir -File -Recurse -Force | Sort-Object FullName)
    foreach($file in $files){
        Need (-not ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Linked documentary input refused'
        $rel=[IO.Path]::GetRelativePath($dir,$file.FullName).Replace([char]92,[char]47)
        $entries += [ordered]@{source=$file.FullName;destination=$pair[1]+'/'+$rel;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $groups += [ordered]@{source_directory=$dir;destination_directory=$pair[1];files=$files.Count}
}
$external=@('GENERATED-OPERATION-DRAIN01-ACTUAL.json','GENERATED-OPERATION-CANCEL01-ACTUAL.json','GENERATED-OPERATION-DRAIN-ADMISSION01-ACTUAL.json','GENERATED-OPERATION-DRAIN-ADMISSION02-ACTUAL.json','GENERATED-OPERATION-CANCEL-ADMISSION01-ACTUAL.json','GENERATED-OPERATION-ADMISSION-WRITE-REPAIR.md')
foreach($name in $external){$path=Join-Path $taskScratch $name;$file=Get-Item -LiteralPath $path;$entries += [ordered]@{source=$path;destination='integrator-history/'+$name;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}}
Need (@($entries.destination | Select-Object -Unique).Count -eq $entries.Count) 'Duplicate destination'
foreach($pair in @(@('generated-operation-facade-proposal01',16),@('generated-operation-native-proposal01',20))){
    $dir=Join-Path $taskScratch $pair[0];$m=ReadJson "$dir\PREPARATION-MANIFEST.json";Need ($m.files.Count -eq $pair[1]) 'Original preparation count'
    foreach($row in $m.files){$path=Join-Path $dir $row.path;Need ((Get-Item -LiteralPath $path).Length -eq $row.bytes -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Original preparation payload changed'}
}
SaveFresh 'RECEIPT-REVIEW.json' ([ordered]@{scope='Read-only independent retained-receipt triage; no native rerun or candidate import';observations=$summaries;missing_expected_fields=@();current_text_bindings_match=$true;original_preparations_verified=@(16,20);native_support_not_reopened=$true})
SaveFresh 'COPY-PLAN.json' ([ordered]@{status='PLAN ONLY; no copy or integration executed';payload_count=$entries.Count;payload_bytes=($entries | Measure-Object -Property bytes -Sum).Sum;groups=$groups;external_records=$external;generated_fixture_note='Ten explicitly generated ASCII placeholders, including two 60-byte model.bin names, are retained as fixture evidence; no real model or installed support is included.';entries=$entries})
[ordered]@{observations=$summaries.Count;missing_expected_fields=0;copy_payloads=$entries.Count;copy_bytes=($entries | Measure-Object -Property bytes -Sum).Sum} | ConvertTo-Json
