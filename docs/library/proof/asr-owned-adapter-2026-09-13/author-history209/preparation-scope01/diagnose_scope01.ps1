$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskRun=Join-Path $PSScriptRoot 'runs\scope01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh scope diagnostic label required'}
$taskChild=Join-Path $PSScriptRoot 'diagnostic-child-one.py'
if((Get-FileHash -LiteralPath $taskChild -Algorithm SHA256).Hash.ToLowerInvariant() -cne '28e17420d511118e5afe2dfb998af0e66a0daa279d63844d5d7427697733ec8f'){throw 'Reviewed inert child mismatch'}
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$taskPython='C:\Python314\python.exe'
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null

function Write-ScopeObservation($taskLabel,$taskChosen,$taskUnqualified,$taskGlobal,$taskLocal){
    $taskRow=[ordered]@{label=$taskLabel;chosen_capture=$taskChosen;unqualified_observed=$taskUnqualified;global_observed=$taskGlobal;local_variable_present=($null -ne $taskLocal);local_value=$null;expected_child_exit=1;asr_cases_executed=0}
    if($null -ne $taskLocal){$taskRow.local_value=$taskLocal.Value}
    $taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRow | ConvertTo-Json))
    $taskStream=[IO.File]::Open((Join-Path $taskRun ($taskLabel+'.json')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$taskStream.Write($taskBytes,0,$taskBytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
}

# Observation 1: exact original unqualified reset/capture in script scope.
# A distinct global sentinel makes an unchanged previous exit visible.
$global:LASTEXITCODE=314159
$LASTEXITCODE=$null
& $taskPython -I -S -B $taskChild 1> (Join-Path $taskRun 'original-script-stdout.log') 2> (Join-Path $taskRun 'original-script-stderr.log')
$taskChosen=$LASTEXITCODE
$taskObservedGlobal=$global:LASTEXITCODE
$taskObservedLocal=Get-Variable -Name LASTEXITCODE -Scope Local -ErrorAction SilentlyContinue
Write-ScopeObservation 'original-script' $taskChosen $LASTEXITCODE $taskObservedGlobal $taskObservedLocal

# Observation 2: exact original reset/capture in a called function.
function Invoke-OriginalFunctionObservation {
    $global:LASTEXITCODE=314159
    $LASTEXITCODE=$null
    & $taskPython -I -S -B $taskChild 1> (Join-Path $taskRun 'original-function-stdout.log') 2> (Join-Path $taskRun 'original-function-stderr.log')
    $taskChosen=$LASTEXITCODE
    $taskObservedGlobal=$global:LASTEXITCODE
    $taskObservedLocal=Get-Variable -Name LASTEXITCODE -Scope Local -ErrorAction SilentlyContinue
    Write-ScopeObservation 'original-function' $taskChosen $LASTEXITCODE $taskObservedGlobal $taskObservedLocal
}
Invoke-OriginalFunctionObservation

# Observation 3: proposed explicit global reset/capture in script scope.
$global:LASTEXITCODE=$null
& $taskPython -I -S -B $taskChild 1> (Join-Path $taskRun 'global-script-stdout.log') 2> (Join-Path $taskRun 'global-script-stderr.log')
$taskChosen=$global:LASTEXITCODE
$taskObservedGlobal=$global:LASTEXITCODE
$taskObservedLocal=Get-Variable -Name LASTEXITCODE -Scope Local -ErrorAction SilentlyContinue
Write-ScopeObservation 'global-script' $taskChosen $LASTEXITCODE $taskObservedGlobal $taskObservedLocal

# Observation 4: proposed explicit global reset/capture in a called function.
function Invoke-GlobalFunctionObservation {
    $global:LASTEXITCODE=$null
    & $taskPython -I -S -B $taskChild 1> (Join-Path $taskRun 'global-function-stdout.log') 2> (Join-Path $taskRun 'global-function-stderr.log')
    $taskChosen=$global:LASTEXITCODE
    $taskObservedGlobal=$global:LASTEXITCODE
    $taskObservedLocal=Get-Variable -Name LASTEXITCODE -Scope Local -ErrorAction SilentlyContinue
    Write-ScopeObservation 'global-function' $taskChosen $LASTEXITCODE $taskObservedGlobal $taskObservedLocal
}
Invoke-GlobalFunctionObservation

$taskRows=@()
$taskGlobalMatches=$true
$taskOriginalMatches=$true
$taskCorrectedMatches=$true
foreach($taskLabel in @('original-script','original-function','global-script','global-function')){
    $taskRow=Get-Content -LiteralPath (Join-Path $taskRun ($taskLabel+'.json')) -Raw | ConvertFrom-Json
    $taskRows += $taskRow
    if($taskRow.global_observed -isnot [long] -and $taskRow.global_observed -isnot [int]){$taskGlobalMatches=$false}
    if($taskRow.global_observed -ne 1){$taskGlobalMatches=$false}
    if($taskLabel.StartsWith('original-') -and $taskRow.chosen_capture -ne 1){$taskOriginalMatches=$false}
    if($taskLabel.StartsWith('global-') -and $taskRow.chosen_capture -ne 1){$taskCorrectedMatches=$false}
    if((Get-Item -LiteralPath (Join-Path $taskRun ($taskLabel+'-stderr.log'))).Length -ne 0){$taskGlobalMatches=$false}
}
$taskExit=1
if($taskGlobalMatches -and $taskCorrectedMatches){$taskExit=0}
$taskResult=[ordered]@{schema='uoink.native-exit-scope-diagnostic.v1';powershell_version=$PSVersionTable.PSVersion.ToString();observations=$taskRows;all_global_observations_match_child_exit=$taskGlobalMatches;original_captures_match_child_exit=$taskOriginalMatches;explicit_global_captures_match_child_exit=$taskCorrectedMatches;diagnostic_exit=$taskExit;asr_cases_executed=0;scope='Four inert observations; no previous null native receipt is repaired by these observations'}
$taskResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'result.json') -Encoding utf8
$taskResult | ConvertTo-Json -Depth 8
exit $taskExit
