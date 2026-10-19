#!/bin/bash
set -euo pipefail
for variable in "${!DYLD_@}"; do unset "$variable"; done
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE PYTHONEXECUTABLE
app="${1:?Uoink: choose the installed Uoink.app in the extension settings.}"
python="$app/Contents/Frameworks/Python/bin/python3"
script="$app/Contents/Resources/uoink_mcp.py"
if [[ "$app" != /* || ! -x "$python" || ! -f "$script" || ! -f "$app/Contents/Resources/uoink_mcp_tools.py" ]]; then
  echo "Uoink is not installed at $app. Install Uoink.app from the DMG, then choose its location in this extension's Uoink app setting." >&2
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONIOENCODING=utf-8 PYTHONUTF8=1
exec "$python" -B -s "$script"
