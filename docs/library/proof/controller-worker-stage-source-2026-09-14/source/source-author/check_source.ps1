$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$d=Join-Path $root '_scratch/controller-worker-stage-repair01'
$originDir=Join-Path $root '_scratch/real-startup-authority-repair01'
$origin=Get-Content -LiteralPath (Join-Path $originDir 'SOURCE-INPUTS.json') -Raw | ConvertFrom-Json
$specs=@([ordered]@{source='_scratch/real-startup-authority-repair01/asr_loading_adapter.py';copy='before/asr_loading_adapter.py';expected='6482b782c545adbcd524a68ae85ba2abb3f081683379a9d53ada66d03a5ddb51';role='accepted adapter prefix'})
foreach($row in $origin.original_inputs){$specs += [ordered]@{source=$row.source;copy=('inputs/'+[IO.Path]::GetFileName($row.source));expected=$row.sha256;role='unchanged startup81 dependency/reference'}}
foreach($name in @('startup_authority_fixture.py','test_startup_authority.py','FIXTURE-LOADER-CONTRACT.md','SOURCE-INPUTS.json')){$specs += [ordered]@{source=('_scratch/real-startup-authority-repair01/'+$name);copy=('inputs/'+$name);role='unchanged accepted fixture or origin context'}}
foreach($name in @('win32_worker_connection.py','generated_worker_flow.py')){$specs += [ordered]@{source=('_scratch/windows-interrupted-owner-native-proposal02/'+$name);copy=('reference/'+$name);role='native contract reference text only'}}
$inputRows=@(foreach($s in $specs){$src=Join-Path $root $s.source;$copy=Join-Path $d $s.copy;$hash=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant();if(($s.expected -and $hash -cne $s.expected) -or (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash){throw ('Source/copy mismatch '+$s.source)};[ordered]@{source=$s.source;copy=$s.copy;bytes=(Get-Item -LiteralPath $src).Length;sha256=$hash;role=$s.role}})
$checks=@()
foreach($name in @('asr_loading_adapter.py','worker_stage_fixture.py','test_controller_worker_stage.py')){
$new=[IO.File]::ReadAllText((Join-Path $d $name));$isAdapter=$name -ceq 'asr_loading_adapter.py';$old=if($isAdapter){[IO.File]::ReadAllText((Join-Path $d ('before/'+$name)))}else{''};$diffPath=Join-Path $d $(if($isAdapter){'asr_loading_adapter.diff'}else{$name+'.diff'});$lines=[IO.File]::ReadAllLines($diffPath)
if($new.Contains("`r") -or $old.Contains("`r")){throw 'Unexpected source line ending'}
if($lines[2] -notmatch '^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$'){throw 'Invalid complete hunk'}
$oldStart=[int]$Matches[1];$oldCount=[int]$Matches[2];$newStart=[int]$Matches[3];$newCount=[int]$Matches[4]
$beforePart=@();$afterPart=@();foreach($line in $lines[3..($lines.Length-1)]){if($line.StartsWith(' ')){$beforePart+=$line.Substring(1);$afterPart+=$line.Substring(1)}elseif($line.StartsWith('-')){$beforePart+=$line.Substring(1)}elseif($line.StartsWith('+')){$afterPart+=$line.Substring(1)}else{throw 'Invalid diff row'}}
if($beforePart.Count -ne $oldCount -or $afterPart.Count -ne $newCount){throw 'Diff hunk counts differ'}
$oldTail=if($oldCount){($beforePart -join "`n")+"`n"}else{''};$newTail=($afterPart -join "`n")+"`n"
$prefix=if($isAdapter){$old.Substring(0,$old.Length-$oldTail.Length)}else{''}
if($old -cne ($prefix+$oldTail) -or $new -cne ($prefix+$newTail)){throw 'Complete diff reconstruction differs'}
if($isAdapter -and -not $new.StartsWith($old,[StringComparison]::Ordinal)){throw 'Accepted prefix changed'}
$checks += [ordered]@{file=$name;old_start=$oldStart;old_count=$oldCount;new_start=$newStart;new_count=$newCount;forward=$true;reverse=$true}
}
$names=@('asr_loading_adapter.py','stage_addition.py.txt','worker_stage_fixture.py','test_controller_worker_stage.py','asr_loading_adapter.diff','worker_stage_fixture.py.diff','test_controller_worker_stage.py.diff','EXPECTED-CASES.json','REPORT.md','SOURCE-CORRECTIONS.md','SOURCE-VIEW-COVERAGE.json')
$derived=@(foreach($name in $names){$p=Join-Path $d $name;[ordered]@{path=$name;bytes=(Get-Item -LiteralPath $p).Length;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}})
$brief='docs/library/CONTROLLER-WORKER-STAGE-REPAIR-BRIEF-2026-09-14.md'
$map=[ordered]@{schema='uoink.controller-worker-stage-source.v1';scope='source and14 proposed controls only; no qualification admission';brief=[ordered]@{path=$brief;sha256=(Get-FileHash -LiteralPath (Join-Path $root $brief) -Algorithm SHA256).Hash.ToLowerInvariant()};original_inputs=$inputRows;derivatives=$derived;prefix_bytes=28922;prefix_unchanged=$true;diff_reconstruction=$checks;candidate_execution=$false;native_ownership_claim=$false;existing_accepted_tests_edited=$false}
$mapPath=Join-Path $d 'SOURCE-INPUTS.json';if(Test-Path -LiteralPath $mapPath){throw 'Final map already exists'};[IO.File]::WriteAllText($mapPath,($map|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
[ordered]@{status='PASS';unchanged_source_pairs=$inputRows.Count;complete_diffs=$checks;new_cases=14;map_sha256=(Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant();derived=$derived;candidate_execution=$false}|ConvertTo-Json -Depth 6 -Compress
