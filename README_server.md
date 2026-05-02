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

Verify it's alive — `http://127.0.0.1:5179/ping` should return:

```json
{"ok": true, "version": "1.0"}
```

Logs are written to `server.log` next to `server.py`.

## Auto-start at login

1. Press <kbd>Win</kbd>+<kbd>R</kbd>, type `shell:startup`, press Enter.
2. Drop a shortcut to `start_server.bat` into that folder.

The server launches with `pythonw`, so it sits silently in the background — no
console window. Stop it via Task Manager (kill the `pythonw.exe` process) or by
running the GUI's launcher and then closing it; cleaner: leave it running.

## Endpoints

### `GET /ping`

```json
{"ok": true, "version": "1.0"}
```

### `POST /extract`

Body:

```json
{"url": "https://www.youtube.com/watch?v=...", "interval": 30}
```

Response on success:

```json
{
  "ok": true,
  "folder": "C:\\Users\\you\\Desktop\\Yoink\\<slug>",
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
