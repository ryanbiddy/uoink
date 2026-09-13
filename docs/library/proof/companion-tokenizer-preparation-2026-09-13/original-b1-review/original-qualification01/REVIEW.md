# Companion B selected constructor verdict — 2026-09-13

The exact proposed companion-B constructor change passes all six preserved
synthetic contracts. The retained original source passes one and fails five;
those failures and the repair reason remain separate evidence. This result
supports review of the small source derivative. It does not accept a packaged
runtime or authorize applying the derivative to shared staging.

| Assertion | Original `baseline01` | Proposed `candidate01` |
| --- | --- | --- |
| Explicit non-local fallback remains available | Pass | Pass |
| Invalid local tokenizer refuses before model construction | Fail | Pass |
| Missing local tokenizer refuses before model construction | Fail | Pass |
| Supplied tokenizer bytes precede model construction | Fail | Pass |
| Tokenizer disappearing after the file check refuses before construction | Fail | Pass |
| Valid local tokenizer is prepared before construction | Fail | Pass |

Both arms ran six cases with zero errors and zero skips. Actual process exits
were 1 and 0 respectively. They used the same extracted protocol bytes,
`01e8d20863ca74aa855ac86b3a1609bf7212addc15032705e990b50a25064d04`.
Every assertion, the entire companion TestCase class, and both extracted helpers
have unchanged ASTs compared with the original sealed proposal. Only unrelated
product-A definitions and the original CLI were omitted; required stdlib imports
and a scope docstring were supplied. The harness injects the selected source path
and places temporary synthetic fixtures below each run directory. No existing
product or accepted test was edited.

The source input is retained staging text recorded as faster-whisper 1.2.1,
bound by the original 24-payload seal. It is not a fresh upstream retrieval or
independently established full wheel identity. The target member is
`faster_whisper/transcribe.py`. Its input SHA-256 is
`5d5ffb00018561d3d529b2c72e1d9f5fff055bea725f3cccc7c6c67f5cc8ffe4`;
the unchanged proposed derivative is
`e500e12b0a58420ce5f41b202ba7d942b901a9b99c617d6ca3d3304b9493f269`;
the exact patch is
`ef6e3ea49d4a30279ec6a37dc5d737db5ea8d8d1191af25c578f6411c407b764`.
The retained patch reconstructs the derivative as normalized source text.
`source-mapping.json` records the exact byte identities and extraction changes.
No derivative version, wheel, dependency lock or installed artifact was created.

| Compatibility point | Evidence in `original-proposal01/companion-B.py.txt` | Effect and remaining limit |
| --- | --- | --- |
| Local file and supplied buffer preparation | Lines 689–696 | Parsing happens before CTranslate2, including non-local mode when a local tokenizer exists. Synthetic order and refusal are verified; actual tokenizer format/native behavior is unobserved. |
| Missing local-only tokenizer | Lines 695–696 | Raises an explicit FileNotFoundError before model construction. This intentionally replaces the old remote fallback for that condition. |
| Constructor arguments | Lines 698–707 | CTranslate2 arguments are unchanged. The harness records the call; it does not construct a native model. |
| Non-local missing-tokenizer fallback | Lines 709–714 | The old fallback and multilingual/English name expression remain after construction. The multilingual fake path is exercised; actual remote retrieval and the English branch are untested. |
| Resolver and supplied-file dictionary | Lines 673–687 | Existing branch selection and dictionary pop behavior are unchanged. Synthetic local-directory and supplied-buffer branches are exercised; alias/cache resolution and download_model are not. |
| Later initialization | Lines 715 onward | Feature extraction and all later constructor work are unchanged and deliberately excluded from execution. |

Exception precedence changes where both tokenizer and model input are invalid:
the tokenizer error now occurs first, before a model allocation. A tokenizer
prepared successfully before a later CTranslate2 failure is left to normal
object cleanup; native allocation/cleanup behavior was not tested. Empty supplied
tokenizer bytes still follow the existing truthiness rule, now reaching the
explicit local-only refusal if no tokenizer file exists. None of the six cases
proves every malformed input or filesystem race safe. The guard does not replace
the unresolved artifact manifest, VAD/checkpoint, dependency vulnerability or
full-stack compatibility work.

The harness ran on Python 3.14.6 with isolated, no-site and no-bytecode flags.
It parsed source text and executed only the selected __init__ prefix through the
assignment to self.hf_tokenizer. Explicit fake namespaces supplied CTranslate2,
tokenizer and logger behavior; download_model raises if called. No whole
dependency module, actual tokenizer or model was imported or executed. Both
receipts show no preloaded or postloaded heavy packages, no import or audit
violations, and the import finder still installed at completion. The finder
denies heavy/non-stdlib discovery, and the audit hook denies socket, child-process
and ctypes library-load operations. These receipts are observation under this
reviewed harness, not an adversarial sandbox certification or target-Python 3.13
runtime receipt.

Exact commands, run from
`E:\AI\projects\uoink\checkouts\Yoink-library`:

```powershell
C:\Python314\python.exe -I -S -B _scratch\companion-b-static-qualification01\prepare.py
C:\Python314\python.exe -I -S -B _scratch\companion-b-static-qualification01\launch.py baseline01
C:\Python314\python.exe -I -S -B _scratch\companion-b-static-qualification01\launch.py candidate01
C:\Python314\python.exe -I -S -B _scratch\companion-b-static-qualification01\verify-and-seal.py
```

Each launcher plan records its exact child command, input hashes, environment
variable names scrubbed without their values, and UTC start time. Child results,
raw unittest logs, raw console output and actual launcher exits are retained.
`BASELINE-REPAIR-REASON-2026-09-13.md` was written before candidate execution.
The candidate arm made no repairs to the proposal or assertions.

Root review should decide whether this exact delta is suitable for a separately
identified derivative and provenance/build plan. No new Ryan ruling was needed
for this authorized scratch qualification. Applying or building the dependency
derivative remains a separate action; it must not silently replace the original
package identity or frozen compatibility contracts. The original 24-payload seal
and all its bytes remain unchanged, both outside this directory and in its copied
child. The outer proof includes `* -text` to preserve those bytes in Git transport.
