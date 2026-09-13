$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-fixed-converter-proposal01'
$taskProof=Join-Path $taskBase '_scratch\vad-fixed-converter-final-proof01'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh proof destination required'}
$taskPinned=@{
 'fixed_converter.py'='b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b';
 'zip_bounds.py'='bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6';
 'fixed-plan.json'='37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf';
 'qualify_converter.py'='11f9addddf9b349c4ee249c000cc60c4986b989de2e11ec990ba940d6b7949a9'
}
foreach($taskName in $taskPinned.Keys){if((Get-FileHash -LiteralPath (Join-Path $taskProposal $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPinned[$taskName]){throw 'Frozen input mismatch'}}
$taskAuthor=Get-Content -Raw -LiteralPath (Join-Path $taskProposal 'converter-preflight03\stdout.json') | ConvertFrom-Json
$taskRootDir=Join-Path $taskBase '_scratch\astra-vad-converter-synthetic01'
$taskRoot=Get-Content -Raw -LiteralPath (Join-Path $taskRootDir 'stdout.json') | ConvertFrom-Json
foreach($taskResult in @($taskAuthor,$taskRoot)){
 if($taskResult.passed -ne 82 -or $taskResult.failed -ne 0 -or $taskResult.qualification_exit -ne 0 -or @($taskResult.cases).Count -ne 82 -or @($taskResult.cases | Where-Object {-not $_.passed}).Count -ne 0 -or @($taskResult.unexpected_audit_events).Count -ne 0){throw 'Synthetic result mismatch'}
}
if(($taskAuthor.cases.case -join "`n") -ne ($taskRoot.cases.case -join "`n") -or @($taskAuthor.cases.case | Sort-Object -Unique).Count -ne 82){throw 'Case identity mismatch'}
$taskOuter=Get-Content -Raw -LiteralPath (Join-Path $taskRootDir 'outer-exit.json') | ConvertFrom-Json
if($taskOuter.actual_outer_exit -ne 0){throw 'Root outer exit mismatch'}
foreach($taskRun in @((Join-Path $taskProposal 'converter-preflight03'),$taskRootDir)){
 $taskExit=Get-Content -Raw -LiteralPath (Join-Path $taskRun 'exit.json') | ConvertFrom-Json
 if($taskExit.native_exit -ne 0 -or -not $taskExit.inputs_unchanged -or -not $taskExit.startup_binding_set -or (Get-Item -LiteralPath (Join-Path $taskRun 'stderr.log')).Length -ne 0){throw 'Native receipt mismatch'}
}
New-Item -ItemType Directory -Path $taskProof -ErrorAction Stop | Out-Null
function Copy-SealFile([string]$source,[string]$relative){
 $taskSource=Join-Path $taskBase $source
 $taskItem=Get-Item -LiteralPath $taskSource -ErrorAction Stop
 if($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Non-plain payload'}
 $taskDestination=Join-Path $taskProof $relative
 New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($taskDestination)) -Force | Out-Null
 $taskBefore=(Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
 Copy-Item -LiteralPath $taskSource -Destination $taskDestination -ErrorAction Stop
 if((Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore -or (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore){throw 'Payload changed during copy'}
}
foreach($taskFile in Get-ChildItem -LiteralPath $taskProposal -Recurse -File){$taskRel=$taskFile.FullName.Substring($taskProposal.Length+1);Copy-SealFile ('_scratch\vad-fixed-converter-proposal01\'+$taskRel) ('proposal\'+$taskRel)}
foreach($taskFile in Get-ChildItem -LiteralPath $taskRootDir -File){Copy-SealFile ('_scratch\astra-vad-converter-synthetic01\'+$taskFile.Name) ('root-run\'+$taskFile.Name)}
$taskExtras=@(
 @('_scratch\vad-converter-independent-review01\PRE-SYNTHETIC-REVIEW.md','review\PRE-SYNTHETIC-REVIEW.md'),
 @('_scratch\vad-converter-independent-review01\FINAL-REVIEW.md','review\FINAL-REVIEW.md'),
 @('_scratch\ASTRA-VAD-CONVERTER-SYNTHETIC-REVIEW-2026-09-13.md','review\ASTRA-SYNTHETIC-REVIEW.md'),
 @('_scratch\run_astra_vad_converter_synthetic01.ps1','root-run\launcher.ps1'),
 @('_scratch\vad-selected-metadata-map01\mapping.json','context\mapping.json'),
 @('_scratch\vad-selected-metadata-map01\manifest.proposal02.json','context\manifest.proposal02.json'),
 @('_scratch\vad-selected-metadata-map01\fixed-factory.proposal.txt','context\fixed-factory.proposal.txt'),
 @('_scratch\vad-metadata-independent-review01\VERDICT.md','context\MAPPING-VERDICT.md'),
 @('_scratch\vad-selected-metadata-map-final-proof01\SHA256.json','prior-seals\mapping48-SHA256.json'),
 @('_scratch\vad-static-inventory-final-proof01\SHA256.json','prior-seals\inventory80-SHA256.json'),
 @('_scratch\vad-static-metadata-tail-final-proof01\SHA256.json','prior-seals\tail29-SHA256.json'),
 @('_scratch\vad-selected-root-projection-final-proof01\SHA256.json','prior-seals\projection214-SHA256.json'),
 @('_scratch\vad-provenance-text01\SHA256.json','prior-seals\provenance88-SHA256.json'),
 @('_scratch\vad-provenance-text01\REPORT.md','context\PROVENANCE-REPORT.md')
)
foreach($taskPair in $taskExtras){Copy-SealFile $taskPair[0] $taskPair[1]}
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@(Get-ChildItem -LiteralPath $taskProof -Recurse -File | Sort-Object FullName | ForEach-Object {[ordered]@{path=$_.FullName.Substring($taskProof.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[ordered]@{scope='Synthetic converter proposal only; no actual artifact read or accepted real profile';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskProof 'SHA256.json') -Encoding utf8
foreach($taskRecord in $taskRecords){if((Get-FileHash -LiteralPath (Join-Path $taskProof $taskRecord.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){throw 'Sealed payload mismatch'}}
$taskSeal=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{payload_count=$taskRecords.Count;manifest_sha256=$taskSeal;verified_payloads=$taskRecords.Count;author_passed=82;root_passed=82;failed=0;real_profile_accepted=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskProof 'VERIFICATION.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskProof 'VERIFICATION.json')
