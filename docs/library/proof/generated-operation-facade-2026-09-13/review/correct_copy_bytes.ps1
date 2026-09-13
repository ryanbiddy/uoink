$ErrorActionPreference='Stop'
$taskDir='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\generated-operation-proof-proposal01'
$taskOld=Get-Content -LiteralPath (Join-Path $taskDir 'COPY-PLAN.json') -Raw | ConvertFrom-Json
if($taskOld.payload_count -ne 96 -or $taskOld.entries.Count -ne 96 -or $null -ne $taskOld.payload_bytes){throw 'Exact first accounting result required'}
$taskBefore=$taskOld.entries | ConvertTo-Json -Depth 12 -Compress
[long]$taskBytes=0
foreach($taskRow in $taskOld.entries){
    if(($taskRow.bytes -isnot [long] -and $taskRow.bytes -isnot [int]) -or $taskRow.bytes -lt 0 -or $taskRow.bytes -gt 262144){throw 'Bounded explicit payload length required'}
    $taskBytes += $taskRow.bytes
}
$taskOld.payload_bytes=$taskBytes
if(($taskOld.entries | ConvertTo-Json -Depth 12 -Compress) -cne $taskBefore){throw 'Payload rows changed'}
$taskEncoded=[Text.UTF8Encoding]::new($false).GetBytes(($taskOld | ConvertTo-Json -Depth 35)+"`n")
$taskPath=Join-Path $taskDir 'COPY-PLAN02.json'
$taskStream=[IO.File]::Open($taskPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$taskStream.Write($taskEncoded,0,$taskEncoded.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
[ordered]@{payload_count=$taskOld.payload_count;payload_bytes=$taskBytes;payload_rows_unchanged=$true;sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
