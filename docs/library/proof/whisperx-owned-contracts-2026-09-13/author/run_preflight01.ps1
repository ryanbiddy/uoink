param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedManifestSha256)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$proposal = $PSScriptRoot
$manifestPath = Join-Path $proposal 'INPUT-HASHES.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedManifestSha256) { throw 'Admission manifest mismatch' }
$manifestRows = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$launch = Join-Path $proposal 'launch-qualification01'
if (Test-Path -LiteralPath $launch) { throw 'Refuse reused launch path' }
[IO.Directory]::CreateDirectory($launch) | Out-Null
function Write-DurableJson([string]$Path, $Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 12) + "`n")
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read, 4096, [IO.FileOptions]::WriteThrough)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Get-InputIdentities {
    $rows = foreach ($row in $manifestRows) {
        if ($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))') { throw 'Noncanonical manifest path' }
        $path = Join-Path $proposal $row.path
        $item = Get-Item -LiteralPath $path
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($item.Length -ne $row.bytes -or $hash -ne $row.sha256) { throw ('Source identity mismatch: ' + $row.path) }
        [ordered]@{path=$row.path; bytes=$item.Length; sha256=$hash}
    }
    return @($rows)
}
$before = Get-InputIdentities
$removedNames = @()
foreach ($entry in @(Get-ChildItem Env:)) {
    $name = $entry.Name.ToUpperInvariant()
    if ($name -match 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL' -or
        $name -match '^(ANTHROPIC_|OPENAI_|GOOGLE_API_|GEMINI_API_|XAI_|GROK_|CLAUDE_CODE_USE_)' -or
        $name -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','PYTHONPATH','PYTHONHOME')) {
        $removedNames += $entry.Name
        Remove-Item -LiteralPath ('Env:' + $entry.Name)
    }
}
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD = '0'
$env:PYANNOTE_METRICS_ENABLED = '0'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_DATASETS_OFFLINE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$python = 'C:\Python314\python.exe'
$arguments = @('-I','-S','-B',(Join-Path $proposal 'qualify.py'),'qualification01')
Write-DurableJson (Join-Path $launch 'plan.json') ([ordered]@{
    command=@($python)+$arguments; manifest_sha256=$ExpectedManifestSha256; input_hashes=$before;
    scrubbed_variable_names=@($removedNames|Sort-Object); startup_live_string_bound=$true;
    native_preference=$PSNativeCommandUseErrorActionPreference; started_utc=[DateTime]::UtcNow.ToString('o')
})
& $python @arguments 1> (Join-Path $launch 'stdout.log') 2> (Join-Path $launch 'stderr.log')
$actualNativeExit = $global:LASTEXITCODE
Write-DurableJson (Join-Path $launch 'actual-native-exit.json') ([ordered]@{
    actual_native_exit=$actualNativeExit;
    actual_native_exit_type=$(if ($null -eq $actualNativeExit) { $null } else { $actualNativeExit.GetType().FullName });
    observed_utc=[DateTime]::UtcNow.ToString('o')
})
# Actual native status is durable before any source/log/JSON postcheck.
$outerExit = 99
$postcheckError = $null
$after = @()
$logChecks = @()
try {
    if ($null -eq $actualNativeExit -or $actualNativeExit -isnot [int]) { throw 'Instrumentation: actual native exit is absent or not an integer' }
    $outerExit = $actualNativeExit
    foreach ($log in @('stdout.log','stderr.log')) {
        $logPath = Join-Path $launch $log
        $logItem = Get-Item -LiteralPath $logPath
        if ($logItem.PSIsContainer -or $logItem.Length -gt 262144) { throw 'Instrumentation: missing, non-file or oversized process log' }
        $logChecks += [ordered]@{path=$log; bytes=$logItem.Length; sha256=(Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()}
        if ($log -eq 'stderr.log' -and $logItem.Length -ne 0) { throw 'Instrumentation: expected empty stderr' }
    }
    $after = Get-InputIdentities
    if ((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -ne $ExpectedManifestSha256) { throw 'Manifest changed' }
    if ($actualNativeExit -eq 0) {
        $resultPath = Join-Path $proposal 'runs/qualification01/result.json'
        if ((Get-Item -LiteralPath $resultPath).Length -gt 524288) { throw 'Instrumentation: oversized child receipt' }
        $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
        if ($result.exit -ne 0 -or $result.status -ne 'PASS' -or $result.tests_run -ne 50 -or
            $result.passed -ne 50 -or $result.failed -ne 0 -or $result.errors -ne 0 -or $result.skipped -ne 0 -or
            $result.subtests -ne 0 -or @($result.subtest_observations).Count -ne 0 -or
            $result.guard.valid -ne $true -or $result.inputs_unchanged -ne $true) { throw 'Child/result disagreement' }
        $expectedIds = @(Get-Content -Raw -LiteralPath (Join-Path $proposal 'EXPECTED-CASES.json') | ConvertFrom-Json)
        if ($expectedIds.Count -ne 50 -or @($result.case_ids).Count -ne 50 -or @($result.expected_case_ids).Count -ne 50 -or
            @($result.observations).Count -ne 50) { throw 'Instrumentation: incomplete case membership' }
        for ($i = 0; $i -lt 50; $i++) {
            if ($result.case_ids[$i] -cne $expectedIds[$i] -or $result.expected_case_ids[$i] -cne $expectedIds[$i] -or
                $result.observations[$i].id -cne $expectedIds[$i] -or $result.observations[$i].status -cne 'passed') {
                throw 'Instrumentation: case order, identity or actual outcome mismatch'
            }
        }
    }
} catch {
    $outerExit = 99
    $postcheckError = $_.Exception.Message
}
Write-DurableJson (Join-Path $launch 'result.json') ([ordered]@{
    actual_native_exit=$actualNativeExit; intended_outer_exit=$outerExit;
    input_hashes_before=$before; input_hashes_after=$after;
    process_log_checks=$logChecks; instrumentation_verdict=$(if ($null -eq $postcheckError) { 'VALID' } else { 'FAILED' });
    postcheck_error=$postcheckError; finished_utc=[DateTime]::UtcNow.ToString('o')
})
exit $outerExit
