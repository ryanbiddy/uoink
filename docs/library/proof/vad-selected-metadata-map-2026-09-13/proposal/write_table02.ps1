$ErrorActionPreference='Stop'
$taskDir='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-selected-metadata-map01'
$taskMapPath=Join-Path $taskDir 'mapping.json'
if ((Get-FileHash -LiteralPath $taskMapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca') { throw 'Mapping digest mismatch' }
$taskMap=Get-Content -Raw -LiteralPath $taskMapPath | ConvertFrom-Json
$taskLines=@('# Tensor views and whole-storage declarations','','These are literal declarations and arithmetic from the safe JSON receipt. The original table remains in tensor-table.md. Storage key 16 is shared by 32 tensor views: count its 5,521,408 whole-storage bytes once. Across 23 distinct keys, the advertised storage total is 5,891,996 bytes. No storage payload was read and no dtype, tensor values or numerical behavior was validated.','','| Key (key ref) | Tensor ref | Storage key | Offset ref: elements | Size ref: dimensions | Stride ref: elements | Tensor shape product | Whole-storage declared elements | Whole-storage advertised bytes (repeats) |','| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: |')
foreach($taskRow in $taskMap.tensor_rows) {
    $taskLines += '| ' + $taskRow.key + ' (' + $taskRow.key_ref + ') | ' + $taskRow.reducer_ref + ' | ' + $taskRow.storage.key_literal + ' | ' + $taskRow.storage_offset.ref + ': ' + $taskRow.storage_offset.value + ' | ' + $taskRow.size.ref + ': [' + ($taskRow.size.values -join ', ') + '] | ' + $taskRow.stride.ref + ': [' + ($taskRow.stride.values -join ', ') + '] | ' + $taskRow.declaration_arithmetic_only.shape_product + ' | ' + $taskRow.storage.elements_literal + ' | ' + $taskRow.candidate_member_name_association_not_storage_resolution.uncompressed_bytes + ' |'
}
$taskOut=Join-Path $taskDir 'tensor-table02.md'
if (Test-Path -LiteralPath $taskOut) { throw 'Refuse overwrite' }
$taskLines -join "`n" | Set-Content -LiteralPath $taskOut -Encoding utf8
[ordered]@{status='clarified_table_written';rows=$taskMap.tensor_rows.Count;sha256=(Get-FileHash -LiteralPath $taskOut -Algorithm SHA256).Hash.ToLowerInvariant();exit=0} | ConvertTo-Json
