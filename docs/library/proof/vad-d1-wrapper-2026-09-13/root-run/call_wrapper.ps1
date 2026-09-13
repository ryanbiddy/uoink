param(
    [Parameter(Mandatory=$true)][string]$CaseRoot,
    [Parameter(Mandatory=$true)][ValidateSet('0','1','2','3')][string]$RequestedExit,
    [Parameter(Mandatory=$true)][ValidateSet('false','true')][string]$InheritedNativeErrors,
    [Parameter(Mandatory=$true)][ValidateSet('false','true')][string]$ThrowPostcheck,
    [Parameter(Mandatory=$true)][ValidateSet('original','repaired')][string]$WrapperKind
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'This qualification requires PowerShell 7'}
$taskCase=[IO.Path]::GetFullPath($CaseRoot)
$taskParent=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'cases'))
if([IO.Path]::GetDirectoryName($taskCase) -cne $taskParent -or [IO.Path]::GetFileName($taskCase) -cnotmatch '^(repaired-(false|true|postcheck)|original-true)-[0-3]$'){throw 'Only fixed generated case roots are admitted'}
$taskWrapper=Join-Path $taskCase 'run-root.ps1'
$taskInert=Join-Path $taskCase 'launch_d1.py'
$taskWrapperHash=if($WrapperKind -ceq 'repaired'){'11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63'}else{'75b8058874a0389ccdd02f63815b1430b543967e5ad232904bbb86b7a0073a23'}
if((Get-FileHash -LiteralPath $taskWrapper -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskWrapperHash){throw 'Wrapper fixture bytes differ'}
if((Get-FileHash -LiteralPath $taskInert -Algorithm SHA256).Hash.ToLowerInvariant() -cne '9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f'){throw 'Only the inert child is admitted; D1 source is forbidden'}
if(Test-Path -LiteralPath (Join-Path $taskCase 'outer-d1-real-01')){throw 'Fixture output already exists'}
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
$env:D1_WRAPPER_SYNTHETIC_SCOPE='uoink-d1-wrapper-fixture-v1'
$env:D1_WRAPPER_SYNTHETIC_EXIT=$RequestedExit
$PSNativeCommandUseErrorActionPreference=($InheritedNativeErrors -ceq 'true')
$taskInherited=$PSNativeCommandUseErrorActionPreference
if($ThrowPostcheck -ceq 'true'){
    function global:Get-Content {
        param([string]$LiteralPath)
        throw 'INTENTIONAL_D1_WRAPPER_POSTCHECK_FAILURE'
    }
}
$taskDisposition='not_started'
$taskFailureType=$null
$taskFailureMessage=$null
$taskProcessExit=90
$taskLastNativeExit=$null
try{
    & $taskWrapper
    $taskLastNativeExit=$LASTEXITCODE
    $taskDisposition='wrapper_returned'
    $taskProcessExit=[int]$taskLastNativeExit
}catch{
    $taskLastNativeExit=$LASTEXITCODE
    $taskDisposition='wrapper_threw'
    $taskFailureType=$_.Exception.GetType().FullName
    $taskFailureMessage=$_.Exception.Message
    $taskProcessExit=91
}
$taskReceipt=[ordered]@{
    scope='uoink-d1-wrapper-fixture-v1';wrapper_kind=$WrapperKind;requested_exit=[int]$RequestedExit
    inherited_native_errors=$taskInherited;throw_postcheck=($ThrowPostcheck -ceq 'true')
    disposition=$taskDisposition;last_native_exit=$taskLastNativeExit;caller_process_exit=$taskProcessExit
    exception_type=$taskFailureType;exception_message=$taskFailureMessage
    original_d1_source_executed=$false;inert_child_sha256='9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f'
}
$taskReceipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskCase 'caller-observation.json') -Encoding utf8
exit $taskProcessExit
