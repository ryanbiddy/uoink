param([Parameter(Mandatory=$true)][string]$Label)
$ErrorActionPreference = 'Stop'
if ($Label -notmatch '^partition-exit-unit[0-9]{2}$') { throw 'Unexpected unit label' }
$contractRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$contractLaunch = Join-Path $contractRoot ('_scratch\' + $Label + '-launch')
if (Test-Path -LiteralPath $contractLaunch) { throw 'Launch receipt already exists' }
New-Item -ItemType Directory -Path $contractLaunch | Out-Null
foreach ($name in @('partition_exit_contract.py','test_partition_exit_contract.py','PARTITION-EXIT-CONTRACT-REVIEW-2026-09-13.md','run_partition_exit_contract01.ps1')) {
    Copy-Item -LiteralPath (Join-Path $contractRoot ('_scratch\' + $name)) -Destination (Join-Path $contractLaunch $name)
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)$' -or $_.Name -match '^(ANTHROPIC|CLAUDE_CODE|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
Set-Location -LiteralPath $contractRoot
$contractCommand = @('-B','_scratch/integrator_verify.py','--root',$contractRoot,'--label',$Label,'_scratch/test_partition_exit_contract.py')
@{ command = @((Join-Path $contractRoot '_scratch\ig-native\Scripts\python.exe')) + $contractCommand; scope = 'new synthetic unit data only' } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $contractLaunch 'command.json') -Encoding utf8
& (Join-Path $contractRoot '_scratch\ig-native\Scripts\python.exe') @contractCommand
$contractExit = $LASTEXITCODE
@{ verifier_exit = $contractExit; label = $Label } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $contractLaunch 'result.json') -Encoding utf8
exit $contractExit
