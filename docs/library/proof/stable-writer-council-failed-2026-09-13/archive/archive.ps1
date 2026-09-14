param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPinsSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-stable-writer-council-failed-proposal01/archive.ps1'
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

# Data-only derivative of reviewed archive-writer04 core 61024d126c7b98e05e47577b05b5c004539f4857baef2a20da8229ced564f72b.
# No candidate/check script, test, native observation, model or support binary is executed/read.
# Git commands inspect only fixed committed proof blobs and corresponding text files.
Require ([IO.Path]::GetFullPath($PSCommandPath) -ceq [IO.Path]::GetFullPath((Join-Path $repo $scriptRelative))) 'Fixed archive source required'
$self = Row $scriptRelative 'archive/archive.ps1' (Get-Item -LiteralPath $PSCommandPath).Length $ExpectedScriptSha256
$null = Read-Verified $PSCommandPath $self $scriptRelative
$proposal = '_scratch/archive-stable-writer-council-failed-proposal01'
$mapRow = Row ($proposal+'/COPY-MAP.json') 'archive/COPY-MAP.json' 21744 '975b81f29300b0b18c608fade5150d2e5bb315b0cf4402df93859141ee284a19'
$mapRaw = Read-Verified (Join-Path $repo $mapRow.source) $mapRow $mapRow.source
$map = $utf8.GetString($mapRaw) | ConvertFrom-Json
Require ($map.schema -ceq 'uoink.stable-writer-council-failed-copy.v1' -and $map.payload_count -eq 19 -and @($map.files).Count -eq 19 -and $map.total_payload_bytes -eq 240606) 'Fixed payload map required'
Require ($map.run_id -ceq '2b39a17c-9418-4cfe-85d8-ecc07d7cdde2' -and $map.recorded_run_status -ceq 'completed' -and $map.review_accuracy -ceq 'FAILED' -and $map.component_measurements_changed -ceq $false) 'Recorded review status differs'
Require ($map.proof -ceq 'docs/library/proof/stable-writer-council-failed-2026-09-13' -and $map.git_commit -ceq 'b45aaad866d67823a319779bb854018b8cb218f9' -and $map.git_proof_count -eq 52 -and @($map.git_proofs).Count -eq 52) 'Fixed proof bindings required'
$pinsPath = Join-Path $repo ($proposal+'/PINS.json')
$pinsRow = Row ($proposal+'/PINS.json') 'archive/PINS.json' (Get-Item -LiteralPath $pinsPath).Length $ExpectedPinsSha256
$pinsRaw = Read-Verified $pinsPath $pinsRow $pinsRow.source
$pins = $utf8.GetString($pinsRaw) | ConvertFrom-Json
Require ($pins.schema -ceq 'uoink.stable-writer-council-archive-source-pins.v1' -and $pins.count -eq 2 -and @($pins.files).Count -eq 2) 'Two preparation pins required'
foreach ($expected in @($self,$mapRow)) {
    $leaf=[IO.Path]::GetFileName($expected.source)
    $matches=@($pins.files | Where-Object {$_.path -ceq $leaf})
    Require ($matches.Count -eq 1 -and $matches[0].bytes -eq $expected.bytes -and $matches[0].sha256 -ceq $expected.sha256) 'Preparation pin mismatch'
}
$payloadRows=@(); $sum=0L
foreach ($entry in $map.files) { $payloadRows += Row $entry.source $entry.destination $entry.bytes $entry.sha256; $sum += $entry.bytes }
Require ($sum -eq 240606) 'Payload total differs'
$rows=@($payloadRows)+@($self,$mapRow,$pinsRow)
$destinations=@{}; $sources=@{}
foreach ($row in $rows) {
    Require (-not $destinations.ContainsKey($row.destination) -and -not $sources.ContainsKey($row.source)) 'Duplicate source/destination'
    Require ($row.destination -cnotin @('.gitattributes','COPY-CHECKS.json','SHA256.json')) 'Reserved output name'
    $destinations[$row.destination]=$true; $sources[$row.source]=$true
}

