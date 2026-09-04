# Phase 0 brief, 2026-09-04 (run B, codex only)

Read `docs/library/THE-LIVING-LIBRARY-2026-09-04.md` sections 4 and 8 ("Phase 0") and
`docs/library/DECISIONS-2026-09-04.md`. You are the single owner of Phase 0: bug fixes with
known files, not design. A separate codex worker is hardening the clip index in another
worktree and owns `clips.py`, the `index.py` search paths, the `uoink_mcp_tools.py` search
tools, and the three parity tests; stay out of those. You may add migration
`0025_source_type_backfill.sql` (0024 is clips; 0026 is reserved).

Rules: own worktree, commit as you go, do not merge or push, never touch the live index at
`%LOCALAPPDATA%\Uoink\index.db`. A read-only copy with the real data is at
`C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04.db`; query it to
size every repair before and after. Tests: `PYTHONPATH=. python -m pytest -q tests/ -p
no:cacheprovider`. Add a test for every fix.

1. **N3 helper liveness.** The helper was down about 20 h on 2026-09-03 while `/health`
   said ok. In `server.py`: `main()` must exit non-zero when the port bind fails; `--doctor`
   must exit 1 when the helper is not healthy or a migration is pending; `/health` must
   report the migration version and the last successful tick timestamp. Add
   `scripts/install-watchdog.ps1` that registers (or updates) the existing helper Scheduled
   Task with restart-on-failure (3 retries, 1 min apart) and documents the command in
   `docs/`. Do not run schtasks yourself; the user installs it.
2. **`source_type` backfill.** 461 of 537 items had NULL `source_type`. Write
   `0025_source_type_backfill.sql` plus a Python backfill in `index.py` (or a new
   `provenance.py`) that derives `source_type` from `platform`, the source URL in
   `metadata_json`, and the sidecar kind (video / podcast / x_post / x_article / page /
   reddit / note / image / short_video). New inserts must set it at write time. Report the
   before/after NULL count against the index copy.
3. **147 stranded podcast episodes.** `podcasts.py` near line 423 freezes
   `auto_ingest_requested` at insert time and the scheduler ANDs it with the feed flag (near
   line 570), so flipping a feed on never picks up its existing `status=new` episodes. Fix:
   compute eligibility at scheduling time from the feed's current flag (respecting the
   decision-5 caps: back-catalog 25 per source, 10 ingests per day per source) and add a
   one-time repair that re-evaluates `status=new` rows. Report how many of the 147 become
   eligible under the caps.
4. **N2 registry parity.** `uoink_url`, notes capture, image capture and X capture exist as
   helper endpoints but are missing from the HTTP/OpenAPI tool registry in
   `uoink_mcp_tools.py`. Register them (registry only, not stdio), with rate limiters, and
   update `docs/v2-mcp.md` counts. Coordinate the count: the other codex worker is moving
   the documented registry from 65 to 67; you add on top and state your final number in the
   handoff so the integrator can reconcile.
5. **N1 CLI.** Ship `uoink.cmd` (and a `uoink` POSIX shim) at the repo root that forwards to
   `python server.py` subcommands: `uoink doctor`, `uoink rebuild-index`, `uoink search
   <query>`, `uoink clips <query>` (the last two call the running helper's HTTP registry;
   print JSON). Document in README.
6. **N4 X truncation (stretch, only if 1-5 are green).** Long X posts are captured
   truncated. The known fix is the FxTwitter v2 API for the full text. Implement behind the
   existing X extractor with a test on a fixture; no live network in tests.

Handoff must list: per item the files changed, the measured before/after against the index
copy, test totals, and your final registry count.
