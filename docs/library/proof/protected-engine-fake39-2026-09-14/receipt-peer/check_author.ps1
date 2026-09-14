$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskRepo '_scratch/protected-engine-ownership-fake39-author01'
$taskRun=Join-Path $taskSource 'runs/protected-engine-fake01'
function Text-Binding([string]$path){
 $item=Get-Item -LiteralPath $path
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576){throw 'Bounded plain text required'}
 [ordered]@{bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Read-Json([string]$path){$null=Text-Binding $path;Get-Content -LiteralPath $path -Raw|ConvertFrom-Json}
function Same($a,$b,[string]$why){if(($a|ConvertTo-Json -Depth 30 -Compress) -cne ($b|ConvertTo-Json -Depth 30 -Compress)){throw $why}}
$pinsPath=Join-Path $taskSource 'PINS.json'
$pinsBinding=Text-Binding $pinsPath
if($pinsBinding.sha256 -cne '7309394f50729101e23899ef1a947639e4abcb27d59910f3dd2446d98f3524ba'){throw 'Author PINS changed'}
$pins=Read-Json $pinsPath
if($pins.count -ne 40 -or @($pins.files).Count -ne 40){throw 'Parent pin count'}
$expected=Read-Json (Join-Path $taskSource 'EXPECTED-CASES.json')
$r=Read-Json (Join-Path $taskRun 'stdout.json')
$exit=Read-Json (Join-Path $taskRun 'exit.json')
$native=Read-Json (Join-Path $taskRun 'native-exit.json')
$plan=Read-Json (Join-Path $taskRun 'plan.json')
$after=Read-Json (Join-Path $taskRun 'after.json')
$admission=Read-Json (Join-Path $taskSource 'ROOT-ADMISSION.json')
$names=@($pins.files.path)
$expectedFiles=@($names+@('ROOT-ADMISSION.json','plan.json','stdout.json','stderr.log','after.json','exit.json','native-exit.json'))
$items=@(Get-ChildItem -LiteralPath $taskRun -Force)
if($items.Count -ne 47 -or @($items|Where-Object{$_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)}).Count -ne 0){throw '47 flat plain outputs required'}
Same @($items.Name|Sort-Object) @($expectedFiles|Sort-Object) 'Exact output membership'
foreach($item in $items){$null=Text-Binding $item.FullName}
if($r.schema -cne 'uoink.runtime-owner-native-fake.v1' -or $r.passed -ne 39 -or $r.failed -ne 0 -or $r.skipped -ne 0 -or $r.count -ne 39 -or @($r.cases).Count -ne 39){throw '39/0/0 required'}
Same @($r.cases.name) @($expected.ordered_cases) 'Ordered raw cases'
Same @($r.expected_cases) @($expected.ordered_cases) 'Expected IDs in result'
foreach($case in $r.cases){
 Same @($case.PSObject.Properties.Name|Sort-Object) @('name','passed') 'Case object shape'
 if($case.passed -isnot [bool] -or $case.passed -cne $true){throw 'Case did not pass'}
}
$guardNames=@('metadata_traps_installed','content_reads_closed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','methods_unchanged','closed_entries_unchanged','owner_binding_valid')
foreach($name in @($guardNames+'guard_valid')){if($r.$name -isnot [bool] -or $r.$name -cne $true){throw ('Guard refused '+$name)}}
$trapNames=@('CloseKey','ConnectRegistry','CreateKey','CreateKeyEx','DeleteKey','DeleteKeyEx','DeleteValue','DisableReflectionKey','EnableReflectionKey','EnumKey','EnumValue','ExpandEnvironmentStrings','FlushKey','HKEYType','LoadKey','OpenKey','OpenKeyEx','QueryInfoKey','QueryReflectionKey','QueryValue','QueryValueEx','SaveKey','SetValue','SetValueEx','error')
if($r.metadata_trap_count -ne 12 -or $r.registry_trap_count -ne 25){throw 'Trap counts'}
Same @($r.registry_trap_names) $trapNames 'Exact registry traps'
foreach($name in @('guard_denials','registry_denials','heavy_roots_loaded')){if(@($r.$name).Count -ne 0){throw ('Unexpected '+$name)}}
if($r.stdout_capture -cne '' -or $r.stderr_capture -cne '' -or $r.native_exit -ne 0){throw 'Capture or child exit'}
if($r.elapsed_seconds -isnot [ValueType] -or $r.elapsed_seconds -lt 0 -or $r.elapsed_seconds -ge 3600){throw 'Elapsed field'}
if($native.schema -cne 'uoink.native-exit.v1' -or $native.child_returned -cne $true -or $native.native_exit -ne 0){throw 'Immediate native receipt'}
if($exit.native_exit -ne 0 -or $exit.outer_exit -ne 0 -or $exit.inputs_unchanged -cne $true -or $exit.receipt_valid -cne $true -or $null -ne $exit.receipt_parse_error_type -or $exit.startup_binding_set -cne $true){throw 'Final exit receipt'}
$stdout=Text-Binding (Join-Path $taskRun 'stdout.json');$stderr=Text-Binding (Join-Path $taskRun 'stderr.log')
if($stdout.bytes -ne $exit.stdout_bytes -or $stdout.bytes -gt 131073 -or $stderr.bytes -ne 0 -or $exit.stderr_bytes -ne 0){throw 'Raw capture binding'}
if($plan.label -cne 'protected-engine-fake01' -or $plan.startup_binding_set -cne $true -or $plan.interpreter -cne 'C:\Python314\python.exe'){throw 'Plan identity'}
Same @($plan.arguments) @('-I','-S','-B','qualify_owner.py') 'Plan arguments'
Same @($plan.planned_cases) @($expected.ordered_cases) 'Plan cases'
Same @($plan.inputs.name) $names 'Plan inputs'
Same @($after.name) @($names+'ROOT-ADMISSION.json') 'After input membership'
if($admission.root_reviewed -cne $true -or $admission.label -cne 'protected-engine-fake01' -or $admission.scope -cne 'protected-engine-ownership-fake-39-only'){throw 'Actual admission binding'}
Same @($admission.expected_cases) @($expected.ordered_cases) 'Admission cases'
Same @($admission.input_sha256.PSObject.Properties.Name|Sort-Object) @($names|Sort-Object) 'Admission input keys'
$children=@($names[0..37])
Same @($r.input_sha256.PSObject.Properties.Name|Sort-Object) @($children|Sort-Object) '38 child hash names'
$checked=@()
for($i=0;$i -lt 40;$i++){
 $row=$pins.files[$i];$p=$plan.inputs[$i];$a=$after[$i]
 $sourcePath=Join-Path $taskSource $row.path;$copyPath=Join-Path $taskRun $row.path
 if([IO.Path]::GetFullPath($p.source) -cne $sourcePath){throw 'Original source path mismatch'}
 $original=Text-Binding $sourcePath;$copy=Text-Binding $copyPath
 if($original.bytes -ne $row.bytes -or $copy.bytes -ne $row.bytes){throw 'Source/copy byte size'}
 foreach($hash in @($p.sha256,$a.before_sha256,$a.copy_after_sha256,$a.source_after_sha256,$original.sha256,$copy.sha256,$admission.input_sha256.($row.path))){if($hash -cne $row.sha256){throw ('Source/control hash mismatch '+$row.path)}}
 if($i -lt 38 -and $r.input_sha256.($row.path) -cne $row.sha256){throw 'Child raw hash mismatch'}
 $checked += [ordered]@{name=$row.path;bytes=$row.bytes;sha256=$row.sha256}
}
$a=$after[40];$admissionCurrent=Text-Binding (Join-Path $taskSource 'ROOT-ADMISSION.json');$admissionCopy=Text-Binding (Join-Path $taskRun 'ROOT-ADMISSION.json')
foreach($hash in @($a.copy_after_sha256,$a.source_after_sha256,$admissionCurrent.sha256,$admissionCopy.sha256)){if($hash -cne $a.before_sha256){throw 'Admission changed'}}
$initial=Read-Json (Join-Path $taskRepo '_scratch/ENGINE-FAKE39-AUTHOR-ACTUAL.json')
$poll=Read-Json (Join-Path $taskRepo '_scratch/ENGINE-FAKE39-AUTHOR-POLL01-ACTUAL.json')
$final=Read-Json (Join-Path $taskRepo '_scratch/ENGINE-FAKE39-AUTHOR-POLL02-ACTUAL.json')
if($initial.chunk_id -cne '4e81bd' -or $initial.session_id -ne 7190 -or $null -ne $initial.exit_code -or $poll.chunk_id -cne '7e49b6' -or $poll.session_id -ne 7190 -or $null -ne $poll.exit_code -or $final.chunk_id -cne '09d91a' -or $final.exit_code -ne 0 -or $null -ne $final.session_id){throw 'Actual tool completion chain mismatch'}
$caseText=$r.cases|ConvertTo-Json -Depth 10 -Compress
$caseDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($caseText))).ToLowerInvariant()
[ordered]@{status='AUTHOR_PASSIVE_RECEIPT_REVIEW_PASS';subject_rerun=$false;cases=39;passed=39;failed=0;skipped=0;ordered_case_objects_exact=$true;case_object_digest=$caseDigest;subtest_receipts='not separately recorded by inherited direct-method instrument';child_hashes=38;source_control_before_copy_after_current=40;admission_before_copy_after_current=1;outputs=47;guards=10;all_guards=$true;metadata_traps=12;registry_traps=25;denials=0;heavy_roots=0;captures_empty=$true;stdout=$stdout;stderr_bytes=0;elapsed_seconds=$r.elapsed_seconds;native_exit=0;outer_exit=0;actual_initial='4e81bd';actual_pending_poll='7e49b6';actual_final='09d91a';session=7190;admission=$admissionCurrent;source_pins=$pinsBinding;pair_status='Independent data not yet reviewed';scope='Generated ownership/factory methods with fake APIs only; no native/backend acceptance'}|ConvertTo-Json -Depth 10
