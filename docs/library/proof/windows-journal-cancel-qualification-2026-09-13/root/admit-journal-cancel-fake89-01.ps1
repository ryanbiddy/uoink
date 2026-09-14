$ErrorActionPreference='Stop'
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskRepo '_scratch/windows-journal-cancel-fake-proposal01'
$taskPins=Join-Path $taskSource 'PINS.json'
$taskExpected='e60aa77cdd2dd4477960f44f24770f22f7a1e1ff3c334b8985047acb8e8f1a79'
if((Get-FileHash -LiteralPath $taskPins -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskExpected){throw 'Final reviewed map required'}
$taskMap=Get-Content -LiteralPath $taskPins -Raw|ConvertFrom-Json
if($taskMap.files.Count -ne 33){throw 'Expected33 inputs'}
foreach($row in $taskMap.files){
  if($row.path -cnotmatch '^[A-Za-z0-9_.-]+$'){throw 'Flat source only'}
  $path=Join-Path $taskSource $row.path
  $item=Get-Item -LiteralPath $path
  if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $row.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.sha256){throw 'Source binding mismatch'}
}
$taskPrevious=Join-Path $taskRepo '_scratch/windows-stable-directory-identity-proposal01'
foreach($name in @('test_reservations.py','test_windows_reservations.py','test_creation_transfer.py','test_stable_directory.py')){
  if((Get-FileHash -LiteralPath (Join-Path $taskSource $name) -Algorithm SHA256).Hash -cne (Get-FileHash -LiteralPath (Join-Path $taskPrevious $name) -Algorithm SHA256).Hash){throw 'Original test bytes changed'}
}
$taskOld=@(Get-Content -LiteralPath (Join-Path $taskPrevious 'EXPECTED-CASES.json') -Raw|ConvertFrom-Json)
$taskNew=@(Get-Content -LiteralPath (Join-Path $taskSource 'EXPECTED-CASES.json') -Raw|ConvertFrom-Json)
if($taskOld.Count -ne 81 -or $taskNew.Count -ne 89 -or ((ConvertTo-Json -InputObject $taskOld -Compress) -cne (ConvertTo-Json -InputObject @($taskNew[0..80]) -Compress))){throw 'Original ordered cases changed'}
$taskReviewSha=(Get-FileHash -LiteralPath (Join-Path $taskRepo '_scratch/JOURNAL-CANCEL-FAKE89-ROOT-REVIEW01.md') -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAdmission=[ordered]@{approved=$true;label='journal-cancel-fake01';pins_sha256=$taskExpected;scope='generated_bytes_and_fake_ports_only';root_review_sha256=$taskReviewSha;note='One initial qualification of unchanged81 plus8 new controls; no native or model authority.'}
$taskDestination=Join-Path $taskSource 'ROOT-ADMISSION.json'
$taskRaw=[Text.UTF8Encoding]::new($false).GetBytes(($taskAdmission|ConvertTo-Json -Depth 5)+"`n")
$s=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$s.Write($taskRaw,0,$taskRaw.Length);$s.Flush($true)}finally{$s.Dispose()}
[ordered]@{source_inputs=33;original_test_files_unchanged=4;original_ordered_cases=81;new_cases=8;root_review_sha256=$taskReviewSha;admission_sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant();execution=$false}|ConvertTo-Json
