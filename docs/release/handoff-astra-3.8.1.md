# Uoink 3.8.1 implementation handoff

Status: items 1–5 implemented, with external verification gaps below.
97 distinct targeted tests passed. No full-tree run, installer build, install
test, merge or item-6 work was performed.

Worker: codex. Date: 2026-09-23 (America/Los_Angeles).
Branch: `control-room/5a4dd329-9f0-codex`.
Base: `d31ba188fc352f32b9b336d6625a52e31ce58ee9`.
Changes are uncommitted in the dedicated worktree.

## What changed

- All 32 stdio decorators now specify a title and all four hints. The same 32
  HTTP registry entries advertise matching metadata. The low-level stdio list
  handler no longer replaces complete annotations with two-field defaults.
- MCPB version is 3.8.1 and `privacy_policies` links to
  https://uoink.app/privacy. MCPB 0.4 forbids tool titles in its strict tool
  entries, so titles are on the live MCP surface only.
- Root and bundle READMEs describe local storage and network calls. The bundle
  README's stale 29-tool inventory now includes all 32.
- All six version surfaces are 3.8.1. The setup download link and its test are
  3.8.0. README/REQUIREMENTS install links remain at the published 3.8.0;
  their test now distinguishes published assets from the source version.
- Both modules that monkeypatch `os.name` to `nt` have non-Windows skip
  markers. Model-readiness fixtures canonicalize temporary roots before
  containment assertions and synthetic link resolution.

## Files changed

21 source/doc/test files:

| Area | Files |
|---|---|
| MCP | `uoink_mcp.py`, `uoink_mcp_tools.py`, `docs/mcp-tool-annotations.md` |
| Bundle | `.mcpb/manifest.json`, `.mcpb/README.md`, `docs/mcpb-bundle.md` |
| Release | `VERSION`, `helper/_version.py`, `extension/manifest.json`, `installer/uoink.iss`, `tauri-ui/src-tauri/src/main.rs`, `extension/setup.js`, `CHANGELOG.md`, `README.md` |
| Tests | `tests/test_c01_mcp_stdio.py`, `tests/test_release_version_v380.py`, `tests/test_installer_download_accuracy.py`, `tests/test_library_mirror_process_authority.py`, `tests/test_mirror_process_handle_lifetime.py`, `tests/test_reliability_model_readiness.py` |
| Handoff | `docs/release/handoff-astra-3.8.1.md` |

Generated, ignored output: `dist/uoink-3.8.1.mcpb` and
`build/mcpb/uoink/`. Scratch scripts, temporary test data and the failed npm
installation log are under ignored `_scratch/`.

## Commands and real results

Runtime: Windows, `C:\Python314\python.exe`, Python 3.14.6,
MCP SDK 1.28.1, pytest 9.1.1. Commands ran from this worktree.

Every pytest command used:

```powershell
$env:PYTHONPATH = (Get-Location).Path
```

Initial changed-file checks:

```powershell
python -m pytest tests/test_c01_mcp_stdio.py tests/test_release_version_v380.py tests/test_installer_download_accuracy.py tests/test_reliability_model_readiness.py tests/test_library_mirror_process_authority.py tests/test_mirror_process_handle_lifetime.py -q
```

Result: **47 passed in 5.20s**.

After clearing inherited `PYTHONPATH` in the stdio child, to prove its app-dir
pin actually works:

```powershell
python -m pytest tests/test_c01_mcp_stdio.py -q -s
```

Result: **4 passed in 1.10s**, with these live protocol checks:

```text
ok  initialize answers under -P (embeddable path rules)
ok  32 live stdio titles and all four hints match HTTP and audit
ok  tools/list returns exactly 32 canonical tools
ok  tools/call round-trips against the isolated index
```

This starts the real worktree `uoink_mcp.py` with `python -P`, sends
initialize/initialized/tools-list messages, then calls `list_recent_uoinks`.
It does not substitute a fake server. Initialization reports product version
3.8.1. The child uses disposable data/output directories.

CI-failure investigation:

```powershell
$env:LOCALAPPDATA = Join-Path (Get-Location).Path '_scratch/profile'
$env:UOINK_OUTPUT_DIR = Join-Path (Get-Location).Path '_scratch/output'
python -m pytest tests/library_work_astra/test_phase4_aw3_acceptance.py tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase5_measurements.py --basetemp=_scratch/t381 -q --tb=short
```

Result: **50 passed in 42.92s**. The first attempt without a worktree
`--basetemp` produced 50 setup errors: access denied to
`C:\Users\hello\AppData\Local\Temp\pytest-of-hello`. No test bodies ran
in that attempt. The rerun above used an allowed directory.

After canonicalizing all readiness fixtures:

```powershell
python -m pytest tests/test_reliability_model_readiness.py -q
```

Result: **12 passed in 0.13s**. The same command also passed **12 in 0.13s**
with TEMP and TMP set to an actual Windows 8.3 alias obtained via
`GetShortPathNameW`:

