# Build the macOS CI bundle

Run **macOS qualification** (`.github/workflows/mac-qualify.yml`) on a `mac/**`
branch or with `workflow_dispatch`. Its `mac-build` job now produces:

- `Uoink-<VERSION>-macos-arm64.dmg`, with an Applications shortcut and volume
  name `Uoink <VERSION>`.
- `uoink-<VERSION>-macos.mcpb`, the Darwin-only thin Claude Desktop connector.
- `uoink-<VERSION>-macos-arm64.tar.gz`, retained for bundle inspection.

Pass 11 hosted arm64 run `39552211211` passed the ad-hoc build, DMG smoke and
installed receipt. Pass 12 adds `mac-sign` after `mac-build` for Developer ID
signing and notarization. Run `39707190093` signed all 1,436 targets after the
G2 intermediate import fix, then hit the app's 30-minute notary wait timeout.
Submission `a85b5ddc-eff7-496a-af76-df93e91632ab` was still processing at that
timeout. Run `40237282753` then signed, notarized and stapled the app and DMG,
and that DMG passed interactive acceptance on a real Mac, including a
quarantined first open with no override.

Releases attach the DMG from `uoink-macos-arm64-signed`, built from the release
commit. The ad-hoc artifact establishes no developer trust.
`LSMinimumSystemVersion` is `15.0`, matching the hosted runtime coverage. See [INSTALL.md](INSTALL.md) for user steps.

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
  Frameworks/FFmpeg7/            LGPL 7.1.5 dylibs, only if TorchCodec decodes
  Resources/
    Python/                     relocatable Python, stdlib and installed wheels
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
start the helper and its menu-bar process, or pass `--helper` as login startup
does. Finder and interactive desktop behavior still need the acceptance checklist.

The launcher, CLI shim and MCPB shim clear every `DYLD_*` variable and
`PYTHONHOME`, `PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONUSERBASE` and
`PYTHONEXECUTABLE` before executing bundled Python. The LaunchAgent runs
`Contents/MacOS/Uoink --helper` so login startup uses the same environment cleanup.

Python's entire install lives under `Contents/Resources/Python`, including
stdlib, site-packages, extension `.so` files and dylibs. `MacOS` contains the
native launcher; `Frameworks/FFmpeg7` admits only Mach-O dylibs and their links.
FFmpeg headers, pkg-config files and notices are not copied into Frameworks.

After wheel installation, the builder removes Python's `include/`,
`lib/pkgconfig/`, `lib/python*/config-*-darwin/`, `share/`, stdlib `test/`,
`unittest/test/`, `ctypes/test/`, and all `bin/` entries except `python3` and its
real interpreter target. Every removed entry is recorded in `python-pruned.json`
beside the build and in `Resources/notices/`; `python-bin-pruned.json` retains
the console-script removal list. Tkinter, Tcl/Tk and idlelib remain in the
Python payload, but the Darwin picker uses a timed osascript subprocess.
No helper worker enters Tk. The splash and dashboard use pywebview Cocoa.

Signing runs inside-out: every Mach-O file anywhere in the app, including
Resources and the main launcher, then enclosing code bundles, then
`codesign --force --sign - --timestamp=none Uoink.app` last. The outer bundle
signing step seals `Contents/MacOS/Uoink` with its `Info.plist` bound.
`codesign --verify --strict --deep`
verifies the completed app. Failures print the exit code and codesign stderr.
The launcher is compiled for arm64 with `-mmacosx-version-min=15.0`, and
`CFBundleExecutable` must be `Uoink`.

## Developer ID signing and notarization

`mac-sign` runs on `macos-15` arm64 after `mac-build`. It downloads that job's
tar archive and Darwin MCPB without rebuilding. Tar preserves modes and links;
the signing pass replaces ad-hoc signatures, including the CLI script's xattrs.
This job and the status-only `notary-check` job use the `mac-release`
environment. The signing step receives:

- `MACOS_CERT_P12_BASE64`
- `MACOS_CERT_PASSWORD`
- `NOTARY_API_KEY_P8_BASE64`
- `NOTARY_API_KEY_ID`
- `NOTARY_API_ISSUER_ID`

