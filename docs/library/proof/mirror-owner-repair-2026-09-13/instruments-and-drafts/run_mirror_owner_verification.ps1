param(
 [ValidateSet('worker','checkout')][string]$Target,
 [ValidateSet('focused','phase4')][string]$Suite,
 [Parameter(Mandatory=$true)][string]$Label
)
$ErrorActionPreference = 'Stop'
$taskCheckout = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWorker = 'E:\AI\projects\uoink\worktrees\mirror-owner-admission-repair'
$taskRoot = if ($Target -eq 'worker') { $taskWorker } else { $taskCheckout }
if ($Label -notmatch '^[a-z0-9-]+$') { throw 'Invalid observation label' }
if (Test-Path -LiteralPath (Join-Path $taskRoot ('_scratch\'+$Label))) { throw 'Observation already exists' }
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|XAI|GROK)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+ $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:IG_OWNER_DIAGNOSTIC_OUT = Join-Path $taskRoot ('_scratch\'+$Label+'-original-events.json')
$taskSelectors = @('tests/test_mirror_owner_admission.py', '_scratch/test_mirror_owner_admission_diagnostic.py')
if ($Suite -eq 'phase4') {
 $taskSelectors = @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'tests') -Filter 'test_phase4*.py' -File | Sort-Object Name | ForEach-Object { 'tests/'+$_.Name })
 $taskSelectors += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'tests\library_work_astra') -Filter 'test_phase4*.py' -File | Sort-Object Name | ForEach-Object { 'tests/library_work_astra/'+$_.Name })
 $taskSelectors += 'tests/test_mirror_owner_admission.py'
}
& (Join-Path $taskCheckout '_scratch\ig-native\Scripts\python.exe') -B (Join-Path $taskCheckout '_scratch\integrator_verify.py') --root $taskRoot --label $Label @taskSelectors --runxfail
exit $LASTEXITCODE
