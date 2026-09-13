$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskBase=$PSScriptRoot
$taskAdmissionPath=Join-Path $taskBase 'ROOT-ADMISSION.json'
if(-not (Test-Path -LiteralPath $taskAdmissionPath -PathType Leaf)){throw 'Exact-source root admission required'}
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
$taskSealPath=Join-Path $taskBase 'SHA256.json'
$taskSealHash=(Get-FileHash -LiteralPath $taskSealPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($taskAdmission.schema -cne 'uoink.asr-instrument-subset-admission.v1' -or $taskAdmission.root_reviewed -cne $true -or $taskAdmission.source_manifest_sha256 -cne $taskSealHash){throw 'Admission does not bind this reviewed preparation'}
$taskSeal=Get-Content -LiteralPath $taskSealPath -Raw | ConvertFrom-Json
foreach($taskRow in $taskSeal.files){
    $taskPath=Join-Path $taskBase $taskRow.path
    if((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRow.sha256 -or (Get-Item -LiteralPath $taskPath).Length -ne $taskRow.bytes){throw 'Prepared input mismatch'}
}
$taskRun=Join-Path $taskBase 'runs\instrument01'
if(Test-Path -LiteralPath $taskRun){throw 'Fresh instrument label required'}
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'
$taskPowerShell='C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
$taskPython='C:\Python314\python.exe'

function Write-FlushedJson($taskPath,$taskValue){
    $taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskValue | ConvertTo-Json -Depth 10))
    $taskStream=[IO.File]::Open($taskPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$taskStream.Write($taskBytes,0,$taskBytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
}

Write-FlushedJson (Join-Path $taskRun 'plan.json') ([ordered]@{preparation_manifest_sha256=$taskSealHash;powershell=$taskPowerShell;python=$taskPython;planned_wrapper_outcomes=2;planned_guard_checks=4;asr_cases_executed=0;startup_binding_set=$true;torch_backend_autoload_disabled=$true})
$taskOutcomes=@()
foreach($taskLabel in @('missing01','success01')){
    $taskWrapper=Join-Path $taskBase ('wrapper-'+$taskLabel+'.ps1')
    $taskLog=Join-Path $taskRun ($taskLabel+'-wrapper-stdout.log')
    $taskErrorLog=Join-Path $taskRun ($taskLabel+'-wrapper-stderr.log')
    $PSNativeCommandUseErrorActionPreference=$false
    $LASTEXITCODE=$null
    & $taskPowerShell -NoLogo -NoProfile -NonInteractive -File $taskWrapper 1> $taskLog 2> $taskErrorLog
    $taskWrapperExit=$LASTEXITCODE
    Write-FlushedJson (Join-Path $taskRun ($taskLabel+'-actual-wrapper-exit.json')) ([ordered]@{actual_wrapper_exit=$taskWrapperExit;executable=$taskPowerShell;arguments=@('-NoLogo','-NoProfile','-NonInteractive','-File',$taskWrapper)})
    $taskCase=Join-Path $taskRun $taskLabel
    $taskNative=Get-Content -LiteralPath (Join-Path $taskCase 'native-exit.json') -Raw | ConvertFrom-Json
    $taskSetup=Get-Content -LiteralPath (Join-Path $taskCase 'setup.json') -Raw | ConvertFrom-Json
    $taskExpectedNative=0
    $taskExpectedWrapper=0
    if($taskLabel -ceq 'missing01'){$taskExpectedNative=1;$taskExpectedWrapper=1}
    $taskPassed=($taskNative.schema -ceq 'uoink.native-exit.v1' -and $taskNative.child_returned -ceq $true -and $taskNative.native_exit -eq $taskExpectedNative -and $taskWrapperExit -eq $taskExpectedWrapper -and $taskSetup.inherited_native_error_preference -ceq $true)
    if($taskLabel -ceq 'missing01'){
        $taskPassed=$taskPassed -and -not (Test-Path -LiteralPath (Join-Path $taskCase 'exit.json')) -and -not (Test-Path -LiteralPath (Join-Path $taskCase 'after.json'))
    }else{
        $taskFinal=Get-Content -LiteralPath (Join-Path $taskCase 'exit.json') -Raw | ConvertFrom-Json
        $taskPassed=$taskPassed -and $taskFinal.native_exit -eq 0 -and $taskFinal.outer_exit -eq 0 -and $taskFinal.inputs_unchanged -ceq $true -and $taskFinal.receipt_valid -ceq $true -and $taskFinal.stderr_bytes -eq 0
    }
    $taskOutcomes += [ordered]@{name=$taskLabel;passed=$taskPassed;actual_native_exit=$taskNative.native_exit;actual_wrapper_exit=$taskWrapperExit;expected_wrapper_failure=($taskLabel -ceq 'missing01')}
    if(-not $taskPassed){
        Write-FlushedJson (Join-Path $taskRun 'unexpected-outcome.json') ([ordered]@{outcomes=$taskOutcomes;remaining_checks_not_run=$true;actual_outer_exit=1;asr_cases_executed=0})
        exit 1
    }
}
$taskGuardStdout=Join-Path $taskRun 'guards-stdout.json'
$taskGuardStderr=Join-Path $taskRun 'guards-stderr.log'
$PSNativeCommandUseErrorActionPreference=$false
$LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskBase 'qualify_guards.py') 1> $taskGuardStdout 2> $taskGuardStderr
$taskGuardExit=$LASTEXITCODE
Write-FlushedJson (Join-Path $taskRun 'guards-actual-native-exit.json') ([ordered]@{actual_native_exit=$taskGuardExit;executable=$taskPython;arguments=@('-I','-S','-B',(Join-Path $taskBase 'qualify_guards.py'))})
$taskGuards=Get-Content -LiteralPath $taskGuardStdout -Raw | ConvertFrom-Json
$taskGuardNames=@('complete','replaced','removed','missing_registry_entry')
$taskGuardValid=($taskGuardExit -eq 0 -and $taskGuards.native_exit -eq 0 -and $taskGuards.schema -ceq 'uoink.asr-instrument-traps.v1' -and $taskGuards.guard_valid -ceq $true -and $taskGuards.passed -eq 4 -and $taskGuards.failed -eq 0 -and @($taskGuards.cases).Count -eq 4 -and @($taskGuards.guard_denials).Count -eq 0 -and @($taskGuards.heavy_roots_loaded).Count -eq 0 -and (Get-Item -LiteralPath $taskGuardStderr).Length -eq 0)
for($taskIndex=0;$taskIndex -lt 4;$taskIndex++){
    if($taskGuards.cases[$taskIndex].name -cne $taskGuardNames[$taskIndex] -or $taskGuards.cases[$taskIndex].passed -cne $true){$taskGuardValid=$false}
}
$taskUnchanged=$true
foreach($taskRow in $taskSeal.files){
    $taskPath=Join-Path $taskBase $taskRow.path
    if((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRow.sha256 -or (Get-Item -LiteralPath $taskPath).Length -ne $taskRow.bytes){$taskUnchanged=$false}
}
$taskOuterExit=1
if($taskGuardValid -and $taskUnchanged){$taskOuterExit=0}
Write-FlushedJson (Join-Path $taskRun 'result.json') ([ordered]@{wrapper_outcomes=$taskOutcomes;guard_cases=$taskGuards.cases;guard_valid=$taskGuardValid;inputs_unchanged=$taskUnchanged;outer_exit=$taskOuterExit;asr_cases_executed=0;scope='Two wrapper outcomes and four trap checks only; fabricated rows are not ASR cases'})
exit $taskOuterExit
