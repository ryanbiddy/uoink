$ErrorActionPreference='Stop'
# Passive analysis of saved JSON only. Never invoke the launcher or candidate.
$run='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-retirement01'
$out='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-native-run01-peer-diagnosis01\SOFT-PREDICATES.json'
$inputs=@('controller-result.json','contender-result.json','before.json')
$hashes=@{}
foreach($name in $inputs){$hashes[$name]=(Get-FileHash -LiteralPath (Join-Path $run $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$c=Get-Content -LiteralPath (Join-Path $run $inputs[0]) -Raw | ConvertFrom-Json
$t=Get-Content -LiteralPath (Join-Path $run $inputs[1]) -Raw | ConvertFrom-Json
$before=Get-Content -LiteralPath (Join-Path $run $inputs[2]) -Raw | ConvertFrom-Json
$r=$c.result
$checks=[Collections.Generic.List[object]]::new()
function Record($line,$id,$failed){$checks.Add([ordered]@{launcher_line=$line;id=$id;failed=[bool]$failed})}
foreach($v in @($c,$t)){
    Record 117 ($v.role+':complete_guard') ($v.schema -cne 'uoink.generated-windows-interrupted-owner-retirement.v1' -or $v.operation_mode -cne 'drain' -or $v.case -cne 'positive' -or $v.guard_valid -cne $true -or $v.model_calls -ne 0 -or @($v.model_imports).Count -ne 0 -or @($v.guard_denials).Count -ne 0 -or $v.metadata_traps -ne 12 -or $v.registry_traps -ne 25 -or $null -ne $v.error_type -or $v.pending_pipe_operations -ne 0)
    Record 118 ($v.role+':budget') ($v.work_budget_closed -cne $false -or @($v.reserved_cleanup_calls).Count -ne 0 -or $v.kernel32_path_verified -cne $true)
    $casts=0;if($v.role -ceq 'controller'){$casts=2}
    $dispatches=34+@($v.native_api_calls).Count+$casts
    Record 122 ($v.role+':dispatch') ($v.fixed_dispatch_valid -cne $true -or $v.fixed_dispatch_function_count -ne 33 -or $v.fixed_dispatch_invalid_contexts -ne 0 -or $v.fixed_attribute_cast_calls -ne $casts -or $v.fixed_dispatch_completed_calls -ne $dispatches -or $v.fixed_dispatch_audit_events -ne $dispatches)
    foreach($s in $before.sources){Record 123 ($v.role+':source:'+ $s.name) ($v.source_sha256.($s.name) -cne $s.sha256)}
    Record 170 ($v.role+':adapter_state_count') (@($v.adapter_state.PSObject.Properties).Count -ne 5)
    foreach($name in @('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')){Record 171 ($v.role+':adapter:'+ $name) ($v.adapter_state.$name -isnot [bool] -or $v.adapter_state.$name -cne $true)}
}
Record 142 'write_probe_count' (@($r.write_access_observations).Count -ne 10)
$failedProbeDetails=@()
for($i=0;$i -lt 5;$i++){
    $locked=$r.write_access_observations[$i];$opened=$r.write_access_observations[$i+5]
    Record 146 ('write_probe_pair:'+ $i) ($locked.write_open_refused -cne $true -or $locked.winerror -ne 32 -or $opened.write_open_succeeded -cne $true -or $opened.bytes_written -ne 0)
    $failedProbeDetails += [ordered]@{index=$i;locked_row=$locked;post_index=$i+5;post_row=$opened;locked_refused_condition=($locked.write_open_refused -ceq $true);locked_error32_condition=($locked.winerror -eq 32);post_success_condition=($opened.write_open_succeeded -ceq $true);post_zero_write_condition=($opened.bytes_written -eq 0)}
}
$manifest=$r.authenticated_manifest
Record 149 'manifest_membership' ($manifest.schema -cne 'uoink.generated-inherited-readset.v1' -or $manifest.case -cne 'positive' -or @($manifest.members).Count -ne 5)
$canonicalRows=@()
for($i=0;$i -lt 5;$i++){
    $row=$manifest.members[$i];$identity=$row.identity;$fixture=$before.fixtures[$i]
    Record 154 ('manifest_member:'+ $i) ($row.name -cne $fixture.name -or $row.sha256 -cne $fixture.sha256 -or $identity.size -ne $fixture.bytes)
    $canonicalIdentity=[ordered]@{directory=$identity.directory;file_id=$identity.file_id;final_path=$identity.final_path;links=$identity.links;size=$identity.size;volume_serial=$identity.volume_serial}
    $canonicalRows += [ordered]@{handle=$row.handle;identity=$canonicalIdentity;name=$row.name;sha256=$row.sha256}
}
$canonical=[ordered]@{case=$manifest.case;members=$canonicalRows;namespace_sha256=$manifest.namespace_sha256;schema=$manifest.schema}|ConvertTo-Json -Compress -Depth 8
$manifestHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($canonical))).ToLowerInvariant()
Record 160 'manifest_hash' ($manifestHash -cne $r.manifest_sha256)
$authority=@('generated_release','generated_admit','generated_bind','owned_start_validated','worker_start_bound')
Record 174 'authority_count' (@($r.authority_events).Count -ne 5)
for($i=0;$i -lt 5;$i++){Record 175 ('authority_event:'+ $i) ($r.authority_events[$i] -cne $authority[$i])}
Record 176 'actual_adapter_binding' ($r.actual_adapter_context -cne 'faster_whisper_session' -or $r.binding_calls -ne 1)
foreach($name in @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit')){Record 178 ('adapter_result:'+ $name) ($r.$name -isnot [bool] -or $r.$name -cne $true)}
$policy=[ordered]@{action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true;generated_root=$run;inherited_manifest_sha256=$r.manifest_sha256;local_files_only=$true;namespace_sha256='f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9';profile_id='generated-asr-reliability-v1';real_runtime_approved=$false;recipe_sha256='6ab3c738b582349fc5e0fd4ff13f1060df960fc2c7ab2171abf01a2292c1fd33';revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf';usage='reliability'}
Record 190 'policy_count' (@($r.adapter_start.PSObject.Properties).Count -ne $policy.Count)
foreach($name in $policy.Keys){$value=$r.adapter_start.$name;$expected=$policy[$name];Record 194 ('policy:'+ $name) ($null -eq $value -or $value.GetType() -ne $expected.GetType() -or $value -cne $expected)}
$policyCanonical=$policy|ConvertTo-Json -Compress -Depth 5
$policyHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($policyCanonical))).ToLowerInvariant()
$ack=$r.adapter_start_ack
Record 197 'policy_ack' (@($ack.PSObject.Properties).Count -ne 3 -or $ack.action -cne 'generated_adapter_start_bound' -or $ack.policy_sha256 -cne $policyHash -or ($ack.model_calls -isnot [long] -and $ack.model_calls -isnot [int]) -or $ack.model_calls -ne 0)
foreach($name in $inputs){if((Get-FileHash -LiteralPath (Join-Path $run $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hashes[$name]){throw 'Saved input changed'}}
$result=[ordered]@{scope='Passive JSON-only diagnosis of every direct soft-failure predicate in frozen launcher902699e2';recorded_source_count=@($before.sources).Count;predicate_instances=$checks.Count;failed_instances=@($checks|Where-Object {$_.failed}).Count;checks=@($checks);probe_details=$failedProbeDetails;input_sha256=$hashes;inputs_unchanged=$true;subject_execution=$false;native_execution=$false;fixture_or_physical_journal_access=$false}
$encoded=[Text.UTF8Encoding]::new($false).GetBytes(($result|ConvertTo-Json -Depth 10))
$stream=[IO.File]::Open($out,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$stream.Write($encoded,0,$encoded.Length);$stream.Flush($true)}finally{$stream.Dispose()}
[ordered]@{predicate_instances=$checks.Count;failed_instances=@($checks|Where-Object {$_.failed}).Count;failed=@($checks|Where-Object {$_.failed});output=$out;inputs_unchanged=$true;subject_execution=$false}|ConvertTo-Json -Depth 5
