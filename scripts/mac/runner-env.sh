#!/usr/bin/env bash
# Run before any product import. Never upload this disposable profile.
set -euo pipefail
root="$(mktemp -d "$RUNNER_TEMP/uoink-mac.XXXXXX")"
mkdir -p "$root/home/Desktop" "$root/profile" "$root/output" \
  "$root/local" "$root/roaming" "$root/data" "$root/config" "$root/cache" \
  "$RUNNER_TEMP/mac-evidence"
{
  # Signing restores this HOME for security and codesign in that step only.
  echo "UOINK_RUNNER_HOME=${UOINK_RUNNER_HOME:-$HOME}"
  echo "HOME=$root/home"
  echo "USERPROFILE=$root/home"
  echo "LOCALAPPDATA=$root/local"
  echo "APPDATA=$root/roaming"
  echo "XDG_DATA_HOME=$root/data"
  echo "XDG_CONFIG_HOME=$root/config"
  echo "XDG_CACHE_HOME=$root/cache"
  # The suite creates its own isolated bindings. A global binding changes
  # production-default assertions and leaks one settings file across tests.
  if [ "${1:-isolated}" != "suite" ]; then
    echo "UOINK_ISOLATED_PROFILE=$root/profile"
    echo "UOINK_ISOLATED_PORT=5187"
  fi
  echo "UOINK_OUTPUT_DIR=$root/output"
  echo "YOINK_OUTPUT_DIR=$root/output"
  echo "PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring"
} >> "$GITHUB_ENV"
