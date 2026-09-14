param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256)
# Root must review these bytes and integrate the fake qualification archive before invocation.
# This script writes one generated observation admission; it never launches its subject.
$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$prep='_scratch/retired-recovery-native-admission-preparation01'
$proposal='_scratch/windows-retired-owner-recovery-proposal01'
$old='_scratch/windows-journal-cancel-proposal01'
$run=Join-Path $repo '_scratch/windows-retired-owner-recovery01'
$output=Join-Path $repo ($proposal+'/ROOT-ADMISSION-cancel.json')
$utf8=[Text.UTF8Encoding]::new($false,$true)
function Require($ok,[string]$why){if(-not $ok){throw $why}}
function Chain([string]$path){
    $item=Get-Item -LiteralPath $path -Force
    Require (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse input refused'
    $dir=if($item.PSIsContainer){[IO.DirectoryInfo]::new($item.FullName)}else{[IO.DirectoryInfo]::new($item.DirectoryName)}
    while($null -ne $dir){
        $part=Get-Item -LiteralPath $dir.FullName -Force
        Require ($part.PSIsContainer -and ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Unsafe ancestor'
        $dir=$dir.Parent
    }
}
function Read-Fixed([string]$relative,[long]$length,[string]$sha){
    Require ($relative -cmatch '^[A-Za-z0-9_./-]+$' -and $relative -notmatch '(^/|(^|/)\.\.?(/|$)|//)' -and [IO.Path]::GetExtension($relative) -cin @('.py','.ps1','.md','.json')) 'Fixed relative text path required'
    $path=Join-Path $repo $relative
    Chain $path
    $before=Get-Item -LiteralPath $path -Force
    Require (-not $before.PSIsContainer -and $length -ge 0 -and $length -le 1048576 -and $before.Length -eq $length -and $sha -cmatch '^[0-9a-f]{64}$') 'Text input bound'
    $raw=[IO.File]::ReadAllBytes($path)
    Require ($raw.Length -eq $length -and [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant() -ceq $sha -and -not ($raw -contains 0)) 'Text input hash or NUL mismatch'
    $text=$utf8.GetString($raw)
    Chain $path
    $after=Get-Item -LiteralPath $path -Force
    Require ($after.Length -eq $before.Length -and $after.LastWriteTimeUtc.Ticks -eq $before.LastWriteTimeUtc.Ticks) 'Input changed during read'
    return $text
}
Require ($PSCommandPath -ceq (Join-Path $repo ($prep+'/prepare_admission.ps1'))) 'Fixed preparation script required'
$selfLength=(Get-Item -LiteralPath $PSCommandPath).Length
$null=Read-Fixed ($prep+'/prepare_admission.ps1') $selfLength $ExpectedScriptSha256
$bindingsSha='7e275d9fa0a0b1ce29fb76353b465bd30adb4e42a1ff4d721f109ad457a291ff'
$pins=Read-Fixed ($prep+'/INPUT-BINDINGS.json') 5339 $bindingsSha | ConvertFrom-Json -AsHashtable
$allowed=@(
    '_scratch/windows-retired-owner-recovery-proposal01/reservation_file_port.py',
    '_scratch/windows-retired-owner-recovery-proposal01/snapshot_reservations.py',
    '_scratch/windows-retired-owner-recovery-proposal01/snapshot_lifecycle.py',
    '_scratch/windows-retired-owner-recovery-proposal01/durable_lifecycle.py',
    '_scratch/windows-retired-owner-recovery-proposal01/win32_worker_connection.py',
    '_scratch/windows-retired-owner-recovery-proposal01/windows_reservation_port.py',
    '_scratch/windows-retired-owner-recovery-proposal01/owned_generation_protocol.py',
    '_scratch/windows-retired-owner-recovery-proposal01/win32_private_pipe.py',
    '_scratch/windows-retired-owner-recovery-proposal01/pinned_buffer_namespace.py',
    '_scratch/windows-retired-owner-recovery-proposal01/inherited_readset.py',
    '_scratch/windows-retired-owner-recovery-proposal01/generated_worker_flow.py',
    '_scratch/windows-retired-owner-recovery-proposal01/generated_operation_flow.py',
    '_scratch/windows-retired-owner-recovery-proposal01/trusted_asr_resolver.py',
    '_scratch/windows-retired-owner-recovery-proposal01/asr_loading_adapter.py',
    '_scratch/windows-retired-owner-recovery-proposal01/generated_adapter_flow.py',
    '_scratch/windows-retired-owner-recovery-proposal01/generated_journal_setup.py',
    '_scratch/windows-retired-owner-recovery-proposal01/generated_writer_exclusion.py',
    '_scratch/windows-retired-owner-recovery-proposal01/dummy_bootstrap.py',
    '_scratch/windows-retired-owner-recovery-proposal01/SOURCE-INPUTS.json',
    '_scratch/windows-retired-owner-recovery-proposal01/run_retired_recovery01.ps1',
    '_scratch/windows-retired-owner-recovery-proposal01/ROOT-ADMISSION-TEMPLATE.json',
    '_scratch/windows-journal-cancel-proposal01/SOURCE-INPUTS.json',
    'docs/library/ASTRA-RETIRED-OWNER-FAKE22-VERDICT-2026-09-13.md',
    '_scratch/RETIRED-RECOVERY-PAIR-CHECK-ACTUAL.json',
    '_scratch/windows-retired-owner-native-source-review01/VERDICT.md'
)
Require ($pins.schema -ceq 'uoink.retired-recovery.native-admission-text-inputs.v1' -and $pins.files.Count -eq 25 -and $allowed.Count -eq 25) 'Fixed text inventory required'
$texts=@{}
for($i=0;$i -lt 25;$i++){
    $row=$pins.files[$i]
    Require ($row.source -ceq $allowed[$i] -and -not $texts.ContainsKey($row.source)) 'Flat input membership/order differs'
    $texts[$row.source]=Read-Fixed $row.source $row.bytes $row.sha256
}
Require ($pins.files[18].sha256 -ceq '9d988684ca8dfe487521f7d711ec67855393922d53ffe3cce3e13a2c660e34c3' -and $pins.files[19].sha256 -ceq '75a9baea9307658a99217816f7653adfdbb9d0df44286a5b244ea5d3cad43444' -and $pins.files[24].sha256 -ceq '8bdcb55f5ac9a98d15a50d5b2f5d47b76e38154f9e08aa643c0c0d19cea9af03') 'Reviewed native source pins differ'
$map=$texts[$proposal+'/SOURCE-INPUTS.json'] | ConvertFrom-Json -AsHashtable
$baseline=$texts[$old+'/SOURCE-INPUTS.json'] | ConvertFrom-Json -AsHashtable
$template=$texts[$proposal+'/ROOT-ADMISSION-TEMPLATE.json'] | ConvertFrom-Json -AsHashtable
$sourceNames=@(
    'reservation_file_port.py',
    'snapshot_reservations.py',
    'snapshot_lifecycle.py',
    'durable_lifecycle.py',
    'win32_worker_connection.py',
    'windows_reservation_port.py',
    'owned_generation_protocol.py',
    'win32_private_pipe.py',
    'pinned_buffer_namespace.py',
    'inherited_readset.py',
    'generated_worker_flow.py',
    'generated_operation_flow.py',
    'trusted_asr_resolver.py',
    'asr_loading_adapter.py',
    'generated_adapter_flow.py',
    'generated_journal_setup.py',
    'generated_writer_exclusion.py',
    'dummy_bootstrap.py'
)
Require ($map.source_paths.Count -eq 18 -and $map.source_sha256.Count -eq 18) 'Exact native source membership required'
foreach($name in $sourceNames){
    $rows=@($pins.files | Where-Object {$_.source -ceq ($proposal+'/'+$name)})
    Require ($rows.Count -eq 1 -and $map.source_paths[$name] -ceq (Join-Path $repo ($proposal+'/'+$name)) -and $map.source_sha256[$name] -ceq $rows[0].sha256) 'Exact native source path/hash differs'
}
# Treat these only as dictionary keys: never open, stat, import or execute support paths here.
$nativeNames=@('C:\Python314\python.exe','C:\Python314\python314.dll','C:\Python314\python3.dll','C:\Python314\DLLs\_ctypes.pyd','C:\Python314\DLLs\libffi-8.dll','C:\Windows\System32\kernel32.dll','C:\Python314\Lib\ctypes\__init__.py','C:\Python314\Lib\ctypes\_layout.py','C:\Python314\Lib\ctypes\_endian.py')
Require ($map.native_bindings.Count -eq 9 -and $baseline.native_bindings.Count -eq 9) 'Nine support metadata rows required'
foreach($name in $nativeNames){
    Require ($map.native_bindings.Contains($name) -and $baseline.native_bindings.Contains($name) -and $map.native_bindings[$name].bytes -eq $baseline.native_bindings[$name].bytes -and $map.native_bindings[$name].sha256 -ceq $baseline.native_bindings[$name].sha256) 'Support metadata differs'
}
$pairActual=$texts['_scratch/RETIRED-RECOVERY-PAIR-CHECK-ACTUAL.json'] | ConvertFrom-Json -AsHashtable
Require ($pairActual.chunk_id -ceq 'd3c2a4' -and $pairActual.exit_code -eq 0) 'Successful fixed pair-check actual required'
$pair=$pairActual.output | ConvertFrom-Json -AsHashtable
Require ($pair.runs.Count -eq 2 -and $pair.case_objects_identical -is [bool] -and $pair.case_objects_identical -eq $true -and $pair.historical_cases_per_run -eq 12 -and $pair.new_cases_per_run -eq 10 -and $pair.native_recovery_qualified -is [bool] -and $pair.native_recovery_qualified -eq $false) 'Focused fake pair contract differs'
$runRoots=@((Join-Path $repo $proposal),(Join-Path $repo '_scratch/astra-retired-recovery-confirmation01'))
$stdoutHashes=@('056412f747a1e4e02d78f509ec7e179b6e7f8ed63a87d9cf6aca05bee0022266','957bb81b5d18c6f1ea16091fd4403c79ca0e53e502cbf159ab9dde1b6769c041')
for($i=0;$i -lt 2;$i++){
    $r=$pair.runs[$i]
    Require ($r.root -ceq $runRoots[$i] -and $r.passed -eq 22 -and $r.failed -eq 0 -and $r.skipped -eq 0 -and $r.passing_subtests -eq 21 -and $r.guards -eq 10 -and $r.metadata_traps -eq 12 -and $r.registry_traps -eq 25 -and $r.fixed_inputs -eq 26 -and $r.controls -eq 3 -and $r.child_inputs -eq 23 -and $r.stdout_bytes -eq 15257 -and $r.stdout_sha256 -ceq $stdoutHashes[$i] -and $r.native_exit -eq 0) 'Each fixed fake run must match its retained summary'
}
Require ($template.root_reviewed -is [bool] -and $template.root_reviewed -eq $false -and $template.native_execution_admitted -is [bool] -and $template.native_execution_admitted -eq $false) 'Original false template required'
Require ($template.scope -ceq 'generated-windows-retired-owner-recovery-only' -and $template.case -ceq 'positive' -and $template.operation_mode -ceq 'cancel' -and $template.run_path -ceq $run -and $template.source_inputs_sha256 -ceq $pins.files[18].sha256 -and $template.launcher_sha256 -ceq $pins.files[19].sha256) 'Fixed template scope/pins differ'
Chain (Join-Path $repo $proposal)
Chain ([IO.Path]::GetDirectoryName($run))
Require (-not (Test-Path -LiteralPath $run) -and -not (Test-Path -LiteralPath $output)) 'Fresh run and admission required'
# Sole mutation. The template remains unchanged; this creates no run directory.
$admission=[ordered]@{
    root_reviewed=$true
    scope=$template.scope
    case=$template.case
    operation_mode=$template.operation_mode
    run_path=$run
    source_inputs_sha256=$template.source_inputs_sha256
    launcher_sha256=$template.launcher_sha256
    native_execution_admitted=$true
    generated_python_interruption_only=$true
    model_execution_admitted=$false
    fetch_admitted=$false
    D3_admitted=$false
    D4_admitted=$false
    converted_output_access_admitted=$false
    os_interrupt_crash_restart_admitted=$false
    active_worker_recovery_admitted=$false
    root_fake_verdict_sha256=$pins.files[22].sha256
    fake_pair_check_actual_sha256=$pins.files[23].sha256
    native_source_verdict_sha256=$pins.files[24].sha256
    preparation_inputs_sha256=$bindingsSha
    preparation_script_sha256=$ExpectedScriptSha256
    note='Root admits one fresh generated Windows observation after source review, both fake22 qualifications and archive integration. Inject only the fixed Python KeyboardInterrupt after actual retirement; preserve failures with no retry. No model, checkpoint, converted output, fetch, D3/D4 or release authority.'
}
$raw=$utf8.GetBytes(($admission | ConvertTo-Json -Depth 4)+[char]10)
Require ($raw.Length -le 4096) 'Admission output cap'
$stream=[IO.FileStream]::new($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None,4096,[IO.FileOptions]::WriteThrough)
try{$stream.Write($raw,0,$raw.Length);$stream.Flush($true)}finally{$stream.Dispose()}
$sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
$null=Read-Fixed ($proposal+'/ROOT-ADMISSION-cancel.json') $raw.Length $sha
foreach($row in $pins.files){$null=Read-Fixed $row.source $row.bytes $row.sha256}
$null=Read-Fixed ($prep+'/INPUT-BINDINGS.json') 5339 $bindingsSha
$null=Read-Fixed ($prep+'/prepare_admission.ps1') $selfLength $ExpectedScriptSha256
Require (-not (Test-Path -LiteralPath $run)) 'Run appeared during admission preparation'
[ordered]@{created_admission=$output;bytes=$raw.Length;sha256=$sha;source_count=18;support_metadata_rows=9;support_paths_accessed=0;fake_runs=2;cases_per_run=22;subtests_per_run=21;false_template_preserved=$true;inputs_unchanged=$true;native_launched=$false} | ConvertTo-Json
