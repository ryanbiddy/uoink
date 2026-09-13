$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d1-dormant-invocation-repair01'
$taskNames=@(
    '.gitattributes','ORIGINAL-BINDINGS.json','SOURCE-REVIEW-VERDICT.md','REPAIR-BRIEF-2026-09-13.md',
    'run-root.repaired.ps1','inert_child.py','call_wrapper.ps1','qualify_wrapper.ps1',
    'QUALIFICATION01-PROTOCOL.md','run_preflight01.ps1','PREQUALIFICATION-OUTCOME-REFINEMENT.md',
    'wrapper-repair.patch.txt','qualifier-outcome-refinement.patch.txt','seal_preparation.ps1',
    'before/run-root.ps1','before/launch_d1.py','before/d1_child.py','before/PROTOCOL.md','before/SHA256.json',
    'drafts/qualify_wrapper.before-immediate-outcome.ps1','drafts/run_preflight01.before-qualifier-rebind.ps1',
    'drafts/QUALIFICATION01-PROTOCOL.before-immediate-outcome.md'
)
$taskManifest=Join-Path $taskRoot 'SHA256.json'
if(Test-Path -LiteralPath $taskManifest){throw 'Preparation seal already exists'}
$taskActual=@(Get-ChildItem -LiteralPath $taskRoot -File -Recurse -Force | ForEach-Object {[IO.Path]::GetRelativePath($taskRoot,$_.FullName).Replace('\','/')})
if(@(Compare-Object ($taskNames | Sort-Object) ($taskActual | Sort-Object)).Count -ne 0){throw 'Unexpected preparation payload membership'}
$taskFiles=@()
$taskBytes=0L
foreach($taskName in ($taskNames | Sort-Object)){
    $taskPath=Join-Path $taskRoot $taskName
    $taskSize=(Get-Item -LiteralPath $taskPath).Length
    $taskFiles += [ordered]@{path=$taskName;bytes=$taskSize;sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    $taskBytes += $taskSize
}
[ordered]@{schema='uoink.documentary-payload-manifest.v1';sealed_utc=[DateTime]::UtcNow.ToString('o');status='UNEXECUTED_WRAPPER_QUALIFICATION_PREPARATION';payload_count=$taskFiles.Count;payload_bytes=$taskBytes;planned_repair_cases=12;planned_original_diagnostics=4;owner_pins_activated=$false;actual_d1_invoked=$false;files=$taskFiles} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskManifest -Encoding utf8
foreach($taskFile in $taskFiles){
    $taskPath=Join-Path $taskRoot $taskFile.path
    if((Get-Item -LiteralPath $taskPath).Length -ne $taskFile.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskFile.sha256){throw 'Sealed preparation payload changed'}
}
$taskOriginal=Get-Content -LiteralPath (Join-Path $taskRoot 'ORIGINAL-BINDINGS.json') -Raw | ConvertFrom-Json
foreach($taskRecord in $taskOriginal){if((Get-FileHash -LiteralPath $taskRecord.source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskRecord.sha256){throw 'Original dormant proposal changed'}}
[ordered]@{payload_count=$taskFiles.Count;payload_bytes=$taskBytes;sha256_manifest=(Get-FileHash -LiteralPath $taskManifest -Algorithm SHA256).Hash.ToLowerInvariant();all_payloads_verified=$true;original_dormant_sources_unchanged=$true;qualification_executed=$false} | ConvertTo-Json
