$ErrorActionPreference = 'Stop'
$taskBase = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskReview = Join-Path $taskBase 'interrupted-owner-prelock-fake30-receipt-peer03'
$taskReads = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
function Demand([bool]$condition, [string]$reason) { if (-not $condition) { throw $reason } }
function File-Data([string]$path) {
    if ($taskReads.ContainsKey($path)) { return $taskReads[$path] }
    $item = Get-Item -LiteralPath $path
    Demand (-not $item.PSIsContainer -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -and $item.Length -le 1048576) 'Bounded flat text required'
    $bytes = [IO.File]::ReadAllBytes($path)
    $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    $row = [pscustomobject]@{bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant();text=$text}
    $taskReads.Add($path, $row)
    return $row
}
function Json-Data([string]$path) { return ((File-Data $path).text | ConvertFrom-Json) }
function Canon($value) { return ConvertTo-Json -InputObject $value -Depth 30 -Compress }
function Equal-Names($left, $right) { return (Canon @($left)) -ceq (Canon @($right)) }
function Same-Binding($left, $right, [string]$reason) { Demand ($left.bytes -eq $right.bytes -and $left.sha256 -ceq $right.sha256) $reason }
$taskSpecs = @(
    @{dir='interrupted-owner-prelock-fake30-author03';label='interrupted-owner-prelock-fake03';actual='INTERRUPTED-PRELOCK30-AUTHOR-RUN-ACTUAL.json';chunk='c3d9f3';pins='f70f8f0ad7f1ad634939d91f04096996852cfe700c41829a492b00df883c1851'},
    @{dir='interrupted-owner-prelock-fake30-confirmation03';label='prelock-retirement-confirmation03';actual='INTERRUPTED-PRELOCK30-CONFIRMATION-RUN-ACTUAL.json';chunk='01d8d4';pins='8cd78502de3f77aa5ce22e0060a19d7a7911881f63f2f389487c077ea6055e30'}
)
$taskLegacyPath = Join-Path $taskBase 'interrupted-retirement-fake28-author01\interrupted-retirement-fake01\stdout.json'
$taskLegacy = Json-Data $taskLegacyPath
Demand ($taskLegacy.count -eq 28 -and $taskLegacy.passed -eq 28 -and $taskLegacy.failed -eq 0 -and $taskLegacy.skipped -eq 0 -and $taskLegacy.qualification_exit -eq 0) 'Legacy receipt counts'
$taskGuardNames = @('startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','real_entrypoints_unchanged')
$taskControlNames = @('PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1')
$taskScope = 'Original28 plus two controller prelock cases; fake Windows services only; native interruption, restart and model behavior unmeasured'
$taskRuns = [Collections.Generic.List[object]]::new()
$taskCaseObjects = [Collections.Generic.List[object]]::new()
$taskChildHashes = [Collections.Generic.List[object]]::new()
foreach ($spec in $taskSpecs) {
    $prep = Join-Path $taskBase $spec.dir; $run = Join-Path $prep $spec.label
    $actualPath = Join-Path $taskBase $spec.actual; $actual = Json-Data $actualPath
    Demand ($actual.exit_code -eq 0 -and $actual.chunk_id -ceq $spec.chunk -and -not $actual.session_id) 'Actual completed outer exit'
    Demand ($actual.output -ceq ($spec.label + ": 30 passed, 0 failed, 0 skipped; generated scope only.`r`n")) 'Actual outer output'
    $pinsData = File-Data (Join-Path $prep 'PINS.json'); $pins = Json-Data (Join-Path $prep 'PINS.json')
    Demand ($pinsData.sha256 -ceq $spec.pins -and $pins.finalized -eq $true -and $pins.files.Count -eq 39) 'Frozen39 pins'
    $names = @($pins.files.path)
    Demand (@($names | Sort-Object -Unique).Count -eq 39) 'Unique pin names'
    foreach ($name in $names) { Demand ($name -cmatch '^[A-Za-z0-9_.-]+$') 'Flat pinned name' }
    $expectedFiles = @($names + @('PINS.json','ROOT-ADMISSION.json','plan.json','native-exit.json','input-check.json','stdout.json','stderr.log','exit.json') | Sort-Object)
    $actualFiles = @(Get-ChildItem -LiteralPath $run -Force | Select-Object -ExpandProperty Name | Sort-Object)
    Demand ($actualFiles.Count -eq 47 -and (Equal-Names $actualFiles $expectedFiles)) 'Exact47 output membership'
    foreach ($row in $pins.files) {
        Same-Binding (File-Data (Join-Path $prep $row.path)) $row ('Original pin: ' + $row.path)
        Same-Binding (File-Data (Join-Path $run $row.path)) $row ('Copied pin: ' + $row.path)
    }
    foreach ($name in $taskControlNames) { Same-Binding (File-Data (Join-Path $prep $name)) (File-Data (Join-Path $run $name)) ('Control copy: ' + $name) }
    $admission = Json-Data (Join-Path $run 'ROOT-ADMISSION.json')
    Demand ($admission.approved -eq $true -and $admission.label -ceq $spec.label -and $admission.pins_sha256 -ceq $spec.pins -and $admission.scope -ceq 'generated_bytes_and_fake_ports_only' -and $admission.admission_commit -ceq '7316e53a32fd217021d4ba05607ae471f928358b') 'Admission binding'
    $result = Json-Data (Join-Path $run 'stdout.json'); $exit = Json-Data (Join-Path $run 'exit.json'); $native = Json-Data (Join-Path $run 'native-exit.json')
    $plan = Json-Data (Join-Path $run 'plan.json'); $check = Json-Data (Join-Path $run 'input-check.json'); $expected = Json-Data (Join-Path $run 'EXPECTED-CASES.json')
    Demand ($result.schema -ceq 'uoink.windows-reservation-fake-preflight.v1' -and $result.scope -ceq $taskScope -and $result.qualification_exit -eq 0 -and $exit.native_exit -eq 0 -and $native.native_exit -eq 0 -and $exit.qualification_exit -eq 0) 'Recorded qualification/native exits and scope'
    foreach ($outcome in @($result,$exit)) { Demand ($outcome.passed -eq 30 -and $outcome.failed -eq 0 -and $outcome.skipped -eq 0 -and $outcome.membership_valid -eq $true) 'Recorded pass counts' }
    Demand ($result.count -eq 30 -and $result.guard_valid -eq $true -and $exit.valid -eq $true -and $exit.guards_valid -eq $true -and $exit.inputs_unchanged -eq $true -and $check.inputs_unchanged -eq $true) 'Outcome validity'
    Demand (Equal-Names @($result.guards.psobject.Properties.Name | Sort-Object) @($taskGuardNames | Sort-Object)) 'Exact ten guards'
    foreach ($guard in $result.guards.psobject.Properties) { Demand ($guard.Value -is [bool] -and $guard.Value) ('True guard: ' + $guard.Name) }
    Demand ($result.metadata_trap_count -eq 12 -and $result.registry_trap_count -eq 25 -and $result.guard_denials.Count -eq 0 -and $result.registry_denials.Count -eq 0 -and $result.heavy_roots_loaded.Count -eq 0) 'Trap/denial/heavy-import observations'
    Demand ($expected.Count -eq 30 -and (Equal-Names $result.expected_cases $expected) -and (Equal-Names @($result.cases.id) $expected)) 'Exact ordered30 case membership'
    Demand ((Canon @($result.cases[0..27])) -ceq (Canon @($taskLegacy.cases))) 'Original28 complete case objects'
    $subtests = 0
    foreach ($case in $result.cases) {
        Demand ($case.passed -eq $true -and $case.skipped -eq $false -and $case.errors.Count -eq 0 -and $case.subtests.Count -le 64) 'Case success and bounded subtests'
        foreach ($sub in $case.subtests) { Demand ($sub.passed -eq $true -and $sub.id.StartsWith($case.id + ' (')) 'Subtest success and parent' }
        $subtests += $case.subtests.Count
    }
    Demand ($subtests -eq 62 -and $result.cases[28].subtests.Count -eq 0 -and $result.cases[29].subtests.Count -eq 5) '62 subtests with five prelock negatives'
    $childNames = @($names | Where-Object { $_.EndsWith('.py') -or $_ -ceq 'EXPECTED-CASES.json' } | Sort-Object)
    Demand ($childNames.Count -eq 36 -and (Equal-Names @($result.input_sha256.psobject.Properties.Name | Sort-Object) $childNames)) 'Exact36 child hashes'
    foreach ($name in $childNames) { Demand ($result.input_sha256.$name -ceq (File-Data (Join-Path $run $name)).sha256) ('Child hash: ' + $name) }
    Demand ($check.inputs.Count -eq 39 -and $plan.before.Count -eq 39 -and (Equal-Names @($check.inputs.name) $names) -and (Equal-Names @($plan.before.name) $names)) 'Exact39 before/after rows'
    for ($i=0; $i -lt 39; $i++) {
        $pin=$pins.files[$i]; $after=$check.inputs[$i]
        Demand ($after.unchanged -eq $true) 'Recorded source unchanged'
        Same-Binding $plan.before[$i] $pin 'Recorded pre-start binding'
        Same-Binding $after.original $pin 'Recorded post original binding'
        Same-Binding $after.copy $pin 'Recorded post copied binding'
    }
    Demand ($plan.controls.Count -eq 3 -and $check.controls.Count -eq 3 -and (Equal-Names @($plan.controls.name) $taskControlNames) -and (Equal-Names @($check.controls.name) $taskControlNames)) 'Exact3 control rows'
    for ($i=0; $i -lt 3; $i++) {
        $data=File-Data (Join-Path $prep $taskControlNames[$i]); $after=$check.controls[$i]
        Demand ($after.unchanged -eq $true) 'Recorded control unchanged'
        Same-Binding $plan.controls[$i].binding $data 'Recorded pre-control binding'
        Same-Binding $after.original $data 'Recorded post original control'
        Same-Binding $after.copy $data 'Recorded post copied control'
    }
    Demand ($plan.schema -ceq 'uoink.windows-reservation-fake-launch.v1' -and $plan.label -ceq $spec.label -and $plan.python -ceq 'C:\Python314\python.exe' -and $plan.startup_binding_set -eq $true -and $plan.scope -ceq 'generated_bytes_and_fake_ports_only') 'Plan scope and startup'
    Demand ($plan.arguments.Count -eq 4 -and (Equal-Names @($plan.arguments[0..2]) @('-I','-S','-B')) -and $plan.arguments[3] -ceq (Join-Path $run 'qualify_windows_reservations.py')) 'Exact recorded isolated child arguments'
    $stdout=File-Data (Join-Path $run 'stdout.json'); $stderr=File-Data (Join-Path $run 'stderr.log')
    Demand ($stdout.bytes -le 262144 -and $stdout.bytes -eq $exit.stdout_bytes -and $stderr.bytes -eq 0 -and $exit.stderr_bytes -eq 0) 'Stream bounds and empty stderr'
    $taskCaseObjects.Add($result.cases); $taskChildHashes.Add($result.input_sha256)
    $taskRuns.Add([ordered]@{directory=$spec.dir;label=$spec.label;actual=$spec.chunk;actual_sha256=(File-Data $actualPath).sha256;outer_exit=0;outer_elapsed_seconds=$actual.wall_time_seconds;launcher_elapsed_seconds=$exit.elapsed_seconds;case_elapsed_seconds=$result.elapsed_seconds;passed=30;failed=0;skipped=0;passing_subtests=$subtests;original28_complete_objects_unchanged=$true;source_pairs=39;control_pairs=3;output_files=47;child_hashes=36;all_ten_guards_true=$true;metadata_traps=12;registry_traps=25;denials=0;stderr_bytes=0;stdout_bytes=$stdout.bytes;stdout_sha256=$stdout.sha256;pins_sha256=$pinsData.sha256})
}
Demand ((Canon $taskCaseObjects[0]) -ceq (Canon $taskCaseObjects[1])) 'Independent complete case objects equality'
Demand ((Canon $taskChildHashes[0]) -ceq (Canon $taskChildHashes[1])) 'Independent child hash map equality'
foreach ($entry in $taskReads.GetEnumerator()) { Same-Binding ([pscustomobject]@{bytes=(Get-Item -LiteralPath $entry.Key).Length;sha256=(Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash.ToLowerInvariant()}) $entry.Value 'Final passive input unchanged' }
$taskReport = [ordered]@{status='PASS';scope='Independent passive saved fake30 receipts and fixed text bindings only';candidate_executed=$false;copies=$taskRuns.ToArray();complete_case_objects_equal=$true;child_hash_maps_equal=$true;fixed_texts_read=$taskReads.Count;all_review_inputs_unchanged=$true;legacy_stdout_sha256=(File-Data $taskLegacyPath).sha256}
$taskReportText = ConvertTo-Json -InputObject $taskReport -Depth 12
$taskOutput = Join-Path $taskReview 'RESULT.json'
$taskBytes = [Text.UTF8Encoding]::new($false).GetBytes($taskReportText + "`n")
$taskStream = [IO.FileStream]::new($taskOutput,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $taskStream.Write($taskBytes,0,$taskBytes.Length); $taskStream.Flush($true) } finally { $taskStream.Dispose() }
$taskReportText
