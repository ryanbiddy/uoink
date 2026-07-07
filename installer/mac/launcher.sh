#!/bin/bash
#
# Uoink.app/Contents/MacOS/Uoink -- launch stub (cc/mac-prep SKELETON).
#
# STATUS: never executed on a Mac. This is the starting point for the .app's
# CFBundleExecutable. build-mac.sh copies it to Contents/MacOS/Uoink.
#
# It runs the bundled framework Python on the helper's server.py with the
# bundle's Resources dir as cwd, so server.py's HERE-relative layout
# (python/, bin/, assets/, etc.) resolves exactly as it does on Windows.
#
# The Windows equivalent is the Start Menu / autostart command:
#   "{app}\python\pythonw.exe" "{app}\server.py"
# Here there is no windowless interpreter variant -- a .app-launched process
# has no console -- so we exec python3 directly.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../Resources" && pwd)"
cd "${HERE}"

PYBIN="${HERE}/python/bin/python3"   # matches server.py _bundled_interpreter()
if [[ ! -x "${PYBIN}" ]]; then
  # Degrade to whatever python3 is on PATH so a half-built dev bundle still
  # launches something rather than dying silently. A real build always ships
  # the bundled interpreter.
  PYBIN="$(command -v python3 || true)"
fi
if [[ -z "${PYBIN}" ]]; then
  echo "Uoink: no bundled or system python3 found" >&2
  exit 1
fi

exec "${PYBIN}" "${HERE}/server.py" "$@"
