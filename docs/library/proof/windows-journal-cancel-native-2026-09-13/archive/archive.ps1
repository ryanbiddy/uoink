param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPinsSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-native-journal-cancel-proposal01/archive.ps1'
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
    $info=Get-Item -LiteralPath $Path -Force
    Require (-not $info.PSIsContainer -and $Row.bytes -ge 0 -and $Row.bytes -le $cap -and $info.Length -eq $Row.bytes) 'Input size/cap mismatch'
    Require ($Row.sha256 -cmatch '^[0-9a-f]{64}$') 'Invalid input digest'
    $name=[IO.Path]::GetFileName($Path)
    $fixtureNames=@('config.json','model.bin','preprocessor_config.json','tokenizer.json','vocabulary.json')
    $fixture=$name -cin $fixtureNames -and $SourceRelative -ceq ('_scratch/windows-journal-cancel01/'+$name)
    Require ($fixture -or $name -ceq '.gitattributes' -or [IO.Path]::GetExtension($Path) -cin @('.py','.ps1','.md','.json','.diff','.txt','.log')) 'Non-text input refused before read'
    Require (-not $SourceRelative.StartsWith('_scratch/windows-journal-cancel01/registry/',[StringComparison]::Ordinal)) 'Filesystem journal excluded'
    $bytes=[IO.File]::ReadAllBytes($Path)
    Require ($bytes.LongLength -eq $Row.bytes -and (Digest $bytes) -ceq $Row.sha256) 'Input bytes/hash mismatch'
    $text=$utf8.GetString($bytes)
    Require (-not ($bytes -contains 0)) 'NUL in text input'
    if ($fixture) {
        $expected='Uoink generated adoption fixture: '+$name+". No model data.`n"
        Require ($bytes.LongLength -le 75 -and $text -ceq $expected -and (Digest ([Text.Encoding]::ASCII.GetBytes($expected))) -ceq $Row.sha256) 'Exact generated ASCII fixture required'
    }
    Chain $Path
    $after=Get-Item -LiteralPath $Path -Force
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

# Fixed documentary copier; do not execute any copied source, test or native probe.
# Reviewed writer04 core reused. The physical registry/journal is never traversed/read.
Require ([IO.Path]::GetFullPath($PSCommandPath) -ceq [IO.Path]::GetFullPath((Join-Path $repo $scriptRelative))) 'Fixed archive source required'
$self=Row $scriptRelative 'archive/archive.ps1' (Get-Item -LiteralPath $PSCommandPath).Length $ExpectedScriptSha256
$null=Read-Verified $PSCommandPath $self $scriptRelative
$proposal='_scratch/archive-native-journal-cancel-proposal01'
$mapRow=Row ($proposal+'/COPY-MAP.json') 'archive/COPY-MAP.json' 28438 'ba398da5aa929969f148a854818f732e94f0694dbf4c2230626ec7d4656e407a'
$mapRaw=Read-Verified (Join-Path $repo $mapRow.source) $mapRow $mapRow.source
$map=$utf8.GetString($mapRaw) | ConvertFrom-Json
Require ($map.schema -ceq 'uoink.native-journal-cancel-copy.v1' -and $map.payload_count -eq 95 -and @($map.files).Count -eq 95 -and $map.total_payload_bytes -eq 1368823) 'Fixed 95-payload map required'
Require ($map.status -ceq 'PASSED_GENERATED_NATIVE_CLEAN_CANCEL_ONLY' -and $map.proof -ceq 'docs/library/proof/windows-journal-cancel-native-2026-09-13') 'Fixed native-cancel scope required'
Require ($map.run -ceq '_scratch/windows-journal-cancel01' -and @($map.run_omitted_directories).Count -eq 1 -and $map.run_omitted_directories[0] -ceq 'registry') 'Exact journal exclusion required'
$pinsPath=Join-Path $repo ($proposal+'/PINS.json')
$pinsRow=Row ($proposal+'/PINS.json') 'archive/PINS.json' (Get-Item -LiteralPath $pinsPath).Length $ExpectedPinsSha256
$pinsRaw=Read-Verified $pinsPath $pinsRow $pinsRow.source
$pins=$utf8.GetString($pinsRaw) | ConvertFrom-Json
Require ($pins.schema -ceq 'uoink.native-journal-cancel-archive-pins.v1' -and $pins.count -eq 2 -and @($pins.files).Count -eq 2) 'Two preparation pins required'
foreach($expected in @($self,$mapRow)) {
    $leaf=[IO.Path]::GetFileName($expected.source)
    $found=@($pins.files | Where-Object {$_.path -ceq $leaf})
    Require ($found.Count -eq 1 -and $found[0].bytes -eq $expected.bytes -and $found[0].sha256 -ceq $expected.sha256) 'Preparation pin mismatch'
}
$payloadRows=@();$sum=0L
foreach($entry in $map.files) {$payloadRows+=Row $entry.source $entry.destination $entry.bytes $entry.sha256;$sum+=$entry.bytes}
Require ($sum -eq 1368823) 'Payload total differs'
$rows=@($payloadRows)+@($self,$mapRow,$pinsRow)
$destinations=@{};$sources=@{}
foreach($row in $rows) {
    Require (-not $destinations.ContainsKey($row.destination) -and -not $sources.ContainsKey($row.source)) 'Duplicate source/destination'
    Require ($row.destination -cnotin @('.gitattributes','COPY-CHECKS.json','SHA256.json')) 'Reserved output name'
    $destinations[$row.destination]=$true;$sources[$row.source]=$true
}

