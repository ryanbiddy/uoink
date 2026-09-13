$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskReader = Join-Path $taskRoot '_scratch\vad-static-inventory-proposal01\read_checkpoint_inventory.py'
$taskOutput = Join-Path $taskRoot '_scratch\vad-static-inventory-run01-launch'
$taskExpected = '15125eebf629e014a20a200f19a3bc627363170a0375c2d49eaf6ed7e7bfb7d7'
if (Test-Path -LiteralPath $taskOutput) { throw 'Fresh launch directory required' }
if ((Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Reader differs from reviewed source' }
New-Item -ItemType Directory -Path $taskOutput | Out-Null
$taskPlan = [ordered]@{
  scope = 'One allowlisted static ZIP/pickle-opcode inventory; no deserialization, object construction, model load, inference or conversion'
  reviewed_reader_sha256 = $taskExpected
  reader = $taskReader
  arguments = @('-I','-S','-B',$taskReader,'--inspect','--run-id','run01')
  checkpoint_copied_to_proof = $false
  reviewer = 'Astra; complete corrected reader and synthetic verdict inspected before execution'
  started_utc = [DateTime]::UtcNow.ToString('o')
}
$taskPlan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOutput 'plan.json') -Encoding utf8
$env:IG_FORBIDDEN_LIVE = [IO.Path]::Combine($env:LOCALAPPDATA,'Uoink','index.db')
& (Join-Path $taskRoot '_scratch\ig-native\Scripts\python.exe') -I -S -B $taskReader --inspect --run-id run01 1> (Join-Path $taskOutput 'stdout.log') 2> (Join-Path $taskOutput 'stderr.log')
$taskExit = $LASTEXITCODE
$taskAfter = (Get-FileHash -LiteralPath $taskReader -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{ actual_process_exit = $taskExit; reader_sha256_after = $taskAfter; reader_unchanged = ($taskAfter -eq $taskExpected); finished_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskOutput 'stdout.log')
Get-Content -LiteralPath (Join-Path $taskOutput 'result.json')
exit $taskExit
