param([Parameter(Mandatory=$true)][string]$RunPath)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$taskHere=$PSScriptRoot
$taskAllowedRun=Join-Path $taskHere 'notice-blocks01'
if([IO.Path]::GetFullPath($RunPath) -cne [IO.Path]::GetFullPath($taskAllowedRun)){throw 'Only the fixed fresh notice-blocks01 path is allowed'}
if(Test-Path -LiteralPath $RunPath){throw 'Fresh notice-block outcome path required'}
if($env:IG_FORBIDDEN_LIVE -cne 'C:\Users\hello\AppData\Local\Uoink\index.db'){throw 'Forbidden-live startup binding missing'}
$taskInputs=Get-Content -LiteralPath (Join-Path $taskHere 'SOURCE-INPUTS.json') -Raw | ConvertFrom-Json
foreach($taskInput in $taskInputs.files){
    $taskPath=Join-Path $taskHere $taskInput.path
    if((Get-Item -LiteralPath $taskPath).Length -ne $taskInput.bytes -or
        (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInput.sha256){throw 'Pinned qualification input differs'}
}
$taskBuildPath=Join-Path $taskHere 'overlay\build.ps1'
if((Get-FileHash -LiteralPath $taskBuildPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne '88cf746727876ad2fa0b822b210738b886fb0fac966d4d882f9d049ee360a368'){throw 'Exact proposed build source differs'}
$taskBuild=[IO.File]::ReadAllText($taskBuildPath,[Text.UTF8Encoding]::new($false,$true))
$taskBoundBlocks=Get-Content -LiteralPath (Join-Path $taskHere 'BLOCK-BINDINGS.json') -Raw | ConvertFrom-Json
$taskBlocks=@{}
foreach($taskBound in $taskBoundBlocks.blocks){
    $taskRaw=[IO.File]::ReadAllBytes((Join-Path $taskHere $taskBound.path))
    $taskText=[Text.UTF8Encoding]::new($false,$true).GetString($taskRaw)
    if($taskBuild.Substring($taskBound.start,$taskBound.characters) -cne $taskText -or
        $taskRaw.Length -ne $taskBound.bytes -or
        [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskRaw)).ToLowerInvariant() -cne $taskBound.sha256){throw 'Exact source block differs'}
    $taskTokens=$null;$taskErrors=$null
    $taskAst=[Management.Automation.Language.Parser]::ParseInput($taskText,[ref]$taskTokens,[ref]$taskErrors)
    if($taskErrors.Count -ne 0 -or $null -ne $taskAst.ParamBlock){throw 'Changed block parse refused'}
    $taskBlocks[$taskBound.name]=[scriptblock]::Create($taskText)
}
if($taskBlocks.Count -ne 2 -or -not $taskBlocks.ContainsKey('generation') -or -not $taskBlocks.ContainsKey('staging')){throw 'Fixed block membership differs'}
New-Item -ItemType Directory -Path $RunPath -ErrorAction Stop | Out-Null
$script:Results=[Collections.Generic.List[object]]::new()
$taskClock=[Diagnostics.Stopwatch]::StartNew()

function Assert-Notice($condition,[string]$message){if(-not $condition){throw $message}}
function Write-Text([string]$path,[string]$text){[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))}
function Write-Step { $script:Steps.Add([string]$args[0]) }
function Get-PackageTimestampUtc { return [DateTime]::SpecifyKind([datetime]'2000-01-01',[DateTimeKind]::Utc) }
function Invoke-NoticeStandIn {
    $actual=@($args | ForEach-Object {[string]$_})
    $i=$script:Calls.Count
    Assert-Notice ($i -lt 3) 'Unexpected stand-in invocation'
    $expected=$script:ExpectedArguments[$i]
    Assert-Notice ($actual.Count -eq $expected.Count) 'Stand-in argument count differs'
    for($j=0;$j -lt $actual.Count;$j++){Assert-Notice ($actual[$j] -ceq $expected[$j]) 'Stand-in argument differs'}
    $script:Calls.Add([ordered]@{operation=@('tool_install','generator','cleanup')[$i];arguments=$actual;native_execution=$false})
    if($i -eq 1 -and $script:ThrowGenerator){throw 'fixed_generator_exception'}
    $global:LASTEXITCODE=[int]$script:FakeExits[$i]
    if($i -eq 1 -and $global:LASTEXITCODE -eq 0){Write-Text $script:ExpectedOutput "Fresh generated index fixture.`n"}
}
$taskStandInIdentity=(Get-Command Invoke-NoticeStandIn -CommandType Function).ScriptBlock

function Record-Case([string]$name,[scriptblock]$body){
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $status='passed';$errorType=$null;$errorText=$null;$facts=$null
    try{$facts=& $body}catch{$status='failed';$errorType=$_.Exception.GetType().FullName;$errorText=$_.Exception.Message.Substring(0,[Math]::Min(500,$_.Exception.Message.Length))}
    $script:Results.Add([ordered]@{id=$name;outcome=$status;seconds=$clock.Elapsed.TotalSeconds;error_type=$errorType;error=$errorText;facts=$facts})
    $script:Results | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $RunPath 'cases.json') -Encoding utf8
}

