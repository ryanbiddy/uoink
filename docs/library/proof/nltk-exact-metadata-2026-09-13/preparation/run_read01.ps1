param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedManifestSha256)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$base = $PSScriptRoot
$manifestPath = Join-Path $base 'INPUT-HASHES.json'
if ((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedManifestSha256) { throw 'Admission manifest mismatch' }
$rows = @(Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json)
function Write-Durable([string]$Path, $Value) {
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($Value|ConvertTo-Json -Depth 12)+"`n")
    $stream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try {$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)} finally {$stream.Dispose()}
}
function Check-Inputs {
    $checked=@(foreach($row in $rows){
        if ($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))'){throw 'Invalid source path'}
        $path=Join-Path $base $row.path
        $file=Get-Item -LiteralPath $path
        $hash=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
        if($file.PSIsContainer -or $file.Length -ne $row.bytes -or $hash -cne $row.sha256){throw 'Text input mismatch'}
        [ordered]@{path=$row.path;bytes=$file.Length;sha256=$hash}
    })
    return $checked
}
$before=@(Check-Inputs)
$launch=Join-Path $base 'launch-read01'
if(Test-Path -LiteralPath $launch){throw 'Fresh launch required'}
[IO.Directory]::CreateDirectory($launch)|Out-Null
$removed=@()
foreach($entry in @(Get-ChildItem Env:)){
    $name=$entry.Name.ToUpperInvariant()
    if($name -match 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL' -or $name -match '^(ANTHROPIC_|OPENAI_|GOOGLE_API_|GEMINI_API_|XAI_|GROK_|CLAUDE_CODE_USE_)' -or $name -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','PYTHONPATH','PYTHONHOME')){
        $removed+=$entry.Name; Remove-Item -LiteralPath ('Env:'+$entry.Name)
    }
}
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$env:PYANNOTE_METRICS_ENABLED='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:HF_DATASETS_OFFLINE='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$python='C:\Python314\python.exe'
$arguments=@('-I','-S','-B',(Join-Path $base 'read_metadata.py'))
Write-Durable (Join-Path $launch 'plan.json') ([ordered]@{command=@($python)+$arguments;input_hashes=$before;manifest_sha256=$ExpectedManifestSha256;scrubbed_variable_names=@($removed|Sort-Object);native_preference=$PSNativeCommandUseErrorActionPreference;started_utc=[DateTime]::UtcNow.ToString('o')})
& $python @arguments 1> (Join-Path $launch 'stdout.log') 2> (Join-Path $launch 'stderr.log')
$actualNativeExit=$global:LASTEXITCODE
Write-Durable (Join-Path $launch 'actual-native-exit.json') ([ordered]@{actual_native_exit=$actualNativeExit;actual_native_exit_type=$(if($null -eq $actualNativeExit){$null}else{$actualNativeExit.GetType().FullName});observed_utc=[DateTime]::UtcNow.ToString('o')})
# Raw native status is durable before any throwing receipt/log/source postcheck.
$outerExit=99; $postcheckError=$null; $after=@(); $logs=@()
try {
    if($null -eq $actualNativeExit -or $actualNativeExit -isnot [int]){throw 'Instrumentation: missing/noninteger native exit'}
    $outerExit=$actualNativeExit
    foreach($name in @('stdout.log','stderr.log')){
        $path=Join-Path $launch $name; $file=Get-Item -LiteralPath $path
        if($file.PSIsContainer -or $file.Length -gt 131072){throw 'Instrumentation: oversized/non-file log'}
        $logs += [ordered]@{path=$name;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}
        if($name -eq 'stderr.log' -and $file.Length -ne 0){throw 'Instrumentation: expected empty stderr'}
    }
    $after=@(Check-Inputs)
    if((Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() -cne $ExpectedManifestSha256){throw 'Manifest changed'}
    $receiptPath=Join-Path $base 'results/read01/receipt.json'
    if((Get-Item -LiteralPath $receiptPath).Length -gt 131072){throw 'Instrumentation: oversized receipt'}
    $receipt=Get-Content -Raw -LiteralPath $receiptPath|ConvertFrom-Json
    if($receipt.exit -ne $actualNativeExit){throw 'Instrumentation: receipt/native disagreement'}
    if($actualNativeExit -eq 0){
        if($receipt.status -cne 'PASS' -or $receipt.artifact_verified_in_this_invocation -ne $true -or $receipt.artifact_origin -cne 'owned-built-wheel' -or $null -ne $receipt.artifact_url -or $receipt.public_local_release_record -ne $false -or $receipt.runtime_accepted -ne $false -or $receipt.wheel_member_imports -ne $false -or $receipt.model_execution -ne $false -or @($receipt.guard_violations).Count -ne 0){throw 'Instrumentation: success scope disagreement'}
        if($receipt.archive.members -ne 512 -or $receipt.archive.record_rows -ne 512 -or $receipt.archive.other_payload_record_hashes_recomputed -ne $false -or $receipt.exact_version_only_transformation -ne $true -or $receipt.fields.name -cne 'nltk' -or $receipt.fields.version -cne '3.10.3+uoink.pathsec1'){throw 'Instrumentation: metadata contract mismatch'}
        $metadataPath=Join-Path $base 'results/read01/nltk-local-METADATA.txt'
        if((Get-Item -LiteralPath $metadataPath).Length -ne $receipt.metadata_bytes -or (Get-FileHash -LiteralPath $metadataPath).Hash.ToLowerInvariant() -cne $receipt.metadata_sha256){throw 'Instrumentation: output hash/size mismatch'}
    } elseif($receipt.status -cne 'REFUSED'){throw 'Instrumentation: nonzero outcome mislabeled'}
} catch {$outerExit=99;$postcheckError=$_.Exception.Message}
Write-Durable (Join-Path $launch 'result.json') ([ordered]@{actual_native_exit=$actualNativeExit;intended_outer_exit=$outerExit;input_hashes_before=$before;input_hashes_after=$after;process_log_checks=$logs;instrumentation_verdict=$(if($null -eq $postcheckError){'VALID'}else{'FAILED'});postcheck_error=$postcheckError;finished_utc=[DateTime]::UtcNow.ToString('o')})
exit $outerExit
