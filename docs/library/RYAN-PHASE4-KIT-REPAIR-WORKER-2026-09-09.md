# Phase 4 kit repair worker — 2026-09-09

Worker: grok. Worktree: this Control Room tree only. No commit, push, merge,
subagent, live index, port 5179, paid API, key, Inno, client/model process,
new fetch, diarization or label application.

Status: **source complete**. Astra independently reviews both roots and seals
the package/runbook. This worker does not claim an installed pass.

Input: archived `docs/library/patches/ryan-phase4-kit-original-2026-09-09.patch`
(applied unchanged). Isolation overlay for disposable scratch only:
`docs/library/proof/ryan-install-review-2026-09-09/original.patch`. Stop CLI
was not run.

Existing tests, including `tests/test_install_receipt_p4_kit.py`, were not
edited. The original 11-pass instrument claim is retained as a prior result;
after isolation-root repair that file is **10 passed, 1 failed**.

## Five repairs (p4_*.py only)

### 1. Original-route complete frame checks

`run_installed` now drives initialize, 32 tools, five templates, four prompts,
native + fallback card/excerpt/corpus/brief reads, `prompts/get` for
`consult-library` and `reshelve-review`, reconnect with tap `child_started`
PIDs, unavailable storage (bound 2000 ms, no replacement index) and transport
failure (bound 15000 ms) against original `uoink_mcp.py`. FAKE_CHILD is
`--route synthetic-instrument` only. Fixture-attached stays labeled.
Failures are product findings with the exact command/input;
`hidden_by_special_route` is always false.

Source-runtime overlay (not installed credit) against isolation-aware
`uoink_mcp.py` measured:

- tools: exact frozen 32-name set
- templates: five (`library-card` … `library-brief`)
- prompts: four (`consult-library`, `evidence-brief`, `whats-new`, `reshelve-review`)
- distinct child PIDs (example 55292 / reconnect pair in `_scratch/p4kit-repair-source-runtime.json`)
- native `ReadResourceRequest`, `CallToolRequest`, `GetPromptRequest` frames
- remaining product finding: packet/prompt equality incomplete vs frozen
  expected text (recorded, not hidden)

### 2. Bounded stdio and owned process tree

`p4_session.py`: continuously drained stderr, deadline-matched RPC by id,
retained unmatched/partial frames. Hang of 30 s fails in < 5 s with
`error=timeout`. Windows Job Object `KILL_ON_JOB_CLOSE` owns the tree;
cleanup uses the Popen handle, never a foreign PID or process name.
`p4_stdio_tap.py` assigns the inner child to the same job when
`p4_session` is present.

### 3. Isolation root and guard mechanism

Supported root is `<profile>/index.db`, `token.txt`, `settings.json`,
`output/` — not `<profile>/Uoink/index.db`. Live `LOCALAPPDATA` is captured
at import before redirection. Isolation-aware children keep the live
LOCALAPPDATA so `uoink_install_isolation` does not treat `<profile>/Uoink`
as nested normal data; they bind `--isolated-profile` /
`UOINK_ISOLATED_*`. Guard install uses bundled `Lib/site-packages`
sitecustomize plus a recorded, restorable `python._pth` `import site` when
the interpreter lives under the installed app. Conflicting C22
sitecustomize bytes are refused. Prefix interpreters are not mutated.
No 5179 connect.

### 4. Provenance / source-runtime

Installed credit is not `not instrument_only` and not a 64-character string.
`--runtime-mode installed` requires hex SHA-256 package and source fields,
actual package bytes matching the digest, `uoink_mcp.py` + `server.py`
bindings, bundled `python/python.exe` ownership, `--forbid-checkout`, and
complete measured original-route results. Missing input fails closed.
`--runtime-mode source-runtime` is the named pre-Inno path (user-site may
be on PYTHONPATH, labeled, never installed credit).

### 5. Executable checks and client recipes

`p4_execute_checks.py` runs Recall against a missing isolated index, the
inert sentinel against hostile payloads, and fixture-only mirror
disconnect/reconnect, user-edit bytes, and deletion accounting. Operator
booleans are not a pass. Missing images stay `unobserved`. X 403, optional
`D_FCYsshMI4` jump, `apply` false, no speaker claim, Phase 5 Part B deferred.
`p4_prepare_client.py` writes `stream_collection` paths and
`client/ryan-stream-capture.ps1`. This worker does not start Claude.

## Exact commands and counts

Interpreter: `C:\Python314\python.exe`. User-site on the **test runner**
PYTHONPATH only. `ANTHROPIC_API_KEY` unset.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
$root = '<this-worktree>'
$site = 'C:\Users\hello\AppData\Roaming\Python\Python314\site-packages'
$env:PYTHONPATH = "$root;$root\scripts\install_receipt;$site"

# Original kit file (not edited)
C:\Python314\python.exe -B -m pytest -q --tb=short -p no:cacheprovider `
  tests/test_install_receipt_p4_kit.py --basetemp=_scratch\p4kit-repair-orig
# 10 passed, 1 failed, 6.74 s

# Repair regressions
C:\Python314\python.exe -B -m pytest -q --tb=short -p no:cacheprovider `
  tests/test_install_receipt_p4_kit_repair.py --basetemp=_scratch\p4kit-repair-new2
