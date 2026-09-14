# Data-only independent copy. This script never invokes candidate code or grants admission.
$ErrorActionPreference='Stop'
$taskSource='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-owner-native-connection-proposal01'
$taskPreparation='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-owner-native-confirmation-preparation01'
$taskDestination='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-runtime-owner-native-confirmation01'
$taskInventoryHash='@@INVENTORY_SHA@@'
$taskAuthorPinsHash='43b1e2f210cf1766fa5a074aa29fe1950f361e420dbc3697efcafddbd5a1f02e'
if($PSCommandPath -cne (Join-Path $taskPreparation 'copy_confirmation.ps1')){throw 'Fixed copier path required'}
function Hash-Bytes([byte[]]$taskBytes) {
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
}
function Read-Pinned([string]$taskPath,[string]$taskHash,[long]$taskSize=-1) {
    $taskBytes=[IO.File]::ReadAllBytes($taskPath)
    if(($taskSize -ge 0 -and $taskBytes.Length -ne $taskSize) -or (Hash-Bytes $taskBytes) -cne $taskHash){throw ('Text input changed: '+$taskPath)}
    return ,$taskBytes
}
function Write-New([string]$taskPath,[byte[]]$taskBytes) {
    $taskStream=[IO.File]::Open($taskPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try{$taskStream.Write($taskBytes,0,$taskBytes.Length);$taskStream.Flush($true)}finally{$taskStream.Dispose()}
}
$taskUtf8=[Text.UTF8Encoding]::new($false,$true)
$taskSelfHash=Hash-Bytes ([IO.File]::ReadAllBytes($PSCommandPath))
$taskPlanPath=Join-Path $taskPreparation 'COPY-INVENTORY.json'
$taskPlan=$taskUtf8.GetString((Read-Pinned $taskPlanPath $taskInventoryHash))|ConvertFrom-Json
$taskPinsPath=Join-Path $taskSource 'PINS.json'
$taskAuthorPins=$taskUtf8.GetString((Read-Pinned $taskPinsPath $taskAuthorPinsHash))|ConvertFrom-Json
if($taskPlan.schema -cne 'runtime-owner-native-independent-copy-plan-v1' -or $taskPlan.source_root -cne $taskSource -or $taskPlan.preparation_root -cne $taskPreparation -or $taskPlan.destination_root -cne $taskDestination){throw 'Fixed plan roots refused'}
if($taskPlan.author_pins_sha256 -cne $taskAuthorPinsHash -or $taskPlan.file_count -ne 42 -or @($taskPlan.files).Count -ne 42 -or $taskPlan.case_count -ne 33){throw 'Fixed plan membership refused'}
if(Test-Path -LiteralPath $taskDestination){throw 'Independent destination must be absent; preserve any partial prior copy'}
$taskAuthorByName=@{}
foreach($taskPin in $taskAuthorPins.files){$taskAuthorByName[$taskPin.path]=$taskPin}
$taskCached=@{}
$taskAuthorChecks=@()
$taskSeen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$taskBytesTotal=[long]0
foreach($taskRow in $taskPlan.files){
    if($taskRow.path -notmatch '^[A-Za-z0-9_.-]+$' -or -not $taskSeen.Add($taskRow.path) -or $taskRow.path -ceq 'ROOT-ADMISSION.json'){throw 'Flat unique destination names required'}
    if($taskRow.mode -ceq 'exact'){
        $taskExpectedSource=Join-Path $taskSource $taskRow.path
        if($taskRow.sha256 -cne $taskRow.author_sha256 -or $taskRow.bytes -ne $taskRow.author_bytes){throw 'Exact-copy identity differs'}
    }elseif($taskRow.mode -ceq 'relocated_control' -and @('SOURCE-INPUTS.json','run_fake33_01.ps1','ROOT-ADMISSION.template.json') -ccontains $taskRow.path){
        $taskExpectedSource=Join-Path (Join-Path $taskPreparation 'proposed') $taskRow.path
    }elseif($taskRow.mode -ceq 'new_narrow_inventory' -and $taskRow.path -ceq 'PINS.json'){
        $taskExpectedSource=Join-Path (Join-Path $taskPreparation 'proposed') 'PINS.json'
    }else{throw 'Unreviewed copy mode'}
    if($taskRow.source -cne $taskExpectedSource){throw 'Fixed copy source refused'}
    if($taskRow.mode -cne 'new_narrow_inventory'){
        $taskPin=$taskAuthorByName[$taskRow.path]
        if($null -eq $taskPin -or $taskPin.sha256 -cne $taskRow.author_sha256 -or $taskPin.bytes -ne $taskRow.author_bytes){throw 'Original inventory mismatch'}
        $taskOriginalPath=Join-Path $taskSource $taskRow.path
        $null=Read-Pinned $taskOriginalPath $taskRow.author_sha256 $taskRow.author_bytes
        $taskAuthorChecks += [ordered]@{path=$taskOriginalPath;bytes=$taskRow.author_bytes;sha256=$taskRow.author_sha256}
    }
    $taskCached[$taskRow.path]=Read-Pinned $taskRow.source $taskRow.sha256 $taskRow.bytes
    $taskBytesTotal += [long]$taskRow.bytes
}
if($taskBytesTotal -ne 569125 -or $taskBytesTotal -ne $taskPlan.total_bytes){throw 'Fixed copy byte total refused'}
$taskTemplate=$taskUtf8.GetString($taskCached['ROOT-ADMISSION.template.json'])|ConvertFrom-Json
if($taskTemplate.root_reviewed -isnot [bool] -or $taskTemplate.root_reviewed -cne $false -or $taskTemplate.label -cne 'owner-native-fake01' -or $taskTemplate.scope -cne 'runtime-owner-native-fake-33-only'){throw 'Dormant template required'}
$taskExpected=$taskUtf8.GetString($taskCached['EXPECTED-CASES.json'])|ConvertFrom-Json
if(@($taskExpected.ordered_cases).Count -ne 33 -or @($taskTemplate.expected_cases).Count -ne 33){throw 'Case membership refused'}
for($taskIndex=0;$taskIndex -lt 33;$taskIndex++){if($taskTemplate.expected_cases[$taskIndex] -cne $taskExpected.ordered_cases[$taskIndex]){throw 'Case order changed'}}
foreach($taskProperty in $taskTemplate.input_sha256.PSObject.Properties){
    if(-not $taskCached.ContainsKey($taskProperty.Name) -or (Hash-Bytes $taskCached[$taskProperty.Name]) -cne $taskProperty.Value){throw 'Dormant control pin differs'}
}
if(@($taskTemplate.input_sha256.PSObject.Properties).Count -ne 38){throw 'Dormant input count differs'}
# No candidate, runtime, support path or run directory is accessed below.
New-Item -ItemType Directory -Path $taskDestination -ErrorAction Stop | Out-Null
foreach($taskRow in $taskPlan.files){Write-New (Join-Path $taskDestination $taskRow.path) $taskCached[$taskRow.path]}
$taskResults=@()
foreach($taskRow in $taskPlan.files){
    $null=Read-Pinned $taskRow.source $taskRow.sha256 $taskRow.bytes
    $null=Read-Pinned (Join-Path $taskDestination $taskRow.path) $taskRow.sha256 $taskRow.bytes
    $taskResults += [ordered]@{path=$taskRow.path;mode=$taskRow.mode;author_sha256=$taskRow.author_sha256;source_after_sha256=$taskRow.sha256;copy_after_sha256=$taskRow.sha256;bytes=$taskRow.bytes}
}
foreach($taskRow in $taskAuthorChecks){$null=Read-Pinned $taskRow.path $taskRow.sha256 $taskRow.bytes}
$null=Read-Pinned $taskPinsPath $taskAuthorPinsHash
$null=Read-Pinned $taskPlanPath $taskInventoryHash
$null=Read-Pinned $PSCommandPath $taskSelfHash
$taskReceipt=[ordered]@{schema='runtime-owner-native-independent-copy-result-v1';destination=$taskDestination;copied_files=42;copied_bytes=$taskBytesTotal;source_pins_sha256=$taskAuthorPinsHash;copy_plan_sha256=$taskInventoryHash;copier_sha256=$taskSelfHash;original_selected_sources_unchanged=$true;all_copies_verified=$true;subject_executed=$false;admission_issued=$false;run_directory_created=$false;files=$taskResults}
Write-New (Join-Path $taskDestination 'COPY-BINDINGS.json') $taskUtf8.GetBytes(($taskReceipt|ConvertTo-Json -Depth 6)+"`n")
[ordered]@{copied_files=42;copied_bytes=$taskBytesTotal;destination=$taskDestination;subject_executed=$false;admission_issued=$false}|ConvertTo-Json
