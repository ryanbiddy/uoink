#!/usr/bin/env bash
# One-command Uoink smoke test (macOS, Linux, Git Bash). Dev only, never shipped.
# Seeds an isolated library, starts the helper hidden on a non-5179 port, runs the
# API, CLI, dashboard, accessibility and extension suites, stops the helper and
# prints a pass/fail table. Arguments pass through to scripts/qa_smoke.py, e.g.
#   scripts/qa_smoke.sh --suites api
#   scripts/qa_smoke.sh --break search-500
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
python="${UOINK_QA_PYTHON:-python3}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$repo/_scratch/ms-playwright}"
exec "$python" "$repo/scripts/qa_smoke.py" "$@"
