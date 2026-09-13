$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal=Join-Path $taskBase '_scratch\vad-buffer-version-adapter-proposal01'
$taskReceipt=Join-Path $taskBase '_scratch\vad-symbolic-adapter-proposal01\results\symbolic-projection01.json'
$taskExpected='60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d'
if((Get-FileHash -LiteralPath $taskReceipt -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected){throw 'Safe receipt hash mismatch'}
$taskData=Get-Content -Raw -LiteralPath $taskReceipt | ConvertFrom-Json
if($taskData.artifact.bytes -ne 17719103 -or $taskData.artifact.sha256 -ne '0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea' -or @($taskData.members).Count -ne 131){throw 'Safe receipt identity/count mismatch'}
$taskNames=@('archive/data.pkl','archive/version')+@(0..128 | ForEach-Object {'archive/data/'+$_})
if(Compare-Object ($taskNames | Sort-Object) ($taskData.members.name | Sort-Object)){throw 'Known inventory names differ'}
$taskRows=@()
foreach($taskMember in ($taskData.members | Sort-Object name)){
 if($taskMember.compression -ne 0 -or $taskMember.compressed_bytes -ne $taskMember.uncompressed_bytes){throw 'Observed inventory is not stored'}
 $taskRows+=,@([string]$taskMember.name,[long]$taskMember.uncompressed_bytes,[long][Convert]::ToUInt32($taskMember.crc32,16))
}
$taskCanonical=ConvertTo-Json -InputObject $taskRows -Depth 4 -Compress
$taskOut=Join-Path $taskProposal 'known-inventory.json'
if(Test-Path -LiteralPath $taskOut){throw 'Known inventory already exists'}
[IO.File]::WriteAllText($taskOut,$taskCanonical,[Text.UTF8Encoding]::new($false))
[ordered]@{source_safe_receipt=$taskReceipt;source_sha256=$taskExpected;source_whole_graph_status='refused';source_reason='Reference cycle refused';recorded_member_count=131;canonical_inventory_sha256=(Get-FileHash -LiteralPath $taskOut -Algorithm SHA256).Hash.ToLowerInvariant();actual_checkpoint_reopened=$false;source_version_bytes_observed=$false} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $taskProposal 'SAFE-RECEIPT-BINDING.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $taskProposal 'SAFE-RECEIPT-BINDING.json')
