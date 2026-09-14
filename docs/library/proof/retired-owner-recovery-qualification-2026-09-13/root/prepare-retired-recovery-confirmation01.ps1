$ErrorActionPreference = 'Stop'
$taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource = Join-Path $taskRepo '_scratch/windows-retired-owner-recovery-proposal01'
$taskDestination = Join-Path $taskRepo '_scratch/astra-retired-recovery-confirmation01'
$taskExpectedMap = 'f7c3b964ed77a681ed71d9b03fee934cf402721bc232d869e5ee42c9f564e3a1'
function Read-TaskText([string]$taskPath) {
    $taskItem = Get-Item -LiteralPath $taskPath
    if ($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $taskItem.Length -gt 1048576) { throw 'Bounded plain text required' }
    $taskBytes = [IO.File]::ReadAllBytes($taskPath)
    $taskText = [Text.UTF8Encoding]::new($false,$true).GetString($taskBytes)
    [pscustomobject]@{ bytes=$taskBytes; text=$taskText; sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant() }
}
if (Test-Path -LiteralPath $taskDestination) { throw 'Fresh confirmation directory required' }
$taskMap = Read-TaskText (Join-Path $taskSource 'PINS.json')
if ($taskMap.sha256 -cne $taskExpectedMap) { throw 'Frozen map differs' }
$taskRows = @(($taskMap.text | ConvertFrom-Json).files)
if ($taskRows.Count -ne 26 -or @($taskRows.path | Sort-Object -Unique).Count -ne 26) { throw 'Exact 26 text inputs required' }
$taskPayloads = [ordered]@{}
foreach ($taskRow in $taskRows) {
    if ($taskRow.path -cnotmatch '^[A-Za-z0-9_.-]+$') { throw 'Flat source name required' }
    $taskInput = Read-TaskText (Join-Path $taskSource $taskRow.path)
    if ($taskInput.sha256 -cne $taskRow.sha256 -or $taskInput.bytes.Length -ne $taskRow.bytes) { throw 'Source pin differs' }
    $taskPayloads.Add($taskRow.path,$taskInput)
}
$taskAdmission = Read-TaskText (Join-Path $taskSource 'ROOT-ADMISSION.json')
$taskApproved = $taskAdmission.text | ConvertFrom-Json
if ($taskApproved.approved -cne $true -or $taskApproved.label -cne 'retired-recovery-fake01' -or $taskApproved.pins_sha256 -cne $taskExpectedMap -or $taskApproved.scope -cne 'generated_bytes_and_fake_ports_only') { throw 'Reviewed root admission required' }
$taskPayloads.Add('PINS.json',$taskMap)
$taskPayloads.Add('ROOT-ADMISSION.json',$taskAdmission)
[IO.Directory]::CreateDirectory($taskDestination) | Out-Null
$taskCopied = @()
foreach ($taskName in $taskPayloads.Keys) {
    $taskInput = $taskPayloads[$taskName]
    $taskOutput = Join-Path $taskDestination $taskName
    $taskStream = [IO.FileStream]::new($taskOutput,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $taskStream.Write($taskInput.bytes); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
    $taskCheck = Read-TaskText $taskOutput
    if ($taskCheck.sha256 -cne $taskInput.sha256 -or $taskCheck.bytes.Length -ne $taskInput.bytes.Length) { throw 'Copy differs' }
    $taskCopied += [ordered]@{name=$taskName; bytes=$taskCheck.bytes.Length; sha256=$taskCheck.sha256}
}
[ordered]@{schema='uoink.retired-recovery-confirmation-copy.v1'; copied=$taskCopied; input_count=26; controls=@('PINS.json','ROOT-ADMISSION.json'); candidate_execution=$false; destination=$taskDestination} | ConvertTo-Json -Depth 8