# 10 passed, 3.80 s (later isolation-scratch reruns 6.45–14.32 s)

# Combined after documented repairs
C:\Python314\python.exe -B -m pytest -q --tb=line -p no:cacheprovider `
  tests/test_install_receipt_p4_kit.py tests/test_install_receipt_p4_kit_repair.py `
  --basetemp=_scratch\p4kit-repair-final
```

**Combined: 20 passed, 1 failed, 31.52 s, exit 1.**

Retained original failure (not edited to pass):

`test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false` —
`profile/Uoink/settings.json` missing because settings now live at
`<profile>/settings.json`.

Syntax: `python -B -m py_compile` of all `p4_*.py` and both test files, exit 0.

## Copied-kit commands (Ryan after Astra seals)

Replace angle-bracket paths. Receipt root fresh. Port not 5179. Installed
app is the spaced Inno target. `--runtime-mode installed` plus
`--package-path` with sealed bytes. No `ANTHROPIC_API_KEY`.

```powershell
$ErrorActionPreference = 'Stop'
if ($env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY must be absent' }
$kit = '<copied-kit>\scripts\install_receipt'
$py  = '<installed-app>\python\python.exe'
$app = '<installed-app>'
$root = '<receipt-root>'
$profile = Join-Path $root 'isolated-profile'
$port = 18081
$manifest = Join-Path $root 'package-manifest.json'
$package = '<sealed-installer>'

& $py -B "$kit\p4_prepare_fixture.py" --runtime-mode installed `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --package-path $package `
  --receipt-root $root --forbid-checkout '<this-checkout>'

& $py -B "$kit\p4_stdio_check.py" --runtime-mode instrument-only `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --route synthetic-instrument --instrument-only

& $py -B "$kit\p4_stdio_check.py" --runtime-mode installed `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --package-path $package `
  --receipt-root $root --forbid-checkout '<this-checkout>' `
  --route original-installed

& $py -B "$kit\p4_stdio_check.py" --runtime-mode installed `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --package-path $package `
  --receipt-root $root --forbid-checkout '<this-checkout>' `
  --route fixture-attached

& $py -B "$kit\p4_inspect_evidence.py" `
  --isolated-profile $profile --isolated-port $port `
  --fixture-root $profile --output (Join-Path $profile 'inspection.json')

& $py -B "$kit\p4_prepare_client.py" --runtime-mode installed `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --package-path $package `
  --receipt-root $root --forbid-checkout '<this-checkout>'

# Ryan only: confirm claude.ai subscription, usage credits off, then capture
# the complete stream from launch-isolated.json:
#   1> <profile>\client\claude-stream.jsonl
#   2> <profile>\client\claude-stream.stderr.log
# Do not copy credentials.

& $py -B "$kit\p4_collect_evidence.py" --runtime-mode installed `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --package-path $package `
  --receipt-root $root --forbid-checkout '<this-checkout>' `
  --operator-json (Join-Path $profile 'operator.json') `
  --output (Join-Path $profile 'collection.json')
```

Pre-Inno Astra check: the same commands with `--runtime-mode source-runtime`
(no `--package-path`). That is not installed credit.

## Files

New/repaired under this worktree only:

```
scripts/install_receipt/p4_common.py
scripts/install_receipt/p4_session.py
scripts/install_receipt/p4_provision_isolation.py
scripts/install_receipt/p4_execute_checks.py
scripts/install_receipt/p4_stdio_check.py
scripts/install_receipt/p4_stdio_tap.py
scripts/install_receipt/p4_prepare_fixture.py
scripts/install_receipt/p4_collect_evidence.py
scripts/install_receipt/p4_prepare_client.py
scripts/install_receipt/p4_inspect_evidence.py
scripts/install_receipt/p4_observe_actions.py
tests/test_install_receipt_p4_kit.py          # original, unchanged
tests/test_install_receipt_p4_kit_repair.py   # new
docs/library/RYAN-INSTALLED-PHASE4-KIT-WORKER-2026-09-09.md  # original, unchanged
docs/library/RYAN-PHASE4-KIT-REPAIR-WORKER-2026-09-09.md
```

No production, existing-test, fixture, proof, runbook, C22, or isolation
worktree edits. No commit.

## Unresolved product findings

- Current checkout `uoink_mcp.py` still has no `apply_from_process`; original
  installed credit needs Astra's isolation integration in the sealed package.
- Source-runtime overlay against isolation-aware stdio returned 32/5/4
  inventory and native prompt/resource/tool frames, then recorded packet
  equality incomplete vs fixture expected text (exact input in
  `_scratch/p4kit-repair-source-runtime.json`).
- Unavailable-storage elapsed can be null if the live child exits before the
  bounded read; that stays a finding, not a synthetic pass.
- Ryan still owns sealed Inno, subscription client, screenshots, and stream
  files. Missing images remain unobserved.

## Open for Astra / Ryan

- Seal `package_sha256` / `installer_source_sha` after the isolation rebuild.
  Do not copy a hash from this worker.
- Integrate isolation so the installed `uoink_mcp.py` honors
  `--isolated-profile` / `--isolated-port` with DATA_ROOT `<profile>`.
- Phase 5 Part B remains deferred.
