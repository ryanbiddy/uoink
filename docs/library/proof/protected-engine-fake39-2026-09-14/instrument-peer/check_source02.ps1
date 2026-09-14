$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskDir=Join-Path $taskRepo '_scratch/protected-engine-ownership-fake39-author01'
$taskOld=Join-Path $taskRepo '_scratch/runtime-owner-native-connection-proposal01'
$taskCore=Join-Path $taskRepo '_scratch/protected-engine-ownership-repair02'
function Read-Text([string]$path){
 $item=Get-Item -LiteralPath $path
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576){throw 'Bounded plain text required'}
 [IO.File]::ReadAllText($item.FullName)
}
function Hash-Text([string]$path){$null=Read-Text $path;(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
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
$pins=Read-Text (Join-Path $taskDir 'PINS.json')|ConvertFrom-Json
if((Hash-Text (Join-Path $taskDir 'PINS.json')) -cne '7309394f50729101e23899ef1a947639e4abcb27d59910f3dd2446d98f3524ba'){throw 'Wrong frozen PINS'}
if($pins.count -ne 40 -or @($pins.files).Count -ne 40){throw '40 parents required'}
$rows=@{};$total=0
foreach($row in $pins.files){
 if($rows.ContainsKey($row.path) -or $row.path -cnotmatch '^[A-Za-z0-9_.-]+$'){throw 'Parent membership malformed'}
 $path=Join-Path $taskDir $row.path
 if((Hash-Text $path) -cne $row.sha256 -or (Get-Item -LiteralPath $path).Length -ne $row.bytes){throw ('Parent pin mismatch '+$row.path)}
 $rows[$row.path]=$row.sha256;$total+=$row.bytes
}
$q=Read-Text (Join-Path $taskDir 'qualify_owner.py');$qOld=Read-Text (Join-Path $taskDir 'before/qualify_owner.py')
$l=Read-Text (Join-Path $taskDir 'run_fake39_01.ps1');$lOld=Read-Text (Join-Path $taskDir 'before/run_fake33_01.ps1')
if((Hash-Text (Join-Path $taskDir 'before/qualify_owner.py')) -cne (Hash-Text (Join-Path $taskOld 'qualify_owner.py')) -or (Hash-Text (Join-Path $taskDir 'before/run_fake33_01.ps1')) -cne (Hash-Text (Join-Path $taskOld 'run_fake33_01.ps1'))){throw 'Wrong instrument baseline'}
$child=@(Quoted (Match-One $q '(?m)^INPUTS = \(([^\r\n]*)\)$'))
$modules=@(Quoted (Match-One $q '(?m)^MODULES = \(([^\r\n]*)\)$'))
$allowed=@(Quoted (Match-One $q '(?m)^ALLOWED_IMPORTS = set\(sys.modules\) \| set\(\(([^\r\n]*)\)\)$'))
Equal $modules $allowed 'Allowed imports differ from fixed modules'
Equal $child @(@($modules|ForEach-Object{$_+'.py'})+@('qualify_owner.py','EXPECTED-CASES.json')) 'Child list differs from module closure'
if($child.Count -ne 38 -or $modules.Count -ne 36 -or @($child|Sort-Object -Unique).Count -ne 38){throw 'Child closure counts'}
$parent=@(Quoted (Match-One $l '(?m)^\$taskInputNames=@\(([^\r\n]*)\)$'))
Equal $parent @($child+@('SOURCE-INPUTS.json','run_fake39_01.ps1')) 'Parent closure order'
Equal @($pins.files.path) $parent 'PINS order differs from launcher'
$sourcePins=Match-One $q '(?m)^SOURCE_PINS = (\{[^\r\n]*\})$'|ConvertFrom-Json
Equal @($sourcePins.PSObject.Properties.Name|Sort-Object) @($child|Where-Object{$_ -cne 'qualify_owner.py'}|Sort-Object) 'Child literal pins membership'
foreach($property in $sourcePins.PSObject.Properties){if($rows[$property.Name] -cne $property.Value){throw 'Child source hash mismatch'}}
$expected=Read-Text (Join-Path $taskDir 'EXPECTED-CASES.json')|ConvertFrom-Json
$oldExpected=Read-Text (Join-Path $taskOld 'EXPECTED-CASES.json')|ConvertFrom-Json
$ids=@(Quoted (Match-One $q '(?m)^EXPECTED_CASES = \(([^\r\n]*)\)$'))
Equal $ids @($expected.ordered_cases) 'Qualifier IDs differ'
Equal @($ids[0..32]) @($oldExpected.ordered_cases) 'Original33 prefix differs'
if($ids.Count -ne 39 -or @($ids|Sort-Object -Unique).Count -ne 39){throw '39 unique IDs required'}
$newTests=Read-Text (Join-Path $taskDir 'test_engine_ownership.py')
$newIds=@([regex]::Matches($newTests,'(?m)^    def (test_[A-Za-z0-9_]+)\(self\):')|ForEach-Object{'test_engine_ownership.EngineOwnershipContracts.'+$_.Groups[1].Value})
Equal @($ids[33..38]) $newIds 'New six method order mismatch'
$changed=@('worker_runtime_owner','owned_generation_protocol');$added=@('generated_engine_objects','test_engine_ownership');$preserved=0
foreach($module in $modules){
 $name=$module+'.py'
 if($module -cin $changed -or $module -cin $added){$origin=Join-Path $taskCore $name}else{$origin=Join-Path $taskOld $name;$preserved++}
 if($rows[$name] -cne (Hash-Text $origin)){throw ('Module differs from bound source '+$name)}
}
if([array]::IndexOf($modules,'generated_engine_objects') -ge [array]::IndexOf($modules,'worker_runtime_owner') -or $modules[-1] -cne 'test_engine_ownership'){throw 'Required loader order absent'}
$map=Read-Text (Join-Path $taskDir 'SOURCE-INPUTS.json')|ConvertFrom-Json
Equal @($map.source_paths.PSObject.Properties.Name) $child 'Source map membership differs'
foreach($name in $child){if([IO.Path]::GetFullPath($map.source_paths.$name) -cne (Join-Path $taskDir $name) -or $map.source_sha256.$name -cne $rows[$name]){throw 'Source map binding mismatch'}}
$template=Read-Text (Join-Path $taskDir 'ROOT-ADMISSION.template.json')|ConvertFrom-Json
if($template.root_reviewed -cne $false -or $template.scope -cne 'protected-engine-ownership-fake-39-only' -or $template.label -cne 'protected-engine-fake01'){throw 'False template scope mismatch'}
Equal @($template.input_sha256.PSObject.Properties.Name | Sort-Object) @($parent | Sort-Object) 'Admission input membership'
foreach($name in $parent){if($template.input_sha256.$name -cne $rows[$name]){throw 'Admission pin mismatch'}}
Equal @($template.expected_cases) $ids 'Admission IDs differ'
$edits=Read-Text (Join-Path $taskDir 'DECLARED-INSTRUMENT-EDITS.json')|ConvertFrom-Json
$patchResults=@()
foreach($spec in @(@('qualifier',$qOld,$q,'qualify_owner.diff'),@('launcher',$lOld,$l,'run_fake39_01.diff'))){
 $derived=$spec[1]
 foreach($edit in $edits.($spec[0])){
  $count=1;if($null -ne $edit.count){$count=$edit.count}
  if(([regex]::Matches($derived,[regex]::Escape($edit.before))).Count -ne $count){throw 'Declared edit count mismatch'}
  $derived=$derived.Replace($edit.before,$edit.after)
 }
 if($derived -cne $spec[2]){throw 'Declared edits do not reconstruct exact source text'}
 $delta=Read-Text (Join-Path $taskDir $spec[3])
 $f=Check-Patch $spec[1] $spec[2] $delta $false;$r=Check-Patch $spec[1] $spec[2] $delta $true
 $patchResults += [ordered]@{path=$spec[3];forward_hunks=$f;reverse_hunks=$r;exact_declared_edits=$true}
}
if($q.Substring(0,$q.IndexOf('INPUTS = ')) -cne $qOld.Substring(0,$qOld.IndexOf('INPUTS = '))){throw 'Stdlib/startup prefix changed'}
$copy=Read-Text (Join-Path $taskDir 'COPY-BINDINGS.json')|ConvertFrom-Json
foreach($row in $copy.files){if((Hash-Text $row.source) -cne $row.sha256 -or (Hash-Text (Join-Path $taskDir $row.name)) -cne $row.copy_sha256 -or $row.sha256 -cne $row.copy_sha256){throw 'Original/copy pair differs'}}
[ordered]@{status='PASSIVE_SOURCE_REVIEW_PASS';candidate_executed=$false;parent_pins=40;parent_bytes=$total;child_texts=38;module_count=36;unchanged_old_modules=$preserved;reviewed_replacements=2;added_modules=2;original_cases=33;new_cases=6;original_case_files_exact=3;copy_pairs=@($copy.files).Count;stdlib_preloads_unchanged=$true;source_map_and_template_exact=$true;deltas=$patchResults;qualifier=$rows['qualify_owner.py'];launcher=$rows['run_fake39_01.ps1'];pins=(Hash-Text (Join-Path $taskDir 'PINS.json'));false_template=(Hash-Text (Join-Path $taskDir 'ROOT-ADMISSION.template.json'))}|ConvertTo-Json -Depth 10
