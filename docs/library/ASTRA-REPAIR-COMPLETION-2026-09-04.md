# Astra repair completion packet, 2026-09-04

**581 passed, 3 skipped, 1 xfailed, 171 warnings in 40.79 seconds.** Matching
profiles produced **zero card differences across all 548 items** between the
registry handler, dry run, and cost model, both before and after the copy rebuild.
Source-only staging and the installed-tree runtime test passed. This completes
the codex implementation section on base `ad44850`; independent review and
acceptance of an integrated candidate remain with the control room.

Git staging initially succeeded. Subsequent staging and the commit attempt failed
with `index.lock: Permission denied` in the shared Git metadata. **No commit was
created.** The worktree contains staged changes and later unstaged corrections;
the integrator must stage the final file contents, not commit the existing index
as-is. No merge or push was attempted.

Measurements are recorded in
[`ASTRA-REPAIR-MEASUREMENTS-2026-09-04.json`](ASTRA-REPAIR-MEASUREMENTS-2026-09-04.json).
The named source copy's SHA-256 matched the dispatch before copying and after
measurement: `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`.
SQLite opened only worktree-local duplicates. The live index was never opened.
Corpus prefixes referenced by the copy were read for opening-prose evidence;
the card hashes also cover that selected prose, so the DB hash is not the sole
fingerprint of this experiment.

| Measurement | Before | After |
|---|---:|---:|
| Clip rows | 3,216 | 3,705 |
| Rows with source intervals over 120 seconds | 1,729 | 435 |
| Rows with source intervals over 180 seconds | 72 | 271 |
| Longest source interval, seconds | 1,041.839 | 1,041.839 |
| Transcript-bearing items covered | 212 | 212 |
| Card caller mismatches, each profile | 0 | 0 |
| Largest Librarian packet, UTF-8 bytes including wrapper | 8,153 | 8,153 |

The increase in over-180-second rows reflects multiple text excerpts sharing a
single long source interval. All 435 remaining over-120-second rows represent
bounded excerpts of coarse cues: 114 distinct item/interval pairs, 45 of them
over 180 seconds. No ordinary merged window exceeds 120 seconds. Each coarse
excerpt has at most 1,200 characters and retains its original bounds and link;
the link points to the cue start, not an invented location within it.

Two explicit rebuilds took 1.935 and 1.854 seconds and produced identical payloads
excluding database row IDs. Payload SHA-256:
`d2eb5f2da8277a39e446eef99839684fc18a946b5aed7a4230d4ada0603f6928`.
SQLite quick check, foreign-key check, and external-content FTS integrity passed.
An injected `x_thread` row with metadata `source_type=x_article` in a separate
disposable copy became `x_article` on schema-26 upgrade.

**Implementation and file ownership**

| Files | Final change |
|---|---|
| `build.ps1`, `installer/uoink.iss` | Stage and install `clips.py`, `provenance.py`, `library_cards.py`, both CLI shims, and `scripts/install-watchdog.ps1`. Add `-StageSourceOnly`, using the production source-copy list and a new destination inside this worktree. |
| `library_cards.py` | Pure `build_card(item, clips, *, corpus_text, profile, n_clips, clip_chars, byte_budget)`; explicit read-only `build_cards(conn, ...)` adapter; shared `card_text` renderer. |
| `uoink_mcp_tools.py` | Only the two clip tools, their helpers and schemas changed. `get_evidence_card` adds `profile`; search results expose timing. |
| `scripts/librarian/dryrun.py`, `scripts/library/cost_model.py` | Replace copied card selection, construction and rendering with shared calls. Packing, model execution, pricing and verdict logic remain the other workers' scope. |
| `clips.py`, `index.py` | Close ordinary windows before exceeding 120 seconds, split long cues into bounded text, expose coarse timing, and repair oversized legacy clips once on open. |
| `provenance.py`, `migrations/0026_provenance_precedence.sql` | Explicit metadata kinds win before sidecar and platform inference. Reconcile populated rows using the same key priority and aliases. Migration 0025 remains unchanged; 0027 was not created. |
| `tests/test_clips.py`, `tests/test_library_cards.py`, `tests/test_phase0_provenance.py` | Timing, one-time upgrade, lossless coarse splitting, profiles, caller parity, byte budgets, prompt delimiter escaping, evidence absence, stable IDs, and all explicit-kind aliases. |
| `tests/test_installer_files_complete.py`, `tests/test_installed_library_runtime.py` | Walk reachable AST imports from all four entry points, including deferred and relative imports; verify both package lists; exercise the package-shaped runtime without the source checkout on `sys.path`. |
| `tests/test_podcast_corpus_bridge.py`, `tests/test_podcast_watch.py` | Replace two schema-25 assertions with the latest shipped schema. No podcast behavior changed. |
| `tests/repair_run_d_measure.py` | Reproduce the fingerprinted-copy measurements and assertions without helper or model execution. |
| This packet and its measurement JSON | Reviewable results and integration notes. |

