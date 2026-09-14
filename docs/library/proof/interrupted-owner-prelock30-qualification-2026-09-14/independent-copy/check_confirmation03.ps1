$ErrorActionPreference='Stop'
$base='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$author=Join-Path $base 'interrupted-owner-prelock-fake30-author03'
$copy=Join-Path $base 'interrupted-owner-prelock-fake30-confirmation03'
$prep=Join-Path $base 'interrupted-owner-prelock-confirmation-copy03'
$oldLabel='interrupted-owner-prelock-fake03';$newLabel='prelock-retirement-confirmation03'
function H([string]$path){return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function J([string]$path){return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable)}
function Require([bool]$ok,[string]$name){if(-not $ok){throw $name}}
$authorPins=Join-Path $author 'PINS.json';$copyPins=Join-Path $copy 'PINS.json'
Require ((H $authorPins) -ceq 'f70f8f0ad7f1ad634939d91f04096996852cfe700c41829a492b00df883c1851') 'Frozen author map'
Require ((H $copyPins) -ceq '8cd78502de3f77aa5ce22e0060a19d7a7911881f63f2f389487c077ea6055e30') 'Independent map'
$a=J $authorPins;$c=J $copyPins;$relation=J (Join-Path $copy 'COPY-BINDINGS.json')
Require ($a.files.Count -eq 39 -and $c.files.Count -eq 39 -and $relation.files.Count -eq 39) '39 mapped rows'
Require ($a.schema -ceq $c.schema -and $a.finalized -ceq $true -and $c.finalized -ceq $true) 'Map metadata'
$changed=@();$childCount=0;$byteCount=0
for($i=0;$i -lt 39;$i++){
    $ar=$a.files[$i];$cr=$c.files[$i];$rr=$relation.files[$i]
    Require ($ar.path -ceq $cr.path -and $cr.path -ceq $rr.path -and $ar.status -ceq $cr.status) 'Ordered row identity/status'
    $ap=Join-Path $author $ar.path;$cp=Join-Path $copy $cr.path
    Require ((H $ap) -ceq $ar.sha256 -and (H $cp) -ceq $cr.sha256) 'Current source/copy hashes'
    Require ((Get-Item -LiteralPath $ap).Length -eq $ar.bytes -and (Get-Item -LiteralPath $cp).Length -eq $cr.bytes) 'Current source/copy sizes'
    Require ($rr.author_sha256 -ceq $ar.sha256 -and $rr.independent_sha256 -ceq $cr.sha256 -and $rr.author_bytes -eq $ar.bytes -and $rr.independent_bytes -eq $cr.bytes) 'Saved relation'
    if($ar.sha256 -cne $cr.sha256){$changed+= $cr.path}
    if($cr.path.EndsWith('.py',[StringComparison]::Ordinal) -or $cr.path -ceq 'EXPECTED-CASES.json'){
        $childCount++;Require ($ar.sha256 -ceq $cr.sha256 -and $rr.child_input -ceq $true) 'Exact child bytes'
    }
    $byteCount += $cr.bytes
}
Require ($changed.Count -eq 1 -and $changed[0] -ceq 'run_preflight01.ps1' -and $childCount -eq 36) 'Only launcher changed;36 child inputs'
$old=[IO.File]::ReadAllText((Join-Path $author 'run_preflight01.ps1'))
$new=[IO.File]::ReadAllText((Join-Path $copy 'run_preflight01.ps1'))
Require ([regex]::Matches($old,[regex]::Escape($oldLabel)).Count -eq 5 -and $old.Replace($oldLabel,$newLabel) -ceq $new -and $new.Replace($newLabel,$oldLabel) -ceq $old) 'Bidirectional five-label-only replacement'
foreach($name in @('PINS.json','run_preflight01.ps1','ROOT-ADMISSION.template.json')){Require ((H (Join-Path $prep ('before\'+$name))) -ceq (H (Join-Path $author $name))) 'Original control preservation'}
$diff=[IO.File]::ReadAllText((Join-Path $prep 'run_preflight01.ps1.diff')).Replace([string][char]13,'').Split([char]10)
Require ($diff[0] -ceq '--- before/run_preflight01.ps1' -and $diff[1] -ceq '+++ independent/run_preflight01.ps1' -and $diff[2] -cmatch '^@@ -1,[0-9]+ \+1,[0-9]+ @@$') 'Full hunk header'
$minus=@();$plus=@()
foreach($line in $diff[3..($diff.Count-2)]){if($line.StartsWith('-')){$minus+=$line.Substring(1)}elseif($line.StartsWith('+')){$plus+=$line.Substring(1)}else{throw 'Unexpected full-hunk line'}}
Require (($minus -join [char]10) -ceq $old.Replace([string][char]13,'').TrimEnd()) 'Full old text reconstruction'
Require (($plus -join [char]10) -ceq $new.Replace([string][char]13,'').TrimEnd()) 'Full new text reconstruction'
$at=J (Join-Path $author 'ROOT-ADMISSION.template.json');$ct=J (Join-Path $copy 'ROOT-ADMISSION.template.json')
Require ($at.approved -ceq $false -and $ct.approved -ceq $false -and $ct.label -ceq $newLabel -and $ct.pins_sha256 -ceq (H $copyPins)) 'False independent template'
Require ((($at.Keys | Sort-Object) -join '|') -ceq (($ct.Keys | Sort-Object) -join '|')) 'Template keys'
foreach($key in $at.Keys){if($key -cnotin @('label','pins_sha256')){Require ($at[$key] -ceq $ct[$key]) 'Other template values unchanged'}}
$expected=J (Join-Path $copy 'EXPECTED-CASES.json');$oldExpected=J (Join-Path $base 'interrupted-retirement-fake28-author01\EXPECTED-CASES.json')
Require ($expected.Count -eq 30) '30 selected IDs'
for($i=0;$i -lt 28;$i++){Require ($expected[$i] -ceq $oldExpected[$i]) 'Original28 ordered IDs'}
foreach($name in @('test_reservations.py','test_windows_reservations.py','test_journal_cancel.py','test_retired_owner_recovery.py','test_interrupted_owner_retirement.py')){Require ((H (Join-Path $copy $name)) -ceq (H (Join-Path $base ('interrupted-retirement-fake28-author01\'+$name)))) 'Five historical test files'}
$names=@($c.files.path)+@('PINS.json','ROOT-ADMISSION.template.json','COPY-BINDINGS.json','.gitattributes')
$items=@(Get-ChildItem -LiteralPath $copy -Force)
Require ($items.Count -eq 43 -and @($items | Where-Object {$_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)}).Count -eq 0) 'Exact flat43 plain-file membership'
Require ((($items.Name | Sort-Object) -join '|') -ceq (($names | Sort-Object) -join '|')) 'Exact target names; no admission/run'
Require ((H (Join-Path $prep 'COPY-BINDINGS.json')) -ceq (H (Join-Path $copy 'COPY-BINDINGS.json'))) 'Saved copy relations identical'
$meta=@()
foreach($name in @('PINS.json','ROOT-ADMISSION.template.json','run_preflight01.ps1','COPY-BINDINGS.json')){$p=Join-Path $copy $name;$meta += [ordered]@{path=$p;bytes=(Get-Item -LiteralPath $p).Length;sha256=(H $p)}}
foreach($name in @('copy_confirmation03.ps1','run_preflight01.ps1.diff','COPY03-ACTUAL.json','check_confirmation03.ps1')){$p=Join-Path $prep $name;$meta += [ordered]@{path=$p;bytes=(Get-Item -LiteralPath $p).Length;sha256=(H $p)}}
[ordered]@{scope='Passive text/control verification only; no subject execution';pass=$true;payloads=39;payload_bytes=$byteCount;exact_payloads=38;child_inputs=36;target_files=43;launcher_label_replacements=5;full_hunk_old_new_reconstruction=$true;original28_ordered_ids=$true;five_historical_tests=$true;false_template=$true;no_admission_or_run=$true;author_inputs_unchanged=$true;metadata=$meta} | ConvertTo-Json -Depth 8