function Check-Sources {
    foreach($folder in $map.folders) {
        Canonical $folder.source
        $prefix=$folder.source+'/'
        $wanted=@($payloadRows | Where-Object {$_.source.StartsWith($prefix,[StringComparison]::Ordinal)} | ForEach-Object {$_.source.Substring($prefix.Length)})
        Exact-Members (Join-Path $repo $folder.source) $wanted
    }
    # Inspect only direct run members. Do not enumerate or read the registry.
    $runRoot=Join-Path $repo $map.run;Chain $runRoot
    $items=@(Get-ChildItem -LiteralPath $runRoot -Force)
    foreach($item in $items) {Require (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse run member refused'}
    $directories=@($items | Where-Object {$_.PSIsContainer})
    Require ($directories.Count -eq 1 -and $directories[0].Name -ceq 'registry') 'Only the excluded registry directory may be present'
    $runNames=@($items | Where-Object {-not $_.PSIsContainer} | ForEach-Object {$_.Name} | Sort-Object)
    $prefix=$map.run+'/'
    $wanted=@($payloadRows | Where-Object {$_.source.StartsWith($prefix,[StringComparison]::Ordinal)} | ForEach-Object {$_.source.Substring($prefix.Length)} | Sort-Object)
    Require ($runNames.Count -eq 36 -and $wanted.Count -eq 36 -and ($runNames -join "`n") -ceq ($wanted -join "`n")) 'Exact 36 direct run files required'
    Exact-Members (Join-Path $repo $proposal) @('archive.ps1','COPY-MAP.json','PINS.json')
    foreach($row in $rows) {$null=Read-Verified (Join-Path $repo $row.source) $row $row.source}
    $prior=$map.prior_qualification
    Require ($prior.path -ceq 'docs/library/proof/windows-journal-cancel-qualification-2026-09-13/SHA256.json' -and $prior.commit -ceq '60b3bb5' -and $prior.recopied -ceq $false) 'Fixed prior qualification reference required'
    Chain (Join-Path $repo $prior.path)
    Require ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repo $prior.path)).Hash.ToLowerInvariant() -ceq $prior.sha256) 'Prior qualification seal changed'
}

$output=Join-Path $repo $map.proof
Chain ([IO.Path]::GetDirectoryName($output))
Require (-not (Test-Path -LiteralPath $output)) 'Fresh proof destination required; retain any partial attempt'
Check-Sources
Require (-not (Test-Path -LiteralPath $output)) 'Destination appeared before copying'
New-Directory $output
foreach($row in $rows) {
    $raw=Read-Verified (Join-Path $repo $row.source) $row $row.source
    Write-New (Join-Path $output $row.destination) $raw
    $null=Read-Verified (Join-Path $output $row.destination) $row $row.source
    $null=Read-Verified (Join-Path $repo $row.source) $row $row.source
}
Check-Sources
Write-New (Join-Path $output '.gitattributes') ($utf8.GetBytes("* -text`n"))
$checks=[ordered]@{
    scope='Documentary copies of one recorded generated native clean cancellation';recorded_status=$map.status;
    source_payloads=95;source_payload_bytes=1368823;copied_files=$rows.Count;copies=$rows;
    source_membership_and_hashes_checked_before_after=$true;all_copies_rehashed=$true;
    prior_qualification=$map.prior_qualification;per_file_cap_bytes=$cap;no_reparse_in_checked_chains=$true;
    physical_journal_read_hashed_or_copied=$false;registry_contents_enumerated=$false;
    generated_fixture_count=5;fixtures_match_exact_source_ascii=$true;
    support_checkpoint_or_converted_output_accessed=$false;tests_or_native_observations_rerun=0;
    interruption_restart_power_loss_model_or_release_accepted=$false;
    preparation_failure='Initial inventory pair construction failed before writes; its clearly labeled tool transcript and correction are preserved';
    script_sha256=$ExpectedScriptSha256;pins_sha256=$ExpectedPinsSha256
}
Write-New (Join-Path $output 'COPY-CHECKS.json') (Json-Bytes $checks)
$expected=@($rows | ForEach-Object {$_.destination})+@('.gitattributes','COPY-CHECKS.json')
Exact-Members $output $expected
$sealRows=@()
foreach($name in ($expected | Sort-Object)) {
    $path=Join-Path $output $name;Chain $path;$raw=[IO.File]::ReadAllBytes($path)
    Require ($raw.LongLength -le $cap) 'Seal member exceeds cap'
    $sealRows += [ordered]@{path=$name;bytes=$raw.LongLength;sha256=(Digest $raw)}
}
Write-New (Join-Path $output 'SHA256.json') (Json-Bytes ([ordered]@{files=$sealRows}))
Exact-Members $output (@($expected)+@('SHA256.json'))
foreach($row in $rows) {$null=Read-Verified (Join-Path $output $row.destination) $row $row.source}
foreach($row in $sealRows) {Require ((Get-FileHash -LiteralPath (Join-Path $output $row.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Final seal hash mismatch'}
Check-Sources
[ordered]@{proof=$map.proof;recorded_status=$map.status;copied_files=$rows.Count;sealed_payloads=$sealRows.Count;physical_files=($sealRows.Count+1);manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $output 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
