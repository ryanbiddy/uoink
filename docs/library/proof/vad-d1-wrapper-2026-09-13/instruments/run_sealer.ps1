$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskWork='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d1-wrapper-combined-seal01'
$taskAttempt=Join-Path $taskWork 'seal-attempt01'
if(Test-Path -LiteralPath $taskAttempt){throw 'Fresh documentary seal attempt required'}
New-Item -ItemType Directory -Path $taskAttempt -ErrorAction Stop | Out-Null
Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(API.?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$taskFiles=@('BRIEF.md','build_proof.py','verify_proof.py','README.md','run_sealer.ps1')
$taskHashes=@()
foreach($taskName in $taskFiles){$taskHashes += [ordered]@{name=$taskName;sha256=(Get-FileHash -LiteralPath (Join-Path $taskWork $taskName) -Algorithm SHA256).Hash.ToLowerInvariant()}}
[ordered]@{action='documentary copy/hash/archive only';executable='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe';arguments=@('-I','-S','-B','build_proof.py');inputs=$taskHashes;startup_binding_set=$true;test_rerun=$false;real_d1_invoked=$false} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskAttempt 'plan.json') -Encoding utf8
& 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe' -I -S -B (Join-Path $taskWork 'build_proof.py') 1> (Join-Path $taskAttempt 'stdout.json') 2> (Join-Path $taskAttempt 'stderr.log')
$taskExit=$LASTEXITCODE
[ordered]@{native_exit=$taskExit;startup_binding_set=$true;test_rerun=$false;real_d1_invoked=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskAttempt 'exit.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskAttempt 'stdout.json')
Get-Content -LiteralPath (Join-Path $taskAttempt 'stderr.log')
exit $taskExit
