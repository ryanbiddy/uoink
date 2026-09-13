$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proposal01'
$taskRootRun=Join-Path $taskBase '_scratch\astra-asr-resolver-synthetic01'
$taskProof=Join-Path $taskBase '_scratch\asr-trusted-manifest-resolver-proof01'
if(Test-Path -LiteralPath $taskProof){throw 'Fresh proof path required'}
$taskUtf8=[System.Text.UTF8Encoding]::new($false)
$taskCopies=[System.Collections.Generic.List[object]]::new()
$taskFixtures=[System.Collections.Generic.List[object]]::new()
$taskFixtureDirs=[System.Collections.Generic.List[object]]::new()

function Write-TaskJson($taskPath,$taskValue){[System.IO.File]::WriteAllText($taskPath,($taskValue | ConvertTo-Json -Depth 30)+"`n",$taskUtf8)}
function Get-TaskHash($taskPath){return (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
function Assert-TaskPlain($taskItem){if($taskItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint){throw 'Reparse source refused'}}
function Copy-TaskPayload($taskSource,$taskRelative){
    $taskItem=Get-Item -LiteralPath $taskSource -Force
    Assert-TaskPlain $taskItem
    if($taskItem.PSIsContainer){throw 'Payload must be a regular file'}
    $taskHash=Get-TaskHash $taskSource
    $taskDest=Join-Path $taskProof $taskRelative
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($taskDest)) | Out-Null
    Copy-Item -LiteralPath $taskSource -Destination $taskDest -ErrorAction Stop
    if((Get-TaskHash $taskDest) -ne $taskHash -or (Get-TaskHash $taskSource) -ne $taskHash){throw 'Copy/source hash mismatch'}
    $taskCopies.Add([ordered]@{source=$taskSource;sealed_path=$taskRelative.Replace('\','/');bytes=$taskItem.Length;sha256=$taskHash;source_before_copy_after_source_after_equal=$true})
}
function Copy-TaskFlatText($taskDir,$taskRelative){
    foreach($taskItem in Get-ChildItem -LiteralPath $taskDir -Force){
        Assert-TaskPlain $taskItem
        if($taskItem.PSIsContainer){continue}
        if($taskItem.Extension -notin @('.py','.ps1','.md','.txt','.json','.log') -or $taskItem.Length -gt 262144){throw 'Unexpected documentary payload'}
        Copy-TaskPayload $taskItem.FullName (Join-Path $taskRelative $taskItem.Name)
    }
}
function Check-TaskRun($taskDir,$taskPassed,$taskFailed,$taskExit,$taskCount){
    $taskPlan=Get-Content -LiteralPath (Join-Path $taskDir 'plan.json') -Raw | ConvertFrom-Json
    $taskRaw=Get-Content -LiteralPath (Join-Path $taskDir 'stdout.json') -Raw | ConvertFrom-Json
    $taskEnd=Get-Content -LiteralPath (Join-Path $taskDir 'exit.json') -Raw | ConvertFrom-Json
    if($taskRaw.passed -ne $taskPassed -or $taskRaw.failed -ne $taskFailed -or $taskRaw.qualification_exit -ne $taskExit -or $taskRaw.cases.Count -ne $taskCount){throw 'Raw case count mismatch'}
    if(@($taskRaw.cases | Where-Object {$_.passed}).Count -ne $taskPassed -or @($taskRaw.cases.name | Sort-Object -Unique).Count -ne $taskCount){throw 'Raw membership mismatch'}
    if($taskEnd.native_exit -ne $taskExit -or -not $taskEnd.inputs_unchanged -or -not $taskRaw.startup_binding_asserted -or @($taskRaw.guard_denials).Count -ne 0){throw 'Raw exit/startup/guard mismatch'}
    if((Get-Item -LiteralPath (Join-Path $taskDir 'stderr.log')).Length -ne 0){throw 'Unexpected raw stderr'}
    foreach($taskRecord in $taskPlan.inputs){
        if([System.IO.Path]::GetFileName($taskRecord.name) -ne $taskRecord.name){throw 'Unsafe plan member'}
        if((Get-TaskHash (Join-Path $taskDir $taskRecord.name)) -ne $taskRecord.sha256){throw 'Archived launch input mismatch'}
    }
    return [ordered]@{directory=$taskDir;passed=$taskPassed;failed=$taskFailed;cases=$taskCount;qualification_exit=$taskExit;native_exit=$taskEnd.native_exit;elapsed_seconds=$taskRaw.elapsed_seconds;recorded_originals_unchanged_after_run=$taskEnd.inputs_unchanged;archived_input_count=@($taskPlan.inputs).Count;archived_inputs_match_before_hashes=$true;case_names=@($taskRaw.cases.name)}
}

[System.IO.Directory]::CreateDirectory($taskProof) | Out-Null
$taskAllowedProposalDirs=@('drafts','resolver-preflight01','resolver-preflight02','identity-diagnostic01')
foreach($taskItem in Get-ChildItem -LiteralPath $taskProposal -Directory -Force){Assert-TaskPlain $taskItem;if($taskItem.Name -notin $taskAllowedProposalDirs){throw 'Unexpected proposal subdirectory'}}
Copy-TaskFlatText $taskProposal 'proposal'
Copy-TaskFlatText (Join-Path $taskProposal 'drafts') 'proposal/drafts'
foreach($taskRunName in @('resolver-preflight01','resolver-preflight02','identity-diagnostic01')){Copy-TaskFlatText (Join-Path $taskProposal $taskRunName) ('proposal/'+$taskRunName)}
Copy-TaskFlatText $taskRootRun 'root-run'
Copy-TaskPayload (Join-Path $taskProposal 'COMBINED-VERDICT.md') 'VERDICT.md'

$taskChecks=@()
$taskChecks += Check-TaskRun (Join-Path $taskProposal 'resolver-preflight01') 64 9 1 73
$taskChecks += Check-TaskRun (Join-Path $taskProposal 'resolver-preflight02') 87 0 0 87
$taskChecks += Check-TaskRun $taskRootRun 87 0 0 87
if(($taskChecks[1].case_names -join "`n") -ne ($taskChecks[2].case_names -join "`n")){throw 'Author/root case membership differs'}
foreach($taskPair in @(@('resolver-preflight01',1),@('resolver-preflight02',0),@('identity-diagnostic01',0))){
    $taskOuter=Get-Content -LiteralPath (Join-Path $taskProposal ($taskPair[0]+'/outer-exit.json')) -Raw | ConvertFrom-Json
    if($taskOuter.outer_exit -ne $taskPair[1]){throw 'Author outer exit mismatch'}
}
$taskRootOuter=Get-Content -LiteralPath (Join-Path $taskRootRun 'outer-tool-result.json') -Raw | ConvertFrom-Json
if($taskRootOuter.exit_code -ne 0){throw 'Root outer exit mismatch'}

$taskFixtureRoots=@(
    @('author-run01',(Join-Path $taskProposal 'resolver-preflight01/synthetic-assets')),
    @('author-run02',(Join-Path $taskProposal 'resolver-preflight02/synthetic-assets')),
    @('root-run',(Join-Path $taskRootRun 'synthetic-assets'))
)
foreach($taskGroup in $taskFixtureRoots){
    $taskQueue=[System.Collections.Generic.Queue[string]]::new()
    $taskQueue.Enqueue($taskGroup[1])
    while($taskQueue.Count){
        $taskDirectory=$taskQueue.Dequeue()
        Assert-TaskPlain (Get-Item -LiteralPath $taskDirectory)
        foreach($taskItem in Get-ChildItem -LiteralPath $taskDirectory -Force){
            Assert-TaskPlain $taskItem
            $taskRelative=[System.IO.Path]::GetRelativePath($taskGroup[1],$taskItem.FullName).Replace('\','/')
            if($taskRelative -match '(^|/)\.\.(/|$)' -or $taskRelative.Split('/').Count -gt 4 -or $taskRelative -notmatch '^[A-Za-z0-9_.\-/]+$'){throw 'Unexpected generated path'}
            $taskArchivePath=$taskGroup[0]+'/'+$taskRelative
            if($taskItem.PSIsContainer){
                $taskFixtureDirs.Add([ordered]@{source=$taskItem.FullName;archive_path=$taskArchivePath+'/'})
                $taskQueue.Enqueue($taskItem.FullName)
            }else{
                if($taskItem.Length -gt 4096 -or $taskFixtures.Count -ge 1000){throw 'Synthetic fixture byte/count bound'}
                $taskFixtures.Add([ordered]@{source=$taskItem.FullName;archive_path=$taskArchivePath;bytes=$taskItem.Length;sha256=(Get-TaskHash $taskItem.FullName)})
            }
        }
    }
}
$taskArchivePath=Join-Path $taskProof 'generated-fixtures.zip'
$taskArchiveFile=[System.IO.File]::Open($taskArchivePath,[System.IO.FileMode]::CreateNew)
$taskArchive=[System.IO.Compression.ZipArchive]::new($taskArchiveFile,[System.IO.Compression.ZipArchiveMode]::Create,$false)
try{
    foreach($taskDir in $taskFixtureDirs){$taskEntry=$taskArchive.CreateEntry($taskDir.archive_path);$taskEntry.LastWriteTime=[DateTimeOffset]::new(1980,1,1,0,0,0,[TimeSpan]::Zero)}
    foreach($taskFixture in $taskFixtures){
        $taskEntry=$taskArchive.CreateEntry($taskFixture.archive_path,[System.IO.Compression.CompressionLevel]::Optimal)
        $taskEntry.LastWriteTime=[DateTimeOffset]::new(1980,1,1,0,0,0,[TimeSpan]::Zero)
        $taskInput=[System.IO.File]::OpenRead($taskFixture.source)
        $taskOutput=$taskEntry.Open()
        try{$taskInput.CopyTo($taskOutput)}finally{$taskOutput.Dispose();$taskInput.Dispose()}
        if((Get-TaskHash $taskFixture.source) -ne $taskFixture.sha256){throw 'Fixture changed during archive'}
    }
}finally{$taskArchive.Dispose();$taskArchiveFile.Dispose()}
$taskArchive=[System.IO.Compression.ZipFile]::OpenRead($taskArchivePath)
$taskExpected=@{}
foreach($taskFixture in $taskFixtures){$taskExpected.Add($taskFixture.archive_path,$taskFixture)}
$taskSeen=@{}
try{
    foreach($taskEntry in $taskArchive.Entries){
        if($taskSeen.ContainsKey($taskEntry.FullName)){throw 'Duplicate ZIP entry'}
        $taskSeen.Add($taskEntry.FullName,$true)
        if($taskEntry.FullName.EndsWith('/')){if($taskEntry.Length -ne 0){throw 'Nonempty ZIP directory'};continue}
        if(-not $taskExpected.ContainsKey($taskEntry.FullName)){throw 'Unexpected ZIP payload'}
        $taskExpectedFile=$taskExpected[$taskEntry.FullName]
        if($taskEntry.Length -ne $taskExpectedFile.bytes -or $taskEntry.Length -gt 4096){throw 'ZIP size mismatch'}
        $taskInput=$taskEntry.Open()
        $taskSha=[System.Security.Cryptography.SHA256]::Create()
        try{$taskHash=[Convert]::ToHexString($taskSha.ComputeHash($taskInput)).ToLowerInvariant()}finally{$taskSha.Dispose();$taskInput.Dispose()}
        if($taskHash -ne $taskExpectedFile.sha256){throw 'ZIP content mismatch'}
    }
    if($taskSeen.Count -ne $taskFixtures.Count+$taskFixtureDirs.Count){throw 'ZIP membership mismatch'}
}finally{$taskArchive.Dispose()}

$taskDiagnosticDir=Join-Path $taskProposal 'identity-diagnostic01'
$taskDiagnostic=Get-Content -LiteralPath (Join-Path $taskDiagnosticDir 'stdout.json') -Raw | ConvertFrom-Json
$taskDiagnosticExit=Get-Content -LiteralPath (Join-Path $taskDiagnosticDir 'exit.json') -Raw | ConvertFrom-Json
$taskDiagnosticPlan=Get-Content -LiteralPath (Join-Path $taskDiagnosticDir 'plan.json') -Raw | ConvertFrom-Json
if($taskDiagnostic.observed -ne 40 -or $taskDiagnostic.refused -ne 0 -or $taskDiagnostic.diagnostic_exit -ne 0 -or @($taskDiagnostic.guard_denials).Count -ne 0 -or $taskDiagnosticExit.native_exit -ne 0 -or -not $taskDiagnosticExit.inputs_unchanged -or -not $taskDiagnostic.startup_binding_asserted){throw 'Diagnostic outcome mismatch'}
if((Get-Item -LiteralPath (Join-Path $taskDiagnosticDir 'stderr.log')).Length -ne 0){throw 'Diagnostic stderr is not empty'}
foreach($taskInputRecord in $taskDiagnosticPlan.inputs){
    if([System.IO.Path]::GetFileName($taskInputRecord.name) -ne $taskInputRecord.name -or (Get-TaskHash (Join-Path $taskDiagnosticDir $taskInputRecord.name)) -ne $taskInputRecord.sha256){throw 'Diagnostic archived input mismatch'}
}
$taskCtimeMismatches=0
foreach($taskObservation in $taskDiagnostic.records){
    if(@($taskObservation.mismatched_fields.fstat_before_vs_fstat_after).Count -ne 0 -or @($taskObservation.mismatched_fields.lstat_before_vs_lstat_after).Count -ne 0){throw 'Unexpected same-API diagnostic change'}
    $taskCross=@($taskObservation.mismatched_fields.lstat_before_vs_fstat_before)
    if($taskCross.Count){
        if($taskCross.Count -ne 1 -or $taskCross[0] -ne 'st_ctime_ns' -or @($taskObservation.mismatched_fields.fstat_after_vs_lstat_after).Count -ne 1 -or $taskObservation.mismatched_fields.fstat_after_vs_lstat_after[0] -ne 'st_ctime_ns'){throw 'Unexpected cross-API diagnostic mismatch'}
        $taskCtimeMismatches++
    }
}
if($taskCtimeMismatches -ne 9){throw 'Diagnostic mismatch count changed'}
$taskDiagnosticMap=@()
foreach($taskRecord in $taskDiagnostic.records){
    if($taskRecord.status -ne 'observed' -or -not $taskRecord.prefix_verified -or $taskRecord.path -match '(^|[\\/])\.\.([\\/]|$)'){throw 'Diagnostic source record refused'}
    $taskRelative=$taskRecord.path.Replace('\','/')
    $taskArchiveKey='author-run01/'+$taskRelative
    if(-not $taskExpected.ContainsKey($taskArchiveKey)){throw 'Diagnostic file absent from exact fixture inventory'}
    $taskFixture=$taskExpected[$taskArchiveKey]
    $taskSealed='diagnostic-fixtures/'+$taskRelative
    Copy-TaskPayload $taskFixture.source $taskSealed
    $taskDiagnosticMap += [ordered]@{original_source_path=$taskFixture.source;sealed_copy=$taskSealed;archive_entry=$taskArchiveKey;retained_bytes_sha256_at_sealing=$taskFixture.sha256;historical_content_sha256_available=$false;historical_observation=$taskRecord;copied_filesystem_metadata_is_not_original_observation=$true}
}
if(@($taskDiagnosticMap).Count -ne 40){throw 'Diagnostic mapping count mismatch'}
Write-TaskJson (Join-Path $taskProof 'diagnostic-source-metadata-map.json') ([ordered]@{scope='Historical JSON observations refer to original paths; copied/extracted inodes/timestamps are different. Hashes bind retained bytes at sealing, not a historical digest.';files=$taskDiagnosticMap})
Write-TaskJson (Join-Path $taskProof 'fixture-inventory.json') ([ordered]@{scope='Generated synthetic placeholders only, including intentional negative fixtures; ZIP timestamps are fixed archival metadata.';file_count=$taskFixtures.Count;directory_count=$taskFixtureDirs.Count;files=$taskFixtures;directories=$taskFixtureDirs;every_zip_payload_verified=$true})
Write-TaskJson (Join-Path $taskProof 'source-copy-map.json') ([ordered]@{copies=$taskCopies;every_copy_and_source_hash_verified=$true})
Write-TaskJson (Join-Path $taskProof 'verification.json') ([ordered]@{date='2026-09-13';runs=$taskChecks;author_root_case_membership_exact=$true;all_recorded_launch_input_hashes_verified_from_archived_copies=$true;independent_root_outer_exit=$taskRootOuter.exit_code;diagnostic_observed=40;diagnostic_refused=0;diagnostic_native_exit=0;diagnostic_elapsed_seconds=$taskDiagnostic.elapsed_seconds;fixture_files=$taskFixtures.Count;fixture_directories=$taskFixtureDirs.Count;all_fixture_zip_payloads_verified=$true;diagnostic_copies=40;source_copy_count=$taskCopies.Count;product_or_model_runs_by_sealer=0})
[System.IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",$taskUtf8)
$taskPayloads=@(Get-ChildItem -LiteralPath $taskProof -File -Recurse -Force | Sort-Object FullName | ForEach-Object {[ordered]@{path=[System.IO.Path]::GetRelativePath($taskProof,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-TaskHash $_.FullName)}})
$taskTotal=($taskPayloads | Measure-Object -Property bytes -Sum).Sum
Write-TaskJson (Join-Path $taskProof 'SHA256.json') ([ordered]@{schema='uoink.documentary-payload-sha256.v1';payload_count=$taskPayloads.Count;payload_bytes=$taskTotal;excluded_only='SHA256.json';files=$taskPayloads})
foreach($taskPayload in $taskPayloads){if((Get-TaskHash (Join-Path $taskProof $taskPayload.path)) -ne $taskPayload.sha256){throw 'Final payload hash mismatch'}}
[ordered]@{proof=$taskProof;payload_count=$taskPayloads.Count;payload_bytes=$taskTotal;manifest_sha256=(Get-TaskHash (Join-Path $taskProof 'SHA256.json'));fixture_files=$taskFixtures.Count;fixture_directories=$taskFixtureDirs.Count;fixture_uncompressed_bytes=($taskFixtures | Measure-Object -Property bytes -Sum).Sum;fixture_archive_bytes=(Get-Item -LiteralPath $taskArchivePath).Length;verified_copies=$taskCopies.Count;diagnostic_copies=40} | ConvertTo-Json
