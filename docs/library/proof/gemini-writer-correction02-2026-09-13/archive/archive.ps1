param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPinsSha256)
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$scriptRelative = '_scratch/archive-gemini-writer-correction02-proposal01/archive.ps1'
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


$proposalRelative='_scratch/archive-gemini-writer-correction02-proposal01'
$proposal=Join-Path $repo $proposalRelative
$proofRelative='docs/library/proof/gemini-writer-correction02-2026-09-13'
$output=Join-Path $repo $proofRelative
$status='SOURCE_CONCLUSION_ACCEPTED_WITH_MANDATORY_CORRECTIONS'
Require ([IO.Path]::GetFullPath($PSCommandPath) -ceq [IO.Path]::GetFullPath((Join-Path $repo $scriptRelative))) 'Fixed archive source required'
Exact-Members $proposal @('archive.ps1','COPY-MAP.json','PROTOCOL.md','PINS.json')
$pinPath=Join-Path $proposal 'PINS.json'
$pinRow=Row ($proposalRelative+'/PINS.json') 'archive/PINS.json' (Get-Item -LiteralPath $pinPath).Length $ExpectedPinsSha256
$pins=$utf8.GetString((Read-Verified $pinPath $pinRow $pinRow.source)) | ConvertFrom-Json
Require ($pins.schema -ceq 'uoink.archive-instrument-pins.v1' -and @($pins.files).Count -eq 3) 'Exact instrument pins required'
$controlRows=@($pinRow)
$expectedControls=@('archive.ps1','COPY-MAP.json','PROTOCOL.md')
for($index=0;$index -lt 3;$index++){
    $entry=$pins.files[$index]
    Require ($entry.path -ceq $expectedControls[$index]) 'Instrument membership/order changed'
    $controlRows+=Row ($proposalRelative+'/'+$entry.path) ('archive/'+$entry.path) $entry.bytes $entry.sha256
}
foreach($row in $controlRows){$null=Read-Verified (Join-Path $repo $row.source) $row $row.source}
$mapRow=$controlRows[2]
$map=$utf8.GetString((Read-Verified (Join-Path $repo $mapRow.source) $mapRow $mapRow.source)) | ConvertFrom-Json
Require ($map.schema -ceq 'uoink.fixed-text-archive-map.v1' -and $map.status -ceq $status -and $map.proof -ceq $proofRelative -and $map.run_id -ceq '5444c59a-8ae1-4188-9b57-d967f04bbbb6' -and $map.payload_count -eq 17 -and @($map.files).Count -eq 17 -and $map.total_payload_bytes -eq 59369) 'Fixed archive map contract changed'
$allowedSources=@(
    'docs/library/GEMINI-WRITER-EXCLUSION-CORRECTION02-2026-09-13.md',
    'docs/library/GEMINI-WRITER-EXCLUSION-CORRECTION02-2026-09-13.coverage.json',
    'docs/library/ASTRA-GEMINI-WRITER-CORRECTION02-VERDICT-2026-09-13.md',
    '_scratch/check-gemini-writer-correction02.py',
    '_scratch/GEMINI-WRITER-CORRECTION02.patch',
    '_scratch/GEMINI-WRITER-CORRECTION02-DISPATCH-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-POLL01-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-COMPLETION-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-ROOT-CHECK-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-WORKER-PATCH-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-METADATA-ACTUAL.json',
    '_scratch/GEMINI-WRITER-CORRECTION02-EXACT-BYTES-ACTUAL.json',
    '_scratch/gemini-writer-correction02-peer-review01/VERDICT.md',
    '_scratch/gemini-writer-correction02-peer-review01/check_text.ps1',
    '_scratch/gemini-writer-correction02-peer-review01/CHECK-ACTUAL.json',
    'docs/library/proof/writer-exclusion-correction02-brief-2026-09-13/BRIEF.md',
    'docs/library/proof/writer-exclusion-correction02-brief-2026-09-13/INPUT-SELECTION.json'
)
$payloadRows=@()
$total=0L
for($index=0;$index -lt 17;$index++){
    $entry=$map.files[$index]
    Require ($entry.source -ceq $allowedSources[$index]) 'Payload source membership/order changed'
    $payloadRows+=Row $entry.source $entry.destination $entry.bytes $entry.sha256
    $total+=$entry.bytes
}
Require ($total -eq 59369) 'Payload byte total differs'
$rows=@($payloadRows)+@($controlRows)
$seenSources=@{}; $seenDestinations=@{}
foreach($row in $rows){
    Require (-not $seenSources.ContainsKey($row.source) -and -not $seenDestinations.ContainsKey($row.destination)) 'Duplicate source/destination'
    Require ($row.destination -cnotin @('.gitattributes','COPY-CHECKS.json','SHA256.json')) 'Reserved output name'
    $seenSources[$row.source]=$true; $seenDestinations[$row.destination]=$true
}
function Check-AllSources {
    Exact-Members $proposal @('archive.ps1','COPY-MAP.json','PROTOCOL.md','PINS.json')
    Exact-Members (Join-Path $repo '_scratch/gemini-writer-correction02-peer-review01') @('VERDICT.md','check_text.ps1','CHECK-ACTUAL.json')
    foreach($row in $rows){$null=Read-Verified (Join-Path $repo $row.source) $row $row.source}
}
Chain ([IO.Path]::GetDirectoryName($output))
Require (-not (Test-Path -LiteralPath $output)) 'Fresh proof folder required'
Check-AllSources
Require (-not (Test-Path -LiteralPath $output)) 'Proof folder appeared before copying'
New-Directory $output
foreach($row in $rows){
    $raw=Read-Verified (Join-Path $repo $row.source) $row $row.source
    $destination=Join-Path $output $row.destination
    Write-New $destination $raw
    $null=Read-Verified $destination $row $row.source
    $null=Read-Verified (Join-Path $repo $row.source) $row $row.source
}
Check-AllSources
Write-New (Join-Path $output '.gitattributes') ($utf8.GetBytes(('* -text'+[char]10)))
$checks=[ordered]@{
    scope='Fixed documentary text copies only'
    recorded_status=$status
    run_id=$map.run_id
    inventory_payloads=17
    inventory_payload_bytes=59369
    copied_files=$rows.Count
    source_membership_and_hashes_checked_before_after=$true
    all_copies_rehashed=$true
    no_reparse_in_checked_chains=$true
    per_file_cap_bytes=$cap
    worker_view_trace_verified=$false
    native_acceptance=$false
    candidate_execution_performed=$false
    tests_or_observations_rerun=0
    completion_tool_truncation_preserved_as_returned=$true
    raw_apply_actual_object_available=$false
    pins_sha256=$ExpectedPinsSha256
    copies=$rows
}
Write-New (Join-Path $output 'COPY-CHECKS.json') (Json-Bytes $checks)
$expected=@($rows | ForEach-Object {$_.destination})+@('.gitattributes','COPY-CHECKS.json')
Require ($expected.Count -eq 23) 'Fixed payload membership differs'
Exact-Members $output $expected
$sealRows=@()
foreach($name in ($expected | Sort-Object)){
    $path=Join-Path $output $name; Chain $path
    $raw=[IO.File]::ReadAllBytes($path)
    Require ($raw.LongLength -le $cap) 'Seal member exceeds cap'
    $sealRows+=[ordered]@{path=$name;bytes=$raw.LongLength;sha256=(Digest $raw)}
}
Write-New (Join-Path $output 'SHA256.json') (Json-Bytes ([ordered]@{files=$sealRows}))
Exact-Members $output (@($expected)+@('SHA256.json'))
foreach($row in $rows){$null=Read-Verified (Join-Path $output $row.destination) $row $row.source}
foreach($row in $sealRows){
    Require ((Get-FileHash -LiteralPath (Join-Path $output $row.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $row.sha256) 'Final seal hash mismatch'
}
Check-AllSources
[ordered]@{
    proof=$proofRelative
    recorded_status=$status
    fixed_payloads=17
    copied_files=$rows.Count
    sealed_payloads=$sealRows.Count
    complete_physical_files=24
    manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $output 'SHA256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json -Depth 5
