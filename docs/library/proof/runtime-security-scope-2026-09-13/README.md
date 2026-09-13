# Runtime security evidence archive

This archive combines two completed, unchanged evidence collections. `candidate02-osv01` contains the 31 OSV payloads; `candidate03-source` contains the 68 source-review payloads. Their original `SHA256.json` files are preserved byte-for-byte as `ORIGINAL-CANDIDATE02-OSV-SHA256.json` and `ORIGINAL-CANDIDATE03-SOURCE-SHA256.json` inside their respective directories. The root `SHA256.json` covers all documentary payloads except itself.

The source files, collectors and source proposal are retained as evidence. Do not run the collectors or import captured package code to verify this archive. The original instruments retain their original paths and freshness guards; their receipts describe completed attempts. `instruments/verify_runtime_security_scope_seal.py` is a separate stdlib-only reader for this relocated archive. It checks root and original manifests, source/retrieval/commit bindings and OSV raw query counts without fetching or executing captured code.

From the checkout, run this read-only verification with the existing native interpreter:

```powershell
Get-ChildItem Env: | Where-Object {
    $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)$' -or
    $_.Name -match '^(ANTHROPIC|CLAUDE_CODE|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_'
} | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\_scratch\ig-native\Scripts\python.exe -I -S -B .\docs\library\proof\runtime-security-scope-2026-09-13\instruments\verify_runtime_security_scope_seal.py
```

The live-index path above is only the required startup guard string; the verifier does not open it. PASS means the archived evidence is internally consistent. It does not mean the runtime is compatible, secure or ready for release. The root copy receipt records every original source and destination hash, and the detailed reviews preserve the unresolved findings.
