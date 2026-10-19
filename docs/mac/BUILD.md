# Build the macOS CI bundle

Run **macOS qualification** (`.github/workflows/mac-qualify.yml`) on a `mac/**`
branch or with `workflow_dispatch`. Its `mac-build` job now produces:

- `Uoink-<VERSION>-macos-arm64.dmg`, with an Applications shortcut and volume
  name `Uoink <VERSION>`.
- `uoink-<VERSION>-macos.mcpb`, the Darwin-only thin Claude Desktop connector.
- `uoink-<VERSION>-macos-arm64.tar.gz`, retained for bundle inspection.

The preceding hosted run built Python 3.13.16, the hashed wheel graph and LGPL
FFmpeg, then passed helper health, media/alignment, mirror gating, MCP 91/35
and immutable-bundle smoke. The DMG, whole-app ad-hoc signature, login startup
and client setup added in passes 7, 9 and 10 still need a hosted run.

Artifacts are private test builds. Ad-hoc signing establishes no developer
trust. Developer ID, notarization, the native UI pass and interactive Mac
acceptance remain pending. `LSMinimumSystemVersion` remains `14.0`; only
macOS 15 has hosted coverage. See [INSTALL.md](INSTALL.md) for draft user steps.

## Build locally on a disposable macOS arm64 machine

Use the `mac-qualified-wheels` artifact from the same workflow revision:

```sh
python3 -B scripts/mac/build_ffmpeg.py --output "$RUNNER_TEMP/mac-ffmpeg"
bash build-mac.sh --wheels "$RUNNER_TEMP/mac-wheels" \
  --ffmpeg-output "$RUNNER_TEMP/mac-ffmpeg" --output "$RUNNER_TEMP/mac-app"
python3 -B scripts/mac/bundle_smoke.py \
  --app "$RUNNER_TEMP/mac-app/Uoink.app" \
  --output "$RUNNER_TEMP/mac-smoke"
python3 -B scripts/mac/build_mcpb.py --output "$RUNNER_TEMP/mac-app"
version="$(cat VERSION)"
python3 -B scripts/mac/dmg_smoke.py \
  --dmg "$RUNNER_TEMP/mac-app/Uoink-$version-macos-arm64.dmg" \
  --mcpb "$RUNNER_TEMP/mac-app/uoink-$version-macos.mcpb" \
  --output "$RUNNER_TEMP/mac-dmg-smoke"
```

Use a new output directory. The builder refuses to overwrite one. CI sets a
disposable home, profile and output root before imports. The smoke test uses
its own isolated profile and an ephemeral loopback port, never port 5179.
It does not upload the profile or credentials.

The app's small native launcher has no system-Python fallback:

```text
Uoink.app/Contents/
  Info.plist
  MacOS/Uoink
  Helpers/uoink                 symlink-aware CLI shim
  Helpers/ffmpeg, ffprobe        static LGPL FFmpeg 8.1.2 CLI
  Frameworks/Python/             relocatable Python and installed wheels
  Frameworks/FFmpeg7/            LGPL 7.1.5 dylibs, only if TorchCodec decodes
  Resources/
    server.py, uoink_mcp.py, remaining application modules, uoink, VERSION
    helper/, uoink_core/, migrations/, defaults/, assets/, extension/
    skills/, voice_dna/, scripts/recall_hook.py, scripts/mac/uninstall.sh
    notices/, third-party-notices/, LICENSE
```

`Contents/MacOS/Uoink status` queries the helper and prints its capabilities.
`Contents/Helpers/uoink status` uses the bundled CLI. A user-created PATH
symlink resolves back to this shim. `Contents/Resources/uoink` remains a
forwarder to the app launcher.
Neither command starts the helper. Run the launcher without arguments to
start the headless helper, or pass `--helper` as login startup does. Finder and
interactive desktop behavior are not qualified by this build job.

The launcher, CLI shim and MCPB shim clear every `DYLD_*` variable and
`PYTHONHOME`, `PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONUSERBASE` and
`PYTHONEXECUTABLE` before executing bundled Python. The LaunchAgent runs
`Contents/MacOS/Uoink --helper` so login startup uses the same environment cleanup.

Signing runs inside-out: nested Mach-O files and code bundles first, then
`codesign --force --sign - --timestamp=none Uoink.app` last. The outer bundle
signing step signs `Contents/MacOS/Uoink` with its `Info.plist` bound; the main
executable is never signed separately. `codesign --verify --strict --deep`
verifies the completed app. Failures print the exit code and codesign stderr.
The launcher is compiled for arm64 with `-mmacosx-version-min=14.0`, and
`CFBundleExecutable` must be `Uoink`.

