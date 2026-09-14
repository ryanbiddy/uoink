import fs from 'node:fs';
const s='_scratch/interrupted-native-run01-launcher-diagnosis01/compare_saved_predicates01.ps1';
let text=fs.readFileSync(s,'utf8').replaceAll('windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02').replaceAll('windows-interrupted-owner-native-proposal01','windows-interrupted-owner-native-proposal02').replaceAll('run_interrupted_owner01.ps1','run_interrupted_owner02.ps1').replaceAll('902699e2d05fedc2b850dc952e3d14fc063ee62b5276e9724cfe876e5ac71ac6','0ca7fa0fa81596c14659117f4e92688eea83b06d0d57a3e68073fa5922e8cc4f');
const marker="[ordered]@{scope='Independent passive data comparisons";
if(text.split(marker).length!==2)throw Error('One result marker');
text=text.slice(0,text.indexOf(marker));
text+=String.raw`
if($rows.Count -ne 116 -or $failures.Count -ne 0){throw '116 passive comparisons must pass'}
$after=Get-Content -LiteralPath (Join-Path $p 'after.json') -Raw | ConvertFrom-Json
if($after.inputs_unchanged -cne $true -or @($after.source_and_controls).Count -ne 32 -or @($after.support_and_fixtures).Count -ne 14){throw 'Saved input pair counts'}
foreach($input in @($before.sources)+@($before.controls)){
  $pair=@($after.source_and_controls | Where-Object {$_.name -ceq $input.name})
  if($pair.Count -ne 1 -or $pair[0].before_sha256 -cne $input.sha256 -or $pair[0].source_after_sha256 -cne $input.sha256 -or $pair[0].copy_after_sha256 -cne $input.sha256){throw 'Saved source pair'}
  foreach($textPath in @($input.path,(Join-Path $p $input.name))){if((Get-FileHash -LiteralPath $textPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $input.sha256){throw 'Current source/control text binding'}}
}
foreach($input in @($before.native_inputs)+@($before.fixtures)){
  $pair=@($after.support_and_fixtures | Where-Object {$_.path -ceq $input.path})
  if($pair.Count -ne 1 -or $pair[0].bytes -ne $input.bytes -or $pair[0].before_sha256 -cne $input.sha256 -or $pair[0].after_sha256 -cne $input.sha256){throw 'Recorded support/fixture metadata pair'}
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
`;
fs.writeFileSync('_scratch/check-native02-root-receipts.ps1',text,{flag:'wx'});
console.log(JSON.stringify({created:'_scratch/check-native02-root-receipts.ps1',bytes:Buffer.byteLength(text)}));
