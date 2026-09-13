$ErrorActionPreference = 'Stop'
$taskCheckout = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scratch = Join-Path $taskCheckout '_scratch'
$asrSource = Join-Path $scratch 'asr-asset-metadata01'
$asrProof = Join-Path $scratch 'asr-asset-metadata-proof01'
$pipelineSource = Join-Path $scratch 'pipeline-candidate05-contracts01'
$pipelineIndependent = Join-Path $scratch 'astra-pipeline-contracts01'
$pipelineProof = Join-Path $scratch 'pipeline-contracts-proof01'
$encoding = [System.Text.UTF8Encoding]::new($false)
function Assert($condition, [string]$reason) { if (-not $condition) { throw $reason } }
function Read-Json([string]$path) { Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
function Digest([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-Json([string]$path, $value) {
    Assert (-not (Test-Path -LiteralPath $path)) "Output already exists: $path"
    [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 70) + "`n", $encoding)
}
function Files([string]$root) {
    @(Get-ChildItem -LiteralPath $root -File -Recurse -Force | ForEach-Object {
        Assert (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Linked input refused'
        $_.FullName.Substring($root.Length + 1).Replace('\','/')
    } | Sort-Object)
}
function Exact-Membership([string]$root, $expected) {
    $actual = @(Files $root)
    Assert ($actual.Count -eq $expected.Count) "Unexpected file count under $root"
    Assert (@(Compare-Object $actual @($expected | Sort-Object)).Count -eq 0) "Unexpected file membership under $root"
}
function Check-Bytes([string]$path, [long]$bytes, [string]$sha) {
    Assert ((Get-Item -LiteralPath $path).Length -eq $bytes) "Size mismatch: $path"
    Assert ((Digest $path) -eq $sha) "Hash mismatch: $path"
}
function Copy-Verified([string]$source, [string]$destination, [string]$proofRoot, $ledger) {
    Assert ($destination.StartsWith($proofRoot + '\', [StringComparison]::OrdinalIgnoreCase)) 'Outside proof destination'
    Assert (-not (Test-Path -LiteralPath $destination)) "Destination already exists: $destination"
    $sourceInfo = Get-Item -LiteralPath $source
    Assert (-not $sourceInfo.PSIsContainer) 'Directory copy refused'
    Assert (($sourceInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Linked source refused'
    Assert ($sourceInfo.Name -eq '.gitattributes' -or $sourceInfo.Extension -in @('.json','.md','.txt','.py','.ps1','.log')) 'Non-text suffix refused'
    $before = Digest $source
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    [IO.File]::Copy($source, $destination, $false)
    Check-Bytes $destination $sourceInfo.Length $before
    Assert ((Digest $source) -eq $before) "Source changed during copy: $source"
    $ledger.Add([ordered]@{ source=$source; file=$destination.Substring($proofRoot.Length+1).Replace('\','/'); bytes=$sourceInfo.Length; sha256=$before }) | Out-Null
}
function Seal([string]$root, $ledger, $checks) {
    [IO.File]::WriteAllText((Join-Path $root '.gitattributes'), "* -text`n", $encoding)
    Copy-Verified $PSCommandPath (Join-Path $root 'seal-asr-pipeline-evidence01.ps1') $root $ledger
    Write-Json (Join-Path $root 'COPY-BINDINGS.json') ([ordered]@{ created_utc=[DateTime]::UtcNow.ToString('o'); copied_count=$ledger.Count; copies=$ledger })
    Write-Json (Join-Path $root 'VERIFICATION.json') $checks
    $payloads = @(Files $root | ForEach-Object {
        $p=Join-Path $root $_
        [ordered]@{file=$_; bytes=(Get-Item -LiteralPath $p).Length; sha256=(Digest $p)}
    })
    Write-Json (Join-Path $root 'SHA256.json') ([ordered]@{created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$payloads.Count;payloads=$payloads;scope='Documentary evidence seal only; no tests, collector, package, model or binary execution.'})
    Exact-Membership $root @(@($payloads | ForEach-Object {$_.file}) + 'SHA256.json')
    foreach($entry in $payloads) { Check-Bytes (Join-Path $root $entry.file) $entry.bytes $entry.sha256 }
    foreach($entry in $ledger) { Check-Bytes $entry.source $entry.bytes $entry.sha256 }
    [ordered]@{root=$root;payload_count=$payloads.Count;copied_count=$ledger.Count;sha256=(Digest (Join-Path $root 'SHA256.json'));all_hashes_verified=$true}
}

Exact-Membership $asrProof @('SEAL-BRIEF.md','REPORT.md')
Exact-Membership $pipelineProof @('SEAL-BRIEF.md','INDEPENDENT-VERDICT.md')
$asrFiles = @('BRIEF.md','CANONICAL-TURBO-BRIEF.md','REDIRECT-DIAGNOSTIC-BRIEF.md','collect.py','collect-canonical-turbo.py','canonical-turbo-diff.txt','inspect-redirect.py','run01/result.json','run01/outer-exit.json','run01/whisper_runner.py.txt','run01/hf_api.py.txt','redirect01/result.json','redirect01/outer-exit.json','redirect01/body.txt','canonical-turbo01/large-v3-turbo-current.json','canonical-turbo01/large-v3-turbo-pinned.json','canonical-turbo01/result.json','canonical-turbo01/outer-exit.json','canonical-turbo01/whisper_runner.py.txt','canonical-turbo01/hf_api.py.txt')
foreach($choice in @('tiny','base','small','medium','large')) { $asrFiles += @("run01/$choice-current.json", "run01/$choice-pinned.json") }
Exact-Membership $asrSource $asrFiles
$first=Read-Json (Join-Path $asrSource 'run01/result.json')
$canonical=Read-Json (Join-Path $asrSource 'canonical-turbo01/result.json')
$redirect=Read-Json (Join-Path $asrSource 'redirect01/result.json')
Assert ($first.status -eq 'FAILED' -and $first.exit -eq 1 -and $first.requests.Count -eq 11 -and @($first.requests|Where-Object {$_.ok}).Count -eq 10 -and $first.plans.Count -eq 5 -and $first.failures.Count -eq 1) 'Original failure not preserved'
Assert ($first.requests[-1].failure.type -eq 'PermissionError' -and $first.requests[-1].failure.message -eq 'Redirect refused') 'Original refusal mismatch'
Assert ($canonical.status -eq 'METADATA_CAPTURED' -and $canonical.exit -eq 0 -and $canonical.requests.Count -eq 2 -and $canonical.plans.Count -eq 1 -and $canonical.failures.Count -eq 0) 'Canonical outcome mismatch'
Assert ($redirect.status -eq 307 -and $redirect.diagnostic_exit -eq 0 -and -not $redirect.redirect_followed -and -not $redirect.plan_accepted -and $redirect.body_bytes_retained -eq 0) 'Redirect diagnostic mismatch'
Assert ($redirect.location -eq '/api/models/dropbox-dash/faster-whisper-large-v3-turbo?blobs=true') 'Canonical diagnostic identity mismatch'
Check-Bytes (Join-Path $asrSource 'redirect01/body.txt') $redirect.body_bytes_retained $redirect.body_sha256
foreach($run in @('run01','redirect01','canonical-turbo01')) {
    $outer=Read-Json (Join-Path $asrSource "$run/outer-exit.json")
    $expected=0
    if($run -eq 'run01') {$expected=1}
    Assert ($outer.actual_outer_exit -eq $expected) "ASR actual outer exit mismatch: $run"
}
$models=[Collections.Generic.List[object]]::new()
$rawCount=0
$sourceCount=0
$selectedCount=0
$lfsCount=0
$ordinaryCount=0
$approximate=@{tiny=80;base=150;small=490;medium=1540;large=3100;'large-v3-turbo'=1630}
foreach($run in @('run01','canonical-turbo01')) {
    $result=Read-Json (Join-Path $asrSource "$run/result.json")
    foreach($request in @($result.requests|Where-Object {$_.ok})) {
        Assert ($request.status -eq 200) 'Unexpected successful HTTP status'
        Check-Bytes (Join-Path $asrSource "$run/$($request.file)") $request.bytes $request.sha256
        $rawCount++
    }
    foreach($binding in $result.source_bindings) {
        Check-Bytes (Join-Path $asrSource "$run/$($binding.copy)") $binding.bytes $binding.sha256
        $sourceCount++
    }
    foreach($plan in $result.plans) {
        $pinned=Read-Json (Join-Path $asrSource "$run/$($plan.choice)-pinned.json")
        $current=Read-Json (Join-Path $asrSource "$run/$($plan.choice)-current.json")
        Assert ($pinned.sha -eq $plan.revision -and $pinned.id -eq $plan.repo -and $current.sha -eq $plan.revision -and $current.id -eq $plan.repo) 'Pinned repository identity mismatch'
        Assert (($pinned.siblings|ConvertTo-Json -Depth 20 -Compress) -eq ($current.siblings|ConvertTo-Json -Depth 20 -Compress)) 'Sibling capture mismatch'
        Assert (-not $plan.asset_downloaded -and -not $plan.manifest_accepted -and -not $plan.all_selected_have_advertised_sha256) 'Asset acceptance flag was changed'
        [long]$sum=0
        foreach($file in $plan.files) {
            $matches=@($pinned.siblings|Where-Object {$_.rfilename -eq $file.path})
            Assert ($matches.Count -eq 1) 'Missing or duplicate selected sibling'
            $sibling=$matches[0]
            Assert ($sibling.size -eq $file.bytes -and $sibling.blobId -eq $file.git_blob_oid -and -not $file.sha256_verified_from_asset) 'Selected byte/OID/verification mismatch'
            if($null -ne $file.lfs_sha256) {
                Assert ($file.path -eq 'model.bin' -and $sibling.lfs.sha256 -eq $file.lfs_sha256 -and $sibling.lfs.size -eq $file.bytes) 'LFS identity mismatch'
                $lfsCount++
            } else {
                Assert ($null -eq $sibling.lfs) 'Ordinary identity incorrectly missing LFS hash'
                $ordinaryCount++
            }
            $selectedCount++
            $sum += $file.bytes
        }
        Assert ($sum -eq $plan.advertised_selected_bytes) 'Selected byte sum mismatch'
        $models.Add([ordered]@{choice=$plan.choice;repo=$plan.repo;revision=$plan.revision;metadata_url="https://huggingface.co/api/models/$($plan.repo)/revision/$($plan.revision)?blobs=true";source_result="capture/$run/result.json";raw_pinned="capture/$run/$($plan.choice)-pinned.json";advertised_selected_bytes=$plan.advertised_selected_bytes;approximate_decimal_mb_from_settings_brief=$approximate[$plan.choice];license_metadata=$plan.license_metadata;files=$plan.files;asset_downloaded=$false;manifest_accepted=$false;all_selected_have_advertised_sha256=$false})
    }
}
Assert ($rawCount -eq 12 -and $sourceCount -eq 4 -and $selectedCount -eq 26 -and $lfsCount -eq 6 -and $ordinaryCount -eq 20 -and $models.Count -eq 6) 'ASR counts mismatch'
$asrLedger=[Collections.Generic.List[object]]::new()
foreach($file in $asrFiles) { Copy-Verified (Join-Path $asrSource $file) (Join-Path $asrProof "capture/$file") $asrProof $asrLedger }
$review=Join-Path $scratch 'asr-asset-metadata-independent-review01/VERDICT.md'
Assert ((Digest $review) -eq '6b44789934f3535c7962247c30e19c328161fb34eedfa373b94bbdd0eaf98a61') 'ASR review changed'
Copy-Verified $review (Join-Path $asrProof 'INDEPENDENT-VERDICT.md') $asrProof $asrLedger
$settings=Join-Path $taskCheckout 'docs/library/RELIABILITY-CONSENT-SETTINGS-REPAIR-BRIEF-2026-09-13.md'
Assert ((Digest $settings) -eq 'e8563bed64c688097ec8f75d7633e3fcae48e7c781ebd95669b3a6f5bb494678') 'Settings brief changed'
Copy-Verified $settings (Join-Path $asrProof 'RELIABILITY-CONSENT-SETTINGS-REPAIR-BRIEF-2026-09-13.md') $asrProof $asrLedger
Write-Json (Join-Path $asrProof 'SIX-MODEL-PLAN.json') ([ordered]@{date='2026-09-13';scope='Public repository metadata only; dated logical byte estimates. No asset downloaded or model accepted.';settings_brief_commit='44e69fc';lfs_sha256_meaning='Publisher-advertised model payload identity, not locally verified';lfs_git_blob_oid_meaning='Git LFS pointer blob identity';ordinary_git_blob_oid_meaning='Ordinary Git blob identity, not SHA256';missing_non_lfs_sha256_count=$ordinaryCount;models=$models})
$asrChecks=[ordered]@{verified_utc=[DateTime]::UtcNow.ToString('o');source_file_count=30;successful_raw_responses_verified=$rawCount;retained_source_copies_verified=$sourceCount;selected_files_verified=$selectedCount;lfs_sha256_records=$lfsCount;ordinary_git_oid_without_sha256_records=$ordinaryCount;initial_status=$first.status;initial_requests=11;initial_successful_responses=10;initial_plan_count=5;initial_exit=1;initial_outer_exit=1;redirect_http_status=307;redirect_followed=$false;redirect_diagnostic_exit=0;redirect_outer_exit=0;canonical_status=$canonical.status;canonical_requests=2;canonical_plan_count=1;canonical_exit=0;canonical_outer_exit=0;all_recorded_response_source_copy_hashes_match=$true;asset_reads=0;new_requests=0;test_executions=0;runtime_accepted=$false}

$authorManifestPath=Join-Path $pipelineSource 'SHA256.json'
Assert ((Digest $authorManifestPath) -eq 'd37beab5e30cdef7680e0aab19538cef93007ea0f3cad445da06fd54d0503ea2') 'Author manifest changed'
$authorManifest=Read-Json $authorManifestPath
Assert ($authorManifest.payload_count -eq 26 -and $authorManifest.payloads.Count -eq 26) 'Author count mismatch'
Exact-Membership $pipelineSource @(@($authorManifest.payloads|ForEach-Object {$_.file}) + 'SHA256.json')
foreach($entry in $authorManifest.payloads) { Check-Bytes (Join-Path $pipelineSource $entry.file) $entry.bytes $entry.sha256 }
$rootFiles=@('BRIEF.md','launch.py','PREQUALIFICATION.json','root-outer-exit.json','ROOT-REVIEW.json','run.py','seams.py','SOURCE-BINDINGS.json','tests.py','inputs/REVIEW.md','inputs/pt_utils.py.txt','inputs/ORIGINAL-SOURCE-MANIFEST.json','inputs/commit-bindings.json','inputs/base.py.txt','inputs/asr.py.txt','launch-pc01/result.json','launch-pc01/plan.json','launch-pc01/console.log','runs/pc01/result.json','runs/pc01/tests.log')
Exact-Membership $pipelineIndependent $rootFiles
$authorPlan=Read-Json (Join-Path $pipelineSource 'launch-pc01/plan.json')
$rootPlan=Read-Json (Join-Path $pipelineIndependent 'launch-pc01/plan.json')
$rootInputs=@($rootPlan.input_hashes.PSObject.Properties)
Assert ($rootInputs.Count -eq 13 -and @($authorPlan.input_hashes.PSObject.Properties).Count -eq 13) 'Planned input count mismatch'
foreach($input in $rootInputs) {
    Assert ($input.Value -eq $authorPlan.input_hashes.($input.Name)) "Author/root planned input differs: $($input.Name)"
    Assert ((Digest (Join-Path $pipelineIndependent $input.Name)) -eq $input.Value) 'Root input changed'
    Assert ((Digest (Join-Path $pipelineSource $input.Name)) -eq $input.Value) 'Author input changed'
}
$rootReview=Read-Json (Join-Path $pipelineIndependent 'ROOT-REVIEW.json')
Assert ($rootReview.verified_input_count -eq 13 -and $rootReview.source_manifest_sha256 -eq (Digest $authorManifestPath)) 'Root source review binding mismatch'
$pipelineOutcomes=[Collections.Generic.List[object]]::new()
foreach($runRoot in @($pipelineSource,$pipelineIndependent)) {
    $result=Read-Json (Join-Path $runRoot 'runs/pc01/result.json')
    $launch=Read-Json (Join-Path $runRoot 'launch-pc01/result.json')
    $outerPath=Join-Path $runRoot 'root-outer-exit.json'
    if($runRoot -eq $pipelineSource) {$outerPath=Join-Path $runRoot 'launch-pc01/root-outer-exit.json'}
    $outer=Read-Json $outerPath
    Assert ($result.tests_run -eq 23 -and $result.passed -eq 23 -and $result.failed -eq 0 -and $result.errors -eq 0 -and $result.skipped -eq 0 -and $result.exit -eq 0 -and $null -eq $result.fatal) 'Pipeline counts/fatal mismatch'
    Assert ($result.observations.Count -eq 23 -and @($result.observations|Where-Object {$_.status -ne 'passed'}).Count -eq 0 -and @($result.observations.id|Sort-Object -Unique).Count -eq 23) 'Pipeline case membership mismatch'
    Assert ($launch.actual_child_exit -eq 0 -and $launch.launcher_exit -eq 0 -and $launch.inputs_unchanged -and $outer.actual_outer_exit -eq 0) 'Pipeline exit or unchanged-input mismatch'
    $guard=$result.guard
    Assert ($guard.valid -and $guard.finder_installed_at_finish -and $guard.profile_installed_at_finish -and $guard.preloaded_heavy.Count -eq 0 -and $guard.postloaded_heavy.Count -eq 0 -and $guard.violations.Count -eq 0 -and $guard.forbidden_pipeline_initializer_calls.Count -eq 0) 'Pipeline guard mismatch'
    Assert ($result.flags.isolated -eq 1 -and $result.flags.no_site -eq 1 -and $result.flags.dont_write_bytecode -eq 1) 'Pipeline Python flags mismatch'
    Assert ($result.diagnostics.Count -eq 1 -and $result.diagnostics[0].status -eq 'UNACCEPTED_OPTIONAL_API_DEFECT' -and $result.diagnostics[0].input -eq 'direct empty list' -and $result.diagnostics[0].exception_type -eq 'IndexError' -and $result.diagnostics[0].line -eq 1242) 'Optional diagnostic changed'
    $log=Get-Content -LiteralPath (Join-Path $runRoot 'runs/pc01/tests.log') -Raw
    Assert ($log -match 'Ran 23 tests in 0\.009s' -and $log -match '(?m)^OK\s*$') 'Raw count/elapsed/OK mismatch'
    $pipelineOutcomes.Add([ordered]@{source=$runRoot;tests_run=23;passed=23;failed=0;errors=0;skipped=0;elapsed_seconds_from_log='0.009';actual_child_exit=0;launcher_exit=0;actual_outer_exit=0;guard_valid=$true;optional_diagnostic=$result.diagnostics[0];case_ids=$result.observations.id})
}
Assert (($pipelineOutcomes[0].case_ids -join "`n") -eq ($pipelineOutcomes[1].case_ids -join "`n")) 'Author/root case lists differ'
$pipelineLedger=[Collections.Generic.List[object]]::new()
foreach($entry in $authorManifest.payloads) { Copy-Verified (Join-Path $pipelineSource $entry.file) (Join-Path $pipelineProof "author26/$($entry.file)") $pipelineProof $pipelineLedger }
Copy-Verified $authorManifestPath (Join-Path $pipelineProof 'author26/ORIGINAL-AUTHOR-SHA256.json') $pipelineProof $pipelineLedger
foreach($file in $rootFiles) { Copy-Verified (Join-Path $pipelineIndependent $file) (Join-Path $pipelineProof "root-independent/$file") $pipelineProof $pipelineLedger }
$pipelineChecks=[ordered]@{verified_utc=[DateTime]::UtcNow.ToString('o');original_author_payloads_verified=26;original_author_manifest_sha256=(Digest $authorManifestPath);root_evidence_files=20;common_planned_inputs_verified=13;unique_qualified_cases=23;qualification_runs=2;outcomes=$pipelineOutcomes;new_executions=0;runtime_accepted=$false}
$sealed=@((Seal $asrProof $asrLedger $asrChecks),(Seal $pipelineProof $pipelineLedger $pipelineChecks))
$sealed | ConvertTo-Json -Depth 5
