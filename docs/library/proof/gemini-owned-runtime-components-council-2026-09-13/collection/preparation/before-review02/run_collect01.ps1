$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$proposal = Join-Path $taskRoot '_scratch\owned-runtime-council-collector-proposal01'
$launchRoot = Join-Path $taskRoot '_scratch\gemini-owned-runtime-components-council-collect01-launch'
if (Test-Path -LiteralPath $launchRoot) { throw 'Fresh launch directory already exists' }
$sourcePath = Join-Path $proposal 'collect.py'
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
$pinsPath = Join-Path $proposal 'PINS.json'
$pins = Get-Content -LiteralPath $pinsPath -Raw | ConvertFrom-Json
foreach ($pin in $pins.files) {
    $p = Join-Path $proposal $pin.path
    if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin.sha256) { throw "Input hash mismatch: $($pin.path)" }
}
$savedEnv = @{}
$scrubNames = @(Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(API_KEY|TOKEN|SECRET|PASSWORD|PROXY|^ANTHROPIC_|^OPENAI_|^GOOGLE_|^GEMINI_|^GROK_|^XAI_)' } | ForEach-Object Name)
$names = @($scrubNames + @('IG_FORBIDDEN_LIVE') | Sort-Object -Unique)
foreach ($name in $names) { $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
New-Item -ItemType Directory -Path $launchRoot | Out-Null
$started = [DateTimeOffset]::UtcNow.ToString('o')
try {
    foreach ($name in $scrubNames) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
    $env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
    $plan = [ordered]@{ source = $sourcePath; source_sha256 = $sourceHash; pins_sha256 = (Get-FileHash -LiteralPath $pinsPath -Algorithm SHA256).Hash.ToLowerInvariant(); started_utc = $started; interpreter = 'C:\Python314\python.exe'; argv = @('-I','-S','-B',$sourcePath,'--collect'); startup_forbidden_binding_set = ($env:IG_FORBIDDEN_LIVE -ceq 'C:\Users\hello\AppData\Local\Uoink\index.db'); scrubbed_variable_names = $scrubNames; general_os_sandbox_claim = $false }
    $plan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $launchRoot 'plan.json') -Encoding utf8NoBOM
    $PSNativeCommandUseErrorActionPreference = $false
    & 'C:\Python314\python.exe' -I -S -B $sourcePath --collect 1> (Join-Path $launchRoot 'stdout.json') 2> (Join-Path $launchRoot 'stderr.log')
    $nativeExit = $global:LASTEXITCODE
    $finished = [DateTimeOffset]::UtcNow.ToString('o')
    $after = @($pins.files | ForEach-Object { [ordered]@{ path = $_.path; expected_sha256 = $_.sha256; actual_sha256 = (Get-FileHash -LiteralPath (Join-Path $proposal $_.path) -Algorithm SHA256).Hash.ToLowerInvariant() } })
    $unchanged = @($after | Where-Object { $_.expected_sha256 -cne $_.actual_sha256 }).Count -eq 0
    $receipt = [ordered]@{ actual_native_exit = $nativeExit; finished_utc = $finished; inputs_unchanged = $unchanged; input_checks = $after; stdout_sha256 = (Get-FileHash -LiteralPath (Join-Path $launchRoot 'stdout.json') -Algorithm SHA256).Hash.ToLowerInvariant(); stderr_sha256 = (Get-FileHash -LiteralPath (Join-Path $launchRoot 'stderr.log') -Algorithm SHA256).Hash.ToLowerInvariant(); stderr_bytes = (Get-Item -LiteralPath (Join-Path $launchRoot 'stderr.log')).Length }
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $launchRoot 'exit.json') -Encoding utf8NoBOM
    if ($null -eq $nativeExit -or -not $unchanged) { throw 'Native exit unavailable or inputs changed; raw results retained' }
    Get-Content -LiteralPath (Join-Path $launchRoot 'stdout.json') -Raw | Write-Output
    if ($nativeExit -ne 0) { Get-Content -LiteralPath (Join-Path $launchRoot 'stderr.log') -Raw | Write-Output }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
}
exit $nativeExit
