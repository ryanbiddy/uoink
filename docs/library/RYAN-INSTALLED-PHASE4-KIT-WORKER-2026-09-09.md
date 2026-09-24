# Phase 4 installed-client / everyday receipt kit (Grok, 2026-09-09)

Worker: Grok. Worktree: this Control Room tree. No commit, push, existing
product/test/proof edit, live index, port 5179, model subprocess, Inno, paid
API, or `ANTHROPIC_API_KEY`. Isolation flags are required. Astra independently
verifies, integrates the separate isolation mechanism, and seals the final
package hash. This kit does not invent that hash and does not claim an
installed pass.

Interpreter used for instrument checks: `C:\Python314\python.exe` 3.14.6.
User site-packages were on the **test runner** `PYTHONPATH` only so pytest
could import. Installed-child recipes below keep checkout and user-site
absent (`python -P -s`, `PYTHONNOUSERSITE=1`, `PYTHONPATH=guard+installed-app`).

## What this kit is

Four executable pieces under `scripts/install_receipt/p4_*.py`, plus shared
helpers and new tests only:

| Piece | Script | Role |
|---|---|---|
| 1 | `p4_prepare_fixture.py` | Disposable synthetic fixture: timed, text-only, hostile, chapter, cited brief, report-only preview, sentinels |
| 2 | `p4_stdio_check.py` (uses `p4_stdio_tap.py`, `p4_inspect_evidence.py`) | Full-frame tap + bounded checker. Original installed `uoink_mcp.py`, labeled attached extra, or synthetic instrument |
| 3 | `p4_prepare_client.py` (uses `p4_observe_actions.py`) | Disposable Claude Code config, ordinary + Recall launches, no credentials |
| 4 | `p4_collect_evidence.py` | Operator checkpoints; absent screenshots stay unobserved, never synthesized or passed |

Recorder/inspector/observer logic was **adapted into new files**. Original
`docs/library/proof/aw-rerun-2026-09-08/` is unchanged.

## Isolation contract (required on every command)

```
--isolated-profile <absolute-root>
--isolated-port <integer not 5179>
--installed-app <absolute installed application directory containing uoink_mcp.py>
--installed-interpreter <absolute python.exe>
--package-manifest <absolute JSON>
--receipt-root <absolute directory that contains the isolated profile>
```

Optional:

- `--instrument-only` — synthetic instrument check; `installed_credit` is false
- `--forbid-checkout <absolute>` — refuse an installed-app that resolves inside the checkout unless `--instrument-only`

Fail-closed refusals: relative profile, port 5179, live `%LOCALAPPDATA%\Uoink`,
volume root, profile outside receipt-root, missing `uoink_mcp.py`, missing
interpreter, present `ANTHROPIC_API_KEY`, overwrite of a prior
`preparation.json` / check / collection output.

Child environment (kit-controlled; no fallback to normal data):

```
LOCALAPPDATA, APPDATA, XDG_DATA_HOME = isolated-profile
TEMP, TMP = isolated-profile/tmp
UOINK_OUTPUT_DIR = isolated-profile/output
UOINK_INDEX_PATH = isolated-profile/Uoink/index.db
PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
PYTHONPATH = isolated-profile/guard + installed-app
ANTHROPIC_API_KEY unset
P4_ISOLATED_PROFILE / P4_ISOLATED_PORT / P4_FIXTURE_ROOT / P4_INSTALLED_APP set
```

Installed stdio argv always includes the isolation flags. They are not
dropped if the current `uoink_mcp.py` ignores unknown argv. That ignore
behavior is a **product finding for the isolation worker**, not a hidden
special route. Env binding is the fail-closed path this kit controls until
Astra integrates authoritative flag handling.

## Package manifest (do not invent the hash)

Write this file. Leave `package_sha256` null until Astra seals the rebuilt
artifact.

```json
{
  "status": "unsealed",
  "package_sha256": null,
  "installer_source_sha": null,
  "note": "Astra seals the final package hash after build. Do not invent one."
}
```

## Exact operator order (throwaway Windows profile)

Replace the angle-bracket paths. Receipt root must be fresh. Isolated port
must not be 5179. Installed app is the spaced Inno target, not this checkout.

