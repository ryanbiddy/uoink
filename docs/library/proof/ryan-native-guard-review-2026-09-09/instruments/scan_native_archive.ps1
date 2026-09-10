param([Parameter(Mandatory=$true)][string]$File,[Parameter(Mandatory=$true)][string]$ExpectedHash,[Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch'
$taskFile=[IO.Path]::GetFullPath($File)
$taskOut=[IO.Path]::GetFullPath($Out)
if (-not $taskFile.StartsWith($taskBase+'\native-binary-candidates-',[StringComparison]::OrdinalIgnoreCase) -or -not $taskOut.StartsWith($taskBase+'\native-scan-',[StringComparison]::OrdinalIgnoreCase)) { throw 'Outside native-review scope' }
if ($ExpectedHash -cnotmatch '^[0-9a-f]{64}$' -or (Test-Path -LiteralPath $taskOut)) { throw 'Expected hash and fresh output required' }
foreach ($taskPath in @($taskFile,[IO.Path]::GetDirectoryName($taskOut))) {
 $taskCursor=$taskPath
 while ($taskCursor) {
  if ((Get-Item -LiteralPath $taskCursor).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point refused' }
  $taskCursor=[IO.Path]::GetDirectoryName($taskCursor)
 }
}
if ((Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) { throw 'Archive hash mismatch' }
New-Item -ItemType Directory -Path $taskOut | Out-Null
$taskStatus=Get-MpComputerStatus
$taskRecord=[ordered]@{file=$taskFile;sha256=$ExpectedHash;bytes=(Get-Item -LiteralPath $taskFile).Length;utc_start=[DateTimeOffset]::UtcNow.ToString('o');exit=$null;antivirus_enabled=$taskStatus.AntivirusEnabled;realtime_enabled=$taskStatus.RealTimeProtectionEnabled;definitions=$taskStatus.AntivirusSignatureVersion;remediation_disabled=$true;settings_changed=$false;scope='Custom archive scan; existing cloud/sample policies retained; not a vulnerability clearance'}
try {
 $taskProc=Start-Process -FilePath 'C:\Program Files\Windows Defender\MpCmdRun.exe' -ArgumentList @('-Scan','-ScanType','3','-File',('"'+$taskFile+'"'),'-DisableRemediation') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskOut 'scan.stdout') -RedirectStandardError (Join-Path $taskOut 'scan.stderr')
 $taskProc.WaitForExit();$taskProc.Refresh();$taskRecord.exit=$taskProc.ExitCode
} finally {
 $taskRecord.utc_end=[DateTimeOffset]::UtcNow.ToString('o')
 $taskRecord.sha256_after=(Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant()
 [IO.File]::WriteAllText((Join-Path $taskOut 'scan.json'),($taskRecord|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
if ($null -eq $taskRecord.exit -or $taskRecord.exit -ne 0 -or $taskRecord.sha256_after -ne $ExpectedHash) { throw 'Scan failed; preserve output' }
$taskRecord|ConvertTo-Json -Depth 5
