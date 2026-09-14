param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$FinalMapSha256)
$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskOld=Join-Path $taskBase 'windows-interrupted-owner-native-proposal01'
$taskNew=Join-Path $taskBase 'windows-interrupted-owner-native-proposal02'
function Task-Sha([string]$path){return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Task-Require([bool]$condition,[string]$message){if(-not $condition){throw $message}}
function Task-Json([string]$path){return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable)}
function Task-Bytes([string]$path){return ,([IO.File]::ReadAllBytes($path))}
function Task-HashBytes([byte[]]$bytes){return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
$taskMapPath=Join-Path $taskNew 'SOURCE-INPUTS.json'
Task-Require ((Task-Sha $taskMapPath) -ceq $FinalMapSha256) 'Exact final map'
$taskA=Task-Json (Join-Path $taskOld 'SOURCE-INPUTS.json');$taskB=Task-Json $taskMapPath
Task-Require ($taskA.source_sha256.Count -eq 29 -and $taskB.source_sha256.Count -eq 29 -and $taskA.source_paths.Count -eq 29 -and $taskB.source_paths.Count -eq 29) '29 source rows'
Task-Require ((($taskA.source_sha256.Keys | Sort-Object) -join '|') -ceq (($taskB.source_sha256.Keys | Sort-Object) -join '|')) 'Exact source names'
$taskRows=@();$taskChanged=@()
foreach($taskName in $taskA.source_sha256.Keys){
    Task-Require ($taskName -cmatch '^[a-z0-9_]+\.py$') 'Plain source filename'
    $taskAp=Join-Path $taskOld $taskName;$taskBp=Join-Path $taskNew $taskName
    Task-Require ($taskA.source_paths[$taskName] -ceq $taskAp -and $taskB.source_paths[$taskName] -ceq $taskBp) 'Fixed source paths'
    $taskAh=Task-Sha $taskAp;$taskBh=Task-Sha $taskBp
    Task-Require ($taskAh -ceq $taskA.source_sha256[$taskName] -and $taskBh -ceq $taskB.source_sha256[$taskName]) 'Actual source hash'
    if($taskAh -cne $taskBh){$taskChanged+=$taskName}
    $taskRows += [ordered]@{name=$taskName;old_sha256=$taskAh;new_sha256=$taskBh;new_bytes=(Get-Item -LiteralPath $taskBp).Length;unchanged=($taskAh -ceq $taskBh)}
}
Task-Require ((($taskChanged | Sort-Object) -join '|') -ceq 'dummy_bootstrap.py|generated_adapter_flow.py') 'Only qualified adapter and bootstrap changed'
Task-Require ($taskB.source_sha256['generated_adapter_flow.py'] -ceq '24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961') 'Qualified adapter'
Task-Require ((Task-Sha (Join-Path $taskBase 'interrupted-owner-prelock-repair03\generated_adapter_flow.py')) -ceq $taskB.source_sha256['generated_adapter_flow.py']) 'Exact qualified source match'
$taskUtf8=[Text.UTF8Encoding]::new($false)
$taskOldBootstrap=Task-Bytes (Join-Path $taskOld 'dummy_bootstrap.py');$taskNewBootstrap=Task-Bytes (Join-Path $taskNew 'dummy_bootstrap.py')
$taskExpectedBootstrap=$taskUtf8.GetBytes($taskUtf8.GetString($taskOldBootstrap).Replace('windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02'))
Task-Require ((Task-HashBytes $taskExpectedBootstrap) -ceq (Task-HashBytes $taskNewBootstrap)) 'Bootstrap run-label-only full bytes'
$taskOldLauncher=Task-Bytes (Join-Path $taskOld 'run_interrupted_owner01.ps1');$taskNewLauncher=Task-Bytes (Join-Path $taskNew 'run_interrupted_owner02.ps1')
$taskOldText=$taskUtf8.GetString($taskOldLauncher)
$taskNewText=$taskUtf8.GetString($taskNewLauncher)
$taskForward=$taskOldText.Replace('windows-interrupted-owner-native-proposal01','windows-interrupted-owner-native-proposal02').Replace('windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02').Replace('run_interrupted_owner01.ps1','run_interrupted_owner02.ps1')
$taskReverse=$taskNewText.Replace('windows-interrupted-owner-native-proposal02','windows-interrupted-owner-native-proposal01').Replace('windows-interrupted-owner-retirement02','windows-interrupted-owner-retirement01').Replace('run_interrupted_owner02.ps1','run_interrupted_owner01.ps1')
Task-Require ((Task-HashBytes ($taskUtf8.GetBytes($taskForward))) -ceq (Task-HashBytes $taskNewLauncher) -and (Task-HashBytes ($taskUtf8.GetBytes($taskReverse))) -ceq (Task-HashBytes $taskOldLauncher)) 'Full launcher forward/inverse byte equality'
$taskOldAdapter=$taskUtf8.GetString((Task-Bytes (Join-Path $taskOld 'generated_adapter_flow.py')))
$taskNewAdapter=$taskUtf8.GetString((Task-Bytes (Join-Path $taskNew 'generated_adapter_flow.py')))
$taskInsertion="                for path, expected in port.expectations:`n                    port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, True))`n"
$taskFunctionOffset=$taskNewAdapter.IndexOf('def controller_interrupted_recovery_flow(', [StringComparison]::Ordinal)
Task-Require ($taskFunctionOffset -ge 0) 'Actual interrupted controller function'
$taskInsertionOffset=$taskNewAdapter.IndexOf($taskInsertion,$taskFunctionOffset,[StringComparison]::Ordinal)
Task-Require ($taskInsertionOffset -ge 0 -and $taskNewAdapter.Remove($taskInsertionOffset,$taskInsertion.Length) -ceq $taskOldAdapter) 'Only qualified two-line adapter insertion'
Task-Require ($taskA.native_bindings.Count -eq 9 -and $taskB.native_bindings.Count -eq 9 -and (($taskA.native_bindings.Keys | Sort-Object) -join '|') -ceq (($taskB.native_bindings.Keys | Sort-Object) -join '|')) 'Exact nine support metadata names'
foreach($taskName in $taskA.native_bindings.Keys){
    $taskAr=$taskA.native_bindings[$taskName];$taskBr=$taskB.native_bindings[$taskName]
    Task-Require ($taskAr.bytes -eq $taskBr.bytes -and $taskAr.sha256 -ceq $taskBr.sha256) 'Support metadata values unchanged'
}
$taskTemplate=Task-Json (Join-Path $taskNew 'ROOT-ADMISSION-TEMPLATE.json')
Task-Require ($taskTemplate.root_reviewed -ceq $false -and $taskTemplate.scope -ceq 'generated-windows-interrupted-owner-retirement-only' -and $taskTemplate.case -ceq 'positive' -and $taskTemplate.operation_mode -ceq 'drain') 'Dormant exact-scope template'
Task-Require ($taskTemplate.run_path -ceq (Join-Path $taskBase 'windows-interrupted-owner-retirement02') -and $taskTemplate.source_inputs_sha256 -ceq $FinalMapSha256 -and $taskTemplate.launcher_sha256 -ceq (Task-HashBytes $taskNewLauncher)) 'Template bindings'
[ordered]@{scope='Passive source and recorded metadata only';pass=$true;source_rows=29;unchanged_sources=27;qualified_adapter_exact=$true;bootstrap_fixed_label_only=$true;launcher_full_forward_inverse_byte_equality=$true;all_receipt_predicates_and_native_exit_block_unchanged=$true;adapter_two_line_insertion_only=$true;support_metadata_rows=9;support_metadata_unchanged=$true;no_support_paths_opened=$true;false_template=$true;source_inputs_sha256=$FinalMapSha256;launcher_sha256=(Task-HashBytes $taskNewLauncher);rows=$taskRows} | ConvertTo-Json -Depth 8
