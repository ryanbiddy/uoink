$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskHere=$PSScriptRoot
$taskPython='C:\Python314\python.exe'
$taskPowerShell='C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
$taskInputPath=Join-Path $taskHere 'SOURCE-INPUTS.json'
$taskAdmissionPath=Join-Path $taskHere 'ROOT-ADMISSION.json'
$taskInputsHash=(Get-FileHash -LiteralPath $taskInputPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmissionHash=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskInputs=Get-Content -LiteralPath $taskInputPath -Raw | ConvertFrom-Json
$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json
if($taskAdmission.source_inputs_sha256 -cne $taskInputsHash -or $taskAdmission.label -cne 'notice01' -or
   $taskAdmission.source_tests_and_inert_blocks_approved -cne $true -or
   $taskAdmission.full_build_or_models_approved -cne $false){throw 'Exact root admission missing'}

function Save-NoticeReceipt([string]$name,$value){
    $raw=[Text.UTF8Encoding]::new($false).GetBytes(($value | ConvertTo-Json -Depth 15)+"`n")
    $stream=[IO.File]::Open((Join-Path $taskHere $name),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$stream.Write($raw,0,$raw.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}
function Read-InputState {
    $rows=[Collections.Generic.List[object]]::new()
    foreach($inputFile in $taskInputs.files){
        $path=Join-Path $taskHere $inputFile.path
        $size=(Get-Item -LiteralPath $path).Length
        $digest=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if($size -ne $inputFile.bytes -or $digest -cne $inputFile.sha256){throw 'Qualification input differs'}
        $rows.Add([ordered]@{path=$inputFile.path;bytes=$size;sha256=$digest})
    }
    foreach($copy in (Get-Content -LiteralPath (Join-Path $taskHere 'COPY-BINDINGS.json') -Raw | ConvertFrom-Json)){
        if((Get-Item -LiteralPath $copy.source).Length -ne $copy.bytes -or
           (Get-FileHash -LiteralPath $copy.source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $copy.sha256){throw 'Original source changed since copy'}
    }
    if((Get-FileHash -LiteralPath $taskInputPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInputsHash -or
       (Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHash){throw 'Input/admission control changed'}
    return $rows.ToArray()
}

$taskOutputs=@('inputs-before01.json','inputs-after01.json','pytest-profile01','pytest-stdout01.log','pytest-stderr01.log',
    'pytest-native-exit01.json','pytest-bootstrap01.json','pytest-validated01.json','validate-stdout01.log','validate-stderr01.log',
    'validate-native-exit01.json','blocks-stdout01.log','blocks-stderr01.log','blocks-native-exit01.json','notice-blocks01',
    'overlay\_scratch\notice01-temp','overlay\_scratch\notice01-partition','overlay\_scratch\notice01.xml','overlay\_scratch\notice01-heavy.json','LAUNCH-RESULT01.json')
foreach($name in $taskOutputs){if(Test-Path -LiteralPath (Join-Path $taskHere $name)){throw 'Fresh notice01 outcome paths required'}}
Save-NoticeReceipt 'inputs-before01.json' ([ordered]@{files=@(Read-InputState);source_inputs_sha256=$taskInputsHash;admission_sha256=$taskAdmissionHash})
$taskSavedEnv=@{}
$taskScrub=@(Get-ChildItem Env: | Where-Object {$_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|AWS_|AZURE_|CODEX_API|CLAUDE_API)' -or $_.Name -match '^(HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|PYTHONPATH|PYTHONHOME|PYTHONSTARTUP|PYTEST_ADDOPTS|PYTEST_PLUGINS|SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE)$'})
foreach($entry in $taskScrub){$taskSavedEnv[$entry.Name]=$entry.Value;[Environment]::SetEnvironmentVariable($entry.Name,$null,'Process')}
$taskAssigned=@{IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db';PYTHONDONTWRITEBYTECODE='1';PYTHONUTF8='1';PYTEST_DISABLE_PLUGIN_AUTOLOAD='1';PHASE3_REQUIRE_IMPLEMENTATION='1';PY_COLORS='0';NO_COLOR='1'}
foreach($name in $taskAssigned.Keys){if(-not $taskSavedEnv.ContainsKey($name)){$taskSavedEnv[$name]=[Environment]::GetEnvironmentVariable($name,'Process')};[Environment]::SetEnvironmentVariable($name,$taskAssigned[$name],'Process')}
$taskExit=1;$taskFailure=$null;$taskAfterValid=$false
$taskClock=[Diagnostics.Stopwatch]::StartNew()
try{
    New-Item -ItemType Directory -Path (Join-Path $taskHere 'pytest-profile01') -ErrorAction Stop | Out-Null
    $PSNativeCommandUseErrorActionPreference=$false
    & $taskPython -I -S -B (Join-Path $taskHere 'notice_bootstrap.py') 1>(Join-Path $taskHere 'pytest-stdout01.log') 2>(Join-Path $taskHere 'pytest-stderr01.log')
    $taskNative=$global:LASTEXITCODE
    Save-NoticeReceipt 'pytest-native-exit01.json' ([ordered]@{native_exit=$taskNative;executable=$taskPython;flags=@('-I','-S','-B');elapsed_seconds=$taskClock.Elapsed.TotalSeconds})
    if($taskNative -ne 0){throw "Pytest source check failed: $taskNative"}
    $PSNativeCommandUseErrorActionPreference=$false
    & $taskPython -I -S -B (Join-Path $taskHere 'validate_results.py') 1>(Join-Path $taskHere 'validate-stdout01.log') 2>(Join-Path $taskHere 'validate-stderr01.log')
    $taskNative=$global:LASTEXITCODE
    Save-NoticeReceipt 'validate-native-exit01.json' ([ordered]@{native_exit=$taskNative;executable=$taskPython;flags=@('-I','-S','-B')})
    if($taskNative -ne 0){throw "Pytest receipt validation failed: $taskNative"}
    $PSNativeCommandUseErrorActionPreference=$false
    & $taskPowerShell -NoLogo -NoProfile -NonInteractive -File (Join-Path $taskHere 'run_build_blocks.ps1') -RunPath (Join-Path $taskHere 'notice-blocks01') 1>(Join-Path $taskHere 'blocks-stdout01.log') 2>(Join-Path $taskHere 'blocks-stderr01.log')
    $taskNative=$global:LASTEXITCODE
    Save-NoticeReceipt 'blocks-native-exit01.json' ([ordered]@{native_exit=$taskNative;executable=$taskPowerShell;native_standin_execution=$false})
    if($taskNative -ne 0){throw "Inert build-block check failed: $taskNative"}
    $taskPythonResult=Get-Content -LiteralPath (Join-Path $taskHere 'pytest-validated01.json') -Raw | ConvertFrom-Json
    $taskBlockResult=Get-Content -LiteralPath (Join-Path $taskHere 'notice-blocks01\result.json') -Raw | ConvertFrom-Json
    if($taskPythonResult.counts.passed -ne 20 -or $taskPythonResult.counts.failed -ne 0 -or $taskPythonResult.counts.skipped -ne 0 -or
       $taskBlockResult.passed -ne 10 -or $taskBlockResult.failed -ne 0 -or $taskBlockResult.qualification_exit -ne 0 -or
       $taskBlockResult.inputs_unchanged -cne $true){throw 'Fixed qualification counts or final guards differ'}
    $taskExit=0
}catch{$taskFailure=$_.Exception.Message;$taskExit=1}
finally{
    try{Save-NoticeReceipt 'inputs-after01.json' ([ordered]@{files=@(Read-InputState);source_inputs_sha256=$taskInputsHash;admission_sha256=$taskAdmissionHash});$taskAfterValid=$true}
    catch{$taskAfterValid=$false;$taskExit=1;if($null -eq $taskFailure){$taskFailure=$_.Exception.Message}}
    foreach($name in $taskSavedEnv.Keys){[Environment]::SetEnvironmentVariable($name,$taskSavedEnv[$name],'Process')}
}
Save-NoticeReceipt 'LAUNCH-RESULT01.json' ([ordered]@{label='notice01';qualification_exit=$taskExit;elapsed_seconds=$taskClock.Elapsed.TotalSeconds;inputs_unchanged=$taskAfterValid;failure=$taskFailure;full_build_or_models_executed=$false;source_inputs_sha256=$taskInputsHash;admission_sha256=$taskAdmissionHash})
Get-Content -LiteralPath (Join-Path $taskHere 'LAUNCH-RESULT01.json') -Raw
exit $taskExit
