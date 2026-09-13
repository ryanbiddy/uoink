$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskReader = Join-Path $taskRoot '_scratch\vad-static-metadata-tail01\read_checkpoint_inventory.py'
$taskOutput = Join-Path $taskRoot '_scratch\vad-static-inventory-run04-launch'
$taskExpected = '67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5'
if (Test-Path -LiteralPath $taskOutput) { throw 'Fresh launch directory required' }
if ((Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reader differs from reviewed source' }
New-Item -ItemType Directory -Path $taskOutput | Out-Null
$taskPlan = [ordered]@{
  scope = 'One allowlisted static ZIP/pickle-opcode inventory; no deserialization, object construction, model load, inference or conversion'
  reviewed_reader_sha256 = $taskExpected
  reader = $taskReader
  arguments = @('-I','-S','-B',$taskReader,'--inspect','--run-id','run04')
  checkpoint_copied_to_proof = $false
  reviewer = 'Astra; bounded last64 token reporting diff reviewed after17 synthetic checks; prior complete inventory unchanged; no architecture or config inferred'
  started_utc = [DateTime]::UtcNow.ToString('o')
}
$taskPlan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOutput 'plan.json') -Encoding utf8
$env:IG_FORBIDDEN_LIVE = [IO.Path]::Combine($env:LOCALAPPDATA,'Uoink','index.db')
& (Join-Path $taskRoot '_scratch\ig-native\Scripts\python.exe') -I -S -B $taskReader --inspect --run-id run04 1> (Join-Path $taskOutput 'stdout.log') 2> (Join-Path $taskOutput 'stderr.log')
$taskExit = $LASTEXITCODE
$taskAfter = (Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{ actual_process_exit = $taskExit; reader_sha256_after = $taskAfter; reader_unchanged = ($taskAfter -eq $taskExpected); finished_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskOutput 'stdout.log')
Get-Content -LiteralPath (Join-Path $taskOutput 'result.json')
exit $taskExit
