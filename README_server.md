# Local Server (`server.py`)

The browser extension talks to this server at `http://127.0.0.1:5179`.
It runs the same yt-dlp + ffmpeg pipeline as the GUI, but exposed as JSON
endpoints with CORS allowed for youtube.com.

## Dependencies

Pure Python stdlib — **no fastapi/flask/uvicorn install required**.

The optional `win11toast` package is used for a friendly startup toast; if
it's missing, the server still runs (silently).

```
pip install win11toast      # optional
```

You also still need the same external tools as the GUI:

```
pip install yt-dlp
winget install Gyan.FFmpeg
```

## Running

Double-click **`start_server.bat`**, or:

```
pythonw server.py
```

(Use `python server.py` instead if you want logs streaming to a console.)

PowerShell equivalent:

```
.\start_server.ps1
```

Verify it's alive at `http://127.0.0.1:5179/ping`. A live helper returns HTTP
200 with `"ok": true`; the full response shape is documented below.

Logs are written to `server.log` next to `server.py`.

## Auto-start at login

1. Press <kbd>Win</kbd>+<kbd>R</kbd>, type `shell:startup`, press Enter.
2. Drop a shortcut to `start_server.bat` into that folder.

The server launches with `pythonw`, so it sits silently in the background — no
console window. Stop it via Task Manager (kill the `pythonw.exe` process) or by
running the GUI's launcher and then closing it; cleaner: leave it running.

## Endpoints

### `GET /ping`

Values vary with the installed version, selected Whisper model, downloaded
models, output-root recovery, and corpus state. The response shape is:

```json
{
  "ok": true,
  "version": "<current version>",
  "whisperx_available": false,
  "whisper_model": "base",
  "whisperx_model_loaded": false,
  "index_recovering": false,
  "output_root_fallback": false,
  "path_integrity": {
    "ok": true,
    "checked": 0,
    "missing": 0
  }
}
```

`path_integrity` always contains `ok`, `checked`, and `missing`. When indexed
files are missing it also contains a human-readable `hint`; if the index scan
itself fails it instead contains an `error` string.

### `POST /extract`

Body:

```json
{"url": "https://www.youtube.com/watch?v=...", "interval": 30}
```

Response on success:

```json
{
  "ok": true,
  "folder": "C:\\Users\\you\\Desktop\\Uoink\\<slug>",
  "combined_md": "# Title\n\n...",
  "screenshot_count": 12,
  "title": "Original video title"
}
```

The server also calls `os.startfile(folder)` on success so File Explorer pops
open at the result folder automatically.

Response on failure:

```json
{"ok": false, "error": "ffmpeg failed: ..."}
```

## CORS

Allowed origins: `https://www.youtube.com`, `https://youtube.com`.
Methods: `GET, POST, OPTIONS`. Headers: `Content-Type`. Preflight handled.

If you hit a CORS error from somewhere else, edit `ALLOWED_ORIGINS` in
`server.py`.
