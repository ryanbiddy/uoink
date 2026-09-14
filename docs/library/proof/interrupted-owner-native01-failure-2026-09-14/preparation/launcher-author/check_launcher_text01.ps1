$ErrorActionPreference='Stop'
$p='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-interrupted-owner-native-proposal01'
$old=[IO.File]::ReadAllText((Join-Path $p 'before\run_native_owner_cancel01.ps1')).Replace([string][char]13,'')
$new=[IO.File]::ReadAllText((Join-Path $p 'run_interrupted_owner01.ps1')).Replace([string][char]13,'')
function Cut([string]$text,[string]$start,[string]$end){
    $i=$text.IndexOf($start,[StringComparison]::Ordinal);if($i -lt 0){throw 'Missing section start'}
    $j=$text.IndexOf($end,$i,[StringComparison]::Ordinal);if($j -lt 0){throw 'Missing section end'}
    return $text.Substring($i,$j-$i)
}
$prefix=Cut $old 'param(' '$taskValid=$false'
$prefix=$prefix.Replace("ValidateSet('cancel')","ValidateSet('drain')").Replace('$taskRuns=@{cancel=','$taskRuns=@{drain=').Replace('runtime-owner-native-connection-native-proposal01','windows-interrupted-owner-native-proposal01').Replace('runtime-owner-native-connection01','windows-interrupted-owner-retirement01').Replace('run_native_owner_cancel01.ps1','run_interrupted_owner01.ps1').Replace('generated-windows-runtime-owner-cancel-only','generated-windows-interrupted-owner-retirement-only')
if($prefix -cne (Cut $new 'param(' '$taskValid=$false')){throw 'Unexpected startup/copy/exit/after change'}
if((Cut $old '# BEGIN EXACT NATIVE RECEIPT BLOCK' '# END EXACT NATIVE RECEIPT BLOCK') -cne (Cut $new '# BEGIN EXACT NATIVE RECEIPT BLOCK' '# END EXACT NATIVE RECEIPT BLOCK')){throw 'Native receipt block changed'}
if($new -match '__[A-Z_]+__' -or $new -match '\$taskChild\b' -or $new.Contains('adapter_owned_cleanup')){throw 'Unfilled placeholder or forbidden final-child claim'}
$oldWrites=Cut $old '    if(@($taskResult.write_access_observations)' '    $taskAdoption='
$newWrites=Cut $new '    if(@($taskResult.write_access_observations)' '    $taskManifest='
if($oldWrites.TrimEnd() -cne $newWrites.TrimEnd()){throw 'Write probes changed'}
$oldManifest=Cut $old '    if($taskManifest.schema' '    $taskExpectedIdentities='
$newManifest=Cut $new '    if($taskManifest.schema' '    $taskActions='
if($oldManifest.TrimEnd() -cne $newManifest.TrimEnd()){throw 'Manifest assertions changed'}
$map=Get-Content -LiteralPath (Join-Path $p 'SOURCE-INPUTS.json') -Raw | ConvertFrom-Json
if(@($map.source_paths.PSObject.Properties).Count -ne 29 -or @($map.source_sha256.PSObject.Properties).Count -ne 29 -or @($map.native_bindings.PSObject.Properties).Count -ne 9){throw 'Control-map text membership'}
foreach($row in $map.source_paths.PSObject.Properties){
    if($row.Value -cne (Join-Path $p $row.Name)){throw 'Fixed source path'}
    if((Get-FileHash -LiteralPath $row.Value -Algorithm SHA256).Hash.ToLowerInvariant() -cne $map.source_sha256.($row.Name)){throw 'Source text binding changed'}
}
$diff=[IO.File]::ReadAllLines((Join-Path $p 'run_interrupted_owner01.ps1.diff'))
$minus=@($diff | Select-Object -Skip 3 | Where-Object {$_.StartsWith('-')} | ForEach-Object {$_.Substring(1)})
$plus=@($diff | Select-Object -Skip 3 | Where-Object {$_.StartsWith('+')} | ForEach-Object {$_.Substring(1)})
$lf=[string][char]10
if(($minus -join $lf) -cne $old.TrimEnd() -or ($plus -join $lf) -cne $new.TrimEnd()){throw 'Full-hunk source reconstruction'}
$rows=@()
foreach($name in @('before\run_native_owner_cancel01.ps1','launcher-verifier.source.txt','run_interrupted_owner01.ps1','run_interrupted_owner01.ps1.diff','dummy_bootstrap.py','SOURCE-INPUTS.json','snapshot_reservations.py')){
    $file=Get-Item -LiteralPath (Join-Path $p $name)
    $rows += [ordered]@{path=$name;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{scope='Passive source text only; no parsing/compilation or candidate execution';source_rows=29;support_metadata_rows_only=9;source_control_pairs=32;prefix_exact_except_fixed_mode_path_name_scope=$true;native_exit_block_text_unchanged=$true;write_probes_unchanged=$true;manifest_assertions_unchanged=$true;no_final_child_reference=$true;full_hunk_reconstructs_both_LF_normalized_texts=$true;files=$rows} | ConvertTo-Json -Depth 7
