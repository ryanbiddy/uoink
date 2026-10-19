# Uoink on macOS: build status

There is no public macOS installer yet. Passes 1-4 passed the hosted macOS 15
arm64 checks on Python 3.11 and 3.13. The new build pipeline assembles an
unsigned Apple Silicon app for CI testing. Hosted run 39244020379 failed the
portable suite and native-loader inventory; the repairs still need a hosted
rerun. See [Build the macOS CI bundle](mac/BUILD.md) for commands,
artifact contents and the evidence required from that run.

The first app bundle deliberately disables library mirroring
(`library_mirror_unavailable_macos`) and media features that need FFmpeg
(`media_requires_ffmpeg`). The dashboard and API report these limitations.
Windows remains the shipped installer.

Signing, notarization, a DMG, LaunchAgent, menu bar and first-run UI are still
pending. The bundle targets the macOS 15 runner; macOS 14 is a provisional
future minimum, and Intel is not included. Do not treat the CI archive as a
verified Finder installation or a public release.
