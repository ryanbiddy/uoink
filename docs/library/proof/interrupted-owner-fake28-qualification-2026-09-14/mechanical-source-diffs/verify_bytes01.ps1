$ErrorActionPreference='Stop'
$taskHere=$PSScriptRoot
$taskUtf8=[Text.UTF8Encoding]::new($false)
$map=Get-Content -LiteralPath (Join-Path $taskHere 'SOURCE-BINDINGS.json') -Raw|ConvertFrom-Json
function Bind([string]$path){$b=[IO.File]::ReadAllBytes($path);return [ordered]@{bytes=$b.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b)).ToLowerInvariant()}}
function Equal($a,$b){return $a.bytes -eq $b.bytes -and $a.sha256 -ceq $b.sha256}
$rows=@()
$deletePaths=@()
foreach($row in $map.core){
    $original=Bind $row.original_path;$candidate=Bind $row.candidate_path
    $rawOriginal=Bind (Join-Path $taskHere $row.raw_diff_original)
    $rawCandidate=Bind (Join-Path $taskHere $row.raw_diff_candidate)
    $forward=Bind (Join-Path $taskHere $row.forward_path)
    $reverse=Bind (Join-Path $taskHere $row.reverse_path)
    if(-not(Equal $original $row.original) -or -not(Equal $candidate $row.candidate) -or
       -not(Equal $rawOriginal $row.original) -or -not(Equal $rawCandidate $row.candidate) -or
       -not(Equal $forward $row.candidate) -or -not(Equal $reverse $row.original)){throw 'Source or reconstruction byte mismatch'}
    $patch=Bind (Join-Path $taskHere ('patches\'+$row.name+'.patch'))
    $diffActual=Get-Content -LiteralPath (Join-Path $taskHere ('DIFF-'+$row.name+'-ACTUAL.json')) -Raw|ConvertFrom-Json
    if($diffActual.exit_code -ne 1){throw 'Raw diff did not report differences'}
    $operations=@()
    foreach($direction in @('forward','reverse')){
        foreach($action in @('check','apply')){
            $name=$direction+'-'+$action+'-'+$row.name+'-ACTUAL.json'
            $actual=Get-Content -LiteralPath (Join-Path $taskHere $name) -Raw|ConvertFrom-Json
            if($actual.exit_code -ne 0){throw 'Reconstruction operation failed'}
            $operations += [ordered]@{file=$name;chunk_id=$actual.chunk_id;exit_code=$actual.exit_code}
        }
    }
    $rows += [ordered]@{name=$row.name;patch=$patch;diff_actual=[ordered]@{chunk_id=$diffActual.chunk_id;exit_code=$diffActual.exit_code;meaning='differences found, expected no-index status'};
        original=$row.original;candidate=$row.candidate;forward_reconstruction=$forward;reverse_reconstruction=$reverse;
        originals_and_candidates_unchanged=$true;forward_matches_candidate=$true;reverse_matches_original=$true;operations=$operations}
    foreach($name in @($row.raw_diff_original,$row.raw_diff_candidate,$row.forward_path,$row.reverse_path)){$deletePaths+=Join-Path $taskHere $name}
}
$test=Bind $map.test_proposal.path
if(-not(Equal $test $map.test_proposal.binding)){throw 'Test proposal changed'}
$inputMapPath='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\interrupted-owner-retirement-repair02\INPUTS.json'
if(-not(Equal (Bind $inputMapPath) $map.input_map)){throw 'Root input map changed'}
$report=[ordered]@{schema='uoink.interrupted-repair02-mechanical-reconstruction.v1';scope='Passive byte reconstruction only; no candidate import/compilation/test/Python/native-model execution';
    raw_patch_format='git diff --no-index --binary --no-ext-diff --no-textconv; core.autocrlf=false; PowerShell7.6.5 byte redirection';
    apply_scope='Disposable copies only; git apply -p2 --directory=fixed reconstruction path; forward and reverse; no index or candidate writes';
    three_patch_rows=$rows;test_proposal_unchanged=$true;test_proposal=$test;rejected_test_reference=$map.rejected_test_reference;
    disposable_copy_policy='Remove only the12 verified disposable text copies after this report, retaining exact full input/output hashes, patches, commands and actuals.';
    candidate_execution=$false;all_checks_pass=$true}
$reportPath=Join-Path $taskHere 'RECONSTRUCTION-CHECK.json'
if(Test-Path -LiteralPath $reportPath){throw 'Report must be fresh'}
[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 16)+[char]10,$taskUtf8)
$prefix=[IO.Path]::GetFullPath($taskHere).TrimEnd('\')+'\'
foreach($path in $deletePaths){
    $full=[IO.Path]::GetFullPath($path)
    if(-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Disposable path escaped package'}
    $rel=$full.Substring($prefix.Length).Replace('\','/')
    if($rel -cnotmatch '^(original|candidate|reconstruction/(forward|reverse))/(durable_lifecycle|generated_adapter_flow|generated_journal_setup)\.py$'){throw 'Unexpected disposable path'}
    $item=Get-Item -LiteralPath $full
    if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Plain disposable copy required'}
}
foreach($path in $deletePaths){Remove-Item -LiteralPath $path -ErrorAction Stop}
foreach($dir in @('reconstruction\forward','reconstruction\reverse','reconstruction','original','candidate')){
    $full=[IO.Path]::GetFullPath((Join-Path $taskHere $dir))
    if(-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Disposable directory escaped package'}
    if(@(Get-ChildItem -LiteralPath $full -Force).Count -ne 0){throw 'Disposable directory not empty'}
    Remove-Item -LiteralPath $full -ErrorAction Stop
}
[ordered]@{patches=3;raw_diff_exits=@(1,1,1);reconstruction_checks=12;all_original_and_derivative_bytes_unchanged=$true;all_forward_and_reverse_hashes_exact=$true;test_proposal_unchanged=$true;disposable_text_copies_removed=12;report=(Bind $reportPath)}|ConvertTo-Json -Depth 6

