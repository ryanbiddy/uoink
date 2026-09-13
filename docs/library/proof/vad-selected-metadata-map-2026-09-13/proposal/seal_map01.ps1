param([Parameter(Mandatory=$true)][string]$ReviewPath,[Parameter(Mandatory=$true)][string]$ReviewSha256)
$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskBase '_scratch\vad-selected-metadata-map01'
$taskProof=Join-Path $taskBase '_scratch\vad-selected-metadata-map-final-proof01'
$taskOriginal=Join-Path $taskBase '_scratch\vad-fixed-loader-proposal01'
if (Test-Path -LiteralPath $taskProof) { throw 'Proof destination already exists' }
if ((Get-FileHash -LiteralPath $ReviewPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ReviewSha256) { throw 'Review hash mismatch' }
$taskBindingsPath=Join-Path $taskOriginal 'source-bindings.json'
if ((Get-FileHash -LiteralPath $taskBindingsPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne '8dbd83213bceac5012bc342e001826902ce3a88fd420fa64f8f8d9a65366fa9c') { throw 'Original bindings changed' }
$taskBindings=Get-Content -Raw -LiteralPath $taskBindingsPath | ConvertFrom-Json
$taskKeys=@('PYANNET','SINCNET','SINC_FB','TASK','MODEL','INFERENCE','WXVAD','WXASR','GETTER','LOCK','VADPIPE','PARAMS')
$taskPlan=@()
foreach($taskFile in (Get-ChildItem -LiteralPath $taskSource -File -Recurse)) {
    $taskRelative=[IO.Path]::GetRelativePath($taskSource,$taskFile.FullName)
    if ($taskRelative.StartsWith('..')) { throw 'Noncontained task file' }
    $taskPlan += [ordered]@{source=$taskFile.FullName;relative=('proposal/'+$taskRelative.Replace('\','/'));expected=(Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
foreach($taskBinding in $taskBindings.bindings) {
    if ($taskBinding.key -in $taskKeys) {
        $taskPlan += [ordered]@{source=(Join-Path $taskOriginal $taskBinding.saved_file);relative=('retained-fixed-loader/'+$taskBinding.saved_file);expected=$taskBinding.sha256}
    }
}
$taskPlan += [ordered]@{source=$ReviewPath;relative='INDEPENDENT-REVIEW.md';expected=$ReviewSha256}
$taskPlan += [ordered]@{source=$taskBindingsPath;relative='context/fixed-loader-source-bindings.json';expected='8dbd83213bceac5012bc342e001826902ce3a88fd420fa64f8f8d9a65366fa9c'}
$taskPlan += [ordered]@{source=(Join-Path $taskOriginal 'SHA256.json');relative='context/original-fixed-loader38-SHA256.json';expected='129773fb33e4ec94a4e217373064d6d55de68d1db71f299a2372a91be1a76403'}
$taskPlan += [ordered]@{source=(Join-Path $taskBase '_scratch\vad-selected-root-projection-final-proof01\SHA256.json');relative='context/original-projection214-SHA256.json';expected='7a3484f2b52d607c65748cb03eb13363418ff2c157e76648c1e7c1cef68d66ed'}
$taskPlan += [ordered]@{source=(Join-Path $taskBase '_scratch\vad-symbolic-adapter-proposal01\results\symbolic-projection01.json');relative='context/symbolic-projection01.json';expected='60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d'}
if ($taskPlan.Count -gt 100) { throw 'Proof count bound' }
if (@($taskPlan.relative | Select-Object -Unique).Count -ne $taskPlan.Count) { throw 'Duplicate proof path' }
foreach($taskEntry in $taskPlan) {
    if ((Get-FileHash -LiteralPath $taskEntry.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.expected) { throw 'Planned source hash changed' }
}
New-Item -ItemType Directory -Path $taskProof -ErrorAction Stop | Out-Null
foreach($taskEntry in $taskPlan) {
    $taskTarget=[IO.Path]::GetFullPath((Join-Path $taskProof $taskEntry.relative))
    if (-not $taskTarget.StartsWith($taskProof+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Noncontained proof destination' }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($taskTarget)) | Out-Null
    Copy-Item -LiteralPath $taskEntry.source -Destination $taskTarget -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.expected) { throw 'Copy hash mismatch' }
    if ((Get-FileHash -LiteralPath $taskEntry.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskEntry.expected) { throw 'Source changed while copying' }
}
[IO.File]::WriteAllText((Join-Path $taskProof '.gitattributes'),"* -text`n",[Text.UTF8Encoding]::new($false))
$taskRecords=@()
foreach($taskFile in (Get-ChildItem -LiteralPath $taskProof -File -Recurse | Sort-Object FullName)) {
    $taskRecords += [ordered]@{path=[IO.Path]::GetRelativePath($taskProof,$taskFile.FullName).Replace('\','/');bytes=$taskFile.Length;sha256=(Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$taskSeal=[ordered]@{scope='Receipt-only selected metadata mapping and inert factory proposal; no model or conversion execution';created_utc=[DateTime]::UtcNow.ToString('o');payload_count=$taskRecords.Count;records=$taskRecords;original_checkpoint_read=$false;original_refusal_preserved=$true;original_projection214_unchanged=$true;original_fixed_loader38_unchanged=$true;factory_approved=$false;release_approved=$false}
$taskSealPath=Join-Path $taskProof 'SHA256.json'
$taskSeal | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskSealPath -Encoding utf8
foreach($taskRecord in $taskRecords) {
    $taskChecked=Join-Path $taskProof $taskRecord.path
    if ((Get-FileHash -LiteralPath $taskChecked -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { throw 'Final payload mismatch' }
}
[ordered]@{status='sealed';payload_count=$taskRecords.Count;seal_sha256=(Get-FileHash -LiteralPath $taskSealPath -Algorithm SHA256).Hash.ToLowerInvariant();proof_path=$taskProof;exit=0} | ConvertTo-Json
