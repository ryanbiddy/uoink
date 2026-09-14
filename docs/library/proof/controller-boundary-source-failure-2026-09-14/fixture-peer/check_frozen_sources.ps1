$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Assert-Task($condition, [string]$message) { if (-not $condition) { throw $message } }
function Hash-TextFile([string]$path) {
    $taskBytes=[IO.File]::ReadAllBytes($path)
    [ordered]@{path=$path;bytes=$taskBytes.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskBytes)).ToLowerInvariant()}
}
$taskFrozen='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary01-root-review'
$taskPins=Hash-TextFile ($taskFrozen+'/FROZEN-SOURCE-PINS.json')
Assert-Task ($taskPins.sha256 -ceq '1679fc8f78e08f6585232f9400cc12e3d2b2c15bcadb0d22bda31d50d149a438') 'Frozen map mismatch'
$taskMap=[IO.File]::ReadAllText($taskPins.path)|ConvertFrom-Json
$taskCurrent=@'
[
  {
    "source": "C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\19ac6c2d-eaa\\gemini\\_scratch\\controller-resume-publication-implementation01\\controller_boundary_fixture.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\current\\controller_boundary_fixture.py",
    "observed_utc": "2026-09-14T14:21:29.0534550+00:00",
    "bytes": 9592,
    "sha256": "e9229f73dc8d004a71a6c45f73cae7e57985cf3458ca00a96dbb2120bcfbf215"
  },
  {
    "source": "C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\19ac6c2d-eaa\\gemini\\_scratch\\controller-resume-publication-implementation01\\test_controller_resume_publication.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\current\\test_controller_resume_publication.py",
    "observed_utc": "2026-09-14T14:21:29.0574160+00:00",
    "bytes": 11682,
    "sha256": "b2c4b52127e3a51a43b05367124993c0bb4ed1f621b7eab20d63ac5d97113511"
  },
  {
    "source": "C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\19ac6c2d-eaa\\gemini\\_scratch\\controller-resume-publication-implementation01\\EXPECTED-CASES.json",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\current\\EXPECTED-CASES.json",
    "observed_utc": "2026-09-14T14:21:29.0579673+00:00",
    "bytes": 1412,
    "sha256": "401a3149a38ca03fc49ea150575340318e736b612c3941539a7c6d8b8c2e58f0"
  }
]
'@|ConvertFrom-Json
$taskRelations=@(foreach($taskRow in $taskCurrent) {
    $taskName=[IO.Path]::GetFileName($taskRow.snapshot)
    $taskSourcePath=$taskFrozen+'/frozen/'+$taskName
    $taskSnapshot=Hash-TextFile $taskRow.snapshot
    $taskSource=Hash-TextFile $taskSourcePath
    $taskMapRow=@($taskMap.files|Where-Object path -CEQ ('frozen/'+$taskName))
    Assert-Task ($taskMapRow.Count -eq 1) 'Frozen membership mismatch'
    Assert-Task ($taskSnapshot.sha256 -ceq $taskRow.sha256 -and $taskSnapshot.bytes -eq $taskRow.bytes) 'Snapshot changed'
    Assert-Task ($taskSource.sha256 -ceq $taskRow.sha256 -and $taskSource.bytes -eq $taskRow.bytes) 'Frozen bytes differ'
    Assert-Task ($taskMapRow[0].sha256 -ceq $taskSource.sha256 -and $taskMapRow[0].bytes -eq $taskSource.bytes) 'Frozen row differs'
    Assert-Task ([Convert]::ToBase64String([IO.File]::ReadAllBytes($taskRow.snapshot)) -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($taskSourcePath))) 'Full byte comparison failed'
    [ordered]@{snapshot=$taskSnapshot;frozen=$taskSource;full_bytes_equal=$true}
})
$taskDonors=@'
[
  {
    "source": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\real-startup-authority-repair01\\startup_authority_fixture.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\donors\\startup_authority_fixture.py",
    "bytes": 8556,
    "sha256": "fe82ffe16117a9a74b3194e607c86c69b4411076337965ccb5d78c8a9cec897a"
  },
  {
    "source": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\windows-reservation-implementation-proposal02\\test_reservations.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\donors\\test_reservations.py",
    "bytes": 37737,
    "sha256": "604a295d5e925b9a9d7f55750bfeb1ddcda3e6a9873d6d8d7f9e98c84d9b4b9e"
  },
  {
    "source": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\real-startup-authority-repair01\\inputs\\durable_lifecycle.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\donors\\durable_lifecycle.py",
    "bytes": 32833,
    "sha256": "3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3"
  },
  {
    "source": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\windows-interrupted-owner-native-proposal02\\generated_worker_flow.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\donors\\generated_worker_flow.py",
    "bytes": 22853,
    "sha256": "1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238"
  },
  {
    "source": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\windows-interrupted-owner-native-proposal02\\generated_adapter_flow.py",
    "snapshot": "E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\controller-boundary01-tests-preliminary-peer\\snapshots\\donors\\generated_adapter_flow.py",
    "bytes": 90105,
    "sha256": "24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961"
  }
]
'@|ConvertFrom-Json
$taskDonorChecks=@(foreach($taskRow in $taskDonors) {
    $taskSnapshot=Hash-TextFile $taskRow.snapshot
    Assert-Task ($taskSnapshot.sha256 -ceq $taskRow.sha256 -and $taskSnapshot.bytes -eq $taskRow.bytes) 'Retained donor snapshot changed'
    $taskSnapshot
})
$taskContext=@(foreach($taskName in @('durable_lifecycle.py','asr_loading_adapter.py')) {
    $taskValue=Hash-TextFile ($taskFrozen+'/frozen/'+$taskName)
    $taskRow=@($taskMap.files|Where-Object path -CEQ ('frozen/'+$taskName))
    Assert-Task ($taskRow.Count -eq 1 -and $taskValue.sha256 -ceq $taskRow[0].sha256 -and $taskValue.bytes -eq $taskRow[0].bytes) 'Read core context differs from root map'
    $taskValue
})
$taskTests=[IO.File]::ReadAllText('E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary01-tests-preliminary-peer/snapshots/current/test_controller_resume_publication.py')
$taskExpected=@([IO.File]::ReadAllText('E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary01-tests-preliminary-peer/snapshots/current/EXPECTED-CASES.json')|ConvertFrom-Json)
$taskMethods=@([regex]::Matches($taskTests,'(?m)^    def (test_[a-z0-9_]+)\(self\):')|ForEach-Object {$_.Groups[1].Value})
$taskIDs=@($taskMethods|ForEach-Object {'test_controller_resume_publication.ControllerBoundaryContracts.'+$_})
Assert-Task ($taskIDs.Count -eq 10 -and $taskExpected.Count -eq 10) 'Ten IDs required'
for($taskI=0;$taskI -lt 10;$taskI++){ Assert-Task ($taskIDs[$taskI] -ceq $taskExpected[$taskI]) 'Source order differs from EXPECTED' }
$taskFixture=[IO.File]::ReadAllText('E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary01-tests-preliminary-peer/snapshots/current/controller_boundary_fixture.py')
$taskImports=@([regex]::Matches($taskFixture+$taskTests,'(?m)^(?:from|import) [^\r\n]+')|ForEach-Object {$_.Value})
[ordered]@{
    scope='Passive source bytes and text only; no import, compilation or candidate execution';
    frozen_map=$taskPins;snapshot_to_final_relations=$taskRelations;
    retained_donor_snapshots=$taskDonorChecks;read_core_context=$taskContext;
    source_order_ids=$taskIDs;all_ten_ids_match=$true;
    observed_import_lines=$taskImports;
    generated_gate_module_imports_present=[bool]($taskImports -match 'generated_(adapter|worker)_flow');
    candidate_executions=0
}|ConvertTo-Json -Depth 12

