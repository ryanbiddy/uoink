$ErrorActionPreference = 'Stop'
$proofRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$scratchRoot = Split-Path -Parent $proofRoot
$checkoutRoot = Split-Path -Parent $scratchRoot
$preparationRoot = Join-Path $scratchRoot 'b2-python313-reproduction-preparation01'
$firstManifestPath = Join-Path $checkoutRoot 'docs\library\proof\companion-b2-first-build-2026-09-13\SHA256.json'
$preparationHash = '0b1cb98b296f34965d8bcebe8a67755bb5315df1a3663b479e282da630346f4c'
$firstHash = 'a553c5264f19c08dd86d98fe56db4d9f19cee5bf471a8c1a79bf45f6c0cff9eb'
$bindings = [Collections.Generic.List[object]]::new()

function Get-Sha([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-TextFile([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576) { throw 'Documentary regular file within cap required' }
    if ($item.Name -ne '.gitattributes' -and $item.Extension.ToLowerInvariant() -notin @('.json','.md','.txt','.py','.ps1','.log')) { throw 'Non-documentary file refused' }
    $item
}
function Fresh-Text([string]$Relative, [string]$Text) {
    $target = [IO.Path]::GetFullPath((Join-Path $proofRoot $Relative))
    if (-not $target.StartsWith($proofRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output outside fresh proof' }
    if (Test-Path -LiteralPath $target) { throw 'Fresh output required' }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
    $stream = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $raw = [Text.UTF8Encoding]::new($false).GetBytes($Text); $stream.Write($raw, 0, $raw.Length) } finally { $stream.Dispose() }
}
function Copy-Evidence([string]$Source, [string]$Relative, [string]$ExpectedHash = '', [long]$ExpectedBytes = -1) {
    $item = Assert-TextFile $Source
    $before = Get-Sha $Source
    if ($ExpectedHash -and $before -ne $ExpectedHash) { throw ('Original evidence hash mismatch: ' + $Source) }
    if ($ExpectedBytes -ge 0 -and $item.Length -ne $ExpectedBytes) { throw 'Original evidence size mismatch' }
    $target = [IO.Path]::GetFullPath((Join-Path $proofRoot $Relative))
    if (-not $target.StartsWith($proofRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Copy outside fresh proof' }
    if (Test-Path -LiteralPath $target) { throw 'Copy destination already exists' }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
    [IO.File]::Copy($Source, $target, $false)
    $after = Get-Sha $Source
    $copied = Get-Sha $target
    if ($before -ne $after -or $before -ne $copied -or (Get-Item -LiteralPath $target).Length -ne $item.Length) { throw 'Evidence drift during copy' }
    $bindings.Add([ordered]@{ source=$Source; file=$Relative.Replace('\','/'); bytes=$item.Length; source_sha256_before=$before; source_sha256_after=$after; copied_sha256=$copied })
}

$existing = @(Get-ChildItem -LiteralPath $proofRoot -Force -File | ForEach-Object { $_.Name } | Sort-Object)
if (($existing -join '|') -ne 'BRIEF.md|seal-documentary.ps1|VERDICT.md' -or @(Get-ChildItem -LiteralPath $proofRoot -Force -Directory).Count) { throw 'Fresh three-file documentary preparation required' }
$preparationManifestPath = Join-Path $preparationRoot 'SHA256.json'
if ((Get-Sha $preparationManifestPath) -ne $preparationHash -or (Get-Sha $firstManifestPath) -ne $firstHash) { throw 'Pinned original seal mismatch' }
$preparation = Get-Content -Raw -LiteralPath $preparationManifestPath | ConvertFrom-Json
$first = Get-Content -Raw -LiteralPath $firstManifestPath | ConvertFrom-Json
if ($preparation.payload_count -ne 28 -or @($preparation.payloads).Count -ne 28 -or $first.payload_count -ne 132) { throw 'Original seal count mismatch' }
$names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($row in $preparation.payloads) {
    if ([IO.Path]::IsPathRooted($row.file) -or $row.file -match '(^|[/\\])\.\.([/\\]|$)|:' -or -not $names.Add($row.file)) { throw 'Invalid original manifest member' }
    $source = [IO.Path]::GetFullPath((Join-Path $preparationRoot $row.file))
    if (-not $source.StartsWith($preparationRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Original member escaped preparation' }
    Copy-Evidence $source ('preparation28/' + $row.file) $row.sha256 $row.bytes
}
Copy-Evidence $preparationManifestPath 'preparation28/SHA256.json' $preparationHash
Copy-Evidence $firstManifestPath 'references/first-build132-SHA256.json' $firstHash
Copy-Evidence (Join-Path $scratchRoot 'B2-PYTHON313-ROOT-DECISION-2026-09-13.md') 'ROOT-DECISION.md'
foreach ($name in @('copy-result.json','outer-exit.json')) { Copy-Evidence (Join-Path $scratchRoot ('b2-stdlib313-copy01/' + $name)) ('actual-copy01/' + $name) }
foreach ($name in @('build-result.json','console.log','launch-plan.json','launch-result.json','outer-exit.json','artifact/provenance.json')) { Copy-Evidence (Join-Path $scratchRoot ('b2-real-wheel-py313-01/' + $name)) ('actual-py313-01/' + $name) }
if ($bindings.Count -ne 39) { throw 'Unexpected documentary copy count' }

$copied = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-copy01/copy-result.json') | ConvertFrom-Json
$copyExit = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-copy01/outer-exit.json') | ConvertFrom-Json
$built = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-py313-01/build-result.json') | ConvertFrom-Json
$launch = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-py313-01/launch-result.json') | ConvertFrom-Json
$outer = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-py313-01/outer-exit.json') | ConvertFrom-Json
$provenance = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'actual-py313-01/artifact/provenance.json') | ConvertFrom-Json
$firstBuild = Get-Content -Raw -LiteralPath (Join-Path $proofRoot 'preparation28/first-run/build-result.json') | ConvertFrom-Json
if ($copied.status -ne 'COPIED_AND_BYTE_VERIFIED' -or $copied.exit -ne 0 -or $copyExit.actual_outer_exit -ne 0 -or $copied.exact_file_count -ne 34 -or @($copied.copied).Count -ne 33 -or $copied.private_runtime_launched) { throw 'Copy outcome mismatch' }
if ($built.status -ne 'BUILT_AND_BYTE_VERIFIED' -or $built.exit -ne 0 -or $launch.actual_child_exit -ne 0 -or $launch.launcher_return_code -ne 0 -or $outer.actual_outer_exit -ne 0 -or -not $launch.inputs_unchanged -or -not $launch.runtime_unchanged) { throw 'Build outcome mismatch' }
if (-not $built.guard.valid -or -not $built.guard.finder_installed_at_finish -or @($built.guard.violations).Count -or @($built.guard.preloaded_heavy).Count -or @($built.guard.postloaded_heavy).Count) { throw 'Guard outcome mismatch' }
if ($built.flags.isolated -ne 1 -or $built.flags.no_site -ne 1 -or $built.flags.dont_write_bytecode -ne 1 -or @($built.sys_path).Count -ne 2 -or $built.python -notlike '3.13.15 *' -or $built.private_runtime_file_count -ne 34 -or -not $built.private_runtime_verified) { throw 'Recorded startup mismatch' }
if ($built.member_count -ne 16 -or -not $built.manifest_and_record_verified -or -not $built.opaque_asset_and_license_unchanged -or $built.reproducibility_python313 -ne 'BYTE_IDENTICAL' -or @($provenance.output_members).Count -ne 16) { throw 'Member verification mismatch' }
if ($built.output.sha256 -ne 'd64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883' -or $built.output.size -ne 1387859 -or $built.output.sha256 -ne $firstBuild.output.sha256 -or $built.output.sha256 -ne $provenance.output.sha256 -or $built.model_execution -or $built.runtime_acceptance -or $built.release_ready) { throw 'Packaging scope or byte identity mismatch' }
$firstRow = @($first.payloads | Where-Object { $_.file -eq 'actual-py314-01/build-result.json' })
if ($firstRow.Count -ne 1 -or $firstRow[0].sha256 -ne (Get-Sha (Join-Path $proofRoot 'preparation28/first-run/build-result.json'))) { throw 'Historical first build reference mismatch' }

Fresh-Text '.gitattributes' "* -text`n"
Fresh-Text 'copy-bindings.json' (($bindings | ConvertTo-Json -Depth 6) + "`n")
Fresh-Text 'references/first-build132-reference.json' (([ordered]@{ source_manifest=$firstManifestPath; copied_manifest='first-build132-SHA256.json'; sha256=$firstHash; payload_count=132; scope='Historical manifest reference only; no first-build payload or wheel remeasurement'; first_build_receipt_cross_reference_verified=$true } | ConvertTo-Json -Depth 5) + "`n")
Fresh-Text 'verification.json' (([ordered]@{ created_utc=[DateTime]::UtcNow.ToString('o'); original_preparation_payloads_verified=28; original_preparation_manifest_sha256=$preparationHash; documentary_copies_verified=$bindings.Count; source_before_after_copy_hash_mismatches=0; copy_actual_exit=0; copy_outer_exit=0; build_actual_child_exit=0; build_launcher_exit=0; build_outer_exit=0; recorded_private_runtime_files=34; recorded_output_members=16; recorded_wheel_bytes=1387859; recorded_wheel_sha256=$built.output.sha256; receipt_consistency_verified=$true; wheels_or_runtime_binaries_read_here=$false; packaging_programs_tests_or_models_run_here=$false; first132_manifest_reference_only=$true; tracked_edits=$false } | ConvertTo-Json -Depth 5) + "`n")
$payloads = @(Get-ChildItem -LiteralPath $proofRoot -Recurse -Force -File | Sort-Object FullName | ForEach-Object { $item = Assert-TextFile $_.FullName; [ordered]@{ file=[IO.Path]::GetRelativePath($proofRoot,$item.FullName).Replace('\','/'); bytes=$item.Length; sha256=(Get-Sha $item.FullName) } })
if ($payloads.Count -ne 46) { throw 'Unexpected final payload count' }
Fresh-Text 'SHA256.json' (([ordered]@{ created_utc=[DateTime]::UtcNow.ToString('o'); payload_count=$payloads.Count; payloads=$payloads } | ConvertTo-Json -Depth 6) + "`n")
foreach ($row in $payloads) { if ((Get-Sha (Join-Path $proofRoot $row.file)) -ne $row.sha256 -or (Get-Item -LiteralPath (Join-Path $proofRoot $row.file)).Length -ne $row.bytes) { throw 'Final sealed payload drift' } }
[ordered]@{ status='DOCUMENTARY_SEAL_VERIFIED'; copies=$bindings.Count; payloads=$payloads.Count; preparation_payloads=28; manifest_sha256=(Get-Sha (Join-Path $proofRoot 'SHA256.json')); verdict_sha256=(Get-Sha (Join-Path $proofRoot 'VERDICT.md')); new_builds_or_tests=0 } | ConvertTo-Json -Depth 5