function Git-Lines([string[]]$Arguments) {
    $PSNativeCommandUseErrorActionPreference=$false
    $answer=@(& git -C $repo @Arguments)
    $native=$global:LASTEXITCODE
    Require ($native -is [int] -and $native -eq 0) 'Read-only Git command failed'
    return $answer
}
function Check-GitProofs {
    $names=@(); $seen=@{}
    foreach ($row in $map.git_proofs) {
        Canonical $row.path
        Require ($row.path.StartsWith('docs/library/proof/',[StringComparison]::Ordinal) -and -not $seen.ContainsKey($row.path) -and $row.git_blob -cmatch '^[0-9a-f]{40}$') 'Fixed unique Git proof text required'
        $seen[$row.path]=$true; $names += $row.path
        $null=Read-Verified (Join-Path $repo $row.path) $row $row.path
    }
    $tree=@(Git-Lines (@('ls-tree','-r',$map.git_commit,'--')+$names))
    $blobs=@(Git-Lines (@('hash-object','--no-filters','--')+$names))
    Require ($tree.Count -eq 52 -and $blobs.Count -eq 52) 'Exact Git proof membership required'
    $treeMap=@{}
    foreach ($line in $tree) {
        Require ($line -cmatch '^100644 blob ([0-9a-f]{40})\t(.+)$') 'Plain committed blob required'
        $oid=$Matches[1]; $name=$Matches[2]
        Require (-not $treeMap.ContainsKey($name)) 'Duplicate Git proof name'
        $treeMap[$name]=$oid
    }
    for ($index=0; $index -lt 52; $index++) {
        $row=$map.git_proofs[$index]
        Require ($treeMap.ContainsKey($row.path) -and $treeMap[$row.path] -ceq $row.git_blob -and $blobs[$index] -ceq $row.git_blob) 'Committed/worktree proof blob mismatch'
        $null=Read-Verified (Join-Path $repo $row.path) $row $row.path
    }
}
function Check-Sources {
    $prefix='_scratch/gemini-stable-writer-accuracy-review01/'
    $expected=@($payloadRows | Where-Object {$_.source.StartsWith($prefix,[StringComparison]::Ordinal)} | ForEach-Object {$_.source.Substring($prefix.Length)})
    Require ($expected.Count -eq 6) 'Six accuracy-review files required'
    Exact-Members (Join-Path $repo $prefix) $expected
    $observed=@(Get-ChildItem -LiteralPath (Join-Path $repo '_scratch') -Filter 'STABLE-WRITER-COUNCIL01*' -Force)
    $wanted=@($payloadRows | Where-Object {$_.source.StartsWith('_scratch/STABLE-WRITER-COUNCIL01',[StringComparison]::Ordinal)} | ForEach-Object {[IO.Path]::GetFileName($_.source)} | Sort-Object)
    Require ($observed.Count -eq 7 -and $wanted.Count -eq 7 -and ((@($observed.Name | Sort-Object)) -join "`n") -ceq ($wanted -join "`n")) 'Seven council records/patch required'
    Exact-Members (Join-Path $repo $proposal) @('archive.ps1','COPY-MAP.json','PINS.json')
    foreach ($row in $rows) { $null=Read-Verified (Join-Path $repo $row.source) $row $row.source }
    Check-GitProofs
}

$output=Join-Path $repo $map.proof
Chain ([IO.Path]::GetDirectoryName($output))
Require (-not (Test-Path -LiteralPath $output)) 'Fresh proof destination required; retain any partial attempt'
Check-Sources
Require (-not (Test-Path -LiteralPath $output)) 'Destination appeared before copying'
New-Directory $output
foreach ($row in $rows) {
    $raw=Read-Verified (Join-Path $repo $row.source) $row $row.source
    Write-New (Join-Path $output $row.destination) $raw
    $null=Read-Verified (Join-Path $output $row.destination) $row $row.source
    $null=Read-Verified (Join-Path $repo $row.source) $row $row.source
}
Check-Sources
Write-New (Join-Path $output '.gitattributes') ($utf8.GetBytes("* -text`n"))
$checks=[ordered]@{
    scope='Fixed documentary text/control copies only'; run_id=$map.run_id; recorded_run_status='completed'; review_accuracy='FAILED';
    component_measurements_changed=$false; council_acceptance=$false; tests_or_observations_rerun=0;
    source_payloads=19; source_payload_bytes=240606; copied_files=$rows.Count; copies=$rows;
    source_membership_and_hashes_checked_before_after=$true; all_copies_rehashed=$true;
    git_commit=$map.git_commit; git_proof_count=52; git_proof_hashes_and_blobs_checked_before_after=$true; git_proofs=$map.git_proofs;
    per_file_cap_bytes=$cap; no_reparse_in_checked_chains=$true;
    saved_completion_truncation='Original markers and omissions preserved; no reconstructed tool output or proof of complete source reading';
    script_sha256=$ExpectedScriptSha256; pins_sha256=$ExpectedPinsSha256
}
Write-New (Join-Path $output 'COPY-CHECKS.json') (Json-Bytes $checks)
$expected=@($rows | ForEach-Object {$_.destination})+@('.gitattributes','COPY-CHECKS.json')
Exact-Members $output $expected
$sealRows=@()
foreach ($name in ($expected | Sort-Object)) {
    $path=Join-Path $output $name; Chain $path
    $raw=[IO.File]::ReadAllBytes($path)
    Require ($raw.LongLength -le $cap) 'Seal member exceeds cap'
    $sealRows += [ordered]@{path=$name;bytes=$raw.LongLength;sha256=(Digest $raw)}
}
Write-New (Join-Path $output 'SHA256.json') (Json-Bytes ([ordered]@{files=$sealRows}))
Exact-Members $output (@($expected)+@('SHA256.json'))
foreach ($row in $rows) { $null=Read-Verified (Join-Path $output $row.destination) $row $row.source }
foreach ($row in $sealRows) { Require ((Get-FileHash -LiteralPath (Join-Path $output $row.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Final seal hash mismatch' }
Check-Sources
[ordered]@{proof=$map.proof;recorded_run_status='completed';review_accuracy='FAILED';copied_files=$rows.Count;sealed_payloads=$sealRows.Count;physical_files=($sealRows.Count+1);manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $output 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
