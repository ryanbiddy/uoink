$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Assert-Task($condition,[string]$message) { if(-not $condition){throw $message} }
function Hash-Bytes([byte[]]$bytes) { [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant() }
function Read-Text([string]$path) {
    $bytes=[IO.File]::ReadAllBytes($path)
    $text=[Text.UTF8Encoding]::new($false,$true).GetString($bytes)
    Assert-Task ([Convert]::ToBase64String($bytes) -ceq [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($text))) 'Exact UTF8 round trip required'
    [ordered]@{path=$path;bytes=$bytes.Length;sha256=(Hash-Bytes $bytes);text=$text}
}
function Apply-Delta([string]$before,[string]$patch,[bool]$reverse) {
    Assert-Task (-not $before.Contains([char]13) -and ($before.Length -eq 0 -or $before.EndsWith([string][char]10))) 'Exact LF source required'
    $old=if($before.Length -eq 0){@()}else{$before.Substring(0,$before.Length-1).Split([char]10)}
    $lines=$patch.TrimEnd([char]10).Split([char]10)
    $i=0
    while($i -lt $lines.Length -and -not $lines[$i].StartsWith('--- ')) {
        Assert-Task ($lines[$i] -match '^(diff --git |index |new file mode )') 'Known mechanical Git header required'
        $i++
    }
    Assert-Task ($i+1 -lt $lines.Length -and $lines[$i].StartsWith('--- ') -and $lines[$i+1].StartsWith('+++ ')) 'Separate file headers required'
    $i+=2
    $out=[Collections.Generic.List[string]]::new()
    $at=0
    while($i -lt $lines.Length) {
        Assert-Task ($lines[$i] -cmatch '^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(?: .*)?$') 'Valid hunk header required'
        $oldStart=[int]$Matches[1];$newStart=[int]$Matches[3]
        $wantOld=if($Matches.ContainsKey(2)){[int]$Matches[2]}else{1}
        $wantNew=if($Matches.ContainsKey(4)){[int]$Matches[4]}else{1}
        if($reverse){$swap=$oldStart;$oldStart=$newStart;$newStart=$swap;$swap=$wantOld;$wantOld=$wantNew;$wantNew=$swap}
        $start=if($wantOld -eq 0){$oldStart}else{$oldStart-1}
        Assert-Task ($start -ge $at -and $start -le $old.Length) 'Ordered hunk required'
        while($at -lt $start){$out.Add($old[$at]);$at++}
        $i++;$gotOld=0;$gotNew=0
        while($i -lt $lines.Length -and -not $lines[$i].StartsWith('@@ ')) {
            Assert-Task ($lines[$i].Length -ge 1) 'Prefixed hunk body required'
            $tag=$lines[$i].Substring(0,1);$body=$lines[$i].Substring(1)
            if($reverse){if($tag -ceq '+'){$tag='-'}elseif($tag -ceq '-'){$tag='+'}}
            Assert-Task ($tag -cin @(' ','+','-')) 'Known hunk prefix required'
            if($tag -cne '+'){Assert-Task ($at -lt $old.Length -and $old[$at] -ceq $body) 'Exact source context required';$at++;$gotOld++}
            if($tag -cne '-'){$out.Add($body);$gotNew++}
            $i++
        }
        Assert-Task ($gotOld -eq $wantOld -and $gotNew -eq $wantNew) 'Exact hunk counts required'
    }
    while($at -lt $old.Length){$out.Add($old[$at]);$at++}
    if($out.Count -eq 0){return ''}
    return [string]::Join([string][char]10,$out)+[char]10
}
$root=$PSScriptRoot
$utf8=[Text.UTF8Encoding]::new($false)
[IO.Directory]::CreateDirectory($root+'/reconstructed')|Out-Null
$relations=@(foreach($name in @('controller_boundary_fixture.py','test_controller_resume_publication.py')) {
    $old=Read-Text ($root+'/before/'+$name)
    $now=Read-Text ($root+'/'+$name)
    $patch=Read-Text ($root+'/'+$name.Replace('.py','.diff'))
    $added=Read-Text ($root+'/'+$name+'.new.diff')
    $forward=Apply-Delta $old.text $patch.text $false
    $reverse=Apply-Delta $now.text $patch.text $true
    Assert-Task ($forward -ceq $now.text -and $reverse -ceq $old.text) 'Full repair reconstruction mismatch'
    Assert-Task ((Apply-Delta '' $added.text $false) -ceq $now.text) 'New-file reconstruction mismatch'
    Assert-Task ((Apply-Delta $now.text $added.text $true) -ceq '') 'New-file reverse reconstruction mismatch'
    foreach($row in @(@('forward',$forward),@('reverse',$reverse))) {
        $path=$root+'/reconstructed/'+$name+'.'+$row[0]+'.txt'
        Assert-Task (-not [IO.File]::Exists($path)) 'Fresh reconstruction path required'
        [IO.File]::WriteAllText($path,$row[1],$utf8)
    }
    [ordered]@{name=$name;before_bytes=$old.bytes;before_sha256=$old.sha256;after_bytes=$now.bytes;after_sha256=$now.sha256;diff_sha256=$patch.sha256;new_file_diff_sha256=$added.sha256;forward_equal=$true;reverse_equal=$true;new_file_forward_reverse_equal=$true}
})
$tests=Read-Text ($root+'/test_controller_resume_publication.py')
$expected=@([IO.File]::ReadAllText($root+'/EXPECTED-CASES.json')|ConvertFrom-Json)
$names=@([regex]::Matches($tests.text,'(?m)^    def (test_[a-z0-9_]+)\(self\):')|ForEach-Object {'test_controller_resume_publication.ControllerBoundaryContracts.'+$_.Groups[1].Value})
Assert-Task ($names.Count -eq 10 -and $expected.Count -eq 10) 'Ten exact case IDs required'
for($i=0;$i -lt 10;$i++){Assert-Task ($names[$i] -ceq $expected[$i]) 'Expected source order differs'}
[ordered]@{scope='Passive source-text and raw mechanical patch verification only';candidate_executions=0;git_diff_exit1_means_differences=$true;relations=$relations;ordered_cases=$names}|ConvertTo-Json -Depth 6

