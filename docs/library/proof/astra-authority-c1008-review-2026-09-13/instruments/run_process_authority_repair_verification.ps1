param([ValidateSet('worker','checkout')][string]$Target,[ValidateSet('worker','boundary','all')][string]$Suite,[Parameter(Mandatory=$true)][string]$Label)
$ErrorActionPreference='Stop'
$taskCheckout='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWorker='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c1008e0b-74f\gemini'
$taskRoot=if ($Target -eq 'worker') { $taskWorker } else { $taskCheckout }
if ($Label -notmatch '^[a-z0-9-]+$') { throw 'Invalid label' }
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PHASE3_REQUIRE_IMPLEMENTATION='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$taskTests=@()
if ($Suite -in @('worker','all')) { $taskTests+='tests/test_library_mirror_process_authority.py' }
if ($Suite -in @('boundary','all')) { $taskTests+='tests/test_mirror_process_identity_boundaries.py' }
& (Join-Path $taskCheckout '_scratch\ig-native\Scripts\python.exe') -B (Join-Path $taskCheckout '_scratch\integrator_verify.py') --root $taskRoot --label $Label @taskTests --runxfail
exit $LASTEXITCODE
