$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-fixed-converter-proposal01'
$taskRun=Join-Path $taskProposal 'converter-preflight03'
if (Test-Path -LiteralPath $taskRun) {throw 'Fresh label required'}
$taskFiles=@(@('fixed_converter.py',(Join-Path $taskProposal 'fixed_converter.py')),@('zip_bounds.py',(Join-Path $taskProposal 'zip_bounds.py')),@('fixed-plan.json',(Join-Path $taskProposal 'fixed-plan.json')),@('qualify_converter.py',(Join-Path $taskProposal 'qualify_converter.py')),@('reviewed_zip_reader.txt',(Join-Path $taskBase '_scratch\vad-static-metadata-tail01\read_checkpoint_inventory.py')))
$taskRecords=@()
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskPair in $taskFiles){
    $taskBefore=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $taskPair[1] -Destination (Join-Path $taskRun $taskPair[0]) -ErrorAction Stop
    if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskPair[0]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskBefore){throw 'Input copy mismatch'}
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskBefore}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='converter-preflight03';inputs=$taskRecords;startup_binding_set=$true;arguments=@('-I','-S','-B','qualify_converter.py');no_actual_artifact=$true} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& (Join-Path $taskBase '_scratch\ig-native\Scripts\python.exe') -I -S -B (Join-Path $taskRun 'qualify_converter.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit=$LASTEXITCODE
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false};if((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if ((Get-Item -LiteralPath (Join-Path $taskRun 'stdout.json')).Length -gt 0){$taskOutput=Get-Content -Raw -LiteralPath (Join-Path $taskRun 'stdout.json') | ConvertFrom-Json;$taskOutput | Select-Object passed,failed,elapsed_seconds,qualification_exit; $taskOutput.cases | Where-Object {-not $_.passed} | ConvertTo-Json -Depth 4}
Get-Content -LiteralPath (Join-Path $taskRun 'stderr.log')
if(-not $taskUnchanged){throw 'Qualification source changed'}
exit $taskExit
