$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskDir=Join-Path $taskRoot '_scratch\controller-stage-qualification-proposal01'
function Assert-Task([bool]$condition,[string]$message){if(-not $condition){throw $message}}
function Read-Text([string]$relative){return [IO.File]::ReadAllText((Join-Path $taskDir $relative))}
function Get-Sha([string]$file){return (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
function Hash-Bytes([byte[]]$bytes){$taskSha=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($taskSha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}finally{$taskSha.Dispose()}}
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

$taskPins=Read-Text 'PINS.json' | ConvertFrom-Json
Assert-Task ((Get-Sha (Join-Path $taskDir 'PINS.json')) -ceq 'b831bf6c864d8a7bef24355e5868dfa7480e6bba6ff1381cbc3ac9db07388606') 'Final parent map changed'
Assert-Task ($taskPins.count -eq 29 -and @($taskPins.files).Count -eq 29) 'Exact29 parent inputs'
$taskBytesTotal=0
foreach($taskRow in $taskPins.files){
 $taskFile=Join-Path $taskDir $taskRow.path
 $taskBytes=[IO.File]::ReadAllBytes($taskFile)
 Assert-Task ($taskBytes.Length -eq $taskRow.bytes -and (Get-Sha $taskFile) -ceq $taskRow.sha256) ('Parent pin mismatch: '+$taskRow.path)
 $taskBytesTotal += $taskBytes.Length
}
$taskMap=Read-Text 'SOURCE-INPUTS.json' | ConvertFrom-Json
Assert-Task ($taskMap.module_count -eq 23 -and @($taskMap.modules).Count -eq 23 -and @($taskMap.child_inputs).Count -eq 25) 'Exact23/25 closure'
foreach($taskRow in $taskMap.child_inputs){
 $taskPinned=@($taskPins.files | Where-Object {$_.path -ceq $taskRow.name})
 Assert-Task ($taskPinned.Count -eq 1 -and $taskPinned[0].sha256 -ceq $taskRow.sha256 -and $taskPinned[0].bytes -eq $taskRow.bytes) ('Child/map mismatch: '+$taskRow.name)
 Assert-Task ((Get-Sha $taskRow.source) -ceq $taskRow.sha256) ('Source changed: '+$taskRow.name)
}
$taskCopy=Read-Text 'COPY-PLAN.json' | ConvertFrom-Json
foreach($taskRow in @($taskCopy.modules)+@($taskCopy.before)){
 Assert-Task ((Get-Sha $taskRow.source) -ceq $taskRow.sha256 -and (Get-Sha (Join-Path $taskDir $taskRow.name)) -ceq $taskRow.sha256) ('Before/copy changed: '+$taskRow.name)
}
Assert-Task ((Get-Sha $taskCopy.source_map.path) -ceq $taskCopy.source_map.sha256) 'Frozen stage source map changed'
$taskDiffResults=@()
foreach($taskPair in @(@('qualify_windows_reservations.py','QUALIFIER-DECLARED-EDITS.json'),@('run_preflight01.ps1','LAUNCHER-DECLARED-EDITS.json'))){
 $taskName=$taskPair[0];$taskOld=Read-Text ('before/'+$taskName);$taskNew=Read-Text $taskName
 $taskEdited=$taskOld;$taskEdits=Read-Text $taskPair[1] | ConvertFrom-Json
 foreach($taskEdit in $taskEdits){
  $taskExpectedCount=1
  if($null -ne $taskEdit.PSObject.Properties['count']){$taskExpectedCount=[int]$taskEdit.count}
  Assert-Task ([regex]::Matches($taskEdited,[regex]::Escape([string]$taskEdit.before)).Count -eq $taskExpectedCount) ('Declared exact edit count: '+$taskEdit.id)
  $taskEdited=$taskEdited.Replace([string]$taskEdit.before,[string]$taskEdit.after)
 }
 Assert-Task ($taskEdited -ceq $taskNew) ('Only declared changes permitted: '+$taskName)
 $taskPatch=Read-Text ($taskName+'.diff')
 Assert-Task ((Apply-TextDelta $taskOld $taskPatch $false) -ceq $taskNew) ('Full forward mismatch: '+$taskName)
 Assert-Task ((Apply-TextDelta $taskNew $taskPatch $true) -ceq $taskOld) ('Full reverse mismatch: '+$taskName)
 $taskDiffResults += [ordered]@{file=$taskName;declared_edits=@($taskEdits).Count;hunks=[regex]::Matches($taskPatch,'(?m)^@@ ').Count;forward=$true;reverse=$true}
}
$taskExpected=@(Read-Text 'EXPECTED-CASES.json' | ConvertFrom-Json)
$taskOldExpected=@(Read-Text 'before/EXPECTED-CASES.json' | ConvertFrom-Json)
$taskNewExpectedPath=Join-Path $taskRoot '_scratch/controller-worker-stage-repair01/EXPECTED-CASES.json'
Assert-Task ((Get-Sha $taskNewExpectedPath) -ceq $taskMap.stage.expected14_sha256) 'Frozen14 changed'
$taskNewExpected=@([IO.File]::ReadAllText($taskNewExpectedPath) | ConvertFrom-Json)
Assert-Task ($taskExpected.Count -eq 95 -and @($taskExpected|Sort-Object -Unique).Count -eq 95 -and $taskOldExpected.Count -eq 81 -and $taskNewExpected.Count -eq 14) 'Exact95/81/14 membership'
for($taskIndex=0;$taskIndex -lt 81;$taskIndex++){Assert-Task ($taskExpected[$taskIndex] -ceq $taskOldExpected[$taskIndex]) 'Original81 order changed'}
for($taskIndex=0;$taskIndex -lt 14;$taskIndex++){Assert-Task ($taskExpected[81+$taskIndex] -ceq $taskNewExpected[$taskIndex]) 'Declared14 order changed'}
$taskMethodNames=@([regex]::Matches((Read-Text 'test_controller_worker_stage.py'),'(?m)^    def (test_[A-Za-z0-9_]+)\(') | ForEach-Object {$_.Groups[1].Value})
Assert-Task ($taskMethodNames.Count -eq 14) 'Exact14 source methods'
for($taskIndex=0;$taskIndex -lt 14;$taskIndex++){Assert-Task (('test_controller_worker_stage.ControllerWorkerStageContracts.'+$taskMethodNames[$taskIndex]) -ceq $taskNewExpected[$taskIndex]) 'New source-order mismatch'}
$taskAdapter=[IO.File]::ReadAllBytes((Join-Path $taskDir 'startup_fixture_adapter.py'))
$taskPrefix=[byte[]]$taskAdapter[0..28921]
Assert-Task ((Hash-Bytes $taskPrefix) -ceq $taskMap.stage.accepted_adapter_prefix_sha256) 'Entire accepted adapter prefix changed'
$taskQ=Read-Text 'qualify_windows_reservations.py'
$taskOldQ=Read-Text 'before/qualify_windows_reservations.py'
$taskModuleLine=[regex]::Match($taskQ,'(?m)^MODULES = \((.+)\)$')
$taskModuleNames=@([regex]::Matches($taskModuleLine.Groups[1].Value,'"([A-Za-z0-9_]+)"') | ForEach-Object {$_.Groups[1].Value})
Assert-Task (($taskModuleNames -join '|') -ceq (@($taskMap.modules) -join '|')) 'Loader/map order mismatch'
$taskOriginalModules=@((Read-Text 'before/SOURCE-INPUTS.json' | ConvertFrom-Json).modules)
Assert-Task (($taskModuleNames[0..20] -join '|') -ceq ($taskOriginalModules -join '|')) 'Original module order changed'
Assert-Task (($taskModuleNames[21..22] -join '|') -ceq 'worker_stage_fixture|test_controller_worker_stage') 'New dependency order mismatch'
function Captures([string]$text){
 $taskRows=@()
 foreach($taskMatch in [regex]::Matches($text,'(?m)^                    \("([^"]+)", \((.*?)\)\),$')){
  foreach($taskMethod in [regex]::Matches($taskMatch.Groups[2].Value,'"([^"]+)"')){$taskRows += ($taskMatch.Groups[1].Value+':'+$taskMethod.Groups[1].Value)}
 }
 return $taskRows
}
$taskOldFunctions=@(Captures $taskOldQ);$taskFunctions=@(Captures $taskQ)
Assert-Task ($taskOldFunctions.Count -eq 36 -and $taskFunctions.Count -eq 38) 'Exact36+2 function captures'
Assert-Task (($taskFunctions[0..35] -join '|') -ceq ($taskOldFunctions -join '|')) 'Original36 function captures changed'
Assert-Task (($taskFunctions[36..37] -join '|') -ceq 'startup_fixture_adapter:_validate_controller_worker_stage|startup_fixture_adapter:_validate_controller_worker_stage_locked') 'Exact stage function captures'
$taskOldImports=[regex]::Match($taskOldQ,'(?s)import contextlib.*?(?=assert sys.flags)').Value
$taskImports=[regex]::Match($taskQ,'(?s)import contextlib.*?(?=assert sys.flags)').Value
Assert-Task ($taskOldImports.Length -gt 0 -and $taskImports -ceq $taskOldImports) 'Preloads changed'
$taskTypeLines=@(
 '            STARTUP_KERNEL_TYPE = LOADED["durable_lifecycle"]._DurableKernel',
 '            assert LOADED["startup_fixture_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE',
 '        and LOADED["durable_lifecycle"]._DurableKernel is STARTUP_KERNEL_TYPE',
 '        and LOADED["startup_fixture_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE,'
)
foreach($taskLine in $taskTypeLines){Assert-Task ($taskQ.Contains($taskLine)) 'Exact type capture/check missing'}
$taskAuthor=Read-Text 'ROOT-ADMISSION.template.json'|ConvertFrom-Json
$taskConfirmation=Read-Text 'CONFIRMATION-ADMISSION.template.json'|ConvertFrom-Json
Assert-Task ($taskAuthor.approved -ceq $false -and $taskConfirmation.approved -ceq $false -and $taskAuthor.case_count -eq 95 -and $taskConfirmation.case_count -eq 95) 'False95 templates required'
Assert-Task ($taskAuthor.pins_sha256 -ceq (Get-Sha (Join-Path $taskDir 'PINS.json')) -and $null -eq $taskConfirmation.pins_sha256) 'Template binding mismatch'
Assert-Task ($taskAuthor.label -ceq 'controller-stage-fake01' -and $taskConfirmation.label -ceq 'controller-stage-confirmation01') 'Exact separate labels required'
foreach($taskForbidden in @('ROOT-ADMISSION.json','controller-stage-fake01','controller-stage-confirmation01')){Assert-Task (-not [IO.File]::Exists((Join-Path $taskDir $taskForbidden)) -and -not [IO.Directory]::Exists((Join-Path $taskDir $taskForbidden))) 'No actual admission or run permitted'}
[ordered]@{
 scope='Passive source/text proof only; no Python, imports, compilation or subject invocation'
 parent_inputs=29;parent_bytes=$taskBytesTotal;module_count=23;child_texts=25;before_copies=8
 old_case_prefix=81;new_source_order_cases=14;total_expected=95
 original_test_and_fixture_bytes_unchanged=$true;accepted_adapter_prefix_bytes=28922
 original_function_captures=36;new_stage_function_captures=2;fixed_kernel_type_capture=$true
 preloads_unchanged=$true;declared_diffs=$taskDiffResults;false_templates=$true;actual_admission_or_run=$false
 pins_sha256=(Get-Sha (Join-Path $taskDir 'PINS.json'))
} | ConvertTo-Json -Depth 8
