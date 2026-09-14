# Unexecuted data-only proposal for root review. Running this fixed preparation
# creates a distinct fake-only root admission after copying and validating inputs.
# It never invokes Python, the qualification launcher, tests, or native APIs.
# Trusted source/scratch directories must remain quiescent during this copy.
$ErrorActionPreference = 'Stop'
$taskSource = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-journal-cancel-fake-proposal01'
$taskTarget = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-journal-cancel-confirmation01'
$taskPinsHash = 'e60aa77cdd2dd4477960f44f24770f22f7a1e1ff3c334b8985047acb8e8f1a79'
$taskCasesHash = '2422c084ec371ac8cbce6c191dab8bd7d6c32640afebe73aae6ae982dc4b8bea'
$taskLauncherHash = 'e6ce742b838131e5b2abbb70e3e0ffdb67bc36702d211dc5e520151bcd4abe3f'
$taskStarted = [DateTimeOffset]::UtcNow.ToString('o')

function Get-TaskBinding([string]$taskPath) {
    $taskItem = Get-Item -LiteralPath $taskPath -ErrorAction Stop
    if ($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Plain text input required' }
    return [ordered]@{ bytes=$taskItem.Length; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $taskPath).Hash.ToLowerInvariant() }
}
function Write-TaskJson([string]$taskPath, $taskValue) {
    $taskBytes = [Text.UTF8Encoding]::new($false).GetBytes(($taskValue | ConvertTo-Json -Depth 20) + "`n")
    $taskStream = [IO.FileStream]::new($taskPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $taskStream.Write($taskBytes); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
}

foreach ($taskDirectory in @($taskSource, (Split-Path -Parent $taskTarget))) {
    $taskItem = Get-Item -LiteralPath $taskDirectory -ErrorAction Stop
    if (-not $taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Plain fixed source and scratch directories required' }
}
if (Test-Path -LiteralPath $taskTarget) { throw 'Fresh independent target required; preserve any previous attempt' }
$taskScriptBefore = Get-TaskBinding $PSCommandPath
$taskPinsPath = Join-Path $taskSource 'PINS.json'
$taskPinsBefore = Get-TaskBinding $taskPinsPath
if ($taskPinsBefore.sha256 -cne $taskPinsHash) { throw 'Frozen PINS hash mismatch' }
$taskPins = Get-Content -LiteralPath $taskPinsPath -Raw | ConvertFrom-Json
$taskRows = @($taskPins.files)
if ($taskPins.schema -cne 'uoink.windows-journal-cancel-fake-inputs.v1' -or $taskPins.count -ne 33 -or
    $taskRows.Count -ne 33 -or @($taskRows.path | Sort-Object -Unique).Count -ne 33) { throw 'Exact 33-entry manifest required' }
$taskBefore = @()
foreach ($taskRow in $taskRows) {
    if ($taskRow.path -cnotmatch '^[A-Za-z0-9_.-]+$' -or $taskRow.path -in @('.', '..', 'PINS.json', 'ROOT-ADMISSION.json', 'COPY-BINDINGS.json')) { throw 'Pinned flat source name required' }
    $taskActual = Get-TaskBinding (Join-Path $taskSource $taskRow.path)
    if ($taskActual.sha256 -cne $taskRow.sha256 -or $taskActual.bytes -ne $taskRow.bytes) { throw ('Source input mismatch: ' + $taskRow.path) }
    $taskBefore += [ordered]@{path=$taskRow.path; bytes=$taskActual.bytes; sha256=$taskActual.sha256}
}
$taskCasesBinding = Get-TaskBinding (Join-Path $taskSource 'EXPECTED-CASES.json')
$taskLauncherBinding = Get-TaskBinding (Join-Path $taskSource 'run_preflight01.ps1')
$taskCases = @(Get-Content -LiteralPath (Join-Path $taskSource 'EXPECTED-CASES.json') -Raw | ConvertFrom-Json)
if ($taskCasesBinding.sha256 -cne $taskCasesHash -or $taskCases.Count -ne 89 -or @($taskCases | Sort-Object -Unique).Count -ne 89 -or
    $taskLauncherBinding.sha256 -cne $taskLauncherHash) { throw 'Exact 89 IDs and unchanged dynamic launcher required' }

# The original PINS bytes and all 33 rows are copied without any source rewriting.
New-Item -ItemType Directory -Path $taskTarget -ErrorAction Stop | Out-Null
foreach ($taskRow in $taskBefore) { Copy-Item -LiteralPath (Join-Path $taskSource $taskRow.path) -Destination (Join-Path $taskTarget $taskRow.path) -ErrorAction Stop }
Copy-Item -LiteralPath $taskPinsPath -Destination (Join-Path $taskTarget 'PINS.json') -ErrorAction Stop
$taskFiles = @()
foreach ($taskRow in $taskBefore) {
    $taskOriginal = Get-TaskBinding (Join-Path $taskSource $taskRow.path)
    $taskCopy = Get-TaskBinding (Join-Path $taskTarget $taskRow.path)
    $taskUnchanged = $taskOriginal.sha256 -ceq $taskRow.sha256 -and $taskCopy.sha256 -ceq $taskRow.sha256 -and
        $taskOriginal.bytes -eq $taskRow.bytes -and $taskCopy.bytes -eq $taskRow.bytes
    if (-not $taskUnchanged) { throw ('Original or copied input mismatch: ' + $taskRow.path) }
    $taskFiles += [ordered]@{path=$taskRow.path; before=$taskRow; original_after=$taskOriginal; copy=$taskCopy; unchanged=$taskUnchanged}
}
$taskPinsAfter = Get-TaskBinding $taskPinsPath
$taskPinsCopy = Get-TaskBinding (Join-Path $taskTarget 'PINS.json')
$taskScriptAfter = Get-TaskBinding $PSCommandPath
if ($taskPinsAfter.sha256 -cne $taskPinsHash -or $taskPinsCopy.sha256 -cne $taskPinsHash -or
    $taskPinsAfter.bytes -ne $taskPinsBefore.bytes -or $taskPinsCopy.bytes -ne $taskPinsBefore.bytes -or
    $taskScriptAfter.sha256 -cne $taskScriptBefore.sha256 -or $taskScriptAfter.bytes -ne $taskScriptBefore.bytes) { throw 'Manifest or preparation source changed' }
$taskExpectedMembers = @($taskRows.path) + @('PINS.json')
$taskActualMembers = @(Get-ChildItem -LiteralPath $taskTarget -Force | ForEach-Object { $_.Name })
if ($taskActualMembers.Count -ne 34 -or @(Compare-Object ($taskExpectedMembers | Sort-Object) ($taskActualMembers | Sort-Object)).Count -ne 0) { throw 'Exact copied membership required' }

# This admission is newly issued by the reviewed root preparation, never copied
# from or written to the author directory. It is not native-work authorization.
$taskAdmissionPath = Join-Path $taskTarget 'ROOT-ADMISSION.json'
Write-TaskJson $taskAdmissionPath ([ordered]@{
    approved=$true; label='journal-cancel-fake01'; pins_sha256=$taskPinsHash;
    scope='generated_bytes_and_fake_ports_only'; independent_source=$taskSource; independent_target=$taskTarget;
    preparation_sha256=$taskScriptBefore.sha256; expected_cases_sha256=$taskCasesHash; expected_case_count=89;
    note='One unchanged independent fake-port qualification; no tests or native work executed by preparation.'
})
$taskAdmissionBinding = Get-TaskBinding $taskAdmissionPath
Write-TaskJson (Join-Path $taskTarget 'COPY-BINDINGS.json') ([ordered]@{
    schema='uoink.journal-cancel-independent-copy.v1'; source=$taskSource; target=$taskTarget;
    started_utc=$taskStarted; finished_utc=[DateTimeOffset]::UtcNow.ToString('o');
    preparation=[ordered]@{path=$PSCommandPath; before=$taskScriptBefore; after=$taskScriptAfter};
    count=33; files=$taskFiles; pins=[ordered]@{before=$taskPinsBefore; original_after=$taskPinsAfter; copy=$taskPinsCopy};
    cases=[ordered]@{count=89; sha256=$taskCasesHash; ordering='Exact unchanged EXPECTED-CASES.json bytes'};
    launcher=[ordered]@{sha256=$taskLauncherHash; changes=0; child_directory='journal-cancel-fake01'};
    admission=$taskAdmissionBinding; inputs_unchanged=$true; tests_executed=$false; native_executed=$false;
    scope='Fixed text/control copy only; native/runtime/model semantics remain unqualified by this preparation.'
})
$taskFinalMembers = @(Get-ChildItem -LiteralPath $taskTarget -Force | ForEach-Object { $_.Name })
$taskExpectedFinal = $taskExpectedMembers + @('ROOT-ADMISSION.json', 'COPY-BINDINGS.json')
if ($taskFinalMembers.Count -ne 36 -or @(Compare-Object ($taskExpectedFinal | Sort-Object) ($taskFinalMembers | Sort-Object)).Count -ne 0) { throw 'Unexpected prepared membership' }
Write-Output ('Prepared 33 exact pins plus original PINS, distinct admission and copy bindings: ' + $taskTarget)
Write-Output 'No tests or native work executed. Root must invoke the unchanged launcher separately.'
