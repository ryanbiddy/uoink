$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$delivery=Join-Path $root '_scratch/real-child-namespace01-root-review'
$pins=Join-Path $delivery 'FROZEN-SOURCE-PINS.json'
if((Get-FileHash -LiteralPath $pins -Algorithm SHA256).Hash.ToLowerInvariant() -cne '75d20134558f5cebf61a8dc219d8652bf9d592a1ca29d835d757c8fd749fa124'){throw 'Freeze pin mismatch'}
$pinmap=Get-Content -LiteralPath $pins -Raw | ConvertFrom-Json
$total=[int64]0
foreach($row in $pinmap.files){$p=Join-Path $delivery $row.path; $f=Get-Item -LiteralPath $p -Force; if($f.Length -ne $row.bytes -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -or (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256){throw ('Frozen mismatch '+$row.path)}; $total += [int64]$row.bytes}
$frozen=Join-Path $delivery 'frozen'
$inputmap=Get-Content -LiteralPath (Join-Path $frozen 'SOURCE-INPUTS.json') -Raw | ConvertFrom-Json
foreach($row in $inputmap.derivatives){$p=Join-Path $frozen $row.path; if((Get-Item -LiteralPath $p).Length -ne $row.bytes -or (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256){throw 'Derivative map mismatch'}}
foreach($row in $inputmap.inputs){foreach($p in @((Join-Path $frozen $row.local_path),(Join-Path $root $row.source_path))){if((Get-Item -LiteralPath $p).Length -ne $row.bytes -or (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256){throw ('Before/source map mismatch '+$p)}}}
$oldPath=Join-Path $frozen 'before/asr_loading_adapter.py'
$newPath=Join-Path $frozen 'asr_loading_adapter.py'
$old=[IO.File]::ReadAllText($oldPath)
$new=[IO.File]::ReadAllText($newPath)
$start=$new.IndexOf('def _validate_controller_stage_locked(')
$end=$new.IndexOf('def _fixed_real_worker_start(',$start)
if($start -lt 0 -or $end -le $start -or $new.Remove($start,$end-$start) -cne $old){throw 'Whole-source inverse mismatch'}
$added=$new.Substring($start,$end-$start)
if($old.Insert($start,$added) -cne $new){throw 'Whole-source forward mismatch'}
$diff=[IO.File]::ReadAllLines((Join-Path $frozen 'asr_loading_adapter.diff'))
if($diff[0] -cne '--- before/asr_loading_adapter.py' -or $diff[1] -cne '+++ asr_loading_adapter.py' -or $diff[2] -cne '@@ -463,6 +463,80 @@'){throw 'Hunk header mismatch'}
$minus=@();$plus=@()
foreach($line in $diff[3..($diff.Length-1)]){if($line.StartsWith(' ')){$minus+=$line.Substring(1);$plus+=$line.Substring(1)}elseif($line.StartsWith('-')){$minus+=$line.Substring(1)}elseif($line.StartsWith('+')){$plus+=$line.Substring(1)}else{throw 'Unexpected hunk row'}}
$oldLines=[IO.File]::ReadAllLines($oldPath);$newLines=[IO.File]::ReadAllLines($newPath)
if($minus.Count -ne 6 -or $plus.Count -ne 80 -or ($minus -join "`n") -cne ($oldLines[462..467] -join "`n") -or ($plus -join "`n") -cne ($newLines[462..541] -join "`n")){throw 'Hunk/source relation mismatch'}
$review=Join-Path $root '_scratch/child-namespace01-controller-peer'
if(Test-Path -LiteralPath $review){throw 'Review folder already exists'}
[IO.Directory]::CreateDirectory((Join-Path $review 'before')) | Out-Null
[IO.File]::Copy($oldPath,(Join-Path $review 'before/asr_loading_adapter.py'),$false)
$observed=@(foreach($p in @($oldPath,$newPath,(Join-Path $frozen 'asr_loading_adapter.diff'),(Join-Path $frozen 'admitted_namespace_flow.py'),(Join-Path $root '_scratch/windows-interrupted-owner-native-proposal02/snapshot_lifecycle.py'),(Join-Path $root '_scratch/windows-interrupted-owner-native-proposal02/durable_lifecycle.py'))){[ordered]@{path=$p.Substring($root.Length+1).Replace('\','/');bytes=(Get-Item -LiteralPath $p).Length;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}})
$obs=[ordered]@{scope='Source-byte preservation only; not candidate qualification';frozen_pin_sha256='75d20134558f5cebf61a8dc219d8652bf9d592a1ca29d835d757c8fd749fa124';frozen_files=$pinmap.files.Count;frozen_bytes=$total;derivative_map_rows=$inputmap.derivatives.Count;original_copy_rows=$inputmap.inputs.Count;adapter_full_forward_reverse_exact=$true;adapter_unified_hunks=1;adapter_added_lines=74;selected_sources=$observed;candidate_execution=$false}
[IO.File]::WriteAllText((Join-Path $review 'SOURCE-OBSERVATIONS.json'),($obs|ConvertTo-Json -Depth 7)+"`n",[Text.UTF8Encoding]::new($false))
$obs | ConvertTo-Json -Depth 7 -Compress
