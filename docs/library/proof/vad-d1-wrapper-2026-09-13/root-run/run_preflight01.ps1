$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
if($PSVersionTable.PSVersion.Major -lt 7){throw 'Use PowerShell 7 for this qualification'}
$taskProposal='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-d1-wrapper-qualification01'
$taskRun=Join-Path $taskProposal 'wrapper-preflight01'
$taskAdmission=Join-Path $taskProposal 'ROOT-ADMISSION.md'
if(-not (Test-Path -LiteralPath $taskAdmission -PathType Leaf)){throw 'Root exact-source admission is required'}
if(Test-Path -LiteralPath $taskRun){throw 'Fresh qualification label required'}
$taskExpected=@{
    'run-root.original.ps1'='75b8058874a0389ccdd02f63815b1430b543967e5ad232904bbb86b7a0073a23'
    'run-root.repaired.ps1'='11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63'
    'inert_child.py'='9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f'
    'call_wrapper.ps1'='3165e20b0b8f836f37fac7175a3433adfbf0e740952e091dd389f02e32d5c1df'
    'qualify_wrapper.ps1'='4aa3bc369618da8b668e68a13122673ff2fb70c32ecd183d3e2aa32ecf80e104'
}
$taskFiles=@(
    @('run-root.original.ps1',(Join-Path $taskProposal 'before\run-root.ps1')),
    @('run-root.repaired.ps1',(Join-Path $taskProposal 'run-root.repaired.ps1')),
    @('inert_child.py',(Join-Path $taskProposal 'inert_child.py')),
    @('call_wrapper.ps1',(Join-Path $taskProposal 'call_wrapper.ps1')),
    @('qualify_wrapper.ps1',(Join-Path $taskProposal 'qualify_wrapper.ps1')),
    @('REPAIR-BRIEF-2026-09-13.md',(Join-Path $taskProposal 'REPAIR-BRIEF-2026-09-13.md')),
    @('SOURCE-REVIEW-VERDICT.md',(Join-Path $taskProposal 'SOURCE-REVIEW-VERDICT.md')),
    @('QUALIFICATION01-PROTOCOL.md',(Join-Path $taskProposal 'QUALIFICATION01-PROTOCOL.md')),
    @('PREQUALIFICATION-OUTCOME-REFINEMENT.md',(Join-Path $taskProposal 'PREQUALIFICATION-OUTCOME-REFINEMENT.md')),
    @('ORIGINAL-BINDINGS.json',(Join-Path $taskProposal 'ORIGINAL-BINDINGS.json')),
    @('wrapper-repair.patch.txt',(Join-Path $taskProposal 'wrapper-repair.patch.txt')),
    @('run_preflight01.ps1',(Join-Path $taskProposal 'run_preflight01.ps1')),
    @('ROOT-ADMISSION.md',$taskAdmission)
)
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
$taskRecords=@()
foreach($taskPair in $taskFiles){
    $taskHash=(Get-FileHash -LiteralPath $taskPair[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskExpected.ContainsKey($taskPair[0]) -and $taskExpected[$taskPair[0]] -cne $taskHash){throw 'Reviewed code input differs'}
    $taskCopy=Join-Path $taskRun $taskPair[0]
    Copy-Item -LiteralPath $taskPair[1] -Destination $taskCopy
    if((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskHash){throw 'Copied input differs'}
    $taskRecords += [ordered]@{name=$taskPair[0];source=$taskPair[1];sha256=$taskHash}
}
Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(API.?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$taskPwsh=Join-Path $PSHOME 'pwsh.exe'
[ordered]@{label='wrapper-preflight01';executable=$taskPwsh;arguments=@('-NoLogo','-NoProfile','-NonInteractive','-File','qualify_wrapper.ps1');inputs=$taskRecords;startup_binding_set=$true;planned_repair_cases=12;planned_original_diagnostics=4;actual_d1_invocation_authorized=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& $taskPwsh -NoLogo -NoProfile -NonInteractive -File (Join-Path $taskRun 'qualify_wrapper.ps1') 1> (Join-Path $taskRun 'qualifier-stdout.log') 2> (Join-Path $taskRun 'qualifier-stderr.log')
$taskNativeExit=$LASTEXITCODE
[string]$taskNativeExit | Set-Content -LiteralPath (Join-Path $taskRun 'native-exit.txt') -Encoding ascii
$taskAfter=@()
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    $taskCopyHash=(Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskSourceHash=(Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskCopyHash -cne $taskRecord.sha256 -or $taskSourceHash -cne $taskRecord.sha256){$taskUnchanged=$false}
    $taskAfter += [ordered]@{name=$taskRecord.name;before_sha256=$taskRecord.sha256;copy_after_sha256=$taskCopyHash;source_after_sha256=$taskSourceHash}
}
$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8
$taskValid=$false
$taskReceiptError=$null
try{
    $taskResult=Get-Content -LiteralPath (Join-Path $taskRun 'result.json') -Raw | ConvertFrom-Json
    $taskRepair=@($taskResult.cases | Where-Object {$_.diagnostic_only -ceq $false})
    $taskControls=@($taskResult.cases | Where-Object {$_.diagnostic_only -ceq $true})
    $taskPass=@($taskRepair | Where-Object {$_.expectations_matched -ceq $true}).Count
    $taskControlMatches=@($taskControls | Where-Object {$_.expectations_matched -ceq $true}).Count
    $taskExpectedExit=if($taskRepair.Count -eq 12 -and $taskPass -eq 12 -and $taskControls.Count -eq 4 -and $taskControlMatches -eq 4 -and $taskResult.inputs_unchanged -ceq $true){0}else{1}
    $taskValid=(
        $taskResult.schema -ceq 'uoink.d1-wrapper-inert-qualification.v1' -and
        $taskResult.qualification_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskExpectedExit -and
        $taskResult.repaired_passed -eq $taskPass -and $taskResult.repaired_failed -eq ($taskRepair.Count-$taskPass) -and
        $taskResult.original_diagnostic_count -eq $taskControls.Count -and $taskResult.original_diagnostics_matched -eq $taskControlMatches -and
        $taskResult.original_wrapper_qualified -ceq $false -and $taskResult.actual_d1_invoked -ceq $false -and
        @($taskResult.cases.name | Sort-Object -Unique).Count -eq @($taskResult.cases).Count
    )
    foreach($taskName in $taskExpected.Keys){if($taskResult.input_sha256.$taskName -cne $taskExpected[$taskName]){$taskValid=$false}}
}catch{$taskReceiptError=$_.Exception.GetType().FullName}
$taskStderrBytes=(Get-Item -LiteralPath (Join-Path $taskRun 'qualifier-stderr.log')).Length
$taskOuterExit=$taskNativeExit
if(-not $taskValid -or -not $taskUnchanged -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{native_qualifier_exit=$taskNativeExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;result_valid=$taskValid;result_error_type=$taskReceiptError;stderr_bytes=$taskStderrBytes;actual_d1_invoked=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit
