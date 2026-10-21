# macOS qualification, pass 2 repair

Pass 8 updates: the current minimum is macOS 15. The macOS 14 probe is
diagnostic only. The five PyObjC 12.2.2 wheel hashes are now reviewed inputs,
and Cocoa imports and installed menu-process checks are required. See
[BUILD.md](BUILD.md) and [ACCEPTANCE.md](ACCEPTANCE.md). The historical test
results below remain the pass-2 results.

The repair follows hosted arm64 run **39215500494** at commit `954198d`.
Import smoke passed with 91 full / 35 core tools and every dependency pin
resolved. Both portable Python versions had the same six failures. The
standalone download failed with HTTP 403, `rate limit exceeded`.

| Finding | Root cause and repair |
| --- | --- |
| Two zombie/exit assertions | The fixture supplied Linux `/proc` text but left `sys.platform` as Darwin. It now explicitly selects Linux. Separate Darwin fixtures verify `SZOMB` (5) and `ESRCH` before executable lookup; a native test waits for an exited child without reaping it first. Isolation now uses the same complete native observation as the other consumers. |
| Two read-only app startups | The hand-written copy list omitted `uoink_core` and `voice_dna/VOICE-DNA.md`. The fixture now consumes `build.ps1`'s staging list through the existing installer completeness helper. A portable completeness assertion checks all reachable modules and the voice resource. Startup deliberately exercises WhisperX being unavailable. |
| Resident-helper assertion | The test supplied only the legacy PID file and mocked legacy probes. Darwin requires `runtime-identity.json`. Separate fixtures now exercise both contracts, including a birth mismatch of one microsecond; the native child case also checks resident detection. |
| Live vault worker reported absent | The Darwin adapter required a birth identity even for a PID-only liveness query. Mirror probes now explicitly allow that query, while ownership checks still require a birth timestamp. |
| Lost birth precision | `created_ms` truncated native microseconds. Darwin records now retain fractional milliseconds and compare integer microseconds after JSON round-trip. Isolation parsing, mirror comparisons, subscription records and the receipt adapter preserve the fraction. Windows timestamps remain integers. |
| Inconsistent executable and lease checks | Mirror and subscriptions now request executable-bound observations through the shared adapter. Subscription children persist their own executable, including ffmpeg. Missing child executable evidence remains unknown. Mirror passes its lease tolerance through in milliseconds; ownership defaults to zero. |
| Standalone download failure | The unauthenticated moving release endpoint hit GitHub's rate limit. `standalone-python.json` pins release `20261013`, both Python 3.13.16 arm64 asset names, sizes and SHA-256 values from the successful run-1 report. CI supplies its token through the environment for API metadata only. HTTP failures print their status and persist it in the report; pinned hashes are mandatory even if GitHub omits a digest. |
| Linux qualification unit failure | Wheel-set validation imported pip's private vendored parser. It now uses `packaging.version`, with a regression that makes pip unavailable. |
| Moving qualification tooling | `build-tooling.txt` hashes pip 26.1.2, setuptools 83.0.0, wheel 0.47.0 and packaging 26.2. Workflow and source builds use that file. Portable tests pin pytest 9.1.1, Pillow 13.0.0 and mcp 1.30.0, the versions observed in both hosted legs. |

The local repair checks use the requested Windows interpreter, BelowNormal
priority, `IG_FORBIDDEN_LIVE`, and a guarded source copy under `%TEMP%`.
They make no external connections and exclude the live installation and port
5179. CI static checks pass, including 13 JavaScript parses, cached ESLint
8.57.1, Python compilation, JSON/version checks, bash syntax and the 91/35 MCP
inventory. The workflow YAML also parses. The full suite was not rerun.
The 47-file targeted run completed in 17:30: **715 passed, 5 skipped,
6 subtests passed**. The skips are two existing absent-proof-archive cases,
the Darwin unreaped-child case and the two POSIX read-only cases. Its six
warnings are existing `utcnow()` deprecations in podcasts/mobile playlists.
The final adapter recheck passed **20 tests, 1 native skip**; qualification
unit tests passed **19 tests**. These rechecks overlap the targeted selection.
All standalone pins were compared offline with run 1's download report, and
all four tooling hashes with retained wheel evidence or PyPI metadata.
Repair evidence is under `%TEMP%/mr-6d91/`: `targeted.txt`, `targeted.xml`,
`selection.txt`, `adapter-final.xml`, `native-final.xml` and `static.json`.
WSL startup was denied by the local environment, so Linux runtime confirmation
remains pending alongside the hosted Mac checks.

