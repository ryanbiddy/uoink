param([string]$ProofPath=$PSScriptRoot)
$ErrorActionPreference = 'Stop'
$rows = @(Get-Content -LiteralPath (Join-Path $ProofPath 'SHA256.json') -Raw | ConvertFrom-Json)
if ($rows.Count -ne 38) { throw 'Unexpected proof count' }
$names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
[long]$total = 0
foreach ($row in $rows) {
    if ($row.path -match '(^/|\\|:|(^|/)\.\.?(/|$))' -or -not $names.Add($row.path)) { throw 'Duplicate/noncanonical path' }
    $path = Join-Path $ProofPath $row.path
    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $row.bytes -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256) { throw ('Payload mismatch: ' + $row.path) }
    $total += $item.Length
}
$files = @(Get-ChildItem -LiteralPath $ProofPath -File -Recurse)
if ($files.Count -ne 39) { throw 'Extra/missing proof files' }
foreach ($file in $files) {
    $name = [IO.Path]::GetRelativePath($ProofPath,$file.FullName).Replace([char]92,[char]47)
    if ($name -cne 'SHA256.json' -and -not $names.Contains($name)) { throw 'Unsealed proof file' }
}
$map = Get-Content -LiteralPath (Join-Path $ProofPath 'SOURCE-COPY-MAP.json') -Raw | ConvertFrom-Json
$rootRows = @(Get-Content -LiteralPath (Join-Path $ProofPath 'ROOT-COPY-BINDINGS.json') -Raw | ConvertFrom-Json)
foreach ($copy in (@($map.files) + $rootRows)) {
    $bound = @($rows|Where-Object path -CEQ $copy.path)
    if ($bound.Count -ne 1 -or $bound[0].bytes -ne $copy.bytes -or $bound[0].sha256 -cne $copy.sha256) { throw 'Copy binding mismatch' }
}
[ordered]@{status='VERIFIED'; payloads=38; bytes=$total; copies=30;
    manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $ProofPath 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant(); executed_models_tests_builds=$false} | ConvertTo-Json -Compress
