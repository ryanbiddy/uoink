$ErrorActionPreference='Stop'
$p='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-retirement01'
$l='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-native-proposal01\run_interrupted_owner01.ps1'
$names=@('before.json','exit.json','native-exit.json','controller-result.json','contender-result.json','child-receipt-observation.json','closed-journal-observation.json','interrupted-journal-observation.json')
$bindings=@();$data=@{}
foreach($name in $names){$path=Join-Path $p $name;$bytes=[IO.File]::ReadAllBytes($path);$bindings+= [ordered]@{path=$path;bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()};$data[$name]=[Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json}
$bindings += [ordered]@{path=$l;bytes=(Get-Item -LiteralPath $l).Length;sha256=(Get-FileHash -LiteralPath $l -Algorithm SHA256).Hash.ToLowerInvariant()}
if($bindings[-1].sha256 -cne '902699e2d05fedc2b850dc952e3d14fc063ee62b5276e9724cfe876e5ac71ac6'){throw 'Frozen launcher binding'}
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
[ordered]@{scope='Independent passive data comparisons of every nonthrowing validity predicate; launcher not executed';predicate_lines=$found;comparison_count=$rows.Count;failed_comparisons=$failures.Count;failures=$failures;all_comparisons=@($rows.ToArray());selected_inputs_unchanged=$true;bindings=$bindings;original_exit=$data['exit.json'];throwing_checks_not_reexecuted=$true;journal_observation_present=($null -ne $data['interrupted-journal-observation.json'])} | ConvertTo-Json -Depth 12
