$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWork='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\31e8890c-ab8\gemini'
$taskRel='docs/library/proof/interrupted-owner-prelock30-qualification-2026-09-14'
$taskPatch=Join-Path $taskRoot '_scratch/prelock30-qualification.patch'
if(Test-Path -LiteralPath $taskPatch){throw 'Fresh patch required'}
git -C $taskWork add -N -f -- $taskRel
if($global:LASTEXITCODE -ne 0){exit $global:LASTEXITCODE}
git -C $taskWork diff --binary --full-index -- $taskRel > $taskPatch
if($global:LASTEXITCODE -ne 0){exit $global:LASTEXITCODE}
$PSNativeCommandUseErrorActionPreference=$false
git -C $taskRoot -c core.autocrlf=false apply --3way --whitespace=nowarn $taskPatch 1> (Join-Path $taskRoot '_scratch/prelock30-apply.stdout.log') 2> (Join-Path $taskRoot '_scratch/prelock30-apply.stderr.log')
$taskExit=$global:LASTEXITCODE
[ordered]@{patch=$taskPatch;bytes=(Get-Item -LiteralPath $taskPatch).Length;sha256=(Get-FileHash -LiteralPath $taskPatch -Algorithm SHA256).Hash.ToLowerInvariant();apply_exit=$taskExit;stdout='_scratch/prelock30-apply.stdout.log';stderr='_scratch/prelock30-apply.stderr.log'} | ConvertTo-Json -Compress
exit $taskExit
