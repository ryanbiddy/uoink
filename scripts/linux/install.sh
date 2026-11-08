#!/bin/sh
set -eu
unset CDPATH

usage() {
    cat <<'HELP'
Usage: sh scripts/linux/install.sh [options]

Install the headless Linux runtime from this checkout.
  --prefix DIR           App folder (default: $HOME/.local/lib/uoink)
  --bin-dir DIR          Command symlink folder (default: $HOME/.local/bin)
  --python PATH          Python >= 3.11 used for the venv (default: python3)
  --no-model             Skip the pinned Whisper base model (~145 MB)
  --with-whisperx        Add podcast diarization with CPU torch and WhisperX
  --skip-ffmpeg-check    Allow image builds to install ffmpeg later
  -h, --help             Show this help
HELP
}

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

prefix=
bin_dir=
python=python3
no_model=0
with_whisperx=0
skip_ffmpeg=0
while [ "$#" -gt 0 ]; do
    case $1 in
        --prefix|--bin-dir|--python)
            if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                fail "$1 requires a value."
            fi
            case $2 in -*) fail "$1 requires a value." ;; esac
            case $1 in
                --prefix) prefix=$2 ;;
                --bin-dir) bin_dir=$2 ;;
                --python) python=$2 ;;
            esac
            shift 2 ;;
        --no-model) no_model=1; shift ;;
        --with-whisperx) with_whisperx=1; shift ;;
        --skip-ffmpeg-check) skip_ffmpeg=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1 (use --help)." ;;
    esac
done
# Defaults resolve after parsing so --help and explicit paths work without HOME.
: "${prefix:=${HOME:?HOME is required unless --prefix is set}/.local/lib/uoink}"
: "${bin_dir:=${HOME:?HOME is required unless --bin-dir is set}/.local/bin}"

repo=$(cd -- "$(dirname -- "$0")/../.." && pwd -P)
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
if ! "$python" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    fail 'Python 3.11 or newer is required. Select it with --python PATH.'
fi
if [ "$skip_ffmpeg" -eq 0 ]; then
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
        fail 'ffmpeg and ffprobe are required. Install them: sudo apt-get install ffmpeg (Debian/Ubuntu), sudo dnf install ffmpeg (Fedora, RPM Fusion), sudo pacman -S ffmpeg (Arch), apk add ffmpeg (Alpine).'
    fi
fi

if ! command -v deno >/dev/null 2>&1; then
    printf '%s\n' 'Note: Deno was not found. YouTube capture works best with Deno 2.3 or newer on PATH (https://docs.deno.com/runtime/getting_started/installation/). Without it, yt-dlp may list fewer YouTube formats.' >&2
fi

