# S22 receipt: staged installed-tree run (2026-09-08)

Fable's evidence for contract `phase3-v1-2026-09-07` gate S22 ("installed disposable
candidate includes the new module/migration and registry schemas; no access to resident port
5179 or live index") and for Phase 4 P4-13's staged part, on candidate `c1e467d` (Phase 3
round-2 repairs at `d479899`, Phase 4 AV-1b at `82e973a`, Phase 5 AZ-2 at `619766b`). Astra
rules; this is a receipt.

## What was run

1. `build.ps1 -StageSourceOnly -SourceStagePath installer/staging-source-s22`: the
   production copy list staged into a fresh directory inside the worktree (141 files, tree
   SHA-256 `170d8f16…` over relative path plus bytes). No download, embedded Python, Inno
   Setup, task registration or installed helper. This is the installer's copy list, not an
   installer run: the real bundle's embedded Python and its site-packages were not
   exercised, and nothing was installed on this machine.
2. **Imports with the checkout absent.** A child interpreter with `PYTHONPATH` = the staged
   tree only (user site disabled) imported `source_subscriptions`, `library_resources`,
   `library_prompts`, `library_analysis`, `library_work`, `library_cards` and
   `uoink_mcp_tools` from the staged tree (each module's `__file__` asserted under
   `staging-source-s22`); registry 85 tools; `migrations/0028_source_subscriptions.sql`
   present.
3. **Real stdio session from the staged tree** in an isolated profile (`LOCALAPPDATA`,
   `APPDATA`, `TEMP`, `TMP`, `UOINK_OUTPUT_DIR` all set to `_scratch/s22-profile`;
   `ANTHROPIC_API_KEY` unset; the MCP SDK reached through the real user site-packages on
   `PYTHONPATH`, since the source-only staging carries no bundled interpreter):
   `initialize` (protocol `2025-11-25`, serverInfo `uoink 3.8.0`, capabilities
   `prompts`, `resources`, `tools`, `experimental`), `tools/list` 29,
   `resources/templates/list` 5, `prompts/list` 4, `tools/call search_library` (Phase 4
   envelope, fenced, zero hits) and `tools/call get_library_activity` (Phase 5 envelope,
   `contract_version phase5-v1`). Migrations 0001 to 0028 applied to the profile's fresh
   index. Diagnostics went to stderr; stdout carried only JSON-RPC.

## Observations Astra should weigh

- The isolated profile started empty and the backend **created a new index** there, so
  `search_library` answered an empty library rather than `library_unavailable`. That is
  Astra's open item D7 (`PHASE4-AV1-RULINGS-2026-09-08.md`): the contract forbids
  substituting a new empty database for unavailable storage. It is assigned to the Claude
  worker with Fable's `server.py` seam and is not repaired in this candidate.
- Nothing touched port 5179 or the resident data root: the profile directory contained only
  the `Uoink` folder the staged helper created for itself.
- An installed-build run of the actual Inno package (embedded Python, bundled
  site-packages, upgrade path) is still owed; it requires installing over or beside the
  live installation, which Fable does not do without Ryan.

The staging directory was removed after the run; the receipt's hashes and outputs are the
record. Commands and outputs are reproducible from the steps above.
