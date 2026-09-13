$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskHere=Join-Path $taskBase 'child-adoption-proof-proposal01'
$taskOutput=Join-Path $taskHere 'SOURCE-MEMBERS.json'
if(Test-Path -LiteralPath $taskOutput){throw 'Fresh documentary inventory required'}
$taskRoots=@('child-readset-adoption-proposal01','child-readset-adoption-proposal02','child-readset-positive01','child-readset-wrong-identity01')
$taskStandalone=@('CHILD-ADOPTION-POSITIVE01-ADMISSION-ACTUAL.json','CHILD-ADOPTION-POSITIVE01-ACTUAL.json','CHILD-ADOPTION-NEGATIVE01-ADMISSION-ACTUAL.json','CHILD-ADOPTION-NEGATIVE01-ACTUAL.json')
$taskGeneratedBinaryNames=@('child-readset-positive01/model.bin','child-readset-wrong-identity01/model.bin')
$taskPaths=@()
foreach($taskRoot in $taskRoots){$taskPaths += @(Get-ChildItem -LiteralPath (Join-Path $taskBase $taskRoot) -Recurse -File | ForEach-Object {$_.FullName})}
foreach($taskName in $taskStandalone){$taskPaths += Join-Path $taskBase $taskName}
$taskRows=@()
foreach($taskPath in @($taskPaths | Sort-Object -Unique)){
    $taskItem=Get-Item -LiteralPath $taskPath
    if($taskItem.Length -gt 1048576 -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Documentary file boundary refused'}
    $taskLogical=[IO.Path]::GetRelativePath($taskBase,$taskPath).Replace('\','/')
    if($taskLogical.StartsWith('../') -or $taskLogical.Contains(':')){throw 'Noncontained documentary member'}
    $taskGeneratedBinary=$taskLogical -cin $taskGeneratedBinaryNames
    if($taskItem.Extension -notin @('.py','.ps1','.json','.md','.diff','.txt','.log') -and $taskItem.Name -cne '.gitattributes' -and -not $taskGeneratedBinary){throw 'Unexpected nontext input'}
    if($taskGeneratedBinary -and $taskItem.Length -ne 60){throw 'Generated ASCII fixture length differs'}
    $taskBytes=[IO.File]::ReadAllBytes($taskPath)
    $taskText=[Text.UTF8Encoding]::new($false,$true).GetString($taskBytes)
    $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
    if($taskGeneratedBinary -and ($taskHash -cne 'e0a9fc9e76fc24578e81900fcb506dc23fa39c17dcb7313e83c382d731ed1f27' -or $taskText -cne "Uoink generated adoption fixture: model.bin. No model data.`n")){throw 'Generated ASCII fixture bytes differ'}
    $taskRows += [ordered]@{logical_path=$taskLogical;source_path=$taskPath;bytes=$taskBytes.Length;sha256=$taskHash}
}
if($taskRows.Count -ne @($taskRows.logical_path | Sort-Object -Unique).Count){throw 'Duplicate logical member'}
$taskInventory=[ordered]@{schema='uoink.child-adoption-documentary-source-members.v1';logical_count=$taskRows.Count;logical_bytes=($taskRows.bytes | Measure-Object -Sum).Sum;distinct_objects=@($taskRows.sha256 | Sort-Object -Unique).Count;roots=$taskRoots;standalone=$taskStandalone;files=$taskRows}
$taskInventory | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskOutput -Encoding utf8
[ordered]@{logical_count=$taskInventory.logical_count;logical_bytes=$taskInventory.logical_bytes;distinct_objects=$taskInventory.distinct_objects;inventory_sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant();archived_code_or_native_execution=0} | ConvertTo-Json
