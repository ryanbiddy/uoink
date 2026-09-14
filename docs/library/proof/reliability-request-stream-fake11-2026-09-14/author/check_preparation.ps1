$ErrorActionPreference='Stop'
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
$map=Text-Task 'SOURCE-INPUTS.json'|ConvertFrom-Json
Assert-Task (@($map.files).Count -eq 10) 'Exact ten provenance rows required'
$copies=@()
foreach($row in $map.files) {
    $original=[IO.File]::ReadAllBytes($row.source)
    $copy=[IO.File]::ReadAllBytes((Join-Path $taskBase $row.path))
    $originalHash=(Get-FileHash -LiteralPath $row.source -Algorithm SHA256).Hash.ToLowerInvariant()
    $copyHash=(Get-FileHash -LiteralPath (Join-Path $taskBase $row.path) -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-Task ($original.Length -eq $row.bytes -and $copy.Length -eq $row.bytes -and $originalHash -ceq $row.sha256 -and $copyHash -ceq $row.sha256) 'Exact frozen copy required'
    $copies += [ordered]@{path=$row.path;bytes=$row.bytes;sha256=$copyHash;original_unchanged=$true;copy_exact=$true}
}
$edits=Text-Task 'INSTRUMENT-EDITS.json'|ConvertFrom-Json
$checks=@()
foreach($unit in @(
    [ordered]@{kind='qualifier';before='before/qualify_windows_reservations.py';after='qualify_reliability.py';diff='qualify_reliability.diff'},
    [ordered]@{kind='launcher';before='before/run_preflight01.ps1';after='run_fake11_01.ps1';diff='run_fake11_01.diff'}
)) {
    $old=Text-Task $unit.before; $new=Text-Task $unit.after
    $rebuilt=$old
    foreach($edit in $edits.($unit.kind)) {
        $count=([regex]::Matches($rebuilt,[regex]::Escape($edit.before))).Count
        $expected=1
        if($unit.kind -ceq 'launcher') {$expected=$edit.occurrences}
        Assert-Task ($count -eq $expected) 'Exact declared substitution count required'
        $rebuilt=$rebuilt.Replace([string]$edit.before,[string]$edit.after)
    }
    Assert-Task ($rebuilt -ceq $new) 'Complete declared edit relationship required'
    $patch=Text-Task $unit.diff
    Assert-Task ((Apply-TextDelta $old $patch $false) -ceq $new) 'Complete forward delta reconstruction required'
    Assert-Task ((Apply-TextDelta $new $patch $true) -ceq $old) 'Complete reverse delta reconstruction required'
    $checks += [ordered]@{kind=$unit.kind;declared_substitutions_exact=$true;forward_exact=$true;reverse_exact=$true;sha256=(Get-FileHash -LiteralPath (Join-Path $taskBase $unit.after) -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$ids=@(Text-Task 'EXPECTED-CASES.json'|ConvertFrom-Json)
$testText=Text-Task 'test_reliability_request_stream.py'
$declared=@([regex]::Matches($testText,'(?m)^    def (test_[A-Za-z0-9_]+)\(self\):')|ForEach-Object {'test_reliability_request_stream.ReliabilityRequestStreamContracts.'+$_.Groups[1].Value})
Assert-Task ($ids.Count -eq 11 -and (($ids|ConvertTo-Json -Compress) -ceq ($declared|ConvertTo-Json -Compress))) 'Exact eleven supplied definition-order IDs required'
Assert-Task (-not $testText.Contains('unittest.mock') -and -not $testText.Contains('Path.is_file')) 'No mock preload or global Path method patch allowed'
$q=Text-Task 'qualify_reliability.py'
$expectedModules='MODULES = ("snapshot_lifecycle", "snapshot_reservations", "durable_lifecycle", "trusted_asr_resolver", "asr_loading_adapter", "uoink_reliability", "test_reliability_request_stream")'
Assert-Task ($q.Contains($expectedModules)) 'Exact module order required'
Assert-Task ($q.IndexOf('CONTENT_OPEN = False') -lt $q.IndexOf('exec(compile(')) 'Closed content before candidate compilation required'
Assert-Task ($q.Contains('and LOADED["uoink_reliability"]._RELIABILITY_MEDIA_TICKETS is None')) 'Final absent ticket-source assertion required'
$launcher=Text-Task 'run_fake11_01.ps1'
Assert-Task ($launcher.Contains('$taskNative = $global:LASTEXITCODE')) 'Global native-exit capture required'
Assert-Task (-not (Test-Path -LiteralPath (Join-Path $taskBase 'ROOT-ADMISSION.json'))) 'No actual admission permitted in preparation'
Assert-Task (-not (Test-Path -LiteralPath (Join-Path $taskBase 'reliability-request-stream-fake01'))) 'No run directory permitted in preparation'
[ordered]@{scope='passive text, hashes and JSON only';copies=$copies;instrument_relationships=$checks;ordered_ids=$ids;module_count=7;child_text_count=9;parent_input_count=13;no_new_preloads=$true;guard_structure_preserved=$true;candidate_execution=$false}|ConvertTo-Json -Depth 10
