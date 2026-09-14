$ErrorActionPreference='Stop'
$taskRoot='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWork='C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\05a3bf93-0b6\gemini'
$taskRel='docs/library/proof/child-namespace01-failure-2026-09-14'
$taskNotes='docs/library/RELEASE-NOTES-LIVING-LIBRARY.md'
$taskPatch=Join-Path $taskRoot '_scratch/child-namespace01-failure.patch'
if(Test-Path -LiteralPath $taskPatch){throw 'Fresh patch required'}
git -C $taskWork add -N -f -- $taskRel
if($global:LASTEXITCODE -ne 0){exit $global:LASTEXITCODE}
git -C $taskWork diff --binary --full-index -- $taskRel $taskNotes > $taskPatch
if($global:LASTEXITCODE -ne 0){exit $global:LASTEXITCODE}
$PSNativeCommandUseErrorActionPreference=$false
git -C $taskRoot -c core.autocrlf=false apply --3way --whitespace=nowarn $taskPatch 1> (Join-Path $taskRoot '_scratch/child-namespace01-failure-apply.stdout.log') 2> (Join-Path $taskRoot '_scratch/child-namespace01-failure-apply.stderr.log')
$taskExit=$global:LASTEXITCODE
[ordered]@{patch=$taskPatch;bytes=(Get-Item -LiteralPath $taskPatch).Length;sha256=(Get-FileHash -LiteralPath $taskPatch -Algorithm SHA256).Hash.ToLowerInvariant();apply_exit=$taskExit} | ConvertTo-Json -Compress
exit $taskExit
