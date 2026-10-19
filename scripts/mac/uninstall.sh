#!/bin/bash
# Usage: bash uninstall.sh /path/to/Uoink.app [--remove]
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo 'Uoink uninstall requires macOS.' >&2; exit 2; }
app="${1:?Usage: uninstall.sh /path/to/Uoink.app [--remove]}"
shift
[[ ! -L "$app" ]] || { echo 'Select Uoink.app itself, not a symlink.' >&2; exit 2; }
app="$(cd "$(dirname "$app")" && pwd)/$(basename "$app")"
cd "$app/Contents/Resources"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP
exec "$app/Contents/Resources/Python/bin/python3" -B -s -m helper.mac_lifecycle uninstall "$app" "$@"