Decoded files stay in a mode 0700 directory under `RUNNER_TEMP`. The job imports
the certificate into a temporary keychain with a random, masked password and
codesign access. It reads the imported identity name and requires team
`WTGFF582VY`, a public workflow value. Cleanup runs even after failure, restores
the previous keychain search list and deletes the temporary keychain and files.
No bundled code runs until cleanup succeeds.

Signing uses `--force --options runtime --timestamp`, the imported identity and
the temporary keychain. It signs every Mach-O file, scripts in Helpers/MacOS,
enclosing code bundles and finally Uoink.app. It never signs with `--deep`.
There are **no entitlement exceptions**: none has been proved necessary for
this payload. Library validation stays enabled; nested native code uses the
same identity. JIT, unsigned executable memory, disabled library validation
and `get-task-allow` are not granted. A hosted runtime failure must establish
the need for any later exception, which belongs only on its executable.

The archive scan opens ZIP, wheel, JAR, egg and tar payloads recursively, including
ZIP files detected by content. `nested-archives.json` lists each archive, native
members, action and before/after hashes. Native members and enclosing bundles
are signed with the same ordering before their archive is repacked; child
archives finish first. Archives without native code stay byte-identical.
Traversal, escaping links, excessive nesting or more than 8 GiB of expanded
archive data fail the job. The first hosted scan must establish the real
payload findings; offline tests use nested archive fixtures.

CI submits a ditto ZIP of the signed app without `--wait`, saves the submission
ID immediately, then checks `notarytool info` every 60 seconds. JSON can arrive
on stdout or stderr. The app has a 150-minute budget; the DMG has 90 minutes.
Each budget starts before upload and includes polling. Individual uploads have
a 15-minute process timeout; info calls have at most two minutes, bounded by
the remaining budget. `Accepted` permits stapling; `Invalid` and `Rejected`
fail and fetch Apple's log. An exhausted budget fails with the submission ID
and a command to check it later.

Set `NOTARY_APP_TIMEOUT_MINUTES` and `NOTARY_DMG_TIMEOUT_MINUTES` to positive
whole minutes to override the defaults. CI reads the matching GitHub Actions
variables from the repository or `mac-release` environment. The dispatch input
`notary_app_minutes` overrides the app variable, for example `210` with the
default 90-minute DMG budget. The combined budgets must be at most 300 minutes;
larger values fail before key import. The job limit stays at 350 minutes,
leaving at least 50 minutes for signing, packaging, smoke tests and cleanup.
The temporary keychain stays unlocked for up to six hours so the DMG can be
signed after a long app wait. The sign phase's `finally` cleanup and the
workflow's `always()` cleanup still delete it before any payload runs.

To check a slow submission, dispatch `mac-qualify.yml` with `notary_check_ids`
set to one to five comma-separated UUIDs. For the pending runs, use
`968ac10a-dc40-435f-89a5-85ddfb941ab9,a85b5ddc-eff7-496a-af76-df93e91632ab`.
Only the ten-minute `notary-check` job runs. It uses the p8 key, checks each
ID once, fetches logs for Accepted, Invalid or Rejected results, and deletes
the key even on failure. Read the status and created date in the job summary
and download `mac-notary-check` for JSON. It cannot cancel a signing run.

Once an app submission is Accepted, leave `notary_check_ids` empty and set
the dispatch input `notary_reuse_submission_id` to that UUID. This overrides
`NOTARY_REUSE_SUBMISSION_ID` from Actions variables for that run. CI tries
stapling and validating the freshly signed app before uploading a ZIP.
Success skips app submission; a pending status or a ticket that does not fit
falls back to a new submission. The full build still runs, and the DMG still
needs its own notarization. Reuse does not guarantee a short signing run.

CI builds the DMG from the stapled app, signs and submits the DMG separately,
then staples and validates its ticket. `dmg.json` is rewritten after DMG
stapling so its SHA-256 names the final bytes. App submission reuse never skips
DMG notarization.

After key deletion, CI verifies strict signatures, team, runtime flags, secure
timestamps and both tickets. It quarantines a DMG copy as a Safari download,
installs with ditto into a path with spaces, requires the app's quarantine
attribute, and assesses both app and DMG with spctl. It records
`syspolicy_check distribution` when available, launches through LaunchServices
with disposable paths and requires `/health` within 120 seconds. DMG smoke
and the strict installed receipt then run against the signed artifact.

