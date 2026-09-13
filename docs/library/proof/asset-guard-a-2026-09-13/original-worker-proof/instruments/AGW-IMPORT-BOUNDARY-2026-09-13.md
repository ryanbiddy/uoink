# Guarded import boundary for agw01/agw02 — 2026-09-13

The parent resolved the earlier wording before execution: the named existing
agw02 suites may execute the real runner/server under an explicit heavy-import
blocker. This permits the runner's existing unavailable-runtime branch; it does
not approve model or native-library imports. Existing tests remain unchanged.
The new eleven-case file still uses only selected AST function bodies.

`_scratch/agw_heavy_import_guard.py` is loaded by pytest `-p` before collection.
It refuses startup if any of the ten named heavy packages is already present,
then prepends a `sys.meta_path` finder that raises ImportError on actual package
discovery. Tests may still use their existing inert objects in `sys.modules`;
those are not real package imports. No fake runner replaces product code. The
packaged-decoder suite already stubs DLL registration while executing copied
runner source. The normal worktree is not an installed application.

The root checkout's existing verifier still supplies the path/network/provider
process guard, private data directories, pytest plugin isolation, logs and JUnit.
The launcher's additional offline flags and credential-variable scrubbing remain
active in its child environment. Both agw01 and agw02 use this declared profile;
results receive no native, model, installer, quality or speaker acceptance credit.

The launcher writes exact command, command hash and source/verifier/plugin hashes
to each fresh `agwNN-launch/plan.json` before starting that child. It rechecks all
those input hashes after completion. This file, the plugin and launcher are
scratch verification instruments; neither the shared verifier nor any existing
test or sealed proposal is edited.

Pre-launch plugin SHA-256:
`4a97b84d24edea4bca28958183ffc9dd442be0522f1b0a7b230e441630a879d9`.
Pre-launch launcher SHA-256:
`693b9bfe898270432b042eb7f497ce995f9037ed81e8dc0e8f4ed45c91a61376`.
The worktree has no `bin/torchcodec` directory, so its normal runner import does
not register an installed decoder directory. No library contents were inspected.
