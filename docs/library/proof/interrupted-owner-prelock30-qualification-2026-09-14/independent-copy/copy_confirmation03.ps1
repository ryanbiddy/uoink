param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$AuthorPinsSha256)
$ErrorActionPreference='Stop'
$author='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-owner-prelock-fake30-author03'
$destination='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-owner-prelock-fake30-confirmation03'
$preparation='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-owner-prelock-confirmation-copy03'
$oldLabel='interrupted-owner-prelock-fake03'
$newLabel='prelock-retirement-confirmation03'
$utf8=[Text.UTF8Encoding]::new($false)
function Hash([byte[]]$bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
function Read-Plain([string]$path){
    $item=Get-Item -LiteralPath $path
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576){throw 'Bounded plain text required'}
    return ,([IO.File]::ReadAllBytes($path))
}
function Write-New([string]$path,[byte[]]$bytes){
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
function Json-Bytes($value){return ,($utf8.GetBytes(($value | ConvertTo-Json -Depth 20)+[char]10))}
if(Test-Path -LiteralPath $destination){throw 'Fresh independent preparation required'}
$pinsBytes=Read-Plain (Join-Path $author 'PINS.json')
if((Hash $pinsBytes) -cne $AuthorPinsSha256){throw 'Final author map binding'}
$pins=$utf8.GetString($pinsBytes) | ConvertFrom-Json -AsHashtable
if($pins['finalized'] -cne $true -or @($pins['files']).Count -ne 39){throw 'Final39 map required'}
$raw=@{};$relation=@()
foreach($row in $pins['files']){
    $name=$row['path']
    if($name -cnotmatch '^[A-Za-z0-9_.-]+\.(py|ps1|json|md)$' -or $raw.ContainsKey($name) -or $name -ceq 'ROOT-ADMISSION.json' -or $row['status'] -ceq 'pending_author_freeze'){throw 'Exact flat payload membership'}
    $bytes=Read-Plain (Join-Path $author $name)
    if($bytes.Length -ne $row['bytes'] -or (Hash $bytes) -cne $row['sha256']){throw 'Author payload differs'}
    $raw[$name]=$bytes
}
$templateBytes=Read-Plain (Join-Path $author 'ROOT-ADMISSION.template.json')
$template=$utf8.GetString($templateBytes) | ConvertFrom-Json -AsHashtable
if($template['approved'] -cne $false -or $template['label'] -cne $oldLabel -or $template['pins_sha256'] -cne $AuthorPinsSha256){throw 'False author template binding'}
$oldLauncher=$utf8.GetString($raw['run_preflight01.ps1'])
if([regex]::Matches($oldLauncher,[regex]::Escape($oldLabel)).Count -ne 5){throw 'Exact five launcher substitutions'}
$newLauncher=$oldLauncher.Replace($oldLabel,$newLabel)
$childNames=@($raw.Keys | Where-Object {$_ -clike '*.py'}) + @('EXPECTED-CASES.json')
if($childNames.Count -ne 36){throw 'Exact36 child membership'}
$expected=$utf8.GetString($raw['EXPECTED-CASES.json']) | ConvertFrom-Json
if(@($expected).Count -ne 30 -or @($expected | Sort-Object -Unique).Count -ne 30){throw 'Expected30 IDs'}
$oldExpectedBytes=Read-Plain 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-retirement-fake28-author01\EXPECTED-CASES.json'
if((Hash $oldExpectedBytes) -cne '226ac87eb7d0167312ebc0b77cddd13b8354d2f1624ad8555a3dbae27b1f7f39'){throw 'Original28 list binding'}
$oldExpected=$utf8.GetString($oldExpectedBytes) | ConvertFrom-Json
for($i=0;$i -lt 28;$i++){if($expected[$i] -cne $oldExpected[$i]){throw 'Original28 ordered IDs'}}
$oldTests=@{
'test_reservations.py'='604a295d5e925b9a9d7f55750bfeb1ddcda3e6a9873d6d8d7f9e98c84d9b4b9e'
'test_windows_reservations.py'='91b0de71eb55d088ee2fdbcd11ff3e6a074f18f713dfcd5b384814a1dc78300c'
'test_journal_cancel.py'='b02f35091e45af10380d725de77fc84e1f3e4c42f8bd163e41c78222b4aa6b31'
'test_retired_owner_recovery.py'='1da9c5f8eefdad3ae4f2b22d8b632b242a2cb27296bbec6e6dd96c24da687f0c'
'test_interrupted_owner_retirement.py'='c833cf67e5534c8a0c57e27ae6fec5cb8f6d2c68e8db6844ef7b47075998a2d0'
}
foreach($name in $oldTests.Keys){if((Hash $raw[$name]) -cne $oldTests[$name]){throw 'Inherited test source changed'}}
$beforeDir=Join-Path $preparation 'before'
if(Test-Path -LiteralPath $beforeDir){throw 'Fresh before preservation required'}
New-Item -ItemType Directory -Path $beforeDir -ErrorAction Stop | Out-Null
Write-New (Join-Path $beforeDir 'PINS.json') $pinsBytes
Write-New (Join-Path $beforeDir 'run_preflight01.ps1') $raw['run_preflight01.ps1']
Write-New (Join-Path $beforeDir 'ROOT-ADMISSION.template.json') $templateBytes
New-Item -ItemType Directory -Path $destination -ErrorAction Stop | Out-Null
foreach($row in $pins['files']){
    $name=$row['path'];$bytes=$raw[$name]
    if($name -ceq 'run_preflight01.ps1'){$bytes=$utf8.GetBytes($newLauncher)}
    Write-New (Join-Path $destination $name) $bytes
    $relation += [ordered]@{path=$name;author_path=(Join-Path $author $name);independent_path=(Join-Path $destination $name);author_bytes=$raw[$name].Length;author_sha256=(Hash $raw[$name]);independent_bytes=$bytes.Length;independent_sha256=(Hash $bytes);change=$(if($name -ceq 'run_preflight01.ps1'){'five_fixed_label_substitutions'}else{'byte_identical'});child_input=($name -cin $childNames)}
    $row['bytes']=$bytes.Length;$row['sha256']=Hash $bytes
}
$newPinsBytes=Json-Bytes $pins;$newPinsHash=Hash $newPinsBytes
Write-New (Join-Path $destination 'PINS.json') $newPinsBytes
$template['approved']=$false;$template['label']=$newLabel;$template['pins_sha256']=$newPinsHash
Write-New (Join-Path $destination 'ROOT-ADMISSION.template.json') (Json-Bytes $template)
Write-New (Join-Path $destination '.gitattributes') ($utf8.GetBytes('* -text'+[char]10))
foreach($row in $relation){
    $copy=Read-Plain $row['independent_path'];$source=Read-Plain $row['author_path']
    if((Hash $copy) -cne $row['independent_sha256'] -or $copy.Length -ne $row['independent_bytes'] -or (Hash $source) -cne $row['author_sha256'] -or $source.Length -ne $row['author_bytes']){throw 'Source/copy after binding'}
    if($row['child_input'] -and (Hash $copy) -cne (Hash $source)){throw 'Child input changed'}
}
if((Hash (Read-Plain (Join-Path $author 'PINS.json'))) -cne $AuthorPinsSha256 -or (Hash (Read-Plain (Join-Path $author 'ROOT-ADMISSION.template.json'))) -cne (Hash $templateBytes)){throw 'Author control changed'}
if(Test-Path -LiteralPath (Join-Path $destination 'ROOT-ADMISSION.json')){throw 'No independent admission authorized'}
if(Test-Path -LiteralPath (Join-Path $destination $newLabel)){throw 'No independent run authorized'}
$report=[ordered]@{scope='Independent preparation only; zero candidate invocations';author=$author;destination=$destination;author_pins_sha256=$AuthorPinsSha256;independent_pins_sha256=$newPinsHash;payloads=39;exact_payloads=38;child_inputs=36;child_inputs_byte_identical=$true;original28_ordered_ids_unchanged=$true;five_old_test_files_unchanged=$true;false_template_only=$true;run_absent=$true;all30_ordered_ids=$expected;files=$relation}
Write-New (Join-Path $destination 'COPY-BINDINGS.json') (Json-Bytes $report)
Write-New (Join-Path $preparation 'COPY-BINDINGS.json') (Json-Bytes $report)
$lf=[string][char]10
$oldLines=@($oldLauncher.Replace([string][char]13,'').TrimEnd().Split([char]10))
$newLines=@($newLauncher.Replace([string][char]13,'').TrimEnd().Split([char]10))
$diff='--- before/run_preflight01.ps1'+$lf+'+++ independent/run_preflight01.ps1'+$lf+'@@ -1,'+$oldLines.Count+' +1,'+$newLines.Count+' @@'+$lf+(($oldLines | ForEach-Object {'-'+$_}) -join $lf)+$lf+(($newLines | ForEach-Object {'+'+$_}) -join $lf)+$lf
Write-New (Join-Path $preparation 'run_preflight01.ps1.diff') ($utf8.GetBytes($diff))
$report | ConvertTo-Json -Depth 12
