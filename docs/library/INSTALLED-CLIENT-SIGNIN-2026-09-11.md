# Sign into the prepared isolated client

The new installer has passed the isolated Setup/reinstall, C22 and independent
P4 route checks. The remaining real-client check needs your Claude subscription
sign-in and confirmation that extra paid usage is off. No ordinary credentials
have been copied or inspected. This step does not run a model.

Use a new PowerShell window on this computer. The dedicated client fixture is
`E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\profile`.
It is prepared and has not run the collector's fixture deletion checks.
The sibling `p4\profile` is a completed historical observation; leave it intact.

```powershell
$ErrorActionPreference = 'Stop'
$clientRoot = 'E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\profile\client'
$clientExe = 'C:\Users\hello\.local\bin\claude.exe'
$clientPrep = Get-Content -LiteralPath (Join-Path $clientRoot 'client-config-preparation.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $clientPrep.hashes.PSObject.Properties) {
    $file = Join-Path $clientRoot $entry.Name
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw ('Prepared client file changed: ' + $entry.Name)
    }
}
$clientLaunch = Get-Content -LiteralPath (Join-Path $clientRoot 'launch-isolated.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($key in 'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL',
                'CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY') {
    Remove-Item -LiteralPath ('Env:' + $key) -ErrorAction SilentlyContinue
}
foreach ($entry in $clientLaunch.environment.PSObject.Properties) {
    [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, 'Process')
}
if ($env:CLAUDE_CONFIG_DIR -ine (Join-Path $clientRoot 'claude-config')) { throw 'Wrong client configuration directory.' }
Set-Location -LiteralPath $clientRoot
& $clientExe --version
& $clientExe auth login --claudeai
if ($LASTEXITCODE -ne 0) { throw 'Sign-in did not complete; retain the refusal.' }
& $clientExe auth status
```

Finish sign-in in the browser and confirm in your Claude account settings that
extra paid usage is off. Tell Astra: **“The isolated client is signed in, and
extra usage is off.”** Do not paste login codes, tokens or credential files.
Then close that PowerShell window. Astra will run the bounded ordinary/Recall
checks through the guarded operator and collect the actual client and visual
evidence. A missing subscription allowance remains blocked; there is no paid
fallback. Main merge and public release still require your separate decision.
