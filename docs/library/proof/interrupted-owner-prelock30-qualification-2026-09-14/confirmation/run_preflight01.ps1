$ErrorActionPreference = 'Stop'
$taskSource = $PSScriptRoot
$taskRun = Join-Path $taskSource 'prelock-retirement-confirmation03'
$taskPython = 'C:\Python314\python.exe'
$taskNative = $null
$taskRunStarted = [DateTimeOffset]::UtcNow.ToString('o')
$taskClock = [Diagnostics.Stopwatch]::StartNew()

function Write-TaskJson([string]$taskPath, $taskValue) {
    $taskBytes = [Text.UTF8Encoding]::new($false).GetBytes(($taskValue | ConvertTo-Json -Depth 24) + "`n")
    $taskStream = [IO.FileStream]::new($taskPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $taskStream.Write($taskBytes); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
}
function Get-TaskBinding([string]$taskPath) {
    $taskItem = Get-Item -LiteralPath $taskPath -ErrorAction Stop
    if ($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Plain pinned input required' }
    return [ordered]@{ bytes = $taskItem.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $taskPath).Hash.ToLowerInvariant() }
}

if (Test-Path -LiteralPath $taskRun) { throw 'Fresh prelock-retirement-confirmation03 output required' }
$taskPinsPath = Join-Path $taskSource 'PINS.json'
$taskAdmissionPath = Join-Path $taskSource 'ROOT-ADMISSION.json'
$taskPinsBinding = Get-TaskBinding $taskPinsPath
$taskAdmissionBinding = Get-TaskBinding $taskAdmissionPath
$taskLauncherBinding = Get-TaskBinding $PSCommandPath
$taskPins = Get-Content -LiteralPath $taskPinsPath -Raw | ConvertFrom-Json
$taskAdmission = Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
if ($taskAdmission.approved -cne $true -or $taskAdmission.label -cne 'prelock-retirement-confirmation03' -or
    $taskAdmission.pins_sha256 -cne $taskPinsBinding.sha256 -or
    $taskAdmission.scope -cne 'generated_bytes_and_fake_ports_only') { throw 'Exact root admission required' }
if ($taskPins.finalized -cne $true -or @($taskPins.files | Where-Object { $_.status -ceq 'pending_author_freeze' }).Count -ne 0) {
    throw 'Source preparation remains pending; no launch admitted'
}
$taskRows = @($taskPins.files)
if ($taskRows.Count -ne 39 -or @($taskRows.path | Sort-Object -Unique).Count -ne 39) { throw 'Exact 39-entry input map required' }
$taskBefore = @()
foreach ($taskRow in $taskRows) {
    if ($taskRow.path -cnotmatch '^[A-Za-z0-9_.-]+$') { throw 'Flat input name required' }
    $taskPath = Join-Path $taskSource $taskRow.path
    $taskActual = Get-TaskBinding $taskPath
    if ($taskActual.sha256 -cne $taskRow.sha256 -or $taskActual.bytes -ne $taskRow.bytes) { throw 'Pinned input mismatch' }
    $taskBefore += [ordered]@{ name = $taskRow.path; bytes = $taskActual.bytes; sha256 = $taskActual.sha256 }
}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach ($taskRow in $taskRows) { Copy-Item -LiteralPath (Join-Path $taskSource $taskRow.path) -Destination (Join-Path $taskRun $taskRow.path) -ErrorAction Stop }
Copy-Item -LiteralPath $taskPinsPath -Destination (Join-Path $taskRun 'PINS.json') -ErrorAction Stop
Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop
$taskControls = @(
    [ordered]@{name='PINS.json'; binding=$taskPinsBinding},
    [ordered]@{name='ROOT-ADMISSION.json'; binding=$taskAdmissionBinding},
    [ordered]@{name='run_preflight01.ps1'; binding=$taskLauncherBinding}
)
foreach ($taskRow in $taskBefore) {
    $taskCopy = Get-TaskBinding (Join-Path $taskRun $taskRow.name)
    if ($taskCopy.sha256 -cne $taskRow.sha256 -or $taskCopy.bytes -ne $taskRow.bytes) { throw 'Copied input mismatch' }
}
foreach ($taskControl in $taskControls) {
    $taskCopy = Get-TaskBinding (Join-Path $taskRun $taskControl.name)
    if ($taskCopy.sha256 -cne $taskControl.binding.sha256 -or $taskCopy.bytes -ne $taskControl.binding.bytes) { throw 'Copied control mismatch' }
}
$taskRemovedNames = @()
foreach ($taskEnv in @(Get-ChildItem Env:)) {
    if ($taskEnv.Name -match '(?i)(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI|AZURE_OPENAI|HF_TOKEN|HUGGING_FACE|API_KEY|ACCESS_TOKEN|PROXY|PYTHONPATH|PYTHONHOME|PYTHONSTARTUP|PYTHONUSERBASE|VIRTUAL_ENV)') {
        $taskRemovedNames += $taskEnv.Name
        Remove-Item -LiteralPath ('Env:' + $taskEnv.Name)
    }
}
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
Write-TaskJson (Join-Path $taskRun 'plan.json') ([ordered]@{
    schema='uoink.windows-reservation-fake-launch.v1'; label='prelock-retirement-confirmation03'; python=$taskPython;
    arguments=@('-I','-S','-B',(Join-Path $taskRun 'qualify_windows_reservations.py'));
    started_utc=$taskRunStarted; before=$taskBefore; controls=$taskControls;
    removed_environment_names=$taskRemovedNames; startup_binding_set=$true;
    scope='generated_bytes_and_fake_ports_only'
})

try {
    $PSNativeCommandUseErrorActionPreference = $false
    & $taskPython -I -S -B (Join-Path $taskRun 'qualify_windows_reservations.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
    $taskNative = $global:LASTEXITCODE
    Write-TaskJson (Join-Path $taskRun 'native-exit.json') ([ordered]@{
        native_exit=$taskNative; finished_utc=[DateTimeOffset]::UtcNow.ToString('o');
        elapsed_seconds=$taskClock.Elapsed.TotalSeconds
    })
    $taskAfter = @()
    foreach ($taskRow in $taskBefore) {
        $taskOriginal = Get-TaskBinding (Join-Path $taskSource $taskRow.name)
        $taskCopy = Get-TaskBinding (Join-Path $taskRun $taskRow.name)
        $taskAfter += [ordered]@{name=$taskRow.name; original=$taskOriginal; copy=$taskCopy;
            unchanged=($taskOriginal.sha256 -ceq $taskRow.sha256 -and $taskCopy.sha256 -ceq $taskRow.sha256 -and
                $taskOriginal.bytes -eq $taskRow.bytes -and $taskCopy.bytes -eq $taskRow.bytes)}
    }
    $taskAfterControls = @()
    foreach ($taskControl in $taskControls) {
        $taskOriginal = Get-TaskBinding (Join-Path $taskSource $taskControl.name)
        $taskCopy = Get-TaskBinding (Join-Path $taskRun $taskControl.name)
        $taskAfterControls += [ordered]@{name=$taskControl.name; original=$taskOriginal; copy=$taskCopy;
            unchanged=($taskOriginal.sha256 -ceq $taskControl.binding.sha256 -and $taskCopy.sha256 -ceq $taskControl.binding.sha256 -and
                $taskOriginal.bytes -eq $taskControl.binding.bytes -and $taskCopy.bytes -eq $taskControl.binding.bytes)}
    }
    $taskInputsOkay = @($taskAfter | Where-Object { $_.unchanged -ne $true }).Count -eq 0 -and
        @($taskAfterControls | Where-Object { $_.unchanged -ne $true }).Count -eq 0
    Write-TaskJson (Join-Path $taskRun 'input-check.json') ([ordered]@{inputs=$taskAfter; controls=$taskAfterControls; inputs_unchanged=$taskInputsOkay})
    $taskStdout = Get-Item -LiteralPath (Join-Path $taskRun 'stdout.json')
    $taskStderr = Get-Item -LiteralPath (Join-Path $taskRun 'stderr.log')
    if ($taskStdout.Length -gt 262144) { throw 'Raw receipt exceeds bound' }
    $taskResult = Get-Content -LiteralPath $taskStdout.FullName -Raw | ConvertFrom-Json
    $taskExpected = @(Get-Content -LiteralPath (Join-Path $taskRun 'EXPECTED-CASES.json') -Raw | ConvertFrom-Json)
    $taskCaseIds = @($taskResult.cases | ForEach-Object { $_.id })
    $taskMembership = ($taskCaseIds.Count -eq 30 -and $taskExpected.Count -eq 30 -and
        (($taskCaseIds | ConvertTo-Json -Compress) -ceq ($taskExpected | ConvertTo-Json -Compress)))
    $taskGuardsOkay = @($taskResult.guards.PSObject.Properties).Count -eq 10 -and
        @($taskResult.guards.PSObject.Properties | Where-Object { $_.Value -cne $true }).Count -eq 0
    $taskValid = ($taskNative -is [int] -and $taskNative -eq 0 -and $taskResult.qualification_exit -eq 0 -and
        $taskResult.passed -eq 30 -and $taskResult.failed -eq 0 -and $taskResult.skipped -eq 0 -and
        $taskMembership -and $taskGuardsOkay -and $taskResult.guard_valid -ceq $true -and
        $taskResult.membership_valid -ceq $true -and $taskInputsOkay -and $taskStderr.Length -eq 0 -and
        @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.registry_denials).Count -eq 0)
    Write-TaskJson (Join-Path $taskRun 'exit.json') ([ordered]@{
        native_exit=$taskNative; qualification_exit=$taskResult.qualification_exit;
        valid=$taskValid; inputs_unchanged=$taskInputsOkay; membership_valid=$taskMembership;
        guards_valid=$taskGuardsOkay; passed=$taskResult.passed; failed=$taskResult.failed; skipped=$taskResult.skipped;
        stdout_bytes=$taskStdout.Length; stderr_bytes=$taskStderr.Length;
        finished_utc=[DateTimeOffset]::UtcNow.ToString('o'); elapsed_seconds=$taskClock.Elapsed.TotalSeconds
    })
    if (-not $taskValid) { exit 1 }
    Write-Output 'prelock-retirement-confirmation03: 30 passed, 0 failed, 0 skipped; generated scope only.'
    exit 0
} catch {
    Write-TaskJson (Join-Path $taskRun 'launch-failure.json') ([ordered]@{
        native_exit=$taskNative; failure_type=$_.Exception.GetType().FullName;
        message=$_.Exception.Message; finished_utc=[DateTimeOffset]::UtcNow.ToString('o')
    })
    throw
}