Files changed for this repair:

| Area | Files |
| --- | --- |
| Process identity | `_platform.py`, `uoink_install_isolation.py`, `library_mirror.py`, `source_subscriptions.py`, `scripts/install_receipt/process_identity.py` |
| Qualification | `.github/workflows/mac-qualify.yml`, `scripts/mac/qualify_deps.py`, `scripts/mac/import_smoke.py`; new `scripts/mac/build-tooling.txt`, `scripts/mac/portable-tests.txt`, `scripts/mac/standalone-python.json` |
| Tests | `tests/test_install_isolation_repair.py`, `tests/test_mac_process_identity.py`, `tests/test_mac_state.py`, `tests/test_mac_qualification.py`, `tests/test_mcp_full_toolset.py`, `tests/fixtures/mac_qualification.json` |
| Report | `docs/mac/QUALIFICATION.md` |

Hosted confirmation is still required for both Python portable suites, native
libproc behavior (especially an unreaped child), read-only helper/MCP startup,
the real vault worker, and authenticated downloads with the pinned hashes.
The offline fixtures do not provide those results. Windows user behavior,
`ci.yml`, `build.ps1`, the Windows dependency lock and third-party notices are
unchanged. No commits, pushes or ref changes were made.

The following records the pass-2 scope and earlier evidence, with the adapter
and qualification descriptions updated for this repair.

Pass 2 separates Darwin application resources from writable state, supplies
native process identity and repairs the three missing-wheel paths in Job B.
The code and offline Windows checks do not establish a passing Mac build.
The orchestrator must push and rerun `mac-qualify.yml`; this pass performs no
network requests, commits, pushes or git-ref changes.

The pass-1 baseline is macos-15 arm64 run **39203865751**. Both Python 3.11 and
3.13 reports contain the same 24 failures across eight modules. Of 136 included
pins, 133 had compatible public wheels. The other three were the two pure-Python
source releases and the reviewed local NLTK patch. Import smoke could not install
that incomplete set.

| Failing module | Count | Cause and pass-2 change |
| --- | ---: | --- |
| `test_install_isolation` | 7 | Four assertions inherited the workflow's global profile/5187 binding. Job A now uses a disposable HOME without a global isolation binding. Three helper/stop cases lacked Darwin creation or executable identity; they now use libproc. Helper startup also avoids reverse DNS on Darwin. |
| `test_install_isolation_integrator_review` | 3 | `/proc` returned no creation identity. The shared adapter supplies it; missing and mismatched identities still fail ownership checks. |
| `test_install_isolation_repair` | 2 | Current-process and owned-child creation identities were missing. Native start-time and zombie/exit observations repair those checks. |
| `test_proof_run` | 8 | The helper missed its 30-second startup deadline. Logs show a consistent 35-second pause between migration and index initialization, across the HTTP bind that calls `getfqdn()`. Reverse DNS is the inferred cause; Darwin now binds through `TCPServer` without it. The ambient isolation binding is also removed from Job A. The hosted rerun must confirm that this removes the observed stall. |
| `test_image_capture` | 1 | Ambient isolation restricted `/file` to the global profile while the test wrote to its own output root, yielding 403. Removing the workflow binding restores the intended context without weakening `/file` authorization. |
| `test_isolated_credential_store` | 1 | The ordinary-mode test inherited an isolated binding. Job A no longer supplies one. Credential behavior is unchanged. |
| `test_library_mirror_wiring` | 1 | The ambient binding redirected settings to one shared profile, bypassing each test's temporary `SETTINGS_PATH` and leaking enabled state. Job A no longer supplies that binding. |
| `test_s6_suite_integration` | 1 | The fixture expects the ordinary 5179 address; the workflow forced 5187. Removing the binding restores the fixture's context. This assertion does not contact 5179. |

