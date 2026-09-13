$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$outerRoot = Join-Path $taskRoot 'outer-d1-real-01'
New-Item -ItemType Directory -Path $outerRoot -ErrorAction Stop | Out-Null
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$providerNames = @(Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(API.?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION)' } | ForEach-Object { $_.Name })
foreach ($providerName in $providerNames) { Remove-Item -LiteralPath ('Env:' + $providerName) }
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_DATASETS_OFFLINE = '1'
$env:PYANNOTE_METRICS_ENABLED = '0'
$arguments = @('-I','-S','-B',(Join-Path $taskRoot 'launch_d1.py'))
[ordered]@{executable='C:\Python314\python.exe';arguments=$arguments;forbidden_live_binding_set=$true;provider_environment_scrubbed=$true;removed_variable_names=$providerNames} | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $outerRoot 'command.json') -Encoding utf8
& 'C:\Python314\python.exe' @arguments 1> (Join-Path $outerRoot 'stdout.log') 2> (Join-Path $outerRoot 'stderr.log')
$rawExit = $LASTEXITCODE
[ordered]@{actual_outer_exit=$rawExit;finished_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $outerRoot 'actual-exit.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $outerRoot 'stdout.log')
Get-Content -LiteralPath (Join-Path $outerRoot 'stderr.log')
exit $rawExit
