# Passive mirror state receipt

This scratch plugin records raw Python state after each Phase 4 teardown report
and after any failed setup, call or teardown report. It does not import the
product, poll processes, query process identities, acquire product locks, change
fixtures or ordering, terminate workers, or change pytest outcomes. Owner/session
fields can span concurrent transitions; this is an unlocked diagnostic snapshot,
not proof of physical process liveness.

Use `-p _scratch.mirror_state_receipt_plugin` with a fresh absolute JSONL filename
under this checkout's `_scratch`, supplied as `IG_MIRROR_STATE_RECEIPT_PATH`.
The parent directory must already exist. Existing files, lexical escapes and
linked/reparse parent directories are refused before tests start. Set
`IG_MIRROR_STATE_INCLUDE_STACKS=1` only when stack receipts are wanted. The default
is 0. Stacks contain code filename, function and line only, never locals or source
text. Frame presence is recorded without claiming kernel/process liveness.

Observer capture or write errors are separate `observer_error` records and stderr
messages, with a terminal summary. They leave pytest counts/status untouched and
make the diagnostic receipt incomplete. Missing `observer_finished`, a nonzero
observer error count, or any observer error on stderr invalidates the diagnostic
receipt even if product tests pass. Setup/path failures explicitly say the
observer setup failed. A pytest exit code alone cannot establish observer health.

No full-tree runner integration is authorized in this task. Verification uses
only the new scratch synthetic tests and the existing guarded verifier. Native
Python startup must receive `IG_FORBIDDEN_LIVE` as a string before invocation;
provider variables must be scrubbed. No product suite or kernel gate is used.

Attempt 01, `mirror-state-plugin01`, passed all 14 new synthetic cases in 0.17 s
(verifier and pytest exit 0). Its untouched initial plugin and test drafts are
saved as `mirror-state-plugin01/plugin.initial.py` and `tests.initial.py`.
After that pass, static review found an uncovered observer error boundary:
`pytest_unconfigure` could write `diagnostic_complete=true` with exitstatus -1
when normal session completion had not been observed. This was not a product
failure and was not exercised by the 14-case result. The correction adds a
separate `session_incomplete` observer error before closing and a new synthetic
case that requires incomplete status and stderr disclosure. Attempt 02 is
authorized solely to verify that documented instrument correction and its case.

Both attempts use this exact PowerShell environment preparation, in this checkout:

```powershell
$ErrorActionPreference = 'Stop'
Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)$' -or $_.Name -match '^(ANTHROPIC|CLAUDE_CODE|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:IG_FORBIDDEN_LIVE = 'C:\Users\hello\AppData\Local\Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
```

Attempt 01 command:

```powershell
& .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root E:\AI\projects\uoink\checkouts\Yoink-library --label mirror-state-plugin01 _scratch/test_mirror_state_receipt_plugin.py
```

Attempt 02 command:

```powershell
& .\_scratch\ig-native\Scripts\python.exe -B _scratch/integrator_verify.py --root E:\AI\projects\uoink\checkouts\Yoink-library --label mirror-state-plugin02 _scratch/test_mirror_state_receipt_plugin.py
```

The guard also supplies its existing isolated temporary-path fixture. These
synthetic checks invoke the new observer's hooks with inert report/session
objects; they do not activate it over any actual product tests. Logs, XML and
exact child commands remain in each attempt's `tests.log`, `tests.xml` and
`results.json`. Attempt 02, `mirror-state-plugin02`, passed all 15 synthetic cases
in 0.17 s (verifier and pytest exit 0). The original 14 cases remain intact;
the additional case covers the documented incomplete-session correction.

The first attempt to append this result used a note-patch context missing a
leading backtick and was refused before writing. The corrected note patch only
records the measured result; it changes no instrument or test bytes.
