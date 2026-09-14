param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-writer-d2-proposal01/archive.ps1'
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
    $fixture = $SourceRelative -ceq '_scratch/windows-reservation-writer-exclusion02/model.bin'
    $journal = $SourceRelative -ceq '_scratch/windows-reservation-writer-exclusion02/registry/4640b95540b94d05-516b2100000002000000000000000000.journal'
    Require ($fixture -or $journal -or $name -ceq '.gitattributes' -or [IO.Path]::GetExtension($Path) -cin @('.py','.ps1','.md','.json','.diff','.txt','.log')) 'Non-text input refused before read'
    Require ($name -cnotin @('ROOT-ADMISSION.json','RYAN-D2-DECISION.json') -or $SourceRelative -ceq '_scratch/windows-reservation-writer-exclusion02/ROOT-ADMISSION.json') 'Actual D2 authority record refused'
    $bytes = [IO.File]::ReadAllBytes($Path)
    Require ($bytes.LongLength -eq $Row.bytes -and (Digest $bytes) -ceq $Row.sha256) 'Input bytes/hash mismatch'
    if ($fixture) {
        Require ($bytes.Length -eq 60 -and $Row.sha256 -ceq 'e0a9fc9e76fc24578e81900fcb506dc23fa39c17dcb7313e83c382d731ed1f27') 'Generated fixture identity mismatch'
        foreach ($value in $bytes) { Require ($value -le 127 -and ($value -ge 32 -or $value -in @(9,10,13))) 'Non-ASCII fixture refused' }
    } elseif ($journal) {
        Require ($bytes.Length -eq 1566 -and $Row.sha256 -ceq '440b6e028d3ab6a63a9bdafedc7ddd4784fcd77b5cee9aa640362c6408aa9c91') 'Generated journal identity mismatch'
    } else {
        $text = $utf8.GetString($bytes)
        Require (-not ($bytes -contains 0)) 'NUL in text input'
        if ($name -cin @('d2_adapter.py','d2_child.py','launch_d2.py')) { Require ($text -match '(?m)^OWNER_DECISION_SHA256 = None(?:\s*#.*)?$') 'Real D2 owner pin activated' }
        if ($name -ceq 'fixed_converter.py') { Require ($text -match '(?m)^REAL_PROFILE = None') 'Real converter profile activated' }
    }
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
        name='writer'; inventory='_scratch/windows-writer-exclusion02-copy-inventory01'; count=122; bytes=1595351
        proof='docs/library/proof/windows-writer-exclusion-failed-2026-09-13'; status='FAILED'
        folders=@('windows-reservation-writer-exclusion-proposal01','windows-reservation-writer-exclusion-proposal02','windows-reservation-writer-exclusion02','windows-reservation-writer-source-review01','windows-reservation-writer-source-review02','windows-writer-exclusion02-diagnosis01')
        singles=@('WINDOWS-WRITER-EXCLUSION02-ADMISSION-ACTUAL.json','WINDOWS-WRITER-EXCLUSION02-ACTUAL.json','WINDOWS-WRITER-EXCLUSION02-ROOT-REVIEW.md')
        inventory_files=@(
            @('.gitattributes',8,'705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
            @('COPY-INVENTORY.json',41373,'ac6a0cca368bc75df9362a765b86a42808632a21d428be98dce750c41357ede7'),
            @('INVENTORY-ACTUAL.json',1704,'66e1657ed7952cb729300f7f4beeff1d53dbf100516afca9d89284068e97d158'),
            @('README.md',2535,'36be7f0dce3644636d80ad73cc8067b022dd61530d8f47262f50c855b491402a'))
        extras=@((Row 'docs/library/ASTRA-WRITER-EXCLUSION02-FAILURE-2026-09-13.md' 'VERDICT.md' 2551 'ef6d7624eb6d29a205be24f46311f7f30da299a09372b0fe31614a4be2892165'))
        extra_folders=@()
    },
    [ordered]@{
        name='d2'; inventory='_scratch/vad-d2-fake23-copy-inventory01'; count=110; bytes=515253
        proof='docs/library/proof/vad-d2-fake23-qualification-2026-09-13'; status='RECORDED_FAKE23_PASSED_BOTH_ROOTS_REAL_D2_CLOSED'
        folders=@('vad-d2-dormant-invocation-proposal01','vad-d2-dormant-invocation-proposal02','astra-d2-fake23-confirmation01','vad-d2-dormant-source-review01','vad-d2-readiness-review01')
        singles=@('D2-FAKE23-ADMISSION-ACTUAL.json','D2-FAKE23-AUTHOR-ACTUAL.json','D2-FAKE23-INDEPENDENT-ACTUAL.json','D2-FAKE23-INDEPENDENT-PREPARATION-ACTUAL.json','D2-FAKE23-PAIR-CHECK.json','D2-FAKE23-ROOT-REVIEW.md','check_d2_fake23_pair01.py','prepare_d2_fake23_confirmation01.py')
        inventory_files=@(
            @('.gitattributes',8,'705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
            @('COPY-INVENTORY.json',32509,'0973778d6a518387cd071b7f58f87f816546d259ad340010d7bb96c28d44f29e'),
            @('INVENTORY01-ACTUAL.json',367,'c8aa87ad9032fbbc7ba4e8a895617cf4ee67e9c6a49427cdd52731444267a87f'),
            @('INVENTORY01-CORRECTION.md',636,'cea1b9267d079c507d639f0c9a1fb98f6e550c4349783d9a6e36b9b34d8516dd'),
            @('INVENTORY02-ACTUAL.json',1494,'80a0105d58d66d705602c1d97f19ab8d970efc092287129bf92025adf043b2a6'),
            @('README.md',2885,'04fdf7cefdbbb0e02908232b9dc4037d09624f0d8a9f804417312e0d3d375133'))
        extras=@(
            (Row 'docs/library/ASTRA-D2-FAKE23-VERDICT-2026-09-13.md' 'VERDICT.md' 2634 '25222616565d7ba3d798567fafbe97014c92e1155aad1e9fc9286fb1ffe056c6'),
            (Row '_scratch/D2-FAKE23-PAIR-CHECK-ACTUAL.json' 'root/D2-FAKE23-PAIR-CHECK-ACTUAL.json' 1158 '0bf879b8c8385f886cac755407acfad25f5c77852fb6736cca9c4b9d58490909'),
            (Row '_scratch/vad-d2-owner-question-readiness01/.gitattributes' 'owner-question-readiness01/.gitattributes' 8 '705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
            (Row '_scratch/vad-d2-owner-question-readiness01/VERDICT.md' 'owner-question-readiness01/VERDICT.md' 2220 'a16566080b6e6c8a05eb952030e9b1347cf479d15e210ca1d0a48f5fada9824d'),
            (Row '_scratch/vad-d2-current-binding-check01/ACTUAL-CHECK.json' 'current-binding-check01/ACTUAL-CHECK.json' 1711 '5136917b200945a2a4aa66469eed36e48f17545b2d25d73624e925cd87a5a108'))
        extra_folders=@('_scratch/vad-d2-owner-question-readiness01','_scratch/vad-d2-current-binding-check01')
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

# Check all sources and both fresh destinations before creating either proof.
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
        if ($entry.source -cin @($spec.singles | ForEach-Object {'_scratch/'+$_})) {$allowed=$true}
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
    $checks = [ordered]@{scope='Documentary byte copies only';recorded_status=$spec.status;inventory_payloads=$spec.count;copied_files=$spec.rows.Count;source_membership_and_hashes_checked_before_after=$true;all_copies_rehashed=$true;per_file_cap_bytes=$cap;no_reparse_in_checked_chains=$true;real_D2_approval=$false;tests_or_observations_rerun=0;script_sha256=$ExpectedScriptSha256;copies=$spec.rows}
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
