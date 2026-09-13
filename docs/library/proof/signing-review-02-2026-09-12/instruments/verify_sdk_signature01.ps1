# New read-only corroboration of the verifier against an existing signed SDK tool.
# No signing operation, model, installer, certificate/private-key export or trust change.
$ErrorActionPreference = 'Stop'
$repo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$out = Join-Path $repo '_scratch\signing12-sdk-verification01'
if (Test-Path -LiteralPath $out) { throw 'Fresh label required' }
New-Item -ItemType Directory -Path $out | Out-Null
. (Join-Path $repo 'scripts\installer_signing.ps1')
$sdk = 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
$before = Get-UoinkFileSha256 $sdk
$identity = Get-AuthenticodeSignature -LiteralPath $sdk
if ($null -eq $identity.SignerCertificate -or $identity.SignerCertificate.Subject -notmatch '(^|, )CN=Microsoft Corporation(,|$)') {
    throw 'Expected SDK publisher not present; no verifier invocation'
}
$started = [DateTime]::UtcNow.ToString('o')
try {
    $receipt = Assert-UoinkSignedFile $sdk $identity.SignerCertificate.Thumbprint $sdk
    $result = [ordered]@{
        status = 'PASS'
        scope = 'Read-only verifier check on the existing Microsoft Windows SDK executable; not Uoink signing.'
        started_utc = $started
        finished_utc = [DateTime]::UtcNow.ToString('o')
        before_sha256 = $before
        after_sha256 = Get-UoinkFileSha256 $sdk
        receipt = $receipt
        uoink_signature_credit = $false
    }
    if ($result.after_sha256 -ne $before) { throw 'SDK bytes changed during read-only verification' }
} catch {
    $result = [ordered]@{status='FAIL'; started_utc=$started; error=$_.Exception.Message; uoink_signature_credit=$false}
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 5
if ($result.status -ne 'PASS') { exit 1 }
