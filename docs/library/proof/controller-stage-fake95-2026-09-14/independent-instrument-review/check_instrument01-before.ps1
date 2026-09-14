$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskRoot=Join-Path $taskRepo '_scratch\controller-stage-qualification-proposal01'
$taskBase=Join-Path $taskRepo '_scratch\startup-authority-qualification-proposal01'
$taskStage=Join-Path $taskRepo '_scratch\controller-worker-stage-repair01'
$taskReview=Join-Path $taskRepo '_scratch\controller-stage-instrument-peer01'
function Assert-Task([bool]$ok,[string]$why){if(-not $ok){throw $why}}
function Read-TaskText([string]$p){
  $f=Get-Item -LiteralPath $p
  Assert-Task (-not $f.PSIsContainer -and ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and $f.Length -le 1048576) "plain bounded text: $p"
  return [IO.File]::ReadAllText($f.FullName)
}
function Get-TaskBinding([string]$p){
  $null=Read-TaskText $p
  $f=Get-Item -LiteralPath $p
  return [ordered]@{bytes=$f.Length;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Assert-TaskRow([string]$p,$row){
  $b=Get-TaskBinding $p
  Assert-Task ($b.bytes -eq $row.bytes -and $b.sha256 -ceq $row.sha256) "binding: $p"
}
function Get-TaskLines([string]$s){
  $a=$s.Replace([string][char]13,'').Split([char]10)
  Assert-Task ($a[-1] -ceq '') 'terminal newline required'
  return $a[0..($a.Count-2)]
}
function Apply-TaskDiff([string]$source,[string]$patch,[bool]$reverse){
  $old=@(Get-TaskLines $source); $p=@(Get-TaskLines $patch)
  Assert-Task ($p[0].StartsWith('--- ') -and $p[1].StartsWith('+++ ')) 'separate diff headers'
  $out=[Collections.Generic.List[string]]::new()
  $cursor=0; $i=2; $hunks=0
  while($i -lt $p.Count){
    Assert-Task ($p[$i] -match '^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@') "hunk header $i"
    $oldStart=[int]$Matches[1]; $oldCount=1; if($Matches[2] -ne ''){$oldCount=[int]$Matches[2]}
    $newStart=[int]$Matches[3]; $newCount=1; if($Matches[4] -ne ''){$newCount=[int]$Matches[4]}
    if($reverse){$start=$newStart; $expectedConsumed=$newCount; $expectedAdded=$oldCount; $outputStart=$oldStart}
    else{$start=$oldStart; $expectedConsumed=$oldCount; $expectedAdded=$newCount; $outputStart=$newStart}
    $target=$start-1; if($start -eq 0){$target=0}
    Assert-Task ($target -ge $cursor) 'ordered hunks'
    while($cursor -lt $target){$out.Add($old[$cursor]);$cursor++}
    Assert-Task ($out.Count -eq ($outputStart-1)) 'output hunk position'
    $consumed=0;$added=0;$i++;$hunks++
    while($i -lt $p.Count -and -not $p[$i].StartsWith('@@ ')){
      $line=$p[$i]; Assert-Task ($line.Length -gt 0) 'diff line prefix'
      $tag=$line.Substring(0,1); $body=$line.Substring(1)
      if($reverse){if($tag -ceq '+'){$tag='-'}elseif($tag -ceq '-'){$tag='+'}}
      if($tag -ceq ' ' -or $tag -ceq '-'){
        Assert-Task ($cursor -lt $old.Count -and $old[$cursor] -ceq $body) "exact hunk source $cursor"
        $cursor++;$consumed++
      }
      if($tag -ceq ' ' -or $tag -ceq '+'){$out.Add($body);$added++}
      Assert-Task ($tag -ceq ' ' -or $tag -ceq '+' -or $tag -ceq '-') 'known line marker'
      $i++
    }
    Assert-Task ($consumed -eq $expectedConsumed -and $added -eq $expectedAdded) 'hunk counts'
  }
  while($cursor -lt $old.Count){$out.Add($old[$cursor]);$cursor++}
  return [ordered]@{text=([string]::Join([char]10,$out)+[char]10);hunks=$hunks}
}
$pinPath=Join-Path $taskRoot 'PINS.json'
$pinHash=(Get-TaskBinding $pinPath).sha256
Assert-Task ($pinHash -ceq 'b831bf6c864d8a7bef24355e5868dfa7480e6bba6ff1381cbc3ac9db07388606') 'frozen pins'
$pins=(Read-TaskText $pinPath)|ConvertFrom-Json
Assert-Task ($pins.count -eq 29 -and $pins.files.Count -eq 29 -and @($pins.files.path|Sort-Object -Unique).Count -eq 29) '29 unique parent inputs'
foreach($r in $pins.files){Assert-Task ($r.path -match '^[A-Za-z0-9_.-]+$') 'flat member';Assert-TaskRow (Join-Path $taskRoot $r.path) $r}
$map=(Read-TaskText (Join-Path $taskRoot 'SOURCE-INPUTS.json'))|ConvertFrom-Json
$baseMap=(Read-TaskText (Join-Path $taskBase 'SOURCE-INPUTS.json'))|ConvertFrom-Json
$copy=(Read-TaskText (Join-Path $taskRoot 'COPY-PLAN.json'))|ConvertFrom-Json
Assert-Task ($map.module_count -eq 23 -and $map.modules.Count -eq 23 -and $map.child_count -eq 25 -and $map.child_inputs.Count -eq 25) 'module/child counts'
Assert-Task (($map.modules[0..20] -join '|') -ceq ($baseMap.modules -join '|')) '21 original modules in order'
Assert-Task (($map.modules[21..22] -join '|') -ceq 'worker_stage_fixture|test_controller_worker_stage') 'two appended modules'
Assert-Task (($map.child_inputs.name -join '|') -ceq ((@($map.modules|ForEach-Object{$_+'.py'})+@('qualify_windows_reservations.py','EXPECTED-CASES.json')) -join '|')) '25 ordered child names'
foreach($r in $map.child_inputs){
  Assert-Task ($r.source.StartsWith(($taskBase.Replace('\','/')+'/')) -or $r.source.StartsWith(($taskStage.Replace('\','/')+'/')) -or $r.source.StartsWith(($taskRoot.Replace('\','/')+'/'))) 'fixed source roots'
  Assert-TaskRow $r.source $r;Assert-TaskRow (Join-Path $taskRoot $r.name) $r
  $parent=@($pins.files|Where-Object path -CEQ $r.name)
  Assert-Task ($parent.Count -eq 1 -and $parent[0].sha256 -ceq $r.sha256 -and $parent[0].bytes -eq $r.bytes) 'child parent match'
}
Assert-Task ($copy.modules.Count -eq 23 -and $copy.before.Count -eq 8) 'copy plan membership'
foreach($r in @($copy.modules)+@($copy.before)){Assert-TaskRow $r.source $r;Assert-TaskRow (Join-Path $taskRoot $r.name) $r}
foreach($f in @('test_reservations.py','test_windows_reservations.py','test_startup_authority.py','startup_authority_fixture.py')){
  Assert-Task ((Get-TaskBinding (Join-Path $taskRoot $f)).sha256 -ceq (Get-TaskBinding (Join-Path $taskBase $f)).sha256) "unchanged old fixture $f"
}
$baseCases=(Read-TaskText (Join-Path $taskBase 'EXPECTED-CASES.json'))|ConvertFrom-Json
$newCases=(Read-TaskText (Join-Path $taskStage 'EXPECTED-CASES.json'))|ConvertFrom-Json
$cases=(Read-TaskText (Join-Path $taskRoot 'EXPECTED-CASES.json'))|ConvertFrom-Json
Assert-Task ($baseCases.Count -eq 81 -and $newCases.Count -eq 14 -and $cases.Count -eq 95 -and @($cases|Sort-Object -Unique).Count -eq 95) 'case counts'
Assert-Task (($cases[0..80] -join '|') -ceq ($baseCases -join '|')) '81 ordered prefix'
Assert-Task (($cases[81..94] -join '|') -ceq ($newCases -join '|')) '14 source ordered suffix'
$baseAdapter=[IO.File]::ReadAllBytes((Join-Path $taskBase 'startup_fixture_adapter.py'))
$newAdapter=[IO.File]::ReadAllBytes((Join-Path $taskRoot 'startup_fixture_adapter.py'))
Assert-Task ($baseAdapter.Length -eq 28922) 'old adapter bytes'
Assert-Task ([Convert]::ToBase64String($newAdapter,0,28922) -ceq [Convert]::ToBase64String($baseAdapter)) 'accepted adapter prefix'
$diffResults=@()
foreach($f in @('qualify_windows_reservations.py','run_preflight01.ps1')){
  $old=Read-TaskText (Join-Path $taskBase $f);$current=Read-TaskText (Join-Path $taskRoot $f);$patch=Read-TaskText (Join-Path $taskRoot ($f+'.diff'))
  $forward=Apply-TaskDiff $old $patch $false;$reverse=Apply-TaskDiff $current $patch $true
  Assert-Task ($forward.text -ceq $current.Replace([string][char]13,'')) "full forward $f"
  Assert-Task ($reverse.text -ceq $old.Replace([string][char]13,'')) "full reverse $f"
  $diffResults+=[ordered]@{file=$f;hunks=$forward.hunks;forward=$true;reverse=$true;comparison='complete text with CRLF normalized to LF';before_sha256=(Get-TaskBinding (Join-Path $taskBase $f)).sha256;after_sha256=(Get-TaskBinding (Join-Path $taskRoot $f)).sha256}
}
$q=Read-TaskText (Join-Path $taskRoot 'qualify_windows_reservations.py')
$baseQ=Read-TaskText (Join-Path $taskBase 'qualify_windows_reservations.py')
$qModules=[regex]::Match($q,'(?m)^MODULES = (.+)$').Groups[1].Value
$names=@([regex]::Matches($qModules,'"([a-z0-9_]+)"')|ForEach-Object{$_.Groups[1].Value})
Assert-Task (($names -join '|') -ceq ($map.modules -join '|')) 'manual loader order'
$start=$q.IndexOf('            STARTUP_FUNCTIONS = tuple(')
Assert-Task ($start -ge 0) 'function capture block'
$end=$q.IndexOf('REAL_ENTRIES', $start)
Assert-Task ($end -gt $start) 'capture block end'
$capture=$q.Substring($start,$end-$start)
$functions=@([regex]::Matches($capture,'"(_?[A-Za-z][A-Za-z0-9_]*)"')|ForEach-Object{$_.Groups[1].Value})
# Module owner strings occur before their tuples; remove these four exact owners.
$functions=@($functions|Where-Object{$_ -notin @('trusted_asr_resolver','startup_fixture_resolver','asr_loading_adapter','startup_fixture_adapter')})
Assert-Task ($functions.Count -eq 38 -and $functions[-2] -ceq '_validate_controller_worker_stage' -and $functions[-1] -ceq '_validate_controller_worker_stage_locked') '38 captured functions'
Assert-Task ($q.Contains('STARTUP_KERNEL_TYPE = LOADED["durable_lifecycle"]._DurableKernel') -and $q.Contains('assert LOADED["startup_fixture_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE')) 'entry type capture'
Assert-Task ($q.Contains('and LOADED["durable_lifecycle"]._DurableKernel is STARTUP_KERNEL_TYPE') -and $q.Contains('and LOADED["startup_fixture_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE,')) 'final type comparison'
$template=(Read-TaskText (Join-Path $taskRoot 'ROOT-ADMISSION.template.json'))|ConvertFrom-Json
$indTemplate=(Read-TaskText (Join-Path $taskRoot 'CONFIRMATION-ADMISSION.template.json'))|ConvertFrom-Json
Assert-Task ($template.approved -eq $false -and $template.pins_sha256 -ceq $pinHash -and $template.label -ceq 'controller-stage-fake01' -and $template.case_count -eq 95) 'false author template'
Assert-Task ($indTemplate.approved -eq $false -and $null -eq $indTemplate.pins_sha256 -and $indTemplate.label -ceq 'controller-stage-confirmation01') 'false pending independent template'
$copies=[Collections.Generic.List[object]]::new()
$recordNames=@('qualify_windows_reservations.py','run_preflight01.ps1','qualify_windows_reservations.py.diff','run_preflight01.ps1.diff','PINS.json','SOURCE-INPUTS.json','COPY-PLAN.json','EXPECTED-CASES.json','ROOT-ADMISSION.template.json','CONFIRMATION-ADMISSION.template.json')
$destRoot=Join-Path $taskReview 'frozen-controls'
$null=[IO.Directory]::CreateDirectory($destRoot)
foreach($f in $recordNames){
  $src=Join-Path $taskRoot $f;$dst=Join-Path $destRoot $f
  Assert-Task (-not (Test-Path -LiteralPath $dst)) 'fresh peer control copy'
  [IO.File]::Copy($src,$dst,$false)
  $b=Get-TaskBinding $src;Assert-TaskRow $dst $b
  $copies.Add([ordered]@{path=$f;bytes=$b.bytes;sha256=$b.sha256})
}
[ordered]@{
  scope='Independent passive source/data review; no candidate execution'
  result='PASS';pins_sha256=$pinHash;parent_count=29;parent_bytes=($pins.files|Measure-Object bytes -Sum).Sum
  source_copy_pairs=25;copy_plan_pairs=31;module_count=23;child_count=25;ordered_cases=95;preserved_prefix=81;new_suffix=14
  old_three_case_files_and_startup_fixture_unchanged=$true;accepted_adapter_prefix_bytes=28922
  captured_functions=38;added_function_captures=2;entry_final_DurableKernel_identity=$true
  deltas=$diffResults;false_templates=$true;peer_copies=$copies
}|ConvertTo-Json -Depth 10
