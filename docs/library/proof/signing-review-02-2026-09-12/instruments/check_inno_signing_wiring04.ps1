$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$out = Join-Path $repo '_scratch\signing12-inno-wiring04'
if (Test-Path -LiteralPath $out) { throw 'Fresh observation label required' }
[void][IO.Directory]::CreateDirectory($out)
. (Join-Path $repo 'scripts\installer_signing.ps1')
$inno = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $inno)) { throw 'Expected compiler missing' }
$sdk = Join-Path $out 'Synthetic SDK with spaces'
$receipts = Join-Path $out 'callback receipts'
[void][IO.Directory]::CreateDirectory($sdk)
[void][IO.Directory]::CreateDirectory($receipts)
$fakeTool = Join-Path $sdk 'signtool.exe'
[IO.File]::WriteAllText($fakeTool, 'NOT EXECUTABLE: certificate refusal must precede invocation')
$thumb = '0000000000000000000000000000000000000000'
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
if (Test-Path -LiteralPath "Cert:\CurrentUser\My\$thumb") { throw 'Synthetic certificate unexpectedly exists' }
$command = Get-UoinkInnoSignCommand -PowerShellPath (Get-UoinkSigningPowerShellPath) `
    -CallbackPath (Join-Path $repo 'scripts\sign_installer.ps1') `
    -CertificateThumbprint $thumb -TimestampUrl https://timestamp.example.test `
    -SignToolPath $fakeTool -ReceiptDirectory $receipts
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
SignedUninstallerDir=cache with spaces
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
$compilerExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$callbacks = @(Get-ChildItem -LiteralPath $receipts -Filter '*.json' -File | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
})
$refused = $callbacks.Count -eq 1 -and $callbacks[0].status -eq 'failed' -and
    $callbacks[0].error.Contains('Cannot find path') -and $callbacks[0].error.Contains($thumb)
$result = [ordered]@{
    started_utc=$started; finished_utc=[DateTime]::UtcNow.ToString('o');
    compiler=$inno; compiler_sha256=(Get-UoinkFileSha256 $inno); compiler_exit=$compilerExit;
    callback_command=$command; callback_count=$callbacks.Count;
    missing_certificate_refused=$refused; observation_forwarder_used=$false;
    installer_created=(Test-Path -LiteralPath (Join-Path $out 'output\synthetic-refusal.exe'));
    actual_signature_credit=$false
}
Write-UoinkSigningJson (Join-Path $out 'result.json') $result
$result | ConvertTo-Json -Depth 4
if ($compilerExit -eq 0 -or -not $refused -or $result.installer_created) {
    throw 'Direct callback refusal did not meet the expected result; preserve output'
}
