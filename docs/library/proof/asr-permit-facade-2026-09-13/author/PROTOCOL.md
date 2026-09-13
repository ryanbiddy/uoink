# Connected adapter qualification — prepared 2026-09-13

Root reviews `qualify_adapter.py`, `run_connected01.ps1`, both historical diffs, `SOURCE-BINDINGS.json` and the four copied candidate sources. Root then writes a separate `ROOT-ADMISSION.md` identifying the exact admitted hashes and the six ordered IDs in `EXPECTED-CASES.json`. The launcher refuses an absent admission or an existing `connected01` directory. No admission is included in this preparation.

The command, once admitted, is:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-permit-facade-qualification01\run_connected01.ps1'
```

Save the actual outer tool result outside the preparation seal. The child command is the existing `_scratch\ig-native\Scripts\python.exe -I -S -B` against the copied `connected01\qualify_adapter.py`. The launcher writes a durable `native-exit.json` immediately after return, before postchecks, using the unchanged reviewed global-exit block. `exit.json` records the distinct computed outer exit, membership/guard validation and unchanged original/copy inputs. `stdout.json` preserves all six case rows, elapsed time, pass/fail/skip counts, source hashes and final guard checks; `stderr.log` stays raw.

The only case setup change is replacing the previous 58-case registration block with the exact `connection_cases.define_cases` result. All six new assertion bodies are copied unchanged. `enum`, `math` and `threading` are preloaded for the actual lifecycle; the fixed content window closes after five source reads, twelve metadata traps install before candidate compilation, and `_release` restoration joins the existing resolver/global checks. The launcher verifies ordered membership and bounds result parsing to 64 KiB. It retains existing input-copy hashing, then checks the launcher, admission and other copied control bytes after the child returns.

No counts exist for this proposal yet. The old 58 passed cases apply to the original adapter interface. This run would measure six connected cases with a fake kernel and real pure-Python lifecycle. It would not exercise Windows, IPC, native model loading, model files, acquisition or real resolver approval. The lexical fake snapshot is never created.

An independent repetition, if root chooses one after a valid first run, must copy the same executable bytes to a fresh root. Only the runner's literal proposal directory may change; preserve that diff, new launcher hash, admission and actual tool result. Do not repeat the author label or repair fixtures after a failure.
