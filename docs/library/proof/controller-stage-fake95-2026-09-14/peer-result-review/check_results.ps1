$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskScratch=Join-Path $taskRoot '_scratch'
function Assert-Result([bool]$condition,[string]$message){if(-not $condition){throw $message}}
function Binding([string]$file){
 $taskItem=Get-Item -LiteralPath $file
 Assert-Result (-not $taskItem.PSIsContainer -and -not ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Plain retained text required'
 return [ordered]@{bytes=$taskItem.Length;sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Read-Json([string]$file,[int]$limit=1048576){
 $taskB=Binding $file
 Assert-Result ($taskB.bytes -le $limit) ('Bounded JSON required: '+$file)
 return ([IO.File]::ReadAllText($file)|ConvertFrom-Json)
}
function Equal-Json($a,$b){return (($a|ConvertTo-Json -Depth 64 -Compress) -ceq ($b|ConvertTo-Json -Depth 64 -Compress))}
function Names($object){return @($object.PSObject.Properties.Name|Sort-Object)}
function Same-Names($a,$b){return ((@($a|Sort-Object) -join '|') -ceq (@($b|Sort-Object) -join '|'))}
function Check-Binding($actual,$expected,[string]$where){Assert-Result ($actual.bytes -eq $expected.bytes -and $actual.sha256 -ceq $expected.sha256) ('Binding mismatch: '+$where)}
$taskRoles=@(
 [ordered]@{role='author';source='controller-stage-fake95-author01';label='controller-stage-fake01';pins='b831bf6c864d8a7bef24355e5868dfa7480e6bba6ff1381cbc3ac9db07388606';actual='CONTROLLER95-AUTHOR-RUN-ACTUAL.json'},
 [ordered]@{role='confirmation';source='controller-stage-fake95-confirmation01';label='controller-stage-confirmation01';pins='6fdc1188f323541aaff93a3fb5205f54e395b13d5b20ebf8a95bd69420e864cb';actual='CONTROLLER95-CONFIRMATION-RUN-ACTUAL.json'}
)
$taskGuardNames=@('startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','real_entrypoints_unchanged')
$taskRuntimeNames=@('plan.json','stdout.json','stderr.log','native-exit.json','input-check.json','exit.json')
$taskSummaries=@();$taskFullCases=@();$taskChildHashPairs=@()
foreach($taskRole in $taskRoles){
 $taskSource=Join-Path $taskScratch $taskRole.source
 $taskRun=Join-Path $taskSource $taskRole.label
 $taskActualPath=Join-Path $taskScratch $taskRole.actual
 $taskActual=Read-Json $taskActualPath
 Assert-Result ($taskActual.exit_code -eq 0 -and $taskActual.output.Contains($taskRole.label+': 95 passed, 0 failed, 0 skipped;')) 'Retained outer tool exit/label mismatch'
 $taskPinsPath=Join-Path $taskSource 'PINS.json'
 Assert-Result ((Binding $taskPinsPath).sha256 -ceq $taskRole.pins) 'Frozen root-copy PINS mismatch'
 $taskPins=Read-Json $taskPinsPath
 Assert-Result ($taskPins.count -eq 29 -and @($taskPins.files).Count -eq 29 -and @($taskPins.files.path|Sort-Object -Unique).Count -eq 29) 'Exact29 parent pins'
 $taskMap=Read-Json (Join-Path $taskSource 'SOURCE-INPUTS.json')
 Assert-Result ($taskMap.module_count -eq 23 -and @($taskMap.modules).Count -eq 23 -and $taskMap.child_count -eq 25 -and @($taskMap.child_inputs).Count -eq 25) 'Exact23/25 source closure'
 $taskNames=@($taskPins.files.path)+@('PINS.json','ROOT-ADMISSION.json')+$taskRuntimeNames
 $taskItems=@(Get-ChildItem -LiteralPath $taskRun)
 Assert-Result ($taskItems.Count -eq 37 -and (Same-Names $taskItems.Name $taskNames)) 'Exact37 success-run files'
 foreach($taskItem in $taskItems){Assert-Result (-not $taskItem.PSIsContainer -and -not ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'No directory/link in fake result set'}
 foreach($taskPin in $taskPins.files){
  Assert-Result ($taskPin.path -cmatch '^[A-Za-z0-9_.-]+$') 'Flat known input name required'
  Check-Binding (Binding (Join-Path $taskSource $taskPin.path)) $taskPin ('source/'+$taskPin.path)
  Check-Binding (Binding (Join-Path $taskRun $taskPin.path)) $taskPin ('copy/'+$taskPin.path)
 }
 Check-Binding (Binding (Join-Path $taskRun 'PINS.json')) (Binding $taskPinsPath) 'copied PINS'
 $taskAdmissionPath=Join-Path $taskSource 'ROOT-ADMISSION.json'
 $taskAdmission=Read-Json $taskAdmissionPath
 Assert-Result ($taskAdmission.approved -ceq $true -and $taskAdmission.label -ceq $taskRole.label -and $taskAdmission.pins_sha256 -ceq $taskRole.pins -and $taskAdmission.scope -ceq 'generated_bytes_and_fake_ports_only') 'Actual admission mismatch'
 Check-Binding (Binding (Join-Path $taskRun 'ROOT-ADMISSION.json')) (Binding $taskAdmissionPath) 'copied admission'
 $taskPlan=Read-Json (Join-Path $taskRun 'plan.json')
 Assert-Result ($taskPlan.label -ceq $taskRole.label -and $taskPlan.python -ceq 'C:\Python314\python.exe' -and $taskPlan.startup_binding_set -ceq $true -and $taskPlan.scope -ceq 'generated_bytes_and_fake_ports_only') 'Launch plan identity mismatch'
 $taskArguments=@('-I','-S','-B',(Join-Path $taskRun 'qualify_windows_reservations.py'))
 Assert-Result (Equal-Json @($taskPlan.arguments) $taskArguments) 'Actual fixed invocation plan mismatch'
 Assert-Result (@($taskPlan.before).Count -eq 29 -and (Same-Names $taskPlan.before.name $taskPins.files.path)) 'Before29 membership mismatch'
 $taskCheck=Read-Json (Join-Path $taskRun 'input-check.json')
 Assert-Result ($taskCheck.inputs_unchanged -ceq $true -and @($taskCheck.inputs).Count -eq 29 -and (Same-Names $taskCheck.inputs.name $taskPins.files.path)) 'After29 membership mismatch'
 foreach($taskPin in $taskPins.files){
  $taskBefore=@($taskPlan.before|Where-Object {$_.name -ceq $taskPin.path})
  $taskAfter=@($taskCheck.inputs|Where-Object {$_.name -ceq $taskPin.path})
  Assert-Result ($taskBefore.Count -eq 1 -and $taskAfter.Count -eq 1 -and $taskAfter[0].unchanged -ceq $true) 'Unique before/after input'
  Check-Binding $taskBefore[0] $taskPin ('before/'+$taskPin.path)
  Check-Binding $taskAfter[0].original $taskPin ('after-original/'+$taskPin.path)
  Check-Binding $taskAfter[0].copy $taskPin ('after-copy/'+$taskPin.path)
 }
 $taskControlNames=@('PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1')
 Assert-Result (@($taskPlan.controls).Count -eq 3 -and @($taskCheck.controls).Count -eq 3 -and (Same-Names $taskPlan.controls.name $taskControlNames) -and (Same-Names $taskCheck.controls.name $taskControlNames)) 'Exact3 control memberships'
 foreach($taskControlName in $taskControlNames){
  $taskBound=Binding (Join-Path $taskSource $taskControlName)
  $taskBefore=@($taskPlan.controls|Where-Object {$_.name -ceq $taskControlName})
  $taskAfter=@($taskCheck.controls|Where-Object {$_.name -ceq $taskControlName})
  Assert-Result ($taskBefore.Count -eq 1 -and $taskAfter.Count -eq 1 -and $taskAfter[0].unchanged -ceq $true) 'Unique control before/after'
  Check-Binding $taskBefore[0].binding $taskBound ('control-before/'+$taskControlName)
  Check-Binding $taskAfter[0].original $taskBound ('control-original/'+$taskControlName)
  Check-Binding $taskAfter[0].copy $taskBound ('control-copy/'+$taskControlName)
  Check-Binding (Binding (Join-Path $taskRun $taskControlName)) $taskBound ('control-current-copy/'+$taskControlName)
 }
 $taskResult=Read-Json (Join-Path $taskRun 'stdout.json') 262144
 $taskExit=Read-Json (Join-Path $taskRun 'exit.json')
 $taskNative=Read-Json (Join-Path $taskRun 'native-exit.json')
 $taskStderr=Binding (Join-Path $taskRun 'stderr.log')
 $taskStdout=Binding (Join-Path $taskRun 'stdout.json')
 Assert-Result ($taskStderr.bytes -eq 0) 'Stderr not empty'
 Assert-Result ($taskNative.native_exit -eq 0 -and $taskExit.native_exit -eq 0 -and $taskExit.qualification_exit -eq 0 -and $taskResult.qualification_exit -eq 0) 'Recorded Python/qualification exits not zero'
 foreach($taskName in @('valid','inputs_unchanged','membership_valid','guards_valid')){Assert-Result ($taskExit.$taskName -ceq $true) ('Outer receipt flag: '+$taskName)}
 Assert-Result ($taskExit.passed -eq 95 -and $taskExit.failed -eq 0 -and $taskExit.skipped -eq 0 -and $taskExit.stdout_bytes -eq $taskStdout.bytes -and $taskExit.stderr_bytes -eq 0) 'Exit count/byte mismatch'
 Assert-Result ($taskResult.schema -ceq 'uoink.windows-reservation-fake-preflight.v1' -and $taskResult.count -eq 95 -and $taskResult.passed -eq 95 -and $taskResult.failed -eq 0 -and $taskResult.skipped -eq 0 -and $taskResult.membership_valid -ceq $true -and $taskResult.guard_valid -ceq $true) 'Result schema/count/status mismatch'
 Assert-Result ((Same-Names (Names $taskResult.guards) $taskGuardNames) -and @($taskResult.guards.PSObject.Properties).Count -eq 10) 'Exact10 guard names required'
 foreach($taskName in $taskGuardNames){Assert-Result ($taskResult.guards.$taskName -ceq $true) ('Reported guard failed: '+$taskName)}
 Assert-Result ($taskResult.metadata_trap_count -eq 12 -and $taskResult.registry_trap_count -eq 25 -and @($taskResult.guard_denials).Count -eq 0 -and @($taskResult.registry_denials).Count -eq 0 -and @($taskResult.heavy_roots_loaded).Count -eq 0) 'Trap/denial/heavy mismatch'
 $taskExpected=@(Read-Json (Join-Path $taskRun 'EXPECTED-CASES.json'))
 Assert-Result ($taskExpected.Count -eq 95 -and @($taskResult.cases).Count -eq 95 -and (Equal-Json @($taskResult.expected_cases) $taskExpected)) 'Expected95 mismatch'
 $taskSubtests=0
 for($taskIndex=0;$taskIndex -lt 95;$taskIndex++){
  $taskCase=$taskResult.cases[$taskIndex]
  Assert-Result ((Same-Names (Names $taskCase) @('id','passed','skipped','errors','subtests')) -and $taskCase.id -ceq $taskExpected[$taskIndex] -and $taskCase.passed -ceq $true -and $taskCase.skipped -ceq $false -and @($taskCase.errors).Count -eq 0 -and @($taskCase.subtests).Count -le 64) ('Full case mismatch: '+$taskIndex)
  foreach($taskSub in $taskCase.subtests){
   Assert-Result ((Same-Names (Names $taskSub) @('id','passed')) -and $taskSub.id -is [string] -and $taskSub.id.Length -le 512 -and $taskSub.passed -ceq $true) ('Full subtest mismatch: '+$taskCase.id)
   $taskSubtests++
  }
 }
 Assert-Result ($taskSubtests -eq 95) 'Root-reported95 subtests differ'
 Assert-Result (@($taskResult.input_sha256.PSObject.Properties).Count -eq 25 -and (Same-Names (Names $taskResult.input_sha256) $taskMap.child_inputs.name)) 'Exact25 child hashes required'
 $taskChildRows=@()
 foreach($taskChild in $taskMap.child_inputs){
  Assert-Result ($taskResult.input_sha256.($taskChild.name) -ceq $taskChild.sha256) ('Result child hash mismatch: '+$taskChild.name)
  $taskPinned=@($taskPins.files|Where-Object {$_.path -ceq $taskChild.name})
  Assert-Result ($taskPinned.Count -eq 1) 'Unique child pin'
  Check-Binding $taskPinned[0] $taskChild ('child-map/'+$taskChild.name)
  $taskChildRows += [ordered]@{name=$taskChild.name;sha256=$taskChild.sha256}
 }
 $taskFullCases += ,($taskResult.cases|ConvertTo-Json -Depth 64 -Compress)
 $taskChildHashPairs += ,($taskChildRows|ConvertTo-Json -Depth 8 -Compress)
 $taskSummaries += [ordered]@{role=$taskRole.role;actual=$taskRole.actual;actual_binding=(Binding $taskActualPath);tool_chunk=$taskActual.chunk_id;outer_exit=$taskActual.exit_code;python_exit=$taskNative.native_exit;passed=95;failed=0;skipped=0;passing_subtests=$taskSubtests;guard_count=10;metadata_traps=12;registry_traps=25;parent_pairs=29;control_pairs=3;child_hashes=25;output_files=37;stdout=$taskStdout;stderr=$taskStderr;recorded_case_seconds=$taskResult.elapsed_seconds;pins_sha256=$taskRole.pins}
}
Assert-Result ($taskFullCases.Count -eq 2 -and $taskFullCases[0] -ceq $taskFullCases[1]) 'Complete case/subtest arrays differ between roots'
Assert-Result ($taskChildHashPairs[0] -ceq $taskChildHashPairs[1]) 'Complete child hash sets differ'
[ordered]@{scope='PASSIVE saved-text result check only; no subject rerun';reviewer_role='Instrument author; root independently reviews outcomes';source_checkpoint='851bcdd';instrument_peer_verdict='66b1654cba5576ad0d09680913713eaaee88d32cc55d4ab7ff69a171b90d63aa';complete_cases_and_subtests_identical=$true;child_hash_sets_identical=$true;results=$taskSummaries;native_worker_or_model_acceptance=$false}|ConvertTo-Json -Depth 12
