$ErrorActionPreference='Stop'
$p='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-retirement02'
$l='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-native-proposal02\run_interrupted_owner02.ps1'
$names=@('before.json','exit.json','native-exit.json','controller-result.json','contender-result.json','child-receipt-observation.json','closed-journal-observation.json','interrupted-journal-observation.json')
$bindings=@();$data=@{}
foreach($name in $names){$path=Join-Path $p $name;$bytes=[IO.File]::ReadAllBytes($path);$bindings+= [ordered]@{path=$path;bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()};$data[$name]=[Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json}
$bindings += [ordered]@{path=$l;bytes=(Get-Item -LiteralPath $l).Length;sha256=(Get-FileHash -LiteralPath $l -Algorithm SHA256).Hash.ToLowerInvariant()}
if($bindings[-1].sha256 -cne '0ca7fa0fa81596c14659117f4e92688eea83b06d0d57a3e68073fa5922e8cc4f'){throw 'Frozen launcher binding'}
$before=$data['before.json'];$controller=$data['controller-result.json'];$contender=$data['contender-result.json'];$result=$controller.result
$rows=[Collections.Generic.List[object]]::new()
function Record([int]$line,[string]$label,[bool]$passed,$observed){$rows.Add([ordered]@{launcher_line=$line;label=$label;passed=$passed;observed=$observed})}
foreach($receipt in @($controller,$contender)){
    Record 117 ($receipt.role+': guards') (-not ($receipt.schema -cne 'uoink.generated-windows-interrupted-owner-retirement.v1' -or $receipt.operation_mode -cne 'drain' -or $receipt.case -cne 'positive' -or $receipt.guard_valid -cne $true -or $receipt.model_calls -ne 0 -or @($receipt.model_imports).Count -ne 0 -or @($receipt.guard_denials).Count -ne 0 -or $receipt.metadata_traps -ne 12 -or $receipt.registry_traps -ne 25 -or $null -ne $receipt.error_type -or $receipt.pending_pipe_operations -ne 0)) $null
    Record 118 ($receipt.role+': budget') (-not ($receipt.work_budget_closed -cne $false -or @($receipt.reserved_cleanup_calls).Count -ne 0 -or $receipt.kernel32_path_verified -cne $true)) $null
    $casts=0;if($receipt.role -ceq 'controller'){$casts=2}
    $dispatch=34+@($receipt.native_api_calls).Count+$casts
    Record 122 ($receipt.role+': dispatch') (-not ($receipt.fixed_dispatch_valid -cne $true -or $receipt.fixed_dispatch_function_count -ne 33 -or $receipt.fixed_dispatch_invalid_contexts -ne 0 -or $receipt.fixed_attribute_cast_calls -ne $casts -or $receipt.fixed_dispatch_completed_calls -ne $dispatch -or $receipt.fixed_dispatch_audit_events -ne $dispatch)) ([ordered]@{native_api_count=@($receipt.native_api_calls).Count;dispatch=$dispatch})
    foreach($source in $before.sources){Record 123 ($receipt.role+': source '+$source.name) ($receipt.source_sha256.($source.name) -ceq $source.sha256) $null}
}
Record 142 'Ten write observations' (@($result.write_access_observations).Count -eq 10) ([ordered]@{expected=10;actual=@($result.write_access_observations).Count})
for($i=0;$i -lt 5;$i++){
    $locked=$result.write_access_observations[$i];$opened=$result.write_access_observations[$i+5]
    Record 146 ('Write pair '+$i) (-not ($locked.write_open_refused -cne $true -or $locked.winerror -ne 32 -or $opened.write_open_succeeded -cne $true -or $opened.bytes_written -ne 0)) ([ordered]@{expected_first=[ordered]@{write_open_refused=$true;winerror=32};actual_first=$locked;expected_second=[ordered]@{write_open_succeeded=$true;bytes_written=0};actual_second=$opened})
}
$manifest=$result.authenticated_manifest
Record 149 'Manifest membership' (-not ($manifest.schema -cne 'uoink.generated-inherited-readset.v1' -or $manifest.case -cne 'positive' -or @($manifest.members).Count -ne 5)) $null
$canonicalRows=@()
for($i=0;$i -lt 5;$i++){
    $row=$manifest.members[$i];$id=$row.identity;$fixture=$before.fixtures[$i]
    Record 154 ('Manifest member '+$i) (-not ($row.name -cne $fixture.name -or $row.sha256 -cne $fixture.sha256 -or $id.size -ne $fixture.bytes)) $null
    $canonicalIdentity=[ordered]@{directory=$id.directory;file_id=$id.file_id;final_path=$id.final_path;links=$id.links;size=$id.size;volume_serial=$id.volume_serial}
    $canonicalRows += [ordered]@{handle=$row.handle;identity=$canonicalIdentity;name=$row.name;sha256=$row.sha256}
}
$canonical=[ordered]@{case=$manifest.case;members=$canonicalRows;namespace_sha256=$manifest.namespace_sha256;schema=$manifest.schema} | ConvertTo-Json -Compress -Depth 8
$digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($canonical))).ToLowerInvariant()
Record 160 'Manifest hash' ($digest -ceq $result.manifest_sha256) $digest
foreach($receipt in @($controller,$contender)){
    Record 170 ($receipt.role+': adapter count') (@($receipt.adapter_state.PSObject.Properties).Count -eq 5) $null
    foreach($name in @('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')){Record 171 ($receipt.role+': adapter '+$name) ($receipt.adapter_state.$name -is [bool] -and $receipt.adapter_state.$name -ceq $true) $null}
}
$expectedEvents=@('generated_release','generated_admit','generated_bind','owned_start_validated','worker_start_bound')
Record 174 'Authority event count' (@($result.authority_events).Count -eq 5) $null
for($i=0;$i -lt 5;$i++){Record 175 ('Authority event '+$i) ($result.authority_events[$i] -ceq $expectedEvents[$i]) $null}
Record 176 'Actual adapter context/count' ($result.actual_adapter_context -ceq 'faster_whisper_session' -and $result.binding_calls -eq 1) $null
foreach($name in @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit')){Record 178 ('Actual adapter '+$name) ($result.$name -is [bool] -and $result.$name -ceq $true) $null}
$expectedPolicy=[ordered]@{
    action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true
    generated_root=$p;inherited_manifest_sha256=$result.manifest_sha256;local_files_only=$true
    namespace_sha256='f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9';profile_id='generated-asr-reliability-v1';real_runtime_approved=$false
    recipe_sha256='6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33';revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf';usage='reliability'
}
$canonical=$expectedPolicy | ConvertTo-Json -Compress -Depth 5
$policyDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($canonical))).ToLowerInvariant()
Record 190 'Policy count' (@($result.adapter_start.PSObject.Properties).Count -eq $expectedPolicy.Count) $null
foreach($name in $expectedPolicy.Keys){$value=$result.adapter_start.$name;$expected=$expectedPolicy[$name];Record 194 ('Policy '+$name) ($null -ne $value -and $value.GetType() -eq $expected.GetType() -and $value -ceq $expected) $null}
$ack=$result.adapter_start_ack
Record 197 'Policy ack' (-not (@($ack.PSObject.Properties).Count -ne 3 -or $ack.action -cne 'generated_adapter_start_bound' -or $ack.policy_sha256 -cne $policyDigest -or ($ack.model_calls -isnot [long] -and $ack.model_calls -isnot [int]) -or $ack.model_calls -ne 0)) $policyDigest
$expectedLines=@(117,118,122,123,142,146,149,154,160,170,171,174,175,176,178,190,194,197)
$found=@($rows | ForEach-Object {$_.launcher_line} | Sort-Object -Unique)
if(($found -join ',') -cne ($expectedLines -join ',')){throw 'Predicate line coverage'}
foreach($binding in $bindings){if((Get-FileHash -LiteralPath $binding.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $binding.sha256){throw 'Selected source/receipt changed'}}
$failures=@($rows | Where-Object {-not $_.passed})

if($rows.Count -ne 116 -or $failures.Count -ne 0){throw '116 passive comparisons must pass'}
$after=Get-Content -LiteralPath (Join-Path $p 'after.json') -Raw | ConvertFrom-Json
if($after.inputs_unchanged -cne $true -or @($after.source_and_controls).Count -ne 32 -or @($after.support_and_fixtures).Count -ne 14){throw 'Saved input pair counts'}
foreach($taskInputRow in @($before.sources)+@($before.controls)){
  $pair=@($after.source_and_controls | Where-Object {$_.name -ceq $taskInputRow.name})
  if($pair.Count -ne 1 -or $pair[0].before_sha256 -cne $taskInputRow.sha256 -or $pair[0].source_after_sha256 -cne $taskInputRow.sha256 -or $pair[0].copy_after_sha256 -cne $taskInputRow.sha256){throw 'Saved source pair'}
  foreach($textPath in @($taskInputRow.path,(Join-Path $p $taskInputRow.name))){if((Get-FileHash -LiteralPath $textPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInputRow.sha256){throw 'Current source/control text binding'}}
}
foreach($taskInputRow in @($before.native_inputs)+@($before.fixtures)){
  $pair=@($after.support_and_fixtures | Where-Object {$_.path -ceq $taskInputRow.path})
  if($pair.Count -ne 1 -or $pair[0].bytes -ne $taskInputRow.bytes -or $pair[0].before_sha256 -cne $taskInputRow.sha256 -or $pair[0].after_sha256 -cne $taskInputRow.sha256){throw 'Recorded support/fixture metadata pair'}
}
$exit=$data['exit.json'];$native=$data['native-exit.json'];$closed=$data['closed-journal-observation.json'];$obs=$data['interrupted-journal-observation.json'];$partial=$data['child-receipt-observation.json']
if($exit.outer_exit -ne 0 -or $exit.controller_native_exit -ne 0 -or $exit.receipt_valid -cne $true -or $exit.inputs_unchanged -cne $true -or $null -ne $exit.receipt_error_type -or $native.native_exit -ne 0 -or $native.child_returned -cne $true){throw 'Saved outer/native outcomes'}
if($exit.final_child_state_claimed -cne $false -or $exit.ordinary_parent_guard_claim_available -cne $false -or $partial.present -cne $false -or $partial.final_guard_or_clean_owner_credit -cne $false){throw 'No absent child credit'}
foreach($name in @('controller-stdout.log','controller-stderr.log')){if((Get-Item -LiteralPath (Join-Path $p $name)).Length -ne 0){throw 'Empty native logs'}}
$j=$result.durable_journal;$o=$result.interrupted_retirement_observation;$r=$result.interrupted_owner_recovery
if($o.primary_native_exit -ne 1 -or $o.primary_job_active_processes -ne 0 -or $o.ordinary_parent_guard_claim_available -cne $false -or $o.final_child_guard_or_clean_owner_claim -cne $false -or $r.owner_still_revoked -cne $true -or $r.token_still_revoked -cne $true -or $r.native_interrupt_crash_or_restart_claim -cne $false){throw 'Retained owner outcome'}
if(@($result.segments).Count -ne 1 -or ($result.operation_events -join ',') -cne 'admit_generated_media,begin_generated_transcription,next_generated_segment,next_generated_segment'){throw 'One delivered segment'}
$expected=@(@('TerminateJobObject','job',$false,1),@('WaitForSingleObject','process',$false,0),@('GetProcessTimes','process',$true,1),@('WaitForSingleObject','process',$true,0),@('GetExitCodeProcess','process',$true,1),@('QueryInformationJobObject','job',$true,1),@('CloseHandle','server',$true,1),@('CloseHandle','thread',$true,1),@('CloseHandle','process',$true,1),@('CloseHandle','job',$true,1),@('CloseHandle','member4',$true,1),@('CloseHandle','member3',$true,1),@('CloseHandle','member2',$true,1),@('CloseHandle','member1',$true,1),@('CloseHandle','member0',$true,1))
if(@($o.native_events).Count -ne 15){throw '15 events'}
$last=-1
for($i=0;$i -lt 15;$i++){$e=$o.native_events[$i];$x=$expected[$i];if($e.api -cne $x[0] -or $e.owner -cne $x[1] -or $e.manager_attempt_active_at_call -cne $x[2] -or $e.native_result -ne $x[3] -or $e.call_index -le $last -or $controller.native_api_calls[$e.call_index] -cne $e.api){throw 'Retained event sequence'};$last=$e.call_index}
$flushes=@($j.io_events | Where-Object {$_.api -ceq 'FlushFileBuffers'})
if($flushes.Count -ne 5 -or $o.native_events[1].call_index -ge $flushes[3].call_index -or $o.native_events[2].call_index -le $flushes[3].call_index -or $o.native_events[-1].call_index -ge $flushes[4].call_index){throw 'Retirement/quarantine/clear ordering'}
# Interpret only bytes already embedded in the saved controller JSON.
$bytes=[Convert]::FromHexString($j.journal_hex)
$sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
if($bytes.Length -ne 2688 -or $sha -cne $j.journal_sha256 -or $sha -cne $closed.sha256 -or $closed.bytes -ne $bytes.Length -or $closed.matches_controller_confirmed_bytes -cne $true -or $closed.exclusive_postexit_read_closed -cne $true -or $closed.power_loss_or_restart_proven -cne $false){throw 'Recorded closed-journal binding'}
if([Text.Encoding]::ASCII.GetString($bytes,0,6) -cne "UORS1"+[char]10){throw 'Journal magic'}
$phases=@('INITIALIZED','RESERVED','WORKER_BOUND','QUARANTINED','CLEARED');$offset=6;$previous='0'*64;$ends=@();$heads=@()
for($i=0;$i -lt 5;$i++){
 $n=[int]([uint64]$bytes[$offset]*16777216+[uint64]$bytes[$offset+1]*65536+[uint64]$bytes[$offset+2]*256+[uint64]$bytes[$offset+3]);$offset+=4
 if($n -le 0 -or $n -gt 4096 -or $offset+$n+32 -gt $bytes.Length){throw 'Frame bounds'}
 $payload=[byte[]]::new($n);[Array]::Copy($bytes,$offset,$payload,0,$n);$offset+=$n
 $digest=[byte[]]::new(32);[Array]::Copy($bytes,$offset,$digest,0,32);$offset+=32
 $head=[Convert]::ToHexString($digest).ToLowerInvariant();$calc=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($payload)).ToLowerInvariant()
 $frame=[Text.Encoding]::ASCII.GetString($payload) | ConvertFrom-Json
 if($calc -cne $head -or $frame.previous -cne $previous -or $frame.sequence -ne $i -or $frame.phase -cne $phases[$i] -or $frame.schema -ne 1 -or $obs.frame_heads[$i] -cne $head){throw 'Recorded frame chain'}
 $previous=$head;$heads+=$head;$ends+=$offset
}
if($offset -ne $bytes.Length -or $previous -cne $j.head -or $heads[3] -cne $o.quarantine_head -or $ends[3] -ne $obs.quarantine_prefix_bytes){throw 'Complete five-frame chain'}
$prefix=[byte[]]::new($ends[3]);[Array]::Copy($bytes,0,$prefix,0,$prefix.Length)
$prefixHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($prefix)).ToLowerInvariant()
if($prefixHash -cne $o.quarantine_sha256 -or $prefixHash -cne $obs.quarantine_prefix_sha256){throw 'Quarantine prefix hash'}
$out=[ordered]@{scope='Passive saved native02 receipt/source review only';soft_comparisons=116;soft_failures=0;source_control_pairs=32;recorded_support_fixture_pairs=14;write_observations=10;retained_events=15;controller_exit=0;primary_exit=1;primary_job_active=0;frames=5;journal_bytes=$bytes.Length;journal_sha256=$sha;prefix_bytes=$prefix.Length;prefix_sha256=$prefixHash;physical_journal_support_fixture_access=$false;native_replayed=$false;bindings=$bindings;comparisons=@($rows.ToArray())}
$out | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath '_scratch/INTERRUPTED-NATIVE02-ROOT-RECEIPT-RESULT.json' -Encoding utf8 -NoNewline
[ordered]@{soft_comparisons=116;soft_failures=0;source_control_pairs=32;recorded_support_fixture_pairs=14;write_observations=10;retained_events=15;frames=5;journal_bytes=2688;native_replayed=$false} | ConvertTo-Json -Compress
