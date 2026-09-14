$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$target='_scratch/journal-cancel-qualification-copy-inventory01'
$utf8=[Text.UTF8Encoding]::new($false,$true)
function Need($value,[string]$reason) { if (-not $value) { throw $reason } }
function Chain([string]$path) {
    $item=Get-Item -LiteralPath $path -Force
    Need (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse item refused'
    $dir=if ($item.PSIsContainer) { [IO.DirectoryInfo]::new($item.FullName) } else { [IO.DirectoryInfo]::new($item.DirectoryName) }
    while ($null -ne $dir) {
        $part=Get-Item -LiteralPath $dir.FullName -Force
        Need ($part.PSIsContainer -and ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Unsafe ancestor'
        $dir=$dir.Parent
    }
}
function Capture([string]$relative,[string]$destination) {
    $path=Join-Path $repo $relative
    Chain $path
    $item=Get-Item -LiteralPath $path -Force
    Need (-not $item.PSIsContainer -and $item.Length -le 1048576) 'Size/type refused'
    Need ($item.Name -ceq '.gitattributes' -or $item.Extension -cin @('.py','.ps1','.md','.json','.diff','.txt','.log')) 'Non-text refused before read'
    $bytes=[IO.File]::ReadAllBytes($path)
    $null=$utf8.GetString($bytes)
    Need (-not ($bytes -contains 0)) 'NUL refused'
    Chain $path
    $after=Get-Item -LiteralPath $path -Force
    Need ($bytes.LongLength -eq $item.Length -and $after.Length -eq $item.Length -and $after.LastWriteTimeUtc.Ticks -eq $item.LastWriteTimeUtc.Ticks) 'Changed during read'
    return [ordered]@{source=$relative;destination=$destination;bytes=$bytes.LongLength;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
}
Need (-not (Test-Path -LiteralPath (Join-Path $repo $target))) 'Fresh inventory required'
$groups=@(
    @('windows-journal-cancel-fake-proposal01','author',112),
    @('astra-journal-cancel-confirmation01','independent',77),
    @('windows-journal-cancel-source-review01','source-review',2),
    @('windows-journal-cancel-complementary-review01','complementary-review',2),
    @('windows-journal-cancel-author-result-review01','author-result-review',2)
)
$rows=@(); $groupRows=@()
foreach ($group in $groups) {
    $relative='_scratch/'+$group[0]
    $root=Join-Path $repo $relative
    Chain $root
    $pending=[Collections.Generic.Stack[string]]::new(); $pending.Push($root)
    $members=[Collections.Generic.List[string]]::new()
    while ($pending.Count) {
        foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            Need (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse tree member'
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else { $members.Add([IO.Path]::GetRelativePath($root,$item.FullName).Replace([char]92,[char]47)) }
        }
    }
    Need ($members.Count -eq $group[2]) 'Unexpected fixed-root membership'
    $sum=0L
    foreach ($member in ($members | Sort-Object)) {
        $row=Capture ($relative+'/'+$member) ($group[1]+'/'+$member)
        $rows += $row; $sum += [long]$row.bytes
    }
    $groupRows += [ordered]@{source_root=$relative;destination_root=$group[1];payload_count=$members.Count;payload_bytes=$sum}
}
$wildcards=@(
    'JOURNAL-CANCEL-FAKE89-ADMISSION-ACTUAL01.json',
    'JOURNAL-CANCEL-FAKE89-AUTHOR-ACTUAL01.json',
    'JOURNAL-CANCEL-FAKE89-INDEPENDENT-ACTUAL01.json',
    'JOURNAL-CANCEL-FAKE89-INDEPENDENT-PREP-ACTUAL01.json',
    'JOURNAL-CANCEL-FAKE89-PAIR-CHECK-ACTUAL01.json',
    'JOURNAL-CANCEL-FAKE89-PAIR-CHECK01.json',
    'JOURNAL-CANCEL-FAKE89-ROOT-REVIEW01.md'
)
$actualNames=@(Get-ChildItem -LiteralPath (Join-Path $repo '_scratch') -Filter 'JOURNAL-CANCEL-FAKE89-*' -Force | ForEach-Object {$_.Name} | Sort-Object)
Need (($actualNames -join "`n") -ceq (($wildcards | Sort-Object) -join "`n")) 'Wildcard membership changed'
$singles=@($wildcards | ForEach-Object {'_scratch/'+$_})+@(
    '_scratch/admit-journal-cancel-fake89-01.ps1',
    '_scratch/prepare_journal_cancel_confirmation01.ps1',
    '_scratch/check-journal-cancel-fake89-pair01.py',
    'docs/library/ASTRA-JOURNAL-CANCEL-FAKE89-VERDICT-2026-09-13.md'
)
foreach ($relative in $singles) { $rows += Capture $relative ('root/'+[IO.Path]::GetFileName($relative)) }
$rows=@($rows | Sort-Object { $_.source })
Need ($rows.Count -eq 206) 'Unexpected payload count'
Need (@($rows | ForEach-Object {$_.source} | Select-Object -Unique).Count -eq 206) 'Duplicate source'
Need (@($rows | ForEach-Object {$_.destination} | Select-Object -Unique).Count -eq 206) 'Duplicate destination'
$total=0L; $max=0L
foreach ($row in $rows) { $total += [long]$row.bytes; if ([long]$row.bytes -gt $max) {$max=[long]$row.bytes} }
$doc=[ordered]@{
    schema='uoink.fixed-documentary-copy-inventory.v1'
    status='PASSED_TWO_GENERATED_FAKE89_OBSERVATIONS_ONLY'
    proof='docs/library/proof/windows-journal-cancel-qualification-2026-09-13'
    per_file_cap_bytes=1048576
    text_only=$true
    no_reparse_in_checked_chains=$true
    payload_count=$rows.Count
    total_payload_bytes=$total
    largest_payload_bytes=$max
    source_groups=$groupRows
    exact_single_files=$singles
    distinct_cases=89
    observations=2
    passed_nested_per_observation=86
    native_cancellation_executed=$false
    runtime_or_release_approved=$false
    files=$rows
}
$targetPath=Join-Path $repo $target
Chain ([IO.Path]::GetDirectoryName($targetPath))
Need (-not (Test-Path -LiteralPath $targetPath)) 'Inventory appeared'
$null=[IO.Directory]::CreateDirectory($targetPath)
[IO.File]::WriteAllText((Join-Path $targetPath 'COPY-INVENTORY.json'),($doc | ConvertTo-Json -Depth 8)+"`n",$utf8)
[IO.File]::WriteAllText((Join-Path $targetPath '.gitattributes'),"* -text`n",$utf8)
[ordered]@{payload_count=$rows.Count;total_payload_bytes=$total;largest_payload_bytes=$max;groups=$groupRows;map_sha256=(Get-FileHash -LiteralPath (Join-Path $targetPath 'COPY-INVENTORY.json') -Algorithm SHA256).Hash.ToLowerInvariant();copies=0;tests_rerun=0;native_cancellation_executed=$false} | ConvertTo-Json -Depth 6
