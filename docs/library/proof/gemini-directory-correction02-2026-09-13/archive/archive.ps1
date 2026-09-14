param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-gemini-directory-correction02-proposal01/archive.ps1'
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
    Require ($name -ceq '.gitattributes' -or [IO.Path]::GetExtension($Path) -cin @('.py','.ps1','.md','.json','.diff','.txt','.log','.patch')) 'Non-text input refused before read'
    Require ($name -cnotin @('ROOT-ADMISSION.json','RYAN-D2-DECISION.json')) 'Runtime authority outside documentary review scope'
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
        name='gemini-directory-correction02'; inventory='_scratch/gemini-directory-correction02-copy-inventory01'; count=17; bytes=49473
        proof='docs/library/proof/gemini-directory-correction02-2026-09-13'; status='SOURCE_CONCLUSION_ACCEPTED_WITH_MANDATORY_CORRECTIONS'
        folders=@('gemini-stable-directory-correction02-peer-review01')
        singles=@('docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.md','docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.coverage.json','docs/library/ASTRA-GEMINI-DIRECTORY-CORRECTION02-VERDICT-2026-09-13.md','docs/library/proof/stable-directory-correction02-brief-2026-09-13/INPUT-SELECTION.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-APPLY-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-COMPLETION-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-DISPATCH-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-METADATA-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-POLL1-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-POLL2-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-ROOT-CHECK-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02-WORKER-PATCH-ACTUAL.json','_scratch/GEMINI-DIRECTORY-CORRECTION02.patch','_scratch/check-gemini-directory-correction02.py')
        inventory_files=@(
            @('.gitattributes',8,'705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
            @('COPY-INVENTORY.json',4794,'e5d4fa3fd3691bdc61289030a5477045b3a810bd245f379fce70cc3b57feac15'),
            @('INVENTORY-ACTUAL.json',349,'292e6f82b6ee17131f4a932098228093befc45980e7f12bd5c7c60d4203164f1'),
            @('README.md',1680,'1e4ab0929599862369e03ef5fc9e2f2557961ee3ac36719e069ad58d51a42440'))
        extras=@()
        extra_folders=@()
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
    $checks = [ordered]@{scope='Documentary byte copies only';recorded_status=$spec.status;inventory_payloads=$spec.count;copied_files=$spec.rows.Count;source_membership_and_hashes_checked_before_after=$true;all_copies_rehashed=$true;per_file_cap_bytes=$cap;no_reparse_in_checked_chains=$true;worker_view_trace_verified=$false;candidate_execution_performed=$false;tests_or_observations_rerun=0;script_sha256=$ExpectedScriptSha256;copies=$spec.rows}
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
