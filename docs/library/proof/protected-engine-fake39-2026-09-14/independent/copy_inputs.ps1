$ErrorActionPreference='Stop'
$taskRoot='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-fake39-independent01'
$taskPlan=Get-Content -LiteralPath (Join-Path $taskRoot 'COPY-PLAN.json') -Raw | ConvertFrom-Json
if($taskPlan.execution_authority -cne $false -or $taskPlan.target -cne $taskRoot -or @($taskPlan.files).Count -ne 42){throw 'Fixed dormant copy plan'}
if((Test-Path -LiteralPath (Join-Path $taskRoot 'ROOT-ADMISSION.json')) -or (Test-Path -LiteralPath (Join-Path $taskRoot 'runs'))){throw 'No independent admission or run tree'}
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'before') -ErrorAction Stop | Out-Null
$taskRows=@()
foreach($taskRow in $taskPlan.files){
 $taskTarget=Join-Path $taskRoot $taskRow.name
 if(Test-Path -LiteralPath $taskTarget){throw 'No overwrite of independent input'}
 $taskBytes=[IO.File]::ReadAllBytes($taskRow.source)
 $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()
 if($taskBytes.Length -ne $taskRow.bytes -or $taskHash -cne $taskRow.sha256){throw 'Frozen author bytes changed'}
 [IO.File]::WriteAllBytes($taskTarget,$taskBytes)
 $taskCopyHash=(Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant()
 $taskAfterHash=(Get-FileHash -LiteralPath $taskRow.source -Algorithm SHA256).Hash.ToLowerInvariant()
 if($taskCopyHash -cne $taskHash -or $taskAfterHash -cne $taskHash){throw 'Original/copy/after mismatch'}
 $taskRows += [ordered]@{name=$taskRow.name;source=$taskRow.source;bytes=$taskBytes.Length;before_sha256=$taskHash;copy_sha256=$taskCopyHash;source_after_sha256=$taskAfterHash;role=$taskRow.role}
}
$taskPayload=[ordered]@{schema='uoink.protected-engine-fake39-independent-copy-result.v1';subject_executed=$false;execution_authority=$false;files=$taskRows}
[IO.File]::WriteAllText((Join-Path $taskRoot 'COPY-BINDINGS.json'),($taskPayload | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
[ordered]@{copied=$taskRows.Count;child_texts=38;before_controls=4;unchanged=$true;subject_executed=$false} | ConvertTo-Json
