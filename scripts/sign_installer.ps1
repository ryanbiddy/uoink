[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$FilePath,
    [Parameter(Mandatory)][string]$CertificateThumbprint,
    [Parameter(Mandatory)][string]$TimestampUrl,
    [Parameter(Mandatory)][string]$SignToolPath,
    [Parameter(Mandatory)][string]$ReceiptDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'installer_signing.ps1')
$script:UoinkSigningDiagnostics = [Collections.Generic.List[object]]::new()
try {
    $receipt = Invoke-UoinkSignFile $FilePath $CertificateThumbprint $TimestampUrl $SignToolPath
    Write-UoinkSigningCallbackReceipt $ReceiptDirectory @{
        status='verified'; receipt=$receipt; release_ready=$false; diagnostics=@($script:UoinkSigningDiagnostics.ToArray())
    }
    $receipt | ConvertTo-Json -Depth 4 | Write-Output
    exit 0
} catch {
    $failure = $_
    try {
        Write-UoinkSigningCallbackReceipt $ReceiptDirectory @{
            status='failed'; path=$FilePath; error=$failure.Exception.Message;
            recorded_utc=[DateTime]::UtcNow.ToString('o'); signature_verified=$false; release_ready=$false
            diagnostics=@($script:UoinkSigningDiagnostics.ToArray())
        }
    } catch { Write-Error -ErrorAction Continue $_ }
    Write-Error -ErrorAction Continue $failure
    exit 1
}
