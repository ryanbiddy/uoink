$ErrorActionPreference='Stop'
$taskDir='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-selected-metadata-map01'
$taskBefore=Join-Path $taskDir 'manifest.proposal.json'
if ((Get-FileHash -LiteralPath $taskBefore -Algorithm SHA256).Hash.ToLowerInvariant() -ne '5c8cf91da7b9798979fe612a4299512a9c24c1f334355dc911027dff7118ab47') { throw 'Original manifest digest mismatch' }
$taskManifest=Get-Content -Raw -LiteralPath $taskBefore | ConvertFrom-Json -AsHashtable
$taskManifest.factory_text_sha256=(Get-FileHash -LiteralPath (Join-Path $taskDir 'fixed-factory.proposal.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
$taskManifest.plain_state_key_precondition='54 exact built-in str keys from the approved tensor reader; verified again by the proposed factory'
$taskOut=Join-Path $taskDir 'manifest.proposal02.json'
if (Test-Path -LiteralPath $taskOut) { throw 'Refuse overwrite' }
$taskManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $taskOut -Encoding utf8
[ordered]@{status='refined_inert_manifest_written';factory_text_sha256=$taskManifest.factory_text_sha256;manifest_sha256=(Get-FileHash -LiteralPath $taskOut -Algorithm SHA256).Hash.ToLowerInvariant();exit=0} | ConvertTo-Json
