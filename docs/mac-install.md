# Uoink on macOS — current status

**Uoink does not run on macOS today. There is no macOS build, no `.dmg`,
and no `Uoink.app`.** Uoink currently ships as a Windows installer only.

This page previously described a macOS installation flow — a `.dmg`, an
app bundle, a LaunchAgent, a universal binary — that was never built and
never released. That was wrong, and it is corrected here rather than
quietly deleted, so anyone who followed those instructions understands
what happened.

## What actually works on a Mac right now

Two of the three tools in the suite are pure Python and install cleanly
on macOS today (both have macOS continuous integration passing):

- **zing** (the video director) — install from source per its README.
- **writer** (prose and scripts) — install from source per its README.

Both work standalone. They do not require uoink to be installed, and
they degrade honestly when it is absent.

## What blocks uoink specifically

Uoink bundles a Python runtime, `ffmpeg`, `yt-dlp`, and machine-learning
dependencies, and ships a tray application. Porting it means solving:

- **Distribution shape** — either a non-app helper install (no Apple
  developer account required) or a signed, notarized `.app` (which
  requires signing every nested binary in the ML dependency tree
  individually; Apple forbids the shortcut).
- **Architecture reality** — a universal binary is not currently
  achievable with our dependency set. The honest target would be Apple
  Silicon (arm64) on macOS 14 or later.
- **ffmpeg licensing** — the LGPL build uoink uses on Windows has no
  macOS equivalent from the same source, and the common macOS suppliers
  ship GPL builds. This is an unresolved licensing question, not just a
  packaging one.

The full analysis, with sources, lives in
[MAC-BUILD-PLAN.md](MAC-BUILD-PLAN.md).

## If you want macOS support

Open or upvote an issue. Mac support is a real roadmap item, but it will
be announced when a build exists — not before. Nothing on this page
promises a date.
