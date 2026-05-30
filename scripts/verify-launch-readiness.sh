#!/usr/bin/env bash
# verify-launch-readiness.sh
# Pre-launch technical readiness check for Uoink v2.1.
# Run from repo root: bash scripts/verify-launch-readiness.sh
#
# Verifies the technical (not infra) items from docs/store-listing.md:147-158:
#   - USE_MOCK_API = false           (extension/popup.js:8)
#   - Windows installer download URL points at the current release
#   - All MOCK_FORCE_* flags = false (extension/lib/mock-api.js)
#   - manifest.json version = VERSION file  (extension/manifest.json)
#   - No console.log("[Yoink|Uoink]"...) (extension/lib/extract.js, Sprint 14 S1)
#   - No obvious dev artifacts       (extension/ tree)
#
# Exits 0 if all checks pass, 1 otherwise.

set -u

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || { echo "FAIL: cannot cd to repo root"; exit 1; }

PASS=0
FAIL=0
RESULTS=()

ok() {
  PASS=$((PASS + 1))
  RESULTS+=("PASS  $1")
}

bad() {
  FAIL=$((FAIL + 1))
  RESULTS+=("FAIL  $1")
}

# ---------------------------------------------------------------------------
# 1. USE_MOCK_API = false in extension/popup.js
# ---------------------------------------------------------------------------
if [[ ! -f extension/popup.js ]]; then
  bad "popup.js: file not found at extension/popup.js"
else
  USE_MOCK_LINE="$(grep -n '^const USE_MOCK_API' extension/popup.js | head -1)"
  if [[ -z "$USE_MOCK_LINE" ]]; then
    bad "popup.js: USE_MOCK_API declaration not found"
  elif echo "$USE_MOCK_LINE" | grep -q 'USE_MOCK_API = false'; then
    ok "popup.js: USE_MOCK_API = false  ($USE_MOCK_LINE)"
  else
    bad "popup.js: USE_MOCK_API is NOT false  ($USE_MOCK_LINE)"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Windows installer download URL points at current VERSION
# ---------------------------------------------------------------------------
if [[ ! -f extension/setup.js ]]; then
  bad "setup.js: file not found at extension/setup.js"
else
  INSTALLER_LINE="$(grep -n '^const INSTALLER_PUBLISHED' extension/setup.js | head -1)"
  VERSION_FOR_URL="$(tr -d '[:space:]' < VERSION 2>/dev/null || true)"
  DOWNLOAD_LINE="$(grep -n "download/v${VERSION_FOR_URL}/Uoink-Setup-${VERSION_FOR_URL}\\.exe" extension/setup.js | head -1)"
  if [[ -n "$INSTALLER_LINE" ]] && echo "$INSTALLER_LINE" | grep -q 'INSTALLER_PUBLISHED = true'; then
    ok "setup.js: INSTALLER_PUBLISHED = true  ($INSTALLER_LINE)"
  elif [[ -n "$DOWNLOAD_LINE" ]]; then
    ok "setup.js: Windows download URL points at v${VERSION_FOR_URL}  ($DOWNLOAD_LINE)"
  elif [[ -z "$INSTALLER_LINE" ]]; then
    bad "setup.js: no INSTALLER_PUBLISHED flag and no current-version download URL found"
  else
    bad "setup.js: INSTALLER_PUBLISHED is NOT true  ($INSTALLER_LINE)"
  fi
fi

# ---------------------------------------------------------------------------
# 3. All MOCK_FORCE_* flags = false in extension/lib/mock-api.js
# ---------------------------------------------------------------------------
if [[ ! -f extension/lib/mock-api.js ]]; then
  bad "mock-api.js: file not found at extension/lib/mock-api.js"
else
  # Find every `const MOCK_FORCE_* = <value>;` declaration.
  MOCK_FLAGS="$(grep -nE '^\s*const MOCK_FORCE_[A-Z_]+ *=' extension/lib/mock-api.js)"
  if [[ -z "$MOCK_FLAGS" ]]; then
    bad "mock-api.js: no MOCK_FORCE_* declarations found (unexpected)"
  else
    TRUE_FLAGS="$(echo "$MOCK_FLAGS" | grep -E '= *true' || true)"
    if [[ -z "$TRUE_FLAGS" ]]; then
      COUNT="$(echo "$MOCK_FLAGS" | wc -l | tr -d ' ')"
      ok "mock-api.js: all $COUNT MOCK_FORCE_* flags are false"
    else
      bad "mock-api.js: one or more MOCK_FORCE_* flags are true:"
      while IFS= read -r line; do
        RESULTS+=("        $line")
      done <<< "$TRUE_FLAGS"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 4. manifest.json + VERSION match helper/_version.py
