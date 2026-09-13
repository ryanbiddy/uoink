$ErrorActionPreference='Stop'
# The function inherits true from this enclosing scope before the exact block.
$PSNativeCommandUseErrorActionPreference=$true
function Invoke-InertWrapper {
    $taskRun=Join-Path $PSScriptRoot 'runs\instrument02\success02'
    if(Test-Path -LiteralPath $taskRun){throw 'Fresh instrument case required'}
    New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
    $taskPython='C:\Python314\python.exe'
    $taskStdout=Join-Path $taskRun 'stdout.json'
    $taskStderr=Join-Path $taskRun 'stderr.log'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'child-zero.py') -Destination (Join-Path $taskRun 'qualify_adapter.py') -ErrorAction Stop
    $taskExpected=@{'instrument.txt'='cebea3932b7139c83bb057b39e5900a476cae2de05060416e8a5255d80d4da82'}
    $taskRecords=@([ordered]@{name='instrument.txt';source=(Join-Path $taskRun 'source.txt');sha256='cebea3932b7139c83bb057b39e5900a476cae2de05060416e8a5255d80d4da82'})
    [ordered]@{label='success02';inherited_native_error_preference=$PSNativeCommandUseErrorActionPreference;missing_postcheck_expected=$false;asr_cases_executed=0} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'setup.json') -Encoding utf8
    if($PSNativeCommandUseErrorActionPreference -cne $true){throw 'True inherited preference required'}
    [IO.File]::WriteAllBytes((Join-Path $taskRun 'source.txt'),[Convert]::FromBase64String('SU5FUlQgV1JBUFBFUiBQT1NUQ0hFQ0sgVEVYVCBPTkxZCg=='))
    Copy-Item -LiteralPath (Join-Path $taskRun 'source.txt') -Destination (Join-Path $taskRun 'instrument.txt') -ErrorAction Stop
# BEGIN EXACT NATIVE RECEIPT BLOCK
# Override any inherited native-error promotion at this invocation boundary.
$PSNativeCommandUseErrorActionPreference=$false
$global:LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'qualify_adapter.py') 1> $taskStdout 2> $taskStderr
$taskNativeExit=$global:LASTEXITCODE
# Persist the completed-child outcome before any input or result postcheck.
$taskNativeReceipt=[ordered]@{schema='uoink.native-exit.v1';child_returned=$true;native_exit=$taskNativeExit}
$taskNativeBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskNativeReceipt | ConvertTo-Json -Compress))
$taskNativeStream=[IO.File]::Open((Join-Path $taskRun 'native-exit.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{
    $taskNativeStream.Write($taskNativeBytes,0,$taskNativeBytes.Length)
    $taskNativeStream.Flush($true)
}finally{$taskNativeStream.Dispose()}
if($taskNativeExit -isnot [int]){throw 'Returned native exit was not captured as an integer'}
# END EXACT NATIVE RECEIPT BLOCK
$taskAfter=@()
$taskUnchanged=$true
foreach($taskRecord in $taskRecords){
    $taskCopyHash=(Get-FileHash -LiteralPath (Join-Path $taskRun $taskRecord.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskSourceHash=(Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskCopyHash -ne $taskRecord.sha256 -or $taskSourceHash -ne $taskRecord.sha256){$taskUnchanged=$false}
    $taskAfter += [ordered]@{name=$taskRecord.name;before_sha256=$taskRecord.sha256;copy_after_sha256=$taskCopyHash;source_after_sha256=$taskSourceHash}
}
$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8
$taskReceiptValid=$false
$taskReceiptError=$null
try{
    $taskResult=Get-Content -LiteralPath $taskStdout -Raw | ConvertFrom-Json
    $taskPass=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $true }).Count
    $taskFail=@($taskResult.cases | Where-Object { $_.passed -is [bool] -and $_.passed -ceq $false }).Count
    $taskUnique=@($taskResult.cases.name | Sort-Object -Unique).Count
    $taskCountExit=1
    if($taskFail -eq 0){$taskCountExit=0}
    $taskReceiptValid=(
        $taskResult.schema -ceq 'uoink.inert-asr-adapter-qualification.v1' -and
        @($taskResult.cases).Count -eq 58 -and $taskUnique -eq 58 -and
        $taskPass+$taskFail -eq 58 -and $taskResult.passed -eq $taskPass -and $taskResult.failed -eq $taskFail -and
        $taskResult.qualification_exit -eq $taskNativeExit -and $taskNativeExit -eq $taskCountExit -and
        $taskResult.startup_binding_asserted -ceq $true -and $taskResult.torch_backend_autoload_disabled_before_startup -ceq $true -and
        $taskResult.real_resolver_approval_unchanged_none -ceq $true -and $taskResult.real_resolver_functions_unchanged -ceq $true -and
        $taskResult.adapter_globals_restored -ceq $true -and $taskResult.guard_valid -ceq $true -and
        $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 11 -and
        @($taskResult.metadata_trap_mismatches).Count -eq 0 -and
        @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.heavy_roots_loaded).Count -eq 0
    )
    foreach($taskName in $taskExpected.Keys){
        if($taskResult.input_sha256.$taskName -cne $taskExpected[$taskName]){$taskReceiptValid=$false}
    }
}catch{$taskReceiptError=$_.Exception.GetType().Name}
$taskStderrBytes=(Get-Item -LiteralPath $taskStderr).Length
$taskOuterExit=$taskNativeExit
if(-not $taskUnchanged -or -not $taskReceiptValid -or $taskStderrBytes -ne 0){if($taskOuterExit -eq 0){$taskOuterExit=1}}
[ordered]@{native_exit=$taskNativeExit;outer_exit=$taskOuterExit;inputs_unchanged=$taskUnchanged;receipt_valid=$taskReceiptValid;receipt_parse_error_type=$taskReceiptError;stderr_bytes=$taskStderrBytes;startup_binding_set=$true;torch_backend_autoload_disabled=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
exit $taskOuterExit

}
Invoke-InertWrapper
