# Build the macOS CI bundle

Run **macOS qualification** (`.github/workflows/mac-qualify.yml`) on a `mac/**`
branch or with `workflow_dispatch`. Its `mac-build` job creates an unsigned
Apple Silicon `Uoink.app` and uploads `uoink-<VERSION>-macos-arm64.tar.gz` after
the bundle smoke test passes. The preceding bundle build and smoke passed
on the hosted runner without FFmpeg. Pass 6c adds the source-built media
payload; hosted run `39260530038` failed during FFmpeg configure. The repair
still needs a successful hosted build and bundle smoke test.

The archive is a CI test artifact. It has no Developer ID signature,
notarization, DMG, LaunchAgent, menu bar, first-run UI or app icon. Darwin's
automatic tray and splash startup are disabled until the native UI pass.
`LSMinimumSystemVersion` stays at `14.0`, as do the FFmpeg deployment flags.
Only macOS 15 is CI-tested; Python and wheel compatibility on macOS 14 remains
a release gate.

## Build locally on a disposable macOS arm64 machine

Use the `mac-qualified-wheels` artifact from the same workflow revision:

```sh
python3 -B scripts/mac/build_ffmpeg.py --output "$RUNNER_TEMP/mac-ffmpeg"
bash build-mac.sh --wheels "$RUNNER_TEMP/mac-wheels" \
  --ffmpeg-output "$RUNNER_TEMP/mac-ffmpeg" --output "$RUNNER_TEMP/mac-app"
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
  Helpers/ffmpeg, ffprobe        static LGPL FFmpeg 8.1.2 CLI
  Frameworks/Python/             relocatable Python and installed wheels
  Frameworks/FFmpeg7/            LGPL 7.1.5 dylibs, only if TorchCodec decodes
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
Modified binaries need re-signing: the builder ad-hoc signs each one after its
edits, before inventory and smoke testing. Developer ID signing belongs to the
later signing pass; the app is still an unsigned CI artifact for distribution.

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
notarization, DMG packaging, LaunchAgent lifecycle and interactive Mac testing.

The portable suite explicitly skips the older enable/publication wiring tests
and publication-dependent mirror cases on Darwin. Their Windows/Linux coverage
is retained; `test_mac_capabilities.py` verifies Darwin refusals separately.
Those skips are intentional feature deferral, not Mac publication evidence.

Pass 6c offline verification covers source pins and archive safety, cache
integrity, bundled resolution, decode-gated capabilities, format selection,
TorchCodec loader rewrites and existing Windows media regressions. Local
checks cannot compile or run the macOS binaries. The hosted run must produce
the build, native inventory and relocated smoke evidence described above.

The targeted Windows run passed 229 tests and 19 subtests. One existing
real-FFmpeg fixture skipped because no FFmpeg was installed locally. Python
compilation, YAML/JSON/version checks, five shell scripts and 36 workflow run
blocks passed syntax checks. All 13 extension JavaScript files passed parsing
and the cached ESLint 8 checks from `ci.yml`. The MCP inventory remains 91 full
/ 35 core, and the source payload remains 160 tracked files. Network access
was blocked during the Python tests; no dependencies were downloaded. The
full portable suite and the new hosted macOS build were not run locally.
