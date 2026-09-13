$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-buffer-version-adapter-proposal01'
$taskRoot=Join-Path $taskBase '_scratch\astra-d1-adapter-synthetic01'
$taskAuthor=Join-Path $taskProposal 'd1-preflight01'
$taskProof=Join-Path $taskBase '_scratch\vad-buffer-version-adapter-final-proof01'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh proof required'}
$taskA=Get-Content -Raw -LiteralPath (Join-Path $taskAuthor 'stdout.json') | ConvertFrom-Json
$taskR=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'stdout.json') | ConvertFrom-Json
foreach($taskResult in @($taskA,$taskR)){
 if($taskResult.passed -ne 54 -or $taskResult.failed -ne 0 -or $taskResult.qualification_exit -ne 0 -or @($taskResult.cases).Count -ne 54 -or @($taskResult.cases.case | Sort-Object -Unique).Count -ne 54 -or @($taskResult.cases | Where-Object {-not $_.passed}).Count -ne 0 -or @($taskResult.unexpected_audit_events).Count -ne 0 -or @($taskResult.forbidden_conversion_calls).Count -ne 0 -or -not $taskResult.startup_binding_asserted -or $taskResult.actual_artifact_or_storage_read -or $taskResult.real_owner_profile_approved -or $taskResult.conversion_profile_activated){throw 'Result mismatch'}
}
if(($taskA.cases | ConvertTo-Json -Depth 5 -Compress) -ne ($taskR.cases | ConvertTo-Json -Depth 5 -Compress)){throw 'Ordered case membership/outcome mismatch'}
if(($taskA | Select-Object -Property * -ExcludeProperty elapsed_seconds | ConvertTo-Json -Depth 10 -Compress) -ne ($taskR | Select-Object -Property * -ExcludeProperty elapsed_seconds | ConvertTo-Json -Depth 10 -Compress)){throw 'Non-time facts mismatch'}
foreach($taskRun in @($taskAuthor,$taskRoot)){
 $taskExit=Get-Content -Raw -LiteralPath (Join-Path $taskRun 'exit.json') | ConvertFrom-Json
 if($taskExit.native_exit -ne 0 -or -not $taskExit.inputs_unchanged -or -not $taskExit.startup_binding_set -or (Get-Item -LiteralPath (Join-Path $taskRun 'stderr.log')).Length -ne 0){throw 'Native receipt mismatch'}
}
$taskOuter=Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'outer-tool-result.json') | ConvertFrom-Json
if($taskOuter.exit_code -ne 0){throw 'Root outer exit mismatch'}
$taskPlan=Get-Content -Raw -LiteralPath (Join-Path $taskAuthor 'plan.json') | ConvertFrom-Json
if(@($taskPlan.inputs).Count -ne 8 -or @($taskPlan.inputs.name | Sort-Object -Unique).Count -ne 8){throw 'Input count mismatch'}
foreach($taskInput in $taskPlan.inputs){foreach($taskDir in @($taskProposal,$taskAuthor,$taskRoot)){if((Get-FileHash -LiteralPath (Join-Path $taskDir $taskInput.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInput.sha256){throw 'Input changed'}}}
if((Get-FileHash -LiteralPath (Join-Path $taskProposal 'inspect_adapter.py') -Algorithm SHA256).Hash.ToLowerInvariant() -ne '533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649'){throw 'Adapter source mismatch'}
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
foreach($taskFile in Get-ChildItem -LiteralPath $taskProposal -Recurse -File -Force){Copy-Exact $taskFile.FullName ('proposal\'+$taskFile.FullName.Substring($taskProposal.Length+1))}
$taskRootFiles=@(Get-ChildItem -LiteralPath $taskRoot -File -Force)
if($taskRootFiles.Count -ne 15){throw 'Root payload count mismatch'}
foreach($taskFile in $taskRootFiles){Copy-Exact $taskFile.FullName ('root-run\'+$taskFile.Name)}
$taskPriorSeals=@(
 @('_scratch\vad-fixed-converter-final-proof02\SHA256.json','converter81-SHA256.json','96fc5968bf5423681e3d037a93e4d043f34d0aca9a2a89093678d3fba18e187e'),
 @('_scratch\vad-buffer-endian-final-proof02\SHA256.json','buffer35-SHA256.json','1025f7210cfde794b457ed00f7b9062694487e682dab786ecdc2d4ec7c03f0a1')
)
foreach($taskPrior in $taskPriorSeals){$taskSource=Join-Path $taskBase $taskPrior[0];if((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPrior[2]){throw 'Prior seal mismatch'};Copy-Exact $taskSource ('prior-seals\'+$taskPrior[1])}
[ordered]@{ordered_case_ids=@($taskA.cases.case);distinct_case_count=54;ordered_outcomes_equal=$true;all_reported_facts_except_elapsed_equal=$true;author_elapsed_seconds=$taskA.elapsed_seconds;root_elapsed_seconds=$taskR.elapsed_seconds;author_stdout_sha256=(Get-FileHash -LiteralPath (Join-Path $taskAuthor 'stdout.json') -Algorithm SHA256).Hash.ToLowerInvariant();root_stdout_sha256=(Get-FileHash -LiteralPath (Join-Path $taskRoot 'stdout.json') -Algorithm SHA256).Hash.ToLowerInvariant();comparison_executes_no_tests=$true} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'CASE-COMPARISON.json') -Encoding utf8
[ordered]@{scope='Preseal input/result verification; outer exact-set check prints outside proof';source_and_both_run_inputs_verified=24;author_passed=54;root_passed=54;failed=0;author_native_exit=0;root_native_exit=0;root_outer_exit=0;stderr_empty_both=$true;unexpected_audit_events=0;forbidden_conversion_calls=0;all_cases_and_non_time_facts_agree=$true;source_changed=$false;test_rerun=$false;actual_artifact_or_storage_read=$false;real_owner_approval_absent=$true;conversion_profile_activated=$false} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $taskProof 'PRESEAL-VERIFICATION.json') -Encoding utf8
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=$_.FullName.Substring($taskProof.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{scope='D1 static adapter proposal; author/root synthetic only; no real invocation approval';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'SHA256.json') -Encoding utf8
$taskActual=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File -Force | ForEach-Object {$_.FullName.Substring($taskProof.Length+1).Replace('\','/')})
if(Compare-Object ($taskActual | Sort-Object) (@($taskRecords.path)+@('SHA256.json') | Sort-Object)){throw 'Unlisted or missing outer proof file'}
foreach($taskRecord in $taskRecords){$taskPath=Join-Path $taskProof $taskRecord.path;if((Get-Item -LiteralPath $taskPath).Length -ne $taskRecord.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Final payload mismatch'}}
[ordered]@{payload_count=$taskRecords.Count;actual_total_files=$taskActual.Count;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant();exact_file_set_verified=$true;all_payloads_verified=$true;author_passed=54;root_passed=54;failed=0;actual_artifact_or_storage_read=$false;real_owner_approval_absent=$true} | ConvertTo-Json
