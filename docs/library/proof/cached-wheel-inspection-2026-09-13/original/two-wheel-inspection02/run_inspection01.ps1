param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPreparationSha256)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$base=$PSScriptRoot
$manifestPath=Join-Path $base 'PREPARATION-HASHES.json'
if((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedPreparationSha256){throw 'Exact preparation admission required'}
$rows=@(Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json)
function Save-New([string]$Path,$Value) {
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 15)+"`n")
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}
function Check-Inputs {
    @(foreach($row in $rows){if($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))'){throw 'Invalid preparation path'};$path=Join-Path $base $row.path;$file=Get-Item -LiteralPath $path;$hash=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant();if($file.PSIsContainer -or $file.Length -ne $row.bytes -or $hash -cne $row.sha256){throw 'Preparation changed'};[ordered]@{path=$row.path;bytes=$file.Length;sha256=$hash}})
}
$before=@(Check-Inputs)
$launch=Join-Path $base 'launch-inspection01'
if((Test-Path -LiteralPath $launch) -or (Test-Path -LiteralPath (Join-Path $base 'inspection01.json'))){throw 'Fresh inspection and launcher receipts required'}
[IO.Directory]::CreateDirectory($launch)|Out-Null
$removed=@()
foreach($entry in @(Get-ChildItem Env:)) {
    $name=$entry.Name.ToUpperInvariant()
    if($name -match 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL' -or $name -match '^(ANTHROPIC_|OPENAI_|GOOGLE_API_|GEMINI_API_|XAI_|GROK_|CLAUDE_CODE_USE_)' -or $name -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','PYTHONPATH','PYTHONHOME')){$removed+=$entry.Name;Remove-Item -LiteralPath ('Env:'+$entry.Name)}
}
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:PYANNOTE_METRICS_ENABLED='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:HF_DATASETS_OFFLINE='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$python='C:\Python314\python.exe'
$arguments=@('-I','-S','-B',(Join-Path $base 'inspect_existing_wheels.py'),$ExpectedPreparationSha256)
Save-New (Join-Path $launch 'plan.json') ([ordered]@{command=@($python)+$arguments;preparation_sha256=$ExpectedPreparationSha256;input_hashes=$before;scrubbed_variable_names=@($removed|Sort-Object);native_error_promotion=$PSNativeCommandUseErrorActionPreference;started_utc=[DateTime]::UtcNow.ToString('o')})
& $python @arguments 1> (Join-Path $launch 'stdout.log') 2> (Join-Path $launch 'stderr.log')
$actualNativeExit=$global:LASTEXITCODE
Save-New (Join-Path $launch 'actual-native-exit.json') ([ordered]@{actual_native_exit=$actualNativeExit;type=$(if($null -eq $actualNativeExit){$null}else{$actualNativeExit.GetType().FullName});recorded_utc=[DateTime]::UtcNow.ToString('o')})
$outerExit=99;$errorText=$null;$after=@();$logs=@()
try {
    if($null -eq $actualNativeExit -or $actualNativeExit -isnot [int]){throw 'Missing/noninteger native exit'}
    $outerExit=$actualNativeExit
    foreach($name in @('stdout.log','stderr.log')){$path=Join-Path $launch $name;$file=Get-Item -LiteralPath $path;if($file.PSIsContainer -or $file.Length -gt 262144){throw 'Log bound/type'};if($name -eq 'stderr.log' -and $file.Length -ne 0){throw 'Unexpected stderr'};$logs+=[ordered]@{path=$name;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}}
    $after=@(Check-Inputs)
    if((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedPreparationSha256){throw 'Preparation manifest changed'}
    $receiptPath=Join-Path $base 'inspection01.json'
    if((Get-Item -LiteralPath $receiptPath).Length -gt 262144){throw 'Receipt bound'}
    $receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json
    if($receipt.exit -ne $actualNativeExit -or $receipt.preparation_sha256 -cne $ExpectedPreparationSha256 -or $receipt.guard.startup_binding -ne $true -or @($receipt.guard.violations).Count -ne 0 -or @($receipt.source_hashes_after).Count -ne $rows.Count){throw 'Receipt/native/source/guard mismatch'}
    if($actualNativeExit -eq 0){if($receipt.inspection_status -cne 'VALID' -or @($receipt.results).Count -ne 2 -or $null -ne $receipt.error){throw 'Invalid success receipt'}}
    elseif($actualNativeExit -eq 2){if($receipt.inspection_status -cne 'REFUSED' -or $null -eq $receipt.error){throw 'Refusal receipt mismatch'}}
    else {throw 'Unexpected native outcome'}
} catch {$outerExit=99;$errorText=$_.Exception.Message}
Save-New (Join-Path $launch 'result.json') ([ordered]@{actual_native_exit=$actualNativeExit;intended_outer_exit=$outerExit;instrumentation_verdict=$(if($null -eq $errorText){'VALID'}else{'FAILED'});postcheck_error=$errorText;input_hashes_before=$before;input_hashes_after=$after;process_logs=$logs;finished_utc=[DateTime]::UtcNow.ToString('o')})
exit $outerExit
