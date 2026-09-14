param([Parameter(Mandatory=$true)][string]$ExpectedInputsSha256)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$taskRoot = [IO.Path]::GetFullPath($PSScriptRoot)
if ($taskRoot -cne 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d2-dormant-invocation-proposal02') { throw 'Only the fixed reviewed proposal root is allowed' }
if ($ExpectedInputsSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Expected source manifest hash required' }
$inputPath = Join-Path $taskRoot 'QUALIFICATION-INPUTS.json'
if ((Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ExpectedInputsSha256) { throw 'Qualification input manifest changed' }
$inputs = Get-Content -LiteralPath $inputPath -Raw | ConvertFrom-Json -AsHashtable
$names = @('d2_adapter.py','test_d2_boundaries.py','D2-PROFILE.json','D1-RESULT.json','known-inventory.json','fixed-plan.json','EXPECTED-CASES.json','qualify_d2.py','run_fake23_01.ps1')
if (@($inputs.files.Keys).Count -ne 9 -or @(Compare-Object @($inputs.files.Keys) $names).Count -ne 0) { throw 'Exact nine text inputs required' }
foreach ($name in $names) {
    if ((Get-FileHash -LiteralPath (Join-Path $taskRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $inputs.files[$name]) { throw ('Input changed: '+$name) }
}
$admissionPath = Join-Path $taskRoot 'ROOT-FAKE23-ADMISSION.json'
$admission = Get-Content -LiteralPath $admissionPath -Raw | ConvertFrom-Json
if ($admission.root_reviewed -ne $true -or $admission.scope -cne 'D2_FAKE23_ONLY_NO_REAL_CONVERSION' -or
    $admission.run_id -cne 'fake23-01' -or $admission.input_manifest_sha256 -cne $ExpectedInputsSha256) { throw 'Exact root fake-only admission required' }
$runRoot = Join-Path $taskRoot 'fake23-01'
New-Item -ItemType Directory -Path $runRoot -ErrorAction Stop | Out-Null
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$providerNames = @(Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(API.?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION)' } | ForEach-Object { $_.Name })
foreach ($providerName in $providerNames) { Remove-Item -LiteralPath ('Env:'+$providerName) }
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_DATASETS_OFFLINE = '1'
$env:PYANNOTE_METRICS_ENABLED = '0'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD = '0'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$arguments = @('-I','-S','-B',(Join-Path $taskRoot 'qualify_d2.py'))
[ordered]@{scope='D2_FAKE23_ONLY_NO_REAL_CONVERSION';executable='C:\Python314\python.exe';arguments=$arguments;
    input_manifest_sha256=$ExpectedInputsSha256;input_hashes=$inputs.files;
    admission_sha256=(Get-FileHash -LiteralPath $admissionPath -Algorithm SHA256).Hash.ToLowerInvariant();
    forbidden_live_binding_set=$true;provider_environment_scrubbed=$true;removed_variable_names=$providerNames} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runRoot 'plan.json') -Encoding utf8
& 'C:\Python314\python.exe' @arguments 1> (Join-Path $runRoot 'stdout.json') 2> (Join-Path $runRoot 'stderr.log')
$rawExit = $global:LASTEXITCODE
$rawBytes = [Text.Encoding]::ASCII.GetBytes(([string]$rawExit)+"`n")
$rawStream = [IO.FileStream]::new((Join-Path $runRoot 'raw-native-exit.txt'),[IO.FileMode]::CreateNew,
    [IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
try { $rawStream.Write($rawBytes,0,$rawBytes.Length); $rawStream.Flush($true) } finally { $rawStream.Dispose() }
if ($null -eq $rawExit -or ($rawExit -isnot [int] -and $rawExit -isnot [long])) {
    [ordered]@{instrumentation_valid=$false;reason='Native exit missing or noninteger';raw_observation_persisted=$true} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'instrumentation-failure.json') -Encoding utf8
    throw 'Native exit missing or noninteger; raw observation retained'
}
[ordered]@{actual_native_exit=$rawExit;finished_utc=[DateTime]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'actual-exit.json') -Encoding utf8
$after = [ordered]@{}
foreach ($name in $names) { $after[$name]=(Get-FileHash -LiteralPath (Join-Path $taskRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant() }
$unchanged = @($names | Where-Object {$after[$_] -cne $inputs.files[$_]}).Count -eq 0
$manifestUnchanged = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExpectedInputsSha256
[ordered]@{input_hashes=$after;unchanged=$unchanged;manifest_unchanged=$manifestUnchanged} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runRoot 'after-inputs.json') -Encoding utf8
$outFile=Get-Item -LiteralPath (Join-Path $runRoot 'stdout.json')
$errFile=Get-Item -LiteralPath (Join-Path $runRoot 'stderr.log')
if ($outFile.Length -le 0 -or $outFile.Length -gt 65536 -or $errFile.Length -ne 0) { throw 'Unexpected bounded log/stderr outcome; raw exit retained' }
$observed=Get-Content -LiteralPath $outFile.FullName -Raw | ConvertFrom-Json
if ($observed.qualification_exit -ne $rawExit) { throw 'Native and qualification exit differ' }
$expected=Get-Content -LiteralPath (Join-Path $taskRoot 'EXPECTED-CASES.json') -Raw | ConvertFrom-Json
$orderedEqual=(@($observed.cases | ForEach-Object {$_.name}) | ConvertTo-Json -Compress) -ceq (@($expected) | ConvertTo-Json -Compress)
$counts=$observed.counts
$passed=$rawExit -eq 0 -and $unchanged -and $manifestUnchanged -and $orderedEqual -and
    $observed.guard_valid -eq $true -and $counts.passed -eq 23 -and $counts.failed -eq 0 -and
    $counts.errors -eq 0 -and $counts.skipped -eq 0 -and $counts.subtests -eq 0 -and $counts.tests_run -eq 23
[ordered]@{actual_native_exit=$rawExit;qualification_exit=$observed.qualification_exit;counts=$counts;
    exact_ordered_membership=$orderedEqual;inputs_unchanged=$unchanged;manifest_unchanged=$manifestUnchanged;
    guard_valid=$observed.guard_valid;fake23_passed=$passed;real_conversion_authorized=$false} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runRoot 'checked-result.json') -Encoding utf8
Get-Content -LiteralPath $outFile.FullName
if ($rawExit -ne 0) { exit $rawExit }
if (-not $passed) { throw 'Fake23 qualification not accepted; all raw results retained' }
exit 0
