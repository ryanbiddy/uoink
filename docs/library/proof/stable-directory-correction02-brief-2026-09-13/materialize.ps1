param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{64}$')]
    [string]$ReviewedScriptSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$checkout = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$preparation = '_scratch\gemini-stable-directory-correction02-proposal01'
$proposal = '_scratch\stable-directory-correction02-materialization01'
$proof = Join-Path $checkout 'docs\library\proof\stable-directory-correction02-brief-2026-09-13'
$canonical = Join-Path $checkout 'docs\library\GEMINI-STABLE-DIRECTORY-CORRECTION02-BRIEF-2026-09-13.md'
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$readCap = 65536

function Hash-Bytes([byte[]]$Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Read-Fixed([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Not an ordinary fixed file: $Path"
    }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $buffer = [byte[]]::new($readCap + 1)
        $used = 0
        while ($used -lt $buffer.Length) {
            $n = $stream.Read($buffer, $used, $buffer.Length - $used)
            if ($n -eq 0) { break }
            $used += $n
        }
        if ($used -gt $readCap) { throw "Fixed text exceeds read cap: $Path" }
        $result = [byte[]]::new($used)
        [Array]::Copy($buffer, $result, $used)
        return ,$result
    } finally { $stream.Dispose() }
}
function Check-Bytes([byte[]]$Bytes, [long]$Length, [string]$Sha, [string]$Label) {
    if ($Bytes.Length -ne $Length -or (Hash-Bytes $Bytes) -cne $Sha) {
        throw "Byte binding mismatch: $Label"
    }
}
function Write-New([string]$Path, [byte[]]$Bytes) {
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($Bytes, 0, $Bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}
function Proof-Path([string]$Relative) {
    $path = [IO.Path]::GetFullPath((Join-Path $proof $Relative))
    if (-not $path.StartsWith($proof + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destination escapes the fixed proof directory'
    }
    return $path
}
$original = @(
    @('.gitattributes', 8, '705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
    @('BRIEF.md', 3929, 'a95db5f71a853fe18111842c82909babeac61fc67087c55b2fc31bac638ff174'),
    @('INPUT-SELECTION.json', 2220, '874b686d4a078d37385cac6b5a860a21aebeec08781d2ec150cd3f2e0491b277'),
    @('LINE-CONVENTION-DIAGNOSTIC01-ACTUAL.json', 575, 'a6ca6df10af89757d88d75ef04cf6d72a4076fe9152036c165397d9ba017a194'),
    @('MAP-PREPARATION01-FAILURE-ACTUAL.json', 353, '4a87e87117367d9ca73b4a99569483910729645dc52aa3987e8becf22d99a9a9'),
    @('MAP-PREPARATION02-SUCCESS-ACTUAL.json', 1186, '032c6cd20a1e72bad2d8ce82f411c37f18666856ef14dfd381add5ecd40ef92f'),
    @('PREPARATION-REPAIR01.md', 1046, '5f206acd87f5c0b130730e3870ed3abb13948beb52a238e23a644d0549ba79bc'),
    @('ROOT-HANDOFF.md', 1565, 'a2bcb5c0e3130f9dd7475f9a1d06541f660e2569f134dad68be20abfb217edba')
)
$rows = [Collections.Generic.List[object]]::new()
foreach ($r in $original) {
    $rows.Add([ordered]@{
        source = Join-Path $preparation $r[0]
        destination = 'original-preparation/' + $r[0]
        bytes = [long]$r[1]; sha256 = $r[2]
    })
}
$extra = @(
    @($preparation, 'INPUT-SELECTION.json', 'INPUT-SELECTION.json', 2220, '874b686d4a078d37385cac6b5a860a21aebeec08781d2ec150cd3f2e0491b277'),
    @($proposal, 'CANONICAL-BRIEF.md', 'CANONICAL-BRIEF.md', 3950, '23ab81309cf61b840aa8e2d666eba8449bcf941d9d91cc383ad7b875581fb15e'),
    @($proposal, 'canonical-brief-change.diff', 'canonical-brief-change.diff', 860, '4d02cb3abe7a555306547bf3d39a7197c836c2867e21dbeaf5fb6a4d6b017c3d'),
    @($proposal, 'MATERIALIZATION-PLAN.md', 'MATERIALIZATION-PLAN.md', 2080, 'f183ece1b7fcd4b25ee1919deba5121087f0d6c7293b5a94d4785cf7e906600f'),
    @($proposal, '.gitattributes', '.gitattributes', 8, '705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da')
)
foreach ($r in $extra) {
    $rows.Add([ordered]@{
        source = Join-Path $r[0] $r[1]; destination = $r[2]
        bytes = [long]$r[3]; sha256 = $r[4]
    })
}
$scriptRel = Join-Path $proposal 'materialize.ps1'
if ([IO.Path]::GetFullPath($PSCommandPath) -ine (Join-Path $checkout $scriptRel)) {
    throw 'Run only the fixed reviewed proposal script'
}
$scriptBytes = Read-Fixed $PSCommandPath
if ((Hash-Bytes $scriptBytes) -cne $ReviewedScriptSha256) { throw 'Script review hash mismatch' }
$rows.Add([ordered]@{
    source = $scriptRel; destination = 'materialize.ps1'
    bytes = $scriptBytes.Length; sha256 = $ReviewedScriptSha256
})
if ($rows.Count -ne 14) { throw 'Fixed copy membership mismatch' }
$cached = @{}
foreach ($row in $rows) {
    if (-not $cached.ContainsKey($row.source)) {
        $cached[$row.source] = Read-Fixed (Join-Path $checkout $row.source)
    }
    Check-Bytes $cached[$row.source] $row.bytes $row.sha256 $row.source
    [void](Proof-Path $row.destination)
}
$map = $utf8.GetString($cached[(Join-Path $preparation 'INPUT-SELECTION.json')]) | ConvertFrom-Json
if (($map.files.id -join ',') -cne 'A-01,A-02,A-03,A-04,A-05' -or
    $map.selected_count -ne 5 -or $map.selected_bytes -ne 65576 -or $map.selected_lines -ne 1286) {
    throw 'Five-file source scope changed'
}
$selectedBefore = @{}
foreach ($selected in $map.files) {
    # The exact map hash above binds all five relative text paths and identities.
    $path = [IO.Path]::GetFullPath((Join-Path $checkout $selected.path))
    if (-not $path.StartsWith($checkout + '\docs\library\proof\windows-stable-directory-qualification-2026-09-13\proposal01\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Selected source path outside the fixed source scope'
    }
    $bytes = Read-Fixed $path
    Check-Bytes $bytes $selected.bytes $selected.sha256 $selected.id
    if ($utf8.GetString($bytes).Split([char]10).Count -ne $selected.lines) { throw 'Catalog count changed' }
    $selectedBefore[$selected.path] = $bytes
}
$oldText = $utf8.GetString($cached[(Join-Path $preparation 'BRIEF.md')])
$oldPhrase = '; it does not repeat or supersede that measurement.'
$newPhrase = '. The earlier review remains failed; no product measurement is repeated.'
if (($oldText.Split($oldPhrase, [StringSplitOptions]::None)).Count -ne 2) { throw 'Expected wording is not unique' }
$expectedCanonical = $utf8.GetBytes($oldText.Replace($oldPhrase, $newPhrase))
$canonicalBytes = $cached[(Join-Path $proposal 'CANONICAL-BRIEF.md')]
Check-Bytes $expectedCanonical $canonicalBytes.Length (Hash-Bytes $canonicalBytes) 'only approved prose change'
if ((Test-Path -LiteralPath $proof) -or (Test-Path -LiteralPath $canonical)) {
    throw 'Destination already exists; preserve it and do not overwrite'
}
[void][IO.Directory]::CreateDirectory($proof)
$manifestRows = [Collections.Generic.List[object]]::new()
foreach ($row in $rows) {
    $path = Proof-Path $row.destination
    Write-New $path $cached[$row.source]
    Check-Bytes (Read-Fixed $path) $row.bytes $row.sha256 $row.destination
    $manifestRows.Add([ordered]@{path=$row.destination;bytes=$row.bytes;sha256=$row.sha256})
}
Write-New $canonical $canonicalBytes
Check-Bytes (Read-Fixed $canonical) 3950 '23ab81309cf61b840aa8e2d666eba8449bcf941d9d91cc383ad7b875581fb15e' 'external canonical brief'
foreach ($source in $cached.Keys) {
    $before = $cached[$source]
    Check-Bytes (Read-Fixed (Join-Path $checkout $source)) $before.Length (Hash-Bytes $before) $source
}
foreach ($selected in $map.files) {
    Check-Bytes (Read-Fixed (Join-Path $checkout $selected.path)) $selected.bytes $selected.sha256 $selected.id
}
$receipt = [ordered]@{
    schema='uoink-documentary-copy-1'
    scope='Fixed source-review brief and preparation trail only; no dispatch or candidate execution'
    copied=$rows.ToArray()
    canonical_brief=[ordered]@{
        path='docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-BRIEF-2026-09-13.md'
        bytes=3950;sha256='23ab81309cf61b840aa8e2d666eba8449bcf941d9d91cc383ad7b875581fb15e'
    }
    selected_inputs_verified=$map.files
    source_inputs_unchanged=$true
}
$receiptBytes = $utf8.GetBytes(($receipt | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
Write-New (Proof-Path 'COPY-RECEIPT.json') $receiptBytes
$manifestRows.Add([ordered]@{path='COPY-RECEIPT.json';bytes=$receiptBytes.Length;sha256=(Hash-Bytes $receiptBytes)})
if ($manifestRows.Count -ne 15) { throw 'Proof payload count changed' }
$manifest = [ordered]@{schema='uoink-proof-sha256-1';files=@($manifestRows.ToArray() | Sort-Object path)}
$manifestBytes = $utf8.GetBytes(($manifest | ConvertTo-Json -Depth 6) + [Environment]::NewLine)
Write-New (Proof-Path 'SHA256.json') $manifestBytes
foreach ($row in $manifest.files) {
    Check-Bytes (Read-Fixed (Proof-Path $row.path)) $row.bytes $row.sha256 $row.path
}
Check-Bytes (Read-Fixed (Proof-Path 'SHA256.json')) $manifestBytes.Length (Hash-Bytes $manifestBytes) 'manifest'
$expectedNames = @($manifest.files.path) + @('SHA256.json')
$actualNames = @(Get-ChildItem -LiteralPath $proof -File -Recurse -Force | ForEach-Object {
    $_.FullName.Substring($proof.Length + 1).Replace('\', '/')
})
if ((($actualNames | Sort-Object) -join '|') -cne (($expectedNames | Sort-Object) -join '|')) {
    throw 'Exact proof membership differs'
}
[ordered]@{
    proof=$proof;payloads=15
    payload_bytes=($manifest.files | Measure-Object bytes -Sum).Sum
    manifest_sha256=(Hash-Bytes $manifestBytes)
    canonical_brief_sha256=(Hash-Bytes $canonicalBytes)
    source_inputs_unchanged=$true
    scope='Documentary copy only'
} | ConvertTo-Json
exit 0
