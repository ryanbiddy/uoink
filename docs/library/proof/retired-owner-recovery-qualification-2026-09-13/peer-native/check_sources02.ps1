$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-retired-owner-recovery-proposal01'
$taskBefore='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-journal-cancel-proposal01'
function Need($ok,[string]$why){if(-not $ok){throw $why}}
function Text([string]$path){
    $item=Get-Item -LiteralPath $path
    Need (-not $item.PSIsContainer -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and $item.Length -le 131072) 'Bounded text leaf required'
    Need ([IO.Path]::GetExtension($path) -cin @('.py','.ps1','.json','.md','.diff')) 'Text extension required'
    $bytes=[IO.File]::ReadAllBytes($path)
    $text=[Text.UTF8Encoding]::new($false,$true).GetString($bytes)
    [pscustomobject]@{path=$path;bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant();text=$text}
}
function Check-Diff([string]$oldPath,[string]$newPath,[string]$diffPath){
    $old=Text $oldPath; $new=Text $newPath; $diff=Text $diffPath
    $a=@($old.text -split '\r?\n'); $b=@($new.text -split '\r?\n'); $d=@($diff.text -split '\r?\n')
    if($a[-1] -ceq ''){$a=$a[0..($a.Count-2)]}; if($b[-1] -ceq ''){$b=$b[0..($b.Count-2)]}
    if($d[-1] -ceq ''){$d=$d[0..($d.Count-2)]}
    Need ($d[0].StartsWith('--- ') -and $d[1].StartsWith('+++ ')) 'Diff header required'
    $oi=0; $ni=0; $di=2; $hunks=0
    while($di -lt $d.Count){
        Need ($d[$di] -match '^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@') 'Hunk header required'
        $oldStart=[int]$Matches[1]; $newStart=[int]$Matches[3]
        $oldCount=if($Matches[2]){[int]$Matches[2]}else{1}; $newCount=if($Matches[4]){[int]$Matches[4]}else{1}
        $ot=[Math]::Max(0,$oldStart-1); $nt=[Math]::Max(0,$newStart-1)
        while($oi -lt $ot -and $ni -lt $nt){Need ($a[$oi] -ceq $b[$ni]) 'Change outside declared hunk'; $oi++; $ni++}
        Need ($oi -eq $ot -and $ni -eq $nt) 'Hunk position differs'
        $oc=0; $nc=0; $di++; $hunks++
        while($di -lt $d.Count -and -not $d[$di].StartsWith('@@ ')){
            Need ($d[$di].Length -ge 1) 'Unprefixed diff line'
            $kind=$d[$di][0]; $value=$d[$di].Substring(1)
            if($kind -eq [char]' ' -or $kind -eq [char]'-'){Need ($oi -lt $a.Count -and $a[$oi] -ceq $value) 'Old hunk content differs'; $oi++; $oc++}
            if($kind -eq [char]' ' -or $kind -eq [char]'+'){Need ($ni -lt $b.Count -and $b[$ni] -ceq $value) 'New hunk content differs'; $ni++; $nc++}
            Need ($kind -cin @([char]' ',[char]'-',[char]'+')) 'Unexpected diff record'
            $di++
        }
        Need ($oc -eq $oldCount -and $nc -eq $newCount) 'Hunk line count differs'
    }
    while($oi -lt $a.Count -and $ni -lt $b.Count){Need ($a[$oi] -ceq $b[$ni]) 'Undeclared tail change'; $oi++; $ni++}
    Need ($oi -eq $a.Count -and $ni -eq $b.Count) 'Tail length differs'
    [ordered]@{source=[IO.Path]::GetFileName($newPath);old_sha256=$old.sha256;new_sha256=$new.sha256;diff_sha256=$diff.sha256;hunks=$hunks;complete_line_diff_matches=$true;line_ending_comparison='CR/LF separators and terminal empty slot ignored; complete file hashes retained'}
}
$mapBinding=Text (Join-Path $taskRoot 'SOURCE-INPUTS.json')
Need ($mapBinding.sha256 -ceq '9d988684ca8dfe487521f7d711ec67855393922d53ffe3cce3e13a2c660e34c3') 'Frozen native map differs'
$map=$mapBinding.text | ConvertFrom-Json
$baseline=(Text (Join-Path $taskBefore 'SOURCE-INPUTS.json')).text | ConvertFrom-Json
$names=@($map.source_sha256.PSObject.Properties.Name)
Need ($names.Count -eq 18 -and @($map.source_paths.PSObject.Properties).Count -eq 18) 'Fixed source membership differs'
Need (($names -join ',') -ceq (@($baseline.source_sha256.PSObject.Properties.Name) -join ',')) 'Baseline source membership differs'
Need (@($map.native_bindings.PSObject.Properties).Count -eq 9 -and ($map.native_bindings | ConvertTo-Json -Depth 5 -Compress) -ceq ($baseline.native_bindings | ConvertTo-Json -Depth 5 -Compress)) 'Support metadata changed'
$sources=@(); $unchanged=0
foreach($name in $names){
    Need ($name -cmatch '^[a-z0-9_]+\.py$' -and $map.source_paths.$name -ceq (Join-Path $taskRoot $name)) 'Unexpected source path'
    $row=Text (Join-Path $taskRoot $name)
    Need ($row.sha256 -ceq $map.source_sha256.$name) 'Source hash mismatch'
    $same=$row.sha256 -ceq $baseline.source_sha256.$name
    if($same){$unchanged++}
    $sources+=[ordered]@{name=$name;bytes=$row.bytes;sha256=$row.sha256;unchanged_from_cancel=$same}
}
Need ($unchanged -eq 14) 'Four changed native sources expected'
$launcher=Text (Join-Path $taskRoot 'run_retired_recovery01.ps1')
Need ($launcher.sha256 -ceq '75a9baea9307658a99217816f7653adfdbb9d0df44286a5b244ea5d3cad43444') 'Frozen launcher differs'
$diffs=@()
foreach($name in @('dummy_bootstrap.py','generated_adapter_flow.py','generated_journal_setup.py','durable_lifecycle.py')){
    $oldPath=Join-Path (Join-Path $taskRoot 'before') $name
    Need ((Text $oldPath).sha256 -ceq $baseline.source_sha256.$name) 'Before source is not baseline'
    $diffs+=Check-Diff $oldPath (Join-Path $taskRoot $name) (Join-Path $taskRoot ($name+'.diff'))
}
Need ((Text (Join-Path $taskRoot 'before\run_journal_cancel01.ps1')).sha256 -ceq (Text (Join-Path $taskBefore 'run_journal_cancel01.ps1')).sha256) 'Before launcher differs'
$diffs+=Check-Diff (Join-Path $taskRoot 'before\run_journal_cancel01.ps1') $launcher.path (Join-Path $taskRoot 'run_retired_recovery01.ps1.diff')
$templateBinding=Text (Join-Path $taskRoot 'ROOT-ADMISSION-TEMPLATE.json')
$template=$templateBinding.text | ConvertFrom-Json
Need ($template.root_reviewed -ceq $false -and $template.native_execution_admitted -ceq $false -and $template.source_inputs_sha256 -ceq $mapBinding.sha256 -and $template.launcher_sha256 -ceq $launcher.sha256) 'Dormant template differs'
foreach($row in $sources){Need ((Text (Join-Path $taskRoot $row.name)).sha256 -ceq $row.sha256) 'Source changed during check'}
Need ((Text $mapBinding.path).sha256 -ceq $mapBinding.sha256 -and (Text $launcher.path).sha256 -ceq $launcher.sha256) 'Control changed during check'
[ordered]@{schema='uoink.retired-owner-native-source-check.v1';passive_check='PASS';map_sha256=$mapBinding.sha256;launcher_sha256=$launcher.sha256;native_protocol_sha256=(Text (Join-Path $taskRoot 'NATIVE-PROTOCOL.md')).sha256;template_sha256=$templateBinding.sha256;source_count=18;unchanged_sources=14;support_metadata_rows_unchanged=9;support_paths_opened=0;native_template_false=$true;candidate_execution=$false;source_hashes_unchanged=$true;sources=$sources;complete_diffs=$diffs} | ConvertTo-Json -Depth 8
