param([Parameter(Mandatory=$true)][string]$Admission)
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$receiptDirectory = Join-Path $taskRoot "outer/$stamp"
New-Item -ItemType Directory -Path $receiptDirectory -ErrorAction Stop | Out-Null
$arguments = @('-I','-S','-B',(Join-Path $taskRoot 'launch.py'),'--admission',[System.IO.Path]::GetFullPath($Admission))
[ordered]@{executable='C:\Python314\python.exe';arguments=$arguments} | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $receiptDirectory 'command.json') -Encoding utf8
& 'C:\Python314\python.exe' @arguments 1> (Join-Path $receiptDirectory 'stdout.log') 2> (Join-Path $receiptDirectory 'stderr.log')
$rawExit = $LASTEXITCODE
[ordered]@{actual_outer_exit=$rawExit;finished_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $receiptDirectory 'actual-exit.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $receiptDirectory 'stdout.log')
Get-Content -LiteralPath (Join-Path $receiptDirectory 'stderr.log')
exit $rawExit
