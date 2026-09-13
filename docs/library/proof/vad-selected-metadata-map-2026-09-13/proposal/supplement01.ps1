$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskDir=Join-Path $taskBase '_scratch\vad-selected-metadata-map01'
$taskMapPath=Join-Path $taskDir 'mapping.json'
if ((Get-FileHash -LiteralPath $taskMapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca') { throw 'Mapping hash mismatch' }
$taskMap=Get-Content -Raw -LiteralPath $taskMapPath | ConvertFrom-Json
$taskGroups=@()
foreach($taskGroup in ($taskMap.tensor_rows | Group-Object {$_.storage.key_literal})) {
    $taskEntries=@($taskGroup.Group | Sort-Object {$_.storage_offset.value})
    $taskEnd=0L
    $taskContinuous=$true
    $taskIntervals=@()
    foreach($taskRow in $taskEntries) {
        if ($taskRow.storage_offset.value -ne $taskEnd) { $taskContinuous=$false }
        if ($taskRow.storage.elements_literal -ne $taskEntries[0].storage.elements_literal) { throw 'Shared length mismatch' }
        if ($taskRow.storage.type_global_literal -ne $taskEntries[0].storage.type_global_literal) { throw 'Shared type mismatch' }
        if ($taskRow.storage.location_literal -ne $taskEntries[0].storage.location_literal) { throw 'Shared location mismatch' }
        $taskEnd=[long]$taskRow.declaration_arithmetic_only.exclusive_max_element
        $taskIntervals += [ordered]@{ key=$taskRow.key; key_ref=$taskRow.key_ref; tensor_ref=$taskRow.reducer_ref; persistent_ref=$taskRow.storage.persistent_record.id; offset_ref=$taskRow.storage_offset.ref; start_element=$taskRow.storage_offset.value; end_element_exclusive=$taskEnd; shape_product=$taskRow.declaration_arithmetic_only.shape_product }
    }
    $taskGroups += [ordered]@{ storage_key_literal=$taskGroup.Name; tensor_entries=$taskEntries.Count; declared_elements=$taskEntries[0].storage.elements_literal; advertised_member_bytes=$taskEntries[0].candidate_member_name_association_not_storage_resolution.uncompressed_bytes; declaration_intervals_contiguous_nonoverlapping_cover_storage=($taskContinuous -and $taskEnd -eq $taskEntries[0].storage.elements_literal); intervals=$taskIntervals }
}
$taskSources=@()
$taskSourceDir=Join-Path $taskDir 'additional-source'
New-Item -ItemType Directory -Path $taskSourceDir -ErrorAction Stop | Out-Null
foreach($taskSource in @(@('TORCH_INIT','torch\__init__.py','torch-init.py'),@('TORCH_RNN','torch\nn\modules\rnn.py','torch-rnn.py'),@('TORCH_UTILS','torch\_utils.py','torch-utils.py'))) {
    $taskOriginal=Join-Path $taskBase ('installer\staging\python\Lib\site-packages\'+$taskSource[1])
    if ([IO.Path]::GetExtension($taskOriginal) -ne '.py') { throw 'Source suffix mismatch' }
    $taskBefore=(Get-FileHash -LiteralPath $taskOriginal -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskRaw=[IO.File]::ReadAllBytes($taskOriginal)
    if ($taskRaw.Length -gt 160000) { throw 'Source size bound' }
    $taskSaved=Join-Path $taskSourceDir $taskSource[2]
    if (Test-Path -LiteralPath $taskSaved) { throw 'Refuse overwrite' }
    [IO.File]::WriteAllBytes($taskSaved,$taskRaw)
    $taskCopied=(Get-FileHash -LiteralPath $taskSaved -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskAfter=(Get-FileHash -LiteralPath $taskOriginal -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskBefore -ne $taskCopied -or $taskBefore -ne $taskAfter) { throw 'Source changed' }
    $taskSources += [ordered]@{ key=$taskSource[0]; source=$taskOriginal; saved_file=('additional-source/'+$taskSource[2]); bytes=$taskRaw.Length; sha256=$taskCopied; before_after_copied_equal=$true; executed=$false }
}
$taskOutput=[ordered]@{ status='receipt_declaration_arithmetic_and_source_text_only'; storage_groups=$taskGroups; distinct_storage_keys=$taskGroups.Count; distinct_advertised_storage_bytes=($taskGroups.advertised_member_bytes | Measure-Object -Sum).Sum; declared_shape_product_total=($taskMap.tensor_rows.declaration_arithmetic_only.shape_product | Measure-Object -Sum).Sum; all_group_intervals_cover_without_overlap=(@($taskGroups | Where-Object {-not $_.declaration_intervals_contiguous_nonoverlapping_cover_storage}).Count -eq 0); sources=$taskSources; checkpoint_read=$false; tensors_constructed=$false; persistent_ids_resolved=$false; exit=0 }
$taskOutPath=Join-Path $taskDir 'supplement01.json'
if (Test-Path -LiteralPath $taskOutPath) { throw 'Refuse overwrite' }
$taskOutput | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $taskOutPath -Encoding utf8
[ordered]@{ exit=0; storage_keys=$taskGroups.Count; declared_shape_products=$taskOutput.declared_shape_product_total; unique_advertised_bytes=$taskOutput.distinct_advertised_storage_bytes; intervals_cover_without_overlap=$taskOutput.all_group_intervals_cover_without_overlap; captured_source_files=$taskSources.Count } | ConvertTo-Json
