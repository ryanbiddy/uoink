#!/usr/bin/env bash
# Run before any product import. Never upload this disposable profile.
set -euo pipefail
root="$(mktemp -d "$RUNNER_TEMP/uoink-mac.XXXXXX")"
mkdir -p "$root/home/Desktop" "$root/profile" "$root/output" \
  "$root/local" "$root/roaming" "$root/data" "$root/config" "$root/cache" \
  "$RUNNER_TEMP/mac-evidence"
{
  echo "HOME=$root/home"
  echo "USERPROFILE=$root/home"
  echo "LOCALAPPDATA=$root/local"
  echo "APPDATA=$root/roaming"
  echo "XDG_DATA_HOME=$root/data"
  echo "XDG_CONFIG_HOME=$root/config"
  echo "XDG_CACHE_HOME=$root/cache"
  echo "UOINK_ISOLATED_PROFILE=$root/profile"
  echo "UOINK_ISOLATED_PORT=5187"
  echo "UOINK_OUTPUT_DIR=$root/output"
  echo "YOINK_OUTPUT_DIR=$root/output"
  echo "PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring"
} >> "$GITHUB_ENV"
