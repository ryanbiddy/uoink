$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$work='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a28eb713-c06\gemini'
$selectionPath='docs/library/proof/stable-directory-correction02-brief-2026-09-13/INPUT-SELECTION.json'
$reportPath='docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.md'
$coveragePath='docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13.coverage.json'
$utf8=[Text.UTF8Encoding]::new($false,$true)
function Need($condition,[string]$reason){if(-not $condition){throw $reason}}
function Text([string]$root,[string]$relative,[string]$expectedHash){
    Need ($relative -cmatch '^docs/library/(proof/[A-Za-z0-9_./-]+|GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13\.(md|coverage\.json))$' -and $relative -notmatch '(^|/)\.\.(/|$)') 'Fixed documentary path'
    $path=Join-Path $root $relative
    $before=Get-Item -LiteralPath $path -Force
    Need (-not $before.PSIsContainer -and $before.Length -le 1048576 -and ($before.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Documentary input bound'
    $raw=[IO.File]::ReadAllBytes($path)
    Need ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant() -ceq $expectedHash) 'Input digest differs'
    $value=$utf8.GetString($raw)
    Need (-not ($raw -contains 0)) 'NUL documentary text'
    $after=Get-Item -LiteralPath $path -Force
    Need ($after.Length -eq $before.Length -and $after.LastWriteTimeUtc.Ticks -eq $before.LastWriteTimeUtc.Ticks) 'Input changed'
    return $value.TrimStart([char]0xfeff)
}
$selectionSha='874b686d4a078d37385cac6b5a860a21aebeec08781d2ec150cd3f2e0491b277'
$selection=Text $repo $selectionPath $selectionSha | ConvertFrom-Json -AsHashtable
$null=Text $work $selectionPath $selectionSha
Need ($selection.selected_count -eq 5 -and $selection.files.Count -eq 5) 'Five selected inputs'
$report=Text $work $reportPath '1a0ced7a1865ee48756946886d05b96badeb5ae305c602c87cde6c4bb2fd9709'
$coverage=Text $work $coveragePath '16818d49930b28afdd58aa64a74e9ee7be5f3c9a48aa4dec5b73d33f9732baf5' | ConvertFrom-Json -AsHashtable
Need ($coverage.Count -eq 5) 'Five coverage entries'
$observed=@();$texts=@{};$sum=0
for($i=0;$i -lt 5;$i++){
    $input=$selection.files[$i];$id='A-{0:d2}' -f ($i+1)
    Need ($input.id -ceq $id) 'Selection order'
    $source=Text $work $input.path $input.sha256
    $canonical=Text $repo $input.path $input.sha256
    Need ($source -ceq $canonical -and $utf8.GetByteCount($source) -eq $input.bytes) 'Root/worktree source equality'
    $lines=$source.Split([char]10)
    Need ($lines.Count -eq $input.lines) 'Catalog LF-slot count'
    $texts[$id]=$source;$sum+=$input.bytes
    $entry=$coverage[$i]
    Need ($entry.Count -eq 2 -and $entry.Contains('id') -and $entry.Contains('viewed_ranges') -and $entry.id -ceq $id) 'Coverage shape/order'
    $last=0
    foreach($range in $entry.viewed_ranges){
        Need ($range.Count -eq 2 -and $range[0] -is [long] -and $range[1] -is [long] -and $range[0] -gt $last -and $range[1] -ge $range[0] -and $range[1] -le $input.lines) 'Coverage numeric range'
        $last=$range[1]
    }
    $observed += [ordered]@{id=$id;bytes=$input.bytes;sha256=$input.sha256;catalog_lf_slots=$lines.Count;last_slot_empty=($lines[-1] -eq '');claimed_ranges=$entry.viewed_ranges;claim_includes_terminal_empty_slot=($last -eq $lines.Count -and $lines[-1] -eq '');actual_worker_view_trace_verified=$false}
}
Need ($sum -eq 65576) 'Selected byte total'
$words=[regex]::Matches($report,'\S+').Count
Need ($words -le 600) 'Report word cap'
$cites=@()
foreach($match in [regex]::Matches($report,'(?<id>A-0[1-5]):(?<start>\d+)[–-](?<end>\d+)')){
    $id=$match.Groups['id'].Value;$first=[int]$match.Groups['start'].Value;$last=[int]$match.Groups['end'].Value
    Need ($first -ge 1 -and $last -ge $first -and $last -le $texts[$id].Split([char]10).Count) 'Citation range'
    $cites += [ordered]@{id=$id;start=$first;end=$last}
}
$methods=@([regex]::Matches($texts['A-05'],'(?m)^    def (?<name>test_[a-z0-9_]+)\(self\):') | ForEach-Object {$_.Groups['name'].Value})
$named=@([regex]::Matches($report,'test_[a-z0-9_]+') | ForEach-Object {$_.Value} | Where-Object {$_ -cne 'test_windows_reservations'})
Need ($methods.Count -eq 11 -and $named.Count -eq 11 -and (($methods | Sort-Object) -join '|') -ceq (($named | Sort-Object) -join '|')) 'Exact eleven named test bodies'
[ordered]@{
    scope='Read-only text/hash/shape checks; factual assessment is in peer verdict'
    report_sha256='1a0ced7a1865ee48756946886d05b96badeb5ae305c602c87cde6c4bb2fd9709'
    coverage_sha256='16818d49930b28afdd58aa64a74e9ee7be5f3c9a48aa4dec5b73d33f9732baf5'
    selection_sha256=$selectionSha
    worktree=$work
    selected_bytes=$sum
    report_whitespace_word_count=$words
    selected_inputs=$observed
    named_test_methods=$methods
    cited_ranges=$cites
    independently_verified_worker_tool_trace=$false
    candidate_execution_performed=$false
} | ConvertTo-Json -Depth 10