Developer ID signing will enable hardened runtime with `--options runtime`.
Start with no entitlements. Qualify bundled Python, native extensions and media
processing under that policy before release. Add `com.apple.security.cs.allow-jit`
only if a required JIT fails that qualification; consider
`com.apple.security.cs.allow-unsigned-executable-memory` only if a required
dependency demonstrably needs it. No entitlement is currently established as
necessary. Keep library validation enabled by signing nested code with the same
Developer ID; do not grant `com.apple.security.cs.disable-library-validation` or
`com.apple.security.cs.allow-dyld-environment-variables` by default.

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
  tracked files plus the individually reviewed `mac_files` additions; caches,
  state and credential files are excluded. Explicit additions allow testing
  an uncommitted worktree without staging files or moving refs.
- `scripts/mac/payload.json` also pins both FFmpeg source tarballs, sizes,
  SHA-256 hashes and signing-key fingerprint. `build_ffmpeg.py` verifies both
  byte checks before extraction and builds explicit LGPL components. The
  workflow caches verified output by pins, flags, recipe, compiler and SDK.
  See [FFMPEG.md](../../scripts/mac/FFMPEG.md) for component reasons, exact
  inputs, network use, source availability and the legal-review boundary.
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

**Bundled media availability is tested at runtime.** An interpreter under
`Uoink.app/Contents/Frameworks/Python` resolves FFmpeg only from that app's
`Contents/Helpers`, passes the location to yt-dlp and ignores ambient yt-dlp
configuration. Both executables must pass `-version`, and FFmpeg must decode
generated audio. Failure returns `media_requires_ffmpeg`. Environment variables
cannot relax this policy. A Darwin source/dev checkout uses PATH, as Linux does,
without the bundle self-test or codec restrictions. Windows/Linux retain their
existing behavior. Input and security validation precede the media gate.

Bundled Darwin podcasts use WAV because no native MP3 encoder exists in this build.
Video selection accepts H.264/VP8/VP9 and rejects AV1/unknown codecs. Chunked
downloads require FFmpeg HTTPS input, explicitly enabled through Apple Secure
Transport. There are no autodetected third-party libraries.

**WhisperX/alignment has a separate gate.** The builder patches FFmpeg 7 and
TorchCodec loader paths, ad-hoc signs changed binaries, and runs a generated
TorchCodec decode. A failed probe removes the shared runtime and records
`alignment_requires_torchcodec` plus its cause in `notices/torchcodec.json`.
A passing CLI test alone cannot enable WhisperX. PyAV's own wheel libraries
remain independently inventoried; they do not substitute for this probe.

`notices/ffmpeg/` records source pins, exact configure commands, actual enabled
components, compiler/SDK, build logs, LGPL-2.1 texts and build scripts.
`notices/build.json` records which payloads were retained. Source/relinking
and signing obligations still require legal review before distribution.

## Hosted acceptance and evidence

Before inventory, the builder removes absolute `LC_RPATH` entries outside the
bundle, `/usr/lib` and `/System/Library`, including paths left by wheel build
machines. Each removal uses a separate `install_name_tool -delete_rpath` call;
`native-rpath-removals.json` records the bundle-relative file and original rpath.
After all rewrites and resource writes, the builder ad-hoc signs nested Mach-O
files and code bundles from the inside out, then signs Uoink.app and its main
executable together. `--deep` is used only for the final
`codesign --verify --strict --deep` check. `signing.json` records the order and
`spctl --assess` output;
Gatekeeper rejection is expected until Developer ID signing and notarization.
The main app entry is compiled from `installer/mac/launcher.c`; it execs only
the bundled Python with `-B -s`. No credentials or signing certificates are used.

The build must fail on an incomplete graph, a changed hash, a missing source,
a Mach-O file without arm64, or any remaining absolute load dependency or rpath
outside the bundle and those two system directories. Other `/System/` paths
are rejected. Bundle paths must be inside the app both literally (after path
normalization) and through symlinks; an outside link pointing into the app
does not qualify, and bundle symlinks cannot escape it. The inventory reads
`otool` output again after edits and signing; `LC_ID_DYLIB` remains excluded
because it identifies the binary itself, rather than a load dependency.
`native-inventory.json` records architectures, hashes and `otool` output.
`file-inventory.json` records the entire app; `size.json` records its total file
bytes and entry count. The compressed archive preserves modes and symlinks.

After relocation, the job must prove bundled helper `/health`, bundled CLI
`status`, exact bundled MCP `tools/list` inventories (91/35), a Pillow image
write/read, both bundled media programs, generated audio converted to 16 kHz
WAV, a frame extracted from generated video, media availability and an
unchanged app tree. Retained TorchCodec libraries must decode again after
relocation without `DYLD_*` variables or Homebrew in PATH. The `mac-build-evidence` artifact keeps
the reports, hash lock, environment/SDK record and smoke output. Failed smoke
tests do not publish the app archive.

