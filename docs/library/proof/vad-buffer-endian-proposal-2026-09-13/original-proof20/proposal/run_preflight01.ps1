$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-buffer-endian-proposal01'
$taskRun=Join-Path $taskProposal 'buffer-preflight01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh label required'}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
$taskRecords=@()
foreach($taskName in @('buffer_basis.py','qualify_basis.py')){
 $taskSource=Join-Path $taskProposal $taskName
 $taskHash=(Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
 Copy-Item -LiteralPath $taskSource -Destination (Join-Path $taskRun $taskName) -ErrorAction Stop
 if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash){throw 'Copy mismatch'}
 $taskRecords+=[ordered]@{name=$taskName;source=$taskSource;sha256=$taskHash}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='buffer-preflight01';inputs=$taskRecords;startup_binding_set=$true;arguments=@('-I','-S','-B','qualify_basis.py');synthetic_only=$true} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& (Join-Path $taskBase '_scratch\ig-native\Scripts\python.exe') -I -S -B (Join-Path $taskRun 'qualify_basis.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit=$LASTEXITCODE
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){foreach($taskPath in @($taskRecord.source,(Join-Path $taskRun $taskRecord.name))){if((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256){$taskUnchanged=$false}}}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if((Get-Item -LiteralPath (Join-Path $taskRun 'stdout.json')).Length -gt 0){Get-Content -Raw -LiteralPath (Join-Path $taskRun 'stdout.json') | ConvertFrom-Json | Select-Object passed,failed,elapsed_seconds,qualification_exit,synthetic_operation_order_maximum_ulp | ConvertTo-Json -Depth 4}
Get-Content -LiteralPath (Join-Path $taskRun 'stderr.log')
if(-not $taskUnchanged){throw 'Inputs changed'}
exit $taskExit