No existing failure is skipped. Existing Windows-only mirror-publication guards
remain. The new read-only-app cases have a POSIX permission guard: Windows mode
bits cannot prove a Windows ACL boundary. They run on the hosted Mac.

The shared Darwin adapter in `_platform.py` uses `/usr/lib/libproc.dylib`: `proc_pidinfo` with
`PROC_PIDTBSDINFO` supplies PID, state and birth time; `proc_pidpath` supplies the
executable. It checks the full 136-byte BSD-info response and PID. Birth time
retains native microseconds while collecting an executable observation, with
before/after reads rejecting mixed incarnations. Darwin records use epoch
milliseconds with a microsecond fraction; comparisons decode that fraction at
native resolution. Windows records retain integer milliseconds. Darwin neither parses locale-dependent
`ps` output nor reads `/proc`.

`ESRCH` and zombies establish death. Denied access, short responses, missing
timestamps, failed executable queries and unavailable APIs remain `unknown`.
An exact timestamp mismatch identifies a different incarnation. Executable
comparisons use filesystem identity; isolation path comparisons also use
`samefile` and ancestor identities for `/var` aliases and case-insensitive APFS.
Case-sensitive volumes retain distinct names. Windows handle APIs and Linux
procfs branches are retained. The adapter stays in an already-installed module,
so it adds no file to the Windows installer. The existing installer completeness
test checks that choice without an exemption.

The adapter serves install isolation, source subscriptions, library mirror and
install receipts. Ordinary Darwin MCP resident detection now reads a complete
helper identity record, rather than inferring ownership from a PID file's mtime.
This does not establish handle-bound Darwin termination or descendant cleanup:
the existing POSIX check-then-signal interval remains a lifecycle-pass concern.
No claim of Windows Job Object equivalence or safe Mac mirror publication is made.

Let `APP` mean the directory containing `server.py` (eventually
`Uoink.app/Contents/Resources`), `DATA` mean
`~/Library/Application Support/Uoink`, and `PROFILE` mean an explicitly declared
isolated profile.

| State | Darwin before → after | Windows, unchanged |
| --- | --- | --- |
| Token | `APP/token.txt` → `DATA/token.txt`; isolated mode retains `PROFILE/token.txt` | `APP/token.txt`; isolated: `PROFILE/token.txt` |
| Rotating log | `APP/server.log[.1–.3]` → `DATA/server.log[.1–.3]`; isolated: `PROFILE` | `APP/server.log[.1–.3]`; isolated: `PROFILE` |
| PID | `APP/server.pid` → `DATA/server.pid`; isolated: `PROFILE` | `APP/server.pid`; isolated: `PROFILE` |
| Runtime identity | Ordinary mode gains `DATA/runtime-identity.json` and its temporary sibling; isolated mode retains `PROFILE/runtime-identity.json` | Existing isolated identity stays in `PROFILE`; ordinary mode unchanged |
| Edited topics | `APP/topics.json` and `.json.tmp` → `DATA/topics.json` and `.json.tmp`; isolated: `PROFILE` | `APP/topics.json` and `.json.tmp`, including isolated mode |
| Editable extension/prompts | `APP/extension` → `DATA/extension`; isolated: `PROFILE/extension` | `APP/extension` |
| Splash sentinels | `.first-run-done` / `.extension-loaded` normally used `DATA`, but fell back to `APP` on resolver failure; now the fallback also uses `DATA`. Isolated mode retains `PROFILE`. | Existing data/profile paths and `APP` error fallback unchanged |
| Bytecode | Source-adjacent `__pycache__` writes disabled by Darwin helper, MCP, splash and dashboard entry points; workers inherit `PYTHONDONTWRITEBYTECODE=1` | Unchanged |

Topics read packaged defaults until the first edit. That edit preserves other
keys, including the fallback, and writes only the override. Subsequent reads use
that override. The unpacked extension copy is created on demand; a version change
refreshes packaged files while preserving `prompts.json` and user-added files.
Its version stamp is written last so interrupted copies retry. Helper
open-prompts/open-extension and splash onboarding use the same resolver.
Interactive Chrome onboarding remains a later acceptance task.

