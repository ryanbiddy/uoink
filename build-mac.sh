#!/usr/bin/env bash
#
# Uoink macOS build orchestrator -- SKELETON (cc/mac-prep).
#
# STATUS: incomplete scaffold. This script was written on a Windows machine
# with no macOS toolchain, so NONE of the Mac-only steps below (framework
# Python relocation, .icns generation, codesign, notarytool, create-dmg) have
# ever been executed or verified. Every such step is marked `# TODO(mac):`.
# It is committed as the concrete starting point for the first real Mac build,
# not as a working build. See docs/MAC-BUILD-PLAN.md for the full plan and the
# exact list of what still needs a Mac + an Apple Developer account.
#
# Mirrors the Windows build.ps1 pipeline:
#   build.ps1 step                     -> build-mac.sh equivalent
#   -------------------------------------------------------------
#   Python embeddable (embed-amd64)    -> python-build-standalone framework
#   ffmpeg BtbN win64-lgpl.exe         -> macOS LGPL ffmpeg (arm64 + x86_64)
#   pip install yt-dlp + deps          -> same, into the bundled framework
#   generate_icon.py (.ico)            -> .icns via iconutil
#   Inno Setup (uoink.iss -> .exe)     -> .app bundle + create-dmg (.dmg)
#   verify_install.ps1                 -> verify-install.sh (files-only)
#   (Windows: unsigned, SmartScreen)   -> codesign + notarytool + stapler
#
# One-command build (once finished):  ./build-mac.sh
#
set -euo pipefail

# ---- Guard: macOS only --------------------------------------------------
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build-mac.sh must run on macOS (uname -s reported: $(uname -s))." >&2
  echo "This is the Windows-authored scaffold from cc/mac-prep -- it is not" >&2
  echo "runnable off a Mac. See docs/MAC-BUILD-PLAN.md." >&2
  exit 2
fi

# ---- Paths --------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${REPO_ROOT}/build-mac"
CACHE_DIR="${BUILD_DIR}/cache"
APP_NAME="Uoink"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
CONTENTS="${APP_BUNDLE}/Contents"
RESOURCES="${CONTENTS}/Resources"
MACOS_DIR="${CONTENTS}/MacOS"

# ---- Versions (keep in lockstep with build.ps1) -------------------------
# The Windows build pins these in build.ps1; the Mac build must match the
# same yt-dlp / Pillow / mcp / etc. versions so both platforms ship the same
# behaviour. Only the interpreter + ffmpeg SOURCES differ per-OS.
PYTHON_VERSION="3.11.9"          # python-build-standalone tag, not python.org embeddable
YTDLP_VERSION="2026.03.17"
PILLOW_VERSION="10.4.0"
MCP_VERSION="1.27.1"
KEYRING_VERSION="25.7.0"
PYSTRAY_VERSION="0.19.5"
PYWEBVIEW_VERSION="5.4"
FASTER_WHISPER_VERSION="1.2.1"
WHISPERX_VERSION="3.8.6"
FFMPEG_VERSION="n7.1"            # match BtbN LGPL n7.1 used on Windows

# ---- Signing identity (Ryan's -- see docs/MAC-BUILD-PLAN.md) -------------
# These come from an Apple Developer account ($99/yr). Left unset here so an
# unsigned local test build still produces a .app; the codesign + notarize
# steps no-op with a loud warning when unset.
: "${APPLE_DEV_ID_APP:=}"       # "Developer ID Application: Ryan Biddy (TEAMID)"
: "${APPLE_TEAM_ID:=}"          # 10-char Apple Team ID
: "${AC_NOTARY_PROFILE:=}"      # notarytool keychain profile name

echo "==> Uoink macOS build (SKELETON) v${PYTHON_VERSION} python / yt-dlp ${YTDLP_VERSION}"
mkdir -p "${CACHE_DIR}" "${RESOURCES}" "${MACOS_DIR}"

# ---- 1. Bundled Python --------------------------------------------------
# Windows uses the python.org "embeddable" zip. There is NO macOS embeddable
# build. Use astral-sh/python-build-standalone: a relocatable, framework-style
# CPython that runs from an arbitrary path inside the .app.
#   https://github.com/astral-sh/python-build-standalone/releases
# For a universal2 app, either fetch the universal2 asset or lipo-merge the
# arm64 + x86_64 builds. Place it at Contents/Resources/python so the runtime
# layout matches server.py's _bundled_interpreter(): python/bin/python3.
echo "==> [1/7] Fetch + relocate framework Python"
# TODO(mac): download python-build-standalone ${PYTHON_VERSION} (arm64 + x86_64),
#            lipo into universal2, extract to "${RESOURCES}/python", verify
#            "${RESOURCES}/python/bin/python3" runs and reports the version.
PYBIN="${RESOURCES}/python/bin/python3"    # server.py expects this path

