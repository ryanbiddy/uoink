$ErrorActionPreference = 'Stop'
$source = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\whisperx-owned-builder-proposal01'
$target = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-whisperx-owned-contracts01'
$manifestHash = '5602d0e46f91739c40799e0ce2592560274cc70c252421f856d3cf77133bcd9f'
$manifestPath = Join-Path $source 'INPUT-HASHES.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $manifestHash) { throw 'Original manifest mismatch' }
$rows = @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)
if ($rows.Count -ne 46) { throw 'Unexpected source membership' }
$rows += [pscustomobject]@{path='INPUT-HASHES.json'; bytes=(Get-Item -LiteralPath $manifestPath).Length; sha256=$manifestHash}
if (Test-Path -LiteralPath $target) { throw 'Refuse reused independent directory' }
[IO.Directory]::CreateDirectory($target) | Out-Null
$bindings = @()
foreach ($row in $rows) {
    if ($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))') { throw 'Noncanonical source path' }
    $from = Join-Path $source $row.path
    $to = Join-Path $target $row.path
    $item = Get-Item -LiteralPath $from
    if ($item.PSIsContainer -or $item.Length -ne $row.bytes -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256) { throw 'Original input mismatch' }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to)) | Out-Null
    [IO.File]::Copy($from, $to, $false)
    $copied = Get-Item -LiteralPath $to
    if ($copied.Length -ne $row.bytes -or
        (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256 -or
        (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256) { throw 'Copy or source changed' }
    $bindings += [ordered]@{path=$row.path; source=$from; destination=$to; bytes=$row.bytes; sha256=$row.sha256}
}
$receipt = [ordered]@{status='COPIED_NOT_EXECUTED'; source=$source; destination=$target; count=$bindings.Count;
    manifest_sha256=$manifestHash; bindings=$bindings; launcher_bytes_unchanged=$true;
    child_label='qualification01 in a fresh independent directory'; no_python_or_tests_run=$true;
    finished_utc=[DateTime]::UtcNow.ToString('o')}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($receipt | ConvertTo-Json -Depth 6) + "`n")
$stream = [IO.FileStream]::new((Join-Path $target 'COPY-BINDINGS.json'), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
$receipt | Select-Object status,count,manifest_sha256,no_python_or_tests_run | ConvertTo-Json -Compress
