$ErrorActionPreference = 'Stop'
$taskBase = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskSubject = Join-Path $taskBase 'interrupted-owner-prelock-fake30-author03'
$taskPrior = Join-Path $taskBase 'interrupted-retirement-fake28-author01'
$taskControls = Join-Path $taskBase 'interrupted-owner-prelock-controls03'
$taskObserved = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
function Read-Text([string]$path) {
    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Non-flat text input' }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskObserved.ContainsKey($path) -and $taskObserved[$path] -cne $hash) { throw 'Input changed during review' }
    $taskObserved[$path] = $hash
    return [IO.File]::ReadAllText($path)
}
function Lines([string]$text) {
    $normalized = $text.Replace("`r`n", "`n")
    if ($normalized.EndsWith("`n")) { $normalized = $normalized.Substring(0, $normalized.Length - 1) }
    return ,$normalized.Split("`n")
}
function Check-Delta([string]$name, [string]$diffName) {
    $oldPath = Join-Path (Join-Path $taskSubject 'before') $name
    $oldText = Read-Text $oldPath
    $priorText = Read-Text (Join-Path $taskPrior $name)
    if ($taskObserved[$oldPath] -cne $taskObserved[(Join-Path $taskPrior $name)]) { throw 'Before bytes differ from accepted origin' }
    $old = Lines $oldText
    $new = Lines (Read-Text (Join-Path $taskSubject $name))
    $delta = Lines (Read-Text (Join-Path $taskSubject $diffName))
    if ($delta[0] -cne ('--- a/' + $name) -or $delta[1] -cne ('+++ b/' + $name)) { throw 'Unexpected diff headers' }
    $out = [Collections.Generic.List[string]]::new()
    $cursor = 0; $k = 2; $hunks = 0
    while ($k -lt $delta.Count) {
        if ($k -eq $delta.Count - 1 -and $delta[$k] -ceq '') { break }
        $m = [regex]::Match($delta[$k], '^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$')
        if (-not $m.Success) { throw ('Malformed hunk header at line ' + ($k + 1)) }
        $start = [int]$m.Groups[1].Value - 1
        $oldCount = [int]$m.Groups[2].Value
        $newStart = [int]$m.Groups[3].Value - 1
        $newCount = [int]$m.Groups[4].Value
        if ($cursor -gt $start) { throw 'Overlapping hunk' }
        while ($cursor -lt $start) { $out.Add($old[$cursor]); $cursor++ }
        if ($out.Count -ne $newStart) { throw 'New hunk position mismatch' }
        $seenOld = 0; $seenNew = 0; $k++; $hunks++
        while ($k -lt $delta.Count -and -not $delta[$k].StartsWith('@@ ')) {
            $line = $delta[$k]
            if ($line.Length -eq 0) {
                if ($k -eq $delta.Count - 1 -and $seenOld -eq $oldCount -and $seenNew -eq $newCount) { $k++; break }
                throw 'Unexpected empty diff line'
            }
            $kind = $line.Substring(0, 1); $body = $line.Substring(1)
            if ($kind -ceq ' ' -or $kind -ceq '-') {
                if ($cursor -ge $old.Count -or $old[$cursor] -cne $body) { throw 'Hunk old line mismatch' }
                $cursor++; $seenOld++
            }
            if ($kind -ceq ' ' -or $kind -ceq '+') { $out.Add($body); $seenNew++ }
            if ($kind -cne ' ' -and $kind -cne '-' -and $kind -cne '+') { throw 'Invalid diff opcode' }
            $k++
        }
        if ($seenOld -ne $oldCount -or $seenNew -ne $newCount) { throw 'Hunk count mismatch' }
    }
    while ($cursor -lt $old.Count) { $out.Add($old[$cursor]); $cursor++ }
    if ($out.Count -ne $new.Count) { throw 'Reconstructed length mismatch' }
    for ($i = 0; $i -lt $new.Count; $i++) { if ($out[$i] -cne $new[$i]) { throw 'Reconstructed text mismatch' } }
    return [ordered]@{file=$name; hunks=$hunks; old_lines=$old.Count; new_lines=$new.Count; exact_LF_line_reconstruction=$true; before_raw_bytes_equal_accepted_origin=$true}
}
function Module-Names([string]$source) {
    $match = [regex]::Match($source, '(?m)^MODULES = \(([^\r\n]+)\)')
    if (-not $match.Success) { throw 'Module declaration missing' }
    return ,@([regex]::Matches($match.Groups[1].Value, '"([a-z_][a-z0-9_]*)"') | ForEach-Object { $_.Groups[1].Value })
}
$taskDeltas = @(
    (Check-Delta 'qualify_windows_reservations.py' 'qualify_windows_reservations.diff')
    (Check-Delta 'run_preflight01.ps1' 'run_preflight01.diff')
)
$taskPinsPath = Join-Path $taskSubject 'PINS.json'
$taskPins = (Read-Text $taskPinsPath) | ConvertFrom-Json
if ($taskPins.finalized -ne $true -or $taskPins.files.Count -ne 39) { throw 'Pin count/finalization mismatch' }
$taskBytes = 0
foreach ($row in $taskPins.files) {
    if ($row.path -cnotmatch '^[A-Za-z0-9_.-]+$') { throw 'Non-flat pin name' }
    $path = Join-Path $taskSubject $row.path
    $null = Read-Text $path
    if ((Get-Item -LiteralPath $path).Length -ne $row.bytes -or $taskObserved[$path] -cne $row.sha256) { throw ('Pin mismatch: ' + $row.path) }
    $taskBytes += $row.bytes
}
$taskModules = Module-Names (Read-Text (Join-Path $taskSubject 'qualify_windows_reservations.py'))
$taskOldModules = Module-Names (Read-Text (Join-Path $taskPrior 'qualify_windows_reservations.py'))
if ($taskModules.Count -ne 34 -or $taskOldModules.Count -ne 33 -or $taskModules[-1] -cne 'test_interrupted_owner_prelock') { throw 'Explicit new module last' }
if (($taskModules[0..32] -join "`n") -cne ($taskOldModules -join "`n")) { throw 'Old module order changed' }
$taskChild = @($taskModules | ForEach-Object { $_ + '.py' }) + @('qualify_windows_reservations.py','EXPECTED-CASES.json')
$taskParent = $taskChild + @('run_preflight01.ps1','QUALIFICATION-PROTOCOL.md','BRIEF.md')
if ($taskChild.Count -ne 36 -or $taskParent.Count -ne 39 -or (@($taskPins.files.path | Sort-Object -Unique).Count -ne 39)) { throw 'Input closure count mismatch' }
if ((@($taskParent | Sort-Object) -join "`n") -cne (@($taskPins.files.path | Sort-Object) -join "`n")) { throw 'Input closure membership mismatch' }
$taskUnchanged = 0
foreach ($name in $taskOldModules) {
    if ($name -ceq 'generated_adapter_flow') { continue }
    $oldPath = Join-Path $taskPrior ($name + '.py')
    $newPath = Join-Path $taskSubject ($name + '.py')
    $null = Read-Text $oldPath
    if ($taskObserved[$oldPath] -cne $taskObserved[$newPath]) { throw ('Inherited module changed: ' + $name) }
    $taskUnchanged++
}
$taskExpected = (Read-Text (Join-Path $taskSubject 'EXPECTED-CASES.json')) | ConvertFrom-Json
$taskOldExpected = (Read-Text (Join-Path $taskPrior 'EXPECTED-CASES.json')) | ConvertFrom-Json
$taskAdded = (Read-Text (Join-Path $taskControls 'NEW-CASE-IDS.json')) | ConvertFrom-Json
if ($taskExpected.Count -ne 30 -or $taskOldExpected.Count -ne 28 -or $taskAdded.Count -ne 2) { throw 'Case count mismatch' }
if (($taskExpected[0..27] -join "`n") -cne ($taskOldExpected -join "`n") -or ($taskExpected[28..29] -join "`n") -cne ($taskAdded -join "`n")) { throw 'Case order mismatch' }
if (@($taskExpected | Sort-Object -Unique).Count -ne 30) { throw 'Duplicate case' }
$taskFixtureNames = @('test_reservations','test_windows_reservations','test_journal_cancel','test_retired_owner_recovery','test_interrupted_owner_retirement')
$taskFixtureBindings = @($taskFixtureNames | ForEach-Object { [ordered]@{name=$_ + '.py'; sha256=$taskObserved[(Join-Path $taskSubject ($_ + '.py'))]; unchanged=$true} })
$taskTemplate = (Read-Text (Join-Path $taskSubject 'ROOT-ADMISSION.template.json')) | ConvertFrom-Json
if ($taskTemplate.approved -ne $false -or $taskTemplate.pins_sha256 -cne $taskObserved[$taskPinsPath] -or $taskTemplate.scope -cne 'generated_bytes_and_fake_ports_only') { throw 'False template binding mismatch' }
foreach ($entry in $taskObserved.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) { throw 'Reviewed input changed' }
}
[ordered]@{
    status='PASS'; scope='passive fixed text reconstruction and bindings only'; candidate_executed=$false
    deltas=$taskDeltas; pins_sha256=$taskObserved[$taskPinsPath]; parent_inputs=39; payload_bytes=$taskBytes
    child_text_inputs=36; module_count=34; unchanged_module_count=$taskUnchanged; new_module_last=$true
    original_ordered_cases=28; appended_ordered_cases=$taskAdded; total_cases=30; old_fixtures=$taskFixtureBindings
    false_template=$true; reviewed_text_inputs=$taskObserved.Count; all_reviewed_inputs_unchanged=$true
} | ConvertTo-Json -Depth 8
