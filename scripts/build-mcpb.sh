#!/usr/bin/env bash
# Build the Uoink Claude Desktop MCP bundle (.mcpb).
#
# A .mcpb file is a ZIP with manifest.json at its root. This is the POSIX
# companion to scripts/build-mcpb.ps1 (PowerShell is the primary path on the
# Windows build box). The bundle is a thin launcher that connects Claude
# Desktop to the Uoink helper installed from https://uoink.app/install.
#
# Spec: github.com/modelcontextprotocol/mcpb (manifest_version 0.4)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/.mcpb"
MANIFEST="$SRC_DIR/manifest.json"
OUT_DIR="${1:-$REPO_ROOT/dist}"

[ -f "$MANIFEST" ] || { echo "manifest.json not found at $MANIFEST" >&2; exit 1; }

# --- Validate manifest -----------------------------------------------------
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
VERSION="$("$PY" - "$MANIFEST" <<'PYEOF'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"))
cmd=m["server"]["mcp_config"]["command"]
args=" ".join(m["server"]["mcp_config"]["args"])
assert cmd.endswith("python/python.exe"), f"command not python.exe: {cmd}"
assert "uoink_mcp.py" in args, f"args do not invoke uoink_mcp.py: {args}"
assert m["server"]["entry_point"]=="uoink_mcp.py", "entry_point must be uoink_mcp.py"
print(m["version"])
PYEOF
)"
echo "Manifest validated OK (valid JSON; entry command matches working stdio command)."

# M-2: derive the bundle version from the product VERSION at build time so the
# .mcpb can never drift from the release. The committed manifest.version is a
# fallback kept equal by the test_release_version parity test.
if [ -f "$REPO_ROOT/VERSION" ]; then
  REPO_VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
  if [ -n "$REPO_VERSION" ] && [ "$REPO_VERSION" != "$VERSION" ]; then
    echo "WARN: manifest.version ($VERSION) != VERSION ($REPO_VERSION); stamping the bundle with VERSION." >&2
    VERSION="$REPO_VERSION"
  fi
else
  echo "WARN: VERSION file not found; using committed manifest.version ($VERSION)." >&2
fi
echo "Bundle version: $VERSION"

# --- Stage -----------------------------------------------------------------
BUILD_DIR="$REPO_ROOT/build/mcpb/uoink"
rm -rf "$BUILD_DIR"; mkdir -p "$BUILD_DIR"
cp "$MANIFEST" "$BUILD_DIR/manifest.json"
# Stamp the derived version into the staged manifest (only the top-level
# "version" value changes; original formatting is preserved).
"$PY" - "$BUILD_DIR/manifest.json" "$VERSION" <<'PYEOF'
import re, sys
path, version = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
text = re.sub(r'"version"\s*:\s*"[^"]*"', '"version": "%s"' % version, text, count=1)
open(path, "w", encoding="utf-8", newline="\n").write(text)
PYEOF
for f in uoink_mcp.py uoink_mcp_tools.py; do
  [ -f "$REPO_ROOT/$f" ] && cp "$REPO_ROOT/$f" "$BUILD_DIR/$f" || true
done
[ -f "$SRC_DIR/README.md" ] && cp "$SRC_DIR/README.md" "$BUILD_DIR/README.md" || true
[ -f "$REPO_ROOT/assets/logo-mark-256.png" ] && cp "$REPO_ROOT/assets/logo-mark-256.png" "$BUILD_DIR/icon.png" || echo "WARN: icon not found"

# --- Pack ------------------------------------------------------------------
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/uoink-$VERSION.mcpb"
rm -f "$OUT_FILE"
if command -v mcpb >/dev/null 2>&1; then
  echo "Packing with official mcpb CLI..."
  mcpb pack "$BUILD_DIR" "$OUT_FILE"
elif command -v zip >/dev/null 2>&1; then
  echo "mcpb CLI not found; packing with zip (ZIP -> .mcpb)..."
  ( cd "$BUILD_DIR" && zip -r -q "$OUT_FILE" . )
else
  echo "mcpb CLI and zip not found; packing with Python stdlib (ZIP -> .mcpb)..."
  "$PY" - "$BUILD_DIR" "$OUT_FILE" <<'PYEOF'
import pathlib
import sys
import zipfile

source = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(source).as_posix())
PYEOF
fi
[ -f "$OUT_FILE" ] || { echo "Failed to produce $OUT_FILE" >&2; exit 1; }
echo "Built $OUT_FILE"
echo "Install: double-click the .mcpb, or drag it into Claude Desktop > Settings > Extensions."
