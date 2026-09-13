$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$out = Join-Path $repo '_scratch\signing12-inno-wiring03'
if (Test-Path -LiteralPath $out) { throw 'Fresh observation label required' }
New-Item -ItemType Directory -Path $out | Out-Null
. (Join-Path $repo 'scripts\installer_signing.ps1')
$inno = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $inno)) { throw 'Expected Inno compiler missing; no compile attempted' }
$sdk = Join-Path $out 'Synthetic SDK with spaces'
New-Item -ItemType Directory -Path $sdk | Out-Null
$fakeTool = Join-Path $sdk 'signtool.exe'
[IO.File]::WriteAllText($fakeTool, 'NOT EXECUTABLE: must never be invoked')
$thumb = '0000000000000000000000000000000000000000'
if (Test-Path -LiteralPath "Cert:\CurrentUser\My\$thumb") { throw 'Synthetic thumbprint unexpectedly exists' }
$forwarder = Join-Path $out 'observed callback.ps1'
$forwarderCode = @"
param([string]`$FilePath,[string]`$CertificateThumbprint,[string]`$TimestampUrl,[string]`$SignToolPath)
`$PSBoundParameters | ConvertTo-Json | Set-Content -LiteralPath '$out\callback-arguments.json' -Encoding UTF8
`$ErrorActionPreference = 'Continue'
& '$repo\scripts\sign_installer.ps1' @PSBoundParameters *> '$out\callback.log'
exit `$LASTEXITCODE
"@
[IO.File]::WriteAllText($forwarder, $forwarderCode)
$command = Get-UoinkInnoSignCommand (Join-Path $PSHOME 'powershell.exe') `
    $forwarder $thumb https://timestamp.example.test $fakeTool
$template = @'
[Setup]
AppName=Synthetic signing refusal
AppVersion=0.0.0
DefaultDirName={tmp}\SyntheticSigningRefusal
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=synthetic-refusal
SignTool=uoinkrelease
SignedUninstaller=yes
SignedUninstallerDir=cache
SignToolRetryCount=0
[Files]
Source: "fixture.txt"; DestDir: "{app}"
'@
$iss = Join-Path $out 'synthetic.iss'
[IO.File]::WriteAllText($iss, $template)
[IO.File]::WriteAllText((Join-Path $out 'fixture.txt'), 'synthetic fixture, never installed')
$started = [DateTime]::UtcNow.ToString('o')
$ErrorActionPreference = 'Continue'
& $inno /Q $command $iss *> (Join-Path $out 'compiler.log')
$ErrorActionPreference = 'Stop'
$compilerExit = $LASTEXITCODE
$log = [IO.File]::ReadAllText((Join-Path $out 'callback.log'))
$result = [ordered]@{
    started_utc = $started
    finished_utc = [DateTime]::UtcNow.ToString('o')
    compiler = $inno
    compiler_sha256 = Get-UoinkFileSha256 $inno
    compiler_exit = $compilerExit
    callback_command = $command
    callback_invoked = (Test-Path -LiteralPath (Join-Path $out 'callback-arguments.json'))
    missing_certificate_refused = ($log.Contains('Cannot find path') -and $log.Contains($thumb))
    installer_created = Test-Path -LiteralPath (Join-Path $out 'output\synthetic-refusal.exe')
    actual_signature_credit = $false
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8
if ($compilerExit -eq 0 -or -not $result.callback_invoked -or
    -not $result.missing_certificate_refused -or $result.installer_created) {
    throw 'Signing-refusal wiring observation did not meet its expected outcome; preserve output'
}
$result | ConvertTo-Json -Depth 4