```text
C:\Users\hello\AppData\Local\AGENTC~1\WORKTR~1\UOINK-~3\5A4DD3~1\codex\_scratch\READIN~1
```

The short-path run used a child `python -m pytest` process with that environment;
no production readiness checks were loosened.

An AST evaluation of both platform skip expressions returned true for
`sys.platform="linux"` and false for `"win32"`. Both modules also ran
successfully in the 47-test Windows batch. Ubuntu itself was not run here.

CLI validation attempt:

```powershell
npm.cmd exec --cache .npm-cache --yes --fetch-retries=0 --fetch-timeout=20000 --package=@anthropic-ai/mcpb -- mcpb validate .mcpb/manifest.json
```

Result: **exit 1**, npm `EACCES` fetching
`https://registry.npmjs.org/@anthropic-ai%2fmcpb`; network sandbox prevented
installation. A prior invocation through `npm.ps1` was blocked by the local
PowerShell execution policy, so this attempt used `npm.cmd`. No official CLI
validation pass is claimed. Manual schema review follows.

MCPB rebuild:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-mcpb.ps1
```

Result: **exit 0**; built `dist/uoink-3.8.1.mcpb`, 73,704 bytes (72 KiB).
Staging and output paths were resolved and checked inside this worktree first.
This is the bundle packer, not the installer `build.ps1`.

A Python `zipfile` check returned no CRC errors. Parsed bundled manifest equals
the source manifest; both Python files, bundle README and icon match source
bytes. Exactly five entries: `icon.png`, `manifest.json`, `README.md`,
`uoink_mcp.py`, `uoink_mcp_tools.py`.

`git -c core.safecrlf=false diff --check`: **exit 0**, no whitespace errors.

## Manual MCPB schema validation

Compared every present field against the
[official 0.4 schema](https://github.com/anthropics/mcpb/blob/main/src/schemas/0.4.ts).
All pass; no unknown keys.

| Field | Check |
|---|---|
| manifest_version | Literal 0.4 |
| name | String |
| display_name | String |
| version | String, 3.8.1 |
| description | String |
| long_description | String |
| author | Object |
| author.name | String |
| author.url | URL |
| homepage | URL |
| documentation | URL |
| support | URL |
| privacy_policies | URL array |
| repository | Object |
| repository.type | String |
| repository.url | URL |
| license | String |
| keywords | String array |
| icon | String |
| server | Object |
| server.type | Allowed python |
| server.entry_point | String |
| server.mcp_config | Object |
| server.mcp_config.command | String |
| server.mcp_config.args | String array |
| server.mcp_config.env | String mapping |
| server.mcp_config.env.PYTHONPATH | String |
| user_config | Mapping |
| user_config.uoink_dir | Object |
| user_config.uoink_dir.type | Allowed directory |
| user_config.uoink_dir.title | String |
| user_config.uoink_dir.description | String |
| user_config.uoink_dir.default | String |
| user_config.uoink_dir.required | Boolean |
| tools | Array, 32 objects |
| tools[*].name | String |
| tools[*].description | String |
| compatibility | Object |
| compatibility.claude_desktop | String |
| compatibility.platforms | Allowed win32 |
| compatibility.runtimes | Object |
| compatibility.runtimes.python | String |

## CI failures from the brief

| Case | Disposition |
|---|---|
| Ubuntu WindowsPath crash | Added skip markers to the two modules that mutate global `os.name`; Ubuntu execution remains with CI/integrator. |
| `test_reliability_model_readiness`, RUNNER~1 | Fixed fixture path normalization; 12 tests pass using an actual 8.3 TEMP path. |
| AW3 d13 visibility/user-edit/later-sync cases | All three pass in the 50-test run. No timeout changes or xfails. |
| AW timed-out vault worker | Passes in the same run. No timeout changes or xfails. |
| Phase 5 measurements | Passes in the same run. No deadline or expected-output changes. |

The AW and measurement failures are **not reproduced**, rather than proven
fixed on GitHub's Windows runner. Python 3.14.6 here differs from CI's 3.11.
If they recur, retain the failing trace and environment details for Claude;
the assertions and service budgets are unchanged.

## Privacy comparison and open questions

The live [privacy page](https://uoink.app/privacy) could not be read: repeated
web-tool requests returned inaccessible/cache-miss errors, including the
homepage's Privacy link. A direct `curl.exe -L --max-time 25` request failed
with connection error 7. Therefore **live-page parity is unverified**.

The repository `docs/privacy-policy.md` is a draft that is not yet effective,
last reviewed 2026-07-23. It omits FxTwitter fallback, enabled background feed
polling, entity extraction and consented transcription model downloads. These
are differences from the updated README, not claims about the unavailable live
page. The draft was not edited or substituted for the live policy.

Claude/Ryan still need to:

1. Compare the README with the live policy and resolve any differences before
   directory submission.
2. Run official `mcpb validate` when network access permits.
3. Run the full tree with the integrator launcher, ig-native environment and
   `IG_FORBIDDEN_LIVE`, including the Ubuntu CI leg.
4. Build the installer with Windows PowerShell 5.1, then install-test on port
   18081 and verify `/health`. This worker did neither.
5. Set the 3.8.1 changelog release date when publishing; its entry is Unreleased.

The existing bundle is a thin launcher: it uses the user's installed helper.
Testing its archive does not prove that helper's installed version or behavior.

## Hashes

SHA-256 of final files and generated bundle:

| File | SHA-256 |
|---|---|
| `dist/uoink-3.8.1.mcpb` | `f4f9b9face9241e03f6943f9da9777c8c93a13f1753ddfde301c8a47cd453f08` |
| `.mcpb/manifest.json` | `44fbf0374848b7514176a4a5ee69bda2e2d5ab877bd8f610b1dce5cbf92cbde8` |
| `uoink_mcp.py` | `aeb1a090277192493593c91574977364c29fd33991df1e1767dae631b05a9fab` |
| `uoink_mcp_tools.py` | `9a310ac836e1d58642b9e23f079bc40aa21028e3e5ae72a793d234a194625c75` |

## Annotation table

32 titles; all 128 boolean hints explicit. Counts of true hints: read-only 20,
destructive 6, idempotent 26, open-world 8. Same table as
[the maintained audit](../mcp-tool-annotations.md). Capture/feed-fetch
destructive hints follow the brief's explicit rule; idempotence describes
repeated effects for unchanged inputs.

| Tool | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Justification |
|---|---|---|---|---|---|---|
| `uoink_video` | Capture video | false | false | false | true | Fetches the requested video and saves a corpus; another capture can fetch new source data. |
| `uoink_playlist` | Capture playlist | false | false | false | true | Fetches a playlist and starts a new capture job. |
| `get_job_status` | Get job status | true | false | true | false | Reads local job state. |
| `cancel_job` | Cancel job | false | true | true | false | Cancels work; repeating cancellation does not restart it. |
| `list_recent_uoinks` | List recent captures | true | false | true | false | Reads saved corpus metadata. |
| `search_uoinks` | Search captures | true | false | true | false | Searches the local library. |
| `search_clips` | Search transcript clips | true | false | true | false | Searches stored transcript windows. |
| `get_evidence_card` | Get evidence card | true | false | true | false | Reads saved metadata and excerpts. |
| `get_uoink_corpus` | Get saved corpus | true | false | true | false | Reads a local Markdown corpus. |
| `analyze_comments` | Analyze comments | false | true | false | true | Calls Anthropic with the saved key and replaces stored comment analysis. |
| `classify_hook` | Classify hook | false | true | false | true | Calls Anthropic with the saved key and replaces stored hook analysis. |
| `get_taxonomy` | Get hook taxonomy | true | false | true | false | Reads stored taxonomy rows. |
| `get_citation_map` | Get citation map | true | false | true | false | Reads stored transcript and screenshot citations. |
| `get_uoink_health` | Get capture health | true | false | true | false | Reads saved extraction health. |
| `find_mentions` | Find entity mentions | true | false | true | false | Searches saved entity mentions. |
| `get_transcript_reliability` | Get transcript reliability | true | false | true | false | Reads stored reliability spans. |
| `add_podcast_feed` | Add podcast feed | false | false | true | true | Registers a unique feed URL and enables future network polling; repeated registration reuses it. |
| `list_podcast_feeds` | List podcast feeds | true | false | true | false | Reads registered feed rows. |
| `remove_podcast_feed` | Remove podcast feed | false | true | true | false | Deletes the feed and tracked episodes; repeating leaves them absent. |
| `poll_podcast_feed` | Poll podcast feed | false | false | false | true | Fetches the feed and records discoveries; repeated polls can find new episodes. |
| `list_podcast_episodes` | List podcast episodes | true | false | true | false | Reads tracked episode rows. |
| `download_podcast_episode` | Download podcast audio | false | false | true | true | Downloads episode audio; reuses an existing nonempty canonical file. |
| `get_whisperx_status` | Get transcription status | true | false | true | false | Inspects local WhisperX availability and settings. |
| `transcribe_podcast_episode` | Transcribe podcast episode | false | true | false | true | Queues transcription that can replace a transcript and download models with consent. |
| `episode_to_corpus` | Publish podcast corpus | false | true | true | false | Publishes deterministic local files and replaces the episode's prior corpus and index snapshot. |
| `get_library_activity` | Get library activity | true | false | true | false | Reads local activity and source observations. |
| `search_library` | Search library | true | false | true | false | Returns bounded local search results. |
| `get_library_item` | Get library item | true | false | true | false | Reads a saved item's evidence card and resource URIs. |
| `read_library_resource` | Read library resource | true | false | true | false | Reads a bounded local library resource. |
| `get_library_brief_input` | Prepare library brief input | true | false | true | false | Reads and hashes brief inputs without acquiring a lease or changing data. |
| `publish_library_brief` | Publish library brief | false | false | true | false | Creates an immutable local brief; submission_key deduplicates retries. |
| `export_cited_range` | Export cited transcript range | true | false | true | false | Returns stored cues and citations without fetching, transcribing or saving. |
