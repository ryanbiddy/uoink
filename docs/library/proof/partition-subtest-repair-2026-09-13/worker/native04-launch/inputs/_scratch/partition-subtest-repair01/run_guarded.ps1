param([Parameter(Mandatory=$true)][ValidateSet('native02','unit01','native03','native04','unit02','unit03','collect01','pass01')][string]$Mode)
$ErrorActionPreference = 'Stop'
$partitionRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$partitionRepair = Join-Path $partitionRoot '_scratch\partition-subtest-repair01'
$partitionLaunch = Join-Path $partitionRepair ($Mode + '-launch')
if (Test-Path -LiteralPath $partitionLaunch) { throw 'Refuse reused launch directory' }
New-Item -ItemType Directory -Path $partitionLaunch | Out-Null
Get-ChildItem Env: | Where-Object { $_.Name -match 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL' -or $_.Name -match '^(ANTHROPIC|CLAUDE_CODE|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:SUBTEST_PROBE_RECEIPT = Join-Path $partitionRepair ($Mode + '-probe')
$env:IG_PARTITION_RECEIPT_PATH = Join-Path $partitionRepair ($Mode + '-partition')
$partitionSelectors = switch ($Mode) {
    'native02' { @('_scratch/partition-subtest-repair01/test_native_semantics.py') }
    'native03' { @('_scratch/partition-subtest-repair01/test_native_semantics.py','_scratch/partition-subtest-repair01/test_guard_activation.py') }
    'native04' { @('_scratch/partition-subtest-repair01/test_native_semantics.py','_scratch/partition-subtest-repair01/test_guard_activation.py') }
    'collect01' { @('_scratch/partition-subtest-repair01/test_native_semantics.py') }
    'pass01' { @('_scratch/partition-subtest-repair01/test_native_semantics.py::TestUnittestSubtests::test_pass_repeated','_scratch/partition-subtest-repair01/test_native_semantics.py::test_pytest_pass','_scratch/partition-subtest-repair01/test_guard_activation.py') }
    'unit01' { @('_scratch/test_partition_exit_contract.py','_scratch/partition-subtest-repair01/test_subtest_contract.py') }
    'unit02' { @('_scratch/test_partition_exit_contract.py','_scratch/partition-subtest-repair01/test_subtest_contract.py','_scratch/test_mirror_state_receipt_plugin.py') }
    'unit03' { @('_scratch/test_partition_exit_contract.py','_scratch/partition-subtest-repair01/test_subtest_contract.py','_scratch/test_mirror_state_receipt_plugin.py') }
}
$partitionCommand = @('-B','_scratch/integrator_verify.py','--root',$partitionRoot,'--label',('partition-subtest-'+$Mode)) + $partitionSelectors + @('--runxfail','-p','_scratch.partition_receipt_plugin')
if ($Mode -in @('native03','native04','unit02','unit03','collect01','pass01')) {
    $env:AGW_HEAVY_GUARD_RECEIPT = Join-Path $partitionRepair ($Mode + '-heavy.json')
    $partitionCommand += @('-p','_scratch.agw_heavy_import_guard')
}
if ($Mode -in @('native03','native04','pass01')) {
    $env:IG_MIRROR_STATE_RECEIPT_PATH = Join-Path $partitionRepair ($Mode + '-mirror.jsonl')
    $partitionCommand += @('-p','_scratch.mirror_state_receipt_plugin')
}
if ($Mode -eq 'collect01') { $partitionCommand += '--collect-only' }
$partitionInputs = @('_scratch/partition-subtest-repair01/conftest.py','_scratch/partition-subtest-repair01/run_guarded.ps1','_scratch/partition_receipt_plugin.py','_scratch/partition_exit_contract.py','_scratch/integrator_verify.py','_scratch/run_partitioned_mirror_tree09.py','_scratch/seal_partitioned_mirror_tree09.py','_scratch/mirror_state_receipt_plugin.py','_scratch/agw_heavy_import_guard.py') + @($partitionSelectors | ForEach-Object { ($_ -split '::')[0] } | Select-Object -Unique)
$partitionHashes = @{}
foreach ($partitionInput in $partitionInputs) {
    $partitionSource = Join-Path $partitionRoot $partitionInput
    $partitionHashes[$partitionInput] = (Get-FileHash -LiteralPath $partitionSource -Algorithm SHA256).Hash.ToLower()
    $partitionSaved = Join-Path $partitionLaunch ('inputs\' + $partitionInput)
    New-Item -ItemType Directory -Path (Split-Path -Parent $partitionSaved) -Force | Out-Null
    Copy-Item -LiteralPath $partitionSource -Destination $partitionSaved
}
@{ command = @((Join-Path $partitionRoot '_scratch\ig-native\Scripts\python.exe')) + $partitionCommand; inputs=$partitionHashes; scope='Inert subtest receipt diagnosis only' } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $partitionLaunch 'plan.json') -Encoding utf8
Set-Location -LiteralPath $partitionRoot
& (Join-Path $partitionRoot '_scratch\ig-native\Scripts\python.exe') @partitionCommand 2>&1 | Tee-Object -FilePath (Join-Path $partitionLaunch 'launcher.log')
$partitionExit = $LASTEXITCODE
$partitionAfter = @{}
foreach ($partitionInput in $partitionInputs) { $partitionAfter[$partitionInput] = (Get-FileHash -LiteralPath (Join-Path $partitionRoot $partitionInput) -Algorithm SHA256).Hash.ToLower() }
@{ exit=$partitionExit; after_inputs=$partitionAfter } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $partitionLaunch 'result.json') -Encoding utf8
exit $partitionExit
