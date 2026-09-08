# Phase 4 acceptance brief, third round (run AW-3, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Reviewer: Astra (codex). Contract:
`phase4-v1` ([PHASE4-CONTRACT-2026-09-08.md](PHASE4-CONTRACT-2026-09-08.md)). Your AW-2
verdict ([PHASE4-ACCEPTANCE-2-2026-09-08.md](PHASE4-ACCEPTANCE-2-2026-09-08.md)) left
D01-D04 and D07-D16 open with 26 reproductions in `test_phase4_aw2_acceptance.py`.
Candidate: the commit this brief lands in, on `cc/living-library`.

## What changed since AW-2 (`69fc6e1`)

| Commit | Content |
|---|---|
| `6559a71` | AV-4r (grok): `library_resources.py` backend open lock and sqlite busy-wait under the shared deadline (D01); `get_item` recheck after corpus admission (D02); complete explicit-path redaction (D03); preview refusal without the exception text (D04); `library_prompts.py`, `server.py` follow. AV-4m (gemini): `library_mirror.py` D07-D16 (source lock through replace, read/discovery recheck; store-init purge retry and interrupted cleanup; fresh resync exports shelf and brief, missed-refresh repair, scope cleanup keeps the local brief; dependency recheck at replace; deletion events while disabled and index-authoritative tombstones; recorded temp ownership only; cancellable replace after timeout and purge recheck of user edits; index intent on manifest failure; no re-adoption after ledger loss; escaped display labels); `library_briefs.py`, `server._mirror_event` follow. First-round unit tests aligned with these rulings (D11, D12) with contract comments in `tests/test_library_mirror.py` and `tests/test_library_mirror_wiring.py`. |
| `fd1825c` | Phase 6 BC-2 on the same branch: `server.py` capture path, `index.py`, `uoink_mcp*.py`, registry 88 and stdio 32 (a Phase 6 `export_cited_range` adapter). Not a Phase 4 surface, but it shares the adapters; run the inventory tests. |

Observed by Fable on the candidate: `test_phase4_aw2_acceptance.py` 28/28,
`test_phase4_aw_acceptance.py` 32/32, Phase 4 unit and inventory suites 152, Astra's tree
671 with the 62 open BA-3 (Phase 5) reproductions deselected.

## Rulings requested

1. Each of D01-D04 and D07-D16: closed, or the exact remaining repair with a reproduction.
   Where a repair satisfies only its particular inputs (your AW-2 note on D12), say so and
   supply the wider case.
2. The two legacy-test alignments (D11 wiring, D12 temp retention): confirm they follow
   your rulings rather than lowering a bar.
3. P4-14 / P4-15 (real client): state what the rerun on this candidate must show, so Fable
   can execute the real-client AW sessions once (Claude Desktop and Claude Code over
   stdio, no paid API).
4. P4-13 installed compatibility remains Ryan's (installed Inno receipt shared with
   Phase 3 C22).

## Suites

`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, no `ANTHROPIC_API_KEY`:

- `python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py`
- `python -B -m pytest -q -p no:cacheprovider tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py tests/test_stdio_clip_tools.py tests/test_phase0_registry_capture.py tests/test_docs_live_contracts.py tests/test_library_adapters.py`

No models, no resident helper, no port 5179, no live index; application and temporary
roots under your worktree's `_scratch/`.

## Output

`docs/library/PHASE4-ACCEPTANCE-3-2026-09-08.md` and, for open items,
`tests/library_work_astra/test_phase4_aw3_acceptance.py`. Do not edit implementation,
existing tests or contracts. Do not commit.
