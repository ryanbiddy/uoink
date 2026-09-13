param([ValidateSet('double','shutdown')][string]$Mode)
$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PHASE3_REQUIRE_IMPLEMENTATION='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$taskLabel='partition-contract-'+$Mode+'01'
$taskReceipt=Join-Path $taskRoot ('_scratch\'+$taskLabel+'-receipt')
if (Test-Path -LiteralPath $taskReceipt) { throw 'Fresh receipt required' }
New-Item -ItemType Directory -Path $taskReceipt | Out-Null
$env:IG_PARTITION_RECEIPT_PATH=Join-Path $taskReceipt 'partition'
$env:IG_MIRROR_STATE_RECEIPT_PATH=Join-Path $taskReceipt 'mirror-state.jsonl'
$taskArgs=@('-p','_scratch.partition_receipt_plugin','-p','_scratch.mirror_state_receipt_plugin')
if ($Mode -eq 'double') {
 $taskCase='_scratch/test_phase4_partition_double_failure_smoke.py'
} else {
 $taskCase='_scratch/test_partition_shutdown_smoke.py'
 $taskArgs+=@('-p','_scratch.partition_shutdown_failure_plugin')
}
& .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root $taskRoot --label $taskLabel $taskCase --runxfail @taskArgs
$taskExit=$LASTEXITCODE
@{label=$taskLabel;outer_exit=$taskExit;intent='inert receipt qualification; no product result'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskReceipt 'launcher-result.json') -Encoding utf8
exit $taskExit
