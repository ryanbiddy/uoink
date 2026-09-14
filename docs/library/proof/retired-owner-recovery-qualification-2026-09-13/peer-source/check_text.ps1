$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$base = Join-Path $repo '_scratch/windows-retired-owner-recovery-proposal01'
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$files = @('BRIEF.md','PREQUALIFICATION-REPAIR01.md','ORIGINS.json',
    'generated_adapter_flow.py','generated_journal_setup.py','durable_lifecycle.py',
    'test_retired_owner_recovery.py','snapshot_reservations.py','reservation_file_port.py',
    'windows_reservation_port.py','snapshot_lifecycle.py','generated_worker_flow.py',
    'test_windows_reservations.py','before/generated_adapter_flow.py',
    'before/generated_journal_setup.py','before/durable_lifecycle.py',
    'before/prequalification-review01-generated_adapter_flow.py',
    'before/prequalification-review01-test_retired_owner_recovery.py')
$texts = @{}
$rows = @()
foreach ($name in $files) {
    $path = Join-Path $base $name
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer -or $item.Length -gt 131072) { throw 'Fixed text bound' }
    $cursor = $item
    while ($null -ne $cursor) {
        if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse input' }
        $cursor = if ($cursor -is [IO.FileInfo]) { $cursor.Directory } else { $cursor.Parent }
    }
    $raw = [IO.File]::ReadAllBytes($path)
    $textValue = $utf8.GetString($raw)
    if ($textValue.Contains([char]0)) { throw 'NUL text input' }
    $texts[$name] = $textValue
    $rows += [ordered]@{ path=$name; bytes=$raw.Length; sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant() }
}
function Definition([string]$value, [string]$name, [string]$indent) {
    $prefix = [regex]::Escape($indent)
    $pattern = '(?ms)^' + $prefix + 'def ' + [regex]::Escape($name) + '\([^\r\n]*\).*?(?=^' + $prefix + 'def |\z)'
    $found = [regex]::Matches($value, $pattern)
    if ($found.Count -ne 1) { throw ('Definition match: ' + $name) }
    return $found[0].Value.TrimEnd([char]13,[char]10)
}
$preserved = @()
foreach ($name in @('controller_flow','_consume_one_then_cancel','_bound_cancel_journal','controller_cancel_flow','_bound_worker_operations','child_flow')) {
    $before = Definition $texts['before/generated_adapter_flow.py'] $name ''
    $after = Definition $texts['generated_adapter_flow.py'] $name ''
    if ($before -cne $after) { throw ('Changed inherited driver: ' + $name) }
    $preserved += $name
}
foreach ($name in @('_confirmed_phase','before_process','before_close','observe','complete')) {
    $before = Definition $texts['before/generated_journal_setup.py'] $name '    '
    $after = Definition $texts['generated_journal_setup.py'] $name '    '
    if ($before -cne $after) { throw ('Changed inherited observer: ' + $name) }
    $preserved += ('GeneratedJournalSetup.' + $name)
}
$names = @([regex]::Matches($texts['test_retired_owner_recovery.py'], '(?m)^    def (test_[a-z0-9_]+)\(') | ForEach-Object { $_.Groups[1].Value })
if ($names.Count -ne 10 -or @($names | Sort-Object -Unique).Count -ne 10) { throw 'Ten unique source cases required' }
[ordered]@{ scope='Fixed source text/hash checks only; no Python parsing, import, test or native execution';
    files=$rows; preserved_definitions=$preserved; comparison='Exact decoded text after trimming terminal CR/LF only';
    test_method_names=$names; test_methods_executed=0; native_calls=0; source_mutations=0 } | ConvertTo-Json -Depth 7