Settings, index, jobs, taxonomy, models, source-instance records and runtime leases
already use data/profile directories. Darwin
creates a new data directory with mode 0700; tokens and ordinary identity records
use 0600. Existing Windows filenames, paths, installer payload and layout remain
unchanged. `build.ps1`, the Windows lock and `THIRD-PARTY-NOTICES.md` are not modified.

`tests/test_mac_state.py` copies the app into a temporary read-only tree, then
starts the helper and both MCP toolsets against disposable state, in ordinary
and isolated modes. It edits topics, rotates the log, checks PID/identity/database
locations and verifies exact 91/35 tool inventories. Mode bits, a write-audit hook
and before/after file hashes cover the app tree. On Darwin it removes ambient
bytecode-disable settings so entry points must enforce the policy. Native ABI
fixtures cover denied/partial queries, zombies, missing paths and PID reuse;
live-child tests cover exact identity, mismatch and exit. POSIX and libproc runtime
results remain pending hosted execution.

Run `mac-qualify.yml` with `workflow_dispatch`, or push a branch matching
`mac/**`. Read the uploaded reports before treating a green workflow as evidence
of Mac support. Portable tests and import smoke have job-level
`continue-on-error: true`; their failures are expected to inform later passes.
The required jobs and matrix in `ci.yml` are unchanged.

Every job requests `macos-15` and an arm64 Python. This explicit OS label avoids
the moving `macos-latest` alias and lets the runtime probe use wheels that need
macOS 15. Each job records and checks the actual architecture. A runner or
interpreter reporting anything other than `arm64` fails that check. The image
can still receive updates; the log records `uname -m`, `sw_vers`,
`xcode-select -p`, Python version/build/configuration, and `pip freeze --all`.
The original macOS 14 proposal was not runtime-qualified. Pass 8 sets the
minimum to macOS 15, the OS used for hosted runtime checks.

| Job | Evidence |
| --- | --- |
| A, portable tests | `tests/` and `pytest Pillow "mcp<2"` on Python 3.11/3.13. Disposable HOME and OS data/cache directories, without a global isolation binding. Individual tests retain explicit isolation. Each run uploads JUnit XML and environment details. |
| B, dependency graph | Builds the three reviewed local wheels, then probes included pins for CPython 3.13 at both `macosx_14_0_arm64` and `macosx_15_0_arm64`. Combined resolvers use `--find-links` for built wheels. Missing packages and failed builds remain failures. |
| C, import smoke | Rejects missing pins or changed wheel hashes before installation. A fresh venv installs the complete selected set with `--no-index --no-deps`, runs `pip check`, imports, and actual `initialize`/`tools/list` exchanges for 91 full and 35 core tools. |

All jobs set a disposable HOME, profile, output, and platform data/cache
directories before product imports. This matters because `server.py` creates
its log handler while importing. Jobs B/C use isolation port 5187; Job A lets
each test choose its own binding. Smoke
subprocesses reuse `_isolated_env` from `tests/test_c01_mcp_stdio.py` and add a
disposable HOME because Darwin does not use `XDG_DATA_HOME` for application data.
Keyring selects its null backend. Profiles, application logs, and credentials
are excluded from uploaded artifacts.

`mac-dependency-evidence` contains `wheels.json`, `source-builds.json`, the included pins, pip logs,
and `python-standalone.json`. Each package result includes the requested version,
target, wheel availability, filename/tag, size, SHA-256, and the macOS minimum
implied by its filename. A pure Python wheel has no macOS minimum in its tag.
For universal2 wheels, the arm64 floor is at least macOS 11 even when the tag
advertises an older Intel floor. These values do not inspect Mach-O load commands
or prove that a wheel's native libraries will load.

The separate `mac-qualified-wheels` artifact includes `wheel-manifest.json`,
lasts three days and supplies C,
including when B fails. Its name means pip accepted those wheels for the target;
it does not mean the application or full dependency graph passed. The other
evidence artifacts last 14 days. Both target probes run even if the first fails.
One failed package does not stop later packages. A failed combined resolution
does not erase successful individual downloads. If the combined resolution
succeeds, any additional Darwin dependencies are also saved for C.

The exclusions are checked in at
[`dependency-exclusions.json`](../../scripts/mac/dependency-exclusions.json):

