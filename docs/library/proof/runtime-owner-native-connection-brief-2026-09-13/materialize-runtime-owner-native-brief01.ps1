$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskRepo '_scratch/runtime-owner-native-connection-next-brief01'
$taskProof=Join-Path $taskRepo 'docs/library/proof/runtime-owner-native-connection-brief-2026-09-13'
$taskCanonical=Join-Path $taskRepo 'docs/library/RUNTIME-OWNER-NATIVE-CONNECTION-BRIEF-2026-09-13.md'
$taskUtf8=[Text.UTF8Encoding]::new($false,$true)
function Read-TaskText([string]$taskPath) {
    $taskItem=Get-Item -LiteralPath $taskPath
    if ($taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $taskItem.Length -gt 1048576) { throw 'Bounded ordinary text required' }
    $taskBytes=[IO.File]::ReadAllBytes($taskPath)
    $taskText=$taskUtf8.GetString($taskBytes)
    if ($taskText.IndexOf([char]0) -ge 0) { throw 'NUL refused' }
    [pscustomobject]@{bytes=$taskBytes; text=$taskText; sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()}
}
function Write-TaskNew([string]$taskPath,[byte[]]$taskBytes) {
    $taskStream=[IO.FileStream]::new($taskPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try {$taskStream.Write($taskBytes);$taskStream.Flush($true)} finally {$taskStream.Dispose()}
}
if ((Test-Path -LiteralPath $taskProof) -or (Test-Path -LiteralPath $taskCanonical)) { throw 'Fresh proof and canonical brief required' }
$taskBrief=Read-TaskText (Join-Path $taskSource 'BRIEF.md')
$taskMap=Read-TaskText (Join-Path $taskSource 'SOURCE-BINDINGS.json')
$taskActual=Read-TaskText (Join-Path $taskSource 'TEXT-BINDING-CHECK-ACTUAL.json')
if ($taskBrief.sha256 -cne '78311a84a5f54e3b1e1660496f07647f0978d8f27bd13e5a0829c3121e310d4e' -or $taskMap.sha256 -cne 'a95374737f5a49a97fedd8e689b5a1890e31c21c1e9997997dced792c0537659') { throw 'Frozen brief/map differs' }
$taskSelection=$taskMap.text | ConvertFrom-Json
if ($taskSelection.count -ne 25 -or @($taskSelection.files).Count -ne 25 -or $taskSelection.total_bytes -ne 708005) { throw 'Fixed selection required' }
$taskCurrent=0
foreach ($taskRow in $taskSelection.files) {
    if ($taskRow.id -ceq 'HANDOFF') { continue }
    if ($taskRow.path -cnotmatch '^docs/library/[A-Za-z0-9_./-]+$' -or $taskRow.path.Contains('..') -or [IO.Path]::GetExtension($taskRow.path) -cnotin @('.md','.py','.ps1')) { throw 'Selected source text only' }
    $taskInput=Read-TaskText (Join-Path $taskRepo $taskRow.path)
    if ($taskInput.bytes.Length -ne $taskRow.bytes -or $taskInput.sha256 -cne $taskRow.sha256) { throw 'Selected source changed' }
    $taskCurrent++
}
if ($taskCurrent -ne 24 -or $taskSelection.files[0].id -cne 'HANDOFF') { throw '24 current texts and one historical handoff row required' }
$taskReview=@'
# Root direction for the next runtime-owner connection

The brief is accepted for source preparation. Root read it completely as e0f397. Its24 stable source/verdict inputs match; its handoff row records an earlier snapshot and is not a current-state requirement. Preserve that row and its review extent rather than silently updating its hash.

Use the latest retired-owner recovery adapter source as the implementation before copy, preserving all existing drain/cancel/recovery controllers and the prior child route. The first native proposal uses the existing cancellation controller. A combined owner/recovery claim requires separate evidence. The new bridge must retain one channel, publish within the qualified owner/PCM/VAD boundary and retain uncertain inputs; no real factory/registry/owner gate or accepted assertion changes.

The writer is preparing source under _scratch/runtime-owner-native-connection-proposal01. Original17 cases must remain intact, with new cases separately frozen after implementation. Nothing in this brief admits candidate tests or native/model execution. D2 remains locally complete; no checkpoint/converted-output access or D3/D4/fetch authority is supplied.
'@
$taskPayloads=[ordered]@{'BRIEF.md'=$taskBrief.bytes;'SOURCE-BINDINGS.json'=$taskMap.bytes;'TEXT-BINDING-CHECK-ACTUAL.json'=$taskActual.bytes;'ROOT-DIRECTION.md'=$taskUtf8.GetBytes($taskReview+"`n");'.gitattributes'=$taskUtf8.GetBytes("* -text`n");'materialize-runtime-owner-native-brief01.ps1'=([IO.File]::ReadAllBytes($PSCommandPath))}
[IO.Directory]::CreateDirectory($taskProof) | Out-Null
$taskRows=@()
$taskTotal=0
foreach ($taskName in $taskPayloads.Keys) {
    Write-TaskNew (Join-Path $taskProof $taskName) $taskPayloads[$taskName]
    $taskCopy=Read-TaskText (Join-Path $taskProof $taskName)
    $taskExpected=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskPayloads[$taskName])).ToLowerInvariant()
    if ($taskCopy.sha256 -cne $taskExpected) { throw 'Documentary copy differs' }
    $taskRows += [ordered]@{path=$taskName;bytes=$taskCopy.bytes.Length;sha256=$taskCopy.sha256}
    $taskTotal += $taskCopy.bytes.Length
}
Write-TaskNew (Join-Path $taskProof 'SHA256.json') $taskUtf8.GetBytes((([ordered]@{files=$taskRows}) | ConvertTo-Json -Depth 6)+"`n")
Write-TaskNew $taskCanonical $taskBrief.bytes
if ((Read-TaskText $taskCanonical).sha256 -cne $taskBrief.sha256) { throw 'Canonical copy differs' }
[ordered]@{payloads=6;payload_bytes=$taskTotal;current_source_bindings=24;historical_handoff_rows=1;candidate_executions=0;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $taskProof 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
