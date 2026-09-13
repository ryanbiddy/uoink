param([ValidateSet('worker','checkout')][string]$Target, [Parameter(Mandatory=$true)][string]$Label)
$ErrorActionPreference='Stop'
$taskCheckout='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWorker='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\213914a5-528\gemini'
$taskRoot=if ($Target -eq 'worker') { $taskWorker } else { $taskCheckout }
if ($Label -notmatch '^[a-z0-9-]+$') { throw 'Invalid label' }
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PHASE3_REQUIRE_IMPLEMENTATION='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$taskProbe=if ($Target -eq 'worker') { 'tests/test_gemini_synthetic_process_authority.py' } else { 'docs/library/proof/gemini-mirror-authority-2026-09-13/test_gemini_synthetic_process_authority.py' }
& (Join-Path $taskCheckout '_scratch\ig-native\Scripts\python.exe') -B (Join-Path $taskCheckout '_scratch\integrator_verify.py') --root $taskRoot --label $Label $taskProbe --runxfail
exit $LASTEXITCODE
