# Build the macOS CI bundle

Run **macOS qualification** (`.github/workflows/mac-qualify.yml`) on a `mac/**`
branch or with `workflow_dispatch`. Its `mac-build` job creates an unsigned
Apple Silicon `Uoink.app` and uploads `uoink-<VERSION>-macos-arm64.tar.gz` after
the bundle smoke test passes. This work has been checked offline on Windows;
the new hosted build and smoke test still need their first run.

The archive is a CI test artifact. It has no Developer ID signature,
notarization, DMG, LaunchAgent, menu bar, first-run UI or app icon. Darwin's
automatic tray and splash startup are disabled until the native UI pass.
The plist currently requires macOS 15, the tested runner target. The plan's
macOS 14 floor remains provisional; wheel filenames alone cannot establish it.

## Build locally on a disposable macOS arm64 machine

Use the `mac-qualified-wheels` artifact from the same workflow revision:

```sh
bash build-mac.sh --wheels "$RUNNER_TEMP/mac-wheels" --output "$RUNNER_TEMP/mac-app"
python3 -B scripts/mac/bundle_smoke.py \
  --app "$RUNNER_TEMP/mac-app/Uoink.app" \
  --output "$RUNNER_TEMP/mac-smoke"
```

Use a new output directory. The builder refuses to overwrite one. CI sets a
disposable home, profile and output root before imports. The smoke test uses
its own isolated profile and an ephemeral loopback port, never port 5179.
It does not upload the profile or credentials.

The app's small shell launcher has no system-Python fallback:

```text
Uoink.app/Contents/
  Info.plist
  MacOS/Uoink
  Frameworks/Python/             relocatable Python and installed wheels
  Resources/
    server.py, uoink_mcp.py, remaining application modules, uoink, VERSION
    helper/, uoink_core/, migrations/, defaults/, assets/, extension/
    skills/, voice_dna/, scripts/recall_hook.py
    notices/, third-party-notices/, LICENSE
```

`Contents/MacOS/Uoink status` queries the helper and prints its capabilities.
`Contents/Resources/uoink status` forwards to the same bundled launcher.
Neither command starts the helper. Run the launcher without arguments to
start the headless helper. Finder and interactive desktop behavior are not
qualified by this build job.

## Inputs and reproducibility

- `scripts/mac/standalone-python.json` pins python-build-standalone release
  `20261013`, CPython `3.13.16`, archive size and SHA-256. The builder selects
  the arm64 `install_only` archive, checks its bytes before extraction, and
  rejects tar traversal and escaping links. It verifies the running Python
  version and architecture.
- Qualification uses the shipping pins in `requirements-installer-lock.txt`,
  excludes only `scripts/mac/dependency-exclusions.json`, and retains the
  reviewed source-wheel/NLTK patches. After a successful macOS 15 solve,
  `wheel_lock.py` writes `requirements-macos-arm64-lock.txt` and
  `resolved-wheels.json` into the wheel artifact.
