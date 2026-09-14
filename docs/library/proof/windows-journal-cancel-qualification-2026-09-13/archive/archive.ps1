param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-journal-cancel-qualification-proposal01/archive.ps1'
$cap = 1048576L
$utf8 = [Text.UTF8Encoding]::new($false,$true)

function Require($Condition,[string]$Reason) { if (-not $Condition) { throw $Reason } }
function Canonical([string]$Name) {
    Require ($Name -cmatch '^[A-Za-z0-9_./+\-]+$' -and $Name -notmatch '(^/|(^|/)\.\.?(/|$)|//)') 'Invalid relative path'
}
function Chain([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    Require (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse member refused'
    $dir = if ($item.PSIsContainer) { [IO.DirectoryInfo]::new($item.FullName) } else { [IO.DirectoryInfo]::new($item.DirectoryName) }
    while ($null -ne $dir) {
        $part = Get-Item -LiteralPath $dir.FullName -Force
        Require ($part.PSIsContainer -and ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Unsafe ancestor'
        $dir = $dir.Parent
    }
}
function Digest([byte[]]$Bytes) { [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant() }
function Read-Verified([string]$Path,$Row,[string]$SourceRelative) {
    Chain $Path
    $info = Get-Item -LiteralPath $Path -Force
    Require (-not $info.PSIsContainer -and $Row.bytes -ge 0 -and $Row.bytes -le $cap -and $info.Length -eq $Row.bytes) 'Input size/cap mismatch'
    Require ($Row.sha256 -cmatch '^[0-9a-f]{64}$') 'Invalid input digest'
    $name = [IO.Path]::GetFileName($Path)
    Require ($name -ceq '.gitattributes' -or [IO.Path]::GetExtension($Path) -cin @('.py','.ps1','.md','.json','.diff','.txt','.log')) 'Non-text input refused before read'
    Require ($name -cne 'RYAN-D2-DECISION.json') 'Real conversion authority outside fixed scope'
    if ($name -ceq 'ROOT-ADMISSION.json') {
        Require ($SourceRelative -cin @(
            '_scratch/windows-journal-cancel-fake-proposal01/ROOT-ADMISSION.json',
            '_scratch/windows-journal-cancel-fake-proposal01/journal-cancel-fake01/ROOT-ADMISSION.json',
            '_scratch/astra-journal-cancel-confirmation01/ROOT-ADMISSION.json',
            '_scratch/astra-journal-cancel-confirmation01/journal-cancel-fake01/ROOT-ADMISSION.json'
        )) 'Admission outside the two fixed fake observations'
    }
    $bytes = [IO.File]::ReadAllBytes($Path)
    Require ($bytes.LongLength -eq $Row.bytes -and (Digest $bytes) -ceq $Row.sha256) 'Input bytes/hash mismatch'
    $null = $utf8.GetString($bytes)
    Require (-not ($bytes -contains 0)) 'NUL in text input'
    Chain $Path
    $after = Get-Item -LiteralPath $Path -Force
    Require ($after.Length -eq $info.Length -and $after.LastWriteTimeUtc.Ticks -eq $info.LastWriteTimeUtc.Ticks) 'Input metadata changed during read'
    return ,$bytes
}
function Members([string]$Root) {
    Chain $Root
    $pending = [Collections.Generic.Stack[string]]::new(); $pending.Push($Root)
    $names = [Collections.Generic.List[string]]::new()
    while ($pending.Count -gt 0) {
        foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            Require (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse tree member'
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else { $names.Add([IO.Path]::GetRelativePath($Root,$item.FullName).Replace([char]92,[char]47)) }
        }
    }
    return @($names | Sort-Object)
}
function Exact-Members([string]$Root,$Expected) {
    $actual = @(Members $Root); $wanted = @($Expected | Sort-Object)
    Require ($actual.Count -eq $wanted.Count -and ($actual -join "`n") -ceq ($wanted -join "`n")) ('Membership changed: '+$Root)
}
function New-Directory([string]$Path) {
    if (Test-Path -LiteralPath $Path) { Chain $Path; Require ((Get-Item -LiteralPath $Path).PSIsContainer) 'Directory required'; return }
    $parent = [IO.Path]::GetDirectoryName($Path)
    New-Directory $parent
    $null = [IO.Directory]::CreateDirectory($Path)
    Chain $Path
}
function Write-New([string]$Path,[byte[]]$Bytes) {
    Require ($Bytes.LongLength -le $cap) 'Output cap exceeded'
    New-Directory ([IO.Path]::GetDirectoryName($Path))
    Require (-not (Test-Path -LiteralPath $Path)) 'Exclusive output required'
    $stream = [IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try { $stream.Write($Bytes,0,$Bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    Chain $Path
}
function Json-Bytes($Value) { return ,$utf8.GetBytes(($Value | ConvertTo-Json -Depth 12)+"`n") }
function Row([string]$Source,[string]$Destination,[long]$Bytes,[string]$Sha) {
    Canonical $Source; Canonical $Destination
    return [ordered]@{source=$Source;destination=$Destination;bytes=$Bytes;sha256=$Sha}
}

Require ([IO.Path]::GetFullPath($PSCommandPath) -ceq [IO.Path]::GetFullPath((Join-Path $repo $scriptRelative))) 'Fixed archive source required'
Chain $PSCommandPath
$self = Row $scriptRelative 'archive/archive.ps1' (Get-Item -LiteralPath $PSCommandPath).Length $ExpectedScriptSha256
$null = Read-Verified $PSCommandPath $self $scriptRelative

$specs = @(
    [ordered]@{
        name='journal-cancel-fake89'; inventory='_scratch/journal-cancel-qualification-copy-inventory01'; count=206; bytes=2370626
        proof='docs/library/proof/windows-journal-cancel-qualification-2026-09-13'; status='PASSED_TWO_GENERATED_FAKE89_OBSERVATIONS_ONLY'
        folders=@('windows-journal-cancel-fake-proposal01','astra-journal-cancel-confirmation01','windows-journal-cancel-source-review01','windows-journal-cancel-complementary-review01','windows-journal-cancel-author-result-review01')
        singles=@('_scratch/JOURNAL-CANCEL-FAKE89-ADMISSION-ACTUAL01.json','_scratch/JOURNAL-CANCEL-FAKE89-AUTHOR-ACTUAL01.json','_scratch/JOURNAL-CANCEL-FAKE89-INDEPENDENT-ACTUAL01.json','_scratch/JOURNAL-CANCEL-FAKE89-INDEPENDENT-PREP-ACTUAL01.json','_scratch/JOURNAL-CANCEL-FAKE89-PAIR-CHECK-ACTUAL01.json','_scratch/JOURNAL-CANCEL-FAKE89-PAIR-CHECK01.json','_scratch/JOURNAL-CANCEL-FAKE89-ROOT-REVIEW01.md','_scratch/admit-journal-cancel-fake89-01.ps1','_scratch/prepare_journal_cancel_confirmation01.ps1','_scratch/check-journal-cancel-fake89-pair01.py','docs/library/ASTRA-JOURNAL-CANCEL-FAKE89-VERDICT-2026-09-13.md')
        inventory_files=@(
            @('.gitattributes',8,'705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
            @('COPY-INVENTORY.json',61607,'1c015a72a1ee6874795fef0f9a3691bd5d845d74674b135a544661c7da244fe6'),
            @('README.md',2053,'30d79345c454ce0cb6df687b1931d32898caeed4d7e5d639b7a4a3d9883c48fb'))
        extras=@(
            (Row '_scratch/journal-cancel-qualification-inventory-preparation01/INVENTORY01-ACTUAL.json' 'inventory-preparation/INVENTORY01-ACTUAL.json' 533 'c54c2c1c2608bd73dff822d8637a589d335cd7f804e34907c521eae86521cd60'),
            (Row '_scratch/journal-cancel-qualification-inventory-preparation01/INVENTORY02-ACTUAL.json' 'inventory-preparation/INVENTORY02-ACTUAL.json' 1534 'c58b47edd4ee9ba1834fb28aa70f142342cf04bc434b057355152d60cf9d95c4'),
            (Row '_scratch/journal-cancel-qualification-inventory-preparation01/PREPARATION-CORRECTION.md' 'inventory-preparation/PREPARATION-CORRECTION.md' 614 '87616e1a4d53f5ea9990d639b74bfad74692c7e7e310a81b3dc5f9562fa2d01e'),
            (Row '_scratch/journal-cancel-qualification-inventory-preparation01/prepare_inventory.ps1' 'inventory-preparation/prepare_inventory.ps1' 6139 'ffb83d9b4d49cd4435de33e3d8c2f93234c27a7344bb16eccc7b1c15eeba28a7'))
        extra_folders=@('_scratch/journal-cancel-qualification-inventory-preparation01')
    }
)

function Check-Sources($Spec) {
    foreach ($folder in $Spec.folders) {
        $prefix = '_scratch/'+$folder+'/'
        $expected = @($Spec.payload_rows | Where-Object {$_.source.StartsWith($prefix,[StringComparison]::Ordinal)} | ForEach-Object {$_.source.Substring($prefix.Length)})
        Exact-Members (Join-Path $repo ('_scratch/'+$folder)) $expected
    }
    Exact-Members (Join-Path $repo $Spec.inventory) @($Spec.inventory_files | ForEach-Object {$_[0]})
    foreach ($folder in $Spec.extra_folders) {
        $prefix=$folder+'/'
        $expected=@($Spec.extras | Where-Object {$_.source.StartsWith($prefix,[StringComparison]::Ordinal)} | ForEach-Object {$_.source.Substring($prefix.Length)})
        Exact-Members (Join-Path $repo $folder) $expected
    }
    foreach ($row in $Spec.rows) { $null = Read-Verified (Join-Path $repo $row.source) $row $row.source }
}

# Check all sources and the fresh destination before creating the proof.
foreach ($spec in $specs) {
    $mapPin=$null
    foreach ($candidate in $spec.inventory_files) { if ($candidate[0] -ceq 'COPY-INVENTORY.json') {$mapPin=$candidate} }
    Require ($null -ne $mapPin) 'Fixed inventory pin missing'
    $mapRow = Row ($spec.inventory+'/COPY-INVENTORY.json') 'inventory/COPY-INVENTORY.json' $mapPin[1] $mapPin[2]
    $mapRaw = Read-Verified (Join-Path $repo $mapRow.source) $mapRow $mapRow.source
    $map = $utf8.GetString($mapRaw) | ConvertFrom-Json
    Require ($map.payload_count -eq $spec.count -and @($map.files).Count -eq $spec.count -and $map.total_payload_bytes -eq $spec.bytes -and $map.status -ceq $spec.status) 'Pinned inventory contract differs'
    $payloadRows = @(); $sum=0L
    foreach ($entry in $map.files) {
        $allowed = $false
        foreach ($folder in $spec.folders) { if ($entry.source.StartsWith('_scratch/'+$folder+'/',[StringComparison]::Ordinal)) {$allowed=$true} }
        if ($entry.source -cin $spec.singles) {$allowed=$true}
        Require $allowed 'Source outside fixed folders and files'
        $payloadRows += Row $entry.source $entry.destination $entry.bytes $entry.sha256; $sum += $entry.bytes
    }
    Require ($sum -eq $spec.bytes) 'Inventory byte total differs'
    $spec.payload_rows = $payloadRows
    $spec.rows = @($payloadRows)+@($spec.extras)+@($self)
    foreach ($entry in $spec.inventory_files) { $spec.rows += Row ($spec.inventory+'/'+$entry[0]) ('inventory/'+$entry[0]) $entry[1] $entry[2] }
    $destinations=@{}; $sources=@{}
    foreach ($row in $spec.rows) {
        Require (-not $destinations.ContainsKey($row.destination) -and -not $sources.ContainsKey($row.source)) 'Duplicate source/destination'
        Require ($row.destination -cnotin @('.gitattributes','COPY-CHECKS.json','SHA256.json')) 'Reserved output name'
        $destinations[$row.destination]=$true; $sources[$row.source]=$true
    }
    $spec.output = Join-Path $repo $spec.proof
    Chain ([IO.Path]::GetDirectoryName($spec.output))
    Require (-not (Test-Path -LiteralPath $spec.output)) 'Fresh proof folder required'
    Check-Sources $spec
}

$results=@()
foreach ($spec in $specs) {
    Require (-not (Test-Path -LiteralPath $spec.output)) 'Proof folder appeared before copying'
    New-Directory $spec.output
    foreach ($row in $spec.rows) {
        $raw = Read-Verified (Join-Path $repo $row.source) $row $row.source
        $destination = Join-Path $spec.output $row.destination
        Write-New $destination $raw
        $null = Read-Verified $destination $row $row.source
        $null = Read-Verified (Join-Path $repo $row.source) $row $row.source
    }
    Check-Sources $spec
    Write-New (Join-Path $spec.output '.gitattributes') ($utf8.GetBytes("* -text`n"))
    $checks = [ordered]@{scope='Documentary byte copies only';recorded_status=$spec.status;inventory_payloads=$spec.count;copied_files=$spec.rows.Count;source_membership_and_hashes_checked_before_after=$true;all_copies_rehashed=$true;per_file_cap_bytes=$cap;no_reparse_in_checked_chains=$true;native_cancellation_executed=$false;runtime_or_release_approved=$false;tests_or_observations_rerun=0;script_sha256=$ExpectedScriptSha256;copies=$spec.rows}
    Write-New (Join-Path $spec.output 'COPY-CHECKS.json') (Json-Bytes $checks)
    $expected = @($spec.rows | ForEach-Object {$_.destination})+@('.gitattributes','COPY-CHECKS.json')
    Exact-Members $spec.output $expected
    $sealRows = @()
    foreach ($name in ($expected | Sort-Object)) {
        $path=Join-Path $spec.output $name; Chain $path
        $raw=[IO.File]::ReadAllBytes($path)
        Require ($raw.LongLength -le $cap) 'Seal member exceeds cap'
        $sealRows += [ordered]@{path=$name;bytes=$raw.LongLength;sha256=(Digest $raw)}
    }
    Write-New (Join-Path $spec.output 'SHA256.json') (Json-Bytes ([ordered]@{files=$sealRows}))
    Exact-Members $spec.output (@($expected)+@('SHA256.json'))
    foreach ($row in $spec.rows) { $null=Read-Verified (Join-Path $spec.output $row.destination) $row $row.source }
    foreach ($row in $sealRows) { Require ((Get-FileHash -LiteralPath (Join-Path $spec.output $row.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Final seal hash mismatch' }
    $results += [ordered]@{proof=$spec.proof;recorded_status=$spec.status;copied_files=$spec.rows.Count;sealed_payloads=$sealRows.Count;manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $spec.output 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()}
}
foreach ($spec in $specs) { Check-Sources $spec }
$results | ConvertTo-Json -Depth 5
