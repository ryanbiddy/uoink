param([Parameter(Mandatory=$true)][string]$Package,[Parameter(Mandatory=$true)][string]$ExpectedHash,[Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference='Stop'
$taskPackage=[IO.Path]::GetFullPath($Package)
$taskOut=[IO.Path]::GetFullPath($Out)
$taskRepo='E:\AI\projects\uoink\checkouts\Yoink-library'
if (-not $taskPackage.StartsWith(($taskRepo+'\build\'),[StringComparison]::OrdinalIgnoreCase) -or -not $taskOut.StartsWith(($taskRepo+'\_scratch\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Package/scan output outside scoped paths' }
if ($taskPackage.Contains('"') -or (Test-Path -LiteralPath $taskOut)) { throw 'Plain package path and fresh scan directory required' }
if ((Get-FileHash -LiteralPath $taskPackage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) { throw 'Package bytes differ' }
New-Item -ItemType Directory -Path $taskOut | Out-Null
$taskScanner='C:\Program Files\Windows Defender\MpCmdRun.exe'
$taskStatus=Get-MpComputerStatus
$taskSig=Get-AuthenticodeSignature -LiteralPath $taskPackage
$taskRecord=[ordered]@{ utc_start=[DateTimeOffset]::UtcNow.ToString('o');package=$taskPackage;package_sha256=$ExpectedHash;package_bytes=(Get-Item -LiteralPath $taskPackage).Length;
 signature=[string]$taskSig.Status;signature_message=$taskSig.StatusMessage;scanner=$taskScanner;
 antivirus_enabled=$taskStatus.AntivirusEnabled;real_time_enabled=$taskStatus.RealTimeProtectionEnabled;
 definitions=$taskStatus.AntivirusSignatureVersion;definitions_updated=$taskStatus.AntivirusSignatureLastUpdated;
 scan='Custom file scan; existing cloud/sample policies retained, not an offline-only claim';remediation_disabled=$true;exit=$null }
try {
 $taskProcess=Start-Process -FilePath $taskScanner -ArgumentList @('-Scan','-ScanType','3','-File',('"'+$taskPackage+'"'),'-DisableRemediation') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskOut 'scan.stdout') -RedirectStandardError (Join-Path $taskOut 'scan.stderr')
 $taskProcess.WaitForExit();$taskProcess.Refresh();$taskRecord.exit=$taskProcess.ExitCode
} finally {
 $taskRecord.utc_end=[DateTimeOffset]::UtcNow.ToString('o')
 $taskRecord.package_sha256_after=(Get-FileHash -LiteralPath $taskPackage -Algorithm SHA256).Hash.ToLowerInvariant()
 [IO.File]::WriteAllText((Join-Path $taskOut 'scan.json'),($taskRecord|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
if ($null -eq $taskRecord.exit -or $taskRecord.exit -ne 0 -or $taskRecord.package_sha256_after -ne $ExpectedHash) { throw 'Scan did not report zero with unchanged package bytes; retain original output' }
$taskRecord|ConvertTo-Json -Depth 5
