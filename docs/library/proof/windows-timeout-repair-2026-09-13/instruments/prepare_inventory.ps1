$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskHere=Join-Path $taskBase 'timeout-repair-proof-proposal01'
$taskOutput=Join-Path $taskHere 'SOURCE-MEMBERS.json'
if(Test-Path -LiteralPath $taskOutput){throw 'Fresh documentary inventory required'}
$taskRoots=@('asr-dummy-worker-timeout-proposal01','asr-dummy-worker-timeout-proposal02','asr-dummy-worker-timeout01','asr-dummy-worker-timeout02','astra-pipe-terminal67-qualification01')
$taskStandalone=@('DUMMY-TIMEOUT01-ACTUAL.json','DUMMY-TIMEOUT01-ADMISSION-ACTUAL.json','DUMMY-TIMEOUT02-ACTUAL.json','DUMMY-TIMEOUT02-ADMISSION-ACTUAL.json','PIPE-TERMINAL67-ADMISSION-ACTUAL.json','PIPE-TERMINAL67-AUTHOR-ACTUAL.json','PIPE-TERMINAL67-ROOT-ACTUAL.json','PIPE-TERMINAL67-ROOT-PREP-ACTUAL.json')
$taskPaths=@()
foreach($taskRoot in $taskRoots){$taskPaths += @(Get-ChildItem -LiteralPath (Join-Path $taskBase $taskRoot) -Recurse -File | ForEach-Object {$_.FullName})}
foreach($taskName in $taskStandalone){$taskPaths += Join-Path $taskBase $taskName}
$taskRows=@()
foreach($taskPath in @($taskPaths | Sort-Object -Unique)){
    $taskItem=Get-Item -LiteralPath $taskPath
    if($taskItem.Length -gt 1048576 -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Documentary file boundary refused'}
    if($taskItem.Extension -notin @('.py','.ps1','.json','.md','.diff','.txt','.log')){throw 'Unexpected nontext input'}
    $taskBytes=[IO.File]::ReadAllBytes($taskPath)
    $null=[Text.UTF8Encoding]::new($false,$true).GetString($taskBytes)
    $taskLogical=[IO.Path]::GetRelativePath($taskBase,$taskPath).Replace('\','/')
    if($taskLogical.StartsWith('../') -or $taskLogical.Contains(':')){throw 'Noncontained documentary member'}
    $taskRows += [ordered]@{logical_path=$taskLogical;source_path=$taskPath;bytes=$taskBytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()}
}
if($taskRows.Count -ne @($taskRows.logical_path | Sort-Object -Unique).Count){throw 'Duplicate logical member'}
$taskInventory=[ordered]@{schema='uoink.timeout-documentary-source-members.v1';logical_count=$taskRows.Count;logical_bytes=($taskRows.bytes | Measure-Object -Sum).Sum;distinct_objects=@($taskRows.sha256 | Sort-Object -Unique).Count;roots=$taskRoots;standalone=$taskStandalone;files=$taskRows}
$taskInventory | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskOutput -Encoding utf8
[ordered]@{logical_count=$taskInventory.logical_count;logical_bytes=$taskInventory.logical_bytes;distinct_objects=$taskInventory.distinct_objects;inventory_sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant();archived_code_or_native_execution=0} | ConvertTo-Json