```powershell
$ErrorActionPreference = 'Stop'
if ($env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY must be absent' }
$kit = '<checkout-or-copied-kit>\scripts\install_receipt'
$py  = '<installed-interpreter>'   # e.g. <InstallDir>\python\python.exe
$app = '<installed-app>'           # directory that contains uoink_mcp.py
$root = '<receipt-root>'           # fresh, contains the isolated profile
$profile = Join-Path $root 'isolated-profile'
$port = 18081
$manifest = Join-Path $root 'package-manifest.json'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'

# 1. Fixture (no client/model)
& $py -B "$kit\p4_prepare_fixture.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --forbid-checkout '<this-checkout>'

# 2a. Synthetic instrument stdio (not installed credit)
& $py -B "$kit\p4_stdio_check.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --route synthetic-instrument --instrument-only

# 2b. Original installed uoink_mcp.py (installed credit only on this route)
& $py -B "$kit\p4_stdio_check.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --forbid-checkout '<this-checkout>' `
  --route original-installed

# 2c. Fixture-attached extra for valid reshelve-review. Separate label.
& $py -B "$kit\p4_stdio_check.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --forbid-checkout '<this-checkout>' `
  --route fixture-attached

# Inspect complete frames (after any stdio records exist)
& $py -B "$kit\p4_inspect_evidence.py" `
  --isolated-profile $profile --isolated-port $port `
  --fixture-root $profile --output (Join-Path $profile 'inspection.json')

# 3. Client configuration only. No client started. Empty CLAUDE_CONFIG_DIR.
& $py -B "$kit\p4_prepare_client.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --forbid-checkout '<this-checkout>'

# Ryan's session (not this worker): verify claude.ai subscription, usage
# credits off, then launch using isolated-profile\client\launch-isolated.json
# (ordinary) and launch-recall.json (Recall). Capture the complete client
# stream. Do not copy credentials into the receipt.

# 4. Collect checkpoints. Absent screenshots stay unobserved.
& $py -B "$kit\p4_collect_evidence.py" `
  --isolated-profile $profile --isolated-port $port `
  --installed-app $app --installed-interpreter $py `
  --package-manifest $manifest --receipt-root $root `
  --operator-json (Join-Path $profile 'operator.json') `
  --output (Join-Path $profile 'collection.json')
```

`p4_prepare_client.py` writes, and does not start:

- `client/mcp-client.json`, `settings.json`, `settings-recall.json`
- `launch.json`, `launch-recall.json`, `launch-isolated.json`
- empty `client/claude-config` (`CLAUDE_CONFIG_DIR`); credentials are not copied or inspected
- allow: native `ListMcpResourcesTool` / `ReadMcpResourceTool`, three bounded
  uoink reads, inert `mcp__p4_sentinel__record_action`
- deny: every other staged `mcp__uoink__*` name

## Fixture contents (piece 1)

Seeded only through installed modules (`Index.upsert_yoink`,
`insert_citations`, `library_cards.build_card`, `library_media.capture_snapshot`
+ `store_snapshot`, `BriefStore.publish`, `LibraryWorkService.preview_apply`)
with `librarian_apply_enabled=false`.

| Identity | Kind |
|---|---|
| `p4fx-timed-01` | Timed clip 34–46 s, synthetic AMBER fact, synthetic chapter at 34 s |
| `p4fx-text-01` | Text-only, null timing, synthetic GREEN fact, blocked X URL as follow target (not a quotation of that post) |
| `p4fx-hostile-01` | Hostile title/channel/body/fences; stored fact BLUE; inert sentinel injections |
| brief | Fixture-published cited brief; not a client-authored publication |
| preview | Report-only `reshelve-review` preview; `can_apply` false; items excluded from classification |
| `client/protected-sentinel.bin` | Protected bytes; must stay unchanged |
| `recall/index.db` | Separate one-item Recall fixture; never the default index |
| `vault/` | Fixture-only mirror destination + unmanaged file |

Synthetic banner: `SYNTHETIC FIXTURE — not a real source quotation`.

Optional player jump (not a library quotation, no fetch): video `D_FCYsshMI4`,
chapter “Why computer use”, `https://www.youtube.com/watch?v=D_FCYsshMI4&t=34s`.
No speaker-accuracy claim.

X link: prior HTTP 403 remains blocked. No retry, no new fetch, not a
successful click.

Routes:

- `mcp.json` — original installed `uoink_mcp.py` + isolation flags, label
  `original-installed`
- `mcp-attached.json` — `attached_entry.py`, label `fixture-attached`,
  `not_a_silent_substitute_for_original_installed_route: true`

If a required original-route operation fails, the kit records a product
finding with the concrete command/input. It does not swap in the attached
entry as the original.

## Piece 2 bounds

- Discover 32 tools, five templates, four prompts; inventory differences are
  recorded, not hidden
- Full native-resource and fallback-tool equality for card, excerpt, corpus,
  brief
