#!/usr/bin/env bash
# Assemble an ad-hoc-signed arm64 CI app and DMG from the qualified wheel artifact.
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'build-mac.sh requires a macOS arm64 runner.' >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
exec python3 -B "$root/scripts/mac/build_bundle.py" "$@"
