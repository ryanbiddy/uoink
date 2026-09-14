$ErrorActionPreference = 'Stop'
$taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskPreparation = Join-Path $taskRepo '_scratch/archive-native-retired-owner-recovery01-proposal01'
$taskTargetRelative = 'docs/library/proof/windows-retired-owner-recovery-native-2026-09-13'
$taskTarget = Join-Path $taskRepo $taskTargetRelative
$taskMapPath = Join-Path $taskPreparation 'COPY-INVENTORY.json'
$taskScriptPath = Join-Path $taskPreparation 'copy_archive.ps1'
$taskMapSha = 'ec71160c5e5172e98705a9e16b47d598dcd83780706c2acfeedbd8e456bd1c8f'
$taskLimit = 1048576
$taskUtf8 = [Text.UTF8Encoding]::new($false, $true)

function Named-Path([string]$taskBase, [string]$taskRelative) {
    if ($taskRelative -cnotmatch '^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$' -or
        @($taskRelative.Split('/') | Where-Object { $_ -ceq '.' -or $_ -ceq '..' }).Count) {
        throw 'Fixed ordinary relative path required'
    }
    $taskFull = [IO.Path]::GetFullPath((Join-Path $taskBase $taskRelative))
    $taskPrefix = [IO.Path]::GetFullPath($taskBase).TrimEnd('\') + '\'
    if (-not $taskFull.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Path escaped fixed base'
    }
    return $taskFull
}
function Plain-Path([string]$taskPath, [string]$taskBase) {
    $taskCurrent = [IO.Path]::GetFullPath($taskPath)
    $taskBoundary = [IO.Path]::GetFullPath($taskBase).TrimEnd('\')
    while ($true) {
        $taskAttributes = [IO.File]::GetAttributes($taskCurrent)
        if ($taskAttributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse input refused' }
        if ($taskCurrent.Equals($taskBoundary, [StringComparison]::OrdinalIgnoreCase)) { break }
        $taskParent = [IO.Path]::GetDirectoryName($taskCurrent)
        if (-not $taskParent -or $taskParent.Length -lt $taskBoundary.Length) { throw 'Outside fixed boundary' }
        $taskCurrent = $taskParent
    }
}
function Read-TextBytes([string]$taskPath, [string]$taskBase, [long]$taskExpectedSize = -1, [string]$taskExpectedSha = '') {
    Plain-Path $taskPath $taskBase
    $taskBefore = Get-Item -LiteralPath $taskPath
    if ($taskBefore.PSIsContainer -or $taskBefore.Length -gt $taskLimit) { throw 'Bounded regular text required' }
    $taskLength = [long]$taskBefore.Length
    if ($taskExpectedSize -ge 0 -and $taskLength -ne $taskExpectedSize) { throw 'Input length differs' }
    $taskCreated = $taskBefore.CreationTimeUtc.Ticks
    $taskWritten = $taskBefore.LastWriteTimeUtc.Ticks
    $taskBuffer = [byte[]]::new([int]$taskLength + 1)
    $taskStream = [IO.FileStream]::new($taskPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($taskStream.Length -ne $taskLength) { throw 'Input changed before read' }
        $taskCount = 0
        while ($taskCount -lt $taskBuffer.Length) {
            $taskRead = $taskStream.Read($taskBuffer, $taskCount, $taskBuffer.Length - $taskCount)
            if ($taskRead -eq 0) { break }
            $taskCount += $taskRead
        }
        if ($taskCount -ne $taskLength -or $taskStream.Length -ne $taskLength) { throw 'Input grew or truncated' }
    } finally { $taskStream.Dispose() }
    Plain-Path $taskPath $taskBase
    $taskAfter = Get-Item -LiteralPath $taskPath
    if ($taskAfter.Length -ne $taskLength -or $taskAfter.CreationTimeUtc.Ticks -ne $taskCreated -or
        $taskAfter.LastWriteTimeUtc.Ticks -ne $taskWritten) { throw 'Input metadata changed during read' }
    $taskBytes = [byte[]]::new([int]$taskLength)
    [Array]::Copy($taskBuffer, $taskBytes, [int]$taskLength)
    $taskText = $taskUtf8.GetString($taskBytes)
    if ($taskText.IndexOf([char]0) -ge 0) { throw 'NUL content is not admitted text' }
    $taskSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
    if ($taskExpectedSha -and $taskSha -cne $taskExpectedSha) { throw 'Input hash differs' }
    return [pscustomobject]@{ bytes=$taskBytes; text=$taskText; sha256=$taskSha }
}
function Write-NewBytes([string]$taskPath, [byte[]]$taskBytes) {
    $taskParent = [IO.Path]::GetDirectoryName($taskPath)
    [IO.Directory]::CreateDirectory($taskParent) | Out-Null
    Plain-Path $taskParent $taskTarget
    $taskStream = [IO.FileStream]::new($taskPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $taskStream.Write($taskBytes); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
}

if (-not ([IO.Path]::GetFullPath($PSCommandPath)).Equals($taskScriptPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use the fixed reviewed copier path'
}
if (Test-Path -LiteralPath $taskTarget) { throw 'Fresh archive required; preserve any previous partial output' }
Plain-Path ([IO.Path]::GetDirectoryName($taskTarget)) $taskRepo
$taskMapInput = Read-TextBytes $taskMapPath $taskRepo -1 $taskMapSha
$taskScriptInput = Read-TextBytes $taskScriptPath $taskRepo
$taskMap = $taskMapInput.text | ConvertFrom-Json
$taskRows = @($taskMap.files)
if ($taskMap.schema -cne 'uoink.native-retired-owner-recovery.copy-inventory.v1' -or
    $taskMap.target -cne $taskTargetRelative -or $taskRows.Count -ne 88) { throw 'Exact inventory required' }
$taskPayloads = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
$taskOriginals = @()
$taskTotal = [long]0
foreach ($taskRow in $taskRows) {
    if ($taskRow.bytes -is [bool] -or $taskRow.bytes -lt 0 -or $taskRow.bytes -gt $taskLimit -or
        $taskRow.sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Malformed fixed binding' }
    $taskSourcePath = Named-Path $taskRepo $taskRow.source
    $taskDestinationPath = Named-Path $taskTarget $taskRow.path
    if ($taskPayloads.ContainsKey($taskRow.path)) { throw 'Duplicate archive path' }
    $taskInput = Read-TextBytes $taskSourcePath $taskRepo $taskRow.bytes $taskRow.sha256
    $taskTotal += $taskInput.bytes.Length
    if ($taskTotal -gt 16777216) { throw 'Fixed archive byte budget exceeded' }
    $taskPayloads.Add($taskRow.path, $taskInput)
    $taskOriginals += [pscustomobject]@{ source=$taskSourcePath; bytes=$taskRow.bytes; sha256=$taskRow.sha256 }
}
$taskPayloads.Add('archive-preparation/COPY-INVENTORY.json', $taskMapInput)
$taskPayloads.Add('archive-preparation/copy_archive.ps1', $taskScriptInput)
$taskAttributesBytes = $taskUtf8.GetBytes("* -text`n")
$taskPayloads.Add('.gitattributes', [pscustomobject]@{
    bytes=$taskAttributesBytes; text=$taskUtf8.GetString($taskAttributesBytes);
    sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskAttributesBytes)).ToLowerInvariant()
})
if ($taskPayloads.Count -ne 91) { throw 'Exact 91 output payloads required' }

# No source code in these bytes is imported or executed.
[IO.Directory]::CreateDirectory($taskTarget) | Out-Null
Write-NewBytes (Join-Path $taskTarget '.gitattributes') $taskAttributesBytes
foreach ($taskName in @($taskPayloads.Keys | Sort-Object)) {
    if ($taskName -ceq '.gitattributes') { continue }
    Write-NewBytes (Named-Path $taskTarget $taskName) $taskPayloads[$taskName].bytes
}
foreach ($taskOriginal in $taskOriginals) {
    $null = Read-TextBytes $taskOriginal.source $taskRepo $taskOriginal.bytes $taskOriginal.sha256
}
$null = Read-TextBytes $taskMapPath $taskRepo $taskMapInput.bytes.Length $taskMapInput.sha256
$null = Read-TextBytes $taskScriptPath $taskRepo $taskScriptInput.bytes.Length $taskScriptInput.sha256
$taskSealRows = @()
$taskSealedBytes = [long]0
foreach ($taskName in @($taskPayloads.Keys | Sort-Object)) {
    $taskInput = $taskPayloads[$taskName]
    $taskCopy = Read-TextBytes (Named-Path $taskTarget $taskName) $taskTarget $taskInput.bytes.Length $taskInput.sha256
    $taskSealRows += [pscustomobject]@{path=$taskName; bytes=$taskCopy.bytes.Length; sha256=$taskCopy.sha256}
    $taskSealedBytes += $taskCopy.bytes.Length
}
$taskSealBytes = $taskUtf8.GetBytes((([ordered]@{files=$taskSealRows}) | ConvertTo-Json -Depth 8) + "`n")
Write-NewBytes (Join-Path $taskTarget 'SHA256.json') $taskSealBytes
$taskSealSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskSealBytes)).ToLowerInvariant()
$null = Read-TextBytes (Join-Path $taskTarget 'SHA256.json') $taskTarget $taskSealBytes.Length $taskSealSha
$taskActual = @(Get-ChildItem -LiteralPath $taskTarget -Recurse -File | ForEach-Object {
    [IO.Path]::GetRelativePath($taskTarget, $_.FullName).Replace('\','/')
} | Sort-Object)
$taskExpected = @(@($taskPayloads.Keys) + @('SHA256.json') | Sort-Object)
if (($taskActual | ConvertTo-Json -Compress) -cne ($taskExpected | ConvertTo-Json -Compress)) {
    throw 'Final archive membership differs'
}
foreach ($taskRow in $taskSealRows) {
    $null = Read-TextBytes (Named-Path $taskTarget $taskRow.path) $taskTarget $taskRow.bytes $taskRow.sha256
}
[ordered]@{payloads=$taskSealRows.Count; payload_bytes=$taskSealedBytes; manifest_sha256=$taskSealSha;
    target=$taskTarget; source_inputs_unchanged=$true; copied_bytes_verified=$true;
    candidate_executions=0; new_native_observations=0} | ConvertTo-Json -Depth 4
