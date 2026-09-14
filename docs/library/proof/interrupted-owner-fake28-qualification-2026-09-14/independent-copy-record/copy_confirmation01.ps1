$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskAuthor=Join-Path $taskRoot '_scratch\interrupted-retirement-fake28-author01'
$taskTarget=Join-Path $taskRoot '_scratch\astra-interrupted-retirement-confirmation01'
$taskTemplate=Join-Path $taskRoot '_scratch\interrupted-retirement-fake28-preparation01\independent-template\run_preflight01.ps1'
$taskHistorical=Join-Path $taskRoot 'docs\library\proof\retired-owner-recovery-qualification-2026-09-13\proposal'
$taskExpectedPins='eb108b71b9f2a7d10db57efb2aa92b7b8df20a25bf44923ca273f456ab753bc1'
$taskExpectedLauncher='5bab7ad46fb7d52cffe458e7e8f9d26e9aa198afd5b22047d41bc461f7f05e4f'
$taskUtf8=[Text.UTF8Encoding]::new($false)
function Digest([byte[]]$bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
function Bind([byte[]]$bytes){return [ordered]@{bytes=$bytes.Length;sha256=(Digest $bytes)}}
function Write-Fresh([string]$path,[byte[]]$bytes){
    $stream=[IO.FileStream]::new($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$stream.Write($bytes);$stream.Flush($true)}finally{$stream.Dispose()}
}
function Write-Json([string]$path,$value){Write-Fresh $path ($taskUtf8.GetBytes(($value|ConvertTo-Json -Depth 28)+[char]10))}
if(Test-Path -LiteralPath $taskTarget){throw 'Fresh independent package required'}
$pinsPath=Join-Path $taskAuthor 'PINS.json'
$pinsRaw=[IO.File]::ReadAllBytes($pinsPath)
if((Digest $pinsRaw) -cne $taskExpectedPins){throw 'Final author PINS mismatch'}
$pins=$taskUtf8.GetString($pinsRaw)|ConvertFrom-Json
if($pins.finalized -cne $true -or @($pins.files).Count -ne 38 -or @($pins.files.path|Sort-Object -Unique).Count -ne 38){throw 'Exact finalized38 map required'}
$templateRaw=[IO.File]::ReadAllBytes($taskTemplate)
if((Digest $templateRaw) -cne $taskExpectedLauncher){throw 'Reviewed independent launcher mismatch'}
$raws=@{}
$before=@()
foreach($row in $pins.files){
    if($row.path -cnotmatch '^[A-Za-z0-9_.-]+$' -or $row.status -ceq 'pending_author_freeze'){throw 'Unexpected source row'}
    $path=Join-Path $taskAuthor $row.path
    $raw=[IO.File]::ReadAllBytes($path)
    $b=Bind $raw
    if($b.sha256 -cne $row.sha256 -or $b.bytes -ne $row.bytes){throw "Author source mismatch: $($row.path)"}
    $raws[$row.path]=$raw
    $before += [ordered]@{path=$row.path;source=$path;bytes=$b.bytes;sha256=$b.sha256;status=$row.status}
}
$authorLauncher=$taskUtf8.GetString($raws['run_preflight01.ps1'])
$labelCount=$authorLauncher.Split(@('interrupted-retirement-fake01'),[StringSplitOptions]::None).Count-1
if($labelCount -ne 5){throw 'Expected exactly five fixed label changes'}
$expectedLauncher=$taskUtf8.GetBytes($authorLauncher.Replace('interrupted-retirement-fake01','interrupted-retirement-confirmation01'))
if((Digest $expectedLauncher) -cne (Digest $templateRaw) -or $expectedLauncher.Length -ne $templateRaw.Length){throw 'Independent template is not exact label-only derivative'}
$attributes=[IO.File]::ReadAllBytes((Join-Path $taskAuthor '.gitattributes'))
if($taskUtf8.GetString($attributes) -cne ('* -text'+[char]10)){throw 'Expected binary-preserving attributes'}
$authorFalsePath=Join-Path $taskAuthor 'ROOT-ADMISSION.template.json'
$authorFalseRaw=[IO.File]::ReadAllBytes($authorFalsePath)
$authorFalse=$taskUtf8.GetString($authorFalseRaw)|ConvertFrom-Json
if($authorFalse.approved -cne $false -or $authorFalse.pins_sha256 -cne $taskExpectedPins){throw 'Author false template mismatch'}
$expected=@($taskUtf8.GetString($raws['EXPECTED-CASES.json'])|ConvertFrom-Json)
$oldExpected=@(Get-Content -LiteralPath (Join-Path $taskHistorical 'EXPECTED-CASES.json') -Raw|ConvertFrom-Json)
if($expected.Count -ne 28 -or @($expected|Sort-Object -Unique).Count -ne 28 -or (($expected[0..21]|ConvertTo-Json -Compress) -cne ($oldExpected|ConvertTo-Json -Compress))){throw 'Original22 ordered IDs changed'}
$oldTestChecks=@()
foreach($name in @('test_reservations.py','test_windows_reservations.py','test_journal_cancel.py','test_retired_owner_recovery.py')){
    $oldRaw=[IO.File]::ReadAllBytes((Join-Path $taskHistorical $name))
    if((Digest $oldRaw) -cne (Digest $raws[$name]) -or $oldRaw.Length -ne $raws[$name].Length){throw 'Historical test bytes differ'}
    $oldTestChecks += [ordered]@{path=$name;historical_sha256=(Digest $oldRaw);author_sha256=(Digest $raws[$name]);unchanged=$true}
}
$childNames=@($pins.files.path|Where-Object {$_ -cnotin @('run_preflight01.ps1','QUALIFICATION-PROTOCOL.md','BRIEF.md')})
if($childNames.Count -ne 35){throw 'Exact35 child inputs required'}
New-Item -ItemType Directory -Path $taskTarget -ErrorAction Stop|Out-Null
$relations=@()
$destinationRows=@()
foreach($row in $pins.files){
    $out=if($row.path -ceq 'run_preflight01.ps1'){$templateRaw}else{$raws[$row.path]}
    $path=Join-Path $taskTarget $row.path
    Write-Fresh $path $out
    $copy=Bind ([IO.File]::ReadAllBytes($path))
    if($copy.sha256 -cne (Digest $out) -or $copy.bytes -ne $out.Length){throw 'Copy verification failed'}
    $same=$copy.sha256 -ceq $row.sha256 -and $copy.bytes -eq $row.bytes
    if(($row.path -cne 'run_preflight01.ps1') -and -not $same){throw 'Unexpected payload difference'}
    $relations += [ordered]@{path=$row.path;author_path=(Join-Path $taskAuthor $row.path);independent_path=$path;author=[ordered]@{bytes=$row.bytes;sha256=$row.sha256};independent=$copy;relation=$(if($same){'exact_bytes'}else{'five_fixed_label_replacements'});child_input=($row.path -cin $childNames)}
    $destinationRows += [ordered]@{path=$row.path;bytes=$copy.bytes;sha256=$copy.sha256;status=$row.status}
}
$destinationPins=[ordered]@{schema=$pins.schema;finalized=$true;files=$destinationRows}
Write-Json (Join-Path $taskTarget 'PINS.json') $destinationPins
$destinationPinsBinding=Bind ([IO.File]::ReadAllBytes((Join-Path $taskTarget 'PINS.json')))
Write-Json (Join-Path $taskTarget 'ROOT-ADMISSION.template.json') ([ordered]@{
    approved=$false;label='interrupted-retirement-confirmation01';pins_sha256=$destinationPinsBinding.sha256;
    scope='generated_bytes_and_fake_ports_only';note='Independent package only; root source review and separate actual admission required.'})
Write-Fresh (Join-Path $taskTarget '.gitattributes') $attributes
$after=@()
foreach($row in $before){
    $b=Bind ([IO.File]::ReadAllBytes($row.source))
    if($b.bytes -ne $row.bytes -or $b.sha256 -cne $row.sha256){throw 'Author changed during materialization'}
    $after += [ordered]@{path=$row.path;bytes=$b.bytes;sha256=$b.sha256;unchanged=$true}
}
if((Digest ([IO.File]::ReadAllBytes($pinsPath))) -cne $taskExpectedPins -or
   (Digest ([IO.File]::ReadAllBytes($taskTemplate))) -cne $taskExpectedLauncher -or
   (Digest ([IO.File]::ReadAllBytes($authorFalsePath))) -cne (Digest $authorFalseRaw) -or
   (Digest ([IO.File]::ReadAllBytes((Join-Path $taskAuthor '.gitattributes')))) -cne (Digest $attributes)){throw 'Control changed during materialization'}
if(Test-Path -LiteralPath (Join-Path $taskTarget 'ROOT-ADMISSION.json')){throw 'Actual admission must remain absent'}
if(Test-Path -LiteralPath (Join-Path $taskTarget 'interrupted-retirement-confirmation01')){throw 'Run directory must remain absent'}
$report=[ordered]@{
    schema='uoink.interrupted-retirement-independent-copy.v1';scope='text materialization only; no Python/candidate/test/native execution';
    author_pins=(Bind $pinsRaw);independent_pins=$destinationPinsBinding;
    reviewed_launcher=(Bind $templateRaw);payload_count=38;exact_payloads=37;label_only_payloads=1;child_inputs=35;
    relations=$relations;author_after=$after;all_author_inputs_unchanged=$true;all35_child_bytes_identical=$true;
    original22_order_unchanged=$true;original_four_tests=$oldTestChecks;
    label_replacements=5;admission_approved=$false;actual_admission_absent=$true;run_directory_absent=$true
}
Write-Json (Join-Path $taskTarget 'COPY-BINDINGS.json') $report
Write-Json (Join-Path $PSScriptRoot 'COPY-RESULT.json') ([ordered]@{
    target=$taskTarget;payloads=38;child_inputs=35;independent_pins=$destinationPinsBinding;
    launcher=(Bind $templateRaw);template=(Bind ([IO.File]::ReadAllBytes((Join-Path $taskTarget 'ROOT-ADMISSION.template.json'))));
    copy_bindings=(Bind ([IO.File]::ReadAllBytes((Join-Path $taskTarget 'COPY-BINDINGS.json'))));
    actual_admission_absent=$true;run_directory_absent=$true;candidate_executed=$false})
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'COPY-RESULT.json') -Raw

