# NLTK exact metadata reader — review before invocation

This reader has not run and has not opened the accepted wheel. Root should review its source and all bound text, then admit one command with the final preparation hash:

```powershell
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\nltk-local-metadata-reader01\run_read01.ps1' -ExpectedManifestSha256 '<reviewed hash>'
```

The fixed child command uses `C:\Python314\python.exe -I -S -B`. It accepts no path/URL options. It reads five already copied text inputs and one exact final NLTK wheel; source/root manifests are hash-bound before and after by the launcher. The child verifies the artifact and text snapshots through full same-API path/handle identities, whole-byte size/hash and checked non-reparse ancestors. Windows cross-API identity uses exact birthtime and the remaining identity fields; ctime still must stay exact within each API. No tolerance is introduced. These checks assume quiescent directories and do not claim race-proof OS handle authority.

Only two ZIP payloads are interpreted: the local distribution METADATA and RECORD. Header inspection covers the complete 512-member stored layout, without extracting other members or executing their content. All RECORD membership/sizes are checked, but only the selected METADATA's payload digest is recomputed against RECORD. The whole-file digest is independently checked. Other per-member digest verification remains the historical proof's claim, explicitly outside this invocation.

Fresh `results/read01` contains at most METADATA text and a JSON receipt. Fresh `launch-read01` holds the exact command, raw process logs, immediate durable native exit and outer postcheck result. A refusal exits 2 with its original reason; unexpected startup/instrumentation errors retain their raw native exit. No failure is retried automatically. Output creation uses exclusive writes and retains partial files. The cooperative 30-second budget is checked between operations and before receipt publication; blocking stdlib I/O cannot be preempted by it.

The source-only first draft is retained in `drafts`. Before any invocation, a local-header extent check was made explicit, the output claim was narrowed to wheel-member imports/model execution, and a deadline check was added after receipt serialization. No assertion or measured result changed.

A successful receipt would establish exact local METADATA bytes for a later literal NLTK checker record. It does not imply a public PyPI release exists for the local version, installation, successful imports, a compatible 144-pin graph or model qualification. The reader truthfully sets `artifact_verified_in_this_invocation=true` only after hashing the actual wheel; a future graph invocation using this retained text must still report false for its own artifact verification.
