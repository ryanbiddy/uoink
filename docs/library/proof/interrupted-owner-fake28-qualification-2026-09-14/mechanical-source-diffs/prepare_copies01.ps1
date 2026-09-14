$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskHere=$PSScriptRoot
$taskRepair=Join-Path $taskRoot '_scratch\interrupted-owner-retirement-repair02'
$taskMapRaw=[IO.File]::ReadAllBytes((Join-Path $taskRepair 'INPUTS.json'))
$taskUtf8=[Text.UTF8Encoding]::new($false)
$taskMap=$taskUtf8.GetString($taskMapRaw)|ConvertFrom-Json
function Bind([byte[]]$bytes){return [ordered]@{bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}}
function Put([string]$path,[byte[]]$bytes){
    $s=[IO.FileStream]::new($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$s.Write($bytes);$s.Flush($true)}finally{$s.Dispose()}
}
$specs=@(
    @{id='S02';name='durable_lifecycle.py';bytes=32833;sha='3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3'},
    @{id='S04';name='generated_adapter_flow.py';bytes=89924;sha='6a008136802d614ead53297f030dda3da01767ca8a63d313421f142c4d8a160b'},
    @{id='S09';name='generated_journal_setup.py';bytes=19100;sha='44bdaeeb7ba95b202d7fa0bfd202c8e95f3c5bbae4173786a71aa58071184c9c'})
foreach($dir in @('original','candidate','patches','reconstruction','reconstruction\forward','reconstruction\reverse')){
    New-Item -ItemType Directory -Path (Join-Path $taskHere $dir) -ErrorAction Stop|Out-Null
}
$rows=@()
foreach($spec in $specs){
    $source=@($taskMap.inputs|Where-Object {$_.id -ceq $spec.id})
    if($source.Count -ne 1){throw 'Exact original source row required'}
    $source=$source[0]
    $original=[IO.File]::ReadAllBytes($source.path);$ob=Bind $original
    if($ob.bytes -ne $source.bytes -or $ob.sha256 -cne $source.sha256){throw 'Original source binding mismatch'}
    $newPath=Join-Path $taskRepair $spec.name
    $candidate=[IO.File]::ReadAllBytes($newPath);$nb=Bind $candidate
    if($nb.bytes -ne $spec.bytes -or $nb.sha256 -cne $spec.sha){throw 'Frozen derivative mismatch'}
    Put (Join-Path $taskHere ('original\'+$spec.name)) $original
    Put (Join-Path $taskHere ('candidate\'+$spec.name)) $candidate
    Put (Join-Path $taskHere ('reconstruction\forward\'+$spec.name)) $original
    Put (Join-Path $taskHere ('reconstruction\reverse\'+$spec.name)) $candidate
    $rows += [ordered]@{name=$spec.name;original_path=$source.path;original=$ob;candidate_path=$newPath;candidate=$nb;
        raw_diff_original=('original/'+$spec.name);raw_diff_candidate=('candidate/'+$spec.name);
        forward_path=('reconstruction/forward/'+$spec.name);reverse_path=('reconstruction/reverse/'+$spec.name)}
}
$testPath=Join-Path $taskRepair 'test_interrupted_owner_retirement.py'
$testBinding=Bind ([IO.File]::ReadAllBytes($testPath))
if($testBinding.bytes -ne 27790 -or $testBinding.sha256 -cne 'c833cf67e5534c8a0c57e27ae6fec5cb8f6d2c68e8db6844ef7b47075998a2d0'){throw 'Frozen test proposal mismatch'}
$rejected=@($taskMap.inputs|Where-Object {$_.id -ceq 'F09'})
if($rejected.Count -ne 1){throw 'Rejected original reference required'}
$report=[ordered]@{schema='uoink.interrupted-repair02-mechanical-inputs.v1';input_map=(Bind $taskMapRaw);core=$rows;
    test_proposal=[ordered]@{path=$testPath;binding=$testBinding;changed_here=$false;role='new six-case source proposal; no diff application'};
    rejected_test_reference=[ordered]@{path=$rejected[0].path;bytes=$rejected[0].bytes;sha256=$rejected[0].sha256;provenance='F09 of root INPUTS.json; reference retained, not reread here'};
    scope='Byte-identical source copies for raw no-index diff and disposable reconstruction only'}
Put (Join-Path $taskHere 'SOURCE-BINDINGS.json') ($taskUtf8.GetBytes(($report|ConvertTo-Json -Depth 12)+[char]10))
Write-Output 'Prepared three exact old/new source pairs and isolated forward/reverse text copies; source bindings verified.'

