[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$FilePath,
    [Parameter(Mandatory)][string]$CertificateThumbprint,
    [Parameter(Mandatory)][string]$TimestampUrl,
    [Parameter(Mandatory)][string]$SignToolPath
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'installer_signing.ps1')
try {
    $receipt = Invoke-UoinkSignFile $FilePath $CertificateThumbprint $TimestampUrl $SignToolPath
    $receipt | ConvertTo-Json -Depth 4 | Write-Output
    exit 0
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
