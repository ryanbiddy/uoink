$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOriginal=Join-Path $taskBase '_scratch\vad-buffer-endian-final-proof01'
$taskRoot=Join-Path $taskBase '_scratch\astra-buffer-basis-synthetic01'
$taskPreparation=Join-Path $taskBase '_scratch\vad-buffer-endian-combined-proof02-preparation'
$taskProof=Join-Path $taskBase '_scratch\vad-buffer-endian-final-proof02'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh final proof destination required'}
$taskOriginalManifest=Join-Path $taskOriginal 'SHA256.json'
if((Get-FileHash -LiteralPath $taskOriginalManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne '581fa57387fa06cf38822000aa8f2fb5d5e7da8a3a6307200283c365faa75bd0'){throw 'Original seal mismatch'}
$taskPrior=Get-Content -Raw -LiteralPath $taskOriginalManifest | ConvertFrom-Json
if($taskPrior.payload_count -ne 20 -or @($taskPrior.records).Count -ne 20){throw 'Original payload count mismatch'}
foreach($taskRecord in $taskPrior.records){$taskPath=Join-Path $taskOriginal $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Original payload mismatch'}}
$taskOriginalFiles=@(Get-ChildItem -LiteralPath $taskOriginal -Recurse -File -Force)
$taskOriginalNames=@($taskOriginalFiles | ForEach-Object {$_.FullName.Substring($taskOriginal.Length+1).Replace('\','/')})
if(Compare-Object ($taskOriginalNames | Sort-Object) (@($taskPrior.records.path)+@('SHA256.json') | Sort-Object)){throw 'Original exact file-set mismatch'}
$taskAuthorDir=Join-Path $taskOriginal 'proposal\buffer-preflight01'
$taskAuthor=Get-Content -Raw -LiteralPath (Join-Path $taskAuthorDir 'stdout.json') | ConvertFrom-Json
$taskIndependent=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'stdout.json') | ConvertFrom-Json
foreach($taskResult in @($taskAuthor,$taskIndependent)){
 if($taskResult.passed -ne 37 -or $taskResult.failed -ne 0 -or $taskResult.qualification_exit -ne 0 -or @($taskResult.cases).Count -ne 37 -or @($taskResult.cases.case | Sort-Object -Unique).Count -ne 37 -or @($taskResult.cases | Where-Object {-not $_.passed}).Count -ne 0 -or @($taskResult.unexpected_audit_events).Count -ne 0 -or -not $taskResult.startup_binding_asserted -or $taskResult.actual_storage_read -or $taskResult.real_profile_approved){throw 'Qualification result mismatch'}
}
if(($taskAuthor.cases | ConvertTo-Json -Depth 5 -Compress) -ne ($taskIndependent.cases | ConvertTo-Json -Depth 5 -Compress)){throw 'Ordered cases or outcomes differ'}
$taskAuthorFacts=$taskAuthor | Select-Object -Property * -ExcludeProperty elapsed_seconds | ConvertTo-Json -Depth 10 -Compress
$taskRootFacts=$taskIndependent | Select-Object -Property * -ExcludeProperty elapsed_seconds | ConvertTo-Json -Depth 10 -Compress
if($taskAuthorFacts -ne $taskRootFacts){throw 'Non-time reported facts differ'}
$taskAuthorExit=Get-Content -Raw -LiteralPath (Join-Path $taskAuthorDir 'exit.json') | ConvertFrom-Json
$taskRootExit=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'exit.json') | ConvertFrom-Json
$taskOuterExit=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'outer-exit.json') | ConvertFrom-Json
if($taskAuthorExit.native_exit -ne 0 -or -not $taskAuthorExit.inputs_unchanged -or -not $taskAuthorExit.startup_binding_set -or $taskRootExit.actual_native_exit -ne 0 -or -not $taskRootExit.inputs_unchanged -or $taskOuterExit.tool_observed_outer_exit -ne 0){throw 'Native or outer receipt mismatch'}
foreach($taskDir in @($taskAuthorDir,$taskRoot)){if((Get-Item -LiteralPath (Join-Path $taskDir 'stderr.log')).Length -ne 0){throw 'Nonempty stderr'}}
$taskPins=@{'buffer_basis.py'='bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373';'qualify_basis.py'='fe0e3e5559ecc237bf6d7af4b8f38a4d68d557daa574e4470058c2f2b2fa7aa3'}
foreach($taskName in $taskPins.Keys){foreach($taskDir in @($taskAuthorDir,$taskRoot)){if((Get-FileHash -LiteralPath (Join-Path $taskDir $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPins[$taskName]){throw 'Input source mismatch'}}}
$taskReview=Join-Path $taskBase '_scratch\ASTRA-BUFFER-BASIS-SYNTHETIC-REVIEW-2026-09-13.md'
if((Get-FileHash -LiteralPath $taskReview -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'fb314c6289ccbd8b74c1ab30621481ff7041f53c6a54d9b6e9759f3954a0c68a'){throw 'Root review changed'}
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
foreach($taskFile in $taskOriginalFiles){Copy-Exact $taskFile.FullName ('original-proof20\'+$taskFile.FullName.Substring($taskOriginal.Length+1))}
$taskRootFiles=@(Get-ChildItem -LiteralPath $taskRoot -File -Force)
if($taskRootFiles.Count -ne 7){throw 'Root file count mismatch'}
foreach($taskFile in $taskRootFiles){Copy-Exact $taskFile.FullName ('root-run\'+$taskFile.Name)}
Copy-Exact $taskReview 'review\ASTRA-SYNTHETIC-REVIEW.md'
foreach($taskName in @('BRIEF.md','FINAL-SCOPE.md','seal02.ps1')){Copy-Exact (Join-Path $taskPreparation $taskName) ('preparation\'+$taskName)}
[ordered]@{author_stdout_sha256=(Get-FileHash -LiteralPath (Join-Path $taskAuthorDir 'stdout.json') -Algorithm SHA256).Hash.ToLowerInvariant();root_stdout_sha256=(Get-FileHash -LiteralPath (Join-Path $taskRoot 'stdout.json') -Algorithm SHA256).Hash.ToLowerInvariant();distinct_case_count=37;ordered_case_ids=@($taskAuthor.cases.case);ordered_outcomes_equal=$true;all_non_elapsed_reported_facts_equal=$true;author_elapsed_seconds=$taskAuthor.elapsed_seconds;root_elapsed_seconds=$taskIndependent.elapsed_seconds;comparison_executes_no_tests=$true} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'CASE-COMPARISON.json') -Encoding utf8
[ordered]@{scope='Verification performed before outer manifest; final exact-set check prints outside proof';original_manifest_sha256='581fa57387fa06cf38822000aa8f2fb5d5e7da8a3a6307200283c365faa75bd0';original_payloads_verified=20;original_complete_files=21;root_files=7;both_source_hashes_verified=$true;author_passed=37;root_passed=37;failed=0;author_native_exit=0;root_native_exit=0;root_tool_observed_outer_exit=0;stderr_empty_both=$true;unexpected_audit_events=0;all_reported_facts_except_elapsed_match=$true;source_changed=$false;test_rerun=$false;actual_storage_read=$false;real_profile_approved=$false} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $taskProof 'PRESEAL-VERIFICATION.json') -Encoding utf8
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=$_.FullName.Substring($taskProof.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{scope='Combined author and root synthetic buffer proof; original20 unchanged; no real profile';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'SHA256.json') -Encoding utf8
$taskActual=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | ForEach-Object {$_.FullName.Substring($taskProof.Length+1).Replace('\','/')})
if(Compare-Object ($taskActual | Sort-Object) (@($taskRecords.path)+@('SHA256.json') | Sort-Object)){throw 'Outer exact file-set mismatch'}
foreach($taskRecord in $taskRecords){$taskPath=Join-Path $taskProof $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Outer payload mismatch'}}
[ordered]@{payload_count=$taskRecords.Count;actual_total_files=$taskActual.Count;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant();exact_file_set_verified=$true;all_payloads_verified=$true;original20_unchanged=$true;matching_cases=37;author_passed=37;root_passed=37;failed=0;no_test_rerun=$true} | ConvertTo-Json
