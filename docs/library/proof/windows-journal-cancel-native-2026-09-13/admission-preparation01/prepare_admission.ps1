param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256)
$ErrorActionPreference='Stop'
$repo='E:\AI\projects\uoink\checkouts\Yoink-library'
$prep='_scratch/journal-cancel-native-admission-preparation01'
$proposal='_scratch/windows-journal-cancel-proposal01'
$oldProposal='_scratch/windows-reservation-writer-exclusion-proposal04'
$proof='docs/library/proof/windows-journal-cancel-qualification-2026-09-13'
$run=Join-Path $repo '_scratch/windows-journal-cancel01'
$output=Join-Path $repo ($proposal+'/ROOT-ADMISSION-cancel.json')
$utf8=[Text.UTF8Encoding]::new($false,$true)
function Require($value,[string]$reason) { if(-not $value) {throw $reason} }
function Chain([string]$path) {
    $item=Get-Item -LiteralPath $path -Force
    Require (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Reparse input refused'
    $dir=if($item.PSIsContainer){[IO.DirectoryInfo]::new($item.FullName)}else{[IO.DirectoryInfo]::new($item.DirectoryName)}
    while($null -ne $dir) {
        $part=Get-Item -LiteralPath $dir.FullName -Force
        Require ($part.PSIsContainer -and ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Unsafe ancestor'
        $dir=$dir.Parent
    }
}
function Read-Fixed([string]$relative,[long]$length,[string]$sha) {
    Require ($relative -cmatch '^[A-Za-z0-9_./-]+$' -and $relative -notmatch '(^/|(^|/)\.\.?(/|$)|//)') 'Noncanonical text path'
    Require ([IO.Path]::GetExtension($relative) -cin @('.py','.ps1','.md','.json')) 'Non-text path'
    $path=Join-Path $repo $relative
    Chain $path
    $before=Get-Item -LiteralPath $path -Force
    Require (-not $before.PSIsContainer -and $length -ge 0 -and $length -le 1048576 -and $before.Length -eq $length) 'Text input size'
    $raw=[IO.File]::ReadAllBytes($path)
    Require ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant() -ceq $sha) 'Text input hash'
    $text=$utf8.GetString($raw)
    Require (-not ($raw -contains 0)) 'NUL in text input'
    Chain $path
    $after=Get-Item -LiteralPath $path -Force
    Require ($after.Length -eq $before.Length -and $after.LastWriteTimeUtc.Ticks -eq $before.LastWriteTimeUtc.Ticks) 'Text changed during read'
    return $text
}
Require ($PSCommandPath -ceq (Join-Path $repo ($prep+'/prepare_admission.ps1'))) 'Fixed script path'
$selfLength=(Get-Item -LiteralPath $PSCommandPath).Length
$null=Read-Fixed ($prep+'/prepare_admission.ps1') $selfLength $ExpectedScriptSha256
$pins=Read-Fixed ($prep+'/INPUT-BINDINGS.json') 9508 '5eace362057b19cf1f6c1a7d3e6545f212457f6b5ac4e08e36dca783e2c13aad' | ConvertFrom-Json -AsHashtable
Require ($pins.schema -ceq 'uoink.journal-cancel.native-admission-text-inputs.v1' -and $pins.files.Count -eq 44) 'Fixed preparation membership'
$texts=@{}
foreach($row in $pins.files) {
    Require (-not $texts.ContainsKey($row.source)) 'Duplicate preparation input'
    $texts[$row.source]=Read-Fixed $row.source $row.bytes $row.sha256
}
$map=$texts[$proposal+'/SOURCE-INPUTS.json'] | ConvertFrom-Json -AsHashtable
$old=$texts[$oldProposal+'/SOURCE-INPUTS.json'] | ConvertFrom-Json -AsHashtable
$preservation=$texts[$proposal+'/SOURCE-PRESERVATION.json'] | ConvertFrom-Json -AsHashtable
$template=$texts[$proposal+'/ROOT-ADMISSION-TEMPLATE.json'] | ConvertFrom-Json -AsHashtable
$seal=$texts[$proof+'/SHA256.json'] | ConvertFrom-Json -AsHashtable
Require ($map.source_sha256.Count -eq 18 -and $map.source_paths.Count -eq 18 -and $old.source_sha256.Count -eq 18) 'Fixed source membership'
$same=0
foreach($name in $map.source_sha256.Keys) {
    Require ($name -cmatch '^[a-z0-9_]+\.py$' -and $map.source_paths[$name] -ceq (Join-Path $repo ($proposal+'/'+$name))) 'Fixed source path'
    $rows=@($pins.files | Where-Object {$_.source -ceq ($proposal+'/'+$name)})
    Require ($rows.Count -eq 1 -and $rows[0].sha256 -ceq $map.source_sha256[$name]) 'Pinned source agreement'
    if($name -cnotin @('generated_adapter_flow.py','dummy_bootstrap.py')) {
        $oldRows=@($pins.files | Where-Object {$_.source -ceq ($oldProposal+'/'+$name)})
        Require ($oldRows.Count -eq 1 -and $oldRows[0].sha256 -ceq $map.source_sha256[$name] -and $old.source_sha256[$name] -ceq $map.source_sha256[$name]) 'Writer04 source preservation'
        $same++
    }
}
Require ($same -eq 16 -and $preservation.unchanged_source_count -eq 16 -and $preservation.sources.Count -eq 18) 'Preservation count'
Require ($map.source_sha256['dummy_bootstrap.py'] -ceq 'ed99209c7da9bb98faf960999a38667bd5e96b75bae1e0542d69733b62cc593c') 'Bootstrap pin'
Require ($map.source_sha256['generated_adapter_flow.py'] -ceq 'cc0b7ff4f445ef73b4acdc63475c1aa375b5d0cfbe461ee6c50809cd0f19b4b4') 'Qualified adapter pin'
foreach($side in @('author','independent')) {
    $member=$side+'/generated_adapter_flow.py'
    $records=@($seal.files | Where-Object {$_.path -ceq $member})
    Require ($records.Count -eq 1 -and $records[0].bytes -eq 33890 -and $records[0].sha256 -ceq $map.source_sha256['generated_adapter_flow.py']) 'Adapter proof membership'
    Require ($texts[$proof+'/'+$member] -ceq $texts[$proposal+'/generated_adapter_flow.py']) 'Adapter proof bytes'
}
# These strings are compared as JSON metadata only; no support path is opened or queried.
$nativeNames=@('C:\Python314\python.exe','C:\Python314\python314.dll','C:\Python314\python3.dll','C:\Python314\DLLs\_ctypes.pyd','C:\Python314\DLLs\libffi-8.dll','C:\Windows\System32\kernel32.dll','C:\Python314\Lib\ctypes\__init__.py','C:\Python314\Lib\ctypes\_layout.py','C:\Python314\Lib\ctypes\_endian.py')
Require ($map.native_bindings.Count -eq 9 -and $old.native_bindings.Count -eq 9) 'Support metadata membership'
foreach($name in $nativeNames) {
    Require ($map.native_bindings.Contains($name) -and $old.native_bindings.Contains($name)) 'Fixed support metadata path'
    Require ($map.native_bindings[$name].bytes -eq $old.native_bindings[$name].bytes -and $map.native_bindings[$name].sha256 -ceq $old.native_bindings[$name].sha256) 'Unchanged support metadata'
}
Require ($template.root_reviewed -is [bool] -and $template.root_reviewed -eq $false -and $template.native_execution_admitted -is [bool] -and $template.native_execution_admitted -eq $false) 'False template required'
Require ($template.scope -ceq 'generated-windows-journal-cancel-only' -and $template.case -ceq 'positive' -and $template.operation_mode -ceq 'cancel' -and $template.run_path -ceq $run) 'Fixed admission scope'
Require ($template.source_inputs_sha256 -ceq 'f5e1b8b4d282c28c7ac12aad05b4e2466340769215574948682b69633e4fa4b3' -and $template.launcher_sha256 -ceq '70ab9cc3879ed792db0f8deaec4fd343f6a96438811bad9e37977ae510fa11d6') 'Fixed admission pins'
Chain (Join-Path $repo $proposal)
Chain ([IO.Path]::GetDirectoryName($run))
Require (-not (Test-Path -LiteralPath $run) -and -not (Test-Path -LiteralPath $output)) 'Fresh run and absent admission required'

# Sole mutation: root executing this reviewed script creates the fresh admission, never a run.
$admission=[ordered]@{
    root_reviewed=$true
    scope=$template.scope
    case=$template.case
    operation_mode=$template.operation_mode
    run_path=$template.run_path
    source_inputs_sha256=$template.source_inputs_sha256
    launcher_sha256=$template.launcher_sha256
    native_execution_admitted=$true
    note='Root admits one fresh generated native journal-cancellation observation after the exact source review and two fake89 qualifications. Preserve all failures; no retry. No real asset, D2 conversion, model, network or release authorization is added.'
    root_review_sha256='cf115f87231338b23bc880fb074259f95a3931449a0f7774d56545880746d701'
    fake_qualification_manifest_sha256='635ae8077f66006140df1bcee544bbd2ca086cfc121a909d53f4d18206a8dc5f'
    preparation_inputs_sha256='5eace362057b19cf1f6c1a7d3e6545f212457f6b5ac4e08e36dca783e2c13aad'
    preparation_script_sha256=$ExpectedScriptSha256
}
$raw=$utf8.GetBytes(($admission | ConvertTo-Json -Depth 4)+"`n")
Require ($raw.Length -le 4096) 'Admission cap'
$stream=[IO.FileStream]::new($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None,4096,[IO.FileOptions]::WriteThrough)
try {$stream.Write($raw,0,$raw.Length);$stream.Flush($true)}finally{$stream.Dispose()}
$admissionHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw)).ToLowerInvariant()
$null=Read-Fixed ($proposal+'/ROOT-ADMISSION-cancel.json') $raw.Length $admissionHash
foreach($row in $pins.files){$null=Read-Fixed $row.source $row.bytes $row.sha256}
$null=Read-Fixed ($prep+'/INPUT-BINDINGS.json') 9508 '5eace362057b19cf1f6c1a7d3e6545f212457f6b5ac4e08e36dca783e2c13aad'
$null=Read-Fixed ($prep+'/prepare_admission.ps1') $selfLength $ExpectedScriptSha256
Require (-not (Test-Path -LiteralPath $run)) 'Run appeared during preparation'
[ordered]@{created_admission=$output;bytes=$raw.Length;sha256=$admissionHash;source_count=18;unchanged_writer04_count=16;support_metadata_records=9;support_files_inspected=$false;false_template_preserved=$true;inputs_unchanged=$true;native_launched=$false} | ConvertTo-Json
