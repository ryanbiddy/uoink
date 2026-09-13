param([string]$ProofPath = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $ProofPath 'SHA256.json'
$rows = @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)
if ($rows.Count -ne 217) { throw 'Expected 207 source payloads plus ten documentary/instrument/history files' }
$names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
[long]$bytes = 0
foreach ($row in $rows) {
    if ($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))' -or -not $names.Add($row.path)) { throw 'Noncanonical/duplicate manifest path' }
    $path = Join-Path $ProofPath $row.path
    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $item.Length -ne $row.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256) { throw ('Payload mismatch: ' + $row.path) }
    $bytes += $item.Length
}
$actual = @(Get-ChildItem -LiteralPath $ProofPath -File -Recurse | ForEach-Object { [IO.Path]::GetRelativePath($ProofPath,$_.FullName).Replace([char]92,[char]47) })
if ($actual.Count -ne $rows.Count + 1) { throw 'Extra or missing proof file' }
foreach ($name in $actual) { if ($name -cne 'SHA256.json' -and -not $names.Contains($name)) { throw 'Unsealed proof member' } }
$map = Get-Content -LiteralPath (Join-Path $ProofPath 'SOURCE-MAP.json') -Raw | ConvertFrom-Json
if ($map.files.Count -ne 207) { throw 'Source map membership' }
foreach ($row in $map.files) {
    $sealed = @($rows | Where-Object path -CEQ $row.path)
    if ($sealed.Count -ne 1 -or $sealed[0].bytes -ne $row.bytes -or $sealed[0].sha256 -cne $row.sha256) { throw 'Source-to-proof binding mismatch' }
}
[ordered]@{status='VERIFIED'; payloads=$rows.Count; bytes=$bytes; source_copies=207;
    manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant(); executed_copied_programs=$false} | ConvertTo-Json -Compress