| Exclusion | Reason |
| --- | --- |
| `pywin32` | Windows Win32 API bindings. |
| `pywin32-ctypes` | Windows Credential Manager support for keyring's Windows backend. |
| `pythonnet` | CLR bridge used by the Windows pywebview renderer. |
| `clr-loader` | CLR loader for that renderer path. |

Portable packages such as `cffi`, `pycparser`, `colorama`, and `proxy_tools` stay
in the probe. No ASR package is excluded because it is difficult to resolve.
The Windows lock does not define a complete Mac payload. Pass 8 adds the five
PyObjC/Cocoa packages through `payload.json` and `ui-wheels.json`. Their pins
and hashes participate in qualification, graph accounting and bundle verification.
Job B builds only the two reviewed pure-Python sdists listed in
`scripts/mac/source-wheels.json`. Their exact URLs were retained in the September
Python qualification. The BLAKE2-256 content addresses are checked before build
hooks run; SHA-256 is also recorded. `pip wheel --no-deps --no-build-isolation
--no-index` uses the hashed `scripts/mac/build-tooling.txt` lock, whose versions
are checked against `build.ps1` by an offline test. There is no
generic source fallback for missing native wheels.

For NLTK, Job B downloads upstream 3.10.3 with the existing builder's SHA-256
requirement, then calls `build_nltk_pathsec_wheel.py`, retaining all source,
patch, member and hash checks. The result must match the Windows build hash
`969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8`.
It never substitutes the unpatched public package. Darwin builder scratch uses
canonical system temporary paths, resolving `/var` before the no-linked-ancestor
checks; Windows build scratch is unchanged. Build provenance is retained in
`source-builds.json`. No real archive was downloaded or built during local checks.

The standalone probe queries the explicit `20261013` release of
`astral-sh/python-build-standalone`. It downloads only the two Python 3.13.16
arm64 assets in `standalone-python.json`, verifies their pinned sizes and hashes,
then discards the archives. Those pins come from the successful download report
in run **39203865751**, where computed hashes matched published digests. Missing
assets, changed metadata, HTTP errors and changed bytes fail qualification.
The archives are neither executed nor used by A or C, which use
`actions/setup-python`.

Import discovery follows statically named local imports recursively from `server`,
`uoink_mcp`, and the tray, splash, and dashboard entry modules. Conditional
imports and function bodies are included so startup functions such as the version
reader and MCP transport cannot hide local dependencies. This deliberately also
covers lazy feature modules. Each module runs in a separate subprocess so one
failure cannot hide the rest. This exercises the Python UI modules' imports
without opening windows. It does not force optional third-party libraries that
product code catches and treats as unavailable. `pip check` records dependency
gaps separately.

The hosted rerun must confirm the source hashes/builds, complete Darwin dependency
resolution, libproc behavior, read-only startup, both portable suites and stdio
inventory. Local fixture tests cannot supply those runtime results.

At pass 2 this workflow did not build an app or DMG, run transcription or decode media,
qualify Intel, establish an older runtime floor, or verify mirror publication.
Later passes added the build, media and installed-copy checks described in BUILD.md.
It performs no Finder installation, Gatekeeper/quarantine, Keychain prompt,
menu-bar interaction, WKWebView rendering, Chrome load-unpacked, or real client
checks. It also does not test login startup, Desktop permissions, sleep/wake,
signing, or notarization. Those require later passes and interactive acceptance.

The release direction remains Apple Silicon, the existing Python UI, CPU
transcription, and opt-in login startup. Developer ID signing and notarization
belong to pass 12. If safe Darwin mirror publication is not proven, the Mac
release must disable mirroring through an explicit capability gate. Passing
these jobs alone cannot justify shipping it enabled.

The qualification helper's offline fixtures use the standard library and
`packaging`'s version parser; they do not import or execute pip:

```text
python -B tests/test_mac_qualification.py
```

Only the hosted workflow should run the networked `wheels` and `standalone`
commands. Windows verification uses the requested `ig-native/Scripts/python.exe`,
BelowNormal priority, the forbidden-live-index environment variable and bytecode
suppression. Tests run from a byte-identical disposable source copy under
`%TEMP%`, with the worktree on `PYTHONPATH` and an inherited guard blocking live
installation access, external connections and port 5179. This keeps existing
source-adjacent Windows test writes out of the worktree. Short temporary test
paths are needed for the existing Windows mirror's long staging filenames.

