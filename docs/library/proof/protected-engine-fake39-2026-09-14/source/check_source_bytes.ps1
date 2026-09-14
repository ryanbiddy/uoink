$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskBase=$PSScriptRoot
function Assert-Task($condition,[string]$reason) { if(-not $condition) { throw $reason } }
function Text-Task([string]$name) { return [IO.File]::ReadAllText((Join-Path $taskBase $name)) }
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
$taskPlan=@(
    [ordered]@{path='docs/library/PROTECTED-ENGINE-OWNERSHIP-REPAIR-BRIEF-2026-09-14.md';role='repair_scope';accepted_key=$null},
    [ordered]@{path='docs/library/ASTRA-PROTECTED-CONSTRUCTOR01-FAILURE-2026-09-14.md';role='preserved_failure';accepted_key=$null},
    [ordered]@{path='_scratch/runtime-next-source-plan-2026-09-14/SOURCE-INPUTS.json';role='original_source_plan';accepted_key=$null},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/worker_runtime_owner.py';role='accepted_original';accepted_key='worker_runtime_owner.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/owned_generation_protocol.py';role='accepted_original';accepted_key='owned_generation_protocol.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/owned_factory_port.py';role='accepted_original';accepted_key='owned_factory_port.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/model_binding_registry.py';role='accepted_original';accepted_key='model_binding_registry.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/owned_guard.py';role='accepted_original';accepted_key='owned_guard.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/state_bridge.py';role='accepted_original';accepted_key='state_bridge.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/plain_state_reader.py';role='accepted_original';accepted_key='plain_state_reader.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/owned_cpu_tensor_port.py';role='accepted_original';accepted_key='owned_cpu_tensor_port.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/fake_torch_support.py';role='accepted_original';accepted_key='fake_torch_support.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/fixed_schema_helpers.py';role='accepted_original';accepted_key='fixed_schema_helpers.py'},
    [ordered]@{path='_scratch/windows-interrupted-owner-native-proposal02/snapshot_lifecycle.py';role='accepted_original';accepted_key='snapshot_lifecycle.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/generated_bootstrap_fixture.py';role='unchanged_fixture_or_case_reference';accepted_key='generated_bootstrap_fixture.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/generated_factory_fixture.py';role='unchanged_fixture_or_case_reference';accepted_key='generated_factory_fixture.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/generated_unit_cases.py';role='unchanged_fixture_or_case_reference';accepted_key='generated_unit_cases.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/connection_cases.py';role='unchanged_fixture_or_case_reference';accepted_key='connection_cases.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/native_owner_cases.py';role='unchanged_fixture_or_case_reference';accepted_key='native_owner_cases.py'},
    [ordered]@{path='_scratch/runtime-owner-native-connection-proposal01/EXPECTED-CASES.json';role='unchanged_fixture_or_case_reference';accepted_key='EXPECTED-CASES.json'},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/worker_runtime_owner.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/owned_generation_protocol.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/generated_engine_objects.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/test_engine_ownership.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/NEW-CASE-IDS.json';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/before/worker_runtime_owner.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/before/owned_generation_protocol.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/before/owned_factory_port.py';role='new_or_preserved_local_text';accepted_key=$null},
    [ordered]@{path='_scratch/protected-engine-ownership-repair02/before/model_binding_registry.py';role='new_or_preserved_local_text';accepted_key=$null}
)
$taskAcceptedText=[IO.File]::ReadAllText((Join-Path $taskRoot '_scratch/runtime-owner-native-connection-proposal01/qualify_owner.py'))
Assert-Task ($taskAcceptedText -cmatch '(?m)^SOURCE_PINS = (\{[^\r\n]+\})$') 'Retained accepted source pins required'
$taskAccepted=$Matches[1]|ConvertFrom-Json
$taskSources=@()
foreach($row in $taskPlan) {
    $path=Join-Path $taskRoot $row.path
    $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $size=(Get-Item -LiteralPath $path).Length
    if($null -ne $row.accepted_key) {
        $expected=$taskAccepted.PSObject.Properties[$row.accepted_key].Value
        Assert-Task ($null -ne $expected -and $hash -ceq $expected) 'Accepted source/test reference changed'
    }
    $taskSources += [ordered]@{path=$row.path;role=$row.role;bytes=$size;sha256=$hash;matched_accepted_pin=($null -ne $row.accepted_key)}
}
Assert-Task ($taskSources.Count -eq 29) 'Exact 29 input rows required'
$edits=Text-Task 'FINAL-CORE-EDITS.json'|ConvertFrom-Json
$checks=@()
foreach($name in @('worker_runtime_owner','owned_generation_protocol')) {
    $old=Text-Task ('before/'+$name+'.py'); $new=Text-Task ($name+'.py')
    $rebuilt=$old
    foreach($edit in @($edits|Where-Object {$_.file -ceq ($name+'.py')})) {
        Assert-Task (([regex]::Matches($rebuilt,[regex]::Escape($edit.before))).Count -eq 1) 'Single exact declared source change required'
        $rebuilt=$rebuilt.Replace([string]$edit.before,[string]$edit.after)
    }
    Assert-Task ($rebuilt -ceq $new) 'Full declared source relationship required'
    $patch=Text-Task ($name+'.diff')
    Assert-Task ((Apply-TextDelta $old $patch $false) -ceq $new) 'Full forward reconstruction required'
    Assert-Task ((Apply-TextDelta $new $patch $true) -ceq $old) 'Full reverse reconstruction required'
    $checks += [ordered]@{name=$name;declared_changes_exact=$true;forward_exact=$true;reverse_exact=$true}
}
foreach($name in @('worker_runtime_owner.py','owned_generation_protocol.py','owned_factory_port.py','model_binding_registry.py')) {
    $before=Get-FileHash -LiteralPath (Join-Path $taskBase ('before/'+$name)) -Algorithm SHA256
    $original=Get-FileHash -LiteralPath (Join-Path $taskRoot ('_scratch/windows-interrupted-owner-native-proposal02/'+$name)) -Algorithm SHA256
    Assert-Task ($before.Hash -ceq $original.Hash) 'Exact original before copy required'
}
$ids=@(Text-Task 'NEW-CASE-IDS.json'|ConvertFrom-Json)
$testText=Text-Task 'test_engine_ownership.py'
$declared=@([regex]::Matches($testText,'(?m)^    def (test_[A-Za-z0-9_]+)\(self\):')|ForEach-Object {'test_engine_ownership.EngineOwnershipContracts.'+$_.Groups[1].Value})
Assert-Task ($ids.Count -eq 6 -and (($ids|ConvertTo-Json -Compress) -ceq ($declared|ConvertTo-Json -Compress))) 'Exact six definition-order IDs required'
$tupleIDs=@([regex]::Matches($testText,"(?m)^    '(test_engine_ownership\.[^']+)',")|ForEach-Object {$_.Groups[1].Value})
Assert-Task (($tupleIDs|ConvertTo-Json -Compress) -ceq ($ids|ConvertTo-Json -Compress)) 'Literal expected tuple must match'
Assert-Task (-not $testText.Contains('unittest.mock')) 'No new mock import allowed'
$taskMap=[ordered]@{schema='uoink.protected-engine-ownership-source-inputs.v1';execution_authority=$false;files=$taskSources}
$taskOutput=Join-Path $taskBase 'SOURCE-INPUTS.json'
Assert-Task (-not (Test-Path -LiteralPath $taskOutput)) 'Fresh source map required'
[IO.File]::WriteAllText($taskOutput,($taskMap|ConvertTo-Json -Depth 8)+[char]10,[Text.UTF8Encoding]::new($false))
[ordered]@{scope='passive source/hash/JSON checks only';sources=$taskSources;core_deltas=$checks;ordered_cases=$ids;original_tests_unchanged=$true;original_factory_and_registry_unchanged=$true;new_cases_executed=0;python_started=$false;source_map_sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant()}|ConvertTo-Json -Depth 10
