$ErrorActionPreference = 'Stop'
$root = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-provenance-text01'
$utf8 = [Text.UTF8Encoding]::new($false, $true)
foreach ($name in @('SOURCE-BINDINGS.json','VERIFICATION.json','SHA256.json')) {
  if (Test-Path -LiteralPath (Join-Path $root $name)) { throw 'Fresh seal outputs required' }
}
$labels = @(
 'whisperx-release-tree01','pytorch-110-tag01','pytorch-110-serialization01',
 'pytorch-110-container01','whisperx-license01','whisperx-asset-history02',
 'pytorch-110-container-header01','pytorch-110-docs01','pytorch-110-bindings01',
 'whisperx-asset-move01','whisperx-old-vad01','pytorch-110-versions01',
 'whisperx-readme01','whisperx-model-history01','whisperx-old-readme01',
 'pytorch-110-commit01','whisperx-release-commit01','pyannote-main-metadata01',
 'pyannote-202207-metadata01','whisperx-asset-add01','pyannote-exact-metadata01',
 'pytorch-110-utils01','pytorch-110-storage01','pyannote-exact-card01'
)
function Read-Json([string]$relative) {
  return (Get-Content -LiteralPath (Join-Path $root $relative) -Raw | ConvertFrom-Json)
}
function Hash-File([string]$path) {
  return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Git-Blob([string]$path) {
  $bytes = [IO.File]::ReadAllBytes($path)
  $prefix = [Text.Encoding]::ASCII.GetBytes('blob ' + $bytes.Length + [char]0)
  $joined = [byte[]]::new($prefix.Length + $bytes.Length)
  [Array]::Copy($prefix,0,$joined,0,$prefix.Length)
  [Array]::Copy($bytes,0,$joined,$prefix.Length,$bytes.Length)
  return [Convert]::ToHexString([Security.Cryptography.SHA1]::HashData($joined)).ToLowerInvariant()
}
$bindings = @()
$payloads = @('.gitattributes','BRIEF.md','collect_text.ps1','COLLECTOR-DISPLAY-CORRECTION.md',
 'HF-METADATA-SCOPE.md','HISTORY-PATH-REPAIR.md','local-refusal01.json','REPORT.md','WEB-SEARCH-LEADS.md','seal.ps1',
 'collector-draft01/collect_text.ps1','collector-draft02/collect_text.ps1',
 'collector-draft03/collect_text.ps1','collector-draft04/collect_text.ps1')
$totalBytes = [long]0
$success = 0
$failure = 0
foreach ($label in $labels) {
  $request = Read-Json "$label/request.json"
  $result = Read-Json "$label/result.json"
  $responsePath = Join-Path $root "$label/response.txt"
  $actual = Hash-File $responsePath
  $length = (Get-Item -LiteralPath $responsePath).Length
  if ($actual -cne $result.sha256 -or $length -ne $result.bytes -or $length -gt $request.max_bytes -or $request.url -cne $result.url) { throw 'Response binding mismatch' }
  if ($result.exit -eq 0) {
    if ($result.http_status -ne 200 -or $result.status -cne 'collected_text_only') { throw 'Success status mismatch' }
    $success++
  } else {
    if ($label -cne 'pyannote-exact-card01' -or $result.exit -ne 1 -or $result.http_status -ne 401) { throw 'Unexpected failed outcome' }
    $failure++
  }
  $bindings += [ordered]@{label=$label;url=$request.url;utc=$request.utc;response="$label/response.txt";bytes=$length;sha256=$actual;http_status=$result.http_status;collector_exit=$result.exit}
  $totalBytes += $length
  foreach ($file in @('request.json','response.txt','result.json')) { $payloads += "$label/$file" }
}
if ($success -ne 23 -or $failure -ne 1 -or $totalBytes -ne 257950) { throw 'Count mismatch' }
$historical = Read-Json 'pyannote-exact-metadata01/response.txt'
$tagged = Read-Json 'pyannote-202207-metadata01/response.txt'
$model = @($historical.siblings | Where-Object rfilename -CEQ 'pytorch_model.bin')
if ($historical.sha -cne 'c4c8ceafcbb3a7a280c2d357aee9fbc9b0be7f9b' -or $historical.cardData.license -cne 'mit' -or $model.Count -ne 1 -or $model[0].lfs.sha256 -cne '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea' -or $model[0].size -ne 17719103 -or $model[0].lfs.size -ne 17719103 -or $model[0].lfs.pointerSize -ne 133) { throw 'Historical model metadata mismatch' }
if ((Hash-File (Join-Path $root 'pyannote-exact-metadata01/response.txt')) -cne (Hash-File (Join-Path $root 'pyannote-202207-metadata01/response.txt'))) { throw 'Historical tag/exact metadata differ' }
$localReceiptPath = 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-symbolic-adapter-proposal01\results\symbolic-projection01.json'
if ((Hash-File $localReceiptPath) -cne '60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d') { throw 'Local safe receipt changed' }
$localReceipt = Get-Content -LiteralPath $localReceiptPath -Raw | ConvertFrom-Json
if ($localReceipt.artifact.sha256 -cne $model[0].lfs.sha256 -or $localReceipt.artifact.bytes -ne $model[0].lfs.size -or $localReceipt.reader_exit -ne 2) { throw 'Local receipt identity/outcome mismatch' }
$tree = Read-Json 'whisperx-release-tree01/response.txt'
$asset = @($tree.tree | Where-Object path -CEQ 'whisperx/assets/pytorch_model.bin')
if ($tree.truncated -or $asset.Count -ne 1 -or $asset[0].sha -cne '75c92f09d7efd9d140fae46eb982d93a9316095c' -or $asset[0].size -ne 17719103) { throw 'Release tree mismatch' }
$add = Read-Json 'whisperx-asset-add01/response.txt'
$move = Read-Json 'whisperx-asset-move01/response.txt'
if (@($add.files | Where-Object { $_.filename -ceq 'models/pytorch_model.bin' -and $_.sha -ceq $asset[0].sha -and $_.status -ceq 'added' }).Count -ne 1 -or @($move.files | Where-Object { $_.filename -ceq 'whisperx/assets/pytorch_model.bin' -and $_.previous_filename -ceq 'models/pytorch_model.bin' -and $_.sha -ceq $asset[0].sha -and $_.status -ceq 'renamed' -and $_.changes -eq 0 }).Count -ne 1) { throw 'Add/rename chain mismatch' }
foreach ($pair in @(@('whisperx-license01','LICENSE'),@('whisperx-readme01','README.md'))) {
  $entry = @($tree.tree | Where-Object path -CEQ $pair[1])
  if ($entry.Count -ne 1 -or (Git-Blob (Join-Path $root ($pair[0] + '/response.txt'))) -cne $entry[0].sha) { throw 'WhisperX source Git blob mismatch' }
}
$oldVad = @($add.files | Where-Object filename -CEQ 'whisperx/vad.py')
if ($oldVad.Count -ne 1 -or (Git-Blob (Join-Path $root 'whisperx-old-vad01/response.txt')) -cne $oldVad[0].sha) { throw 'Old VAD source blob mismatch' }
$torchTag = Read-Json 'pytorch-110-tag01/response.txt'
$torchCommit = Read-Json 'pytorch-110-commit01/response.txt'
if ($torchTag.object.type -cne 'commit' -or $torchTag.object.sha -cne '36449ea93134574c2a22b87baad3de0bf8d64d42' -or $torchCommit.sha -cne $torchTag.object.sha) { throw 'PyTorch tag/commit binding mismatch' }
$bindingReport = [ordered]@{status='verified_text_and_metadata_bindings';responses=$bindings;local_safe_receipt=@{path=$localReceiptPath;sha256='60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d';copied=$false;reader_exit=2};model_file_opened=$false;pointer_fetched=$false}
[IO.File]::WriteAllText((Join-Path $root 'SOURCE-BINDINGS.json'),($bindingReport | ConvertTo-Json -Depth 10) + "`n",$utf8)
$verification = [ordered]@{status='documentary_checks_completed';utc=[DateTimeOffset]::UtcNow.ToString('o');collector_http_requests=24;http_200=23;http_401=1;response_bytes=$totalBytes;local_url_guard_failure_before_http=1;response_hash_mismatches=0;whisperx_source_git_blobs_verified=3;historical_tag_exact_metadata_equal=$true;local_public_digest_and_size_match=$true;endianness_established=$false;actual_archive_version_read=$false;model_execution=$false;exit=0}
[IO.File]::WriteAllText((Join-Path $root 'VERIFICATION.json'),($verification | ConvertTo-Json -Depth 8) + "`n",$utf8)
$payloads += @('SOURCE-BINDINGS.json','VERIFICATION.json')
$actualNames = @(Get-ChildItem -LiteralPath $root -File -Recurse | ForEach-Object { [IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/') })
if (@(Compare-Object ($payloads | Sort-Object) ($actualNames | Sort-Object)).Count) { throw 'Unlisted or missing documentary payload' }
$manifest = foreach ($name in $payloads | Sort-Object) {
  $path = Join-Path $root $name
  [ordered]@{path=$name;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Hash-File $path)}
}
[IO.File]::WriteAllText((Join-Path $root 'SHA256.json'),([ordered]@{payload_count=$manifest.Count;files=@($manifest)} | ConvertTo-Json -Depth 6) + "`n",$utf8)
foreach ($item in $manifest) { if ((Hash-File (Join-Path $root $item.path)) -cne $item.sha256) { throw 'Post-seal payload mismatch' } }
[pscustomobject]@{status='sealed';payload_count=$manifest.Count;manifest_sha256=(Hash-File (Join-Path $root 'SHA256.json'));report_sha256=(Hash-File (Join-Path $root 'REPORT.md'));response_hash_mismatches=0;exit=0} | ConvertTo-Json -Compress
