$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOriginal=Join-Path $taskRoot '_scratch\release-progress-startup81-20260914'
$taskAmendment=Join-Path $taskOriginal 'amendment02'
function Assert-Task([bool]$condition,[string]$message) { if(-not $condition){throw $message} }
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

$taskSource=Join-Path $taskOriginal 'amendment01\proposed\RELEASE-NOTES-LIVING-LIBRARY.md'
Assert-Task ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ceq 'd001a39cec31c38097ab44d40203d85c85b88c23fe09686ab24031315f9046f2') 'Frozen original proposal changed'
$taskFrozen=[IO.File]::ReadAllText((Join-Path $taskOriginal 'OUTPUT-BINDINGS.json')) | ConvertFrom-Json
foreach($taskRow in $taskFrozen.files){
  $taskPath=Join-Path $taskOriginal $taskRow.path
  Assert-Task ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskRow.sha256) ('Original frozen output changed: '+$taskRow.path)
}
$taskPrior=[IO.File]::ReadAllText((Join-Path $taskAmendment 'SOURCE-BINDINGS.json')) | ConvertFrom-Json
foreach($taskRow in $taskPrior.prior_amendment_inputs){
  Assert-Task ((Get-FileHash -LiteralPath (Join-Path $taskRoot $taskRow.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskRow.sha256) ('Prior amendment changed: '+$taskRow.path)
}
$taskBefore=[IO.File]::ReadAllText($taskSource)
$taskEdit=[IO.File]::ReadAllText((Join-Path $taskAmendment 'DECLARED-AMENDMENT.json')) | ConvertFrom-Json
Assert-Task ([regex]::Matches($taskBefore,[regex]::Escape([string]$taskEdit.before)).Count -eq 1) 'Exactly one old paragraph required'
$taskAfter=$taskBefore.Replace([string]$taskEdit.before,[string]$taskEdit.after)
$taskLF=[string][char]10
$taskCRLF=[string][char]13+[char]10
Assert-Task ($taskBefore.EndsWith($taskCRLF) -and ([regex]::Matches($taskBefore,[string][char]13).Count -eq 1)) 'Original line endings changed'
Assert-Task ($taskAfter.EndsWith($taskCRLF) -and ([regex]::Matches($taskAfter,[string][char]13).Count -eq 1)) 'Amendment changed line endings'
$taskPatch=[IO.File]::ReadAllText((Join-Path $taskAmendment 'RELEASE-NOTES-LIVING-LIBRARY.md.diff'))
$taskForward=Apply-TextDelta $taskBefore.Replace($taskCRLF,$taskLF) $taskPatch $false
$taskReverse=Apply-TextDelta $taskAfter.Replace($taskCRLF,$taskLF) $taskPatch $true
Assert-Task (($taskForward.Substring(0,$taskForward.Length-1)+$taskCRLF) -ceq $taskAfter) 'Forward reconstruction failed'
Assert-Task (($taskReverse.Substring(0,$taskReverse.Length-1)+$taskCRLF) -ceq $taskBefore) 'Reverse reconstruction failed'
$taskBeforePath=Join-Path $taskAmendment 'before\RELEASE-NOTES-LIVING-LIBRARY.md'
$taskAfterPath=Join-Path $taskAmendment 'proposed\RELEASE-NOTES-LIVING-LIBRARY.md'
Assert-Task (-not [IO.File]::Exists($taskBeforePath) -and -not [IO.File]::Exists($taskAfterPath)) 'Fresh amendment copies required'
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $taskBeforePath))
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $taskAfterPath))
[IO.File]::WriteAllBytes($taskBeforePath,[IO.File]::ReadAllBytes($taskSource))
[IO.File]::WriteAllText($taskAfterPath,$taskAfter,[Text.UTF8Encoding]::new($false,$true))
$taskRows=foreach($taskPair in @(@('before',$taskBeforePath),@('proposed',$taskAfterPath))){
 [ordered]@{role=$taskPair[0];path=$taskPair[1];bytes=([IO.File]::ReadAllBytes($taskPair[1])).Length;sha256=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{scope='Passive text-only amendment; no subject invocation';exact_one_paragraph_change=$true;forward_reconstruction_exact=$true;reverse_reconstruction_exact=$true;original_nine_frozen_outputs_unchanged=$true;prior_amendment_inputs_unchanged=$true;canonical_notes_unchanged=((Get-FileHash -LiteralPath (Join-Path $taskRoot 'docs\library\RELEASE-NOTES-LIVING-LIBRARY.md') -Algorithm SHA256).Hash.ToLowerInvariant() -ceq '957db525ddd81f5e1302fd930eaf5f80d78d561ebd91a49d02b2bbda4e6c4d00');outputs=@($taskRows)} | ConvertTo-Json -Depth 6
