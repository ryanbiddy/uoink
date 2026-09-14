$ErrorActionPreference = 'Stop'
$taskSource = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-reservation-implementation-proposal01'
$taskDestination = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-reservation-independent01'
$taskExpectedPins = '4f5cd502c563f7dc23b3be81bffd93429eea8c30434e56da96b4d49f5cc42ee7'
$taskStarted = [DateTimeOffset]::UtcNow.ToString('o')
function Binding([string]$taskPath) {
    $taskItem = Get-Item -LiteralPath $taskPath -ErrorAction Stop
    if ($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Plain source required' }
    [ordered]@{ bytes=$taskItem.Length; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $taskPath).Hash.ToLowerInvariant() }
}
if (Test-Path -LiteralPath $taskDestination) { throw 'Fresh independent destination required' }
$taskPinsPath = Join-Path $taskSource 'PINS.json'
$taskPinsBinding = Binding $taskPinsPath
if ($taskPinsBinding.sha256 -cne $taskExpectedPins) { throw 'Frozen source pins differ' }
$taskPins = Get-Content -LiteralPath $taskPinsPath -Raw | ConvertFrom-Json
if ($taskPins.files.Count -ne 28 -or @($taskPins.files.path | Sort-Object -Unique).Count -ne 28) { throw 'Exact 28 input rows required' }
$taskRows = @()
foreach ($taskRow in $taskPins.files) {
    if ($taskRow.path -cnotmatch '^[A-Za-z0-9_.-]+$') { throw 'Flat input name required' }
    $taskBinding = Binding (Join-Path $taskSource $taskRow.path)
    if ($taskBinding.sha256 -cne $taskRow.sha256 -or $taskBinding.bytes -ne $taskRow.bytes) { throw 'Input changed before copy' }
    $taskRows += [ordered]@{source=$taskRow.path; destination=$taskRow.path; binding=$taskBinding}
}
$taskRows += [ordered]@{source='PINS.json'; destination='PINS.json'; binding=$taskPinsBinding}
$taskAuthorAdmission = Binding (Join-Path $taskSource 'ROOT-ADMISSION.json')
$taskRows += [ordered]@{source='ROOT-ADMISSION.json'; destination='AUTHOR-ROOT-ADMISSION.json'; binding=$taskAuthorAdmission}
New-Item -ItemType Directory -Path $taskDestination -ErrorAction Stop | Out-Null
$taskCopied = @()
foreach ($taskRow in $taskRows) {
    Copy-Item -LiteralPath (Join-Path $taskSource $taskRow.source) -Destination (Join-Path $taskDestination $taskRow.destination) -ErrorAction Stop
    $taskAfter = Binding (Join-Path $taskSource $taskRow.source)
    $taskCopy = Binding (Join-Path $taskDestination $taskRow.destination)
    if ($taskAfter.sha256 -cne $taskRow.binding.sha256 -or $taskCopy.sha256 -cne $taskRow.binding.sha256 -or
        $taskAfter.bytes -ne $taskRow.binding.bytes -or $taskCopy.bytes -ne $taskRow.binding.bytes) { throw 'Source or copy changed' }
    $taskCopied += [ordered]@{source=$taskRow.source; destination=$taskRow.destination; before=$taskRow.binding; after=$taskAfter; copy=$taskCopy; unchanged=$true}
}
$taskReceipt = [ordered]@{schema='uoink.windows-reservation-independent-copy.v1'; source=$taskSource; destination=$taskDestination;
    pins_sha256=$taskExpectedPins; pinned_count=28; copied_count=30; files=$taskCopied;
    recipe=Binding $PSCommandPath; started_utc=$taskStarted; finished_utc=[DateTimeOffset]::UtcNow.ToString('o');
    independent_admission_created=$false; runner_executed=$false}
$taskBytes = [Text.UTF8Encoding]::new($false).GetBytes(($taskReceipt | ConvertTo-Json -Depth 12)+"`n")
$taskFile = [IO.FileStream]::new((Join-Path $taskDestination 'COPY-BINDINGS.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try { $taskFile.Write($taskBytes); $taskFile.Flush($true) } finally { $taskFile.Dispose() }
Write-Output 'Copied 28 pinned inputs, original PINS and separately named author admission. No independent admission or execution.'