# ---- 2. pip install runtime deps into the bundle ------------------------
echo "==> [2/7] pip install runtime dependencies"
# TODO(mac): "${PYBIN}" -m pip install \
#   "yt-dlp==${YTDLP_VERSION}" "Pillow==${PILLOW_VERSION}" "mcp==${MCP_VERSION}" \
#   "keyring==${KEYRING_VERSION}" "pystray==${PYSTRAY_VERSION}" \
#   "pywebview==${PYWEBVIEW_VERSION}" "faster-whisper==${FASTER_WHISPER_VERSION}" \
#   "whisperx==${WHISPERX_VERSION}"
# NOTE: pywebview on macOS uses the system WKWebView (pyobjc), NOT pythonnet.
#       Do NOT install pythonnet on Mac (it is Windows/.NET-only).
# NOTE: pystray on macOS uses the AppKit backend and REQUIRES the process to be
#       a proper .app bundle with a running NSApplication event loop. Evaluate
#       rumps as a simpler menu-bar alternative (see MAC-BUILD-PLAN.md).

# ---- 3. ffmpeg + ffprobe (LGPL) ----------------------------------------
echo "==> [3/7] Bundle ffmpeg + ffprobe (LGPL, universal2)"
# TODO(mac): fetch macOS LGPL ffmpeg + ffprobe (evermeet.cx / osxexperts, or a
#            Homebrew LGPL build), lipo to universal2, place at
#            "${RESOURCES}/bin/ffmpeg" and "${RESOURCES}/bin/ffprobe".
#            server.py prepends HERE/bin to PATH -- same mechanism as Windows.
#            Keep the LGPL text + a source offer in THIRD-PARTY-NOTICES.md.

# ---- 4. Copy the helper source tree ------------------------------------
echo "==> [4/7] Stage helper source into the bundle"
# The full list is authoritative in build.ps1 (step 2g) + installer/uoink.iss.
# Keep this in sync -- a missing module crashes the helper before it binds 5179.
HELPER_FILES=(
  server.py index.py _platform.py migrate_install.py channels.py workspaces.py
  claims.py scripts.py voice_dna.py writing_studio.py page_extractor.py
  source_manifest.py openapi_bridge.py reddit_extractor.py x_extractor.py
  memory_layer.py podcasts.py mobile_playlists.py whisper_runner.py
  uoink_mcp.py uoink_mcp_tools.py uoink_reliability.py yoink_mcp.py
  uoink_tray.py uoink_splash.py uoink_dashboard.py yt_extract.py
  requirements.txt topics.json VERSION
)
HELPER_DIRS=( helper uoink_core skills voice_dna assets defaults migrations extension )
for f in "${HELPER_FILES[@]}"; do
  cp "${REPO_ROOT}/${f}" "${RESOURCES}/"
done
for d in "${HELPER_DIRS[@]}"; do
  cp -R "${REPO_ROOT}/${d}" "${RESOURCES}/"
done

# ---- 5. Bundle skeleton: Info.plist + launcher + icon ------------------
echo "==> [5/7] Assemble .app skeleton"
cp "${REPO_ROOT}/installer/mac/Info.plist" "${CONTENTS}/Info.plist"
# TODO(mac): generate Uoink.icns from assets/logo-mark-color.png:
#   mkdir Uoink.iconset; sips -z <size> <size> logo-mark-color.png ...
#   iconutil -c icns Uoink.iconset -o "${RESOURCES}/Uoink.icns"
# The MacOS/Uoink launch stub sets cwd to Resources and execs the bundled
# python3 on server.py. A minimal launcher is committed at
# installer/mac/launcher.sh as the starting point.
cp "${REPO_ROOT}/installer/mac/launcher.sh" "${MACOS_DIR}/${APP_NAME}"
chmod +x "${MACOS_DIR}/${APP_NAME}"

# ---- 6. Codesign + notarize (Apple Developer account required) ----------
echo "==> [6/7] Codesign + notarize"
if [[ -z "${APPLE_DEV_ID_APP}" ]]; then
  echo "    WARNING: APPLE_DEV_ID_APP unset -- producing an UNSIGNED build."
  echo "    Gatekeeper will block it (right-click > Open, or it will be quarantined)."
  echo "    A shippable build needs a Developer ID cert + notarization."
else
  echo "    TODO(mac): codesign --deep --force --options runtime --timestamp \\"
  echo "               --entitlements installer/mac/entitlements.plist \\"
  echo "               --sign \"${APPLE_DEV_ID_APP}\" \"${APP_BUNDLE}\""
  # NOTE: --deep is discouraged for final signing; sign nested binaries
  #       (python3, ffmpeg, ffprobe, .dylibs) inside-out. See MAC-BUILD-PLAN.md.
fi

# ---- 7. Package the .dmg ------------------------------------------------
echo "==> [7/7] Build .dmg"
VERSION="$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION")"
DMG_PATH="${BUILD_DIR}/Uoink-${VERSION}.dmg"
# TODO(mac): create-dmg --volname "Uoink ${VERSION}" \
#            --app-drop-link 480 170 --icon "${APP_NAME}.app" 160 170 \
#            "${DMG_PATH}" "${APP_BUNDLE}"
# TODO(mac): notarize the .dmg with `xcrun notarytool submit --wait` then
#            `xcrun stapler staple "${DMG_PATH}"`.
echo ""
echo "SKELETON complete. Real artifact NOT produced -- finish the TODO(mac)"
echo "steps on a Mac. Target output: ${DMG_PATH}"
