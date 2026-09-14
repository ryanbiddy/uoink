$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskWork = 'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\31e8890c-ab8\gemini'
$taskRel = 'docs/library/proof/interrupted-owner-fake28-qualification-2026-09-14'
$taskPatch = Join-Path $taskRoot '_scratch/interrupted-fake28-integration01.patch'
if (Test-Path -LiteralPath $taskPatch) { throw 'Fresh patch required' }
git -C $taskWork add -N -f -- $taskRel
if ($global:LASTEXITCODE -ne 0) { exit $global:LASTEXITCODE }
git -C $taskWork diff --binary --full-index -- $taskRel > $taskPatch
if ($global:LASTEXITCODE -ne 0) { exit $global:LASTEXITCODE }
$taskPatchHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $taskPatch).Hash.ToLowerInvariant()
$PSNativeCommandUseErrorActionPreference = $false
git -C $taskRoot -c core.autocrlf=false apply --3way --whitespace=nowarn $taskPatch 1> (Join-Path $taskRoot '_scratch/interrupted-fake28-apply01.stdout.log') 2> (Join-Path $taskRoot '_scratch/interrupted-fake28-apply01.stderr.log')
$taskApplyExit = $global:LASTEXITCODE
[ordered]@{ patch=$taskPatch; bytes=(Get-Item -LiteralPath $taskPatch).Length; sha256=$taskPatchHash; apply_exit=$taskApplyExit; stdout='_scratch/interrupted-fake28-apply01.stdout.log'; stderr='_scratch/interrupted-fake28-apply01.stderr.log'; transport='Raw PowerShell7 native redirection; core.autocrlf=false for application; verify seal before staging.' } | ConvertTo-Json -Compress
exit $taskApplyExit
