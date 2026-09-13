$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
if($PSVersionTable.PSVersion.Major -lt 7){throw 'PowerShell 7 is required to measure inherited native-command errors'}
$taskRoot=[IO.Path]::GetFullPath($PSScriptRoot)
if([IO.Path]::GetFileName($taskRoot) -cne 'wrapper-preflight01'){throw 'Fresh reviewed qualifier directory required'}
if($env:IG_FORBIDDEN_LIVE -cne 'C:\Users\hello\AppData\Local\Uoink\index.db'){throw 'Required lexical startup binding is absent'}
$taskPwsh=Join-Path $PSHOME 'pwsh.exe'
$taskInputNames=@('run-root.original.ps1','run-root.repaired.ps1','inert_child.py','call_wrapper.ps1','qualify_wrapper.ps1')
$taskInputHashes=@{}
foreach($taskName in $taskInputNames){$taskInputHashes[$taskName]=(Get-FileHash -LiteralPath (Join-Path $taskRoot $taskName) -Algorithm SHA256).Hash.ToLowerInvariant()}
if($taskInputHashes['run-root.original.ps1'] -cne '75b8058874a0389ccdd02f63815b1430b543967e5ad232904bbb86b7a0073a23'){throw 'Original wrapper source changed'}
if($taskInputHashes['run-root.repaired.ps1'] -cne '11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63'){throw 'Repaired wrapper source changed'}
if($taskInputHashes['inert_child.py'] -cne '9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f'){throw 'Inert child source changed'}
$taskCases=Join-Path $taskRoot 'cases'
if(Test-Path -LiteralPath $taskCases){throw 'Generated cases cannot be reused'}
New-Item -ItemType Directory -Path $taskCases -ErrorAction Stop | Out-Null
$taskPlan=@()
foreach($taskPreference in @('false','true')){foreach($taskCode in 0..3){
    $taskPlan += [ordered]@{name="repaired-$taskPreference-$taskCode";kind='repaired';code=$taskCode;inherited=$taskPreference;postcheck='false';diagnostic=$false}
}}
foreach($taskCode in 0..3){$taskPlan += [ordered]@{name="repaired-postcheck-$taskCode";kind='repaired';code=$taskCode;inherited='true';postcheck='true';diagnostic=$false}}
foreach($taskCode in 0..3){$taskPlan += [ordered]@{name="original-true-$taskCode";kind='original';code=$taskCode;inherited='true';postcheck='false';diagnostic=$true}}
$taskPlan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRoot 'case-plan.json') -Encoding utf8
$taskOutcomes=@()
$taskStarted=[DateTime]::UtcNow
function Assert-Case([bool]$Condition,[string]$Reason){if(-not $Condition){throw $Reason}}
function Save-ProcessOutcome([string]$Path,$Outcome){
    $taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($Outcome | ConvertTo-Json) + "`n")
    $taskStream=[IO.FileStream]::new($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try{$taskStream.Write($taskBytes,0,$taskBytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
}
foreach($taskCasePlan in $taskPlan){
    $taskCaseRoot=Join-Path $taskCases $taskCasePlan.name
    New-Item -ItemType Directory -Path $taskCaseRoot -ErrorAction Stop | Out-Null
    $taskWrapperName='run-root.'+$taskCasePlan.kind+'.ps1'
    Copy-Item -LiteralPath (Join-Path $taskRoot $taskWrapperName) -Destination (Join-Path $taskCaseRoot 'run-root.ps1')
    Copy-Item -LiteralPath (Join-Path $taskRoot 'inert_child.py') -Destination (Join-Path $taskCaseRoot 'launch_d1.py')
    $taskCommand=@('-NoLogo','-NoProfile','-NonInteractive','-File',(Join-Path $taskRoot 'call_wrapper.ps1'),'-CaseRoot',$taskCaseRoot,'-RequestedExit',[string]$taskCasePlan.code,'-InheritedNativeErrors',$taskCasePlan.inherited,'-ThrowPostcheck',$taskCasePlan.postcheck,'-WrapperKind',$taskCasePlan.kind)
    [ordered]@{executable=$taskPwsh;arguments=$taskCommand;timeout_seconds=15;child_fixture_sha256=$taskInputHashes['inert_child.py'];wrapper_fixture_sha256=$taskInputHashes[$taskWrapperName]} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskCaseRoot 'command.json') -Encoding utf8
    $taskStartInfo=[Diagnostics.ProcessStartInfo]::new()
    $taskStartInfo.FileName=$taskPwsh
    $taskStartInfo.WorkingDirectory=$taskCaseRoot
    $taskStartInfo.UseShellExecute=$false
    $taskStartInfo.CreateNoWindow=$true
    $taskStartInfo.RedirectStandardOutput=$true
    $taskStartInfo.RedirectStandardError=$true
    foreach($taskArgument in $taskCommand){$taskStartInfo.ArgumentList.Add($taskArgument)}
    $taskProcess=[Diagnostics.Process]::new()
    $taskProcess.StartInfo=$taskStartInfo
    $taskActualExit=$null
    $taskTimeout=$false
    $taskStartError=$null
    $taskCaptureError=$null
    $taskStdout=''
    $taskStderr=''
    try{
        if(-not $taskProcess.Start()){throw 'Caller process did not start'}
        $taskOutRead=$taskProcess.StandardOutput.ReadToEndAsync()
        $taskErrRead=$taskProcess.StandardError.ReadToEndAsync()
        if(-not $taskProcess.WaitForExit(15000)){
            $taskTimeout=$true
            $taskProcess.Kill($true)
            if(-not $taskProcess.WaitForExit(5000)){throw 'Timed-out owned process did not finish after kill'}
        }
        $taskActualExit=$taskProcess.ExitCode
    }catch{$taskStartError=$_.Exception.GetType().FullName}
    finally{
        Save-ProcessOutcome (Join-Path $taskCaseRoot 'actual-process-exit.json') ([ordered]@{actual_caller_process_exit=$taskActualExit;timed_out=$taskTimeout;process_error_type=$taskStartError})
    }
    try{
        if($null -ne $taskActualExit){
            $taskStdout=$taskOutRead.GetAwaiter().GetResult()
            $taskStderr=$taskErrRead.GetAwaiter().GetResult()
        }
    }catch{
        $taskCaptureError=$_.Exception.GetType().FullName
        Save-ProcessOutcome (Join-Path $taskCaseRoot 'process-stream-error.json') ([ordered]@{stream_read_error_type=$taskCaptureError;actual_caller_process_exit=$taskActualExit;native_outcome_receipt_preserved=$true})
    }finally{$taskProcess.Dispose()}
    [IO.File]::WriteAllText((Join-Path $taskCaseRoot 'process-stdout.log'),$taskStdout,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $taskCaseRoot 'process-stderr.log'),$taskStderr,[Text.UTF8Encoding]::new($false))
    $taskMatched=$false
    $taskReason=$null
    try{
        Assert-Case (-not $taskTimeout -and $null -eq $taskStartError -and $null -ne $taskActualExit) 'Caller start/timeout outcome is unqualified'
        Assert-Case ($null -eq $taskCaptureError) 'Captured process stream is unavailable'
        Assert-Case ($taskStderr.Length -eq 0) 'Unexpected caller stderr'
        $taskObserved=Get-Content -LiteralPath (Join-Path $taskCaseRoot 'caller-observation.json') -Raw | ConvertFrom-Json
        $taskOuter=Join-Path $taskCaseRoot 'outer-d1-real-01'
        $taskChild=Get-Content -LiteralPath (Join-Path $taskOuter 'stdout.log') -Raw | ConvertFrom-Json
        Assert-Case ($taskChild.scope -ceq 'uoink-d1-wrapper-fixture-v1' -and $taskChild.requested_exit -eq $taskCasePlan.code -and $taskChild.startup_binding_asserted -ceq $true -and $taskChild.d1_source_executed -ceq $false) 'Expected inert native outcome is absent'
        Assert-Case ((Get-Item -LiteralPath (Join-Path $taskOuter 'stderr.log')).Length -eq 0) 'Unexpected inert native stderr'
        Assert-Case ($taskObserved.inherited_native_errors -ceq ($taskCasePlan.inherited -ceq 'true') -and $taskObserved.requested_exit -eq $taskCasePlan.code -and $taskObserved.last_native_exit -eq $taskCasePlan.code -and $taskObserved.caller_process_exit -eq $taskActualExit -and $taskObserved.original_d1_source_executed -ceq $false) 'Caller receipt disagrees with planned/native outcome'
        if($taskCasePlan.kind -ceq 'repaired'){
            $taskRaw=[IO.File]::ReadAllText((Join-Path $taskOuter 'raw-exit.txt'),[Text.Encoding]::ASCII)
            Assert-Case ($taskRaw -ceq ([string]$taskCasePlan.code + "`n")) 'Durable raw exit differs from inert native exit'
            $taskJson=Get-Content -LiteralPath (Join-Path $taskOuter 'actual-exit.json') -Raw | ConvertFrom-Json
            Assert-Case ($taskJson.actual_outer_exit -eq $taskCasePlan.code) 'JSON native exit differs from raw receipt'
            if($taskCasePlan.postcheck -ceq 'true'){
                Assert-Case ($taskActualExit -eq 91 -and $taskObserved.disposition -ceq 'wrapper_threw' -and $taskObserved.exception_message -ceq 'INTENTIONAL_D1_WRAPPER_POSTCHECK_FAILURE') 'Expected late postcheck failure did not remain separate'
            }else{
                Assert-Case ($taskActualExit -eq $taskCasePlan.code -and $taskObserved.disposition -ceq 'wrapper_returned') 'Repaired wrapper did not propagate native exit'
            }
        }elseif($taskCasePlan.code -eq 0){
            $taskJson=Get-Content -LiteralPath (Join-Path $taskOuter 'actual-exit.json') -Raw | ConvertFrom-Json
            Assert-Case ($taskActualExit -eq 0 -and $taskJson.actual_outer_exit -eq 0 -and $taskObserved.disposition -ceq 'wrapper_returned') 'Original zero-exit control did not complete'
        }else{
            Assert-Case ($taskActualExit -eq 91 -and $taskObserved.disposition -ceq 'wrapper_threw' -and $taskObserved.exception_type -like '*NativeCommandExitException') 'Source-diagnosed original nonzero failure did not reproduce'
            Assert-Case (-not (Test-Path -LiteralPath (Join-Path $taskOuter 'actual-exit.json'))) 'Original control unexpectedly recorded its skipped receipt'
        }
        Assert-Case ((Get-FileHash -LiteralPath (Join-Path $taskCaseRoot 'run-root.ps1') -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskInputHashes[$taskWrapperName]) 'Wrapper fixture source changed'
        Assert-Case ((Get-FileHash -LiteralPath (Join-Path $taskCaseRoot 'launch_d1.py') -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskInputHashes['inert_child.py']) 'Inert child fixture source changed'
        $taskMatched=$true
    }catch{$taskReason=$_.Exception.Message}
    $taskOutcomes += [ordered]@{name=$taskCasePlan.name;diagnostic_only=$taskCasePlan.diagnostic;expectations_matched=$taskMatched;requested_native_exit=$taskCasePlan.code;actual_caller_process_exit=$taskActualExit;timed_out=$taskTimeout;reason=$taskReason}
    $taskOutcomes | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRoot 'observations-partial.json') -Encoding utf8
    if($taskTimeout -or $null -ne $taskStartError -or $null -ne $taskCaptureError){break}
}
$taskInputsUnchanged=$true
foreach($taskName in $taskInputNames){if((Get-FileHash -LiteralPath (Join-Path $taskRoot $taskName) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInputHashes[$taskName]){$taskInputsUnchanged=$false}}
$taskRepair=@($taskOutcomes | Where-Object {-not $_.diagnostic_only})
$taskControls=@($taskOutcomes | Where-Object {$_.diagnostic_only})
$taskPassed=@($taskRepair | Where-Object {$_.expectations_matched}).Count
$taskFailed=$taskRepair.Count-$taskPassed
$taskControlsMatched=@($taskControls | Where-Object {$_.expectations_matched}).Count
$taskExit=if($taskRepair.Count -eq 12 -and $taskPassed -eq 12 -and $taskControls.Count -eq 4 -and $taskControlsMatched -eq 4 -and $taskInputsUnchanged){0}else{1}
$taskResult=[ordered]@{schema='uoink.d1-wrapper-inert-qualification.v1';repaired_passed=$taskPassed;repaired_failed=$taskFailed;original_diagnostic_count=$taskControls.Count;original_diagnostics_matched=$taskControlsMatched;original_wrapper_qualified=$false;cases=$taskOutcomes;elapsed_seconds=([DateTime]::UtcNow-$taskStarted).TotalSeconds;input_sha256=$taskInputHashes;inputs_unchanged=$taskInputsUnchanged;powershell_version=[string]$PSVersionTable.PSVersion;actual_d1_invoked=$false;qualification_exit=$taskExit}
$taskResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRoot 'result.json') -Encoding utf8
exit $taskExit
