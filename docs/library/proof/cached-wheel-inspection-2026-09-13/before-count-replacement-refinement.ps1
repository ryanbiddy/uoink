param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPreparationSha256)
$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$scratch='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$output=Join-Path $scratch 'two-wheel-inspection-proof01'
function Canonical([string]$Name){if($Name -cnotmatch '^[A-Za-z0-9_./+\-]+$' -or $Name -match '(^/|(^|/)\.\.?(/|$)|//)'){throw 'Invalid relative path'}}
function Chain([string]$Path){$cursor=[IO.Path]::GetFullPath($Path);while($cursor){if(Test-Path -LiteralPath $cursor){$item=Get-Item -Force -LiteralPath $cursor;if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Reparse path'}};$parent=[IO.Directory]::GetParent($cursor);$cursor=if($null -eq $parent){$null}else{$parent.FullName}}}
function Check-File([string]$Path,$Row){Chain $Path;$file=Get-Item -LiteralPath $Path;if($file.PSIsContainer -or $file.Length -gt 4194304 -or $file.Length -ne $Row.bytes -or (Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() -cne $Row.sha256){throw ('File size/hash differs: '+$Path)}}
function Write-New([string]$Path,[byte[]]$Bytes){Chain $Path;[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))|Out-Null;$stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough);try{$stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}}
function Json-Bytes($Value){return ,([Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 15)+"`n"))}
$manifestPath=Join-Path $base 'PREPARATION-HASHES.json'
if((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedPreparationSha256){throw 'Admission manifest differs'}
$preparation=@(Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json)
foreach($row in $preparation){Canonical $row.path;Check-File (Join-Path $base $row.path) $row}
$plan=Get-Content -LiteralPath (Join-Path $base 'SOURCE-PLAN.json') -Raw|ConvertFrom-Json
if($plan.source_files -ne 72 -or @($plan.files).Count -ne 72 -or $plan.source_bytes -ne 4554492){throw 'Fixed documentary plan differs'}
$byPath=@{};$byHash=@{}
foreach($row in $plan.files){Canonical $row.path;if([IO.Path]::GetFullPath($row.source) -cne [IO.Path]::GetFullPath((Join-Path $scratch $row.path)) -or $byPath.ContainsKey($row.path) -or $row.sha256 -cnotmatch '^[0-9a-f]{64}$' -or [IO.Path]::GetExtension($row.path) -notin @('.json','.md','.py','.ps1','.txt','.log')){throw 'Source mapping scope differs'};$byPath[$row.path]=$row;$byHash[$row.sha256]=$row}
function Check-Sources {
    foreach($tree in $plan.roots){Chain $tree.source;$files=@(Get-ChildItem -LiteralPath $tree.source -File -Recurse);if($files.Count -ne $tree.files){throw 'Source tree membership differs'};foreach($file in $files){$name=[IO.Path]::GetRelativePath($scratch,$file.FullName).Replace([char]92,[char]47);if(-not $byPath.ContainsKey($name)){throw 'Extra source file'}}}
    foreach($row in $plan.files){Check-File $row.source $row}
}
Check-Sources
$preserved=@(foreach($row in $plan.files){if([IO.Path]::GetFileName($row.path) -ceq 'PREPARATION-HASHES.json'){$old=@(Get-Content -LiteralPath $row.source -Raw|ConvertFrom-Json);foreach($expected in $old){if(-not $byHash.ContainsKey($expected.sha256) -or $byHash[$expected.sha256].bytes -ne $expected.bytes){throw 'Historical preparation bytes missing'}};[ordered]@{path=$row.path;sha256=$row.sha256;members=$old.Count;all_original_payload_hashes_present=$true}}})
$old=Get-Content -LiteralPath $byPath['two-sdist-wheel-repair-plan01/inspection01.json'].source -Raw|ConvertFrom-Json
$fresh=Get-Content -LiteralPath $byPath['two-wheel-inspection02/inspection02.json'].source -Raw|ConvertFrom-Json
if($old.inspection_status -cne 'REFUSED' -or $old.exit -ne 2 -or @($old.results).Count -ne 0 -or $old.error.message -cne 'Unexpected package root'){throw 'Original refusal changed'}
if($fresh.inspection_status -cne 'VALID' -or $fresh.exit -ne 0 -or @($fresh.results).Count -ne 2 -or @($fresh.guard.violations).Count -ne 0 -or @($fresh.source_hashes_after).Count -ne 28){throw 'Final inspection differs'}
if($fresh.results[0].sha256 -cne 'd50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37' -or $fresh.results[0].record_members_verified -ne 61 -or $fresh.results[1].sha256 -cne 'a049f8572f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68' -or $fresh.results[1].record_members_verified -ne 5){throw 'Verified wheel result differs'}
foreach($wheel in $fresh.results){if($wheel.license_text_missing -ne $true -or @($wheel.requires_python).Count -ne 0 -or $wheel.script_execution_or_install_approved -ne $false){throw 'Open license/Python/script limits changed'}}
Chain $output;if(Test-Path -LiteralPath $output){throw 'Fresh proof required'}
[IO.Directory]::CreateDirectory($output)|Out-Null
foreach($row in $plan.files){Write-New (Join-Path $output ('original/'+$row.path)) ([IO.File]::ReadAllBytes($row.source));Check-File (Join-Path $output ('original/'+$row.path)) $row}
foreach($row in $preparation){Write-New (Join-Path $output $row.path) ([IO.File]::ReadAllBytes((Join-Path $base $row.path)));Check-File (Join-Path $output $row.path) $row}
Write-New (Join-Path $output 'PREPARATION-HASHES.json') ([IO.File]::ReadAllBytes($manifestPath))
Check-Sources
foreach($row in $preparation){Check-File (Join-Path $base $row.path) $row}
if((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedPreparationSha256){throw 'Preparation manifest changed'}
Write-New (Join-Path $output 'PRESERVED-PREPARATIONS.json') (Json-Bytes $preserved)
Write-New (Join-Path $output 'COPY-CHECKS.json') (Json-Bytes ([ordered]@{source_files=72;source_bytes=4554492;source_hashes_checked_before_after=$true;copies_rehashed=72;inspection01_still_refused=$true;inspection02_valid_byte_result=$true;license_text_missing_both=$true;script_execution_approved=$false;artifacts_opened_or_tests_rerun=0}))
Write-New (Join-Path $output '.gitattributes') ([Text.Encoding]::ASCII.GetBytes("* -text`n"))
$proofRows=@(Get-ChildItem -Force -LiteralPath $output -File -Recurse|Sort-Object FullName|ForEach-Object{[ordered]@{path=[IO.Path]::GetRelativePath($output,$_.FullName).Replace([char]92,[char]47);bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}})
Write-New (Join-Path $output 'SHA256.json') (Json-Bytes ([ordered]@{files=$proofRows}))
foreach($row in $proofRows){Check-File (Join-Path $output $row.path) $row}
if(@(Get-ChildItem -Force -LiteralPath $output -File -Recurse).Count -ne $proofRows.Count+1){throw 'Final membership differs'}
[ordered]@{proof=$output;payloads=$proofRows.Count;original_files=72;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $output 'SHA256.json')).Hash.ToLowerInvariant();verification='All copied hashes and exact membership verified';artifact_reads_or_reruns=0}|ConvertTo-Json
