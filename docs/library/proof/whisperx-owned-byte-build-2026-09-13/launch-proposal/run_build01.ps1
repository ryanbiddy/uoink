param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPreparationSha256)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$proposal = $PSScriptRoot
$source = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\whisperx-owned-builder-proposal01'
$runtime = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\b2-stdlib313-runtime01'
$inputHash = '5602d0e46f91739c40799e0ce2592560274cc70c252421f856d3cf77133bcd9f'
$runtimePlanHash = '8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b'
$instrumentPath = Join-Path $proposal 'INSTRUMENT-HASHES.json'
$inputPath = Join-Path $source 'INPUT-HASHES.json'
$runtimePlanPath = Join-Path $proposal 'runtime-copy-plan.json'
$launch = Join-Path $proposal 'launch-build01'
$run = Join-Path $source 'runs/build01'
function Assert-That($Condition,[string]$Reason) { if (-not $Condition) { throw $Reason } }
function Save-Json([string]$Path,$Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 12) + "`n")
    $stream = [IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Check-Chain([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    while ($null -ne $item) {
        Assert-That (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Linked/reparse path'
        if ($item -is [IO.DirectoryInfo]) { $item = $item.Parent } else { $item = $item.Directory }
    }
}
Assert-That ((Hash $instrumentPath) -ceq $ExpectedPreparationSha256) 'Instrument manifest mismatch'
Assert-That ((Hash $inputPath) -ceq $inputHash) 'Original source manifest mismatch'
Assert-That ((Hash $runtimePlanPath) -ceq $runtimePlanHash) 'Runtime plan mismatch'
$instruments = @(Get-Content -LiteralPath $instrumentPath -Raw | ConvertFrom-Json)
$inputs = @(Get-Content -LiteralPath $inputPath -Raw | ConvertFrom-Json)
$runtimePlan = Get-Content -LiteralPath $runtimePlanPath -Raw | ConvertFrom-Json
$runtimeRows = @($runtimePlan.files) + @($runtimePlan.private_pth)
Assert-That ($inputs.Count -eq 46 -and $runtimeRows.Count -eq 34) 'Exact input/runtime counts required'
function Check-Rows([string]$Root,$Rows,[string]$Field) {
    $result = @()
    foreach ($row in $Rows) {
        $relative = $row.$Field
        Assert-That ($relative -notmatch '(^/|\\|:|(^|/)\.\.?(/|$))') 'Noncanonical input path'
        $path = Join-Path $Root $relative
        Check-Chain $path
        $item = Get-Item -LiteralPath $path
        $sha = Hash $path
        Assert-That (-not $item.PSIsContainer -and $item.Length -eq $row.bytes -and $sha -ceq $row.sha256) 'Fixed file identity mismatch'
        $result += [ordered]@{path=$relative; bytes=$item.Length; sha256=$sha}
    }
    return $result
}
function Snapshot {
    Assert-That ((Hash $instrumentPath) -ceq $ExpectedPreparationSha256 -and (Hash $inputPath) -ceq $inputHash -and
        (Hash $runtimePlanPath) -ceq $runtimePlanHash) 'Manifest changed'
    $runtimeFiles = @(Get-ChildItem -LiteralPath $runtime -Force)
    Assert-That ($runtimeFiles.Count -eq 34 -and @($runtimeFiles | Where-Object PSIsContainer).Count -eq 0) 'Private runtime membership changed'
    return [ordered]@{instruments=@(Check-Rows $proposal $instruments 'path'); inputs=@(Check-Rows $source $inputs 'path'); runtime=@(Check-Rows $runtime $runtimeRows 'filename')}
}
$before = Snapshot
Assert-That (-not (Test-Path -LiteralPath $launch) -and -not (Test-Path -LiteralPath $run)) 'Refuse reused build/launch directory'
[IO.Directory]::CreateDirectory($launch) | Out-Null
$scrubbed = @()
foreach ($entry in @(Get-ChildItem Env:)) {
    $name = $entry.Name.ToUpperInvariant()
    if ($name -match 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL' -or
        $name -match '^(ANTHROPIC_|OPENAI_|GOOGLE_API_|GEMINI_API_|XAI_|GROK_|CLAUDE_CODE_USE_)' -or
        $name -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','PYTHONPATH','PYTHONHOME')) {
        $scrubbed += $entry.Name
        Remove-Item -LiteralPath ('Env:' + $entry.Name)
    }
}
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD = '0'
$env:PYANNOTE_METRICS_ENABLED = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_DATASETS_OFFLINE = '1'
$python = Join-Path $runtime 'python.exe'
$child = Join-Path $proposal 'guarded_build.py'
Save-Json (Join-Path $launch 'plan.json') ([ordered]@{scope='One exact text-only wheel build and independent verification';
    preparation_sha256=$ExpectedPreparationSha256; input_manifest_sha256=$inputHash; runtime_plan_sha256=$runtimePlanHash;
    before=$before; scrubbed_variable_names=$scrubbed; modes=@('build','verify'); startup_binding=$true;
    command_prefix=@($python,'-I','-S','-B',$child); native_error_preference=$PSNativeCommandUseErrorActionPreference;
    started_utc=[DateTime]::UtcNow.ToString('o')})
$outerExit = 99
$failure = $null
$after = $null
$phases = @()
try {
    foreach ($mode in @('build','verify')) {
        & $python -I -S -B $child $mode 1> (Join-Path $launch ($mode + '-stdout.log')) 2> (Join-Path $launch ($mode + '-stderr.log'))
        $native = $global:LASTEXITCODE
        Save-Json (Join-Path $launch ($mode + '-actual-native-exit.json')) ([ordered]@{
            mode=$mode; actual_native_exit=$native; native_type=$(if ($null -eq $native) { $null } else { $native.GetType().FullName });
            observed_utc=[DateTime]::UtcNow.ToString('o')})
        # Actual return is durable before all throwing postchecks.
        Assert-That ($null -ne $native -and $native -is [int]) 'Instrumentation: no integer native exit'
        $outerExit = $native
        $logs = @()
        foreach ($kind in @('stdout','stderr')) {
            $path = Join-Path $launch ($mode + '-' + $kind + '.log')
            $item = Get-Item -LiteralPath $path
            Assert-That (-not $item.PSIsContainer -and $item.Length -le 262144) 'Instrumentation: log bound'
            Assert-That ($kind -ne 'stderr' -or $item.Length -eq 0) 'Instrumentation: nonempty stderr'
            $logs += [ordered]@{kind=$kind; bytes=$item.Length; sha256=(Hash $path)}
        }
        $phases += [ordered]@{mode=$mode; actual_native_exit=$native; logs=$logs}
        if ($native -ne 0) { break }
        $guardPath = Join-Path $launch ($mode + '-guard.json')
        Assert-That ((Get-Item -LiteralPath $guardPath).Length -le 262144) 'Instrumentation: guard receipt bound'
        $guard = Get-Content -LiteralPath $guardPath -Raw | ConvertFrom-Json
        Assert-That ($guard.exit -eq 0 -and $guard.guard_valid -eq $true -and $guard.violations.Count -eq 0 -and
            $guard.preloaded_heavy.Count -eq 0 -and $guard.postloaded_heavy.Count -eq 0 -and
            $guard.metadata_wrappers_installed -eq $true -and $guard.startup_binding -eq $true) 'Instrumentation: guard disagreement'
        $resultName = if ($mode -eq 'build') { 'result.json' } else { 'independent-verification.json' }
        $resultPath = Join-Path $run $resultName
        Assert-That ((Get-Item -LiteralPath $resultPath).Length -le 262144) 'Instrumentation: result bound'
        $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
        Assert-That ($result.exit -eq 0 -and $result.members -eq 22 -and $result.inputs_unchanged -eq $true) 'Child/result disagreement'
        $wheel = Join-Path $run 'whisperx-3.8.6+uoink.owned1-py3-none-any.whl'
        Assert-That ((Get-Item -LiteralPath $wheel).Length -eq $result.bytes -and $result.bytes -le 1048576 -and
            (Hash $wheel) -ceq $result.sha256) 'Generated wheel identity mismatch'
        if ($mode -eq 'verify') {
            Assert-That ($result.record_rows -eq 22 -and $result.all_payloads_verified -eq $true -and
                $result.complete_byte_layout_verified -eq $true) 'Incomplete independent verification'
        }
        $afterPhase = Snapshot
        Assert-That (($afterPhase | ConvertTo-Json -Depth 10 -Compress) -ceq ($before | ConvertTo-Json -Depth 10 -Compress)) 'Source/runtime changed'
    }
    $after = Snapshot
    Assert-That (($after | ConvertTo-Json -Depth 10 -Compress) -ceq ($before | ConvertTo-Json -Depth 10 -Compress)) 'Final identity mismatch'
    if ($outerExit -eq 0) { Assert-That ($phases.Count -eq 2) 'Incomplete native phases' }
} catch {
    $failure = $_.Exception.Message
    $outerExit = 99
}
Save-Json (Join-Path $launch 'result.json') ([ordered]@{status=$(if ($outerExit -eq 0) { 'BYTE_BUILD_VERIFIED' } else { 'FAILED' });
    intended_outer_exit=$outerExit; phases=$phases; instrumentation_error=$failure; before=$before; after=$after;
    wheel_imported_or_installed=$false; model_runtime_executed=$false; release_accepted=$false;
    finished_utc=[DateTime]::UtcNow.ToString('o')})
exit $outerExit
