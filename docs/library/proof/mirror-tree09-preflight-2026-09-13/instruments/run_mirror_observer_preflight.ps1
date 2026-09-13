param([ValidateSet('unit','pipeline')][string]$Mode)
$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PHASE3_REQUIRE_IMPLEMENTATION='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
if ($Mode -eq 'unit') {
 & .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root $taskRoot --label astra-mirror-state-plugin01 _scratch/test_mirror_state_receipt_plugin.py --runxfail
} else {
 $taskReceipt=Join-Path $taskRoot '_scratch\mirror-observer-pipeline01-receipt'
 New-Item -ItemType Directory -Path $taskReceipt | Out-Null
 $env:IG_PARTITION_RECEIPT_PATH=Join-Path $taskReceipt 'partition'
 $env:IG_MIRROR_STATE_RECEIPT_PATH=Join-Path $taskReceipt 'mirror-state.jsonl'
 $env:IG_MIRROR_STATE_INCLUDE_STACKS='1'
 & .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root $taskRoot --label mirror-observer-pipeline01 _scratch/test_phase4_mirror_observer_pipeline.py --runxfail -p _scratch.partition_receipt_plugin -p _scratch.mirror_state_receipt_plugin
}
exit $LASTEXITCODE