The original pass-2 verification below predates this repair. The requested
interpreter reports Python 3.14.6. Local static checks pass:
backend compilation, JSON/version checks, all 13 extension JS parses, cached
ESLint 8.57.1 `no-undef`, the noisy-log guard, bash syntax and MCP inventory
(91 full / 35 core). Shellcheck is unavailable, so the bash check uses CI's
`bash -n` fallback. The offline checks do not download/build real dependency
artifacts.

The single full `tests/ -q` run completed in 27:11: **4205 passed, 877 failed,
623 errors, 129 skipped, 1 xfailed, 13 subtests passed**. This is not a green
full-suite result. A verification-only guard used the mutable `TEMP` variable;
a receipt test redirects that variable, causing valid scratch writes to be
refused. The interrupted receipt setup left its own database guard active.
Of the 1500 failure/error events, 1463 directly report one of those two guards;
other assertions also failed downstream. The run additionally caught the new
adapter's absence from the Windows installer list, fixed by moving it into
`_platform.py` rather than changing the Windows payload or exempting the test.

The scratch guard now uses the original absolute temporary root. The receipt-kit
recheck passed **36 tests, 1 existing skip**. After the adapter move, the native
fixtures, state, wheel qualification and unchanged installer completeness tests
passed **43 tests, 2 POSIX-only skips, 6 subtests**. The selection of 1495 distinct
failed/error cases then completed in 13:51: **1488 passed, 6 failed, 1 skipped,
6 subtests passed**. The existing skip reports unavailable Windows symlink
privileges. The remaining six are the two parametrized long-path tests
in `test_staged_refresh`: they require space for a long topic beneath the source
root, and the disposable source-copy path exhausted their fixture preconditions
(`25 >= 30` / `10 >= 20`). The final focused check used a shorter source copy at
`%TEMP%/p2s-9a4d73` and passed **135 tests, 7 skips, 6 subtests** in 41.54 seconds.
All six long-path cases passed, along with the current state, process, installer,
splash, proof-run and install-isolation checks. The skips are the two new POSIX
read-only cases and five existing proof-archive cases whose archive was removed
from the public tree. No product assertion failure remains unresolved by the
follow-up checks; this does not turn the contaminated full run into a green
full-suite result. The full suite was run only once.

All three named Windows timing cases passed in the original full run:
`test_timed_out_vault_worker_cannot_publish_after_return`, both parameterizations
of `test_d12_unowned_temps_are_never_inferred_from_name_or_text`, and
`test_d13_replace_syscall_cannot_complete_after_timeout`.

Local evidence is under
`%TEMP%/uoink-mac-pass2-72983c32cf6a4fcf990e23c89d156ca9/`: `full.xml`/`full.txt`,
`retry.xml`/`retry.txt`, `last-checks.xml`/`last-checks.txt`, `kit-recheck.xml` and
`final-checks.xml`. The latter
records the earlier 129-pass, 4-skip focused check before the adapter move;
it is not a replacement for the final rechecks.

Files changed in this pass:

| Area | Files |
| --- | --- |
| State and startup | `_platform.py`, `server.py`, `uoink_mcp.py`, `uoink_splash.py`, `uoink_dashboard.py` |
| Process identity | `_platform.py`, `uoink_install_isolation.py`, `source_subscriptions.py`, `library_mirror.py`, `scripts/install_receipt/process_identity.py` |
| Qualification workflow and wheels | `.github/workflows/mac-qualify.yml`, `scripts/mac/runner-env.sh`, `scripts/mac/qualify_deps.py`, `scripts/mac/import_smoke.py`, new `scripts/mac/source-wheels.json`, `scripts/build_nltk_pathsec_wheel.py` |
| Regression coverage | New `tests/test_mac_process_identity.py` and `tests/test_mac_state.py`; `tests/test_mac_qualification.py`, `tests/test_finance_topic.py`, `tests/test_u01_backend_enablers.py` |
| Evidence | `docs/mac/QUALIFICATION.md` |
