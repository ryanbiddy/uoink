$ErrorActionPreference='Stop'
$base='E:/AI/projects/uoink/checkouts/Yoink-library'
$dir=Join-Path $base '_scratch/startup-authority-qualification-proposal01'
function Assert-Task($condition,[string]$message){if(-not $condition){throw $message}}
function Text-Task([string]$path){return [IO.File]::ReadAllText($path)}
function Binding-Task([string]$path){$b=[IO.File]::ReadAllBytes($path);return [ordered]@{bytes=$b.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b)).ToLowerInvariant()}}
function Apply-TextDelta([string]$before,[string]$patch,[bool]$reverse) {
    Assert-Task ($before.EndsWith([string][char]10) -and -not $before.Contains([char]13)) 'Exact LF subject required'
    $old=$before.Substring(0,$before.Length-1).Split([char]10)
    $lines=$patch.TrimEnd([char]10).Split([char]10)
    Assert-Task ($lines[0].StartsWith('--- ') -and $lines[1].StartsWith('+++ ')) 'Separate patch headers required'
    $out=[Collections.Generic.List[string]]::new()
    $at=0; $i=2; $hunks=0
    while($i -lt $lines.Length) {
        Assert-Task ($lines[$i] -cmatch '^@@ -([0-9]+),([0-9]+) \+([0-9]+),([0-9]+) @@$') 'Valid full hunk header required'
        $start=[int]$Matches[1]-1; $wantOld=[int]$Matches[2]; $wantNew=[int]$Matches[4]
        if($reverse) { $start=[int]$Matches[3]-1; $swap=$wantOld; $wantOld=$wantNew; $wantNew=$swap }
        Assert-Task ($start -ge $at) 'Ordered nonoverlapping hunk required'
        while($at -lt $start) { $out.Add($old[$at]); $at++ }
        $i++; $gotOld=0; $gotNew=0
        while($i -lt $lines.Length -and -not $lines[$i].StartsWith('@@ ')) {
            Assert-Task ($lines[$i].Length -ge 1) 'Prefixed delta line required'
            $tag=$lines[$i].Substring(0,1); $body=$lines[$i].Substring(1)
            if($reverse) { if($tag -ceq '+') {$tag='-'} elseif($tag -ceq '-') {$tag='+'} }
            Assert-Task ($tag -cin @(' ','+','-')) 'Known delta prefix required'
            if($tag -cne '+') { Assert-Task ($at -lt $old.Length -and $old[$at] -ceq $body) 'Exact old context required'; $at++; $gotOld++ }
            if($tag -cne '-') { $out.Add($body); $gotNew++ }
            $i++
        }
        Assert-Task ($gotOld -eq $wantOld -and $gotNew -eq $wantNew) 'Exact hunk counts required'
        $hunks++
    }
    while($at -lt $old.Length) { $out.Add($old[$at]); $at++ }
    return [string]::Join([string][char]10,$out)+[char]10
}

