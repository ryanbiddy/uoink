$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskOut = Join-Path $taskRoot '_scratch\vad-fixed-loader-proposal01'
$taskBindingsPath = Join-Path $taskOut 'source-bindings.json'
$taskBindingsHash = (Get-FileHash -LiteralPath $taskBindingsPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskBindingsHash -ne '8dbd83213bceac5012bc342e001826902ce3a88fd420fa64f8f8d9a65366fa9c') { throw 'Unexpected binding file' }
foreach ($taskFreshOutput in @('SOURCE-INDEX.md', 'verification.json', 'SHA256.json')) {
    if (Test-Path -LiteralPath (Join-Path $taskOut $taskFreshOutput)) { throw "Refusing existing output $taskFreshOutput" }
}
$taskBindings = Get-Content -Raw -LiteralPath $taskBindingsPath | ConvertFrom-Json
if ($taskBindings.bindings.Count -ne 25) { throw 'Unexpected binding count' }
$taskVerifiedRows = @()
$taskIndex = @('# Captured source and context identities', '', 'These are data copies. Do not import or execute the captured model source.', '', '| Key | Saved file | SHA-256 |', '| --- | --- | --- |')
foreach ($taskRow in $taskBindings.bindings) {
    $taskSrc = [IO.Path]::GetFullPath($taskRow.source)
    $taskDest = [IO.Path]::GetFullPath((Join-Path $taskOut $taskRow.saved_file))
    if (!$taskSrc.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Original path outside checkout' }
    if (!$taskDest.StartsWith($taskOut + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Copy path outside proposal' }
    if ([IO.Path]::GetExtension($taskSrc) -notin @('.py', '.txt', '.md', '.json')) { throw 'Original extension refused' }
    $taskOriginalHash = (Get-FileHash -LiteralPath $taskSrc -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskCopyHash = (Get-FileHash -LiteralPath $taskDest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskOriginalHash -ne $taskRow.sha256 -or $taskCopyHash -ne $taskRow.sha256) { throw "Binding mismatch $($taskRow.key)" }
    if ((Get-Item -LiteralPath $taskDest).Length -ne $taskRow.bytes) { throw 'Byte count mismatch' }
    $taskVerifiedRows += [ordered]@{key=$taskRow.key; original_sha256=$taskOriginalHash; copied_sha256=$taskCopyHash; match=$true}
    $taskIndex += '| ' + $taskRow.key + ' | ' + $taskRow.saved_file + ' | ' + $taskRow.sha256 + ' |'
}
[IO.File]::WriteAllText((Join-Path $taskOut 'SOURCE-INDEX.md'), ($taskIndex -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
$taskManifestDraft = Get-Content -Raw -LiteralPath (Join-Path $taskOut 'manifest.draft.json') | ConvertFrom-Json
if ($taskManifestDraft.status -ne 'DRAFT_UNQUALIFIED_ALWAYS_REFUSE' -or $null -ne $taskManifestDraft.fixed_factory_id -or $taskManifestDraft.artifact.exists_or_approved -ne $false) { throw 'Draft no longer explicitly unqualified' }
$taskInventory = Get-Content -Raw -LiteralPath (Join-Path $taskOut 'context\static-inventory-run03.json') | ConvertFrom-Json
if ($null -ne $taskInventory.architecture_claim -or $taskInventory.model_load_authorized -ne $false -or $taskInventory.conversion_authorized -ne $false -or $taskInventory.inference_authorized -ne $false) { throw 'Inventory scope changed' }
$taskAllowed = @($taskBindings.bindings.saved_file) + @('BRIEF.md', 'capture_sources.ps1', 'source-bindings.json', 'REVIEW.md', 'loader-contract.txt', 'manifest.draft.json', 'QUALIFICATION.md', 'capture-attempt01.json', 'drafts/REVIEW01.md', 'drafts/REVISION-NOTE.md', 'verify_and_seal.ps1', 'SOURCE-INDEX.md', 'verification.json')
$taskVerification = [ordered]@{
    scope='source and context copy verification only'; verified_utc=[DateTime]::UtcNow.ToString('o');
    source_or_lock_files=20; context_files=5; original_and_copy_hashes_verified=25; hash_mismatches=0;
    source_bindings_sha256=$taskBindingsHash; bindings=$taskVerifiedRows;
    proposal_manifest_is_draft=$true; inventory_architecture_claim=$null;
    checkpoint_access_by_this_task='none; only existing JSON receipt read'; model_execution_by_this_task='none';
    tests_run=0; qualification_status='not_run'; payload_count=$taskAllowed.Count;
    preserved_attempt='capture-attempt01.json records original null console projection; source copies and written bindings were intact';
    original_collector_rerun=$false; product_source_modified=$false; staged_or_committed=$false
}
[IO.File]::WriteAllText((Join-Path $taskOut 'verification.json'), ($taskVerification | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
$taskActual = @(Get-ChildItem -LiteralPath $taskOut -Recurse -File | ForEach-Object { $_.FullName.Substring($taskOut.Length + 1).Replace('\','/') })
$taskDifference = @(Compare-Object ($taskAllowed | Sort-Object) ($taskActual | Sort-Object))
if ($taskDifference.Count) { throw 'Unexpected/missing file in proposal' }
$taskPayloads = @()
foreach ($taskRel in ($taskAllowed | Sort-Object)) {
    $taskPath = Join-Path $taskOut $taskRel
    $taskPayloads += [ordered]@{path=$taskRel; bytes=(Get-Item -LiteralPath $taskPath).Length; sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$taskSeal = [ordered]@{scope='source-only fixed VAD proposal; no model acceptance'; payload_count=$taskPayloads.Count; files=$taskPayloads}
$taskSealPath = Join-Path $taskOut 'SHA256.json'
[IO.File]::WriteAllText($taskSealPath, ($taskSeal | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
foreach ($taskPayload in $taskPayloads) {
    if ((Get-FileHash -LiteralPath (Join-Path $taskOut $taskPayload.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPayload.sha256) { throw 'Post-seal payload mismatch' }
}
[pscustomobject][ordered]@{payload_count=$taskPayloads.Count; original_and_copy_hashes_verified=25; mismatches=0; tests_run=0; qualification_status='not_run'; manifest_sha256=(Get-FileHash -LiteralPath $taskSealPath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
