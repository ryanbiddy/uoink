param([string]$FilePath,[string]$CertificateThumbprint,[string]$TimestampUrl,[string]$SignToolPath)
$PSBoundParameters | ConvertTo-Json | Set-Content -LiteralPath 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\signing12-inno-wiring03\callback-arguments.json' -Encoding UTF8
$ErrorActionPreference = 'Continue'
& 'E:\AI\projects\uoink\checkouts\Yoink-library\scripts\sign_installer.ps1' @PSBoundParameters *> 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\signing12-inno-wiring03\callback.log'
exit $LASTEXITCODE