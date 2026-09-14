$ErrorActionPreference='Stop'
$taskReview='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/real-engine-connection01-root-review'
$taskFrozen=Join-Path $taskReview 'frozen'
$taskOut='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/real-engine-connection01-owner-peer'
function Assert-Task([bool]$value,[string]$why){if(-not $value){throw $why}}
function Hash-Task([byte[]]$raw){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()}
function Apply-TextDelta([string]$before,[string]$patch,[bool]$reverse) {
    Assert-Task ($before.EndsWith([string][char]10) -and -not $before.Contains([char]13)) 'Exact LF subject required'
    $old=$before.Substring(0,$before.Length-1).Split([char]10)
    $all=$patch.TrimEnd([char]10).Split([char]10)
    $header=0
    while($header -lt $all.Length -and -not $all[$header].StartsWith('--- ')){$header++}
    Assert-Task ($header -lt $all.Length) 'Unified headers present'
    $lines=$all[$header..($all.Length-1)]
    Assert-Task ($lines[0].StartsWith('--- ') -and $lines[1].StartsWith('+++ ')) 'Separate patch headers required'
    $out=[Collections.Generic.List[string]]::new()
    $at=0; $i=2; $hunks=0
    while($i -lt $lines.Length) {
        Assert-Task ($lines[$i] -cmatch '^@@ -([0-9]+),([0-9]+) \+([0-9]+),([0-9]+) @@.*$') 'Valid full hunk header required'
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

$taskPinBytes=[IO.File]::ReadAllBytes((Join-Path $taskReview 'FROZEN-SOURCE-PINS.json'))
Assert-Task ((Hash-Task $taskPinBytes) -ceq '860ac15701fe82f0960867b9f9058e67792b3f2ca73d4ecef7a9799deb611371') 'Frozen source map identity'
$taskPins=[Text.Encoding]::UTF8.GetString($taskPinBytes) | ConvertFrom-Json -AsHashtable
Assert-Task ($taskPins.files.Count -eq 25) 'Fixed25 text members'
$taskRows=@()
foreach($taskPin in $taskPins.files){
 Assert-Task ($taskPin.path -cmatch '^frozen/[A-Za-z0-9_./-]+\.(py|md|json|diff)$' -and -not $taskPin.path.Contains('..')) 'Selected text path only'
 $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskReview $taskPin.path))
 Assert-Task ($taskRaw.Length -eq $taskPin.bytes -and (Hash-Task $taskRaw) -ceq $taskPin.sha256) 'Frozen source pin mismatch'
 $taskRows += [ordered]@{path=$taskPin.path;bytes=$taskRaw.Length;sha256=(Hash-Task $taskRaw)}
}
$taskPairs=@(
 @('before/worker_runtime_owner.py','worker_runtime_owner.py','worker_runtime_owner.diff'),
 @('before/owned_generation_protocol.py','owned_generation_protocol.py','owned_generation_protocol.diff'),
 @('before/after/whisperx/asr.py','after/whisperx/asr.py','asr.diff'),
 @('before/after/whisperx/_uoink_owned.py','after/whisperx/_uoink_owned.py','_uoink_owned.diff')
)
$taskDeltas=@()
foreach($taskPair in $taskPairs){
 $taskOld=[IO.File]::ReadAllText((Join-Path $taskFrozen $taskPair[0]))
 $taskNew=[IO.File]::ReadAllText((Join-Path $taskFrozen $taskPair[1]))
 $taskDiff=[IO.File]::ReadAllText((Join-Path $taskFrozen $taskPair[2]))
 Assert-Task ((Apply-TextDelta $taskOld $taskDiff $false) -ceq $taskNew) 'Full forward reconstruction'
 Assert-Task ((Apply-TextDelta $taskNew $taskDiff $true) -ceq $taskOld) 'Full reverse reconstruction'
 $taskDeltas += [ordered]@{before=$taskPair[0];after=$taskPair[1];patch=$taskPair[2];before_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskOld)));after_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskNew)));patch_sha256=(Hash-Task ([Text.Encoding]::UTF8.GetBytes($taskDiff)));forward=$true;reverse=$true}
}
$taskBaseline=@(
 @('worker_runtime_owner.py','25e57481197e07c8731d54a5313c822e482624f3bc106717870e15890c3362fe'),
 @('owned_generation_protocol.py','86977e0d953a9e25dbefb23d4559f06f90b8fb7f9dc61b2d6e8726cffcff9c20')
)
foreach($taskBase in $taskBaseline){
 $taskRaw=[IO.File]::ReadAllBytes('E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-repair02/'+$taskBase[0])
 Assert-Task ((Hash-Task $taskRaw) -ceq $taskBase[1]) 'Original repair02 binding unchanged'
}
$taskProof=[ordered]@{schema='uoink.real-engine-owner-peer-source-byte-check.v1';subject_executed=$false;source_acceptance=$false;frozen_pin_sha256=(Hash-Task $taskPinBytes);fixed_text_files=25;files=$taskRows;deltas=$taskDeltas;repair02_originals_matched=$true;limits='Hashes and passive text reconstruction only; no candidate import/compile/test/native invocation. Content-review coverage is recorded separately.'}
[IO.File]::WriteAllText((Join-Path $taskOut 'SOURCE-DIFF-BINDINGS.json'),($taskProof | ConvertTo-Json -Depth 14)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
[ordered]@{fixed_text_files=25;full_deltas=4;forward_reverse=$true;repair02_originals_matched=$true;subject_executed=$false;source_acceptance=$false} | ConvertTo-Json
