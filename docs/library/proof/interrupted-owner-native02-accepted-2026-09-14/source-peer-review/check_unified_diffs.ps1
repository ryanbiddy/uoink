$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskOld=Join-Path $taskBase 'windows-interrupted-owner-native-proposal01'
$taskNew=Join-Path $taskBase 'windows-interrupted-owner-native-proposal02'
function Task-Assert([bool]$ok,[string]$message){if(-not $ok){throw $message}}
function Task-Sha256([string]$path){return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Task-Reconstruct([string]$source,[string]$patch,[bool]$reverse){
    Task-Assert ($source.EndsWith("`n") -and $patch.EndsWith("`n")) 'Fixed text must end with newline'
    $sourceEol=if($source.Contains("`r`n")){"`r`n"}else{"`n"}
    $sourceNormalized=$source.Replace("`r`n","`n")
    Task-Assert (-not $sourceNormalized.Contains("`r") -and $sourceNormalized.Replace("`n",$sourceEol) -ceq $source) 'Uniform source line endings'
    $source=$sourceNormalized
    $patch=$patch.Replace("`r`n","`n")
    Task-Assert (-not $patch.Contains("`r")) 'No bare CR in unified patch'
    $src=$source.Substring(0,$source.Length-1).Split([char]10)
    $lines=$patch.Substring(0,$patch.Length-1).Split([char]10)
    Task-Assert ($lines.Count -ge 4 -and $lines[0].StartsWith('--- ') -and $lines[1].StartsWith('+++ ') -and $lines[2].StartsWith('@@ ')) 'Separate unified headers'
    $out=[Collections.Generic.List[string]]::new();$sourceCursor=0;$index=2;$hunks=0
    while($index -lt $lines.Count){
        $match=[regex]::Match($lines[$index],'^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(?:.*)?$')
        Task-Assert $match.Success 'Valid unified hunk header'
        $oldStart=[int]$match.Groups[1].Value;$newStart=[int]$match.Groups[3].Value
        $oldCount=if($match.Groups[2].Success){[int]$match.Groups[2].Value}else{1}
        $newCount=if($match.Groups[4].Success){[int]$match.Groups[4].Value}else{1}
        if($reverse){$swap=$oldStart;$oldStart=$newStart;$newStart=$swap;$swap=$oldCount;$oldCount=$newCount;$newCount=$swap}
        $startOffset=if($oldCount -eq 0){$oldStart}else{$oldStart-1}
        Task-Assert ($startOffset -ge $sourceCursor -and $startOffset -le $src.Count) 'Ordered hunk location'
        while($sourceCursor -lt $startOffset){$out.Add($src[$sourceCursor]);$sourceCursor++}
        $newOffset=if($newCount -eq 0){$newStart}else{$newStart-1}
        Task-Assert ($out.Count -eq $newOffset) 'New hunk offset'
        $consumed=0;$produced=0;$index++;$hunks++
        while($index -lt $lines.Count -and -not $lines[$index].StartsWith('@@ ')){
            $line=$lines[$index];Task-Assert ($line.Length -ge 1) 'Nonempty diff body line'
            $prefix=$line.Substring(0,1);$content=$line.Substring(1)
            if($reverse){if($prefix -ceq '+'){$prefix='-'}elseif($prefix -ceq '-'){$prefix='+'}}
            Task-Assert ($prefix -cin @(' ','-','+')) 'Only unified content prefixes'
            if($prefix -cne '+'){
                Task-Assert ($sourceCursor -lt $src.Count -and $src[$sourceCursor] -ceq $content) 'Exact old context/removal'
                $sourceCursor++;$consumed++
            }
            if($prefix -cne '-'){$out.Add($content);$produced++}
            $index++
        }
        Task-Assert ($consumed -eq $oldCount -and $produced -eq $newCount) 'Exact unified hunk counts'
    }
    while($sourceCursor -lt $src.Count){$out.Add($src[$sourceCursor]);$sourceCursor++}
    Task-Assert ($hunks -ge 1) 'At least one change hunk'
    return (($out -join $sourceEol)+$sourceEol)
}
$pairs=@(
    @('dummy_bootstrap.py','dummy_bootstrap.py','dummy_bootstrap.diff'),
    @('generated_adapter_flow.py','generated_adapter_flow.py','generated_adapter_flow.diff'),
    @('run_interrupted_owner01.ps1','run_interrupted_owner02.ps1','run_interrupted_owner02.diff')
)
$rows=@()
foreach($pair in $pairs){
    $a=Join-Path $taskOld $pair[0];$b=Join-Path $taskNew $pair[1];$d=Join-Path $taskNew $pair[2]
    $at=[IO.File]::ReadAllText($a);$bt=[IO.File]::ReadAllText($b);$dt=[IO.File]::ReadAllText($d)
    $forward=Task-Reconstruct $at $dt $false;$reverse=Task-Reconstruct $bt $dt $true
    Task-Assert ($forward -ceq $bt -and $reverse -ceq $at) 'Full forward/reverse source reconstruction'
    $rows += [ordered]@{old_name=$pair[0];new_name=$pair[1];diff_name=$pair[2];old_sha256=(Task-Sha256 $a);new_sha256=(Task-Sha256 $b);diff_sha256=(Task-Sha256 $d);forward_complete=$true;reverse_complete=$true;valid_headers_and_hunk_counts=$true}
}
[ordered]@{scope='Passive in-memory text reconstruction only; no source application or execution';pass=$true;diffs=$rows} | ConvertTo-Json -Depth 6