Read `mac-signed-evidence` after a failure. `notary-*-submission.json` preserves
each new submission ID. `notary-app.json` and `notary-dmg.json` give the latest
status, elapsed seconds and budget. `notary-*-polls.jsonl` records every poll;
the numbered poll files retain redacted tool output. `notary-*-log.json` holds
Apple's issues for `Invalid` or `Rejected` submissions, when available.
`notary-app-reuse.json` records the optional reuse decision, with separate
info and stapler evidence. `codesign-sign.txt` records signing failures;
`quarantine/quarantine.json` records codesign, spctl and policy output.
Launch stderr and smoke output help locate hardened-runtime crashes.
`receipt/receipt.json` records the strict verdict and all existing runtime,
cleanup and isolation checks. Credentials and keychains are never uploaded.

## Inputs and reproducibility

- `scripts/mac/standalone-python.json` pins python-build-standalone release
  `20261013`, CPython `3.13.16`, archive size and SHA-256. The builder selects
  the arm64 `install_only` archive, checks its bytes before extraction, and
  rejects tar traversal and escaping links. It verifies the running Python
  version and architecture.
- Qualification uses the shipping pins in `requirements-installer-lock.txt`,
  excludes only `scripts/mac/dependency-exclusions.json`, adds the five hashed
  PyObjC 12.2.2 pins in `scripts/mac/ui-wheels.json`, and retains the reviewed
  source-wheel/NLTK patches. `payload.json` names that Darwin-only input. After a successful macOS 15 solve,
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

## Native UI in pass 8

The helper starts `helper.mac_menubar` with the bundle interpreter, `-B -s`
and a clean Python/loader environment. AppKit runs on that process's main
thread. HTTP polling uses a worker; a main-run-loop timer applies menu changes.
Direct AppKit calls allow `NSImage.setTemplate_(True)` without private pystray
APIs. The 18px and 36px images are monochrome alpha masks of the existing U
brand mark, displayed at 18 points. Status stays in the menu text.

The helper's existing bind check prevents repeated launches from spawning
another menu. A flock in the user data directory also admits only one menu
process. The lock file is retained so its inode cannot split into two locks.
Each child receives only the read end of an ownership pipe. Normal Quit closes
the writer and waits; helper death closes it in the kernel. EOF ends the UI
process even if its Cocoa thread is blocked. The helper makes one menu launch
attempt and never restarts it automatically. `/helper/ui` is authenticated
and reports the owned PID and whether its AppKit loop has connected.

Quit uses the existing authenticated `/helper/quit`. Menu and splash requests
to open a dashboard go through authenticated `/helper/dashboard`, so the
helper owns the new window and closing the splash cannot close it. The
dashboard and splash explicitly select Cocoa and open their URL in the default
browser if WebKit cannot start. The splash records VERSION after its page
loads, or after a successful browser fallback, in the existing user-data
sentinel. The native UI never chooses Python from PATH.

The Darwin folder picker runs `/usr/bin/osascript` with a 120-second timeout.
Cancellation, timeout, failed selection and a failed write probe retain the
old output folder. The dashboard gets a clear message, including where to
allow Files and Folders access. No Darwin path calls Tk in the helper.

The only Python clipboard writer found in the existing UI was the splash's
Windows clip.exe/PowerShell path. The dashboard and extension write text with
`navigator.clipboard.writeText`. Darwin adds `/usr/bin/pbcopy` with UTF-8 stdin
and a five-second timeout. Only the Darwin dashboard HTTP response redirects
its copy calls to a native bridge; a browser uses its ordinary clipboard API.
The shared HTML bytes and Windows/Linux responses stay unchanged. This covers
Markdown with base64 image links, configs, prompts, attribution and extension
paths. No current path writes a rich clipboard format, so NSPasteboard is not
needed. The Chrome extension continues to use Chrome's clipboard API.

