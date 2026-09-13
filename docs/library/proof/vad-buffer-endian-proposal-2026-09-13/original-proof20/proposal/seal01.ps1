param([Parameter(Mandatory=$true)][string]$ReviewPath,[Parameter(Mandatory=$true)][string]$ReviewSha256)
$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-buffer-endian-proposal01'
$taskProof=Join-Path $taskBase '_scratch\vad-buffer-endian-final-proof01'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh proof required'}
$taskExpected=@{'buffer_basis.py'='bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373';'qualify_basis.py'='fe0e3e5559ecc237bf6d7af4b8f38a4d68d557daa574e4470058c2f2b2fa7aa3'}
foreach($taskName in $taskExpected.Keys){if((Get-FileHash -LiteralPath (Join-Path $taskProposal $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected[$taskName]){throw 'Source changed'}}
$taskReview=Join-Path $taskBase $ReviewPath
if((Get-FileHash -LiteralPath $taskReview -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ReviewSha256){throw 'Review mismatch'}
$taskResult=Get-Content -Raw -LiteralPath (Join-Path $taskProposal 'buffer-preflight01\stdout.json') | ConvertFrom-Json
$taskExit=Get-Content -Raw -LiteralPath (Join-Path $taskProposal 'buffer-preflight01\exit.json') | ConvertFrom-Json
if($taskResult.passed -ne 37 -or $taskResult.failed -ne 0 -or $taskResult.qualification_exit -ne 0 -or @($taskResult.cases).Count -ne 37 -or @($taskResult.cases.case | Sort-Object -Unique).Count -ne 37 -or @($taskResult.cases | Where-Object {-not $_.passed}).Count -ne 0 -or @($taskResult.unexpected_audit_events).Count -ne 0 -or $taskExit.native_exit -ne 0 -or -not $taskExit.inputs_unchanged -or -not $taskExit.startup_binding_set -or (Get-Item -LiteralPath (Join-Path $taskProposal 'buffer-preflight01\stderr.log')).Length -ne 0){throw 'Qualification mismatch'}
New-Item -ItemType Directory -Path $taskProof -ErrorAction Stop | Out-Null
function Copy-Exact([string]$source,[string]$relative){
 $taskItem=Get-Item -LiteralPath $source -ErrorAction Stop
 if($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Non-plain file'}
 $taskDestination=Join-Path $taskProof $relative
 New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($taskDestination)) -Force | Out-Null
 $taskBefore=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
 Copy-Item -LiteralPath $source -Destination $taskDestination -ErrorAction Stop
 if((Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore -or (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore){throw 'Copy changed'}
}
foreach($taskFile in Get-ChildItem -LiteralPath $taskProposal -Recurse -File -Force){Copy-Exact $taskFile.FullName ('proposal\'+$taskFile.FullName.Substring($taskProposal.Length+1))}
Copy-Exact $taskReview 'review\FINAL-REVIEW.md'
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=$_.FullName.Substring($taskProof.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{scope='Generated-buffer consistency proposal; historical accuracy unproven; no actual storage read or real profile';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'SHA256.json') -Encoding utf8
$taskActual=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | ForEach-Object {$_.FullName.Substring($taskProof.Length+1).Replace('\','/')})
if(Compare-Object ($taskActual | Sort-Object) (@($taskRecords.path)+@('SHA256.json') | Sort-Object)){throw 'Full file-set mismatch'}
foreach($taskRecord in $taskRecords){$taskPath=Join-Path $taskProof $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Payload mismatch'}}
[ordered]@{payload_count=$taskRecords.Count;actual_total_files=$taskActual.Count;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant();exact_file_set_verified=$true;all_payloads_verified=$true;synthetic_passed=37;failed=0;actual_storage_read=$false;real_profile_approved=$false} | ConvertTo-Json
