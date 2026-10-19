# macOS build and packaging surface

The unsigned arm64 build is implemented in `scripts/mac/build_bundle.py`,
invoked by `build-mac.sh` and the `mac-build` job in
`.github/workflows/mac-qualify.yml`. Its first hosted run remains pending.
[Build documentation](../mac/BUILD.md) describes inputs, commands, evidence,
capability limits and release work still required.

- `scripts/mac/payload.json`: reviewed application source list, checked against
  the unchanged Windows staging list and local import closure.
- `scripts/mac/standalone-python.json`: Python archive pins.
- `scripts/mac/wheel_lock.py`: generate and verify the hash lock from the
  successful qualification graph; install only its matching wheel artifact.
- `installer/mac/launcher.sh`: installed as `Contents/MacOS/Uoink`, resolves
  `Contents/Frameworks/Python/bin/python3`, disables runtime bytecode writes
  and user site packages, and has no system-Python fallback.
- `scripts/mac/build_bundle.py`: emits a versioned plist, notices, full file
  and native loader inventories, size report and permission-preserving tar.
  The old `installer/mac/Info.plist` template is no longer used by the builder.
- `scripts/mac/bundle_smoke.py`: relocation, isolated helper health, CLI status,
  MCP 91/35 inventory, Pillow operation and before/after bundle comparison.
- `_platform.py`: mirror and media capabilities; `server.py`, `library_mirror.py`,
  MCP and dashboard surfaces consume them before unsupported work can run.

No FFmpeg CLI is bundled. The reason and proposed source-build approach are in
`scripts/mac/FFMPEG.md`. Library mirroring is unavailable on Darwin. Automatic
Darwin tray and splash startup are deferred to the AppKit/UI pass. The existing
LaunchAgent and entitlement templates are not installed or used for signing.
