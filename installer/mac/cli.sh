#!/bin/bash
# Resolve symlinks so a user-created PATH link still finds the installed app.
set -euo pipefail
for variable in "${!DYLD_@}"; do unset "$variable"; done
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE PYTHONEXECUTABLE
source_path="${BASH_SOURCE[0]}"
while [[ -L "$source_path" ]]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  source_path="$(readlink "$source_path")"
  [[ "$source_path" = /* ]] || source_path="$source_dir/$source_path"
done
contents="$(cd -P "$(dirname "$source_path")/.." && pwd)"
python="$contents/Frameworks/Python/bin/python3"
[[ -x "$python" && -f "$contents/Resources/uoink_cli.py" ]] || {
  echo 'Uoink installation is incomplete. Reinstall Uoink.app from the DMG.' >&2; exit 1;
}
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
exec "$python" -B -s "$contents/Resources/uoink_cli.py" "$@"
