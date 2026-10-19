# macOS qualification, pass 1

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
macOS 14 remains a provisional minimum, subject to later runtime testing.

| Job | Evidence |
| --- | --- |
| A, portable tests | The same `tests/` suite and `pytest Pillow "mcp<2"` installation as required CI, on Python 3.11 and 3.13. Each run uploads JUnit XML, environment details, and installed versions. No new platform skips are added. |
| B, dependency graph | Every included installer pin is probed separately for CPython 3.13 at both `macosx_14_0_arm64` and `macosx_15_0_arm64`. A combined resolver attempt then checks dependencies for each target. Missing wheels remain failures in the report. |
| C, import smoke | A fresh Python 3.13 venv installs only wheels found by B, with `--no-index --no-deps`. It records installation failures, `pip check`, imports, and actual `initialize` and `tools/list` replies from `python uoink_mcp.py` in full and core modes. Current expected counts are 91 and 35, checked against the existing stdio test inventory. |

All jobs set a disposable HOME, profile, output, and platform data/cache
directories before product imports. This matters because `server.py` creates
its log handler while importing. The isolation profile uses port 5187. Smoke
subprocesses reuse `_isolated_env` from `tests/test_c01_mcp_stdio.py` and add a
disposable HOME because Darwin does not use `XDG_DATA_HOME` for application data.
Keyring selects its null backend. Profiles, application logs, and credentials
are excluded from uploaded artifacts.

`mac-dependency-evidence` contains `wheels.json`, the included pins, pip logs,
and `python-standalone.json`. Each package result includes the requested version,
target, wheel availability, filename/tag, size, SHA-256, and the macOS minimum
implied by its filename. A pure Python wheel has no macOS minimum in its tag.
For universal2 wheels, the arm64 floor is at least macOS 11 even when the tag
advertises an older Intel floor. These values do not inspect Mach-O load commands
or prove that a wheel's native libraries will load.

The separate `mac-qualified-wheels` artifact lasts three days and supplies C,
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
The Windows lock does not define a complete Mac payload. Missing PyObjC/Cocoa
dependencies and Mac-specific graph additions must be reviewed in a later lock.
This pass does not invent pins or replace the reviewed
`nltk==3.10.3+uoink.pathsec1` patch with upstream NLTK. That local wheel is not
provided by this workflow, so its public-index lookup is expected to fail.
Source-only releases and native packages without compatible CPython 3.13 arm64
wheels will also fail the binary-only probe.

The standalone probe queries the latest public
`astral-sh/python-build-standalone` release. It downloads all matching Python
3.13 `aarch64-apple-darwin` `install_only` and `install_only_stripped` candidates,
records their release/name/URL, byte size and SHA-256, then discards the archives.
It checks published size and hash when available. Missing candidates, download
errors, and mismatches are explicit failures. This is candidate discovery, not
a pinned runtime: the archives are neither executed nor used by A or C, which
use `actions/setup-python`.

Import discovery follows statically named local imports recursively from `server`,
`uoink_mcp`, and the tray, splash, and dashboard entry modules. Conditional
imports and function bodies are included so startup functions such as the version
reader and MCP transport cannot hide local dependencies. This deliberately also
covers lazy feature modules. Each module runs in a separate subprocess so one
failure cannot hide the rest. This exercises the Python UI modules' imports
without opening windows. It does not force optional third-party libraries that
product code catches and treats as unavailable. `pip check` records dependency
gaps separately.

First-run failures may include the patched NLTK wheel, other missing wheels,
Darwin backend dependencies, and tests that still assume Linux `/proc` or Windows
paths. Pass 1 records those failures without changing product behavior.

This workflow does not build an app or DMG, run transcription or decode media,
qualify Intel, prove the macOS 14 runtime floor, or verify mirror publication.
It performs no Finder installation, Gatekeeper/quarantine, Keychain prompt,
menu-bar interaction, WKWebView rendering, Chrome load-unpacked, or real client
checks. It also does not test login startup, Desktop permissions, sleep/wake,
signing, or notarization. Those require later passes and interactive acceptance.

The release direction remains Apple Silicon, the existing Python UI, CPU
transcription, and opt-in login startup. Developer ID signing and notarization
belong to pass 12. If safe Darwin mirror publication is not proven, the Mac
release must disable mirroring through an explicit capability gate. Passing
these jobs alone cannot justify shipping it enabled.

The helper's offline fixture tests use only the standard library:

```text
python -B tests/test_mac_qualification.py
```

Only the hosted workflow should run the networked `wheels` and `standalone`
commands during this pass. Local verification covers the fixture tests, YAML,
MCP inventory, and the static checks from `ci.yml`; it does not run the full
Windows suite.
