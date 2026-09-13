$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOriginal=Join-Path $taskBase '_scratch\vad-fixed-converter-final-proof01'
$taskRepair=Join-Path $taskBase '_scratch\vad-fixed-converter-proof-repair02'
$taskProof=Join-Path $taskBase '_scratch\vad-fixed-converter-final-proof02'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh proof02 destination required'}
$taskManifest=Join-Path $taskOriginal 'SHA256.json'
if((Get-FileHash -LiteralPath $taskManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f2993a14b2fb47737b77e1d5444a664cdd52b15631a20400a5c21e06d70b3b30'){throw 'Original seal mismatch'}
$taskPrior=Get-Content -Raw -LiteralPath $taskManifest | ConvertFrom-Json
if($taskPrior.payload_count -ne 75 -or @($taskPrior.records).Count -ne 75){throw 'Original count mismatch'}
foreach($taskRecord in $taskPrior.records){$taskPath=Join-Path $taskOriginal $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Original payload mismatch'}}
$taskOriginalFiles=@(Get-ChildItem -LiteralPath $taskOriginal -Recurse -File -Force)
if($taskOriginalFiles.Count -ne 77){throw 'Original complete file count mismatch'}
$taskExpectedOriginal=@($taskPrior.records.path)+@('SHA256.json','VERIFICATION.json')
$taskActualOriginal=@($taskOriginalFiles | ForEach-Object {$_.FullName.Substring($taskOriginal.Length+1).Replace('\','/')})
if(Compare-Object ($taskExpectedOriginal | Sort-Object) ($taskActualOriginal | Sort-Object)){throw 'Unexpected original file set'}
New-Item -ItemType Directory -Path $taskProof -ErrorAction Stop | Out-Null
function Copy-Exact([string]$source,[string]$relative){
 $taskItem=Get-Item -LiteralPath $source -ErrorAction Stop
 if($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Non-plain payload'}
 $taskDestination=Join-Path $taskProof $relative
 New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($taskDestination)) -Force | Out-Null
 $taskBefore=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
 Copy-Item -LiteralPath $source -Destination $taskDestination -ErrorAction Stop
 if((Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore -or (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore){throw 'Copy mismatch'}
}
foreach($taskFile in $taskOriginalFiles){Copy-Exact $taskFile.FullName ('original-proof01\'+$taskFile.FullName.Substring($taskOriginal.Length+1))}
foreach($taskName in @('BRIEF.md','SCOPE.md','seal02.ps1')){Copy-Exact (Join-Path $taskRepair $taskName) ('repair\'+$taskName)}
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=$_.FullName.Substring($taskProof.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{scope='Complete-set documentary seal repair; converter source and results unchanged';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'SHA256.json') -Encoding utf8
$taskActual=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | ForEach-Object {$_.FullName.Substring($taskProof.Length+1).Replace('\','/')})
$taskExpected=@($taskRecords.path)+@('SHA256.json')
if(Compare-Object ($taskActual | Sort-Object) ($taskExpected | Sort-Object)){throw 'Final full-set mismatch'}
foreach($taskRecord in $taskRecords){$taskPath=Join-Path $taskProof $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Final payload mismatch'}}
[ordered]@{payload_count=$taskRecords.Count;actual_total_files=$taskActual.Count;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant();exact_file_set_verified=$true;all_payload_bytes_verified=$true;original75_preserved=$true;omitted_original_verification_included=$true;no_test_rerun=$true} | ConvertTo-Json