mkdir -p -- "$prefix" "$bin_dir"
prefix=$(cd -- "$prefix" && pwd -P)
bin_dir=$(cd -- "$bin_dir" && pwd -P)
case $prefix/ in
    "$repo"/*) fail 'The app prefix must be outside the checkout.' ;;
esac
[ "$bin_dir" != "$repo" ] || fail 'The bin directory must be separate from the checkout.'
[ "$bin_dir" != "$prefix" ] || fail 'The bin directory must be separate from the app prefix.'
if [ -L "$prefix/python" ] || [ -L "$prefix/models" ]; then
    fail 'The python and models folders must belong to the app prefix, not be symlinks.'
fi
if [ -d "$bin_dir/uoink" ]; then
    fail 'The command path already names a directory; choose a different --bin-dir.'
fi

# pip and ensurepip must keep temporary files inside the chosen prefix.
install_tmp=$(mktemp -d "$prefix/.install-XXXXXX")
trap 'rm -rf -- "$install_tmp"' 0
trap 'exit 1' 1 2 3 15
TMPDIR=$install_tmp
TMP=$install_tmp
TEMP=$install_tmp
export TMPDIR TMP TEMP
venv_python=$prefix/python/bin/python3
# A venv without pip is what a failed ensurepip leaves behind (Debian without
# python3-venv). Recreate it so a retry after installing python3-venv works.
if [ ! -x "$venv_python" ] || ! "$venv_python" -m pip --version >/dev/null 2>&1; then
    rm -rf -- "$prefix/python"
    if ! "$python" -m venv "$prefix/python"; then
        rm -rf -- "$prefix/python"
        fail 'Could not create the Python venv. On Debian/Ubuntu, install python3-venv, then retry.'
    fi
fi
"$venv_python" -c 'import sys; sys.exit(sys.version_info < (3, 11))' ||
    fail 'The existing venv requires Python 3.11 or newer.'
if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
    fail 'The venv has no pip. On Debian/Ubuntu, install python3-venv, then recreate the venv.'
fi

"$venv_python" - "$repo" "$prefix" <<'PY'
import json
from pathlib import Path
import shutil
import sys

source, target = (Path(arg).resolve() for arg in sys.argv[1:])
manifest = json.loads((source / "scripts/mac/payload.json").read_text(encoding="utf-8"))
paths = [*manifest["paths"], *manifest["mac_files"], "uoink", "VERSION",
         "requirements-linux.txt", "requirements-linux-whisperx.txt"]


def copy(relative):
    if (relative.suffix.lower() in {".cmd", ".bat", ".ps1", ".pyc", ".pyo"}
            or relative.match("helper/mac_*.py")
            or relative.parts[:2] == ("scripts", "mac")
            or relative.name.startswith(".env")
            or relative.name in {"__pycache__", ".git", "token.txt", "server.pid", "server.log"}):
        return
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"Invalid payload path: {relative}")
    src, dest = source / relative, target / relative
    if src.is_symlink() or dest.is_symlink() or not dest.resolve().is_relative_to(target):
        raise SystemExit(f"Linked payload path: {relative}")
    if src.is_dir():
        if target.is_relative_to(src):
            raise SystemExit(f"App prefix must be outside payload folder: {src}")
        dest.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            copy(child.relative_to(source))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


for name in dict.fromkeys(paths):
    copy(Path(name))
PY

# Ignore user pip configuration and caches; all installed files belong to the venv.
PIP_CONFIG_FILE=/dev/null
export PIP_CONFIG_FILE
"$venv_python" -m pip --isolated --disable-pip-version-check --no-cache-dir install --upgrade pip
"$venv_python" -m pip --isolated --disable-pip-version-check --no-cache-dir install -r "$prefix/requirements-linux.txt"
if [ "$with_whisperx" -eq 1 ]; then
    "$venv_python" -m pip --isolated --disable-pip-version-check --no-cache-dir install -r "$prefix/requirements-linux-whisperx.txt"
fi

model_status='skipped (--no-model; existing models kept)'
if [ "$no_model" -eq 0 ]; then
    cache_dir=${XDG_CACHE_HOME:-$HOME/.cache}/uoink/whisper-model
    # The stager requires an empty destination. Verify before replacing an
    # existing bundled model, keeping the venv and other models on upgrades.
    model_dest=$prefix/models/whisper-bundled
    [ ! -L "$model_dest" ] || fail 'The bundled model folder must not be a symlink.'
    if [ -e "$model_dest" ]; then
        model_dest=$install_tmp/whisper-bundled
    fi
    "$venv_python" "$repo/scripts/stage_whisper_model.py" \
        --cache "$cache_dir" --dest "$model_dest"
    if [ "$model_dest" != "$prefix/models/whisper-bundled" ]; then
        "$venv_python" - "$model_dest" "$prefix/models/whisper-bundled" <<'PY'
from pathlib import Path
import shutil
import sys

source, target = map(Path, sys.argv[1:])
for path in (target, *target.rglob("*")):
    if path.is_symlink():
        raise SystemExit(f"Linked model path: {path}")
if target.exists() and not target.is_dir():
    raise SystemExit(f"Bundled model path is not a directory: {target}")
# Replace, not merge: a new pin must not leave files from the old revision.
shutil.rmtree(target)
shutil.move(str(source), str(target))
PY
    fi
    model_status='staged (pinned base model, SHA-256 verified)'
fi

chmod +x "$prefix/uoink" "$prefix/cli/uoink"
ln -sf -- "$prefix/uoink" "$bin_dir/uoink"
printf '\nApp folder: %s\nData folder: %s\nWhisper model: %s\n' \
    "$prefix" "${XDG_DATA_HOME:-$HOME/.local/share}/Uoink" "$model_status"
printf 'Next: uoink status\n      uoink connect claude-code\n'
case :${PATH:-}: in
    *:"$bin_dir":*) ;;
    *) printf 'Warning: %s is not on PATH. Add it before running uoink.\n' "$bin_dir" >&2 ;;
esac