$map=Text-Task (Join-Path $dir 'SOURCE-INPUTS.json')|ConvertFrom-Json
$pins=Text-Task (Join-Path $dir 'PINS.json')|ConvertFrom-Json
Assert-Task ($pins.count -eq 27 -and @($pins.files).Count -eq 27 -and @($pins.files.path|Select-Object -Unique).Count -eq 27) 'Exact27 parent map'
$parent=@()
foreach($row in $pins.files){
 $b=Binding-Task (Join-Path $dir $row.path)
 Assert-Task ($b.bytes -eq $row.bytes -and $b.sha256 -ceq $row.sha256) ('Parent mismatch '+$row.path)
 $parent+=[ordered]@{path=$row.path;bytes=$b.bytes;sha256=$b.sha256}
}
Assert-Task ($map.child_count -eq 23 -and @($map.child_inputs).Count -eq 23 -and $map.module_count -eq 21) 'Exact child closure'
foreach($row in $map.child_inputs){
 $b=Binding-Task (Join-Path $dir $row.name);$original=Binding-Task $row.source
 Assert-Task ($b.bytes -eq $row.bytes -and $b.sha256 -ceq $row.sha256 -and $original.bytes -eq $row.bytes -and $original.sha256 -ceq $row.sha256) ('Child source/copy mismatch '+$row.name)
}
$oldRoot=Join-Path $base '_scratch/windows-reservation-implementation-proposal02'
$beforeRows=@()
foreach($name in @('qualify_windows_reservations.py','run_preflight01.ps1','EXPECTED-CASES.json','PINS.json','QUALIFICATION-PROTOCOL.md')){
 $a=Binding-Task (Join-Path $oldRoot $name);$b=Binding-Task (Join-Path $dir ('before/'+$name))
 Assert-Task ($a.bytes -eq $b.bytes -and $a.sha256 -ceq $b.sha256) 'Original before copy mismatch'
 $beforeRows+=[ordered]@{name=$name;sha256=$b.sha256}
}
$diffs=@()
foreach($pair in @(@('qualify_windows_reservations.py','qualify_windows_reservations.diff','QUALIFIER-DECLARED-EDITS.json'),@('run_preflight01.ps1','run_preflight01.diff','LAUNCHER-DECLARED-EDITS.json'))){
 $old=Text-Task (Join-Path $dir ('before/'+$pair[0]));$new=Text-Task (Join-Path $dir $pair[0]);$patch=Text-Task (Join-Path $dir $pair[1])
 Assert-Task ((Apply-TextDelta $old $patch $false) -ceq $new) 'Forward exact reconstruction'
 Assert-Task ((Apply-TextDelta $new $patch $true) -ceq $old) 'Reverse exact reconstruction'
 $declared=Text-Task (Join-Path $dir $pair[2])|ConvertFrom-Json
 $reconstructed=$old
 foreach($edit in $declared){
  $count=[regex]::Matches($reconstructed,[regex]::Escape($edit.old)).Count
  $wanted=1;if($edit.PSObject.Properties.Name -contains 'count'){$wanted=$edit.count}
  Assert-Task ($count -eq $wanted) 'Declared edit occurrence mismatch'
  $reconstructed=$reconstructed.Replace([string]$edit.old,[string]$edit.new)
 }
 Assert-Task ($reconstructed -ceq $new) 'Only declared edits permitted'
 $diffs+=[ordered]@{subject=$pair[0];patch=Binding-Task (Join-Path $dir $pair[1]);forward=$true;reverse=$true;declared_edits=@($declared).Count}
}
$expected=@(Text-Task (Join-Path $dir 'EXPECTED-CASES.json')|ConvertFrom-Json)
$oldExpected=@(Text-Task (Join-Path $oldRoot 'EXPECTED-CASES.json')|ConvertFrom-Json)
$newExpected=Text-Task (Join-Path $base '_scratch/real-startup-authority-repair01/EXPECTED-CASES.json')|ConvertFrom-Json
Assert-Task ($expected.Count -eq 81 -and @($expected|Select-Object -Unique).Count -eq 81) '81 distinct cases'
Assert-Task (($expected[0..64] -join '|') -ceq ($oldExpected -join '|')) 'Original65 ordered IDs'
Assert-Task (($expected[65..80] -join '|') -ceq ($newExpected.cases -join '|')) 'Exact16 source-order IDs'
foreach($name in @('test_reservations.py','test_windows_reservations.py')){
 $a=Binding-Task (Join-Path $oldRoot $name);$b=Binding-Task (Join-Path $dir $name)
 Assert-Task ($a.bytes -eq $b.bytes -and $a.sha256 -ceq $b.sha256) 'Original test bytes'
}
$canonical=[IO.File]::ReadAllBytes((Join-Path $dir 'asr_loading_adapter.py'))
$derived=[IO.File]::ReadAllBytes((Join-Path $dir 'startup_fixture_adapter.py'))
Assert-Task ($canonical.Length -eq 12113 -and $derived.Length -eq 28922) 'Bound adapter lengths'
for($i=0;$i -lt $canonical.Length;$i++){Assert-Task ($canonical[$i] -eq $derived[$i]) 'Original adapter prefix'}
$q=Text-Task (Join-Path $dir 'qualify_windows_reservations.py')
$oldQ=Text-Task (Join-Path $dir 'before/qualify_windows_reservations.py')
$modules=@([regex]::Matches([regex]::Match($q,'(?m)^MODULES = \((.+)\)$').Groups[1].Value,'"([a-z0-9_]+)"').ForEach({$_.Groups[1].Value}))
Assert-Task (($modules -join '|') -ceq ($map.modules -join '|')) 'Explicit module order'
Assert-Task ($modules.IndexOf('startup_fixture_adapter') -lt $modules.IndexOf('test_reservations')) 'Alias before all tests'
Assert-Task ($q.Substring(0,$q.IndexOf('MODULES = ')) -ceq $oldQ.Substring(0,$oldQ.IndexOf('MODULES = '))) 'Original preloads/startup guards'
$methodText=$q.Substring($q.IndexOf('            STARTUP_FUNCTIONS = tuple('))
$methodText=$methodText.Substring(0,$methodText.IndexOf(') for method in methods)'))
$functionRows=@()
foreach($match in [regex]::Matches($methodText,'\("([a-z_]+)", \(([^\r\n]+)\)\),')){
 $moduleName=$match.Groups[1].Value;$source=Text-Task (Join-Path $dir ($moduleName+'.py'))
 foreach($method in [regex]::Matches($match.Groups[2].Value,'"([a-z_]+)"')){
  $name=$method.Groups[1].Value
  Assert-Task ([regex]::IsMatch($source,'(?m)^def '+[regex]::Escape($name)+'\(')) ('Missing captured method '+$moduleName+'.'+$name)
  $functionRows+=$moduleName+'.'+$name
 }
}
Assert-Task ($functionRows.Count -eq 36) 'Exact36 captured fixed methods'
Assert-Task (-not [IO.File]::Exists((Join-Path $dir 'ROOT-ADMISSION.json')) -and -not [IO.Directory]::Exists((Join-Path $dir 'startup-authority-fake01')) -and -not [IO.Directory]::Exists((Join-Path $dir 'startup-authority-confirmation01'))) 'No admission or subject run'
[ordered]@{scope='Passive text/byte checks; no subject execution';parent_inputs=$parent;child_count=23;module_count=21;before=$beforeRows;diffs=$diffs;original65_ids_unchanged=$true;new16_source_order=$true;old_test_bytes_unchanged=$true;adapter_prefix_bytes=12113;preloads_unchanged=$true;fixed_function_names=$functionRows;admitted=$false;candidate_executed=$false}|ConvertTo-Json -Depth 10
