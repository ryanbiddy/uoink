$ErrorActionPreference='Stop'
$base='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$review=Join-Path $base 'asr-completion-info-fake59-peer01'
$authorPath=Join-Path $base 'asr-completion-info-fake59-author01\asr-completion-info-fake59-01\stdout.json'
$independentPath=Join-Path $base 'asr-completion-info-fake59-independent01\asr-completion-info-confirmation59-01\stdout.json'
$authorSummary=Get-Content -LiteralPath (Join-Path $review 'AUTHOR-RESULT.json') -Raw|ConvertFrom-Json
$independentSummary=Get-Content -LiteralPath (Join-Path $review 'INDEPENDENT-RESULT.json') -Raw|ConvertFrom-Json
foreach($row in @(@{path=$authorPath;summary=$authorSummary},@{path=$independentPath;summary=$independentSummary})){
 if((Get-FileHash -LiteralPath $row.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $row.summary.stdout.sha256){throw 'receipt changed after full check'}
}
$author=Get-Content -LiteralPath $authorPath -Raw|ConvertFrom-Json
$independent=Get-Content -LiteralPath $independentPath -Raw|ConvertFrom-Json
$aCases=$author.cases|ConvertTo-Json -Depth 20 -Compress
$bCases=$independent.cases|ConvertTo-Json -Depth 20 -Compress
if($aCases -cne $bCases){throw 'complete ordered case objects differ'}
$aInputs=$author.input_sha256|ConvertTo-Json -Depth 5 -Compress
$bInputs=$independent.input_sha256|ConvertTo-Json -Depth 5 -Compress
if($aInputs -cne $bInputs){throw 'five child hashes differ'}
$sha=[Security.Cryptography.SHA256]::Create()
try{$caseHash=[Convert]::ToHexString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($aCases))).ToLowerInvariant()}finally{$sha.Dispose()}
foreach($entry in @(@{name='SUBJECT-AUTHOR-ACTUAL.json';source='COMPLETION-FAKE59-AUTHOR-ACTUAL.json'},@{name='SUBJECT-INDEPENDENT-ACTUAL.json';source='COMPLETION-FAKE59-INDEPENDENT-ACTUAL.json'})){
 [IO.File]::Copy((Join-Path $base $entry.source),(Join-Path $review $entry.name),$false)
}
$result=[ordered]@{scope='Independent passive pair comparison; no subject execution';author_actual='577e68';independent_actual='8fd760';each_passed=59;each_failed=0;each_skipped=0;each_subtests_passed=29;all_ordered_case_objects_equal=$true;case_objects_serialization='PowerShell ConvertTo-Json -Depth20 -Compress in retained property order';case_objects_sha256=$caseHash;five_child_hashes_equal=$true;each_complete_check='9 inputs, 3 controls, 17 outputs, 10 guards, 12 metadata and 25 registry traps';independent_pair_pending=$false;subject_rerun=$false}
$out=Join-Path $review 'PAIR-RESULT.json'
if(Test-Path -LiteralPath $out){throw 'fresh pair result required'}
[IO.File]::WriteAllText($out,($result|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
$result|ConvertTo-Json -Depth 5