function Generation-Case([string]$name,[int[]]$exits,[bool]$throws,[bool]$epochPresent,[bool]$nativePreference,[string]$expectedError){
    $caseRoot=Join-Path $RunPath $name
    New-Item -ItemType Directory -Path $caseRoot | Out-Null
    $RepoRoot=$caseRoot
    $InstallerLock=Join-Path $caseRoot 'requirements-installer-lock.txt'
    $embedPython='Invoke-NoticeStandIn'
    $script:ExpectedOutput=Join-Path $caseRoot 'THIRD-PARTY-NOTICES.md'
    Write-Text $script:ExpectedOutput "Old source index fixture.`n"
    $script:ExpectedArguments=@(
        @('-m','pip','install','--no-warn-script-location','--no-compile','--no-cache-dir','--no-build-isolation','--constraint',$InstallerLock,'pip-licenses==5.0.0'),
        @((Join-Path $caseRoot 'scripts\gen_third_party_notices.py'),$script:ExpectedOutput),
        @('-m','pip','uninstall','-y','pip-licenses','prettytable','tomli','wcwidth'))
    $script:Calls=[Collections.Generic.List[object]]::new();$script:Steps=[Collections.Generic.List[string]]::new()
    $script:FakeExits=$exits;$script:ThrowGenerator=$throws
    $savedEpoch=$env:SOURCE_DATE_EPOCH
    $savedPreference=$PSNativeCommandUseErrorActionPreference
    $observedError=$null;$epochRestored=$false;$preferenceRestored=$false
    try{
        if($epochPresent){$env:SOURCE_DATE_EPOCH='123456789'}else{Remove-Item Env:SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue}
        $PSNativeCommandUseErrorActionPreference=$nativePreference
        try{. $taskBlocks.generation}catch{$observedError=$_.Exception.Message}
        $epochRestored=if($epochPresent){$env:SOURCE_DATE_EPOCH -ceq '123456789'}else{-not (Test-Path Env:SOURCE_DATE_EPOCH)}
        $preferenceRestored=$PSNativeCommandUseErrorActionPreference -ceq $nativePreference
        if($null -eq $expectedError){Assert-Notice ($null -eq $observedError) 'Unexpected generation error'}
        else{Assert-Notice ($null -ne $observedError -and $observedError.Contains($expectedError)) 'Expected generation refusal missing'}
        Assert-Notice ($epochRestored -and $preferenceRestored) 'Generation did not restore scoped state'
        Assert-Notice ((Get-Command Invoke-NoticeStandIn -CommandType Function).ScriptBlock -eq $taskStandInIdentity) 'Inert command binding changed'
        $expectedCalls=if($throws){2}else{3}
        Assert-Notice ($script:Calls.Count -eq $expectedCalls) 'Generation/cleanup call ordering differs'
        Assert-Notice ($script:Steps.Count -eq 1 -and $script:Steps[0] -ceq 'Generating THIRD-PARTY-NOTICES.md') 'Generation step did not run'
        $expectedText=if(-not $throws -and $exits[1] -eq 0){"Fresh generated index fixture.`n"}else{"Old source index fixture.`n"}
        Assert-Notice ([IO.File]::ReadAllText($script:ExpectedOutput) -ceq $expectedText) 'Generation output fixture differs'
        if(-not $throws){Assert-Notice ($noticeGenerationExit -eq $exits[1] -and $noticeCleanupExit -eq $exits[2]) 'Captured exits were overwritten by cleanup'}
        return [ordered]@{calls=@($script:Calls.ToArray());generator_exit=if($throws){$null}else{$noticeGenerationExit};cleanup_exit=if($throws){$null}else{$noticeCleanupExit};expected_error=$observedError;epoch_restored=$epochRestored;native_preference_restored=$preferenceRestored;native_execution=$false}
    }finally{$env:SOURCE_DATE_EPOCH=$savedEpoch;$PSNativeCommandUseErrorActionPreference=$savedPreference}
}

Record-Case 'generation_success_restores_state' { Generation-Case 'generation-success' @(0,0,0) $false $true $true $null }
Record-Case 'tool_install_failure_still_generates' { Generation-Case 'tool-install-failure' @(1,0,0) $false $true $false $null }
Record-Case 'generator_exit2_remains_fatal_after_cleanup0' { Generation-Case 'generator-exit2' @(0,2,0) $false $true $true 'generation failed (exit 2)' }
Record-Case 'cleanup_exit2_is_fatal' { Generation-Case 'cleanup-exit2' @(0,0,2) $false $true $true 'cleanup failed (exit 2)' }
Record-Case 'generator_exception_restores_state' { Generation-Case 'generator-exception' @(0,0,0) $true $true $true 'fixed_generator_exception' }
Record-Case 'absent_epoch_is_restored_absent' { Generation-Case 'absent-epoch' @(0,0,0) $false $false $true $null }

