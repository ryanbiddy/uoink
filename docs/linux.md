# Uoink on Linux

Use Uoink on a Linux desktop, server or headless sandbox to capture YouTube,
podcast and web transcripts, then search them through MCP. This includes
Docker, Codespaces, Claude Code and Codex cloud sandboxes, and E2B.

The helper and `uoink mcp` run headless. Linux has no tray, app windows or
browser extension. An agent uses the CLI or MCP tools to capture and search.

## Requirements

- Git and Python 3.11 or newer.
- Python venv support. On Debian or Ubuntu, install it with
  `sudo apt-get install python3-venv`.
- Both `ffmpeg` and `ffprobe` on PATH. The installer prints these commands
  when either is missing.

| Distribution | Command |
|---|---|
| Debian / Ubuntu | `sudo apt-get install ffmpeg` |
| Fedora, RPM Fusion | `sudo dnf install ffmpeg` |
| Arch | `sudo pacman -S ffmpeg` |
| Alpine | `apk add ffmpeg` |

The [pinned `base` model](../scripts/whisper_model_pin.json) has about 145 MB
of weights. Allow a few hundred MB for the model, its download cache and the
Python venv, plus space for captures. WhisperX needs a much larger download.

## Install

Install from a checkout. There is no Linux package.

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

Add the command folder to your shell's PATH if it is missing. The installer
prints a warning but does not edit your shell configuration.

```sh
export PATH="$HOME/.local/bin:$PATH"
```

The installer accepts these options. Run
`sh uoink/scripts/linux/install.sh --help` to print them.

| Option | Effect |
|---|---|
| `--prefix DIR` | App folder. Defaults to `~/.local/lib/uoink`; must be outside the checkout. |
| `--bin-dir DIR` | Command symlink folder. Defaults to `~/.local/bin`. |
| `--python PATH` | Python 3.11 or newer to create the venv. Defaults to `python3`. |
| `--no-model` | Skip staging the pinned Whisper `base` model. Keeps an existing model. |
| `--with-whisperx` | Add WhisperX and CPU torch for podcast speaker labels. |
| `--skip-ffmpeg-check` | Let image builds install ffmpeg later. Media capture still needs ffmpeg and ffprobe at runtime. |
| `-h`, `--help` | Print help and exit. |

### Files and folders

| What | Default path |
|---|---|
| App and bundled model | `~/.local/lib/uoink` |
| Python venv | `~/.local/lib/uoink/python` |
| Command symlink | `~/.local/bin/uoink` |
| Data and library index | `${XDG_DATA_HOME:-$HOME/.local/share}/Uoink` |
| Model download cache | `${XDG_CACHE_HOME:-$HOME/.cache}/uoink/whisper-model` |

Without XDG overrides, the data folder is `~/.local/share/Uoink` and the model
cache is `~/.cache/uoink/whisper-model`. Mutable state, including helper logs
and its token, stays in the data folder.

By default, captures go to `~/Desktop/Uoink` if `~/Desktop` exists. When there
is no Desktop folder, captures go to `<data>/output`. Podcast audio and
transcripts stay under the data folder. A configured output folder takes
precedence over these defaults.

### Upgrade and uninstall

Update the checkout, then re-run `install.sh` with the same options. The
installer updates the app in place and keeps the venv and library data.

To uninstall, stop any helper and MCP processes, then remove the app folder
and command symlink. The default paths are `~/.local/lib/uoink` and
`~/.local/bin/uoink`. Use your chosen paths if you set `--prefix` or `--bin-dir`.

You can also remove these folders to delete the saved data and download cache.

- `${XDG_DATA_HOME:-$HOME/.local/share}/Uoink` holds the library. Keep it if
  you want to reinstall without losing the library.
- `${XDG_CACHE_HOME:-$HOME/.cache}/uoink/whisper-model` holds the installer's
  model download cache.
- The `uoink` source checkout is separate from the installed app.

Captures in `~/Desktop/Uoink` or a custom output folder are separate too.
Removing the app does not remove them.

## Check the install

```sh
uoink status
uoink tools
```

`status` reads local state without contacting the helper. On Linux,
`capabilities.media.available` is `true` when both ffmpeg and ffprobe are on
PATH. If either is missing, it is `false` with code `media_requires_ffmpeg`;
the reason includes the distribution commands above. An `ok: true` status
does not by itself mean media capture is ready.

`reliability_model` describes the selected Whisper model. `cached: true`
means a local copy is available. After a default install, `source` is
`"bundled"` and `bundled_model` is `"base"`. A separately downloaded model
has source `"downloaded"`. With `--no-model` and no existing copy, the model
is not ready for local transcription. Caption fetches and saved-library
reads do not need it.

`tools` lists the registry tools. Stdio MCP and CLI tool calls work without
a running helper. Start the optional HTTP helper with `uoink serve`.
To force headless behavior even when a display is present, set
`UOINK_HEADLESS=1` in the process environment.

```sh
UOINK_HEADLESS=1 uoink serve
```

Linux also detects headless mode when neither `DISPLAY` nor `WAYLAND_DISPLAY`
is set. The helper still serves the dashboard at `/dashboard` on its local
URL; it does not open a dashboard window in headless mode.