Generated smoke fixtures do not prove all compressed formats, live HTTPS/HLS
section downloads, model ASR/alignment, minimum-OS compatibility,
Gatekeeper acceptance, native UI, Chrome onboarding or real client setup.
Those remain release gates alongside real-format media acceptance, signing,
notarization, login/logout lifecycle and interactive Mac testing.

The portable suite explicitly skips the older enable/publication wiring tests
and publication-dependent mirror cases on Darwin. Their Windows/Linux coverage
is retained; `test_mac_capabilities.py` verifies Darwin refusals separately.
Those skips are intentional feature deferral, not Mac publication evidence.

## DMG and client acceptance

After signing, `hdiutil create -format UDZO` packages Uoink.app and an
`/Applications` symlink. `dmg.json` records SHA-256 and byte size. The Darwin
MCPB builder shares the entry-point, command and platform checks in
`scripts/mcpb_manifest.py` with the POSIX builder. It checks the ZIP payload
again after writing it. The Windows PowerShell builder retains its equivalent
entry command and entry-point checks.

The Darwin connector uses `/bin/bash` to check the selected install before
executing its Python with `-B -s` and `Contents/Resources/uoink_mcp.py`. This
allows a clear missing-install message even when that Python is absent. The
app selection defaults to `/Applications/Uoink.app`; CLI and dashboard output
always resolve the running app and do not use that default.

`dmg_smoke.py` mounts the DMG read-only, copies the app with `ditto` into a
temporary Applications folder with spaces, verifies the signature, runs the
existing relocated bundle smoke against that copy, verifies again, and detaches
in cleanup. The smoke also runs the Helpers CLI through a symlink for `status`
and `connect claude-desktop`, checks the Darwin MCPB, and generates a LaunchAgent
plist under a temporary HOME. It never bootstraps the agent on the runner.
Artifact upload happens only after these checks pass. The evidence artifact
keeps signing, DMG hash/size, native/file inventories and both smoke reports.

LaunchAgent behavior lives in `helper/mac_lifecycle.py`. Tests simulate
`launchctl` and use temporary home directories. `RunAtLoad: true` and
`KeepAlive: false` start once at login without a Quit or duplicate-launch restart
loop. Disable and uninstall parse the plist and require its first program
argument to resolve inside the verified app before any bootout or unlink.
A foreign or unverifiable definition is retained with an error. Bootout must
succeed before the owned plist is removed. Settings validate ownership before
saving, then flush the reply and run disable in a separate process session so
removal can finish after bootout stops the current helper. The uninstall
planner checks the bundle identifier and required files; execution uses the
shared Darwin process identity and termination adapter before app removal.
It preserves user data. No test should access the real user's Library.

Offline Windows checks cover relocated connect paths, Windows/Linux output
comparison against frozen v3.10.0 Git blobs, simulated launchctl, plist
contents, uninstall refusal/planning, signing order, DMG command construction,
MCPB manifests and ZIP contents, shell/YAML syntax, payload closure and the
static jobs in `ci.yml`. These checks do not execute Apple tools.

The next hosted run must prove compilation of the native entry, all strict
signature checks, DMG creation/mount/copy/detach, the relocated immutable-bundle
smoke, CLI output and the generated plist. The owner must provide Developer ID
certificates for the later signing pass and an interactive Apple Silicon Mac
for Gatekeeper, Finder, login/logout, Quit, Chrome, clients, Keychain and UI
acceptance. The provisional macOS 14 floor still needs qualification.

## Offline check record for passes 7, 9 and 10

On Windows, the targeted suite passed 322 tests. Seven skipped: five existing
symlink cases without Windows symlink privileges, the POSIX MCPB packer test,
and a native Darwin process test. Five process/protocol integration cases were
excluded from this offline selection. The full portable suite was not run.
Python network calls were blocked, and test home, profile, output and temporary
directories were inside the worktree. Credential-file reads were blocked.

The v3.10.0 source snapshots in `tests/fixtures/connect_v3100` came from the
local release tag. `baseline.json` records their Git blob IDs and SHA-256.
The comparison exercises every client, list output, stderr notes and both
deeplinks under simulated Windows and Linux branches. The fixtures also work
in CI's shallow checkout, which may not contain the release tag.

Static checks passed for Python compilation, nine shell scripts, workflow YAML
and 43 bash run blocks, JSON/version guards, 13 extension JavaScript files,
cached ESLint 8.57.1, the generated agent kit and the MCP inventory (91/35).
The reviewed Mac payload contains 168 source files. No dependency installation,
network fetch, commit, push or ref change was used for this verification.
