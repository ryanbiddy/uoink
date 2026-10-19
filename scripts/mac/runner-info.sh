#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$(dirname "$1")"
{
  echo 'uname -m:'
  uname -m
  echo 'sw_vers:'
  sw_vers
  echo 'xcode-select -p:'
  xcode-select -p
  python -VV
  python -c 'import platform, sys, sysconfig; print("executable:", sys.executable); print("machine:", platform.machine()); print("build:", platform.python_build()); print("platform:", sysconfig.get_platform()); print("configure:", sysconfig.get_config_var("CONFIG_ARGS"))'
  python -m pip --version
  python -m pip freeze --all
} 2>&1 | tee "$1"
test "$(uname -m)" = arm64
python -c 'import platform; assert platform.machine() == "arm64", platform.machine()'
