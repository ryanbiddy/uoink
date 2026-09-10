$ErrorActionPreference='Stop'
$taskPath=Join-Path $PSScriptRoot 'agent_install_observer05.ps1'
$taskTokens=$null; $taskErrors=$null
$taskAst=[Management.Automation.Language.Parser]::ParseFile($taskPath,[ref]$taskTokens,[ref]$taskErrors)
if ($taskErrors.Count) { throw ($taskErrors | Out-String) }
$taskFn=@($taskAst.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-UntraversedDesktop'},$true))
if ($taskFn.Count -ne 1) { throw 'Expected one decision function.' }
Invoke-Expression $taskFn[0].Extent.Text
$taskDesktop='C:\Users\Synthetic\OneDrive\Desktop'
$taskCases=@(
 @{name='regular Desktop';folder=$taskDesktop;attrs=[IO.FileAttributes]::Directory;expected=$false},
 @{name='reparse Desktop';folder=$taskDesktop;attrs=([IO.FileAttributes]::Directory -bor [IO.FileAttributes]::ReparsePoint);expected=$true},
 @{name='regular Start Menu';folder='C:\Users\Synthetic\AppData\Roaming\Microsoft\Windows\Start Menu';attrs=[IO.FileAttributes]::Directory;expected=$false},
 @{name='reparse Start Menu';folder='C:\Users\Synthetic\AppData\Roaming\Microsoft\Windows\Start Menu';attrs=[IO.FileAttributes]::ReparsePoint;expected=$false},
 @{name='Desktop child';folder=($taskDesktop+'\child');attrs=[IO.FileAttributes]::ReparsePoint;expected=$false},
 @{name='case-normalized Desktop';folder=$taskDesktop.ToUpperInvariant();attrs=[IO.FileAttributes]::ReparsePoint;expected=$true}
)
$taskResults=@()
foreach($taskCase in $taskCases) {
 $taskActual=Test-UntraversedDesktop $taskCase.folder $taskDesktop $taskCase.attrs
 if($taskActual -ne $taskCase.expected) { throw ('Decision failed: '+$taskCase.name) }
 $taskResults += [ordered]@{name=$taskCase.name;actual=$taskActual;expected=$taskCase.expected;passed=$true}
}
$taskSource=Get-Content -LiteralPath $taskPath -Raw
$taskOriginal=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../scripts/install_receipt/agent_install.ps1') -Raw
$taskOriginalTokens=$null; $taskOriginalErrors=$null
$taskOriginalAst=[Management.Automation.Language.Parser]::ParseInput($taskOriginal,[ref]$taskOriginalTokens,[ref]$taskOriginalErrors)
$taskChecks=@()
foreach($taskName in 'Assert-PlainPath','Write-Receipt','Get-TextHash') {
 $taskOld=$taskOriginalAst.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $taskName},$true).Extent.Text
 $taskNew=$taskAst.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $taskName},$true).Extent.Text
 if($taskOld.Replace("`r`n","`n") -cne $taskNew.Replace("`r`n","`n")) { throw ('Changed guard: '+$taskName) }
 $taskChecks += $taskName+' unchanged'
}
$taskTail='$taskInstalledMarker=Get-Content'
if($taskOriginal.Substring($taskOriginal.IndexOf($taskTail)).Replace("`r`n","`n") -cne $taskSource.Substring($taskSource.IndexOf($taskTail)).Replace("`r`n","`n")) {throw 'Installed marker/registry/four-shortcut checks changed.'}
$taskChecks += 'Installed marker, registry ownership and four exact shortcuts unchanged'
foreach($taskLiteral in '/TASKS=""','/NOCLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS','/ISOLATED=1','/SAVEINF=','Setup selected tasks; desktop exclusion is not established.') {
 if(-not $taskSource.Contains($taskLiteral)) {throw ('Missing safeguard: '+$taskLiteral)}
 $taskChecks += $taskLiteral
}
$taskOut=Join-Path $PSScriptRoot 'desktop-observer05-validation.json'
if(Test-Path -LiteralPath $taskOut) {throw 'Fresh validation receipt required.'}
[ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');parse_errors=0;decision_cases=$taskResults;static_checks=$taskChecks;supplement_sha256=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant();setup_executed=$false;exit=0} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskOut -Encoding utf8
Write-Output 'Desktop observer: parse clean, six decisions passed, preserved guards and exact shortcut checks verified.'
