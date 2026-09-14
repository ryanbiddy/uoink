$ErrorActionPreference='Stop'
$taskRoot='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-fake39-author01'
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
$taskMap=(Read-Task 'SOURCE-INPUTS.json') | ConvertFrom-Json -AsHashtable
$taskAdmission=(Read-Task 'ROOT-ADMISSION.template.json') | ConvertFrom-Json -AsHashtable
$taskExpected=(Read-Task 'EXPECTED-CASES.json') | ConvertFrom-Json -AsHashtable
$taskPriorExpected=(Read-Task 'before/EXPECTED-CASES.json') | ConvertFrom-Json -AsHashtable
$taskCopy=(Read-Task 'COPY-BINDINGS.json') | ConvertFrom-Json -AsHashtable
$taskEdits=(Read-Task 'DECLARED-INSTRUMENT-EDITS.json') | ConvertFrom-Json -AsHashtable
Assert-Task ($taskPins.execution_authority -ceq $false -and $taskPins.subject_executed -ceq $false -and $taskPins.count -eq 40 -and $taskPins.files.Count -eq 40) 'Exact40 dormant parent inputs'
Assert-Task ($taskAdmission.root_reviewed -is [bool] -and $taskAdmission.root_reviewed -ceq $false) 'Only false admission template'
Assert-Task ($taskAdmission.scope -ceq 'protected-engine-ownership-fake-39-only' -and $taskAdmission.label -ceq 'protected-engine-fake01') 'Fixed future scope/label'
Assert-Task (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'ROOT-ADMISSION.json')) -and -not (Test-Path -LiteralPath (Join-Path $taskRoot 'runs'))) 'No actual admission/run tree'
$taskSeen=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$taskTotal=0
foreach($taskRow in $taskPins.files){
    Assert-Task ($taskSeen.Add($taskRow.path)) 'Unique primary input'
    $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskRoot $taskRow.path))
    Assert-Task ($taskRaw.Length -eq $taskRow.bytes -and (Hash-Task $taskRaw) -ceq $taskRow.sha256) 'Parent input pin mismatch'
    Assert-Task ($taskAdmission.input_sha256[$taskRow.path] -ceq $taskRow.sha256) 'False template exact pin mismatch'
    $taskTotal += $taskRaw.Length
}
Assert-Task ($taskAdmission.input_sha256.Count -eq 40 -and $taskMap.source_paths.Count -eq 38 -and $taskMap.source_sha256.Count -eq 38) 'Exact source/control membership'
foreach($taskName in $taskMap.source_paths.Keys){
    Assert-Task ($taskSeen.Contains($taskName)) 'Map must be child subset'
    Assert-Task ($taskMap.source_paths[$taskName] -ceq (($taskRoot.Replace('/','\'))+'\'+$taskName)) 'Fixed copied child source path'
    $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskRoot $taskName))
    Assert-Task ((Hash-Task $taskRaw) -ceq $taskMap.source_sha256[$taskName]) 'Child source map pin'
}
Assert-Task ($taskCopy.files.Count -eq 42) 'Fixed36 module and6 before copies'
foreach($taskRow in $taskCopy.files){
    $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskRoot $taskRow.name))
    $taskOriginal=[IO.File]::ReadAllBytes($taskRow.source)
    Assert-Task ((Hash-Task $taskRaw) -ceq $taskRow.sha256 -and (Hash-Task $taskOriginal) -ceq $taskRow.sha256) 'Original/copy source unchanged'
}
Assert-Task ($taskExpected.count -eq 39 -and $taskExpected.ordered_cases.Count -eq 39 -and $taskAdmission.expected_cases.Count -eq 39) 'Exact39 case objects planned'
for($taskIndex=0;$taskIndex -lt 39;$taskIndex++){
    Assert-Task ($taskExpected.ordered_cases[$taskIndex] -ceq $taskAdmission.expected_cases[$taskIndex]) 'Template case order'
    if($taskIndex -lt 33){Assert-Task ($taskExpected.ordered_cases[$taskIndex] -ceq $taskPriorExpected.ordered_cases[$taskIndex]) 'Original33 ordered IDs unchanged'}
}
$taskGroups=@(
    @('generated_unit_cases.py','generated_unit_cases.OwnerContracts.',0,11),
    @('connection_cases.py','connection_cases.BootstrapContracts.',11,6),
    @('native_owner_cases.py','native_owner_cases.NativeOwnerContracts.',17,16),
    @('test_engine_ownership.py','test_engine_ownership.EngineOwnershipContracts.',33,6)
)
foreach($taskGroup in $taskGroups){
    $taskSource=Read-Task $taskGroup[0]
    $taskMethods=@([regex]::Matches($taskSource,'(?m)^    def (test_[A-Za-z0-9_]+)\(self\):'))
    Assert-Task ($taskMethods.Count -eq $taskGroup[3]) 'Actual test-definition membership'
    for($taskIndex=0;$taskIndex -lt $taskMethods.Count;$taskIndex++){
        Assert-Task (($taskGroup[1]+$taskMethods[$taskIndex].Groups[1].Value) -ceq $taskExpected.ordered_cases[$taskGroup[2]+$taskIndex]) 'Actual test source ordered IDs'
    }
}
$taskPairs=@(
    @('before/qualify_owner.py','qualify_owner.py','qualify_owner.diff','qualifier'),
    @('before/run_fake33_01.ps1','run_fake39_01.ps1','run_fake39_01.diff','launcher')
)
$taskDeltaRows=@()
foreach($taskPair in $taskPairs){
    $taskBefore=Read-Task $taskPair[0];$taskAfter=Read-Task $taskPair[1];$taskDelta=Read-Task $taskPair[2]
    Assert-Task ((Apply-TextDelta $taskBefore $taskDelta $false) -ceq $taskAfter) 'Full forward delta reconstruction'
    Assert-Task ((Apply-TextDelta $taskAfter $taskDelta $true) -ceq $taskBefore) 'Full reverse delta reconstruction'
    $taskRebuilt=$taskBefore
    foreach($taskEdit in $taskEdits[$taskPair[3]]){
        $taskCount=1;if($taskEdit.ContainsKey('count')){$taskCount=$taskEdit.count}
        Assert-Task ([regex]::Matches($taskRebuilt,[regex]::Escape($taskEdit.before)).Count -eq $taskCount) 'Declared edit exact multiplicity'
        $taskRebuilt=$taskRebuilt.Replace($taskEdit.before,$taskEdit.after)
    }
    Assert-Task ($taskRebuilt -ceq $taskAfter) 'Only the declared instrument edits'
    $taskDeltaRows += [ordered]@{before=$taskPair[0];after=$taskPair[1];diff=$taskPair[2];before_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskBefore)));after_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskAfter)));forward=$true;reverse=$true;declared_edits_only=$true}
}
$taskQualifier=Read-Task 'qualify_owner.py'
$taskModules=[regex]::Match($taskQualifier,'(?m)^MODULES = (.+)$').Groups[1].Value
$taskModuleNames=@([regex]::Matches($taskModules,"'([a-z0-9_]+)'") | ForEach-Object {$_.Groups[1].Value})
Assert-Task ($taskModuleNames.Count -eq 36 -and $taskModuleNames[8] -ceq 'generated_engine_objects' -and $taskModuleNames[9] -ceq 'worker_runtime_owner' -and $taskModuleNames[35] -ceq 'test_engine_ownership') 'Fixed explicit new module order'
$taskQInputs=@([regex]::Matches([regex]::Match($taskQualifier,'(?m)^INPUTS = (.+)$').Groups[1].Value,"'([^']+)'") | ForEach-Object {$_.Groups[1].Value})
Assert-Task ($taskQInputs.Count -eq 38) 'Exact child content closure'
for($taskIndex=0;$taskIndex -lt 36;$taskIndex++){Assert-Task ($taskQInputs[$taskIndex] -ceq ($taskModuleNames[$taskIndex]+'.py')) 'Module/read order'}
Assert-Task ($taskQInputs[36] -ceq 'qualify_owner.py' -and $taskQInputs[37] -ceq 'EXPECTED-CASES.json') 'Final fixed child inputs'
$taskQHashes=[regex]::Match($taskQualifier,'(?m)^SOURCE_PINS = (.+)$').Groups[1].Value | ConvertFrom-Json -AsHashtable
Assert-Task ($taskQHashes.Count -eq 37) 'Noncircular child pin membership'
foreach($taskName in $taskQHashes.Keys){Assert-Task ($taskQHashes[$taskName] -ceq $taskMap.source_sha256[$taskName]) 'Literal child source pin'}
$taskBeforeLauncher=Read-Task 'before/run_fake33_01.ps1';$taskLauncher=Read-Task 'run_fake39_01.ps1'
$taskNativePattern='(?s)# BEGIN EXACT NATIVE RECEIPT BLOCK.*?# END EXACT NATIVE RECEIPT BLOCK'
Assert-Task ([regex]::Match($taskBeforeLauncher,$taskNativePattern).Value -ceq [regex]::Match($taskLauncher,$taskNativePattern).Value) 'Exact immediate global native-exit block unchanged'
$taskPreloadPattern='(?s)\A.*?assert sys.flags.isolated'
Assert-Task ([regex]::Match((Read-Task 'before/qualify_owner.py'),$taskPreloadPattern).Value -ceq [regex]::Match($taskQualifier,$taskPreloadPattern).Value) 'All setup imports and startup winreg wrappers unchanged'
$taskReport=[ordered]@{
    schema='uoink.protected-engine-fake39-passive-preparation-check.v1'
    subject_executed=$false
    execution_authority=$false
    parent_inputs=40
    parent_bytes=$taskTotal
    child_texts=38
    modules=36
    case_count=39
    original_ordered_ids_unchanged=33
    unchanged_original_module_copies=32
    original_case_files_unchanged=@('generated_unit_cases.py','connection_cases.py','native_owner_cases.py')
    new_cases=6
    before_inputs=6
    source_copy_pairs=42
    setup_imports_and_startup_guard_unchanged=$true
    immediate_native_exit_block_unchanged=$true
    delta_reconstruction=$taskDeltaRows
    false_template=$true
    no_actual_admission_or_run_tree=$true
    limit='Passive exact-byte/source-membership check only. No import, compilation, test, subject, native, model or artifact execution.'
}
[IO.File]::WriteAllText((Join-Path $taskRoot 'PRESERVATION-CHECK.json'),($taskReport | ConvertTo-Json -Depth 12)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$taskReport | ConvertTo-Json -Depth 12
