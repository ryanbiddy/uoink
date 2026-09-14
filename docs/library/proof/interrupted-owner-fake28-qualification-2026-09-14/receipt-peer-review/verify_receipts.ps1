# Passive fixed-text receipt verifier. No candidate/process/native invocation.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskCheckout = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskScratch = Join-Path $taskCheckout '_scratch'
$taskOut = Join-Path $taskScratch 'interrupted-fake28-peer-receipt-review01\RESULT01.json'
$taskParents = @(
    (Join-Path $taskScratch 'interrupted-retirement-fake28-author01'),
    (Join-Path $taskScratch 'astra-interrupted-retirement-confirmation01'))
$taskLabels = @('interrupted-retirement-fake01','interrupted-retirement-confirmation01')
$taskActualNames = @('INTERRUPTED-FAKE28-AUTHOR-RUN-ACTUAL.json','INTERRUPTED-FAKE28-INDEPENDENT-RUN-ACTUAL.json')
$taskChunks = @('70e7f4','dd5dc7')
$taskPayloads = @(
'plain_state_reader.py','state_bridge.py','owned_cpu_tensor_port.py','model_binding_registry.py',
'owned_factory_port.py','owned_guard.py','fake_torch_support.py','fixed_schema_helpers.py',
'worker_runtime_owner.py','reservation_file_port.py','snapshot_reservations.py','snapshot_lifecycle.py',
'durable_lifecycle.py','win32_worker_connection.py','windows_reservation_port.py','owned_generation_protocol.py',
'win32_private_pipe.py','pinned_buffer_namespace.py','inherited_readset.py','generated_worker_flow.py',
'generated_operation_flow.py','trusted_asr_resolver.py','asr_loading_adapter.py','generated_journal_setup.py',
'generated_writer_exclusion.py','generated_worker_factory_inputs.py','generated_worker_runtime_bridge.py',
'generated_adapter_flow.py','test_reservations.py','test_windows_reservations.py','test_journal_cancel.py',
'test_retired_owner_recovery.py','test_interrupted_owner_retirement.py','qualify_windows_reservations.py',
'EXPECTED-CASES.json','BRIEF.md','QUALIFICATION-PROTOCOL.md','run_preflight01.ps1')
$taskControls = @('PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1')
$taskRunNames = @($taskPayloads + @('PINS.json','ROOT-ADMISSION.json','exit.json','native-exit.json','input-check.json','plan.json','stdout.json','stderr.log'))
$taskKnown = @{}
foreach($taskParent in $taskParents) {
    foreach($taskName in @($taskPayloads + @('PINS.json','ROOT-ADMISSION.json','ROOT-ADMISSION.template.json'))) {
        $taskKnown[(Join-Path $taskParent $taskName)] = $true
    }
}
for($taskIndex=0;$taskIndex -lt 2;$taskIndex++) {
    foreach($taskName in $taskRunNames) {
        $taskKnown[(Join-Path (Join-Path $taskParents[$taskIndex] $taskLabels[$taskIndex]) $taskName)] = $true
    }
    $taskKnown[(Join-Path $taskScratch $taskActualNames[$taskIndex])] = $true
}
$taskCopyPath = Join-Path $taskParents[1] 'COPY-BINDINGS.json'
$taskOriginal22 = Join-Path $taskCheckout 'docs\library\proof\retired-owner-recovery-qualification-2026-09-13\proposal\EXPECTED-CASES.json'
$taskKnown[$taskCopyPath] = $true
$taskKnown[$taskOriginal22] = $true
$taskReadBindings = @{}
function Need($taskCondition,[string]$taskReason) {
    if($taskCondition -isnot [bool] -or -not $taskCondition) { throw $taskReason }
}
function Yes($taskValue,[string]$taskReason) { Need ($taskValue -is [bool] -and $taskValue) $taskReason }
function No($taskValue,[string]$taskReason) { Need ($taskValue -is [bool] -and -not $taskValue) $taskReason }
function Canon($taskValue) { return ConvertTo-Json -InputObject $taskValue -Depth 60 -Compress }
function HashText([string]$taskPath) {
    Need ($taskKnown.ContainsKey($taskPath)) 'unlisted text path'
    $taskItem=Get-Item -LiteralPath $taskPath
    Need (-not $taskItem.PSIsContainer -and ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'nonordinary text leaf'
    Need ($taskItem.Length -le 131072) 'fixed text cap exceeded'
    $taskBinding=[ordered]@{bytes=$taskItem.Length;sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    if($taskReadBindings.ContainsKey($taskPath)) { Need ((Canon $taskReadBindings[$taskPath]) -ceq (Canon $taskBinding)) 'text changed during read' }
    else { $taskReadBindings[$taskPath]=$taskBinding }
    return $taskBinding
}
function Text([string]$taskPath) { $null=HashText $taskPath; return [IO.File]::ReadAllText($taskPath) }
function Json([string]$taskPath) { return ConvertFrom-Json -InputObject (Text $taskPath) }
function SameBinding($taskObserved,$taskExpected,[string]$taskReason) {
    Need ($taskObserved.bytes -eq $taskExpected.bytes -and $taskObserved.sha256 -ceq $taskExpected.sha256) $taskReason
}
function Names($taskRows,[string]$taskProperty) {
    $taskMap=@{}
    foreach($taskRow in $taskRows) {
        $taskName=$taskRow.$taskProperty
        Need ($taskName -is [string] -and -not $taskMap.ContainsKey($taskName)) 'duplicate/invalid row name'
        $taskMap[$taskName]=$taskRow
    }
    return $taskMap
}
function SameNames($taskA,$taskB,[string]$taskReason) {
    Need ((Canon @($taskA | Sort-Object -CaseSensitive)) -ceq (Canon @($taskB | Sort-Object -CaseSensitive))) $taskReason
}
$taskGuardNames=@('startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed',
'baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed',
'captures_installed','capture_valid','real_entrypoints_unchanged')
$taskOldPins=@{
'test_reservations.py'='604a295d5e925b9a9d7f55750bfeb1ddcda3e6a9873d6d8d7f9e98c84d9b4b9e'
'test_windows_reservations.py'='91b0de71eb55d088ee2fdbcd11ff3e6a074f18f713dfcd5b384814a1dc78300c'
'test_journal_cancel.py'='b02f35091e45af10380d725de77fc84e1f3e4c42f8bd163e41c78222b4aa6b31'
'test_retired_owner_recovery.py'='1da9c5f8eefdad3ae4f2b22d8b632b242a2cb27296bbec6e6dd96c24da687f0c'}
$taskOldIDs=@(Json $taskOriginal22)
Need ($taskOldIDs.Count -eq 22) 'original22 count'
$taskRunResults=@()
$taskParsedResults=@()
$taskPinMaps=@()
for($taskIndex=0;$taskIndex -lt 2;$taskIndex++) {
    $taskParent=$taskParents[$taskIndex]
    $taskRun=Join-Path $taskParent $taskLabels[$taskIndex]
    $taskDisk=@(Get-ChildItem -LiteralPath $taskRun -Force)
    Need ($taskDisk.Count -eq 46 -and @($taskDisk | Where-Object PSIsContainer).Count -eq 0) 'run exact46 flat membership'
    SameNames @($taskDisk.Name) $taskRunNames 'run unlisted/missing file'
    $taskPins=Json (Join-Path $taskParent 'PINS.json')
    Yes $taskPins.finalized 'pins not final'
    $taskPinMap=Names $taskPins.files 'path'
    SameNames @($taskPinMap.Keys) $taskPayloads 'pins exact38'
    $taskPinMaps+=,$taskPinMap
    $taskExpected=@(Json (Join-Path $taskRun 'EXPECTED-CASES.json'))
    Need ($taskExpected.Count -eq 28 -and @($taskExpected | Select-Object -Unique).Count -eq 28) 'expected28 unique'
    Need ((Canon @($taskExpected[0..21])) -ceq (Canon $taskOldIDs)) 'original22 order changed'
    $taskAdmission=Json (Join-Path $taskParent 'ROOT-ADMISSION.json')
    Yes $taskAdmission.approved 'actual admission'
    Need ($taskAdmission.label -ceq $taskLabels[$taskIndex] -and $taskAdmission.scope -ceq 'generated_bytes_and_fake_ports_only') 'admission scope/label'
    Need ($taskAdmission.pins_sha256 -ceq (HashText (Join-Path $taskParent 'PINS.json')).sha256) 'admission pin binding'
    $taskTemplate=Json (Join-Path $taskParent 'ROOT-ADMISSION.template.json')
    No $taskTemplate.approved 'historical template must stay false'
    Need ($taskTemplate.pins_sha256 -ceq $taskAdmission.pins_sha256) 'template source binding'
    $taskPlan=Json (Join-Path $taskRun 'plan.json')
    $taskCheck=Json (Join-Path $taskRun 'input-check.json')
    $taskExit=Json (Join-Path $taskRun 'exit.json')
    $taskNative=Json (Join-Path $taskRun 'native-exit.json')
    $taskResult=Json (Join-Path $taskRun 'stdout.json')
    $taskActual=Json (Join-Path $taskScratch $taskActualNames[$taskIndex])
    Need ($taskActual.chunk_id -ceq $taskChunks[$taskIndex] -and $taskActual.exit_code -eq 0 -and $taskNative.native_exit -eq 0 -and $taskExit.native_exit -eq 0 -and $taskExit.qualification_exit -eq 0 -and $taskResult.qualification_exit -eq 0) 'actual/native/qualification exits'
    Need ($taskActual.output -ceq ($taskLabels[$taskIndex]+': 28 passed, 0 failed, 0 skipped; generated scope only.'+[char]13+[char]10)) 'actual outcome text'
    Need ($taskPlan.python -ceq 'C:\Python314\python.exe' -and $taskPlan.label -ceq $taskLabels[$taskIndex] -and $taskPlan.scope -ceq 'generated_bytes_and_fake_ports_only') 'recorded startup scope'
    Need ((Canon @($taskPlan.arguments)) -ceq (Canon @('-I','-S','-B',(Join-Path $taskRun 'qualify_windows_reservations.py')))) 'recorded startup arguments'
    Yes $taskPlan.startup_binding_set 'startup binding record'
    foreach($taskField in @('valid','inputs_unchanged','membership_valid','guards_valid')) { Yes $taskExit.$taskField ('exit flag '+$taskField) }
    foreach($taskField in @('membership_valid','guard_valid')) { Yes $taskResult.$taskField ('result flag '+$taskField) }
    Yes $taskCheck.inputs_unchanged 'after input check'
    SameNames @($taskResult.guards.PSObject.Properties.Name) $taskGuardNames 'exact ten guards'
    foreach($taskGuard in $taskGuardNames) { Yes $taskResult.guards.$taskGuard ('guard '+$taskGuard) }
    Need ($taskResult.metadata_trap_count -eq 12 -and $taskResult.registry_trap_count -eq 25) 'trap counts'
    foreach($taskField in @('guard_denials','registry_denials','heavy_roots_loaded')) { Need (@($taskResult.$taskField).Count -eq 0) ('unexpected '+$taskField) }
    Need ($taskResult.scope -ceq 'Original22 plus six interrupted-owner cases; fake Windows services only; native interruption, restart and model behavior unmeasured') 'fake-only recorded scope'
    foreach($taskCountOwner in @($taskResult,$taskExit)) { Need ($taskCountOwner.passed -eq 28 -and $taskCountOwner.failed -eq 0 -and $taskCountOwner.skipped -eq 0) 'summary case counts' }
    Need ($taskResult.count -eq 28 -and @($taskResult.cases).Count -eq 28) 'raw28 cases'
    Need ((Canon @($taskResult.cases.id)) -ceq (Canon $taskExpected) -and (Canon @($taskResult.expected_cases)) -ceq (Canon $taskExpected)) 'raw ordered case IDs'
    $taskSubCount=0
    foreach($taskCase in $taskResult.cases) {
        Yes $taskCase.passed 'raw case failed'; No $taskCase.skipped 'raw case skipped'
        Need (@($taskCase.errors).Count -eq 0) 'raw case errors'
        Need (@($taskCase.subtests).Count -le 64) 'subtest receipt cap'
        foreach($taskSub in $taskCase.subtests) { Yes $taskSub.passed 'raw subtest failed'; $taskSubCount++ }
    }
    Need ($taskSubCount -eq 57) 'exact57 passing subtests'
    $taskBefore=Names $taskPlan.before 'name'; $taskAfter=Names $taskCheck.inputs 'name'
    SameNames @($taskBefore.Keys) $taskPayloads 'before38'; SameNames @($taskAfter.Keys) $taskPayloads 'after38'
    foreach($taskName in $taskPayloads) {
        $taskParentBinding=HashText (Join-Path $taskParent $taskName)
        $taskRunBinding=HashText (Join-Path $taskRun $taskName)
        SameBinding $taskParentBinding $taskPinMap[$taskName] 'parent pin'
        SameBinding $taskRunBinding $taskPinMap[$taskName] 'copy pin'
        SameBinding $taskBefore[$taskName] $taskPinMap[$taskName] 'before pin'
        SameBinding $taskAfter[$taskName].original $taskPinMap[$taskName] 'after original pin'
        SameBinding $taskAfter[$taskName].copy $taskPinMap[$taskName] 'after copy pin'
        Yes $taskAfter[$taskName].unchanged 'after unchanged false'
    }
    $taskControlBefore=Names $taskPlan.controls 'name'; $taskControlAfter=Names $taskCheck.controls 'name'
    SameNames @($taskControlBefore.Keys) $taskControls 'before controls'; SameNames @($taskControlAfter.Keys) $taskControls 'after controls'
    foreach($taskName in $taskControls) {
        $taskBinding=HashText (Join-Path $taskParent $taskName)
        SameBinding (HashText (Join-Path $taskRun $taskName)) $taskBinding 'control copy'
        SameBinding $taskControlBefore[$taskName].binding $taskBinding 'control before'
        SameBinding $taskControlAfter[$taskName].original $taskBinding 'control after original'
        SameBinding $taskControlAfter[$taskName].copy $taskBinding 'control after copy'
        Yes $taskControlAfter[$taskName].unchanged 'control changed'
    }
    $taskChildNames=@($taskResult.input_sha256.PSObject.Properties.Name)
    SameNames $taskChildNames @($taskPayloads[0..34]) '35 child inputs'
    foreach($taskName in $taskChildNames) { Need ($taskResult.input_sha256.$taskName -ceq $taskPinMap[$taskName].sha256) 'child input hash' }
    foreach($taskName in $taskOldPins.Keys) { Need ($taskPinMap[$taskName].sha256 -ceq $taskOldPins[$taskName]) 'original test source changed' }
    Need ((HashText (Join-Path $taskRun 'stderr.log')).bytes -eq 0 -and $taskExit.stderr_bytes -eq 0) 'stderr not empty'
    Need ((HashText (Join-Path $taskRun 'stdout.json')).bytes -eq $taskExit.stdout_bytes) 'stdout size'
    $taskRunResults+=[ordered]@{label=$taskLabels[$taskIndex];passed=28;failed=0;skipped=0;passing_subtests=$taskSubCount;guards=10;metadata_traps=12;registry_traps=25;payloads=38;controls=3;child_hashes=35;run_files=46;stderr_bytes=0;case_elapsed=$taskResult.elapsed_seconds;launcher_elapsed=$taskExit.elapsed_seconds;actual_chunk=$taskActual.chunk_id;actual_elapsed=$taskActual.wall_time_seconds;actual_exit=$taskActual.exit_code;stdout_sha256=(HashText (Join-Path $taskRun 'stdout.json')).sha256}
    $taskParsedResults+=,$taskResult
}
Need ((Canon @($taskParsedResults[0].cases)) -ceq (Canon @($taskParsedResults[1].cases))) 'complete ordered case objects differ'
Need ((Canon $taskParsedResults[0].input_sha256) -ceq (Canon $taskParsedResults[1].input_sha256)) '35 child hash objects differ'
$taskCopy=Json $taskCopyPath
Need ($taskCopy.payload_count -eq 38 -and $taskCopy.exact_payloads -eq 37 -and $taskCopy.label_only_payloads -eq 1 -and $taskCopy.child_inputs -eq 35 -and $taskCopy.label_replacements -eq 5) 'copy counts'
$taskRelations=Names $taskCopy.relations 'path'
SameNames @($taskRelations.Keys) $taskPayloads 'copy38 membership'
$taskCopyAfter=Names $taskCopy.author_after 'path'
SameNames @($taskCopyAfter.Keys) $taskPayloads 'copy after38 membership'
foreach($taskName in $taskPayloads) {
    $taskRelation=$taskRelations[$taskName]
    Need ($taskRelation.author_path -ceq (Join-Path $taskParents[0] $taskName) -and $taskRelation.independent_path -ceq (Join-Path $taskParents[1] $taskName)) 'fixed copy paths'
    SameBinding $taskRelation.author $taskPinMaps[0][$taskName] 'copy source'
    SameBinding $taskRelation.independent $taskPinMaps[1][$taskName] 'copy destination'
    SameBinding $taskCopyAfter[$taskName] $taskPinMaps[0][$taskName] 'copy after source'
    Yes $taskCopyAfter[$taskName].unchanged 'copy after unchanged'
    Need ($taskRelation.child_input -eq ($taskName -in $taskPayloads[0..34])) 'copy child membership'
    if($taskName -eq 'run_preflight01.ps1') { Need ($taskRelation.relation -ceq 'five_fixed_label_replacements') 'launcher relation' }
    else { Need ($taskRelation.relation -ceq 'exact_bytes') 'exact relation'; SameBinding $taskRelation.author $taskRelation.independent 'exact copy bytes' }
}
$taskAuthorLauncher=Text (Join-Path $taskParents[0] 'run_preflight01.ps1')
$taskIndependentLauncher=Text (Join-Path $taskParents[1] 'run_preflight01.ps1')
Need (([regex]::Matches($taskAuthorLauncher,[regex]::Escape($taskLabels[0]))).Count -eq 5 -and $taskAuthorLauncher.Replace($taskLabels[0],$taskLabels[1]) -ceq $taskIndependentLauncher) 'exact five-label-only launcher delta'
SameBinding $taskCopy.author_pins (HashText (Join-Path $taskParents[0] 'PINS.json')) 'copy author pins'
SameBinding $taskCopy.independent_pins (HashText (Join-Path $taskParents[1] 'PINS.json')) 'copy independent pins'
SameBinding $taskCopy.reviewed_launcher (HashText (Join-Path $taskParents[1] 'run_preflight01.ps1')) 'copy reviewed launcher'
foreach($taskFlag in @('all_author_inputs_unchanged','all35_child_bytes_identical','original22_order_unchanged')) { Yes $taskCopy.$taskFlag ('copy flag '+$taskFlag) }
$taskBoundInputs=@()
foreach($taskPath in @($taskReadBindings.Keys | Sort-Object)) {
    $taskBefore=$taskReadBindings[$taskPath]
    $taskAfter=HashText $taskPath
    SameBinding $taskBefore $taskAfter 'final read-only binding'
    $taskBoundInputs+=[ordered]@{path=$taskPath;bytes=$taskAfter.bytes;sha256=$taskAfter.sha256}
}
$taskResult=[ordered]@{schema='interrupted-fake28-independent-passive-review-v1';verdict='PASS';candidate_rerun=$false;scope='retained text only; fake-service observations, no native/restart/model qualification';runs=$taskRunResults;exact_ordered_case_objects_equal=$true;all35_child_hashes_equal=$true;original22_order_preserved=$true;original_four_test_pins_preserved=$true;copy_payloads=38;copy_exact=37;copy_launcher_label_only=1;all_read_texts_unchanged=$true;read_bindings=$taskBoundInputs}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes((Canon $taskResult))
$taskStream=[IO.File]::Open($taskOut,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $taskStream.Write($taskBytes,0,$taskBytes.Length); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
Write-Output ('PASS: both28/0/0; 57 passing subtests each; exact cases,35 child hashes,38 payloads,3 controls,46 run files; passive text only.')
