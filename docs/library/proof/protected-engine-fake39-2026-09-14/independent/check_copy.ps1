$ErrorActionPreference='Stop'
$taskRoot='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-fake39-independent01'
function Assert-Task([bool]$ok,[string]$why){if(-not $ok){throw $why}}
function Hash-Task([byte[]]$bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
function Read-Task([string]$name){return [IO.File]::ReadAllText((Join-Path $taskRoot $name))}
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

$taskPins=(Read-Task 'PINS.json') | ConvertFrom-Json -AsHashtable
$taskBefore=(Read-Task 'before/PINS.json') | ConvertFrom-Json -AsHashtable
$taskTemplate=(Read-Task 'ROOT-ADMISSION.template.json') | ConvertFrom-Json -AsHashtable
$taskMap=(Read-Task 'SOURCE-INPUTS.json') | ConvertFrom-Json -AsHashtable
$taskOldMap=(Read-Task 'before/SOURCE-INPUTS.json') | ConvertFrom-Json -AsHashtable
$taskCopy=(Read-Task 'COPY-BINDINGS.json') | ConvertFrom-Json -AsHashtable
$taskEdits=(Read-Task 'DECLARED-PATH-EDITS.json') | ConvertFrom-Json -AsHashtable
$taskCases=(Read-Task 'EXPECTED-CASES.json') | ConvertFrom-Json -AsHashtable
$taskOriginalTemplate=(Read-Task 'before/ROOT-ADMISSION.template.json') | ConvertFrom-Json -AsHashtable
Assert-Task ($taskPins.execution_authority -ceq $false -and $taskPins.subject_executed -ceq $false -and $taskPins.files.Count -eq 40 -and $taskPins.count -eq 40) 'Exact40 dormant primary inputs'
Assert-Task ($taskTemplate.root_reviewed -is [bool] -and $taskTemplate.root_reviewed -ceq $false -and $taskOriginalTemplate.root_reviewed -ceq $false) 'False templates only'
Assert-Task ($taskTemplate.scope -ceq 'protected-engine-ownership-fake-39-only' -and $taskTemplate.label -ceq 'protected-engine-confirmation01') 'Independent fixed scope/label'
Assert-Task (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'ROOT-ADMISSION.json')) -and -not (Test-Path -LiteralPath (Join-Path $taskRoot 'runs'))) 'No independent admission/run'
Assert-Task ($taskTemplate.input_sha256.Count -eq 40 -and $taskMap.source_paths.Count -eq 38 -and $taskMap.source_sha256.Count -eq 38) 'Exact closure'
$taskChanged=@();$taskBytesTotal=0;$taskCount=0
for($taskIndex=0;$taskIndex -lt 40;$taskIndex++){
 $taskRow=$taskPins.files[$taskIndex];$taskOriginal=$taskBefore.files[$taskIndex]
 Assert-Task ($taskRow.path -ceq $taskOriginal.path) 'Primary input membership/order'
 $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskRoot $taskRow.path));$taskHash=Hash-Task $taskRaw
 Assert-Task ($taskHash -ceq $taskRow.sha256 -and $taskRaw.Length -eq $taskRow.bytes) 'Independent input pin'
 Assert-Task ($taskTemplate.input_sha256[$taskRow.path] -ceq $taskHash) 'False template input pin'
 if($taskHash -cne $taskOriginal.sha256){$taskChanged+=$taskRow.path}else{$taskCount++}
 $taskBytesTotal+=$taskRaw.Length
}
Assert-Task ($taskCount -eq 38 -and $taskChanged.Count -eq 2 -and $taskChanged[0] -ceq 'SOURCE-INPUTS.json' -and $taskChanged[1] -ceq 'run_fake39_01.ps1') 'Only two parent controls changed'
foreach($taskName in $taskMap.source_paths.Keys){
 Assert-Task ($taskMap.source_paths[$taskName] -ceq ($taskRoot.Replace('/','\')+'\'+$taskName)) 'Exact independent child path'
 Assert-Task ($taskMap.source_sha256[$taskName] -ceq $taskOldMap.source_sha256[$taskName]) 'All38 child hashes unchanged'
 Assert-Task ((Hash-Task ([IO.File]::ReadAllBytes((Join-Path $taskRoot $taskName)))) -ceq $taskMap.source_sha256[$taskName]) 'Actual copied child bytes'
}
Assert-Task ($taskCopy.files.Count -eq 42) 'Fixed copy42'
foreach($taskRow in $taskCopy.files){
 Assert-Task ((Hash-Task ([IO.File]::ReadAllBytes((Join-Path $taskRoot $taskRow.name)))) -ceq $taskRow.before_sha256) 'Copied fixed bytes'
 Assert-Task ((Hash-Task ([IO.File]::ReadAllBytes($taskRow.source))) -ceq $taskRow.before_sha256) 'Author fixed bytes unchanged'
}
Assert-Task ($taskCases.count -eq 39 -and $taskCases.ordered_cases.Count -eq 39 -and $taskTemplate.expected_cases.Count -eq 39) 'Exact39'
for($taskIndex=0;$taskIndex -lt 39;$taskIndex++){
 Assert-Task ($taskCases.ordered_cases[$taskIndex] -ceq $taskTemplate.expected_cases[$taskIndex] -and $taskTemplate.expected_cases[$taskIndex] -ceq $taskOriginalTemplate.expected_cases[$taskIndex]) 'All39 ordered IDs unchanged'
}
$taskDeltaRows=@()
foreach($taskEntry in @(@('run_fake39_01.ps1','run_fake39_01.diff','launcher'),@('SOURCE-INPUTS.json','SOURCE-INPUTS.diff','source_map'))){
 $taskOld=Read-Task ('before/'+$taskEntry[0]);$taskNew=Read-Task $taskEntry[0];$taskDelta=Read-Task $taskEntry[1]
 Assert-Task ((Apply-TextDelta $taskOld $taskDelta $false) -ceq $taskNew) 'Forward complete reconstruction'
 Assert-Task ((Apply-TextDelta $taskNew $taskDelta $true) -ceq $taskOld) 'Reverse complete reconstruction'
 $taskRebuilt=$taskOld
 foreach($taskEdit in $taskEdits[$taskEntry[2]]){
  Assert-Task ([regex]::Matches($taskRebuilt,[regex]::Escape($taskEdit.before)).Count -eq $taskEdit.count) 'Exact fixed substitution count'
  $taskRebuilt=$taskRebuilt.Replace($taskEdit.before,$taskEdit.after)
 }
 Assert-Task ($taskRebuilt -ceq $taskNew) 'Only declared path/label substitutions'
 $taskDeltaRows += [ordered]@{input=$taskEntry[0];before_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskOld)));after_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskNew)));forward=$true;reverse=$true;declared_substitutions_only=$true}
}
$taskLauncher=Read-Task 'run_fake39_01.ps1'
$taskQ=Read-Task 'qualify_owner.py'
$taskLauncherPins=[regex]::Match($taskLauncher,'(?s)\$taskExpected=@\{(.*?)\n\}').Groups[1].Value
Assert-Task ([regex]::Matches($taskLauncherPins,"'[^']+'='[0-9a-f]{64}'").Count -eq 38) 'Launcher38 literal child pins'
$taskQpins=[regex]::Match($taskQ,'(?m)^SOURCE_PINS = (.+)$').Groups[1].Value | ConvertFrom-Json -AsHashtable
Assert-Task ($taskQpins.Count -eq 37 -and -not $taskQpins.ContainsKey('qualify_owner.py')) 'Qualifier37 noncircular pins'
foreach($taskName in $taskQpins.Keys){Assert-Task ($taskQpins[$taskName] -ceq $taskMap.source_sha256[$taskName]) 'Qualifier source pins match actual child'}
$taskNativePattern='(?s)# BEGIN EXACT NATIVE RECEIPT BLOCK.*?# END EXACT NATIVE RECEIPT BLOCK'
Assert-Task ([regex]::Match($taskLauncher,$taskNativePattern).Value -ceq [regex]::Match((Read-Task 'before/run_fake39_01.ps1'),$taskNativePattern).Value) 'Native receipt block unchanged'
$taskProof=[ordered]@{schema='uoink.protected-engine-fake39-independent-pins-proof.v1';subject_executed=$false;execution_authority=$false;parent_inputs=40;parent_bytes=$taskBytesTotal;unchanged_child_texts=38;launcher_literal_child_pins=38;qualifier_noncircular_pins=37;unchanged_ordered_case_ids=39;original33_and_new6_bodies_unchanged=$true;source_copy_pairs=42;changed_parent_controls=$taskChanged;source_paths_relocated=38;launcher_root_substitutions=39;launcher_label_substitutions=3;deltas=$taskDeltaRows;native_receipt_block_unchanged=$true;false_template=$true;actual_admission_or_run_created=$false}
[IO.File]::WriteAllText((Join-Path $taskRoot 'PINS-PROOF.json'),($taskProof | ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$taskProof | ConvertTo-Json -Depth 12