function Staging-Case([string]$name,[string]$fault){
    $caseRoot=Join-Path $RunPath $name
    $RepoRoot=Join-Path $caseRoot 'source';$StagingDir=Join-Path $caseRoot 'stage'
    New-Item -ItemType Directory -Path (Join-Path $RepoRoot 'third-party-notices'),$StagingDir -Force | Out-Null
    $InstallerLock=Join-Path $RepoRoot 'requirements-installer-lock.txt'
    Write-Text $InstallerLock "antlr4-python3-runtime==4.9.3`nproxy_tools==0.1.0`n"
    $relative=@('THIRD-PARTY-NOTICES.md','third-party-notices\README.md','third-party-notices\antlr4-python3-runtime-4.9.3-LICENSE.txt','third-party-notices\proxy-tools-0.1.0-UPSTREAM-LICENSE.txt')
    foreach($name in $relative){Copy-Item -LiteralPath (Join-Path (Join-Path $taskHere 'overlay') $name) -Destination (Join-Path $RepoRoot $name)}
    $faultFile=Join-Path $RepoRoot 'third-party-notices\proxy-tools-0.1.0-UPSTREAM-LICENSE.txt'
    if($fault -ceq 'missing'){Remove-Item -LiteralPath $faultFile}
    if($fault -ceq 'changed'){Write-Text $faultFile 'Changed notice fixture'}
    if($fault -ceq 'version'){Write-Text $InstallerLock "antlr4-python3-runtime==4.9.3`nproxy_tools==9.9.9`n"}
    $before=@(Get-ChildItem -LiteralPath $RepoRoot -Recurse -File | ForEach-Object {[ordered]@{path=$_.FullName;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}})
    $observedError=$null
    try{. $taskBlocks.staging}catch{$observedError=$_.Exception.Message}
    if($fault -ceq 'none'){
        Assert-Notice ($null -eq $observedError) 'Successful staging refused'
        $actual=@(Get-ChildItem -LiteralPath $StagingDir -Recurse -File | ForEach-Object {[IO.Path]::GetRelativePath($StagingDir,$_.FullName)})
        Assert-Notice ($actual.Count -eq 4 -and @(Compare-Object $relative $actual).Count -eq 0) 'Staged notice membership differs'
        foreach($name in $relative){Assert-Notice ((Get-FileHash -LiteralPath (Join-Path $RepoRoot $name)).Hash -ceq (Get-FileHash -LiteralPath (Join-Path $StagingDir $name)).Hash) 'Staged notice bytes differ'}
    }else{
        Assert-Notice ($null -ne $observedError) 'Expected staging refusal missing'
        if($fault -ceq 'changed'){Assert-Notice ($observedError.Contains('Upstream notice bytes differ')) 'Wrong changed-notice refusal'}
        if($fault -ceq 'version'){Assert-Notice ($observedError.Contains('Supplemental notice version requires review')) 'Wrong lock-version refusal'}
        Assert-Notice (@(Get-ChildItem -LiteralPath $StagingDir -Recurse -File).Count -eq 0) 'Refused staging still copied notices'
    }
    foreach($row in $before){Assert-Notice ((Get-FileHash -LiteralPath $row.path).Hash -ceq $row.sha256) 'Staging changed or deleted source text'}
    if($fault -ceq 'missing'){Assert-Notice (-not (Test-Path -LiteralPath $faultFile)) 'Missing source was fabricated'}
    return [ordered]@{fault=$fault;expected_error=$observedError;source_preserved=$true;staged_files=@(Get-ChildItem -LiteralPath $StagingDir -Recurse -File).Count}
}

Record-Case 'staging_copies_exact_four_notice_files' { Staging-Case 'staging-success' 'none' }
Record-Case 'staging_missing_notice_refuses_without_source_deletion' { Staging-Case 'staging-missing' 'missing' }
Record-Case 'staging_changed_notice_refuses_without_source_deletion' { Staging-Case 'staging-changed' 'changed' }
Record-Case 'staging_changed_lock_version_refuses' { Staging-Case 'staging-version' 'version' }

$taskUnchanged=$true
foreach($taskInput in $taskInputs.files){if((Get-FileHash -LiteralPath (Join-Path $taskHere $taskInput.path) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskInput.sha256){$taskUnchanged=$false}}
$taskFailures=@($script:Results | Where-Object {$_.outcome -cne 'passed'}).Count
$taskExit=if($taskFailures -or -not $taskUnchanged -or $script:Results.Count -ne 10){1}else{0}
[ordered]@{schema='uoink.notice-block-contracts.v1';cases=@($script:Results.ToArray());passed=10-$taskFailures;failed=$taskFailures;case_count=$script:Results.Count;elapsed_seconds=$taskClock.Elapsed.TotalSeconds;inputs_unchanged=$taskUnchanged;qualification_exit=$taskExit;blocks_executed=@('generation','staging');full_build_executed=$false;native_standin_execution=$false;model_or_installer_acceptance=$false} | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $RunPath 'result.json') -Encoding utf8
exit $taskExit
