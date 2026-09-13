$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$proposal = Join-Path $taskRoot '_scratch\torch213-vad-source-proposal01'
$review = Join-Path $taskRoot '_scratch\torch213-vad-compatibility01'
$author = Join-Path $proposal 'collector-preflight01'
$independent = Join-Path $taskRoot '_scratch\astra-torch-collector-synthetic01'
$output = Join-Path $proposal 'INDEPENDENT-CASE-COMPARISON02.json'
$sumOutput = Join-Path $review 'SOURCE-BYTE-SUM02.json'
if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $sumOutput)) { throw 'Fresh reporting outputs required' }
function Read-Json([string]$path) { Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
function Hash-File([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$a = Read-Json (Join-Path $author 'stdout.json')
$b = Read-Json (Join-Path $independent 'stdout.json')
$ae = Read-Json (Join-Path $author 'exit.json')
$be = Read-Json (Join-Path $independent 'exit.json')
$ao = Read-Json (Join-Path $author 'outer-tool-result.json')
$bo = Read-Json (Join-Path $independent 'outer-tool-result.json')
foreach ($run in @($a,$b)) {
    if ($run.passed -ne 40 -or $run.failed -ne 0 -or $run.qualification_exit -ne 0 -or $run.startup_binding -ne $true -or @($run.guard_denials).Count -ne 0 -or $run.network_or_real_path_calls -ne 0) { throw 'Qualification facts mismatch' }
    if (@($run.cases).Count -ne 40 -or @($run.cases.name | Sort-Object -Unique).Count -ne 40 -or @($run.cases | Where-Object status -ne 'passed').Count -ne 0) { throw 'Case membership mismatch' }
}
if (($a.cases|ConvertTo-Json -Depth 8 -Compress) -cne ($b.cases|ConvertTo-Json -Depth 8 -Compress)) { throw 'Case records differ' }
if ($a.collector_sha256 -cne $b.collector_sha256 -or $a.harness_sha256 -cne $b.harness_sha256) { throw 'Executed source mismatch' }
foreach ($receipt in @($ae,$be)) { if ($receipt.native_exit -ne 0 -or $receipt.inputs_unchanged -ne $true -or $receipt.startup_binding_set -ne $true) { throw 'Native qualification mismatch' } }
if ($ao.exit_code -ne 0 -or $bo.actual_outer_tool_exit -ne 0) { throw 'Actual outer qualification mismatch' }
$inputChecks = @()
foreach ($runDir in @($author,$independent)) {
    $plan = Read-Json (Join-Path $runDir 'plan.json')
    if (@($plan.inputs).Count -ne 8) { throw 'Unexpected launch input count' }
    foreach ($item in $plan.inputs) {
        $copyHash = Hash-File (Join-Path $runDir $item.name)
        $originalHash = Hash-File $item.source
        if ($copyHash -cne $item.sha256 -or $originalHash -cne $item.sha256) { throw 'Historical launch input changed' }
        $inputChecks += @{run=$runDir;name=$item.name;sha256=$item.sha256;copy_and_original_match=$true}
    }
    if ((Get-Item -LiteralPath (Join-Path $runDir 'stderr.log')).Length -ne 0) { throw 'Unexpected stderr' }
}
$result = [ordered]@{
    scope='Read-only receipt comparison; no test rerun'; historical_comparison01='COMPARISON-REPORT-REPAIR01.md';
    exact_ordered_case_records_equal=$true; distinct_cases=40; author_passed=40;author_failed=0;independent_passed=40;independent_failed=0;
    author_elapsed_seconds=$a.elapsed_seconds; independent_elapsed_seconds=$b.elapsed_seconds;
    author_stdout_sha256=(Hash-File (Join-Path $author 'stdout.json'));independent_stdout_sha256=(Hash-File (Join-Path $independent 'stdout.json'));
    native_exits=@($ae.native_exit,$be.native_exit); actual_outer_exits=@($ao.exit_code,$bo.actual_outer_tool_exit);
    independent_outer_field='actual_outer_tool_exit'; collector_sha256=$a.collector_sha256;harness_sha256=$a.harness_sha256;
    input_checks=$inputChecks;cases=$a.cases
}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $output -Encoding utf8
$bindings = Read-Json (Join-Path $review 'TARGET-SOURCE-BINDINGS.json')
$sources = @($bindings.bindings | Where-Object kind -eq 'source')
$apis = @($bindings.bindings | Where-Object kind -eq 'api')
if ($sources.Count -ne 19 -or $apis.Count -ne 2) { throw 'Unexpected response membership' }
$sourceBytes = ($sources|Measure-Object -Property bytes -Sum).Sum
$apiBytes = ($apis|Measure-Object -Property bytes -Sum).Sum
if ($sourceBytes -ne 1044471 -or $apiBytes -ne 6257 -or ($sourceBytes+$apiBytes) -ne 1050728) { throw 'Response byte sum mismatch' }
foreach ($record in $bindings.bindings) {
    if ((Hash-File $record.saved_path) -cne $record.sha256 -or (Get-Item -LiteralPath $record.saved_path).Length -ne $record.bytes) { throw 'Response body changed' }
}
[ordered]@{scope='Documentary sum of unchanged retained response records';original_binding_sha256=(Hash-File (Join-Path $review 'TARGET-SOURCE-BINDINGS.json'));original_source_bytes_was_null=($null -eq $bindings.source_bytes);source_files=19;source_bytes=$sourceBytes;api_files=2;api_bytes=$apiBytes;total_body_bytes=($sourceBytes+$apiBytes);all_individual_body_hashes_and_lengths_match=$true} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $sumOutput -Encoding utf8
[ordered]@{reporting_exit=0;exact_cases=40;input_checks=$inputChecks.Count;source_bytes=$sourceBytes;comparison_sha256=(Hash-File $output);sum_sha256=(Hash-File $sumOutput)} | ConvertTo-Json