## Transcription

`get_transcript` reuses saved transcripts, then tries YouTube captions before
speech recognition. Videos without captions and podcast audio use local CPU
faster-whisper with the bundled `base` model. The default install needs no
model download at transcription time.

For podcast speaker labels, re-run the installer with WhisperX enabled.

```sh
sh uoink/scripts/linux/install.sh --with-whisperx
```

This adds WhisperX and CPU torch, a large download. Without it, podcast
transcripts have no diarization, even when the caller requests it. WhisperX
can need separate models for alignment and speaker labels. If speaker labeling
fails, Uoink still returns the transcript without labels. Whisper runs on CPU
only in this Linux install.

## Docker

Build from the checkout root, then run the MCP stdio server with stdin open.

```sh
docker build -f docker/capture.Dockerfile -t uoink-capture .
docker run -i --rm -v uoink-data:/home/uoink/.local/share/Uoink uoink-capture
```

The named volume `uoink-data` keeps the library after the container exits.
The image runs as non-root UID/GID `10001:10001`. Its app folder, `/opt/uoink`,
is root-owned and read-only. The pinned Whisper `base` model, about 145 MB of
weights, is fetched and SHA-256 checked at build time. Transcription uses
that local copy at runtime.

To make the rest of the container filesystem read-only, keep the library
volume writable and provide temporary folders.

```sh
docker run -i --rm --read-only \
  --tmpfs /tmp --tmpfs /home/uoink:uid=10001,gid=10001 \
  -v uoink-data:/home/uoink/.local/share/Uoink uoink-capture
```

CI runs the capture smoke with these flags and `--network none`, without the
volume.

The root `Dockerfile` is the offline MCP introspection image for registries.
It cannot capture. See [Glama build configuration](GLAMA-BUILD.md) for that
image and [docker/capture.Dockerfile](../docker/capture.Dockerfile) for this one.

## Connect an agent

Print the recipe for the client running on the same machine as Uoink.

```sh
uoink connect --list
uoink connect claude-code
uoink connect codex
uoink connect cursor
```

Other Linux recipes include Gemini CLI and VS Code. `--list` includes all
recipes, including ones for other platforms. An unsupported recipe refuses
to print a config on Linux. See the [client table](connect-your-agent.md#client-recipes-and-documentation-checks)
for platform coverage.

`connect` prints Linux paths and does not edit client files. Config goes to
stdout; the destination and notes go to stderr. For example,
`uoink connect cursor` prints this shape for `~/.cursor/mcp.json`, with your
actual install paths in place of `/home/you`.

```json
{
  "mcpServers": {
    "uoink": {
      "command": "/home/you/.local/lib/uoink/python/bin/python3",
      "args": [
        "/home/you/.local/lib/uoink/uoink_mcp.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "UOINK_MCP_TOOLSET": "core"
      }
    }
  }
}
```

Merge the entry into the existing file and preserve other servers. Cursor
gets the `core` toolset by default. Restart the client's MCP connection after
saving.

### Docker clients

For a client that accepts `mcpServers` JSON, use Docker as the command. The
client must be able to run Docker and find the image you built.

```json
{
  "mcpServers": {
    "uoink": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "uoink-data:/home/uoink/.local/share/Uoink",
        "uoink-capture"
      ]
    }
  }
}
```

Keep `-i` for MCP stdio. Do not add `-t`; the client exchanges JSON-RPC over
stdin and stdout.

### Cloud sandboxes

Put the dependency and `install.sh` commands above in the sandbox setup
script. Run `uoink connect` inside that sandbox so the paths refer to its
filesystem. The agent process must have `~/.local/bin` on PATH, or use the
absolute command paths that `connect` prints.

For Claude Code, run the `claude mcp add` command printed by
`uoink connect claude-code`. For Codex, merge the output of
`uoink connect codex` into `~/.codex/config.toml`, or `CODEX_HOME/config.toml`
if configured. Keep the data folder on persistent storage if the sandbox
will be discarded.

## What does not work, or may not

YouTube often blocks or rate-limits datacenter and cloud IPs. Caption fetches
can fail in cloud sandboxes. `get_transcript` then falls back to Whisper only
if the audio download works; from a blocked IP, it often will not. Podcast
feeds and most web pages are not affected by YouTube's IP restrictions.

Linux has no browser extension, tray or app windows. Headless Linux has no
desktop notifications or dashboard window; the dashboard is still served at
the helper URL. There is no GPU acceleration in this install. ARM64 is
untested; only x86_64 runs in CI. Installation is from a checkout, not a
distribution package.

## CI coverage

The [CI workflow](../.github/workflows/ci.yml) has two Linux jobs for this
runtime.

- `linux-install` installs and upgrades a checkout with `--no-model`. It
  checks status, tool listing, MCP stdio, connection paths, helper state and
  the missing-ffmpeg status.
- `linux-capture-image` builds the capture image with the pinned model. With
  networking disabled, it serves a local podcast fixture, downloads the
  audio, transcribes it, publishes it to the library and searches the result
  through MCP. It runs as UID 10001 with a read-only filesystem and tmpfs
  storage.

These checks use synthetic fixtures. They do not prove that YouTube will
accept requests from a particular cloud IP.