- Build verifies those files against `wheel-manifest.json` and every selected
  wheel's bytes. Installation uses `--no-index --require-hashes
  --only-binary=:all:` and runs `pip check`. There is no build-time dependency
  resolution against an index, source-build fallback or Homebrew dependency.
- The hash lock is generated from that run's resolved graph; it is **not a
  checked-in, permanently frozen macOS lock**. Preserve the wheel artifact and
  lock together to reproduce its dependency set. A later qualification may
  resolve different Darwin-only transitive packages. Promoting a reviewed
  lock to a release input remains necessary before public distribution.
- `scripts/mac/payload.json` records the reviewed Windows source payload with
  its Windows launch/watchdog scripts removed and version/license files added.
  The Windows builder and installer are unchanged. Tests compare the manifests
  and verify that every reachable local import is included. Copying uses
  tracked files only; caches, state and credential files are excluded.
- Build tooling is hash-pinned in `scripts/mac/build-tooling.txt`. The hosted
  `macos-15` image, Xcode/SDK and Actions major tags are not immutable inputs;
  their observed versions are recorded. Tar timestamps and build metadata also
  vary. This is a repeatable pinned-payload procedure, not a claim of identical
  archive bytes across runs.

All launch paths set `PYTHONDONTWRITEBYTECODE=1` and use `-B`; user site packages
are disabled. Pip installation uses `--no-compile`, and installed console
scripts resolve Python relative to their own directory. Runtime state belongs
outside the app. The smoke test checks file bytes, modes, symlink targets and
new/deleted entries before and after running it from a path with spaces.

## Deferred capabilities

**Library mirroring is unavailable on Darwin**, including source checkouts.
The stable code is `library_mirror_unavailable_macos`. Safe identity-bound
replacement/deletion has not been qualified there. Saved enabled settings
cannot bypass this gate. Settings project the capability and show mirroring
off; the dashboard disables mirror controls and displays the reason/code.

Both `/library/mirror` and `/library/mirror-intent`, and settings writes that
contain mirror fields, return HTTP 501 with `ok: false`, the stable `code`,
and `error.code`/`error.message`. Refusal happens before destination probes,
consent minting, index/ledger work or settings mutation. Even status and disable
report unavailable; they do not claim that vault files were changed.

There are no dedicated mirror tools in the existing MCP inventory. MCP
initialize instructions disclose the limitation, and `get_library_activity`
and `publish_library_brief` responses include `capabilities.library_mirror`.
Publishing a local brief remains supported; its result does not claim a vault
copy. The inventory stays at 91 full / 35 core tools. CLI `mirror <operation>`
on Darwin prints the refusal and exits 1; CLI `status` includes capabilities.
Windows and Linux keep their existing mirror behavior and safety checks.
Separate taste/user/script copying is outside this corpus-mirror capability.

**Media features need FFmpeg** (`media_requires_ffmpeg`) in this app bundle.
No reviewed, checksum-pinned macOS FFmpeg input was present in the offline
checkout. This pass therefore uses the explicitly permitted deferral instead
of copying Homebrew executables or inventing a source checksum. Frame capture,
podcast audio download and audio transcription refuse before their media work.
The dashboard, `/health`, CLI status and MCP initialize report the limitation.
Source checkouts and Windows/Linux keep their existing media behavior.

`notices/FFMPEG.md` records this decision and the proposed LGPL source-build
configuration. `notices/build.json` records FFmpeg as absent, with null source,
hash and configure flags. `notices/packages.json`, `resolved-wheels.json` and
the installed wheel license files describe the actual Python payload. PyAV's
bundled libraries do not qualify the missing CLI or TorchCodec ABI.

## Hosted acceptance and evidence

The build must fail on an incomplete graph, a changed hash, a missing source,
a Mach-O file without arm64, or a non-system absolute loader/rpath dependency.
`native-inventory.json` records architectures, hashes and `otool` output.
`file-inventory.json` records the entire app; `size.json` records its total file
bytes and entry count. The compressed archive preserves modes and symlinks.

After relocation, the job must prove bundled helper `/health`, bundled CLI
`status`, exact bundled MCP `tools/list` inventories (91/35), a Pillow image
write/read, and an unchanged app tree. The `mac-build-evidence` artifact keeps
the reports, hash lock, environment/SDK record and smoke output. Failed smoke
tests do not publish the app archive.

This does not prove decoding, ASR/alignment, minimum-OS compatibility,
Gatekeeper acceptance, native UI, Chrome onboarding or real client setup.
Those remain release gates alongside FFmpeg qualification, signing,
notarization, DMG packaging, LaunchAgent lifecycle and interactive Mac testing.

The portable suite explicitly skips the older enable/publication wiring tests
and publication-dependent mirror cases on Darwin. Their Windows/Linux coverage
is retained; `test_mac_capabilities.py` verifies Darwin refusals separately.
Those skips are intentional feature deferral, not Mac publication evidence.

Offline Windows verification for this change passed 167 tests and 19 subtests,
covering capabilities, real MCP SDK dispatch, dashboard controls, builder/lock
logic, qualification fixtures, Windows mirror behavior, settings, CLI and
podcast/Whisper regressions. Python compilation, YAML parsing, shell syntax,
extension/dashboard JavaScript syntax, JSON/version checks and the 91/35 MCP
inventory also passed. The source payload inventory contains 160 tracked files.
ESLint was unavailable locally and was not downloaded. The full test suite and
the new macOS build were not run on this machine.
