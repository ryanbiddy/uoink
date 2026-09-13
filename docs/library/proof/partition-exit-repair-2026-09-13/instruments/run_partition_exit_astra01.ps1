$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
& .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root $taskRoot --label astra-partition-exit-contract01 _scratch/test_partition_exit_contract.py --runxfail
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\_scratch\ig-native\Scripts\python.exe -I -S -B _scratch/verify_partition_exit_wiring01.py
exit $LASTEXITCODE
