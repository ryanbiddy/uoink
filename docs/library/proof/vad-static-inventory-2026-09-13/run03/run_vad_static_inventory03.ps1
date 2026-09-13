$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskReader = Join-Path $taskRoot '_scratch\vad-static-inventory-compatibility01\read_checkpoint_inventory.py'
$taskOutput = Join-Path $taskRoot '_scratch\vad-static-inventory-run03-launch'
$taskExpected = 'f27b91e610284e26975038ff6826f2190758b1d4c53a402db3c2d0386cc4d40d'
if (Test-Path -LiteralPath $taskOutput) { throw 'Fresh launch directory required' }
if ((Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reader differs from reviewed source' }
New-Item -ItemType Directory -Path $taskOutput | Out-Null
$taskPlan = [ordered]@{
  scope = 'One allowlisted static ZIP/pickle-opcode inventory; no deserialization, object construction, model load, inference or conversion'
  reviewed_reader_sha256 = $taskExpected
  reader = $taskReader
  arguments = @('-I','-S','-B',$taskReader,'--inspect','--run-id','run03')
  checkpoint_copied_to_proof = $false
  reviewer = 'Astra; exact version-zero stored-header exception and immutable artifact hash gate reviewed; 89 synthetic cases; both prior refusals retained'
  started_utc = [DateTime]::UtcNow.ToString('o')
}
$taskPlan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOutput 'plan.json') -Encoding utf8
$env:IG_FORBIDDEN_LIVE = [IO.Path]::Combine($env:LOCALAPPDATA,'Uoink','index.db')
& (Join-Path $taskRoot '_scratch\ig-native\Scripts\python.exe') -I -S -B $taskReader --inspect --run-id run03 1> (Join-Path $taskOutput 'stdout.log') 2> (Join-Path $taskOutput 'stderr.log')
$taskExit = $LASTEXITCODE
$taskAfter = (Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{ actual_process_exit = $taskExit; reader_sha256_after = $taskAfter; reader_unchanged = ($taskAfter -eq $taskExpected); finished_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskOutput 'stdout.log')
Get-Content -LiteralPath (Join-Path $taskOutput 'result.json')
exit $taskExit
