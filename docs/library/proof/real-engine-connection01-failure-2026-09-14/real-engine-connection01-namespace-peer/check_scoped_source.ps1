$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskRoot=Join-Path $taskRepo '_scratch/real-engine-connection01-root-review'
function Binding([string]$path){
 $item=Get-Item -LiteralPath $path
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576){throw 'Bounded plain text required'}
 [ordered]@{bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Equal($a,$b,[string]$reason){if(($a|ConvertTo-Json -Compress -Depth 30) -cne ($b|ConvertTo-Json -Compress -Depth 30)){throw $reason}}
function Match-One([string]$text,[string]$pattern){$found=[regex]::Matches($text,$pattern);if($found.Count -ne 1){throw ('Unique match required: '+$pattern)};$found[0].Groups[1].Value}
function Quoted([string]$text){@([regex]::Matches($text,"'([^']+)'" )|ForEach-Object{$_.Groups[1].Value})}
function Check-Patch([string]$before,[string]$after,[string]$delta,[bool]$reverse){
 $a=@($before.Replace("`r`n","`n").Split("`n"));$b=@($after.Replace("`r`n","`n").Split("`n"));$p=@($delta.Replace("`r`n","`n").Split("`n"))
 if($p[0] -notmatch '^--- ' -or $p[1] -notmatch '^\+\+\+ '){throw 'Invalid unified headers'}
 if($reverse){$tmp=$a;$a=$b;$b=$tmp}
 $out=[Collections.Generic.List[string]]::new();$cursor=0;$i=2;$hunks=0
 while($i -lt $p.Count){
  if($i -eq $p.Count-1 -and $p[$i] -ceq ''){break}
  $h=[regex]::Match($p[$i],'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
  if(-not $h.Success){throw ('Invalid hunk header '+$i)}
  $startA=[int]$h.Groups[1].Value;$countA=1;if($h.Groups[2].Success){$countA=[int]$h.Groups[2].Value}
  $startB=[int]$h.Groups[3].Value;$countB=1;if($h.Groups[4].Success){$countB=[int]$h.Groups[4].Value}
  if($reverse){$tmp=$startA;$startA=$startB;$startB=$tmp;$tmp=$countA;$countA=$countB;$countB=$tmp}
  $offsetA=$startA-1;if($countA -eq 0){$offsetA=$startA}
  $offsetB=$startB-1;if($countB -eq 0){$offsetB=$startB}
  if($offsetA -lt $cursor){throw 'Overlapping hunks'}
  while($cursor -lt $offsetA){$out.Add($a[$cursor]);$cursor++}
  if($out.Count -ne $offsetB){throw 'New hunk offset mismatch'}
  $usedA=0;$usedB=0;$i++;$hunks++
  while($i -lt $p.Count -and -not $p[$i].StartsWith('@@ ')){
   if($i -eq $p.Count-1 -and $p[$i] -ceq ''){break}
   $line=$p[$i];if($line.Length -lt 1){throw 'Untagged patch line'}
   $tag=$line.Substring(0,1);$body=$line.Substring(1)
   if($reverse){if($tag -ceq '+'){$tag='-'}elseif($tag -ceq '-'){$tag='+'}}
   if($tag -ceq ' ' -or $tag -ceq '-'){
    if($cursor -ge $a.Count -or $a[$cursor] -cne $body){throw ('Patch context differs at '+$cursor)}
    $cursor++;$usedA++
   }
   if($tag -ceq ' ' -or $tag -ceq '+'){$out.Add($body);$usedB++}
   if($tag -cnotin @(' ','+','-')){throw 'Unknown patch tag'}
   $i++
  }
  if($usedA -ne $countA -or $usedB -ne $countB){throw 'Hunk count mismatch'}
 }
 while($cursor -lt $a.Count){$out.Add($a[$cursor]);$cursor++}
 Equal @($out) $b 'Complete patch reconstruction mismatch'
 $hunks
}
$pinPath=Join-Path $taskRoot 'FROZEN-SOURCE-PINS.json'
if((Binding $pinPath).sha256 -cne '860ac15701fe82f0960867b9f9058e67792b3f2ca73d4ecef7a9799deb611371'){throw 'Frozen25 map changed'}
$pins=Get-Content -LiteralPath $pinPath -Raw|ConvertFrom-Json
if(@($pins.files).Count -ne 25){throw 'Frozen membership count'}
$selected=@('frozen/SOURCE-INPUTS.json','frozen/pinned_buffer_namespace.py','frozen/pinned_buffer_namespace.diff','frozen/before/pinned_buffer_namespace.py','frozen/inherited_readset.py','frozen/inherited_readset.diff','frozen/before/inherited_readset.py','frozen/owned_generation_protocol.py','frozen/owned_generation_protocol.diff','frozen/before/owned_generation_protocol.py','frozen/worker_runtime_owner.py','frozen/test_real_engine_connection.py')
$checked=@()
foreach($name in $selected){
 $row=@($pins.files|Where-Object{$_.path -ceq $name});if($row.Count -ne 1){throw 'Missing scoped row'}
 $path=Join-Path $taskRoot $name;$actual=Binding $path
 if($actual.bytes -ne $row[0].bytes -or $actual.sha256 -cne $row[0].sha256){throw ('Scoped pin changed '+$name)}
 $checked+=[ordered]@{path=$name;bytes=$actual.bytes;sha256=$actual.sha256}
}
$sourceMap=Get-Content -LiteralPath (Join-Path $taskRoot 'frozen/SOURCE-INPUTS.json') -Raw|ConvertFrom-Json
if($sourceMap.input_count -ne 23 -or @($sourceMap.files).Count -ne 23){throw 'Source plan membership'}
$planMap=Join-Path $taskRepo 'docs/library/proof/real-engine-connection-plan-2026-09-14/plan/SOURCE-INPUTS.json'
if((Binding $planMap).sha256 -cne (Binding (Join-Path $taskRoot 'frozen/SOURCE-INPUTS.json')).sha256){throw 'Delivered plan map differs from committed plan'}
$planBrief=Join-Path $taskRepo 'docs/library/proof/real-engine-connection-plan-2026-09-14/plan/BRIEF.md'
if((Binding $planBrief).sha256 -cne '140c4db6c85f7f606533324fa1f3b7d4f8e9922ba6b2c8189c380cd8e8086558'){throw 'Wrong plan brief'}
$originSpecs=@(@('pinned_buffer_namespace.py','_scratch/windows-interrupted-owner-native-proposal02/pinned_buffer_namespace.py'),@('inherited_readset.py','_scratch/windows-interrupted-owner-native-proposal02/inherited_readset.py'),@('owned_generation_protocol.py','_scratch/protected-engine-ownership-repair02/owned_generation_protocol.py'))
$reconstructed=@()
foreach($spec in $originSpecs){
 $row=@($sourceMap.files|Where-Object{$_.path -ceq $spec[1]});if($row.Count -ne 1){throw 'Original source absent from23 map'}
 $beforePath=Join-Path $taskRoot ('frozen/before/'+$spec[0]);$currentPath=Join-Path $taskRoot ('frozen/'+$spec[0]);$deltaPath=Join-Path $taskRoot ('frozen/'+[IO.Path]::GetFileNameWithoutExtension($spec[0])+'.diff')
 foreach($path in @($beforePath,(Join-Path $taskRepo $spec[1]))){$actual=Binding $path;if($actual.sha256 -cne $row[0].sha256 -or $actual.bytes -ne $row[0].bytes){throw 'Before original binding mismatch'}}
 $before=[IO.File]::ReadAllText($beforePath);$current=[IO.File]::ReadAllText($currentPath);$delta=[IO.File]::ReadAllText($deltaPath)
 $start=$delta.IndexOf('--- ');if($start -lt 0){throw 'No unified patch headers'};$delta=$delta.Substring($start)
 $forward=Check-Patch $before $current $delta $false;$reverse=Check-Patch $before $current $delta $true
 $reconstructed+=[ordered]@{source=$spec[0];forward_hunks=$forward;reverse_hunks=$reverse;before_matches_bound_original=$true}
}
$namespace=[IO.File]::ReadAllText((Join-Path $taskRoot 'frozen/pinned_buffer_namespace.py'))
$adoption=[IO.File]::ReadAllText((Join-Path $taskRoot 'frozen/inherited_readset.py'))
$protocol=[IO.File]::ReadAllText((Join-Path $taskRoot 'frozen/owned_generation_protocol.py'))
$test=[IO.File]::ReadAllText((Join-Path $taskRoot 'frozen/test_real_engine_connection.py'))
[ordered]@{status='PASSIVE_SCOPED_BINDINGS_AND_DELTAS_MATCH';candidate_executed=$false;frozen_map=Binding $pinPath;scoped_pins=@($checked).Count;input_plan_count=23;selected=$checked;reconstruction=$reconstructed;new_materialize_method_present=$adoption.Contains('def materialize_admitted(');new_admitted_selection_present=$protocol.Contains('def bind_admitted_selection(');AdmittedNamespaceRecord_definition=[regex]::Matches($namespace,'class AdmittedNamespaceRecord').Count;ReadSetRefusal_defined_in_adoption=[regex]::Matches($adoption,'(?m)^(class|def) ReadSetRefusal\b').Count;test_imports_ReadSetRefusal=$test.Contains('ADMITTED_FORMAT, ReadSetRefusal');runtime_or_qualification_acceptance=$false}|ConvertTo-Json -Depth 10
