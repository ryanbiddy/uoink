$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskBase '_scratch\vad-fixed-converter-proposal01\converter-preflight03'
$taskRun=Join-Path $taskBase '_scratch\astra-vad-converter-synthetic01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh label required'}
$taskInputs=[ordered]@{
 'fixed_converter.py'='b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b'
 'zip_bounds.py'='bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6'
 'fixed-plan.json'='37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf'
 'qualify_converter.py'='11f9addddf9b349c4ee249c000cc60c4986b989de2e11ec990ba940d6b7949a9'
 'reviewed_zip_reader.txt'='67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5'
}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
foreach($taskName in $taskInputs.Keys){
 $taskOriginal=Join-Path $taskSource $taskName
 if((Get-FileHash -LiteralPath $taskOriginal -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInputs[$taskName]){throw 'Source hash mismatch'}
 Copy-Item -LiteralPath $taskOriginal -Destination (Join-Path $taskRun $taskName) -ErrorAction Stop
 if((Get-FileHash -LiteralPath (Join-Path $taskRun $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInputs[$taskName]){throw 'Copy hash mismatch'}
}
Get-ChildItem Env: | Where-Object {$_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_'} | ForEach-Object {Remove-Item -LiteralPath ('Env:'+$_.Name)}
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='astra-vad-converter-synthetic01';inputs=$taskInputs;python='C:\Python314\python.exe';arguments=@('-I','-S','-B','qualify_converter.py');startup_binding_set=$true;no_actual_artifact=$true} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& C:\Python314\python.exe -I -S -B (Join-Path $taskRun 'qualify_converter.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit=$LASTEXITCODE
$taskUnchanged=$true
foreach($taskName in $taskInputs.Keys){
 foreach($taskLocation in @($taskSource,$taskRun)){
  if((Get-FileHash -LiteralPath (Join-Path $taskLocation $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInputs[$taskName]){$taskUnchanged=$false}
 }
}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if(-not $taskUnchanged){throw 'Inputs changed'}
if($taskExit -eq 0){
 $taskResult=Get-Content -Raw -LiteralPath (Join-Path $taskRun 'stdout.json') | ConvertFrom-Json
 if($taskResult.passed -ne 82 -or $taskResult.failed -ne 0 -or $taskResult.qualification_exit -ne 0 -or $taskResult.unexpected_audit_events.Count -ne 0 -or -not $taskResult.input_hashes_unchanged -or (Get-Item -LiteralPath (Join-Path $taskRun 'stderr.log')).Length -ne 0){throw 'Result validation failed'}
 $taskResult | Select-Object passed,failed,elapsed_seconds,qualification_exit
}
exit $taskExit
