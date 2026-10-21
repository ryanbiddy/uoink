# Uoink on macOS: build status

There is no public macOS installer yet. The private build targets Apple Silicon
and requires macOS 15 or later. See [Build the macOS CI bundle](mac/BUILD.md)
for the ad-hoc-signed app, DMG, pinned Python and wheel graph, and hosted checks.

Library mirroring stays disabled (`library_mirror_unavailable_macos`). Bundled
FFmpeg has runtime checks; unavailable media reports `media_requires_ffmpeg`.
Windows remains the shipped installer.

Pass 8 adds the menu bar, first-run window, Cocoa dashboard, folder picker
and clipboard. Its new hosted checks still need a run. Developer ID signing,
notarization and [interactive Mac acceptance](mac/ACCEPTANCE.md) remain pending.
Intel is not included. Follow [the private install steps](mac/INSTALL.md) for
the test DMG; this is not a public release.
