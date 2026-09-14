$ErrorActionPreference='Stop'
$taskOut='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\controller-resume-publication-brief01'
$taskMap=Get-Content -Raw -LiteralPath (Join-Path $taskOut 'SOURCE-BINDINGS.json') | ConvertFrom-Json
[long]$taskTotal=0
foreach($taskRow in $taskMap.inputs){
 if($taskRow.bytes -le 0){throw 'positive recorded bytes required'}
 $taskTotal += [long]$taskRow.bytes
}
$taskPins=@()
foreach($taskName in @('BRIEF.md','SOURCE-BINDINGS.json','SOURCE-BINDINGS-ACTUAL.json')){
 $taskBytes=[IO.File]::ReadAllBytes((Join-Path $taskOut $taskName))
 $taskPins += [ordered]@{name=$taskName;bytes=$taskBytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()}
}
[ordered]@{source_count=$taskMap.inputs.Count;source_bytes=$taskTotal;prior_summary_source_bytes_null='PowerShell Measure-Object did not enumerate ordered-dictionary bytes; exact per-row positive byte counts were preserved';candidate_executed=$false;frozen=$taskPins} | ConvertTo-Json -Depth 6