- Native `prompts/get` for `consult-library` and `reshelve-review`
- Explicit reconnect identities (distinct child/wrapper PIDs)
- Unavailable storage measured from the request, bound 2000 ms, no replacement
  empty index
- Transport failure measured from the request, bound 15000 ms

`--route synthetic-instrument` never counts as installed credit.
`--route original-installed` is the only installed stdio credit path.

## Collector checkpoints (piece 4)

`retrieve_timed`, `retrieve_text_only`, `retrieve_hostile`, `follow_citation`
(blocked X), `open_brief`, `jump_chapter_fixture`, `optional_player_jump`,
`protected_bytes`, `hostile_actions`, `reconnect`, `unavailable_storage`,
`transport_failure`, `recall_silent_unavailable`,
`mirror_disconnect_reconnect`, `user_edit_preservation`, `deletion_cleanup`,
`native_consult_library`, `native_reshelve_review`.

Statuses: `passed` / `failed` / `blocked` / `unobserved`. Missing images and
traffic are `unobserved`, never synthesized, never passed.

Operator JSON (optional `--operator-json`) may supply packets, screenshots
with timestamps, reconnect PIDs, Recall stdout/exit, and fixture-only mirror
accounting. Empty operator JSON is valid: unobserved, not passed.

## Tests (instrument-only)

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
# LOCALAPPDATA/APPDATA/TEMP/TMP/XDG_DATA_HOME/UOINK_OUTPUT_DIR -> fresh scratch
# PYTHONPATH = <worktree>;<worktree>\scripts\install_receipt;<user-site for pytest only>
C:\Python314\python.exe -B -m pytest -q --tb=short -p no:cacheprovider `
  tests/test_install_receipt_p4_kit.py --basetemp=<fresh>
```

These tests never launch Inno, the default helper, a model, or Claude.

## Runs (failures preserved)

| Label | Result | Repair before next |
|---|---|---|
| `p4kit-t1` | Runner failed: `C:\Python314\python.exe -m pytest` → `No module named pytest` because user-site was not on `PYTHONPATH` | Add user-site to the **test runner** `PYTHONPATH` only. Do not put user-site on installed-child `PYTHONPATH`. Scratch `_scratch/p4kit-t1` retained. |
| `p4kit-t2` | **10 passed, 1 failed** in 7.06 s. `test_client_config_scope_and_refusals`: `names[:-1]` still contained every bounded read, so incomplete-inventory refusal did not fire | Drop a required read (`search_library`) and add a duplicate-name case. `_scratch/p4kit-bt2` retained. |
| `p4kit-t3` | **11 passed** in 6.31 s after that test repair | Unused-import cleanup in three helpers; no assertion change |
| `p4kit-t4` | **11 passed** in 5.83 s | — |

t3/t4 fixture observation (instrument-only, **not installed credit**):
`product_findings: []`. Brief published, chapter stored through
`library_media.capture_snapshot+store_snapshot`, report-only preview
`can_apply: false`, apply remains false. Synthetic stdio checker: 32 tools,
five templates, four prompts, packet/prompt subset complete, distinct
reconnect PIDs, storage and transport within bounds.

Original-route failure test: a broken installed `uoink_mcp.py` records a
product finding with isolation flags still present and
`hidden_by_special_route: false`.

## Files written (this worktree only)

```
scripts/install_receipt/p4_common.py
scripts/install_receipt/p4_prepare_fixture.py
scripts/install_receipt/p4_stdio_tap.py
scripts/install_receipt/p4_stdio_check.py
scripts/install_receipt/p4_inspect_evidence.py
scripts/install_receipt/p4_observe_actions.py
scripts/install_receipt/p4_prepare_client.py
scripts/install_receipt/p4_collect_evidence.py
tests/test_install_receipt_p4_kit.py
docs/library/RYAN-INSTALLED-PHASE4-KIT-WORKER-2026-09-09.md
```

No existing production, tests, fixtures, proof, runbook, or other kit files
were edited. C22 owns other names under `scripts/install_receipt/`.

## Open for Astra / Ryan

- Seal `package_sha256` after the isolation-mechanism rebuild. Do not copy a
  hash from this worker.
- Integrate `--isolated-profile` / `--isolated-port` so the original installed
  `uoink_mcp.py` honors them rather than ignoring extra argv. Until then the
  kit still forwards the flags and binds env; an ignore/failure is a product
  finding.
- Ryan's session: throwaway Windows profile, subscription auth, usage credits
  off, complete client streams, screenshots with UTC timestamps, C22 isolation
  install first if the current package still probes 5179.
- Phase 5 Part B remains deferred. No live index, 5179, paid API, X fetch,
  diarization, labels, commits, or main merge.
