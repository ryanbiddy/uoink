# Uoink on macOS

Uoink 3.11.2 adds a Mac preview for Apple Silicon on macOS 15 or later. Download
`Uoink-<VERSION>-macos-arm64.dmg` from the
[latest release](https://github.com/ryanbiddy/uoink/releases/latest) and follow
[the install steps](mac/INSTALL.md). The app and DMG are signed with a Developer
ID and notarized by Apple. See [Build the macOS CI bundle](mac/BUILD.md) for the
app, DMG, pinned Python and wheel graph, signing and hosted checks.

Library mirroring stays disabled (`library_mirror_unavailable_macos`). Bundled
FFmpeg has runtime checks; unavailable media reports `media_requires_ffmpeg`.
Each Mac release passes [interactive Mac acceptance](mac/ACCEPTANCE.md) on a
real Mac before it ships. Intel Macs are not supported.
