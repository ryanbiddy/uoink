#!/bin/bash
# Development shell equivalent of the native bundle launcher.
set -euo pipefail
for variable in "${!DYLD_@}"; do unset "$variable"; done
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE PYTHONEXECUTABLE
entry=server.py
if [[ $# == 0 || "${1:-}" == --helper ]]; then
  entry=uoink_supervisor.py
  if [[ "${1:-}" == --helper ]]; then shift; fi
fi
contents="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$contents/Resources/Python/bin/python3"
if [[ ! -x "$python" ]]; then
  echo 'Uoink: bundled Python is missing or not executable.' >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
cd "$contents/Resources"
exec "$python" -B -s "$contents/Resources/$entry" "$@"
