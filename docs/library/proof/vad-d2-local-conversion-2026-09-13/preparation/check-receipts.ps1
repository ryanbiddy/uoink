$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d2-activated-invocation01'
$taskExecution=Join-Path $taskRoot 'execution-d2-real-01'
$taskOuter=Join-Path $taskRoot 'outer-d2-real-01'
function Sha([byte[]]$Raw){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Raw)).ToLowerInvariant()}
function ReadJson([string]$Path){Get-Content -LiteralPath $Path -Raw|ConvertFrom-Json}
function Require($Condition,[string]$Why){if(-not $Condition){throw $Why}}
$taskChild=ReadJson (Join-Path $taskExecution 'stdout.json')
$taskChecked=ReadJson (Join-Path $taskExecution 'checked-result.json')
$taskChildExit=ReadJson (Join-Path $taskExecution 'actual-child-exit.json')
$taskOuterExit=ReadJson (Join-Path $taskOuter 'actual-exit.json')
$taskActual=ReadJson (Join-Path $PSScriptRoot 'ACTUAL-CONVERSION.json')
Require ($taskActual.exit_code -eq 0 -and $taskOuterExit.actual_outer_exit -eq 0 -and $taskChildExit.actual_child_exit -eq 0 -and $taskChildExit.timed_out -ceq $false -and $taskChild.actual_child_exit -eq 0 -and $taskChecked.actual_child_exit -eq 0) 'Actual exit mismatch'
Require (([IO.File]::ReadAllText((Join-Path $taskOuter 'raw-exit.txt'))) -ceq "0`n") 'Raw native exit mismatch'
foreach($taskPath in @((Join-Path $taskExecution 'stderr.log'),(Join-Path $taskOuter 'stderr.log'))){Require (([IO.File]::ReadAllBytes($taskPath)).Length -eq 0) 'Unexpected stderr'}
Require ($null -eq $taskChild.failure -and $taskChild.runtime_or_release_approved -ceq $false -and $taskChild.conversion_profile_active_at_exit -ceq $false -and $taskChild.adapter_owner_pin_unchanged -ceq $true) 'Final child scope mismatch'
foreach($name in @('valid','inputs_unchanged','metadata_wrappers_installed','conversion_call_wrapper_intact','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed')){Require ($taskChild.guard.$name -ceq $true) "Guard failed: $name"}
foreach($name in @('unexpected_events','heavy_preloaded','heavy_after','registry_denials')){Require ($taskChild.guard.$name.Count -eq 0) "Unexpected guard event: $name"}
Require ($taskChild.guard.active -ceq $false -and $taskChild.guard.registry_trap_count -eq 25 -and $taskChild.guard.artifact_opens -eq 1 -and $taskChild.guard.output_opens -eq 1 -and $taskChild.guard.invocations -eq 1) 'Invocation allowance counts differ'
Require ($taskChild.conversion_operation.file_conversion_calls -eq 1 -and $taskChild.conversion_operation.file_conversion_returns -eq 1) 'Conversion count mismatch'
foreach($name in @('guard_valid','inputs_unchanged','original_and_copied_authority_unchanged','output_identity_verified')){Require ($taskChecked.$name -ceq $true) "Parent check failed: $name"}
Require ($taskChecked.runtime_or_release_approved -ceq $false) 'Parent scope mismatch'
$taskReport=$taskChild.conversion_result
Require ((ConvertTo-Json -InputObject $taskReport -Depth 10 -Compress) -ceq (ConvertTo-Json -InputObject $taskChecked.conversion_result -Depth 10 -Compress)) 'Child/parent result mismatch'
Require ($taskReport.status -ceq 'conversion_bytes_produced_unqualified' -and $taskReport.tensor_entries -eq 54 -and $taskReport.selected_storages -eq 23 -and $taskReport.dense_data_bytes -eq 5891996 -and $taskReport.output_bytes -eq 5896708) 'Fixed conversion shape mismatch'
Require ($taskReport.output_sha256 -ceq '8c15e718b6d502e7e351761f6cfee1a6917450e03c9a4c5318bc0d41d3fdd8c4' -and $taskReport.input_sha256 -ceq '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea' -and $taskReport.input_bytes -eq 17719103) 'Recorded identity mismatch'
foreach($name in @('model_or_tensor_constructed','pickle_interpreted','model_compatibility_qualified','release_approved')){Require ($taskReport.$name -ceq $false) "Broader claim: $name"}
$taskAdmission=ReadJson (Join-Path $taskRoot 'ROOT-ADMISSION.json')
$taskDecision=ReadJson (Join-Path $taskRoot 'RYAN-D2-DECISION.json')
Require (@($taskAdmission.source_hashes.PSObject.Properties).Count -eq 11) 'Root membership mismatch'
foreach($p in $taskAdmission.source_hashes.PSObject.Properties){Require ((Sha ([IO.File]::ReadAllBytes((Join-Path $taskRoot $p.Name)))) -ceq $p.Value) "Root source changed: $($p.Name)"}
Require (@($taskChild.input_sha256.PSObject.Properties).Count -eq 11) 'Copied input membership mismatch'
foreach($p in $taskChild.input_sha256.PSObject.Properties){
  Require ((Sha ([IO.File]::ReadAllBytes((Join-Path $taskExecution $p.Name)))) -ceq $p.Value) "Copied source changed: $($p.Name)"
  Require ((Sha ([IO.File]::ReadAllBytes((Join-Path $taskRoot $p.Name)))) -ceq $p.Value) "Original/copy mismatch: $($p.Name)"
}
Require ($taskDecision.source_note_sha256 -ceq (Sha ([IO.File]::ReadAllBytes((Join-Path $taskRoot 'RYAN-D2-APPROVAL-SOURCE.json'))))) 'Approval transcript binding mismatch'
$taskCheck=[ordered]@{actual_tool_chunk=$taskActual.chunk_id;actual_tool_exit=0;parent_exit=0;child_exit=0;timed_out=$false;guards_valid=$true;registry_traps=25;artifact_opens=1;output_opens=1;conversion_calls=1;conversion_returns=1;original_root_sources_unchanged=11;copied_inputs_unchanged=11;owner_decision_sha256=$taskChild.owner_decision_sha256;root_admission_sha256=Sha ([IO.File]::ReadAllBytes((Join-Path $taskRoot 'ROOT-ADMISSION.json')));conversion_result=$taskReport;parent_opaque_output_identity_verified=$true;root_check_read_only_receipts_and_source=$true;root_check_artifact_or_output_access=$false;runtime_or_release_approved=$false}
$taskOutput=Join-Path $PSScriptRoot 'ROOT-CHECK.json'
$taskRaw=[Text.UTF8Encoding]::new($false).GetBytes(($taskCheck|ConvertTo-Json -Depth 10)+"`n")
$s=[IO.File]::Open($taskOutput,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$s.Write($taskRaw,0,$taskRaw.Length);$s.Flush($true)}finally{$s.Dispose()}
$taskCheck|ConvertTo-Json -Depth 10
