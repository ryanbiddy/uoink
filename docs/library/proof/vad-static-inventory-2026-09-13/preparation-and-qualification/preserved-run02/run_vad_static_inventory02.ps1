$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskReader = Join-Path $taskRoot '_scratch\vad-static-inventory-reporting-repair01\read_checkpoint_inventory.py'
$taskOutput = Join-Path $taskRoot '_scratch\vad-static-inventory-run02-launch'
$taskExpected = '17545bb938104e88eacba85978ab353b41e78df55c13ec6214a564d0fbf351fc'
if (Test-Path -LiteralPath $taskOutput) { throw 'Fresh launch directory required' }
if ((Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reader differs from reviewed source' }
New-Item -ItemType Directory -Path $taskOutput | Out-Null
$taskPlan = [ordered]@{
  scope = 'One allowlisted static ZIP/pickle-opcode inventory; no deserialization, object construction, model load, inference or conversion'
  reviewed_reader_sha256 = $taskExpected
  reader = $taskReader
  arguments = @('-I','-S','-B',$taskReader,'--inspect','--run-id','run02')
  checkpoint_copied_to_proof = $false
  reviewer = 'Astra; reporting-only diff, unchanged predicates and 45 synthetic cases reviewed; run01 remains refused'
  started_utc = [DateTime]::UtcNow.ToString('o')
}
$taskPlan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOutput 'plan.json') -Encoding utf8
$env:IG_FORBIDDEN_LIVE = [IO.Path]::Combine($env:LOCALAPPDATA,'Uoink','index.db')
& (Join-Path $taskRoot '_scratch\ig-native\Scripts\python.exe') -I -S -B $taskReader --inspect --run-id run02 1> (Join-Path $taskOutput 'stdout.log') 2> (Join-Path $taskOutput 'stderr.log')
$taskExit = $LASTEXITCODE
$taskAfter = (Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{ actual_process_exit = $taskExit; reader_sha256_after = $taskAfter; reader_unchanged = ($taskAfter -eq $taskExpected); finished_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskOutput 'stdout.log')
Get-Content -LiteralPath (Join-Path $taskOutput 'result.json')
exit $taskExit
