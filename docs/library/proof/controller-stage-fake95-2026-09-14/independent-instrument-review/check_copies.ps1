$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskRepo '_scratch\controller-stage-qualification-proposal01'
function Assert-Copy([bool]$ok,[string]$why){if(-not $ok){throw $why}}
function Read-Copy([string]$path){$f=Get-Item -LiteralPath $path; Assert-Copy (-not $f.PSIsContainer -and ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and $f.Length -le 1048576) $path;return [IO.File]::ReadAllText($f.FullName)}
function Hash-Copy([string]$path){$null=Read-Copy $path;return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
$taskPins=(Read-Copy (Join-Path $taskProposal 'PINS.json'))|ConvertFrom-Json
$taskLaunch=Read-Copy (Join-Path $taskProposal 'run_preflight01.ps1')
$taskRelation=Read-Copy (Join-Path $taskRepo '_scratch\CONTROLLER95-COPY-RELATION.json')
$taskRows=@()
foreach($spec in @(
  @{folder='controller-stage-fake95-author01';label='controller-stage-fake01';pins='b831bf6c864d8a7bef24355e5868dfa7480e6bba6ff1381cbc3ac9db07388606';launch='b71b436882df599c0650220383ed338f745345e19ca4217c9be1fe18eacf8930'},
  @{folder='controller-stage-fake95-confirmation01';label='controller-stage-confirmation01';pins='6fdc1188f323541aaff93a3fb5205f54e395b13d5b20ebf8a95bd69420e864cb';launch='acf6025208f28439da704cd70ec682471c7344012af6f61fa639ccc3583a9b8f'}
)){
  $root=Join-Path $taskRepo ('_scratch\'+$spec.folder)
  $pinPath=Join-Path $root 'PINS.json'
  Assert-Copy ((Hash-Copy $pinPath) -ceq $spec.pins) 'exact copy pins'
  $pins=(Read-Copy $pinPath)|ConvertFrom-Json
  Assert-Copy ($pins.count -eq 29 -and $pins.files.Count -eq 29) '29 copied inputs'
  $changed=@()
  for($i=0;$i -lt 29;$i++){
    $r=$pins.files[$i];$old=$taskPins.files[$i];$path=Join-Path $root $r.path
    Assert-Copy ($r.path -ceq $old.path) 'same ordered input names'
    Assert-Copy ((Hash-Copy $path) -ceq $r.sha256 -and (Get-Item -LiteralPath $path).Length -eq $r.bytes) 'current copy bytes'
    if($r.sha256 -cne $old.sha256 -or $r.bytes -ne $old.bytes){$changed+=,$r.path}
  }
  if($spec.label -ceq 'controller-stage-fake01'){Assert-Copy ($changed.Count -eq 0) 'author all29 exact'}
  else{Assert-Copy ($changed.Count -eq 1 -and $changed[0] -ceq 'run_preflight01.ps1') 'only confirmation launcher row changes'}
  $launchPath=Join-Path $root 'run_preflight01.ps1'
  Assert-Copy ((Hash-Copy $launchPath) -ceq $spec.launch) 'copy launcher exact hash'
  $literalCount=[regex]::Matches($taskLaunch,[regex]::Escape('controller-stage-fake01')).Count
  Assert-Copy ($literalCount -eq 5) 'five original label literals'
  Assert-Copy ((Read-Copy $launchPath) -ceq $taskLaunch.Replace('controller-stage-fake01',$spec.label)) 'only fixed label substitutions'
  $templatePath=Join-Path $root 'ROOT-ADMISSION.template.json'
  $template=(Read-Copy $templatePath)|ConvertFrom-Json
  Assert-Copy ($template.approved -eq $false -and $template.label -ceq $spec.label -and $template.pins_sha256 -ceq $spec.pins -and $template.scope -ceq 'generated_bytes_and_fake_ports_only' -and $template.case_count -eq 95) 'exact false template'
  $expected=@($pins.files.path)+@('PINS.json','ROOT-ADMISSION.template.json')
  $actual=@(Get-ChildItem -LiteralPath $root -Force)
  Assert-Copy ($actual.Count -eq 31 -and @($actual|Where-Object PSIsContainer).Count -eq 0) '31 fixed source/control files; no run'
  Assert-Copy ((($actual.Name|Sort-Object)-join '|') -ceq (($expected|Sort-Object)-join '|')) 'exact membership; no actual admission'
  $taskRows+=[ordered]@{directory=$spec.folder;label=$spec.label;pins_sha256=$spec.pins;launcher_sha256=$spec.launch;all29_pins_valid=$true;child25_unchanged=$true;changed_parent_rows=$changed;label_literal_count=$literalCount;false_template_sha256=(Hash-Copy $templatePath);actual_admission_absent=$true;run_absent=$true}
}
function Capture-Names([string]$text){
  $start=$text.IndexOf('            STARTUP_FUNCTIONS = tuple(');$end=$text.IndexOf(') for method in methods)',$start)
  Assert-Copy ($start -ge 0 -and $end -gt $start) 'capture region'
  return @([regex]::Matches($text.Substring($start,$end-$start),'"(_?[A-Za-z][A-Za-z0-9_]*)"')|ForEach-Object{$_.Groups[1].Value}|Where-Object{$_ -notin @('trusted_asr_resolver','startup_fixture_resolver','asr_loading_adapter','startup_fixture_adapter')})
}
$oldNames=@(Capture-Names (Read-Copy (Join-Path $taskProposal 'before\qualify_windows_reservations.py')))
$newNames=@(Capture-Names (Read-Copy (Join-Path $taskProposal 'qualify_windows_reservations.py')))
Assert-Copy ($oldNames.Count -eq 36 -and $newNames.Count -eq 38 -and (($oldNames -join '|') -ceq ($newNames[0..35] -join '|'))) '36 exact capture prefix'
[ordered]@{result='PASS';scope='Passive fixed source/control comparison; no subject execution';relation_text=$taskRelation;copies=$taskRows;original36_captured_functions_preserved=$true}|ConvertTo-Json -Depth 10

