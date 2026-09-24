# Brief: uoink 3.8.1 "directory-ready"

Dispatch after Ryan publishes 3.8.0. Owner: Astra (codex engine) implements in a Control Room worktree off `main` (after #269 merges) or off the published v3.8.0 tag; Claude integrates, runs the full tree with the integrator launcher, builds, install-tests, and drafts the release. Ryan publishes.

Finite scope. When every item below is done and verified, stop.

## Why

The Claude connectors / desktop-extension directory rejects bundles whose tools lack a `title` and `readOnlyHint` / `destructiveHint` annotations, and rejects any submission without a privacy policy in both the README and the manifest (`privacy_policies`). In 3.8.0 only 3 of 32 stdio tools carry annotations, none carry titles, and `.mcpb/manifest.json` has no `privacy_policies`. The official MCP Registry and Smithery also read this metadata.

## Items

1. **Tool annotations on every stdio tool** (`uoink_mcp.py`): each `@mcp.tool` gets `title` (short human name) and `annotations=ToolAnnotations(readOnlyHint=…, destructiveHint=…, idempotentHint=…, openWorldHint=…)` set truthfully per tool. Rules: tools that only read the local library → readOnly true. Tools that fetch from the internet (capture a URL, poll a feed) → openWorld true, readOnly false, destructive false. Tools that delete, cancel or overwrite → destructive true. Put the table (tool, title, hints, one-line justification) in `docs/mcp-tool-annotations.md`. Add a test that lists tools over real stdio and asserts every tool has a title and both hints set. Keep the HTTP registry descriptions in sync where the registry carries the same metadata.
2. **Manifest** (`.mcpb/manifest.json`): add `privacy_policies: ["https://uoink.app/privacy"]`, add the tool `title`s in the tools list if the manifest spec version supports it, bump `version` to 3.8.1, validate with the official `mcpb validate` (or `@anthropic-ai/mcpb` CLI), rebuild the bundle.
3. **README privacy section**: a short "Privacy" section stating what stays local, what network calls happen (capture fetches from the source you ask for; podcast feed polling you enable; FxTwitter fallback for truncated X posts; optional Anthropic calls only with your own key, entity extraction off by default), and a link to https://uoink.app/privacy. Must match the uoink.app privacy page; if they disagree, list the differences in the handoff instead of guessing.
4. **Version bump** to 3.8.1 across the six parity surfaces (`VERSION`, `helper/_version.py`, `extension/manifest.json`, `installer/uoink.iss`, `tauri-ui/src-tauri/src/main.rs`, `.mcpb/manifest.json`); `PUBLISHED_INSTALLER_VERSION` in `extension/setup.js` + its test → 3.8.0 (the version that is actually published). CHANGELOG 3.8.1 entry.
5. **CI**: platform-gate Windows-only tests so the ubuntu leg runs instead of crashing with `cannot instantiate WindowsPath` (a `conftest.py` collection hook or `pytest.mark.skipif(sys.platform != "win32")` on the Windows-only modules). Fix the 6 CI-only windows failures if they're test-environment issues (`RUNNER~1` short path in `test_reliability_model_readiness`, the aw3 d13 and aw_acceptance worker timeouts, phase5_measurements), or document them.
6. **Out of scope**: the #264 P1-contract integration (separate 3.9 train), signing, Mac, any Living Library feature work.

## Checks

- Full tree via the integrator launcher with the ig-native venv and `IG_FORBIDDEN_LIVE` → 0 failures beyond documented environment-only cases.
- `mcpb validate` passes; the stdio annotation test passes against the real server.
- Installer built with build.ps1 (Windows PowerShell 5.1, never `-Clean`); isolated install smoke on port 18081 → `/health` OK.
- Handoff with hashes, counts, and the annotation table.
