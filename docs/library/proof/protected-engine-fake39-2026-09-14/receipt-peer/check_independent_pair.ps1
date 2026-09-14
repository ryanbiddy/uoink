$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskRepo '_scratch/protected-engine-ownership-fake39-independent01'
$taskRun=Join-Path $taskSource 'runs/protected-engine-confirmation01'
function Text-Binding([string]$path){
 $item=Get-Item -LiteralPath $path
 if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 1048576){throw 'Bounded plain text required'}
 [ordered]@{bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Read-Json([string]$path){$null=Text-Binding $path;Get-Content -LiteralPath $path -Raw|ConvertFrom-Json}
function Same($a,$b,[string]$why){if(($a|ConvertTo-Json -Depth 30 -Compress) -cne ($b|ConvertTo-Json -Depth 30 -Compress)){throw $why}}
$pinsPath=Join-Path $taskSource 'PINS.json'
$pinsBinding=Text-Binding $pinsPath
if($pinsBinding.sha256 -cne '570221683bb0e49c52ee5a3fe81261eb2c30c3ff37206120ef0ee8d074173154'){throw 'Independent PINS changed'}
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
if($plan.label -cne 'protected-engine-confirmation01' -or $plan.startup_binding_set -cne $true -or $plan.interpreter -cne 'C:\Python314\python.exe'){throw 'Plan identity'}
Same @($plan.arguments) @('-I','-S','-B','qualify_owner.py') 'Plan arguments'
Same @($plan.planned_cases) @($expected.ordered_cases) 'Plan cases'
Same @($plan.inputs.name) $names 'Plan inputs'
Same @($after.name) @($names+'ROOT-ADMISSION.json') 'After input membership'
if($admission.root_reviewed -cne $true -or $admission.label -cne 'protected-engine-confirmation01' -or $admission.scope -cne 'protected-engine-ownership-fake-39-only'){throw 'Actual admission binding'}
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
$initial=Read-Json (Join-Path $taskRepo '_scratch/ENGINE-FAKE39-INDEPENDENT-INITIAL-ACTUAL.json')
$final=Read-Json (Join-Path $taskRepo '_scratch/ENGINE-FAKE39-INDEPENDENT-FINAL-ACTUAL.json')
if($initial.chunk_id -cne 'febfe4' -or $initial.session_id -ne 39862 -or $null -ne $initial.exit_code -or $final.chunk_id -cne 'f5c18c' -or $final.exit_code -ne 0 -or $null -ne $final.session_id){throw 'Independent actual completion chain mismatch'}
$authorSource=Join-Path $taskRepo '_scratch/protected-engine-ownership-fake39-author01'
$authorRun=Join-Path $authorSource 'runs/protected-engine-fake01'
$authorStdout=Text-Binding (Join-Path $authorRun 'stdout.json')
if($authorStdout.sha256 -cne 'da578e702b569c953a17b767111cff56c1e6f9b705343a91ff2894ffacb36fa4'){throw 'Reviewed author stdout changed'}
$author=Read-Json (Join-Path $authorRun 'stdout.json')
Same @($r.cases) @($author.cases) 'Complete author/independent case objects differ'
Same $r.input_sha256 $author.input_sha256 'Complete38 child hash objects differ'
Same @($r.expected_cases) @($author.expected_cases) 'Complete expected IDs differ'
foreach($name in @($guardNames+'guard_valid'+'metadata_trap_count'+'registry_trap_count'+'registry_trap_names'+'guard_denials'+'registry_denials'+'heavy_roots_loaded'+'stdout_capture'+'stderr_capture')){Same $r.$name $author.$name ('Pair guard/capture differs '+$name)}
$authorPins=Read-Json (Join-Path $authorSource 'PINS.json')
$authorPlan=Read-Json (Join-Path $authorRun 'plan.json')
$authorAfter=Read-Json (Join-Path $authorRun 'after.json')
if((Text-Binding (Join-Path $authorSource 'PINS.json')).sha256 -cne '7309394f50729101e23899ef1a947639e4abcb27d59910f3dd2446d98f3524ba'){throw 'Author PINS current mismatch'}
Same @($authorPins.files.path) $names 'Pair parent membership differs'
Same @((Get-ChildItem -LiteralPath $authorRun -Force).Name|Sort-Object) @($expectedFiles|Sort-Object) 'Author47 membership changed'
for($i=0;$i -lt 40;$i++){
 $row=$authorPins.files[$i];$ap=$authorPlan.inputs[$i];$aa=$authorAfter[$i]
 if($ap.name -cne $row.path -or $aa.name -cne $row.path -or [IO.Path]::GetFullPath($ap.source) -cne (Join-Path $authorSource $row.path)){throw 'Author before/after name/path changed'}
 foreach($path in @((Join-Path $authorSource $row.path),(Join-Path $authorRun $row.path))){$binding=Text-Binding $path;if($binding.bytes -ne $row.bytes -or $binding.sha256 -cne $row.sha256){throw 'Author current source/copy changed'}}
 foreach($hash in @($ap.sha256,$aa.before_sha256,$aa.source_after_sha256,$aa.copy_after_sha256)){if($hash -cne $row.sha256){throw 'Author before/after hash changed'}}
}
$authorAdmission=Text-Binding (Join-Path $authorSource 'ROOT-ADMISSION.json')
$authorAdmissionCopy=Text-Binding (Join-Path $authorRun 'ROOT-ADMISSION.json')
if($authorAdmission.sha256 -cne '8568d9b14b52b439ffe45679d20c90700f59f59679ed900073b338fcd31ade3d' -or $authorAdmissionCopy.sha256 -cne $authorAdmission.sha256){throw 'Author authority changed'}
$authorAuthority=Read-Json (Join-Path $authorSource 'ROOT-ADMISSION.json')
foreach($row in $authorPins.files){if($authorAuthority.input_sha256.($row.path) -cne $row.sha256){throw 'Author authority input mismatch'}}
$aa=$authorAfter[40]
if($aa.name -cne 'ROOT-ADMISSION.json'){throw 'Author admission after row'}
foreach($hash in @($aa.before_sha256,$aa.source_after_sha256,$aa.copy_after_sha256)){if($hash -cne $authorAdmission.sha256){throw 'Author authority before/after'}}
$caseText=$r.cases|ConvertTo-Json -Depth 10 -Compress
$caseDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($caseText))).ToLowerInvariant()
[ordered]@{status='INDEPENDENT_AND_PAIR_PASSIVE_RECEIPT_REVIEW_PASS';subject_rerun=$false;each_count=39;each_passed=39;each_failed=0;each_skipped=0;complete_case_objects_equal=$true;case_object_digest=$caseDigest;complete_child_hash_objects_equal=$true;child_hash_count=38;source_control_before_copy_after_current_each=40;admission_before_copy_after_current_each=1;outputs_each=47;guards_each=10;all_guards_equal_true=$true;metadata_traps_each=12;registry_traps_each=25;denials_each=0;heavy_roots_each=0;captures_each_empty=$true;author_stdout=$authorStdout;independent_stdout=$stdout;stderr_each_bytes=0;author_elapsed_seconds=$author.elapsed_seconds;independent_elapsed_seconds=$r.elapsed_seconds;native_each=0;outer_each=0;independent_actual_initial='febfe4';independent_actual_final='f5c18c';independent_session=39862;independent_admission=$admissionCurrent;independent_pins=$pinsBinding;separate_subtest_receipts=$false;scope='Fixed generated ownership/factory/engine methods with fake APIs only'}|ConvertTo-Json -Depth 12
