# Package manager manifests

Ready-to-submit manifests for Uoink 3.11.2. The hashes come from the release's
checksum table and match GitHub's asset digests.

## winget (Windows)

`winget/manifests/r/ReplayRyan/Uoink/3.11.2/` holds the version, installer and
en-US locale files (schema 1.12.0, validated against winget's JSON schemas).
The package identifier follows the installer's publisher name, `ReplayRyan`.

The Inno installer is per-user (`PrivilegesRequired=lowest`), installs silently
with winget's default Inno switches, skips the "set up the browser button" step
when silent, and keeps the "add uoink to PATH" task on, so `uoink` is listed
under `Commands`.

To submit:

1. Fork [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) and copy
   `manifests/r/ReplayRyan/Uoink/3.11.2/` to the same path in the fork.
2. Optional: `winget validate --manifest <that folder>` and
   `winget install --manifest <that folder>` in Windows Sandbox.
3. Open one pull request for this one package version and sign the CLA when the bot asks.

The pipeline runs antivirus and unwanted-software scans and a silent install as a
standard user. The installer is unsigned; that isn't a stated requirement, but a
SmartScreen or antivirus flag would fail the scans.

For later releases, `wingetcreate update ReplayRyan.Uoink --version <v> --urls <exe URL>`
updates the manifests from the new installer.

## Homebrew (Mac)

`homebrew/Casks/uoink.rb` installs the notarized DMG, links the `uoink` command
from `Uoink.app/Contents/Helpers`, and unloads the login item on uninstall.
`zap` leaves `~/Library/Application Support/Uoink` alone because it holds the
user's saved library.

The official `homebrew/cask` repository needs 225 GitHub stars (or 90 forks or
watchers) and a repository at least 30 days old, so start with a tap:

1. Create a public repository named `ryanbiddy/homebrew-uoink`.
2. Copy `Casks/uoink.rb` into it.
3. Users install with `brew install --cask ryanbiddy/uoink/uoink`.

`brew audit --cask --strict --online ryanbiddy/uoink/uoink` and `brew style`
check it on a Mac. Bump `version` and `sha256` for each release; `livecheck`
reads the latest GitHub release.
