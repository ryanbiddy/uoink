$ErrorActionPreference = 'Stop'
$taskBase = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskProposal = Join-Path $taskBase '_scratch/vad-buffer-version-adapter-proposal01'
$taskRun = Join-Path $taskBase '_scratch/astra-d1-adapter-synthetic01'
if (Test-Path -LiteralPath $taskRun) { throw 'Fresh root label required' }
$taskPlan = Get-Content -Raw -LiteralPath (Join-Path $taskProposal 'd1-preflight01/plan.json') | ConvertFrom-Json
$taskNames = @('inspect_adapter.py','fixed_converter.py','zip_bounds.py','buffer_basis.py','synthetic_zip.py','known-inventory.json','reviewed_converter_harness.txt','qualify_adapter.py')
if (@($taskPlan.inputs).Count -ne 8 -or @(Compare-Object $taskNames @($taskPlan.inputs.name)).Count -ne 0) { throw 'Exact eight input names required' }
New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
$taskRecords = @()
foreach ($taskName in $taskNames) {
  $taskRecord = @($taskPlan.inputs | Where-Object name -eq $taskName)
  if ($taskRecord.Count -ne 1) { throw 'Duplicate input' }
  $taskSource = Join-Path $taskProposal $taskName
  $taskHash = (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($taskHash -ne $taskRecord[0].sha256) { throw 'Author input changed' }
  $taskCopy = Join-Path $taskRun $taskName
  Copy-Item -LiteralPath $taskSource -Destination $taskCopy -ErrorAction Stop
  if ((Get-FileHash -LiteralPath $taskCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskHash) { throw 'Input copy mismatch' }
  $taskRecords += [ordered]@{name=$taskName;source=$taskSource;sha256=$taskHash}
}
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $taskRun 'root-launch.ps1')
@'
2026-09-13. Astra independently read the full adapter533c8abe, its exact
frozen parser/comparator helpers in prior qualified source, generated ZIP
builder, full harnessa6764de8, author launcher9f7dca77 and preflight/repair.
Admit one fresh independent synthetic execution of those exact eight inputs.
Only generated in-memory ZIP bytes and the named read-only source/JSON/text
inputs are involved. No real artifact, profile approval, model import, conversion
or native runtime qualification. The approved real wrapper is unexecuted;
its test stops at absent approval with a path-helper trap. Content opens,
imports, network and processes are constrained by the cooperative audit hook;
this is not complete filesystem metadata/mutation interception or an OS sandbox.
Author54-case run has no failure; preserve every root result independently.
'@ | Set-Content -LiteralPath (Join-Path $taskRun 'ROOT-ADMISSION.md') -Encoding utf8
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
[ordered]@{label='astra-d1-adapter-synthetic01';inputs=$taskRecords;startup_binding_set=$true;arguments=@('-I','-S','-B','qualify_adapter.py');synthetic_only=$true;real_owner_approval_absent=$true} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRun 'plan.json') -Encoding utf8
& (Join-Path $taskBase '_scratch/ig-native/Scripts/python.exe') -I -S -B (Join-Path $taskRun 'qualify_adapter.py') 1> (Join-Path $taskRun 'stdout.json') 2> (Join-Path $taskRun 'stderr.log')
$taskExit = $LASTEXITCODE
$taskUnchanged = $true
foreach ($taskRecord in $taskRecords) {
  foreach ($taskPath in @($taskRecord.source,(Join-Path $taskRun $taskRecord.name))) {
    if ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRecord.sha256) { $taskUnchanged=$false }
  }
}
[ordered]@{native_exit=$taskExit;inputs_unchanged=$taskUnchanged;startup_binding_set=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'exit.json') -Encoding utf8
if (-not $taskUnchanged) { throw 'Qualification input changed' }
exit $taskExit