`ui-wheels.json` pins pyobjc-core and the Cocoa, Quartz, WebKit and Security
framework packages at 12.2.2, with SHA-256 for each CPython 3.13 universal2
wheel. Hashes came from the release files on PyPI:
[core](https://pypi.org/project/pyobjc-core/12.2.2/#files),
[Cocoa](https://pypi.org/project/pyobjc-framework-Cocoa/12.2.2/#files),
[Quartz](https://pypi.org/project/pyobjc-framework-Quartz/12.2.2/#files),
[WebKit](https://pypi.org/project/pyobjc-framework-WebKit/12.2.2/#files), and
[Security](https://pypi.org/project/pyobjc-framework-Security/12.2.2/#files).
These are Darwin-only qualification inputs named by `payload.json`.
`source-wheels.json` stays limited to the two reviewed source builds.
Qualification adds the five packages to the pin count and combined graph;
the generated Mac lock carries their hashes. The Windows lock is unchanged.

Universal2 files keep both slices. `binary_inventory` requires arm64 but does
not require it to be the only slice, and checks loader paths across slices.
Retaining the upstream layout avoids a new binary rewrite step. It does not
make this arm64 app an Intel build. `signing_order` scans Mach-O magic under
the whole app, including PyObjC `.so` files under Resources/Python, before
signing enclosing bundles and Uoink.app. Offline tests cover those extensions
and universal2 inventory. Hosted strict codesign verification is still required.

The minimum is now macOS 15. The previous 12.0 reference plist contradicted
the 14.0 generated plist and compiler targets. Neither established support on
an older OS: passes 1 through 7 qualified the selected wheel graph and pinned
python-build-standalone 3.13.16 release 20261013 on macOS 15 only. Some wheels
have lower filename floors, including the PyObjC universal2 wheels and
[ONNX Runtime 1.27.0's macOS 14 wheel](https://pypi.org/project/onnxruntime/1.27.0/#files).
Those tags do not prove the whole app runs there. The standalone pin records
size and hash, not an older runtime test. FFmpeg's old 14.0 build target was
also a component target, not a whole-app result. The reference/generated
plists, launcher, FFmpeg build, DMG text and install docs now all say 15.0.
The 14 wheel probe remains diagnostic; only the 15 graph gates the build.

Both relocated and installed-copy smoke now import AppKit, Quartz, WebKit,
Security and pywebview's Cocoa backend without a webview window. They run the
real menu process, wait for its authenticated connection, inspect its bundled
command, launch again and count menu processes. Quit must stop helper and
menu. A relaunch followed by killing the owned helper must leave no menu
survivor. First-run windows are suppressed with a current sentinel only in
the disposable smoke profile. [ACCEPTANCE.md](ACCEPTANCE.md) covers visible
windows, light/dark menus, TCC, Notes and login sessions on Ryan's Mac.

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

**Bundled media availability is tested at runtime.** The real target of
`Uoink.app/Contents/Resources/Python/bin/python3` resolves FFmpeg only from that app's
`Contents/Helpers`, passes the location to yt-dlp and ignores ambient yt-dlp
configuration. Both executables must pass `-version`, and FFmpeg must decode
generated audio. Failure returns `media_requires_ffmpeg`. Environment variables
cannot relax this policy. Detection uses only `sys.executable`'s resolved location;
the module directory, working directory, other Python files and links pointing
outside the app do not establish bundle mode. A Darwin source/dev checkout uses PATH, as Linux does,
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
the bundled Python with `-B -s`. The ad-hoc build job uses no signing credentials.

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
`launchctl` and use temporary home directories. `RunAtLoad: true` with
`KeepAlive: {SuccessfulExit: false}` and `ThrottleInterval: 30` start once at
login and restart only after a crash, so a Quit or duplicate launch does not
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

The next hosted run must prove Developer ID signing, archive handling, both
notary acceptances and tickets, quarantine propagation and launch, signed DMG
smoke and the strict installed receipt. An interactive Apple Silicon Mac is
still required for Safari, Finder, login/logout, Quit, Chrome, clients, Keychain
and UI acceptance. macOS 15 is the minimum; macOS 14 is not supported.

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

## Offline check record for pass 8

Files changed for this pass:

| Area | Files |
| --- | --- |
| Runtime | `server.py`, `uoink_dashboard.py`, `uoink_splash.py`, new `helper/mac_ui.py` and `helper/mac_menubar.py` |
| Icon | New `assets/brand/menubar-template.png` and `assets/brand/menubar-template@2x.png` |
| Qualification and build | `.github/workflows/mac-qualify.yml`, `installer/mac/Info.plist`, `installer/mac/launcher.c`, `scripts/mac/build_bundle.py`, `build_ffmpeg.py`, `bundle_smoke.py`, `import_smoke.py`, `payload.json`, `qualify_deps.py`, `wheel_lock.py`, `FFMPEG.md`, new `scripts/mac/ui-wheels.json` |
| Tests | `tests/test_mac_bundle.py`, `test_mac_launcher.py`, `test_mac_qualification.py`, `test_log_and_early_errors.py`, `test_sec_import_and_errors.py`, `test_sec_public_surfaces.py`, new `tests/test_mac_ui.py` |
| Docs | `docs/mac/BUILD.md`, `INSTALL.md`, `QUALIFICATION.md`, new `ACCEPTANCE.md`, and `docs/mac-install.md` |

Windows verification used
`E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`
(Python 3.14.6) at BelowNormal priority. `PYTHONPATH` named this worktree,
`PYTHONDONTWRITEBYTECODE=1`, and `IG_FORBIDDEN_LIVE` named the live index to
block. A guarded source copy, home, output and temporary directories stayed
under `_scratch/p8`. The guard blocked credential-file reads, external network,
port 5179 and writes outside the worktree. Read-only Git inventory queries
used the real worktree, since the copied tree has no Git index.

The wrapper `_scratch/p8/run.py` invokes pytest with `-q`, no cache provider,
a disposable base directory and JUnit output. Commands and results:

| Command or selection | Result |
| --- | --- |
| `python -B _scratch/p8/run.py tests/` | Run once: 6,123 passed, 50 failed, 157 skipped, one expected failure and 19 subtests passed, in 23:23. |
| All `tests/test_mac_*.py`, splash/first-run tests, HTTP error/security tests, installer-download checks, `test_agents_connect.py`, both `test_agent_cli*.py`, `test_mcp_full_toolset.py`, `test_c01_mcp_stdio.py` | Final focused check: 1,124 passed, 24 skipped and six subtests passed, in 1:16. |
| `python -B _scratch/p8/run.py static` | Python compilation, nine shell scripts, 43 workflow bash blocks, JSON/version/log guards, 13 JavaScript parses, cached ESLint 8.57.1, generated agent kit, MCP inventory 91/35 and payload closure passed. |
| `git diff --check` and Windows lock comparison | Whitespace check passed; `requirements-installer-lock.txt` remains byte-identical to its HEAD checkout. |

Forty-five full-run failures came from three AST-based HTTP fixtures that did
not supply `sys` for the new Darwin guards. Those fixtures now supply it;
their complete test files pass in the final focused run. One failure came
from a Git `-C` inventory query inside the copied tree. The harness now maps
that read-only query to the worktree, and the check passes.

Four Windows receipt scenarios remain unverified in this environment:
`test_final_source_runtime_corrected_oracles`,
`test_synthetic_helper_scenarios_and_verdict`,
`test_repair_source_runtime_helper_and_oracles`, and
`test_truth_source_runtime_measured_scenarios`. Three encountered the guard's
credential-file read refusal. The fourth reported its isolated test port
already occupied. These are not counted as passes or as the named timing
flakes. The four recorded helper identities were checked and stopped using
executable and creation-time ownership checks after the run.

The known Windows timing cases all passed:
`test_timed_out_vault_worker_cannot_publish_after_return`, both parameters of
`test_d12_unowned_temps_are_never_inferred_from_name_or_text`, and
`test_d13_replace_syscall_cannot_complete_after_timeout`.
The full suite was not repeated after the fixture corrections; the final
focused run covers them and the last Mac UI edits. Logs and JUnit files are
under `_scratch/p8`. No macOS runtime result is claimed from these Windows
checks. The next hosted run must resolve the new wheel graph, import Cocoa,
sign the added native extensions and pass the real menu-process lifecycle
smoke. A runner without a usable WindowServer session will fail that smoke.
Visible windows, template tinting, TCC attribution, Notes paste and login
sessions still require [ACCEPTANCE.md](ACCEPTANCE.md).
