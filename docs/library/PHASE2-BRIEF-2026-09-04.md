# Phase 2 dispatch, stage 1 (run J), 2026-09-04: the substrate, no labels applied

Contract: `PHASE2-CONTRACT-2026-09-04.md` (`phase2-v1-2026-09-04`), normative drafts in
`phase2-contract/`. Protocol: `ORCHESTRATION-V1-2026-09-04.md`. Repair increment accepted at
`d83be1f` (run I). This brief is Fable's dispatch packet with the reservations the contract
asked for. Find your worker name and do only that section.

## Fable's reservations and decisions

1. **Base SHA:** the commit this file lands in. Repair-accepted candidate `d83be1f`; nothing
   but docs since.
2. **Migration 0027 reserved** for the substrate and allocated to Astra. 0026 stays provenance
   repair. Copy `phase2-contract/0027_library_substrate.sql` into `migrations/` unchanged
   except for defects you document; any change to the 16-table draft is listed in your packet.
3. **Interface freeze:** `phase2-contract/tool-schemas.json` is the frozen adapter interface
   for this stage. Astra may not change a schema without bumping the contract version in the
   file and saying so; Claude builds against it in parallel with an importable service stub
   until `library_work.py` lands.
4. **Shared-surface owners this stage:** `library_work.py`, `migrations/0027`, narrow `index.py`
   hooks = Astra. `uoink_mcp_tools.py`, `uoink_mcp.py`, `server.py`, dashboard, packaging =
   Claude. `tests/test_library_work_*.py`, crash runner, `scripts/librarian/` prompts and the
   frozen taxonomy = Gemini. Nobody touches `library_cards.py` or `clips.py` this stage.
5. **Service reviewer:** Claude audits Astra's transactions and forced-crash cases (contract
   ownership table). **Acceptance worker:** Astra, on the integrated SHA, in a later run.
6. **Initial fixed taxonomy for the proof:** derived from the 60-item gold set's shelf paths
   (`docs/library/gold-set-2026-09-04.json`): every top-level shelf with at least 5 gold items
   becomes a node; second-level nodes need 2. Gemini writes it as
   `docs/library/taxonomy-v1-2026-09-04.json` with definitions and include/exclude cues and
   a canonical hash. Ratified for the PROOF ONLY; it never applies labels.
7. **Hold-out split:** the 60 gold items are the held-out set (47 timed-evidence, 13
   text-only, remeasure). Coverage floor 0.80 per stratum; precision target 0.90 per the
   contract. Held-out labels never enter prompts, examples or the taxonomy definitions.
8. **Authoritative local records:** `%LOCALAPPDATA%\Uoink\library\` next to the index
   (`journal/` append-only JSONL with fsync, `pins.json` written via temp file + atomic
   replace, exclusive-create lock file). Preview approvals live in `library_previews`;
   the user-intent confirmation route is a dashboard POST that mints a short-lived token.
9. **Client and transport for the proof:** Claude Code `claude -p` over the HTTP registry
   on an isolated helper at port `5180` with its own data root; never the resident helper
   on `5179`. Dry-run scope: the whole 548-item copy, at most one retry per rejected result,
   wall-time budget 2 hours. Subscription only; no paid API calls; no spend authorized.
10. **`librarian_apply_enabled=false`** throughout. Apply and undo are implemented and
    tested on disposable databases but the shipping default stays off.
11. **Not in this stage:** the product proof itself (P2-7) and the installed-client gate
    (P2-6 second half). Those are run K after acceptance of P2-0 through P2-5.

Shared rules: own worktree; commit if git allows, else leave files and say so; never merge or
push; never open the live index; disposable copies of
`C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`
(sha256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`) for anything
that writes. No model execution. Tests: `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider`
(baseline 665 passed, 3 skipped, 1 xfailed). Completion packet at the end.

## codex (Astra): substrate and service

`migrations/0027_library_substrate.sql`, `library_work.py` (service: runs, manifests, leases
with attempt tokens, submissions with validation and idempotent stored responses, proposals,
previews with delta hashes, apply with operation keys and inverse journal, pins with intent
tokens, undo with stale-conflict rules, recovery/replay from the authoritative records in
reservation 8), narrow `index.py` hooks (transaction boundary, rebuild preserves pins). Gates
P2-0 through P2-5 with your own tests, knowing Claude re-audits and Gemini's independent
tests are the acceptance evidence. Commit in at least two steps: (a) migration + runs +
leases + submissions (P2-0 to P2-2), (b) preview/apply/pins/undo/recovery (P2-3 to P2-5).

## claude: adapters and audit

Against `phase2-contract/tool-schemas.json`: the six registry tools in `uoink_mcp_tools.py`
(HTTP registry; stdio exposure of the two read-only ones only, `list_library_work` and a
`get_library_status`, if that is in the schema set; otherwise none on stdio), the
`waiting_for_client` status on `/health` and the dashboard, the user-intent POST route and
token minting in `server.py`, `librarian_apply_enabled` default-off setting, packaging of
`library_work.py`. Import the service through one seam so a stub works until Astra's module
lands; parity tests that both transports return identical revisions. Then the audit: read
Astra's `library_work.py` when it appears in the integrated tree (next stage) is out of scope
for this run; in this run, write `docs/library/SERVICE-AUDIT-PLAN-2026-09-04.md` listing the
forced-crash and transaction cases you will run. You cannot run shell commands; write the
tests anyway, deterministic and small; the orchestrator runs them.

## gemini: independent tests, crash runner, frozen taxonomy

`tests/test_library_work_leases.py`, `_validation.py`, `_apply_undo.py`, `_recovery.py`
written from the contract text and `tool-schemas.json`, not from Astra's code (they may
xfail strict until the service lands; name the gate in each reason). A crash runner
(`tests/library_crash_runner.py`) that kills a subprocess at the three durable boundaries.
`docs/library/taxonomy-v1-2026-09-04.json` per reservation 6 with its canonical hash, and
`docs/library/holdout-split-2026-09-04.json` per reservation 7 with item ids and hashes.
Rewrite `scripts/librarian/prompts/assign.md` to consume the frozen taxonomy by `shelf_id`
and the librarian card profile; the prompt must never contain a held-out label.
