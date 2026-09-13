$ErrorActionPreference = 'Stop'
$proposal = $PSScriptRoot
$proof = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\whisperx-owned-contracts-proof01'
$mapPath = Join-Path $proposal 'SOURCE-MAP.json'
$mapHash = '6011f9430240033551b88b25115fd16acc9856dd6251033439a7ffc08de3c5a3'
$inputHash = '5602d0e46f91739c40799e0ce2592560274cc70c252421f856d3cf77133bcd9f'
function Assert-That($Condition, [string]$Reason) { if (-not $Condition) { throw $Reason } }
function Check-Chain([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    while ($null -ne $item) {
        Assert-That (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Linked/reparse source'
        if ($item -is [IO.DirectoryInfo]) { $item = $item.Parent } else { $item = $item.Directory }
    }
}
function Read-Bound($Row) {
    Assert-That ($Row.path -notmatch '(^/|\\|:|(^|/)\.\.?(/|$))') 'Noncanonical proof path'
    Check-Chain $Row.source
    $before = Get-Item -LiteralPath $Row.source
    Assert-That (-not $before.PSIsContainer -and $before.Length -eq $Row.bytes -and $before.Length -le 262144) 'Source type/size'
    $data = [IO.File]::ReadAllBytes($Row.source)
    $after = Get-Item -LiteralPath $Row.source
    $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($data)).ToLowerInvariant()
    Assert-That ($data.Length -eq $Row.bytes -and $digest -ceq $Row.sha256 -and
        $before.Length -eq $after.Length -and $before.LastWriteTimeUtc.Ticks -eq $after.LastWriteTimeUtc.Ticks) 'Source changed or hash mismatch'
    return ,$data
}
function Save-New([string]$Path, [byte[]]$Bytes) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    $stream = [IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try { $stream.Write($Bytes,0,$Bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Encode-Json($Value) { return ,([Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 15) + "`n")) }
Assert-That ((Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $mapHash) 'Source map identity'
$map = Get-Content -LiteralPath $mapPath -Raw | ConvertFrom-Json
Assert-That ($map.payload_count -eq 207 -and $map.files.Count -eq 207) 'Exact source membership count'
$payloads = @{}
[long]$total = 0
foreach ($root in $map.source_roots) {
    Check-Chain $root.directory
    $actual = @(Get-ChildItem -LiteralPath $root.directory -File -Recurse | ForEach-Object { $_.FullName } | Sort-Object -CaseSensitive)
    $expected = @($map.files | Where-Object group -CEQ $root.group | ForEach-Object source | Sort-Object -CaseSensitive)
    Assert-That (($actual | ConvertTo-Json -Compress) -ceq ($expected | ConvertTo-Json -Compress)) 'Source membership changed'
}
foreach ($row in $map.files) {
    Assert-That (-not $payloads.ContainsKey($row.path)) 'Duplicate map path'
    $sourceRoot = @($map.source_roots | Where-Object group -CEQ $row.group)
    Assert-That ($sourceRoot.Count -eq 1 -and $row.path.StartsWith($row.group + '/',[StringComparison]::Ordinal)) 'Source group mismatch'
    $relative = $row.path.Substring($row.group.Length + 1)
    $expectedSource = Join-Path $sourceRoot[0].directory $relative
    Assert-That ([IO.Path]::GetFullPath($row.source) -ceq [IO.Path]::GetFullPath($expectedSource)) 'Source path mismatch'
    $raw = Read-Bound $row
    $total += $raw.Length
    Assert-That ($total -le 4194304) 'Aggregate source byte bound'
    $payloads[$row.path] = $raw
}
function Json-Source([string]$Name) { return ([Text.Encoding]::UTF8.GetString($payloads[$Name]) | ConvertFrom-Json) }
function Hash-Source([string]$Name) { return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($payloads[$Name])).ToLowerInvariant() }
foreach ($group in @('author','root')) {
    Assert-That ((Hash-Source ($group + '/INPUT-HASHES.json')) -ceq $inputHash) 'Original input manifest hash'
    $rows = @(Json-Source ($group + '/INPUT-HASHES.json'))
    Assert-That ($rows.Count -eq 46) 'Original input manifest count'
    foreach ($row in $rows) {
        $key = $group + '/' + $row.path
        Assert-That ($payloads.ContainsKey($key) -and $payloads[$key].Length -eq $row.bytes -and (Hash-Source $key) -ceq $row.sha256) 'Retained input manifest mismatch'
    }
}
foreach ($row in @(Json-Source 'derivative/FINAL-SOURCE-HASHES.json')) {
    $key = 'derivative/' + $row.path
    Assert-That ($payloads.ContainsKey($key) -and $payloads[$key].Length -eq $row.bytes -and (Hash-Source $key) -ceq $row.sha256) 'Retained derivative manifest mismatch'
}
$expectedIds = @(Json-Source 'author/EXPECTED-CASES.json')
$summary = @()
$results = @{}
foreach ($group in @('author','root')) {
    $result = Json-Source ($group + '/runs/qualification01/result.json')
    $native = Json-Source ($group + '/launch-qualification01/actual-native-exit.json')
    $launch = Json-Source ($group + '/launch-qualification01/result.json')
    $toolPath = if ($group -eq 'author') { 'author/actual-outer-tool-result-host02.json' } else { 'root/ACTUAL-QUALIFICATION-TOOL.json' }
    $outer = Json-Source $toolPath
    Assert-That ($result.status -ceq 'PASS' -and $result.exit -eq 0 -and $result.tests_run -eq 50 -and $result.passed -eq 50 -and
        $result.failed -eq 0 -and $result.errors -eq 0 -and $result.skipped -eq 0 -and $result.subtests -eq 0 -and
        $native.actual_native_exit -eq 0 -and $native.actual_native_exit_type -ceq 'System.Int32' -and
        $launch.actual_native_exit -eq 0 -and $launch.intended_outer_exit -eq 0 -and $launch.instrumentation_verdict -ceq 'VALID' -and
        $null -eq $launch.postcheck_error -and $outer.exit_code -eq 0) 'Measured result/exit mismatch'
    Assert-That ($result.guard.valid -eq $true -and $result.guard.violations.Count -eq 0 -and
        $result.guard.preloaded_heavy.Count -eq 0 -and $result.guard.postloaded_heavy.Count -eq 0 -and
        $result.guard.metadata_wrappers_installed -eq $true -and $result.guard.source_identities_unchanged -eq $true -and
        $result.inputs_unchanged -eq $true -and $payloads[$group + '/launch-qualification01/stderr.log'].Length -eq 0) 'Guard/input/stderr mismatch'
    Assert-That (($result.guard.source_identities_before | ConvertTo-Json -Depth 10 -Compress) -ceq
        ($result.guard.source_identities_after | ConvertTo-Json -Depth 10 -Compress)) 'Actual before/after metadata differs'
    $inputRows = @(Json-Source ($group + '/INPUT-HASHES.json'))
    $inputRows += [pscustomobject]@{path='INPUT-HASHES.json'; sha256=$inputHash}
    Assert-That (@($result.input_hashes_before.PSObject.Properties).Count -eq 47 -and
        @($result.input_hashes_after.PSObject.Properties).Count -eq 47) 'Incomplete raw input hash sets'
    foreach ($row in $inputRows) {
        Assert-That ($result.input_hashes_before.PSObject.Properties[$row.path].Value -ceq $row.sha256 -and
            $result.input_hashes_after.PSObject.Properties[$row.path].Value -ceq $row.sha256) 'Raw input hash disagrees with manifest'
    }
    foreach ($log in @('stdout.log','stderr.log')) {
        $logRow = @($launch.process_log_checks | Where-Object path -CEQ $log)
        $key = $group + '/launch-qualification01/' + $log
        Assert-That ($logRow.Count -eq 1 -and $logRow[0].bytes -eq $payloads[$key].Length -and
            $logRow[0].sha256 -ceq (Hash-Source $key)) 'Raw log differs from launch receipt'
    }
    Assert-That ($result.case_ids.Count -eq 50 -and $result.observations.Count -eq 50 -and $expectedIds.Count -eq 50) 'Case membership count'
    for ($index=0; $index -lt 50; $index++) {
        Assert-That ($result.case_ids[$index] -ceq $expectedIds[$index] -and $result.observations[$index].id -ceq $expectedIds[$index] -and
            $result.observations[$index].status -ceq 'passed') 'Case order/outcome mismatch'
    }
    Assert-That ($result.optional_diagnostic.status -ceq 'UNACCEPTED_OPTIONAL_API_DEFECT' -and
        $result.optional_diagnostic.type -ceq 'IndexError') 'Optional diagnostic changed'
    $results[$group] = $result
    $summary += [ordered]@{run=$group; passed=50; failed=0; errors=0; skipped=0; subtests=0;
        harness_seconds=$result.elapsed_seconds; actual_outer_seconds=$outer.wall_time_seconds;
        child_exit=0; native_exit=0; actual_outer_exit=0; result_sha256=(Hash-Source ($group + '/runs/qualification01/result.json'))}
}
Assert-That (($results.author.observations | ConvertTo-Json -Depth 10 -Compress) -ceq
    ($results.root.observations | ConvertTo-Json -Depth 10 -Compress)) 'Complete ordered observations differ'
$failedHost = Json-Source 'author/actual-outer-tool-result.json'
Assert-That ($failedHost.exit_code -eq 1 -and $failedHost.chunk_id -ceq 'bc920e') 'Historical host failure changed'
Assert-That (-not (Test-Path -LiteralPath $proof)) 'Refuse reused proof directory'
[IO.Directory]::CreateDirectory($proof) | Out-Null
foreach ($row in $map.files) {
    $path = Join-Path $proof $row.path
    Save-New $path $payloads[$row.path]
    Assert-That ((Get-Item -LiteralPath $path).Length -eq $row.bytes -and
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Copied bytes mismatch'
}
foreach ($name in @('BRIEF.md','VERDICT.md','SOURCE-MAP.json','seal.ps1','verify_proof.ps1',
    'PATH-NORMALIZATION-REPAIR.md','drafts/path-normalization01/seal.ps1','drafts/path-normalization01/verify_proof.ps1')) {
    Save-New (Join-Path $proof $name) ([IO.File]::ReadAllBytes((Join-Path $proposal $name)))
}
Save-New (Join-Path $proof '.gitattributes') ([Text.Encoding]::ASCII.GetBytes("* -text`n"))
$verification = [ordered]@{status='DOCUMENTARY_VERIFIED'; source_payload_count=207; source_bytes=$total;
    original_input_manifests_verified=2; derivative_source_manifest_verified=$true; complete_observations_equal=$true;
    first_host_attempt=[ordered]@{tool='bc920e'; actual_exit=1; cases_run=0}; runs=$summary;
    tests_rerun=$false; wheel_built_or_imported=$false; model_or_native_runtime_executed=$false;
    finished_utc=[DateTime]::UtcNow.ToString('o')}
Save-New (Join-Path $proof 'VERIFICATION.json') (Encode-Json $verification)
# Check every original again after copying; a changed source leaves an unsealed
# partial proof. The preserved original input manifests are never rewritten.
foreach ($row in $map.files) { $null = Read-Bound $row }
$manifest = @()
foreach ($file in @(Get-ChildItem -LiteralPath $proof -File -Recurse)) {
    $name = [IO.Path]::GetRelativePath($proof,$file.FullName).Replace([char]92,[char]47)
    $manifest += [ordered]@{path=$name; bytes=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest = @($manifest | Sort-Object { $_.path } -CaseSensitive)
Save-New (Join-Path $proof 'SHA256.json') (Encode-Json $manifest)
$verification | ConvertTo-Json -Depth 8
