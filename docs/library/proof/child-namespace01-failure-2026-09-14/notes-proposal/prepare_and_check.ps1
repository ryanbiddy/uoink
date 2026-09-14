$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskPrep = Join-Path $taskRoot '_scratch\release-progress-startup81-20260914'
$taskCanonical = Join-Path $taskRoot 'docs\library\RELEASE-NOTES-LIVING-LIBRARY.md'
$taskBefore = Join-Path $taskPrep 'before\RELEASE-NOTES-LIVING-LIBRARY.md'
$taskAfter = Join-Path $taskPrep 'proposed\RELEASE-NOTES-LIVING-LIBRARY.md'
$taskExpectedSourceHash = '957db525ddd81f5e1302fd930eaf5f80d78d561ebd91a49d02b2bbda4e6c4d00'
function Assert-Task([bool]$condition,[string]$message) { if (-not $condition) { throw $message } }
function Hash-Bytes([byte[]]$bytes) {
    $taskSha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($taskSha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
    finally { $taskSha.Dispose() }
}
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

$taskBeforeBytes = [IO.File]::ReadAllBytes($taskCanonical)
Assert-Task ((Hash-Bytes $taskBeforeBytes) -ceq $taskExpectedSourceHash) 'Canonical input changed before proposal preparation'
$taskEncoding = [Text.UTF8Encoding]::new($false,$true)
$taskBeforeText = $taskEncoding.GetString($taskBeforeBytes)
Assert-Task ((Hash-Bytes $taskEncoding.GetBytes($taskBeforeText)) -ceq $taskExpectedSourceHash) 'Exact UTF8 roundtrip required'
Assert-Task (-not [IO.File]::Exists($taskBefore) -and -not [IO.File]::Exists($taskAfter)) 'Fresh before and proposed paths required'
$taskEdits = ([IO.File]::ReadAllText((Join-Path $taskPrep 'DECLARED-EDITS.json')) | ConvertFrom-Json).edits
Assert-Task (@($taskEdits).Count -eq 3) 'Exactly three declared edit groups'
$taskAfterText = $taskBeforeText
foreach ($taskEdit in $taskEdits) {
    Assert-Task ([regex]::Matches($taskAfterText,[regex]::Escape([string]$taskEdit.before)).Count -eq 1) ('Unique exact source span required: '+$taskEdit.id)
    $taskAfterText = $taskAfterText.Replace([string]$taskEdit.before,[string]$taskEdit.after)
}
$taskLF = [string][char]10
$taskCRLF = [string][char]13 + [char]10
Assert-Task ($taskBeforeText.EndsWith($taskCRLF) -and ([regex]::Matches($taskBeforeText,[string][char]13).Count -eq 1)) 'Preserved original LF body/final CRLF required'
Assert-Task ($taskAfterText.EndsWith($taskCRLF) -and ([regex]::Matches($taskAfterText,[string][char]13).Count -eq 1)) 'No line-ending changes permitted'
$taskPatch = [IO.File]::ReadAllText((Join-Path $taskPrep 'RELEASE-NOTES-LIVING-LIBRARY.md.diff'))
$taskForward = Apply-TextDelta $taskBeforeText.Replace($taskCRLF,$taskLF) $taskPatch $false
$taskReverse = Apply-TextDelta $taskAfterText.Replace($taskCRLF,$taskLF) $taskPatch $true
$taskForwardExact = $taskForward.Substring(0,$taskForward.Length-1) + $taskCRLF
$taskReverseExact = $taskReverse.Substring(0,$taskReverse.Length-1) + $taskCRLF
Assert-Task ($taskForwardExact -ceq $taskAfterText) 'Full forward reconstruction mismatch'
Assert-Task ($taskReverseExact -ceq $taskBeforeText) 'Full reverse reconstruction mismatch'
$taskOldTables = @($taskBeforeText.Split([char]10) | Where-Object { $_.StartsWith('|') })
$taskNewTables = @($taskAfterText.Split([char]10) | Where-Object { $_.StartsWith('|') })
Assert-Task ([string]::Join($taskLF,$taskOldTables) -ceq [string]::Join($taskLF,$taskNewTables)) 'Historical tables changed'
$taskBeforeLines = $taskBeforeText.Split([char]10)
$taskPreservedRanges = @(
    @(1,142), @(149,185), @(188,688), @(690,750)
)
foreach ($taskRange in $taskPreservedRanges) {
    $taskSpan = [string]::Join($taskLF,$taskBeforeLines[($taskRange[0]-1)..($taskRange[1]-1)])
    Assert-Task ($taskAfterText.Contains($taskSpan)) ('Unchanged historical/current span missing: '+$taskRange[0]+'-'+$taskRange[1])
}
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $taskBefore))
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $taskAfter))
[IO.File]::WriteAllBytes($taskBefore,$taskBeforeBytes)
[IO.File]::WriteAllBytes($taskAfter,$taskEncoding.GetBytes($taskAfterText))
$taskAfterBytes = [IO.File]::ReadAllBytes($taskAfter)
Assert-Task ((Hash-Bytes ([IO.File]::ReadAllBytes($taskBefore))) -ceq $taskExpectedSourceHash) 'Before-copy bytes changed'
Assert-Task ((Hash-Bytes $taskAfterBytes) -ceq (Hash-Bytes $taskEncoding.GetBytes($taskForwardExact))) 'Written proposal differs from reconstructed bytes'
Assert-Task ((Hash-Bytes ([IO.File]::ReadAllBytes($taskCanonical))) -ceq $taskExpectedSourceHash) 'Canonical input changed'
$taskBindings = [IO.File]::ReadAllText((Join-Path $taskPrep 'SOURCE-BINDINGS.json')) | ConvertFrom-Json
$taskContextRows = foreach ($taskInput in $taskBindings.inputs) {
    $taskActualHash = (Get-FileHash -LiteralPath (Join-Path $taskRoot $taskInput.path) -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{path=$taskInput.path;observed_source_hash=$taskInput.sha256;current_hash=$taskActualHash;unchanged=($taskActualHash -ceq $taskInput.sha256)}
}
[ordered]@{
    scope='Passive text-only proposal creation and byte verification; no subject invocation'
    declared_edit_groups=3
    unified_hunks=([regex]::Matches($taskPatch,'(?m)^@@ ').Count)
    forward_reconstruction_exact=$true
    reverse_reconstruction_exact=$true
    original_line_endings_preserved=$true
    complete_tables_unchanged=$true
    table_lines=$taskOldTables.Count
    preserved_original_ranges=@($taskPreservedRanges | ForEach-Object { "$($_[0])-$($_[1])" })
    canonical_notes_unchanged=$true
    before=[ordered]@{path=$taskBefore;bytes=$taskBeforeBytes.Length;sha256=$taskExpectedSourceHash}
    proposed=[ordered]@{path=$taskAfter;bytes=$taskAfterBytes.Length;sha256=(Hash-Bytes $taskAfterBytes)}
    context_bindings=@($taskContextRows)
} | ConvertTo-Json -Depth 8
