$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proposal01'
$taskBefore=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proof01'
$taskAfter=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proof02'
$taskUtf8=[System.Text.UTF8Encoding]::new($false)
if(Test-Path -LiteralPath $taskAfter){throw 'Fresh corrected proof required'}
function Get-TaskDigest($taskPath){return (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
function Write-TaskJson($taskPath,$taskValue){[System.IO.File]::WriteAllText($taskPath,($taskValue | ConvertTo-Json -Depth 30)+"`n",$taskUtf8)}
function Copy-TaskVerified($taskSource,$taskTarget,$taskExpected){
    if((Get-Item -LiteralPath $taskSource).Attributes -band [System.IO.FileAttributes]::ReparsePoint){throw 'Reparse proof source refused'}
    if((Get-TaskDigest $taskSource) -ne $taskExpected){throw 'Source digest mismatch'}
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($taskTarget)) | Out-Null
    Copy-Item -LiteralPath $taskSource -Destination $taskTarget -ErrorAction Stop
    if((Get-TaskDigest $taskTarget) -ne $taskExpected -or (Get-TaskDigest $taskSource) -ne $taskExpected){throw 'Copy or original digest changed'}
}
$taskBeforeManifest=Join-Path $taskBefore 'SHA256.json'
$taskBeforeHash=Get-TaskDigest $taskBeforeManifest
if($taskBeforeHash -ne 'd6019311cb7e62b49148cfeb40e2aafc3c38c99c0e859d9df28a03eb3179274a'){throw 'Preliminary manifest changed'}
$taskManifest=Get-Content -LiteralPath $taskBeforeManifest -Raw | ConvertFrom-Json
if($taskManifest.files.Count -ne 134 -or $taskManifest.payload_count -ne 134 -or $null -ne $taskManifest.payload_bytes){throw 'Unexpected preliminary state'}
$taskActualBefore=@(Get-ChildItem -LiteralPath $taskBefore -File -Recurse -Force)
if($taskActualBefore.Count -ne 135){throw 'Preliminary exact file set changed'}
[System.IO.Directory]::CreateDirectory($taskAfter) | Out-Null
$taskOriginalBytes=[int64]0
$taskSeen=@{}
foreach($taskEntry in $taskManifest.files){
    if($taskSeen.ContainsKey($taskEntry.path) -or $taskEntry.path.Split('/') -contains '..'){throw 'Duplicate/escaping preliminary entry'}
    $taskSeen.Add($taskEntry.path,$true)
    $taskSource=Join-Path $taskBefore $taskEntry.path
    if((Get-Item -LiteralPath $taskSource).Length -ne $taskEntry.bytes){throw 'Preliminary length changed'}
    Copy-TaskVerified $taskSource (Join-Path $taskAfter $taskEntry.path) $taskEntry.sha256
    $taskOriginalBytes += [int64]$taskEntry.bytes
}
Copy-TaskVerified $taskBeforeManifest (Join-Path $taskAfter 'preliminary-SHA256.json') $taskBeforeHash
foreach($taskName in @('SEAL-REPAIR02-BRIEF.md','seal_corrected02.ps1')){
    $taskSource=Join-Path $taskProposal $taskName
    Copy-TaskVerified $taskSource (Join-Path $taskAfter $taskName) (Get-TaskDigest $taskSource)
}
$taskFixtureInventory=Get-Content -LiteralPath (Join-Path $taskAfter 'fixture-inventory.json') -Raw | ConvertFrom-Json
$taskFixtureBytes=[int64]0
foreach($taskFixture in $taskFixtureInventory.files){$taskFixtureBytes += [int64]$taskFixture.bytes}
if($taskFixtureInventory.files.Count -ne 415 -or $taskFixtureInventory.directories.Count -ne 312){throw 'Fixture inventory changed'}
Write-TaskJson (Join-Path $taskAfter 'corrected-summary.json') ([ordered]@{date='2026-09-13';preliminary_manifest_sha256=$taskBeforeHash;preliminary_sealer_exit=0;preliminary_summary_incomplete=$true;original_payloads_copied_unchanged=134;original_payload_bytes=$taskOriginalBytes;original_file_hashes_verified=$true;fixture_files=415;fixture_directories=312;fixture_uncompressed_bytes=$taskFixtureBytes;fixture_archive_bytes=(Get-Item -LiteralPath (Join-Path $taskAfter 'generated-fixtures.zip')).Length;diagnostic_fixture_copies=40;no_rerun_or_payload_edit=$true})
$taskFinalEntries=@(Get-ChildItem -LiteralPath $taskAfter -File -Recurse -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=[System.IO.Path]::GetRelativePath($taskAfter,$_.FullName).Replace([char]92,[char]47);bytes=$_.Length;sha256=(Get-TaskDigest $_.FullName)}})
if($taskFinalEntries.Count -ne 138){throw 'Corrected payload count unexpected'}
$taskFinalBytes=[int64]0
foreach($taskEntry in $taskFinalEntries){$taskFinalBytes += [int64]$taskEntry.bytes}
Write-TaskJson (Join-Path $taskAfter 'SHA256.json') ([ordered]@{schema='uoink.documentary-payload-sha256.v1';payload_count=$taskFinalEntries.Count;payload_bytes=$taskFinalBytes;excluded_only='SHA256.json';files=$taskFinalEntries})
foreach($taskEntry in $taskFinalEntries){if((Get-TaskDigest (Join-Path $taskAfter $taskEntry.path)) -ne $taskEntry.sha256){throw 'Corrected final digest mismatch'}}
if(@(Get-ChildItem -LiteralPath $taskAfter -File -Recurse -Force).Count -ne $taskFinalEntries.Count+1){throw 'Corrected final file set mismatch'}
[ordered]@{proof=$taskAfter;payload_count=$taskFinalEntries.Count;payload_bytes=$taskFinalBytes;manifest_sha256=(Get-TaskDigest (Join-Path $taskAfter 'SHA256.json'));fixture_files=415;fixture_directories=312;fixture_uncompressed_bytes=$taskFixtureBytes;fixture_archive_bytes=(Get-Item -LiteralPath (Join-Path $taskAfter 'generated-fixtures.zip')).Length;original_payloads_unchanged=134;diagnostic_fixture_copies=40} | ConvertTo-Json