# ---------------------------------------------------------------------------
if [[ ! -f extension/manifest.json ]]; then
  bad "manifest.json: file not found at extension/manifest.json"
elif [[ ! -f helper/_version.py ]]; then
  bad "helper/_version.py: file not found"
elif [[ ! -f VERSION ]]; then
  bad "VERSION: file not found at repo root"
else
  EXPECTED_VERSION="$(sed -nE 's/^__version__[[:space:]]*=[[:space:]]*["'\'']([0-9]+\.[0-9]+\.[0-9]+)["'\''].*/\1/p' helper/_version.py | head -1)"
  VERSION_FILE_VALUE="$(tr -d '[:space:]' < VERSION)"
  if [[ -z "$EXPECTED_VERSION" ]]; then
    bad "helper/_version.py: __version__ semver not found"
  elif [[ "$VERSION_FILE_VALUE" != "$EXPECTED_VERSION" ]]; then
    bad "VERSION: $VERSION_FILE_VALUE does NOT match helper/_version.py ($EXPECTED_VERSION)"
  else
    ok "VERSION: matches helper/_version.py ($EXPECTED_VERSION)"
  fi
  EXPECTED_VERSION_RE="$(printf '%s' "$EXPECTED_VERSION" | sed 's/[][\\.^$*+?{}|()]/\\&/g')"
  VERSION_LINE="$(grep -nE '"version"\s*:\s*"' extension/manifest.json | head -1)"
  if [[ -z "$VERSION_LINE" ]]; then
    bad "manifest.json: version field not found"
  elif echo "$VERSION_LINE" | grep -qE '"version"\s*:\s*"'"$EXPECTED_VERSION_RE"'"'; then
    ok "manifest.json: version = helper/_version.py ($EXPECTED_VERSION)  ($VERSION_LINE)"
  else
    bad "manifest.json: version does NOT match helper/_version.py ($EXPECTED_VERSION)  ($VERSION_LINE)"
  fi
fi

# ---------------------------------------------------------------------------
# 5. No noisy console.log("[Yoink|Uoink]"...) in extract.js (Sprint 14 S1)
# ---------------------------------------------------------------------------
if [[ ! -f extension/lib/extract.js ]]; then
  bad "extract.js: file not found at extension/lib/extract.js"
else
  # Catches the legacy [Yoink] prefix and the renamed [Uoink] one.
  LOG_HITS="$(grep -nE 'console\.log\(\s*"\[(Yoink|Uoink)\]' extension/lib/extract.js || true)"
  if [[ -z "$LOG_HITS" ]]; then
    ok "extract.js: no noisy console.log(\"[Yoink|Uoink]\"...) calls"
  else
    bad "extract.js: console.log(\"[Yoink|Uoink]\"...) still present (Sprint 14 S1 not landed):"
    while IFS= read -r line; do
      RESULTS+=("        $line")
    done <<< "$LOG_HITS"
  fi
fi

# ---------------------------------------------------------------------------
# 6. No obvious dev artifacts in extension/
# ---------------------------------------------------------------------------
ART_HITS="$(find extension -type f \( \
  -name '.DS_Store' -o \
  -name 'Thumbs.db' -o \
  -name '*.bak' -o \
  -name '*.orig' -o \
  -name '*.swp' -o \
  -name '*.log' \
\) 2>/dev/null)"
if [[ -d extension/node_modules ]]; then
  ART_HITS="${ART_HITS}"$'\n'"extension/node_modules"
fi
ART_HITS="$(echo "$ART_HITS" | sed '/^$/d')"

if [[ -z "$ART_HITS" ]]; then
  ok "extension/: no obvious dev artifacts (.DS_Store, *.bak, *.swp, node_modules, ...)"
else
  bad "extension/: dev artifacts found:"
  while IFS= read -r line; do
    RESULTS+=("        $line")
  done <<< "$ART_HITS"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=== Uoink launch-readiness check ==="
for line in "${RESULTS[@]}"; do
  echo "$line"
done
echo "------------------------------------"
echo "PASS: $PASS    FAIL: $FAIL"
echo

# Non-zero exit if anything failed
if [[ "$FAIL" -gt 0 ]]; then
  echo "Not ready to ship. Resolve the FAILs above, re-run."
  exit 1
fi

echo "All technical checks green. Remaining items are infra (screenshots, promo tiles,"
echo "privacy policy URL live, support email deliverable, landing page) — see"
echo "docs/store-listing.md:147-158 for the full checklist."
exit 0
