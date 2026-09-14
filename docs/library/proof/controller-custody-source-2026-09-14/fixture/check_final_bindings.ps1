$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Require([bool]$ok,[string]$message){if(-not $ok){throw $message}}
function Bind([string]$path){
 $bytes=[IO.File]::ReadAllBytes($path)
 [ordered]@{path=$path;bytes=$bytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()}
}
$root=$PSScriptRoot
$map=[IO.File]::ReadAllText($root+'/SOURCE-INPUTS.json')|ConvertFrom-Json
Require ($map.modules.Count -eq 9) 'Nine modules required'
foreach($row in @($map.modules)+@($map.expected)+@($map.context)){
 $actual=Bind $row.path
 Require ($actual.bytes -eq $row.bytes -and $actual.sha256 -ceq $row.sha256) ('Source binding changed: '+$row.path)
}
$oldRoot='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-stage-qualification-proposal01'
$oldMap=[IO.File]::ReadAllText($oldRoot+'/PINS.json')|ConvertFrom-Json
$preserved=@(foreach($name in @('test_reservations.py','test_windows_reservations.py','test_startup_authority.py','test_controller_worker_stage.py','startup_authority_fixture.py','worker_stage_fixture.py','EXPECTED-CASES.json')){
 $rows=@($oldMap.files|Where-Object path -CEQ $name)
 Require ($rows.Count -eq 1) 'One old input required'
 $actual=Bind ($oldRoot+'/'+$name)
 Require ($actual.bytes -eq $rows[0].bytes -and $actual.sha256 -ceq $rows[0].sha256) ('Old input changed: '+$name)
 $actual
})
$ids=@([IO.File]::ReadAllText($root+'/EXPECTED-CASES.json')|ConvertFrom-Json)
Require ($ids.Count -eq 10 -and $map.cases.Count -eq 10) 'Ten cases required'
for($i=0;$i -lt 10;$i++){Require ($ids[$i] -ceq $map.cases[$i].id) 'Case order changed'}
$total=0
foreach($row in $map.cases){$total+=$row.proposed_subtest_iterations;Require ($row.proposed_subtest_iterations -le 48) 'Declared subtest bound changed'}
Require ($total -eq 104) 'Declared subgroup arithmetic changed'
$notes=@(foreach($name in @('SOURCE-INPUTS.json','EXPECTED-CASES.json','REASONS.md','VERDICT.md','DRAFT-ENTRY-REPAIR02.diff','DRAFT-CLEANUP-REPAIR03.diff','controller_boundary_fixture.diff','test_controller_resume_publication.diff')){
 Bind ($root+'/'+$name)
})
[ordered]@{candidate_executions=0;module_bindings=9;case_count=10;declared_subtest_total=$total;declared_max_subtests=48;old_four_tests_two_fixtures_expected_unchanged=$preserved;final_documents=$notes}|ConvertTo-Json -Depth 6

