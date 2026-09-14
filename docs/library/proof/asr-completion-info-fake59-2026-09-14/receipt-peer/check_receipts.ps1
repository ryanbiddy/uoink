param([Parameter(Mandatory=$true)][string]$SourceRoot, [Parameter(Mandatory=$true)][string]$RunName, [Parameter(Mandatory=$true)][string]$ActualPath, [Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop'
function Need($value, [string]$reason) { if (-not $value) { throw $reason } }
function TrueValue($value) { return $value -is [bool] -and $value }
function Json([string]$path) { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
function Binding([string]$path) {
 $item=Get-Item -LiteralPath $path
 Need (-not $item.PSIsContainer -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'ordinary text required'
 return [pscustomobject]@{bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function SameBinding($a,$b) { return $a.bytes -eq $b.bytes -and $a.sha256 -ceq $b.sha256 }
function SameList($a,$b) { return $a.Count -eq $b.Count -and ($a -join "`n") -ceq ($b -join "`n") }
$base='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\'
$SourceRoot=[IO.Path]::GetFullPath($SourceRoot)
Need ($SourceRoot.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)) 'source root scope'
Need ($RunName -match '^[a-z0-9-]+$') 'run leaf required'
$run=Join-Path $SourceRoot $RunName
$allowed=@('BRIEF.md','exit.json','EXPECTED-CASES.json','input-check.json','lifecycle46_cases.py','native-exit.json','PINS.json','plan.json','QUALIFICATION-PROTOCOL.md','qualify_completion_info.py','ROOT-ADMISSION.json','run_fake59_01.ps1','snapshot_lifecycle.py','SOURCE-INPUTS.json','stderr.log','stdout.json','test_completion_info.py')
$observed=@(Get-ChildItem -LiteralPath $run | Sort-Object Name)
Need ($observed.Count -eq 17 -and @($observed|Where-Object {$_.PSIsContainer}).Count -eq 0) 'exact flat17 outputs'
Need (SameList @($observed.Name) @($allowed|Sort-Object)) 'output membership'
$before=@{}
foreach($name in $allowed){$before[$name]=Binding (Join-Path $run $name)}
$actual=Json $ActualPath
$result=Json (Join-Path $run 'stdout.json')
$exit=Json (Join-Path $run 'exit.json')
$native=Json (Join-Path $run 'native-exit.json')
$plan=Json (Join-Path $run 'plan.json')
$check=Json (Join-Path $run 'input-check.json')
$pins=Json (Join-Path $run 'PINS.json')
$admission=Json (Join-Path $run 'ROOT-ADMISSION.json')
$expected=@(Json (Join-Path $run 'EXPECTED-CASES.json'))
Need ($actual.exit_code -eq 0 -and $native.native_exit -eq 0 -and $exit.native_exit -eq 0 -and $exit.qualification_exit -eq 0 -and $result.qualification_exit -eq 0) 'actual/child/qualification exits'
Need ($result.schema -ceq 'uoink.completion-info-fake-preflight.v1' -and $result.scope -ceq 'Original lifecycle46 plus thirteen completion-info cases; inert ports only, no backend or native metadata qualification') 'receipt schema/scope'
Need ($expected.Count -eq 59 -and $result.cases.Count -eq 59 -and $result.count -eq 59 -and $result.passed -eq 59 -and $result.failed -eq 0 -and $result.skipped -eq 0) '59 complete results'
Need (SameList @($result.cases.id) $expected) 'actual ordered case IDs'
Need (SameList @($result.expected_cases) $expected) 'recorded expected IDs'
$nested=0
foreach($case in $result.cases){
 Need (SameList @($case.PSObject.Properties.Name|Sort-Object) @('errors','id','passed','skipped','subtests')) 'complete case fields'
 Need ((TrueValue $case.passed) -and $case.skipped -is [bool] -and -not $case.skipped -and $case.errors.Count -eq 0) 'case outcome'
 foreach($sub in $case.subtests){
  Need (SameList @($sub.PSObject.Properties.Name|Sort-Object) @('id','passed')) 'subtest fields'
  Need ((TrueValue $sub.passed) -and $sub.id.StartsWith($case.id+' (',[StringComparison]::Ordinal)) 'subtest outcome/parent'
  $nested++
 }
}
$legacyNested=0
foreach($case in $result.cases[0..45]){$legacyNested+=$case.subtests.Count}
Need ($nested -eq 29 -and $legacyNested -eq 0) 'new13 nested29'
$guardNames=@('startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','real_entrypoints_unchanged')
Need (SameList @($result.guards.PSObject.Properties.Name|Sort-Object) @($guardNames|Sort-Object)) 'exact ten guards'
foreach($name in $guardNames){Need (TrueValue $result.guards.$name) ('guard '+$name)}
foreach($flag in @('membership_valid','guard_valid')){Need (TrueValue $result.$flag) $flag}
Need ($result.metadata_trap_count -eq 12 -and $result.registry_trap_count -eq 25 -and $result.guard_denials.Count -eq 0 -and $result.registry_denials.Count -eq 0 -and $result.heavy_roots_loaded.Count -eq 0) 'traps/denials/heavy roots'
foreach($flag in @('valid','inputs_unchanged','membership_valid','guards_valid')){Need (TrueValue $exit.$flag) ('exit '+$flag)}
Need ($exit.passed -eq 59 -and $exit.failed -eq 0 -and $exit.skipped -eq 0 -and $exit.stdout_bytes -eq $before['stdout.json'].bytes -and $exit.stderr_bytes -eq 0 -and $before['stderr.log'].bytes -eq 0) 'exit counts/streams'
Need ($pins.files.Count -eq 9 -and $plan.before.Count -eq 9 -and $check.inputs.Count -eq 9 -and $plan.controls.Count -eq 3 -and $check.controls.Count -eq 3 -and (TrueValue $check.inputs_unchanged)) 'nine inputs/three controls'
Need (SameList @($pins.files.path) @($plan.before.name)) 'pins and before membership'
Need (SameList @($pins.files.path) @($check.inputs.name)) 'pins and after membership'
foreach($pin in $pins.files){
 $pre=@($plan.before|Where-Object {$_.name -ceq $pin.path});$post=@($check.inputs|Where-Object {$_.name -ceq $pin.path})
 Need ($pre.Count -eq 1 -and $post.Count -eq 1 -and (TrueValue $post[0].unchanged)) 'single unchanged input row'
 foreach($value in @($pre[0],$post[0].original,$post[0].copy,$before[$pin.path],(Binding (Join-Path $SourceRoot $pin.path)))){Need (SameBinding $pin $value) ('input hash '+$pin.path)}
}
Need (SameList @($plan.controls.name) @('PINS.json','ROOT-ADMISSION.json','run_fake59_01.ps1')) 'control membership'
Need (SameList @($check.controls.name) @($plan.controls.name)) 'after control membership'
foreach($control in $plan.controls){
 $post=@($check.controls|Where-Object {$_.name -ceq $control.name})
 Need ($post.Count -eq 1 -and (TrueValue $post[0].unchanged)) 'single unchanged control row'
 foreach($value in @($post[0].original,$post[0].copy,$before[$control.name],(Binding (Join-Path $SourceRoot $control.name)))){Need (SameBinding $control.binding $value) ('control hash '+$control.name)}
}
$childNames=@('snapshot_lifecycle.py','lifecycle46_cases.py','test_completion_info.py','qualify_completion_info.py','EXPECTED-CASES.json')
Need (SameList @($result.input_sha256.PSObject.Properties.Name) $childNames) 'five child inputs'
foreach($name in $childNames){Need ($result.input_sha256.$name -ceq $before[$name].sha256) ('child hash '+$name)}
Need ((TrueValue $admission.approved) -and $admission.label -ceq $RunName -and $admission.pins_sha256 -ceq $before['PINS.json'].sha256 -and $admission.scope -ceq 'generated_bytes_and_fake_ports_only') 'admission binding'
Need ($plan.label -ceq $RunName -and $plan.scope -ceq $admission.scope -and $plan.python -ceq 'C:\Python314\python.exe' -and (TrueValue $plan.startup_binding_set)) 'plan scope'
Need (SameList @($plan.arguments) @('-I','-S','-B',(Join-Path $run 'qualify_completion_info.py'))) 'isolated recorded command'
$referenceRoot=Join-Path $base 'asr-completion-info-fake59-author01'
$oldPath=Join-Path $referenceRoot 'before\LIFECYCLE46-EXPECTED.json'
$newPath=Join-Path $referenceRoot 'before\COMPLETION13-EXPECTED.json'
Need ((Binding $oldPath).sha256 -ceq 'a03a8da9270ec47ec796e19a3b6795f9861cea65b6e577fc21a617bffe8d6228') 'original46 list binding'
Need ((Binding $newPath).sha256 -ceq 'a3869c885d622f4f7f248878213af44f2fd3315106ebdd661a00f6318def06f9') 'new13 list binding'
$oldExpected=Json $oldPath
Need ($oldExpected.schema -ceq 'uoink.lifecycle-expected-cases.v1' -and $oldExpected.count -eq 46) 'original46 schema'
Need (SameList @($expected[0..45]) @($oldExpected.ordered_cases)) 'original46 exact order'
Need (SameList @($expected[46..58]) @(Json $newPath)) 'new13 exact order'
foreach($name in $allowed){Need (SameBinding $before[$name] (Binding (Join-Path $run $name))) ('review changed input '+$name)}
Need (-not (Test-Path -LiteralPath $ResultPath)) 'fresh review result required'
$out=[ordered]@{scope='Independent passive saved-receipt review only';source_root=$SourceRoot;run_name=$RunName;actual_chunk=$actual.chunk_id;actual_exit=$actual.exit_code;actual_seconds=$actual.wall_time_seconds;native_exit=$native.native_exit;native_seconds=$native.elapsed_seconds;launcher_seconds=$exit.elapsed_seconds;case_seconds=$result.elapsed_seconds;passed=59;failed=0;skipped=0;subtests_passed=$nested;original46_order=$true;new13_order=$true;child_hashes=5;inputs=9;controls=3;output_files=17;guards=10;metadata_traps=12;registry_traps=25;stderr_bytes=0;stdout=$before['stdout.json'];inputs_unchanged_during_review=$true;subject_rerun=$false;independent_pair_pending=$true}
[IO.File]::WriteAllText($ResultPath,($out|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
$out|ConvertTo-Json -Depth 8
