$ErrorActionPreference = 'Stop'
$opDraft = Get-Content -LiteralPath 'docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md' -Raw -Encoding UTF8
$opBlocks = [regex]::Matches($opDraft, '(?s)```powershell\s*\r?\n(.*?)```')
$opResults = @()
foreach ($opBlock in $opBlocks) {
    $opTokens = $null
    $opErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($opBlock.Groups[1].Value, [ref]$opTokens, [ref]$opErrors)
    $opResults += [ordered]@{ block = $opResults.Count + 1; errors = @($opErrors | ForEach-Object { $_.Message }) }
}
if ($opBlocks.Count -lt 5 -or @($opResults | Where-Object { $_.errors.Count -gt 0 }).Count -gt 0) { throw ($opResults | ConvertTo-Json -Depth 5) }
[ordered]@{ status='PASS'; scope='PowerShell syntax only; commands not executed'; blocks=$opResults } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath '_scratch/runbook08-syntax.json' -Encoding UTF8
Write-Output ('Parsed ' + $opBlocks.Count + ' blocks with zero errors.')
