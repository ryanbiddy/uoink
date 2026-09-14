2026-09-13. This is a prepared independent confirmation, not an executed run. Root reports that the original rto01 passed eleven cases with zero failures or skips in 14.782957000017632 seconds. The original observations and receipts remain in the original instrument directory; this copy does not recreate them.

The thirteen child inputs are byte-identical to their first-run sources. `COPY-BINDINGS.json` records their exact paths, sizes and hashes. The qualifier remains e08653d576dd3ca8367efde9e9438f485de5835f3831e0f7a1f8571fefa6acc1. All eleven case IDs and assertions are unchanged. The launcher differs only in three instrument-directory and eleven proposal-directory literals. Its source map has the corresponding new paths. The fixed copy script, original controls and complete launcher diff are in the sibling `worker-runtime-owner-confirmation-preparation01` directory.

Prepared launcher SHA-256: c74a9a14e808203beba38dc74f43ba7a42c60986b8138d7856d8d31dd4ed5a2a. Source map: d2d4bc31384a41496455ca87e96fd0a1b8957ede79cd4b5a1a2a76532bc98e7e. Copy bindings: e38f736ca291adbba0a15e5c59d69bfeff9e83c05f1d6fb5b7a5575e926e6696. Admission template: 37ebb3c5b28a35ff88a869f5c6915a772e30814ccbcb69a9bb82fb8446a99deb.

Before a run, root reviews the path-only diff, verifies all fifteen template input hashes and thirteen source-copy rows, and creates a separate ROOT-ADMISSION.json from the false template. No actual admission was created by this preparation. Use `@(template.input_sha256.PSObject.Properties).Count` for the fifteen-property count; direct member enumeration caused the first admission writer's documented preparation failure.

The sole proposed command, from the checkout, is:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-worker-runtime-owner-confirmation01\run_owner01.ps1'
```

The index value is only the inherited lexical prohibition. Output goes to the fresh `runs/rto01` beneath this independent directory. Existing output refuses. The unchanged launcher captures and flushes the actual integer native exit before postchecks, verifies all original/copy inputs and admission, and records the real parser and outer result. Save the actual structured tool result separately. Compare the exact ordered eleven case rows to the original only after reading the raw result; do not compare elapsed times as pass criteria. Preserve any failure and stop before a retry.

This is the same eleven generated ownership behaviors observed again, not twenty-two distinct behaviors. Metadata, registry, import, content and capture guards remain unchanged. No real model, native ML library, decoder, filter or artifact is invoked, and no real runtime authority is issued. Fake factory cleanup is not evidence of native quiescence or memory reclamation.
