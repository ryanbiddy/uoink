$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskTarget=Join-Path $taskBase '_scratch\vad-fixed-converter-proposal01'
$taskSource=Join-Path $taskBase '_scratch\vad-selected-metadata-map01\mapping.json'
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca') {throw 'Reviewed mapping mismatch'}
$taskMap=Get-Content -Raw -LiteralPath $taskSource | ConvertFrom-Json
$taskRows=@();$taskStores=@()
foreach($taskRow in $taskMap.tensor_rows){$taskRows += [ordered]@{key=$taskRow.key;shape=$taskRow.size.values;stride=$taskRow.stride.values;storage_key=$taskRow.storage.key_literal;offset_elements=$taskRow.storage_offset.value;key_ref=$taskRow.key_ref;tensor_ref=$taskRow.reducer_ref;offset_ref=$taskRow.storage_offset.ref}}
foreach($taskGroup in ($taskMap.tensor_rows | Group-Object {$_.storage.key_literal})){ $taskFirst=$taskGroup.Group[0];$taskStores += [ordered]@{key=$taskGroup.Name;elements=$taskFirst.storage.elements_literal;bytes=$taskFirst.candidate_member_name_association_not_storage_resolution.uncompressed_bytes} }
$taskPlan=[ordered]@{schema='uoink.fixed-vad.converter-plan.v1';mapping_sha256='b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca';recorded_storage_global='torch FloatStorage';proposed_output_dtype='F32';proposed_source_byte_order_requires_profile=$true;rows=$taskRows;storages=$taskStores;total_elements=1472999;total_output_data_bytes=5891996}
$taskOut=Join-Path $taskTarget 'fixed-plan.json'
if (Test-Path -LiteralPath $taskOut){throw 'Refuse overwrite'}
$taskPlan | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $taskOut -Encoding utf8
[ordered]@{rows=$taskRows.Count;storages=$taskStores.Count;sha256=(Get-FileHash -LiteralPath $taskOut -Algorithm SHA256).Hash.ToLowerInvariant();exit=0} | ConvertTo-Json
