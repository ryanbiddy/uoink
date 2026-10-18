# Phase 4 acceptance brief (run AW, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase4-v1-2026-09-08`
(yours). Base: the commit this brief lands in. No worker runs a model, the resident helper,
or touches port 5179 or the live index. Do not commit.

## Integrated candidate

- AV-1b (`82e973a`), AV-1c fixtures (`d287685`), AV-1d rulings D1/D2/D6/D7 plus briefs
  (`a7863a0`), Grok's mirror module (`a01fa3c`, verified against Gemini's 25 tests) and
  mirror wiring (`d4d99bb`: settings, `/library/mirror-intent`, `/library/mirror`, guarded
  event seams in `server.py` and `library_work.py`, dashboard panel, 11 wiring tests).
  Phase 4 suites 124 of 124; inventories at 31 stdio tools, five templates, four prompts,
  87 registry tools; Grok's client docs, skill and bundle docs committed.
- **AW receipt** executed by Fable with the real Claude Code CLI 2.1.261 over stdio on a
  disposable duplicate of the measured copy:
  [PHASE4-AW-RECEIPT-2026-09-08.md](PHASE4-AW-RECEIPT-2026-09-08.md), raw transcripts,
  prompts, expected packet, copy manifest and client configs hashed in
  `docs/library/proof/aw-2026-09-08/`. Timed and text-only items matched the expected
  packet field for field; reconnect stable; `library_unavailable` on missing storage with
  no database creation; `CONNECTION_CLOSED` within 9 s when the child is down; injected
  instructions contained with only read tools called. Prompts and templates were not
  exposed by the client in print mode (fallback tool used), matching your protocol note.
- Not done: native prompt invocation and resource attachment (client affordance), the
  Recall hook adversarial pass, an isolated HTTP helper restart, the installed Inno build
  (needs Ryan).

## codex (GPT-6 Astra): review and rule

1. Re-run the Phase 4 suites (`tests/test_library_resources.py`,
   `tests/test_library_resource_trust.py`, `tests/test_library_prompts.py`,
   `tests/test_phase4_stdio.py`, `tests/test_library_briefs.py`, `tests/test_library_mirror.py`,
   `tests/test_library_mirror_wiring.py`) and the inventory suites yourself; report counts.
2. Review the code against P4-01 to P4-13 with your rulings (D1, D2, D6, D7 as repaired;
   D3, D4, D5, D8 as confirmed), the brief store against "Brief generation belongs to the
   client", the mirror and its wiring against "Opt-in corpus mirror" (consent separate from
   `obsidian_vault_path`, ownership manifest, atomic replacement, tombstones, purge,
   `purge_blocked_user_edit`, correction store untouched).
3. Weigh the AW receipt against P4-14 and P4-15: reproduce the expected packet from the
   duplicate if you wish (its manifest names the source copy and hashes); say what the
   receipt establishes and what remains a named condition.
4. Rule `PHASE 4 ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED` (named
   defects with exact repairs and reproducing tests under `tests/library_work_astra/test_phase4_*.py`)
   in `docs/library/PHASE4-ACCEPTANCE-2026-09-08.md`.

Files you may edit: `tests/library_work_astra/test_phase4_*.py` (new), the acceptance document.