`full` retains the existing response keys and defaults to ten untruncated clips.
Additional fields carry schema/profile/selection versions, source revision,
stable excerpt IDs, real intervals, evidence kind, hint type, truncation state,
and a card hash. `librarian` allows at most six excerpts of 240 characters and
8,192 serialized bytes, including its prompt wrapper. If the byte cap requires
less evidence, truncation is explicit. Existing full-clip reads remain available.

All copied items have evidence: 212 use `timed_clip`; 336 use `text_only` opening
prose. An empty fixture returns `evidence_kind=none` and
`status=insufficient_evidence`. Headings and metadata lines are excluded from
opening prose. Hints are labeled `opening_prose`, not summaries. Local path
columns never enter public cards; links accept only HTTP(S). The renderer escapes
boundary characters inside JSON and labels the payload as untrusted data.
No model was run to test whether it would obey an injection.

For integration, the dry-run wrapper defaults to `librarian`; the cost wrapper
defaults to `full`. Pass matching `profile` and excerpt limits when comparing
them. Gemini can use `library_cards.card_text` in the benchmark. Grok should
retain the shared builder/renderer calls when integrating packing changes.
Claude's stdio wrapper must forward `profile` to expose bounded cards to clients.

**Commands and limits**

Commands ran from this worktree. For pytest, `PYTHONPATH` was the worktree;
`LOCALAPPDATA` and `XDG_DATA_HOME` pointed to `tests/.repair-run-d/appdata`,
`UOINK_OUTPUT_DIR` to its pre-created `output` directory, and `TEMP`/`TMP` to
its `temp` directory.

```text
python -m pytest -q tests/ -p no:cacheprovider -rs --basetemp tests/.repair-run-d/pytest-final
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -StageSourceOnly -SourceStagePath tests/.repair-run-d/staged-complete
python tests/repair_run_d_measure.py --source C:/Users/hello/AppData/Local/AgentControlRoom/uoink-index-copy-2026-09-04-upgraded.db --out tests/.repair-run-d/measurement
python scripts/library/cost_model.py --index tests/.repair-run-d/measurement/frozen.db --json
git diff HEAD --check
git commit -m "Repair library packaging, evidence cards, clip timing and provenance"
```

The cost CLI smoke completed; its forecast/verdict remains Grok's repair and is
not claimed as operational acceptance. Initial tests exposed a missing fixture
field and two stale schema assertions; those were corrected before the final
full run. The installed-tree test uses host Python and installed third-party
packages, including their normal site initialization, while excluding the source
checkout. It tests imports, an index capture fixture, a populated pre-24 upgrade,
search, cards and rebuilds. It is not an embedded-Python installer execution.

The three skips were POSIX bundle execution, unavailable Windows symlink
privilege, and ffmpeg missing from PATH. The existing expected failure remains
the Unicode FTS finding. No Inno Setup build, native UI capture, media playback,
watchdog registration/recovery, or client acceptance was run. Watchdog assets
ship, but this patch does not register supervision or change existing autostart.
The source-only run omits the generated installer icon when absent.

Logs, staged trees and disposable databases remain under the untracked
`tests/.repair-run-d/` directory. Exclude that directory from commits. The open
handoff is independent review, restaging/commit by the integrator, and rerunning
affected checks after the other workers' changes land.
