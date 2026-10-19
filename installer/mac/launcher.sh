#!/bin/bash
# Installed as Contents/MacOS/Uoink. No system-Python fallback.
set -euo pipefail
contents="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$contents/Frameworks/Python/bin/python3"
if [[ ! -x "$python" ]]; then
  echo 'Uoink: bundled Python is missing or not executable.' >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP
cd "$contents/Resources"
exec "$python" -B -s "$contents/Resources/server.py" "$@"
